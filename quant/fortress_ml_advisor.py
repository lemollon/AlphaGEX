"""
FORTRESS ML Advisor - Machine Learning Feedback Loop for Iron Condor Trading
=========================================================================

PURPOSE:
This module creates a feedback loop between CHRONICLES (backtester) and FORTRESS (live trader).
CHRONICLES historical data trains an ML model that advises FORTRESS on:
1. Should I trade today? (probability of success)
2. How much should I risk? (dynamic position sizing)
3. What SD multiplier to use? (strike selection optimization)

HONEST LIMITATIONS:
- Iron Condors have ~70% win rate, so limited loss examples
- Market regimes change over time (model may need retraining)
- Feature engineering may matter more than model complexity
- Past performance doesn't guarantee future results

FEEDBACK LOOP:
    CHRONICLES Backtests --> Extract Features --> Train Model
            ^                                      |
            |                                      v
    Store Outcome <-- FORTRESS Live Trade <-- Query Model

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
    """ML model advice to FORTRESS"""
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

    # Day features (cyclical encoding)
    day_of_week_sin: float         # sin(2*pi*dow/5) for cyclical encoding
    day_of_week_cos: float         # cos(2*pi*dow/5) for cyclical encoding

    # Price features
    price: float
    price_change_1d: float         # Previous day's price change %

    # IV features
    iv: float                      # Implied volatility used
    expected_move_pct: float       # Expected move as % of price

    # Volatility Risk Premium (IV - realized vol)
    volatility_risk_premium: float  # VRP: expected_move_pct - realized_vol_5d

    # Historical performance (rolling)
    win_rate_60d: float            # 60-trade rolling win rate (longer horizon)

    # GEX features
    gex_normalized: float = 0.0
    gex_regime_positive: int = 0
    gex_distance_to_flip_pct: float = 0.0
    gex_between_walls: int = 1

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


class FortressMLAdvisor:
    """
    ML Advisor for FORTRESS Iron Condor Trading

    Uses CHRONICLES backtest data to train a model that predicts:
    - Probability of trade success
    - Optimal position size
    - Whether to skip today's trade

    The model learns patterns like:
    - VIX levels that correlate with wins/losses
    - Days of week with better performance
    - Market conditions that precede breaches
    """

    # V3 feature columns: cyclical day encoding, VRP, longer win rate horizon
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
        'gex_normalized',           # Scale-independent GEX
        'gex_regime_positive',      # 1 if positive GEX regime, 0 otherwise
        'gex_distance_to_flip_pct', # Distance to flip point as %
        'gex_between_walls',        # 1 if price between call/put walls
    ]

    # V2 feature columns (for backward compatibility with existing models)
    FEATURE_COLS_V2 = [
        'vix',
        'vix_percentile_30d',
        'vix_change_1d',
        'day_of_week',
        'price_change_1d',
        'expected_move_pct',
        'win_rate_30d',
        'gex_normalized',
        'gex_regime_positive',
        'gex_distance_to_flip_pct',
        'gex_between_walls',
    ]

    # V1 feature columns without GEX (for backward compatibility)
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
        self._feature_version = 3  # V3 features (cyclical day, VRP, 60d win rate)
        self._trained_feature_cols = self.FEATURE_COLS  # Track which features model uses

        # Adaptive thresholds (set relative to base rate after training)
        self.high_confidence_threshold = 0.65  # Default, recalculated after training
        self.low_confidence_threshold = 0.45   # Default, recalculated after training
        self._base_rate = None  # Learned from training data

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
                    self._feature_version = saved.get('feature_version', 2)
                    self._trained_feature_cols = saved.get('feature_cols', self.FEATURE_COLS_V2)
                    self._base_rate = saved.get('base_rate')
                    self._update_thresholds_from_base_rate()
                    self.is_trained = True
                    logger.info(f"Loaded FORTRESS ML Advisor v{self.model_version} (features V{self._feature_version}) from file")
                    return True
            except Exception as e:
                logger.warning(f"Failed to load model from file: {e}")

        return False

    def _save_model(self):
        """Save trained model to disk"""
        model_file = os.path.join(self.MODEL_PATH, 'fortress_advisor_model.pkl')

        try:
            with open(model_file, 'wb') as f:
                pickle.dump({
                    'model': self.model,
                    'calibrated_model': self.calibrated_model,
                    'scaler': self.scaler,
                    'metrics': self.training_metrics,
                    'version': self.model_version,
                    'feature_version': self._feature_version,
                    'feature_cols': self._trained_feature_cols,
                    'base_rate': self._base_rate,
                    'saved_at': datetime.now().isoformat()
                }, f)
            logger.info(f"Saved FORTRESS ML Advisor v{self.model_version} (features V{self._feature_version}) to {model_file}")
        except Exception as e:
            logger.error(f"Failed to save model: {e}")

    def _update_thresholds_from_base_rate(self):
        """Set adaptive thresholds relative to the training base rate"""
        if self._base_rate is not None and self._base_rate > 0.5:
            # SKIP when model predicts significantly below base rate
            self.low_confidence_threshold = self._base_rate - 0.15
            # TRADE_FULL when at or above base rate
            self.high_confidence_threshold = self._base_rate - 0.05
            logger.info(
                f"Adaptive thresholds: SKIP < {self.low_confidence_threshold:.2f}, "
                f"FULL >= {self.high_confidence_threshold:.2f} (base rate: {self._base_rate:.2f})"
            )

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
                'feature_version': self._feature_version,
                'feature_cols': self._trained_feature_cols,
                'base_rate': self._base_rate,
            }

            metrics = None
            if self.training_metrics:
                # Helper to sanitize NaN values (not valid JSON)
                def safe_float(val):
                    if val is None or (isinstance(val, float) and math.isnan(val)):
                        return None
                    return val

                metrics = {
                    'accuracy': safe_float(self.training_metrics.accuracy),
                    'auc_roc': safe_float(self.training_metrics.auc_roc),
                    'brier_score': safe_float(self.training_metrics.brier_score),
                    'win_rate': safe_float(self.training_metrics.win_rate_actual),
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
            self._feature_version = model_data.get('feature_version', 2)
            self._trained_feature_cols = model_data.get('feature_cols', self.FEATURE_COLS_V2)
            self._base_rate = model_data.get('base_rate')
            self._update_thresholds_from_base_rate()
            self.is_trained = True

            logger.info(f"Loaded FORTRESS ML Advisor v{self.model_version} (features V{self._feature_version}) from database")
            return True

        except Exception as e:
            logger.error(f"Failed to load model from database: {e}")
            return False

    def extract_features_from_chronicles(
        self,
        backtest_results: Dict[str, Any],
        include_gex: bool = True
    ) -> pd.DataFrame:
        """
        Extract ML features from CHRONICLES backtest results.

        V3: Adds cyclical day encoding, VRP, longer win rate horizon.
        Fixes training/inference mismatch for price_change_1d.

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
                from quant.chronicles_gex_calculator import enrich_trades_with_gex
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
        price_changes = []  # Track price changes for realized vol calculation

        for i, trade in enumerate(trades):
            # Rolling stats with 60-trade lookback (longer horizon, less leakage)
            lookback_60 = max(0, i - 60)
            recent_outcomes_60 = outcomes[lookback_60:i] if i > 0 else []

            win_rate_60d = sum(1 for o in recent_outcomes_60 if o == 'MAX_PROFIT') / len(recent_outcomes_60) if recent_outcomes_60 else 0.70

            # Parse date for cyclical day encoding
            trade_date = trade.get('trade_date', '')
            try:
                dt = datetime.strptime(trade_date, '%Y-%m-%d')
                day_of_week = dt.weekday()
            except Exception:
                day_of_week = 2  # Default to Wednesday

            # Cyclical encoding: sin/cos for day of week
            day_of_week_sin = math.sin(2 * math.pi * day_of_week / 5)
            day_of_week_cos = math.cos(2 * math.pi * day_of_week / 5)

            # Extract features
            vix = trade.get('vix', 20.0)
            open_price = trade.get('open_price', trade.get('underlying_price_entry', 5000))
            close_price = trade.get('close_price', trade.get('underlying_price_exit', open_price))

            # FIX: price_change_1d = previous trade's price change (not same-day)
            # This aligns with live prediction where we pass yesterday's change
            current_price_change = (close_price - open_price) / open_price * 100 if open_price > 0 else 0
            price_change_1d = price_changes[-1] if price_changes else 0  # Use PREVIOUS trade's change
            price_changes.append(current_price_change)

            expected_move = trade.get('expected_move_sd', trade.get('expected_move_1d', 50))
            expected_move_pct = expected_move / open_price * 100 if open_price > 0 else 1.0

            # VRP: expected move (IV proxy) - realized vol (5-trade rolling std of price changes)
            if len(price_changes) >= 5:
                recent_changes = price_changes[-5:]
                realized_vol_5d = (sum(c**2 for c in recent_changes) / len(recent_changes)) ** 0.5
            else:
                realized_vol_5d = expected_move_pct * 0.8  # Conservative fallback
            volatility_risk_premium = expected_move_pct - realized_vol_5d

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
                'vix_percentile_30d': 50,  # Recalculated below
                'vix_change_1d': 0,         # Recalculated below
                'day_of_week_sin': day_of_week_sin,
                'day_of_week_cos': day_of_week_cos,
                'price': open_price,
                'price_change_1d': price_change_1d,
                'expected_move_pct': expected_move_pct,
                'volatility_risk_premium': volatility_risk_premium,
                'win_rate_60d': win_rate_60d,
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

    def train_from_chronicles(
        self,
        backtest_results: Dict[str, Any],
        test_size: float = 0.2,
        min_samples: int = 100
    ) -> TrainingMetrics:
        """
        Train ML model from CHRONICLES backtest results.

        V3 improvements:
        - scale_pos_weight to handle class imbalance (IC ~70-90% win rate)
        - Brier score on held-out fold (not training data)
        - Adaptive thresholds based on learned base rate
        - V3 features: cyclical day encoding, VRP, 60-trade win rate

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
        df = self.extract_features_from_chronicles(backtest_results)

        if len(df) < min_samples:
            raise ValueError(f"Insufficient data: {len(df)} samples < {min_samples} required")

        logger.info(f"Training on {len(df)} trades from CHRONICLES backtest")

        # Prepare features and target
        X = df[self.FEATURE_COLS].values
        y = df['is_win'].values.astype(int)

        # Class imbalance: calculate scale_pos_weight
        # For IC trading with ~89% win rate, losses are underrepresented
        n_wins = int(y.sum())
        n_losses = int(len(y) - n_wins)
        if n_wins > 0 and n_losses > 0:
            scale_pos_weight = n_losses / n_wins  # ~0.11 for 89% win rate
        else:
            scale_pos_weight = 1.0
        logger.info(f"Class balance: {n_wins} wins, {n_losses} losses, scale_pos_weight={scale_pos_weight:.3f}")

        # Store base rate for adaptive thresholds
        self._base_rate = float(y.mean())

        # Scale features
        self.scaler = StandardScaler()
        X_scaled = self.scaler.fit_transform(X)

        # Time-series split for walk-forward validation
        n_splits = 5
        tscv = TimeSeriesSplit(n_splits=n_splits)

        # Train XGBoost with scale_pos_weight for class imbalance
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
            scale_pos_weight=scale_pos_weight,  # Handle class imbalance
            random_state=42,
            use_label_encoder=False,
            eval_metric='logloss',
            verbosity=0
        )

        # Cross-validation metrics (including held-out Brier scores)
        accuracies, precisions, recalls, f1s, aucs, briers = [], [], [], [], [], []

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
            briers.append(brier_score_loss(y_test, y_proba))  # Brier on held-out fold

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

        # Feature importances
        feature_importances = dict(zip(self.FEATURE_COLS, self.model.feature_importances_))

        # Build metrics (Brier from CV, not in-sample)
        self.training_metrics = TrainingMetrics(
            accuracy=np.mean(accuracies),
            precision=np.mean(precisions),
            recall=np.mean(recalls),
            f1_score=np.mean(f1s),
            auc_roc=np.mean(aucs),
            brier_score=np.mean(briers),  # FIX: CV Brier, not in-sample
            win_rate_predicted=self.calibrated_model.predict_proba(X_scaled)[:, 1].mean(),
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
        self._trained_feature_cols = self.FEATURE_COLS

        # Set adaptive thresholds based on base rate
        self._update_thresholds_from_base_rate()

        # Save model
        self._save_model()

        logger.info(f"Model V2.0.0 trained successfully (features V3):")
        logger.info(f"  Accuracy: {self.training_metrics.accuracy:.2%}")
        logger.info(f"  AUC-ROC: {self.training_metrics.auc_roc:.3f}")
        logger.info(f"  Brier Score (CV): {self.training_metrics.brier_score:.4f}")
        logger.info(f"  Win Rate (actual): {self.training_metrics.win_rate_actual:.2%}")
        logger.info(f"  Class balance: {n_wins}W / {n_losses}L (scale_pos_weight={scale_pos_weight:.3f})")
        logger.info(f"  Adaptive thresholds: SKIP < {self.low_confidence_threshold:.2f}, FULL >= {self.high_confidence_threshold:.2f}")
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
        # GEX features (V2+)
        gex_normalized: float = 0,
        gex_regime_positive: int = 0,
        gex_distance_to_flip_pct: float = 0,
        gex_between_walls: int = 1,
        # V3 features
        volatility_risk_premium: float = None,
        realized_vol_5d: float = None,
    ) -> MLPrediction:
        """
        Get ML prediction for today's trading decision.

        Backward compatible: accepts V1/V2/V3 parameters.
        Automatically uses the feature version the model was trained with.

        Args:
            vix: Current VIX level
            day_of_week: 0=Monday, 4=Friday
            price: Current SPX price
            price_change_1d: Yesterday's price change %
            expected_move_pct: Expected move as % of price
            win_rate_30d: Recent 30-day win rate (used as win_rate_60d for V3)
            vix_percentile_30d: VIX percentile in 30-day range
            vix_change_1d: VIX change from yesterday %
            gex_normalized: Scale-independent GEX (GEX / spot^2)
            gex_regime_positive: 1 if positive GEX regime, 0 otherwise
            gex_distance_to_flip_pct: Distance to flip point as %
            gex_between_walls: 1 if price between call/put walls
            volatility_risk_premium: IV - realized vol (V3 feature, auto-calculated if None)
            realized_vol_5d: 5-day realized vol (used to calculate VRP if provided)

        Returns:
            MLPrediction with advice and probability
        """
        if not self.is_trained:
            return self._fallback_prediction(vix, day_of_week, gex_regime_positive)

        # Calculate VRP if not provided
        if volatility_risk_premium is None:
            if realized_vol_5d is not None:
                volatility_risk_premium = expected_move_pct - realized_vol_5d
            else:
                # Approximate: VRP ~ VIX premium over typical realized vol
                volatility_risk_premium = expected_move_pct * 0.2  # ~20% VRP is typical

        # Build feature vector based on which version the model was trained with
        feature_version = getattr(self, '_feature_version', 2)

        if feature_version >= 3:
            # V3: cyclical day encoding, VRP, 60d win rate
            day_sin = math.sin(2 * math.pi * day_of_week / 5)
            day_cos = math.cos(2 * math.pi * day_of_week / 5)
            features = np.array([[
                vix,
                vix_percentile_30d,
                vix_change_1d,
                day_sin,
                day_cos,
                price_change_1d,
                expected_move_pct,
                volatility_risk_premium,
                win_rate_30d,  # Caller can pass 60d rate via this param
                gex_normalized,
                gex_regime_positive,
                gex_distance_to_flip_pct,
                gex_between_walls,
            ]])
            trained_cols = self.FEATURE_COLS
        elif feature_version == 2 or getattr(self, '_has_gex_features', True):
            # V2: integer day, win_rate_30d, no VRP
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
            trained_cols = self.FEATURE_COLS_V2
        else:
            # V1: no GEX
            features = np.array([[
                vix,
                vix_percentile_30d,
                vix_change_1d,
                day_of_week,
                price_change_1d,
                expected_move_pct,
                win_rate_30d,
            ]])
            trained_cols = self.FEATURE_COLS_V1

        # Scale
        features_scaled = self.scaler.transform(features)

        # Get calibrated probability
        if self.calibrated_model:
            proba = self.calibrated_model.predict_proba(features_scaled)[0]
        else:
            proba = self.model.predict_proba(features_scaled)[0]

        win_probability = proba[1]  # Probability of class 1 (win)

        # Determine advice based on adaptive thresholds
        if win_probability >= self.high_confidence_threshold:
            advice = TradingAdvice.TRADE_FULL
            suggested_risk = 10.0
        elif win_probability >= self.low_confidence_threshold:
            advice = TradingAdvice.TRADE_REDUCED
            # Scale risk between 3% and 8%
            threshold_range = self.high_confidence_threshold - self.low_confidence_threshold
            if threshold_range > 0:
                suggested_risk = 3.0 + (win_probability - self.low_confidence_threshold) / threshold_range * 5.0
            else:
                suggested_risk = 5.0
        else:
            advice = TradingAdvice.SKIP_TODAY
            suggested_risk = 0.0

        # Suggested SD multiplier based on probability relative to base rate
        base_rate = self._base_rate or 0.70
        if win_probability >= base_rate + 0.05:
            suggested_sd = 0.9  # Tighter strikes, more premium
        elif win_probability >= base_rate - 0.05:
            suggested_sd = 1.0  # Standard
        else:
            suggested_sd = 1.2  # Wider strikes, safer

        # Top factors
        feature_importance = dict(zip(trained_cols, self.model.feature_importances_))
        top_factors = sorted(feature_importance.items(), key=lambda x: -x[1])[:3]

        # Confidence: calibrated, no artificial inflation
        confidence = min(100, win_probability * 100)

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

        This creates the feedback loop - FORTRESS outcomes feed back
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
                CREATE TABLE IF NOT EXISTS fortress_ml_outcomes (
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
                INSERT INTO fortress_ml_outcomes (
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
        Retrain model incorporating new FORTRESS outcomes.

        V3 fixes:
        - Uses TimeSeriesSplit for proper walk-forward validation
        - Adds scale_pos_weight for class imbalance
        - Computes metrics on held-out folds (not training data)
        - Updates adaptive thresholds

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
                FROM fortress_ml_outcomes
                ORDER BY trade_date
            """

            df = pd.read_sql(query, conn)
            conn.close()

            if len(df) < min_new_samples:
                logger.info(f"Insufficient outcomes for retraining: {len(df)} < {min_new_samples}")
                return None

            logger.info(f"Retraining with {len(df)} FORTRESS outcomes")

            # Compute V3 features from stored outcomes
            # Cyclical day encoding
            df['day_of_week_sin'] = df['day_of_week'].apply(lambda d: math.sin(2 * math.pi * d / 5))
            df['day_of_week_cos'] = df['day_of_week'].apply(lambda d: math.cos(2 * math.pi * d / 5))

            # VRP approximation from available data
            realized_vol_5d = df['price_change_1d'].rolling(5, min_periods=1).apply(
                lambda x: (sum(v**2 for v in x) / len(x)) ** 0.5
            ).fillna(0)
            df['volatility_risk_premium'] = df['expected_move_pct'] - realized_vol_5d

            # 60-trade win rate (longer horizon than 30)
            df['win_rate_60d'] = df['is_win'].rolling(60, min_periods=1).mean().shift(1).fillna(0.70)

            # Prepare features (V3)
            feature_cols = self.FEATURE_COLS
            X = df[feature_cols].values
            y = df['is_win'].values.astype(int)

            # Class imbalance
            n_wins = int(y.sum())
            n_losses = int(len(y) - n_wins)
            scale_pos_weight = n_losses / n_wins if n_wins > 0 and n_losses > 0 else 1.0

            # Store base rate
            self._base_rate = float(y.mean())

            # Scale
            self.scaler = StandardScaler()
            X_scaled = self.scaler.fit_transform(X)

            # Walk-forward validation (proper held-out metrics)
            n_splits = min(5, len(df) // 20)  # Ensure enough samples per fold
            if n_splits < 2:
                n_splits = 2

            tscv = TimeSeriesSplit(n_splits=n_splits)
            accuracies, precisions, recalls, f1s, aucs, briers = [], [], [], [], [], []

            self.model = xgb.XGBClassifier(
                n_estimators=150,
                max_depth=4,
                learning_rate=0.1,
                min_child_weight=10,
                subsample=0.8,
                colsample_bytree=0.8,
                reg_alpha=0.1,
                reg_lambda=1.0,
                scale_pos_weight=scale_pos_weight,
                random_state=42,
                use_label_encoder=False,
                eval_metric='logloss',
                verbosity=0
            )

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
                briers.append(brier_score_loss(y_test, y_proba))

                try:
                    aucs.append(roc_auc_score(y_test, y_proba))
                except ValueError:
                    aucs.append(0.5)

            # Final training on all data
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

            feature_importances = dict(zip(feature_cols, self.model.feature_importances_))

            self.training_metrics = TrainingMetrics(
                accuracy=np.mean(accuracies),
                precision=np.mean(precisions),
                recall=np.mean(recalls),
                f1_score=np.mean(f1s),
                auc_roc=np.mean(aucs),
                brier_score=np.mean(briers),  # CV Brier, not in-sample
                win_rate_predicted=self.calibrated_model.predict_proba(X_scaled)[:, 1].mean(),
                win_rate_actual=y.mean(),
                total_samples=len(df),
                train_samples=int(len(df) * 0.8),
                test_samples=int(len(df) * 0.2),
                positive_samples=n_wins,
                negative_samples=n_losses,
                feature_importances=feature_importances,
                training_date=datetime.now().isoformat(),
                model_version=self.model_version
            )

            self._feature_version = 3
            self._trained_feature_cols = feature_cols
            self._update_thresholds_from_base_rate()
            self._save_model()

            logger.info(f"Retrained model v{self.model_version} (features V3)")
            logger.info(f"  Accuracy (CV): {self.training_metrics.accuracy:.2%}")
            logger.info(f"  AUC-ROC (CV): {self.training_metrics.auc_roc:.3f}")
            logger.info(f"  Win Rate: {self.training_metrics.win_rate_actual:.2%}")
            logger.info(f"  Class balance: {n_wins}W / {n_losses}L")

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
        - V3: adaptive threshold info, VRP sensitivity
        """
        if not self.is_trained:
            return {'error': 'Model not trained'}

        insights = {
            'model_version': self.model_version,
            'feature_version': getattr(self, '_feature_version', 2),
            'training_date': self.training_metrics.training_date if self.training_metrics else None,
            'overall_performance': {
                'accuracy': self.training_metrics.accuracy if self.training_metrics else None,
                'auc_roc': self.training_metrics.auc_roc if self.training_metrics else None,
                'brier_score': self.training_metrics.brier_score if self.training_metrics else None,
                'actual_win_rate': self.training_metrics.win_rate_actual if self.training_metrics else None,
            },
            'adaptive_thresholds': {
                'base_rate': self._base_rate,
                'skip_below': self.low_confidence_threshold,
                'trade_full_above': self.high_confidence_threshold,
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

            # Generate recommendations based on top feature
            top_feature = sorted_features[0][0]

            if top_feature == 'vix':
                insights['pattern_recommendations'].append(
                    "VIX level is the strongest predictor. Consider VIX-based position sizing."
                )
            elif 'day_of_week' in top_feature:
                insights['pattern_recommendations'].append(
                    "Day of week matters significantly. Review performance by day."
                )
            elif 'win_rate' in top_feature:
                insights['pattern_recommendations'].append(
                    "Recent performance predicts future results. Momentum effect detected."
                )
            elif top_feature == 'volatility_risk_premium':
                insights['pattern_recommendations'].append(
                    "VRP is the strongest predictor — premium selling edge is data-driven."
                )
            elif 'gex' in top_feature:
                insights['pattern_recommendations'].append(
                    "GEX features dominate — gamma exposure regime drives IC outcomes."
                )

        # VIX sensitivity analysis
        if self.is_trained:
            vix_sensitivity = []
            for vix in [12, 15, 18, 20, 25, 30, 35]:
                pred = self.predict(vix=vix, day_of_week=2)
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


# Convenience functions for integration with FORTRESS

_advisor: Optional[FortressMLAdvisor] = None

def get_advisor() -> FortressMLAdvisor:
    """Get or create the ML advisor singleton"""
    global _advisor
    if _advisor is None:
        _advisor = FortressMLAdvisor()
    return _advisor


def get_trading_advice(
    vix: float,
    day_of_week: int = None,
    price: float = 5000,
    **kwargs
) -> MLPrediction:
    """
    Get trading advice for FORTRESS.

    Quick integration point - call this from FORTRESS before trading.

    Example:
        from quant.fortress_ml_advisor import get_trading_advice

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
    Train the ML advisor from CHRONICLES backtest results.

    Example:
        from backtest.zero_dte_hybrid_fixed import HybridFixedBacktester
        from quant.fortress_ml_advisor import train_from_backtest

        # Run backtest
        backtester = HybridFixedBacktester(start_date='2021-01-01')
        results = backtester.run()

        # Train ML model
        metrics = train_from_backtest(results)
        print(f"Model trained with {metrics.accuracy:.1%} accuracy")
    """
    advisor = get_advisor()
    return advisor.train_from_chronicles(backtest_results)


if __name__ == "__main__":
    # Demo usage
    print("=" * 60)
    print("FORTRESS ML Advisor - Demo")
    print("=" * 60)

    advisor = get_advisor()

    if not advisor.is_trained:
        print("\nModel not trained. Run a CHRONICLES backtest first:")
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
