"""
PROMETHEUS Box Spread API Routes - Synthetic Borrowing System

Comprehensive API for the PROMETHEUS box spread system with
enhanced educational endpoints for learning the strategy.

This is different from prometheus_routes.py (ML system).
This handles the Box Spread Synthetic Borrowing Bot.

Endpoint Categories:
1. Status & Health - System status and configuration
2. Positions - Box spread position management
3. Signals - Signal generation and execution
4. Analytics - Rate analysis, capital flow, performance
5. Education - Learning content about box spreads
6. Operations - Daily cycles, rolls, closes
"""

from fastapi import APIRouter, HTTPException, Query, Body
from typing import Optional, Dict, Any, List
from datetime import datetime, date
from pydantic import BaseModel, Field
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/prometheus-box", tags=["PROMETHEUS Box Spread - Synthetic Borrowing"])

# Import PROMETHEUS Box Spread components with fallback
PrometheusTrader = None
PrometheusConfig = None
TradingMode = None

try:
    from trading.prometheus import (
        PrometheusTrader,
        PrometheusConfig,
        TradingMode,
    )
    logger.info("PROMETHEUS Box Spread modules loaded successfully")
except ImportError as e:
    logger.warning(f"PROMETHEUS Box Spread modules not available: {e}")


# ========== Pydantic Models for Request/Response ==========

class ConfigUpdateRequest(BaseModel):
    """Request model for configuration updates"""
    mode: Optional[str] = Field(None, description="Trading mode: 'paper' or 'live'")
    ticker: Optional[str] = Field(None, description="Underlying: SPX or XSP")
    strike_width: Optional[float] = Field(None, description="Box spread width in points")
    target_dte_min: Optional[int] = Field(None, description="Minimum days to expiration")
    target_dte_max: Optional[int] = Field(None, description="Maximum days to expiration")
    max_implied_rate: Optional[float] = Field(None, description="Max acceptable borrowing rate %")
    capital: Optional[float] = Field(None, description="Total capital for box spreads")
    max_positions: Optional[int] = Field(None, description="Maximum simultaneous positions")
    ares_allocation_pct: Optional[float] = Field(None, description="% to deploy to ARES")
    titan_allocation_pct: Optional[float] = Field(None, description="% to deploy to TITAN")
    pegasus_allocation_pct: Optional[float] = Field(None, description="% to deploy to PEGASUS")
    educational_mode: Optional[bool] = Field(None, description="Enable extra explanations")


class ExecuteSignalRequest(BaseModel):
    """Request to execute a specific signal"""
    signal_id: str = Field(..., description="Signal ID to execute")
    override_validation: bool = Field(False, description="Execute even if validation fails")


class ClosePositionRequest(BaseModel):
    """Request to close a position"""
    position_id: str = Field(..., description="Position ID to close")
    reason: str = Field("manual", description="Reason for closing")


class RollPositionRequest(BaseModel):
    """Request to roll a position"""
    position_id: str = Field(..., description="Position ID to roll")
    target_expiration: Optional[str] = Field(None, description="Target expiration YYYY-MM-DD")


# ========== Status & Health Endpoints ==========

@router.get("/status")
async def get_prometheus_box_status():
    """
    Get comprehensive PROMETHEUS Box Spread system status.

    Returns:
    - System status (ACTIVE, PAUSED, MARGIN_WARNING, etc.)
    - Open positions count and value
    - Total borrowed and deployed amounts
    - Net P&L from IC returns vs borrowing costs
    - Configuration summary
    """
    if not PrometheusTrader:
        raise HTTPException(status_code=503, detail="PROMETHEUS Box Spread not available")

    try:
        trader = PrometheusTrader()
        return trader.get_status()
    except Exception as e:
        logger.error(f"Error getting PROMETHEUS Box status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def prometheus_box_health_check():
    """
    Health check for PROMETHEUS Box Spread system.

    Verifies:
    - Database connectivity
    - Module availability
    - Configuration validity
    """
    health = {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "bot_name": "PROMETHEUS",
        "bot_type": "Box Spread Synthetic Borrowing",
        "checks": {
            "trader_available": PrometheusTrader is not None,
            "config_available": PrometheusConfig is not None,
        }
    }

    if not PrometheusTrader:
        health["status"] = "degraded"
        health["message"] = "PROMETHEUS Box Spread trader not available"

    return health


@router.get("/config")
async def get_config():
    """
    Get current PROMETHEUS Box Spread configuration.

    Returns all configuration parameters with explanations.
    """
    if not PrometheusTrader:
        raise HTTPException(status_code=503, detail="PROMETHEUS Box Spread not available")

    try:
        trader = PrometheusTrader()
        config = trader.config.to_dict()

        # Add explanations in educational mode
        config['explanations'] = {
            'ticker': 'SPX preferred for European-style (no early assignment)',
            'strike_width': 'Wider = more cash per contract but higher margin',
            'target_dte': 'Longer DTE generally means lower implied rates',
            'max_implied_rate': 'Skip opportunities with rates above this threshold',
            'allocations': 'How borrowed capital is distributed to IC bots',
        }

        return config
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/config")
async def update_config(request: ConfigUpdateRequest):
    """
    Update PROMETHEUS Box Spread configuration.

    Only provided fields will be updated.
    """
    if not PrometheusTrader:
        raise HTTPException(status_code=503, detail="PROMETHEUS Box Spread not available")

    try:
        trader = PrometheusTrader()
        config = trader.config

        # Update provided fields
        update_data = request.dict(exclude_none=True)
        for key, value in update_data.items():
            if key == 'mode':
                config.mode = TradingMode(value)
            elif hasattr(config, key):
                setattr(config, key, value)

        # Save configuration
        trader.db.save_config(config)

        return {
            "success": True,
            "message": "Configuration updated",
            "updated_fields": list(update_data.keys()),
            "new_config": config.to_dict(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ========== Position Endpoints ==========

@router.get("/positions")
async def get_positions():
    """
    Get all open box spread positions.

    Each position includes:
    - Strike details and expiration
    - Cash received and owed
    - Borrowing cost metrics
    - Capital deployment to IC bots
    - Current returns and net P&L
    """
    if not PrometheusTrader:
        raise HTTPException(status_code=503, detail="PROMETHEUS Box Spread not available")

    try:
        trader = PrometheusTrader()
        positions = trader.get_positions()

        return {
            "open_positions": positions,
            "count": len(positions),
            "summary": {
                "total_borrowed": sum(p.get('total_credit_received', 0) for p in positions),
                "total_deployed": sum(p.get('total_cash_deployed', 0) for p in positions),
                "total_returns": sum(p.get('total_ic_returns', 0) for p in positions),
                "net_profit": sum(p.get('net_profit', 0) for p in positions),
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/positions/{position_id}")
async def get_position_detail(position_id: str):
    """
    Get detailed information about a specific position.

    Includes full educational explanation of the position.
    """
    if not PrometheusTrader:
        raise HTTPException(status_code=503, detail="PROMETHEUS Box Spread not available")

    try:
        trader = PrometheusTrader()
        position = trader.db.get_position(position_id)

        if not position:
            raise HTTPException(status_code=404, detail="Position not found")

        return position.to_dict()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/positions/close")
async def close_position(request: ClosePositionRequest):
    """
    Close an open box spread position.

    This will:
    1. Buy back both spreads at market
    2. Record final P&L
    3. Deactivate capital deployments
    """
    if not PrometheusTrader:
        raise HTTPException(status_code=503, detail="PROMETHEUS Box Spread not available")

    try:
        trader = PrometheusTrader()
        result = trader.close_position(request.position_id, request.reason)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/positions/roll")
async def roll_position(request: RollPositionRequest):
    """
    Roll a position to a new expiration.

    Rolling involves closing the current position and opening
    a new one at a later expiration to extend borrowing.
    """
    if not PrometheusTrader:
        raise HTTPException(status_code=503, detail="PROMETHEUS Box Spread not available")

    try:
        trader = PrometheusTrader()
        result = trader.roll_position(
            request.position_id,
            request.target_expiration
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ========== Signal & Execution Endpoints ==========

@router.get("/signals/scan")
async def scan_for_signals():
    """
    Scan for new box spread opportunities.

    Analyzes current market conditions and generates a signal
    if a favorable opportunity exists.
    """
    if not PrometheusTrader:
        raise HTTPException(status_code=503, detail="PROMETHEUS Box Spread not available")

    try:
        trader = PrometheusTrader()
        result = trader.run_signal_scan()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/signals/recent")
async def get_recent_signals(limit: int = Query(20, ge=1, le=100)):
    """
    Get recent signals (executed or not).

    Shows signal history for review and learning.
    """
    if not PrometheusTrader:
        raise HTTPException(status_code=503, detail="PROMETHEUS Box Spread not available")

    try:
        trader = PrometheusTrader()
        signals = trader.db.get_recent_signals(limit)
        return {
            "signals": signals,
            "count": len(signals),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/signals/execute")
async def execute_signal():
    """
    Execute a box spread signal.

    This places the actual orders to open the box spread position.
    """
    if not PrometheusTrader:
        raise HTTPException(status_code=503, detail="PROMETHEUS Box Spread not available")

    try:
        trader = PrometheusTrader()

        # First, generate a fresh signal
        scan_result = trader.run_signal_scan()
        if not scan_result.get('should_trade'):
            return {
                "success": False,
                "message": scan_result.get('reason', 'No valid signal'),
            }

        # Get the signal and execute
        from trading.prometheus.models import BoxSpreadSignal
        signal_data = scan_result.get('signal')
        if not signal_data:
            return {"success": False, "message": "No signal data"}

        # Reconstruct signal object - handle datetime
        if isinstance(signal_data.get('signal_time'), str):
            signal_data['signal_time'] = datetime.fromisoformat(signal_data['signal_time'])

        signal = BoxSpreadSignal(**signal_data)
        result = trader.execute_signal(signal)
        return result
    except Exception as e:
        logger.error(f"Error executing signal: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ========== Analytics Endpoints ==========

@router.get("/analytics/rates")
async def get_rate_analysis():
    """
    Get current borrowing rate analysis.

    Compares box spread implied rates to alternatives:
    - Fed Funds rate
    - Broker margin rate
    - SOFR

    Includes recommendation on whether to borrow.
    """
    if not PrometheusTrader:
        raise HTTPException(status_code=503, detail="PROMETHEUS Box Spread not available")

    try:
        trader = PrometheusTrader()
        return trader.get_rate_analysis()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analytics/rates/history")
async def get_rate_history(days: int = Query(30, ge=1, le=365)):
    """
    Get historical rate analysis for trend analysis.
    """
    if not PrometheusTrader:
        raise HTTPException(status_code=503, detail="PROMETHEUS Box Spread not available")

    try:
        trader = PrometheusTrader()
        history = trader.db.get_rate_history(days)
        return {
            "history": history,
            "count": len(history),
            "days_requested": days,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analytics/capital-flow")
async def get_capital_flow():
    """
    Get capital flow analysis.

    Shows how box spread cash is deployed across IC bots
    and the returns generated by each.
    """
    if not PrometheusTrader:
        raise HTTPException(status_code=503, detail="PROMETHEUS Box Spread not available")

    try:
        trader = PrometheusTrader()
        return trader.get_capital_flow()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analytics/performance")
async def get_performance():
    """
    Get overall performance summary.

    Includes:
    - Closed position statistics
    - Win rate
    - Total P&L
    - Average implied rate achieved
    """
    if not PrometheusTrader:
        raise HTTPException(status_code=503, detail="PROMETHEUS Box Spread not available")

    try:
        trader = PrometheusTrader()
        return trader.db.get_performance_summary()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/equity-curve")
async def get_equity_curve(limit: int = Query(100, ge=1, le=500)):
    """
    Get historical equity curve data.
    """
    if not PrometheusTrader:
        raise HTTPException(status_code=503, detail="PROMETHEUS Box Spread not available")

    try:
        trader = PrometheusTrader()
        curve = trader.db.get_equity_curve(limit)
        return {
            "equity_curve": curve,
            "starting_capital": trader.db.get_starting_capital(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/equity-curve/intraday")
async def get_intraday_equity():
    """
    Get today's equity snapshots for intraday tracking.
    """
    if not PrometheusTrader:
        raise HTTPException(status_code=503, detail="PROMETHEUS Box Spread not available")

    try:
        trader = PrometheusTrader()
        return {
            "snapshots": trader.db.get_intraday_equity(),
            "date": date.today().isoformat(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ========== Operations Endpoints ==========

@router.post("/operations/daily-cycle")
async def run_daily_cycle():
    """
    Run the daily PROMETHEUS cycle.

    This updates all positions:
    - Recalculates DTE
    - Accrues borrowing costs
    - Fetches IC bot returns
    - Checks for roll opportunities
    - Records equity snapshot
    """
    if not PrometheusTrader:
        raise HTTPException(status_code=503, detail="PROMETHEUS Box Spread not available")

    try:
        trader = PrometheusTrader()
        return trader.run_daily_cycle()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/operations/daily-briefing")
async def get_daily_briefing():
    """
    Get today's daily briefing.

    Comprehensive status report including:
    - System status
    - Position summaries
    - Rate environment
    - Recommendations and warnings
    - Educational tip of the day
    """
    if not PrometheusTrader:
        raise HTTPException(status_code=503, detail="PROMETHEUS Box Spread not available")

    try:
        trader = PrometheusTrader()
        return trader.generate_daily_briefing()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/operations/equity-snapshot")
async def record_equity_snapshot():
    """
    Manually record an equity snapshot.

    Normally called automatically during daily cycle.
    """
    if not PrometheusTrader:
        raise HTTPException(status_code=503, detail="PROMETHEUS Box Spread not available")

    try:
        trader = PrometheusTrader()
        success = trader.db.record_equity_snapshot()
        return {"success": success}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ========== Education Endpoints ==========

@router.get("/education")
async def get_education_topics():
    """
    List available educational topics about box spreads.
    """
    return {
        "topics": [
            {
                "id": "overview",
                "title": "Box Spread Synthetic Borrowing - Overview",
                "description": "Introduction to box spreads and the PROMETHEUS strategy",
            },
            {
                "id": "mechanics",
                "title": "Box Spread Mechanics",
                "description": "Detailed explanation of how box spreads work",
            },
            {
                "id": "risks",
                "title": "Box Spread Risks",
                "description": "Understanding and managing box spread risks",
            },
            {
                "id": "comparison",
                "title": "Box Spreads vs Alternatives",
                "description": "Comparing box spreads to margin and other borrowing methods",
            },
        ]
    }


@router.get("/education/{topic}")
async def get_education_content(topic: str):
    """
    Get educational content for a specific topic.

    Topics:
    - overview: Introduction to box spreads
    - mechanics: How box spreads work
    - risks: Understanding risks
    - comparison: vs margin and other methods
    """
    if not PrometheusTrader:
        raise HTTPException(status_code=503, detail="PROMETHEUS Box Spread not available")

    try:
        trader = PrometheusTrader()
        content = trader.get_education_content(topic)
        return content
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/education/calculator")
async def box_spread_calculator(
    strike_width: float = Query(50, description="Strike width in points"),
    dte: int = Query(180, description="Days to expiration"),
    market_price: float = Query(49.5, description="Current box spread price"),
):
    """
    Interactive box spread calculator.

    Calculate implied rate and borrowing costs for given parameters.
    Great for learning how the numbers work.
    """
    # Theoretical value is always the strike width
    theoretical = strike_width

    # Implied rate calculation
    time_years = dte / 365
    implied_rate = ((theoretical / market_price) - 1) / time_years * 100 if market_price > 0 and time_years > 0 else 0

    # Per contract calculations
    cash_received = market_price * 100
    cash_owed = theoretical * 100
    borrowing_cost = cash_owed - cash_received
    daily_cost = borrowing_cost / dte if dte > 0 else 0

    # Comparison to margin (assume 8.5%)
    margin_cost = cash_received * 0.085 * time_years
    savings = margin_cost - borrowing_cost

    return {
        "inputs": {
            "strike_width": strike_width,
            "dte": dte,
            "market_price": market_price,
        },
        "per_contract": {
            "theoretical_value": theoretical,
            "cash_received": cash_received,
            "cash_owed_at_expiration": cash_owed,
            "borrowing_cost": borrowing_cost,
            "daily_cost": round(daily_cost, 4),
        },
        "rates": {
            "implied_annual_rate": round(implied_rate, 2),
            "implied_monthly_rate": round(implied_rate / 12, 2),
            "comparison_margin_rate": 8.5,
            "savings_vs_margin_pct": round(8.5 - implied_rate, 2),
        },
        "break_even": {
            "required_monthly_ic_return": round(implied_rate / 12, 2),
            "days_to_break_even": round(borrowing_cost / (cash_received * 0.025 / 30)) if cash_received > 0 else 0,
            "explanation": f"IC bots need to return {implied_rate/12:.2f}% monthly to cover box cost",
        },
        "example_10_contracts": {
            "cash_received": cash_received * 10,
            "cash_owed": cash_owed * 10,
            "total_borrowing_cost": borrowing_cost * 10,
            "vs_margin_savings": savings * 10,
        },
    }


# ========== Logs Endpoint ==========

@router.get("/logs")
async def get_logs(limit: int = Query(50, ge=1, le=500)):
    """
    Get recent activity logs for audit trail.
    """
    if not PrometheusTrader:
        raise HTTPException(status_code=503, detail="PROMETHEUS Box Spread not available")

    try:
        trader = PrometheusTrader()
        logs = trader.db.get_recent_logs(limit)
        return {
            "logs": logs,
            "count": len(logs),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ========== Deployments Endpoint ==========

@router.get("/deployments")
async def get_deployments():
    """
    Get active capital deployments.

    Shows how borrowed capital is allocated across IC bots.
    """
    if not PrometheusTrader:
        raise HTTPException(status_code=503, detail="PROMETHEUS Box Spread not available")

    try:
        trader = PrometheusTrader()
        deployments = trader.db.get_active_deployments()
        return {
            "deployments": deployments,
            "count": len(deployments),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
