"""Trigger T8 -- Underlying GEX flip occurred mid-trade.

Master spec section 4 trigger 8:
    "Underlying GEX flip occurred mid-trade -- Re-evaluate; close if
     regime now adverse"

A "flip" means the underlying GEX regime changed since entry. The
trigger fires only on adverse flips:
    POSITIVE -> NEGATIVE  (or NEUTRAL -> NEGATIVE) -- adverse for a
    bullish put-credit-spread + long-call structure since dealer
    hedging now amplifies moves rather than dampens them.

A flip POSITIVE -> NEUTRAL is treated as a soft transition; it does
not fire on its own (T4 / T5 / T8 with full flip will catch it
later if it deteriorates further).
"""
from __future__ import annotations

from typing import Optional

from ..state import ManagementAction, Position

# Adverse transitions per spec: any move into NEGATIVE regime is
# adverse for the long-biased GOLIATH structure.
_ADVERSE_NEW_REGIMES = {"NEGATIVE"}
# Origins from which an adverse flip is meaningful (skip "we entered
# already in NEGATIVE" -- that would have been a G02 fail).
_NON_NEGATIVE_ORIGINS = {"POSITIVE", "NEUTRAL"}


def evaluate(position: Position) -> Optional[ManagementAction]:
    """Fire when entry regime was non-negative AND current is NEGATIVE."""
    entry = position.entry_underlying_gex_regime
    current = position.current_underlying_gex_regime

    if entry == current:
        return None
    if entry not in _NON_NEGATIVE_ORIGINS:
        return None
    if current not in _ADVERSE_NEW_REGIMES:
        return None

    return ManagementAction(
        trigger_id="T8",
        close_call=True,
        close_put_spread=True,
        reason=(
            f"Underlying {position.underlying_ticker} GEX regime flipped "
            f"{entry} -> {current} mid-trade; close entire position"
        ),
        context={
            "underlying_ticker": position.underlying_ticker,
            "entry_underlying_gex_regime": entry,
            "current_underlying_gex_regime": current,
        },
    )
