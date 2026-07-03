"""Trigger T2 -- Long call 5x of cost.

Master spec section 4 trigger 2:
    "Long call 5x of cost -- Close entire position"

Fires when current long-call mid >= 5x entry cost. Closes everything
(both call leg and put spread) -- the call has run far enough that
holding the spread for theta no longer justifies the risk of giving
back the call's gain.

T1 (3x close-call-only) and T2 (5x close-everything) are evaluated
as separate triggers; the management engine prefers T2 over T1 when
both fire simultaneously (i.e. call has rocketed straight to 5x+
without an intermediate management cycle).
"""
from __future__ import annotations

from typing import Optional

from ..state import ManagementAction, Position

CALL_HARD_PROFIT_MULTIPLIER = 5.0


def evaluate(position: Position) -> Optional[ManagementAction]:
    """Return ManagementAction if call leg is at >= 5x entry cost, else None."""
    entry_cost = position.entry_long_call_cost
    if entry_cost <= 0:
        return None

    current = position.current_long_call_mid
    multiple = current / entry_cost

    if multiple < CALL_HARD_PROFIT_MULTIPLIER:
        return None

    return ManagementAction(
        trigger_id="T2",
        close_call=True,
        close_put_spread=True,
        reason=(
            f"Long call at {multiple:.2f}x entry "
            f"(current {current:.4f} vs entry {entry_cost:.4f}); "
            "close entire position"
        ),
        context={
            "entry_long_call_cost": entry_cost,
            "current_long_call_mid": current,
            "multiple": multiple,
            "threshold_multiple": CALL_HARD_PROFIT_MULTIPLIER,
        },
    )
