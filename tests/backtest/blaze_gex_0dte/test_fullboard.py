import datetime as dt
from backtest.blaze_gex_0dte.fullboard import compute_eod_gex, EodGex

# rows: (strike, gamma, call_oi, put_oi, underlying_price, call_iv)
def test_compute_eod_gex_positive_regime():
    rows = [
        (495.0, 0.02, 100,  5000, 500.0, 0.20),
        (500.0, 0.04, 2000, 2000, 500.0, 0.25),
        (505.0, 0.02, 8000, 100,  500.0, 0.20),
    ]
    g = compute_eod_gex(rows, dt.date(2024, 3, 15))
    assert isinstance(g, EodGex)
    assert g.spot == 500.0
    assert g.call_wall == 505.0     # max call gamma*OI at/above spot
    assert g.put_wall == 495.0      # max put gamma*OI at/below spot
    assert g.regime == "MODERATE_POSITIVE"   # net (cg-pg) summed > 0
    assert g.sigma_1d_band_width > 0

def test_compute_eod_gex_negative_regime():
    rows = [
        (495.0, 0.02, 100, 9000, 500.0, 0.20),
        (505.0, 0.02, 100, 9000, 500.0, 0.20),
    ]
    g = compute_eod_gex(rows, dt.date(2024, 3, 15))
    assert g.regime == "MODERATE_NEGATIVE"
    assert g.net_gex < 0

def test_compute_eod_gex_empty_returns_none():
    assert compute_eod_gex([], dt.date(2024, 3, 15)) is None
