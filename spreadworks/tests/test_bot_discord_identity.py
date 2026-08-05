"""Per-bot Discord webhook identity (username + avatar) for bot alerts."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.bots import identity

SPREADWORKS = Path(__file__).resolve().parent.parent
DIST_BOTS = SPREADWORKS / "frontend" / "dist" / "bots"
PUBLIC_BOTS = SPREADWORKS / "frontend" / "public" / "bots"


def test_every_registry_bot_has_an_avatar():
    """A bot with no PNG posts under the generic SpreadWorks icon — the exact
    thing this feature exists to fix. Fails loudly when a bot is added to the
    registry without re-running gen_bot_avatars.py."""
    from backend.bots.registry import BOT_REGISTRY

    missing = sorted(set(BOT_REGISTRY) - identity.AVATAR_KEYS)
    assert not missing, (
        f"No Discord avatar for {missing}. Run "
        "`python spreadworks/scripts/gen_bot_avatars.py` and add the key(s) "
        "to identity.AVATAR_KEYS."
    )


def test_avatar_keys_all_have_files_on_disk():
    """AVATAR_KEYS is a hand-maintained literal — if it drifts ahead of the
    generated files, Discord gets a 404 URL and shows a broken grey avatar,
    which is WORSE than sending no avatar_url at all."""
    for key in sorted(identity.AVATAR_KEYS):
        assert (DIST_BOTS / f"{key}.png").is_file(), f"missing dist/bots/{key}.png"
        assert (PUBLIC_BOTS / f"{key}.png").is_file(), f"missing public/bots/{key}.png"


def test_identity_shape_for_known_bot():
    ident = identity.bot_identity("surge", "SURGE")
    assert ident["username"] == "SURGE"
    assert ident["avatar_url"].endswith("/bots/surge.png")
    assert ident["avatar_url"].startswith("https://")


def test_unknown_bot_omits_avatar_but_keeps_name():
    ident = identity.bot_identity("nosuchbot", "NOSUCHBOT")
    assert ident == {"username": "NOSUCHBOT"}, (
        "an unknown bot must NOT get an avatar_url — a 404 renders as a broken "
        "grey icon, whereas omitting it falls back to the SpreadWorks logo"
    )


def test_empty_bot_sends_no_override():
    assert identity.bot_identity("") == {}
    assert identity.bot_identity(None) == {}  # type: ignore[arg-type]


def test_public_base_url_env_override(monkeypatch):
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://example.test/")
    assert identity.avatar_url("tide") == "https://example.test/bots/tide.png"


def _capture_payload(monkeypatch):
    """Patch requests.post inside _send_webhook_sync and capture the JSON body."""
    import requests

    captured: dict = {}

    class _Resp:
        status_code = 204

        def raise_for_status(self):
            return None

    def _fake_post(url, json=None, **kw):  # noqa: A002
        captured["url"] = url
        captured["json"] = json
        return _Resp()

    monkeypatch.setattr(requests, "post", _fake_post)
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.test/webhook")
    return captured


def test_send_webhook_omits_identity_when_not_given(monkeypatch):
    """Briefings must keep the webhook's own SpreadWorks name + icon. Sending
    the keys as null does NOT fall back — they have to be absent."""
    from backend import _send_webhook_sync

    captured = _capture_payload(monkeypatch)
    assert _send_webhook_sync({"title": "morning brief"}) is True
    assert captured["json"] == {"embeds": [{"title": "morning brief"}]}


def test_send_webhook_includes_identity_when_given(monkeypatch):
    from backend import _send_webhook_sync

    captured = _capture_payload(monkeypatch)
    _send_webhook_sync({"title": "x"}, username="SURGE",
                       avatar_url="https://h/bots/surge.png")
    assert captured["json"]["username"] == "SURGE"
    assert captured["json"]["avatar_url"] == "https://h/bots/surge.png"


def test_username_is_clamped(monkeypatch):
    """Discord 400s the whole POST on an over-length username — losing the
    trade alert to save the nameplate would be a bad trade."""
    from backend import _send_webhook_sync

    captured = _capture_payload(monkeypatch)
    _send_webhook_sync({"title": "x"}, username="A" * 200)
    assert len(captured["json"]["username"]) == 80


def test_post_open_sends_bot_identity(monkeypatch):
    """End-to-end through the real alert path — this is the behaviour the
    feature is actually judged on."""
    from backend.bots import discord_alerts

    captured = _capture_payload(monkeypatch)
    monkeypatch.setattr("backend._dedup_ok", lambda key: True)

    discord_alerts.post_open(
        bot="splash", display="SPLASH", strategy="long_butterfly",
        position_id="pos-1",
        legs=[{"side": "buy", "type": "call", "strike": 500,
               "expiration": "2026-08-04", "entry_price": 1.0}],
        entry_price=1.0, contracts=1, max_profit=100.0, max_loss=-50.0,
    )
    assert captured["json"]["username"] == "SPLASH"
    assert captured["json"]["avatar_url"].endswith("/bots/splash.png")


def test_post_close_sends_bot_identity(monkeypatch):
    from backend.bots import discord_alerts

    captured = _capture_payload(monkeypatch)
    monkeypatch.setattr("backend._dedup_ok", lambda key: True)

    discord_alerts.post_close(
        bot="ripple", display="RIPPLE", strategy="long_butterfly",
        position_id="pos-2", close_reason="PT", realized_pnl=12.5,
        time_in_trade_min=90,
    )
    assert captured["json"]["username"] == "RIPPLE"
    assert captured["json"]["avatar_url"].endswith("/bots/ripple.png")


def test_monograms_are_unique():
    """Two bots sharing a monogram AND a palette entry (UPDRAFT and EMBER are
    both amber-400) would be indistinguishable in the feed."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "gen_bot_avatars", SPREADWORKS / "scripts" / "gen_bot_avatars.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    monos = list(mod.MONOGRAM.values())
    assert len(monos) == len(set(monos)), "duplicate monogram"
