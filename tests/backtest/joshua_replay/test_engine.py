import datetime as dt

from backtest.joshua_replay.engine import replay_day
from trading.helios.gex_client import GexSnapshot
from trading.helios.models import JoshuaConfig
from dataclasses import replace


def _snap(*, spot, net_gex, regime, sigma, ts, call_wall=505.0, put_wall=495.0, flip=500.0):
    return GexSnapshot(
        symbol="SPY", spot=spot, net_gex=net_gex, flip_point=flip,
        call_wall=call_wall, put_wall=put_wall, vix=18.0, regime=regime,
        sigma_1d_band_width=sigma, snapshot_at=ts,
    )


def test_replay_day_no_qualifying_snaps_returns_no_trades():
    # CT base = 9:30 AM (after open), 14:30 UTC
    base = dt.datetime(2026, 5, 1, 14, 30, tzinfo=dt.timezone.utc)
    snaps = [
        _snap(spot=500.0, net_gex=0.5e9, regime="NEUTRAL", sigma=5.0,
              ts=base + dt.timedelta(minutes=i)) for i in range(60)
    ]
    out = replay_day(snaps, config=JoshuaConfig(), spot_mark_provider=lambda **kw: 1.0)
    assert out == []


def test_replay_day_fires_wall_fade_once_when_cap_is_one():
    base = dt.datetime(2026, 5, 1, 14, 30, tzinfo=dt.timezone.utc)
    snaps = [
        _snap(spot=500.0, net_gex=2.0e9, regime="HIGH_POSITIVE", sigma=5.0, call_wall=501.0,
              ts=base + dt.timedelta(minutes=i)) for i in range(60)
    ]
    cfg = replace(JoshuaConfig(), max_trades_per_setup_per_day=1)
    out = replay_day(snaps, config=cfg, spot_mark_provider=lambda **kw: 0.80)
    assert len(out) == 1
    assert out[0].setup == "wall_fade"
    assert out[0].direction == "put"


def test_replay_day_fires_wall_fade_up_to_cap():
    base = dt.datetime(2026, 5, 1, 14, 30, tzinfo=dt.timezone.utc)
    snaps = [
        _snap(spot=500.0, net_gex=2.0e9, regime="HIGH_POSITIVE", sigma=5.0, call_wall=501.0,
              ts=base + dt.timedelta(minutes=i)) for i in range(60)
    ]
    # Default cap is 3
    out = replay_day(snaps, config=JoshuaConfig(), spot_mark_provider=lambda **kw: 0.80)
    assert len(out) == 3
    assert all(t.setup == "wall_fade" for t in out)
