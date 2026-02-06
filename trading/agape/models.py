"""
AGAPE Models - Data structures for the ETH Micro Futures bot.

Mirrors ARES V2 models pattern with crypto-specific fields.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any


class TradingMode(Enum):
    PAPER = "paper"
    LIVE = "live"


class PositionSide(Enum):
    LONG = "long"
    SHORT = "short"


class PositionStatus(Enum):
    OPEN = "open"
    CLOSED = "closed"
    EXPIRED = "expired"
    STOPPED = "stopped"


class SignalAction(Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    RANGE_BOUND = "RANGE_BOUND"   # For future premium selling
    WAIT = "WAIT"
    CLOSE = "CLOSE"


@dataclass
class AgapeConfig:
    """Configuration for AGAPE bot - loaded from autonomous_config table.

    AGGRESSIVE MODE (matching HERACLES/Valor aggressiveness):
    - High position limits for frequent trading
    - Short cooldown to avoid missing opportunities
    - Low confidence threshold to trade on any signal
    - Oracle advisory only (not blocking)
    - No-loss trailing to let winners run
    - SAR to reverse losing positions
    """

    # Identity
    bot_name: str = "AGAPE"
    ticker: str = "ETH"
    instrument: str = "/MET"          # CME Micro Ether Futures

    # Trading mode
    mode: TradingMode = TradingMode.PAPER

    # Risk management
    starting_capital: float = 5000.0   # Small account for micro futures
    risk_per_trade_pct: float = 5.0    # 5% risk per trade ($250 on $5K)
    max_contracts: int = 10
    max_open_positions: int = 20       # Aggressive: allow many concurrent positions

    # Position sizing
    contract_size: float = 0.1         # /MET = 0.1 ETH
    tick_size: float = 0.50            # Minimum price increment
    tick_value: float = 0.05           # Dollar value per tick

    # Entry/exit rules
    profit_target_pct: float = 50.0    # Close at 50% of expected move captured
    stop_loss_pct: float = 100.0       # Stop at 100% of risk (1:1 R:R)
    trailing_stop_pct: float = 0.0     # 0 = disabled (use no-loss trailing instead)
    max_hold_hours: int = 24           # Max position duration

    # No-Loss Trailing Strategy (ported from HERACLES)
    # Let winners run, only trail after profitable
    use_no_loss_trailing: bool = True
    no_loss_activation_pct: float = 1.0   # % profit before trailing activates
    no_loss_trail_distance_pct: float = 0.75  # % behind best price (< activation_pct to lock in profit)
    no_loss_emergency_stop_pct: float = 5.0  # Emergency stop for catastrophic moves
    max_unrealized_loss_pct: float = 3.0     # Exit if down 3% (safety net)
    no_loss_profit_target_pct: float = 0.0   # 0 = disabled, let winners run

    # Stop-and-Reverse (SAR) Strategy (ported from HERACLES)
    # When a trade is clearly wrong, reverse direction to capture momentum
    use_sar: bool = True
    sar_trigger_pct: float = 1.5       # Trigger SAR when down this % from entry
    sar_mfe_threshold_pct: float = 0.3 # Only reverse if MFE < this % (never profitable)

    # Timing (crypto trades 23hrs/day Sun-Fri)
    entry_start: str = "18:00"         # 6 PM CT Sunday open
    entry_end: str = "15:30"           # 3:30 PM CT Friday
    force_exit: str = "15:45"          # Force close before CME close

    # Signal thresholds - AGGRESSIVE
    min_confidence: str = "LOW"        # Trade on any signal (was MEDIUM)
    min_funding_rate_signal: float = 0.001  # Lower threshold for directional signals
    min_ls_ratio_extreme: float = 1.1       # Lower extreme threshold
    min_liquidation_proximity_pct: float = 5.0  # Wider liquidation zone

    # Oracle integration - ADVISORY ONLY (not blocking)
    require_oracle_approval: bool = False   # Don't let Oracle block trades
    min_oracle_win_probability: float = 0.35  # Lower threshold when advisory

    # Cooldown - AGGRESSIVE
    cooldown_minutes: int = 5          # Short cooldown (was 30)

    # Loss streak protection (from HERACLES)
    max_consecutive_losses: int = 3    # Pause after 3 losses in a row
    loss_streak_pause_minutes: int = 5 # How long to pause (minutes)

    # Direction Tracker settings (from HERACLES)
    direction_cooldown_scans: int = 2      # Pause direction for 2 scans after loss
    direction_win_streak_caution: int = 100 # Effectively disabled
    direction_memory_size: int = 10         # Track last 10 trades per direction

    @classmethod
    def load_from_db(cls, db) -> "AgapeConfig":
        """Load config from database, falling back to defaults."""
        config = cls()
        try:
            db_config = db.load_config()
            if db_config:
                for key, value in db_config.items():
                    if hasattr(config, key):
                        attr_type = type(getattr(config, key))
                        if attr_type == float:
                            setattr(config, key, float(value))
                        elif attr_type == int:
                            setattr(config, key, int(value))
                        elif attr_type == bool:
                            setattr(config, key, str(value).lower() in ("true", "1", "yes"))
                        elif attr_type == str:
                            setattr(config, key, str(value))
                        elif attr_type == TradingMode:
                            setattr(config, key, TradingMode(value))
        except Exception:
            pass  # Use defaults
        return config


@dataclass
class AgapeSignal:
    """Trading signal generated by AGAPE signal engine.

    Equivalent to ARES's IronCondorSignal but for directional /MET trades.
    """
    # Market data at signal time
    spot_price: float
    timestamp: datetime

    # Crypto microstructure (replaces GEX data)
    funding_rate: float = 0.0
    funding_regime: str = "UNKNOWN"
    ls_ratio: float = 1.0
    ls_bias: str = "NEUTRAL"
    nearest_long_liq: Optional[float] = None
    nearest_short_liq: Optional[float] = None
    squeeze_risk: str = "LOW"
    leverage_regime: str = "UNKNOWN"
    max_pain: Optional[float] = None

    # Crypto GEX (from Deribit options)
    crypto_gex: float = 0.0
    crypto_gex_regime: str = "NEUTRAL"

    # Signal decision
    action: SignalAction = SignalAction.WAIT
    confidence: str = "LOW"
    reasoning: str = ""
    source: str = "agape"

    # Oracle context (audit trail)
    oracle_advice: str = "UNKNOWN"
    oracle_win_probability: float = 0.0
    oracle_confidence: float = 0.0
    oracle_top_factors: List[str] = field(default_factory=list)

    # Trade parameters (populated if action != WAIT)
    side: Optional[str] = None             # "long" or "short"
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    contracts: int = 0
    max_risk_usd: float = 0.0

    @property
    def is_valid(self) -> bool:
        """Signal is tradeable."""
        return (
            self.action in (SignalAction.LONG, SignalAction.SHORT)
            and self.confidence in ("HIGH", "MEDIUM")
            and self.contracts > 0
            and self.entry_price is not None
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "spot_price": self.spot_price,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "funding_rate": self.funding_rate,
            "funding_regime": self.funding_regime,
            "ls_ratio": self.ls_ratio,
            "ls_bias": self.ls_bias,
            "nearest_long_liq": self.nearest_long_liq,
            "nearest_short_liq": self.nearest_short_liq,
            "squeeze_risk": self.squeeze_risk,
            "leverage_regime": self.leverage_regime,
            "max_pain": self.max_pain,
            "crypto_gex": self.crypto_gex,
            "crypto_gex_regime": self.crypto_gex_regime,
            "action": self.action.value,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "oracle_advice": self.oracle_advice,
            "oracle_win_probability": self.oracle_win_probability,
            "oracle_confidence": self.oracle_confidence,
            "oracle_top_factors": self.oracle_top_factors,
            "side": self.side,
            "entry_price": self.entry_price,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "contracts": self.contracts,
            "max_risk_usd": self.max_risk_usd,
        }


@dataclass
class AgapePosition:
    """An open or closed AGAPE position.

    Equivalent to ARES's IronCondorPosition but for directional /MET trades.
    """
    position_id: str
    side: PositionSide
    contracts: int
    entry_price: float
    stop_loss: float
    take_profit: float
    max_risk_usd: float

    # Market context at entry
    underlying_at_entry: float
    funding_rate_at_entry: float
    funding_regime_at_entry: str
    ls_ratio_at_entry: float
    squeeze_risk_at_entry: str
    max_pain_at_entry: Optional[float]
    crypto_gex_at_entry: float
    crypto_gex_regime_at_entry: str

    # Oracle context (full audit)
    oracle_advice: str
    oracle_win_probability: float
    oracle_confidence: float
    oracle_top_factors: List[str]

    # Signal reasoning
    signal_action: str
    signal_confidence: str
    signal_reasoning: str

    # Status
    status: PositionStatus = PositionStatus.OPEN
    open_time: Optional[datetime] = None
    close_time: Optional[datetime] = None
    close_price: Optional[float] = None
    close_reason: Optional[str] = None
    realized_pnl: Optional[float] = None

    # Tracking
    unrealized_pnl: float = 0.0
    high_water_mark: float = 0.0      # For trailing stop
    last_update: Optional[datetime] = None

    def calculate_pnl(self, current_price: float) -> float:
        """Calculate P&L for current price.

        /MET: Each $1 move in ETH = $0.10 per contract.
        P&L = (current - entry) * contract_size * contracts * direction
        """
        direction = 1 if self.side == PositionSide.LONG else -1
        pnl_per_contract = (current_price - self.entry_price) * 0.1 * direction
        return round(pnl_per_contract * self.contracts, 2)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "position_id": self.position_id,
            "side": self.side.value,
            "contracts": self.contracts,
            "entry_price": self.entry_price,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "max_risk_usd": self.max_risk_usd,
            "underlying_at_entry": self.underlying_at_entry,
            "funding_rate_at_entry": self.funding_rate_at_entry,
            "funding_regime_at_entry": self.funding_regime_at_entry,
            "ls_ratio_at_entry": self.ls_ratio_at_entry,
            "squeeze_risk_at_entry": self.squeeze_risk_at_entry,
            "max_pain_at_entry": self.max_pain_at_entry,
            "crypto_gex_at_entry": self.crypto_gex_at_entry,
            "crypto_gex_regime_at_entry": self.crypto_gex_regime_at_entry,
            "oracle_advice": self.oracle_advice,
            "oracle_win_probability": self.oracle_win_probability,
            "oracle_confidence": self.oracle_confidence,
            "oracle_top_factors": self.oracle_top_factors,
            "signal_action": self.signal_action,
            "signal_confidence": self.signal_confidence,
            "signal_reasoning": self.signal_reasoning,
            "status": self.status.value,
            "open_time": self.open_time.isoformat() if self.open_time else None,
            "close_time": self.close_time.isoformat() if self.close_time else None,
            "close_price": self.close_price,
            "close_reason": self.close_reason,
            "realized_pnl": self.realized_pnl,
            "unrealized_pnl": self.unrealized_pnl,
            "high_water_mark": self.high_water_mark,
        }
