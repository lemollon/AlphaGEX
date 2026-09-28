"""PAPER-ONLY forward call log for EMBER's XSP Flow bot (xsp-flow-v1).

WHY THIS EXISTS
----------------
XSP Flow is paused live (``EMBER_XSP_LIVE=0``) but Leron still wants its
UP/calls signal tracked forward so a sample builds up while it is unarmed.
The live executor (``xsp_flow_live.py``) only records a durable, structured
result once a real order is broker-confirmed -- a dry run just writes
``entry.state=dry_run`` into an ephemeral JSON state blob that gets
overwritten day to day and never gets a settlement computed for it (the
SETTLEMENT agent mode only reconciles real bot-owned positions). This module
is the missing record: one row per trading day in Postgres, independent of
the live/dry-run agent flow entirely, with a real market-priced entry NBBO
and a real cash-settled payout.

🚨 LOGGING NEVER DEPENDS ON ARMING. Nothing in this module reads
``EMBER_XSP_LIVE``. It is registered in ``runtime.register()`` as its own
scheduler jobs, gated only on ``EMBER_XSP_ENABLED`` (same "whole module is
off" carve-out ``tv_call_log.py`` uses for TVBook) -- never on the live flag.

NO ORDERS, NO AGENT, NO BROKER LOCK. This module never launches the Claude
Robinhood-Agentic subprocess, never calls the runtime's advisory-lock
acquisition, and never imports anything from the live executor's
order-tool allowlist. It prices XSP verticals with a direct,
read-only Tradier HTTP GET (the same self-contained client TSUNAMI uses,
``bots/tsunami/data/tradier_client.py``) and reads the frozen UP/DOWN signal
from the SAME public confirm-history endpoint the live executor already
polls (``xsp_flow_live.fetch_history``). Both are pure market-data reads.

GEOMETRY MATCHES THE LIVE BOT EXACTLY -- this module imports
``strike_geometry``, ``executable_debit``, ``debit_is_allowed``,
``settlement_payout``, ``within_scheduled_window``, ``ENTRY_CUTOFF_CT``, and
``SIGNAL_MAX_AGE_SECONDS`` from ``xsp_flow_live`` rather than
re-implementing them, so the paper record never silently drifts from what
live ENTRY would compute.

ONE ROW PER TRADE_DATE, idempotent/frozen once ``captured_at`` is set.
``record_tick()`` runs on the same per-minute cadence as the live cycle
(8:30-15:05 CT) but only spends a Tradier call the FIRST tick a fresh signal
is seen (age <= ``SIGNAL_MAX_AGE_SECONDS``, before ``ENTRY_CUTOFF_CT``) --
that one quote becomes the permanent "entry NBBO at the coded decision
minute" for the day. Every later tick that day is a cheap no-op once
``captured_at`` is set. A day that never sees a signal, or sees one only
after it has gone stale/past cutoff, still gets exactly one row -- with
``would_trade=False`` and a ``reason`` -- so the table is never
survivorship-biased toward days that fired.

WHAT ``would_trade`` DOES AND DOES NOT MODEL: it is the deterministic subset
of live ENTRY's gates this module can evaluate without a broker session --
fresh signal, before the 14:54 CT cutoff, and an executable package debit
(long ask - short bid) inside $0.01-$0.20. It does NOT model live's
broker-side checks (exact account, buying power, collateral preview,
existing-position reconciliation, the daily trade cap, the realized-loss
halt) -- those all require the Robinhood MCP session this module
intentionally never touches.

SETTLEMENT reuses the SAME confirm-history rows the signal came from: every
row already carries a ``close_spot`` field (backfilled by the risk-advisor's
own ``confirm_record_close`` after the session ends), on the identical
scale ``strike_geometry`` expects (XSP's own spot, not full-size SPX). No
Robinhood ``get_index_historicals`` call is needed. ``settle_pending()``
walks every captured ``would_trade=True`` row with ``settled_at IS NULL``,
and settles it the first tick that a ``close_spot`` shows up for that date.

NEVER RAISES. ``record_tick``/``settle_pending`` catch every exception,
log a warning, and return -- a paper-logging failure must never take the
real scheduler tick down with it.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any, Callable, Optional
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.engine import Engine

from . import xsp_flow_live as live
from ..bots.tsunami.data import tradier_client as _tradier

logger = logging.getLogger("spreadworks.ember.xsp_paper_ledger")

CT = ZoneInfo("America/Chicago")
UTC = timezone.utc
TABLE = "ember_xsp_paper_ledger"

_OPTION_TYPE_NAME = {"C": "call", "P": "put"}

_COLUMNS_SQL = """
    trade_date               DATE NOT NULL UNIQUE,
    run_ts_utc                TIMESTAMP NOT NULL,
    run_ts_ct                 TIMESTAMP NOT NULL,
    direction                 TEXT,
    signal_fired_at            TIMESTAMP,
    signal_fired_spot          DOUBLE PRECISION,
    signal_armed                TEXT,
    signal_putcall_z            DOUBLE PRECISION,
    would_trade                  BOOLEAN NOT NULL DEFAULT FALSE,
    reason                       TEXT,
    option_type                  TEXT,
    base_strike                  INTEGER,
    long_strike                  INTEGER,
    short_strike                 INTEGER,
    expiry                       TEXT,
    long_ask                     DOUBLE PRECISION,
    short_bid                    DOUBLE PRECISION,
    quote_ts_utc                 TIMESTAMP,
    debit                        DOUBLE PRECISION,
    debit_ok                     BOOLEAN,
    captured_at                  TIMESTAMP,
    settlement_value             DOUBLE PRECISION,
    payout                       DOUBLE PRECISION,
    pnl                          DOUBLE PRECISION,
    settled_at                   TIMESTAMP,
    created_at                   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
"""


def _ddl() -> str:
    """SQLite has no BIGSERIAL; see tv_call_log._ddl() for the same split."""
    return f"CREATE TABLE IF NOT EXISTS {TABLE} (\n    id BIGSERIAL PRIMARY KEY,\n{_COLUMNS_SQL}\n)"


def _ddl_sqlite() -> str:
    return f"CREATE TABLE IF NOT EXISTS {TABLE} (\n    id INTEGER PRIMARY KEY AUTOINCREMENT,\n{_COLUMNS_SQL}\n)"


def ensure_table(engine: Optional[Engine]) -> None:
    """Idempotent create. Never raises."""
    if engine is None:
        return
    try:
        with engine.begin() as conn:
            conn.execute(text(_ddl_sqlite() if engine.dialect.name == "sqlite" else _ddl()))
    except Exception as exc:  # noqa: BLE001
        logger.warning("[xsp_paper_ledger] table create failed: %r", exc)


def _now_utc_ct() -> tuple[datetime, datetime]:
    now_utc = datetime.now(UTC)
    return now_utc.replace(tzinfo=None), now_utc.astimezone(CT).replace(tzinfo=None)


def _raw_row_for_date(rows: list[dict[str, Any]], trade_date: date) -> Optional[dict[str, Any]]:
    for row in rows:
        if isinstance(row, dict) and row.get("d") == trade_date.isoformat():
            return row
    return None


def _fetch_existing(engine: Engine, trade_date: date) -> Optional[dict[str, Any]]:
    with engine.begin() as conn:
        row = conn.execute(
            text(f"SELECT * FROM {TABLE} WHERE trade_date = :d"), {"d": trade_date}
        ).mappings().first()
    return dict(row) if row else None


_UPSERT_SQL = f"""
    INSERT INTO {TABLE} (
        trade_date, run_ts_utc, run_ts_ct, direction, signal_fired_at,
        signal_fired_spot, signal_armed, signal_putcall_z, would_trade, reason,
        option_type, base_strike, long_strike, short_strike, expiry,
        long_ask, short_bid, quote_ts_utc, debit, debit_ok, captured_at
    ) VALUES (
        :trade_date, :run_ts_utc, :run_ts_ct, :direction, :signal_fired_at,
        :signal_fired_spot, :signal_armed, :signal_putcall_z, :would_trade, :reason,
        :option_type, :base_strike, :long_strike, :short_strike, :expiry,
        :long_ask, :short_bid, :quote_ts_utc, :debit, :debit_ok, :captured_at
    )
    ON CONFLICT (trade_date) DO UPDATE SET
        run_ts_utc = EXCLUDED.run_ts_utc, run_ts_ct = EXCLUDED.run_ts_ct,
        direction = EXCLUDED.direction, signal_fired_at = EXCLUDED.signal_fired_at,
        signal_fired_spot = EXCLUDED.signal_fired_spot, signal_armed = EXCLUDED.signal_armed,
        signal_putcall_z = EXCLUDED.signal_putcall_z, would_trade = EXCLUDED.would_trade,
        reason = EXCLUDED.reason, option_type = EXCLUDED.option_type,
        base_strike = EXCLUDED.base_strike, long_strike = EXCLUDED.long_strike,
        short_strike = EXCLUDED.short_strike, expiry = EXCLUDED.expiry,
        long_ask = EXCLUDED.long_ask, short_bid = EXCLUDED.short_bid,
        quote_ts_utc = EXCLUDED.quote_ts_utc, debit = EXCLUDED.debit,
        debit_ok = EXCLUDED.debit_ok, captured_at = EXCLUDED.captured_at
"""


def _upsert(engine: Engine, params: dict[str, Any]) -> None:
    ensure_table(engine)
    with engine.begin() as conn:
        conn.execute(text(_UPSERT_SQL), params)


def _default_chain_fn(expiry: str) -> list[dict[str, Any]]:
    return _tradier.get_chain_contracts("XSP", expiration=expiry)


def _quote_legs(
    option_type_letter: str,
    long_strike: int,
    short_strike: int,
    expiry: str,
    chain_fn: Callable[[str], list[dict[str, Any]]],
) -> dict[str, Any]:
    """Read-only Tradier chain lookup for the two legs. Never raises -- any
    failure comes back as a `note` explaining what was missing."""
    opt_name = _OPTION_TYPE_NAME.get(option_type_letter)
    try:
        contracts = chain_fn(expiry) or []
    except Exception as exc:  # noqa: BLE001
        return {"note": f"chain fetch failed: {exc}"}
    if not contracts:
        return {"note": "no_0dte_expiry"}

    def _find(strike: int) -> Optional[dict[str, Any]]:
        for c in contracts:
            if c.get("option_type") == opt_name and abs(float(c.get("strike", -1)) - strike) < 1e-6:
                return c
        return None

    long_c = _find(long_strike)
    short_c = _find(short_strike)
    if long_c is None or short_c is None:
        missing = []
        if long_c is None:
            missing.append(f"long {long_strike}{option_type_letter}")
        if short_c is None:
            missing.append(f"short {short_strike}{option_type_letter}")
        return {"note": f"missing contract(s): {', '.join(missing)}"}
    long_ask = float(long_c.get("ask") or 0)
    short_bid = float(short_c.get("bid") or 0)
    if long_ask <= 0 or short_bid <= 0:
        return {"note": "missing_quote", "long_ask": long_ask or None, "short_bid": short_bid or None}
    return {"long_ask": long_ask, "short_bid": short_bid}


def _evaluate(
    now_ct: datetime,
    history_rows: list[dict[str, Any]],
    already_captured: bool,
    chain_fn: Callable[[str], list[dict[str, Any]]],
) -> Optional[dict[str, Any]]:
    """Pure decision function -- no DB, no network beyond `chain_fn`. Returns
    None when there is nothing to write this tick (already captured, or the
    window is closed and there's nothing new to finalize)."""
    trade_date = now_ct.date()
    try:
        signal = live.signal_for_date(history_rows, trade_date)
    except live.FlowError as exc:
        logger.warning("[xsp_paper_ledger] signal parse failed: %r", exc)
        signal = None
        signal_error = str(exc)
    else:
        signal_error = None

    run_ts_utc, run_ts_ct = _now_utc_ct()
    base = {
        "trade_date": trade_date, "run_ts_utc": run_ts_utc, "run_ts_ct": run_ts_ct,
        "direction": None, "signal_fired_at": None, "signal_fired_spot": None,
        "signal_armed": None, "signal_putcall_z": None,
        "option_type": None, "base_strike": None, "long_strike": None, "short_strike": None,
        "expiry": None, "long_ask": None, "short_bid": None, "quote_ts_utc": None,
        "debit": None, "debit_ok": None, "captured_at": None,
    }

    if signal is None:
        if already_captured:
            return None
        now_time = now_ct.time().replace(tzinfo=None)
        terminal = now_time >= live.WINDOW_END_CT
        base["would_trade"] = False
        base["reason"] = signal_error or "no frozen signal today"
        if terminal:
            base["captured_at"] = run_ts_utc
            base["reason"] = signal_error or "no_signal: window closed with no fire"
        return base

    base["direction"] = signal.direction
    base["signal_fired_at"] = signal.fired_at.astimezone(UTC).replace(tzinfo=None)
    base["signal_fired_spot"] = signal.fired_spot
    base["signal_armed"] = str(signal.armed) if signal.armed is not None else None
    base["signal_putcall_z"] = signal.putcall_z

    if already_captured:
        return None

    now_time = now_ct.time().replace(tzinfo=None)
    age = live.signal_age_seconds(signal, now_ct)
    opt_letter, base_strike, long_strike, short_strike = live.strike_geometry(
        signal.direction, signal.fired_spot
    )
    base.update({"option_type": opt_letter, "base_strike": base_strike,
                 "long_strike": long_strike, "short_strike": short_strike,
                 "expiry": trade_date.isoformat()})

    if now_time > live.ENTRY_CUTOFF_CT:
        base["would_trade"] = False
        base["reason"] = "missed: after 14:54 CT entry cutoff"
        base["captured_at"] = run_ts_utc
        return base
    if age > live.SIGNAL_MAX_AGE_SECONDS:
        base["would_trade"] = False
        base["reason"] = f"missed: signal stale before first eval (age={age:.0f}s)"
        base["captured_at"] = run_ts_utc
        return base
    if age < -30:
        # Signal timestamp in the future -- same guard xsp_flow_live's
        # choose_mode() uses. Not terminal; wait for the clock to catch up.
        return None

    quote = _quote_legs(opt_letter, long_strike, short_strike, trade_date.isoformat(), chain_fn)
    base["captured_at"] = run_ts_utc
    base["quote_ts_utc"] = run_ts_utc
    if "note" in quote:
        base["would_trade"] = False
        base["reason"] = quote["note"]
        base["long_ask"] = quote.get("long_ask")
        base["short_bid"] = quote.get("short_bid")
        return base
    long_ask, short_bid = quote["long_ask"], quote["short_bid"]
    debit = live.executable_debit(long_ask, short_bid)
    ok = live.debit_is_allowed(long_ask, short_bid)
    base["long_ask"] = long_ask
    base["short_bid"] = short_bid
    base["debit"] = debit
    base["debit_ok"] = ok
    base["would_trade"] = ok
    base["reason"] = (
        f"would enter: fresh {signal.direction} signal, debit {debit:.2f} in range"
        if ok else f"debit {debit:.2f} outside $0.01-$0.20"
    )
    return base


def record_tick(
    engine: Optional[Engine],
    now_ct: datetime,
    *,
    history_fn: Optional[Callable[[], list[dict[str, Any]]]] = None,
    chain_fn: Optional[Callable[[str], list[dict[str, Any]]]] = None,
) -> bool:
    """One paper-logging tick. Never raises -- returns False (and logs) on
    any failure, same discipline as tv_call_log.log_call."""
    if engine is None:
        return False
    if not live.within_scheduled_window(now_ct):
        return False
    history_fn = history_fn or live.fetch_history
    chain_fn = chain_fn or _default_chain_fn
    try:
        ensure_table(engine)
        existing = _fetch_existing(engine, now_ct.date())
        already_captured = bool(existing and existing.get("captured_at") is not None)
        if already_captured:
            return True
        try:
            rows = history_fn()
        except live.FlowError as exc:
            logger.warning("[xsp_paper_ledger] confirm-history fetch failed: %r", exc)
            return False
        params = _evaluate(now_ct, rows, already_captured, chain_fn)
        if params is None:
            return True
        _upsert(engine, params)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("[xsp_paper_ledger] record_tick failed: %r", exc)
        return False


def settle_pending(
    engine: Optional[Engine],
    *,
    history_fn: Optional[Callable[[], list[dict[str, Any]]]] = None,
) -> int:
    """Settle every captured would_trade=True row still missing settled_at,
    the first time its trade_date's close_spot shows up in confirm-history.
    Never raises; returns the count settled."""
    if engine is None:
        return 0
    history_fn = history_fn or live.fetch_history
    n = 0
    try:
        ensure_table(engine)
        with engine.begin() as conn:
            pending = conn.execute(text(
                f"SELECT trade_date, direction, long_strike, short_strike, debit "
                f"FROM {TABLE} WHERE would_trade = TRUE AND settled_at IS NULL"
            )).mappings().all()
        if not pending:
            return 0
        try:
            rows = history_fn()
        except live.FlowError as exc:
            logger.warning("[xsp_paper_ledger] settle_pending history fetch failed: %r", exc)
            return 0
        for row in pending:
            trade_date = row["trade_date"]
            if isinstance(trade_date, str):
                trade_date = date.fromisoformat(trade_date)
            raw = _raw_row_for_date(rows, trade_date)
            close_spot = raw.get("close_spot") if raw else None
            if close_spot is None:
                continue
            settlement_value = float(close_spot)
            payout = live.settlement_payout(
                row["direction"], settlement_value, row["long_strike"], row["short_strike"]
            )
            debit = row["debit"] or 0.0
            pnl = round(payout - debit * 100.0, 2)
            now_utc, _ = _now_utc_ct()
            with engine.begin() as conn:
                conn.execute(text(
                    f"UPDATE {TABLE} SET settlement_value = :sv, payout = :payout, "
                    f"pnl = :pnl, settled_at = :settled_at WHERE trade_date = :d"
                ), {"sv": settlement_value, "payout": payout, "pnl": pnl,
                    "settled_at": now_utc, "d": trade_date})
            n += 1
        return n
    except Exception as exc:  # noqa: BLE001
        logger.warning("[xsp_paper_ledger] settle_pending failed: %r", exc)
        return n


def export_csv(engine: Optional[Engine], out_path: str, *, days: int = 60) -> int:
    """Read-only export used by scripts/export_xsp_paper_ledger.py. Returns
    the row count written; 0 on any failure. Never raises."""
    if engine is None:
        logger.warning("[xsp_paper_ledger] export skipped: no engine")
        return 0
    import csv

    try:
        ensure_table(engine)
        with engine.begin() as conn:
            rows = conn.execute(text(
                f"SELECT * FROM {TABLE} WHERE trade_date >= CURRENT_DATE - :days "
                "ORDER BY trade_date DESC"
                if engine.dialect.name != "sqlite" else
                f"SELECT * FROM {TABLE} WHERE date(trade_date) >= date('now', '-' || :days || ' days') "
                "ORDER BY trade_date DESC"
            ), {"days": days}).mappings().all()
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            if not rows:
                return 0
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            for row in rows:
                writer.writerow(dict(row))
        return len(rows)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[xsp_paper_ledger] export failed: %r", exc)
        return 0


def _env_bool(name: str, default: bool = False) -> bool:
    import os
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _run_eval_tick() -> None:
    from .. import db
    record_tick(db.engine, datetime.now(CT))


def _run_settle_tick() -> None:
    from .. import db
    settle_pending(db.engine)


def register(scheduler: Any) -> None:
    """Register the two paper-ledger jobs. Gated only on EMBER_XSP_ENABLED
    (module off entirely means nothing to log -- a real "no scan happened",
    same carve-out tv_call_log/TVBook uses) -- deliberately never on
    EMBER_XSP_LIVE. Independent scheduler jobs: no shared lock, no shared
    state file, no dependency on the live/dry-run agent flow."""
    if not _env_bool("EMBER_XSP_ENABLED"):
        return
    scheduler.add_job(
        _run_eval_tick,
        "cron",
        day_of_week="mon-fri",
        hour="8-15",
        minute="*",
        second="20",
        timezone="America/Chicago",
        id="ember_xsp_paper_eval",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=30,
    )
    scheduler.add_job(
        _run_settle_tick,
        "cron",
        day_of_week="mon-fri",
        hour=8,
        minute=35,
        timezone="America/Chicago",
        id="ember_xsp_paper_settle",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=120,
    )
    logger.info("[xsp_paper_ledger] registered paper-only XSP evaluation + settlement jobs")
