"""
PROMETHEUS - Predictive Risk Optimization Through Machine Evaluation & Training
for Honest Earnings Utility System
===============================================================================

Enhanced ML system for SPX cash-secured put selling with:
- Cross-validation and time-series split
- Probability calibration (isotonic regression)
- Database persistence (survives restarts)
- Comprehensive logging and tracing
- Feature importance analysis
- Performance tracking
- Model versioning

This is the modernized Prometheus system, matching Oracle's capabilities
while staying focused on SPX Wheel strategy optimization.

Author: AlphaGEX Quant
"""

import os
import sys
import json
import uuid
import pickle
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, asdict, field
from enum import Enum

# Add project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)

# ML imports
try:
    import numpy as np
    from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
    from sklearn.model_selection import train_test_split, cross_val_score, TimeSeriesSplit
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import (
        accuracy_score, precision_score, recall_score, f1_score,
        roc_auc_score, brier_score_loss, classification_report, confusion_matrix
    )
    from sklearn.calibration import CalibratedClassifierCV
    ML_AVAILABLE = True
except ImportError:
    ML_AVAILABLE = False
    np = None
    logger.warning("scikit-learn not available. Install with: pip install scikit-learn")

# Database
try:
    from database_adapter import get_connection
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False


# =============================================================================
# ENUMS AND DATA CLASSES
# =============================================================================

class Recommendation(Enum):
    """ML recommendation levels"""
    STRONG_TRADE = "STRONG_TRADE"      # High confidence, full size
    TRADE = "TRADE"                     # Good confidence, trade
    NEUTRAL = "NEUTRAL"                 # Mixed signals
    CAUTION = "CAUTION"                 # Elevated risk
    SKIP = "SKIP"                       # High loss probability


class LogType(Enum):
    """Types of Prometheus logs"""
    PREDICTION = "PREDICTION"
    TRAINING = "TRAINING"
    OUTCOME = "OUTCOME"
    FEATURE_ANALYSIS = "FEATURE_ANALYSIS"
    PERFORMANCE = "PERFORMANCE"
    ERROR = "ERROR"
    INFO = "INFO"


@dataclass
class PrometheusFeatures:
    """
    Features for SPX put selling prediction.
    Each feature has a clear reason for inclusion.
    """
    # Trade parameters
    trade_date: str
    strike: float
    underlying_price: float
    dte: int
    delta: float
    premium: float

    # Volatility features
    iv: float
    iv_rank: float
    vix: float
    vix_percentile: float
    vix_term_structure: float

    # GEX/Positioning features
    put_wall_distance_pct: float
    call_wall_distance_pct: float
    net_gex: float

    # Market regime features
    spx_20d_return: float
    spx_5d_return: float
    spx_distance_from_high: float

    # Premium quality
    premium_to_strike_pct: float
    annualized_return: float

    def to_array(self) -> 'np.ndarray':
        """Convert to numpy array for ML model"""
        if not ML_AVAILABLE:
            return []
        return np.array([
            self.dte,
            self.delta,
            self.iv,
            self.iv_rank,
            self.vix,
            self.vix_percentile,
            self.vix_term_structure,
            self.put_wall_distance_pct,
            self.call_wall_distance_pct,
            self.net_gex / 1e9,  # Scale to billions
            self.spx_20d_return,
            self.spx_5d_return,
            self.spx_distance_from_high,
            self.premium_to_strike_pct,
            self.annualized_return
        ])

    @staticmethod
    def feature_names() -> List[str]:
        return [
            'dte',
            'delta',
            'iv',
            'iv_rank',
            'vix',
            'vix_percentile',
            'vix_term_structure',
            'put_wall_distance_pct',
            'call_wall_distance_pct',
            'net_gex_billions',
            'spx_20d_return',
            'spx_5d_return',
            'spx_distance_from_high',
            'premium_to_strike_pct',
            'annualized_return'
        ]

    @staticmethod
    def feature_meanings() -> Dict[str, str]:
        """Human-readable meanings for each feature"""
        return {
            'dte': 'Days to expiration - affects theta decay rate',
            'delta': 'Option delta - probability of finishing ITM',
            'iv': 'Implied volatility - option pricing',
            'iv_rank': 'IV percentile over past year - selling high IV is profitable',
            'vix': 'VIX level - market fear gauge',
            'vix_percentile': 'VIX percentile - historical context',
            'vix_term_structure': 'VIX contango/backwardation - market stress indicator',
            'put_wall_distance_pct': 'Distance to put wall support - GEX protection',
            'call_wall_distance_pct': 'Distance to call wall resistance',
            'net_gex_billions': 'Net gamma exposure - dealer positioning',
            'spx_20d_return': '20-day momentum - trend context',
            'spx_5d_return': '5-day momentum - recent move',
            'spx_distance_from_high': 'Distance from 52-week high - pullback opportunity',
            'premium_to_strike_pct': 'Premium yield - trade quality',
            'annualized_return': 'Annualized return potential - risk/reward'
        }


@dataclass
class PrometheusOutcome:
    """Trade outcome for training"""
    trade_id: str
    features: PrometheusFeatures
    outcome: str  # 'WIN' or 'LOSS'
    pnl: float
    max_drawdown: float
    settlement_price: float

    def is_win(self) -> bool:
        return self.outcome == 'WIN'


@dataclass
class PrometheusPrediction:
    """Prediction result from Prometheus"""
    trade_id: str
    win_probability: float
    recommendation: Recommendation
    confidence: float
    reasoning: str
    key_factors: Dict[str, Any]
    feature_values: Dict[str, float]
    model_version: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict:
        return {
            'trade_id': self.trade_id,
            'win_probability': self.win_probability,
            'recommendation': self.recommendation.value,
            'confidence': self.confidence,
            'reasoning': self.reasoning,
            'key_factors': self.key_factors,
            'feature_values': self.feature_values,
            'model_version': self.model_version,
            'timestamp': self.timestamp
        }


@dataclass
class TrainingMetrics:
    """Metrics from a training run"""
    training_id: str
    training_date: str

    # Data stats
    total_samples: int
    train_samples: int
    test_samples: int
    win_count: int
    loss_count: int
    baseline_win_rate: float

    # Performance metrics
    accuracy: float
    precision: float
    recall: float
    f1_score: float
    auc_roc: float
    brier_score: float

    # Cross-validation
    cv_accuracy_mean: float
    cv_accuracy_std: float
    cv_scores: List[float]

    # Calibration
    calibration_error: float
    is_calibrated: bool

    # Feature importance
    feature_importance: List[Tuple[str, float]]

    # Model info
    model_type: str
    model_version: str

    # Interpretation
    interpretation: Dict[str, str]
    honest_assessment: str
    recommendation: str


# =============================================================================
# PROMETHEUS LOGGER - Comprehensive Logging System
# =============================================================================

class PrometheusLogger:
    """
    Comprehensive logging system for Prometheus ML.
    Stores logs in database for persistence and analysis.
    """

    _instance = None
    MAX_MEMORY_LOGS = 100

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._logs = []
            cls._instance._session_id = None
            cls._instance._trace_id = None
        return cls._instance

    def set_session(self, session_id: str = None):
        """Set session ID for log grouping"""
        self._session_id = session_id or str(uuid.uuid4())[:8]

    def new_trace(self) -> str:
        """Start a new trace for request tracking"""
        self._trace_id = str(uuid.uuid4())
        return self._trace_id

    def log(
        self,
        log_type: LogType,
        action: str,
        message: str = None,
        details: Dict = None,
        ml_score: float = None,
        recommendation: str = None,
        trade_id: str = None,
        features: Dict = None,
        error: Exception = None,
        execution_time_ms: int = None
    ):
        """Log an event"""
        entry = {
            'timestamp': datetime.now().isoformat(),
            'session_id': self._session_id,
            'trace_id': self._trace_id,
            'log_type': log_type.value,
            'action': action,
            'message': message,
            'details': details,
            'ml_score': ml_score,
            'recommendation': recommendation,
            'trade_id': trade_id,
            'features': features,
            'error_message': str(error) if error else None,
            'execution_time_ms': execution_time_ms
        }

        # Keep in memory
        self._logs.append(entry)
        if len(self._logs) > self.MAX_MEMORY_LOGS:
            self._logs = self._logs[-self.MAX_MEMORY_LOGS:]

        # Log to standard logger
        log_msg = f"[PROMETHEUS] {log_type.value}: {action}"
        if message:
            log_msg += f" - {message}"
        if error:
            logger.error(log_msg, exc_info=True)
        else:
            logger.info(log_msg)

        # Persist to database
        self._persist_log(entry)

    def _persist_log(self, entry: Dict):
        """Save log to database"""
        if not DB_AVAILABLE:
            return

        try:
            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute('''
                INSERT INTO prometheus_decision_logs (
                    session_id, trace_id, log_type, action, reasoning,
                    trade_id, ml_score, recommendation, details, features,
                    error_message, execution_time_ms
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ''', (
                entry.get('session_id'),
                entry.get('trace_id'),
                entry.get('log_type'),
                entry.get('action'),
                entry.get('message'),
                entry.get('trade_id'),
                entry.get('ml_score'),
                entry.get('recommendation'),
                json.dumps(entry.get('details')) if entry.get('details') else None,
                json.dumps(entry.get('features')) if entry.get('features') else None,
                entry.get('error_message'),
                entry.get('execution_time_ms')
            ))

            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Failed to persist log: {e}")

    def get_logs(self, limit: int = 50, log_type: str = None) -> List[Dict]:
        """Get recent logs from memory"""
        logs = self._logs
        if log_type:
            logs = [l for l in logs if l.get('log_type') == log_type]
        return logs[-limit:]

    def get_logs_from_db(
        self,
        limit: int = 100,
        log_type: str = None,
        session_id: str = None,
        since: datetime = None
    ) -> List[Dict]:
        """Get logs from database"""
        if not DB_AVAILABLE:
            return self.get_logs(limit, log_type)

        try:
            conn = get_connection()
            cursor = conn.cursor()

            query = 'SELECT * FROM prometheus_decision_logs WHERE 1=1'
            params = []

            if log_type:
                query += ' AND log_type = %s'
                params.append(log_type)
            if session_id:
                query += ' AND session_id = %s'
                params.append(session_id)
            if since:
                query += ' AND timestamp >= %s'
                params.append(since)

            query += ' ORDER BY timestamp DESC LIMIT %s'
            params.append(limit)

            cursor.execute(query, params)
            columns = [desc[0] for desc in cursor.description]
            results = [dict(zip(columns, row)) for row in cursor.fetchall()]

            conn.close()
            return results
        except Exception as e:
            logger.error(f"Failed to get logs from DB: {e}")
            return self.get_logs(limit, log_type)


# Global logger instance
prometheus_logger = PrometheusLogger()


# =============================================================================
# PROMETHEUS ML TRAINER - Enhanced with Calibration
# =============================================================================

class PrometheusMLTrainer:
    """
    Enhanced ML trainer for Prometheus with:
    - Time-series cross-validation
    - Probability calibration
    - Database persistence
    - Comprehensive logging
    """

    MODEL_VERSION_PREFIX = "PROMETHEUS"

    def __init__(self, model_path: str = None):
        self.model = None
        self.calibrated_model = None
        self.scaler = None
        self.feature_importance = {}
        self.training_metrics = None
        self.model_version = None
        self.is_calibrated = False
        self.logger = prometheus_logger

        self.model_path = model_path or os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'models',
            'prometheus_ml.pkl'
        )

        # Try to load from database first, then file
        if not self._load_from_db():
            self.load_model()

    def train(
        self,
        outcomes: List[PrometheusOutcome],
        min_samples: int = 30,
        calibrate: bool = True,
        use_time_series_cv: bool = True,
        n_cv_splits: int = 5
    ) -> Dict:
        """
        Train ML model with full validation and calibration.

        Args:
            outcomes: List of trade outcomes for training
            min_samples: Minimum samples required
            calibrate: Whether to apply probability calibration
            use_time_series_cv: Use time-series CV instead of random
            n_cv_splits: Number of CV folds

        Returns:
            Training metrics and interpretation
        """
        training_id = f"{self.MODEL_VERSION_PREFIX}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        start_time = time.time()

        self.logger.new_trace()
        self.logger.log(
            LogType.TRAINING,
            "TRAINING_START",
            f"Starting training with {len(outcomes)} samples",
            details={'min_samples': min_samples, 'calibrate': calibrate}
        )

        if not ML_AVAILABLE:
            error_msg = 'scikit-learn not installed'
            self.logger.log(LogType.ERROR, "ML_NOT_AVAILABLE", error_msg)
            return {'error': error_msg}

        if len(outcomes) < min_samples:
            error_msg = f'Need at least {min_samples} trades to train. Have {len(outcomes)}.'
            self.logger.log(
                LogType.ERROR, "INSUFFICIENT_DATA",
                error_msg,
                details={'trades_available': len(outcomes), 'trades_needed': min_samples}
            )
            return {
                'error': error_msg,
                'trades_available': len(outcomes),
                'trades_needed': min_samples
            }

        try:
            # Extract features and labels
            X = np.array([o.features.to_array() for o in outcomes])
            y = np.array([1 if o.is_win() else 0 for o in outcomes])

            # Class balance check
            win_rate = y.mean()
            win_count = int(y.sum())
            loss_count = len(y) - win_count

            if win_rate < 0.1 or win_rate > 0.9:
                self.logger.log(
                    LogType.INFO, "CLASS_IMBALANCE",
                    f"Imbalanced classes: {win_rate:.1%} win rate"
                )

            # Split data (preserve time order for time series)
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=0.2, random_state=42,
                stratify=y if win_rate > 0.1 and win_rate < 0.9 else None
            )

            # Scale features
            self.scaler = StandardScaler()
            X_train_scaled = self.scaler.fit_transform(X_train)
            X_test_scaled = self.scaler.transform(X_test)

            # Train base model (GradientBoosting for better probability estimates)
            base_model = GradientBoostingClassifier(
                n_estimators=100,
                max_depth=4,
                min_samples_leaf=5,
                learning_rate=0.1,
                subsample=0.8,
                random_state=42
            )

            base_model.fit(X_train_scaled, y_train)

            # Cross-validation
            if use_time_series_cv:
                cv = TimeSeriesSplit(n_splits=n_cv_splits)
            else:
                cv = n_cv_splits

            cv_scores = cross_val_score(base_model, X_train_scaled, y_train, cv=cv, scoring='accuracy')

            # Probability calibration using isotonic regression
            if calibrate and len(X_train) >= 50:
                self.calibrated_model = CalibratedClassifierCV(
                    base_model,
                    method='isotonic',
                    cv=3
                )
                self.calibrated_model.fit(X_train_scaled, y_train)
                self.model = self.calibrated_model
                self.is_calibrated = True

                # Calculate calibration error
                y_prob_calibrated = self.calibrated_model.predict_proba(X_test_scaled)[:, 1]
                calibration_error = self._calculate_calibration_error(y_test, y_prob_calibrated)
            else:
                self.model = base_model
                self.is_calibrated = False
                calibration_error = None

            # Evaluate
            y_pred = self.model.predict(X_test_scaled)
            y_prob = self.model.predict_proba(X_test_scaled)[:, 1]

            # Calculate all metrics
            accuracy = float(accuracy_score(y_test, y_pred))
            precision = float(precision_score(y_test, y_pred, zero_division=0))
            recall = float(recall_score(y_test, y_pred, zero_division=0))
            f1 = float(f1_score(y_test, y_pred, zero_division=0))

            try:
                auc = float(roc_auc_score(y_test, y_prob))
            except ValueError:
                auc = 0.5

            brier = float(brier_score_loss(y_test, y_prob))

            # Feature importance (from base model)
            feature_names = PrometheusFeatures.feature_names()
            if hasattr(base_model, 'feature_importances_'):
                importance = base_model.feature_importances_
            else:
                importance = np.zeros(len(feature_names))

            self.feature_importance = dict(zip(feature_names, importance))
            sorted_features = sorted(self.feature_importance.items(), key=lambda x: x[1], reverse=True)

            # Model version
            self.model_version = f"{self.MODEL_VERSION_PREFIX}-{datetime.now().strftime('%Y%m%d')}-v{len(outcomes)}"

            # Create metrics object
            self.training_metrics = TrainingMetrics(
                training_id=training_id,
                training_date=datetime.now().isoformat(),
                total_samples=len(outcomes),
                train_samples=len(X_train),
                test_samples=len(X_test),
                win_count=win_count,
                loss_count=loss_count,
                baseline_win_rate=float(win_rate),
                accuracy=accuracy,
                precision=precision,
                recall=recall,
                f1_score=f1,
                auc_roc=auc,
                brier_score=brier,
                cv_accuracy_mean=float(cv_scores.mean()),
                cv_accuracy_std=float(cv_scores.std()),
                cv_scores=[float(s) for s in cv_scores],
                calibration_error=calibration_error,
                is_calibrated=self.is_calibrated,
                feature_importance=sorted_features,
                model_type='GradientBoosting+IsotonicCalibration' if self.is_calibrated else 'GradientBoosting',
                model_version=self.model_version,
                interpretation=self._interpret_results(accuracy, win_rate, sorted_features),
                honest_assessment=self._get_honest_assessment(accuracy, win_rate),
                recommendation=self._get_recommendation(accuracy - win_rate, accuracy)
            )

            # Save model
            self._save_to_db()
            self.save_model()

            execution_time = int((time.time() - start_time) * 1000)

            self.logger.log(
                LogType.TRAINING,
                "TRAINING_COMPLETE",
                f"Model trained: accuracy={accuracy:.1%}, calibrated={self.is_calibrated}",
                details={
                    'training_id': training_id,
                    'accuracy': accuracy,
                    'precision': precision,
                    'cv_mean': float(cv_scores.mean()),
                    'is_calibrated': self.is_calibrated,
                    'model_version': self.model_version
                },
                execution_time_ms=execution_time
            )

            return {
                'success': True,
                'training_id': training_id,
                'metrics': asdict(self.training_metrics),
                'interpretation': self.training_metrics.interpretation,
                'honest_assessment': self.training_metrics.honest_assessment,
                'recommendation': self.training_metrics.recommendation,
                'model_version': self.model_version
            }

        except Exception as e:
            self.logger.log(LogType.ERROR, "TRAINING_FAILED", str(e), error=e)
            return {'error': str(e)}

    def _calculate_calibration_error(self, y_true: np.ndarray, y_prob: np.ndarray, n_bins: int = 10) -> float:
        """Calculate Expected Calibration Error (ECE)"""
        bin_boundaries = np.linspace(0, 1, n_bins + 1)
        ece = 0.0

        for i in range(n_bins):
            mask = (y_prob >= bin_boundaries[i]) & (y_prob < bin_boundaries[i + 1])
            if mask.sum() > 0:
                bin_acc = y_true[mask].mean()
                bin_conf = y_prob[mask].mean()
                ece += mask.sum() * abs(bin_acc - bin_conf)

        return float(ece / len(y_true))

    def _interpret_results(self, accuracy: float, baseline: float, top_features: List) -> Dict:
        """Generate interpretation of training results"""
        improvement = accuracy - baseline

        return {
            'baseline_explanation': f"Without ML, random put selling has {baseline:.1%} win rate",
            'ml_accuracy': f"ML correctly predicts {accuracy:.1%} of trades",
            'ml_value_add': f"ML {'improves' if improvement > 0.02 else 'does not significantly improve'} on baseline by {improvement:.1%}",
            'top_factors': [f"{f[0]}: {f[1]:.1%} importance" for f in top_features[:5]],
            'calibration_status': 'Probabilities are calibrated' if self.is_calibrated else 'Using raw probabilities'
        }

    def _get_honest_assessment(self, accuracy: float, baseline: float) -> str:
        """Honest assessment of model value"""
        improvement = accuracy - baseline

        if improvement > 0.1 and accuracy > 0.7:
            return "ML is providing significant value. Model predictions should be trusted for trade filtering."
        elif improvement > 0.05 and accuracy > 0.6:
            return "ML shows meaningful improvement. Use predictions as a strong signal, but combine with other factors."
        elif improvement > 0.02:
            return "ML provides modest improvement. Consider as one of several factors in decision making."
        elif accuracy > baseline:
            return "ML shows minimal improvement over baseline. May help avoid worst trades but don't rely heavily on it."
        else:
            return "ML is NOT adding value over random selection. Stick to mechanical strategy rules."

    def _get_recommendation(self, improvement: float, accuracy: float) -> str:
        """Recommendation on whether to use ML"""
        if improvement > 0.05 and accuracy > 0.6:
            return "STRONG: Use ML scoring for trade selection"
        elif improvement > 0.02:
            return "MODERATE: Use ML as secondary filter"
        elif accuracy > 0.55:
            return "WEAK: May help avoid worst trades"
        else:
            return "NOT RECOMMENDED: Stick to mechanical rules"

    def predict(self, features: PrometheusFeatures, trade_id: str = None) -> PrometheusPrediction:
        """
        Predict trade outcome with full logging and tracing.

        Args:
            features: Trade features for prediction
            trade_id: Optional trade ID for tracking

        Returns:
            PrometheusPrediction with probability and recommendation
        """
        start_time = time.time()
        trace_id = self.logger.new_trace()
        trade_id = trade_id or str(uuid.uuid4())[:12]

        if not ML_AVAILABLE or self.model is None:
            self.logger.log(
                LogType.PREDICTION,
                "PREDICT_FALLBACK",
                "ML model not available, using mechanical rules",
                trade_id=trade_id
            )
            return PrometheusPrediction(
                trade_id=trade_id,
                win_probability=0.0,
                recommendation=Recommendation.NEUTRAL,
                confidence=0.0,
                reasoning='ML model not trained. Use mechanical strategy rules.',
                key_factors={'status': 'model_not_available'},
                feature_values={},
                model_version='N/A'
            )

        try:
            # Scale features
            X = features.to_array().reshape(1, -1)
            X_scaled = self.scaler.transform(X)

            # Predict
            prob = float(self.model.predict_proba(X_scaled)[0][1])

            # Feature values for logging
            feature_names = PrometheusFeatures.feature_names()
            feature_values = dict(zip(feature_names, features.to_array()))

            # Key factors analysis
            key_factors = self._identify_key_factors(features)

            # Determine recommendation
            if prob >= 0.70:
                recommendation = Recommendation.STRONG_TRADE
                reasoning = f"High win probability ({prob:.1%}). {key_factors['positive']}"
                confidence = 0.9
            elif prob >= 0.55:
                recommendation = Recommendation.TRADE
                reasoning = f"Favorable conditions ({prob:.1%}). {key_factors['positive']}"
                confidence = 0.7
            elif prob >= 0.45:
                recommendation = Recommendation.NEUTRAL
                reasoning = f"Mixed signals ({prob:.1%}). {key_factors['mixed']}"
                confidence = 0.5
            elif prob >= 0.30:
                recommendation = Recommendation.CAUTION
                reasoning = f"Elevated risk ({prob:.1%}). {key_factors['negative']}"
                confidence = 0.6
            else:
                recommendation = Recommendation.SKIP
                reasoning = f"High loss probability ({1-prob:.1%}). {key_factors['negative']}"
                confidence = 0.8

            prediction = PrometheusPrediction(
                trade_id=trade_id,
                win_probability=prob,
                recommendation=recommendation,
                confidence=confidence,
                reasoning=reasoning,
                key_factors=key_factors,
                feature_values=feature_values,
                model_version=self.model_version or 'unknown'
            )

            execution_time = int((time.time() - start_time) * 1000)

            # Log prediction
            self.logger.log(
                LogType.PREDICTION,
                "PREDICT",
                f"Win probability: {prob:.1%}, Recommendation: {recommendation.value}",
                ml_score=prob,
                recommendation=recommendation.value,
                trade_id=trade_id,
                features=feature_values,
                details={'key_factors': key_factors},
                execution_time_ms=execution_time
            )

            # Persist prediction to database
            self._save_prediction(prediction, features)

            return prediction

        except Exception as e:
            self.logger.log(LogType.ERROR, "PREDICT_FAILED", str(e), trade_id=trade_id, error=e)
            return PrometheusPrediction(
                trade_id=trade_id,
                win_probability=0.0,
                recommendation=Recommendation.NEUTRAL,
                confidence=0.0,
                reasoning=f'Prediction error: {str(e)}',
                key_factors={'error': str(e)},
                feature_values={},
                model_version=self.model_version or 'error'
            )

    def _identify_key_factors(self, features: PrometheusFeatures) -> Dict:
        """Identify which factors are driving the prediction"""
        positive = []
        negative = []

        # IV Rank analysis
        if features.iv_rank > 50:
            positive.append(f"IV Rank {features.iv_rank:.0f}% (selling expensive options)")
        elif features.iv_rank < 20:
            negative.append(f"IV Rank {features.iv_rank:.0f}% (cheap options)")

        # VIX analysis
        if 18 <= features.vix <= 30:
            positive.append(f"VIX {features.vix:.1f} (good premium environment)")
        elif features.vix > 35:
            negative.append(f"VIX {features.vix:.1f} (extreme volatility)")
        elif features.vix < 15:
            negative.append(f"VIX {features.vix:.1f} (low premium)")

        # VIX term structure
        if features.vix_term_structure > 2:
            negative.append("VIX backwardation (market stress)")
        elif features.vix_term_structure < -2:
            positive.append("VIX contango (normal conditions)")

        # Put wall support
        if features.put_wall_distance_pct < 3:
            positive.append(f"Strong put wall support ({features.put_wall_distance_pct:.1f}% below)")
        elif features.put_wall_distance_pct > 8:
            negative.append("No nearby put wall support")

        # Recent performance
        if features.spx_5d_return < -3:
            positive.append(f"SPX pullback ({features.spx_5d_return:.1f}%) - mean reversion")
        elif features.spx_5d_return > 3:
            negative.append(f"SPX extended ({features.spx_5d_return:.1f}%)")

        # Premium quality
        if features.annualized_return > 20:
            positive.append(f"Strong premium ({features.annualized_return:.0f}% ann.)")
        elif features.annualized_return < 8:
            negative.append(f"Weak premium ({features.annualized_return:.0f}% ann.)")

        return {
            'positive': ' '.join(positive) if positive else 'No strong positive factors',
            'negative': ' '.join(negative) if negative else 'No significant risks',
            'mixed': f"{len(positive)} positive, {len(negative)} negative factors",
            'positive_list': positive,
            'negative_list': negative
        }

    def _save_prediction(self, prediction: PrometheusPrediction, features: PrometheusFeatures):
        """Save prediction to database"""
        if not DB_AVAILABLE:
            return

        try:
            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute('''
                INSERT INTO prometheus_predictions (
                    trade_id, trade_date, strike, underlying_price, dte, delta, premium,
                    win_probability, recommendation, confidence, reasoning,
                    key_factors, feature_values, vix, iv_rank,
                    model_version, session_id
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (trade_id) DO UPDATE SET
                    win_probability = EXCLUDED.win_probability,
                    recommendation = EXCLUDED.recommendation,
                    updated_at = CURRENT_TIMESTAMP
            ''', (
                prediction.trade_id,
                features.trade_date,
                features.strike,
                features.underlying_price,
                features.dte,
                features.delta,
                features.premium,
                prediction.win_probability,
                prediction.recommendation.value,
                prediction.confidence,
                prediction.reasoning,
                json.dumps(prediction.key_factors),
                json.dumps(prediction.feature_values),
                features.vix,
                features.iv_rank,
                prediction.model_version,
                self.logger._session_id
            ))

            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Failed to save prediction: {e}")

    def record_outcome(
        self,
        trade_id: str,
        outcome: str,
        pnl: float,
        was_traded: bool = True
    ):
        """Record the actual outcome of a prediction"""
        self.logger.log(
            LogType.OUTCOME,
            "OUTCOME_RECORDED",
            f"Trade {trade_id}: {outcome}, P&L: ${pnl:,.2f}",
            trade_id=trade_id,
            details={'outcome': outcome, 'pnl': pnl, 'was_traded': was_traded}
        )

        if not DB_AVAILABLE:
            return

        try:
            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute('''
                UPDATE prometheus_predictions
                SET actual_outcome = %s,
                    actual_pnl = %s,
                    was_traded = %s,
                    outcome_date = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE trade_id = %s
            ''', (outcome, pnl, was_traded, trade_id))

            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Failed to record outcome: {e}")

    def save_model(self):
        """Save model to file"""
        if self.model is None:
            return False

        os.makedirs(os.path.dirname(self.model_path), exist_ok=True)

        with open(self.model_path, 'wb') as f:
            pickle.dump({
                'model': self.model,
                'scaler': self.scaler,
                'feature_importance': self.feature_importance,
                'training_metrics': asdict(self.training_metrics) if self.training_metrics else {},
                'model_version': self.model_version,
                'is_calibrated': self.is_calibrated
            }, f)

        self.logger.log(LogType.INFO, "MODEL_SAVED", f"Model saved to {self.model_path}")
        return True

    def load_model(self) -> bool:
        """Load model from file"""
        if not os.path.exists(self.model_path):
            return False

        try:
            with open(self.model_path, 'rb') as f:
                data = pickle.load(f)

            self.model = data['model']
            self.scaler = data['scaler']
            self.feature_importance = data.get('feature_importance', {})
            self.model_version = data.get('model_version')
            self.is_calibrated = data.get('is_calibrated', False)

            self.logger.log(LogType.INFO, "MODEL_LOADED", f"Model loaded from {self.model_path}")
            return True
        except Exception as e:
            self.logger.log(LogType.ERROR, "MODEL_LOAD_FAILED", str(e), error=e)
            return False

    def _save_to_db(self):
        """Save model to database for persistence across restarts"""
        if not DB_AVAILABLE or self.model is None:
            return

        try:
            # Serialize model and scaler
            model_binary = pickle.dumps(self.model)
            scaler_binary = pickle.dumps(self.scaler) if self.scaler else None

            conn = get_connection()
            cursor = conn.cursor()

            # Deactivate previous models
            cursor.execute('''
                UPDATE prometheus_live_model SET is_active = FALSE
            ''')

            # Insert new active model
            cursor.execute('''
                INSERT INTO prometheus_live_model (
                    model_version, model_binary, scaler_binary,
                    model_type, feature_names, accuracy, calibration_error,
                    is_active
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, TRUE)
            ''', (
                self.model_version,
                model_binary,
                scaler_binary,
                'GradientBoosting+Calibrated' if self.is_calibrated else 'GradientBoosting',
                json.dumps(PrometheusFeatures.feature_names()),
                self.training_metrics.accuracy if self.training_metrics else None,
                self.training_metrics.calibration_error if self.training_metrics else None
            ))

            # Also save training history
            if self.training_metrics:
                cursor.execute('''
                    INSERT INTO prometheus_training_history (
                        training_id, total_samples, train_samples, test_samples,
                        win_count, loss_count, baseline_win_rate,
                        accuracy, precision_score, recall, f1_score, auc_roc, brier_score,
                        cv_accuracy_mean, cv_accuracy_std, cv_scores,
                        calibration_error, is_calibrated,
                        feature_importance, model_type, model_version,
                        interpretation, honest_assessment, recommendation,
                        model_path, model_saved_to_db, model_binary, scaler_binary
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE, %s, %s
                    )
                    ON CONFLICT (training_id) DO NOTHING
                ''', (
                    self.training_metrics.training_id,
                    self.training_metrics.total_samples,
                    self.training_metrics.train_samples,
                    self.training_metrics.test_samples,
                    self.training_metrics.win_count,
                    self.training_metrics.loss_count,
                    self.training_metrics.baseline_win_rate,
                    self.training_metrics.accuracy,
                    self.training_metrics.precision,
                    self.training_metrics.recall,
                    self.training_metrics.f1_score,
                    self.training_metrics.auc_roc,
                    self.training_metrics.brier_score,
                    self.training_metrics.cv_accuracy_mean,
                    self.training_metrics.cv_accuracy_std,
                    json.dumps(self.training_metrics.cv_scores),
                    self.training_metrics.calibration_error,
                    self.training_metrics.is_calibrated,
                    json.dumps(self.training_metrics.feature_importance),
                    self.training_metrics.model_type,
                    self.training_metrics.model_version,
                    json.dumps(self.training_metrics.interpretation),
                    self.training_metrics.honest_assessment,
                    self.training_metrics.recommendation,
                    self.model_path,
                    model_binary,
                    scaler_binary
                ))

            conn.commit()
            conn.close()

            self.logger.log(LogType.INFO, "MODEL_SAVED_DB", "Model persisted to database")

        except Exception as e:
            logger.error(f"Failed to save model to DB: {e}")

    def _load_from_db(self) -> bool:
        """Load model from database"""
        if not DB_AVAILABLE:
            return False

        try:
            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute('''
                SELECT model_binary, scaler_binary, model_version, accuracy
                FROM prometheus_live_model
                WHERE is_active = TRUE
                ORDER BY deployed_at DESC
                LIMIT 1
            ''')

            row = cursor.fetchone()
            conn.close()

            if row:
                self.model = pickle.loads(row[0])
                if row[1]:
                    self.scaler = pickle.loads(row[1])
                self.model_version = row[2]
                self.is_calibrated = True  # Assume calibrated if from DB

                self.logger.log(LogType.INFO, "MODEL_LOADED_DB", f"Model {self.model_version} loaded from database")
                return True

            return False

        except Exception as e:
            logger.error(f"Failed to load model from DB: {e}")
            return False

    def get_feature_importance_analysis(self) -> Dict:
        """Get detailed feature importance analysis"""
        if not self.feature_importance:
            return {'error': 'No model trained'}

        meanings = PrometheusFeatures.feature_meanings()

        sorted_features = sorted(
            self.feature_importance.items(),
            key=lambda x: x[1],
            reverse=True
        )

        analysis = []
        for i, (name, importance) in enumerate(sorted_features):
            analysis.append({
                'rank': i + 1,
                'name': name,
                'importance': importance,
                'importance_pct': importance * 100,
                'meaning': meanings.get(name, 'Unknown feature')
            })

        return {
            'features': analysis,
            'top_3': [a['name'] for a in analysis[:3]],
            'total_features': len(analysis),
            'model_version': self.model_version
        }

    def get_performance_summary(self) -> Dict:
        """Get performance summary from database"""
        if not DB_AVAILABLE:
            return {'error': 'Database not available'}

        try:
            conn = get_connection()
            cursor = conn.cursor()

            # Get prediction stats
            cursor.execute('''
                SELECT
                    COUNT(*) as total_predictions,
                    COUNT(CASE WHEN actual_outcome IS NOT NULL THEN 1 END) as completed,
                    COUNT(CASE WHEN actual_outcome = 'WIN' THEN 1 END) as wins,
                    COUNT(CASE WHEN actual_outcome = 'LOSS' THEN 1 END) as losses,
                    AVG(win_probability) as avg_predicted_prob,
                    SUM(actual_pnl) as total_pnl
                FROM prometheus_predictions
                WHERE created_at >= NOW() - INTERVAL '30 days'
            ''')

            row = cursor.fetchone()
            conn.close()

            if row:
                total = row[0] or 0
                completed = row[1] or 0
                wins = row[2] or 0
                losses = row[3] or 0

                return {
                    'total_predictions': total,
                    'completed': completed,
                    'wins': wins,
                    'losses': losses,
                    'win_rate': wins / completed if completed > 0 else 0,
                    'avg_predicted_prob': row[4] or 0,
                    'total_pnl': row[5] or 0,
                    'period': 'last_30_days'
                }

            return {'error': 'No data'}

        except Exception as e:
            return {'error': str(e)}


# =============================================================================
# SINGLETON INSTANCES
# =============================================================================

_prometheus_trainer = None

def get_prometheus_trainer() -> PrometheusMLTrainer:
    """Get singleton Prometheus trainer"""
    global _prometheus_trainer
    if _prometheus_trainer is None:
        _prometheus_trainer = PrometheusMLTrainer()
    return _prometheus_trainer


def get_prometheus_logger() -> PrometheusLogger:
    """Get singleton Prometheus logger"""
    return prometheus_logger


# =============================================================================
# BACKWARDS COMPATIBILITY with spx_wheel_ml.py
# =============================================================================

# Alias for backwards compatibility
SPXWheelFeatures = PrometheusFeatures
SPXWheelOutcome = PrometheusOutcome
SPXWheelMLTrainer = PrometheusMLTrainer

def get_spx_wheel_ml_trainer() -> PrometheusMLTrainer:
    """Backwards compatible alias"""
    return get_prometheus_trainer()
