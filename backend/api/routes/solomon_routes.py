"""
SOLOMON Dashboard API Routes
=============================

API endpoints for the Solomon Feedback Loop Intelligence System.
Provides dashboard, audit logs, proposal management, version control, and rollback.

All endpoints require the Solomon system to be available.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query, Body
from pydantic import BaseModel, Field
from zoneinfo import ZoneInfo

router = APIRouter(prefix="/api/solomon", tags=["Solomon"])
logger = logging.getLogger(__name__)

# Try to import Solomon
SOLOMON_AVAILABLE = False
solomon_instance = None

try:
    from quant.solomon_feedback_loop import (
        get_solomon, run_feedback_loop, approve_proposal, reject_proposal,
        rollback_bot, kill_bot, resume_bot, get_dashboard,
        BotName, ActionType, ProposalType, ProposalStatus
    )
    SOLOMON_AVAILABLE = True
    logger.info("Solomon feedback loop system loaded")
except ImportError as e:
    logger.warning(f"Solomon not available: {e}")


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
    bot_name: str = Field(..., description="Bot name (ARES, ATHENA, ATLAS, PHOENIX)")
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
async def solomon_health():
    """
    Check Solomon system health.

    Returns availability status and basic metrics.
    """
    if not SOLOMON_AVAILABLE:
        return {
            "status": "unavailable",
            "message": "Solomon feedback loop system not loaded",
            "timestamp": datetime.now(CENTRAL_TZ).isoformat()
        }

    try:
        solomon = get_solomon()
        health = solomon._get_system_health()

        return {
            "status": "healthy",
            "session_id": solomon.session_id,
            "database_connected": health.get('database', False),
            "oracle_connected": health.get('oracle', False),
            "last_feedback_run": health.get('last_feedback_run'),
            "pending_proposals": health.get('pending_proposals_count', 0),
            "degradation_alerts_24h": health.get('degradation_alerts', 0),
            "timestamp": datetime.now(CENTRAL_TZ).isoformat()
        }
    except Exception as e:
        logger.error(f"Solomon health check failed: {e}")
        return {
            "status": "error",
            "message": str(e),
            "timestamp": datetime.now(CENTRAL_TZ).isoformat()
        }


# =============================================================================
# DASHBOARD
# =============================================================================

@router.get("/dashboard")
async def get_solomon_dashboard():
    """
    Get comprehensive Solomon dashboard data.

    Returns:
    - Bot statuses (performance, versions, kill switch)
    - Pending proposals
    - Recent actions (audit log)
    - System health
    """
    if not SOLOMON_AVAILABLE:
        raise HTTPException(status_code=503, detail="Solomon system not available")

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
    if not SOLOMON_AVAILABLE:
        raise HTTPException(status_code=503, detail="Solomon system not available")

    bot_name = bot_name.upper()
    if bot_name not in ['ARES', 'ATHENA', 'ATLAS', 'PHOENIX']:
        raise HTTPException(status_code=400, detail=f"Invalid bot name: {bot_name}")

    try:
        solomon = get_solomon()

        return {
            "bot_name": bot_name,
            "is_killed": solomon.is_bot_killed(bot_name),
            "performance": solomon._get_current_performance(bot_name),
            "performance_history": solomon.get_performance_history(bot_name, days=30),
            "active_version": solomon._get_active_version_info(bot_name),
            "version_history": solomon.get_version_history(bot_name, limit=10),
            "recent_actions": solomon.get_audit_log(bot_name=bot_name, limit=20),
            "rollback_history": solomon.get_rollback_history(bot_name=bot_name, limit=5),
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
    if not SOLOMON_AVAILABLE:
        raise HTTPException(status_code=503, detail="Solomon system not available")

    try:
        solomon = get_solomon()

        start = datetime.fromisoformat(start_date) if start_date else None
        end = datetime.fromisoformat(end_date) if end_date else None

        logs = solomon.get_audit_log(
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
    if not SOLOMON_AVAILABLE:
        raise HTTPException(status_code=503, detail="Solomon system not available")

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
    if not SOLOMON_AVAILABLE:
        raise HTTPException(status_code=503, detail="Solomon system not available")

    try:
        from database_adapter import get_connection

        conn = get_connection()
        cursor = conn.cursor()

        query = "SELECT * FROM solomon_proposals WHERE 1=1"
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
    if not SOLOMON_AVAILABLE:
        raise HTTPException(status_code=503, detail="Solomon system not available")

    try:
        solomon = get_solomon()
        proposals = solomon.get_pending_proposals(bot_name=bot_name.upper() if bot_name else None)

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
    if not SOLOMON_AVAILABLE:
        raise HTTPException(status_code=503, detail="Solomon system not available")

    try:
        from database_adapter import get_connection

        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM solomon_proposals WHERE proposal_id = %s", (proposal_id,))
        columns = [desc[0] for desc in cursor.description]
        row = cursor.fetchone()
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
    if not SOLOMON_AVAILABLE:
        raise HTTPException(status_code=503, detail="Solomon system not available")

    try:
        solomon = get_solomon()

        proposal_type = ProposalType[request.proposal_type.upper()]

        proposal_id = solomon.create_proposal(
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
    if not SOLOMON_AVAILABLE:
        raise HTTPException(status_code=503, detail="Solomon system not available")

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
    if not SOLOMON_AVAILABLE:
        raise HTTPException(status_code=503, detail="Solomon system not available")

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
    if not SOLOMON_AVAILABLE:
        raise HTTPException(status_code=503, detail="Solomon system not available")

    try:
        solomon = get_solomon()
        versions = solomon.get_version_history(
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
    if not SOLOMON_AVAILABLE:
        raise HTTPException(status_code=503, detail="Solomon system not available")

    try:
        solomon = get_solomon()
        success = solomon.activate_version(version_id, f"USER:{user}")

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
    if not SOLOMON_AVAILABLE:
        raise HTTPException(status_code=503, detail="Solomon system not available")

    try:
        solomon = get_solomon()
        rollbacks = solomon.get_rollback_history(
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
    if not SOLOMON_AVAILABLE:
        raise HTTPException(status_code=503, detail="Solomon system not available")

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
    if not SOLOMON_AVAILABLE:
        raise HTTPException(status_code=503, detail="Solomon system not available")

    try:
        solomon = get_solomon()
        status = solomon.get_kill_switch_status()

        # Add bots not yet in the table
        for bot in ['ARES', 'ATHENA', 'ATLAS', 'PHOENIX']:
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
    if not SOLOMON_AVAILABLE:
        raise HTTPException(status_code=503, detail="Solomon system not available")

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
    if not SOLOMON_AVAILABLE:
        raise HTTPException(status_code=503, detail="Solomon system not available")

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
    if not SOLOMON_AVAILABLE:
        raise HTTPException(status_code=503, detail="Solomon system not available")

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
    if not SOLOMON_AVAILABLE:
        raise HTTPException(status_code=503, detail="Solomon system not available")

    try:
        solomon = get_solomon()

        # Get last run info
        runs = solomon.get_audit_log(
            action_type="FEEDBACK_LOOP_RUN",
            limit=5
        )

        return {
            "session_id": solomon.session_id,
            "recent_runs": runs,
            "guardrails": {
                'min_sample_size': 50,
                'max_parameter_change_pct': 20,
                'degradation_threshold': 15,
                'rollback_on_drawdown_pct': 10,
                'proposal_expiry_hours': 72
            },
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
    if not SOLOMON_AVAILABLE:
        raise HTTPException(status_code=503, detail="Solomon system not available")

    try:
        solomon = get_solomon()

        current = solomon._get_current_performance(bot_name.upper())
        history = solomon.get_performance_history(bot_name.upper(), days=days)
        degradation = solomon.detect_degradation(bot_name.upper())

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
    if not SOLOMON_AVAILABLE:
        raise HTTPException(status_code=503, detail="Solomon system not available")

    try:
        solomon = get_solomon()
        snapshot_id = solomon.record_performance_snapshot(bot_name.upper())

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
