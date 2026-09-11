"""Wall Scanner API: /api/spreadworks/wall-scanner

DESCRIPTIVE ONLY — $ to break, $ gap, % gap to the nearest call/put GEX wall,
scanned across TradingVolatility's covered universe (liquid, optionable
names — see `backend/bots/wall_scanner.py` module docstring for why that's
the market-wide filter, not a fixed basket). Sorted tightest-gap-first.
NO directional fade/breakout call anywhere in this surface, by design: see
memory `flowmix-singlename-fails.md`. This is not re-litigated here.

Read-only; import-guarded in `backend/__init__.py` like the other advisory
surfaces (Squeeze, Risk, Book Risk) so a TradingVolatility outage never
takes down the API. A full scan is a cached ~200-ticker pass (see
`_CACHE_TTL` in the bot module) — do not add a way to force it on every
request without a cache-bust guard.
"""
from __future__ import annotations

from fastapi import APIRouter

from .bots.wall_scanner import scan_all, scan_ticker

router = APIRouter(prefix="/api/spreadworks/wall-scanner", tags=["Wall Scanner"])


@router.get("")
async def get_wall_scanner():
    result = scan_all()
    return {
        "tickers_scanned": result.get("tickers_scanned", 0),
        "data": result.get("data", []),
        "elapsed_sec": result.get("elapsed_sec"),
        "descriptive_only": True,
    }


@router.get("/{ticker}")
async def get_wall_scanner_ticker(ticker: str):
    return {"data": scan_ticker(ticker.upper()), "descriptive_only": True}
