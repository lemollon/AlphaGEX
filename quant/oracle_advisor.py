"""
ORACLE - Multi-Strategy ML Advisor for AlphaGEX Trading Bots
=============================================================

Named after the Greek deity of prophecy and wisdom.

PURPOSE:
Oracle is the central advisory system that aggregates multiple signals
(GEX, ML predictions, VIX regime, market conditions) and provides
curated recommendations to each trading bot:

    - ARES: Iron Condor advice (strikes, risk %, skip signals)
    - ATLAS: Wheel strategy advice (CSP entry, assignment handling)
    - PHOENIX: Directional call advice (entry timing, position sizing)

ARCHITECTURE:
    ┌─────────────────────────────────────────────────────────┐
    │                      ORACLE                              │
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
      │  ARES   │       │  ATLAS  │       │ PHOENIX │
      │   IC    │       │  Wheel  │       │  Calls  │
      └─────────┘       └─────────┘       └─────────┘

FEEDBACK LOOP:
    KRONOS Backtests --> Extract Features --> Train Model
            ^                                      |
            |                                      v
    Store Outcome <-- Bot Live Trade <-- Query Oracle

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
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any, TYPE_CHECKING
from dataclasses import dataclass, asdict, field
from enum import Enum
import warnings

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
    """Trading bots that Oracle advises"""
    ARES = "ARES"          # Aggressive Iron Condor (SPY 0DTE)
    ATLAS = "ATLAS"        # SPX Wheel Strategy
    PHOENIX = "PHOENIX"    # Directional Calls
    HERMES = "HERMES"      # Manual Wheel via UI
    ATHENA = "ATHENA"      # Directional Spreads (Bull Call / Bear Call)
    PEGASUS = "PEGASUS"    # SPX Iron Condor ($10 spreads, weekly)


class TradeOutcome(Enum):
    """Possible trade outcomes"""
    MAX_PROFIT = "MAX_PROFIT"
    PUT_BREACHED = "PUT_BREACHED"
    CALL_BREACHED = "CALL_BREACHED"
    DOUBLE_BREACH = "DOUBLE_BREACH"
    PARTIAL_PROFIT = "PARTIAL_PROFIT"
    LOSS = "LOSS"


class TradingAdvice(Enum):
    """Oracle advice levels"""
    TRADE_FULL = "TRADE_FULL"           # High confidence, full size
    TRADE_REDUCED = "TRADE_REDUCED"     # Medium confidence, reduce size
    SKIP_TODAY = "SKIP_TODAY"           # Low confidence, don't trade


class GEXRegime(Enum):
    """GEX market regime"""
    POSITIVE = "POSITIVE"    # Mean reversion, good for premium selling
    NEGATIVE = "NEGATIVE"    # Trending, bad for premium selling
    NEUTRAL = "NEUTRAL"      # Mixed signals


@dataclass
class MarketContext:
    """Current market conditions for Oracle"""
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


@dataclass
class OraclePrediction:
    """Prediction from Oracle for a specific bot"""
    bot_name: BotName
    advice: TradingAdvice
    win_probability: float
    confidence: float
    suggested_risk_pct: float
    suggested_sd_multiplier: float

    # GEX-specific for ARES
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


# =============================================================================
# CLAUDE AI ENHANCER
# =============================================================================

# =============================================================================
# ORACLE LIVE LOG - For Frontend Transparency
# =============================================================================

class OracleLiveLog:
    """
    Live logging system for Oracle - FULL TRANSPARENCY.
    Captures every piece of data flowing through Oracle for frontend visibility.
    """
    _instance = None
    MAX_LOGS = 500  # Increased for more history
    MAX_DATA_FLOWS = 100  # Store detailed data flow records

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._logs = []
            cls._instance._callbacks = []
            cls._instance._data_flows = []  # Full data pipeline records
            cls._instance._claude_exchanges = []  # Complete Claude prompt/response pairs
        return cls._instance

    def log(self, event_type: str, message: str, data: Optional[Dict] = None):
        """Add a log entry"""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "type": event_type,
            "message": message,
            "data": data
        }
        self._logs.append(entry)

        # Keep only recent logs
        if len(self._logs) > self.MAX_LOGS:
            self._logs = self._logs[-self.MAX_LOGS:]

        # Notify callbacks
        for callback in self._callbacks:
            try:
                callback(entry)
            except:
                pass

        # Also log to standard logger
        logger.info(f"[ORACLE] {event_type}: {message}")

    def log_data_flow(self, bot_name: str, stage: str, data: Dict):
        """
        Log a complete data flow step for full transparency.

        Stages: INPUT, ML_FEATURES, ML_OUTPUT, CLAUDE_PROMPT, CLAUDE_RESPONSE,
                DECISION, SENT_TO_BOT, ANTI_HALLUCINATION_CHECK
        """
        entry = {
            "timestamp": datetime.now().isoformat(),
            "bot_name": bot_name,
            "stage": stage,
            "data": data
        }
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
        Log a complete Claude AI exchange with full context.
        This is the key for transparency - shows exactly what AI sees and says.
        Includes anti-hallucination validation results.
        """
        exchange = {
            "timestamp": datetime.now().isoformat(),
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
oracle_live_log = OracleLiveLog()


class OracleClaudeEnhancer:
    """
    Claude AI integration for Oracle predictions.
    Uses direct Anthropic SDK (no LangChain needed!).

    Provides three key capabilities:
    1. Validate and enhance ML predictions with reasoning
    2. Explain Oracle reasoning in natural language
    3. Identify patterns in training data
    """

    CLAUDE_MODEL = "claude-sonnet-4-5-20250929"  # Sonnet 4.5 - latest model

    def __init__(self, api_key: Optional[str] = None):
        """Initialize Claude AI enhancer"""
        # Check both ANTHROPIC_API_KEY and CLAUDE_API_KEY
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY")
        self._client = None
        self._enabled = False
        self.live_log = oracle_live_log

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

        system_prompt = """You are an expert options trading analyst validating ML predictions for the Oracle system.

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
- Top Factors: {ml_prediction.get('top_factors', [])}

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
    # 2. EXPLAIN ORACLE REASONING
    # =========================================================================

    def explain_prediction(
        self,
        prediction: 'OraclePrediction',
        context: 'MarketContext'
    ) -> str:
        """
        Generate natural language explanation of Oracle's prediction.

        Args:
            prediction: The Oracle prediction to explain
            context: Market context used for prediction

        Returns:
            Human-readable explanation string
        """
        if not self._enabled:
            return f"Oracle predicts {prediction.advice.value} with {prediction.win_probability:.1%} confidence. {prediction.reasoning}"

        day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

        system_prompt = """You are explaining Oracle's trading predictions to a human trader.

Write a clear, concise explanation (3-5 sentences) that:
1. States the recommendation in plain English
2. Explains the key factors driving the decision
3. Highlights any important risks or opportunities
4. Gives actionable guidance

Use a professional but approachable tone. Avoid jargon where possible."""

        user_prompt = f"""Explain this Oracle prediction for {prediction.bot_name.value}:

PREDICTION:
- Advice: {prediction.advice.value}
- Win Probability: {prediction.win_probability:.1%}
- Suggested Risk %: {prediction.suggested_risk_pct:.1f}%
- Use GEX Walls: {"Yes" if prediction.use_gex_walls else "No"}
- Model Reasoning: {prediction.reasoning}

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

            explanation = message.content[0].text.strip()

            self.live_log.log("EXPLAIN_DONE", f"Explanation generated ({len(explanation)} chars)")

            return explanation

        except Exception as e:
            self.live_log.log("ERROR", f"Claude explanation failed: {e}")
            return f"Oracle predicts {prediction.advice.value} with {prediction.win_probability:.1%} confidence. {prediction.reasoning}"

    # =========================================================================
    # 3. IDENTIFY PATTERNS IN TRAINING DATA
    # =========================================================================

    def analyze_training_patterns(
        self,
        df: 'pd.DataFrame',
        recent_losses: Optional[List[Dict]] = None
    ) -> Dict[str, Any]:
        """
        Use Claude to identify patterns in KRONOS training data.

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

        user_prompt = f"""Analyze these KRONOS backtest statistics:

OVERALL PERFORMANCE:
- Total Trades: {total_trades}
- Win Rate: {win_rate:.1f}%
- Recent 30-Day Win Rate: {recent_win_rate:.1f}%

VIX ANALYSIS:
- Average VIX: {avg_vix:.1f}
- Avg VIX on Wins: {vix_win:.1f}
- Avg VIX on Losses: {vix_loss:.1f}

DAY OF WEEK STATS:
{dow_stats}

GEX REGIME STATS:
{gex_stats}

RECENT LOSSES (if any):
{recent_losses or "None"}

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
# ORACLE ADVISOR
# =============================================================================

class OracleAdvisor:
    """
    ORACLE - Central Advisory System for AlphaGEX Trading Bots

    Aggregates multiple signals and provides bot-specific recommendations.

    Features:
    - GEX-aware predictions
    - Bot-specific advice tailoring
    - PostgreSQL persistence for feedback loop
    - Real-time outcome updates
    """

    # Feature columns for ML prediction
    FEATURE_COLS = [
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

    # V1 features (backward compatibility)
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

    def __init__(self, enable_claude: bool = True):
        self.model = None
        self.calibrated_model = None
        self.scaler = None
        self.is_trained = False
        self.training_metrics: Optional[TrainingMetrics] = None
        self.model_version = "0.0.0"
        self._has_gex_features = False

        # Live log for frontend transparency
        self.live_log = oracle_live_log

        # Thresholds
        self.high_confidence_threshold = 0.70
        self.low_confidence_threshold = 0.55

        # Claude AI Enhancer
        self.claude: Optional[OracleClaudeEnhancer] = None
        self._claude_enabled = enable_claude
        if enable_claude:
            self.claude = OracleClaudeEnhancer()

        # Create models directory
        os.makedirs(self.MODEL_PATH, exist_ok=True)

        # Try to load existing model
        self._load_model()

        # Log initialization
        self.live_log.log("INIT", f"Oracle Advisor initialized (model v{self.model_version})", {
            "model_trained": self.is_trained,
            "claude_enabled": enable_claude,
            "has_gex_features": self._has_gex_features
        })

    @property
    def claude_available(self) -> bool:
        """Check if Claude AI is available and enabled"""
        return self.claude is not None and self.claude.is_enabled

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
        model_file = os.path.join(self.MODEL_PATH, 'oracle_model.pkl')

        # Try new name first, then fall back to old name
        if not os.path.exists(model_file):
            model_file = os.path.join(self.MODEL_PATH, 'ares_advisor_model.pkl')

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
                    self.is_trained = True
                    logger.info(f"Loaded Oracle model v{self.model_version} from local file")
                    return True
            except Exception as e:
                logger.warning(f"Failed to load model from file: {e}")

        return False

    def _load_model_from_db(self) -> bool:
        """Load trained model from database (persists across Render deploys)"""
        if not DB_AVAILABLE:
            return False

        try:
            conn = get_connection()
            cursor = conn.cursor()

            # Check if table exists
            cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = 'oracle_trained_models'
                )
            """)
            if not cursor.fetchone()[0]:
                conn.close()
                return False

            # Get the most recent active model
            cursor.execute("""
                SELECT model_version, model_data, training_metrics, has_gex_features
                FROM oracle_trained_models
                WHERE is_active = TRUE
                ORDER BY created_at DESC
                LIMIT 1
            """)
            row = cursor.fetchone()
            conn.close()

            if row:
                model_version, model_data, metrics_json, has_gex = row

                # Deserialize model data
                saved = pickle.loads(model_data)
                self.model = saved.get('model')
                self.calibrated_model = saved.get('calibrated_model')
                self.scaler = saved.get('scaler')
                self.model_version = model_version
                self._has_gex_features = has_gex or False
                self.is_trained = True

                # Restore training metrics
                if metrics_json:
                    if isinstance(metrics_json, str):
                        metrics_dict = json.loads(metrics_json)
                    else:
                        metrics_dict = metrics_json
                    self.training_metrics = TrainingMetrics(**metrics_dict)

                logger.info(f"Loaded Oracle model v{self.model_version} from DATABASE (persistent)")
                return True

        except Exception as e:
            logger.warning(f"Failed to load model from database: {e}")

        return False

    def _save_model(self):
        """Save trained model to BOTH database (for Render) and local file (backup)"""
        # Save to database first (critical for Render persistence)
        db_saved = self._save_model_to_db()

        # Also save to local file as backup
        model_file = os.path.join(self.MODEL_PATH, 'oracle_model.pkl')

        try:
            with open(model_file, 'wb') as f:
                pickle.dump({
                    'model': self.model,
                    'calibrated_model': self.calibrated_model,
                    'scaler': self.scaler,
                    'metrics': self.training_metrics,
                    'version': self.model_version,
                    'has_gex_features': self._has_gex_features,
                    'saved_at': datetime.now().isoformat()
                }, f)
            logger.info(f"Saved Oracle model to {model_file}")
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

        try:
            conn = get_connection()
            cursor = conn.cursor()

            # Create table if not exists
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS oracle_trained_models (
                    id SERIAL PRIMARY KEY,
                    model_version VARCHAR(20) NOT NULL,
                    model_data BYTEA NOT NULL,
                    training_metrics JSONB,
                    has_gex_features BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_active BOOLEAN DEFAULT TRUE
                )
            """)

            # Deactivate previous models
            cursor.execute("UPDATE oracle_trained_models SET is_active = FALSE")

            # Serialize model data
            model_data = pickle.dumps({
                'model': self.model,
                'calibrated_model': self.calibrated_model,
                'scaler': self.scaler,
            })

            # Serialize training metrics
            metrics_json = json.dumps(self.training_metrics.__dict__) if self.training_metrics else None

            # Insert new model
            cursor.execute("""
                INSERT INTO oracle_trained_models
                (model_version, model_data, training_metrics, has_gex_features, is_active)
                VALUES (%s, %s, %s, %s, TRUE)
            """, (
                self.model_version,
                model_data,
                metrics_json,
                self._has_gex_features
            ))

            conn.commit()
            conn.close()

            logger.info(f"Saved Oracle model v{self.model_version} to DATABASE (persists across deploys)")
            return True

        except Exception as e:
            logger.error(f"Failed to save model to database: {e}")
            import traceback
            traceback.print_exc()
            return False

    # =========================================================================
    # BOT-SPECIFIC ADVICE
    # =========================================================================

    def get_ares_advice(
        self,
        context: MarketContext,
        use_gex_walls: bool = False,
        use_claude_validation: bool = True,
        vix_hard_skip: float = 32.0,
        vix_monday_friday_skip: float = 0.0,
        vix_streak_skip: float = 0.0,
        recent_losses: int = 0
    ) -> OraclePrediction:
        """
        Get Iron Condor advice for ARES.

        Args:
            context: Current market conditions
            use_gex_walls: Whether to suggest strikes based on GEX walls
            use_claude_validation: Whether to use Claude AI to validate prediction
            vix_hard_skip: Skip if VIX > this threshold (0 = disabled)
            vix_monday_friday_skip: Skip on Mon/Fri if VIX > this (0 = disabled)
            vix_streak_skip: Skip after recent losses if VIX > this (0 = disabled)
            recent_losses: Number of recent consecutive losses

        Returns:
            OraclePrediction with IC-specific advice
        """
        # Log prediction request
        self.live_log.log("PREDICT", "ARES advice requested", {
            "vix": context.vix,
            "gex_regime": context.gex_regime.value,
            "spot_price": context.spot_price,
            "use_gex_walls": use_gex_walls,
            "use_claude": use_claude_validation,
            "vix_hard_skip": vix_hard_skip,
            "vix_monday_friday_skip": vix_monday_friday_skip,
            "vix_streak_skip": vix_streak_skip
        })

        # =========================================================================
        # VIX-BASED SKIP LOGIC (Configurable per Strategy Preset)
        # Based on backtest: 2022-2024 showed Sharpe 8.55 → 16.84 with VIX filtering
        # =========================================================================
        skip_reason = None
        skip_threshold_used = 0.0

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

        # If any VIX skip rule triggered, return SKIP_TODAY
        if skip_reason:
            self.live_log.log("VIX_SKIP", skip_reason, {
                "vix": context.vix,
                "threshold": skip_threshold_used,
                "day_of_week": context.day_of_week,
                "recent_losses": recent_losses,
                "action": "SKIP_TODAY"
            })
            return OraclePrediction(
                bot_name=BotName.ARES,
                advice=TradingAdvice.SKIP_TODAY,
                win_probability=0.35,
                confidence=0.95,  # High confidence in the skip decision
                suggested_risk_pct=0.0,
                suggested_sd_multiplier=1.0,
                reasoning=skip_reason,
                top_factors=[
                    ("vix_level", context.vix),
                    ("skip_threshold", skip_threshold_used),
                    ("day_of_week", context.day_of_week),
                    ("recent_losses", recent_losses)
                ],
                model_version=self.model_version
            )

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
        self.live_log.log_data_flow("ARES", "INPUT", input_data)

        # Get base prediction
        base_pred = self._get_base_prediction(context)

        # === FULL DATA FLOW LOGGING: ML_OUTPUT ===
        self.live_log.log_data_flow("ARES", "ML_OUTPUT", {
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
                scale_factor = context.spot_price / ((gex_put_wall + gex_call_wall) / 2)
                gex_put_wall = gex_put_wall * scale_factor
                gex_call_wall = gex_call_wall * scale_factor
                logger.info(f"Scaled SPY GEX walls to SPX: Put ${gex_put_wall:.0f}, Call ${gex_call_wall:.0f} (scale: {scale_factor:.2f}x)")

            # Use proportional buffer based on expected move (0.5% of price as minimum)
            # This ensures buffer scales with the underlying
            buffer = max(context.spot_price * 0.005, context.spot_price * context.expected_move_pct / 100 * 0.25)

            suggested_put = gex_put_wall - buffer  # Below put wall (support)
            suggested_call = gex_call_wall + buffer  # Above call wall (resistance)

            logger.info(f"GEX-Protected strikes: Put ${suggested_put:.0f} (wall ${gex_put_wall:.0f} - ${buffer:.0f}), "
                       f"Call ${suggested_call:.0f} (wall ${gex_call_wall:.0f} + ${buffer:.0f})")

        # Adjust advice based on GEX regime
        reasoning_parts = []

        if context.gex_regime == GEXRegime.POSITIVE:
            reasoning_parts.append("Positive GEX favors mean reversion (good for IC)")
            base_pred['win_probability'] = min(0.85, base_pred['win_probability'] + 0.03)
        elif context.gex_regime == GEXRegime.NEGATIVE:
            reasoning_parts.append("Negative GEX indicates trending market (risky for IC)")
            base_pred['win_probability'] = max(0.40, base_pred['win_probability'] - 0.05)

        if context.gex_between_walls:
            reasoning_parts.append("Price between GEX walls (stable zone)")
        else:
            reasoning_parts.append("Price outside GEX walls (breakout risk)")
            base_pred['win_probability'] = max(0.40, base_pred['win_probability'] - 0.03)

        # =========================================================================
        # CLAUDE AI VALIDATION (if enabled)
        # =========================================================================
        claude_analysis = None
        if use_claude_validation and self.claude_available:
            claude_analysis = self.claude.validate_prediction(context, base_pred, BotName.ARES)

            # Apply Claude's confidence adjustment
            if claude_analysis.recommendation in ["ADJUST", "OVERRIDE"]:
                base_pred['win_probability'] = max(0.40, min(0.85,
                    base_pred['win_probability'] + claude_analysis.confidence_adjustment
                ))
                reasoning_parts.append(f"Claude: {claude_analysis.analysis}")

                # Log risk factors
                if claude_analysis.risk_factors:
                    logger.info(f"Claude risk factors: {claude_analysis.risk_factors}")

        # Determine final advice
        advice, risk_pct = self._get_advice_from_probability(base_pred['win_probability'])

        # SD multiplier - ALWAYS keep strikes at or OUTSIDE expected move
        # Backtest showed 97% win rate with SD >= 1.0 (outside expected move)
        # NEVER suggest SD < 1.0 - that puts strikes inside expected move = losses
        if base_pred['win_probability'] >= 0.70:
            sd_mult = 1.0  # Confident: baseline at expected move boundary
        elif base_pred['win_probability'] >= 0.60:
            sd_mult = 1.1  # Medium: slightly wider for safety
        else:
            sd_mult = 1.2  # Low confidence: wider strikes (or should SKIP)

        prediction = OraclePrediction(
            bot_name=BotName.ARES,
            advice=advice,
            win_probability=base_pred['win_probability'],
            confidence=min(100, base_pred['win_probability'] * 100 * 1.2),
            suggested_risk_pct=risk_pct,
            suggested_sd_multiplier=sd_mult,
            use_gex_walls=use_gex_walls,
            suggested_put_strike=suggested_put,
            suggested_call_strike=suggested_call,
            top_factors=base_pred['top_factors'],
            reasoning=" | ".join(reasoning_parts),
            model_version=self.model_version,
            probabilities=base_pred['probabilities'],
            claude_analysis=claude_analysis  # Include real Claude data for logging
        )

        # Log prediction result
        self.live_log.log("PREDICT_DONE", f"ARES: {advice.value} ({base_pred['win_probability']:.1%})", {
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
            "model_version": self.model_version
        }
        self.live_log.log_data_flow("ARES", "DECISION", decision_data)

        return prediction

    def get_atlas_advice(self, context: MarketContext) -> OraclePrediction:
        """
        Get Wheel strategy advice for ATLAS.

        ATLAS trades cash-secured puts and covered calls.
        GEX signals help with entry timing.
        """
        # Log prediction request
        self.live_log.log("PREDICT", "ATLAS advice requested", {
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
        self.live_log.log_data_flow("ATLAS", "INPUT", input_data)

        base_pred = self._get_base_prediction(context)

        # === FULL DATA FLOW LOGGING: ML_OUTPUT ===
        self.live_log.log_data_flow("ATLAS", "ML_OUTPUT", {
            "win_probability": base_pred.get('win_probability'),
            "top_factors": base_pred.get('top_factors', []),
            "probabilities": base_pred.get('probabilities', {}),
            "model_version": self.model_version
        })

        reasoning_parts = []

        # Wheel benefits from high IV (more premium)
        if context.vix > 25:
            reasoning_parts.append("High VIX = rich premiums for CSP")
            base_pred['win_probability'] = min(0.85, base_pred['win_probability'] + 0.05)
        elif context.vix < 15:
            reasoning_parts.append("Low VIX = thin premiums, consider waiting")
            base_pred['win_probability'] = max(0.40, base_pred['win_probability'] - 0.05)

        # Positive GEX = less likely to get assigned
        if context.gex_regime == GEXRegime.POSITIVE:
            reasoning_parts.append("Positive GEX supports put selling")

        advice, risk_pct = self._get_advice_from_probability(base_pred['win_probability'])

        prediction = OraclePrediction(
            bot_name=BotName.ATLAS,
            advice=advice,
            win_probability=base_pred['win_probability'],
            confidence=min(100, base_pred['win_probability'] * 100 * 1.2),
            suggested_risk_pct=risk_pct,
            suggested_sd_multiplier=1.0,
            top_factors=base_pred['top_factors'],
            reasoning=" | ".join(reasoning_parts),
            model_version=self.model_version,
            probabilities=base_pred['probabilities']
        )

        # Log prediction result
        self.live_log.log("PREDICT_DONE", f"ATLAS: {advice.value} ({base_pred['win_probability']:.1%})", {
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
        self.live_log.log_data_flow("ATLAS", "DECISION", decision_data)

        return prediction

    def get_phoenix_advice(
        self,
        context: MarketContext,
        use_claude_validation: bool = True
    ) -> OraclePrediction:
        """
        Get directional call advice for PHOENIX.

        PHOENIX trades long calls, needs directional bias.
        """
        # Log prediction request
        self.live_log.log("PREDICT", "PHOENIX advice requested", {
            "vix": context.vix,
            "gex_regime": context.gex_regime.value,
            "spot_price": context.spot_price,
            "claude_validation": use_claude_validation
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
        self.live_log.log_data_flow("PHOENIX", "INPUT", input_data)

        base_pred = self._get_base_prediction(context)

        # === FULL DATA FLOW LOGGING: ML_OUTPUT ===
        self.live_log.log_data_flow("PHOENIX", "ML_OUTPUT", {
            "win_probability": base_pred.get('win_probability'),
            "top_factors": base_pred.get('top_factors', []),
            "probabilities": base_pred.get('probabilities', {}),
            "model_version": self.model_version
        })

        reasoning_parts = []

        # Negative GEX + below flip = potential rally
        if context.gex_regime == GEXRegime.NEGATIVE and context.gex_distance_to_flip_pct < 0:
            reasoning_parts.append("Negative GEX below flip = gamma squeeze potential")
            base_pred['win_probability'] = min(0.75, base_pred['win_probability'] + 0.10)
        elif context.gex_regime == GEXRegime.POSITIVE:
            reasoning_parts.append("Positive GEX = mean reversion, less directional opportunity")
            base_pred['win_probability'] = max(0.30, base_pred['win_probability'] - 0.10)

        # =========================================================================
        # CLAUDE AI VALIDATION (if enabled)
        # =========================================================================
        claude_analysis = None
        if use_claude_validation and self.claude_available:
            claude_analysis = self.claude.validate_prediction(context, base_pred, BotName.PHOENIX)

            # Apply Claude's confidence adjustment
            if claude_analysis.recommendation in ["ADJUST", "OVERRIDE"]:
                base_pred['win_probability'] = max(0.30, min(0.80,
                    base_pred['win_probability'] + claude_analysis.confidence_adjustment
                ))
                reasoning_parts.append(f"Claude: {claude_analysis.analysis}")

        advice, risk_pct = self._get_advice_from_probability(base_pred['win_probability'])

        prediction = OraclePrediction(
            bot_name=BotName.PHOENIX,
            advice=advice,
            win_probability=base_pred['win_probability'],
            confidence=min(100, base_pred['win_probability'] * 100 * 1.2),
            suggested_risk_pct=risk_pct * 0.5,  # Lower risk for directional
            suggested_sd_multiplier=1.0,
            top_factors=base_pred['top_factors'],
            reasoning=" | ".join(reasoning_parts),
            model_version=self.model_version,
            probabilities=base_pred['probabilities'],
            claude_analysis=claude_analysis  # Include real Claude data for logging
        )

        # Log prediction result
        self.live_log.log("PREDICT_DONE", f"PHOENIX: {advice.value} ({base_pred['win_probability']:.1%})", {
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
            "model_version": self.model_version
        }
        self.live_log.log_data_flow("PHOENIX", "DECISION", decision_data)

        return prediction

    def get_athena_advice(
        self,
        context: MarketContext,
        use_gex_walls: bool = True,
        use_claude_validation: bool = True,
        wall_filter_pct: float = 1.0  # Default 1.0%, backtest showed 0.5% = 98% WR
    ) -> OraclePrediction:
        """
        Get directional spread advice for ATHENA.

        ATHENA trades Bull Call Spreads (bullish) and Bear Call Spreads (bearish).
        Uses GEX walls for entry timing and direction confirmation.

        Strategy:
        - BULLISH: Buy ATM call, Sell OTM call (Bull Call Spread)
        - BEARISH: Sell ATM call, Buy OTM call (Bear Call Spread)

        GEX Wall Logic:
        - Near Put Wall (support) + BULLISH signal = Strong entry for Bull Call Spread
        - Near Call Wall (resistance) + BEARISH signal = Strong entry for Bear Call Spread
        """
        # Log prediction request
        self.live_log.log("PREDICT", "ATHENA advice requested", {
            "vix": context.vix,
            "gex_regime": context.gex_regime.value,
            "spot_price": context.spot_price,
            "use_gex_walls": use_gex_walls,
            "claude_validation": use_claude_validation
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
        self.live_log.log_data_flow("ATHENA", "INPUT", input_data)

        base_pred = self._get_base_prediction(context)

        # === FULL DATA FLOW LOGGING: ML_OUTPUT ===
        self.live_log.log_data_flow("ATHENA", "ML_OUTPUT", {
            "win_probability": base_pred.get('win_probability'),
            "top_factors": base_pred.get('top_factors', []),
            "probabilities": base_pred.get('probabilities', {}),
            "model_version": self.model_version
        })

        reasoning_parts = []

        # Determine directional bias from GEX structure
        direction = "FLAT"
        direction_confidence = 0.5

        # Calculate distance to walls
        dist_to_call_wall = 0
        dist_to_put_wall = 0

        if context.gex_call_wall > 0 and context.spot_price > 0:
            dist_to_call_wall = (context.gex_call_wall - context.spot_price) / context.spot_price * 100
        if context.gex_put_wall > 0 and context.spot_price > 0:
            dist_to_put_wall = (context.spot_price - context.gex_put_wall) / context.spot_price * 100

        # GEX-based directional logic
        if context.gex_regime == GEXRegime.NEGATIVE:
            # Negative GEX = trending market, directional opportunity
            if context.gex_distance_to_flip_pct < -1:
                # Price well below flip point = bearish momentum
                direction = "BEARISH"
                direction_confidence = 0.60
                reasoning_parts.append("Negative GEX below flip = bearish momentum")
            elif context.gex_distance_to_flip_pct > 1:
                # Price above flip in negative GEX = potential reversal
                direction = "BULLISH"
                direction_confidence = 0.55
                reasoning_parts.append("Price above flip in negative GEX = squeeze potential")
        elif context.gex_regime == GEXRegime.POSITIVE:
            # Positive GEX = mean reversion
            if dist_to_put_wall < 1.0 and dist_to_put_wall > 0:
                # Near support
                direction = "BULLISH"
                direction_confidence = 0.65
                reasoning_parts.append(f"Near put wall support ({dist_to_put_wall:.1f}%)")
            elif dist_to_call_wall < 1.0 and dist_to_call_wall > 0:
                # Near resistance
                direction = "BEARISH"
                direction_confidence = 0.65
                reasoning_parts.append(f"Near call wall resistance ({dist_to_call_wall:.1f}%)")

        # Wall filter check - use configurable parameter (backtest: 0.5% = 98% WR, 1.0% = 90% WR)
        wall_filter_passed = False
        if use_gex_walls:
            if direction == "BULLISH" and dist_to_put_wall < wall_filter_pct:
                wall_filter_passed = True
                reasoning_parts.append(f"Wall filter PASSED: {dist_to_put_wall:.2f}% from put wall (threshold: {wall_filter_pct}%)")
            elif direction == "BEARISH" and dist_to_call_wall < wall_filter_pct:
                wall_filter_passed = True
                reasoning_parts.append(f"Wall filter PASSED: {dist_to_call_wall:.2f}% from call wall (threshold: {wall_filter_pct}%)")
            else:
                reasoning_parts.append(f"Wall filter FAILED: Call wall {dist_to_call_wall:.1f}%, Put wall {dist_to_put_wall:.1f}% (need < {wall_filter_pct}%)")

        # Adjust win probability based on direction confidence
        if direction != "FLAT":
            base_pred['win_probability'] = max(0.40, min(0.85, direction_confidence))
            if wall_filter_passed:
                base_pred['win_probability'] = min(0.90, base_pred['win_probability'] + 0.10)
        else:
            base_pred['win_probability'] = 0.45  # No directional bias

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
            claude_analysis = self.claude.validate_prediction(context, base_pred, BotName.ATHENA)

            if claude_analysis.recommendation in ["ADJUST", "OVERRIDE"]:
                base_pred['win_probability'] = max(0.30, min(0.85,
                    base_pred['win_probability'] + claude_analysis.confidence_adjustment
                ))
                reasoning_parts.append(f"Claude: {claude_analysis.analysis}")

        advice, risk_pct = self._get_advice_from_probability(base_pred['win_probability'])

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

        prediction = OraclePrediction(
            bot_name=BotName.ATHENA,
            advice=advice,
            win_probability=base_pred['win_probability'],
            confidence=min(100, direction_confidence * 100),
            suggested_risk_pct=risk_pct * 0.5,  # Conservative for directional spreads
            suggested_sd_multiplier=1.0,
            use_gex_walls=use_gex_walls,
            suggested_put_strike=suggested_put,
            suggested_call_strike=suggested_call,
            top_factors=base_pred.get('top_factors', []),
            reasoning=" | ".join(reasoning_parts) + f" | Direction: {direction}",
            model_version=self.model_version,
            probabilities=base_pred.get('probabilities', {}),
            claude_analysis=claude_analysis
        )

        # Log prediction result
        self.live_log.log("PREDICT_DONE", f"ATHENA: {advice.value} ({base_pred['win_probability']:.1%})", {
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
            "reasoning": prediction.reasoning,
            "claude_validated": claude_analysis is not None,
            "claude_recommendation": claude_analysis.recommendation if claude_analysis else None,
            "claude_confidence_adj": claude_analysis.confidence_adjustment if claude_analysis else None,
            "model_version": self.model_version
        }
        self.live_log.log_data_flow("ATHENA", "DECISION", decision_data)

        return prediction

    # =========================================================================
    # PEGASUS ADVICE (SPX IRON CONDOR - WEEKLY)
    # =========================================================================

    def get_pegasus_advice(
        self,
        context: MarketContext,
        use_gex_walls: bool = True,
        use_claude_validation: bool = True,
        vix_hard_skip: float = 0.0,
        vix_monday_friday_skip: float = 0.0,
        vix_streak_skip: float = 0.0,
        recent_losses: int = 0,
        spread_width: float = 10.0  # Default $10 spread width
    ) -> OraclePrediction:
        """
        Get Iron Condor advice for PEGASUS (SPX Weekly Iron Condors).

        PEGASUS trades SPX weekly options with $10 spread widths.
        Key differences from ARES:
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
            OraclePrediction with SPX IC-specific advice
        """
        # Log prediction request
        self.live_log.log("PREDICT", "PEGASUS advice requested", {
            "vix": context.vix,
            "gex_regime": context.gex_regime.value,
            "spot_price": context.spot_price,
            "use_gex_walls": use_gex_walls,
            "use_claude": use_claude_validation,
            "vix_hard_skip": vix_hard_skip,
            "spread_width": spread_width
        })

        # =========================================================================
        # VIX-BASED SKIP LOGIC (Similar to ARES but tuned for SPX weekly)
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
        if skip_reason:
            self.live_log.log("VIX_SKIP", skip_reason, {
                "vix": context.vix,
                "threshold": skip_threshold_used,
                "day_of_week": context.day_of_week,
                "recent_losses": recent_losses,
                "action": "SKIP_TODAY"
            })
            return OraclePrediction(
                bot_name=BotName.PEGASUS,
                advice=TradingAdvice.SKIP_TODAY,
                win_probability=0.35,
                confidence=0.95,
                suggested_risk_pct=0.0,
                suggested_sd_multiplier=1.0,
                reasoning=skip_reason,
                top_factors=[
                    ("vix_level", context.vix),
                    ("skip_threshold", skip_threshold_used),
                    ("day_of_week", context.day_of_week),
                    ("recent_losses", recent_losses)
                ],
                model_version=self.model_version
            )

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
        self.live_log.log_data_flow("PEGASUS", "INPUT", input_data)

        # Get base prediction
        base_pred = self._get_base_prediction(context)

        # === FULL DATA FLOW LOGGING: ML_OUTPUT ===
        self.live_log.log_data_flow("PEGASUS", "ML_OUTPUT", {
            "win_probability": base_pred.get('win_probability'),
            "top_factors": base_pred.get('top_factors', []),
            "probabilities": base_pred.get('probabilities', {}),
            "model_version": self.model_version
        })

        reasoning_parts = []

        # SPX-specific GEX analysis (use SPX values from context)
        # SPX typically has ~10x the notional of SPY
        gex_context = f"GEX Regime: {context.gex_regime.value}"
        if context.gex_between_walls:
            gex_context += " - Price between walls (pinning expected)"
            reasoning_parts.append("SPX between GEX walls - favorable for Iron Condor")
        else:
            reasoning_parts.append(f"SPX GEX regime: {context.gex_regime.value}")

        # Weekly expiration considerations
        if context.days_to_opex <= 2:
            reasoning_parts.append(f"Near expiration ({context.days_to_opex} days) - elevated gamma risk")

        # Determine trading advice based on probability
        win_prob = base_pred['win_probability']

        # SPX IC thresholds (slightly more conservative than SPY 0DTE)
        if win_prob >= 0.58:
            advice = TradingAdvice.TRADE_FULL
            risk_pct = 0.03  # 3% risk for full position
            reasoning_parts.append(f"Strong setup: {win_prob:.1%} win probability")
        elif win_prob >= 0.52:
            advice = TradingAdvice.TRADE_HALF
            risk_pct = 0.015  # 1.5% risk for half position
            reasoning_parts.append(f"Moderate setup: {win_prob:.1%} win probability")
        elif win_prob >= 0.48:
            advice = TradingAdvice.TRADE_CAUTIOUS
            risk_pct = 0.01  # 1% risk for cautious position
            reasoning_parts.append(f"Marginal setup: {win_prob:.1%} win probability")
        else:
            advice = TradingAdvice.SKIP_TODAY
            risk_pct = 0.0
            reasoning_parts.append(f"Poor setup: {win_prob:.1%} win probability - skip")

        # GEX wall-based strike suggestions for SPX
        suggested_put = None
        suggested_call = None

        if use_gex_walls and context.gex_put_wall > 0 and context.gex_call_wall > 0:
            # For SPX IC, use GEX walls as outer boundaries
            # Put spread below put wall, call spread above call wall
            suggested_put = context.gex_put_wall - spread_width
            suggested_call = context.gex_call_wall + spread_width
            reasoning_parts.append(f"GEX walls: Put wall {context.gex_put_wall:.0f}, Call wall {context.gex_call_wall:.0f}")

        # Claude AI validation (optional)
        claude_analysis = None
        if use_claude_validation and self.claude_analyzer:
            try:
                claude_analysis = self.claude_analyzer.analyze_setup(
                    context, "PEGASUS_IC", win_prob, reasoning_parts
                )
                if claude_analysis:
                    reasoning_parts.append(f"Claude: {claude_analysis.recommendation}")
                    # Adjust confidence based on Claude
                    if claude_analysis.confidence_adjustment:
                        win_prob = min(0.95, max(0.05, win_prob + claude_analysis.confidence_adjustment))
            except Exception as e:
                self.live_log.log("CLAUDE_ERROR", f"PEGASUS Claude validation failed: {e}")

        # Build final prediction
        prediction = OraclePrediction(
            bot_name=BotName.PEGASUS,
            advice=advice,
            win_probability=win_prob,
            confidence=base_pred.get('confidence', 0.6),
            suggested_risk_pct=risk_pct,
            suggested_sd_multiplier=1.0,  # SPX uses fixed spread widths
            reasoning=" | ".join(reasoning_parts),
            top_factors=base_pred.get('top_factors', []),
            model_version=self.model_version,
            suggested_put_strike=suggested_put,
            suggested_call_strike=suggested_call
        )

        # Log prediction result
        self.live_log.log("PREDICT_DONE", f"PEGASUS: {advice.value} ({win_prob:.1%})", {
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
            "model_version": self.model_version
        }
        self.live_log.log_data_flow("PEGASUS", "DECISION", decision_data)

        return prediction

    # =========================================================================
    # BASE PREDICTION
    # =========================================================================

    def _get_base_prediction(self, context: MarketContext) -> Dict[str, Any]:
        """Get base ML prediction from context"""
        if not self.is_trained:
            return self._fallback_prediction(context)

        # Prepare features
        gex_regime_positive = 1 if context.gex_regime == GEXRegime.POSITIVE else 0
        gex_between_walls = 1 if context.gex_between_walls else 0

        if self._has_gex_features:
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
        else:
            features = np.array([[
                context.vix,
                context.vix_percentile_30d,
                context.vix_change_1d,
                context.day_of_week,
                context.price_change_1d,
                context.expected_move_pct,
                context.win_rate_30d,
            ]])

        # Scale and predict
        features_scaled = self.scaler.transform(features)

        if self.calibrated_model:
            proba = self.calibrated_model.predict_proba(features_scaled)[0]
        else:
            proba = self.model.predict_proba(features_scaled)[0]

        win_probability = proba[1]

        # Feature importance
        feature_cols = self.FEATURE_COLS if self._has_gex_features else self.FEATURE_COLS_V1
        feature_importance = dict(zip(feature_cols, self.model.feature_importances_))
        top_factors = sorted(feature_importance.items(), key=lambda x: -x[1])[:3]

        return {
            'win_probability': win_probability,
            'top_factors': top_factors,
            'probabilities': {'win': proba[1], 'loss': proba[0]}
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

        # Day of week (Monday/Friday are historically worse)
        dow_adj = {0: -0.08, 1: 0.02, 2: 0.03, 3: 0.02, 4: -0.05}
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

    # =========================================================================
    # CLAUDE AI METHODS
    # =========================================================================

    def explain_prediction(
        self,
        prediction: OraclePrediction,
        context: MarketContext
    ) -> str:
        """
        Get natural language explanation of prediction using Claude AI.

        Args:
            prediction: Oracle prediction to explain
            context: Market context used for prediction

        Returns:
            Human-readable explanation string
        """
        if self.claude_available:
            return self.claude.explain_prediction(prediction, context)
        else:
            return f"Oracle predicts {prediction.advice.value} with {prediction.win_probability:.1%} confidence. {prediction.reasoning}"

    def get_claude_analysis(
        self,
        context: MarketContext,
        bot_name: BotName = BotName.ARES
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
            backtest_results: Optional KRONOS results (will extract features if provided)

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
                df = self.extract_features_from_kronos(backtest_results)
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

    def extract_features_from_kronos(
        self,
        backtest_results: Dict[str, Any],
        include_gex: bool = True
    ) -> pd.DataFrame:
        """Extract ML features from KRONOS backtest results"""
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
                from quant.kronos_gex_calculator import enrich_trades_with_gex
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

        for i, trade in enumerate(trades):
            # Rolling stats
            lookback_start = max(0, i - 30)
            recent_outcomes = outcomes[lookback_start:i] if i > 0 else []
            recent_pnls = pnls[lookback_start:i] if i > 0 else []

            win_rate_30d = sum(1 for o in recent_outcomes if o == 'MAX_PROFIT') / len(recent_outcomes) if recent_outcomes else 0.68
            avg_pnl_30d = sum(recent_pnls) / len(recent_pnls) if recent_pnls else 0

            trade_date = trade.get('trade_date', '')
            try:
                dt = datetime.strptime(trade_date, '%Y-%m-%d')
                day_of_week = dt.weekday()
            except:
                day_of_week = 2

            vix = trade.get('vix', 20.0)
            open_price = trade.get('open_price', 5000)
            close_price = trade.get('close_price', open_price)
            price_change_1d = (close_price - open_price) / open_price * 100 if open_price > 0 else 0
            expected_move = trade.get('expected_move_sd', trade.get('expected_move_1d', 50))
            expected_move_pct = expected_move / open_price * 100 if open_price > 0 else 1.0

            outcome = trade.get('outcome', 'MAX_PROFIT')
            is_win = outcome == 'MAX_PROFIT'
            net_pnl = trade.get('net_pnl', 0)

            outcomes.append(outcome)
            pnls.append(net_pnl)

            record = {
                'trade_date': trade_date,
                'vix': vix,
                'vix_percentile_30d': 50,
                'vix_change_1d': 0,
                'day_of_week': day_of_week,
                'price_change_1d': price_change_1d,
                'expected_move_pct': expected_move_pct,
                'win_rate_30d': win_rate_30d,
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

    def train_from_kronos(
        self,
        backtest_results: Dict[str, Any],
        test_size: float = 0.2,
        min_samples: int = 100
    ) -> TrainingMetrics:
        """Train Oracle from KRONOS backtest results"""
        # Log training start
        self.live_log.log("TRAIN_START", "Oracle training initiated from KRONOS data", {
            "test_size": test_size,
            "min_samples": min_samples
        })

        if not ML_AVAILABLE:
            self.live_log.log("TRAIN_ERROR", "ML libraries not available", {})
            raise ImportError("ML libraries required")

        df = self.extract_features_from_kronos(backtest_results)

        if len(df) < min_samples:
            raise ValueError(f"Insufficient data: {len(df)} < {min_samples}")

        logger.info(f"Training Oracle on {len(df)} trades")

        feature_cols = self.FEATURE_COLS if self._has_gex_features else self.FEATURE_COLS_V1
        X = df[feature_cols].values
        y = df['is_win'].values.astype(int)

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

        accuracies, precisions, recalls, f1s, aucs = [], [], [], [], []

        for train_idx, test_idx in tscv.split(X_scaled):
            X_train, X_test = X_scaled[train_idx], X_scaled[test_idx]
            y_train, y_test = y[train_idx], y[test_idx]

            self.model.fit(X_train, y_train)
            y_pred = self.model.predict(X_test)
            y_proba = self.model.predict_proba(X_test)[:, 1]

            accuracies.append(accuracy_score(y_test, y_pred))
            precisions.append(precision_score(y_test, y_pred, zero_division=0))
            recalls.append(recall_score(y_test, y_pred, zero_division=0))
            f1s.append(f1_score(y_test, y_pred, zero_division=0))
            try:
                aucs.append(roc_auc_score(y_test, y_proba))
            except ValueError:
                aucs.append(0.5)

        self.model.fit(X_scaled, y)

        self.calibrated_model = CalibratedClassifierCV(self.model, method='isotonic', cv=3)
        self.calibrated_model.fit(X_scaled, y)

        y_proba_full = self.calibrated_model.predict_proba(X_scaled)[:, 1]
        brier = brier_score_loss(y, y_proba_full)

        feature_importances = dict(zip(feature_cols, self.model.feature_importances_))

        self.training_metrics = TrainingMetrics(
            accuracy=np.mean(accuracies),
            precision=np.mean(precisions),
            recall=np.mean(recalls),
            f1_score=np.mean(f1s),
            auc_roc=np.mean(aucs),
            brier_score=brier,
            win_rate_predicted=y_proba_full.mean(),
            win_rate_actual=y.mean(),
            total_samples=len(df),
            train_samples=int(len(df) * (1 - test_size)),
            test_samples=int(len(df) * test_size),
            positive_samples=int(y.sum()),
            negative_samples=int(len(y) - y.sum()),
            feature_importances=feature_importances,
            training_date=datetime.now().isoformat(),
            model_version="1.0.0"
        )

        self.is_trained = True
        self.model_version = "1.0.0"
        self._save_model()

        # Log training complete
        self.live_log.log("TRAIN_DONE", f"Oracle trained - Accuracy: {self.training_metrics.accuracy:.1%}", {
            "accuracy": self.training_metrics.accuracy,
            "auc_roc": self.training_metrics.auc_roc,
            "total_samples": self.training_metrics.total_samples,
            "win_rate_actual": self.training_metrics.win_rate_actual,
            "model_version": self.model_version
        })

        logger.info(f"Oracle trained successfully:")
        logger.info(f"  Accuracy: {self.training_metrics.accuracy:.2%}")
        logger.info(f"  AUC-ROC: {self.training_metrics.auc_roc:.3f}")
        logger.info(f"  Win Rate: {self.training_metrics.win_rate_actual:.2%}")

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
        prediction: OraclePrediction,
        context: MarketContext,
        trade_date: str
    ) -> bool:
        """Store prediction to database for feedback loop - FULL data persistence"""
        if not DB_AVAILABLE:
            logger.warning("Database not available")
            return False

        try:
            conn = get_connection()
            cursor = conn.cursor()

            # Ensure table has all required columns (migration-safe)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS oracle_predictions (
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

                    -- GEX-Specific (ARES)
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
            ]
            for col_name, col_type in migration_columns:
                try:
                    cursor.execute(f"ALTER TABLE oracle_predictions ADD COLUMN IF NOT EXISTS {col_name} {col_type}")
                except Exception:
                    pass  # Column already exists or other error

            conn.commit()

            # Serialize top_factors as JSON
            top_factors_json = json.dumps([
                {"feature": f[0], "importance": f[1]}
                for f in (prediction.top_factors or [])
            ]) if prediction.top_factors else None

            # Serialize probabilities as JSON
            probabilities_json = json.dumps(prediction.probabilities) if prediction.probabilities else None

            # Serialize Claude analysis as JSON (full transparency)
            claude_json = None
            if prediction.claude_analysis:
                ca = prediction.claude_analysis
                claude_json = json.dumps({
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
                })

            cursor.execute("""
                INSERT INTO oracle_predictions (
                    trade_date, bot_name, spot_price, vix, gex_net, gex_normalized, gex_regime,
                    gex_flip_point, gex_call_wall, gex_put_wall, day_of_week,
                    advice, win_probability, confidence, suggested_risk_pct,
                    suggested_sd_multiplier, model_version,
                    use_gex_walls, suggested_put_strike, suggested_call_strike,
                    reasoning, top_factors, probabilities, claude_analysis
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (trade_date, bot_name) DO UPDATE SET
                    advice = EXCLUDED.advice,
                    win_probability = EXCLUDED.win_probability,
                    confidence = EXCLUDED.confidence,
                    reasoning = EXCLUDED.reasoning,
                    top_factors = EXCLUDED.top_factors,
                    probabilities = EXCLUDED.probabilities,
                    claude_analysis = EXCLUDED.claude_analysis,
                    timestamp = NOW()
            """, (
                trade_date,
                prediction.bot_name.value,
                context.spot_price,
                context.vix,
                context.gex_net,
                context.gex_normalized,
                context.gex_regime.value,
                context.gex_flip_point,
                context.gex_call_wall,
                context.gex_put_wall,
                context.day_of_week,
                prediction.advice.value,
                prediction.win_probability,
                prediction.confidence,
                prediction.suggested_risk_pct,
                prediction.suggested_sd_multiplier,
                prediction.model_version,
                prediction.use_gex_walls,
                prediction.suggested_put_strike,
                prediction.suggested_call_strike,
                prediction.reasoning,
                top_factors_json,
                probabilities_json,
                claude_json
            ))

            conn.commit()
            conn.close()
            logger.info(f"Stored Oracle prediction for {prediction.bot_name.value}")

            # === COMPREHENSIVE BOT LOGGER ===
            if BOT_LOGGER_AVAILABLE and log_bot_decision:
                try:
                    comprehensive = BotDecision(
                        bot_name="ORACLE",
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
                        entry_reasoning=f"Oracle {prediction.advice.value}: Win prob {prediction.win_probability:.1%}, Risk {prediction.suggested_risk_pct:.1%}",
                        backtest_win_rate=prediction.win_probability * 100,
                        kelly_pct=prediction.suggested_risk_pct,
                        passed_all_checks=prediction.advice.value != "SKIP_TODAY",
                        blocked_reason="" if prediction.advice.value != "SKIP_TODAY" else prediction.reasoning or "Low win probability",
                    )
                    comp_id = log_bot_decision(comprehensive)
                    logger.info(f"Oracle logged to bot_decision_logs: {comp_id}")
                except Exception as comp_e:
                    logger.warning(f"Could not log Oracle to comprehensive table: {comp_e}")

            return True

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
        call_strike: float = None
    ) -> bool:
        """Update prediction with actual outcome and store training data for ML feedback loop"""
        if not DB_AVAILABLE:
            return False

        try:
            conn = get_connection()
            cursor = conn.cursor()

            # Update the prediction with outcome
            cursor.execute("""
                UPDATE oracle_predictions
                SET prediction_used = TRUE,
                    actual_outcome = %s,
                    actual_pnl = %s,
                    outcome_date = CURRENT_DATE
                WHERE trade_date = %s AND bot_name = %s
            """, (outcome.value, actual_pnl, trade_date, bot_name.value))

            # Also store in oracle_training_outcomes for ML feedback loop
            # First, get the original prediction features
            cursor.execute("""
                SELECT spot_price, vix, gex_net, gex_normalized, gex_regime,
                       gex_flip_point, gex_call_wall, gex_put_wall, day_of_week,
                       win_probability, suggested_put_strike, suggested_call_strike,
                       model_version
                FROM oracle_predictions
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

                # Create training outcomes table if needed
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS oracle_training_outcomes (
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
                        UNIQUE(trade_date, bot_name)
                    )
                """)

                # Store training outcome for ML retraining
                cursor.execute("""
                    INSERT INTO oracle_training_outcomes (
                        trade_date, bot_name, features, outcome, is_win, net_pnl,
                        put_strike, call_strike, spot_at_entry, spot_at_exit
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (trade_date, bot_name) DO UPDATE SET
                        outcome = EXCLUDED.outcome,
                        is_win = EXCLUDED.is_win,
                        net_pnl = EXCLUDED.net_pnl,
                        spot_at_exit = EXCLUDED.spot_at_exit
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
                    spot_at_exit
                ))

                # Log to live log
                self.live_log.log("OUTCOME", f"{bot_name.value}: {outcome.value} (${actual_pnl:+.2f})", {
                    "bot": bot_name.value,
                    "outcome": outcome.value,
                    "pnl": actual_pnl,
                    "is_win": is_win
                })

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

_oracle: Optional[OracleAdvisor] = None


def get_oracle() -> OracleAdvisor:
    """Get or create Oracle singleton"""
    global _oracle
    if _oracle is None:
        _oracle = OracleAdvisor()
    return _oracle


def get_ares_advice(
    vix: float,
    day_of_week: int = None,
    gex_regime: str = "NEUTRAL",
    gex_call_wall: float = 0,
    gex_put_wall: float = 0,
    use_gex_walls: bool = False,
    **kwargs
) -> OraclePrediction:
    """Quick helper to get ARES advice"""
    if day_of_week is None:
        day_of_week = datetime.now().weekday()

    regime = GEXRegime[gex_regime] if isinstance(gex_regime, str) else gex_regime

    context = MarketContext(
        spot_price=kwargs.get('price', 5000),
        vix=vix,
        day_of_week=day_of_week,
        gex_regime=regime,
        gex_call_wall=gex_call_wall,
        gex_put_wall=gex_put_wall,
        **{k: v for k, v in kwargs.items() if k != 'price'}
    )

    oracle = get_oracle()
    return oracle.get_ares_advice(context, use_gex_walls=use_gex_walls)


# Backward compatibility aliases
AresMLAdvisor = OracleAdvisor
get_advisor = get_oracle
get_trading_advice = get_ares_advice


def train_from_backtest(backtest_results: Dict[str, Any]) -> TrainingMetrics:
    """Train Oracle from backtest results"""
    oracle = get_oracle()
    return oracle.train_from_kronos(backtest_results)


def explain_oracle_advice(
    prediction: OraclePrediction,
    context: MarketContext
) -> str:
    """Get Claude AI explanation of Oracle prediction"""
    oracle = get_oracle()
    return oracle.explain_prediction(prediction, context)


def analyze_kronos_patterns(backtest_results: Dict[str, Any]) -> Dict[str, Any]:
    """Use Claude to analyze patterns in KRONOS backtest results"""
    oracle = get_oracle()
    return oracle.analyze_patterns(backtest_results)


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
            cursor.execute("SELECT COUNT(*) FROM oracle_training_outcomes")
            count = cursor.fetchone()[0]
        except Exception:
            # Table might not exist yet
            count = 0

        conn.close()
        return count
    except Exception as e:
        logger.warning(f"Failed to get pending outcomes count: {e}")
        return 0


def get_training_status() -> Dict[str, Any]:
    """Get comprehensive training status for API"""
    oracle = get_oracle()
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
                cursor.execute("SELECT COUNT(*) FROM oracle_training_outcomes")
                total_outcomes = cursor.fetchone()[0]
            except Exception:
                conn.rollback()  # Reset transaction state
                total_outcomes = 0

            # Try to get last training date from model save time
            try:
                cursor.execute("""
                    SELECT MAX(created_at) FROM oracle_trained_models
                    WHERE is_active = TRUE
                """)
                row = cursor.fetchone()
                if row and row[0]:
                    last_trained = row[0].isoformat()
            except Exception:
                conn.rollback()  # Reset transaction state

            # Check if model exists in database
            try:
                cursor.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables
                        WHERE table_name = 'oracle_trained_models'
                    )
                """)
                if cursor.fetchone()[0]:
                    cursor.execute("""
                        SELECT model_version, created_at FROM oracle_trained_models
                        WHERE is_active = TRUE
                        ORDER BY created_at DESC LIMIT 1
                    """)
                    db_row = cursor.fetchone()
                    if db_row:
                        db_model_exists = True
                        model_source = "database"
                        if not last_trained:
                            last_trained = db_row[1].isoformat() if db_row[1] else None
            except Exception:
                conn.rollback()

        except Exception as e:
            logger.warning(f"Failed to get training status: {e}")
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    # Determine model source
    if oracle.is_trained and not db_model_exists:
        model_source = "local_file"
    elif not oracle.is_trained:
        model_source = "none"

    return {
        "model_trained": oracle.is_trained,
        "model_version": oracle.model_version,
        "pending_outcomes": pending_count,
        "total_outcomes": total_outcomes,
        "last_trained": last_trained,
        "threshold_for_retrain": 100,
        "needs_training": pending_count >= 100 or not oracle.is_trained,
        "training_metrics": oracle.training_metrics.__dict__ if oracle.training_metrics else None,
        "claude_available": oracle.claude_available,
        "model_source": model_source,
        "db_persistence": db_model_exists,
        "persistence_status": "Model saved in database - survives restarts" if db_model_exists else "Model NOT in database - will be lost on restart"
    }


def train_from_live_outcomes(min_samples: int = 100) -> Optional[TrainingMetrics]:
    """
    Train Oracle model from live trading outcomes stored in database.

    This enables continuous learning from actual trading results.
    """
    if not DB_AVAILABLE:
        logger.error("Database not available for training")
        return None

    oracle = get_oracle()
    oracle.live_log.log("TRAIN_START", "Auto-training from live outcomes", {"min_samples": min_samples})

    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Get all outcomes from database
        cursor.execute("""
            SELECT trade_date, bot_name, features, outcome, is_win, net_pnl
            FROM oracle_training_outcomes
            ORDER BY trade_date
        """)
        rows = cursor.fetchall()
        conn.close()

        if len(rows) < min_samples:
            oracle.live_log.log("TRAIN_SKIP", f"Insufficient live data: {len(rows)} < {min_samples}", {})
            logger.info(f"Insufficient live outcomes for training: {len(rows)} < {min_samples}")
            return None

        # Convert to training format
        records = []
        for row in rows:
            trade_date, bot_name, features_json, outcome, is_win, net_pnl = row

            if isinstance(features_json, str):
                features = json.loads(features_json)
            else:
                features = features_json or {}

            record = {
                'trade_date': trade_date,
                'is_win': 1 if is_win else 0,
                'vix': features.get('vix', 20),
                'day_of_week': features.get('day_of_week', 2),
                'price_change_1d': features.get('price_change_1d', 0),
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
        oracle._has_gex_features = has_gex

        feature_cols = oracle.FEATURE_COLS if has_gex else oracle.FEATURE_COLS_V1

        # Ensure all required columns exist
        for col in feature_cols:
            if col not in df.columns:
                df[col] = 0

        X = df[feature_cols].values
        y = df['is_win'].values.astype(int)

        # Train model
        oracle.scaler = StandardScaler()
        X_scaled = oracle.scaler.fit_transform(X)

        tscv = TimeSeriesSplit(n_splits=5)

        oracle.model = GradientBoostingClassifier(
            n_estimators=150,
            max_depth=4,
            learning_rate=0.1,
            min_samples_split=20,
            min_samples_leaf=10,
            subsample=0.8,
            random_state=42
        )

        accuracies, precisions, recalls, f1s, aucs = [], [], [], [], []

        for train_idx, test_idx in tscv.split(X_scaled):
            X_train, X_test = X_scaled[train_idx], X_scaled[test_idx]
            y_train, y_test = y[train_idx], y[test_idx]

            oracle.model.fit(X_train, y_train)
            y_pred = oracle.model.predict(X_test)
            y_proba = oracle.model.predict_proba(X_test)[:, 1]

            accuracies.append(accuracy_score(y_test, y_pred))
            precisions.append(precision_score(y_test, y_pred, zero_division=0))
            recalls.append(recall_score(y_test, y_pred, zero_division=0))
            f1s.append(f1_score(y_test, y_pred, zero_division=0))
            try:
                aucs.append(roc_auc_score(y_test, y_proba))
            except ValueError:
                aucs.append(0.5)

        # Final fit on all data
        oracle.model.fit(X_scaled, y)

        # Calibrate probabilities
        oracle.calibrated_model = CalibratedClassifierCV(oracle.model, method='isotonic', cv=3)
        oracle.calibrated_model.fit(X_scaled, y)

        y_proba_full = oracle.calibrated_model.predict_proba(X_scaled)[:, 1]
        brier = brier_score_loss(y, y_proba_full)

        feature_importances = dict(zip(feature_cols, oracle.model.feature_importances_))

        # Increment version for live training
        version_parts = oracle.model_version.split('.') if oracle.model_version else ['1', '0', '0']
        new_minor = int(version_parts[1]) + 1 if len(version_parts) > 1 else 1
        new_version = f"{version_parts[0]}.{new_minor}.0"

        oracle.training_metrics = TrainingMetrics(
            accuracy=np.mean(accuracies),
            precision=np.mean(precisions),
            recall=np.mean(recalls),
            f1_score=np.mean(f1s),
            auc_roc=np.mean(aucs),
            brier_score=brier,
            win_rate_predicted=y_proba_full.mean(),
            win_rate_actual=y.mean(),
            total_samples=len(df),
            train_samples=int(len(df) * 0.8),
            test_samples=int(len(df) * 0.2),
            positive_samples=int(y.sum()),
            negative_samples=int(len(y) - y.sum()),
            feature_importances=feature_importances,
            training_date=datetime.now().isoformat(),
            model_version=new_version
        )

        oracle.is_trained = True
        oracle.model_version = new_version
        oracle._save_model()

        # Note: used_in_model_version column tracking removed for simplicity
        # Training outcomes are tracked by the oracle_trained_models table

        oracle.live_log.log("TRAIN_DONE", f"Auto-trained v{new_version} - Accuracy: {oracle.training_metrics.accuracy:.1%}", {
            "accuracy": oracle.training_metrics.accuracy,
            "auc_roc": oracle.training_metrics.auc_roc,
            "total_samples": oracle.training_metrics.total_samples,
            "model_version": new_version
        })

        logger.info(f"Oracle auto-trained successfully from {len(df)} live outcomes - v{new_version}")
        return oracle.training_metrics

    except Exception as e:
        oracle.live_log.log("TRAIN_ERROR", f"Auto-training failed: {e}", {})
        logger.error(f"Failed to train from live outcomes: {e}")
        import traceback
        traceback.print_exc()
        return None


def auto_train(
    threshold_outcomes: int = 100,
    force: bool = False
) -> Dict[str, Any]:
    """
    Automatic Oracle training trigger.

    Called by scheduler on:
    1. Weekly schedule (Sunday midnight CT)
    2. When threshold outcomes is reached (100+ new outcomes)

    Training strategy:
    1. If KRONOS backtest data available and no live outcomes -> Train from KRONOS
    2. If live outcomes available -> Train from live data (more accurate)
    3. If both available -> Train from live, use KRONOS as fallback

    Args:
        threshold_outcomes: Minimum new outcomes before retraining
        force: Force training even if threshold not met

    Returns:
        Dict with training status and results
    """
    oracle = get_oracle()
    oracle.live_log.log("AUTO_TRAIN_CHECK", "Checking if training needed", {
        "threshold": threshold_outcomes,
        "force": force
    })

    pending_count = get_pending_outcomes_count()

    result = {
        "triggered": False,
        "reason": "",
        "pending_outcomes": pending_count,
        "threshold": threshold_outcomes,
        "model_was_trained": oracle.is_trained,
        "training_metrics": None,
        "success": False
    }

    # Decide if training is needed
    needs_training = False
    reason = ""

    if force:
        needs_training = True
        reason = "Forced training requested"
    elif not oracle.is_trained:
        needs_training = True
        reason = "Model not trained - initial training"
    elif pending_count >= threshold_outcomes:
        needs_training = True
        reason = f"Threshold reached: {pending_count} >= {threshold_outcomes} new outcomes"

    if not needs_training:
        result["reason"] = f"No training needed - only {pending_count}/{threshold_outcomes} new outcomes"
        oracle.live_log.log("AUTO_TRAIN_SKIP", result["reason"], result)
        return result

    result["triggered"] = True
    result["reason"] = reason

    oracle.live_log.log("AUTO_TRAIN_START", reason, {"pending_outcomes": pending_count})

    # Try training from live outcomes first (more accurate)
    if pending_count >= 50:  # Need at least 50 for live training
        metrics = train_from_live_outcomes(min_samples=50)
        if metrics:
            result["training_metrics"] = metrics.__dict__
            result["success"] = True
            result["method"] = "live_outcomes"
            oracle.live_log.log("AUTO_TRAIN_SUCCESS", f"Trained from live outcomes - v{metrics.model_version}", result)
            return result

    # Try training from database backtest results
    metrics = train_from_database_backtests()
    if metrics:
        result["training_metrics"] = metrics.__dict__
        result["success"] = True
        result["method"] = "database_backtests"
        oracle.live_log.log("AUTO_TRAIN_SUCCESS", f"Trained from DB backtests - v{metrics.model_version}", result)
        return result

    # Fallback to KRONOS backtest data
    try:
        from backtest.autonomous_backtest_engine import get_backtester

        backtester = get_backtester()
        backtest_results = backtester.get_latest_results()

        if backtest_results and backtest_results.get('trades'):
            metrics = oracle.train_from_kronos(backtest_results)
            result["training_metrics"] = metrics.__dict__
            result["success"] = True
            result["method"] = "kronos_backtest"
            oracle.live_log.log("AUTO_TRAIN_SUCCESS", f"Trained from KRONOS - v{metrics.model_version}", result)
            return result
    except Exception as e:
        logger.warning(f"Could not train from KRONOS: {e}")

    result["reason"] = "Insufficient data for training"
    oracle.live_log.log("AUTO_TRAIN_FAIL", result["reason"], result)
    return result


def train_from_database_backtests(min_samples: int = 100) -> Optional[TrainingMetrics]:
    """
    Train Oracle from backtest results stored in database.

    This pulls data from zero_dte_backtest_trades table directly.
    More robust than KRONOS in-memory data as it persists across restarts.
    """
    if not DB_AVAILABLE:
        logger.warning("Database not available for training")
        return None

    oracle = get_oracle()
    oracle.live_log.log("TRAIN_DB_START", "Training from database backtest results", {})

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

        conn.close()

        if not rows or len(rows) < min_samples:
            oracle.live_log.log("TRAIN_DB_SKIP", f"Insufficient trades: {len(rows) if rows else 0} < {min_samples}", {})
            logger.info(f"Insufficient trades from database: {len(rows) if rows else 0} < {min_samples}")
            return None

        # Convert to trade dictionaries for train_from_kronos
        all_trades = []
        for row in rows:
            trade_date, spy_price, vix, iv, outcome, pnl, ret_pct, gex_net, gex_regime, put_strike, call_strike = row

            # Map outcome to win/loss
            is_win = outcome in ('MAX_PROFIT', 'PARTIAL_PROFIT')

            # Format trade to match extract_features_from_kronos expectations
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

        oracle.live_log.log("TRAIN_DB_DATA", f"Loaded {len(all_trades)} trades from database", {})

        # Format as KRONOS backtest results
        backtest_results = {'all_trades': all_trades}
        metrics = oracle.train_from_kronos(backtest_results, min_samples=min_samples)

        oracle.live_log.log("TRAIN_DB_DONE", f"Trained from {len(all_trades)} database trades", {
            "accuracy": metrics.accuracy,
            "total_samples": metrics.total_samples
        })

        return metrics

    except Exception as e:
        oracle.live_log.log("TRAIN_DB_ERROR", f"Database training failed: {e}", {})
        logger.error(f"Failed to train from database: {e}")
        import traceback
        traceback.print_exc()
        return None


if __name__ == "__main__":
    print("=" * 60)
    print("ORACLE - Multi-Strategy ML Advisor with Claude AI")
    print("=" * 60)

    oracle = get_oracle()
    print(f"Model loaded: {oracle.is_trained}")
    print(f"Version: {oracle.model_version}")
    print(f"Claude AI: {'ENABLED' if oracle.claude_available else 'DISABLED'}")

    # Demo predictions
    print("\n--- ARES Advice Demo ---")
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
    advice = oracle.get_ares_advice(context, use_gex_walls=True, use_claude_validation=True)
    print(f"Advice: {advice.advice.value}")
    print(f"Win Prob: {advice.win_probability:.1%}")
    print(f"Risk %: {advice.suggested_risk_pct:.1f}%")
    print(f"Reasoning: {advice.reasoning}")

    if advice.suggested_put_strike:
        print(f"GEX Put Strike: {advice.suggested_put_strike}")
        print(f"GEX Call Strike: {advice.suggested_call_strike}")

    # Demo Claude explanation
    if oracle.claude_available:
        print("\n--- Claude AI Explanation ---")
        explanation = oracle.explain_prediction(advice, context)
        print(explanation)

        print("\n--- Claude AI Market Analysis ---")
        analysis = oracle.get_claude_analysis(context)
        if analysis:
            print(f"Recommendation: {analysis.recommendation}")
            print(f"Confidence Adjustment: {analysis.confidence_adjustment:+.2f}")
            if analysis.risk_factors:
                print(f"Risk Factors: {', '.join(analysis.risk_factors)}")
            if analysis.opportunities:
                print(f"Opportunities: {', '.join(analysis.opportunities)}")
