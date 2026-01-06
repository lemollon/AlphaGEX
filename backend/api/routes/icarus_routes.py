"""
ICARUS Aggressive Directional Spread Bot API Routes
=====================================================

API endpoints for the ICARUS aggressive directional spread trading bot.
ICARUS is an aggressive clone of ATHENA with relaxed GEX wall filters.

Key differences from ATHENA:
- 10% wall filter (vs 3%)
- 40% min win probability (vs 48%)
- 4% risk per trade (vs 2%)
- 10 max daily trades (vs 5)
- 5 max open positions (vs 3)
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query, Depends, Request
from zoneinfo import ZoneInfo

from database_adapter import get_connection

# Authentication middleware
try:
    from backend.api.auth_middleware import require_api_key, require_admin, optional_auth, AuthInfo
    AUTH_AVAILABLE = True
except ImportError:
    AUTH_AVAILABLE = False
    require_api_key = None
    require_admin = None

router = APIRouter(prefix="/api/icarus", tags=["ICARUS"])
logger = logging.getLogger(__name__)

CENTRAL_TZ = ZoneInfo("America/Chicago")

# Flag to track if database schema has been initialized
_schema_initialized = False


def _ensure_icarus_schema():
    """Ensure ICARUS database tables and columns exist before queries"""
    global _schema_initialized
    if _schema_initialized:
        return

    conn = None
    try:
        conn = get_connection()
        c = conn.cursor()

        # Create main positions table if not exists
        c.execute("""
            CREATE TABLE IF NOT EXISTS icarus_positions (
                id SERIAL PRIMARY KEY,
                position_id VARCHAR(50) UNIQUE NOT NULL,
                spread_type VARCHAR(30) NOT NULL,
                ticker VARCHAR(10) NOT NULL,
                long_strike DECIMAL(10, 2) NOT NULL,
                short_strike DECIMAL(10, 2) NOT NULL,
                expiration DATE NOT NULL,
                entry_debit DECIMAL(10, 4) NOT NULL,
                contracts INTEGER NOT NULL,
                max_profit DECIMAL(10, 2) NOT NULL,
                max_loss DECIMAL(10, 2) NOT NULL,
                underlying_at_entry DECIMAL(10, 2) NOT NULL,
                call_wall DECIMAL(10, 2),
                put_wall DECIMAL(10, 2),
                gex_regime VARCHAR(30),
                vix_at_entry DECIMAL(6, 2),
                oracle_confidence DECIMAL(5, 4),
                ml_direction VARCHAR(20),
                ml_confidence DECIMAL(5, 4),
                order_id VARCHAR(50),
                status VARCHAR(20) NOT NULL DEFAULT 'open',
                open_time TIMESTAMP WITH TIME ZONE NOT NULL,
                close_time TIMESTAMP WITH TIME ZONE,
                close_price DECIMAL(10, 4),
                close_reason VARCHAR(100),
                realized_pnl DECIMAL(10, 2),
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        """)

        # Add ML context columns if they don't exist (migration)
        columns_to_add = [
            ("flip_point", "DECIMAL(10, 2)"),
            ("net_gex", "DECIMAL(15, 2)"),
            ("ml_model_name", "VARCHAR(100)"),
            ("ml_win_probability", "DECIMAL(8, 4)"),
            ("ml_top_features", "TEXT"),
            ("wall_type", "VARCHAR(20)"),
            ("wall_distance_pct", "DECIMAL(6, 4)"),
            ("trade_reasoning", "TEXT"),
        ]

        for col_name, col_type in columns_to_add:
            try:
                c.execute(f"ALTER TABLE icarus_positions ADD COLUMN IF NOT EXISTS {col_name} {col_type}")
            except Exception:
                pass  # Column might already exist

        # Create signals table
        c.execute("""
            CREATE TABLE IF NOT EXISTS icarus_signals (
                id SERIAL PRIMARY KEY,
                signal_time TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                direction VARCHAR(20) NOT NULL,
                spread_type VARCHAR(30),
                confidence DECIMAL(5, 4),
                spot_price DECIMAL(10, 2),
                call_wall DECIMAL(10, 2),
                put_wall DECIMAL(10, 2),
                gex_regime VARCHAR(30),
                vix DECIMAL(6, 2),
                rr_ratio DECIMAL(6, 2),
                was_executed BOOLEAN DEFAULT FALSE,
                skip_reason VARCHAR(200),
                reasoning TEXT
            )
        """)

        # Create logs table
        c.execute("""
            CREATE TABLE IF NOT EXISTS icarus_logs (
                id SERIAL PRIMARY KEY,
                log_time TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                level VARCHAR(10),
                message TEXT,
                details JSONB
            )
        """)

        # Create daily performance table
        c.execute("""
            CREATE TABLE IF NOT EXISTS icarus_daily_perf (
                id SERIAL PRIMARY KEY,
                trade_date DATE UNIQUE NOT NULL,
                trades_executed INTEGER DEFAULT 0,
                positions_closed INTEGER DEFAULT 0,
                realized_pnl DECIMAL(10, 2) DEFAULT 0,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        """)

        conn.commit()
        _schema_initialized = True
        logger.info("ICARUS database schema initialized")
    except Exception as e:
        logger.warning(f"Could not initialize ICARUS schema: {e}")
    finally:
        if conn:
            conn.close()


def _resolve_query_param(param, default=None):
    """Resolve a FastAPI Query parameter to its actual value."""
    if param is None:
        return default
    if hasattr(param, 'default'):
        return param.default if param.default is not None else default
    return param


# Try to import ICARUS trader
icarus_trader = None
try:
    from trading.icarus import ICARUSTrader, ICARUSConfig, TradingMode
    ICARUS_AVAILABLE = True
except ImportError as e:
    ICARUS_AVAILABLE = False
    ICARUSConfig = None
    logger.warning(f"ICARUS module not available: {e}")


def get_icarus_instance():
    """Get the ICARUS trader instance"""
    global icarus_trader
    if icarus_trader:
        return icarus_trader

    try:
        # Try to get from scheduler first
        from scheduler.trader_scheduler import get_icarus_trader
        icarus_trader = get_icarus_trader()
        if icarus_trader:
            return icarus_trader
    except ImportError as e:
        logger.debug(f"Could not import trader_scheduler: {e}")
    except Exception as e:
        logger.debug(f"Could not get ICARUS from scheduler: {e}")

    # Initialize a new instance if needed
    if ICARUS_AVAILABLE and ICARUSConfig:
        try:
            config = ICARUSConfig(mode=TradingMode.PAPER)
            icarus_trader = ICARUSTrader(config=config)
            return icarus_trader
        except Exception as e:
            logger.error(f"Failed to initialize ICARUS: {e}")

    return None


def _get_heartbeat(bot_name: str) -> dict:
    """Get heartbeat info for a bot from the database"""
    conn = None

    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT last_heartbeat, status, scan_count, details
            FROM bot_heartbeats
            WHERE bot_name = %s
        ''', (bot_name,))

        row = cursor.fetchone()

        if row:
            last_heartbeat, status, scan_count, details = row

            if last_heartbeat:
                if last_heartbeat.tzinfo is None:
                    last_heartbeat = last_heartbeat.replace(tzinfo=ZoneInfo("UTC"))
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
    finally:
        if conn:
            conn.close()


def _is_bot_actually_active(heartbeat: dict, scan_interval_minutes: int = 5) -> tuple[bool, str]:
    """Determine if a bot is actually active based on heartbeat."""
    status = heartbeat.get('status', 'UNKNOWN')

    inactive_statuses = {
        'UNAVAILABLE': 'Trader not initialized',
        'ERROR': 'Encountered an error',
        'KILLED': 'Stopped by kill switch',
        'NEVER_RUN': 'Has never run',
        'UNKNOWN': 'Status unknown'
    }

    if status in inactive_statuses:
        return False, inactive_statuses[status]

    last_scan_iso = heartbeat.get('last_scan_iso')
    if not last_scan_iso:
        return False, 'No heartbeat recorded'

    try:
        last_scan_time = datetime.fromisoformat(last_scan_iso)
        now = datetime.now(last_scan_time.tzinfo)
        age_seconds = (now - last_scan_time).total_seconds()
        max_age_seconds = scan_interval_minutes * 60 * 2
        if age_seconds > max_age_seconds:
            return False, f'Heartbeat stale ({int(age_seconds)}s old)'
    except Exception as e:
        logger.warning(f"Error parsing heartbeat time: {e}")

    if status in ('SCAN_COMPLETE', 'TRADED', 'MARKET_CLOSED', 'BEFORE_WINDOW', 'AFTER_WINDOW'):
        return True, f'Running ({status})'

    return True, f'Running ({status})'


@router.get("/status")
async def get_icarus_status():
    """
    Get current ICARUS bot status.

    Returns mode, capital, P&L, positions, configuration, and heartbeat.
    """
    # Ensure database schema exists before querying
    _ensure_icarus_schema()

    icarus = get_icarus_instance()
    heartbeat = _get_heartbeat('ICARUS')

    now = datetime.now(CENTRAL_TZ)
    current_time_str = now.strftime('%Y-%m-%d %H:%M:%S CT')

    # ICARUS trading window: 8:35 AM - 2:30 PM CT (same as ATHENA)
    entry_start = "08:35"
    entry_end = "14:30"

    if now.month == 12 and now.day == 24:
        entry_end = "11:00"  # Christmas Eve early close

    start_parts = entry_start.split(':')
    end_parts = entry_end.split(':')
    start_time = now.replace(hour=int(start_parts[0]), minute=int(start_parts[1]), second=0, microsecond=0)
    end_time = now.replace(hour=int(end_parts[0]), minute=int(end_parts[1]), second=0, microsecond=0)

    is_weekday = now.weekday() < 5
    in_window = is_weekday and start_time <= now <= end_time
    trading_window_status = "OPEN" if in_window else "CLOSED"

    if not icarus:
        # ICARUS not running - read stats from database
        total_pnl = 0
        trade_count = 0
        win_count = 0
        open_count = 0
        closed_count = 0
        traded_today = False
        today = now.strftime('%Y-%m-%d')

        try:
            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute('''
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 'open' THEN 1 ELSE 0 END) as open_count,
                    SUM(CASE WHEN status IN ('closed', 'expired') THEN 1 ELSE 0 END) as closed_count,
                    SUM(CASE WHEN status IN ('closed', 'expired') AND realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
                    COALESCE(SUM(CASE WHEN status IN ('closed', 'expired') THEN realized_pnl ELSE 0 END), 0) as total_pnl,
                    SUM(CASE WHEN DATE(created_at) = %s THEN 1 ELSE 0 END) as traded_today
                FROM icarus_positions
            ''', (today,))
            row = cursor.fetchone()

            if row:
                trade_count = row[0] or 0
                open_count = row[1] or 0
                closed_count = row[2] or 0
                win_count = row[3] or 0
                total_pnl = float(row[4] or 0)
                traded_today = (row[5] or 0) > 0

            conn.close()
        except Exception as db_err:
            logger.debug(f"Could not read ICARUS stats from database: {db_err}")

        win_rate = round((win_count / closed_count) * 100, 1) if closed_count > 0 else 0
        scan_interval = 5
        is_active, active_reason = _is_bot_actually_active(heartbeat, scan_interval)

        return {
            "success": True,
            "data": {
                "mode": "paper",
                "ticker": "SPY",
                "capital": 100000,
                "total_pnl": round(total_pnl, 2),
                "trade_count": trade_count,
                "win_rate": win_rate,
                "open_positions": open_count,
                "closed_positions": closed_count,
                "traded_today": traded_today,
                "daily_trades": 0,
                "daily_pnl": 0,
                "in_trading_window": in_window,
                "trading_window_status": trading_window_status,
                "trading_window_end": entry_end,
                "current_time": current_time_str,
                "is_active": is_active,
                "active_reason": active_reason,
                "scan_interval_minutes": scan_interval,
                "heartbeat": heartbeat,
                "oracle_available": False,
                "gex_ml_available": False,
                "config": {
                    "risk_per_trade": 4.0,
                    "spread_width": 3,
                    "wall_filter_pct": 10.0,
                    "ticker": "SPY",
                    "max_daily_trades": 10,
                    "max_open_positions": 5,
                    "min_win_probability": 0.40,
                    "profit_target_pct": 30.0,
                    "stop_loss_pct": 70.0
                },
                "message": "ICARUS reading from database"
            }
        }

    try:
        status = icarus.get_status()
        scan_interval = 5
        is_active, active_reason = _is_bot_actually_active(heartbeat, scan_interval)
        status['is_active'] = is_active
        status['active_reason'] = active_reason
        status['scan_interval_minutes'] = scan_interval
        status['heartbeat'] = heartbeat
        status['in_trading_window'] = in_window
        status['trading_window_status'] = trading_window_status
        status['trading_window_end'] = entry_end
        status['current_time'] = current_time_str

        if 'capital' not in status:
            status['capital'] = 100000
        if 'total_pnl' not in status:
            status['total_pnl'] = 0

        return {
            "success": True,
            "data": status
        }
    except Exception as e:
        logger.error(f"Error getting ICARUS status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/positions")
async def get_icarus_positions(
    status_filter: Optional[str] = Query(None, description="Filter by status: open, closed, all"),
    limit: int = Query(500, description="Max positions to return")
):
    """Get ICARUS positions from database."""
    # Ensure database schema exists before querying
    _ensure_icarus_schema()

    status_filter = _resolve_query_param(status_filter, None)
    limit = _resolve_query_param(limit, 500)

    try:
        conn = get_connection()
        c = conn.cursor()

        where_clause = ""
        if status_filter == "open":
            where_clause = "WHERE status = 'open'"
        elif status_filter == "closed":
            where_clause = "WHERE status IN ('closed', 'expired')"

        c.execute(f"""
            SELECT
                position_id, spread_type, ticker,
                long_strike, short_strike, expiration,
                entry_debit, contracts, max_profit, max_loss,
                underlying_at_entry, call_wall, put_wall,
                gex_regime, vix_at_entry,
                oracle_confidence, ml_direction, ml_confidence,
                status, close_price, close_reason, realized_pnl,
                open_time, close_time,
                wall_type, wall_distance_pct, trade_reasoning
            FROM icarus_positions
            {where_clause}
            ORDER BY open_time DESC
            LIMIT %s
        """, (limit,))

        rows = c.fetchall()
        conn.close()

        positions = []
        for row in rows:
            long_strike = float(row[3]) if row[3] else 0
            short_strike = float(row[4]) if row[4] else 0
            entry_debit = float(row[6]) if row[6] else 0
            spread_width = abs(short_strike - long_strike)

            spread_type_str = row[1] or ""
            is_call = "CALL" in spread_type_str.upper()
            is_bullish = "BULL" in spread_type_str.upper()
            strike_suffix = "C" if is_call else "P"

            if is_bullish:
                spread_formatted = f"{long_strike}/{short_strike}{strike_suffix}"
            else:
                spread_formatted = f"{short_strike}/{long_strike}{strike_suffix}"

            max_profit_val = float(row[8]) if row[8] else 0
            realized_pnl = float(row[21]) if row[21] else 0
            return_pct = round((realized_pnl / max_profit_val) * 100, 1) if max_profit_val and realized_pnl else 0

            # Calculate is_0dte (same as ATHENA)
            expiration = str(row[5]) if row[5] else None
            is_0dte = False
            if expiration:
                try:
                    exp_date = datetime.strptime(expiration, "%Y-%m-%d").date()
                    open_time = row[22]
                    if open_time:
                        is_0dte = exp_date == open_time.date()
                except (ValueError, TypeError, AttributeError):
                    pass  # Keep default is_0dte=False if date parsing fails

            position_data = {
                "position_id": row[0],
                "spread_type": row[1],
                "ticker": row[2],
                "long_strike": long_strike,
                "short_strike": short_strike,
                "spread_formatted": spread_formatted,
                "spread_width": spread_width,
                "expiration": expiration,
                "is_0dte": is_0dte,
                "entry_price": entry_debit,  # Match ATHENA's field name
                "entry_debit": entry_debit,  # Keep for backward compat
                "contracts": row[7],
                "max_profit": max_profit_val,
                "max_loss": float(row[9]) if row[9] else 0,
                "spot_at_entry": float(row[10]) if row[10] else 0,  # Match ATHENA's field name
                "underlying_at_entry": float(row[10]) if row[10] else 0,  # Keep for backward compat
                "call_wall": float(row[11]) if row[11] else 0,
                "put_wall": float(row[12]) if row[12] else 0,
                "gex_regime": row[13],
                "vix_at_entry": float(row[14]) if row[14] else 0,
                "oracle_confidence": float(row[15]) if row[15] else 0,
                "ml_direction": row[16],
                "ml_confidence": float(row[17]) if row[17] else 0,
                "status": row[18],
                "exit_price": float(row[19]) if row[19] else 0,  # Match ATHENA's field name
                "close_price": float(row[19]) if row[19] else 0,  # Keep for backward compat
                "exit_reason": row[20],  # Match ATHENA's field name
                "close_reason": row[20],  # Keep for backward compat
                "realized_pnl": realized_pnl,
                "return_pct": return_pct,
                "created_at": row[22].isoformat() if row[22] else None,  # Match ATHENA's field name
                "open_time": row[22].isoformat() if row[22] else None,  # Keep for backward compat
                "exit_time": row[23].isoformat() if row[23] else None,  # Match ATHENA's field name
                "close_time": row[23].isoformat() if row[23] else None,  # Keep for backward compat
                "wall_type": row[24],
                "wall_distance_pct": float(row[25]) if row[25] else 0,
                "trade_reasoning": row[26]
            }

            positions.append(position_data)

        return {
            "success": True,
            "data": positions,
            "count": len(positions)
        }

    except Exception as e:
        logger.error(f"Error getting ICARUS positions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/positions/closed")
async def get_icarus_closed_positions(
    limit: int = Query(100, description="Max positions to return")
):
    """Get closed ICARUS positions."""
    return await get_icarus_positions(status_filter="closed", limit=limit)


@router.get("/signals")
async def get_icarus_signals(
    limit: int = Query(50, description="Max signals to return")
):
    """Get ICARUS signals from database."""
    _ensure_icarus_schema()

    try:
        conn = get_connection()
        c = conn.cursor()

        c.execute("""
            SELECT
                id, signal_time, direction, spread_type,
                confidence, spot_price, call_wall, put_wall,
                gex_regime, vix, rr_ratio,
                was_executed, skip_reason, reasoning
            FROM icarus_signals
            ORDER BY signal_time DESC
            LIMIT %s
        """, (limit,))

        rows = c.fetchall()
        conn.close()

        signals = []
        for row in rows:
            signals.append({
                "id": row[0],
                "signal_time": row[1].isoformat() if row[1] else None,
                "direction": row[2],
                "spread_type": row[3],
                "confidence": float(row[4]) if row[4] else 0,
                "spot_price": float(row[5]) if row[5] else 0,
                "call_wall": float(row[6]) if row[6] else 0,
                "put_wall": float(row[7]) if row[7] else 0,
                "gex_regime": row[8],
                "vix": float(row[9]) if row[9] else 0,
                "rr_ratio": float(row[10]) if row[10] else 0,
                "was_executed": row[11],
                "skip_reason": row[12],
                "reasoning": row[13]
            })

        return {
            "success": True,
            "data": signals,
            "count": len(signals)
        }

    except Exception as e:
        logger.error(f"Error getting ICARUS signals: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/logs")
async def get_icarus_logs(
    level: Optional[str] = Query(None, description="Filter by level"),
    limit: int = Query(100, description="Max logs to return")
):
    """Get ICARUS logs."""
    _ensure_icarus_schema()

    level = _resolve_query_param(level, None)
    limit = _resolve_query_param(limit, 100)

    try:
        conn = get_connection()
        c = conn.cursor()

        where_clause = ""
        params = [limit]
        if level:
            where_clause = "WHERE level = %s"
            params = [level, limit]

        c.execute(f"""
            SELECT id, log_time, level, message, details
            FROM icarus_logs
            {where_clause}
            ORDER BY log_time DESC
            LIMIT %s
        """, tuple(params))

        rows = c.fetchall()
        conn.close()

        logs = []
        for row in rows:
            logs.append({
                "id": row[0],
                "log_time": row[1].isoformat() if row[1] else None,
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
        logger.error(f"Error getting ICARUS logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/performance")
async def get_icarus_performance(
    days: int = Query(30, description="Number of days to include")
):
    """Get ICARUS performance metrics over time."""
    _ensure_icarus_schema()

    try:
        conn = get_connection()
        c = conn.cursor()

        # Get daily performance from positions
        c.execute("""
            SELECT
                DATE(open_time AT TIME ZONE 'America/Chicago') as trade_date,
                COUNT(*) as trades,
                SUM(CASE WHEN status IN ('closed', 'expired') AND realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN status IN ('closed', 'expired') AND realized_pnl <= 0 THEN 1 ELSE 0 END) as losses,
                COALESCE(SUM(realized_pnl), 0) as total_pnl
            FROM icarus_positions
            WHERE DATE(open_time AT TIME ZONE 'America/Chicago') >= CURRENT_DATE - INTERVAL '%s days'
            GROUP BY DATE(open_time AT TIME ZONE 'America/Chicago')
            ORDER BY trade_date DESC
        """, (days,))

        rows = c.fetchall()

        # Calculate summary stats
        c.execute("""
            SELECT
                COUNT(*) as total_trades,
                SUM(CASE WHEN status IN ('closed', 'expired') AND realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
                COALESCE(SUM(realized_pnl), 0) as total_pnl
            FROM icarus_positions
            WHERE DATE(open_time AT TIME ZONE 'America/Chicago') >= CURRENT_DATE - INTERVAL '%s days'
        """, (days,))

        summary_row = c.fetchone()
        conn.close()

        daily_data = []
        for row in rows:
            trades = row[1] or 0
            wins = row[2] or 0
            win_rate = round((wins / trades) * 100, 1) if trades > 0 else 0

            daily_data.append({
                "date": str(row[0]),
                "trades": trades,
                "wins": wins,
                "losses": row[3] or 0,
                "win_rate": win_rate,
                "pnl": float(row[4]) if row[4] else 0
            })

        total_trades = summary_row[0] if summary_row else 0
        total_wins = summary_row[1] if summary_row else 0
        avg_win_rate = round((total_wins / total_trades) * 100, 1) if total_trades > 0 else 0

        return {
            "success": True,
            "data": {
                "summary": {
                    "total_trades": total_trades,
                    "total_wins": total_wins,
                    "total_pnl": float(summary_row[2]) if summary_row and summary_row[2] else 0,
                    "avg_win_rate": avg_win_rate
                },
                "daily": daily_data
            }
        }

    except Exception as e:
        logger.error(f"Error getting ICARUS performance: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/config")
async def get_icarus_config():
    """Get ICARUS configuration settings."""
    # ICARUS aggressive configuration
    default_config = {
        "risk_per_trade": {"value": "4.0", "description": "Risk per trade (4% - aggressive)"},
        "spread_width": {"value": "3", "description": "Width of spread in strikes ($3)"},
        "max_daily_trades": {"value": "10", "description": "Maximum trades per day (aggressive)"},
        "max_open_positions": {"value": "5", "description": "Maximum concurrent positions"},
        "ticker": {"value": "SPY", "description": "Trading ticker symbol"},
        "wall_filter_pct": {"value": "10.0", "description": "GEX wall filter (10% - most relaxed)"},
        "min_win_probability": {"value": "0.40", "description": "Minimum Oracle win probability (40%)"},
        "min_rr_ratio": {"value": "0.5", "description": "Minimum risk:reward ratio"},
        "stop_loss_pct": {"value": "70", "description": "Stop loss percentage (wider stops)"},
        "profit_target_pct": {"value": "30", "description": "Take profit percentage (earlier exits)"},
        "entry_start_time": {"value": "08:35", "description": "Trading window start time CT"},
        "entry_end_time": {"value": "14:30", "description": "Trading window end time CT"},
    }

    return {
        "success": True,
        "data": default_config,
        "source": "defaults"
    }


@router.post("/run")
async def run_icarus_cycle(
    request: Request,
    auth: AuthInfo = Depends(require_admin) if AUTH_AVAILABLE and require_admin else None
):
    """Manually trigger an ICARUS trading cycle."""
    icarus = get_icarus_instance()

    if not icarus:
        raise HTTPException(status_code=503, detail="ICARUS not available")

    try:
        result = icarus.run_cycle()
        return {
            "success": True,
            "data": result
        }
    except Exception as e:
        logger.error(f"Error running ICARUS cycle: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/skip-today")
async def skip_icarus_today(
    request: Request,
    auth: AuthInfo = Depends(require_api_key) if AUTH_AVAILABLE and require_api_key else None
):
    """Skip trading for the rest of today."""
    icarus = get_icarus_instance()

    if not icarus:
        raise HTTPException(status_code=503, detail="ICARUS not initialized")

    try:
        today = datetime.now(CENTRAL_TZ).date()
        icarus.skip_date = today

        return {
            "success": True,
            "message": f"ICARUS will skip trading for {today.isoformat()}",
            "data": {"skip_date": today.isoformat()}
        }
    except Exception as e:
        logger.error(f"Error setting skip date: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/oracle-advice")
async def get_current_oracle_advice():
    """Get current Oracle advice for ICARUS."""
    icarus = get_icarus_instance()

    if not icarus:
        raise HTTPException(status_code=503, detail="ICARUS not available")

    try:
        advice = icarus.get_oracle_advice()

        if not advice:
            return {
                "success": True,
                "data": None,
                "message": "No Oracle advice available"
            }

        return {
            "success": True,
            "data": advice
        }
    except Exception as e:
        logger.error(f"Error getting Oracle advice: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/live-pnl")
async def get_icarus_live_pnl():
    """Get live P&L for open positions."""
    icarus = get_icarus_instance()

    if not icarus:
        raise HTTPException(status_code=503, detail="ICARUS not available")

    try:
        pnl_data = icarus.get_live_pnl()
        return {
            "success": True,
            "data": pnl_data
        }
    except Exception as e:
        logger.error(f"Error getting live P&L: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reset")
async def reset_icarus_data(
    request: Request,
    auth: AuthInfo = Depends(require_admin) if AUTH_AVAILABLE and require_admin else None
):
    """Reset all ICARUS data (positions, signals, logs)."""
    _ensure_icarus_schema()

    try:
        conn = get_connection()
        c = conn.cursor()

        # Delete all ICARUS data (tables are ensured to exist by _ensure_icarus_schema)
        c.execute("DELETE FROM icarus_positions")
        c.execute("DELETE FROM icarus_signals")
        c.execute("DELETE FROM icarus_logs")
        c.execute("DELETE FROM icarus_daily_perf")

        conn.commit()
        conn.close()

        return {
            "success": True,
            "message": "All ICARUS data has been reset"
        }

    except Exception as e:
        logger.error(f"Error resetting ICARUS data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scan-activity")
async def get_icarus_scan_activity(
    date: str = None,
    outcome: str = None,
    limit: int = Query(50, description="Max scans to return")
):
    """
    Get ICARUS scan activity with full decision context.

    Each scan shows:
    - Market conditions at time of scan
    - ML signals and Oracle advice
    - Risk/Reward ratio analysis
    - GEX regime and wall positions
    - Why trade was/wasn't taken
    - All checks performed

    This is the key endpoint for understanding ICARUS behavior.
    """
    try:
        from trading.scan_activity_logger import get_recent_scans

        scans = get_recent_scans(
            bot_name="ICARUS",
            date=date,
            outcome=outcome.upper() if outcome else None,
            limit=min(limit, 200)
        )

        # Calculate summary stats
        trades = sum(1 for s in scans if s.get('trade_executed'))
        no_trades = sum(1 for s in scans if s.get('outcome') == 'NO_TRADE')
        errors = sum(1 for s in scans if s.get('outcome') == 'ERROR')

        return {
            "success": True,
            "data": {
                "bot_name": "ICARUS",
                "scans": scans,
                "count": len(scans),
                "summary": {
                    "total_scans": len(scans),
                    "trades_executed": trades,
                    "no_trade_scans": no_trades,
                    "error_scans": errors
                }
            }
        }
    except ImportError as e:
        logger.debug(f"Scan activity logger not available: {e}")
        return {
            "success": True,
            "data": {
                "bot_name": "ICARUS",
                "scans": [],
                "count": 0,
                "message": "Scan activity logger not available"
            }
        }
    except Exception as e:
        logger.error(f"Error getting ICARUS scan activity: {e}")
        return {
            "success": True,
            "data": {
                "bot_name": "ICARUS",
                "scans": [],
                "count": 0,
                "message": f"Scan activity error: {str(e)}"
            }
        }


@router.get("/scan-activity/today")
async def get_icarus_scan_activity_today():
    """Get all ICARUS scans from today with summary."""
    today = datetime.now(CENTRAL_TZ).strftime('%Y-%m-%d')
    return await get_icarus_scan_activity(date=today, limit=200)
