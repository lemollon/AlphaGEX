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
