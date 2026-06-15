#!/usr/bin/env python3
"""
Unit tests for the GEX walls + scale data-quality fix (fix/gex-walls-and-scale).

Covers:
  A. compute_walls() — the shared spot-constrained wall helper:
       - normal case (call wall >= spot, put wall <= spot)
       - sparse / single-strike case must NOT collapse (call_wall != put_wall)
       - all strikes below spot
       - all strikes above spot
  B. Tradier per-1%-move conversion + SIGNED per-strike net in
     calculate_gex_from_chain():
       - net_gex is on the ~per-1%-move scale (raw per-$1 * 0.01)
       - net_gex equals the signed per-strike sum (call_gex - |put_gex|)
       - filter_strikes_to_7day_range never returns call_wall == put_wall
"""

import sys
import importlib.util
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

# Load data/gex_calculator.py directly by file path. We intentionally bypass the
# `data` package __init__ (which eagerly imports pandas-backed fetchers) so these
# pure-math unit tests run without the project's heavy optional dependencies.
_spec = importlib.util.spec_from_file_location(
    "gex_calculator_under_test", _ROOT / "data" / "gex_calculator.py"
)
_gex_calculator = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_gex_calculator)

compute_walls = _gex_calculator.compute_walls
calculate_gex_from_chain = _gex_calculator.calculate_gex_from_chain
filter_strikes_to_7day_range = _gex_calculator.filter_strikes_to_7day_range


# ---------------------------------------------------------------------------
# A. compute_walls()
# ---------------------------------------------------------------------------

def test_compute_walls_normal_case():
    """Call wall is the max-call-gamma strike at/above spot; put wall the
    max-put-gamma strike at/below spot."""
    spot = 600.0
    strikes = [
        {'strike': 590, 'call_gamma': 5, 'put_gamma': 40},
        {'strike': 595, 'call_gamma': 10, 'put_gamma': 30},
        {'strike': 600, 'call_gamma': 20, 'put_gamma': 20},
        {'strike': 605, 'call_gamma': 50, 'put_gamma': 10},   # biggest call (above)
        {'strike': 610, 'call_gamma': 15, 'put_gamma': 5},
        {'strike': 585, 'call_gamma': 2, 'put_gamma': 60},    # biggest put (below)
    ]
    call_wall, put_wall = compute_walls(strikes, spot)
    assert call_wall == 605, f"expected 605, got {call_wall}"
    assert put_wall == 585, f"expected 585, got {put_wall}"
    assert call_wall >= spot
    assert put_wall <= spot
    assert call_wall != put_wall


def test_compute_walls_ignores_bigger_call_below_spot():
    """A huge call gamma BELOW spot must not become the call wall."""
    spot = 600.0
    strikes = [
        {'strike': 580, 'call_gamma': 999, 'put_gamma': 1},   # huge but below spot
        {'strike': 605, 'call_gamma': 10, 'put_gamma': 1},
        {'strike': 595, 'call_gamma': 1, 'put_gamma': 50},
    ]
    call_wall, put_wall = compute_walls(strikes, spot)
    assert call_wall == 605
    assert put_wall == 595
    assert call_wall != put_wall


def test_compute_walls_single_strike_does_not_collapse():
    """Sparse/single-strike data must NOT return call_wall == put_wall."""
    spot = 600.0
    strikes = [{'strike': 600, 'call_gamma': 10, 'put_gamma': 10}]
    call_wall, put_wall = compute_walls(strikes, spot)
    assert call_wall != put_wall, "single-strike chain collapsed to zero-width band"


def test_compute_walls_two_strikes_does_not_collapse():
    spot = 600.0
    strikes = [
        {'strike': 600, 'call_gamma': 10, 'put_gamma': 10},
        {'strike': 605, 'call_gamma': 10, 'put_gamma': 10},
    ]
    call_wall, put_wall = compute_walls(strikes, spot)
    assert call_wall != put_wall


def test_compute_walls_all_below_spot():
    """When every strike is below spot, walls still differ (call falls back to
    nearest above -> none, so overall argmax call; put constrained as normal)."""
    spot = 600.0
    strikes = [
        {'strike': 580, 'call_gamma': 30, 'put_gamma': 10},
        {'strike': 585, 'call_gamma': 5, 'put_gamma': 40},
        {'strike': 590, 'call_gamma': 50, 'put_gamma': 20},
    ]
    call_wall, put_wall = compute_walls(strikes, spot)
    assert call_wall != put_wall
    # put wall is the max-put strike at/below spot
    assert put_wall == 585


def test_compute_walls_all_above_spot():
    spot = 600.0
    strikes = [
        {'strike': 610, 'call_gamma': 30, 'put_gamma': 10},
        {'strike': 615, 'call_gamma': 5, 'put_gamma': 40},
        {'strike': 620, 'call_gamma': 50, 'put_gamma': 20},
    ]
    call_wall, put_wall = compute_walls(strikes, spot)
    assert call_wall != put_wall
    # call wall is the max-call strike at/above spot
    assert call_wall == 620


def test_compute_walls_empty_returns_spot():
    spot = 600.0
    call_wall, put_wall = compute_walls([], spot)
    assert call_wall == spot and put_wall == spot


def test_compute_walls_signed_put_gamma_treated_by_magnitude():
    """v2 emits put gamma as a negative number; magnitude must be used."""
    spot = 600.0
    strikes = [
        {'strike': 590, 'call_gamma': 1, 'put_gamma': -80},   # biggest |put|
        {'strike': 595, 'call_gamma': 1, 'put_gamma': -10},
        {'strike': 605, 'call_gamma': 40, 'put_gamma': -1},
    ]
    call_wall, put_wall = compute_walls(strikes, spot)
    assert put_wall == 590
    assert call_wall == 605


# ---------------------------------------------------------------------------
# B. Tradier per-1%-move conversion + signed net
# ---------------------------------------------------------------------------

SPOT = 600.0
OPTIONS = [
    {'strike': 590, 'gamma': 0.015, 'open_interest': 15000, 'option_type': 'call'},
    {'strike': 595, 'gamma': 0.025, 'open_interest': 25000, 'option_type': 'call'},
    {'strike': 600, 'gamma': 0.040, 'open_interest': 50000, 'option_type': 'call'},
    {'strike': 605, 'gamma': 0.030, 'open_interest': 30000, 'option_type': 'call'},
    {'strike': 610, 'gamma': 0.020, 'open_interest': 20000, 'option_type': 'call'},
    {'strike': 590, 'gamma': 0.020, 'open_interest': 20000, 'option_type': 'put'},
    {'strike': 595, 'gamma': 0.030, 'open_interest': 35000, 'option_type': 'put'},
    {'strike': 600, 'gamma': 0.040, 'open_interest': 45000, 'option_type': 'put'},
    {'strike': 605, 'gamma': 0.025, 'open_interest': 20000, 'option_type': 'put'},
    {'strike': 610, 'gamma': 0.015, 'open_interest': 10000, 'option_type': 'put'},
]


def _raw_per_dollar_net(options, spot):
    """Reproduce the OLD raw per-$1 difference-of-totals for scale comparison."""
    total_call = sum(
        c['gamma'] * c['open_interest'] * 100 * spot ** 2
        for c in options if c['option_type'] == 'call'
    )
    total_put = sum(
        c['gamma'] * c['open_interest'] * 100 * spot ** 2
        for c in options if c['option_type'] == 'put'
    )
    return total_call, total_put


def test_net_gex_is_per_1pct_scale():
    """net_gex should be 1/100th of the raw per-$1 dollar-gamma magnitude."""
    res = calculate_gex_from_chain('SPY', SPOT, OPTIONS)
    total_call_raw, total_put_raw = _raw_per_dollar_net(OPTIONS, SPOT)
    raw_signed = total_call_raw - total_put_raw
    # net_gex is per-1%-move => raw_signed * 0.01
    assert abs(res.net_gex - raw_signed * 0.01) < 1.0, (
        f"net_gex {res.net_gex:.3e} not equal to raw*0.01 {raw_signed * 0.01:.3e}"
    )


def test_net_gex_equals_signed_per_strike_sum():
    """net_gex must equal Sum(per-strike (call_gex - |put_gex|)), not the
    difference of two huge totals."""
    res = calculate_gex_from_chain('SPY', SPOT, OPTIONS)
    per_strike_sum = sum(s['net_gex'] for s in res.strikes_data)
    assert abs(res.net_gex - per_strike_sum) < 1e-3, (
        f"net_gex {res.net_gex} != signed per-strike sum {per_strike_sum}"
    )
    # per-strike net == call_gex + put_gex (put already signed negative)
    for s in res.strikes_data:
        assert abs(s['net_gex'] - (s['call_gex'] + s['put_gex'])) < 1e-6


def test_response_internal_consistency():
    """call_gex + put_gex (put signed negative) should ≈ net_gex within 25%."""
    res = calculate_gex_from_chain('SPY', SPOT, OPTIONS)
    # res.call_gex is positive total, res.put_gex is negative total
    assert abs((res.call_gex + res.put_gex) - res.net_gex) <= 0.25 * abs(res.net_gex) + 1.0


def test_calculate_gex_walls_constrained_and_distinct():
    res = calculate_gex_from_chain('SPY', SPOT, OPTIONS)
    assert res.call_wall >= SPOT
    assert res.put_wall <= SPOT
    assert res.call_wall != res.put_wall


def test_filter_strikes_never_collapses_walls():
    """filter_strikes_to_7day_range must never return call_wall == put_wall,
    even when the 7-day window is so tight only one strike survives."""
    gamma_array = [
        {'strike': 599, 'call_gamma': 5, 'put_gamma': 50},
        {'strike': 600, 'call_gamma': 20, 'put_gamma': 20},
        {'strike': 601, 'call_gamma': 50, 'put_gamma': 5},
    ]
    # Tiny IV -> tiny window -> likely sparse/empty filtered set
    filtered, call_wall, put_wall, lo, hi = filter_strikes_to_7day_range(
        gamma_array, spot_price=600.0, implied_vol=0.0001
    )
    assert call_wall != put_wall, "filter collapsed walls to a zero-width band"


def test_filter_strikes_empty_array_falls_back_to_spot():
    filtered, call_wall, put_wall, lo, hi = filter_strikes_to_7day_range(
        [], spot_price=600.0, implied_vol=0.20
    )
    assert call_wall == 600.0 and put_wall == 600.0


if __name__ == '__main__':
    import pytest
    raise SystemExit(pytest.main([__file__, '-v']))
