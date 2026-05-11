"""Tests for JOSHUA exit decision tree."""
import datetime as dt

from trading.helios.models import JoshuaConfig, ExitReason
from trading.helios.strategy import decide_exit, ExitDecision


def _now(h, m):
    return dt.datetime(2026, 5, 11, h, m)


def test_pt_hit():
    cfg = JoshuaConfig()
    d = decide_exit(debit=1.00, mark_to_close=1.25, now_ct=_now(10, 0), quotes_unavail_streak=0, config=cfg)
    assert d.should_exit
    assert d.reason == ExitReason.PT


def test_sl_hit():
    cfg = JoshuaConfig()
    d = decide_exit(debit=1.00, mark_to_close=0.70, now_ct=_now(10, 0), quotes_unavail_streak=0, config=cfg)
    assert d.should_exit
    assert d.reason == ExitReason.SL


def test_time_stop_at_15_55_ct():
    cfg = JoshuaConfig()
    d = decide_exit(debit=1.00, mark_to_close=1.05, now_ct=_now(15, 55), quotes_unavail_streak=0, config=cfg)
    assert d.should_exit
    assert d.reason == ExitReason.TIME_STOP


def test_time_stop_not_yet_before_15_55():
    cfg = JoshuaConfig()
    d = decide_exit(debit=1.00, mark_to_close=1.05, now_ct=_now(15, 54), quotes_unavail_streak=0, config=cfg)
    assert not d.should_exit


def test_data_failure_after_10_streaks():
    cfg = JoshuaConfig()
    d = decide_exit(debit=1.00, mark_to_close=1.05, now_ct=_now(10, 0), quotes_unavail_streak=10, config=cfg)
    assert d.should_exit
    assert d.reason == ExitReason.DATA_FAILURE


def test_pt_takes_precedence_over_time_stop():
    cfg = JoshuaConfig()
    d = decide_exit(debit=1.00, mark_to_close=1.25, now_ct=_now(15, 55), quotes_unavail_streak=0, config=cfg)
    assert d.reason == ExitReason.PT


def test_no_trailing_stop_field_in_decision():
    assert "TRAIL" not in {r.value for r in ExitReason}
