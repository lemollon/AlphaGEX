import datetime as dt
from backtest.ember.models import Quote, MinuteChain, DayChain
from backtest.ember.adapters.base import AdapterConfig
from backtest.ember.adapters.spark import SparkRepresentativeIC


def _synthetic_day():
    """One minute (entry=0) chain around spot=500, strikes 480..520 step 5, both rights."""
    quotes = {}
    spot = 500.0
    for k in range(480, 521, 5):
        # crude prices: ITM intrinsic + 0.5 time value, OTM 0.5..2.0 decaying
        c_intrinsic = max(spot - k, 0.0)
        p_intrinsic = max(k - spot, 0.0)
        c_mid = c_intrinsic + max(2.5 - 0.05 * abs(k - spot), 0.2)
        p_mid = p_intrinsic + max(2.5 - 0.05 * abs(k - spot), 0.2)
        quotes[(float(k), "C")] = Quote(c_mid - 0.1, c_mid + 0.1, c_mid)
        quotes[(float(k), "P")] = Quote(p_mid - 0.1, p_mid + 0.1, p_mid)
    mc = MinuteChain(minute=0, spot=spot, quotes=quotes)
    return DayChain(dt.date(2024, 6, 3), dt.date(2024, 6, 4), {0: mc})


def test_spark_adapter_builds_iron_condor():
    day = _synthetic_day()
    cfg = AdapterConfig(entry_minute=0, short_delta=0.16, wing_width=5.0)
    adapter = SparkRepresentativeIC()
    assert adapter.eligible(day, cfg)
    pos = adapter.build_entry(day, cfg)
    assert pos is not None
    # 4 legs: short put, long put (lower), short call, long call (higher)
    assert len(pos.legs) == 4
    rights = sorted(leg.right for leg in pos.legs)
    assert rights == ["C", "C", "P", "P"]
    # net qty zero (2 short, 2 long)
    assert sum(leg.qty for leg in pos.legs) == 0
    # entry credit positive
    assert pos.entry_credit > 0
    # wings are wing_width away from shorts
    puts = sorted([leg for leg in pos.legs if leg.right == "P"], key=lambda l: l.strike)
    calls = sorted([leg for leg in pos.legs if leg.right == "C"], key=lambda l: l.strike)
    assert puts[0].qty == 1 and puts[1].qty == -1     # long put below short put
    assert calls[1].qty == 1 and calls[0].qty == -1   # long call above short call


def test_spark_adapter_ineligible_when_entry_minute_missing():
    day = _synthetic_day()
    cfg = AdapterConfig(entry_minute=99, short_delta=0.16, wing_width=5.0)
    assert not SparkRepresentativeIC().eligible(day, cfg)
