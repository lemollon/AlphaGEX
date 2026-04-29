"""Tests for trading.goliath.calibration.wall_concentration.

Synthetic-input math validation. Does NOT exercise the live TV API — that's
covered by data_fetch tests (Step 7) and the live calibration run (Step 9).

Uses dependency injection (the optional ``client`` kwarg on calibrate()) to
inject a MagicMock TV client, avoiding any need to import core_classes_and_engines.
"""
from __future__ import annotations

import sys
import os
import unittest
from unittest.mock import MagicMock

import pandas as pd

# Repo root on sys.path so `trading.goliath.*` imports work when running
# `pytest tests/goliath/calibration/` from repo root or as a module.
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
    """Return a dict shaped like TradingVolatilityAPI.get_gex_profile output."""
    return {"spot_price": spot, "strikes": strikes}


class TestComputeConcentration(unittest.TestCase):
    """Math kernel: wall concentration ratio for a single snapshot."""

    def test_clean_wall_below_spot(self):
        # Spot 100; strikes 90/95/100/105/110; wall at 95 with 10x typical gamma.
        strikes = [
            {"strike": 90, "total_gamma": 100},
            {"strike": 95, "total_gamma": 1000},
            {"strike": 100, "total_gamma": 100},
            {"strike": 105, "total_gamma": 100},
            {"strike": 110, "total_gamma": 100},
        ]
        ratio = wc._compute_concentration(_profile(100, strikes), band_pct=0.10)
        # Median in ±10% band = 100; max below spot = 1000 → ratio = 10.0
        self.assertAlmostEqual(ratio, 10.0, places=2)

    def test_uniform_gamma_yields_unity(self):
        strikes = [{"strike": s, "total_gamma": 100} for s in (90, 95, 100, 105, 110)]
        ratio = wc._compute_concentration(_profile(100, strikes), band_pct=0.10)
        self.assertAlmostEqual(ratio, 1.0, places=2)

    def test_negative_gamma_uses_absolute_value(self):
        # Below-spot strikes are typically put-dominated → negative total_gamma.
        # Concentration must use abs() so put walls register as walls.
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


class TestPercentile(unittest.TestCase):
    """Sanity check the percentile helper used for n=5 universe stats."""

    def test_n5_percentiles(self):
        s = [1.0, 2.0, 3.0, 4.0, 5.0]
        self.assertAlmostEqual(wc._percentile(s, 0.25), 2.0)
        self.assertAlmostEqual(wc._percentile(s, 0.50), 3.0)
        self.assertAlmostEqual(wc._percentile(s, 0.90), 5.0)

    def test_empty_returns_zero(self):
        self.assertEqual(wc._percentile([], 0.50), 0.0)


def _mock_client_with_ratios(ratios):
    """Build a MagicMock client whose get_gex_profile() returns profiles
    designed so _compute_concentration() yields exactly the ratios in order."""
    profiles = []
    for r in ratios:
        # Wall at strike 95 (below spot 100); baseline gamma 100 in band.
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


class TestCalibrate(unittest.TestCase):
    """Universe-level orchestration with injected mock TV client."""

    def test_universe_in_corridor_keeps_spec(self):
        config = _make_config(threshold=2.0)
        gex_history = {u: pd.DataFrame() for u in ("MSTR", "TSLA", "NVDA", "COIN", "AMD")}
        # Ratios spanning [1.6, 2.9] — spec 2.0 is comfortably in [P25, P90]
        client = _mock_client_with_ratios([1.6, 1.8, 2.0, 2.5, 2.9])

        result = wc.calibrate(gex_history, config, client=client)

        self.assertEqual(result.tag, "CALIB-OK")
        self.assertIsNone(result.recommended_value)
        self.assertEqual(len(result.per_underlying), 5)
        self.assertTrue(result.universe_p25 <= 2.0 <= result.universe_p90)

    def test_universe_below_spec_recommends_median(self):
        config = _make_config(threshold=2.0)
        gex_history = {u: pd.DataFrame() for u in ("A", "B", "C", "D", "E")}
        # All ratios well below 2.0 — spec falls outside [P25, P90].
        client = _mock_client_with_ratios([0.5, 0.6, 0.7, 0.8, 0.9])

        result = wc.calibrate(gex_history, config, client=client)

        self.assertEqual(result.tag, "CALIB-ADJUST")
        self.assertIsNotNone(result.recommended_value)
        self.assertAlmostEqual(result.recommended_value, 0.7, places=1)

    def test_empty_history_blocks(self):
        result = wc.calibrate({}, _make_config(), client=MagicMock())
        self.assertEqual(result.tag, "CALIB-BLOCK")
        self.assertEqual(len(result.per_underlying), 0)

    def test_all_fetches_fail_blocks(self):
        config = _make_config()
        gex_history = {u: pd.DataFrame() for u in ("X", "Y", "Z")}
        client = MagicMock()
        client.get_gex_profile.side_effect = Exception("network down")

        result = wc.calibrate(gex_history, config, client=client)

        self.assertEqual(result.tag, "CALIB-BLOCK")
        # Per-underlying entries exist but are all None
        self.assertEqual(len(result.per_underlying), 3)
        self.assertTrue(all(v is None for v in result.per_underlying.values()))


if __name__ == "__main__":
    unittest.main()
