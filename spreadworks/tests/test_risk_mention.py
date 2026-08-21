"""The time-critical alert must actually push to a phone.

`@here` is suppressed in a muted channel and only reaches members who are
online — so the alert that matters most is the one most likely to be swallowed.
A direct user mention pushes regardless. These tests pin that behaviour and the
delivery flag that reports it.
"""
from __future__ import annotations

import pytest

from backend import risk_alerts


def test_falls_back_to_here_when_unset(monkeypatch):
    monkeypatch.delenv("RISK_DISCORD_USER_ID", raising=False)
    assert risk_alerts._mention() == "@here"


def test_direct_mention_when_set(monkeypatch):
    monkeypatch.setenv("RISK_DISCORD_USER_ID", "123456789012345678")
    assert risk_alerts._mention() == "<@123456789012345678>"


@pytest.mark.parametrize("bad", ["", "   ", "not-an-id", "<@123>", "123abc"])
def test_a_malformed_id_degrades_instead_of_posting_garbage(monkeypatch, bad):
    """A typo'd snowflake must not ship `<@oops>` into the channel — it should
    fall back to the behaviour that at least sometimes works."""
    monkeypatch.setenv("RISK_DISCORD_USER_ID", bad)
    assert risk_alerts._mention() == "@here"


def test_whitespace_is_tolerated(monkeypatch):
    monkeypatch.setenv("RISK_DISCORD_USER_ID", "  123456789012345678  ")
    assert risk_alerts._mention() == "<@123456789012345678>"


def test_send_uses_the_mention_as_content(monkeypatch):
    sent = {}

    class _Resp:
        status_code = 204

    class _Req:
        @staticmethod
        def post(url, json=None, timeout=None):
            sent["payload"] = json
            return _Resp()

    monkeypatch.setattr(risk_alerts, "_webhook_url", lambda: "https://x/y")
    monkeypatch.setenv("RISK_DISCORD_USER_ID", "42424242424242424")
    monkeypatch.setitem(__import__("sys").modules, "requests", _Req)
    assert risk_alerts._send({"title": "t"}, ping=True) is True
    assert sent["payload"]["content"] == "<@42424242424242424>"


def test_no_ping_means_no_content(monkeypatch):
    sent = {}

    class _Resp:
        status_code = 204

    class _Req:
        @staticmethod
        def post(url, json=None, timeout=None):
            sent["payload"] = json
            return _Resp()

    monkeypatch.setattr(risk_alerts, "_webhook_url", lambda: "https://x/y")
    monkeypatch.setenv("RISK_DISCORD_USER_ID", "42424242424242424")
    monkeypatch.setitem(__import__("sys").modules, "requests", _Req)
    risk_alerts._send({"title": "t"}, ping=False)
    assert "content" not in sent["payload"]
