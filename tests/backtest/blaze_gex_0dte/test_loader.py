import datetime as dt
from backtest.blaze_gex_0dte.loader import DayChain, bars_to_daychain

def test_bars_to_daychain_groups_by_minute_and_strike():
    rows = [
        (0, 500.0, "C", 1.00, 1.10),
        (0, 500.0, "P", 0.90, 1.00),
        (0, 501.0, "C", 0.50, 0.60),
        (1, 500.0, "C", 1.05, 1.15),
    ]
    oi = {(500.0, "C"): 1000, (500.0, "P"): 800, (501.0, "C"): 500}
    day = bars_to_daychain(dt.date(2024, 3, 15), rows, oi)
    assert day.minutes() == [0, 1]
    assert day.mid(0, 500.0, "C") == 1.05
    assert day.oi[(500.0, "C")] == 1000
    assert day.mid(1, 501.0, "C") is None
