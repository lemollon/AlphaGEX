"""Tests for trading.goliath.gates.g02_underlying_gex.

Per kickoff prompt: G02 must have 5 fails, one per LETF underlying.
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from trading.goliath.gates import GateOutcome  # noqa: E402
from trading.goliath.gates.g02_underlying_gex import (  # noqa: E402
    EXTREME_NEGATIVE_GEX_THRESHOLD,
    evaluate,
)

UNDERLYINGS = ["MSTR", "TSLA", "NVDA", "COIN", "AMD"]


class G02HappyPath(unittest.TestCase):
    def test_passes_on_positive_gex(self):
        result = evaluate("MSTR", underlying_net_gex=2.0e8)
        self.assertEqual(result.gate, "G02")
        self.assertEqual(result.outcome, GateOutcome.PASS)
        self.assertEqual(result.context["underlying_ticker"], "MSTR")

    def test_passes_at_exact_threshold(self):
        result = evaluate("TSLA", EXTREME_NEGATIVE_GEX_THRESHOLD)
        self.assertTrue(result.passed)


class G02FailsPerUnderlying(unittest.TestCase):
    """Spec/kickoff: one fail test per LETF underlying."""

    def _assert_fail(self, ticker: str):
        result = evaluate(ticker, EXTREME_NEGATIVE_GEX_THRESHOLD - 1e7)
        self.assertEqual(result.outcome, GateOutcome.FAIL)
        self.assertIn(ticker, result.reason)
        self.assertEqual(result.context["underlying_ticker"], ticker)

    def test_mstr_extreme_negative_fails(self):
        self._assert_fail("MSTR")

    def test_tsla_extreme_negative_fails(self):
        self._assert_fail("TSLA")

    def test_nvda_extreme_negative_fails(self):
        self._assert_fail("NVDA")

    def test_coin_extreme_negative_fails(self):
        self._assert_fail("COIN")

    def test_amd_extreme_negative_fails(self):
        self._assert_fail("AMD")


class G02ContextSnapshot(unittest.TestCase):
    def test_context_includes_inputs_and_threshold(self):
        result = evaluate("NVDA", 5.0e7)
        self.assertEqual(result.context["underlying_ticker"], "NVDA")
        self.assertEqual(result.context["underlying_net_gex"], 5.0e7)
        self.assertEqual(result.context["threshold"], EXTREME_NEGATIVE_GEX_THRESHOLD)


if __name__ == "__main__":
    unittest.main()
