"""Tests for trading.goliath.calibration.tracking_error.

Two test suites:
    TestComputePairTE   -- math kernel with synthetic GBM-style price pairs
    TestCalibrate       -- module contract; tag transitions verified by
                           mocking _compute_pair_te to return controlled
                           ratios (decouples tag logic tests from the
                           statistical noise of synthetic data)
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

from trading.goliath.calibration import tracking_error as te  # noqa: E402
from trading.goliath.models import GoliathConfig  # noqa: E402


def _make_config(fudge: float = 0.1, vol_window: int = 30) -> GoliathConfig:
    return GoliathConfig(
        instance_name="GOLIATH-TEST",
        letf_ticker="TEST",
        underlying_ticker="TEST_UND",
        tracking_error_fudge=fudge,
        realized_vol_window_days=vol_window,
    )


def _synthetic_pair(days=120, sigma_annual=0.30, leverage=2.0, te_noise=0.0, seed=42):
    """Generate underlying + LETF daily price series with controlled TE noise.

    Underlying: GBM with given annual sigma.
    LETF: leverage * u_t + drag + Gaussian noise (te_noise is annualized
    additive vol on the LETF residual; 0 = perfect tracking).
    """
    rng = np.random.default_rng(seed)
    daily_sigma = sigma_annual / np.sqrt(252)
    u_daily = rng.normal(0, daily_sigma, days)
    daily_drag = -0.5 * leverage * (leverage - 1) * daily_sigma**2
    noise = rng.normal(0, te_noise / np.sqrt(252), days) if te_noise > 0 else 0
    l_daily = leverage * u_daily + daily_drag + noise

    u_prices = 100.0 * np.exp(np.cumsum(u_daily))
    l_prices = 100.0 * np.exp(np.cumsum(l_daily))
    dates = pd.bdate_range(end=pd.Timestamp("2026-04-25"), periods=days)
    return (
        pd.DataFrame({"Close": u_prices}, index=dates),
        pd.DataFrame({"Close": l_prices}, index=dates),
    )


class TestComputePairTE(unittest.TestCase):
    """Math kernel: per-pair observed vs predicted TE."""

    def test_no_noise_yields_low_ratio(self):
        u, l = _synthetic_pair(days=120, te_noise=0.0)
        m = te._compute_pair_te(u["Close"], l["Close"], leverage=2.0, vol_window_days=30)
        self.assertIsNotNone(m)
        # No injected noise -> residuals are essentially numerical artifact.
        self.assertLess(m["ratio"], 0.5)
        self.assertGreater(m["sigma"], 0)

    def test_high_noise_yields_high_ratio(self):
        u, l = _synthetic_pair(days=120, te_noise=0.50)
        m = te._compute_pair_te(u["Close"], l["Close"], leverage=2.0, vol_window_days=30)
        self.assertIsNotNone(m)
        self.assertGreater(m["ratio"], 1.0)

    def test_insufficient_data_returns_none(self):
        u, l = _synthetic_pair(days=30)
        m = te._compute_pair_te(u["Close"], l["Close"], leverage=2.0, vol_window_days=30)
        self.assertIsNone(m)

    def test_zero_sigma_returns_none(self):
        dates = pd.bdate_range(end=pd.Timestamp("2026-04-25"), periods=120)
        u = pd.Series([100.0] * 120, index=dates)
        l = pd.Series([100.0] * 120, index=dates)
        m = te._compute_pair_te(u, l, leverage=2.0, vol_window_days=30)
        self.assertIsNone(m)


def _empty_price_history(n_pairs: int) -> dict:
    """Build a price_history dict that's just non-empty enough to enter
    the calibrate() loop. Actual TE computation is mocked separately."""
    dates = pd.bdate_range(end=pd.Timestamp("2026-04-25"), periods=120)
    flat = pd.DataFrame({"Close": [100.0] * 120}, index=dates)
    ph = {}
    for letf, underlying in list(te.LETF_PAIRS.items())[:n_pairs]:
        ph[underlying] = flat.copy()
        ph[letf] = flat.copy()
    return ph


def _calibrate_with_mocked_ratios(ratios):
    """Run calibrate() with _compute_pair_te mocked to yield given ratios in order."""
    config = _make_config()
    ph = _empty_price_history(len(ratios))
    iterator = iter(ratios)

    def _mock(*_args, **_kwargs):
        try:
            r = next(iterator)
        except StopIteration:
            return None
        return {
            "observed_te": r * 0.05,
            "predicted_te": 0.05,
            "ratio": float(r),
            "weeks": 12,
            "sigma": 0.30,
        }

    with patch.object(te, "_compute_pair_te", side_effect=_mock):
        return te.calibrate(ph, config)


class TestCalibrate(unittest.TestCase):
    """Module contract + tag-transition tests."""

    def test_keyword_only_client_arg(self):
        import inspect

        sig = inspect.signature(te.calibrate)
        self.assertEqual(sig.parameters["client"].kind, inspect.Parameter.KEYWORD_ONLY)

    def test_empty_history_blocks(self):
        result = te.calibrate({}, _make_config())
        self.assertEqual(result.tag, "CALIB-BLOCK")
        self.assertEqual(result.universe_count, 0)

    def test_universe_in_corridor_yields_calib_ok(self):
        # 5 ratios spanning [0.8, 1.2]; median 1.0 is in [0.75, 1.25]
        result = _calibrate_with_mocked_ratios([0.8, 0.9, 1.0, 1.1, 1.2])
        self.assertEqual(result.tag, "CALIB-OK")
        self.assertIsNone(result.recommended_value)
        self.assertEqual(result.universe_count, 5)
        self.assertAlmostEqual(result.universe_median_ratio, 1.0, places=2)

    def test_universe_too_conservative_recommends_proportional(self):
        # Median 0.5 -> spec too conservative. Recommend 0.1 * 0.5 = 0.05
        result = _calibrate_with_mocked_ratios([0.3, 0.4, 0.5, 0.6, 0.7])
        self.assertEqual(result.tag, "CALIB-ADJUST")
        self.assertAlmostEqual(result.recommended_value, 0.05, places=4)
        self.assertIn("too conservative", result.notes)

    def test_universe_too_aggressive_recommends_proportional(self):
        # Median 2.0 -> spec too aggressive. Recommend 0.1 * 2.0 = 0.20
        result = _calibrate_with_mocked_ratios([1.5, 1.8, 2.0, 2.2, 2.5])
        self.assertEqual(result.tag, "CALIB-ADJUST")
        self.assertAlmostEqual(result.recommended_value, 0.20, places=4)
        self.assertIn("too aggressive", result.notes)

    def test_outlier_flagged(self):
        # 4 ratios near 1.0, one at 5.0 (5x median). Outlier threshold = 1.5x median.
        result = _calibrate_with_mocked_ratios([0.9, 1.0, 1.0, 1.1, 5.0])
        self.assertGreater(len(result.outliers), 0)
        outlier_ratios = [r for _, r in result.outliers]
        self.assertIn(5.0, outlier_ratios)
        self.assertIn("Outliers", result.notes)


if __name__ == "__main__":
    unittest.main()
