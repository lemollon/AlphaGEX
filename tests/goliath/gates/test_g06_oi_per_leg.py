"""Tests for trading.goliath.gates.g06_oi_per_leg."""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from trading.goliath.gates import GateOutcome  # noqa: E402
from trading.goliath.gates.g06_oi_per_leg import evaluate  # noqa: E402
from trading.goliath.strike_mapping.engine import MIN_OI_PER_LEG, OptionLeg  # noqa: E402


def _leg(strike: float, oi: int, kind: str = "put") -> OptionLeg:
    return OptionLeg(strike=strike, bid=0.50, ask=0.52, open_interest=oi, contract_type=kind)


class G06Pass(unittest.TestCase):
    def test_passes_when_all_legs_meet_threshold(self):
        result = evaluate(_leg(9.0, 500, "put"), _leg(8.5, 300, "put"), _leg(12.0, 250, "call"))
        self.assertEqual(result.gate, "G06")
        self.assertEqual(result.outcome, GateOutcome.PASS)

    def test_passes_at_exact_threshold(self):
        threshold = MIN_OI_PER_LEG
        result = evaluate(
            _leg(9.0, threshold, "put"),
            _leg(8.5, threshold, "put"),
            _leg(12.0, threshold, "call"),
        )
        self.assertTrue(result.passed)


class G06Fail(unittest.TestCase):
    def test_fails_when_short_put_oi_low(self):
        result = evaluate(_leg(9.0, 100, "put"), _leg(8.5, 500, "put"), _leg(12.0, 500, "call"))
        self.assertEqual(result.outcome, GateOutcome.FAIL)
        self.assertIn("short_put@9.0", result.reason)

    def test_fails_when_long_put_oi_low(self):
        result = evaluate(_leg(9.0, 500, "put"), _leg(8.5, 50, "put"), _leg(12.0, 500, "call"))
        self.assertEqual(result.outcome, GateOutcome.FAIL)
        self.assertIn("long_put", result.reason)

    def test_fails_when_long_call_oi_low(self):
        result = evaluate(_leg(9.0, 500, "put"), _leg(8.5, 500, "put"), _leg(12.0, 10, "call"))
        self.assertEqual(result.outcome, GateOutcome.FAIL)
        self.assertIn("long_call", result.reason)

    def test_lists_all_failures(self):
        # Two legs below threshold -> both surface in reason.
        result = evaluate(_leg(9.0, 50, "put"), _leg(8.5, 60, "put"), _leg(12.0, 500, "call"))
        self.assertIn("short_put", result.reason)
        self.assertIn("long_put", result.reason)


class G06Context(unittest.TestCase):
    def test_context_includes_per_leg_oi(self):
        result = evaluate(_leg(9.0, 500, "put"), _leg(8.5, 400, "put"), _leg(12.0, 300, "call"))
        self.assertEqual(result.context["short_put_oi"], 500)
        self.assertEqual(result.context["long_put_oi"], 400)
        self.assertEqual(result.context["long_call_oi"], 300)
        self.assertEqual(result.context["min_oi"], MIN_OI_PER_LEG)


if __name__ == "__main__":
    unittest.main()
