"""
AGAPE-SPOT Models - Data structures for the 24/7 Coinbase Spot ETH bot.

Mirrors AGAPE models but adapted for spot trading:
  - No Exchange enum (always Coinbase spot)
  - P&L based on full ETH value, not futures contract multiplier
  - Position sizing in ETH quantity
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
    RANGE_BOUND = "RANGE_BOUND"
    WAIT = "WAIT"
    CLOSE = "CLOSE"


@dataclass
class AgapeSpotConfig:
    """Configuration for AGAPE-SPOT bot - loaded from autonomous_config table.

    SPOT-NATIVE: Trades ETH-USD on Coinbase 24/7/365.
    P&L = (exit - entry) * eth_quantity (full spot value).
    """

    # Identity
    bot_name: str = "AGAPE-SPOT"
    ticker: str = "ETH"
    instrument: str = "ETH-USD"

    # Trading mode
    mode: TradingMode = TradingMode.PAPER

    # Risk management - scaled for spot (no leverage)
    starting_capital: float = 5000.0
    risk_per_trade_pct: float = 5.0    # 5% risk per trade ($250 on $5K)
    max_eth_per_trade: float = 1.0     # Max 1 ETH per trade (~$2,085)
    max_open_positions: int = 20       # Aggressive: many concurrent positions

    # Position sizing
    # Spot: trade in ETH quantity directly
    # min_eth_order = Coinbase minimum (0.00001 ETH, but practical min ~0.001)
    min_eth_order: float = 0.001
    default_eth_size: float = 0.1      # Default 0.1 ETH per trade (~$208)

    # Entry/exit rules
    profit_target_pct: float = 50.0
    stop_loss_pct: float = 100.0
    trailing_stop_pct: float = 0.0
    max_hold_hours: int = 24

    # No-Loss Trailing Strategy (ported from HERACLES via AGAPE)
    use_no_loss_trailing: bool = True
    no_loss_activation_pct: float = 1.0
    no_loss_trail_distance_pct: float = 0.75
    no_loss_emergency_stop_pct: float = 5.0
    max_unrealized_loss_pct: float = 3.0
    no_loss_profit_target_pct: float = 0.0

    # Stop-and-Reverse (SAR)
    use_sar: bool = True
    sar_trigger_pct: float = 1.5
    sar_mfe_threshold_pct: float = 0.3

    # Signal thresholds - AGGRESSIVE
    min_confidence: str = "LOW"
    min_funding_rate_signal: float = 0.001
    min_ls_ratio_extreme: float = 1.1
    min_liquidation_proximity_pct: float = 5.0

    # Oracle integration - ADVISORY ONLY
    require_oracle_approval: bool = False
    min_oracle_win_probability: float = 0.35

    # Cooldown - AGGRESSIVE
    cooldown_minutes: int = 5

    # Loss streak protection
    max_consecutive_losses: int = 3
    loss_streak_pause_minutes: int = 5

    # Direction Tracker settings
    direction_cooldown_scans: int = 2
    direction_win_streak_caution: int = 100
    direction_memory_size: int = 10

    @classmethod
    def load_from_db(cls, db) -> "AgapeSpotConfig":
        """Load config from database, falling back to defaults."""
        config = cls()
        code_controlled_keys = {"cooldown_minutes", "max_open_positions"}
        try:
            db_config = db.load_config()
            if db_config:
                for key, value in db_config.items():
                    if key in code_controlled_keys:
                        continue
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
            pass
        return config


@dataclass
class AgapeSpotSignal:
    """Trading signal for AGAPE-SPOT.

    Spot-native: position sized in ETH quantity, not contracts.
    """
    spot_price: float
    timestamp: datetime

    # Crypto microstructure
    funding_rate: float = 0.0
    funding_regime: str = "UNKNOWN"
    ls_ratio: float = 1.0
    ls_bias: str = "NEUTRAL"
    nearest_long_liq: Optional[float] = None
    nearest_short_liq: Optional[float] = None
    squeeze_risk: str = "LOW"
    leverage_regime: str = "UNKNOWN"
    max_pain: Optional[float] = None

    # Crypto GEX
    crypto_gex: float = 0.0
    crypto_gex_regime: str = "NEUTRAL"

    # Signal decision
    action: SignalAction = SignalAction.WAIT
    confidence: str = "LOW"
    reasoning: str = ""
    source: str = "agape_spot"

    # Oracle context
    oracle_advice: str = "UNKNOWN"
    oracle_win_probability: float = 0.0
    oracle_confidence: float = 0.0
    oracle_top_factors: List[str] = field(default_factory=list)

    # Trade parameters - SPOT NATIVE
    side: Optional[str] = None
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    eth_quantity: float = 0.0          # ETH amount (not contracts)
    max_risk_usd: float = 0.0

    @property
    def is_valid(self) -> bool:
        """Signal is tradeable."""
        return (
            self.action in (SignalAction.LONG, SignalAction.SHORT)
            and self.confidence in ("HIGH", "MEDIUM", "LOW")
            and self.eth_quantity > 0
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
            "eth_quantity": self.eth_quantity,
            "max_risk_usd": self.max_risk_usd,
        }


@dataclass
class AgapeSpotPosition:
    """An open or closed AGAPE-SPOT position.

    SPOT-NATIVE P&L:
      P&L = (current - entry) * eth_quantity * direction
      No contract_size multiplier - full ETH value.
    """
    position_id: str
    side: PositionSide
    eth_quantity: float            # ETH amount (e.g., 0.5 ETH)
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

    # Oracle context
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
    high_water_mark: float = 0.0
    last_update: Optional[datetime] = None

    def calculate_pnl(self, current_price: float) -> float:
        """Calculate P&L for current price.

        SPOT: P&L = (current - entry) * eth_quantity * direction
        Full ETH value, no contract multiplier.
        """
        direction = 1 if self.side == PositionSide.LONG else -1
        pnl = (current_price - self.entry_price) * self.eth_quantity * direction
        return round(pnl, 2)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "position_id": self.position_id,
            "side": self.side.value,
            "eth_quantity": self.eth_quantity,
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
