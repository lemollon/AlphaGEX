"""
QUANT Dashboard API Routes
===========================

API endpoints for the Quant ML Models System.
Provides status, predictions, and logging for all quantitative ML models.

Quant Models:
- ML Regime Classifier: SELL_PREMIUM, BUY_CALLS, BUY_PUTS, STAY_FLAT
- GEX Directional ML: BULLISH, BEARISH, FLAT predictions
- Ensemble Strategy: Multi-signal combination with learned weights
- Monte Carlo Kelly: Position sizing optimization
- Walk-Forward Optimizer: Parameter validation
"""

import logging
import json
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from zoneinfo import ZoneInfo

router = APIRouter(prefix="/api/quant", tags=["Quant"])
logger = logging.getLogger(__name__)

CENTRAL_TZ = ZoneInfo("America/Chicago")

# =============================================================================
# IMPORT QUANT MODULES
# =============================================================================

# ML Regime Classifier
ML_REGIME_AVAILABLE = False
MLRegimeClassifier = None
train_regime_classifier = None
try:
    from quant.ml_regime_classifier import MLRegimeClassifier, MLPrediction, MLRegimeAction, train_regime_classifier
    ML_REGIME_AVAILABLE = True
    logger.info("ML Regime Classifier loaded")
except ImportError as e:
    logger.warning(f"ML Regime Classifier not available: {e}")

# GEX Directional ML
GEX_DIRECTIONAL_AVAILABLE = False
GEXDirectionalPredictor = None
try:
    from quant.gex_directional_ml import GEXDirectionalPredictor, Direction, DirectionalPrediction
    GEX_DIRECTIONAL_AVAILABLE = True
    logger.info("GEX Directional ML loaded")
except ImportError as e:
    logger.warning(f"GEX Directional ML not available: {e}")

# Ensemble Strategy
ENSEMBLE_AVAILABLE = False
get_ensemble_signal = None
try:
    from quant.ensemble_strategy import get_ensemble_signal, EnsembleSignal
    ENSEMBLE_AVAILABLE = True
    logger.info("Ensemble Strategy loaded")
except ImportError as e:
    logger.warning(f"Ensemble Strategy not available: {e}")

# Monte Carlo Kelly
MONTE_CARLO_AVAILABLE = False
MonteCarloKellySizer = None
try:
    from quant.monte_carlo_kelly import MonteCarloKellySizer
    MONTE_CARLO_AVAILABLE = True
    logger.info("Monte Carlo Kelly loaded")
except ImportError as e:
    logger.warning(f"Monte Carlo Kelly not available: {e}")

# Walk-Forward Optimizer
WALK_FORWARD_AVAILABLE = False
WalkForwardOptimizer = None
try:
    from quant.walk_forward_optimizer import WalkForwardOptimizer
    WALK_FORWARD_AVAILABLE = True
    logger.info("Walk-Forward Optimizer loaded")
except ImportError as e:
    logger.warning(f"Walk-Forward Optimizer not available: {e}")

# IV Solver
IV_SOLVER_AVAILABLE = False
IVSolver = None
try:
    from quant.iv_solver import IVSolver
    IV_SOLVER_AVAILABLE = True
    logger.info("IV Solver loaded")
except ImportError as e:
    logger.warning(f"IV Solver not available: {e}")

# Database
DB_AVAILABLE = False
try:
    from database_adapter import get_connection
    DB_AVAILABLE = True
except ImportError:
    logger.warning("Database not available for Quant logging")

# Model persistence - check if models exist in database
MODEL_PERSISTENCE_AVAILABLE = False
model_exists = None
get_model_info = None
try:
    from quant.model_persistence import model_exists, get_model_info, MODEL_GEX_DIRECTIONAL
    MODEL_PERSISTENCE_AVAILABLE = True
except ImportError:
    MODEL_GEX_DIRECTIONAL = 'gex_directional'
    logger.warning("Model persistence not available")


# =============================================================================
# REQUEST/RESPONSE MODELS
# =============================================================================

class RegimePredictionRequest(BaseModel):
    """Request for ML Regime prediction"""
    spot_price: float = Field(..., description="Current spot price")
    vix: float = Field(20.0, description="Current VIX level")
    net_gex: float = Field(0, description="Net GEX value")
    flip_point: float = Field(0, description="GEX flip point")
    iv_rank: float = Field(50.0, description="IV Rank (0-100)")


class DirectionalPredictionRequest(BaseModel):
    """Request for GEX Directional prediction"""
    net_gex: float = Field(..., description="Net GEX value")
    call_wall: float = Field(0, description="Call wall price")
    put_wall: float = Field(0, description="Put wall price")
    flip_point: float = Field(0, description="GEX flip point")
    spot_price: float = Field(..., description="Current spot price")
    vix: float = Field(20.0, description="Current VIX")


class EnsembleRequest(BaseModel):
    """Request for Ensemble signal"""
    symbol: str = Field("SPY", description="Trading symbol")
    gex_regime: str = Field("NEUTRAL", description="GEX regime")
    action: str = Field("SELL_IC", description="Proposed action")
    confidence: float = Field(70, description="Signal confidence")


# =============================================================================
# HEALTH AND STATUS
# =============================================================================

@router.get("/health")
async def quant_health():
    """
    Check Quant system health and module availability.
    """
    return {
        "status": "healthy",
        "modules": {
            "ml_regime_classifier": ML_REGIME_AVAILABLE,
            "gex_directional_ml": GEX_DIRECTIONAL_AVAILABLE,
            "ensemble_strategy": ENSEMBLE_AVAILABLE,
            "monte_carlo_kelly": MONTE_CARLO_AVAILABLE,
            "walk_forward_optimizer": WALK_FORWARD_AVAILABLE,
            "iv_solver": IV_SOLVER_AVAILABLE,
        },
        "database_logging": DB_AVAILABLE,
        "timestamp": datetime.now(CENTRAL_TZ).isoformat()
    }


@router.get("/status")
async def quant_status():
    """
    Get detailed status of all Quant models.
    """
    status = {
        "models": [],
        "total_predictions_24h": 0,
        "timestamp": datetime.now(CENTRAL_TZ).isoformat()
    }

    # ML Regime Classifier
    if ML_REGIME_AVAILABLE:
        try:
            classifier = MLRegimeClassifier(symbol="SPY")
            status["models"].append({
                "name": "ML Regime Classifier",
                "available": True,
                "is_trained": classifier.is_trained,
                "model_version": classifier.model_version,
                "description": "Classifies market regime: SELL_PREMIUM, BUY_CALLS, BUY_PUTS, STAY_FLAT"
            })
        except Exception as e:
            status["models"].append({
                "name": "ML Regime Classifier",
                "available": True,
                "error": str(e)
            })
    else:
        status["models"].append({
            "name": "ML Regime Classifier",
            "available": False
        })

    # GEX Directional ML
    if GEX_DIRECTIONAL_AVAILABLE:
        try:
            # Check database for trained model first (persists across Render deploys)
            model_info = None
            is_trained_in_db = False
            model_version = None
            if MODEL_PERSISTENCE_AVAILABLE and get_model_info:
                try:
                    model_info = get_model_info(MODEL_GEX_DIRECTIONAL)
                    if model_info:
                        is_trained_in_db = True
                        model_version = f"v{model_info.get('version', '?')}"
                        logger.debug(f"GEX Directional ML found in database: {model_info}")
                except Exception as db_e:
                    logger.debug(f"Could not check database for GEX Directional model: {db_e}")

            # If model exists in DB, report as trained
            if is_trained_in_db:
                status["models"].append({
                    "name": "GEX Directional ML",
                    "available": True,
                    "is_trained": True,
                    "model_version": model_version,
                    "trained_at": model_info.get('created_at') if model_info else None,
                    "description": "Predicts market direction: BULLISH, BEARISH, FLAT"
                })
            else:
                # Fall back to checking local instance (may not have loaded)
                predictor = GEXDirectionalPredictor()
                status["models"].append({
                    "name": "GEX Directional ML",
                    "available": True,
                    "is_trained": getattr(predictor, 'is_trained', False),
                    "description": "Predicts market direction: BULLISH, BEARISH, FLAT"
                })
        except Exception as e:
            status["models"].append({
                "name": "GEX Directional ML",
                "available": True,
                "error": str(e)
            })
    else:
        status["models"].append({
            "name": "GEX Directional ML",
            "available": False
        })

    # Ensemble Strategy
    status["models"].append({
        "name": "Ensemble Strategy",
        "available": ENSEMBLE_AVAILABLE,
        "description": "Combines multiple signals with learned regime weights"
    })

    # Monte Carlo Kelly
    status["models"].append({
        "name": "Monte Carlo Kelly",
        "available": MONTE_CARLO_AVAILABLE,
        "description": "Position sizing using Kelly criterion with Monte Carlo simulation"
    })

    # Walk-Forward Optimizer
    status["models"].append({
        "name": "Walk-Forward Optimizer",
        "available": WALK_FORWARD_AVAILABLE,
        "description": "Parameter validation via walk-forward testing"
    })

    # IV Solver
    status["models"].append({
        "name": "IV Solver",
        "available": IV_SOLVER_AVAILABLE,
        "description": "Newton-Raphson implied volatility calculation"
    })

    # Get prediction counts from database
    if DB_AVAILABLE:
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) FROM ml_predictions
                WHERE timestamp > NOW() - INTERVAL '24 hours'
            """)
            result = cursor.fetchone()
            status["total_predictions_24h"] = result[0] if result else 0
            cursor.close()
            conn.close()
        except Exception as e:
            logger.debug(f"Could not fetch prediction count: {e}")

    return status


# =============================================================================
# PREDICTIONS
# =============================================================================

@router.post("/predict/regime")
async def predict_regime(request: RegimePredictionRequest):
    """
    Get ML Regime Classifier prediction.

    Returns recommended action: SELL_PREMIUM, BUY_CALLS, BUY_PUTS, or STAY_FLAT
    """
    if not ML_REGIME_AVAILABLE:
        raise HTTPException(status_code=503, detail="ML Regime Classifier not available")

    try:
        classifier = MLRegimeClassifier(symbol="SPY")

        # Calculate distance to flip
        distance_to_flip = 0
        if request.spot_price > 0 and request.flip_point > 0:
            distance_to_flip = ((request.spot_price - request.flip_point) / request.spot_price) * 100

        now = datetime.now(CENTRAL_TZ)

        prediction = classifier.predict(
            gex_normalized=request.net_gex / 1e9 if request.net_gex != 0 else 1.0,
            gex_percentile=50.0,
            gex_change_1d=0.0,
            gex_change_5d=0.0,
            vix=request.vix,
            vix_percentile=50.0,
            vix_change_1d=0.0,
            iv_rank=request.iv_rank,
            iv_hv_ratio=1.1,
            distance_to_flip=distance_to_flip,
            momentum_1h=0.0,
            momentum_4h=0.0,
            above_20ma=True,
            above_50ma=True,
            regime_duration=1,
            day_of_week=now.weekday(),
            days_to_opex=0
        )

        result = {
            "action": prediction.predicted_action.value,
            "confidence": prediction.confidence,
            "probabilities": prediction.probabilities,
            "is_trained": prediction.is_trained,
            "model_version": prediction.model_version,
            "timestamp": now.isoformat()
        }

        # Log prediction
        _log_prediction("REGIME_CLASSIFIER", result, request.dict())

        return result

    except Exception as e:
        logger.error(f"Regime prediction failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/predict/direction")
async def predict_direction(request: DirectionalPredictionRequest):
    """
    Get GEX Directional ML prediction.

    Returns predicted direction: BULLISH, BEARISH, or FLAT
    """
    if not GEX_DIRECTIONAL_AVAILABLE:
        raise HTTPException(status_code=503, detail="GEX Directional ML not available")

    try:
        predictor = GEXDirectionalPredictor()

        prediction = predictor.predict(
            net_gex=request.net_gex,
            call_wall=request.call_wall,
            put_wall=request.put_wall,
            flip_point=request.flip_point,
            spot_price=request.spot_price,
            vix=request.vix
        )

        if not prediction:
            return {
                "direction": "FLAT",
                "confidence": 0.5,
                "message": "No prediction available"
            }

        result = {
            "direction": prediction.direction.value,
            "confidence": prediction.confidence,
            "probabilities": prediction.probabilities if hasattr(prediction, 'probabilities') else {},
            "timestamp": datetime.now(CENTRAL_TZ).isoformat()
        }

        # Log prediction
        _log_prediction("GEX_DIRECTIONAL", result, request.dict())

        return result

    except Exception as e:
        logger.error(f"Direction prediction failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/predict/ensemble")
async def predict_ensemble(request: EnsembleRequest):
    """
    Get Ensemble Strategy signal.

    Combines multiple signals with learned regime weights.
    """
    if not ENSEMBLE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Ensemble Strategy not available")

    try:
        gex_data = {
            'recommended_action': request.action,
            'confidence': request.confidence,
            'reasoning': f"GEX Regime: {request.gex_regime}"
        }

        current_regime = request.gex_regime
        if current_regime == 'POSITIVE':
            current_regime = 'POSITIVE_GAMMA'
        elif current_regime == 'NEGATIVE':
            current_regime = 'NEGATIVE_GAMMA'

        ensemble = get_ensemble_signal(
            symbol=request.symbol,
            gex_data=gex_data,
            ml_prediction=None,
            current_regime=current_regime
        )

        if not ensemble:
            return {
                "should_trade": True,
                "confidence": 70,
                "position_size_multiplier": 1.0,
                "message": "Ensemble returned no signal"
            }

        result = {
            "final_signal": ensemble.final_signal.value,
            "should_trade": ensemble.should_trade,
            "confidence": ensemble.confidence,
            "position_size_multiplier": ensemble.position_size_multiplier,
            "reasoning": ensemble.reasoning,
            "timestamp": datetime.now(CENTRAL_TZ).isoformat()
        }

        # Log prediction
        _log_prediction("ENSEMBLE", result, request.dict())

        return result

    except Exception as e:
        logger.error(f"Ensemble prediction failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# LOGGING
# =============================================================================

@router.get("/logs")
async def get_quant_logs(
    model: Optional[str] = Query(None, description="Filter by model name"),
    limit: int = Query(100, le=500),
    offset: int = Query(0)
):
    """
    Get Quant prediction logs.
    """
    if not DB_AVAILABLE:
        return {"logs": [], "total": 0, "message": "Database not available"}

    try:
        conn = get_connection()
        cursor = conn.cursor()

        where_clause = ""
        params = []

        if model:
            where_clause = "WHERE prediction_type = %s"
            params.append(model)

        cursor.execute(f"""
            SELECT id, timestamp, symbol, prediction_type, predicted_value,
                   confidence, features_used
            FROM ml_predictions
            {where_clause}
            ORDER BY timestamp DESC
            LIMIT %s OFFSET %s
        """, params + [limit, offset])

        rows = cursor.fetchall()

        logs = []
        for row in rows:
            logs.append({
                "id": row[0],
                "timestamp": row[1].isoformat() if row[1] else None,
                "symbol": row[2],
                "prediction_type": row[3],
                "predicted_value": row[4],
                "confidence": row[5],
                "features": row[6] if isinstance(row[6], dict) else json.loads(row[6]) if row[6] else {}
            })

        # Get total count
        cursor.execute(f"SELECT COUNT(*) FROM ml_predictions {where_clause}", params)
        total = cursor.fetchone()[0]

        cursor.close()
        conn.close()

        return {
            "logs": logs,
            "total": total,
            "limit": limit,
            "offset": offset
        }

    except Exception as e:
        logger.error(f"Failed to get Quant logs: {e}")
        return {"logs": [], "total": 0, "error": str(e)}


@router.get("/logs/stats")
async def get_quant_stats(days: int = Query(7, le=90)):
    """
    Get Quant prediction statistics.
    """
    if not DB_AVAILABLE:
        return {"stats": {}, "message": "Database not available"}

    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Predictions by type
        cursor.execute("""
            SELECT prediction_type, COUNT(*), AVG(confidence)
            FROM ml_predictions
            WHERE timestamp > NOW() - INTERVAL '%s days'
            GROUP BY prediction_type
            ORDER BY COUNT(*) DESC
        """, (days,))

        by_type = []
        for row in cursor.fetchall():
            by_type.append({
                "model": row[0],
                "count": row[1],
                "avg_confidence": round(row[2], 1) if row[2] else 0
            })

        # Predictions by day
        cursor.execute("""
            SELECT DATE(timestamp), COUNT(*)
            FROM ml_predictions
            WHERE timestamp > NOW() - INTERVAL '%s days'
            GROUP BY DATE(timestamp)
            ORDER BY DATE(timestamp)
        """, (days,))

        by_day = []
        for row in cursor.fetchall():
            by_day.append({
                "date": row[0].isoformat() if row[0] else None,
                "count": row[1]
            })

        # Predicted values distribution
        cursor.execute("""
            SELECT predicted_value, COUNT(*)
            FROM ml_predictions
            WHERE timestamp > NOW() - INTERVAL '%s days'
            GROUP BY predicted_value
            ORDER BY COUNT(*) DESC
            LIMIT 10
        """, (days,))

        by_value = []
        for row in cursor.fetchall():
            by_value.append({
                "value": row[0],
                "count": row[1]
            })

        cursor.close()
        conn.close()

        return {
            "days": days,
            "by_type": by_type,
            "by_day": by_day,
            "by_value": by_value
        }

    except Exception as e:
        logger.error(f"Failed to get Quant stats: {e}")
        return {"stats": {}, "error": str(e)}


# =============================================================================
# OUTCOME TRACKING
# =============================================================================

class OutcomeRequest(BaseModel):
    """Request to record prediction outcome"""
    prediction_id: int = Field(..., description="ID of the prediction")
    correct: bool = Field(..., description="Was the prediction correct?")
    pnl: Optional[float] = Field(None, description="P&L if applicable")
    notes: Optional[str] = Field(None, description="Additional notes")


@router.post("/outcomes/record")
async def record_outcome(request: OutcomeRequest):
    """
    Record the outcome of a prediction (correct/incorrect).
    """
    if not DB_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE ml_predictions
            SET outcome_correct = %s,
                outcome_pnl = %s,
                outcome_notes = %s,
                outcome_recorded_at = NOW()
            WHERE id = %s
            RETURNING id, prediction_type, predicted_value
        """, (request.correct, request.pnl, request.notes, request.prediction_id))

        result = cursor.fetchone()
        if not result:
            raise HTTPException(status_code=404, detail="Prediction not found")

        # Update daily performance
        _update_model_performance(cursor, result[1], request.correct, request.pnl)

        conn.commit()
        cursor.close()
        conn.close()

        return {
            "success": True,
            "prediction_id": result[0],
            "model": result[1],
            "predicted_value": result[2],
            "outcome_correct": request.correct
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to record outcome: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/outcomes/pending")
async def get_pending_outcomes(limit: int = Query(50, le=200)):
    """
    Get predictions that need outcome recording.
    """
    if not DB_AVAILABLE:
        return {"predictions": [], "total": 0}

    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, timestamp, prediction_type, predicted_value, confidence,
                   spot_price, vix, used_by_bot
            FROM ml_predictions
            WHERE outcome_correct IS NULL
              AND timestamp > NOW() - INTERVAL '7 days'
            ORDER BY timestamp DESC
            LIMIT %s
        """, (limit,))

        predictions = []
        for row in cursor.fetchall():
            predictions.append({
                "id": row[0],
                "timestamp": row[1].isoformat() if row[1] else None,
                "model": row[2],
                "predicted_value": row[3],
                "confidence": row[4],
                "spot_price": row[5],
                "vix": row[6],
                "used_by_bot": row[7]
            })

        cursor.execute("""
            SELECT COUNT(*) FROM ml_predictions
            WHERE outcome_correct IS NULL
              AND timestamp > NOW() - INTERVAL '7 days'
        """)
        total = cursor.fetchone()[0]

        cursor.close()
        conn.close()

        return {"predictions": predictions, "total": total}

    except Exception as e:
        logger.error(f"Failed to get pending outcomes: {e}")
        return {"predictions": [], "total": 0, "error": str(e)}


# =============================================================================
# BOT INTEGRATION
# =============================================================================

class BotPredictionRequest(BaseModel):
    """Request to log a prediction used by a bot"""
    bot_name: str = Field(..., description="Bot name (FORTRESS, SOLOMON, etc)")
    prediction_type: str = Field(..., description="Model type")
    predicted_value: str = Field(..., description="Prediction value")
    confidence: float = Field(..., description="Confidence level")
    trade_id: Optional[str] = Field(None, description="Associated trade ID")
    session_id: Optional[str] = Field(None, description="Trading session ID")
    spot_price: Optional[float] = Field(None)
    vix: Optional[float] = Field(None)
    gex_regime: Optional[str] = Field(None)


@router.post("/bot/log-usage")
async def log_bot_prediction_usage(request: BotPredictionRequest):
    """
    Log when a bot uses a QUANT prediction.
    """
    if not DB_AVAILABLE:
        return {"success": False, "message": "Database not available"}

    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO ml_predictions (
                timestamp, symbol, prediction_type, predicted_value, confidence,
                used_by_bot, trade_id, session_id, spot_price, vix, gex_regime
            ) VALUES (NOW(), 'SPY', %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            request.prediction_type,
            request.predicted_value,
            request.confidence,
            request.bot_name,
            request.trade_id,
            request.session_id,
            request.spot_price,
            request.vix,
            request.gex_regime
        ))

        pred_id = cursor.fetchone()[0]

        # Check for regime change and create alert if needed
        _check_and_create_alerts(cursor, request.prediction_type, request.predicted_value, request.confidence)

        conn.commit()
        cursor.close()
        conn.close()

        return {"success": True, "prediction_id": pred_id}

    except Exception as e:
        logger.error(f"Failed to log bot usage: {e}")
        return {"success": False, "error": str(e)}


@router.get("/bot/usage")
async def get_bot_usage(
    bot: Optional[str] = Query(None, description="Filter by bot"),
    days: int = Query(7, le=30)
):
    """
    Get prediction usage by bots.
    """
    if not DB_AVAILABLE:
        return {"usage": []}

    try:
        conn = get_connection()
        cursor = conn.cursor()

        where_clause = "WHERE timestamp > NOW() - INTERVAL '%s days' AND used_by_bot IS NOT NULL"
        params = [days]

        if bot:
            where_clause += " AND used_by_bot = %s"
            params.append(bot)

        cursor.execute(f"""
            SELECT used_by_bot, prediction_type, predicted_value,
                   COUNT(*) as usage_count,
                   AVG(confidence) as avg_confidence,
                   SUM(CASE WHEN outcome_correct = TRUE THEN 1 ELSE 0 END) as correct,
                   SUM(CASE WHEN outcome_correct = FALSE THEN 1 ELSE 0 END) as incorrect
            FROM ml_predictions
            {where_clause}
            GROUP BY used_by_bot, prediction_type, predicted_value
            ORDER BY used_by_bot, usage_count DESC
        """, params)

        usage = []
        for row in cursor.fetchall():
            total_with_outcome = (row[5] or 0) + (row[6] or 0)
            usage.append({
                "bot": row[0],
                "model": row[1],
                "predicted_value": row[2],
                "usage_count": row[3],
                "avg_confidence": round(row[4], 1) if row[4] else 0,
                "correct": row[5] or 0,
                "incorrect": row[6] or 0,
                "accuracy": round((row[5] or 0) / total_with_outcome * 100, 1) if total_with_outcome > 0 else None
            })

        cursor.close()
        conn.close()

        return {"usage": usage, "days": days}

    except Exception as e:
        logger.error(f"Failed to get bot usage: {e}")
        return {"usage": [], "error": str(e)}


# =============================================================================
# ALERTS
# =============================================================================

@router.get("/alerts")
async def get_alerts(
    unacknowledged_only: bool = Query(False),
    severity: Optional[str] = Query(None),
    limit: int = Query(50, le=200)
):
    """
    Get QUANT alerts.
    """
    if not DB_AVAILABLE:
        return {"alerts": [], "total": 0}

    try:
        conn = get_connection()
        cursor = conn.cursor()

        where_clauses = []
        params = []

        if unacknowledged_only:
            where_clauses.append("acknowledged = FALSE")

        if severity:
            where_clauses.append("severity = %s")
            params.append(severity)

        where_sql = ""
        if where_clauses:
            where_sql = "WHERE " + " AND ".join(where_clauses)

        cursor.execute(f"""
            SELECT id, timestamp, alert_type, severity, title, message,
                   previous_value, current_value, confidence, model_name,
                   acknowledged
            FROM quant_alerts
            {where_sql}
            ORDER BY timestamp DESC
            LIMIT %s
        """, params + [limit])

        alerts = []
        for row in cursor.fetchall():
            alerts.append({
                "id": row[0],
                "timestamp": row[1].isoformat() if row[1] else None,
                "alert_type": row[2],
                "severity": row[3],
                "title": row[4],
                "message": row[5],
                "previous_value": row[6],
                "current_value": row[7],
                "confidence": row[8],
                "model_name": row[9],
                "acknowledged": row[10]
            })

        cursor.execute(f"SELECT COUNT(*) FROM quant_alerts {where_sql}", params)
        total = cursor.fetchone()[0]

        cursor.close()
        conn.close()

        return {"alerts": alerts, "total": total}

    except Exception as e:
        logger.error(f"Failed to get alerts: {e}")
        return {"alerts": [], "total": 0, "error": str(e)}


@router.post("/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(alert_id: int):
    """
    Acknowledge an alert.
    """
    if not DB_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE quant_alerts
            SET acknowledged = TRUE, acknowledged_at = NOW()
            WHERE id = %s
            RETURNING id
        """, (alert_id,))

        result = cursor.fetchone()
        if not result:
            raise HTTPException(status_code=404, detail="Alert not found")

        conn.commit()
        cursor.close()
        conn.close()

        return {"success": True, "alert_id": alert_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to acknowledge alert: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# PERFORMANCE TRACKING
# =============================================================================

@router.get("/performance")
async def get_model_performance(
    model: Optional[str] = Query(None),
    days: int = Query(30, le=90)
):
    """
    Get model performance metrics.
    """
    if not DB_AVAILABLE:
        return {"performance": []}

    try:
        conn = get_connection()
        cursor = conn.cursor()

        where_clause = "WHERE date > CURRENT_DATE - INTERVAL '%s days'"
        params = [days]

        if model:
            where_clause += " AND model_name = %s"
            params.append(model)

        cursor.execute(f"""
            SELECT date, model_name, total_predictions, correct_predictions,
                   accuracy, avg_confidence, total_pnl
            FROM quant_model_performance
            {where_clause}
            ORDER BY date DESC, model_name
        """, params)

        performance = []
        for row in cursor.fetchall():
            performance.append({
                "date": row[0].isoformat() if row[0] else None,
                "model": row[1],
                "total_predictions": row[2],
                "correct_predictions": row[3],
                "accuracy": float(row[4]) if row[4] else None,
                "avg_confidence": float(row[5]) if row[5] else None,
                "total_pnl": float(row[6]) if row[6] else None
            })

        cursor.close()
        conn.close()

        return {"performance": performance, "days": days}

    except Exception as e:
        logger.error(f"Failed to get performance: {e}")
        return {"performance": [], "error": str(e)}


@router.get("/performance/summary")
async def get_performance_summary(days: int = Query(30, le=90)):
    """
    Get overall performance summary by model.
    """
    if not DB_AVAILABLE:
        return {"summary": []}

    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT prediction_type,
                   COUNT(*) as total,
                   SUM(CASE WHEN outcome_correct = TRUE THEN 1 ELSE 0 END) as correct,
                   SUM(CASE WHEN outcome_correct = FALSE THEN 1 ELSE 0 END) as incorrect,
                   AVG(confidence) as avg_confidence,
                   SUM(outcome_pnl) as total_pnl
            FROM ml_predictions
            WHERE timestamp > NOW() - INTERVAL '%s days'
            GROUP BY prediction_type
            ORDER BY total DESC
        """, (days,))

        summary = []
        for row in cursor.fetchall():
            total_with_outcome = (row[2] or 0) + (row[3] or 0)
            summary.append({
                "model": row[0],
                "total_predictions": row[1],
                "correct": row[2] or 0,
                "incorrect": row[3] or 0,
                "pending": row[1] - total_with_outcome,
                "accuracy": round((row[2] or 0) / total_with_outcome * 100, 1) if total_with_outcome > 0 else None,
                "avg_confidence": round(row[4], 1) if row[4] else None,
                "total_pnl": float(row[5]) if row[5] else None
            })

        cursor.close()
        conn.close()

        return {"summary": summary, "days": days}

    except Exception as e:
        logger.error(f"Failed to get performance summary: {e}")
        return {"summary": [], "error": str(e)}


# =============================================================================
# MODEL TRAINING
# =============================================================================

@router.get("/training/history")
async def get_training_history(model: Optional[str] = Query(None), limit: int = Query(20)):
    """
    Get model training history.
    """
    if not DB_AVAILABLE:
        return {"history": []}

    try:
        conn = get_connection()
        cursor = conn.cursor()

        where_clause = ""
        params = []

        if model:
            where_clause = "WHERE model_name = %s"
            params.append(model)

        cursor.execute(f"""
            SELECT id, timestamp, model_name, training_samples, validation_samples,
                   accuracy_before, accuracy_after, model_version, status,
                   duration_seconds, triggered_by
            FROM quant_training_history
            {where_clause}
            ORDER BY timestamp DESC
            LIMIT %s
        """, params + [limit])

        history = []
        for row in cursor.fetchall():
            history.append({
                "id": row[0],
                "timestamp": row[1].isoformat() if row[1] else None,
                "model": row[2],
                "training_samples": row[3],
                "validation_samples": row[4],
                "accuracy_before": float(row[5]) if row[5] else None,
                "accuracy_after": float(row[6]) if row[6] else None,
                "model_version": row[7],
                "status": row[8],
                "duration_seconds": row[9],
                "triggered_by": row[10]
            })

        cursor.close()
        conn.close()

        return {"history": history}

    except Exception as e:
        logger.error(f"Failed to get training history: {e}")
        return {"history": [], "error": str(e)}


@router.get("/training/schedule")
async def get_training_schedule():
    """
    Get the automated training schedule information.
    Training runs automatically every Sunday at 5:00 PM CT.
    """
    return {
        "schedule": "WEEKLY",
        "day": "Sunday",
        "time": "5:00 PM CT",
        "models": ["REGIME_CLASSIFIER", "GEX_DIRECTIONAL"],
        "note": "ENSEMBLE auto-calibrates from trade outcomes - no explicit training needed",
        "message": "ML model training is fully automated. Models are retrained weekly on Sunday when markets are closed."
    }


@router.post("/training/run-now")
async def run_training_now():
    """
    Trigger immediate training of all ML models (one-time run for testing).
    This is the same logic that runs automatically every Sunday.
    """
    import traceback

    results = {
        "timestamp": datetime.now(CENTRAL_TZ).isoformat(),
        "models_trained": [],
        "models_failed": [],
        "details": {}
    }

    # Train REGIME_CLASSIFIER
    if ML_REGIME_AVAILABLE and train_regime_classifier:
        try:
            logger.info("Running immediate training for REGIME_CLASSIFIER...")
            metrics = train_regime_classifier(symbol="SPY", lookback_days=365)

            if metrics:
                results["models_trained"].append("REGIME_CLASSIFIER")
                results["details"]["REGIME_CLASSIFIER"] = {
                    "accuracy": metrics.accuracy,
                    "f1": metrics.f1,
                    "precision": metrics.precision,
                    "recall": metrics.recall,
                    "samples": metrics.samples_trained
                }

                # Record to database
                if DB_AVAILABLE:
                    try:
                        conn = get_connection()
                        cursor = conn.cursor()
                        cursor.execute("""
                            INSERT INTO quant_training_history (
                                timestamp, model_name, status, accuracy_after,
                                training_samples, triggered_by
                            ) VALUES (NOW(), %s, 'COMPLETED', %s, %s, 'MANUAL_TEST')
                        """, ('REGIME_CLASSIFIER', metrics.accuracy * 100, metrics.samples_trained))
                        conn.commit()
                        cursor.close()
                        conn.close()
                    except Exception as db_err:
                        logger.error(f"Failed to record REGIME_CLASSIFIER training: {db_err}")
            else:
                results["models_failed"].append("REGIME_CLASSIFIER")
                results["details"]["REGIME_CLASSIFIER"] = {"error": "No metrics returned"}

        except Exception as e:
            logger.error(f"REGIME_CLASSIFIER training failed: {e}")
            logger.error(traceback.format_exc())
            results["models_failed"].append("REGIME_CLASSIFIER")
            results["details"]["REGIME_CLASSIFIER"] = {"error": str(e)}
    else:
        results["details"]["REGIME_CLASSIFIER"] = {"error": "Not available"}

    # Train GEX_DIRECTIONAL
    if GEX_DIRECTIONAL_AVAILABLE and GEXDirectionalPredictor:
        try:
            logger.info("Running immediate training for GEX_DIRECTIONAL...")
            predictor = GEXDirectionalPredictor(ticker="SPY")
            result = predictor.train(start_date="2022-01-01", n_splits=5)

            if result:
                predictor.save_model("models/gex_directional_model.joblib")
                results["models_trained"].append("GEX_DIRECTIONAL")
                results["details"]["GEX_DIRECTIONAL"] = {
                    "accuracy": result.accuracy,
                    "training_samples": result.training_samples,
                    "test_samples": result.test_samples
                }

                # Record to database
                if DB_AVAILABLE:
                    try:
                        conn = get_connection()
                        cursor = conn.cursor()
                        cursor.execute("""
                            INSERT INTO quant_training_history (
                                timestamp, model_name, status, accuracy_after,
                                training_samples, triggered_by
                            ) VALUES (NOW(), %s, 'COMPLETED', %s, %s, 'MANUAL_TEST')
                        """, ('GEX_DIRECTIONAL', result.accuracy * 100, result.training_samples))
                        conn.commit()
                        cursor.close()
                        conn.close()
                    except Exception as db_err:
                        logger.error(f"Failed to record GEX_DIRECTIONAL training: {db_err}")
            else:
                results["models_failed"].append("GEX_DIRECTIONAL")
                results["details"]["GEX_DIRECTIONAL"] = {"error": "No result returned"}

        except Exception as e:
            logger.error(f"GEX_DIRECTIONAL training failed: {e}")
            logger.error(traceback.format_exc())
            results["models_failed"].append("GEX_DIRECTIONAL")
            results["details"]["GEX_DIRECTIONAL"] = {"error": str(e)}
    else:
        results["details"]["GEX_DIRECTIONAL"] = {"error": "Not available"}

    results["success"] = len(results["models_failed"]) == 0
    results["message"] = f"Trained {len(results['models_trained'])} models, {len(results['models_failed'])} failed"

    return results


# =============================================================================
# MODEL COMPARISON
# =============================================================================

@router.get("/compare")
async def compare_models(days: int = Query(7, le=30)):
    """
    Compare predictions from different models.
    """
    if not DB_AVAILABLE:
        return {"comparison": {}}

    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Get latest prediction from each model
        cursor.execute("""
            SELECT DISTINCT ON (prediction_type)
                prediction_type, predicted_value, confidence, timestamp
            FROM ml_predictions
            WHERE timestamp > NOW() - INTERVAL '24 hours'
            ORDER BY prediction_type, timestamp DESC
        """)

        current_predictions = {}
        for row in cursor.fetchall():
            current_predictions[row[0]] = {
                "value": row[1],
                "confidence": float(row[2]) if row[2] else None,
                "timestamp": row[3].isoformat() if row[3] else None
            }

        # Check for agreement
        values = [p["value"] for p in current_predictions.values()]
        all_agree = len(set(values)) <= 1 if values else False

        # Get accuracy comparison
        cursor.execute("""
            SELECT prediction_type,
                   COUNT(*) as total,
                   SUM(CASE WHEN outcome_correct = TRUE THEN 1 ELSE 0 END) as correct
            FROM ml_predictions
            WHERE timestamp > NOW() - INTERVAL '%s days'
              AND outcome_correct IS NOT NULL
            GROUP BY prediction_type
        """, (days,))

        accuracy_comparison = {}
        for row in cursor.fetchall():
            accuracy_comparison[row[0]] = {
                "total": row[1],
                "correct": row[2] or 0,
                "accuracy": round((row[2] or 0) / row[1] * 100, 1) if row[1] > 0 else None
            }

        # Get disagreement history
        cursor.execute("""
            SELECT COUNT(*) FROM quant_alerts
            WHERE alert_type = 'MODEL_DISAGREE'
              AND timestamp > NOW() - INTERVAL '%s days'
        """, (days,))
        disagreement_count = cursor.fetchone()[0]

        cursor.close()
        conn.close()

        return {
            "current_predictions": current_predictions,
            "models_agree": all_agree,
            "consensus_value": values[0] if all_agree and values else None,
            "accuracy_comparison": accuracy_comparison,
            "disagreement_count": disagreement_count,
            "days": days
        }

    except Exception as e:
        logger.error(f"Failed to compare models: {e}")
        return {"comparison": {}, "error": str(e)}


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _log_prediction(prediction_type: str, result: Dict, features: Dict, spot_price: float = None, vix: float = None):
    """Log prediction to database."""
    if not DB_AVAILABLE:
        return

    try:
        conn = get_connection()
        cursor = conn.cursor()

        predicted_value = result.get('action') or result.get('direction') or result.get('final_signal', 'UNKNOWN')

        cursor.execute("""
            INSERT INTO ml_predictions (
                timestamp, symbol, prediction_type, predicted_value,
                confidence, features_used, spot_price, vix
            ) VALUES (NOW(), %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            "SPY",
            prediction_type,
            predicted_value,
            result.get('confidence', 0),
            json.dumps({
                'input': features,
                'output': result
            }),
            spot_price,
            vix
        ))

        pred_id = cursor.fetchone()[0]

        # Check for regime change and create alert
        _check_and_create_alerts(cursor, prediction_type, predicted_value, result.get('confidence', 0))

        conn.commit()
        cursor.close()
        conn.close()

        return pred_id
    except Exception as e:
        logger.debug(f"Failed to log prediction: {e}")


def _check_and_create_alerts(cursor, prediction_type: str, predicted_value: str, confidence: float):
    """Check for regime changes and create alerts."""
    try:
        # Get last prediction for this model
        cursor.execute("""
            SELECT predicted_value, confidence FROM quant_last_predictions
            WHERE model_name = %s
        """, (prediction_type,))

        row = cursor.fetchone()
        previous_value = row[0] if row else None
        previous_confidence = row[1] if row else None

        # Update last prediction
        cursor.execute("""
            INSERT INTO quant_last_predictions (model_name, symbol, predicted_value, confidence, timestamp, updated_at)
            VALUES (%s, 'SPY', %s, %s, NOW(), NOW())
            ON CONFLICT (model_name) DO UPDATE SET
                predicted_value = EXCLUDED.predicted_value,
                confidence = EXCLUDED.confidence,
                timestamp = NOW(),
                updated_at = NOW()
        """, (prediction_type, predicted_value, confidence))

        # Check for regime change
        if previous_value and previous_value != predicted_value:
            severity = 'WARNING' if confidence > 70 else 'INFO'
            cursor.execute("""
                INSERT INTO quant_alerts (
                    timestamp, alert_type, severity, title, message,
                    previous_value, current_value, confidence, model_name
                ) VALUES (
                    NOW(), 'REGIME_CHANGE', %s, %s, %s, %s, %s, %s, %s
                )
            """, (
                severity,
                f"{prediction_type}: {previous_value} -> {predicted_value}",
                f"Model {prediction_type} changed prediction from {previous_value} to {predicted_value} with {confidence:.0f}% confidence",
                previous_value,
                predicted_value,
                confidence,
                prediction_type
            ))

        # Check for high confidence signal
        if confidence > 85:
            cursor.execute("""
                INSERT INTO quant_alerts (
                    timestamp, alert_type, severity, title, message,
                    current_value, confidence, model_name
                ) VALUES (
                    NOW(), 'HIGH_CONFIDENCE', 'INFO', %s, %s, %s, %s, %s
                )
            """, (
                f"High confidence {predicted_value} signal",
                f"{prediction_type} predicts {predicted_value} with {confidence:.0f}% confidence",
                predicted_value,
                confidence,
                prediction_type
            ))

    except Exception as e:
        logger.debug(f"Failed to check/create alerts: {e}")


def _update_model_performance(cursor, model_name: str, correct: bool, pnl: float = None):
    """Update daily model performance metrics."""
    try:
        cursor.execute("""
            INSERT INTO quant_model_performance (
                date, model_name, symbol, total_predictions,
                correct_predictions, incorrect_predictions, total_pnl
            ) VALUES (
                CURRENT_DATE, %s, 'SPY', 1,
                CASE WHEN %s THEN 1 ELSE 0 END,
                CASE WHEN %s THEN 0 ELSE 1 END,
                COALESCE(%s, 0)
            )
            ON CONFLICT (date, model_name, symbol) DO UPDATE SET
                total_predictions = quant_model_performance.total_predictions + 1,
                correct_predictions = quant_model_performance.correct_predictions + CASE WHEN %s THEN 1 ELSE 0 END,
                incorrect_predictions = quant_model_performance.incorrect_predictions + CASE WHEN %s THEN 0 ELSE 1 END,
                total_pnl = COALESCE(quant_model_performance.total_pnl, 0) + COALESCE(%s, 0),
                accuracy = (quant_model_performance.correct_predictions + CASE WHEN %s THEN 1 ELSE 0 END)::DECIMAL /
                           NULLIF(quant_model_performance.total_predictions + 1, 0) * 100,
                updated_at = NOW()
        """, (model_name, correct, correct, pnl, correct, correct, pnl, correct))
    except Exception as e:
        logger.debug(f"Failed to update model performance: {e}")
