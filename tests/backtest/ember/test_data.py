# tests/backtest/ember/test_data.py
import datetime as dt
import os
import math
import pytest
from backtest.ember.data import build_day_chain, t_years, delta_at, load_day, list_trade_dates


def _row(minute, strike, right, bid, ask, close):
    return {"minute": minute, "strike": strike, "right": right, "bid": bid, "ask": ask, "close": close}


def test_build_day_chain_groups_and_derives_spot():
    # At minute 0: 100C mid=2.0, 100P mid=1.0 -> spot ~ 100 + (2-1) = 101 (discount ~1 at 1DTE)
    rows = [
        _row(0, 100.0, "C", 1.9, 2.1, 2.0),
        _row(0, 100.0, "P", 0.9, 1.1, 1.0),
        _row(0, 105.0, "C", 0.4, 0.6, 0.5),
        _row(0, 105.0, "P", 5.0, 5.2, 5.1),
    ]
    day = build_day_chain(dt.date(2024, 6, 3), dt.date(2024, 6, 4), rows)
    assert day.sorted_minutes == [0]
    # spot from the strike minimizing |C-P| -> strike 100 (|2-1|=1 < |0.5-5.1|)
    assert math.isclose(day.spot(0), 101.0, abs_tol=0.5)
    assert day.quote(0, 100.0, "C").mid == 2.0


def test_build_day_chain_skips_minute_without_both_rights():
    rows = [_row(5, 100.0, "C", 1.0, 1.2, 1.1)]  # no put -> can't derive spot
    day = build_day_chain(dt.date(2024, 6, 3), dt.date(2024, 6, 4), rows)
    assert day.sorted_minutes == []   # minute dropped


def test_t_years_positive_and_small_for_1dte():
    # minute 0 on day T (09:30 ET), expiry 16:00 ET next day -> < 2 calendar days
    ty = t_years(dt.date(2024, 6, 3), dt.date(2024, 6, 4), minute=0)
    assert 0 < ty < (2.0 / 365.0)


def test_delta_at_short_put_is_negative_small():
    rows = [
        _row(0, 100.0, "C", 1.9, 2.1, 2.0),
        _row(0, 100.0, "P", 0.9, 1.1, 1.0),
        _row(0, 95.0, "C", 5.0, 5.2, 5.1),
        _row(0, 95.0, "P", 0.2, 0.3, 0.25),
    ]
    day = build_day_chain(dt.date(2024, 6, 3), dt.date(2024, 6, 4), rows)
    d = delta_at(day, minute=0, strike=95.0, right="P")
    assert d is None or (-0.5 < d < 0.0)


@pytest.mark.integration
def test_load_day_live_db():
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL not set")
    dates = list_trade_dates(os.environ["DATABASE_URL"], dt.date(2024, 1, 1), dt.date(2024, 1, 31))
    assert dates, "expected some 1DTE trading days in Jan 2024"
    day = load_day(dates[0], os.environ["DATABASE_URL"])
    assert day.sorted_minutes
    assert 0 <= day.sorted_minutes[0] <= 5
    mid_min = day.sorted_minutes[len(day.sorted_minutes) // 2]
    assert day.spot(mid_min) and 300 < day.spot(mid_min) < 800
