"""
ATHENA V2 - Data Models
========================

Clean, minimal data models for ATHENA trading bot.
Single source of truth for all position and configuration data.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any
from zoneinfo import ZoneInfo

CENTRAL_TZ = ZoneInfo("America/Chicago")


class TradingMode(Enum):
    """Trading execution mode"""
    PAPER = "paper"
    LIVE = "live"


class SpreadType(Enum):
    """Type of directional spread"""
    BULL_CALL = "BULL_CALL_SPREAD"  # Bullish debit spread
    BEAR_PUT = "BEAR_PUT_SPREAD"    # Bearish debit spread


class PositionStatus(Enum):
    """Position lifecycle status"""
    OPEN = "open"
    CLOSED = "closed"
    EXPIRED = "expired"


@dataclass
class SpreadPosition:
    """
    Represents a directional spread position.

    This is the ONLY position object used throughout the system.
    All fields are explicitly defined - no hidden state.
    """
    # Identity
    position_id: str

    # Trade details
    spread_type: SpreadType
    ticker: str
    long_strike: float
    short_strike: float
    expiration: str  # YYYY-MM-DD format

    # Pricing
    entry_debit: float  # Cost to enter (positive = debit)
    contracts: int

    # Calculated at entry
    max_profit: float
    max_loss: float
    underlying_at_entry: float

    # Market context at entry
    call_wall: float = 0.0
    put_wall: float = 0.0
    gex_regime: str = ""
    vix_at_entry: float = 0.0

    # Oracle/ML context
    oracle_confidence: float = 0.0
    ml_direction: str = ""
    ml_confidence: float = 0.0

    # Order tracking
    order_id: str = ""

    # Status
    status: PositionStatus = PositionStatus.OPEN
    open_time: datetime = field(default_factory=lambda: datetime.now(CENTRAL_TZ))
    close_time: Optional[datetime] = None
    close_price: float = 0.0
    close_reason: str = ""
    realized_pnl: float = 0.0

    @property
    def spread_width(self) -> float:
        """Width between strikes"""
        return abs(self.short_strike - self.long_strike)

    @property
    def breakeven(self) -> float:
        """Breakeven price for the spread"""
        if self.spread_type == SpreadType.BULL_CALL:
            return self.long_strike + self.entry_debit
        else:  # BEAR_PUT
            return self.long_strike - self.entry_debit

    @property
    def is_open(self) -> bool:
        """Check if position is still open"""
        return self.status == PositionStatus.OPEN

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for DB/logging"""
        return {
            'position_id': self.position_id,
            'spread_type': self.spread_type.value,
            'ticker': self.ticker,
            'long_strike': self.long_strike,
            'short_strike': self.short_strike,
            'expiration': self.expiration,
            'entry_debit': self.entry_debit,
            'contracts': self.contracts,
            'max_profit': self.max_profit,
            'max_loss': self.max_loss,
            'underlying_at_entry': self.underlying_at_entry,
            'call_wall': self.call_wall,
            'put_wall': self.put_wall,
            'gex_regime': self.gex_regime,
            'vix_at_entry': self.vix_at_entry,
            'oracle_confidence': self.oracle_confidence,
            'ml_direction': self.ml_direction,
            'ml_confidence': self.ml_confidence,
            'order_id': self.order_id,
            'status': self.status.value,
            'open_time': self.open_time.isoformat() if self.open_time else None,
            'close_time': self.close_time.isoformat() if self.close_time else None,
            'close_price': self.close_price,
            'close_reason': self.close_reason,
            'realized_pnl': self.realized_pnl,
        }


@dataclass
class ATHENAConfig:
    """
    ATHENA configuration - all settings in one place.

    Loaded from database, with sensible defaults.
    """
    # Risk limits
    risk_per_trade_pct: float = 2.0
    max_daily_trades: int = 5
    max_open_positions: int = 3

    # Strategy params
    ticker: str = "SPY"
    spread_width: int = 2  # $2 spreads
    wall_filter_pct: float = 0.5  # Only trade within 0.5% of GEX wall
    min_rr_ratio: float = 1.5  # Min risk:reward

    # Exit rules
    profit_target_pct: float = 50.0  # Take profit at 50% of max
    stop_loss_pct: float = 50.0  # Stop at 50% of max loss

    # Trading window (Central Time)
    entry_start: str = "08:35"
    entry_end: str = "14:30"
    force_exit: str = "15:55"

    # Mode
    mode: TradingMode = TradingMode.PAPER

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ATHENAConfig':
        """Create config from dictionary (e.g., from DB)"""
        config = cls()
        for key, value in data.items():
            if hasattr(config, key):
                if key == 'mode':
                    value = TradingMode(value)
                setattr(config, key, value)
        return config


@dataclass
class TradeSignal:
    """
    A trading signal with all context needed for execution.
    """
    direction: str  # "BULLISH" or "BEARISH"
    spread_type: SpreadType
    confidence: float

    # Market context
    spot_price: float
    call_wall: float
    put_wall: float
    gex_regime: str
    vix: float

    # Target strikes
    long_strike: float
    short_strike: float
    expiration: str

    # Pricing
    estimated_debit: float
    max_profit: float
    max_loss: float
    rr_ratio: float

    # Source
    source: str = "ML"  # "ML", "ORACLE", or "COMBINED"
    reasoning: str = ""

    @property
    def is_valid(self) -> bool:
        """Check if signal passes basic validation"""
        return (
            self.confidence > 0.5 and
            self.rr_ratio >= 1.5 and
            self.max_profit > 0 and
            self.long_strike > 0 and
            self.short_strike > 0
        )


@dataclass
class DailySummary:
    """Daily trading summary"""
    date: str
    trades_executed: int = 0
    positions_closed: int = 0
    realized_pnl: float = 0.0
    open_positions: int = 0
    unrealized_pnl: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            'date': self.date,
            'trades_executed': self.trades_executed,
            'positions_closed': self.positions_closed,
            'realized_pnl': self.realized_pnl,
            'open_positions': self.open_positions,
            'unrealized_pnl': self.unrealized_pnl,
        }
