"""Discord open/close embeds for bot positions.

Reuses `_send_webhook_sync` + `_dedup_ok` from backend.__init__ so we get
the existing 3-attempt retry + cross-process dedup for free.
"""
from __future__ import annotations

import os
from typing import Any


_COLOR = {"open": 0x3498DB, "close_PT": 0x2ECC71, "close_SL": 0xE74C3C,
          "close_EOD": 0xF39C12, "close_FORCE": 0x9B59B6,
          "close_EVENT_HALT": 0xE67E22, "close_SETTLE": 0x95A5A6}


def _webhook_url(bot: str) -> str | None:
    """Per-bot webhook override, read from the registry.

    `BOT_REGISTRY[bot]["discord_webhook_env"]` names an env var to use
    INSTEAD of the module-wide DISCORD_WEBHOOK_URL (e.g. EBB routes to
    RISK_ADVISOR_DISCORD_WEBHOOK — the risk-advisor channel — falling back
    to DISCORD_WEBHOOK_URL, same resolution as risk_alerts._webhook_url()).
    Returns None when a bot has no override, so the caller's default
    (module-wide) webhook applies.
    """
    from .registry import BOT_REGISTRY
    env_name = (BOT_REGISTRY.get(bot) or {}).get("discord_webhook_env")
    if not env_name:
        return None
    return os.getenv(env_name, "") or os.getenv("DISCORD_WEBHOOK_URL", "")


def post_open(*, bot: str, display: str, strategy: str,
              position_id: str, legs: list[dict[str, Any]],
              entry_price: float, contracts: int,
              max_profit: float, max_loss: float) -> bool:
    from .. import _send_webhook_sync, _dedup_ok  # late import to avoid circular
    if not _dedup_ok(f"bot:{bot}:position:{position_id}:open"):
        return False
    webhook_url = _webhook_url(bot)
    if bot in ("ebb", "ebb_pm"):
        # EBB / EBB PM's validated 0DTE bull put spread — a plain-language
        # line to the risk-advisor channel instead of the generic legs-table
        # embed (research registry #23b / #41-#42 format, 2026-08-13).
        long_k = next((l["strike"] for l in legs if l["side"] == "long"), None)
        short_k = next((l["strike"] for l in legs if l["side"] == "short"), None)
        embed = {
            "description": (f"\U0001f30a {display} opened: SPY {short_k:.0f}/{long_k:.0f} "
                            f"put spread exp today · credit ${entry_price:.2f} "
                            f"· 1 ct"),
            "color": _COLOR["open"],
        }
        return _send_webhook_sync(embed, webhook_url=webhook_url)
    legs_text = "\n".join(
        f"  {l['side'].upper():5} {l['type'].upper():4} {l['strike']} {l['expiration']} @ {float(l['entry_price']):.2f}"
        for l in legs
    )
    embed = {
        "title": f"{display} — OPEN {strategy}",
        "description": f"`{position_id}`",
        "color": _COLOR["open"],
        "fields": [
            {"name": "Entry", "value": f"{entry_price:.2f}", "inline": True},
            {"name": "Contracts", "value": str(contracts), "inline": True},
            {"name": "Max Profit / Loss",
             "value": f"${max_profit:.0f} / ${max_loss:.0f}", "inline": True},
            {"name": "Legs", "value": f"```\n{legs_text}\n```", "inline": False},
        ],
    }
    return _send_webhook_sync(embed, webhook_url=webhook_url)


def post_close(*, bot: str, display: str, strategy: str,
               position_id: str, close_reason: str,
               realized_pnl: float, time_in_trade_min: int) -> bool:
    from .. import _send_webhook_sync, _dedup_ok
    if not _dedup_ok(f"bot:{bot}:position:{position_id}:close"):
        return False
    color = _COLOR.get(f"close_{close_reason}", 0x95A5A6)
    sign = "+" if realized_pnl >= 0 else ""
    embed = {
        "title": f"{display} — CLOSE {strategy} ({close_reason})",
        "description": f"`{position_id}`",
        "color": color,
        "fields": [
            {"name": "Realized P&L", "value": f"{sign}${realized_pnl:.2f}", "inline": True},
            {"name": "Time in Trade", "value": f"{time_in_trade_min} min", "inline": True},
        ],
    }
    return _send_webhook_sync(embed, webhook_url=_webhook_url(bot))


def post_settle(*, bot: str, display: str, strategy: str,
                position_id: str, realized_pnl: float,
                n_trades: int | None = None,
                total_pnl: float | None = None) -> bool:
    """Settle-at-expiry close (RIPPLE, SPLASH, EBB, EBB PM). The scanner's
    cash-settlement path never calls `post_close` — there is no PT/SL/EOD
    close reason to report, only intrinsic-vs-official-close — so this is the
    dedicated hook for it.

    EBB / EBB PM get their own plain-language running-total line to the
    risk-advisor channel; other settle_at_expiry bots fall back to a generic
    SETTLE embed on their normal (module-wide) webhook.
    """
    from .. import _send_webhook_sync, _dedup_ok
    if not _dedup_ok(f"bot:{bot}:position:{position_id}:settle"):
        return False
    webhook_url = _webhook_url(bot)
    if bot in ("ebb", "ebb_pm"):
        sign = "+" if realized_pnl >= 0 else ""
        n_str = str(n_trades) if n_trades is not None else "?"
        if total_pnl is not None:
            total_str = f"{'+' if total_pnl >= 0 else ''}{total_pnl:,.2f}"
        else:
            total_str = "?"
        embed = {
            "description": (f"\U0001f30a {display} settled: {sign}${realized_pnl:.2f} "
                            f"· {n_str} trades so far · total "
                            f"${total_str}"),
            "color": _COLOR["close_PT"] if realized_pnl >= 0 else _COLOR["close_SL"],
        }
        return _send_webhook_sync(embed, webhook_url=webhook_url)
    sign = "+" if realized_pnl >= 0 else ""
    embed = {
        "title": f"{display} — CLOSE {strategy} (SETTLE)",
        "description": f"`{position_id}`",
        "color": _COLOR["close_SETTLE"],
        "fields": [
            {"name": "Realized P&L", "value": f"{sign}${realized_pnl:.2f}", "inline": True},
        ],
    }
    return _send_webhook_sync(embed, webhook_url=webhook_url)
