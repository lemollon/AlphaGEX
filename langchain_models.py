"""
LangChain Pydantic Models for AlphaGEX

This module defines structured output models for LangChain integration,
ensuring type-safe and validated responses from Claude AI.
"""

from pydantic import BaseModel, Field, validator
from typing import Optional, List, Literal
from datetime import date, datetime
from enum import Enum


# ============================================================================
# ENUMS FOR TYPE SAFETY
# ============================================================================

class OptionType(str, Enum):
    """Option type enumeration"""
    CALL = "call"
    PUT = "put"


class MarketMakerState(str, Enum):
    """Market Maker behavioral states"""
    PANICKING = "PANICKING"  # < -$3B GEX
    TRAPPED = "TRAPPED"      # -$3B to -$2B
    HUNTING = "HUNTING"      # -$2B to -$1B
    DEFENDING = "DEFENDING"  # +$1B to +$2B
    NEUTRAL = "NEUTRAL"      # -$1B to +$1B


class StrategyType(str, Enum):
    """Trading strategy types"""
    NEGATIVE_GEX_SQUEEZE = "NEGATIVE_GEX_SQUEEZE"
    POSITIVE_GEX_BREAKDOWN = "POSITIVE_GEX_BREAKDOWN"
    FLIP_POINT_EXPLOSION = "FLIP_POINT_EXPLOSION"
    IRON_CONDOR = "IRON_CONDOR"
    PREMIUM_SELLING = "PREMIUM_SELLING"
    STRADDLE = "STRADDLE"
    STRANGLE = "STRANGLE"
    CALENDAR_SPREAD = "CALENDAR_SPREAD"
    WAIT = "WAIT"


class VolatilityRegime(str, Enum):
    """Volatility environment classification"""
    LOW = "LOW"           # VIX < 15
    NORMAL = "NORMAL"     # VIX 15-20
    ELEVATED = "ELEVATED" # VIX 20-30
    EXTREME = "EXTREME"   # VIX > 30


class RiskLevel(str, Enum):
    """Risk level classification"""
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    EXTREME = "EXTREME"


# ============================================================================
# TRADE RECOMMENDATION MODELS
# ============================================================================

class OptionLeg(BaseModel):
    """Single option leg in a trade"""
    option_type: OptionType = Field(..., description="Call or Put")
    strike: float = Field(..., gt=0, description="Strike price")
    expiration: date = Field(..., description="Expiration date")
    action: Literal["BUY", "SELL"] = Field(..., description="Buy to open or Sell to open")
    quantity: int = Field(..., ge=1, le=100, description="Number of contracts")
    entry_price: float = Field(..., gt=0, description="Target entry price per contract")

    @validator('expiration')
    def expiration_must_be_future(cls, v):
        """Ensure expiration is in the future"""
        if v < date.today():
            raise ValueError('Expiration date must be in the future')
        return v


class TradeRecommendation(BaseModel):
    """Structured trade recommendation from Claude AI"""

    # Basic identification
    symbol: str = Field(..., pattern="^[A-Z]{1,5}$", description="Ticker symbol (e.g., SPY, QQQ)")
    strategy_type: StrategyType = Field(..., description="The strategy being recommended")

    # Option legs (can be multi-leg for spreads)
    legs: List[OptionLeg] = Field(..., min_items=1, max_items=4, description="Option legs in the trade")

    # Pricing and exits
    max_entry_price: float = Field(..., gt=0, description="Maximum price to pay for the spread")
    target_price: float = Field(..., gt=0, description="Target exit price (profit taking)")
    stop_loss: float = Field(..., gt=0, description="Stop loss price")

    # Position sizing
    recommended_contracts: int = Field(..., ge=1, le=100, description="Recommended number of contracts")
    max_risk_dollars: float = Field(..., gt=0, description="Maximum $ risk on this trade")
    account_allocation_pct: float = Field(..., ge=0, le=100, description="% of account to allocate")

    # Trade rationale
    market_maker_state: MarketMakerState = Field(..., description="Current MM state driving this trade")
    edge_description: str = Field(..., min_length=50, description="Why this trade has an edge")
    key_levels: dict = Field(..., description="Key price levels (flip, walls, support/resistance)")

    # Risk metrics
    confidence: float = Field(..., ge=0, le=1, description="Confidence score 0-1")
    win_probability: float = Field(..., ge=0, le=1, description="Estimated probability of profit")
    risk_reward_ratio: float = Field(..., gt=0, description="Expected R:R ratio")
    max_loss_pct: float = Field(..., ge=0, le=100, description="Maximum loss as % of position")

    # Timing
    entry_timing: str = Field(..., description="When to enter (e.g., 'immediately', 'on dip to $565')")
    exit_timing: str = Field(..., description="When to exit (e.g., 'by Wednesday 3PM', '50% profit')")
    hold_duration_days: int = Field(..., ge=0, le=30, description="Expected hold time in days")

    # Additional context
    warnings: List[str] = Field(default_factory=list, description="Risk warnings or concerns")
    catalysts: List[str] = Field(default_factory=list, description="Events that could impact trade")

    @validator('target_price')
    def target_must_be_profitable(cls, v, values):
        """Ensure target represents a profit"""
        if 'max_entry_price' in values:
            # For debit spreads, target should be higher
            if v <= values['max_entry_price']:
                raise ValueError('Target price must be higher than entry for debit spreads')
        return v

    @validator('risk_reward_ratio')
    def reasonable_risk_reward(cls, v):
        """Ensure R:R ratio is reasonable"""
        if v < 0.1 or v > 10.0:
            raise ValueError('Risk:Reward ratio should be between 0.1 and 10.0')
        return v


# ============================================================================
# MARKET ANALYSIS MODELS
# ============================================================================

class GEXAnalysis(BaseModel):
    """Structured GEX analysis output"""

    # Core metrics
    net_gex: float = Field(..., description="Net dealer gamma exposure in billions")
    flip_point: float = Field(..., gt=0, description="Zero gamma crossover price")
    current_spot: float = Field(..., gt=0, description="Current underlying price")
    distance_to_flip_pct: float = Field(..., description="% distance to flip point")

    # Walls
    call_wall: float = Field(..., gt=0, description="Major call wall strike")
    put_wall: float = Field(..., gt=0, description="Major put wall strike")
    call_wall_strength: float = Field(..., ge=0, description="Gamma concentration at call wall (billions)")
    put_wall_strength: float = Field(..., ge=0, description="Gamma concentration at put wall (billions)")

    # State classification
    market_maker_state: MarketMakerState = Field(..., description="Current MM behavioral state")
    state_confidence: float = Field(..., ge=0, le=1, description="Confidence in state classification")

    # Gamma dynamics
    total_gamma_expiring_today: float = Field(..., ge=0, description="Gamma expiring today (billions)")
    gamma_decay_this_week_pct: float = Field(..., ge=0, le=100, description="% of gamma expiring this week")
    volatility_expansion_potential: RiskLevel = Field(..., description="Potential for vol expansion")

    # Interpretation
    dealer_positioning: str = Field(..., description="What dealers are doing")
    expected_behavior: str = Field(..., description="How dealers will likely behave")
    trading_implications: str = Field(..., min_length=100, description="What this means for trading")


class MarketRegimeAnalysis(BaseModel):
    """Complete market regime analysis"""

    # Volatility environment
    vix_level: float = Field(..., ge=0, description="Current VIX level")
    volatility_regime: VolatilityRegime = Field(..., description="Vol regime classification")

    # Economic context
    treasury_yield_10y: Optional[float] = Field(None, ge=0, description="10-year Treasury yield")
    fed_funds_rate: Optional[float] = Field(None, ge=0, description="Fed Funds rate")

    # GEX analysis
    gex_analysis: GEXAnalysis = Field(..., description="Detailed GEX analysis")

    # Overall assessment
    market_phase: str = Field(..., description="Overall market phase (e.g., 'Risk On', 'Risk Off')")
    dominant_theme: str = Field(..., description="Dominant market theme")
    overnight_risk: RiskLevel = Field(..., description="Risk of overnight gaps")

    # Day-of-week context
    day_of_week: str = Field(..., description="Current day of week")
    day_specific_guidance: str = Field(..., description="Day-specific trading rules")


# ============================================================================
# RISK ASSESSMENT MODELS
# ============================================================================

class RiskAssessment(BaseModel):
    """Risk assessment for a potential trade"""

    # Overall risk
    overall_risk_level: RiskLevel = Field(..., description="Overall risk classification")
    risk_score: float = Field(..., ge=0, le=100, description="Risk score 0-100")

    # Specific risks
    directional_risk: str = Field(..., description="Risk if market moves against position")
    volatility_risk: str = Field(..., description="Risk from IV expansion/contraction")
    time_decay_risk: str = Field(..., description="Theta risk assessment")
    gamma_risk: str = Field(..., description="Gamma exposure risk")

    # Scenario analysis
    best_case_return_pct: float = Field(..., description="Best case return %")
    expected_return_pct: float = Field(..., description="Expected return %")
    worst_case_loss_pct: float = Field(..., le=0, description="Worst case loss % (negative)")

    # Risk mitigation
    position_size_recommendation: str = Field(..., description="Position sizing guidance")
    hedge_suggestions: List[str] = Field(default_factory=list, description="Potential hedges")
    early_exit_triggers: List[str] = Field(..., min_items=1, description="When to exit early")

    # Approval
    trade_approved: bool = Field(..., description="Whether trade meets risk criteria")
    rejection_reason: Optional[str] = Field(None, description="Why trade was rejected (if applicable)")


# ============================================================================
# EDUCATIONAL MODELS
# ============================================================================

class ConceptExplanation(BaseModel):
    """Educational explanation of a trading concept"""

    concept_name: str = Field(..., description="Name of the concept")
    simple_explanation: str = Field(..., min_length=100, description="ELI5 explanation")
    detailed_explanation: str = Field(..., min_length=200, description="Detailed technical explanation")

    # Examples
    real_world_example: str = Field(..., description="Real market example")
    how_to_use_it: str = Field(..., description="Practical application")

    # Common mistakes
    common_mistakes: List[str] = Field(..., min_items=1, description="Common errors to avoid")

    # Further learning
    related_concepts: List[str] = Field(default_factory=list, description="Related concepts to learn")
    recommended_reading: List[str] = Field(default_factory=list, description="Resources for learning more")


class PsychologicalAssessment(BaseModel):
    """Psychological trading assessment"""

    # Red flags detected
    red_flags: List[str] = Field(default_factory=list, description="Behavioral red flags")
    severity: RiskLevel = Field(..., description="Severity of psychological issues")

    # Patterns identified
    emotional_state: str = Field(..., description="Current emotional state")
    trading_pattern: str = Field(..., description="Pattern in recent behavior")

    # Guidance
    recommended_action: str = Field(..., description="What to do right now")
    long_term_improvement: str = Field(..., description="How to improve going forward")

    # Urgency
    take_break: bool = Field(..., description="Whether to stop trading immediately")
    break_duration: Optional[str] = Field(None, description="How long to take a break")


# ============================================================================
# POST-TRADE ANALYSIS MODELS
# ============================================================================

class TradePostMortem(BaseModel):
    """Post-trade analysis"""

    # Trade basics
    trade_id: str = Field(..., description="Unique trade identifier")
    entry_date: date = Field(..., description="Entry date")
    exit_date: date = Field(..., description="Exit date")
    hold_duration_days: int = Field(..., ge=0, description="Days held")

    # Performance
    entry_price: float = Field(..., gt=0, description="Actual entry price")
    exit_price: float = Field(..., gt=0, description="Actual exit price")
    profit_loss_dollars: float = Field(..., description="P&L in dollars")
    profit_loss_pct: float = Field(..., description="P&L as %")

    # Analysis
    what_went_right: List[str] = Field(..., description="Positive aspects")
    what_went_wrong: List[str] = Field(default_factory=list, description="Mistakes or issues")
    edge_validation: str = Field(..., description="Did the edge play out as expected?")

    # Lessons
    key_lessons: List[str] = Field(..., min_items=1, description="Lessons learned")
    behavioral_notes: str = Field(..., description="Psychological observations")

    # Future application
    would_take_again: bool = Field(..., description="Would you take this trade again?")
    what_to_change: str = Field(..., description="What would you do differently?")
    pattern_to_remember: str = Field(..., description="Pattern to remember for future")


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def validate_trade_recommendation(recommendation: dict) -> TradeRecommendation:
    """
    Validate and parse a trade recommendation from Claude

    Args:
        recommendation: Dictionary from Claude's response

    Returns:
        Validated TradeRecommendation object

    Raises:
        ValidationError: If recommendation doesn't meet requirements
    """
    return TradeRecommendation(**recommendation)


def validate_market_analysis(analysis: dict) -> MarketRegimeAnalysis:
    """
    Validate and parse market analysis from Claude

    Args:
        analysis: Dictionary from Claude's response

    Returns:
        Validated MarketRegimeAnalysis object

    Raises:
        ValidationError: If analysis doesn't meet requirements
    """
    return MarketRegimeAnalysis(**analysis)
