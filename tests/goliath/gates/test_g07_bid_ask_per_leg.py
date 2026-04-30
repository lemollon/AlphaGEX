"""Tests for trading.goliath.gates.g07_bid_ask_per_leg."""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from trading.goliath.gates import GateOutcome  # noqa: E402
from trading.goliath.gates.g07_bid_ask_per_leg import evaluate  # noqa: E402
from trading.goliath.strike_mapping.engine import (  # noqa: E402
    MAX_BID_ASK_RATIO,
    OptionLeg,
)


def _leg(strike: float, bid: float, ask: float, kind: str = "put") -> OptionLeg:
    return OptionLeg(strike=strike, bid=bid, ask=ask, open_interest=500, contract_type=kind)


class G07Pass(unittest.TestCase):
    def test_passes_on_tight_spreads(self):
        # Mid 1.00, spread 0.04 = 4%% <= 20%%
        result = evaluate(
            _leg(9.0, 0.98, 1.02, "put"),
            _leg(8.5, 0.48, 0.52, "put"),
            _leg(12.0, 0.28, 0.32, "call"),
        )
        self.assertEqual(result.gate, "G07")
        self.assertEqual(result.outcome, GateOutcome.PASS)

    def test_passes_at_exact_20_pct(self):
        # bid 0.90 / ask 1.10 -> mid 1.00, spread 0.20 = 20%% (boundary; <=).
        result = evaluate(
            _leg(9.0, 0.90, 1.10, "put"),
            _leg(8.5, 0.45, 0.55, "put"),
            _leg(12.0, 0.27, 0.33, "call"),
        )
        self.assertTrue(result.passed)


class G07Fail(unittest.TestCase):
    def test_fails_when_short_put_spread_wide(self):
        # Mid 0.65, spread 0.30 = 46%%
        result = evaluate(
            _leg(9.0, 0.50, 0.80, "put"),
            _leg(8.5, 0.48, 0.52, "put"),
            _leg(12.0, 0.28, 0.32, "call"),
        )
        self.assertEqual(result.outcome, GateOutcome.FAIL)
        self.assertIn("short_put", result.reason)

    def test_fails_when_long_call_spread_wide(self):
        result = evaluate(
            _leg(9.0, 0.98, 1.02, "put"),
            _leg(8.5, 0.48, 0.52, "put"),
            _leg(12.0, 0.20, 0.40, "call"),
        )
        self.assertEqual(result.outcome, GateOutcome.FAIL)
        self.assertIn("long_call", result.reason)

    def test_fails_when_mid_non_positive(self):
        # bid=0, ask=0 -> mid=0 -> degenerate -> infinity ratio -> fail.
        result = evaluate(
            _leg(9.0, 0.0, 0.0, "put"),
            _leg(8.5, 0.48, 0.52, "put"),
            _leg(12.0, 0.28, 0.32, "call"),
        )
        self.assertEqual(result.outcome, GateOutcome.FAIL)


class G07Context(unittest.TestCase):
    def test_context_includes_per_leg_ratios(self):
        result = evaluate(
            _leg(9.0, 0.98, 1.02, "put"),
            _leg(8.5, 0.48, 0.52, "put"),
            _leg(12.0, 0.28, 0.32, "call"),
        )
        # mid 1.00, spread 0.04 -> ratio 0.04
        self.assertAlmostEqual(result.context["short_put_ratio"], 0.04, places=3)
        self.assertEqual(result.context["max_bid_ask_ratio"], MAX_BID_ASK_RATIO)


if __name__ == "__main__":
    unittest.main()
