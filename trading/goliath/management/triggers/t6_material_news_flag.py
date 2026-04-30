"""Trigger T6 -- Material news flag set on the underlying.

Master spec section 4 trigger 6 + Leron Q5 (2026-04-29):
    "Material news mid-trade -- Close everything (manual flag for v0.2,
     not auto-detected). CLI command on Render shell sets the flag."

The trigger reads goliath_news_flags via news_flag_store.is_ticker_flagged.
Flag is keyed on the *underlying* ticker (TSLA news -> close TSLL position).
For unit testability, the lookup is dependency-injected.
"""
from __future__ import annotations

from typing import Callable, Optional

from ..state import ManagementAction, Position


def evaluate(
    position: Position,
    is_flagged: Optional[Callable[[str], bool]] = None,
) -> Optional[ManagementAction]:
    """Fire when underlying_ticker has an active news flag."""
    if is_flagged is None:
        from ..news_flag_store import is_ticker_flagged
        is_flagged = is_ticker_flagged

    if not is_flagged(position.underlying_ticker):
        return None

    return ManagementAction(
        trigger_id="T6",
        close_call=True,
        close_put_spread=True,
        reason=(
            f"Material news flag active on {position.underlying_ticker}; "
            "close entire position"
        ),
        context={
            "underlying_ticker": position.underlying_ticker,
            "letf_ticker": position.letf_ticker,
        },
    )
