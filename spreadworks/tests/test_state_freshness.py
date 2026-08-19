"""Freshness on /risk — "am I looking at stale data?"

The page had every timestamp it needed (asof_close, flow.captured_at,
flow_rolling.captured_at) and rendered none of them, so a stale read looked
exactly like a fresh one. These pin the two ways that fix goes wrong.
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from backend.routes_risk import _state_freshness, _sessions_behind

CT = ZoneInfo("America/Chicago")


def _wed(h, m):                      # 2026-08-19 is a Wednesday
    return datetime(2026, 8, 19, h, m, tzinfo=CT)


FRESH_FLOW = {"captured_at": "2026-08-19T10:00:03"}
FRESH_ROLL = {"captured_at": "2026-08-19T11:00:00"}


def test_a_verdict_built_from_the_prior_close_is_not_stale():
    """🚨 THE TRAP. This page is a regime call made from the PREVIOUS session
    by design. Grading it against 'today' would print STALE every morning, and
    a warning that fires daily is one nobody reads."""
    f = _state_freshness(_wed(11, 2), datetime(2026, 8, 18).date(),
                         FRESH_FLOW, FRESH_ROLL)
    assert f["state"] == "CURRENT"
    assert f["expected_close"] == "2026-08-18"
    assert f["close_sessions_behind"] == 0


def test_a_genuinely_old_close_is_stale_and_says_which_leg():
    f = _state_freshness(_wed(11, 2), datetime(2026, 8, 14).date(),
                         FRESH_FLOW, FRESH_ROLL)
    assert f["state"] == "STALE"
    assert "VIX / term structure" in f["detail"]
    assert f["close_sessions_behind"] == 2      # 08-14 Fri -> 08-17, 08-18


def test_monday_expects_fridays_close_not_sundays():
    """Weekend handling: a Monday verdict built off Friday is current."""
    mon = datetime(2026, 8, 17, 11, 0, tzinfo=CT)
    f = _state_freshness(mon, datetime(2026, 8, 14).date(), FRESH_FLOW, FRESH_ROLL)
    assert f["expected_close"] == "2026-08-14"
    assert f["close_sessions_behind"] == 0


def test_a_missed_10am_snapshot_is_called_out_after_it_was_due():
    f = _state_freshness(_wed(11, 2), datetime(2026, 8, 18).date(),
                         {"captured_at": None}, FRESH_ROLL)
    assert f["state"] == "STALE"
    assert "DUE BUT NOT CAPTURED" in f["detail"]


def test_before_10am_a_missing_snapshot_is_not_a_fault():
    """Not-yet-due must read differently from missed — otherwise the bar is
    red every morning until 10:00 and gets ignored by 10:01."""
    f = _state_freshness(_wed(9, 0), datetime(2026, 8, 18).date(),
                         {"captured_at": None}, {"captured_at": None})
    assert f["state"] == "CURRENT"


def test_a_stalled_rolling_watcher_inside_its_window_is_a_fault():
    stale_roll = {"captured_at": "2026-08-19T11:00:00"}
    f = _state_freshness(_wed(12, 30), datetime(2026, 8, 18).date(),
                         FRESH_FLOW, stale_roll)          # 90 min old at 12:30
    assert f["state"] == "STALE"
    assert "rolling flow watcher" in f["detail"]


def test_the_same_gap_outside_the_window_is_not_a_fault():
    """After 14:00 the watcher is supposed to be quiet. A closed window must
    never look like a broken one."""
    f = _state_freshness(_wed(14, 45), datetime(2026, 8, 18).date(),
                         FRESH_FLOW, {"captured_at": "2026-08-19T13:50:00"})
    assert f["state"] == "CURRENT"


def test_freshness_never_raises_and_never_claims_fresh_on_error():
    f = _state_freshness(_wed(11, 0), None, None, None)    # garbage in
    assert f["state"] in ("UNKNOWN", "STALE")
    assert f["state"] != "CURRENT"


def test_sessions_behind_skips_weekends():
    from datetime import date
    assert _sessions_behind(date(2026, 8, 14), date(2026, 8, 18)) == 2
    assert _sessions_behind(date(2026, 8, 18), date(2026, 8, 18)) == 0
    assert _sessions_behind(date(2026, 8, 19), date(2026, 8, 18)) == -1
