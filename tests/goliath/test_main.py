"""Tests for trading.goliath.main.Runner."""
from __future__ import annotations

import os
import sys
import unittest
from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from trading.goliath.configs import all_instances, get  # noqa: E402
from trading.goliath.engine import (  # noqa: E402
    EngineEntryDecision,
    MarketSnapshot,
    PlatformContext,
)
from trading.goliath.instance import GoliathInstance, build_all_instances  # noqa: E402
from trading.goliath.main import Runner  # noqa: E402
from trading.goliath.strike_mapping.engine import OptionLeg  # noqa: E402
from trading.goliath.strike_mapping.wall_finder import GammaStrike  # noqa: E402


_TODAY = datetime(2026, 5, 4, 14, 30, tzinfo=timezone.utc)


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


def _good_snapshot(_inst):
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


def _empty_platform(_instances):
    return PlatformContext(open_position_count=0, open_dollars_at_risk=0.0)


def _g01_fail_snapshot(_inst):
    snap = _good_snapshot(_inst)
    return MarketSnapshot(**{**snap.__dict__, "spy_net_gex": -5.0e9})


class EntryCycleHappyPath(unittest.TestCase):
    def setUp(self):
        self._kill_patch = patch("trading.goliath.instance.is_killed", return_value=False)
        self._kill_patch.start()
        # No DB; record_* is best-effort no-op.

    def tearDown(self):
        self._kill_patch.stop()

    def test_entry_cycle_runs_all_5_instances(self):
        broker = MagicMock(return_value="pos-123")
        runner = Runner(
            snapshot_fetcher=_good_snapshot,
            platform_fetcher=_empty_platform,
            broker_executor=broker,
            dry_run=False,
        )
        result = runner.run_entry_cycle(now=_TODAY)
        self.assertEqual(result.instances_evaluated, 5)
        # All 5 instances should approve given the same good snapshot.
        self.assertEqual(result.entries_approved, 5)
        self.assertEqual(result.entries_filled, 5)
        self.assertEqual(broker.call_count, 5)

    def test_dry_run_does_not_call_broker(self):
        broker = MagicMock(return_value="pos-x")
        runner = Runner(
            snapshot_fetcher=_good_snapshot,
            platform_fetcher=_empty_platform,
            broker_executor=broker,
            dry_run=True,
        )
        result = runner.run_entry_cycle(now=_TODAY)
        self.assertEqual(result.entries_approved, 5)
        self.assertEqual(result.entries_filled, 0)
        broker.assert_not_called()


class EntryCycleSkips(unittest.TestCase):
    def setUp(self):
        self._kill_patch = patch("trading.goliath.instance.is_killed", return_value=False)
        self._kill_patch.start()

    def tearDown(self):
        self._kill_patch.stop()

    def test_snapshot_failure_skips_instance(self):
        def _broken(_inst):
            raise RuntimeError("TV API down")

        broker = MagicMock()
        runner = Runner(
            snapshot_fetcher=_broken,
            platform_fetcher=_empty_platform,
            broker_executor=broker,
            dry_run=True,
        )
        result = runner.run_entry_cycle(now=_TODAY)
        self.assertEqual(result.instances_evaluated, 5)
        self.assertEqual(result.entries_approved, 0)
        self.assertEqual(len(result.skips), 5)

    def test_kill_active_skips_instance(self):
        with patch("trading.goliath.instance.is_killed", return_value=True):
            runner = Runner(
                snapshot_fetcher=_good_snapshot,
                platform_fetcher=_empty_platform,
                broker_executor=MagicMock(),
                dry_run=True,
            )
            result = runner.run_entry_cycle(now=_TODAY)
        self.assertEqual(result.entries_approved, 0)
        self.assertTrue(all("kill_active" in s for s in result.skips))

    def test_none_snapshot_skips_instance_without_aborting_cycle(self):
        # Regression: build_market_snapshot returns None when the LETF chain
        # is empty. Earlier the runner passed None straight into
        # engine.evaluate_entry, which crashed with AttributeError on the
        # first instance and aborted the entire cycle (only MSTU got a
        # heartbeat in production, TSLL/NVDL/CONL/AMDL never ran).
        broker = MagicMock()
        runner = Runner(
            snapshot_fetcher=lambda _inst: None,
            platform_fetcher=_empty_platform,
            broker_executor=broker,
            dry_run=True,
        )
        result = runner.run_entry_cycle(now=_TODAY)
        self.assertEqual(result.instances_evaluated, 5)
        self.assertEqual(result.entries_approved, 0)
        self.assertEqual(len(result.skips), 5)
        self.assertTrue(all("snapshot_none" in s for s in result.skips))

    def test_unhandled_evaluate_entry_error_does_not_abort_cycle(self):
        # Regression: any per-instance failure in evaluate_entry must skip
        # the instance, not abort the loop for the remaining 4.
        engine = MagicMock()
        engine.evaluate_entry.side_effect = RuntimeError("boom")
        runner = Runner(
            engine=engine,
            snapshot_fetcher=_good_snapshot,
            platform_fetcher=_empty_platform,
            broker_executor=MagicMock(),
            dry_run=True,
        )
        result = runner.run_entry_cycle(now=_TODAY)
        self.assertEqual(result.instances_evaluated, 5)
        self.assertEqual(engine.evaluate_entry.call_count, 5)
        self.assertEqual(len(result.skips), 5)
        self.assertTrue(all("cycle_error" in s for s in result.skips))


class EntryCycleGateBlocks(unittest.TestCase):
    def setUp(self):
        self._kill_patch = patch("trading.goliath.instance.is_killed", return_value=False)
        self._kill_patch.start()

    def tearDown(self):
        self._kill_patch.stop()

    def test_g01_extreme_negative_blocks_all_entries(self):
        broker = MagicMock()
        runner = Runner(
            snapshot_fetcher=_g01_fail_snapshot,
            platform_fetcher=_empty_platform,
            broker_executor=broker,
            dry_run=True,
        )
        result = runner.run_entry_cycle(now=_TODAY)
        self.assertEqual(result.entries_approved, 0)


class ManagementCycle(unittest.TestCase):
    def test_no_open_positions_no_triggers_fire(self):
        runner = Runner(
            snapshot_fetcher=_good_snapshot,
            platform_fetcher=_empty_platform,
            broker_executor=MagicMock(),
            dry_run=True,
        )
        result = runner.run_management_cycle(now=_TODAY)
        # No open positions across the 5 fresh instances.
        self.assertEqual(result.instances_evaluated, 0)
        self.assertEqual(result.triggers_fired, 0)


if __name__ == "__main__":
    unittest.main()
