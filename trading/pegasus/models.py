"""
PEGASUS - Data Models
======================

Data models for PEGASUS SPX Iron Condor trading bot.

PEGASUS trades SPX Iron Condors:
- Larger spread widths ($10)
- $5 strike increments
- Cash-settled (European style)
- SPXW symbols for weeklies
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any, List
from zoneinfo import ZoneInfo

CENTRAL_TZ = ZoneInfo("America/Chicago")


class TradingMode(Enum):
    """Trading execution mode"""
    PAPER = "paper"
    LIVE = "live"


class PositionStatus(Enum):
    """Position lifecycle status"""
    OPEN = "open"
    CLOSED = "closed"
    EXPIRED = "expired"
    PARTIAL_CLOSE = "partial_close"  # One leg closed, other failed - needs manual intervention


class StrategyPreset(Enum):
    """Strategy presets for SPX trading"""
    BASELINE = "baseline"
    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"
    WIDE_STRIKES = "wide_strikes"


STRATEGY_PRESETS = {
    StrategyPreset.BASELINE: {
        "name": "Baseline",
        "vix_skip": None,
        "sd_multiplier": 1.0,
    },
    StrategyPreset.CONSERVATIVE: {
        "name": "Conservative",
        "vix_skip": 35.0,
        "sd_multiplier": 1.0,
    },
    StrategyPreset.MODERATE: {
        "name": "Moderate",
        "vix_skip": 32.0,
        "sd_multiplier": 1.0,
    },
    StrategyPreset.AGGRESSIVE: {
        "name": "Aggressive",
        "vix_skip": 30.0,
        "sd_multiplier": 1.0,
    },
    StrategyPreset.WIDE_STRIKES: {
        "name": "Wide Strikes",
        "vix_skip": 32.0,
        "sd_multiplier": 1.2,
    },
}


@dataclass
class IronCondorPosition:
    """
    SPX Iron Condor position.

    Key differences from SPY:
    - $10 spread width (vs $2)
    - $5 strike increments
    - Cash-settled at expiration
    """
    # Identity
    position_id: str
    ticker: str = "SPX"
    expiration: str = ""

    # Put spread legs
    put_short_strike: float = 0
    put_long_strike: float = 0
    put_credit: float = 0

    # Call spread legs
    call_short_strike: float = 0
    call_long_strike: float = 0
    call_credit: float = 0

    # Position sizing
    contracts: int = 1
    spread_width: float = 10.0  # SPX uses $10 spreads

    # Calculated values
    total_credit: float = 0
    max_loss: float = 0
    max_profit: float = 0

    # Market context
    underlying_at_entry: float = 0
    vix_at_entry: float = 0
    expected_move: float = 0
    call_wall: float = 0
    put_wall: float = 0
    gex_regime: str = ""

    # Kronos context (flip point, net GEX)
    flip_point: float = 0
    net_gex: float = 0

    # Oracle context (FULL audit trail)
    oracle_confidence: float = 0
    oracle_win_probability: float = 0
    oracle_advice: str = ""
    oracle_reasoning: str = ""
    oracle_top_factors: str = ""  # JSON string of top factors
    oracle_use_gex_walls: bool = False

    # Order tracking
    put_order_id: str = ""
    call_order_id: str = ""

    # Status
    status: PositionStatus = PositionStatus.OPEN
    open_time: datetime = field(default_factory=lambda: datetime.now(CENTRAL_TZ))
    close_time: Optional[datetime] = None
    close_price: float = 0
    close_reason: str = ""
    realized_pnl: float = 0

    @property
    def is_open(self) -> bool:
        return self.status == PositionStatus.OPEN

    def to_dict(self) -> Dict[str, Any]:
        return {
            'position_id': self.position_id,
            'ticker': self.ticker,
            'expiration': self.expiration,
            'put_short_strike': self.put_short_strike,
            'put_long_strike': self.put_long_strike,
            'put_credit': self.put_credit,
            'call_short_strike': self.call_short_strike,
            'call_long_strike': self.call_long_strike,
            'call_credit': self.call_credit,
            'contracts': self.contracts,
            'spread_width': self.spread_width,
            'total_credit': self.total_credit,
            'max_loss': self.max_loss,
            'max_profit': self.max_profit,
            'underlying_at_entry': self.underlying_at_entry,
            'vix_at_entry': self.vix_at_entry,
            'expected_move': self.expected_move,
            'call_wall': self.call_wall,
            'put_wall': self.put_wall,
            'gex_regime': self.gex_regime,
            # Kronos context
            'flip_point': self.flip_point,
            'net_gex': self.net_gex,
            # Oracle context (FULL audit trail)
            'oracle_confidence': self.oracle_confidence,
            'oracle_win_probability': self.oracle_win_probability,
            'oracle_advice': self.oracle_advice,
            'oracle_reasoning': self.oracle_reasoning,
            'oracle_top_factors': self.oracle_top_factors,
            'oracle_use_gex_walls': self.oracle_use_gex_walls,
            # Order tracking
            'put_order_id': self.put_order_id,
            'call_order_id': self.call_order_id,
            'status': self.status.value,
            'open_time': self.open_time.isoformat() if self.open_time and hasattr(self.open_time, 'isoformat') else self.open_time,
            'close_time': self.close_time.isoformat() if self.close_time and hasattr(self.close_time, 'isoformat') else self.close_time,
            'close_price': self.close_price,
            'close_reason': self.close_reason,
            'realized_pnl': self.realized_pnl,
        }


@dataclass
class PEGASUSConfig:
    """
    PEGASUS configuration for SPX trading.
    """
    # Strategy
    preset: StrategyPreset = StrategyPreset.MODERATE
    ticker: str = "SPX"

    # VIX filtering
    vix_skip: Optional[float] = 32.0

    # Strike selection
    sd_multiplier: float = 1.0
    spread_width: float = 10.0   # $10 spreads for SPX
    strike_increment: float = 5.0  # SPX trades in $5 increments

    # Risk limits
    capital: float = 200000.0  # Paper trading capital for SPX
    risk_per_trade_pct: float = 10.0
    max_contracts: int = 25  # Reduced from 100 - conservative SPX sizing
    min_credit: float = 0.75  # Lowered from $1.50 to capture more opportunities
    max_open_positions: int = 3  # Reduced from 5 - limit concurrent exposure
    max_trades_per_day: int = 2  # Prevent rapid position accumulation
    min_ic_suitability: float = 0.3  # Minimum IC suitability from Oracle (0.0-1.0)

    # Oracle thresholds
    min_win_probability: float = 0.42  # Minimum Oracle win probability to trade (42%)

    # Exit rules
    use_stop_loss: bool = False
    stop_loss_multiple: float = 2.0
    profit_target_pct: float = 50.0

    # Trading window (CT - Central Time)
    # Market closes at 3:00 PM CT (4:00 PM ET)
    entry_start: str = "08:30"
    entry_end: str = "14:45"  # Stop new entries 15 min before close
    force_exit: str = "14:50"  # Force close 10 min before market close (3:00 PM CT)

    # Mode
    mode: TradingMode = TradingMode.PAPER

    def apply_preset(self, preset: StrategyPreset) -> None:
        self.preset = preset
        config = STRATEGY_PRESETS.get(preset, {})
        self.vix_skip = config.get('vix_skip')
        self.sd_multiplier = config.get('sd_multiplier', 1.0)

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

        # Contract limits
        if self.max_contracts <= 0:
            errors.append(f"max_contracts must be > 0, got {self.max_contracts}")

        # Spread width
        if self.spread_width <= 0:
            errors.append(f"spread_width must be > 0, got {self.spread_width}")

        # Position limits
        if self.max_open_positions <= 0:
            errors.append(f"max_open_positions must be > 0, got {self.max_open_positions}")

        # Daily trade limits
        if hasattr(self, 'max_trades_per_day') and self.max_trades_per_day <= 0:
            errors.append(f"max_trades_per_day must be > 0, got {self.max_trades_per_day}")

        # Oracle suitability
        if self.min_ic_suitability < 0 or self.min_ic_suitability > 1:
            errors.append(f"min_ic_suitability must be 0-1, got {self.min_ic_suitability}")

        # Profit target
        if self.profit_target_pct <= 0 or self.profit_target_pct > 100:
            errors.append(f"profit_target_pct must be 0-100, got {self.profit_target_pct}")

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
class IronCondorSignal:
    """
    Signal for SPX Iron Condor.

    Contains full context for trade audit trail.
    """
    # Market context
    spot_price: float
    vix: float
    expected_move: float
    call_wall: float
    put_wall: float
    gex_regime: str

    # Kronos GEX context
    flip_point: float = 0
    net_gex: float = 0

    # Strike recommendations
    put_short: float = 0
    put_long: float = 0
    call_short: float = 0
    call_long: float = 0
    expiration: str = ""

    # Estimated pricing
    estimated_put_credit: float = 0
    estimated_call_credit: float = 0
    total_credit: float = 0
    max_loss: float = 0
    max_profit: float = 0

    # Signal quality
    confidence: float = 0
    reasoning: str = ""
    source: str = "GEX"  # GEX, ORACLE, or SD

    # Oracle prediction details (CRITICAL for audit)
    oracle_win_probability: float = 0
    oracle_advice: str = ""  # ENTER, HOLD, EXIT
    oracle_confidence: float = 0  # Oracle's confidence in its prediction
    oracle_top_factors: List[Dict[str, Any]] = field(default_factory=list)
    oracle_suggested_sd: float = 1.0
    oracle_use_gex_walls: bool = False
    oracle_probabilities: Dict[str, float] = field(default_factory=dict)

    @property
    def is_valid(self) -> bool:
        # ORACLE IS GOD: When Oracle says TRADE, nothing blocks it
        oracle_approved = self.oracle_advice in ('TRADE_FULL', 'TRADE_REDUCED', 'ENTER')

        if oracle_approved:
            # Only check basic strike validity when Oracle approves
            return (
                self.put_short > self.put_long > 0 and
                self.call_short < self.call_long and
                self.call_short > self.put_short
            )

        return (
            self.confidence >= 0.5 and
            self.total_credit >= 0.75 and  # Match PEGASUSConfig.min_credit
            self.put_short > self.put_long > 0 and
            self.call_short < self.call_long and
            self.call_short > self.put_short
        )


@dataclass
class DailySummary:
    """Daily trading summary"""
    date: str
    trades_executed: int = 0
    positions_closed: int = 0
    realized_pnl: float = 0.0
    open_positions: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            'date': self.date,
            'trades_executed': self.trades_executed,
            'positions_closed': self.positions_closed,
            'realized_pnl': self.realized_pnl,
            'open_positions': self.open_positions,
        }
