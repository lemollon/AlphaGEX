"""Wall Scanner API: /api/spreadworks/wall-scanner

DESCRIPTIVE ONLY — $ to break, $ gap, % gap to the nearest call/put GEX wall
for GME + the 7 tickers flow-mix continuation was tested (and failed) on.
NO directional fade/breakout call anywhere in this surface, by design: see
`backend/bots/wall_scanner.py` module docstring and memory
`flowmix-singlename-fails.md`. This is not re-litigated here.

GME ships in the ticker list even though it was never itself backtested —
it inherits descriptive-only by default like every ticker on this page.

Read-only; import-guarded in `backend/__init__.py` like the other advisory
surfaces (Squeeze, Risk, Book Risk) so a TradingVolatility outage never
takes down the API.
"""
from __future__ import annotations

from fastapi import APIRouter

from .bots.wall_scanner import TICKERS, scan_all

router = APIRouter(prefix="/api/spreadworks/wall-scanner", tags=["Wall Scanner"])


@router.get("")
async def get_wall_scanner():
    return {
        "tickers": TICKERS,
        "data": scan_all(),
        "descriptive_only": True,
    }


@router.get("/{ticker}")
async def get_wall_scanner_ticker(ticker: str):
    from .bots.wall_scanner import scan_ticker

    return {"data": scan_ticker(ticker.upper()), "descriptive_only": True}
