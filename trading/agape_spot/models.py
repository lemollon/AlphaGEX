"""
AGAPE-SPOT Models - Multi-ticker 24/7 Coinbase Spot trading.

Supports: ETH-USD, BTC-USD, XRP-USD, SHIB-USD, DOGE-USD, MSTU-USD
LONG-ONLY: Coinbase spot doesn't support shorting for US retail.
P&L = (exit - entry) * quantity (always long).
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any, Tuple
from zoneinfo import ZoneInfo

_CT = ZoneInfo("America/Chicago")


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
        "min_notional_usd": 2.0,  # Coinbase $1 min + safety buffer
        "quantity_decimals": 4,
        "price_decimals": 2,
        # ETH exit params: wider trail for bigger moves
        "no_loss_activation_pct": 1.5,
        "no_loss_trail_distance_pct": 1.25,
        "max_unrealized_loss_pct": 1.5,
        "no_loss_profit_target_pct": 0.0,  # disabled — let trail manage
        "max_hold_hours": 6,
    },
    "BTC-USD": {
        "symbol": "BTC",
        "display_name": "Bitcoin",
        "starting_capital": 5000.0,
        "default_quantity": 0.001,
        "min_order": 0.00001,
        "max_per_trade": 0.05,
        "min_notional_usd": 2.0,
        "quantity_decimals": 5,
        "price_decimals": 2,
        # BTC exit params: similar % to ETH, wider trail for bigger absolute moves
        "no_loss_activation_pct": 1.5,
        "no_loss_trail_distance_pct": 1.25,
        "max_unrealized_loss_pct": 1.5,
        "no_loss_profit_target_pct": 0.0,  # disabled — let trail manage
        "max_hold_hours": 6,
    },
    "XRP-USD": {
        "symbol": "XRP",
        "display_name": "XRP",
        "starting_capital": 1000.0,
        "live_capital": 50.0,
        "default_quantity": 100.0,
        "min_order": 1.0,
        "max_per_trade": 5000.0,
        "min_notional_usd": 2.0,
        "quantity_decimals": 0,
        "price_decimals": 4,
        # XRP exit params: let winners run (removed 1.0% profit cap that was capping gains)
        "no_loss_activation_pct": 0.3,
        "no_loss_trail_distance_pct": 0.25,
        "max_unrealized_loss_pct": 0.5,   # Was 0.75% — cut losers faster (avg loss was ~1.5x avg win)
        "no_loss_profit_target_pct": 0.0,  # Was 1.0% — disabled, let trail manage exits like DOGE
        "max_hold_hours": 2,
        # Signal quality gates — XRP has no Deribit options data, need actual funding signal
        "require_funding_data": True,       # Don't enter on UNKNOWN funding regime
        "allow_base_long": False,           # Disable ALTCOIN_BASE_LONG catchall
        "use_eth_leader": True,             # Use ETH GEX signal as directional compass
        "use_momentum_filter": True,        # Block entries during price downtrends
        "min_scans_between_trades": 10,     # 10 min between entries (1-min scans)
        "max_positions": 2,                 # Was 5 — reduce concurrent exposure
    },
    "SHIB-USD": {
        "symbol": "SHIB",
        "display_name": "Shiba Inu",
        "starting_capital": 1000.0,
        "live_capital": 50.0,
        "default_quantity": 1000000.0,
        "min_order": 1000.0,
        "max_per_trade": 100000000.0,
        "min_notional_usd": 2.0,
        "quantity_decimals": 0,
        "price_decimals": 8,
        # SHIB exit params: meme coin — tighter stops, no profit cap
        "no_loss_activation_pct": 0.3,
        "no_loss_trail_distance_pct": 0.2,  # Was 0.25% — tighter trail for meme coin
        "max_unrealized_loss_pct": 0.5,     # Was 0.75% — cut losers faster
        "no_loss_profit_target_pct": 0.0,   # Was 1.0% — disabled, let trail manage exits
        "max_hold_hours": 2,
        # Signal quality gates — SHIB has no Deribit data, meme coin needs real signal
        "require_funding_data": True,       # Don't enter on UNKNOWN funding regime
        "allow_base_long": False,           # Disable ALTCOIN_BASE_LONG catchall
        "use_eth_leader": True,             # Use ETH GEX signal as directional compass
        "use_momentum_filter": True,        # Block entries during price downtrends
        "min_scans_between_trades": 10,     # 10 min between entries (1-min scans)
        "max_positions": 2,                 # Was 5 — reduce concurrent exposure
    },
    "DOGE-USD": {
        "symbol": "DOGE",
        "display_name": "Dogecoin",
        "starting_capital": 1000.0,
        "live_capital": 50.0,
        "default_quantity": 500.0,
        "min_order": 1.0,
        "max_per_trade": 50000.0,
        "min_notional_usd": 2.0,
        "quantity_decimals": 0,
        "price_decimals": 4,
        # DOGE exit params: 7.43 PF with 40% WR — trailing stop working well, don't change exits
        "no_loss_activation_pct": 0.3,
        "no_loss_trail_distance_pct": 0.25,
        "max_unrealized_loss_pct": 0.75,
        "no_loss_profit_target_pct": 0.0,  # Was 1.0% — disabled, let trail manage (this IS why PF is high)
        "max_hold_hours": 2,
        # Signal quality gates — DOGE trending well, keep base_long but add ETH leader + momentum
        "require_funding_data": False,      # DOGE works without funding data (trending market)
        "allow_base_long": True,            # Keep catchall — DOGE profits from it
        "use_eth_leader": True,             # Use ETH GEX signal as directional compass
        "use_momentum_filter": True,        # Block entries during price downtrends
        "min_scans_between_trades": 5,      # 5 min between entries (1-min scans)
        "max_positions": 3,                 # Was 5 — slight reduction
    },
    "MSTU-USD": {
        "symbol": "MSTU",
        "display_name": "T-Rex 2X Long MSTR ETF",
        "starting_capital": 1000.0,
        "live_capital": 50.0,
        "default_quantity": 10.0,           # ~$53 at $5.32
        "min_order": 0.01,                  # Coinbase supports fractional shares
        "max_per_trade": 500.0,
        "min_notional_usd": 1.0,
        "quantity_decimals": 2,             # Fractional shares to 2 decimals
        "price_decimals": 2,
        # MSTU exit params: 2x leveraged ETF — moves fast, wider stops to avoid whipsaws
        "no_loss_activation_pct": 1.0,      # 2x leverage = big swings, wait for real move
        "no_loss_trail_distance_pct": 0.75, # Trail 0.75% behind HWM
        "max_unrealized_loss_pct": 1.5,     # 2x leverage can gap — give room
        "no_loss_profit_target_pct": 0.0,   # Disabled — let trail manage
        "max_hold_hours": 4,                # Leveraged ETFs have daily decay, don't hold overnight
        # Signal quality gates — stock/ETF on Coinbase, no crypto funding data
        "require_funding_data": False,      # Not a crypto asset — no Deribit funding
        "allow_base_long": True,            # Allow entry on momentum alone
        "use_eth_leader": True,             # MSTU tracks MSTR which tracks BTC — ETH/BTC correlated
        "use_momentum_filter": True,        # Block entries during price downtrends
        "min_scans_between_trades": 10,     # 10 min spacing — lower liquidity than crypto
        "max_positions": 2,                 # Conservative — new ticker, let it prove itself
        # Market hours: MSTU is a US stock ETF — only trades Mon-Fri during market hours
        "market_hours_only": True,          # Skip scanning outside US equity market hours
        "market_open_hour": 8,              # 8:30 AM CT (Central Time)
        "market_open_minute": 30,
        "market_close_hour": 15,            # 3:00 PM CT
        "market_close_minute": 0,
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
    MULTI-TICKER: Trades ETH-USD, BTC-USD, XRP-USD, SHIB-USD, DOGE-USD.
    """

    bot_name: str = "AGAPE-SPOT"
    mode: TradingMode = TradingMode.PAPER

    # Active tickers
    tickers: List[str] = field(default_factory=lambda: list(SPOT_TICKERS.keys()))

    # Per-ticker live trading: tickers in this list execute real Coinbase orders.
    # Tickers NOT in this list run in paper mode regardless of global mode.
    # ETH-USD and BTC-USD use COINBASE_DEDICATED_API_KEY (shared dedicated account).
    live_tickers: List[str] = field(
        default_factory=lambda: ["ETH-USD", "BTC-USD", "XRP-USD", "SHIB-USD", "DOGE-USD", "MSTU-USD"]
    )

    # Risk management (shared)
    risk_per_trade_pct: float = 5.0
    max_open_positions_per_ticker: int = 5

    # Entry/exit rules
    profit_target_pct: float = 50.0
    stop_loss_pct: float = 100.0
    trailing_stop_pct: float = 0.0
    max_hold_hours: int = 6  # Was 24h — data shows 4-12h trades lose money (56% WR, -$9.95 avg)

    # No-Loss Trailing
    use_no_loss_trailing: bool = True
    no_loss_activation_pct: float = 1.5  # Was 1.0% — don't activate trail too early
    no_loss_trail_distance_pct: float = 1.25  # Was 0.75% — was giving back exactly 0.75% every trade
    no_loss_emergency_stop_pct: float = 5.0
    max_unrealized_loss_pct: float = 1.5  # Was 3.0% — losses were $30 vs $9 avg win, need 77% WR to break even
    no_loss_profit_target_pct: float = 0.0

    # SAR disabled for long-only (can't reverse to short)
    use_sar: bool = False

    # Signal thresholds
    min_confidence: str = "LOW"
    min_funding_rate_signal: float = 0.001
    min_ls_ratio_extreme: float = 1.1
    min_liquidation_proximity_pct: float = 5.0

    # Prophet
    require_prophet_approval: bool = False
    min_prophet_win_probability: float = 0.35

    # Cooldown
    cooldown_minutes: int = 0  # Cooldowns removed — trade freely

    # Loss streak
    max_consecutive_losses: int = 3
    loss_streak_pause_minutes: int = 5

    # Daily loss limit (portfolio circuit breaker)
    daily_loss_limit_usd: float = 50.0  # Pause ALL tickers if daily realized P&L < -$50
    daily_loss_limit_enabled: bool = True

    # Direction Tracker
    direction_cooldown_scans: int = 2
    direction_win_streak_caution: int = 100
    direction_memory_size: int = 10

    # Bayesian Choppy-Market Mode
    # When market is range-bound with no momentum, require Bayesian edge confirmation.
    enable_bayesian_choppy: bool = True
    choppy_min_win_prob: float = 0.52      # Bayesian gate for choppy markets
    choppy_position_size_mult: float = 0.5 # Half-size in choppy conditions
    choppy_funding_regimes: str = "BALANCED,MILD_LONG_BIAS,MILD_SHORT_BIAS"
    choppy_max_squeeze_risk: str = "ELEVATED"

    def is_live(self, ticker: str) -> bool:
        """Return True if *ticker* should execute real Coinbase orders."""
        return ticker in self.live_tickers

    def get_ticker_config(self, ticker: str) -> Dict[str, Any]:
        """Get per-ticker config (capital, sizing, etc.)."""
        return SPOT_TICKERS.get(ticker, SPOT_TICKERS["ETH-USD"])

    def get_starting_capital(self, ticker: str) -> float:
        """Get starting capital for a specific ticker (paper tracking)."""
        return self.get_ticker_config(ticker).get("starting_capital", 1000.0)

    def get_exit_params(self, ticker: str) -> Dict[str, Any]:
        """Get per-ticker exit parameters (trail, loss, hold).

        Each ticker in SPOT_TICKERS can override the shared config defaults.
        This enables quick-scalp settings for altcoins (tight trail, fast exits)
        while ETH keeps wider parameters for bigger moves.
        """
        cfg = self.get_ticker_config(ticker)
        return {
            "no_loss_activation_pct": cfg.get("no_loss_activation_pct", self.no_loss_activation_pct),
            "no_loss_trail_distance_pct": cfg.get("no_loss_trail_distance_pct", self.no_loss_trail_distance_pct),
            "max_unrealized_loss_pct": cfg.get("max_unrealized_loss_pct", self.max_unrealized_loss_pct),
            "no_loss_profit_target_pct": cfg.get("no_loss_profit_target_pct", self.no_loss_profit_target_pct),
            "max_hold_hours": cfg.get("max_hold_hours", self.max_hold_hours),
        }

    def get_entry_filters(self, ticker: str) -> Dict[str, Any]:
        """Get per-ticker entry quality filters.

        Controls when a ticker is allowed to enter new trades:
        - require_funding_data: Block entry if funding regime is UNKNOWN
        - allow_base_long: Allow the ALTCOIN_BASE_LONG fallback signal
        - use_eth_leader: Use ETH's GEX signal as directional compass for altcoins
        - use_momentum_filter: Block entries during price downtrends
        - min_scans_between_trades: Minimum scans between new entries (prevents stacking)
        - max_positions: Per-ticker max open positions (overrides shared config)
        """
        cfg = self.get_ticker_config(ticker)
        return {
            "require_funding_data": cfg.get("require_funding_data", False),
            "allow_base_long": cfg.get("allow_base_long", True),
            "use_eth_leader": cfg.get("use_eth_leader", False),
            "use_momentum_filter": cfg.get("use_momentum_filter", False),
            "min_scans_between_trades": cfg.get("min_scans_between_trades", 0),
            "max_positions": cfg.get("max_positions", self.max_open_positions_per_ticker),
        }

    def is_market_hours_ticker(self, ticker: str) -> bool:
        """Return True if this ticker is restricted to US equity market hours."""
        return self.get_ticker_config(ticker).get("market_hours_only", False)

    def is_ticker_in_market_hours(self, ticker: str, now: Optional[datetime] = None) -> bool:
        """Return True if *ticker* is currently in its tradeable window.

        Crypto tickers (market_hours_only=False) always return True (24/7).
        MSTU and other equity-based tickers return True only during Mon-Fri
        market hours in Central Time.
        """
        cfg = self.get_ticker_config(ticker)
        if not cfg.get("market_hours_only", False):
            return True  # crypto — always tradeable

        if now is None:
            now = datetime.now(_CT)
        elif now.tzinfo is None:
            now = now.replace(tzinfo=_CT)
        else:
            now = now.astimezone(_CT)

        # Weekend check: Monday=0 .. Sunday=6
        if now.weekday() >= 5:
            return False

        # Market hours check
        open_h = cfg.get("market_open_hour", 8)
        open_m = cfg.get("market_open_minute", 30)
        close_h = cfg.get("market_close_hour", 15)
        close_m = cfg.get("market_close_minute", 0)

        market_open = now.replace(hour=open_h, minute=open_m, second=0, microsecond=0)
        market_close = now.replace(hour=close_h, minute=close_m, second=0, microsecond=0)

        return market_open <= now <= market_close

    def get_active_tickers(self, now: Optional[datetime] = None) -> List[str]:
        """Return list of tickers currently in their trading window.

        Useful for the capital allocator to redistribute capital from
        inactive tickers (e.g. MSTU on weekends) to active crypto tickers.
        """
        return [t for t in self.tickers if self.is_ticker_in_market_hours(t, now)]

    def get_trading_capital(self, ticker: str) -> float:
        """Get capital used for position sizing.

        LIVE tickers use live_capital (real Coinbase balance).
        PAPER tickers use starting_capital.
        """
        cfg = self.get_ticker_config(ticker)
        if self.is_live(ticker):
            return cfg.get("live_capital", cfg.get("starting_capital", 1000.0))
        return cfg.get("starting_capital", 1000.0)

    @classmethod
    def load_from_db(cls, db) -> "AgapeSpotConfig":
        """Load config from database, falling back to defaults."""
        config = cls()
        code_controlled_keys = {"cooldown_minutes", "max_open_positions_per_ticker", "tickers", "live_tickers"}
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

    # Prophet
    oracle_advice: str = "UNKNOWN"
    oracle_win_probability: float = 0.0
    oracle_confidence: float = 0.0
    oracle_top_factors: List[str] = field(default_factory=list)

    # Volatility context (ATR + chop detection)
    atr: Optional[float] = None           # Average True Range ($)
    atr_pct: Optional[float] = None       # ATR as % of price
    chop_index: Optional[float] = None    # 0=trending, 1=choppy
    volatility_regime: str = "UNKNOWN"    # TRENDING / CHOPPY / UNKNOWN

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
            "atr": self.atr,
            "atr_pct": self.atr_pct,
            "chop_index": self.chop_index,
            "volatility_regime": self.volatility_regime,
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

    # Prophet
    oracle_advice: str
    oracle_win_probability: float
    oracle_confidence: float
    oracle_top_factors: List[str]

    # Signal
    signal_action: str
    signal_confidence: str
    signal_reasoning: str

    # Volatility context at entry (for ATR-adaptive exits)
    atr_at_entry: Optional[float] = None       # ATR in $ at time of entry
    atr_pct_at_entry: Optional[float] = None   # ATR as % of entry price
    chop_index_at_entry: Optional[float] = None

    # Status
    status: PositionStatus = PositionStatus.OPEN
    open_time: Optional[datetime] = None
    close_time: Optional[datetime] = None
    close_price: Optional[float] = None
    close_reason: Optional[str] = None
    realized_pnl: Optional[float] = None

    # Account tracking (which Coinbase account this position belongs to)
    # "default" = COINBASE_API_KEY, "{SYMBOL}" = COINBASE_{SYMBOL}_API_KEY, "paper" = simulated
    account_label: str = "default"

    # Coinbase execution tracking
    coinbase_order_id: Optional[str] = None
    coinbase_sell_order_id: Optional[str] = None
    entry_slippage_pct: Optional[float] = None
    exit_slippage_pct: Optional[float] = None
    entry_fee_usd: Optional[float] = None
    exit_fee_usd: Optional[float] = None

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
            "account_label": self.account_label,
            "coinbase_order_id": self.coinbase_order_id,
            "coinbase_sell_order_id": self.coinbase_sell_order_id,
            "entry_slippage_pct": self.entry_slippage_pct,
            "exit_slippage_pct": self.exit_slippage_pct,
            "entry_fee_usd": self.entry_fee_usd,
            "exit_fee_usd": self.exit_fee_usd,
            "unrealized_pnl": self.unrealized_pnl,
            "high_water_mark": self.high_water_mark,
        }


# ==============================================================================
# Funding Regime enum for Bayesian tracker
# ==============================================================================

class FundingRegime(Enum):
    """Simplified funding regime for Bayesian tracking.

    Groups the detailed funding regimes (EXTREME_POSITIVE, HEAVILY_POSITIVE, etc.)
    into three buckets for meaningful win-rate statistics.
    """
    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"
    NEUTRAL = "NEUTRAL"

    @classmethod
    def from_funding_string(cls, regime_str: str) -> "FundingRegime":
        """Map detailed funding regime strings to simplified buckets."""
        if not regime_str:
            return cls.NEUTRAL
        upper = regime_str.upper()
        if "POSITIVE" in upper:
            return cls.POSITIVE
        if "NEGATIVE" in upper:
            return cls.NEGATIVE
        return cls.NEUTRAL


# ==============================================================================
# BayesianWinTracker - Per-ticker crypto adaptation
# ==============================================================================

@dataclass
class BayesianWinTracker:
    """Tracks win probability using Bayesian updating for crypto spot trading.

    Adapted from VALOR's gamma-regime tracker for crypto funding regimes.
    Each ticker gets its own tracker instance for independent learning.

    Phases:
      - Cold start (< 10 trades): probability floored at 0.52 so the bot
        can trade and collect data.
      - Bayesian (10-49 trades): blends regime-specific win rate with signal
        confidence. Bayesian weight ramps from 0.3 to 0.7.
      - ML transition (>= 50 trades): signals that enough data exists for an
        ML model (future use).

    Recovery mechanism:
      After a losing streak the regime probability drops below the 0.50 gate,
      suppressing new entries in that regime.  Each subsequent win raises it
      back: (wins+1)/(wins+losses+2).  The Laplace prior (+1/+2) ensures it
      can never hit 0.0 or 1.0, always pulling toward 0.50.
    """
    ticker: str = "ETH-USD"

    # Bayesian parameters
    alpha: float = 1.0   # Wins + 1 (prior)
    beta: float = 1.0    # Losses + 1 (prior)
    total_trades: int = 0

    # By funding regime tracking
    positive_funding_wins: int = 0
    positive_funding_losses: int = 0
    negative_funding_wins: int = 0
    negative_funding_losses: int = 0
    neutral_funding_wins: int = 0
    neutral_funding_losses: int = 0

    # Cold start protection
    cold_start_trades: int = 10
    cold_start_floor: float = 0.52

    # ML transition threshold
    ml_transition_trades: int = 50

    @property
    def win_probability(self) -> float:
        """Current overall Bayesian estimate of win probability."""
        return self.alpha / (self.alpha + self.beta)

    def update(self, won: bool, funding_regime: FundingRegime):
        """Update estimates after a trade closes."""
        self.total_trades += 1

        if won:
            self.alpha += 1
            if funding_regime == FundingRegime.POSITIVE:
                self.positive_funding_wins += 1
            elif funding_regime == FundingRegime.NEGATIVE:
                self.negative_funding_wins += 1
            else:
                self.neutral_funding_wins += 1
        else:
            self.beta += 1
            if funding_regime == FundingRegime.POSITIVE:
                self.positive_funding_losses += 1
            elif funding_regime == FundingRegime.NEGATIVE:
                self.negative_funding_losses += 1
            else:
                self.neutral_funding_losses += 1

    def get_regime_probability(self, funding_regime: FundingRegime) -> float:
        """Get win probability for a specific funding regime.

        Uses Laplace smoothing: (wins + 1) / (wins + losses + 2).
        """
        if funding_regime == FundingRegime.POSITIVE:
            wins = self.positive_funding_wins
            losses = self.positive_funding_losses
        elif funding_regime == FundingRegime.NEGATIVE:
            wins = self.negative_funding_wins
            losses = self.negative_funding_losses
        else:
            wins = self.neutral_funding_wins
            losses = self.neutral_funding_losses

        return (wins + 1) / (wins + losses + 2)

    @property
    def is_cold_start(self) -> bool:
        """True when too few trades for reliable Bayesian estimate."""
        return self.total_trades < self.cold_start_trades

    @property
    def should_use_ml(self) -> bool:
        """Check if enough data for ML model."""
        return self.total_trades >= self.ml_transition_trades

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ticker": self.ticker,
            "alpha": self.alpha,
            "beta": self.beta,
            "total_trades": self.total_trades,
            "win_probability": self.win_probability,
            "is_cold_start": self.is_cold_start,
            "cold_start_floor": self.cold_start_floor,
            "positive_funding_wins": self.positive_funding_wins,
            "positive_funding_losses": self.positive_funding_losses,
            "negative_funding_wins": self.negative_funding_wins,
            "negative_funding_losses": self.negative_funding_losses,
            "neutral_funding_wins": self.neutral_funding_wins,
            "neutral_funding_losses": self.neutral_funding_losses,
            "should_use_ml": self.should_use_ml,
            "regime_probabilities": {
                "POSITIVE": self.get_regime_probability(FundingRegime.POSITIVE),
                "NEGATIVE": self.get_regime_probability(FundingRegime.NEGATIVE),
                "NEUTRAL": self.get_regime_probability(FundingRegime.NEUTRAL),
            },
        }


# ==============================================================================
# CapitalAllocator - Performance-based live-account capital allocation
# ==============================================================================

import logging as _logging

_alloc_logger = _logging.getLogger(__name__)


@dataclass
class TickerPerformance:
    """Snapshot of a ticker's historical performance used for ranking."""
    ticker: str
    total_trades: int = 0
    wins: int = 0
    total_pnl: float = 0.0
    recent_pnl: float = 0.0       # last 24h realized P&L
    avg_win: float = 0.0
    avg_loss: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    score: float = 0.0            # computed composite score
    allocation_pct: float = 0.0   # assigned % of available balance
    is_active: bool = True        # False when outside market hours (e.g. MSTU on weekends)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ticker": self.ticker,
            "total_trades": self.total_trades,
            "wins": self.wins,
            "total_pnl": round(self.total_pnl, 2),
            "recent_pnl": round(self.recent_pnl, 2),
            "avg_win": round(self.avg_win, 2),
            "avg_loss": round(self.avg_loss, 2),
            "win_rate": round(self.win_rate, 4),
            "profit_factor": round(self.profit_factor, 2),
            "score": round(self.score, 4),
            "allocation_pct": round(self.allocation_pct, 4),
            "is_active": self.is_active,
        }


class CapitalAllocator:
    """Ranks tickers by historical performance and allocates live capital proportionally.

    Used by the executor to decide how much of an account's available USD balance
    to spend on a given ticker. Paper accounts are NOT affected — they always
    trade at full config quantity.

    Scoring formula (composite):
      score = (0.35 * norm_pf) + (0.25 * norm_wr) + (0.25 * norm_recent) + (0.15 * norm_total)

    Where:
      - norm_pf     = profit_factor / max_pf  (capped at 1.0)
      - norm_wr     = win_rate                 (already 0-1)
      - norm_recent = recent_pnl normalised to [-1, 1] range
      - norm_total  = total_pnl normalised to [-1, 1] range

    Allocation:
      - Each ticker gets a proportional share based on its score.
      - A floor of 10% ensures no ticker gets starved entirely (can still enter).
      - Tickers with zero trades get a cold-start share (equal split).

    Refresh cadence: once per scan cycle (called from trader.py).
    """

    # Floor allocation % so every ticker can at least enter small positions
    MIN_ALLOCATION_PCT = 0.10

    # How many recent hours of P&L count as "recent" performance
    RECENT_HOURS = 24

    def __init__(self, tickers: List[str]):
        self.tickers = tickers
        self._rankings: Dict[str, TickerPerformance] = {}
        # Equal split until first refresh
        equal_share = 1.0 / max(len(tickers), 1)
        for t in tickers:
            self._rankings[t] = TickerPerformance(
                ticker=t, allocation_pct=equal_share,
            )

    def refresh(
        self,
        perf_data: Dict[str, Dict[str, Any]],
        active_tickers: Optional[List[str]] = None,
    ) -> None:
        """Recalculate rankings from fresh performance data.

        perf_data: {ticker: {total_trades, wins, total_pnl, recent_pnl,
                             avg_win, avg_loss}} — provided by db query.
        active_tickers: subset of tickers currently in their trading window.
                        If provided, inactive tickers get 0% allocation and
                        their share is redistributed to active ones.
                        Scores are still computed for all tickers (for UI).
        """
        # Default: all tickers active
        active_set = set(active_tickers) if active_tickers is not None else set(self.tickers)

        perfs: List[TickerPerformance] = []
        for ticker in self.tickers:
            d = perf_data.get(ticker, {})
            total = d.get("total_trades", 0)
            wins = d.get("wins", 0)
            losses = total - wins
            total_pnl = d.get("total_pnl", 0.0)
            recent_pnl = d.get("recent_pnl", 0.0)
            avg_win = d.get("avg_win", 0.0)
            avg_loss = abs(d.get("avg_loss", 0.0))

            win_rate = wins / total if total > 0 else 0.0
            pf = (avg_win * wins) / (avg_loss * losses) if (losses > 0 and avg_loss > 0) else (
                2.0 if wins > 0 else 0.0
            )

            perfs.append(TickerPerformance(
                ticker=ticker,
                total_trades=total,
                wins=wins,
                total_pnl=total_pnl,
                recent_pnl=recent_pnl,
                avg_win=avg_win,
                avg_loss=avg_loss,
                win_rate=win_rate,
                profit_factor=min(pf, 10.0),  # cap to prevent single outlier domination
                is_active=(ticker in active_set),
            ))

        # --- Compute composite scores (for ALL tickers, active or not) ---
        self._score_tickers(perfs)

        # --- Assign allocation percentages (only active tickers get share) ---
        self._allocate(perfs)

        # Store
        self._rankings = {p.ticker: p for p in perfs}

        inactive_str = ""
        inactive = [p.ticker for p in perfs if not p.is_active]
        if inactive:
            inactive_str = f" | INACTIVE (market closed): {', '.join(inactive)}"

        _alloc_logger.info(
            "AGAPE-SPOT ALLOCATOR: Rankings refreshed — %s%s",
            " | ".join(
                f"{p.ticker}: score={p.score:.3f} alloc={p.allocation_pct:.1%}"
                for p in sorted(perfs, key=lambda x: x.score, reverse=True)
            ),
            inactive_str,
        )

    def _score_tickers(self, perfs: List[TickerPerformance]) -> None:
        """Compute composite score for each ticker.

        For inactive tickers (outside market hours), the 24h recent P&L
        component is excluded and its weight redistributed to avoid
        penalizing tickers that simply can't trade right now.
        """
        # Normalisation bounds
        max_pf = max((p.profit_factor for p in perfs), default=1.0) or 1.0
        pnl_values = [p.total_pnl for p in perfs]
        recent_values = [p.recent_pnl for p in perfs]
        pnl_range = max(abs(max(pnl_values, default=0)), abs(min(pnl_values, default=0)), 1.0)
        recent_range = max(abs(max(recent_values, default=0)), abs(min(recent_values, default=0)), 1.0)

        for p in perfs:
            if p.total_trades == 0:
                # Cold start: neutral score so it gets equal share
                p.score = 0.5
                continue

            norm_pf = min(p.profit_factor / max_pf, 1.0)
            norm_wr = p.win_rate
            norm_total = (p.total_pnl / pnl_range + 1.0) / 2.0   # map [-1,1] -> [0,1]

            if p.is_active:
                # Normal weighting: 35% PF + 25% WR + 25% recent + 15% total
                norm_recent = (p.recent_pnl / recent_range + 1.0) / 2.0
                p.score = (
                    0.35 * norm_pf
                    + 0.25 * norm_wr
                    + 0.25 * norm_recent
                    + 0.15 * norm_total
                )
            else:
                # Inactive ticker: drop the 24h recent component (it's always $0
                # on weekends) and redistribute weight to long-term metrics.
                # Reweighted: 45% PF + 30% WR + 25% total
                p.score = (
                    0.45 * norm_pf
                    + 0.30 * norm_wr
                    + 0.25 * norm_total
                )

    def _allocate(self, perfs: List[TickerPerformance]) -> None:
        """Assign allocation percentages based on scores.

        Scores are shifted so the minimum becomes MIN_ALLOCATION_PCT,
        then normalised so they sum to 1.0.

        Inactive tickers (outside market hours) get 0% allocation and
        their share is redistributed proportionally to active tickers.
        """
        n = len(perfs)
        if n == 0:
            return
        if n == 1:
            perfs[0].allocation_pct = 1.0 if perfs[0].is_active else 0.0
            return

        active_perfs = [p for p in perfs if p.is_active]
        inactive_perfs = [p for p in perfs if not p.is_active]

        # Give inactive tickers 0% — their capital goes to active tickers
        for p in inactive_perfs:
            p.allocation_pct = 0.0

        if not active_perfs:
            # All tickers inactive (shouldn't happen, but handle gracefully)
            equal_share = 1.0 / n
            for p in perfs:
                p.allocation_pct = equal_share
            return

        # Allocate among active tickers only
        min_score = min(p.score for p in active_perfs)
        shifted = []
        for p in active_perfs:
            shifted.append(max(p.score - min_score, 0.0) + self.MIN_ALLOCATION_PCT)

        total_shifted = sum(shifted)
        for p, s in zip(active_perfs, shifted):
            p.allocation_pct = s / total_shifted

    def get_allocation(self, ticker: str) -> float:
        """Return the allocation fraction [0.0, 1.0] for a ticker.

        This is the fraction of available USD balance to use for this ticker.
        """
        perf = self._rankings.get(ticker)
        if not perf:
            return 1.0 / max(len(self.tickers), 1)
        return perf.allocation_pct

    def get_rankings(self) -> List[TickerPerformance]:
        """Return all tickers sorted by score (best first)."""
        return sorted(self._rankings.values(), key=lambda p: p.score, reverse=True)

    def to_dict(self) -> Dict[str, Any]:
        ranked = self.get_rankings()
        return {
            "rankings": [p.to_dict() for p in ranked],
            "total_tickers": len(ranked),
        }
