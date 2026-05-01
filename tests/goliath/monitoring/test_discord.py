"""Tests for trading.goliath.monitoring.discord."""
from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from trading.goliath.monitoring import discord  # noqa: E402


class IsConfigured(unittest.TestCase):
    def test_unset_returns_false(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DISCORD_WEBHOOK_URL", None)
            self.assertFalse(discord.is_configured())

    def test_set_returns_true(self):
        with patch.dict(os.environ, {"DISCORD_WEBHOOK_URL": "https://discord.com/api/webhooks/x/y"}):
            self.assertTrue(discord.is_configured())

    def test_empty_string_returns_false(self):
        with patch.dict(os.environ, {"DISCORD_WEBHOOK_URL": "   "}):
            self.assertFalse(discord.is_configured())


class PostEmbedSafetyFallbacks(unittest.TestCase):
    def test_no_webhook_returns_false(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DISCORD_WEBHOOK_URL", None)
            ok = discord.post_embed("title", "body")
        self.assertFalse(ok)

    def test_request_exception_swallowed(self):
        session = MagicMock()
        session.post.side_effect = Exception("network gone")
        ok = discord.post_embed(
            "title", "body",
            webhook_url="https://discord.com/api/webhooks/x/y",
            session=session,
        )
        self.assertFalse(ok)

    def test_non_2xx_returns_false(self):
        session = MagicMock()
        resp = MagicMock(status_code=400, text="bad request body")
        session.post.return_value = resp
        ok = discord.post_embed(
            "title", "body",
            webhook_url="https://discord.com/api/webhooks/x/y",
            session=session,
        )
        self.assertFalse(ok)

    def test_2xx_returns_true(self):
        session = MagicMock()
        resp = MagicMock(status_code=204, text="")
        session.post.return_value = resp
        ok = discord.post_embed(
            "title", "body",
            webhook_url="https://discord.com/api/webhooks/x/y",
            session=session,
        )
        self.assertTrue(ok)


class PayloadShape(unittest.TestCase):
    def test_payload_is_valid_discord_shape(self):
        session = MagicMock()
        session.post.return_value = MagicMock(status_code=204, text="")
        discord.post_embed(
            "Test title",
            "Test description",
            color=discord.COLOR_OPEN,
            fields=[{"name": "k", "value": "v", "inline": True}],
            footer_text="footer",
            webhook_url="https://discord.com/api/webhooks/x/y",
            session=session,
        )
        kwargs = session.post.call_args.kwargs
        import json
        body = json.loads(kwargs["data"])
        self.assertEqual(body["username"], "GOLIATH")
        self.assertEqual(len(body["embeds"]), 1)
        embed = body["embeds"][0]
        self.assertEqual(embed["title"], "Test title")
        self.assertEqual(embed["color"], discord.COLOR_OPEN)
        self.assertEqual(embed["footer"]["text"], "footer")
        self.assertEqual(embed["fields"][0]["name"], "k")

    def test_title_truncated_to_256_chars(self):
        session = MagicMock()
        session.post.return_value = MagicMock(status_code=204, text="")
        long_title = "A" * 500
        discord.post_embed(
            long_title, "body",
            webhook_url="https://discord.com/api/webhooks/x/y",
            session=session,
        )
        import json
        body = json.loads(session.post.call_args.kwargs["data"])
        self.assertEqual(len(body["embeds"][0]["title"]), 256)


class EmbedBuilders(unittest.TestCase):
    def test_entry_embed_has_strike_fields(self):
        embed = discord.build_entry_embed(
            instance="GOLIATH-MSTU",
            structure={"short_put_strike": 9.0, "long_put_strike": 8.5,
                       "long_call_strike": 12.0, "net_cost": 0.05},
            contracts=2,
        )
        self.assertEqual(embed["color"], discord.COLOR_OPEN)
        self.assertIn("$9.0", str(embed["fields"]))
        self.assertIn("GOLIATH-MSTU", embed["title"])

    def test_exit_embed_color_reflects_pnl_sign(self):
        win = discord.build_exit_embed("X", "T7", 12.5, ["call"])
        loss = discord.build_exit_embed("X", "T4", -8.0, ["call", "put"])
        flat = discord.build_exit_embed("X", "T7", 0.0, [])
        self.assertEqual(win["color"], discord.COLOR_WIN)
        self.assertEqual(loss["color"], discord.COLOR_LOSS)
        self.assertEqual(flat["color"], discord.COLOR_NEUTRAL)

    def test_kill_embed_uses_kill_color(self):
        embed = discord.build_kill_embed("INSTANCE", "GOLIATH-MSTU", "I-K1", "drawdown 35%")
        self.assertEqual(embed["color"], discord.COLOR_KILL)
        self.assertIn("I-K1", embed["title"])

    def test_alert_embed_color_by_severity(self):
        warn = discord.build_alert_embed("WARN", "x", "y")
        page = discord.build_alert_embed("PAGE", "x", "y")
        self.assertEqual(warn["color"], discord.COLOR_WARN)
        self.assertEqual(page["color"], discord.COLOR_LOSS)


if __name__ == "__main__":
    unittest.main()
