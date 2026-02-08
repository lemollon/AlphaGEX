"""
Pydantic Request/Response Models for FORTRESS and SOLOMON APIs

Provides strict input validation for all API endpoints to ensure:
- Type safety for all parameters
- Range validation for numeric values
- Required field enforcement
- Clear error messages for invalid input

Usage:
    from backend.api.models import FortressConfigUpdate, StrategyPresetRequest

    @router.post("/config")
    async def update_config(request: FortressConfigUpdate):
        # request is already validated
        ...
"""

from datetime import datetime, date
from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict
from enum import Enum


# =============================================================================
# Enums
# =============================================================================

class TradingModeEnum(str, Enum):
    """Trading mode options"""
    PAPER = "paper"
    LIVE = "live"
    BACKTEST = "backtest"


class StrategyPresetEnum(str, Enum):
    """FORTRESS strategy preset options"""
    BASELINE = "baseline"
    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"
    WIDE_STRIKES = "wide_strikes"


class SpreadTypeEnum(str, Enum):
    """SOLOMON spread type options"""
    BULL_CALL_SPREAD = "BULL_CALL_SPREAD"
    BEAR_CALL_SPREAD = "BEAR_CALL_SPREAD"


class ScanOutcomeEnum(str, Enum):
    """Scan outcome types"""
    TRADE = "trade"
    SKIP = "skip"
    ERROR = "error"
    BEFORE_WINDOW = "before_window"
    AFTER_WINDOW = "after_window"


# =============================================================================
# FORTRESS Request Models
# =============================================================================

class FortressConfigUpdate(BaseModel):
    """Request model for updating FORTRESS configuration"""

    risk_per_trade_pct: Optional[float] = Field(
        None,
        ge=1.0,
        le=15.0,
        description="Risk per trade as percentage of capital (1-15%)"
    )

    sd_multiplier: Optional[float] = Field(
        None,
        ge=0.3,
        le=1.5,
        description="Standard deviation multiplier for strike selection (0.3-1.5)"
    )

    spread_width: Optional[float] = Field(
        None,
        ge=5.0,
        le=50.0,
        description="Spread width in dollars (5-50)"
    )

    min_credit_per_spread: Optional[float] = Field(
        None,
        ge=0.10,
        le=10.0,
        description="Minimum credit per spread to accept ($0.10-$10)"
    )

    max_contracts: Optional[int] = Field(
        None,
        ge=1,
        le=1000,
        description="Maximum contracts per trade (1-1000)"
    )

    use_stop_loss: Optional[bool] = Field(
        None,
        description="Enable per-position stop loss"
    )

    stop_loss_premium_multiple: Optional[float] = Field(
        None,
        ge=1.0,
        le=5.0,
        description="Stop loss at X times premium collected (1-5x)"
    )

    profit_target_pct: Optional[float] = Field(
        None,
        ge=10.0,
        le=90.0,
        description="Profit target as percentage of max profit (10-90%)"
    )

    model_config = ConfigDict(extra="forbid")  # Reject unknown fields


class StrategyPresetRequest(BaseModel):
    """Request model for setting strategy preset"""

    preset: StrategyPresetEnum = Field(
        ...,
        description="Strategy preset to apply"
    )

    model_config = ConfigDict(extra="forbid")


class ARESSkipDayRequest(BaseModel):
    """Request model for skip day (optional date)"""

    skip_date: date | None = Field(
        default=None,
        description="Date to skip (defaults to today if not specified)"
    )


# =============================================================================
# SOLOMON Request Models
# =============================================================================

class SolomonConfigUpdate(BaseModel):
    """Request model for updating SOLOMON configuration"""

    setting_name: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Configuration setting name"
    )

    value: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="New value for the setting"
    )

    @field_validator('setting_name')
    @classmethod
    def validate_setting_name(cls, v: str) -> str:
        allowed_settings = [
            'max_daily_trades',
            'risk_per_trade_pct',
            'spread_width',
            'hard_stop_pct',
            'profit_threshold_pct',
            'trail_keep_pct',
            'atr_multiplier',
            'min_gex_score',
            'enabled'
        ]
        if v.lower() not in [s.lower() for s in allowed_settings]:
            raise ValueError(f"Unknown setting: {v}. Allowed: {allowed_settings}")
        return v.lower()


class SOLOMONTradeRequest(BaseModel):
    """Request model for manual SOLOMON trade"""

    direction: Literal["bullish", "bearish"] = Field(
        ...,
        description="Trade direction"
    )

    contracts: Optional[int] = Field(
        1,
        ge=1,
        le=100,
        description="Number of contracts (1-100)"
    )

    spread_width: Optional[float] = Field(
        None,
        ge=1.0,
        le=20.0,
        description="Spread width in dollars"
    )


# =============================================================================
# Shared Request Models
# =============================================================================

class DateRangeRequest(BaseModel):
    """Request model for date range queries"""

    start_date: date | None = Field(
        default=None,
        description="Start date for range"
    )

    end_date: date | None = Field(
        default=None,
        description="End date for range"
    )

    @model_validator(mode='after')
    def validate_date_range(self):
        if self.start_date and self.end_date:
            if self.start_date > self.end_date:
                raise ValueError("start_date must be before end_date")
        return self


class PaginationParams(BaseModel):
    """Pagination parameters"""

    page: int = Field(
        1,
        ge=1,
        description="Page number (1-indexed)"
    )

    per_page: int = Field(
        20,
        ge=1,
        le=100,
        description="Items per page (1-100)"
    )


class SymbolRequest(BaseModel):
    """Request model for symbol-based queries"""

    symbol: str = Field(
        ...,
        min_length=1,
        max_length=10,
        pattern=r'^[A-Z]{1,5}$',
        description="Stock symbol (1-5 uppercase letters)"
    )

    @field_validator('symbol')
    @classmethod
    def validate_symbol(cls, v: str) -> str:
        # Additional validation
        blocked = ['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'DROP']
        if v.upper() in blocked:
            raise ValueError("Invalid symbol")
        return v.upper()


# =============================================================================
# Response Models
# =============================================================================

class APIResponse(BaseModel):
    """Standard API response wrapper"""

    success: bool = Field(..., description="Whether the request succeeded")
    message: Optional[str] = Field(None, description="Human-readable message")
    data: Optional[Any] = Field(None, description="Response data")
    error: Optional[str] = Field(None, description="Error message if failed")
    timestamp: datetime = Field(
        default_factory=datetime.now,
        description="Response timestamp"
    )


class PositionResponse(BaseModel):
    """Response model for position data"""

    position_id: str
    bot: str = Field(..., description="Bot name (FORTRESS or SOLOMON)")
    status: str = Field(..., description="Position status")
    open_date: str
    expiration: str
    contracts: int
    entry_price: float
    current_value: Optional[float] = None
    unrealized_pnl: Optional[float] = None
    realized_pnl: Optional[float] = None

    # FORTRESS-specific
    put_short_strike: Optional[float] = None
    put_long_strike: Optional[float] = None
    call_short_strike: Optional[float] = None
    call_long_strike: Optional[float] = None
    total_credit: Optional[float] = None

    # SOLOMON-specific
    spread_type: Optional[str] = None
    long_strike: Optional[float] = None
    short_strike: Optional[float] = None
    entry_debit: Optional[float] = None


class PerformanceMetrics(BaseModel):
    """Response model for performance metrics"""

    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = Field(0.0, ge=0, le=100)
    total_pnl: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    profit_factor: Optional[float] = None
    sharpe_ratio: Optional[float] = None
    max_drawdown: Optional[float] = None
    max_drawdown_pct: Optional[float] = None


class BotStatusResponse(BaseModel):
    """Response model for bot status"""

    bot_name: str
    status: str = Field(..., description="Current bot status")
    mode: str = Field(..., description="Trading mode (paper/live)")
    is_running: bool = False
    last_scan: Optional[datetime] = None
    last_trade: Optional[datetime] = None
    open_positions: int = 0
    daily_trades: int = 0
    daily_pnl: float = 0.0
    capital: float = 0.0

    # Circuit breaker info
    circuit_breaker_active: bool = False
    consecutive_losses: int = 0


class ScanActivityResponse(BaseModel):
    """Response model for scan activity"""

    scan_id: int
    bot_name: str
    timestamp: datetime
    outcome: str
    decision_summary: str
    action_taken: Optional[str] = None
    full_reasoning: Optional[str] = None
    checks: Optional[List[Dict[str, Any]]] = None


class CircuitBreakerStatus(BaseModel):
    """Response model for circuit breaker status"""

    state: str
    can_trade: bool
    trip_reason: Optional[str] = None
    trip_time: Optional[datetime] = None
    daily_pnl: float = 0.0
    daily_pnl_pct: float = 0.0
    daily_trades: int = 0
    consecutive_losses: int = 0
    max_consecutive_losses: int = 3
    consecutive_loss_cooldown_until: Optional[datetime] = None
    limits: Dict[str, Any] = {}


# =============================================================================
# Validation Helpers
# =============================================================================

def validate_strikes(
    put_long: float,
    put_short: float,
    call_short: float,
    call_long: float
) -> bool:
    """Validate Iron Condor strike ordering"""
    return put_long < put_short < call_short < call_long


def validate_spread_strikes(
    long_strike: float,
    short_strike: float,
    is_bullish: bool
) -> bool:
    """Validate vertical spread strike ordering"""
    if is_bullish:
        return long_strike < short_strike  # Bull call: buy lower, sell higher
    else:
        return short_strike < long_strike  # Bear call: sell lower, buy higher


def validate_expiration(expiration: str) -> bool:
    """Validate expiration date format and value"""
    try:
        exp_date = datetime.strptime(expiration, '%Y-%m-%d').date()
        today = date.today()
        return exp_date >= today
    except ValueError:
        return False
