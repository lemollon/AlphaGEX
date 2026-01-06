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
try:
    from quant.ml_regime_classifier import MLRegimeClassifier, MLPrediction, MLRegimeAction
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
            predictor = GEXDirectionalPredictor()
            status["models"].append({
                "name": "GEX Directional ML",
                "available": True,
                "is_trained": getattr(predictor, 'is_trained', True),
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
# HELPER FUNCTIONS
# =============================================================================

def _log_prediction(prediction_type: str, result: Dict, features: Dict):
    """Log prediction to database."""
    if not DB_AVAILABLE:
        return

    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO ml_predictions (
                timestamp, symbol, prediction_type, predicted_value,
                confidence, features_used
            ) VALUES (NOW(), %s, %s, %s, %s, %s)
        """, (
            "SPY",
            prediction_type,
            result.get('action') or result.get('direction') or result.get('final_signal', 'UNKNOWN'),
            result.get('confidence', 0),
            json.dumps({
                'input': features,
                'output': result
            })
        ))

        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        logger.debug(f"Failed to log prediction: {e}")
