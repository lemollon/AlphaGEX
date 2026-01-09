"""
Scan Activity Logger - Comprehensive logging for EVERY bot scan

This module provides complete visibility into what each trading bot is doing
on every single scan. No more mystery - you'll see exactly:

1. WHEN the scan happened
2. WHAT market conditions were observed
3. WHAT signals were generated
4. WHY a trade was or wasn't taken
5. WHAT checks were performed and their results

Usage:
    from trading.scan_activity_logger import log_scan_activity, ScanOutcome

    # Log every scan - whether it trades or not
    log_scan_activity(
        bot_name="ARES",
        outcome=ScanOutcome.NO_TRADE,
        decision_summary="Oracle confidence too low (45%)",
        market_data={"underlying_price": 5980, "vix": 18.5},
        ...
    )
"""

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

# Texas Central Time
CENTRAL_TZ = ZoneInfo("America/Chicago")


class ScanOutcome(Enum):
    """Possible outcomes of a scan"""
    TRADED = "TRADED"                    # Trade was executed
    NO_TRADE = "NO_TRADE"               # Scan complete, no trade (conditions not met)
    SKIP = "SKIP"                       # Skipped intentionally (already traded, etc.)
    ERROR = "ERROR"                     # Error occurred during scan
    MARKET_CLOSED = "MARKET_CLOSED"     # Market is closed
    BEFORE_WINDOW = "BEFORE_WINDOW"     # Before trading window
    AFTER_WINDOW = "AFTER_WINDOW"       # After trading window
    UNAVAILABLE = "UNAVAILABLE"         # Bot/service unavailable


@dataclass
class CheckResult:
    """Result of a single check performed during scan"""
    check_name: str
    passed: bool
    value: str = ""
    threshold: str = ""
    reason: str = ""


@dataclass
class ScanActivity:
    """Complete record of a scan"""
    # Identification
    bot_name: str
    scan_id: str
    scan_number: int

    # Timing
    timestamp: datetime
    date: str
    time_ct: str

    # Outcome
    outcome: ScanOutcome
    action_taken: str
    decision_summary: str
    full_reasoning: str = ""

    # Market conditions
    underlying_price: float = 0
    underlying_symbol: str = ""
    vix: float = 0
    expected_move: float = 0

    # GEX context
    gex_regime: str = ""
    net_gex: float = 0
    call_wall: float = 0
    put_wall: float = 0
    distance_to_call_wall_pct: float = 0
    distance_to_put_wall_pct: float = 0

    # Signals
    signal_source: str = ""
    signal_direction: str = ""
    signal_confidence: float = 0
    signal_win_probability: float = 0

    # Oracle - FULL context for frontend visibility
    oracle_advice: str = ""
    oracle_reasoning: str = ""
    oracle_win_probability: float = 0
    oracle_confidence: float = 0
    oracle_top_factors: List[Dict] = field(default_factory=list)
    oracle_probabilities: Dict = field(default_factory=dict)
    oracle_suggested_strikes: Dict = field(default_factory=dict)
    oracle_thresholds: Dict = field(default_factory=dict)  # What thresholds were evaluated
    min_win_probability_threshold: float = 0  # What the bot required

    # Quant ML Advisor - ARES ML feedback loop (from quant/ares_ml_advisor.py)
    quant_ml_advice: str = ""  # TRADE_FULL, TRADE_REDUCED, SKIP_TODAY
    quant_ml_win_probability: float = 0
    quant_ml_confidence: float = 0
    quant_ml_suggested_risk_pct: float = 0
    quant_ml_suggested_sd_multiplier: float = 0
    quant_ml_top_factors: List[Dict] = field(default_factory=list)
    quant_ml_model_version: str = ""

    # ML Regime Classifier (from quant/ml_regime_classifier.py)
    regime_predicted_action: str = ""  # SELL_PREMIUM, BUY_CALLS, BUY_PUTS, STAY_FLAT
    regime_confidence: float = 0
    regime_probabilities: Dict = field(default_factory=dict)
    regime_feature_importance: Dict = field(default_factory=dict)
    regime_model_version: str = ""

    # GEX Directional ML (from quant/gex_directional_ml.py)
    gex_ml_direction: str = ""  # BULLISH, BEARISH, FLAT
    gex_ml_confidence: float = 0
    gex_ml_probabilities: Dict = field(default_factory=dict)
    gex_ml_features_used: Dict = field(default_factory=dict)

    # Ensemble Strategy (from quant/ensemble_strategy.py)
    ensemble_signal: str = ""  # STRONG_BUY, BUY, NEUTRAL, SELL, STRONG_SELL
    ensemble_confidence: float = 0
    ensemble_bullish_weight: float = 0
    ensemble_bearish_weight: float = 0
    ensemble_neutral_weight: float = 0
    ensemble_should_trade: bool = False
    ensemble_position_size_multiplier: float = 0
    ensemble_component_signals: List[Dict] = field(default_factory=list)
    ensemble_reasoning: str = ""

    # Volatility Regime (from core/psychology_trap_detector.py)
    volatility_regime: str = ""  # EXPLOSIVE_VOLATILITY, NEGATIVE_GAMMA_RISK, etc.
    volatility_risk_level: str = ""  # extreme, high, medium, low
    volatility_description: str = ""
    at_flip_point: bool = False
    flip_point: float = 0
    flip_point_distance_pct: float = 0

    # Psychology Patterns (Liberation, False Floor, Forward Magnets)
    psychology_pattern: str = ""
    liberation_setup: bool = False
    false_floor_detected: bool = False
    forward_magnets: List[Dict] = field(default_factory=list)

    # Monte Carlo Kelly (from quant/monte_carlo_kelly.py)
    kelly_optimal: float = 0
    kelly_safe: float = 0
    kelly_conservative: float = 0
    kelly_prob_ruin: float = 0
    kelly_recommendation: str = ""

    # ARGUS Pattern Similarity / ROC Analysis
    argus_pattern_match: str = ""
    argus_similarity_score: float = 0
    argus_historical_outcome: str = ""
    argus_roc_value: float = 0
    argus_roc_signal: str = ""

    # === NEW: IV Context ===
    iv_rank: float = 0  # 0-100 percentile
    iv_percentile: float = 0  # IV percentile vs 52-week range
    iv_hv_ratio: float = 0  # Implied vol / Historical vol ratio
    iv_30d: float = 0  # 30-day implied volatility
    hv_30d: float = 0  # 30-day historical volatility

    # === NEW: Time Context ===
    day_of_week: str = ""  # Monday, Tuesday, etc.
    day_of_week_num: int = 0  # 0=Monday, 4=Friday
    time_of_day: str = ""  # morning, midday, afternoon
    hour_ct: int = 0  # Hour in Central Time
    minute_ct: int = 0  # Minute in Central Time
    days_to_monthly_opex: int = 0  # Days until monthly options expiration
    days_to_weekly_opex: int = 0  # Days until weekly expiration
    is_opex_week: bool = False  # True if within OPEX week
    is_fomc_day: bool = False  # True if FOMC announcement day
    is_cpi_day: bool = False  # True if CPI release day

    # === NEW: Recent Performance Context ===
    similar_setup_win_rate: float = 0  # Win rate in similar conditions (last 30 days)
    similar_setup_count: int = 0  # Number of similar setups found
    similar_setup_avg_pnl: float = 0  # Average P&L in similar conditions
    current_streak: int = 0  # Positive = win streak, Negative = loss streak
    streak_type: str = ""  # "WIN" or "LOSS"
    last_5_trades_win_rate: float = 0  # Win rate of last 5 trades
    last_10_trades_win_rate: float = 0  # Win rate of last 10 trades
    daily_pnl: float = 0  # Today's P&L so far
    weekly_pnl: float = 0  # This week's P&L

    # === NEW: ML Consensus & Conflict Detection ===
    ml_consensus: str = ""  # STRONG_BULLISH, BULLISH, MIXED, BEARISH, STRONG_BEARISH, NO_DATA
    ml_consensus_score: float = 0  # -1 (all bearish) to +1 (all bullish)
    ml_systems_agree: int = 0  # Number of systems that agree with consensus
    ml_systems_total: int = 0  # Total number of active ML systems
    ml_conflicts: List[Dict] = field(default_factory=list)  # List of conflicting signals
    ml_conflict_severity: str = ""  # none, low, medium, high
    ml_highest_confidence_system: str = ""  # Which ML system has highest confidence
    ml_highest_confidence_value: float = 0  # The confidence value

    # Checks
    checks_performed: List[CheckResult] = field(default_factory=list)
    all_checks_passed: bool = True

    # Trade details
    trade_executed: bool = False
    position_id: str = ""
    strike_selection: Dict = field(default_factory=dict)
    contracts: int = 0
    premium_collected: float = 0
    max_risk: float = 0

    # Error
    error_message: str = ""
    error_type: str = ""

    # Full context
    full_context: Dict = field(default_factory=dict)


# Counter for scan IDs
_scan_counters: Dict[str, int] = {}


def _generate_scan_id(bot_name: str) -> str:
    """Generate unique scan ID"""
    global _scan_counters
    if bot_name not in _scan_counters:
        _scan_counters[bot_name] = 0
    _scan_counters[bot_name] += 1

    now = datetime.now(CENTRAL_TZ)
    return f"{bot_name}-{now.strftime('%Y%m%d-%H%M%S')}-{_scan_counters[bot_name]:04d}"


def _get_scan_number_today(bot_name: str) -> int:
    """Get the scan number for today from database.

    CRITICAL: Uses finally block to prevent connection leaks.
    This function is called on EVERY scan, so leaks here cause
    pool exhaustion over time (the 6:05 AM stoppage root cause).
    """
    conn = None
    try:
        from database_adapter import get_connection
        conn = get_connection()
        c = conn.cursor()

        today = datetime.now(CENTRAL_TZ).date()
        c.execute("""
            SELECT COALESCE(MAX(scan_number), 0) + 1
            FROM scan_activity
            WHERE bot_name = %s AND date = %s
        """, (bot_name, today))

        result = c.fetchone()
        return result[0] if result else 1
    except Exception as e:
        logger.debug(f"Could not get scan number: {e}")
        return _scan_counters.get(bot_name, 0) + 1
    finally:
        # CRITICAL: Always close connection to prevent pool exhaustion
        try:
            if conn:
                conn.close()
        except Exception:
            pass


def log_scan_activity(
    bot_name: str,
    outcome: ScanOutcome,
    decision_summary: str,
    action_taken: str = "",
    full_reasoning: str = "",
    # Market data
    market_data: Optional[Dict] = None,
    # GEX data
    gex_data: Optional[Dict] = None,
    # Signal data
    signal_source: str = "",
    signal_direction: str = "",
    signal_confidence: float = 0,
    signal_win_probability: float = 0,
    # Oracle data - FULL context for frontend visibility
    oracle_advice: str = "",
    oracle_reasoning: str = "",
    oracle_win_probability: float = 0,
    oracle_confidence: float = 0,
    oracle_top_factors: Optional[List[Dict]] = None,
    oracle_probabilities: Optional[Dict] = None,
    oracle_suggested_strikes: Optional[Dict] = None,
    oracle_thresholds: Optional[Dict] = None,
    min_win_probability_threshold: float = 0,
    # Risk/Reward
    risk_reward_ratio: float = 0,
    # Checks
    checks: Optional[List[CheckResult]] = None,
    # Trade data
    trade_executed: bool = False,
    position_id: str = "",
    strike_selection: Optional[Dict] = None,
    contracts: int = 0,
    premium_collected: float = 0,
    max_risk: float = 0,
    # Error
    error_message: str = "",
    error_type: str = "",
    # Claude AI explanations
    what_would_trigger: str = "",
    market_insight: str = "",
    # Additional context
    full_context: Optional[Dict] = None,
    # Generate AI explanation
    generate_ai_explanation: bool = True,
    # === NEW: Quant ML Advisor ===
    quant_ml_advice: str = "",
    quant_ml_win_probability: float = 0,
    quant_ml_confidence: float = 0,
    quant_ml_suggested_risk_pct: float = 0,
    quant_ml_suggested_sd_multiplier: float = 0,
    quant_ml_top_factors: Optional[List[Dict]] = None,
    quant_ml_model_version: str = "",
    # === NEW: ML Regime Classifier ===
    regime_predicted_action: str = "",
    regime_confidence: float = 0,
    regime_probabilities: Optional[Dict] = None,
    regime_feature_importance: Optional[Dict] = None,
    regime_model_version: str = "",
    # === NEW: GEX Directional ML ===
    gex_ml_direction: str = "",
    gex_ml_confidence: float = 0,
    gex_ml_probabilities: Optional[Dict] = None,
    gex_ml_features_used: Optional[Dict] = None,
    # === NEW: Ensemble Strategy ===
    ensemble_signal: str = "",
    ensemble_confidence: float = 0,
    ensemble_bullish_weight: float = 0,
    ensemble_bearish_weight: float = 0,
    ensemble_neutral_weight: float = 0,
    ensemble_should_trade: bool = False,
    ensemble_position_size_multiplier: float = 0,
    ensemble_component_signals: Optional[List[Dict]] = None,
    ensemble_reasoning: str = "",
    # === NEW: Volatility Regime ===
    volatility_regime: str = "",
    volatility_risk_level: str = "",
    volatility_description: str = "",
    at_flip_point: bool = False,
    flip_point: float = 0,
    flip_point_distance_pct: float = 0,
    # === NEW: Psychology Patterns ===
    psychology_pattern: str = "",
    liberation_setup: bool = False,
    false_floor_detected: bool = False,
    forward_magnets: Optional[List[Dict]] = None,
    # === NEW: Monte Carlo Kelly ===
    kelly_optimal: float = 0,
    kelly_safe: float = 0,
    kelly_conservative: float = 0,
    kelly_prob_ruin: float = 0,
    kelly_recommendation: str = "",
    # === NEW: ARGUS Pattern Analysis ===
    argus_pattern_match: str = "",
    argus_similarity_score: float = 0,
    argus_historical_outcome: str = "",
    argus_roc_value: float = 0,
    argus_roc_signal: str = "",
    # === NEW: IV Context ===
    iv_rank: float = 0,
    iv_percentile: float = 0,
    iv_hv_ratio: float = 0,
    iv_30d: float = 0,
    hv_30d: float = 0,
    # === NEW: Time Context ===
    day_of_week: str = "",
    day_of_week_num: int = 0,
    time_of_day: str = "",
    hour_ct: int = 0,
    minute_ct: int = 0,
    days_to_monthly_opex: int = 0,
    days_to_weekly_opex: int = 0,
    is_opex_week: bool = False,
    is_fomc_day: bool = False,
    is_cpi_day: bool = False,
    # === NEW: Recent Performance Context ===
    similar_setup_win_rate: float = 0,
    similar_setup_count: int = 0,
    similar_setup_avg_pnl: float = 0,
    current_streak: int = 0,
    streak_type: str = "",
    last_5_trades_win_rate: float = 0,
    last_10_trades_win_rate: float = 0,
    daily_pnl: float = 0,
    weekly_pnl: float = 0,
    # === NEW: ML Consensus & Conflict Detection ===
    ml_consensus: str = "",
    ml_consensus_score: float = 0,
    ml_systems_agree: int = 0,
    ml_systems_total: int = 0,
    ml_conflicts: Optional[List[Dict]] = None,
    ml_conflict_severity: str = "",
    ml_highest_confidence_system: str = "",
    ml_highest_confidence_value: float = 0
) -> Optional[str]:
    """
    Log a scan activity to the database.

    This should be called on EVERY scan, regardless of outcome.

    Args:
        bot_name: Name of the bot (ARES, ATHENA)
        outcome: What happened (TRADED, NO_TRADE, ERROR, etc.)
        decision_summary: One-line human-readable summary
        action_taken: What action was taken (if any)
        full_reasoning: Detailed reasoning for the decision
        market_data: Current market conditions
        gex_data: GEX context if available
        signal_source: Where the signal came from (ML, Oracle, etc.)
        signal_direction: BULLISH, BEARISH, NEUTRAL
        signal_confidence: 0-1 confidence score
        signal_win_probability: 0-1 win probability
        oracle_advice: What Oracle recommended
        oracle_reasoning: Why Oracle made that recommendation
        checks: List of checks performed
        trade_executed: Whether a trade was executed
        position_id: Position ID if traded
        strike_selection: Strike details if traded
        contracts: Number of contracts traded
        premium_collected: Premium collected
        max_risk: Maximum risk
        error_message: Error message if error occurred
        error_type: Type of error
        full_context: Additional context as JSON

    Returns:
        scan_id if logged successfully, None otherwise
    """
    try:
        from database_adapter import get_connection

        now = datetime.now(CENTRAL_TZ)
        scan_id = _generate_scan_id(bot_name)
        scan_number = _get_scan_number_today(bot_name)

        # Extract market data
        underlying_price = 0
        underlying_symbol = ""
        vix = 0
        expected_move = 0

        if market_data:
            underlying_price = market_data.get('underlying_price', 0) or market_data.get('spot_price', 0)
            underlying_symbol = market_data.get('symbol', '') or market_data.get('ticker', '')
            vix = market_data.get('vix', 0)
            expected_move = market_data.get('expected_move', 0)

        # Extract GEX data
        gex_regime = ""
        net_gex = 0
        call_wall = 0
        put_wall = 0
        distance_to_call_wall_pct = 0
        distance_to_put_wall_pct = 0

        if gex_data:
            gex_regime = gex_data.get('regime', '') or gex_data.get('gex_regime', '')
            net_gex = gex_data.get('net_gex', 0)
            call_wall = gex_data.get('call_wall', 0)
            put_wall = gex_data.get('put_wall', 0)

            # Calculate distances if we have spot price
            spot = underlying_price or gex_data.get('spot_price', 0)
            if spot and call_wall:
                distance_to_call_wall_pct = ((call_wall - spot) / spot) * 100
            if spot and put_wall:
                distance_to_put_wall_pct = ((spot - put_wall) / spot) * 100

        # Convert checks to JSON
        checks_json = []
        all_checks_passed = True
        if checks:
            for check in checks:
                if isinstance(check, CheckResult):
                    checks_json.append(asdict(check))
                    if not check.passed:
                        all_checks_passed = False
                elif isinstance(check, dict):
                    checks_json.append(check)
                    if not check.get('passed', True):
                        all_checks_passed = False

        # Build full context
        context = full_context or {}
        context['market_data'] = market_data
        context['gex_data'] = gex_data

        conn = get_connection()
        c = conn.cursor()

        # Ensure table exists with all columns
        c.execute("""
            CREATE TABLE IF NOT EXISTS scan_activity (
                id SERIAL PRIMARY KEY,
                bot_name VARCHAR(50) NOT NULL,
                scan_id VARCHAR(100) NOT NULL UNIQUE,
                scan_number INTEGER NOT NULL,
                timestamp TIMESTAMP NOT NULL,
                date DATE NOT NULL,
                time_ct VARCHAR(20) NOT NULL,
                outcome VARCHAR(50) NOT NULL,
                action_taken VARCHAR(100),
                decision_summary TEXT NOT NULL,
                full_reasoning TEXT,
                underlying_price DECIMAL(15, 4),
                underlying_symbol VARCHAR(10),
                vix DECIMAL(10, 4),
                expected_move DECIMAL(10, 4),
                gex_regime VARCHAR(50),
                net_gex DECIMAL(20, 2),
                call_wall DECIMAL(15, 4),
                put_wall DECIMAL(15, 4),
                distance_to_call_wall_pct DECIMAL(10, 4),
                distance_to_put_wall_pct DECIMAL(10, 4),
                signal_source VARCHAR(50),
                signal_direction VARCHAR(20),
                signal_confidence DECIMAL(5, 4),
                signal_win_probability DECIMAL(5, 4),
                oracle_advice VARCHAR(50),
                oracle_reasoning TEXT,
                oracle_win_probability DECIMAL(5, 4),
                oracle_confidence DECIMAL(5, 4),
                oracle_top_factors JSONB,
                oracle_probabilities JSONB,
                oracle_suggested_strikes JSONB,
                oracle_thresholds JSONB,
                min_win_probability_threshold DECIMAL(5, 4),
                risk_reward_ratio DECIMAL(10, 4),
                checks_performed JSONB,
                all_checks_passed BOOLEAN DEFAULT TRUE,
                trade_executed BOOLEAN DEFAULT FALSE,
                position_id VARCHAR(100),
                strike_selection JSONB,
                contracts INTEGER,
                premium_collected DECIMAL(15, 4),
                max_risk DECIMAL(15, 4),
                error_message TEXT,
                error_type VARCHAR(100),
                what_would_trigger TEXT,
                market_insight TEXT,
                full_context JSONB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Add new columns if they don't exist (for existing tables)
        # Note: These are safe migrations - ADD COLUMN IF NOT EXISTS won't error
        try:
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS risk_reward_ratio DECIMAL(10, 4)")
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS what_would_trigger TEXT")
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS market_insight TEXT")
            # Oracle context columns
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS oracle_win_probability DECIMAL(5, 4)")
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS oracle_confidence DECIMAL(5, 4)")
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS oracle_top_factors JSONB")
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS oracle_probabilities JSONB")
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS oracle_suggested_strikes JSONB")
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS oracle_thresholds JSONB")
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS min_win_probability_threshold DECIMAL(5, 4)")
            # === NEW: Quant ML Advisor columns ===
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS quant_ml_advice VARCHAR(50)")
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS quant_ml_win_probability DECIMAL(5, 4)")
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS quant_ml_confidence DECIMAL(5, 4)")
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS quant_ml_suggested_risk_pct DECIMAL(5, 4)")
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS quant_ml_suggested_sd_multiplier DECIMAL(5, 4)")
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS quant_ml_top_factors JSONB")
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS quant_ml_model_version VARCHAR(50)")
            # === NEW: ML Regime Classifier columns ===
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS regime_predicted_action VARCHAR(50)")
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS regime_confidence DECIMAL(5, 4)")
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS regime_probabilities JSONB")
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS regime_feature_importance JSONB")
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS regime_model_version VARCHAR(50)")
            # === NEW: GEX Directional ML columns ===
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS gex_ml_direction VARCHAR(20)")
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS gex_ml_confidence DECIMAL(5, 4)")
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS gex_ml_probabilities JSONB")
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS gex_ml_features_used JSONB")
            # === NEW: Ensemble Strategy columns ===
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS ensemble_signal VARCHAR(50)")
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS ensemble_confidence DECIMAL(5, 4)")
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS ensemble_bullish_weight DECIMAL(5, 4)")
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS ensemble_bearish_weight DECIMAL(5, 4)")
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS ensemble_neutral_weight DECIMAL(5, 4)")
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS ensemble_should_trade BOOLEAN")
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS ensemble_position_size_multiplier DECIMAL(5, 4)")
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS ensemble_component_signals JSONB")
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS ensemble_reasoning TEXT")
            # === NEW: Volatility Regime columns ===
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS volatility_regime VARCHAR(50)")
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS volatility_risk_level VARCHAR(20)")
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS volatility_description TEXT")
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS at_flip_point BOOLEAN")
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS flip_point DECIMAL(15, 4)")
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS flip_point_distance_pct DECIMAL(10, 4)")
            # === NEW: Psychology Patterns columns ===
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS psychology_pattern VARCHAR(100)")
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS liberation_setup BOOLEAN")
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS false_floor_detected BOOLEAN")
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS forward_magnets JSONB")
            # === NEW: Monte Carlo Kelly columns ===
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS kelly_optimal DECIMAL(5, 4)")
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS kelly_safe DECIMAL(5, 4)")
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS kelly_conservative DECIMAL(5, 4)")
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS kelly_prob_ruin DECIMAL(5, 4)")
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS kelly_recommendation TEXT")
            # === NEW: ARGUS Pattern Analysis columns ===
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS argus_pattern_match VARCHAR(100)")
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS argus_similarity_score DECIMAL(5, 4)")
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS argus_historical_outcome VARCHAR(50)")
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS argus_roc_value DECIMAL(10, 4)")
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS argus_roc_signal VARCHAR(50)")
            # === NEW: IV Context columns ===
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS iv_rank DECIMAL(5, 2)")
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS iv_percentile DECIMAL(5, 2)")
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS iv_hv_ratio DECIMAL(5, 2)")
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS iv_30d DECIMAL(5, 2)")
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS hv_30d DECIMAL(5, 2)")
            # === NEW: Time Context columns ===
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS day_of_week VARCHAR(20)")
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS day_of_week_num INTEGER")
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS time_of_day VARCHAR(20)")
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS hour_ct INTEGER")
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS minute_ct INTEGER")
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS days_to_monthly_opex INTEGER")
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS days_to_weekly_opex INTEGER")
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS is_opex_week BOOLEAN")
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS is_fomc_day BOOLEAN")
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS is_cpi_day BOOLEAN")
            # === NEW: Recent Performance Context columns ===
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS similar_setup_win_rate DECIMAL(5, 4)")
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS similar_setup_count INTEGER")
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS similar_setup_avg_pnl DECIMAL(15, 2)")
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS current_streak INTEGER")
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS streak_type VARCHAR(10)")
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS last_5_trades_win_rate DECIMAL(5, 4)")
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS last_10_trades_win_rate DECIMAL(5, 4)")
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS daily_pnl DECIMAL(15, 2)")
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS weekly_pnl DECIMAL(15, 2)")
            # === NEW: ML Consensus & Conflict Detection columns ===
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS ml_consensus VARCHAR(50)")
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS ml_consensus_score DECIMAL(5, 4)")
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS ml_systems_agree INTEGER")
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS ml_systems_total INTEGER")
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS ml_conflicts JSONB")
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS ml_conflict_severity VARCHAR(20)")
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS ml_highest_confidence_system VARCHAR(50)")
            c.execute("ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS ml_highest_confidence_value DECIMAL(5, 4)")
            conn.commit()  # Commit schema changes before INSERT
        except Exception as e:
            # Log the error but continue - columns likely already exist
            logger.debug(f"ALTER TABLE scan_activity (non-critical): {e}")
            try:
                conn.rollback()  # Rollback any failed transaction to clean state
            except Exception:
                pass

        # Generate Claude AI explanation if enabled and market data available
        ai_what_trigger = what_would_trigger
        ai_market_insight = market_insight

        if generate_ai_explanation and market_data and not ai_what_trigger:
            try:
                from trading.scan_explainer import generate_scan_explanation, ScanContext, MarketContext, SignalContext, CheckDetail, DecisionType

                # Build context for Claude
                check_details = []
                if checks:
                    for check in checks:
                        if isinstance(check, CheckResult):
                            check_details.append(CheckDetail(
                                name=check.check_name,
                                passed=check.passed,
                                actual_value=check.value,
                                required_value=check.threshold,
                                explanation=check.reason
                            ))

                scan_ctx = ScanContext(
                    bot_name=bot_name,
                    scan_number=scan_number,
                    decision_type=DecisionType(outcome.value),
                    market=MarketContext(
                        underlying_symbol=underlying_symbol or "SPY",
                        underlying_price=underlying_price,
                        vix=vix,
                        expected_move=expected_move,
                        net_gex=net_gex,
                        gex_regime=gex_regime,
                        call_wall=call_wall,
                        put_wall=put_wall,
                        distance_to_call_wall_pct=distance_to_call_wall_pct,
                        distance_to_put_wall_pct=distance_to_put_wall_pct
                    ),
                    signal=SignalContext(
                        source=signal_source or "None",
                        direction=signal_direction or "NONE",
                        confidence=signal_confidence,
                        win_probability=signal_win_probability,
                        advice=oracle_advice,
                        reasoning=oracle_reasoning
                    ) if signal_source else None,
                    checks=check_details if check_details else None,
                    error_message=error_message
                )

                explanation = generate_scan_explanation(scan_ctx)
                ai_what_trigger = explanation.get('what_would_trigger', '')
                ai_market_insight = explanation.get('market_insight', '')

                # Use Claude's full explanation if we don't have one
                if not full_reasoning and explanation.get('full_explanation'):
                    full_reasoning = explanation.get('full_explanation', '')

            except Exception as e:
                logger.debug(f"Could not generate Claude explanation: {e}")

        # Insert scan activity
        c.execute("""
            INSERT INTO scan_activity (
                bot_name, scan_id, scan_number,
                timestamp, date, time_ct,
                outcome, action_taken, decision_summary, full_reasoning,
                underlying_price, underlying_symbol, vix, expected_move,
                gex_regime, net_gex, call_wall, put_wall,
                distance_to_call_wall_pct, distance_to_put_wall_pct,
                signal_source, signal_direction, signal_confidence, signal_win_probability,
                oracle_advice, oracle_reasoning,
                oracle_win_probability, oracle_confidence,
                oracle_top_factors, oracle_probabilities,
                oracle_suggested_strikes, oracle_thresholds,
                min_win_probability_threshold,
                risk_reward_ratio,
                checks_performed, all_checks_passed,
                trade_executed, position_id, strike_selection, contracts,
                premium_collected, max_risk,
                error_message, error_type,
                what_would_trigger, market_insight,
                full_context,
                -- NEW: Quant ML Advisor
                quant_ml_advice, quant_ml_win_probability, quant_ml_confidence,
                quant_ml_suggested_risk_pct, quant_ml_suggested_sd_multiplier,
                quant_ml_top_factors, quant_ml_model_version,
                -- NEW: ML Regime Classifier
                regime_predicted_action, regime_confidence,
                regime_probabilities, regime_feature_importance, regime_model_version,
                -- NEW: GEX Directional ML
                gex_ml_direction, gex_ml_confidence, gex_ml_probabilities, gex_ml_features_used,
                -- NEW: Ensemble Strategy
                ensemble_signal, ensemble_confidence, ensemble_bullish_weight,
                ensemble_bearish_weight, ensemble_neutral_weight, ensemble_should_trade,
                ensemble_position_size_multiplier, ensemble_component_signals, ensemble_reasoning,
                -- NEW: Volatility Regime
                volatility_regime, volatility_risk_level, volatility_description,
                at_flip_point, flip_point, flip_point_distance_pct,
                -- NEW: Psychology Patterns
                psychology_pattern, liberation_setup, false_floor_detected, forward_magnets,
                -- NEW: Monte Carlo Kelly
                kelly_optimal, kelly_safe, kelly_conservative, kelly_prob_ruin, kelly_recommendation,
                -- NEW: ARGUS Pattern Analysis
                argus_pattern_match, argus_similarity_score, argus_historical_outcome,
                argus_roc_value, argus_roc_signal,
                -- NEW: IV Context
                iv_rank, iv_percentile, iv_hv_ratio, iv_30d, hv_30d,
                -- NEW: Time Context
                day_of_week, day_of_week_num, time_of_day, hour_ct, minute_ct,
                days_to_monthly_opex, days_to_weekly_opex, is_opex_week, is_fomc_day, is_cpi_day,
                -- NEW: Recent Performance Context
                similar_setup_win_rate, similar_setup_count, similar_setup_avg_pnl,
                current_streak, streak_type, last_5_trades_win_rate, last_10_trades_win_rate,
                daily_pnl, weekly_pnl,
                -- NEW: ML Consensus & Conflict Detection
                ml_consensus, ml_consensus_score, ml_systems_agree, ml_systems_total,
                ml_conflicts, ml_conflict_severity, ml_highest_confidence_system, ml_highest_confidence_value
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s
            )
        """, (
            bot_name, scan_id, scan_number,
            now, now.date(), now.strftime('%I:%M:%S %p'),
            outcome.value, action_taken, decision_summary, full_reasoning,
            underlying_price, underlying_symbol, vix, expected_move,
            gex_regime, net_gex, call_wall, put_wall,
            distance_to_call_wall_pct, distance_to_put_wall_pct,
            signal_source, signal_direction, signal_confidence, signal_win_probability,
            oracle_advice, oracle_reasoning,
            oracle_win_probability, oracle_confidence,
            json.dumps(oracle_top_factors) if oracle_top_factors else None,
            json.dumps(oracle_probabilities) if oracle_probabilities else None,
            json.dumps(oracle_suggested_strikes) if oracle_suggested_strikes else None,
            json.dumps(oracle_thresholds) if oracle_thresholds else None,
            min_win_probability_threshold,
            risk_reward_ratio,
            json.dumps(checks_json) if checks_json else None, all_checks_passed,
            trade_executed, position_id, json.dumps(strike_selection) if strike_selection else None, contracts,
            premium_collected, max_risk,
            error_message, error_type,
            ai_what_trigger, ai_market_insight,
            json.dumps(context),
            # NEW: Quant ML Advisor
            quant_ml_advice, quant_ml_win_probability, quant_ml_confidence,
            quant_ml_suggested_risk_pct, quant_ml_suggested_sd_multiplier,
            json.dumps(quant_ml_top_factors) if quant_ml_top_factors else None, quant_ml_model_version,
            # NEW: ML Regime Classifier
            regime_predicted_action, regime_confidence,
            json.dumps(regime_probabilities) if regime_probabilities else None,
            json.dumps(regime_feature_importance) if regime_feature_importance else None, regime_model_version,
            # NEW: GEX Directional ML
            gex_ml_direction, gex_ml_confidence,
            json.dumps(gex_ml_probabilities) if gex_ml_probabilities else None,
            json.dumps(gex_ml_features_used) if gex_ml_features_used else None,
            # NEW: Ensemble Strategy
            ensemble_signal, ensemble_confidence, ensemble_bullish_weight,
            ensemble_bearish_weight, ensemble_neutral_weight, ensemble_should_trade,
            ensemble_position_size_multiplier,
            json.dumps(ensemble_component_signals) if ensemble_component_signals else None, ensemble_reasoning,
            # NEW: Volatility Regime
            volatility_regime, volatility_risk_level, volatility_description,
            at_flip_point, flip_point, flip_point_distance_pct,
            # NEW: Psychology Patterns
            psychology_pattern, liberation_setup, false_floor_detected,
            json.dumps(forward_magnets) if forward_magnets else None,
            # NEW: Monte Carlo Kelly
            kelly_optimal, kelly_safe, kelly_conservative, kelly_prob_ruin, kelly_recommendation,
            # NEW: ARGUS Pattern Analysis
            argus_pattern_match, argus_similarity_score, argus_historical_outcome,
            argus_roc_value, argus_roc_signal,
            # NEW: IV Context
            iv_rank, iv_percentile, iv_hv_ratio, iv_30d, hv_30d,
            # NEW: Time Context
            day_of_week, day_of_week_num, time_of_day, hour_ct, minute_ct,
            days_to_monthly_opex, days_to_weekly_opex, is_opex_week, is_fomc_day, is_cpi_day,
            # NEW: Recent Performance Context
            similar_setup_win_rate, similar_setup_count, similar_setup_avg_pnl,
            current_streak, streak_type, last_5_trades_win_rate, last_10_trades_win_rate,
            daily_pnl, weekly_pnl,
            # NEW: ML Consensus & Conflict Detection
            ml_consensus, ml_consensus_score, ml_systems_agree, ml_systems_total,
            json.dumps(ml_conflicts) if ml_conflicts else None, ml_conflict_severity,
            ml_highest_confidence_system, ml_highest_confidence_value
        ))

        conn.commit()
        logger.info(f"[{bot_name}] Scan #{scan_number} logged: {outcome.value} - {decision_summary}")
        return scan_id

    except Exception as e:
        logger.error(f"Failed to log scan activity: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None

    finally:
        # Always close connection to prevent leaks
        try:
            if conn:
                conn.close()
        except Exception:
            pass


def get_recent_scans(
    bot_name: Optional[str] = None,
    limit: int = 50,
    date: Optional[str] = None,
    outcome: Optional[str] = None
) -> List[Dict]:
    """
    Get recent scan activity.

    Args:
        bot_name: Filter by bot name (optional)
        limit: Maximum records to return
        date: Filter by date (YYYY-MM-DD)
        outcome: Filter by outcome (TRADED, NO_TRADE, etc.)

    Returns:
        List of scan activity records
    """
    try:
        from database_adapter import get_connection
        conn = get_connection()
        c = conn.cursor()

        # Build query
        query = """
            SELECT
                id, bot_name, scan_id, scan_number,
                timestamp, date, time_ct,
                outcome, action_taken, decision_summary, full_reasoning,
                underlying_price, underlying_symbol, vix, expected_move,
                gex_regime, net_gex, call_wall, put_wall,
                distance_to_call_wall_pct, distance_to_put_wall_pct,
                signal_source, signal_direction, signal_confidence, signal_win_probability,
                oracle_advice, oracle_reasoning,
                oracle_win_probability, oracle_confidence,
                oracle_top_factors, oracle_probabilities,
                oracle_suggested_strikes, oracle_thresholds,
                min_win_probability_threshold,
                risk_reward_ratio,
                checks_performed, all_checks_passed,
                trade_executed, position_id, strike_selection, contracts,
                premium_collected, max_risk,
                error_message, error_type,
                what_would_trigger, market_insight,
                -- NEW: Quant ML Advisor
                quant_ml_advice, quant_ml_win_probability, quant_ml_confidence,
                quant_ml_suggested_risk_pct, quant_ml_suggested_sd_multiplier,
                quant_ml_top_factors, quant_ml_model_version,
                -- NEW: ML Regime Classifier
                regime_predicted_action, regime_confidence,
                regime_probabilities, regime_feature_importance, regime_model_version,
                -- NEW: GEX Directional ML
                gex_ml_direction, gex_ml_confidence, gex_ml_probabilities, gex_ml_features_used,
                -- NEW: Ensemble Strategy
                ensemble_signal, ensemble_confidence, ensemble_bullish_weight,
                ensemble_bearish_weight, ensemble_neutral_weight, ensemble_should_trade,
                ensemble_position_size_multiplier, ensemble_component_signals, ensemble_reasoning,
                -- NEW: Volatility Regime
                volatility_regime, volatility_risk_level, volatility_description,
                at_flip_point, flip_point, flip_point_distance_pct,
                -- NEW: Psychology Patterns
                psychology_pattern, liberation_setup, false_floor_detected, forward_magnets,
                -- NEW: Monte Carlo Kelly
                kelly_optimal, kelly_safe, kelly_conservative, kelly_prob_ruin, kelly_recommendation,
                -- NEW: ARGUS Pattern Analysis
                argus_pattern_match, argus_similarity_score, argus_historical_outcome,
                argus_roc_value, argus_roc_signal,
                -- NEW: IV Context
                iv_rank, iv_percentile, iv_hv_ratio, iv_30d, hv_30d,
                -- NEW: Time Context
                day_of_week, day_of_week_num, time_of_day, hour_ct, minute_ct,
                days_to_monthly_opex, days_to_weekly_opex, is_opex_week, is_fomc_day, is_cpi_day,
                -- NEW: Recent Performance Context
                similar_setup_win_rate, similar_setup_count, similar_setup_avg_pnl,
                current_streak, streak_type, last_5_trades_win_rate, last_10_trades_win_rate,
                daily_pnl, weekly_pnl,
                -- NEW: ML Consensus & Conflict Detection
                ml_consensus, ml_consensus_score, ml_systems_agree, ml_systems_total,
                ml_conflicts, ml_conflict_severity, ml_highest_confidence_system, ml_highest_confidence_value
            FROM scan_activity
            WHERE 1=1
        """
        params = []

        if bot_name:
            query += " AND bot_name = %s"
            params.append(bot_name)

        if date:
            query += " AND date = %s"
            params.append(date)

        if outcome:
            query += " AND outcome = %s"
            params.append(outcome)

        query += " ORDER BY timestamp DESC LIMIT %s"
        params.append(limit)

        c.execute(query, params)

        columns = [
            'id', 'bot_name', 'scan_id', 'scan_number',
            'timestamp', 'date', 'time_ct',
            'outcome', 'action_taken', 'decision_summary', 'full_reasoning',
            'underlying_price', 'underlying_symbol', 'vix', 'expected_move',
            'gex_regime', 'net_gex', 'call_wall', 'put_wall',
            'distance_to_call_wall_pct', 'distance_to_put_wall_pct',
            'signal_source', 'signal_direction', 'signal_confidence', 'signal_win_probability',
            'oracle_advice', 'oracle_reasoning',
            'oracle_win_probability', 'oracle_confidence',
            'oracle_top_factors', 'oracle_probabilities',
            'oracle_suggested_strikes', 'oracle_thresholds',
            'min_win_probability_threshold',
            'risk_reward_ratio',
            'checks_performed', 'all_checks_passed',
            'trade_executed', 'position_id', 'strike_selection', 'contracts',
            'premium_collected', 'max_risk',
            'error_message', 'error_type',
            'what_would_trigger', 'market_insight',
            # NEW: Quant ML Advisor
            'quant_ml_advice', 'quant_ml_win_probability', 'quant_ml_confidence',
            'quant_ml_suggested_risk_pct', 'quant_ml_suggested_sd_multiplier',
            'quant_ml_top_factors', 'quant_ml_model_version',
            # NEW: ML Regime Classifier
            'regime_predicted_action', 'regime_confidence',
            'regime_probabilities', 'regime_feature_importance', 'regime_model_version',
            # NEW: GEX Directional ML
            'gex_ml_direction', 'gex_ml_confidence', 'gex_ml_probabilities', 'gex_ml_features_used',
            # NEW: Ensemble Strategy
            'ensemble_signal', 'ensemble_confidence', 'ensemble_bullish_weight',
            'ensemble_bearish_weight', 'ensemble_neutral_weight', 'ensemble_should_trade',
            'ensemble_position_size_multiplier', 'ensemble_component_signals', 'ensemble_reasoning',
            # NEW: Volatility Regime
            'volatility_regime', 'volatility_risk_level', 'volatility_description',
            'at_flip_point', 'flip_point', 'flip_point_distance_pct',
            # NEW: Psychology Patterns
            'psychology_pattern', 'liberation_setup', 'false_floor_detected', 'forward_magnets',
            # NEW: Monte Carlo Kelly
            'kelly_optimal', 'kelly_safe', 'kelly_conservative', 'kelly_prob_ruin', 'kelly_recommendation',
            # NEW: ARGUS Pattern Analysis
            'argus_pattern_match', 'argus_similarity_score', 'argus_historical_outcome',
            'argus_roc_value', 'argus_roc_signal',
            # NEW: IV Context
            'iv_rank', 'iv_percentile', 'iv_hv_ratio', 'iv_30d', 'hv_30d',
            # NEW: Time Context
            'day_of_week', 'day_of_week_num', 'time_of_day', 'hour_ct', 'minute_ct',
            'days_to_monthly_opex', 'days_to_weekly_opex', 'is_opex_week', 'is_fomc_day', 'is_cpi_day',
            # NEW: Recent Performance Context
            'similar_setup_win_rate', 'similar_setup_count', 'similar_setup_avg_pnl',
            'current_streak', 'streak_type', 'last_5_trades_win_rate', 'last_10_trades_win_rate',
            'daily_pnl', 'weekly_pnl',
            # NEW: ML Consensus & Conflict Detection
            'ml_consensus', 'ml_consensus_score', 'ml_systems_agree', 'ml_systems_total',
            'ml_conflicts', 'ml_conflict_severity', 'ml_highest_confidence_system', 'ml_highest_confidence_value'
        ]

        results = []
        for row in c.fetchall():
            record = dict(zip(columns, row))
            # Convert timestamp to ISO string
            if record.get('timestamp'):
                record['timestamp'] = record['timestamp'].isoformat()
            if record.get('date'):
                record['date'] = str(record['date'])
            # Convert Decimal to float for JSON serialization
            decimal_fields = [
                'underlying_price', 'vix', 'expected_move', 'net_gex',
                'call_wall', 'put_wall', 'distance_to_call_wall_pct',
                'distance_to_put_wall_pct', 'signal_confidence',
                'signal_win_probability', 'premium_collected', 'max_risk',
                'risk_reward_ratio', 'oracle_win_probability', 'oracle_confidence',
                'min_win_probability_threshold',
                # Quant ML / Regime / GEX ML / Ensemble
                'quant_ml_win_probability', 'quant_ml_confidence',
                'quant_ml_suggested_risk_pct', 'quant_ml_suggested_sd_multiplier',
                'regime_confidence', 'gex_ml_confidence',
                'ensemble_confidence', 'ensemble_bullish_weight',
                'ensemble_bearish_weight', 'ensemble_neutral_weight',
                'ensemble_position_size_multiplier',
                'flip_point', 'flip_point_distance_pct',
                'kelly_optimal', 'kelly_safe', 'kelly_conservative', 'kelly_prob_ruin',
                'argus_similarity_score', 'argus_roc_value',
                # IV Context
                'iv_rank', 'iv_percentile', 'iv_hv_ratio', 'iv_30d', 'hv_30d',
                # Recent Performance Context
                'similar_setup_win_rate', 'similar_setup_avg_pnl',
                'last_5_trades_win_rate', 'last_10_trades_win_rate',
                'daily_pnl', 'weekly_pnl',
                # ML Consensus
                'ml_consensus_score', 'ml_highest_confidence_value'
            ]
            for key in decimal_fields:
                if record.get(key) is not None:
                    record[key] = float(record[key])
            results.append(record)

        conn.close()
        return results

    except Exception as e:
        logger.error(f"Failed to get recent scans: {e}")
        return []


def get_scan_summary(bot_name: Optional[str] = None, days: int = 7) -> Dict:
    """
    Get summary statistics for scan activity.

    Args:
        bot_name: Filter by bot name (optional)
        days: Number of days to include

    Returns:
        Summary statistics
    """
    try:
        from database_adapter import get_connection
        conn = get_connection()
        c = conn.cursor()

        bot_filter = "AND bot_name = %s" if bot_name else ""
        params = [days]
        if bot_name:
            params.append(bot_name)

        c.execute(f"""
            SELECT
                COUNT(*) as total_scans,
                COUNT(CASE WHEN trade_executed THEN 1 END) as trades_executed,
                COUNT(CASE WHEN outcome = 'NO_TRADE' THEN 1 END) as no_trade_scans,
                COUNT(CASE WHEN outcome = 'ERROR' THEN 1 END) as error_scans,
                COUNT(CASE WHEN outcome = 'MARKET_CLOSED' THEN 1 END) as market_closed_scans,
                AVG(signal_confidence) as avg_confidence,
                AVG(vix) as avg_vix,
                MAX(timestamp) as last_scan
            FROM scan_activity
            WHERE timestamp >= NOW() - INTERVAL '%s days'
            {bot_filter}
        """, params)

        row = c.fetchone()
        conn.close()

        if row:
            return {
                'total_scans': row[0] or 0,
                'trades_executed': row[1] or 0,
                'no_trade_scans': row[2] or 0,
                'error_scans': row[3] or 0,
                'market_closed_scans': row[4] or 0,
                'avg_confidence': round(float(row[5] or 0), 3),
                'avg_vix': round(float(row[6] or 0), 2),
                'last_scan': row[7].isoformat() if row[7] else None
            }
        return {}

    except Exception as e:
        logger.error(f"Failed to get scan summary: {e}")
        return {}


# Convenience functions for specific bots with AI explanations
def log_ares_scan(
    outcome: ScanOutcome,
    decision_summary: str,
    market_data: Optional[Dict] = None,
    gex_data: Optional[Dict] = None,
    checks: Optional[List[CheckResult]] = None,
    signal_source: str = "",
    signal_direction: str = "",
    signal_confidence: float = 0,
    signal_win_probability: float = 0,
    oracle_advice: str = "",
    oracle_reasoning: str = "",
    oracle_win_probability: float = 0,
    oracle_confidence: float = 0,
    oracle_top_factors: Optional[List[Dict]] = None,
    oracle_probabilities: Optional[Dict] = None,
    oracle_suggested_strikes: Optional[Dict] = None,
    oracle_thresholds: Optional[Dict] = None,
    min_win_probability_threshold: float = 0,
    trade_executed: bool = False,
    error_message: str = "",
    generate_ai_explanation: bool = True,
    **kwargs
) -> Optional[str]:
    """
    Log ARES scan activity with optional Claude AI explanation.

    If generate_ai_explanation is True, uses Claude to create a detailed
    human-readable explanation of WHY this decision was made.
    """
    # Pop parameters from kwargs to avoid "multiple values" error when passing **kwargs
    full_reasoning = kwargs.pop('full_reasoning', '')
    action_taken = kwargs.pop('action_taken', '')
    error_type = kwargs.pop('error_type', '')

    # Generate AI explanation if requested and we have enough context
    if generate_ai_explanation and market_data:
        try:
            from trading.scan_explainer import explain_ares_decision

            # Convert checks to dict format
            checks_list = []
            if checks:
                for check in checks:
                    if isinstance(check, CheckResult):
                        checks_list.append({
                            'check_name': check.check_name,
                            'passed': check.passed,
                            'value': check.value,
                            'threshold': check.threshold,
                            'reason': check.reason
                        })
                    elif isinstance(check, dict):
                        checks_list.append(check)

            # Get scan number
            scan_number = _get_scan_number_today("ARES")

            # Get values from market/gex data
            underlying_price = market_data.get('underlying_price', 0) or market_data.get('spot_price', 0)
            vix = market_data.get('vix', 0)
            expected_move = market_data.get('expected_move', 0)

            net_gex = gex_data.get('net_gex', 0) if gex_data else 0
            call_wall = gex_data.get('call_wall', 0) if gex_data else 0
            put_wall = gex_data.get('put_wall', 0) if gex_data else 0

            # Build trade details if traded
            trade_details = None
            if trade_executed:
                trade_details = {
                    'strategy': 'Iron Condor',
                    'contracts': kwargs.get('contracts', 0),
                    'premium_collected': kwargs.get('premium_collected', 0),
                    'max_risk': kwargs.get('max_risk', 0)
                }

            # Generate explanation
            explanation = explain_ares_decision(
                scan_number=scan_number,
                outcome=outcome.value,
                underlying_price=underlying_price,
                vix=vix,
                checks=checks_list,
                signal_source=signal_source or None,
                signal_direction=signal_direction or None,
                signal_confidence=signal_confidence or None,
                signal_win_prob=signal_win_probability or None,
                oracle_advice=oracle_advice or None,
                oracle_reasoning=oracle_reasoning or None,
                expected_move=expected_move or None,
                net_gex=net_gex or None,
                call_wall=call_wall or None,
                put_wall=put_wall or None,
                trade_details=trade_details,
                error_message=error_message or None
            )

            # Use AI-generated summary and reasoning
            decision_summary = explanation.get('summary', decision_summary)
            full_reasoning = explanation.get('full_explanation', full_reasoning)

            logger.info(f"[ARES] AI explanation generated: {decision_summary}")

        except Exception as e:
            logger.warning(f"Failed to generate AI explanation for ARES: {e}")
            # Fall back to provided summary

    return log_scan_activity(
        bot_name="ARES",
        outcome=outcome,
        decision_summary=decision_summary,
        action_taken=action_taken,
        full_reasoning=full_reasoning,
        market_data=market_data,
        gex_data=gex_data,
        checks=checks,
        signal_source=signal_source,
        signal_direction=signal_direction,
        signal_confidence=signal_confidence,
        signal_win_probability=signal_win_probability,
        oracle_advice=oracle_advice,
        oracle_reasoning=oracle_reasoning,
        oracle_win_probability=oracle_win_probability,
        oracle_confidence=oracle_confidence,
        oracle_top_factors=oracle_top_factors,
        oracle_probabilities=oracle_probabilities,
        oracle_suggested_strikes=oracle_suggested_strikes,
        oracle_thresholds=oracle_thresholds,
        min_win_probability_threshold=min_win_probability_threshold,
        trade_executed=trade_executed,
        error_message=error_message,
        error_type=error_type,
        **kwargs
    )


def log_pegasus_scan(
    outcome: ScanOutcome,
    decision_summary: str,
    market_data: Optional[Dict] = None,
    gex_data: Optional[Dict] = None,
    checks: Optional[List[CheckResult]] = None,
    signal_source: str = "",
    signal_direction: str = "",
    signal_confidence: float = 0,
    signal_win_probability: float = 0,
    oracle_advice: str = "",
    oracle_reasoning: str = "",
    oracle_win_probability: float = 0,
    oracle_confidence: float = 0,
    oracle_top_factors: Optional[List[Dict]] = None,
    oracle_probabilities: Optional[Dict] = None,
    oracle_suggested_strikes: Optional[Dict] = None,
    oracle_thresholds: Optional[Dict] = None,
    min_win_probability_threshold: float = 0,
    trade_executed: bool = False,
    error_message: str = "",
    generate_ai_explanation: bool = False,  # Disable by default for PEGASUS
    **kwargs
) -> Optional[str]:
    """
    Log PEGASUS (SPX Iron Condor) scan activity.

    PEGASUS trades SPX Iron Condors with $10 spreads using SPXW weekly options.
    Similar to ARES but for SPX instead of SPY.
    """
    full_reasoning = kwargs.pop('full_reasoning', '')
    action_taken = kwargs.pop('action_taken', '')
    error_type = kwargs.pop('error_type', '')

    return log_scan_activity(
        bot_name="PEGASUS",
        outcome=outcome,
        decision_summary=decision_summary,
        action_taken=action_taken,
        full_reasoning=full_reasoning,
        market_data=market_data,
        gex_data=gex_data,
        checks=checks,
        signal_source=signal_source,
        signal_direction=signal_direction,
        signal_confidence=signal_confidence,
        signal_win_probability=signal_win_probability,
        oracle_advice=oracle_advice,
        oracle_reasoning=oracle_reasoning,
        oracle_win_probability=oracle_win_probability,
        oracle_confidence=oracle_confidence,
        oracle_top_factors=oracle_top_factors,
        oracle_probabilities=oracle_probabilities,
        oracle_suggested_strikes=oracle_suggested_strikes,
        oracle_thresholds=oracle_thresholds,
        min_win_probability_threshold=min_win_probability_threshold,
        trade_executed=trade_executed,
        error_message=error_message,
        error_type=error_type,
        generate_ai_explanation=generate_ai_explanation,
        **kwargs
    )


def log_athena_scan(
    outcome: ScanOutcome,
    decision_summary: str,
    market_data: Optional[Dict] = None,
    gex_data: Optional[Dict] = None,
    checks: Optional[List[CheckResult]] = None,
    signal_source: str = "",
    signal_direction: str = "",
    signal_confidence: float = 0,
    signal_win_probability: float = 0,
    oracle_advice: str = "",
    oracle_reasoning: str = "",
    oracle_win_probability: float = 0,
    oracle_confidence: float = 0,
    oracle_top_factors: Optional[List[Dict]] = None,
    oracle_probabilities: Optional[Dict] = None,
    oracle_suggested_strikes: Optional[Dict] = None,
    oracle_thresholds: Optional[Dict] = None,
    min_win_probability_threshold: float = 0,
    trade_executed: bool = False,
    error_message: str = "",
    risk_reward_ratio: float = 0,
    generate_ai_explanation: bool = True,
    **kwargs
) -> Optional[str]:
    """
    Log ATHENA scan activity with optional Claude AI explanation.

    If generate_ai_explanation is True, uses Claude to create a detailed
    human-readable explanation of WHY this decision was made.
    """
    # Pop parameters from kwargs to avoid "multiple values" error when passing **kwargs
    # CRITICAL: Must pop ALL params that are explicitly passed to log_scan_activity
    full_reasoning = kwargs.pop('full_reasoning', '')
    action_taken = kwargs.pop('action_taken', '')
    error_type = kwargs.pop('error_type', '')

    # Generate AI explanation if requested and we have enough context
    if generate_ai_explanation and market_data:
        try:
            from trading.scan_explainer import explain_athena_decision

            # Convert checks to dict format
            checks_list = []
            if checks:
                for check in checks:
                    if isinstance(check, CheckResult):
                        checks_list.append({
                            'check_name': check.check_name,
                            'passed': check.passed,
                            'value': check.value,
                            'threshold': check.threshold,
                            'reason': check.reason
                        })
                    elif isinstance(check, dict):
                        checks_list.append(check)

            # Get scan number
            scan_number = _get_scan_number_today("ATHENA")

            # Get values from market/gex data
            underlying_price = market_data.get('underlying_price', 0) or market_data.get('spot_price', 0)
            vix = market_data.get('vix', 0)

            net_gex = gex_data.get('net_gex', 0) if gex_data else 0
            gex_regime = gex_data.get('regime', '') if gex_data else ''
            call_wall = gex_data.get('call_wall', 0) if gex_data else 0
            put_wall = gex_data.get('put_wall', 0) if gex_data else 0

            # Build trade details if traded
            trade_details = None
            if trade_executed:
                trade_details = {
                    'strategy': kwargs.get('strategy', 'Directional Spread'),
                    'contracts': kwargs.get('contracts', 0),
                    'premium_collected': kwargs.get('premium_collected', 0),
                    'max_risk': kwargs.get('max_risk', 0)
                }

            # Generate explanation
            explanation = explain_athena_decision(
                scan_number=scan_number,
                outcome=outcome.value,
                underlying_price=underlying_price,
                vix=vix,
                checks=checks_list,
                signal_source=signal_source or None,
                signal_direction=signal_direction or None,
                signal_confidence=signal_confidence or None,
                signal_win_prob=signal_win_probability or None,
                net_gex=net_gex or None,
                gex_regime=gex_regime or None,
                call_wall=call_wall or None,
                put_wall=put_wall or None,
                risk_reward_ratio=risk_reward_ratio or None,
                trade_details=trade_details,
                error_message=error_message or None
            )

            # Use AI-generated summary and reasoning
            decision_summary = explanation.get('summary', decision_summary)
            full_reasoning = explanation.get('full_explanation', full_reasoning)

            logger.info(f"[ATHENA] AI explanation generated: {decision_summary}")

        except Exception as e:
            logger.warning(f"Failed to generate AI explanation for ATHENA: {e}")
            # Fall back to provided summary

    return log_scan_activity(
        bot_name="ATHENA",
        outcome=outcome,
        decision_summary=decision_summary,
        action_taken=action_taken,
        full_reasoning=full_reasoning,
        market_data=market_data,
        gex_data=gex_data,
        checks=checks,
        signal_source=signal_source,
        signal_direction=signal_direction,
        signal_confidence=signal_confidence,
        signal_win_probability=signal_win_probability,
        oracle_advice=oracle_advice,
        oracle_reasoning=oracle_reasoning,
        oracle_win_probability=oracle_win_probability,
        oracle_confidence=oracle_confidence,
        oracle_top_factors=oracle_top_factors,
        oracle_probabilities=oracle_probabilities,
        oracle_suggested_strikes=oracle_suggested_strikes,
        oracle_thresholds=oracle_thresholds,
        min_win_probability_threshold=min_win_probability_threshold,
        risk_reward_ratio=risk_reward_ratio,
        trade_executed=trade_executed,
        error_message=error_message,
        error_type=error_type,
        **kwargs
    )


def log_phoenix_scan(
    outcome: ScanOutcome,
    decision_summary: str,
    market_data: Optional[Dict] = None,
    gex_data: Optional[Dict] = None,
    signal_source: str = "",
    signal_direction: str = "",
    signal_confidence: float = 0,
    signal_win_probability: float = 0,
    oracle_advice: str = "",
    oracle_reasoning: str = "",
    oracle_win_probability: float = 0,
    oracle_confidence: float = 0,
    oracle_top_factors: Optional[List[Dict]] = None,
    oracle_probabilities: Optional[Dict] = None,
    oracle_suggested_strikes: Optional[Dict] = None,
    oracle_thresholds: Optional[Dict] = None,
    min_win_probability_threshold: float = 0,
    trade_executed: bool = False,
    error_message: str = "",
    error_type: str = "",
    **kwargs
):
    """
    Convenience function to log PHOENIX (0DTE SPY/SPX directional) scan activity.

    PHOENIX is the 0DTE options trader that uses GEX-based directional plays.
    Logs every scan attempt with full Oracle context for frontend visibility.
    """
    action_taken = ""
    full_reasoning = ""

    if trade_executed:
        action_taken = "EXECUTED: 0DTE directional trade opened"
        full_reasoning = f"PHOENIX opened position: {kwargs.get('strategy', 'Call/Put')} | {oracle_reasoning}"
    elif outcome == ScanOutcome.NO_TRADE:
        action_taken = "NO_TRADE: Conditions not met"
        full_reasoning = f"PHOENIX scan - no trade: {decision_summary}"
    elif outcome == ScanOutcome.MARKET_CLOSED:
        action_taken = "MARKET_CLOSED"
        full_reasoning = "Market is closed"
    elif outcome == ScanOutcome.ERROR:
        action_taken = f"ERROR: {error_message}"
        full_reasoning = f"PHOENIX error: {error_message}"
    else:
        action_taken = f"{outcome.value}: {decision_summary}"
        full_reasoning = decision_summary

    return log_scan_activity(
        bot_name="PHOENIX",
        outcome=outcome,
        decision_summary=decision_summary,
        action_taken=action_taken,
        full_reasoning=full_reasoning,
        market_data=market_data,
        gex_data=gex_data,
        signal_source=signal_source,
        signal_direction=signal_direction,
        signal_confidence=signal_confidence,
        signal_win_probability=signal_win_probability,
        oracle_advice=oracle_advice,
        oracle_reasoning=oracle_reasoning,
        oracle_win_probability=oracle_win_probability,
        oracle_confidence=oracle_confidence,
        oracle_top_factors=oracle_top_factors,
        oracle_probabilities=oracle_probabilities,
        oracle_suggested_strikes=oracle_suggested_strikes,
        oracle_thresholds=oracle_thresholds,
        min_win_probability_threshold=min_win_probability_threshold,
        trade_executed=trade_executed,
        error_message=error_message,
        error_type=error_type,
        **kwargs
    )


def log_atlas_scan(
    outcome: ScanOutcome,
    decision_summary: str,
    market_data: Optional[Dict] = None,
    gex_data: Optional[Dict] = None,
    signal_source: str = "",
    signal_confidence: float = 0,
    signal_win_probability: float = 0,
    oracle_advice: str = "",
    oracle_reasoning: str = "",
    oracle_win_probability: float = 0,
    oracle_confidence: float = 0,
    oracle_top_factors: Optional[List[Dict]] = None,
    oracle_probabilities: Optional[Dict] = None,
    oracle_suggested_strikes: Optional[Dict] = None,
    oracle_thresholds: Optional[Dict] = None,
    min_win_probability_threshold: float = 0,
    trade_executed: bool = False,
    error_message: str = "",
    error_type: str = "",
    **kwargs
):
    """
    Convenience function to log ATLAS (SPX Wheel) scan activity.

    ATLAS is the SPX cash-secured put wheel strategy.
    Logs every scan attempt with full Oracle context for frontend visibility.
    """
    action_taken = ""
    full_reasoning = ""

    if trade_executed:
        action_taken = "EXECUTED: SPX wheel position opened/managed"
        full_reasoning = f"ATLAS wheel action: {kwargs.get('action_type', 'CSP')} | {oracle_reasoning}"
    elif outcome == ScanOutcome.NO_TRADE:
        action_taken = "NO_TRADE: No wheel action needed"
        full_reasoning = f"ATLAS scan - no action: {decision_summary}"
    elif outcome == ScanOutcome.MARKET_CLOSED:
        action_taken = "MARKET_CLOSED"
        full_reasoning = "Market is closed"
    elif outcome == ScanOutcome.ERROR:
        action_taken = f"ERROR: {error_message}"
        full_reasoning = f"ATLAS error: {error_message}"
    else:
        action_taken = f"{outcome.value}: {decision_summary}"
        full_reasoning = decision_summary

    return log_scan_activity(
        bot_name="ATLAS",
        outcome=outcome,
        decision_summary=decision_summary,
        action_taken=action_taken,
        full_reasoning=full_reasoning,
        market_data=market_data,
        gex_data=gex_data,
        signal_source=signal_source,
        signal_confidence=signal_confidence,
        signal_win_probability=signal_win_probability,
        oracle_advice=oracle_advice,
        oracle_reasoning=oracle_reasoning,
        oracle_win_probability=oracle_win_probability,
        oracle_confidence=oracle_confidence,
        oracle_top_factors=oracle_top_factors,
        oracle_probabilities=oracle_probabilities,
        oracle_suggested_strikes=oracle_suggested_strikes,
        oracle_thresholds=oracle_thresholds,
        min_win_probability_threshold=min_win_probability_threshold,
        trade_executed=trade_executed,
        error_message=error_message,
        error_type=error_type,
        **kwargs
    )


def log_icarus_scan(
    outcome: ScanOutcome,
    decision_summary: str,
    market_data: Optional[Dict] = None,
    gex_data: Optional[Dict] = None,
    checks: Optional[List[CheckResult]] = None,
    signal_source: str = "",
    signal_direction: str = "",
    signal_confidence: float = 0,
    signal_win_probability: float = 0,
    oracle_advice: str = "",
    oracle_reasoning: str = "",
    oracle_win_probability: float = 0,
    oracle_confidence: float = 0,
    oracle_top_factors: Optional[List[Dict]] = None,
    oracle_probabilities: Optional[Dict] = None,
    oracle_suggested_strikes: Optional[Dict] = None,
    oracle_thresholds: Optional[Dict] = None,
    min_win_probability_threshold: float = 0,
    trade_executed: bool = False,
    error_message: str = "",
    risk_reward_ratio: float = 0,
    generate_ai_explanation: bool = True,
    **kwargs
) -> Optional[str]:
    """
    Log ICARUS scan activity with optional Claude AI explanation.

    ICARUS is an aggressive directional spreads bot with relaxed GEX filters:
    - 10% wall filter (vs ATHENA's 3%)
    - 40% min win probability (vs ATHENA's 48%)
    - 4% risk per trade (vs ATHENA's 2%)

    If generate_ai_explanation is True, uses Claude to create a detailed
    human-readable explanation of WHY this decision was made.
    """
    # Pop parameters from kwargs to avoid "multiple values" error when passing **kwargs
    full_reasoning = kwargs.pop('full_reasoning', '')
    action_taken = kwargs.pop('action_taken', '')
    error_type = kwargs.pop('error_type', '')

    # Generate AI explanation if requested and we have enough context
    # Use ATHENA's explain function since ICARUS is similar
    if generate_ai_explanation and market_data:
        try:
            from trading.scan_explainer import explain_athena_decision

            # Convert checks to dict format
            checks_list = []
            if checks:
                for check in checks:
                    if isinstance(check, CheckResult):
                        checks_list.append({
                            'check_name': check.check_name,
                            'passed': check.passed,
                            'value': check.value,
                            'threshold': check.threshold,
                            'reason': check.reason
                        })
                    elif isinstance(check, dict):
                        checks_list.append(check)

            # Get scan number
            scan_number = _get_scan_number_today("ICARUS")

            # Get values from market/gex data
            underlying_price = market_data.get('underlying_price', 0) or market_data.get('spot_price', 0)
            vix = market_data.get('vix', 0)

            net_gex = gex_data.get('net_gex', 0) if gex_data else 0
            gex_regime = gex_data.get('regime', '') if gex_data else ''
            call_wall = gex_data.get('call_wall', 0) if gex_data else 0
            put_wall = gex_data.get('put_wall', 0) if gex_data else 0

            # Build trade details if traded
            trade_details = None
            if trade_executed:
                trade_details = {
                    'strategy': kwargs.get('strategy', 'Aggressive Directional Spread'),
                    'contracts': kwargs.get('contracts', 0),
                    'premium_collected': kwargs.get('premium_collected', 0),
                    'max_risk': kwargs.get('max_risk', 0)
                }

            # Generate explanation (reuse ATHENA's explainer)
            explanation = explain_athena_decision(
                scan_number=scan_number,
                outcome=outcome.value,
                underlying_price=underlying_price,
                vix=vix,
                checks=checks_list,
                signal_source=signal_source or None,
                signal_direction=signal_direction or None,
                signal_confidence=signal_confidence or None,
                signal_win_prob=signal_win_probability or None,
                net_gex=net_gex or None,
                gex_regime=gex_regime or None,
                call_wall=call_wall or None,
                put_wall=put_wall or None,
                risk_reward_ratio=risk_reward_ratio or None,
                trade_details=trade_details,
                error_message=error_message or None
            )

            # Use AI-generated summary and reasoning
            decision_summary = explanation.get('summary', decision_summary)
            full_reasoning = explanation.get('full_explanation', full_reasoning)

            logger.info(f"[ICARUS] AI explanation generated: {decision_summary}")

        except Exception as e:
            logger.warning(f"Failed to generate AI explanation for ICARUS: {e}")
            # Fall back to provided summary

    return log_scan_activity(
        bot_name="ICARUS",
        outcome=outcome,
        decision_summary=decision_summary,
        action_taken=action_taken,
        full_reasoning=full_reasoning,
        market_data=market_data,
        gex_data=gex_data,
        checks=checks,
        signal_source=signal_source,
        signal_direction=signal_direction,
        signal_confidence=signal_confidence,
        signal_win_probability=signal_win_probability,
        oracle_advice=oracle_advice,
        oracle_reasoning=oracle_reasoning,
        oracle_win_probability=oracle_win_probability,
        oracle_confidence=oracle_confidence,
        oracle_top_factors=oracle_top_factors,
        oracle_probabilities=oracle_probabilities,
        oracle_suggested_strikes=oracle_suggested_strikes,
        oracle_thresholds=oracle_thresholds,
        min_win_probability_threshold=min_win_probability_threshold,
        risk_reward_ratio=risk_reward_ratio,
        trade_executed=trade_executed,
        error_message=error_message,
        error_type=error_type,
        **kwargs
    )


def log_titan_scan(
    outcome: ScanOutcome,
    decision_summary: str,
    market_data: Optional[Dict] = None,
    gex_data: Optional[Dict] = None,
    checks: Optional[List[CheckResult]] = None,
    signal_source: str = "",
    signal_direction: str = "",
    signal_confidence: float = 0,
    signal_win_probability: float = 0,
    oracle_advice: str = "",
    oracle_reasoning: str = "",
    oracle_win_probability: float = 0,
    oracle_confidence: float = 0,
    oracle_top_factors: Optional[List[Dict]] = None,
    oracle_probabilities: Optional[Dict] = None,
    oracle_suggested_strikes: Optional[Dict] = None,
    oracle_thresholds: Optional[Dict] = None,
    min_win_probability_threshold: float = 0,
    trade_executed: bool = False,
    error_message: str = "",
    risk_reward_ratio: float = 0,
    generate_ai_explanation: bool = False,  # Disable by default for TITAN (similar to PEGASUS)
    **kwargs
) -> Optional[str]:
    """
    Log TITAN scan activity.

    TITAN is an aggressive SPX Iron Condor bot with relaxed filters vs PEGASUS:
    - 40% VIX skip (vs PEGASUS's 32%)
    - 40% min win probability (vs PEGASUS's 50%)
    - 15% risk per trade (vs PEGASUS's 10%)
    - 10 max positions (vs PEGASUS's 5)
    - 0.8 SD multiplier for closer strikes (vs PEGASUS's 1.0)
    - $12 spread widths (vs PEGASUS's $10)
    - 30-minute cooldown for multiple trades per day

    Similar to PEGASUS but more aggressive, trading daily with higher frequency.
    """
    full_reasoning = kwargs.pop('full_reasoning', '')
    action_taken = kwargs.pop('action_taken', '')
    error_type = kwargs.pop('error_type', '')

    # Generate action description based on outcome
    if trade_executed:
        action_taken = action_taken or "EXECUTED: SPX Iron Condor position opened"
        full_reasoning = full_reasoning or f"TITAN opened IC position | {oracle_reasoning}"
    elif outcome == ScanOutcome.NO_TRADE:
        action_taken = action_taken or "NO_TRADE: Conditions not met"
        full_reasoning = full_reasoning or f"TITAN scan - no trade: {decision_summary}"
    elif outcome == ScanOutcome.SKIP:
        action_taken = action_taken or f"SKIP: {decision_summary}"
        full_reasoning = full_reasoning or f"TITAN skipped: {decision_summary}"
    elif outcome == ScanOutcome.MARKET_CLOSED:
        action_taken = "MARKET_CLOSED"
        full_reasoning = "Market is closed"
    elif outcome == ScanOutcome.ERROR:
        action_taken = f"ERROR: {error_message}"
        full_reasoning = f"TITAN error: {error_message}"
    else:
        action_taken = action_taken or f"{outcome.value}: {decision_summary}"
        full_reasoning = full_reasoning or decision_summary

    return log_scan_activity(
        bot_name="TITAN",
        outcome=outcome,
        decision_summary=decision_summary,
        action_taken=action_taken,
        full_reasoning=full_reasoning,
        market_data=market_data,
        gex_data=gex_data,
        checks=checks,
        signal_source=signal_source,
        signal_direction=signal_direction,
        signal_confidence=signal_confidence,
        signal_win_probability=signal_win_probability,
        oracle_advice=oracle_advice,
        oracle_reasoning=oracle_reasoning,
        oracle_win_probability=oracle_win_probability,
        oracle_confidence=oracle_confidence,
        oracle_top_factors=oracle_top_factors,
        oracle_probabilities=oracle_probabilities,
        oracle_suggested_strikes=oracle_suggested_strikes,
        oracle_thresholds=oracle_thresholds,
        min_win_probability_threshold=min_win_probability_threshold,
        risk_reward_ratio=risk_reward_ratio,
        trade_executed=trade_executed,
        error_message=error_message,
        error_type=error_type,
        generate_ai_explanation=generate_ai_explanation,
        **kwargs
    )