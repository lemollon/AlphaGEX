"""Trigger T5 -- Short strike breached + <= 3 DTE.

Master spec section 4 trigger 5:
    "Short strike breached + 3 DTE -- Close everything"

The short put leg is on the LETF; the strike is "breached" when the
LETF spot is at or below the short_put_strike. Combined with <= 3 DTE,
this is a close-everything risk trigger -- the put spread can't be
relied on to bleed off in 3 days if it's already ITM.

T5 is the most data-sensitive trigger:
    - LETF spot must be set on the Position (current_letf_spot > 0)
    - 'now' is supplied so DTE is reproducible across testing and prod
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional

from ..state import ManagementAction, Position

DTE_THRESHOLD = 3


def evaluate(position: Position, now: Optional[datetime] = None) -> Optional[ManagementAction]:
    """Fire when LETF spot <= short-put strike AND DTE <= 3."""
    if position.current_letf_spot <= 0:
        # No LETF spot known -> can't evaluate; let other triggers handle.
        return None

    today = (now or datetime.now(timezone.utc)).date()
    dte = (position.expiration_date - today).days

    breached = position.current_letf_spot <= position.short_put_strike
    in_window = dte <= DTE_THRESHOLD

    if not (breached and in_window):
        return None

    return ManagementAction(
        trigger_id="T5",
        close_call=True,
        close_put_spread=True,
        reason=(
            f"Short strike {position.short_put_strike:.2f} breached "
            f"(LETF spot {position.current_letf_spot:.2f}) with {dte} DTE "
            f"<= {DTE_THRESHOLD}; close entire position"
        ),
        context={
            "short_put_strike": position.short_put_strike,
            "current_letf_spot": position.current_letf_spot,
            "expiration_date": position.expiration_date.isoformat(),
            "today": today.isoformat(),
            "dte": dte,
            "dte_threshold": DTE_THRESHOLD,
            "breach_distance": position.current_letf_spot - position.short_put_strike,
        },
    )
