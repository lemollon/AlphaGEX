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

# Import decision logger for ATHENA decisions
try:
    from trading.decision_logger import export_decisions_json
    DECISION_LOGGER_AVAILABLE = True
except ImportError:
    DECISION_LOGGER_AVAILABLE = False
    export_decisions_json = None

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


def _get_heartbeat(bot_name: str) -> dict:
    """Get heartbeat info for a bot from the database"""
    CENTRAL_TZ = ZoneInfo("America/Chicago")

    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT last_heartbeat, status, scan_count, details
            FROM bot_heartbeats
            WHERE bot_name = %s
        ''', (bot_name,))

        row = cursor.fetchone()
        conn.close()

        if row:
            last_heartbeat, status, scan_count, details = row

            # Convert timestamp to Central Time
            # PostgreSQL may return UTC or naive datetime - handle both cases
            if last_heartbeat:
                if last_heartbeat.tzinfo is None:
                    # Naive datetime from PostgreSQL - assume it's UTC
                    last_heartbeat = last_heartbeat.replace(tzinfo=ZoneInfo("UTC"))
                # Convert to Central Time
                last_heartbeat_ct = last_heartbeat.astimezone(CENTRAL_TZ)
            else:
                last_heartbeat_ct = None

            return {
                'last_scan': last_heartbeat_ct.strftime('%Y-%m-%d %H:%M:%S CT') if last_heartbeat_ct else None,
                'last_scan_iso': last_heartbeat_ct.isoformat() if last_heartbeat_ct else None,
                'status': status,
                'scan_count_today': scan_count or 0,
                'details': details or {}
            }
        return {
            'last_scan': None,
            'last_scan_iso': None,
            'status': 'NEVER_RUN',
            'scan_count_today': 0,
            'details': {}
        }
    except Exception as e:
        logger.debug(f"Could not get heartbeat for {bot_name}: {e}")
        return {
            'last_scan': None,
            'last_scan_iso': None,
            'status': 'UNKNOWN',
            'scan_count_today': 0,
            'details': {}
        }


@router.get("/status")
async def get_athena_status():
    """
    Get current ATHENA bot status.

    Returns mode, capital, P&L, positions, configuration, and heartbeat.
    """
    athena = get_athena_instance()

    # Get heartbeat info
    heartbeat = _get_heartbeat('ATHENA')

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
                "scan_interval_minutes": 5,
                "heartbeat": heartbeat,
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
        status['scan_interval_minutes'] = 5
        status['heartbeat'] = heartbeat

        return {
            "success": True,
            "data": status
        }
    except Exception as e:
        logger.error(f"Error getting ATHENA status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _calculate_position_greeks(long_strike: float, short_strike: float, spot: float, vix: float = 15) -> dict:
    """Calculate simplified Greeks for a spread position."""
    try:
        # Long leg Greeks (ATM-ish)
        long_moneyness = (spot - long_strike) / spot if spot > 0 else 0
        long_delta = 0.5 + (long_moneyness * 2)
        long_delta = max(-1, min(1, long_delta))

        # Short leg Greeks (OTM)
        short_moneyness = (spot - short_strike) / spot if spot > 0 else 0
        short_delta = 0.5 + (short_moneyness * 2)
        short_delta = max(-1, min(1, short_delta))

        # Net Greeks
        net_delta = long_delta - short_delta
        net_gamma = 0.05 - 0.03  # Long gamma - short gamma
        net_theta = (-0.10 * vix / 20) - (-0.08 * vix / 20)  # Long theta - short theta

        return {
            "net_delta": round(net_delta, 3),
            "net_gamma": round(net_gamma, 3),
            "net_theta": round(net_theta, 3),
            "long_delta": round(long_delta, 3),
            "short_delta": round(short_delta, 3)
        }
    except Exception:
        return {"net_delta": 0, "net_gamma": 0, "net_theta": 0, "long_delta": 0, "short_delta": 0}


@router.get("/positions")
async def get_athena_positions(
    status_filter: Optional[str] = Query(None, description="Filter by status: open, closed, all"),
    limit: int = Query(50, description="Max positions to return")
):
    """
    Get ATHENA positions from database.

    Returns open and/or closed positions with P&L details, Greeks, and market context.
    """
    try:
        conn = get_connection()
        c = conn.cursor()

        where_clause = ""
        if status_filter == "open":
            where_clause = "WHERE status = 'open'"
        elif status_filter == "closed":
            where_clause = "WHERE status IN ('closed', 'expired')"

        # Check if new columns exist (migration 010)
        c.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'apache_positions' AND column_name = 'vix_at_entry'
        """)
        has_new_columns = c.fetchone() is not None

        if has_new_columns:
            # Full query with all new columns
            c.execute(f"""
                SELECT
                    position_id, spread_type, ticker,
                    long_strike, short_strike, expiration,
                    entry_price, contracts, max_profit, max_loss,
                    spot_at_entry, gex_regime, oracle_confidence,
                    status, exit_price, exit_reason, realized_pnl,
                    created_at, exit_time, oracle_reasoning,
                    vix_at_entry, put_wall_at_entry, call_wall_at_entry,
                    flip_point_at_entry, net_gex_at_entry,
                    entry_delta, entry_gamma, entry_theta, entry_vega,
                    ml_direction, ml_confidence, ml_win_probability,
                    breakeven, rr_ratio
                FROM apache_positions
                {where_clause}
                ORDER BY created_at DESC
                LIMIT %s
            """, (limit,))
        else:
            # Legacy query without new columns (pre-migration)
            c.execute(f"""
                SELECT
                    position_id, spread_type, ticker,
                    long_strike, short_strike, expiration,
                    entry_price, contracts, max_profit, max_loss,
                    spot_at_entry, gex_regime, oracle_confidence,
                    status, exit_price, exit_reason, realized_pnl,
                    created_at, exit_time, oracle_reasoning
                FROM apache_positions
                {where_clause}
                ORDER BY created_at DESC
                LIMIT %s
            """, (limit,))

        rows = c.fetchall()
        conn.close()

        positions = []
        for row in rows:
            long_strike = float(row[3]) if row[3] else 0
            short_strike = float(row[4]) if row[4] else 0
            spot_at_entry = float(row[10]) if row[10] else 0
            entry_price = float(row[6]) if row[6] else 0
            spread_width = abs(short_strike - long_strike)

            # Use stored Greeks if available (new schema), otherwise calculate
            if has_new_columns and len(row) > 25:
                stored_delta = row[25]
                stored_gamma = row[26]
                stored_theta = row[27]
                stored_vega = row[28]

                if stored_delta is not None:
                    greeks = {
                        "net_delta": round(float(stored_delta), 3),
                        "net_gamma": round(float(stored_gamma), 3) if stored_gamma else 0,
                        "net_theta": round(float(stored_theta), 3) if stored_theta else 0,
                        "net_vega": round(float(stored_vega), 3) if stored_vega else 0,
                        "long_delta": 0,
                        "short_delta": 0
                    }
                else:
                    greeks = _calculate_position_greeks(long_strike, short_strike, spot_at_entry)
            else:
                # Fallback to calculated Greeks for older schema
                greeks = _calculate_position_greeks(long_strike, short_strike, spot_at_entry)

            # Use stored breakeven if available, otherwise calculate
            if has_new_columns and len(row) > 32:
                stored_breakeven = row[32]
                if stored_breakeven:
                    breakeven = float(stored_breakeven)
                else:
                    spread_type_str = row[1] or ""
                    is_bullish = "BULL" in spread_type_str.upper()
                    breakeven = long_strike + entry_price if is_bullish else short_strike - abs(entry_price)
            else:
                spread_type_str = row[1] or ""
                is_bullish = "BULL" in spread_type_str.upper()
                breakeven = long_strike + entry_price if is_bullish else short_strike - abs(entry_price)

            # Calculate time info
            expiration = str(row[5]) if row[5] else None
            is_0dte = False
            if expiration:
                from datetime import datetime
                try:
                    exp_date = datetime.strptime(expiration, "%Y-%m-%d").date()
                    created_at = row[17]
                    if created_at:
                        is_0dte = exp_date == created_at.date()
                except:
                    pass

            position_data = {
                "position_id": row[0],
                "spread_type": row[1],
                "ticker": row[2],
                "long_strike": long_strike,
                "short_strike": short_strike,
                "spread_width": spread_width,
                "expiration": expiration,
                "is_0dte": is_0dte,
                "entry_price": entry_price,
                "contracts": row[7],
                "max_profit": float(row[8]) if row[8] else 0,
                "max_loss": float(row[9]) if row[9] else 0,
                "breakeven": round(breakeven, 2),
                "spot_at_entry": spot_at_entry,
                "gex_regime": row[11],
                "oracle_confidence": float(row[12]) if row[12] else 0,
                "oracle_reasoning": row[19][:200] if row[19] else None,
                "greeks": greeks,
                "status": row[13],
                "exit_price": float(row[14]) if row[14] else 0,
                "exit_reason": row[15],
                "realized_pnl": float(row[16]) if row[16] else 0,
                "created_at": row[17].isoformat() if row[17] else None,
                "exit_time": row[18].isoformat() if row[18] else None,
            }

            # Add new fields if available
            if has_new_columns and len(row) > 33:
                position_data.update({
                    "vix_at_entry": float(row[20]) if row[20] else None,
                    "put_wall_at_entry": float(row[21]) if row[21] else None,
                    "call_wall_at_entry": float(row[22]) if row[22] else None,
                    "flip_point_at_entry": float(row[23]) if row[23] else None,
                    "net_gex_at_entry": float(row[24]) if row[24] else None,
                    "ml_direction": row[29],
                    "ml_confidence": float(row[30]) if row[30] else None,
                    "ml_win_probability": float(row[31]) if row[31] else None,
                    "rr_ratio": float(row[33]) if row[33] else None
                })

            positions.append(position_data)

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


@router.get("/decisions")
async def get_athena_decisions(
    limit: int = Query(100, description="Max decisions to return"),
    start_date: Optional[str] = Query(None, description="Filter from date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="Filter to date (YYYY-MM-DD)"),
    decision_type: Optional[str] = Query(None, description="Filter by type: ENTRY_SIGNAL, NO_TRADE, EXIT_SIGNAL")
):
    """
    Get ATHENA decision logs with full audit trail.

    Returns comprehensive decision data including:
    - Oracle/ML advice with win probability and confidence
    - GEX context (walls, flip point, regime)
    - Trade legs with strikes, prices, Greeks
    - Position sizing breakdown
    - Alternatives considered
    - Risk checks performed
    """
    if not DECISION_LOGGER_AVAILABLE or not export_decisions_json:
        raise HTTPException(
            status_code=503,
            detail="Decision logger not available"
        )

    try:
        decisions = export_decisions_json(
            bot_name="ATHENA",
            start_date=start_date,
            end_date=end_date,
            decision_type=decision_type,
            limit=limit
        )

        return {
            "success": True,
            "data": decisions,
            "count": len(decisions)
        }

    except Exception as e:
        logger.error(f"Error getting ATHENA decisions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/live-pnl")
async def get_athena_live_pnl():
    """
    Get real-time unrealized P&L for all open ATHENA positions.

    Returns:
    - total_unrealized_pnl: Sum of all open position unrealized P&L
    - total_realized_pnl: Today's realized P&L from closed positions
    - net_pnl: Total (unrealized + realized)
    - positions: List of position details with current P&L
    - underlying_price: Current SPY price
    """
    athena = get_athena_instance()

    if not athena:
        return {
            "success": True,
            "data": {
                "total_unrealized_pnl": 0,
                "total_realized_pnl": 0,
                "net_pnl": 0,
                "positions": [],
                "position_count": 0,
                "message": "ATHENA not initialized"
            }
        }

    try:
        live_pnl = athena.get_live_pnl()

        return {
            "success": True,
            "data": live_pnl
        }
    except Exception as e:
        logger.error(f"Error getting ATHENA live P&L: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/process-expired")
async def process_athena_expired_positions():
    """
    Manually trigger processing of all expired ATHENA positions.

    This will process any positions that have expired but weren't processed
    due to service downtime or errors. Useful for catching up after outages.

    Processes positions where expiration <= today and status = 'open'.
    """
    athena = get_athena_instance()

    if not athena:
        raise HTTPException(
            status_code=503,
            detail="ATHENA not initialized. Wait for scheduled startup."
        )

    try:
        result = athena.process_expired_positions()

        return {
            "success": True,
            "data": result,
            "message": f"Processed {result.get('processed_count', 0)} expired positions"
        }
    except Exception as e:
        logger.error(f"Error processing expired positions: {e}")
        raise HTTPException(status_code=500, detail=str(e))
