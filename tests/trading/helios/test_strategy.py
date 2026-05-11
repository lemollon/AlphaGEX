import datetime as dt
import pytest
from trading.helios.models import HeliosConfig
from trading.helios.strategy import decide_exit, ExitReason


def _now(h, m):
    return dt.datetime(2026, 5, 8, h, m, tzinfo=dt.timezone.utc)


def test_pt_fires_in_grace_window():
    decision = decide_exit(
        debit=1.00, mark_to_close=1.20, minutes_since_entry=5,
        now_ct=_now(9, 0), config=HeliosConfig(),
    )
    assert decision.should_exit
    assert decision.reason == ExitReason.PT_GRACE


def test_sl_does_not_fire_in_grace_window():
    decision = decide_exit(
        debit=1.00, mark_to_close=0.40, minutes_since_entry=5,
        now_ct=_now(9, 0), config=HeliosConfig(),
    )
    assert not decision.should_exit


def test_sl_fires_after_grace():
    decision = decide_exit(
        debit=1.00, mark_to_close=0.40, minutes_since_entry=31,
        now_ct=_now(10, 0), config=HeliosConfig(),
    )
    assert decision.should_exit
    assert decision.reason == ExitReason.SL


def test_pt_fires_after_grace():
    decision = decide_exit(
        debit=1.00, mark_to_close=1.25, minutes_since_entry=120,
        now_ct=_now(11, 0), config=HeliosConfig(),
    )
    assert decision.should_exit
    assert decision.reason == ExitReason.PT


def test_eod_fires_at_close_time():
    decision = decide_exit(
        debit=1.00, mark_to_close=0.95, minutes_since_entry=300,
        now_ct=_now(14, 50), config=HeliosConfig(),
    )
    assert decision.should_exit
    assert decision.reason == ExitReason.EOD


def test_eod_does_not_fire_before_close_time():
    decision = decide_exit(
        debit=1.00, mark_to_close=0.95, minutes_since_entry=300,
        now_ct=_now(14, 49), config=HeliosConfig(),
    )
    assert not decision.should_exit


def test_pt_takes_priority_over_eod():
    decision = decide_exit(
        debit=1.00, mark_to_close=1.20, minutes_since_entry=300,
        now_ct=_now(14, 50), config=HeliosConfig(),
    )
    assert decision.reason == ExitReason.PT
