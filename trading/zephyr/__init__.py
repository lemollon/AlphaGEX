"""
ZEPHYR (display: ASAHEL) - Kalshi Live-Sports Scalper
=====================================================

A single-venue Kalshi scalper for live (in-game) sports markets.

Strategy: anchor Kalshi's live price to a fast sharp "fair value", capture the
deviation, and get flat in seconds-to-minutes. ZEPHYR does NOT hold to
settlement - it trades the price *path*, not the game outcome.

Three things decide profitability (all execution, not prediction):
  1. Fee gate      - never enter unless modeled edge > round-trip fees.
  2. Score kill    - on any scoring event, cancel + flatten immediately.
  3. Exit discipline - time-stop + revert-to-fair + max-hold guillotine so a
                       scalp can never silently become a hold.

Decision authority: `fairvalue.py` (the sports analog of PROPHET). PROPHET
itself is GEX/options-specific and does NOT apply to this bot.
"""

from .models import (
    MARKETS,
    ZephyrConfig,
    ScalpPosition,
    FairValueQuote,
    GameEvent,
    ScalpSignal,
    PositionStatus,
    Side,
    SignalAction,
    ExitReason,
    kalshi_fee,
    round_trip_fee,
)

__all__ = [
    "MARKETS",
    "ZephyrConfig",
    "ScalpPosition",
    "FairValueQuote",
    "GameEvent",
    "ScalpSignal",
    "PositionStatus",
    "Side",
    "SignalAction",
    "ExitReason",
    "kalshi_fee",
    "round_trip_fee",
    "create_zephyr_trader",
]


def create_zephyr_trader(*args, **kwargs):
    """Lazy factory so importing the package never hard-fails on optional deps."""
    from .trader import ZephyrTrader
    return ZephyrTrader(*args, **kwargs)
