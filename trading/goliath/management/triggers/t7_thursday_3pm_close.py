"""Trigger T7 -- Mandatory Thursday 3:00 PM ET close.

Master spec section 4 trigger 7:
    "Thursday 3:00 PM ET -- Mandatory close, regardless of P&L"

For a position expiring on Friday (the standard 7-DTE entry; spec
section 1.7), this fires at-or-after 15:00 ET on the preceding
Thursday. After that cutoff, T7 always fires regardless of any
profit/loss state.

Timezone discipline: 'now' is normalized to America/New_York via
zoneinfo before comparison. Caller can pass any tz-aware datetime;
naive datetimes are rejected as a defensive guard.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from ..state import ManagementAction, Position

_ET = ZoneInfo("America/New_York")
THURSDAY_CUTOFF_TIME = time(15, 0)  # 3:00 PM ET


def _thursday_cutoff_for_expiration(expiration_date: date) -> datetime:
    """Return the Thursday-3pm-ET cutoff datetime for the given expiration.

    Spec assumes a Friday expiration; we subtract one calendar day and
    set the local-clock to 15:00 ET. zoneinfo handles DST automatically.
    """
    thursday = expiration_date - timedelta(days=1)
    return datetime.combine(thursday, THURSDAY_CUTOFF_TIME, tzinfo=_ET)


def evaluate(position: Position, now: Optional[datetime] = None) -> Optional[ManagementAction]:
    """Fire when now (in ET) is at or after Thursday 3pm ET of expiration week."""
    if now is None:
        now = datetime.now(_ET)
    if now.tzinfo is None:
        # Defensive: refuse to evaluate naive datetimes; ambiguous TZ.
        return None

    cutoff = _thursday_cutoff_for_expiration(position.expiration_date)
    now_et = now.astimezone(_ET)

    if now_et < cutoff:
        return None

    return ManagementAction(
        trigger_id="T7",
        close_call=True,
        close_put_spread=True,
        reason=(
            f"Past mandatory Thursday-3pm-ET cutoff "
            f"({cutoff.isoformat()}); now={now_et.isoformat()}"
        ),
        context={
            "now_et": now_et.isoformat(),
            "cutoff_et": cutoff.isoformat(),
            "expiration_date": position.expiration_date.isoformat(),
        },
    )
