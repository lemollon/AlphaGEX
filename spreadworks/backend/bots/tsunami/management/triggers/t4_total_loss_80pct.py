"""Trigger T4 -- Total loss > 80%% of defined max.

Master spec section 4 trigger 4:
    "Total loss > 80%% of defined max -- Close everything"

defined_max_loss is the put-spread width minus entry credit, snapshotted
at entry. Mark-to-market P&L = call_pnl + spread_pnl. We treat a loss
as MTM P&L < 0 and fire when -P&L > 0.80 * defined_max_loss.

Closes everything (call + put spread). This is a hard risk trigger;
the engine will preempt profit-taking triggers (T1, T3) when this
fires alongside them.
"""
from __future__ import annotations

from typing import Optional

from ..state import ManagementAction, Position

LOSS_TRIGGER_FRACTION = 0.80


def evaluate(position: Position) -> Optional[ManagementAction]:
    """Return ManagementAction if MTM loss > 80%% of defined_max_loss, else None."""
    defined_max = position.defined_max_loss
    if defined_max <= 0:
        # Spec assumes a true defined-risk position; degenerate setup -> skip.
        return None

    pnl = position.current_total_pnl
    if pnl >= 0:
        # Position is at MTM profit; T4 cannot fire.
        return None

    loss_magnitude = -pnl
    threshold = LOSS_TRIGGER_FRACTION * defined_max

    if loss_magnitude <= threshold:
        return None

    return ManagementAction(
        trigger_id="T4",
        close_call=True,
        close_put_spread=True,
        reason=(
            f"MTM loss {loss_magnitude:.4f} > {LOSS_TRIGGER_FRACTION * 100:.0f}%% "
            f"of defined max {defined_max:.4f} (threshold {threshold:.4f}); "
            "close entire position"
        ),
        context={
            "current_total_pnl": pnl,
            "loss_magnitude": loss_magnitude,
            "defined_max_loss": defined_max,
            "threshold_fraction": LOSS_TRIGGER_FRACTION,
            "loss_pct_of_max": loss_magnitude / defined_max,
        },
    )
