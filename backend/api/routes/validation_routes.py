"""
Auto-Validation System API Routes
=================================

Endpoints for monitoring and triggering ML model validation and Thompson allocation.

Routes:
- GET /api/validation/status - Get validation system status
- GET /api/validation/models - List all registered models
- GET /api/validation/results - Get last validation results
- POST /api/validation/run - Trigger validation (force=true for immediate)
- POST /api/validation/retrain/{model_name} - Trigger retrain for specific model
- GET /api/validation/thompson - Get Thompson allocation status
- GET /api/validation/thompson/allocate - Get capital allocation
- POST /api/validation/thompson/record - Record bot outcome

Author: AlphaGEX
Date: 2025-01
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Validation"])

# Import AutoValidationSystem
try:
    from quant.auto_validation_system import (
        get_auto_validation_system,
        run_validation,
        get_capital_allocation,
        record_bot_outcome,
        get_validation_status,
        ModelValidationResult
    )
    VALIDATION_AVAILABLE = True
except ImportError as e:
    VALIDATION_AVAILABLE = False
    logger.warning(f"AutoValidationSystem not available: {e}")


# =============================================================================
# PYDANTIC MODELS
# =============================================================================

class ValidationRunRequest(BaseModel):
    force: bool = False


class RetrainRequest(BaseModel):
    model_name: str


class ThompsonOutcomeRequest(BaseModel):
    bot_name: str
    win: bool
    pnl: float = 0.0


class AllocationRequest(BaseModel):
    total_capital: float = 100000.0
    method: str = "thompson"  # "thompson" or "equal"


# =============================================================================
# STATUS ENDPOINTS
# =============================================================================

@router.get("/api/validation/status")
async def get_status():
    """
    Get current validation system status.

    Returns:
        - Last validation time
        - Number of models registered
        - Thompson allocation parameters
        - Auto-retrain status
    """
    if not VALIDATION_AVAILABLE:
        raise HTTPException(status_code=503, detail="AutoValidationSystem not available")

    try:
        status = get_validation_status()
        return {
            "status": "success",
            "data": status
        }
    except Exception as e:
        logger.error(f"Failed to get validation status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/validation/models")
async def list_models():
    """
    List all registered ML models.

    Returns list of models with:
        - Name
        - Description
        - Degradation threshold
        - Last validation time
        - Current status
    """
    if not VALIDATION_AVAILABLE:
        raise HTTPException(status_code=503, detail="AutoValidationSystem not available")

    try:
        system = get_auto_validation_system()

        models = []
        for name, info in system.model_registry.models.items():
            models.append({
                "name": name,
                "description": info['description'],
                "degradation_threshold": info['degradation_threshold'],
                "last_validation": info['last_validation'].isoformat() if info['last_validation'] else None,
                "last_retrain": info['last_retrain'].isoformat() if info['last_retrain'] else None,
                "status": info['status'].value
            })

        return {
            "status": "success",
            "total_models": len(models),
            "models": models
        }
    except Exception as e:
        logger.error(f"Failed to list models: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/validation/results")
async def get_results():
    """
    Get results from the last validation run.

    Returns detailed results for each model including:
        - In-sample accuracy
        - Out-of-sample accuracy
        - Degradation percentage
        - Is robust (boolean)
        - Recommendation (KEEP/RETRAIN/INVESTIGATE)
    """
    if not VALIDATION_AVAILABLE:
        raise HTTPException(status_code=503, detail="AutoValidationSystem not available")

    try:
        system = get_auto_validation_system()
        summary = system.get_validation_summary()

        return {
            "status": "success",
            "data": summary
        }
    except Exception as e:
        logger.error(f"Failed to get validation results: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# VALIDATION ENDPOINTS
# =============================================================================

@router.post("/api/validation/run")
async def trigger_validation(request: ValidationRunRequest):
    """
    Trigger ML model validation.

    Args:
        force: If true, run immediately regardless of schedule

    Returns:
        Validation results for all models
    """
    if not VALIDATION_AVAILABLE:
        raise HTTPException(status_code=503, detail="AutoValidationSystem not available")

    try:
        logger.info(f"Validation triggered via API (force={request.force})")

        results = run_validation(force=request.force)

        # Convert results to dict
        results_dict = [r.to_dict() for r in results]

        # Count by status
        healthy = sum(1 for r in results if r.status.value == 'healthy')
        degraded = sum(1 for r in results if r.status.value == 'degraded')
        failed = sum(1 for r in results if r.status.value == 'failed')

        return {
            "status": "success",
            "message": f"Validation completed for {len(results)} models",
            "summary": {
                "total": len(results),
                "healthy": healthy,
                "degraded": degraded,
                "failed": failed
            },
            "results": results_dict
        }
    except Exception as e:
        logger.error(f"Validation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/validation/retrain/{model_name}")
async def trigger_retrain(model_name: str):
    """
    Trigger retrain for a specific ML model.

    Args:
        model_name: Name of the model to retrain

    Returns:
        Success/failure status
    """
    if not VALIDATION_AVAILABLE:
        raise HTTPException(status_code=503, detail="AutoValidationSystem not available")

    try:
        system = get_auto_validation_system()

        if model_name not in system.model_registry.models:
            raise HTTPException(
                status_code=404,
                detail=f"Model '{model_name}' not found. Available: {list(system.model_registry.models.keys())}"
            )

        logger.info(f"Retrain triggered for {model_name} via API")

        success = system.retrain_model(model_name)

        return {
            "status": "success" if success else "failed",
            "model_name": model_name,
            "retrained": success,
            "message": f"Model {model_name} {'retrained successfully' if success else 'retrain failed'}"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Retrain failed for {model_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# THOMPSON SAMPLING ENDPOINTS
# =============================================================================

@router.get("/api/validation/thompson")
async def get_thompson_status():
    """
    Get Thompson Sampling allocator status.

    Returns:
        - Bot names
        - Alpha/Beta parameters for each bot
        - Confidence scores
        - Win rate estimates
    """
    if not VALIDATION_AVAILABLE:
        raise HTTPException(status_code=503, detail="AutoValidationSystem not available")

    try:
        system = get_auto_validation_system()

        if not system.thompson:
            return {
                "status": "success",
                "available": False,
                "message": "Thompson Sampling not available"
            }

        bots = {}
        for bot in system.bot_names:
            alpha = system.thompson.alpha[bot]
            beta = system.thompson.beta[bot]
            confidence = system.get_bot_confidence(bot)

            bots[bot] = {
                "alpha": alpha,
                "beta": beta,
                "confidence": confidence,
                "win_rate_estimate": confidence,
                "total_observations": alpha + beta - 2  # Subtract prior
            }

        return {
            "status": "success",
            "available": True,
            "bots": bots
        }
    except Exception as e:
        logger.error(f"Failed to get Thompson status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/validation/thompson/allocate")
async def get_allocation(request: AllocationRequest):
    """
    Get capital allocation across bots using Thompson Sampling.

    Args:
        total_capital: Total capital to allocate (default: 100000)
        method: "thompson" or "equal" (default: "thompson")

    Returns:
        Allocation amounts and percentages per bot
    """
    if not VALIDATION_AVAILABLE:
        raise HTTPException(status_code=503, detail="AutoValidationSystem not available")

    try:
        system = get_auto_validation_system()
        allocation = system.get_capital_allocation(
            total_capital=request.total_capital,
            method=request.method
        )

        return {
            "status": "success",
            "allocation": {
                "timestamp": allocation.timestamp,
                "total_capital": allocation.total_capital,
                "method": allocation.method,
                "allocations": allocation.allocations,
                "allocation_percentages": allocation.allocation_pcts,
                "confidence": allocation.confidence
            }
        }
    except Exception as e:
        logger.error(f"Failed to get allocation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/validation/thompson/record")
async def record_outcome(request: ThompsonOutcomeRequest):
    """
    Record a bot trade outcome for Thompson Sampling.

    This updates the Beta distribution parameters for the bot,
    affecting future capital allocation.

    Args:
        bot_name: Name of the bot (ARES, ATHENA, etc.)
        win: Whether the trade was profitable
        pnl: Actual P&L amount

    Returns:
        Updated confidence for the bot
    """
    if not VALIDATION_AVAILABLE:
        raise HTTPException(status_code=503, detail="AutoValidationSystem not available")

    try:
        system = get_auto_validation_system()

        if request.bot_name not in system.bot_names:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown bot: {request.bot_name}. Valid: {system.bot_names}"
            )

        # Record the outcome
        record_bot_outcome(request.bot_name, request.win, request.pnl)

        # Get updated confidence
        confidence = system.get_bot_confidence(request.bot_name)

        return {
            "status": "success",
            "bot_name": request.bot_name,
            "win": request.win,
            "pnl": request.pnl,
            "updated_confidence": confidence
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to record outcome: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# HEALTH CHECK
# =============================================================================

@router.get("/api/validation/health")
async def health_check():
    """
    Check if validation system is healthy.
    """
    return {
        "status": "healthy" if VALIDATION_AVAILABLE else "unavailable",
        "validation_available": VALIDATION_AVAILABLE
    }
