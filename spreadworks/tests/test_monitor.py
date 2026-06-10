from datetime import datetime, time, date
from zoneinfo import ZoneInfo

from backend.bots.monitor import (
    decide_exit, ExitDecision, eod_close_time_for_strategy,
    pt_pct_for_time_of_day,
)

CT = ZoneInfo("America/Chicago")


def test_pt_hit_returns_pt():
    d = decide_exit(
        strategy="iron_butterfly", mtm_pnl=50.0,
        pt_target_pnl=45.0, sl_target_pnl=300.0,
        now_ct=datetime(2026, 5, 20, 11, 0, tzinfo=CT),
        front_expiration=date(2026, 5, 20),
        eod_close_ct=time(14, 45),
        event_blackout=False,
    )
    assert d.should_close
    assert d.reason == "PT"


def test_sl_hit_returns_sl():
    d = decide_exit(
        strategy="iron_butterfly", mtm_pnl=-310.0,
        pt_target_pnl=45.0, sl_target_pnl=300.0,
        now_ct=datetime(2026, 5, 20, 11, 0, tzinfo=CT),
        front_expiration=date(2026, 5, 20),
        eod_close_ct=time(14, 45),
        event_blackout=False,
    )
    assert d.should_close
    assert d.reason == "SL"


def test_breeze_eod_force_close():
    d = decide_exit(
        strategy="iron_butterfly", mtm_pnl=10.0,
        pt_target_pnl=45.0, sl_target_pnl=300.0,
        now_ct=datetime(2026, 5, 20, 14, 46, tzinfo=CT),
        front_expiration=date(2026, 5, 20),
        eod_close_ct=time(14, 45),
        event_blackout=False,
    )
    assert d.should_close
    assert d.reason == "EOD"


def test_tide_holds_overnight_when_not_expiry_day():
    d = decide_exit(
        strategy="double_calendar", mtm_pnl=10.0,
        pt_target_pnl=45.0, sl_target_pnl=300.0,
        now_ct=datetime(2026, 5, 20, 14, 46, tzinfo=CT),
        front_expiration=date(2026, 5, 21),  # tomorrow
        eod_close_ct=time(14, 45),
        event_blackout=False,
    )
    assert not d.should_close


def test_tide_closes_on_expiry_day_after_eod():
    d = decide_exit(
        strategy="double_calendar", mtm_pnl=10.0,
        pt_target_pnl=45.0, sl_target_pnl=300.0,
        now_ct=datetime(2026, 5, 21, 14, 46, tzinfo=CT),
        front_expiration=date(2026, 5, 21),
        eod_close_ct=time(14, 45),
        event_blackout=False,
    )
    assert d.should_close
    assert d.reason == "EOD"


def test_event_blackout_closes():
    d = decide_exit(
        strategy="iron_butterfly", mtm_pnl=10.0,
        pt_target_pnl=45.0, sl_target_pnl=300.0,
        now_ct=datetime(2026, 5, 20, 11, 0, tzinfo=CT),
        front_expiration=date(2026, 5, 20),
        eod_close_ct=time(14, 45),
        event_blackout=True,
    )
    assert d.should_close
    assert d.reason == "EVENT_HALT"


def test_pt_ladder_morning_midday_afternoon():
    # DECREASING ladder: take profit easier as expiry approaches.
    # MORNING -> 0.30, MIDDAY -> 0.25, AFTERNOON -> 0.20
    assert pt_pct_for_time_of_day(time(9, 0)) == 0.30
    assert pt_pct_for_time_of_day(time(11, 30)) == 0.25
    assert pt_pct_for_time_of_day(time(13, 30)) == 0.20
    # Monotonically non-increasing through the day.
    assert (pt_pct_for_time_of_day(time(9, 0))
            >= pt_pct_for_time_of_day(time(11, 30))
            >= pt_pct_for_time_of_day(time(13, 30)))


# ---------------------------------------------------------------------------
# dip_buy branch: TIME_STOP + PRE_EXPIRY
# ---------------------------------------------------------------------------

def _call(now, *, entry, hold_days=2, exp="2026-06-22", mtm=0.0):
    return decide_exit(
        strategy="dip_buy", mtm_pnl=mtm, pt_target_pnl=200.0,
        sl_target_pnl=250.0, now_ct=now, front_expiration=date.fromisoformat(exp),
        eod_close_ct=time(14, 45), event_blackout=False,
        entry_time=entry, hold_days=hold_days,
    )


def test_dip_buy_pt_fires():
    d = _call(datetime(2026, 6, 10, 10, 0), entry=datetime(2026, 6, 10, 9, 0), mtm=250.0)
    assert d.should_close and d.reason == "PT"


def test_dip_buy_sl_fires():
    d = _call(datetime(2026, 6, 10, 10, 0), entry=datetime(2026, 6, 10, 9, 0), mtm=-300.0)
    assert d.should_close and d.reason == "SL"


def test_dip_buy_time_stop_fires_after_hold_days():
    # entered 2026-06-08, now 2026-06-10 -> 2 calendar days held >= hold_days 2
    d = _call(datetime(2026, 6, 10, 9, 0), entry=datetime(2026, 6, 8, 9, 0))
    assert d.should_close and d.reason == "TIME_STOP"


def test_dip_buy_holds_before_time_stop():
    d = _call(datetime(2026, 6, 9, 9, 0), entry=datetime(2026, 6, 8, 9, 0))
    assert not d.should_close


def test_dip_buy_pre_expiry_force_close():
    d = _call(datetime(2026, 6, 22, 9, 0), entry=datetime(2026, 6, 21, 9, 0),
              hold_days=99, exp="2026-06-22")
    assert d.should_close and d.reason == "PRE_EXPIRY"
