"""Regression test for the SHIB-PERP near-zero exit price bug (2026-09-24).

Production symptom: a SHIB short closed with exit_price 0.00000001 against
an entry of 0.00000561 (a ~561x move in one scan cycle), booking a fake
+$209.51 (+4988%) profit. The kSHIB unit fix (PR #3050) corrected entry
prices, but nothing guarded the exit path against a corrupt/stale upstream
tick that is still numerically > 0 slipping straight into trailing-stop and
close logic.

AgapeShibPerpExecutor.get_current_price() now rejects any single-cycle move
bigger than MAX_TICK_DEVIATION_PCT from the last known-good price and holds
the last good price instead, since SHIB does not move 50%+ between two scan
cycles on a real market event.
"""

import pytest

from trading.agape_shib_perp.executor import AgapeShibPerpExecutor
from trading.agape_shib_perp.models import AgapeShibPerpConfig


class _FakeSnapshot:
    def __init__(self, spot_price):
        self.spot_price = spot_price


def _make_executor():
    return AgapeShibPerpExecutor(AgapeShibPerpConfig())


def _patch_provider(monkeypatch, price):
    import data.crypto_data_provider as cdp

    fake_provider = type(
        "FakeProvider", (), {"get_snapshot": lambda self, symbol: _FakeSnapshot(price)}
    )()
    monkeypatch.setattr(cdp, "get_crypto_data_provider", lambda: fake_provider)


def test_normal_move_passes_through_and_stays_within_20pct_of_entry(monkeypatch):
    """A normal SHIB move (a few percent) must flow through untouched, and
    a position closed on it must land within 20% of entry - the behavior a
    real exit should have, not a 561x collapse."""
    entry_price = 0.00000561
    _patch_provider(monkeypatch, entry_price)
    executor = _make_executor()
    seeded = executor.get_current_price()
    assert seeded == pytest.approx(entry_price)

    # A realistic 3% adverse move.
    normal_move_price = entry_price * 1.03
    _patch_provider(monkeypatch, normal_move_price)
    exit_price = executor.get_current_price()

    assert exit_price == pytest.approx(normal_move_price)
    assert abs(exit_price - entry_price) / entry_price <= 0.20


def test_corrupt_near_zero_tick_is_rejected(monkeypatch):
    """The actual production bug: a tick of 0.00000001 (a ~561x drop from
    the last good price) must be rejected, not fed into exit/close logic."""
    entry_price = 0.00000561
    _patch_provider(monkeypatch, entry_price)
    executor = _make_executor()
    assert executor.get_current_price() == pytest.approx(entry_price)

    _patch_provider(monkeypatch, 0.00000001)
    guarded_price = executor.get_current_price()

    # Must hold the last known-good price, not the corrupt near-zero tick.
    assert guarded_price == pytest.approx(entry_price)
    assert guarded_price != pytest.approx(0.00000001)


def test_first_reading_is_always_accepted(monkeypatch):
    """With no prior good price, there is nothing to compare against - the
    very first tick must be accepted even if it looks extreme."""
    _patch_provider(monkeypatch, 0.00000001)
    executor = _make_executor()
    assert executor.get_current_price() == pytest.approx(0.00000001)


def test_none_or_non_positive_price_falls_back_to_last_good(monkeypatch):
    entry_price = 0.00000561
    _patch_provider(monkeypatch, entry_price)
    executor = _make_executor()
    executor.get_current_price()

    _patch_provider(monkeypatch, 0.0)
    assert executor.get_current_price() == pytest.approx(entry_price)
