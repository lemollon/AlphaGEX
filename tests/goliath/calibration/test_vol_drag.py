"""Tests for trading.goliath.calibration.vol_drag.

TestComputePairDrag  -- math kernel with synthetic GBM-style price pairs.
TestCalibrate        -- module contract; tag transitions verified by mocking
                        _compute_pair_drag to return controlled per-pair stats.
"""
from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from trading.goliath.calibration import vol_drag as vd  # noqa: E402
from trading.goliath.models import GoliathConfig  # noqa: E402


def _make_config(coeff: float = 1.0, vol_window: int = 30) -> GoliathConfig:
    return GoliathConfig(
        instance_name="GOLIATH-TEST",
        letf_ticker="TEST",
        underlying_ticker="TEST_UND",
        drag_coefficient=coeff,
        realized_vol_window_days=vol_window,
    )


def _synthetic_pair(days=120, sigma_annual=0.30, leverage=2.0, drag_factor=1.0, seed=42):
    """Synthetic underlying + LETF pair with controlled drag.

    drag_factor=1.0 -> LETF tracks theory exactly (modulo discretization noise).
    drag_factor=1.5 -> observed drag is 1.5x theoretical (LETF underperforms).
    drag_factor=0.5 -> observed drag is 0.5x theoretical (LETF outperforms).
    """
    rng = np.random.default_rng(seed)
    daily_sigma = sigma_annual / np.sqrt(252)
    u_daily = rng.normal(0, daily_sigma, days)
    theoretical_daily_drag = -0.5 * leverage * (leverage - 1) * daily_sigma**2
    # Apply drag_factor to the drag term so observed drag scales accordingly
    l_daily = leverage * u_daily + drag_factor * theoretical_daily_drag

    u_prices = 100.0 * np.exp(np.cumsum(u_daily))
    l_prices = 100.0 * np.exp(np.cumsum(l_daily))
    dates = pd.bdate_range(end=pd.Timestamp("2026-04-25"), periods=days)
    return (
        pd.DataFrame({"Close": u_prices}, index=dates),
        pd.DataFrame({"Close": l_prices}, index=dates),
    )


class TestComputePairDrag(unittest.TestCase):
    """Math kernel: per-pair observed vs theoretical drag ratio."""

    def test_theory_matches_yields_ratio_near_one(self):
        # drag_factor=1.0 means observed == theoretical (per discretization)
        u, l = _synthetic_pair(days=180, drag_factor=1.0, seed=1)
        m = vd._compute_pair_drag(u["Close"], l["Close"], leverage=2.0, vol_window_days=30)
        self.assertIsNotNone(m)
        # Ratio should be near 1.0 with some tolerance for finite-sample noise
        self.assertAlmostEqual(m["mean_ratio"], 1.0, delta=0.5)

    def test_double_drag_yields_ratio_near_two(self):
        u, l = _synthetic_pair(days=180, drag_factor=2.0, seed=2)
        m = vd._compute_pair_drag(u["Close"], l["Close"], leverage=2.0, vol_window_days=30)
        self.assertIsNotNone(m)
        self.assertGreater(m["mean_ratio"], 1.2)

    def test_se_decreases_with_more_data(self):
        u_short, l_short = _synthetic_pair(days=80, drag_factor=1.0, seed=3)
        u_long, l_long = _synthetic_pair(days=200, drag_factor=1.0, seed=3)
        m_short = vd._compute_pair_drag(u_short["Close"], l_short["Close"], 2.0, 30)
        m_long = vd._compute_pair_drag(u_long["Close"], l_long["Close"], 2.0, 30)
        self.assertIsNotNone(m_short)
        self.assertIsNotNone(m_long)
        # More observations -> smaller SE
        self.assertLess(m_long["se_mean"], m_short["se_mean"])

    def test_insufficient_data_returns_none(self):
        u, l = _synthetic_pair(days=30, drag_factor=1.0)
        m = vd._compute_pair_drag(u["Close"], l["Close"], leverage=2.0, vol_window_days=30)
        self.assertIsNone(m)

    def test_zero_sigma_returns_none(self):
        dates = pd.bdate_range(end=pd.Timestamp("2026-04-25"), periods=120)
        u = pd.Series([100.0] * 120, index=dates)
        l = pd.Series([100.0] * 120, index=dates)
        m = vd._compute_pair_drag(u, l, leverage=2.0, vol_window_days=30)
        self.assertIsNone(m)


def _empty_price_history(n_pairs: int) -> dict:
    """Minimal price_history that lets calibrate() enter the loop."""
    dates = pd.bdate_range(end=pd.Timestamp("2026-04-25"), periods=120)
    flat = pd.DataFrame({"Close": [100.0] * 120}, index=dates)
    ph = {}
    for letf, underlying in list(vd.LETF_PAIRS.items())[:n_pairs]:
        ph[underlying] = flat.copy()
        ph[letf] = flat.copy()
    return ph


def _calibrate_with_pair_stats(stats_per_pair):
    """Run calibrate() with _compute_pair_drag mocked to yield per-pair stats."""
    config = _make_config()
    ph = _empty_price_history(len(stats_per_pair))
    iterator = iter(stats_per_pair)

    def _mock(*_args, **_kwargs):
        try:
            stats = next(iterator)
        except StopIteration:
            return None
        return stats

    with patch.object(vd, "_compute_pair_drag", side_effect=_mock):
        return vd.calibrate(ph, config)


def _make_pair_stats(mean: float, se: float = 0.05):
    """Helper: build a per-pair stats dict matching _compute_pair_drag output."""
    return {
        "mean_ratio": float(mean),
        "median_ratio": float(mean),  # identical for testing simplicity
        "se_mean": float(se),
        "theoretical_drag": -0.001,
        "weeks": 12,
        "sigma": 0.30,
    }


class TestCalibrate(unittest.TestCase):
    """Module contract + tag-transition tests."""

    def test_keyword_only_client_arg(self):
        import inspect

        sig = inspect.signature(vd.calibrate)
        self.assertEqual(sig.parameters["client"].kind, inspect.Parameter.KEYWORD_ONLY)

    def test_empty_history_blocks(self):
        result = vd.calibrate({}, _make_config())
        self.assertEqual(result.tag, "CALIB-BLOCK")

    def test_universe_in_corridor_yields_calib_ok(self):
        # 5 pairs with mean_ratio near 1.0 -> universe mean in [0.90, 1.10]
        result = _calibrate_with_pair_stats(
            [_make_pair_stats(r) for r in (0.95, 0.98, 1.00, 1.02, 1.05)]
        )
        self.assertEqual(result.tag, "CALIB-OK")
        self.assertIsNone(result.recommended_value)
        self.assertEqual(result.universe_count, 5)
        self.assertAlmostEqual(result.universe_mean_ratio, 1.0, places=2)

    def test_universe_below_corridor_recommends_median(self):
        # Mean 0.6 -> below 0.90 -> CALIB-ADJUST, recommend median
        result = _calibrate_with_pair_stats(
            [_make_pair_stats(r) for r in (0.4, 0.5, 0.6, 0.7, 0.8)]
        )
        self.assertEqual(result.tag, "CALIB-ADJUST")
        self.assertAlmostEqual(result.recommended_value, 0.6, places=2)
        self.assertIn("weaker than theory", result.notes)

    def test_universe_above_corridor_recommends_median(self):
        # Mean 1.4 -> above 1.10 -> CALIB-ADJUST, recommend median
        result = _calibrate_with_pair_stats(
            [_make_pair_stats(r) for r in (1.2, 1.3, 1.4, 1.5, 1.6)]
        )
        self.assertEqual(result.tag, "CALIB-ADJUST")
        self.assertAlmostEqual(result.recommended_value, 1.4, places=2)
        self.assertIn("stronger than theory", result.notes)

    def test_high_se_blocks_with_extension_recommendation(self):
        # SE = 0.20 > 0.15 -> CALIB-BLOCK regardless of mean
        result = _calibrate_with_pair_stats(
            [_make_pair_stats(r, se=0.20) for r in (0.95, 1.00, 1.05)]
        )
        self.assertEqual(result.tag, "CALIB-BLOCK")
        self.assertIn("180d", result.notes)
        self.assertIn("noisy", result.notes)

    def test_outlier_flagged(self):
        # 4 pairs near 1.0, one at 2.0 (>25% from mean ~1.2)
        result = _calibrate_with_pair_stats(
            [_make_pair_stats(r) for r in (0.9, 1.0, 1.0, 1.1, 2.0)]
        )
        self.assertGreater(len(result.outliers), 0)
        outlier_ratios = [r for _, r in result.outliers]
        self.assertIn(2.0, outlier_ratios)
        self.assertIn("outliers", result.notes.lower())


if __name__ == "__main__":
    unittest.main()
