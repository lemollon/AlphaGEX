"""Integration tests against real ORAT postgres. Marked @integration; skipped without DB env."""
import datetime as dt
import os

import pytest

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.environ.get("ORAT_DATABASE_URL"),
        reason="ORAT_DATABASE_URL not set",
    ),
]


def test_load_trading_days_returns_expected_count_for_known_week():
    from backtest.directional_1dte.data import load_trading_days
    # Week of 2024-03-11 (M-F, no holidays) — exactly 5 trading days
    days = load_trading_days(dt.date(2024, 3, 11), dt.date(2024, 3, 15))
    assert len(days) == 5
    assert days[0] == dt.date(2024, 3, 11)
    assert days[-1] == dt.date(2024, 3, 15)


def test_load_chain_returns_indexed_dataframe_with_required_columns():
    from backtest.directional_1dte.data import load_chain
    chain = load_chain(dt.date(2024, 3, 15))
    assert len(chain) > 100  # SPY March 2024 has thousands of strikes
    required = {"call_bid", "call_ask", "call_mid", "put_bid", "put_ask", "put_mid",
                "underlying_price", "dte"}
    assert required.issubset(set(chain.columns))
    assert chain.index.names == ["expiration_date", "strike"]


def test_load_vix_returns_float_for_known_date():
    from backtest.directional_1dte.data import load_vix
    vix = load_vix(dt.date(2024, 3, 15))
    assert vix is not None
    assert 5.0 < vix < 100.0


def test_load_vix_returns_none_for_weekend():
    from backtest.directional_1dte.data import load_vix
    assert load_vix(dt.date(2024, 3, 16)) is None


def test_load_gex_walls_returns_walls_for_known_date():
    from backtest.directional_1dte.data import load_gex_walls
    walls = load_gex_walls(dt.date(2024, 3, 15))
    assert walls is not None
    assert "call_wall" in walls and walls["call_wall"] > 0
    assert "put_wall" in walls and walls["put_wall"] > 0
    assert "spot" in walls and walls["spot"] > 0
