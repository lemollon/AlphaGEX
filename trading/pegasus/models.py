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
from typing import Optional, Dict, Any
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

    # Oracle context
    oracle_confidence: float = 0
    oracle_reasoning: str = ""

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
            'status': self.status.value,
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
    risk_per_trade_pct: float = 10.0
    max_contracts: int = 100
    min_credit: float = 1.50  # Higher minimum for SPX

    # Exit rules
    use_stop_loss: bool = False
    stop_loss_multiple: float = 2.0
    profit_target_pct: float = 50.0

    # Trading window
    entry_start: str = "08:30"
    entry_end: str = "15:30"
    force_exit: str = "15:55"

    # Mode
    mode: TradingMode = TradingMode.PAPER

    def apply_preset(self, preset: StrategyPreset) -> None:
        self.preset = preset
        config = STRATEGY_PRESETS.get(preset, {})
        self.vix_skip = config.get('vix_skip')
        self.sd_multiplier = config.get('sd_multiplier', 1.0)


@dataclass
class IronCondorSignal:
    """Signal for SPX Iron Condor"""
    spot_price: float
    vix: float
    expected_move: float
    call_wall: float
    put_wall: float
    gex_regime: str

    put_short: float
    put_long: float
    call_short: float
    call_long: float
    expiration: str

    estimated_put_credit: float
    estimated_call_credit: float
    total_credit: float
    max_loss: float
    max_profit: float

    confidence: float
    reasoning: str
    source: str = "GEX"

    @property
    def is_valid(self) -> bool:
        return (
            self.confidence >= 0.5 and
            self.total_credit >= 1.50 and  # Higher threshold for SPX
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
