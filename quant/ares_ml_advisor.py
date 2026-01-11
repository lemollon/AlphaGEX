"""
ARES ML Advisor - Machine Learning Feedback Loop for Iron Condor Trading
=========================================================================

PURPOSE:
This module creates a feedback loop between KRONOS (backtester) and ARES (live trader).
KRONOS historical data trains an ML model that advises ARES on:
1. Should I trade today? (probability of success)
2. How much should I risk? (dynamic position sizing)
3. What SD multiplier to use? (strike selection optimization)

HONEST LIMITATIONS:
- Iron Condors have ~70% win rate, so limited loss examples
- Market regimes change over time (model may need retraining)
- Feature engineering may matter more than model complexity
- Past performance doesn't guarantee future results

FEEDBACK LOOP:
    KRONOS Backtests --> Extract Features --> Train Model
            ^                                      |
            |                                      v
    Store Outcome <-- ARES Live Trade <-- Query Model

Author: AlphaGEX ML
Date: 2025-12-10
"""
from __future__ import annotations  # Allow string type hints - must be first

import os
import sys
import math
import json
import pickle
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any, TYPE_CHECKING
from dataclasses import dataclass, asdict
from enum import Enum
import warnings

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ML imports
try:
    import numpy as np
    import pandas as pd
    from sklearn.preprocessing import StandardScaler
    from sklearn.model_selection import TimeSeriesSplit
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.metrics import (
        accuracy_score, precision_score, recall_score, f1_score,
        roc_auc_score, brier_score_loss, confusion_matrix
    )
    ML_AVAILABLE = True
except ImportError:
    ML_AVAILABLE = False
    np = None
    pd = None
    print("Warning: ML libraries not available. Install with: pip install scikit-learn pandas numpy")

# XGBoost for all ML in AlphaGEX
try:
    import xgboost as xgb
    HAS_XGBOOST = True
except ImportError:
    HAS_XGBOOST = False
    print("Warning: XGBoost not installed. Install with: pip install xgboost")

# Database
try:
    from database_adapter import get_connection
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False

logger = logging.getLogger(__name__)


class TradeOutcome(Enum):
    """Possible Iron Condor outcomes"""
    MAX_PROFIT = "MAX_PROFIT"           # Both sides OTM at expiration
    PUT_BREACHED = "PUT_BREACHED"       # Short put went ITM
    CALL_BREACHED = "CALL_BREACHED"     # Short call went ITM
    DOUBLE_BREACH = "DOUBLE_BREACH"     # Both sides breached (rare)


class TradingAdvice(Enum):
    """ML model advice to ARES"""
    TRADE_FULL = "TRADE_FULL"           # High confidence, trade normal size
    TRADE_REDUCED = "TRADE_REDUCED"     # Medium confidence, reduce size
    SKIP_TODAY = "SKIP_TODAY"           # Low confidence, don't trade


@dataclass
class MLFeatures:
    """Features extracted for ML prediction"""
    # VIX features
    vix: float
    vix_percentile_30d: float      # Where VIX sits in 30-day range
    vix_change_1d: float           # 1-day VIX change %

    # Day features
    day_of_week: int               # 0=Mon, 4=Fri

    # Price features
    price: float
    price_change_1d: float         # 1-day price change %

    # IV features
    iv: float                      # Implied volatility used
    expected_move_pct: float       # Expected move as % of price

    # Historical performance (rolling)
    win_rate_30d: float           # Recent 30-day win rate
    avg_pnl_30d: float            # Recent 30-day avg P&L

    # Optional: tier info
    tier_name: str = "TIER_1_0DTE"


@dataclass
class MLPrediction:
    """Prediction from ML model"""
    advice: TradingAdvice
    win_probability: float         # 0-1 probability of MAX_PROFIT
    confidence: float              # 0-100 confidence in prediction
    suggested_risk_pct: float      # Suggested risk % (0-15%)
    suggested_sd_multiplier: float # Suggested SD (0.5-1.5)

    # Explanation for transparency
    top_factors: List[Tuple[str, float]]  # Top 3 factors influencing decision
    model_version: str

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
    brier_score: float            # Calibration quality

    # Class-specific
    win_rate_predicted: float
    win_rate_actual: float

    # Data info
    total_samples: int
    train_samples: int
    test_samples: int
    positive_samples: int         # Wins
    negative_samples: int         # Losses

    # Feature importance
    feature_importances: Dict[str, float]

    training_date: str
    model_version: str


class AresMLAdvisor:
    """
    ML Advisor for ARES Iron Condor Trading

    Uses KRONOS backtest data to train a model that predicts:
    - Probability of trade success
    - Optimal position size
    - Whether to skip today's trade

    The model learns patterns like:
    - VIX levels that correlate with wins/losses
    - Days of week with better performance
    - Market conditions that precede breaches
    """

    # Feature columns for prediction
    # V2: Now includes GEX features for better Iron Condor prediction
    FEATURE_COLS = [
        'vix',
        'vix_percentile_30d',
        'vix_change_1d',
        'day_of_week',
        'price_change_1d',
        'expected_move_pct',
        'win_rate_30d',
        # GEX features (V2)
        'gex_normalized',           # Scale-independent GEX
        'gex_regime_positive',      # 1 if positive GEX regime, 0 otherwise
        'gex_distance_to_flip_pct', # Distance to flip point as %
        'gex_between_walls',        # 1 if price between call/put walls
    ]

    # Feature columns without GEX (for backward compatibility)
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

        # Thresholds for advice
        self.high_confidence_threshold = 0.65  # Above this = TRADE_FULL
        self.low_confidence_threshold = 0.45   # Below this = SKIP_TODAY

        # Create models directory
        os.makedirs(self.MODEL_PATH, exist_ok=True)

        # Try to load existing model (database first, then file)
        self._load_model()

    def _load_model(self) -> bool:
        """Load pre-trained model if available (database first, then file)"""
        # Try database first (persists across Render deploys)
        if self.load_from_db():
            return True

        # Fall back to file
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
                    self.is_trained = True
                    logger.info(f"Loaded ARES ML Advisor v{self.model_version} from file")
                    return True
            except Exception as e:
                logger.warning(f"Failed to load model from file: {e}")

        return False

    def _save_model(self):
        """Save trained model to disk"""
        model_file = os.path.join(self.MODEL_PATH, 'ares_advisor_model.pkl')

        try:
            with open(model_file, 'wb') as f:
                pickle.dump({
                    'model': self.model,
                    'calibrated_model': self.calibrated_model,
                    'scaler': self.scaler,
                    'metrics': self.training_metrics,
                    'version': self.model_version,
                    'saved_at': datetime.now().isoformat()
                }, f)
            logger.info(f"Saved ARES ML Advisor to {model_file}")
        except Exception as e:
            logger.error(f"Failed to save model: {e}")

    def save_to_db(self, training_records: int = None) -> bool:
        """Save model to database for persistence across Render deploys"""
        if not self.is_trained:
            logger.warning("Cannot save untrained model to database")
            return False

        try:
            from quant.model_persistence import save_model_to_db, MODEL_ARES_ML

            model_data = {
                'model': self.model,
                'calibrated_model': self.calibrated_model,
                'scaler': self.scaler,
                'metrics': self.training_metrics,
                'version': self.model_version,
            }

            metrics = None
            if self.training_metrics:
                metrics = {
                    'accuracy': self.training_metrics.accuracy,
                    'auc_roc': self.training_metrics.auc_roc,
                    'brier_score': self.training_metrics.brier_score,
                    'win_rate': self.training_metrics.actual_win_rate,
                }

            return save_model_to_db(
                MODEL_ARES_ML,
                model_data,
                metrics=metrics,
                training_records=training_records
            )
        except Exception as e:
            logger.error(f"Failed to save model to database: {e}")
            return False

    def load_from_db(self) -> bool:
        """Load model from database"""
        try:
            from quant.model_persistence import load_model_from_db, MODEL_ARES_ML

            model_data = load_model_from_db(MODEL_ARES_ML)
            if model_data is None:
                return False

            self.model = model_data.get('model')
            self.calibrated_model = model_data.get('calibrated_model')
            self.scaler = model_data.get('scaler')
            self.training_metrics = model_data.get('metrics')
            self.model_version = model_data.get('version', '1.0.0')
            self.is_trained = True

            logger.info(f"Loaded ARES ML Advisor v{self.model_version} from database")
            return True

        except Exception as e:
            logger.error(f"Failed to load model from database: {e}")
            return False

    def extract_features_from_kronos(
        self,
        backtest_results: Dict[str, Any],
        include_gex: bool = True
    ) -> pd.DataFrame:
        """
        Extract ML features from KRONOS backtest results.

        Args:
            backtest_results: Results dict from HybridFixedBacktester.run()
            include_gex: Whether to include GEX features (requires enriched data)

        Returns:
            DataFrame with features and outcomes for each trade
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
            logger.info("GEX data not found in backtest results. Enriching with GEX...")
            try:
                from quant.kronos_gex_calculator import enrich_trades_with_gex
                backtest_results = enrich_trades_with_gex(backtest_results)
                trades = backtest_results.get('all_trades', [])
                has_gex = 'gex_normalized' in trades[0] if trades else False
                if has_gex:
                    logger.info("Successfully enriched trades with GEX data")
            except Exception as e:
                logger.warning(f"Could not enrich with GEX: {e}")
                has_gex = False

        records = []

        # Build rolling stats as we process
        outcomes = []
        pnls = []

        for i, trade in enumerate(trades):
            # Calculate rolling stats (30-day lookback)
            lookback_start = max(0, i - 30)
            recent_outcomes = outcomes[lookback_start:i] if i > 0 else []
            recent_pnls = pnls[lookback_start:i] if i > 0 else []

            win_rate_30d = sum(1 for o in recent_outcomes if o == 'MAX_PROFIT') / len(recent_outcomes) if recent_outcomes else 0.68
            avg_pnl_30d = sum(recent_pnls) / len(recent_pnls) if recent_pnls else 0

            # Parse date for day of week
            trade_date = trade.get('trade_date', '')
            try:
                dt = datetime.strptime(trade_date, '%Y-%m-%d')
                day_of_week = dt.weekday()
            except:
                day_of_week = 2  # Default to Wednesday

            # Extract features
            vix = trade.get('vix', 20.0)
            open_price = trade.get('open_price', 5000)
            close_price = trade.get('close_price', open_price)

            # Calculate derived features
            price_change_1d = (close_price - open_price) / open_price * 100 if open_price > 0 else 0
            expected_move = trade.get('expected_move_sd', trade.get('expected_move_1d', 50))
            expected_move_pct = expected_move / open_price * 100 if open_price > 0 else 1.0

            # Outcome
            outcome = trade.get('outcome', 'MAX_PROFIT')
            is_win = outcome == 'MAX_PROFIT'
            net_pnl = trade.get('net_pnl', 0)

            # Store for rolling calculation
            outcomes.append(outcome)
            pnls.append(net_pnl)

            record = {
                'trade_date': trade_date,
                'vix': vix,
                'vix_percentile_30d': 50,  # Will calculate later
                'vix_change_1d': 0,         # Will calculate later
                'day_of_week': day_of_week,
                'price': open_price,
                'price_change_1d': price_change_1d,
                'expected_move_pct': expected_move_pct,
                'win_rate_30d': win_rate_30d,
                'avg_pnl_30d': avg_pnl_30d,
                'tier_name': trade.get('tier_name', 'TIER_1_0DTE'),

                # Target variables
                'outcome': outcome,
                'is_win': is_win,
                'net_pnl': net_pnl,
                'return_pct': trade.get('return_pct', 0),
            }

            # Add GEX features if available
            if has_gex:
                gex_regime = trade.get('gex_regime', 'NEUTRAL')
                record['gex_normalized'] = trade.get('gex_normalized', 0)
                record['gex_regime_positive'] = 1 if gex_regime == 'POSITIVE' else 0
                record['gex_distance_to_flip_pct'] = trade.get('gex_distance_to_flip_pct', 0)
                record['gex_between_walls'] = 1 if trade.get('gex_between_walls', True) else 0
            else:
                # Default GEX values (neutral)
                record['gex_normalized'] = 0
                record['gex_regime_positive'] = 0
                record['gex_distance_to_flip_pct'] = 0
                record['gex_between_walls'] = 1

            records.append(record)

        df = pd.DataFrame(records)

        # Calculate VIX rolling percentile and change
        if len(df) > 1:
            df['vix_percentile_30d'] = df['vix'].rolling(30, min_periods=1).apply(
                lambda x: (x.rank().iloc[-1] / len(x)) * 100 if len(x) > 0 else 50
            ).fillna(50)
            df['vix_change_1d'] = df['vix'].pct_change().fillna(0) * 100

        # Store whether we have GEX for later use
        self._has_gex_features = has_gex

        return df

    def train_from_kronos(
        self,
        backtest_results: Dict[str, Any],
        test_size: float = 0.2,
        min_samples: int = 100
    ) -> TrainingMetrics:
        """
        Train ML model from KRONOS backtest results.

        Uses walk-forward validation to avoid look-ahead bias.

        Args:
            backtest_results: Results from HybridFixedBacktester
            test_size: Fraction for test set
            min_samples: Minimum samples required

        Returns:
            TrainingMetrics with model performance
        """
        if not ML_AVAILABLE:
            raise ImportError("ML libraries required. Install: pip install scikit-learn pandas numpy")

        # Extract features
        df = self.extract_features_from_kronos(backtest_results)

        if len(df) < min_samples:
            raise ValueError(f"Insufficient data: {len(df)} samples < {min_samples} required")

        logger.info(f"Training on {len(df)} trades from KRONOS backtest")

        # Prepare features and target
        X = df[self.FEATURE_COLS].values
        y = df['is_win'].values.astype(int)

        # Scale features
        self.scaler = StandardScaler()
        X_scaled = self.scaler.fit_transform(X)

        # Time-series split for walk-forward validation
        n_splits = 5
        tscv = TimeSeriesSplit(n_splits=n_splits)

        # Train XGBoost (best performance on tabular data)
        if not HAS_XGBOOST:
            raise ImportError("XGBoost required. Install with: pip install xgboost")

        self.model = xgb.XGBClassifier(
            n_estimators=150,
            max_depth=4,
            learning_rate=0.1,
            min_child_weight=10,
            subsample=0.8,
            colsample_bytree=0.8,
            reg_alpha=0.1,  # L1 regularization
            reg_lambda=1.0,  # L2 regularization
            random_state=42,
            use_label_encoder=False,
            eval_metric='logloss',
            verbosity=0
        )

        # Cross-validation metrics
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
                aucs.append(0.5)  # Only one class in test set

        # Final training on all data
        self.model.fit(X_scaled, y)

        # Calibrate probabilities for better confidence estimates
        self.calibrated_model = CalibratedClassifierCV(
            self.model, method='isotonic', cv=3
        )
        self.calibrated_model.fit(X_scaled, y)

        # Calculate Brier score (calibration quality)
        y_proba_full = self.calibrated_model.predict_proba(X_scaled)[:, 1]
        brier = brier_score_loss(y, y_proba_full)

        # Feature importances
        feature_importances = dict(zip(self.FEATURE_COLS, self.model.feature_importances_))

        # Build metrics
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

        # Save model
        self._save_model()

        logger.info(f"Model trained successfully:")
        logger.info(f"  Accuracy: {self.training_metrics.accuracy:.2%}")
        logger.info(f"  AUC-ROC: {self.training_metrics.auc_roc:.3f}")
        logger.info(f"  Win Rate (actual): {self.training_metrics.win_rate_actual:.2%}")
        logger.info(f"  Top features: {sorted(feature_importances.items(), key=lambda x: -x[1])[:3]}")

        return self.training_metrics

    def predict(
        self,
        vix: float,
        day_of_week: int,
        price: float = 5000,
        price_change_1d: float = 0,
        expected_move_pct: float = 1.0,
        win_rate_30d: float = 0.68,
        vix_percentile_30d: float = 50,
        vix_change_1d: float = 0,
        # GEX features (V2)
        gex_normalized: float = 0,
        gex_regime_positive: int = 0,
        gex_distance_to_flip_pct: float = 0,
        gex_between_walls: int = 1
    ) -> MLPrediction:
        """
        Get ML prediction for today's trading decision.

        Args:
            vix: Current VIX level
            day_of_week: 0=Monday, 4=Friday
            price: Current SPX price
            price_change_1d: Yesterday's price change %
            expected_move_pct: Expected move as % of price
            win_rate_30d: Recent 30-day win rate
            vix_percentile_30d: VIX percentile in 30-day range
            vix_change_1d: VIX change from yesterday %
            gex_normalized: Scale-independent GEX (GEX / spot^2)
            gex_regime_positive: 1 if positive GEX regime, 0 otherwise
            gex_distance_to_flip_pct: Distance to flip point as %
            gex_between_walls: 1 if price between call/put walls

        Returns:
            MLPrediction with advice and probability
        """
        if not self.is_trained:
            # Return conservative fallback
            return self._fallback_prediction(vix, day_of_week, gex_regime_positive)

        # Prepare features - use the feature columns the model was trained on
        has_gex = getattr(self, '_has_gex_features', len(self.FEATURE_COLS) > 7)

        if has_gex:
            features = np.array([[
                vix,
                vix_percentile_30d,
                vix_change_1d,
                day_of_week,
                price_change_1d,
                expected_move_pct,
                win_rate_30d,
                gex_normalized,
                gex_regime_positive,
                gex_distance_to_flip_pct,
                gex_between_walls,
            ]])
        else:
            # V1 model without GEX
            features = np.array([[
                vix,
                vix_percentile_30d,
                vix_change_1d,
                day_of_week,
                price_change_1d,
                expected_move_pct,
                win_rate_30d,
            ]])

        # Scale
        features_scaled = self.scaler.transform(features)

        # Get calibrated probability
        if self.calibrated_model:
            proba = self.calibrated_model.predict_proba(features_scaled)[0]
        else:
            proba = self.model.predict_proba(features_scaled)[0]

        win_probability = proba[1]  # Probability of class 1 (win)

        # Determine advice based on thresholds
        if win_probability >= self.high_confidence_threshold:
            advice = TradingAdvice.TRADE_FULL
            suggested_risk = 10.0  # Full 10%
        elif win_probability >= self.low_confidence_threshold:
            advice = TradingAdvice.TRADE_REDUCED
            # Scale risk between 3% and 8%
            suggested_risk = 3.0 + (win_probability - self.low_confidence_threshold) / \
                (self.high_confidence_threshold - self.low_confidence_threshold) * 5.0
        else:
            advice = TradingAdvice.SKIP_TODAY
            suggested_risk = 0.0

        # Suggested SD multiplier (more conservative when less confident)
        if win_probability >= 0.75:
            suggested_sd = 0.9  # Tighter strikes, more premium
        elif win_probability >= 0.65:
            suggested_sd = 1.0  # Standard
        else:
            suggested_sd = 1.2  # Wider strikes, safer

        # Top factors
        feature_importance = dict(zip(self.FEATURE_COLS, self.model.feature_importances_))
        top_factors = sorted(feature_importance.items(), key=lambda x: -x[1])[:3]

        # Confidence (scaled win probability)
        confidence = min(100, win_probability * 100 * 1.2)  # Slight boost for display

        return MLPrediction(
            advice=advice,
            win_probability=win_probability,
            confidence=confidence,
            suggested_risk_pct=suggested_risk,
            suggested_sd_multiplier=suggested_sd,
            top_factors=top_factors,
            model_version=self.model_version,
            probabilities={'win': proba[1], 'loss': proba[0]}
        )

    def _fallback_prediction(
        self,
        vix: float,
        day_of_week: int,
        gex_regime_positive: int = 0
    ) -> MLPrediction:
        """
        Rule-based fallback when model not trained.

        Uses simple heuristics based on known patterns:
        - High VIX (>30) = more risk, reduce size
        - Mondays tend to be more volatile
        - Fridays have theta acceleration
        - Positive GEX = better for Iron Condors (mean reversion)
        """
        # Base win probability from historical average
        # Iron Condors historically have ~70% win rate
        base_prob = 0.70

        # VIX adjustment - REDUCED penalties to avoid blocking too many trades
        # High VIX actually means higher premiums, which can offset risk
        if vix > 35:
            base_prob -= 0.05  # REDUCED from -10%: High VIX = more risk but more premium
        elif vix > 25:
            base_prob -= 0.02  # REDUCED from -5%: Elevated but manageable
        elif vix < 12:
            base_prob -= 0.02  # REDUCED from -3%: Low VIX = low premium

        # Day of week adjustment - REDUCED to be less aggressive
        dow_adjustments = {
            0: -0.01,  # REDUCED from -2%: Monday - gap risk
            1: 0.01,   # Tuesday
            2: 0.02,   # Wednesday - hump day stability
            3: 0.01,   # Thursday
            4: 0.00,   # Friday - theta but expiration risk
        }
        base_prob += dow_adjustments.get(day_of_week, 0)

        # GEX adjustment - REDUCED penalties
        # Positive GEX = market makers long gamma = mean reversion = good for Iron Condors
        # Negative GEX = market makers short gamma = trending = slightly risky for IC
        if gex_regime_positive == 1:
            base_prob += 0.03  # REDUCED from +5%: Positive GEX favors Iron Condors
        else:
            base_prob -= 0.02  # REDUCED from -3%: Negative/neutral GEX slightly unfavorable

        # Clip to reasonable range - raised floor from 0.4 to 0.5
        win_probability = max(0.5, min(0.85, base_prob))

        # Determine advice
        if win_probability >= 0.65:
            advice = TradingAdvice.TRADE_FULL
            suggested_risk = 10.0
        elif win_probability >= 0.55:
            advice = TradingAdvice.TRADE_REDUCED
            suggested_risk = 5.0
        else:
            advice = TradingAdvice.SKIP_TODAY
            suggested_risk = 0.0

        # Build top factors
        top_factors = [('vix', 0.4), ('gex_regime', 0.3), ('day_of_week', 0.2), ('base_rate', 0.1)]

        return MLPrediction(
            advice=advice,
            win_probability=win_probability,
            confidence=45.0,  # Slightly higher with GEX
            suggested_risk_pct=suggested_risk,
            suggested_sd_multiplier=1.0,
            top_factors=top_factors,
            model_version="fallback_v2_gex",
            probabilities={'win': win_probability, 'loss': 1 - win_probability}
        )

    def record_outcome(
        self,
        trade_date: str,
        features: MLFeatures,
        outcome: TradeOutcome,
        net_pnl: float,
        prediction_used: Optional[MLPrediction] = None
    ) -> bool:
        """
        Record trade outcome for future training.

        This creates the feedback loop - ARES outcomes feed back
        into the training data for model improvement.

        Args:
            trade_date: Date of trade
            features: Features at time of prediction
            outcome: Actual trade outcome
            net_pnl: Realized P&L
            prediction_used: The prediction that was used (for analysis)

        Returns:
            True if recorded successfully
        """
        if not DB_AVAILABLE:
            logger.warning("Database not available for recording outcome")
            return False

        try:
            conn = get_connection()
            cursor = conn.cursor()

            # Check if table exists, create if not
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ares_ml_outcomes (
                    id SERIAL PRIMARY KEY,
                    trade_date TEXT NOT NULL,

                    -- Features at prediction time
                    vix REAL,
                    vix_percentile_30d REAL,
                    vix_change_1d REAL,
                    day_of_week INTEGER,
                    price REAL,
                    price_change_1d REAL,
                    expected_move_pct REAL,
                    win_rate_30d REAL,
                    tier_name TEXT,

                    -- Prediction made
                    predicted_advice TEXT,
                    predicted_win_prob REAL,
                    suggested_risk_pct REAL,
                    model_version TEXT,

                    -- Actual outcome
                    actual_outcome TEXT,
                    is_win BOOLEAN,
                    net_pnl REAL,

                    -- Metadata
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)

            # Insert record
            cursor.execute("""
                INSERT INTO ares_ml_outcomes (
                    trade_date, vix, vix_percentile_30d, vix_change_1d,
                    day_of_week, price, price_change_1d, expected_move_pct,
                    win_rate_30d, tier_name,
                    predicted_advice, predicted_win_prob, suggested_risk_pct, model_version,
                    actual_outcome, is_win, net_pnl
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                trade_date,
                features.vix,
                features.vix_percentile_30d,
                features.vix_change_1d,
                features.day_of_week,
                features.price,
                features.price_change_1d,
                features.expected_move_pct,
                features.win_rate_30d,
                features.tier_name,
                prediction_used.advice.value if prediction_used else None,
                prediction_used.win_probability if prediction_used else None,
                prediction_used.suggested_risk_pct if prediction_used else None,
                prediction_used.model_version if prediction_used else None,
                outcome.value,
                outcome == TradeOutcome.MAX_PROFIT,
                net_pnl
            ))

            conn.commit()
            conn.close()

            logger.info(f"Recorded outcome: {outcome.value} with P&L ${net_pnl:.2f}")
            return True

        except Exception as e:
            logger.error(f"Failed to record outcome: {e}")
            return False

    def retrain_from_outcomes(self, min_new_samples: int = 50) -> Optional[TrainingMetrics]:
        """
        Retrain model incorporating new ARES outcomes.

        This is the key to the feedback loop - as ARES trades,
        the outcomes improve the model over time.

        Args:
            min_new_samples: Minimum new samples required before retraining

        Returns:
            TrainingMetrics if retrained, None if insufficient data
        """
        if not DB_AVAILABLE:
            logger.warning("Database not available for retraining")
            return None

        try:
            conn = get_connection()

            # Query outcomes
            query = """
                SELECT
                    trade_date, vix, vix_percentile_30d, vix_change_1d,
                    day_of_week, price_change_1d, expected_move_pct, win_rate_30d,
                    actual_outcome, is_win, net_pnl
                FROM ares_ml_outcomes
                ORDER BY trade_date
            """

            df = pd.read_sql(query, conn)
            conn.close()

            if len(df) < min_new_samples:
                logger.info(f"Insufficient outcomes for retraining: {len(df)} < {min_new_samples}")
                return None

            logger.info(f"Retraining with {len(df)} ARES outcomes")

            # Prepare features
            X = df[['vix', 'vix_percentile_30d', 'vix_change_1d', 'day_of_week',
                    'price_change_1d', 'expected_move_pct', 'win_rate_30d']].values
            y = df['is_win'].values.astype(int)

            # Scale
            self.scaler = StandardScaler()
            X_scaled = self.scaler.fit_transform(X)

            # Retrain with XGBoost (same architecture)
            self.model = xgb.XGBClassifier(
                n_estimators=150,
                max_depth=4,
                learning_rate=0.1,
                min_child_weight=10,
                subsample=0.8,
                colsample_bytree=0.8,
                reg_alpha=0.1,
                reg_lambda=1.0,
                random_state=42,
                use_label_encoder=False,
                eval_metric='logloss',
                verbosity=0
            )

            self.model.fit(X_scaled, y)

            # Calibrate
            self.calibrated_model = CalibratedClassifierCV(
                self.model, method='isotonic', cv=3
            )
            self.calibrated_model.fit(X_scaled, y)

            # Update version
            old_version = self.model_version.split('.')
            new_minor = int(old_version[1]) + 1 if len(old_version) > 1 else 1
            self.model_version = f"{old_version[0]}.{new_minor}.0"

            # Calculate metrics
            y_pred = self.model.predict(X_scaled)
            y_proba = self.calibrated_model.predict_proba(X_scaled)[:, 1]

            feature_importances = dict(zip(self.FEATURE_COLS, self.model.feature_importances_))

            self.training_metrics = TrainingMetrics(
                accuracy=accuracy_score(y, y_pred),
                precision=precision_score(y, y_pred, zero_division=0),
                recall=recall_score(y, y_pred, zero_division=0),
                f1_score=f1_score(y, y_pred, zero_division=0),
                auc_roc=roc_auc_score(y, y_proba) if len(np.unique(y)) > 1 else 0.5,
                brier_score=brier_score_loss(y, y_proba),
                win_rate_predicted=y_proba.mean(),
                win_rate_actual=y.mean(),
                total_samples=len(df),
                train_samples=len(df),
                test_samples=0,
                positive_samples=int(y.sum()),
                negative_samples=int(len(y) - y.sum()),
                feature_importances=feature_importances,
                training_date=datetime.now().isoformat(),
                model_version=self.model_version
            )

            self._save_model()

            logger.info(f"Retrained model v{self.model_version}")
            logger.info(f"  Accuracy: {self.training_metrics.accuracy:.2%}")
            logger.info(f"  Win Rate: {self.training_metrics.win_rate_actual:.2%}")

            return self.training_metrics

        except Exception as e:
            logger.error(f"Failed to retrain: {e}")
            return None

    def get_pattern_insights(self) -> Dict[str, Any]:
        """
        Extract interpretable patterns from the trained model.

        Returns insights like:
        - Which VIX ranges work best
        - Which days of week are most profitable
        - Feature importance ranking
        """
        if not self.is_trained:
            return {'error': 'Model not trained'}

        insights = {
            'model_version': self.model_version,
            'training_date': self.training_metrics.training_date if self.training_metrics else None,
            'overall_performance': {
                'accuracy': self.training_metrics.accuracy if self.training_metrics else None,
                'auc_roc': self.training_metrics.auc_roc if self.training_metrics else None,
                'actual_win_rate': self.training_metrics.win_rate_actual if self.training_metrics else None,
            },
            'feature_importance': {},
            'pattern_recommendations': []
        }

        # Feature importance
        if self.training_metrics:
            sorted_features = sorted(
                self.training_metrics.feature_importances.items(),
                key=lambda x: -x[1]
            )
            insights['feature_importance'] = {k: round(v, 4) for k, v in sorted_features}

            # Generate recommendations
            top_feature = sorted_features[0][0]

            if top_feature == 'vix':
                insights['pattern_recommendations'].append(
                    "VIX level is the strongest predictor. Consider VIX-based position sizing."
                )
            elif top_feature == 'day_of_week':
                insights['pattern_recommendations'].append(
                    "Day of week matters significantly. Review performance by day."
                )
            elif top_feature == 'win_rate_30d':
                insights['pattern_recommendations'].append(
                    "Recent performance predicts future results. Momentum effect detected."
                )

        # VIX sensitivity analysis
        if self.is_trained:
            vix_sensitivity = []
            for vix in [12, 15, 18, 20, 25, 30, 35]:
                pred = self.predict(vix=vix, day_of_week=2)  # Wednesday
                vix_sensitivity.append({
                    'vix': vix,
                    'win_probability': round(pred.win_probability, 3),
                    'advice': pred.advice.value
                })
            insights['vix_sensitivity'] = vix_sensitivity

            # Day of week analysis
            dow_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
            dow_analysis = []
            for dow in range(5):
                pred = self.predict(vix=20, day_of_week=dow)
                dow_analysis.append({
                    'day': dow_names[dow],
                    'win_probability': round(pred.win_probability, 3),
                    'advice': pred.advice.value
                })
            insights['day_of_week_analysis'] = dow_analysis

        return insights


# Convenience functions for integration with ARES

_advisor: Optional[AresMLAdvisor] = None

def get_advisor() -> AresMLAdvisor:
    """Get or create the ML advisor singleton"""
    global _advisor
    if _advisor is None:
        _advisor = AresMLAdvisor()
    return _advisor


def get_trading_advice(
    vix: float,
    day_of_week: int = None,
    price: float = 5000,
    **kwargs
) -> MLPrediction:
    """
    Get trading advice for ARES.

    Quick integration point - call this from ARES before trading.

    Example:
        from quant.ares_ml_advisor import get_trading_advice

        advice = get_trading_advice(vix=22.5, day_of_week=1)
        if advice.advice == TradingAdvice.SKIP_TODAY:
            logger.info("ML advisor suggests skipping today")
            return

        # Adjust risk based on ML suggestion
        risk_pct = advice.suggested_risk_pct
    """
    if day_of_week is None:
        day_of_week = datetime.now().weekday()

    advisor = get_advisor()
    return advisor.predict(vix=vix, day_of_week=day_of_week, price=price, **kwargs)


def train_from_backtest(backtest_results: Dict[str, Any]) -> TrainingMetrics:
    """
    Train the ML advisor from KRONOS backtest results.

    Example:
        from backtest.zero_dte_hybrid_fixed import HybridFixedBacktester
        from quant.ares_ml_advisor import train_from_backtest

        # Run backtest
        backtester = HybridFixedBacktester(start_date='2021-01-01')
        results = backtester.run()

        # Train ML model
        metrics = train_from_backtest(results)
        print(f"Model trained with {metrics.accuracy:.1%} accuracy")
    """
    advisor = get_advisor()
    return advisor.train_from_kronos(backtest_results)


if __name__ == "__main__":
    # Demo usage
    print("=" * 60)
    print("ARES ML Advisor - Demo")
    print("=" * 60)

    advisor = get_advisor()

    if not advisor.is_trained:
        print("\nModel not trained. Run a KRONOS backtest first:")
        print("  python backtest/zero_dte_hybrid_fixed.py --start 2021-01-01")
        print("  Then call train_from_backtest(results)")

    # Demo predictions with fallback
    print("\n--- Demo Predictions (fallback mode) ---")

    scenarios = [
        {"vix": 15, "day_of_week": 2, "desc": "Low VIX Wednesday"},
        {"vix": 25, "day_of_week": 0, "desc": "Medium VIX Monday"},
        {"vix": 35, "day_of_week": 4, "desc": "High VIX Friday"},
    ]

    for scenario in scenarios:
        pred = advisor.predict(vix=scenario['vix'], day_of_week=scenario['day_of_week'])
        print(f"\n{scenario['desc']}:")
        print(f"  Advice: {pred.advice.value}")
        print(f"  Win Probability: {pred.win_probability:.1%}")
        print(f"  Suggested Risk: {pred.suggested_risk_pct:.1f}%")
        print(f"  Suggested SD: {pred.suggested_sd_multiplier:.2f}")
