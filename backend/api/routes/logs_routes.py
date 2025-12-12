"""
Comprehensive Logs API Routes

Provides unified access to ALL logging tables in AlphaGEX:
- Trading Decisions (trading_decisions)
- ML Logs (ml_decision_logs, ml_predictions, ares_ml_outcomes, spx_wheel_ml_outcomes)
- Oracle Predictions (oracle_predictions)
- Psychology Analysis (psychology_analysis, pattern_learning)
- System Logs (autonomous_trader_logs, spx_debug_logs, data_collection_log)
- AI Analysis (ai_analysis_history, ai_predictions, ai_performance, ai_recommendations)
- Wheel Activity (wheel_activity_log)
- GEX Changes (gex_change_log)
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
import io
import csv
import json

from database_adapter import get_connection

router = APIRouter(prefix="/api/logs", tags=["Logs"])
logger = logging.getLogger(__name__)


# ============================================================================
# UNIFIED LOG SUMMARY
# ============================================================================

@router.get("/summary")
async def get_all_logs_summary(days: int = 7):
    """
    Get summary of ALL log tables with record counts and latest entries.
    This gives a complete picture of system activity.
    """
    conn = get_connection()
    cursor = conn.cursor()

    try:
        summaries = {}

        # List of all log tables to check
        log_tables = [
            ('trading_decisions', 'Trading Decisions', 'timestamp'),
            ('autonomous_trader_logs', 'Autonomous Trader', 'timestamp'),
            ('ml_decision_logs', 'ML Decision Logs', 'timestamp'),
            ('ml_predictions', 'ML Predictions', 'timestamp'),
            ('oracle_predictions', 'Oracle Predictions', 'created_at'),
            ('ares_ml_outcomes', 'ARES ML Outcomes', 'trade_date'),
            ('spx_wheel_ml_outcomes', 'SPX Wheel ML', 'trade_date'),
            ('psychology_analysis', 'Psychology Analysis', 'timestamp'),
            ('pattern_learning', 'Pattern Learning', 'last_seen'),
            ('ai_analysis_history', 'AI Analysis', 'timestamp'),
            ('ai_predictions', 'AI Predictions', 'timestamp'),
            ('ai_performance', 'AI Performance', 'date'),
            ('ai_recommendations', 'AI Recommendations', 'timestamp'),
            ('wheel_activity_log', 'Wheel Activity', 'timestamp'),
            ('gex_change_log', 'GEX Changes', 'timestamp'),
            ('spx_debug_logs', 'SPX Debug', 'timestamp'),
            ('data_collection_log', 'Data Collection', 'timestamp'),
            ('options_collection_log', 'Options Collection', 'timestamp'),
        ]

        total_records = 0

        for table_name, display_name, ts_col in log_tables:
            try:
                # Check if table exists
                cursor.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables
                        WHERE table_name = %s
                    )
                """, (table_name,))
                exists = cursor.fetchone()[0]

                if not exists:
                    summaries[table_name] = {
                        'display_name': display_name,
                        'exists': False,
                        'total_count': 0,
                        'recent_count': 0,
                        'latest_entry': None
                    }
                    continue

                # Get total count
                cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                total = cursor.fetchone()[0]

                # Get recent count (last N days)
                cursor.execute(f"""
                    SELECT COUNT(*) FROM {table_name}
                    WHERE {ts_col} >= NOW() - INTERVAL '%s days'
                """, (days,))
                recent = cursor.fetchone()[0]

                # Get latest entry timestamp
                cursor.execute(f"SELECT MAX({ts_col}) FROM {table_name}")
                latest = cursor.fetchone()[0]

                summaries[table_name] = {
                    'display_name': display_name,
                    'exists': True,
                    'total_count': total,
                    'recent_count': recent,
                    'latest_entry': str(latest) if latest else None
                }
                total_records += total

            except Exception as e:
                logger.warning(f"Error checking {table_name}: {e}")
                summaries[table_name] = {
                    'display_name': display_name,
                    'exists': False,
                    'error': str(e)
                }

        cursor.close()
        conn.close()

        return {
            'success': True,
            'data': {
                'total_records_all_tables': total_records,
                'days_analyzed': days,
                'tables': summaries,
                'generated_at': datetime.now().isoformat()
            }
        }

    except Exception as e:
        cursor.close()
        conn.close()
        logger.error(f"Error getting logs summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# ML LOGS (ml_decision_logs, ml_predictions)
# ============================================================================

@router.get("/ml")
async def get_ml_logs(
    limit: int = Query(50, le=500),
    offset: int = 0,
    action: Optional[str] = None,
    symbol: Optional[str] = None
):
    """Get ML decision logs with filtering."""
    conn = get_connection()
    cursor = conn.cursor()

    try:
        # Check if table exists
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'ml_decision_logs'
            )
        """)
        if not cursor.fetchone()[0]:
            return {'success': True, 'data': {'logs': [], 'total': 0, 'message': 'Table not yet created'}}

        where_clauses = []
        params = []

        if action:
            where_clauses.append("action = %s")
            params.append(action)
        if symbol:
            where_clauses.append("symbol = %s")
            params.append(symbol)

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        # Get total count
        cursor.execute(f"SELECT COUNT(*) FROM ml_decision_logs {where_sql}", params)
        total = cursor.fetchone()[0]

        # Get logs
        cursor.execute(f"""
            SELECT id, timestamp, action, symbol, details, ml_score,
                   recommendation, reasoning, trade_id, backtest_id
            FROM ml_decision_logs
            {where_sql}
            ORDER BY timestamp DESC
            LIMIT %s OFFSET %s
        """, params + [limit, offset])

        columns = ['id', 'timestamp', 'action', 'symbol', 'details', 'ml_score',
                   'recommendation', 'reasoning', 'trade_id', 'backtest_id']
        logs = [dict(zip(columns, row)) for row in cursor.fetchall()]

        # Convert timestamps
        for log in logs:
            if log['timestamp']:
                log['timestamp'] = str(log['timestamp'])
            if log['details'] and isinstance(log['details'], str):
                try:
                    log['details'] = json.loads(log['details'])
                except:
                    pass

        cursor.close()
        conn.close()

        return {
            'success': True,
            'data': {
                'logs': logs,
                'total': total,
                'limit': limit,
                'offset': offset
            }
        }

    except Exception as e:
        cursor.close()
        conn.close()
        logger.error(f"Error getting ML logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# ORACLE PREDICTIONS
# ============================================================================

@router.get("/oracle")
async def get_oracle_predictions(
    limit: int = Query(50, le=500),
    bot_name: Optional[str] = None,
    days: int = 30
):
    """Get Oracle ML predictions with outcomes."""
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'oracle_predictions'
            )
        """)
        if not cursor.fetchone()[0]:
            return {'success': True, 'data': {'predictions': [], 'total': 0, 'message': 'Table not yet created'}}

        where_clauses = ["created_at >= NOW() - INTERVAL '%s days'"]
        params = [days]

        if bot_name:
            where_clauses.append("bot_name = %s")
            params.append(bot_name)

        where_sql = f"WHERE {' AND '.join(where_clauses)}"

        cursor.execute(f"""
            SELECT id, trade_date, bot_name, advice, win_probability, confidence,
                   suggested_risk_pct, reasoning, model_version, top_factors,
                   actual_outcome, actual_pnl, created_at
            FROM oracle_predictions
            {where_sql}
            ORDER BY created_at DESC
            LIMIT %s
        """, params + [limit])

        columns = ['id', 'trade_date', 'bot_name', 'advice', 'win_probability', 'confidence',
                   'suggested_risk_pct', 'reasoning', 'model_version', 'top_factors',
                   'actual_outcome', 'actual_pnl', 'created_at']
        predictions = [dict(zip(columns, row)) for row in cursor.fetchall()]

        for pred in predictions:
            for key in ['trade_date', 'created_at']:
                if pred.get(key):
                    pred[key] = str(pred[key])

        # Get accuracy stats
        cursor.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN actual_outcome = 'WIN' THEN 1 ELSE 0 END) as wins,
                AVG(confidence) as avg_confidence
            FROM oracle_predictions
            WHERE actual_outcome IS NOT NULL
        """)
        stats = cursor.fetchone()

        cursor.close()
        conn.close()

        return {
            'success': True,
            'data': {
                'predictions': predictions,
                'stats': {
                    'total_with_outcome': stats[0] or 0,
                    'wins': stats[1] or 0,
                    'accuracy': (stats[1] / stats[0] * 100) if stats[0] else 0,
                    'avg_confidence': float(stats[2]) if stats[2] else 0
                }
            }
        }

    except Exception as e:
        cursor.close()
        conn.close()
        logger.error(f"Error getting Oracle predictions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# PSYCHOLOGY ANALYSIS
# ============================================================================

@router.get("/psychology")
async def get_psychology_logs(
    limit: int = Query(50, le=500),
    regime_type: Optional[str] = None,
    days: int = 30
):
    """Get psychology analysis and trap detection logs."""
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'psychology_analysis'
            )
        """)
        if not cursor.fetchone()[0]:
            return {'success': True, 'data': {'analyses': [], 'total': 0, 'message': 'Table not yet created'}}

        where_clauses = ["timestamp >= NOW() - INTERVAL '%s days'"]
        params = [days]

        if regime_type:
            where_clauses.append("regime_type = %s")
            params.append(regime_type)

        where_sql = f"WHERE {' AND '.join(where_clauses)}"

        cursor.execute(f"""
            SELECT id, timestamp, symbol, regime_type, confidence,
                   psychology_trap, trap_probability, market_context,
                   recommended_action, notes
            FROM psychology_analysis
            {where_sql}
            ORDER BY timestamp DESC
            LIMIT %s
        """, params + [limit])

        columns = ['id', 'timestamp', 'symbol', 'regime_type', 'confidence',
                   'psychology_trap', 'trap_probability', 'market_context',
                   'recommended_action', 'notes']
        analyses = [dict(zip(columns, row)) for row in cursor.fetchall()]

        for item in analyses:
            if item.get('timestamp'):
                item['timestamp'] = str(item['timestamp'])

        cursor.close()
        conn.close()

        return {
            'success': True,
            'data': {
                'analyses': analyses,
                'total': len(analyses)
            }
        }

    except Exception as e:
        cursor.close()
        conn.close()
        logger.error(f"Error getting psychology logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# AUTONOMOUS TRADER LOGS
# ============================================================================

@router.get("/autonomous")
async def get_autonomous_trader_logs(
    limit: int = Query(50, le=500),
    log_type: Optional[str] = None,
    session_id: Optional[str] = None,
    days: int = 7
):
    """Get autonomous trader scan logs with AI thought process."""
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'autonomous_trader_logs'
            )
        """)
        if not cursor.fetchone()[0]:
            return {'success': True, 'data': {'logs': [], 'total': 0, 'message': 'Table not yet created'}}

        where_clauses = ["timestamp >= NOW() - INTERVAL '%s days'"]
        params = [days]

        if log_type:
            where_clauses.append("log_type = %s")
            params.append(log_type)
        if session_id:
            where_clauses.append("session_id = %s")
            params.append(session_id)

        where_sql = f"WHERE {' AND '.join(where_clauses)}"

        cursor.execute(f"""
            SELECT id, timestamp, log_type, symbol, pattern_detected,
                   confidence_score, ai_thought_process, reasoning_summary,
                   scan_cycle, session_id, additional_data
            FROM autonomous_trader_logs
            {where_sql}
            ORDER BY timestamp DESC
            LIMIT %s
        """, params + [limit])

        columns = ['id', 'timestamp', 'log_type', 'symbol', 'pattern_detected',
                   'confidence_score', 'ai_thought_process', 'reasoning_summary',
                   'scan_cycle', 'session_id', 'additional_data']
        logs = [dict(zip(columns, row)) for row in cursor.fetchall()]

        for log in logs:
            if log.get('timestamp'):
                log['timestamp'] = str(log['timestamp'])

        cursor.close()
        conn.close()

        return {
            'success': True,
            'data': {
                'logs': logs,
                'total': len(logs)
            }
        }

    except Exception as e:
        cursor.close()
        conn.close()
        logger.error(f"Error getting autonomous logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# AI RECOMMENDATIONS
# ============================================================================

@router.get("/ai-recommendations")
async def get_ai_recommendations(
    limit: int = Query(50, le=500),
    symbol: Optional[str] = None,
    days: int = 30
):
    """Get AI trade recommendations with outcomes."""
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'ai_recommendations'
            )
        """)
        if not cursor.fetchone()[0]:
            return {'success': True, 'data': {'recommendations': [], 'total': 0, 'message': 'Table not yet created'}}

        where_clauses = ["timestamp >= NOW() - INTERVAL '%s days'"]
        params = [days]

        if symbol:
            where_clauses.append("symbol = %s")
            params.append(symbol)

        where_sql = f"WHERE {' AND '.join(where_clauses)}"

        cursor.execute(f"""
            SELECT id, timestamp, symbol, recommendation_type, action,
                   strike, expiration, confidence, reasoning,
                   expected_return, outcome, actual_pnl
            FROM ai_recommendations
            {where_sql}
            ORDER BY timestamp DESC
            LIMIT %s
        """, params + [limit])

        columns = ['id', 'timestamp', 'symbol', 'recommendation_type', 'action',
                   'strike', 'expiration', 'confidence', 'reasoning',
                   'expected_return', 'outcome', 'actual_pnl']
        recs = [dict(zip(columns, row)) for row in cursor.fetchall()]

        for rec in recs:
            if rec.get('timestamp'):
                rec['timestamp'] = str(rec['timestamp'])
            if rec.get('expiration'):
                rec['expiration'] = str(rec['expiration'])

        cursor.close()
        conn.close()

        return {
            'success': True,
            'data': {
                'recommendations': recs,
                'total': len(recs)
            }
        }

    except Exception as e:
        cursor.close()
        conn.close()
        logger.error(f"Error getting AI recommendations: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# WHEEL ACTIVITY LOG
# ============================================================================

@router.get("/wheel-activity")
async def get_wheel_activity(
    limit: int = Query(50, le=500),
    action: Optional[str] = None,
    days: int = 30
):
    """Get wheel strategy activity logs."""
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'wheel_activity_log'
            )
        """)
        if not cursor.fetchone()[0]:
            return {'success': True, 'data': {'activities': [], 'total': 0, 'message': 'Table not yet created'}}

        where_clauses = ["timestamp >= NOW() - INTERVAL '%s days'"]
        params = [days]

        if action:
            where_clauses.append("action = %s")
            params.append(action)

        where_sql = f"WHERE {' AND '.join(where_clauses)}"

        cursor.execute(f"""
            SELECT id, timestamp, action, description, premium_impact,
                   pnl_impact, underlying_price, option_price, details
            FROM wheel_activity_log
            {where_sql}
            ORDER BY timestamp DESC
            LIMIT %s
        """, params + [limit])

        columns = ['id', 'timestamp', 'action', 'description', 'premium_impact',
                   'pnl_impact', 'underlying_price', 'option_price', 'details']
        activities = [dict(zip(columns, row)) for row in cursor.fetchall()]

        for act in activities:
            if act.get('timestamp'):
                act['timestamp'] = str(act['timestamp'])

        cursor.close()
        conn.close()

        return {
            'success': True,
            'data': {
                'activities': activities,
                'total': len(activities)
            }
        }

    except Exception as e:
        cursor.close()
        conn.close()
        logger.error(f"Error getting wheel activity: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# GEX CHANGE LOG
# ============================================================================

@router.get("/gex-changes")
async def get_gex_changes(
    limit: int = Query(100, le=500),
    symbol: Optional[str] = None,
    change_type: Optional[str] = None,
    days: int = 7
):
    """Get GEX change and direction shift logs."""
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'gex_change_log'
            )
        """)
        if not cursor.fetchone()[0]:
            return {'success': True, 'data': {'changes': [], 'total': 0, 'message': 'Table not yet created'}}

        where_clauses = ["timestamp >= NOW() - INTERVAL '%s days'"]
        params = [days]

        if symbol:
            where_clauses.append("symbol = %s")
            params.append(symbol)
        if change_type:
            where_clauses.append("change_type = %s")
            params.append(change_type)

        where_sql = f"WHERE {' AND '.join(where_clauses)}"

        cursor.execute(f"""
            SELECT id, timestamp, symbol, change_type, previous_value,
                   new_value, change_pct, velocity_trend, direction_change
            FROM gex_change_log
            {where_sql}
            ORDER BY timestamp DESC
            LIMIT %s
        """, params + [limit])

        columns = ['id', 'timestamp', 'symbol', 'change_type', 'previous_value',
                   'new_value', 'change_pct', 'velocity_trend', 'direction_change']
        changes = [dict(zip(columns, row)) for row in cursor.fetchall()]

        for change in changes:
            if change.get('timestamp'):
                change['timestamp'] = str(change['timestamp'])

        cursor.close()
        conn.close()

        return {
            'success': True,
            'data': {
                'changes': changes,
                'total': len(changes)
            }
        }

    except Exception as e:
        cursor.close()
        conn.close()
        logger.error(f"Error getting GEX changes: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# ARES ML OUTCOMES
# ============================================================================

@router.get("/ares-ml")
async def get_ares_ml_outcomes(
    limit: int = Query(50, le=500),
    days: int = 30
):
    """Get ARES ML model outcomes for learning analysis."""
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'ares_ml_outcomes'
            )
        """)
        if not cursor.fetchone()[0]:
            return {'success': True, 'data': {'outcomes': [], 'total': 0, 'message': 'Table not yet created'}}

        cursor.execute("""
            SELECT id, trade_date, vix, net_gex, gex_regime, day_of_week,
                   predicted_advice, win_probability, confidence,
                   actual_outcome, is_win, net_pnl, created_at
            FROM ares_ml_outcomes
            WHERE trade_date >= NOW() - INTERVAL '%s days'
            ORDER BY trade_date DESC
            LIMIT %s
        """, (days, limit))

        columns = ['id', 'trade_date', 'vix', 'net_gex', 'gex_regime', 'day_of_week',
                   'predicted_advice', 'win_probability', 'confidence',
                   'actual_outcome', 'is_win', 'net_pnl', 'created_at']
        outcomes = [dict(zip(columns, row)) for row in cursor.fetchall()]

        for outcome in outcomes:
            if outcome.get('trade_date'):
                outcome['trade_date'] = str(outcome['trade_date'])
            if outcome.get('created_at'):
                outcome['created_at'] = str(outcome['created_at'])

        # Get accuracy stats
        cursor.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN is_win THEN 1 ELSE 0 END) as wins,
                AVG(net_pnl) as avg_pnl
            FROM ares_ml_outcomes
            WHERE actual_outcome IS NOT NULL
        """)
        stats = cursor.fetchone()

        cursor.close()
        conn.close()

        return {
            'success': True,
            'data': {
                'outcomes': outcomes,
                'stats': {
                    'total': stats[0] or 0,
                    'wins': stats[1] or 0,
                    'win_rate': (stats[1] / stats[0] * 100) if stats[0] else 0,
                    'avg_pnl': float(stats[2]) if stats[2] else 0
                }
            }
        }

    except Exception as e:
        cursor.close()
        conn.close()
        logger.error(f"Error getting ARES ML outcomes: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# EXPORT ALL LOGS
# ============================================================================

@router.get("/export/{log_type}")
async def export_logs(
    log_type: str,
    format: str = Query("csv", regex="^(csv|json)$"),
    days: int = 30
):
    """
    Export logs to CSV or JSON.

    log_type options:
    - trading_decisions
    - ml_logs
    - oracle
    - psychology
    - autonomous
    - ai_recommendations
    - wheel_activity
    - gex_changes
    - ares_ml
    """
    # Get data based on log type
    if log_type == "trading_decisions":
        from trading.decision_logger import export_decisions_json, export_decisions_csv
        if format == "csv":
            content = export_decisions_csv()
            return StreamingResponse(
                io.StringIO(content),
                media_type="text/csv",
                headers={"Content-Disposition": f"attachment; filename=trading_decisions_{datetime.now().strftime('%Y%m%d')}.csv"}
            )
        else:
            data = export_decisions_json(limit=10000)
            return data

    # For other log types, use the respective endpoints
    # This is a simplified version - could be expanded
    raise HTTPException(status_code=400, detail=f"Export not yet implemented for {log_type}")
