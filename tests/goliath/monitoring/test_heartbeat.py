"""Tests for trading.goliath.monitoring.heartbeat."""
from __future__ import annotations

import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from trading.goliath.monitoring import heartbeat  # noqa: E402


class _FakeConn:
    """Minimal psycopg2-shaped connection for tests."""

    def __init__(self, fetchone_result=None, capture_calls=None):
        self.fetchone_result = fetchone_result
        self.capture_calls = capture_calls if capture_calls is not None else []

    def cursor(self):
        return _FakeCursor(self.fetchone_result, self.capture_calls)

    def commit(self):
        pass

    def close(self):
        pass


class _FakeCursor:
    def __init__(self, fetchone_result, capture_calls):
        self._fetch = fetchone_result
        self._calls = capture_calls

    def execute(self, sql, params=None):
        self._calls.append((sql, params))

    def fetchone(self):
        return self._fetch

    def close(self):
        pass


class SafeFallbackWithoutDB(unittest.TestCase):
    def test_record_returns_false_without_db(self):
        with patch("trading.goliath.monitoring.heartbeat._connect",
                   return_value=(None, False)):
            self.assertFalse(heartbeat.record_heartbeat("GOLIATH-MSTU"))

    def test_read_returns_none_without_db(self):
        with patch("trading.goliath.monitoring.heartbeat._connect",
                   return_value=(None, False)):
            self.assertIsNone(heartbeat.read_heartbeat("GOLIATH-MSTU"))

    def test_is_stale_returns_true_without_db(self):
        with patch("trading.goliath.monitoring.heartbeat._connect",
                   return_value=(None, False)):
            self.assertTrue(heartbeat.is_stale("GOLIATH-MSTU"))


class RecordHeartbeatUpsert(unittest.TestCase):
    def test_upsert_runs_with_expected_params(self):
        calls: list = []
        conn = _FakeConn(capture_calls=calls)
        with patch("trading.goliath.monitoring.heartbeat._connect",
                   return_value=(conn, True)):
            ok = heartbeat.record_heartbeat(
                bot_name="GOLIATH-MSTU",
                status="OK",
                scan_count_delta=1,
                trades_today_delta=0,
                details={"cycle": "entry"},
            )
        self.assertTrue(ok)
        self.assertEqual(len(calls), 1)
        sql, params = calls[0]
        self.assertIn("INSERT INTO bot_heartbeats", sql)
        self.assertIn("ON CONFLICT (bot_name) DO UPDATE", sql)
        # First param should be bot_name.
        self.assertEqual(params[0], "GOLIATH-MSTU")

    def test_failure_returns_false_no_raise(self):
        conn = MagicMock()
        cur = MagicMock()
        cur.execute.side_effect = Exception("boom")
        conn.cursor.return_value = cur
        with patch("trading.goliath.monitoring.heartbeat._connect",
                   return_value=(conn, True)):
            ok = heartbeat.record_heartbeat("GOLIATH-MSTU")
        self.assertFalse(ok)


class IsStaleLogic(unittest.TestCase):
    def test_returns_true_when_no_row(self):
        conn = _FakeConn(fetchone_result=None)
        with patch("trading.goliath.monitoring.heartbeat._connect",
                   return_value=(conn, True)):
            self.assertTrue(heartbeat.is_stale("GOLIATH-MSTU"))

    def test_returns_true_when_old_heartbeat(self):
        old = datetime.now(timezone.utc) - timedelta(minutes=10)
        row = ("GOLIATH-MSTU", old, "OK", 100, 0, None, None)
        conn = _FakeConn(fetchone_result=row)
        with patch("trading.goliath.monitoring.heartbeat._connect",
                   return_value=(conn, True)):
            self.assertTrue(heartbeat.is_stale("GOLIATH-MSTU", max_age_seconds=300))

    def test_returns_false_when_recent_heartbeat(self):
        recent = datetime.now(timezone.utc) - timedelta(seconds=60)
        row = ("GOLIATH-MSTU", recent, "OK", 100, 0, None, None)
        conn = _FakeConn(fetchone_result=row)
        with patch("trading.goliath.monitoring.heartbeat._connect",
                   return_value=(conn, True)):
            self.assertFalse(heartbeat.is_stale("GOLIATH-MSTU", max_age_seconds=300))


class ReadHeartbeat(unittest.TestCase):
    def test_returns_dict_with_iso_timestamps(self):
        ts = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)
        row = ("GOLIATH-MSTU", ts, "OK", 42, 1, ts, {"k": "v"})
        conn = _FakeConn(fetchone_result=row)
        with patch("trading.goliath.monitoring.heartbeat._connect",
                   return_value=(conn, True)):
            result = heartbeat.read_heartbeat("GOLIATH-MSTU")
        self.assertEqual(result["bot_name"], "GOLIATH-MSTU")
        self.assertEqual(result["status"], "OK")
        self.assertEqual(result["scan_count"], 42)
        self.assertEqual(result["last_heartbeat"], ts.isoformat())
        self.assertEqual(result["details"], {"k": "v"})


if __name__ == "__main__":
    unittest.main()
