"""Characterization/correctness tests for the Black-Scholes pricer used by
/api/spreadworks/calculate (backend/routes.py::_bs_price, _bs_greeks).

Per the SpreadWorks Greeks recon (2026-07-26), these functions back ~20+
call sites across every strategy type /calculate prices (calendars,
butterflies, condors, double diagonals, ...) and had ZERO tests despite
that -- "the only pricing math in the repo is unverified... no regression
net for a refactor." This file is that regression net.

These are plain Black-Scholes, no dividend yield (q=0) -- SPY pays
dividends, so this is a known source of small bias, not a bug. Verified
correct against put-call parity and finite-difference cross-checks before
writing these tests (unlike quant/bs.py::bs_charm, which had an actual
sign-inversion bug caught the same way -- see PR #3219).
"""
from __future__ import annotations

import math

import pytest

from backend.routes import _bs_greeks, _bs_price, _norm_cdf, _norm_pdf

S, K, SIGMA, R = 500.0, 500.0, 0.20, 0.05
T = 10 / 365.0


def test_norm_cdf_known_values():
    assert _norm_cdf(0.0) == pytest.approx(0.5)
    assert _norm_cdf(1.959964) == pytest.approx(0.975, abs=1e-4)


def test_norm_pdf_known_values():
    assert _norm_pdf(0.0) == pytest.approx(1.0 / math.sqrt(2 * math.pi))


@pytest.mark.parametrize("is_call", [True, False])
def test_bs_price_at_expiry_is_intrinsic(is_call):
    assert _bs_price(510.0, 500.0, 0.0, R, SIGMA, is_call) == (10.0 if is_call else 0.0)
    assert _bs_price(490.0, 500.0, 0.0, R, SIGMA, is_call) == (0.0 if is_call else 10.0)


def test_bs_price_put_call_parity():
    call = _bs_price(S, K, T, R, SIGMA, True)
    put = _bs_price(S, K, T, R, SIGMA, False)
    assert call - put == pytest.approx(S - K * math.exp(-R * T), rel=1e-9)


@pytest.mark.parametrize("strike", [480.0, 495.0, 500.0, 505.0, 520.0])
def test_bs_price_matches_numerical_delta(strike):
    """Cross-check _bs_greeks delta against a finite difference of _bs_price
    with respect to spot."""
    eps = 0.01
    for is_call in (True, False):
        numerical = (
            _bs_price(S + eps, strike, T, R, SIGMA, is_call)
            - _bs_price(S - eps, strike, T, R, SIGMA, is_call)
        ) / (2 * eps)
        coded = _bs_greeks(S, strike, T, R, SIGMA, is_call)["delta"]
        assert coded == pytest.approx(numerical, abs=1e-4)


@pytest.mark.parametrize("strike", [480.0, 495.0, 500.0, 505.0, 520.0])
def test_bs_greeks_theta_matches_numerical_calendar_time_decay(strike):
    """Cross-check theta against a finite difference of _bs_price as one
    calendar day passes (T decreases by 1/365) -- the exact kind of
    sign-convention check that would have caught #3219's bs_charm bug."""
    eps = 1 / 365.0
    for is_call in (True, False):
        price_now = _bs_price(S, strike, T, R, SIGMA, is_call)
        price_tomorrow = _bs_price(S, strike, T - eps, R, SIGMA, is_call)
        numerical_theta_per_day = price_tomorrow - price_now
        coded = _bs_greeks(S, strike, T, R, SIGMA, is_call)["theta"]
        assert (coded > 0) == (numerical_theta_per_day > 0)
        assert coded == pytest.approx(numerical_theta_per_day, abs=0.05)


@pytest.mark.parametrize("strike", [480.0, 500.0, 520.0])
def test_bs_greeks_vega_matches_numerical(strike):
    eps = 0.001
    for is_call in (True, False):
        numerical = (
            _bs_price(S, strike, T, R, SIGMA + eps, is_call)
            - _bs_price(S, strike, T, R, SIGMA - eps, is_call)
        ) / (2 * eps) / 100.0
        coded = _bs_greeks(S, strike, T, R, SIGMA, is_call)["vega"]
        assert coded == pytest.approx(numerical, rel=1e-3)


def test_bs_greeks_gamma_same_for_call_and_put():
    g_call = _bs_greeks(S, K, T, R, SIGMA, True)["gamma"]
    g_put = _bs_greeks(S, K, T, R, SIGMA, False)["gamma"]
    assert g_call == pytest.approx(g_put)
    assert g_call > 0


def test_bs_greeks_delta_bounds():
    delta_call = _bs_greeks(S, K, T, R, SIGMA, True)["delta"]
    delta_put = _bs_greeks(S, K, T, R, SIGMA, False)["delta"]
    assert 0.0 <= delta_call <= 1.0
    assert -1.0 <= delta_put <= 0.0
    assert delta_call - delta_put == pytest.approx(1.0)


@pytest.mark.parametrize("is_call", [True, False])
def test_bs_greeks_at_expiry_is_flat(is_call):
    """T<=0 collapses to the documented sentinel: zero gamma/theta/vega,
    delta pinned to ±1/0 by intrinsic value."""
    g = _bs_greeks(510.0, 500.0, 0.0, R, SIGMA, is_call)
    assert g["gamma"] == 0.0
    assert g["theta"] == 0.0
    assert g["vega"] == 0.0


@pytest.mark.parametrize("sigma", [0.05, 0.15, 0.20, 0.35, 0.80])
def test_bs_price_monotonic_in_vol(sigma):
    """Higher IV should never make either leg of a straddle cheaper."""
    base_call = _bs_price(S, K, T, R, 0.01, True)
    base_put = _bs_price(S, K, T, R, 0.01, False)
    call = _bs_price(S, K, T, R, sigma, True)
    put = _bs_price(S, K, T, R, sigma, False)
    assert call >= base_call
    assert put >= base_put
