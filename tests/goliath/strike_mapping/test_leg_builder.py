"""Tests for trading.goliath.strike_mapping.leg_builder.

Synthetic-input validation. Maps to master spec section 3.1 tests:
    #9  short put strike respects "below central target" rule
    #10 long call strike respects "above central target" rule
    #11 long put is correctly 1 strike below short put
    #12 edge case: short put is lowest available strike -> None
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from trading.goliath.models import GoliathConfig  # noqa: E402
from trading.goliath.strike_mapping.leg_builder import (  # noqa: E402
    ThreeLegStructure,
    build_legs,
)
from trading.goliath.strike_mapping.letf_mapper import LETFTarget  # noqa: E402


def _config() -> GoliathConfig:
    return GoliathConfig(
        instance_name="GOLIATH-TEST",
        letf_ticker="TSLL",
        underlying_ticker="TSLA",
    )


def _target(
    target_strike: float = 9.0,
    band_low: float = 8.5,
    band_high: float = 9.5,
) -> LETFTarget:
    """Build an LETFTarget for tests with sensible defaults.

    Default: target $9 with band [$8.5, $9.5] (assuming LETF spot ~$10).
    """
    return LETFTarget(
        target_strike=target_strike,
        band_low=band_low,
        band_high=band_high,
        predicted_letf_return=-0.10,
        vol_drag=-0.001,
        te_band=(band_high - target_strike) / target_strike,
    )


# Standard $0.50-step LETF strike grid around $10 spot.
_STRIKE_GRID = [
    7.0, 7.5, 8.0, 8.5, 9.0, 9.5, 10.0, 10.5, 11.0,
    11.5, 12.0, 12.5, 13.0, 13.5, 14.0,
]


class HappyPath(unittest.TestCase):
    def test_returns_three_leg_structure_with_correct_strikes(self):
        # target=$9 (band [8.5,9.5]), spot=$10
        # short_put = highest in [8.5, 9.0] = $9.0
        # long_put  = next-below $9.0 = $8.5
        # long_call = closest to 20% OTM ($12), in [15%,25%] = [11.5,12.5] => $12
        result = build_legs(_target(), _STRIKE_GRID, letf_spot=10.0, config=_config())
        self.assertIsInstance(result, ThreeLegStructure)
        self.assertEqual(result.short_put_strike, 9.0)
        self.assertEqual(result.long_put_strike, 8.5)
        self.assertEqual(result.long_call_strike, 12.0)
        self.assertAlmostEqual(result.put_spread_width, 0.5)


class ShortPutBelowTarget(unittest.TestCase):
    """Spec section 3.1 test 9: short put respects 'below central target'."""

    def test_short_put_is_at_or_below_target(self):
        result = build_legs(_target(target_strike=9.0), _STRIKE_GRID, 10.0, _config())
        self.assertIsNotNone(result)
        self.assertLessEqual(result.short_put_strike, 9.0)

    def test_picks_highest_strike_at_or_below_target(self):
        # Target between $9.0 and $9.5 -> highest qualifier is $9.0
        result = build_legs(
            _target(target_strike=9.4, band_low=8.5),
            _STRIKE_GRID, 10.0, _config(),
        )
        self.assertIsNotNone(result)
        self.assertEqual(result.short_put_strike, 9.0)

    def test_short_put_must_be_at_or_above_band_low(self):
        # No strike in [9.5, 9.7]; no qualifier -> None.
        # Use a target/band that lies entirely between grid strikes.
        narrow = _target(target_strike=9.7, band_low=9.6, band_high=9.8)
        self.assertIsNone(build_legs(narrow, _STRIKE_GRID, 10.0, _config()))


class LongPutOneStrikeBelow(unittest.TestCase):
    """Spec section 3.1 test 11: long put is exactly 1 strike below short put."""

    def test_long_put_is_strike_immediately_below_short_put(self):
        result = build_legs(_target(), _STRIKE_GRID, 10.0, _config())
        self.assertIsNotNone(result)
        # In a sorted grid, long_put should be the predecessor of short_put.
        sp_idx = sorted(_STRIKE_GRID).index(result.short_put_strike)
        self.assertEqual(result.long_put_strike, sorted(_STRIKE_GRID)[sp_idx - 1])

    def test_works_with_irregular_strike_spacing(self):
        # Mix $0.50 and $1.00 increments. Long put still = next-below.
        irregular = [7.0, 8.0, 9.0, 9.5, 10.0, 11.0, 12.0, 13.0]
        result = build_legs(_target(), irregular, 10.0, _config())
        self.assertIsNotNone(result)
        self.assertEqual(result.short_put_strike, 9.0)
        self.assertEqual(result.long_put_strike, 8.0)
        self.assertEqual(result.put_spread_width, 1.0)


class ShortPutAtLowestEdge(unittest.TestCase):
    """Spec section 3.1 test 12: short put is lowest available strike."""

    def test_returns_none_when_short_put_has_nothing_below(self):
        # Strike grid where the only qualifier is the lowest entry.
        # target=$8 with band [$7.99, $8.5]; only strike at $8 qualifies -> short put.
        # No strike below $8 -> long put leg cannot be built -> None.
        sparse = [8.0, 8.5, 9.0, 11.5, 12.0, 12.5]
        target = _target(target_strike=8.0, band_low=7.99, band_high=8.5)
        self.assertIsNone(build_legs(target, sparse, 10.0, _config()))


class LongCallAboveTarget(unittest.TestCase):
    """Spec section 3.1 test 10: long call respects 'above central target'."""

    def test_long_call_is_above_target(self):
        result = build_legs(_target(), _STRIKE_GRID, 10.0, _config())
        self.assertIsNotNone(result)
        self.assertGreater(result.long_call_strike, _target().target_strike)

    def test_long_call_is_in_15_to_25_pct_otm(self):
        # LETF spot $10 -> OTM band [$11.50, $12.50].
        result = build_legs(_target(), _STRIKE_GRID, 10.0, _config())
        self.assertIsNotNone(result)
        self.assertGreaterEqual(result.long_call_strike, 11.5)
        self.assertLessEqual(result.long_call_strike, 12.5)

    def test_returns_none_when_no_strike_in_otm_range(self):
        # Grid lacks any strike in the [$11.50, $12.50] band.
        gap_grid = [7.0, 7.5, 8.0, 8.5, 9.0, 9.5, 10.0, 10.5, 11.0, 13.0, 13.5]
        self.assertIsNone(build_legs(_target(), gap_grid, 10.0, _config()))


class GuardClauses(unittest.TestCase):
    def test_empty_strikes_returns_none(self):
        self.assertIsNone(build_legs(_target(), [], 10.0, _config()))

    def test_zero_letf_spot_returns_none(self):
        self.assertIsNone(build_legs(_target(), _STRIKE_GRID, 0.0, _config()))

    def test_negative_letf_spot_returns_none(self):
        self.assertIsNone(build_legs(_target(), _STRIKE_GRID, -5.0, _config()))


if __name__ == "__main__":
    unittest.main()
