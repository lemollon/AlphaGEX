"""
Trading Models
==============

Shared data models for FLAME (2DTE) and SPARK (1DTE) Iron Condor bots.
Part of the IronSight Databricks trading system.
Ported from AlphaGEX FAITH/GRACE bots.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any
from zoneinfo import ZoneInfo

CENTRAL_TZ = ZoneInfo("America/Chicago")
EASTERN_TZ = ZoneInfo("America/New_York")


class TradingMode(Enum):
    PAPER = "paper"


class PositionStatus(Enum):
    OPEN = "open"
    CLOSED = "closed"
    EXPIRED = "expired"


@dataclass
class BotConfig:
    """
    Unified bot configuration for both FAITH and GRACE.

    The only difference between the two bots is min_dte and dte_mode.
    """
    bot_name: str = "FLAME"
    mode: TradingMode = TradingMode.PAPER
    ticker: str = "SPY"

    # DTE
    min_dte: int = 2
    dte_mode: str = "2DTE"

    # Capital
    starting_capital: float = 5000.0
    risk_per_trade_pct: float = 0.15

    # Strike selection
    sd_multiplier: float = 1.2
    spread_width: float = 5.0
    min_credit: float = 0.05

    # Trade frequency
    max_trades_per_day: int = 1

    # Exit parameters
    profit_target_pct: float = 30.0
    stop_loss_pct: float = 100.0
    eod_cutoff_et: str = "15:45"

    # Trading window (Central Time)
    entry_start: str = "08:30"
    entry_end: str = "14:00"

    # VIX filter
    vix_skip: float = 32.0

    # PDT
    pdt_max_day_trades: int = 3
    pdt_rolling_window_days: int = 5

    # Position sizing
    max_contracts: int = 10
    buying_power_usage_pct: float = 0.85

    # ML advisor minimum win probability
    min_win_probability: float = 0.42

    def validate(self) -> tuple:
        if self.starting_capital <= 0:
            return False, "Starting capital must be positive"
        if self.spread_width <= 0:
            return False, "Spread width must be positive"
        if self.profit_target_pct <= 0 or self.profit_target_pct >= 100:
            return False, "Profit target must be between 0 and 100"
        if self.stop_loss_pct <= 0:
            return False, "Stop loss must be positive"
        if self.max_trades_per_day < 1:
            return False, "Max trades per day must be at least 1"
        if self.min_dte < 1:
            return False, "Min DTE must be at least 1"
        return True, "OK"


def flame_config() -> BotConfig:
    """Default FLAME configuration (2DTE)."""
    return BotConfig(bot_name="FLAME", min_dte=2, dte_mode="2DTE")


def spark_config() -> BotConfig:
    """Default SPARK configuration (1DTE)."""
    return BotConfig(bot_name="SPARK", min_dte=1, dte_mode="1DTE")


@dataclass
class IronCondorPosition:
    """Represents a paper Iron Condor position."""
    position_id: str
    ticker: str
    expiration: str

    put_short_strike: float
    put_long_strike: float
    put_credit: float

    call_short_strike: float
    call_long_strike: float
    call_credit: float

    contracts: int
    spread_width: float
    total_credit: float
    max_loss: float
    max_profit: float

    underlying_at_entry: float
    vix_at_entry: float = 0.0
    expected_move: float = 0.0
    call_wall: float = 0.0
    put_wall: float = 0.0
    gex_regime: str = ""
    flip_point: float = 0.0
    net_gex: float = 0.0

    oracle_confidence: float = 0.0
    oracle_win_probability: float = 0.0
    oracle_advice: str = ""
    oracle_reasoning: str = ""
    oracle_top_factors: str = ""
    oracle_use_gex_walls: bool = False

    wings_adjusted: bool = False
    original_put_width: float = 0.0
    original_call_width: float = 0.0

    put_order_id: str = "PAPER"
    call_order_id: str = "PAPER"

    status: PositionStatus = PositionStatus.OPEN
    open_time: Optional[datetime] = None
    close_time: Optional[datetime] = None
    close_price: float = 0.0
    close_reason: str = ""
    realized_pnl: float = 0.0
    collateral_required: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        put_width = self.put_short_strike - self.put_long_strike
        call_width = self.call_long_strike - self.call_short_strike
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
            'gex_regime': self.gex_regime,
            'oracle_confidence': self.oracle_confidence,
            'oracle_win_probability': self.oracle_win_probability,
            'oracle_advice': self.oracle_advice,
            'wings_adjusted': self.wings_adjusted,
            'put_width': put_width,
            'call_width': call_width,
            'wings_symmetric': abs(put_width - call_width) < 0.01,
            'status': self.status.value,
            'open_time': self.open_time.isoformat() if self.open_time else None,
            'close_time': self.close_time.isoformat() if self.close_time else None,
            'close_price': self.close_price,
            'close_reason': self.close_reason,
            'realized_pnl': self.realized_pnl,
            'collateral_required': self.collateral_required,
        }


@dataclass
class IronCondorSignal:
    """Signal generated by the signal generator."""
    spot_price: float
    vix: float
    expected_move: float
    call_wall: float = 0.0
    put_wall: float = 0.0
    gex_regime: str = ""
    flip_point: float = 0.0
    net_gex: float = 0.0

    put_short: float = 0.0
    put_long: float = 0.0
    call_short: float = 0.0
    call_long: float = 0.0

    expiration: str = ""

    estimated_put_credit: float = 0.0
    estimated_call_credit: float = 0.0
    total_credit: float = 0.0
    max_loss: float = 0.0
    max_profit: float = 0.0

    confidence: float = 0.0
    oracle_win_probability: float = 0.0
    oracle_confidence: float = 0.0
    oracle_advice: str = ""
    oracle_top_factors: Any = None
    oracle_probabilities: Any = None
    oracle_use_gex_walls: bool = False
    oracle_suggested_sd: float = 0.0

    is_valid: bool = False
    reasoning: str = ""
    source: str = ""

    wings_adjusted: bool = False
    original_put_width: float = 0.0
    original_call_width: float = 0.0


@dataclass
class PaperAccount:
    """Paper trading account state."""
    starting_balance: float = 5000.0
    balance: float = 5000.0
    buying_power: float = 5000.0
    collateral_in_use: float = 0.0
    total_trades: int = 0
    cumulative_pnl: float = 0.0
    high_water_mark: float = 5000.0
    max_drawdown: float = 0.0
    is_active: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return_pct = (self.cumulative_pnl / self.starting_balance * 100) if self.starting_balance > 0 else 0
        return {
            'starting_balance': self.starting_balance,
            'balance': self.balance,
            'buying_power': self.buying_power,
            'collateral_in_use': self.collateral_in_use,
            'total_trades': self.total_trades,
            'cumulative_pnl': self.cumulative_pnl,
            'return_pct': round(return_pct, 2),
            'high_water_mark': self.high_water_mark,
            'max_drawdown': self.max_drawdown,
            'is_active': self.is_active,
        }


@dataclass
class DailySummary:
    """Daily trading summary."""
    date: str
    trades_executed: int = 0
    positions_closed: int = 0
    realized_pnl: float = 0.0
    open_positions: int = 0
