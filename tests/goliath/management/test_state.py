"""Tests for trading.goliath.management.state."""
from __future__ import annotations

import os
import sys
import unittest
from datetime import date, datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from trading.goliath.management import (  # noqa: E402
    ManagementAction,
    Position,
    PositionState,
)


def _position(**overrides) -> Position:
    base = dict(
        position_id="pos-1",
        instance_name="GOLIATH-TSLL",
        letf_ticker="TSLL",
        underlying_ticker="TSLA",
        state=PositionState.OPEN,
        entered_at=datetime(2026, 5, 4, 14, 30, tzinfo=timezone.utc),
        expiration_date=date(2026, 5, 8),
        short_put_strike=9.0,
        long_put_strike=8.5,
        long_call_strike=12.0,
        entry_long_call_cost=0.30,
        entry_put_spread_credit=0.30,
        entry_net_cost=0.00,
        defined_max_loss=0.20,  # spread width 0.5 - credit 0.30
        entry_underlying_gex_regime="POSITIVE",
        current_short_put_mid=0.40,
        current_long_put_mid=0.10,
        current_long_call_mid=0.45,
        current_underlying_spot=205.0,
        current_underlying_gex_regime="POSITIVE",
    )
    base.update(overrides)
    return Position(**base)


class PositionStateMachine(unittest.TestCase):
    def test_states_in_lifecycle_order(self):
        order = [
            PositionState.OPEN, PositionState.MANAGING,
            PositionState.CLOSING, PositionState.CLOSED,
        ]
        self.assertEqual([s.value for s in order],
                         ["OPEN", "MANAGING", "CLOSING", "CLOSED"])


class PositionDerivedFields(unittest.TestCase):
    def test_current_put_spread_value(self):
        p = _position()
        self.assertAlmostEqual(p.current_put_spread_value, 0.30)

    def test_current_net_position_value(self):
        # long_call 0.45 + (entry_credit 0.30 - current_spread_value 0.30)
        # = 0.45 + 0.00 = 0.45
        p = _position()
        self.assertAlmostEqual(p.current_net_position_value, 0.45)

    def test_current_total_pnl(self):
        # current_net_value 0.45 - entry_long_call_cost 0.30 = +0.15
        p = _position()
        self.assertAlmostEqual(p.current_total_pnl, 0.15)


class ManagementActionFlags(unittest.TestCase):
    def test_closes_everything_when_both_set(self):
        a = ManagementAction("T2", close_call=True, close_put_spread=True, reason="x")
        self.assertTrue(a.closes_everything)
        self.assertTrue(a.closes_anything)

    def test_closes_anything_when_only_call(self):
        a = ManagementAction("T1", close_call=True, close_put_spread=False, reason="x")
        self.assertTrue(a.closes_anything)
        self.assertFalse(a.closes_everything)

    def test_closes_anything_when_only_spread(self):
        a = ManagementAction("T3", close_call=False, close_put_spread=True, reason="x")
        self.assertTrue(a.closes_anything)
        self.assertFalse(a.closes_everything)

    def test_no_close_neither_flag(self):
        a = ManagementAction("noop", close_call=False, close_put_spread=False, reason="x")
        self.assertFalse(a.closes_anything)
        self.assertFalse(a.closes_everything)


if __name__ == "__main__":
    unittest.main()
