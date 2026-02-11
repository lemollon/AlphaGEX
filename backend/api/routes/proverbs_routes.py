"""
PROVERBS Dashboard API Routes
=============================

API endpoints for the Proverbs Feedback Loop Intelligence System.
Provides dashboard, audit logs, proposal management, version control, and rollback.

All endpoints require the Proverbs system to be available.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query, Body
from pydantic import BaseModel, Field
from zoneinfo import ZoneInfo

router = APIRouter(prefix="/api/proverbs", tags=["Proverbs"])
logger = logging.getLogger(__name__)

# Try to import Proverbs
PROVERBS_AVAILABLE = False
proverbs_instance = None

try:
    from quant.proverbs_feedback_loop import (
        get_proverbs, run_feedback_loop, approve_proposal, reject_proposal,
        rollback_bot, kill_bot, resume_bot, get_dashboard,
        BotName, ActionType, ProposalType, ProposalStatus
    )
    PROVERBS_AVAILABLE = True
    logger.info("Proverbs feedback loop system loaded")
except ImportError as e:
    logger.warning(f"Proverbs not available: {e}")


CENTRAL_TZ = ZoneInfo("America/Chicago")


# =============================================================================
# REQUEST/RESPONSE MODELS
# =============================================================================

class ApprovalRequest(BaseModel):
    """Request to approve a proposal"""
    reviewer: str = Field(..., description="Username of the reviewer")
    notes: str = Field("", description="Optional review notes")


class RejectionRequest(BaseModel):
    """Request to reject a proposal"""
    reviewer: str = Field(..., description="Username of the reviewer")
    notes: str = Field(..., description="Reason for rejection")


class RollbackRequest(BaseModel):
    """Request to rollback to a previous version"""
    to_version_id: str = Field(..., description="Version ID to rollback to")
    reason: str = Field(..., description="Reason for rollback")
    user: str = Field(..., description="Username performing rollback")


class KillSwitchRequest(BaseModel):
    """Request to activate kill switch"""
    reason: str = Field(..., description="Reason for killing the bot")
    user: str = Field(..., description="Username activating kill switch")


class ResumeRequest(BaseModel):
    """Request to resume a killed bot"""
    user: str = Field(..., description="Username resuming the bot")


class ProposalCreateRequest(BaseModel):
    """Request to create a new proposal"""
    bot_name: str = Field(..., description="Bot name (FORTRESS, SOLOMON, ANCHOR, LAZARUS)")
    proposal_type: str = Field(..., description="Type of proposal (MODEL_UPDATE, PARAMETER_CHANGE, etc.)")
    title: str = Field(..., description="Short title for the proposal")
    description: str = Field(..., description="Detailed description")
    current_value: dict = Field(..., description="Current configuration/value")
    proposed_value: dict = Field(..., description="Proposed new configuration/value")
    reason: str = Field(..., description="Why this change is needed")
    risk_level: str = Field("MEDIUM", description="Risk level (LOW, MEDIUM, HIGH)")
    risk_factors: List[str] = Field([], description="List of risk factors")
    rollback_plan: str = Field("", description="Plan for rollback if needed")


# =============================================================================
# HEALTH AND STATUS
# =============================================================================

@router.get("/health")
async def proverbs_health():
    """
    Check Proverbs system health.

    Returns availability status and basic metrics.
    """
    if not PROVERBS_AVAILABLE:
        return {
            "status": "unavailable",
            "message": "Proverbs feedback loop system not loaded",
            "timestamp": datetime.now(CENTRAL_TZ).isoformat()
        }

    try:
        proverbs = get_proverbs()
        health = proverbs._get_system_health()

        return {
            "status": "healthy",
            "session_id": proverbs.session_id,
            "database_connected": health.get('database', False),
            "oracle_connected": health.get('prophet', False),
            "last_feedback_run": health.get('last_feedback_run'),
            "pending_proposals": health.get('pending_proposals_count', 0),
            "degradation_alerts_24h": health.get('degradation_alerts', 0),
            "timestamp": datetime.now(CENTRAL_TZ).isoformat()
        }
    except Exception as e:
        logger.error(f"Proverbs health check failed: {e}")
        return {
            "status": "error",
            "message": str(e),
            "timestamp": datetime.now(CENTRAL_TZ).isoformat()
        }


# =============================================================================
# DASHBOARD
# =============================================================================

@router.get("/dashboard")
async def get_proverbs_dashboard():
    """
    Get comprehensive Proverbs dashboard data.

    Returns:
    - Bot statuses (performance, versions, kill switch)
    - Pending proposals
    - Recent actions (audit log)
    - System health
    """
    if not PROVERBS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Proverbs system not available")

    try:
        return get_dashboard()
    except Exception as e:
        logger.error(f"Failed to get dashboard: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dashboard/bot/{bot_name}")
async def get_bot_dashboard(bot_name: str):
    """
    Get detailed dashboard for a specific bot.
    """
    if not PROVERBS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Proverbs system not available")

    bot_name = bot_name.upper()
    if bot_name not in ['FORTRESS', 'SOLOMON', 'GIDEON', 'ANCHOR', 'SAMSON', 'VALOR', 'LAZARUS']:
        raise HTTPException(status_code=400, detail=f"Invalid bot name: {bot_name}")

    try:
        proverbs = get_proverbs()

        return {
            "bot_name": bot_name,
            "is_killed": proverbs.is_bot_killed(bot_name),
            "performance": proverbs._get_current_performance(bot_name),
            "performance_history": proverbs.get_performance_history(bot_name, days=30),
            "active_version": proverbs._get_active_version_info(bot_name),
            "version_history": proverbs.get_version_history(bot_name, limit=10),
            "recent_actions": proverbs.get_audit_log(bot_name=bot_name, limit=20),
            "rollback_history": proverbs.get_rollback_history(bot_name=bot_name, limit=5),
            "timestamp": datetime.now(CENTRAL_TZ).isoformat()
        }
    except Exception as e:
        logger.error(f"Failed to get bot dashboard: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# AUDIT LOG
# =============================================================================

@router.get("/audit")
async def get_audit_log(
    bot_name: Optional[str] = Query(None, description="Filter by bot name"),
    action_type: Optional[str] = Query(None, description="Filter by action type"),
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    limit: int = Query(100, ge=1, le=500, description="Number of entries to return")
):
    """
    Get audit log entries with filtering.

    The audit log contains WHO, WHAT, WHY, WHEN for every action.
    """
    if not PROVERBS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Proverbs system not available")

    try:
        proverbs = get_proverbs()

        try:
            start = datetime.fromisoformat(start_date) if start_date else None
            end = datetime.fromisoformat(end_date) if end_date else None
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")

        logs = proverbs.get_audit_log(
            bot_name=bot_name.upper() if bot_name else None,
            action_type=action_type,
            start_date=start,
            end_date=end,
            limit=limit
        )

        return {
            "count": len(logs),
            "filters": {
                "bot_name": bot_name,
                "action_type": action_type,
                "start_date": start_date,
                "end_date": end_date
            },
            "entries": logs
        }
    except Exception as e:
        logger.error(f"Failed to get audit log: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/audit/action-types")
async def get_action_types():
    """Get all available action types for filtering."""
    if not PROVERBS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Proverbs system not available")

    return {
        "action_types": [at.value for at in ActionType]
    }


# =============================================================================
# PROPOSALS
# =============================================================================

@router.get("/proposals")
async def get_proposals(
    status: Optional[str] = Query(None, description="Filter by status (PENDING, APPROVED, REJECTED, etc.)"),
    bot_name: Optional[str] = Query(None, description="Filter by bot name"),
    limit: int = Query(50, ge=1, le=200, description="Number of proposals to return")
):
    """
    Get proposals with filtering.

    By default returns pending proposals.
    """
    if not PROVERBS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Proverbs system not available")

    try:
        from database_adapter import get_connection

        conn = get_connection()
        try:
            cursor = conn.cursor()

            query = "SELECT * FROM proverbs_proposals WHERE 1=1"
            params = []

            if status:
                query += " AND status = %s"
                params.append(status.upper())

            if bot_name:
                query += " AND bot_name = %s"
                params.append(bot_name.upper())

            query += " ORDER BY created_at DESC LIMIT %s"
            params.append(limit)

            cursor.execute(query, params)
            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()
        finally:
            conn.close()

        proposals = [dict(zip(columns, row)) for row in rows]

        return {
            "count": len(proposals),
            "filters": {"status": status, "bot_name": bot_name},
            "proposals": proposals
        }
    except Exception as e:
        logger.error(f"Failed to get proposals: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/proposals/pending")
async def get_pending_proposals(
    bot_name: Optional[str] = Query(None, description="Filter by bot name")
):
    """
    Get all pending proposals awaiting approval.
    """
    if not PROVERBS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Proverbs system not available")

    try:
        proverbs = get_proverbs()
        proposals = proverbs.get_pending_proposals(bot_name=bot_name.upper() if bot_name else None)

        return {
            "count": len(proposals),
            "proposals": proposals
        }
    except Exception as e:
        logger.error(f"Failed to get pending proposals: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/proposals/{proposal_id}")
async def get_proposal(proposal_id: str):
    """
    Get a specific proposal by ID.
    """
    if not PROVERBS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Proverbs system not available")

    try:
        from database_adapter import get_connection

        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM proverbs_proposals WHERE proposal_id = %s", (proposal_id,))
            columns = [desc[0] for desc in cursor.description]
            row = cursor.fetchone()
        finally:
            conn.close()

        if not row:
            raise HTTPException(status_code=404, detail=f"Proposal {proposal_id} not found")

        return dict(zip(columns, row))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get proposal: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/proposals")
async def create_proposal(request: ProposalCreateRequest):
    """
    Create a new proposal for review.

    Proposals must be approved before changes are applied.
    """
    if not PROVERBS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Proverbs system not available")

    try:
        proverbs = get_proverbs()

        proposal_type = ProposalType[request.proposal_type.upper()]

        proposal_id = proverbs.create_proposal(
            bot_name=request.bot_name.upper(),
            proposal_type=proposal_type,
            title=request.title,
            description=request.description,
            current_value=request.current_value,
            proposed_value=request.proposed_value,
            reason=request.reason,
            supporting_metrics={},
            expected_improvement={},
            risk_level=request.risk_level.upper(),
            risk_factors=request.risk_factors,
            rollback_plan=request.rollback_plan
        )

        if not proposal_id:
            raise HTTPException(status_code=500, detail="Failed to create proposal")

        return {
            "success": True,
            "proposal_id": proposal_id,
            "message": f"Proposal created successfully. Awaiting approval."
        }
    except KeyError as e:
        raise HTTPException(status_code=400, detail=f"Invalid proposal type: {request.proposal_type}")
    except Exception as e:
        logger.error(f"Failed to create proposal: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/proposals/{proposal_id}/approve")
async def approve_proposal_endpoint(proposal_id: str, request: ApprovalRequest):
    """
    Approve a pending proposal.

    This will apply the proposed changes.
    """
    if not PROVERBS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Proverbs system not available")

    try:
        success = approve_proposal(proposal_id, request.reviewer, request.notes)

        if not success:
            raise HTTPException(status_code=400, detail="Failed to approve proposal. It may not be pending or may not exist.")

        return {
            "success": True,
            "proposal_id": proposal_id,
            "approved_by": request.reviewer,
            "message": "Proposal approved and changes applied"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to approve proposal: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/proposals/{proposal_id}/reject")
async def reject_proposal_endpoint(proposal_id: str, request: RejectionRequest):
    """
    Reject a pending proposal.
    """
    if not PROVERBS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Proverbs system not available")

    try:
        success = reject_proposal(proposal_id, request.reviewer, request.notes)

        if not success:
            raise HTTPException(status_code=400, detail="Failed to reject proposal")

        return {
            "success": True,
            "proposal_id": proposal_id,
            "rejected_by": request.reviewer,
            "message": "Proposal rejected"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to reject proposal: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# VERSIONS
# =============================================================================

@router.get("/versions/{bot_name}")
async def get_versions(
    bot_name: str,
    artifact_name: Optional[str] = Query(None, description="Filter by artifact name"),
    limit: int = Query(20, ge=1, le=100, description="Number of versions to return")
):
    """
    Get version history for a bot.
    """
    if not PROVERBS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Proverbs system not available")

    try:
        proverbs = get_proverbs()
        versions = proverbs.get_version_history(
            bot_name=bot_name.upper(),
            artifact_name=artifact_name,
            limit=limit
        )

        return {
            "bot_name": bot_name.upper(),
            "count": len(versions),
            "versions": versions
        }
    except Exception as e:
        logger.error(f"Failed to get versions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/versions/{version_id}/activate")
async def activate_version(version_id: str, user: str = Query(..., description="Username activating version")):
    """
    Activate a specific version.

    Deactivates the current active version.
    """
    if not PROVERBS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Proverbs system not available")

    try:
        proverbs = get_proverbs()
        success = proverbs.activate_version(version_id, f"USER:{user}")

        if not success:
            raise HTTPException(status_code=400, detail="Failed to activate version")

        return {
            "success": True,
            "version_id": version_id,
            "activated_by": user,
            "message": "Version activated"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to activate version: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# ROLLBACK
# =============================================================================

@router.get("/rollbacks")
async def get_rollback_history(
    bot_name: Optional[str] = Query(None, description="Filter by bot name"),
    limit: int = Query(20, ge=1, le=100, description="Number of rollbacks to return")
):
    """
    Get rollback history.
    """
    if not PROVERBS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Proverbs system not available")

    try:
        proverbs = get_proverbs()
        rollbacks = proverbs.get_rollback_history(
            bot_name=bot_name.upper() if bot_name else None,
            limit=limit
        )

        return {
            "count": len(rollbacks),
            "rollbacks": rollbacks
        }
    except Exception as e:
        logger.error(f"Failed to get rollback history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/rollback/{bot_name}")
async def rollback_bot_endpoint(bot_name: str, request: RollbackRequest):
    """
    Rollback a bot to a previous version.
    """
    if not PROVERBS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Proverbs system not available")

    try:
        success = rollback_bot(
            bot_name=bot_name.upper(),
            to_version_id=request.to_version_id,
            reason=request.reason,
            user=request.user
        )

        if not success:
            raise HTTPException(status_code=400, detail="Failed to rollback")

        return {
            "success": True,
            "bot_name": bot_name.upper(),
            "to_version_id": request.to_version_id,
            "rolled_back_by": request.user,
            "message": "Rollback completed successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to rollback: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# KILL SWITCH
# =============================================================================

@router.get("/killswitch")
async def get_kill_switch_status():
    """
    Get kill switch status for all bots.
    """
    if not PROVERBS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Proverbs system not available")

    try:
        proverbs = get_proverbs()
        status = proverbs.get_kill_switch_status()

        # Add bots not yet in the table
        for bot in ['FORTRESS', 'SOLOMON', 'GIDEON', 'ANCHOR', 'SAMSON', 'VALOR', 'LAZARUS']:
            if bot not in status:
                status[bot] = {
                    'bot_name': bot,
                    'is_killed': False,
                    'killed_at': None,
                    'killed_by': None,
                    'kill_reason': None
                }

        return {
            "status": status,
            "timestamp": datetime.now(CENTRAL_TZ).isoformat()
        }
    except Exception as e:
        logger.error(f"Failed to get kill switch status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/killswitch/{bot_name}/activate")
async def activate_kill_switch(bot_name: str, request: KillSwitchRequest):
    """
    Activate kill switch for a bot.

    Immediately stops all trading for the specified bot.
    """
    if not PROVERBS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Proverbs system not available")

    try:
        success = kill_bot(bot_name.upper(), request.reason, request.user)

        if not success:
            raise HTTPException(status_code=400, detail="Failed to activate kill switch")

        return {
            "success": True,
            "bot_name": bot_name.upper(),
            "killed_by": request.user,
            "reason": request.reason,
            "message": f"Kill switch activated for {bot_name.upper()}. All trading stopped."
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to activate kill switch: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/killswitch/{bot_name}/deactivate")
async def deactivate_kill_switch(bot_name: str, request: ResumeRequest):
    """
    Deactivate kill switch for a bot.

    Allows the bot to resume trading.
    """
    if not PROVERBS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Proverbs system not available")

    try:
        success = resume_bot(bot_name.upper(), request.user)

        if not success:
            raise HTTPException(status_code=400, detail="Failed to deactivate kill switch")

        return {
            "success": True,
            "bot_name": bot_name.upper(),
            "resumed_by": request.user,
            "message": f"Kill switch deactivated for {bot_name.upper()}. Trading can resume."
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to deactivate kill switch: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/killswitch/clear-all")
async def clear_all_kill_switches():
    """
    Clear all kill switch records from the database.

    This completely removes all killswitch entries, allowing all bots to trade.
    """
    try:
        from database_adapter import get_connection
        conn = get_connection()
        try:
            cursor = conn.cursor()

            # Clear all killswitch records
            cursor.execute("DELETE FROM proverbs_kill_switch")
            deleted_count = cursor.rowcount

            conn.commit()
        finally:
            conn.close()

        return {
            "success": True,
            "message": f"Cleared {deleted_count} kill switch records. All bots can now trade.",
            "deleted_count": deleted_count
        }
    except Exception as e:
        logger.error(f"Failed to clear kill switches: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# FEEDBACK LOOP CONTROL
# =============================================================================

@router.post("/feedback-loop/run")
async def trigger_feedback_loop():
    """
    Manually trigger a feedback loop run.

    This will:
    1. Check each bot's performance
    2. Detect degradation
    3. Create proposals for improvements
    4. Record performance snapshots
    """
    if not PROVERBS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Proverbs system not available")

    try:
        result = run_feedback_loop()

        return {
            "success": result.success,
            "run_id": result.run_id,
            "started_at": result.started_at.isoformat(),
            "completed_at": result.completed_at.isoformat(),
            "duration_seconds": (result.completed_at - result.started_at).total_seconds(),
            "bots_checked": result.bots_checked,
            "outcomes_processed": result.outcomes_processed,
            "proposals_created": result.proposals_created,
            "alerts_raised": result.alerts_raised,
            "errors": result.errors
        }
    except Exception as e:
        logger.error(f"Failed to run feedback loop: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/feedback-loop/status")
async def get_feedback_loop_status():
    """
    Get the current status of the feedback loop.
    """
    if not PROVERBS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Proverbs system not available")

    try:
        proverbs = get_proverbs()

        # Get last run info
        runs = proverbs.get_audit_log(
            action_type="FEEDBACK_LOOP_RUN",
            limit=5
        )

        # Pull guardrails from the actual GUARDRAILS config rather than hardcoding
        try:
            from quant.proverbs_feedback_loop import GUARDRAILS
            guardrail_config = dict(GUARDRAILS)
        except (ImportError, AttributeError):
            guardrail_config = {
                'min_sample_size': 50,
                'max_parameter_change_pct': 20,
                'degradation_threshold': 15,
                'rollback_on_drawdown_pct': 10,
                'proposal_expiry_hours': 72
            }

        return {
            "session_id": proverbs.session_id,
            "recent_runs": runs,
            "guardrails": guardrail_config,
            "timestamp": datetime.now(CENTRAL_TZ).isoformat()
        }
    except Exception as e:
        logger.error(f"Failed to get feedback loop status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# PERFORMANCE
# =============================================================================

@router.get("/performance/{bot_name}")
async def get_bot_performance(
    bot_name: str,
    days: int = Query(30, ge=1, le=365, description="Number of days of history")
):
    """
    Get performance history for a bot.
    """
    if not PROVERBS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Proverbs system not available")

    try:
        proverbs = get_proverbs()

        current = proverbs._get_current_performance(bot_name.upper())
        history = proverbs.get_performance_history(bot_name.upper(), days=days)
        degradation = proverbs.detect_degradation(bot_name.upper())

        return {
            "bot_name": bot_name.upper(),
            "current": current,
            "history": history,
            "degradation_alert": degradation,
            "timestamp": datetime.now(CENTRAL_TZ).isoformat()
        }
    except Exception as e:
        logger.error(f"Failed to get performance: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/performance/{bot_name}/snapshot")
async def record_performance_snapshot(bot_name: str):
    """
    Record a performance snapshot for a bot.
    """
    if not PROVERBS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Proverbs system not available")

    try:
        proverbs = get_proverbs()
        snapshot_id = proverbs.record_performance_snapshot(bot_name.upper())

        if not snapshot_id:
            raise HTTPException(status_code=400, detail="Failed to record snapshot - no performance data available")

        return {
            "success": True,
            "snapshot_id": snapshot_id,
            "bot_name": bot_name.upper(),
            "message": "Performance snapshot recorded"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to record snapshot: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# ENHANCED FEATURES
# =============================================================================

# Try to import enhanced Proverbs features
ENHANCED_AVAILABLE = False
try:
    from quant.proverbs_enhancements import get_proverbs_enhanced
    ENHANCED_AVAILABLE = True
    logger.info("Proverbs enhanced features loaded")
except ImportError as e:
    logger.warning(f"Proverbs enhanced features not available: {e}")


@router.get("/realtime-status")
async def get_realtime_status(
    days: int = Query(7, ge=1, le=30, description="Number of days for recent analysis")
):
    """
    Get real-time Proverbs monitoring status with actual trade data.

    This endpoint provides visibility into what Proverbs is actively monitoring,
    derived directly from each bot's positions table (fortress_positions, samson_positions, etc.)
    rather than summary tables.

    Returns per-bot:
    - Recent trade count and P&L
    - Win/loss streak status
    - Daily P&L status
    - Trend indicators
    """
    try:
        from database_adapter import get_connection

        conn = get_connection()
        try:
            cursor = conn.cursor()

            # Bot tables mapping - query actual position tables
            BOT_TABLES = {
                'FORTRESS': 'fortress_positions',
                'SOLOMON': 'solomon_positions',
                'SAMSON': 'samson_positions',
                'ANCHOR': 'anchor_positions',
                'GIDEON': 'gideon_positions',
                'VALOR': 'valor_positions',
                'JUBILEE': 'jubilee_ic_positions',
            }

            days_interval = f'{days} days'

            # Collect performance from each bot's actual table
            bot_rows = []
            today_by_bot = {}
            streak_rows = []

            for bot_name, table_name in BOT_TABLES.items():
                try:
                    # Get recent trade performance for this bot
                    # Cast to timestamptz to handle FORTRESS TEXT columns and other bots' timestamp columns
                    cursor.execute(f"""
                        SELECT
                            COUNT(*) as total_trades,
                            SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
                            SUM(CASE WHEN realized_pnl < 0 THEN 1 ELSE 0 END) as losses,
                            COALESCE(SUM(realized_pnl), 0) as total_pnl,
                            COALESCE(AVG(realized_pnl), 0) as avg_pnl,
                            MAX(close_time::timestamptz) as last_trade_time
                        FROM {table_name}
                        WHERE status = 'closed'
                          AND close_time::timestamptz >= NOW() - INTERVAL %s
                    """, (days_interval,))
                    row = cursor.fetchone()
                    if row and row[0] > 0:
                        bot_rows.append((bot_name, row[0], row[1], row[2], row[3], row[4], row[5]))

                    # Get today's performance for this bot
                    # Cast to timestamptz to handle FORTRESS TEXT columns
                    cursor.execute(f"""
                        SELECT
                            COUNT(*) as today_trades,
                            COALESCE(SUM(realized_pnl), 0) as today_pnl
                        FROM {table_name}
                        WHERE status = 'closed'
                          AND DATE(close_time::timestamptz AT TIME ZONE 'America/Chicago') = CURRENT_DATE
                    """)
                    today_row = cursor.fetchone()
                    if today_row and today_row[0] > 0:
                        today_by_bot[bot_name] = {'trades': today_row[0], 'pnl': float(today_row[1] or 0)}

                    # Get last 10 trades for streak calculation
                    # Cast to timestamptz to handle FORTRESS TEXT columns
                    cursor.execute(f"""
                        SELECT realized_pnl
                        FROM {table_name}
                        WHERE status = 'closed'
                          AND close_time::timestamptz >= NOW() - INTERVAL %s
                        ORDER BY close_time::timestamptz DESC
                        LIMIT 10
                    """, (days_interval,))
                    trades = cursor.fetchall()
                    for trade in trades:
                        streak_rows.append((bot_name, trade[0]))

                except Exception as table_err:
                    logger.warning(f"Could not query {table_name} ({type(table_err).__name__}): {table_err}")
                    continue
        finally:
            conn.close()

        # Calculate streaks
        bot_streaks = {}
        for row in streak_rows:
            bot_name, pnl = row
            if bot_name not in bot_streaks:
                bot_streaks[bot_name] = []
            bot_streaks[bot_name].append(pnl)

        def calculate_streak(pnls):
            if not pnls:
                return {'current_streak': 0, 'streak_type': 'none'}
            streak = 0
            streak_type = 'win' if pnls[0] > 0 else 'loss'
            for pnl in pnls:
                if (pnl > 0 and streak_type == 'win') or (pnl < 0 and streak_type == 'loss'):
                    streak += 1
                else:
                    break
            return {'current_streak': streak, 'streak_type': streak_type}

        # Build bot status
        bots = {}
        ic_bots = ['FORTRESS', 'SAMSON', 'ANCHOR', 'JUBILEE']
        dir_bots = ['SOLOMON', 'GIDEON']

        for row in bot_rows:
            bot_name, total_trades, wins, losses, total_pnl, avg_pnl, last_trade = row
            streak_info = calculate_streak(bot_streaks.get(bot_name, []))
            today_info = today_by_bot.get(bot_name, {'trades': 0, 'pnl': 0})

            bots[bot_name] = {
                'strategy_type': 'IRON_CONDOR' if bot_name in ic_bots else 'DIRECTIONAL',
                'period_days': days,
                'total_trades': total_trades or 0,
                'wins': wins or 0,
                'losses': losses or 0,
                'win_rate': (wins / total_trades * 100) if total_trades else 0,
                'total_pnl': float(total_pnl or 0),
                'avg_pnl': float(avg_pnl or 0),
                'last_trade': last_trade.isoformat() if last_trade else None,
                'current_streak': streak_info['current_streak'],
                'streak_type': streak_info['streak_type'],
                'today_trades': today_info['trades'],
                'today_pnl': today_info['pnl'],
                'status': 'active' if total_trades > 0 else 'inactive'
            }

        # Calculate totals
        total_trades = sum(b['total_trades'] for b in bots.values())
        total_wins = sum(b['wins'] for b in bots.values())
        total_pnl = sum(b['total_pnl'] for b in bots.values())
        today_pnl = sum(b['today_pnl'] for b in bots.values())

        return {
            'success': True,
            'data_source': 'bot_positions_tables (real-time)',
            'period_days': days,
            'timestamp': datetime.now(CENTRAL_TZ).isoformat(),
            'bots': bots,
            'summary': {
                'total_trades': total_trades,
                'total_wins': total_wins,
                'overall_win_rate': (total_wins / total_trades * 100) if total_trades else 0,
                'total_pnl': total_pnl,
                'today_pnl': today_pnl,
                'active_bots': len([b for b in bots.values() if b['status'] == 'active'])
            },
            'alerts': [
                {'type': 'loss_streak', 'bot': bot, 'streak': bots[bot]['current_streak']}
                for bot in bots
                if bots[bot]['streak_type'] == 'loss' and bots[bot]['current_streak'] >= 3
            ]
        }

    except Exception as e:
        logger.error(f"Failed to get realtime status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/strategy-analysis")
async def get_strategy_analysis(
    days: int = Query(30, ge=1, le=365, description="Number of days to analyze")
):
    """
    Get strategy-level performance analysis (IC vs Directional).

    Migration 023: Compares Iron Condor strategy performance against
    Directional strategy performance across all bots.

    Returns:
    - Iron Condor metrics (FORTRESS, SAMSON, ANCHOR)
    - Directional metrics (SOLOMON, GIDEON)
    - Win rate comparison
    - Average P&L comparison
    - Strategy recommendation
    """
    if not ENHANCED_AVAILABLE:
        raise HTTPException(status_code=503, detail="Enhanced features not available")

    try:
        enhanced = get_proverbs_enhanced()
        analysis = enhanced.get_strategy_analysis(days=days)

        return {
            "success": True,
            **analysis
        }
    except Exception as e:
        logger.error(f"Failed to get strategy analysis: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/prophet-accuracy")
async def get_prophet_accuracy(
    days: int = Query(30, ge=1, le=365, description="Number of days to analyze")
):
    """
    Get Prophet advice accuracy analysis.

    Migration 023: Analyzes how well Prophet's recommendations correlate
    with actual trade outcomes.

    Returns:
    - Accuracy by advice type (TRADE_FULL, TRADE_REDUCED, SKIP_TODAY)
    - Accuracy by strategy (IC vs Directional)
    - Summary with overall accuracy
    """
    if not ENHANCED_AVAILABLE:
        raise HTTPException(status_code=503, detail="Enhanced features not available")

    try:
        enhanced = get_proverbs_enhanced()
        accuracy = enhanced.get_prophet_accuracy(days=days)

        return {
            "success": True,
            **accuracy
        }
    except Exception as e:
        logger.error(f"Failed to get prophet accuracy: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/enhanced/analysis/{bot_name}")
async def get_enhanced_analysis(
    bot_name: str,
    days: int = Query(30, ge=1, le=365, description="Number of days to analyze")
):
    """
    Get comprehensive enhanced analysis for a bot.

    Includes:
    - Consecutive loss tracking
    - Daily P&L status
    - Time of day performance
    - Regime performance
    - Version history comparison
    """
    if not ENHANCED_AVAILABLE:
        raise HTTPException(status_code=503, detail="Enhanced features not available")

    try:
        enhanced = get_proverbs_enhanced()
        analysis = enhanced.get_comprehensive_analysis(bot_name.upper())

        return {
            "success": True,
            **analysis
        }
    except Exception as e:
        logger.error(f"Failed to get enhanced analysis: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/enhanced/correlations")
async def get_cross_bot_correlations(
    days: int = Query(30, ge=7, le=365, description="Number of days to analyze")
):
    """
    Get cross-bot performance correlations.

    Analyzes how bot performances are correlated to assess diversification.
    """
    if not ENHANCED_AVAILABLE:
        raise HTTPException(status_code=503, detail="Enhanced features not available")

    try:
        enhanced = get_proverbs_enhanced()
        correlations = enhanced.get_portfolio_correlations()

        return {
            "success": True,
            "period_days": days,
            **correlations
        }
    except Exception as e:
        logger.error(f"Failed to get correlations: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/enhanced/time-analysis/{bot_name}")
async def get_time_of_day_analysis(
    bot_name: str,
    days: int = Query(30, ge=7, le=365, description="Number of days to analyze")
):
    """
    Get time-of-day performance analysis for a bot.

    Shows which hours have the best/worst performance.
    """
    if not ENHANCED_AVAILABLE:
        raise HTTPException(status_code=503, detail="Enhanced features not available")

    try:
        enhanced = get_proverbs_enhanced()
        analysis = enhanced.time_analyzer.analyze(bot_name.upper(), days)

        return {
            "success": True,
            "bot_name": bot_name.upper(),
            "period_days": days,
            "hourly_performance": [a.to_dict() for a in analysis]
        }
    except Exception as e:
        logger.error(f"Failed to get time analysis: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/enhanced/regime/{bot_name}")
async def get_regime_performance(
    bot_name: str,
    days: int = Query(90, ge=30, le=365, description="Number of days to analyze")
):
    """
    Get performance by market regime for a bot.

    Shows how the bot performs in different market conditions.
    """
    if not ENHANCED_AVAILABLE:
        raise HTTPException(status_code=503, detail="Enhanced features not available")

    try:
        enhanced = get_proverbs_enhanced()
        analysis = enhanced.regime_tracker.analyze_regime_performance(bot_name.upper(), days)

        return {
            "success": True,
            "bot_name": bot_name.upper(),
            "period_days": days,
            "regime_performance": [r.to_dict() for r in analysis]
        }
    except Exception as e:
        logger.error(f"Failed to get regime performance: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/enhanced/digest")
async def get_daily_digest(
    date: Optional[str] = Query(None, description="Date for digest (YYYY-MM-DD), defaults to today")
):
    """
    Get daily performance digest.

    Summary of all bot performance for the day.
    """
    if not ENHANCED_AVAILABLE:
        raise HTTPException(status_code=503, detail="Enhanced features not available")

    try:
        enhanced = get_proverbs_enhanced()
        digest = enhanced.daily_digest.generate_digest(date)

        return {
            "success": True,
            **digest
        }
    except Exception as e:
        logger.error(f"Failed to generate digest: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/enhanced/weekend-precheck")
async def get_weekend_precheck():
    """
    Get weekend pre-check analysis.

    Analysis for preparing bots for the upcoming trading week.
    """
    if not ENHANCED_AVAILABLE:
        raise HTTPException(status_code=503, detail="Enhanced features not available")

    try:
        enhanced = get_proverbs_enhanced()
        precheck = enhanced.weekend_precheck.generate_precheck()

        return {
            "success": True,
            **precheck.to_dict()
        }
    except Exception as e:
        logger.error(f"Failed to generate weekend precheck: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/enhanced/version-compare/{bot_name}")
async def compare_versions(
    bot_name: str,
    version_a: str = Query(..., description="First version ID"),
    version_b: str = Query(..., description="Second version ID")
):
    """
    Compare performance between two versions.
    """
    if not ENHANCED_AVAILABLE:
        raise HTTPException(status_code=503, detail="Enhanced features not available")

    try:
        enhanced = get_proverbs_enhanced()
        comparison = enhanced.version_comparer.compare_versions(
            bot_name.upper(), version_a, version_b
        )

        return {
            "success": True,
            "bot_name": bot_name.upper(),
            **comparison
        }
    except Exception as e:
        logger.error(f"Failed to compare versions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/enhanced/version-history/{bot_name}")
async def get_version_performance_history(
    bot_name: str,
    days: int = Query(30, ge=7, le=365, description="Number of days to analyze")
):
    """
    Get performance history grouped by version.
    """
    if not ENHANCED_AVAILABLE:
        raise HTTPException(status_code=503, detail="Enhanced features not available")

    try:
        enhanced = get_proverbs_enhanced()
        history = enhanced.version_comparer.get_version_performance_history(
            bot_name.upper(), days
        )

        return {
            "success": True,
            "bot_name": bot_name.upper(),
            "period_days": days,
            "versions": [v.to_dict() for v in history]
        }
    except Exception as e:
        logger.error(f"Failed to get version history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# A/B TESTING
# =============================================================================

class ABTestCreateRequest(BaseModel):
    """Request to create an A/B test"""
    bot_name: str = Field(..., description="Bot name")
    control_config: dict = Field(..., description="Control configuration")
    variant_config: dict = Field(..., description="Variant configuration")
    control_allocation: float = Field(0.5, ge=0.1, le=0.9, description="Allocation to control group")


@router.post("/enhanced/ab-test")
async def create_ab_test(request: ABTestCreateRequest):
    """
    Create a new A/B test for a bot.
    """
    if not ENHANCED_AVAILABLE:
        raise HTTPException(status_code=503, detail="Enhanced features not available")

    try:
        enhanced = get_proverbs_enhanced()
        test_id = enhanced.ab_testing.create_test(
            request.bot_name.upper(),
            request.control_config,
            request.variant_config,
            request.control_allocation
        )

        return {
            "success": True,
            "test_id": test_id,
            "message": "A/B test created"
        }
    except Exception as e:
        logger.error(f"Failed to create A/B test: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/enhanced/ab-test")
async def get_active_ab_tests(
    bot_name: Optional[str] = Query(None, description="Filter by bot name")
):
    """
    Get active A/B tests.
    """
    if not ENHANCED_AVAILABLE:
        raise HTTPException(status_code=503, detail="Enhanced features not available")

    try:
        enhanced = get_proverbs_enhanced()
        tests = enhanced.ab_testing.get_active_tests(bot_name.upper() if bot_name else None)

        return {
            "success": True,
            "tests": tests
        }
    except Exception as e:
        logger.error(f"Failed to get A/B tests: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/enhanced/ab-test/{test_id}/evaluate")
async def evaluate_ab_test(test_id: str):
    """
    Evaluate an A/B test's results.
    """
    if not ENHANCED_AVAILABLE:
        raise HTTPException(status_code=503, detail="Enhanced features not available")

    try:
        enhanced = get_proverbs_enhanced()
        result = enhanced.ab_testing.evaluate_test(test_id)

        return {
            "success": True,
            **result
        }
    except Exception as e:
        logger.error(f"Failed to evaluate A/B test: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# ROLLBACK COOLDOWN
# =============================================================================

@router.get("/enhanced/rollback-status/{bot_name}")
async def get_rollback_status(bot_name: str):
    """
    Check if a rollback is allowed for a bot.
    """
    if not ENHANCED_AVAILABLE:
        raise HTTPException(status_code=503, detail="Enhanced features not available")

    try:
        enhanced = get_proverbs_enhanced()
        can_rollback, message = enhanced.rollback_cooldown.can_rollback(bot_name.upper())

        return {
            "bot_name": bot_name.upper(),
            "can_rollback": can_rollback,
            "message": message
        }
    except Exception as e:
        logger.error(f"Failed to check rollback status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# AI ANALYSIS
# =============================================================================

AI_ANALYST_AVAILABLE = False
try:
    from quant.proverbs_ai_analyst import ProverbsAIAnalyst, get_analyst
    AI_ANALYST_AVAILABLE = True
    logger.info("Proverbs AI Analyst loaded")
except ImportError as e:
    logger.warning(f"Proverbs AI Analyst not available: {e}")


@router.get("/ai/analyze-performance/{bot_name}")
async def ai_analyze_performance(bot_name: str):
    """
    Get AI analysis of bot performance.

    Uses Claude to provide insights and recommendations.
    """
    if not PROVERBS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Proverbs system not available")
    if not AI_ANALYST_AVAILABLE:
        raise HTTPException(status_code=503, detail="AI Analyst not available")

    try:
        analyst = get_analyst()
        # Note: analyze_performance_drop is synchronous (calls Claude API internally)
        analysis = analyst.analyze_performance_drop(bot_name.upper(), [], {}, {})

        return {
            "success": True,
            "bot_name": bot_name.upper(),
            "analysis": analysis.to_dict() if analysis else None
        }
    except Exception as e:
        logger.error(f"Failed to get AI analysis: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ai/proposal-reasoning/{proposal_id}")
async def ai_proposal_reasoning(proposal_id: str):
    """
    Get AI-generated reasoning for a proposal.
    """
    if not AI_ANALYST_AVAILABLE:
        raise HTTPException(status_code=503, detail="AI Analyst not available")

    conn = None
    try:
        # Get proposal data
        from database_adapter import get_connection

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM proverbs_proposals WHERE proposal_id = %s", (proposal_id,))
        columns = [desc[0] for desc in cursor.description]
        row = cursor.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Proposal not found")

        proposal = dict(zip(columns, row))

        analyst = get_analyst()
        # Note: generate_proposal_reasoning is synchronous
        reasoning = analyst.generate_proposal_reasoning(
            bot_name=proposal.get('bot_name', 'UNKNOWN'),
            proposal_type=proposal.get('proposal_type', 'UNKNOWN'),
            current_value=proposal.get('current_value', {}),
            proposed_value=proposal.get('proposed_value', {}),
            supporting_metrics=proposal.get('supporting_metrics', {})
        )

        return {
            "success": True,
            "proposal_id": proposal_id,
            "reasoning": reasoning
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get AI reasoning: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            conn.close()


@router.get("/ai/weekend-analysis")
async def ai_weekend_analysis():
    """
    Get AI-generated weekend market analysis.
    """
    if not AI_ANALYST_AVAILABLE:
        raise HTTPException(status_code=503, detail="AI Analyst not available")

    try:
        analyst = get_analyst()
        # Note: weekend_market_analysis is synchronous
        analysis = analyst.weekend_market_analysis({}, {})

        return {
            "success": True,
            "analysis": analysis.to_dict() if analysis else None
        }
    except Exception as e:
        logger.error(f"Failed to get weekend analysis: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# PROPOSAL VALIDATION - PROVEN IMPROVEMENT REQUIRED
# =============================================================================

class ValidatedProposalRequest(BaseModel):
    """
    Request to create a proposal with full reasoning documentation.

    This is the recommended way to create proposals as it enforces
    the "proven improvement required" policy.
    """
    bot_name: str = Field(..., description="Bot name (FORTRESS, SOLOMON, ANCHOR, LAZARUS)")
    title: str = Field(..., description="Short title for the proposal")

    # DETAILED REASONING (WHY)
    problem_statement: str = Field(..., min_length=20, description="What problem are we solving? (min 20 chars)")
    hypothesis: str = Field(..., min_length=20, description="What do we believe will happen? (min 20 chars)")
    supporting_evidence: List[dict] = Field(..., min_items=1, description="Evidence supporting the change")
    expected_improvement: dict = Field(..., description="Expected improvement metrics")

    # Configuration
    current_config: dict = Field(..., description="Current configuration")
    proposed_config: dict = Field(..., description="Proposed new configuration")

    # Risk
    risk_level: str = Field("MEDIUM", description="Risk level (LOW, MEDIUM, HIGH)")
    risk_assessment: str = Field("", description="Risk assessment details")
    potential_downsides: List[str] = Field([], description="Potential downsides")

    # Validation method
    validation_method: str = Field("AB_TEST", description="Validation method (AB_TEST, BACKTEST, SHADOW_MODE)")


@router.post("/validation/create-proposal")
async def create_validated_proposal(request: ValidatedProposalRequest):
    """
    Create a proposal with complete reasoning and start validation.

    KEY PRINCIPLE: Proposals will ONLY be applied after improvement is PROVEN.

    This endpoint:
    1. Validates the reasoning is complete
    2. Creates the proposal with full documentation
    3. Starts the validation process (A/B test, backtest, etc.)

    The proposal cannot be applied until validation proves improvement.
    """
    if not ENHANCED_AVAILABLE:
        raise HTTPException(status_code=503, detail="Enhanced features not available")

    try:
        enhanced = get_proverbs_enhanced()

        result = enhanced.create_proposal_with_reasoning(
            bot_name=request.bot_name.upper(),
            title=request.title,
            problem_statement=request.problem_statement,
            hypothesis=request.hypothesis,
            supporting_evidence=request.supporting_evidence,
            expected_improvement=request.expected_improvement,
            current_config=request.current_config,
            proposed_config=request.proposed_config,
            risk_level=request.risk_level,
            risk_assessment=request.risk_assessment,
            potential_downsides=request.potential_downsides,
            validation_method=request.validation_method
        )

        return result
    except Exception as e:
        logger.error(f"Failed to create validated proposal: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/validation/status")
async def get_all_validation_status():
    """
    Get status of all pending validations.

    Shows which proposals are being validated and their current results.
    """
    if not ENHANCED_AVAILABLE:
        raise HTTPException(status_code=503, detail="Enhanced features not available")

    try:
        enhanced = get_proverbs_enhanced()
        status = enhanced.get_validation_status()

        return {
            "success": True,
            **status
        }
    except Exception as e:
        logger.error(f"Failed to get validation status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/validation/status/{proposal_id}")
async def get_proposal_validation_status(proposal_id: str):
    """
    Get validation status for a specific proposal.

    Shows:
    - Current validation progress
    - Whether improvement is proven
    - Detailed metrics comparison
    - Whether proposal can be applied
    """
    if not ENHANCED_AVAILABLE:
        raise HTTPException(status_code=503, detail="Enhanced features not available")

    try:
        enhanced = get_proverbs_enhanced()
        status = enhanced.get_validation_status(proposal_id)

        return {
            "success": True,
            "proposal_id": proposal_id,
            **status
        }
    except Exception as e:
        logger.error(f"Failed to get proposal validation status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/validation/can-apply/{proposal_id}")
async def can_apply_proposal(proposal_id: str):
    """
    Check if a proposal can be applied.

    Returns detailed status on:
    - Whether improvement is proven
    - Why/why not the proposal can be applied
    - What requirements are met/unmet
    """
    if not ENHANCED_AVAILABLE:
        raise HTTPException(status_code=503, detail="Enhanced features not available")

    try:
        enhanced = get_proverbs_enhanced()
        result = enhanced.can_apply_proposal(proposal_id)

        return {
            "success": True,
            "proposal_id": proposal_id,
            **result
        }
    except Exception as e:
        logger.error(f"Failed to check if proposal can be applied: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class ApplyValidatedProposalRequest(BaseModel):
    """Request to apply a validated proposal"""
    reviewer: str = Field(..., description="Username of the reviewer")


@router.post("/validation/apply/{proposal_id}")
async def apply_validated_proposal(proposal_id: str, request: ApplyValidatedProposalRequest):
    """
    Apply a proposal ONLY if validation proves improvement.

    This is the safe way to apply proposals - it enforces the
    "proven improvement required" policy.

    Will REJECT if:
    - Validation is incomplete
    - Improvement is not proven
    - Minimum trade count not reached
    - Minimum validation period not met
    """
    if not ENHANCED_AVAILABLE:
        raise HTTPException(status_code=503, detail="Enhanced features not available")

    try:
        enhanced = get_proverbs_enhanced()
        result = enhanced.apply_validated_proposal(
            proposal_id=proposal_id,
            reviewer=request.reviewer
        )

        if not result.get('success'):
            error_msg = result.get('error', 'Failed to apply proposal')
            details = result.get('details', {})
            raise HTTPException(
                status_code=400,
                detail=f"{error_msg}: {details}" if details else error_msg
            )

        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to apply validated proposal: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/validation/reasoning/{proposal_id}")
async def get_proposal_reasoning(proposal_id: str):
    """
    Get detailed reasoning for a proposal.

    Shows all the WHY information:
    - Problem statement
    - Hypothesis
    - Supporting evidence
    - Expected improvement
    - Risk assessment
    - Success criteria
    - Rollback triggers
    """
    if not ENHANCED_AVAILABLE:
        raise HTTPException(status_code=503, detail="Enhanced features not available")

    try:
        enhanced = get_proverbs_enhanced()
        reasoning = enhanced.get_proposal_reasoning(proposal_id)

        if not reasoning:
            raise HTTPException(status_code=404, detail="Reasoning not found for proposal")

        return {
            "success": True,
            "proposal_id": proposal_id,
            "reasoning": reasoning
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get proposal reasoning: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/validation/transparency-report/{proposal_id}")
async def get_transparency_report(proposal_id: str):
    """
    Get complete transparency report for a proposal.

    This shows ALL the details - WHO, WHAT, WHY, WHEN:
    - Who is making the change and who approves it
    - What exactly is changing (before/after)
    - Why the change is being made (detailed reasoning)
    - When it will be applied (validation status)
    - Risk assessment and rollback plan
    """
    if not ENHANCED_AVAILABLE:
        raise HTTPException(status_code=503, detail="Enhanced features not available")

    try:
        enhanced = get_proverbs_enhanced()
        report = enhanced.get_proposal_transparency_report(proposal_id)

        return {
            "success": True,
            **report
        }
    except Exception as e:
        logger.error(f"Failed to get transparency report: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class RecordValidationTradeRequest(BaseModel):
    """Request to record a trade during validation"""
    validation_id: str = Field(..., description="Validation ID")
    is_proposed: bool = Field(..., description="Whether this trade used the proposed config")
    pnl: float = Field(..., description="Trade P&L")


@router.post("/validation/record-trade")
async def record_validation_trade(request: RecordValidationTradeRequest):
    """
    Record a trade result during validation.

    This is used to track performance during A/B testing or other validation methods.
    """
    if not ENHANCED_AVAILABLE:
        raise HTTPException(status_code=503, detail="Enhanced features not available")

    try:
        enhanced = get_proverbs_enhanced()
        enhanced.proposal_validator.record_validation_trade(
            validation_id=request.validation_id,
            is_proposed=request.is_proposed,
            pnl=request.pnl
        )

        return {
            "success": True,
            "message": "Trade recorded for validation"
        }
    except Exception as e:
        logger.error(f"Failed to record validation trade: {e}")
        raise HTTPException(status_code=500, detail=str(e))
