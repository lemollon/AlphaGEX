import datetime as dt
from types import SimpleNamespace
from backtest.blaze_gex_0dte.loader import bars_to_daychain
from backtest.blaze_gex_0dte.providers import make_providers

def _action(direction, long_strike, short_strike):
    return SimpleNamespace(direction=direction, long_strike=long_strike, short_strike=short_strike)

def _snap(minute):
    return SimpleNamespace(spot=500.0)

def test_debit_is_long_ask_minus_short_bid():
    rows = [
        (0, 500.0, "C", 1.00, 1.20),
        (0, 501.0, "C", 0.40, 0.55),
    ]
    day = bars_to_daychain(dt.date(2024,3,15), rows, {})
    debit_est, _mark = make_providers(day)
    a = _action("call", 500.0, 501.0)
    assert abs(debit_est(_snap(0), a) - (1.20 - 0.40)) < 1e-9

def test_mark_is_long_mid_minus_short_mid():
    rows = [
        (3, 500.0, "C", 1.40, 1.60),
        (3, 501.0, "C", 0.50, 0.70),
    ]
    day = bars_to_daychain(dt.date(2024,3,15), rows, {})
    _debit, mark = make_providers(day)
    a = _action("call", 500.0, 501.0)
    v = mark(snapshot=_snap(3), action=a, minute=3, entry_minute=0, debit=0.9)
    assert abs(v - (1.50 - 0.60)) < 1e-9
