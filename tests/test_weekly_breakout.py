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
