"""Full-lifecycle integration test per kickoff prompt.

Runs evaluate_entry -> simulate broker fill -> manage_open_positions
across cycles -> verify audit log reconstructs the decision chain.

Uses an in-memory audit store stub so the test does not require a
database. The stub captures every recorder.insert call and exposes
the same shape that replayer.query_by_position would return on
production Postgres.
"""
from __future__ import annotations

import os
import sys
import unittest
from datetime import date, datetime, timezone
from unittest.mock import patch
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from trading.goliath.audit import recorder, replayer  # noqa: E402
from trading.goliath.configs import get  # noqa: E402
from trading.goliath.engine import (  # noqa: E402
    GoliathEngine,
    MarketSnapshot,
    PlatformContext,
)
from trading.goliath.instance import GoliathInstance  # noqa: E402
from trading.goliath.management.state import Position, PositionState  # noqa: E402
from trading.goliath.strike_mapping.engine import OptionLeg  # noqa: E402
from trading.goliath.strike_mapping.wall_finder import GammaStrike  # noqa: E402

_ET = ZoneInfo("America/New_York")
_MONDAY_10AM_ET = datetime(2026, 5, 4, 10, 0, tzinfo=_ET)
_THURSDAY_3PM_ET = datetime(2026, 5, 7, 15, 0, tzinfo=_ET)
_FRIDAY = date(2026, 5, 8)
_POSITION_ID = "pos-integration-1"


class _InMemoryAuditStore:
    """In-memory replacement for goliath_trade_audit during tests."""

    def __init__(self):
        self.rows: list[dict] = []
        self._next_id = 1

    def insert(self, instance, event_type, data, position_id=None):
        self.rows.append({
            "id": self._next_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "instance": instance, "event_type": event_type,
            "data": data, "position_id": position_id,
        })
        self._next_id += 1
        return True

    def query_by_position(self, position_id):
        return [r for r in self.rows if r["position_id"] == position_id]

    def query_recent(self, instance, limit=100):
        return [r for r in self.rows if r["instance"] == instance][:limit]


def _good_chain():
    chain = {}
    for k in [7.5, 8.0, 8.5, 9.0, 9.5, 10.0, 11.5, 12.0, 12.5]:
        if k <= 10.0:
            mid = max(0.20, 10.0 - k + 0.20)
            chain[(k, "put")] = OptionLeg(k, mid - 0.02, mid + 0.02, 500, "put")
        else:
            chain[(k, "call")] = OptionLeg(k, 0.28, 0.32, 500, "call")
    chain[(12.0, "call")] = OptionLeg(12.0, 0.28, 0.32, 500, "call")
    return chain


def _good_snapshot() -> MarketSnapshot:
    return MarketSnapshot(
        spy_net_gex=2.0e9, underlying_net_gex=1.0e8,
        underlying_strikes=[
            GammaStrike(190.0, 1.0), GammaStrike(191.0, 8.0),
            GammaStrike(195.0, 1.0), GammaStrike(200.0, 1.0),
            GammaStrike(205.0, 1.0), GammaStrike(210.0, 1.0),
        ],
        underlying_spot=200.0, letf_spot=10.0,
        letf_chain=_good_chain(), sigma_annualized=0.5,
        next_earnings_date=date(2026, 6, 1),
        iv_rank=75.0, underlying_50d_ma=185.0,
    )


def _make_filled_position(structure, contracts) -> Position:
    """Synthesize a Position from the engine's approved structure."""
    s = structure
    spread_width = s.short_put.strike - s.long_put.strike
    defined_max = spread_width - s.put_spread_credit
    return Position(
        position_id=_POSITION_ID,
        instance_name="GOLIATH-TSLL",
        letf_ticker="TSLL", underlying_ticker="TSLA",
        state=PositionState.OPEN,
        entered_at=_MONDAY_10AM_ET.astimezone(timezone.utc),
        expiration_date=_FRIDAY,
        short_put_strike=s.short_put.strike,
        long_put_strike=s.long_put.strike,
        long_call_strike=s.long_call.strike,
        entry_long_call_cost=s.long_call_cost,
        entry_put_spread_credit=s.put_spread_credit,
        entry_net_cost=s.net_cost,
        defined_max_loss=defined_max,
        entry_underlying_gex_regime="POSITIVE",
        current_short_put_mid=(s.short_put.bid + s.short_put.ask) / 2,
        current_long_put_mid=(s.long_put.bid + s.long_put.ask) / 2,
        current_long_call_mid=(s.long_call.bid + s.long_call.ask) / 2,
        current_underlying_spot=200.0,
        current_underlying_gex_regime="POSITIVE",
        current_letf_spot=10.0,
    )


class FullLifecycle(unittest.TestCase):
    """End-to-end: entry -> fill -> management cycles -> audit replay."""

    def setUp(self):
        self.store = _InMemoryAuditStore()
        # Patch the underlying store both for inserts (recorder) and
        # for queries (replayer).
        self._patches = [
            patch("trading.goliath.audit.recorder.store.insert",
                  side_effect=self.store.insert),
            patch("trading.goliath.audit.replayer.store.query_by_position",
                  side_effect=self.store.query_by_position),
            patch("trading.goliath.instance.is_killed", return_value=False),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()

    def test_lifecycle_entry_through_thursday_close(self):
        engine = GoliathEngine()
        instance = GoliathInstance(config=get("GOLIATH-TSLL"))
        platform = PlatformContext(0, 0.0)

        # 1. Monday 10am: evaluate_entry.
        decision = engine.evaluate_entry(
            instance, _good_snapshot(), platform, now=_MONDAY_10AM_ET,
        )
        self.assertTrue(decision.approved)
        self.assertGreater(decision.contracts_to_trade, 0)

        # Record ENTRY_EVAL + ENTRY_FILLED.
        recorder.record_entry_eval(
            instance.name,
            chain=[{"gate": r.gate, "outcome": r.outcome.value,
                    "reason": r.reason, "context": r.context}
                   for r in decision.gate_chain],
            structure={"short_put": decision.structure.short_put.strike,
                       "long_put": decision.structure.long_put.strike,
                       "long_call": decision.structure.long_call.strike},
            decision="STRUCTURE_RETURNED", position_id=_POSITION_ID,
        )

        # 2. Simulate broker fill -> position lands in instance.
        position = _make_filled_position(decision.structure, decision.contracts_to_trade)
        instance.add_position(position)
        recorder.record_entry_filled(
            instance.name, position_id=_POSITION_ID,
            structure={"short_put": position.short_put_strike},
            fill_details={"sp_fill": position.current_short_put_mid},
            contracts=decision.contracts_to_trade,
        )

        # 3. Tuesday afternoon: management cycle, no triggers fire.
        tue = datetime(2026, 5, 5, 14, 0, tzinfo=_ET)
        actions_tue = engine.manage_open_positions(instance, now=tue)
        self.assertEqual(actions_tue, [])
        recorder.record_management_eval(
            instance.name, position_id=_POSITION_ID,
            triggers_evaluated=["T7", "T6", "T5", "T4", "T8", "T2", "T1", "T3"],
            fired_action=None, position_snapshot={"state": position.state.value},
        )

        # 4. Thursday 3pm ET: T7 fires -> close everything.
        actions_thu = engine.manage_open_positions(instance, now=_THURSDAY_3PM_ET)
        self.assertEqual(len(actions_thu), 1)
        _, action = actions_thu[0]
        self.assertEqual(action.trigger_id, "T7")
        self.assertTrue(action.closes_everything)

        recorder.record_exit_filled(
            instance.name, position_id=_POSITION_ID,
            trigger_id=action.trigger_id,
            legs_closed=["short_put", "long_put", "long_call"],
            realized_pnl=12.50,
            fill_details={"close_kind": "mandatory"},
        )

        # 5. Replay -- the timeline must reconstruct the full decision chain.
        timeline = replayer.replay_position(_POSITION_ID)
        self.assertEqual(timeline.instance, instance.name)
        self.assertIsNotNone(timeline.entry_eval)
        self.assertIsNotNone(timeline.entry_filled)
        self.assertEqual(len(timeline.management_evals), 1)
        self.assertIsNotNone(timeline.exit_filled)
        self.assertTrue(timeline.is_complete)
        self.assertEqual(timeline.event_count, 4)

        summary = replayer.summarize(timeline)
        self.assertEqual(summary["entry_decision"], "STRUCTURE_RETURNED")
        self.assertEqual(summary["fired_trigger"], "T7")
        self.assertEqual(summary["realized_pnl"], 12.50)


if __name__ == "__main__":
    unittest.main()
