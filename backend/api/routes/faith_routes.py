"""
FAITH API Routes
================

API endpoints for the FAITH 2DTE Paper Iron Condor bot.

Endpoints:
- GET  /api/faith/status              - Bot status and configuration
- GET  /api/faith/positions           - Current open positions
- GET  /api/faith/trades              - Trade history (closed positions)
- GET  /api/faith/performance         - P&L, win rate, statistics
- GET  /api/faith/pdt-status          - PDT dashboard data
- GET  /api/faith/paper-account       - Paper account balance/collateral
- GET  /api/faith/position-monitor    - Live position monitoring data
- GET  /api/faith/equity-curve        - Historical equity curve
- GET  /api/faith/logs                - Activity logs
- POST /api/faith/toggle              - Enable/disable bot
- POST /api/faith/run-cycle           - Manually trigger a scan cycle
"""

import logging
from typing import Optional
from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)

router = APIRouter(tags=["FAITH"])

# Lazy-initialized singleton
_faith_trader = None


def _get_trader():
    """Get or create the FAITH trader singleton."""
    global _faith_trader
    if _faith_trader is None:
        try:
            from trading.faith.trader import FaithTrader
            _faith_trader = FaithTrader()
            logger.info("FAITH: Trader initialized via API")
        except Exception as e:
            logger.error(f"FAITH: Failed to initialize trader: {e}")
            raise HTTPException(
                status_code=503,
                detail=f"FAITH bot unavailable: {e}"
            )
    return _faith_trader


@router.get("/api/faith/status")
async def get_faith_status():
    """Get comprehensive FAITH bot status."""
    try:
        trader = _get_trader()
        status = trader.get_status()
        return {"status": "success", "data": status}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"FAITH status error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/faith/positions")
async def get_faith_positions():
    """Get current open positions."""
    try:
        trader = _get_trader()
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
async def get_faith_trades(limit: int = 50):
    """Get trade history (closed positions)."""
    try:
        trader = _get_trader()
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
async def get_faith_performance():
    """Get performance statistics (win rate, P&L, etc.)."""
    try:
        trader = _get_trader()
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
async def get_faith_pdt_status():
    """
    Get PDT (Pattern Day Trader) status.

    Returns day trade count, remaining trades, and next reset date.
    """
    try:
        trader = _get_trader()
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
async def get_faith_paper_account():
    """Get paper account balance and collateral data."""
    try:
        trader = _get_trader()
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
async def get_faith_position_monitor():
    """
    Get live position monitoring data.

    Returns real-time progress toward profit target, stop loss, and EOD cutoff.
    Returns null data field if no open position.
    """
    try:
        trader = _get_trader()
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
async def get_faith_equity_curve():
    """Get historical equity curve from closed trades."""
    try:
        trader = _get_trader()
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


@router.get("/api/faith/logs")
async def get_faith_logs(limit: int = 100):
    """Get activity logs."""
    try:
        trader = _get_trader()
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
async def toggle_faith(active: bool = True):
    """Enable or disable the FAITH bot."""
    try:
        trader = _get_trader()
        result = trader.toggle(active)
        return {"status": "success", "data": result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"FAITH toggle error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/faith/run-cycle")
async def run_faith_cycle(close_only: bool = False):
    """
    Manually trigger a FAITH scan/trade cycle.

    Args:
        close_only: If true, only manage existing positions (no new trades)
    """
    try:
        trader = _get_trader()
        result = trader.run_cycle(close_only=close_only)
        return {"status": "success", "data": result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"FAITH run cycle error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
