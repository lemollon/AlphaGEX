"""
Scan Activity API Routes

Provides endpoints for accessing comprehensive scan activity logs
for FORTRESS, SOLOMON, GIDEON, ANCHOR, and SAMSON trading bots.

This is the key endpoint for understanding what each bot is doing
on every single scan - whether it trades or not.
"""

from fastapi import APIRouter, Query
from typing import Optional
from datetime import datetime
from zoneinfo import ZoneInfo

router = APIRouter(prefix="/api/scans", tags=["Scan Activity"])

CENTRAL_TZ = ZoneInfo("America/Chicago")


@router.get("/activity")
async def get_scan_activity(
    bot: Optional[str] = Query(None, description="Filter by bot name (FORTRESS, SOLOMON, GIDEON, ANCHOR, SAMSON)"),
    date: Optional[str] = Query(None, description="Filter by date (YYYY-MM-DD)"),
    outcome: Optional[str] = Query(None, description="Filter by outcome (TRADED, NO_TRADE, ERROR, etc.)"),
    limit: int = Query(50, description="Maximum number of records to return", le=200)
):
    """
    Get recent scan activity with full context.

    Each scan record shows:
    - When the scan happened
    - What market conditions were observed
    - What signals were generated
    - WHY a trade was or wasn't taken
    - What checks were performed

    This is the key endpoint for understanding bot behavior.
    """
    try:
        from trading.scan_activity_logger import get_recent_scans

        scans = get_recent_scans(
            bot_name=bot.upper() if bot else None,
            date=date,
            outcome=outcome.upper() if outcome else None,
            limit=limit
        )

        return {
            "success": True,
            "data": {
                "count": len(scans),
                "scans": scans,
                "filters_applied": {
                    "bot": bot,
                    "date": date,
                    "outcome": outcome
                }
            }
        }
    except ImportError:
        return {
            "success": True,
            "data": {
                "count": 0,
                "scans": [],
                "message": "Scan activity logger not available"
            }
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


@router.get("/activity/{bot_name}")
async def get_bot_scan_activity(
    bot_name: str,
    date: Optional[str] = Query(None, description="Filter by date (YYYY-MM-DD)"),
    limit: int = Query(50, description="Maximum number of records to return", le=200)
):
    """
    Get scan activity for a specific bot.

    Args:
        bot_name: FORTRESS, SOLOMON, or ANCHOR
        date: Optional date filter (YYYY-MM-DD)
        limit: Max records to return
    """
    try:
        from trading.scan_activity_logger import get_recent_scans

        scans = get_recent_scans(
            bot_name=bot_name.upper(),
            date=date,
            limit=limit
        )

        return {
            "success": True,
            "data": {
                "bot_name": bot_name.upper(),
                "count": len(scans),
                "scans": scans
            }
        }
    except ImportError:
        return {
            "success": True,
            "data": {
                "bot_name": bot_name.upper(),
                "count": 0,
                "scans": [],
                "message": "Scan activity logger not available"
            }
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


@router.get("/summary")
async def get_scan_summary(
    bot: Optional[str] = Query(None, description="Filter by bot name (FORTRESS, SOLOMON, GIDEON, ANCHOR, SAMSON)"),
    days: int = Query(7, description="Number of days to include in summary", le=30)
):
    """
    Get summary statistics for scan activity.

    Returns:
    - Total scans
    - Trades executed
    - No-trade scans
    - Error scans
    - Average confidence
    - Last scan time
    """
    try:
        from trading.scan_activity_logger import get_scan_summary

        summary = get_scan_summary(
            bot_name=bot.upper() if bot else None,
            days=days
        )

        return {
            "success": True,
            "data": summary
        }
    except ImportError:
        return {
            "success": True,
            "data": {
                "total_scans": 0,
                "trades_executed": 0,
                "no_trade_scans": 0,
                "error_scans": 0,
                "message": "Scan activity logger not available"
            }
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


@router.get("/today")
async def get_todays_scans(
    bot: Optional[str] = Query(None, description="Filter by bot name (FORTRESS, SOLOMON, ANCHOR)")
):
    """
    Get all scans from today.

    This is useful for quickly seeing what happened today.
    """
    try:
        from trading.scan_activity_logger import get_recent_scans

        today = datetime.now(CENTRAL_TZ).strftime('%Y-%m-%d')

        scans = get_recent_scans(
            bot_name=bot.upper() if bot else None,
            date=today,
            limit=200
        )

        # Calculate summary
        trades = sum(1 for s in scans if s.get('trade_executed'))
        no_trades = sum(1 for s in scans if s.get('outcome') == 'NO_TRADE')
        errors = sum(1 for s in scans if s.get('outcome') == 'ERROR')

        return {
            "success": True,
            "data": {
                "date": today,
                "total_scans": len(scans),
                "trades_executed": trades,
                "no_trade_scans": no_trades,
                "error_scans": errors,
                "scans": scans
            }
        }
    except ImportError:
        return {
            "success": True,
            "data": {
                "date": datetime.now(CENTRAL_TZ).strftime('%Y-%m-%d'),
                "total_scans": 0,
                "scans": [],
                "message": "Scan activity logger not available"
            }
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


@router.get("/fortress/today")
async def get_ares_today():
    """Get all FORTRESS scans from today with summary"""
    return await get_todays_scans(bot="FORTRESS")


@router.get("/solomon/today")
async def get_solomon_today():
    """Get all SOLOMON scans from today with summary"""
    return await get_todays_scans(bot="SOLOMON")


@router.get("/anchor/today")
async def get_anchor_today():
    """Get all ANCHOR scans from today with summary"""
    return await get_todays_scans(bot="ANCHOR")
