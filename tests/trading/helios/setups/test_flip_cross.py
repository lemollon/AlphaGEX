import datetime as dt

from trading.helios.gex_client import GexSnapshot
from trading.helios.models import SetupType, JoshuaConfig
from trading.helios.setups.flip_cross import evaluate, FlipBuffer


def _snap(*, spot, net_gex, flip=500.0, sigma=5.0, ts=None):
    return GexSnapshot(
        symbol="SPY", spot=spot, net_gex=net_gex, flip_point=flip,
        call_wall=505.0, put_wall=495.0, vix=18.0,
        regime="HIGH_POSITIVE" if net_gex > 0 else "HIGH_NEGATIVE",
        sigma_1d_band_width=sigma,
        snapshot_at=ts or dt.datetime.now(dt.timezone.utc),
    )


def test_flip_cross_fires_call_on_upward_cross_with_regime_flip():
    buf = FlipBuffer(max_minutes=5)
    base = dt.datetime(2026, 5, 11, 14, 0, tzinfo=dt.timezone.utc)
    buf.add(_snap(spot=499.0, net_gex=-1.0e9, ts=base))
    buf.add(_snap(spot=499.2, net_gex=-0.5e9, ts=base + dt.timedelta(minutes=2)))
    now_snap = _snap(spot=501.0, net_gex=1.0e9, ts=base + dt.timedelta(minutes=5))
    a = evaluate(now_snap, buffer=buf, config=JoshuaConfig())
    assert a is not None
    assert a.setup == SetupType.FLIP_CROSS
    assert a.direction == "call"
    assert a.long_strike == 501.0
    assert a.short_strike == 502.0


def test_flip_cross_fires_put_on_downward_cross_with_regime_flip():
    buf = FlipBuffer(max_minutes=5)
    base = dt.datetime(2026, 5, 11, 14, 0, tzinfo=dt.timezone.utc)
    buf.add(_snap(spot=501.0, net_gex=1.0e9, ts=base))
    buf.add(_snap(spot=500.5, net_gex=0.5e9, ts=base + dt.timedelta(minutes=2)))
    now_snap = _snap(spot=499.0, net_gex=-1.0e9, ts=base + dt.timedelta(minutes=5))
    a = evaluate(now_snap, buffer=buf, config=JoshuaConfig())
    assert a is not None
    assert a.direction == "put"


def test_flip_cross_skips_if_no_regime_flip():
    buf = FlipBuffer(max_minutes=5)
    base = dt.datetime(2026, 5, 11, 14, 0, tzinfo=dt.timezone.utc)
    buf.add(_snap(spot=499.0, net_gex=1.0e9, ts=base))
    now_snap = _snap(spot=501.0, net_gex=1.5e9, ts=base + dt.timedelta(minutes=5))
    assert evaluate(now_snap, buffer=buf, config=JoshuaConfig()) is None


def test_flip_cross_skips_if_hysteresis_not_breached():
    buf = FlipBuffer(max_minutes=5)
    base = dt.datetime(2026, 5, 11, 14, 0, tzinfo=dt.timezone.utc)
    buf.add(_snap(spot=500.3, net_gex=-1.0e9, ts=base))
    now_snap = _snap(spot=500.4, net_gex=1.0e9, ts=base + dt.timedelta(minutes=5))
    assert evaluate(now_snap, buffer=buf, config=JoshuaConfig()) is None


def test_flip_cross_skips_if_buffer_too_short():
    buf = FlipBuffer(max_minutes=5)
    base = dt.datetime(2026, 5, 11, 14, 0, tzinfo=dt.timezone.utc)
    buf.add(_snap(spot=499.0, net_gex=-1.0e9, ts=base + dt.timedelta(minutes=3)))
    now_snap = _snap(spot=501.0, net_gex=1.0e9, ts=base + dt.timedelta(minutes=5))
    assert evaluate(now_snap, buffer=buf, config=JoshuaConfig()) is None


def test_flip_buffer_evicts_old_entries():
    buf = FlipBuffer(max_minutes=5)
    base = dt.datetime(2026, 5, 11, 14, 0, tzinfo=dt.timezone.utc)
    buf.add(_snap(spot=499.0, net_gex=-1.0e9, ts=base))
    buf.add(_snap(spot=499.5, net_gex=-0.5e9, ts=base + dt.timedelta(minutes=10)))
    earliest = buf.earliest_within(base + dt.timedelta(minutes=10), minutes=5)
    assert earliest is not None
    assert earliest.spot == 499.5
