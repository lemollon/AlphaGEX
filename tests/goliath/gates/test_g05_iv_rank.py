"""Tests for trading.goliath.gates.g05_iv_rank.

Per kickoff prompt: G05 cold-start case must produce
INSUFFICIENT_HISTORY (per Leron Q6 decision).
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from trading.goliath.gates import GateOutcome  # noqa: E402
from trading.goliath.gates.g05_iv_rank import (  # noqa: E402
    DEFAULT_IV_RANK_THRESHOLD,
    evaluate,
)


class G05PassCases(unittest.TestCase):
    def test_passes_above_threshold(self):
        result = evaluate("TSLL", iv_rank=80.0)
        self.assertEqual(result.gate, "G05")
        self.assertEqual(result.outcome, GateOutcome.PASS)

    def test_passes_at_threshold(self):
        result = evaluate("TSLL", iv_rank=DEFAULT_IV_RANK_THRESHOLD)
        self.assertTrue(result.passed)

    def test_passes_at_max_iv_rank(self):
        result = evaluate("TSLL", iv_rank=100.0)
        self.assertTrue(result.passed)


class G05FailCases(unittest.TestCase):
    def test_fails_just_below_threshold(self):
        result = evaluate("TSLL", iv_rank=DEFAULT_IV_RANK_THRESHOLD - 0.1)
        self.assertEqual(result.outcome, GateOutcome.FAIL)
        self.assertFalse(result.passed)

    def test_fails_at_low_iv_rank(self):
        result = evaluate("TSLL", iv_rank=10.0)
        self.assertEqual(result.outcome, GateOutcome.FAIL)
        self.assertIn("10.0", result.reason)

    def test_fails_at_zero_iv_rank(self):
        result = evaluate("TSLL", iv_rank=0.0)
        self.assertEqual(result.outcome, GateOutcome.FAIL)


class G05ColdStart(unittest.TestCase):
    """Spec/Leron Q6: missing IV rank -> INSUFFICIENT_HISTORY (fail-closed)."""

    def test_none_iv_rank_returns_insufficient_history(self):
        result = evaluate("TSLL", iv_rank=None)
        self.assertEqual(result.outcome, GateOutcome.INSUFFICIENT_HISTORY)
        self.assertFalse(result.passed)
        self.assertTrue(result.is_terminal_fail)
        self.assertIn("cold-start", result.reason)
        self.assertIn("fail-closed", result.reason)

    def test_insufficient_history_context_records_none(self):
        result = evaluate("TSLL", iv_rank=None)
        self.assertIsNone(result.context["iv_rank"])
        self.assertEqual(result.context["letf_ticker"], "TSLL")


class G05CustomThreshold(unittest.TestCase):
    def test_custom_threshold_honored(self):
        # IV rank 50 with threshold 40 passes; with default 60 it fails.
        result_low = evaluate("TSLL", iv_rank=50.0, threshold=40.0)
        self.assertTrue(result_low.passed)
        result_default = evaluate("TSLL", iv_rank=50.0)
        self.assertEqual(result_default.outcome, GateOutcome.FAIL)


if __name__ == "__main__":
    unittest.main()
