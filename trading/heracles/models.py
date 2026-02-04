"""
HERACLES - Data Models
======================

MES Futures Scalping Bot using GEX signals.
Named after the legendary hero known for strength and perseverance.

Clean, minimal data models for HERACLES futures trading bot.
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

# MES Contract Specifications
MES_POINT_VALUE = 5.0  # $5 per index point
MES_TICK_SIZE = 0.25   # Minimum price movement
MES_TICK_VALUE = 1.25  # $1.25 per tick (0.25 * $5)


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


class SignalSource(Enum):
    """Source of trade signal"""
    GEX_MEAN_REVERSION = "GEX_MEAN_REVERSION"  # Positive gamma fade
    GEX_MOMENTUM = "GEX_MOMENTUM"              # Negative gamma breakout
    GEX_FLIP_POINT = "GEX_FLIP_POINT"          # Trade toward flip point
    GEX_WALL_BOUNCE = "GEX_WALL_BOUNCE"        # Bounce off call/put wall
    OVERNIGHT_N1 = "OVERNIGHT_N1"              # Overnight using n+1 GEX


@dataclass
class FuturesPosition:
    """
    Represents an MES futures position.

    This is the ONLY position object used throughout the system.
    All fields are explicitly defined - no hidden state.
    """
    # Identity
    position_id: str

    # Trade details
    symbol: str  # e.g., "/MESH6"
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
    scan_id: str = ""  # Links to heracles_scan_activity for outcome tracking

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
        """Calculate P&L at given price"""
        if self.direction == TradeDirection.LONG:
            pnl_points = current_price - self.entry_price
        else:
            pnl_points = self.entry_price - current_price
        return pnl_points * self.contracts * MES_POINT_VALUE

    @property
    def is_open(self) -> bool:
        """Check if position is still open"""
        return self.status == PositionStatus.OPEN

    @property
    def risk_amount(self) -> float:
        """Dollar risk from entry to initial stop"""
        stop_distance = abs(self.entry_price - self.initial_stop)
        return stop_distance * self.contracts * MES_POINT_VALUE

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
class HERACLESConfig:
    """
    HERACLES configuration - all settings in one place.

    MES Scalping Strategy Parameters:
    - GEX-based entries (positive = fade, negative = momentum)
    - Tight trailing stops with breakeven activation
    - Fixed fractional position sizing with ATR adjustment
    - 24/5 operation with n+1 GEX for overnight
    """
    # Risk limits
    capital: float = 100000.0  # Paper trading capital ($100k starting)
    risk_per_trade_pct: float = 1.0  # Risk 1% per trade
    max_contracts: int = 5  # Maximum contracts per trade
    max_open_positions: int = 100  # Effectively unlimited positions per user request

    # MES contract settings
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

    # OVERNIGHT HYBRID STRATEGY - Different parameters for overnight vs RTH
    # Overnight = 5 PM - 4 AM CT (lower liquidity, different price behavior)
    # RTH = 4 AM - 5 PM CT (regular trading hours with better liquidity)
    # Backtest shows tighter stops/smaller targets work better overnight
    use_overnight_hybrid: bool = True  # Enable different params for overnight
    overnight_stop_points: float = 1.5  # Tighter stop for overnight (vs 2.5 RTH)
    overnight_target_points: float = 3.0  # Smaller target for overnight (vs 6.0 RTH)
    # When use_no_loss_trailing is True, these affect the emergency stop only:
    overnight_emergency_stop: float = 10.0  # Tighter emergency stop overnight

    # GAMMA REGIME FILTER - Optionally restrict to specific gamma regime
    # Backtest showed POSITIVE_GAMMA only = $2,387.50 profit (more consistent)
    # Options: None (all regimes), "POSITIVE", "NEGATIVE"
    allowed_gamma_regime: str = ""  # Empty = all regimes allowed

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
    def from_dict(cls, data: Dict[str, Any]) -> 'HERACLESConfig':
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

        if errors:
            return False, "; ".join(errors)
        return True, ""


@dataclass
class FuturesSignal:
    """
    A trading signal for MES futures with all context needed for execution.
    """
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
        return self.risk_points * self.contracts * MES_POINT_VALUE


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
    def should_use_ml(self) -> bool:
        """Check if enough data for ML model"""
        return self.total_trades >= self.ml_transition_trades

    def to_dict(self) -> Dict[str, Any]:
        return {
            'alpha': self.alpha,
            'beta': self.beta,
            'total_trades': self.total_trades,
            'win_probability': self.win_probability,
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
