"""Shared post-liquidation position cleanup for AGAPE perp bots.

Two independent problems, closed in the same pass right before the normal
per-position exit loop (after liquidation handling):

1. Legacy-strategy close: `config.strategy_mode` can be flipped from
   "combined_signal" to "weekly_breakout" (or back) without ever touching
   positions that are already open. A position opened under the old
   strategy has no stop/trail semantics the new strategy understands, and
   worse - while it sits open it silently eats a slot out of the new mode's
   (usually much smaller) `max_open_positions`, so every future scan comes
   back BLOCKED_MAX_POSITIONS forever. When the bot is currently in
   "weekly_breakout" mode, any open position that was NOT opened by the
   weekly-breakout entry path is force-closed with reason STRATEGY_CHANGED.

   The marker: `decide_entry()` in weekly_breakout.py always returns a
   reason of the form "WEEKLY_BREAKOUT_<...>" (see signals.py's
   `_weekly_breakout_signal`, which seeds the signal's `reasoning` with
   that string), and that reasoning is persisted verbatim as
   `signal_reasoning` on the position row. No combined-signal reasoning
   string (see `_determine_action`) ever starts with that prefix, so a
   `signal_reasoning` that is missing or doesn't start with
   "WEEKLY_BREAKOUT_" reliably means "not a weekly-breakout entry" -
   including every position opened before this strategy existed.

2. Over-cap trim: after step 1, if open positions still exceed
   `config.max_open_positions` (e.g. the cap itself was lowered under a
   live position), the oldest excess positions are force-closed with
   reason OVER_POSITION_CAP so the bot can resume trading immediately
   instead of waiting for them to exit naturally.

Both steps close through `trader._close_position(pos, current_price,
reason)` - the same path normal exits and liquidation already use - so
P&L, funding accrual, consecutive-loss tracking, and equity snapshots all
stay consistent. Every close is logged at WARNING via `trader.db.log(...)`
so it shows up in the bot's activity log.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)

WB_REASONING_PREFIX = "WEEKLY_BREAKOUT_"


def close_legacy_and_overcap_positions(
    trader,
    open_positions: List[Dict],
    current_price: float,
    wb_prefix: str = WB_REASONING_PREFIX,
) -> Tuple[List[Dict], int]:
    """Close positions stranded by a strategy_mode change, then trim to cap.

    Returns (still_open_positions, num_closed). Never raises - a failed
    close just leaves that position in still_open_positions for the normal
    exit loop to retry next cycle.
    """
    if not open_positions or not current_price:
        return open_positions, 0

    bot_name = getattr(trader.config, "bot_name", "?")
    remaining = list(open_positions)
    closed = 0

    # 1. Legacy-strategy close.
    if getattr(trader.config, "strategy_mode", "") == "weekly_breakout":
        keep = []
        for pos in remaining:
            reasoning = pos.get("signal_reasoning") or ""
            if reasoning.startswith(wb_prefix):
                keep.append(pos)
                continue
            try:
                success = trader._close_position(pos, current_price, "STRATEGY_CHANGED")
            except Exception as e:
                logger.error(f"{bot_name}: legacy-strategy close failed for "
                             f"{pos.get('position_id')}: {e}")
                success = False
            if success:
                closed += 1
                trader.db.log(
                    "WARNING", "STRATEGY_CHANGED",
                    f"Closed legacy position {pos.get('position_id')} opened under a prior "
                    f"strategy_mode (signal_reasoning={reasoning[:80] or 'none'!r})",
                    details={"position_id": pos.get("position_id"), "reasoning": reasoning},
                )
            else:
                keep.append(pos)
        remaining = keep

    # 2. Over-cap trim (oldest first).
    max_positions = getattr(trader.config, "max_open_positions", None)
    if max_positions and len(remaining) > max_positions:
        remaining.sort(key=lambda p: p.get("open_time") or "")
        excess = len(remaining) - max_positions
        still_open = list(remaining)
        for pos in remaining[:excess]:
            try:
                success = trader._close_position(pos, current_price, "OVER_POSITION_CAP")
            except Exception as e:
                logger.error(f"{bot_name}: over-cap close failed for "
                             f"{pos.get('position_id')}: {e}")
                success = False
            if success:
                closed += 1
                still_open.remove(pos)
                trader.db.log(
                    "WARNING", "OVER_POSITION_CAP",
                    f"Closed {pos.get('position_id')} - open positions exceeded "
                    f"cap of {max_positions}",
                    details={"position_id": pos.get("position_id"), "max_open_positions": max_positions},
                )
        remaining = still_open

    return remaining, closed
