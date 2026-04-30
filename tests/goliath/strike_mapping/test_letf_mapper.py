"""Tests for trading.goliath.strike_mapping.letf_mapper.

Synthetic-input math validation. Maps to master spec section 3.1
test 7 ("Volatility drag computed correctly for known inputs") and
test 8 ("Tracking error band sensible across multiple sigma values").
"""
from __future__ import annotations

import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from trading.goliath.models import GoliathConfig  # noqa: E402
from trading.goliath.strike_mapping.letf_mapper import (  # noqa: E402
    LETFTarget,
    compute_tracking_error_band,
    compute_vol_drag,
    map_to_letf,
)


def _config(
    leverage: float = 2.0,
    drag_coef: float = 1.0,
    fudge: float = 0.1,
) -> GoliathConfig:
    return GoliathConfig(
        instance_name="GOLIATH-TEST",
        letf_ticker="TSLL",
        underlying_ticker="TSLA",
        leverage=leverage,
        drag_coefficient=drag_coef,
        tracking_error_fudge=fudge,
    )


# Common test inputs: 1-week horizon, sigma 50% annualized, leverage 2x.
_T_WEEK = 7.0 / 365.0
_SIGMA = 0.5


class VolDragMath(unittest.TestCase):
    """Spec section 3.1 test 7: volatility drag for known inputs."""

    def test_known_value_two_x_leverage(self):
        # drag = -0.5 * 2 * 1 * 0.25 * (7/365) * 1.0
        expected = -0.5 * 2.0 * 1.0 * 0.25 * _T_WEEK * 1.0
        self.assertAlmostEqual(compute_vol_drag(2.0, 0.5, _T_WEEK, 1.0), expected)

    def test_zero_drag_at_unleveraged(self):
        # L=1 -> L*(L-1) = 0 -> no drag.
        self.assertEqual(compute_vol_drag(1.0, 0.5, _T_WEEK, 1.0), 0.0)

    def test_scales_with_sigma_squared(self):
        d_low = compute_vol_drag(2.0, 0.2, _T_WEEK, 1.0)
        d_high = compute_vol_drag(2.0, 0.4, _T_WEEK, 1.0)
        # Doubling sigma -> 4x the drag magnitude.
        self.assertAlmostEqual(d_high, d_low * 4.0)

    def test_scales_linearly_with_t(self):
        d_1w = compute_vol_drag(2.0, 0.5, _T_WEEK, 1.0)
        d_2w = compute_vol_drag(2.0, 0.5, 2 * _T_WEEK, 1.0)
        self.assertAlmostEqual(d_2w, d_1w * 2.0)

    def test_scales_with_drag_coefficient(self):
        base = compute_vol_drag(2.0, 0.5, _T_WEEK, 1.0)
        scaled = compute_vol_drag(2.0, 0.5, _T_WEEK, 1.5)
        self.assertAlmostEqual(scaled, base * 1.5)


class TrackingErrorMath(unittest.TestCase):
    """Spec section 3.1 test 8: tracking error band across sigmas."""

    def test_known_value(self):
        # te = 2 * 0.5 * sqrt(7/365) * sqrt(2/3) * 0.1
        expected = 2.0 * 0.5 * math.sqrt(_T_WEEK) * math.sqrt(2.0 / 3.0) * 0.1
        self.assertAlmostEqual(
            compute_tracking_error_band(2.0, 0.5, _T_WEEK, 0.1), expected
        )

    def test_zero_when_sigma_zero(self):
        self.assertEqual(compute_tracking_error_band(2.0, 0.0, _T_WEEK, 0.1), 0.0)

    def test_zero_when_t_zero(self):
        self.assertEqual(compute_tracking_error_band(2.0, 0.5, 0.0, 0.1), 0.0)

    def test_scales_linearly_with_sigma(self):
        te_low = compute_tracking_error_band(2.0, 0.2, _T_WEEK, 0.1)
        te_high = compute_tracking_error_band(2.0, 0.6, _T_WEEK, 0.1)
        self.assertAlmostEqual(te_high, te_low * 3.0)

    def test_scales_with_sqrt_t(self):
        te_1w = compute_tracking_error_band(2.0, 0.5, _T_WEEK, 0.1)
        te_4w = compute_tracking_error_band(2.0, 0.5, 4 * _T_WEEK, 0.1)
        # sqrt(4) = 2, so 4x t -> 2x band.
        self.assertAlmostEqual(te_4w, te_1w * 2.0)

    def test_sensible_across_sigma_values(self):
        # Spec test 8 explicitly: spot-check that band is monotone in sigma
        # and stays bounded for realistic LETF vol values (20%-200%).
        prior = -1.0
        for sigma in [0.2, 0.5, 1.0, 2.0]:
            te = compute_tracking_error_band(2.0, sigma, _T_WEEK, 0.1)
            self.assertGreater(te, prior, f"non-monotone at sigma={sigma}")
            self.assertLess(te, 1.0, f"unrealistic band > 100% at sigma={sigma}")
            prior = te


class MapToLETFIntegration(unittest.TestCase):
    def test_central_target_matches_formula(self):
        # Underlying TSLA at 200, wall at 190 (-5%); LETF TSLL at 10.
        # r_u = -0.05; r_l = 2*(-0.05) + drag.
        cfg = _config()
        result = map_to_letf(
            underlying_wall_price=190.0,
            underlying_spot=200.0,
            letf_spot=10.0,
            sigma_annualized=_SIGMA,
            t_years=_T_WEEK,
            config=cfg,
        )
        expected_drag = compute_vol_drag(2.0, _SIGMA, _T_WEEK, 1.0)
        expected_r_l = 2.0 * (-0.05) + expected_drag
        expected_target = 10.0 * (1.0 + expected_r_l)
        self.assertAlmostEqual(result.target_strike, expected_target)
        self.assertAlmostEqual(result.predicted_letf_return, expected_r_l)
        self.assertAlmostEqual(result.vol_drag, expected_drag)

    def test_band_symmetric_around_target(self):
        cfg = _config()
        result = map_to_letf(190.0, 200.0, 10.0, _SIGMA, _T_WEEK, cfg)
        # band_low = target*(1-te), band_high = target*(1+te) -> midpoint=target
        midpoint = (result.band_low + result.band_high) / 2.0
        self.assertAlmostEqual(midpoint, result.target_strike)

    def test_returns_letf_target_dataclass(self):
        cfg = _config()
        result = map_to_letf(190.0, 200.0, 10.0, _SIGMA, _T_WEEK, cfg)
        self.assertIsInstance(result, LETFTarget)


class GuardClauses(unittest.TestCase):
    def test_zero_underlying_spot_raises(self):
        with self.assertRaises(ValueError):
            map_to_letf(190.0, 0.0, 10.0, _SIGMA, _T_WEEK, _config())

    def test_zero_letf_spot_raises(self):
        with self.assertRaises(ValueError):
            map_to_letf(190.0, 200.0, 0.0, _SIGMA, _T_WEEK, _config())

    def test_negative_sigma_raises(self):
        with self.assertRaises(ValueError):
            map_to_letf(190.0, 200.0, 10.0, -0.1, _T_WEEK, _config())

    def test_negative_t_raises(self):
        with self.assertRaises(ValueError):
            map_to_letf(190.0, 200.0, 10.0, _SIGMA, -0.1, _config())


if __name__ == "__main__":
    unittest.main()
