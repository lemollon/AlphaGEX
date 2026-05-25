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

def test_snapshot_minute_roundtrips_through_engine_in_both_seasons():
    """The replay engine derives the bar-minute from snapshot_at via a FIXED
    -5h offset (not DST-aware). reconstruct must encode snapshot_at so that
    derivation recovers the loader's bar-minute in EST *and* EDT, or the PT/SL
    mark lookups mis-map ~4 months/year."""
    from backtest.joshua_replay.engine import _minutes_since_open_ct
    def _chain(minutes):
        rows = []
        for m in minutes:
            rows += [
                (m, 499.0, "C", 1.6, 1.7), (m, 499.0, "P", 0.5, 0.6),
                (m, 500.0, "C", 1.0, 1.1), (m, 500.0, "P", 1.0, 1.1),
                (m, 501.0, "C", 0.5, 0.6), (m, 501.0, "P", 1.6, 1.7),
            ]
        oi = {(499.0,"C"):100,(499.0,"P"):100,(500.0,"C"):5000,
              (500.0,"P"):5000,(501.0,"C"):100,(501.0,"P"):100}
        return rows, oi
    for d in (dt.date(2024, 1, 15), dt.date(2024, 7, 15)):  # EST then EDT
        rows, oi = _chain([0, 120])
        snaps = build_snapshots(bars_to_daychain(d, rows, oi))
        recovered = sorted(_minutes_since_open_ct(s.snapshot_at) for s in snaps)
        assert recovered == [0, 120], f"{d}: got {recovered}"
