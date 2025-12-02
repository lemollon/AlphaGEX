"""
Regime Signals API Routes

Exposes the 80+ columns of market regime analysis data that was previously hidden.
This gives full transparency into the AI/ML analysis driving trading decisions.
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List
import logging
from datetime import datetime, timedelta

from database_adapter import get_connection
import psycopg2.extras

router = APIRouter(prefix="/api/regime", tags=["Regime Analysis"])
logger = logging.getLogger(__name__)


@router.get("/current")
async def get_current_regime(symbol: str = "SPY"):
    """
    Get the most recent regime analysis with ALL fields.

    Returns 80+ columns of analysis including:
    - RSI across 5 timeframes (5m, 15m, 1h, 4h, 1d)
    - Gamma wall distances and strengths
    - Liberation setup detection
    - False floor detection
    - Monthly magnets
    - Psychology trap indicators
    - VIX analysis
    - And much more...
    """
    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cursor.execute("""
            SELECT * FROM regime_signals
            ORDER BY timestamp DESC
            LIMIT 1
        """)

        row = cursor.fetchone()
        conn.close()

        if not row:
            return {
                "success": False,
                "message": "No regime signals found",
                "data": None
            }

        return {
            "success": True,
            "data": dict(row),
            "columns_returned": len(row.keys()),
            "note": "All 80+ analysis columns are now exposed"
        }

    except Exception as e:
        logger.error(f"Error getting current regime: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history")
async def get_regime_history(
    days: int = Query(7, ge=1, le=90, description="Number of days of history"),
    limit: int = Query(100, ge=1, le=1000, description="Max records to return"),
    symbol: str = "SPY"
):
    """
    Get historical regime signals with ALL fields.

    Use this to analyze how regime classifications evolved over time.
    """
    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

        cursor.execute("""
            SELECT * FROM regime_signals
            WHERE timestamp >= %s
            ORDER BY timestamp DESC
            LIMIT %s
        """, (start_date, limit))

        rows = cursor.fetchall()
        conn.close()

        return {
            "success": True,
            "data": [dict(row) for row in rows],
            "count": len(rows),
            "days_requested": days,
            "columns_per_record": len(rows[0].keys()) if rows else 0
        }

    except Exception as e:
        logger.error(f"Error getting regime history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/columns")
async def get_regime_columns():
    """
    Get list of all columns in regime_signals table.

    Useful for understanding what data is available.
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'regime_signals'
            ORDER BY ordinal_position
        """)

        columns = cursor.fetchall()
        conn.close()

        return {
            "success": True,
            "columns": [
                {
                    "name": col[0],
                    "type": col[1],
                    "nullable": col[2]
                }
                for col in columns
            ],
            "total_columns": len(columns)
        }

    except Exception as e:
        logger.error(f"Error getting columns: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/rsi-analysis")
async def get_rsi_analysis(limit: int = 20):
    """
    Get RSI analysis across all timeframes.

    Shows RSI values for 5m, 15m, 1h, 4h, 1d timeframes.
    """
    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cursor.execute("""
            SELECT
                timestamp,
                spy_price,
                rsi_5m,
                rsi_15m,
                rsi_1h,
                rsi_4h,
                rsi_1d,
                rsi_score,
                rsi_aligned_overbought,
                rsi_aligned_oversold,
                rsi_coiling,
                primary_regime_type,
                confidence_score
            FROM regime_signals
            ORDER BY timestamp DESC
            LIMIT %s
        """, (limit,))

        rows = cursor.fetchall()
        conn.close()

        return {
            "success": True,
            "data": [dict(row) for row in rows],
            "description": "RSI analysis across 5 timeframes (5m, 15m, 1h, 4h, 1d)"
        }

    except Exception as e:
        logger.error(f"Error getting RSI analysis: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/gamma-walls")
async def get_gamma_wall_analysis(limit: int = 20):
    """
    Get gamma wall analysis data.

    Shows call/put wall levels, distances, and dealer positioning.
    """
    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cursor.execute("""
            SELECT
                timestamp,
                spy_price,
                nearest_call_wall,
                call_wall_distance_pct,
                call_wall_strength,
                call_wall_dealer_position,
                nearest_put_wall,
                put_wall_distance_pct,
                put_wall_strength,
                put_wall_dealer_position,
                net_gamma,
                net_gamma_regime,
                zero_dte_gamma,
                gamma_expiring_this_week,
                gamma_expiring_next_week,
                gamma_persistence_ratio
            FROM regime_signals
            ORDER BY timestamp DESC
            LIMIT %s
        """, (limit,))

        rows = cursor.fetchall()
        conn.close()

        return {
            "success": True,
            "data": [dict(row) for row in rows],
            "description": "Gamma wall analysis with dealer positioning"
        }

    except Exception as e:
        logger.error(f"Error getting gamma wall analysis: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/psychology-traps")
async def get_psychology_trap_analysis(limit: int = 20):
    """
    Get psychology trap detection data.

    Shows liberation setups, false floors, and trap indicators.
    """
    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cursor.execute("""
            SELECT
                timestamp,
                spy_price,
                psychology_trap,
                liberation_setup_detected,
                liberation_target_strike,
                liberation_expiry_date,
                false_floor_detected,
                false_floor_strike,
                false_floor_expiry_date,
                path_of_least_resistance,
                polr_confidence,
                primary_regime_type,
                confidence_score,
                trade_direction
            FROM regime_signals
            ORDER BY timestamp DESC
            LIMIT %s
        """, (limit,))

        rows = cursor.fetchall()
        conn.close()

        return {
            "success": True,
            "data": [dict(row) for row in rows],
            "description": "Psychology trap detection including liberation and false floor setups"
        }

    except Exception as e:
        logger.error(f"Error getting psychology trap analysis: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/monthly-magnets")
async def get_monthly_magnet_analysis(limit: int = 20):
    """
    Get monthly magnet (expiration target) data.

    Shows key price magnets from monthly option expirations.
    """
    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cursor.execute("""
            SELECT
                timestamp,
                spy_price,
                monthly_magnet_above,
                monthly_magnet_above_strength,
                monthly_magnet_below,
                monthly_magnet_below_strength,
                target_price_near,
                target_price_far,
                target_timeline_days
            FROM regime_signals
            ORDER BY timestamp DESC
            LIMIT %s
        """, (limit,))

        rows = cursor.fetchall()
        conn.close()

        return {
            "success": True,
            "data": [dict(row) for row in rows],
            "description": "Monthly expiration magnet levels"
        }

    except Exception as e:
        logger.error(f"Error getting monthly magnet analysis: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/signal-accuracy")
async def get_signal_accuracy(days: int = 30):
    """
    Get signal accuracy tracking data.

    Shows which signals were correct vs incorrect for learning.
    """
    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

        cursor.execute("""
            SELECT
                timestamp,
                primary_regime_type,
                confidence_score,
                trade_direction,
                signal_correct,
                price_change_1d,
                price_change_5d,
                price_change_10d
            FROM regime_signals
            WHERE timestamp >= %s AND signal_correct IS NOT NULL
            ORDER BY timestamp DESC
        """, (start_date,))

        rows = cursor.fetchall()
        conn.close()

        # Calculate accuracy stats
        total = len(rows)
        correct = sum(1 for r in rows if r['signal_correct'] == 1)
        accuracy = (correct / total * 100) if total > 0 else 0

        return {
            "success": True,
            "data": [dict(row) for row in rows],
            "summary": {
                "total_signals": total,
                "correct_signals": correct,
                "accuracy_pct": round(accuracy, 2),
                "days_analyzed": days
            }
        }

    except Exception as e:
        logger.error(f"Error getting signal accuracy: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/vix-analysis")
async def get_vix_analysis(limit: int = 20):
    """
    Get VIX-related analysis data.
    """
    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cursor.execute("""
            SELECT
                timestamp,
                spy_price,
                vix_current,
                vix_spike_detected,
                volatility_regime,
                risk_level
            FROM regime_signals
            ORDER BY timestamp DESC
            LIMIT %s
        """, (limit,))

        rows = cursor.fetchall()
        conn.close()

        return {
            "success": True,
            "data": [dict(row) for row in rows],
            "description": "VIX and volatility regime analysis"
        }

    except Exception as e:
        logger.error(f"Error getting VIX analysis: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/trade-reasoning")
async def get_trade_reasoning(limit: int = 10):
    """
    Get detailed trade reasoning and explanations.

    Shows WHY the system classified regimes the way it did.
    """
    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cursor.execute("""
            SELECT
                timestamp,
                spy_price,
                primary_regime_type,
                secondary_regime_type,
                confidence_score,
                trade_direction,
                risk_level,
                description,
                detailed_explanation
            FROM regime_signals
            ORDER BY timestamp DESC
            LIMIT %s
        """, (limit,))

        rows = cursor.fetchall()
        conn.close()

        return {
            "success": True,
            "data": [dict(row) for row in rows],
            "description": "Detailed reasoning behind each regime classification"
        }

    except Exception as e:
        logger.error(f"Error getting trade reasoning: {e}")
        raise HTTPException(status_code=500, detail=str(e))
