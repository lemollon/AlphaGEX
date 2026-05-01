"""GOLIATH Phase 7 monitoring package.

Three modules:
    discord     -- webhook poster + embed builders (DISCORD_WEBHOOK_URL)
    heartbeat   -- writes to bot_heartbeats table per AlphaGEX convention
    alerts      -- threshold checks + alert composition

Public API exposed here.
"""
from . import alerts, discord, heartbeat

__all__ = ["alerts", "discord", "heartbeat"]
