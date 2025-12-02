"""
Machine Learning API Routes

Exposes the ML PatternLearner for:
1. Training on historical data
2. Getting predictions for new trades
3. Viewing feature importance
4. Analyzing similar patterns
5. TRANSPARENCY - all ML decisions are logged

This integrates ML into the trading system in a VISIBLE way.
"""

import os
import sys
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

# Add project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from database_adapter import get_connection
import psycopg2.extras
import json

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/ml", tags=["Machine Learning"])


# ============================================================================
# ML Model Instance - Singleton
# ============================================================================

_ml_learner = None

def get_ml_learner():
    """Get or create ML PatternLearner instance"""
    global _ml_learner
    if _ml_learner is None:
        try:
            from ai.autonomous_ml_pattern_learner import PatternLearner
            _ml_learner = PatternLearner()

            # Try to load saved model
            model_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
                'models',
                'pattern_learner.pkl'
            )
            if os.path.exists(model_path):
                _ml_learner.load_model(model_path)
                logger.info(f"Loaded ML model from {model_path}")
        except ImportError as e:
            logger.warning(f"ML PatternLearner not available: {e}")
            _ml_learner = None
    return _ml_learner


# ============================================================================
# Request/Response Models
# ============================================================================

class TrainModelRequest(BaseModel):
    """Request to train the ML model"""
    lookback_days: int = 180


class PredictRequest(BaseModel):
    """Request for ML prediction on a trade setup"""
    symbol: str = "SPX"
    strike: float
    underlying_price: float
    dte: int
    delta: float = 0.20
    iv: float = 0.15
    vix: float = 15.0
    net_gex: float = 0.0
    rsi_1h: float = 50.0
    rsi_1d: float = 50.0
    confidence_score: float = 50.0


class MLLogEntry(BaseModel):
    """A single ML decision log entry"""
    timestamp: str
    symbol: str
    action: str
    ml_score: float
    recommendation: str
    features: Dict[str, Any]
    outcome: Optional[str] = None


# ============================================================================
# ML Logging - TRANSPARENCY
# ============================================================================

def ensure_ml_log_table():
    """Create ML decision log table if not exists"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ml_decision_log (
                id SERIAL PRIMARY KEY,
                timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                symbol VARCHAR(20),
                action VARCHAR(50),
                ml_score DECIMAL(5,4),
                ml_confidence VARCHAR(20),
                recommendation VARCHAR(20),
                features JSONB,
                similar_patterns JSONB,
                trade_id INTEGER,
                outcome VARCHAR(20),
                actual_pnl DECIMAL(12,2)
            )
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_ml_log_timestamp ON ml_decision_log(timestamp DESC)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_ml_log_symbol ON ml_decision_log(symbol)
        ''')
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Error creating ML log table: {e}")
        return False


def log_ml_decision(
    symbol: str,
    action: str,
    ml_result: Dict,
    features: Dict,
    similar_patterns: List = None,
    trade_id: int = None
):
    """Log an ML decision for transparency and auditing"""
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO ml_decision_log (
                symbol, action, ml_score, ml_confidence, recommendation,
                features, similar_patterns, trade_id
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (
            symbol,
            action,
            ml_result.get('success_probability', 0.5),
            ml_result.get('ml_confidence', 'UNKNOWN'),
            ml_result.get('recommendation', 'UNKNOWN'),
            json.dumps(features),
            json.dumps(similar_patterns) if similar_patterns else None,
            trade_id
        ))

        log_id = cursor.fetchone()[0]
        conn.commit()
        conn.close()

        logger.info(f"ML Decision logged (id={log_id}): {symbol} {action} -> {ml_result.get('recommendation')}")
        return log_id

    except Exception as e:
        logger.error(f"Error logging ML decision: {e}")
        return None


# ============================================================================
# API Endpoints
# ============================================================================

@router.get("/status")
async def get_ml_status():
    """
    Get ML system status - is it trained, what accuracy, etc.

    TRANSPARENCY: Shows if ML is active and how accurate it is.
    """
    learner = get_ml_learner()

    if learner is None:
        return {
            "success": True,
            "data": {
                "ml_available": False,
                "status": "ML not available (scikit-learn not installed)",
                "model_trained": False
            }
        }

    model_trained = learner.model is not None

    return {
        "success": True,
        "data": {
            "ml_available": True,
            "status": "Model trained and ready" if model_trained else "Model not trained",
            "model_trained": model_trained,
            "feature_importance": dict(sorted(
                learner.feature_importance.items(),
                key=lambda x: x[1],
                reverse=True
            )[:10]) if learner.feature_importance else {},
            "top_features": list(dict(sorted(
                learner.feature_importance.items(),
                key=lambda x: x[1],
                reverse=True
            )[:5]).keys()) if learner.feature_importance else []
        }
    }


@router.post("/train")
async def train_ml_model(config: TrainModelRequest = TrainModelRequest()):
    """
    Train the ML model on historical trade data.

    TRANSPARENCY: Shows exactly what the model learned and how accurate it is.
    """
    learner = get_ml_learner()

    if learner is None:
        raise HTTPException(
            status_code=500,
            detail="ML not available. Install scikit-learn: pip install scikit-learn"
        )

    try:
        # Train
        results = learner.train_pattern_classifier(lookback_days=config.lookback_days)

        if 'error' in results:
            return {
                "success": False,
                "error": results['error'],
                "message": "Training failed - need more data"
            }

        # Save model
        models_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
            'models'
        )
        os.makedirs(models_dir, exist_ok=True)
        model_path = os.path.join(models_dir, 'pattern_learner.pkl')
        learner.save_model(model_path)

        # Log training event
        log_ml_decision(
            symbol="ALL",
            action="TRAIN_MODEL",
            ml_result={
                'success_probability': results.get('accuracy', 0),
                'ml_confidence': 'N/A',
                'recommendation': 'TRAINED'
            },
            features={
                'samples': results.get('samples', 0),
                'accuracy': results.get('accuracy', 0),
                'f1_score': results.get('f1_score', 0)
            }
        )

        return {
            "success": True,
            "message": f"ML model trained on {results.get('samples', 0)} samples",
            "data": {
                "training_samples": results.get('samples', 0),
                "test_samples": results.get('test_samples', 0),
                "accuracy": round(results.get('accuracy', 0) * 100, 1),
                "precision": round(results.get('precision', 0) * 100, 1),
                "recall": round(results.get('recall', 0) * 100, 1),
                "f1_score": round(results.get('f1_score', 0) * 100, 1),
                "top_features": [
                    {"feature": f[0], "importance": round(f[1] * 100, 1)}
                    for f in results.get('top_features', [])[:10]
                ],
                "model_saved": model_path
            }
        }

    except Exception as e:
        logger.error(f"Training error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/predict")
async def predict_trade_success(request: PredictRequest):
    """
    Get ML prediction for a potential trade.

    TRANSPARENCY: Shows exactly why the ML recommends or rejects a trade.
    """
    ensure_ml_log_table()
    learner = get_ml_learner()

    if learner is None or learner.model is None:
        return {
            "success": True,
            "data": {
                "prediction": {
                    "success_probability": 0.5,
                    "ml_confidence": "UNKNOWN",
                    "recommendation": "TRADE",
                    "note": "ML model not trained - using baseline"
                },
                "ml_active": False
            }
        }

    # Build regime dict for prediction
    regime = {
        'rsi_5m': 50,
        'rsi_15m': 50,
        'rsi_1h': request.rsi_1h,
        'rsi_4h': (request.rsi_1h + request.rsi_1d) / 2,
        'rsi_1d': request.rsi_1d,
        'net_gamma': request.net_gex,
        'call_wall_distance_pct': 2.0,
        'put_wall_distance_pct': 2.0,
        'vix_current': request.vix,
        'liberation_setup_detected': False,
        'false_floor_detected': False,
        'monthly_magnet_above': 0,
        'monthly_magnet_below': 0,
        'confidence_score': request.confidence_score
    }

    # Get prediction
    prediction = learner.predict_pattern_success(regime)

    # Get similar patterns for context
    similar = learner.analyze_pattern_similarity(regime, top_n=3)

    # Prepare features for logging
    features = {
        'symbol': request.symbol,
        'strike': request.strike,
        'underlying': request.underlying_price,
        'dte': request.dte,
        'delta': request.delta,
        'iv': request.iv,
        'vix': request.vix,
        'net_gex': request.net_gex,
        'rsi_1h': request.rsi_1h,
        'rsi_1d': request.rsi_1d
    }

    # Log this prediction for transparency
    log_id = log_ml_decision(
        symbol=request.symbol,
        action="PREDICT_TRADE",
        ml_result=prediction,
        features=features,
        similar_patterns=similar
    )

    return {
        "success": True,
        "data": {
            "prediction": {
                "success_probability": round(prediction.get('success_probability', 0.5) * 100, 1),
                "ml_confidence": prediction.get('ml_confidence', 'UNKNOWN'),
                "recommendation": prediction.get('recommendation', 'UNKNOWN'),
                "adjusted_confidence": round(prediction.get('adjusted_confidence', 50), 1),
                "ml_boost": round(prediction.get('ml_boost', 0) * 100, 1)
            },
            "similar_patterns": [
                {
                    "similarity": round(s.get('similarity_score', 0) * 100, 1),
                    "outcome": s.get('outcome'),
                    "confidence": s.get('confidence'),
                    "price_change": round(s.get('price_change', 0), 2)
                }
                for s in similar[:3]
            ],
            "features_used": features,
            "log_id": log_id,
            "ml_active": True
        }
    }


@router.get("/feature-importance")
async def get_feature_importance():
    """
    Get ML feature importance rankings.

    TRANSPARENCY: Shows exactly which factors the ML considers most important.
    """
    learner = get_ml_learner()

    if learner is None or not learner.feature_importance:
        return {
            "success": True,
            "data": {
                "features": [],
                "message": "Model not trained yet"
            }
        }

    sorted_features = sorted(
        learner.feature_importance.items(),
        key=lambda x: x[1],
        reverse=True
    )

    return {
        "success": True,
        "data": {
            "features": [
                {
                    "name": f[0],
                    "importance_pct": round(f[1] * 100, 2),
                    "rank": i + 1
                }
                for i, f in enumerate(sorted_features)
            ],
            "interpretation": {
                "top_3": [f[0] for f in sorted_features[:3]],
                "description": f"The model weighs {sorted_features[0][0]} most heavily ({sorted_features[0][1]*100:.1f}%)"
                if sorted_features else "No features analyzed yet"
            }
        }
    }


@router.get("/logs")
async def get_ml_decision_logs(
    symbol: Optional[str] = None,
    limit: int = 50,
    include_features: bool = False
):
    """
    Get ML decision logs.

    TRANSPARENCY: Full audit trail of every ML decision made.
    """
    ensure_ml_log_table()

    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        if symbol:
            cursor.execute('''
                SELECT id, timestamp, symbol, action, ml_score, ml_confidence,
                       recommendation, features, outcome, actual_pnl
                FROM ml_decision_log
                WHERE symbol = %s
                ORDER BY timestamp DESC
                LIMIT %s
            ''', (symbol, limit))
        else:
            cursor.execute('''
                SELECT id, timestamp, symbol, action, ml_score, ml_confidence,
                       recommendation, features, outcome, actual_pnl
                FROM ml_decision_log
                ORDER BY timestamp DESC
                LIMIT %s
            ''', (limit,))

        rows = cursor.fetchall()
        conn.close()

        logs = []
        for row in rows:
            log_entry = {
                "id": row['id'],
                "timestamp": row['timestamp'].isoformat() if row['timestamp'] else None,
                "symbol": row['symbol'],
                "action": row['action'],
                "ml_score": float(row['ml_score']) if row['ml_score'] else 0.5,
                "ml_confidence": row['ml_confidence'],
                "recommendation": row['recommendation'],
                "outcome": row['outcome'],
                "actual_pnl": float(row['actual_pnl']) if row['actual_pnl'] else None
            }

            if include_features and row['features']:
                log_entry['features'] = row['features']

            logs.append(log_entry)

        return {
            "success": True,
            "data": {
                "logs": logs,
                "count": len(logs),
                "showing": f"Last {limit} decisions"
            }
        }

    except Exception as e:
        logger.error(f"Error fetching ML logs: {e}")
        return {
            "success": True,
            "data": {"logs": [], "count": 0, "message": "No logs yet"}
        }


@router.get("/accuracy-report")
async def get_ml_accuracy_report():
    """
    Get ML accuracy report comparing predictions to actual outcomes.

    TRANSPARENCY: Shows how accurate the ML has been.
    """
    ensure_ml_log_table()

    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Get predictions with outcomes
        cursor.execute('''
            SELECT
                recommendation,
                outcome,
                ml_score,
                actual_pnl
            FROM ml_decision_log
            WHERE outcome IS NOT NULL
            AND action = 'PREDICT_TRADE'
        ''')

        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return {
                "success": True,
                "data": {
                    "message": "No completed trades with ML predictions yet",
                    "total_predictions": 0
                }
            }

        # Calculate accuracy
        total = len(rows)
        correct = 0
        trade_recommended = 0
        trade_won = 0
        skip_recommended = 0
        skip_would_have_lost = 0

        for row in rows:
            rec = row['recommendation']
            outcome = row['outcome']
            pnl = float(row['actual_pnl']) if row['actual_pnl'] else 0

            if rec in ['TRADE', 'CAUTION']:
                trade_recommended += 1
                if pnl > 0:
                    trade_won += 1
                    correct += 1
            elif rec == 'SKIP':
                skip_recommended += 1
                if pnl < 0:
                    skip_would_have_lost += 1
                    correct += 1

        accuracy = (correct / total * 100) if total > 0 else 0
        trade_accuracy = (trade_won / trade_recommended * 100) if trade_recommended > 0 else 0
        skip_accuracy = (skip_would_have_lost / skip_recommended * 100) if skip_recommended > 0 else 0

        return {
            "success": True,
            "data": {
                "total_predictions": total,
                "overall_accuracy": round(accuracy, 1),
                "trade_recommendations": {
                    "total": trade_recommended,
                    "profitable": trade_won,
                    "accuracy": round(trade_accuracy, 1)
                },
                "skip_recommendations": {
                    "total": skip_recommended,
                    "correct_skips": skip_would_have_lost,
                    "accuracy": round(skip_accuracy, 1)
                },
                "value_added": "ML is contributing positively" if accuracy > 50 else "ML needs more training data"
            }
        }

    except Exception as e:
        logger.error(f"Error generating accuracy report: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/update-outcome")
async def update_ml_outcome(log_id: int, outcome: str, actual_pnl: float):
    """
    Update an ML prediction log with the actual outcome.

    Called after a trade closes to track ML accuracy.
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            UPDATE ml_decision_log
            SET outcome = %s, actual_pnl = %s
            WHERE id = %s
        ''', (outcome, actual_pnl, log_id))

        conn.commit()
        conn.close()

        return {
            "success": True,
            "message": f"Updated log {log_id} with outcome: {outcome}, P&L: ${actual_pnl:.2f}"
        }

    except Exception as e:
        logger.error(f"Error updating outcome: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Integration with SPX Backtest
# ============================================================================

@router.post("/score-spx-trade")
async def score_spx_trade(
    strike: float,
    underlying_price: float,
    dte: int,
    premium: float,
    vix: float = 15.0,
    net_gex: float = 0.0
):
    """
    Score an SPX put trade using ML + strategy rules.

    This is the KEY integration point - ML contributes to trade selection.

    Returns a comprehensive score that combines:
    1. ML prediction (60% weight)
    2. Risk/reward ratio (20% weight)
    3. Market conditions (20% weight)
    """
    ensure_ml_log_table()
    learner = get_ml_learner()

    # Calculate basic metrics
    otm_pct = (underlying_price - strike) / underlying_price * 100
    premium_pct = premium / underlying_price * 100

    # ML prediction
    ml_score = 0.5  # Baseline
    ml_confidence = "UNKNOWN"
    ml_recommendation = "TRADE"

    if learner and learner.model is not None:
        regime = {
            'rsi_5m': 50,
            'rsi_15m': 50,
            'rsi_1h': 50,
            'rsi_4h': 50,
            'rsi_1d': 50,
            'net_gamma': net_gex,
            'call_wall_distance_pct': otm_pct,
            'put_wall_distance_pct': otm_pct,
            'vix_current': vix,
            'liberation_setup_detected': False,
            'false_floor_detected': False,
            'monthly_magnet_above': 0,
            'monthly_magnet_below': 0,
            'confidence_score': 50
        }

        prediction = learner.predict_pattern_success(regime)
        ml_score = prediction.get('success_probability', 0.5)
        ml_confidence = prediction.get('ml_confidence', 'UNKNOWN')
        ml_recommendation = prediction.get('recommendation', 'TRADE')

    # Risk/Reward score (higher premium relative to risk = better)
    # At 45 DTE, 20 delta put, ~3-5% OTM is typical
    # Premium of 0.5-1.5% of underlying is good
    rr_score = min(1.0, premium_pct / 1.0)  # 1% premium = perfect score

    # Market conditions score
    # Low VIX (12-16): cautious, High VIX (>25): opportunities
    if vix < 12:
        market_score = 0.3  # Too calm, low premiums
    elif vix < 18:
        market_score = 0.6  # Normal
    elif vix < 25:
        market_score = 0.8  # Good premium environment
    else:
        market_score = 0.7  # High fear, risky but high premium

    # Combine scores (weighted)
    combined_score = (
        ml_score * 0.60 +
        rr_score * 0.20 +
        market_score * 0.20
    )

    # Final recommendation
    if combined_score >= 0.65:
        final_recommendation = "STRONG_TRADE"
    elif combined_score >= 0.50:
        final_recommendation = "TRADE"
    elif combined_score >= 0.40:
        final_recommendation = "CAUTION"
    else:
        final_recommendation = "SKIP"

    # Log this scoring
    log_ml_decision(
        symbol="SPX",
        action="SCORE_TRADE",
        ml_result={
            'success_probability': combined_score,
            'ml_confidence': ml_confidence,
            'recommendation': final_recommendation
        },
        features={
            'strike': strike,
            'underlying': underlying_price,
            'dte': dte,
            'premium': premium,
            'otm_pct': otm_pct,
            'vix': vix,
            'net_gex': net_gex,
            'ml_score': ml_score,
            'rr_score': rr_score,
            'market_score': market_score
        }
    )

    return {
        "success": True,
        "data": {
            "combined_score": round(combined_score * 100, 1),
            "recommendation": final_recommendation,
            "breakdown": {
                "ml_contribution": {
                    "score": round(ml_score * 100, 1),
                    "weight": "60%",
                    "confidence": ml_confidence,
                    "recommendation": ml_recommendation
                },
                "risk_reward_contribution": {
                    "score": round(rr_score * 100, 1),
                    "weight": "20%",
                    "premium_pct": round(premium_pct, 3)
                },
                "market_conditions_contribution": {
                    "score": round(market_score * 100, 1),
                    "weight": "20%",
                    "vix": vix
                }
            },
            "trade_details": {
                "strike": strike,
                "underlying": underlying_price,
                "otm_pct": round(otm_pct, 2),
                "dte": dte,
                "premium": premium
            }
        }
    }
