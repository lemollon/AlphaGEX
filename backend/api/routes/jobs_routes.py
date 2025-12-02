"""
Background Jobs API Routes

Endpoints for starting, monitoring, and managing background jobs.
Jobs continue running even when user closes browser.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import logging

router = APIRouter(prefix="/api/jobs", tags=["Background Jobs"])
logger = logging.getLogger(__name__)


class StartJobRequest(BaseModel):
    """Request to start a background job"""
    job_type: str  # 'spx_backtest', 'spy_backtest', 'full_backtest', 'ml_training'
    params: Optional[Dict[str, Any]] = {}


class JobResponse(BaseModel):
    """Job status response"""
    job_id: str
    job_type: str
    status: str
    progress: int
    message: str
    result: Optional[Dict] = None
    error: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


@router.post("/start", response_model=Dict)
async def start_job(request: StartJobRequest):
    """
    Start a new background job.

    Job types:
    - spx_backtest: Run SPX wheel strategy backtest
    - spy_backtest: Run SPY trader backtest
    - full_backtest: Run backtest for all symbols
    - ml_training: Train ML model

    Jobs run in background threads and persist to database.
    Use /api/jobs/{job_id}/status to poll for completion.
    """
    try:
        from backend.jobs import get_job_manager

        job_manager = get_job_manager()

        # Validate job type
        valid_types = ['spx_backtest', 'spy_backtest', 'full_backtest', 'ml_training']
        if request.job_type not in valid_types:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid job_type. Must be one of: {valid_types}"
            )

        # Start the job
        job_id = job_manager.start_job(request.job_type, request.params or {})

        return {
            "success": True,
            "job_id": job_id,
            "message": f"Job {job_id} started. Poll /api/jobs/{job_id}/status for updates.",
            "poll_url": f"/api/jobs/{job_id}/status"
        }

    except Exception as e:
        logger.error(f"Error starting job: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{job_id}/status")
async def get_job_status(job_id: str):
    """
    Get the current status of a background job.

    Poll this endpoint to track job progress.
    Returns progress (0-100), status, and result when complete.
    """
    try:
        from backend.jobs import get_job_manager

        job_manager = get_job_manager()
        job = job_manager.get_job_status(job_id)

        if not job:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

        return {
            "success": True,
            "job": job.to_dict()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting job status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{job_id}/result")
async def get_job_result(job_id: str):
    """
    Get the full result of a completed job.

    Returns error if job is still running or failed.
    """
    try:
        from backend.jobs import get_job_manager

        job_manager = get_job_manager()
        job = job_manager.get_job_status(job_id)

        if not job:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

        if job.status.value == 'running':
            return {
                "success": False,
                "message": "Job still running",
                "progress": job.progress
            }

        if job.status.value == 'failed':
            return {
                "success": False,
                "message": "Job failed",
                "error": job.error
            }

        return {
            "success": True,
            "result": job.result
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting job result: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{job_id}/cancel")
async def cancel_job(job_id: str):
    """Cancel a running job (best effort)"""
    try:
        from backend.jobs import get_job_manager

        job_manager = get_job_manager()
        success = job_manager.cancel_job(job_id)

        if not success:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found or already finished")

        return {
            "success": True,
            "message": f"Job {job_id} cancelled"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cancelling job: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/")
async def list_jobs(status: Optional[str] = None, limit: int = 20):
    """
    List recent background jobs.

    Args:
        status: Optional filter (pending, running, completed, failed)
        limit: Max jobs to return (default 20)
    """
    try:
        from backend.jobs import get_job_manager

        job_manager = get_job_manager()
        jobs = job_manager.list_jobs(status=status, limit=limit)

        return {
            "success": True,
            "jobs": jobs,
            "count": len(jobs)
        }

    except Exception as e:
        logger.error(f"Error listing jobs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Convenience endpoints for specific job types

@router.post("/backtest/spx")
async def start_spx_backtest(days: int = 365, params: Optional[Dict] = None):
    """
    Start SPX wheel strategy backtest.

    This runs in background - use returned job_id to poll for status.
    """
    full_params = {'days': days}
    if params:
        full_params.update(params)

    request = StartJobRequest(job_type='spx_backtest', params=full_params)
    return await start_job(request)


@router.post("/backtest/spy")
async def start_spy_backtest(days: int = 90, params: Optional[Dict] = None):
    """
    Start SPY trader backtest.

    This runs in background - use returned job_id to poll for status.
    """
    full_params = {'days': days, 'symbol': 'SPY'}
    if params:
        full_params.update(params)

    request = StartJobRequest(job_type='spy_backtest', params=full_params)
    return await start_job(request)


@router.post("/backtest/all")
async def start_full_backtest(symbols: List[str] = ['SPY', 'SPX'], days: int = 90):
    """
    Start backtest for multiple symbols.

    This runs in background - use returned job_id to poll for status.
    """
    request = StartJobRequest(
        job_type='full_backtest',
        params={'symbols': symbols, 'days': days}
    )
    return await start_job(request)


@router.post("/ml/train")
async def start_ml_training(lookback_days: int = 180):
    """
    Start ML model training.

    This runs in background - use returned job_id to poll for status.
    """
    request = StartJobRequest(
        job_type='ml_training',
        params={'lookback_days': lookback_days}
    )
    return await start_job(request)
