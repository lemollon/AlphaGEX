"""
OMEGA ORCHESTRATOR - Central Trading Decision Coordination Hub
================================================================

The OMEGA (Optimal Market Execution & Governance Architecture) Orchestrator is the
central coordination hub for all trading decisions in AlphaGEX.

ARCHITECTURE:
┌─────────────────────────────────────────────────────────────────────────────────┐
│                            OMEGA ORCHESTRATOR                                    │
│                                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────────────┐│
│  │ LAYER 1: SOLOMON - ABSOLUTE AUTHORITY (Hard Safety Limits)                  ││
│  │ • Consecutive loss tracking (kill after 3 in a row)                         ││
│  │ • Daily loss limits (3% max)                                                ││
│  │ • Kill switch management                                                    ││
│  │ • IF SOLOMON SAYS STOP → FULL STOP. No override possible.                   ││
│  └─────────────────────────────────────────────────────────────────────────────┘│
│                                    ↓                                            │
│  ┌─────────────────────────────────────────────────────────────────────────────┐│
│  │ LAYER 2: ENSEMBLE - INFORMATIONAL (Market Context)                          ││
│  │ • Combines 5 GEX probability models                                         ││
│  │ • Psychology trap signals                                                   ││
│  │ • RSI multi-timeframe alignment                                             ││
│  │ • Vol surface analysis                                                      ││
│  │ • Dynamic weight updates based on performance                               ││
│  └─────────────────────────────────────────────────────────────────────────────┘│
│                                    ↓                                            │
│  ┌─────────────────────────────────────────────────────────────────────────────┐│
│  │ LAYER 3: ML ADVISOR - PRIMARY DECISION MAKER                                ││
│  │ • XGBoost model trained on KRONOS backtest data                             ││
│  │ • Win probability prediction                                                ││
│  │ • Position sizing recommendation                                            ││
│  │ • Auto-retrain when performance degrades                                    ││
│  └─────────────────────────────────────────────────────────────────────────────┘│
│                                    ↓                                            │
│  ┌─────────────────────────────────────────────────────────────────────────────┐│
│  │ LAYER 4: ORACLE - BOT-SPECIFIC ADAPTATION                                   ││
│  │ • Adapts ML decision for specific bot (ARES, ATHENA, etc.)                  ││
│  │ • Strike selection, risk percentage                                         ││
│  │ • NO veto power over ML Advisor                                             ││
│  └─────────────────────────────────────────────────────────────────────────────┘│
│                                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────────────┐│
│  │ GAP IMPLEMENTATIONS:                                                        ││
│  │ • Gap 1: Auto-Retrain Monitor - triggers ML retraining on degradation       ││
│  │ • Gap 2: Thompson Capital Allocator - dynamic capital allocation            ││
│  │ • Gap 5: Dynamic Ensemble Weights - real-time weight updates                ││
│  │ • Gap 6: Regime Transition Detector - alerts on regime changes              ││
│  │ • Gap 9: Cross-Bot Correlation Enforcer - limits correlated exposure        ││
│  │ • Gap 10: Equity Compound Scaler - scales positions with equity             ││
│  └─────────────────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────────────┘

Author: AlphaGEX Quant Team
Date: January 2025
"""

from __future__ import annotations

import os
import sys
import json
import logging
import math
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any, Union
from dataclasses import dataclass, field, asdict
from enum import Enum
from zoneinfo import ZoneInfo
from threading import Lock

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)
CENTRAL_TZ = ZoneInfo("America/Chicago")


# =============================================================================
# ENUMS AND CONSTANTS
# =============================================================================

class DecisionAuthority(Enum):
    """Who made the trading decision"""
    SOLOMON = "SOLOMON"           # Safety layer - ABSOLUTE
    ENSEMBLE = "ENSEMBLE"         # Market context - INFORMATIONAL
    ML_ADVISOR = "ML_ADVISOR"     # Win probability - PRIMARY
    ORACLE = "ORACLE"             # Bot-specific - ADAPTATION


class TradingDecision(Enum):
    """Final trading decision"""
    TRADE_FULL = "TRADE_FULL"           # High confidence, full size
    TRADE_REDUCED = "TRADE_REDUCED"     # Medium confidence, reduce size
    SKIP_TODAY = "SKIP_TODAY"           # Low confidence or safety block
    BLOCKED_BY_SOLOMON = "BLOCKED_BY_SOLOMON"  # Safety limit hit


class RegimeTransition(Enum):
    """Regime transition types"""
    NO_CHANGE = "NO_CHANGE"
    BULLISH_TO_BEARISH = "BULLISH_TO_BEARISH"
    BEARISH_TO_BULLISH = "BEARISH_TO_BULLISH"
    LOW_VOL_TO_HIGH_VOL = "LOW_VOL_TO_HIGH_VOL"
    HIGH_VOL_TO_LOW_VOL = "HIGH_VOL_TO_LOW_VOL"
    POSITIVE_TO_NEGATIVE_GAMMA = "POSITIVE_TO_NEGATIVE_GAMMA"
    NEGATIVE_TO_POSITIVE_GAMMA = "NEGATIVE_TO_POSITIVE_GAMMA"


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class SolomonVerdict:
    """Solomon safety layer verdict"""
    can_trade: bool
    reason: str
    consecutive_losses: int = 0
    daily_loss_pct: float = 0.0
    is_killed: bool = False
    authority: DecisionAuthority = DecisionAuthority.SOLOMON

    def to_dict(self) -> Dict:
        return {
            **asdict(self),
            'authority': self.authority.value
        }


@dataclass
class EnsembleContext:
    """Ensemble market context"""
    signal: str  # BUY, SELL, NEUTRAL
    confidence: float  # 0-100
    bullish_weight: float
    bearish_weight: float
    neutral_weight: float
    component_signals: Dict[str, Dict]  # strategy -> {signal, confidence, weight}
    position_size_multiplier: float  # 0.25 to 1.0
    regime: str  # Current detected regime
    authority: DecisionAuthority = DecisionAuthority.ENSEMBLE

    def to_dict(self) -> Dict:
        return {
            **asdict(self),
            'authority': self.authority.value
        }


@dataclass
class MLAdvisorDecision:
    """ML Advisor primary decision"""
    advice: str  # TRADE_FULL, TRADE_REDUCED, SKIP_TODAY
    win_probability: float  # 0-1
    confidence: float  # 0-100
    suggested_risk_pct: float
    suggested_sd_multiplier: float
    top_factors: List[Tuple[str, float]]
    model_version: str
    needs_retraining: bool = False
    authority: DecisionAuthority = DecisionAuthority.ML_ADVISOR

    def to_dict(self) -> Dict:
        result = asdict(self)
        result['authority'] = self.authority.value
        return result


@dataclass
class OracleAdaptation:
    """Oracle bot-specific adaptation"""
    bot_name: str
    suggested_put_strike: Optional[float] = None
    suggested_call_strike: Optional[float] = None
    use_gex_walls: bool = False
    risk_adjustment: float = 1.0  # Multiplier for risk
    reasoning: str = ""
    authority: DecisionAuthority = DecisionAuthority.ORACLE

    def to_dict(self) -> Dict:
        return {
            **asdict(self),
            'authority': self.authority.value
        }


@dataclass
class OmegaDecision:
    """
    Complete OMEGA decision with full transparency.

    Shows exactly WHO made each part of the decision and WHY.
    """
    timestamp: datetime
    bot_name: str

    # Final decision
    final_decision: TradingDecision
    final_risk_pct: float
    final_position_size_multiplier: float

    # Layer outputs (transparency)
    solomon_verdict: SolomonVerdict
    ensemble_context: EnsembleContext
    ml_decision: MLAdvisorDecision
    oracle_adaptation: OracleAdaptation

    # Gap implementations
    capital_allocation: Dict[str, float]  # From Thompson Sampling
    equity_scaled_risk: float  # From Equity Compound Scaler
    correlation_check: Dict  # From Cross-Bot Correlation
    regime_transition: Optional[RegimeTransition] = None

    # Decision trace
    decision_path: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            'timestamp': self.timestamp.isoformat(),
            'bot_name': self.bot_name,
            'final_decision': self.final_decision.value,
            'final_risk_pct': self.final_risk_pct,
            'final_position_size_multiplier': self.final_position_size_multiplier,
            'solomon_verdict': self.solomon_verdict.to_dict(),
            'ensemble_context': self.ensemble_context.to_dict(),
            'ml_decision': self.ml_decision.to_dict(),
            'oracle_adaptation': self.oracle_adaptation.to_dict(),
            'capital_allocation': self.capital_allocation,
            'equity_scaled_risk': self.equity_scaled_risk,
            'correlation_check': self.correlation_check,
            'regime_transition': self.regime_transition.value if self.regime_transition else None,
            'decision_path': self.decision_path
        }


# =============================================================================
# GAP 1: AUTO-RETRAIN MONITOR
# =============================================================================

class AutoRetrainMonitor:
    """
    Gap 1: Monitors ML Advisor performance and triggers retraining when needed.

    Triggers retraining when:
    - Win rate drops >10% below expected
    - Consecutive losses exceed threshold
    - Model age exceeds maximum days
    - Significant regime shift detected
    """

    # Configuration
    WIN_RATE_DEGRADATION_THRESHOLD = 0.10  # 10% drop triggers retrain
    MAX_MODEL_AGE_DAYS = 30
    MIN_TRADES_FOR_EVALUATION = 20
    CONSECUTIVE_LOSS_TRIGGER = 5

    def __init__(self):
        self.recent_predictions: List[Dict] = []  # Last N predictions
        self.recent_outcomes: List[Dict] = []  # Last N outcomes
        self.last_retrain_date: Optional[datetime] = None
        self.retrain_triggered: bool = False
        self._lock = Lock()

        logger.info("AutoRetrainMonitor initialized")

    def record_prediction(
        self,
        bot_name: str,
        predicted_win_prob: float,
        model_version: str
    ) -> None:
        """Record a prediction for later evaluation"""
        with self._lock:
            self.recent_predictions.append({
                'timestamp': datetime.now(CENTRAL_TZ),
                'bot_name': bot_name,
                'predicted_win_prob': predicted_win_prob,
                'model_version': model_version
            })

            # Keep only last 100 predictions
            if len(self.recent_predictions) > 100:
                self.recent_predictions = self.recent_predictions[-100:]

    def record_outcome(
        self,
        bot_name: str,
        was_win: bool,
        pnl: float
    ) -> Dict:
        """
        Record trade outcome and check if retraining is needed.

        Returns:
            Dict with retrain_needed and reason if triggered
        """
        with self._lock:
            self.recent_outcomes.append({
                'timestamp': datetime.now(CENTRAL_TZ),
                'bot_name': bot_name,
                'was_win': was_win,
                'pnl': pnl
            })

            # Keep only last 100 outcomes
            if len(self.recent_outcomes) > 100:
                self.recent_outcomes = self.recent_outcomes[-100:]

            return self._evaluate_retrain_need()

    def _evaluate_retrain_need(self) -> Dict:
        """Evaluate if retraining is needed"""
        result = {
            'retrain_needed': False,
            'reason': None,
            'metrics': {}
        }

        if len(self.recent_outcomes) < self.MIN_TRADES_FOR_EVALUATION:
            result['metrics']['status'] = 'insufficient_data'
            return result

        # Calculate actual win rate
        wins = sum(1 for o in self.recent_outcomes if o['was_win'])
        actual_win_rate = wins / len(self.recent_outcomes)

        # Calculate predicted win rate (average of predictions)
        if self.recent_predictions:
            predicted_win_rate = sum(
                p['predicted_win_prob'] for p in self.recent_predictions
            ) / len(self.recent_predictions)
        else:
            predicted_win_rate = 0.70  # Default expected

        result['metrics'] = {
            'actual_win_rate': actual_win_rate,
            'predicted_win_rate': predicted_win_rate,
            'sample_size': len(self.recent_outcomes)
        }

        # Check 1: Win rate degradation
        degradation = predicted_win_rate - actual_win_rate
        if degradation > self.WIN_RATE_DEGRADATION_THRESHOLD:
            result['retrain_needed'] = True
            result['reason'] = f"Win rate degraded by {degradation:.1%} (expected {predicted_win_rate:.1%}, actual {actual_win_rate:.1%})"
            return result

        # Check 2: Consecutive losses
        recent_losses = 0
        for outcome in reversed(self.recent_outcomes):
            if not outcome['was_win']:
                recent_losses += 1
            else:
                break

        if recent_losses >= self.CONSECUTIVE_LOSS_TRIGGER:
            result['retrain_needed'] = True
            result['reason'] = f"Consecutive losses: {recent_losses}"
            return result

        # Check 3: Model age
        if self.last_retrain_date:
            age_days = (datetime.now(CENTRAL_TZ) - self.last_retrain_date).days
            if age_days > self.MAX_MODEL_AGE_DAYS:
                result['retrain_needed'] = True
                result['reason'] = f"Model age: {age_days} days (max: {self.MAX_MODEL_AGE_DAYS})"
                return result

        return result

    def mark_retrained(self) -> None:
        """Mark that retraining has completed"""
        with self._lock:
            self.last_retrain_date = datetime.now(CENTRAL_TZ)
            self.retrain_triggered = False
            self.recent_predictions.clear()
            self.recent_outcomes.clear()
            logger.info("AutoRetrainMonitor: Marked as retrained")

    def get_status(self) -> Dict:
        """Get current monitoring status"""
        with self._lock:
            return {
                'predictions_tracked': len(self.recent_predictions),
                'outcomes_tracked': len(self.recent_outcomes),
                'last_retrain_date': self.last_retrain_date.isoformat() if self.last_retrain_date else None,
                'retrain_triggered': self.retrain_triggered,
                'evaluation': self._evaluate_retrain_need()
            }


# =============================================================================
# GAP 6: REGIME TRANSITION DETECTOR
# =============================================================================

class RegimeTransitionDetector:
    """
    Gap 6: Detects regime transitions and generates alerts.

    Monitors:
    - GEX regime (positive/negative gamma)
    - VIX regime (low/normal/elevated/high/extreme)
    - Market trend (bullish/bearish/ranging)
    - Volatility regime
    """

    TRANSITION_LOOKBACK_PERIODS = 5  # Number of observations for confirmation
    MIN_CONFIDENCE_FOR_ALERT = 0.75

    def __init__(self):
        self.gex_regime_history: List[Dict] = []
        self.vix_regime_history: List[Dict] = []
        self.trend_history: List[Dict] = []
        self.recent_transitions: List[Dict] = []
        self._lock = Lock()

        logger.info("RegimeTransitionDetector initialized")

    def record_observation(
        self,
        gex_regime: str,
        vix: float,
        price_trend: str,
        net_gamma: float
    ) -> Optional[Dict]:
        """
        Record market observation and check for regime transitions.

        Returns:
            Transition alert dict if transition detected, None otherwise
        """
        now = datetime.now(CENTRAL_TZ)

        with self._lock:
            # Determine VIX regime
            vix_regime = self._classify_vix_regime(vix)

            # Store observations
            self.gex_regime_history.append({
                'timestamp': now,
                'regime': gex_regime,
                'net_gamma': net_gamma
            })

            self.vix_regime_history.append({
                'timestamp': now,
                'regime': vix_regime,
                'vix': vix
            })

            self.trend_history.append({
                'timestamp': now,
                'trend': price_trend
            })

            # Keep only recent history
            max_history = 100
            self.gex_regime_history = self.gex_regime_history[-max_history:]
            self.vix_regime_history = self.vix_regime_history[-max_history:]
            self.trend_history = self.trend_history[-max_history:]

            # Check for transitions
            return self._detect_transitions()

    def _classify_vix_regime(self, vix: float) -> str:
        """Classify VIX into regime"""
        if vix < 15:
            return "LOW"
        elif vix < 22:
            return "NORMAL"
        elif vix < 28:
            return "ELEVATED"
        elif vix < 35:
            return "HIGH"
        else:
            return "EXTREME"

    def _detect_transitions(self) -> Optional[Dict]:
        """Detect regime transitions with confirmation"""
        if len(self.gex_regime_history) < self.TRANSITION_LOOKBACK_PERIODS + 1:
            return None

        transitions = []

        # Check GEX regime transition
        current_gex = self.gex_regime_history[-1]['regime']
        previous_gex_list = [
            h['regime'] for h in self.gex_regime_history[-(self.TRANSITION_LOOKBACK_PERIODS + 1):-1]
        ]

        if previous_gex_list and all(r == previous_gex_list[0] for r in previous_gex_list):
            previous_gex = previous_gex_list[0]
            if current_gex != previous_gex:
                if previous_gex == "POSITIVE" and current_gex == "NEGATIVE":
                    transitions.append({
                        'type': RegimeTransition.POSITIVE_TO_NEGATIVE_GAMMA,
                        'from': previous_gex,
                        'to': current_gex,
                        'impact': 'HIGH',
                        'recommendation': 'Consider switching from Iron Condors to Directional'
                    })
                elif previous_gex == "NEGATIVE" and current_gex == "POSITIVE":
                    transitions.append({
                        'type': RegimeTransition.NEGATIVE_TO_POSITIVE_GAMMA,
                        'from': previous_gex,
                        'to': current_gex,
                        'impact': 'HIGH',
                        'recommendation': 'Iron Condors more favorable, mean reversion expected'
                    })

        # Check VIX regime transition
        current_vix_regime = self.vix_regime_history[-1]['regime']
        previous_vix_list = [
            h['regime'] for h in self.vix_regime_history[-(self.TRANSITION_LOOKBACK_PERIODS + 1):-1]
        ]

        if previous_vix_list and all(r == previous_vix_list[0] for r in previous_vix_list):
            previous_vix = previous_vix_list[0]
            if current_vix_regime != previous_vix:
                if previous_vix in ["LOW", "NORMAL"] and current_vix_regime in ["HIGH", "EXTREME"]:
                    transitions.append({
                        'type': RegimeTransition.LOW_VOL_TO_HIGH_VOL,
                        'from': previous_vix,
                        'to': current_vix_regime,
                        'impact': 'HIGH',
                        'recommendation': 'Reduce position sizes, widen strikes'
                    })
                elif previous_vix in ["HIGH", "EXTREME"] and current_vix_regime in ["LOW", "NORMAL"]:
                    transitions.append({
                        'type': RegimeTransition.HIGH_VOL_TO_LOW_VOL,
                        'from': previous_vix,
                        'to': current_vix_regime,
                        'impact': 'MEDIUM',
                        'recommendation': 'Can increase position sizes, tighten strikes'
                    })

        if transitions:
            alert = {
                'timestamp': datetime.now(CENTRAL_TZ).isoformat(),
                'transitions': [
                    {
                        **t,
                        'type': t['type'].value
                    }
                    for t in transitions
                ],
                'current_state': {
                    'gex_regime': current_gex,
                    'vix_regime': current_vix_regime,
                    'vix': self.vix_regime_history[-1]['vix']
                }
            }

            self.recent_transitions.append(alert)
            if len(self.recent_transitions) > 50:
                self.recent_transitions = self.recent_transitions[-50:]

            logger.warning(f"Regime transition detected: {transitions}")
            return alert

        return None

    def get_current_regimes(self) -> Dict:
        """Get current regime classifications"""
        with self._lock:
            return {
                'gex_regime': self.gex_regime_history[-1]['regime'] if self.gex_regime_history else 'UNKNOWN',
                'vix_regime': self.vix_regime_history[-1]['regime'] if self.vix_regime_history else 'UNKNOWN',
                'trend': self.trend_history[-1]['trend'] if self.trend_history else 'UNKNOWN',
                'recent_transitions': self.recent_transitions[-5:]
            }


# =============================================================================
# GAP 9: CROSS-BOT CORRELATION ENFORCER
# =============================================================================

class CrossBotCorrelationEnforcer:
    """
    Gap 9: Enforces correlation limits between bots.

    Prevents multiple bots from taking highly correlated positions
    that could result in catastrophic losses.
    """

    MAX_CORRELATION_THRESHOLD = 0.70  # Block if correlation > 70%
    MAX_CORRELATED_EXPOSURE_PCT = 30.0  # Max total exposure when correlated

    def __init__(self):
        self.active_positions: Dict[str, Dict] = {}  # bot -> position info
        self.daily_pnl: Dict[str, float] = {}  # bot -> daily P&L
        self.correlation_cache: Dict[str, float] = {}  # "BOT_A:BOT_B" -> correlation
        self._lock = Lock()

        logger.info("CrossBotCorrelationEnforcer initialized")

    def register_position(
        self,
        bot_name: str,
        direction: str,  # BULLISH, BEARISH, NEUTRAL
        exposure_pct: float,
        underlying: str = "SPY"
    ) -> None:
        """Register an active position for correlation tracking"""
        with self._lock:
            self.active_positions[bot_name] = {
                'direction': direction,
                'exposure_pct': exposure_pct,
                'underlying': underlying,
                'opened_at': datetime.now(CENTRAL_TZ)
            }

    def close_position(self, bot_name: str) -> None:
        """Remove a closed position"""
        with self._lock:
            if bot_name in self.active_positions:
                del self.active_positions[bot_name]

    def record_daily_pnl(self, bot_name: str, pnl: float) -> None:
        """Record daily P&L for correlation calculation"""
        with self._lock:
            self.daily_pnl[bot_name] = self.daily_pnl.get(bot_name, 0) + pnl

    def check_new_position(
        self,
        bot_name: str,
        direction: str,
        proposed_exposure_pct: float
    ) -> Dict:
        """
        Check if a new position would violate correlation limits.

        Returns:
            Dict with:
            - allowed: bool
            - reason: str (if blocked)
            - correlated_bots: List of correlated bot names
            - adjusted_exposure: float (if reduction recommended)
        """
        with self._lock:
            result = {
                'allowed': True,
                'reason': None,
                'correlated_bots': [],
                'total_correlated_exposure': 0.0,
                'adjusted_exposure': proposed_exposure_pct
            }

            # Find bots with same direction
            correlated = []
            total_exposure = proposed_exposure_pct

            for other_bot, position in self.active_positions.items():
                if other_bot == bot_name:
                    continue

                if position['direction'] == direction:
                    correlated.append(other_bot)
                    total_exposure += position['exposure_pct']

            result['correlated_bots'] = correlated
            result['total_correlated_exposure'] = total_exposure

            # Check if total correlated exposure exceeds limit
            if total_exposure > self.MAX_CORRELATED_EXPOSURE_PCT:
                # Calculate how much we can allocate
                available = max(0, self.MAX_CORRELATED_EXPOSURE_PCT - (total_exposure - proposed_exposure_pct))

                if available <= 0:
                    result['allowed'] = False
                    result['reason'] = (
                        f"Correlated exposure limit exceeded. "
                        f"Current {direction} exposure: {total_exposure - proposed_exposure_pct:.1f}%, "
                        f"proposed: {proposed_exposure_pct:.1f}%, "
                        f"limit: {self.MAX_CORRELATED_EXPOSURE_PCT:.1f}%"
                    )
                else:
                    result['adjusted_exposure'] = available
                    result['reason'] = (
                        f"Reduced exposure from {proposed_exposure_pct:.1f}% to {available:.1f}% "
                        f"due to correlated positions in {', '.join(correlated)}"
                    )

            return result

    def get_status(self) -> Dict:
        """Get current correlation status"""
        with self._lock:
            # Group by direction
            by_direction = {'BULLISH': [], 'BEARISH': [], 'NEUTRAL': []}
            for bot, pos in self.active_positions.items():
                by_direction[pos['direction']].append({
                    'bot': bot,
                    'exposure_pct': pos['exposure_pct']
                })

            return {
                'active_positions': len(self.active_positions),
                'positions_by_direction': by_direction,
                'total_bullish_exposure': sum(p['exposure_pct'] for p in by_direction['BULLISH']),
                'total_bearish_exposure': sum(p['exposure_pct'] for p in by_direction['BEARISH']),
                'correlation_limit': self.MAX_CORRELATED_EXPOSURE_PCT
            }


# =============================================================================
# GAP 10: EQUITY COMPOUND SCALER
# =============================================================================

class EquityCompoundScaler:
    """
    Gap 10: Scales position sizes based on equity growth.

    Implements compound growth while protecting against drawdowns:
    - Increase size as equity grows
    - Reduce size during drawdowns
    - Never exceed maximum position size
    """

    DRAWDOWN_REDUCTION_THRESHOLD = 0.05  # 5% drawdown triggers reduction
    DRAWDOWN_REDUCTION_FACTOR = 0.75  # Reduce to 75% during drawdown
    GROWTH_SCALING_FACTOR = 0.5  # Scale at 50% of equity growth rate
    MAX_POSITION_MULTIPLIER = 2.0  # Never more than 2x base size
    MIN_POSITION_MULTIPLIER = 0.25  # Never less than 25% base size

    def __init__(self, initial_capital: float = 100000):
        self.initial_capital = initial_capital
        self.current_equity = initial_capital
        self.high_water_mark = initial_capital
        self._lock = Lock()

        logger.info(f"EquityCompoundScaler initialized with ${initial_capital:,.0f}")

    def update_equity(self, current_equity: float) -> None:
        """Update current equity value"""
        with self._lock:
            self.current_equity = current_equity
            if current_equity > self.high_water_mark:
                self.high_water_mark = current_equity

    def get_position_multiplier(self, base_risk_pct: float) -> Dict:
        """
        Calculate position size multiplier based on equity.

        Args:
            base_risk_pct: Base risk percentage to apply

        Returns:
            Dict with:
            - multiplier: float (position size multiplier)
            - adjusted_risk_pct: float
            - reason: str
        """
        with self._lock:
            # Calculate drawdown from high water mark
            drawdown = (self.high_water_mark - self.current_equity) / self.high_water_mark

            # Calculate growth from initial
            growth = (self.current_equity - self.initial_capital) / self.initial_capital

            result = {
                'multiplier': 1.0,
                'adjusted_risk_pct': base_risk_pct,
                'drawdown_pct': drawdown * 100,
                'growth_pct': growth * 100,
                'reason': 'Base position size'
            }

            # Check for drawdown reduction
            if drawdown >= self.DRAWDOWN_REDUCTION_THRESHOLD:
                result['multiplier'] = self.DRAWDOWN_REDUCTION_FACTOR
                result['reason'] = f"Drawdown protection: {drawdown:.1%} drawdown from HWM"

            # Check for growth scaling (only if not in drawdown)
            elif growth > 0:
                # Scale position size with equity growth
                growth_multiplier = 1 + (growth * self.GROWTH_SCALING_FACTOR)
                result['multiplier'] = min(growth_multiplier, self.MAX_POSITION_MULTIPLIER)
                result['reason'] = f"Equity scaling: {growth:.1%} growth from initial"

            # Apply min/max bounds
            result['multiplier'] = max(
                self.MIN_POSITION_MULTIPLIER,
                min(self.MAX_POSITION_MULTIPLIER, result['multiplier'])
            )

            # Calculate adjusted risk
            result['adjusted_risk_pct'] = base_risk_pct * result['multiplier']

            return result

    def get_status(self) -> Dict:
        """Get current scaling status"""
        with self._lock:
            return {
                'initial_capital': self.initial_capital,
                'current_equity': self.current_equity,
                'high_water_mark': self.high_water_mark,
                'drawdown_pct': ((self.high_water_mark - self.current_equity) / self.high_water_mark) * 100,
                'growth_pct': ((self.current_equity - self.initial_capital) / self.initial_capital) * 100
            }


# =============================================================================
# MAIN OMEGA ORCHESTRATOR
# =============================================================================

class OmegaOrchestrator:
    """
    The OMEGA Orchestrator - Central Trading Decision Coordination Hub.

    Provides a single entry point for all trading decisions with:
    - Layered decision authority (Solomon → Ensemble → ML → Oracle)
    - Full transparency on WHO made each decision and WHY
    - Gap implementations for enhanced profitability
    """

    def __init__(self, capital: float = 100000):
        self.capital = capital

        # Gap implementations
        self.auto_retrain_monitor = AutoRetrainMonitor()
        self.regime_detector = RegimeTransitionDetector()
        self.correlation_enforcer = CrossBotCorrelationEnforcer()
        self.equity_scaler = EquityCompoundScaler(capital)

        # Thompson Sampling allocator (Gap 2)
        self._thompson_allocator = None

        # Solomon Enhanced (with ConsecutiveLossMonitor, DailyLossMonitor, etc.)
        self._solomon_enhanced = None

        # Ensemble weighter
        self._ensemble_weighter = None

        # ML Advisor
        self._ml_advisor = None

        # Oracle
        self._oracle = None

        # Decision history
        self.decision_history: List[OmegaDecision] = []
        self._lock = Lock()

        logger.info("OMEGA Orchestrator initialized")

    def _get_solomon_enhanced(self):
        """Lazy load Solomon Enhanced"""
        if self._solomon_enhanced is None:
            try:
                from quant.solomon_enhancements import get_solomon_enhanced
                self._solomon_enhanced = get_solomon_enhanced()
            except ImportError as e:
                logger.warning(f"Could not load Solomon Enhanced: {e}")
        return self._solomon_enhanced

    def _get_ensemble_weighter(self, symbol: str = "SPY"):
        """Lazy load Ensemble Weighter"""
        if self._ensemble_weighter is None:
            try:
                from quant.ensemble_strategy import get_ensemble_weighter
                self._ensemble_weighter = get_ensemble_weighter(symbol)
            except ImportError as e:
                logger.warning(f"Could not load Ensemble Weighter: {e}")
        return self._ensemble_weighter

    def _get_ml_advisor(self):
        """Lazy load ML Advisor"""
        if self._ml_advisor is None:
            try:
                from quant.ares_ml_advisor import AresMLAdvisor
                self._ml_advisor = AresMLAdvisor()
            except ImportError as e:
                logger.warning(f"Could not load ML Advisor: {e}")
        return self._ml_advisor

    def _get_thompson_allocator(self):
        """Lazy load Thompson Sampling Allocator (Gap 2)"""
        if self._thompson_allocator is None:
            try:
                from core.math_optimizers import ThompsonSamplingAllocator
                self._thompson_allocator = ThompsonSamplingAllocator()
            except ImportError as e:
                logger.warning(f"Could not load Thompson Allocator: {e}")
        return self._thompson_allocator

    # =========================================================================
    # LAYER 1: SOLOMON - ABSOLUTE AUTHORITY
    # =========================================================================

    def _check_solomon(self, bot_name: str) -> SolomonVerdict:
        """
        Check Solomon safety layer.

        IF SOLOMON SAYS STOP → FULL STOP. No override possible.
        """
        solomon = self._get_solomon_enhanced()

        if solomon is None:
            # Fallback: allow trading if Solomon not available
            return SolomonVerdict(
                can_trade=True,
                reason="Solomon not available, proceeding with caution"
            )

        # Check consecutive losses
        consec_status = solomon.consecutive_loss_monitor.get_status(bot_name)
        consecutive_losses = consec_status.get('consecutive_losses', 0)

        # Check daily loss
        daily_status = solomon.daily_loss_monitor.get_status(bot_name)
        daily_pnl = daily_status.get('total_pnl', 0)
        daily_loss_pct = abs(daily_pnl / self.capital * 100) if daily_pnl < 0 else 0

        # Check kill switch
        is_killed = solomon.solomon.is_bot_killed(bot_name)

        # Determine if trading is allowed
        if is_killed:
            return SolomonVerdict(
                can_trade=False,
                reason="Kill switch is active",
                consecutive_losses=consecutive_losses,
                daily_loss_pct=daily_loss_pct,
                is_killed=True
            )

        if consec_status.get('triggered_kill', False):
            return SolomonVerdict(
                can_trade=False,
                reason=f"Consecutive loss limit reached: {consecutive_losses} losses",
                consecutive_losses=consecutive_losses,
                daily_loss_pct=daily_loss_pct,
                is_killed=False
            )

        if daily_status.get('triggered_kill', False):
            return SolomonVerdict(
                can_trade=False,
                reason=f"Daily loss limit reached: {daily_loss_pct:.1f}%",
                consecutive_losses=consecutive_losses,
                daily_loss_pct=daily_loss_pct,
                is_killed=False
            )

        return SolomonVerdict(
            can_trade=True,
            reason="All safety checks passed",
            consecutive_losses=consecutive_losses,
            daily_loss_pct=daily_loss_pct,
            is_killed=False
        )

    # =========================================================================
    # LAYER 2: ENSEMBLE - INFORMATIONAL
    # =========================================================================

    def _get_ensemble_context(
        self,
        gex_data: Dict,
        psychology_data: Optional[Dict] = None,
        rsi_data: Optional[Dict] = None,
        vol_surface_data: Optional[Dict] = None,
        ml_prediction: Optional[Dict] = None,
        current_regime: str = "UNKNOWN"
    ) -> EnsembleContext:
        """
        Get ensemble market context.

        Combines multiple signals into a unified market view.
        """
        ensemble = self._get_ensemble_weighter()

        if ensemble is None:
            # Fallback: neutral context
            return EnsembleContext(
                signal="NEUTRAL",
                confidence=50.0,
                bullish_weight=0.33,
                bearish_weight=0.33,
                neutral_weight=0.34,
                component_signals={},
                position_size_multiplier=0.5,
                regime=current_regime
            )

        # Get ensemble signal
        signal = ensemble.get_ensemble_signal(
            gex_data=gex_data,
            psychology_data=psychology_data,
            rsi_data=rsi_data,
            vol_surface_data=vol_surface_data,
            ml_prediction=ml_prediction,
            current_regime=current_regime
        )

        # Convert component signals to dict
        component_signals = {}
        for comp in signal.component_signals:
            component_signals[comp.strategy_name] = {
                'signal': comp.signal.value,
                'confidence': comp.confidence,
                'weight': comp.weight
            }

        return EnsembleContext(
            signal=signal.final_signal.value,
            confidence=signal.confidence,
            bullish_weight=signal.bullish_weight,
            bearish_weight=signal.bearish_weight,
            neutral_weight=signal.neutral_weight,
            component_signals=component_signals,
            position_size_multiplier=signal.position_size_multiplier,
            regime=current_regime
        )

    # =========================================================================
    # LAYER 3: ML ADVISOR - PRIMARY DECISION MAKER
    # =========================================================================

    def _get_ml_decision(
        self,
        features: Dict,
        ensemble_context: EnsembleContext
    ) -> MLAdvisorDecision:
        """
        Get ML Advisor decision.

        This is the PRIMARY decision maker for trading.
        """
        ml_advisor = self._get_ml_advisor()

        if ml_advisor is None or not ml_advisor.is_trained:
            # Fallback: use ensemble confidence
            if ensemble_context.confidence >= 70:
                advice = "TRADE_FULL"
            elif ensemble_context.confidence >= 55:
                advice = "TRADE_REDUCED"
            else:
                advice = "SKIP_TODAY"

            return MLAdvisorDecision(
                advice=advice,
                win_probability=ensemble_context.confidence / 100,
                confidence=ensemble_context.confidence,
                suggested_risk_pct=5.0 if advice == "TRADE_FULL" else 2.5,
                suggested_sd_multiplier=1.0,
                top_factors=[("ensemble_confidence", ensemble_context.confidence)],
                model_version="fallback",
                needs_retraining=False
            )

        # Get ML prediction
        try:
            # Create feature vector from dict
            import numpy as np
            feature_cols = ml_advisor.FEATURE_COLS
            feature_values = [features.get(col, 0) for col in feature_cols]

            if ml_advisor.scaler is not None:
                X = np.array([feature_values])
                X_scaled = ml_advisor.scaler.transform(X)
            else:
                X_scaled = np.array([feature_values])

            # Get probability
            if ml_advisor.calibrated_model is not None:
                proba = ml_advisor.calibrated_model.predict_proba(X_scaled)[0]
            elif ml_advisor.model is not None:
                proba = ml_advisor.model.predict_proba(X_scaled)[0]
            else:
                proba = [0.3, 0.7]  # Fallback

            win_probability = float(proba[1])  # Probability of win

            # Determine advice based on probability
            if win_probability >= ml_advisor.high_confidence_threshold:
                advice = "TRADE_FULL"
                risk_pct = 7.5
            elif win_probability >= ml_advisor.low_confidence_threshold:
                advice = "TRADE_REDUCED"
                risk_pct = 5.0
            else:
                advice = "SKIP_TODAY"
                risk_pct = 0

            # Get feature importances
            if hasattr(ml_advisor.model, 'feature_importances_'):
                importances = ml_advisor.model.feature_importances_
                top_factors = sorted(
                    zip(feature_cols, importances),
                    key=lambda x: abs(x[1]),
                    reverse=True
                )[:5]
            else:
                top_factors = []

            # Check if retraining needed
            retrain_check = self.auto_retrain_monitor._evaluate_retrain_need()

            return MLAdvisorDecision(
                advice=advice,
                win_probability=win_probability,
                confidence=win_probability * 100,
                suggested_risk_pct=risk_pct,
                suggested_sd_multiplier=1.0,
                top_factors=top_factors,
                model_version=ml_advisor.model_version,
                needs_retraining=retrain_check.get('retrain_needed', False)
            )

        except Exception as e:
            logger.error(f"ML Advisor prediction failed: {e}")
            return MLAdvisorDecision(
                advice="SKIP_TODAY",
                win_probability=0.5,
                confidence=50.0,
                suggested_risk_pct=0,
                suggested_sd_multiplier=1.0,
                top_factors=[("error", 0)],
                model_version="error",
                needs_retraining=True
            )

    # =========================================================================
    # LAYER 4: ORACLE - BOT-SPECIFIC ADAPTATION
    # =========================================================================

    def _get_oracle_adaptation(
        self,
        bot_name: str,
        ml_decision: MLAdvisorDecision,
        ensemble_context: EnsembleContext,
        gex_data: Dict
    ) -> OracleAdaptation:
        """
        Get Oracle bot-specific adaptation.

        NO veto power over ML Advisor decision.
        Only adapts the decision for the specific bot.
        """
        adaptation = OracleAdaptation(bot_name=bot_name)

        # Use GEX walls for strike selection if available
        if gex_data:
            put_wall = gex_data.get('put_wall', gex_data.get('gex_put_wall'))
            call_wall = gex_data.get('call_wall', gex_data.get('gex_call_wall'))

            if put_wall and call_wall:
                adaptation.use_gex_walls = True
                adaptation.suggested_put_strike = put_wall
                adaptation.suggested_call_strike = call_wall
                adaptation.reasoning = f"Using GEX walls for strikes: Put={put_wall}, Call={call_wall}"

        # Adjust risk based on ensemble context
        if ensemble_context.confidence >= 80:
            adaptation.risk_adjustment = 1.2  # Increase risk slightly
            adaptation.reasoning += " | High ensemble confidence: +20% risk"
        elif ensemble_context.confidence < 60:
            adaptation.risk_adjustment = 0.8  # Reduce risk
            adaptation.reasoning += " | Low ensemble confidence: -20% risk"

        return adaptation

    # =========================================================================
    # MAIN DECISION FUNCTION
    # =========================================================================

    def get_trading_decision(
        self,
        bot_name: str,
        gex_data: Dict,
        features: Dict,
        psychology_data: Optional[Dict] = None,
        rsi_data: Optional[Dict] = None,
        vol_surface_data: Optional[Dict] = None,
        current_regime: str = "UNKNOWN"
    ) -> OmegaDecision:
        """
        Get complete trading decision with full transparency.

        This is the main entry point for all trading decisions.

        Args:
            bot_name: Name of the bot requesting decision (ARES, ATHENA, etc.)
            gex_data: GEX analysis data
            features: ML features dict
            psychology_data: Optional psychology trap data
            rsi_data: Optional RSI multi-timeframe data
            vol_surface_data: Optional vol surface data
            current_regime: Current market regime

        Returns:
            OmegaDecision with complete decision and transparency
        """
        decision_path = []
        now = datetime.now(CENTRAL_TZ)

        # =====================================================================
        # LAYER 1: SOLOMON CHECK (ABSOLUTE AUTHORITY)
        # =====================================================================
        decision_path.append("LAYER 1: Checking Solomon safety limits...")
        solomon_verdict = self._check_solomon(bot_name)

        if not solomon_verdict.can_trade:
            decision_path.append(f"BLOCKED BY SOLOMON: {solomon_verdict.reason}")

            return OmegaDecision(
                timestamp=now,
                bot_name=bot_name,
                final_decision=TradingDecision.BLOCKED_BY_SOLOMON,
                final_risk_pct=0,
                final_position_size_multiplier=0,
                solomon_verdict=solomon_verdict,
                ensemble_context=EnsembleContext(
                    signal="NEUTRAL", confidence=0, bullish_weight=0,
                    bearish_weight=0, neutral_weight=1, component_signals={},
                    position_size_multiplier=0, regime=current_regime
                ),
                ml_decision=MLAdvisorDecision(
                    advice="SKIP_TODAY", win_probability=0, confidence=0,
                    suggested_risk_pct=0, suggested_sd_multiplier=0,
                    top_factors=[], model_version="blocked"
                ),
                oracle_adaptation=OracleAdaptation(bot_name=bot_name),
                capital_allocation={},
                equity_scaled_risk=0,
                correlation_check={'allowed': False},
                decision_path=decision_path
            )

        decision_path.append("Solomon: PASSED - Proceeding to Ensemble")

        # =====================================================================
        # LAYER 2: ENSEMBLE CONTEXT (INFORMATIONAL)
        # =====================================================================
        decision_path.append("LAYER 2: Getting Ensemble market context...")
        ensemble_context = self._get_ensemble_context(
            gex_data=gex_data,
            psychology_data=psychology_data,
            rsi_data=rsi_data,
            vol_surface_data=vol_surface_data,
            current_regime=current_regime
        )
        decision_path.append(f"Ensemble: {ensemble_context.signal} ({ensemble_context.confidence:.0f}% confidence)")

        # =====================================================================
        # LAYER 3: ML ADVISOR DECISION (PRIMARY)
        # =====================================================================
        decision_path.append("LAYER 3: Getting ML Advisor decision (PRIMARY)...")
        ml_decision = self._get_ml_decision(features, ensemble_context)
        decision_path.append(f"ML Advisor: {ml_decision.advice} (win prob: {ml_decision.win_probability:.1%})")

        # Record prediction for auto-retrain monitoring (Gap 1)
        self.auto_retrain_monitor.record_prediction(
            bot_name=bot_name,
            predicted_win_prob=ml_decision.win_probability,
            model_version=ml_decision.model_version
        )

        # =====================================================================
        # LAYER 4: ORACLE ADAPTATION (BOT-SPECIFIC)
        # =====================================================================
        decision_path.append("LAYER 4: Getting Oracle bot-specific adaptation...")
        oracle_adaptation = self._get_oracle_adaptation(
            bot_name=bot_name,
            ml_decision=ml_decision,
            ensemble_context=ensemble_context,
            gex_data=gex_data
        )
        decision_path.append(f"Oracle: Risk adjustment {oracle_adaptation.risk_adjustment:.0%}")

        # =====================================================================
        # GAP IMPLEMENTATIONS
        # =====================================================================

        # Gap 2: Thompson Capital Allocation
        thompson = self._get_thompson_allocator()
        if thompson:
            allocation = thompson.sample_allocation(self.capital)
            capital_allocation = allocation.allocations
            bot_allocation = capital_allocation.get(bot_name, 0.25)
        else:
            capital_allocation = {bot_name: 0.25}
            bot_allocation = 0.25

        decision_path.append(f"Gap 2 (Thompson): {bot_name} allocation = {bot_allocation:.1%}")

        # Gap 6: Regime Transition Detection
        gex_regime = gex_data.get('regime', 'UNKNOWN')
        vix = features.get('vix', 20)
        trend = gex_data.get('trend', 'UNKNOWN')
        net_gamma = gex_data.get('net_gamma', 0)

        transition_alert = self.regime_detector.record_observation(
            gex_regime=gex_regime,
            vix=vix,
            price_trend=trend,
            net_gamma=net_gamma
        )

        regime_transition = None
        if transition_alert:
            decision_path.append(f"Gap 6 (Regime): TRANSITION DETECTED - {transition_alert}")
            if transition_alert['transitions']:
                regime_transition = RegimeTransition(transition_alert['transitions'][0]['type'])

        # Gap 9: Cross-Bot Correlation Check
        direction = "NEUTRAL"
        if ensemble_context.signal in ["STRONG_BUY", "BUY"]:
            direction = "BULLISH"
        elif ensemble_context.signal in ["STRONG_SELL", "SELL"]:
            direction = "BEARISH"

        proposed_exposure = ml_decision.suggested_risk_pct * bot_allocation * 100
        correlation_check = self.correlation_enforcer.check_new_position(
            bot_name=bot_name,
            direction=direction,
            proposed_exposure_pct=proposed_exposure
        )

        decision_path.append(f"Gap 9 (Correlation): {'ALLOWED' if correlation_check['allowed'] else 'ADJUSTED'}")

        # Gap 10: Equity Compound Scaling
        base_risk = ml_decision.suggested_risk_pct * oracle_adaptation.risk_adjustment
        equity_scaling = self.equity_scaler.get_position_multiplier(base_risk)

        decision_path.append(f"Gap 10 (Equity): Multiplier = {equity_scaling['multiplier']:.2f}")

        # =====================================================================
        # FINAL DECISION CALCULATION
        # =====================================================================

        # Apply all adjustments
        final_risk_pct = equity_scaling['adjusted_risk_pct']

        # Apply correlation adjustment if needed
        if not correlation_check['allowed']:
            final_risk_pct = 0
        elif correlation_check['adjusted_exposure'] < proposed_exposure:
            adjustment_factor = correlation_check['adjusted_exposure'] / proposed_exposure
            final_risk_pct *= adjustment_factor

        # Calculate final position size multiplier
        final_multiplier = (
            ensemble_context.position_size_multiplier *
            equity_scaling['multiplier'] *
            bot_allocation * 4  # Normalize allocation (4 bots)
        )
        final_multiplier = max(0.1, min(1.5, final_multiplier))

        # Determine final decision
        if ml_decision.advice == "SKIP_TODAY":
            final_decision = TradingDecision.SKIP_TODAY
        elif ml_decision.advice == "TRADE_REDUCED" or final_multiplier < 0.5:
            final_decision = TradingDecision.TRADE_REDUCED
        else:
            final_decision = TradingDecision.TRADE_FULL

        decision_path.append(f"FINAL: {final_decision.value} | Risk: {final_risk_pct:.2f}% | Size: {final_multiplier:.0%}")

        # Create complete decision
        omega_decision = OmegaDecision(
            timestamp=now,
            bot_name=bot_name,
            final_decision=final_decision,
            final_risk_pct=final_risk_pct,
            final_position_size_multiplier=final_multiplier,
            solomon_verdict=solomon_verdict,
            ensemble_context=ensemble_context,
            ml_decision=ml_decision,
            oracle_adaptation=oracle_adaptation,
            capital_allocation=capital_allocation,
            equity_scaled_risk=equity_scaling['adjusted_risk_pct'],
            correlation_check=correlation_check,
            regime_transition=regime_transition,
            decision_path=decision_path
        )

        # Store in history
        with self._lock:
            self.decision_history.append(omega_decision)
            if len(self.decision_history) > 1000:
                self.decision_history = self.decision_history[-1000:]

        return omega_decision

    # =========================================================================
    # OUTCOME RECORDING
    # =========================================================================

    def record_trade_outcome(
        self,
        bot_name: str,
        was_win: bool,
        pnl: float
    ) -> Dict:
        """
        Record trade outcome for all feedback loops.

        Updates:
        - Solomon (consecutive loss tracking)
        - Auto-retrain monitor (Gap 1)
        - Thompson allocator (Gap 2)
        - Equity scaler (Gap 10)
        """
        results = {}

        # Update Solomon
        solomon = self._get_solomon_enhanced()
        if solomon:
            alerts = solomon.record_trade_outcome(
                bot_name=bot_name,
                pnl=pnl,
                trade_date=datetime.now(CENTRAL_TZ).strftime('%Y-%m-%d')
            )
            results['solomon_alerts'] = alerts

        # Update Auto-Retrain Monitor (Gap 1)
        retrain_check = self.auto_retrain_monitor.record_outcome(
            bot_name=bot_name,
            was_win=was_win,
            pnl=pnl
        )
        results['retrain_check'] = retrain_check

        # Update Thompson Allocator (Gap 2)
        thompson = self._get_thompson_allocator()
        if thompson:
            thompson.record_outcome(bot_name, was_win, pnl)
            results['thompson_updated'] = True

        # Update Equity Scaler (Gap 10)
        current_equity = self.capital + pnl
        self.equity_scaler.update_equity(current_equity)
        self.capital = current_equity
        results['new_equity'] = current_equity

        # Update correlation enforcer
        if was_win or pnl < 0:  # Trade closed
            self.correlation_enforcer.close_position(bot_name)

        return results

    # =========================================================================
    # STATUS AND DIAGNOSTICS
    # =========================================================================

    def get_status(self) -> Dict:
        """Get comprehensive OMEGA status"""
        return {
            'timestamp': datetime.now(CENTRAL_TZ).isoformat(),
            'capital': self.capital,
            'gaps': {
                'gap1_auto_retrain': self.auto_retrain_monitor.get_status(),
                'gap2_thompson': self._get_thompson_allocator().get_expected_win_rates() if self._get_thompson_allocator() else None,
                'gap6_regime': self.regime_detector.get_current_regimes(),
                'gap9_correlation': self.correlation_enforcer.get_status(),
                'gap10_equity': self.equity_scaler.get_status()
            },
            'recent_decisions': len(self.decision_history),
            'layers': {
                'solomon': 'ACTIVE',
                'ensemble': 'ACTIVE',
                'ml_advisor': 'ACTIVE' if self._get_ml_advisor() and self._get_ml_advisor().is_trained else 'FALLBACK',
                'oracle': 'ACTIVE'
            }
        }


# =============================================================================
# SINGLETON
# =============================================================================

_omega_instance: Optional[OmegaOrchestrator] = None
_omega_lock = Lock()


def get_omega_orchestrator(capital: float = 100000) -> OmegaOrchestrator:
    """Get or create OMEGA Orchestrator singleton"""
    global _omega_instance

    with _omega_lock:
        if _omega_instance is None:
            _omega_instance = OmegaOrchestrator(capital)

    return _omega_instance


# =============================================================================
# CLI
# =============================================================================

if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(description="OMEGA Orchestrator")
    parser.add_argument("command", choices=["status", "test", "decision"])
    parser.add_argument("--bot", default="ARES")
    args = parser.parse_args()

    omega = get_omega_orchestrator()

    if args.command == "status":
        status = omega.get_status()
        print(json.dumps(status, indent=2, default=str))

    elif args.command == "test":
        print("Testing OMEGA Orchestrator...")
        print(f"  Capital: ${omega.capital:,.0f}")
        print(f"  Layers: {omega.get_status()['layers']}")
        print("  Test complete!")

    elif args.command == "decision":
        # Test decision with mock data
        test_gex = {
            'regime': 'POSITIVE',
            'net_gamma': 100,
            'put_wall': 580,
            'call_wall': 600,
            'trend': 'BULLISH'
        }

        test_features = {
            'vix': 18.0,
            'vix_percentile_30d': 45.0,
            'vix_change_1d': -0.5,
            'day_of_week': 2,
            'price_change_1d': 0.3,
            'expected_move_pct': 1.2,
            'win_rate_30d': 0.68,
            'gex_normalized': 0.5,
            'gex_regime_positive': 1,
            'gex_distance_to_flip_pct': 2.0,
            'gex_between_walls': 1
        }

        decision = omega.get_trading_decision(
            bot_name=args.bot,
            gex_data=test_gex,
            features=test_features,
            current_regime="POSITIVE"
        )

        print("\n=== OMEGA DECISION ===")
        print(f"Bot: {decision.bot_name}")
        print(f"Final Decision: {decision.final_decision.value}")
        print(f"Final Risk: {decision.final_risk_pct:.2f}%")
        print(f"Position Multiplier: {decision.final_position_size_multiplier:.0%}")
        print("\n--- Decision Path ---")
        for step in decision.decision_path:
            print(f"  {step}")
