"""Tests for trading.goliath.kill_switch.cli."""
from __future__ import annotations

import io
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from trading.goliath.kill_switch import cli  # noqa: E402


class CLIList(unittest.TestCase):
    def test_list_empty(self):
        with patch("trading.goliath.kill_switch.cli.list_active_kills", return_value=[]), \
             patch("sys.stdout", new_callable=io.StringIO) as out:
            rc = cli.main(["list-kills"])
        self.assertEqual(rc, 0)
        self.assertIn("(no active kills)", out.getvalue())

    def test_list_renders_rows(self):
        rows = [{"id": 1, "scope": "INSTANCE", "instance_name": "GOLIATH-MSTU",
                 "trigger_id": "I-K1", "reason": "x", "killed_at": "2026-05-04T15:00:00"}]
        with patch("trading.goliath.kill_switch.cli.list_active_kills", return_value=rows), \
             patch("sys.stdout", new_callable=io.StringIO) as out:
            rc = cli.main(["list-kills"])
        self.assertEqual(rc, 0)
        self.assertIn("GOLIATH-MSTU", out.getvalue())


class CLIOverrideRefusedWithoutFlag(unittest.TestCase):
    """Paranoia gate: missing --confirm-leron-override -> refuse."""

    def test_refuses_without_confirmation_flag(self):
        with patch("trading.goliath.kill_switch.cli.clear_kill") as clear, \
             patch("sys.stderr", new_callable=io.StringIO) as err:
            rc = cli.main([
                "override-kill", "--scope", "INSTANCE",
                "--instance", "GOLIATH-MSTU", "--by", "leron",
            ])
        self.assertEqual(rc, 2)
        clear.assert_not_called()
        self.assertIn("REFUSED", err.getvalue())


class CLIOverrideValidation(unittest.TestCase):
    def test_instance_scope_requires_instance_arg(self):
        with patch("trading.goliath.kill_switch.cli.clear_kill") as clear, \
             patch("sys.stderr", new_callable=io.StringIO):
            rc = cli.main([
                "override-kill", "--scope", "INSTANCE",
                "--by", "leron", "--confirm-leron-override",
            ])
        self.assertEqual(rc, 2)
        clear.assert_not_called()

    def test_platform_scope_rejects_instance_arg(self):
        with patch("trading.goliath.kill_switch.cli.clear_kill") as clear, \
             patch("sys.stderr", new_callable=io.StringIO):
            rc = cli.main([
                "override-kill", "--scope", "PLATFORM",
                "--instance", "GOLIATH-MSTU",
                "--by", "leron", "--confirm-leron-override",
            ])
        self.assertEqual(rc, 2)
        clear.assert_not_called()


class CLIOverrideHappyPath(unittest.TestCase):
    def test_instance_override_calls_clear(self):
        with patch("trading.goliath.kill_switch.cli.clear_kill", return_value=True) as clear, \
             patch("sys.stdout", new_callable=io.StringIO) as out:
            rc = cli.main([
                "override-kill", "--scope", "INSTANCE",
                "--instance", "goliath-mstu",  # lowercase to test uppercasing
                "--by", "leron", "--confirm-leron-override",
            ])
        self.assertEqual(rc, 0)
        clear.assert_called_once_with("INSTANCE", "GOLIATH-MSTU", cleared_by="leron")
        self.assertIn("OK cleared INSTANCE/GOLIATH-MSTU", out.getvalue())

    def test_platform_override_calls_clear_with_none(self):
        with patch("trading.goliath.kill_switch.cli.clear_kill", return_value=True) as clear:
            rc = cli.main([
                "override-kill", "--scope", "PLATFORM",
                "--by", "leron", "--confirm-leron-override",
            ])
        self.assertEqual(rc, 0)
        clear.assert_called_once_with("PLATFORM", None, cleared_by="leron")

    def test_override_noop_when_no_active_kill(self):
        with patch("trading.goliath.kill_switch.cli.clear_kill", return_value=False), \
             patch("sys.stdout", new_callable=io.StringIO) as out:
            rc = cli.main([
                "override-kill", "--scope", "PLATFORM",
                "--by", "leron", "--confirm-leron-override",
            ])
        self.assertEqual(rc, 0)
        self.assertIn("NOOP", out.getvalue())


if __name__ == "__main__":
    unittest.main()
