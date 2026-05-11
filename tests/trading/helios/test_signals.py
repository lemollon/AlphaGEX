import pytest
from quant.gex_walls import GammaStrike
from trading.helios.models import HeliosConfig, SpreadType, SkipReason
from trading.helios.signals import generate_signal


def _chain_with_walls(call_wall_strike=505.0, put_support_strike=495.0):
    base = [GammaStrike(strike=490.0 + i, gamma=1.0) for i in range(21)]
    base.append(GammaStrike(strike=call_wall_strike, gamma=10.0))
    base.append(GammaStrike(strike=put_support_strike, gamma=10.0))
    return base


def test_bullish_when_near_put_support():
    cfg = HeliosConfig()
    sig = generate_signal(
        strikes=_chain_with_walls(call_wall_strike=520.0, put_support_strike=499.5),
        spot=500.0, vix=20.0, prophet_advice=None,
        trades_today=0, has_open_position=False, config=cfg,
    )
    assert sig.action == "TRADE"
    assert sig.spread_type == SpreadType.BULL_CALL
    assert sig.long_strike == 500.0
    assert sig.short_strike == 502.0


def test_bearish_when_near_call_wall():
    cfg = HeliosConfig()
    sig = generate_signal(
        strikes=_chain_with_walls(call_wall_strike=500.5, put_support_strike=480.0),
        spot=500.0, vix=20.0, prophet_advice=None,
        trades_today=0, has_open_position=False, config=cfg,
    )
    assert sig.action == "TRADE"
    assert sig.spread_type == SpreadType.BEAR_PUT
    assert sig.long_strike == 500.0
    assert sig.short_strike == 498.0


@pytest.mark.parametrize("vix", [10.0, 14.9, 35.1, 60.0])
def test_skip_vix_out_of_range(vix):
    sig = generate_signal(
        strikes=_chain_with_walls(), spot=500.0, vix=vix, prophet_advice=None,
        trades_today=0, has_open_position=False, config=HeliosConfig(),
    )
    assert sig.action == "SKIP"
    assert sig.skip_reason == SkipReason.VIX_OUT_OF_RANGE


def test_skip_no_major_wall_when_concentration_below_threshold():
    flat = [GammaStrike(strike=490.0 + i, gamma=1.0) for i in range(21)]
    sig = generate_signal(
        strikes=flat, spot=500.0, vix=20.0, prophet_advice=None,
        trades_today=0, has_open_position=False, config=HeliosConfig(),
    )
    assert sig.skip_reason == SkipReason.NO_MAJOR_WALL


def test_skip_not_near_wall():
    sig = generate_signal(
        strikes=_chain_with_walls(call_wall_strike=525.0, put_support_strike=475.0),
        spot=500.0, vix=20.0, prophet_advice=None,
        trades_today=0, has_open_position=False, config=HeliosConfig(),
    )
    assert sig.skip_reason == SkipReason.NOT_NEAR_WALL


def test_skip_already_open():
    sig = generate_signal(
        strikes=_chain_with_walls(put_support_strike=499.5), spot=500.0, vix=20.0, prophet_advice=None,
        trades_today=0, has_open_position=True, config=HeliosConfig(),
    )
    assert sig.skip_reason == SkipReason.ALREADY_OPEN


def test_skip_max_trades_today():
    sig = generate_signal(
        strikes=_chain_with_walls(put_support_strike=499.5), spot=500.0, vix=20.0, prophet_advice=None,
        trades_today=1, has_open_position=False, config=HeliosConfig(),
    )
    assert sig.skip_reason == SkipReason.MAX_TRADES_TODAY


def test_prophet_strong_skip_blocks():
    sig = generate_signal(
        strikes=_chain_with_walls(put_support_strike=499.5), spot=500.0, vix=20.0,
        prophet_advice={"action": "SKIP_TODAY", "confidence": 0.85},
        trades_today=0, has_open_position=False, config=HeliosConfig(),
    )
    assert sig.skip_reason == SkipReason.PROPHET_VETO


def test_prophet_low_confidence_does_not_veto():
    sig = generate_signal(
        strikes=_chain_with_walls(put_support_strike=499.5), spot=500.0, vix=20.0,
        prophet_advice={"action": "SKIP_TODAY", "confidence": 0.5},
        trades_today=0, has_open_position=False, config=HeliosConfig(),
    )
    assert sig.action == "TRADE"


def test_tie_break_prefers_smaller_dollar_distance():
    sig = generate_signal(
        strikes=_chain_with_walls(call_wall_strike=502.0, put_support_strike=499.0),
        spot=500.0, vix=20.0, prophet_advice=None,
        trades_today=0, has_open_position=False, config=HeliosConfig(),
    )
    assert sig.spread_type == SpreadType.BULL_CALL
