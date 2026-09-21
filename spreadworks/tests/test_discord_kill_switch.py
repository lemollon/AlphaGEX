"""Discord scope gates keep entry alerts isolated from fleet-wide posts.

The fleet-wide route remains default-off. Intraday and QQQ entry alerts use a
separate explicit switch and webhook so enabling them cannot reactivate the
scheduler, bot, gamma/risk, TSUNAMI, or daily-brief routes.
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


def test_intraday_route_posts_while_fleet_route_stays_disabled(monkeypatch):
    monkeypatch.setenv("SPREADWORKS_DISCORD_ENABLED", "false")
    monkeypatch.setenv("INTRADAY_ALERTS_ENABLED", "true")
    monkeypatch.setenv(
        "INTRADAY_DISCORD_WEBHOOK_URL",
        "https://discord.com/api/webhooks/intraday/secret",
    )
    monkeypatch.setenv(
        "DISCORD_WEBHOOK_URL",
        "https://discord.com/api/webhooks/fleet/secret",
    )
    fake = _fake_requests(monkeypatch)

    assert backend._send_webhook_sync({"title": "fleet"}) is False
    assert backend._send_intraday_webhook_sync({"title": "entry"}) is True

    fake.post.assert_called_once()
    assert fake.post.call_args.args[0].endswith("/intraday/secret")


def test_intraday_route_skips_http_unless_explicitly_enabled(monkeypatch):
    monkeypatch.setenv("SPREADWORKS_DISCORD_ENABLED", "true")
    monkeypatch.delenv("INTRADAY_ALERTS_ENABLED", raising=False)
    monkeypatch.setenv(
        "INTRADAY_DISCORD_WEBHOOK_URL",
        "https://discord.com/api/webhooks/intraday/secret",
    )
    fake = _fake_requests(monkeypatch)

    assert backend._send_intraday_webhook_sync({"title": "entry"}) is False
    fake.post.assert_not_called()


def test_intraday_route_falls_back_to_shared_webhook(monkeypatch):
    monkeypatch.setenv("INTRADAY_ALERTS_ENABLED", "true")
    monkeypatch.delenv("INTRADAY_DISCORD_WEBHOOK_URL", raising=False)
    monkeypatch.setenv(
        "DISCORD_WEBHOOK_URL",
        "https://discord.com/api/webhooks/fleet/secret",
    )
    fake = _fake_requests(monkeypatch)

    assert backend._send_intraday_webhook_sync({"title": "entry"}) is True
    fake.post.assert_called_once()
    assert fake.post.call_args.args[0].endswith("/fleet/secret")


def test_webhook_failures_do_not_log_the_secret_url(monkeypatch, caplog):
    import time

    webhook = "https://discord.com/api/webhooks/intraday/do-not-log"
    monkeypatch.setenv("INTRADAY_ALERTS_ENABLED", "true")
    monkeypatch.setenv("INTRADAY_DISCORD_WEBHOOK_URL", webhook)
    fake = _fake_requests(monkeypatch)
    fake.post.side_effect = RuntimeError(webhook)
    monkeypatch.setattr(time, "sleep", lambda _seconds: None)

    assert backend._send_intraday_webhook_sync({"title": "entry"}) is False
    assert webhook not in caplog.text
    assert "RuntimeError" in caplog.text
