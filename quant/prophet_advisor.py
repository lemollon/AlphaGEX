"""
PROPHET - Multi-Strategy ML Advisor for AlphaGEX Trading Bots
=============================================================

Named after the Greek deity of prophecy and wisdom.

PURPOSE:
Prophet is the central advisory system that aggregates multiple signals
(GEX, ML predictions, VIX regime, market conditions) and provides
curated recommendations to each trading bot:

    - FORTRESS: Iron Condor advice (strikes, risk %, skip signals)
    - CORNERSTONE: Wheel strategy advice (CSP entry, assignment handling)
    - LAZARUS: Directional call advice (entry timing, position sizing)

ARCHITECTURE:
    ┌─────────────────────────────────────────────────────────┐
    │                      PROPHET                              │
    │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐      │
    │  │ GEX Signals │  │ ML Model    │  │ VIX Regime  │      │
    │  └─────────────┘  └─────────────┘  └─────────────┘      │
    │                         │                                │
    │              ┌──────────┴──────────┐                    │
    │              │  Signal Aggregator  │                    │
    │              └──────────┬──────────┘                    │
    └─────────────────────────┼───────────────────────────────┘
                              │
           ┌──────────────────┼──────────────────┐
           │                  │                  │
           ▼                  ▼                  ▼
      ┌─────────┐       ┌─────────┐       ┌─────────┐
      │  FORTRESS   │       │  CORNERSTONE  │       │ LAZARUS │
      │   IC    │       │  Wheel  │       │  Calls  │
      └─────────┘       └─────────┘       └─────────┘

FEEDBACK LOOP:
    CHRONICLES Backtests --> Extract Features --> Train Model
            ^                                      |
            |                                      v
    Store Outcome <-- Bot Live Trade <-- Query Prophet

Author: AlphaGEX Quant
Date: 2025-12-10
"""
from __future__ import annotations

import os
import sys
import math
import json
import pickle
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple, Any, TYPE_CHECKING
from dataclasses import dataclass, asdict, field
from enum import Enum
import warnings
import threading

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Claude AI - Direct Anthropic SDK (no LangChain needed!)
try:
    import anthropic
    CLAUDE_AVAILABLE = True
except ImportError:
    CLAUDE_AVAILABLE = False
    anthropic = None
    print("Info: Anthropic SDK not available. Install with: pip install anthropic")

# ML imports
try:
    import numpy as np
    import pandas as pd
    from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
    from sklearn.preprocessing import StandardScaler
    from sklearn.model_selection import TimeSeriesSplit
    from sklearn.metrics import (
        accuracy_score, precision_score, recall_score, f1_score,
        roc_auc_score, brier_score_loss, confusion_matrix
    )
    from sklearn.calibration import CalibratedClassifierCV
    ML_AVAILABLE = True
except ImportError:
    ML_AVAILABLE = False
    np = None
    pd = None
    print("Warning: ML libraries not available. Install with: pip install scikit-learn pandas numpy")

# Database
try:
    from database_adapter import get_connection
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False

# Price Trend Tracker for NEUTRAL regime handling
try:
    from quant.price_trend_tracker import (
        get_trend_tracker, PriceTrendTracker, TrendDirection,
        TrendAnalysis, WallPositionAnalysis, StrategySuitability
    )
    TREND_TRACKER_AVAILABLE = True
except ImportError:
    TREND_TRACKER_AVAILABLE = False
    get_trend_tracker = None
    logger.info("Price trend tracker not available - NEUTRAL regime will use legacy logic")

# Proverbs Feedback Loop - Advisory data for Prophet
PROVERBS_AVAILABLE = False
try:
    from quant.proverbs_enhancements import get_proverbs_enhanced
    PROVERBS_AVAILABLE = True
except ImportError:
    get_proverbs_enhanced = None
    print("Info: Proverbs enhanced features not available")

# GEX Signal Integration - ML direction for SOLOMON/GIDEON
GEX_ML_AVAILABLE = False
_gex_signal_integration = None
_gex_signal_lock = threading.Lock()  # V3 FIX: Thread-safe singleton initialization
try:
    from quant.gex_signal_integration import GEXSignalIntegration
    GEX_ML_AVAILABLE = True
except ImportError:
    GEXSignalIntegration = None
    print("Info: GEX Signal Integration not available")

# Context manager for safe database connections (prevents connection leaks)
from contextlib import contextmanager

@contextmanager
def get_db_connection():
    """
    Context manager for database connections.

    Ensures connections are always closed, even if an exception occurs.

    Usage:
        with get_db_connection() as conn:
            if conn is None:
                return  # DB not available
            cursor = conn.cursor()
            cursor.execute(...)
    """
    conn = None
    try:
        if not DB_AVAILABLE:
            yield None
        else:
            conn = get_connection()
            yield conn
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

# Comprehensive bot logger
try:
    from trading.bot_logger import (
        log_bot_decision, BotDecision, MarketContext as BotLogMarketContext,
        ClaudeContext, generate_session_id
    )
    BOT_LOGGER_AVAILABLE = True
except ImportError:
    BOT_LOGGER_AVAILABLE = False
    log_bot_decision = None

logger = logging.getLogger(__name__)


# =============================================================================
# ENUMS AND DATA CLASSES
# =============================================================================

class BotName(Enum):
    """Trading bots that Prophet advises"""
    FORTRESS = "FORTRESS"          # Aggressive Iron Condor (SPY 0DTE)
    CORNERSTONE = "CORNERSTONE"        # SPX Wheel Strategy
    LAZARUS = "LAZARUS"    # Directional Calls
    SHEPHERD = "SHEPHERD"      # Manual Wheel via UI
    SOLOMON = "SOLOMON"      # Directional Spreads (Bull Call / Bear Call)
    ANCHOR = "ANCHOR"    # SPX Iron Condor ($10 spreads, weekly)
    GIDEON = "GIDEON"      # Aggressive Directional Spreads (relaxed filters)
    SAMSON = "SAMSON"        # Aggressive SPX Iron Condor ($12 spreads)
    JUBILEE = "JUBILEE"  # Box Spread Synthetic Borrowing + IC Trading


class TradeOutcome(Enum):
    """Possible trade outcomes"""
    MAX_PROFIT = "MAX_PROFIT"
    PUT_BREACHED = "PUT_BREACHED"
    CALL_BREACHED = "CALL_BREACHED"
    DOUBLE_BREACH = "DOUBLE_BREACH"
    PARTIAL_PROFIT = "PARTIAL_PROFIT"
    LOSS = "LOSS"


class TradingAdvice(Enum):
    """Prophet advice levels"""
    TRADE_FULL = "TRADE_FULL"           # High confidence, full size
    TRADE_REDUCED = "TRADE_REDUCED"     # Medium confidence, reduce size
    SKIP_TODAY = "SKIP_TODAY"           # Low confidence, don't trade


class StrategyType(Enum):
    """Strategy types for IC vs Directional selection"""
    IRON_CONDOR = "IRON_CONDOR"         # FORTRESS/ANCHOR - profit when pinned
    DIRECTIONAL = "DIRECTIONAL"         # SOLOMON - profit when price moves
    SKIP = "SKIP"                       # Market too uncertain


class VIXRegime(Enum):
    """VIX-based volatility regime"""
    LOW = "LOW"                # VIX < 15 - cheap options, low premium
    NORMAL = "NORMAL"          # VIX 15-22 - ideal for IC
    ELEVATED = "ELEVATED"      # VIX 22-28 - cautious IC, consider directional
    HIGH = "HIGH"              # VIX 28-35 - favor directional
    EXTREME = "EXTREME"        # VIX > 35 - favor directional or skip


class GEXRegime(Enum):
    """GEX market regime"""
    POSITIVE = "POSITIVE"    # Mean reversion, good for premium selling
    NEGATIVE = "NEGATIVE"    # Trending, bad for premium selling
    NEUTRAL = "NEUTRAL"      # Mixed signals


@dataclass
class MarketContext:
    """Current market conditions for Prophet"""
    # Price
    spot_price: float
    price_change_1d: float = 0

    # Volatility
    vix: float = 20.0
    vix_percentile_30d: float = 50.0
    vix_change_1d: float = 0

    # GEX
    gex_net: float = 0
    gex_normalized: float = 0
    gex_regime: GEXRegime = GEXRegime.NEUTRAL
    gex_flip_point: float = 0
    gex_call_wall: float = 0
    gex_put_wall: float = 0
    gex_distance_to_flip_pct: float = 0
    gex_between_walls: bool = True

    # Time
    day_of_week: int = 2
    days_to_opex: int = 15

    # Historical
    win_rate_30d: float = 0.68
    expected_move_pct: float = 1.0

    # =========================================================================
    # TREND DATA (for NEUTRAL regime direction determination)
    # These fields are populated by PriceTrendTracker on every 5-min scan
    # =========================================================================
    trend_direction: str = "SIDEWAYS"  # UPTREND, DOWNTREND, SIDEWAYS
    trend_strength: float = 0.0  # 0-1
    price_5m_ago: float = 0.0
    price_30m_ago: float = 0.0
    price_60m_ago: float = 0.0
    is_higher_high: bool = False
    is_higher_low: bool = False
    position_in_range_pct: float = 50.0  # 0% = at put wall, 100% = at call wall
    is_contained: bool = True  # Price between walls


@dataclass
class ProphetPrediction:
    """Prediction from Prophet for a specific bot"""
    bot_name: BotName
    advice: TradingAdvice
    win_probability: float
    confidence: float
    suggested_risk_pct: float
    suggested_sd_multiplier: float

    # GEX-specific for FORTRESS
    use_gex_walls: bool = False
    suggested_put_strike: Optional[float] = None
    suggested_call_strike: Optional[float] = None

    # Explanation
    top_factors: List[Tuple[str, float]] = field(default_factory=list)
    reasoning: str = ""
    model_version: str = "1.0.0"

    # Raw probabilities
    probabilities: Dict[str, float] = None

    # Claude AI analysis data for logging transparency
    claude_analysis: Optional['ClaudeAnalysis'] = None

    # Strategy recommendation: When SKIP_TODAY, may suggest alternative bot
    # e.g., FORTRESS skip due to high VIX -> suggest SOLOMON directional
    suggested_alternative: Optional[BotName] = None
    strategy_recommendation: Optional['StrategyRecommendation'] = None

    # =========================================================================
    # NEUTRAL REGIME ANALYSIS (new fields for trend-based direction)
    # =========================================================================
    neutral_derived_direction: str = ""  # Direction derived for NEUTRAL regime
    neutral_confidence: float = 0.0  # Confidence in derived direction
    neutral_reasoning: str = ""  # Full reasoning for the derivation

    # Strategy suitability scores (0-1)
    ic_suitability: float = 0.0  # Iron Condor suitability
    bullish_suitability: float = 0.0  # Bull spread suitability
    bearish_suitability: float = 0.0  # Bear spread suitability

    # Trend analysis data
    trend_direction: str = ""  # UPTREND, DOWNTREND, SIDEWAYS
    trend_strength: float = 0.0
    position_in_range_pct: float = 50.0  # Where price sits in wall range
    wall_filter_passed: bool = False

    # =========================================================================
    # MODEL STALENESS TRACKING (Issue #1 & #4 fix)
    # Allows bots to know how fresh the model is and adjust confidence
    # =========================================================================
    prediction_id: Optional[int] = None  # Links prediction to outcome (Issue #3)
    hours_since_training: float = 0.0  # Hours since model was last trained
    model_loaded_at: Optional[str] = None  # ISO timestamp when model was loaded
    is_model_fresh: bool = True  # True if model < 24 hours old


@dataclass
class StrategyRecommendation:
    """
    Strategy recommendation based on VIX + GEX regime analysis.

    This helps decide: Should we trade Iron Condors (FORTRESS/ANCHOR)
    or Directional Spreads (SOLOMON) given current market conditions?

    Decision Matrix:
    ┌─────────────┬────────────────┬────────────────┬────────────────┐
    │ VIX Regime  │  GEX POSITIVE  │  GEX NEUTRAL   │  GEX NEGATIVE  │
    ├─────────────┼────────────────┼────────────────┼────────────────┤
    │ LOW (<15)   │  IC (reduced)  │  SKIP          │  DIRECTIONAL   │
    │ NORMAL      │  IC (full)     │  IC (reduced)  │  DIRECTIONAL   │
    │ ELEVATED    │  IC (reduced)  │  DIRECTIONAL   │  DIRECTIONAL   │
    │ HIGH        │  DIRECTIONAL   │  DIRECTIONAL   │  DIRECTIONAL   │
    │ EXTREME     │  SKIP          │  SKIP          │  DIRECTIONAL   │
    └─────────────┴────────────────┴────────────────┴────────────────┘
    """
    recommended_strategy: StrategyType
    vix_regime: VIXRegime
    gex_regime: GEXRegime
    confidence: float  # 0-1 how confident in the recommendation

    # Why this strategy
    reasoning: str

    # Strategy-specific details
    ic_suitability: float = 0.0   # 0-1 how suitable for Iron Condor
    dir_suitability: float = 0.0  # 0-1 how suitable for Directional

    # Suggested position sizing multiplier (0.25, 0.5, 0.75, 1.0)
    size_multiplier: float = 1.0

    # Raw market data for transparency
    vix: float = 0.0
    spot_price: float = 0.0


@dataclass
class TrainingMetrics:
    """Metrics from model training"""
    accuracy: float
    precision: float
    recall: float
    f1_score: float
    auc_roc: float
    brier_score: float

    win_rate_predicted: float
    win_rate_actual: float

    total_samples: int
    train_samples: int
    test_samples: int
    positive_samples: int
    negative_samples: int

    feature_importances: Dict[str, float]
    training_date: str
    model_version: str


@dataclass
class ClaudeAnalysis:
    """Claude AI analysis result with full transparency"""
    analysis: str
    confidence_adjustment: float  # -0.1 to +0.1 adjustment
    risk_factors: List[str]
    opportunities: List[str]
    recommendation: str  # "AGREE", "ADJUST", "OVERRIDE"
    override_advice: Optional[str] = None
    # Raw Claude interaction data for logging transparency
    raw_prompt: Optional[str] = None
    raw_response: Optional[str] = None
    tokens_used: int = 0  # input_tokens + output_tokens
    input_tokens: int = 0
    output_tokens: int = 0
    response_time_ms: int = 0
    model_used: Optional[str] = None
    # Anti-hallucination fields
    hallucination_risk: str = "LOW"  # LOW, MEDIUM, HIGH
    data_citations: List[str] = None  # List of data points Claude cited
    hallucination_warnings: List[str] = None  # Specific warnings about potential hallucinations


@dataclass
class ProverbsAdvisory:
    """
    Advisory data from Proverbs Feedback Loop.

    These are SUGGESTIONS to Prophet - Prophet remains the final decision maker.
    Proverbs provides historical performance data to help Prophet make better decisions.
    """
    # Time-of-day analysis
    is_optimal_hour: bool = True  # Is this hour historically good for this bot?
    hour_win_rate: float = 0.0  # Historical win rate for this hour
    hour_avg_pnl: float = 0.0  # Historical average P&L for this hour
    best_hour: Optional[int] = None  # Best performing hour (0-23)
    worst_hour: Optional[int] = None  # Worst performing hour (0-23)
    time_of_day_adjustment: float = 0.0  # Score adjustment (-0.2 to +0.1)

    # Regime performance analysis
    regime_ic_win_rate: float = 0.0  # IC win rate in current regime
    regime_dir_win_rate: float = 0.0  # Directional win rate in current regime
    regime_recommendation: str = "NEUTRAL"  # IC_PREFERRED, DIR_PREFERRED, NEUTRAL
    regime_adjustment: float = 0.0  # Score adjustment based on regime history

    # Cross-bot correlation
    correlated_bots_active: List[str] = field(default_factory=list)  # Other bots with positions
    correlation_risk: str = "LOW"  # LOW, MEDIUM, HIGH
    size_reduction_pct: float = 0.0  # Suggested size reduction due to correlation

    # Weekend pre-check (for Friday trading)
    weekend_gap_prediction: str = "NEUTRAL"  # GAP_UP, GAP_DOWN, NEUTRAL
    weekend_risk_level: str = "NORMAL"  # LOW, NORMAL, HIGH, EXTREME
    friday_size_adjustment: float = 1.0  # Multiplier for Friday positions

    # Active proposals for this bot
    pending_proposal: bool = False
    proposal_summary: Optional[str] = None

    # Overall Proverbs confidence
    data_quality: str = "GOOD"  # GOOD, LIMITED, NONE
    proverbs_confidence: float = 0.5  # How confident Proverbs is in its advice

    def get_combined_adjustment(self) -> float:
        """Get combined score adjustment from all Proverbs factors"""
        return self.time_of_day_adjustment + self.regime_adjustment


# =============================================================================
# CLAUDE AI ENHANCER
# =============================================================================

# =============================================================================
# PROPHET LIVE LOG - For Frontend Transparency
# =============================================================================

class ProphetLiveLog:
    """
    Live logging system for Prophet - FULL TRANSPARENCY.
    Captures every piece of data flowing through Prophet for frontend visibility.
    Thread-safe singleton implementation.
    """
    _instance = None
    _instance_lock = threading.Lock()
    MAX_LOGS = 500  # Increased for more history
    MAX_DATA_FLOWS = 100  # Store detailed data flow records

    def __new__(cls):
        if cls._instance is None:
            with cls._instance_lock:
                # Double-check locking pattern for thread safety
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._logs = []
                    cls._instance._callbacks = []
                    cls._instance._data_flows = []  # Full data pipeline records
                    cls._instance._claude_exchanges = []  # Complete Claude prompt/response pairs
                    cls._instance._log_lock = threading.Lock()  # Lock for list operations
        return cls._instance

    def log(self, event_type: str, message: str, data: Optional[Dict] = None):
        """Add a log entry (thread-safe)"""
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
            "type": event_type,
            "message": message,
            "data": data
        }

        with self._log_lock:
            self._logs.append(entry)

            # Keep only recent logs
            if len(self._logs) > self.MAX_LOGS:
                self._logs = self._logs[-self.MAX_LOGS:]

        # Notify callbacks (outside lock to prevent deadlocks)
        for callback in self._callbacks:
            try:
                callback(entry)
            except Exception as e:
                # Log callback errors but don't let them break the logging system
                logger.debug(f"Prophet live log callback error: {e}")

        # Also log to standard logger
        logger.info(f"[PROPHET] {event_type}: {message}")

    def log_data_flow(self, bot_name: str, stage: str, data: Dict):
        """
        Log a complete data flow step for full transparency (thread-safe).

        Stages: INPUT, ML_FEATURES, ML_OUTPUT, CLAUDE_PROMPT, CLAUDE_RESPONSE,
                DECISION, SENT_TO_BOT, ANTI_HALLUCINATION_CHECK
        """
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
            "bot_name": bot_name,
            "stage": stage,
            "data": data
        }

        with self._log_lock:
            self._data_flows.append(entry)

            # Keep only recent
            if len(self._data_flows) > self.MAX_DATA_FLOWS:
                self._data_flows = self._data_flows[-self.MAX_DATA_FLOWS:]

        # Also add to regular logs with summary
        self.log(f"DATA_FLOW_{stage}", f"{bot_name}: {stage}", {
            "bot": bot_name,
            "stage": stage,
            "summary": self._summarize_data(data, stage)
        })

    def log_claude_exchange(self, bot_name: str, prompt: str, response: str,
                           market_context: Dict, ml_prediction: Dict,
                           tokens_used: int = 0, response_time_ms: int = 0,
                           model: str = "", hallucination_risk: str = "LOW",
                           hallucination_warnings: List = None,
                           data_citations: List = None):
        """
        Log a complete Claude AI exchange with full context (thread-safe).
        This is the key for transparency - shows exactly what AI sees and says.
        Includes anti-hallucination validation results.
        """
        exchange = {
            "timestamp": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
            "bot_name": bot_name,
            "market_context": market_context,
            "ml_prediction": ml_prediction,
            "prompt_sent": prompt,
            "response_received": response,
            "tokens_used": tokens_used,
            "response_time_ms": response_time_ms,
            "model": model,
            "hallucination_risk": hallucination_risk,
            "hallucination_warnings": hallucination_warnings or [],
            "data_citations": data_citations or []
        }

        with self._log_lock:
            self._claude_exchanges.append(exchange)

            # Keep only recent
            if len(self._claude_exchanges) > self.MAX_DATA_FLOWS:
                self._claude_exchanges = self._claude_exchanges[-self.MAX_DATA_FLOWS:]

        # Log summary with hallucination status
        self.log("CLAUDE_EXCHANGE", f"{bot_name}: Claude AI consulted (Hallucination Risk: {hallucination_risk})", {
            "bot": bot_name,
            "tokens": tokens_used,
            "time_ms": response_time_ms,
            "model": model,
            "prompt_length": len(prompt),
            "response_length": len(response),
            "hallucination_risk": hallucination_risk,
            "hallucination_warnings_count": len(hallucination_warnings or [])
        })

    def _summarize_data(self, data: Dict, stage: str) -> Dict:
        """Create a summary of data for log display"""
        if stage == "INPUT":
            return {
                "spot_price": data.get("spot_price"),
                "vix": data.get("vix"),
                "gex_regime": data.get("gex_regime"),
                "gex_net": data.get("gex_net")
            }
        elif stage == "ML_OUTPUT":
            return {
                "win_probability": data.get("win_probability"),
                "advice": data.get("advice")
            }
        elif stage == "DECISION":
            return {
                "final_advice": data.get("advice"),
                "win_prob": data.get("win_probability"),
                "claude_validated": data.get("claude_validated", False)
            }
        return {"keys": list(data.keys())[:5]}

    def get_logs(self, limit: int = 50) -> List[Dict]:
        """Get recent logs"""
        return self._logs[-limit:]

    def get_data_flows(self, limit: int = 50, bot_name: str = None) -> List[Dict]:
        """Get detailed data flow records"""
        flows = self._data_flows
        if bot_name:
            flows = [f for f in flows if f.get("bot_name") == bot_name]
        return flows[-limit:]

    def get_claude_exchanges(self, limit: int = 20, bot_name: str = None) -> List[Dict]:
        """Get complete Claude AI exchanges with full prompt/response"""
        exchanges = self._claude_exchanges
        if bot_name:
            exchanges = [e for e in exchanges if e.get("bot_name") == bot_name]
        return exchanges[-limit:]

    def get_latest_flow_for_bot(self, bot_name: str) -> Optional[Dict]:
        """Get the most recent complete data flow for a specific bot"""
        bot_flows = [f for f in self._data_flows if f.get("bot_name") == bot_name]
        if bot_flows:
            return bot_flows[-1]
        return None

    def clear(self):
        """Clear all logs"""
        self._logs = []
        self._data_flows = []
        self._claude_exchanges = []

    def add_callback(self, callback):
        """Add callback for real-time log streaming"""
        self._callbacks.append(callback)

    def remove_callback(self, callback):
        """Remove callback"""
        if callback in self._callbacks:
            self._callbacks.remove(callback)


# Global live log instance
prophet_live_log = ProphetLiveLog()


class ProphetClaudeEnhancer:
    """
    Claude AI integration for Prophet predictions.
    Uses direct Anthropic SDK (no LangChain needed!).

    Provides three key capabilities:
    1. Validate and enhance ML predictions with reasoning
    2. Explain Prophet reasoning in natural language
    3. Identify patterns in training data
    """

    CLAUDE_MODEL = "claude-sonnet-4-5-20250929"  # Sonnet 4.5 - latest model

    def __init__(self, api_key: Optional[str] = None):
        """Initialize Claude AI enhancer"""
        # Check both ANTHROPIC_API_KEY and CLAUDE_API_KEY
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY")
        self._client = None
        self._enabled = False
        self.live_log = prophet_live_log

        if CLAUDE_AVAILABLE and self.api_key:
            try:
                self._client = anthropic.Anthropic(api_key=self.api_key)
                self._enabled = True
                self.live_log.log("INIT", f"Claude AI enabled (model: {self.CLAUDE_MODEL})")
            except Exception as e:
                self.live_log.log("ERROR", f"Failed to initialize Claude: {e}")
        else:
            if not CLAUDE_AVAILABLE:
                self.live_log.log("WARN", "Claude AI not available (pip install anthropic)")
            elif not self.api_key:
                self.live_log.log("WARN", "Claude AI not available (no API key - set ANTHROPIC_API_KEY or CLAUDE_API_KEY)")

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    @staticmethod
    def _sanitize_for_prompt(value: Any) -> str:
        """
        Sanitize a value before including it in a Claude prompt.

        Prevents prompt injection by:
        1. Converting to string
        2. Removing/escaping dangerous patterns
        3. Truncating excessively long strings
        """
        if value is None:
            return "N/A"

        # Convert to string
        s = str(value)

        # Remove common prompt injection patterns
        dangerous_patterns = [
            "ignore previous",
            "ignore above",
            "disregard",
            "forget everything",
            "new instructions",
            "system prompt",
            "```",
            "SYSTEM:",
            "USER:",
            "ASSISTANT:",
        ]

        s_lower = s.lower()
        for pattern in dangerous_patterns:
            if pattern.lower() in s_lower:
                s = s.replace(pattern, "[FILTERED]")
                s = s.replace(pattern.lower(), "[FILTERED]")
                s = s.replace(pattern.upper(), "[FILTERED]")

        # Limit length to prevent context stuffing
        max_len = 500
        if len(s) > max_len:
            s = s[:max_len] + "...[truncated]"

        return s

    # =========================================================================
    # 1. VALIDATE/ENHANCE ML PREDICTIONS
    # =========================================================================

    def validate_prediction(
        self,
        context: 'MarketContext',
        ml_prediction: Dict[str, Any],
        bot_name: BotName
    ) -> ClaudeAnalysis:
        """
        Use Claude to validate and potentially adjust ML prediction.

        Args:
            context: Current market conditions
            ml_prediction: ML model's prediction dict
            bot_name: Which bot is requesting advice

        Returns:
            ClaudeAnalysis with validation result
        """
        if not self._enabled:
            return ClaudeAnalysis(
                analysis="Claude AI not available",
                confidence_adjustment=0.0,
                risk_factors=[],
                opportunities=[],
                recommendation="AGREE"
            )

        day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

        system_prompt = """You are an expert options trading analyst validating ML predictions for the Prophet system.

Your job is to review the ML model's prediction and market context, then:
1. Identify any risk factors the ML model might have missed
2. Identify opportunities the context suggests
3. Recommend whether to AGREE, ADJUST (small confidence change), or OVERRIDE (significant change)
4. Suggest a confidence adjustment (-0.10 to +0.10)

CRITICAL ANTI-HALLUCINATION RULES:
- You MUST cite ONLY the exact data values provided in the MARKET CONTEXT and ML PREDICTION sections
- Every claim you make MUST reference a specific data point (e.g., "VIX at 18.5 indicates...")
- DO NOT invent data, metrics, or facts not provided in the input
- If you're uncertain about something, say "Based on the provided data..." rather than making assumptions
- In your DATA_CITATIONS section, list the exact data points you used for your analysis

Be concise and data-driven. Focus ONLY on data provided: GEX regime, VIX levels, and day-of-week patterns."""

        # Sanitize any string values that could potentially be manipulated
        sanitized_top_factors = self._sanitize_for_prompt(ml_prediction.get('top_factors', []))

        user_prompt = f"""Validate this ML prediction for {bot_name.value}:

MARKET CONTEXT:
- Spot Price: ${context.spot_price:,.2f}
- VIX: {context.vix:.1f}
- VIX Change 1d: {context.vix_change_1d:+.1f}%
- GEX Regime: {context.gex_regime.value}
- GEX Normalized: {context.gex_normalized:.6f}
- Between GEX Walls: {"Yes" if context.gex_between_walls else "No"}
- Day of Week: {day_names[context.day_of_week]}

ML PREDICTION:
- Win Probability: {ml_prediction.get('win_probability', 0.68):.1%}
- Top Factors: {sanitized_top_factors}

Provide your analysis in this format:
DATA_CITATIONS: [List the exact data values you're basing your analysis on, e.g., "VIX=18.5, GEX_REGIME=POSITIVE, Day=Monday"]
ANALYSIS: [Your analysis in 2-3 sentences, citing specific data values]
RISK_FACTORS: [Comma-separated list, each citing a data point]
OPPORTUNITIES: [Comma-separated list, each citing a data point]
CONFIDENCE_ADJUSTMENT: [Number between -0.10 and +0.10]
RECOMMENDATION: [AGREE/ADJUST/OVERRIDE]
OVERRIDE_ADVICE: [Only if OVERRIDE, what advice to give instead]"""

        self.live_log.log("VALIDATE", f"Validating {bot_name.value} prediction...", {
            "vix": context.vix,
            "gex_regime": context.gex_regime.value,
            "win_prob": ml_prediction.get('win_probability', 0.68)
        })

        # Build full prompt for logging
        full_prompt = f"SYSTEM:\n{system_prompt}\n\nUSER:\n{user_prompt}"

        try:
            start_time = time.time()
            message = self._client.messages.create(
                model=self.CLAUDE_MODEL,
                max_tokens=1024,
                messages=[
                    {"role": "user", "content": user_prompt}
                ],
                system=system_prompt
            )
            response_time_ms = int((time.time() - start_time) * 1000)

            # Safe access to Claude response content
            if not message.content or len(message.content) == 0:
                self.live_log.log("ERROR", "Claude returned empty content array")
                return ClaudeValidation(
                    recommendation="PROCEED",
                    confidence_adjustment=0.0,
                    risk_factors=[],
                    reasoning="Claude returned empty response"
                )
            response = message.content[0].text

            # Extract token counts from response
            input_tokens = getattr(message.usage, 'input_tokens', 0) if hasattr(message, 'usage') else 0
            output_tokens = getattr(message.usage, 'output_tokens', 0) if hasattr(message, 'usage') else 0
            tokens_used = input_tokens + output_tokens

            result = self._parse_validation_response(response, context=context, ml_prediction=ml_prediction)

            # Add raw Claude data for transparency
            result.raw_prompt = full_prompt
            result.raw_response = response
            result.tokens_used = tokens_used
            result.input_tokens = input_tokens
            result.output_tokens = output_tokens
            result.response_time_ms = response_time_ms
            result.model_used = self.CLAUDE_MODEL

            self.live_log.log("VALIDATE_DONE", f"Claude recommends: {result.recommendation}", {
                "confidence_adj": result.confidence_adjustment,
                "risk_factors": result.risk_factors,
                "tokens": tokens_used,
                "time_ms": response_time_ms
            })

            # Log complete Claude exchange for full transparency
            day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
            market_context_dict = {
                "spot_price": context.spot_price,
                "vix": context.vix,
                "vix_change_1d": context.vix_change_1d,
                "gex_regime": context.gex_regime.value,
                "gex_normalized": context.gex_normalized,
                "gex_net": context.gex_net,
                "gex_flip_point": context.gex_flip_point,
                "gex_call_wall": context.gex_call_wall,
                "gex_put_wall": context.gex_put_wall,
                "gex_between_walls": context.gex_between_walls,
                "day_of_week": day_names[context.day_of_week] if 0 <= context.day_of_week < 7 else "Unknown",
                "days_to_opex": context.days_to_opex
            }
            self.live_log.log_claude_exchange(
                bot_name=bot_name.value,
                prompt=full_prompt,
                response=response,
                market_context=market_context_dict,
                ml_prediction=ml_prediction,
                tokens_used=tokens_used,
                response_time_ms=response_time_ms,
                model=self.CLAUDE_MODEL,
                hallucination_risk=result.hallucination_risk,
                hallucination_warnings=result.hallucination_warnings,
                data_citations=result.data_citations
            )

            return result

        except Exception as e:
            self.live_log.log("ERROR", f"Claude validation failed: {e}")
            return ClaudeAnalysis(
                analysis=f"Validation error: {str(e)}",
                confidence_adjustment=0.0,
                risk_factors=[],
                opportunities=[],
                recommendation="AGREE",
                raw_prompt=full_prompt
            )

    def _parse_validation_response(self, response: str, context: 'MarketContext' = None,
                                     ml_prediction: Dict = None) -> ClaudeAnalysis:
        """Parse Claude's validation response with hallucination detection"""
        lines = response.strip().split('\n')

        analysis = ""
        risk_factors = []
        opportunities = []
        confidence_adj = 0.0
        recommendation = "AGREE"
        override_advice = None
        data_citations = []

        for line in lines:
            line = line.strip()
            if line.startswith("DATA_CITATIONS:"):
                citations_str = line.replace("DATA_CITATIONS:", "").strip()
                data_citations = [c.strip() for c in citations_str.split(",") if c.strip()]
            elif line.startswith("ANALYSIS:"):
                analysis = line.replace("ANALYSIS:", "").strip()
            elif line.startswith("RISK_FACTORS:"):
                factors = line.replace("RISK_FACTORS:", "").strip()
                risk_factors = [f.strip() for f in factors.split(",") if f.strip()]
            elif line.startswith("OPPORTUNITIES:"):
                opps = line.replace("OPPORTUNITIES:", "").strip()
                opportunities = [o.strip() for o in opps.split(",") if o.strip()]
            elif line.startswith("CONFIDENCE_ADJUSTMENT:"):
                try:
                    adj_str = line.replace("CONFIDENCE_ADJUSTMENT:", "").strip()
                    confidence_adj = float(adj_str)
                    confidence_adj = max(-0.10, min(0.10, confidence_adj))
                except ValueError:
                    confidence_adj = 0.0
            elif line.startswith("RECOMMENDATION:"):
                rec = line.replace("RECOMMENDATION:", "").strip().upper()
                if rec in ["AGREE", "ADJUST", "OVERRIDE"]:
                    recommendation = rec
            elif line.startswith("OVERRIDE_ADVICE:"):
                override_advice = line.replace("OVERRIDE_ADVICE:", "").strip()

        # Detect hallucination risk
        hallucination_risk, hallucination_warnings = self._detect_hallucination_risk(
            response=response,
            analysis=analysis,
            data_citations=data_citations,
            context=context,
            ml_prediction=ml_prediction
        )

        return ClaudeAnalysis(
            analysis=analysis,
            confidence_adjustment=confidence_adj,
            risk_factors=risk_factors,
            opportunities=opportunities,
            recommendation=recommendation,
            override_advice=override_advice,
            hallucination_risk=hallucination_risk,
            data_citations=data_citations,
            hallucination_warnings=hallucination_warnings
        )

    def _detect_hallucination_risk(
        self,
        response: str,
        analysis: str,
        data_citations: List[str],
        context: 'MarketContext' = None,
        ml_prediction: Dict = None
    ) -> tuple:
        """
        Detect potential hallucinations in Claude's response.

        Returns:
            Tuple of (risk_level: str, warnings: List[str])
        """
        warnings = []
        risk_score = 0

        # Check 1: No data citations provided
        if not data_citations:
            warnings.append("No data citations provided - response may not be grounded in input data")
            risk_score += 3

        # Check 2: Validate citations against actual input data if context is available
        if context and data_citations:
            valid_data_markers = [
                f"VIX={context.vix:.1f}",
                f"VIX {context.vix:.1f}",
                str(round(context.vix, 1)),
                context.gex_regime.value,
                f"${context.spot_price:,.0f}",
                f"${context.spot_price:,.2f}",
                str(round(context.spot_price, 2)),
            ]

            # Add day of week
            day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
            if 0 <= context.day_of_week < 7:
                valid_data_markers.append(day_names[context.day_of_week])

            # Check if at least one citation matches input data
            citations_text = " ".join(data_citations).upper()
            response_upper = response.upper()

            found_valid_citation = False
            for marker in valid_data_markers:
                if marker.upper() in citations_text or marker.upper() in response_upper:
                    found_valid_citation = True
                    break

            if not found_valid_citation:
                warnings.append("Citations don't match input data - potential fabricated values")
                risk_score += 2

        # Check 3: Look for common hallucination patterns
        hallucination_patterns = [
            ("according to recent", "Reference to external sources not provided"),
            ("studies show", "Reference to external studies not in input"),
            ("historical data suggests", "Reference to historical data not provided"),
            ("typically", "Generalization without citing specific input data"),
            ("usually", "Generalization without citing specific input data"),
            ("research indicates", "Reference to research not in input"),
            ("based on my knowledge", "Using external knowledge instead of input data"),
        ]

        response_lower = response.lower()
        for pattern, warning in hallucination_patterns:
            if pattern in response_lower:
                warnings.append(warning)
                risk_score += 1

        # Check 4: ML prediction win probability should be cited
        if ml_prediction:
            win_prob = ml_prediction.get('win_probability', 0.68)
            win_prob_str = f"{win_prob:.1%}"
            if win_prob_str not in response and str(round(win_prob * 100)) not in response:
                warnings.append("ML win probability not referenced in analysis")
                risk_score += 1

        # Check 5: Verify analysis isn't empty or generic
        if len(analysis) < 20:
            warnings.append("Analysis is too short to be meaningful")
            risk_score += 2

        # Determine risk level
        if risk_score >= 4:
            risk_level = "HIGH"
        elif risk_score >= 2:
            risk_level = "MEDIUM"
        else:
            risk_level = "LOW"

        return risk_level, warnings

    # =========================================================================
    # 2. EXPLAIN PROPHET REASONING
    # =========================================================================

    def explain_prediction(
        self,
        prediction: 'ProphetPrediction',
        context: 'MarketContext'
    ) -> str:
        """
        Generate natural language explanation of Prophet's prediction.

        Args:
            prediction: The Prophet prediction to explain
            context: Market context used for prediction

        Returns:
            Human-readable explanation string
        """
        if not self._enabled:
            return f"Prophet predicts {prediction.advice.value} with {prediction.win_probability:.1%} confidence. {prediction.reasoning}"

        day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

        system_prompt = """You are explaining Prophet's trading predictions to a human trader.

Write a clear, concise explanation (3-5 sentences) that:
1. States the recommendation in plain English
2. Explains the key factors driving the decision
3. Highlights any important risks or opportunities
4. Gives actionable guidance

Use a professional but approachable tone. Avoid jargon where possible."""

        # Sanitize reasoning text which may contain external data
        sanitized_reasoning = self._sanitize_for_prompt(prediction.reasoning)

        user_prompt = f"""Explain this Prophet prediction for {prediction.bot_name.value}:

PREDICTION:
- Advice: {prediction.advice.value}
- Win Probability: {prediction.win_probability:.1%}
- Suggested Risk %: {prediction.suggested_risk_pct:.1f}%
- Use GEX Walls: {"Yes" if prediction.use_gex_walls else "No"}
- Model Reasoning: {sanitized_reasoning}

MARKET CONTEXT:
- VIX: {context.vix:.1f}
- GEX Regime: {context.gex_regime.value}
- Day: {day_names[context.day_of_week]}
- Price between walls: {"Yes" if context.gex_between_walls else "No"}

Write a clear explanation for the trader."""

        self.live_log.log("EXPLAIN", f"Generating explanation for {prediction.bot_name.value}...")

        try:
            message = self._client.messages.create(
                model=self.CLAUDE_MODEL,
                max_tokens=512,
                messages=[
                    {"role": "user", "content": user_prompt}
                ],
                system=system_prompt
            )

            # Safe access to Claude response content
            if not message.content or len(message.content) == 0:
                return f"Prophet predicts {prediction.advice.value} with {prediction.win_probability:.1%} confidence. {prediction.reasoning}"
            explanation = message.content[0].text.strip()

            self.live_log.log("EXPLAIN_DONE", f"Explanation generated ({len(explanation)} chars)")

            return explanation

        except Exception as e:
            self.live_log.log("ERROR", f"Claude explanation failed: {e}")
            return f"Prophet predicts {prediction.advice.value} with {prediction.win_probability:.1%} confidence. {prediction.reasoning}"

    # =========================================================================
    # 3. IDENTIFY PATTERNS IN TRAINING DATA
    # =========================================================================

    def analyze_training_patterns(
        self,
        df: 'pd.DataFrame',
        recent_losses: Optional[List[Dict]] = None
    ) -> Dict[str, Any]:
        """
        Use Claude to identify patterns in CHRONICLES training data.

        Args:
            df: Training DataFrame with features and outcomes
            recent_losses: Optional list of recent losing trades

        Returns:
            Dict with pattern analysis and recommendations
        """
        if not self._enabled:
            return {
                "success": False,
                "error": "Claude AI not available",
                "patterns": [],
                "recommendations": []
            }

        if not ML_AVAILABLE or df is None or len(df) == 0:
            return {
                "success": False,
                "error": "No training data available",
                "patterns": [],
                "recommendations": []
            }

        # Calculate summary statistics for Claude
        try:
            total_trades = len(df)
            win_rate = df['is_win'].mean() * 100
            avg_vix = df['vix'].mean()
            vix_win = df[df['is_win'] == True]['vix'].mean() if 'is_win' in df.columns else avg_vix
            vix_loss = df[df['is_win'] == False]['vix'].mean() if 'is_win' in df.columns else avg_vix

            # Day of week analysis
            dow_stats = df.groupby('day_of_week')['is_win'].agg(['count', 'mean']).to_dict()

            # GEX regime analysis (if available)
            gex_stats = {}
            if 'gex_regime_positive' in df.columns:
                gex_stats = df.groupby('gex_regime_positive')['is_win'].agg(['count', 'mean']).to_dict()

            # Recent performance
            recent_30 = df.tail(30)
            recent_win_rate = recent_30['is_win'].mean() * 100 if len(recent_30) > 0 else win_rate

        except Exception as e:
            logger.error(f"Failed to calculate stats: {e}")
            return {
                "success": False,
                "error": str(e),
                "patterns": [],
                "recommendations": []
            }

        system_prompt = """You are a quantitative analyst reviewing trading data for pattern identification.

Analyze the provided statistics and identify:
1. Key patterns affecting win rate
2. Conditions that lead to losses
3. Optimal trading conditions
4. Actionable recommendations for the ML model

Be specific and data-driven. Focus on actionable insights."""

        # Sanitize stats that could contain manipulated data
        sanitized_dow_stats = self._sanitize_for_prompt(dow_stats)
        sanitized_gex_stats = self._sanitize_for_prompt(gex_stats)
        sanitized_recent_losses = self._sanitize_for_prompt(recent_losses or "None")

        user_prompt = f"""Analyze these CHRONICLES backtest statistics:

OVERALL PERFORMANCE:
- Total Trades: {total_trades}
- Win Rate: {win_rate:.1f}%
- Recent 30-Day Win Rate: {recent_win_rate:.1f}%

VIX ANALYSIS:
- Average VIX: {avg_vix:.1f}
- Avg VIX on Wins: {vix_win:.1f}
- Avg VIX on Losses: {vix_loss:.1f}

DAY OF WEEK STATS:
{sanitized_dow_stats}

GEX REGIME STATS:
{sanitized_gex_stats}

RECENT LOSSES (if any):
{sanitized_recent_losses}

Provide analysis in this format:
PATTERNS:
1. [Pattern 1]
2. [Pattern 2]
3. [Pattern 3]

LOSS_CONDITIONS:
- [Condition that leads to losses]

OPTIMAL_CONDITIONS:
- [Best conditions for trading]

RECOMMENDATIONS:
1. [Recommendation 1]
2. [Recommendation 2]
3. [Recommendation 3]"""

        self.live_log.log("PATTERNS", f"Analyzing {total_trades} trades for patterns...", {
            "win_rate": win_rate,
            "recent_win_rate": recent_win_rate
        })

        try:
            message = self._client.messages.create(
                model=self.CLAUDE_MODEL,
                max_tokens=1024,
                messages=[
                    {"role": "user", "content": user_prompt}
                ],
                system=system_prompt
            )

            # Safe access to Claude response content
            if not message.content or len(message.content) == 0:
                self.live_log.log("ERROR", "Claude returned empty content for pattern analysis")
                return {
                    "success": False,
                    "error": "Claude returned empty response",
                    "patterns": [],
                    "recommendations": []
                }
            response = message.content[0].text
            result = self._parse_pattern_response(response)

            self.live_log.log("PATTERNS_DONE", f"Found {len(result.get('patterns', []))} patterns", {
                "patterns": result.get('patterns', [])[:3]
            })

            return result

        except Exception as e:
            self.live_log.log("ERROR", f"Claude pattern analysis failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "patterns": [],
                "recommendations": []
            }

    def _parse_pattern_response(self, response: str) -> Dict[str, Any]:
        """Parse Claude's pattern analysis response"""
        result = {
            "success": True,
            "patterns": [],
            "loss_conditions": [],
            "optimal_conditions": [],
            "recommendations": [],
            "raw_analysis": response
        }

        current_section = None
        lines = response.strip().split('\n')

        for line in lines:
            line = line.strip()

            if line.startswith("PATTERNS:"):
                current_section = "patterns"
            elif line.startswith("LOSS_CONDITIONS:"):
                current_section = "loss_conditions"
            elif line.startswith("OPTIMAL_CONDITIONS:"):
                current_section = "optimal_conditions"
            elif line.startswith("RECOMMENDATIONS:"):
                current_section = "recommendations"
            elif line and current_section:
                # Remove leading numbers and dashes
                cleaned = line.lstrip("0123456789.-) ").strip()
                if cleaned:
                    result[current_section].append(cleaned)

        return result


# =============================================================================
# PROPHET ADVISOR
# =============================================================================

class ProphetAdvisor:
    """
    PROPHET - Central Advisory System for AlphaGEX Trading Bots

    Aggregates multiple signals and provides bot-specific recommendations.

    Features:
    - GEX-aware predictions
    - Bot-specific advice tailoring
    - PostgreSQL persistence for feedback loop
    - Real-time outcome updates
    """

    # V3 feature columns: cyclical day encoding, VRP, longer win rate horizon
    # Matches WISDOM V3 patterns for consistency across ML advisory layer
    FEATURE_COLS = [
        'vix',
        'vix_percentile_30d',
        'vix_change_1d',
        'day_of_week_sin',          # Cyclical encoding: sin(2*pi*dow/5)
        'day_of_week_cos',          # Cyclical encoding: cos(2*pi*dow/5)
        'price_change_1d',
        'expected_move_pct',
        'volatility_risk_premium',  # IV - realized vol (profit engine signal)
        'win_rate_60d',             # 60-trade rolling win rate (reduced leakage)
        # GEX features
        'gex_normalized',
        'gex_regime_positive',
        'gex_distance_to_flip_pct',
        'gex_between_walls',
    ]

    # V2 features with VIX regime for strategy selection (backward compat)
    FEATURE_COLS_V2 = [
        'vix',
        'vix_percentile_30d',
        'vix_change_1d',
        'day_of_week',
        'price_change_1d',
        'expected_move_pct',
        'win_rate_30d',
        # GEX features
        'gex_normalized',
        'gex_regime_positive',
        'gex_distance_to_flip_pct',
        'gex_between_walls',
    ]

    # V1 features (backward compatibility, no GEX)
    FEATURE_COLS_V1 = [
        'vix',
        'vix_percentile_30d',
        'vix_change_1d',
        'day_of_week',
        'price_change_1d',
        'expected_move_pct',
        'win_rate_30d',
    ]

    MODEL_PATH = os.path.join(os.path.dirname(__file__), '.models')

    def __init__(self, enable_claude: bool = True, omega_mode: bool = False):
        """
        Initialize Prophet Advisor.

        Args:
            enable_claude: Whether to enable Claude AI validation
            omega_mode: OMEGA Orchestrator mode - when True:
                - Disables strict VIX skip rules (defers to ML Advisor)
                - Integrates Ensemble signals for context
                - Acts as bot-specific adapter rather than decision maker
        """
        self.model = None
        self.calibrated_model = None
        self.scaler = None
        self.is_trained = False
        self.training_metrics: Optional[TrainingMetrics] = None
        self.model_version = "0.0.0"
        self._has_gex_features = False
        self._feature_version = 3  # V3 features (cyclical day, VRP, 60d win rate)
        self._trained_feature_cols = self.FEATURE_COLS  # Track which features model uses

        # =========================================================================
        # MODEL STALENESS TRACKING (Issue #1 fix)
        # Track when model was loaded/trained to detect stale models
        # =========================================================================
        self._model_loaded_at: Optional[datetime] = None  # When model was loaded into memory
        self._model_trained_at: Optional[datetime] = None  # When model was last trained
        self._last_version_check: Optional[datetime] = None  # Throttle version checks
        self._version_check_interval_seconds = 300  # Check for new model every 5 minutes

        # OMEGA mode - trust ML Advisor, use Prophet for adaptation only
        self.omega_mode = omega_mode

        # Ensemble integration (Gap 5 / Option B)
        self._ensemble_weighter = None
        self._dynamic_weight_updater = None

        # Live log for frontend transparency
        self.live_log = prophet_live_log

        # Adaptive thresholds (set relative to base rate after training)
        self.high_confidence_threshold = 0.65  # Default, recalculated after training
        self.low_confidence_threshold = 0.45   # Default, recalculated after training
        self._base_rate = None  # Learned from training data

        # Claude AI Enhancer
        self.claude: Optional[ProphetClaudeEnhancer] = None
        self._claude_enabled = enable_claude
        if enable_claude:
            self.claude = ProphetClaudeEnhancer()

        # Create models directory
        os.makedirs(self.MODEL_PATH, exist_ok=True)

        # Try to load existing model
        self._load_model()

        # Log initialization
        self.live_log.log("INIT", f"Prophet Advisor initialized (model v{self.model_version})", {
            "model_trained": self.is_trained,
            "claude_enabled": enable_claude,
            "has_gex_features": self._has_gex_features,
            "omega_mode": omega_mode
        })

    def _update_thresholds_from_base_rate(self):
        """Set adaptive thresholds relative to the training base rate.

        With 89% win rate, hardcoded 0.45/0.65 thresholds meant:
        - Model outputs ~0.89 on average
        - SKIP (<0.45) would essentially never fire
        - TRADE_FULL (>=0.65) fires on almost everything

        Adaptive thresholds key off the learned base rate:
        - SKIP when model predicts significantly BELOW base rate
        - TRADE_FULL when at or near base rate
        """
        if self._base_rate is not None and self._base_rate > 0.5:
            # SKIP when model predicts significantly below base rate
            self.low_confidence_threshold = self._base_rate - 0.15
            # TRADE_FULL when at or above base rate
            self.high_confidence_threshold = self._base_rate - 0.05
            logger.info(
                f"Adaptive thresholds: SKIP < {self.low_confidence_threshold:.2f}, "
                f"FULL >= {self.high_confidence_threshold:.2f} (base rate: {self._base_rate:.2f})"
            )

    # =========================================================================
    # ENSEMBLE INTEGRATION - REMOVED
    # Prophet is the god of all trade decisions. Ensemble is dead code.
    # GEX + VIX analysis is the fallback when Prophet is unavailable.
    # =========================================================================

    def get_ensemble_weighter(self, symbol: str = "SPY"):
        """REMOVED: Ensemble Strategy is dead code. Prophet is god."""
        return None

    def get_dynamic_weight_updater(self, symbol: str = "SPY"):
        """REMOVED: Ensemble Strategy is dead code. Prophet is god."""
        return None

    def get_ensemble_context(
        self,
        context: 'MarketContext',
        gex_data: Optional[Dict] = None,
        psychology_data: Optional[Dict] = None,
        rsi_data: Optional[Dict] = None,
        vol_surface_data: Optional[Dict] = None
    ) -> Optional[Dict]:
        """
        REMOVED: Ensemble Strategy is dead code. Prophet is god.
        Returns neutral context for any callers that haven't been updated yet.
        """
        return {
            'signal': 'NEUTRAL',
            'confidence': 50,
            'should_trade': True,
            'position_size_multiplier': 1.0,
            'bullish_weight': 0.33,
            'bearish_weight': 0.33,
            'neutral_weight': 0.34,
            'component_count': 0
        }

    def update_ensemble_from_outcome(
        self,
        strategy_name: str,
        was_correct: bool,
        confidence_at_prediction: float,
        actual_pnl_pct: float,
        current_regime: str
    ) -> Optional[Dict[str, float]]:
        """REMOVED: Ensemble Strategy is dead code. Prophet is god."""
        return None

    @property
    def claude_available(self) -> bool:
        """Check if Claude AI is available and enabled"""
        return self.claude is not None and self.claude.is_enabled

    # =========================================================================
    # PROVERBS ADVISORY - Feedback Loop Intelligence
    # Proverbs provides historical performance data as SUGGESTIONS to Prophet.
    # Prophet remains the final decision maker ("Prophet is god").
    # =========================================================================

    def get_proverbs_advisory(
        self,
        bot_name: str,
        current_hour: Optional[int] = None,
        market_regime: Optional[str] = None,
        is_friday: bool = False
    ) -> ProverbsAdvisory:
        """
        Get Proverbs's advisory data for Prophet decision-making.

        This data INFORMS Prophet's decisions but does NOT override them.
        Prophet uses this historical performance data to adjust its scores.

        Args:
            bot_name: The bot requesting advice (FORTRESS, SOLOMON, SAMSON, etc.)
            current_hour: Current trading hour (0-23, CT timezone)
            market_regime: Current market regime (BULLISH, BEARISH, NEUTRAL)
            is_friday: Whether it's Friday (for weekend pre-check)

        Returns:
            ProverbsAdvisory with all relevant performance data
        """
        advisory = ProverbsAdvisory()

        if not PROVERBS_AVAILABLE:
            advisory.data_quality = "NONE"
            advisory.proverbs_confidence = 0.0
            return advisory

        try:
            proverbs = get_proverbs_enhanced()
            if proverbs is None:
                advisory.data_quality = "NONE"
                return advisory

            # 1. TIME-OF-DAY ANALYSIS
            if current_hour is not None:
                try:
                    time_analysis = proverbs.time_analyzer.analyze(bot_name, days=30)
                    if time_analysis:
                        # Find current hour performance
                        for hour_data in time_analysis:
                            if hour_data.hour == current_hour:
                                advisory.hour_win_rate = hour_data.win_rate
                                advisory.hour_avg_pnl = hour_data.avg_pnl
                                advisory.is_optimal_hour = not hour_data.worst_performance
                                break

                        # Find best/worst hours
                        for hour_data in time_analysis:
                            if hour_data.best_performance:
                                advisory.best_hour = hour_data.hour
                            if hour_data.worst_performance:
                                advisory.worst_hour = hour_data.hour

                        # Calculate time adjustment
                        # Penalize trading during worst hours, slight boost for best hours
                        if advisory.worst_hour == current_hour:
                            advisory.time_of_day_adjustment = -0.15  # Significant penalty
                        elif advisory.best_hour == current_hour:
                            advisory.time_of_day_adjustment = 0.05  # Small boost
                        elif advisory.hour_win_rate < 40:
                            advisory.time_of_day_adjustment = -0.10  # Poor historical hour
                except Exception as e:
                    self.live_log.log("PROVERBS_TIME_ERR", f"Time analysis failed: {e}")

            # 2. REGIME PERFORMANCE ANALYSIS
            if market_regime:
                try:
                    regime_perf = proverbs.regime_tracker.analyze_regime_performance(bot_name, days=90)
                    if regime_perf:
                        for rp in regime_perf:
                            if rp.regime and rp.regime.upper() == market_regime.upper():
                                # Check if this is an IC or directional bot
                                is_ic_bot = bot_name.upper() in ['FORTRESS', 'SAMSON', 'ANCHOR', 'JUBILEE']
                                if is_ic_bot:
                                    advisory.regime_ic_win_rate = rp.win_rate
                                else:
                                    advisory.regime_dir_win_rate = rp.win_rate

                                # Adjust based on regime-specific performance
                                if rp.win_rate > 70:
                                    advisory.regime_adjustment = 0.10  # Strong performance in this regime
                                    advisory.regime_recommendation = "IC_PREFERRED" if is_ic_bot else "DIR_PREFERRED"
                                elif rp.win_rate < 40:
                                    advisory.regime_adjustment = -0.15  # Poor performance in this regime
                                    advisory.regime_recommendation = "DIR_PREFERRED" if is_ic_bot else "IC_PREFERRED"
                                break
                except Exception as e:
                    self.live_log.log("PROVERBS_REGIME_ERR", f"Regime analysis failed: {e}")

            # 3. CROSS-BOT CORRELATION (check for concentration risk)
            try:
                correlations = proverbs.cross_bot_analyzer.get_all_correlations(days=30)
                if correlations:
                    high_correlation_bots = []
                    for corr in correlations:
                        if corr.bot_a == bot_name or corr.bot_b == bot_name:
                            if abs(corr.correlation) > 0.7:  # High correlation threshold
                                other_bot = corr.bot_b if corr.bot_a == bot_name else corr.bot_a
                                high_correlation_bots.append(other_bot)

                    if high_correlation_bots:
                        advisory.correlated_bots_active = high_correlation_bots
                        advisory.correlation_risk = "HIGH" if len(high_correlation_bots) >= 2 else "MEDIUM"
                        advisory.size_reduction_pct = min(30, len(high_correlation_bots) * 15)  # 15% per correlated bot
            except Exception as e:
                self.live_log.log("PROVERBS_CORR_ERR", f"Correlation analysis failed: {e}")

            # 4. WEEKEND PRE-CHECK (Friday only)
            if is_friday:
                try:
                    weekend_check = proverbs.weekend_prechecker.analyze()
                    if weekend_check:
                        advisory.weekend_gap_prediction = weekend_check.get('prediction', 'NEUTRAL')
                        advisory.weekend_risk_level = weekend_check.get('risk_level', 'NORMAL')
                        # Reduce Friday position sizes based on weekend risk
                        if advisory.weekend_risk_level == 'HIGH':
                            advisory.friday_size_adjustment = 0.5
                        elif advisory.weekend_risk_level == 'EXTREME':
                            advisory.friday_size_adjustment = 0.25
                except Exception as e:
                    self.live_log.log("PROVERBS_WEEKEND_ERR", f"Weekend pre-check failed: {e}")

            # 5. CHECK FOR PENDING PROPOSALS
            try:
                proposals = proverbs.proposals
                if proposals:
                    for p in proposals:
                        if p.get('bot_name') == bot_name and p.get('status') == 'pending':
                            advisory.pending_proposal = True
                            advisory.proposal_summary = p.get('description', 'Pending proposal')[:100]
                            break
            except Exception as e:
                pass  # Non-critical

            # Set overall data quality
            advisory.data_quality = "GOOD"
            advisory.proverbs_confidence = 0.7

            # Log the advisory
            self.live_log.log("PROVERBS_ADVISORY", f"Advisory for {bot_name}", {
                "time_adjustment": advisory.time_of_day_adjustment,
                "regime_adjustment": advisory.regime_adjustment,
                "combined_adjustment": advisory.get_combined_adjustment(),
                "is_optimal_hour": advisory.is_optimal_hour,
                "correlation_risk": advisory.correlation_risk
            })

            return advisory

        except Exception as e:
            self.live_log.log("PROVERBS_ERR", f"Failed to get Proverbs advisory: {e}")
            advisory.data_quality = "NONE"
            advisory.proverbs_confidence = 0.0
            return advisory

    # =========================================================================
    # MODEL STALENESS DETECTION & AUTO-RELOAD (Issue #1 fix)
    # Ensures bots always use the most recent model version
    # =========================================================================

    def _get_hours_since_training(self) -> float:
        """Calculate hours since model was last trained"""
        if self._model_trained_at is None:
            return 0.0
        delta = datetime.now() - self._model_trained_at
        return delta.total_seconds() / 3600.0

    def _is_model_fresh(self, max_age_hours: float = 24.0) -> bool:
        """Check if model is considered fresh (< max_age_hours old)"""
        return self._get_hours_since_training() < max_age_hours

    def _get_db_model_version(self) -> Optional[str]:
        """Get the current active model version from database"""
        if not DB_AVAILABLE:
            return None

        with get_db_connection() as conn:
            if conn is None:
                return None
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT model_version
                    FROM prophet_trained_models
                    WHERE is_active = TRUE
                    ORDER BY created_at DESC
                    LIMIT 1
                """)
                row = cursor.fetchone()
                return row[0] if row else None
            except Exception as e:
                logger.debug(f"Failed to check DB model version: {e}")
                return None

    def _check_and_reload_model_if_stale(self) -> bool:
        """
        Check if a newer model exists in DB and reload if so.

        This fixes Issue #1: Model staleness after retraining.
        Called before every prediction to ensure fresh model is used.

        Returns:
            True if model was reloaded, False otherwise
        """
        # Throttle version checks to avoid DB spam (every 5 minutes)
        now = datetime.now()
        if self._last_version_check is not None:
            seconds_since_check = (now - self._last_version_check).total_seconds()
            if seconds_since_check < self._version_check_interval_seconds:
                return False

        self._last_version_check = now

        # Check DB for newer version
        db_version = self._get_db_model_version()
        if db_version is None:
            return False

        # If DB has different version, reload
        if db_version != self.model_version:
            logger.info(f"Prophet detected new model version in DB: {db_version} (current: {self.model_version})")
            old_version = self.model_version
            if self._load_model_from_db():
                self.live_log.log("MODEL_RELOAD", f"Auto-reloaded model: {old_version} → {self.model_version}", {
                    "old_version": old_version,
                    "new_version": self.model_version,
                    "hours_since_training": self._get_hours_since_training()
                })
                return True
            else:
                logger.warning(f"Failed to reload new model version {db_version}")

        return False

    def _add_staleness_to_prediction(self, prediction: ProphetPrediction) -> ProphetPrediction:
        """
        Add staleness tracking fields to a prediction.

        This fixes Issue #4: Bots can now see how fresh the model is
        and optionally adjust their confidence based on model age.
        """
        hours_since = self._get_hours_since_training()
        prediction.hours_since_training = hours_since
        prediction.model_loaded_at = self._model_loaded_at.isoformat() if self._model_loaded_at else None
        prediction.is_model_fresh = hours_since < 24.0
        return prediction

    # =========================================================================
    # MODEL PERSISTENCE
    # =========================================================================

    def _load_model(self) -> bool:
        """
        Load pre-trained model - tries DATABASE first (for Render persistence),
        then falls back to local file.
        """
        # Try database first (persists across Render deploys)
        if self._load_model_from_db():
            return True

        # Fall back to local file
        model_file = os.path.join(self.MODEL_PATH, 'prophet_model.pkl')

        # Try new name first, then fall back to old name
        if not os.path.exists(model_file):
            model_file = os.path.join(self.MODEL_PATH, 'fortress_advisor_model.pkl')

        if os.path.exists(model_file):
            try:
                with open(model_file, 'rb') as f:
                    saved = pickle.load(f)
                    self.model = saved.get('model')
                    self.calibrated_model = saved.get('calibrated_model')
                    self.scaler = saved.get('scaler')
                    self.training_metrics = saved.get('metrics')
                    self.model_version = saved.get('version', '1.0.0')
                    self._has_gex_features = saved.get('has_gex_features', False)
                    # V3 metadata
                    self._feature_version = saved.get('feature_version', 2)
                    self._trained_feature_cols = saved.get('feature_cols', self.FEATURE_COLS_V2)
                    self._base_rate = saved.get('base_rate')
                    self._update_thresholds_from_base_rate()
                    self.is_trained = True
                    logger.info(f"Loaded Prophet model v{self.model_version} (features V{self._feature_version}) from local file")
                    return True
            except Exception as e:
                logger.warning(f"Failed to load model from file: {e}")

        return False

    def _load_model_from_db(self) -> bool:
        """Load trained model from database (persists across Render deploys)"""
        if not DB_AVAILABLE:
            return False

        with get_db_connection() as conn:
            if conn is None:
                return False
            try:
                cursor = conn.cursor()

                # Check if table exists
                cursor.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables
                        WHERE table_name = 'prophet_trained_models'
                    )
                """)
                if not cursor.fetchone()[0]:
                    return False

                # Get the most recent active model (including created_at for staleness tracking)
                cursor.execute("""
                    SELECT model_version, model_data, training_metrics, has_gex_features, created_at
                    FROM prophet_trained_models
                    WHERE is_active = TRUE
                    ORDER BY created_at DESC
                    LIMIT 1
                """)
                row = cursor.fetchone()

                if row:
                    model_version, model_data, metrics_json, has_gex, created_at = row

                    # Deserialize model data
                    saved = pickle.loads(model_data)
                    self.model = saved.get('model')
                    self.calibrated_model = saved.get('calibrated_model')
                    self.scaler = saved.get('scaler')
                    self.model_version = model_version
                    self._has_gex_features = has_gex or False
                    # V3 metadata
                    self._feature_version = saved.get('feature_version', 2)
                    self._trained_feature_cols = saved.get('feature_cols', self.FEATURE_COLS_V2)
                    self._base_rate = saved.get('base_rate')
                    self._update_thresholds_from_base_rate()
                    self.is_trained = True

                    # Track when model was trained and loaded (Issue #1 fix)
                    self._model_loaded_at = datetime.now()
                    if created_at:
                        # Handle both timezone-aware and naive datetimes
                        if hasattr(created_at, 'tzinfo') and created_at.tzinfo is not None:
                            self._model_trained_at = created_at.replace(tzinfo=None)
                        else:
                            self._model_trained_at = created_at
                    else:
                        self._model_trained_at = self._model_loaded_at

                    # Restore training metrics
                    if metrics_json:
                        if isinstance(metrics_json, str):
                            metrics_dict = json.loads(metrics_json)
                        else:
                            metrics_dict = metrics_json
                        self.training_metrics = TrainingMetrics(**metrics_dict)

                    hours_since = self._get_hours_since_training()
                    logger.info(f"Loaded Prophet model v{self.model_version} from DATABASE "
                               f"(trained {hours_since:.1f}h ago)")
                    return True

            except Exception as e:
                logger.warning(f"Failed to load model from database: {e}")

        return False

    def _save_model(self):
        """Save trained model to BOTH database (for Render) and local file (backup)"""
        # Save to database first (critical for Render persistence)
        db_saved = self._save_model_to_db()

        # Also save to local file as backup
        model_file = os.path.join(self.MODEL_PATH, 'prophet_model.pkl')

        try:
            with open(model_file, 'wb') as f:
                pickle.dump({
                    'model': self.model,
                    'calibrated_model': self.calibrated_model,
                    'scaler': self.scaler,
                    'metrics': self.training_metrics,
                    'version': self.model_version,
                    'has_gex_features': self._has_gex_features,
                    'feature_version': self._feature_version,
                    'feature_cols': self._trained_feature_cols,
                    'base_rate': self._base_rate,
                    'saved_at': datetime.now().isoformat()
                }, f)
            logger.info(f"Saved Prophet model to {model_file}")
        except Exception as e:
            logger.error(f"Failed to save model to file: {e}")

        if db_saved:
            self.live_log.log("MODEL_SAVED", f"Model v{self.model_version} saved to database", {
                "version": self.model_version,
                "persistent": True
            })

    def _save_model_to_db(self) -> bool:
        """Save trained model to database for persistence across Render deploys"""
        if not DB_AVAILABLE:
            logger.warning("Database not available - model will not persist across restarts")
            return False

        with get_db_connection() as conn:
            if conn is None:
                return False
            try:
                cursor = conn.cursor()

                # Create table if not exists
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS prophet_trained_models (
                        id SERIAL PRIMARY KEY,
                        model_version VARCHAR(20) NOT NULL,
                        model_data BYTEA NOT NULL,
                        training_metrics JSONB,
                        has_gex_features BOOLEAN DEFAULT FALSE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        is_active BOOLEAN DEFAULT TRUE
                    )
                """)

                # Deactivate previous active models (only update those that are currently active)
                cursor.execute("UPDATE prophet_trained_models SET is_active = FALSE WHERE is_active = TRUE")

                # Serialize model data (includes V3 metadata)
                model_data = pickle.dumps({
                    'model': self.model,
                    'calibrated_model': self.calibrated_model,
                    'scaler': self.scaler,
                    'feature_version': self._feature_version,
                    'feature_cols': self._trained_feature_cols,
                    'base_rate': self._base_rate,
                })

                # Serialize training metrics
                metrics_json = json.dumps(self.training_metrics.__dict__) if self.training_metrics else None

                # Insert new model
                cursor.execute("""
                    INSERT INTO prophet_trained_models
                    (model_version, model_data, training_metrics, has_gex_features, is_active)
                    VALUES (%s, %s, %s, %s, TRUE)
                """, (
                    self.model_version,
                    model_data,
                    metrics_json,
                    self._has_gex_features
                ))

                conn.commit()

                logger.info(f"Saved Prophet model v{self.model_version} to DATABASE (persists across deploys)")
                return True

            except Exception as e:
                logger.error(f"Failed to save model to database: {e}")
                import traceback
                traceback.print_exc()
                return False

    # =========================================================================
    # STRATEGY SELECTION (IC vs DIRECTIONAL)
    # =========================================================================

    def _get_vix_regime(self, vix: float) -> VIXRegime:
        """Classify VIX into regime buckets"""
        if vix < 15:
            return VIXRegime.LOW
        elif vix < 22:
            return VIXRegime.NORMAL
        elif vix < 28:
            return VIXRegime.ELEVATED
        elif vix < 35:
            return VIXRegime.HIGH
        else:
            return VIXRegime.EXTREME

    def get_strategy_recommendation(
        self,
        context: MarketContext
    ) -> StrategyRecommendation:
        """
        Determine whether to trade Iron Condors or Directional Spreads.

        This is the CENTRAL method that bots can call before deciding
        whether to proceed with their specific strategy.

        Key Insight:
        - IC (FORTRESS/ANCHOR) profits when price stays PINNED
        - Directional (SOLOMON) profits when price MOVES

        Decision Logic:
        1. HIGH VIX + NEGATIVE GEX = TRENDING = Favor DIRECTIONAL
        2. NORMAL VIX + POSITIVE GEX = PINNING = Favor IC
        3. EXTREME VIX = Too risky, SKIP or reduced DIRECTIONAL
        4. LOW VIX = Cheap options, favor DIRECTIONAL if trending

        Returns:
            StrategyRecommendation with recommended strategy and reasoning
        """
        vix_regime = self._get_vix_regime(context.vix)
        gex_regime = context.gex_regime

        reasoning_parts = []
        ic_score = 0.5  # Start neutral
        dir_score = 0.5

        # =========================================================================
        # VIX REGIME SCORING
        # =========================================================================
        if vix_regime == VIXRegime.LOW:
            # Low VIX = cheap options, but low premium for IC
            ic_score -= 0.15
            dir_score += 0.10
            reasoning_parts.append(f"VIX {context.vix:.1f} (LOW): Cheap options favor directional, IC premium weak")

        elif vix_regime == VIXRegime.NORMAL:
            # Normal VIX = IDEAL for IC (goldilocks zone)
            ic_score += 0.20
            reasoning_parts.append(f"VIX {context.vix:.1f} (NORMAL): Ideal IC environment")

        elif vix_regime == VIXRegime.ELEVATED:
            # Elevated VIX = IC possible but caution needed
            ic_score -= 0.05
            dir_score += 0.15
            reasoning_parts.append(f"VIX {context.vix:.1f} (ELEVATED): Consider directional if trending")

        elif vix_regime == VIXRegime.HIGH:
            # High VIX = Markets volatile, favor directional
            ic_score -= 0.25
            dir_score += 0.25
            reasoning_parts.append(f"VIX {context.vix:.1f} (HIGH): Volatile market favors directional")

        elif vix_regime == VIXRegime.EXTREME:
            # Extreme VIX = Panic/crisis, very risky
            ic_score -= 0.40
            dir_score += 0.10  # Still risky for directional
            reasoning_parts.append(f"VIX {context.vix:.1f} (EXTREME): Crisis conditions, reduce exposure")

        # =========================================================================
        # GEX REGIME SCORING
        # =========================================================================
        if gex_regime == GEXRegime.POSITIVE:
            # Positive GEX = Mean reversion, pinning behavior
            ic_score += 0.25
            dir_score -= 0.10
            reasoning_parts.append("GEX POSITIVE: Mean reversion, pinning favors IC")

        elif gex_regime == GEXRegime.NEGATIVE:
            # Negative GEX = Trending, explosive moves
            ic_score -= 0.30
            dir_score += 0.30
            reasoning_parts.append("GEX NEGATIVE: Trending market favors directional")

        elif gex_regime == GEXRegime.NEUTRAL:
            # Neutral = Mixed signals
            reasoning_parts.append("GEX NEUTRAL: Mixed signals")

        # =========================================================================
        # ADDITIONAL FACTORS
        # =========================================================================

        # Day of week adjustment (Monday/Friday more volatile)
        if context.day_of_week in [0, 4]:  # Monday=0, Friday=4
            ic_score -= 0.05
            reasoning_parts.append("Mon/Fri: Higher volatility days")

        # Distance to flip point
        if context.gex_distance_to_flip_pct > 2:
            # Far above flip = more pinning
            ic_score += 0.05
        elif context.gex_distance_to_flip_pct < -2:
            # Far below flip = more trending
            dir_score += 0.05

        # =========================================================================
        # PROVERBS ADVISORY - Historical Performance Feedback (INFORMATION ONLY)
        # Proverbs provides informational context based on past performance.
        # This data is for DISPLAY ONLY - it does NOT affect Prophet's scores.
        # Prophet is the sole decision authority for all trading decisions.
        # =========================================================================
        proverbs_info = []  # Collect Proverbs insights for display

        if PROVERBS_AVAILABLE:
            try:
                # Get current hour (Central Time)
                from datetime import datetime
                import pytz
                ct_tz = pytz.timezone('America/Chicago')
                current_hour = datetime.now(ct_tz).hour
                is_friday = context.day_of_week == 4

                # Determine market regime string from GEX
                if gex_regime == GEXRegime.POSITIVE:
                    market_regime = "BULLISH"
                elif gex_regime == GEXRegime.NEGATIVE:
                    market_regime = "BEARISH"
                else:
                    market_regime = "NEUTRAL"

                # Get Proverbs's advisory (informational only)
                proverbs_advisory = self.get_proverbs_advisory(
                    bot_name="STRATEGY",  # Generic for strategy-level advice
                    current_hour=current_hour,
                    market_regime=market_regime,
                    is_friday=is_friday
                )

                if proverbs_advisory.data_quality != "NONE":
                    # Time-of-day info (DISPLAY ONLY - no score adjustment)
                    if proverbs_advisory.hour_win_rate > 0:
                        hour_quality = "strong" if proverbs_advisory.hour_win_rate >= 60 else "weak" if proverbs_advisory.hour_win_rate < 45 else "average"
                        proverbs_info.append(
                            f"Hour {current_hour}: {proverbs_advisory.hour_win_rate:.0f}% historical win rate ({hour_quality})"
                        )

                    # Regime performance info (DISPLAY ONLY - no score adjustment)
                    if proverbs_advisory.regime_recommendation != "NEUTRAL":
                        if proverbs_advisory.regime_recommendation == "IC_PREFERRED":
                            proverbs_info.append(
                                f"IC historically performs well in {market_regime} regime "
                                f"({proverbs_advisory.regime_ic_win_rate:.0f}% win rate)"
                            )
                        elif proverbs_advisory.regime_recommendation == "DIR_PREFERRED":
                            proverbs_info.append(
                                f"Directional historically performs well in {market_regime} regime "
                                f"({proverbs_advisory.regime_dir_win_rate:.0f}% win rate)"
                            )

                    # Correlation risk info (DISPLAY ONLY - no size adjustment)
                    if proverbs_advisory.correlation_risk in ["MEDIUM", "HIGH"]:
                        proverbs_info.append(
                            f"Correlation alert: {len(proverbs_advisory.correlated_bots_active)} correlated bots active "
                            f"({proverbs_advisory.correlation_risk} risk)"
                        )

                    # Weekend risk info (DISPLAY ONLY - no size adjustment)
                    if is_friday and proverbs_advisory.weekend_risk_level != "NORMAL":
                        proverbs_info.append(
                            f"Weekend gap prediction: {proverbs_advisory.weekend_gap_prediction} "
                            f"(risk level: {proverbs_advisory.weekend_risk_level})"
                        )

                    # Add all Proverbs info to reasoning as informational context
                    if proverbs_info:
                        reasoning_parts.append(f"PROVERBS INFO: {' | '.join(proverbs_info)}")

            except Exception as e:
                self.live_log.log("PROVERBS_STRATEGY_ERR", f"Proverbs advisory failed: {e}")

        # =========================================================================
        # DETERMINE RECOMMENDATION
        # =========================================================================

        # Normalize scores to 0-1
        ic_score = max(0.0, min(1.0, ic_score))
        dir_score = max(0.0, min(1.0, dir_score))

        # Calculate position size multiplier based on confidence
        confidence = max(ic_score, dir_score)
        if vix_regime == VIXRegime.EXTREME:
            size_multiplier = 0.25
        elif vix_regime == VIXRegime.HIGH:
            size_multiplier = 0.50
        elif vix_regime == VIXRegime.ELEVATED:
            size_multiplier = 0.75
        else:
            size_multiplier = 1.0

        # NOTE: Proverbs is information-only and does NOT affect sizing
        # Prophet is the sole authority for all trading decisions

        # Determine strategy
        if vix_regime == VIXRegime.EXTREME and gex_regime != GEXRegime.NEGATIVE:
            # Extreme VIX without clear trend = SKIP
            strategy = StrategyType.SKIP
            reasoning_parts.append("RESULT: SKIP - Extreme VIX without clear directional signal")

        elif ic_score > dir_score + 0.15:
            # Clear IC advantage
            strategy = StrategyType.IRON_CONDOR
            reasoning_parts.append(f"RESULT: IRON_CONDOR (IC={ic_score:.2f} > DIR={dir_score:.2f})")

        elif dir_score > ic_score + 0.10:
            # Clear directional advantage
            strategy = StrategyType.DIRECTIONAL
            reasoning_parts.append(f"RESULT: DIRECTIONAL (DIR={dir_score:.2f} > IC={ic_score:.2f})")

        else:
            # Close call - default to IC in normal conditions, directional in elevated
            if vix_regime in [VIXRegime.LOW, VIXRegime.NORMAL]:
                strategy = StrategyType.IRON_CONDOR
                reasoning_parts.append(f"RESULT: IRON_CONDOR (close call, normal VIX)")
            else:
                strategy = StrategyType.DIRECTIONAL
                reasoning_parts.append(f"RESULT: DIRECTIONAL (close call, elevated VIX)")

        # Log the recommendation
        self.live_log.log("STRATEGY_REC", f"Recommended: {strategy.value}", {
            "vix": context.vix,
            "vix_regime": vix_regime.value,
            "gex_regime": gex_regime.value,
            "ic_score": ic_score,
            "dir_score": dir_score,
            "strategy": strategy.value,
            "size_multiplier": size_multiplier
        })

        return StrategyRecommendation(
            recommended_strategy=strategy,
            vix_regime=vix_regime,
            gex_regime=gex_regime,
            confidence=confidence,
            reasoning=" | ".join(reasoning_parts),
            ic_suitability=ic_score,
            dir_suitability=dir_score,
            size_multiplier=size_multiplier,
            vix=context.vix,
            spot_price=context.spot_price
        )

    def analyze_strategy_performance(self, days: int = 30) -> Dict[str, Any]:
        """
        Analyze IC vs Directional performance by VIX/GEX regime.

        This helps Prophet LEARN which strategy works best in which conditions.
        Uses data from prophet_training_outcomes table.

        Returns:
            Dict with performance metrics by regime and strategy type
        """
        if not DB_AVAILABLE:
            return {"error": "Database not available"}

        conn = None
        try:
            conn = get_connection()
            cursor = conn.cursor()

            # Query outcomes with regime context
            cursor.execute("""
                SELECT
                    bot_name,
                    features->>'vix' as vix,
                    features->>'gex_regime' as gex_regime,
                    is_win,
                    net_pnl,
                    trade_date
                FROM prophet_training_outcomes
                WHERE trade_date >= CURRENT_DATE - INTERVAL '%s days'
                ORDER BY trade_date DESC
            """, (days,))

            rows = cursor.fetchall()

            if not rows:
                return {"error": "No outcome data available", "days": days}

            # Categorize by strategy and regime
            ic_bots = ['FORTRESS', 'ANCHOR']
            dir_bots = ['SOLOMON']

            results = {
                'ic_by_vix_regime': {
                    'LOW': {'wins': 0, 'total': 0, 'pnl': 0},
                    'NORMAL': {'wins': 0, 'total': 0, 'pnl': 0},
                    'ELEVATED': {'wins': 0, 'total': 0, 'pnl': 0},
                    'HIGH': {'wins': 0, 'total': 0, 'pnl': 0},
                    'EXTREME': {'wins': 0, 'total': 0, 'pnl': 0},
                },
                'dir_by_vix_regime': {
                    'LOW': {'wins': 0, 'total': 0, 'pnl': 0},
                    'NORMAL': {'wins': 0, 'total': 0, 'pnl': 0},
                    'ELEVATED': {'wins': 0, 'total': 0, 'pnl': 0},
                    'HIGH': {'wins': 0, 'total': 0, 'pnl': 0},
                    'EXTREME': {'wins': 0, 'total': 0, 'pnl': 0},
                },
                'ic_by_gex_regime': {
                    'POSITIVE': {'wins': 0, 'total': 0, 'pnl': 0},
                    'NEUTRAL': {'wins': 0, 'total': 0, 'pnl': 0},
                    'NEGATIVE': {'wins': 0, 'total': 0, 'pnl': 0},
                },
                'dir_by_gex_regime': {
                    'POSITIVE': {'wins': 0, 'total': 0, 'pnl': 0},
                    'NEUTRAL': {'wins': 0, 'total': 0, 'pnl': 0},
                    'NEGATIVE': {'wins': 0, 'total': 0, 'pnl': 0},
                },
                'total_ic': {'wins': 0, 'total': 0, 'pnl': 0},
                'total_dir': {'wins': 0, 'total': 0, 'pnl': 0},
            }

            for row in rows:
                bot_name, vix_str, gex_regime, is_win, net_pnl, trade_date = row
                vix = float(vix_str) if vix_str else 20.0
                gex_regime = gex_regime or 'NEUTRAL'
                net_pnl = net_pnl or 0

                # Determine VIX regime
                if vix < 15:
                    vix_regime = 'LOW'
                elif vix < 22:
                    vix_regime = 'NORMAL'
                elif vix < 28:
                    vix_regime = 'ELEVATED'
                elif vix < 35:
                    vix_regime = 'HIGH'
                else:
                    vix_regime = 'EXTREME'

                # Categorize
                is_ic = bot_name in ic_bots
                is_dir = bot_name in dir_bots

                if is_ic:
                    results['ic_by_vix_regime'][vix_regime]['total'] += 1
                    results['ic_by_vix_regime'][vix_regime]['pnl'] += net_pnl
                    results['ic_by_gex_regime'][gex_regime]['total'] += 1
                    results['ic_by_gex_regime'][gex_regime]['pnl'] += net_pnl
                    results['total_ic']['total'] += 1
                    results['total_ic']['pnl'] += net_pnl
                    if is_win:
                        results['ic_by_vix_regime'][vix_regime]['wins'] += 1
                        results['ic_by_gex_regime'][gex_regime]['wins'] += 1
                        results['total_ic']['wins'] += 1

                elif is_dir:
                    results['dir_by_vix_regime'][vix_regime]['total'] += 1
                    results['dir_by_vix_regime'][vix_regime]['pnl'] += net_pnl
                    results['dir_by_gex_regime'][gex_regime]['total'] += 1
                    results['dir_by_gex_regime'][gex_regime]['pnl'] += net_pnl
                    results['total_dir']['total'] += 1
                    results['total_dir']['pnl'] += net_pnl
                    if is_win:
                        results['dir_by_vix_regime'][vix_regime]['wins'] += 1
                        results['dir_by_gex_regime'][gex_regime]['wins'] += 1
                        results['total_dir']['wins'] += 1

            # Calculate win rates
            for regime_dict in [results['ic_by_vix_regime'], results['dir_by_vix_regime'],
                               results['ic_by_gex_regime'], results['dir_by_gex_regime']]:
                for regime, stats in regime_dict.items():
                    if stats['total'] > 0:
                        stats['win_rate'] = stats['wins'] / stats['total']
                    else:
                        stats['win_rate'] = 0

            for total_key in ['total_ic', 'total_dir']:
                if results[total_key]['total'] > 0:
                    results[total_key]['win_rate'] = results[total_key]['wins'] / results[total_key]['total']
                else:
                    results[total_key]['win_rate'] = 0

            results['days_analyzed'] = days
            results['total_trades'] = len(rows)

            # Log the analysis
            self.live_log.log("STRATEGY_ANALYSIS", "IC vs Directional performance analyzed", {
                "days": days,
                "total_trades": len(rows),
                "ic_win_rate": results['total_ic'].get('win_rate', 0),
                "dir_win_rate": results['total_dir'].get('win_rate', 0),
            })

            return results

        except Exception as e:
            logger.error(f"Failed to analyze strategy performance: {e}")
            return {"error": str(e)}
        finally:
            # V3 FIX: Ensure connection is always closed (was leaking on exception paths)
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

    # =========================================================================
    # BOT-SPECIFIC ADVICE
    # =========================================================================

    def get_fortress_advice(
        self,
        context: MarketContext,
        use_gex_walls: bool = False,
        use_claude_validation: bool = True,
        vix_hard_skip: float = 32.0,
        vix_monday_friday_skip: float = 0.0,
        vix_streak_skip: float = 0.0,
        recent_losses: int = 0
    ) -> ProphetPrediction:
        """
        Get Iron Condor advice for FORTRESS.

        Args:
            context: Current market conditions
            use_gex_walls: Whether to suggest strikes based on GEX walls
            use_claude_validation: Whether to use Claude AI to validate prediction
            vix_hard_skip: Skip if VIX > this threshold (0 = disabled)
            vix_monday_friday_skip: Skip on Mon/Fri if VIX > this (0 = disabled)
            vix_streak_skip: Skip after recent losses if VIX > this (0 = disabled)
            recent_losses: Number of recent consecutive losses

        Returns:
            ProphetPrediction with IC-specific advice
        """
        # Check for newer model version in DB and reload if available (Issue #1 fix)
        self._check_and_reload_model_if_stale()

        # Log prediction request
        self.live_log.log("PREDICT", "FORTRESS advice requested", {
            "vix": context.vix,
            "gex_regime": context.gex_regime.value,
            "spot_price": context.spot_price,
            "use_gex_walls": use_gex_walls,
            "use_claude": use_claude_validation,
            "vix_hard_skip": vix_hard_skip,
            "vix_monday_friday_skip": vix_monday_friday_skip,
            "vix_streak_skip": vix_streak_skip,
            "model_version": self.model_version,
            "hours_since_training": self._get_hours_since_training()
        })

        # =========================================================================
        # VIX-BASED SKIP LOGIC (Configurable per Strategy Preset)
        # Based on backtest: 2022-2024 showed Sharpe 8.55 → 16.84 with VIX filtering
        #
        # OMEGA MODE: When omega_mode=True, VIX skip rules are DISABLED.
        # In OMEGA mode, ML Advisor is the PRIMARY decision maker, and Prophet
        # only provides bot-specific adaptation (strikes, risk adjustment).
        # =========================================================================
        skip_reason = None
        skip_threshold_used = 0.0

        # OMEGA MODE CHECK: Skip VIX rules if Prophet is in OMEGA mode
        # In OMEGA mode, we trust ML Advisor for the trade/skip decision
        if not self.omega_mode:
            # Rule 1: Hard VIX skip (e.g., VIX > 32 for Moderate strategy)
            if vix_hard_skip > 0 and context.vix > vix_hard_skip:
                skip_reason = f"VIX {context.vix:.1f} > {vix_hard_skip} - volatility too high for Iron Condor"
                skip_threshold_used = vix_hard_skip

            # Rule 2: Monday/Friday VIX skip (e.g., VIX > 30 on Mon/Fri for Aggressive strategy)
            elif vix_monday_friday_skip > 0 and context.day_of_week in [0, 4]:  # Monday=0, Friday=4
                if context.vix > vix_monday_friday_skip:
                    day_name = "Monday" if context.day_of_week == 0 else "Friday"
                    skip_reason = f"VIX {context.vix:.1f} > {vix_monday_friday_skip} on {day_name} - higher risk day"
                    skip_threshold_used = vix_monday_friday_skip

            # Rule 3: Streak-based VIX skip (e.g., VIX > 28 after 2+ losses for Aggressive strategy)
            elif vix_streak_skip > 0 and recent_losses >= 2:
                if context.vix > vix_streak_skip:
                    skip_reason = f"VIX {context.vix:.1f} > {vix_streak_skip} with {recent_losses} recent losses - risk reduction"
                    skip_threshold_used = vix_streak_skip
        else:
            # Log that OMEGA mode is active
            self.live_log.log("OMEGA_MODE", "VIX skip rules DISABLED - deferring to ML Advisor", {
                "vix": context.vix,
                "vix_hard_skip_would_trigger": vix_hard_skip > 0 and context.vix > vix_hard_skip
            })

        # If any VIX skip rule triggered, return SKIP_TODAY
        # BUT: Check if conditions favor directional trading (SOLOMON)
        if skip_reason:
            # Get strategy recommendation to see if SOLOMON directional is better
            strategy_rec = self.get_strategy_recommendation(context)

            # Determine if we should suggest SOLOMON instead of just skipping
            suggest_solomon = False
            enhanced_reasoning = skip_reason

            if strategy_rec.recommended_strategy == StrategyType.DIRECTIONAL:
                suggest_solomon = True
                enhanced_reasoning = f"{skip_reason} | Consider SOLOMON directional: {strategy_rec.reasoning}"
            elif context.gex_regime == GEXRegime.NEGATIVE and context.vix < 40:
                # Trending market with elevated VIX = good for directional
                suggest_solomon = True
                enhanced_reasoning = f"{skip_reason} | GEX NEGATIVE (trending) favors SOLOMON directional"

            self.live_log.log("VIX_SKIP", skip_reason, {
                "vix": context.vix,
                "threshold": skip_threshold_used,
                "day_of_week": context.day_of_week,
                "recent_losses": recent_losses,
                "action": "SKIP_TODAY",
                "suggest_solomon": suggest_solomon,
                "strategy_rec": strategy_rec.recommended_strategy.value
            })
            skip_prediction = ProphetPrediction(
                bot_name=BotName.FORTRESS,
                advice=TradingAdvice.SKIP_TODAY,
                win_probability=0.35,
                confidence=0.95,  # High confidence in the skip decision
                suggested_risk_pct=0.0,
                suggested_sd_multiplier=1.0,
                reasoning=enhanced_reasoning,
                top_factors=[
                    ("vix_level", context.vix),
                    ("skip_threshold", skip_threshold_used),
                    ("day_of_week", context.day_of_week),
                    ("recent_losses", recent_losses),
                    ("suggest_solomon", 1.0 if suggest_solomon else 0.0)
                ],
                model_version=self.model_version,
                suggested_alternative=BotName.SOLOMON if suggest_solomon else None,
                strategy_recommendation=strategy_rec
            )
            return self._add_staleness_to_prediction(skip_prediction)

        # === FULL DATA FLOW LOGGING: INPUT ===
        input_data = {
            "spot_price": context.spot_price,
            "price_change_1d": context.price_change_1d,
            "vix": context.vix,
            "vix_percentile_30d": context.vix_percentile_30d,
            "vix_change_1d": context.vix_change_1d,
            "gex_net": context.gex_net,
            "gex_normalized": context.gex_normalized,
            "gex_regime": context.gex_regime.value,
            "gex_flip_point": context.gex_flip_point,
            "gex_call_wall": context.gex_call_wall,
            "gex_put_wall": context.gex_put_wall,
            "gex_distance_to_flip_pct": context.gex_distance_to_flip_pct,
            "gex_between_walls": context.gex_between_walls,
            "day_of_week": context.day_of_week,
            "days_to_opex": context.days_to_opex,
            "win_rate_30d": context.win_rate_30d,
            "expected_move_pct": context.expected_move_pct
        }
        self.live_log.log_data_flow("FORTRESS", "INPUT", input_data)

        # Get base prediction
        base_pred = self._get_base_prediction(context)

        # === FULL DATA FLOW LOGGING: ML_OUTPUT ===
        self.live_log.log_data_flow("FORTRESS", "ML_OUTPUT", {
            "win_probability": base_pred.get('win_probability'),
            "top_factors": base_pred.get('top_factors', []),
            "probabilities": base_pred.get('probabilities', {}),
            "model_version": self.model_version,
            "is_calibrated": self.calibrated_model is not None
        })

        # Calculate GEX wall strikes if requested
        suggested_put = None
        suggested_call = None

        if use_gex_walls and context.gex_call_wall > 0 and context.gex_put_wall > 0:
            # GEX-Protected IC: strikes OUTSIDE walls (support/resistance)
            # GEX walls from SPY need to be scaled for SPX trading
            # SPX is ~10x SPY price, so walls need proportional scaling

            gex_put_wall = context.gex_put_wall
            gex_call_wall = context.gex_call_wall

            # Check if trading SPX (price > 1000) but GEX walls are SPY-scale (< 1000)
            is_spx_trading = context.spot_price > 1000
            is_spy_gex_data = gex_put_wall < 1000 and gex_call_wall < 1000

            if is_spx_trading and is_spy_gex_data:
                # Scale SPY walls to SPX (multiply by ratio)
                avg_wall = (gex_put_wall + gex_call_wall) / 2
                if avg_wall > 0:
                    scale_factor = context.spot_price / avg_wall
                    # Validate scale_factor is reasonable (should be ~10x for SPY->SPX)
                    if scale_factor < 5 or scale_factor > 15:
                        logger.warning(f"GEX scale factor {scale_factor:.2f}x is unusual (expected 8-12x). "
                                      f"Spot: ${context.spot_price:.0f}, Avg Wall: ${avg_wall:.0f}")
                    gex_put_wall = gex_put_wall * scale_factor
                    gex_call_wall = gex_call_wall * scale_factor
                    logger.info(f"Scaled SPY GEX walls to SPX: Put ${gex_put_wall:.0f}, Call ${gex_call_wall:.0f} (scale: {scale_factor:.2f}x)")
                else:
                    logger.warning(f"Invalid GEX walls (avg={avg_wall:.2f}), skipping scale conversion")

            # Use proportional buffer based on expected move (0.5% of price as minimum)
            # This ensures buffer scales with the underlying
            buffer = max(context.spot_price * 0.005, context.spot_price * context.expected_move_pct / 100 * 0.25)

            suggested_put = gex_put_wall - buffer  # Below put wall (support)
            suggested_call = gex_call_wall + buffer  # Above call wall (resistance)

            logger.info(f"GEX-Protected strikes: Put ${suggested_put:.0f} (wall ${gex_put_wall:.0f} - ${buffer:.0f}), "
                       f"Call ${suggested_call:.0f} (wall ${gex_call_wall:.0f} + ${buffer:.0f})")

        # =====================================================================
        # GEX REGIME HANDLING - Now properly handles NEUTRAL for IC
        # NEUTRAL regime is actually FAVORABLE for Iron Condors:
        # - Walls are holding (mean reversion)
        # - Price is contained within range
        # - Less trending behavior = less breach risk
        # =====================================================================
        reasoning_parts = []
        ic_suitability = 0.50  # Start neutral
        position_in_range_pct = 50.0
        trend_direction_str = "SIDEWAYS"
        trend_strength = 0.0
        # NEUTRAL regime fields for consistency with SOLOMON
        neutral_derived_direction = ""
        neutral_confidence = 0.0
        neutral_reasoning = ""
        bullish_suitability = 0.0
        bearish_suitability = 0.0
        wall_filter_passed = False  # IC doesn't use wall filter, but track for consistency

        # Calculate position in wall range
        wall_range = context.gex_call_wall - context.gex_put_wall
        if wall_range > 0 and context.spot_price > 0:
            position_in_range_pct = (context.spot_price - context.gex_put_wall) / wall_range * 100

        # V2: GEX regime adjusts ic_suitability (strategy scoring) but NOT win_probability
        # The ML model already has gex_regime_positive, gex_between_walls as features.
        # Adding post-ML probability adjustments double-counts the signal and
        # destroys the isotonic calibration we apply during training.
        if context.gex_regime == GEXRegime.POSITIVE:
            reasoning_parts.append("Positive GEX favors mean reversion (good for IC)")
            ic_suitability += 0.20

        elif context.gex_regime == GEXRegime.NEGATIVE:
            reasoning_parts.append("Negative GEX indicates trending market (slightly risky for IC)")
            ic_suitability -= 0.15

        elif context.gex_regime == GEXRegime.NEUTRAL:
            # =====================================================================
            # NEUTRAL REGIME - GOOD FOR IC! Walls are holding, price contained
            # This is the key fix - NEUTRAL should NOT penalize IC strategies
            # =====================================================================
            reasoning_parts.append("NEUTRAL GEX: Balanced market, walls likely to hold (good for IC)")

            # NEUTRAL with contained price = ideal IC environment
            if context.gex_between_walls:
                ic_suitability += 0.15
                reasoning_parts.append("Price contained within walls (IC sweet spot)")

            # Use trend tracker if available for additional confidence
            if TREND_TRACKER_AVAILABLE and get_trend_tracker is not None:
                try:
                    tracker = get_trend_tracker()
                    tracker.update("SPY", context.spot_price)

                    trend_analysis = tracker.analyze_trend("SPY")
                    if trend_analysis:
                        trend_direction_str = trend_analysis.direction.value
                        trend_strength = trend_analysis.strength

                        # Sideways trend is IDEAL for IC
                        if trend_analysis.direction.value == "SIDEWAYS":
                            ic_suitability += 0.10
                            reasoning_parts.append("Sideways trend (range-bound = IC paradise)")
                        elif trend_strength > 0.6:
                            # Strong trend in either direction is risky for IC
                            ic_suitability -= 0.10
                            reasoning_parts.append(f"Strong {trend_direction_str} trend ({trend_strength:.0%}) - caution")

                    # Calculate full IC suitability
                    wall_position = tracker.analyze_wall_position(
                        "SPY", context.spot_price,
                        context.gex_call_wall, context.gex_put_wall,
                        trend_analysis
                    )
                    suitability = tracker.calculate_strategy_suitability(
                        trend_analysis, wall_position, context.vix,
                        context.gex_regime.value
                    )
                    ic_suitability = suitability.ic_suitability
                    bullish_suitability = suitability.bullish_suitability
                    bearish_suitability = suitability.bearish_suitability
                    position_in_range_pct = wall_position.position_in_range_pct

                    # For IC, derive direction based on position in range (for transparency)
                    if position_in_range_pct < 35:
                        neutral_derived_direction = "BULLISH"  # Near put wall
                        neutral_confidence = 0.6
                    elif position_in_range_pct > 65:
                        neutral_derived_direction = "BEARISH"  # Near call wall
                        neutral_confidence = 0.6
                    else:
                        neutral_derived_direction = "NEUTRAL"  # Centered = ideal for IC
                        neutral_confidence = 0.7
                    neutral_reasoning = f"IC: Position {position_in_range_pct:.0f}% in wall range, trend {trend_direction_str}"

                    logger.info(f"[FORTRESS NEUTRAL] IC suitability: {ic_suitability:.0%}, trend: {trend_direction_str}")

                except Exception as e:
                    logger.warning(f"[FORTRESS] Trend tracker error: {e}")
                    # Still boost IC for NEUTRAL regime even without tracker
                    ic_suitability += 0.10

        if context.gex_between_walls:
            reasoning_parts.append("Price between GEX walls (stable zone)")
            ic_suitability += 0.10
        else:
            reasoning_parts.append("Price outside GEX walls (minor breakout risk)")
            ic_suitability -= 0.10

        # Normalize IC suitability
        ic_suitability = max(0.0, min(1.0, ic_suitability))

        # =========================================================================
        # CLAUDE AI VALIDATION (if enabled)
        # =========================================================================
        claude_analysis = None
        if use_claude_validation and self.claude_available:
            claude_analysis = self.claude.validate_prediction(context, base_pred, BotName.FORTRESS)

            # Apply Claude's confidence adjustment
            if claude_analysis.recommendation in ["ADJUST", "OVERRIDE"]:
                base_pred['win_probability'] = max(0.40, min(0.85,
                    base_pred['win_probability'] + claude_analysis.confidence_adjustment
                ))
                reasoning_parts.append(f"Claude: {claude_analysis.analysis}")

                # Log risk factors
                if claude_analysis.risk_factors:
                    logger.info(f"Claude risk factors: {claude_analysis.risk_factors}")

            # VALIDATE hallucination_risk and reduce confidence if HIGH
            # REDUCED penalties: original values were too aggressive and blocked trades
            hallucination_risk = getattr(claude_analysis, 'hallucination_risk', 'LOW')
            if hallucination_risk == 'HIGH':
                penalty = 0.05  # REDUCED from 10% to 5%
                base_pred['win_probability'] = max(0.50, base_pred['win_probability'] - penalty)
                reasoning_parts.append(f"Claude hallucination risk HIGH (confidence reduced by {penalty:.0%})")
                logger.warning(f"[FORTRESS] Claude hallucination risk HIGH - reducing confidence by {penalty:.0%}")
                if hasattr(claude_analysis, 'hallucination_warnings') and claude_analysis.hallucination_warnings:
                    for warning in claude_analysis.hallucination_warnings:
                        logger.warning(f"  - {warning}")
            elif hallucination_risk == 'MEDIUM':
                penalty = 0.02  # REDUCED from 5% to 2%
                base_pred['win_probability'] = max(0.50, base_pred['win_probability'] - penalty)
                reasoning_parts.append(f"Claude hallucination risk MEDIUM (confidence reduced by {penalty:.0%})")
                logger.info(f"[FORTRESS] Claude hallucination risk MEDIUM - reducing confidence by {penalty:.0%}")

        # Determine final advice
        advice, risk_pct = self._get_advice_from_probability(base_pred['win_probability'])

        # SD multiplier - ALWAYS keep strikes OUTSIDE expected move
        # FIX (Jan 2025): Changed minimum from 1.0 to 1.2
        # 1.0 SD = strikes at EXACTLY expected move boundary = breached 32% of time
        # 1.2 SD = strikes 20% OUTSIDE expected move = better cushion
        # Higher SD = wider strikes = lower credit but higher win rate
        if base_pred['win_probability'] >= 0.70:
            sd_mult = 1.2  # FIX: Was 1.0 - baseline now 20% outside expected move
        elif base_pred['win_probability'] >= 0.60:
            sd_mult = 1.3  # FIX: Was 1.1 - medium confidence gets wider strikes
        else:
            sd_mult = 1.4  # FIX: Was 1.2 - low confidence = much wider for safety

        prediction = ProphetPrediction(
            bot_name=BotName.FORTRESS,
            advice=advice,
            win_probability=base_pred['win_probability'],
            confidence=base_pred['win_probability'],  # V2: removed 1.2x inflation that destroyed calibration
            suggested_risk_pct=risk_pct,
            suggested_sd_multiplier=sd_mult,
            use_gex_walls=use_gex_walls,
            suggested_put_strike=suggested_put,
            suggested_call_strike=suggested_call,
            top_factors=base_pred['top_factors'],
            reasoning=" | ".join(reasoning_parts),
            model_version=self.model_version,
            probabilities=base_pred['probabilities'],
            claude_analysis=claude_analysis,
            # NEUTRAL regime fields (all 10 for consistency)
            neutral_derived_direction=neutral_derived_direction,
            neutral_confidence=neutral_confidence,
            neutral_reasoning=neutral_reasoning,
            ic_suitability=ic_suitability,
            bullish_suitability=bullish_suitability,
            bearish_suitability=bearish_suitability,
            trend_direction=trend_direction_str,
            trend_strength=trend_strength,
            position_in_range_pct=position_in_range_pct,
            wall_filter_passed=wall_filter_passed
        )

        # Log prediction result
        self.live_log.log("PREDICT_DONE", f"FORTRESS: {advice.value} ({base_pred['win_probability']:.1%})", {
            "advice": advice.value,
            "win_probability": base_pred['win_probability'],
            "risk_pct": risk_pct,
            "claude_validated": claude_analysis is not None
        })

        # === FULL DATA FLOW LOGGING: DECISION ===
        decision_data = {
            "advice": advice.value,
            "win_probability": base_pred['win_probability'],
            "confidence": prediction.confidence,
            "risk_pct": risk_pct,
            "sd_multiplier": sd_mult,
            "use_gex_walls": use_gex_walls,
            "suggested_put_strike": suggested_put,
            "suggested_call_strike": suggested_call,
            "reasoning": prediction.reasoning,
            "claude_validated": claude_analysis is not None,
            "claude_recommendation": claude_analysis.recommendation if claude_analysis else None,
            "claude_confidence_adj": claude_analysis.confidence_adjustment if claude_analysis else None,
            "claude_risk_factors": claude_analysis.risk_factors if claude_analysis else [],
            "model_version": self.model_version,
            "hours_since_training": self._get_hours_since_training()
        }
        self.live_log.log_data_flow("FORTRESS", "DECISION", decision_data)

        return self._add_staleness_to_prediction(prediction)

    def get_cornerstone_advice(self, context: MarketContext) -> ProphetPrediction:
        """
        Get Wheel strategy advice for CORNERSTONE.

        CORNERSTONE trades cash-secured puts and covered calls.
        GEX signals help with entry timing.
        """
        # Log prediction request
        self.live_log.log("PREDICT", "CORNERSTONE advice requested", {
            "vix": context.vix,
            "gex_regime": context.gex_regime.value,
            "spot_price": context.spot_price
        })

        # === FULL DATA FLOW LOGGING: INPUT ===
        input_data = {
            "spot_price": context.spot_price,
            "price_change_1d": context.price_change_1d,
            "vix": context.vix,
            "vix_percentile_30d": context.vix_percentile_30d,
            "vix_change_1d": context.vix_change_1d,
            "gex_net": context.gex_net,
            "gex_normalized": context.gex_normalized,
            "gex_regime": context.gex_regime.value,
            "gex_flip_point": context.gex_flip_point,
            "gex_call_wall": context.gex_call_wall,
            "gex_put_wall": context.gex_put_wall,
            "gex_between_walls": context.gex_between_walls,
            "day_of_week": context.day_of_week,
            "days_to_opex": context.days_to_opex
        }
        self.live_log.log_data_flow("CORNERSTONE", "INPUT", input_data)

        base_pred = self._get_base_prediction(context)

        # === FULL DATA FLOW LOGGING: ML_OUTPUT ===
        self.live_log.log_data_flow("CORNERSTONE", "ML_OUTPUT", {
            "win_probability": base_pred.get('win_probability'),
            "top_factors": base_pred.get('top_factors', []),
            "probabilities": base_pred.get('probabilities', {}),
            "model_version": self.model_version
        })

        reasoning_parts = []

        # V2: VIX and GEX inform reasoning but do NOT manipulate calibrated probability.
        # The ML model already has VIX and GEX as input features.
        if context.vix > 25:
            reasoning_parts.append("High VIX = rich premiums for CSP")
        elif context.vix < 15:
            reasoning_parts.append("Low VIX = thin premiums, consider waiting")

        # Positive GEX = less likely to get assigned
        if context.gex_regime == GEXRegime.POSITIVE:
            reasoning_parts.append("Positive GEX supports put selling")

        advice, risk_pct = self._get_advice_from_probability(base_pred['win_probability'])

        prediction = ProphetPrediction(
            bot_name=BotName.CORNERSTONE,
            advice=advice,
            win_probability=base_pred['win_probability'],
            confidence=base_pred['win_probability'],  # V2: removed 1.2x inflation that destroyed calibration
            suggested_risk_pct=risk_pct,
            suggested_sd_multiplier=1.0,
            top_factors=base_pred['top_factors'],
            reasoning=" | ".join(reasoning_parts),
            model_version=self.model_version,
            probabilities=base_pred['probabilities']
        )

        # Log prediction result
        self.live_log.log("PREDICT_DONE", f"CORNERSTONE: {advice.value} ({base_pred['win_probability']:.1%})", {
            "advice": advice.value,
            "win_probability": base_pred['win_probability'],
            "risk_pct": risk_pct
        })

        # === FULL DATA FLOW LOGGING: DECISION ===
        decision_data = {
            "advice": advice.value,
            "win_probability": base_pred['win_probability'],
            "confidence": prediction.confidence,
            "risk_pct": risk_pct,
            "reasoning": prediction.reasoning,
            "model_version": self.model_version
        }
        self.live_log.log_data_flow("CORNERSTONE", "DECISION", decision_data)

        return self._add_staleness_to_prediction(prediction)

    def get_lazarus_advice(
        self,
        context: MarketContext,
        use_claude_validation: bool = True
    ) -> ProphetPrediction:
        """
        Get directional call advice for LAZARUS.

        LAZARUS trades long calls, needs directional bias.
        """
        # Check for newer model version in DB and reload if available (Issue #1 fix)
        self._check_and_reload_model_if_stale()

        # Log prediction request
        self.live_log.log("PREDICT", "LAZARUS advice requested", {
            "vix": context.vix,
            "gex_regime": context.gex_regime.value,
            "spot_price": context.spot_price,
            "claude_validation": use_claude_validation,
            "model_version": self.model_version,
            "hours_since_training": self._get_hours_since_training()
        })

        # === FULL DATA FLOW LOGGING: INPUT ===
        input_data = {
            "spot_price": context.spot_price,
            "price_change_1d": context.price_change_1d,
            "vix": context.vix,
            "vix_percentile_30d": context.vix_percentile_30d,
            "vix_change_1d": context.vix_change_1d,
            "gex_net": context.gex_net,
            "gex_normalized": context.gex_normalized,
            "gex_regime": context.gex_regime.value,
            "gex_flip_point": context.gex_flip_point,
            "gex_call_wall": context.gex_call_wall,
            "gex_put_wall": context.gex_put_wall,
            "gex_distance_to_flip_pct": context.gex_distance_to_flip_pct,
            "gex_between_walls": context.gex_between_walls,
            "day_of_week": context.day_of_week,
            "days_to_opex": context.days_to_opex
        }
        self.live_log.log_data_flow("LAZARUS", "INPUT", input_data)

        base_pred = self._get_base_prediction(context)

        # === FULL DATA FLOW LOGGING: ML_OUTPUT ===
        self.live_log.log_data_flow("LAZARUS", "ML_OUTPUT", {
            "win_probability": base_pred.get('win_probability'),
            "top_factors": base_pred.get('top_factors', []),
            "probabilities": base_pred.get('probabilities', {}),
            "model_version": self.model_version
        })

        reasoning_parts = []

        # V2: GEX regime informs reasoning but does NOT manipulate calibrated probability.
        # The ML model already has gex_regime_positive, gex_distance_to_flip_pct as features.
        if context.gex_regime == GEXRegime.NEGATIVE and context.gex_distance_to_flip_pct < 0:
            reasoning_parts.append("Negative GEX below flip = gamma squeeze potential")
        elif context.gex_regime == GEXRegime.POSITIVE:
            reasoning_parts.append("Positive GEX = mean reversion, less directional opportunity")

        # =========================================================================
        # CLAUDE AI VALIDATION (if enabled)
        # =========================================================================
        claude_analysis = None
        if use_claude_validation and self.claude_available:
            claude_analysis = self.claude.validate_prediction(context, base_pred, BotName.LAZARUS)

            # Apply Claude's confidence adjustment
            if claude_analysis.recommendation in ["ADJUST", "OVERRIDE"]:
                base_pred['win_probability'] = max(0.45, min(0.80,
                    base_pred['win_probability'] + claude_analysis.confidence_adjustment
                ))
                reasoning_parts.append(f"Claude: {claude_analysis.analysis}")

            # VALIDATE hallucination_risk - REDUCED penalties
            hallucination_risk = getattr(claude_analysis, 'hallucination_risk', 'LOW')
            if hallucination_risk == 'HIGH':
                penalty = 0.05  # REDUCED from 10%
                base_pred['win_probability'] = max(0.45, base_pred['win_probability'] - penalty)
                reasoning_parts.append(f"Claude hallucination risk HIGH (confidence reduced by {penalty:.0%})")
                logger.warning(f"[LAZARUS] Claude hallucination risk HIGH - reducing confidence by {penalty:.0%}")
            elif hallucination_risk == 'MEDIUM':
                penalty = 0.02  # REDUCED from 5%
                base_pred['win_probability'] = max(0.45, base_pred['win_probability'] - penalty)
                reasoning_parts.append(f"Claude hallucination risk MEDIUM (confidence reduced by {penalty:.0%})")
                logger.info(f"[LAZARUS] Claude hallucination risk MEDIUM - reducing confidence by {penalty:.0%}")

        advice, risk_pct = self._get_advice_from_probability(base_pred['win_probability'])

        prediction = ProphetPrediction(
            bot_name=BotName.LAZARUS,
            advice=advice,
            win_probability=base_pred['win_probability'],
            confidence=base_pred['win_probability'],  # V2: removed 1.2x inflation that destroyed calibration
            suggested_risk_pct=risk_pct * 0.5,  # Lower risk for directional
            suggested_sd_multiplier=1.0,
            top_factors=base_pred['top_factors'],
            reasoning=" | ".join(reasoning_parts),
            model_version=self.model_version,
            probabilities=base_pred['probabilities'],
            claude_analysis=claude_analysis  # Include real Claude data for logging
        )

        # Log prediction result
        self.live_log.log("PREDICT_DONE", f"LAZARUS: {advice.value} ({base_pred['win_probability']:.1%})", {
            "advice": advice.value,
            "win_probability": base_pred['win_probability'],
            "risk_pct": risk_pct,
            "claude_validated": claude_analysis is not None
        })

        # === FULL DATA FLOW LOGGING: DECISION ===
        decision_data = {
            "advice": advice.value,
            "win_probability": base_pred['win_probability'],
            "confidence": prediction.confidence,
            "risk_pct": risk_pct * 0.5,
            "reasoning": prediction.reasoning,
            "claude_validated": claude_analysis is not None,
            "claude_recommendation": claude_analysis.recommendation if claude_analysis else None,
            "claude_confidence_adj": claude_analysis.confidence_adjustment if claude_analysis else None,
            "model_version": self.model_version,
            "hours_since_training": self._get_hours_since_training()
        }
        self.live_log.log_data_flow("LAZARUS", "DECISION", decision_data)

        return self._add_staleness_to_prediction(prediction)

    def get_solomon_advice(
        self,
        context: MarketContext,
        use_gex_walls: bool = True,
        use_claude_validation: bool = True,
        wall_filter_pct: float = 1.0,  # Default 1.0%, backtest showed 0.5% = 98% WR
        bot_name: str = "SOLOMON"  # Allow GIDEON to pass its own name for proper logging
    ) -> ProphetPrediction:
        """
        Get directional spread advice for SOLOMON (or GIDEON).

        SOLOMON trades Bull Call Spreads (bullish) and Bear Call Spreads (bearish).
        Uses GEX walls for entry timing and direction confirmation.

        Strategy:
        - BULLISH: Buy ATM call, Sell OTM call (Bull Call Spread)
        - BEARISH: Sell ATM call, Buy OTM call (Bear Call Spread)

        GEX Wall Logic:
        - Near Put Wall (support) + BULLISH signal = Strong entry for Bull Call Spread
        - Near Call Wall (resistance) + BEARISH signal = Strong entry for Bear Call Spread

        Args:
            bot_name: Bot identifier for logging (SOLOMON or GIDEON)
        """
        # Log prediction request
        # Check for newer model version in DB and reload if available (Issue #1 fix)
        self._check_and_reload_model_if_stale()

        self.live_log.log("PREDICT", f"{bot_name} advice requested", {
            "vix": context.vix,
            "gex_regime": context.gex_regime.value,
            "spot_price": context.spot_price,
            "use_gex_walls": use_gex_walls,
            "claude_validation": use_claude_validation,
            "model_version": self.model_version,
            "hours_since_training": self._get_hours_since_training()
        })

        # === FULL DATA FLOW LOGGING: INPUT ===
        input_data = {
            "spot_price": context.spot_price,
            "price_change_1d": context.price_change_1d,
            "vix": context.vix,
            "vix_percentile_30d": context.vix_percentile_30d,
            "vix_change_1d": context.vix_change_1d,
            "gex_net": context.gex_net,
            "gex_normalized": context.gex_normalized,
            "gex_regime": context.gex_regime.value,
            "gex_flip_point": context.gex_flip_point,
            "gex_call_wall": context.gex_call_wall,
            "gex_put_wall": context.gex_put_wall,
            "gex_distance_to_flip_pct": context.gex_distance_to_flip_pct,
            "gex_between_walls": context.gex_between_walls,
            "day_of_week": context.day_of_week,
            "days_to_opex": context.days_to_opex
        }
        self.live_log.log_data_flow(bot_name, "INPUT", input_data)

        base_pred = self._get_base_prediction(context)

        # === FULL DATA FLOW LOGGING: ML_OUTPUT ===
        self.live_log.log_data_flow(bot_name, "ML_OUTPUT", {
            "win_probability": base_pred.get('win_probability'),
            "top_factors": base_pred.get('top_factors', []),
            "probabilities": base_pred.get('probabilities', {}),
            "model_version": self.model_version
        })

        reasoning_parts = []

        # Calculate distance to walls
        dist_to_call_wall = 0
        dist_to_put_wall = 0
        position_in_range_pct = 50.0

        if context.gex_call_wall > 0 and context.spot_price > 0:
            dist_to_call_wall = (context.gex_call_wall - context.spot_price) / context.spot_price * 100
        if context.gex_put_wall > 0 and context.spot_price > 0:
            dist_to_put_wall = (context.spot_price - context.gex_put_wall) / context.spot_price * 100

        # Calculate position in range
        wall_range = context.gex_call_wall - context.gex_put_wall
        if wall_range > 0:
            position_in_range_pct = (context.spot_price - context.gex_put_wall) / wall_range * 100

        # =====================================================================
        # ML DIRECTION IS THE PRIMARY SOURCE FOR SOLOMON/GIDEON
        # Prophet uses GEX probability models (STARS) to determine direction
        # This ensures Prophet direction matches what ML says
        # =====================================================================
        direction = "FLAT"
        direction_confidence = 0.50
        wall_filter_passed = False
        neutral_derived_direction = ""
        neutral_confidence = 0.0
        neutral_reasoning = ""
        trend_direction_str = "SIDEWAYS"
        trend_strength = 0.0
        ic_suitability = 0.50
        bullish_suitability = 0.50
        bearish_suitability = 0.50

        # Try to get ML direction from GEX probability models (STARS)
        ml_direction_used = False
        if GEX_ML_AVAILABLE and GEXSignalIntegration is not None:
            try:
                # V3 FIX: Thread-safe singleton initialization (multiple bots call concurrently)
                global _gex_signal_integration
                if _gex_signal_integration is None:
                    with _gex_signal_lock:
                        if _gex_signal_integration is None:  # Double-check after acquiring lock
                            _gex_signal_integration = GEXSignalIntegration()

                ml_signal = _gex_signal_integration.get_combined_signal(
                    ticker="SPY",
                    spot_price=context.spot_price,
                    call_wall=context.gex_call_wall,
                    put_wall=context.gex_put_wall,
                    vix=context.vix,
                )

                if ml_signal and ml_signal.get('direction') in ('BULLISH', 'BEARISH'):
                    direction = ml_signal['direction']
                    direction_confidence = ml_signal.get('confidence', 0.60)
                    ml_direction_used = True
                    wall_filter_passed = True  # ML bypasses wall filter
                    neutral_derived_direction = direction
                    neutral_confidence = direction_confidence
                    reasoning_parts.append(f"ML DIRECTION: {direction} (confidence: {direction_confidence:.0%})")
                    logger.info(f"[{bot_name}] PROPHET USING ML DIRECTION: {direction} @ {direction_confidence:.0%}")

                    # Set suitability based on ML direction
                    if direction == "BULLISH":
                        bullish_suitability = direction_confidence
                        bearish_suitability = 1.0 - direction_confidence
                    else:
                        bearish_suitability = direction_confidence
                        bullish_suitability = 1.0 - direction_confidence
                    ic_suitability = 0.30  # Directional trade preferred
            except Exception as e:
                logger.warning(f"[{bot_name}] ML direction error: {e}, using GEX fallback")

        # GEX-based directional logic ONLY if ML direction not available
        if not ml_direction_used and context.gex_regime == GEXRegime.NEGATIVE:
            # Negative GEX = trending market, directional opportunity
            if context.gex_distance_to_flip_pct < -1:
                direction = "BEARISH"
                direction_confidence = 0.60
                reasoning_parts.append("Negative GEX below flip = bearish momentum")
            elif context.gex_distance_to_flip_pct > 1:
                direction = "BULLISH"
                direction_confidence = 0.55
                reasoning_parts.append("Price above flip in negative GEX = squeeze potential")

        elif not ml_direction_used and context.gex_regime == GEXRegime.POSITIVE:
            # Positive GEX = mean reversion, use wall proximity
            if dist_to_put_wall < wall_filter_pct and dist_to_put_wall > 0:
                direction = "BULLISH"
                direction_confidence = 0.65
                reasoning_parts.append(f"POSITIVE GEX near put wall support ({dist_to_put_wall:.1f}%)")
            elif dist_to_call_wall < wall_filter_pct and dist_to_call_wall > 0:
                direction = "BEARISH"
                direction_confidence = 0.65
                reasoning_parts.append(f"POSITIVE GEX near call wall resistance ({dist_to_call_wall:.1f}%)")

        elif not ml_direction_used and context.gex_regime == GEXRegime.NEUTRAL:
            # =====================================================================
            # NEUTRAL REGIME - The key fix! Use trend + wall proximity
            # =====================================================================
            reasoning_parts.append("NEUTRAL GEX: Using trend + wall proximity for direction")

            # Try to use the trend tracker for dynamic direction
            if TREND_TRACKER_AVAILABLE and get_trend_tracker is not None:
                try:
                    tracker = get_trend_tracker()
                    # Update tracker with current price
                    tracker.update("SPY", context.spot_price)

                    # Get direction from trend tracker
                    direction, direction_confidence, neutral_reasoning, wall_filter_passed = \
                        tracker.get_neutral_regime_direction(
                            symbol="SPY",
                            spot_price=context.spot_price,
                            call_wall=context.gex_call_wall,
                            put_wall=context.gex_put_wall,
                            wall_filter_pct=wall_filter_pct
                        )

                    neutral_derived_direction = direction
                    neutral_confidence = direction_confidence
                    reasoning_parts.append(f"Trend tracker: {neutral_reasoning}")

                    # Get trend analysis for additional context
                    trend_analysis = tracker.analyze_trend("SPY")
                    if trend_analysis:
                        trend_direction_str = trend_analysis.direction.value
                        trend_strength = trend_analysis.strength

                    # Get strategy suitability
                    wall_position = tracker.analyze_wall_position(
                        "SPY", context.spot_price,
                        context.gex_call_wall, context.gex_put_wall,
                        trend_analysis
                    )
                    suitability = tracker.calculate_strategy_suitability(
                        trend_analysis, wall_position, context.vix,
                        context.gex_regime.value
                    )
                    ic_suitability = suitability.ic_suitability
                    bullish_suitability = suitability.bullish_suitability
                    bearish_suitability = suitability.bearish_suitability

                    logger.info(f"[SOLOMON NEUTRAL] Trend tracker: {direction} ({direction_confidence:.0%})")

                except Exception as e:
                    logger.warning(f"[SOLOMON] Trend tracker error: {e}, using fallback")
                    # Fallback to wall-proximity based direction
                    direction, direction_confidence, neutral_reasoning = \
                        self._get_neutral_direction_fallback(
                            context.spot_price, context.gex_call_wall, context.gex_put_wall,
                            position_in_range_pct, wall_filter_pct
                        )
                    neutral_derived_direction = direction
                    neutral_confidence = direction_confidence
                    reasoning_parts.append(f"Fallback: {neutral_reasoning}")
            else:
                # Fallback when trend tracker not available
                direction, direction_confidence, neutral_reasoning = \
                    self._get_neutral_direction_fallback(
                        context.spot_price, context.gex_call_wall, context.gex_put_wall,
                        position_in_range_pct, wall_filter_pct
                    )
                neutral_derived_direction = direction
                neutral_confidence = direction_confidence
                reasoning_parts.append(f"Fallback: {neutral_reasoning}")

        # =====================================================================
        # Wall filter check (now properly handles all directions)
        # =====================================================================
        if not wall_filter_passed and use_gex_walls:
            if direction == "BULLISH":
                if dist_to_put_wall <= wall_filter_pct:
                    wall_filter_passed = True
                    reasoning_parts.append(f"Wall filter PASSED: {dist_to_put_wall:.2f}% from put wall (threshold: {wall_filter_pct}%)")
                else:
                    reasoning_parts.append(f"Wall filter: {dist_to_put_wall:.2f}% from put wall (threshold: {wall_filter_pct}%)")
            elif direction == "BEARISH":
                if dist_to_call_wall <= wall_filter_pct:
                    wall_filter_passed = True
                    reasoning_parts.append(f"Wall filter PASSED: {dist_to_call_wall:.2f}% from call wall (threshold: {wall_filter_pct}%)")
                else:
                    reasoning_parts.append(f"Wall filter: {dist_to_call_wall:.2f}% from call wall (threshold: {wall_filter_pct}%)")

        # =====================================================================
        # Win probability: BLEND GBC model + direction confidence (V3 FIX)
        # =====================================================================
        # V3 FIX: Previously REPLACED base_pred['win_probability'] with direction_confidence,
        # which completely discarded the calibrated GBC model output. The GBC model trained
        # on historical IC/directional data was made irrelevant for directional bots.
        #
        # New approach: 40% GBC model (quality-of-setup) + 60% direction confidence.
        # Direction confidence gets higher weight because SOLOMON is directional trading
        # and the GBC model was primarily trained on IC outcomes.
        gbc_prob = base_pred['win_probability']

        if direction != "FLAT":
            dir_conf_clamped = max(0.40, min(0.85, direction_confidence))
            blended_prob = (gbc_prob * 0.4) + (dir_conf_clamped * 0.6)
            base_pred['win_probability'] = max(0.35, min(0.90, blended_prob))
            reasoning_parts.append(f"Blended prob: GBC {gbc_prob:.1%} × 0.4 + direction {dir_conf_clamped:.1%} × 0.6 = {base_pred['win_probability']:.1%}")

            # Boost if wall filter passed
            if wall_filter_passed:
                base_pred['win_probability'] = min(0.90, base_pred['win_probability'] + 0.10)

            # Boost for strong trends
            if trend_strength > 0.6:
                base_pred['win_probability'] = min(0.90, base_pred['win_probability'] + 0.05)
        else:
            # FLAT direction - keep GBC probability (it still reflects market quality)
            # Clamp to neutral range since no directional edge
            base_pred['win_probability'] = max(0.40, min(0.60, gbc_prob))
            reasoning_parts.append(f"FLAT direction: using GBC prob {gbc_prob:.1%} clamped to 0.40-0.60")

        # VIX impact
        if context.vix > 25:
            reasoning_parts.append("High VIX = wider spreads, more premium")
        elif context.vix < 15:
            reasoning_parts.append("Low VIX = narrower spreads")

        # =========================================================================
        # CLAUDE AI VALIDATION (if enabled)
        # =========================================================================
        claude_analysis = None
        if use_claude_validation and self.claude_available:
            claude_analysis = self.claude.validate_prediction(context, base_pred, BotName.SOLOMON)

            if claude_analysis.recommendation in ["ADJUST", "OVERRIDE"]:
                base_pred['win_probability'] = max(0.45, min(0.85,
                    base_pred['win_probability'] + claude_analysis.confidence_adjustment
                ))
                reasoning_parts.append(f"Claude: {claude_analysis.analysis}")

            # VALIDATE hallucination_risk - REDUCED penalties
            hallucination_risk = getattr(claude_analysis, 'hallucination_risk', 'LOW')
            if hallucination_risk == 'HIGH':
                penalty = 0.05  # REDUCED from 10%
                base_pred['win_probability'] = max(0.45, base_pred['win_probability'] - penalty)
                reasoning_parts.append(f"Claude hallucination risk HIGH (confidence reduced by {penalty:.0%})")
                logger.warning(f"[SOLOMON] Claude hallucination risk HIGH - reducing confidence by {penalty:.0%}")
            elif hallucination_risk == 'MEDIUM':
                penalty = 0.02  # REDUCED from 5%
                base_pred['win_probability'] = max(0.45, base_pred['win_probability'] - penalty)
                reasoning_parts.append(f"Claude hallucination risk MEDIUM (confidence reduced by {penalty:.0%})")
                logger.info(f"[SOLOMON] Claude hallucination risk MEDIUM - reducing confidence by {penalty:.0%}")

        # =====================================================================
        # FLIP DISTANCE FILTER - Data showed trades far from flip point lose
        # Winners avg 2.1% from flip, losers avg 4.8% from flip
        # Filter: 0.5-3% = TRADE_FULL, 3-5% = TRADE_REDUCED, >5% = SKIP
        # =====================================================================
        flip_distance_pct = 0.0
        flip_filter_applied = False
        if context.gex_flip_point > 0 and context.spot_price > 0:
            flip_distance_pct = abs(context.spot_price - context.gex_flip_point) / context.spot_price * 100

            if flip_distance_pct > 5.0:
                # Too far from flip - skip trade entirely
                base_pred['win_probability'] = max(0.35, base_pred['win_probability'] - 0.15)
                reasoning_parts.append(f"FLIP_FILTER: {flip_distance_pct:.1f}% from flip (>5%) - HIGH RISK")
                flip_filter_applied = True
                logger.info(f"[{bot_name}] Flip distance {flip_distance_pct:.1f}% > 5% - reducing win probability")
            elif flip_distance_pct > 3.0:
                # Moderate distance - reduce size
                base_pred['win_probability'] = max(0.40, base_pred['win_probability'] - 0.08)
                reasoning_parts.append(f"FLIP_FILTER: {flip_distance_pct:.1f}% from flip (3-5%) - REDUCED SIZE")
                flip_filter_applied = True
                logger.info(f"[{bot_name}] Flip distance {flip_distance_pct:.1f}% (3-5%) - trade with caution")
            else:
                # Sweet spot (0.5-3%) - full confidence
                reasoning_parts.append(f"FLIP_FILTER: {flip_distance_pct:.1f}% from flip - OPTIMAL ZONE")
                logger.info(f"[{bot_name}] Flip distance {flip_distance_pct:.1f}% - in optimal zone")

        # =====================================================================
        # FRIDAY SIZE REDUCTION - Data showed Friday has 14% WR, -$215K losses
        # Apply TRADE_REDUCED on Fridays with 0DTE expiration risk
        # =====================================================================
        is_friday = context.day_of_week == 4
        friday_risk_applied = False
        if is_friday:
            # Friday with 0DTE = high risk, reduce size
            base_pred['win_probability'] = max(0.40, base_pred['win_probability'] - 0.05)
            reasoning_parts.append("FRIDAY_FILTER: 0DTE + weekend gap risk - HALF SIZE")
            friday_risk_applied = True
            logger.info(f"[{bot_name}] Friday detected - applying size reduction")

        advice, risk_pct = self._get_advice_from_probability(base_pred['win_probability'])

        # Apply Friday size reduction AFTER advice calculation
        if friday_risk_applied and advice == TradingAdvice.TRADE_FULL:
            advice = TradingAdvice.TRADE_REDUCED
            risk_pct = risk_pct * 0.5
            logger.info(f"[{bot_name}] Friday: Downgraded TRADE_FULL -> TRADE_REDUCED")

        # Apply flip distance size reduction AFTER advice calculation
        if flip_filter_applied and flip_distance_pct > 3.0 and advice == TradingAdvice.TRADE_FULL:
            advice = TradingAdvice.TRADE_REDUCED
            risk_pct = risk_pct * 0.5
            logger.info(f"[{bot_name}] Flip distance: Downgraded TRADE_FULL -> TRADE_REDUCED")

        # Suggested strikes based on direction
        suggested_put = None
        suggested_call = None
        spread_direction = None

        if direction == "BULLISH" and advice != TradingAdvice.SKIP_TODAY:
            # Bull Call Spread: Buy ATM call, Sell OTM call
            suggested_call = round(context.spot_price)  # ATM
            spread_direction = "BULL_CALL_SPREAD"
            reasoning_parts.append(f"Recommend: {spread_direction}")
        elif direction == "BEARISH" and advice != TradingAdvice.SKIP_TODAY:
            # Bear Put Spread: Buy ATM put, Sell OTM put (debit spread for bearish directional plays)
            suggested_put = round(context.spot_price)  # ATM
            spread_direction = "BEAR_PUT_SPREAD"
            reasoning_parts.append(f"Recommend: {spread_direction}")

        # Map bot_name string to BotName enum
        try:
            prediction_bot_name = BotName[bot_name.upper()] if bot_name else BotName.SOLOMON
        except (KeyError, AttributeError):
            prediction_bot_name = BotName.SOLOMON

        prediction = ProphetPrediction(
            bot_name=prediction_bot_name,
            advice=advice,
            win_probability=base_pred['win_probability'],
            confidence=min(1.0, direction_confidence),  # FIX: Scale 0-1, not 0-100
            suggested_risk_pct=risk_pct * 0.5,  # Conservative for directional spreads
            suggested_sd_multiplier=1.0,
            use_gex_walls=use_gex_walls,
            suggested_put_strike=suggested_put,
            suggested_call_strike=suggested_call,
            top_factors=base_pred.get('top_factors', []),
            reasoning=" | ".join(reasoning_parts) + f" | Direction: {direction}",
            model_version=self.model_version,
            probabilities=base_pred.get('probabilities', {}),
            claude_analysis=claude_analysis,
            # New NEUTRAL regime fields
            neutral_derived_direction=neutral_derived_direction,
            neutral_confidence=neutral_confidence,
            neutral_reasoning=neutral_reasoning,
            ic_suitability=ic_suitability,
            bullish_suitability=bullish_suitability,
            bearish_suitability=bearish_suitability,
            trend_direction=trend_direction_str,
            trend_strength=trend_strength,
            position_in_range_pct=position_in_range_pct,
            wall_filter_passed=wall_filter_passed
        )

        # Log prediction result
        self.live_log.log("PREDICT_DONE", f"{bot_name}: {advice.value} ({base_pred['win_probability']:.1%})", {
            "advice": advice.value,
            "win_probability": base_pred['win_probability'],
            "direction": direction,
            "spread_type": spread_direction,
            "claude_validated": claude_analysis is not None
        })

        # === FULL DATA FLOW LOGGING: DECISION ===
        decision_data = {
            "advice": advice.value,
            "win_probability": base_pred['win_probability'],
            "confidence": prediction.confidence,
            "risk_pct": risk_pct * 0.5,
            "direction": direction,
            "spread_type": spread_direction,
            "direction_confidence": direction_confidence,
            "suggested_put_strike": suggested_put,
            "suggested_call_strike": suggested_call,
            "dist_to_call_wall": dist_to_call_wall,
            "dist_to_put_wall": dist_to_put_wall,
            # NEW: Flip distance and Friday filters for audit trail
            "flip_distance_pct": flip_distance_pct,
            "flip_filter_applied": flip_filter_applied,
            "is_friday": is_friday,
            "friday_risk_applied": friday_risk_applied,
            "reasoning": prediction.reasoning,
            "claude_validated": claude_analysis is not None,
            "claude_recommendation": claude_analysis.recommendation if claude_analysis else None,
            "claude_confidence_adj": claude_analysis.confidence_adjustment if claude_analysis else None,
            "model_version": self.model_version,
            "hours_since_training": self._get_hours_since_training()
        }
        self.live_log.log_data_flow(bot_name, "DECISION", decision_data)

        return self._add_staleness_to_prediction(prediction)

    # =========================================================================
    # ANCHOR ADVICE (SPX IRON CONDOR - WEEKLY)
    # =========================================================================

    def get_anchor_advice(
        self,
        context: MarketContext,
        use_gex_walls: bool = True,
        use_claude_validation: bool = True,
        vix_hard_skip: float = 0.0,
        vix_monday_friday_skip: float = 0.0,
        vix_streak_skip: float = 0.0,
        recent_losses: int = 0,
        spread_width: float = 10.0  # Default $10 spread width
    ) -> ProphetPrediction:
        """
        Get Iron Condor advice for ANCHOR (SPX Weekly Iron Condors).

        ANCHOR trades SPX weekly options with $10 spread widths.
        Key differences from FORTRESS:
        - SPX (cash-settled) vs SPY
        - Weekly expirations vs 0DTE
        - Larger notional value per contract
        - One trade per day max

        Args:
            context: Current market conditions
            use_gex_walls: Whether to suggest strikes based on GEX walls
            use_claude_validation: Whether to use Claude AI to validate prediction
            vix_hard_skip: Skip if VIX > this threshold (0 = disabled)
            vix_monday_friday_skip: Skip on Mon/Fri if VIX > this (0 = disabled)
            vix_streak_skip: Skip after recent losses if VIX > this (0 = disabled)
            recent_losses: Number of recent consecutive losses
            spread_width: Width of IC spreads (default $10)

        Returns:
            ProphetPrediction with SPX IC-specific advice
        """
        # Check for newer model version in DB and reload if available (Issue #1 fix)
        self._check_and_reload_model_if_stale()

        # Log prediction request
        self.live_log.log("PREDICT", "ANCHOR advice requested", {
            "vix": context.vix,
            "gex_regime": context.gex_regime.value,
            "spot_price": context.spot_price,
            "use_gex_walls": use_gex_walls,
            "use_claude": use_claude_validation,
            "vix_hard_skip": vix_hard_skip,
            "spread_width": spread_width,
            "model_version": self.model_version,
            "hours_since_training": self._get_hours_since_training()
        })

        # =========================================================================
        # VIX-BASED SKIP LOGIC (Similar to FORTRESS but tuned for SPX weekly)
        # =========================================================================
        skip_reason = None
        skip_threshold_used = 0.0

        # Rule 1: Hard VIX skip (SPX weekly more sensitive to vol)
        if vix_hard_skip > 0 and context.vix > vix_hard_skip:
            skip_reason = f"VIX {context.vix:.1f} > {vix_hard_skip} - volatility too high for SPX Iron Condor"
            skip_threshold_used = vix_hard_skip

        # Rule 2: Monday/Friday VIX skip (weekly expiration risk)
        elif vix_monday_friday_skip > 0 and context.day_of_week in [0, 4]:
            if context.vix > vix_monday_friday_skip:
                day_name = "Monday" if context.day_of_week == 0 else "Friday"
                skip_reason = f"VIX {context.vix:.1f} > {vix_monday_friday_skip} on {day_name} - weekly expiration risk"
                skip_threshold_used = vix_monday_friday_skip

        # Rule 3: Streak-based VIX skip
        elif vix_streak_skip > 0 and recent_losses >= 2:
            if context.vix > vix_streak_skip:
                skip_reason = f"VIX {context.vix:.1f} > {vix_streak_skip} with {recent_losses} recent losses - risk reduction"
                skip_threshold_used = vix_streak_skip

        # If any VIX skip rule triggered, return SKIP_TODAY
        # BUT: Check if conditions favor directional trading (SOLOMON)
        if skip_reason:
            # Get strategy recommendation to see if SOLOMON directional is better
            strategy_rec = self.get_strategy_recommendation(context)

            # Determine if we should suggest SOLOMON instead of just skipping
            suggest_solomon = False
            enhanced_reasoning = skip_reason

            if strategy_rec.recommended_strategy == StrategyType.DIRECTIONAL:
                suggest_solomon = True
                enhanced_reasoning = f"{skip_reason} | Consider SOLOMON directional: {strategy_rec.reasoning}"
            elif context.gex_regime == GEXRegime.NEGATIVE and context.vix < 40:
                # Trending market with elevated VIX = good for directional
                suggest_solomon = True
                enhanced_reasoning = f"{skip_reason} | GEX NEGATIVE (trending) favors SOLOMON directional"

            self.live_log.log("VIX_SKIP", skip_reason, {
                "vix": context.vix,
                "threshold": skip_threshold_used,
                "day_of_week": context.day_of_week,
                "recent_losses": recent_losses,
                "action": "SKIP_TODAY",
                "suggest_solomon": suggest_solomon,
                "strategy_rec": strategy_rec.recommended_strategy.value
            })
            skip_prediction = ProphetPrediction(
                bot_name=BotName.ANCHOR,
                advice=TradingAdvice.SKIP_TODAY,
                win_probability=0.35,
                confidence=0.95,
                suggested_risk_pct=0.0,
                suggested_sd_multiplier=1.0,
                reasoning=enhanced_reasoning,
                top_factors=[
                    ("vix_level", context.vix),
                    ("skip_threshold", skip_threshold_used),
                    ("day_of_week", context.day_of_week),
                    ("recent_losses", recent_losses),
                    ("suggest_solomon", 1.0 if suggest_solomon else 0.0)
                ],
                model_version=self.model_version,
                suggested_alternative=BotName.SOLOMON if suggest_solomon else None,
                strategy_recommendation=strategy_rec
            )
            return self._add_staleness_to_prediction(skip_prediction)

        # === FULL DATA FLOW LOGGING: INPUT ===
        input_data = {
            "spot_price": context.spot_price,
            "price_change_1d": context.price_change_1d,
            "vix": context.vix,
            "vix_percentile_30d": context.vix_percentile_30d,
            "vix_change_1d": context.vix_change_1d,
            "gex_net": context.gex_net,
            "gex_normalized": context.gex_normalized,
            "gex_regime": context.gex_regime.value,
            "gex_flip_point": context.gex_flip_point,
            "gex_call_wall": context.gex_call_wall,
            "gex_put_wall": context.gex_put_wall,
            "gex_distance_to_flip_pct": context.gex_distance_to_flip_pct,
            "gex_between_walls": context.gex_between_walls,
            "day_of_week": context.day_of_week,
            "days_to_opex": context.days_to_opex,
            "spread_width": spread_width
        }
        self.live_log.log_data_flow("ANCHOR", "INPUT", input_data)

        # Get base prediction
        base_pred = self._get_base_prediction(context)

        # === FULL DATA FLOW LOGGING: ML_OUTPUT ===
        self.live_log.log_data_flow("ANCHOR", "ML_OUTPUT", {
            "win_probability": base_pred.get('win_probability'),
            "top_factors": base_pred.get('top_factors', []),
            "probabilities": base_pred.get('probabilities', {}),
            "model_version": self.model_version
        })

        reasoning_parts = []
        ic_suitability = 0.50  # Start neutral
        position_in_range_pct = 50.0
        trend_direction_str = "SIDEWAYS"
        trend_strength = 0.0
        # NEUTRAL regime fields for consistency
        neutral_derived_direction = ""
        neutral_confidence = 0.0
        neutral_reasoning = ""
        bullish_suitability = 0.0
        bearish_suitability = 0.0
        wall_filter_passed = False

        # Calculate position in wall range
        wall_range = context.gex_call_wall - context.gex_put_wall
        if wall_range > 0 and context.spot_price > 0:
            position_in_range_pct = (context.spot_price - context.gex_put_wall) / wall_range * 100

        # =====================================================================
        # GEX REGIME HANDLING - NEUTRAL is GOOD for SPX IC
        # =====================================================================
        # V2: GEX regime adjusts ic_suitability but NOT win_probability (already in features)
        if context.gex_regime == GEXRegime.POSITIVE:
            reasoning_parts.append("Positive GEX favors pinning (ideal for SPX IC)")
            ic_suitability += 0.20

        elif context.gex_regime == GEXRegime.NEGATIVE:
            reasoning_parts.append("Negative GEX = trending (risky for SPX IC)")
            ic_suitability -= 0.15

        elif context.gex_regime == GEXRegime.NEUTRAL:
            # NEUTRAL is good for IC - walls holding, balanced market
            reasoning_parts.append("NEUTRAL GEX: Balanced market, walls likely to hold (good for SPX IC)")
            ic_suitability += 0.10

            # Use trend tracker if available
            if TREND_TRACKER_AVAILABLE and get_trend_tracker is not None:
                try:
                    tracker = get_trend_tracker()
                    tracker.update("SPY", context.spot_price / 10)  # Scale SPX to SPY for GEX

                    trend_analysis = tracker.analyze_trend("SPY")
                    if trend_analysis:
                        trend_direction_str = trend_analysis.direction.value
                        trend_strength = trend_analysis.strength

                        if trend_analysis.direction.value == "SIDEWAYS":
                            ic_suitability += 0.15
                            reasoning_parts.append("Sideways trend (IC paradise)")
                        elif trend_strength > 0.6:
                            ic_suitability -= 0.10
                            reasoning_parts.append(f"Strong {trend_direction_str} ({trend_strength:.0%})")

                    # Get full suitability
                    wall_position = tracker.analyze_wall_position(
                        "SPY", context.spot_price / 10,
                        context.gex_call_wall / 10, context.gex_put_wall / 10,
                        trend_analysis
                    )
                    suitability = tracker.calculate_strategy_suitability(
                        trend_analysis, wall_position, context.vix, "NEUTRAL"
                    )
                    ic_suitability = suitability.ic_suitability
                    bullish_suitability = suitability.bullish_suitability
                    bearish_suitability = suitability.bearish_suitability
                    position_in_range_pct = wall_position.position_in_range_pct

                    # For IC, derive direction based on position in range (for transparency)
                    if position_in_range_pct < 35:
                        neutral_derived_direction = "BULLISH"
                        neutral_confidence = 0.6
                    elif position_in_range_pct > 65:
                        neutral_derived_direction = "BEARISH"
                        neutral_confidence = 0.6
                    else:
                        neutral_derived_direction = "NEUTRAL"
                        neutral_confidence = 0.7
                    neutral_reasoning = f"SPX IC: Position {position_in_range_pct:.0f}% in wall range, trend {trend_direction_str}"

                except Exception as e:
                    logger.warning(f"[ANCHOR] Trend tracker error: {e}")

        if context.gex_between_walls:
            reasoning_parts.append("SPX between GEX walls - favorable for Iron Condor")
            ic_suitability += 0.10
        else:
            reasoning_parts.append(f"SPX GEX regime: {context.gex_regime.value}")
            ic_suitability -= 0.05

        ic_suitability = max(0.0, min(1.0, ic_suitability))

        # Weekly expiration considerations
        if context.days_to_opex <= 2:
            reasoning_parts.append(f"Near expiration ({context.days_to_opex} days) - elevated gamma risk")

        # Determine trading advice based on probability
        win_prob = base_pred['win_probability']

        # V3 FIX: Use adaptive thresholds (same as FORTRESS/CORNERSTONE/LAZARUS)
        # Previously hardcoded 0.58/0.52/0.48 which bypassed the V2 adaptive system.
        # Adaptive thresholds key off base_rate learned from training data.
        advice, risk_pct = self._get_advice_from_probability(win_prob)

        # ANCHOR-specific risk scaling: SPX weekly IC uses lower risk % than SPY 0DTE
        # _get_advice_from_probability returns 10.0/3.0-8.0/0.0 for FORTRESS-scale trades.
        # ANCHOR needs ~30% of those values because SPX contracts are ~10x SPY notional.
        risk_pct = risk_pct * 0.30  # e.g. FULL 10% → 3%, REDUCED ~5% → 1.5%

        if advice == TradingAdvice.TRADE_FULL:
            reasoning_parts.append(f"Strong setup: {win_prob:.1%} win probability (adaptive threshold: {self.high_confidence_threshold:.2f})")
        elif advice == TradingAdvice.TRADE_REDUCED:
            reasoning_parts.append(f"Moderate setup: {win_prob:.1%} win probability")
        else:
            reasoning_parts.append(f"Below threshold: {win_prob:.1%} < {self.low_confidence_threshold:.2f} - skip")

        # GEX wall-based strike suggestions for SPX
        # ANCHOR RULE: Strikes must ALWAYS be at least 1 SD from spot
        suggested_put = None
        suggested_call = None

        # Calculate 1 SD expected move (minimum strike distance)
        import math
        annual_factor = math.sqrt(252)
        daily_vol = (context.vix / 100) / annual_factor if context.vix > 0 else 0.01
        expected_move = context.spot_price * daily_vol
        # Ensure minimum expected move of 0.5% of spot
        expected_move = max(expected_move, context.spot_price * 0.005)

        # Calculate minimum allowed strikes (1 SD from spot)
        min_put_strike = context.spot_price - expected_move
        min_call_strike = context.spot_price + expected_move

        if use_gex_walls and context.gex_put_wall > 0 and context.gex_call_wall > 0:
            # For SPX IC, use GEX walls as outer boundaries
            # But ONLY if they result in strikes >= 1 SD from spot
            gex_put = context.gex_put_wall - spread_width
            gex_call = context.gex_call_wall + spread_width

            # Check if GEX-based strikes meet minimum distance requirement
            if gex_put <= min_put_strike and gex_call >= min_call_strike:
                suggested_put = gex_put
                suggested_call = gex_call
                reasoning_parts.append(f"GEX walls: Put {context.gex_put_wall:.0f}, Call {context.gex_call_wall:.0f} (>= 1 SD)")
            else:
                # GEX walls too tight - use 1 SD minimum instead
                suggested_put = min_put_strike - spread_width
                suggested_call = min_call_strike + spread_width
                reasoning_parts.append(f"GEX walls too tight, using 1 SD minimum (EM=${expected_move:.0f})")

        # Claude AI validation (optional)
        # Fixed: Was incorrectly referencing self.claude_analyzer (doesn't exist)
        claude_analysis = None
        if use_claude_validation and self.claude_available and self.claude:
            try:
                claude_analysis = self.claude.validate_prediction(
                    context, base_pred, BotName.ANCHOR
                )
                if claude_analysis:
                    reasoning_parts.append(f"Claude: {claude_analysis.recommendation}")
                    # Adjust confidence based on Claude
                    if claude_analysis.confidence_adjustment:
                        win_prob = min(0.95, max(0.05, win_prob + claude_analysis.confidence_adjustment))

                    # VALIDATE hallucination_risk and reduce confidence if HIGH
                    # V3 FIX: Standardized to 5%/2% (was 10%/5%, 2x higher than other bots)
                    hallucination_risk = getattr(claude_analysis, 'hallucination_risk', 'LOW')
                    if hallucination_risk == 'HIGH':
                        penalty = 0.05  # V3: Standardized from 0.10 to match FORTRESS/LAZARUS/SOLOMON
                        win_prob = max(0.05, win_prob - penalty)
                        reasoning_parts.append(f"Claude hallucination risk HIGH (confidence reduced by {penalty:.0%})")
                        logger.warning(f"[ANCHOR] Claude hallucination risk HIGH - reducing confidence by {penalty:.0%}")
                    elif hallucination_risk == 'MEDIUM':
                        penalty = 0.02  # V3: Standardized from 0.05 to match FORTRESS/LAZARUS/SOLOMON
                        win_prob = max(0.05, win_prob - penalty)
                        reasoning_parts.append(f"Claude hallucination risk MEDIUM (confidence reduced by {penalty:.0%})")
                        logger.info(f"[ANCHOR] Claude hallucination risk MEDIUM - reducing confidence by {penalty:.0%}")
            except Exception as e:
                logger.warning(f"ANCHOR Claude validation failed: {e}")
                self.live_log.log("CLAUDE_ERROR", f"ANCHOR Claude validation failed: {e}")

        # Build final prediction
        # Fixed: confidence should be derived from win_prob, not base_pred (which doesn't have 'confidence' key)
        # Confidence represents certainty in the prediction itself, scaled from win_probability
        model_confidence = min(0.95, 0.5 + abs(win_prob - 0.5) * 2)  # Higher when win_prob is far from 50%
        prediction = ProphetPrediction(
            bot_name=BotName.ANCHOR,
            advice=advice,
            win_probability=win_prob,
            confidence=model_confidence,
            suggested_risk_pct=risk_pct,
            suggested_sd_multiplier=1.2,  # FIX: Was 1.0 - strikes 20% outside expected move
            reasoning=" | ".join(reasoning_parts),
            top_factors=base_pred.get('top_factors', []),
            model_version=self.model_version,
            suggested_put_strike=suggested_put,
            suggested_call_strike=suggested_call,
            claude_analysis=claude_analysis,
            # NEUTRAL regime fields (all 10 for consistency)
            neutral_derived_direction=neutral_derived_direction,
            neutral_confidence=neutral_confidence,
            neutral_reasoning=neutral_reasoning,
            ic_suitability=ic_suitability,
            bullish_suitability=bullish_suitability,
            bearish_suitability=bearish_suitability,
            trend_direction=trend_direction_str,
            trend_strength=trend_strength,
            position_in_range_pct=position_in_range_pct,
            wall_filter_passed=wall_filter_passed
        )

        # Log prediction result
        self.live_log.log("PREDICT_DONE", f"ANCHOR: {advice.value} ({win_prob:.1%})", {
            "advice": advice.value,
            "win_probability": win_prob,
            "spread_width": spread_width,
            "claude_validated": claude_analysis is not None
        })

        # === FULL DATA FLOW LOGGING: DECISION ===
        decision_data = {
            "advice": advice.value,
            "win_probability": win_prob,
            "confidence": prediction.confidence,
            "risk_pct": risk_pct,
            "spread_width": spread_width,
            "suggested_put_strike": suggested_put,
            "suggested_call_strike": suggested_call,
            "reasoning": prediction.reasoning,
            "claude_validated": claude_analysis is not None,
            "model_version": self.model_version,
            "hours_since_training": self._get_hours_since_training()
        }
        self.live_log.log_data_flow("ANCHOR", "DECISION", decision_data)

        return self._add_staleness_to_prediction(prediction)

    # =========================================================================
    # BASE PREDICTION
    # =========================================================================

    def _get_base_prediction(self, context: MarketContext) -> Dict[str, Any]:
        """Get base ML prediction from context.

        V2: Supports V3 features (cyclical day, VRP) with backward compat for V2/V1 models.
        """
        if not self.is_trained:
            return self._fallback_prediction(context)

        # Prepare features based on which version the model was trained with
        gex_regime_positive = 1 if context.gex_regime == GEXRegime.POSITIVE else 0
        gex_between_walls = 1 if context.gex_between_walls else 0
        feature_version = getattr(self, '_feature_version', 2)

        if feature_version >= 3 and self._has_gex_features:
            # V3: cyclical day encoding, VRP, 60d win rate
            day_sin = math.sin(2 * math.pi * context.day_of_week / 5)
            day_cos = math.cos(2 * math.pi * context.day_of_week / 5)

            # V3 FIX: VRP proxy that scales with VIX level
            # Training computes VRP = expected_move_pct - realized_vol_5d (rolling 5-trade)
            # At inference we don't have historical price changes, so approximate:
            # - Low VIX (<15): VRP ~10% of EM (tight spread between implied and realized)
            # - Normal VIX (15-25): VRP ~20% of EM (typical risk premium)
            # - High VIX (>25): VRP ~30% of EM (VIX overestimates realized vol more)
            vrp_ratio = 0.10 + 0.004 * min(context.vix, 50)  # Scales: VIX10→0.14, VIX20→0.18, VIX30→0.22, VIX40→0.26
            volatility_risk_premium = context.expected_move_pct * vrp_ratio

            features = np.array([[
                context.vix,
                context.vix_percentile_30d,
                context.vix_change_1d,
                day_sin,
                day_cos,
                context.price_change_1d,
                context.expected_move_pct,
                volatility_risk_premium,
                context.win_rate_30d,  # MarketContext still uses win_rate_30d field for 60d value
                context.gex_normalized,
                gex_regime_positive,
                context.gex_distance_to_flip_pct,
                gex_between_walls,
            ]])
            trained_cols = self.FEATURE_COLS
        elif self._has_gex_features:
            # V2: integer day, win_rate_30d, no VRP
            features = np.array([[
                context.vix,
                context.vix_percentile_30d,
                context.vix_change_1d,
                context.day_of_week,
                context.price_change_1d,
                context.expected_move_pct,
                context.win_rate_30d,
                context.gex_normalized,
                gex_regime_positive,
                context.gex_distance_to_flip_pct,
                gex_between_walls,
            ]])
            trained_cols = self.FEATURE_COLS_V2
        else:
            # V1: no GEX
            features = np.array([[
                context.vix,
                context.vix_percentile_30d,
                context.vix_change_1d,
                context.day_of_week,
                context.price_change_1d,
                context.expected_move_pct,
                context.win_rate_30d,
            ]])
            trained_cols = self.FEATURE_COLS_V1

        # Scale and predict
        features_scaled = self.scaler.transform(features)

        if self.calibrated_model:
            proba_result = self.calibrated_model.predict_proba(features_scaled)
        else:
            proba_result = self.model.predict_proba(features_scaled)

        # Safe access to predict_proba results (expected shape: (1, 2) for binary classifier)
        if proba_result is None or len(proba_result) == 0:
            return self._fallback_prediction(context)
        proba = proba_result[0]
        if len(proba) < 2:
            return self._fallback_prediction(context)

        win_probability = float(proba[1])

        # Feature importance
        feature_importance = dict(zip(trained_cols, self.model.feature_importances_))
        top_factors = sorted(feature_importance.items(), key=lambda x: -x[1])[:3]

        return {
            'win_probability': win_probability,
            'top_factors': top_factors,
            'probabilities': {'win': float(proba[1]), 'loss': float(proba[0])}
        }

    def _fallback_prediction(self, context: MarketContext) -> Dict[str, Any]:
        """Rule-based fallback when model not trained"""
        # Start neutral - let conditions determine probability
        base_prob = 0.60

        # VIX is the primary filter (major impact on IC success)
        if context.vix > 35:
            base_prob -= 0.20  # High VIX = volatile = bad for IC
        elif context.vix > 30:
            base_prob -= 0.15
        elif context.vix > 25:
            base_prob -= 0.10
        elif context.vix > 20:
            base_prob -= 0.05
        elif context.vix < 12:
            base_prob -= 0.05  # Too low VIX = low premium, not worth it
        elif 14 <= context.vix <= 18:
            base_prob += 0.08  # Sweet spot for premium selling

        # Day of week - all days are tradable (removed penalties to allow daily trading)
        # Previously: Monday -8%, Friday -5% - now neutral to enable consistent daily trading
        dow_adj = {0: 0.0, 1: 0.02, 2: 0.03, 3: 0.02, 4: 0.0}
        base_prob += dow_adj.get(context.day_of_week, 0)

        # GEX regime (major factor for mean reversion)
        if context.gex_regime == GEXRegime.POSITIVE:
            base_prob += 0.10  # Positive GEX = mean reversion = good for IC
        elif context.gex_regime == GEXRegime.NEGATIVE:
            base_prob -= 0.12  # Negative GEX = trending = bad for IC

        # Price position relative to GEX walls
        if not context.gex_between_walls:
            base_prob -= 0.10  # Outside walls = more risky

        # Distance to flip point (closer = more uncertain)
        if context.gex_distance_to_flip_pct is not None:
            if abs(context.gex_distance_to_flip_pct) < 0.5:
                base_prob -= 0.08  # Very close to flip = regime change possible

        # Recent performance (momentum)
        if context.win_rate_30d is not None:
            if context.win_rate_30d < 0.50:
                base_prob -= 0.08  # Recent poor performance = be cautious
            elif context.win_rate_30d > 0.80:
                base_prob += 0.05  # Strong recent performance

        # Expected move (if unusually high, skip)
        if context.expected_move_pct is not None:
            if context.expected_move_pct > 2.0:  # >2% expected move is dangerous
                base_prob -= 0.10
            elif context.expected_move_pct > 1.5:
                base_prob -= 0.05

        win_probability = max(0.30, min(0.85, base_prob))

        return {
            'win_probability': win_probability,
            'top_factors': [('vix', 0.4), ('gex_regime', 0.3), ('day_of_week', 0.2)],
            'probabilities': {'win': win_probability, 'loss': 1 - win_probability}
        }

    def _get_advice_from_probability(self, win_prob: float) -> Tuple[TradingAdvice, float]:
        """Convert win probability to advice and risk percentage"""
        if win_prob >= self.high_confidence_threshold:
            return TradingAdvice.TRADE_FULL, 10.0
        elif win_prob >= self.low_confidence_threshold:
            risk = 3.0 + (win_prob - self.low_confidence_threshold) / \
                (self.high_confidence_threshold - self.low_confidence_threshold) * 5.0
            return TradingAdvice.TRADE_REDUCED, risk
        else:
            return TradingAdvice.SKIP_TODAY, 0.0

    def _get_neutral_direction_fallback(
        self,
        spot_price: float,
        call_wall: float,
        put_wall: float,
        position_in_range_pct: float,
        wall_filter_pct: float
    ) -> Tuple[str, float, str]:
        """
        Fallback direction determination for NEUTRAL regime when trend tracker unavailable.

        Uses wall proximity to determine direction instead of defaulting to FLAT.

        Args:
            spot_price: Current spot price
            call_wall: Call wall level
            put_wall: Put wall level
            position_in_range_pct: Where price sits in range (0-100)
            wall_filter_pct: Wall filter threshold

        Returns:
            Tuple of (direction, confidence, reasoning)
        """
        # Calculate distances
        dist_to_call = 0
        dist_to_put = 0

        if call_wall > 0 and spot_price > 0:
            dist_to_call = (call_wall - spot_price) / spot_price * 100
        if put_wall > 0 and spot_price > 0:
            dist_to_put = (spot_price - put_wall) / spot_price * 100

        # Determine direction based on wall proximity
        if position_in_range_pct < 35:
            # Lower third = near put wall = expect bounce = BULLISH
            direction = "BULLISH"
            confidence = 0.60
            reasoning = f"Near put wall support ({position_in_range_pct:.0f}% of range)"
        elif position_in_range_pct > 65:
            # Upper third = near call wall = expect pullback = BEARISH
            direction = "BEARISH"
            confidence = 0.60
            reasoning = f"Near call wall resistance ({position_in_range_pct:.0f}% of range)"
        else:
            # Middle of range - use nearest wall
            if dist_to_put < dist_to_call:
                direction = "BULLISH"
                confidence = 0.55
                reasoning = f"Mid-range, closer to put wall ({dist_to_put:.1f}%)"
            else:
                direction = "BEARISH"
                confidence = 0.55
                reasoning = f"Mid-range, closer to call wall ({dist_to_call:.1f}%)"

        # Adjust confidence if within wall filter threshold
        if direction == "BULLISH" and dist_to_put <= wall_filter_pct:
            confidence = min(0.75, confidence + 0.10)
            reasoning += f" | Within {wall_filter_pct}% of support"
        elif direction == "BEARISH" and dist_to_call <= wall_filter_pct:
            confidence = min(0.75, confidence + 0.10)
            reasoning += f" | Within {wall_filter_pct}% of resistance"

        logger.info(f"[NEUTRAL Fallback] {direction} ({confidence:.0%}): {reasoning}")

        return direction, confidence, reasoning

    # =========================================================================
    # CLAUDE AI METHODS
    # =========================================================================

    def explain_prediction(
        self,
        prediction: ProphetPrediction,
        context: MarketContext
    ) -> str:
        """
        Get natural language explanation of prediction using Claude AI.

        Args:
            prediction: Prophet prediction to explain
            context: Market context used for prediction

        Returns:
            Human-readable explanation string
        """
        if self.claude_available:
            return self.claude.explain_prediction(prediction, context)
        else:
            return f"Prophet predicts {prediction.advice.value} with {prediction.win_probability:.1%} confidence. {prediction.reasoning}"

    def get_claude_analysis(
        self,
        context: MarketContext,
        bot_name: BotName = BotName.FORTRESS
    ) -> Optional[ClaudeAnalysis]:
        """
        Get standalone Claude AI analysis of market conditions.

        Args:
            context: Current market conditions
            bot_name: Which bot is requesting analysis

        Returns:
            ClaudeAnalysis or None if Claude unavailable
        """
        if not self.claude_available:
            return None

        # Get base prediction first
        base_pred = self._get_base_prediction(context)
        return self.claude.validate_prediction(context, base_pred, bot_name)

    def analyze_patterns(
        self,
        backtest_results: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Use Claude to analyze patterns in training data.

        Args:
            backtest_results: Optional CHRONICLES results (will extract features if provided)

        Returns:
            Dict with pattern analysis
        """
        if not self.claude_available:
            return {
                "success": False,
                "error": "Claude AI not available",
                "patterns": [],
                "recommendations": []
            }

        # Extract features if backtest results provided
        df = None
        if backtest_results:
            try:
                df = self.extract_features_from_chronicles(backtest_results)
            except Exception as e:
                logger.error(f"Failed to extract features: {e}")

        # Get recent losses for analysis
        recent_losses = None
        if df is not None and 'is_win' in df.columns:
            losses = df[df['is_win'] == False].tail(10)
            if len(losses) > 0:
                recent_losses = losses.to_dict('records')

        return self.claude.analyze_training_patterns(df, recent_losses)

    # =========================================================================
    # TRAINING
    # =========================================================================

    def extract_features_from_chronicles(
        self,
        backtest_results: Dict[str, Any],
        include_gex: bool = True
    ) -> pd.DataFrame:
        """
        Extract ML features from CHRONICLES backtest results.

        V3: Adds cyclical day encoding, VRP, 60-trade win rate horizon.
        Fixes training/inference mismatch for price_change_1d (uses previous-day
        change instead of same-day close which is look-ahead bias).
        """
        if not ML_AVAILABLE:
            raise ImportError("ML libraries required")

        trades = backtest_results.get('all_trades', [])
        if not trades:
            logger.warning("No trades found in backtest results")
            return pd.DataFrame()

        # Check if GEX data is available
        has_gex = 'gex_normalized' in trades[0] if trades else False

        if include_gex and not has_gex:
            logger.info("GEX data not found. Enriching with GEX...")
            try:
                from quant.chronicles_gex_calculator import enrich_trades_with_gex
                backtest_results = enrich_trades_with_gex(backtest_results)
                trades = backtest_results.get('all_trades', [])
                has_gex = 'gex_normalized' in trades[0] if trades else False
                if has_gex:
                    logger.info("Successfully enriched with GEX data")
            except Exception as e:
                logger.warning(f"Could not enrich with GEX: {e}")
                has_gex = False

        records = []
        outcomes = []
        pnls = []
        price_changes = []  # Track for VRP calculation

        for i, trade in enumerate(trades):
            # Rolling stats - 60 trade lookback (reduced leakage vs 30-day)
            lookback_start_60 = max(0, i - 60)
            recent_outcomes_60 = outcomes[lookback_start_60:i] if i > 0 else []

            win_rate_60d = sum(1 for o in recent_outcomes_60 if o == 'MAX_PROFIT') / len(recent_outcomes_60) if recent_outcomes_60 else 0.68

            trade_date = trade.get('trade_date', '')
            try:
                dt = datetime.strptime(trade_date, '%Y-%m-%d')
                day_of_week = dt.weekday()
            except (ValueError, TypeError) as e:
                logger.debug(f"Date parsing failed for {trade_date}: {e}, defaulting to Wednesday")
                day_of_week = 2  # Default to Wednesday

            # Cyclical day encoding (Mon=0..Fri=4 → sin/cos over 5-day cycle)
            day_sin = math.sin(2 * math.pi * day_of_week / 5)
            day_cos = math.cos(2 * math.pi * day_of_week / 5)

            vix = trade.get('vix', 20.0)
            open_price = trade.get('open_price', 5000)
            close_price = trade.get('close_price', open_price)

            # V3 FIX: price_change_1d = PREVIOUS day's move, not same-day close.
            # In live inference, we don't know today's close at trade entry time.
            # Use the previous trade's price change to avoid look-ahead bias.
            if i > 0:
                prev_open = trades[i - 1].get('open_price', open_price)
                prev_close = trades[i - 1].get('close_price', prev_open)
                price_change_1d = (prev_close - prev_open) / prev_open * 100 if prev_open > 0 else 0
            else:
                price_change_1d = 0

            expected_move = trade.get('expected_move_sd', trade.get('expected_move_1d', 50))
            expected_move_pct = expected_move / open_price * 100 if open_price > 0 else 1.0

            outcome = trade.get('outcome', 'MAX_PROFIT')
            is_win = outcome == 'MAX_PROFIT'
            net_pnl = trade.get('net_pnl', 0)

            outcomes.append(outcome)
            pnls.append(net_pnl)

            # Track actual intraday move for VRP calculation
            actual_change = abs(close_price - open_price) / open_price * 100 if open_price > 0 else 0
            price_changes.append(actual_change)

            # VRP: expected move (IV proxy) - realized vol (5-trade rolling std of price changes)
            if len(price_changes) >= 5:
                recent_changes = price_changes[-5:]
                realized_vol_5d = (sum(c**2 for c in recent_changes) / len(recent_changes)) ** 0.5
            else:
                realized_vol_5d = expected_move_pct * 0.8  # Approximate

            volatility_risk_premium = expected_move_pct - realized_vol_5d

            record = {
                'trade_date': trade_date,
                'vix': vix,
                'vix_percentile_30d': 50,  # Computed after DataFrame creation
                'vix_change_1d': 0,        # Computed after DataFrame creation
                'day_of_week': day_of_week,  # Keep for V2 backward compat
                'day_of_week_sin': day_sin,
                'day_of_week_cos': day_cos,
                'price_change_1d': price_change_1d,
                'expected_move_pct': expected_move_pct,
                'volatility_risk_premium': volatility_risk_premium,
                'win_rate_60d': win_rate_60d,
                'outcome': outcome,
                'is_win': is_win,
                'net_pnl': net_pnl,
            }

            if has_gex:
                gex_regime = trade.get('gex_regime', 'NEUTRAL')
                record['gex_normalized'] = trade.get('gex_normalized', 0)
                record['gex_regime_positive'] = 1 if gex_regime == 'POSITIVE' else 0
                record['gex_distance_to_flip_pct'] = trade.get('gex_distance_to_flip_pct', 0)
                record['gex_between_walls'] = 1 if trade.get('gex_between_walls', True) else 0
            else:
                record['gex_normalized'] = 0
                record['gex_regime_positive'] = 0
                record['gex_distance_to_flip_pct'] = 0
                record['gex_between_walls'] = 1

            records.append(record)

        df = pd.DataFrame(records)

        if len(df) > 1:
            df['vix_percentile_30d'] = df['vix'].rolling(30, min_periods=1).apply(
                lambda x: (x.rank().iloc[-1] / len(x)) * 100 if len(x) > 0 else 50
            ).fillna(50)
            df['vix_change_1d'] = df['vix'].pct_change().fillna(0) * 100

        self._has_gex_features = has_gex
        return df

    def train_from_chronicles(
        self,
        backtest_results: Dict[str, Any],
        test_size: float = 0.2,
        min_samples: int = 100
    ) -> TrainingMetrics:
        """
        Train Prophet from CHRONICLES backtest results.

        V2 improvements (matching WISDOM V3 patterns):
        - sample_weight to handle class imbalance (IC ~70-90% win rate)
        - Brier score on held-out CV folds (not training data)
        - Adaptive thresholds based on learned base rate
        - V3 features: cyclical day encoding, VRP, 60-trade win rate
        """
        # Log training start
        self.live_log.log("TRAIN_START", "Prophet V2 training initiated from CHRONICLES data", {
            "test_size": test_size,
            "min_samples": min_samples
        })

        if not ML_AVAILABLE:
            self.live_log.log("TRAIN_ERROR", "ML libraries not available", {})
            raise ImportError("ML libraries required")

        df = self.extract_features_from_chronicles(backtest_results)

        if len(df) < min_samples:
            raise ValueError(f"Insufficient data: {len(df)} < {min_samples}")

        logger.info(f"Training Prophet V2 on {len(df)} trades")

        # Use V3 features if GEX available, else V1
        feature_cols = self.FEATURE_COLS if self._has_gex_features else self.FEATURE_COLS_V1
        X = df[feature_cols].values
        y = df['is_win'].values.astype(int)

        # Class imbalance: compute sample_weight
        # For IC trading with ~89% win rate, losses are underrepresented
        n_wins = int(y.sum())
        n_losses = int(len(y) - n_wins)
        if n_wins > 0 and n_losses > 0:
            # Weight losses higher so model learns to distinguish them
            weight_win = n_losses / len(y)
            weight_loss = n_wins / len(y)
            sample_weight_array = np.where(y == 1, weight_win, weight_loss)
        else:
            sample_weight_array = np.ones(len(y))
        logger.info(f"Class balance: {n_wins} wins, {n_losses} losses, ratio={n_wins/max(1,n_losses):.1f}:1")

        # Store base rate for adaptive thresholds
        self._base_rate = float(y.mean())

        self.scaler = StandardScaler()
        X_scaled = self.scaler.fit_transform(X)

        tscv = TimeSeriesSplit(n_splits=5)

        self.model = GradientBoostingClassifier(
            n_estimators=150,
            max_depth=4,
            learning_rate=0.1,
            min_samples_split=20,
            min_samples_leaf=10,
            subsample=0.8,
            random_state=42
        )

        accuracies, precisions, recalls, f1s, aucs, briers = [], [], [], [], [], []

        for train_idx, test_idx in tscv.split(X_scaled):
            X_train, X_test = X_scaled[train_idx], X_scaled[test_idx]
            y_train, y_test = y[train_idx], y[test_idx]
            sw_train = sample_weight_array[train_idx]

            self.model.fit(X_train, y_train, sample_weight=sw_train)
            y_pred = self.model.predict(X_test)
            y_proba = self.model.predict_proba(X_test)[:, 1]

            accuracies.append(accuracy_score(y_test, y_pred))
            precisions.append(precision_score(y_test, y_pred, zero_division=0))
            recalls.append(recall_score(y_test, y_pred, zero_division=0))
            f1s.append(f1_score(y_test, y_pred, zero_division=0))
            briers.append(brier_score_loss(y_test, y_proba))
            try:
                aucs.append(roc_auc_score(y_test, y_proba))
            except ValueError:
                aucs.append(0.5)

        # Final model fit on all data with sample weights
        self.model.fit(X_scaled, y, sample_weight=sample_weight_array)

        # Calibrate probabilities (isotonic calibration on full dataset)
        self.calibrated_model = CalibratedClassifierCV(self.model, method='isotonic', cv=3)
        self.calibrated_model.fit(X_scaled, y)

        feature_importances = dict(zip(feature_cols, self.model.feature_importances_))

        # Brier score from CV folds (NOT in-sample)
        brier_cv = np.mean(briers) if briers else 0.25

        self.training_metrics = TrainingMetrics(
            accuracy=np.mean(accuracies),
            precision=np.mean(precisions),
            recall=np.mean(recalls),
            f1_score=np.mean(f1s),
            auc_roc=np.mean(aucs),
            brier_score=brier_cv,
            win_rate_predicted=float(self.calibrated_model.predict_proba(X_scaled)[:, 1].mean()),
            win_rate_actual=y.mean(),
            total_samples=len(df),
            train_samples=int(len(df) * (1 - test_size)),
            test_samples=int(len(df) * test_size),
            positive_samples=n_wins,
            negative_samples=n_losses,
            feature_importances=feature_importances,
            training_date=datetime.now().isoformat(),
            model_version="2.0.0"
        )

        self.is_trained = True
        self.model_version = "2.0.0"
        self._feature_version = 3
        self._trained_feature_cols = feature_cols
        self._save_model()

        # Set adaptive thresholds based on base rate
        self._update_thresholds_from_base_rate()

        # Log training complete
        self.live_log.log("TRAIN_DONE", f"Prophet V2 trained - Accuracy: {self.training_metrics.accuracy:.1%}", {
            "accuracy": self.training_metrics.accuracy,
            "auc_roc": self.training_metrics.auc_roc,
            "brier_cv": brier_cv,
            "total_samples": self.training_metrics.total_samples,
            "win_rate_actual": self.training_metrics.win_rate_actual,
            "model_version": self.model_version,
            "base_rate": self._base_rate,
            "class_balance": f"{n_wins}W/{n_losses}L"
        })

        logger.info(f"Prophet V2 trained successfully (features V3):")
        logger.info(f"  Accuracy: {self.training_metrics.accuracy:.2%}")
        logger.info(f"  AUC-ROC: {self.training_metrics.auc_roc:.3f}")
        logger.info(f"  Brier Score (CV): {brier_cv:.4f}")
        logger.info(f"  Win Rate (actual): {self.training_metrics.win_rate_actual:.2%}")
        logger.info(f"  Class balance: {n_wins}W / {n_losses}L")
        logger.info(f"  Adaptive thresholds: SKIP < {self.low_confidence_threshold:.2f}, FULL >= {self.high_confidence_threshold:.2f}")

        # =========================================================================
        # CLAUDE PATTERN ANALYSIS (if enabled)
        # =========================================================================
        if self.claude_available:
            logger.info("Running Claude AI pattern analysis...")
            try:
                pattern_analysis = self.claude.analyze_training_patterns(df)
                if pattern_analysis.get('success'):
                    logger.info("Claude identified patterns:")
                    for pattern in pattern_analysis.get('patterns', [])[:3]:
                        logger.info(f"  - {pattern}")
                    logger.info("Claude recommendations:")
                    for rec in pattern_analysis.get('recommendations', [])[:3]:
                        logger.info(f"  - {rec}")
            except Exception as e:
                logger.warning(f"Claude pattern analysis failed: {e}")

        return self.training_metrics

    # =========================================================================
    # DATABASE PERSISTENCE
    # =========================================================================

    def store_prediction(
        self,
        prediction: ProphetPrediction,
        context: MarketContext,
        trade_date: str,
        position_id: str = None,
        strategy_recommendation: str = None
    ) -> int:
        """
        Store prediction to database for feedback loop - FULL data persistence.

        Args:
            prediction: The ProphetPrediction object
            context: Market context at prediction time
            trade_date: Date of the trade
            position_id: Unique position ID (required for 1:1 prediction-to-position linking)
            strategy_recommendation: IRON_CONDOR or DIRECTIONAL (Prophet's strategy advice)

        Returns:
            prediction_id (int) if successful, None if failed

        Note: Per Option C, this should only be called when a position is actually opened,
        not on every scan. This ensures 1:1 prediction-to-position mapping.
        """
        # Helper to convert numpy types to Python native types
        def _convert_numpy(val):
            try:
                import numpy as np
                if isinstance(val, (np.integer, np.int64, np.int32)):
                    return int(val)
                elif isinstance(val, (np.floating, np.float64, np.float32)):
                    return float(val)
                elif isinstance(val, np.bool_):
                    return bool(val)
                elif isinstance(val, np.ndarray):
                    return val.tolist()
            except ImportError:
                pass
            return val

        def _convert_dict_numpy(d):
            if d is None:
                return None
            if isinstance(d, dict):
                return {k: _convert_dict_numpy(v) for k, v in d.items()}
            elif isinstance(d, list):
                return [_convert_dict_numpy(item) for item in d]
            return _convert_numpy(d)

        if not DB_AVAILABLE:
            logger.warning("Database not available")
            return False

        with get_db_connection() as conn:
            if conn is None:
                return False
            try:
                cursor = conn.cursor()

                # Ensure table has all required columns (migration-safe)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS prophet_predictions (
                    id SERIAL PRIMARY KEY,
                    timestamp TIMESTAMPTZ DEFAULT NOW(),
                    trade_date DATE NOT NULL,
                    bot_name TEXT NOT NULL,
                    prediction_time TIMESTAMPTZ DEFAULT NOW(),

                    -- Market Context
                    spot_price REAL,
                    vix REAL,
                    gex_net REAL,
                    gex_normalized REAL,
                    gex_regime TEXT,
                    gex_flip_point REAL,
                    gex_call_wall REAL,
                    gex_put_wall REAL,
                    day_of_week INTEGER,

                    -- Prediction Details
                    advice TEXT,
                    win_probability REAL,
                    confidence REAL,
                    suggested_risk_pct REAL,
                    suggested_sd_multiplier REAL,
                    model_version TEXT,

                    -- GEX-Specific (FORTRESS)
                    use_gex_walls BOOLEAN DEFAULT FALSE,
                    suggested_put_strike REAL,
                    suggested_call_strike REAL,

                    -- Explanation & Transparency
                    reasoning TEXT,
                    top_factors JSONB,
                    probabilities JSONB,

                    -- Claude AI Analysis (full transparency)
                    claude_analysis JSONB,

                    -- Outcomes (filled after trade closes)
                    prediction_used BOOLEAN DEFAULT FALSE,
                    actual_outcome TEXT,
                    actual_pnl REAL,
                    outcome_date DATE,

                    UNIQUE(trade_date, bot_name)
                    )
                """)

                # Migration: Add missing columns to existing tables
                migration_columns = [
                    ("claude_analysis", "JSONB"),
                    ("prediction_used", "BOOLEAN DEFAULT FALSE"),
                    ("actual_outcome", "TEXT"),
                    ("actual_pnl", "REAL"),
                    ("outcome_date", "DATE"),
                    ("prediction_time", "TIMESTAMPTZ DEFAULT NOW()"),
                    # New columns for feedback loop enhancements
                    ("position_id", "VARCHAR(100)"),
                    ("strategy_recommendation", "VARCHAR(20)"),
                    ("direction_predicted", "VARCHAR(10)"),
                    ("direction_correct", "BOOLEAN"),
                ]
                for col_name, col_type in migration_columns:
                    try:
                        cursor.execute(f"ALTER TABLE prophet_predictions ADD COLUMN IF NOT EXISTS {col_name} {col_type}")
                    except Exception as e:
                        # Column already exists or other migration error - log but continue
                        logger.debug(f"Migration column {col_name}: {e}")

                conn.commit()

                # Serialize top_factors as JSON (convert numpy types)
                top_factors_json = json.dumps([
                    {"feature": f[0], "importance": _convert_numpy(f[1])}
                    for f in (prediction.top_factors or [])
                ]) if prediction.top_factors else None

                # Serialize probabilities as JSON (convert numpy types)
                probabilities_json = json.dumps(_convert_dict_numpy(prediction.probabilities)) if prediction.probabilities else None

                # Serialize Claude analysis as JSON (full transparency)
                claude_json = None
                if prediction.claude_analysis:
                    ca = prediction.claude_analysis
                    claude_json = json.dumps(_convert_dict_numpy({
                        "analysis": ca.analysis,
                        "confidence_adjustment": ca.confidence_adjustment,
                        "risk_factors": ca.risk_factors,
                        "opportunities": ca.opportunities,
                        "recommendation": ca.recommendation,
                        "override_advice": ca.override_advice,
                        "tokens_used": ca.tokens_used,
                        "input_tokens": ca.input_tokens,
                        "output_tokens": ca.output_tokens,
                        "response_time_ms": ca.response_time_ms,
                        "model_used": ca.model_used,
                        # Store raw prompt/response for full transparency
                        "raw_prompt": ca.raw_prompt[:2000] if ca.raw_prompt else None,
                        "raw_response": ca.raw_response[:5000] if ca.raw_response else None,
                    }))

                # Issue #3 fix: Use RETURNING to get prediction_id for outcome linking
                # Option C: Include position_id for 1:1 prediction-to-position linking
                cursor.execute("""
                    INSERT INTO prophet_predictions (
                        trade_date, bot_name, spot_price, vix, gex_net, gex_normalized, gex_regime,
                        gex_flip_point, gex_call_wall, gex_put_wall, day_of_week,
                        advice, win_probability, confidence, suggested_risk_pct,
                        suggested_sd_multiplier, model_version,
                        use_gex_walls, suggested_put_strike, suggested_call_strike,
                        reasoning, top_factors, probabilities, claude_analysis,
                        position_id, strategy_recommendation
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (trade_date, bot_name)
                    WHERE position_id IS NULL
                    DO UPDATE SET
                        advice = EXCLUDED.advice,
                        win_probability = EXCLUDED.win_probability,
                        confidence = EXCLUDED.confidence,
                        reasoning = EXCLUDED.reasoning,
                        top_factors = EXCLUDED.top_factors,
                        probabilities = EXCLUDED.probabilities,
                        claude_analysis = EXCLUDED.claude_analysis,
                        timestamp = NOW()
                    RETURNING id
                """, (
                    trade_date,
                    prediction.bot_name.value,
                    _convert_numpy(context.spot_price),
                    _convert_numpy(context.vix),
                    _convert_numpy(context.gex_net),
                    _convert_numpy(context.gex_normalized),
                    context.gex_regime.value,
                    _convert_numpy(context.gex_flip_point),
                    _convert_numpy(context.gex_call_wall),
                    _convert_numpy(context.gex_put_wall),
                    _convert_numpy(context.day_of_week),
                    prediction.advice.value,
                    _convert_numpy(prediction.win_probability),
                    _convert_numpy(prediction.confidence),
                    _convert_numpy(prediction.suggested_risk_pct),
                    _convert_numpy(prediction.suggested_sd_multiplier),
                    prediction.model_version,
                    prediction.use_gex_walls,
                    _convert_numpy(prediction.suggested_put_strike),
                    _convert_numpy(prediction.suggested_call_strike),
                    prediction.reasoning,
                    top_factors_json,
                    probabilities_json,
                    claude_json,
                    position_id,
                    strategy_recommendation
                ))

                # Issue #3 fix: Fetch the returned prediction_id for linking
                row = cursor.fetchone()
                prediction_id = row[0] if row else None

                conn.commit()
                logger.info(f"Stored Prophet prediction for {prediction.bot_name.value} (id={prediction_id})")

                # Update prediction object with the stored ID
                if prediction_id:
                    prediction.prediction_id = prediction_id

                # === COMPREHENSIVE BOT LOGGER ===
                if BOT_LOGGER_AVAILABLE and log_bot_decision:
                    try:
                        comprehensive = BotDecision(
                            bot_name="PROPHET",
                            decision_type="ANALYSIS",
                            action=prediction.advice.value,
                            symbol="SPY",
                            strategy="oracle_ml_prediction",
                            session_id=generate_session_id(),
                            market_context=BotLogMarketContext(
                                spot_price=context.spot_price,
                                vix=context.vix,
                                net_gex=context.gex_net,
                                gex_regime=context.gex_regime.value if hasattr(context.gex_regime, 'value') else str(context.gex_regime),
                                flip_point=context.gex_flip_point,
                                call_wall=context.gex_call_wall,
                                put_wall=context.gex_put_wall,
                            ),
                            claude_context=ClaudeContext(
                                response=prediction.reasoning or "",
                                confidence=f"{prediction.win_probability:.1%}",
                            ),
                            entry_reasoning=f"Prophet {prediction.advice.value}: Win prob {prediction.win_probability:.1%}, Risk {prediction.suggested_risk_pct:.1%}",
                            backtest_win_rate=prediction.win_probability * 100,
                            kelly_pct=prediction.suggested_risk_pct,
                            passed_all_checks=prediction.advice.value != "SKIP_TODAY",
                            blocked_reason="" if prediction.advice.value != "SKIP_TODAY" else prediction.reasoning or "Low win probability",
                        )
                        comp_id = log_bot_decision(comprehensive)
                        logger.info(f"Prophet logged to bot_decision_logs: {comp_id}")
                    except Exception as comp_e:
                        logger.warning(f"Could not log Prophet to comprehensive table: {comp_e}")

                # Issue #3 fix: Return prediction_id for linking, or True for backward compatibility
                return prediction_id if prediction_id else True

            except Exception as e:
                logger.error(f"Failed to store prediction: {e}")
                return False

    def update_outcome(
        self,
        trade_date: str,
        bot_name: BotName,
        outcome: TradeOutcome,
        actual_pnl: float,
        spot_at_exit: float = None,
        put_strike: float = None,
        call_strike: float = None,
        prediction_id: int = None,  # Issue #3: Optional direct linking by ID
        # New feedback loop parameters (Migration 023)
        outcome_type: str = None,  # MAX_PROFIT, PUT_BREACHED, CALL_BREACHED, WIN, LOSS, etc.
        direction_predicted: str = None,  # BULLISH or BEARISH (for directional bots)
        direction_correct: bool = None  # Was the direction prediction correct?
    ) -> bool:
        """
        Update prediction with actual outcome and store training data for ML feedback loop.

        Issue #3 fix: Supports both (trade_date, bot_name) linking and direct prediction_id linking.
        The prediction_id provides a more robust link when available.

        Feedback Loop Enhancement (Migration 023):
        - outcome_type: Specific outcome classification (MAX_PROFIT, PUT_BREACHED, etc.)
        - direction_predicted: For directional bots (SOLOMON, GIDEON) - BULLISH or BEARISH
        - direction_correct: Whether the directional prediction was correct

        This data flows to Proverbs for strategy-level analysis.
        """
        if not DB_AVAILABLE:
            return False

        try:
            conn = get_connection()
            cursor = conn.cursor()

            # Issue #3: Support both linking methods
            # If prediction_id is provided, use it for direct linking (more robust)
            # Otherwise, fall back to (trade_date, bot_name) composite key
            if prediction_id:
                # Direct linking by prediction_id - includes direction tracking (Migration 023)
                cursor.execute("""
                    UPDATE prophet_predictions
                    SET prediction_used = TRUE,
                        actual_outcome = %s,
                        actual_pnl = %s,
                        outcome_date = CURRENT_DATE,
                        direction_predicted = COALESCE(%s, direction_predicted),
                        direction_correct = %s
                    WHERE id = %s
                """, (outcome.value, actual_pnl, direction_predicted, direction_correct, prediction_id))
                logger.info(f"Updated outcome for prediction_id={prediction_id}, direction_correct={direction_correct}")
            else:
                # Fall back to composite key linking - includes direction tracking (Migration 023)
                cursor.execute("""
                    UPDATE prophet_predictions
                    SET prediction_used = TRUE,
                        actual_outcome = %s,
                        actual_pnl = %s,
                        outcome_date = CURRENT_DATE,
                        direction_predicted = COALESCE(%s, direction_predicted),
                        direction_correct = %s
                    WHERE trade_date = %s AND bot_name = %s
                """, (outcome.value, actual_pnl, direction_predicted, direction_correct, trade_date, bot_name.value))

            # Also store in prophet_training_outcomes for ML feedback loop
            # First, get the original prediction features
            if prediction_id:
                cursor.execute("""
                    SELECT spot_price, vix, gex_net, gex_normalized, gex_regime,
                           gex_flip_point, gex_call_wall, gex_put_wall, day_of_week,
                           win_probability, suggested_put_strike, suggested_call_strike,
                           model_version
                    FROM prophet_predictions
                    WHERE id = %s
                """, (prediction_id,))
            else:
                cursor.execute("""
                    SELECT spot_price, vix, gex_net, gex_normalized, gex_regime,
                           gex_flip_point, gex_call_wall, gex_put_wall, day_of_week,
                           win_probability, suggested_put_strike, suggested_call_strike,
                           model_version
                    FROM prophet_predictions
                    WHERE trade_date = %s AND bot_name = %s
                """, (trade_date, bot_name.value))

            row = cursor.fetchone()
            if row:
                spot_at_entry, vix, gex_net, gex_norm, gex_regime, flip, call_wall, put_wall, dow, \
                    win_prob, pred_put, pred_call, model_ver = row

                is_win = outcome.value in ['MAX_PROFIT', 'WIN', 'PARTIAL_WIN']

                # Build features JSON for training
                features_json = json.dumps({
                    'vix': vix,
                    'gex_net': gex_net,
                    'gex_normalized': gex_norm,
                    'gex_regime': gex_regime,
                    'gex_flip_point': flip,
                    'gex_call_wall': call_wall,
                    'gex_put_wall': put_wall,
                    'day_of_week': dow,
                    'predicted_win_probability': win_prob,
                })

                # Create training outcomes table if needed (Migration 023: added direction tracking)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS prophet_training_outcomes (
                        id SERIAL PRIMARY KEY,
                        trade_date DATE NOT NULL,
                        bot_name TEXT NOT NULL,
                        features JSONB NOT NULL,
                        outcome TEXT NOT NULL,
                        is_win BOOLEAN NOT NULL,
                        net_pnl REAL,
                        put_strike REAL,
                        call_strike REAL,
                        spot_at_entry REAL,
                        spot_at_exit REAL,
                        created_at TIMESTAMPTZ DEFAULT NOW(),
                        -- Migration 023: Feedback loop enhancements
                        strategy_type VARCHAR(20),       -- IRON_CONDOR or DIRECTIONAL
                        outcome_type VARCHAR(30),        -- MAX_PROFIT, PUT_BREACHED, etc.
                        direction_predicted VARCHAR(10), -- BULLISH or BEARISH
                        direction_correct BOOLEAN,       -- Was direction prediction correct?
                        prediction_id INTEGER,           -- Link to prophet_predictions
                        UNIQUE(trade_date, bot_name)
                    )
                """)

                # Determine strategy type from bot name
                strategy_type = 'DIRECTIONAL' if bot_name.value in ['SOLOMON', 'GIDEON'] else 'IRON_CONDOR'

                # Store training outcome for ML retraining (Migration 023: added direction tracking)
                cursor.execute("""
                    INSERT INTO prophet_training_outcomes (
                        trade_date, bot_name, features, outcome, is_win, net_pnl,
                        put_strike, call_strike, spot_at_entry, spot_at_exit,
                        strategy_type, outcome_type, direction_predicted, direction_correct, prediction_id
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (trade_date, bot_name) DO UPDATE SET
                        outcome = EXCLUDED.outcome,
                        is_win = EXCLUDED.is_win,
                        net_pnl = EXCLUDED.net_pnl,
                        spot_at_exit = EXCLUDED.spot_at_exit,
                        outcome_type = EXCLUDED.outcome_type,
                        direction_predicted = EXCLUDED.direction_predicted,
                        direction_correct = EXCLUDED.direction_correct,
                        prediction_id = EXCLUDED.prediction_id
                """, (
                    trade_date,
                    bot_name.value,
                    features_json,
                    outcome.value,
                    is_win,
                    actual_pnl,
                    put_strike or pred_put,
                    call_strike or pred_call,
                    spot_at_entry,
                    spot_at_exit,
                    strategy_type,
                    outcome_type or outcome.value,  # Use outcome_type if provided, else use outcome
                    direction_predicted,
                    direction_correct,
                    prediction_id
                ))

                # Log to live log (Migration 023: includes direction tracking)
                log_data = {
                    "bot": bot_name.value,
                    "outcome": outcome.value,
                    "pnl": actual_pnl,
                    "is_win": is_win,
                    "strategy_type": strategy_type
                }
                if direction_predicted:
                    log_data["direction_predicted"] = direction_predicted
                    log_data["direction_correct"] = direction_correct
                self.live_log.log("OUTCOME", f"{bot_name.value}: {outcome.value} (${actual_pnl:+.2f})", log_data)

            conn.commit()
            conn.close()
            logger.info(f"Updated outcome for {bot_name.value}: {outcome.value} - training data stored")
            return True

        except Exception as e:
            logger.error(f"Failed to update outcome: {e}")
            return False


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

_prophet: Optional[ProphetAdvisor] = None
_prophet_lock = threading.Lock()


def get_prophet() -> ProphetAdvisor:
    """Get or create Prophet singleton (thread-safe)"""
    global _prophet
    if _prophet is None:
        with _prophet_lock:
            # Double-check locking pattern
            if _prophet is None:
                _prophet = ProphetAdvisor()
    return _prophet


def get_fortress_advice(
    vix: float,
    day_of_week: int = None,
    gex_regime: str = "NEUTRAL",
    gex_call_wall: float = 0,
    gex_put_wall: float = 0,
    use_gex_walls: bool = False,
    **kwargs
) -> ProphetPrediction:
    """Quick helper to get FORTRESS advice"""
    if day_of_week is None:
        day_of_week = datetime.now().weekday()

    # Safe enum access with fallback to NEUTRAL
    if isinstance(gex_regime, str):
        try:
            regime = GEXRegime[gex_regime]
        except (KeyError, TypeError):
            regime = GEXRegime.NEUTRAL
    else:
        regime = gex_regime if isinstance(gex_regime, GEXRegime) else GEXRegime.NEUTRAL

    context = MarketContext(
        spot_price=kwargs.get('price', 5000),
        vix=vix,
        day_of_week=day_of_week,
        gex_regime=regime,
        gex_call_wall=gex_call_wall,
        gex_put_wall=gex_put_wall,
        **{k: v for k, v in kwargs.items() if k != 'price'}
    )

    prophet = get_prophet()
    return prophet.get_fortress_advice(context, use_gex_walls=use_gex_walls)


# Backward compatibility aliases
FortressMLAdvisor = ProphetAdvisor
get_advisor = get_prophet
get_trading_advice = get_fortress_advice


def train_from_backtest(backtest_results: Dict[str, Any]) -> TrainingMetrics:
    """Train Prophet from backtest results"""
    prophet = get_prophet()
    return prophet.train_from_chronicles(backtest_results)


def explain_prophet_advice(
    prediction: ProphetPrediction,
    context: MarketContext
) -> str:
    """Get Claude AI explanation of Prophet prediction"""
    prophet = get_prophet()
    return prophet.explain_prediction(prediction, context)


def analyze_chronicles_patterns(backtest_results: Dict[str, Any]) -> Dict[str, Any]:
    """Use Claude to analyze patterns in CHRONICLES backtest results"""
    prophet = get_prophet()
    return prophet.analyze_patterns(backtest_results)


# =============================================================================
# AUTO-TRAINING SYSTEM
# =============================================================================

def get_pending_outcomes_count() -> int:
    """Get count of outcomes available for training"""
    if not DB_AVAILABLE:
        return 0

    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Count all outcomes (simplified - used_in_model_version column may not exist)
        try:
            cursor.execute("SELECT COUNT(*) FROM prophet_training_outcomes")
            count = cursor.fetchone()[0]
        except Exception as e:
            # Table might not exist yet
            logger.debug(f"prophet_training_outcomes table query failed: {e}")
            count = 0

        conn.close()
        return count
    except Exception as e:
        logger.warning(f"Failed to get pending outcomes count: {e}")
        return 0


def get_training_status() -> Dict[str, Any]:
    """Get comprehensive training status for API"""
    prophet = get_prophet()
    pending_count = get_pending_outcomes_count()

    # Get last training date from database
    last_trained = None
    total_outcomes = 0
    model_source = "none"
    db_model_exists = False

    if DB_AVAILABLE:
        conn = None
        try:
            conn = get_connection()
            cursor = conn.cursor()

            # Get total outcomes (table might not exist)
            try:
                cursor.execute("SELECT COUNT(*) FROM prophet_training_outcomes")
                total_outcomes = cursor.fetchone()[0]
            except Exception as e:
                logger.debug(f"Failed to get total outcomes: {e}")
                conn.rollback()  # Reset transaction state
                total_outcomes = 0

            # Try to get last training date from model save time
            try:
                cursor.execute("""
                    SELECT MAX(created_at) FROM prophet_trained_models
                    WHERE is_active = TRUE
                """)
                row = cursor.fetchone()
                if row and row[0]:
                    last_trained = row[0].isoformat()
            except Exception as e:
                logger.debug(f"Failed to get last training date: {e}")
                conn.rollback()  # Reset transaction state

            # Check if model exists in database
            try:
                cursor.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables
                        WHERE table_name = 'prophet_trained_models'
                    )
                """)
                if cursor.fetchone()[0]:
                    cursor.execute("""
                        SELECT model_version, created_at FROM prophet_trained_models
                        WHERE is_active = TRUE
                        ORDER BY created_at DESC LIMIT 1
                    """)
                    db_row = cursor.fetchone()
                    if db_row:
                        db_model_exists = True
                        model_source = "database"
                        if not last_trained:
                            last_trained = db_row[1].isoformat() if db_row[1] else None
            except Exception as e:
                logger.debug(f"Failed to check model in database: {e}")
                conn.rollback()

        except Exception as e:
            logger.warning(f"Failed to get training status: {e}")
        finally:
            if conn:
                try:
                    conn.close()
                except Exception as e:
                    logger.debug(f"Failed to close connection: {e}")

    # Determine model source
    if prophet.is_trained and not db_model_exists:
        model_source = "local_file"
    elif not prophet.is_trained:
        model_source = "none"

    return {
        "model_trained": prophet.is_trained,
        "model_version": prophet.model_version,
        "pending_outcomes": pending_count,
        "total_outcomes": total_outcomes,
        "last_trained": last_trained,
        "threshold_for_retrain": 100,
        "needs_training": pending_count >= 100 or not prophet.is_trained,
        "training_metrics": prophet.training_metrics.__dict__ if prophet.training_metrics else None,
        "claude_available": prophet.claude_available,
        "model_source": model_source,
        "db_persistence": db_model_exists,
        "persistence_status": "Model saved in database - survives restarts" if db_model_exists else "Model NOT in database - will be lost on restart"
    }


def train_from_live_outcomes(min_samples: int = 100) -> Optional[TrainingMetrics]:
    """
    Train Prophet model from live trading outcomes stored in database.

    V2: Uses sample_weight for class imbalance, Brier on CV folds,
    V3 features (cyclical day, VRP), adaptive thresholds.
    """
    if not DB_AVAILABLE:
        logger.error("Database not available for training")
        return None

    prophet = get_prophet()
    prophet.live_log.log("TRAIN_START", "V2 auto-training from live outcomes", {"min_samples": min_samples})

    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Get all outcomes from database
        cursor.execute("""
            SELECT trade_date, bot_name, features, outcome, is_win, net_pnl
            FROM prophet_training_outcomes
            ORDER BY trade_date
        """)
        rows = cursor.fetchall()
        conn.close()

        if len(rows) < min_samples:
            prophet.live_log.log("TRAIN_SKIP", f"Insufficient live data: {len(rows)} < {min_samples}", {})
            logger.info(f"Insufficient live outcomes for training: {len(rows)} < {min_samples}")
            return None

        # Convert to training format with V3 features
        records = []
        price_changes = []
        for row in rows:
            trade_date, bot_name, features_json, outcome, is_win, net_pnl = row

            if isinstance(features_json, str):
                features = json.loads(features_json)
            else:
                features = features_json or {}

            day_of_week = features.get('day_of_week', 2)
            day_sin = math.sin(2 * math.pi * day_of_week / 5)
            day_cos = math.cos(2 * math.pi * day_of_week / 5)

            price_change_1d = features.get('price_change_1d', 0)
            expected_move_pct = features.get('expected_move_pct', 1.0)
            price_changes.append(abs(price_change_1d))

            # VRP calculation
            if len(price_changes) >= 5:
                recent = price_changes[-5:]
                realized_vol = (sum(c**2 for c in recent) / len(recent)) ** 0.5
            else:
                realized_vol = expected_move_pct * 0.8
            vrp = expected_move_pct - realized_vol

            # Rolling win rate (60-trade horizon)
            recent_wins = [r.get('is_win', 0) for r in records[-60:]] if records else []
            win_rate_60d = sum(recent_wins) / len(recent_wins) if recent_wins else 0.68

            record = {
                'trade_date': trade_date,
                'is_win': 1 if is_win else 0,
                'vix': features.get('vix', 20),
                'day_of_week': day_of_week,
                'day_of_week_sin': day_sin,
                'day_of_week_cos': day_cos,
                'price_change_1d': price_change_1d,
                'expected_move_pct': expected_move_pct,
                'volatility_risk_premium': vrp,
                'win_rate_60d': win_rate_60d,
                'vix_change_1d': features.get('vix_change_1d', 0),
                'gex_normalized': features.get('gex_normalized', 0),
                'gex_regime_positive': 1 if features.get('gex_regime') == 'POSITIVE' else 0,
                'gex_distance_to_flip_pct': features.get('gex_distance_to_flip_pct', 0),
                'gex_between_walls': 1 if features.get('gex_between_walls') else 0,
            }
            records.append(record)

        df = pd.DataFrame(records)

        # Calculate rolling metrics
        if len(df) > 1:
            df['vix_percentile_30d'] = df['vix'].rolling(30, min_periods=1).apply(
                lambda x: (x.rank().iloc[-1] / len(x)) * 100 if len(x) > 0 else 50
            ).fillna(50)
        else:
            df['vix_percentile_30d'] = 50

        # Check if we have GEX features
        has_gex = df['gex_normalized'].abs().sum() > 0
        prophet._has_gex_features = has_gex

        feature_cols = prophet.FEATURE_COLS if has_gex else prophet.FEATURE_COLS_V1

        # Ensure all required columns exist
        for col in feature_cols:
            if col not in df.columns:
                df[col] = 0

        X = df[feature_cols].values
        y = df['is_win'].values.astype(int)

        # Class imbalance: compute sample_weight
        n_wins = int(y.sum())
        n_losses = int(len(y) - n_wins)
        if n_wins > 0 and n_losses > 0:
            weight_win = n_losses / len(y)
            weight_loss = n_wins / len(y)
            sample_weight_array = np.where(y == 1, weight_win, weight_loss)
        else:
            sample_weight_array = np.ones(len(y))

        # Store base rate for adaptive thresholds
        prophet._base_rate = float(y.mean())

        # Train model
        prophet.scaler = StandardScaler()
        X_scaled = prophet.scaler.fit_transform(X)

        tscv = TimeSeriesSplit(n_splits=5)

        prophet.model = GradientBoostingClassifier(
            n_estimators=150,
            max_depth=4,
            learning_rate=0.1,
            min_samples_split=20,
            min_samples_leaf=10,
            subsample=0.8,
            random_state=42
        )

        accuracies, precisions, recalls, f1s, aucs, briers = [], [], [], [], [], []

        for train_idx, test_idx in tscv.split(X_scaled):
            X_train, X_test = X_scaled[train_idx], X_scaled[test_idx]
            y_train, y_test = y[train_idx], y[test_idx]
            sw_train = sample_weight_array[train_idx]

            prophet.model.fit(X_train, y_train, sample_weight=sw_train)
            y_pred = prophet.model.predict(X_test)
            y_proba = prophet.model.predict_proba(X_test)[:, 1]

            accuracies.append(accuracy_score(y_test, y_pred))
            precisions.append(precision_score(y_test, y_pred, zero_division=0))
            recalls.append(recall_score(y_test, y_pred, zero_division=0))
            f1s.append(f1_score(y_test, y_pred, zero_division=0))
            briers.append(brier_score_loss(y_test, y_proba))
            try:
                aucs.append(roc_auc_score(y_test, y_proba))
            except ValueError:
                aucs.append(0.5)

        # Final fit on all data with sample weights
        prophet.model.fit(X_scaled, y, sample_weight=sample_weight_array)

        # Calibrate probabilities
        prophet.calibrated_model = CalibratedClassifierCV(prophet.model, method='isotonic', cv=3)
        prophet.calibrated_model.fit(X_scaled, y)

        feature_importances = dict(zip(feature_cols, prophet.model.feature_importances_))
        brier_cv = np.mean(briers) if briers else 0.25

        # Increment version for live training
        version_parts = prophet.model_version.split('.') if prophet.model_version else ['2', '0', '0']
        new_minor = int(version_parts[1]) + 1 if len(version_parts) > 1 else 1
        new_version = f"{version_parts[0]}.{new_minor}.0"

        prophet.training_metrics = TrainingMetrics(
            accuracy=np.mean(accuracies),
            precision=np.mean(precisions),
            recall=np.mean(recalls),
            f1_score=np.mean(f1s),
            auc_roc=np.mean(aucs),
            brier_score=brier_cv,
            win_rate_predicted=float(prophet.calibrated_model.predict_proba(X_scaled)[:, 1].mean()),
            win_rate_actual=y.mean(),
            total_samples=len(df),
            train_samples=int(len(df) * 0.8),
            test_samples=int(len(df) * 0.2),
            positive_samples=n_wins,
            negative_samples=n_losses,
            feature_importances=feature_importances,
            training_date=datetime.now().isoformat(),
            model_version=new_version
        )

        prophet.is_trained = True
        prophet.model_version = new_version
        prophet._feature_version = 3
        prophet._trained_feature_cols = feature_cols
        prophet._save_model()

        # Set adaptive thresholds
        prophet._update_thresholds_from_base_rate()

        prophet.live_log.log("TRAIN_DONE", f"V2 auto-trained v{new_version} - Accuracy: {prophet.training_metrics.accuracy:.1%}", {
            "accuracy": prophet.training_metrics.accuracy,
            "auc_roc": prophet.training_metrics.auc_roc,
            "brier_cv": brier_cv,
            "total_samples": prophet.training_metrics.total_samples,
            "model_version": new_version,
            "class_balance": f"{n_wins}W/{n_losses}L"
        })

        logger.info(f"Prophet V2 auto-trained from {len(df)} live outcomes - v{new_version}")
        return prophet.training_metrics

    except Exception as e:
        prophet.live_log.log("TRAIN_ERROR", f"Auto-training failed: {e}", {})
        logger.error(f"Failed to train from live outcomes: {e}")
        import traceback
        traceback.print_exc()
        return None


def auto_train(
    threshold_outcomes: int = 20,  # Reduced from 100 for more frequent learning
    force: bool = False
) -> Dict[str, Any]:
    """
    Automatic Prophet training trigger.

    Called by scheduler on:
    1. Daily schedule (midnight CT)
    2. When threshold outcomes is reached (20+ new outcomes)
    3. After any bot completes a trade (via outcome recording)

    Training Frequency:
    - Original: Weekly + 100 outcome threshold
    - Updated: Daily + 20 outcome threshold (faster learning)

    Training strategy:
    1. If CHRONICLES backtest data available and no live outcomes -> Train from CHRONICLES
    2. If live outcomes available -> Train from live data (more accurate)
    3. If both available -> Train from live, use CHRONICLES as fallback

    Args:
        threshold_outcomes: Minimum new outcomes before retraining (default: 20)
        force: Force training even if threshold not met

    Returns:
        Dict with training status and results
    """
    prophet = get_prophet()
    prophet.live_log.log("AUTO_TRAIN_CHECK", "Checking if training needed", {
        "threshold": threshold_outcomes,
        "force": force
    })

    pending_count = get_pending_outcomes_count()

    result = {
        "triggered": False,
        "reason": "",
        "pending_outcomes": pending_count,
        "threshold": threshold_outcomes,
        "model_was_trained": prophet.is_trained,
        "training_metrics": None,
        "success": False
    }

    # Decide if training is needed
    needs_training = False
    reason = ""

    if force:
        needs_training = True
        reason = "Forced training requested"
    elif not prophet.is_trained:
        needs_training = True
        reason = "Model not trained - initial training"
    elif pending_count >= threshold_outcomes:
        needs_training = True
        reason = f"Threshold reached: {pending_count} >= {threshold_outcomes} new outcomes"

    if not needs_training:
        result["reason"] = f"No training needed - only {pending_count}/{threshold_outcomes} new outcomes"
        prophet.live_log.log("AUTO_TRAIN_SKIP", result["reason"], result)
        return result

    result["triggered"] = True
    result["reason"] = reason

    prophet.live_log.log("AUTO_TRAIN_START", reason, {"pending_outcomes": pending_count})

    # Try training from live outcomes first (more accurate)
    # Reduced threshold from 50 to 20 for faster learning from live data
    if pending_count >= 20:  # Need at least 20 for live training
        metrics = train_from_live_outcomes(min_samples=20)
        if metrics:
            result["training_metrics"] = metrics.__dict__
            result["success"] = True
            result["method"] = "live_outcomes"
            prophet.live_log.log("AUTO_TRAIN_SUCCESS", f"Trained from live outcomes - v{metrics.model_version}", result)
            return result

    # Try training from database backtest results
    metrics = train_from_database_backtests()
    if metrics:
        result["training_metrics"] = metrics.__dict__
        result["success"] = True
        result["method"] = "database_backtests"
        prophet.live_log.log("AUTO_TRAIN_SUCCESS", f"Trained from DB backtests - v{metrics.model_version}", result)
        return result

    # Fallback to CHRONICLES backtest data
    try:
        from backtest.autonomous_backtest_engine import get_backtester

        backtester = get_backtester()
        backtest_results = backtester.get_latest_results()

        if backtest_results and backtest_results.get('trades'):
            metrics = prophet.train_from_chronicles(backtest_results)
            result["training_metrics"] = metrics.__dict__
            result["success"] = True
            result["method"] = "chronicles_backtest"
            prophet.live_log.log("AUTO_TRAIN_SUCCESS", f"Trained from CHRONICLES - v{metrics.model_version}", result)
            return result
    except Exception as e:
        logger.warning(f"Could not train from CHRONICLES: {e}")

    result["reason"] = "Insufficient data for training"
    prophet.live_log.log("AUTO_TRAIN_FAIL", result["reason"], result)
    return result


def train_from_database_backtests(min_samples: int = 100) -> Optional[TrainingMetrics]:
    """
    Train Prophet from backtest results stored in database.

    This pulls data from zero_dte_backtest_trades table directly.
    More robust than CHRONICLES in-memory data as it persists across restarts.
    """
    if not DB_AVAILABLE:
        logger.warning("Database not available for training")
        return None

    prophet = get_prophet()
    prophet.live_log.log("TRAIN_DB_START", "Training from database backtest results", {})

    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        rows = []

        # Try to query from zero_dte_backtest_trades table
        try:
            cursor.execute("""
                SELECT
                    trade_date,
                    underlying_price_entry,
                    vix_entry,
                    iv_used,
                    outcome,
                    net_pnl,
                    return_pct,
                    gex_net,
                    gex_regime,
                    put_short_strike,
                    call_short_strike
                FROM zero_dte_backtest_trades
                WHERE outcome IS NOT NULL
                ORDER BY trade_date DESC
                LIMIT 1000
            """)
            rows = cursor.fetchall()
        except Exception as e:
            logger.warning(f"Could not query zero_dte_backtest_trades: {e}")
            # Rollback the failed transaction
            conn.rollback()

        # V3 FIX: Close connection in finally block (was leaking on exception in train_from_chronicles)
        conn.close()
        conn = None  # Mark as closed so finally doesn't double-close

        if not rows or len(rows) < min_samples:
            prophet.live_log.log("TRAIN_DB_SKIP", f"Insufficient trades: {len(rows) if rows else 0} < {min_samples}", {})
            logger.info(f"Insufficient trades from database: {len(rows) if rows else 0} < {min_samples}")
            return None

        # Convert to trade dictionaries for train_from_chronicles
        all_trades = []
        for row in rows:
            trade_date, spy_price, vix, iv, outcome, pnl, ret_pct, gex_net, gex_regime, put_strike, call_strike = row

            # Map outcome to win/loss
            is_win = outcome in ('MAX_PROFIT', 'PARTIAL_PROFIT')

            # Format trade to match extract_features_from_chronicles expectations
            trade = {
                'trade_date': str(trade_date) if trade_date else '',
                'open_price': float(spy_price) if spy_price else 590.0,
                'close_price': float(spy_price) if spy_price else 590.0,  # Approximate
                'vix': float(vix) if vix else 15.0,
                'expected_move_1d': float(spy_price) * 0.01 if spy_price else 5.0,  # ~1% move
                'outcome': outcome or 'MAX_PROFIT',
                'net_pnl': float(pnl) if pnl else 0,
                # GEX fields
                'gex_normalized': float(gex_net) / 1e9 if gex_net else 0,  # Normalize to billions
                'gex_regime': gex_regime or 'NEUTRAL',
                'gex_distance_to_flip_pct': 0,  # Not available
                'gex_between_walls': True,  # Default
            }
            all_trades.append(trade)

        prophet.live_log.log("TRAIN_DB_DATA", f"Loaded {len(all_trades)} trades from database", {})

        # Format as CHRONICLES backtest results
        backtest_results = {'all_trades': all_trades}
        metrics = prophet.train_from_chronicles(backtest_results, min_samples=min_samples)

        prophet.live_log.log("TRAIN_DB_DONE", f"Trained from {len(all_trades)} database trades", {
            "accuracy": metrics.accuracy,
            "total_samples": metrics.total_samples
        })

        return metrics

    except Exception as e:
        prophet.live_log.log("TRAIN_DB_ERROR", f"Database training failed: {e}", {})
        logger.error(f"Failed to train from database: {e}")
        import traceback
        traceback.print_exc()
        return None
    finally:
        # V3 FIX: Ensure connection is always closed
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


if __name__ == "__main__":
    print("=" * 60)
    print("PROPHET - Multi-Strategy ML Advisor with Claude AI")
    print("=" * 60)

    prophet = get_prophet()
    print(f"Model loaded: {prophet.is_trained}")
    print(f"Version: {prophet.model_version}")
    print(f"Claude AI: {'ENABLED' if prophet.claude_available else 'DISABLED'}")

    # Demo predictions
    print("\n--- FORTRESS Advice Demo ---")
    context = MarketContext(
        spot_price=5900,
        vix=20,
        day_of_week=2,
        gex_regime=GEXRegime.POSITIVE,
        gex_call_wall=5950,
        gex_put_wall=5850,
        gex_between_walls=True
    )

    # Get advice with Claude validation
    advice = prophet.get_fortress_advice(context, use_gex_walls=True, use_claude_validation=True)
    print(f"Advice: {advice.advice.value}")
    print(f"Win Prob: {advice.win_probability:.1%}")
    print(f"Risk %: {advice.suggested_risk_pct:.1f}%")
    print(f"Reasoning: {advice.reasoning}")

    if advice.suggested_put_strike:
        print(f"GEX Put Strike: {advice.suggested_put_strike}")
        print(f"GEX Call Strike: {advice.suggested_call_strike}")

    # Demo Claude explanation
    if prophet.claude_available:
        print("\n--- Claude AI Explanation ---")
        explanation = prophet.explain_prediction(advice, context)
        print(explanation)

        print("\n--- Claude AI Market Analysis ---")
        analysis = prophet.get_claude_analysis(context)
        if analysis:
            print(f"Recommendation: {analysis.recommendation}")
            print(f"Confidence Adjustment: {analysis.confidence_adjustment:+.2f}")
            if analysis.risk_factors:
                print(f"Risk Factors: {', '.join(analysis.risk_factors)}")
            if analysis.opportunities:
                print(f"Opportunities: {', '.join(analysis.opportunities)}")
