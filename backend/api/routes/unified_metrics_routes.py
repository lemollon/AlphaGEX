"""
Unified Bot Metrics API Routes

This module provides consistent, authoritative metrics endpoints for all trading bots.
These endpoints should be used by the frontend instead of individual bot endpoints
to ensure data consistency.

Key Principles:
1. ONE source of truth for capital (database config → Tradier → default)
2. ONE source of truth for all stats (database aggregates)
3. Consistent field names across all bots
4. Historical and intraday charts use SAME starting capital

Created: January 2025
Purpose: Fix data reconciliation issues between bot frontends
"""

import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Unified Metrics"])


# ==============================================================================
# PYDANTIC MODELS
# ==============================================================================

class SetCapitalRequest(BaseModel):
    """Request to set bot starting capital"""
    bot: str
    capital: float


class ReconciliationResult(BaseModel):
    """Result of data reconciliation check"""
    bot: str
    is_consistent: bool
    issues: list
    metrics_summary: dict


# ==============================================================================
# HELPER FUNCTIONS
# ==============================================================================

def _get_bot_enum(bot_name: str):
    """Convert string to BotName enum"""
    try:
        from backend.services.bot_metrics_service import BotName
        return BotName[bot_name.upper()]
    except (KeyError, AttributeError):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid bot name: {bot_name}. Valid options: ARES, ATHENA, ICARUS, TITAN, PEGASUS, HERACLES, AGAPE"
        )


# ==============================================================================
# METRICS ENDPOINTS
# ==============================================================================

@router.get("/api/metrics/{bot}/summary")
async def get_bot_metrics_summary(bot: str):
    """
    Get unified metrics summary for a bot.

    This is THE authoritative source for bot statistics.
    Frontend should use this instead of calculating stats locally.

    Returns:
    - starting_capital: Authoritative starting capital
    - current_equity: starting_capital + total_pnl
    - total_pnl: realized + unrealized
    - win_rate: Percentage (0-100), NOT decimal
    - trade_count: Total closed trades
    - All values from database, never frontend calculations
    """
    try:
        from backend.services.bot_metrics_service import get_metrics_service

        bot_enum = _get_bot_enum(bot)
        service = get_metrics_service()
        summary = service.get_metrics_summary(bot_enum)

        return {
            "success": True,
            "data": summary.to_dict()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get metrics summary for {bot}: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/metrics/{bot}/capital")
async def get_bot_capital_config(bot: str, force_refresh: bool = False):
    """
    Get the authoritative capital configuration for a bot.

    This is THE source of truth for starting capital.
    Both historical and intraday charts should use this value.

    Priority:
    1. Database config (set via /api/metrics/{bot}/capital POST)
    2. Tradier account balance (if connected)
    3. Default fallback ($100k for ARES/ATHENA/ICARUS, $200k for TITAN/PEGASUS)
    """
    try:
        from backend.services.bot_metrics_service import get_metrics_service

        bot_enum = _get_bot_enum(bot)
        service = get_metrics_service()
        config = service.get_capital_config(bot_enum, force_refresh=force_refresh)

        return {
            "success": True,
            "data": config.to_dict()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get capital config for {bot}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/metrics/{bot}/capital")
async def set_bot_capital(bot: str, request: SetCapitalRequest):
    """
    Set the starting capital for a bot.

    This should be called:
    1. When user manually configures their starting capital
    2. When first connecting to Tradier (to capture initial balance)

    The set value becomes the authoritative starting capital for all calculations.
    """
    try:
        from backend.services.bot_metrics_service import get_metrics_service

        bot_enum = _get_bot_enum(bot)

        if request.capital <= 0:
            raise HTTPException(status_code=400, detail="Capital must be positive")

        service = get_metrics_service()
        success = service.set_starting_capital(bot_enum, request.capital)

        if success:
            # Return updated config
            config = service.get_capital_config(bot_enum, force_refresh=True)
            return {
                "success": True,
                "message": f"Starting capital set to ${request.capital:,.2f}",
                "data": config.to_dict()
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to save capital configuration")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to set capital for {bot}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/metrics/{bot}/equity-curve")
async def get_bot_equity_curve(
    bot: str,
    days: int = Query(default=90, ge=1, le=365),
    include_unrealized: bool = True
):
    """
    Get historical equity curve for a bot.

    CRITICAL: Uses the SAME starting capital as intraday endpoint.
    This ensures charts align when switching between views.

    Returns equity curve points with:
    - Consistent starting capital (from /api/metrics/{bot}/capital)
    - Daily P&L aggregates
    - Cumulative P&L
    - Drawdown calculations
    """
    try:
        from backend.services.bot_metrics_service import get_metrics_service

        bot_enum = _get_bot_enum(bot)
        service = get_metrics_service()
        result = service.get_equity_curve(bot_enum, days=days, include_unrealized=include_unrealized)

        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get equity curve for {bot}: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/metrics/{bot}/equity-curve/intraday")
async def get_bot_intraday_equity(bot: str, date: Optional[str] = None):
    """
    Get intraday equity curve for a bot.

    CRITICAL: Uses the SAME starting capital as historical endpoint.
    This ensures charts align when switching between views.

    Returns:
    - market_open_equity: Starting capital + all realized P&L before today
    - Intraday snapshots with equity, realized, unrealized P&L
    - Current live point with latest data
    """
    try:
        from backend.services.bot_metrics_service import get_metrics_service

        bot_enum = _get_bot_enum(bot)
        service = get_metrics_service()
        result = service.get_intraday_equity(bot_enum, date_str=date)

        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get intraday equity for {bot}: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ==============================================================================
# RECONCILIATION / DIAGNOSTIC ENDPOINTS
# ==============================================================================

@router.get("/api/metrics/{bot}/reconcile")
async def reconcile_bot_data(bot: str):
    """
    Check data consistency for a bot.

    Compares:
    - Historical vs intraday starting capital
    - Sum of positions P&L vs reported total P&L
    - Frontend-style calculations vs backend calculations

    Returns list of any discrepancies found.
    """
    try:
        from backend.services.bot_metrics_service import get_metrics_service, BotName

        bot_enum = _get_bot_enum(bot)
        service = get_metrics_service()

        issues = []

        # Get authoritative metrics
        summary = service.get_metrics_summary(bot_enum)
        capital_config = service.get_capital_config(bot_enum)
        equity_curve = service.get_equity_curve(bot_enum, days=30)
        intraday = service.get_intraday_equity(bot_enum)

        # Check 1: Capital consistency
        hist_capital = equity_curve.get('summary', {}).get('starting_capital', 0)
        intra_capital = intraday.get('starting_equity', 0)

        if abs(hist_capital - intra_capital) > 0.01:
            issues.append({
                "type": "capital_mismatch",
                "severity": "critical",
                "message": f"Historical ({hist_capital}) vs Intraday ({intra_capital}) starting capital mismatch",
                "fix": "This should not happen with unified service - investigate"
            })

        # Check 2: Capital source
        if capital_config.capital_source == 'default':
            issues.append({
                "type": "default_capital",
                "severity": "warning",
                "message": f"Using default capital (${capital_config.starting_capital:,.0f}). Consider setting actual capital.",
                "fix": f"POST /api/metrics/{bot}/capital with your actual starting capital"
            })

        # Check 3: Tradier connection
        if not capital_config.tradier_connected:
            issues.append({
                "type": "tradier_disconnected",
                "severity": "info",
                "message": "Tradier not connected - using database/default capital",
                "fix": "Configure Tradier credentials if live trading"
            })

        # Check 4: Data freshness
        if summary.total_trades == 0:
            issues.append({
                "type": "no_trades",
                "severity": "info",
                "message": "No closed trades found",
                "fix": "Data will populate once trades are closed"
            })

        is_consistent = not any(i['severity'] == 'critical' for i in issues)

        return {
            "success": True,
            "data": {
                "bot": bot,
                "is_consistent": is_consistent,
                "issues": issues,
                "metrics_summary": summary.to_dict(),
                "capital_config": capital_config.to_dict()
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to reconcile data for {bot}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/metrics/{bot}/debug-equity")
async def debug_equity_curve(bot: str):
    """
    DEBUG endpoint to diagnose equity curve issues.

    Runs the same queries as get_equity_curve but returns raw diagnostic data.
    """
    try:
        from database_adapter import get_connection

        bot_enum = _get_bot_enum(bot)

        # Table mapping
        table_map = {
            "ARES": "ares_positions",
            "ATHENA": "athena_positions",
            "TITAN": "titan_positions",
            "PEGASUS": "pegasus_positions",
            "ICARUS": "icarus_positions",
        }
        positions_table = table_map.get(bot.upper())

        conn = get_connection()
        cursor = conn.cursor()

        # Test 1: Simple count (no timestamp handling)
        cursor.execute(f"""
            SELECT status, COUNT(*), COALESCE(SUM(realized_pnl), 0)
            FROM {positions_table}
            GROUP BY status
        """)
        status_counts = cursor.fetchall()

        # Test 2: Check if close_time and open_time exist
        cursor.execute(f"""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN close_time IS NULL THEN 1 ELSE 0 END) as null_close_time,
                SUM(CASE WHEN open_time IS NULL THEN 1 ELSE 0 END) as null_open_time
            FROM {positions_table}
            WHERE status IN ('closed', 'expired', 'partial_close')
        """)
        null_check = cursor.fetchone()

        # Test 3: Try the exact equity curve query
        error_msg = None
        trades_found = 0
        try:
            cursor.execute(f"""
                SELECT
                    COALESCE(close_time, open_time)::timestamptz AT TIME ZONE 'America/Chicago' as close_timestamp,
                    realized_pnl,
                    position_id
                FROM {positions_table}
                WHERE status IN ('closed', 'expired', 'partial_close')
                ORDER BY COALESCE(close_time, open_time)::timestamptz ASC
                LIMIT 5
            """)
            sample_trades = cursor.fetchall()
            trades_found = len(sample_trades)
        except Exception as e:
            error_msg = str(e)
            sample_trades = []

        conn.close()

        return {
            "success": True,
            "bot": bot.upper(),
            "table": positions_table,
            "diagnostics": {
                "status_breakdown": [
                    {"status": row[0], "count": row[1], "total_pnl": float(row[2])}
                    for row in status_counts
                ],
                "null_timestamps": {
                    "total_closed": null_check[0] if null_check else 0,
                    "null_close_time": null_check[1] if null_check else 0,
                    "null_open_time": null_check[2] if null_check else 0,
                },
                "equity_curve_query": {
                    "success": error_msg is None,
                    "error": error_msg,
                    "trades_found": trades_found,
                    "sample": [
                        {
                            "timestamp": str(t[0]) if t[0] else None,
                            "pnl": float(t[1]) if t[1] else 0,
                            "position_id": t[2]
                        }
                        for t in sample_trades
                    ]
                }
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        return {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }


@router.get("/api/metrics/all/summary")
async def get_all_bots_summary():
    """
    Get metrics summary for all bots at once.

    Useful for dashboard overview showing all bot performance.
    """
    try:
        from backend.services.bot_metrics_service import get_metrics_service, BotName

        service = get_metrics_service()
        summaries = {}

        for bot in BotName:
            try:
                summary = service.get_metrics_summary(bot)
                summaries[bot.value] = summary.to_dict()
            except Exception as e:
                logger.warning(f"Failed to get summary for {bot.value}: {e}")
                summaries[bot.value] = {"error": str(e)}

        return {
            "success": True,
            "data": summaries
        }

    except Exception as e:
        logger.error(f"Failed to get all bot summaries: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/metrics/all/capital")
async def get_all_bots_capital():
    """
    Get capital configuration for all bots at once.

    Useful for admin/config overview.
    """
    try:
        from backend.services.bot_metrics_service import get_metrics_service, BotName

        service = get_metrics_service()
        configs = {}

        for bot in BotName:
            try:
                config = service.get_capital_config(bot)
                configs[bot.value] = config.to_dict()
            except Exception as e:
                logger.warning(f"Failed to get capital for {bot.value}: {e}")
                configs[bot.value] = {"error": str(e)}

        return {
            "success": True,
            "data": configs
        }

    except Exception as e:
        logger.error(f"Failed to get all bot capital configs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/metrics/all/reconcile")
async def reconcile_all_bots():
    """
    Run reconciliation check on all bots.

    Returns summary of data consistency across all bots.
    """
    try:
        from backend.services.bot_metrics_service import get_metrics_service, BotName

        service = get_metrics_service()
        results = {}
        all_consistent = True

        for bot in BotName:
            try:
                # Get data for this bot
                summary = service.get_metrics_summary(bot)
                capital_config = service.get_capital_config(bot)

                issues = []

                # Check capital source
                if capital_config.capital_source == 'default':
                    issues.append({
                        "type": "default_capital",
                        "severity": "warning",
                        "message": f"Using default capital"
                    })

                if not capital_config.tradier_connected:
                    issues.append({
                        "type": "tradier_disconnected",
                        "severity": "info",
                        "message": "Tradier not connected"
                    })

                is_consistent = not any(i['severity'] == 'critical' for i in issues)
                if not is_consistent:
                    all_consistent = False

                results[bot.value] = {
                    "is_consistent": is_consistent,
                    "issues_count": len(issues),
                    "issues": issues,
                    "starting_capital": capital_config.starting_capital,
                    "capital_source": capital_config.capital_source,
                    "current_equity": summary.current_equity,
                    "total_pnl": summary.total_pnl,
                    "win_rate": summary.win_rate,
                    "total_trades": summary.total_trades
                }

            except Exception as e:
                logger.warning(f"Failed to reconcile {bot.value}: {e}")
                results[bot.value] = {
                    "is_consistent": False,
                    "error": str(e)
                }
                all_consistent = False

        return {
            "success": True,
            "all_consistent": all_consistent,
            "data": results
        }

    except Exception as e:
        logger.error(f"Failed to reconcile all bots: {e}")
        raise HTTPException(status_code=500, detail=str(e))
