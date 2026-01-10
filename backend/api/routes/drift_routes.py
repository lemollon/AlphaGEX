"""
Drift Detection API Routes
===========================

Provides endpoints for comparing backtest vs live trading performance.
"""

from fastapi import APIRouter, HTTPException
from typing import Optional
import logging

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Drift Detection"])

# Import drift detector
DRIFT_AVAILABLE = False
try:
    from quant.backtest_live_drift import (
        get_drift_detector,
        check_bot_drift,
        check_all_bots_drift,
        DriftSeverity
    )
    DRIFT_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Drift detector not available: {e}")


@router.get("/api/drift/status")
async def get_all_drift_status(lookback_days: int = 90):
    """
    Get drift status for all bots.

    Returns performance comparison between backtest expectations and live results.
    """
    if not DRIFT_AVAILABLE:
        return {
            "status": "unavailable",
            "message": "Drift detector not available",
            "bots": {}
        }

    try:
        reports = check_all_bots_drift(lookback_days)

        return {
            "status": "success",
            "lookback_days": lookback_days,
            "bots": reports
        }
    except Exception as e:
        logger.error(f"Failed to get drift status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/drift/bot/{bot_name}")
async def get_bot_drift_status(bot_name: str, lookback_days: int = 90):
    """
    Get drift status for a specific bot.

    Args:
        bot_name: Bot name (ARES, ATHENA, ICARUS, PEGASUS, TITAN)
        lookback_days: Number of days of live data to analyze
    """
    if not DRIFT_AVAILABLE:
        return {
            "status": "unavailable",
            "message": "Drift detector not available"
        }

    try:
        report = check_bot_drift(bot_name.upper(), lookback_days)

        if not report:
            return {
                "status": "no_data",
                "bot_name": bot_name.upper(),
                "message": "Insufficient backtest or live data for analysis"
            }

        return {
            "status": "success",
            "data": report
        }
    except Exception as e:
        logger.error(f"Failed to get drift for {bot_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/drift/history/{bot_name}")
async def get_bot_drift_history(bot_name: str, days: int = 30):
    """
    Get historical drift analysis for a bot.

    Shows how drift has changed over time.
    """
    if not DRIFT_AVAILABLE:
        return {
            "status": "unavailable",
            "message": "Drift detector not available"
        }

    try:
        detector = get_drift_detector()
        history = detector.get_drift_history(bot_name.upper(), days)

        return {
            "status": "success",
            "bot_name": bot_name.upper(),
            "days": days,
            "history": history
        }
    except Exception as e:
        logger.error(f"Failed to get drift history for {bot_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/drift/summary")
async def get_drift_summary():
    """
    Get a quick summary of drift status for dashboard display.

    Returns simplified status for each bot.
    """
    if not DRIFT_AVAILABLE:
        return {
            "status": "unavailable",
            "bots": []
        }

    try:
        reports = check_all_bots_drift(90)

        summary = []
        for bot_name, report in reports.items():
            # Find expectancy metric for the main drift value
            expectancy_drift = 0
            for metric in report.get('metrics', []):
                if metric.get('metric') == 'Expectancy %':
                    expectancy_drift = metric.get('drift_pct', 0)
                    break

            summary.append({
                "bot": bot_name,
                "severity": report.get('overall_severity', 'NORMAL'),
                "drift_pct": round(expectancy_drift, 1),
                "live_trades": report.get('live_trades', 0),
                "backtest_trades": report.get('backtest_trades', 0)
            })

        # Sort by severity (CRITICAL first)
        severity_order = {'CRITICAL': 0, 'WARNING': 1, 'NORMAL': 2, 'OUTPERFORM': 3}
        summary.sort(key=lambda x: severity_order.get(x['severity'], 2))

        # Count issues
        critical_count = sum(1 for s in summary if s['severity'] == 'CRITICAL')
        warning_count = sum(1 for s in summary if s['severity'] == 'WARNING')

        return {
            "status": "success",
            "critical_count": critical_count,
            "warning_count": warning_count,
            "bots": summary
        }
    except Exception as e:
        logger.error(f"Failed to get drift summary: {e}")
        return {
            "status": "error",
            "message": str(e),
            "bots": []
        }
