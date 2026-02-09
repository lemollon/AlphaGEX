"""
VALOR API Routes
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
router = APIRouter(tags=["VALOR"])

# Import VALOR components with graceful fallback
ValorTrader = None
get_valor_trader = None
run_valor_scan = None

try:
    from trading.valor import (
        ValorTrader,
        get_valor_trader,
        run_valor_scan,
    )
    logger.info("✅ VALOR module loaded")
except ImportError as e:
    logger.warning(f"⚠️ VALOR module not available: {e}")


def _get_trader():
    """Get VALOR trader instance or raise error"""
    if get_valor_trader is None:
        raise HTTPException(
            status_code=503,
            detail="VALOR module not available"
        )
    return get_valor_trader()


# ============================================================================
# Status Endpoint
# ============================================================================

@router.get("/api/valor/status")
async def get_valor_status():
    """
    Get VALOR bot status and configuration.

    Returns current status, configuration, open positions count,
    and performance summary.
    """
    try:
        trader = _get_trader()
        return trader.get_status()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting VALOR status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Position Endpoints
# ============================================================================

@router.get("/api/valor/positions")
async def get_valor_positions():
    """
    Get all open VALOR positions with unrealized P&L.
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
        logger.error(f"Error getting VALOR positions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/valor/closed-trades")
async def get_valor_closed_trades(
    limit: int = Query(1000, ge=1, le=10000, description="Number of trades to return (default: 1000 to show all daily trades)"),
    today_only: bool = Query(False, description="If true, only return today's trades")
):
    """
    Get VALOR closed trade history.

    By default returns up to 1000 trades (enough for all daily trades).
    Use today_only=true to filter to just today's trades.
    """
    try:
        trader = _get_trader()
        trades = trader.get_closed_trades(limit=limit)

        # Filter to today only if requested
        if today_only:
            from zoneinfo import ZoneInfo
            today = datetime.now(ZoneInfo("America/Chicago")).date()
            trades = [
                t for t in trades
                if t.get('close_time') and datetime.fromisoformat(t['close_time'].replace('Z', '+00:00')).astimezone(ZoneInfo("America/Chicago")).date() == today
            ]

        # Calculate daily summary
        today_trades = []
        from zoneinfo import ZoneInfo
        today = datetime.now(ZoneInfo("America/Chicago")).date()
        for t in trades:
            try:
                if t.get('close_time'):
                    trade_date = datetime.fromisoformat(t['close_time'].replace('Z', '+00:00')).astimezone(ZoneInfo("America/Chicago")).date()
                    if trade_date == today:
                        today_trades.append(t)
            except Exception:
                pass

        today_pnl = sum(float(t.get('realized_pnl', 0) or 0) for t in today_trades)
        today_wins = sum(1 for t in today_trades if float(t.get('realized_pnl', 0) or 0) > 0)
        today_losses = len(today_trades) - today_wins

        return {
            "trades": trades,
            "count": len(trades),
            "today_summary": {
                "trades_today": len(today_trades),
                "wins_today": today_wins,
                "losses_today": today_losses,
                "pnl_today": today_pnl,
                "win_rate_today": (today_wins / len(today_trades) * 100) if today_trades else 0
            },
            "timestamp": datetime.now().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting VALOR closed trades: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Equity Curve Endpoints
# ============================================================================

@router.get("/api/valor/equity-curve")
async def get_valor_equity_curve(
    days: int = Query(30, ge=1, le=365, description="Number of days of history")
):
    """
    Get VALOR historical equity curve.
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
        logger.error(f"Error getting VALOR equity curve: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/valor/equity-curve/intraday")
async def get_heracles_intraday_equity():
    """
    Get VALOR today's equity snapshots.
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
        logger.error(f"Error getting VALOR intraday equity: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Performance Endpoint
# ============================================================================

@router.get("/api/valor/performance")
async def get_valor_performance():
    """
    Get VALOR performance statistics.

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
        logger.error(f"Error getting VALOR performance: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Logs Endpoint
# ============================================================================

@router.get("/api/valor/logs")
async def get_valor_logs(
    limit: int = Query(100, ge=1, le=1000, description="Number of log entries")
):
    """
    Get VALOR activity logs for audit trail.
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
        logger.error(f"Error getting VALOR logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Signals Endpoint
# ============================================================================

@router.get("/api/valor/signals/recent")
async def get_heracles_recent_signals(
    limit: int = Query(50, ge=1, le=500, description="Number of signals")
):
    """
    Get recent VALOR signals (scan activity).
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
        logger.error(f"Error getting VALOR signals: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Manual Scan Trigger (for testing)
# ============================================================================

@router.post("/api/valor/scan")
async def trigger_heracles_scan():
    """
    Manually trigger a VALOR trading scan.

    This is for testing - in production, scans are triggered by the scheduler.
    """
    try:
        if run_valor_scan is None:
            raise HTTPException(
                status_code=503,
                detail="VALOR module not available"
            )

        result = run_valor_scan()
        return {
            "success": True,
            "scan_result": result,
            "timestamp": datetime.now().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error triggering VALOR scan: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Configuration Endpoint
# ============================================================================

@router.get("/api/valor/config")
async def get_valor_config():
    """
    Get VALOR configuration.
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
        logger.error(f"Error getting VALOR config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Win Probability Tracker
# ============================================================================

@router.get("/api/valor/win-tracker")
async def get_heracles_win_tracker():
    """
    Get VALOR Bayesian win probability tracker stats.

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
        logger.error(f"Error getting VALOR win tracker: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Market Status
# ============================================================================

@router.get("/api/valor/market-status")
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

@router.get("/api/valor/paper-account")
async def get_heracles_paper_account():
    """
    Get VALOR paper trading account status.

    Returns current balance, cumulative P&L, margin usage,
    and performance metrics for the virtual paper trading account.
    """
    try:
        trader = _get_trader()
        paper_account = trader.get_paper_account()

        if not paper_account:
            return {
                "exists": False,
                "message": "No paper trading account initialized. Call POST /api/valor/paper-account/initialize to create one.",
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


@router.post("/api/valor/paper-account/initialize")
async def initialize_heracles_paper_account(
    starting_capital: float = Query(100000.0, ge=1000, le=10000000, description="Starting capital for paper trading")
):
    """
    Initialize VALOR paper trading account.

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


@router.post("/api/valor/paper-account/reset")
async def reset_heracles_paper_account(
    starting_capital: float = Query(100000.0, ge=1000, le=10000000, description="Starting capital for new account"),
    full_reset: bool = Query(True, description="If true, also clears closed_trades, positions, equity snapshots for clean slate")
):
    """
    Reset VALOR paper trading account.

    Deactivates current account and creates a fresh one.
    WARNING: This will lose all paper trading history.

    With full_reset=True (default), also clears:
    - All closed trades history
    - All open positions
    - All equity snapshots
    - Resets win tracker to default priors

    This ensures data consistency after bugs where tables got out of sync.
    """
    try:
        trader = _get_trader()
        success = trader.db.reset_paper_account(starting_capital, full_reset=full_reset)

        if success:
            paper_account = trader.get_paper_account()
            return {
                "success": True,
                "message": f"Paper trading account {'FULLY ' if full_reset else ''}reset with ${starting_capital:,.2f}",
                "full_reset": full_reset,
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


@router.get("/api/valor/data-integrity")
async def check_valor_data_integrity():
    """
    Check data integrity between paper_account and closed_trades.

    Returns whether the cumulative P&L in paper_account matches the sum
    of realized_pnl in closed_trades. A discrepancy indicates a bug
    caused trades to be recorded in one place but not the other.

    This should be checked periodically to catch issues early.
    """
    try:
        trader = _get_trader()
        result = trader.db.verify_data_integrity()

        return {
            "is_consistent": result.get("is_consistent", False),
            "paper_account_pnl": result.get("paper_pnl", 0),
            "closed_trades_pnl": result.get("trades_pnl", 0),
            "discrepancy": result.get("discrepancy", 0),
            "paper_trade_count": result.get("trade_count_account", 0),
            "actual_trade_count": result.get("trade_count_actual", 0),
            "checked_at": result.get("checked_at"),
            "recommendation": "OK" if result.get("is_consistent") else "RESET RECOMMENDED - use POST /api/valor/paper-account/reset with full_reset=true"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error checking data integrity: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/valor/diagnostics")
async def get_heracles_diagnostics():
    """
    DIAGNOSTIC ENDPOINT: Get raw counts and data from all VALOR tables.

    Use this to debug data sync issues between tables.
    """
    try:
        trader = _get_trader()

        # Get raw counts from each table
        diagnostics = trader.db.get_diagnostics()

        return {
            "timestamp": datetime.now().isoformat(),
            "diagnostics": diagnostics
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting diagnostics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/valor/force-reset")
async def force_reset_heracles():
    """
    EMERGENCY: Force a complete reset of all VALOR data.

    Use when data is corrupted and auto-reset didn't work.
    """
    try:
        trader = _get_trader()

        # Force full reset
        success = trader.db.reset_paper_account(
            starting_capital=trader.config.capital,
            full_reset=True
        )

        if success:
            # Verify the reset worked
            integrity = trader.db.verify_data_integrity()
            return {
                "success": True,
                "message": "Force reset completed",
                "integrity_after_reset": integrity,
                "timestamp": datetime.now().isoformat()
            }
        else:
            return {
                "success": False,
                "message": "Force reset failed",
                "timestamp": datetime.now().isoformat()
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in force reset: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/valor/cleanup-orphaned-positions")
async def cleanup_orphaned_positions():
    """
    Fix orphaned positions that show as 'open' but have closed trade records.

    This can happen if the position status UPDATE fails but the closed_trades INSERT
    succeeds. This endpoint finds and fixes such inconsistencies.

    Returns:
        - orphaned_found: Number of orphaned positions found
        - updated: Number of positions fixed
        - errors: Number of errors during cleanup
    """
    try:
        trader = _get_trader()
        result = trader.db.cleanup_orphaned_positions()
        return {
            "success": True,
            "cleanup_result": result,
            "message": f"Cleanup complete: {result['updated']}/{result['orphaned_found']} orphaned positions fixed",
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error cleaning up orphaned positions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Scan Activity (ML Training Data Collection)
# ============================================================================

@router.get("/api/valor/scan-activity")
async def get_valor_scan_activity(
    limit: int = Query(1000, ge=1, le=10000, description="Number of scans to return (default: 1000 to show all daily activity)"),
    outcome: Optional[str] = Query(None, description="Filter by outcome (TRADED, NO_TRADE, SKIP, ERROR)"),
    gamma_regime: Optional[str] = Query(None, description="Filter by gamma regime (POSITIVE, NEGATIVE, NEUTRAL)"),
    today_only: bool = Query(False, description="If true, only return today's scans")
):
    """
    Get VALOR scan activity log.

    Per STANDARDS.md Bot-Specific Requirements, this endpoint provides
    visibility into EVERY scan the bot performs, including:
    - Market conditions at scan time
    - Signals generated and their parameters
    - Decisions made and why
    - Trade execution details

    By default returns up to 1000 scans (enough for all daily activity).
    This data is critical for ML model training.
    """
    try:
        trader = _get_trader()
        scans = trader.db.get_scan_activity(
            limit=limit,
            outcome=outcome,
            gamma_regime=gamma_regime
        )

        # Filter to today only if requested
        if today_only:
            from zoneinfo import ZoneInfo
            today = datetime.now(ZoneInfo("America/Chicago")).date()
            scans = [
                s for s in scans
                if s.get('scan_time') and datetime.fromisoformat(s['scan_time'].replace('Z', '+00:00')).astimezone(ZoneInfo("America/Chicago")).date() == today
            ]

        # Calculate summary statistics
        total_scans = len(scans)
        traded_count = len([s for s in scans if s.get('outcome') == 'TRADED'])
        no_trade_count = len([s for s in scans if s.get('outcome') == 'NO_TRADE'])
        skip_count = len([s for s in scans if s.get('outcome') == 'SKIP'])
        error_count = len([s for s in scans if s.get('outcome') == 'ERROR'])
        market_closed_count = len([s for s in scans if s.get('outcome') == 'MARKET_CLOSED'])

        # Calculate today's stats
        from zoneinfo import ZoneInfo
        today = datetime.now(ZoneInfo("America/Chicago")).date()
        today_scans = []
        for s in scans:
            try:
                if s.get('scan_time'):
                    scan_date = datetime.fromisoformat(s['scan_time'].replace('Z', '+00:00')).astimezone(ZoneInfo("America/Chicago")).date()
                    if scan_date == today:
                        today_scans.append(s)
            except Exception:
                pass

        today_traded = len([s for s in today_scans if s.get('outcome') == 'TRADED'])

        return {
            "scans": scans,
            "count": total_scans,
            "summary": {
                "traded": traded_count,
                "no_trade": no_trade_count,
                "skip": skip_count,
                "error": error_count,
                "market_closed": market_closed_count,
                "trade_rate_pct": (traded_count / total_scans * 100) if total_scans > 0 else 0
            },
            "today_summary": {
                "scans_today": len(today_scans),
                "traded_today": today_traded,
                "trade_rate_today_pct": (today_traded / len(today_scans) * 100) if today_scans else 0
            },
            "timestamp": datetime.now().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting scan activity: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/valor/ml-training-data")
async def get_heracles_ml_training_data():
    """
    Get VALOR ML training data.

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


@router.get("/api/valor/ml/training-data-stats")
async def get_heracles_ml_training_data_stats():
    """
    Get statistics about ML training data quality.

    Shows breakdown of trades BEFORE vs AFTER parameter version change.
    ML should only be trained on NEW parameter trades to ensure
    the model learns from quality data with balanced risk/reward.

    Returns:
    - parameter_version: Current parameter version
    - parameter_version_date: When new parameters were deployed
    - old_parameter_trades: Count/win_rate of trades with OLD parameters (garbage data)
    - new_parameter_trades: Count/win_rate of trades with NEW parameters (quality data)
    - ready_for_ml_training: True if enough new parameter trades exist
    - trades_needed_for_ml: How many more trades needed before ML training
    """
    try:
        from trading.valor.ml import get_training_data_stats

        stats = get_training_data_stats()

        if 'error' in stats:
            raise HTTPException(status_code=500, detail=stats['error'])

        return {
            **stats,
            "timestamp": datetime.now().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting ML training data stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# ML Model Training Endpoints
# ============================================================================

@router.post("/api/valor/ml/train")
async def train_heracles_ml_model(
    min_samples: int = 50,
    use_new_params_only: bool = Query(
        True,
        description="Only train on trades AFTER parameter version date (recommended). "
                    "Set to False to use all historical data (not recommended - old data has poor risk/reward)."
    )
):
    """
    Train the VALOR ML model from scan_activity data.

    Trains an XGBoost classifier to predict trade win probability,
    replacing the Bayesian estimator with ML-enhanced predictions.

    By default, only trains on trades AFTER the parameter version date.
    This ensures the model learns from quality data with balanced risk/reward.
    Old parameter trades had asymmetric risk/reward (big losses, small wins)
    which produces a model that can't predict properly.

    Requires at least 50 samples (trades with recorded outcomes).
    Returns comparison with previous model if one exists.
    """
    try:
        from trading.valor.ml import get_heracles_ml_advisor

        advisor = get_heracles_ml_advisor()

        # Capture previous model metrics for comparison
        previous_metrics = None
        if advisor.is_trained and advisor.training_metrics:
            prev = advisor.training_metrics
            previous_metrics = {
                "accuracy": round(prev.accuracy, 4),
                "precision": round(prev.precision, 4),
                "recall": round(prev.recall, 4),
                "f1_score": round(prev.f1_score, 4),
                "auc_roc": round(prev.auc_roc, 4),
                "brier_score": round(prev.brier_score, 4),
                "training_samples": prev.total_samples,
                "training_date": prev.training_date,
            }

        # Get current data count first (using new params filter)
        training_df = advisor.get_training_data(use_new_params_only=use_new_params_only)
        if training_df is None or len(training_df) < min_samples:
            sample_count = len(training_df) if training_df is not None else 0

            # Get stats about old vs new data for helpful error message
            from trading.valor.ml import get_training_data_stats
            stats = get_training_data_stats()

            return {
                "success": False,
                "error": f"Insufficient training data. Have {sample_count} samples, need {min_samples}.",
                "samples_available": sample_count,
                "samples_required": min_samples,
                "use_new_params_only": use_new_params_only,
                "data_breakdown": {
                    "old_parameter_trades": stats.get('old_parameter_trades', {}).get('count', 0),
                    "new_parameter_trades": stats.get('new_parameter_trades', {}).get('count', 0),
                    "trades_needed": stats.get('trades_needed_for_ml', min_samples - sample_count),
                    "recommendation": stats.get('recommendation', '')
                }
            }

        # Train the model (with new params filter)
        metrics = advisor.train(min_samples=min_samples, use_new_params_only=use_new_params_only)

        if not metrics:
            return {
                "success": False,
                "error": "Training failed - check logs for details"
            }

        # Build comparison analysis
        comparison = None
        improvement_reasons = []
        is_improvement = False

        if previous_metrics:
            acc_change = metrics.accuracy - previous_metrics["accuracy"]
            auc_change = metrics.auc_roc - previous_metrics["auc_roc"]
            precision_change = metrics.precision - previous_metrics["precision"]
            sample_change = metrics.total_samples - previous_metrics["training_samples"]

            comparison = {
                "previous": previous_metrics,
                "changes": {
                    "accuracy": round(acc_change, 4),
                    "auc_roc": round(auc_change, 4),
                    "precision": round(precision_change, 4),
                    "samples_added": sample_change,
                }
            }

            # Determine if this is an improvement
            if acc_change > 0.01:  # >1% improvement
                improvement_reasons.append(f"Accuracy improved by {acc_change*100:.1f}%")
            if auc_change > 0.01:
                improvement_reasons.append(f"AUC-ROC improved by {auc_change:.3f}")
            if precision_change > 0.01:
                improvement_reasons.append(f"Precision improved by {precision_change*100:.1f}%")
            if sample_change > 10:
                improvement_reasons.append(f"Trained on {sample_change} more samples")

            # Check for regressions
            regressions = []
            if acc_change < -0.02:
                regressions.append(f"Accuracy dropped by {abs(acc_change)*100:.1f}%")
            if auc_change < -0.02:
                regressions.append(f"AUC-ROC dropped by {abs(auc_change):.3f}")

            is_improvement = len(improvement_reasons) > 0 and len(regressions) == 0

            comparison["is_improvement"] = is_improvement
            comparison["improvement_reasons"] = improvement_reasons
            comparison["regressions"] = regressions
            comparison["recommendation"] = (
                "APPROVE: New model shows improvement" if is_improvement else
                "REVIEW: Check if regressions are acceptable" if regressions else
                "APPROVE: Model retrained with more data"
            )
        else:
            # First model - always recommend approval if metrics are reasonable
            is_improvement = metrics.accuracy > 0.55  # Better than random
            improvement_reasons = [
                f"First ML model trained with {metrics.total_samples} samples",
                f"Accuracy: {metrics.accuracy*100:.1f}% (above 55% threshold)" if metrics.accuracy > 0.55 else f"Accuracy: {metrics.accuracy*100:.1f}%",
                f"AUC-ROC: {metrics.auc_roc:.3f}" + (" (good discrimination)" if metrics.auc_roc > 0.6 else ""),
            ]
            comparison = {
                "previous": None,
                "is_improvement": is_improvement,
                "improvement_reasons": improvement_reasons,
                "regressions": [],
                "recommendation": "APPROVE: First ML model shows promising results" if is_improvement else "REVIEW: Model accuracy is below 55% threshold"
            }

        return {
            "success": True,
            "message": f"VALOR ML trained on {metrics.total_samples} trades",
            "metrics": {
                "accuracy": round(metrics.accuracy, 4),
                "precision": round(metrics.precision, 4),
                "recall": round(metrics.recall, 4),
                "f1_score": round(metrics.f1_score, 4),
                "auc_roc": round(metrics.auc_roc, 4),
                "brier_score": round(metrics.brier_score, 4),
                "win_rate_actual": round(metrics.win_rate_actual, 4),
                "win_rate_predicted": round(metrics.win_rate_predicted, 4),
                "positive_gamma_accuracy": round(metrics.positive_gamma_accuracy, 4) if metrics.positive_gamma_accuracy else None,
                "negative_gamma_accuracy": round(metrics.negative_gamma_accuracy, 4) if metrics.negative_gamma_accuracy else None,
            },
            "samples": {
                "total": metrics.total_samples,
                "wins": metrics.wins,
                "losses": metrics.losses
            },
            "comparison": comparison,
            "training_samples": metrics.total_samples,
            "model_version": metrics.model_version,
            "training_date": metrics.training_date,
            "timestamp": datetime.now().isoformat()
        }

    except ValueError as e:
        return {
            "success": False,
            "error": str(e)
        }
    except ImportError as e:
        logger.error(f"ML libraries not available: {e}")
        return {
            "success": False,
            "error": f"ML libraries not available: {e}. Install with: pip install xgboost scikit-learn"
        }
    except Exception as e:
        logger.error(f"Error training VALOR ML: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e)
        }


@router.get("/api/valor/ml/status")
async def get_heracles_ml_status():
    """
    Get VALOR ML model status.

    Shows whether model is trained, accuracy metrics, and training info.
    """
    try:
        from trading.valor.ml import get_heracles_ml_advisor

        advisor = get_heracles_ml_advisor()
        status = advisor.get_status()

        # Also get training data availability
        training_df = advisor.get_training_data()
        samples_available = len(training_df) if training_df is not None else 0

        return {
            "model_trained": status['is_trained'],
            "model_version": status['model_version'],
            "training_date": status['training_date'],
            "accuracy": status['accuracy'],
            "auc_roc": status['auc_roc'],
            "samples_trained_on": status['samples'],
            "win_rate": status['win_rate'],
            "samples_available": samples_available,
            "ready_for_training": samples_available >= 50,
            "can_retrain": samples_available >= 50,
            "timestamp": datetime.now().isoformat()
        }

    except ImportError:
        return {
            "model_trained": False,
            "error": "ML module not available",
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting ML status: {e}")
        return {
            "model_trained": False,
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }


@router.get("/api/valor/ml/feature-importance")
async def get_heracles_ml_feature_importance():
    """
    Get VALOR ML feature importance rankings.

    Shows which features have the most impact on win probability prediction.
    """
    try:
        from trading.valor.ml import get_heracles_ml_advisor

        advisor = get_heracles_ml_advisor()

        if not advisor.is_trained:
            return {
                "success": True,
                "model_trained": False,
                "features": [],
                "message": "Train the model first to see feature importance"
            }

        features = advisor.get_feature_importance()

        return {
            "success": True,
            "model_trained": True,
            "features": features,
            "model_version": advisor.model_version,
            "timestamp": datetime.now().isoformat()
        }

    except ImportError:
        return {
            "success": False,
            "model_trained": False,
            "features": [],
            "error": "ML module not available"
        }
    except Exception as e:
        logger.error(f"Error getting feature importance: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@router.post("/api/valor/ml/approve")
async def approve_heracles_ml_model():
    """
    Approve the ML model for use in signal generation.

    After training, the ML model is NOT automatically used.
    You must explicitly approve it after reviewing the training results.
    This activates the ML model for win probability predictions.
    """
    try:
        from trading.valor.signals import approve_ml_model, is_ml_approved
        from trading.valor.ml import get_heracles_ml_advisor

        # Check if model is trained first
        advisor = get_heracles_ml_advisor()
        if not advisor.is_trained:
            return {
                "success": False,
                "error": "No ML model trained. Train the model first before approving.",
                "ml_approved": False,
                "timestamp": datetime.now().isoformat()
            }

        # Approve the model
        success = approve_ml_model()

        return {
            "success": success,
            "message": "ML model approved and now active for win probability predictions" if success else "Failed to approve ML model",
            "ml_approved": is_ml_approved(),
            "model_version": advisor.model_version,
            "accuracy": advisor.training_metrics.accuracy if advisor.training_metrics else None,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Error approving ML model: {e}")
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }


@router.post("/api/valor/ml/revoke")
async def revoke_heracles_ml_approval():
    """
    Revoke ML model approval.

    Switches back to Bayesian probability estimation.
    Use this if the ML model is underperforming.
    """
    try:
        from trading.valor.signals import revoke_ml_approval, is_ml_approved

        success = revoke_ml_approval()

        return {
            "success": success,
            "message": "ML model revoked - using Bayesian probability estimation" if success else "Failed to revoke ML approval",
            "ml_approved": is_ml_approved(),
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Error revoking ML approval: {e}")
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }


@router.post("/api/valor/ml/reject")
async def reject_heracles_ml_model():
    """
    Reject the newly trained ML model.

    This completely removes the trained model and reverts to Bayesian.
    Different from revoke:
    - Revoke: Turns off ML but keeps model (can re-approve later)
    - Reject: Clears the model entirely (must retrain to use ML again)

    Use this when you train a model but decide not to use it.
    """
    try:
        from trading.valor.signals import reject_ml_model, is_ml_approved
        from trading.valor.ml import get_heracles_ml_advisor

        success = reject_ml_model()
        advisor = get_heracles_ml_advisor()

        return {
            "success": success,
            "message": "ML model rejected and cleared - using Bayesian probability estimation" if success else "Failed to reject ML model",
            "ml_approved": is_ml_approved(),
            "model_trained": advisor.is_trained if advisor else False,
            "probability_source": "BAYESIAN",
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Error rejecting ML model: {e}")
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }


@router.get("/api/valor/ml/approval-status")
async def get_heracles_ml_approval_status():
    """
    Get ML model approval status.

    Shows whether the ML model is approved and active,
    or if Bayesian fallback is being used.
    """
    try:
        from trading.valor.signals import is_ml_approved
        from trading.valor.ml import get_heracles_ml_advisor

        advisor = get_heracles_ml_advisor()
        ml_approved = is_ml_approved()

        return {
            "ml_approved": ml_approved,
            "model_trained": advisor.is_trained,
            "model_version": advisor.model_version if advisor.is_trained else None,
            "probability_source": "ML" if (ml_approved and advisor.is_trained) else "BAYESIAN",
            "accuracy": advisor.training_metrics.accuracy if advisor.training_metrics else None,
            "message": (
                "ML model is approved and active" if (ml_approved and advisor.is_trained) else
                "ML model trained but awaiting approval" if (advisor.is_trained and not ml_approved) else
                "No ML model trained - using Bayesian estimation"
            ),
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Error getting ML approval status: {e}")
        return {
            "ml_approved": False,
            "model_trained": False,
            "probability_source": "BAYESIAN",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }


# ============================================================================
# A/B Test Endpoints
# ============================================================================

@router.post("/api/valor/ab-test/enable")
async def enable_heracles_ab_test():
    """
    Enable A/B test for stop loss comparison.

    When enabled:
    - 50% of trades will use FIXED stops (base config value)
    - 50% of trades will use DYNAMIC stops (VIX/ATR/regime adjusted)

    This allows you to compare stop strategies on real trades.
    Need 100+ trades for meaningful comparison.
    """
    try:
        from trading.valor.signals import enable_ab_test, is_ab_test_enabled

        success = enable_ab_test()

        return {
            "success": success,
            "ab_test_enabled": is_ab_test_enabled(),
            "message": "A/B test enabled - 50% fixed / 50% dynamic stops" if success else "Failed to enable A/B test",
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Error enabling A/B test: {e}")
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }


@router.post("/api/valor/ab-test/disable")
async def disable_heracles_ab_test():
    """
    Disable A/B test.

    All trades will use DYNAMIC stops (default behavior).
    """
    try:
        from trading.valor.signals import disable_ab_test, is_ab_test_enabled

        success = disable_ab_test()

        return {
            "success": success,
            "ab_test_enabled": is_ab_test_enabled(),
            "message": "A/B test disabled - all trades use FIXED stops (2.5 pts / $12.50 max loss)" if success else "Failed to disable A/B test",
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Error disabling A/B test: {e}")
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }


@router.get("/api/valor/ab-test/status")
async def get_heracles_ab_test_status():
    """
    Get A/B test status and settings.
    """
    try:
        from trading.valor.signals import is_ab_test_enabled

        return {
            "ab_test_enabled": is_ab_test_enabled(),
            "description": "When enabled, 50% trades use FIXED stops, 50% use DYNAMIC stops",
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Error getting A/B test status: {e}")
        return {
            "ab_test_enabled": False,
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }


@router.get("/api/valor/ab-test/results")
async def get_heracles_ab_test_results():
    """
    Get A/B test results comparing FIXED vs DYNAMIC stops.

    Returns performance statistics for both groups:
    - Win rate, total P&L, average P&L
    - Recommendation based on results
    - Confidence level (based on sample size)

    Need 100+ trades for meaningful comparison.
    """
    try:
        trader = _get_trader()
        results = trader.db.get_ab_test_results()

        from trading.valor.signals import is_ab_test_enabled

        return {
            "ab_test_enabled": is_ab_test_enabled(),
            "results": results,
            "timestamp": datetime.now().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting A/B test results: {e}")
        return {
            "ab_test_enabled": False,
            "results": None,
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }


@router.get("/api/valor/paper-equity-curve")
async def get_heracles_paper_equity_curve(
    days: int = Query(30, ge=1, le=365, description="Number of days of history")
):
    """
    Get VALOR paper trading equity curve.

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


# ============================================================================
# Trading Control Endpoints
# ============================================================================

@router.post("/api/valor/run-cycle")
async def run_heracles_cycle():
    """
    Manually trigger a VALOR trading cycle.

    Runs a full trading scan, checking for signals and managing positions.
    Equivalent to /scan but named for consistency with other bots.
    """
    try:
        if run_valor_scan is None:
            raise HTTPException(
                status_code=503,
                detail="VALOR module not available"
            )

        result = run_valor_scan()
        return {
            "success": True,
            "action": "run_cycle",
            "result": result,
            "timestamp": datetime.now().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error running VALOR cycle: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/valor/force-close-all")
async def force_close_all_valor_positions(
    reason: str = Query("MANUAL_CLOSE", description="Reason for force close")
):
    """
    Force close all open VALOR positions.

    Immediately closes all open positions at current market price.
    Use with caution - this is an emergency action.
    """
    try:
        trader = _get_trader()
        result = trader.force_close_all(reason=reason)
        return {
            "success": True,
            "action": "force_close_all",
            "result": result,
            "timestamp": datetime.now().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error force closing VALOR positions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/valor/process-expired")
async def process_expired_valor_positions():
    """
    Manually trigger EOD position processing.

    Closes any open positions at current market price.
    Normally called automatically by scheduler at 4:00 PM CT.
    """
    try:
        trader = _get_trader()
        result = trader.process_expired_positions()
        return {
            "success": True,
            "action": "process_expired",
            "result": result,
            "timestamp": datetime.now().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing expired positions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Diagnostics Endpoint
# ============================================================================

@router.get("/api/valor/diagnostics")
async def get_heracles_diagnostics():
    """
    Get comprehensive VALOR system diagnostics.

    Includes:
    - Bot status and configuration
    - Execution capability
    - Database connectivity
    - Market connectivity
    - Position health
    - Performance metrics
    """
    try:
        trader = _get_trader()
        status = trader.get_status()

        # Check execution capability
        execution_status = {}
        try:
            execution_status = {
                "can_connect": trader.executor.session is not None if hasattr(trader.executor, 'session') else False,
                "auth_method": trader.executor.auth_method if hasattr(trader.executor, 'auth_method') else "UNKNOWN",
                "market_open": trader.executor.is_market_open() if hasattr(trader.executor, 'is_market_open') else False
            }
        except Exception as e:
            execution_status = {"error": str(e)}

        # Check database connectivity
        db_status = {}
        try:
            position_count = trader.db.get_position_count()
            trades_today = trader.db.get_trades_today_count()
            db_status = {
                "connected": True,
                "position_count": position_count,
                "trades_today": trades_today
            }
        except Exception as e:
            db_status = {"connected": False, "error": str(e)}

        # Get current quote
        quote_status = {}
        try:
            quote = trader.executor.get_mes_quote()
            if quote:
                quote_status = {
                    "available": True,
                    "last": quote.get("last", 0),
                    "bid": quote.get("bid", 0),
                    "ask": quote.get("ask", 0),
                    "source": quote.get("source", "UNKNOWN")
                }
            else:
                quote_status = {"available": False, "error": "No quote returned"}
        except Exception as e:
            quote_status = {"available": False, "error": str(e)}

        # Check GEX data availability (CRITICAL for signal generation)
        gex_status = {}
        try:
            from trading.valor.signals import get_gex_data_for_heracles
            gex_data = get_gex_data_for_heracles("SPX")
            flip_point = gex_data.get("flip_point", 0)
            net_gex = gex_data.get("net_gex", 0)
            current_price = quote_status.get("last", 0) if quote_status.get("available") else 0

            # Check if GEX data is valid (flip_point should be different from current_price)
            if flip_point > 0 and current_price > 0:
                # Check if flip_point is NOT just set to current_price (which indicates fallback)
                is_synthetic = abs(flip_point - current_price) < 1  # Within 1 point = likely fallback
                gex_status = {
                    "available": not is_synthetic,
                    "is_synthetic": is_synthetic,
                    "flip_point": flip_point,
                    "call_wall": gex_data.get("call_wall", 0),
                    "put_wall": gex_data.get("put_wall", 0),
                    "net_gex": net_gex,
                    "source": "SPX_TRADIER_PRODUCTION" if not is_synthetic else "SYNTHETIC_FALLBACK",
                    "warning": None if not is_synthetic else "GEX data unavailable - using synthetic levels. Check Tradier production API keys."
                }
            else:
                gex_status = {
                    "available": False,
                    "is_synthetic": True,
                    "flip_point": 0,
                    "net_gex": 0,
                    "source": "UNAVAILABLE",
                    "warning": "SPX GEX data unavailable. VALOR requires Tradier PRODUCTION API keys for SPX options (sandbox doesn't support SPX). Signals will use synthetic flip_point."
                }
        except Exception as e:
            gex_status = {
                "available": False,
                "is_synthetic": True,
                "error": str(e),
                "warning": f"GEX data fetch failed: {e}. Check Tradier production API configuration."
            }

        # Calculate dynamic stop for current conditions
        dynamic_stop_info = {}
        try:
            from trading.valor.signals import HERACLESSignalGenerator
            from trading.valor.models import GammaRegime

            # Get current market data
            vix = 18.0  # Default
            try:
                from data.tradier_data_fetcher import TradierDataFetcher
                fetcher = TradierDataFetcher()
                vix_quote = fetcher.get_quote("VIX")
                if vix_quote and vix_quote.get("last"):
                    vix = vix_quote["last"]
            except Exception:
                pass

            atr = 4.0  # Default estimate
            current_price = quote_status.get("last", 6000)

            # Determine gamma regime
            net_gex = gex_status.get("net_gex", 0)
            if net_gex > 0:
                gamma_regime = GammaRegime.POSITIVE
            elif net_gex < 0:
                gamma_regime = GammaRegime.NEGATIVE
            else:
                gamma_regime = GammaRegime.NEUTRAL

            # Calculate dynamic stop
            signal_gen = trader.signal_generator
            base_stop = trader.config.initial_stop_points
            dynamic_stop = signal_gen._calculate_dynamic_stop(base_stop, vix, atr, gamma_regime)

            dynamic_stop_info = {
                "enabled": True,
                "base_stop_pts": base_stop,
                "current_dynamic_stop_pts": dynamic_stop,
                "current_vix": vix,
                "current_atr": atr,
                "gamma_regime": gamma_regime.value,
                "stop_dollar_value": dynamic_stop * 5.0,  # $5 per point
                "explanation": f"Base {base_stop}pt adjusted for VIX={vix:.1f}, ATR={atr:.1f}, {gamma_regime.value} gamma → {dynamic_stop}pt (${dynamic_stop*5:.2f})"
            }
        except Exception as e:
            dynamic_stop_info = {"enabled": False, "error": str(e)}

        return {
            "bot_name": "VALOR",
            "display_name": "VALOR",  # User-facing name
            "mode": status.get("mode", "UNKNOWN"),
            "status": status.get("status", "UNKNOWN"),
            "execution": execution_status,
            "database": db_status,
            "market_data": quote_status,
            "gex_data": gex_status,  # CRITICAL: Shows if GEX data is available for signal generation
            "dynamic_stop": dynamic_stop_info,  # Dynamic stop loss calculation for current conditions
            "config": status.get("config", {}),
            "performance": status.get("performance", {}),
            "win_tracker": status.get("win_tracker", {}),
            "positions": {
                "open_count": len(status.get("positions", {}).get("positions", [])),
                "positions": status.get("positions", {}).get("positions", [])
            },
            "paper_account": status.get("paper_account", {}),
            "last_scan": status.get("last_scan"),
            "timestamp": datetime.now().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting VALOR diagnostics: {e}")
        raise HTTPException(status_code=500, detail=str(e))
