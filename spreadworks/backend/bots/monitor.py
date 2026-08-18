"""Shared exit decision logic for all 3 bots."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time


@dataclass
class ExitDecision:
    should_close: bool
    reason: str | None  # PT | SL | EOD | EVENT_HALT | None


MULTI_DAY_STRATEGIES = frozenset(
    {"dip_buy", "vertical_debit", "vertical_credit",
     "bull_call_spread", "bear_put_spread", "bull_put_spread", "bear_call_spread"}
)


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
    hold_minutes: int | None = None,
    settle_at_expiry: bool = False,
    pivot_confirmed: bool = False,
) -> ExitDecision:
    if event_blackout:
        return ExitDecision(True, "EVENT_HALT")

    # settle_at_expiry structures (RIPPLE/SPLASH flies, EBB's 0DTE put credit
    # spread) are NEVER bought back — the scanner books intrinsic value vs the
    # official close via the settlement pass. This must be checked BEFORE
    # PT/SL so a "no stop by design" strategy (EBB, registry #23b) cannot be
    # closed early no matter what pt_pct/sl_pct happen to be configured — the
    # % NUMERIC(5,4) ceiling cannot otherwise guarantee an unreachable SL for
    # a credit vertical whose max loss dwarfs its credit. RIPPLE/SPLASH were
    # already unaffected in practice (their pt_pct/sl_pct were documented as
    # unreachable), so this is a no-op for them and a real guarantee for EBB.
    if settle_at_expiry:
        # ONE exception, added 2026-08-18: the CONFIRMED-DIRECTION pivot.
        #
        # "No stop by design" is correct and stays correct — every previous
        # stop test on this stream failed. Re-measured on 892 sessions of real
        # expiry-day NBBO, the control is unambiguous: closing on a 0.10%
        # down-break UNCONDITIONALLY fires on 45.7% of days and LOSES $1,050.
        # That is the finding that made "never buy it back" the rule.
        #
        # The same exit gated on the morning put/call MIX being extreme is a
        # different animal — it fires on 3.7% of days and adds +$952
        # (t=+1.95), lifting EBB from $3.13 to $4.20/trade and ret/DD from
        # 2.98 to 5.55 with the worst month improving -$581 -> -$350. Positive
        # in all four years and in every offset/wing variant tried (+$778 to
        # +$1,517). It wins on only 42% of its firings: this truncates the
        # tail, it does not improve the median.
        #
        # 🚨 So the gate is the whole edge. `pivot_confirmed` must NEVER be
        # set from price alone — it requires stage 1 (flow mix) AND stage 2
        # (price commitment). Loosening it back toward a plain stop walks
        # straight into the control's -$1,050.
        if pivot_confirmed:
            return ExitDecision(True, "PIVOT")
        return ExitDecision(False, None)

    if mtm_pnl >= pt_target_pnl:
        return ExitDecision(True, "PT")
    if mtm_pnl <= -abs(sl_target_pnl):
        return ExitDecision(True, "SL")

    # Intraday time-stop, in MINUTES. UPDRAFT (45m) and BACKDRAFT (30m) are
    # timer exits: the research showed a profit target cut returns roughly
    # 6x, so the timer IS the exit and pt_target_pnl is set unreachable.
    # Checked before the strategy branches so it applies to any 0DTE bot.
    if hold_minutes is not None and entry_time is not None:
        held_min = (now_ct - entry_time).total_seconds() / 60.0
        if held_min >= float(hold_minutes):
            return ExitDecision(True, "TIME_STOP")

    if strategy in MULTI_DAY_STRATEGIES:
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
        # settle_at_expiry (RIPPLE) already returned above — this only runs
        # for the buyback flies (BREEZE-style). 0DTE single-expiration
        # strategies force-close at EOD every day.
        if now_ct.timetz().replace(tzinfo=None) >= eod:
            return ExitDecision(True, "EOD")
    else:
        # DC / DD only force-close on the day the FRONT leg expires
        if now_ct.date() == front_expiration and now_ct.timetz().replace(tzinfo=None) >= eod:
            return ExitDecision(True, "EOD")

    return ExitDecision(False, None)
