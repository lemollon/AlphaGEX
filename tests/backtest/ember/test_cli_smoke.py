import datetime as dt
from backtest.ember.models import Quote, MinuteChain, DayChain
from backtest.ember.policy import default_grid
from backtest.ember.cli import run_policies_for_day, pick_best


def _day(trade_date, decay):
    """Iron-condor-able day: spot 500, strikes 480..520, combo decays by `decay` factor by EOD."""
    minutes = {}
    spot = 500.0
    for m, factor in [(0, 1.0), (200, 1.0 - decay / 2), (385, 1.0 - decay)]:
        quotes = {}
        for k in range(480, 521, 5):
            c_intrinsic = max(spot - k, 0.0)
            p_intrinsic = max(k - spot, 0.0)
            tv = max(2.5 - 0.05 * abs(k - spot), 0.2) * factor
            c_mid = c_intrinsic + tv
            p_mid = p_intrinsic + tv
            quotes[(float(k), "C")] = Quote(c_mid - 0.1, c_mid + 0.1, c_mid)
            quotes[(float(k), "P")] = Quote(p_mid - 0.1, p_mid + 0.1, p_mid)
        minutes[m] = MinuteChain(minute=m, spot=spot, quotes=quotes)
    return DayChain(trade_date, trade_date + dt.timedelta(days=1), minutes)


def test_run_and_pick_best_produces_results():
    from backtest.ember.adapters.base import AdapterConfig
    from backtest.ember.adapters.spark import SparkRepresentativeIC
    from backtest.ember.fills import FILL_MID

    days = [_day(dt.date(2024, 1, 3 + i), decay=0.6) for i in range(5)]
    adapter = SparkRepresentativeIC()
    cfg = AdapterConfig(entry_minute=0, short_delta=0.16, wing_width=5.0)
    grid = default_grid()

    # results: policy_name -> list[TradeResult]
    results = {}
    for day in days:
        per_day = run_policies_for_day(day, adapter, cfg, grid, fill=FILL_MID)
        for name, tr in per_day.items():
            results.setdefault(name, []).append(tr)

    assert results, "expected trades for at least one policy"
    best_name, best_summary = pick_best(results)
    assert best_name in results
    assert best_summary["n"] >= 1
