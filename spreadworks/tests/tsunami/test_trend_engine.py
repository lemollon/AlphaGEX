"""Unit tests for the TSUNAMI-TREND signal math (backtest-validated engine)."""
from __future__ import annotations

import math
import unittest
from unittest.mock import patch

from backend.bots.tsunami import trend_engine


def _hist(closes: list[float]) -> list[dict]:
    return [{"date": f"2026-01-{i+1:02d}", "close": c} for i, c in enumerate(closes)]


class SignalWeight(unittest.TestCase):
    def test_trend_off_below_ma_returns_zero(self):
        closes = [100.0] * 80  # flat history
        with patch.object(trend_engine.tradier_client, "get_daily_history",
                          return_value=_hist(closes)), \
             patch.object(trend_engine.tradier_client, "get_quote",
                          return_value={"last": 90.0}):  # below the 100 MA
            self.assertEqual(trend_engine._signal_weight("TSLL"), 0.0)

    def test_trend_on_returns_vol_scaled_weight(self):
        # gentle uptrend: last > MA, RV small but positive
        closes = [100.0 * (1.002 ** i) for i in range(80)]
        with patch.object(trend_engine.tradier_client, "get_daily_history",
                          return_value=_hist(closes)), \
             patch.object(trend_engine.tradier_client, "get_quote",
                          return_value={"last": closes[-1] * 1.01}):
            w = trend_engine._signal_weight("TSLL")
        self.assertIsNotNone(w)
        self.assertGreater(w, 0.0)
        # cap: never more than SLICE * W_CAP
        self.assertLessEqual(w, trend_engine.SLICE * trend_engine.W_CAP + 1e-9)

    def test_high_vol_scales_down(self):
        # violent series -> RV >> target -> weight well under SLICE
        closes = [100.0 + (8.0 if i % 2 else -8.0) for i in range(80)]
        base = [100.0 + i * 0.5 for i in range(80)]  # keep last above MA
        mixed = [b + (4.0 if i % 2 else -4.0) for i, b in enumerate(base)]
        with patch.object(trend_engine.tradier_client, "get_daily_history",
                          return_value=_hist(mixed)), \
             patch.object(trend_engine.tradier_client, "get_quote",
                          return_value={"last": mixed[-1] + 10}):
            w = trend_engine._signal_weight("TSLL")
        self.assertIsNotNone(w)
        self.assertLess(w, trend_engine.SLICE)

    def test_no_data_returns_none(self):
        with patch.object(trend_engine.tradier_client, "get_daily_history",
                          return_value=[]), \
             patch.object(trend_engine.tradier_client, "get_quote",
                          return_value=None):
            self.assertIsNone(trend_engine._signal_weight("TSLL"))


class Config(unittest.TestCase):
    def test_backtested_parameters(self):
        # These are the values the 2026-07-03 backtest validated. Changing
        # them invalidates the backtest — fail loudly.
        self.assertEqual(trend_engine.SLICE, 0.40)
        self.assertEqual(trend_engine.VOL_TGT, 0.35)
        self.assertEqual(trend_engine.MA_N, 50)
        self.assertEqual(trend_engine.RV_N, 20)
        self.assertEqual(trend_engine.START_CASH, 500.0)
        self.assertEqual([l for _, l in trend_engine.PAIRS],
                         ["TSLL", "AMDL", "NVDL", "CONL", "MSTU",
                          "BITX", "ETHU", "IONX",
                          "SBIT", "ETHD", "SMST"])


if __name__ == "__main__":
    unittest.main()
