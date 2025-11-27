"""
Autonomous Trader API routes.

Handles trader status, performance, positions, trades, and equity curve.
"""

import math
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException
import psycopg2.extras

from database_adapter import get_connection

router = APIRouter(prefix="/api/trader", tags=["Trader"])

# Try to import the autonomous trader
try:
    from autonomous_paper_trader import AutonomousPaperTrader
    trader = AutonomousPaperTrader()
    trader_available = True
except Exception as e:
    trader = None
    trader_available = False
    print(f"⚠️ Trader routes: Autonomous trader not available: {e}")


def safe_round(value, decimals=2, default=0):
    """Round a value, returning default if inf/nan"""
    if value is None:
        return default
    try:
        float_val = float(value)
        if math.isnan(float_val) or math.isinf(float_val):
            return default
        return round(float_val, decimals)
    except (ValueError, TypeError, OverflowError):
        return default


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

    try:
        perf = trader.get_performance() if hasattr(trader, 'get_performance') else {}

        conn = get_connection()
        cursor = conn.cursor()

        # Get latest equity snapshot
        cursor.execute("""
            SELECT sharpe_ratio, max_drawdown_pct, daily_pnl
            FROM autonomous_equity_snapshots
            ORDER BY snapshot_date DESC, snapshot_time DESC
            LIMIT 1
        """)
        snapshot = cursor.fetchone()
        sharpe_ratio = float(snapshot[0] or 0) if snapshot else 0
        max_drawdown = float(snapshot[1] or 0) if snapshot else 0

        # Get today's P&L
        from zoneinfo import ZoneInfo
        today = datetime.now(ZoneInfo("America/Chicago")).strftime('%Y-%m-%d')

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

        conn.close()

        today_pnl = float(today_realized) + float(today_unrealized)

        return {
            "success": True,
            "data": {
                "total_pnl": perf.get('total_pnl', 0),
                "today_pnl": today_pnl,
                "win_rate": perf.get('win_rate', 0),
                "total_trades": perf.get('total_trades', 0),
                "closed_trades": perf.get('closed_trades', 0),
                "open_positions": perf.get('open_positions', 0),
                "winning_trades": perf.get('winning_trades', 0),
                "losing_trades": perf.get('losing_trades', 0),
                "sharpe_ratio": sharpe_ratio,
                "max_drawdown": max_drawdown,
                "realized_pnl": perf.get('realized_pnl', 0),
                "unrealized_pnl": perf.get('unrealized_pnl', 0),
                "starting_capital": perf.get('starting_capital', 1000000),
                "current_value": perf.get('current_value', 1000000),
                "return_pct": perf.get('return_pct', 0)
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/positions")
async def get_open_positions():
    """Get all open positions from database"""
    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cursor.execute("""
            SELECT * FROM autonomous_open_positions
            ORDER BY entry_date DESC, entry_time DESC
        """)
        positions = cursor.fetchall()
        conn.close()

        return {
            "success": True,
            "data": [dict(p) for p in positions]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/closed-trades")
async def get_closed_trades(limit: int = 50):
    """Get closed trades from database"""
    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cursor.execute(f"""
            SELECT * FROM autonomous_closed_trades
            ORDER BY exit_date DESC, exit_time DESC
            LIMIT {int(limit)}
        """)
        trades = cursor.fetchall()
        conn.close()

        return {
            "success": True,
            "data": [dict(t) for t in trades]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/equity-curve")
async def get_equity_curve(days: int = 30):
    """Get historical equity curve from snapshots or trades"""
    if not trader_available:
        return {
            "success": False,
            "message": "Trader not configured",
            "data": []
        }

    try:
        import pandas as pd

        conn = get_connection()
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        starting_equity = 1000000

        snapshots = pd.read_sql_query(f"""
            SELECT
                snapshot_date,
                snapshot_time,
                starting_capital,
                total_realized_pnl,
                total_unrealized_pnl,
                account_value,
                daily_pnl,
                daily_return_pct,
                total_return_pct,
                max_drawdown_pct,
                sharpe_ratio,
                win_rate,
                total_trades
            FROM autonomous_equity_snapshots
            WHERE snapshot_date >= '{start_date.strftime('%Y-%m-%d')}'
            ORDER BY snapshot_date ASC, snapshot_time ASC
        """, conn)

        if snapshots.empty:
            # Build from closed trades
            trades = pd.read_sql_query(f"""
                SELECT
                    exit_date as trade_date,
                    exit_time as trade_time,
                    realized_pnl,
                    strategy
                FROM autonomous_closed_trades
                WHERE exit_date >= '{start_date.strftime('%Y-%m-%d')}'
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
                cumulative_pnl += float(row['daily_pnl'])
                current_equity = starting_equity + cumulative_pnl
                peak_equity = max(peak_equity, current_equity)
                drawdown = (peak_equity - current_equity) / peak_equity * 100 if peak_equity > 0 else 0
                max_drawdown = max(max_drawdown, drawdown)

                equity_data.append({
                    "timestamp": int(row['trade_date'].timestamp()),
                    "date": row['trade_date'].strftime('%Y-%m-%d'),
                    "equity": safe_round(current_equity),
                    "pnl": safe_round(cumulative_pnl),
                    "daily_pnl": safe_round(row['daily_pnl']),
                    "total_return_pct": safe_round(cumulative_pnl / starting_equity * 100),
                    "max_drawdown_pct": safe_round(max_drawdown)
                })

            return {
                "success": True,
                "data": equity_data,
                "total_pnl": safe_round(cumulative_pnl),
                "starting_equity": starting_equity,
                "max_drawdown_pct": safe_round(max_drawdown)
            }

        conn.close()

        # Format snapshot data
        equity_data = []
        for _, row in snapshots.iterrows():
            equity_data.append({
                "timestamp": int(pd.Timestamp(row['snapshot_date']).timestamp()),
                "date": str(row['snapshot_date']),
                "equity": safe_round(row['account_value']),
                "pnl": safe_round(row['total_realized_pnl']),
                "daily_pnl": safe_round(row['daily_pnl']),
                "total_return_pct": safe_round(row['total_return_pct']),
                "max_drawdown_pct": safe_round(row['max_drawdown_pct']),
                "sharpe_ratio": safe_round(row['sharpe_ratio']),
                "win_rate": safe_round(row['win_rate'])
            })

        return {
            "success": True,
            "data": equity_data,
            "total_pnl": safe_round(snapshots['total_realized_pnl'].iloc[-1]) if len(snapshots) > 0 else 0,
            "starting_equity": starting_equity,
            "sharpe_ratio": safe_round(snapshots['sharpe_ratio'].iloc[-1]) if len(snapshots) > 0 else 0,
            "max_drawdown_pct": safe_round(snapshots['max_drawdown_pct'].max()) if len(snapshots) > 0 else 0,
            "win_rate": safe_round(snapshots['win_rate'].iloc[-1]) if len(snapshots) > 0 else 0
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/strategies")
async def get_strategies():
    """Get all trading strategies and their performance"""
    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cursor.execute("""
            SELECT
                strategy,
                COUNT(*) as total_trades,
                SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as winning_trades,
                SUM(realized_pnl) as total_pnl,
                AVG(realized_pnl) as avg_pnl,
                MAX(exit_date) as last_trade_date
            FROM autonomous_closed_trades
            GROUP BY strategy
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
