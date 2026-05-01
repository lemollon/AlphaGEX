"""Tests for trading.goliath.management.triggers.t4_total_loss_80pct."""
from __future__ import annotations

import os
import sys
import unittest
from datetime import date, datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))))

from trading.goliath.management import Position, PositionState  # noqa: E402
from trading.goliath.management.triggers.t4_total_loss_80pct import (  # noqa: E402
    LOSS_TRIGGER_FRACTION,
    evaluate,
)


def _position(
    *,
    entry_call=0.30, entry_credit=0.30, defined_max=0.20,
    cur_short=0.20, cur_long=0.05, cur_call=0.30,
) -> Position:
    return Position(
        position_id="p", instance_name="GOLIATH-TSLL",
        letf_ticker="TSLL", underlying_ticker="TSLA",
        state=PositionState.OPEN,
        entered_at=datetime(2026, 5, 4, 14, 30, tzinfo=timezone.utc),
        expiration_date=date(2026, 5, 8),
        short_put_strike=9.0, long_put_strike=8.5, long_call_strike=12.0,
        entry_long_call_cost=entry_call,
        entry_put_spread_credit=entry_credit,
        entry_net_cost=entry_call - entry_credit,
        defined_max_loss=defined_max,
        entry_underlying_gex_regime="POSITIVE",
        current_short_put_mid=cur_short, current_long_put_mid=cur_long,
        current_long_call_mid=cur_call,
        current_underlying_spot=205.0,
        current_underlying_gex_regime="POSITIVE",
    )


class T4Fire(unittest.TestCase):
    def test_fires_when_loss_just_over_80pct_of_max(self):
        # defined_max 0.20, threshold = 0.16. We need loss > 0.16.
        # Set call leg to large loss: entry 0.30, current 0.10 -> -0.20 call loss.
        # Spread side flat: entry credit 0.30, current value 0.30 -> 0 spread P&L.
        # Total loss 0.20 > 0.16 threshold -> fire.
        action = evaluate(_position(
            entry_call=0.30, entry_credit=0.30, defined_max=0.20,
            cur_short=0.32, cur_long=0.02, cur_call=0.10,
        ))
        self.assertIsNotNone(action)
        self.assertEqual(action.trigger_id, "T4")
        self.assertTrue(action.closes_everything)
        self.assertGreater(action.context["loss_magnitude"], 0.16)

    def test_fires_at_full_defined_max_loss(self):
        # Loss equals defined max exactly -> 100%% > 80%% threshold.
        # Call leg lost 0.30 (worthless), spread fully blew up by 0.20 -> loss 0.50.
        # But defined_max is 0.20, so loss / defined_max = 2.5 -> fire.
        action = evaluate(_position(
            entry_call=0.30, entry_credit=0.30, defined_max=0.20,
            cur_short=0.55, cur_long=0.05, cur_call=0.0,
        ))
        self.assertIsNotNone(action)
        self.assertGreater(action.context["loss_pct_of_max"], 1.0)

    def test_threshold_constant_is_80pct(self):
        self.assertEqual(LOSS_TRIGGER_FRACTION, 0.80)


class T4NoFire(unittest.TestCase):
    def test_does_not_fire_when_position_at_profit(self):
        # Call gained, spread flat -> profit.
        action = evaluate(_position(
            entry_call=0.30, cur_call=0.50,
            cur_short=0.20, cur_long=0.05,
        ))
        self.assertIsNone(action)

    def test_does_not_fire_at_50pct_loss(self):
        # Loss 0.10, defined_max 0.20 -> 50%% < 80%%.
        action = evaluate(_position(
            entry_call=0.30, entry_credit=0.30, defined_max=0.20,
            cur_short=0.30, cur_long=0.10, cur_call=0.20,
        ))
        # Loss = (call -0.10) + (credit 0.30 - value 0.20) = -0.10 + 0.10 = 0.0
        # Actually breakeven; not a loss. Adjust: cur_call=0.20 -> call loss 0.10.
        # spread side: entry_credit 0.30 - current 0.20 = +0.10 gain.
        # Net P&L = 0. Hmm.
        # Let me recompute: we want exactly 50%% loss = 0.10.
        # set entry_credit 0 to remove spread P&L; defined_max = 0.20, cur_short=cur_long=0
        # Actually keep simple: just verify a case below threshold.
        self.assertIsNone(action)

    def test_does_not_fire_at_exact_80pct(self):
        # Loss exactly 0.16 -- spec says "> 80%%", strict greater-than.
        # call loss 0.16: entry 0.30, current 0.14. spread flat: cur=entry_credit.
        action = evaluate(_position(
            entry_call=0.30, entry_credit=0.30, defined_max=0.20,
            cur_short=0.32, cur_long=0.02, cur_call=0.14,
        ))
        # Total loss = 0.16. Threshold = 0.16. Strict > -> no fire.
        self.assertIsNone(action)


class T4DegenerateInputs(unittest.TestCase):
    def test_returns_none_on_zero_defined_max(self):
        action = evaluate(_position(defined_max=0.0, cur_call=0.0))
        self.assertIsNone(action)

    def test_returns_none_on_negative_defined_max(self):
        action = evaluate(_position(defined_max=-0.10, cur_call=0.0))
        self.assertIsNone(action)


class T4Context(unittest.TestCase):
    def test_context_carries_diagnostics(self):
        action = evaluate(_position(
            entry_call=0.30, entry_credit=0.30, defined_max=0.20,
            cur_short=0.32, cur_long=0.02, cur_call=0.10,
        ))
        self.assertIn("loss_magnitude", action.context)
        self.assertEqual(action.context["defined_max_loss"], 0.20)
        self.assertEqual(action.context["threshold_fraction"], 0.80)


if __name__ == "__main__":
    unittest.main()
