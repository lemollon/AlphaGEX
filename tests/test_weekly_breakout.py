"""168h breakout strategy module + XRP wiring."""
from types import SimpleNamespace
from unittest.mock import patch

from trading.perp_strategies import weekly_breakout as wb


def _flat(n, price=1.0, rng=0.01):
    return [{"ts": i * 3600, "o": price, "h": price + rng, "l": price - rng, "c": price} for i in range(n)]


def test_breakout_up_down_and_none():
    c = _flat(200)
    assert wb.evaluate(c).direction == 0
    up = c + [{"ts": 200 * 3600, "o": 1.0, "h": 1.05, "l": 1.0, "c": 1.04}]
    s = wb.evaluate(up)
    assert s.direction == 1 and s.reason == "BREAKOUT_UP" and s.atr > 0 and s.candle_ts == 200 * 3600
    down = c + [{"ts": 200 * 3600, "o": 1.0, "h": 1.0, "l": 0.95, "c": 0.96}]
    assert wb.evaluate(down).direction == -1


def test_insufficient_history_waits():
    assert wb.evaluate(_flat(100)).reason.startswith("INSUFFICIENT_CANDLES")


def test_long_trail_tightens_never_loosens_and_exits():
    entry, atr = 1.0, 0.01
    sl = wb.initial_stop(entry, 1, atr, 2.5)  # 0.975
    close, _, stop = wb.exit_decision("long", entry, sl, None, best_price=1.05, price=1.04, stop_atr=2.5, trail_atr=2.0)
    assert not close and abs(stop - 1.03) < 1e-9          # 1.05 - 2*0.01
    close, _, stop2 = wb.exit_decision("long", entry, sl, stop, best_price=1.05, price=1.035, stop_atr=2.5, trail_atr=2.0)
    assert not close and stop2 == stop                     # does not loosen
    close, reason, _ = wb.exit_decision("long", entry, sl, stop, best_price=1.05, price=1.029, stop_atr=2.5, trail_atr=2.0)
    assert close and reason == "WB_TRAIL_STOP"


def test_short_initial_stop_hit():
    entry, atr = 1.0, 0.01
    sl = wb.initial_stop(entry, -1, atr, 2.5)  # 1.025
    close, reason, _ = wb.exit_decision("short", entry, sl, None, best_price=1.0, price=1.026, stop_atr=2.5, trail_atr=2.0)
    assert close and reason == "WB_STOP"


def test_xrp_signal_uses_breakout_sizes_to_atr_stop_and_acts_once_per_candle():
    from trading.agape_xrp_perp.models import AgapeXrpPerpConfig, SignalAction
    from trading.agape_xrp_perp.signals import AgapeXrpPerpSignalGenerator

    cfg = AgapeXrpPerpConfig()
    assert cfg.strategy_mode == "weekly_breakout" and cfg.max_open_positions == 1
    gen = AgapeXrpPerpSignalGenerator.__new__(AgapeXrpPerpSignalGenerator)
    gen.config = cfg
    candles = _flat(200) + [{"ts": 200 * 3600, "o": 1.0, "h": 1.05, "l": 1.0, "c": 1.04}]
    md = {"spot_price": 1.04, "funding_regime": "BALANCED", "funding_rate": 0.001}
    with patch.object(gen, "get_market_data", return_value=md), \
         patch("trading.perp_strategies.weekly_breakout.fetch_hourly_candles", return_value=candles):
        s1 = gen.generate_signal(prophet_data={"advice": "UNAVAILABLE"})
        s2 = gen.generate_signal(prophet_data={"advice": "UNAVAILABLE"})
    assert s1.action == SignalAction.LONG and s1.is_valid
    assert s1.stop_loss < 1.04 and s1.take_profit is None
    assert s2.action == SignalAction.WAIT and s2.reasoning == "WB_ALREADY_ACTED_THIS_CANDLE"


def test_xrp_signal_waits_when_candles_unavailable():
    from trading.agape_xrp_perp.models import AgapeXrpPerpConfig, SignalAction
    from trading.agape_xrp_perp.signals import AgapeXrpPerpSignalGenerator

    gen = AgapeXrpPerpSignalGenerator.__new__(AgapeXrpPerpSignalGenerator)
    gen.config = AgapeXrpPerpConfig()
    with patch.object(gen, "get_market_data", return_value={"spot_price": 1.0}), \
         patch("trading.perp_strategies.weekly_breakout.fetch_hourly_candles", side_effect=RuntimeError("down")):
        s = gen.generate_signal(prophet_data={})
    assert s.action == SignalAction.WAIT and s.reasoning.startswith("WB_CANDLES_UNAVAILABLE")


def test_session_window_wraps_midnight():
    h = lambda hour: hour * 3600
    assert wb.in_session(h(22), 22, 12) and wb.in_session(h(23), 22, 12)
    assert wb.in_session(h(0), 22, 12) and wb.in_session(h(9), 22, 12)
    assert not wb.in_session(h(10), 22, 12) and not wb.in_session(h(21), 22, 12)
    assert wb.in_session(h(15), 22, 24)


def test_breakout_outside_session_waits():
    from trading.agape_xrp_perp.models import AgapeXrpPerpConfig, SignalAction
    from trading.agape_xrp_perp.signals import AgapeXrpPerpSignalGenerator

    gen = AgapeXrpPerpSignalGenerator.__new__(AgapeXrpPerpSignalGenerator)
    gen.config = AgapeXrpPerpConfig()
    base = _flat(206)  # breakout candle index 206 -> 14:00 UTC, outside 22-10
    candles = base + [{"ts": 206 * 3600, "o": 1.0, "h": 1.05, "l": 1.0, "c": 1.04}]
    with patch.object(gen, "get_market_data", return_value={"spot_price": 1.04}), \
         patch("trading.perp_strategies.weekly_breakout.fetch_hourly_candles", return_value=candles):
        s = gen.generate_signal(prophet_data={})
    assert s.action == SignalAction.WAIT and s.reasoning == "WB_OUTSIDE_SESSION_SHADOWED"
    # Next scan while the shadow is still open: blocked even by a fresh in-session breakout.
    later = candles + [{"ts": 207 * 3600, "o": 1.04, "h": 1.06, "l": 1.04, "c": 1.055}]
    with patch.object(gen, "get_market_data", return_value={"spot_price": 1.055}), \
         patch("trading.perp_strategies.weekly_breakout.fetch_hourly_candles", return_value=later):
        s2 = gen.generate_signal(prophet_data={})
    assert s2.reasoning == "WB_SHADOW_ACTIVE"
    # Price collapses through the shadow's stop -> shadow closes, bot free again.
    crash = later + [{"ts": 208 * 3600, "o": 1.0, "h": 1.0, "l": 0.90, "c": 0.91}]
    with patch.object(gen, "get_market_data", return_value={"spot_price": 0.91}), \
         patch("trading.perp_strategies.weekly_breakout.fetch_hourly_candles", return_value=crash):
        s3 = gen.generate_signal(prophet_data={})
    # The long shadow is stopped out; the crash is itself an out-of-session
    # downside breakout, so a new short shadow replaces it.
    assert s3.reasoning == "WB_OUTSIDE_SESSION_SHADOWED"
    assert gen._wb_shadow["side"] == "short" and gen._wb_shadow["entry"] == 0.91


def test_shib_uses_breakout_with_full_precision_stop():
    from trading.agape_shib_perp.models import AgapeShibPerpConfig, SignalAction
    from trading.agape_shib_perp.signals import AgapeShibPerpSignalGenerator

    cfg = AgapeShibPerpConfig()
    assert cfg.strategy_mode == "weekly_breakout" and cfg.max_open_positions == 1
    gen = AgapeShibPerpSignalGenerator.__new__(AgapeShibPerpSignalGenerator)
    gen.config = cfg
    p = 0.000012
    candles = _flat(200, price=p, rng=p * 0.005) + [
        {"ts": 200 * 3600, "o": p, "h": p * 1.05, "l": p, "c": p * 1.04}]
    with patch.object(gen, "get_market_data", return_value={"spot_price": p * 1.04}), \
         patch("trading.perp_strategies.weekly_breakout.fetch_hourly_candles", return_value=candles):
        s = gen.generate_signal(prophet_data={})
    assert s.action == SignalAction.LONG and 0 < s.stop_loss < p * 1.04
    assert s.quantity > 0


def test_manage_open_position_closes_on_stop_and_updates_trail():
    from datetime import datetime, timezone

    closed, updates = [], []
    trader = SimpleNamespace(
        config=SimpleNamespace(wb_stop_atr=2.5, wb_trail_atr=2.0, wb_max_hold_hours=72),
        db=SimpleNamespace(_execute=lambda sql, params: updates.append(params)),
        _close_position=lambda pos, price, reason: closed.append(reason) or True,
    )
    now = datetime.now(timezone.utc)
    pos = {"position_id": "p1", "side": "long", "entry_price": 1.0, "stop_loss": 0.975,
           "current_stop": None, "high_water_mark": 1.05, "open_time": now.isoformat()}
    assert wb.manage_open_position(trader, "t", pos, 1.04, now, timezone.utc) is False
    assert abs(updates[-1][0] - 1.03) < 1e-9
    pos["current_stop"] = updates[-1][0]
    assert wb.manage_open_position(trader, "t", pos, 1.02, now, timezone.utc) is True
    assert closed == ["WB_TRAIL_STOP"]


import pytest


@pytest.mark.parametrize("coin,price", [("btc", 84000.0), ("doge", 0.21)])
def test_btc_doge_use_breakout(coin, price):
    import importlib
    models = importlib.import_module(f"trading.agape_{coin}_perp.models")
    signals = importlib.import_module(f"trading.agape_{coin}_perp.signals")
    cfg_cls = next(getattr(models, n) for n in dir(models) if n.startswith("Agape") and n.endswith("PerpConfig"))
    gen_cls = next(getattr(signals, n) for n in dir(signals) if n.endswith("SignalGenerator"))
    cfg = cfg_cls()
    assert cfg.strategy_mode == "weekly_breakout" and cfg.max_open_positions == 1
    gen = gen_cls.__new__(gen_cls)
    gen.config = cfg
    candles = _flat(200, price=price, rng=price * 0.005) + [
        {"ts": 200 * 3600, "o": price, "h": price * 1.05, "l": price, "c": price * 1.04}]
    with patch.object(gen, "get_market_data", return_value={"spot_price": price * 1.04}), \
         patch("trading.perp_strategies.weekly_breakout.fetch_hourly_candles", return_value=candles):
        s = gen.generate_signal(prophet_data={})
    assert s.action == models.SignalAction.LONG and s.is_valid
    assert 0 < s.stop_loss < price * 1.04 and s.quantity > 0
