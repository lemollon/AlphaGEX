"""
ZEPHYR Risk - exit decisions + the score-event kill switch (pure logic).

A scalp must NEVER silently become a hold. Every open position is evaluated
each tick against, in priority order:
  1. SCORE_KILL  - a scoring event landed since/around entry -> flatten now.
  2. MAX_HOLD    - absolute guillotine on hold time.
  3. STOP_LOSS   - adverse move beyond tolerance.
  4. TIME_STOP   - held past the target scalp window.
  5. REVERT_TO_FAIR - price returned to fair -> take the scalp profit.

The score kill is a RISK CONTROL: it cannot be disabled without explicit
approval (same class as the paper lock).
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from .models import (
    CENTRAL_TZ,
    ExitReason,
    FairValueQuote,
    GameEvent,
    ScalpPosition,
    Side,
    market_config,
)


def _now() -> datetime:
    return datetime.now(CENTRAL_TZ)


def current_side_price(pos: ScalpPosition, yes_bid: float, yes_ask: float) -> float:
    """Marketable exit price for the side we're long (we cross to get out)."""
    if pos.side == Side.YES:
        return yes_bid           # sell YES into the bid
    return 100.0 - yes_ask        # sell NO == buy back YES at ask -> 100-ask


def score_event_since(
    pos: ScalpPosition,
    events: List[GameEvent],
    window_seconds: float,
) -> Optional[GameEvent]:
    """Return the first scoring event relevant to this position's market."""
    if not pos.open_time:
        return None
    for ev in events:
        if ev.market_id != pos.market_id or not ev.is_score:
            continue
        # any score at/after entry (minus a small window for feed jitter)
        if (ev.ts - pos.open_time).total_seconds() >= -window_seconds:
            return ev
    return None


def evaluate_exit(
    pos: ScalpPosition,
    yes_bid: float,
    yes_ask: float,
    fair: Optional[FairValueQuote],
    game_events: Optional[List[GameEvent]] = None,
    now: Optional[datetime] = None,
) -> Optional[ExitReason]:
    """Return an ExitReason if the position should be closed now, else None."""
    cfg = market_config(pos.sport)
    now = now or _now()
    game_events = game_events or []
    exit_px = current_side_price(pos, yes_bid, yes_ask)

    # 1) SCORE KILL (highest priority, non-negotiable)
    ev = score_event_since(pos, game_events, float(cfg.get("score_kill_window_seconds", 8)))
    if ev is not None:
        return ExitReason.SCORE_KILL

    held = (now - pos.open_time).total_seconds() if pos.open_time else 0.0

    # 2) MAX HOLD guillotine
    if held >= float(cfg.get("max_hold_seconds", 600)):
        return ExitReason.MAX_HOLD

    # 3) STOP LOSS (adverse move from entry, in cents)
    adverse = pos.entry_cents - exit_px  # positive = we're underwater
    if adverse >= float(cfg.get("stop_loss_cents", 5.0)):
        return ExitReason.STOP_LOSS

    # 4) TIME STOP
    if held >= float(cfg.get("max_scalp_seconds", 180)):
        return ExitReason.TIME_STOP

    # 5) REVERT TO FAIR -> take profit when price has come back to fair value
    if fair is not None:
        if pos.side == Side.YES:
            mid_vs_fair = fair.fair_cents - (yes_bid + yes_ask) / 2.0
        else:
            mid_vs_fair = ((yes_bid + yes_ask) / 2.0) - fair.fair_cents
        # once the gap has closed to within the exit band, harvest
        if abs(mid_vs_fair) <= float(cfg.get("exit_band_cents", 1.0)):
            # only harvest if we're at/above entry (otherwise let stop/time act)
            if exit_px >= pos.entry_cents:
                return ExitReason.REVERT_TO_FAIR

    return None
