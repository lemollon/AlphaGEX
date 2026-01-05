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
    PARTIAL_CLOSE = "partial_close"  # One leg closed, other failed - needs manual intervention


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

    # Kronos context (for audit trail)
    flip_point: float = 0.0
    net_gex: float = 0.0

    # Oracle/ML context (FULL for audit)
    oracle_confidence: float = 0.0
    ml_direction: str = ""
    ml_confidence: float = 0.0
    ml_model_name: str = ""
    ml_win_probability: float = 0.0
    ml_top_features: str = ""  # JSON string
    wall_type: str = ""  # PUT_WALL or CALL_WALL
    wall_distance_pct: float = 0.0
    trade_reasoning: str = ""  # Full reasoning

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
        """Convert to dictionary for DB/logging with FULL context"""
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
            # Market context
            'call_wall': self.call_wall,
            'put_wall': self.put_wall,
            'gex_regime': self.gex_regime,
            'vix_at_entry': self.vix_at_entry,
            # Kronos context
            'flip_point': self.flip_point,
            'net_gex': self.net_gex,
            # ML/Oracle context (FULL for audit)
            'oracle_confidence': self.oracle_confidence,
            'ml_direction': self.ml_direction,
            'ml_confidence': self.ml_confidence,
            'ml_model_name': self.ml_model_name,
            'ml_win_probability': self.ml_win_probability,
            'ml_top_features': self.ml_top_features,
            'wall_type': self.wall_type,
            'wall_distance_pct': self.wall_distance_pct,
            'trade_reasoning': self.trade_reasoning,
            # Order tracking
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
    capital: float = 100000.0  # Paper trading capital
    risk_per_trade_pct: float = 2.0
    max_daily_trades: int = 5
    max_open_positions: int = 3

    # Strategy params
    ticker: str = "SPY"
    spread_width: int = 2  # $2 spreads
    wall_filter_pct: float = 3.0  # Trade within 3% of GEX wall (was 0.5% - too restrictive)
    min_rr_ratio: float = 0.8  # Min risk:reward (realistic for 0DTE debit spreads)

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

    def validate(self) -> tuple[bool, str]:
        """
        Validate configuration values.

        Returns: (is_valid, error_message)
        """
        errors = []

        # Capital validation
        if self.capital <= 0:
            errors.append(f"capital must be > 0, got {self.capital}")

        # Risk validation
        if self.risk_per_trade_pct <= 0 or self.risk_per_trade_pct > 100:
            errors.append(f"risk_per_trade_pct must be 0-100, got {self.risk_per_trade_pct}")

        # Trade limits
        if self.max_daily_trades <= 0:
            errors.append(f"max_daily_trades must be > 0, got {self.max_daily_trades}")
        if self.max_open_positions <= 0:
            errors.append(f"max_open_positions must be > 0, got {self.max_open_positions}")

        # Spread width
        if self.spread_width <= 0:
            errors.append(f"spread_width must be > 0, got {self.spread_width}")

        # Exit rules
        if self.profit_target_pct <= 0 or self.profit_target_pct > 100:
            errors.append(f"profit_target_pct must be 0-100, got {self.profit_target_pct}")
        if self.stop_loss_pct <= 0 or self.stop_loss_pct > 100:
            errors.append(f"stop_loss_pct must be 0-100, got {self.stop_loss_pct}")

        # Time format validation
        def validate_time(time_str: str, field_name: str):
            try:
                parts = time_str.split(':')
                if len(parts) != 2:
                    return f"{field_name} must be HH:MM format, got {time_str}"
                hour, minute = int(parts[0]), int(parts[1])
                if not (0 <= hour <= 23 and 0 <= minute <= 59):
                    return f"{field_name} has invalid time values: {time_str}"
            except (ValueError, AttributeError):
                return f"{field_name} must be HH:MM format, got {time_str}"
            return None

        for field, value in [('entry_start', self.entry_start),
                             ('entry_end', self.entry_end),
                             ('force_exit', self.force_exit)]:
            if err := validate_time(value, field):
                errors.append(err)

        if errors:
            return False, "; ".join(errors)
        return True, ""


@dataclass
class TradeSignal:
    """
    A trading signal with all context needed for execution.

    Contains FULL context for audit trail.
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

    # Kronos GEX context
    flip_point: float = 0
    net_gex: float = 0

    # Target strikes
    long_strike: float = 0
    short_strike: float = 0
    expiration: str = ""

    # Pricing
    estimated_debit: float = 0
    max_profit: float = 0
    max_loss: float = 0
    rr_ratio: float = 0

    # Source
    source: str = "ML"  # "ML", "GEX_WALL", "GEX_ORACLE", or "COMBINED"
    reasoning: str = ""

    # ML model details (for audit)
    ml_model_name: str = ""
    ml_win_probability: float = 0
    ml_top_features: str = ""  # JSON string of top features

    # Oracle details (for audit)
    oracle_win_probability: float = 0
    oracle_advice: str = ""  # TRADE_FULL, TRADE_REDUCED, SKIP_TODAY
    oracle_direction: str = ""  # BULLISH, BEARISH, FLAT
    oracle_confidence: float = 0
    oracle_top_factors: str = ""  # JSON string of top factors

    # Wall proximity details
    wall_type: str = ""  # "PUT_WALL" or "CALL_WALL"
    wall_distance_pct: float = 0

    @property
    def is_valid(self) -> bool:
        """Check if signal passes basic validation"""
        return (
            self.confidence > 0.45 and  # Lowered to match signals.py threshold
            self.rr_ratio >= 0.8 and  # Realistic for 0DTE debit spreads
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
