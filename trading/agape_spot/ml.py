"""
AGAPE-SPOT ML Shadow Advisor - Machine Learning for Crypto Spot Trading
========================================================================

PURPOSE:
Shadow ML system that learns from AGAPE-SPOT trade outcomes and competes
with the Bayesian win tracker. Runs predictions in parallel ("shadow mode")
without affecting live trading until explicitly promoted.

LIFECYCLE:
  1. COLLECTING  - Not enough data (<50 closed trades)
  2. TRAINING    - Model trains on closed trades from agape_spot_scan_activity
  3. SHADOW      - Both Bayesian + ML predict, only Bayesian used for decisions
  4. ELIGIBLE    - ML beats Bayesian on Brier score over 150+ shadow predictions
  5. PROMOTED    - ML predictions used for trade gating (replaces Bayesian)

PROMOTION CRITERIA:
  - 150+ shadow predictions with resolved outcomes
  - ML Brier score at least 5% better than Bayesian
  - No catastrophic misses (>80% confidence on loss) more than 10% of the time

PATTERN:
Follows VALOR ML advisor (trading/valor/ml.py) architecture:
- XGBoost classifier with calibrated probabilities
- Model persistence in PostgreSQL (survives Render deploys)
- Fallback to Bayesian when ML not available or not promoted
"""

import os
import sys
import math
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

try:
    import numpy as np
    import pandas as pd
    from sklearn.preprocessing import StandardScaler
    from sklearn.model_selection import TimeSeriesSplit
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.metrics import (
        accuracy_score, precision_score, recall_score, f1_score,
        roc_auc_score, brier_score_loss,
    )
    ML_AVAILABLE = True
except ImportError:
    ML_AVAILABLE = False
    np = None
    pd = None

try:
    import xgboost as xgb
    HAS_XGBOOST = True
except ImportError:
    HAS_XGBOOST = False

try:
    from database_adapter import get_connection
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Promotion criteria constants
# ---------------------------------------------------------------------------
MIN_SHADOW_PREDICTIONS = 150
BRIER_IMPROVEMENT_THRESHOLD = 0.05  # ML must be 5% better
MAX_CATASTROPHIC_MISS_RATE = 0.10   # <=10% high-confidence losses allowed
AUTO_RETRAIN_INTERVAL = 25          # Retrain every 25 new closed trades


@dataclass
class SpotMLTrainingMetrics:
    """Metrics from AGAPE-SPOT model training."""
    accuracy: float
    precision: float
    recall: float
    f1_score: float
    auc_roc: float
    brier_score: float

    win_rate_predicted: float
    win_rate_actual: float

    total_samples: int
    wins: int
    losses: int

    positive_funding_accuracy: Optional[float]
    negative_funding_accuracy: Optional[float]

    feature_importances: Dict[str, float]
    training_date: str
    model_version: str


@dataclass
class ShadowComparison:
    """Comparison between ML and Bayesian shadow predictions."""
    total_predictions: int = 0
    resolved_predictions: int = 0

    ml_brier: float = 1.0
    bayesian_brier: float = 1.0
    brier_improvement_pct: float = 0.0

    ml_accuracy: float = 0.0
    bayesian_accuracy: float = 0.0

    ml_catastrophic_misses: int = 0
    catastrophic_miss_rate: float = 0.0

    is_eligible: bool = False
    promotion_blockers: List[str] = field(default_factory=list)


class AgapeSpotMLAdvisor:
    """
    ML Advisor for AGAPE-SPOT crypto spot trading.

    Trains on closed trade outcomes from agape_spot_scan_activity.
    Runs in shadow mode alongside Bayesian until promoted.

    Features are crypto-native: funding rate, LS ratio, squeeze risk,
    volatility regime, chop index — no GEX/gamma walls.
    """

    FEATURE_COLS = [
        'funding_rate',
        'funding_regime_encoded',     # 0=NEGATIVE, 1=NEUTRAL, 2=POSITIVE
        'ls_ratio',
        'ls_bias_encoded',            # -1=SHORT, 0=NEUTRAL, 1=LONG
        'squeeze_risk_encoded',       # 0=LOW, 1=MEDIUM, 2=HIGH
        'crypto_gex',
        'oracle_win_prob',
        'day_of_week',
        'hour_of_day',
        'positive_funding_win_rate',
        'negative_funding_win_rate',
        'chop_index',
    ]

    MODEL_NAME = 'agape_spot_ml'

    def __init__(self):
        self.model = None
        self.calibrated_model = None
        self.scaler = None
        self.is_trained = False
        self.training_metrics: Optional[SpotMLTrainingMetrics] = None
        self.model_version = "0.0.0"
        self.min_samples_for_training = 50
        self._load_model()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load_model(self) -> bool:
        """Load pre-trained model from database."""
        try:
            from quant.model_persistence import load_model_from_db
            model_data = load_model_from_db(self.MODEL_NAME)
            if model_data is None:
                logger.info("No AGAPE-SPOT ML model found in database")
                return False

            self.model = model_data.get('model')
            self.calibrated_model = model_data.get('calibrated_model')
            self.scaler = model_data.get('scaler')
            self.training_metrics = model_data.get('metrics')
            self.model_version = model_data.get('version', '1.0.0')
            self.is_trained = True
            logger.info(f"Loaded AGAPE-SPOT ML model v{self.model_version}")
            return True
        except Exception as e:
            logger.warning(f"Failed to load AGAPE-SPOT ML model: {e}")
            return False

    def save_to_db(self, training_records: int = None) -> bool:
        """Save trained model to database."""
        if not self.is_trained:
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

            def safe_float(val):
                if val is None or (isinstance(val, float) and math.isnan(val)):
                    return None
                return val

            metrics = None
            if self.training_metrics:
                metrics = {
                    'accuracy': safe_float(self.training_metrics.accuracy),
                    'auc_roc': safe_float(self.training_metrics.auc_roc),
                    'brier_score': safe_float(self.training_metrics.brier_score),
                    'win_rate': safe_float(self.training_metrics.win_rate_actual),
                    'precision': safe_float(self.training_metrics.precision),
                    'recall': safe_float(self.training_metrics.recall),
                }

            return save_model_to_db(
                self.MODEL_NAME, model_data,
                metrics=metrics, training_records=training_records,
            )
        except Exception as e:
            logger.error(f"Failed to save AGAPE-SPOT ML model: {e}")
            return False

    def clear_model(self) -> bool:
        """Clear trained model (revoke/reject)."""
        try:
            self.model = None
            self.calibrated_model = None
            self.scaler = None
            self.is_trained = False
            self.training_metrics = None
            self.model_version = "0.0.0"
            try:
                from quant.model_persistence import delete_model_from_db
                delete_model_from_db(self.MODEL_NAME)
            except Exception:
                pass
            logger.info("AGAPE-SPOT ML model cleared")
            return True
        except Exception as e:
            logger.error(f"Failed to clear AGAPE-SPOT ML model: {e}")
            return False

    # ------------------------------------------------------------------
    # Training
    # ------------------------------------------------------------------

    def get_training_data(self) -> Optional["pd.DataFrame"]:
        """Fetch closed trades from agape_spot_scan_activity for training."""
        if not DB_AVAILABLE or not ML_AVAILABLE:
            return None
        try:
            conn = get_connection()
            query = """
                SELECT
                    s.timestamp AS scan_time,
                    s.ticker,
                    s.funding_rate,
                    s.funding_regime,
                    s.ls_ratio,
                    s.ls_bias,
                    s.squeeze_risk,
                    s.crypto_gex,
                    s.oracle_win_prob,
                    EXTRACT(DOW FROM s.timestamp) AS day_of_week,
                    EXTRACT(HOUR FROM s.timestamp AT TIME ZONE 'America/Chicago') AS hour_of_day,
                    -- Join to closed positions to get outcome
                    CASE WHEN p.realized_pnl > 0 THEN 'WIN' ELSE 'LOSS' END AS trade_outcome,
                    p.realized_pnl
                FROM agape_spot_scan_activity s
                INNER JOIN agape_spot_positions p
                    ON s.position_id = p.position_id
                WHERE s.signal_action = 'LONG'
                  AND s.position_id IS NOT NULL
                  AND p.status IN ('closed', 'expired', 'stopped')
                  AND p.realized_pnl IS NOT NULL
                ORDER BY s.timestamp ASC
            """
            df = pd.read_sql(query, conn)
            conn.close()

            if len(df) == 0:
                logger.warning("No completed trades found for ML training")
                return None
            logger.info(f"Fetched {len(df)} completed trades for AGAPE-SPOT ML training")
            return df
        except Exception as e:
            logger.error(f"Failed to fetch training data: {e}")
            return None

    def _prepare_features(self, df: "pd.DataFrame") -> Tuple["np.ndarray", "np.ndarray"]:
        """Prepare features and target from raw data."""
        regime_map = {'NEGATIVE': 0, 'NEUTRAL': 1, 'POSITIVE': 2}
        df = df.copy()
        df['funding_regime_encoded'] = df['funding_regime'].map(regime_map).fillna(1)

        bias_map = {'SHORT': -1, 'NEUTRAL': 0, 'LONG': 1}
        df['ls_bias_encoded'] = df['ls_bias'].map(bias_map).fillna(0)

        squeeze_map = {'LOW': 0, 'MEDIUM': 1, 'HIGH': 2}
        df['squeeze_risk_encoded'] = df['squeeze_risk'].map(squeeze_map).fillna(0)

        # Defaults
        df['funding_rate'] = df['funding_rate'].fillna(0.0)
        df['ls_ratio'] = df['ls_ratio'].fillna(1.0)
        df['crypto_gex'] = df['crypto_gex'].fillna(0.0)
        df['oracle_win_prob'] = df['oracle_win_prob'].fillna(0.5)
        df['day_of_week'] = df['day_of_week'].fillna(3)
        df['hour_of_day'] = df['hour_of_day'].fillna(12)
        df['positive_funding_win_rate'] = df.get('positive_funding_win_rate', pd.Series(0.5, index=df.index)).fillna(0.5)
        df['negative_funding_win_rate'] = df.get('negative_funding_win_rate', pd.Series(0.5, index=df.index)).fillna(0.5)
        df['chop_index'] = df.get('chop_index', pd.Series(0.5, index=df.index)).fillna(0.5)

        X = df[self.FEATURE_COLS].values
        y = (df['trade_outcome'] == 'WIN').astype(int).values
        return X, y

    def train(self, min_samples: int = None) -> Optional[SpotMLTrainingMetrics]:
        """Train XGBoost model on closed trade data."""
        if not ML_AVAILABLE:
            raise ImportError("ML libraries required: pip install scikit-learn pandas numpy")
        if not HAS_XGBOOST:
            raise ImportError("XGBoost required: pip install xgboost")

        min_samples = min_samples or self.min_samples_for_training

        df = self.get_training_data()
        if df is None or len(df) < min_samples:
            count = len(df) if df is not None else 0
            raise ValueError(f"Insufficient data: {count} samples < {min_samples} required")

        logger.info(f"Training AGAPE-SPOT ML on {len(df)} trades")

        X, y = self._prepare_features(df)
        n_wins = int(y.sum())
        n_losses = len(y) - n_wins

        if n_wins < 5 or n_losses < 5:
            raise ValueError(f"Insufficient class balance: {n_wins} wins, {n_losses} losses")

        self.scaler = StandardScaler()
        X_scaled = self.scaler.fit_transform(X)

        n_splits = min(5, len(df) // 20)
        tscv = TimeSeriesSplit(n_splits=max(2, n_splits))

        self.model = xgb.XGBClassifier(
            n_estimators=100,
            max_depth=3,
            learning_rate=0.1,
            min_child_weight=5,
            subsample=0.8,
            colsample_bytree=0.8,
            reg_alpha=0.1,
            reg_lambda=1.0,
            random_state=42,
            use_label_encoder=False,
            eval_metric='logloss',
            verbosity=0,
        )

        accuracies, precisions, recalls, f1s, aucs = [], [], [], [], []
        for train_idx, test_idx in tscv.split(X_scaled):
            X_tr, X_te = X_scaled[train_idx], X_scaled[test_idx]
            y_tr, y_te = y[train_idx], y[test_idx]
            self.model.fit(X_tr, y_tr)
            y_pred = self.model.predict(X_te)
            y_proba = self.model.predict_proba(X_te)[:, 1]
            accuracies.append(accuracy_score(y_te, y_pred))
            precisions.append(precision_score(y_te, y_pred, zero_division=0))
            recalls.append(recall_score(y_te, y_pred, zero_division=0))
            f1s.append(f1_score(y_te, y_pred, zero_division=0))
            try:
                aucs.append(roc_auc_score(y_te, y_proba))
            except ValueError:
                aucs.append(0.5)

        # Final train on all data
        self.model.fit(X_scaled, y)

        # Calibrate probabilities
        self.calibrated_model = CalibratedClassifierCV(
            self.model, method='isotonic', cv=3,
        )
        self.calibrated_model.fit(X_scaled, y)

        y_proba_full = self.calibrated_model.predict_proba(X_scaled)[:, 1]
        brier = brier_score_loss(y, y_proba_full)
        feature_importances = dict(zip(self.FEATURE_COLS, self.model.feature_importances_))

        # Per-regime accuracy
        df_copy = df.copy()
        regime_map = {'NEGATIVE': 0, 'NEUTRAL': 1, 'POSITIVE': 2}
        df_copy['funding_regime_encoded'] = df_copy['funding_regime'].map(regime_map).fillna(1)
        pos_mask = df_copy['funding_regime_encoded'] == 2
        neg_mask = df_copy['funding_regime_encoded'] == 0
        pos_acc = accuracy_score(y[pos_mask], self.model.predict(X_scaled[pos_mask])) if pos_mask.sum() >= 10 else None
        neg_acc = accuracy_score(y[neg_mask], self.model.predict(X_scaled[neg_mask])) if neg_mask.sum() >= 10 else None

        self.training_metrics = SpotMLTrainingMetrics(
            accuracy=float(np.mean(accuracies)),
            precision=float(np.mean(precisions)),
            recall=float(np.mean(recalls)),
            f1_score=float(np.mean(f1s)),
            auc_roc=float(np.mean(aucs)),
            brier_score=float(brier),
            win_rate_predicted=float(y_proba_full.mean()),
            win_rate_actual=float(y.mean()),
            total_samples=len(df),
            wins=n_wins,
            losses=n_losses,
            positive_funding_accuracy=pos_acc,
            negative_funding_accuracy=neg_acc,
            feature_importances=feature_importances,
            training_date=datetime.now().isoformat(),
            model_version="1.0.0",
        )
        self.is_trained = True
        self.model_version = "1.0.0"
        self.save_to_db(training_records=len(df))

        logger.info(
            f"AGAPE-SPOT ML trained: accuracy={self.training_metrics.accuracy:.2%}, "
            f"AUC={self.training_metrics.auc_roc:.3f}, Brier={brier:.4f}"
        )
        return self.training_metrics

    # ------------------------------------------------------------------
    # Prediction
    # ------------------------------------------------------------------

    def predict(self, features: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Get ML prediction for win probability.

        Args:
            features: dict matching FEATURE_COLS keys

        Returns:
            dict with win_probability and source, or None if model unavailable
        """
        if not self.is_trained or self.model is None or self.scaler is None:
            return None

        try:
            regime_map = {'NEGATIVE': 0, 'NEUTRAL': 1, 'POSITIVE': 2}
            bias_map = {'SHORT': -1, 'NEUTRAL': 0, 'LONG': 1}
            squeeze_map = {'LOW': 0, 'MEDIUM': 1, 'HIGH': 2}

            row = np.array([[
                features.get('funding_rate', 0.0),
                regime_map.get(features.get('funding_regime', 'NEUTRAL'), 1),
                features.get('ls_ratio', 1.0),
                bias_map.get(features.get('ls_bias', 'NEUTRAL'), 0),
                squeeze_map.get(features.get('squeeze_risk', 'LOW'), 0),
                features.get('crypto_gex', 0.0),
                features.get('oracle_win_prob', 0.5),
                features.get('day_of_week', 3),
                features.get('hour_of_day', 12),
                features.get('positive_funding_win_rate', 0.5),
                features.get('negative_funding_win_rate', 0.5),
                features.get('chop_index', 0.5),
            ]])

            scaled = self.scaler.transform(row)
            if self.calibrated_model:
                proba = self.calibrated_model.predict_proba(scaled)[0]
            else:
                proba = self.model.predict_proba(scaled)[0]

            return {
                'win_probability': float(proba[1]),
                'source': 'ML',
            }
        except Exception as e:
            logger.warning(f"AGAPE-SPOT ML prediction failed: {e}")
            return None

    # ------------------------------------------------------------------
    # Shadow comparison
    # ------------------------------------------------------------------

    def get_shadow_comparison(self) -> ShadowComparison:
        """Compare ML vs Bayesian on shadow predictions."""
        if not DB_AVAILABLE:
            return ShadowComparison()

        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    COUNT(*) AS total,
                    COUNT(CASE WHEN actual_outcome IS NOT NULL THEN 1 END) AS resolved,
                    -- Brier scores (only resolved)
                    AVG(CASE WHEN actual_outcome IS NOT NULL
                        THEN POWER(ml_probability - actual_outcome, 2) END) AS ml_brier,
                    AVG(CASE WHEN actual_outcome IS NOT NULL
                        THEN POWER(bayesian_probability - actual_outcome, 2) END) AS bayes_brier,
                    -- Accuracy (threshold 0.5)
                    AVG(CASE WHEN actual_outcome IS NOT NULL
                        THEN CASE WHEN (ml_probability >= 0.5) = (actual_outcome = 1) THEN 1.0 ELSE 0.0 END END) AS ml_acc,
                    AVG(CASE WHEN actual_outcome IS NOT NULL
                        THEN CASE WHEN (bayesian_probability >= 0.5) = (actual_outcome = 1) THEN 1.0 ELSE 0.0 END END) AS bayes_acc,
                    -- Catastrophic misses: ML said >80% but lost
                    SUM(CASE WHEN actual_outcome = 0 AND ml_probability >= 0.8 THEN 1 ELSE 0 END) AS ml_catastrophic,
                    COUNT(CASE WHEN actual_outcome IS NOT NULL THEN 1 END) AS resolved_denom
                FROM agape_spot_ml_shadow
            """)
            row = cursor.fetchone()
            conn.close()

            if not row or not row[0]:
                return ShadowComparison()

            total, resolved = row[0], row[1] or 0
            ml_brier = float(row[2]) if row[2] is not None else 1.0
            bayes_brier = float(row[3]) if row[3] is not None else 1.0
            ml_acc = float(row[4]) if row[4] is not None else 0.0
            bayes_acc = float(row[5]) if row[5] is not None else 0.0
            ml_catastrophic = int(row[6]) if row[6] else 0
            resolved_denom = max(row[7] or 1, 1)

            improvement = ((bayes_brier - ml_brier) / bayes_brier * 100) if bayes_brier > 0 else 0
            cat_rate = ml_catastrophic / resolved_denom if resolved_denom > 0 else 0

            blockers = []
            if resolved < MIN_SHADOW_PREDICTIONS:
                blockers.append(f"Need {MIN_SHADOW_PREDICTIONS - resolved} more resolved predictions")
            if improvement < BRIER_IMPROVEMENT_THRESHOLD * 100:
                blockers.append(f"Brier improvement {improvement:.1f}% < {BRIER_IMPROVEMENT_THRESHOLD*100:.0f}% required")
            if cat_rate > MAX_CATASTROPHIC_MISS_RATE:
                blockers.append(f"Catastrophic miss rate {cat_rate:.1%} > {MAX_CATASTROPHIC_MISS_RATE:.0%} max")

            return ShadowComparison(
                total_predictions=total,
                resolved_predictions=resolved,
                ml_brier=ml_brier,
                bayesian_brier=bayes_brier,
                brier_improvement_pct=improvement,
                ml_accuracy=ml_acc,
                bayesian_accuracy=bayes_acc,
                ml_catastrophic_misses=ml_catastrophic,
                catastrophic_miss_rate=cat_rate,
                is_eligible=len(blockers) == 0,
                promotion_blockers=blockers,
            )
        except Exception as e:
            logger.warning(f"Shadow comparison failed: {e}")
            return ShadowComparison()

    # ------------------------------------------------------------------
    # Info
    # ------------------------------------------------------------------

    def get_feature_importance(self) -> List[Dict[str, Any]]:
        """Get feature importance rankings."""
        if not self.is_trained or not self.training_metrics:
            return []
        importances = self.training_metrics.feature_importances
        total = sum(importances.values()) if importances else 1
        return [
            {
                'rank': i + 1,
                'name': name,
                'importance': round(imp, 4),
                'importance_pct': round(imp / total * 100, 1),
            }
            for i, (name, imp) in enumerate(sorted(importances.items(), key=lambda x: -x[1]))
        ]

    def get_status(self) -> Dict[str, Any]:
        """Get model status for API/UI."""
        return {
            'is_trained': self.is_trained,
            'model_version': self.model_version,
            'model_name': self.MODEL_NAME,
            'training_date': self.training_metrics.training_date if self.training_metrics else None,
            'accuracy': self.training_metrics.accuracy if self.training_metrics else None,
            'auc_roc': self.training_metrics.auc_roc if self.training_metrics else None,
            'brier_score': self.training_metrics.brier_score if self.training_metrics else None,
            'samples': self.training_metrics.total_samples if self.training_metrics else 0,
            'win_rate': self.training_metrics.win_rate_actual if self.training_metrics else None,
        }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
_advisor: Optional[AgapeSpotMLAdvisor] = None


def get_agape_spot_ml_advisor() -> AgapeSpotMLAdvisor:
    """Get or create the AGAPE-SPOT ML advisor singleton."""
    global _advisor
    if _advisor is None:
        _advisor = AgapeSpotMLAdvisor()
    return _advisor
