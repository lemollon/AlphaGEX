"""SPREADWORKS_DISCORD_ENABLED is the master switch for every Discord post.

Default OFF. Every SpreadWorks poster (scheduler, bot embeds, gamma/risk
alerts, intraday + QQQ watchers) goes through backend._send_webhook_sync,
so gating it there silences all of them at once.
"""
from unittest.mock import MagicMock

import backend


def _fake_requests(monkeypatch):
    fake = MagicMock()
    fake.post.return_value = MagicMock(status_code=204)
    fake.exceptions = type("E", (), {"ReadTimeout": TimeoutError})
    monkeypatch.setitem(__import__("sys").modules, "requests", fake)
    return fake


def test_default_is_disabled(monkeypatch):
    monkeypatch.delenv("SPREADWORKS_DISCORD_ENABLED", raising=False)
    assert backend.discord_posting_enabled() is False


def test_explicit_false_is_disabled(monkeypatch):
    for v in ("false", "0", "no", "off", "", "  "):
        monkeypatch.setenv("SPREADWORKS_DISCORD_ENABLED", v)
        assert backend.discord_posting_enabled() is False


def test_truthy_values_enable(monkeypatch):
    for v in ("true", "True", "1", "yes", "on", " TRUE "):
        monkeypatch.setenv("SPREADWORKS_DISCORD_ENABLED", v)
        assert backend.discord_posting_enabled() is True


def test_send_skips_http_when_disabled(monkeypatch):
    monkeypatch.delenv("SPREADWORKS_DISCORD_ENABLED", raising=False)
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/x/y")
    fake = _fake_requests(monkeypatch)
    assert backend._send_webhook_sync({"title": "t"}) is False
    fake.post.assert_not_called()


def test_send_skips_http_when_disabled_even_with_override_url(monkeypatch):
    monkeypatch.setenv("SPREADWORKS_DISCORD_ENABLED", "false")
    fake = _fake_requests(monkeypatch)
    assert backend._send_webhook_sync(
        {"title": "t"}, webhook_url="https://discord.com/api/webhooks/a/b") is False
    fake.post.assert_not_called()


def test_send_posts_when_enabled(monkeypatch):
    monkeypatch.setenv("SPREADWORKS_DISCORD_ENABLED", "true")
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/x/y")
    fake = _fake_requests(monkeypatch)
    assert backend._send_webhook_sync({"title": "t"}) is True
    fake.post.assert_called_once()
