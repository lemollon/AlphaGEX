"""PAPER-ONLY forward call log for EMBER's TVBook (RR + BOUNCE) scanner.

WHY THIS EXISTS
----------------
TVBook's long/short call comes from TradingVolatility's own proprietary
`recommended_direction` / `trade_bias` fields -- a black box with no history
of its own. Nobody can score "was TV's call right" without a record of what
TV actually said, when it said it, and whether our RR/BOUNCE geometry would
have turned it into a setup. This module is that record: a point-in-time
snapshot, written every time the scanner runs, independent of whether EMBER
is armed to trade.

🚨 LOGGING NEVER DEPENDS ON ARMING. `tv_scanner.py` (the flat script
`fleet_runtime._run_tv_scanner()` subprocess-runs) has no live/dry-run branch
of its own -- it never places an order, it only writes the ledger and prints
tables. `fleet_runtime._run()` calls `_run_tv_scanner()` before it forces
`cfg.armed`/`cfg.dry_run` from `EMBER_TVBOOK_LIVE`, so a call to this module
from inside the scanner fires on every scheduled tick as long as
`EMBER_TVBOOK_ENABLED=1` -- `EMBER_TVBOOK_LIVE=0` (paper/unarmed) does not
skip it. If TVBOOK is fully disabled (`EMBER_TVBOOK_ENABLED=0`) the whole
job is never scheduled and there is nothing to log -- that is a real "no
scan happened", not a logging gap.

NO ORDERS, NO BROKER LOCK. This module only opens its own short-lived
Postgres transaction (via the `engine` the caller passes in, same one
`squeeze_ledger.py` uses) -- it never touches `ember_lock`, the
`ember-fleet:*` / `agent-runtime` advisory locks, or any broker client.

TWO ROW FLAVORS, ONE TABLE, keyed IDEMPOTENT on (run_id, endpoint, ticker):
  - source rows: one per TV list item, `endpoint` = "top-setups", each of
    the 7 screener preset names, or "income-setups" -- exactly the raw item
    TV returned for that ticker on that list, `rank` = its position in that
    list's own response order. Written by `log_source_items()`, called right
    after the scanner fetches each list (no extra TV calls -- these are the
    items the scan already pulled).
  - evaluation rows: two per candidate ticker, `endpoint` = "rr_eval" /
    "bounce_eval" -- whether the RR/BOUNCE geometry (section B/D/F of
    tv_scanner.py's own docstring) would have produced a >=2:1 setup off the
    SAME /tickers + curve payload the scan already fetched for that name,
    and the planned entry/stop/target/structure/strikes if so. Written by
    `log_evaluation()`, called once per candidate after `process_candidate()`
    has already computed its RR/BOUNCE rows -- again, no extra TV calls.

`raw_item_json` / `raw_context_json` keep the full TV/derived payload for a
row (every field TV returned, not just the ones broken out into columns) so
nothing is lost to a schema that didn't anticipate a field.

`run_id` is the scanner's own stable per-run token (tv_scanner.py's
`SCAN_TIME_ISO`, computed once at process start) -- re-running the exact same
scan process twice (should that ever happen) upserts the same rows instead
of duplicating them; a genuinely new run gets a new run_id and new rows.

NEVER RAISES. Every public function here is best-effort instrumentation
hanging off a scanner that has a job to do -- a logging failure prints a
line and returns False/0, it never takes the scan down with it.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from typing import Any, Iterable, Optional
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = logging.getLogger("spreadworks.ember.tv_call_log")

CT = ZoneInfo("America/Chicago")
TABLE = "ember_tv_call_log"

# TV's list source tags (tv_scanner.py's `_source`) map onto the endpoint
# names Leron asked for; screener preset names (already TV's own preset
# name, e.g. "bottoming_reversal") pass through unchanged.
_ENDPOINT_LABELS = {"idea": "top-setups", "income": "income-setups"}

_COLUMNS_SQL = """
    run_id                  TEXT NOT NULL,
    run_ts_utc               TIMESTAMP NOT NULL,
    run_ts_ct                TIMESTAMP NOT NULL,
    scan_date                DATE NOT NULL,
    endpoint                 TEXT NOT NULL,
    ticker                   TEXT NOT NULL,
    rank                     INTEGER,
    recommended_direction    TEXT,
    trade_bias               TEXT,
    opportunity_score        DOUBLE PRECISION,
    income_score             DOUBLE PRECISION,
    price                    DOUBLE PRECISION,
    flip                     DOUBLE PRECISION,
    put_wall                 DOUBLE PRECISION,
    call_wall                DOUBLE PRECISION,
    max_gamma_strike         DOUBLE PRECISION,
    dist_to_flip_pct         DOUBLE PRECISION,
    em_1d_pct                DOUBLE PRECISION,
    em_1w_pct                DOUBLE PRECISION,
    iv_rank                  DOUBLE PRECISION,
    pcr_vol                  DOUBLE PRECISION,
    pcr_oi                   DOUBLE PRECISION,
    pcr_oi_d30               DOUBLE PRECISION,
    spec_score                DOUBLE PRECISION,
    rsi14                     DOUBLE PRECISION,
    opt_oi                    DOUBLE PRECISION,
    opt_vol                   DOUBLE PRECISION,
    would_setup                BOOLEAN,
    side                       TEXT,
    entry                      DOUBLE PRECISION,
    stop                       DOUBLE PRECISION,
    target                     DOUBLE PRECISION,
    stock_rr                   DOUBLE PRECISION,
    liquid                     BOOLEAN,
    structure                  TEXT,
    contract                   TEXT,
    debit                      DOUBLE PRECISION,
    cost_usd                   DOUBLE PRECISION,
    note                       TEXT,
    raw_item_json               TEXT,
    raw_context_json            TEXT,
    created_at                  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (run_id, endpoint, ticker)
"""


def _ddl() -> str:
    """SQLite has no BIGSERIAL; a non-`INTEGER`-typed PRIMARY KEY there does
    not get the auto-rowid convenience, so every insert without an explicit
    id would fail. Postgres gets BIGSERIAL for real headroom in production."""
    return f"CREATE TABLE IF NOT EXISTS {TABLE} (\n    id BIGSERIAL PRIMARY KEY,\n{_COLUMNS_SQL}\n)"


def _ddl_sqlite() -> str:
    return f"CREATE TABLE IF NOT EXISTS {TABLE} (\n    id INTEGER PRIMARY KEY AUTOINCREMENT,\n{_COLUMNS_SQL}\n)"


def endpoint_label(source_tag: str) -> str:
    """tv_scanner.py's `_source` tag -> the endpoint name for this log
    ("idea" -> "top-setups", "income" -> "income-setups", a preset name
    passes through as-is)."""
    return _ENDPOINT_LABELS.get(source_tag, source_tag)


def ensure_table(engine: Optional[Engine]) -> None:
    """Idempotent create. Never raises -- a failure here just means the next
    write also fails and logs, same as any other best-effort path in this
    module."""
    if engine is None:
        return
    try:
        with engine.begin() as conn:
            conn.execute(text(_ddl_sqlite() if engine.dialect.name == "sqlite" else _ddl()))
    except Exception as exc:  # noqa: BLE001
        logger.warning("[tv_call_log] table create failed: %r", exc)


def _now_utc_ct() -> tuple[datetime, datetime]:
    now_utc = datetime.now(timezone.utc)
    return now_utc.replace(tzinfo=None), now_utc.astimezone(CT).replace(tzinfo=None)


def _to_date(value: Any) -> date:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            pass
    return datetime.now(CT).date()


def _jsonify(value: Any) -> Optional[str]:
    if value is None:
        return None
    try:
        return json.dumps(value, default=str)[:20000]
    except Exception:  # noqa: BLE001
        return None


_UPSERT_SQL = f"""
    INSERT INTO {TABLE} (
        run_id, run_ts_utc, run_ts_ct, scan_date, endpoint, ticker, rank,
        recommended_direction, trade_bias, opportunity_score, income_score,
        price, flip, put_wall, call_wall, max_gamma_strike, dist_to_flip_pct,
        em_1d_pct, em_1w_pct, iv_rank, pcr_vol, pcr_oi, pcr_oi_d30, spec_score,
        rsi14, opt_oi, opt_vol, would_setup, side, entry, stop, target,
        stock_rr, liquid, structure, contract, debit, cost_usd, note,
        raw_item_json, raw_context_json
    ) VALUES (
        :run_id, :run_ts_utc, :run_ts_ct, :scan_date, :endpoint, :ticker, :rank,
        :recommended_direction, :trade_bias, :opportunity_score, :income_score,
        :price, :flip, :put_wall, :call_wall, :max_gamma_strike, :dist_to_flip_pct,
        :em_1d_pct, :em_1w_pct, :iv_rank, :pcr_vol, :pcr_oi, :pcr_oi_d30, :spec_score,
        :rsi14, :opt_oi, :opt_vol, :would_setup, :side, :entry, :stop, :target,
        :stock_rr, :liquid, :structure, :contract, :debit, :cost_usd, :note,
        :raw_item_json, :raw_context_json
    )
    ON CONFLICT (run_id, endpoint, ticker) DO UPDATE SET
        rank = EXCLUDED.rank, recommended_direction = EXCLUDED.recommended_direction,
        trade_bias = EXCLUDED.trade_bias, opportunity_score = EXCLUDED.opportunity_score,
        income_score = EXCLUDED.income_score, price = EXCLUDED.price, flip = EXCLUDED.flip,
        put_wall = EXCLUDED.put_wall, call_wall = EXCLUDED.call_wall,
        max_gamma_strike = EXCLUDED.max_gamma_strike, dist_to_flip_pct = EXCLUDED.dist_to_flip_pct,
        em_1d_pct = EXCLUDED.em_1d_pct, em_1w_pct = EXCLUDED.em_1w_pct, iv_rank = EXCLUDED.iv_rank,
        pcr_vol = EXCLUDED.pcr_vol, pcr_oi = EXCLUDED.pcr_oi, pcr_oi_d30 = EXCLUDED.pcr_oi_d30,
        spec_score = EXCLUDED.spec_score, rsi14 = EXCLUDED.rsi14, opt_oi = EXCLUDED.opt_oi,
        opt_vol = EXCLUDED.opt_vol, would_setup = EXCLUDED.would_setup, side = EXCLUDED.side,
        entry = EXCLUDED.entry, stop = EXCLUDED.stop, target = EXCLUDED.target,
        stock_rr = EXCLUDED.stock_rr, liquid = EXCLUDED.liquid, structure = EXCLUDED.structure,
        contract = EXCLUDED.contract, debit = EXCLUDED.debit, cost_usd = EXCLUDED.cost_usd,
        note = EXCLUDED.note, raw_item_json = EXCLUDED.raw_item_json,
        raw_context_json = EXCLUDED.raw_context_json
"""


def log_call(engine: Optional[Engine], *, run_id: str, scan_date: Any, endpoint: str,
             ticker: str, rank: Optional[int] = None,
             recommended_direction: Optional[str] = None, trade_bias: Optional[str] = None,
             opportunity_score: Optional[float] = None, income_score: Optional[float] = None,
             context: Optional[dict] = None, would_setup: Optional[bool] = None,
             side: Optional[str] = None, entry: Optional[float] = None, stop: Optional[float] = None,
             target: Optional[float] = None, stock_rr: Optional[float] = None,
             liquid: Optional[bool] = None, structure: Optional[str] = None,
             contract: Optional[str] = None, debit: Optional[float] = None,
             cost_usd: Optional[float] = None, note: Optional[str] = None,
             raw_item: Optional[dict] = None) -> bool:
    """Write (or refresh, same run) one row. Never raises -- returns False and
    logs on any failure (missing engine, table create, insert)."""
    if engine is None or not ticker or not endpoint:
        return False
    ctx = context or {}
    run_ts_utc, run_ts_ct = _now_utc_ct()
    params = {
        "run_id": run_id, "run_ts_utc": run_ts_utc, "run_ts_ct": run_ts_ct,
        "scan_date": _to_date(scan_date), "endpoint": endpoint, "ticker": ticker,
        "rank": rank, "recommended_direction": recommended_direction, "trade_bias": trade_bias,
        "opportunity_score": opportunity_score, "income_score": income_score,
        "price": ctx.get("price"), "flip": ctx.get("flip"), "put_wall": ctx.get("put_wall"),
        "call_wall": ctx.get("call_wall"), "max_gamma_strike": ctx.get("max_gamma_strike"),
        "dist_to_flip_pct": ctx.get("dist_to_flip_pct"), "em_1d_pct": ctx.get("em_1d_pct"),
        "em_1w_pct": ctx.get("em_1w_pct"), "iv_rank": ctx.get("iv_rank"), "pcr_vol": ctx.get("pcr_vol"),
        "pcr_oi": ctx.get("pcr_oi"), "pcr_oi_d30": ctx.get("pcr_oi_d30"), "spec_score": ctx.get("spec_score"),
        "rsi14": ctx.get("rsi14"), "opt_oi": ctx.get("opt_oi"), "opt_vol": ctx.get("opt_vol"),
        "would_setup": would_setup, "side": side, "entry": entry, "stop": stop, "target": target,
        "stock_rr": stock_rr, "liquid": liquid, "structure": structure, "contract": contract,
        "debit": debit, "cost_usd": cost_usd, "note": (note or "")[:500] or None,
        "raw_item_json": _jsonify(raw_item), "raw_context_json": _jsonify(context),
    }
    try:
        ensure_table(engine)
        with engine.begin() as conn:
            conn.execute(text(_UPSERT_SQL), params)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("[tv_call_log] insert failed run=%s endpoint=%s ticker=%s: %r",
                        run_id, endpoint, ticker, exc)
        return False


def log_source_items(engine: Optional[Engine], *, run_id: str, scan_date: Any,
                      endpoint: str, items: Iterable[dict]) -> int:
    """One row per raw TV list item for this endpoint -- `rank` = the item's
    1-indexed position in the list TV actually returned. Reuses the item the
    scanner already fetched; makes no TV call of its own. Returns the number
    of rows written (0 on total failure -- never raises)."""
    n = 0
    for i, item in enumerate(items or [], start=1):
        ticker = (item or {}).get("ticker")
        if not ticker:
            continue

        def _score(key: str) -> Optional[float]:
            v = item.get(key)
            try:
                return float(v) if v is not None else None
            except (TypeError, ValueError):
                return None

        ok = log_call(
            engine, run_id=run_id, scan_date=scan_date, endpoint=endpoint, ticker=ticker,
            rank=i, recommended_direction=item.get("recommended_direction"),
            trade_bias=item.get("trade_bias"), opportunity_score=_score("opportunity_score"),
            income_score=_score("income_score"), raw_item=item,
        )
        n += int(ok)
    return n


def _row_would_setup(bucket: Optional[str], setup_buckets: tuple[str, ...]) -> bool:
    return bucket in setup_buckets


def log_evaluation(engine: Optional[Engine], *, run_id: str, scan_date: Any, ticker: str,
                    context: Optional[dict], rr_row: Optional[dict], rr_bucket: Optional[str],
                    bounce_row: Optional[dict], bounce_bucket: Optional[str],
                    nodata_reason: Optional[str] = None) -> int:
    """Two rows ("rr_eval", "bounce_eval") per candidate ticker -- whether the
    scanner's own >=2:1 RR/BOUNCE geometry produced a setup off the SAME
    /tickers + curve payload already pulled for this name, and the planned
    entry/stop/target/structure/contract if so. Written even when neither
    strategy signals (both rows still record the attempt, with `would_setup`
    False and `note` explaining why -- e.g. "no direction"). Never raises;
    returns the number of rows written."""
    n = 0
    if rr_row is not None:
        n += int(log_call(
            engine, run_id=run_id, scan_date=scan_date, endpoint="rr_eval", ticker=ticker,
            context=context, would_setup=_row_would_setup(rr_bucket, ("setups", "illiquid")),
            side=rr_row.get("dir"), entry=rr_row.get("price"), stop=rr_row.get("stop"),
            target=rr_row.get("target"), stock_rr=rr_row.get("stock_rr"), liquid=rr_row.get("liquid"),
            structure=rr_row.get("structure"), contract=rr_row.get("contract"),
            debit=rr_row.get("debit"), cost_usd=rr_row.get("cost_usd"),
            note=rr_row.get("liq_note") or rr_row.get("structure_note") or rr_row.get("note"),
            raw_item=rr_row,
        ))
    else:
        n += int(log_call(
            engine, run_id=run_id, scan_date=scan_date, endpoint="rr_eval", ticker=ticker,
            context=context, would_setup=False, note=nodata_reason or "no rr geometry",
        ))
    if bounce_row is not None:
        structure = bounce_row.get("structure")
        debit = bounce_row.get("call_debit") if structure == "call" else bounce_row.get("pcs_credit")
        cost_usd = bounce_row.get("call_cost_usd") if structure == "call" else bounce_row.get("pcs_max_loss")
        n += int(log_call(
            engine, run_id=run_id, scan_date=scan_date, endpoint="bounce_eval", ticker=ticker,
            context=context,
            would_setup=_row_would_setup(bounce_bucket, ("bounce_rows", "bounce_illiquid"))
            and bounce_row.get("tier") == "setup",
            side=bounce_row.get("dir"), entry=bounce_row.get("price"), stop=bounce_row.get("stop"),
            target=bounce_row.get("target"), stock_rr=bounce_row.get("stock_rr"),
            liquid=bounce_row.get("liquid"), structure=structure,
            contract=None, debit=debit, cost_usd=cost_usd,
            note=bounce_row.get("liq_note") or bounce_row.get("pcs_note") or bounce_row.get("call_note"),
            raw_item=bounce_row,
        ))
    else:
        n += int(log_call(
            engine, run_id=run_id, scan_date=scan_date, endpoint="bounce_eval", ticker=ticker,
            context=context, would_setup=False, note=nodata_reason or "no bounce signal",
        ))
    return n


def export_csv(engine: Optional[Engine], out_path: str, *, days: int = 30) -> int:
    """Read-only export used by scripts/export_tv_call_log.py. Returns the
    row count written; 0 (with a log line) on any failure. Never raises."""
    if engine is None:
        logger.warning("[tv_call_log] export skipped: no engine")
        return 0
    import csv

    try:
        ensure_table(engine)
        with engine.begin() as conn:
            rows = conn.execute(text(
                f"SELECT * FROM {TABLE} WHERE scan_date >= CURRENT_DATE - :days "
                "ORDER BY run_ts_utc DESC, endpoint, ticker"
                if engine.dialect.name != "sqlite" else
                f"SELECT * FROM {TABLE} WHERE date(scan_date) >= date('now', '-' || :days || ' days') "
                "ORDER BY run_ts_utc DESC, endpoint, ticker"
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
        logger.warning("[tv_call_log] export failed: %r", exc)
        return 0
