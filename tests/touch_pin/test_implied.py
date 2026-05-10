"""Tests for backtest.touch_pin.implied."""
import pytest

from backtest.touch_pin.vehicle import VerticalSpec
from backtest.touch_pin.implied import implied_pin_probabilities, ImpliedProbs
from quant.bs import bs_price


def make_call_vertical(spot, long_K, short_K, sigma, t):
    long_mid = bs_price(spot, long_K, t, sigma, is_call=True)
    short_mid = bs_price(spot, short_K, t, sigma, is_call=True)
    return VerticalSpec(
        side="PIN-CALL", long_K=long_K, short_K=short_K, width=short_K - long_K,
        entry_mid=long_mid - short_mid,
        long_bid=long_mid - 0.01, long_ask=long_mid + 0.01,
        short_bid=short_mid - 0.01, short_ask=short_mid + 0.01,
    )


def test_implied_methods_agree_synthetic():
    spec = make_call_vertical(spot=500.0, long_K=500.0, short_K=501.0, sigma=0.20, t=1/365)
    probs = implied_pin_probabilities(spec, spot=500.0, t_years=1/365)
    assert probs is not None
    assert abs(probs.method_bs_d2 - probs.method_price_over_width) < 0.05


def test_implied_far_otm_low_prob():
    spec = make_call_vertical(spot=500.0, long_K=520.0, short_K=521.0, sigma=0.20, t=1/365)
    probs = implied_pin_probabilities(spec, spot=500.0, t_years=1/365)
    assert probs.method_bs_d2 < 0.10
    assert probs.method_price_over_width < 0.10


def test_implied_returns_clamped_when_iv_solver_fails():
    # Vertical with crazy entry_mid → IV solver fails on long leg
    spec = VerticalSpec(
        side="PIN-CALL", long_K=500.0, short_K=501.0, width=1.0,
        entry_mid=999.0,
        long_bid=998.0, long_ask=1000.0,
        short_bid=0.0, short_ask=0.01,
    )
    probs = implied_pin_probabilities(spec, spot=500.0, t_years=1/365)
    assert probs is not None
    assert 0.0 <= probs.method_price_over_width <= 1.0


def test_implied_put_method1_uses_negative_d2():
    spec = VerticalSpec(
        side="PIN-PUT", long_K=500.0, short_K=499.0, width=1.0,
        entry_mid=0.45,
        long_bid=0.50, long_ask=0.55,
        short_bid=0.05, short_ask=0.07,
    )
    probs = implied_pin_probabilities(spec, spot=500.0, t_years=1/365)
    assert probs is not None
    assert 0.0 <= probs.method_bs_d2 <= 1.0
