"""Tests for backtest.touch_pin.loader."""
import datetime as dt
import os
import pytest

from backtest.touch_pin.loader import load_minute_chain, ChainEntry, MinuteSnapshot


@pytest.mark.db
def test_load_minute_chain_known_day():
    db_url = os.environ["DATABASE_URL"]
    snap = load_minute_chain(
        db_url,
        trade_date=dt.date(2025, 6, 2),
        expiration_date=dt.date(2025, 6, 3),
        target_minute=5,
    )
    assert snap is not None
    assert isinstance(snap, MinuteSnapshot)
    assert snap.trade_date == dt.date(2025, 6, 2)
    assert len(snap.chain) >= 5
    for k, entry in snap.chain.items():
        assert isinstance(entry, ChainEntry)
        assert entry.strike == k


def test_minute_snapshot_dataclass_shape():
    e = ChainEntry(
        strike=500.0,
        call_bid=0.10, call_ask=0.12,
        put_bid=0.05, put_ask=0.07,
        call_volume=100, put_volume=50,
    )
    assert e.call_mid == pytest.approx(0.11)
    assert e.put_mid == pytest.approx(0.06)
    assert e.call_valid()
    assert e.put_valid()


def test_chain_entry_invalid_quotes():
    e = ChainEntry(strike=500.0, call_bid=0.0, call_ask=0.05, put_bid=0.05, put_ask=0.07)
    assert not e.call_valid()
    assert e.put_valid()
