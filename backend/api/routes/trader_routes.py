"""
Autonomous Trader API routes.

Handles trader status, performance, positions, trades, and equity curve.

IMPORTANT: Trade execution endpoints are protected by ENABLE_LIVE_TRADING flag.
"""

import math
import os
from datetime import datetime, timedelta
import logging

from fastapi import APIRouter, HTTPException
import psycopg2.extras

from database_adapter import get_connection

# Import centralized utilities
from backend.api.utils import safe_round, clean_dict_for_json, get_market_time
from backend.api.logging_config import api_logger, log_trade_entry, log_trade_exit

router = APIRouter(prefix="/api/trader", tags=["Trader"])
logger = logging.getLogger(__name__)

# Import mark-to-market utility for fresh unrealized P&L calculation
MTM_AVAILABLE = False
calculate_ic_mark_to_market = None
try:
    from trading.mark_to_market import calculate_ic_mark_to_market
    MTM_AVAILABLE = True
    logger.info("Mark-to-market utility loaded for trader routes")
except ImportError as e:
    logger.debug(f"Mark-to-market import failed: {e}")


def check_live_trading_enabled() -> bool:
    """
    Check if live trading is enabled.
    Returns True if ENABLE_LIVE_TRADING env var is 'true'.
    """
    return os.getenv('ENABLE_LIVE_TRADING', 'false').lower() == 'true'


def require_live_trading():
    """
    Guard function to block trade execution when live trading is disabled.
    Raises HTTPException if live trading is not enabled.
    """
    if not check_live_trading_enabled():
        raise HTTPException(
            status_code=403,
            detail="Live trading is disabled. Set ENABLE_LIVE_TRADING=true to enable trade execution."
        )


def _calculate_portfolio_unrealized_pnl(cursor) -> dict:
    """
    Calculate fresh unrealized P&L from source bot tables using MTM.

    Queries each bot's open positions directly and calculates mark-to-market
    values for accurate unrealized P&L. This bypasses stale values in the
    unified tables.

    Returns:
        Dict with:
        - total_unrealized_pnl: Aggregate unrealized P&L across all bots
        - by_symbol: Unrealized P&L broken down by symbol (SPY, SPX)
        - by_bot: Unrealized P&L by bot name
        - method: 'mark_to_market' or 'estimation'
    """
    result = {
        'total_unrealized_pnl': 0.0,
        'by_symbol': {'SPY': 0.0, 'SPX': 0.0},
        'by_bot': {},
        'method': 'estimation',
        'position_count': 0
    }

    if not MTM_AVAILABLE:
        logger.debug("MTM not available for portfolio unrealized calculation")
        return result

    # Bot configurations: (table, symbol, credit_field)
    bot_configs = [
        ('ares_positions', 'ARES', 'SPY', 'total_credit'),
        ('athena_positions', 'ATHENA', 'SPY', 'entry_price'),
        ('icarus_positions', 'ICARUS', 'SPY', 'entry_price'),
        ('titan_positions', 'TITAN', 'SPX', 'total_credit'),
        ('pegasus_positions', 'PEGASUS', 'SPX', 'total_credit'),
    ]

    has_mtm = False

    for table, bot_name, symbol, credit_field in bot_configs:
        try:
            # Query open positions with IC leg details
            cursor.execute(f"""
                SELECT position_id, {credit_field}, contracts, spread_width,
                       put_short_strike, put_long_strike, call_short_strike, call_long_strike,
                       expiration
                FROM {table}
                WHERE status = 'open'
            """)
            positions = cursor.fetchall()

            bot_unrealized = 0.0
            bot_position_count = 0

            for pos in positions:
                (pos_id, credit, contracts, spread_width,
                 put_short, put_long, call_short, call_long, expiration) = pos

                # Skip non-IC positions (ATHENA/ICARUS directional)
                if not all([put_short, put_long, call_short, call_long]):
                    continue

                credit_val = float(credit or 0)
                contracts_val = int(contracts or 1)

                try:
                    exp_str = expiration.strftime('%Y-%m-%d') if hasattr(expiration, 'strftime') else str(expiration)
                    mtm = calculate_ic_mark_to_market(
                        underlying=symbol,
                        expiration=exp_str,
                        put_short_strike=float(put_short),
                        put_long_strike=float(put_long),
                        call_short_strike=float(call_short),
                        call_long_strike=float(call_long),
                        contracts=contracts_val,
                        entry_credit=credit_val,
                        use_cache=True
                    )
                    if mtm.get('success'):
                        bot_unrealized += mtm['unrealized_pnl']
                        bot_position_count += 1
                        has_mtm = True
                except Exception as e:
                    logger.debug(f"MTM failed for {bot_name} position {pos_id}: {e}")

            result['by_bot'][bot_name] = round(bot_unrealized, 2)
            result['by_symbol'][symbol] += bot_unrealized
            result['total_unrealized_pnl'] += bot_unrealized
            result['position_count'] += bot_position_count

        except Exception as e:
            logger.debug(f"Error querying {table} for unrealized P&L: {e}")
            result['by_bot'][bot_name] = 0.0

    # Round final values
    result['total_unrealized_pnl'] = round(result['total_unrealized_pnl'], 2)
    result['by_symbol']['SPY'] = round(result['by_symbol']['SPY'], 2)
    result['by_symbol']['SPX'] = round(result['by_symbol']['SPX'], 2)
    result['method'] = 'mark_to_market' if has_mtm else 'estimation'

    return result


# Try to import the autonomous trader
try:
    from core.autonomous_paper_trader import AutonomousPaperTrader
    trader = AutonomousPaperTrader()
    trader_available = True
    logger.info("Autonomous trader initialized successfully")
except Exception as e:
    trader = None
    trader_available = False
    logger.warning(f"Autonomous trader not available: {type(e).__name__}")


@router.get("/status")
async def get_trader_status():
    """Get autonomous trader status"""
    if not trader_available:
        return {
            "success": False,
            "message": "Trader not configured",
            "data": {
                "is_active": False,
                "mode": "paper",
                "uptime": 0,
                "last_check": None,
                "strategies_active": 0,
                "total_trades_today": 0
            }
        }

    try:
        status = trader.get_status() if hasattr(trader, 'get_status') else {}
        return {
            "success": True,
            "data": {
                "is_active": status.get('is_active', False),
                "mode": status.get('mode', 'paper'),
                "status": status.get('status', 'idle'),
                "current_action": status.get('current_action'),
                "market_analysis": status.get('market_analysis'),
                "last_decision": status.get('last_decision'),
                "last_check": status.get('last_check'),
                "next_check_time": status.get('next_check_time'),
                "strategies_active": status.get('strategies_active', 0),
                "total_trades_today": status.get('total_trades_today', 0),
                "uptime": status.get('uptime', 0)
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/performance")
async def get_trader_performance():
    """Get autonomous trader performance metrics"""
    if not trader_available:
        return {
            "success": False,
            "message": "Trader not configured",
            "data": {
                "total_pnl": 0,
                "today_pnl": 0,
                "win_rate": 0,
                "total_trades": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "sharpe_ratio": 0,
                "max_drawdown": 0
            }
        }

    conn = None
    try:
        perf = trader.get_performance() if hasattr(trader, 'get_performance') else {}

        conn = get_connection()
        cursor = conn.cursor()

        # PERFORMANCE FIX: Single CTE query for all metrics (was 4 sequential queries)
        from zoneinfo import ZoneInfo
        today = datetime.now(ZoneInfo("America/Chicago")).strftime('%Y-%m-%d')

        max_drawdown = 0
        sharpe_ratio = 0
        today_pnl = 0
        starting_capital = 1000000

        try:
            cursor.execute("""
                WITH capital_config AS (
                    SELECT COALESCE(value::numeric, 1000000) as capital
                    FROM autonomous_config WHERE key = 'capital'
                    LIMIT 1
                ),
                latest_equity AS (
                    SELECT equity, cumulative_pnl
                    FROM autonomous_equity_snapshots
                    ORDER BY timestamp DESC
                    LIMIT 1
                ),
                today_realized AS (
                    SELECT COALESCE(SUM(realized_pnl), 0) as total
                    FROM autonomous_closed_trades
                    WHERE COALESCE(exit_date, entry_date) = %s
                ),
                today_unrealized AS (
                    SELECT COALESCE(SUM(unrealized_pnl), 0) as total
                    FROM autonomous_open_positions
                )
                SELECT
                    COALESCE((SELECT capital FROM capital_config), 1000000) as starting_capital,
                    (SELECT equity FROM latest_equity) as current_equity,
                    (SELECT cumulative_pnl FROM latest_equity) as cumulative_pnl,
                    (SELECT total FROM today_realized) as today_realized,
                    (SELECT total FROM today_unrealized) as today_unrealized
            """, (today,))
            row = cursor.fetchone()

            if row:
                starting_capital = float(row[0]) if row[0] else 1000000
                current_equity = float(row[1]) if row[1] else starting_capital
                today_realized = float(row[3]) if row[3] else 0
                today_unrealized = float(row[4]) if row[4] else 0

                today_pnl = today_realized + today_unrealized

                # Calculate drawdown from equity if available
                if current_equity < starting_capital:
                    max_drawdown = ((starting_capital - current_equity) / starting_capital * 100)

        except Exception as e:
            logger.warning(f"Could not fetch performance metrics: {e}")
            conn.rollback()

        conn.close()

        return {
            "success": True,
            "data": {
                "total_pnl": safe_round(perf.get('total_pnl', 0)),
                "today_pnl": safe_round(today_pnl),
                "win_rate": safe_round(perf.get('win_rate', 0)),
                "total_trades": perf.get('total_trades', 0),
                "closed_trades": perf.get('closed_trades', 0),
                "open_positions": perf.get('open_positions', 0),
                "winning_trades": perf.get('winning_trades', 0),
                "losing_trades": perf.get('losing_trades', 0),
                "sharpe_ratio": safe_round(sharpe_ratio),
                "max_drawdown": safe_round(max_drawdown),
                "realized_pnl": safe_round(perf.get('realized_pnl', 0)),
                "unrealized_pnl": safe_round(perf.get('unrealized_pnl', 0)),
                "starting_capital": perf.get('starting_capital', 1000000),
                "current_value": safe_round(perf.get('current_value', 1000000)),
                "return_pct": safe_round(perf.get('return_pct', 0))
            }
        }
    except Exception as e:
        if conn:
            try:
                conn.rollback()
                conn.close()
            except Exception:
                pass
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{symbol}/positions")
async def get_symbol_positions(symbol: str):
    """Get open positions for a specific symbol (path parameter version)."""
    return await get_open_positions(symbol=symbol)


@router.get("/positions")
async def get_open_positions(symbol: str = None):
    """Get all open positions from database with full details for tracking.

    Args:
        symbol: Optional - filter by symbol (SPY, SPX, etc). If None, returns ALL symbols.
    """
    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Support multi-symbol: if symbol provided, filter; otherwise show ALL
        # Use defensive query that handles missing Greek columns gracefully
        base_query = """
            SELECT
                id, symbol, strategy, strike, option_type, contracts,
                entry_price, current_price, unrealized_pnl, entry_date,
                entry_time, entry_spot_price, current_spot_price, gex_regime, created_at
            FROM autonomous_open_positions
        """

        full_query = """
            SELECT
                id, symbol, strategy, strike, option_type, contracts,
                entry_price, current_price, unrealized_pnl, entry_date,
                entry_time, expiration_date, contract_symbol, entry_spot_price,
                current_spot_price, gex_regime,
                COALESCE(confidence, 0) as confidence,
                trade_reasoning,
                profit_target_pct, stop_loss_pct, created_at,
                COALESCE(entry_iv, 0) as entry_iv,
                COALESCE(entry_delta, 0) as entry_delta,
                COALESCE(entry_gamma, 0) as entry_gamma,
                COALESCE(entry_theta, 0) as entry_theta,
                COALESCE(entry_vega, 0) as entry_vega,
                COALESCE(current_iv, 0) as current_iv,
                COALESCE(current_delta, 0) as current_delta,
                COALESCE(current_gamma, 0) as current_gamma,
                COALESCE(current_theta, 0) as current_theta,
                COALESCE(current_vega, 0) as current_vega,
                COALESCE(is_delayed, false) as is_delayed,
                COALESCE(data_confidence, 'unknown') as data_confidence,
                COALESCE(entry_bid, 0) as entry_bid,
                COALESCE(entry_ask, 0) as entry_ask
            FROM autonomous_open_positions
        """

        # Try full query first, fall back to basic if columns missing
        try:
            if symbol:
                cursor.execute(full_query + " WHERE symbol = %s ORDER BY entry_date DESC, entry_time DESC", (symbol.upper(),))
            else:
                cursor.execute(full_query + " ORDER BY entry_date DESC, entry_time DESC")
        except Exception as col_error:
            # Fallback to basic query if Greek columns don't exist
            logger.warning(f"Full query failed, using basic: {col_error}")
            conn.rollback()  # Reset transaction after error
            if symbol:
                cursor.execute(base_query + " WHERE symbol = %s ORDER BY entry_date DESC, entry_time DESC", (symbol.upper(),))
            else:
                cursor.execute(base_query + " ORDER BY entry_date DESC, entry_time DESC")

        positions = cursor.fetchall()
        conn.close()

        # Format the response with proper date/time handling
        formatted_positions = []
        for p in positions:
            pos = dict(p)
            # Format entry_date and entry_time into a combined timestamp for display
            if pos.get('entry_date') and pos.get('entry_time'):
                pos['entry_timestamp'] = f"{pos['entry_date']} {pos['entry_time']}"
            # Format expiration_date as string for frontend
            if pos.get('expiration_date'):
                pos['expiration'] = str(pos['expiration_date'])
            formatted_positions.append(pos)

        return {
            "success": True,
            "data": formatted_positions
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/closed-trades")
async def get_closed_trades(limit: int = 50, symbol: str = None):
    """Get closed trades from database.

    Args:
        limit: Max trades to return (default 50)
        symbol: Optional - filter by symbol (SPY, SPX, etc). If None, returns ALL symbols.
    """
    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        if symbol:
            cursor.execute("""
                SELECT * FROM autonomous_closed_trades
                WHERE symbol = %s
                ORDER BY COALESCE(exit_date, entry_date) DESC, COALESCE(exit_time, entry_time) DESC
                LIMIT %s
            """, (symbol.upper(), int(limit)))
        else:
            # Show ALL symbols for unified portfolio view
            cursor.execute("""
                SELECT * FROM autonomous_closed_trades
                ORDER BY COALESCE(exit_date, entry_date) DESC, COALESCE(exit_time, entry_time) DESC
                LIMIT %s
            """, (int(limit),))
        trades = cursor.fetchall()
        conn.close()

        return {
            "success": True,
            "data": [dict(t) for t in trades]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/equity-curve")
async def get_equity_curve(days: int = 30, symbol: str = None):
    """Get historical equity curve from snapshots or trades.

    Args:
        days: Number of days of history (default 30)
        symbol: Optional - filter by symbol (SPY, SPX, etc). If None, returns ALL symbols combined.
    """
    if not trader_available:
        return {
            "success": False,
            "message": "Trader not configured",
            "data": []
        }

    conn = None
    try:
        import pandas as pd

        conn = get_connection()
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        starting_equity = 1000000
        start_date_str = start_date.strftime('%Y-%m-%d')

        logger.debug(f"equity-curve: Querying snapshots from {start_date_str}")

        # Query only columns that exist - avoid daily_pnl, drawdown_pct
        # Use string formatting for date since pandas can be finicky with params
        snapshots = pd.read_sql_query(f"""
            SELECT
                DATE(timestamp) as snapshot_date,
                timestamp::time as snapshot_time,
                equity as account_value,
                COALESCE(cumulative_pnl, 0) as total_realized_pnl,
                ROUND(((equity - 1000000) / 1000000 * 100)::numeric, 2) as total_return_pct
            FROM autonomous_equity_snapshots
            WHERE timestamp >= '{start_date_str}'
            ORDER BY timestamp ASC
        """, conn)

        logger.debug(f"equity-curve: Found {len(snapshots)} snapshots")

        if snapshots.empty:
            # Build from closed trades - support multi-symbol
            symbol_filter = f"AND symbol = '{symbol.upper()}'" if symbol else ""
            trades = pd.read_sql_query(f"""
                SELECT
                    COALESCE(exit_date, entry_date) as trade_date,
                    COALESCE(exit_time, entry_time) as trade_time,
                    realized_pnl,
                    strategy,
                    symbol
                FROM autonomous_closed_trades
                WHERE COALESCE(exit_date, entry_date) >= '{start_date_str}' {symbol_filter}
                ORDER BY COALESCE(exit_date, entry_date) ASC, COALESCE(exit_time, entry_time) ASC
            """, conn)

            conn.close()

            if trades.empty:
                return {
                    "success": True,
                    "data": [{
                        "timestamp": int(start_date.timestamp()),
                        "date": start_date.strftime('%Y-%m-%d'),
                        "equity": starting_equity,
                        "pnl": 0,
                        "daily_pnl": 0,
                        "total_return_pct": 0,
                        "max_drawdown_pct": 0,
                        "sharpe_ratio": 0,
                        "win_rate": 0
                    }],
                    "total_pnl": 0,
                    "starting_equity": starting_equity,
                    "message": "No trades yet"
                }

            # Calculate from trades
            equity_data = []
            cumulative_pnl = 0
            peak_equity = starting_equity
            max_drawdown = 0

            trades['trade_date'] = pd.to_datetime(trades['trade_date'])
            daily = trades.groupby('trade_date').agg({
                'realized_pnl': 'sum',
                'strategy': 'count'
            }).reset_index()
            daily.columns = ['trade_date', 'daily_pnl', 'trades_count']

            for _, row in daily.iterrows():
                try:
                    daily_pnl_val = float(row['daily_pnl'] or 0)
                    cumulative_pnl += daily_pnl_val
                    current_equity = starting_equity + cumulative_pnl
                    peak_equity = max(peak_equity, current_equity)
                    drawdown = (peak_equity - current_equity) / peak_equity * 100 if peak_equity > 0 else 0
                    max_drawdown = max(max_drawdown, drawdown)

                    trade_date = row['trade_date']
                    if pd.isna(trade_date) or trade_date is None:
                        continue

                    equity_data.append({
                        "timestamp": int(trade_date.timestamp()),
                        "date": trade_date.strftime('%Y-%m-%d'),
                        "equity": safe_round(current_equity),
                        "pnl": safe_round(cumulative_pnl),
                        "daily_pnl": safe_round(daily_pnl_val),
                        "total_return_pct": safe_round(cumulative_pnl / starting_equity * 100),
                        "max_drawdown_pct": safe_round(max_drawdown)
                    })
                except Exception as row_error:
                    logger.warning(f"Skipping trade row due to error: {row_error}")
                    continue

            return {
                "success": True,
                "data": equity_data,
                "total_pnl": safe_round(cumulative_pnl),
                "starting_equity": starting_equity,
                "max_drawdown_pct": safe_round(max_drawdown)
            }

        conn.close()

        # Format snapshot data - calculate drawdown on the fly
        equity_data = []
        peak_equity = starting_equity
        max_drawdown = 0
        prev_pnl = 0

        for _, row in snapshots.iterrows():
            try:
                current_equity = float(row['account_value'] or starting_equity)
                current_pnl = float(row['total_realized_pnl'] or 0)
                daily_pnl = current_pnl - prev_pnl
                prev_pnl = current_pnl

                peak_equity = max(peak_equity, current_equity)
                drawdown = (peak_equity - current_equity) / peak_equity * 100 if peak_equity > 0 else 0
                max_drawdown = max(max_drawdown, drawdown)

                # Safely handle timestamp conversion
                snapshot_date = row['snapshot_date']
                if pd.isna(snapshot_date) or snapshot_date is None:
                    continue  # Skip rows with null dates

                equity_data.append({
                    "timestamp": int(pd.Timestamp(snapshot_date).timestamp()),
                    "date": str(snapshot_date),
                    "equity": safe_round(current_equity),
                    "pnl": safe_round(current_pnl),
                    "daily_pnl": safe_round(daily_pnl),
                    "total_return_pct": safe_round(row['total_return_pct']),
                    "max_drawdown_pct": safe_round(drawdown)
                })
            except Exception as row_error:
                logger.warning(f"Skipping equity snapshot row due to error: {row_error}")
                continue

        # Safely get total_pnl from the last snapshot
        total_pnl = 0
        if len(equity_data) > 0:
            # Use the last equity_data entry's pnl value (already processed and safe)
            total_pnl = equity_data[-1].get('pnl', 0)
        elif len(snapshots) > 0:
            try:
                last_pnl = snapshots['total_realized_pnl'].iloc[-1]
                total_pnl = safe_round(last_pnl) if last_pnl is not None and not pd.isna(last_pnl) else 0
            except (IndexError, KeyError):
                total_pnl = 0

        return {
            "success": True,
            "data": equity_data,
            "total_pnl": total_pnl,
            "starting_equity": starting_equity,
            "max_drawdown_pct": safe_round(max_drawdown)
        }
    except Exception as e:
        import traceback
        logger.error(f"equity-curve failed: {type(e).__name__}: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        if conn:
            try:
                conn.close()
            except Exception:
                pass
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {str(e)}")


@router.get("/strategies")
async def get_strategies(symbol: str = None):
    """Get all trading strategies and their performance.

    Args:
        symbol: Optional - filter by symbol (SPY, SPX, etc). If None, returns ALL symbols combined.
    """
    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        if symbol:
            cursor.execute("""
                SELECT
                    strategy,
                    COUNT(*) as total_trades,
                    SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as winning_trades,
                    SUM(realized_pnl) as total_pnl,
                    AVG(realized_pnl) as avg_pnl,
                    MAX(exit_date) as last_trade_date
                FROM autonomous_closed_trades
                WHERE symbol = %s
                GROUP BY strategy
                ORDER BY total_pnl DESC
            """, (symbol.upper(),))
        else:
            # Show ALL symbols with symbol breakdown
            cursor.execute("""
                SELECT
                    strategy,
                    symbol,
                    COUNT(*) as total_trades,
                    SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as winning_trades,
                    SUM(realized_pnl) as total_pnl,
                    AVG(realized_pnl) as avg_pnl,
                    MAX(exit_date) as last_trade_date
                FROM autonomous_closed_trades
                GROUP BY strategy, symbol
                ORDER BY total_pnl DESC
            """)
        strategies = cursor.fetchall()
        conn.close()

        result = []
        for s in strategies:
            total = s['total_trades'] or 0
            wins = s['winning_trades'] or 0
            result.append({
                "id": s['strategy'],
                "name": s['strategy'],
                "status": "active",
                "win_rate": safe_round((wins / total * 100) if total > 0 else 0),
                "total_trades": total,
                "pnl": safe_round(s['total_pnl'] or 0),
                "avg_pnl": safe_round(s['avg_pnl'] or 0),
                "last_trade_date": str(s['last_trade_date']) if s['last_trade_date'] else None
            })

        return {
            "success": True,
            "data": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/diagnostics")
async def get_trader_diagnostics():
    """
    Run comprehensive diagnostics on the autonomous trader
    Returns detailed status of all components to help debug issues
    """
    from datetime import time as dt_time
    from zoneinfo import ZoneInfo

    diagnostics = {
        "timestamp": datetime.now().isoformat(),
        "checks": {},
        "recommendations": []
    }

    # 1. Check market hours
    try:
        ct_now = datetime.now(ZoneInfo("America/Chicago"))
        market_open = dt_time(8, 30)
        market_close = dt_time(15, 0)
        current_time = ct_now.time()
        is_weekday = ct_now.weekday() < 5
        is_market_hours = is_weekday and market_open <= current_time <= market_close

        diagnostics["checks"]["market_hours"] = {
            "status": "open" if is_market_hours else "closed",
            "current_time_ct": ct_now.strftime('%I:%M:%S %p CT'),
            "day_of_week": ct_now.strftime('%A'),
            "is_trading_day": is_weekday,
            "market_open": "8:30 AM CT",
            "market_close": "3:00 PM CT"
        }

        if not is_market_hours:
            diagnostics["recommendations"].append("Market is closed - trader only runs during 8:30 AM - 3:00 PM CT, Mon-Fri")
    except Exception as e:
        diagnostics["checks"]["market_hours"] = {"error": str(e)}

    # 2. Check trader availability
    diagnostics["checks"]["trader_available"] = trader_available

    if not trader_available:
        diagnostics["recommendations"].append("Trader is not available - check startup logs for errors")

    # 3. Check live status
    if trader_available:
        try:
            live_status = trader.get_live_status()
            diagnostics["checks"]["live_status"] = live_status

            if live_status.get('timestamp'):
                try:
                    last_update = datetime.fromisoformat(live_status['timestamp'].replace('Z', '+00:00'))
                    now = datetime.now(last_update.tzinfo) if last_update.tzinfo else datetime.now()
                    age_minutes = (now - last_update).total_seconds() / 60
                    diagnostics["checks"]["live_status"]["age_minutes"] = round(age_minutes, 1)

                    if age_minutes > 10:
                        diagnostics["checks"]["live_status"]["stale"] = True
                        diagnostics["recommendations"].append(f"Status is {age_minutes:.0f} minutes old - scheduler thread may have crashed")
                except (ValueError, TypeError, AttributeError):
                    pass
        except Exception as e:
            diagnostics["checks"]["live_status"] = {"error": str(e)}

    # 4. Check configuration
    if trader_available:
        try:
            config = {
                "capital": trader.get_config('capital'),
                "mode": trader.get_config('mode'),
                "signal_only": trader.get_config('signal_only'),
                "last_trade_date": trader.get_config('last_trade_date'),
                "auto_execute": trader.get_config('auto_execute')
            }
            diagnostics["checks"]["config"] = config

            if config.get('signal_only', '').lower() == 'true':
                diagnostics["recommendations"].append("signal_only mode is ENABLED - trades will NOT auto-execute!")
        except Exception as e:
            diagnostics["checks"]["config"] = {"error": str(e)}

    # 5. Check database tables
    try:
        conn = get_connection()
        c = conn.cursor()

        tables = {}
        for table in ['autonomous_live_status', 'autonomous_trade_log', 'autonomous_open_positions',
                      'autonomous_closed_trades', 'autonomous_config', 'autonomous_trader_logs']:
            try:
                c.execute(f"SELECT COUNT(*) FROM {table}")
                tables[table] = c.fetchone()[0]
            except Exception as e:
                tables[table] = f"Error: {e}"

        diagnostics["checks"]["database_tables"] = tables
        conn.close()
    except Exception as e:
        diagnostics["checks"]["database_tables"] = {"error": str(e)}

    # 6. Check recent activity
    try:
        conn = get_connection()
        c = conn.cursor()

        c.execute("""
            SELECT action, details, date, time, success
            FROM autonomous_trade_log
            ORDER BY id DESC
            LIMIT 5
        """)
        recent_logs = []
        for row in c.fetchall():
            recent_logs.append({
                "action": row[0],
                "details": str(row[1])[:100] if row[1] else None,
                "timestamp": f"{row[2]} {row[3]}",
                "success": row[4]
            })
        diagnostics["checks"]["recent_activity"] = recent_logs

        c.execute("SELECT COUNT(*) FROM autonomous_open_positions")
        diagnostics["checks"]["open_positions"] = c.fetchone()[0]

        conn.close()
    except Exception as e:
        diagnostics["checks"]["recent_activity"] = {"error": str(e)}

    # 7. Summary
    has_issues = len(diagnostics["recommendations"]) > 0
    diagnostics["summary"] = {
        "healthy": not has_issues,
        "issues_found": len(diagnostics["recommendations"])
    }

    return {"success": True, "data": diagnostics}


@router.get("/live-status")
async def get_trader_live_status():
    """
    Get real-time "thinking out loud" status from autonomous trader
    Shows what the trader is currently doing and its analysis
    """
    if not trader_available:
        return {
            "success": False,
            "message": "Trader not configured",
            "data": {
                "status": "OFFLINE",
                "current_action": "Trader service not available",
                "is_working": False
            }
        }

    try:
        live_status = trader.get_live_status()
        return {
            "success": True,
            "data": live_status
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/trades")
async def get_trader_trades(limit: int = 10, symbol: str = None):
    """Get recent trades from autonomous trader - combines open and closed positions.

    Args:
        limit: Max trades to return (default 10, max 100)
        symbol: Optional - filter by symbol (SPY, SPX, etc). If None, returns ALL symbols.
    """
    if not trader_available:
        return {
            "success": False,
            "message": "Trader not configured",
            "data": []
        }

    limit = max(1, min(limit, 100))

    conn = None
    try:
        import pandas as pd
        import numpy as np

        conn = get_connection()

        # Support multi-symbol: if symbol provided, filter; otherwise show ALL
        symbol_filter_open = f"WHERE symbol = '{symbol.upper()}'" if symbol else ""
        symbol_filter_closed = f"WHERE symbol = '{symbol.upper()}'" if symbol else ""

        open_trades = pd.read_sql_query(f"""
            SELECT id, symbol, strategy, strike, option_type,
                   contracts, entry_date, entry_time, entry_price,
                   COALESCE(unrealized_pnl, 0) as unrealized_pnl,
                   'OPEN' as status,
                   NULL::date as exit_date, NULL::time as exit_time,
                   NULL::numeric as exit_price,
                   NULL::numeric as realized_pnl, NULL::text as exit_reason
            FROM autonomous_open_positions
            {symbol_filter_open}
            ORDER BY entry_date DESC, entry_time DESC
            LIMIT %s
        """, conn, params=(int(limit),))

        closed_trades = pd.read_sql_query(f"""
            SELECT id, symbol, strategy, strike, option_type,
                   contracts, entry_date, entry_time, entry_price,
                   COALESCE(realized_pnl, 0) as unrealized_pnl,
                   'CLOSED' as status, exit_date, exit_time,
                   exit_price, realized_pnl, exit_reason
            FROM autonomous_closed_trades
            {symbol_filter_closed}
            ORDER BY COALESCE(exit_date, entry_date) DESC, COALESCE(exit_time, entry_time) DESC
            LIMIT %s
        """, conn, params=(int(limit),))

        conn.close()

        all_trades = pd.concat([open_trades, closed_trades], ignore_index=True)
        if not all_trades.empty:
            all_trades = all_trades.sort_values(
                by=['entry_date', 'entry_time'],
                ascending=[False, False]
            ).head(limit)

            # Replace inf/-inf/nan with None for JSON compatibility
            all_trades = all_trades.replace([np.inf, -np.inf], np.nan)

        # Convert to list and clean NaN values
        trades_list = []
        if not all_trades.empty:
            for record in all_trades.to_dict('records'):
                cleaned = {}
                for k, v in record.items():
                    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                        cleaned[k] = None
                    else:
                        cleaned[k] = v
                trades_list.append(cleaned)

        return {
            "success": True,
            "data": trades_list
        }
    except Exception as e:
        if conn:
            try:
                conn.close()
            except Exception:
                pass
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/trade-log")
async def get_trade_log():
    """Get today's trade activity from autonomous_trade_activity table"""
    from fastapi.responses import JSONResponse

    if not trader_available:
        return JSONResponse({
            "success": False,
            "message": "Trader not configured",
            "data": []
        })

    try:
        import pandas as pd

        conn = get_connection()

        from core.intelligence_and_strategies import get_local_time
        today = get_local_time('US/Central').strftime('%Y-%m-%d')

        log_entries = pd.read_sql_query("""
            SELECT
                id,
                activity_date as date,
                activity_time as time,
                action_type as action,
                details,
                position_id,
                pnl_impact as pnl,
                success,
                error_message
            FROM autonomous_trade_activity
            WHERE activity_date = %s
            ORDER BY activity_time DESC
        """, conn, params=(today,))
        conn.close()

        if not log_entries.empty:
            log_entries = log_entries.replace([float('inf'), float('-inf')], None)
            log_list = []
            for record in log_entries.to_dict('records'):
                cleaned_record = {}
                for key, value in record.items():
                    if isinstance(value, float):
                        if math.isnan(value) or math.isinf(value):
                            cleaned_record[key] = None
                        else:
                            cleaned_record[key] = value
                    else:
                        cleaned_record[key] = value
                log_list.append(cleaned_record)
        else:
            log_list = []

        return JSONResponse({
            "success": True,
            "data": log_list
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/execute")
async def execute_trader_cycle():
    """
    Execute one autonomous trader cycle NOW

    This endpoint:
    1. Finds and executes a daily trade (if not already traded today)
    2. Manages existing open positions
    3. Returns the results

    PROTECTED: Requires ENABLE_LIVE_TRADING=true
    """
    # GUARD: Check if live trading is enabled
    require_live_trading()

    if not trader_available:
        return {
            "success": False,
            "message": "Trader not configured",
            "error": "Autonomous trader module not available"
        }

    try:
        from backend.api.dependencies import api_client

        logger.info("=" * 60)
        logger.info(f"MANUAL TRADER EXECUTION - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("=" * 60)

        trader.update_live_status(
            status='MANUAL_EXECUTION',
            action='Manual execution triggered via API',
            analysis='User initiated trader cycle'
        )

        results = {
            "new_trade": None,
            "closed_positions": [],
            "message": ""
        }

        logger.info("Checking for new trade opportunity...")
        try:
            position_id = trader.find_and_execute_daily_trade(api_client)

            if position_id:
                logger.info(f"SUCCESS: Opened position #{position_id}")
                results["new_trade"] = {
                    "position_id": position_id,
                    "message": f"Successfully opened position #{position_id}"
                }
                results["message"] = f"New position #{position_id} opened"
            else:
                logger.info("No new trade (already traded today or no setup found)")
                results["message"] = "No new trade (already traded today or no qualifying setup)"

        except Exception as e:
            logger.error(f"ERROR during trade execution: {type(e).__name__}")
            results["message"] = f"Trade execution error: {str(e)}"

        logger.info("Checking open positions for exit conditions...")
        try:
            actions = trader.auto_manage_positions(api_client)

            if actions:
                logger.info(f"SUCCESS: Closed {len(actions)} position(s)")
                for action in actions:
                    logger.info(f"- {action['strategy']}: P&L ${action['pnl']:+,.2f} ({action['pnl_pct']:+.1f}%) - {action['reason']}")

                results["closed_positions"] = actions
                if not results["message"]:
                    results["message"] = f"Closed {len(actions)} position(s)"
                else:
                    results["message"] += f", closed {len(actions)} position(s)"
            else:
                logger.info("All positions look good - no exits needed")
                if not results["message"]:
                    results["message"] = "No exits needed"

        except Exception as e:
            logger.error(f"ERROR during position management: {type(e).__name__}")

        perf = trader.get_performance()
        logger.info("PERFORMANCE SUMMARY:")
        logger.info(f"Starting Capital: ${perf['starting_capital']:,.0f}")
        logger.info(f"Current Value: ${perf['current_value']:,.2f}")
        logger.info(f"Total P&L: ${perf['total_pnl']:+,.2f} ({perf['return_pct']:+.2f}%)")
        logger.info(f"Total Trades: {perf['total_trades']}")
        logger.info(f"Open Positions: {perf['open_positions']}")
        logger.info(f"Win Rate: {perf['win_rate']:.1f}%")

        logger.info("CYCLE COMPLETE")

        return {
            "success": True,
            "data": {
                **results,
                "performance": perf
            }
        }

    except Exception as e:
        logger.error(f" CRITICAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/strategies/{strategy_id}/toggle")
async def toggle_strategy(strategy_id: str, enabled: bool = True):
    """
    Toggle a strategy on/off

    PROTECTED: Requires ENABLE_LIVE_TRADING=true
    """
    # GUARD: Check if live trading is enabled
    require_live_trading()

    if not trader_available:
        return {"success": False, "message": "Trader not configured"}

    try:
        conn = get_connection()
        c = conn.cursor()

        # NOTE: Table 'strategy_config' defined in db/config_and_database.py (single source of truth)

        strategy_name = strategy_id.replace('_', ' ').title()

        c.execute("""
            INSERT INTO strategy_config (strategy_name, enabled, updated_at)
            VALUES (%s, %s, NOW())
            ON CONFLICT (strategy_name) DO UPDATE SET
                enabled = EXCLUDED.enabled,
                updated_at = NOW()
        """, (strategy_name, enabled))

        conn.commit()
        conn.close()

        return {
            "success": True,
            "message": f"Strategy '{strategy_name}' {'enabled' if enabled else 'disabled'}",
            "strategy": strategy_name,
            "enabled": enabled
        }
    except Exception as e:
        logger.error(f"Error toggling strategy: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/strategies/config")
async def get_strategy_configs():
    """Get all strategy configurations (enabled/disabled status)"""
    if not trader_available:
        return {"success": False, "data": {}}

    try:
        conn = get_connection()

        c = conn.cursor()
        c.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'strategy_config'
            )
        """)
        table_exists = c.fetchone()[0]

        if not table_exists:
            conn.close()
            return {"success": True, "data": {}}

        import pandas as pd
        df = pd.read_sql_query("SELECT strategy_name, enabled FROM strategy_config", conn)
        conn.close()

        config = {row['strategy_name']: row['enabled'] for _, row in df.iterrows()}
        return {"success": True, "data": config}
    except Exception as e:
        logger.error(f"Error getting strategy configs: {e}")
        return {"success": False, "data": {}}


# ============================================================================
# UNIFIED PORTFOLIO DASHBOARD - Combined SPY + SPX View
# ============================================================================

@router.get("/portfolio/unified")
async def get_unified_portfolio():
    """
    Get unified portfolio dashboard combining ALL symbols (SPY, SPX, etc.)

    Returns:
    - Total positions across all symbols
    - Aggregate P&L (realized + unrealized)
    - Per-symbol breakdown
    - Portfolio Greeks exposure
    - Risk metrics
    - Performance summary

    This is the master view for traders managing multiple underlying symbols.
    """
    try:
        import pandas as pd
        import numpy as np
        from decimal import Decimal

        conn = get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Get all open positions grouped by symbol
        # Use defensive query that handles missing Greek columns
        try:
            cursor.execute("""
                SELECT
                    symbol,
                    COUNT(*) as position_count,
                    SUM(contracts) as total_contracts,
                    SUM(unrealized_pnl) as unrealized_pnl,
                    SUM(COALESCE(current_delta, entry_delta, 0) * contracts * 100) as net_delta,
                    SUM(COALESCE(current_gamma, entry_gamma, 0) * contracts * 100) as net_gamma,
                    SUM(COALESCE(current_theta, entry_theta, 0) * contracts * 100) as net_theta,
                    SUM(COALESCE(current_vega, entry_vega, 0) * contracts * 100) as net_vega
                FROM autonomous_open_positions
                GROUP BY symbol
                ORDER BY symbol
            """)
        except Exception as col_error:
            # Fallback if Greek columns don't exist yet
            logger.warning(f"Greek columns not available, using basic query: {col_error}")
            cursor.execute("""
                SELECT
                    symbol,
                    COUNT(*) as position_count,
                    SUM(contracts) as total_contracts,
                    SUM(unrealized_pnl) as unrealized_pnl,
                    0 as net_delta,
                    0 as net_gamma,
                    0 as net_theta,
                    0 as net_vega
                FROM autonomous_open_positions
                GROUP BY symbol
                ORDER BY symbol
            """)
        symbol_positions = cursor.fetchall()

        # Get all positions with full detail - handle missing columns gracefully
        try:
            cursor.execute("""
                SELECT
                    id, symbol, strategy, strike, option_type, contracts,
                    entry_price, current_price, unrealized_pnl, entry_date,
                    expiration_date, contract_symbol, gex_regime,
                    COALESCE(entry_iv, 0) as entry_iv,
                    COALESCE(entry_delta, 0) as entry_delta,
                    COALESCE(entry_gamma, 0) as entry_gamma,
                    COALESCE(entry_theta, 0) as entry_theta,
                    COALESCE(entry_vega, 0) as entry_vega,
                    COALESCE(current_iv, 0) as current_iv,
                    COALESCE(current_delta, 0) as current_delta,
                    COALESCE(current_gamma, 0) as current_gamma,
                    COALESCE(current_theta, 0) as current_theta,
                    COALESCE(current_vega, 0) as current_vega
                FROM autonomous_open_positions
                ORDER BY symbol, entry_date DESC
            """)
        except Exception as col_error:
            # Fallback if Greek columns don't exist yet
            logger.warning(f"Greek columns not available for positions detail: {col_error}")
            cursor.execute("""
                SELECT
                    id, symbol, strategy, strike, option_type, contracts,
                    entry_price, current_price, unrealized_pnl, entry_date,
                    NULL as expiration_date, NULL as contract_symbol, gex_regime,
                    0 as entry_iv, 0 as entry_delta, 0 as entry_gamma, 0 as entry_theta, 0 as entry_vega,
                    0 as current_iv, 0 as current_delta, 0 as current_gamma, 0 as current_theta, 0 as current_vega
                FROM autonomous_open_positions
                ORDER BY symbol, entry_date DESC
            """)
        all_positions = cursor.fetchall()

        # Get realized P&L by symbol
        cursor.execute("""
            SELECT
                symbol,
                COUNT(*) as trade_count,
                SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as winners,
                SUM(CASE WHEN realized_pnl <= 0 THEN 1 ELSE 0 END) as losers,
                SUM(realized_pnl) as total_pnl,
                AVG(realized_pnl) as avg_pnl,
                MAX(realized_pnl) as best_trade,
                MIN(realized_pnl) as worst_trade
            FROM autonomous_closed_trades
            GROUP BY symbol
            ORDER BY symbol
        """)
        symbol_performance = cursor.fetchall()

        # Get account config
        cursor.execute("SELECT value FROM autonomous_config WHERE key = 'capital'")
        capital_row = cursor.fetchone()
        starting_capital = float(capital_row['value']) if capital_row else 1000000.0

        # Calculate FRESH unrealized P&L from source bot tables using MTM
        # This bypasses stale values in autonomous_open_positions table
        fresh_unrealized = _calculate_portfolio_unrealized_pnl(cursor)
        unrealized_by_symbol = fresh_unrealized.get('by_symbol', {})
        unrealized_by_bot = fresh_unrealized.get('by_bot', {})
        unrealized_method = fresh_unrealized.get('method', 'estimation')

        conn.close()

        # Calculate aggregate metrics using FRESH unrealized P&L
        total_unrealized = fresh_unrealized.get('total_unrealized_pnl', 0.0)
        total_realized = sum(float(p.get('total_pnl', 0) or 0) for p in symbol_performance)
        total_positions = sum(int(p.get('position_count', 0) or 0) for p in symbol_positions)
        total_contracts = sum(int(p.get('total_contracts', 0) or 0) for p in symbol_positions)

        # Calculate portfolio Greeks
        portfolio_delta = sum(float(p.get('net_delta', 0) or 0) for p in symbol_positions)
        portfolio_gamma = sum(float(p.get('net_gamma', 0) or 0) for p in symbol_positions)
        portfolio_theta = sum(float(p.get('net_theta', 0) or 0) for p in symbol_positions)
        portfolio_vega = sum(float(p.get('net_vega', 0) or 0) for p in symbol_positions)

        # Calculate overall performance
        total_trades = sum(int(p.get('trade_count', 0) or 0) for p in symbol_performance)
        total_winners = sum(int(p.get('winners', 0) or 0) for p in symbol_performance)
        win_rate = (total_winners / total_trades * 100) if total_trades > 0 else 0

        current_equity = starting_capital + total_realized + total_unrealized
        total_return_pct = ((current_equity - starting_capital) / starting_capital * 100) if starting_capital > 0 else 0

        # Format per-symbol data
        def format_decimal(val):
            if val is None:
                return 0
            if isinstance(val, Decimal):
                return float(val)
            return val

        symbols_breakdown = []
        for sp in symbol_positions:
            # Find matching performance data
            perf = next((p for p in symbol_performance if p['symbol'] == sp['symbol']), {})
            # Use FRESH unrealized P&L from MTM instead of stale unified table value
            symbol_name = sp['symbol']
            fresh_symbol_unrealized = unrealized_by_symbol.get(symbol_name, 0.0)
            symbols_breakdown.append({
                'symbol': symbol_name,
                'open_positions': format_decimal(sp.get('position_count', 0)),
                'total_contracts': format_decimal(sp.get('total_contracts', 0)),
                'unrealized_pnl': round(fresh_symbol_unrealized, 2),
                'realized_pnl': round(format_decimal(perf.get('total_pnl', 0)), 2),
                'net_pnl': round(fresh_symbol_unrealized + format_decimal(perf.get('total_pnl', 0)), 2),
                'trade_count': format_decimal(perf.get('trade_count', 0)),
                'win_rate': round((format_decimal(perf.get('winners', 0)) / format_decimal(perf.get('trade_count', 1))) * 100, 1) if perf.get('trade_count', 0) > 0 else 0,
                # Portfolio Greeks for this symbol
                'net_delta': round(format_decimal(sp.get('net_delta', 0)), 2),
                'net_gamma': round(format_decimal(sp.get('net_gamma', 0)), 4),
                'net_theta': round(format_decimal(sp.get('net_theta', 0)), 2),
                'net_vega': round(format_decimal(sp.get('net_vega', 0)), 2)
            })

        # Format positions for JSON
        formatted_positions = []
        for p in all_positions:
            formatted_positions.append({
                'id': p['id'],
                'symbol': p['symbol'],
                'strategy': p['strategy'],
                'strike': float(p['strike']) if p['strike'] else 0,
                'option_type': p['option_type'],
                'contracts': p['contracts'],
                'entry_price': float(p['entry_price']) if p['entry_price'] else 0,
                'current_price': float(p['current_price']) if p['current_price'] else 0,
                'unrealized_pnl': round(float(p['unrealized_pnl']) if p['unrealized_pnl'] else 0, 2),
                'entry_date': str(p['entry_date']) if p['entry_date'] else None,
                'expiration_date': str(p['expiration_date']) if p['expiration_date'] else None,
                'greeks': {
                    'entry': {
                        'iv': float(p['entry_iv']) if p['entry_iv'] else None,
                        'delta': float(p['entry_delta']) if p['entry_delta'] else None,
                        'gamma': float(p['entry_gamma']) if p['entry_gamma'] else None,
                        'theta': float(p['entry_theta']) if p['entry_theta'] else None,
                        'vega': float(p['entry_vega']) if p['entry_vega'] else None
                    },
                    'current': {
                        'iv': float(p['current_iv']) if p['current_iv'] else None,
                        'delta': float(p['current_delta']) if p['current_delta'] else None,
                        'gamma': float(p['current_gamma']) if p['current_gamma'] else None,
                        'theta': float(p['current_theta']) if p['current_theta'] else None,
                        'vega': float(p['current_vega']) if p['current_vega'] else None
                    }
                }
            })

        return {
            "success": True,
            "data": {
                "summary": {
                    "starting_capital": starting_capital,
                    "current_equity": round(current_equity, 2),
                    "total_pnl": round(total_realized + total_unrealized, 2),
                    "total_return_pct": round(total_return_pct, 2),
                    "realized_pnl": round(total_realized, 2),
                    "unrealized_pnl": round(total_unrealized, 2),
                    "unrealized_pnl_method": unrealized_method,
                    "total_positions": total_positions,
                    "total_contracts": total_contracts,
                    "total_trades": total_trades,
                    "win_rate": round(win_rate, 1)
                },
                "portfolio_greeks": {
                    "net_delta": round(portfolio_delta, 2),
                    "net_gamma": round(portfolio_gamma, 4),
                    "net_theta": round(portfolio_theta, 2),
                    "net_vega": round(portfolio_vega, 2),
                    "description": "Aggregate Greeks exposure across all positions"
                },
                "by_symbol": symbols_breakdown,
                "unrealized_by_bot": unrealized_by_bot,
                "positions": formatted_positions,
                "timestamp": datetime.now().isoformat()
            }
        }
    except Exception as e:
        logger.error(f"Error getting unified portfolio: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# QUANT MODULE ENDPOINTS - Expose ML/Monte Carlo/Ensemble metrics to UI
# =============================================================================

@router.get("/quant/status")
async def get_quant_status():
    """
    Get overall status of quant modules.
    Shows which modules are available and their current state.
    """
    status = {
        "ml_classifier": {"available": False, "trained": False, "last_prediction": None},
        "monte_carlo_kelly": {"available": False, "simulations": 0},
        "ensemble_strategy": {"available": False, "active_strategies": 0},
        "walk_forward": {"available": False, "last_validation": None},
    }

    try:
        from quant import _DEPENDENCIES_AVAILABLE
        if not _DEPENDENCIES_AVAILABLE:
            return {
                "success": True,
                "data": {
                    "quant_available": False,
                    "message": "Quant modules require numpy, pandas, scipy. Install with: pip install numpy pandas scipy scikit-learn",
                    "modules": status
                }
            }
    except ImportError:
        return {
            "success": True,
            "data": {
                "quant_available": False,
                "message": "Quant module not installed",
                "modules": status
            }
        }

    # Check ML Classifier
    try:
        from quant.ml_regime_classifier import MLRegimeClassifier
        classifier = MLRegimeClassifier("SPY")
        status["ml_classifier"] = {
            "available": True,
            "trained": classifier.is_trained,
            "model_version": getattr(classifier, 'model_version', 'rule-based'),
            "features_count": len(classifier.feature_names) if hasattr(classifier, 'feature_names') else 17
        }
    except Exception as e:
        logger.debug(f"ML classifier not available: {e}")

    # Check Monte Carlo Kelly
    try:
        from quant.monte_carlo_kelly import MonteCarloKelly
        mc = MonteCarloKelly()
        status["monte_carlo_kelly"] = {
            "available": True,
            "simulations": mc.num_simulations,
            "trades_per_sim": mc.num_trades_per_sim
        }
    except Exception as e:
        logger.debug(f"Monte Carlo Kelly not available: {e}")

    # Check Ensemble Strategy
    try:
        from quant.ensemble_strategy import EnsembleStrategyWeighter
        weighter = EnsembleStrategyWeighter("SPY")
        status["ensemble_strategy"] = {
            "available": True,
            "active_strategies": len(weighter.strategies) if hasattr(weighter, 'strategies') else 5,
            "default_weights": weighter.default_weights if hasattr(weighter, 'default_weights') else {}
        }
    except Exception as e:
        logger.debug(f"Ensemble strategy not available: {e}")

    # Check Walk Forward
    try:
        from quant.walk_forward_optimizer import WalkForwardOptimizer
        status["walk_forward"] = {
            "available": True,
            "default_train_days": 60,
            "default_test_days": 20
        }
    except Exception as e:
        logger.debug(f"Walk forward not available: {e}")

    return {
        "success": True,
        "data": {
            "quant_available": True,
            "modules": status,
            "timestamp": datetime.now().isoformat()
        }
    }


@router.get("/quant/ml-prediction/{symbol}")
async def get_ml_prediction(symbol: str):
    """
    Get current ML regime prediction for a symbol.
    Returns predicted action, confidence, and feature importance.
    """
    try:
        from quant.ml_regime_classifier import get_ml_regime_prediction
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="Quant ML module not available. Install dependencies: pip install numpy pandas scipy scikit-learn"
        )

    # Get current market data for the symbol
    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Get latest GEX data
        cursor.execute("""
            SELECT gex_percentile, iv_rank, distance_to_flip_pct, vix
            FROM gex_analysis
            WHERE symbol = %s
            ORDER BY timestamp DESC
            LIMIT 1
        """, (symbol.upper(),))
        gex_data = cursor.fetchone()

        cursor.close()
        conn.close()

        if not gex_data:
            # Use default values if no data
            gex_data = {
                'gex_percentile': 50,
                'iv_rank': 50,
                'distance_to_flip_pct': 0,
                'vix': 20
            }

        # Get prediction
        prediction = get_ml_regime_prediction(
            symbol=symbol.upper(),
            gex_percentile=float(gex_data.get('gex_percentile', 50)),
            iv_rank=float(gex_data.get('iv_rank', 50)),
            distance_to_flip=float(gex_data.get('distance_to_flip_pct', 0)),
            vix=float(gex_data.get('vix', 20))
        )

        return {
            "success": True,
            "data": {
                "symbol": symbol.upper(),
                "predicted_action": prediction.predicted_action.value,
                "confidence": prediction.confidence,
                "is_ml_trained": prediction.is_trained,
                "model_version": prediction.model_version,
                "probabilities": prediction.probabilities,
                "feature_importance": prediction.feature_importance if hasattr(prediction, 'feature_importance') else {},
                "input_features": {
                    "gex_percentile": gex_data.get('gex_percentile'),
                    "iv_rank": gex_data.get('iv_rank'),
                    "distance_to_flip": gex_data.get('distance_to_flip_pct'),
                    "vix": gex_data.get('vix')
                },
                "timestamp": datetime.now().isoformat()
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting ML prediction: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/quant/kelly-stress-test/{symbol}")
async def get_kelly_stress_test(symbol: str):
    """
    Get Monte Carlo Kelly stress test results for a symbol.
    Returns optimal, safe, and conservative Kelly percentages with ruin probabilities.
    """
    try:
        from quant.monte_carlo_kelly import get_safe_position_size
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="Quant Monte Carlo module not available. Install dependencies: pip install numpy pandas scipy"
        )

    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Get strategy performance stats
        cursor.execute("""
            SELECT
                COUNT(*) as total_trades,
                COUNT(CASE WHEN pnl > 0 THEN 1 END) as winners,
                AVG(CASE WHEN pnl > 0 THEN pnl END) as avg_win,
                AVG(CASE WHEN pnl < 0 THEN ABS(pnl) END) as avg_loss
            FROM trades
            WHERE symbol = %s AND exit_price IS NOT NULL
        """, (symbol.upper(),))
        stats = cursor.fetchone()

        cursor.close()
        conn.close()

        if not stats or stats['total_trades'] < 5:
            # Not enough trades for meaningful stress test
            return {
                "success": True,
                "data": {
                    "symbol": symbol.upper(),
                    "status": "insufficient_data",
                    "message": f"Need at least 5 closed trades for stress test (have {stats['total_trades'] if stats else 0})",
                    "recommendation": "Continue paper trading to build sample size"
                }
            }

        win_rate = stats['winners'] / stats['total_trades'] if stats['total_trades'] > 0 else 0.5
        avg_win = float(stats['avg_win']) if stats['avg_win'] else 10
        avg_loss = float(stats['avg_loss']) if stats['avg_loss'] else 10

        # Run stress test
        result = get_safe_position_size(
            win_rate=win_rate,
            avg_win=avg_win,
            avg_loss=avg_loss,
            sample_size=stats['total_trades'],
            account_size=100000,  # Normalized to 100k
            max_risk_pct=25.0
        )

        return {
            "success": True,
            "data": {
                "symbol": symbol.upper(),
                "input_stats": {
                    "total_trades": stats['total_trades'],
                    "win_rate": round(win_rate * 100, 1),
                    "avg_win": round(avg_win, 2),
                    "avg_loss": round(avg_loss, 2),
                    "payoff_ratio": round(avg_win / avg_loss, 2) if avg_loss > 0 else 0
                },
                "kelly_results": {
                    "kelly_optimal_pct": result.get('kelly_optimal', 0),
                    "kelly_safe_pct": result.get('kelly_safe', 0),
                    "kelly_conservative_pct": result.get('kelly_conservative', 0),
                    "recommended_pct": result.get('position_size_pct', 0)
                },
                "risk_metrics": {
                    "prob_ruin_optimal": result.get('prob_ruin_optimal', 0),
                    "prob_ruin_safe": result.get('prob_ruin_safe', 0),
                    "prob_50pct_drawdown": result.get('prob_50pct_drawdown_safe', 0),
                    "uncertainty_level": result.get('uncertainty_level', 'unknown')
                },
                "recommendation": result.get('recommendation', ''),
                "timestamp": datetime.now().isoformat()
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error running Kelly stress test: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/quant/ensemble-signal/{symbol}")
async def get_ensemble_signal_endpoint(symbol: str):
    """
    Get current ensemble signal combining multiple strategies.
    Returns weighted signal from GEX, ML, RSI, volatility surface, etc.
    """
    try:
        from quant.ensemble_strategy import get_ensemble_signal
        from quant.ml_regime_classifier import get_ml_regime_prediction
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="Quant ensemble module not available. Install dependencies: pip install numpy pandas scipy scikit-learn"
        )

    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Get GEX data
        cursor.execute("""
            SELECT gex_percentile, iv_rank, distance_to_flip_pct, vix,
                   recommended_action, confidence
            FROM gex_analysis
            WHERE symbol = %s
            ORDER BY timestamp DESC
            LIMIT 1
        """, (symbol.upper(),))
        gex_data = cursor.fetchone()

        cursor.close()
        conn.close()

        if not gex_data:
            return {
                "success": True,
                "data": {
                    "symbol": symbol.upper(),
                    "status": "no_data",
                    "message": "No GEX data available for this symbol"
                }
            }

        # Get ML prediction
        ml_pred = get_ml_regime_prediction(
            symbol=symbol.upper(),
            gex_percentile=float(gex_data.get('gex_percentile', 50)),
            iv_rank=float(gex_data.get('iv_rank', 50)),
            distance_to_flip=float(gex_data.get('distance_to_flip_pct', 0)),
            vix=float(gex_data.get('vix', 20))
        )

        # Get ensemble signal
        ensemble = get_ensemble_signal(
            symbol=symbol.upper(),
            gex_data={
                'recommended_action': gex_data.get('recommended_action', 'NEUTRAL'),
                'confidence': gex_data.get('confidence', 50)
            },
            ml_prediction={
                'predicted_action': ml_pred.predicted_action.value,
                'confidence': ml_pred.confidence,
                'is_trained': ml_pred.is_trained
            }
        )

        # Format component signals for response
        component_signals = []
        for sig in ensemble.component_signals:
            component_signals.append({
                'strategy': sig.strategy_name,
                'signal': sig.signal.value if hasattr(sig.signal, 'value') else str(sig.signal),
                'confidence': sig.confidence,
                'weight': sig.weight,
                'reason': sig.reason
            })

        return {
            "success": True,
            "data": {
                "symbol": symbol.upper(),
                "final_signal": ensemble.final_signal.value if hasattr(ensemble.final_signal, 'value') else str(ensemble.final_signal),
                "confidence": ensemble.confidence,
                "should_trade": ensemble.should_trade,
                "weights": {
                    "bullish": round(ensemble.bullish_weight, 2),
                    "bearish": round(ensemble.bearish_weight, 2),
                    "neutral": round(ensemble.neutral_weight, 2)
                },
                "component_signals": component_signals,
                "agreement_score": round(max(ensemble.bullish_weight, ensemble.bearish_weight, ensemble.neutral_weight) * 100, 1),
                "timestamp": datetime.now().isoformat()
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting ensemble signal: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/quant/recommendation/{symbol}")
async def get_quant_recommendation(symbol: str):
    """
    Get full quant recommendation combining all modules.
    This is the primary endpoint for trading decisions informed by quant analysis.
    """
    try:
        from quant.integration import get_quant_recommendation as get_recommendation
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="Quant integration module not available"
        )

    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Get current market data
        cursor.execute("""
            SELECT gex_percentile, iv_rank, distance_to_flip_pct, vix,
                   recommended_action, confidence, net_gex
            FROM gex_analysis
            WHERE symbol = %s
            ORDER BY timestamp DESC
            LIMIT 1
        """, (symbol.upper(),))
        gex_data = cursor.fetchone()

        # Get strategy stats
        cursor.execute("""
            SELECT
                COUNT(*) as total_trades,
                COUNT(CASE WHEN pnl > 0 THEN 1 END) as winners,
                AVG(CASE WHEN pnl > 0 THEN pnl END) as avg_win,
                AVG(CASE WHEN pnl < 0 THEN ABS(pnl) END) as avg_loss
            FROM trades
            WHERE symbol = %s AND exit_price IS NOT NULL
        """, (symbol.upper(),))
        trade_stats = cursor.fetchone()

        cursor.close()
        conn.close()

        if not gex_data:
            return {
                "success": True,
                "data": {
                    "symbol": symbol.upper(),
                    "status": "no_data",
                    "message": "No market data available"
                }
            }

        # Build market data dict
        market_data = {
            'gex_percentile': float(gex_data.get('gex_percentile', 50)),
            'iv_rank': float(gex_data.get('iv_rank', 50)),
            'distance_to_flip': float(gex_data.get('distance_to_flip_pct', 0)),
            'vix': float(gex_data.get('vix', 20)),
            'gex_action': gex_data.get('recommended_action', 'NEUTRAL'),
            'gex_confidence': gex_data.get('confidence', 50)
        }

        # Build strategy stats
        stats = None
        if trade_stats and trade_stats['total_trades'] >= 5:
            win_rate = trade_stats['winners'] / trade_stats['total_trades']
            stats = {
                'win_rate': win_rate,
                'avg_win': float(trade_stats['avg_win']) if trade_stats['avg_win'] else 10,
                'avg_loss': float(trade_stats['avg_loss']) if trade_stats['avg_loss'] else 10,
                'sample_size': trade_stats['total_trades']
            }

        # Get recommendation
        recommendation = get_recommendation(
            symbol=symbol.upper(),
            market_data=market_data,
            strategy_stats=stats
        )

        return {
            "success": True,
            "data": {
                "symbol": symbol.upper(),
                "action": recommendation.action,
                "confidence": recommendation.confidence,
                "should_trade": recommendation.should_trade,
                "position_size_pct": recommendation.position_size_pct,
                "reasoning": recommendation.reasoning,
                "ml_prediction": {
                    "action": recommendation.ml_prediction.predicted_action.value if recommendation.ml_prediction else None,
                    "confidence": recommendation.ml_prediction.confidence if recommendation.ml_prediction else None,
                    "is_trained": recommendation.ml_prediction.is_trained if recommendation.ml_prediction else False
                },
                "ensemble_signal": {
                    "signal": recommendation.ensemble_signal.final_signal.value if recommendation.ensemble_signal else None,
                    "confidence": recommendation.ensemble_signal.confidence if recommendation.ensemble_signal else None,
                    "agreement": recommendation.ensemble_signal.bullish_weight if recommendation.ensemble_signal else None
                },
                "kelly_sizing": {
                    "safe_pct": recommendation.kelly_result.get('kelly_safe', 0) if recommendation.kelly_result else None,
                    "optimal_pct": recommendation.kelly_result.get('kelly_optimal', 0) if recommendation.kelly_result else None,
                    "uncertainty": recommendation.kelly_result.get('uncertainty_level', 'unknown') if recommendation.kelly_result else None
                },
                "timestamp": datetime.now().isoformat()
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting quant recommendation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# BOT DECISION LOG ENDPOINTS - Export and monitor what/why/how for each trade
# =============================================================================

@router.get("/logs/decisions")
async def get_decision_logs(
    bot: str = None,
    start_date: str = None,
    end_date: str = None,
    decision_type: str = None,
    symbol: str = None,
    limit: int = 100
):
    """
    Get decision logs for all bots or a specific bot.

    Args:
        bot: Filter by bot name (PHOENIX, ATLAS, HERMES, ORACLE)
        start_date: Filter from date (YYYY-MM-DD)
        end_date: Filter to date (YYYY-MM-DD)
        decision_type: Filter by type (ENTRY_SIGNAL, STAY_FLAT, etc.)
        symbol: Filter by symbol (SPY, SPX)
        limit: Max records (default 100)

    Returns detailed decision logs with what/why/how for each decision.
    """
    try:
        from trading.decision_logger import export_decisions_json

        decisions = export_decisions_json(
            bot_name=bot,
            start_date=start_date,
            end_date=end_date,
            decision_type=decision_type,
            symbol=symbol,
            limit=min(limit, 1000)
        )

        return {
            "success": True,
            "data": {
                "count": len(decisions),
                "decisions": decisions,
                "filters": {
                    "bot": bot,
                    "start_date": start_date,
                    "end_date": end_date,
                    "decision_type": decision_type,
                    "symbol": symbol
                }
            }
        }
    except Exception as e:
        logger.error(f"Error getting decision logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/logs/decisions/export")
async def export_decision_logs_csv(
    bot: str = None,
    start_date: str = None,
    end_date: str = None,
    symbol: str = None
):
    """
    Export decision logs as CSV for download.

    Returns CSV with columns:
    timestamp, bot, decision_type, action, symbol, strategy, spot_price,
    vix, net_gex, regime, reason, position_size, pnl
    """
    try:
        from trading.decision_logger import export_decisions_csv
        from fastapi.responses import Response

        csv_content = export_decisions_csv(
            bot_name=bot,
            start_date=start_date,
            end_date=end_date,
            symbol=symbol
        )

        filename = f"alphagex_decisions_{bot or 'all'}_{datetime.now().strftime('%Y%m%d')}.csv"

        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )
    except Exception as e:
        logger.error(f"Error exporting decision logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/logs/summary")
async def get_decision_summary(bot: str = None, days: int = 7):
    """
    Get summary statistics for bot decisions.

    Args:
        bot: Filter by bot name (PHOENIX, ATLAS, HERMES, ORACLE)
        days: Number of days to look back (default 7)

    Returns:
        Summary with total decisions, trades, wins/losses, P&L by bot
    """
    try:
        from trading.decision_logger import get_bot_decision_summary

        summary = get_bot_decision_summary(bot_name=bot, days=days)

        return {
            "success": True,
            "data": {
                "period_days": days,
                "bot_filter": bot or "all",
                "summary": summary,
                "timestamp": datetime.now().isoformat()
            }
        }
    except Exception as e:
        logger.error(f"Error getting decision summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/logs/recent")
async def get_recent_decision_logs(bot: str = None, limit: int = 20):
    """
    Get recent decisions for dashboard display.

    Args:
        bot: Filter by bot name (PHOENIX, ATLAS, HERMES, ORACLE)
        limit: Number of recent decisions (default 20)

    Returns simplified decision records for quick viewing.
    """
    try:
        from trading.decision_logger import get_recent_decisions

        decisions = get_recent_decisions(bot_name=bot, limit=min(limit, 100))

        return {
            "success": True,
            "data": {
                "count": len(decisions),
                "bot_filter": bot or "all",
                "decisions": decisions,
                "timestamp": datetime.now().isoformat()
            }
        }
    except Exception as e:
        logger.error(f"Error getting recent decisions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/bots/status")
async def get_all_bots_status():
    """
    Get status of all trading bots.

    Returns status for: PHOENIX, ATLAS, HERMES, ORACLE
    """
    try:
        from trading.decision_logger import get_bot_decision_summary

        # Capital allocation configuration
        TOTAL_CAPITAL = 1_000_000
        RESERVE_CAPITAL = 100_000

        bots = {
            "PHOENIX": {
                "name": "PHOENIX",
                "description": "0DTE SPY/SPX Options Trader",
                "type": "autonomous",
                "scheduled": True,
                "schedule": "Hourly 10 AM - 3 PM ET (Mon-Fri)",
                "capital_allocation": 300_000,
                "capital_pct": 30,
                "strategy": "0DTE directional + premium selling",
                "data_sources": ["GEX", "IV Surface", "Psychology Rules", "ML Regime"]
            },
            "ATLAS": {
                "name": "ATLAS",
                "description": "SPX Cash-Secured Put Wheel",
                "type": "autonomous",
                "scheduled": True,
                "schedule": "Daily at 10:05 AM ET (Mon-Fri)",
                "capital_allocation": 400_000,
                "capital_pct": 40,
                "strategy": "Weekly CSP wheel with ML optimization",
                "data_sources": ["Backtester", "VIX", "Delta Targeting", "Walk-Forward"]
            },
            "ARES": {
                "name": "ARES",
                "description": "Aggressive Iron Condor (10% Monthly Target)",
                "type": "autonomous",
                "scheduled": True,
                "schedule": "8:30 AM - 3:30 PM CT (Mon-Fri), every 5 min",
                "capital_allocation": 200_000,
                "capital_pct": 20,
                "strategy": "0DTE Iron Condor at 1 SD, 10% risk per trade",
                "data_sources": ["VIX", "Expected Move", "Tradier Sandbox"]
            },
            "HERMES": {
                "name": "HERMES",
                "description": "Manual Wheel Strategy Manager",
                "type": "manual",
                "scheduled": False,
                "schedule": "User-initiated",
                "capital_allocation": 0,
                "capital_pct": 0,
                "strategy": "User-initiated wheel trades via UI"
            },
            "ORACLE": {
                "name": "ORACLE",
                "description": "Strategy Recommendation Engine",
                "type": "advisory",
                "scheduled": False,
                "schedule": "On-demand",
                "capital_allocation": 0,
                "capital_pct": 0,
                "strategy": "12-strategy comparison with ensemble weighting"
            }
        }

        # Get decision counts for each bot
        for bot_name in bots:
            summary = get_bot_decision_summary(bot_name=bot_name, days=7)
            bots[bot_name]["last_7_days"] = {
                "decisions": summary.get("total_decisions", 0),
                "trades": summary.get("trades_executed", 0),
                "pnl": summary.get("total_pnl", 0)
            }

        return {
            "success": True,
            "data": {
                "bots": bots,
                "capital_summary": {
                    "total_capital": TOTAL_CAPITAL,
                    "allocated_capital": sum(b["capital_allocation"] for b in bots.values()),
                    "reserve_capital": RESERVE_CAPITAL,
                    "allocation": {
                        "PHOENIX": {"amount": 300_000, "pct": 30},
                        "ATLAS": {"amount": 400_000, "pct": 40},
                        "ARES": {"amount": 200_000, "pct": 20},
                        "RESERVE": {"amount": 100_000, "pct": 10}
                    }
                },
                "active_count": sum(1 for b in bots.values() if b["scheduled"]),
                "autonomous_bots": ["PHOENIX", "ATLAS", "ARES"],
                "timestamp": datetime.now().isoformat()
            }
        }
    except Exception as e:
        logger.error(f"Error getting bots status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/bots/recapitalize")
async def recapitalize_bot(bot: str, capital: float, note: str = None):
    """
    Recapitalize a bot with fresh capital while preserving all historical data.

    Use this instead of reset when a bot blows an account - keeps all trade
    history for Solomon learning while allowing the bot to continue trading.

    Args:
        bot: Bot name (ARES, ATHENA, TITAN, PEGASUS, ICARUS)
        capital: New starting capital amount
        note: Optional note explaining the recapitalization

    Preserves:
        - All closed trades (for win/loss pattern analysis)
        - All equity snapshots (for drawdown analysis)
        - All decision logs (for Solomon learning)
        - All scan activity (for signal analysis)
    """
    valid_bots = ['ARES', 'ATHENA', 'TITAN', 'PEGASUS', 'ICARUS']
    bot_upper = bot.upper()

    if bot_upper not in valid_bots:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid bot. Must be one of: {', '.join(valid_bots)}"
        )

    if capital <= 0:
        raise HTTPException(status_code=400, detail="Capital must be positive")

    try:
        conn = get_connection()
        c = conn.cursor()

        bot_lower = bot_upper.lower()
        config_key = f"{bot_lower}_starting_capital"
        snapshot_table = f"{bot_lower}_equity_snapshots"

        # Get previous capital for logging
        c.execute(
            "SELECT value FROM autonomous_config WHERE key = %s",
            (config_key,)
        )
        row = c.fetchone()
        previous_capital = float(row[0]) if row else None

        # Update starting capital
        c.execute("""
            INSERT INTO autonomous_config (key, value, updated_at)
            VALUES (%s, %s, NOW())
            ON CONFLICT (key) DO UPDATE SET value = %s, updated_at = NOW()
        """, (config_key, str(capital), str(capital)))

        # Record recapitalization event in equity snapshots
        recap_note = note or f"Recapitalized from ${previous_capital:,.2f}" if previous_capital else "Initial capitalization"

        try:
            c.execute(f"""
                INSERT INTO {snapshot_table}
                (timestamp, balance, realized_pnl, unrealized_pnl, open_positions, note)
                VALUES (NOW(), %s, 0, 0, 0, %s)
            """, (capital, f"[RECAPITALIZE] {recap_note}"))
        except Exception as snap_err:
            logger.warning(f"Could not record recap in {snapshot_table}: {snap_err}")

        # Log the recapitalization event
        try:
            c.execute("""
                INSERT INTO trading_decisions
                (bot_name, decision_type, decision, reasoning, created_at)
                VALUES (%s, 'RECAPITALIZE', 'APPROVED', %s, NOW())
            """, (bot_upper, f"Capital set to ${capital:,.2f}. Previous: ${previous_capital:,.2f if previous_capital else 0:,.2f}. Note: {note or 'None'}"))
        except Exception:
            pass

        conn.commit()
        conn.close()

        return {
            "success": True,
            "bot": bot_upper,
            "previous_capital": previous_capital,
            "new_capital": capital,
            "note": note,
            "message": f"{bot_upper} recapitalized to ${capital:,.2f}. All historical data preserved for Solomon learning.",
            "data_preserved": [
                f"{bot_lower}_positions (closed trades)",
                f"{bot_lower}_equity_snapshots (drawdown history)",
                f"{bot_lower}_scan_activity (signal history)",
                "trading_decisions (decision logs)"
            ]
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error recapitalizing {bot}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/bots/reset")
async def reset_bot_data(bot: str = None, confirm: bool = False):
    """
    Reset bot data to start fresh with proper tracking.

    Args:
        bot: Bot name to reset (PHOENIX, ATLAS) or None for all
        confirm: Must be True to actually delete data

    DANGEROUS: This deletes all historical trade data for the bot(s).
    Only use when you want to start fresh with proper tracking.
    """
    if not confirm:
        return {
            "success": False,
            "error": "Must set confirm=true to reset data. This action cannot be undone.",
            "warning": "This will delete ALL historical trades, positions, and decisions for the bot(s)."
        }

    try:
        conn = get_connection()
        c = conn.cursor()

        deleted_counts = {
            "open_positions": 0,
            "closed_trades": 0,
            "decision_logs": 0,
            "equity_snapshots": 0
        }

        # Build WHERE clause for bot filter
        bot_filter = ""
        bot_params = []
        if bot:
            bot_filter = " WHERE bot_name = %s" if "bot_name" in "bot_name" else ""
            bot_params = [bot]

        # Delete open positions
        try:
            if bot:
                c.execute("DELETE FROM autonomous_open_positions WHERE symbol LIKE %s",
                         ('%SPY%' if bot == 'PHOENIX' else '%SPX%',))
            else:
                c.execute("DELETE FROM autonomous_open_positions")
            deleted_counts["open_positions"] = c.rowcount
        except Exception:
            pass

        # Delete closed trades
        try:
            if bot:
                c.execute("DELETE FROM autonomous_closed_trades WHERE symbol LIKE %s",
                         ('%SPY%' if bot == 'PHOENIX' else '%SPX%',))
            else:
                c.execute("DELETE FROM autonomous_closed_trades")
            deleted_counts["closed_trades"] = c.rowcount
        except Exception:
            pass

        # Delete decision logs
        try:
            c.execute("DELETE FROM decision_logs" + (" WHERE bot_name = %s" if bot else ""),
                     (bot,) if bot else ())
            deleted_counts["decision_logs"] = c.rowcount
        except Exception:
            pass

        # Delete equity snapshots (reset equity curve)
        try:
            c.execute("DELETE FROM autonomous_equity_snapshots")
            deleted_counts["equity_snapshots"] = c.rowcount
        except Exception:
            pass

        # Reset capital to starting value
        try:
            c.execute("""
                INSERT INTO autonomous_config (key, value, updated_at)
                VALUES ('capital', '1000000', NOW())
                ON CONFLICT (key) DO UPDATE SET value = '1000000', updated_at = NOW()
            """)
        except Exception:
            pass

        conn.commit()
        conn.close()

        return {
            "success": True,
            "message": f"Bot data reset successfully{' for ' + bot if bot else ' for all bots'}",
            "deleted": deleted_counts,
            "note": "Bots will start fresh with proper tracking on next run"
        }

    except Exception as e:
        logger.error(f"Error resetting bot data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# ARES (Aggressive Iron Condor) Routes
# =============================================================================

# Try to import ARES V2 trader
try:
    from trading.ares_v2 import ARESTrader, ARESConfig, TradingMode as ARESTradingMode
    ARES_AVAILABLE = True
except ImportError as e:
    ARES_AVAILABLE = False
    ARESConfig = None
    logger.warning(f"ARES trader not available: {e}")

# Initialize ARES trader instance (lazy initialization)
_ares_trader = None

def get_ares_trader():
    """Get or create ARES trader instance"""
    global _ares_trader
    if _ares_trader is None and ARES_AVAILABLE:
        # Use default ARESConfig which is LIVE mode (sandbox=True in executor)
        config = ARESConfig()
        _ares_trader = ARESTrader(config=config)
    return _ares_trader


@router.get("/bots/ares/status")
async def get_ares_status():
    """
    Get ARES bot status.

    Returns current status, configuration, and performance metrics.
    """
    if not ARES_AVAILABLE:
        return {
            "success": False,
            "error": "ARES trader not available",
            "mode": "unavailable"
        }

    try:
        ares = get_ares_trader()
        if ares:
            status = ares.get_status()
            return status
        else:
            return {
                "success": False,
                "error": "Could not initialize ARES trader"
            }
    except Exception as e:
        logger.error(f"Error getting ARES status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/bots/ares/run")
async def run_ares_cycle():
    """
    Run ARES daily trading cycle.

    This will:
    1. Check if within trading window
    2. Get SPY price and calculate expected move
    3. Find Iron Condor strikes at 1 SD
    4. Place order on Tradier (sandbox mode)

    Returns the cycle result with any actions taken.
    """
    if not ARES_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="ARES trader not available"
        )

    try:
        ares = get_ares_trader()
        if not ares:
            raise HTTPException(
                status_code=503,
                detail="Could not initialize ARES trader"
            )

        result = ares.run_daily_cycle()
        return {
            "success": True,
            "data": result
        }
    except Exception as e:
        logger.error(f"Error running ARES cycle: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/debug/data-sources")
async def debug_data_sources():
    """
    Debug endpoint to check if market data sources are working.
    This is the FIRST thing to check if bots aren't trading.
    """
    result = {
        "timestamp": datetime.now().isoformat(),
        "data_sources": {},
        "env_vars": {},
        "test_results": {}
    }

    # 1. Check environment variables (masked)
    env_vars = [
        'TRADIER_API_KEY', 'TRADIER_ACCOUNT_ID',
        'TRADIER_SANDBOX_API_KEY', 'TRADIER_SANDBOX_ACCOUNT_ID',
        'POLYGON_API_KEY', 'TRADING_VOLATILITY_API_KEY', 'TV_USERNAME'
    ]
    for var in env_vars:
        val = os.getenv(var, '')
        if val:
            result["env_vars"][var] = f"SET ({len(val)} chars, ends with ...{val[-4:]})"
        else:
            result["env_vars"][var] = "NOT SET"

    # 2. Check data provider initialization
    try:
        from data.unified_data_provider import get_data_provider, TRADIER_AVAILABLE, POLYGON_AVAILABLE, TRADING_VOL_AVAILABLE
        result["data_sources"]["tradier_module"] = TRADIER_AVAILABLE
        result["data_sources"]["polygon_module"] = POLYGON_AVAILABLE
        result["data_sources"]["trading_vol_module"] = TRADING_VOL_AVAILABLE

        provider = get_data_provider()
        result["data_sources"]["tradier_initialized"] = provider._tradier is not None
        result["data_sources"]["polygon_initialized"] = provider._polygon is not None
        result["data_sources"]["trading_vol_initialized"] = provider._trading_vol is not None

        # 3. Test actual data fetch
        try:
            price = provider.get_price('SPY')
            result["test_results"]["spy_price"] = price
            result["test_results"]["spy_price_ok"] = price > 0
        except Exception as e:
            result["test_results"]["spy_price_error"] = str(e)

        try:
            vix = provider.get_vix()
            result["test_results"]["vix"] = vix
            result["test_results"]["vix_ok"] = vix > 0
        except Exception as e:
            result["test_results"]["vix_error"] = str(e)

        try:
            gex = provider.get_gex('SPY')
            if gex:
                result["test_results"]["gex"] = {
                    "net_gex": gex.net_gex,
                    "flip_point": gex.flip_point
                }
                result["test_results"]["gex_ok"] = True
            else:
                result["test_results"]["gex"] = None
                result["test_results"]["gex_ok"] = False
        except Exception as e:
            result["test_results"]["gex_error"] = str(e)

    except Exception as e:
        result["error"] = str(e)

    # 4. Summary
    issues = []
    if result["env_vars"].get("TRADIER_API_KEY") == "NOT SET":
        issues.append("TRADIER_API_KEY not set")
    if result["env_vars"].get("TRADIER_ACCOUNT_ID") == "NOT SET":
        issues.append("TRADIER_ACCOUNT_ID not set")
    if not result.get("data_sources", {}).get("tradier_initialized"):
        issues.append("Tradier failed to initialize - check API key")
    if result.get("test_results", {}).get("spy_price", 0) == 0:
        issues.append("SPY price returned 0 - API may be down or key invalid")
    if result.get("test_results", {}).get("vix", 0) == 0:
        issues.append("VIX returned 0 - data source issue")

    result["summary"] = issues if issues else ["All data sources working"]
    result["trading_blocked"] = len(issues) > 0

    return result


@router.get("/debug/no-trades")
async def debug_no_trades():
    """
    Debug endpoint to find exactly why bots didn't trade today.
    Returns comprehensive diagnostic information.
    """
    from zoneinfo import ZoneInfo
    CENTRAL_TZ = ZoneInfo("America/Chicago")
    today = datetime.now(CENTRAL_TZ).strftime('%Y-%m-%d')

    result = {
        "date": today,
        "timestamp": datetime.now(CENTRAL_TZ).isoformat(),
        "diagnostics": {}
    }

    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # 1. Bot Heartbeats
        try:
            cursor.execute('''
                SELECT bot_name, last_heartbeat, status, scan_count, details,
                       EXTRACT(EPOCH FROM (NOW() - last_heartbeat))/60 as minutes_ago
                FROM bot_heartbeats
                ORDER BY last_heartbeat DESC NULLS LAST
            ''')
            result["diagnostics"]["heartbeats"] = cursor.fetchall()
        except Exception as e:
            result["diagnostics"]["heartbeats_error"] = str(e)

        # 2. Today's Scan Activity
        try:
            cursor.execute('''
                SELECT bot_name, timestamp, outcome, decision_summary,
                       oracle_advice, oracle_win_probability, oracle_confidence,
                       underlying_price, vix, gex_regime
                FROM scan_activity
                WHERE date = %s
                ORDER BY timestamp DESC
                LIMIT 100
            ''', (today,))
            result["diagnostics"]["scan_activity"] = cursor.fetchall()
        except Exception as e:
            result["diagnostics"]["scan_activity_error"] = str(e)

        # 3. Scan Outcome Summary
        try:
            cursor.execute('''
                SELECT bot_name, outcome, COUNT(*) as count
                FROM scan_activity
                WHERE date = %s
                GROUP BY bot_name, outcome
                ORDER BY bot_name, count DESC
            ''', (today,))
            result["diagnostics"]["outcome_summary"] = cursor.fetchall()
        except Exception as e:
            result["diagnostics"]["outcome_summary_error"] = str(e)

        # 4. Open Positions
        open_positions = {}
        for table, bot in [('ares_positions', 'ARES'), ('athena_positions', 'ATHENA')]:
            try:
                cursor.execute(f'''
                    SELECT position_id, status, open_time, underlying_at_entry
                    FROM {table}
                    WHERE status = 'open'
                ''')
                open_positions[bot] = cursor.fetchall()
            except:
                open_positions[bot] = []
        result["diagnostics"]["open_positions"] = open_positions

        # 5. Scheduler State
        try:
            cursor.execute('''
                SELECT is_running, last_trade_check, execution_count,
                       should_auto_restart, updated_at
                FROM scheduler_state WHERE id = 1
            ''')
            result["diagnostics"]["scheduler_state"] = cursor.fetchone()
        except Exception as e:
            result["diagnostics"]["scheduler_state_error"] = str(e)

        # 6. Recent decision logs
        try:
            cursor.execute('''
                SELECT bot_name, timestamp, decision_type, decision_value, reasoning
                FROM decision_logs
                WHERE DATE(timestamp) = %s
                ORDER BY timestamp DESC
                LIMIT 30
            ''', (today,))
            result["diagnostics"]["decision_logs"] = cursor.fetchall()
        except Exception as e:
            result["diagnostics"]["decision_logs_error"] = str(e)

        # 7. Bot configs (check thresholds)
        try:
            cursor.execute('''
                SELECT bot_name, config_key, config_value
                FROM bot_config
                WHERE config_key IN ('min_win_probability', 'vix_skip', 'wall_filter_pct', 'mode')
            ''')
            result["diagnostics"]["bot_configs"] = cursor.fetchall()
        except Exception as e:
            result["diagnostics"]["bot_configs_error"] = str(e)

        conn.close()

        # 8. Add analysis summary
        summary = []

        # Check heartbeats
        heartbeats = result["diagnostics"].get("heartbeats", [])
        if not heartbeats:
            summary.append("❌ NO HEARTBEATS - Bots may not be running!")
        else:
            for hb in heartbeats:
                if hb.get('minutes_ago') and hb['minutes_ago'] > 10:
                    summary.append(f"⚠️ {hb['bot_name']} last heartbeat was {hb['minutes_ago']:.0f} min ago")

        # Check scan activity
        scans = result["diagnostics"].get("scan_activity", [])
        if not scans:
            summary.append("❌ NO SCANS TODAY - Scheduler may not be running!")
        else:
            # Check for NO_TRADE outcomes
            no_trades = [s for s in scans if s.get('outcome') == 'NO_TRADE']
            if no_trades:
                reasons = set(s.get('decision_summary', '') for s in no_trades[:5])
                summary.append(f"ℹ️ {len(no_trades)} NO_TRADE scans. Reasons: {reasons}")

        # Check for open positions
        for bot, positions in result["diagnostics"].get("open_positions", {}).items():
            if positions:
                summary.append(f"🔒 {bot} has {len(positions)} open position(s) - BLOCKING NEW ENTRIES")

        result["summary"] = summary if summary else ["✅ No obvious issues detected - check scan_activity for details"]

        return result

    except Exception as e:
        if conn:
            conn.close()
        raise HTTPException(status_code=500, detail=f"Debug failed: {str(e)}")


# =============================================================================
# TRADE SYNC ENDPOINTS
# =============================================================================

@router.post("/sync/full")
async def run_full_trade_sync():
    """
    Run full trade synchronization across all bots.

    Operations performed:
    1. Cleanup stale positions (expired but still 'open')
    2. Fix missing P&L values on closed positions
    3. Sync bot tables to unified tables

    This endpoint should be called:
    - On system startup
    - Periodically during market hours
    - After suspected data inconsistencies

    Returns:
        Complete sync results with counts and errors
    """
    try:
        from trading.trade_sync_service import run_full_sync
        results = run_full_sync()
        return {
            "success": len(results.get('total_errors', [])) == 0,
            "data": results,
            "message": f"Sync completed: {results.get('stale_cleanup', {}).get('total_cleaned', 0)} stale cleaned, "
                      f"{results.get('pnl_fix', {}).get('total_fixed', 0)} P&L fixed, "
                      f"{results.get('unified_sync', {}).get('open_synced', 0)} open synced"
        }
    except Exception as e:
        logger.error(f"Full trade sync failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sync/stale-cleanup")
async def cleanup_stale_positions():
    """
    Cleanup stale positions across all bots.

    Finds positions that:
    - Have status='open'
    - Have expiration date in the past

    These are marked as 'expired' with calculated P&L.

    Returns:
        Cleanup results by bot
    """
    try:
        from trading.trade_sync_service import cleanup_stale_positions as do_cleanup
        results = do_cleanup()
        return {
            "success": len(results.get('errors', [])) == 0,
            "data": results,
            "message": f"Cleaned {results.get('total_cleaned', 0)} stale positions"
        }
    except Exception as e:
        logger.error(f"Stale cleanup failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sync/fix-pnl")
async def fix_missing_pnl():
    """
    Fix missing P&L values on closed/expired positions.

    Calculates and updates realized_pnl for positions where it's NULL.

    Returns:
        Fix results by bot
    """
    try:
        from trading.trade_sync_service import fix_missing_pnl as do_fix
        results = do_fix()
        return {
            "success": len(results.get('errors', [])) == 0,
            "data": results,
            "message": f"Fixed {results.get('total_fixed', 0)} positions with missing P&L"
        }
    except Exception as e:
        logger.error(f"P&L fix failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sync/unified")
async def sync_to_unified_tables():
    """
    Sync bot-specific tables to unified tracking tables.

    Ensures:
    - autonomous_open_positions has all open positions
    - autonomous_closed_trades has all closed positions

    Returns:
        Sync results by bot
    """
    try:
        from trading.trade_sync_service import sync_to_unified as do_sync
        results = do_sync()
        return {
            "success": len(results.get('errors', [])) == 0,
            "data": results,
            "message": f"Synced {results.get('open_synced', 0)} open, {results.get('closed_synced', 0)} closed positions"
        }
    except Exception as e:
        logger.error(f"Unified sync failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sync/status")
async def get_sync_status():
    """
    Get current sync status and data integrity metrics.

    Checks:
    - Stale positions count
    - Positions with missing P&L
    - Unified table sync status

    Returns:
        Sync status and recommendations
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()

        status = {
            "timestamp": datetime.now().isoformat(),
            "stale_positions": {},
            "missing_pnl": {},
            "unified_sync": {},
            "recommendations": []
        }

        bot_tables = [
            ('ares', 'ares_positions'),
            ('athena', 'athena_positions'),
            ('titan', 'titan_positions'),
            ('pegasus', 'pegasus_positions'),
            ('icarus', 'icarus_positions')
        ]

        today = datetime.now().date()

        for bot_name, table in bot_tables:
            try:
                # Check for stale positions
                cursor.execute(f"""
                    SELECT COUNT(*) FROM {table}
                    WHERE status = 'open' AND expiration < %s
                """, (today,))
                stale_count = cursor.fetchone()[0]
                status["stale_positions"][bot_name] = stale_count

                # Check for missing P&L
                cursor.execute(f"""
                    SELECT COUNT(*) FROM {table}
                    WHERE status IN ('closed', 'expired', 'partial_close') AND realized_pnl IS NULL
                """, ())
                missing_pnl_count = cursor.fetchone()[0]
                status["missing_pnl"][bot_name] = missing_pnl_count

                if stale_count > 0:
                    status["recommendations"].append(f"Run /sync/stale-cleanup - {bot_name} has {stale_count} stale positions")
                if missing_pnl_count > 0:
                    status["recommendations"].append(f"Run /sync/fix-pnl - {bot_name} has {missing_pnl_count} positions with missing P&L")

            except Exception as e:
                logger.debug(f"Error checking {bot_name}: {e}")

        # Check unified table status
        try:
            cursor.execute("SELECT COUNT(*) FROM autonomous_open_positions WHERE status = 'open'")
            status["unified_sync"]["open_positions"] = cursor.fetchone()[0]

            # Use COALESCE to handle legacy data with NULL exit_time
            cursor.execute("SELECT COUNT(*) FROM autonomous_closed_trades WHERE COALESCE(exit_time::timestamp, entry_time::timestamp) >= NOW() - INTERVAL '7 days'")
            status["unified_sync"]["recent_closed"] = cursor.fetchone()[0]
        except Exception as e:
            status["unified_sync"]["error"] = str(e)

        conn.close()

        if not status["recommendations"]:
            status["recommendations"].append("✅ No sync issues detected")

        return {"success": True, "data": status}

    except Exception as e:
        logger.error(f"Sync status check failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
