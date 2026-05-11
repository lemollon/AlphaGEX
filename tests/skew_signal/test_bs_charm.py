"""Sanity checks for bs_charm."""
import math
import pytest

from quant.bs import bs_charm


def test_bs_charm_atm_returns_finite():
    c = bs_charm(spot=500.0, strike=500.0, t_years=1/365, sigma=0.20)
    assert math.isfinite(c)


def test_bs_charm_zero_at_expiry():
    assert bs_charm(500.0, 500.0, 0.0, 0.20) == 0.0


def test_bs_charm_zero_when_sigma_zero():
    assert bs_charm(500.0, 500.0, 1/365, 0.0) == 0.0


def test_bs_charm_finite_otm_call():
    c = bs_charm(spot=500.0, strike=510.0, t_years=1/365, sigma=0.20)
    assert math.isfinite(c)


def test_bs_charm_finite_itm_call():
    c = bs_charm(spot=500.0, strike=490.0, t_years=1/365, sigma=0.20)
    assert math.isfinite(c)
    assert abs(c) < 1000.0
