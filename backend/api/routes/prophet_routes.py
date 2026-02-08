"""
PROPHET Dashboard API Routes
============================

API endpoints for the Prophet ML Advisory System.
Provides strategy recommendations, performance analysis, and training status.

Prophet advises all trading bots:
- FORTRESS: Iron Condor advice (SPY 0DTE)
- ANCHOR: Iron Condor advice (SPX weekly)
- SOLOMON: Directional spread advice
- CORNERSTONE: Wheel strategy advice
"""

import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from zoneinfo import ZoneInfo

router = APIRouter(prefix="/api/prophet", tags=["Prophet"])
logger = logging.getLogger(__name__)

# Try to import Prophet
ORACLE_AVAILABLE = False
oracle_instance = None

try:
    from quant.prophet_advisor import (
        ProphetAdvisor, get_oracle, auto_train,
        get_pending_outcomes_count, train_from_live_outcomes,
        MarketContext, GEXRegime, VIXRegime, StrategyType,
        StrategyRecommendation, BotName, TradingAdvice
    )
    ORACLE_AVAILABLE = True
    logger.info("Prophet advisor system loaded")
except ImportError as e:
    logger.warning(f"Prophet not available: {e}")

CENTRAL_TZ = ZoneInfo("America/Chicago")


# =============================================================================
# REQUEST/RESPONSE MODELS
# =============================================================================

class StrategyRecommendationRequest(BaseModel):
    """Request for strategy recommendation"""
    spot_price: float = Field(..., description="Current spot price")
    vix: float = Field(..., description="Current VIX level")
    gex_regime: str = Field("NEUTRAL", description="GEX regime (POSITIVE, NEGATIVE, NEUTRAL)")
    gex_call_wall: float = Field(0, description="GEX call wall price")
    gex_put_wall: float = Field(0, description="GEX put wall price")
    gex_flip_point: float = Field(0, description="GEX flip point")
    gex_net: float = Field(0, description="Net GEX value")
    day_of_week: int = Field(None, description="Day of week (0=Monday, 4=Friday)")


class TrainRequest(BaseModel):
    """Request to trigger Prophet training"""
    force: bool = Field(False, description="Force training even if threshold not met")
    threshold: int = Field(20, description="Minimum outcomes for training")


# =============================================================================
# HEALTH AND STATUS
# =============================================================================

@router.get("/health")
async def prophet_health():
    """
    Check Prophet system health.

    Returns availability status, model info, and training metrics.
    """
    if not ORACLE_AVAILABLE:
        return {
            "status": "unavailable",
            "message": "Prophet system not loaded"
        }

    try:
        prophet = get_oracle()
        pending = get_pending_outcomes_count()

        # Calculate model freshness metrics
        hours_since_training = prophet._get_hours_since_training() if hasattr(prophet, '_get_hours_since_training') else 0.0
        is_model_fresh = prophet._is_model_fresh() if hasattr(prophet, '_is_model_fresh') else True
        model_trained_at = prophet._model_trained_at.isoformat() if hasattr(prophet, '_model_trained_at') and prophet._model_trained_at else None

        return {
            "status": "healthy",
            "is_trained": prophet.is_trained,
            "model_version": prophet.model_version,
            "pending_outcomes": pending,
            "training_threshold": 20,
            "has_gex_features": prophet._has_gex_features if hasattr(prophet, '_has_gex_features') else False,
            # Model freshness metrics (Issue #4 - staleness visibility)
            "hours_since_training": round(hours_since_training, 2),
            "is_model_fresh": is_model_fresh,
            "model_trained_at": model_trained_at,
            "freshness_warning": f"Model is {hours_since_training:.1f}h old - retraining recommended" if not is_model_fresh else None,
            "timestamp": datetime.now(CENTRAL_TZ).isoformat()
        }
    except Exception as e:
        logger.error(f"Prophet health check failed: {e}")
        return {
            "status": "error",
            "message": str(e)
        }


@router.get("/status")
async def prophet_status():
    """
    Get detailed Prophet status including training metrics.
    """
    if not ORACLE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Prophet not available")

    try:
        prophet = get_oracle()
        pending = get_pending_outcomes_count()

        # Calculate model freshness metrics
        hours_since_training = prophet._get_hours_since_training() if hasattr(prophet, '_get_hours_since_training') else 0.0
        is_model_fresh = prophet._is_model_fresh() if hasattr(prophet, '_is_model_fresh') else True
        model_trained_at = prophet._model_trained_at.isoformat() if hasattr(prophet, '_model_trained_at') and prophet._model_trained_at else None

        result = {
            "is_trained": prophet.is_trained,
            "model_version": prophet.model_version,
            "pending_outcomes": pending,
            "training_threshold": 20,
            "training_frequency": "daily",
            # Model freshness metrics (Issue #4 - staleness visibility)
            "hours_since_training": round(hours_since_training, 2),
            "is_model_fresh": is_model_fresh,
            "model_trained_at": model_trained_at,
            "freshness_warning": f"Model is {hours_since_training:.1f}h old - retraining recommended" if not is_model_fresh else None,
            "timestamp": datetime.now(CENTRAL_TZ).isoformat()
        }

        # Add training metrics if available
        if prophet.training_metrics:
            result["training_metrics"] = {
                "accuracy": prophet.training_metrics.accuracy,
                "precision": prophet.training_metrics.precision,
                "recall": prophet.training_metrics.recall,
                "f1_score": prophet.training_metrics.f1_score,
                "auc_roc": prophet.training_metrics.auc_roc,
                "total_samples": prophet.training_metrics.total_samples,
                "training_date": prophet.training_metrics.training_date
            }

        return result
    except Exception as e:
        logger.error(f"Prophet status check failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# STRATEGY RECOMMENDATION
# =============================================================================

@router.post("/strategy-recommendation")
async def get_strategy_recommendation(request: StrategyRecommendationRequest):
    """
    Get IC vs Directional strategy recommendation based on market conditions.

    Decision Matrix:
    - HIGH VIX + NEGATIVE GEX = Favor DIRECTIONAL (SOLOMON)
    - NORMAL VIX + POSITIVE GEX = Favor IRON_CONDOR (FORTRESS/ANCHOR)
    - EXTREME VIX = SKIP or reduced exposure
    """
    if not ORACLE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Prophet not available")

    try:
        prophet = get_oracle()

        # Convert gex_regime string to enum
        gex_regime_str = request.gex_regime.upper()
        try:
            gex_regime = GEXRegime[gex_regime_str]
        except KeyError:
            gex_regime = GEXRegime.NEUTRAL

        # Build context
        day_of_week = request.day_of_week
        if day_of_week is None:
            day_of_week = datetime.now(CENTRAL_TZ).weekday()

        context = MarketContext(
            spot_price=request.spot_price,
            vix=request.vix,
            gex_regime=gex_regime,
            gex_call_wall=request.gex_call_wall,
            gex_put_wall=request.gex_put_wall,
            gex_flip_point=request.gex_flip_point,
            gex_net=request.gex_net,
            day_of_week=day_of_week
        )

        # Get recommendation
        rec = prophet.get_strategy_recommendation(context)

        return {
            "recommended_strategy": rec.recommended_strategy.value,
            "vix_regime": rec.vix_regime.value,
            "gex_regime": rec.gex_regime.value,
            "confidence": rec.confidence,
            "ic_suitability": rec.ic_suitability,
            "dir_suitability": rec.dir_suitability,
            "size_multiplier": rec.size_multiplier,
            "reasoning": rec.reasoning,
            "timestamp": datetime.now(CENTRAL_TZ).isoformat()
        }
    except Exception as e:
        logger.error(f"Strategy recommendation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/strategy-recommendation")
async def get_strategy_recommendation_current():
    """
    Get strategy recommendation using current market conditions.

    Fetches live VIX and GEX data to make recommendation.
    """
    if not ORACLE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Prophet not available")

    try:
        prophet = get_oracle()

        # Try to get live market data
        try:
            from core_classes_and_engines import TradingVolatilityAPI
            api = TradingVolatilityAPI()
            gex_data = api.get_gex_levels('SPY')

            spot_price = gex_data.get('spot_price', 590)
            vix = gex_data.get('vix', 20)
            gex_regime_str = gex_data.get('gex_regime', 'NEUTRAL')
            call_wall = gex_data.get('call_wall', 0)
            put_wall = gex_data.get('put_wall', 0)
            flip_point = gex_data.get('flip_point', 0)
            net_gex = gex_data.get('net_gex', 0)
        except Exception as e:
            logger.warning(f"Could not fetch live data: {e}")
            # Use defaults
            spot_price = 590
            vix = 20
            gex_regime_str = 'NEUTRAL'
            call_wall = 600
            put_wall = 580
            flip_point = 590
            net_gex = 0

        # Convert gex_regime
        try:
            gex_regime = GEXRegime[gex_regime_str.upper()]
        except KeyError:
            gex_regime = GEXRegime.NEUTRAL

        context = MarketContext(
            spot_price=spot_price,
            vix=vix,
            gex_regime=gex_regime,
            gex_call_wall=call_wall,
            gex_put_wall=put_wall,
            gex_flip_point=flip_point,
            gex_net=net_gex,
            day_of_week=datetime.now(CENTRAL_TZ).weekday()
        )

        rec = prophet.get_strategy_recommendation(context)

        return {
            "recommended_strategy": rec.recommended_strategy.value,
            "vix_regime": rec.vix_regime.value,
            "gex_regime": rec.gex_regime.value,
            "confidence": rec.confidence,
            "ic_suitability": rec.ic_suitability,
            "dir_suitability": rec.dir_suitability,
            "size_multiplier": rec.size_multiplier,
            "reasoning": rec.reasoning,
            "market_data": {
                "spot_price": spot_price,
                "vix": vix,
                "call_wall": call_wall,
                "put_wall": put_wall
            },
            "timestamp": datetime.now(CENTRAL_TZ).isoformat()
        }
    except Exception as e:
        logger.error(f"Strategy recommendation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# PERFORMANCE ANALYSIS
# =============================================================================

@router.get("/strategy-performance")
async def get_strategy_performance(
    days: int = Query(30, description="Number of days to analyze")
):
    """
    Analyze IC vs Directional performance by VIX and GEX regime.

    Returns win rates and P&L for each strategy type broken down by:
    - VIX regime (LOW, NORMAL, ELEVATED, HIGH, EXTREME)
    - GEX regime (POSITIVE, NEUTRAL, NEGATIVE)
    """
    if not ORACLE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Prophet not available")

    try:
        prophet = get_oracle()
        results = prophet.analyze_strategy_performance(days=days)

        if "error" in results:
            return {
                "status": "no_data",
                "message": results["error"],
                "days": days
            }

        return {
            "status": "success",
            "days_analyzed": results.get("days_analyzed", days),
            "total_trades": results.get("total_trades", 0),
            "ic_performance": {
                "by_vix_regime": results.get("ic_by_vix_regime", {}),
                "by_gex_regime": results.get("ic_by_gex_regime", {}),
                "total": results.get("total_ic", {})
            },
            "directional_performance": {
                "by_vix_regime": results.get("dir_by_vix_regime", {}),
                "by_gex_regime": results.get("dir_by_gex_regime", {}),
                "total": results.get("total_dir", {})
            },
            "timestamp": datetime.now(CENTRAL_TZ).isoformat()
        }
    except Exception as e:
        logger.error(f"Strategy performance analysis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# TRAINING
# =============================================================================

@router.post("/train")
async def trigger_training(request: TrainRequest):
    """
    Trigger Prophet model training.

    Training uses:
    1. Live outcomes from prophet_training_outcomes table (preferred)
    2. Database backtests (fallback)
    3. CHRONICLES backtest data (final fallback)
    """
    if not ORACLE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Prophet not available")

    try:
        result = auto_train(
            threshold_outcomes=request.threshold,
            force=request.force
        )

        return {
            "triggered": result.get("triggered", False),
            "success": result.get("success", False),
            "reason": result.get("reason", ""),
            "method": result.get("method", ""),
            "pending_outcomes": result.get("pending_outcomes", 0),
            "training_metrics": result.get("training_metrics"),
            "timestamp": datetime.now(CENTRAL_TZ).isoformat()
        }
    except Exception as e:
        logger.error(f"Training trigger failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pending-outcomes")
async def get_pending_outcomes():
    """
    Get count of pending outcomes for training.
    """
    if not ORACLE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Prophet not available")

    try:
        count = get_pending_outcomes_count()
        return {
            "pending_outcomes": count,
            "training_threshold": 20,
            "ready_for_training": count >= 20,
            "timestamp": datetime.now(CENTRAL_TZ).isoformat()
        }
    except Exception as e:
        logger.error(f"Failed to get pending outcomes: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# VIX REGIME INFO
# =============================================================================

@router.get("/vix-regimes")
async def get_vix_regimes():
    """
    Get VIX regime definitions and their strategy implications.
    """
    return {
        "regimes": [
            {
                "regime": "LOW",
                "vix_range": "< 15",
                "description": "Low volatility, cheap options",
                "ic_suitability": "Reduced (low premium)",
                "directional_suitability": "Good if trending"
            },
            {
                "regime": "NORMAL",
                "vix_range": "15 - 22",
                "description": "Ideal conditions for Iron Condors",
                "ic_suitability": "Excellent",
                "directional_suitability": "Average"
            },
            {
                "regime": "ELEVATED",
                "vix_range": "22 - 28",
                "description": "Cautious IC, consider directional",
                "ic_suitability": "Reduced",
                "directional_suitability": "Good"
            },
            {
                "regime": "HIGH",
                "vix_range": "28 - 35",
                "description": "Volatile market, favor directional",
                "ic_suitability": "Poor",
                "directional_suitability": "Excellent"
            },
            {
                "regime": "EXTREME",
                "vix_range": "> 35",
                "description": "Crisis conditions, reduce exposure",
                "ic_suitability": "Skip",
                "directional_suitability": "Good with trend"
            }
        ],
        "strategy_matrix": {
            "NORMAL VIX + POSITIVE GEX": "IRON_CONDOR (FORTRESS/ANCHOR)",
            "HIGH VIX + NEGATIVE GEX": "DIRECTIONAL (SOLOMON)",
            "EXTREME VIX + NO TREND": "SKIP",
            "LOW VIX + NEGATIVE GEX": "DIRECTIONAL (cheap options)"
        }
    }
