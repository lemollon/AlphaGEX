"""
PROMETHEUS Models - Box Spread Synthetic Borrowing

Enhanced transparency models for educational purposes.
Every field includes documentation explaining its purpose.
"""

from dataclasses import dataclass, field
from datetime import datetime, date
from decimal import Decimal
from enum import Enum
from typing import Optional, List, Dict, Any
import json


class TradingMode(Enum):
    """Trading execution mode"""
    PAPER = "paper"      # Simulated trading for testing
    LIVE = "live"        # Real orders via Tradier


class PositionStatus(Enum):
    """Box spread position lifecycle states"""
    PENDING = "pending"          # Order submitted, awaiting fill
    OPEN = "open"                # Position is active
    CLOSING = "closing"          # Close order submitted
    CLOSED = "closed"            # Position fully closed
    EXPIRED = "expired"          # Let expire at maturity
    ROLLED = "rolled"            # Rolled to new expiration
    ASSIGNMENT_RISK = "assignment_risk"  # Early assignment detected


class BoxSpreadStatus(Enum):
    """Overall PROMETHEUS system status"""
    ACTIVE = "active"            # Normal operation
    PAUSED = "paused"            # Manually paused
    MARGIN_WARNING = "margin_warning"    # Approaching margin limit
    ASSIGNMENT_ALERT = "assignment_alert"  # Assignment risk detected
    RATE_UNFAVORABLE = "rate_unfavorable"  # Borrowing rate too high


@dataclass
class BoxSpreadSignal:
    """
    A signal to open a box spread position.

    EDUCATIONAL NOTE - Box Spread Mechanics:
    =========================================
    A box spread combines a bull call spread with a bear put spread
    at the same strikes, creating a position with a guaranteed payoff
    at expiration equal to the strike width.

    Example with 500/510 strikes:
    - Buy 500 Call + Sell 510 Call (Bull Call Spread)
    - Buy 510 Put + Sell 500 Put (Bear Put Spread)
    - Guaranteed payoff at expiration: $10 × 100 = $1,000 per contract

    If you SELL this box for $985 today:
    - You receive $985 cash now
    - You pay back $1,000 at expiration
    - Implied borrowing cost: $15 over the period
    - This is synthetic borrowing at near risk-free rates!
    """

    # Signal identification
    signal_id: str
    signal_time: datetime

    # Underlying details
    ticker: str                   # SPX (European-style, no early assignment)
    spot_price: float             # Current underlying price

    # Strike selection
    lower_strike: float           # Lower strike (e.g., 5900)
    upper_strike: float           # Upper strike (e.g., 5950)
    strike_width: float           # Difference (e.g., 50 points)
    expiration: str               # Target expiration date (YYYY-MM-DD)
    dte: int                      # Days to expiration

    # Pricing - THE KEY TO UNDERSTANDING BOX SPREADS
    theoretical_value: float      # Strike width × 100 (guaranteed at expiration)
    market_bid: float             # What market will pay for box (you receive this)
    market_ask: float             # What market wants to sell box for
    mid_price: float              # (bid + ask) / 2

    # Borrowing cost analysis - THIS IS THE MAGIC
    cash_received: float          # Mid price × contracts × 100
    cash_owed_at_expiration: float  # Theoretical value × contracts × 100
    borrowing_cost: float         # cash_owed - cash_received (your "interest")
    implied_annual_rate: float    # Annualized borrowing rate (%)

    # Comparison to alternatives
    fed_funds_rate: float         # Current Fed Funds rate for comparison
    margin_rate: float            # Typical broker margin rate
    rate_advantage: float         # How much cheaper than margin (bps)

    # Risk assessment
    early_assignment_risk: str    # LOW/MEDIUM/HIGH (SPX=LOW, SPY=MEDIUM)
    assignment_risk_explanation: str  # Why this risk level
    margin_requirement: float     # Estimated margin needed
    margin_pct_of_capital: float  # As percentage of total capital

    # Recommended sizing
    recommended_contracts: int    # Based on capital and risk tolerance
    total_cash_generated: float   # If signal is executed

    # Educational annotations
    strategy_explanation: str     # Plain English explanation
    why_this_expiration: str      # Why this expiration was chosen
    why_these_strikes: str        # Why these strikes were chosen

    # Validity
    is_valid: bool = True
    skip_reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary with all educational context"""
        return {
            'signal_id': self.signal_id,
            'signal_time': self.signal_time.isoformat() if self.signal_time else None,
            'ticker': self.ticker,
            'spot_price': self.spot_price,
            'lower_strike': self.lower_strike,
            'upper_strike': self.upper_strike,
            'strike_width': self.strike_width,
            'expiration': self.expiration,
            'dte': self.dte,
            'theoretical_value': self.theoretical_value,
            'market_bid': self.market_bid,
            'market_ask': self.market_ask,
            'mid_price': self.mid_price,
            'cash_received': self.cash_received,
            'cash_owed_at_expiration': self.cash_owed_at_expiration,
            'borrowing_cost': self.borrowing_cost,
            'implied_annual_rate': self.implied_annual_rate,
            'fed_funds_rate': self.fed_funds_rate,
            'margin_rate': self.margin_rate,
            'rate_advantage': self.rate_advantage,
            'early_assignment_risk': self.early_assignment_risk,
            'assignment_risk_explanation': self.assignment_risk_explanation,
            'margin_requirement': self.margin_requirement,
            'margin_pct_of_capital': self.margin_pct_of_capital,
            'recommended_contracts': self.recommended_contracts,
            'total_cash_generated': self.total_cash_generated,
            'strategy_explanation': self.strategy_explanation,
            'why_this_expiration': self.why_this_expiration,
            'why_these_strikes': self.why_these_strikes,
            'is_valid': self.is_valid,
            'skip_reason': self.skip_reason,
        }


@dataclass
class BoxSpreadPosition:
    """
    An active box spread position with full transparency.

    EDUCATIONAL NOTE - Position Lifecycle:
    ======================================
    1. OPEN: You sold the box, received cash
    2. HOLDING: Cash is deployed to IC bots, earning premium
    3. EXPIRATION: Box expires, you "repay" the theoretical value
    4. NET RESULT: IC returns minus borrowing cost = profit/loss

    The goal: IC returns > Borrowing cost
    Example: If IC bots return 3% monthly and box costs 0.1% monthly,
    you net 2.9% on borrowed capital.
    """

    # Position identification
    position_id: str
    ticker: str                   # SPX or XSP

    # Leg details - all 4 legs of the box
    lower_strike: float
    upper_strike: float
    strike_width: float
    expiration: str
    dte_at_entry: int
    current_dte: int              # Updates daily

    # Individual leg symbols (OCC format)
    call_long_symbol: str         # Buy lower strike call
    call_short_symbol: str        # Sell upper strike call
    put_long_symbol: str          # Buy upper strike put
    put_short_symbol: str         # Sell lower strike put

    # Order IDs from Tradier
    call_spread_order_id: str
    put_spread_order_id: str

    # Execution prices
    contracts: int
    entry_credit: float           # Credit received per contract
    total_credit_received: float  # entry_credit × contracts × 100
    theoretical_value: float      # What you'll "owe" at expiration
    total_owed_at_expiration: float  # theoretical_value × contracts × 100

    # Borrowing cost tracking - CORE TRANSPARENCY
    borrowing_cost: float         # total_owed - total_received
    implied_annual_rate: float    # Annualized rate at entry
    daily_cost: float             # borrowing_cost / dte
    cost_accrued_to_date: float   # Tracks cost as time passes

    # Comparison benchmarks
    fed_funds_at_entry: float
    margin_rate_at_entry: float
    savings_vs_margin: float      # What you saved vs margin loan

    # Capital deployment tracking - WHERE DID THE CASH GO?
    cash_deployed_to_ares: float
    cash_deployed_to_titan: float
    cash_deployed_to_pegasus: float
    cash_held_in_reserve: float
    total_cash_deployed: float

    # Returns from deployed capital - THE PAYOFF
    returns_from_ares: float
    returns_from_titan: float
    returns_from_pegasus: float
    total_ic_returns: float
    net_profit: float             # total_ic_returns - borrowing_cost

    # Market context at entry
    spot_at_entry: float
    vix_at_entry: float

    # Risk monitoring
    early_assignment_risk: str
    current_margin_used: float
    margin_cushion: float         # How much margin buffer remains

    # Status tracking
    status: PositionStatus
    open_time: datetime
    close_time: Optional[datetime] = None
    close_reason: str = ""

    # Educational annotations
    position_explanation: str = ""     # What this position represents
    daily_briefing: str = ""          # Updated daily with status

    # Audit trail
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary with full transparency"""
        return {
            'position_id': self.position_id,
            'ticker': self.ticker,
            'lower_strike': self.lower_strike,
            'upper_strike': self.upper_strike,
            'strike_width': self.strike_width,
            'expiration': self.expiration,
            'dte_at_entry': self.dte_at_entry,
            'current_dte': self.current_dte,
            'contracts': self.contracts,
            'entry_credit': self.entry_credit,
            'total_credit_received': self.total_credit_received,
            'theoretical_value': self.theoretical_value,
            'total_owed_at_expiration': self.total_owed_at_expiration,
            'borrowing_cost': self.borrowing_cost,
            'implied_annual_rate': self.implied_annual_rate,
            'daily_cost': self.daily_cost,
            'cost_accrued_to_date': self.cost_accrued_to_date,
            'fed_funds_at_entry': self.fed_funds_at_entry,
            'margin_rate_at_entry': self.margin_rate_at_entry,
            'savings_vs_margin': self.savings_vs_margin,
            'cash_deployed_to_ares': self.cash_deployed_to_ares,
            'cash_deployed_to_titan': self.cash_deployed_to_titan,
            'cash_deployed_to_pegasus': self.cash_deployed_to_pegasus,
            'cash_held_in_reserve': self.cash_held_in_reserve,
            'total_cash_deployed': self.total_cash_deployed,
            'returns_from_ares': self.returns_from_ares,
            'returns_from_titan': self.returns_from_titan,
            'returns_from_pegasus': self.returns_from_pegasus,
            'total_ic_returns': self.total_ic_returns,
            'net_profit': self.net_profit,
            'spot_at_entry': self.spot_at_entry,
            'vix_at_entry': self.vix_at_entry,
            'early_assignment_risk': self.early_assignment_risk,
            'current_margin_used': self.current_margin_used,
            'margin_cushion': self.margin_cushion,
            'status': self.status.value,
            'open_time': self.open_time.isoformat() if self.open_time else None,
            'close_time': self.close_time.isoformat() if self.close_time else None,
            'close_reason': self.close_reason,
            'position_explanation': self.position_explanation,
            'daily_briefing': self.daily_briefing,
        }


@dataclass
class BorrowingCostAnalysis:
    """
    Detailed analysis of borrowing costs for transparency.

    EDUCATIONAL NOTE - Why This Matters:
    ====================================
    Box spread borrowing is only profitable if:
    1. The implied rate is lower than your broker's margin rate
    2. You can deploy the cash at higher returns (IC premiums)
    3. Early assignment risk is managed (use European-style SPX)

    This analysis shows the complete cost breakdown.
    """

    analysis_time: datetime

    # Current rates comparison
    box_implied_rate: float       # What box spread costs (annualized)
    fed_funds_rate: float         # Risk-free benchmark
    sofr_rate: float              # Secured overnight rate
    broker_margin_rate: float     # What broker charges

    # Rate differentials
    spread_to_fed_funds: float    # Box rate - Fed Funds (should be small)
    spread_to_margin: float       # Box rate - Margin rate (should be negative = savings)

    # Cost projections
    cost_per_100k_monthly: float  # Borrowing cost per $100K per month
    cost_per_100k_annual: float   # Borrowing cost per $100K per year

    # Break-even analysis
    required_ic_return_monthly: float  # What IC bots need to return to break even
    current_ic_return_estimate: float  # Estimated IC returns based on history
    projected_profit_per_100k: float   # Estimated profit per $100K borrowed

    # Historical comparison
    avg_box_rate_30d: float       # 30-day average box spread rate
    avg_box_rate_90d: float       # 90-day average
    rate_trend: str               # RISING/FALLING/STABLE

    # Recommendation
    is_favorable: bool            # Should we borrow via box spreads now?
    recommendation: str           # Plain English recommendation
    reasoning: str                # Why this recommendation

    # Rate source tracking
    rates_source: str = "unknown"      # 'live', 'cached', or 'fallback'
    rates_last_updated: datetime = None  # When rates were last fetched

    def to_dict(self) -> Dict[str, Any]:
        return {
            'analysis_time': self.analysis_time.isoformat(),
            'box_implied_rate': self.box_implied_rate,
            'fed_funds_rate': self.fed_funds_rate,
            'sofr_rate': self.sofr_rate,
            'broker_margin_rate': self.broker_margin_rate,
            'spread_to_fed_funds': self.spread_to_fed_funds,
            'spread_to_margin': self.spread_to_margin,
            'cost_per_100k_monthly': self.cost_per_100k_monthly,
            'cost_per_100k_annual': self.cost_per_100k_annual,
            'required_ic_return_monthly': self.required_ic_return_monthly,
            'current_ic_return_estimate': self.current_ic_return_estimate,
            'projected_profit_per_100k': self.projected_profit_per_100k,
            'avg_box_rate_30d': self.avg_box_rate_30d,
            'avg_box_rate_90d': self.avg_box_rate_90d,
            'rate_trend': self.rate_trend,
            'is_favorable': self.is_favorable,
            'recommendation': self.recommendation,
            'reasoning': self.reasoning,
            'rates_source': self.rates_source,
            'rates_last_updated': self.rates_last_updated.isoformat() if self.rates_last_updated else None,
        }


@dataclass
class CapitalDeployment:
    """
    Tracks how box spread capital is deployed to IC bots.

    EDUCATIONAL NOTE - Capital Flow:
    ================================
    1. PROMETHEUS sells box spreads → receives cash
    2. Cash is allocated to IC bots based on:
       - Historical performance (better performers get more)
       - Current market conditions (some bots better in certain regimes)
       - Risk limits (no single bot gets too much)
    3. IC bots trade with this capital → generate returns
    4. At box expiration, returns are tallied against borrowing cost
    """

    deployment_id: str
    deployment_time: datetime
    source_box_position_id: str   # Which box spread funded this

    # Capital amounts
    total_capital_available: float

    # Allocation by bot
    ares_allocation: float
    ares_allocation_pct: float
    ares_allocation_reasoning: str

    titan_allocation: float
    titan_allocation_pct: float
    titan_allocation_reasoning: str

    pegasus_allocation: float
    pegasus_allocation_pct: float
    pegasus_allocation_reasoning: str

    reserve_amount: float
    reserve_pct: float
    reserve_reasoning: str

    # Allocation methodology
    allocation_method: str        # EQUAL, PERFORMANCE_WEIGHTED, REGIME_BASED
    methodology_explanation: str  # Why this allocation method

    # Performance tracking
    ares_returns_to_date: float
    titan_returns_to_date: float
    pegasus_returns_to_date: float
    total_returns_to_date: float

    # Status
    is_active: bool
    deactivation_reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            'deployment_id': self.deployment_id,
            'deployment_time': self.deployment_time.isoformat(),
            'source_box_position_id': self.source_box_position_id,
            'total_capital_available': self.total_capital_available,
            'allocations': {
                'ares': {
                    'amount': self.ares_allocation,
                    'pct': self.ares_allocation_pct,
                    'reasoning': self.ares_allocation_reasoning,
                    'returns': self.ares_returns_to_date,
                },
                'titan': {
                    'amount': self.titan_allocation,
                    'pct': self.titan_allocation_pct,
                    'reasoning': self.titan_allocation_reasoning,
                    'returns': self.titan_returns_to_date,
                },
                'pegasus': {
                    'amount': self.pegasus_allocation,
                    'pct': self.pegasus_allocation_pct,
                    'reasoning': self.pegasus_allocation_reasoning,
                    'returns': self.pegasus_returns_to_date,
                },
                'reserve': {
                    'amount': self.reserve_amount,
                    'pct': self.reserve_pct,
                    'reasoning': self.reserve_reasoning,
                },
            },
            'allocation_method': self.allocation_method,
            'methodology_explanation': self.methodology_explanation,
            'total_returns_to_date': self.total_returns_to_date,
            'is_active': self.is_active,
        }


@dataclass
class PrometheusConfig:
    """
    PROMETHEUS configuration with educational annotations.

    EDUCATIONAL NOTE - Key Parameters:
    ==================================
    - ticker: SPX preferred (European-style = no early assignment)
    - strike_width: Wider = more cash but more margin
    - target_dte: Longer = better rates but capital tied up longer
    - max_margin_pct: Never use more than X% of available margin
    """

    # Basic settings
    mode: TradingMode = TradingMode.PAPER
    ticker: str = "SPX"           # SPX (European) strongly preferred over SPY

    # Strike selection
    strike_width: float = 50.0    # $50 width for SPX (5000 per contract)
    min_strike_width: float = 20.0
    max_strike_width: float = 100.0

    # Strike distance from current price
    strike_distance_pct: float = 0.5  # Strikes 0.5% from current price
    prefer_round_strikes: bool = True  # Use round numbers (5900, 5950)

    # Expiration preferences
    target_dte_min: int = 180     # At least 6 months out
    target_dte_max: int = 365     # Up to 1 year out
    prefer_quarterly_expiry: bool = True  # March, June, Sept, Dec

    # Rate thresholds
    max_implied_rate: float = 6.0  # Don't borrow if rate > 6%
    min_rate_advantage: float = 100  # Min 100 bps savings vs margin

    # Position sizing
    capital: float = 500000.0     # Total capital for box spreads
    max_position_size: float = 250000.0  # Max per position
    max_total_exposure: float = 1000000.0  # Max total borrowed
    max_contracts_per_position: int = 50

    # Margin management
    max_margin_pct: float = 50.0  # Never use more than 50% of margin
    margin_buffer_pct: float = 20.0  # Keep 20% margin buffer

    # Capital deployment to IC bots
    ares_allocation_pct: float = 35.0
    titan_allocation_pct: float = 35.0
    pegasus_allocation_pct: float = 20.0
    reserve_pct: float = 10.0

    # Risk management
    max_positions: int = 5        # Max simultaneous box positions
    min_dte_to_hold: int = 30     # Roll if DTE < 30
    assignment_check_frequency: str = "daily"

    # Trading window (SPX opens at 8:30 AM CT)
    entry_start: str = "08:30"    # 8:30 AM CT - market open
    entry_end: str = "15:00"      # 3 PM CT

    # Educational mode
    educational_mode: bool = True  # Extra explanations in all outputs
    show_math_details: bool = True  # Show calculation breakdowns

    def to_dict(self) -> Dict[str, Any]:
        return {
            'mode': self.mode.value,
            'ticker': self.ticker,
            'strike_width': self.strike_width,
            'min_strike_width': self.min_strike_width,
            'max_strike_width': self.max_strike_width,
            'strike_distance_pct': self.strike_distance_pct,
            'prefer_round_strikes': self.prefer_round_strikes,
            'target_dte_min': self.target_dte_min,
            'target_dte_max': self.target_dte_max,
            'prefer_quarterly_expiry': self.prefer_quarterly_expiry,
            'max_implied_rate': self.max_implied_rate,
            'min_rate_advantage': self.min_rate_advantage,
            'capital': self.capital,
            'max_position_size': self.max_position_size,
            'max_total_exposure': self.max_total_exposure,
            'max_contracts_per_position': self.max_contracts_per_position,
            'max_margin_pct': self.max_margin_pct,
            'margin_buffer_pct': self.margin_buffer_pct,
            'allocations': {
                'ares_pct': self.ares_allocation_pct,
                'titan_pct': self.titan_allocation_pct,
                'pegasus_pct': self.pegasus_allocation_pct,
                'reserve_pct': self.reserve_pct,
            },
            'max_positions': self.max_positions,
            'min_dte_to_hold': self.min_dte_to_hold,
            'assignment_check_frequency': self.assignment_check_frequency,
            'entry_start': self.entry_start,
            'entry_end': self.entry_end,
            'educational_mode': self.educational_mode,
            'show_math_details': self.show_math_details,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PrometheusConfig':
        """Create config from dictionary"""
        config = cls()
        if 'mode' in data:
            config.mode = TradingMode(data['mode'])
        for key, value in data.items():
            if key == 'mode':
                continue
            if key == 'allocations':
                config.ares_allocation_pct = value.get('ares_pct', 35.0)
                config.titan_allocation_pct = value.get('titan_pct', 35.0)
                config.pegasus_allocation_pct = value.get('pegasus_pct', 20.0)
                config.reserve_pct = value.get('reserve_pct', 10.0)
            elif hasattr(config, key):
                setattr(config, key, value)
        return config


@dataclass
class RollDecision:
    """
    Decision to roll a box spread to a new expiration.

    EDUCATIONAL NOTE - When to Roll:
    ================================
    Roll when:
    1. DTE is getting low (< 30 days)
    2. A better rate is available at longer expiration
    3. You want to extend the borrowing period

    Rolling involves:
    1. Closing current box spread
    2. Opening new box spread at later expiration
    3. Adjusting for any rate difference
    """

    decision_time: datetime
    current_position_id: str

    # Current position details
    current_expiration: str
    current_dte: int
    current_implied_rate: float

    # Roll target
    target_expiration: str
    target_dte: int
    target_implied_rate: float

    # Cost analysis
    roll_cost: float              # Cost to close current + open new
    rate_improvement: float       # New rate - old rate (negative = better)
    total_borrowing_extension: int  # How many more days of borrowing

    # Decision
    should_roll: bool
    decision_reasoning: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            'decision_time': self.decision_time.isoformat(),
            'current_position_id': self.current_position_id,
            'current_expiration': self.current_expiration,
            'current_dte': self.current_dte,
            'current_implied_rate': self.current_implied_rate,
            'target_expiration': self.target_expiration,
            'target_dte': self.target_dte,
            'target_implied_rate': self.target_implied_rate,
            'roll_cost': self.roll_cost,
            'rate_improvement': self.rate_improvement,
            'total_borrowing_extension': self.total_borrowing_extension,
            'should_roll': self.should_roll,
            'decision_reasoning': self.decision_reasoning,
        }


@dataclass
class DailyBriefing:
    """
    Daily status briefing for PROMETHEUS system.

    EDUCATIONAL NOTE:
    =================
    This is your daily snapshot of how the box spread
    synthetic borrowing strategy is performing.
    """

    briefing_date: date
    briefing_time: datetime

    # Overall status
    system_status: BoxSpreadStatus

    # Position summary
    total_open_positions: int
    total_borrowed_amount: float
    total_cash_deployed: float
    total_margin_used: float
    margin_remaining: float

    # Cost tracking
    total_borrowing_cost_to_date: float
    average_borrowing_rate: float
    comparison_to_margin_rate: float  # Savings

    # IC performance from deployed capital
    total_ic_returns_to_date: float
    net_profit_to_date: float
    roi_on_strategy: float        # Net profit / total borrowed

    # Risk metrics
    highest_assignment_risk_position: str
    days_until_nearest_expiration: int

    # Rate environment
    current_box_rate: float
    rate_vs_yesterday: float
    rate_trend_7d: str

    # Recommendations
    recommended_actions: List[str]
    warnings: List[str]

    # Educational content
    daily_tip: str                # Educational tip about box spreads

    def to_dict(self) -> Dict[str, Any]:
        return {
            'briefing_date': self.briefing_date.isoformat(),
            'briefing_time': self.briefing_time.isoformat(),
            'system_status': self.system_status.value,
            'positions': {
                'total_open': self.total_open_positions,
                'total_borrowed': self.total_borrowed_amount,
                'total_deployed': self.total_cash_deployed,
            },
            'margin': {
                'used': self.total_margin_used,
                'remaining': self.margin_remaining,
            },
            'costs': {
                'total_borrowing_cost': self.total_borrowing_cost_to_date,
                'avg_rate': self.average_borrowing_rate,
                'vs_margin_rate': self.comparison_to_margin_rate,
            },
            'returns': {
                'ic_returns': self.total_ic_returns_to_date,
                'net_profit': self.net_profit_to_date,
                'roi': self.roi_on_strategy,
            },
            'risk': {
                'highest_assignment_risk': self.highest_assignment_risk_position,
                'days_to_nearest_expiry': self.days_until_nearest_expiration,
            },
            'rates': {
                'current': self.current_box_rate,
                'vs_yesterday': self.rate_vs_yesterday,
                'trend_7d': self.rate_trend_7d,
            },
            'actions': {
                'recommendations': self.recommended_actions,
                'warnings': self.warnings,
            },
            'education': {
                'daily_tip': self.daily_tip,
            },
        }


# ==============================================================================
# PROMETHEUS IC TRADING MODELS
# ==============================================================================
# These models support PROMETHEUS's own Iron Condor trading using borrowed capital.
# Instead of deploying to ARES/TITAN/PEGASUS, PROMETHEUS trades its own ICs.
# ==============================================================================


class ICPositionStatus(Enum):
    """Iron Condor position lifecycle states"""
    PENDING = "pending"          # Order submitted, awaiting fill
    OPEN = "open"                # Position is active
    CLOSING = "closing"          # Close order submitted
    CLOSED = "closed"            # Position fully closed
    EXPIRED = "expired"          # Let expire worthless (ideal outcome)
    STOPPED_OUT = "stopped_out"  # Hit stop loss


@dataclass
class PrometheusICSignal:
    """
    A signal to open an Iron Condor position using borrowed capital.

    EDUCATIONAL NOTE - Iron Condor Basics:
    ======================================
    An Iron Condor is a neutral options strategy that profits when the
    underlying stays within a range. It consists of:

    1. Sell OTM Put (lower strike) - collect premium
    2. Buy further OTM Put (protection) - pay premium
    3. Sell OTM Call (upper strike) - collect premium
    4. Buy further OTM Call (protection) - pay premium

    Max Profit: Net credit received (if price stays between short strikes)
    Max Loss: Width of spread - credit received (if price breaks through)

    PROMETHEUS uses borrowed capital to trade ICs, aiming to earn more
    from IC premium than the cost of borrowing via box spreads.
    """

    # Signal identification
    signal_id: str
    signal_time: datetime
    source_box_position_id: str   # Which box spread is funding this trade

    # Underlying details
    ticker: str                   # SPX (same as box spread for simplicity)
    spot_price: float             # Current underlying price

    # Put spread (lower side)
    put_short_strike: float       # Sell this put
    put_long_strike: float        # Buy this put (protection)
    put_spread_width: float       # Difference

    # Call spread (upper side)
    call_short_strike: float      # Sell this call
    call_long_strike: float       # Buy this call (protection)
    call_spread_width: float      # Difference

    # Expiration
    expiration: str               # Target expiration date (YYYY-MM-DD)
    dte: int                      # Days to expiration (0-7 typically)

    # Pricing
    put_spread_credit: float      # Credit from put spread
    call_spread_credit: float     # Credit from call spread
    total_credit: float           # Net credit received
    max_loss: float               # If breached

    # Risk metrics
    probability_of_profit: float  # Estimated PoP
    delta_of_short_put: float     # Delta of short put
    delta_of_short_call: float    # Delta of short call

    # Position sizing
    contracts: int                # Number of contracts
    margin_required: float        # Margin for this position
    capital_at_risk: float        # Max loss × contracts

    # Oracle/SAGE recommendation
    oracle_approved: bool
    oracle_confidence: float
    oracle_reasoning: str

    # Market context
    vix_level: float
    gamma_regime: str             # POSITIVE/NEGATIVE/NEUTRAL
    gex_regime: str               # Market maker positioning

    # Validity
    is_valid: bool = True
    skip_reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            'signal_id': self.signal_id,
            'signal_time': self.signal_time.isoformat() if self.signal_time else None,
            'source_box_position_id': self.source_box_position_id,
            'ticker': self.ticker,
            'spot_price': self.spot_price,
            'put_spread': {
                'short_strike': self.put_short_strike,
                'long_strike': self.put_long_strike,
                'width': self.put_spread_width,
                'credit': self.put_spread_credit,
            },
            'call_spread': {
                'short_strike': self.call_short_strike,
                'long_strike': self.call_long_strike,
                'width': self.call_spread_width,
                'credit': self.call_spread_credit,
            },
            'expiration': self.expiration,
            'dte': self.dte,
            'total_credit': self.total_credit,
            'max_loss': self.max_loss,
            'probability_of_profit': self.probability_of_profit,
            'contracts': self.contracts,
            'margin_required': self.margin_required,
            'capital_at_risk': self.capital_at_risk,
            'oracle_approved': self.oracle_approved,
            'oracle_confidence': self.oracle_confidence,
            'oracle_reasoning': self.oracle_reasoning,
            'vix_level': self.vix_level,
            'gamma_regime': self.gamma_regime,
            'gex_regime': self.gex_regime,
            'is_valid': self.is_valid,
            'skip_reason': self.skip_reason,
        }


@dataclass
class PrometheusICPosition:
    """
    An active Iron Condor position traded with borrowed capital.

    EDUCATIONAL NOTE - Tracking IC Performance:
    ===========================================
    Each IC position is linked to a box spread position. The goal is:
    IC Returns > Box Spread Borrowing Cost

    Example:
    - Box spread borrowed $100K at 4.5% annual = $375/month cost
    - IC trades on that capital earn $2,000/month
    - Net profit = $2,000 - $375 = $1,625/month

    This position tracks the IC side of that equation.
    """

    # Position identification
    position_id: str
    source_box_position_id: str   # Which box spread funded this
    ticker: str                   # SPX

    # Leg details
    put_short_strike: float
    put_long_strike: float
    call_short_strike: float
    call_long_strike: float
    spread_width: float           # Width of each spread

    # Option symbols (OCC format)
    put_short_symbol: str
    put_long_symbol: str
    call_short_symbol: str
    call_long_symbol: str

    # Order IDs
    put_spread_order_id: str
    call_spread_order_id: str

    # Expiration
    expiration: str
    dte_at_entry: int
    current_dte: int

    # Execution
    contracts: int
    entry_credit: float           # Credit per contract (total IC)
    total_credit_received: float  # entry_credit × contracts × 100
    max_loss: float               # (spread_width - entry_credit) × contracts × 100

    # Current value (for mark-to-market)
    current_value: float          # What it would cost to close
    unrealized_pnl: float         # total_credit - current_value

    # Exit details
    exit_price: float = 0.0
    realized_pnl: float = 0.0

    # Market context at entry
    spot_at_entry: float = 0.0
    vix_at_entry: float = 0.0
    gamma_regime_at_entry: str = ""

    # Oracle decision context
    oracle_confidence_at_entry: float = 0.0
    oracle_reasoning: str = ""

    # Status
    status: ICPositionStatus = ICPositionStatus.OPEN
    open_time: datetime = None
    close_time: Optional[datetime] = None
    close_reason: str = ""

    # Risk management
    stop_loss_pct: float = 200.0  # Close if loss reaches 200% of credit
    profit_target_pct: float = 50.0  # Close if profit reaches 50% of credit
    time_stop_dte: int = 0        # Close at this DTE if still open

    # Audit trail
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'position_id': self.position_id,
            'source_box_position_id': self.source_box_position_id,
            'ticker': self.ticker,
            'put_spread': {
                'short_strike': self.put_short_strike,
                'long_strike': self.put_long_strike,
            },
            'call_spread': {
                'short_strike': self.call_short_strike,
                'long_strike': self.call_long_strike,
            },
            'spread_width': self.spread_width,
            'expiration': self.expiration,
            'dte_at_entry': self.dte_at_entry,
            'current_dte': self.current_dte,
            'contracts': self.contracts,
            'entry_credit': self.entry_credit,
            'total_credit_received': self.total_credit_received,
            'max_loss': self.max_loss,
            'current_value': self.current_value,
            'unrealized_pnl': self.unrealized_pnl,
            'exit_price': self.exit_price,
            'realized_pnl': self.realized_pnl,
            'spot_at_entry': self.spot_at_entry,
            'vix_at_entry': self.vix_at_entry,
            'gamma_regime_at_entry': self.gamma_regime_at_entry,
            'oracle_confidence_at_entry': self.oracle_confidence_at_entry,
            'oracle_reasoning': self.oracle_reasoning,
            'status': self.status.value,
            'open_time': self.open_time.isoformat() if self.open_time else None,
            'close_time': self.close_time.isoformat() if self.close_time else None,
            'close_reason': self.close_reason,
            'stop_loss_pct': self.stop_loss_pct,
            'profit_target_pct': self.profit_target_pct,
            'time_stop_dte': self.time_stop_dte,
        }


@dataclass
class PrometheusICConfig:
    """
    Configuration for PROMETHEUS IC trading.

    EDUCATIONAL NOTE - IC Trading Parameters:
    =========================================
    These settings control how PROMETHEUS trades Iron Condors
    using the capital borrowed via box spreads.

    The goal is to earn consistent premium while managing risk.
    """

    # Trading mode
    enabled: bool = True          # Enable IC trading
    mode: TradingMode = TradingMode.PAPER

    # Underlying
    ticker: str = "SPX"           # Trade SPX (matches box spreads)

    # Expiration preferences
    target_dte_min: int = 0       # 0DTE trading
    target_dte_max: int = 7       # Up to weekly
    prefer_0dte: bool = True      # Focus on 0DTE

    # Strike selection (delta-based)
    short_put_delta: float = 0.10   # ~10 delta for short put
    short_call_delta: float = 0.10  # ~10 delta for short call
    spread_width: float = 25.0      # $25 wide spreads on SPX

    # Position sizing
    max_positions: int = 3          # Max simultaneous IC positions
    max_capital_per_trade_pct: float = 10.0  # Max 10% of borrowed capital per trade
    max_daily_trades: int = 5       # Max trades per day

    # Risk management
    stop_loss_pct: float = 200.0    # Close if loss = 200% of credit
    profit_target_pct: float = 50.0 # Close if profit = 50% of credit
    time_stop_dte: int = 0          # Close at expiration

    # Oracle integration
    require_oracle_approval: bool = True
    min_oracle_confidence: float = 0.6
    min_win_probability: float = 0.50

    # VIX filters
    min_vix: float = 12.0         # Don't trade if VIX too low (thin premiums)
    max_vix: float = 35.0         # Don't trade if VIX too high (too risky)

    # Trading window
    entry_start: str = "08:35"    # 8:35 AM CT
    entry_end: str = "14:30"      # 2:30 PM CT (stop new trades before close)
    exit_by: str = "15:00"        # Exit all by 3:00 PM CT

    # Cooldown
    cooldown_after_loss_minutes: int = 30  # Wait after a loss
    cooldown_after_win_minutes: int = 15   # Brief pause after win
    cooldown_minutes_after_trade: int = 15  # General cooldown (used by trader)

    # Capital tracking (for equity curve calculations)
    starting_capital: float = 500000.0      # Starting capital for IC trading (matches box spread capital)
    min_capital_per_trade: float = 5000.0   # Minimum capital required per trade

    @property
    def max_trades_per_day(self) -> int:
        """Alias for max_daily_trades for compatibility with trader code"""
        return self.max_daily_trades

    def to_dict(self) -> Dict[str, Any]:
        return {
            'enabled': self.enabled,
            'mode': self.mode.value,
            'ticker': self.ticker,
            'expiration': {
                'target_dte_min': self.target_dte_min,
                'target_dte_max': self.target_dte_max,
                'prefer_0dte': self.prefer_0dte,
            },
            'strikes': {
                'short_put_delta': self.short_put_delta,
                'short_call_delta': self.short_call_delta,
                'spread_width': self.spread_width,
            },
            'sizing': {
                'max_positions': self.max_positions,
                'max_capital_per_trade_pct': self.max_capital_per_trade_pct,
                'max_daily_trades': self.max_daily_trades,
            },
            'risk': {
                'stop_loss_pct': self.stop_loss_pct,
                'profit_target_pct': self.profit_target_pct,
                'time_stop_dte': self.time_stop_dte,
            },
            'oracle': {
                'require_approval': self.require_oracle_approval,
                'min_confidence': self.min_oracle_confidence,
                'min_win_probability': self.min_win_probability,
            },
            'vix_filters': {
                'min_vix': self.min_vix,
                'max_vix': self.max_vix,
            },
            'trading_window': {
                'entry_start': self.entry_start,
                'entry_end': self.entry_end,
                'exit_by': self.exit_by,
            },
            'cooldown': {
                'after_loss_minutes': self.cooldown_after_loss_minutes,
                'after_win_minutes': self.cooldown_after_win_minutes,
                'minutes_after_trade': self.cooldown_minutes_after_trade,
            },
            'capital': {
                'starting_capital': self.starting_capital,
                'min_per_trade': self.min_capital_per_trade,
            },
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PrometheusICConfig':
        """Create config from dictionary"""
        config = cls()
        if 'mode' in data:
            config.mode = TradingMode(data['mode'])
        if 'enabled' in data:
            config.enabled = data['enabled']

        # Handle nested structures
        if 'expiration' in data:
            config.target_dte_min = data['expiration'].get('target_dte_min', 0)
            config.target_dte_max = data['expiration'].get('target_dte_max', 7)
            config.prefer_0dte = data['expiration'].get('prefer_0dte', True)

        if 'strikes' in data:
            config.short_put_delta = data['strikes'].get('short_put_delta', 0.10)
            config.short_call_delta = data['strikes'].get('short_call_delta', 0.10)
            config.spread_width = data['strikes'].get('spread_width', 25.0)

        if 'sizing' in data:
            config.max_positions = data['sizing'].get('max_positions', 3)
            config.max_capital_per_trade_pct = data['sizing'].get('max_capital_per_trade_pct', 10.0)
            config.max_daily_trades = data['sizing'].get('max_daily_trades', 5)

        if 'risk' in data:
            config.stop_loss_pct = data['risk'].get('stop_loss_pct', 200.0)
            config.profit_target_pct = data['risk'].get('profit_target_pct', 50.0)
            config.time_stop_dte = data['risk'].get('time_stop_dte', 0)

        if 'oracle' in data:
            config.require_oracle_approval = data['oracle'].get('require_approval', True)
            config.min_oracle_confidence = data['oracle'].get('min_confidence', 0.6)
            config.min_win_probability = data['oracle'].get('min_win_probability', 0.50)

        return config


@dataclass
class PrometheusPerformanceSummary:
    """
    Combined performance summary for PROMETHEUS system.

    Shows both box spread (borrowing) and IC trading (returns) performance.
    """

    summary_time: datetime

    # Box Spread Performance (Capital Raising Side)
    total_box_positions: int
    total_borrowed: float
    total_borrowing_cost: float
    average_borrowing_rate: float
    borrowing_cost_to_date: float

    # IC Trading Performance (Returns Side)
    total_ic_trades: int
    ic_win_rate: float
    total_ic_premium_collected: float
    total_ic_realized_pnl: float
    total_ic_unrealized_pnl: float
    average_ic_return_per_trade: float

    # Combined Performance
    net_profit: float             # IC returns - borrowing costs
    roi_on_borrowed_capital: float  # Net profit / total borrowed
    monthly_return_rate: float    # Annualized return rate

    # Risk Metrics
    max_drawdown: float
    sharpe_ratio: float
    win_streak: int
    loss_streak: int

    # Comparison
    vs_margin_borrowing: float    # What you saved vs margin loan
    vs_buy_and_hold_spx: float    # Performance vs just holding SPX

    def to_dict(self) -> Dict[str, Any]:
        return {
            'summary_time': self.summary_time.isoformat(),
            'box_spread': {
                'total_positions': self.total_box_positions,
                'total_borrowed': self.total_borrowed,
                'total_cost': self.total_borrowing_cost,
                'avg_rate': self.average_borrowing_rate,
                'cost_to_date': self.borrowing_cost_to_date,
            },
            'ic_trading': {
                'total_trades': self.total_ic_trades,
                'win_rate': self.ic_win_rate,
                'premium_collected': self.total_ic_premium_collected,
                'realized_pnl': self.total_ic_realized_pnl,
                'unrealized_pnl': self.total_ic_unrealized_pnl,
                'avg_return_per_trade': self.average_ic_return_per_trade,
            },
            'combined': {
                'net_profit': self.net_profit,
                'roi': self.roi_on_borrowed_capital,
                'monthly_return': self.monthly_return_rate,
            },
            'risk': {
                'max_drawdown': self.max_drawdown,
                'sharpe_ratio': self.sharpe_ratio,
                'win_streak': self.win_streak,
                'loss_streak': self.loss_streak,
            },
            'comparison': {
                'vs_margin': self.vs_margin_borrowing,
                'vs_buy_hold': self.vs_buy_and_hold_spx,
            },
        }

