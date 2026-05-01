"""Tests for trading.goliath.management.triggers.t6_material_news_flag.

Uses dependency-injected is_flagged callable so tests do not touch
the database. The store layer is tested separately.
"""
from __future__ import annotations

import os
import sys
import unittest
from datetime import date, datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))))

from trading.goliath.management import Position, PositionState  # noqa: E402
from trading.goliath.management.triggers.t6_material_news_flag import (  # noqa: E402
    evaluate,
)


def _position(*, letf="TSLL", underlying="TSLA") -> Position:
    return Position(
        position_id="p", instance_name=f"GOLIATH-{letf}",
        letf_ticker=letf, underlying_ticker=underlying,
        state=PositionState.OPEN,
        entered_at=datetime(2026, 5, 4, 14, 30, tzinfo=timezone.utc),
        expiration_date=date(2026, 5, 8),
        short_put_strike=9.0, long_put_strike=8.5, long_call_strike=12.0,
        entry_long_call_cost=0.30, entry_put_spread_credit=0.30,
        entry_net_cost=0.0, defined_max_loss=0.20,
        entry_underlying_gex_regime="POSITIVE",
        current_short_put_mid=0.30, current_long_put_mid=0.05,
        current_long_call_mid=0.30,
        current_underlying_spot=205.0,
        current_underlying_gex_regime="POSITIVE",
    )


class T6Fire(unittest.TestCase):
    def test_fires_when_flag_active_for_underlying(self):
        action = evaluate(_position(underlying="TSLA"), is_flagged=lambda t: t == "TSLA")
        self.assertIsNotNone(action)
        self.assertEqual(action.trigger_id, "T6")
        self.assertTrue(action.closes_everything)
        self.assertEqual(action.context["underlying_ticker"], "TSLA")

    def test_fires_for_each_underlying_independently(self):
        # Flag on MSTR fires for GOLIATH-MSTU, not for GOLIATH-TSLL.
        flagged = {"MSTR"}
        is_flagged = lambda t: t in flagged
        mstu = _position(letf="MSTU", underlying="MSTR")
        tsll = _position(letf="TSLL", underlying="TSLA")
        self.assertIsNotNone(evaluate(mstu, is_flagged=is_flagged))
        self.assertIsNone(evaluate(tsll, is_flagged=is_flagged))


class T6NoFire(unittest.TestCase):
    def test_does_not_fire_when_no_flag(self):
        action = evaluate(_position(), is_flagged=lambda t: False)
        self.assertIsNone(action)

    def test_does_not_fire_for_letf_ticker_only(self):
        # Flag is keyed on underlying -- a flag accidentally set on the
        # LETF ticker should NOT trigger when the position's underlying
        # is something else.
        action = evaluate(
            _position(letf="TSLL", underlying="TSLA"),
            is_flagged=lambda t: t == "TSLL",
        )
        self.assertIsNone(action)


class T6DefaultStore(unittest.TestCase):
    """When is_flagged is not provided, falls back to news_flag_store."""

    def test_uses_default_store_when_none_provided(self):
        # In sandbox without DB, news_flag_store.is_ticker_flagged returns False.
        # So the gate should not fire (no flag).
        action = evaluate(_position())
        self.assertIsNone(action)


if __name__ == "__main__":
    unittest.main()
