"""
Export API Routes

Endpoints for downloading trade data in Excel/CSV format:
- Trade history export
- P&L attribution export
- Decision logs export
- Wheel cycles export
- Full audit package
"""

import logging
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from zoneinfo import ZoneInfo

from trading.export_service import export_service, OPENPYXL_AVAILABLE

router = APIRouter(prefix="/api/export", tags=["Export"])
logger = logging.getLogger(__name__)

tz = ZoneInfo("America/New_York")


def _parse_date(date_str: Optional[str], default_days_ago: int = 30) -> datetime:
    """Parse date string or return default"""
    if date_str:
        return datetime.strptime(date_str, '%Y-%m-%d').replace(tzinfo=tz)
    return datetime.now(tz) - timedelta(days=default_days_ago)


@router.get("/trades")
async def export_trades(
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    symbol: str = Query("SPY", description="Symbol to export"),
    format: str = Query("xlsx", description="Export format: xlsx or csv")
):
    """
    Export complete trade history with full details.

    Returns Excel file with:
    - Closed Trades sheet: All completed trades with P&L
    - Open Positions sheet: Current open positions
    - Summary sheet: Win rate, total P&L, etc.
    """
    if format == 'xlsx' and not OPENPYXL_AVAILABLE:
        raise HTTPException(
            status_code=500,
            detail="Excel export not available. openpyxl not installed."
        )

    try:
        start = _parse_date(start_date, 30)
        end = _parse_date(end_date, 0) if end_date else datetime.now(tz)

        buffer = export_service.export_trade_history(
            start_date=start,
            end_date=end,
            symbol=symbol,
            format=format
        )

        filename = f"trades_{symbol}_{start.strftime('%Y%m%d')}_to_{end.strftime('%Y%m%d')}"
        content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" if format == 'xlsx' else "text/csv"
        extension = format

        return StreamingResponse(
            buffer,
            media_type=content_type,
            headers={
                "Content-Disposition": f"attachment; filename={filename}.{extension}"
            }
        )
    except Exception as e:
        logger.error(f"Error exporting trades: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pnl-attribution")
async def export_pnl_attribution(
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    symbol: str = Query("SPY", description="Symbol to export")
):
    """
    Export P&L attribution showing exactly how each trade contributed.

    Columns include:
    - Trade ID, Date, Strategy
    - Gross P&L (before costs)
    - Commission, Slippage
    - Net P&L
    - Running Total
    - Contribution % (what % of total P&L this trade represents)
    """
    if not OPENPYXL_AVAILABLE:
        raise HTTPException(
            status_code=500,
            detail="Excel export not available. openpyxl not installed."
        )

    try:
        start = _parse_date(start_date, 30)
        end = _parse_date(end_date, 0) if end_date else datetime.now(tz)

        buffer = export_service.export_pnl_attribution(
            start_date=start,
            end_date=end,
            symbol=symbol
        )

        filename = f"pnl_attribution_{symbol}_{start.strftime('%Y%m%d')}_to_{end.strftime('%Y%m%d')}"

        return StreamingResponse(
            buffer,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f"attachment; filename={filename}.xlsx"
            }
        )
    except Exception as e:
        logger.error(f"Error exporting P&L attribution: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/decision-logs")
async def export_decision_logs(
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    symbol: str = Query("SPY", description="Symbol to export")
):
    """
    Export decision logs with AI reasoning for full transparency.

    Shows what the system saw, analyzed, and decided - with full AI reasoning.

    Sheets include:
    - Decision Logs: All scan/decision events
    - AI Reasoning: Claude's thought process for each decision
    - RSI Analysis: Multi-timeframe RSI data
    """
    if not OPENPYXL_AVAILABLE:
        raise HTTPException(
            status_code=500,
            detail="Excel export not available. openpyxl not installed."
        )

    try:
        start = _parse_date(start_date, 7)  # Default 7 days for logs
        end = _parse_date(end_date, 0) if end_date else datetime.now(tz)

        buffer = export_service.export_decision_logs(
            start_date=start,
            end_date=end,
            symbol=symbol
        )

        filename = f"decision_logs_{symbol}_{start.strftime('%Y%m%d')}_to_{end.strftime('%Y%m%d')}"

        return StreamingResponse(
            buffer,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f"attachment; filename={filename}.xlsx"
            }
        )
    except Exception as e:
        logger.error(f"Error exporting decision logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/wheel-cycles")
async def export_wheel_cycles(
    symbol: Optional[str] = Query(None, description="Symbol to filter (optional)")
):
    """
    Export wheel strategy cycle history.

    Shows:
    - All wheel cycles with CSP and CC premiums
    - Assignment and call-away details
    - Total premium collected per cycle
    - P&L breakdown
    """
    if not OPENPYXL_AVAILABLE:
        raise HTTPException(
            status_code=500,
            detail="Excel export not available. openpyxl not installed."
        )

    try:
        buffer = export_service.export_wheel_cycles(symbol=symbol)

        filename = f"wheel_cycles_{symbol or 'all'}_{datetime.now(tz).strftime('%Y%m%d')}"

        return StreamingResponse(
            buffer,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f"attachment; filename={filename}.xlsx"
            }
        )
    except Exception as e:
        logger.error(f"Error exporting wheel cycles: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/full-audit")
async def export_full_audit(
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    symbol: str = Query("SPY", description="Symbol to export")
):
    """
    Export a complete audit package with ALL data.

    This is the ultimate transparency export - everything in one file:
    - Trade History
    - P&L Attribution
    - Decision Logs
    - Wheel Cycles
    - Performance Summary

    Use this to fully understand how P&L was generated.
    """
    if not OPENPYXL_AVAILABLE:
        raise HTTPException(
            status_code=500,
            detail="Excel export not available. openpyxl not installed."
        )

    try:
        start = _parse_date(start_date, 30)
        end = _parse_date(end_date, 0) if end_date else datetime.now(tz)

        buffer = export_service.export_full_audit(
            start_date=start,
            end_date=end,
            symbol=symbol
        )

        filename = f"full_audit_{symbol}_{start.strftime('%Y%m%d')}_to_{end.strftime('%Y%m%d')}"

        return StreamingResponse(
            buffer,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f"attachment; filename={filename}.xlsx"
            }
        )
    except Exception as e:
        logger.error(f"Error exporting full audit: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def get_export_status():
    """
    Check export service status and available formats.
    """
    return {
        "success": True,
        "data": {
            "excel_available": OPENPYXL_AVAILABLE,
            "csv_available": True,
            "available_exports": [
                {
                    "endpoint": "/api/export/trades",
                    "description": "Complete trade history",
                    "formats": ["xlsx", "csv"]
                },
                {
                    "endpoint": "/api/export/pnl-attribution",
                    "description": "P&L breakdown showing how each trade contributed",
                    "formats": ["xlsx"]
                },
                {
                    "endpoint": "/api/export/decision-logs",
                    "description": "AI decision reasoning and market analysis",
                    "formats": ["xlsx"]
                },
                {
                    "endpoint": "/api/export/wheel-cycles",
                    "description": "Wheel strategy cycle history",
                    "formats": ["xlsx"]
                },
                {
                    "endpoint": "/api/export/full-audit",
                    "description": "Complete audit package with all data",
                    "formats": ["xlsx"]
                }
            ]
        }
    }
