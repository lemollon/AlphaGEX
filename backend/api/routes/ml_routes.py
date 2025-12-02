"""
REAL Machine Learning API Routes for SPX Wheel Strategy

HONEST DISCLOSURE:
- ML can ONLY help if trained on REAL trade outcomes
- Without training data, ML predictions are meaningless
- The base strategy (selling puts) has an edge from volatility risk premium
- ML tries to improve WHEN to sell, not WHETHER selling works

This routes file provides:
1. Honest status about ML readiness
2. Training on REAL trade outcomes
3. Predictions with clear reasoning
4. Transparency about what ML can and cannot do
"""

import os
import sys
import logging
from datetime import datetime
from typing import Optional, List, Dict
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

# Add project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/ml", tags=["Machine Learning"])


# ============================================================================
# Request/Response Models
# ============================================================================

class TrainRequest(BaseModel):
    """Request to train ML model"""
    min_samples: int = 30  # Minimum trades needed to train


class PredictRequest(BaseModel):
    """Request for ML prediction - requires REAL market data"""
    trade_date: str
    strike: float
    underlying_price: float
    dte: int
    delta: float = 0.20
    premium: float

    # These should come from REAL data sources
    iv: float  # Option implied volatility
    iv_rank: float  # IV percentile (0-100)
    vix: float
    vix_percentile: float = 50  # VIX percentile (0-100)
    vix_term_structure: float = 0  # VIX - VIX3M

    # GEX data (from Trading Volatility API)
    put_wall_distance_pct: float = 5
    call_wall_distance_pct: float = 5
    net_gex: float = 0

    # Market data
    spx_20d_return: float = 0
    spx_5d_return: float = 0
    spx_distance_from_high: float = 0


class RecordOutcomeRequest(BaseModel):
    """Request to record trade outcome for ML learning"""
    trade_id: str
    outcome: str  # 'WIN' or 'LOSS'
    pnl: float
    settlement_price: float
    max_drawdown: float = 0


# ============================================================================
# HONEST STATUS ENDPOINT
# ============================================================================

@router.get("/status")
async def get_ml_status():
    """
    Get HONEST status of ML system.

    Returns:
    - Whether ML is available
    - Whether model is trained
    - How many trades it was trained on
    - Whether you should trust it
    """
    try:
        from trading.spx_wheel_ml import get_spx_wheel_ml_trainer, get_outcome_tracker, ML_AVAILABLE

        trainer = get_spx_wheel_ml_trainer()
        tracker = get_outcome_tracker()

        # Get outcome count
        try:
            outcomes = tracker.get_all_outcomes()
            outcome_count = len(outcomes)
        except:
            outcome_count = 0

        model_trained = trainer.model is not None
        metrics = trainer.training_metrics

        return {
            "success": True,
            "data": {
                "ml_library_available": ML_AVAILABLE,
                "model_trained": model_trained,
                "training_data_available": outcome_count,
                "can_train": outcome_count >= 30,
                "should_trust_predictions": model_trained and outcome_count >= 50,

                "honest_assessment": _get_honest_assessment(model_trained, outcome_count),

                "training_metrics": metrics if metrics else None,

                "what_ml_can_do": [
                    "Identify high IV environments (better premium)",
                    "Avoid extreme stress conditions",
                    "Find support levels for safer strikes",
                    "Time entries after pullbacks"
                ],
                "what_ml_cannot_do": [
                    "Predict black swan events",
                    "Guarantee profits",
                    "Eliminate drawdowns",
                    "Create edge where none exists"
                ]
            }
        }
    except Exception as e:
        logger.error(f"Status error: {e}")
        return {
            "success": True,
            "data": {
                "ml_library_available": False,
                "model_trained": False,
                "error": str(e),
                "honest_assessment": "ML system not available. Use mechanical strategy rules."
            }
        }


def _get_honest_assessment(model_trained: bool, outcome_count: int) -> str:
    """Provide honest assessment of ML readiness"""
    if not model_trained and outcome_count < 30:
        return f"ML NOT READY. Need {30 - outcome_count} more completed trades to train. Use mechanical rules."
    elif not model_trained and outcome_count >= 30:
        return "ML can be trained. Call POST /api/ml/train to train on your trade history."
    elif model_trained and outcome_count < 50:
        return f"ML trained on {outcome_count} trades. Results may not be reliable yet. Consider as secondary signal only."
    elif model_trained and outcome_count < 100:
        return f"ML trained on {outcome_count} trades. Reasonably reliable for filtering obvious bad trades."
    else:
        return f"ML trained on {outcome_count} trades. Should provide useful filtering."


# ============================================================================
# TRAINING ENDPOINT
# ============================================================================

@router.post("/train")
async def train_ml_model(config: TrainRequest = TrainRequest()):
    """
    Train ML model on REAL trade outcomes.

    IMPORTANT: This trains on YOUR actual trades, not theoretical data.
    The more trades you have, the better the model.

    Minimum 30 trades required to train.
    """
    try:
        from trading.spx_wheel_ml import get_spx_wheel_ml_trainer, get_outcome_tracker

        trainer = get_spx_wheel_ml_trainer()
        tracker = get_outcome_tracker()

        # Get all completed outcomes
        outcomes = tracker.get_all_outcomes()

        if len(outcomes) < config.min_samples:
            return {
                "success": False,
                "error": f"Not enough training data",
                "detail": {
                    "trades_available": len(outcomes),
                    "trades_needed": config.min_samples,
                    "action_required": "Complete more trades and record their outcomes using POST /api/ml/record-outcome"
                }
            }

        # Train
        result = trainer.train(outcomes, min_samples=config.min_samples)

        if 'error' in result:
            return {
                "success": False,
                "error": result['error'],
                "detail": result
            }

        return {
            "success": True,
            "message": f"ML model trained on {len(outcomes)} trades",
            "data": {
                "metrics": result['metrics'],
                "interpretation": result['interpretation'],
                "what_this_means": _explain_training_results(result)
            }
        }

    except Exception as e:
        logger.error(f"Training error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _explain_training_results(result: Dict) -> str:
    """Plain English explanation of training results"""
    metrics = result.get('metrics', {})
    interp = result.get('interpretation', {})

    baseline = metrics.get('baseline_win_rate', 0)
    accuracy = metrics.get('test_accuracy', 0)

    if accuracy > baseline + 0.05:
        return f"ML is adding value. Your trades have a {baseline:.0%} base win rate. ML predicts correctly {accuracy:.0%} of the time. Use ML to filter trades."
    elif accuracy > baseline:
        return f"ML shows slight improvement over baseline ({baseline:.0%} -> {accuracy:.0%}). May help avoid worst trades."
    else:
        return f"ML is NOT improving on your base win rate ({baseline:.0%}). Stick to mechanical rules. This could mean: (1) not enough data, (2) your rules are already optimal, or (3) market is random."


# ============================================================================
# PREDICTION ENDPOINT
# ============================================================================

@router.post("/predict")
async def predict_trade(request: PredictRequest):
    """
    Get ML prediction for a potential trade.

    IMPORTANT: This uses REAL features you provide.
    Garbage in = garbage out. Use accurate market data.

    Returns:
    - Win probability (if model is trained)
    - Clear reasoning for the prediction
    - Key factors driving the decision
    """
    try:
        from trading.spx_wheel_ml import (
            get_spx_wheel_ml_trainer,
            SPXWheelFeatures
        )

        trainer = get_spx_wheel_ml_trainer()

        # Build features
        premium_to_strike = request.premium / request.strike * 100
        annualized_return = premium_to_strike * (365 / request.dte) if request.dte > 0 else 0

        features = SPXWheelFeatures(
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
            premium_to_strike_pct=premium_to_strike,
            annualized_return=annualized_return
        )

        # Get prediction
        prediction = trainer.predict(features)

        return {
            "success": True,
            "data": {
                "prediction": prediction,
                "trade_summary": {
                    "strike": request.strike,
                    "underlying": request.underlying_price,
                    "otm_pct": round((request.underlying_price - request.strike) / request.underlying_price * 100, 2),
                    "dte": request.dte,
                    "premium": request.premium,
                    "annualized_return": round(annualized_return, 1)
                },
                "important_note": "ML prediction is only as good as (1) your training data and (2) the accuracy of the features you provided."
            }
        }

    except Exception as e:
        logger.error(f"Prediction error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# OUTCOME RECORDING - CRITICAL FOR ML LEARNING
# ============================================================================

@router.post("/record-outcome")
async def record_trade_outcome(request: RecordOutcomeRequest):
    """
    Record a trade outcome - THIS IS HOW ML LEARNS.

    After each trade closes:
    1. Call this endpoint with the outcome
    2. ML uses this data to improve

    Without recording outcomes, ML cannot learn from your trades.
    """
    try:
        from trading.spx_wheel_ml import get_outcome_tracker

        tracker = get_outcome_tracker()

        outcome = tracker.record_trade_outcome(
            trade_id=request.trade_id,
            outcome=request.outcome,
            pnl=request.pnl,
            settlement_price=request.settlement_price,
            max_drawdown=request.max_drawdown
        )

        if outcome is None:
            return {
                "success": False,
                "error": f"Trade {request.trade_id} not found. Record entry first with POST /api/ml/record-entry"
            }

        # Check if we can train now
        all_outcomes = tracker.get_all_outcomes()

        return {
            "success": True,
            "message": f"Recorded {request.outcome} for trade {request.trade_id}",
            "data": {
                "trade_id": request.trade_id,
                "outcome": request.outcome,
                "pnl": request.pnl,
                "total_recorded_outcomes": len(all_outcomes),
                "can_train_ml": len(all_outcomes) >= 30,
                "next_step": "Call POST /api/ml/train to retrain model" if len(all_outcomes) >= 30 else f"Need {30 - len(all_outcomes)} more outcomes to train"
            }
        }

    except Exception as e:
        logger.error(f"Record outcome error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/record-entry")
async def record_trade_entry(request: PredictRequest, trade_id: str):
    """
    Record a trade entry for future outcome tracking.

    Call this when you open a new trade.
    Later, call /record-outcome when the trade closes.
    """
    try:
        from trading.spx_wheel_ml import get_outcome_tracker, SPXWheelFeatures

        tracker = get_outcome_tracker()

        premium_to_strike = request.premium / request.strike * 100
        annualized_return = premium_to_strike * (365 / request.dte) if request.dte > 0 else 0

        features = SPXWheelFeatures(
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
            premium_to_strike_pct=premium_to_strike,
            annualized_return=annualized_return
        )

        tracker.record_trade_entry(trade_id, features)

        return {
            "success": True,
            "message": f"Recorded entry for trade {trade_id}",
            "data": {
                "trade_id": trade_id,
                "features_recorded": len(SPXWheelFeatures.feature_names()),
                "next_step": f"When trade closes, call POST /api/ml/record-outcome with trade_id={trade_id}"
            }
        }

    except Exception as e:
        logger.error(f"Record entry error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# FEATURE IMPORTANCE - WHAT ACTUALLY MATTERS
# ============================================================================

@router.get("/feature-importance")
async def get_feature_importance():
    """
    See which features the ML model considers most important.

    This shows what factors actually drive profitable trades
    based on YOUR trading history.
    """
    try:
        from trading.spx_wheel_ml import get_spx_wheel_ml_trainer

        trainer = get_spx_wheel_ml_trainer()

        if not trainer.model:
            return {
                "success": True,
                "data": {
                    "model_trained": False,
                    "message": "Train the model first to see feature importance",
                    "theoretical_importance": {
                        "iv_rank": "HIGH - Selling high IV = better premium",
                        "vix": "HIGH - Indicates market fear/premium levels",
                        "put_wall_distance": "MEDIUM - Support levels matter",
                        "spx_5d_return": "MEDIUM - Mean reversion after drops",
                        "annualized_return": "MEDIUM - Premium quality"
                    }
                }
            }

        importance = trainer.feature_importance
        sorted_features = sorted(importance.items(), key=lambda x: x[1], reverse=True)

        return {
            "success": True,
            "data": {
                "model_trained": True,
                "features": [
                    {
                        "name": f[0],
                        "importance": round(f[1] * 100, 1),
                        "meaning": _get_feature_meaning(f[0])
                    }
                    for f in sorted_features
                ],
                "interpretation": f"Your model finds '{sorted_features[0][0]}' most important ({sorted_features[0][1]*100:.1f}%)"
            }
        }

    except Exception as e:
        logger.error(f"Feature importance error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _get_feature_meaning(feature: str) -> str:
    """Get plain English meaning of each feature"""
    meanings = {
        'iv_rank': 'IV percentile - higher = more expensive options = better to sell',
        'iv': 'Implied volatility of the option',
        'vix': 'Market fear gauge - higher = more premium but more risk',
        'vix_percentile': 'VIX compared to history',
        'vix_term_structure': 'VIX curve shape - backwardation = stress',
        'put_wall_distance_pct': 'Distance to support from options positioning',
        'call_wall_distance_pct': 'Distance to resistance',
        'net_gex_billions': 'Dealer gamma - positive = dealers buy dips',
        'spx_20d_return': '20-day momentum',
        'spx_5d_return': 'Recent move - negative = potential mean reversion',
        'spx_distance_from_high': 'How far below all-time high',
        'dte': 'Days to expiration',
        'delta': 'Option delta - probability of ITM',
        'premium_to_strike_pct': 'Premium yield',
        'annualized_return': 'Annualized return if trade wins'
    }
    return meanings.get(feature, 'Feature for ML model')


# ============================================================================
# WHY THE STRATEGY WORKS - HONEST EXPLANATION
# ============================================================================

@router.get("/strategy-explanation")
async def get_strategy_explanation():
    """
    HONEST explanation of why SPX put selling can make money.

    No hype, no guarantees - just the math and risks.
    """
    return {
        "success": True,
        "data": {
            "strategy": "SPX Cash-Secured Put Selling",

            "why_it_works": {
                "volatility_risk_premium": {
                    "explanation": "Implied volatility exceeds realized volatility ~80% of the time",
                    "why": "People pay extra for insurance (put protection)",
                    "you_benefit": "By selling that insurance, you collect the premium"
                },
                "theta_decay": {
                    "explanation": "Options lose value every day as expiration approaches",
                    "why": "Time value decays - mathematical certainty",
                    "you_benefit": "Every day that passes, you keep more premium"
                },
                "probability": {
                    "explanation": "20-delta puts have ~80% chance of expiring worthless",
                    "why": "You're selling far out-of-the-money options",
                    "you_benefit": "You win more often than you lose"
                }
            },

            "why_it_can_fail": {
                "tail_risk": {
                    "explanation": "The 20% losses can be HUGE",
                    "examples": ["March 2020: SPX -34%", "2008: SPX -50%+"],
                    "impact": "One bad month can wipe out a year of gains"
                },
                "asymmetric_payoff": {
                    "explanation": "You win small amounts often, lose big occasionally",
                    "math": "Win $2,000 eight times, lose $10,000 twice = breakeven"
                },
                "drawdowns": {
                    "explanation": "Even without crashes, you'll have losing streaks",
                    "reality": "3-4 losses in a row is normal and expected"
                }
            },

            "what_ml_adds": {
                "helps_with": [
                    "Identifying HIGH IV environments (sell when premium is rich)",
                    "Avoiding EXTREME STRESS (skip when crash indicators flash)",
                    "Finding SUPPORT (sell into put walls)",
                    "TIMING (enter after pullbacks)"
                ],
                "cannot_help_with": [
                    "Predicting black swans (nobody can)",
                    "Eliminating losses (impossible)",
                    "Guaranteeing profits (no such thing)"
                ]
            },

            "realistic_expectations": {
                "annual_return": "10-20% in normal years (if done well)",
                "max_drawdown": "20-40% in bad years (March 2020 type)",
                "win_rate": "70-85% of trades profitable",
                "key_insight": "Survival matters more than optimization. Don't oversize positions."
            },

            "bottom_line": "This strategy has a statistical edge from volatility risk premium. ML can help you capture that edge more efficiently. But no ML can turn a losing strategy into a winner or protect against black swans."
        }
    }


# ============================================================================
# DATA QUALITY CHECK
# ============================================================================

@router.get("/data-quality")
async def check_data_quality():
    """
    Check quality of your training data.

    More data = better ML. Better data = better ML.
    """
    try:
        from trading.spx_wheel_ml import get_outcome_tracker

        tracker = get_outcome_tracker()
        outcomes = tracker.get_all_outcomes()

        if not outcomes:
            return {
                "success": True,
                "data": {
                    "total_trades": 0,
                    "message": "No trade outcomes recorded yet. Record trades using /record-entry and /record-outcome",
                    "quality": "NO_DATA"
                }
            }

        wins = sum(1 for o in outcomes if o.is_win())
        losses = len(outcomes) - wins
        total_pnl = sum(o.pnl for o in outcomes)
        avg_pnl = total_pnl / len(outcomes)

        return {
            "success": True,
            "data": {
                "total_trades": len(outcomes),
                "wins": wins,
                "losses": losses,
                "win_rate": round(wins / len(outcomes) * 100, 1),
                "total_pnl": round(total_pnl, 2),
                "avg_pnl": round(avg_pnl, 2),

                "quality": _assess_data_quality(len(outcomes)),
                "can_train": len(outcomes) >= 30,

                "recommendation": _get_data_recommendation(len(outcomes), wins / len(outcomes) if outcomes else 0)
            }
        }

    except Exception as e:
        logger.error(f"Data quality error: {e}")
        return {
            "success": True,
            "data": {
                "error": str(e),
                "quality": "UNKNOWN"
            }
        }


def _assess_data_quality(count: int) -> str:
    if count < 30:
        return "INSUFFICIENT"
    elif count < 50:
        return "MINIMAL"
    elif count < 100:
        return "ADEQUATE"
    elif count < 200:
        return "GOOD"
    else:
        return "EXCELLENT"


def _get_data_recommendation(count: int, win_rate: float) -> str:
    if count < 30:
        return f"Need {30 - count} more trades. Keep trading and recording outcomes."
    elif count < 50:
        return "Can train ML but results may be unreliable. More data is better."
    elif win_rate < 0.5:
        return "Warning: Win rate below 50%. ML might not help a losing strategy. Review your rules first."
    elif win_rate > 0.85:
        return "Excellent win rate! ML can help maintain this edge and avoid the occasional bad trade."
    else:
        return "Good data quality. Train ML to see if it can improve your already solid results."


# ============================================================================
# ML DECISION LOGS - FULL TRANSPARENCY
# ============================================================================

def _ensure_ml_logs_table():
    """Create ML logs table if not exists"""
    try:
        from database_adapter import get_connection
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ml_decision_logs (
                id SERIAL PRIMARY KEY,
                timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                action VARCHAR(50) NOT NULL,
                symbol VARCHAR(20) DEFAULT 'SPX',
                details JSONB,
                ml_score DECIMAL(5,4),
                recommendation VARCHAR(20),
                reasoning TEXT,
                trade_id VARCHAR(50),
                backtest_id VARCHAR(50)
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_ml_logs_ts ON ml_decision_logs(timestamp DESC)')
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Error creating ML logs table: {e}")
        return False


def log_ml_action(action: str, details: dict, ml_score: float = None,
                  recommendation: str = None, reasoning: str = None,
                  trade_id: str = None, backtest_id: str = None):
    """Log an ML action for transparency"""
    _ensure_ml_logs_table()
    try:
        from database_adapter import get_connection
        import json
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO ml_decision_logs
            (action, details, ml_score, recommendation, reasoning, trade_id, backtest_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (
            action,
            json.dumps(details),
            ml_score,
            recommendation,
            reasoning,
            trade_id,
            backtest_id
        ))

        log_id = cursor.fetchone()[0]
        conn.commit()
        conn.close()

        logger.info(f"ML Log [{log_id}]: {action} - {recommendation or 'N/A'}")
        return log_id
    except Exception as e:
        logger.error(f"Failed to log ML action: {e}")
        return None


@router.get("/logs")
async def get_ml_logs(limit: int = 100, action_filter: str = None):
    """
    Get ML decision logs - SEE EVERYTHING ML DOES.

    Returns chronological log of all ML actions:
    - Trade scoring
    - Training events
    - Predictions made
    - Recommendations given
    """
    _ensure_ml_logs_table()
    try:
        from database_adapter import get_connection
        conn = get_connection()
        cursor = conn.cursor()

        if action_filter:
            cursor.execute('''
                SELECT id, timestamp, action, symbol, details, ml_score,
                       recommendation, reasoning, trade_id, backtest_id
                FROM ml_decision_logs
                WHERE action LIKE %s
                ORDER BY timestamp DESC
                LIMIT %s
            ''', (f'%{action_filter}%', limit))
        else:
            cursor.execute('''
                SELECT id, timestamp, action, symbol, details, ml_score,
                       recommendation, reasoning, trade_id, backtest_id
                FROM ml_decision_logs
                ORDER BY timestamp DESC
                LIMIT %s
            ''', (limit,))

        rows = cursor.fetchall()
        conn.close()

        logs = []
        for row in rows:
            logs.append({
                "id": row[0],
                "timestamp": row[1].isoformat() if row[1] else None,
                "action": row[2],
                "symbol": row[3],
                "details": row[4],
                "ml_score": float(row[5]) if row[5] else None,
                "recommendation": row[6],
                "reasoning": row[7],
                "trade_id": row[8],
                "backtest_id": row[9]
            })

        return {
            "success": True,
            "data": {
                "logs": logs,
                "count": len(logs),
                "showing": f"Last {limit} ML actions"
            }
        }

    except Exception as e:
        logger.error(f"Error fetching ML logs: {e}")
        return {
            "success": True,
            "data": {
                "logs": [],
                "count": 0,
                "message": f"Logs not available: {str(e)}"
            }
        }


@router.get("/logs/summary")
async def get_ml_logs_summary():
    """Get summary of ML activity"""
    _ensure_ml_logs_table()
    try:
        from database_adapter import get_connection
        conn = get_connection()
        cursor = conn.cursor()

        # Count by action type
        cursor.execute('''
            SELECT action, COUNT(*),
                   AVG(ml_score) as avg_score,
                   COUNT(CASE WHEN recommendation = 'TRADE' THEN 1 END) as trade_count,
                   COUNT(CASE WHEN recommendation = 'SKIP' THEN 1 END) as skip_count
            FROM ml_decision_logs
            WHERE timestamp > NOW() - INTERVAL '24 hours'
            GROUP BY action
        ''')

        action_stats = cursor.fetchall()

        # Recent activity
        cursor.execute('''
            SELECT COUNT(*) FROM ml_decision_logs
            WHERE timestamp > NOW() - INTERVAL '1 hour'
        ''')
        last_hour = cursor.fetchone()[0]

        cursor.execute('''
            SELECT COUNT(*) FROM ml_decision_logs
            WHERE timestamp > NOW() - INTERVAL '24 hours'
        ''')
        last_24h = cursor.fetchone()[0]

        conn.close()

        return {
            "success": True,
            "data": {
                "activity": {
                    "last_hour": last_hour,
                    "last_24_hours": last_24h
                },
                "by_action": [
                    {
                        "action": row[0],
                        "count": row[1],
                        "avg_score": round(float(row[2]), 3) if row[2] else None,
                        "trade_recommendations": row[3],
                        "skip_recommendations": row[4]
                    }
                    for row in action_stats
                ]
            }
        }

    except Exception as e:
        logger.error(f"Error fetching ML summary: {e}")
        return {"success": True, "data": {"activity": {"last_hour": 0, "last_24_hours": 0}, "by_action": []}}


# ============================================================================
# AUTOMATED ML - NO MANUAL INTERVENTION NEEDED
# ============================================================================

@router.post("/auto-process-backtest")
async def auto_process_backtest(backtest_id: str, trades: list):
    """
    AUTOMATED: Process backtest trades for ML training.

    Called automatically after each backtest:
    1. Records all trades as ML training data
    2. Auto-trains if we have enough data
    3. Logs everything
    """
    try:
        from trading.spx_wheel_ml import (
            get_spx_wheel_ml_trainer,
            get_outcome_tracker,
            SPXWheelFeatures,
            SPXWheelOutcome
        )

        tracker = get_outcome_tracker()
        trainer = get_spx_wheel_ml_trainer()

        recorded = 0
        for trade in trades:
            trade_id = f"{backtest_id}_{trade.get('trade_date', 'unknown')}_{trade.get('strike', 0)}"

            # Extract features from trade
            strike = trade.get('strike', 0)
            underlying = trade.get('entry_underlying_price', trade.get('underlying_price', 0))
            pnl = trade.get('total_pnl', trade.get('pnl', 0)) or 0

            if not strike or not underlying:
                continue

            # Create features (use available data, estimate what's missing)
            features = SPXWheelFeatures(
                trade_date=trade.get('trade_date', ''),
                strike=float(strike),
                underlying_price=float(underlying),
                dte=trade.get('dte', 45),
                delta=trade.get('delta', 0.20),
                premium=trade.get('premium', trade.get('entry_price', 0)) or 0,
                iv=trade.get('iv', 0.15),
                iv_rank=trade.get('iv_rank', 50),
                vix=trade.get('vix', 15),
                vix_percentile=trade.get('vix_percentile', 50),
                vix_term_structure=trade.get('vix_term_structure', 0),
                put_wall_distance_pct=trade.get('put_wall_distance', 5),
                call_wall_distance_pct=trade.get('call_wall_distance', 5),
                net_gex=trade.get('net_gex', 0),
                spx_20d_return=trade.get('spx_20d_return', 0),
                spx_5d_return=trade.get('spx_5d_return', 0),
                spx_distance_from_high=trade.get('distance_from_high', 0),
                premium_to_strike_pct=float(trade.get('premium', 0) or 0) / float(strike) * 100 if strike else 0,
                annualized_return=0  # Will be calculated
            )

            # Determine outcome
            outcome = 'WIN' if float(pnl) > 0 else 'LOSS'

            # Record for training
            tracker.record_trade_entry(trade_id, features)
            tracker.record_trade_outcome(
                trade_id=trade_id,
                outcome=outcome,
                pnl=float(pnl),
                settlement_price=trade.get('settlement_price', underlying),
                max_drawdown=trade.get('max_drawdown', 0)
            )

            recorded += 1

            # Log this
            log_ml_action(
                action="AUTO_RECORD_TRADE",
                details={
                    "strike": strike,
                    "underlying": underlying,
                    "pnl": pnl,
                    "outcome": outcome
                },
                ml_score=None,
                recommendation=outcome,
                reasoning=f"Auto-recorded from backtest {backtest_id}",
                trade_id=trade_id,
                backtest_id=backtest_id
            )

        # Check if we can auto-train
        all_outcomes = tracker.get_all_outcomes()
        can_train = len(all_outcomes) >= 30
        trained = False

        if can_train and not trainer.model:
            # Auto-train!
            result = trainer.train(all_outcomes)
            trained = 'error' not in result

            log_ml_action(
                action="AUTO_TRAIN",
                details={
                    "samples": len(all_outcomes),
                    "success": trained,
                    "accuracy": result.get('metrics', {}).get('test_accuracy') if trained else None
                },
                ml_score=result.get('metrics', {}).get('test_accuracy') if trained else None,
                recommendation="TRAINED" if trained else "FAILED",
                reasoning=f"Auto-trained on {len(all_outcomes)} samples from backtest",
                backtest_id=backtest_id
            )

        return {
            "success": True,
            "data": {
                "trades_recorded": recorded,
                "total_training_samples": len(all_outcomes),
                "can_train": can_train,
                "auto_trained": trained,
                "message": f"Recorded {recorded} trades. {'Auto-trained ML model!' if trained else f'Need {30 - len(all_outcomes)} more for training' if not can_train else 'Model already trained'}"
            }
        }

    except Exception as e:
        logger.error(f"Auto-process error: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e)
        }


@router.post("/score-and-log")
async def score_trade_and_log(
    strike: float,
    underlying_price: float,
    dte: int,
    premium: float,
    iv: float = 0.15,
    iv_rank: float = 50,
    vix: float = 15,
    trade_id: str = None
):
    """
    Score a trade AND log the decision - AUTOMATED TRANSPARENCY.

    Use this for live trading - every decision is logged.
    """
    try:
        from trading.spx_wheel_ml import get_spx_wheel_ml_trainer, SPXWheelFeatures

        trainer = get_spx_wheel_ml_trainer()

        # Build features
        premium_to_strike = premium / strike * 100
        annualized_return = premium_to_strike * (365 / dte) if dte > 0 else 0

        features = SPXWheelFeatures(
            trade_date=datetime.now().strftime('%Y-%m-%d'),
            strike=strike,
            underlying_price=underlying_price,
            dte=dte,
            delta=0.20,
            premium=premium,
            iv=iv,
            iv_rank=iv_rank,
            vix=vix,
            vix_percentile=50,
            vix_term_structure=0,
            put_wall_distance_pct=(underlying_price - strike) / underlying_price * 100,
            call_wall_distance_pct=5,
            net_gex=0,
            spx_20d_return=0,
            spx_5d_return=0,
            spx_distance_from_high=0,
            premium_to_strike_pct=premium_to_strike,
            annualized_return=annualized_return
        )

        # Get prediction
        prediction = trainer.predict(features)

        # Log the decision
        log_id = log_ml_action(
            action="SCORE_TRADE",
            details={
                "strike": strike,
                "underlying": underlying_price,
                "dte": dte,
                "premium": premium,
                "iv": iv,
                "iv_rank": iv_rank,
                "vix": vix,
                "annualized_return": annualized_return
            },
            ml_score=prediction.get('win_probability'),
            recommendation=prediction.get('recommendation'),
            reasoning=prediction.get('reasoning'),
            trade_id=trade_id
        )

        return {
            "success": True,
            "data": {
                "prediction": prediction,
                "log_id": log_id,
                "trade_details": {
                    "strike": strike,
                    "underlying": underlying_price,
                    "otm_pct": round((underlying_price - strike) / underlying_price * 100, 2),
                    "premium": premium,
                    "annualized_return": round(annualized_return, 1)
                }
            }
        }

    except Exception as e:
        logger.error(f"Score and log error: {e}")
        return {"success": False, "error": str(e)}
