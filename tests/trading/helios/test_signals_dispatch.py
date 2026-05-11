"""Dispatcher tests: flip_cross > wall_break > wall_fade ordering."""
import datetime as dt

from trading.helios.gex_client import GexSnapshot
from trading.helios.models import DailyState, SetupType, JoshuaConfig
from trading.helios.setups.flip_cross import FlipBuffer
from trading.helios.signals import dispatch


def _snap(**kw):
    defaults = dict(
        symbol="SPY", spot=500.0, net_gex=2.0e9, flip_point=499.0,
        call_wall=501.0, put_wall=495.0, vix=18.0, regime="HIGH_POSITIVE",
        sigma_1d_band_width=5.0,
        snapshot_at=dt.datetime(2026, 5, 11, 14, 0, tzinfo=dt.timezone.utc),
    )
    defaults.update(kw)
    return GexSnapshot(**defaults)


def test_dispatch_returns_none_when_no_setup_qualifies():
    snap = _snap(spot=500.0, call_wall=520.0, put_wall=480.0, regime="NEUTRAL")
    state = DailyState(trade_date=dt.date(2026, 5, 11))
    buf = FlipBuffer()
    action = dispatch(snap, state=state, buffer=buf, config=JoshuaConfig())
    assert action is None


def test_dispatch_skips_setups_already_fired_today():
    snap = _snap(spot=500.0, call_wall=501.0, regime="HIGH_POSITIVE", sigma_1d_band_width=5.0)
    state = DailyState(trade_date=dt.date(2026, 5, 11), wall_fade_fired=True)
    buf = FlipBuffer()
    action = dispatch(snap, state=state, buffer=buf, config=JoshuaConfig())
    assert action is None


def test_dispatch_prefers_flip_cross_when_multiple_qualify():
    buf = FlipBuffer(max_minutes=5)
    base = dt.datetime(2026, 5, 11, 14, 0, tzinfo=dt.timezone.utc)
    past = _snap(spot=499.0, net_gex=-1.0e9, regime="HIGH_NEGATIVE",
                 flip_point=500.0, call_wall=501.0, sigma_1d_band_width=5.0,
                 snapshot_at=base)
    buf.add(past)
    now_snap = _snap(spot=501.0, net_gex=1.0e9, regime="HIGH_POSITIVE",
                     flip_point=500.0, call_wall=502.0, sigma_1d_band_width=5.0,
                     snapshot_at=base + dt.timedelta(minutes=5))
    state = DailyState(trade_date=dt.date(2026, 5, 11))
    action = dispatch(now_snap, state=state, buffer=buf, config=JoshuaConfig())
    assert action is not None
    assert action.setup == SetupType.FLIP_CROSS


def test_dispatch_wall_fade_when_only_qualifier():
    snap = _snap(spot=500.0, call_wall=501.0, regime="HIGH_POSITIVE", sigma_1d_band_width=5.0)
    state = DailyState(trade_date=dt.date(2026, 5, 11))
    action = dispatch(snap, state=state, buffer=FlipBuffer(), config=JoshuaConfig())
    assert action is not None
    assert action.setup == SetupType.WALL_FADE


def test_dispatch_wall_break_when_only_qualifier():
    snap = _snap(spot=502.0, call_wall=500.0, regime="HIGH_NEGATIVE", sigma_1d_band_width=5.0)
    state = DailyState(trade_date=dt.date(2026, 5, 11))
    action = dispatch(snap, state=state, buffer=FlipBuffer(), config=JoshuaConfig())
    assert action is not None
    assert action.setup == SetupType.WALL_BREAK
