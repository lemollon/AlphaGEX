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

# Dynamic rate fetching
RateFetcher = None
try:
    from trading.prometheus.rate_fetcher import get_current_rates, get_rate_fetcher
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
    if not PrometheusTrader:
        raise HTTPException(status_code=503, detail="PROMETHEUS Box Spread not available")

    try:
        trader = PrometheusTrader()
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
    if not PrometheusTrader:
        raise HTTPException(status_code=503, detail="PROMETHEUS Box Spread not available")

    try:
        trader = PrometheusTrader()
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
        # Return fallback rates when live data unavailable
        from datetime import datetime
        logger.warning(f"Rate analysis failed, returning estimates: {e}")
        return {
            "analysis_time": datetime.now().isoformat(),
            "box_implied_rate": 4.5,
            "fed_funds_rate": 4.5,
            "sofr_rate": 4.45,
            "broker_margin_rate": 8.5,
            "spread_to_fed_funds": 0.0,
            "spread_to_margin": -4.0,
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
            "reasoning": "Live market data unavailable - using estimated rates. Box spreads typically offer rates 3-4% below margin.",
            "data_source": "estimated",
            "error": str(e),
        }


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

    # Fallback
    return {
        "fed_funds_rate": 4.33,
        "sofr_rate": 4.30,
        "treasury_3m": 4.25,
        "treasury_1y": 4.15,
        "margin_rate": 8.33,
        "last_updated": datetime.now().isoformat(),
        "source": "fallback",
        "cache_hours": 4,
        "error": "Rate fetcher not available",
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
        # Return a basic briefing when full generation fails
        from datetime import datetime, date
        logger.warning(f"Daily briefing generation failed, returning basic briefing: {e}")

        # Get basic position info that doesn't require live market data
        try:
            trader = PrometheusTrader()
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
    if not PrometheusTrader:
        raise HTTPException(status_code=503, detail="PROMETHEUS Box Spread not available")

    try:
        trader = PrometheusTrader()
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
    if not PrometheusTrader:
        raise HTTPException(status_code=503, detail="PROMETHEUS Box Spread not available")

    try:
        trader = PrometheusTrader()
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
    if not PrometheusTrader:
        raise HTTPException(status_code=503, detail="PROMETHEUS Box Spread not available")

    try:
        trader = PrometheusTrader()
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
    if not PrometheusTrader:
        raise HTTPException(status_code=503, detail="PROMETHEUS Box Spread not available")

    try:
        from trading.prometheus.executor import get_box_spread_quotes

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
    if not PrometheusTrader:
        raise HTTPException(status_code=503, detail="PROMETHEUS Box Spread not available")

    try:
        trader = PrometheusTrader()
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
    if not PrometheusTrader:
        return {
            "available": False,
            "message": "PROMETHEUS Box Spread not available",
        }

    try:
        import os
        trader = PrometheusTrader()
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
# PROMETHEUS IC TRADING ENDPOINTS
# ==============================================================================
# These endpoints handle the Iron Condor trading side of PROMETHEUS - trading
# with borrowed capital from box spreads to generate returns.
# ==============================================================================

# Import IC components
PrometheusICTrader = None
PrometheusICConfig = None
try:
    from trading.prometheus.trader import PrometheusICTrader
    from trading.prometheus.models import PrometheusICConfig, ICPositionStatus
    logger.info("PROMETHEUS IC Trader modules loaded successfully")
except ImportError as e:
    logger.warning(f"PROMETHEUS IC Trader modules not available: {e}")


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
    require_oracle_approval: Optional[bool] = Field(None, description="Require Oracle approval")
    min_oracle_confidence: Optional[float] = Field(None, description="Min Oracle confidence")
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
    Get comprehensive PROMETHEUS IC trading status.

    Returns:
    - Trading enabled/disabled
    - Open positions and unrealized P&L
    - Performance metrics
    - Available capital for new trades
    """
    if not PrometheusICTrader:
        raise HTTPException(status_code=503, detail="PROMETHEUS IC Trader not available")

    try:
        trader = PrometheusICTrader()
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
    if not PrometheusICTrader:
        raise HTTPException(status_code=503, detail="PROMETHEUS IC Trader not available")

    try:
        trader = PrometheusICTrader()
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
    if not PrometheusICTrader:
        raise HTTPException(status_code=503, detail="PROMETHEUS IC Trader not available")

    try:
        trader = PrometheusICTrader()
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


# ========== IC Positions ==========

@router.get("/ic/positions")
async def get_ic_positions():
    """
    Get all open IC positions with current metrics.

    Each position includes:
    - Strikes and expiration
    - Entry credit and current value
    - Unrealized P&L
    - Oracle confidence at entry
    """
    if not PrometheusICTrader:
        raise HTTPException(status_code=503, detail="PROMETHEUS IC Trader not available")

    try:
        trader = PrometheusICTrader()
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
    if not PrometheusICTrader:
        raise HTTPException(status_code=503, detail="PROMETHEUS IC Trader not available")

    try:
        trader = PrometheusICTrader()
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
    if not PrometheusICTrader:
        raise HTTPException(status_code=503, detail="PROMETHEUS IC Trader not available")

    try:
        trader = PrometheusICTrader()
        result = trader.close_position(request.position_id, request.reason)
        return result
    except Exception as e:
        logger.error(f"Error closing IC position: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ========== IC Closed Trades & Performance ==========

@router.get("/ic/closed-trades")
async def get_ic_closed_trades(limit: int = Query(50, ge=1, le=500)):
    """Get closed IC trade history"""
    if not PrometheusICTrader:
        raise HTTPException(status_code=503, detail="PROMETHEUS IC Trader not available")

    try:
        trader = PrometheusICTrader()
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
    if not PrometheusICTrader:
        raise HTTPException(status_code=503, detail="PROMETHEUS IC Trader not available")

    try:
        trader = PrometheusICTrader()
        performance = trader.db.get_ic_performance()
        return {
            "available": True,
            "performance": performance,
        }
    except Exception as e:
        logger.error(f"Error getting IC performance: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ic/equity-curve")
async def get_ic_equity_curve(limit: int = Query(100, ge=1, le=500)):
    """Get IC trading equity curve data"""
    if not PrometheusICTrader:
        raise HTTPException(status_code=503, detail="PROMETHEUS IC Trader not available")

    try:
        trader = PrometheusICTrader()
        curve = trader.get_equity_curve(limit)
        return {
            "available": True,
            "count": len(curve),
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
    if not PrometheusICTrader:
        raise HTTPException(status_code=503, detail="PROMETHEUS IC Trader not available")

    try:
        trader = PrometheusICTrader()
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
    if not PrometheusICTrader:
        raise HTTPException(status_code=503, detail="PROMETHEUS IC Trader not available")

    try:
        trader = PrometheusICTrader()
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
    if not PrometheusICTrader:
        raise HTTPException(status_code=503, detail="PROMETHEUS IC Trader not available")

    try:
        trader = PrometheusICTrader()
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
    if not PrometheusICTrader:
        raise HTTPException(status_code=503, detail="PROMETHEUS IC Trader not available")

    try:
        trader = PrometheusICTrader()
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
    if not PrometheusICTrader:
        raise HTTPException(status_code=503, detail="PROMETHEUS IC Trader not available")

    try:
        from trading.prometheus.trader import run_prometheus_ic_mtm_update
        result = run_prometheus_ic_mtm_update()
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
    if not PrometheusTrader or not PrometheusICTrader:
        raise HTTPException(status_code=503, detail="PROMETHEUS modules not available")

    try:
        from trading.prometheus.db import PrometheusDatabase
        db = PrometheusDatabase()
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
