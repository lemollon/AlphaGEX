"""
ICARUS - Data Models
=====================

All data classes for ICARUS aggressive directional spread trading.

ICARUS uses MORE AGGRESSIVE Apache GEX backtest parameters than ATHENA:
- 2% wall filter (vs ATHENA's 1%) - more room to trade
- 48% min win probability (vs 55%) - lower threshold
- 3% risk per trade (vs 2%) - larger positions
- 8 max daily trades (vs 5) - more opportunities
- VIX range 12-30 (vs 15-25) - wider volatility range
- GEX ratio 1.3/0.77 (vs 1.5/0.67) - weaker asymmetry allowed

Safety filters ARE ENABLED (unlike old ICARUS with everything disabled).
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any, Tuple
from zoneinfo import ZoneInfo


# Timezone constant
CENTRAL_TZ = ZoneInfo("America/Chicago")


class SpreadType(Enum):
    """Types of directional spreads"""
    BULL_CALL = "BULL_CALL"
    BEAR_PUT = "BEAR_PUT"


class PositionStatus(Enum):
    """Position lifecycle states"""
    OPEN = "open"
    CLOSED = "closed"
    EXPIRED = "expired"
    PARTIAL_CLOSE = "partial_close"


class TradingMode(Enum):
    """Trading modes"""
    PAPER = "paper"
    LIVE = "live"


@dataclass
class ICARUSConfig:
    """
    ICARUS configuration with AGGRESSIVE Apache GEX backtest parameters.

    Key differences from ATHENA (Apache optimal):
    - wall_filter_pct: 2% (vs 1%) - more room to trade
    - min_win_probability: 48% (vs 55%) - lower threshold but still positive expectancy
    - min_confidence: 48% (vs 55%) - lower threshold
    - min_rr_ratio: 1.2 (vs 1.5) - accept slightly lower R:R
    - VIX range: 12-30 (vs 15-25) - wider volatility range
    - GEX ratio: 1.3/0.77 (vs 1.5/0.67) - weaker asymmetry allowed
    - risk_per_trade_pct: 3% (vs 2%) - larger positions
    - max_daily_trades: 8 (vs 5) - more trades
    - max_open_positions: 4 (vs 3) - more exposure
    - spread_width: $3 (vs $2) - wider spreads
    - profit_target_pct: 40% (vs 50%) - take profits earlier
    - stop_loss_pct: 60% (vs 50%) - wider stops
    """
    # Mode
    mode: TradingMode = TradingMode.PAPER
    ticker: str = "SPY"

    # Capital management - AGGRESSIVE
    capital: float = 100_000.0
    risk_per_trade_pct: float = 3.0  # 3% vs ATHENA's 2%

    # Trade limits - AGGRESSIVE
    max_daily_trades: int = 8  # 8 vs ATHENA's 5
    max_open_positions: int = 4  # 4 vs ATHENA's 3

    # Spread parameters - AGGRESSIVE
    spread_width: int = 3  # $3 vs ATHENA's $2

    # Signal thresholds - AGGRESSIVE but with EDGE (Apache-based)
    wall_filter_pct: float = 1.0  # 1% - Apache backtest optimal (same as ATHENA)
    min_rr_ratio: float = 1.2  # 1.2 vs ATHENA's 1.5 - still need edge
    min_win_probability: float = 0.48  # 48% vs ATHENA's 50% - lower but near breakeven
    min_confidence: float = 0.48  # 48% vs ATHENA's 50%

    # VIX filter (AGGRESSIVE - wider range than ATHENA)
    min_vix: float = 12.0  # 12 vs ATHENA's 15 - allow lower vol
    max_vix: float = 30.0  # 30 vs ATHENA's 25 - allow higher vol

    # GEX ratio asymmetry (AGGRESSIVE - weaker asymmetry allowed)
    min_gex_ratio_bearish: float = 1.3  # 1.3 vs ATHENA's 1.5 for bearish
    max_gex_ratio_bullish: float = 0.77  # 0.77 vs ATHENA's 0.67 for bullish

    # Exit thresholds - AGGRESSIVE
    profit_target_pct: float = 40.0  # 40% vs ATHENA's 50% - take profits earlier
    stop_loss_pct: float = 60.0  # 60% vs ATHENA's 50% - slightly wider stops

    # Trading hours (Central Time)
    # Market closes at 3:00 PM CT (4:00 PM ET)
    entry_start: str = "08:35"
    entry_end: str = "14:30"
    force_exit: str = "14:50"  # Force close 10 min before market close

    def validate(self) -> Tuple[bool, str]:
        """Validate configuration"""
        if self.risk_per_trade_pct <= 0 or self.risk_per_trade_pct > 20:
            return False, "risk_per_trade_pct must be between 0 and 20"
        if self.max_daily_trades <= 0:
            return False, "max_daily_trades must be positive"
        if self.max_open_positions <= 0:
            return False, "max_open_positions must be positive"
        if self.spread_width <= 0:
            return False, "spread_width must be positive"
        if self.wall_filter_pct <= 0 or self.wall_filter_pct > 50:
            return False, "wall_filter_pct must be between 0 and 50"
        if self.min_rr_ratio < 0:
            return False, "min_rr_ratio must be non-negative"
        if self.min_win_probability < 0 or self.min_win_probability > 1:
            return False, "min_win_probability must be between 0 and 1"
        if self.profit_target_pct <= 0 or self.profit_target_pct > 100:
            return False, "profit_target_pct must be between 0 and 100"
        if self.stop_loss_pct <= 0 or self.stop_loss_pct > 100:
            return False, "stop_loss_pct must be between 0 and 100"
        return True, "OK"


@dataclass
class SpreadPosition:
    """
    A directional spread position with FULL context for audit trail.

    Stores all market conditions, ML predictions, and Oracle advice
    at time of entry for post-trade analysis.
    """
    # Identity
    position_id: str
    spread_type: SpreadType
    ticker: str

    # Structure
    long_strike: float
    short_strike: float
    expiration: str

    # Execution
    entry_debit: float
    contracts: int
    max_profit: float
    max_loss: float

    # Market context at entry
    underlying_at_entry: float
    call_wall: float = 0
    put_wall: float = 0
    gex_regime: str = ""
    vix_at_entry: float = 0

    # Kronos GEX context (for audit)
    flip_point: float = 0
    net_gex: float = 0

    # ML context (FULL audit trail)
    oracle_confidence: float = 0
    oracle_advice: str = ""  # Oracle's trade decision for audit trail
    ml_direction: str = ""
    ml_confidence: float = 0
    ml_model_name: str = ""
    ml_win_probability: float = 0
    ml_top_features: str = ""

    # Wall proximity context
    wall_type: str = ""
    wall_distance_pct: float = 0

    # Trade reasoning
    trade_reasoning: str = ""

    # Order tracking
    order_id: str = ""
    status: PositionStatus = PositionStatus.OPEN
    open_time: datetime = field(default_factory=lambda: datetime.now(CENTRAL_TZ))

    # Close details
    close_time: Optional[datetime] = None
    close_price: float = 0
    close_reason: str = ""
    realized_pnl: float = 0

    # DB persistence flag
    db_persisted: bool = True

    @property
    def spread_width(self) -> float:
        """Calculate spread width"""
        return abs(self.short_strike - self.long_strike)

    @property
    def is_bullish(self) -> bool:
        """Check if this is a bullish spread"""
        return self.spread_type == SpreadType.BULL_CALL

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        data = asdict(self)
        data['spread_type'] = self.spread_type.value
        data['status'] = self.status.value
        if self.open_time:
            data['open_time'] = self.open_time.isoformat() if hasattr(self.open_time, 'isoformat') else self.open_time
        if self.close_time:
            data['close_time'] = self.close_time.isoformat() if hasattr(self.close_time, 'isoformat') else self.close_time
        return data


@dataclass
class TradeSignal:
    """
    A trading signal with ALL context for audit trail.

    Contains market data, ML predictions, Oracle advice, and trade reasoning.
    """
    # Direction
    direction: str  # BULLISH or BEARISH
    spread_type: SpreadType
    confidence: float

    # Market data
    spot_price: float
    call_wall: float
    put_wall: float
    gex_regime: str
    vix: float

    # Kronos GEX context
    flip_point: float = 0
    net_gex: float = 0

    # Strikes
    long_strike: float = 0
    short_strike: float = 0
    expiration: str = ""

    # Pricing estimates
    estimated_debit: float = 0
    max_profit: float = 0
    max_loss: float = 0
    rr_ratio: float = 0

    # Source and reasoning
    source: str = ""
    reasoning: str = ""

    # ML context (for audit)
    ml_model_name: str = ""
    ml_win_probability: float = 0
    ml_top_features: str = ""

    # Oracle context (for audit)
    oracle_win_probability: float = 0
    oracle_advice: str = ""
    oracle_direction: str = ""
    oracle_confidence: float = 0
    oracle_top_factors: str = ""

    # Wall context
    wall_type: str = ""
    wall_distance_pct: float = 0

    @property
    def is_valid(self) -> bool:
        """Check if signal passes validation (aggressive Apache thresholds)"""
        # ORACLE IS GOD: When Oracle says TRADE, nothing blocks it
        oracle_approved = self.oracle_advice in ('TRADE_FULL', 'TRADE_REDUCED', 'ENTER')

        if oracle_approved:
            return (
                self.direction in ("BULLISH", "BEARISH") and
                self.spot_price > 0 and
                self.long_strike > 0 and
                self.short_strike > 0 and
                self.max_profit > 0
            )

        return (
            self.direction in ("BULLISH", "BEARISH") and
            self.spot_price > 0 and
            self.long_strike > 0 and
            self.short_strike > 0 and
            self.confidence >= 0.48 and
            self.rr_ratio >= 1.2 and
            self.max_profit > 0
        )


@dataclass
class DailySummary:
    """Daily trading summary"""
    date: str
    trades_executed: int = 0
    positions_closed: int = 0
    realized_pnl: float = 0
    open_positions: int = 0
