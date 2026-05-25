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

def test_parity_spot_at_minute_recovers_spot():
    from backtest.blaze_gex_0dte.loader import bars_to_daychain
    from backtest.blaze_gex_0dte.fullboard import parity_spot_at_minute
    rows = [
        (0, 499.0, "C", 1.6, 1.7), (0, 499.0, "P", 0.5, 0.6),
        (0, 500.0, "C", 1.0, 1.1), (0, 500.0, "P", 1.0, 1.1),
        (0, 501.0, "C", 0.5, 0.6), (0, 501.0, "P", 1.6, 1.7),
    ]
    day = bars_to_daychain(dt.date(2024, 3, 15), rows, {})
    spot = parity_spot_at_minute(day, 0)
    assert spot is not None and 498.0 < spot < 502.0

def test_build_fullboard_snapshots_uses_eod_walls_not_local():
    from backtest.blaze_gex_0dte.loader import bars_to_daychain
    from backtest.blaze_gex_0dte.fullboard import build_fullboard_snapshots, EodGex
    from backtest.joshua_replay.engine import _minutes_since_open_ct
    rows = []
    for m in (0, 120):
        rows += [
            (m, 499.0, "C", 1.6, 1.7), (m, 499.0, "P", 0.5, 0.6),
            (m, 500.0, "C", 1.0, 1.1), (m, 500.0, "P", 1.0, 1.1),
            (m, 501.0, "C", 0.5, 0.6), (m, 501.0, "P", 1.6, 1.7),
        ]
    day = bars_to_daychain(dt.date(2024, 3, 15), rows, {})
    eod = EodGex(trade_date=dt.date(2024, 3, 15), spot=500.0, net_gex=12345.0,
                 call_wall=510.0, put_wall=490.0, flip_point=500.0,
                 regime="MODERATE_POSITIVE", sigma_1d_band_width=5.0)
    snaps = build_fullboard_snapshots(day, eod)
    assert len(snaps) == 2
    for s in snaps:
        assert s.call_wall == 510.0 and s.put_wall == 490.0   # from EOD, not local
        assert s.regime == "MODERATE_POSITIVE"
        assert s.sigma_1d_band_width == 5.0
        assert 498.0 < s.spot < 502.0                          # intraday parity spot
    assert sorted(_minutes_since_open_ct(s.snapshot_at) for s in snaps) == [0, 120]

def test_replay_daychain_fullboard_returns_list():
    from backtest.blaze_gex_0dte.loader import bars_to_daychain
    from backtest.blaze_gex_0dte.fullboard import replay_daychain_fullboard, EodGex
    from trading.helios.models import JoshuaConfig
    rows = []
    for m in range(0, 6):
        rows += [
            (m, 499.0, "C", 1.6, 1.7), (m, 499.0, "P", 0.5, 0.6),
            (m, 500.0, "C", 1.0, 1.1), (m, 500.0, "P", 1.0, 1.1),
            (m, 501.0, "C", 0.5, 0.6), (m, 501.0, "P", 1.6, 1.7),
        ]
    day = bars_to_daychain(dt.date(2024, 3, 15), rows, {})
    eod = EodGex(trade_date=dt.date(2024, 3, 15), spot=500.0, net_gex=1.0,
                 call_wall=510.0, put_wall=490.0, flip_point=500.0,
                 regime="MODERATE_POSITIVE", sigma_1d_band_width=5.0)
    out = replay_daychain_fullboard(day, eod, JoshuaConfig())
    assert isinstance(out, list)
