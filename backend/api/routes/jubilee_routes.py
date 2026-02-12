"""
JUBILEE Box Spread API Routes - Synthetic Borrowing System

Comprehensive API for the JUBILEE box spread system with
enhanced educational endpoints for learning the strategy.

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

router = APIRouter(prefix="/api/jubilee", tags=["JUBILEE Box Spread - Synthetic Borrowing"])

# Import JUBILEE Box Spread components with fallback
JubileeTrader = None
JubileeConfig = None
TradingMode = None

try:
    from trading.jubilee import (
        JubileeTrader,
        JubileeConfig,
        TradingMode,
    )
    logger.info("JUBILEE Box Spread modules loaded successfully")
except ImportError as e:
    logger.warning(f"JUBILEE Box Spread modules not available: {e}")

# Dynamic rate fetching
RateFetcher = None
try:
    from trading.jubilee.rate_fetcher import get_current_rates, get_rate_fetcher
    RateFetcher = get_rate_fetcher
    logger.info("Rate fetcher loaded successfully")
except ImportError as e:
    logger.warning(f"Rate fetcher not available: {e}")


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
    fortress_allocation_pct: Optional[float] = Field(None, description="% to deploy to FORTRESS")
    samson_allocation_pct: Optional[float] = Field(None, description="% to deploy to SAMSON")
    anchor_allocation_pct: Optional[float] = Field(None, description="% to deploy to ANCHOR")
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
async def get_jubilee_status():
    """
    Get comprehensive JUBILEE Box Spread system status.

    Returns:
    - System status (ACTIVE, PAUSED, MARGIN_WARNING, etc.)
    - Open positions count and value
    - Total borrowed and deployed amounts
    - Net P&L from IC returns vs borrowing costs
    - Configuration summary
    """
    if not JubileeTrader:
        raise HTTPException(status_code=503, detail="JUBILEE Box Spread not available")

    try:
        trader = JubileeTrader()
        return trader.get_status()
    except Exception as e:
        logger.error(f"Error getting JUBILEE Box status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def jubilee_health_check():
    """
    Health check for JUBILEE Box Spread system.

    Verifies:
    - Database connectivity
    - Module availability
    - Configuration validity
    """
    health = {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "bot_name": "JUBILEE",
        "bot_type": "Box Spread Synthetic Borrowing",
        "checks": {
            "trader_available": JubileeTrader is not None,
            "config_available": JubileeConfig is not None,
        }
    }

    if not JubileeTrader:
        health["status"] = "degraded"
        health["message"] = "JUBILEE Box Spread trader not available"

    return health


@router.get("/config")
async def get_config():
    """
    Get current JUBILEE Box Spread configuration.

    Returns all configuration parameters with explanations.
    """
    if not JubileeTrader:
        raise HTTPException(status_code=503, detail="JUBILEE Box Spread not available")

    try:
        trader = JubileeTrader()
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
    Update JUBILEE Box Spread configuration.

    Only provided fields will be updated.
    """
    if not JubileeTrader:
        raise HTTPException(status_code=503, detail="JUBILEE Box Spread not available")

    try:
        trader = JubileeTrader()
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
    if not JubileeTrader:
        raise HTTPException(status_code=503, detail="JUBILEE Box Spread not available")

    try:
        trader = JubileeTrader()
        positions = trader.get_positions()

        return {
            "positions": positions,
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
    if not JubileeTrader:
        raise HTTPException(status_code=503, detail="JUBILEE Box Spread not available")

    try:
        trader = JubileeTrader()
        position = trader.db.get_position(position_id)

        if not position:
            raise HTTPException(status_code=404, detail="Position not found")

        return position.to_dict()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/closed-trades")
async def get_closed_trades(limit: int = Query(100, ge=1, le=500)):
    """
    Get closed box spread positions (trade history).

    Returns closed positions with realized P&L, matching STANDARDS.md requirements.
    Each closed trade includes:
    - Position details (strikes, expiration, contracts)
    - Borrowing cost analysis (implied rate, total cost)
    - IC returns from deployed capital
    - Final realized P&L (net profit)
    - Close time and reason
    """
    if not JubileeTrader:
        raise HTTPException(status_code=503, detail="JUBILEE Box Spread not available")

    try:
        trader = JubileeTrader()
        closed = trader.db.get_closed_positions(limit)

        # Format dates for JSON serialization
        for trade in closed:
            if trade.get('open_time'):
                trade['open_time'] = trade['open_time'].isoformat() if hasattr(trade['open_time'], 'isoformat') else str(trade['open_time'])
            if trade.get('close_time'):
                trade['close_time'] = trade['close_time'].isoformat() if hasattr(trade['close_time'], 'isoformat') else str(trade['close_time'])
            if trade.get('expiration'):
                trade['expiration'] = str(trade['expiration'])

        return {
            "closed_trades": closed,
            "count": len(closed),
        }
    except Exception as e:
        logger.error(f"Error getting closed trades: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scan-activity")
async def get_scan_activity(limit: int = Query(50, ge=1, le=200)):
    """
    Get scan activity history (alias for signals/recent).

    Returns signal scan history matching STANDARDS.md bot requirements.
    Each scan includes signal details and whether it was executed.
    """
    if not JubileeTrader:
        raise HTTPException(status_code=503, detail="JUBILEE Box Spread not available")

    try:
        trader = JubileeTrader()
        signals = trader.db.get_recent_signals(limit)
        return {
            "scans": signals,
            "count": len(signals),
        }
    except Exception as e:
        logger.error(f"Error getting scan activity: {e}")
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
    if not JubileeTrader:
        raise HTTPException(status_code=503, detail="JUBILEE Box Spread not available")

    try:
        trader = JubileeTrader()
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
    if not JubileeTrader:
        raise HTTPException(status_code=503, detail="JUBILEE Box Spread not available")

    try:
        trader = JubileeTrader()
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
    if not JubileeTrader:
        raise HTTPException(status_code=503, detail="JUBILEE Box Spread not available")

    try:
        trader = JubileeTrader()
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
    if not JubileeTrader:
        raise HTTPException(status_code=503, detail="JUBILEE Box Spread not available")

    try:
        trader = JubileeTrader()
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
    if not JubileeTrader:
        raise HTTPException(status_code=503, detail="JUBILEE Box Spread not available")

    try:
        trader = JubileeTrader()

        # First, generate a fresh signal
        scan_result = trader.run_signal_scan()
        if not scan_result.get('should_trade'):
            return {
                "success": False,
                "message": scan_result.get('reason', 'No valid signal'),
            }

        # Get the signal and execute
        from trading.jubilee.models import BoxSpreadSignal
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
    if not JubileeTrader:
        raise HTTPException(status_code=503, detail="JUBILEE Box Spread not available")

    try:
        trader = JubileeTrader()
        return trader.get_rate_analysis()
    except Exception as e:
        # Return fallback rates when live data unavailable
        from datetime import datetime
        logger.warning(f"Rate analysis failed, returning estimates: {e}")
        return {
            "analysis_time": datetime.now().isoformat(),
            "box_implied_rate": 4.5,
            "fed_funds_rate": 4.38,  # Current FOMC target midpoint (4.25-4.50%)
            "sofr_rate": 4.35,
            "broker_margin_rate": 8.38,  # Fed Funds + 4%
            "spread_to_fed_funds": 0.12,
            "spread_to_margin": -3.88,
            "cost_per_100k_monthly": 375.0,
            "cost_per_100k_annual": 4500.0,
            "required_ic_return_monthly": 0.375,
            "current_ic_return_estimate": 2.5,
            "projected_profit_per_100k": 2125.0,
            "avg_box_rate_30d": 4.5,
            "avg_box_rate_90d": 4.5,
            "rate_trend": "STABLE",
            "is_favorable": True,
            "recommendation": "FAVORABLE - Box spread rates estimated at 4.5%",
            "reasoning": "Live market data unavailable - using estimated rates based on FOMC target range (4.25-4.50%).",
            # CRITICAL: Include these fields - frontend expects them
            "rates_source": "fallback",
            "rates_last_updated": datetime.now().isoformat(),
            "data_source": "estimated",
            "error": str(e),
        }


@router.get("/analytics/rates/history")
async def get_rate_history(days: int = Query(30, ge=1, le=365)):
    """
    Get historical rate analysis for trend analysis.
    """
    if not JubileeTrader:
        raise HTTPException(status_code=503, detail="JUBILEE Box Spread not available")

    try:
        trader = JubileeTrader()
        history = trader.db.get_rate_history(days)
        return {
            "history": history,
            "count": len(history),
            "days_requested": days,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analytics/interest-rates")
async def get_interest_rates():
    """
    Get current interest rates from live sources.

    Returns Fed Funds, SOFR, Treasury rates, and estimated margin rate.
    Rates are cached for 4 hours and fetched from FRED/Treasury APIs.
    """
    if RateFetcher:
        try:
            fetcher = RateFetcher()
            rates = fetcher.get_rates()
            return {
                "fed_funds_rate": rates.fed_funds_rate,
                "sofr_rate": rates.sofr_rate,
                "treasury_3m": rates.treasury_3m,
                "treasury_1y": rates.treasury_1y,
                "margin_rate": rates.margin_rate,
                "last_updated": rates.last_updated.isoformat(),
                "source": rates.source,
                "cache_hours": 4,
                "description": {
                    "fed_funds_rate": "Federal Funds Effective Rate - overnight bank lending rate",
                    "sofr_rate": "Secured Overnight Financing Rate - repo market rate",
                    "treasury_3m": "3-Month Treasury Bill yield",
                    "treasury_1y": "1-Year Treasury Bill yield",
                    "margin_rate": "Estimated broker margin rate (Fed Funds + 4%)",
                },
            }
        except Exception as e:
            logger.warning(f"Rate fetcher error: {e}")

    # Fallback - use FOMC target midpoint (4.25-4.50% as of Jan 2026)
    return {
        "fed_funds_rate": 4.38,  # FOMC midpoint
        "sofr_rate": 4.35,
        "treasury_3m": 4.30,
        "treasury_1y": 4.25,
        "margin_rate": 8.38,  # Fed Funds + 4%
        "last_updated": datetime.now().isoformat(),
        "source": "fomc_based",  # More accurate than generic "fallback"
        "cache_hours": 4,
        "note": "Using FOMC target range (4.25-4.50%) - Rate fetcher not available",
    }


@router.post("/analytics/interest-rates/refresh")
async def refresh_interest_rates():
    """
    Force refresh of interest rates from live sources.

    Bypasses the 4-hour cache and fetches fresh data.
    """
    if RateFetcher:
        try:
            fetcher = RateFetcher()
            rates = fetcher.get_rates(force_refresh=True)
            return {
                "status": "refreshed",
                "fed_funds_rate": rates.fed_funds_rate,
                "sofr_rate": rates.sofr_rate,
                "treasury_3m": rates.treasury_3m,
                "treasury_1y": rates.treasury_1y,
                "margin_rate": rates.margin_rate,
                "last_updated": rates.last_updated.isoformat(),
                "source": rates.source,
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Rate refresh failed: {e}")

    raise HTTPException(status_code=503, detail="Rate fetcher not available")


@router.get("/analytics/capital-flow")
async def get_capital_flow():
    """
    Get capital flow analysis.

    Shows how box spread cash is deployed across IC bots
    and the returns generated by each.
    """
    if not JubileeTrader:
        raise HTTPException(status_code=503, detail="JUBILEE Box Spread not available")

    try:
        trader = JubileeTrader()
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
    if not JubileeTrader:
        raise HTTPException(status_code=503, detail="JUBILEE Box Spread not available")

    try:
        trader = JubileeTrader()
        return trader.db.get_performance_summary()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/equity-curve")
async def get_equity_curve(
    limit: int = Query(100, ge=1, le=500),
    days: int = Query(None, ge=0, le=365, description="Filter to last N days. 0=today, None=all history")
):
    """
    Get historical equity curve data.

    Supports timeframe filtering for chart display (matching VALOR):
    - days=0: Today only (intraday)
    - days=7: Last 7 days
    - days=30: Last 30 days
    - days=90: Last 90 days
    - days=None: All history (default)
    """
    if not JubileeTrader:
        raise HTTPException(status_code=503, detail="JUBILEE Box Spread not available")

    try:
        trader = JubileeTrader()
        curve = trader.db.get_equity_curve(limit=limit, days=days)
        return {
            "equity_curve": curve,
            "count": len(curve),
            "days": days,
            "starting_capital": trader.db.get_starting_capital(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/equity-curve/intraday")
async def get_intraday_equity():
    """
    Get today's equity snapshots for intraday tracking.
    """
    if not JubileeTrader:
        raise HTTPException(status_code=503, detail="JUBILEE Box Spread not available")

    try:
        trader = JubileeTrader()
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
    Run the daily JUBILEE cycle.

    This updates all positions:
    - Recalculates DTE
    - Accrues borrowing costs
    - Fetches IC bot returns
    - Checks for roll opportunities
    - Records equity snapshot
    """
    if not JubileeTrader:
        raise HTTPException(status_code=503, detail="JUBILEE Box Spread not available")

    try:
        trader = JubileeTrader()
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
    if not JubileeTrader:
        raise HTTPException(status_code=503, detail="JUBILEE Box Spread not available")

    try:
        trader = JubileeTrader()
        return trader.generate_daily_briefing()
    except Exception as e:
        # Return a basic briefing when full generation fails
        from datetime import datetime, date
        logger.warning(f"Daily briefing generation failed, returning basic briefing: {e}")

        # Get basic position info that doesn't require live market data
        try:
            trader = JubileeTrader()
            positions = trader.db.get_open_positions()
            total_borrowed = sum(p.total_credit_received for p in positions)
            total_deployed = sum(p.total_cash_deployed for p in positions)
            total_returns = sum(p.total_ic_returns for p in positions)
            total_costs = sum(p.cost_accrued_to_date for p in positions)
        except Exception:
            positions = []
            total_borrowed = 0
            total_deployed = 0
            total_returns = 0
            total_costs = 0

        tips = [
            "Box spreads work best on European-style options (SPX) to avoid early assignment.",
            "The implied rate should be compared to your broker's margin rate to assess value.",
            "Longer-dated box spreads typically have better (lower) implied rates.",
        ]
        daily_tip = tips[date.today().timetuple().tm_yday % len(tips)]

        return {
            "briefing_date": date.today().isoformat(),
            "briefing_time": datetime.now().isoformat(),
            "system_status": "OPERATIONAL" if len(positions) > 0 else "IDLE",
            "total_open_positions": len(positions),
            "total_borrowed_amount": total_borrowed,
            "total_cash_deployed": total_deployed,
            "total_margin_used": 0,
            "margin_remaining": 500000,
            "total_borrowing_cost_to_date": total_costs,
            "average_borrowing_rate": 4.5,
            "comparison_to_margin_rate": 4.0,
            "total_ic_returns_to_date": total_returns,
            "net_profit_to_date": total_returns - total_costs,
            "roi_on_strategy": (total_returns - total_costs) / total_borrowed * 100 if total_borrowed > 0 else 0,
            "highest_assignment_risk_position": "",
            "days_until_nearest_expiration": 999,
            "current_box_rate": 4.5,
            "rate_vs_yesterday": 0,
            "rate_trend_7d": "STABLE",
            "recommended_actions": [],
            "warnings": [],
            "daily_tip": daily_tip,
            "data_source": "basic",
            "error": str(e),
        }


@router.post("/operations/equity-snapshot")
async def record_equity_snapshot():
    """
    Manually record an equity snapshot.

    Normally called automatically during daily cycle.
    """
    if not JubileeTrader:
        raise HTTPException(status_code=503, detail="JUBILEE Box Spread not available")

    try:
        trader = JubileeTrader()
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
                "description": "Introduction to box spreads and the JUBILEE strategy",
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


# NOTE: Calculator endpoint MUST come BEFORE {topic} route to avoid being captured as a topic
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
    if not JubileeTrader:
        raise HTTPException(status_code=503, detail="JUBILEE Box Spread not available")

    try:
        trader = JubileeTrader()
        content = trader.get_education_content(topic)
        return content
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ========== Logs Endpoint ==========

@router.get("/logs")
async def get_logs(limit: int = Query(50, ge=1, le=500)):
    """
    Get recent activity logs for audit trail.
    """
    if not JubileeTrader:
        raise HTTPException(status_code=503, detail="JUBILEE Box Spread not available")

    try:
        trader = JubileeTrader()
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
    if not JubileeTrader:
        raise HTTPException(status_code=503, detail="JUBILEE Box Spread not available")

    try:
        trader = JubileeTrader()
        deployments = trader.db.get_active_deployments()
        return {
            "deployments": deployments,
            "count": len(deployments),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ========== Mark-to-Market & Transparency Endpoints ==========

@router.get("/positions/{position_id}/mtm")
async def get_position_mark_to_market(position_id: str):
    """
    Get real-time mark-to-market valuation for a position.

    TRANSPARENCY FEATURES:
    - Uses PRODUCTION Tradier quotes for accurate pricing
    - Shows current vs entry implied rate
    - Includes exact quote timestamps
    - Details unrealized P&L from box spread value changes

    This endpoint uses the same quotes that would be used in live trading,
    making paper trading "as real as possible".
    """
    if not JubileeTrader:
        raise HTTPException(status_code=503, detail="JUBILEE Box Spread not available")

    try:
        trader = JubileeTrader()
        mtm = trader.executor.get_position_mark_to_market(position_id)
        return mtm
    except Exception as e:
        logger.error(f"Error getting MTM for {position_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/positions/{position_id}/roll-decision")
async def get_roll_decision(position_id: str):
    """
    Get detailed roll decision analysis for a position.

    FULL TRANSPARENCY on roll timing:
    - Exact dates when roll threshold will be reached
    - Recommended roll window (earliest, optimal, latest)
    - Current rate comparison to entry rate
    - Estimated roll costs
    - Educational explanation of roll process

    This helps you understand exactly WHEN you need to act and WHY.
    """
    if not JubileeTrader:
        raise HTTPException(status_code=503, detail="JUBILEE Box Spread not available")

    try:
        trader = JubileeTrader()
        position = trader.db.get_position(position_id)

        if not position:
            raise HTTPException(status_code=404, detail="Position not found")

        roll_decision = trader.executor.check_roll_decision(position)
        return roll_decision
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting roll decision for {position_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/quotes/live")
async def get_live_box_spread_quotes(
    ticker: str = Query("SPX", description="Underlying symbol (SPX, XSP)"),
    lower_strike: float = Query(..., description="Lower strike price"),
    upper_strike: float = Query(..., description="Upper strike price"),
    expiration: str = Query(..., description="Expiration date YYYY-MM-DD"),
):
    """
    Get live box spread quotes from Tradier PRODUCTION API.

    IMPORTANT - SPX Quote Strategy:
    - SPX quotes require PRODUCTION Tradier API (sandbox doesn't provide them)
    - This endpoint always uses production quotes for accuracy
    - Quotes are cached for 30 seconds to reduce API calls

    Returns:
    - Individual leg quotes (bid/ask/last for each option)
    - Calculated box spread bid/ask/mid
    - Current implied borrowing rate
    - Quote source and timestamp
    """
    if not JubileeTrader:
        raise HTTPException(status_code=503, detail="JUBILEE Box Spread not available")

    try:
        from trading.jubilee.executor import get_box_spread_quotes

        result = get_box_spread_quotes(
            ticker=ticker,
            expiration=expiration,
            lower_strike=lower_strike,
            upper_strike=upper_strike,
            use_cache=True
        )
        return result
    except Exception as e:
        logger.error(f"Error getting live quotes: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/operations/equity-snapshot-mtm")
async def record_equity_snapshot_with_mtm():
    """
    Record equity snapshot with REAL mark-to-market quotes.

    ENHANCED TRANSPARENCY:
    - Uses PRODUCTION Tradier quotes for each position
    - Records quote source (tradier_production, cache, simulated)
    - Includes per-position MTM breakdown
    - Shows current implied rates vs entry rates

    This provides the most accurate equity curve possible for paper trading.
    """
    if not JubileeTrader:
        raise HTTPException(status_code=503, detail="JUBILEE Box Spread not available")

    try:
        trader = JubileeTrader()
        success = trader.db.record_equity_snapshot(use_real_quotes=True)
        return {
            "success": success,
            "message": "Equity snapshot recorded with real MTM quotes" if success else "Failed to record snapshot",
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"Error recording MTM equity snapshot: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/transparency/summary")
async def get_transparency_summary():
    """
    Get comprehensive transparency summary.

    Shows all the "under the hood" details:
    - Quote sources being used (production vs simulated)
    - MTM calculation methods
    - Interest accrual schedule
    - Roll timing for each position
    - API availability status

    This endpoint helps you understand exactly how the system works.
    """
    if not JubileeTrader:
        return {
            "available": False,
            "message": "JUBILEE Box Spread not available",
        }

    try:
        import os
        trader = JubileeTrader()
        positions = trader.get_positions()

        # Check API availability
        prod_key_set = bool(os.environ.get('TRADIER_PROD_API_KEY') or os.environ.get('TRADIER_API_KEY'))

        # Calculate roll schedule for all positions
        roll_schedule = []
        for pos_dict in positions:
            position = trader.db.get_position(pos_dict['position_id'])
            if position:
                roll_decision = trader.executor.check_roll_decision(position)
                roll_schedule.append({
                    'position_id': position.position_id,
                    'expiration': position.expiration,
                    'current_dte': roll_decision['current_dte'],
                    'roll_threshold_date': roll_decision['roll_threshold_date'],
                    'days_until_roll': roll_decision['days_until_roll_threshold'],
                    'urgency': roll_decision['urgency'],
                })

        return {
            "available": True,
            "mode": trader.config.mode.value,
            "timestamp": datetime.now().isoformat(),

            "quote_configuration": {
                "production_api_configured": prod_key_set,
                "quote_source": "tradier_production" if prod_key_set else "simulated",
                "cache_ttl_seconds": 30,
                "notes": "SPX quotes REQUIRE Tradier production API - sandbox does not provide them",
            },

            "mtm_configuration": {
                "method": "real_quotes" if prod_key_set else "theoretical",
                "pricing_basis": "mid_price",
                "update_frequency": "on_demand_or_daily_cycle",
            },

            "interest_accrual": {
                "method": "linear_daily",
                "accrual_time": "daily_at_market_open",
                "formula": "daily_cost = borrowing_cost / dte_at_entry",
            },

            "roll_schedule": roll_schedule,

            "educational_features": {
                "educational_mode": trader.config.educational_mode,
                "position_explanations": True,
                "daily_briefings": True,
                "calculator_available": True,
            },
        }
    except Exception as e:
        logger.error(f"Error getting transparency summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==============================================================================
# JUBILEE IC TRADING ENDPOINTS
# ==============================================================================
# These endpoints handle the Iron Condor trading side of JUBILEE - trading
# with borrowed capital from box spreads to generate returns.
# ==============================================================================

# Import IC components
JubileeICTrader = None
JubileeICConfig = None
try:
    from trading.jubilee.trader import JubileeICTrader
    from trading.jubilee.models import JubileeICConfig, ICPositionStatus
    logger.info("JUBILEE IC Trader modules loaded successfully")
except ImportError as e:
    logger.warning(f"JUBILEE IC Trader modules not available: {e}")


# ========== IC Pydantic Models ==========

class ICConfigUpdateRequest(BaseModel):
    """Request model for IC configuration updates"""
    enabled: Optional[bool] = Field(None, description="Enable/disable IC trading")
    ticker: Optional[str] = Field(None, description="Underlying to trade (SPX)")
    spread_width: Optional[float] = Field(None, description="IC spread width")
    short_put_delta: Optional[float] = Field(None, description="Target delta for short put")
    short_call_delta: Optional[float] = Field(None, description="Target delta for short call")
    max_positions: Optional[int] = Field(None, description="Max concurrent IC positions")
    max_trades_per_day: Optional[int] = Field(None, description="Max daily IC trades")
    require_oracle_approval: Optional[bool] = Field(None, description="Require Prophet approval")
    min_oracle_confidence: Optional[float] = Field(None, description="Min Prophet confidence")
    stop_loss_pct: Optional[float] = Field(None, description="Stop loss % of max loss")
    profit_target_pct: Optional[float] = Field(None, description="Profit target % of max profit")


class ICClosePositionRequest(BaseModel):
    """Request to close an IC position"""
    position_id: str = Field(..., description="IC position ID to close")
    reason: str = Field("manual", description="Reason for closing")


# ========== IC Status & Configuration ==========

@router.get("/ic/status")
async def get_ic_status():
    """
    Get comprehensive JUBILEE IC trading status.

    Returns:
    - Trading enabled/disabled
    - Open positions and unrealized P&L
    - Performance metrics
    - Available capital for new trades
    """
    if not JubileeICTrader:
        raise HTTPException(status_code=503, detail="JUBILEE IC Trader not available")

    try:
        trader = JubileeICTrader()
        status = trader.get_status()
        return {
            "available": True,
            "status": status,
        }
    except Exception as e:
        logger.error(f"Error getting IC status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ic/config")
async def get_ic_config():
    """Get current IC trading configuration"""
    if not JubileeICTrader:
        raise HTTPException(status_code=503, detail="JUBILEE IC Trader not available")

    try:
        trader = JubileeICTrader()
        return {
            "available": True,
            "config": trader.config.to_dict() if hasattr(trader.config, 'to_dict') else {
                'enabled': trader.config.enabled,
                'mode': trader.config.mode.value,
                'ticker': trader.config.ticker,
                'spread_width': trader.config.spread_width,
                'short_put_delta': trader.config.short_put_delta,
                'short_call_delta': trader.config.short_call_delta,
                'max_positions': trader.config.max_positions,
                'max_trades_per_day': trader.config.max_trades_per_day,
                'require_oracle_approval': trader.config.require_oracle_approval,
                'min_oracle_confidence': trader.config.min_oracle_confidence,
                'stop_loss_pct': trader.config.stop_loss_pct,
                'profit_target_pct': trader.config.profit_target_pct,
            },
        }
    except Exception as e:
        logger.error(f"Error getting IC config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ic/config")
async def update_ic_config(request: ICConfigUpdateRequest):
    """Update IC trading configuration"""
    if not JubileeICTrader:
        raise HTTPException(status_code=503, detail="JUBILEE IC Trader not available")

    try:
        trader = JubileeICTrader()
        updates = request.dict(exclude_none=True)

        # Apply updates to config
        for key, value in updates.items():
            if hasattr(trader.config, key):
                setattr(trader.config, key, value)

        # Save to database
        trader.db.save_ic_config(trader.config)

        return {
            "success": True,
            "updated_fields": list(updates.keys()),
            "config": trader.config.to_dict() if hasattr(trader.config, 'to_dict') else updates,
        }
    except Exception as e:
        logger.error(f"Error updating IC config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ic/config/reset-aggressive")
async def reset_ic_config_aggressive():
    """
    Reset IC config to AGGRESSIVE defaults (matching ANCHOR).

    This overwrites the stored config with:
    - spread_width: $10 (was $25)
    - max_contracts: 50 (was 10)
    - max_daily_trades: 0 (unlimited)
    - max_positions: 5
    - max_capital_per_trade_pct: 10%

    Use this when trades are showing 1 contract instead of expected 50.
    """
    if not JubileeICTrader:
        raise HTTPException(status_code=503, detail="JUBILEE IC Trader not available")

    try:
        from trading.jubilee.models import JubileeICConfig

        # Create fresh config with aggressive defaults
        aggressive_config = JubileeICConfig()

        # Explicitly set aggressive values to ensure they're not overridden
        aggressive_config.spread_width = 10.0      # Match ANCHOR
        aggressive_config.max_contracts = 50       # Raised from 10
        aggressive_config.max_daily_trades = 0     # UNLIMITED
        aggressive_config.max_positions = 5        # Same as ANCHOR
        aggressive_config.max_capital_per_trade_pct = 10.0

        # Save to database
        trader = JubileeICTrader()
        trader.db.save_ic_config(aggressive_config)

        return {
            "success": True,
            "message": "IC config reset to AGGRESSIVE defaults",
            "config": {
                "spread_width": aggressive_config.spread_width,
                "max_contracts": aggressive_config.max_contracts,
                "max_daily_trades": "UNLIMITED" if aggressive_config.max_daily_trades == 0 else aggressive_config.max_daily_trades,
                "max_positions": aggressive_config.max_positions,
                "max_capital_per_trade_pct": aggressive_config.max_capital_per_trade_pct,
            },
            "expected_sizing": "With $500K capital @ 10% risk and $10 spreads: ~50 contracts per trade"
        }
    except Exception as e:
        logger.error(f"Error resetting IC config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ========== IC Positions ==========

@router.get("/ic/positions")
async def get_ic_positions():
    """
    Get all open IC positions with current metrics.

    Each position includes:
    - Strikes and expiration
    - Entry credit and current value
    - Unrealized P&L
    - Prophet confidence at entry
    """
    if not JubileeICTrader:
        raise HTTPException(status_code=503, detail="JUBILEE IC Trader not available")

    try:
        trader = JubileeICTrader()
        positions = trader.get_positions()
        return {
            "available": True,
            "count": len(positions),
            "positions": positions,
        }
    except Exception as e:
        logger.error(f"Error getting IC positions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ic/positions/{position_id}")
async def get_ic_position(position_id: str):
    """Get a specific IC position by ID"""
    if not JubileeICTrader:
        raise HTTPException(status_code=503, detail="JUBILEE IC Trader not available")

    try:
        trader = JubileeICTrader()
        position = trader.db.get_ic_position(position_id)

        if not position:
            raise HTTPException(status_code=404, detail="Position not found")

        return {
            "available": True,
            "position": trader._position_to_dict(position),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting IC position: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ic/positions/close")
async def close_ic_position(request: ICClosePositionRequest):
    """Manually close an IC position"""
    if not JubileeICTrader:
        raise HTTPException(status_code=503, detail="JUBILEE IC Trader not available")

    try:
        trader = JubileeICTrader()
        result = trader.close_position(request.position_id, request.reason)
        return result
    except Exception as e:
        logger.error(f"Error closing IC position: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ========== IC Closed Trades & Performance ==========

@router.get("/ic/closed-trades")
async def get_ic_closed_trades(limit: int = Query(50, ge=1, le=500)):
    """Get closed IC trade history"""
    if not JubileeICTrader:
        raise HTTPException(status_code=503, detail="JUBILEE IC Trader not available")

    try:
        trader = JubileeICTrader()
        trades = trader.get_closed_trades(limit)
        return {
            "available": True,
            "count": len(trades),
            "trades": trades,
        }
    except Exception as e:
        logger.error(f"Error getting closed IC trades: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ic/performance")
async def get_ic_performance():
    """
    Get IC trading performance metrics.

    Includes:
    - Win rate and total P&L
    - Average win/loss amounts
    - Profit factor
    - Today's stats
    - Streak information
    """
    if not JubileeICTrader:
        raise HTTPException(status_code=503, detail="JUBILEE IC Trader not available")

    try:
        trader = JubileeICTrader()
        performance = trader.db.get_ic_performance()
        return {
            "available": True,
            "performance": performance,
        }
    except Exception as e:
        logger.error(f"Error getting IC performance: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ic/equity-curve")
async def get_ic_equity_curve(
    limit: int = Query(100, ge=1, le=500),
    days: int = Query(None, ge=0, le=365, description="Filter to last N days. 0=today, None=all history")
):
    """
    Get IC trading equity curve data.

    Supports timeframe filtering for chart display:
    - days=0: Today only (intraday)
    - days=7: Last 7 days
    - days=30: Last 30 days
    - days=90: Last 90 days
    - days=None: All history (default)
    """
    if not JubileeICTrader:
        raise HTTPException(status_code=503, detail="JUBILEE IC Trader not available")

    try:
        trader = JubileeICTrader()
        # Get starting capital for response
        ic_config = trader.db.load_ic_config()
        starting_capital = ic_config.starting_capital

        curve = trader.db.get_ic_equity_curve(limit=limit, days=days)
        return {
            "available": True,
            "count": len(curve),
            "days": days,
            "starting_capital": starting_capital,
            "data": curve,
        }
    except Exception as e:
        logger.error(f"Error getting IC equity curve: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ic/equity-curve/intraday")
async def get_ic_intraday_equity():
    """
    Get today's IC equity snapshots for intraday tracking.

    STANDARDS.md COMPLIANCE:
    - Returns intraday equity snapshots for current trading day
    - Includes unrealized P&L from open positions
    - Required endpoint per Bot-Specific Requirements
    """
    if not JubileeICTrader:
        raise HTTPException(status_code=503, detail="JUBILEE IC Trader not available")

    try:
        trader = JubileeICTrader()
        snapshots = trader.db.get_ic_intraday_equity()
        return {
            "available": True,
            "date": date.today().isoformat(),
            "count": len(snapshots),
            "snapshots": snapshots,
        }
    except Exception as e:
        logger.error(f"Error getting IC intraday equity: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ic/logs")
async def get_ic_logs(limit: int = Query(50, ge=1, le=500)):
    """
    Get recent IC trading activity logs.

    STANDARDS.md COMPLIANCE:
    - Returns activity log for IC trading actions
    - Required endpoint per Bot-Specific Requirements
    """
    if not JubileeICTrader:
        raise HTTPException(status_code=503, detail="JUBILEE IC Trader not available")

    try:
        trader = JubileeICTrader()
        logs = trader.db.get_recent_ic_logs(limit)
        return {
            "available": True,
            "count": len(logs),
            "logs": logs,
        }
    except Exception as e:
        logger.error(f"Error getting IC logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ========== IC Signals ==========

@router.get("/ic/signals/recent")
async def get_recent_ic_signals(limit: int = Query(50, ge=1, le=200)):
    """Get recent IC trading signals (both executed and skipped)"""
    if not JubileeICTrader:
        raise HTTPException(status_code=503, detail="JUBILEE IC Trader not available")

    try:
        trader = JubileeICTrader()
        signals = trader.db.get_recent_ic_signals(limit)
        return {
            "available": True,
            "count": len(signals),
            "signals": signals,
        }
    except Exception as e:
        logger.error(f"Error getting IC signals: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ========== IC Operations ==========

@router.post("/ic/operations/run-cycle")
async def run_ic_trading_cycle():
    """
    Manually trigger an IC trading cycle.

    This will:
    1. Check exit conditions on all open positions
    2. Generate new signals if capital is available
    3. Execute approved signals
    """
    if not JubileeICTrader:
        raise HTTPException(status_code=503, detail="JUBILEE IC Trader not available")

    try:
        trader = JubileeICTrader()
        result = trader.run_trading_cycle()
        return {
            "available": True,
            "result": result,
        }
    except Exception as e:
        logger.error(f"Error running IC cycle: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ic/operations/update-mtm")
async def update_ic_mtm():
    """
    Update mark-to-market for all open IC positions.

    Uses real-time Tradier production quotes to calculate
    current values and unrealized P&L.
    """
    if not JubileeICTrader:
        raise HTTPException(status_code=503, detail="JUBILEE IC Trader not available")

    try:
        from trading.jubilee.trader import run_jubilee_ic_mtm_update
        result = run_jubilee_ic_mtm_update()
        return {
            "available": True,
            "result": result,
        }
    except Exception as e:
        logger.error(f"Error updating IC MTM: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ========== Combined Performance ==========

@router.get("/combined/performance")
async def get_combined_performance():
    """
    Get combined performance for both box spreads and IC trading.

    This is the key metric: Are IC returns > borrowing costs?

    Returns:
    - Box spread borrowing metrics
    - IC trading performance
    - Net profit calculation
    - ROI on borrowed capital
    """
    if not JubileeTrader or not JubileeICTrader:
        raise HTTPException(status_code=503, detail="JUBILEE modules not available")

    try:
        from trading.jubilee.db import JubileeDatabase
        db = JubileeDatabase()
        summary = db.get_combined_performance_summary()

        return {
            "available": True,
            "summary": {
                "summary_time": summary.summary_time.isoformat() if summary.summary_time else None,
                # Box Spread Metrics
                "box_spread": {
                    "total_positions": summary.total_box_positions,
                    "total_borrowed": summary.total_borrowed,
                    "total_borrowing_cost": summary.total_borrowing_cost,
                    "average_borrowing_rate": summary.average_borrowing_rate,
                },
                # IC Trading Metrics
                "ic_trading": {
                    "total_trades": summary.total_ic_trades,
                    "win_rate": summary.ic_win_rate,
                    "total_premium_collected": summary.total_ic_premium_collected,
                    "total_realized_pnl": summary.total_ic_realized_pnl,
                    "total_unrealized_pnl": summary.total_ic_unrealized_pnl,
                    "avg_return_per_trade": summary.average_ic_return_per_trade,
                },
                # Combined
                "net_profit": summary.net_profit,
                "roi_on_borrowed_capital": summary.roi_on_borrowed_capital,
                "monthly_return_rate": summary.monthly_return_rate,
                "vs_margin_borrowing_savings": summary.vs_margin_borrowing,
            },
        }
    except Exception as e:
        logger.error(f"Error getting combined performance: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/daily-pnl")
async def get_daily_pnl(days: int = Query(30, ge=1, le=90)):
    """
    Get daily P&L breakdown showing IC earnings vs borrowing costs per day.

    Returns:
    - Daily breakdown of IC realized P&L
    - Daily borrowing cost accrual
    - Net daily P&L
    - Cumulative running total
    """
    if not JubileeICTrader or not JubileeTrader:
        raise HTTPException(status_code=503, detail="JUBILEE modules not available")

    try:
        from datetime import datetime, timedelta
        from zoneinfo import ZoneInfo
        from collections import defaultdict

        CENTRAL_TZ = ZoneInfo("America/Chicago")
        now = datetime.now(CENTRAL_TZ)

        # Get traders and database
        box_trader = JubileeTrader()
        ic_trader = JubileeICTrader()

        # Get box positions for daily borrowing cost calculation
        box_positions = box_trader.get_positions()
        total_daily_borrowing_cost = sum(pos.get('daily_cost', 0) for pos in box_positions)

        # Get closed IC trades from the last N days
        closed_trades = ic_trader.db.get_ic_closed_trades(limit=500)

        # Build daily P&L dictionary
        daily_pnl = defaultdict(lambda: {'ic_earned': 0, 'box_cost': total_daily_borrowing_cost, 'trades': 0})

        for trade in closed_trades:
            close_time = trade.get('close_time')
            if not close_time:
                continue

            # Parse date
            if isinstance(close_time, str):
                close_date = datetime.fromisoformat(close_time.replace('Z', '+00:00')).date()
            else:
                close_date = close_time.date()

            # Check if within range
            days_ago = (now.date() - close_date).days
            if days_ago <= days:
                date_key = close_date.isoformat()
                daily_pnl[date_key]['ic_earned'] += trade.get('realized_pnl', 0)
                daily_pnl[date_key]['trades'] += 1

        # Build sorted list for the last N days
        result = []
        cumulative = 0
        for i in range(days, -1, -1):
            date = (now - timedelta(days=i)).date()
            date_key = date.isoformat()

            ic_earned = daily_pnl[date_key]['ic_earned']
            box_cost = daily_pnl[date_key]['box_cost']
            net = ic_earned - box_cost
            cumulative += net
            trades = daily_pnl[date_key]['trades']

            result.append({
                'date': date_key,
                'ic_earned': round(ic_earned, 2),
                'box_cost': round(box_cost, 2),
                'net': round(net, 2),
                'cumulative': round(cumulative, 2),
                'trades': trades,
            })

        return {
            "available": True,
            "days_requested": days,
            "total_daily_borrowing_cost": round(total_daily_borrowing_cost, 2),
            "daily_pnl": result,
            "summary": {
                "total_ic_earned": round(sum(d['ic_earned'] for d in result), 2),
                "total_box_cost": round(sum(d['box_cost'] for d in result), 2),
                "total_net": round(sum(d['net'] for d in result), 2),
                "avg_daily_net": round(sum(d['net'] for d in result) / len(result), 2) if result else 0,
            },
        }
    except Exception as e:
        logger.error(f"Error getting daily P&L: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/reconciliation")
async def get_full_reconciliation():
    """
    Get complete reconciliation data for the JUBILEE dashboard.

    ALL calculations are done server-side - frontend just displays.

    Returns:
    - Per-position box spread reconciliation (strikes, expiration, capital math)
    - Cost accrual with remaining cost to accrue
    - IC positions with full Prophet reasoning
    - Net profit reconciliation with all components
    - Config values (no hardcoded 15% reserve, etc.)
    """
    if not JubileeTrader or not JubileeICTrader:
        raise HTTPException(status_code=503, detail="JUBILEE modules not available")

    try:
        from datetime import datetime
        from zoneinfo import ZoneInfo
        from trading.jubilee.db import JubileeDatabase

        CENTRAL_TZ = ZoneInfo("America/Chicago")
        now = datetime.now(CENTRAL_TZ)

        # Get traders
        box_trader = JubileeTrader()
        ic_trader = JubileeICTrader()
        db = JubileeDatabase()

        # Get config (real values, not hardcoded)
        box_config = db.load_config()
        ic_config = db.load_ic_config()

        # Ensure a paper box spread exists for display/reconciliation.
        # In PAPER mode, IC trading capital is guaranteed by config,
        # but the dashboard needs a box spread position to show capital source.
        try:
            ic_trader._ensure_paper_box_spread()
        except Exception as e:
            logger.warning(f"Failed to ensure paper box spread for reconciliation: {e}")

        # Get all positions
        box_positions = box_trader.get_positions()
        ic_positions = ic_trader.get_positions()

        # Get performance data
        ic_performance = db.get_ic_performance()
        combined = db.get_combined_performance_summary()

        # Build per-position box spread reconciliation
        box_reconciliation = []
        total_borrowed = 0
        total_face_value = 0
        total_borrowing_cost = 0
        total_cost_accrued = 0
        total_cost_remaining = 0

        # Get reserve_pct and min_capital_per_trade from configs for per-position deployment
        pos_reserve_pct = (box_config.reserve_pct / 100) if box_config and box_config.reserve_pct else 0.10
        pos_margin_per_trade = ic_config.min_capital_per_trade if ic_config and ic_config.min_capital_per_trade else 5000.0
        min_dte_to_hold = box_config.min_dte_to_hold if box_config else 30

        # Track roll schedule and risk alerts
        roll_schedule = []
        risk_alerts = []

        for pos in box_positions:
            # Calculate position-specific values
            strike_width = pos.get('strike_width', 50)
            contracts = pos.get('contracts', 0)
            face_value = strike_width * 100 * contracts
            credit_received = pos.get('total_credit_received', 0)
            total_cost = face_value - credit_received  # Total interest over life

            # Time-based accrual
            dte_at_entry = pos.get('dte_at_entry', 90)
            current_dte = pos.get('current_dte', 90)
            days_held = dte_at_entry - current_dte
            daily_cost = total_cost / dte_at_entry if dte_at_entry > 0 else 0
            cost_accrued = daily_cost * days_held
            cost_remaining = total_cost - cost_accrued

            # Implied rate calculation
            implied_rate = pos.get('implied_annual_rate', 0)
            if implied_rate == 0 and credit_received > 0 and dte_at_entry > 0:
                implied_rate = (total_cost / credit_received) / (dte_at_entry / 365) * 100

            # PER-POSITION CAPITAL DEPLOYMENT
            # Count ICs funded by this specific box spread
            ics_from_this_box = [ic for ic in ic_positions if ic.get('source_box_position_id') == pos.get('position_id')]
            capital_reserved = credit_received * pos_reserve_pct
            capital_in_ics = len(ics_from_this_box) * pos_margin_per_trade
            capital_available = credit_received - capital_reserved - capital_in_ics

            # Roll schedule calculation
            days_until_roll = current_dte - min_dte_to_hold
            roll_urgency = "CRITICAL" if days_until_roll <= 0 else "WARNING" if days_until_roll <= 7 else "SOON" if days_until_roll <= 14 else "OK"

            # Add to roll schedule
            roll_schedule.append({
                'position_id': pos.get('position_id'),
                'ticker': pos.get('ticker', 'SPX'),
                'strikes': f"{pos.get('lower_strike')}/{pos.get('upper_strike')}",
                'expiration': pos.get('expiration'),
                'current_dte': current_dte,
                'roll_threshold_dte': min_dte_to_hold,
                'days_until_roll': days_until_roll,
                'urgency': roll_urgency,
            })

            # Risk alerts for this position
            if roll_urgency == "CRITICAL":
                risk_alerts.append({
                    'type': 'ROLL_CRITICAL',
                    'severity': 'HIGH',
                    'position_id': pos.get('position_id'),
                    'message': f"BOX {pos.get('position_id')[:8]} requires IMMEDIATE roll - {current_dte} DTE (threshold: {min_dte_to_hold})",
                })
            elif roll_urgency == "WARNING":
                risk_alerts.append({
                    'type': 'ROLL_WARNING',
                    'severity': 'MEDIUM',
                    'position_id': pos.get('position_id'),
                    'message': f"BOX {pos.get('position_id')[:8]} needs roll within {days_until_roll} days",
                })

            box_reconciliation.append({
                'position_id': pos.get('position_id'),
                # Strike and expiration details
                'ticker': pos.get('ticker', 'SPX'),
                'lower_strike': pos.get('lower_strike'),
                'upper_strike': pos.get('upper_strike'),
                'strike_width': strike_width,
                'expiration': pos.get('expiration'),
                'dte_at_entry': dte_at_entry,
                'current_dte': current_dte,
                'days_held': days_held,
                'contracts': contracts,

                # Capital math (all server-calculated)
                'face_value': face_value,
                'credit_received': credit_received,
                'total_borrowing_cost': total_cost,
                'implied_annual_rate': implied_rate,

                # Cost accrual
                'daily_cost': daily_cost,
                'cost_accrued_to_date': cost_accrued,
                'cost_remaining': cost_remaining,
                'accrual_pct': (cost_accrued / total_cost * 100) if total_cost > 0 else 0,

                # PER-POSITION CAPITAL DEPLOYMENT (NEW)
                'capital_deployment': {
                    'total_borrowed': credit_received,
                    'reserved': capital_reserved,
                    'reserved_pct': pos_reserve_pct * 100,
                    'in_ic_trades': capital_in_ics,
                    'ic_count': len(ics_from_this_box),
                    'available': capital_available,
                    'reconciles': abs((capital_reserved + capital_in_ics + capital_available) - credit_received) < 0.01,
                },

                # Roll schedule info
                'roll_info': {
                    'days_until_roll': days_until_roll,
                    'roll_threshold_dte': min_dte_to_hold,
                    'urgency': roll_urgency,
                },

                # IC returns from this box spread's capital
                'total_ic_returns': pos.get('total_ic_returns', 0),
                'net_profit': pos.get('net_profit', 0),

                # Status
                'status': pos.get('status', 'open'),
                'open_time': pos.get('open_time'),
            })

            # Accumulate totals
            total_borrowed += credit_received
            total_face_value += face_value
            total_borrowing_cost += total_cost
            total_cost_accrued += cost_accrued
            total_cost_remaining += cost_remaining

        # Build IC reconciliation with Prophet details
        ic_reconciliation = []
        total_ic_unrealized = 0
        total_ic_credit = 0
        total_ic_current_value = 0

        for pos in ic_positions:
            unrealized = pos.get('unrealized_pnl', 0)
            credit = pos.get('total_credit_received', 0)
            current_value = pos.get('current_value', 0)

            ic_reconciliation.append({
                'position_id': pos.get('position_id'),
                'source_box_position_id': pos.get('source_box_position_id'),

                # Full strike details
                'ticker': pos.get('ticker', 'SPX'),
                'put_short_strike': pos.get('put_short_strike'),
                'put_long_strike': pos.get('put_long_strike'),
                'call_short_strike': pos.get('call_short_strike'),
                'call_long_strike': pos.get('call_long_strike'),
                'put_spread': pos.get('put_spread'),
                'call_spread': pos.get('call_spread'),
                'spread_width': pos.get('spread_width'),

                # Expiration
                'expiration': pos.get('expiration'),
                'dte': pos.get('dte'),

                # P&L
                'contracts': pos.get('contracts'),
                'entry_credit': pos.get('entry_credit'),
                'total_credit_received': credit,
                'current_value': current_value,
                'unrealized_pnl': unrealized,
                'pnl_pct': pos.get('pnl_pct', 0),

                # Prophet details - FULL transparency
                'oracle_confidence': pos.get('oracle_confidence', 0),
                'oracle_reasoning': pos.get('oracle_reasoning', ''),

                # Market context at entry
                'spot_at_entry': pos.get('spot_at_entry', 0),
                'vix_at_entry': pos.get('vix_at_entry', 0),
                'gamma_regime_at_entry': pos.get('gamma_regime_at_entry', ''),

                # Risk rules
                'stop_loss_pct': pos.get('stop_loss_pct', 200),
                'profit_target_pct': pos.get('profit_target_pct', 50),

                # Status
                'status': pos.get('status'),
                'open_time': pos.get('open_time'),
            })

            total_ic_unrealized += unrealized
            total_ic_credit += credit
            total_ic_current_value += current_value

            # IC position risk alerts
            pnl_pct = (unrealized / credit * 100) if credit > 0 else 0
            stop_loss_pct = pos.get('stop_loss_pct', 200)
            profit_target_pct = pos.get('profit_target_pct', 50)

            if pnl_pct <= -stop_loss_pct * 0.8:  # Within 20% of stop loss
                risk_alerts.append({
                    'type': 'IC_NEAR_STOP',
                    'severity': 'HIGH' if pnl_pct <= -stop_loss_pct else 'MEDIUM',
                    'position_id': pos.get('position_id'),
                    'message': f"IC {pos.get('ticker')} {pos.get('put_short_strike')}/{pos.get('call_short_strike')} at {pnl_pct:.1f}% loss (stop: -{stop_loss_pct}%)",
                })
            elif pnl_pct >= profit_target_pct * 0.8:  # Within 20% of profit target
                risk_alerts.append({
                    'type': 'IC_NEAR_TARGET',
                    'severity': 'LOW',
                    'position_id': pos.get('position_id'),
                    'message': f"IC {pos.get('ticker')} at +{pnl_pct:.1f}% profit - consider closing (target: +{profit_target_pct}%)",
                })

        # Position limit alerts removed - no max positions

        # Get IC closed trades summary
        closed_trades = ic_performance.get('closed_trades', {})
        ic_realized = closed_trades.get('total_pnl', 0)
        ic_wins = closed_trades.get('wins', 0)
        ic_losses = closed_trades.get('losses', 0)
        ic_win_rate = closed_trades.get('win_rate', 0)

        # Calculate capital deployment - USE CONFIG VALUES, NOT HARDCODED
        # box_config.reserve_pct is percentage (e.g., 10.0 = 10%)
        reserve_pct = (box_config.reserve_pct / 100) if box_config and box_config.reserve_pct else 0.10
        # ic_config.min_capital_per_trade is the margin required per IC trade
        margin_per_trade = ic_config.min_capital_per_trade if ic_config and ic_config.min_capital_per_trade else 5000.0

        # Capital comes from box spreads - the sole source of borrowed capital.
        # _ensure_paper_box_spread (called above) guarantees one exists in PAPER mode.
        reserved_capital = total_borrowed * reserve_pct
        capital_in_ic_trades = len(ic_positions) * margin_per_trade
        available_capital = total_borrowed - reserved_capital - capital_in_ic_trades

        # Net profit calculation (all server-side)
        total_ic_returns = ic_realized + total_ic_unrealized
        net_profit = total_ic_returns - total_cost_accrued

        # ROI calculations
        roi_on_borrowed = (net_profit / total_borrowed * 100) if total_borrowed > 0 else 0

        # Cost efficiency
        cost_efficiency = (total_ic_returns / total_cost_accrued) if total_cost_accrued > 0 else 0

        return {
            "available": True,
            "reconciliation_time": now.isoformat(),

            # Config values (ALL from config, not hardcoded)
            "config": {
                "reserve_pct": reserve_pct * 100,  # Return as percentage for display (10 = 10%)
                "min_capital_per_trade": margin_per_trade,  # From ic_config.min_capital_per_trade
                "box_target_dte_min": box_config.target_dte_min if box_config else 180,
                "box_target_dte_max": box_config.target_dte_max if box_config else 365,
                "box_min_dte_to_hold": box_config.min_dte_to_hold if box_config else 30,
                "ic_max_positions": ic_config.max_positions if ic_config else 3,
                "ic_max_daily_trades": ic_config.max_daily_trades if ic_config else 5,
                "ic_profit_target_pct": ic_config.profit_target_pct if ic_config else 50,
                "ic_stop_loss_pct": ic_config.stop_loss_pct if ic_config else 200,
                "require_oracle_approval": ic_config.require_oracle_approval if ic_config else True,
                "min_oracle_confidence": ic_config.min_oracle_confidence if ic_config else 0.6,
                "ic_spread_width": ic_config.spread_width if ic_config else 25,
                "max_margin_pct": box_config.max_margin_pct if box_config else 50,
            },

            # Box Spread Reconciliation (per position)
            "box_spreads": {
                "positions": box_reconciliation,
                "count": len(box_reconciliation),
                "totals": {
                    "total_borrowed": total_borrowed,
                    "total_face_value": total_face_value,
                    "total_borrowing_cost": total_borrowing_cost,
                    "cost_accrued_to_date": total_cost_accrued,
                    "cost_remaining": total_cost_remaining,
                },
            },

            # Capital Deployment Reconciliation
            "capital_deployment": {
                "total_borrowed": total_borrowed,
                "reserved": reserved_capital,
                "reserved_pct": reserve_pct * 100,
                "in_ic_trades": capital_in_ic_trades,
                "ic_positions_count": len(ic_positions),
                "available_to_trade": available_capital,
                # Verification: these should add up
                "reconciles": abs((reserved_capital + capital_in_ic_trades + available_capital) - total_borrowed) < 0.01,
            },

            # IC Trading Reconciliation (per position with Prophet)
            "ic_trading": {
                "positions": ic_reconciliation,
                "count": len(ic_reconciliation),
                "totals": {
                    "total_credit_received": total_ic_credit,
                    "total_current_value": total_ic_current_value,
                    "total_unrealized_pnl": total_ic_unrealized,
                },
                "closed_trades": {
                    "total": ic_wins + ic_losses,
                    "wins": ic_wins,
                    "losses": ic_losses,
                    "win_rate": ic_win_rate,
                    "realized_pnl": ic_realized,
                },
            },

            # Net Profit Reconciliation (the bottom line)
            "net_profit_reconciliation": {
                "income": {
                    "ic_realized_pnl": ic_realized,
                    "ic_unrealized_pnl": total_ic_unrealized,
                    "total_ic_returns": total_ic_returns,
                },
                "costs": {
                    "borrowing_cost_accrued": total_cost_accrued,
                    "borrowing_cost_remaining": total_cost_remaining,
                    "total_borrowing_cost": total_borrowing_cost,
                },
                "net_profit": net_profit,
                "is_profitable": net_profit > 0,

                # Efficiency metrics
                "cost_efficiency": cost_efficiency,
                "roi_on_borrowed": roi_on_borrowed,

                # Reconciliation verification
                "reconciles": abs((total_ic_returns - total_cost_accrued) - net_profit) < 0.01,
            },

            # ROLL SCHEDULE - When each position needs to roll
            "roll_schedule": roll_schedule,

            # RISK ALERTS - Active warnings and alerts
            "risk_alerts": {
                "alerts": sorted(risk_alerts, key=lambda x: {'HIGH': 0, 'MEDIUM': 1, 'LOW': 2}.get(x['severity'], 3)),
                "count": len(risk_alerts),
                "has_critical": any(a['severity'] == 'HIGH' for a in risk_alerts),
                "has_warnings": any(a['severity'] == 'MEDIUM' for a in risk_alerts),
            },

            # BREAK-EVEN PROGRESS - Visual indicator of strategy health
            "break_even_progress": {
                "ic_returns": total_ic_returns,
                "borrowing_costs": total_cost_accrued,
                "is_above_break_even": total_ic_returns >= total_cost_accrued,
                "excess_over_break_even": total_ic_returns - total_cost_accrued,
                "break_even_pct": (total_ic_returns / total_cost_accrued * 100) if total_cost_accrued > 0 else 100,
                "message": f"IC returns {'exceed' if net_profit > 0 else 'below'} borrowing costs by {abs(net_profit):.2f}",
            },
        }

    except Exception as e:
        logger.error(f"Error getting reconciliation: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ==============================================================================
# TRACING & OBSERVABILITY ENDPOINTS
# ==============================================================================
# These endpoints expose JUBILEE tracing and metrics for monitoring.
# ==============================================================================

# Import tracing module
JubileeTracer = None
try:
    from trading.jubilee.tracing import get_tracer, JubileeTracer
    logger.info("JUBILEE tracing module loaded successfully")
except ImportError as e:
    logger.warning(f"JUBILEE tracing module not available: {e}")


@router.get("/tracing/metrics")
async def get_tracing_metrics():
    """
    Get JUBILEE tracing metrics.

    Returns:
    - Total spans tracked
    - Error rate
    - Operation counts and durations
    - JUBILEE-specific metrics (quotes, rates, positions)
    """
    if JubileeTracer is None:
        return {
            "available": False,
            "message": "Tracing module not available",
        }

    try:
        tracer = get_tracer()
        metrics = tracer.get_metrics()
        return {
            "available": True,
            "metrics": metrics,
        }
    except Exception as e:
        logger.error(f"Error getting tracing metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tracing/recent")
async def get_recent_traces(limit: int = Query(50, ge=1, le=200)):
    """
    Get recent trace spans for debugging.

    Returns completed trace spans with timing and attributes.
    """
    if JubileeTracer is None:
        return {
            "available": False,
            "message": "Tracing module not available",
        }

    try:
        tracer = get_tracer()
        traces = tracer.get_recent_traces(limit)
        return {
            "available": True,
            "count": len(traces),
            "traces": traces,
        }
    except Exception as e:
        logger.error(f"Error getting recent traces: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tracing/rate-audit")
async def get_rate_audit_trail(limit: int = Query(50, ge=1, le=100)):
    """
    Get rate calculation audit trail.

    Shows history of implied rate calculations for transparency.
    """
    if JubileeTracer is None:
        return {
            "available": False,
            "message": "Tracing module not available",
        }

    try:
        tracer = get_tracer()
        audit = tracer.get_rate_audit_trail(limit)
        return {
            "available": True,
            "count": len(audit),
            "calculations": audit,
        }
    except Exception as e:
        logger.error(f"Error getting rate audit trail: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tracing/reset")
async def reset_tracing_metrics():
    """
    Reset tracing metrics (for testing/debugging).

    Clears all accumulated metrics and trace history.
    """
    if JubileeTracer is None:
        return {
            "available": False,
            "message": "Tracing module not available",
        }

    try:
        tracer = get_tracer()
        tracer.reset_metrics()
        return {
            "success": True,
            "message": "Tracing metrics reset",
        }
    except Exception as e:
        logger.error(f"Error resetting tracing metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))
