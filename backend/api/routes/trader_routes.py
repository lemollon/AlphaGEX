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

        # Get latest equity snapshot - handle missing columns gracefully
        max_drawdown = 0
        sharpe_ratio = 0
        try:
            cursor.execute("""
                SELECT equity, cumulative_pnl
                FROM autonomous_equity_snapshots
                ORDER BY timestamp DESC
                LIMIT 1
            """)
            snapshot = cursor.fetchone()
            # Calculate drawdown from equity if available
            if snapshot and snapshot[0]:
                # Get starting capital for drawdown calculation
                cursor.execute("SELECT value FROM autonomous_config WHERE key = 'capital'")
                cap_row = cursor.fetchone()
                starting_capital = float(cap_row[0]) if cap_row else 1000000
                current_equity = float(snapshot[0])
                if current_equity < starting_capital:
                    max_drawdown = ((starting_capital - current_equity) / starting_capital * 100)
        except Exception:
            # Rollback on error to clear aborted transaction state
            conn.rollback()

        # Get today's P&L
        from zoneinfo import ZoneInfo
        today = datetime.now(ZoneInfo("America/Chicago")).strftime('%Y-%m-%d')

        today_pnl = 0
        try:
            cursor.execute("""
                SELECT COALESCE(SUM(realized_pnl), 0)
                FROM autonomous_closed_trades
                WHERE exit_date = %s
            """, (today,))
            today_realized = cursor.fetchone()[0] or 0

            cursor.execute("""
                SELECT COALESCE(SUM(unrealized_pnl), 0)
                FROM autonomous_open_positions
            """)
            today_unrealized = cursor.fetchone()[0] or 0

            today_pnl = float(today_realized) + float(today_unrealized)
        except Exception:
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
        # NOW INCLUDES: All Greeks (delta, gamma, theta, vega) for full transparency
        if symbol:
            cursor.execute("""
                SELECT
                    id, symbol, strategy, strike, option_type, contracts,
                    entry_price, current_price, unrealized_pnl, entry_date,
                    entry_time, expiration_date, contract_symbol, entry_spot_price,
                    current_spot_price, gex_regime, confidence, trade_reasoning,
                    profit_target_pct, stop_loss_pct, created_at,
                    -- Entry Greeks for analysis
                    entry_iv, entry_delta, entry_gamma, entry_theta, entry_vega,
                    -- Current Greeks for live monitoring
                    current_iv, current_delta, current_gamma, current_theta, current_vega
                FROM autonomous_open_positions
                WHERE symbol = %s
                ORDER BY entry_date DESC, entry_time DESC
            """, (symbol.upper(),))
        else:
            # Show ALL symbols for unified portfolio view
            cursor.execute("""
                SELECT
                    id, symbol, strategy, strike, option_type, contracts,
                    entry_price, current_price, unrealized_pnl, entry_date,
                    entry_time, expiration_date, contract_symbol, entry_spot_price,
                    current_spot_price, gex_regime, confidence, trade_reasoning,
                    profit_target_pct, stop_loss_pct, created_at,
                    -- Entry Greeks for analysis
                    entry_iv, entry_delta, entry_gamma, entry_theta, entry_vega,
                    -- Current Greeks for live monitoring
                    current_iv, current_delta, current_gamma, current_theta, current_vega
                FROM autonomous_open_positions
                ORDER BY entry_date DESC, entry_time DESC
            """)
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
                ORDER BY exit_date DESC, exit_time DESC
                LIMIT %s
            """, (symbol.upper(), int(limit)))
        else:
            # Show ALL symbols for unified portfolio view
            cursor.execute("""
                SELECT * FROM autonomous_closed_trades
                ORDER BY exit_date DESC, exit_time DESC
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
                    exit_date as trade_date,
                    exit_time as trade_time,
                    realized_pnl,
                    strategy,
                    symbol
                FROM autonomous_closed_trades
                WHERE exit_date >= '{start_date_str}' {symbol_filter}
                ORDER BY exit_date ASC, exit_time ASC
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
            ORDER BY exit_date DESC, exit_time DESC
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

        c.execute("""
            CREATE TABLE IF NOT EXISTS strategy_config (
                strategy_name VARCHAR(100) PRIMARY KEY,
                enabled BOOLEAN DEFAULT TRUE,
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)

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
        symbol_positions = cursor.fetchall()

        # Get all positions with full detail
        cursor.execute("""
            SELECT
                id, symbol, strategy, strike, option_type, contracts,
                entry_price, current_price, unrealized_pnl, entry_date,
                expiration_date, contract_symbol, gex_regime, confidence,
                entry_iv, entry_delta, entry_gamma, entry_theta, entry_vega,
                current_iv, current_delta, current_gamma, current_theta, current_vega
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

        conn.close()

        # Calculate aggregate metrics
        total_unrealized = sum(float(p.get('unrealized_pnl', 0) or 0) for p in symbol_positions)
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
            symbols_breakdown.append({
                'symbol': sp['symbol'],
                'open_positions': format_decimal(sp.get('position_count', 0)),
                'total_contracts': format_decimal(sp.get('total_contracts', 0)),
                'unrealized_pnl': round(format_decimal(sp.get('unrealized_pnl', 0)), 2),
                'realized_pnl': round(format_decimal(perf.get('total_pnl', 0)), 2),
                'net_pnl': round(format_decimal(sp.get('unrealized_pnl', 0)) + format_decimal(perf.get('total_pnl', 0)), 2),
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
                "positions": formatted_positions,
                "timestamp": datetime.now().isoformat()
            }
        }
    except Exception as e:
        logger.error(f"Error getting unified portfolio: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
