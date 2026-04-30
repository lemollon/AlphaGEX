"""Tests for trading.goliath.gates.g10_platform_position_cap."""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from trading.goliath.gates import GateOutcome  # noqa: E402
from trading.goliath.gates.g10_platform_position_cap import (  # noqa: E402
    DEFAULT_MAX_CONCURRENT,
    evaluate,
)


class G10Pass(unittest.TestCase):
    def test_passes_with_zero_open(self):
        result = evaluate(open_position_count=0)
        self.assertEqual(result.gate, "G10")
        self.assertEqual(result.outcome, GateOutcome.PASS)

    def test_passes_with_one_open(self):
        self.assertTrue(evaluate(1).passed)

    def test_passes_with_room_for_one_more(self):
        # 2 open + 1 new = 3 (at cap, allowed)
        result = evaluate(open_position_count=DEFAULT_MAX_CONCURRENT - 1)
        self.assertTrue(result.passed)


class G10Fail(unittest.TestCase):
    def test_fails_at_cap(self):
        # 3 open already -> no room for a 4th.
        result = evaluate(open_position_count=DEFAULT_MAX_CONCURRENT)
        self.assertEqual(result.outcome, GateOutcome.FAIL)
        self.assertIn("no room", result.reason)

    def test_fails_over_cap(self):
        # Defensive: should not happen but gate must still reject.
        result = evaluate(open_position_count=DEFAULT_MAX_CONCURRENT + 5)
        self.assertEqual(result.outcome, GateOutcome.FAIL)


class G10CustomCap(unittest.TestCase):
    def test_custom_cap_honored(self):
        # 3 open with cap=5 -> pass; with default cap=3 -> fail.
        self.assertTrue(evaluate(open_position_count=3, max_concurrent=5).passed)
        self.assertEqual(
            evaluate(open_position_count=3).outcome, GateOutcome.FAIL
        )


class G10Context(unittest.TestCase):
    def test_context_includes_count_and_cap(self):
        result = evaluate(open_position_count=2)
        self.assertEqual(result.context["open_position_count"], 2)
        self.assertEqual(result.context["max_concurrent"], DEFAULT_MAX_CONCURRENT)


if __name__ == "__main__":
    unittest.main()
