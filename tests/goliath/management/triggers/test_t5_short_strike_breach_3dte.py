"""Tests for trading.goliath.management.triggers.t5_short_strike_breach_3dte."""
from __future__ import annotations

import os
import sys
import unittest
from datetime import date, datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))))

from trading.goliath.management import Position, PositionState  # noqa: E402
from trading.goliath.management.triggers.t5_short_strike_breach_3dte import (  # noqa: E402
    DTE_THRESHOLD,
    evaluate,
)


_NOW = datetime(2026, 5, 6, 14, 30, tzinfo=timezone.utc)  # Wed
_FRIDAY = date(2026, 5, 8)


def _position(*, short_put=9.0, letf_spot=10.0, exp=_FRIDAY) -> Position:
    return Position(
        position_id="p", instance_name="GOLIATH-TSLL",
        letf_ticker="TSLL", underlying_ticker="TSLA",
        state=PositionState.OPEN,
        entered_at=datetime(2026, 5, 4, 14, 30, tzinfo=timezone.utc),
        expiration_date=exp,
        short_put_strike=short_put, long_put_strike=short_put - 0.5,
        long_call_strike=12.0,
        entry_long_call_cost=0.30, entry_put_spread_credit=0.30,
        entry_net_cost=0.0, defined_max_loss=0.20,
        entry_underlying_gex_regime="POSITIVE",
        current_short_put_mid=0.30, current_long_put_mid=0.05,
        current_long_call_mid=0.30,
        current_underlying_spot=200.0,
        current_underlying_gex_regime="POSITIVE",
        current_letf_spot=letf_spot,
    )


class T5Fire(unittest.TestCase):
    def test_fires_when_breached_and_in_dte_window(self):
        # _NOW = Wed May 6, exp = Fri May 8 -> 2 DTE. LETF spot 8.50 <= short 9.0.
        action = evaluate(_position(short_put=9.0, letf_spot=8.50), now=_NOW)
        self.assertIsNotNone(action)
        self.assertEqual(action.trigger_id, "T5")
        self.assertTrue(action.closes_everything)
        self.assertEqual(action.context["dte"], 2)

    def test_fires_at_exact_strike(self):
        # LETF at exact strike -> breach (<=).
        action = evaluate(_position(short_put=9.0, letf_spot=9.0), now=_NOW)
        self.assertIsNotNone(action)

    def test_fires_at_dte_threshold_boundary(self):
        # 3 DTE exactly -> in window (<=).
        now = datetime(2026, 5, 5, 14, 30, tzinfo=timezone.utc)  # Tue
        action = evaluate(_position(short_put=9.0, letf_spot=8.0), now=now)
        self.assertIsNotNone(action)
        self.assertEqual(action.context["dte"], 3)


class T5NoFire(unittest.TestCase):
    def test_does_not_fire_when_not_breached(self):
        # LETF 9.50 > short 9.0 -> not breached.
        action = evaluate(_position(short_put=9.0, letf_spot=9.50), now=_NOW)
        self.assertIsNone(action)

    def test_does_not_fire_when_outside_dte_window(self):
        # Breach but 4 DTE -> outside <= 3 window.
        now = datetime(2026, 5, 4, 14, 30, tzinfo=timezone.utc)  # Mon
        action = evaluate(_position(short_put=9.0, letf_spot=8.0), now=now)
        self.assertIsNone(action)

    def test_does_not_fire_when_letf_spot_unknown(self):
        # Default current_letf_spot=0 -> can't evaluate; defer.
        action = evaluate(_position(short_put=9.0, letf_spot=0.0), now=_NOW)
        self.assertIsNone(action)


class T5DTEEdges(unittest.TestCase):
    def test_dte_threshold_constant(self):
        self.assertEqual(DTE_THRESHOLD, 3)

    def test_dte_zero_at_expiration(self):
        # _NOW shifted to Friday morning -> 0 DTE.
        now = datetime(2026, 5, 8, 9, 30, tzinfo=timezone.utc)
        action = evaluate(_position(short_put=9.0, letf_spot=8.0), now=now)
        self.assertIsNotNone(action)
        self.assertEqual(action.context["dte"], 0)


class T5Context(unittest.TestCase):
    def test_context_carries_diagnostics(self):
        action = evaluate(_position(short_put=9.0, letf_spot=8.50), now=_NOW)
        self.assertEqual(action.context["short_put_strike"], 9.0)
        self.assertEqual(action.context["current_letf_spot"], 8.50)
        self.assertAlmostEqual(action.context["breach_distance"], -0.50)
        self.assertEqual(action.context["dte_threshold"], 3)


if __name__ == "__main__":
    unittest.main()
