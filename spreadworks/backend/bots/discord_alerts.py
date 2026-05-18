"""Discord open/close embeds for bot positions.

Reuses `_send_webhook_sync` + `_dedup_ok` from backend.__init__ so we get
the existing 3-attempt retry + cross-process dedup for free.
"""
from __future__ import annotations

from typing import Any


_COLOR = {"open": 0x3498DB, "close_PT": 0x2ECC71, "close_SL": 0xE74C3C,
          "close_EOD": 0xF39C12, "close_FORCE": 0x9B59B6,
          "close_EVENT_HALT": 0xE67E22}


def post_open(*, bot: str, display: str, strategy: str,
              position_id: str, legs: list[dict[str, Any]],
              entry_price: float, contracts: int,
              max_profit: float, max_loss: float) -> bool:
    from .. import _send_webhook_sync, _dedup_ok  # late import to avoid circular
    if not _dedup_ok(f"bot:{bot}:position:{position_id}:open"):
        return False
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
    return _send_webhook_sync(embed)


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
    return _send_webhook_sync(embed)
