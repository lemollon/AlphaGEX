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
    # MORNING -> 0.30, MIDDAY -> 0.40, AFTERNOON -> 0.50
    assert pt_pct_for_time_of_day(time(9, 0)) == 0.30
    assert pt_pct_for_time_of_day(time(11, 30)) == 0.40
    assert pt_pct_for_time_of_day(time(13, 30)) == 0.50
