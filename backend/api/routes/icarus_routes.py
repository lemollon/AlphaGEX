"""
ICARUS Aggressive Directional Spread Bot API Routes
=====================================================

API endpoints for the ICARUS aggressive directional spread trading bot.
ICARUS uses AGGRESSIVE Apache GEX backtest parameters (vs ATHENA conservative):

Key differences from ATHENA:
- 2% wall filter (vs 1%) - more room to trade
- 48% min win probability (vs 55%) - lower threshold
- 3% risk per trade (vs 2%) - larger positions
- 8 max daily trades (vs 5) - more opportunities
- 4 max open positions (vs 3) - more exposure
- VIX range 12-30 (vs 15-25) - wider volatility range
- GEX ratio 1.3/0.77 (vs 1.5/0.67) - weaker asymmetry allowed
- 1.2 R:R ratio (vs 1.5) - accept slightly lower R:R

Safety filters ARE ENABLED with aggressive thresholds.
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

# Import mark-to-market module for real option pricing
MTM_AVAILABLE = False
try:
    from trading.mark_to_market import (
        calculate_spread_mark_to_market,
        build_occ_symbol,
        get_option_quotes_batch,
        clear_quote_cache
    )
    MTM_AVAILABLE = True
    logger.debug("ICARUS: Mark-to-market module loaded successfully")
except ImportError as e:
    logger.debug(f"ICARUS: Mark-to-market import failed (estimation fallback will be used): {e}")

# Flag to track if database schema has been initialized
_schema_initialized = False


def _calculate_icarus_unrealized_pnl(positions: list, spy_price: float = None) -> dict:
    """
    Calculate unrealized P&L for ICARUS open positions using real option quotes.

    ICARUS trades aggressive directional spreads (Bull Call / Bear Put) on SPY.

    Args:
        positions: List of position tuples from DB query with fields:
                   (position_id, spread_type, entry_debit, contracts,
                    long_strike, short_strike, max_profit, max_loss, expiration)
        spy_price: Current SPY price for estimation fallback

    Returns:
        Dict with total_unrealized_pnl, position_details, and method used
    """
    total_unrealized = 0.0
    position_details = []
    mtm_success_count = 0
    estimation_count = 0

    for pos in positions:
        pos_id, spread_type, entry_debit, contracts, long_strike, short_strike, max_profit, max_loss, expiration = pos
        entry_debit = float(entry_debit or 0)
        contracts = int(contracts or 1)
        long_strike = float(long_strike or 0)
        short_strike = float(short_strike or 0)
        spread_type_upper = (spread_type or '').upper()
        spread_width = abs(short_strike - long_strike)
        # For debit spreads: max_loss = entry_debit * 100, max_profit = (spread_width - entry_debit) * 100
        max_profit = float(max_profit) if max_profit else (spread_width - entry_debit) * 100
        max_loss = float(max_loss) if max_loss else entry_debit * 100

        pos_unrealized = 0.0
        method = 'estimation'

        # Try mark-to-market first using real option quotes
        if MTM_AVAILABLE and expiration:
            try:
                # Format expiration as string
                exp_str = str(expiration) if not isinstance(expiration, str) else expiration

                mtm_result = calculate_spread_mark_to_market(
                    underlying='SPY',
                    expiration=exp_str,
                    long_strike=long_strike,
                    short_strike=short_strike,
                    spread_type=spread_type,  # e.g., 'BULL_CALL', 'BEAR_PUT'
                    contracts=contracts,
                    entry_debit=entry_debit,
                    use_cache=True
                )

                if mtm_result.get('success') and mtm_result.get('unrealized_pnl') is not None:
                    pos_unrealized = mtm_result['unrealized_pnl']
                    method = 'mark_to_market'
                    mtm_success_count += 1
                    logger.debug(f"ICARUS MTM: {pos_id} unrealized=${pos_unrealized:.2f}")
            except Exception as e:
                logger.debug(f"ICARUS MTM failed for {pos_id}: {e}")

        # Fallback to estimation if MTM failed
        if method == 'estimation' and spy_price and spy_price > 0 and long_strike and short_strike:
            estimation_count += 1
            # Calculate current spread value based on type and price
            if 'BULL' in spread_type_upper or 'CALL' in spread_type_upper:
                # Bull spread profits when price goes up
                if spy_price >= short_strike:
                    current_value = spread_width
                elif spy_price <= long_strike:
                    current_value = 0
                else:
                    current_value = max(0, spy_price - long_strike)
            else:
                # Bear spread profits when price goes down
                if spy_price <= short_strike:
                    current_value = spread_width
                elif spy_price >= long_strike:
                    current_value = 0
                else:
                    current_value = max(0, long_strike - spy_price)

            pos_unrealized = (current_value - entry_debit) * 100 * contracts
            # Bound unrealized P&L: max_loss and max_profit are per-contract, scale by contracts
            pos_unrealized = max(-max_loss * contracts, min(max_profit * contracts, pos_unrealized))

        total_unrealized += pos_unrealized
        position_details.append({
            'position_id': pos_id,
            'spread_type': spread_type,
            'unrealized_pnl': round(pos_unrealized, 2),
            'method': method
        })

    return {
        'total_unrealized_pnl': round(total_unrealized, 2),
        'position_details': position_details,
        'mtm_count': mtm_success_count,
        'estimation_count': estimation_count,
        'primary_method': 'mark_to_market' if mtm_success_count > estimation_count else 'estimation'
    }


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
        unrealized_pnl = 0  # Will calculate using MTM if open positions exist
        trade_count = 0
        win_count = 0
        open_count = 0
        closed_count = 0
        traded_today = False
        today = now.strftime('%Y-%m-%d')
        spy_price = None

        # Get current SPY price for MTM estimation fallback
        try:
            from data.unified_data_provider import get_price
            spy_price = get_price("SPY")
        except Exception:
            pass

        try:
            conn = get_connection()
            cursor = conn.cursor()

            # Get trade stats
            cursor.execute('''
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 'open' THEN 1 ELSE 0 END) as open_count,
                    SUM(CASE WHEN status IN ('closed', 'expired', 'partial_close') THEN 1 ELSE 0 END) as closed_count,
                    SUM(CASE WHEN status IN ('closed', 'expired', 'partial_close') AND realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
                    COALESCE(SUM(CASE WHEN status IN ('closed', 'expired', 'partial_close') THEN realized_pnl ELSE 0 END), 0) as total_pnl,
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

            # Calculate unrealized P&L using MTM if there are open positions
            if open_count > 0:
                cursor.execute('''
                    SELECT position_id, spread_type, entry_debit, contracts,
                           long_strike, short_strike, max_profit, max_loss, expiration
                    FROM icarus_positions
                    WHERE status = 'open'
                ''')
                open_positions = cursor.fetchall()
                if open_positions:
                    mtm_result = _calculate_icarus_unrealized_pnl(open_positions, spy_price)
                    unrealized_pnl = mtm_result['total_unrealized_pnl']
                    logger.debug(f"ICARUS status: MTM unrealized=${unrealized_pnl:.2f} via {mtm_result['primary_method']}")

            # Get starting capital from config table (consistent with intraday endpoint)
            starting_capital = 100000  # Default for ICARUS (SPY bot)
            try:
                cursor.execute("SELECT value FROM autonomous_config WHERE key = 'icarus_starting_capital'")
                config_row = cursor.fetchone()
                if config_row and config_row[0]:
                    starting_capital = float(config_row[0])
            except Exception:
                pass

            conn.close()
        except Exception as db_err:
            logger.debug(f"Could not read ICARUS stats from database: {db_err}")
            starting_capital = 100000

        win_rate = round((win_count / closed_count) * 100, 1) if closed_count > 0 else 0
        scan_interval = 5
        is_active, active_reason = _is_bot_actually_active(heartbeat, scan_interval)
        current_equity = starting_capital + total_pnl + unrealized_pnl

        return {
            "success": True,
            "data": {
                "mode": "paper",
                "ticker": "SPY",
                "capital": starting_capital,
                "starting_capital": starting_capital,
                "current_equity": round(current_equity, 2),
                "total_pnl": round(total_pnl, 2),
                # Return None to frontend when live pricing unavailable
                "unrealized_pnl": round(unrealized_pnl, 2) if unrealized_pnl is not None else None,
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
                    "risk_per_trade": 3.0,
                    "spread_width": 3,
                    "wall_filter_pct": 2.0,
                    "ticker": "SPY",
                    "max_daily_trades": 8,
                    "max_open_positions": 4,
                    "min_win_probability": 0.48,
                    "min_confidence": 0.48,
                    "min_rr_ratio": 1.2,
                    "min_vix": 12.0,
                    "max_vix": 30.0,
                    "min_gex_ratio_bearish": 1.3,
                    "max_gex_ratio_bullish": 0.77,
                    "profit_target_pct": 40.0,
                    "stop_loss_pct": 60.0
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

        # CRITICAL FIX: Query database for total realized P&L from closed positions
        # The trader's get_status() doesn't include total_pnl, causing portfolio sync issues
        db_total_pnl = 0
        db_trade_count = 0
        db_win_count = 0
        db_open_count = 0
        db_closed_count = 0
        today = now.strftime('%Y-%m-%d')
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 'open' THEN 1 ELSE 0 END) as open_count,
                    SUM(CASE WHEN status IN ('closed', 'expired', 'partial_close') THEN 1 ELSE 0 END) as closed_count,
                    SUM(CASE WHEN status IN ('closed', 'expired', 'partial_close') AND realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
                    COALESCE(SUM(CASE WHEN status IN ('closed', 'expired', 'partial_close') THEN realized_pnl ELSE 0 END), 0) as total_pnl
                FROM icarus_positions
            ''')
            row = cursor.fetchone()
            conn.close()
            if row:
                db_trade_count = row[0] or 0
                db_open_count = row[1] or 0
                db_closed_count = row[2] or 0
                db_win_count = row[3] or 0
                db_total_pnl = float(row[4] or 0)
        except Exception as db_err:
            logger.debug(f"Could not read ICARUS stats from database: {db_err}")

        # Use database values for accurate P&L tracking
        status['total_pnl'] = db_total_pnl
        status['trade_count'] = db_trade_count
        status['win_rate'] = round((db_win_count / db_closed_count) * 100, 1) if db_closed_count > 0 else 0
        status['open_positions'] = db_open_count
        status['closed_positions'] = db_closed_count

        # Get starting capital from config table (NOT hardcoded)
        starting_capital = 100000  # Default for ICARUS (SPY bot)
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM autonomous_config WHERE key = 'icarus_starting_capital'")
            config_row = cursor.fetchone()
            if config_row and config_row[0]:
                starting_capital = float(config_row[0])
            conn.close()
        except Exception:
            pass  # Use default if config lookup fails

        # Ensure capital fields exist
        if 'capital' not in status:
            status['capital'] = starting_capital

        # Calculate current_equity = starting_capital + realized + unrealized (matches equity curve)
        total_pnl = status.get('total_pnl', 0)
        unrealized_pnl = status.get('unrealized_pnl')  # Can be None if no live pricing
        status['starting_capital'] = starting_capital
        # Only include unrealized in equity if we have live pricing
        if unrealized_pnl is not None:
            status['current_equity'] = round(starting_capital + total_pnl + unrealized_pnl, 2)
        else:
            status['current_equity'] = round(starting_capital + total_pnl, 2)

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
            where_clause = "WHERE status IN ('closed', 'expired', 'partial_close')"

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
                DATE(open_time::timestamptz AT TIME ZONE 'America/Chicago') as trade_date,
                COUNT(*) as trades,
                SUM(CASE WHEN status IN ('closed', 'expired', 'partial_close') AND realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN status IN ('closed', 'expired', 'partial_close') AND realized_pnl <= 0 THEN 1 ELSE 0 END) as losses,
                COALESCE(SUM(realized_pnl), 0) as total_pnl
            FROM icarus_positions
            WHERE DATE(open_time::timestamptz AT TIME ZONE 'America/Chicago') >= CURRENT_DATE - INTERVAL '%s days'
            GROUP BY DATE(open_time::timestamptz AT TIME ZONE 'America/Chicago')
            ORDER BY trade_date DESC
        """, (days,))

        rows = c.fetchall()

        # Calculate summary stats
        c.execute("""
            SELECT
                COUNT(*) as total_trades,
                SUM(CASE WHEN status IN ('closed', 'expired', 'partial_close') AND realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
                COALESCE(SUM(realized_pnl), 0) as total_pnl
            FROM icarus_positions
            WHERE DATE(open_time::timestamptz AT TIME ZONE 'America/Chicago') >= CURRENT_DATE - INTERVAL '%s days'
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
    """Get ICARUS configuration settings (Apache GEX backtest aggressive parameters)."""
    # ICARUS aggressive Apache GEX backtest configuration
    default_config = {
        "risk_per_trade": {"value": "3.0", "description": "Risk per trade (3% vs ATHENA's 2%)"},
        "spread_width": {"value": "3", "description": "Width of spread in strikes ($3 vs ATHENA's $2)"},
        "max_daily_trades": {"value": "8", "description": "Maximum trades per day (8 vs ATHENA's 5)"},
        "max_open_positions": {"value": "4", "description": "Maximum concurrent positions (4 vs ATHENA's 3)"},
        "ticker": {"value": "SPY", "description": "Trading ticker symbol"},
        "wall_filter_pct": {"value": "2.0", "description": "GEX wall filter (2% vs ATHENA's 1%)"},
        "min_win_probability": {"value": "0.48", "description": "Minimum win probability (48% vs ATHENA's 55%)"},
        "min_confidence": {"value": "0.48", "description": "Minimum signal confidence (48% vs ATHENA's 55%)"},
        "min_rr_ratio": {"value": "1.2", "description": "Minimum risk:reward ratio (1.2 vs ATHENA's 1.5)"},
        "min_vix": {"value": "12.0", "description": "Minimum VIX (12 vs ATHENA's 15)"},
        "max_vix": {"value": "30.0", "description": "Maximum VIX (30 vs ATHENA's 25)"},
        "min_gex_ratio_bearish": {"value": "1.3", "description": "GEX ratio for bearish signal (1.3 vs ATHENA's 1.5)"},
        "max_gex_ratio_bullish": {"value": "0.77", "description": "GEX ratio for bullish signal (0.77 vs ATHENA's 0.67)"},
        "stop_loss_pct": {"value": "60", "description": "Stop loss percentage (60% vs ATHENA's 50%)"},
        "profit_target_pct": {"value": "40", "description": "Take profit percentage (40% vs ATHENA's 50%)"},
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
    """Get live P&L for open positions with mark-to-market valuation."""
    icarus = get_icarus_instance()
    today = datetime.now(CENTRAL_TZ).strftime('%Y-%m-%d')
    today_date = datetime.now(CENTRAL_TZ).date()

    if not icarus:
        # ICARUS not running - read from database with MTM valuation
        try:
            conn = get_connection()
            cursor = conn.cursor()

            # Get open positions
            cursor.execute('''
                SELECT
                    position_id, spread_type, open_time, expiration,
                    long_strike, short_strike, entry_debit, contracts,
                    max_profit, max_loss, underlying_at_entry
                FROM icarus_positions
                WHERE status = 'open' AND expiration >= %s
                ORDER BY open_time ASC
            ''', (today,))
            open_rows = cursor.fetchall()

            # Get today's realized P&L
            cursor.execute('''
                SELECT COALESCE(SUM(realized_pnl), 0)
                FROM icarus_positions
                WHERE status IN ('closed', 'expired', 'partial_close')
                AND DATE(close_time) = %s
            ''', (today,))
            realized_row = cursor.fetchone()
            today_realized = float(realized_row[0]) if realized_row else 0

            # Get cumulative realized P&L from ALL closed positions (matches equity curve)
            cursor.execute('''
                SELECT COALESCE(SUM(realized_pnl), 0)
                FROM icarus_positions
                WHERE status IN ('closed', 'expired', 'partial_close')
                AND close_time IS NOT NULL
            ''')
            cumulative_row = cursor.fetchone()
            cumulative_realized = float(cumulative_row[0]) if cumulative_row else 0
            conn.close()

            # Calculate MTM for each position
            positions = []
            total_unrealized = 0.0
            mtm_method = 'estimation'

            for row in open_rows:
                (pos_id, spread_type, open_time, exp, long_strike, short_strike,
                 entry_debit, contracts, max_profit, max_loss, underlying_at_entry) = row

                entry_debit_val = float(entry_debit) if entry_debit else 0
                contracts_val = int(contracts) if contracts else 0
                long_strike_val = float(long_strike) if long_strike else 0
                short_strike_val = float(short_strike) if short_strike else 0

                # Calculate DTE
                dte = None
                try:
                    if exp:
                        exp_date = datetime.strptime(str(exp), '%Y-%m-%d').date()
                        dte = (exp_date - today_date).days
                except (ValueError, TypeError):
                    pass

                # Calculate unrealized P&L using MTM
                pos_unrealized = None
                method = 'estimation'

                if MTM_AVAILABLE and exp and long_strike_val and short_strike_val:
                    try:
                        mtm_result = calculate_spread_mark_to_market(
                            underlying='SPY',
                            expiration=str(exp),
                            long_strike=long_strike_val,
                            short_strike=short_strike_val,
                            spread_type=spread_type or 'BULL_CALL',
                            contracts=contracts_val,
                            entry_debit=entry_debit_val,
                            use_cache=True
                        )
                        if mtm_result.get('success') and mtm_result.get('unrealized_pnl') is not None:
                            pos_unrealized = mtm_result['unrealized_pnl']
                            total_unrealized += pos_unrealized
                            method = 'mark_to_market'
                            mtm_method = 'mark_to_market'
                    except Exception as e:
                        logger.debug(f"ICARUS live-pnl MTM failed for {pos_id}: {e}")

                positions.append({
                    'position_id': pos_id,
                    'spread_type': spread_type,
                    'open_date': str(open_time) if open_time else None,
                    'expiration': str(exp) if exp else None,
                    'long_strike': long_strike_val,
                    'short_strike': short_strike_val,
                    'entry_debit': entry_debit_val,
                    'contracts': contracts_val,
                    'max_profit': round(float(max_profit or 0) * 100 * contracts_val, 2),
                    'max_loss': round(float(max_loss or 0) * 100 * contracts_val, 2),
                    'underlying_at_entry': float(underlying_at_entry) if underlying_at_entry else 0,
                    'dte': dte,
                    'unrealized_pnl': round(pos_unrealized, 2) if pos_unrealized is not None else None,
                    'method': method
                })

            final_unrealized = round(total_unrealized, 2) if mtm_method == 'mark_to_market' else None

            return {
                "success": True,
                "data": {
                    "total_unrealized_pnl": final_unrealized,
                    "total_realized_pnl": round(cumulative_realized, 2),
                    "today_realized_pnl": round(today_realized, 2),
                    "net_pnl": round(cumulative_realized + (final_unrealized or 0), 2) if final_unrealized is not None else round(cumulative_realized, 2),
                    "positions": positions,
                    "position_count": len(positions),
                    "source": "database",
                    "method": mtm_method,
                    "message": "Live valuation via mark-to-market" if mtm_method == 'mark_to_market' else "MTM unavailable - estimation fallback"
                }
            }
        except Exception as db_err:
            logger.warning(f"Could not read ICARUS live P&L from database: {db_err}")

        return {
            "success": True,
            "data": {
                "total_unrealized_pnl": None,
                "total_realized_pnl": 0,
                "net_pnl": None,
                "positions": [],
                "position_count": 0,
                "message": "ICARUS not initialized"
            }
        }

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


@router.get("/equity-curve")
async def get_icarus_equity_curve(days: int = 30):
    """
    Get ICARUS equity curve data including unrealized P&L from open positions.

    Args:
        days: Number of days of history (default 30)
    """
    starting_capital = 100000
    today = datetime.now(CENTRAL_TZ).strftime('%Y-%m-%d')
    unrealized_pnl = 0.0
    open_positions_count = 0

    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Get starting capital from config
        cursor.execute("""
            SELECT value FROM autonomous_config WHERE key = 'icarus_starting_capital'
        """)
        row = cursor.fetchone()
        if row and row[0]:
            try:
                starting_capital = float(row[0])
            except (ValueError, TypeError):
                pass

        # Get ALL closed positions for correct cumulative P&L calculation
        # The days parameter filters the OUTPUT, not the query
        cursor.execute('''
            SELECT DATE(close_time::timestamptz AT TIME ZONE 'America/Chicago') as close_date,
                   realized_pnl, position_id
            FROM icarus_positions
            WHERE status IN ('closed', 'expired', 'partial_close')
            AND close_time IS NOT NULL
            ORDER BY close_time ASC
        ''')
        rows = cursor.fetchall()

        # Get open positions for unrealized P&L calculation
        cursor.execute('''
            SELECT position_id, spread_type, entry_debit, contracts,
                   long_strike, short_strike, expiration, ticker
            FROM icarus_positions
            WHERE status = 'open'
        ''')
        open_positions = cursor.fetchall()
        open_positions_count = len(open_positions)
        conn.close()

        # Calculate unrealized P&L from open positions
        if open_positions and MTM_AVAILABLE:
            for pos in open_positions:
                pos_id, spread_type, entry_debit, contracts, long_strike, short_strike, exp, ticker = pos
                try:
                    exp_str = exp.strftime('%Y-%m-%d') if hasattr(exp, 'strftime') else str(exp)
                    mtm_result = calculate_spread_mark_to_market(
                        underlying=ticker or 'SPY',
                        expiration=exp_str,
                        long_strike=float(long_strike),
                        short_strike=float(short_strike),
                        spread_type=spread_type or 'BEAR_PUT',
                        contracts=int(contracts),
                        entry_debit=float(entry_debit) if entry_debit else 0
                    )
                    if mtm_result and mtm_result.get('success'):
                        pos_pnl = mtm_result.get('unrealized_pnl', 0) or 0
                        unrealized_pnl += pos_pnl
                except Exception as e:
                    logger.debug(f"MTM calculation failed for {pos_id}: {e}")

        equity_curve = []
        positions_by_date = {}
        cumulative_pnl = 0

        if rows:
            for row in rows:
                close_date, pnl, pos_id = row
                date_key = str(close_date) if close_date else None
                if date_key:
                    if date_key not in positions_by_date:
                        positions_by_date[date_key] = []
                    positions_by_date[date_key].append({'pnl': float(pnl) if pnl else 0, 'id': pos_id})

            sorted_dates = sorted(positions_by_date.keys())

            if sorted_dates:
                equity_curve.append({
                    "date": sorted_dates[0],
                    "equity": starting_capital,
                    "pnl": 0,
                    "daily_pnl": 0,
                    "return_pct": 0
                })

            for date_str in sorted_dates:
                daily_pnl = sum(p['pnl'] for p in positions_by_date[date_str])
                cumulative_pnl += daily_pnl
                current_equity = starting_capital + cumulative_pnl

                equity_curve.append({
                    "date": date_str,
                    "equity": round(current_equity, 2),
                    "pnl": round(cumulative_pnl, 2),
                    "daily_pnl": round(daily_pnl, 2),
                    "return_pct": round((cumulative_pnl / starting_capital) * 100, 2),
                    "trades_closed": len(positions_by_date[date_str])
                })

        # Add today's entry with unrealized P&L from open positions
        total_pnl_with_unrealized = cumulative_pnl + unrealized_pnl
        current_equity_with_unrealized = starting_capital + total_pnl_with_unrealized

        # Always add today's data point if we have open positions or closed positions
        if open_positions_count > 0 or rows:
            # Remove duplicate today entry if exists
            if equity_curve and equity_curve[-1]["date"] == today:
                equity_curve.pop()

            equity_curve.append({
                "date": today,
                "equity": round(current_equity_with_unrealized, 2),
                "pnl": round(total_pnl_with_unrealized, 2),
                "realized_pnl": round(cumulative_pnl, 2),
                "unrealized_pnl": round(unrealized_pnl, 2),
                "daily_pnl": round(unrealized_pnl, 2),
                "return_pct": round((total_pnl_with_unrealized / starting_capital) * 100, 2),
                "open_positions": open_positions_count
            })

            return {
                "success": True,
                "data": {
                    "equity_curve": equity_curve,
                    "starting_capital": starting_capital,
                    "current_equity": round(current_equity_with_unrealized, 2),
                    "total_pnl": round(total_pnl_with_unrealized, 2),
                    "realized_pnl": round(cumulative_pnl, 2),
                    "unrealized_pnl": round(unrealized_pnl, 2),
                    "total_return_pct": round((total_pnl_with_unrealized / starting_capital) * 100, 2),
                    "closed_positions_count": len(rows),
                    "open_positions_count": open_positions_count,
                    "source": "database"
                }
            }

    except Exception as db_err:
        logger.warning(f"Could not read equity curve from database: {db_err}")

    return {
        "success": True,
        "data": {
            "equity_curve": [{
                "date": today,
                "equity": starting_capital,
                "pnl": 0,
                "daily_pnl": 0,
                "return_pct": 0
            }],
            "starting_capital": starting_capital,
            "current_equity": starting_capital,
            "total_pnl": 0,
            "message": "No positions found"
        }
    }


@router.get("/equity-curve/intraday")
async def get_icarus_intraday_equity(date: str = None):
    """
    Get ICARUS intraday equity curve with 5-minute interval snapshots.

    Returns equity data points throughout the trading day showing:
    - Realized P&L from closed positions
    - Unrealized P&L from open positions (mark-to-market)

    Args:
        date: Date to get intraday data for (default: today)
    """
    now = datetime.now(CENTRAL_TZ)
    today = date or now.strftime('%Y-%m-%d')
    current_time = now.strftime('%H:%M:%S')

    starting_capital = 100000

    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Get starting capital from config
        cursor.execute("""
            SELECT value FROM autonomous_config WHERE key = 'icarus_starting_capital'
        """)
        row = cursor.fetchone()
        if row and row[0]:
            try:
                starting_capital = float(row[0])
            except (ValueError, TypeError):
                pass

        # Get intraday snapshots for the requested date
        cursor.execute("""
            SELECT timestamp, balance, unrealized_pnl, realized_pnl, open_positions, note
            FROM icarus_equity_snapshots
            WHERE DATE(timestamp::timestamptz AT TIME ZONE 'America/Chicago') = %s
            ORDER BY timestamp ASC
        """, (today,))
        snapshots = cursor.fetchall()

        # Get total realized P&L from closed positions up to today
        cursor.execute("""
            SELECT COALESCE(SUM(realized_pnl), 0)
            FROM icarus_positions
            WHERE status IN ('closed', 'expired', 'partial_close')
            AND DATE(close_time::timestamptz AT TIME ZONE 'America/Chicago') <= %s
        """, (today,))
        total_realized_row = cursor.fetchone()
        total_realized = float(total_realized_row[0]) if total_realized_row and total_realized_row[0] else 0

        # Get today's closed positions P&L
        cursor.execute("""
            SELECT COALESCE(SUM(realized_pnl), 0), COUNT(*)
            FROM icarus_positions
            WHERE status IN ('closed', 'expired', 'partial_close')
            AND DATE(close_time::timestamptz AT TIME ZONE 'America/Chicago') = %s
        """, (today,))
        today_row = cursor.fetchone()
        today_realized = float(today_row[0]) if today_row and today_row[0] else 0
        today_closed_count = int(today_row[1]) if today_row and today_row[1] else 0

        # Get today's closed trades with timestamps for accurate intraday cumulative calculation
        # This fixes the "cliff" bug where old snapshots had NULL/incorrect realized_pnl
        cursor.execute("""
            SELECT close_time::timestamptz, realized_pnl
            FROM icarus_positions
            WHERE status IN ('closed', 'expired')
            AND DATE(close_time::timestamptz AT TIME ZONE 'America/Chicago') = %s
            ORDER BY close_time ASC
        """, (today,))
        today_closes = cursor.fetchall()

        # Calculate unrealized P&L from open positions using real option quotes (MTM)
        unrealized_pnl = 0
        open_positions = []
        spy_price = None

        # Get current SPY price for estimation fallback
        try:
            from data.unified_data_provider import get_price
            spy_price = get_price("SPY")
            if not spy_price or spy_price <= 0:
                spx_price = get_price("SPX")
                if spx_price and spx_price > 0:
                    spy_price = spx_price / 10
        except Exception:
            pass

        # Fallback to Tradier direct
        if not spy_price or spy_price <= 0:
            try:
                from data.tradier_data_fetcher import TradierDataFetcher
                import os
                api_key = os.environ.get('TRADIER_API_KEY') or os.environ.get('TRADIER_SANDBOX_API_KEY')
                if api_key:
                    tradier = TradierDataFetcher(api_key=api_key, sandbox='SANDBOX' in str(os.environ.get('TRADIER_SANDBOX_API_KEY', '')))
                    quote = tradier.get_quote('SPY')
                    if quote and quote.get('last'):
                        price = float(quote['last'])
                        if price > 0:
                            spy_price = price
            except Exception as e:
                logger.debug(f"Tradier price fetch failed: {e}")

        try:
            # Query includes expiration for MTM pricing
            cursor.execute("""
                SELECT position_id, spread_type, entry_debit, contracts,
                       long_strike, short_strike, max_profit, max_loss, expiration
                FROM icarus_positions
                WHERE status = 'open'
            """)
            open_rows = cursor.fetchall()

            # Use MTM helper function for accurate unrealized P&L
            if open_rows:
                pnl_result = _calculate_icarus_unrealized_pnl(open_rows, spy_price)
                unrealized_pnl = pnl_result['total_unrealized_pnl']
                open_positions = pnl_result['position_details']
                logger.debug(f"ICARUS intraday: unrealized=${unrealized_pnl:.2f} "
                           f"(MTM: {pnl_result['mtm_count']}, Est: {pnl_result['estimation_count']})")
        except Exception as e:
            logger.debug(f"Error calculating unrealized P&L: {e}")

        conn.close()

        # Build intraday data points (frontend expects data_points with cumulative_pnl)
        data_points = []

        # Add market open point
        prev_day_realized = total_realized - today_realized
        market_open_equity = round(starting_capital + prev_day_realized, 2)
        data_points.append({
            "timestamp": f"{today}T08:30:00",
            "time": "08:30:00",
            "equity": market_open_equity,
            "cumulative_pnl": round(prev_day_realized, 2),
            "open_positions": 0,
            "unrealized_pnl": 0
        })

        # Track high/low for summary
        all_equities = [market_open_equity]

        # Add snapshots - calculate cumulative realized at each snapshot's timestamp
        # This fixes the "cliff" bug where old snapshots had NULL/incorrect realized_pnl
        for snapshot in snapshots:
            ts, balance, snap_unrealized, snap_realized, open_count, note = snapshot
            snap_time = ts.astimezone(CENTRAL_TZ) if ts.tzinfo else ts

            # Calculate cumulative realized at this snapshot's timestamp from actual trades
            # prev_day_realized + sum of today's closes that happened before this snapshot
            snap_realized_val = prev_day_realized
            for close_time, close_pnl in today_closes:
                close_time_ct = close_time.astimezone(CENTRAL_TZ) if close_time and close_time.tzinfo else close_time
                if close_time_ct and close_time_ct <= snap_time:
                    snap_realized_val += float(close_pnl or 0)

            snap_unrealized_val = float(snap_unrealized or 0)
            # Recalculate equity: starting_capital + realized + unrealized
            snap_equity = round(starting_capital + snap_realized_val + snap_unrealized_val, 2)
            all_equities.append(snap_equity)

            data_points.append({
                "timestamp": snap_time.isoformat(),
                "time": snap_time.strftime('%H:%M:%S'),
                "equity": snap_equity,
                "cumulative_pnl": round(snap_realized_val + snap_unrealized_val, 2),
                "open_positions": open_count or 0,
                "unrealized_pnl": round(snap_unrealized_val, 2)
            })

        # Add current live point if viewing today
        current_equity = starting_capital + total_realized + unrealized_pnl
        if today == now.strftime('%Y-%m-%d'):
            total_pnl = total_realized + unrealized_pnl
            current_equity = starting_capital + total_pnl
            all_equities.append(round(current_equity, 2))

            data_points.append({
                "timestamp": now.isoformat(),
                "time": current_time,
                "equity": round(current_equity, 2),
                "cumulative_pnl": round(total_pnl, 2),
                "open_positions": len(open_positions),
                "unrealized_pnl": round(unrealized_pnl, 2)
            })

        # Calculate high/low of day
        high_of_day = max(all_equities) if all_equities else starting_capital
        low_of_day = min(all_equities) if all_equities else starting_capital
        day_pnl = today_realized + unrealized_pnl

        return {
            "success": True,
            "date": today,
            "bot": "ICARUS",
            "data_points": data_points,
            "current_equity": round(current_equity, 2),
            "day_pnl": round(day_pnl, 2),
            "day_realized": round(today_realized, 2),
            "day_unrealized": round(unrealized_pnl, 2),
            "starting_equity": market_open_equity,  # Equity at market open (starting_capital + prev realized)
            "high_of_day": round(high_of_day, 2),
            "low_of_day": round(low_of_day, 2),
            "snapshots_count": len(snapshots)
        }

    except Exception as e:
        logger.error(f"Error getting ICARUS intraday equity: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e),
            "date": today,
            "bot": "ICARUS",
            "data_points": [{
                "timestamp": now.isoformat(),
                "time": current_time,
                "equity": starting_capital,
                "cumulative_pnl": 0,
                "open_positions": 0,
                "unrealized_pnl": 0
            }],
            "current_equity": starting_capital,
            "day_pnl": 0,
            "day_realized": 0,
            "day_unrealized": 0,
            "starting_equity": starting_capital,
            "high_of_day": starting_capital,
            "low_of_day": starting_capital,
            "snapshots_count": 0
        }


@router.post("/equity-snapshot")
async def save_icarus_equity_snapshot():
    """
    Save current equity snapshot for intraday tracking.

    Call this periodically (every 5 minutes) during market hours
    to build detailed intraday equity curve.
    """
    now = datetime.now(CENTRAL_TZ)

    starting_capital = 100000
    unrealized_pnl = 0
    realized_pnl = 0
    open_count = 0

    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Get starting capital
        cursor.execute("""
            SELECT value FROM autonomous_config WHERE key = 'icarus_starting_capital'
        """)
        row = cursor.fetchone()
        if row and row[0]:
            try:
                starting_capital = float(row[0])
            except (ValueError, TypeError):
                pass

        # Get total realized P&L
        cursor.execute("""
            SELECT COALESCE(SUM(realized_pnl), 0)
            FROM icarus_positions
            WHERE status IN ('closed', 'expired', 'partial_close')
        """)
        row = cursor.fetchone()
        realized_pnl = float(row[0]) if row and row[0] else 0

        # Get open positions with spread info for unrealized P&L calculation
        # Include expiration for MTM pricing
        cursor.execute("""
            SELECT position_id, spread_type, entry_debit, contracts,
                   long_strike, short_strike, max_profit, max_loss, expiration
            FROM icarus_positions
            WHERE status = 'open'
        """)
        open_positions = cursor.fetchall()
        open_count = len(open_positions)

        # Calculate unrealized P&L using MTM with estimation fallback
        unrealized_pnl = 0
        spy_price = None

        # Get SPY price for estimation fallback
        try:
            from data.unified_data_provider import get_price
            spy_price = get_price("SPY")
            if not spy_price or spy_price <= 0:
                spx_price = get_price("SPX")
                if spx_price and spx_price > 0:
                    spy_price = spx_price / 10
        except Exception:
            pass

        # Fallback to Tradier direct
        if not spy_price or spy_price <= 0:
            try:
                from data.tradier_data_fetcher import TradierDataFetcher
                import os
                api_key = os.environ.get('TRADIER_API_KEY') or os.environ.get('TRADIER_SANDBOX_API_KEY')
                if api_key:
                    tradier = TradierDataFetcher(api_key=api_key, sandbox='SANDBOX' in str(os.environ.get('TRADIER_SANDBOX_API_KEY', '')))
                    quote = tradier.get_quote('SPY')
                    if quote and quote.get('last'):
                        price = float(quote['last'])
                        if price > 0:
                            spy_price = price
            except Exception as e:
                logger.debug(f"Tradier price fetch failed: {e}")

        # Use MTM helper function for accurate unrealized P&L
        if open_positions:
            pnl_result = _calculate_icarus_unrealized_pnl(open_positions, spy_price)
            unrealized_pnl = pnl_result['total_unrealized_pnl']
            logger.debug(f"ICARUS snapshot: unrealized=${unrealized_pnl:.2f} "
                       f"(MTM: {pnl_result['mtm_count']}, Est: {pnl_result['estimation_count']})")

        current_equity = starting_capital + realized_pnl + unrealized_pnl

        # Create table if not exists
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS icarus_equity_snapshots (
                id SERIAL PRIMARY KEY,
                timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
                balance DECIMAL(12, 2) NOT NULL,
                unrealized_pnl DECIMAL(12, 2),
                realized_pnl DECIMAL(12, 2),
                open_positions INTEGER,
                note TEXT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        ''')

        # Insert snapshot
        cursor.execute('''
            INSERT INTO icarus_equity_snapshots
            (timestamp, balance, unrealized_pnl, realized_pnl, open_positions, note)
            VALUES (%s, %s, %s, %s, %s, %s)
        ''', (
            now,
            current_equity,
            unrealized_pnl,
            realized_pnl,
            open_count,
            f"Auto snapshot at {now.strftime('%H:%M:%S')}"
        ))

        conn.commit()
        conn.close()

        return {
            "success": True,
            "data": {
                "timestamp": now.isoformat(),
                "equity": round(current_equity, 2),
                "unrealized_pnl": round(unrealized_pnl, 2),
                "realized_pnl": round(realized_pnl, 2),
                "open_positions": open_count
            }
        }

    except Exception as e:
        logger.error(f"Error saving ICARUS equity snapshot: {e}")
        return {
            "success": False,
            "error": str(e)
        }
