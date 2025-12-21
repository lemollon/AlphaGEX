"""
PROMETHEUS API Routes
======================

REST API endpoints for the Prometheus ML system.
Provides comprehensive ML training, prediction, and monitoring capabilities.

Endpoints:
- GET  /api/prometheus/status - Get Prometheus ML status
- POST /api/prometheus/train - Train the ML model
- POST /api/prometheus/predict - Get prediction for a trade
- GET  /api/prometheus/feature-importance - Get feature importance analysis
- GET  /api/prometheus/logs - Get decision logs
- GET  /api/prometheus/training-history - Get training history
- GET  /api/prometheus/performance - Get performance metrics
- POST /api/prometheus/record-outcome - Record trade outcome
- GET  /api/prometheus/health - Health check

Author: AlphaGEX Quant
"""

import os
import sys
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

# Add paths
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/prometheus", tags=["prometheus"])

# Import Prometheus ML system
try:
    from trading.prometheus_ml import (
        get_prometheus_trainer,
        get_prometheus_logger,
        PrometheusFeatures,
        PrometheusOutcome,
        Recommendation,
        LogType,
        ML_AVAILABLE,
        DB_AVAILABLE
    )
    PROMETHEUS_AVAILABLE = True
except ImportError as e:
    PROMETHEUS_AVAILABLE = False
    logger.error(f"Failed to import Prometheus ML: {e}")


# =============================================================================
# PYDANTIC MODELS
# =============================================================================

class TrainRequest(BaseModel):
    min_samples: int = 30
    calibrate: bool = True
    use_time_series_cv: bool = True


class PredictRequest(BaseModel):
    trade_date: str
    strike: float
    underlying_price: float
    dte: int
    delta: float
    premium: float
    iv: float
    iv_rank: float
    vix: float
    vix_percentile: float
    vix_term_structure: float
    put_wall_distance_pct: float
    call_wall_distance_pct: float
    net_gex: float
    spx_20d_return: float
    spx_5d_return: float
    spx_distance_from_high: float
    premium_to_strike_pct: float
    annualized_return: float
    trade_id: Optional[str] = None


class RecordOutcomeRequest(BaseModel):
    trade_id: str
    outcome: str  # WIN or LOSS
    pnl: float
    was_traded: bool = True


# =============================================================================
# STATUS ENDPOINT
# =============================================================================

@router.get("/status")
async def get_prometheus_status():
    """
    Get comprehensive Prometheus ML system status.

    Returns model training status, performance metrics, and honest assessment.
    """
    if not PROMETHEUS_AVAILABLE:
        return {
            "success": False,
            "error": "Prometheus ML system not available",
            "ml_library_available": False
        }

    try:
        trainer = get_prometheus_trainer()

        # Get training data count
        training_data_count = 0
        if DB_AVAILABLE:
            try:
                from database_adapter import get_connection
                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT COUNT(*) FROM spx_wheel_ml_outcomes
                    WHERE outcome IS NOT NULL
                ''')
                row = cursor.fetchone()
                training_data_count = row[0] if row else 0
                conn.close()
            except Exception as e:
                logger.error(f"Failed to get training data count: {e}")

        # Build status response
        model_trained = trainer.model is not None
        training_metrics = None

        if trainer.training_metrics:
            training_metrics = {
                'accuracy': trainer.training_metrics.accuracy,
                'precision': trainer.training_metrics.precision,
                'recall': trainer.training_metrics.recall,
                'f1_score': trainer.training_metrics.f1_score,
                'cv_accuracy_mean': trainer.training_metrics.cv_accuracy_mean,
                'cv_accuracy_std': trainer.training_metrics.cv_accuracy_std,
                'calibration_error': trainer.training_metrics.calibration_error,
                'brier_score': trainer.training_metrics.brier_score,
                'auc_roc': trainer.training_metrics.auc_roc
            }

        # Get performance summary
        performance = trainer.get_performance_summary() if model_trained else None

        # Build honest assessment
        if not model_trained:
            honest_assessment = "Prometheus ML model is not trained yet. Collect trade outcomes and train the model to enable ML-powered predictions."
        elif training_data_count < 50:
            honest_assessment = f"Model is trained on {training_data_count} samples. Consider collecting more data (50+) for more reliable predictions."
        elif training_metrics and training_metrics['accuracy'] > 0.65:
            honest_assessment = "Prometheus is providing meaningful predictions. Model accuracy exceeds baseline win rate."
        else:
            honest_assessment = "Model is trained but may not be adding significant value over baseline. Continue collecting data and retraining."

        return {
            "success": True,
            "ml_library_available": ML_AVAILABLE,
            "db_available": DB_AVAILABLE,
            "model_trained": model_trained,
            "model_version": trainer.model_version,
            "is_calibrated": trainer.is_calibrated,
            "training_data_available": training_data_count,
            "can_train": training_data_count >= 30,
            "honest_assessment": honest_assessment,
            "training_metrics": training_metrics,
            "performance": performance,
            "what_ml_can_do": [
                "Identify favorable market conditions for put selling",
                "Estimate win probability based on historical patterns",
                "Highlight key factors driving each prediction",
                "Avoid high-risk setups during extreme volatility",
                "Provide calibrated probability estimates"
            ],
            "what_ml_cannot_do": [
                "Predict black swan events or flash crashes",
                "Guarantee profits on any individual trade",
                "Create alpha where none exists in the strategy",
                "Replace sound risk management practices",
                "Perfectly predict market movements"
            ]
        }

    except Exception as e:
        logger.error(f"Error getting Prometheus status: {e}")
        return {
            "success": False,
            "error": str(e)
        }


# =============================================================================
# TRAINING ENDPOINT
# =============================================================================

@router.post("/train")
async def train_prometheus_model(request: TrainRequest = TrainRequest()):
    """
    Train the Prometheus ML model.

    Requires at least 30 trade outcomes in the database.
    Uses cross-validation and optional probability calibration.
    """
    if not PROMETHEUS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Prometheus ML system not available")

    if not ML_AVAILABLE:
        raise HTTPException(status_code=503, detail="ML libraries not installed")

    try:
        trainer = get_prometheus_trainer()
        prom_logger = get_prometheus_logger()

        # Load training data from database
        outcomes = []

        if DB_AVAILABLE:
            from database_adapter import get_connection
            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute('''
                SELECT trade_id, trade_date, strike, underlying_price, dte, delta, premium,
                       iv, iv_rank, vix, vix_percentile, vix_term_structure,
                       put_wall_distance_pct, call_wall_distance_pct, net_gex,
                       spx_20d_return, spx_5d_return, spx_distance_from_high,
                       premium_to_strike_pct, annualized_return, outcome, pnl,
                       max_drawdown, settlement_price
                FROM spx_wheel_ml_outcomes
                WHERE outcome IS NOT NULL
                ORDER BY trade_date
            ''')

            for row in cursor.fetchall():
                features = PrometheusFeatures(
                    trade_date=str(row[1]),
                    strike=float(row[2]),
                    underlying_price=float(row[3]),
                    dte=int(row[4]),
                    delta=float(row[5]),
                    premium=float(row[6]),
                    iv=float(row[7]),
                    iv_rank=float(row[8]),
                    vix=float(row[9]),
                    vix_percentile=float(row[10]),
                    vix_term_structure=float(row[11]),
                    put_wall_distance_pct=float(row[12]),
                    call_wall_distance_pct=float(row[13]),
                    net_gex=float(row[14]),
                    spx_20d_return=float(row[15]),
                    spx_5d_return=float(row[16]),
                    spx_distance_from_high=float(row[17]),
                    premium_to_strike_pct=float(row[18]),
                    annualized_return=float(row[19])
                )

                outcomes.append(PrometheusOutcome(
                    trade_id=row[0],
                    features=features,
                    outcome=row[20],
                    pnl=float(row[21]) if row[21] else 0,
                    max_drawdown=float(row[22]) if row[22] else 0,
                    settlement_price=float(row[23]) if row[23] else 0
                ))

            conn.close()

        # Train the model
        result = trainer.train(
            outcomes=outcomes,
            min_samples=request.min_samples,
            calibrate=request.calibrate,
            use_time_series_cv=request.use_time_series_cv
        )

        return {
            "success": result.get('success', False),
            "data": result
        }

    except Exception as e:
        logger.error(f"Training failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# PREDICTION ENDPOINT
# =============================================================================

@router.post("/predict")
async def predict_trade(request: PredictRequest):
    """
    Get ML prediction for a proposed trade.

    Returns win probability, recommendation, and key factors.
    """
    if not PROMETHEUS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Prometheus ML system not available")

    try:
        trainer = get_prometheus_trainer()

        features = PrometheusFeatures(
            trade_date=request.trade_date,
            strike=request.strike,
            underlying_price=request.underlying_price,
            dte=request.dte,
            delta=request.delta,
            premium=request.premium,
            iv=request.iv,
            iv_rank=request.iv_rank,
            vix=request.vix,
            vix_percentile=request.vix_percentile,
            vix_term_structure=request.vix_term_structure,
            put_wall_distance_pct=request.put_wall_distance_pct,
            call_wall_distance_pct=request.call_wall_distance_pct,
            net_gex=request.net_gex,
            spx_20d_return=request.spx_20d_return,
            spx_5d_return=request.spx_5d_return,
            spx_distance_from_high=request.spx_distance_from_high,
            premium_to_strike_pct=request.premium_to_strike_pct,
            annualized_return=request.annualized_return
        )

        prediction = trainer.predict(features, trade_id=request.trade_id)

        return {
            "success": True,
            "data": prediction.to_dict()
        }

    except Exception as e:
        logger.error(f"Prediction failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# FEATURE IMPORTANCE ENDPOINT
# =============================================================================

@router.get("/feature-importance")
async def get_feature_importance():
    """
    Get feature importance analysis from the trained model.
    """
    if not PROMETHEUS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Prometheus ML system not available")

    try:
        trainer = get_prometheus_trainer()
        analysis = trainer.get_feature_importance_analysis()

        return {
            "success": True,
            "data": analysis
        }

    except Exception as e:
        logger.error(f"Failed to get feature importance: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# LOGS ENDPOINT
# =============================================================================

@router.get("/logs")
async def get_prometheus_logs(
    limit: int = Query(100, le=500),
    log_type: Optional[str] = None,
    session_id: Optional[str] = None
):
    """
    Get Prometheus decision logs.

    Provides full transparency on all ML decisions and predictions.
    """
    if not PROMETHEUS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Prometheus ML system not available")

    try:
        prom_logger = get_prometheus_logger()

        # Try to get from database first
        logs = prom_logger.get_logs_from_db(
            limit=limit,
            log_type=log_type,
            session_id=session_id
        )

        # Convert datetime objects to strings for JSON serialization
        for log in logs:
            if 'timestamp' in log and hasattr(log['timestamp'], 'isoformat'):
                log['timestamp'] = log['timestamp'].isoformat()

        return {
            "success": True,
            "data": {
                "logs": logs,
                "total": len(logs)
            }
        }

    except Exception as e:
        logger.error(f"Failed to get logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# TRAINING HISTORY ENDPOINT
# =============================================================================

@router.get("/training-history")
async def get_training_history(limit: int = Query(20, le=100)):
    """
    Get history of model training runs.
    """
    if not PROMETHEUS_AVAILABLE or not DB_AVAILABLE:
        return {
            "success": True,
            "data": {"history": []}
        }

    try:
        from database_adapter import get_connection
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT training_id, training_date, total_samples, train_samples, test_samples,
                   accuracy, precision_score, recall, cv_accuracy_mean, cv_accuracy_std,
                   calibration_error, is_calibrated, model_version, model_type
            FROM prometheus_training_history
            ORDER BY training_date DESC
            LIMIT %s
        ''', (limit,))

        columns = [desc[0] for desc in cursor.description]
        history = []

        for row in cursor.fetchall():
            entry = dict(zip(columns, row))
            # Convert datetime to string
            if 'training_date' in entry and hasattr(entry['training_date'], 'isoformat'):
                entry['training_date'] = entry['training_date'].isoformat()
            history.append(entry)

        conn.close()

        return {
            "success": True,
            "data": {"history": history}
        }

    except Exception as e:
        logger.error(f"Failed to get training history: {e}")
        return {
            "success": True,
            "data": {"history": []}
        }


# =============================================================================
# PERFORMANCE ENDPOINT
# =============================================================================

@router.get("/performance")
async def get_performance_metrics(period_days: int = Query(30, le=365)):
    """
    Get Prometheus performance metrics over a time period.
    """
    if not PROMETHEUS_AVAILABLE or not DB_AVAILABLE:
        return {
            "success": True,
            "data": {}
        }

    try:
        from database_adapter import get_connection
        conn = get_connection()
        cursor = conn.cursor()

        # Get prediction stats
        cursor.execute('''
            SELECT
                COUNT(*) as total_predictions,
                COUNT(CASE WHEN actual_outcome IS NOT NULL THEN 1 END) as completed,
                COUNT(CASE WHEN actual_outcome = 'WIN' THEN 1 END) as wins,
                COUNT(CASE WHEN actual_outcome = 'LOSS' THEN 1 END) as losses,
                COUNT(CASE WHEN was_traded = TRUE THEN 1 END) as trades_followed,
                AVG(win_probability) as avg_predicted_prob,
                SUM(CASE WHEN was_traded = TRUE THEN actual_pnl ELSE 0 END) as total_pnl,
                AVG(CASE WHEN actual_outcome IS NOT NULL THEN
                    CASE WHEN (win_probability >= 0.5 AND actual_outcome = 'WIN')
                         OR (win_probability < 0.5 AND actual_outcome = 'LOSS')
                    THEN 1 ELSE 0 END
                ELSE NULL END) as prediction_accuracy
            FROM prometheus_predictions
            WHERE created_at >= NOW() - INTERVAL '%s days'
        ''', (period_days,))

        row = cursor.fetchone()

        result = {}
        if row:
            total = row[0] or 0
            completed = row[1] or 0
            wins = row[2] or 0
            losses = row[3] or 0

            result = {
                'period_days': period_days,
                'total_predictions': total,
                'completed': completed,
                'wins': wins,
                'losses': losses,
                'win_rate': wins / completed if completed > 0 else 0,
                'trades_followed': row[4] or 0,
                'avg_predicted_prob': float(row[5]) if row[5] else 0,
                'total_pnl': float(row[6]) if row[6] else 0,
                'prediction_accuracy': float(row[7]) if row[7] else 0
            }

            # Calculate calibration error
            if completed > 0 and result['avg_predicted_prob'] > 0:
                result['calibration_error'] = abs(result['win_rate'] - result['avg_predicted_prob'])

        conn.close()

        return {
            "success": True,
            "data": result
        }

    except Exception as e:
        logger.error(f"Failed to get performance: {e}")
        return {
            "success": True,
            "data": {}
        }


# =============================================================================
# RECORD OUTCOME ENDPOINT
# =============================================================================

@router.post("/record-outcome")
async def record_trade_outcome(request: RecordOutcomeRequest):
    """
    Record the actual outcome of a predicted trade.

    This is critical for the ML feedback loop.
    """
    if not PROMETHEUS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Prometheus ML system not available")

    try:
        trainer = get_prometheus_trainer()
        trainer.record_outcome(
            trade_id=request.trade_id,
            outcome=request.outcome,
            pnl=request.pnl,
            was_traded=request.was_traded
        )

        return {
            "success": True,
            "message": f"Outcome recorded for trade {request.trade_id}"
        }

    except Exception as e:
        logger.error(f"Failed to record outcome: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# HEALTH CHECK ENDPOINT
# =============================================================================

@router.get("/health")
async def health_check():
    """
    Health check for Prometheus ML system.
    """
    return {
        "status": "healthy" if PROMETHEUS_AVAILABLE else "degraded",
        "prometheus_available": PROMETHEUS_AVAILABLE,
        "ml_available": ML_AVAILABLE if PROMETHEUS_AVAILABLE else False,
        "db_available": DB_AVAILABLE if PROMETHEUS_AVAILABLE else False,
        "timestamp": datetime.now().isoformat()
    }
