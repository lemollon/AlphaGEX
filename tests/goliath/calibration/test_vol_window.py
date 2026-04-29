"""Tests for trading.goliath.calibration.vol_window.

TestComputePairWindowStats -- math kernel with synthetic GBM-style pairs.
TestCalibrate              -- module contract; tag transitions verified by
                              mocking _compute_pair_window_stats to return
                              controlled per-pair winners (decouples tag
                              logic from synthetic-data noise).
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

from trading.goliath.calibration import vol_window as vw  # noqa: E402
from trading.goliath.models import GoliathConfig  # noqa: E402


def _make_config(spec_window: int = 30) -> GoliathConfig:
    return GoliathConfig(
        instance_name="GOLIATH-TEST",
        letf_ticker="TEST",
        underlying_ticker="TEST_UND",
        realized_vol_window_days=spec_window,
    )


def _synthetic_pair(days=180, sigma_annual=0.30, leverage=2.0, seed=42):
    """Synthetic pair where LETF cleanly tracks 2x underlying minus drag."""
    rng = np.random.default_rng(seed)
    daily_sigma = sigma_annual / np.sqrt(252)
    u_daily = rng.normal(0, daily_sigma, days)
    daily_drag = -0.5 * leverage * (leverage - 1) * daily_sigma**2
    l_daily = leverage * u_daily + daily_drag

    u_prices = 100.0 * np.exp(np.cumsum(u_daily))
    l_prices = 100.0 * np.exp(np.cumsum(l_daily))
    dates = pd.bdate_range(end=pd.Timestamp("2026-04-25"), periods=days)
    return (
        pd.DataFrame({"Close": u_prices}, index=dates),
        pd.DataFrame({"Close": l_prices}, index=dates),
    )


class TestComputePairWindowStats(unittest.TestCase):
    """Math kernel: per-pair residual SD across candidate windows."""

    def test_returns_stats_for_each_window(self):
        u, l = _synthetic_pair(days=200)
        m = vw._compute_pair_window_stats(
            u["Close"], l["Close"], leverage=2.0, windows=[20, 30, 60]
        )
        self.assertIsNotNone(m)
        windows_present = {s["window_days"] for s in m["window_stats"]}
        self.assertEqual(windows_present, {20, 30, 60})

    def test_winner_has_smallest_residual_sd(self):
        u, l = _synthetic_pair(days=200)
        m = vw._compute_pair_window_stats(
            u["Close"], l["Close"], leverage=2.0, windows=[20, 30, 60]
        )
        sds = [s["residual_sd"] for s in m["window_stats"]]
        winner_stats = next(s for s in m["window_stats"] if s["window_days"] == m["winner"])
        self.assertEqual(winner_stats["residual_sd"], min(sds))

    def test_insufficient_data_returns_none(self):
        u, l = _synthetic_pair(days=30)
        m = vw._compute_pair_window_stats(
            u["Close"], l["Close"], leverage=2.0, windows=[20, 30, 60]
        )
        self.assertIsNone(m)

    def test_zero_sigma_returns_none(self):
        dates = pd.bdate_range(end=pd.Timestamp("2026-04-25"), periods=200)
        u = pd.Series([100.0] * 200, index=dates)
        l = pd.Series([100.0] * 200, index=dates)
        m = vw._compute_pair_window_stats(u, l, leverage=2.0, windows=[20, 30, 60])
        self.assertIsNone(m)

    def test_empty_windows_returns_none(self):
        u, l = _synthetic_pair(days=200)
        m = vw._compute_pair_window_stats(u["Close"], l["Close"], leverage=2.0, windows=[])
        self.assertIsNone(m)


def _empty_price_history(n_pairs: int) -> dict:
    """Minimal price_history that lets calibrate() enter the loop."""
    dates = pd.bdate_range(end=pd.Timestamp("2026-04-25"), periods=200)
    flat = pd.DataFrame({"Close": [100.0] * 200}, index=dates)
    ph = {}
    for letf, underlying in list(vw.LETF_PAIRS.items())[:n_pairs]:
        ph[underlying] = flat.copy()
        ph[letf] = flat.copy()
    return ph


def _make_pair_metrics(winner: int, sd_20: float = 0.05, sd_30: float = 0.05, sd_60: float = 0.05):
    """Build a per-pair metrics dict matching _compute_pair_window_stats output.

    The `winner` arg sets which window the calibrator should treat as best.
    By default residual_sd values are equal; override to test override-flag logic.
    """
    return {
        "window_stats": [
            {"window_days": 20, "sigma": 0.30, "residual_sd": sd_20},
            {"window_days": 30, "sigma": 0.30, "residual_sd": sd_30},
            {"window_days": 60, "sigma": 0.30, "residual_sd": sd_60},
        ],
        "winner": int(winner),
        "winner_residual_sd": min(sd_20, sd_30, sd_60),
    }


def _calibrate_with_pair_metrics(metrics_per_pair):
    """Run calibrate() with _compute_pair_window_stats mocked to yield metrics."""
    config = _make_config()
    ph = _empty_price_history(len(metrics_per_pair))
    iterator = iter(metrics_per_pair)

    def _mock(*_args, **_kwargs):
        try:
            return next(iterator)
        except StopIteration:
            return None

    with patch.object(vw, "_compute_pair_window_stats", side_effect=_mock):
        return vw.calibrate(ph, config)


class TestCalibrate(unittest.TestCase):
    """Module contract + tag-transition tests."""

    def test_keyword_only_client_arg(self):
        import inspect

        sig = inspect.signature(vw.calibrate)
        self.assertEqual(sig.parameters["client"].kind, inspect.Parameter.KEYWORD_ONLY)

    def test_empty_history_blocks(self):
        result = vw.calibrate({}, _make_config())
        self.assertEqual(result.tag, "CALIB-BLOCK")

    def test_30d_wins_majority_yields_calib_ok(self):
        # 4 of 5 prefer 30d -> majority -> CALIB-OK
        result = _calibrate_with_pair_metrics(
            [_make_pair_metrics(w) for w in (30, 30, 30, 30, 60)]
        )
        self.assertEqual(result.tag, "CALIB-OK")
        self.assertEqual(result.universe_winner, 30)
        self.assertIsNone(result.recommended_value)
        self.assertEqual(result.universe_winners, {30: 4, 60: 1})

    def test_60d_wins_majority_recommends_change(self):
        # 4 of 5 prefer 60d -> CALIB-ADJUST recommending 60d
        result = _calibrate_with_pair_metrics(
            [_make_pair_metrics(w) for w in (60, 60, 60, 60, 30)]
        )
        self.assertEqual(result.tag, "CALIB-ADJUST")
        self.assertEqual(result.recommended_value, 60)

    def test_split_yields_finding(self):
        # 2 / 2 / 1 split -> no majority -> CALIB-FINDING (keep 30d)
        result = _calibrate_with_pair_metrics(
            [_make_pair_metrics(w) for w in (20, 20, 30, 30, 60)]
        )
        self.assertEqual(result.tag, "CALIB-FINDING")
        self.assertIsNone(result.recommended_value)
        self.assertIsNone(result.universe_winner)
        self.assertIn("ambiguous", result.notes.lower())

    def test_per_underlying_override_flagged(self):
        # One pair shows 60d residual_sd 50% lower than 30d -> override candidate
        # Other 4 pairs are flat (30d wins, no override)
        metrics = [
            _make_pair_metrics(60, sd_30=0.10, sd_60=0.05, sd_20=0.10),  # 50% lower at 60d
            _make_pair_metrics(30),
            _make_pair_metrics(30),
            _make_pair_metrics(30),
            _make_pair_metrics(30),
        ]
        result = _calibrate_with_pair_metrics(metrics)
        self.assertGreater(len(result.per_underlying_overrides), 0)
        # First pair -> 60d -> 50% improvement
        first_override = result.per_underlying_overrides[0]
        self.assertEqual(first_override[1], 60)
        self.assertGreater(first_override[2], 0.30)


if __name__ == "__main__":
    unittest.main()
