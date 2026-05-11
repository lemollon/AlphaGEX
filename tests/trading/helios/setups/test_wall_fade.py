import datetime as dt

from trading.helios.gex_client import GexSnapshot
from trading.helios.models import SetupType, JoshuaConfig
from trading.helios.setups.wall_fade import evaluate


def _snap(*, spot=500.0, call_wall=501.0, put_wall=495.0, regime="HIGH_POSITIVE", sigma=5.0):
    return GexSnapshot(
        symbol="SPY",
        spot=spot,
        net_gex=2.0e9,
        flip_point=498.0,
        call_wall=call_wall,
        put_wall=put_wall,
        vix=18.0,
        regime=regime,
        sigma_1d_band_width=sigma,
        snapshot_at=dt.datetime.now(dt.timezone.utc),
    )


def test_wall_fade_fires_put_when_spot_near_call_wall():
    snap = _snap(spot=500.0, call_wall=501.0, sigma=5.0)  # (501-500)/5 = 0.20 < 0.30
    action = evaluate(snap, config=JoshuaConfig())
    assert action is not None
    assert action.setup == SetupType.WALL_FADE
    assert action.direction == "put"
    assert action.long_strike == 500.0
    assert action.short_strike == 499.0


def test_wall_fade_fires_call_when_spot_near_put_wall():
    snap = _snap(spot=496.0, put_wall=495.0, sigma=5.0)  # (496-495)/5 = 0.20 < 0.30
    action = evaluate(snap, config=JoshuaConfig())
    assert action is not None
    assert action.direction == "call"
    assert action.long_strike == 496.0
    assert action.short_strike == 497.0


def test_wall_fade_skips_when_spot_far_from_wall():
    snap = _snap(spot=500.0, call_wall=510.0, put_wall=490.0, sigma=5.0)
    assert evaluate(snap, config=JoshuaConfig()) is None


def test_wall_fade_skips_when_regime_not_positive():
    snap = _snap(spot=500.0, call_wall=501.0, sigma=5.0, regime="MODERATE_NEGATIVE")
    assert evaluate(snap, config=JoshuaConfig()) is None


def test_wall_fade_skips_when_sigma_zero():
    snap = _snap(spot=500.0, call_wall=501.0, sigma=0.0)
    assert evaluate(snap, config=JoshuaConfig()) is None


def test_wall_fade_picks_closer_wall_when_both_near():
    snap = _snap(spot=500.0, call_wall=501.0, put_wall=499.0, sigma=10.0)
    action = evaluate(snap, config=JoshuaConfig())
    assert action.direction == "put"
