"""Tests for trading.goliath.management.triggers.t2_call_5x."""
from __future__ import annotations

import os
import sys
import unittest
from datetime import date, datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))))

from trading.goliath.management import Position, PositionState  # noqa: E402
from trading.goliath.management.triggers.t2_call_5x import (  # noqa: E402
    CALL_HARD_PROFIT_MULTIPLIER,
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


class T2Fire(unittest.TestCase):
    def test_fires_at_exact_5x(self):
        action = evaluate(_position(entry_call_cost=0.30, current_call_mid=1.50))
        self.assertIsNotNone(action)
        self.assertEqual(action.trigger_id, "T2")
        self.assertTrue(action.close_call)
        self.assertTrue(action.close_put_spread)
        self.assertTrue(action.closes_everything)

    def test_fires_above_5x(self):
        action = evaluate(_position(entry_call_cost=0.20, current_call_mid=2.00))
        self.assertIsNotNone(action)
        self.assertAlmostEqual(action.context["multiple"], 10.0)

    def test_threshold_constant_is_5(self):
        self.assertEqual(CALL_HARD_PROFIT_MULTIPLIER, 5.0)


class T2NoFire(unittest.TestCase):
    def test_does_not_fire_below_5x(self):
        # 3.99x -- below threshold; T1 would fire here, T2 would not.
        action = evaluate(_position(entry_call_cost=0.30, current_call_mid=1.197))
        self.assertIsNone(action)

    def test_does_not_fire_at_3x(self):
        action = evaluate(_position(entry_call_cost=0.30, current_call_mid=0.90))
        self.assertIsNone(action)

    def test_does_not_fire_when_call_at_loss(self):
        action = evaluate(_position(entry_call_cost=0.30, current_call_mid=0.10))
        self.assertIsNone(action)


class T2DegenerateInputs(unittest.TestCase):
    def test_returns_none_on_zero_entry_cost(self):
        action = evaluate(_position(entry_call_cost=0.0, current_call_mid=2.00))
        self.assertIsNone(action)

    def test_returns_none_on_negative_entry_cost(self):
        action = evaluate(_position(entry_call_cost=-0.05, current_call_mid=2.00))
        self.assertIsNone(action)


class T2Context(unittest.TestCase):
    def test_context_carries_diagnostics(self):
        action = evaluate(_position(entry_call_cost=0.40, current_call_mid=2.40))
        self.assertEqual(action.context["entry_long_call_cost"], 0.40)
        self.assertEqual(action.context["current_long_call_mid"], 2.40)
        self.assertAlmostEqual(action.context["multiple"], 6.0)
        self.assertEqual(action.context["threshold_multiple"], 5.0)


if __name__ == "__main__":
    unittest.main()
