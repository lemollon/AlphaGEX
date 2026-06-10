"""Shared exit decision logic for all 3 bots."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time


@dataclass
class ExitDecision:
    should_close: bool
    reason: str | None  # PT | SL | EOD | EVENT_HALT | None


def pt_pct_for_time_of_day(now_ct_time: time) -> float:
    """Single-expiration butterfly profit-target ladder (BREEZE + RIVER).

    DECREASING — take profit EASIER as expiration approaches, because gamma
    risk grows toward end-of-day and a green 0DTE fly can give it all back in
    minutes. Anchored at 30% in the morning, eased through the day:

      MORNING (open-11:00 CT) -> 0.30
      MIDDAY  (11:00-13:00 CT) -> 0.25
      AFTERNOON (13:00+)        -> 0.20

    Returns a fraction of MAX PROFIT (credit for the iron fly, wing-minus-debit
    for the long fly). Both BREEZE (iron_butterfly) and RIVER (long_butterfly)
    re-derive their PT from this ladder each scan in scanner.py.

    History: was an INCREASING ladder (0.30/0.40/0.50) ported from IronForge
    SPARK fix-2, which raised the bar intraday and skipped a +36.6% BREEZE peak
    on 2026-05-29. Flipped to decreasing per operator decision the same day.
    """
    if now_ct_time < time(11, 0):
        return 0.30
    if now_ct_time < time(13, 0):
        return 0.25
    return 0.20


def pt_pct_for_iron_condor_tod(now_ct_time: time) -> float:
    """FLOW (Iron Condor 1DTE) profit-target ladder.

    Mirrors IronForge SPARK's behavior (decreasing — take profit earlier
    as expiration approaches, since gamma risk grows toward end-of-day):

      MORNING (open-11:00 CT) -> 0.30
      MIDDAY  (11:00-13:00 CT) -> 0.20
      AFTERNOON (13:00+)        -> 0.15
    """
    if now_ct_time < time(11, 0):
        return 0.30
    if now_ct_time < time(13, 0):
        return 0.20
    return 0.15


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
    entry_time: datetime | None = None,
    hold_days: int | None = None,
) -> ExitDecision:
    if event_blackout:
        return ExitDecision(True, "EVENT_HALT")

    if mtm_pnl >= pt_target_pnl:
        return ExitDecision(True, "PT")
    if mtm_pnl <= -abs(sl_target_pnl):
        return ExitDecision(True, "SL")

    if strategy == "dip_buy":
        # Multi-day long-call hold: no same-day EOD close. Exit on a hard
        # time-stop (kills post-peak decay) and never hold into expiry.
        if entry_time is not None and hold_days is not None:
            held_days = (now_ct.date() - entry_time.date()).days
            if held_days >= int(hold_days):
                return ExitDecision(True, "TIME_STOP")
        if now_ct.date() >= front_expiration:
            return ExitDecision(True, "PRE_EXPIRY")
        return ExitDecision(False, None)

    eod = eod_close_time_for_strategy(strategy, eod_close_ct)
    if strategy in ("iron_butterfly", "long_butterfly"):
        # 0DTE single-expiration strategies: force-close at EOD every day.
        if now_ct.timetz().replace(tzinfo=None) >= eod:
            return ExitDecision(True, "EOD")
    else:
        # DC / DD only force-close on the day the FRONT leg expires
        if now_ct.date() == front_expiration and now_ct.timetz().replace(tzinfo=None) >= eod:
            return ExitDecision(True, "EOD")

    return ExitDecision(False, None)
