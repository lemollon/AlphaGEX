"""
AlphaGEX Configuration File
===========================

All tunable parameters, thresholds, and constants in one place.
Modify these values to adjust system behavior without changing core code.

Last updated: 2025-11-27
"""

from typing import Dict, List, Optional, Any
import os


class VIXConfig:
    """VIX-related configuration"""

    # Default VIX value (used only if fetch completely fails AND no historical data)
    # Use 18.0 - consistent across entire app (historical average)
    DEFAULT_VIX = 18.0

    # Historical VIX averages for better fallback
    HISTORICAL_AVERAGE_VIX = 16.5  # Long-term average (~2000-2024)
    RECENT_AVERAGE_VIX = 18.0      # Recent 5-year average

    # VIX regime thresholds
    LOW_VIX_THRESHOLD = 15.0       # Below this = low volatility
    ELEVATED_VIX_THRESHOLD = 20.0  # Above this = elevated volatility
    HIGH_VIX_THRESHOLD = 30.0      # Above this = high volatility
    EXTREME_VIX_THRESHOLD = 40.0   # Above this = extreme volatility


class GammaDecayConfig:
    """Weekly gamma decay patterns"""

    # DEFAULT: Front-loaded decay pattern (typical for 0DTE-heavy weeks)
    # These represent the fraction of Monday's gamma remaining on each day
    FRONT_LOADED_PATTERN = {
        0: 1.00,  # Monday - 100% of weekly gamma
        1: 0.71,  # Tuesday - 71% remaining (29% decay)
        2: 0.42,  # Wednesday - 42% remaining (58% total decay)
        3: 0.12,  # Thursday - 12% remaining (88% total decay)
        4: 0.08   # Friday - 8% remaining (92% total decay)
    }

    # BALANCED: More gradual decay (for weeks with less 0DTE activity)
    BALANCED_PATTERN = {
        0: 1.00,  # Monday - 100%
        1: 0.80,  # Tuesday - 80%
        2: 0.60,  # Wednesday - 60%
        3: 0.35,  # Thursday - 35%
        4: 0.15   # Friday - 15%
    }

    # BACK_LOADED: Gamma concentrated late in week
    BACK_LOADED_PATTERN = {
        0: 1.00,  # Monday - 100%
        1: 0.90,  # Tuesday - 90%
        2: 0.75,  # Wednesday - 75%
        3: 0.50,  # Thursday - 50%
        4: 0.20   # Friday - 20%
    }

    # Which pattern to use (can be changed dynamically)
    ACTIVE_PATTERN = FRONT_LOADED_PATTERN

    # Auto-select pattern based on conditions
    USE_ADAPTIVE_PATTERN = True  # If True, system selects pattern based on market


class GEXThresholdConfig:
    """GEX (Gamma Exposure) threshold configuration - ADAPTIVE"""

    # ===== ADAPTIVE MODE =====
    # When enabled, thresholds scale based on current market GEX magnitude
    USE_ADAPTIVE_THRESHOLDS = True

    # Adaptive thresholds as MULTIPLES of average GEX
    # Example: If avg GEX is $5B, EXTREME would be 5B * 0.6 = $3B
    ADAPTIVE_MULTIPLIERS = {
        'extreme_negative': -0.6,  # -60% of average = extreme short gamma
        'high_negative': -0.4,     # -40% of average = high short gamma
        'moderate_negative': -0.2, # -20% of average = moderate short gamma
        'moderate_positive': 0.2,  # +20% of average = moderate long gamma
        'high_positive': 0.4,      # +40% of average = high long gamma
        'extreme_positive': 0.6    # +60% of average = extreme long gamma
    }

    # ===== FIXED MODE (Fallback) =====
    # Used when adaptive mode is disabled or no historical data available
    FIXED_THRESHOLDS = {
        'extreme_negative': -3e9,  # -$3B
        'high_negative': -2e9,     # -$2B
        'moderate_negative': -1e9, # -$1B
        'moderate_positive': 1e9,  # +$1B
        'high_positive': 2e9,      # +$2B
        'extreme_positive': 3e9    # +$3B
    }

    # Rolling average period for adaptive thresholds (trading days)
    ADAPTIVE_LOOKBACK_DAYS = 20  # 20 trading days ≈ 1 month


class DirectionalPredictionConfig:
    """Directional prediction scoring configuration"""

    # Scoring weights (must sum to 100%)
    FACTOR_WEIGHTS = {
        'gex_regime': 0.40,      # 40% - GEX regime (short/long gamma)
        'wall_proximity': 0.30,  # 30% - Distance to call/put walls
        'vix_regime': 0.20,      # 20% - VIX level
        'day_of_week': 0.10      # 10% - Day of week effect
    }

    # Starting score (neutral)
    NEUTRAL_SCORE = 50

    # Direction thresholds
    UPWARD_THRESHOLD = 65    # Score >= 65 = UPWARD prediction
    DOWNWARD_THRESHOLD = 35  # Score <= 35 = DOWNWARD prediction
    # Between 35-65 = SIDEWAYS

    # Wall proximity threshold (percentage)
    WALL_PROXIMITY_THRESHOLD = 1.5  # Within 1.5% of wall = strong influence

    # GEX regime influence (points added/subtracted)
    GEX_REGIME_STRONG_INFLUENCE = 20  # Short gamma adjustment
    GEX_REGIME_MILD_INFLUENCE = 5     # Long gamma adjustment

    # Wall influence (points added/subtracted)
    WALL_INFLUENCE = 15

    # VIX dampening factors (pull score toward neutral)
    VIX_HIGH_DAMPENING = 0.7   # High VIX: multiply deviation by 0.7
    VIX_LOW_DAMPENING = 0.8    # Low VIX: multiply deviation by 0.8

    # Day of week dampening
    DAY_OF_WEEK_DAMPENING = 0.9  # Mon/Tue: multiply deviation by 0.9


class RiskLevelConfig:
    """Risk level classification thresholds"""

    # Daily risk levels (0-100 scale)
    DAILY_RISK_LEVELS = {
        'monday': 29,     # Low risk, max gamma
        'tuesday': 41,    # Moderate, gamma declining
        'wednesday': 70,  # High, major decay point
        'thursday': 38,   # Moderate, post-decay
        'friday': 100     # Extreme, final expiration
    }

    # Risk level thresholds
    EXTREME_RISK_THRESHOLD = 70
    HIGH_RISK_THRESHOLD = 50
    MODERATE_RISK_THRESHOLD = 30
    # Below 30 = LOW risk


class TradeSetupConfig:
    """Trade setup generation configuration"""

    # Spread width as percentage of spot price
    SPREAD_WIDTH_NORMAL = 0.015  # 1.5% for most stocks
    SPREAD_WIDTH_LOW_PRICE = 0.02  # 2% for stocks under $50
    LOW_PRICE_THRESHOLD = 50.0

    # Strike rounding increments by price
    STRIKE_INCREMENT_UNDER_20 = 0.5
    STRIKE_INCREMENT_20_TO_100 = 1.0
    STRIKE_INCREMENT_100_TO_200 = 2.5
    STRIKE_INCREMENT_OVER_200 = 5.0

    # Confidence thresholds
    MIN_CONFIDENCE_THRESHOLD = 0.65  # 65% minimum confidence
    MIN_WIN_RATE_THRESHOLD = 0.50    # 50% minimum win rate

    # Base confidence scores by strategy type
    BASE_CONFIDENCE = {
        'call_spread': 0.65,
        'put_spread': 0.62,
        'call_credit': 0.70,
        'put_credit': 0.68,
        'iron_condor': 0.72,
        'negative_gex_squeeze': 0.75,
        'straddle': 0.55
    }

    # Confidence adjustments
    CONFIDENCE_BOOST_GEX_EXTREME = 0.10
    CONFIDENCE_BOOST_NEAR_FLIP = 0.05
    CONFIDENCE_BOOST_WIDE_WALLS = 0.08


class RateLimitConfig:
    """API rate limiting configuration"""

    # Trading Volatility API limits
    # Official: 20 calls/minute = 3 seconds between calls
    # We use 4 seconds to be conservative
    MIN_REQUEST_INTERVAL = 4.0  # seconds between requests

    # Circuit breaker settings
    CIRCUIT_BREAKER_DURATION = 60  # seconds to wait when rate limited
    MAX_CONSECUTIVE_ERRORS = 3     # errors before circuit breaker activates

    # Cache duration
    CACHE_DURATION = 1800  # 30 minutes (in seconds)


class ImpliedVolatilityConfig:
    """Implied Volatility defaults and thresholds"""

    # Default IV when not available from API
    DEFAULT_IV = 0.20  # 20%

    # IV percentile thresholds
    LOW_IV_PERCENTILE = 25
    HIGH_IV_PERCENTILE = 75

    # IV regime thresholds (absolute)
    LOW_IV_THRESHOLD = 0.15   # 15%
    NORMAL_IV_THRESHOLD = 0.25  # 25%
    HIGH_IV_THRESHOLD = 0.40  # 40%
    EXTREME_IV_THRESHOLD = 0.60  # 60%


class SystemConfig:
    """System-wide configuration"""

    # Environment
    ENVIRONMENT = os.getenv('ENVIRONMENT', 'development')

    # API endpoints
    TRADINGVOLATILITY_API_BASE = 'https://api.tradingvolatility.net'

    # Logging
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')

    # Feature flags
    ENABLE_ADAPTIVE_GEX_THRESHOLDS = True
    ENABLE_ADAPTIVE_GAMMA_PATTERN = True
    ENABLE_HISTORICAL_VIX_FALLBACK = True

    # Performance
    MAX_CONCURRENT_API_CALLS = 5
    REQUEST_TIMEOUT = 120  # seconds


class OracleConfig:
    """
    Oracle Decision Authority Configuration

    ORACLE_IS_FINAL = True means:
    - Oracle win probability is the ONLY gate for trade execution
    - All other checks (ensemble, confidence, R:R, credit) are INFORMATIONAL ONLY
    - No system can veto Oracle's decision to trade

    This centralizes the authority model and prevents future code from
    accidentally adding blocking gates that override Oracle.
    """

    # MASTER SWITCH: When True, Oracle decision cannot be overridden
    # Set to False to enable traditional multi-gate blocking behavior
    ORACLE_IS_FINAL = True

    # Default win probability threshold (42% based on KRONOS backtests)
    DEFAULT_MIN_WIN_PROBABILITY = 0.42

    # When Oracle is final, these checks become WARNINGS only:
    # - Ensemble should_trade check
    # - Confidence threshold check
    # - Risk/Reward ratio check
    # - Minimum credit check
    # - Backtest validation check
    # - Position sizer validation


# ===== HELPER FUNCTIONS =====

def get_gex_thresholds(symbol: str = 'SPY', avg_gex: Optional[float] = None) -> Dict[str, float]:
    """
    Get GEX thresholds - adaptive or fixed based on configuration

    Args:
        symbol: Stock symbol
        avg_gex: Average GEX value (for adaptive thresholds)

    Returns:
        Dictionary of threshold names to dollar values
    """
    if GEXThresholdConfig.USE_ADAPTIVE_THRESHOLDS and avg_gex is not None:
        # Calculate adaptive thresholds
        return {
            name: abs(avg_gex) * multiplier
            for name, multiplier in GEXThresholdConfig.ADAPTIVE_MULTIPLIERS.items()
        }
    else:
        # Use fixed thresholds
        return GEXThresholdConfig.FIXED_THRESHOLDS.copy()


def get_gamma_decay_pattern(vix: Optional[float] = None, net_gex: Optional[float] = None) -> Dict[int, float]:
    """
    Get gamma decay pattern - adaptive or fixed based on configuration

    Args:
        vix: Current VIX level
        net_gex: Current net GEX

    Returns:
        Dictionary mapping day number (0=Mon) to remaining gamma fraction
    """
    if not GammaDecayConfig.USE_ADAPTIVE_PATTERN:
        return GammaDecayConfig.ACTIVE_PATTERN.copy()

    # Adaptive pattern selection logic
    # High VIX or negative GEX = more front-loaded decay
    # Low VIX or positive GEX = more balanced decay

    if vix is not None and vix > VIXConfig.HIGH_VIX_THRESHOLD:
        return GammaDecayConfig.FRONT_LOADED_PATTERN.copy()

    if net_gex is not None and net_gex < -2e9:
        return GammaDecayConfig.FRONT_LOADED_PATTERN.copy()

    if vix is not None and vix < VIXConfig.LOW_VIX_THRESHOLD:
        return GammaDecayConfig.BACK_LOADED_PATTERN.copy()

    # Default to balanced
    return GammaDecayConfig.BALANCED_PATTERN.copy()


def get_vix_fallback(last_known_vix: Optional[float] = None) -> float:
    """
    Get VIX fallback value when API fetch fails

    Args:
        last_known_vix: Last successfully fetched VIX value

    Returns:
        VIX value to use
    """
    if SystemConfig.ENABLE_HISTORICAL_VIX_FALLBACK:
        # Priority 1: Use last known good value (if recent)
        if last_known_vix is not None and last_known_vix > 0:
            return last_known_vix

        # Priority 2: Use recent historical average
        return VIXConfig.RECENT_AVERAGE_VIX

    # Priority 3: Use default
    return VIXConfig.DEFAULT_VIX


# ===== SIMULATION AND MODEL PARAMETERS =====

class SimulationConfig:
    """
    Configuration for simulation and model parameters.

    IMPORTANT: These values are used when real data is unavailable.
    Results from simulated data should NOT be used for trading decisions.

    All values documented with sources and typical ranges.
    """

    # ===== GEX LEVEL SIMULATION =====
    # Used in backtest_gex_strategies.py and backtest_options_strategies.py
    # when real Trading Volatility API data is unavailable

    # Flip point distance from current price (percentage)
    # Source: Empirical analysis of SPY options positioning
    # Typical range: 1-4% below current price
    # 2.5% represents median observed flip point distance
    FLIP_POINT_DISTANCE_PCT = 0.025  # 2.5% below current price

    # Call wall distance from current price (percentage)
    # Source: Analysis of SPY call OI concentration
    # Typical range: 1-3% above current price
    # 2% represents median observed call wall distance
    CALL_WALL_DISTANCE_PCT = 0.020  # 2% above current price

    # Put wall distance from current price (percentage)
    # Source: Analysis of SPY put OI concentration
    # Typical range: 1-4% below current price
    # 2.5% represents median observed put wall distance
    PUT_WALL_DISTANCE_PCT = 0.025  # 2.5% below current price

    # Net GEX simulation values (in billions)
    # Source: Historical SPY GEX data analysis
    # SPY GEX typically ranges from -20B to +20B
    # These are simplified heuristic values for simulation ONLY
    SIMULATED_GEX_HIGH_VOL = -5e9      # -$5B when volatility is high
    SIMULATED_GEX_LOW_VOL = 2e9        # +$2B when volatility is low
    SIMULATED_GEX_NEUTRAL = 0          # $0 when volatility is normal

    # Volatility threshold multipliers for GEX simulation
    # High vol = volatility > median * 1.5
    # Low vol = volatility < median * 0.7
    SIMULATED_GEX_HIGH_VOL_MULTIPLIER = 1.5
    SIMULATED_GEX_LOW_VOL_MULTIPLIER = 0.7


class GreeksModelConfig:
    """
    Configuration for options Greeks calculations.

    These values are used in core_classes_and_engines.py for gamma calculations.
    """

    # Risk-free rate (annualized)
    # Source: Federal Reserve fed funds rate
    # Updated: Should track current Fed policy rate
    # Current value based on Nov 2024 rates (adjust as rates change)
    RISK_FREE_RATE = 0.045  # 4.5% (update when Fed changes rates)

    # Base gamma calculation parameters
    # Source: Black-Scholes model adaptations for dealer gamma
    # These are model-specific tuning parameters

    # Gamma base value (unitless scaling factor)
    # Affects absolute gamma magnitude - validated against market data
    GAMMA_BASE = 0.05

    # Distance coefficient for ATM proximity effect
    # Higher values = faster gamma decay away from ATM
    # Typical range: 8-15
    GAMMA_DISTANCE_COEFFICIENT = 10

    # IV floor (minimum implied volatility for calculations)
    # Prevents division issues and unrealistic gamma spikes
    # Based on minimum observed IV for SPY options
    IV_FLOOR = 0.10  # 10% minimum IV

    # Time floor (minimum time to expiry in years)
    # Prevents extreme gamma values at expiration
    TIME_FLOOR_YEARS = 0.5 / 365  # 0.5 days minimum


class OptionsContractConfig:
    """
    Configuration for options contract parameters.

    These values affect strike selection, pricing, and position sizing.
    """

    # Strike selection parameters
    # OTM distance for typical setups (percentage from ATM)
    DEFAULT_OTM_DISTANCE_CALLS = 0.02   # 2% OTM for calls
    DEFAULT_OTM_DISTANCE_PUTS = 0.025   # 2.5% OTM for puts

    # Spread width as percentage of spot price
    DEFAULT_SPREAD_WIDTH_PCT = 0.015    # 1.5% for most setups
    MIN_SPREAD_WIDTH_POINTS = 1.0       # Minimum $1 spread width

    # DTE (days to expiration) preferences
    DEFAULT_DTE_MIN = 3                 # Minimum 3 DTE
    DEFAULT_DTE_MAX = 14                # Maximum 14 DTE for most strategies
    DTE_0DTE = 0                        # Same-day expiration
    DTE_WEEKLY = 5                      # Weekly options

    # Profit targets (percentage of max profit)
    DEFAULT_PROFIT_TARGET_PCT = 0.50    # 50% of max profit
    AGGRESSIVE_PROFIT_TARGET_PCT = 0.75 # 75% of max profit

    # Stop loss (percentage of max loss)
    DEFAULT_STOP_LOSS_PCT = 1.00        # 100% of max loss (let expire)
    TIGHT_STOP_LOSS_PCT = 0.50          # 50% of max loss

    # Trading days per year (for annualization)
    TRADING_DAYS_PER_YEAR = 252


# ===== CONFIGURATION VALIDATION =====

def validate_config() -> bool:
    """Validate configuration values. Raises ValueError if invalid."""
    errors: List[str] = []

    # Check that directional prediction weights sum to 100%
    total_weight = sum(DirectionalPredictionConfig.FACTOR_WEIGHTS.values())
    if abs(total_weight - 1.0) > 0.01:
        errors.append(f"Directional prediction weights sum to {total_weight}, not 1.0")

    # Check thresholds are in order
    if DirectionalPredictionConfig.DOWNWARD_THRESHOLD >= DirectionalPredictionConfig.UPWARD_THRESHOLD:
        errors.append("DOWNWARD_THRESHOLD must be less than UPWARD_THRESHOLD")

    # Check VIX thresholds
    if not (VIXConfig.LOW_VIX_THRESHOLD < VIXConfig.ELEVATED_VIX_THRESHOLD < VIXConfig.HIGH_VIX_THRESHOLD):
        errors.append("VIX thresholds must be in ascending order")

    if errors:
        raise ValueError(f"Configuration validation failed:\n" + "\n".join(errors))

    return True


# Validate on import
try:
    validate_config()
    print("✅ Configuration validated successfully")
except Exception as e:
    print(f"⚠️ Configuration validation warning: {e}")


# ===== EXPORT ALL CONFIGS =====
__all__ = [
    'VIXConfig',
    'GammaDecayConfig',
    'GEXThresholdConfig',
    'DirectionalPredictionConfig',
    'RiskLevelConfig',
    'TradeSetupConfig',
    'RateLimitConfig',
    'ImpliedVolatilityConfig',
    'SystemConfig',
    'SimulationConfig',
    'GreeksModelConfig',
    'OptionsContractConfig',
    'get_gex_thresholds',
    'get_gamma_decay_pattern',
    'get_vix_fallback',
    'validate_config'
]
