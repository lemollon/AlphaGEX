"""Tests for trading.goliath.management.triggers.t1_call_3x."""
from __future__ import annotations

import os
import sys
import unittest
from datetime import date, datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))))

from trading.goliath.management import Position, PositionState  # noqa: E402
from trading.goliath.management.triggers.t1_call_3x import (  # noqa: E402
    CALL_PROFIT_MULTIPLIER,
    evaluate,
)


def _position(*, entry_call_cost=0.30, current_call_mid=0.30) -> Position:
    return Position(
        position_id="p", instance_name="GOLIATH-TSLL",
        letf_ticker="TSLL", underlying_ticker="TSLA",
        state=PositionState.OPEN,
        entered_at=datetime(2026, 5, 4, 14, 30, tzinfo=timezone.utc),
        expiration_date=date(2026, 5, 8),
        short_put_strike=9.0, long_put_strike=8.5, long_call_strike=12.0,
        entry_long_call_cost=entry_call_cost,
        entry_put_spread_credit=0.30, entry_net_cost=0.0, defined_max_loss=0.20,
        entry_underlying_gex_regime="POSITIVE",
        current_short_put_mid=0.40, current_long_put_mid=0.10,
        current_long_call_mid=current_call_mid,
        current_underlying_spot=205.0,
        current_underlying_gex_regime="POSITIVE",
    )


class T1Fire(unittest.TestCase):
    def test_fires_at_exact_3x(self):
        action = evaluate(_position(entry_call_cost=0.30, current_call_mid=0.90))
        self.assertIsNotNone(action)
        self.assertEqual(action.trigger_id, "T1")
        self.assertTrue(action.close_call)
        self.assertFalse(action.close_put_spread)
        self.assertFalse(action.closes_everything)

    def test_fires_above_3x(self):
        action = evaluate(_position(entry_call_cost=0.30, current_call_mid=1.20))
        self.assertIsNotNone(action)
        self.assertAlmostEqual(action.context["multiple"], 4.0)

    def test_threshold_constant_is_3(self):
        self.assertEqual(CALL_PROFIT_MULTIPLIER, 3.0)


class T1NoFire(unittest.TestCase):
    def test_does_not_fire_below_3x(self):
        action = evaluate(_position(entry_call_cost=0.30, current_call_mid=0.85))
        self.assertIsNone(action)

    def test_does_not_fire_when_call_at_loss(self):
        action = evaluate(_position(entry_call_cost=0.30, current_call_mid=0.10))
        self.assertIsNone(action)

    def test_does_not_fire_at_entry_cost(self):
        action = evaluate(_position(entry_call_cost=0.30, current_call_mid=0.30))
        self.assertIsNone(action)


class T1DegenerateInputs(unittest.TestCase):
    def test_returns_none_on_zero_entry_cost(self):
        action = evaluate(_position(entry_call_cost=0.0, current_call_mid=1.00))
        self.assertIsNone(action)

    def test_returns_none_on_negative_entry_cost(self):
        action = evaluate(_position(entry_call_cost=-0.05, current_call_mid=1.00))
        self.assertIsNone(action)


class T1Context(unittest.TestCase):
    def test_context_carries_diagnostics(self):
        action = evaluate(_position(entry_call_cost=0.40, current_call_mid=1.60))
        self.assertEqual(action.context["entry_long_call_cost"], 0.40)
        self.assertEqual(action.context["current_long_call_mid"], 1.60)
        self.assertAlmostEqual(action.context["multiple"], 4.0)
        self.assertEqual(action.context["threshold_multiple"], 3.0)


if __name__ == "__main__":
    unittest.main()
