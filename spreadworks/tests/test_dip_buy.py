"""UNDERTOW dip-buy strategy + indicator tests."""
from __future__ import annotations

from datetime import date

from backend.bots.strategies.dip_buy import (
    closed_bars, rsi, sma,
)


def _bar(d: str, high: float, close: float) -> dict:
    return {"date": d, "open": close, "high": high, "low": close, "close": close}


def test_closed_bars_drops_todays_partial_and_sorts():
    hist = [
        _bar("2026-06-10", 105, 104),  # today — partial, must be dropped
        _bar("2026-06-08", 101, 100),
        _bar("2026-06-09", 103, 102),
    ]
    bars = closed_bars(hist, date(2026, 6, 10))
    assert [b["date"] for b in bars] == ["2026-06-08", "2026-06-09"]


def test_sma_simple_average_of_last_period():
    assert sma([10, 20, 30, 40], 2) == 35.0
    assert sma([10, 20, 30, 40], 4) == 25.0


def test_sma_insufficient_returns_none():
    assert sma([10, 20], 5) is None


def test_rsi_all_gains_is_100():
    # strictly rising closes -> no losses -> RSI 100
    assert rsi([1, 2, 3, 4, 5], 2) == 100.0


def test_rsi_all_losses_is_zero():
    assert rsi([5, 4, 3, 2, 1], 2) == 0.0


def test_rsi_insufficient_returns_none():
    assert rsi([5], 2) is None
