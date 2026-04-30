"""Tests for trading.goliath.gates.g01_spy_gex."""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from trading.goliath.gates import GateOutcome  # noqa: E402
from trading.goliath.gates.g01_spy_gex import (  # noqa: E402
    EXTREME_NEGATIVE_GEX_THRESHOLD,
    evaluate,
)


class G01SpyGex(unittest.TestCase):
    def test_passes_on_positive_gex(self):
        result = evaluate(spy_net_gex=2.0e9)
        self.assertEqual(result.gate, "G01")
        self.assertEqual(result.outcome, GateOutcome.PASS)
        self.assertTrue(result.passed)
        self.assertEqual(result.context["spy_net_gex"], 2.0e9)

    def test_passes_on_mild_negative_gex(self):
        result = evaluate(spy_net_gex=-1.5e9)
        self.assertTrue(result.passed)

    def test_fails_at_extreme_negative(self):
        result = evaluate(spy_net_gex=EXTREME_NEGATIVE_GEX_THRESHOLD - 1.0)
        self.assertEqual(result.outcome, GateOutcome.FAIL)
        self.assertFalse(result.passed)
        self.assertIn("extreme-negative", result.reason)

    def test_passes_exactly_at_threshold(self):
        # spec: "below" threshold fails -> at threshold should pass.
        result = evaluate(spy_net_gex=EXTREME_NEGATIVE_GEX_THRESHOLD)
        self.assertTrue(result.passed)

    def test_context_includes_threshold(self):
        result = evaluate(spy_net_gex=1.0e9)
        self.assertEqual(result.context["threshold"], EXTREME_NEGATIVE_GEX_THRESHOLD)


if __name__ == "__main__":
    unittest.main()
