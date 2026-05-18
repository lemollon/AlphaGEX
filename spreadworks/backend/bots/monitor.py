"""Shared exit decision logic for all 3 bots."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time


@dataclass
class ExitDecision:
    should_close: bool
    reason: str | None  # PT | SL | EOD | EVENT_HALT | None


def pt_pct_for_time_of_day(now_ct_time: time) -> float:
    """BREEZE-only profit-target ladder.

    MORNING (open-11:00 CT) -> 0.30
    MIDDAY  (11:00-13:00 CT) -> 0.40
    AFTERNOON (13:00+)        -> 0.50

    Ported from IronForge SPARK fix-2.
    """
    if now_ct_time < time(11, 0):
        return 0.30
    if now_ct_time < time(13, 0):
        return 0.40
    return 0.50


def eod_close_time_for_strategy(strategy: str, eod_close_ct: time) -> time:
    return eod_close_ct  # currently uniform; kept for future per-strategy tweaks


def decide_exit(
    *,
    strategy: str,
    mtm_pnl: float,
    pt_target_pnl: float,
    sl_target_pnl: float,
    now_ct: datetime,
    front_expiration: date,
    eod_close_ct: time,
    event_blackout: bool,
) -> ExitDecision:
    if event_blackout:
        return ExitDecision(True, "EVENT_HALT")

    if mtm_pnl >= pt_target_pnl:
        return ExitDecision(True, "PT")
    if mtm_pnl <= -abs(sl_target_pnl):
        return ExitDecision(True, "SL")

    eod = eod_close_time_for_strategy(strategy, eod_close_ct)
    if strategy == "iron_butterfly":
        if now_ct.timetz().replace(tzinfo=None) >= eod:
            return ExitDecision(True, "EOD")
    else:
        # DC / DD only force-close on the day the FRONT leg expires
        if now_ct.date() == front_expiration and now_ct.timetz().replace(tzinfo=None) >= eod:
            return ExitDecision(True, "EOD")

    return ExitDecision(False, None)
