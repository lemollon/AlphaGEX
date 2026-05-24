import datetime as dt
from backtest.blaze_gex_0dte.loader import bars_to_daychain
from backtest.blaze_gex_0dte.reconstruct import build_snapshots, regime_for_net_gex

def test_regime_sign_mapping():
    assert regime_for_net_gex(1.0) == "MODERATE_POSITIVE"
    assert regime_for_net_gex(-1.0) == "MODERATE_NEGATIVE"
    assert regime_for_net_gex(0.0) == "MODERATE_POSITIVE"

def test_build_snapshots_yields_one_per_minute_with_walls():
    rows = [
        (0, 499.0, "C", 1.6, 1.7), (0, 499.0, "P", 0.5, 0.6),
        (0, 500.0, "C", 1.0, 1.1), (0, 500.0, "P", 1.0, 1.1),
        (0, 501.0, "C", 0.5, 0.6), (0, 501.0, "P", 1.6, 1.7),
    ]
    oi = {(499.0,"C"):100,(499.0,"P"):100,(500.0,"C"):5000,
          (500.0,"P"):5000,(501.0,"C"):100,(501.0,"P"):100}
    day = bars_to_daychain(dt.date(2024,3,15), rows, oi)
    snaps = build_snapshots(day)
    assert len(snaps) == 1
    s = snaps[0]
    assert 498.0 < s.spot < 502.0
    assert s.sigma_1d_band_width > 0
    assert s.regime in ("MODERATE_POSITIVE", "MODERATE_NEGATIVE")
    assert s.snapshot_at.tzinfo is not None
