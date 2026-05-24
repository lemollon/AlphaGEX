import datetime as dt
import os
import pytest
from backtest.ember.models import Leg, Quote, MinuteChain, DayChain
from backtest.ember.spark_replay import (SparkTrade, spark_day_path, build_spark_paths,
                                          compare_spark, load_spark_trades)


def _spark_trade(date=dt.date(2026, 3, 16)):
    legs = [Leg(722.0, "P", -1), Leg(717.0, "P", 1), Leg(748.0, "C", -1), Leg(753.0, "C", 1)]
    return SparkTrade(trade_date=date, entry_minute=30, legs=legs, contracts=10,
                      actual_pnl_per_contract=5.0, actual_exit_reason="profit_target_MORNING")


def _chain_with(date, strikes_present, value=1.0, minutes=(30, 200, 385)):
    """Build a DayChain where the given (strike,right) set is present each minute, combo mid=value.

    Strikes closer to spot=735 get the full value; strikes further away get a fraction,
    so that a short-outer-long inner condor structure yields a positive net credit."""
    spot = 735.0
    mc_map = {}
    for m in minutes:
        quotes = {}
        for (k, r) in strikes_present:
            dist = abs(k - spot)
            # Scale: closer to ATM → full value; wing strikes are worth ~30%
            scale = max(0.3, 1.0 - dist / 30.0)
            mid = value * scale
            quotes[(k, r)] = Quote(mid - 0.05, mid + 0.05, mid)
        mc_map[m] = MinuteChain(minute=m, spot=spot, quotes=quotes)
    return DayChain(date, date + dt.timedelta(days=1), mc_map)


def test_spark_day_path_prices_when_strikes_present():
    t = _spark_trade()
    present = [(722.0, "P"), (717.0, "P"), (748.0, "C"), (753.0, "C")]
    chain = _chain_with(t.trade_date, present, value=0.8)
    dp = spark_day_path(chain, t)
    assert dp is not None
    assert dp.entry_credit > 0
    assert dp.is_oos is False
    assert len(dp.path) >= 1


def test_spark_day_path_none_when_strike_missing():
    t = _spark_trade()
    # missing the long call (753) — outside the captured band
    present = [(722.0, "P"), (717.0, "P"), (748.0, "C")]
    chain = _chain_with(t.trade_date, present, value=0.8)
    assert spark_day_path(chain, t) is None


def test_spark_day_path_uses_nearest_minute_at_or_after_entry():
    t = _spark_trade()  # entry_minute=30
    present = [(722.0, "P"), (717.0, "P"), (748.0, "C"), (753.0, "C")]
    chain = _chain_with(t.trade_date, present, value=0.8, minutes=(45, 200, 385))  # no exact 30
    dp = spark_day_path(chain, t)
    assert dp is not None and dp.entry_minute == 45


def test_compare_spark_runs_over_priced_paths():
    t = _spark_trade()
    present = [(722.0, "P"), (717.0, "P"), (748.0, "C"), (753.0, "C")]
    chain = _chain_with(t.trade_date, present, value=0.8)
    dp = spark_day_path(chain, t)
    res = compare_spark([t], [dp])
    assert res["spark_actual"]["n"] == 1
    assert res["spark_actual"]["ev_per_contract"] == 5.0
    assert res["ember_best"] is not None
    assert res["ember_spark_live_config"] is not None


@pytest.mark.integration
def test_load_spark_trades_live():
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL not set")
    trades = load_spark_trades(os.environ["DATABASE_URL"], dt.date(2026, 2, 27), dt.date(2026, 5, 21))
    assert len(trades) >= 10
    t = trades[0]
    assert len(t.legs) == 4
    assert 0 <= t.entry_minute <= 390
