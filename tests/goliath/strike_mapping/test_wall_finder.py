"""Tests for trading.goliath.strike_mapping.wall_finder.

Synthetic-input math validation. Maps to master spec section 3.1
test 2 ("No wall meeting concentration threshold -> returns None")
plus all internal branches of find_wall.
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from trading.goliath.models import GoliathConfig  # noqa: E402
from trading.goliath.strike_mapping.wall_finder import (  # noqa: E402
    GammaStrike,
    Wall,
    find_wall,
)


def _config(threshold: float = 2.0) -> GoliathConfig:
    return GoliathConfig(
        instance_name="GOLIATH-TEST",
        letf_ticker="TSLL",
        underlying_ticker="TSLA",
        wall_concentration_threshold=threshold,
    )


def _grid(spot: float, gammas: dict[float, float]) -> list[GammaStrike]:
    """Build a strike grid from {strike: gamma} mapping."""
    return [GammaStrike(strike=k, gamma=v) for k, v in gammas.items()]


class HappyPath(unittest.TestCase):
    def test_returns_wall_with_correct_fields(self):
        # Spot 100, local band [95, 105]. Median of {1,1,1,1,1} = 1.0.
        # Threshold = 2.0 * 1.0 = 2.0. Wall at 92 with gamma 5.
        spot = 100.0
        gammas = {92.0: 5.0, 95.0: 1.0, 98.0: 1.0, 100.0: 1.0, 102.0: 1.0, 105.0: 1.0}
        result = find_wall(_grid(spot, gammas), spot, _config())
        self.assertIsInstance(result, Wall)
        self.assertEqual(result.strike, 92.0)
        self.assertEqual(result.gamma, 5.0)
        self.assertAlmostEqual(result.median_local_gamma, 1.0)
        self.assertAlmostEqual(result.concentration_ratio, 5.0)


class GuardClauses(unittest.TestCase):
    def test_empty_strikes_returns_none(self):
        self.assertIsNone(find_wall([], 100.0, _config()))

    def test_zero_spot_returns_none(self):
        self.assertIsNone(find_wall(_grid(100, {100.0: 1.0}), 0.0, _config()))

    def test_negative_spot_returns_none(self):
        self.assertIsNone(find_wall(_grid(100, {100.0: 1.0}), -50.0, _config()))

    def test_no_strikes_in_local_band_returns_none(self):
        # Spot 100, band [95, 105]; only strikes far away.
        gammas = {50.0: 5.0, 200.0: 5.0}
        self.assertIsNone(find_wall(_grid(100.0, gammas), 100.0, _config()))

    def test_non_positive_median_returns_none(self):
        # All local gammas zero -> median is zero -> spec is undefined.
        gammas = {95.0: 0.0, 100.0: 0.0, 105.0: 0.0, 92.0: 5.0}
        self.assertIsNone(find_wall(_grid(100.0, gammas), 100.0, _config()))


class NoQualifyingWall(unittest.TestCase):
    """Spec section 3.1 test 2: no wall meeting concentration threshold."""

    def test_below_spot_strikes_under_threshold_returns_none(self):
        # Median local = 1.0, threshold = 2.0; below-spot gammas only reach 1.5
        spot = 100.0
        gammas = {
            92.0: 1.5, 95.0: 1.0, 98.0: 1.0, 100.0: 1.0, 102.0: 1.0, 105.0: 1.0,
        }
        self.assertIsNone(find_wall(_grid(spot, gammas), spot, _config()))

    def test_threshold_only_met_above_spot_returns_none(self):
        # Wall-sized gamma exists at 108 (above spot) -- must be ignored.
        spot = 100.0
        gammas = {
            95.0: 1.0, 100.0: 1.0, 105.0: 1.0, 108.0: 10.0,
        }
        self.assertIsNone(find_wall(_grid(spot, gammas), spot, _config()))

    def test_negative_gamma_below_spot_ignored(self):
        spot = 100.0
        # Strike at 92 has |gamma| big but it's negative; should not qualify.
        gammas = {
            92.0: -10.0, 95.0: 1.0, 100.0: 1.0, 105.0: 1.0,
        }
        self.assertIsNone(find_wall(_grid(spot, gammas), spot, _config()))


class WallSelection(unittest.TestCase):
    def test_picks_largest_gamma_when_multiple_qualify(self):
        spot = 100.0
        gammas = {
            90.0: 3.0, 92.0: 5.0, 94.0: 4.0,  # all qualify; pick 92 (gamma 5)
            95.0: 1.0, 100.0: 1.0, 105.0: 1.0,
        }
        result = find_wall(_grid(spot, gammas), spot, _config())
        self.assertIsNotNone(result)
        self.assertEqual(result.strike, 92.0)
        self.assertEqual(result.gamma, 5.0)

    def test_exactly_at_threshold_qualifies(self):
        # Threshold is >=, not strict >.
        spot = 100.0
        gammas = {92.0: 2.0, 95.0: 1.0, 100.0: 1.0, 105.0: 1.0}
        result = find_wall(_grid(spot, gammas), spot, _config(threshold=2.0))
        self.assertIsNotNone(result)
        self.assertEqual(result.strike, 92.0)

    def test_higher_threshold_disqualifies_marginal_walls(self):
        spot = 100.0
        gammas = {92.0: 2.5, 95.0: 1.0, 100.0: 1.0, 105.0: 1.0}
        # At threshold 2.0: gamma=2.5 qualifies. At threshold 3.0: it does not.
        self.assertIsNotNone(find_wall(_grid(spot, gammas), spot, _config(2.0)))
        self.assertIsNone(find_wall(_grid(spot, gammas), spot, _config(3.0)))


if __name__ == "__main__":
    unittest.main()
