"""Tests for trading.goliath.audit.store."""
from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from trading.goliath.audit import store  # noqa: E402


class EventTypeValidation(unittest.TestCase):
    def test_valid_event_types(self):
        self.assertEqual(
            store.VALID_EVENT_TYPES,
            frozenset({"ENTRY_EVAL", "ENTRY_FILLED", "MANAGEMENT_EVAL", "EXIT_FILLED"}),
        )

    def test_insert_rejects_invalid_event_type(self):
        with patch("trading.goliath.audit.store._connect") as conn:
            ok = store.insert("GOLIATH-MSTU", "BOGUS", {}, position_id="p1")
        self.assertFalse(ok)
        conn.assert_not_called()  # short-circuited before DB attempt


class SafeFallbackWithoutDB(unittest.TestCase):
    def setUp(self):
        self._patch = patch(
            "trading.goliath.audit.store._connect", return_value=(None, False)
        )
        self._patch.start()

    def tearDown(self):
        self._patch.stop()

    def test_insert_returns_false_without_db(self):
        self.assertFalse(
            store.insert("GOLIATH-MSTU", "ENTRY_EVAL", {"k": 1}, position_id="p1")
        )

    def test_query_by_position_returns_empty(self):
        self.assertEqual(store.query_by_position("p1"), [])

    def test_query_recent_returns_empty(self):
        self.assertEqual(store.query_recent("GOLIATH-MSTU"), [])


class InsertExecutesValidSQL(unittest.TestCase):
    def test_insert_calls_execute_with_payload(self):
        seen: list = []

        class _Cur:
            def execute(self, sql, args):
                seen.append((sql, args))
            def close(self):
                pass

        class _Conn:
            def cursor(self):
                return _Cur()
            def commit(self):
                pass
            def close(self):
                pass

        with patch(
            "trading.goliath.audit.store._connect", return_value=(_Conn(), True)
        ):
            ok = store.insert(
                "GOLIATH-MSTU", "ENTRY_FILLED",
                {"strike": 9.0, "n": 1}, position_id="p-uuid-1",
            )
        self.assertTrue(ok)
        self.assertEqual(len(seen), 1)
        sql, args = seen[0]
        self.assertIn("INSERT INTO goliath_trade_audit", sql)
        self.assertEqual(args[0], "GOLIATH-MSTU")
        self.assertEqual(args[1], "ENTRY_FILLED")
        self.assertIn("strike", args[2])
        self.assertEqual(args[3], "p-uuid-1")


if __name__ == "__main__":
    unittest.main()
