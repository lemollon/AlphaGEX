"""
Wheel Strategy API Routes

Endpoints for managing wheel strategy cycles:
- Start new wheel (sell CSP)
- View active cycles
- Process expirations
- Roll positions
- Close cycles
"""

import logging
from datetime import datetime, date
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from zoneinfo import ZoneInfo

from trading.wheel_strategy import wheel_manager, WheelPhase

router = APIRouter(prefix="/api/wheel", tags=["Wheel Strategy"])
logger = logging.getLogger(__name__)


# ============================================================================
# Request/Response Models
# ============================================================================

class StartWheelRequest(BaseModel):
    """Request to start a new wheel cycle"""
    symbol: str = "SPY"
    strike: float
    expiration_date: str  # YYYY-MM-DD
    contracts: int = 1
    premium: float        # Per contract
    underlying_price: float
    delta: float = 0.30
    iv: float = 0.0
    contract_symbol: Optional[str] = None


class SellCoveredCallRequest(BaseModel):
    """Request to sell a covered call on assigned shares"""
    cycle_id: int
    strike: float
    expiration_date: str  # YYYY-MM-DD
    premium: float
    underlying_price: float
    delta: float = 0.30
    iv: float = 0.0
    contract_symbol: Optional[str] = None


class RollPositionRequest(BaseModel):
    """Request to roll a position"""
    cycle_id: int
    new_strike: float
    new_expiration: str  # YYYY-MM-DD
    close_price: float   # Cost to buy back current option
    open_premium: float  # Premium for new option
    underlying_price: float
    delta: float = 0.30
    iv: float = 0.0


class ProcessExpirationRequest(BaseModel):
    """Request to process option expiration"""
    cycle_id: int
    final_underlying_price: float


class CloseWheelRequest(BaseModel):
    """Request to close a wheel cycle"""
    cycle_id: int
    reason: str
    close_price: float = 0.0
    underlying_price: float = 0.0


# ============================================================================
# Endpoints
# ============================================================================

@router.post("/start")
async def start_wheel_cycle(request: StartWheelRequest):
    """
    Start a new wheel cycle by selling a cash-secured put.

    This is Phase 1 of the wheel strategy.
    """
    try:
        exp_date = datetime.strptime(request.expiration_date, '%Y-%m-%d').date()

        cycle_id = wheel_manager.start_wheel_cycle(
            symbol=request.symbol,
            strike=request.strike,
            expiration_date=exp_date,
            contracts=request.contracts,
            premium=request.premium,
            underlying_price=request.underlying_price,
            delta=request.delta,
            iv=request.iv,
            contract_symbol=request.contract_symbol
        )

        return {
            "success": True,
            "message": f"Started wheel cycle #{cycle_id}",
            "data": {
                "cycle_id": cycle_id,
                "phase": "CSP",
                "symbol": request.symbol,
                "strike": request.strike,
                "expiration": request.expiration_date,
                "premium_collected": request.premium * request.contracts * 100
            }
        }
    except Exception as e:
        logger.error(f"Error starting wheel cycle: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sell-covered-call")
async def sell_covered_call(request: SellCoveredCallRequest):
    """
    Sell a covered call on assigned shares.

    This is Phase 3 of the wheel strategy (after assignment).
    """
    try:
        exp_date = datetime.strptime(request.expiration_date, '%Y-%m-%d').date()

        leg_id = wheel_manager.sell_covered_call(
            cycle_id=request.cycle_id,
            strike=request.strike,
            expiration_date=exp_date,
            premium=request.premium,
            underlying_price=request.underlying_price,
            delta=request.delta,
            iv=request.iv,
            contract_symbol=request.contract_symbol
        )

        return {
            "success": True,
            "message": f"Sold covered call for cycle #{request.cycle_id}",
            "data": {
                "cycle_id": request.cycle_id,
                "leg_id": leg_id,
                "phase": "COVERED_CALL",
                "strike": request.strike,
                "expiration": request.expiration_date,
                "premium_collected": request.premium * 100  # Assuming 1 contract for now
            }
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error selling covered call: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/process-expiration")
async def process_expiration(request: ProcessExpirationRequest):
    """
    Process option expiration (CSP or CC).

    Determines if option expired OTM (keep premium) or was assigned/called away.
    """
    try:
        # Get current phase
        cycle = wheel_manager.get_cycle_details(request.cycle_id)
        if not cycle:
            raise HTTPException(status_code=404, detail=f"Cycle {request.cycle_id} not found")

        phase = cycle['status']

        if phase == WheelPhase.CSP.value:
            result = wheel_manager.process_csp_expiration(
                request.cycle_id,
                request.final_underlying_price
            )
        elif phase == WheelPhase.COVERED_CALL.value:
            result = wheel_manager.process_cc_expiration(
                request.cycle_id,
                request.final_underlying_price
            )
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot process expiration for cycle in {phase} status"
            )

        return {
            "success": True,
            "message": f"Processed expiration: {result['action']}",
            "data": result
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing expiration: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/roll")
async def roll_position(request: RollPositionRequest):
    """
    Roll an existing position to a new strike/expiration.

    Closes the current leg and opens a new one.
    """
    try:
        new_exp = datetime.strptime(request.new_expiration, '%Y-%m-%d').date()

        result = wheel_manager.roll_position(
            cycle_id=request.cycle_id,
            new_strike=request.new_strike,
            new_expiration=new_exp,
            close_price=request.close_price,
            open_premium=request.open_premium,
            underlying_price=request.underlying_price,
            delta=request.delta,
            iv=request.iv
        )

        return {
            "success": True,
            "message": f"Rolled position: {result['old_strike']} -> {result['new_strike']}",
            "data": result
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error rolling position: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/close")
async def close_wheel_cycle(request: CloseWheelRequest):
    """
    Manually close a wheel cycle.
    """
    try:
        result = wheel_manager.close_cycle(
            cycle_id=request.cycle_id,
            reason=request.reason,
            close_price=request.close_price,
            underlying_price=request.underlying_price
        )

        return {
            "success": True,
            "message": f"Closed wheel cycle #{request.cycle_id}",
            "data": result
        }
    except Exception as e:
        logger.error(f"Error closing wheel cycle: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/active")
async def get_active_cycles(symbol: Optional[str] = None):
    """
    Get all active wheel cycles.
    """
    try:
        cycles = wheel_manager.get_active_cycles(symbol)
        return {
            "success": True,
            "data": cycles,
            "count": len(cycles)
        }
    except Exception as e:
        logger.error(f"Error getting active cycles: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/cycle/{cycle_id}")
async def get_cycle_details(cycle_id: int):
    """
    Get full details of a wheel cycle including all legs and activity.
    """
    try:
        cycle = wheel_manager.get_cycle_details(cycle_id)
        if not cycle:
            raise HTTPException(status_code=404, detail=f"Cycle {cycle_id} not found")

        return {
            "success": True,
            "data": cycle
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting cycle details: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/summary")
async def get_wheel_summary(symbol: Optional[str] = None):
    """
    Get summary statistics for the wheel strategy.
    """
    try:
        summary = wheel_manager.get_wheel_summary(symbol)
        return {
            "success": True,
            "data": summary
        }
    except Exception as e:
        logger.error(f"Error getting wheel summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/phases")
async def get_wheel_phases():
    """
    Get information about wheel phases for UI display.
    """
    return {
        "success": True,
        "data": {
            "phases": [
                {
                    "id": "CSP",
                    "name": "Cash-Secured Put",
                    "description": "Sell a put option. Collect premium. Wait for expiration.",
                    "next_if_otm": "Sell another CSP (premium income)",
                    "next_if_itm": "Get assigned shares (move to Phase 2)"
                },
                {
                    "id": "ASSIGNED",
                    "name": "Share Assignment",
                    "description": "You now own 100 shares per contract at the strike price.",
                    "cost_basis": "Strike price - premiums collected",
                    "next": "Sell a covered call above your cost basis"
                },
                {
                    "id": "COVERED_CALL",
                    "name": "Covered Call",
                    "description": "Sell a call option against your shares. Collect premium.",
                    "next_if_otm": "Keep shares, sell another covered call",
                    "next_if_itm": "Shares called away (cycle complete)"
                },
                {
                    "id": "CALLED_AWAY",
                    "name": "Cycle Complete",
                    "description": "Shares sold at strike price. Wheel cycle is complete.",
                    "total_profit": "All premiums collected + (call strike - put strike) if positive",
                    "next": "Start a new wheel cycle"
                }
            ]
        }
    }
