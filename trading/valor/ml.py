"""
VALOR ML Advisor - Machine Learning for MES Futures Scalping
================================================================

PURPOSE:
This module creates an ML-enhanced win probability estimator for VALOR.
Replaces the Bayesian probability estimator with an XGBoost model trained
on actual trade outcomes from valor_scan_activity.

PATTERN:
Follows the exact same architecture as WISDOM (quant/fortress_ml_advisor.py):
- XGBoost classifier with calibrated probabilities
- Model persistence in PostgreSQL (survives Render deploys)
- Fallback to Bayesian when ML not available

FEEDBACK LOOP:
    Scan Activity → Extract Features → Train Model
            ^                              |
            |                              v
    Record Outcome <-- Trade <-- ML Probability
"""

import os
import sys
import math
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

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

# XGBoost
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


@dataclass
class ValorTrainingMetrics:
    """Metrics from VALOR model training"""
    accuracy: float
    precision: float
    recall: float
    f1_score: float
    auc_roc: float
    brier_score: float  # Calibration quality

    # Win/loss breakdown
    win_rate_predicted: float
    win_rate_actual: float

    # Data info
    total_samples: int
    train_samples: int
    test_samples: int
    wins: int
    losses: int

    # By regime
    positive_gamma_accuracy: Optional[float]
    negative_gamma_accuracy: Optional[float]

    # Feature importance
    feature_importances: Dict[str, float]

    training_date: str
    model_version: str


class ValorMLAdvisor:
    """
    ML Advisor for VALOR MES Futures Scalping.

    Uses scan_activity trade outcomes to train a model that predicts:
    - Win probability for each signal
    - Replaces Bayesian estimator after sufficient data

    The model learns patterns like:
    - Gamma regime effects on win rate
    - Time of day patterns
    - Distance from flip point thresholds
    - VIX conditions that correlate with wins/losses
    """

    # Feature columns for prediction
    # Must match exactly between training and prediction!
    FEATURE_COLS = [
        'vix',
        'atr',
        'gamma_regime_encoded',  # 0=NEGATIVE, 1=NEUTRAL, 2=POSITIVE
        'distance_to_flip_pct',
        'distance_to_call_wall_pct',
        'distance_to_put_wall_pct',
        'day_of_week',
        'hour_of_day',
        'is_overnight',
        'positive_gamma_win_rate',
        'negative_gamma_win_rate',
        'signal_confidence',
    ]

    # Model name for persistence (must be unique across all bots)
    MODEL_NAME = 'valor_ml'

    def __init__(self):
        self.model = None
        self.calibrated_model = None
        self.scaler = None
        self.is_trained = False
        self.training_metrics: Optional[ValorTrainingMetrics] = None
        self.model_version = "0.0.0"

        # Thresholds
        self.min_samples_for_training = 50

        # Try to load existing model from database
        self._load_model()

    def clear_model(self) -> bool:
        """
        Clear the trained model and reset to untrained state.

        Used when user rejects a newly trained model.
        Also removes the model from the database.
        """
        try:
            self.model = None
            self.calibrated_model = None
            self.scaler = None
            self.is_trained = False
            self.training_metrics = None
            self.model_version = "0.0.0"

            # Try to delete from database
            try:
                from quant.model_persistence import delete_model_from_db
                delete_model_from_db(self.MODEL_NAME)
                logger.info("Deleted VALOR ML model from database")
            except ImportError:
                # delete_model_from_db may not exist, try direct SQL
                try:
                    from database_adapter import DatabaseAdapter
                    db = DatabaseAdapter()
                    db.execute(
                        "DELETE FROM ml_models WHERE name = %s",
                        (self.MODEL_NAME,)
                    )
                    logger.info("Deleted VALOR ML model from database (direct SQL)")
                except Exception as e:
                    logger.warning(f"Could not delete model from database: {e}")
            except Exception as e:
                logger.warning(f"Could not delete model from database: {e}")

            logger.info("VALOR ML model cleared successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to clear VALOR ML model: {e}")
            return False

    def _load_model(self) -> bool:
        """Load pre-trained model from database"""
        try:
            from quant.model_persistence import load_model_from_db, get_model_info

            model_data = load_model_from_db(self.MODEL_NAME)
            if model_data is None:
                logger.info("No VALOR ML model found in database")
                return False

            self.model = model_data.get('model')
            self.calibrated_model = model_data.get('calibrated_model')
            self.scaler = model_data.get('scaler')
            self.training_metrics = model_data.get('metrics')
            self.model_version = model_data.get('version', '1.0.0')
            self.is_trained = True

            logger.info(f"Loaded VALOR ML model v{self.model_version} from database")
            return True

        except Exception as e:
            logger.warning(f"Failed to load VALOR ML model from database: {e}")
            return False

    def save_to_db(self, training_records: int = None) -> bool:
        """Save trained model to database for persistence"""
        if not self.is_trained:
            logger.warning("Cannot save untrained model to database")
            return False

        try:
            from quant.model_persistence import save_model_to_db

            model_data = {
                'model': self.model,
                'calibrated_model': self.calibrated_model,
                'scaler': self.scaler,
                'metrics': self.training_metrics,
                'version': self.model_version,
            }

            # Prepare metrics for JSON storage
            metrics = None
            if self.training_metrics:
                def safe_float(val):
                    if val is None or (isinstance(val, float) and math.isnan(val)):
                        return None
                    return val

                metrics = {
                    'accuracy': safe_float(self.training_metrics.accuracy),
                    'auc_roc': safe_float(self.training_metrics.auc_roc),
                    'brier_score': safe_float(self.training_metrics.brier_score),
                    'win_rate': safe_float(self.training_metrics.win_rate_actual),
                    'precision': safe_float(self.training_metrics.precision),
                    'recall': safe_float(self.training_metrics.recall),
                }

            return save_model_to_db(
                self.MODEL_NAME,
                model_data,
                metrics=metrics,
                training_records=training_records
            )
        except Exception as e:
            logger.error(f"Failed to save VALOR ML model to database: {e}")
            return False

    def get_training_data(self, use_new_params_only: bool = True) -> Optional[pd.DataFrame]:
        """
        Fetch training data from valor_scan_activity.

        Only includes:
        - Scans that resulted in trades (trade_executed = true)
        - Trades with recorded outcomes (trade_outcome IS NOT NULL)
        - If use_new_params_only=True, only trades AFTER PARAMETER_VERSION_DATE

        Args:
            use_new_params_only: If True, only return trades after parameter version date.
                                 This ensures ML trains on quality data with balanced risk/reward.
        """
        if not DB_AVAILABLE or not ML_AVAILABLE:
            return None

        try:
            from .models import PARAMETER_VERSION_DATE
            conn = get_connection()

            # Build query with optional date filter
            if use_new_params_only:
                query = f"""
                    SELECT
                        scan_time,
                        vix,
                        atr,
                        gamma_regime,
                        distance_to_flip_pct,
                        distance_to_call_wall_pct,
                        distance_to_put_wall_pct,
                        day_of_week,
                        hour_of_day,
                        is_overnight_session,
                        positive_gamma_win_rate,
                        negative_gamma_win_rate,
                        signal_confidence,
                        trade_outcome,
                        realized_pnl
                    FROM valor_scan_activity
                    WHERE trade_executed = true
                      AND trade_outcome IS NOT NULL
                      AND scan_time >= '{PARAMETER_VERSION_DATE}'::timestamp
                    ORDER BY scan_time ASC
                """
                logger.info(f"Fetching training data ONLY after {PARAMETER_VERSION_DATE} (new parameters)")
            else:
                query = """
                    SELECT
                        scan_time,
                        vix,
                        atr,
                        gamma_regime,
                        distance_to_flip_pct,
                        distance_to_call_wall_pct,
                        distance_to_put_wall_pct,
                        day_of_week,
                        hour_of_day,
                        is_overnight_session,
                        positive_gamma_win_rate,
                        negative_gamma_win_rate,
                        signal_confidence,
                        trade_outcome,
                        realized_pnl
                    FROM valor_scan_activity
                    WHERE trade_executed = true
                      AND trade_outcome IS NOT NULL
                    ORDER BY scan_time ASC
                """

            df = pd.read_sql(query, conn)
            conn.close()

            if len(df) == 0:
                if use_new_params_only:
                    logger.warning(f"No completed trades found after {PARAMETER_VERSION_DATE} - collect more data with new parameters")
                else:
                    logger.warning("No completed trades found in scan_activity")
                return None

            logger.info(f"Fetched {len(df)} completed trades for training")
            return df

        except Exception as e:
            logger.error(f"Failed to fetch training data: {e}")
            return None

    def get_training_data_stats(self) -> Dict[str, Any]:
        """
        Get statistics about available training data.

        Returns counts of trades before/after parameter version date,
        so users know when enough new data is available for ML training.
        """
        if not DB_AVAILABLE:
            return {'error': 'Database not available'}

        try:
            from .models import PARAMETER_VERSION, PARAMETER_VERSION_DATE, PARAMETER_VERSION_DESCRIPTION
            conn = get_connection()
            cursor = conn.cursor()

            # Get total trades
            cursor.execute("""
                SELECT COUNT(*) FROM valor_scan_activity
                WHERE trade_executed = true AND trade_outcome IS NOT NULL
            """)
            total_trades = cursor.fetchone()[0]

            # Get old parameter trades (before version date)
            cursor.execute(f"""
                SELECT COUNT(*),
                       SUM(CASE WHEN trade_outcome = 'WIN' THEN 1 ELSE 0 END),
                       SUM(CASE WHEN trade_outcome = 'LOSS' THEN 1 ELSE 0 END)
                FROM valor_scan_activity
                WHERE trade_executed = true
                  AND trade_outcome IS NOT NULL
                  AND scan_time < '{PARAMETER_VERSION_DATE}'::timestamp
            """)
            old_row = cursor.fetchone()
            old_trades = old_row[0] or 0
            old_wins = old_row[1] or 0
            old_losses = old_row[2] or 0

            # Get new parameter trades (after version date)
            cursor.execute(f"""
                SELECT COUNT(*),
                       SUM(CASE WHEN trade_outcome = 'WIN' THEN 1 ELSE 0 END),
                       SUM(CASE WHEN trade_outcome = 'LOSS' THEN 1 ELSE 0 END)
                FROM valor_scan_activity
                WHERE trade_executed = true
                  AND trade_outcome IS NOT NULL
                  AND scan_time >= '{PARAMETER_VERSION_DATE}'::timestamp
            """)
            new_row = cursor.fetchone()
            new_trades = new_row[0] or 0
            new_wins = new_row[1] or 0
            new_losses = new_row[2] or 0

            conn.close()

            # Calculate if ready for ML training
            min_for_training = 50
            ready_for_ml = new_trades >= min_for_training
            trades_needed = max(0, min_for_training - new_trades)

            return {
                'parameter_version': PARAMETER_VERSION,
                'parameter_version_date': PARAMETER_VERSION_DATE,
                'parameter_description': PARAMETER_VERSION_DESCRIPTION,
                'total_trades': total_trades,
                'old_parameter_trades': {
                    'count': old_trades,
                    'wins': old_wins,
                    'losses': old_losses,
                    'win_rate': round(old_wins / old_trades * 100, 1) if old_trades > 0 else 0
                },
                'new_parameter_trades': {
                    'count': new_trades,
                    'wins': new_wins,
                    'losses': new_losses,
                    'win_rate': round(new_wins / new_trades * 100, 1) if new_trades > 0 else 0
                },
                'ready_for_ml_training': ready_for_ml,
                'trades_needed_for_ml': trades_needed,
                'recommendation': (
                    "Ready to train ML on new parameter data!" if ready_for_ml
                    else f"Collect {trades_needed} more trades with new parameters before training ML"
                )
            }

        except Exception as e:
            logger.error(f"Failed to get training data stats: {e}")
            return {'error': str(e)}

    def _prepare_features(self, df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
        """
        Prepare features and target from raw data.

        This function is used by BOTH training and prediction to ensure
        feature alignment. NEVER create separate feature extraction logic!
        """
        # Encode gamma regime: NEGATIVE=0, NEUTRAL=1, POSITIVE=2
        regime_map = {'NEGATIVE': 0, 'NEUTRAL': 1, 'POSITIVE': 2}
        df['gamma_regime_encoded'] = df['gamma_regime'].map(regime_map).fillna(1)

        # Encode overnight session
        df['is_overnight'] = df['is_overnight_session'].astype(int) if 'is_overnight_session' in df.columns else 0

        # Fill missing values with sensible defaults
        df['vix'] = df['vix'].fillna(20.0)
        df['atr'] = df['atr'].fillna(15.0)
        df['distance_to_flip_pct'] = df['distance_to_flip_pct'].fillna(0)
        df['distance_to_call_wall_pct'] = df['distance_to_call_wall_pct'].fillna(1.5)
        df['distance_to_put_wall_pct'] = df['distance_to_put_wall_pct'].fillna(1.5)
        df['day_of_week'] = df['day_of_week'].fillna(2)  # Wednesday
        df['hour_of_day'] = df['hour_of_day'].fillna(10)
        df['positive_gamma_win_rate'] = df['positive_gamma_win_rate'].fillna(0.5)
        df['negative_gamma_win_rate'] = df['negative_gamma_win_rate'].fillna(0.5)
        df['signal_confidence'] = df['signal_confidence'].fillna(0.7)

        # Extract features in exact column order
        X = df[self.FEATURE_COLS].values

        # Target: WIN = 1, LOSS = 0
        y = (df['trade_outcome'] == 'WIN').astype(int).values

        return X, y

    def train(self, min_samples: int = None, use_new_params_only: bool = True) -> Optional[ValorTrainingMetrics]:
        """
        Train the ML model from scan_activity data.

        Args:
            min_samples: Minimum samples required (default: 50)
            use_new_params_only: If True, only train on trades after PARAMETER_VERSION_DATE.
                                 This ensures the model learns from quality data with
                                 balanced risk/reward parameters. Set to False to train
                                 on ALL historical data (not recommended).

        Returns:
            ValorTrainingMetrics if successful, None otherwise
        """
        if not ML_AVAILABLE:
            raise ImportError("ML libraries required. Install: pip install scikit-learn pandas numpy")

        if not HAS_XGBOOST:
            raise ImportError("XGBoost required. Install: pip install xgboost")

        min_samples = min_samples or self.min_samples_for_training

        # Fetch training data (filtered by parameter version if requested)
        df = self.get_training_data(use_new_params_only=use_new_params_only)
        if df is None or len(df) < min_samples:
            sample_count = len(df) if df is not None else 0
            raise ValueError(f"Insufficient data: {sample_count} samples < {min_samples} required")

        logger.info(f"Training VALOR ML on {len(df)} trades")

        # Prepare features and target
        X, y = self._prepare_features(df)

        # Check for class balance
        n_wins = y.sum()
        n_losses = len(y) - n_wins
        logger.info(f"Class balance: {n_wins} wins, {n_losses} losses ({n_wins/len(y)*100:.1f}% win rate)")

        if n_wins < 5 or n_losses < 5:
            raise ValueError(f"Insufficient class balance: {n_wins} wins, {n_losses} losses. Need at least 5 of each.")

        # Scale features
        self.scaler = StandardScaler()
        X_scaled = self.scaler.fit_transform(X)

        # Time-series split for walk-forward validation
        n_splits = min(5, len(df) // 20)  # At least 20 samples per fold
        tscv = TimeSeriesSplit(n_splits=max(2, n_splits))

        # Train XGBoost (matching WISDOM's hyperparameters)
        self.model = xgb.XGBClassifier(
            n_estimators=100,  # Fewer trees for smaller dataset
            max_depth=3,       # Shallower to prevent overfitting
            learning_rate=0.1,
            min_child_weight=5,
            subsample=0.8,
            colsample_bytree=0.8,
            reg_alpha=0.1,
            reg_lambda=1.0,
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

        # Calibrate probabilities
        self.calibrated_model = CalibratedClassifierCV(
            self.model, method='isotonic', cv=3
        )
        self.calibrated_model.fit(X_scaled, y)

        # Calculate Brier score (calibration quality)
        y_proba_full = self.calibrated_model.predict_proba(X_scaled)[:, 1]
        brier = brier_score_loss(y, y_proba_full)

        # Feature importances
        feature_importances = dict(zip(self.FEATURE_COLS, self.model.feature_importances_))

        # Calculate by-regime accuracy
        df['gamma_regime_encoded'] = df['gamma_regime'].map({'NEGATIVE': 0, 'NEUTRAL': 1, 'POSITIVE': 2}).fillna(1)
        pos_mask = df['gamma_regime_encoded'] == 2
        neg_mask = df['gamma_regime_encoded'] == 0

        pos_accuracy = None
        neg_accuracy = None

        if pos_mask.sum() >= 10:
            y_pred_pos = self.model.predict(X_scaled[pos_mask])
            pos_accuracy = accuracy_score(y[pos_mask], y_pred_pos)

        if neg_mask.sum() >= 10:
            y_pred_neg = self.model.predict(X_scaled[neg_mask])
            neg_accuracy = accuracy_score(y[neg_mask], y_pred_neg)

        # Build metrics
        self.training_metrics = ValorTrainingMetrics(
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
            wins=int(n_wins),
            losses=int(n_losses),
            positive_gamma_accuracy=pos_accuracy,
            negative_gamma_accuracy=neg_accuracy,
            feature_importances=feature_importances,
            training_date=datetime.now().isoformat(),
            model_version="1.0.0"
        )

        self.is_trained = True
        self.model_version = "1.0.0"

        # Save to database
        self.save_to_db(training_records=len(df))

        logger.info(f"VALOR ML trained successfully:")
        logger.info(f"  Accuracy: {self.training_metrics.accuracy:.2%}")
        logger.info(f"  AUC-ROC: {self.training_metrics.auc_roc:.3f}")
        logger.info(f"  Win Rate (actual): {self.training_metrics.win_rate_actual:.2%}")
        logger.info(f"  Top features: {sorted(feature_importances.items(), key=lambda x: -x[1])[:3]}")

        return self.training_metrics

    def predict(
        self,
        vix: float,
        atr: float,
        gamma_regime: str,
        distance_to_flip_pct: float,
        distance_to_call_wall_pct: float,
        distance_to_put_wall_pct: float,
        day_of_week: int,
        hour_of_day: int,
        is_overnight: bool,
        positive_gamma_win_rate: float,
        negative_gamma_win_rate: float,
        signal_confidence: float
    ) -> Tuple[float, str]:
        """
        Get ML prediction for win probability.

        Returns:
            Tuple of (win_probability, source)
            source is "ML" or "BAYESIAN" (fallback)
        """
        if not self.is_trained or self.model is None:
            # Fallback to Bayesian
            return self._bayesian_fallback(gamma_regime, positive_gamma_win_rate, negative_gamma_win_rate), "BAYESIAN"

        try:
            # Encode gamma regime
            regime_map = {'NEGATIVE': 0, 'NEUTRAL': 1, 'POSITIVE': 2}
            gamma_regime_encoded = regime_map.get(gamma_regime, 1)

            # Prepare features in exact column order (must match FEATURE_COLS!)
            features = np.array([[
                vix,
                atr,
                gamma_regime_encoded,
                distance_to_flip_pct,
                distance_to_call_wall_pct,
                distance_to_put_wall_pct,
                day_of_week,
                hour_of_day,
                int(is_overnight),
                positive_gamma_win_rate,
                negative_gamma_win_rate,
                signal_confidence,
            ]])

            # Scale
            features_scaled = self.scaler.transform(features)

            # Get calibrated probability
            if self.calibrated_model:
                proba = self.calibrated_model.predict_proba(features_scaled)[0]
            else:
                proba = self.model.predict_proba(features_scaled)[0]

            win_probability = proba[1]  # Probability of class 1 (win)

            return win_probability, "ML"

        except Exception as e:
            logger.warning(f"ML prediction failed, falling back to Bayesian: {e}")
            return self._bayesian_fallback(gamma_regime, positive_gamma_win_rate, negative_gamma_win_rate), "BAYESIAN"

    def _bayesian_fallback(
        self,
        gamma_regime: str,
        positive_gamma_win_rate: float,
        negative_gamma_win_rate: float
    ) -> float:
        """Bayesian fallback when ML not available"""
        if gamma_regime == 'POSITIVE':
            return positive_gamma_win_rate
        elif gamma_regime == 'NEGATIVE':
            return negative_gamma_win_rate
        else:
            # Neutral - blend both
            return (positive_gamma_win_rate + negative_gamma_win_rate) / 2

    def get_feature_importance(self) -> List[Dict[str, Any]]:
        """Get feature importance rankings"""
        if not self.is_trained or not self.training_metrics:
            return []

        importances = self.training_metrics.feature_importances
        total = sum(importances.values()) if importances else 1

        sorted_features = sorted(importances.items(), key=lambda x: -x[1])

        return [
            {
                'rank': i + 1,
                'name': name,
                'importance': round(imp, 4),
                'importance_pct': round(imp / total * 100, 1)
            }
            for i, (name, imp) in enumerate(sorted_features)
        ]

    def get_status(self) -> Dict[str, Any]:
        """Get model status for API/UI"""
        return {
            'is_trained': self.is_trained,
            'model_version': self.model_version,
            'training_date': self.training_metrics.training_date if self.training_metrics else None,
            'accuracy': self.training_metrics.accuracy if self.training_metrics else None,
            'auc_roc': self.training_metrics.auc_roc if self.training_metrics else None,
            'samples': self.training_metrics.total_samples if self.training_metrics else 0,
            'win_rate': self.training_metrics.win_rate_actual if self.training_metrics else None,
        }


# Singleton instance
_advisor: Optional[ValorMLAdvisor] = None


def get_valor_ml_advisor() -> ValorMLAdvisor:
    """Get or create the VALOR ML advisor singleton"""
    global _advisor
    if _advisor is None:
        _advisor = ValorMLAdvisor()
    return _advisor


def get_training_data_stats() -> Dict[str, Any]:
    """
    Get statistics about available training data (old vs new parameters).

    Convenience function for API use.
    """
    advisor = get_valor_ml_advisor()
    return advisor.get_training_data_stats()


def get_ml_win_probability(
    vix: float,
    atr: float,
    gamma_regime: str,
    distance_to_flip_pct: float,
    distance_to_call_wall_pct: float,
    distance_to_put_wall_pct: float,
    day_of_week: int,
    hour_of_day: int,
    is_overnight: bool,
    positive_gamma_win_rate: float,
    negative_gamma_win_rate: float,
    signal_confidence: float
) -> Tuple[float, str]:
    """
    Get ML-enhanced win probability for a signal.

    Returns:
        Tuple of (win_probability, source)
        source is "ML" or "BAYESIAN"
    """
    advisor = get_valor_ml_advisor()
    return advisor.predict(
        vix=vix,
        atr=atr,
        gamma_regime=gamma_regime,
        distance_to_flip_pct=distance_to_flip_pct,
        distance_to_call_wall_pct=distance_to_call_wall_pct,
        distance_to_put_wall_pct=distance_to_put_wall_pct,
        day_of_week=day_of_week,
        hour_of_day=hour_of_day,
        is_overnight=is_overnight,
        positive_gamma_win_rate=positive_gamma_win_rate,
        negative_gamma_win_rate=negative_gamma_win_rate,
        signal_confidence=signal_confidence
    )
