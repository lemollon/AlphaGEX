"""Trigger T1 -- Long call 3x of cost.

Master spec section 4 trigger 1:
    "Long call 3x of cost -- Close call leg, hold put spread to expiry"

Fires when the current long-call mid >= 3 x entry_long_call_cost.
Action: close the call leg only; the put spread runs to expiration
to harvest remaining theta on the credit.

Multiplier exposed as a module constant so tests can drive both
sides of the boundary cleanly. Threshold ratio is spec-fixed; not
v0.3-tunable.
"""
from __future__ import annotations

from typing import Optional

from ..state import ManagementAction, Position

CALL_PROFIT_MULTIPLIER = 3.0


def evaluate(position: Position) -> Optional[ManagementAction]:
    """Return ManagementAction if call leg is at >= 3x entry cost, else None."""
    entry_cost = position.entry_long_call_cost
    if entry_cost <= 0:
        # Degenerate: cannot compute a multiple of zero/negative cost.
        return None

    current = position.current_long_call_mid
    multiple = current / entry_cost

    if multiple < CALL_PROFIT_MULTIPLIER:
        return None

    return ManagementAction(
        trigger_id="T1",
        close_call=True,
        close_put_spread=False,
        reason=(
            f"Long call at {multiple:.2f}x entry "
            f"(current {current:.4f} vs entry {entry_cost:.4f}); "
            "close call leg, hold spread"
        ),
        context={
            "entry_long_call_cost": entry_cost,
            "current_long_call_mid": current,
            "multiple": multiple,
            "threshold_multiple": CALL_PROFIT_MULTIPLIER,
        },
    )
