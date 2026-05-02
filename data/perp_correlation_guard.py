"""
Correlation cap for the AGAPE alt-perp bots (XRP, DOGE, SHIB).

The three alts have nearly identical signal structure (no Deribit GEX,
funding + L/S + OI only). When the market is broadly long-crowded, all
three will signal SHORT simultaneously. Without a guard, the bot opens
3 correlated short positions at full size — meaning a market-wide alt
squeeze hits all three at once.

This module exposes count_open_alt_positions(exclude_ticker) which lets
each alt trader check how many siblings already have open positions.
The trader's entry gate then refuses new opens beyond a cap.

Default cap: 2 simultaneous alt positions. The third alt waits.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

ALT_TICKERS = ("XRP", "DOGE", "SHIB")
DEFAULT_MAX_SIMULTANEOUS_ALTS = 2


def _count_for(ticker: str) -> int:
    """Count open positions for one alt ticker. Returns 0 on any failure."""
    ticker = ticker.upper()
    try:
        if ticker == "XRP":
            from trading.agape_xrp_perp.db import AgapeXrpPerpDatabase as DB
        elif ticker == "DOGE":
            from trading.agape_doge_perp.db import AgapeDogePerpDatabase as DB
        elif ticker == "SHIB":
            from trading.agape_shib_perp.db import AgapeShibPerpDatabase as DB
        else:
            return 0
        db = DB()
        open_pos = db.get_open_positions() or []
        return len(open_pos)
    except Exception as e:
        # Fail open: if we can't read sibling state, don't block trading
        logger.debug(f"perp_correlation_guard: count for {ticker} failed: {e}")
        return 0


def count_open_alt_positions(exclude_ticker: Optional[str] = None) -> int:
    """Total open positions across XRP+DOGE+SHIB perp bots.

    Pass exclude_ticker to skip the caller's own count (caller usually
    wants to know how many SIBLINGS are open, not including itself).
    """
    excl = (exclude_ticker or "").upper()
    return sum(_count_for(t) for t in ALT_TICKERS if t != excl)


def is_alt_correlation_capped(
    self_ticker: str,
    cap: int = DEFAULT_MAX_SIMULTANEOUS_ALTS,
) -> bool:
    """True if opening a new position on `self_ticker` would breach the cap.

    cap=2 means: if 2 sibling alts already have positions, this bot waits.
    The bot's own current open positions don't count (we're asking
    "should this bot OPEN one more?", not "is this bot at risk?").
    """
    siblings_open = count_open_alt_positions(exclude_ticker=self_ticker)
    return siblings_open >= cap
