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
import json
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from zoneinfo import ZoneInfo

router = APIRouter(prefix="/api/prophet", tags=["Prophet"])
# Secondary router for metrics-compatible equity curve endpoint
metrics_router = APIRouter(tags=["Prophet Metrics"])
logger = logging.getLogger(__name__)

# Try to import Prophet
PROPHET_AVAILABLE = False
oracle_instance = None

# Database availability
DB_AVAILABLE = False
try:
    from database_adapter import get_connection
    DB_AVAILABLE = True
except ImportError:
    try:
        import psycopg2
        import os
        def get_connection():
            return psycopg2.connect(os.environ.get("DATABASE_URL", ""))
        DB_AVAILABLE = True
    except Exception:
        pass

try:
    from quant.prophet_advisor import (
        ProphetAdvisor, get_prophet, auto_train,
        get_pending_outcomes_count, train_from_live_outcomes,
        get_training_status,
        MarketContext, GEXRegime, VIXRegime, StrategyType,
        StrategyRecommendation, BotName, TradingAdvice,
        ProphetLiveLog
    )
    PROPHET_AVAILABLE = True
    logger.info("Prophet advisor system loaded")
except ImportError as e:
    logger.warning(f"Prophet not available: {e}")
    get_training_status = None
    ProphetLiveLog = None

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
    if not PROPHET_AVAILABLE:
        return {
            "status": "unavailable",
            "message": "Prophet system not loaded"
        }

    try:
        prophet = get_prophet()
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
    Get detailed Prophet status including training metrics and bot heartbeats.
    Returns data wrapped in 'prophet' and 'bot_heartbeats' keys for frontend.
    """
    if not PROPHET_AVAILABLE:
        return {
            "success": True,
            "prophet": {
                "model_trained": False,
                "model_version": "0.0.0",
                "claude_available": False,
                "claude_model": "",
                "high_confidence_threshold": 0.7,
                "low_confidence_threshold": 0.55
            },
            "bot_heartbeats": {}
        }

    try:
        prophet = get_prophet()
        pending = get_pending_outcomes_count()

        # Calculate model freshness metrics
        hours_since_training = prophet._get_hours_since_training() if hasattr(prophet, '_get_hours_since_training') else 0.0
        is_model_fresh = prophet._is_model_fresh() if hasattr(prophet, '_is_model_fresh') else True

        prophet_data = {
            "model_trained": prophet.is_trained,
            "model_version": prophet.model_version,
            "claude_available": prophet.claude_available if hasattr(prophet, 'claude_available') else False,
            "claude_model": getattr(prophet, 'CLAUDE_MODEL', ''),
            "high_confidence_threshold": getattr(prophet, 'high_confidence_threshold', 0.7),
            "low_confidence_threshold": getattr(prophet, 'low_confidence_threshold', 0.55),
            "pending_outcomes": pending,
            "training_threshold": 1,
            "training_frequency": "daily",
            "hours_since_training": round(hours_since_training, 2),
            "is_model_fresh": is_model_fresh,
            "timestamp": datetime.now(CENTRAL_TZ).isoformat()
        }

        # Add training metrics if available
        if prophet.training_metrics:
            prophet_data["training_metrics"] = {
                "accuracy": prophet.training_metrics.accuracy,
                "precision": prophet.training_metrics.precision,
                "recall": prophet.training_metrics.recall,
                "f1_score": prophet.training_metrics.f1_score,
                "auc_roc": prophet.training_metrics.auc_roc,
                "total_samples": prophet.training_metrics.total_samples,
                "training_date": prophet.training_metrics.training_date
            }

        # Build bot heartbeats from recent predictions
        bot_heartbeats = {}
        if DB_AVAILABLE:
            try:
                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT bot_name,
                           MAX(prediction_time) as last_scan_time,
                           COUNT(*) FILTER (WHERE trade_date = CURRENT_DATE) as scan_count_today,
                           (SELECT advice FROM prophet_predictions pp2
                            WHERE pp2.bot_name = pp.bot_name
                            ORDER BY prediction_time DESC LIMIT 1) as last_advice
                    FROM prophet_predictions pp
                    WHERE prediction_time >= NOW() - INTERVAL '24 hours'
                    GROUP BY bot_name
                """)
                for row in cursor.fetchall():
                    bname, last_time, count_today, last_advice = row
                    status_str = "SCAN_COMPLETE"
                    if last_advice and last_advice in ('TRADE_FULL', 'TRADE_REDUCED'):
                        status_str = "TRADED"
                    elif last_advice == 'SKIP_TODAY':
                        status_str = "SCAN_COMPLETE"

                    bot_heartbeats[bname] = {
                        "last_scan": last_time.strftime("%I:%M %p CT") if last_time else None,
                        "last_scan_iso": last_time.isoformat() if last_time else None,
                        "status": status_str,
                        "scan_count_today": count_today or 0,
                        "details": {"last_advice": last_advice}
                    }
                conn.close()
            except Exception as hb_err:
                logger.debug(f"Failed to get bot heartbeats: {hb_err}")

        return {
            "success": True,
            "prophet": prophet_data,
            "bot_heartbeats": bot_heartbeats
        }
    except Exception as e:
        logger.error(f"Prophet status check failed: {e}")
        return {
            "success": True,
            "prophet": {
                "model_trained": False,
                "model_version": "0.0.0",
                "claude_available": False,
                "claude_model": "",
                "high_confidence_threshold": 0.7,
                "low_confidence_threshold": 0.55
            },
            "bot_heartbeats": {},
            "error": str(e)
        }


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
    if not PROPHET_AVAILABLE:
        raise HTTPException(status_code=503, detail="Prophet not available")

    try:
        prophet = get_prophet()

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
    if not PROPHET_AVAILABLE:
        raise HTTPException(status_code=503, detail="Prophet not available")

    try:
        prophet = get_prophet()

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
    if not PROPHET_AVAILABLE:
        raise HTTPException(status_code=503, detail="Prophet not available")

    try:
        prophet = get_prophet()
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
    if not PROPHET_AVAILABLE:
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
    if not PROPHET_AVAILABLE:
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


# =============================================================================
# LIVE LOGS
# =============================================================================

@router.get("/logs")
async def get_prophet_logs(limit: int = Query(50, description="Max logs to return")):
    """
    Get live Prophet logs from in-memory log buffer.
    Returns recent activity including predictions, training, and Claude exchanges.
    """
    if not PROPHET_AVAILABLE:
        return {"success": True, "logs": []}

    try:
        prophet = get_prophet()
        logs = prophet.live_log.get_logs(limit=limit)
        return {
            "success": True,
            "logs": logs,
            "count": len(logs)
        }
    except Exception as e:
        logger.error(f"Failed to get prophet logs: {e}")
        return {"success": True, "logs": []}


@router.delete("/logs")
async def clear_prophet_logs():
    """Clear all in-memory Prophet logs."""
    if not PROPHET_AVAILABLE:
        return {"success": True}

    try:
        prophet = get_prophet()
        prophet.live_log.clear()
        return {"success": True, "message": "Logs cleared"}
    except Exception as e:
        logger.error(f"Failed to clear logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# BOT INTERACTIONS (from prophet_predictions table)
# =============================================================================

@router.get("/bot-interactions")
async def get_bot_interactions(
    days: int = Query(7, description="Number of days to look back"),
    limit: int = Query(200, description="Max interactions to return"),
    bot_name: Optional[str] = Query(None, description="Filter by bot name")
):
    """
    Get Prophet bot interactions from the prophet_predictions database table.
    Each row represents a time Prophet advised a bot on a trading decision.
    """
    if not DB_AVAILABLE:
        return {"success": True, "interactions": [], "total": 0}

    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Build query
        where_clauses = ["trade_date >= (CURRENT_DATE - INTERVAL '%s days')"]
        params: list = [days]

        if bot_name:
            where_clauses.append("bot_name = %s")
            params.append(bot_name)

        where_sql = " AND ".join(where_clauses)

        cursor.execute(f"""
            SELECT id, trade_date, bot_name, prediction_time, advice,
                   win_probability, confidence, reasoning, spot_price, vix,
                   gex_regime, gex_net, gex_call_wall, gex_put_wall, gex_flip_point,
                   day_of_week, model_version, top_factors, claude_analysis,
                   actual_outcome, actual_pnl, outcome_date,
                   use_gex_walls, suggested_risk_pct, suggested_sd_multiplier,
                   suggested_put_strike, suggested_call_strike
            FROM prophet_predictions
            WHERE {where_sql}
            ORDER BY COALESCE(prediction_time, timestamp) DESC
            LIMIT %s
        """, params + [limit])

        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
        conn.close()

        interactions = []
        for row in rows:
            interaction = dict(zip(columns, row))

            # Convert datetime objects to ISO strings
            for key in ['trade_date', 'prediction_time', 'outcome_date']:
                if interaction.get(key) and hasattr(interaction[key], 'isoformat'):
                    interaction[key] = interaction[key].isoformat()

            # Parse JSONB fields
            for key in ['top_factors', 'claude_analysis']:
                if interaction.get(key) and isinstance(interaction[key], str):
                    try:
                        interaction[key] = json.loads(interaction[key])
                    except (json.JSONDecodeError, TypeError):
                        pass

            # Add source field and use prediction_time as timestamp
            interaction['source'] = 'prophet_predictions'
            interaction['timestamp'] = interaction.get('prediction_time') or interaction.get('trade_date')
            interaction['action'] = interaction.get('advice', 'UNKNOWN')

            interactions.append(interaction)

        return {
            "success": True,
            "interactions": interactions,
            "total": len(interactions)
        }

    except Exception as e:
        logger.error(f"Failed to get bot interactions: {e}")
        return {"success": True, "interactions": [], "total": 0}


# =============================================================================
# TRAINING STATUS (detailed)
# =============================================================================

@router.get("/training-status")
async def get_training_status_endpoint():
    """
    Get detailed Prophet training status including model state,
    pending outcomes, freshness metrics, and persistence info.
    """
    if not PROPHET_AVAILABLE or not get_training_status:
        return {
            "success": False,
            "error": "Prophet not available",
            "model_trained": False,
            "model_version": "0.0.0",
            "pending_outcomes": 0,
            "total_outcomes": 0,
            "threshold_for_retrain": 1,
            "needs_training": True,
        }

    try:
        status = get_training_status()

        # Override threshold to 1 so training always appears ready
        status["threshold_for_retrain"] = 1
        status["needs_training"] = not status.get("model_trained", False) or status.get("pending_outcomes", 0) >= 1

        # Add freshness metrics
        prophet = get_prophet()
        hours_since = prophet._get_hours_since_training() if hasattr(prophet, '_get_hours_since_training') else 0.0
        is_fresh = prophet._is_model_fresh() if hasattr(prophet, '_is_model_fresh') else True

        status["hours_since_training"] = round(hours_since, 2)
        status["is_model_fresh"] = is_fresh
        status["success"] = True

        return status

    except Exception as e:
        logger.error(f"Failed to get training status: {e}")
        return {
            "success": False,
            "error": str(e),
            "model_trained": False,
            "model_version": "0.0.0",
            "pending_outcomes": 0,
            "total_outcomes": 0,
            "threshold_for_retrain": 1,
            "needs_training": True,
        }


# =============================================================================
# TRIGGER TRAINING (always attempt)
# =============================================================================

@router.post("/trigger-training")
async def trigger_training_endpoint(
    force: bool = Query(False, description="Force training even with no new data")
):
    """
    Trigger Prophet model training.
    Always attempts training with available data (no minimum threshold).
    """
    if not PROPHET_AVAILABLE:
        raise HTTPException(status_code=503, detail="Prophet not available")

    try:
        # Always force=True to bypass threshold checks
        result = auto_train(
            threshold_outcomes=1,
            force=True
        )

        return {
            "success": result.get("success", False),
            "triggered": result.get("triggered", False),
            "reason": result.get("reason", ""),
            "method": result.get("method", ""),
            "pending_outcomes": result.get("pending_outcomes", 0),
            "training_metrics": result.get("training_metrics"),
            "timestamp": datetime.now(CENTRAL_TZ).isoformat()
        }
    except Exception as e:
        logger.error(f"Training trigger failed: {e}")
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.now(CENTRAL_TZ).isoformat()
        }


# =============================================================================
# PERFORMANCE (prediction accuracy & P&L)
# =============================================================================

@router.get("/performance")
async def get_prophet_performance(
    days: int = Query(90, description="Number of days to analyze")
):
    """
    Get Prophet prediction performance metrics.
    Analyzes win rate, P&L, and calibration from prophet_predictions with outcomes.
    """
    if not DB_AVAILABLE:
        return {"success": True, "total_predictions": 0, "days": days}

    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Get predictions with outcomes
        cursor.execute("""
            SELECT bot_name, advice, win_probability, confidence,
                   actual_outcome, actual_pnl
            FROM prophet_predictions
            WHERE trade_date >= (CURRENT_DATE - INTERVAL '%s days')
              AND actual_outcome IS NOT NULL
            ORDER BY trade_date DESC
        """, (days,))

        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return {
                "success": True,
                "total_predictions": 0,
                "days": days,
                "overall": None,
                "by_bot": {}
            }

        # Calculate overall stats
        total = len(rows)
        wins = 0
        losses = 0
        total_pnl = 0.0
        predicted_probs = []

        by_bot: Dict[str, Dict] = {}

        for row in rows:
            data = dict(zip(columns, row))
            bot = data['bot_name'] or 'UNKNOWN'
            outcome = str(data.get('actual_outcome', '')).upper()
            pnl = float(data['actual_pnl'] or 0)
            prob = float(data['win_probability'] or 0.5)

            is_win = 'WIN' in outcome or 'MAX_PROFIT' in outcome or 'PROFIT' in outcome
            if is_win:
                wins += 1
            else:
                losses += 1

            total_pnl += pnl
            predicted_probs.append((prob, 1.0 if is_win else 0.0))

            # By bot aggregation
            if bot not in by_bot:
                by_bot[bot] = {"total": 0, "wins": 0, "pnl": 0.0, "predicted_probs": []}
            by_bot[bot]["total"] += 1
            if is_win:
                by_bot[bot]["wins"] += 1
            by_bot[bot]["pnl"] += pnl
            by_bot[bot]["predicted_probs"].append(prob)

        # Calculate calibration error (avg predicted prob vs actual win rate)
        avg_predicted = sum(p for p, _ in predicted_probs) / len(predicted_probs) if predicted_probs else 0.5
        actual_rate = wins / total if total > 0 else 0
        calibration_error = abs(avg_predicted - actual_rate)

        # Format by_bot
        by_bot_formatted = {}
        for bot, stats in by_bot.items():
            bot_total = stats["total"]
            bot_wins = stats["wins"]
            by_bot_formatted[bot] = {
                "total": bot_total,
                "wins": bot_wins,
                "pnl": round(stats["pnl"], 2),
                "win_rate": bot_wins / bot_total if bot_total > 0 else 0,
                "avg_predicted_prob": sum(stats["predicted_probs"]) / len(stats["predicted_probs"]) if stats["predicted_probs"] else 0
            }

        return {
            "success": True,
            "total_predictions": total,
            "days": days,
            "overall": {
                "wins": wins,
                "losses": losses,
                "win_rate": wins / total if total > 0 else 0,
                "avg_predicted_win_prob": avg_predicted,
                "calibration_error": calibration_error,
                "total_pnl": round(total_pnl, 2)
            },
            "by_bot": by_bot_formatted
        }

    except Exception as e:
        logger.error(f"Failed to get performance: {e}")
        return {"success": True, "total_predictions": 0, "days": days, "overall": None, "by_bot": {}}


# =============================================================================
# DATA FLOW TRANSPARENCY
# =============================================================================

@router.get("/data-flows")
async def get_data_flows(
    limit: int = Query(50, description="Max records"),
    bot_name: Optional[str] = Query(None, description="Filter by bot")
):
    """Get detailed data flow records from Prophet's in-memory pipeline log."""
    if not PROPHET_AVAILABLE:
        return {"success": True, "data_flows": [], "count": 0}

    try:
        prophet = get_prophet()
        flows = prophet.live_log.get_data_flows(limit=limit, bot_name=bot_name)
        return {
            "success": True,
            "data_flows": flows,
            "count": len(flows)
        }
    except Exception as e:
        logger.error(f"Failed to get data flows: {e}")
        return {"success": True, "data_flows": [], "count": 0}


@router.get("/claude-exchanges")
async def get_claude_exchanges(
    limit: int = Query(20, description="Max records"),
    bot_name: Optional[str] = Query(None, description="Filter by bot")
):
    """Get complete Claude AI exchange records with full prompt/response pairs."""
    if not PROPHET_AVAILABLE:
        return {"success": True, "claude_exchanges": [], "count": 0}

    try:
        prophet = get_prophet()
        exchanges = prophet.live_log.get_claude_exchanges(limit=limit, bot_name=bot_name)
        return {
            "success": True,
            "claude_exchanges": exchanges,
            "count": len(exchanges)
        }
    except Exception as e:
        logger.error(f"Failed to get Claude exchanges: {e}")
        return {"success": True, "claude_exchanges": [], "count": 0}


@router.get("/full-transparency")
async def get_full_transparency(
    bot_name: Optional[str] = Query(None, description="Filter by bot")
):
    """
    Get complete transparency data: logs, data flows, Claude exchanges.
    Combined endpoint for the Prophet Data Flow tab.
    """
    if not PROPHET_AVAILABLE:
        return {
            "success": True,
            "data_flows": [],
            "claude_exchanges": [],
            "summary": {"total_logs": 0, "total_data_flows": 0, "total_claude_exchanges": 0}
        }

    try:
        prophet = get_prophet()
        live_log = prophet.live_log

        data_flows = live_log.get_data_flows(limit=100, bot_name=bot_name)
        claude_exchanges = live_log.get_claude_exchanges(limit=50, bot_name=bot_name)
        all_logs = live_log.get_logs(limit=500)

        return {
            "success": True,
            "data_flows": data_flows,
            "claude_exchanges": claude_exchanges,
            "summary": {
                "total_logs": len(all_logs),
                "total_data_flows": len(data_flows),
                "total_claude_exchanges": len(claude_exchanges)
            }
        }
    except Exception as e:
        logger.error(f"Failed to get full transparency: {e}")
        return {
            "success": True,
            "data_flows": [],
            "claude_exchanges": [],
            "summary": {"total_logs": 0, "total_data_flows": 0, "total_claude_exchanges": 0}
        }


# =============================================================================
# PREDICTIONS LIST
# =============================================================================

@router.get("/predictions")
async def get_predictions(
    days: int = Query(30, description="Number of days"),
    limit: int = Query(100, description="Max predictions"),
    bot_name: Optional[str] = Query(None, description="Filter by bot"),
    include_claude: bool = Query(False, description="Include Claude analysis details")
):
    """
    Get Prophet predictions from the database.
    Used by the logs page and prediction history views.
    """
    if not DB_AVAILABLE:
        return {"success": True, "predictions": [], "total": 0}

    try:
        conn = get_connection()
        cursor = conn.cursor()

        where_clauses = ["trade_date >= (CURRENT_DATE - INTERVAL '%s days')"]
        params: list = [days]

        if bot_name:
            where_clauses.append("bot_name = %s")
            params.append(bot_name)

        where_sql = " AND ".join(where_clauses)

        select_fields = """
            id, trade_date, bot_name, prediction_time, advice,
            win_probability, confidence, reasoning, spot_price, vix,
            gex_regime, model_version, actual_outcome, actual_pnl
        """
        if include_claude:
            select_fields += ", claude_analysis"

        cursor.execute(f"""
            SELECT {select_fields}
            FROM prophet_predictions
            WHERE {where_sql}
            ORDER BY COALESCE(prediction_time, timestamp) DESC
            LIMIT %s
        """, params + [limit])

        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
        conn.close()

        predictions = []
        for row in rows:
            pred = dict(zip(columns, row))
            for key in ['trade_date', 'prediction_time']:
                if pred.get(key) and hasattr(pred[key], 'isoformat'):
                    pred[key] = pred[key].isoformat()
            if include_claude and pred.get('claude_analysis') and isinstance(pred['claude_analysis'], str):
                try:
                    pred['claude_analysis'] = json.loads(pred['claude_analysis'])
                except (json.JSONDecodeError, TypeError):
                    pass
            predictions.append(pred)

        return {
            "success": True,
            "predictions": predictions,
            "total": len(predictions)
        }

    except Exception as e:
        logger.error(f"Failed to get predictions: {e}")
        return {"success": True, "predictions": [], "total": 0}


# =============================================================================
# EQUITY CURVE (metrics-compatible endpoint for EquityCurveChart component)
# =============================================================================

@metrics_router.get("/api/metrics/PROPHET/equity-curve")
async def prophet_equity_curve(
    days: int = Query(90, ge=1, le=365)
):
    """
    Build Prophet prediction equity curve from realized outcomes.
    Returns data compatible with the EquityCurveChart component format.
    """
    if not DB_AVAILABLE:
        return {
            "success": True,
            "timeframe": "daily",
            "equity_curve": [],
            "events": [],
            "summary": {
                "total_pnl": 0,
                "final_equity": 0,
                "max_drawdown_pct": 0,
                "total_trades": 0,
                "starting_capital": 0
            }
        }

    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Get daily aggregated P&L from prophet predictions with outcomes
        cursor.execute("""
            SELECT
                trade_date,
                SUM(COALESCE(actual_pnl, 0)) as daily_pnl,
                COUNT(*) as trade_count
            FROM prophet_predictions
            WHERE trade_date >= (CURRENT_DATE - INTERVAL '%s days')
              AND actual_outcome IS NOT NULL
              AND actual_pnl IS NOT NULL
            GROUP BY trade_date
            ORDER BY trade_date ASC
        """, (days,))

        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return {
                "success": True,
                "timeframe": "daily",
                "equity_curve": [],
                "events": [],
                "summary": {
                    "total_pnl": 0,
                    "final_equity": 0,
                    "max_drawdown_pct": 0,
                    "total_trades": 0,
                    "starting_capital": 0
                }
            }

        # Build equity curve
        cumulative_pnl = 0.0
        peak_equity = 0.0
        max_drawdown_pct = 0.0
        total_trades = 0
        equity_curve = []

        for row in rows:
            trade_date, daily_pnl, trade_count = row
            cumulative_pnl += float(daily_pnl or 0)
            total_trades += int(trade_count or 0)
            equity = cumulative_pnl

            if equity > peak_equity:
                peak_equity = equity
            drawdown_pct = ((peak_equity - equity) / peak_equity * 100) if peak_equity > 0 else 0

            if drawdown_pct > max_drawdown_pct:
                max_drawdown_pct = drawdown_pct

            equity_curve.append({
                "date": trade_date.isoformat() if hasattr(trade_date, 'isoformat') else str(trade_date),
                "equity": round(cumulative_pnl, 2),
                "daily_pnl": round(float(daily_pnl or 0), 2),
                "cumulative_pnl": round(cumulative_pnl, 2),
                "drawdown_pct": round(drawdown_pct, 2),
                "trade_count": int(trade_count or 0)
            })

        return {
            "success": True,
            "timeframe": "daily",
            "equity_curve": equity_curve,
            "events": [],
            "summary": {
                "total_pnl": round(cumulative_pnl, 2),
                "final_equity": round(cumulative_pnl, 2),
                "max_drawdown_pct": round(max_drawdown_pct, 2),
                "total_trades": total_trades,
                "starting_capital": 0
            }
        }

    except Exception as e:
        logger.error(f"Failed to build prophet equity curve: {e}")
        return {
            "success": True,
            "timeframe": "daily",
            "equity_curve": [],
            "events": [],
            "summary": {
                "total_pnl": 0,
                "final_equity": 0,
                "max_drawdown_pct": 0,
                "total_trades": 0,
                "starting_capital": 0
            }
        }
