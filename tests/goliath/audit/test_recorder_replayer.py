"""Tests for trading.goliath.audit.recorder + replayer."""
from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from trading.goliath.audit import recorder, replayer  # noqa: E402


class RecorderDispatchesEventTypes(unittest.TestCase):
    """Each recorder helper inserts the right event_type."""

    def test_entry_eval_uses_correct_event_type(self):
        with patch("trading.goliath.audit.recorder.store.insert", return_value=True) as ins:
            recorder.record_entry_eval(
                "GOLIATH-MSTU",
                chain=[{"gate": "G01", "outcome": "PASS", "reason": "", "context": {}}],
                structure=None,
                decision="FAILED_AT:G02",
            )
        kwargs = ins.call_args.kwargs
        self.assertEqual(kwargs["event_type"], "ENTRY_EVAL")
        self.assertEqual(kwargs["data"]["decision"], "FAILED_AT:G02")

    def test_entry_filled_uses_correct_event_type(self):
        with patch("trading.goliath.audit.recorder.store.insert", return_value=True) as ins:
            recorder.record_entry_filled(
                "GOLIATH-MSTU", position_id="p1",
                structure={"sp": 9.0, "lp": 8.5, "lc": 12.0},
                fill_details={"sp_fill": 0.50}, contracts=1,
            )
        self.assertEqual(ins.call_args.kwargs["event_type"], "ENTRY_FILLED")
        self.assertEqual(ins.call_args.kwargs["position_id"], "p1")

    def test_management_eval_uses_correct_event_type(self):
        with patch("trading.goliath.audit.recorder.store.insert", return_value=True) as ins:
            recorder.record_management_eval(
                "GOLIATH-MSTU", position_id="p1",
                triggers_evaluated=["T7", "T6", "T5"],
                fired_action=None, position_snapshot={"pnl": 0.0},
            )
        self.assertEqual(ins.call_args.kwargs["event_type"], "MANAGEMENT_EVAL")

    def test_exit_filled_uses_correct_event_type(self):
        with patch("trading.goliath.audit.recorder.store.insert", return_value=True) as ins:
            recorder.record_exit_filled(
                "GOLIATH-MSTU", position_id="p1", trigger_id="T7",
                legs_closed=["short_put", "long_put", "long_call"],
                realized_pnl=12.50, fill_details={},
            )
        self.assertEqual(ins.call_args.kwargs["event_type"], "EXIT_FILLED")


class ReplayerReconstructsTimeline(unittest.TestCase):
    def test_replay_assembles_full_chain(self):
        rows = [
            {"id": 1, "timestamp": "t0", "instance": "GOLIATH-MSTU",
             "event_type": "ENTRY_EVAL", "data": {"decision": "STRUCTURE_RETURNED"},
             "position_id": "p1"},
            {"id": 2, "timestamp": "t1", "instance": "GOLIATH-MSTU",
             "event_type": "ENTRY_FILLED", "data": {"contracts": 1},
             "position_id": "p1"},
            {"id": 3, "timestamp": "t2", "instance": "GOLIATH-MSTU",
             "event_type": "MANAGEMENT_EVAL", "data": {"fired_action": None},
             "position_id": "p1"},
            {"id": 4, "timestamp": "t3", "instance": "GOLIATH-MSTU",
             "event_type": "EXIT_FILLED",
             "data": {"trigger_id": "T7", "realized_pnl": 12.5},
             "position_id": "p1"},
        ]
        with patch("trading.goliath.audit.replayer.store.query_by_position", return_value=rows):
            timeline = replayer.replay_position("p1")

        self.assertEqual(timeline.instance, "GOLIATH-MSTU")
        self.assertIsNotNone(timeline.entry_eval)
        self.assertIsNotNone(timeline.entry_filled)
        self.assertEqual(len(timeline.management_evals), 1)
        self.assertIsNotNone(timeline.exit_filled)
        self.assertEqual(timeline.event_count, 4)
        self.assertTrue(timeline.is_complete)

    def test_replay_handles_partial_chain(self):
        # Open position: entry_eval + entry_filled + a couple management_evals,
        # but no exit_filled yet.
        rows = [
            {"id": 1, "timestamp": "t0", "instance": "GOLIATH-MSTU",
             "event_type": "ENTRY_EVAL", "data": {"decision": "STRUCTURE_RETURNED"},
             "position_id": "p1"},
            {"id": 2, "timestamp": "t1", "instance": "GOLIATH-MSTU",
             "event_type": "ENTRY_FILLED", "data": {}, "position_id": "p1"},
            {"id": 3, "timestamp": "t2", "instance": "GOLIATH-MSTU",
             "event_type": "MANAGEMENT_EVAL", "data": {}, "position_id": "p1"},
            {"id": 4, "timestamp": "t3", "instance": "GOLIATH-MSTU",
             "event_type": "MANAGEMENT_EVAL", "data": {}, "position_id": "p1"},
        ]
        with patch("trading.goliath.audit.replayer.store.query_by_position", return_value=rows):
            timeline = replayer.replay_position("p1")
        self.assertFalse(timeline.is_complete)
        self.assertEqual(len(timeline.management_evals), 2)

    def test_replay_empty_when_no_rows(self):
        with patch("trading.goliath.audit.replayer.store.query_by_position", return_value=[]):
            timeline = replayer.replay_position("ghost")
        self.assertEqual(timeline.event_count, 0)
        self.assertIsNone(timeline.instance)


class SummarizeProducesCompactDigest(unittest.TestCase):
    def test_summary_includes_decision_and_pnl(self):
        rows = [
            {"id": 1, "timestamp": "t0", "instance": "GOLIATH-MSTU",
             "event_type": "ENTRY_EVAL", "data": {"decision": "STRUCTURE_RETURNED"},
             "position_id": "p1"},
            {"id": 4, "timestamp": "t3", "instance": "GOLIATH-MSTU",
             "event_type": "EXIT_FILLED",
             "data": {"trigger_id": "T2", "realized_pnl": 50.0},
             "position_id": "p1"},
        ]
        with patch("trading.goliath.audit.replayer.store.query_by_position", return_value=rows):
            timeline = replayer.replay_position("p1")
        summary = replayer.summarize(timeline)
        self.assertEqual(summary["entry_decision"], "STRUCTURE_RETURNED")
        self.assertEqual(summary["fired_trigger"], "T2")
        self.assertEqual(summary["realized_pnl"], 50.0)


if __name__ == "__main__":
    unittest.main()
