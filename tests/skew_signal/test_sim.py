"""Tests for quant.sim.simulate_intraday."""
import pytest

from quant.sim import simulate_intraday, MarkSeries


def test_pt_hit():
    marks = {m: 1.0 + 0.05 * m for m in range(0, 11)}
    bars = MarkSeries(marks)
    out = simulate_intraday(
        debit=1.0, entry_minute=0, eod_minute=10, bars=bars,
        pt_pct=20.0, sl_pct=30.0,
    )
    assert out.exit_reason == "PT"
    assert out.exit_minute == 4
    assert out.realized_pct == pytest.approx(20.0)


def test_sl_hit_after_grace():
    marks = {m: 1.0 - 0.05 * m for m in range(0, 11)}
    bars = MarkSeries(marks)
    out = simulate_intraday(
        debit=1.0, entry_minute=0, eod_minute=10, bars=bars,
        pt_pct=50.0, sl_pct=30.0, sl_grace_minutes=2,
    )
    assert out.exit_reason == "SL"
    assert out.exit_minute == 6


def test_eod_when_no_trigger():
    marks = {m: 1.0 + 0.001 * m for m in range(0, 11)}
    bars = MarkSeries(marks)
    out = simulate_intraday(
        debit=1.0, entry_minute=0, eod_minute=10, bars=bars,
        pt_pct=50.0, sl_pct=50.0,
    )
    assert out.exit_reason == "EOD"
    assert out.exit_minute == 10


def test_trail_activates_and_exits():
    marks = {0: 1.0, 1: 1.05, 2: 1.10, 3: 1.05, 4: 1.00}
    bars = MarkSeries(marks)
    out = simulate_intraday(
        debit=1.0, entry_minute=0, eod_minute=10, bars=bars,
        pt_pct=50.0, sl_pct=50.0,
        trailing_activate_pct=5.0, trailing_stop_pct=8.0,
    )
    assert out.exit_reason == "TRAIL"
    assert out.exit_minute == 4
