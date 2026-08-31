"""SQUEEZE HUNT — small-cap float-velocity short-squeeze surface.

Read-only window into the standalone squeeze research pipeline's DuckDB
warehouse. This is NOT the dealer gamma-regime "squeeze" signal that lives
on the live `/squeeze` page (bots/gamma_regime.py) — different population,
different math, do not conflate the two.

Endpoints
---------
GET  /api/spreadworks/squeeze-hunt/signals   Today's alert-like symbols
GET  /api/spreadworks/squeeze-hunt/tape      Intraday dollar-vol pace by sweep

Data source: C:\\Users\\lemol\\dev\\squeeze\\squeeze.duckdb (override via
SQUEEZE_DUCKDB_PATH). A scheduled job holds the single-writer lock on this
file, so every connection here is opened `read_only=True` and closed
immediately after the query — never held open, never opened for write.
"""
from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import APIRouter, HTTPException

logger = logging.getLogger("spreadworks")

router = APIRouter(prefix="/api/spreadworks/squeeze-hunt", tags=["SqueezeHunt"])

_DEFAULT_DB_PATH = r"C:\Users\lemol\dev\squeeze\squeeze.duckdb"
DB_PATH = os.getenv("SQUEEZE_DUCKDB_PATH", _DEFAULT_DB_PATH)

_STATE_LABELS = {
    "feeding": "STILL FEEDING",
    "drying": "DRYING UP",
    "halted": "HALTED",
}


def _query(sql: str, params: tuple = ()) -> list[tuple]:
    """Open a fresh read-only DuckDB connection, run one query, close it.

    Never opens for write — the nightly ingest job holds the single writer
    lock on this file, and a write-mode connect would crash it. Returns an
    empty list (never raises) so a missing/locked file degrades the page
    instead of 500ing it; the route wraps this and surfaces a clear error
    only when the file is entirely unreachable.
    """
    import duckdb

    con = duckdb.connect(DB_PATH, read_only=True)
    try:
        return con.execute(sql, params).fetchall()
    finally:
        con.close()


def _money_state(state: str | None, day_kind: str | None) -> str:
    if state and state in _STATE_LABELS:
        return _STATE_LABELS[state]
    if day_kind and "BOUNCE" in day_kind.upper():
        return "BOUNCE"
    return "\u2014"  # em dash — no read yet


@router.get("/signals")
def squeeze_hunt_signals() -> dict[str, Any]:
    """Today's alert-like symbols, one row per symbol (latest snapshot),
    sorted by dollars traded descending. Badges symbols with a same-day
    `lottery_ledger` entry as LOTTERY SETUP."""
    try:
        sig_rows = _query(
            """
            SELECT DISTINCT ON (symbol)
                symbol, signal_ts, price, day_chg, dollar_vol, dollar_x,
                turnover, spread_pct, off_day_high, day_kind, run_days, hot_days
            FROM forward_signals_intraday
            WHERE signal_date = (SELECT MAX(signal_date) FROM forward_signals_intraday)
            ORDER BY symbol, signal_ts DESC
            """
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("[squeeze-hunt] signals query failed: %r", exc)
        raise HTTPException(status_code=503, detail=f"squeeze warehouse unreachable: {exc!r}")

    # Latest intraday_tape state per symbol, today only.
    try:
        tape_rows = _query(
            """
            SELECT DISTINCT ON (symbol) symbol, state
            FROM intraday_tape
            WHERE trade_date = (SELECT MAX(trade_date) FROM intraday_tape)
            ORDER BY symbol, ts DESC
            """
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[squeeze-hunt] tape state query failed: %r", exc)
        tape_rows = []
    state_by_symbol = {r[0]: r[1] for r in tape_rows}

    # Same-day lottery badge from lottery_ledger (empty until a name actually
    # fires — this is a confirmation flag, never the SI source).
    try:
        lottery_rows = _query(
            """
            SELECT symbol
            FROM lottery_ledger
            WHERE entry_date = (SELECT MAX(entry_date) FROM lottery_ledger)
            """
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[squeeze-hunt] lottery query failed: %r", exc)
        lottery_rows = []
    lottery_symbols = {r[0] for r in lottery_rows}

    # Short interest % — sourced from FINRA settlement data (finra_si), NOT
    # lottery_ledger. SI is one of the INPUTS to a lottery setup decision,
    # so joining it from lottery_ledger would be circular: every non-lottery
    # name would show null SI forever. finra_si is fully populated
    # (22,482 symbols) independent of anything else on this page.
    si_settlement_date = None
    si_by_symbol: dict[str, float] = {}
    try:
        si_rows = _query(
            """
            SELECT f.symbol, 100.0 * f.short_shares / s.shares AS si_pct,
                   f.settlement_date
            FROM finra_si f
            JOIN (SELECT ticker, shares FROM shares_outstanding
                  QUALIFY row_number() OVER (PARTITION BY ticker ORDER BY as_of DESC) = 1) s
              ON s.ticker = f.symbol
            WHERE f.settlement_date = (SELECT max(settlement_date) FROM finra_si)
            """
        )
        si_by_symbol = {r[0]: r[1] for r in si_rows}
        if si_rows:
            si_settlement_date = si_rows[0][2].isoformat()
    except Exception as exc:  # noqa: BLE001
        logger.warning("[squeeze-hunt] finra_si query failed: %r", exc)

    signals = []
    for (symbol, signal_ts, price, day_chg, dollar_vol, dollar_x, turnover,
         spread_pct, off_day_high, day_kind, run_days, hot_days) in sig_rows:
        si_pct = si_by_symbol.get(symbol)
        # PREREG #2 cut: sub-$5 AND short interest 10-20%, evaluated on
        # today's own numbers — independent of whether lottery_ledger has
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
    return {"signals": signals, "count": len(signals), "si_settlement_date": si_settlement_date}


@router.get("/tape")
def squeeze_hunt_tape() -> dict[str, Any]:
    """Today's intraday tape grouped by symbol, one point per sweep, so the
    page can render a money-pace sparkline (dollars arriving vs drying)."""
    try:
        rows = _query(
            """
            SELECT symbol, sweep, ts, price, day_chg, dollar_vol, state
            FROM intraday_tape
            WHERE trade_date = (SELECT MAX(trade_date) FROM intraday_tape)
            ORDER BY symbol, ts ASC
            """
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("[squeeze-hunt] tape query failed: %r", exc)
        raise HTTPException(status_code=503, detail=f"squeeze warehouse unreachable: {exc!r}")

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
