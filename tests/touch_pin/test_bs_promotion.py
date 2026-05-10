"""Sanity checks for the promoted quant.bs module."""
import pytest

from quant.bs import bs_price, bs_gamma, bs_vega, implied_vol, derive_spot_from_parity


def test_atm_call_price_textbook():
    price = bs_price(spot=500.0, strike=500.0, t_years=1/365, sigma=0.20, is_call=True)
    assert 0.5 < price < 5.0


def test_iv_roundtrip():
    sigma_in = 0.25
    price = bs_price(500.0, 505.0, 5/365, sigma_in, is_call=True)
    sigma_out = implied_vol(price, 500.0, 505.0, 5/365, is_call=True)
    assert sigma_out is not None
    assert abs(sigma_out - sigma_in) < 1e-3


def test_iv_below_intrinsic_returns_none():
    iv = implied_vol(market_price=1.0, spot=505.0, strike=500.0, t_years=1/365, is_call=True)
    assert iv is None


def test_parity_spot_recovers_spot():
    spot = 500.0
    K = 500.0
    T = 1/365
    sigma = 0.20
    cm = bs_price(spot, K, T, sigma, is_call=True)
    pm = bs_price(spot, K, T, sigma, is_call=False)
    spot_recovered = derive_spot_from_parity(cm, pm, K, T)
    assert abs(spot_recovered - spot) < 1e-2


def test_gamma_positive_atm():
    g = bs_gamma(500.0, 500.0, 1/365, 0.20)
    assert g > 0


def test_vega_positive_atm():
    v = bs_vega(500.0, 500.0, 1/365, 0.20)
    assert v > 0
