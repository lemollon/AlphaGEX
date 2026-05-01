"""Tests for trading.goliath.instance."""
from __future__ import annotations

import os
import sys
import unittest
from datetime import date, datetime, timezone
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from trading.goliath.configs import InstanceConfig, get  # noqa: E402
from trading.goliath.instance import GoliathInstance, build_all_instances  # noqa: E402
from trading.goliath.management.state import Position, PositionState  # noqa: E402


def _position(*, position_id="p1", defined_max=0.20, contracts=1) -> Position:
    p = Position(
        position_id=position_id, instance_name="GOLIATH-MSTU",
        letf_ticker="MSTU", underlying_ticker="MSTR",
        state=PositionState.OPEN,
        entered_at=datetime(2026, 5, 4, 14, 30, tzinfo=timezone.utc),
        expiration_date=date(2026, 5, 8),
        short_put_strike=9.0, long_put_strike=8.5, long_call_strike=12.0,
        entry_long_call_cost=0.30, entry_put_spread_credit=0.30,
        entry_net_cost=0.0, defined_max_loss=defined_max,
        entry_underlying_gex_regime="POSITIVE",
        current_short_put_mid=0.30, current_long_put_mid=0.05,
        current_long_call_mid=0.30,
        current_underlying_spot=200.0,
        current_underlying_gex_regime="POSITIVE",
    )
    # Position has no `contracts` field by default; attach via setattr to
    # exercise the getattr-default path in open_dollars_at_risk.
    if contracts != 1:
        object.__setattr__(p, "contracts", contracts)
    return p


class IdentityProperties(unittest.TestCase):
    def test_name_letf_underlying(self):
        inst = GoliathInstance(config=get("GOLIATH-MSTU"))
        self.assertEqual(inst.name, "GOLIATH-MSTU")
        self.assertEqual(inst.letf_ticker, "MSTU")
        self.assertEqual(inst.underlying_ticker, "MSTR")


class PositionAggregates(unittest.TestCase):
    def test_open_count_starts_zero(self):
        inst = GoliathInstance(config=get("GOLIATH-MSTU"))
        self.assertEqual(inst.open_count, 0)

    def test_dollars_at_risk_uses_multiplier(self):
        # defined_max_loss=0.20 per contract * 100 multiplier = $20/contract.
        inst = GoliathInstance(config=get("GOLIATH-MSTU"))
        inst.add_position(_position(defined_max=0.20))
        self.assertAlmostEqual(inst.open_dollars_at_risk(), 20.0)

    def test_dollars_at_risk_scales_with_contracts(self):
        inst = GoliathInstance(config=get("GOLIATH-MSTU"))
        inst.add_position(_position(defined_max=0.20, contracts=2))
        self.assertAlmostEqual(inst.open_dollars_at_risk(), 40.0)

    def test_multiplier_override(self):
        inst = GoliathInstance(config=get("GOLIATH-MSTU"))
        inst.add_position(_position(defined_max=0.20))
        # multiplier=1 -> raw 0.20.
        self.assertAlmostEqual(inst.open_dollars_at_risk(multiplier=1), 0.20)


class CapacityCheck(unittest.TestCase):
    def test_has_capacity_when_empty_and_not_killed(self):
        with patch("trading.goliath.instance.is_killed", return_value=False):
            inst = GoliathInstance(config=get("GOLIATH-MSTU"))
            self.assertTrue(inst.has_capacity_for_new_trade())

    def test_no_capacity_when_killed(self):
        with patch("trading.goliath.instance.is_killed", return_value=True):
            inst = GoliathInstance(config=get("GOLIATH-MSTU"))
            self.assertFalse(inst.has_capacity_for_new_trade())

    def test_no_capacity_at_or_above_allocation_cap(self):
        # MSTU cap = $200; saturate it: defined_max=2.00 (which becomes
        # $200 with multiplier 100).
        with patch("trading.goliath.instance.is_killed", return_value=False):
            inst = GoliathInstance(config=get("GOLIATH-MSTU"))
            inst.add_position(_position(defined_max=2.00))
            self.assertFalse(inst.has_capacity_for_new_trade())


class PositionLifecycle(unittest.TestCase):
    def test_add_remove_find(self):
        inst = GoliathInstance(config=get("GOLIATH-MSTU"))
        inst.add_position(_position(position_id="p1"))
        inst.add_position(_position(position_id="p2"))

        self.assertEqual(inst.open_count, 2)
        self.assertEqual(inst.find_position("p1").position_id, "p1")
        self.assertIsNone(inst.find_position("ghost"))

        self.assertTrue(inst.remove_position("p1"))
        self.assertEqual(inst.open_count, 1)
        self.assertFalse(inst.remove_position("p1"))  # already gone


class BuildAllInstances(unittest.TestCase):
    def test_returns_5_instances(self):
        from trading.goliath.configs import all_instances
        instances = build_all_instances(all_instances())
        self.assertEqual(len(instances), 5)
        self.assertIn("GOLIATH-MSTU", instances)
        for inst in instances.values():
            self.assertEqual(inst.open_count, 0)


if __name__ == "__main__":
    unittest.main()
