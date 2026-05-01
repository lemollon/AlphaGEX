"""Tests for trading.goliath.equity_snapshots."""
from __future__ import annotations

import os
import sys
import unittest
from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from trading.goliath import equity_snapshots  # noqa: E402
from trading.goliath.configs import all_instances, get  # noqa: E402
from trading.goliath.instance import GoliathInstance, build_all_instances  # noqa: E402
from trading.goliath.management.state import Position, PositionState  # noqa: E402


def _open_pos(defined_max=0.20, current_call=0.45, current_short=0.20, current_long=0.05) -> Position:
    return Position(
        position_id="p1", instance_name="GOLIATH-MSTU",
        letf_ticker="MSTU", underlying_ticker="MSTR",
        state=PositionState.OPEN,
        entered_at=datetime(2026, 5, 4, 14, 30, tzinfo=timezone.utc),
        expiration_date=date(2026, 5, 8),
        short_put_strike=9.0, long_put_strike=8.5, long_call_strike=12.0,
        entry_long_call_cost=0.30, entry_put_spread_credit=0.30,
        entry_net_cost=0.0, defined_max_loss=defined_max,
        entry_underlying_gex_regime="POSITIVE",
        current_short_put_mid=current_short, current_long_put_mid=current_long,
        current_long_call_mid=current_call,
        current_underlying_spot=200.0,
        current_underlying_gex_regime="POSITIVE",
    )


class SafeFallbackWithoutDB(unittest.TestCase):
    def test_returns_zero_without_db(self):
        with patch("trading.goliath.equity_snapshots._connect",
                   return_value=(None, False)):
            instances = build_all_instances(all_instances())
            self.assertEqual(equity_snapshots.write_snapshots(instances), 0)


class WritesPerInstanceAndPlatform(unittest.TestCase):
    def test_writes_5_instances_plus_1_platform(self):
        # Track INSERT calls.
        inserts: list = []

        class _Cur:
            def execute(self, sql, args):
                inserts.append((sql, args))
            def close(self):
                pass
            def fetchone(self):
                # _instance_realized_pnl SELECT returns 0
                return (0,)

        class _Conn:
            def cursor(self):
                return _Cur()
            def commit(self):
                pass
            def close(self):
                pass

        with patch("trading.goliath.equity_snapshots._connect",
                   return_value=(_Conn(), True)):
            instances = build_all_instances(all_instances())
            written = equity_snapshots.write_snapshots(instances)

        # 5 instances + 1 platform = 6 INSERT calls (plus 5 SELECT calls
        # for realized_pnl). Total execute calls = 11.
        # Filter to INSERTs only.
        insert_calls = [c for c in inserts if "INSERT" in c[0]]
        self.assertEqual(len(insert_calls), 6)
        self.assertEqual(written, 6)

        # Verify scope distribution.
        scopes = [c[1][0] for c in insert_calls]
        self.assertEqual(scopes.count("INSTANCE"), 5)
        self.assertEqual(scopes.count("PLATFORM"), 1)


class UnrealizedPnLAggregation(unittest.TestCase):
    def test_unrealized_uses_position_total_pnl(self):
        inst = GoliathInstance(config=get("GOLIATH-MSTU"))
        # Profit position: call gained, spread flat -> total_pnl positive.
        # current_total_pnl = (current_long_call_mid - entry_long_call_cost)
        #                   + (entry_put_spread_credit - current_put_spread_value)
        # = (0.45 - 0.30) + (0.30 - (0.20 - 0.05)) = 0.15 + 0.15 = 0.30
        inst.add_position(_open_pos())
        # multiplier 100 -> $30 unrealized.
        unrealized = equity_snapshots._instance_unrealized_pnl(inst)
        self.assertAlmostEqual(unrealized, 30.0, places=2)

    def test_no_open_positions_returns_zero(self):
        inst = GoliathInstance(config=get("GOLIATH-MSTU"))
        self.assertEqual(equity_snapshots._instance_unrealized_pnl(inst), 0.0)


class StartingCapitalLookup(unittest.TestCase):
    def test_known_instance_returns_allocation_cap(self):
        self.assertEqual(equity_snapshots._instance_starting_capital("GOLIATH-MSTU"), 200.0)
        self.assertEqual(equity_snapshots._instance_starting_capital("GOLIATH-CONL"), 150.0)

    def test_unknown_instance_returns_zero(self):
        self.assertEqual(equity_snapshots._instance_starting_capital("GOLIATH-NOPE"), 0.0)


if __name__ == "__main__":
    unittest.main()
