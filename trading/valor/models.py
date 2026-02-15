"""
VALOR - Data Models
======================

Multi-Futures Scalping Bot using GEX signals.
Named after the legendary hero known for strength and perseverance.

Trades multiple volatile futures contracts: MNQ, CL, NG, RTY (and MES).
All instruments combined in a single bot (like AGAPE-SPOT for crypto).

Clean, minimal data models for VALOR futures trading bot.
Single source of truth for all position and configuration data.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any, List
from zoneinfo import ZoneInfo

CENTRAL_TZ = ZoneInfo("America/Chicago")

# =============================================================================
# PARAMETER VERSION TRACKING
# =============================================================================
# This timestamp marks when the current risk/reward parameters were deployed.
# ML training will ONLY use trades AFTER this date to ensure quality data.
# Update this whenever you make significant parameter changes!
#
# History:
# - v1.0 (original): activation=3.0, max_loss=8.0, no profit target
# - v2.0 (2026-02-04): activation=0.75, max_loss=5.0, profit_target=4.0
# - v2.1 (2026-02-04): REMOVED profit_target cap, let winners run with trailing stop
PARAMETER_VERSION = "2.1"
PARAMETER_VERSION_DATE = "2026-02-04T00:00:00"  # ISO format, Central Time
PARAMETER_VERSION_DESCRIPTION = "Let winners run: no profit cap, trail at +0.75pts, max loss 5pts"

# =============================================================================
# GEX DATA SOURCE RULES (PERMANENT - DO NOT CHANGE)
# =============================================================================
# MARKET HOURS (8 AM - 3 PM CT):
#   PRIMARY: Tradier production API (real-time SPX options chain)
#   FALLBACK: TradingVolatility API
#   Returns: Current day's GEX levels
#
# AFTER HOURS & PRE-MARKET (3 PM - 8 AM CT):
#   PRIMARY: TradingVolatility API (returns FOLLOWING DAY's GEX levels)
#   FALLBACK: Cache from TradingVolatility only (NOT Tradier market-hours data)
#   There is NO Tradier options data after hours.
#   TradingVolatility updates after market close with the next trading day's
#   expected GEX levels (flip point, call wall, put wall, net_gex, etc.).
#   Example: Wed evening → trade off Thursday's GEX.
#            Fri evening → trade off Monday's GEX.
#
# NEVER short-circuit the overnight TradingVolatility call with stale
# Tradier cache from market hours. That is TODAY's data, not tomorrow's.
# =============================================================================

# MES Contract Specifications (kept for backward compatibility)
MES_POINT_VALUE = 5.0  # $5 per index point
MES_TICK_SIZE = 0.25   # Minimum price movement
MES_TICK_VALUE = 1.25  # $1.25 per tick (0.25 * $5)

# =============================================================================
# FUTURES_TICKERS - Multi-instrument contract specifications
# =============================================================================
# Each ticker defines its contract specs, quote sources, and per-ticker
# trading parameters. This is the single source of truth for all instruments.
# Follows the AGAPE-SPOT multi-ticker pattern.
#
# Adding a new ticker:
#   1. Add entry to FUTURES_TICKERS below
#   2. Database tables auto-migrate (ticker column added)
#   3. Executor auto-detects Yahoo/DXFeed symbols
#   4. Frontend auto-discovers via /api/valor/tickers
# =============================================================================

FUTURES_TICKERS: Dict[str, Dict[str, Any]] = {
    "MNQ": {
        "symbol": "MNQ",
        "display_name": "Micro Nasdaq 100",
        "description": "Micro E-mini Nasdaq-100 Futures",
        "exchange": "CME",

        # Contract specifications
        "point_value": 2.0,       # $2 per index point
        "tick_size": 0.25,        # Minimum price movement (0.25 points)
        "tick_value": 0.50,       # $0.50 per tick (0.25 * $2)
        "contract_months": "HMUZ",  # Mar, Jun, Sep, Dec
        "contract_prefix": "/MNQ",  # e.g., /MNQH6

        # Quote sources
        "yahoo_symbol": "MNQ=F",
        "dxfeed_symbol": "/MNQ:XCME",
        "spy_derive_multiplier": None,  # Cannot derive from SPY

        # Capital & risk
        "starting_capital": 100000.0,
        "risk_per_trade_pct": 1.0,
        "max_contracts": 5,
        "max_open_positions": 10,

        # Exit parameters (tuned for NQ volatility - wider stops)
        "initial_stop_points": 10.0,      # ~$20 risk per contract
        "no_loss_activation_pts": 3.0,     # Activate trail after +3 pts ($6)
        "no_loss_trail_distance": 5.0,     # Trail 5 pts behind ($10)
        "no_loss_emergency_stop": 40.0,    # Emergency: 40 pts ($80)
        "max_unrealized_loss_pts": 15.0,   # Safety net: 15 pts ($30)
        "profit_target_points": 20.0,      # Target: 20 pts ($40)

        # SAR parameters
        "sar_trigger_pts": 6.0,
        "sar_mfe_threshold": 1.5,

        # Overnight
        "overnight_stop_points": 5.0,
        "overnight_target_points": 8.0,
        "overnight_emergency_stop": 25.0,

        # GEX source: NQ tracks NDX/QQQ
        "gex_symbol": "NDX",
        "gex_scale_factor": 1.0,  # NDX price ≈ MNQ price

        # UI
        "color_class": "purple",
        "icon": "Zap",
    },
    "CL": {
        "symbol": "CL",
        "display_name": "Crude Oil",
        "description": "WTI Crude Oil Futures (full-size)",
        "exchange": "NYMEX",

        # Contract specifications
        "point_value": 1000.0,     # $1,000 per $1 move (1,000 barrels)
        "tick_size": 0.01,         # $0.01 per barrel
        "tick_value": 10.0,        # $10 per tick (0.01 * $1,000)
        "contract_months": "FGHJKMNQUVXZ",  # Every month
        "contract_prefix": "/CL",

        # Quote sources
        "yahoo_symbol": "CL=F",
        "dxfeed_symbol": "/CL:XNYM",
        "spy_derive_multiplier": None,

        # Capital & risk
        "starting_capital": 100000.0,
        "risk_per_trade_pct": 1.0,
        "max_contracts": 2,
        "max_open_positions": 5,

        # Exit parameters (CL moves ~$1-3/day, $1 = $1,000)
        "initial_stop_points": 0.30,       # $0.30 = $300 risk per contract
        "no_loss_activation_pts": 0.15,    # +$0.15 ($150) to activate trail
        "no_loss_trail_distance": 0.20,    # Trail $0.20 ($200) behind
        "no_loss_emergency_stop": 1.50,    # Emergency: $1.50 ($1,500)
        "max_unrealized_loss_pts": 0.60,   # Safety: $0.60 ($600)
        "profit_target_points": 0.80,      # Target: $0.80 ($800)

        # SAR parameters
        "sar_trigger_pts": 0.25,
        "sar_mfe_threshold": 0.08,

        # Overnight
        "overnight_stop_points": 0.20,
        "overnight_target_points": 0.40,
        "overnight_emergency_stop": 1.00,

        # GEX source: CL uses SPX GEX as macro regime proxy
        "gex_symbol": "SPX",
        "gex_scale_factor": None,  # No price scaling, regime only

        # UI
        "color_class": "amber",
        "icon": "Flame",
    },
    "NG": {
        "symbol": "NG",
        "display_name": "Natural Gas",
        "description": "Henry Hub Natural Gas Futures",
        "exchange": "NYMEX",

        # Contract specifications
        "point_value": 10000.0,    # $10,000 per $1 move (10,000 mmBtu)
        "tick_size": 0.001,        # $0.001 per mmBtu
        "tick_value": 10.0,        # $10 per tick (0.001 * $10,000)
        "contract_months": "FGHJKMNQUVXZ",  # Every month
        "contract_prefix": "/NG",

        # Quote sources
        "yahoo_symbol": "NG=F",
        "dxfeed_symbol": "/NG:XNYM",
        "spy_derive_multiplier": None,

        # Capital & risk
        "starting_capital": 100000.0,
        "risk_per_trade_pct": 0.5,   # Lower risk - NG is extremely volatile
        "max_contracts": 1,
        "max_open_positions": 3,

        # Exit parameters (NG moves ~$0.05-0.20/day, $0.01 = $100)
        "initial_stop_points": 0.020,      # $0.020 = $200 risk per contract
        "no_loss_activation_pts": 0.010,   # +$0.010 ($100) to activate trail
        "no_loss_trail_distance": 0.015,   # Trail $0.015 ($150) behind
        "no_loss_emergency_stop": 0.100,   # Emergency: $0.10 ($1,000)
        "max_unrealized_loss_pts": 0.040,  # Safety: $0.040 ($400)
        "profit_target_points": 0.050,     # Target: $0.050 ($500)

        # SAR parameters
        "sar_trigger_pts": 0.015,
        "sar_mfe_threshold": 0.005,

        # Overnight
        "overnight_stop_points": 0.015,
        "overnight_target_points": 0.030,
        "overnight_emergency_stop": 0.060,

        # GEX source: NG uses SPX GEX as macro regime proxy
        "gex_symbol": "SPX",
        "gex_scale_factor": None,

        # UI
        "color_class": "green",
        "icon": "Flame",
    },
    "RTY": {
        "symbol": "RTY",
        "display_name": "Micro Russell 2000",
        "description": "Micro E-mini Russell 2000 Futures",
        "exchange": "CME",

        # Contract specifications
        "point_value": 5.0,        # $5 per index point
        "tick_size": 0.10,         # 0.10 points
        "tick_value": 0.50,        # $0.50 per tick (0.10 * $5)
        "contract_months": "HMUZ",  # Mar, Jun, Sep, Dec
        "contract_prefix": "/M2K",  # Micro Russell 2000

        # Quote sources
        "yahoo_symbol": "RTY=F",
        "dxfeed_symbol": "/M2K:XCME",
        "spy_derive_multiplier": None,

        # Capital & risk
        "starting_capital": 100000.0,
        "risk_per_trade_pct": 1.0,
        "max_contracts": 5,
        "max_open_positions": 10,

        # Exit parameters (RTY moves ~15-40 pts/day, $5/pt)
        "initial_stop_points": 3.0,        # 3 pts = $15 risk per contract
        "no_loss_activation_pts": 1.5,     # +1.5 pts ($7.50) to activate trail
        "no_loss_trail_distance": 2.0,     # Trail 2 pts ($10) behind
        "no_loss_emergency_stop": 20.0,    # Emergency: 20 pts ($100)
        "max_unrealized_loss_pts": 6.0,    # Safety: 6 pts ($30)
        "profit_target_points": 8.0,       # Target: 8 pts ($40)

        # SAR parameters
        "sar_trigger_pts": 2.5,
        "sar_mfe_threshold": 0.8,

        # Overnight
        "overnight_stop_points": 2.0,
        "overnight_target_points": 4.0,
        "overnight_emergency_stop": 12.0,

        # GEX source: RTY tracks IWM
        "gex_symbol": "IWM",
        "gex_scale_factor": 10.0,  # IWM * 10 ≈ RTY price

        # UI
        "color_class": "red",
        "icon": "TrendingUp",
    },
    "MES": {
        "symbol": "MES",
        "display_name": "Micro S&P 500",
        "description": "Micro E-mini S&P 500 Futures (original VALOR instrument)",
        "exchange": "CME",

        # Contract specifications
        "point_value": MES_POINT_VALUE,
        "tick_size": MES_TICK_SIZE,
        "tick_value": MES_TICK_VALUE,
        "contract_months": "HMUZ",
        "contract_prefix": "/MES",

        # Quote sources
        "yahoo_symbol": "MES=F",
        "dxfeed_symbol": "/MES:XCME",
        "spy_derive_multiplier": 10.0,  # SPY * 10 ≈ MES

        # Capital & risk
        "starting_capital": 100000.0,
        "risk_per_trade_pct": 1.0,
        "max_contracts": 5,
        "max_open_positions": 100,

        # Exit parameters (original VALOR params)
        "initial_stop_points": 2.5,
        "no_loss_activation_pts": 0.75,
        "no_loss_trail_distance": 1.5,
        "no_loss_emergency_stop": 15.0,
        "max_unrealized_loss_pts": 5.0,
        "profit_target_points": 6.0,

        # SAR parameters
        "sar_trigger_pts": 2.0,
        "sar_mfe_threshold": 0.5,

        # Overnight
        "overnight_stop_points": 1.25,
        "overnight_target_points": 2.0,
        "overnight_emergency_stop": 8.0,

        # GEX source: SPX (direct)
        "gex_symbol": "SPX",
        "gex_scale_factor": 1.0,

        # UI
        "color_class": "cyan",
        "icon": "Activity",
    },
}

# Default tickers to trade (can be overridden by config)
DEFAULT_VALOR_TICKERS = ["MNQ", "CL", "NG", "RTY", "MES"]


def get_ticker_config(ticker: str) -> Dict[str, Any]:
    """Get configuration for a specific ticker. Returns empty dict if not found."""
    return FUTURES_TICKERS.get(ticker, {})


def get_ticker_point_value(ticker: str) -> float:
    """Get point value for a ticker. Falls back to MES_POINT_VALUE."""
    cfg = FUTURES_TICKERS.get(ticker, {})
    return cfg.get("point_value", MES_POINT_VALUE)


def get_front_month_symbol(ticker: str) -> str:
    """
    Get the current front month contract symbol for any futures ticker.

    Month codes: F=Jan, G=Feb, H=Mar, J=Apr, K=May, M=Jun,
                 N=Jul, Q=Aug, U=Sep, V=Oct, X=Nov, Z=Dec
    """
    cfg = FUTURES_TICKERS.get(ticker, {})
    prefix = cfg.get("contract_prefix", f"/{ticker}")
    months_str = cfg.get("contract_months", "HMUZ")

    now = datetime.now(CENTRAL_TZ)
    month = now.month
    year = now.year % 10

    # Month code mapping
    month_codes = {
        1: 'F', 2: 'G', 3: 'H', 4: 'J', 5: 'K', 6: 'M',
        7: 'N', 8: 'Q', 9: 'U', 10: 'V', 11: 'X', 12: 'Z'
    }
    # Reverse mapping
    code_to_month = {v: k for k, v in month_codes.items()}

    # Find next valid contract month
    available_months = sorted([code_to_month[c] for c in months_str if c in code_to_month])

    for m in available_months:
        if m >= month:
            return f"{prefix}{month_codes[m]}{year}"

    # Wrap to next year's first available month
    next_year = (year + 1) % 10
    return f"{prefix}{month_codes[available_months[0]]}{next_year}"


class TradingMode(Enum):
    """Trading execution mode"""
    PAPER = "paper"
    LIVE = "live"


class TradeDirection(Enum):
    """Direction of futures trade"""
    LONG = "LONG"
    SHORT = "SHORT"


class GammaRegime(Enum):
    """Market gamma regime"""
    POSITIVE = "POSITIVE"  # Mean reversion - fade moves
    NEGATIVE = "NEGATIVE"  # Momentum - trade breakouts
    NEUTRAL = "NEUTRAL"    # No clear regime


class PositionStatus(Enum):
    """Position lifecycle status"""
    OPEN = "open"
    CLOSED = "closed"
    STOPPED = "stopped"           # Closed by stop loss
    PROFIT_TARGET = "profit_target"  # Closed by profit target
    TRAILED = "trailed"           # Closed by trailing stop
    BREAKEVEN = "breakeven"       # Closed at breakeven
    EXPIRED = "expired"           # Contract expired
    SAR_CLOSED = "sar_closed"     # Closed by Stop-and-Reverse (original position)
    SAR_REVERSAL = "sar_reversal" # Position opened from SAR (reversal trade)


class SignalSource(Enum):
    """Source of trade signal"""
    GEX_MEAN_REVERSION = "GEX_MEAN_REVERSION"  # Positive gamma fade
    GEX_MOMENTUM = "GEX_MOMENTUM"              # Negative gamma breakout
    GEX_FLIP_POINT = "GEX_FLIP_POINT"          # Trade toward flip point
    GEX_WALL_BOUNCE = "GEX_WALL_BOUNCE"        # Bounce off call/put wall
    OVERNIGHT_N1 = "OVERNIGHT_N1"              # Overnight using n+1 GEX
    SAR_REVERSAL = "SAR_REVERSAL"              # Stop-and-Reverse momentum capture


@dataclass
class FuturesPosition:
    """
    Represents a futures position for any supported instrument.

    This is the ONLY position object used throughout the system.
    All fields are explicitly defined - no hidden state.
    """
    # Identity
    position_id: str
    ticker: str = "MES"  # Instrument key into FUTURES_TICKERS (MNQ, CL, NG, RTY, MES)

    # Trade details
    symbol: str  # e.g., "/MESH6", "/MNQH6", "/CLG6"
    direction: TradeDirection
    contracts: int

    # Pricing
    entry_price: float  # MES index points (e.g., 6050.25)
    entry_value: float  # Dollar value (entry_price * contracts * MES_POINT_VALUE)

    # Stop management
    initial_stop: float      # Initial stop price
    current_stop: float      # Current stop (may be trailed)
    breakeven_price: float   # Price where stop moves to breakeven
    trailing_active: bool = False

    # Market context at entry
    gamma_regime: GammaRegime = GammaRegime.NEUTRAL
    gex_value: float = 0.0
    flip_point: float = 0.0
    call_wall: float = 0.0
    put_wall: float = 0.0
    vix_at_entry: float = 0.0
    atr_at_entry: float = 0.0  # For position sizing

    # Signal context (for audit trail)
    signal_source: SignalSource = SignalSource.GEX_MEAN_REVERSION
    signal_confidence: float = 0.0
    win_probability: float = 0.0
    trade_reasoning: str = ""

    # Tastytrade order tracking
    order_id: str = ""

    # ML training data linkage
    scan_id: str = ""  # Links to valor_scan_activity for outcome tracking

    # A/B Test tracking for stop types
    stop_type: str = "DYNAMIC"  # 'FIXED' or 'DYNAMIC' (for A/B test tracking)
    stop_points_used: float = 0.0  # Actual stop distance in points

    # Status
    status: PositionStatus = PositionStatus.OPEN
    open_time: datetime = field(default_factory=lambda: datetime.now(CENTRAL_TZ))
    close_time: Optional[datetime] = None
    close_price: float = 0.0
    close_reason: str = ""
    realized_pnl: float = 0.0

    # Running metrics
    high_water_mark: float = 0.0  # Highest profit reached (in dollars)
    max_adverse_excursion: float = 0.0  # Largest drawdown (in dollars)
    high_price_since_entry: float = 0.0  # Highest price since entry (for backtesting)
    low_price_since_entry: float = 0.0  # Lowest price since entry (for backtesting)

    @property
    def current_pnl_points(self) -> float:
        """Current P&L in points (requires current_price as input)"""
        return 0.0  # Calculated externally with live price

    def calculate_pnl(self, current_price: float) -> float:
        """Calculate P&L at given price using per-ticker point value"""
        if self.direction == TradeDirection.LONG:
            pnl_points = current_price - self.entry_price
        else:
            pnl_points = self.entry_price - current_price
        point_value = get_ticker_point_value(self.ticker)
        return pnl_points * self.contracts * point_value

    @property
    def is_open(self) -> bool:
        """Check if position is still open"""
        return self.status == PositionStatus.OPEN

    @property
    def risk_amount(self) -> float:
        """Dollar risk from entry to initial stop"""
        stop_distance = abs(self.entry_price - self.initial_stop)
        point_value = get_ticker_point_value(self.ticker)
        return stop_distance * self.contracts * point_value

    def should_trail_stop(self, current_price: float, trail_points: float = 1.0) -> Optional[float]:
        """
        Check if trailing stop should be updated.

        Args:
            current_price: Current MES price
            trail_points: Trailing distance in points (default 1.0 = $5)

        Returns:
            New stop price if should update, None otherwise
        """
        if self.direction == TradeDirection.LONG:
            # For longs, trail below current price
            new_stop = current_price - trail_points
            if new_stop > self.current_stop:
                return new_stop
        else:
            # For shorts, trail above current price
            new_stop = current_price + trail_points
            if new_stop < self.current_stop:
                return new_stop
        return None

    def should_move_to_breakeven(self, current_price: float, activation_points: float = 2.0) -> bool:
        """
        Check if stop should move to breakeven.

        Args:
            current_price: Current MES price
            activation_points: Points profit to activate breakeven (default 2.0 = $10)
        """
        if self.trailing_active:
            return False  # Already trailing

        if self.direction == TradeDirection.LONG:
            return current_price >= self.entry_price + activation_points
        else:
            return current_price <= self.entry_price - activation_points

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for DB/logging with FULL context"""
        return {
            'position_id': self.position_id,
            'ticker': self.ticker,
            'symbol': self.symbol,
            'direction': self.direction.value,
            'contracts': self.contracts,
            'entry_price': self.entry_price,
            'entry_value': self.entry_value,
            'initial_stop': self.initial_stop,
            'current_stop': self.current_stop,
            'breakeven_price': self.breakeven_price,
            'trailing_active': self.trailing_active,
            # Market context
            'gamma_regime': self.gamma_regime.value,
            'gex_value': self.gex_value,
            'flip_point': self.flip_point,
            'call_wall': self.call_wall,
            'put_wall': self.put_wall,
            'vix_at_entry': self.vix_at_entry,
            'atr_at_entry': self.atr_at_entry,
            # Signal context
            'signal_source': self.signal_source.value,
            'signal_confidence': self.signal_confidence,
            'win_probability': self.win_probability,
            'trade_reasoning': self.trade_reasoning,
            # Order tracking
            'order_id': self.order_id,
            'status': self.status.value,
            'open_time': self.open_time.isoformat() if self.open_time and hasattr(self.open_time, 'isoformat') else self.open_time,
            'close_time': self.close_time.isoformat() if self.close_time and hasattr(self.close_time, 'isoformat') else self.close_time,
            'close_price': self.close_price,
            'close_reason': self.close_reason,
            'realized_pnl': self.realized_pnl,
            'high_water_mark': self.high_water_mark,
            'max_adverse_excursion': self.max_adverse_excursion,
            'high_price_since_entry': self.high_price_since_entry,
            'low_price_since_entry': self.low_price_since_entry,
        }


@dataclass
class ValorConfig:
    """
    VALOR configuration - all settings in one place.

    Multi-Futures Scalping Strategy Parameters:
    - Trades MNQ, CL, NG, RTY (and MES) simultaneously
    - GEX-based entries (positive = fade, negative = momentum)
    - Per-ticker stop/target/trailing params from FUTURES_TICKERS
    - Fixed fractional position sizing with ATR adjustment
    - 24/5 operation with n+1 GEX for overnight
    """
    # Multi-ticker configuration
    tickers: List[str] = field(default_factory=lambda: list(DEFAULT_VALOR_TICKERS))

    # Risk limits (shared defaults, overridden per-ticker by FUTURES_TICKERS)
    capital: float = 500000.0  # Paper trading capital ($100k per instrument × 5)
    risk_per_trade_pct: float = 1.0  # Risk 1% per trade
    max_contracts: int = 5  # Maximum contracts per trade
    max_open_positions: int = 100  # Effectively unlimited positions per user request

    # MES contract settings (legacy/default - new tickers use FUTURES_TICKERS)
    symbol: str = "/MESH6"  # Current front month (March 2026)
    point_value: float = MES_POINT_VALUE  # $5 per point
    tick_size: float = MES_TICK_SIZE  # 0.25 points

    # Stop loss and profit target settings (in points)
    # TUNED: Based on 136-trade backtest showing 2.5pt stop + 6pt target = +88.5% P&L
    # Risk/Reward ratio: 2.4:1
    initial_stop_points: float = 2.5  # Initial stop: 2.5 points = $12.50
    breakeven_activation_points: float = 1.5  # Move to BE at +1.5 points = $7.50
    trailing_stop_points: float = 0.75  # Trail by 0.75 point = $3.75
    profit_target_points: float = 6.0  # Profit target: 6 points = $30

    # NO-LOSS TRAILING STRATEGY (NL_ACT3_TRAIL2 from backtest: $18,005 P&L, 88% win rate)
    # This strategy: No tight stop until profitable, then trail to lock in gains
    # Key insight: Avoid small stop-outs that would have turned into winners
    use_no_loss_trailing: bool = True  # Enable no-loss trailing mode
    no_loss_activation_pts: float = 0.75  # Points profit before trailing activates
    # TUNED: Lowered from 1.5 to 0.75 because real data shows avg MFE is only 0.63 pts
    # At 1.5, trailing rarely activated - most trades never reached +1.5 pts
    # At 0.75, trailing activates for trades showing even modest initial promise
    no_loss_trail_distance: float = 1.5  # How far behind price to trail (was 2.0)
    no_loss_emergency_stop: float = 15.0  # Emergency stop for catastrophic moves only
    no_loss_profit_target_pts: float = 0.0  # DISABLED - let winners run with trailing stop
    # Set to 0 to disable profit target cap. Winners exit via trailing stop only.
    # This allows unlimited upside while max_loss (5pts) caps downside.

    # MAX UNREALIZED LOSS RULE - Safety net between normal trading and emergency stop
    # Problem: At 8pts ($40/contract) losses were too large vs wins (asymmetric risk/reward)
    # Solution: Tighter max loss to balance risk/reward ratio
    # This is NOT a tighter stop - it's a safety valve before catastrophic loss
    max_unrealized_loss_pts: float = 5.0  # Exit if down 5 pts ($25/contract)
    # TUNED: Lowered from 8.0 to 5.0 for better risk/reward balance
    # At 5 pts: Loss capped at $25/contract - closer to typical win size
    # This improves win/loss ratio from needing 3+ wins per loss to ~2 wins per loss

    # STOP-AND-REVERSE (SAR) STRATEGY
    # When a trade is clearly wrong (down X pts with no profit seen), reverse direction
    # to capture momentum in the correct direction.
    # Backtested on 273 trades: Losers avg MFE=0.18 pts, Winners that dip avg MFE=4.28 pts
    # This clear separation allows safe filtering: only reverse if MFE < threshold
    use_sar: bool = True  # Enable Stop-and-Reverse
    sar_trigger_pts: float = 2.0  # Trigger SAR when down this many points
    sar_mfe_threshold: float = 0.5  # Only reverse if MFE < this (never went profitable)
    # Projected improvement: 55 losers × $33.50/trade = ~$1,842 additional profit
    # Key insight: Losing trades never go profitable (MFE=0.18), so reversing captures momentum

    # OVERNIGHT HYBRID STRATEGY - Different parameters for overnight vs RTH
    # Overnight = 3 PM - 8 AM CT (options close at 3 PM, no hedging = different behavior)
    # RTH = 8 AM - 3 PM CT (regular trading hours with options hedging + better liquidity)
    # Backtest shows tighter stops/smaller targets work better overnight
    use_overnight_hybrid: bool = True  # Enable different params for overnight
    overnight_stop_points: float = 1.25  # Tighter stop for choppy overnight (vs 2.5 RTH)
    overnight_target_points: float = 2.0  # Take profits faster in overnight chop (vs 6.0 RTH)
    # When use_no_loss_trailing is True, these affect the emergency stop only:
    overnight_emergency_stop: float = 8.0  # Tighter emergency stop overnight (low liquidity = gaps)

    # Overnight signal generation thresholds (looser than RTH to account for smaller moves)
    overnight_flip_proximity_pct: float = 0.15  # 0.15% from flip to fade (vs 0.5% RTH) - ~9 pts at SPX 6000
    overnight_breakout_atr_mult: float = 0.3  # 0.3 ATR for breakout (vs 0.5 RTH) - overnight moves are smaller

    # Position sizing
    position_sizing_method: str = "FIXED_FRACTIONAL_ATR"  # Method for sizing
    atr_period: int = 14  # ATR calculation period
    atr_multiplier: float = 2.0  # ATR multiplier for sizing

    # Breakout confirmation
    breakout_method: str = "ATR_TIME_HYBRID"  # ATR + time hold
    breakout_atr_threshold: float = 0.5  # Break by 0.5 ATR to confirm
    breakout_hold_bars: int = 2  # Hold for 2 bars to confirm

    # GEX thresholds
    positive_gamma_threshold: float = 0.0  # Above = positive gamma
    negative_gamma_threshold: float = 0.0  # Below = negative gamma
    flip_point_proximity_pct: float = 0.5  # Trade within 0.5% of flip point

    # Win probability (Bayesian → ML hybrid)
    min_win_probability: float = 0.50  # Minimum 50% win prob to trade
    prior_win_rate: float = 0.50  # Bayesian prior
    learning_rate: float = 0.1  # How fast to update estimates

    # Trading hours (24/5 - futures trade nearly 24 hours)
    # Futures trade Sun 5pm CT - Fri 4pm CT with daily 4pm-5pm CT break
    trade_overnight: bool = True  # Allow overnight trading (futures trade 24/5)
    use_overnight_gex: bool = True  # Use n+1 GEX for overnight (if trading overnight)
    avoid_news_minutes: int = 30  # Reduce size 30 min before major news

    # No daily loss limit as requested
    max_daily_loss: float = 0.0  # 0 = no limit

    # LOSS STREAK PROTECTION - Pause trading after consecutive losses
    # Prevents bleeding during adverse market conditions
    max_consecutive_losses: int = 3  # Pause after this many losses in a row
    loss_streak_pause_minutes: int = 5  # How long to pause (minutes)

    # Mode
    mode: TradingMode = TradingMode.PAPER

    # Tastytrade settings
    account_id: str = ""

    def __post_init__(self):
        """
        Post-initialization hook to auto-update contract symbol.

        BUG FIX: Contract symbol was hardcoded as /MESH6 and required manual
        updates quarterly. This now automatically uses the current front month.
        """
        # Auto-update symbol to current front month if using default MES contract
        # Only update if symbol looks like a hardcoded MES contract (e.g., /MESH6, /MESM5)
        if self.symbol.startswith("/MES") and len(self.symbol) == 6:
            current_front_month = self.get_front_month_symbol()
            if self.symbol != current_front_month:
                # Symbol is stale, auto-update to current front month
                self.symbol = current_front_month

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ValorConfig':
        """Create config from dictionary (e.g., from DB)"""
        config = cls()
        for key, value in data.items():
            if hasattr(config, key):
                if key == 'mode':
                    value = TradingMode(value)
                setattr(config, key, value)
        return config

    def get_front_month_symbol(self) -> str:
        """
        Get the current front month MES contract symbol.

        Month codes: H=Mar, M=Jun, U=Sep, Z=Dec
        """
        now = datetime.now(CENTRAL_TZ)
        month = now.month
        year = now.year % 10  # Last digit

        # Determine front month
        if month <= 3:
            return f"/MESH{year}"  # March
        elif month <= 6:
            return f"/MESM{year}"  # June
        elif month <= 9:
            return f"/MESU{year}"  # September
        else:
            return f"/MESZ{year}"  # December

    def calculate_position_size(
        self,
        account_balance: float,
        atr: float,
        entry_price: float
    ) -> int:
        """
        Calculate position size using Fixed Fractional with ATR Adjustment.

        Formula: contracts = (account * risk_pct) / (ATR * atr_multiplier * point_value)

        Args:
            account_balance: Current account value
            atr: Current ATR in points
            entry_price: Entry price (for validation)

        Returns:
            Number of contracts to trade
        """
        if atr <= 0:
            return 1  # Minimum 1 contract

        # Risk amount
        risk_amount = account_balance * (self.risk_per_trade_pct / 100)

        # Dollar risk per contract based on ATR-adjusted stop
        stop_distance = atr * self.atr_multiplier
        dollar_risk_per_contract = stop_distance * self.point_value

        # Calculate contracts
        if dollar_risk_per_contract <= 0:
            return 1

        contracts = int(risk_amount / dollar_risk_per_contract)

        # Enforce limits
        contracts = max(1, min(contracts, self.max_contracts))

        return contracts

    def get_ticker_exit_params(self, ticker: str) -> Dict[str, Any]:
        """
        Get per-ticker exit parameters (stops, trails, targets).

        Per-ticker values from FUTURES_TICKERS override shared config defaults.
        """
        cfg = FUTURES_TICKERS.get(ticker, {})
        return {
            "initial_stop_points": cfg.get("initial_stop_points", self.initial_stop_points),
            "no_loss_activation_pts": cfg.get("no_loss_activation_pts", self.no_loss_activation_pts),
            "no_loss_trail_distance": cfg.get("no_loss_trail_distance", self.no_loss_trail_distance),
            "no_loss_emergency_stop": cfg.get("no_loss_emergency_stop", self.no_loss_emergency_stop),
            "max_unrealized_loss_pts": cfg.get("max_unrealized_loss_pts", self.max_unrealized_loss_pts),
            "profit_target_points": cfg.get("profit_target_points", self.profit_target_points),
            "sar_trigger_pts": cfg.get("sar_trigger_pts", self.sar_trigger_pts),
            "sar_mfe_threshold": cfg.get("sar_mfe_threshold", self.sar_mfe_threshold),
            "overnight_stop_points": cfg.get("overnight_stop_points", self.overnight_stop_points),
            "overnight_target_points": cfg.get("overnight_target_points", self.overnight_target_points),
            "overnight_emergency_stop": cfg.get("overnight_emergency_stop", self.overnight_emergency_stop),
        }

    def get_ticker_risk_params(self, ticker: str) -> Dict[str, Any]:
        """Get per-ticker risk/sizing parameters."""
        cfg = FUTURES_TICKERS.get(ticker, {})
        return {
            "starting_capital": cfg.get("starting_capital", self.capital),
            "risk_per_trade_pct": cfg.get("risk_per_trade_pct", self.risk_per_trade_pct),
            "max_contracts": cfg.get("max_contracts", self.max_contracts),
            "max_open_positions": cfg.get("max_open_positions", self.max_open_positions),
            "point_value": cfg.get("point_value", self.point_value),
            "tick_size": cfg.get("tick_size", self.tick_size),
        }

    def get_ticker_symbol(self, ticker: str) -> str:
        """Get the current front month contract symbol for a ticker."""
        return get_front_month_symbol(ticker)

    def get_ticker_gex_config(self, ticker: str) -> Dict[str, Any]:
        """Get GEX data source config for a ticker."""
        cfg = FUTURES_TICKERS.get(ticker, {})
        return {
            "gex_symbol": cfg.get("gex_symbol", "SPX"),
            "gex_scale_factor": cfg.get("gex_scale_factor"),
        }

    def calculate_position_size_for_ticker(
        self,
        ticker: str,
        account_balance: float,
        atr: float,
        entry_price: float
    ) -> int:
        """Calculate position size for a specific ticker."""
        risk_params = self.get_ticker_risk_params(ticker)
        point_value = risk_params["point_value"]
        risk_pct = risk_params["risk_per_trade_pct"]
        max_cts = risk_params["max_contracts"]

        if atr <= 0:
            return 1

        risk_amount = account_balance * (risk_pct / 100)
        stop_distance = atr * self.atr_multiplier
        dollar_risk_per_contract = stop_distance * point_value

        if dollar_risk_per_contract <= 0:
            return 1

        contracts = int(risk_amount / dollar_risk_per_contract)
        contracts = max(1, min(contracts, max_cts))
        return contracts

    def validate(self) -> tuple[bool, str]:
        """Validate configuration values."""
        errors = []

        if self.capital <= 0:
            errors.append(f"capital must be > 0, got {self.capital}")

        if self.risk_per_trade_pct <= 0 or self.risk_per_trade_pct > 10:
            errors.append(f"risk_per_trade_pct should be 0-10%, got {self.risk_per_trade_pct}")

        if self.max_contracts <= 0:
            errors.append(f"max_contracts must be > 0, got {self.max_contracts}")

        if self.initial_stop_points <= 0:
            errors.append(f"initial_stop_points must be > 0, got {self.initial_stop_points}")

        if self.trailing_stop_points <= 0:
            errors.append(f"trailing_stop_points must be > 0, got {self.trailing_stop_points}")

        for ticker in self.tickers:
            if ticker not in FUTURES_TICKERS:
                errors.append(f"Unknown ticker '{ticker}' not in FUTURES_TICKERS")

        if errors:
            return False, "; ".join(errors)
        return True, ""


@dataclass
class FuturesSignal:
    """
    A trading signal for any supported futures instrument.
    """
    ticker: str  # Instrument key (MNQ, CL, NG, RTY, MES)
    direction: TradeDirection
    confidence: float
    source: SignalSource

    # Market context
    current_price: float
    gamma_regime: GammaRegime
    gex_value: float
    flip_point: float
    call_wall: float
    put_wall: float
    vix: float
    atr: float

    # Calculated values
    entry_price: float = 0.0
    stop_price: float = 0.0
    target_price: float = 0.0
    contracts: int = 1

    # Win probability
    win_probability: float = 0.0

    # A/B Test tracking for stop types
    stop_type: str = "DYNAMIC"  # 'FIXED' or 'DYNAMIC'
    stop_points_used: float = 0.0  # Actual stop distance in points

    # Reasoning
    reasoning: str = ""

    @property
    def is_valid(self) -> bool:
        """Check if signal passes basic validation"""
        return (
            self.confidence >= 0.50 and
            self.win_probability >= 0.50 and
            self.entry_price > 0 and
            self.stop_price > 0 and
            self.contracts >= 1
        )

    @property
    def risk_points(self) -> float:
        """Risk in points from entry to stop"""
        return abs(self.entry_price - self.stop_price)

    @property
    def risk_dollars(self) -> float:
        """Risk in dollars"""
        point_value = get_ticker_point_value(self.ticker)
        return self.risk_points * self.contracts * point_value


@dataclass
class BayesianWinTracker:
    """
    Tracks win probability using Bayesian updating.
    Transitions to ML model after sufficient data.
    """
    # Bayesian parameters
    alpha: float = 1.0  # Wins + 1 (prior)
    beta: float = 1.0   # Losses + 1 (prior)
    total_trades: int = 0

    # By regime tracking
    positive_gamma_wins: int = 0
    positive_gamma_losses: int = 0
    negative_gamma_wins: int = 0
    negative_gamma_losses: int = 0

    # Cold start protection - floor probability until enough data to be meaningful
    cold_start_trades: int = 10  # Below this, floor the blended probability
    cold_start_floor: float = 0.52  # Floor value (just above 0.50 gate)

    # ML transition threshold
    ml_transition_trades: int = 50  # Switch to ML after 50 trades

    @property
    def win_probability(self) -> float:
        """Current Bayesian estimate of win probability"""
        return self.alpha / (self.alpha + self.beta)

    def update(self, won: bool, regime: GammaRegime):
        """Update estimates after a trade"""
        self.total_trades += 1

        if won:
            self.alpha += 1
            if regime == GammaRegime.POSITIVE:
                self.positive_gamma_wins += 1
            else:
                self.negative_gamma_wins += 1
        else:
            self.beta += 1
            if regime == GammaRegime.POSITIVE:
                self.positive_gamma_losses += 1
            else:
                self.negative_gamma_losses += 1

    def get_regime_probability(self, regime: GammaRegime) -> float:
        """Get win probability for specific regime"""
        if regime == GammaRegime.POSITIVE:
            wins = self.positive_gamma_wins
            losses = self.positive_gamma_losses
        else:
            wins = self.negative_gamma_wins
            losses = self.negative_gamma_losses

        # Add prior
        return (wins + 1) / (wins + losses + 2)

    @property
    def is_cold_start(self) -> bool:
        """True when too few trades for reliable Bayesian estimate"""
        return self.total_trades < self.cold_start_trades

    @property
    def should_use_ml(self) -> bool:
        """Check if enough data for ML model"""
        return self.total_trades >= self.ml_transition_trades

    def to_dict(self) -> Dict[str, Any]:
        return {
            'alpha': self.alpha,
            'beta': self.beta,
            'total_trades': self.total_trades,
            'win_probability': self.win_probability,
            'is_cold_start': self.is_cold_start,
            'cold_start_floor': self.cold_start_floor,
            'positive_gamma_wins': self.positive_gamma_wins,
            'positive_gamma_losses': self.positive_gamma_losses,
            'negative_gamma_wins': self.negative_gamma_wins,
            'negative_gamma_losses': self.negative_gamma_losses,
            'should_use_ml': self.should_use_ml,
        }


@dataclass
class DailySummary:
    """Daily trading summary"""
    date: str
    trades_executed: int = 0
    positions_closed: int = 0
    realized_pnl: float = 0.0
    open_positions: int = 0
    unrealized_pnl: float = 0.0
    positive_gamma_trades: int = 0
    negative_gamma_trades: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            'date': self.date,
            'trades_executed': self.trades_executed,
            'positions_closed': self.positions_closed,
            'realized_pnl': self.realized_pnl,
            'open_positions': self.open_positions,
            'unrealized_pnl': self.unrealized_pnl,
            'positive_gamma_trades': self.positive_gamma_trades,
            'negative_gamma_trades': self.negative_gamma_trades,
        }
