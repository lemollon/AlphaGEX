"""Black-Scholes pricing, IV solver, and Greeks for SPY-style options.

All functions assume:
  - Continuous compounding for the risk-free rate r (default 5.0% annualized,
    a reasonable approximation for 2023-2025 short-end).
  - No dividend yield (q=0).
  - Time to expiry T in years.
  - American-vs-European is ignored — for SPY options at 1DTE the early
    exercise premium is negligible.

The IV solver uses Newton-Raphson with a Brent fallback. Returns None when:
  - Mid price is below intrinsic value
  - Mid price is above strike + spot (impossible)
  - Newton fails to converge in 30 iterations and Brent finds no root
"""
from __future__ import annotations

import math
from typing import Optional

DEFAULT_R = 0.05  # continuous risk-free rate
SQRT_2PI = math.sqrt(2.0 * math.pi)


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / SQRT_2PI


def bs_price(
    spot: float,
    strike: float,
    t_years: float,
    sigma: float,
    is_call: bool,
    r: float = DEFAULT_R,
) -> float:
    """Black-Scholes European option price."""
    if t_years <= 0 or sigma <= 0:
        # At/past expiry — return intrinsic
        intrinsic = max(spot - strike, 0.0) if is_call else max(strike - spot, 0.0)
        return intrinsic
    sqrt_t = math.sqrt(t_years)
    d1 = (math.log(spot / strike) + (r + 0.5 * sigma * sigma) * t_years) / (sigma * sqrt_t)
    d2 = d1 - sigma * sqrt_t
    if is_call:
        return spot * _norm_cdf(d1) - strike * math.exp(-r * t_years) * _norm_cdf(d2)
    return strike * math.exp(-r * t_years) * _norm_cdf(-d2) - spot * _norm_cdf(-d1)


def bs_vega(
    spot: float,
    strike: float,
    t_years: float,
    sigma: float,
    r: float = DEFAULT_R,
) -> float:
    """Sensitivity to volatility (∂Price/∂sigma). Same for call and put."""
    if t_years <= 0 or sigma <= 0:
        return 0.0
    sqrt_t = math.sqrt(t_years)
    d1 = (math.log(spot / strike) + (r + 0.5 * sigma * sigma) * t_years) / (sigma * sqrt_t)
    return spot * _norm_pdf(d1) * sqrt_t


def bs_gamma(
    spot: float,
    strike: float,
    t_years: float,
    sigma: float,
    r: float = DEFAULT_R,
) -> float:
    """Sensitivity to spot squared (∂²Price/∂spot²). Same for call and put."""
    if t_years <= 0 or sigma <= 0 or spot <= 0:
        return 0.0
    sqrt_t = math.sqrt(t_years)
    d1 = (math.log(spot / strike) + (r + 0.5 * sigma * sigma) * t_years) / (sigma * sqrt_t)
    return _norm_pdf(d1) / (spot * sigma * sqrt_t)


def bs_charm(
    spot: float,
    strike: float,
    t_years: float,
    sigma: float,
    r: float = DEFAULT_R,
) -> float:
    """∂Δ/∂T (per year). Same value for calls and puts under no dividends.

    Returns 0 at/past expiry or when sigma is non-positive (undefined region).
    Sign convention: positive charm means delta increases as time passes.
    """
    if t_years <= 0 or sigma <= 0 or spot <= 0:
        return 0.0
    sqrt_t = math.sqrt(t_years)
    d1 = (math.log(spot / strike) + (r + 0.5 * sigma * sigma) * t_years) / (sigma * sqrt_t)
    return _norm_pdf(d1) * ((r + 0.5 * sigma * sigma) / (sigma * sqrt_t) - d1 / (2.0 * t_years))


def implied_vol(
    market_price: float,
    spot: float,
    strike: float,
    t_years: float,
    is_call: bool,
    r: float = DEFAULT_R,
    initial_sigma: float = 0.30,
    max_iter: int = 30,
    tol: float = 1e-5,
) -> Optional[float]:
    """Newton-Raphson IV solver with intrinsic-value sanity check.

    Returns None if the price is unreasonable (below intrinsic, above bound)
    or solver fails to converge.
    """
    if t_years <= 0:
        return None
    intrinsic = max(spot - strike, 0.0) if is_call else max(strike - spot, 0.0)
    if market_price < intrinsic - 1e-6:
        return None  # arbitrage or stale quote
    upper_bound = strike + spot
    if market_price >= upper_bound:
        return None

    sigma = max(initial_sigma, 1e-3)
    for _ in range(max_iter):
        price = bs_price(spot, strike, t_years, sigma, is_call, r)
        diff = price - market_price
        if abs(diff) < tol:
            return sigma
        v = bs_vega(spot, strike, t_years, sigma, r)
        if v < 1e-8:
            break
        sigma_new = sigma - diff / v
        # Clamp to a reasonable IV range to avoid divergence
        if sigma_new <= 0.001:
            sigma_new = 0.001
        if sigma_new > 5.0:
            sigma_new = 5.0
        if abs(sigma_new - sigma) < tol:
            return sigma_new
        sigma = sigma_new

    # Brent fallback for hard cases
    try:
        return _brent_iv(market_price, spot, strike, t_years, is_call, r)
    except Exception:
        return None


def _brent_iv(
    market_price: float,
    spot: float,
    strike: float,
    t_years: float,
    is_call: bool,
    r: float,
) -> Optional[float]:
    """Brent's method bisection — slower but more robust than Newton."""
    lo, hi = 1e-3, 5.0
    p_lo = bs_price(spot, strike, t_years, lo, is_call, r) - market_price
    p_hi = bs_price(spot, strike, t_years, hi, is_call, r) - market_price
    if p_lo * p_hi > 0:
        return None  # no root in interval
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        p_mid = bs_price(spot, strike, t_years, mid, is_call, r) - market_price
        if abs(p_mid) < 1e-5:
            return mid
        if p_lo * p_mid < 0:
            hi, p_hi = mid, p_mid
        else:
            lo, p_lo = mid, p_mid
    return mid


def derive_spot_from_parity(call_mid: float, put_mid: float, strike: float, t_years: float = 0.0, r: float = DEFAULT_R) -> float:
    """Spot ≈ call - put + strike * exp(-r*T) by put-call parity.

    For 1DTE/0DTE options T is small enough that the discount factor is
    essentially 1, but we include it for correctness.
    """
    return call_mid - put_mid + strike * math.exp(-r * t_years)
