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


def _synthetic_day(date=dt.date(2024, 6, 3)):
    from backtest.ember.models import Quote, MinuteChain, DayChain
    quotes = {}
    spot = 500.0
    for k in range(480, 521, 5):
        c_int = max(spot - k, 0.0); p_int = max(k - spot, 0.0)
        tv = max(2.5 - 0.05 * abs(k - spot), 0.2)
        quotes[(float(k), "C")] = Quote(c_int + tv - 0.1, c_int + tv + 0.1, c_int + tv)
        quotes[(float(k), "P")] = Quote(p_int + tv - 0.1, p_int + tv + 0.1, p_int + tv)
    mc = MinuteChain(minute=0, spot=spot, quotes=quotes)
    return DayChain(date, date + dt.timedelta(days=1), {0: mc})


def test_day_path_from_chain_builds_valid_daypath():
    from backtest.ember.build import day_path_from_chain
    from backtest.ember.adapters.base import AdapterConfig
    cfg = AdapterConfig(entry_minute=0, short_delta=0.16, wing_width=5.0)
    dp = day_path_from_chain(_synthetic_day(), cfg, fill="ask_cross", is_oos=True)
    assert dp is not None
    assert dp.is_oos is True
    assert dp.entry_credit > 0
    assert dp.commission_dollars > 0
    assert len(dp.path) >= 1


def test_day_path_from_chain_none_when_no_entry():
    from backtest.ember.build import day_path_from_chain
    from backtest.ember.adapters.base import AdapterConfig
    from backtest.ember.models import DayChain
    import datetime as _dt
    empty = DayChain(_dt.date(2024, 6, 3), _dt.date(2024, 6, 4), {})  # no minutes -> ineligible
    cfg = AdapterConfig(entry_minute=0, short_delta=0.16, wing_width=5.0)
    assert day_path_from_chain(empty, cfg, fill="ask_cross", is_oos=False) is None


def test_build_cancelled_exception_exists():
    from backtest.ember.build import BuildCancelled
    assert issubclass(BuildCancelled, Exception)


@pytest.mark.integration
def test_build_paths_reports_incremental_progress():
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL not set")
    calls = []
    paths = build_paths(dt.date(2024, 1, 1), dt.date(2024, 1, 31), entry_minute=30,
                        short_delta=0.16, wing_width=5.0, fill="ask_cross",
                        db_url=os.environ["DATABASE_URL"],
                        progress_cb=lambda done, total, msg: calls.append((done, total, msg)))
    assert len(paths) >= 5
    assert len(calls) >= 5
    # progress is monotonic non-decreasing in `done`, and messages are non-empty
    assert calls[0][2] and isinstance(calls[0][2], str)
    dones = [c[0] for c in calls]
    assert dones == sorted(dones)
    assert calls[-1][0] == calls[-1][1]  # ends at done == total


@pytest.mark.integration
def test_build_paths_cancellation_raises():
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL not set")
    from backtest.ember.build import BuildCancelled
    with pytest.raises(BuildCancelled):
        build_paths(dt.date(2024, 1, 1), dt.date(2024, 3, 31), entry_minute=30,
                    short_delta=0.16, wing_width=5.0, fill="ask_cross",
                    db_url=os.environ["DATABASE_URL"],
                    should_cancel=lambda: True)  # cancel on the very first check (i=0)
