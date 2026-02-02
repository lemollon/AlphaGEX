"""
HERACLES API Routes
===================

MES Futures Scalping Bot - API endpoints for status, positions, and control.
Following AlphaGEX bot standards (per STANDARDS.md).

Endpoints:
- /status - Bot status and configuration
- /positions - Open positions with unrealized P&L
- /closed-trades - Trade history
- /equity-curve - Historical equity curve
- /equity-curve/intraday - Today's equity snapshots
- /performance - Win rate, P&L, statistics
- /logs - Activity log for audit trail
- /signals/recent - Recent signals (scan activity)
"""

import logging
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException, Query

logger = logging.getLogger(__name__)
router = APIRouter(tags=["HERACLES"])

# Import HERACLES components with graceful fallback
HERACLESTrader = None
get_heracles_trader = None
run_heracles_scan = None

try:
    from trading.heracles import (
        HERACLESTrader,
        get_heracles_trader,
        run_heracles_scan,
    )
    logger.info("✅ HERACLES module loaded")
except ImportError as e:
    logger.warning(f"⚠️ HERACLES module not available: {e}")


def _get_trader():
    """Get HERACLES trader instance or raise error"""
    if get_heracles_trader is None:
        raise HTTPException(
            status_code=503,
            detail="HERACLES module not available"
        )
    return get_heracles_trader()


# ============================================================================
# Status Endpoint
# ============================================================================

@router.get("/api/heracles/status")
async def get_heracles_status():
    """
    Get HERACLES bot status and configuration.

    Returns current status, configuration, open positions count,
    and performance summary.
    """
    try:
        trader = _get_trader()
        return trader.get_status()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting HERACLES status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Position Endpoints
# ============================================================================

@router.get("/api/heracles/positions")
async def get_heracles_positions():
    """
    Get all open HERACLES positions with unrealized P&L.
    """
    try:
        trader = _get_trader()
        status = trader.get_status()
        return {
            "positions": status.get("positions", {}).get("positions", []),
            "count": status.get("positions", {}).get("open_count", 0),
            "timestamp": datetime.now().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting HERACLES positions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/heracles/closed-trades")
async def get_heracles_closed_trades(
    limit: int = Query(50, ge=1, le=500, description="Number of trades to return")
):
    """
    Get HERACLES closed trade history.
    """
    try:
        trader = _get_trader()
        trades = trader.get_closed_trades(limit=limit)
        return {
            "trades": trades,
            "count": len(trades),
            "timestamp": datetime.now().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting HERACLES closed trades: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Equity Curve Endpoints
# ============================================================================

@router.get("/api/heracles/equity-curve")
async def get_heracles_equity_curve(
    days: int = Query(30, ge=1, le=365, description="Number of days of history")
):
    """
    Get HERACLES historical equity curve.
    """
    try:
        trader = _get_trader()
        curve = trader.get_equity_curve(days=days)
        return {
            "equity_curve": curve,
            "points": len(curve),
            "days": days,
            "timestamp": datetime.now().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting HERACLES equity curve: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/heracles/equity-curve/intraday")
async def get_heracles_intraday_equity():
    """
    Get HERACLES today's equity snapshots.
    """
    try:
        trader = _get_trader()
        curve = trader.get_intraday_equity()
        return {
            "equity_curve": curve,
            "points": len(curve),
            "timestamp": datetime.now().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting HERACLES intraday equity: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Performance Endpoint
# ============================================================================

@router.get("/api/heracles/performance")
async def get_heracles_performance():
    """
    Get HERACLES performance statistics.

    Includes win rate, total P&L, average win/loss,
    profit factor, and regime-specific stats.
    """
    try:
        trader = _get_trader()
        status = trader.get_status()
        return {
            "performance": status.get("performance", {}),
            "win_tracker": status.get("win_tracker", {}),
            "today": status.get("today", {}),
            "timestamp": datetime.now().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting HERACLES performance: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Logs Endpoint
# ============================================================================

@router.get("/api/heracles/logs")
async def get_heracles_logs(
    limit: int = Query(100, ge=1, le=1000, description="Number of log entries")
):
    """
    Get HERACLES activity logs for audit trail.
    """
    try:
        trader = _get_trader()
        logs = trader.get_logs(limit=limit)
        return {
            "logs": logs,
            "count": len(logs),
            "timestamp": datetime.now().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting HERACLES logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Signals Endpoint
# ============================================================================

@router.get("/api/heracles/signals/recent")
async def get_heracles_recent_signals(
    limit: int = Query(50, ge=1, le=500, description="Number of signals")
):
    """
    Get recent HERACLES signals (scan activity).
    """
    try:
        trader = _get_trader()
        signals = trader.get_recent_signals(limit=limit)
        return {
            "signals": signals,
            "count": len(signals),
            "timestamp": datetime.now().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting HERACLES signals: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Manual Scan Trigger (for testing)
# ============================================================================

@router.post("/api/heracles/scan")
async def trigger_heracles_scan():
    """
    Manually trigger a HERACLES trading scan.

    This is for testing - in production, scans are triggered by the scheduler.
    """
    try:
        if run_heracles_scan is None:
            raise HTTPException(
                status_code=503,
                detail="HERACLES module not available"
            )

        result = run_heracles_scan()
        return {
            "success": True,
            "scan_result": result,
            "timestamp": datetime.now().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error triggering HERACLES scan: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Configuration Endpoint
# ============================================================================

@router.get("/api/heracles/config")
async def get_heracles_config():
    """
    Get HERACLES configuration.
    """
    try:
        trader = _get_trader()
        status = trader.get_status()
        return {
            "config": status.get("config", {}),
            "symbol": status.get("symbol"),
            "mode": status.get("mode"),
            "timestamp": datetime.now().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting HERACLES config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Win Probability Tracker
# ============================================================================

@router.get("/api/heracles/win-tracker")
async def get_heracles_win_tracker():
    """
    Get HERACLES Bayesian win probability tracker stats.

    Shows current win probability estimates by gamma regime.
    """
    try:
        trader = _get_trader()
        status = trader.get_status()
        return {
            "win_tracker": status.get("win_tracker", {}),
            "timestamp": datetime.now().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting HERACLES win tracker: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Market Status
# ============================================================================

@router.get("/api/heracles/market-status")
async def get_heracles_market_status():
    """
    Check if MES futures market is open.
    """
    try:
        trader = _get_trader()
        is_open = trader.executor.is_market_open()
        maintenance_seconds = trader.executor.get_maintenance_break_seconds()

        return {
            "market_open": is_open,
            "in_maintenance": maintenance_seconds > 0,
            "maintenance_seconds_remaining": maintenance_seconds,
            "symbol": trader.config.symbol,
            "timestamp": datetime.now().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting market status: {e}")
        raise HTTPException(status_code=500, detail=str(e))
