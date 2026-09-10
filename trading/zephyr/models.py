"""
ZEPHYR Models - Multi-sport Kalshi live-scalper config + dataclasses.

Prices on Kalshi trade in CENTS (1..99) for a contract that settles at $1.00
(100c) or $0.00. Internally we keep "fair value" as a probability in [0, 1]
and Kalshi prices as cents; helpers convert between them.

Everything here is pure (no I/O) so it can be unit-tested without credentials.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo

CENTRAL_TZ = ZoneInfo("America/Chicago")


# ==============================================================================
# FEE MODEL  (the make-or-break for a scalper)
# ==============================================================================
# Kalshi's general trading fee:  fee = ceil(coeff * C * P * (1 - P))  in dollars
# where C = contracts and P = price in DOLLARS (0..1). The fee is maximized at
# P = 0.50 and shrinks toward the 1c/99c extremes - which is exactly why a
# scalper prefers cheap-fee price zones.
#
# VERIFY before live trading: Kalshi's per-market sports schedule and whether
# *maker* (resting) orders are fee-free. The coefficients below are the
# documented general defaults; override per-market in MARKETS[...]["fees"].
DEFAULT_TAKER_FEE_COEFF = 0.07
DEFAULT_MAKER_FEE_COEFF = 0.00  # most Kalshi markets: makers pay no trading fee


def kalshi_fee(price_cents: float, contracts: int, coeff: float = DEFAULT_TAKER_FEE_COEFF) -> float:
    """Per-side Kalshi trading fee in dollars. price_cents in 1..99."""
    if coeff <= 0 or contracts <= 0:
        return 0.0
    p = max(0.0, min(1.0, price_cents / 100.0))
    raw = coeff * contracts * p * (1.0 - p)
    # Kalshi rounds the fee UP to the next cent.
    return math.ceil(raw * 100.0) / 100.0


def round_trip_fee(
    entry_cents: float,
    exit_cents: float,
    contracts: int,
    entry_coeff: float = DEFAULT_TAKER_FEE_COEFF,
    exit_coeff: float = DEFAULT_TAKER_FEE_COEFF,
) -> float:
    """Total entry + exit fee in dollars for a round-trip scalp."""
    return (
        kalshi_fee(entry_cents, contracts, entry_coeff)
        + kalshi_fee(exit_cents, contracts, exit_coeff)
    )


# ==============================================================================
# ENUMS
# ==============================================================================
class Side(str, Enum):
    YES = "YES"
    NO = "NO"


class PositionStatus(str, Enum):
    OPEN = "open"
    CLOSED = "closed"
    PENDING = "pending"  # resting maker order, not yet filled


class SignalAction(str, Enum):
    NONE = "NONE"            # no edge / blocked by fee gate
    BUY_YES_MAKER = "BUY_YES_MAKER"
    BUY_YES_TAKER = "BUY_YES_TAKER"
    BUY_NO_MAKER = "BUY_NO_MAKER"
    BUY_NO_TAKER = "BUY_NO_TAKER"


class ExitReason(str, Enum):
    REVERT_TO_FAIR = "revert_to_fair"   # price came back to fair -> take profit
    TIME_STOP = "time_stop"             # held longer than target scalp window
    MAX_HOLD = "max_hold"               # absolute guillotine
    SCORE_KILL = "score_kill"           # scoring event -> flatten immediately
    STOP_LOSS = "stop_loss"             # adverse move beyond tolerance
    EOG = "end_of_game"                 # market closing / game ending


# ==============================================================================
# PER-SPORT CONFIG  (generic from day one -> multi-sport)
# ==============================================================================
# A scalper wants high event frequency + lower jump magnitude + liquidity.
# MLB is the gentlest (best maker-scalp); NFL the most violent. Tune per sport.
MARKETS: Dict[str, Dict[str, Any]] = {
    "MLB": {
        "display_name": "MLB",
        "kalshi_series": "KXMLBGAME",   # Kalshi event-ticker series root
        "enabled": True,
        "starting_capital": 500.0,
        "max_contracts_per_scalp": 5,    # tiny live size to start
        "max_open_scalps": 2,
        # Scalp economics (all in CENTS of edge unless noted)
        "min_edge_buffer_cents": 1.5,    # required edge ON TOP of round-trip fee
        "exit_band_cents": 1.0,          # exit when |mid - fair| <= this
        "stop_loss_cents": 4.0,          # adverse move tolerance before bailing
        # Timing (seconds) - a scalp must never become a hold
        "max_scalp_seconds": 180,        # time-stop
        "max_hold_seconds": 600,         # absolute guillotine
        "score_kill_window_seconds": 8,  # flatten if a score lands within window
        # Price-zone preference: avoid the expensive mid where fees peak
        "avoid_mid_band": (40, 60),      # de-prioritize 40-60c entries
        "fees": {"taker_coeff": 0.07, "maker_coeff": 0.00},
    },
    "NBA": {
        "display_name": "NBA",
        "kalshi_series": "KXNBAGAME",
        "enabled": True,
        "starting_capital": 500.0,
        "max_contracts_per_scalp": 5,
        "max_open_scalps": 2,
        "min_edge_buffer_cents": 2.0,    # more violent -> demand more edge
        "exit_band_cents": 1.0,
        "stop_loss_cents": 5.0,
        "max_scalp_seconds": 120,
        "max_hold_seconds": 420,
        "score_kill_window_seconds": 6,
        "avoid_mid_band": (40, 60),
        "fees": {"taker_coeff": 0.07, "maker_coeff": 0.00},
    },
    "NFL": {
        "display_name": "NFL",
        "kalshi_series": "KXNFLGAME",
        "enabled": False,                # hardest scalp profile - off until proven
        "starting_capital": 500.0,
        "max_contracts_per_scalp": 3,
        "max_open_scalps": 1,
        "min_edge_buffer_cents": 3.0,
        "exit_band_cents": 1.5,
        "stop_loss_cents": 6.0,
        "max_scalp_seconds": 90,
        "max_hold_seconds": 360,
        "score_kill_window_seconds": 5,
        "avoid_mid_band": (40, 60),
        "fees": {"taker_coeff": 0.07, "maker_coeff": 0.00},
    },
}


def market_config(sport: str) -> Dict[str, Any]:
    """Return per-sport config, defaulting to MLB params for unknown sports."""
    return MARKETS.get(sport.upper(), MARKETS["MLB"])


# ==============================================================================
# DATACLASSES
# ==============================================================================
@dataclass
class ZephyrConfig:
    """Top-level bot config. Persisted in zephyr_config; never hardcode capital."""
    bot_name: str = "ZEPHYR"
    display_name: str = "ASAHEL"
    live_enabled: bool = False          # gates real-money order submission
    paper_locked: bool = True           # safety: must be explicitly unlocked
    fair_value_provider: str = "espn"   # "espn" (free) | "odds_api" (production)
    max_total_open_scalps: int = 3
    starting_capital: float = 500.0


@dataclass
class FairValueQuote:
    """A sharp 'fair value' for one Kalshi market side, as probability [0,1]."""
    market_id: str
    fair_prob: float            # P(YES settles at $1)
    source: str                 # "espn" | "odds_api" | ...
    ts: datetime
    confidence: float = 0.5     # provider-reported reliability, 0..1
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def fair_cents(self) -> float:
        return round(self.fair_prob * 100.0, 2)


@dataclass
class GameEvent:
    """A scoring (or other risk-relevant) event from the game feed."""
    market_id: str
    sport: str
    event_type: str             # "score", "turnover", "period_end", ...
    ts: datetime
    detail: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_score(self) -> bool:
        return self.event_type == "score"


@dataclass
class ScalpSignal:
    """Output of signals.evaluate(): what to do, and why."""
    action: SignalAction
    market_id: str
    sport: str
    side: Optional[Side]
    limit_cents: Optional[float]      # price to post/cross at
    contracts: int
    fair_cents: float
    kalshi_mid_cents: float
    edge_cents: float                 # signed edge in our favor before fees
    required_edge_cents: float        # fee + buffer that edge had to clear
    reason: str

    @property
    def is_trade(self) -> bool:
        return self.action != SignalAction.NONE


@dataclass
class ScalpPosition:
    """An open or closed scalp. P&L is path-based, not settlement-based."""
    position_id: str
    market_id: str
    sport: str
    side: Side
    contracts: int
    entry_cents: float
    status: PositionStatus = PositionStatus.OPEN
    is_maker: bool = True
    open_time: Optional[datetime] = None
    fair_at_entry_cents: Optional[float] = None
    # exit
    close_time: Optional[datetime] = None
    exit_cents: Optional[float] = None
    exit_reason: Optional[ExitReason] = None
    realized_pnl: Optional[float] = None
    entry_fee: float = 0.0
    exit_fee: float = 0.0
    # bookkeeping
    is_paper: bool = True
    kalshi_order_id: Optional[str] = None

    def gross_pnl(self, exit_cents: float) -> float:
        """Gross $ P&L of closing at exit_cents (long the chosen side)."""
        # Both YES and NO are modeled as longs of that side's contract; the
        # entry_cents/exit_cents are already that side's price.
        return (exit_cents - self.entry_cents) / 100.0 * self.contracts
