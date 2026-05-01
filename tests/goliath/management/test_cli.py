"""Tests for trading.goliath.management.cli."""
from __future__ import annotations

import io
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from trading.goliath.management import cli  # noqa: E402


class CLIFlagNews(unittest.TestCase):
    def test_flag_news_calls_store_with_uppercased_ticker(self):
        with patch("trading.goliath.management.cli.news_flag_store") as store:
            store.flag_ticker.return_value = True
            rc = cli.main(["flag-news", "tsla", "--reason", "FDA news"])
        self.assertEqual(rc, 0)
        store.flag_ticker.assert_called_once_with(
            ticker="TSLA", reason="FDA news", flagged_by="cli"
        )

    def test_flag_news_returns_1_on_db_failure(self):
        with patch("trading.goliath.management.cli.news_flag_store") as store:
            store.flag_ticker.return_value = False
            rc = cli.main(["flag-news", "TSLA"])
        self.assertEqual(rc, 1)


class CLIUnflagNews(unittest.TestCase):
    def test_unflag_calls_store_and_returns_zero(self):
        with patch("trading.goliath.management.cli.news_flag_store") as store:
            store.unflag_ticker.return_value = True
            rc = cli.main(["unflag-news", "tsla"])
        self.assertEqual(rc, 0)
        store.unflag_ticker.assert_called_once_with("TSLA")

    def test_unflag_idempotent_when_no_active_flag(self):
        with patch("trading.goliath.management.cli.news_flag_store") as store:
            store.unflag_ticker.return_value = False
            rc = cli.main(["unflag-news", "TSLA"])
        # No flag to remove is not an error -- idempotent.
        self.assertEqual(rc, 0)


class CLIListFlags(unittest.TestCase):
    def test_list_empty(self):
        with patch("trading.goliath.management.cli.news_flag_store") as store, \
             patch("sys.stdout", new_callable=io.StringIO) as fake_stdout:
            store.list_flagged_tickers.return_value = []
            rc = cli.main(["list-flags"])
        self.assertEqual(rc, 0)
        self.assertIn("(no active flags)", fake_stdout.getvalue())

    def test_list_renders_rows_as_json(self):
        rows = [{"ticker": "TSLA", "reason": "x", "flagged_at": "2026-05-04T15:00:00", "flagged_by": "cli"}]
        with patch("trading.goliath.management.cli.news_flag_store") as store, \
             patch("sys.stdout", new_callable=io.StringIO) as fake_stdout:
            store.list_flagged_tickers.return_value = rows
            rc = cli.main(["list-flags"])
        self.assertEqual(rc, 0)
        self.assertIn("TSLA", fake_stdout.getvalue())


class CLIArgparse(unittest.TestCase):
    def test_no_subcommand_exits_with_error(self):
        with self.assertRaises(SystemExit):
            cli.main([])

    def test_unknown_subcommand_exits_with_error(self):
        with self.assertRaises(SystemExit):
            cli.main(["wat"])


if __name__ == "__main__":
    unittest.main()
