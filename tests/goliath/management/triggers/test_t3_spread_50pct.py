"""Tests for trading.goliath.management.triggers.t3_spread_50pct."""
from __future__ import annotations

import os
import sys
import unittest
from datetime import date, datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))))

from trading.goliath.management import Position, PositionState  # noqa: E402
from trading.goliath.management.triggers.t3_spread_50pct import (  # noqa: E402
    PROFIT_CAPTURE_FRACTION,
    evaluate,
)


def _position(*, entry_credit=0.30, current_short=0.20, current_long=0.05) -> Position:
    return Position(
        position_id="p", instance_name="GOLIATH-TSLL",
        letf_ticker="TSLL", underlying_ticker="TSLA",
        state=PositionState.OPEN,
        entered_at=datetime(2026, 5, 4, 14, 30, tzinfo=timezone.utc),
        expiration_date=date(2026, 5, 8),
        short_put_strike=9.0, long_put_strike=8.5, long_call_strike=12.0,
        entry_long_call_cost=0.30,
        entry_put_spread_credit=entry_credit,
        entry_net_cost=0.0, defined_max_loss=0.20,
        entry_underlying_gex_regime="POSITIVE",
        current_short_put_mid=current_short,
        current_long_put_mid=current_long,
        current_long_call_mid=0.45,
        current_underlying_spot=205.0,
        current_underlying_gex_regime="POSITIVE",
    )


class T3Fire(unittest.TestCase):
    def test_fires_at_exact_50pct(self):
        # entry_credit 0.30; threshold = 0.5 * 0.30 = 0.15.
        # current value 0.15 (short 0.20 - long 0.05) -> exactly at threshold.
        action = evaluate(_position(entry_credit=0.30, current_short=0.20, current_long=0.05))
        self.assertIsNotNone(action)
        self.assertEqual(action.trigger_id, "T3")
        self.assertTrue(action.close_put_spread)
        self.assertFalse(action.close_call)
        self.assertAlmostEqual(action.context["profit_pct_of_max"], 0.50)

    def test_fires_above_50pct(self):
        # current value 0.10 (short 0.12 - long 0.02) -> 67%% captured.
        action = evaluate(_position(entry_credit=0.30, current_short=0.12, current_long=0.02))
        self.assertIsNotNone(action)
        self.assertGreater(action.context["profit_pct_of_max"], 0.66)

    def test_fires_at_full_capture(self):
        # current value 0 -> 100%% captured.
        action = evaluate(_position(entry_credit=0.30, current_short=0.05, current_long=0.05))
        self.assertIsNotNone(action)
        self.assertAlmostEqual(action.context["profit_pct_of_max"], 1.0, places=4)


class T3NoFire(unittest.TestCase):
    def test_does_not_fire_at_25pct_capture(self):
        # current value 0.225 -> 25%% captured (below 50%% threshold).
        action = evaluate(_position(entry_credit=0.30, current_short=0.25, current_long=0.025))
        self.assertIsNone(action)

    def test_does_not_fire_when_spread_at_loss(self):
        # current value 0.40 > entry credit 0.30 -> we're losing on the spread.
        action = evaluate(_position(entry_credit=0.30, current_short=0.45, current_long=0.05))
        self.assertIsNone(action)

    def test_does_not_fire_just_below_50pct(self):
        action = evaluate(_position(entry_credit=0.30, current_short=0.20, current_long=0.04))
        # current_value = 0.16, threshold = 0.15 -> still above threshold.
        self.assertIsNone(action)


class T3DegenerateInputs(unittest.TestCase):
    def test_returns_none_on_zero_entry_credit(self):
        self.assertIsNone(evaluate(_position(entry_credit=0.0)))

    def test_returns_none_on_debit_entry(self):
        # Negative entry credit means the spread was a debit at entry.
        self.assertIsNone(evaluate(_position(entry_credit=-0.10)))


class T3Context(unittest.TestCase):
    def test_context_carries_diagnostics(self):
        action = evaluate(_position(entry_credit=0.40, current_short=0.15, current_long=0.05))
        self.assertEqual(action.context["entry_put_spread_credit"], 0.40)
        self.assertAlmostEqual(action.context["current_put_spread_value"], 0.10)
        self.assertAlmostEqual(action.context["profit_captured"], 0.30)
        self.assertEqual(action.context["threshold_fraction"], PROFIT_CAPTURE_FRACTION)


if __name__ == "__main__":
    unittest.main()
