"""Tests for trading.goliath.monitoring.alerts."""
from __future__ import annotations

import os
import sys
import unittest
from collections import deque
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from trading.goliath.monitoring import alerts  # noqa: E402


class RateWindowEvictsExpiredEvents(unittest.TestCase):
    def test_record_and_count(self):
        w = alerts._RateWindow(seconds=600, threshold=3)
        # Three events at t=0, 1, 2.
        w.record(now=0)
        w.record(now=1)
        w.record(now=2)
        self.assertEqual(w.count(now=10), 3)
        self.assertFalse(w.breached(now=10))

    def test_evicts_old_events(self):
        w = alerts._RateWindow(seconds=600, threshold=3)
        w.record(now=0)
        w.record(now=100)
        # Query at t=700: t=0 is past the 600s window, evicted.
        self.assertEqual(w.count(now=700), 1)

    def test_breached_above_threshold(self):
        w = alerts._RateWindow(seconds=600, threshold=3)
        for t in range(5):
            w.record(now=t)
        # 5 events > threshold of 3 -> breached.
        self.assertTrue(w.breached(now=10))


class RateCountersIsolated(unittest.TestCase):
    """Module-level counters get cleared between tests via deque() reset."""

    def setUp(self):
        # Reset module counters so tests don't pollute each other.
        alerts.TV_API_FAILURES.events = deque()
        alerts.YFINANCE_FAILURES.events = deque()

    def test_record_tv_api_failure_increments(self):
        for _ in range(5):
            alerts.record_tv_api_failure()
        self.assertTrue(alerts.check_tv_api_failure_rate())

    def test_three_tv_failures_does_not_breach(self):
        for _ in range(3):
            alerts.record_tv_api_failure()
        # threshold > 3, count is 3 -> not breached
        self.assertFalse(alerts.check_tv_api_failure_rate())

    def test_yfinance_threshold(self):
        for _ in range(6):
            alerts.record_yfinance_failure()
        self.assertTrue(alerts.check_yfinance_failure_rate())


class HeartbeatCheckDelegates(unittest.TestCase):
    def test_check_heartbeat_stale_calls_module(self):
        with patch("trading.goliath.monitoring.alerts.heartbeat.is_stale",
                   return_value=True) as mock_stale:
            self.assertTrue(alerts.check_heartbeat_stale("GOLIATH-MSTU"))
        mock_stale.assert_called_once_with("GOLIATH-MSTU", max_age_seconds=300)


class AlertComposersCallDiscord(unittest.TestCase):
    """Each alert helper builds an embed and calls discord.post_embed."""

    def test_alert_heartbeat_stale(self):
        with patch("trading.goliath.monitoring.alerts.discord.post_embed",
                   return_value=True) as mock_post:
            self.assertTrue(alerts.alert_heartbeat_stale("GOLIATH-MSTU"))
        kwargs = mock_post.call_args.kwargs
        self.assertIn("Heartbeat stale", kwargs["title"])
        self.assertIn("GOLIATH-MSTU", kwargs["description"])

    def test_alert_tv_api_failures(self):
        with patch("trading.goliath.monitoring.alerts.discord.post_embed",
                   return_value=True) as mock_post:
            alerts.alert_tv_api_failures()
        kwargs = mock_post.call_args.kwargs
        self.assertIn("TV API failure rate", kwargs["title"])

    def test_alert_yfinance_failures(self):
        with patch("trading.goliath.monitoring.alerts.discord.post_embed",
                   return_value=True) as mock_post:
            alerts.alert_yfinance_failures()
        kwargs = mock_post.call_args.kwargs
        self.assertIn("yfinance failure rate", kwargs["title"])

    def test_alert_kill_switch(self):
        with patch("trading.goliath.monitoring.alerts.discord.post_embed",
                   return_value=True) as mock_post:
            alerts.alert_kill_switch(
                scope="INSTANCE", instance="GOLIATH-MSTU",
                trigger_id="I-K1", reason="drawdown 35%",
            )
        kwargs = mock_post.call_args.kwargs
        self.assertIn("KILL", kwargs["title"])
        self.assertIn("I-K1", kwargs["title"])

    def test_alert_entry_filled(self):
        with patch("trading.goliath.monitoring.alerts.discord.post_embed",
                   return_value=True) as mock_post:
            alerts.alert_entry_filled(
                instance="GOLIATH-MSTU",
                structure={"short_put_strike": 9.0, "long_put_strike": 8.5,
                           "long_call_strike": 12.0, "net_cost": 0.05},
                contracts=2,
            )
        kwargs = mock_post.call_args.kwargs
        self.assertIn("OPEN", kwargs["title"])

    def test_alert_exit_filled(self):
        with patch("trading.goliath.monitoring.alerts.discord.post_embed",
                   return_value=True) as mock_post:
            alerts.alert_exit_filled(
                instance="GOLIATH-MSTU", trigger_id="T7",
                realized_pnl=12.50, legs_closed=["short_put", "long_put", "long_call"],
            )
        kwargs = mock_post.call_args.kwargs
        self.assertIn("CLOSE", kwargs["title"])
        self.assertIn("T7", kwargs["title"])


if __name__ == "__main__":
    unittest.main()
