import datetime as dt
import os
import pytest
from backtest.ember.build import DayPath, build_paths, evaluate_grid, evaluate_policy
from backtest.ember.policy import ExitPolicy


def _dp(date, path, is_oos=False, credit=1.0):
    return DayPath(trade_date=date, entry_minute=0, entry_credit=credit, contracts=1,
                   commission_dollars=5.2, is_oos=is_oos, path=path)


def test_daypath_roundtrip():
    dp = _dp(dt.date(2024, 6, 3), [(0, 0.0), (10, 30.0)], is_oos=True)
    dp2 = DayPath.from_dict(dp.to_dict())
    assert dp2.trade_date == dp.trade_date
    assert dp2.path == dp.path
    assert dp2.is_oos is True
    assert dp2.entry_credit == dp.entry_credit
    assert dp2.commission_dollars == dp.commission_dollars


def test_evaluate_grid_splits_in_sample_oos():
    paths = [
        _dp(dt.date(2024, 3, 1), [(0, 0.0), (10, 60.0), (385, 60.0)], is_oos=False),
        _dp(dt.date(2025, 3, 1), [(0, 0.0), (10, -60.0), (385, -60.0)], is_oos=True),
    ]
    grid = [ExitPolicy("pt50", profit_target_pct=50, stop_loss_mult=None, time_stop_minute=None, min_hold_minutes=1)]
    res = evaluate_grid(paths, grid)
    assert len(res) == 1
    assert res[0]["policy"] == "pt50"
    assert res[0]["in_sample"]["n"] == 1
    assert res[0]["oos"]["n"] == 1


def test_evaluate_policy_equity_curve_and_trades():
    paths = [
        _dp(dt.date(2024, 3, 2), [(0, 0.0), (10, 60.0), (385, 60.0)]),
        _dp(dt.date(2024, 3, 1), [(0, 0.0), (10, 60.0), (385, 60.0)]),  # earlier date, out of order
    ]
    policy = ExitPolicy("pt50", profit_target_pct=50, stop_loss_mult=None, time_stop_minute=None, min_hold_minutes=1)
    res = evaluate_policy(paths, policy)
    assert len(res["trades"]) == 2
    assert len(res["equity_curve"]) == 2
    # equity curve is sorted by date and cumulative
    assert res["equity_curve"][0]["date"] == "2024-03-01"
    assert res["equity_curve"][1]["cum_pnl"] > res["equity_curve"][0]["cum_pnl"]
    assert res["in_sample"]["n"] == 2


@pytest.mark.integration
def test_build_paths_live_db():
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL not set")
    paths = build_paths(dt.date(2024, 1, 1), dt.date(2024, 1, 31), entry_minute=30,
                        short_delta=0.16, wing_width=5.0, fill="ask_cross",
                        db_url=os.environ["DATABASE_URL"])
    assert len(paths) >= 5
    assert all(p.path for p in paths)
    assert all(p.entry_credit > 0 for p in paths)
