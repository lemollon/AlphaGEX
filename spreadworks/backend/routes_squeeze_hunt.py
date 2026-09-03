"""SQUEEZE HUNT — small-cap float-velocity short-squeeze surface.

Read-only window into the standalone squeeze research pipeline. This is NOT
the dealer gamma-regime "squeeze" signal that lives on the live `/squeeze`
page (bots/gamma_regime.py) — different population, different math, do not
conflate the two. `sw_squeeze_ledger` belongs to THAT signal; the tables here
are all `sw_hunt_*`.

Endpoints
---------
GET  /api/spreadworks/squeeze-hunt/signals   Today's alert-like symbols
GET  /api/spreadworks/squeeze-hunt/tape      Intraday dollar-vol pace by sweep
GET  /api/spreadworks/squeeze-hunt/lottery   Confirmed lottery-setup entries, last N days

Data source: the app's own Postgres, tables `sw_hunt_signals`,
`sw_hunt_tape`, `sw_hunt_lottery`, `sw_hunt_si`, `sw_hunt_running`. These are
a one-way display mirror of the research warehouse's DuckDB, pushed after
every sweep by `research/sync_to_postgres.py` in the squeeze repo. DuckDB
stays the source of truth; nothing on this page writes back to it.

`sw_hunt_running` holds the names the 30-day dedupe already hid from `signals` —
still over the V1/V2 line today, but first seen on an earlier day — so
`/signals` reports them separately instead of dropping them.

(The original version of this file read the DuckDB file directly off a local
Windows path, which does not exist on the deploy host — so the page rendered
empty in production. Hence the mirror.)
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from .db import engine

logger = logging.getLogger("spreadworks")

router = APIRouter(prefix="/api/spreadworks/squeeze-hunt", tags=["SqueezeHunt"])

_STATE_LABELS = {
    "feeding": "STILL FEEDING",
    "drying": "DRYING UP",
    "halted": "HALTED",
}


def _query(sql: str) -> list[tuple]:
    """Run one read-only query against the app Postgres and return raw rows."""
    if engine is None:
        raise RuntimeError("DATABASE_URL not configured")
    with engine.connect() as conn:
        return [tuple(r) for r in conn.execute(text(sql)).fetchall()]


def _money_state(state: str | None, day_kind: str | None) -> str:
    if state and state in _STATE_LABELS:
        return _STATE_LABELS[state]
    if day_kind and "BOUNCE" in day_kind.upper():
        return "BOUNCE"
    return "—"  # em dash — no read yet


def _business_days_inclusive(start, end) -> int | None:
    """Weekday count from `start` to `end`, both included — no market-holiday
    calendar here, just Mon-Fri, matching how "day N" is meant to read on the
    page (first fired 9/1, still running 9/2 -> day 2)."""
    if not start or not end or start > end:
        return None
    n, d = 0, start
    while d <= end:
        if d.weekday() < 5:
            n += 1
        d += timedelta(days=1)
    return n


@router.get("/signals")
def squeeze_hunt_signals() -> dict[str, Any]:
    """Today's alert-like symbols, one row per symbol (latest snapshot),
    sorted by dollars traded descending. Badges symbols with a same-day
    `sw_hunt_lottery` entry as LOTTERY SETUP."""
    try:
        sig_rows = _query(
            """
            SELECT DISTINCT ON (symbol)
                symbol, signal_ts, price, day_chg, dollar_vol, dollar_x,
                turnover, spread_pct, off_day_high, day_kind, run_days, hot_days
            FROM sw_hunt_signals
            WHERE signal_date = (SELECT MAX(signal_date) FROM sw_hunt_signals)
            ORDER BY symbol, signal_ts DESC
            """
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("[squeeze-hunt] signals query failed: %r", exc)
        raise HTTPException(status_code=503, detail=f"squeeze mirror unreachable: {exc!r}")

    # Latest tape state per symbol, today only.
    try:
        tape_rows = _query(
            """
            SELECT DISTINCT ON (symbol) symbol, state
            FROM sw_hunt_tape
            WHERE trade_date = (SELECT MAX(trade_date) FROM sw_hunt_tape)
            ORDER BY symbol, ts DESC
            """
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[squeeze-hunt] tape state query failed: %r", exc)
        tape_rows = []
    state_by_symbol = {r[0]: r[1] for r in tape_rows}

    # Same-day lottery badge (empty until a name actually fires — this is a
    # confirmation flag, never the SI source).
    try:
        lottery_rows = _query(
            """
            SELECT symbol
            FROM sw_hunt_lottery
            WHERE entry_date = (SELECT MAX(entry_date) FROM sw_hunt_lottery)
            """
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[squeeze-hunt] lottery query failed: %r", exc)
        lottery_rows = []
    lottery_symbols = {r[0] for r in lottery_rows}

    # Short interest % — from FINRA settlement data, NOT from the lottery
    # table. SI is one of the INPUTS to a lottery setup decision, so sourcing
    # it there would be circular: every non-lottery name would show null SI
    # forever. `sw_hunt_si` is populated independently of anything else here.
    si_settlement_date = None
    si_by_symbol: dict[str, float] = {}
    try:
        si_rows = _query(
            "SELECT symbol, si_pct, settlement_date FROM sw_hunt_si"
        )
        si_by_symbol = {r[0]: r[1] for r in si_rows}
        if si_rows:
            si_settlement_date = si_rows[0][2].isoformat()
    except Exception as exc:  # noqa: BLE001
        logger.warning("[squeeze-hunt] si query failed: %r", exc)

    signals = []
    for (symbol, signal_ts, price, day_chg, dollar_vol, dollar_x, turnover,
         spread_pct, off_day_high, day_kind, run_days, hot_days) in sig_rows:
        si_pct = si_by_symbol.get(symbol)
        # PREREG #2 cut: sub-$5 AND short interest 10-20%, evaluated on
        # today's own numbers — independent of whether the lottery table has
        # confirmed it yet (that table stays empty until 9/1).
        prereg_cut = (
            si_pct is not None and price is not None
            and price <= 5.0 and 10.0 <= si_pct <= 20.0
        )
        signals.append({
            "symbol": symbol,
            "signal_ts": signal_ts.isoformat() if signal_ts else None,
            "price": price,
            "day_chg_pct": (day_chg * 100.0) if day_chg is not None else None,
            "dollar_vol": dollar_vol,
            "dollar_x": dollar_x,
            "float_turnover": turnover,
            "short_interest_pct": si_pct,
            "si_settlement_date": si_settlement_date,
            "money_state": _money_state(state_by_symbol.get(symbol), day_kind),
            "spread_pct": spread_pct,
            "off_day_high_pct": (off_day_high * 100.0) if off_day_high is not None else None,
            "day_kind": day_kind,
            "run_days": run_days,
            "hot_days": hot_days,
            "lottery_setup": symbol in lottery_symbols,
            "prereg_cut": prereg_cut,
        })

    signals.sort(key=lambda s: s["dollar_vol"] or 0.0, reverse=True)

    # Still running: names the 30-day dedupe hid from `signals` above because
    # they already fired within the last 30 days, but still clear the V1/V2
    # line on the latest sweep. `sw_hunt_running` does not exist until the
    # squeeze repo's sync has written it once, so a missing table must read
    # as empty, not a 500.
    signal_symbols = {s["symbol"] for s in signals}
    try:
        run_rows = _query(
            """
            SELECT symbol, trade_date, variant, price, day_chg, turnover,
                   volx, dollar_vol, first_signal_date
            FROM sw_hunt_running
            WHERE trade_date = (SELECT MAX(trade_date) FROM sw_hunt_running)
              AND ts = (
                SELECT MAX(ts) FROM sw_hunt_running
                WHERE trade_date = (SELECT MAX(trade_date) FROM sw_hunt_running)
              )
            """
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[squeeze-hunt] running query failed "
                       "(table may not exist yet): %r", exc)
        run_rows = []

    # One row per symbol — prefer the V1 read over V2 when both fired on the
    # same sweep, matching how the signal list itself treats the two tiers.
    best: dict[str, tuple] = {}
    for row in run_rows:
        symbol, variant = row[0], row[2]
        if symbol in signal_symbols:
            continue
        prev = best.get(symbol)
        if prev is None or (prev[2] == "V2" and variant == "V1"):
            best[symbol] = row

    running = []
    for (symbol, trade_date, variant, price, day_chg, turnover, volx,
         dollar_vol, first_signal_date) in best.values():
        running.append({
            "symbol": symbol,
            "price": price,
            "day_chg_pct": (day_chg * 100.0) if day_chg is not None else None,
            "turnover": turnover,
            "volx": volx,
            "dollar_vol": dollar_vol,
            "first_signal_date": first_signal_date.isoformat() if first_signal_date else None,
            "run_days": _business_days_inclusive(first_signal_date, trade_date),
            "money_state": _money_state(state_by_symbol.get(symbol), None),
            "short_interest_pct": si_by_symbol.get(symbol),
        })
    running.sort(key=lambda r: r["dollar_vol"] or 0.0, reverse=True)

    return {"signals": signals, "count": len(signals), "si_settlement_date": si_settlement_date,
            "running": running, "running_count": len(running)}


@router.get("/tape")
def squeeze_hunt_tape() -> dict[str, Any]:
    """Today's intraday tape grouped by symbol, one point per sweep, so the
    page can render a money-pace sparkline (dollars arriving vs drying)."""
    try:
        rows = _query(
            """
            SELECT symbol, sweep, ts, price, day_chg, dollar_vol, state
            FROM sw_hunt_tape
            WHERE trade_date = (SELECT MAX(trade_date) FROM sw_hunt_tape)
            ORDER BY symbol, ts ASC
            """
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("[squeeze-hunt] tape query failed: %r", exc)
        raise HTTPException(status_code=503, detail=f"squeeze mirror unreachable: {exc!r}")

    by_symbol: dict[str, list[dict[str, Any]]] = {}
    for symbol, sweep, ts, price, day_chg, dollar_vol, state in rows:
        by_symbol.setdefault(symbol, []).append({
            "sweep": sweep,
            "ts": ts.isoformat() if ts else None,
            "price": price,
            "day_chg_pct": (day_chg * 100.0) if day_chg is not None else None,
            "dollar_vol": dollar_vol,
            "state": state,
        })

    return {"symbols": by_symbol, "count": len(by_symbol)}


@router.get("/lottery")
def squeeze_hunt_lottery(days: int = 7) -> dict[str, Any]:
    """Confirmed lottery-setup entries from the last `days` days, newest
    first. Read-only mirror of `sw_hunt_lottery` — a devbox bot consumes this
    payload, so the JSON keys are a fixed contract, not cosmetic."""
    days = max(1, min(60, days))
    try:
        rows = _query(
            f"""
            SELECT symbol, entry_ts, entry_date, entry_px, day_chg, si_pct, dollar_vol, sweep
            FROM sw_hunt_lottery
            WHERE entry_date >= CURRENT_DATE - {days}
            ORDER BY entry_date DESC, entry_ts DESC
            """
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("[squeeze-hunt] lottery query failed: %r", exc)
        raise HTTPException(status_code=503, detail=f"squeeze mirror unreachable: {exc!r}")

    out = []
    for symbol, entry_ts, entry_date, entry_px, day_chg, si_pct, dollar_vol, sweep in rows:
        out.append({
            "symbol": symbol,
            "entry_ts": entry_ts.isoformat() if entry_ts else None,
            "entry_date": entry_date.isoformat() if entry_date else None,
            "entry_px": entry_px,
            "day_chg": day_chg,
            "si_pct": si_pct,
            "dollar_vol": dollar_vol,
            "sweep": sweep,
        })

    return {"rows": out, "count": len(out), "days": days}
