#!/usr/bin/env python3
"""
VALOR RTY Regime-Conviction Gate Tests
======================================

Tests for the paper data-collection gate that suppresses RTY's backtest-negative
regime/conviction buckets while leaving every other ticker untouched.

Rule (from replay of 35,686 closed trades):
  * Right side of regime:  NEGATIVE -> LONG, POSITIVE -> SHORT, NEUTRAL -> LONG
  * Conviction sweet-spot: win_probability in [0.50, 0.60] OR >= 0.70
    (the bot's own 0.60-0.674 band is mis-calibrated and loses money)

Run: pytest tests/test_valor_rty_gate.py -v
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from trading.valor.models import (
    ValorConfig, GammaRegime, TradeDirection, FuturesSignal, SignalSource,
)
from trading.valor.trader import rty_regime_gate_decision


def make_signal(direction, regime, win_probability, ticker="RTY"):
    """Build a minimal but real FuturesSignal carrying the gate's inputs."""
    return FuturesSignal(
        ticker=ticker,
        direction=direction,
        confidence=0.60,
        source=SignalSource.GEX_MEAN_REVERSION,
        current_price=2300.0,
        gamma_regime=regime,
        gex_value=0.0,
        flip_point=2300.0,
        call_wall=2320.0,
        put_wall=2280.0,
        vix=16.0,
        atr=20.0,
        entry_price=2300.0,
        stop_price=2297.5,
        contracts=4,
        win_probability=win_probability,
    )


class TestConfigDefaults:
    def test_config_has_gate_fields(self):
        cfg = ValorConfig()
        assert cfg.rty_regime_gate_enabled is True
        assert cfg.rty_gate_wp_low_min == 0.50
        assert cfg.rty_gate_wp_low_max == 0.60
        assert cfg.rty_gate_wp_high_min == 0.70


class TestNonRtyUntouched:
    @pytest.mark.parametrize("ticker", ["MES", "MNQ", "CL", "NG", "MGC"])
    def test_other_tickers_always_allowed(self, ticker):
        cfg = ValorConfig()
        # Wrong-side + toxic win_prob would block RTY, but must pass for others.
        sig = make_signal(TradeDirection.LONG, GammaRegime.POSITIVE, 0.65, ticker=ticker)
        allowed, reason = rty_regime_gate_decision(ticker, sig, cfg)
        assert allowed is True
        assert reason == ""


class TestRightSideAllowed:
    def test_negative_long_midband(self):
        cfg = ValorConfig()
        sig = make_signal(TradeDirection.LONG, GammaRegime.NEGATIVE, 0.55)
        assert rty_regime_gate_decision("RTY", sig, cfg)[0] is True

    def test_positive_short_midband(self):
        cfg = ValorConfig()
        sig = make_signal(TradeDirection.SHORT, GammaRegime.POSITIVE, 0.55)
        assert rty_regime_gate_decision("RTY", sig, cfg)[0] is True

    def test_neutral_long_midband(self):
        cfg = ValorConfig()
        sig = make_signal(TradeDirection.LONG, GammaRegime.NEUTRAL, 0.55)
        assert rty_regime_gate_decision("RTY", sig, cfg)[0] is True

    def test_negative_long_high_conviction(self):
        cfg = ValorConfig()
        sig = make_signal(TradeDirection.LONG, GammaRegime.NEGATIVE, 0.80)
        assert rty_regime_gate_decision("RTY", sig, cfg)[0] is True


class TestWrongSideBlocked:
    def test_negative_short_blocked(self):
        cfg = ValorConfig()
        sig = make_signal(TradeDirection.SHORT, GammaRegime.NEGATIVE, 0.55)
        allowed, reason = rty_regime_gate_decision("RTY", sig, cfg)
        assert allowed is False
        assert "wrong side" in reason

    def test_positive_long_blocked(self):
        cfg = ValorConfig()
        sig = make_signal(TradeDirection.LONG, GammaRegime.POSITIVE, 0.55)
        allowed, reason = rty_regime_gate_decision("RTY", sig, cfg)
        assert allowed is False
        assert "wrong side" in reason

    def test_neutral_short_blocked(self):
        cfg = ValorConfig()
        sig = make_signal(TradeDirection.SHORT, GammaRegime.NEUTRAL, 0.55)
        assert rty_regime_gate_decision("RTY", sig, cfg)[0] is False


class TestConvictionBands:
    def test_toxic_band_blocked(self):
        """0.60-0.674 is the mis-calibrated money-loser; must be blocked."""
        cfg = ValorConfig()
        sig = make_signal(TradeDirection.LONG, GammaRegime.NEGATIVE, 0.65)
        allowed, reason = rty_regime_gate_decision("RTY", sig, cfg)
        assert allowed is False
        assert "win_prob" in reason

    def test_below_floor_blocked(self):
        cfg = ValorConfig()
        sig = make_signal(TradeDirection.LONG, GammaRegime.NEGATIVE, 0.45)
        assert rty_regime_gate_decision("RTY", sig, cfg)[0] is False

    @pytest.mark.parametrize("wp,expected", [
        (0.50, True),    # lower edge of low band
        (0.60, True),    # upper edge of low band (inclusive)
        (0.6001, False), # just into the toxic band
        (0.699, False),  # just below high band
        (0.70, True),    # high band floor (inclusive)
        (0.95, True),    # well into high band
    ])
    def test_band_boundaries(self, wp, expected):
        cfg = ValorConfig()
        sig = make_signal(TradeDirection.LONG, GammaRegime.NEGATIVE, wp)
        assert rty_regime_gate_decision("RTY", sig, cfg)[0] is expected


class TestGateDisabled:
    def test_disabled_allows_everything(self):
        cfg = ValorConfig()
        cfg.rty_regime_gate_enabled = False
        # Wrong-side + toxic band would normally block — disabled means allow.
        sig = make_signal(TradeDirection.LONG, GammaRegime.POSITIVE, 0.65)
        allowed, reason = rty_regime_gate_decision("RTY", sig, cfg)
        assert allowed is True
        assert reason == ""
