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
    """
    Verify ML logs table exists.
    NOTE: Table 'ml_decision_logs' is now defined in db/config_and_database.py (single source of truth).
    """
    # Table is created by main schema - just return True
    return True


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


# ============================================================================
# SAGE (ARES ML ADVISOR) ENDPOINTS - Trading Bot ML Intelligence
# ============================================================================

class SagePredictRequest(BaseModel):
    """Request for SAGE (ARES ML Advisor) prediction"""
    vix: float
    day_of_week: int = None  # 0-6, defaults to today
    price: float = None  # SPY price
    price_change_1d: float = 0.0
    expected_move_pct: float = 1.0
    gex_regime_positive: bool = True
    gex_normalized: float = 0.0
    gex_distance_to_flip_pct: float = 5.0
    gex_between_walls: bool = True
    vix_percentile_30d: float = 50.0
    vix_change_1d: float = 0.0
    win_rate_30d: float = 0.7


@router.get("/sage/status")
async def get_sage_status():
    """
    Get SAGE (ARES ML Advisor) status - the PRIMARY ML system for trading bots.

    SAGE provides ML-driven predictions for Iron Condor and directional strategies.
    Used by ARES, ATHENA, ICARUS, PEGASUS, and TITAN bots.
    """
    try:
        from quant.ares_ml_advisor import get_advisor, AresMLAdvisor

        advisor = get_advisor()

        # Check if model is trained
        model_trained = advisor.model is not None
        model_version = advisor.model_version if hasattr(advisor, 'model_version') else None

        # Get training metrics if available
        training_metrics = None
        if hasattr(advisor, 'training_metrics') and advisor.training_metrics:
            tm = advisor.training_metrics
            training_metrics = {
                "accuracy": tm.accuracy if hasattr(tm, 'accuracy') else None,
                "precision": tm.precision if hasattr(tm, 'precision') else None,
                "recall": tm.recall if hasattr(tm, 'recall') else None,
                "f1": tm.f1 if hasattr(tm, 'f1') else None,
                "auc_roc": tm.auc_roc if hasattr(tm, 'auc_roc') else None,
                "brier_score": tm.brier_score if hasattr(tm, 'brier_score') else None
            }

        # Count training data from outcomes table
        training_data_count = 0
        try:
            from database_adapter import get_connection
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM ares_ml_outcomes WHERE actual_outcome IS NOT NULL")
            training_data_count = cursor.fetchone()[0]
            conn.close()
        except:
            pass

        can_train = training_data_count >= 30
        should_trust = model_trained and training_data_count >= 50

        return {
            "success": True,
            "ml_library_available": True,
            "model_trained": model_trained,
            "model_version": model_version,
            "training_data_available": training_data_count,
            "can_train": can_train,
            "should_trust_predictions": should_trust,
            "honest_assessment": _get_sage_assessment(model_trained, training_data_count),
            "training_metrics": training_metrics,
            "what_ml_can_do": [
                "Identify favorable market conditions from historical patterns",
                "Adjust position sizing based on win probability",
                "Learn from KRONOS backtest results and live trades",
                "Provide calibrated probability estimates",
                "Integrate GEX regime signals for better timing"
            ],
            "what_ml_cannot_do": [
                "Predict black swan events or flash crashes",
                "Guarantee profits on any individual trade",
                "Eliminate the inherent risks of options trading",
                "Replace proper risk management and position sizing",
                "Foresee unprecedented market conditions"
            ]
        }

    except ImportError as e:
        logger.error(f"SAGE import error: {e}")
        return {
            "success": True,
            "ml_library_available": False,
            "model_trained": False,
            "error": f"SAGE module not available: {str(e)}",
            "honest_assessment": "SAGE (ARES ML Advisor) module not available. Using fallback rules."
        }
    except Exception as e:
        logger.error(f"SAGE status error: {e}")
        return {
            "success": False,
            "error": str(e)
        }


def _get_sage_assessment(model_trained: bool, data_count: int) -> str:
    """Provide honest assessment of SAGE readiness"""
    if not model_trained and data_count < 30:
        return f"SAGE needs training data. Currently have {data_count} outcomes, need 30 minimum. Using conservative fallback rules."
    elif not model_trained and data_count >= 30:
        return "SAGE can be trained. Sufficient data available. Call POST /api/ml/sage/train to train."
    elif model_trained and data_count < 50:
        return f"SAGE trained on {data_count} trades. Predictions available but may have limited reliability. Consider as secondary signal."
    elif model_trained and data_count < 100:
        return f"SAGE trained on {data_count} trades. Reasonably reliable for filtering trade opportunities."
    else:
        return f"SAGE trained on {data_count} trades. Should provide useful ML-driven predictions for trading decisions."


@router.post("/sage/predict")
async def sage_predict(request: SagePredictRequest):
    """
    Get SAGE (ARES ML Advisor) prediction for current market conditions.

    Returns win probability, trading advice, and suggested position sizing.
    """
    try:
        from quant.ares_ml_advisor import get_advisor
        from datetime import datetime

        advisor = get_advisor()

        # Default day_of_week to today if not provided
        day_of_week = request.day_of_week
        if day_of_week is None:
            day_of_week = datetime.now().weekday()

        # Get prediction
        prediction = advisor.predict(
            vix=request.vix,
            day_of_week=day_of_week,
            price=request.price,
            price_change_1d=request.price_change_1d,
            expected_move_pct=request.expected_move_pct,
            gex_regime_positive=request.gex_regime_positive,
            gex_normalized=request.gex_normalized,
            gex_distance_to_flip_pct=request.gex_distance_to_flip_pct,
            gex_between_walls=request.gex_between_walls,
            vix_percentile_30d=request.vix_percentile_30d,
            vix_change_1d=request.vix_change_1d,
            win_rate_30d=request.win_rate_30d
        )

        # Convert to dict if it's a dataclass
        prediction_dict = {}
        if hasattr(prediction, '__dict__'):
            for key, value in prediction.__dict__.items():
                if key == 'advice' and hasattr(value, 'value'):
                    prediction_dict[key] = value.value
                elif key == 'top_factors':
                    prediction_dict[key] = list(value) if value else []
                else:
                    prediction_dict[key] = value
        else:
            prediction_dict = prediction

        # Log the prediction
        log_ml_action(
            action="SAGE_PREDICT",
            details={
                "vix": request.vix,
                "day_of_week": day_of_week,
                "gex_regime": "positive" if request.gex_regime_positive else "negative"
            },
            ml_score=prediction_dict.get('win_probability'),
            recommendation=prediction_dict.get('advice'),
            reasoning=f"SAGE prediction for VIX={request.vix}, DOW={day_of_week}"
        )

        return {
            "success": True,
            "data": {
                "prediction": prediction_dict
            }
        }

    except Exception as e:
        logger.error(f"SAGE predict error: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e)
        }


def train_sage_model_internal(min_samples: int = 30, use_kronos: bool = True) -> dict:
    """
    Internal (non-async) SAGE training function for scheduler use.

    FIX (Jan 2026): Added for scheduled SAGE training - previously only
    available via async API endpoint.

    Returns:
        dict with success, training_method, samples_used, accuracy
    """
    try:
        from quant.ares_ml_advisor import get_advisor

        advisor = get_advisor()

        if use_kronos:
            # Train from KRONOS backtests
            from backtest.zero_dte_backtest import ZeroDTEBacktester

            backtester = ZeroDTEBacktester()
            results = backtester.get_recent_results(limit=500)

            if not results or len(results) < min_samples:
                return {
                    "success": False,
                    "message": f"Not enough KRONOS data. Have {len(results) if results else 0}, need {min_samples}",
                    "training_method": "kronos",
                    "samples_used": len(results) if results else 0
                }

            metrics = advisor.train_from_kronos(results, min_samples=min_samples)

            return {
                "success": True,
                "message": f"SAGE trained on {len(results)} KRONOS results",
                "training_method": "kronos",
                "samples_used": len(results),
                "accuracy": metrics.accuracy if metrics else None,
                "model_version": advisor.model_version
            }
        else:
            # Train from live outcomes
            metrics = advisor.retrain_from_outcomes(min_new_samples=min_samples)

            if not metrics:
                return {
                    "success": False,
                    "message": f"Not enough live outcomes. Need {min_samples}",
                    "training_method": "live",
                    "samples_used": 0
                }

            return {
                "success": True,
                "message": "SAGE trained on live outcomes",
                "training_method": "live",
                "samples_used": min_samples,
                "accuracy": metrics.accuracy if metrics else None,
                "model_version": advisor.model_version
            }

    except Exception as e:
        logger.error(f"SAGE internal train error: {e}")
        return {
            "success": False,
            "message": f"Training error: {str(e)}",
            "training_method": "unknown",
            "samples_used": 0
        }


@router.post("/sage/train")
async def train_sage(min_samples: int = 30, use_kronos: bool = True):
    """
    Train SAGE (ARES ML Advisor) model.

    Can train from:
    1. KRONOS backtest results (default)
    2. Live trade outcomes
    """
    try:
        from quant.ares_ml_advisor import get_advisor

        advisor = get_advisor()

        if use_kronos:
            # Train from KRONOS backtests
            from backtest.zero_dte_backtest import ZeroDTEBacktester

            backtester = ZeroDTEBacktester()
            results = backtester.get_recent_results(limit=500)

            if not results or len(results) < min_samples:
                return {
                    "success": False,
                    "error": f"Not enough KRONOS backtest data. Have {len(results) if results else 0}, need {min_samples}"
                }

            metrics = advisor.train_from_kronos(results, min_samples=min_samples)

            log_ml_action(
                action="SAGE_TRAIN_KRONOS",
                details={"samples": len(results), "min_samples": min_samples},
                ml_score=metrics.accuracy if metrics else None,
                recommendation="TRAINED" if metrics else "FAILED",
                reasoning="Trained SAGE from KRONOS backtest results"
            )

            return {
                "success": True,
                "message": f"SAGE trained on {len(results)} KRONOS backtest results",
                "data": {
                    "accuracy": metrics.accuracy if metrics else None,
                    "precision": metrics.precision if metrics else None,
                    "recall": metrics.recall if metrics else None,
                    "model_version": advisor.model_version
                }
            }
        else:
            # Train from live outcomes
            metrics = advisor.retrain_from_outcomes(min_new_samples=min_samples)

            if not metrics:
                return {
                    "success": False,
                    "error": f"Not enough live trade outcomes. Need {min_samples} minimum."
                }

            log_ml_action(
                action="SAGE_TRAIN_LIVE",
                details={"min_samples": min_samples},
                ml_score=metrics.accuracy if metrics else None,
                recommendation="TRAINED",
                reasoning="Trained SAGE from live trade outcomes"
            )

            return {
                "success": True,
                "message": "SAGE trained on live trade outcomes",
                "data": {
                    "accuracy": metrics.accuracy,
                    "precision": metrics.precision,
                    "model_version": advisor.model_version
                }
            }

    except Exception as e:
        logger.error(f"SAGE train error: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e)
        }


@router.get("/sage/feature-importance")
async def get_sage_feature_importance():
    """
    Get SAGE feature importance - which factors drive predictions.
    """
    try:
        from quant.ares_ml_advisor import get_advisor

        advisor = get_advisor()

        if not advisor.model:
            return {
                "success": True,
                "data": {
                    "model_trained": False,
                    "features": [],
                    "message": "Train SAGE to see feature importance"
                }
            }

        # Get feature importance from the model
        importance = {}
        if hasattr(advisor.model, 'feature_importances_'):
            feature_names = advisor.feature_columns if hasattr(advisor, 'feature_columns') else [
                'vix', 'vix_percentile_30d', 'vix_change_1d', 'day_of_week',
                'price_change_1d', 'expected_move_pct', 'win_rate_30d',
                'gex_normalized', 'gex_regime_positive', 'gex_distance_to_flip_pct', 'gex_between_walls'
            ]
            for i, imp in enumerate(advisor.model.feature_importances_):
                if i < len(feature_names):
                    importance[feature_names[i]] = float(imp)

        sorted_features = sorted(importance.items(), key=lambda x: x[1], reverse=True)
        total_importance = sum(importance.values()) if importance else 1

        features = []
        for rank, (name, imp) in enumerate(sorted_features, 1):
            features.append({
                "rank": rank,
                "name": name,
                "importance": round(imp, 4),
                "importance_pct": round(imp / total_importance * 100, 1),
                "meaning": _get_sage_feature_meaning(name)
            })

        return {
            "success": True,
            "data": {
                "model_trained": True,
                "features": features
            }
        }

    except Exception as e:
        logger.error(f"SAGE feature importance error: {e}")
        return {
            "success": False,
            "error": str(e)
        }


def _get_sage_feature_meaning(feature: str) -> str:
    """Get plain English meaning of SAGE features"""
    meanings = {
        'vix': 'Market fear gauge - higher VIX means more premium but more risk',
        'vix_percentile_30d': 'VIX compared to 30-day history - identifies elevated volatility',
        'vix_change_1d': 'VIX movement - rising VIX can signal stress',
        'day_of_week': 'Day of week - some days historically perform better',
        'price_change_1d': '1-day price movement - momentum signal',
        'expected_move_pct': 'Expected move % - options market implied range',
        'win_rate_30d': 'Recent 30-day win rate - momentum in strategy performance',
        'gex_normalized': 'Normalized GEX value - dealer positioning strength',
        'gex_regime_positive': 'GEX regime - positive = dealers buy dips (supportive)',
        'gex_distance_to_flip_pct': 'Distance to GEX flip point - proximity to regime change',
        'gex_between_walls': 'Price between put/call walls - ideal positioning zone'
    }
    return meanings.get(feature, 'Feature used by ML model')


@router.get("/bot-status")
async def get_bot_ml_status():
    """
    Get ML integration status for all trading bots.

    Shows which bots use SAGE as primary prediction source,
    their minimum win probability thresholds, and last prediction.
    """
    try:
        bots = [
            {"name": "ARES", "min_win_prob": 50, "description": "SPY Iron Condor"},
            {"name": "ATHENA", "min_win_prob": 48, "description": "Directional Spreads"},
            {"name": "ICARUS", "min_win_prob": 40, "description": "Aggressive Directional"},
            {"name": "PEGASUS", "min_win_prob": 50, "description": "SPX Iron Condor"},
            {"name": "TITAN", "min_win_prob": 40, "description": "Aggressive SPX IC"}
        ]

        bot_statuses = []

        for bot in bots:
            # Check for last prediction in logs
            last_prediction = None
            try:
                from database_adapter import get_connection
                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT ml_score, recommendation, timestamp
                    FROM ml_decision_logs
                    WHERE action LIKE %s
                    ORDER BY timestamp DESC
                    LIMIT 1
                ''', (f'%{bot["name"]}%',))
                row = cursor.fetchone()
                if row:
                    last_prediction = {
                        "win_probability": float(row[0]) if row[0] else None,
                        "advice": row[1],
                        "timestamp": row[2].isoformat() if row[2] else None
                    }
                conn.close()
            except:
                pass

            bot_statuses.append({
                "bot_name": bot["name"],
                "ml_enabled": True,
                "ml_source": "SAGE (ARES_ML_ADVISOR)",
                "min_win_probability": bot["min_win_prob"],
                "description": bot["description"],
                "last_prediction": last_prediction
            })

        return {
            "success": True,
            "data": {
                "bots": bot_statuses,
                "primary_source": "SAGE (ARES ML Advisor)",
                "backup_source": "Oracle (when ML unavailable)"
            }
        }

    except Exception as e:
        logger.error(f"Bot status error: {e}")
        return {
            "success": False,
            "error": str(e)
        }


# ============================================================================
# GEX PROBABILITY MODELS - For ARGUS/HYPERION
# ============================================================================

@router.get("/gex-models/status")
async def get_gex_models_status():
    """
    Get status of GEX Probability Models used by ARGUS and HYPERION.

    Returns:
        - is_trained: Whether models are loaded and ready
        - model_info: Metadata about the trained model
        - staleness_hours: Hours since last training
        - needs_retraining: Whether models need retraining
        - sub_models: Status of all 5 sub-models
    """
    try:
        from quant.gex_probability_models import GEXProbabilityModels
        from quant.model_persistence import get_model_info, MODEL_GEX_PROBABILITY

        models = GEXProbabilityModels()

        # Get model info from persistence layer
        model_info = get_model_info(MODEL_GEX_PROBABILITY)

        # Build response
        response = {
            "is_trained": models.is_trained,
            "model_info": model_info,
            "staleness_hours": models.get_model_staleness_hours(),
            "needs_retraining": models.needs_retraining(),
            "sub_models": {
                "direction": models._generator.direction_model.is_trained if models._generator else False,
                "flip_gravity": models._generator.flip_gravity_model.is_trained if models._generator else False,
                "magnet_attraction": models._generator.magnet_attraction_model.is_trained if models._generator else False,
                "volatility": models._generator.volatility_model.is_trained if models._generator else False,
                "pin_zone": models._generator.pin_zone_model.is_trained if models._generator else False
            },
            "usage": {
                "argus": "60% ML + 40% distance-weighted probability",
                "hyperion": "60% ML + 40% distance-weighted probability"
            }
        }

        return {"success": True, "data": response}

    except Exception as e:
        logger.error(f"GEX models status error: {e}")
        return {
            "success": False,
            "error": str(e),
            "data": {
                "is_trained": False,
                "model_info": None,
                "staleness_hours": None,
                "needs_retraining": True,
                "sub_models": {}
            }
        }


@router.post("/gex-models/train")
async def train_gex_models(
    symbols: List[str] = ["SPX", "SPY"],
    start_date: str = "2020-01-01",
    end_date: str = None
):
    """
    Trigger training of GEX Probability Models.

    This trains all 5 models:
    1. Direction Probability (UP/DOWN/FLAT)
    2. Flip Gravity (probability price moves toward flip point)
    3. Magnet Attraction (probability price reaches nearest magnet)
    4. Volatility Estimate (expected price range)
    5. Pin Zone Behavior (probability of staying between magnets)

    Args:
        symbols: List of symbols to train on (default: SPX, SPY)
        start_date: Training data start date
        end_date: Training data end date (default: today)

    Returns:
        Training results and metrics
    """
    try:
        from quant.gex_probability_models import GEXSignalGenerator

        generator = GEXSignalGenerator()

        # Train models
        logger.info(f"Starting GEX model training: symbols={symbols}, start={start_date}, end={end_date}")
        results = generator.train(
            symbols=symbols,
            start_date=start_date,
            end_date=end_date
        )

        # Save to database for persistence
        generator.save_to_db(
            metrics=results if isinstance(results, dict) else None,
            training_records=results.get('total_records') if isinstance(results, dict) else None
        )

        logger.info("GEX model training complete, saved to database")

        return {
            "success": True,
            "message": "GEX models trained and saved successfully",
            "data": {
                "training_results": results,
                "saved_to_db": True
            }
        }

    except Exception as e:
        logger.error(f"GEX model training error: {e}")
        import traceback
        return {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }


@router.post("/gex-models/predict")
async def predict_with_gex_models(
    spot_price: float,
    net_gamma: float,
    total_gamma: float,
    flip_point: float = None,
    vix: float = 20,
    magnets: List[dict] = None
):
    """
    Get prediction from GEX Probability Models.

    Args:
        spot_price: Current spot price
        net_gamma: Net gamma at spot
        total_gamma: Total absolute gamma
        flip_point: Gamma flip point (optional)
        vix: Current VIX level
        magnets: List of magnet strikes with gamma

    Returns:
        Combined prediction from all 5 models
    """
    try:
        from quant.gex_probability_models import GEXProbabilityModels

        models = GEXProbabilityModels()

        if not models.is_trained:
            return {
                "success": False,
                "error": "Models not trained. Run /api/ml/gex-models/train first."
            }

        # Build gamma structure
        gamma_structure = {
            'net_gamma': net_gamma,
            'total_gamma': total_gamma,
            'flip_point': flip_point or spot_price,
            'magnets': magnets or [],
            'vix': vix,
            'gamma_regime': 'POSITIVE' if net_gamma > 0 else 'NEGATIVE',
            'expected_move': spot_price * 0.01,
            'spot_price': spot_price
        }

        # Get combined prediction
        signal = models.predict_combined(spot_price, gamma_structure)

        if signal:
            return {
                "success": True,
                "data": {
                    "direction": signal.direction_prediction,
                    "direction_confidence": signal.direction_confidence,
                    "flip_gravity_prob": signal.flip_gravity_prob,
                    "magnet_attraction_prob": signal.magnet_attraction_prob,
                    "expected_volatility_pct": signal.expected_volatility_pct,
                    "pin_zone_prob": signal.pin_zone_prob,
                    "overall_conviction": signal.overall_conviction,
                    "trade_recommendation": signal.trade_recommendation
                }
            }
        else:
            return {
                "success": False,
                "error": "Prediction failed"
            }

    except Exception as e:
        logger.error(f"GEX model prediction error: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@router.get("/gex-models/data-status")
async def get_gex_training_data_status():
    """
    Check availability of GEX training data in database.

    Returns:
        - gex_structure_daily: Record count and date range (primary source)
        - gex_history: Record count and date range (fallback source)
        - vix_daily: Record count and date range
        - readiness: Whether enough data exists for training
    """
    try:
        from database_adapter import get_connection

        conn = get_connection()
        cursor = conn.cursor()

        # Helper to safely query table that might not exist
        def safe_count_query(table_name, date_col="trade_date"):
            try:
                if date_col == "timestamp":
                    cursor.execute(f"""
                        SELECT COUNT(DISTINCT DATE({date_col})), MIN(DATE({date_col})), MAX(DATE({date_col}))
                        FROM {table_name}
                    """)
                else:
                    cursor.execute(f"""
                        SELECT COUNT(*), MIN({date_col}), MAX({date_col})
                        FROM {table_name}
                    """)
                row = cursor.fetchone()
                return row[0] if row else 0, str(row[1]) if row and row[1] else None, str(row[2]) if row and row[2] else None
            except Exception as e:
                if "does not exist" in str(e).lower() or "relation" in str(e).lower():
                    conn.rollback()  # Clear the error state
                    return 0, None, None
                raise

        # Check gex_structure_daily (primary source)
        gex_count, gex_min, gex_max = safe_count_query("gex_structure_daily", "trade_date")

        # Check gex_history (fallback source) - count distinct days
        hist_days, hist_min, hist_max = safe_count_query("gex_history", "timestamp")

        # Also get total snapshots in gex_history
        try:
            cursor.execute("SELECT COUNT(*) FROM gex_history")
            hist_snapshots = cursor.fetchone()[0] or 0
        except Exception:
            conn.rollback()
            hist_snapshots = 0

        # Check vix_daily
        vix_count, vix_min, vix_max = safe_count_query("vix_daily", "trade_date")

        conn.close()

        # Determine readiness - can use either gex_structure_daily or gex_history
        min_records = 100
        usable_records = gex_count if gex_count > 0 else hist_days
        is_ready = usable_records >= min_records
        data_source = "gex_structure_daily" if gex_count > 0 else ("gex_history" if hist_days > 0 else "none")

        return {
            "success": True,
            "data": {
                "gex_structure_daily": {
                    "count": gex_count,
                    "date_range": f"{gex_min} to {gex_max}" if gex_min else "No data",
                    "has_data": gex_count > 0,
                    "is_primary": True
                },
                "gex_history": {
                    "unique_days": hist_days,
                    "total_snapshots": hist_snapshots,
                    "date_range": f"{hist_min} to {hist_max}" if hist_min else "No data",
                    "has_data": hist_days > 0,
                    "is_fallback": True,
                    "note": "Used when gex_structure_daily is empty"
                },
                "vix_daily": {
                    "count": vix_count,
                    "date_range": f"{vix_min} to {vix_max}" if vix_min else "No data",
                    "has_data": vix_count > 0
                },
                "readiness": {
                    "is_ready": is_ready,
                    "data_source": data_source,
                    "usable_records": usable_records,
                    "min_records_needed": min_records,
                    "message": f"Ready for training using {data_source}" if is_ready else f"Need at least {min_records} records (have {usable_records})"
                }
            }
        }

    except Exception as e:
        logger.error(f"GEX data status error: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@router.get("/gex-models/data-preview")
async def get_gex_training_data_preview(limit: int = 10):
    """
    Preview sample training data that will be used for ORION model training.

    Shows actual records from gex_structure_daily (primary) or gex_history (fallback)
    so users can verify data quality before training.

    Args:
        limit: Number of sample records to return (default: 10, max: 50)

    Returns:
        - source: Which table the data came from
        - sample_records: List of sample training records
        - columns: List of columns available
        - feature_columns: Columns that will be used as ML features
    """
    try:
        from database_adapter import get_connection

        limit = min(limit, 50)  # Cap at 50

        conn = get_connection()
        cursor = conn.cursor()

        # First check gex_structure_daily (primary source)
        cursor.execute("SELECT COUNT(*) FROM gex_structure_daily")
        gex_count = cursor.fetchone()[0] or 0

        sample_records = []
        source = None
        columns = []

        if gex_count > 0:
            source = "gex_structure_daily"
            cursor.execute(f"""
                SELECT
                    g.trade_date,
                    g.symbol,
                    g.spot_open,
                    g.spot_close,
                    g.net_gamma,
                    g.flip_point,
                    g.magnet_1_strike,
                    g.magnet_1_gamma,
                    g.call_wall,
                    g.put_wall,
                    g.gamma_imbalance_pct,
                    g.price_change_pct,
                    g.open_to_flip_distance_pct,
                    g.open_in_pin_zone,
                    v.vix_close
                FROM gex_structure_daily g
                LEFT JOIN vix_daily v ON g.trade_date = v.trade_date
                ORDER BY g.trade_date DESC
                LIMIT {limit}
            """)
            columns = [
                'trade_date', 'symbol', 'spot_open', 'spot_close', 'net_gamma',
                'flip_point', 'magnet_1_strike', 'magnet_1_gamma', 'call_wall',
                'put_wall', 'gamma_imbalance_pct', 'price_change_pct',
                'open_to_flip_distance_pct', 'open_in_pin_zone', 'vix_close'
            ]
            rows = cursor.fetchall()
            for row in rows:
                record = {}
                for i, col in enumerate(columns):
                    val = row[i]
                    if hasattr(val, 'isoformat'):
                        val = val.isoformat()
                    elif val is not None:
                        try:
                            val = float(val)
                        except (ValueError, TypeError):
                            val = str(val)
                    record[col] = val
                sample_records.append(record)
        else:
            # Fall back to gex_history
            cursor.execute("SELECT COUNT(*) FROM gex_history")
            hist_count = cursor.fetchone()[0] or 0

            if hist_count > 0:
                source = "gex_history"
                cursor.execute(f"""
                    SELECT DISTINCT ON (DATE(timestamp))
                        DATE(timestamp) as trade_date,
                        symbol,
                        spot_price,
                        net_gex,
                        flip_point,
                        call_wall,
                        put_wall,
                        total_call_gamma,
                        total_put_gamma,
                        timestamp
                    FROM gex_history
                    ORDER BY DATE(timestamp) DESC, timestamp DESC
                    LIMIT {limit}
                """)
                columns = [
                    'trade_date', 'symbol', 'spot_price', 'net_gex', 'flip_point',
                    'call_wall', 'put_wall', 'total_call_gamma', 'total_put_gamma', 'timestamp'
                ]
                rows = cursor.fetchall()
                for row in rows:
                    record = {}
                    for i, col in enumerate(columns):
                        val = row[i]
                        if hasattr(val, 'isoformat'):
                            val = val.isoformat()
                        elif val is not None:
                            try:
                                val = float(val)
                            except (ValueError, TypeError):
                                val = str(val)
                        record[col] = val
                    sample_records.append(record)
            else:
                source = "none"

        conn.close()

        # Define which columns are used as ML features
        feature_columns = [
            'net_gamma', 'flip_point', 'gamma_imbalance_pct', 'open_to_flip_distance_pct',
            'vix_close', 'magnet_1_gamma', 'call_wall', 'put_wall', 'open_in_pin_zone'
        ]

        return {
            "success": True,
            "data": {
                "source": source,
                "record_count": len(sample_records),
                "columns": columns,
                "feature_columns": feature_columns,
                "sample_records": sample_records,
                "note": "Most recent records shown. Training uses full date range."
            }
        }

    except Exception as e:
        logger.error(f"GEX data preview error: {e}")
        import traceback
        return {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }


@router.get("/gex-models/data-diagnostic")
async def diagnose_gex_training_data():
    """
    Comprehensive diagnostic for ORION training data availability.

    Checks all possible data sources and provides actionable recommendations.
    """
    try:
        from database_adapter import get_connection

        conn = get_connection()
        cursor = conn.cursor()

        diagnostics = {
            "gex_structure_daily": {"exists": False, "count": 0, "status": "empty"},
            "gex_history": {"exists": False, "count": 0, "status": "empty"},
            "vix_daily": {"exists": False, "count": 0, "status": "empty"},
            "gex_snapshots": {"exists": False, "count": 0, "status": "empty"},
        }

        # Check if tables exist and have data
        tables_to_check = [
            ("gex_structure_daily", "SELECT COUNT(*) FROM gex_structure_daily"),
            ("gex_history", "SELECT COUNT(*) FROM gex_history"),
            ("vix_daily", "SELECT COUNT(*) FROM vix_daily"),
            ("gex_snapshots", "SELECT COUNT(*) FROM gex_snapshots"),
        ]

        for table_name, query in tables_to_check:
            try:
                cursor.execute(query)
                count = cursor.fetchone()[0] or 0
                diagnostics[table_name] = {
                    "exists": True,
                    "count": count,
                    "status": "has_data" if count > 0 else "empty"
                }
            except Exception as e:
                if "does not exist" in str(e).lower():
                    diagnostics[table_name] = {
                        "exists": False,
                        "count": 0,
                        "status": "table_missing"
                    }
                else:
                    diagnostics[table_name] = {
                        "exists": False,
                        "count": 0,
                        "status": f"error: {str(e)}"
                    }

        conn.close()

        # Determine overall status and recommendations
        recommendations = []
        can_train = False

        gex_struct = diagnostics["gex_structure_daily"]
        gex_hist = diagnostics["gex_history"]
        vix = diagnostics["vix_daily"]

        if gex_struct["count"] >= 100:
            can_train = True
            recommendations.append({
                "priority": "info",
                "message": f"Primary source (gex_structure_daily) has {gex_struct['count']} records. Ready to train."
            })
        elif gex_hist["count"] >= 100:
            can_train = True
            recommendations.append({
                "priority": "info",
                "message": f"Fallback source (gex_history) has {gex_hist['count']} records. Can train using fallback."
            })
        else:
            # No training data - provide solutions
            if not gex_struct["exists"]:
                recommendations.append({
                    "priority": "high",
                    "message": "Table gex_structure_daily doesn't exist. Run: python scripts/populate_gex_structures.py --create-only"
                })
            elif gex_struct["count"] == 0:
                recommendations.append({
                    "priority": "high",
                    "message": "gex_structure_daily is empty. Run: python scripts/populate_gex_structures.py --symbol SPY --start 2024-01-01"
                })

            if not gex_hist["exists"]:
                recommendations.append({
                    "priority": "medium",
                    "message": "Table gex_history doesn't exist. The data collector creates this table automatically."
                })
            elif gex_hist["count"] == 0:
                recommendations.append({
                    "priority": "medium",
                    "message": "gex_history is empty. Start the data collector: python data/automated_data_collector.py"
                })
            elif gex_hist["count"] < 100:
                recommendations.append({
                    "priority": "medium",
                    "message": f"gex_history has only {gex_hist['count']} records. Need 100+ for training. Data collector runs every 5 min."
                })

            if vix["count"] == 0:
                recommendations.append({
                    "priority": "low",
                    "message": "VIX data missing. Run data collector or: python scripts/seed_all_tables.py --vix-only"
                })

        # Check data collector status
        try:
            cursor = get_connection().cursor()
            cursor.execute("""
                SELECT MAX(timestamp) FROM gex_history
            """)
            last_snapshot = cursor.fetchone()[0]
            if last_snapshot:
                from datetime import datetime, timezone
                age_hours = (datetime.now(timezone.utc) - last_snapshot.replace(tzinfo=timezone.utc)).total_seconds() / 3600
                if age_hours > 1:
                    recommendations.append({
                        "priority": "medium",
                        "message": f"Last GEX snapshot was {age_hours:.1f} hours ago. Data collector may not be running."
                    })
        except Exception:
            pass

        return {
            "success": True,
            "data": {
                "diagnostics": diagnostics,
                "can_train": can_train,
                "recommendations": recommendations,
                "summary": "Ready for training" if can_train else "Insufficient training data - see recommendations"
            }
        }

    except Exception as e:
        logger.error(f"GEX diagnostic error: {e}")
        import traceback
        return {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }


@router.post("/gex-models/populate-from-snapshots")
async def populate_gex_structure_from_snapshots():
    """
    Populate gex_structure_daily from gex_history snapshots.

    This converts intraday GEX snapshots into daily structure records
    that can be used for ML training.
    """
    try:
        from database_adapter import get_connection

        conn = get_connection()
        cursor = conn.cursor()

        # First ensure the table exists
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS gex_structure_daily (
                id SERIAL PRIMARY KEY,
                trade_date DATE NOT NULL,
                symbol VARCHAR(10) NOT NULL,
                spot_open NUMERIC(12,4),
                spot_close NUMERIC(12,4),
                spot_high NUMERIC(12,4),
                spot_low NUMERIC(12,4),
                net_gamma NUMERIC(20,2),
                total_call_gamma NUMERIC(20,2),
                total_put_gamma NUMERIC(20,2),
                flip_point NUMERIC(12,4),
                magnet_1_strike NUMERIC(12,2),
                magnet_1_gamma NUMERIC(20,2),
                magnet_2_strike NUMERIC(12,2),
                magnet_2_gamma NUMERIC(20,2),
                magnet_3_strike NUMERIC(12,2),
                magnet_3_gamma NUMERIC(20,2),
                call_wall NUMERIC(12,2),
                put_wall NUMERIC(12,2),
                gamma_above_spot NUMERIC(20,2),
                gamma_below_spot NUMERIC(20,2),
                gamma_imbalance_pct NUMERIC(10,4),
                num_magnets_above INTEGER,
                num_magnets_below INTEGER,
                nearest_magnet_strike NUMERIC(12,2),
                nearest_magnet_distance_pct NUMERIC(10,4),
                open_to_flip_distance_pct NUMERIC(10,4),
                open_in_pin_zone BOOLEAN,
                price_change_pct NUMERIC(10,4),
                price_range_pct NUMERIC(10,4),
                close_distance_to_flip_pct NUMERIC(10,4),
                close_distance_to_magnet1_pct NUMERIC(10,4),
                close_distance_to_magnet2_pct NUMERIC(10,4),
                UNIQUE(trade_date, symbol)
            )
        """)

        # Aggregate gex_history snapshots into daily records
        cursor.execute("""
            INSERT INTO gex_structure_daily (
                trade_date, symbol, spot_open, spot_close, spot_high, spot_low,
                net_gamma, total_call_gamma, total_put_gamma, flip_point,
                call_wall, put_wall, price_change_pct, price_range_pct,
                open_to_flip_distance_pct
            )
            SELECT
                DATE(timestamp) as trade_date,
                symbol,
                (array_agg(spot_price ORDER BY timestamp))[1] as spot_open,
                (array_agg(spot_price ORDER BY timestamp DESC))[1] as spot_close,
                MAX(spot_price) as spot_high,
                MIN(spot_price) as spot_low,
                AVG(net_gex) as net_gamma,
                AVG(total_call_gamma) as total_call_gamma,
                AVG(total_put_gamma) as total_put_gamma,
                AVG(flip_point) as flip_point,
                MAX(call_wall) as call_wall,
                MIN(put_wall) as put_wall,
                ((array_agg(spot_price ORDER BY timestamp DESC))[1] -
                 (array_agg(spot_price ORDER BY timestamp))[1]) /
                NULLIF((array_agg(spot_price ORDER BY timestamp))[1], 0) * 100 as price_change_pct,
                (MAX(spot_price) - MIN(spot_price)) /
                NULLIF(MIN(spot_price), 0) * 100 as price_range_pct,
                ((array_agg(spot_price ORDER BY timestamp))[1] - AVG(flip_point)) /
                NULLIF((array_agg(spot_price ORDER BY timestamp))[1], 0) * 100 as open_to_flip_distance_pct
            FROM gex_history
            WHERE symbol IS NOT NULL
            GROUP BY DATE(timestamp), symbol
            HAVING COUNT(*) >= 1
            ON CONFLICT (trade_date, symbol) DO UPDATE SET
                spot_close = EXCLUDED.spot_close,
                spot_high = EXCLUDED.spot_high,
                spot_low = EXCLUDED.spot_low,
                net_gamma = EXCLUDED.net_gamma,
                price_change_pct = EXCLUDED.price_change_pct,
                price_range_pct = EXCLUDED.price_range_pct
        """)

        rows_affected = cursor.rowcount
        conn.commit()

        # Get updated count
        cursor.execute("SELECT COUNT(*) FROM gex_structure_daily")
        total_count = cursor.fetchone()[0]

        conn.close()

        return {
            "success": True,
            "data": {
                "rows_inserted_or_updated": rows_affected,
                "total_records": total_count,
                "message": f"Populated {rows_affected} daily records from gex_history snapshots"
            }
        }

    except Exception as e:
        logger.error(f"Populate from snapshots error: {e}")
        import traceback
        return {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }


@router.post("/gex-models/populate-from-orat")
async def populate_gex_structure_from_orat(
    symbol: str = "SPY",
    start_date: str = "2023-01-01",
    limit: int = 500
):
    """
    Populate gex_structure_daily from ORAT historical options database.

    This reads from the ORAT_DATABASE_URL (historical options data)
    and writes to the main DATABASE_URL (AlphaGEX production).

    Args:
        symbol: SPY or SPX (default: SPY)
        start_date: Start date for data (default: 2023-01-01)
        limit: Max days to process (default: 500)
    """
    import os
    import psycopg2
    from urllib.parse import urlparse

    orat_url = os.getenv('ORAT_DATABASE_URL')
    main_url = os.getenv('DATABASE_URL')

    if not orat_url:
        return {
            "success": False,
            "error": "ORAT_DATABASE_URL not configured. Cannot populate from ORAT."
        }

    if not main_url:
        return {
            "success": False,
            "error": "DATABASE_URL not configured."
        }

    try:
        # Connect to ORAT database (read source)
        orat_parsed = urlparse(orat_url)
        orat_conn = psycopg2.connect(
            host=orat_parsed.hostname,
            port=orat_parsed.port or 5432,
            user=orat_parsed.username,
            password=orat_parsed.password,
            database=orat_parsed.path[1:],
            connect_timeout=30
        )

        # Connect to main database (write destination)
        from database_adapter import get_connection
        main_conn = get_connection()

        orat_cursor = orat_conn.cursor()
        main_cursor = main_conn.cursor()

        # Create table in main database if not exists
        main_cursor.execute("""
            CREATE TABLE IF NOT EXISTS gex_structure_daily (
                id SERIAL PRIMARY KEY,
                trade_date DATE NOT NULL,
                symbol VARCHAR(10) NOT NULL,
                spot_open NUMERIC(12,4),
                spot_close NUMERIC(12,4),
                spot_high NUMERIC(12,4),
                spot_low NUMERIC(12,4),
                net_gamma NUMERIC(20,2),
                total_call_gamma NUMERIC(20,2),
                total_put_gamma NUMERIC(20,2),
                flip_point NUMERIC(12,4),
                flip_point_2 NUMERIC(12,4),
                magnet_1_strike NUMERIC(12,2),
                magnet_1_gamma NUMERIC(20,2),
                magnet_2_strike NUMERIC(12,2),
                magnet_2_gamma NUMERIC(20,2),
                magnet_3_strike NUMERIC(12,2),
                magnet_3_gamma NUMERIC(20,2),
                call_wall NUMERIC(12,2),
                put_wall NUMERIC(12,2),
                gamma_above_spot NUMERIC(20,2),
                gamma_below_spot NUMERIC(20,2),
                gamma_imbalance_pct NUMERIC(10,4),
                num_magnets_above INTEGER,
                num_magnets_below INTEGER,
                nearest_magnet_strike NUMERIC(12,2),
                nearest_magnet_distance_pct NUMERIC(10,4),
                open_to_flip_distance_pct NUMERIC(10,4),
                open_in_pin_zone BOOLEAN,
                price_open NUMERIC(12,4),
                price_close NUMERIC(12,4),
                price_high NUMERIC(12,4),
                price_low NUMERIC(12,4),
                price_change_pct NUMERIC(10,4),
                price_range_pct NUMERIC(10,4),
                close_distance_to_flip_pct NUMERIC(10,4),
                close_distance_to_magnet1_pct NUMERIC(10,4),
                close_distance_to_magnet2_pct NUMERIC(10,4),
                close_distance_to_call_wall_pct NUMERIC(10,4),
                close_distance_to_put_wall_pct NUMERIC(10,4),
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(trade_date, symbol)
            )
        """)
        main_conn.commit()

        # Get available dates from ORAT
        ticker = 'SPX' if symbol == 'SPX' else 'SPY'
        orat_cursor.execute("""
            SELECT DISTINCT trade_date
            FROM orat_options_eod
            WHERE ticker = %s AND trade_date >= %s
            ORDER BY trade_date
            LIMIT %s
        """, (ticker, start_date, limit))

        available_dates = [row[0] for row in orat_cursor.fetchall()]

        if not available_dates:
            orat_conn.close()
            main_conn.close()
            return {
                "success": False,
                "error": f"No ORAT data found for {symbol} since {start_date}"
            }

        # Check which dates already exist in main database
        main_cursor.execute("""
            SELECT trade_date FROM gex_structure_daily
            WHERE symbol = %s AND trade_date >= %s
        """, (symbol, start_date))
        existing_dates = set(row[0] for row in main_cursor.fetchall())

        # Filter to only new dates
        new_dates = [d for d in available_dates if d not in existing_dates]

        if not new_dates:
            orat_conn.close()
            main_conn.close()
            return {
                "success": True,
                "data": {
                    "message": f"All {len(available_dates)} dates already populated",
                    "skipped": len(available_dates),
                    "inserted": 0
                }
            }

        # Process each new date
        inserted = 0
        errors = []

        for trade_date in new_dates:
            try:
                # Get options data from ORAT for this date
                orat_cursor.execute("""
                    SELECT strike, gamma, call_oi, put_oi, underlying_price
                    FROM orat_options_eod
                    WHERE ticker = %s AND trade_date = %s
                    AND dte <= 7 AND dte >= 0
                    AND gamma IS NOT NULL AND gamma > 0
                    ORDER BY strike
                """, (ticker, trade_date))

                rows = orat_cursor.fetchall()
                if not rows:
                    continue

                # Calculate GEX structure
                spot_price = float(rows[0][4])

                # Build strike data
                strike_data = {}
                for row in rows:
                    strike = float(row[0])
                    gamma = float(row[1])
                    call_oi = int(row[2]) if row[2] else 0
                    put_oi = int(row[3]) if row[3] else 0

                    call_gex = gamma * call_oi * 100 * (spot_price ** 2)
                    put_gex = gamma * put_oi * 100 * (spot_price ** 2)

                    if strike not in strike_data:
                        strike_data[strike] = {'call': 0, 'put': 0}
                    strike_data[strike]['call'] += call_gex
                    strike_data[strike]['put'] += put_gex

                # Calculate aggregates
                total_call = sum(d['call'] for d in strike_data.values())
                total_put = sum(d['put'] for d in strike_data.values())
                net_gamma = total_call - total_put

                # Find flip point
                flip_point = None
                sorted_strikes = sorted(strike_data.keys())
                for i in range(len(sorted_strikes) - 1):
                    s1, s2 = sorted_strikes[i], sorted_strikes[i+1]
                    net1 = strike_data[s1]['call'] - strike_data[s1]['put']
                    net2 = strike_data[s2]['call'] - strike_data[s2]['put']
                    if (net1 > 0 and net2 < 0) or (net1 < 0 and net2 > 0):
                        if net2 != net1:
                            flip_point = s1 + (s2 - s1) * abs(net1) / (abs(net1) + abs(net2))
                            break

                # Find magnets (top 3 by absolute net gamma)
                net_by_strike = [(s, d['call'] - d['put']) for s, d in strike_data.items()]
                magnets = sorted(net_by_strike, key=lambda x: abs(x[1]), reverse=True)[:3]

                # Insert into main database
                main_cursor.execute("""
                    INSERT INTO gex_structure_daily (
                        trade_date, symbol, spot_open, spot_close,
                        net_gamma, total_call_gamma, total_put_gamma,
                        flip_point,
                        magnet_1_strike, magnet_1_gamma,
                        magnet_2_strike, magnet_2_gamma,
                        magnet_3_strike, magnet_3_gamma,
                        price_open, price_close
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    ON CONFLICT (trade_date, symbol) DO UPDATE SET
                        net_gamma = EXCLUDED.net_gamma,
                        total_call_gamma = EXCLUDED.total_call_gamma,
                        total_put_gamma = EXCLUDED.total_put_gamma,
                        flip_point = EXCLUDED.flip_point
                """, (
                    trade_date, symbol, spot_price, spot_price,
                    net_gamma, total_call, total_put,
                    flip_point,
                    magnets[0][0] if len(magnets) > 0 else None,
                    magnets[0][1] if len(magnets) > 0 else None,
                    magnets[1][0] if len(magnets) > 1 else None,
                    magnets[1][1] if len(magnets) > 1 else None,
                    magnets[2][0] if len(magnets) > 2 else None,
                    magnets[2][1] if len(magnets) > 2 else None,
                    spot_price, spot_price
                ))
                inserted += 1

                # Commit every 50 rows
                if inserted % 50 == 0:
                    main_conn.commit()

            except Exception as e:
                if len(errors) < 5:
                    errors.append(f"{trade_date}: {str(e)[:100]}")

        main_conn.commit()

        # Get final count
        main_cursor.execute("SELECT COUNT(*) FROM gex_structure_daily WHERE symbol = %s", (symbol,))
        total_count = main_cursor.fetchone()[0]

        orat_conn.close()
        main_conn.close()

        return {
            "success": True,
            "data": {
                "inserted": inserted,
                "skipped": len(available_dates) - len(new_dates),
                "total_records": total_count,
                "errors": errors if errors else None,
                "message": f"Populated {inserted} days from ORAT for {symbol}"
            }
        }

    except Exception as e:
        logger.error(f"ORAT populate error: {e}")
        import traceback
        return {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }


# ============================================================================
# ML MODEL METADATA ENDPOINTS
# ============================================================================

@router.get("/model-metadata")
async def get_all_model_metadata():
    """
    Get metadata for all ML models (active versions only).

    Returns information about currently deployed models:
    - SAGE: Trade outcome predictor
    - ORACLE: Strategy advisor
    - GEX_PROBABILITY: GEX probability models (ORION)
    - GEX_DIRECTIONAL: GEX directional predictor

    Part of the Complete Loop: Database → Backend API → Frontend
    """
    try:
        conn = get_connection()
        if not conn:
            return {
                "success": False,
                "error": "Database connection unavailable",
                "data": []
            }

        cursor = conn.cursor()

        # Ensure table exists
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ml_model_metadata (
                id SERIAL PRIMARY KEY,
                model_name VARCHAR(50) NOT NULL,
                model_version VARCHAR(50),
                trained_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                training_samples INTEGER,
                accuracy DECIMAL(5,4),
                feature_importance JSONB,
                hyperparameters JSONB,
                model_type VARCHAR(50),
                is_active BOOLEAN DEFAULT TRUE,
                deployed_at TIMESTAMPTZ DEFAULT NOW(),
                created_at TIMESTAMPTZ DEFAULT NOW(),
                notes TEXT
            )
        """)
        conn.commit()

        # Get all active models
        cursor.execute("""
            SELECT
                model_name,
                model_version,
                trained_at,
                training_samples,
                accuracy,
                feature_importance,
                hyperparameters,
                model_type,
                deployed_at,
                EXTRACT(EPOCH FROM (NOW() - trained_at)) / 3600 as hours_since_training
            FROM ml_model_metadata
            WHERE is_active = TRUE
            ORDER BY model_name
        """)

        models = []
        for row in cursor.fetchall():
            hours_since = row[9] if row[9] else 0
            is_stale = hours_since > 168  # More than 7 days

            models.append({
                "model_name": row[0],
                "model_version": row[1],
                "trained_at": row[2].isoformat() if row[2] else None,
                "training_samples": row[3],
                "accuracy": float(row[4]) if row[4] else None,
                "feature_importance": row[5],
                "hyperparameters": row[6],
                "model_type": row[7],
                "deployed_at": row[8].isoformat() if row[8] else None,
                "hours_since_training": round(hours_since, 1),
                "is_stale": is_stale,
                "status": "stale" if is_stale else ("not_trained" if row[1] == 'not_trained' else "fresh")
            })

        cursor.close()
        conn.close()

        return {
            "success": True,
            "data": models,
            "count": len(models),
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Failed to get model metadata: {e}")
        return {
            "success": False,
            "error": str(e),
            "data": []
        }


@router.get("/model-metadata/{model_name}")
async def get_model_metadata(model_name: str):
    """
    Get metadata for a specific ML model.

    Args:
        model_name: One of SAGE, ORACLE, GEX_PROBABILITY, GEX_DIRECTIONAL

    Returns detailed model information including feature importance
    and hyperparameters if available.
    """
    try:
        conn = get_connection()
        if not conn:
            raise HTTPException(status_code=503, detail="Database unavailable")

        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                model_name,
                model_version,
                trained_at,
                training_samples,
                accuracy,
                feature_importance,
                hyperparameters,
                model_type,
                deployed_at,
                notes,
                EXTRACT(EPOCH FROM (NOW() - trained_at)) / 3600 as hours_since_training
            FROM ml_model_metadata
            WHERE model_name = %s AND is_active = TRUE
        """, (model_name.upper(),))

        row = cursor.fetchone()
        cursor.close()
        conn.close()

        if not row:
            raise HTTPException(
                status_code=404,
                detail=f"Model {model_name} not found or not trained"
            )

        hours_since = row[10] if row[10] else 0
        is_stale = hours_since > 168

        return {
            "success": True,
            "data": {
                "model_name": row[0],
                "model_version": row[1],
                "trained_at": row[2].isoformat() if row[2] else None,
                "training_samples": row[3],
                "accuracy": float(row[4]) if row[4] else None,
                "feature_importance": row[5],
                "hyperparameters": row[6],
                "model_type": row[7],
                "deployed_at": row[8].isoformat() if row[8] else None,
                "notes": row[9],
                "hours_since_training": round(hours_since, 1),
                "is_stale": is_stale,
                "freshness_status": "stale" if is_stale else "fresh"
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get model {model_name} metadata: {e}")
        raise HTTPException(status_code=500, detail=str(e))
