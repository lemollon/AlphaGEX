"""Tests for trading.goliath.broker.paper_executor."""
from __future__ import annotations

import os
import sys
import unittest
from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from trading.goliath.broker.paper_executor import (  # noqa: E402
    _next_friday,
    paper_broker_executor,
)
from trading.goliath.configs import get  # noqa: E402
from trading.goliath.engine import EngineEntryDecision  # noqa: E402
from trading.goliath.instance import GoliathInstance  # noqa: E402
from trading.goliath.strike_mapping.engine import OptionLeg, TradeStructure  # noqa: E402
from trading.goliath.strike_mapping.letf_mapper import LETFTarget  # noqa: E402
from trading.goliath.strike_mapping.wall_finder import Wall  # noqa: E402


def _approved_decision() -> EngineEntryDecision:
    sp = OptionLeg(strike=9.0, bid=0.48, ask=0.52, open_interest=500, contract_type="put")
    lp = OptionLeg(strike=8.5, bid=0.18, ask=0.22, open_interest=500, contract_type="put")
    lc = OptionLeg(strike=12.0, bid=0.28, ask=0.32, open_interest=500, contract_type="call")
    s = TradeStructure(
        short_put=sp, long_put=lp, long_call=lc,
        put_spread_credit=0.30, long_call_cost=0.30, net_cost=0.0,
        wall=Wall(strike=191.0, gamma=8.0, median_local_gamma=1.0, concentration_ratio=8.0),
        letf_target=LETFTarget(target_strike=9.0, band_low=8.5, band_high=9.5,
                               predicted_letf_return=-0.10, vol_drag=-0.005, te_band=0.056),
    )
    decision = EngineEntryDecision(structure=s)
    decision.contracts_to_trade = 2
    return decision


class NextFriday(unittest.TestCase):
    def test_monday_returns_same_week_friday(self):
        # 2026-05-04 is a Monday.
        mon = datetime(2026, 5, 4, 10, 0, tzinfo=timezone.utc)
        self.assertEqual(_next_friday(mon), date(2026, 5, 8))

    def test_thursday_returns_same_week_friday(self):
        thu = datetime(2026, 5, 7, 10, 0, tzinfo=timezone.utc)
        self.assertEqual(_next_friday(thu), date(2026, 5, 8))

    def test_friday_morning_returns_same_friday(self):
        fri = datetime(2026, 5, 8, 9, 0, tzinfo=timezone.utc)
        self.assertEqual(_next_friday(fri), date(2026, 5, 8))


class PaperBrokerExecutorReturnsNoneWithoutDB(unittest.TestCase):
    def test_returns_none_when_db_unavailable(self):
        with patch("trading.goliath.broker.paper_executor._connect",
                   return_value=(None, False)):
            inst = GoliathInstance(config=get("GOLIATH-MSTU"))
            result = paper_broker_executor(inst, _approved_decision())
        self.assertIsNone(result)
        self.assertEqual(inst.open_count, 0)

    def test_returns_none_for_unapproved_decision(self):
        unapproved = EngineEntryDecision(structure=None)
        unapproved.contracts_to_trade = 0
        inst = GoliathInstance(config=get("GOLIATH-MSTU"))
        result = paper_broker_executor(inst, unapproved)
        self.assertIsNone(result)


class PaperBrokerExecutorPersistsAndReturnsId(unittest.TestCase):
    def test_returns_uuid_position_id_and_appends_position(self):
        # Mock DB to accept INSERT.
        cur = MagicMock()
        conn = MagicMock()
        conn.cursor.return_value = cur
        with patch("trading.goliath.broker.paper_executor._connect",
                   return_value=(conn, True)), \
             patch("trading.goliath.broker.paper_executor.audit_recorder") as ar:
            ar.record_entry_filled.return_value = True
            inst = GoliathInstance(config=get("GOLIATH-MSTU"))
            result = paper_broker_executor(inst, _approved_decision())

        self.assertIsNotNone(result)
        self.assertTrue(result.startswith("goliath-paper-"))
        self.assertEqual(inst.open_count, 1)
        added = inst.open_positions[0]
        self.assertEqual(added.position_id, result)
        self.assertEqual(added.short_put_strike, 9.0)
        self.assertEqual(added.long_put_strike, 8.5)
        self.assertEqual(added.long_call_strike, 12.0)
        # Audit ENTRY_FILLED was called.
        ar.record_entry_filled.assert_called_once()


if __name__ == "__main__":
    unittest.main()
