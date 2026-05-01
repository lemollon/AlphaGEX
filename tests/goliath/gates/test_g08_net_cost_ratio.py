"""Tests for trading.goliath.gates.g08_net_cost_ratio."""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from trading.goliath.gates import GateOutcome  # noqa: E402
from trading.goliath.gates.g08_net_cost_ratio import evaluate  # noqa: E402
from trading.goliath.strike_mapping.engine import (  # noqa: E402
    MAX_NET_COST_TO_CALL_RATIO,
    OptionLeg,
)


def _leg(strike: float, mid: float, kind: str) -> OptionLeg:
    return OptionLeg(strike=strike, bid=mid - 0.01, ask=mid + 0.01, open_interest=500, contract_type=kind)


class G08Pass(unittest.TestCase):
    def test_passes_when_credit_subsidizes_call(self):
        # short put 0.50 - long put 0.20 = 0.30 credit; long call 0.30
        # net_cost = 0.30 - 0.30 = 0.00 -> ratio 0.00 <= 0.30
        result = evaluate(
            _leg(9.0, 0.50, "put"),
            _leg(8.5, 0.20, "put"),
            _leg(12.0, 0.30, "call"),
        )
        self.assertEqual(result.gate, "G08")
        self.assertEqual(result.outcome, GateOutcome.PASS)

    def test_passes_with_net_credit(self):
        # spread credit 0.50; long call 0.20 -> net_cost = -0.30 (credit)
        result = evaluate(
            _leg(9.0, 0.70, "put"),
            _leg(8.5, 0.20, "put"),
            _leg(12.0, 0.20, "call"),
        )
        self.assertTrue(result.passed)
        self.assertLess(result.context["net_cost"], 0)

    def test_passes_at_exact_30_pct_boundary(self):
        # spread credit 0.20; long call 1.00 -> net_cost = 0.80? wait
        # We need net_cost / long_call_mid == 0.30 exactly.
        # net_cost = 1.00 - credit = 0.30 -> credit = 0.70
        # short_put_mid - long_put_mid = 0.70 with short=0.90, long=0.20
        result = evaluate(
            _leg(9.0, 0.90, "put"),
            _leg(8.5, 0.20, "put"),
            _leg(12.0, 1.00, "call"),
        )
        self.assertTrue(result.passed)
        self.assertAlmostEqual(result.context["net_cost_ratio"], 0.30, places=5)


class G08Fail(unittest.TestCase):
    def test_fails_when_call_too_expensive(self):
        # spread credit 0.10; long call 1.00 -> net_cost 0.90 = 90%% of call.
        result = evaluate(
            _leg(9.0, 0.30, "put"),
            _leg(8.5, 0.20, "put"),
            _leg(12.0, 1.00, "call"),
        )
        self.assertEqual(result.outcome, GateOutcome.FAIL)
        self.assertIn("Net cost", result.reason)

    def test_fails_when_long_call_mid_non_positive(self):
        result = evaluate(
            _leg(9.0, 0.50, "put"),
            _leg(8.5, 0.20, "put"),
            _leg(12.0, 0.0, "call"),
        )
        self.assertEqual(result.outcome, GateOutcome.FAIL)
        self.assertIn("non-positive", result.reason)


class G08Context(unittest.TestCase):
    def test_context_includes_economics(self):
        result = evaluate(
            _leg(9.0, 0.50, "put"),
            _leg(8.5, 0.20, "put"),
            _leg(12.0, 0.30, "call"),
        )
        self.assertAlmostEqual(result.context["short_put_mid"], 0.50, places=2)
        self.assertAlmostEqual(result.context["long_put_mid"], 0.20, places=2)
        self.assertAlmostEqual(result.context["long_call_mid"], 0.30, places=2)
        self.assertAlmostEqual(result.context["put_spread_credit"], 0.30, places=2)
        self.assertAlmostEqual(result.context["net_cost"], 0.0, places=2)
        self.assertEqual(
            result.context["max_net_cost_to_call_ratio"],
            MAX_NET_COST_TO_CALL_RATIO,
        )


if __name__ == "__main__":
    unittest.main()
