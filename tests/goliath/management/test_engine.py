"""Tests for trading.goliath.management.engine."""
from __future__ import annotations

import os
import sys
import unittest
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from trading.goliath.management import Position, PositionState  # noqa: E402
from trading.goliath.management.engine import evaluate_all  # noqa: E402

_ET = ZoneInfo("America/New_York")
_FRIDAY = date(2026, 5, 8)
_NEVER_FLAGGED = lambda t: False
_NORMAL_NOW = datetime(2026, 5, 5, 14, 0, tzinfo=_ET)  # Tue 2pm ET, no T7/T5 fire


def _position(**overrides) -> Position:
    base = dict(
        position_id="p", instance_name="GOLIATH-TSLL",
        letf_ticker="TSLL", underlying_ticker="TSLA",
        state=PositionState.OPEN,
        entered_at=datetime(2026, 5, 4, 14, 30, tzinfo=timezone.utc),
        expiration_date=_FRIDAY,
        short_put_strike=9.0, long_put_strike=8.5, long_call_strike=12.0,
        entry_long_call_cost=0.30, entry_put_spread_credit=0.30,
        entry_net_cost=0.0, defined_max_loss=0.20,
        entry_underlying_gex_regime="POSITIVE",
        current_short_put_mid=0.30, current_long_put_mid=0.05,
        current_long_call_mid=0.30,
        current_underlying_spot=205.0,
        current_underlying_gex_regime="POSITIVE",
        current_letf_spot=10.0,
    )
    base.update(overrides)
    return Position(**base)


class NoTriggerFires(unittest.TestCase):
    def test_quiet_position_returns_none(self):
        action = evaluate_all(_position(), now=_NORMAL_NOW, is_flagged=_NEVER_FLAGGED)
        self.assertIsNone(action)


class PriorityOrder(unittest.TestCase):
    def test_t7_preempts_everything(self):
        # Set a position that would also trigger T1 (call at 3x).
        thursday_3pm = datetime(2026, 5, 7, 15, 0, tzinfo=_ET)
        action = evaluate_all(
            _position(current_long_call_mid=0.90),
            now=thursday_3pm, is_flagged=_NEVER_FLAGGED,
        )
        self.assertEqual(action.trigger_id, "T7")

    def test_t6_preempts_t4(self):
        # Big loss + flag -> T6 first (manual news).
        action = evaluate_all(
            _position(current_long_call_mid=0.0,
                      current_short_put_mid=0.55, current_long_put_mid=0.05),
            now=_NORMAL_NOW, is_flagged=lambda t: True,
        )
        self.assertEqual(action.trigger_id, "T6")

    def test_t5_preempts_t4(self):
        # Strike breached + huge loss simultaneously -> T5 first.
        action = evaluate_all(
            _position(current_letf_spot=8.0, current_long_call_mid=0.0,
                      current_short_put_mid=0.55, current_long_put_mid=0.05,
                      expiration_date=date(2026, 5, 8)),
            now=datetime(2026, 5, 7, 10, 0, tzinfo=_ET),  # Thu morning; 1 DTE
            is_flagged=_NEVER_FLAGGED,
        )
        self.assertEqual(action.trigger_id, "T5")

    def test_t4_preempts_t8(self):
        # Adverse flip + 80%% loss -> T4 first.
        action = evaluate_all(
            _position(current_long_call_mid=0.0,
                      current_short_put_mid=0.50, current_long_put_mid=0.02,
                      current_underlying_gex_regime="NEGATIVE"),
            now=_NORMAL_NOW, is_flagged=_NEVER_FLAGGED,
        )
        self.assertEqual(action.trigger_id, "T4")

    def test_t2_preempts_t1(self):
        # Call at 5x -> both T1 and T2 fire; engine picks T2 (close all).
        action = evaluate_all(
            _position(current_long_call_mid=1.50),
            now=_NORMAL_NOW, is_flagged=_NEVER_FLAGGED,
        )
        self.assertEqual(action.trigger_id, "T2")

    def test_t1_only_when_call_between_3x_and_5x(self):
        action = evaluate_all(
            _position(current_long_call_mid=1.20),  # 4x
            now=_NORMAL_NOW, is_flagged=_NEVER_FLAGGED,
        )
        self.assertEqual(action.trigger_id, "T1")


class IndividualTriggers(unittest.TestCase):
    def test_t3_fires_when_only_spread_profit(self):
        action = evaluate_all(
            _position(current_short_put_mid=0.10, current_long_put_mid=0.0),
            now=_NORMAL_NOW, is_flagged=_NEVER_FLAGGED,
        )
        # Spread value 0.10, threshold for T3: 0.5 * 0.30 = 0.15. 0.10 <= 0.15 -> fire.
        self.assertEqual(action.trigger_id, "T3")

    def test_t8_fires_on_adverse_flip(self):
        action = evaluate_all(
            _position(current_underlying_gex_regime="NEGATIVE"),
            now=_NORMAL_NOW, is_flagged=_NEVER_FLAGGED,
        )
        self.assertEqual(action.trigger_id, "T8")


if __name__ == "__main__":
    unittest.main()
