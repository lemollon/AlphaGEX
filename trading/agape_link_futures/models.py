"""
AGAPE-LINK-FUTURES Models - Data structures for the LINK Futures Contract bot.

Mirrors AGAPE-DOGE models pattern with futures contract specs.
Key difference: No contract expiration, 24/7 trading, quantity-based sizing.
LINK: Mid-cap DeFi oracle (~$15-25). 100 LINK per contract.

KEY DIFFERENCES from a perpetual bot:
- Trades Coinbase Derivatives monthly futures (LNK-29MAY26-CDE, LNK-26JUN26-CDE, etc.)
  rather than the geo-blocked Coinbase International perpetual.
- Sizing is integer contracts (1 contract = 100 LINK underlying).
- Live execution requires Tastytrade FCM (or NinjaTrader/IBKR) — NOT Coinbase Advanced Trade.
- Monthly expiration with contract roll required (paper mode skips this; live mode TBD).
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any


class TradingMode(Enum):
    PAPER = "paper"
    LIVE = "live"


class Exchange(Enum):
    PERPETUAL = "perpetual"    # Futures contract exchange


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
class AgapeLinkFuturesConfig:
    """Configuration for AGAPE-LINK-FUTURES bot.

    AGGRESSIVE MODE - Futures contracts, 24/7 trading.
    LINK: Mid-cap DeFi oracle (~$15-25). 100 LINK per contract.
    """

    # Identity
    bot_name: str = "AGAPE_LINK_FUTURES"
    ticker: str = "LINK"
    instrument: str = "LINK-FUT"     # Futures contract

    # Trading mode
    mode: TradingMode = TradingMode.PAPER
    exchange: Exchange = Exchange.PERPETUAL

    # Risk management
    starting_capital: float = 2500.0    # $2.5K starting capital
    risk_per_trade_pct: float = 5.0     # 5% risk per trade
    max_quantity: float = 10.0          # Max 10 contracts per position — at ~$1500/contract notional that's ~$15K per trade
    max_open_positions: int = 2         # Conservative for meme coin

    # Position sizing - Futures contract specs (integer contracts only)
    # 1 contract = 100 LINK
    contract_size: int = 100             # Coinbase Derivatives LNK contract = 100 LINK
    default_quantity: float = 1.0        # 1 contract default trade size
    min_quantity: float = 1.0            # Minimum 1 contract (integer contracts only)
    tick_size: float = 0.01              # Coinbase futures tick — 2-decimal price
    leverage: float = 1.0                # No leverage by default (paper)

    # Entry/exit rules
    profit_target_pct: float = 50.0
    stop_loss_pct: float = 100.0
    trailing_stop_pct: float = 0.0
    max_hold_hours: int = 24

    # No-Loss Trailing Strategy (ported from VALOR)
    use_no_loss_trailing: bool = True
    no_loss_activation_pct: float = 0.5       # 0.5% activation (LINK has larger swings)
    no_loss_trail_distance_pct: float = 0.3   # 0.3% trail distance
    no_loss_emergency_stop_pct: float = 5.0
    max_unrealized_loss_pct: float = 1.5      # 1.5% max loss (LINK)
    no_loss_profit_target_pct: float = 0.0

    # Stop-and-Reverse (SAR) Strategy
    use_sar: bool = True
    sar_trigger_pct: float = 1.5
    sar_mfe_threshold_pct: float = 0.3

    # Regime-aware exits feature flag (default off — current behaviour preserved).
    use_regime_aware_exits: bool = False
    # Optional per-regime profile overrides; stored as JSON strings in
    # autonomous_config and parsed by get_chop_profile/get_trend_profile below.
    exit_profile_chop_json: Optional[str] = None
    exit_profile_trend_json: Optional[str] = None

    # Timing (24/7/365 - futures contracts never close)
    entry_start: str = "00:00"
    entry_end: str = "23:59"
    force_exit: str = ""               # No forced exit - futures

    # Signal thresholds - AGGRESSIVE
    min_confidence: str = "LOW"
    min_funding_rate_signal: float = 0.001
    min_ls_ratio_extreme: float = 1.1
    min_liquidation_proximity_pct: float = 5.0

    # Prophet integration - ADVISORY ONLY
    require_oracle_approval: bool = False
    min_oracle_win_probability: float = 0.35

    # Cooldown - AGGRESSIVE
    cooldown_minutes: int = 0

    # Loss streak protection
    max_consecutive_losses: int = 3
    loss_streak_pause_minutes: int = 5

    # Direction Tracker settings
    direction_cooldown_scans: int = 2
    direction_win_streak_caution: int = 100
    direction_memory_size: int = 10

    @classmethod
    def load_from_db(cls, db) -> "AgapeLinkFuturesConfig":
        """Load config from database, falling back to defaults."""
        config = cls()
        code_controlled_keys = {"cooldown_minutes", "max_open_positions"}
        try:
            db_config = db.load_config()
            if db_config:
                for key, value in db_config.items():
                    if key in code_controlled_keys:
                        continue
                    if key in ("exit_profile_chop_json", "exit_profile_trend_json"):
                        setattr(config, key, str(value) if value is not None else None)
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
                        elif attr_type == Exchange:
                            setattr(config, key, Exchange(value))
        except Exception:
            pass
        return config


@dataclass
class AgapeLinkFuturesSignal:
    """Trading signal generated by AGAPE-LINK-FUTURES signal engine."""
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
    source: str = "agape_link_futures"

    # Prophet context
    oracle_advice: str = "UNKNOWN"
    oracle_win_probability: float = 0.0
    oracle_confidence: float = 0.0
    oracle_top_factors: List[str] = field(default_factory=list)

    # Trade parameters
    side: Optional[str] = None
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    quantity: float = 0.0
    max_risk_usd: float = 0.0

    @property
    def is_valid(self) -> bool:
        return (
            self.action in (SignalAction.LONG, SignalAction.SHORT)
            and self.confidence in ("HIGH", "MEDIUM", "LOW")
            and self.quantity > 0
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
            "quantity": self.quantity,
            "max_risk_usd": self.max_risk_usd,
        }


@dataclass
class AgapeLinkFuturesPosition:
    """An open or closed AGAPE-LINK-FUTURES position."""
    position_id: str
    side: PositionSide
    quantity: float
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

    # Prophet context
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

    # Regime at entry (chop / trend / unknown). Set by trader.run_cycle when
    # use_regime_aware_exits is enabled; None for legacy rows.
    regime_at_entry: Optional[str] = None

    def calculate_pnl(self, current_price: float) -> float:
        """Calculate P&L for current price.

        Futures: P&L = (current - entry) * quantity * direction
        """
        direction = 1 if self.side == PositionSide.LONG else -1
        pnl = (current_price - self.entry_price) * self.quantity * direction
        return round(pnl, 2)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "position_id": self.position_id,
            "side": self.side.value,
            "quantity": self.quantity,
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

import json as _json
from trading.agape_shared.exit_profile import (
    ExitProfile,
    default_chop_profile,
    default_trend_profile,
)


def _resolve_profile(json_str, default_factory):
    if not json_str:
        return default_factory()
    try:
        return ExitProfile.from_dict(_json.loads(json_str))
    except Exception:
        return default_factory()


def get_chop_profile(cfg) -> ExitProfile:
    return _resolve_profile(cfg.exit_profile_chop_json, default_chop_profile)


def get_trend_profile(cfg) -> ExitProfile:
    return _resolve_profile(cfg.exit_profile_trend_json, default_trend_profile)
