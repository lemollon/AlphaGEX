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


# ============================================================================
# Paper Trading Account Endpoints
# ============================================================================

@router.get("/api/heracles/paper-account")
async def get_heracles_paper_account():
    """
    Get HERACLES paper trading account status.

    Returns current balance, cumulative P&L, margin usage,
    and performance metrics for the virtual paper trading account.
    """
    try:
        trader = _get_trader()
        paper_account = trader.get_paper_account()

        if not paper_account:
            return {
                "exists": False,
                "message": "No paper trading account initialized. Call POST /api/heracles/paper-account/initialize to create one.",
                "timestamp": datetime.now().isoformat()
            }

        return {
            "exists": True,
            "account": paper_account,
            "timestamp": datetime.now().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting paper account: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/heracles/paper-account/initialize")
async def initialize_heracles_paper_account(
    starting_capital: float = Query(100000.0, ge=1000, le=10000000, description="Starting capital for paper trading")
):
    """
    Initialize HERACLES paper trading account.

    Creates a new paper trading account with the specified starting capital.
    Default is $100,000.
    """
    try:
        trader = _get_trader()
        success = trader.db.initialize_paper_account(starting_capital)

        if success:
            paper_account = trader.get_paper_account()
            return {
                "success": True,
                "message": f"Paper trading account initialized with ${starting_capital:,.2f}",
                "account": paper_account,
                "timestamp": datetime.now().isoformat()
            }
        else:
            return {
                "success": False,
                "message": "Failed to initialize paper account",
                "timestamp": datetime.now().isoformat()
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error initializing paper account: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/heracles/paper-account/reset")
async def reset_heracles_paper_account(
    starting_capital: float = Query(100000.0, ge=1000, le=10000000, description="Starting capital for new account")
):
    """
    Reset HERACLES paper trading account.

    Deactivates current account and creates a fresh one.
    WARNING: This will lose all paper trading history.
    """
    try:
        trader = _get_trader()
        success = trader.reset_paper_account(starting_capital)

        if success:
            paper_account = trader.get_paper_account()
            return {
                "success": True,
                "message": f"Paper trading account reset with ${starting_capital:,.2f}",
                "account": paper_account,
                "timestamp": datetime.now().isoformat()
            }
        else:
            return {
                "success": False,
                "message": "Failed to reset paper account",
                "timestamp": datetime.now().isoformat()
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resetting paper account: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Scan Activity (ML Training Data Collection)
# ============================================================================

@router.get("/api/heracles/scan-activity")
async def get_heracles_scan_activity(
    limit: int = Query(100, ge=1, le=500, description="Number of scans to return"),
    outcome: Optional[str] = Query(None, description="Filter by outcome (TRADED, NO_TRADE, SKIP, ERROR)"),
    gamma_regime: Optional[str] = Query(None, description="Filter by gamma regime (POSITIVE, NEGATIVE, NEUTRAL)")
):
    """
    Get HERACLES scan activity log.

    Per STANDARDS.md Bot-Specific Requirements, this endpoint provides
    visibility into EVERY scan the bot performs, including:
    - Market conditions at scan time
    - Signals generated and their parameters
    - Decisions made and why
    - Trade execution details

    This data is critical for ML model training.
    """
    try:
        trader = _get_trader()
        scans = trader.db.get_scan_activity(
            limit=limit,
            outcome=outcome,
            gamma_regime=gamma_regime
        )

        # Calculate summary statistics
        total_scans = len(scans)
        traded_count = len([s for s in scans if s.get('outcome') == 'TRADED'])
        no_trade_count = len([s for s in scans if s.get('outcome') == 'NO_TRADE'])
        skip_count = len([s for s in scans if s.get('outcome') == 'SKIP'])
        error_count = len([s for s in scans if s.get('outcome') == 'ERROR'])

        return {
            "scans": scans,
            "count": total_scans,
            "summary": {
                "traded": traded_count,
                "no_trade": no_trade_count,
                "skip": skip_count,
                "error": error_count,
                "trade_rate_pct": (traded_count / total_scans * 100) if total_scans > 0 else 0
            },
            "timestamp": datetime.now().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting scan activity: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/heracles/ml-training-data")
async def get_heracles_ml_training_data():
    """
    Get HERACLES ML training data.

    Returns scan activity data formatted for supervised learning model training.
    Only includes scans where:
    1. A trade was executed
    2. The trade outcome has been recorded (position closed)

    This creates labeled data: features (market conditions) → label (win/loss)
    """
    try:
        trader = _get_trader()
        training_data = trader.db.get_ml_training_data()

        # Separate wins and losses for balance check
        wins = [t for t in training_data if t.get('trade_outcome') == 'WIN']
        losses = [t for t in training_data if t.get('trade_outcome') == 'LOSS']

        return {
            "training_data": training_data,
            "total_samples": len(training_data),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": (len(wins) / len(training_data) * 100) if training_data else 0,
            "ready_for_training": len(training_data) >= 50,
            "recommended_min_samples": 50,
            "timestamp": datetime.now().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting ML training data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/heracles/paper-equity-curve")
async def get_heracles_paper_equity_curve(
    days: int = Query(30, ge=1, le=365, description="Number of days of history")
):
    """
    Get HERACLES paper trading equity curve.

    Shows daily equity progression calculated from cumulative P&L of closed trades.
    Equity = Starting Capital + Cumulative Realized P&L
    """
    try:
        trader = _get_trader()
        curve = trader.db.get_paper_equity_curve(days=days)

        # If no trades yet, return starting point
        if not curve:
            paper_account = trader.get_paper_account()
            starting_capital = paper_account.get('starting_capital', 100000.0) if paper_account else 100000.0
            curve = [{
                'date': datetime.now().date().isoformat(),
                'daily_pnl': 0.0,
                'cumulative_pnl': 0.0,
                'equity': starting_capital,
                'trades': 0,
                'return_pct': 0.0
            }]

        return {
            "equity_curve": curve,
            "points": len(curve),
            "days": days,
            "timestamp": datetime.now().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting paper equity curve: {e}")
        raise HTTPException(status_code=500, detail=str(e))
