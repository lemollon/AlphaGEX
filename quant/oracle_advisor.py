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
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any, TYPE_CHECKING
from dataclasses import dataclass, asdict, field
from enum import Enum
import warnings

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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

logger = logging.getLogger(__name__)


# =============================================================================
# ENUMS AND DATA CLASSES
# =============================================================================

class BotName(Enum):
    """Trading bots that Oracle advises"""
    ARES = "ARES"          # Aggressive Iron Condor
    ATLAS = "ATLAS"        # SPX Wheel Strategy
    PHOENIX = "PHOENIX"    # Directional Calls
    HERMES = "HERMES"      # Manual Wheel via UI


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

    def __init__(self):
        self.model = None
        self.calibrated_model = None
        self.scaler = None
        self.is_trained = False
        self.training_metrics: Optional[TrainingMetrics] = None
        self.model_version = "0.0.0"
        self._has_gex_features = False

        # Thresholds
        self.high_confidence_threshold = 0.70
        self.low_confidence_threshold = 0.55

        # Create models directory
        os.makedirs(self.MODEL_PATH, exist_ok=True)

        # Try to load existing model
        self._load_model()

    # =========================================================================
    # MODEL PERSISTENCE
    # =========================================================================

    def _load_model(self) -> bool:
        """Load pre-trained model if available"""
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
                    logger.info(f"Loaded Oracle model v{self.model_version}")
                    return True
            except Exception as e:
                logger.warning(f"Failed to load model: {e}")

        return False

    def _save_model(self):
        """Save trained model to disk"""
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
            logger.error(f"Failed to save model: {e}")

    # =========================================================================
    # BOT-SPECIFIC ADVICE
    # =========================================================================

    def get_ares_advice(
        self,
        context: MarketContext,
        use_gex_walls: bool = False
    ) -> OraclePrediction:
        """
        Get Iron Condor advice for ARES.

        Args:
            context: Current market conditions
            use_gex_walls: Whether to suggest strikes based on GEX walls

        Returns:
            OraclePrediction with IC-specific advice
        """
        # Get base prediction
        base_pred = self._get_base_prediction(context)

        # Calculate GEX wall strikes if requested
        suggested_put = None
        suggested_call = None

        if use_gex_walls and context.gex_call_wall > 0 and context.gex_put_wall > 0:
            # GEX-Protected IC: strikes outside walls
            suggested_put = context.gex_put_wall - 10  # $10 below put wall
            suggested_call = context.gex_call_wall + 10  # $10 above call wall

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

        # Determine final advice
        advice, risk_pct = self._get_advice_from_probability(base_pred['win_probability'])

        # SD multiplier based on confidence
        if base_pred['win_probability'] >= 0.75:
            sd_mult = 0.9  # Tighter, more premium
        elif base_pred['win_probability'] >= 0.65:
            sd_mult = 1.0  # Standard
        else:
            sd_mult = 1.2  # Wider, safer

        return OraclePrediction(
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
            probabilities=base_pred['probabilities']
        )

    def get_atlas_advice(self, context: MarketContext) -> OraclePrediction:
        """
        Get Wheel strategy advice for ATLAS.

        ATLAS trades cash-secured puts and covered calls.
        GEX signals help with entry timing.
        """
        base_pred = self._get_base_prediction(context)
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

        return OraclePrediction(
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

    def get_phoenix_advice(self, context: MarketContext) -> OraclePrediction:
        """
        Get directional call advice for PHOENIX.

        PHOENIX trades long calls, needs directional bias.
        """
        base_pred = self._get_base_prediction(context)
        reasoning_parts = []

        # Negative GEX + below flip = potential rally
        if context.gex_regime == GEXRegime.NEGATIVE and context.gex_distance_to_flip_pct < 0:
            reasoning_parts.append("Negative GEX below flip = gamma squeeze potential")
            base_pred['win_probability'] = min(0.75, base_pred['win_probability'] + 0.10)
        elif context.gex_regime == GEXRegime.POSITIVE:
            reasoning_parts.append("Positive GEX = mean reversion, less directional opportunity")
            base_pred['win_probability'] = max(0.30, base_pred['win_probability'] - 0.10)

        advice, risk_pct = self._get_advice_from_probability(base_pred['win_probability'])

        return OraclePrediction(
            bot_name=BotName.PHOENIX,
            advice=advice,
            win_probability=base_pred['win_probability'],
            confidence=min(100, base_pred['win_probability'] * 100 * 1.2),
            suggested_risk_pct=risk_pct * 0.5,  # Lower risk for directional
            suggested_sd_multiplier=1.0,
            top_factors=base_pred['top_factors'],
            reasoning=" | ".join(reasoning_parts),
            model_version=self.model_version,
            probabilities=base_pred['probabilities']
        )

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
        base_prob = 0.68

        # VIX adjustment
        if context.vix > 35:
            base_prob -= 0.10
        elif context.vix > 25:
            base_prob -= 0.05
        elif context.vix < 12:
            base_prob -= 0.03

        # Day of week
        dow_adj = {0: -0.02, 1: 0.01, 2: 0.02, 3: 0.01, 4: 0.00}
        base_prob += dow_adj.get(context.day_of_week, 0)

        # GEX
        if context.gex_regime == GEXRegime.POSITIVE:
            base_prob += 0.05
        elif context.gex_regime == GEXRegime.NEGATIVE:
            base_prob -= 0.03

        if not context.gex_between_walls:
            base_prob -= 0.03

        win_probability = max(0.40, min(0.85, base_prob))

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
        if not ML_AVAILABLE:
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

        logger.info(f"Oracle trained successfully:")
        logger.info(f"  Accuracy: {self.training_metrics.accuracy:.2%}")
        logger.info(f"  AUC-ROC: {self.training_metrics.auc_roc:.3f}")
        logger.info(f"  Win Rate: {self.training_metrics.win_rate_actual:.2%}")

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
        """Store prediction to database for feedback loop"""
        if not DB_AVAILABLE:
            logger.warning("Database not available")
            return False

        try:
            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS oracle_predictions (
                    id SERIAL PRIMARY KEY,
                    timestamp TIMESTAMPTZ DEFAULT NOW(),
                    trade_date DATE NOT NULL,
                    bot_name TEXT NOT NULL,

                    vix REAL,
                    gex_normalized REAL,
                    gex_regime TEXT,
                    gex_flip_point REAL,
                    gex_call_wall REAL,
                    gex_put_wall REAL,
                    day_of_week INTEGER,

                    advice TEXT,
                    win_probability REAL,
                    suggested_risk_pct REAL,
                    suggested_sd_multiplier REAL,
                    model_version TEXT,

                    prediction_used BOOLEAN DEFAULT FALSE,
                    actual_outcome TEXT,
                    actual_pnl REAL,

                    UNIQUE(trade_date, bot_name)
                )
            """)

            cursor.execute("""
                INSERT INTO oracle_predictions (
                    trade_date, bot_name, vix, gex_normalized, gex_regime,
                    gex_flip_point, gex_call_wall, gex_put_wall, day_of_week,
                    advice, win_probability, suggested_risk_pct,
                    suggested_sd_multiplier, model_version
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (trade_date, bot_name) DO UPDATE SET
                    advice = EXCLUDED.advice,
                    win_probability = EXCLUDED.win_probability,
                    timestamp = NOW()
            """, (
                trade_date,
                prediction.bot_name.value,
                context.vix,
                context.gex_normalized,
                context.gex_regime.value,
                context.gex_flip_point,
                context.gex_call_wall,
                context.gex_put_wall,
                context.day_of_week,
                prediction.advice.value,
                prediction.win_probability,
                prediction.suggested_risk_pct,
                prediction.suggested_sd_multiplier,
                prediction.model_version
            ))

            conn.commit()
            conn.close()
            logger.info(f"Stored Oracle prediction for {prediction.bot_name.value}")
            return True

        except Exception as e:
            logger.error(f"Failed to store prediction: {e}")
            return False

    def update_outcome(
        self,
        trade_date: str,
        bot_name: BotName,
        outcome: TradeOutcome,
        actual_pnl: float
    ) -> bool:
        """Update prediction with actual outcome (real-time)"""
        if not DB_AVAILABLE:
            return False

        try:
            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute("""
                UPDATE oracle_predictions
                SET prediction_used = TRUE,
                    actual_outcome = %s,
                    actual_pnl = %s
                WHERE trade_date = %s AND bot_name = %s
            """, (outcome.value, actual_pnl, trade_date, bot_name.value))

            conn.commit()
            conn.close()
            logger.info(f"Updated outcome for {bot_name.value}: {outcome.value}")
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


if __name__ == "__main__":
    print("=" * 60)
    print("ORACLE - Multi-Strategy ML Advisor")
    print("=" * 60)

    oracle = get_oracle()
    print(f"Model loaded: {oracle.is_trained}")
    print(f"Version: {oracle.model_version}")

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

    advice = oracle.get_ares_advice(context, use_gex_walls=True)
    print(f"Advice: {advice.advice.value}")
    print(f"Win Prob: {advice.win_probability:.1%}")
    print(f"Risk %: {advice.suggested_risk_pct:.1f}%")
    print(f"Reasoning: {advice.reasoning}")

    if advice.suggested_put_strike:
        print(f"GEX Put Strike: {advice.suggested_put_strike}")
        print(f"GEX Call Strike: {advice.suggested_call_strike}")
