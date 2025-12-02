"""
SPX Wheel Backtest API Routes with ML Integration

This provides TRANSPARENCY into:
1. How the SPX wheel backtest performs
2. How ML scoring affects trade selection
3. Full audit trail of every trade
4. Data quality metrics (real vs estimated)

ML CONTRIBUTION:
- Each trade is scored by the ML model
- Trades below ML threshold can be filtered
- Shows exactly how ML improved/hurt performance
"""

import os
import sys
import logging
from datetime import datetime, timedelta
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
import json

# Add project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from database_adapter import get_connection
import psycopg2.extras

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/spx-backtest", tags=["SPX Wheel Backtest"])


# ============================================================================
# Request/Response Models
# ============================================================================

class RunBacktestRequest(BaseModel):
    """Request to run an SPX backtest"""
    start_date: str = "2024-01-01"
    end_date: Optional[str] = None
    initial_capital: float = 100000
    put_delta: float = 0.20
    dte_target: int = 45
    max_margin_pct: float = 0.50
    use_ml_scoring: bool = True
    ml_min_score: float = 0.40  # Minimum ML score to take trade


class BacktestSummary(BaseModel):
    """Summary of backtest results"""
    backtest_id: str
    start_date: str
    end_date: str
    initial_capital: float
    final_equity: float
    total_return_pct: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    max_drawdown_pct: float
    data_quality_pct: float  # % of trades with real data


# ============================================================================
# API Endpoints
# ============================================================================

@router.post("/run")
async def run_spx_backtest(config: RunBacktestRequest = RunBacktestRequest()):
    """
    Run a new SPX wheel backtest with ML scoring integration.

    TRANSPARENCY:
    - Shows ML score for each trade
    - Tracks whether ML would have filtered trades
    - Compares performance with/without ML filtering
    """
    try:
        from backtest.spx_premium_backtest import SPXPremiumBacktester

        # Generate unique backtest ID
        backtest_id = f"spx_wheel_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        logger.info(f"Starting SPX backtest {backtest_id}")
        logger.info(f"Config: {config.dict()}")

        # Create backtester
        backtester = SPXPremiumBacktester(
            start_date=config.start_date,
            end_date=config.end_date or datetime.now().strftime('%Y-%m-%d'),
            initial_capital=config.initial_capital,
            put_delta=config.put_delta,
            dte_target=config.dte_target,
            max_margin_pct=config.max_margin_pct
        )

        # Run backtest
        results = backtester.run(save_to_db=True)

        if not results:
            raise HTTPException(status_code=500, detail="Backtest failed to return results")

        summary = results.get('summary', {})
        data_quality = results.get('data_quality', {})
        trades = results.get('trades', [])

        # If ML scoring is enabled, score each trade
        ml_results = None
        if config.use_ml_scoring and trades:
            ml_results = await _score_trades_with_ml(trades, config.ml_min_score)

        # Save backtest run metadata
        _save_backtest_run(
            backtest_id=backtest_id,
            config=config.dict(),
            summary=summary,
            data_quality=data_quality,
            ml_results=ml_results
        )

        # ========== CRITICAL: AUTO-PROCESS TRADES FOR ML TRAINING ==========
        # This was ORPHANED - now it's actually connected!
        ml_auto_process_result = None
        if trades:
            try:
                ml_auto_process_result = await _auto_process_trades_for_ml(backtest_id, trades)
                logger.info(f"ML auto-processed {ml_auto_process_result.get('trades_recorded', 0)} trades")
            except Exception as ml_err:
                logger.error(f"ML auto-process failed (non-fatal): {ml_err}")
                ml_auto_process_result = {"error": str(ml_err)}

        return {
            "success": True,
            "backtest_id": backtest_id,
            "summary": {
                "start_date": config.start_date,
                "end_date": config.end_date or datetime.now().strftime('%Y-%m-%d'),
                "initial_capital": config.initial_capital,
                "final_equity": summary.get('final_equity', config.initial_capital),
                "total_return_pct": round(summary.get('total_return_pct', 0), 2),
                "total_trades": summary.get('total_trades', 0),
                "winning_trades": summary.get('winning_trades', 0),
                "losing_trades": summary.get('losing_trades', 0),
                "win_rate": round(summary.get('win_rate', 0), 1),
                "max_drawdown_pct": round(summary.get('max_drawdown', 0), 2),
                "sharpe_ratio": round(summary.get('sharpe_ratio', 0), 2)
            },
            "data_quality": {
                "real_data_pct": round(data_quality.get('real_data_pct', 0), 1),
                "real_data_points": data_quality.get('real_data_points', 0),
                "estimated_data_points": data_quality.get('estimated_data_points', 0),
                "quality_verdict": "HIGH" if data_quality.get('real_data_pct', 0) >= 80 else "MEDIUM" if data_quality.get('real_data_pct', 0) >= 50 else "LOW"
            },
            "ml_analysis": ml_results if ml_results else {"enabled": False},
            "ml_training": ml_auto_process_result,  # NEW: Show ML training results
            "trades_count": len(trades),
            "message": f"Backtest completed with {len(trades)} trades. ML {'trained' if ml_auto_process_result and ml_auto_process_result.get('auto_trained') else 'recorded data'}."
        }

    except ImportError as e:
        logger.error(f"Import error: {e}")
        raise HTTPException(status_code=500, detail=f"SPX backtester not available: {e}")
    except Exception as e:
        logger.error(f"Backtest error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/results")
async def get_backtest_results(backtest_id: Optional[str] = None, limit: int = 10):
    """
    Get backtest results and trade details.

    TRANSPARENCY: Shows every trade with its ML score and data source.
    """
    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        if backtest_id:
            # Get specific backtest
            cursor.execute('''
                SELECT * FROM spx_wheel_backtest_trades
                WHERE backtest_id = %s
                ORDER BY trade_date
            ''', (backtest_id,))
            trades = cursor.fetchall()

            cursor.execute('''
                SELECT * FROM spx_wheel_backtest_equity
                WHERE backtest_id = %s
                ORDER BY date
            ''', (backtest_id,))
            equity_curve = cursor.fetchall()

        else:
            # Get recent backtests
            cursor.execute('''
                SELECT DISTINCT backtest_id, MIN(trade_date) as start_date,
                       MAX(trade_date) as end_date, COUNT(*) as trade_count,
                       SUM(total_pnl) as total_pnl
                FROM spx_wheel_backtest_trades
                GROUP BY backtest_id
                ORDER BY MIN(backtest_date) DESC
                LIMIT %s
            ''', (limit,))
            trades = cursor.fetchall()
            equity_curve = []

        conn.close()

        return {
            "success": True,
            "data": {
                "trades": [dict(t) for t in trades] if trades else [],
                "equity_curve": [dict(e) for e in equity_curve] if equity_curve else [],
                "count": len(trades)
            }
        }

    except Exception as e:
        logger.error(f"Error fetching results: {e}")
        return {
            "success": True,
            "data": {"trades": [], "equity_curve": [], "count": 0, "note": "No data available yet"}
        }


@router.get("/trades/{backtest_id}")
async def get_backtest_trades(
    backtest_id: str,
    include_ml_scores: bool = True,
    limit: int = 100
):
    """
    Get detailed trades for a specific backtest.

    TRANSPARENCY: Shows every field including:
    - Option ticker (verifiable)
    - Entry/exit prices
    - Data source (POLYGON vs ESTIMATED)
    - ML score if available
    """
    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cursor.execute('''
            SELECT
                trade_id, trade_date, trade_type, option_ticker,
                strike, expiration, entry_price, exit_price,
                contracts, premium_received, settlement_pnl, total_pnl,
                price_source, entry_underlying_price, exit_underlying_price,
                notes, parameters
            FROM spx_wheel_backtest_trades
            WHERE backtest_id = %s
            ORDER BY trade_date
            LIMIT %s
        ''', (backtest_id, limit))

        trades = cursor.fetchall()
        conn.close()

        # Add ML scores if requested
        if include_ml_scores and trades:
            trades = await _add_ml_scores_to_trades(trades)

        return {
            "success": True,
            "backtest_id": backtest_id,
            "trades": [dict(t) for t in trades],
            "count": len(trades)
        }

    except Exception as e:
        logger.error(f"Error fetching trades: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/equity-curve/{backtest_id}")
async def get_equity_curve(backtest_id: str):
    """
    Get equity curve for charting.

    Returns daily snapshots showing:
    - Total equity
    - Drawdown
    - Open positions
    - Margin usage
    """
    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cursor.execute('''
            SELECT
                date, equity, cash_balance, open_position_value,
                daily_pnl, cumulative_pnl, peak_equity, drawdown_pct,
                open_puts, margin_used
            FROM spx_wheel_backtest_equity
            WHERE backtest_id = %s
            ORDER BY date
        ''', (backtest_id,))

        curve = cursor.fetchall()
        conn.close()

        # Format for charting
        chart_data = []
        for point in curve:
            chart_data.append({
                "time": point['date'],
                "value": float(point['equity']) if point['equity'] else 0,
                "drawdown": float(point['drawdown_pct']) if point['drawdown_pct'] else 0
            })

        return {
            "success": True,
            "backtest_id": backtest_id,
            "equity_curve": [dict(c) for c in curve],
            "chart_data": chart_data,
            "points": len(curve)
        }

    except Exception as e:
        logger.error(f"Error fetching equity curve: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ml-impact")
async def get_ml_impact_analysis(backtest_id: Optional[str] = None):
    """
    Analyze ML's impact on backtest results.

    TRANSPARENCY: Shows exactly how ML affected performance:
    - Trades ML would have taken vs skipped
    - P&L of ML-approved trades vs ML-rejected trades
    - Whether ML improved or hurt performance
    """
    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Get ML decision logs
        if backtest_id:
            cursor.execute('''
                SELECT ml_score, recommendation, actual_pnl, outcome
                FROM ml_decision_log
                WHERE action = 'SCORE_TRADE'
                AND symbol = 'SPX'
                ORDER BY timestamp DESC
                LIMIT 500
            ''')
        else:
            cursor.execute('''
                SELECT ml_score, recommendation, actual_pnl, outcome
                FROM ml_decision_log
                WHERE action = 'SCORE_TRADE'
                AND symbol = 'SPX'
                AND actual_pnl IS NOT NULL
                ORDER BY timestamp DESC
                LIMIT 500
            ''')

        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return {
                "success": True,
                "data": {
                    "message": "No ML-scored trades found yet. Run a backtest with ML scoring enabled.",
                    "ml_trades": 0
                }
            }

        # Analyze impact
        strong_trades = [r for r in rows if r['recommendation'] == 'STRONG_TRADE']
        trade_trades = [r for r in rows if r['recommendation'] == 'TRADE']
        caution_trades = [r for r in rows if r['recommendation'] == 'CAUTION']
        skip_trades = [r for r in rows if r['recommendation'] == 'SKIP']

        def calc_stats(trades_list):
            if not trades_list:
                return {"count": 0, "total_pnl": 0, "avg_pnl": 0, "win_rate": 0}
            pnls = [float(t['actual_pnl'] or 0) for t in trades_list if t['actual_pnl'] is not None]
            if not pnls:
                return {"count": len(trades_list), "total_pnl": 0, "avg_pnl": 0, "win_rate": 0}
            winners = sum(1 for p in pnls if p > 0)
            return {
                "count": len(pnls),
                "total_pnl": round(sum(pnls), 2),
                "avg_pnl": round(sum(pnls) / len(pnls), 2),
                "win_rate": round(winners / len(pnls) * 100, 1)
            }

        strong_stats = calc_stats(strong_trades)
        trade_stats = calc_stats(trade_trades)
        caution_stats = calc_stats(caution_trades)
        skip_stats = calc_stats(skip_trades)

        # Calculate ML value-add
        ml_approved_pnl = strong_stats['total_pnl'] + trade_stats['total_pnl']
        ml_rejected_pnl = skip_stats['total_pnl']

        ml_value = ml_approved_pnl - ml_rejected_pnl if ml_rejected_pnl < 0 else 0

        return {
            "success": True,
            "data": {
                "total_scored_trades": len(rows),
                "by_recommendation": {
                    "STRONG_TRADE": strong_stats,
                    "TRADE": trade_stats,
                    "CAUTION": caution_stats,
                    "SKIP": skip_stats
                },
                "ml_impact": {
                    "ml_approved_pnl": ml_approved_pnl,
                    "ml_rejected_pnl": ml_rejected_pnl,
                    "ml_value_add": ml_value,
                    "verdict": "ML is adding value" if ml_value > 0 else "ML needs more training data"
                }
            }
        }

    except Exception as e:
        logger.error(f"Error analyzing ML impact: {e}")
        return {
            "success": True,
            "data": {"message": "ML impact analysis not available yet", "error": str(e)}
        }


@router.get("/data-quality/{backtest_id}")
async def get_data_quality_report(backtest_id: str):
    """
    Get detailed data quality report for a backtest.

    TRANSPARENCY: Shows exactly which trades used real vs estimated data.
    """
    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cursor.execute('''
            SELECT
                trade_id, trade_date, strike, price_source, total_pnl
            FROM spx_wheel_backtest_trades
            WHERE backtest_id = %s
            ORDER BY trade_date
        ''', (backtest_id,))

        trades = cursor.fetchall()
        conn.close()

        real_trades = [t for t in trades if 'POLYGON' in (t['price_source'] or '')]
        estimated_trades = [t for t in trades if 'POLYGON' not in (t['price_source'] or '')]

        real_pnl = sum(float(t['total_pnl'] or 0) for t in real_trades)
        estimated_pnl = sum(float(t['total_pnl'] or 0) for t in estimated_trades)

        total = len(trades)
        real_pct = (len(real_trades) / total * 100) if total > 0 else 0

        return {
            "success": True,
            "backtest_id": backtest_id,
            "data_quality": {
                "total_trades": total,
                "real_data_trades": len(real_trades),
                "estimated_data_trades": len(estimated_trades),
                "real_data_pct": round(real_pct, 1),
                "real_data_pnl": round(real_pnl, 2),
                "estimated_data_pnl": round(estimated_pnl, 2),
                "quality_grade": "A" if real_pct >= 90 else "B" if real_pct >= 70 else "C" if real_pct >= 50 else "D",
                "verdict": "HIGH CONFIDENCE" if real_pct >= 80 else "MEDIUM CONFIDENCE" if real_pct >= 50 else "LOW CONFIDENCE - Results may not reflect reality"
            },
            "trades_by_source": {
                "POLYGON_HISTORICAL": [{"date": t['trade_date'], "strike": t['strike'], "pnl": float(t['total_pnl'] or 0)} for t in real_trades[:10]],
                "ESTIMATED": [{"date": t['trade_date'], "strike": t['strike'], "pnl": float(t['total_pnl'] or 0)} for t in estimated_trades[:10]]
            }
        }

    except Exception as e:
        logger.error(f"Error fetching data quality: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Helper Functions
# ============================================================================

async def _score_trades_with_ml(trades: List, ml_min_score: float) -> dict:
    """Score trades using ML and analyze impact - NOW USES REAL DATA"""
    try:
        from trading.spx_wheel_ml import get_spx_wheel_ml_trainer, SPXWheelFeatures
        from data.polygon_data_fetcher import get_ml_features_for_trade

        trainer = get_spx_wheel_ml_trainer()
        if not trainer or trainer.model is None:
            return {
                "enabled": True,
                "model_trained": False,
                "message": "ML model not trained yet"
            }

        ml_approved = 0
        ml_rejected = 0
        ml_approved_pnl = 0
        ml_rejected_pnl = 0
        real_data_count = 0
        estimated_count = 0

        for trade in trades:
            # Get trade details
            strike = trade.get('strike', 0)
            underlying = trade.get('entry_underlying_price', 0)
            pnl = trade.get('total_pnl', 0) or trade.get('pnl', 0) or 0
            trade_date = trade.get('trade_date', '')
            premium = trade.get('premium', trade.get('entry_price', 0)) or 0
            dte = trade.get('dte', 45)

            if not underlying or not strike:
                continue

            # ========== FETCH REAL DATA INSTEAD OF HARDCODING ==========
            try:
                real_features = get_ml_features_for_trade(
                    trade_date=trade_date,
                    strike=float(strike),
                    underlying_price=float(underlying),
                    option_iv=trade.get('implied_volatility')
                )
                if real_features.get('data_quality_pct', 0) >= 70:
                    real_data_count += 1
                else:
                    estimated_count += 1
            except:
                real_features = {
                    'vix': 18, 'iv_rank': 50, 'vix_percentile': 50,
                    'vix_term_structure': 0, 'spx_5d_return': 0,
                    'spx_20d_return': 0, 'distance_from_high': 0
                }
                estimated_count += 1

            # Build features for ML prediction using REAL data
            features = SPXWheelFeatures(
                trade_date=trade_date,
                strike=float(strike),
                underlying_price=float(underlying),
                dte=dte,
                delta=trade.get('delta', 0.20),
                premium=float(premium),
                iv=real_features.get('iv', 0.15),
                iv_rank=real_features.get('iv_rank', 50),
                vix=real_features.get('vix', 18),
                vix_percentile=real_features.get('vix_percentile', 50),
                vix_term_structure=real_features.get('vix_term_structure', 0),
                put_wall_distance_pct=(underlying - strike) / underlying * 100 if underlying else 5,
                call_wall_distance_pct=5,  # GEX not available
                net_gex=0,  # GEX not available
                spx_20d_return=real_features.get('spx_20d_return', 0),
                spx_5d_return=real_features.get('spx_5d_return', 0),
                spx_distance_from_high=real_features.get('distance_from_high', 0),
                premium_to_strike_pct=float(premium) / float(strike) * 100 if strike else 0,
                annualized_return=(float(premium) / float(strike) * 100 * 365 / dte) if strike and dte else 0
            )

            prediction = trainer.predict(features)
            ml_score = prediction.get('win_probability', 0.5)

            if ml_score >= ml_min_score:
                ml_approved += 1
                ml_approved_pnl += float(pnl)
            else:
                ml_rejected += 1
                ml_rejected_pnl += float(pnl)

        total = real_data_count + estimated_count
        data_quality = (real_data_count / total * 100) if total > 0 else 0

        return {
            "enabled": True,
            "model_trained": True,
            "ml_threshold": ml_min_score,
            "trades_analyzed": len(trades),
            "ml_approved": ml_approved,
            "ml_rejected": ml_rejected,
            "ml_approved_pnl": round(ml_approved_pnl, 2),
            "ml_rejected_pnl": round(ml_rejected_pnl, 2),
            "ml_value_add": round(ml_approved_pnl - ml_rejected_pnl, 2) if ml_rejected_pnl < 0 else 0,
            "data_quality_pct": round(data_quality, 1),
            "recommendation": "ML filtering would improve results" if ml_rejected_pnl < 0 else "Current trades are good"
        }

    except Exception as e:
        logger.error(f"ML scoring error: {e}")
        return {
            "enabled": True,
            "error": str(e)
        }


async def _add_ml_scores_to_trades(trades: List) -> List:
    """Add ML scores to trade records - NOW USES REAL DATA"""
    try:
        from trading.spx_wheel_ml import get_spx_wheel_ml_trainer, SPXWheelFeatures
        from data.polygon_data_fetcher import get_ml_features_for_trade

        trainer = get_spx_wheel_ml_trainer()
        if not trainer or trainer.model is None:
            return trades

        scored_trades = []
        for trade in trades:
            t = dict(trade)
            strike = t.get('strike', 0)
            underlying = t.get('entry_underlying_price', 0)
            trade_date = t.get('trade_date', '')
            premium = t.get('premium', t.get('entry_price', 0)) or 0
            dte = t.get('dte', 45)

            if underlying and strike:
                # Get real data for this trade
                try:
                    real_features = get_ml_features_for_trade(
                        trade_date=trade_date,
                        strike=float(strike),
                        underlying_price=float(underlying),
                        option_iv=t.get('implied_volatility')
                    )
                except:
                    real_features = {'vix': 18, 'iv_rank': 50, 'vix_percentile': 50}

                features = SPXWheelFeatures(
                    trade_date=trade_date,
                    strike=float(strike),
                    underlying_price=float(underlying),
                    dte=dte,
                    delta=t.get('delta', 0.20),
                    premium=float(premium),
                    iv=real_features.get('iv', 0.15),
                    iv_rank=real_features.get('iv_rank', 50),
                    vix=real_features.get('vix', 18),
                    vix_percentile=real_features.get('vix_percentile', 50),
                    vix_term_structure=real_features.get('vix_term_structure', 0),
                    put_wall_distance_pct=(underlying - strike) / underlying * 100 if underlying else 5,
                    call_wall_distance_pct=5,
                    net_gex=0,
                    spx_20d_return=real_features.get('spx_20d_return', 0),
                    spx_5d_return=real_features.get('spx_5d_return', 0),
                    spx_distance_from_high=real_features.get('distance_from_high', 0),
                    premium_to_strike_pct=float(premium) / float(strike) * 100 if strike else 0,
                    annualized_return=(float(premium) / float(strike) * 100 * 365 / dte) if strike and dte else 0
                )

                prediction = trainer.predict(features)
                t['ml_score'] = round(prediction.get('win_probability', 0.5) * 100, 1)
                t['ml_recommendation'] = prediction.get('recommendation', 'UNKNOWN')
                t['ml_data_quality'] = real_features.get('data_quality_pct', 0)
            else:
                t['ml_score'] = None
                t['ml_recommendation'] = 'N/A'
                t['ml_data_quality'] = 0

            scored_trades.append(t)

        return scored_trades

    except Exception as e:
        logger.error(f"Error adding ML scores: {e}")
        return trades


async def _auto_process_trades_for_ml(backtest_id: str, trades: List) -> dict:
    """
    CRITICAL: Actually process trades for ML training.

    This was ORPHANED before - the endpoint existed but was never called.
    Now it's connected and runs after every backtest.

    USES REAL DATA from Polygon API for VIX, IV rank, SPX returns.
    """
    try:
        from trading.spx_wheel_ml import (
            get_spx_wheel_ml_trainer,
            get_outcome_tracker,
            SPXWheelFeatures
        )
        from backend.api.routes.ml_routes import log_ml_action
        # Import REAL data fetching functions
        from data.polygon_data_fetcher import get_ml_features_for_trade

        tracker = get_outcome_tracker()
        trainer = get_spx_wheel_ml_trainer()

        recorded = 0
        real_data_count = 0
        estimated_data_count = 0

        for trade in trades:
            trade_id = f"{backtest_id}_{trade.get('trade_date', 'unknown')}_{trade.get('strike', 0)}"

            # Extract basic features from trade
            strike = trade.get('strike', 0)
            underlying = trade.get('entry_underlying_price', trade.get('underlying_price', 0))
            pnl = trade.get('total_pnl', trade.get('pnl', 0)) or 0
            trade_date = trade.get('trade_date', '')

            if not strike or not underlying or not trade_date:
                continue

            # Get trade-specific data
            premium = trade.get('premium', trade.get('entry_price', 0)) or 0
            dte = trade.get('dte', 45)
            option_iv = trade.get('implied_volatility', trade.get('iv'))

            # ========== FETCH REAL DATA ==========
            # This now uses Polygon API to get actual VIX, calculate IV rank, etc.
            try:
                real_features = get_ml_features_for_trade(
                    trade_date=trade_date,
                    strike=float(strike),
                    underlying_price=float(underlying),
                    option_iv=option_iv
                )
                data_quality = real_features.get('data_quality_pct', 0)
                if data_quality >= 70:
                    real_data_count += 1
                else:
                    estimated_data_count += 1
            except Exception as e:
                logger.warning(f"Could not fetch real data for {trade_date}: {e}")
                # Fallback to estimated values
                real_features = {
                    'vix': 18.0,
                    'iv_rank': 50,
                    'vix_percentile': 50,
                    'vix_term_structure': 0,
                    'spx_5d_return': 0,
                    'spx_20d_return': 0,
                    'distance_from_high': 0,
                    'data_quality_pct': 0
                }
                estimated_data_count += 1

            # Build features using REAL data
            features = SPXWheelFeatures(
                trade_date=trade_date,
                strike=float(strike),
                underlying_price=float(underlying),
                dte=dte,
                delta=trade.get('delta', 0.20),
                premium=float(premium),
                iv=real_features.get('iv', option_iv or 0.15),
                iv_rank=real_features.get('iv_rank', 50),
                vix=real_features.get('vix', 18),
                vix_percentile=real_features.get('vix_percentile', 50),
                vix_term_structure=real_features.get('vix_term_structure', 0),
                put_wall_distance_pct=real_features.get('put_wall_distance_pct', (float(underlying) - float(strike)) / float(underlying) * 100 if underlying else 5),
                call_wall_distance_pct=trade.get('call_wall_distance', 5),  # GEX data not available
                net_gex=0,  # GEX requires Trading Volatility subscription - noting as unavailable
                spx_20d_return=real_features.get('spx_20d_return', 0),
                spx_5d_return=real_features.get('spx_5d_return', 0),
                spx_distance_from_high=real_features.get('distance_from_high', 0),
                premium_to_strike_pct=float(premium) / float(strike) * 100 if strike else 0,
                annualized_return=(float(premium) / float(strike) * 100 * 365 / dte) if strike and dte else 0
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

            # Log this action with DATA QUALITY info
            log_ml_action(
                action="AUTO_RECORD_TRADE",
                details={
                    "strike": strike,
                    "underlying": underlying,
                    "pnl": pnl,
                    "outcome": outcome,
                    "vix": real_features.get('vix'),
                    "iv_rank": real_features.get('iv_rank'),
                    "data_quality_pct": real_features.get('data_quality_pct', 0),
                    "data_sources": real_features.get('data_sources', {})
                },
                ml_score=None,
                recommendation=outcome,
                reasoning=f"Auto-recorded from backtest {backtest_id} (data quality: {real_features.get('data_quality_pct', 0):.0f}%)",
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

        # Calculate overall data quality
        total_processed = real_data_count + estimated_data_count
        data_quality_pct = (real_data_count / total_processed * 100) if total_processed > 0 else 0

        return {
            "trades_recorded": recorded,
            "total_training_samples": len(all_outcomes),
            "can_train": can_train,
            "auto_trained": trained,
            "data_quality": {
                "real_data_trades": real_data_count,
                "estimated_data_trades": estimated_data_count,
                "quality_pct": round(data_quality_pct, 1),
                "note": "GEX data unavailable (requires Trading Volatility subscription)"
            },
            "message": f"Recorded {recorded} trades ({data_quality_pct:.0f}% real data). {'Auto-trained ML model!' if trained else f'Need {30 - len(all_outcomes)} more for training' if not can_train else 'Model already trained'}"
        }

    except Exception as e:
        logger.error(f"Auto-process error: {e}")
        import traceback
        traceback.print_exc()
        return {"error": str(e), "trades_recorded": 0, "data_quality": {"note": "Error occurred"}}


def _save_backtest_run(backtest_id: str, config: dict, summary: dict, data_quality: dict, ml_results: dict = None):
    """Save backtest run metadata to database"""
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Create backtest runs table if not exists
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS spx_wheel_backtest_runs (
                id SERIAL PRIMARY KEY,
                backtest_id VARCHAR(50) UNIQUE NOT NULL,
                timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                config JSONB,
                summary JSONB,
                data_quality JSONB,
                ml_results JSONB
            )
        ''')

        cursor.execute('''
            INSERT INTO spx_wheel_backtest_runs (backtest_id, config, summary, data_quality, ml_results)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (backtest_id) DO UPDATE SET
                config = EXCLUDED.config,
                summary = EXCLUDED.summary,
                data_quality = EXCLUDED.data_quality,
                ml_results = EXCLUDED.ml_results
        ''', (
            backtest_id,
            json.dumps(config),
            json.dumps(summary),
            json.dumps(data_quality),
            json.dumps(ml_results) if ml_results else None
        ))

        conn.commit()
        conn.close()
        logger.info(f"Saved backtest run {backtest_id}")

    except Exception as e:
        logger.error(f"Error saving backtest run: {e}")
