"""
FAITH API Routes
================

API endpoints for the FAITH Paper Iron Condor bot.
Supports both 2DTE and 1DTE modes via ?dte_mode= parameter for side-by-side comparison.

Endpoints:
- GET  /api/faith/status              - Bot status and configuration
- GET  /api/faith/positions           - Current open positions
- GET  /api/faith/trades              - Trade history (closed positions)
- GET  /api/faith/performance         - P&L, win rate, statistics
- GET  /api/faith/pdt-status          - PDT dashboard data
- GET  /api/faith/paper-account       - Paper account balance/collateral
- GET  /api/faith/position-monitor    - Live position monitoring data
- GET  /api/faith/equity-curve        - Historical equity curve
- GET  /api/faith/equity-curve/intraday - Today's intraday equity curve
- GET  /api/faith/logs                - Activity logs
- POST /api/faith/toggle              - Enable/disable bot
- POST /api/faith/run-cycle           - Manually trigger a scan cycle

All GET endpoints accept ?dte_mode=2DTE or ?dte_mode=1DTE (default: 2DTE)
"""

import logging
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo
from fastapi import APIRouter, HTTPException, Query

logger = logging.getLogger(__name__)

router = APIRouter(tags=["FAITH"])

# Lazy-initialized singletons per DTE mode
_faith_traders = {}


def _get_trader(dte_mode: str = "2DTE"):
    """Get or create the FAITH trader singleton for a given DTE mode."""
    global _faith_traders
    if dte_mode not in _faith_traders:
        try:
            from trading.faith.trader import FaithTrader
            from trading.faith.models import FaithConfig

            if dte_mode == "1DTE":
                config = FaithConfig(min_dte=1, dte_mode="1DTE")
                _faith_traders[dte_mode] = FaithTrader(config=config)
            else:
                _faith_traders[dte_mode] = FaithTrader()

            logger.info(f"FAITH: Trader initialized via API (dte_mode={dte_mode})")
        except Exception as e:
            logger.error(f"FAITH: Failed to initialize trader (dte_mode={dte_mode}): {e}")
            raise HTTPException(
                status_code=503,
                detail=f"FAITH bot unavailable: {e}"
            )
    return _faith_traders[dte_mode]


@router.get("/api/faith/status")
async def get_faith_status(
    dte_mode: str = Query("2DTE", description="DTE mode: 2DTE or 1DTE")
):
    """Get comprehensive FAITH bot status."""
    try:
        trader = _get_trader(dte_mode)
        status = trader.get_status()
        return {"status": "success", "data": status}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"FAITH status error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/faith/positions")
async def get_faith_positions(
    dte_mode: str = Query("2DTE", description="DTE mode: 2DTE or 1DTE")
):
    """Get current open positions."""
    try:
        trader = _get_trader(dte_mode)
        positions = trader.db.get_open_positions()
        return {
            "status": "success",
            "data": [p.to_dict() for p in positions],
            "count": len(positions),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"FAITH positions error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/faith/trades")
async def get_faith_trades(
    limit: int = 50,
    dte_mode: str = Query("2DTE", description="DTE mode: 2DTE or 1DTE")
):
    """Get trade history (closed positions)."""
    try:
        trader = _get_trader(dte_mode)
        trades = trader.db.get_closed_trades(limit=limit)
        return {
            "status": "success",
            "data": trades,
            "count": len(trades),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"FAITH trades error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/faith/performance")
async def get_faith_performance(
    dte_mode: str = Query("2DTE", description="DTE mode: 2DTE or 1DTE")
):
    """Get performance statistics (win rate, P&L, etc.)."""
    try:
        trader = _get_trader(dte_mode)
        stats = trader.db.get_performance_stats()
        account = trader.db.get_paper_account()
        return {
            "status": "success",
            "data": {
                **stats,
                'starting_capital': account.starting_balance,
                'current_balance': account.balance,
                'return_pct': round(
                    (account.cumulative_pnl / account.starting_balance * 100)
                    if account.starting_balance > 0 else 0, 2
                ),
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"FAITH performance error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/faith/pdt-status")
async def get_faith_pdt_status(
    dte_mode: str = Query("2DTE", description="DTE mode: 2DTE or 1DTE")
):
    """
    Get PDT (Pattern Day Trader) status.

    Returns day trade count, remaining trades, and next reset date.
    """
    try:
        trader = _get_trader(dte_mode)
        can_trade, pdt_count, pdt_msg = trader.can_trade_today()
        pdt_log = trader.db.get_pdt_log(days=10)
        next_reset = trader.db.get_next_pdt_reset_date()

        from datetime import datetime
        from trading.faith.models import CENTRAL_TZ
        now = datetime.now(CENTRAL_TZ)
        trades_today = trader.db.get_trades_today_count(now.strftime('%Y-%m-%d'))

        max_day_trades = trader.config.pdt_max_day_trades
        pdt_count_safe = pdt_count if pdt_count >= 0 else 0

        return {
            "status": "success",
            "data": {
                'day_trades_rolling_5': pdt_count_safe,
                'day_trades_remaining': max(0, max_day_trades - pdt_count_safe),
                'max_day_trades': max_day_trades,
                'trades_today': trades_today,
                'max_trades_per_day': trader.config.max_trades_per_day,
                'can_trade': can_trade,
                'reason': pdt_msg,
                'next_reset': next_reset,
                'pdt_log': pdt_log[:10],  # Last 10 entries
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"FAITH PDT status error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/faith/paper-account")
async def get_faith_paper_account(
    dte_mode: str = Query("2DTE", description="DTE mode: 2DTE or 1DTE")
):
    """Get paper account balance and collateral data."""
    try:
        trader = _get_trader(dte_mode)
        account = trader.db.get_paper_account()
        return {
            "status": "success",
            "data": account.to_dict(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"FAITH paper account error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/faith/position-monitor")
async def get_faith_position_monitor(
    dte_mode: str = Query("2DTE", description="DTE mode: 2DTE or 1DTE")
):
    """
    Get live position monitoring data.

    Returns real-time progress toward profit target, stop loss, and EOD cutoff.
    Returns null data field if no open position.
    """
    try:
        trader = _get_trader(dte_mode)
        monitor = trader.get_position_monitor()
        return {
            "status": "success",
            "data": monitor,  # None if no open position
            "has_position": monitor is not None,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"FAITH position monitor error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/faith/equity-curve")
async def get_faith_equity_curve(
    dte_mode: str = Query("2DTE", description="DTE mode: 2DTE or 1DTE")
):
    """Get historical equity curve from closed trades."""
    try:
        trader = _get_trader(dte_mode)
        curve = trader.db.get_equity_curve()
        return {
            "status": "success",
            "data": curve,
            "count": len(curve),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"FAITH equity curve error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/faith/equity-curve/intraday")
async def get_faith_intraday_equity(
    date: str = None,
    dte_mode: str = Query("2DTE", description="DTE mode: 2DTE or 1DTE")
):
    """
    Get FAITH intraday equity curve with snapshots.

    Returns equity data points throughout the trading day showing
    realized and unrealized P&L for paper-traded Iron Condors.
    """
    CENTRAL_TZ = ZoneInfo("America/Chicago")
    now = datetime.now(CENTRAL_TZ)
    today = date or now.strftime('%Y-%m-%d')
    current_time = now.strftime('%H:%M:%S')

    starting_capital = 5000  # Default for FAITH

    try:
        from database_adapter import get_connection
        conn = get_connection()
        cursor = conn.cursor()

        # Get starting capital from config
        cursor.execute("""
            SELECT value FROM autonomous_config WHERE key = 'faith_starting_capital'
        """)
        row = cursor.fetchone()
        if row and row[0]:
            try:
                starting_capital = float(row[0])
            except (ValueError, TypeError):
                pass

        # If no config, check paper account starting_balance for this dte_mode
        if starting_capital == 5000:
            cursor.execute("""
                SELECT starting_capital FROM faith_paper_account
                WHERE dte_mode = %s LIMIT 1
            """, (dte_mode,))
            pa_row = cursor.fetchone()
            if pa_row and pa_row[0]:
                try:
                    starting_capital = float(pa_row[0])
                except (ValueError, TypeError):
                    pass

        # Get intraday snapshots filtered by dte_mode
        cursor.execute("""
            SELECT timestamp, balance, unrealized_pnl, realized_pnl, open_positions, note
            FROM faith_equity_snapshots
            WHERE DATE(timestamp::timestamptz AT TIME ZONE 'America/Chicago') = %s
            AND dte_mode = %s
            ORDER BY timestamp ASC
        """, (today, dte_mode))
        snapshots = cursor.fetchall()

        # Get total realized P&L up to today filtered by dte_mode
        cursor.execute("""
            SELECT COALESCE(SUM(realized_pnl), 0)
            FROM faith_positions
            WHERE status IN ('closed', 'expired')
            AND dte_mode = %s
            AND DATE(COALESCE(close_time, open_time)::timestamptz AT TIME ZONE 'America/Chicago') <= %s
        """, (dte_mode, today))
        total_realized = float(cursor.fetchone()[0] or 0)

        # Get today's closed P&L
        cursor.execute("""
            SELECT COALESCE(SUM(realized_pnl), 0), COUNT(*)
            FROM faith_positions
            WHERE status IN ('closed', 'expired')
            AND dte_mode = %s
            AND DATE(COALESCE(close_time, open_time)::timestamptz AT TIME ZONE 'America/Chicago') = %s
        """, (dte_mode, today))
        today_row = cursor.fetchone()
        today_realized = float(today_row[0] or 0)
        today_closed_count = int(today_row[1] or 0)

        # Get today's closed trades with timestamps for accurate cumulative calc
        cursor.execute("""
            SELECT COALESCE(close_time, open_time)::timestamptz, realized_pnl
            FROM faith_positions
            WHERE status IN ('closed', 'expired')
            AND dte_mode = %s
            AND DATE(COALESCE(close_time, open_time)::timestamptz AT TIME ZONE 'America/Chicago') = %s
            ORDER BY COALESCE(close_time, open_time) ASC
        """, (dte_mode, today))
        today_closes = cursor.fetchall()

        # Get unrealized P&L from open positions
        unrealized_pnl = 0
        open_count = 0
        try:
            trader = _get_trader(dte_mode)
            monitor = trader.get_position_monitor()
            if monitor:
                unrealized_pnl = monitor.get('pnl_total', 0) or 0
                open_count = 1
        except Exception:
            pass

        conn.close()

        # Build data points
        data_points = []
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

        all_equities = [market_open_equity]

        for snapshot in snapshots:
            ts, balance, snap_unrealized, snap_realized, snap_open, note = snapshot
            snap_time = ts.astimezone(CENTRAL_TZ) if ts.tzinfo else ts

            snap_realized_val = prev_day_realized
            for close_time, close_pnl in today_closes:
                close_time_ct = close_time.astimezone(CENTRAL_TZ) if close_time and close_time.tzinfo else close_time
                if close_time_ct and close_time_ct <= snap_time:
                    snap_realized_val += float(close_pnl or 0)

            snap_unrealized_val = float(snap_unrealized or 0)
            snap_equity = round(starting_capital + snap_realized_val + snap_unrealized_val, 2)
            all_equities.append(snap_equity)

            data_points.append({
                "timestamp": snap_time.isoformat(),
                "time": snap_time.strftime('%H:%M:%S'),
                "equity": snap_equity,
                "cumulative_pnl": round(snap_realized_val + snap_unrealized_val, 2),
                "open_positions": snap_open or 0,
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
                "open_positions": open_count,
                "unrealized_pnl": round(unrealized_pnl, 2)
            })

        high_of_day = max(all_equities) if all_equities else starting_capital
        low_of_day = min(all_equities) if all_equities else starting_capital
        day_pnl = today_realized + unrealized_pnl

        return {
            "success": True,
            "date": today,
            "bot": "FAITH",
            "dte_mode": dte_mode,
            "data_points": data_points,
            "current_equity": round(current_equity, 2),
            "day_pnl": round(day_pnl, 2),
            "day_realized": round(today_realized, 2),
            "day_unrealized": round(unrealized_pnl, 2),
            "starting_equity": market_open_equity,
            "high_of_day": round(high_of_day, 2),
            "low_of_day": round(low_of_day, 2),
            "snapshots_count": len(snapshots),
            "today_closed_count": today_closed_count,
            "open_positions_count": open_count
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"FAITH intraday equity error: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e),
            "date": today,
            "bot": "FAITH",
            "dte_mode": dte_mode,
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
            "snapshots_count": 0,
            "today_closed_count": 0,
            "open_positions_count": 0
        }


@router.get("/api/faith/logs")
async def get_faith_logs(
    limit: int = 100,
    dte_mode: str = Query("2DTE", description="DTE mode: 2DTE or 1DTE")
):
    """Get activity logs."""
    try:
        trader = _get_trader(dte_mode)
        logs = trader.db.get_logs(limit=limit)
        return {
            "status": "success",
            "data": logs,
            "count": len(logs),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"FAITH logs error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/faith/toggle")
async def toggle_faith(
    active: bool = True,
    dte_mode: str = Query("2DTE", description="DTE mode: 2DTE or 1DTE")
):
    """Enable or disable the FAITH bot."""
    try:
        trader = _get_trader(dte_mode)
        result = trader.toggle(active)
        return {"status": "success", "data": result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"FAITH toggle error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/faith/run-cycle")
async def run_faith_cycle(
    close_only: bool = False,
    dte_mode: str = Query("2DTE", description="DTE mode: 2DTE or 1DTE")
):
    """
    Manually trigger a FAITH scan/trade cycle.

    Args:
        close_only: If true, only manage existing positions (no new trades)
    """
    try:
        trader = _get_trader(dte_mode)
        result = trader.run_cycle(close_only=close_only)
        return {"status": "success", "data": result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"FAITH run cycle error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
