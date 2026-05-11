import datetime as dt

from trading.helios.gex_client import GexSnapshot
from trading.helios.models import SetupType, JoshuaConfig
from trading.helios.setups.wall_break import evaluate


def _snap(*, spot=500.0, call_wall=501.0, put_wall=495.0, regime="HIGH_NEGATIVE", sigma=5.0):
    return GexSnapshot(
        symbol="SPY", spot=spot, net_gex=-2.0e9, flip_point=498.0,
        call_wall=call_wall, put_wall=put_wall, vix=22.0, regime=regime,
        sigma_1d_band_width=sigma,
        snapshot_at=dt.datetime.now(dt.timezone.utc),
    )


def test_wall_break_fires_call_when_spot_above_call_wall_by_em_threshold():
    snap = _snap(spot=502.0, call_wall=500.0, sigma=5.0)  # (502-500)/5 = 0.40 > 0.20
    a = evaluate(snap, config=JoshuaConfig())
    assert a is not None
    assert a.setup == SetupType.WALL_BREAK
    assert a.direction == "call"
    assert a.long_strike == 502.0
    assert a.short_strike == 503.0


def test_wall_break_fires_put_when_spot_below_put_wall_by_em_threshold():
    snap = _snap(spot=498.0, put_wall=500.0, sigma=5.0)  # (500-498)/5 = 0.40 > 0.20
    a = evaluate(snap, config=JoshuaConfig())
    assert a is not None
    assert a.direction == "put"
    assert a.long_strike == 498.0
    assert a.short_strike == 497.0


def test_wall_break_skips_when_break_too_shallow():
    snap = _snap(spot=500.5, call_wall=500.0, sigma=5.0)  # (500.5-500)/5 = 0.10 < 0.20
    assert evaluate(snap, config=JoshuaConfig()) is None


def test_wall_break_skips_when_regime_positive():
    snap = _snap(spot=502.0, call_wall=500.0, sigma=5.0, regime="HIGH_POSITIVE")
    assert evaluate(snap, config=JoshuaConfig()) is None


def test_wall_break_skips_when_sigma_zero():
    snap = _snap(spot=502.0, call_wall=500.0, sigma=0.0)
    assert evaluate(snap, config=JoshuaConfig()) is None
