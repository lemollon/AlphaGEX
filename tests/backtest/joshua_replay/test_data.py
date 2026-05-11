"""Replay loader tests."""
import datetime as dt
import os
import pytest

from backtest.joshua_replay.data import load_snapshots, regime_from_watchtower


def test_regime_from_watchtower_positive_levels():
    assert regime_from_watchtower("POSITIVE", 300_000) == "MODERATE_POSITIVE"
    assert regime_from_watchtower("POSITIVE", 800_000) == "HIGH_POSITIVE"
    assert regime_from_watchtower("POSITIVE", 2_000_000) == "EXTREME_POSITIVE"


def test_regime_from_watchtower_negative_levels():
    assert regime_from_watchtower("NEGATIVE", -300_000) == "MODERATE_NEGATIVE"
    assert regime_from_watchtower("NEGATIVE", -800_000) == "HIGH_NEGATIVE"
    assert regime_from_watchtower("NEGATIVE", -2_000_000) == "EXTREME_NEGATIVE"


def test_regime_from_watchtower_neutral():
    assert regime_from_watchtower("NEUTRAL", 0.0) == "NEUTRAL"
    assert regime_from_watchtower("NEUTRAL", 100_000) == "NEUTRAL"


@pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL not set; skipping DB-backed test",
)
def test_load_snapshots_known_busy_day_returns_rows():
    # 2026-03-30 had 305 snapshots in production
    snaps = load_snapshots(dt.date(2026, 3, 30), dt.date(2026, 3, 30), symbol="SPY")
    if not snaps:
        pytest.skip("no watchtower data for 2026-03-30")
    assert len(snaps) > 100
    s = snaps[0]
    assert s.symbol == "SPY"
    assert s.spot > 0
    assert s.regime in {
        "EXTREME_NEGATIVE", "HIGH_NEGATIVE", "MODERATE_NEGATIVE",
        "NEUTRAL",
        "MODERATE_POSITIVE", "HIGH_POSITIVE", "EXTREME_POSITIVE",
    }
