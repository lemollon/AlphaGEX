"""
AGAPE-SPOT Models - Multi-ticker 24/7 Coinbase Spot trading.

Supports: ETH-USD, XRP-USD, SHIB-USD, DOGE-USD
LONG-ONLY: Coinbase spot doesn't support shorting for US retail.
P&L = (exit - entry) * quantity (always long).
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any


# ==============================================================================
# SUPPORTED TICKERS - Per-coin configuration
# ==============================================================================

SPOT_TICKERS: Dict[str, Dict[str, Any]] = {
    "ETH-USD": {
        "symbol": "ETH",
        "display_name": "Ethereum",
        "starting_capital": 5000.0,
        "default_quantity": 0.1,
        "min_order": 0.001,
        "max_per_trade": 1.0,
        "quantity_decimals": 4,
        "price_decimals": 2,
    },
    "XRP-USD": {
        "symbol": "XRP",
        "display_name": "XRP",
        "starting_capital": 1000.0,
        "default_quantity": 100.0,
        "min_order": 1.0,
        "max_per_trade": 5000.0,
        "quantity_decimals": 0,
        "price_decimals": 4,
    },
    "SHIB-USD": {
        "symbol": "SHIB",
        "display_name": "Shiba Inu",
        "starting_capital": 1000.0,
        "default_quantity": 1000000.0,
        "min_order": 1000.0,
        "max_per_trade": 100000000.0,
        "quantity_decimals": 0,
        "price_decimals": 8,
    },
    "DOGE-USD": {
        "symbol": "DOGE",
        "display_name": "Dogecoin",
        "starting_capital": 1000.0,
        "default_quantity": 500.0,
        "min_order": 1.0,
        "max_per_trade": 50000.0,
        "quantity_decimals": 0,
        "price_decimals": 4,
    },
}


class TradingMode(Enum):
    PAPER = "paper"
    LIVE = "live"


class PositionStatus(Enum):
    OPEN = "open"
    CLOSED = "closed"
    EXPIRED = "expired"
    STOPPED = "stopped"


class SignalAction(Enum):
    LONG = "LONG"
    RANGE_BOUND = "RANGE_BOUND"
    WAIT = "WAIT"
    CLOSE = "CLOSE"


@dataclass
class AgapeSpotConfig:
    """Configuration for AGAPE-SPOT bot.

    LONG-ONLY: Coinbase spot doesn't support shorting for US retail.
    MULTI-TICKER: Trades ETH-USD, XRP-USD, SHIB-USD, DOGE-USD.
    """

    bot_name: str = "AGAPE-SPOT"
    mode: TradingMode = TradingMode.PAPER

    # Active tickers
    tickers: List[str] = field(default_factory=lambda: list(SPOT_TICKERS.keys()))

    # Risk management (shared)
    risk_per_trade_pct: float = 5.0
    max_open_positions_per_ticker: int = 5

    # Entry/exit rules
    profit_target_pct: float = 50.0
    stop_loss_pct: float = 100.0
    trailing_stop_pct: float = 0.0
    max_hold_hours: int = 24

    # No-Loss Trailing
    use_no_loss_trailing: bool = True
    no_loss_activation_pct: float = 1.0
    no_loss_trail_distance_pct: float = 0.75
    no_loss_emergency_stop_pct: float = 5.0
    max_unrealized_loss_pct: float = 3.0
    no_loss_profit_target_pct: float = 0.0

    # SAR disabled for long-only (can't reverse to short)
    use_sar: bool = False

    # Signal thresholds
    min_confidence: str = "LOW"
    min_funding_rate_signal: float = 0.001
    min_ls_ratio_extreme: float = 1.1
    min_liquidation_proximity_pct: float = 5.0

    # Oracle
    require_oracle_approval: bool = False
    min_oracle_win_probability: float = 0.35

    # Cooldown
    cooldown_minutes: int = 5

    # Loss streak
    max_consecutive_losses: int = 3
    loss_streak_pause_minutes: int = 5

    # Direction Tracker
    direction_cooldown_scans: int = 2
    direction_win_streak_caution: int = 100
    direction_memory_size: int = 10

    def get_ticker_config(self, ticker: str) -> Dict[str, Any]:
        """Get per-ticker config (capital, sizing, etc.)."""
        return SPOT_TICKERS.get(ticker, SPOT_TICKERS["ETH-USD"])

    def get_starting_capital(self, ticker: str) -> float:
        """Get starting capital for a specific ticker."""
        return self.get_ticker_config(ticker).get("starting_capital", 1000.0)

    @classmethod
    def load_from_db(cls, db) -> "AgapeSpotConfig":
        """Load config from database, falling back to defaults."""
        config = cls()
        code_controlled_keys = {"cooldown_minutes", "max_open_positions_per_ticker"}
        try:
            db_config = db.load_config()
            if db_config:
                for key, value in db_config.items():
                    if key in code_controlled_keys:
                        continue
                    if key == "tickers":
                        config.tickers = [t.strip() for t in str(value).split(",") if t.strip()]
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
    """Trading signal for AGAPE-SPOT. LONG-ONLY, multi-ticker."""
    ticker: str
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

    crypto_gex: float = 0.0
    crypto_gex_regime: str = "NEUTRAL"

    # Signal decision
    action: SignalAction = SignalAction.WAIT
    confidence: str = "LOW"
    reasoning: str = ""
    source: str = "agape_spot"

    # Oracle
    oracle_advice: str = "UNKNOWN"
    oracle_win_probability: float = 0.0
    oracle_confidence: float = 0.0
    oracle_top_factors: List[str] = field(default_factory=list)

    # Trade parameters - LONG ONLY
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    quantity: float = 0.0
    max_risk_usd: float = 0.0

    @property
    def is_valid(self) -> bool:
        """Signal is tradeable (LONG only)."""
        return (
            self.action == SignalAction.LONG
            and self.confidence in ("HIGH", "MEDIUM", "LOW")
            and self.quantity > 0
            and self.entry_price is not None
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ticker": self.ticker,
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
            "entry_price": self.entry_price,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "quantity": self.quantity,
            "max_risk_usd": self.max_risk_usd,
        }


@dataclass
class AgapeSpotPosition:
    """LONG-ONLY spot position.

    P&L = (current - entry) * quantity
    No direction multiplier - always long.
    """
    position_id: str
    ticker: str
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

    # Oracle
    oracle_advice: str
    oracle_win_probability: float
    oracle_confidence: float
    oracle_top_factors: List[str]

    # Signal
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
        """LONG-ONLY: P&L = (current - entry) * quantity."""
        pnl = (current_price - self.entry_price) * self.quantity
        return round(pnl, 2)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "position_id": self.position_id,
            "ticker": self.ticker,
            "side": "long",
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
