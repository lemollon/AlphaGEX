"""Sanity checks for bs_charm."""
import math
import pytest

from quant.bs import DEFAULT_R, bs_charm, _norm_cdf


def _call_delta(spot, strike, t_years, sigma, r=DEFAULT_R):
    sqrt_t = math.sqrt(t_years)
    d1 = (math.log(spot / strike) + (r + 0.5 * sigma * sigma) * t_years) / (sigma * sqrt_t)
    return _norm_cdf(d1)


def _numerical_calendar_time_charm(spot, strike, t_years, sigma, r=DEFAULT_R, eps=1e-6):
    """d(delta)/d(calendar time): delta now vs. delta after eps of calendar
    time has passed, i.e. with eps LESS time remaining to expiry."""
    delta_now = _call_delta(spot, strike, t_years, sigma, r)
    delta_later = _call_delta(spot, strike, t_years - eps, sigma, r)
    return (delta_later - delta_now) / eps


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


@pytest.mark.parametrize("strike", [505.0, 495.0, 500.0, 510.0, 490.0])
def test_bs_charm_matches_numerical_calendar_time_derivative(strike):
    """Regression test for a prior sign-inversion bug: bs_charm must equal
    d(delta)/d(calendar time), not d(delta)/d(time_remaining) (its negative).
    The bug let backtest/skew_signal's charm-based BULL/BEAR gate run
    backwards for ~3 years of simulated trades without any test catching it
    (the pre-existing tests here only checked finiteness/magnitude, never
    sign), producing an unreliable NO-GO verdict."""
    spot, t_years, sigma = 500.0, 5 / 365, 0.20
    expected = _numerical_calendar_time_charm(spot, strike, t_years, sigma)
    actual = bs_charm(spot, strike, t_years, sigma)
    assert actual == pytest.approx(expected, rel=1e-3)


def test_bs_charm_sign_is_not_accidentally_flipped():
    """A cheap, obvious tripwire: OTM call and OTM-put-region charm must
    have opposite signs (they are mirror images of the same d1 formula
    around spot), and neither should be the sign a naive ∂Δ/∂t_years
    (unflipped) implementation would produce."""
    otm_call_charm = bs_charm(spot=500.0, strike=505.0, t_years=1 / 365, sigma=0.20)
    otm_put_region_charm = bs_charm(spot=500.0, strike=495.0, t_years=1 / 365, sigma=0.20)
    assert otm_call_charm < 0
    assert otm_put_region_charm > 0
    assert (otm_call_charm > 0) != (otm_put_region_charm > 0)
