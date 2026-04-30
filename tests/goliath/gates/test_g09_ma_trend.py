"""Tests for trading.goliath.gates.g09_ma_trend."""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from trading.goliath.gates import GateOutcome  # noqa: E402
from trading.goliath.gates.g09_ma_trend import evaluate  # noqa: E402


class G09Pass(unittest.TestCase):
    def test_passes_when_spot_above_ma(self):
        result = evaluate("TSLA", underlying_spot=210.0, underlying_50d_ma=200.0)
        self.assertEqual(result.gate, "G09")
        self.assertEqual(result.outcome, GateOutcome.PASS)
        self.assertAlmostEqual(result.context["spot_minus_ma"], 10.0)
        self.assertAlmostEqual(result.context["spot_to_ma_pct"], 0.05, places=4)

    def test_passes_just_above_ma(self):
        result = evaluate("MSTR", underlying_spot=200.01, underlying_50d_ma=200.0)
        self.assertTrue(result.passed)


class G09Fail(unittest.TestCase):
    def test_fails_at_exact_ma(self):
        # Spec says "above" so equal is not strict pass.
        result = evaluate("TSLA", underlying_spot=200.0, underlying_50d_ma=200.0)
        self.assertEqual(result.outcome, GateOutcome.FAIL)
        self.assertIn("downtrend", result.reason)

    def test_fails_when_spot_below_ma(self):
        result = evaluate("NVDA", underlying_spot=180.0, underlying_50d_ma=200.0)
        self.assertEqual(result.outcome, GateOutcome.FAIL)
        self.assertFalse(result.passed)
        self.assertAlmostEqual(result.context["spot_minus_ma"], -20.0)


class G09InsufficientHistory(unittest.TestCase):
    def test_none_ma_returns_insufficient_history(self):
        result = evaluate("AMD", underlying_spot=150.0, underlying_50d_ma=None)
        self.assertEqual(result.outcome, GateOutcome.INSUFFICIENT_HISTORY)
        self.assertTrue(result.is_terminal_fail)
        self.assertIsNone(result.context["underlying_50d_ma"])
        self.assertIn("fail-closed", result.reason)


class G09Context(unittest.TestCase):
    def test_context_includes_inputs(self):
        result = evaluate("COIN", underlying_spot=240.0, underlying_50d_ma=220.0)
        self.assertEqual(result.context["underlying_ticker"], "COIN")
        self.assertEqual(result.context["underlying_spot"], 240.0)
        self.assertEqual(result.context["underlying_50d_ma"], 220.0)


if __name__ == "__main__":
    unittest.main()
