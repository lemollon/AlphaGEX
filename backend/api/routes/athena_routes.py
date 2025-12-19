"""
ATHENA Directional Spread Bot API Routes
==========================================

API endpoints for the ATHENA directional spread trading bot.
Provides status, positions, signals, logs, and performance metrics.

ATHENA trades Bull Call Spreads (bullish) and Bear Call Spreads (bearish)
based on GEX signals from KRONOS and ML advice from ORACLE.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query
from zoneinfo import ZoneInfo

from database_adapter import get_connection

router = APIRouter(prefix="/api/athena", tags=["ATHENA"])
logger = logging.getLogger(__name__)

# Try to import ATHENA trader
athena_trader = None
try:
    from trading.athena_directional_spreads import ATHENATrader, TradingMode, run_athena
    ATHENA_AVAILABLE = True
except ImportError as e:
    ATHENA_AVAILABLE = False
    logger.warning(f"ATHENA module not available: {e}")


def get_athena_instance():
    """Get the ATHENA trader instance"""
    global athena_trader
    if athena_trader:
        return athena_trader

    try:
        # Try to get from scheduler first
        from scheduler.trader_scheduler import get_athena_trader
        athena_trader = get_athena_trader()
        if athena_trader:
            return athena_trader
    except Exception as e:
        logger.debug(f"Could not get ATHENA from scheduler: {e}")

    # Initialize a new instance if needed
    if ATHENA_AVAILABLE:
        try:
            athena_trader = run_athena(capital=100_000, mode="paper")
            return athena_trader
        except Exception as e:
            logger.error(f"Failed to initialize ATHENA: {e}")

    return None


@router.get("/status")
async def get_athena_status():
    """
    Get current ATHENA bot status.

    Returns mode, capital, P&L, positions, and configuration.
    """
    athena = get_athena_instance()

    if not athena:
        # Return default status when ATHENA not initialized
        return {
            "success": True,
            "data": {
                "mode": "paper",
                "capital": 100000,
                "total_pnl": 0,
                "trade_count": 0,
                "win_rate": 0,
                "open_positions": 0,
                "closed_positions": 0,
                "traded_today": False,
                "current_time": datetime.now(ZoneInfo("America/Chicago")).strftime('%Y-%m-%d %H:%M:%S CT'),
                "is_active": False,
                "oracle_available": False,
                "kronos_available": False,
                "gex_ml_available": False,
                "config": {
                    "risk_per_trade": 2.0,
                    "spread_width": 2,
                    "wall_filter_pct": 1.0,
                    "ticker": "SPY",
                    "max_daily_trades": 5
                },
                "message": "ATHENA not yet initialized"
            }
        }

    try:
        status = athena.get_status()
        status['is_active'] = True

        return {
            "success": True,
            "data": status
        }
    except Exception as e:
        logger.error(f"Error getting ATHENA status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/positions")
async def get_athena_positions(
    status_filter: Optional[str] = Query(None, description="Filter by status: open, closed, all"),
    limit: int = Query(50, description="Max positions to return")
):
    """
    Get ATHENA positions from database.

    Returns open and/or closed positions with P&L details.
    """
    try:
        conn = get_connection()
        c = conn.cursor()

        where_clause = ""
        if status_filter == "open":
            where_clause = "WHERE status = 'open'"
        elif status_filter == "closed":
            where_clause = "WHERE status = 'closed'"

        c.execute(f"""
            SELECT
                position_id, spread_type, ticker,
                long_strike, short_strike, expiration,
                entry_price, contracts, max_profit, max_loss,
                spot_at_entry, gex_regime, oracle_confidence,
                status, exit_price, exit_reason, realized_pnl,
                created_at, exit_time
            FROM apache_positions
            {where_clause}
            ORDER BY created_at DESC
            LIMIT %s
        """, (limit,))

        rows = c.fetchall()
        conn.close()

        positions = []
        for row in rows:
            positions.append({
                "position_id": row[0],
                "spread_type": row[1],
                "ticker": row[2],
                "long_strike": float(row[3]) if row[3] else 0,
                "short_strike": float(row[4]) if row[4] else 0,
                "expiration": str(row[5]) if row[5] else None,
                "entry_price": float(row[6]) if row[6] else 0,
                "contracts": row[7],
                "max_profit": float(row[8]) if row[8] else 0,
                "max_loss": float(row[9]) if row[9] else 0,
                "spot_at_entry": float(row[10]) if row[10] else 0,
                "gex_regime": row[11],
                "oracle_confidence": float(row[12]) if row[12] else 0,
                "status": row[13],
                "exit_price": float(row[14]) if row[14] else 0,
                "exit_reason": row[15],
                "realized_pnl": float(row[16]) if row[16] else 0,
                "created_at": row[17].isoformat() if row[17] else None,
                "exit_time": row[18].isoformat() if row[18] else None
            })

        return {
            "success": True,
            "data": positions,
            "count": len(positions)
        }

    except Exception as e:
        logger.error(f"Error getting ATHENA positions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/signals")
async def get_athena_signals(
    limit: int = Query(50, description="Max signals to return"),
    direction: Optional[str] = Query(None, description="Filter by direction: BULLISH, BEARISH")
):
    """
    Get ATHENA signals from Oracle.

    Returns recent signals with direction, confidence, and reasoning.
    """
    try:
        conn = get_connection()
        c = conn.cursor()

        where_clause = ""
        params = [limit]
        if direction:
            where_clause = "WHERE signal_direction = %s"
            params = [direction, limit]

        c.execute(f"""
            SELECT
                id, created_at, ticker, signal_direction,
                ml_confidence, oracle_advice, gex_regime,
                call_wall, put_wall, spot_price,
                spread_type, reasoning, status
            FROM apache_signals
            {where_clause}
            ORDER BY created_at DESC
            LIMIT %s
        """, tuple(params))

        rows = c.fetchall()
        conn.close()

        signals = []
        for row in rows:
            signals.append({
                "id": row[0],
                "created_at": row[1].isoformat() if row[1] else None,
                "ticker": row[2],
                "direction": row[3],
                "confidence": float(row[4]) if row[4] else 0,
                "oracle_advice": row[5],
                "gex_regime": row[6],
                "call_wall": float(row[7]) if row[7] else 0,
                "put_wall": float(row[8]) if row[8] else 0,
                "spot_price": float(row[9]) if row[9] else 0,
                "spread_type": row[10],
                "reasoning": row[11],
                "status": row[12]
            })

        return {
            "success": True,
            "data": signals,
            "count": len(signals)
        }

    except Exception as e:
        logger.error(f"Error getting ATHENA signals: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/logs")
async def get_athena_logs(
    level: Optional[str] = Query(None, description="Filter by level: DEBUG, INFO, WARNING, ERROR"),
    limit: int = Query(100, description="Max logs to return")
):
    """
    Get ATHENA logs for debugging and monitoring.
    """
    try:
        conn = get_connection()
        c = conn.cursor()

        where_clause = ""
        params = [limit]
        if level:
            where_clause = "WHERE log_level = %s"
            params = [level, limit]

        c.execute(f"""
            SELECT
                id, created_at, log_level, message, details
            FROM apache_logs
            {where_clause}
            ORDER BY created_at DESC
            LIMIT %s
        """, tuple(params))

        rows = c.fetchall()
        conn.close()

        logs = []
        for row in rows:
            logs.append({
                "id": row[0],
                "created_at": row[1].isoformat() if row[1] else None,
                "level": row[2],
                "message": row[3],
                "details": row[4]
            })

        return {
            "success": True,
            "data": logs,
            "count": len(logs)
        }

    except Exception as e:
        logger.error(f"Error getting ATHENA logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/performance")
async def get_athena_performance(
    days: int = Query(30, description="Number of days to include")
):
    """
    Get ATHENA performance metrics over time.
    """
    try:
        conn = get_connection()
        c = conn.cursor()

        # Get daily performance
        c.execute("""
            SELECT
                trade_date, trades_executed, trades_won, trades_lost,
                win_rate, gross_pnl, net_pnl, daily_return_pct,
                bullish_trades, bearish_trades
            FROM apache_performance
            WHERE trade_date >= CURRENT_DATE - INTERVAL '%s days'
            ORDER BY trade_date DESC
        """, (days,))

        rows = c.fetchall()

        # Calculate summary stats
        c.execute("""
            SELECT
                COALESCE(SUM(trades_executed), 0) as total_trades,
                COALESCE(SUM(trades_won), 0) as total_wins,
                COALESCE(SUM(net_pnl), 0) as total_pnl,
                COALESCE(AVG(win_rate), 0) as avg_win_rate,
                COALESCE(SUM(bullish_trades), 0) as bullish_count,
                COALESCE(SUM(bearish_trades), 0) as bearish_count
            FROM apache_performance
            WHERE trade_date >= CURRENT_DATE - INTERVAL '%s days'
        """, (days,))

        summary_row = c.fetchone()
        conn.close()

        daily_data = []
        for row in rows:
            daily_data.append({
                "date": str(row[0]),
                "trades": row[1],
                "wins": row[2],
                "losses": row[3],
                "win_rate": float(row[4]) if row[4] else 0,
                "gross_pnl": float(row[5]) if row[5] else 0,
                "net_pnl": float(row[6]) if row[6] else 0,
                "return_pct": float(row[7]) if row[7] else 0,
                "bullish": row[8],
                "bearish": row[9]
            })

        return {
            "success": True,
            "data": {
                "summary": {
                    "total_trades": summary_row[0] if summary_row else 0,
                    "total_wins": summary_row[1] if summary_row else 0,
                    "total_pnl": float(summary_row[2]) if summary_row and summary_row[2] else 0,
                    "avg_win_rate": float(summary_row[3]) if summary_row and summary_row[3] else 0,
                    "bullish_count": summary_row[4] if summary_row else 0,
                    "bearish_count": summary_row[5] if summary_row else 0
                },
                "daily": daily_data
            }
        }

    except Exception as e:
        logger.error(f"Error getting ATHENA performance: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/config")
async def get_athena_config():
    """
    Get ATHENA configuration settings.
    """
    try:
        conn = get_connection()
        c = conn.cursor()

        c.execute("""
            SELECT setting_name, setting_value, description
            FROM apache_config
            ORDER BY setting_name
        """)

        rows = c.fetchall()
        conn.close()

        config = {}
        for row in rows:
            config[row[0]] = {
                "value": row[1],
                "description": row[2]
            }

        return {
            "success": True,
            "data": config
        }

    except Exception as e:
        logger.error(f"Error getting ATHENA config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/config/{setting_name}")
async def update_athena_config(setting_name: str, value: str):
    """
    Update an ATHENA configuration setting.
    """
    try:
        conn = get_connection()
        c = conn.cursor()

        c.execute("""
            UPDATE apache_config
            SET setting_value = %s, updated_at = NOW()
            WHERE setting_name = %s
            RETURNING setting_name
        """, (value, setting_name))

        result = c.fetchone()
        conn.commit()
        conn.close()

        if not result:
            raise HTTPException(status_code=404, detail=f"Setting '{setting_name}' not found")

        return {
            "success": True,
            "message": f"Updated {setting_name} to {value}"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating ATHENA config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/run")
async def run_athena_cycle():
    """
    Manually trigger an ATHENA trading cycle.

    Use for testing or forcing a trade check outside the scheduler.
    """
    athena = get_athena_instance()

    if not athena:
        raise HTTPException(status_code=503, detail="ATHENA not available")

    try:
        result = athena.run_daily_cycle()
        return {
            "success": True,
            "data": result
        }
    except Exception as e:
        logger.error(f"Error running ATHENA cycle: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/oracle-advice")
async def get_current_oracle_advice():
    """
    Get current Oracle advice for ATHENA without executing a trade.

    Useful for monitoring what Oracle would recommend right now.
    """
    athena = get_athena_instance()

    if not athena:
        raise HTTPException(status_code=503, detail="ATHENA not available")

    try:
        advice = athena.get_oracle_advice()

        if not advice:
            return {
                "success": True,
                "data": None,
                "message": "No Oracle advice available (check GEX data)"
            }

        return {
            "success": True,
            "data": {
                "advice": advice.advice.value,
                "win_probability": advice.win_probability,
                "confidence": advice.confidence,
                "reasoning": advice.reasoning,
                "suggested_call_strike": advice.suggested_call_strike,
                "use_gex_walls": advice.use_gex_walls
            }
        }
    except Exception as e:
        logger.error(f"Error getting Oracle advice: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ml-signal")
async def get_current_ml_signal():
    """
    Get current ML signal from GEX probability models without executing a trade.

    Returns the ML-based trading signal using the 5 GEX probability models:
    - Direction probability (UP/DOWN/FLAT)
    - Flip gravity probability
    - Magnet attraction probability
    - Expected volatility
    - Pin zone probability

    Combined into a LONG/SHORT/STAY_OUT recommendation.
    """
    athena = get_athena_instance()

    if not athena:
        raise HTTPException(status_code=503, detail="ATHENA not available")

    try:
        # Get current GEX data
        gex_data = athena.get_gex_data()
        if not gex_data:
            return {
                "success": True,
                "data": None,
                "message": "No GEX data available - Kronos may be unavailable"
            }

        # Get ML signal
        ml_signal = athena.get_ml_signal(gex_data)

        if not ml_signal:
            return {
                "success": True,
                "data": None,
                "message": "ML models not loaded - run train_gex_probability_models.py first"
            }

        return {
            "success": True,
            "data": {
                "advice": ml_signal['advice'],
                "spread_type": ml_signal['spread_type'],
                "confidence": ml_signal['confidence'],
                "win_probability": ml_signal['win_probability'],
                "expected_volatility": ml_signal['expected_volatility'],
                "suggested_strikes": ml_signal['suggested_strikes'],
                "reasoning": ml_signal['reasoning'],
                "model_predictions": ml_signal['model_predictions'],
                "gex_context": {
                    "spot_price": gex_data.get('spot_price'),
                    "regime": gex_data.get('regime'),
                    "call_wall": gex_data.get('call_wall'),
                    "put_wall": gex_data.get('put_wall'),
                    "net_gex": gex_data.get('net_gex')
                }
            }
        }
    except Exception as e:
        logger.error(f"Error getting ML signal: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/diagnostics")
async def get_athena_diagnostics():
    """
    Diagnostic endpoint for troubleshooting Apache issues.

    Returns detailed status of all subsystems:
    - Kronos (GEX calculator)
    - Oracle (ML advisor)
    - GEX ML models
    - Tradier (execution)
    - Database connectivity
    - Recent GEX data availability
    """
    import os

    diagnostics = {
        "timestamp": datetime.now(ZoneInfo("America/Chicago")).isoformat(),
        "subsystems": {},
        "data_availability": {},
        "environment": {}
    }

    # Check Apache availability
    athena = get_athena_instance()
    diagnostics["athena_available"] = athena is not None

    if athena:
        # Subsystem status
        diagnostics["subsystems"]["kronos"] = {
            "available": athena.kronos is not None,
            "type": type(athena.kronos).__name__ if athena.kronos else None
        }
        diagnostics["subsystems"]["oracle"] = {
            "available": athena.oracle is not None,
            "type": type(athena.oracle).__name__ if athena.oracle else None
        }
        diagnostics["subsystems"]["gex_ml"] = {
            "available": athena.gex_ml is not None,
            "type": type(athena.gex_ml).__name__ if athena.gex_ml else None
        }
        diagnostics["subsystems"]["tradier"] = {
            "available": athena.tradier is not None,
            "type": type(athena.tradier).__name__ if athena.tradier else None
        }

        # Try to get GEX data
        try:
            gex_data = athena.get_gex_data()
            diagnostics["data_availability"]["gex_data"] = {
                "available": gex_data is not None,
                "source": gex_data.get('source') if gex_data else None,
                "spot_price": gex_data.get('spot_price') if gex_data else None,
                "regime": gex_data.get('regime') if gex_data else None
            }
        except Exception as e:
            diagnostics["data_availability"]["gex_data"] = {
                "available": False,
                "error": str(e)
            }

    # Check ML model file
    model_path = "models/gex_signal_generator.joblib"
    diagnostics["data_availability"]["ml_model_file"] = {
        "path": model_path,
        "exists": os.path.exists(model_path),
        "size_kb": os.path.getsize(model_path) // 1024 if os.path.exists(model_path) else 0
    }

    # Check database GEX data
    try:
        conn = get_connection()
        c = conn.cursor()

        # Get latest GEX data date
        c.execute("""
            SELECT symbol, MAX(trade_date) as latest_date, COUNT(*) as total_records
            FROM gex_daily
            GROUP BY symbol
            ORDER BY latest_date DESC
            LIMIT 5
        """)
        rows = c.fetchall()
        diagnostics["data_availability"]["database_gex"] = [
            {"symbol": r[0], "latest_date": str(r[1]), "records": r[2]}
            for r in rows
        ]

        conn.close()
    except Exception as e:
        diagnostics["data_availability"]["database_gex"] = {"error": str(e)}

    # Environment checks
    diagnostics["environment"]["polygon_api_key"] = bool(os.environ.get("POLYGON_API_KEY"))
    diagnostics["environment"]["tradier_token"] = bool(os.environ.get("TRADIER_ACCESS_TOKEN"))
    diagnostics["environment"]["anthropic_key"] = bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("CLAUDE_API_KEY"))
    diagnostics["environment"]["database_url"] = bool(os.environ.get("DATABASE_URL"))
    diagnostics["environment"]["orat_database_url"] = bool(os.environ.get("ORAT_DATABASE_URL"))

    # Check ORAT database connectivity and data availability
    orat_url = os.environ.get("ORAT_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if orat_url:
        try:
            import psycopg2
            from urllib.parse import urlparse
            result = urlparse(orat_url)
            conn = psycopg2.connect(
                host=result.hostname,
                port=result.port or 5432,
                user=result.username,
                password=result.password,
                database=result.path[1:],
                connect_timeout=5
            )
            c = conn.cursor()
            # Quick query - just get max date, don't count all rows
            c.execute("""
                SELECT MAX(trade_date)
                FROM orat_options_eod
                WHERE ticker = 'SPX'
                LIMIT 1
            """)
            row = c.fetchone()
            conn.close()
            diagnostics["data_availability"]["orat_database"] = {
                "connected": True,
                "most_recent_date": str(row[0]) if row and row[0] else None
            }
        except Exception as e:
            diagnostics["data_availability"]["orat_database"] = {
                "connected": False,
                "error": str(e)
            }

    return {
        "success": True,
        "data": diagnostics
    }
