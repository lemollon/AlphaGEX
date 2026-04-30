"""Tests for trading.goliath.gates.g04_earnings_window."""
from __future__ import annotations

import os
import sys
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from trading.goliath.gates import GateOutcome  # noqa: E402
from trading.goliath.gates.g04_earnings_window import evaluate  # noqa: E402

_TODAY = date(2026, 5, 4)


class G04PassCases(unittest.TestCase):
    def test_passes_when_earnings_far_away(self):
        result = evaluate("TSLA", _TODAY + timedelta(days=30), today=_TODAY)
        self.assertEqual(result.gate, "G04")
        self.assertEqual(result.outcome, GateOutcome.PASS)
        self.assertEqual(result.context["days_until_earnings"], 30)

    def test_passes_just_outside_window(self):
        # 8 days away (window is 7) -> pass.
        result = evaluate("TSLA", _TODAY + timedelta(days=8), today=_TODAY)
        self.assertTrue(result.passed)

    def test_passes_when_earnings_in_past(self):
        # Already-released earnings should not block trades.
        result = evaluate("TSLA", _TODAY - timedelta(days=5), today=_TODAY)
        self.assertTrue(result.passed)


class G04FailCases(unittest.TestCase):
    def test_fails_inside_window(self):
        result = evaluate("TSLA", _TODAY + timedelta(days=3), today=_TODAY)
        self.assertEqual(result.outcome, GateOutcome.FAIL)
        self.assertIn("3 day", result.reason)

    def test_fails_at_window_edge(self):
        # 7 days away is inside the window (<= blackout_days).
        result = evaluate("TSLA", _TODAY + timedelta(days=7), today=_TODAY)
        self.assertEqual(result.outcome, GateOutcome.FAIL)

    def test_fails_today_is_earnings_day(self):
        result = evaluate("TSLA", _TODAY, today=_TODAY)
        self.assertEqual(result.outcome, GateOutcome.FAIL)


class G04YfinanceUnavailable(unittest.TestCase):
    """Spec: yfinance failure -> fail-closed (do not assume safe)."""

    def test_none_earnings_date_fails_closed(self):
        result = evaluate("TSLA", None, today=_TODAY)
        self.assertEqual(result.outcome, GateOutcome.FAIL)
        self.assertIn("unavailable", result.reason)
        self.assertIn("fail-closed", result.reason)
        self.assertIsNone(result.context["next_earnings_date"])


class G04CustomWindow(unittest.TestCase):
    def test_custom_blackout_days_respected(self):
        # 14-day window; 10 days away should fail.
        result = evaluate(
            "TSLA", _TODAY + timedelta(days=10), today=_TODAY, blackout_days=14
        )
        self.assertEqual(result.outcome, GateOutcome.FAIL)
        # Same date with default 7-day window passes.
        default_window = evaluate("TSLA", _TODAY + timedelta(days=10), today=_TODAY)
        self.assertTrue(default_window.passed)


if __name__ == "__main__":
    unittest.main()
