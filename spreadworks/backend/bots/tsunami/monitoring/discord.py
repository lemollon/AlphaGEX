"""TSUNAMI Discord webhook poster + embed builders.

Webhook resolution (2026-07-10, Leron: TSUNAMI gets its own channel):
``TSUNAMI_DISCORD_WEBHOOK_URL`` if set, else the platform-standard
``DISCORD_WEBHOOK_URL`` (shared with spreadworks-daily-bot and ironforge
FLAME/SPARK). Posts compact embed messages for trade events, kill-switch
fires, and alert notifications.

Design choices:
    - Best-effort: webhook failures NEVER block trading. All HTTP errors,
      timeouts, and missing-env-var conditions log and return False.
    - 5-second timeout: Discord webhook should respond within ~1s; 5s
      gives slack for transient lag.
    - No retries: Discord rate-limits at 30 req/min per webhook. A
      retry storm during an outage would be worse than dropping events.
    - Color codes match the IronForge convention (green/red/grey/amber)
      so messages from different AlphaGEX bots feel consistent.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)

# Discord embed colors (decimal RGB) -- matches ironforge/webapp/src/lib/discord.ts.
COLOR_OPEN = 0x2ECC71      # green
COLOR_WIN = 0x16A085        # dark green / teal
COLOR_LOSS = 0xE74C3C       # red
COLOR_NEUTRAL = 0x95A5A6    # grey
COLOR_WARN = 0xF39C12       # amber
COLOR_KILL = 0x8E44AD       # purple (kill switch / critical)

_TIMEOUT_SECONDS = 5.0
_USER_AGENT = "TSUNAMI-monitoring/1.0"
_ENV_VAR = "TSUNAMI_DISCORD_WEBHOOK_URL"   # dedicated TSUNAMI channel
_FALLBACK_ENV_VAR = "DISCORD_WEBHOOK_URL"  # platform-shared channel


def _webhook_from_env() -> str:
    """Dedicated TSUNAMI webhook if set, else the platform-shared one."""
    return (os.environ.get(_ENV_VAR, "").strip()
            or os.environ.get(_FALLBACK_ENV_VAR, "").strip())


def is_configured() -> bool:
    """True when a TSUNAMI or platform webhook is set in the environment."""
    return bool(_webhook_from_env())


def post_embed(
    title: str,
    description: str,
    color: int = COLOR_NEUTRAL,
    fields: Optional[list[dict[str, Any]]] = None,
    footer_text: Optional[str] = None,
    *,
    webhook_url: Optional[str] = None,
    session: Optional[Any] = None,
) -> bool:
    """Post one embed to Discord. Returns True on success, False on any failure.

    Args:
        title: short embed title (max ~256 chars)
        description: longer body text (max ~4096 chars)
        color: decimal RGB color int
        fields: list of {"name", "value", "inline"} dicts (max 25)
        footer_text: optional footer text (e.g. instance name)
        webhook_url: override env var; mainly for tests
        session: requests.Session for tests; default uses requests directly
    """
    url = webhook_url or _webhook_from_env()
    if not url:
        logger.info("[discord] no TSUNAMI_DISCORD_WEBHOOK_URL or"
                    " DISCORD_WEBHOOK_URL set -- skipping post")
        return False

    embed: dict[str, Any] = {
        "title": title[:256],
        "description": description[:4096],
        "color": color,
    }
    if fields:
        embed["fields"] = fields[:25]
    if footer_text:
        embed["footer"] = {"text": footer_text[:2048]}

    payload = {"embeds": [embed], "username": "TSUNAMI"}
    headers = {"Content-Type": "application/json", "User-Agent": _USER_AGENT}

    try:
        client = session or requests
        resp = client.post(
            url,
            data=json.dumps(payload),
            headers=headers,
            timeout=_TIMEOUT_SECONDS,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[discord] post failed: %r", exc)
        return False

    # Discord returns 204 No Content on success.
    if 200 <= resp.status_code < 300:
        return True
    logger.warning(
        "[discord] post returned HTTP %s: %s",
        resp.status_code, resp.text[:200],
    )
    return False


# ---- Embed builders for TSUNAMI events ------------------------------------

def build_entry_embed(
    instance: str,
    structure: dict[str, Any],
    contracts: int,
) -> dict[str, Any]:
    """Compose an OPEN-event embed payload (returns kwargs for post_embed)."""
    sp = structure.get("short_put_strike")
    lp = structure.get("long_put_strike")
    lc = structure.get("long_call_strike")
    return {
        "title": f"{instance} OPEN",
        "description": f"3-leg structure filled: {contracts} contract(s).",
        "color": COLOR_OPEN,
        "fields": [
            {"name": "Short put", "value": f"${sp}", "inline": True},
            {"name": "Long put", "value": f"${lp}", "inline": True},
            {"name": "Long call", "value": f"${lc}", "inline": True},
            {"name": "Net cost", "value": f"${structure.get('net_cost', 0):.4f}",
             "inline": True},
        ],
        "footer_text": instance,
    }


def build_exit_embed(
    instance: str,
    trigger_id: str,
    realized_pnl: float,
    legs_closed: list[str],
) -> dict[str, Any]:
    """Compose an EXIT embed. Color reflects P&L sign."""
    if realized_pnl > 0:
        color = COLOR_WIN
    elif realized_pnl < 0:
        color = COLOR_LOSS
    else:
        color = COLOR_NEUTRAL
    return {
        "title": f"{instance} CLOSE -- {trigger_id}",
        "description": f"Realized P&L: ${realized_pnl:+.2f}",
        "color": color,
        "fields": [
            {"name": "Trigger", "value": trigger_id, "inline": True},
            {"name": "Legs closed", "value": ", ".join(legs_closed) or "—",
             "inline": True},
        ],
        "footer_text": instance,
    }


def build_kill_embed(
    scope: str,
    instance: Optional[str],
    trigger_id: str,
    reason: str,
) -> dict[str, Any]:
    """Compose a kill-switch fire embed."""
    label = instance if instance else "PLATFORM"
    return {
        "title": f"TSUNAMI KILL {scope} -- {trigger_id}",
        "description": reason,
        "color": COLOR_KILL,
        "fields": [{"name": "Scope", "value": label, "inline": True}],
        "footer_text": f"manual override required to clear ({scope.lower()})",
    }


def build_alert_embed(
    severity: str,  # "WARN" or "PAGE"
    title: str,
    description: str,
    fields: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    """Compose a generic alert embed."""
    color = COLOR_WARN if severity.upper() == "WARN" else COLOR_LOSS
    return {
        "title": f"[{severity.upper()}] {title}",
        "description": description,
        "color": color,
        "fields": fields,
        "footer_text": "TSUNAMI monitoring",
    }
