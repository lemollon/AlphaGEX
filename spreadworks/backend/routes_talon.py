"""TALON — PAPER-ONLY $500 small-cap squeeze stock bot.

Read-only window into the standalone squeeze research pipeline's TALON
paper trader (`research/talon_paper_trader.py` in the squeeze repo). NOT a
live bot and never arms real capital from this route or any route in this
file — TALON only ever trades on paper, and every row it writes carries
`account_type='paper'`.

Reuses the SAME one-way-mirror pattern as `routes_squeeze_hunt.py`:
DuckDB (`squeeze.duckdb`, this workstation only) is the source of truth,
`research/sync_to_postgres.py` pushes a display copy into this app's own
Postgres after every TALON entry/exit run, and this route only ever reads
that Postgres copy. Nothing here writes back to DuckDB, and nothing here
can place an order — nothing in this file imports a broker client.

Endpoints
---------
GET  /api/spreadworks/talon/status     Account balance, total P&L, win rate
GET  /api/spreadworks/talon/positions  Open paper positions
GET  /api/spreadworks/talon/trades     Closed paper trades, newest first
GET  /api/spreadworks/talon/equity-curve  Equity snapshot series for the chart

Data source: `sw_talon_account`, `sw_talon_positions`, `sw_talon_equity` —
pushed by the squeeze repo's `sync_to_postgres.py`, same mirror job that
already feeds `sw_hunt_*`.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from .db import engine

logger = logging.getLogger("spreadworks")

router = APIRouter(prefix="/api/spreadworks/talon", tags=["Talon"])

STARTING_BALANCE_FALLBACK = 500.0


def _query(sql: str) -> list[tuple]:
    """Run one read-only query against the app Postgres and return raw rows."""
    if engine is None:
        raise RuntimeError("DATABASE_URL not configured")
    with engine.connect() as conn:
        return [tuple(r) for r in conn.execute(text(sql)).fetchall()]


@router.get("/status")
def talon_status() -> dict[str, Any]:
    """Account balance + simple performance stats, computed off the closed
    paper trades mirror (never the DuckDB file — this route cannot see it)."""
    try:
        acct_rows = _query(
            "SELECT starting_balance, current_balance, updated_at FROM sw_talon_account "
            "WHERE account_id = 1"
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("[talon] account query failed: %r", exc)
        raise HTTPException(status_code=503, detail=f"talon mirror unreachable: {exc!r}")

    if not acct_rows:
        # No sync has ever run / no account row yet — read as "not started",
        # not an error. The $500 paper balance is the frozen starting point
        # until the mirror reports otherwise.
        return {
            "paper_only": True,
            "starting_balance": STARTING_BALANCE_FALLBACK,
            "current_balance": STARTING_BALANCE_FALLBACK,
            "total_pnl": 0.0,
            "total_pnl_pct": 0.0,
            "open_positions": 0,
            "closed_trades": 0,
            "wins": 0,
            "win_rate": None,
            "updated_at": None,
        }

    starting_balance, current_balance, updated_at = acct_rows[0]
    starting_balance = float(starting_balance)
    current_balance = float(current_balance)

    try:
        open_rows = _query(
            "SELECT COUNT(*) FROM sw_talon_positions WHERE status = 'open'"
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[talon] open-position count failed: %r", exc)
        open_rows = [(0,)]
    open_positions = int(open_rows[0][0] or 0)

    try:
        perf_rows = _query(
            "SELECT COUNT(*) AS n, "
            "SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) AS wins "
            "FROM sw_talon_positions WHERE status = 'closed'"
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[talon] performance query failed: %r", exc)
        perf_rows = [(0, 0)]
    n, wins = perf_rows[0]
    n = int(n or 0)
    wins = int(wins or 0)

    total_pnl = current_balance - starting_balance
    return {
        "paper_only": True,
        "starting_balance": starting_balance,
        "current_balance": current_balance,
        "total_pnl": total_pnl,
        "total_pnl_pct": (total_pnl / starting_balance) if starting_balance else None,
        "open_positions": open_positions,
        "closed_trades": n,
        "wins": wins,
        "win_rate": (wins / n) if n else None,
        "updated_at": updated_at.isoformat() if updated_at else None,
    }


@router.get("/positions")
def talon_positions() -> dict[str, Any]:
    """Open paper positions, newest entry first."""
    try:
        rows = _query(
            "SELECT position_id, symbol, signal_date, entry_ts, entry_ask, "
            "position_size_usd, shares, account_type "
            "FROM sw_talon_positions WHERE status = 'open' "
            "ORDER BY entry_ts DESC"
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("[talon] positions query failed: %r", exc)
        raise HTTPException(status_code=503, detail=f"talon mirror unreachable: {exc!r}")

    out = []
    for (position_id, symbol, signal_date, entry_ts, entry_ask,
         position_size_usd, shares, account_type) in rows:
        out.append({
            "position_id": position_id,
            "symbol": symbol,
            "signal_date": signal_date.isoformat() if signal_date else None,
            "entry_ts": entry_ts.isoformat() if entry_ts else None,
            "entry_ask": entry_ask,
            "position_size_usd": position_size_usd,
            "shares": shares,
            "account_type": account_type,
        })

    return {"positions": out, "count": len(out)}


@router.get("/trades")
def talon_trades(limit: int = 100) -> dict[str, Any]:
    """Closed paper trades, newest exit first."""
    limit = max(1, min(500, limit))
    try:
        rows = _query(
            "SELECT position_id, symbol, signal_date, entry_ts, entry_ask, "
            "exit_ts, exit_price, exit_reason, realized_pnl, position_size_usd, "
            "shares, account_type "
            "FROM sw_talon_positions WHERE status = 'closed' "
            f"ORDER BY exit_ts DESC LIMIT {limit}"
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("[talon] trades query failed: %r", exc)
        raise HTTPException(status_code=503, detail=f"talon mirror unreachable: {exc!r}")

    out = []
    for (position_id, symbol, signal_date, entry_ts, entry_ask, exit_ts,
         exit_price, exit_reason, realized_pnl, position_size_usd, shares,
         account_type) in rows:
        out.append({
            "position_id": position_id,
            "symbol": symbol,
            "signal_date": signal_date.isoformat() if signal_date else None,
            "entry_ts": entry_ts.isoformat() if entry_ts else None,
            "entry_ask": entry_ask,
            "exit_ts": exit_ts.isoformat() if exit_ts else None,
            "exit_price": exit_price,
            "exit_reason": exit_reason,
            "realized_pnl": realized_pnl,
            "position_size_usd": position_size_usd,
            "shares": shares,
            "account_type": account_type,
        })

    return {"trades": out, "count": len(out)}


@router.get("/equity-curve")
def talon_equity_curve() -> dict[str, Any]:
    """Equity snapshot series for the chart — a step function at each
    entry/exit checkpoint, not a smooth intraday mark (TALON does not poll
    quotes continuously — see talon_paper_trader.py's EQUITY CONVENTION
    note). Capped at 2000 most-recent points so an old, never-pruned series
    cannot bloat the response."""
    try:
        rows = _query(
            "SELECT snapshot_ts, equity FROM sw_talon_equity "
            "ORDER BY snapshot_ts DESC LIMIT 2000"
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("[talon] equity-curve query failed: %r", exc)
        raise HTTPException(status_code=503, detail=f"talon mirror unreachable: {exc!r}")

    rows = list(reversed(rows))  # oldest first for the chart
    curve = [{"time": ts.isoformat() if ts else None, "equity": eq} for ts, eq in rows]
    return {"curve": curve, "count": len(curve)}
