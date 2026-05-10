"""Tests for backtest.touch_pin.realized."""
import datetime as dt
import os
import pytest

from backtest.touch_pin.realized import compute_realized, RealizedOutcome
from backtest.touch_pin.vehicle import VerticalSpec


@pytest.mark.db
def test_realized_known_day():
    db_url = os.environ["DATABASE_URL"]
    spec = VerticalSpec(
        side="PIN-CALL", long_K=600.0, short_K=601.0, width=1.0,
        entry_mid=0.20,
        long_bid=0.18, long_ask=0.22,
        short_bid=0.05, short_ask=0.09,
    )
    outcome = compute_realized(
        db_url,
        trade_date=dt.date(2025, 6, 2),
        expiration_date=dt.date(2025, 6, 3),
        spec=spec,
        exit_minute=385,
    )
    if outcome is None:
        pytest.skip("no bars for 600C on 2025-06-02 expiring 2025-06-03; trying another date")
    assert isinstance(outcome, RealizedOutcome)
    assert -spec.width - 0.10 <= outcome.pnl_gross <= spec.width + 0.10


def test_realized_dataclass_shape():
    o = RealizedOutcome(
        exit_mid=0.50, exit_long_bid=0.48, exit_long_ask=0.52,
        exit_short_bid=0.10, exit_short_ask=0.14,
        touched_during_day=1, time_first_touch_minute=120,
        spot_at_exit=535.5, exit_skipped_reason=None,
        pnl_gross=0.30,
    )
    assert o.pnl_gross == pytest.approx(0.30)
