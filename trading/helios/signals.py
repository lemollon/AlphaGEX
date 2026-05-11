"""JOSHUA setup-stack dispatcher.

Pure function. No I/O.

Order of dispatch:
  1. flip_cross — regime transition is highest-conviction
  2. wall_break — negative-gamma momentum
  3. wall_fade  — positive-gamma mean-reversion

A setup is skipped once its daily count reaches `max_trades_per_setup_per_day`.
The first uncapped qualifying setup wins.
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
    cap = config.max_trades_per_setup_per_day

    if not state.is_capped(SetupType.FLIP_CROSS, max_per_day=cap):
        action = flip_cross.evaluate(snapshot, buffer=buffer, config=config)
        if action is not None:
            return action

    if not state.is_capped(SetupType.WALL_BREAK, max_per_day=cap):
        action = wall_break.evaluate(snapshot, config=config)
        if action is not None:
            return action

    if not state.is_capped(SetupType.WALL_FADE, max_per_day=cap):
        action = wall_fade.evaluate(snapshot, config=config)
        if action is not None:
            return action

    return None
