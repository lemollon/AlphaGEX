"""Tests for trading.goliath.calibration.wall_concentration.

Synthetic-input math validation. Does NOT exercise the live TV API.
Uses dependency injection (the keyword-only ``client`` arg per the v2
recovery doc Module Contracts) to inject a MagicMock TV client.

Phase 1.5 v2 revision: tests reflect the sanity-check tag scheme
(CALIB-SANITY-OK / CALIB-FINDING / CALIB-BLOCK), not the original
percentile-based CALIB-OK / CALIB-ADJUST scheme. The metric was
downgraded because TV's v2 API does not expose historical strike-level
data; full distribution validation is deferred to v0.3 once the
strike-snapshot collector accumulates time-series.
"""
from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import MagicMock

import pandas as pd

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from trading.goliath.calibration import wall_concentration as wc  # noqa: E402
from trading.goliath.models import GoliathConfig  # noqa: E402


def _make_config(threshold: float = 2.0) -> GoliathConfig:
    return GoliathConfig(
        instance_name="GOLIATH-TEST",
        letf_ticker="TEST",
        underlying_ticker="TEST_UND",
        wall_concentration_threshold=threshold,
    )


def _profile(spot: float, strikes: list) -> dict:
    """Dict shaped like TradingVolatilityAPI.get_gex_profile output."""
    return {"spot_price": spot, "strikes": strikes}


def _mock_client_with_ratios(ratios):
    """Build a MagicMock client whose get_gex_profile returns profiles
    designed so _compute_concentration yields exactly the given ratios."""
    profiles = []
    for r in ratios:
        profiles.append(
            _profile(
                100.0,
                [
                    {"strike": 95, "total_gamma": 100 * r},
                    {"strike": 100, "total_gamma": 100},
                    {"strike": 105, "total_gamma": 100},
                ],
            )
        )
    client = MagicMock()
    client.get_gex_profile.side_effect = profiles
    return client


class TestComputeConcentration(unittest.TestCase):
    """Math kernel: wall concentration ratio for a single snapshot."""

    def test_clean_wall_below_spot(self):
        strikes = [
            {"strike": 90, "total_gamma": 100},
            {"strike": 95, "total_gamma": 1000},
            {"strike": 100, "total_gamma": 100},
            {"strike": 105, "total_gamma": 100},
            {"strike": 110, "total_gamma": 100},
        ]
        ratio = wc._compute_concentration(_profile(100, strikes), band_pct=0.10)
        self.assertAlmostEqual(ratio, 10.0, places=2)

    def test_uniform_gamma_yields_unity(self):
        strikes = [{"strike": s, "total_gamma": 100} for s in (90, 95, 100, 105, 110)]
        ratio = wc._compute_concentration(_profile(100, strikes), band_pct=0.10)
        self.assertAlmostEqual(ratio, 1.0, places=2)

    def test_negative_gamma_uses_absolute_value(self):
        strikes = [
            {"strike": 95, "total_gamma": -1000},
            {"strike": 100, "total_gamma": 100},
            {"strike": 105, "total_gamma": 100},
        ]
        ratio = wc._compute_concentration(_profile(100, strikes), band_pct=0.10)
        self.assertAlmostEqual(ratio, 10.0, places=2)

    def test_empty_strikes_returns_none(self):
        self.assertIsNone(wc._compute_concentration(_profile(100, [])))

    def test_no_strikes_below_spot_returns_none(self):
        strikes = [{"strike": s, "total_gamma": 100} for s in (105, 110, 115)]
        self.assertIsNone(wc._compute_concentration(_profile(100, strikes), band_pct=0.20))

    def test_zero_spot_returns_none(self):
        self.assertIsNone(
            wc._compute_concentration(_profile(0, [{"strike": 90, "total_gamma": 100}]))
        )

    def test_all_zero_gamma_returns_none(self):
        strikes = [{"strike": s, "total_gamma": 0} for s in (90, 95, 100, 105, 110)]
        self.assertIsNone(wc._compute_concentration(_profile(100, strikes), band_pct=0.20))


class TestCalibrate(unittest.TestCase):
    """Universe-level orchestration with injected mock TV client."""

    def test_tight_cluster_yields_sanity_ok(self):
        # Ratios all in [1.5, 2.5] -- median 2.0, no outliers, plausible range
        config = _make_config(threshold=2.0)
        gex_history = {u: pd.DataFrame() for u in ("MSTR", "TSLA", "NVDA", "COIN", "AMD")}
        client = _mock_client_with_ratios([1.6, 1.8, 2.0, 2.2, 2.5])

        result = wc.calibrate(gex_history, config, client=client)

        self.assertEqual(result.tag, "CALIB-SANITY-OK")
        self.assertEqual(result.universe_count, 5)
        self.assertAlmostEqual(result.universe_median, 2.0, places=1)
        self.assertEqual(len(result.outliers), 0)
        # Verify percentile fields are NOT present in result
        self.assertFalse(hasattr(result, "universe_p25"))
        self.assertFalse(hasattr(result, "universe_p90"))
        self.assertFalse(hasattr(result, "recommended_value"))

    def test_outlier_yields_finding(self):
        # 4 ratios near 2x, one wild outlier at 12x -- median 2.0, outlier > 3x median
        config = _make_config()
        gex_history = {u: pd.DataFrame() for u in ("A", "B", "C", "D", "E")}
        client = _mock_client_with_ratios([1.5, 1.8, 2.0, 2.2, 12.0])

        result = wc.calibrate(gex_history, config, client=client)

        self.assertEqual(result.tag, "CALIB-FINDING")
        self.assertEqual(len(result.outliers), 1)
        # Outlier is the 12x ratio
        self.assertAlmostEqual(result.outliers[0][1], 12.0, places=1)
        self.assertIn("outlier", result.notes.lower())

    def test_universe_median_outside_plausible_range_yields_finding(self):
        # All ratios extremely small -- median 0.1 is below plausible (0.5, 10.0)
        config = _make_config()
        gex_history = {u: pd.DataFrame() for u in ("A", "B", "C", "D", "E")}
        client = _mock_client_with_ratios([0.05, 0.08, 0.1, 0.12, 0.15])

        result = wc.calibrate(gex_history, config, client=client)

        self.assertEqual(result.tag, "CALIB-FINDING")
        self.assertIn("plausible", result.notes.lower())

    def test_no_underlyings_blocks(self):
        result = wc.calibrate({}, _make_config(), client=MagicMock())
        self.assertEqual(result.tag, "CALIB-BLOCK")
        self.assertEqual(result.universe_count, 0)
        self.assertEqual(len(result.per_underlying), 0)

    def test_all_fetches_fail_blocks(self):
        config = _make_config()
        gex_history = {u: pd.DataFrame() for u in ("X", "Y", "Z")}
        client = MagicMock()
        client.get_gex_profile.side_effect = Exception("network down")

        result = wc.calibrate(gex_history, config, client=client)

        self.assertEqual(result.tag, "CALIB-BLOCK")
        self.assertEqual(result.universe_count, 0)
        # Per-underlying entries exist but are all None
        self.assertEqual(len(result.per_underlying), 3)
        self.assertTrue(all(v is None for v in result.per_underlying.values()))

    def test_keyword_only_client_arg(self):
        """Confirm client must be passed as keyword argument per v2 contract."""
        import inspect
        sig = inspect.signature(wc.calibrate)
        client_param = sig.parameters["client"]
        self.assertEqual(client_param.kind, inspect.Parameter.KEYWORD_ONLY)


if __name__ == "__main__":
    unittest.main()
