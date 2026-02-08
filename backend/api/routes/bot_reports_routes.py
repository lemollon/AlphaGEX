"""
Bot Daily Reports API Routes

Provides endpoints for:
- Viewing today's report
- Browsing archive of historical reports
- Downloading reports (JSON for ML, PDF-friendly markdown)
- Generating/regenerating reports on demand

Follows the Daily Manna archive pattern.

Author: AlphaGEX
Date: January 2025
"""

import json
import logging
from datetime import datetime, date, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/trader", tags=["Bot Reports"])

CENTRAL_TZ = ZoneInfo("America/Chicago")
VALID_BOTS = ['fortress', 'solomon', 'samson', 'anchor', 'gideon']

# Import report generator
try:
    from backend.services.bot_report_generator import (
        generate_report_for_bot,
        get_report_from_archive,
        get_report_summary,
        get_reports_bulk,
        get_archive_list,
        get_archive_stats,
        purge_old_reports,
        VALID_BOTS as GENERATOR_VALID_BOTS
    )
    GENERATOR_AVAILABLE = True
except ImportError as e:
    GENERATOR_AVAILABLE = False
    logger.error(f"Report generator not available: {e}")


def _validate_bot(bot: str) -> str:
    """Validate and normalize bot name."""
    bot_lower = bot.lower()
    if bot_lower not in VALID_BOTS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid bot: {bot}. Must be one of: {', '.join(VALID_BOTS)}"
        )
    return bot_lower


def _parse_date(date_str: str) -> date:
    """Parse date string to date object."""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid date format: {date_str}. Use YYYY-MM-DD"
        )


# =============================================================================
# TODAY'S REPORT
# =============================================================================

@router.get("/{bot}/reports/today/summary")
async def get_today_report_summary(bot: str):
    """
    Get a lightweight summary of today's report for dashboard display.

    This endpoint is optimized for fast loading - it only returns scalar fields
    and does NOT fetch large JSONB columns (trades_data, intraday_ticks, etc.).

    Use this for dashboard widgets that don't need full trade details.

    Args:
        bot: Bot name (fortress, solomon, samson, anchor, gideon)

    Returns:
        Lightweight report summary (no trade details or JSONB data)
    """
    if not GENERATOR_AVAILABLE:
        raise HTTPException(status_code=503, detail="Report generator service unavailable")

    bot_lower = _validate_bot(bot)
    today = datetime.now(CENTRAL_TZ).date()

    # Get lightweight summary (NO JSONB columns)
    summary = get_report_summary(bot_lower, today)
    if summary:
        return {
            "success": True,
            "data": summary,
            "cached": True,
            "message": "Report summary retrieved"
        }

    return {
        "success": True,
        "data": None,
        "cached": False,
        "message": f"No report found for {bot.upper()} today"
    }


@router.get("/{bot}/reports/today")
async def get_today_report(
    bot: str,
    force_regenerate: bool = Query(False, description="Force regenerate report even if cached")
):
    """
    Get today's report for a bot.

    Auto-generates if not exists or if force_regenerate=True.
    Returns cached report if available.

    Args:
        bot: Bot name (fortress, solomon, samson, anchor, gideon)
        force_regenerate: Force regenerate report

    Returns:
        Complete report with trades, analysis, and summary
    """
    if not GENERATOR_AVAILABLE:
        raise HTTPException(status_code=503, detail="Report generator service unavailable")

    bot_lower = _validate_bot(bot)
    today = datetime.now(CENTRAL_TZ).date()

    # Check cache first (unless force regenerate)
    if not force_regenerate:
        cached = get_report_from_archive(bot_lower, today)
        if cached:
            return {
                "success": True,
                "data": cached,
                "cached": True,
                "message": "Report retrieved from archive"
            }

    # Generate new report
    try:
        report = generate_report_for_bot(bot_lower, today)
        if report is None:
            return {
                "success": True,
                "data": None,
                "cached": False,
                "message": f"No trades for {bot.upper()} today - no report generated"
            }
        return {
            "success": True,
            "data": report,
            "cached": False,
            "message": "Report generated successfully"
        }
    except Exception as e:
        logger.error(f"Error generating report for {bot}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# ARCHIVE STATS (must be before /archive/{date} to avoid route conflict)
# =============================================================================

@router.get("/{bot}/reports/archive/stats")
async def get_report_archive_stats(bot: str):
    """
    Get statistics about the report archive.

    Returns:
        Archive statistics including total reports, date range, and totals
    """
    if not GENERATOR_AVAILABLE:
        raise HTTPException(status_code=503, detail="Report generator service unavailable")

    bot_lower = _validate_bot(bot)

    try:
        stats = get_archive_stats(bot_lower)
        return {
            "success": True,
            "data": stats
        }
    except Exception as e:
        logger.error(f"Error getting archive stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# ARCHIVE LIST
# =============================================================================

@router.get("/{bot}/reports/archive")
async def get_report_archive(
    bot: str,
    limit: int = Query(30, ge=1, le=100, description="Max reports to return"),
    offset: int = Query(0, ge=0, description="Pagination offset")
):
    """
    Get list of archived reports (summary only, not full data).

    Returns:
        List of report summaries with pagination info
    """
    if not GENERATOR_AVAILABLE:
        raise HTTPException(status_code=503, detail="Report generator service unavailable")

    bot_lower = _validate_bot(bot)

    try:
        reports, total = get_archive_list(bot_lower, limit, offset)
        return {
            "success": True,
            "data": {
                "archive": reports,
                "total": total,
                "limit": limit,
                "offset": offset
            }
        }
    except Exception as e:
        logger.error(f"Error getting archive for {bot}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# SPECIFIC DATE REPORT
# =============================================================================

@router.get("/{bot}/reports/archive/{date}")
async def get_archived_report(bot: str, date: str):
    """
    Get full report for a specific date.

    Args:
        bot: Bot name
        date: Date in YYYY-MM-DD format

    Returns:
        Full report data or 404 if not found
    """
    if not GENERATOR_AVAILABLE:
        raise HTTPException(status_code=503, detail="Report generator service unavailable")

    bot_lower = _validate_bot(bot)
    report_date = _parse_date(date)

    # Check if date is in the future
    if report_date > datetime.now(CENTRAL_TZ).date():
        raise HTTPException(status_code=400, detail="Cannot get report for future date")

    # Try to get from archive
    report = get_report_from_archive(bot_lower, report_date)

    if report:
        return {
            "success": True,
            "data": report,
            "cached": True
        }

    # Not found - return 404
    raise HTTPException(
        status_code=404,
        detail=f"No report found for {bot.upper()} on {date}. Use POST /generate to create one."
    )


# =============================================================================
# GENERATE REPORT
# =============================================================================

@router.post("/{bot}/reports/generate")
async def generate_report(
    bot: str,
    date: Optional[str] = Query(None, description="Date to generate report for (default: today)")
):
    """
    Force generate/regenerate a report.

    Args:
        bot: Bot name
        date: Optional date (YYYY-MM-DD), defaults to today

    Returns:
        Generated report
    """
    if not GENERATOR_AVAILABLE:
        raise HTTPException(status_code=503, detail="Report generator service unavailable")

    bot_lower = _validate_bot(bot)

    if date:
        report_date = _parse_date(date)
        # Don't allow future dates
        if report_date > datetime.now(CENTRAL_TZ).date():
            raise HTTPException(status_code=400, detail="Cannot generate report for future date")
    else:
        report_date = datetime.now(CENTRAL_TZ).date()

    try:
        import time
        start = time.time()

        report = generate_report_for_bot(bot_lower, report_date)

        elapsed = int((time.time() - start) * 1000)

        if report is None:
            return {
                "success": True,
                "data": None,
                "generated": False,
                "generation_time_ms": elapsed,
                "message": f"No trades for {bot.upper()} on {report_date} - no report generated"
            }

        return {
            "success": True,
            "data": report,
            "generated": True,
            "generation_time_ms": elapsed,
            "message": f"Report generated for {bot.upper()} on {report_date}"
        }
    except Exception as e:
        logger.error(f"Error generating report for {bot}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# DOWNLOAD ENDPOINTS
# =============================================================================

@router.get("/{bot}/reports/download/{date}")
async def download_report(
    bot: str,
    date: str,
    format: str = Query("json", description="Download format: json or pdf")
):
    """
    Download a report in specified format.

    Args:
        bot: Bot name
        date: Date (YYYY-MM-DD)
        format: 'json' for ML training, 'pdf' for PDF-friendly markdown

    Returns:
        File download response
    """
    if not GENERATOR_AVAILABLE:
        raise HTTPException(status_code=503, detail="Report generator service unavailable")

    bot_lower = _validate_bot(bot)
    report_date = _parse_date(date)

    # Get report from archive
    report = get_report_from_archive(bot_lower, report_date)
    if not report:
        raise HTTPException(status_code=404, detail=f"No report found for {date}")

    if format.lower() == "json":
        # JSON format for ML training
        content = json.dumps(report, indent=2, default=str)
        filename = f"{bot_lower}-report-{date}.json"

        return Response(
            content=content,
            media_type="application/json",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            }
        )

    elif format.lower() in ["pdf", "markdown", "md"]:
        # PDF-friendly markdown format
        markdown = _generate_markdown_report(report, bot_lower)
        filename = f"{bot_lower}-report-{date}.md"

        return Response(
            content=markdown,
            media_type="text/markdown",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            }
        )

    else:
        raise HTTPException(status_code=400, detail="Invalid format. Use 'json' or 'pdf'")


@router.get("/{bot}/reports/download-all")
async def download_all_reports(
    bot: str,
    format: str = Query("json", description="Download format: json"),
    limit: int = Query(1000, ge=1, le=10000, description="Max reports to download")
):
    """
    Download all reports for a bot.

    Uses bulk fetch (single query) instead of N+1 queries for performance.

    Args:
        bot: Bot name
        format: 'json' for ML training data
        limit: Max reports to fetch (default 1000, max 10000)

    Returns:
        File download with all reports
    """
    if not GENERATOR_AVAILABLE:
        raise HTTPException(status_code=503, detail="Report generator service unavailable")

    bot_lower = _validate_bot(bot)

    try:
        # Use bulk fetch - single query instead of N+1
        full_reports = get_reports_bulk(bot_lower, limit=limit)

        if format.lower() == "json":
            content = json.dumps({
                "bot": bot_lower.upper(),
                "total_reports": len(full_reports),
                "exported_at": datetime.now(CENTRAL_TZ).isoformat(),
                "reports": full_reports
            }, indent=2, default=str)

            filename = f"{bot_lower}-reports-all.json"

            return Response(
                content=content,
                media_type="application/json",
                headers={
                    "Content-Disposition": f'attachment; filename="{filename}"'
                }
            )
        else:
            raise HTTPException(status_code=400, detail="Only 'json' format supported for bulk download")

    except Exception as e:
        logger.error(f"Error downloading all reports: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# COST TRACKING
# =============================================================================

@router.get("/reports/costs")
async def get_all_reports_costs():
    """
    Get aggregate cost data for all bot reports.

    Returns:
        Cost breakdown by bot and total across all bots
    """
    if not GENERATOR_AVAILABLE:
        raise HTTPException(status_code=503, detail="Report generator service unavailable")

    try:
        costs_by_bot = {}
        totals = {
            "total_reports": 0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_tokens": 0,
            "total_cost_usd": 0
        }

        for bot in VALID_BOTS:
            stats = get_archive_stats(bot)
            bot_costs = {
                "total_reports": stats.get("total_reports", 0),
                "total_input_tokens": stats.get("total_input_tokens", 0),
                "total_output_tokens": stats.get("total_output_tokens", 0),
                "total_tokens": stats.get("total_tokens", 0),
                "total_cost_usd": stats.get("total_cost_usd", 0)
            }
            costs_by_bot[bot.upper()] = bot_costs

            # Aggregate totals
            for key in totals:
                totals[key] += bot_costs.get(key, 0)

        return {
            "success": True,
            "data": {
                "by_bot": costs_by_bot,
                "totals": totals
            }
        }
    except Exception as e:
        logger.error(f"Error getting report costs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# ADMIN - PURGE OLD REPORTS
# =============================================================================

@router.post("/reports/admin/purge")
async def purge_old_reports_endpoint(
    days_to_keep: int = Query(5 * 365, description="Days of reports to keep (default: 5 years)")
):
    """
    Purge reports older than specified days.

    This is an admin endpoint typically called by the scheduler.

    Args:
        days_to_keep: Number of days to keep (default 5 years)

    Returns:
        Number of reports purged per bot
    """
    if not GENERATOR_AVAILABLE:
        raise HTTPException(status_code=503, detail="Report generator service unavailable")

    try:
        results = purge_old_reports(days_to_keep)
        total_purged = sum(results.values())

        return {
            "success": True,
            "data": {
                "purged_by_bot": results,
                "total_purged": total_purged,
                "cutoff_date": (datetime.now() - timedelta(days=days_to_keep)).date().isoformat()
            },
            "message": f"Purged {total_purged} old reports"
        }
    except Exception as e:
        logger.error(f"Error purging reports: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _generate_markdown_report(report: dict, bot: str) -> str:
    """
    Generate PDF-friendly markdown from a report.

    Args:
        report: Report dict
        bot: Bot name

    Returns:
        Markdown string
    """
    md = []

    # Header
    md.append(f"# {bot.upper()} Daily Report")
    md.append(f"**Date:** {report.get('report_date', 'Unknown')}")
    md.append(f"**Generated:** {report.get('generated_at', 'Unknown')}")
    md.append("")

    # Summary Stats
    md.append("## Summary")
    md.append("")
    md.append(f"| Metric | Value |")
    md.append(f"|--------|-------|")
    md.append(f"| Total P&L | ${report.get('total_pnl', 0):,.2f} |")
    md.append(f"| Trade Count | {report.get('trade_count', 0)} |")
    md.append(f"| Wins | {report.get('win_count', 0)} |")
    md.append(f"| Losses | {report.get('loss_count', 0)} |")

    win_count = report.get('win_count', 0)
    trade_count = report.get('trade_count', 0)
    win_rate = (win_count / trade_count * 100) if trade_count > 0 else 0
    md.append(f"| Win Rate | {win_rate:.1f}% |")
    md.append("")

    # Daily Summary
    md.append("## Daily Summary")
    md.append("")
    md.append(report.get('daily_summary', 'No summary available.'))
    md.append("")

    # Lessons Learned
    lessons = report.get('lessons_learned', [])
    if lessons:
        md.append("## Lessons Learned")
        md.append("")
        for lesson in lessons:
            md.append(f"- {lesson}")
        md.append("")

    # Trade-by-Trade Analysis
    trade_analyses = report.get('trade_analyses', [])
    if trade_analyses:
        md.append("## Trade Analysis")
        md.append("")

        for i, analysis in enumerate(trade_analyses, 1):
            position_id = analysis.get('position_id', f'Trade {i}')
            pnl = analysis.get('pnl', 0)
            pnl_sign = '+' if pnl >= 0 else ''

            md.append(f"### Trade #{i}: {position_id}")
            md.append(f"**P&L:** {pnl_sign}${pnl:,.2f}")
            md.append("")

            # Entry Analysis
            entry = analysis.get('entry_analysis', {})
            if entry:
                md.append(f"**Entry Quality:** {entry.get('quality', 'N/A')}")
                md.append(f"> {entry.get('reasoning', 'No analysis available.')}")
                md.append("")

            # Price Action
            price_action = analysis.get('price_action_summary', '')
            if price_action:
                md.append(f"**Price Action:** {price_action}")
                md.append("")

            # Exit Analysis
            exit_analysis = analysis.get('exit_analysis', {})
            if exit_analysis:
                optimal = "Yes" if exit_analysis.get('was_optimal') else "No"
                md.append(f"**Optimal Exit:** {optimal}")
                md.append(f"> {exit_analysis.get('reasoning', 'No analysis available.')}")
                md.append("")

            # Why Won/Lost
            why = analysis.get('why_won_or_lost', '')
            if why:
                md.append(f"**Why:** {why}")
                md.append("")

            # Lesson
            lesson = analysis.get('lesson', '')
            if lesson:
                md.append(f"**Lesson:** {lesson}")
                md.append("")

            md.append("---")
            md.append("")

    # Market Context
    market_ctx = report.get('market_context', {})
    if market_ctx:
        summary = market_ctx.get('summary', {})
        md.append("## Market Context")
        md.append("")
        md.append(f"| Metric | Value |")
        md.append(f"|--------|-------|")
        if summary.get('vix_open'):
            md.append(f"| VIX Open | {summary.get('vix_open', 'N/A')} |")
        if summary.get('vix_close'):
            md.append(f"| VIX Close | {summary.get('vix_close', 'N/A')} |")
        if summary.get('vix_high'):
            md.append(f"| VIX High | {summary.get('vix_high', 'N/A')} |")
        if summary.get('vix_low'):
            md.append(f"| VIX Low | {summary.get('vix_low', 'N/A')} |")
        if summary.get('dominant_regime'):
            md.append(f"| Dominant Regime | {summary.get('dominant_regime', 'N/A')} |")
        md.append("")

        events = market_ctx.get('events', [])
        if events:
            md.append("**Events:** " + ", ".join(e.get('type', '') for e in events))
            md.append("")

    # Footer
    md.append("---")
    md.append(f"*Report generated by AlphaGEX {bot.upper()} using {report.get('generation_model', 'unknown')} in {report.get('generation_duration_ms', 0)}ms*")

    return "\n".join(md)
