"""Trigger T3 -- Put spread at 50%% of max profit.

Master spec section 4 trigger 3:
    "Put spread at 50%% of max profit -- Close put spread, hold call"

The put spread's max profit equals the entry credit (entry_put_spread_credit);
the current cost-to-close equals current_put_spread_value (short_mid - long_mid).
50%% of max profit captured when current_close_cost <= 0.5 * entry_credit.

Action: close put spread only; long call stays open. The remaining
upside in the call is uncapped, so we let it run.
"""
from __future__ import annotations

from typing import Optional

from ..state import ManagementAction, Position

PROFIT_CAPTURE_FRACTION = 0.50


def evaluate(position: Position) -> Optional[ManagementAction]:
    """Return ManagementAction if put spread is at >= 50%% of max profit, else None."""
    entry_credit = position.entry_put_spread_credit
    if entry_credit <= 0:
        # Degenerate: entered as a debit spread or zero-credit; T3 undefined.
        return None

    current_value = position.current_put_spread_value
    profit_threshold = (1.0 - PROFIT_CAPTURE_FRACTION) * entry_credit

    if current_value > profit_threshold:
        return None

    profit_captured = entry_credit - current_value
    profit_pct = profit_captured / entry_credit

    return ManagementAction(
        trigger_id="T3",
        close_call=False,
        close_put_spread=True,
        reason=(
            f"Put spread at {profit_pct * 100:.1f}%% of max profit captured "
            f"(current value {current_value:.4f} <= {profit_threshold:.4f} = "
            f"{(1 - PROFIT_CAPTURE_FRACTION) * 100:.0f}%% of entry credit "
            f"{entry_credit:.4f}); close spread, hold call"
        ),
        context={
            "entry_put_spread_credit": entry_credit,
            "current_put_spread_value": current_value,
            "profit_captured": profit_captured,
            "profit_pct_of_max": profit_pct,
            "threshold_fraction": PROFIT_CAPTURE_FRACTION,
        },
    )
