"""Tests for trading.goliath.kill_switch.state.

The Postgres path is exercised on Render (sandbox lacks DB). Here we
verify the module's public contract and safe-fallback behavior:
  - is_killed returns False when DB is unavailable
  - record_kill returns False (no-op) when DB is unavailable
  - clear_kill returns False when DB is unavailable
  - list_active_kills returns empty list when DB is unavailable
  - KillEvent shape and KillScope enum values
"""
from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from trading.goliath.kill_switch import (  # noqa: E402
    KillEvent,
    KillScope,
    clear_kill,
    is_killed,
    list_active_kills,
    record_kill,
)


class KillScopeEnum(unittest.TestCase):
    def test_values(self):
        self.assertEqual(KillScope.INSTANCE.value, "INSTANCE")
        self.assertEqual(KillScope.PLATFORM.value, "PLATFORM")


class KillEventShape(unittest.TestCase):
    def test_event_carries_all_fields(self):
        evt = KillEvent(
            scope=KillScope.INSTANCE,
            instance_name="GOLIATH-MSTU",
            trigger_id="I-K1",
            reason="drawdown 35%",
            context={"dd": 0.35},
        )
        self.assertEqual(evt.scope, KillScope.INSTANCE)
        self.assertEqual(evt.instance_name, "GOLIATH-MSTU")
        self.assertEqual(evt.trigger_id, "I-K1")
        self.assertIn("dd", evt.context)


class SafeFallbackWithoutDB(unittest.TestCase):
    """In sandbox/dev shells with no DB, every public function is a safe no-op."""

    def setUp(self):
        # Force the connect helper to report DB unavailable.
        self._patch = patch(
            "trading.goliath.kill_switch.state._connect",
            return_value=(None, False),
        )
        self._patch.start()

    def tearDown(self):
        self._patch.stop()

    def test_is_killed_returns_false(self):
        self.assertFalse(is_killed(KillScope.INSTANCE, "GOLIATH-MSTU"))
        self.assertFalse(is_killed(KillScope.PLATFORM))

    def test_record_kill_returns_false(self):
        evt = KillEvent(
            scope=KillScope.PLATFORM, instance_name=None,
            trigger_id="P-K1", reason="x", context={},
        )
        self.assertFalse(record_kill(evt))

    def test_clear_kill_returns_false(self):
        self.assertFalse(clear_kill(KillScope.PLATFORM, None, cleared_by="leron"))

    def test_list_returns_empty(self):
        self.assertEqual(list_active_kills(), [])


class PersistenceContract(unittest.TestCase):
    """Round-trip persistence test using a fake DB connection.

    Phase 5 acceptance: 'set kill state, restart process, verify still
    killed.' We simulate restart by calling is_killed in a fresh
    function call -- the state must come from the connection mock,
    not from in-memory state.
    """

    def test_record_then_check_uses_db_connection(self):
        # Mock connection that records calls and returns 1 from fetchone.
        rows: list = []

        class _FakeCursor:
            def __init__(self):
                self._fetched = False
            def execute(self, sql, args=None):
                rows.append((sql, args))
            def fetchone(self):
                # Return a row only on the SELECT after the INSERT.
                return (1,) if any("SELECT" in r[0] for r in rows) else None
            def close(self):
                pass

        class _FakeConn:
            def cursor(self):
                return _FakeCursor()
            def commit(self):
                pass
            def close(self):
                pass

        with patch(
            "trading.goliath.kill_switch.state._connect",
            return_value=(_FakeConn(), True),
        ):
            ok = record_kill(KillEvent(
                scope=KillScope.INSTANCE, instance_name="GOLIATH-MSTU",
                trigger_id="I-K1", reason="drawdown",
                context={"dd_pct": 0.35},
            ))
            killed = is_killed(KillScope.INSTANCE, "GOLIATH-MSTU")

        self.assertTrue(ok)
        self.assertTrue(killed)
        # Verify INSERT and SELECT were both issued.
        self.assertTrue(any("INSERT INTO goliath_kill_state" in r[0] for r in rows))
        self.assertTrue(any("SELECT 1 FROM goliath_kill_state" in r[0] for r in rows))


if __name__ == "__main__":
    unittest.main()
