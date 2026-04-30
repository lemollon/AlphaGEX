"""Tests for trading.goliath.management.triggers.t8_underlying_gex_flip."""
from __future__ import annotations

import os
import sys
import unittest
from datetime import date, datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))))

from trading.goliath.management import Position, PositionState  # noqa: E402
from trading.goliath.management.triggers.t8_underlying_gex_flip import (  # noqa: E402
    evaluate,
)


def _position(*, entry: str, current: str) -> Position:
    return Position(
        position_id="p", instance_name="GOLIATH-TSLL",
        letf_ticker="TSLL", underlying_ticker="TSLA",
        state=PositionState.OPEN,
        entered_at=datetime(2026, 5, 4, 14, 30, tzinfo=timezone.utc),
        expiration_date=date(2026, 5, 8),
        short_put_strike=9.0, long_put_strike=8.5, long_call_strike=12.0,
        entry_long_call_cost=0.30, entry_put_spread_credit=0.30,
        entry_net_cost=0.0, defined_max_loss=0.20,
        entry_underlying_gex_regime=entry,
        current_short_put_mid=0.30, current_long_put_mid=0.05,
        current_long_call_mid=0.30,
        current_underlying_spot=205.0,
        current_underlying_gex_regime=current,
    )


class T8AdverseFlipsFire(unittest.TestCase):
    def test_positive_to_negative_fires(self):
        action = evaluate(_position(entry="POSITIVE", current="NEGATIVE"))
        self.assertIsNotNone(action)
        self.assertEqual(action.trigger_id, "T8")
        self.assertTrue(action.closes_everything)

    def test_neutral_to_negative_fires(self):
        action = evaluate(_position(entry="NEUTRAL", current="NEGATIVE"))
        self.assertIsNotNone(action)


class T8NonAdverseTransitions(unittest.TestCase):
    def test_no_flip_no_fire(self):
        self.assertIsNone(evaluate(_position(entry="POSITIVE", current="POSITIVE")))
        self.assertIsNone(evaluate(_position(entry="NEUTRAL", current="NEUTRAL")))

    def test_positive_to_neutral_no_fire(self):
        # Soft transition; spec lets T4/T5/later T8 catch it if it worsens.
        self.assertIsNone(evaluate(_position(entry="POSITIVE", current="NEUTRAL")))

    def test_neutral_to_positive_no_fire(self):
        # Improvement, not adverse.
        self.assertIsNone(evaluate(_position(entry="NEUTRAL", current="POSITIVE")))

    def test_negative_to_negative_no_fire(self):
        # We shouldn't have entered if we were already negative (G02 would
        # have failed). Defensive: still no fire.
        self.assertIsNone(evaluate(_position(entry="NEGATIVE", current="NEGATIVE")))

    def test_negative_to_positive_no_fire(self):
        # Recovering -- not adverse.
        self.assertIsNone(evaluate(_position(entry="NEGATIVE", current="POSITIVE")))


class T8Context(unittest.TestCase):
    def test_context_carries_regime_transition(self):
        action = evaluate(_position(entry="POSITIVE", current="NEGATIVE"))
        self.assertEqual(action.context["entry_underlying_gex_regime"], "POSITIVE")
        self.assertEqual(action.context["current_underlying_gex_regime"], "NEGATIVE")
        self.assertEqual(action.context["underlying_ticker"], "TSLA")


if __name__ == "__main__":
    unittest.main()
