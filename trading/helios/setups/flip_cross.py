"""Setup 3 — flip_cross: regime-transition directional.

Fires when:
  1. Spot has crossed the flip point through both +/-hysteresis bands
  2. net_gex has flipped sign within the 5-min buffer window
The buffer requires >= flip_buffer_minutes of history; otherwise we abstain.
"""
from __future__ import annotations

import datetime as dt
from collections import deque
from typing import Deque, Optional

from trading.helios.gex_client import GexSnapshot
from trading.helios.models import JoshuaConfig, SetupType
from trading.helios.setups.base import SetupAction


class FlipBuffer:
    """Rolling buffer of GexSnapshots, indexed by snapshot_at."""

    def __init__(self, max_minutes: int = 5):
        self._snaps: Deque[GexSnapshot] = deque()
        self.max_minutes = max_minutes

    def add(self, snap: GexSnapshot) -> None:
        self._snaps.append(snap)
        latest = snap.snapshot_at
        cutoff = latest - dt.timedelta(minutes=self.max_minutes)
        while self._snaps and self._snaps[0].snapshot_at < cutoff:
            self._snaps.popleft()

    def earliest_within(self, now: dt.datetime, *, minutes: int) -> Optional[GexSnapshot]:
        cutoff = now - dt.timedelta(minutes=minutes)
        for s in self._snaps:
            if s.snapshot_at >= cutoff:
                return s
        return None

    def has_buffer(self, now: dt.datetime, *, minutes: int) -> bool:
        earliest = self.earliest_within(now, minutes=minutes)
        if earliest is None:
            return False
        return (now - earliest.snapshot_at).total_seconds() >= (minutes - 1) * 60


def evaluate(snapshot: GexSnapshot, *, buffer: FlipBuffer, config: JoshuaConfig) -> Optional[SetupAction]:
    now = snapshot.snapshot_at
    if not buffer.has_buffer(now, minutes=config.flip_buffer_minutes):
        return None

    past = buffer.earliest_within(now, minutes=config.flip_buffer_minutes)
    if past is None:
        return None

    flip = snapshot.flip_point
    hyst = flip * config.flip_hysteresis_pct
    upper = flip + hyst
    lower = flip - hyst

    crossed_up = past.spot < lower and snapshot.spot > upper
    crossed_down = past.spot > upper and snapshot.spot < lower
    if not crossed_up and not crossed_down:
        return None

    regime_flip_to_pos = past.net_gex < 0 and snapshot.net_gex > 0
    regime_flip_to_neg = past.net_gex > 0 and snapshot.net_gex < 0

    long_strike = float(round(snapshot.spot))
    if crossed_up and regime_flip_to_pos:
        return SetupAction(
            setup=SetupType.FLIP_CROSS,
            direction="call",
            long_strike=long_strike,
            short_strike=long_strike + config.spread_width,
            reason="upward flip cross with net_gex sign-flip",
        )
    if crossed_down and regime_flip_to_neg:
        return SetupAction(
            setup=SetupType.FLIP_CROSS,
            direction="put",
            long_strike=long_strike,
            short_strike=long_strike - config.spread_width,
            reason="downward flip cross with net_gex sign-flip",
        )
    return None
