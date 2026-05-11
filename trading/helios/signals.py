"""JOSHUA setup-stack dispatcher.

Pure function. No I/O.

Order of dispatch:
  1. flip_cross — regime transition is highest-conviction
  2. wall_break — negative-gamma momentum
  3. wall_fade  — positive-gamma mean-reversion

A setup is skipped if it's already fired today (per DailyState). The
first unfired qualifying setup wins.
"""
from __future__ import annotations

from typing import Optional

from trading.helios.gex_client import GexSnapshot
from trading.helios.models import DailyState, JoshuaConfig, SetupType
from trading.helios.setups.base import SetupAction
from trading.helios.setups import wall_fade, wall_break, flip_cross


def dispatch(
    snapshot: GexSnapshot,
    *,
    state: DailyState,
    buffer: "flip_cross.FlipBuffer",
    config: JoshuaConfig,
) -> Optional[SetupAction]:
    if not state.is_fired(SetupType.FLIP_CROSS):
        action = flip_cross.evaluate(snapshot, buffer=buffer, config=config)
        if action is not None:
            return action

    if not state.is_fired(SetupType.WALL_BREAK):
        action = wall_break.evaluate(snapshot, config=config)
        if action is not None:
            return action

    if not state.is_fired(SetupType.WALL_FADE):
        action = wall_fade.evaluate(snapshot, config=config)
        if action is not None:
            return action

    return None
