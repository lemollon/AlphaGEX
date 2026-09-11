"""Wall Scanner API: /api/spreadworks/wall-scanner

DESCRIPTIVE ONLY — $ to break, $ gap, % gap to the nearest call/put GEX wall,
scanned across TradingVolatility's covered universe (liquid, optionable
names — see `backend/bots/wall_scanner.py` module docstring for why that's
the market-wide filter, not a fixed basket). Sorted tightest-gap-first.
NO directional fade/breakout call anywhere in this surface, by design: see
memory `flowmix-singlename-fails.md`. This is not re-litigated here.

Also serves the closest wall's OI/GEX 1h delta (composed here from the
history table — see attach_history_deltas) and a full intraday+multi-day
history series per ticker for charting (`/{ticker}/history`). History only
exists from whenever the scheduled capture job (backend/__init__.py,
`wall_scanner_capture`) started running — a fresh deploy has none yet.

Read-only; import-guarded in `backend/__init__.py` like the other advisory
surfaces (Squeeze, Risk, Book Risk) so a TradingVolatility outage never
takes down the API. A full scan is a cached ~100-call pass (see
`_CACHE_TTL` in the bot module) — do not add a way to force it on every
request without a cache-bust guard.
"""
from __future__ import annotations

from fastapi import APIRouter, Query

from .bots.wall_scanner import (
    attach_history_deltas,
    scan_all,
    scan_ticker,
    wall_history_series,
)
from .db import engine as _engine

router = APIRouter(prefix="/api/spreadworks/wall-scanner", tags=["Wall Scanner"])


@router.get("")
async def get_wall_scanner():
    result = scan_all()
    data = result.get("data", [])
    attach_history_deltas(_engine, data)
    return {
        "tickers_scanned": result.get("tickers_scanned", 0),
        "data": data,
        "elapsed_sec": result.get("elapsed_sec"),
        "descriptive_only": True,
    }


@router.get("/{ticker}")
async def get_wall_scanner_ticker(ticker: str):
    row = scan_ticker(ticker.upper())
    attach_history_deltas(_engine, [row])
    return {"data": row, "descriptive_only": True}


@router.get("/{ticker}/history")
async def get_wall_scanner_history(
    ticker: str,
    side: str = Query(..., pattern="^(call|put)$"),
    strike: float = Query(...),
    days: int = Query(5, ge=1, le=30),
):
    series = wall_history_series(_engine, ticker.upper(), side, strike, days_back=days)
    return {"ticker": ticker.upper(), "side": side, "strike": strike, "days": days, "series": series}
