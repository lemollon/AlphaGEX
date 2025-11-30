"""
SPX Trader API routes.

Uses the unified AutonomousPaperTrader with symbol='SPX' and $100M capital.
This replaces the legacy spx_institutional_trader.py.
"""

import math
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException
import psycopg2.extras

from database_adapter import get_connection

router = APIRouter(prefix="/api/spx", tags=["SPX Trader"])


@router.get("/status")
async def get_spx_trader_status():
    """Get SPX institutional trader status"""
    try:
        from core.autonomous_paper_trader import AutonomousPaperTrader

        trader = AutonomousPaperTrader(symbol='SPX', capital=100_000_000)

        return {
            "success": True,
            "data": {
                "symbol": trader.symbol,
                "starting_capital": trader.starting_capital,
                "available_capital": trader.get_available_capital(),
                "max_position_pct": trader.max_position_pct,
                "max_delta_exposure": trader.max_delta_exposure,
                "max_contracts_per_trade": trader.max_contracts_per_trade,
                "greeks": trader.get_portfolio_greeks()
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/performance")
async def get_spx_performance():
    """Get SPX institutional trader performance summary"""
    try:
        from core.autonomous_paper_trader import AutonomousPaperTrader

        trader = AutonomousPaperTrader(symbol='SPX', capital=100_000_000)
        performance = trader.get_performance_summary()

        return {"success": True, "data": performance}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/check-risk")
async def check_spx_risk_limits(contracts: int, entry_price: float, delta: float = 0.5):
    """Check if a proposed SPX trade passes risk limits"""
    try:
        from core.autonomous_paper_trader import AutonomousPaperTrader

        trader = AutonomousPaperTrader(symbol='SPX', capital=100_000_000)
        proposed_trade = {'contracts': contracts, 'entry_price': entry_price, 'delta': delta}
        can_trade, reason = trader.check_risk_limits(proposed_trade)

        return {
            "success": True,
            "data": {"can_trade": can_trade, "reason": reason, "proposed_trade": proposed_trade}
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/trades")
async def get_spx_trades(limit: int = 20):
    """Get SPX institutional positions/trades"""
    try:
        conn = get_connection()
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        c.execute(f'''
            SELECT id, entry_date, entry_time, exit_date, exit_time, option_type,
                   strike, expiration_date, contracts, entry_price, exit_price,
                   realized_pnl, unrealized_pnl, status, strategy, trade_reasoning
            FROM spx_institutional_positions
            ORDER BY entry_date DESC, entry_time DESC
            LIMIT {int(limit)}
        ''')

        trades = []
        for row in c.fetchall():
            trade = {}
            for key, value in dict(row).items():
                if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
                    trade[key] = 0
                else:
                    trade[key] = value
            trades.append(trade)

        conn.close()
        return {"success": True, "count": len(trades), "data": trades}
    except Exception as e:
        return {"success": True, "count": 0, "data": [], "message": f"No SPX trades available: {str(e)}"}


@router.get("/equity-curve")
async def get_spx_equity_curve(days: int = 30):
    """Get SPX institutional equity curve from position history"""
    try:
        conn = get_connection()
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        starting_capital = 100_000_000

        c.execute('''
            SELECT exit_date as date, SUM(realized_pnl) as daily_pnl
            FROM spx_institutional_positions
            WHERE status = 'CLOSED' AND exit_date >= %s
            GROUP BY exit_date
            ORDER BY exit_date ASC
        ''', (start_date,))

        results = c.fetchall()
        conn.close()

        equity_data = []
        cumulative_pnl = 0

        if results:
            for row in results:
                pnl = float(row['daily_pnl'] or 0)
                if math.isnan(pnl) or math.isinf(pnl):
                    pnl = 0
                cumulative_pnl += pnl
                equity_data.append({
                    "date": str(row['date']),
                    "timestamp": int(datetime.strptime(str(row['date']), '%Y-%m-%d').timestamp()),
                    "pnl": round(cumulative_pnl, 2),
                    "equity": round(starting_capital + cumulative_pnl, 2),
                    "daily_pnl": round(pnl, 2)
                })
        else:
            today = datetime.now().strftime('%Y-%m-%d')
            equity_data.append({
                "date": today,
                "timestamp": int(datetime.now().timestamp()),
                "pnl": 0, "equity": starting_capital, "daily_pnl": 0
            })

        return {"success": True, "data": equity_data}
    except Exception as e:
        return {
            "success": True,
            "data": [{"date": datetime.now().strftime('%Y-%m-%d'), "timestamp": int(datetime.now().timestamp()),
                     "pnl": 0, "equity": 100_000_000, "daily_pnl": 0}],
            "message": str(e)
        }


@router.get("/trade-log")
async def get_spx_trade_log():
    """Get SPX trade activity log"""
    try:
        conn = get_connection()
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        c.execute('''
            SELECT id, entry_date as date, entry_time as time,
                   CASE WHEN status = 'OPEN' THEN 'OPEN ' || option_type ELSE 'CLOSE ' || option_type END as action,
                   'SPX ' || strike || ' ' || option_type || ' ' || expiration_date as details,
                   COALESCE(realized_pnl, unrealized_pnl, 0) as pnl
            FROM spx_institutional_positions
            ORDER BY entry_date DESC, entry_time DESC
            LIMIT 50
        ''')

        trades = []
        for row in c.fetchall():
            trade = {}
            for key, value in dict(row).items():
                if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
                    trade[key] = 0
                else:
                    trade[key] = value
            trades.append(trade)

        conn.close()
        return {"success": True, "data": trades}
    except Exception as e:
        return {"success": True, "data": [], "message": str(e)}


@router.get("/debug/logs")
async def get_spx_debug_logs(limit: int = 100, category: str = None, session_id: str = None):
    """Get SPX debug logs for real-time monitoring."""
    try:
        conn = get_connection()
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        query = '''
            SELECT id, timestamp, session_id, scan_cycle, log_level, category,
                   subcategory, message, data, duration_ms, success, error_message
            FROM spx_debug_logs WHERE 1=1
        '''
        params = []

        if category:
            query += ' AND category = %s'
            params.append(category)
        if session_id:
            query += ' AND session_id = %s'
            params.append(session_id)

        query += ' ORDER BY timestamp DESC LIMIT %s'
        params.append(limit)

        c.execute(query, params)
        logs = [dict(row) for row in c.fetchall()]
        conn.close()

        return {"success": True, "count": len(logs), "data": logs}
    except Exception as e:
        return {"success": False, "error": str(e), "data": []}


@router.get("/debug/errors")
async def get_spx_debug_errors(hours: int = 24):
    """Get SPX error summary for the last N hours."""
    try:
        conn = get_connection()
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        c.execute('''
            SELECT category, COUNT(*) as count FROM spx_debug_logs
            WHERE success = FALSE AND timestamp > NOW() - INTERVAL '%s hours'
            GROUP BY category ORDER BY count DESC
        ''', (hours,))
        error_counts = {row['category']: row['count'] for row in c.fetchall()}

        c.execute('''
            SELECT timestamp, category, subcategory, message, error_message, data
            FROM spx_debug_logs
            WHERE success = FALSE AND timestamp > NOW() - INTERVAL '%s hours'
            ORDER BY timestamp DESC LIMIT 20
        ''', (hours,))
        recent_errors = [dict(row) for row in c.fetchall()]
        conn.close()

        return {
            "success": True, "hours": hours,
            "total_errors": sum(error_counts.values()),
            "error_counts_by_category": error_counts,
            "recent_errors": recent_errors
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/debug/scan-cycles")
async def get_spx_scan_cycles(limit: int = 20):
    """Get summary of recent scan cycles for the SPX trader."""
    try:
        conn = get_connection()
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        c.execute('''
            SELECT session_id, scan_cycle, MIN(timestamp) as start_time, MAX(timestamp) as end_time,
                   COUNT(*) as log_count, SUM(CASE WHEN success = FALSE THEN 1 ELSE 0 END) as error_count,
                   MAX(CASE WHEN subcategory = 'end' THEN message ELSE NULL END) as result
            FROM spx_debug_logs WHERE category = 'SCAN'
            GROUP BY session_id, scan_cycle
            ORDER BY MIN(timestamp) DESC LIMIT %s
        ''', (limit,))

        cycles = [dict(row) for row in c.fetchall()]
        conn.close()
        return {"success": True, "count": len(cycles), "data": cycles}
    except Exception as e:
        return {"success": False, "error": str(e), "data": []}


@router.get("/debug/regime-history")
async def get_spx_regime_history(limit: int = 50):
    """Get history of regime classifications for debugging."""
    try:
        conn = get_connection()
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        c.execute('''
            SELECT timestamp, session_id, message, data FROM spx_debug_logs
            WHERE category = 'REGIME' AND subcategory = 'classification'
            ORDER BY timestamp DESC LIMIT %s
        ''', (limit,))

        regimes = []
        for row in c.fetchall():
            regime_data = row['data'] or {}
            regimes.append({
                'timestamp': row['timestamp'], 'session_id': row['session_id'], 'message': row['message'],
                'volatility_regime': regime_data.get('volatility_regime'),
                'gamma_regime': regime_data.get('gamma_regime'),
                'trend_regime': regime_data.get('trend_regime'),
                'recommended_action': regime_data.get('recommended_action'),
                'confidence': regime_data.get('confidence'),
                'bars_in_regime': regime_data.get('bars_in_regime')
            })
        conn.close()
        return {"success": True, "count": len(regimes), "data": regimes}
    except Exception as e:
        return {"success": False, "error": str(e), "data": []}


@router.get("/debug/kelly-history")
async def get_spx_kelly_history(limit: int = 50):
    """Get history of Kelly criterion calculations for debugging position sizing."""
    try:
        conn = get_connection()
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        c.execute('''
            SELECT timestamp, session_id, message, data FROM spx_debug_logs
            WHERE category = 'SIZING' AND subcategory = 'kelly_calculation'
            ORDER BY timestamp DESC LIMIT %s
        ''', (limit,))

        kelly_calcs = []
        for row in c.fetchall():
            kelly_data = row['data'] or {}
            kelly_calcs.append({
                'timestamp': row['timestamp'], 'session_id': row['session_id'],
                'strategy_name': kelly_data.get('strategy_name'),
                'win_rate': kelly_data.get('win_rate'),
                'avg_win': kelly_data.get('avg_win'), 'avg_loss': kelly_data.get('avg_loss'),
                'risk_reward_ratio': kelly_data.get('risk_reward_ratio'),
                'raw_kelly': kelly_data.get('raw_kelly'),
                'adjusted_kelly': kelly_data.get('adjusted_kelly'),
                'adjustment_type': kelly_data.get('adjustment_type')
            })
        conn.close()
        return {"success": True, "count": len(kelly_calcs), "data": kelly_calcs}
    except Exception as e:
        return {"success": False, "error": str(e), "data": []}


@router.get("/debug/data-fetches")
async def get_spx_data_fetch_history(limit: int = 50):
    """Get history of data fetch operations (GEX, VIX, prices)."""
    try:
        conn = get_connection()
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        c.execute('''
            SELECT timestamp, subcategory as data_type, message, data, duration_ms, success, error_message
            FROM spx_debug_logs WHERE category = 'DATA_FETCH'
            ORDER BY timestamp DESC LIMIT %s
        ''', (limit,))

        fetches = [dict(row) for row in c.fetchall()]
        conn.close()

        total = len(fetches)
        success = sum(1 for f in fetches if f['success'])
        avg_duration = sum(f['duration_ms'] or 0 for f in fetches) / total if total > 0 else 0

        return {
            "success": True, "count": total,
            "success_rate": f"{success/total*100:.1f}%" if total > 0 else "N/A",
            "avg_duration_ms": round(avg_duration, 1),
            "data": fetches
        }
    except Exception as e:
        return {"success": False, "error": str(e), "data": []}


@router.post("/debug/run-diagnostic")
async def run_spx_diagnostic():
    """Run a quick diagnostic check on the SPX trader system."""
    results = {"timestamp": datetime.now().isoformat(), "checks": {}}

    # Check database
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT 1")
        conn.close()
        results["checks"]["database"] = {"status": "OK", "message": "Connected"}
    except Exception as e:
        results["checks"]["database"] = {"status": "ERROR", "message": str(e)}

    # Check GEX data
    try:
        from backend.api.dependencies import api_client
        gex = api_client.get_net_gamma('SPX')
        if gex and not gex.get('error'):
            results["checks"]["gex_data"] = {
                "status": "OK", "net_gex": gex.get('net_gex'), "flip_point": gex.get('flip_point')
            }
        else:
            results["checks"]["gex_data"] = {"status": "WARN", "message": gex.get('error') if gex else "No data"}
    except Exception as e:
        results["checks"]["gex_data"] = {"status": "ERROR", "message": str(e)}

    # Check price data
    try:
        from data.polygon_data_fetcher import polygon_fetcher
        spy = polygon_fetcher.get_current_price('SPY')
        results["checks"]["price_data"] = {"status": "OK" if spy else "WARN", "spy_price": spy}
    except Exception as e:
        results["checks"]["price_data"] = {"status": "ERROR", "message": str(e)}

    # Check regime classifier
    try:
        from core.market_regime_classifier import get_classifier
        classifier = get_classifier('SPX')
        results["checks"]["regime_classifier"] = {"status": "OK", "message": "Initialized"}
    except Exception as e:
        results["checks"]["regime_classifier"] = {"status": "ERROR", "message": str(e)}

    # Check SPX trader (using unified trader with SPX symbol)
    try:
        from core.autonomous_paper_trader import AutonomousPaperTrader
        trader = AutonomousPaperTrader(symbol='SPX', capital=100_000_000)
        results["checks"]["spx_trader"] = {
            "status": "OK", "capital": trader.starting_capital,
            "symbol": trader.symbol,
            "type": "UnifiedTrader"
        }
    except Exception as e:
        results["checks"]["spx_trader"] = {"status": "ERROR", "message": str(e)}

    # Overall status
    error_count = sum(1 for c in results["checks"].values() if c.get("status") == "ERROR")
    warn_count = sum(1 for c in results["checks"].values() if c.get("status") == "WARN")

    results["overall"] = {
        "status": "ERROR" if error_count > 0 else ("WARN" if warn_count > 0 else "OK"),
        "errors": error_count, "warnings": warn_count
    }
    return results
