"""
Margin Management API Routes.

Provides endpoints for margin health monitoring, pre-trade checks,
scenario simulation, and historical margin analysis.

Endpoints:
  GET  /api/margin/health                       - Portfolio margin overview
  GET  /api/margin/bot/{bot_name}/status         - Bot margin health
  GET  /api/margin/bot/{bot_name}/positions       - Per-position margin details
  POST /api/margin/bot/{bot_name}/pre-trade-check - Pre-trade margin validation
  POST /api/margin/bot/{bot_name}/simulate/price  - Price move scenario
  POST /api/margin/bot/{bot_name}/simulate/add    - Add position scenario
  POST /api/margin/bot/{bot_name}/simulate/leverage - Leverage change scenario
  GET  /api/margin/alerts                        - Recent margin alerts
  GET  /api/margin/history/{bot_name}            - Historical margin snapshots
  GET  /api/margin/daily-report                  - Daily margin report
  GET  /api/margin/config/{bot_name}             - Bot margin configuration
  PUT  /api/margin/config/{bot_name}             - Update bot margin configuration
"""

import logging
from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/margin", tags=["Margin Management"])

CENTRAL_TZ = ZoneInfo("America/Chicago")

# Lazy imports for graceful degradation
MarginMonitor = None
MarginEngine = None
get_margin_monitor = None
get_bot_margin_config = None

try:
    from trading.margin.margin_monitor import MarginMonitor as _MM, get_margin_monitor as _gmm
    from trading.margin.margin_engine import MarginEngine as _ME
    from trading.margin.margin_config import get_bot_margin_config as _gbmc
    MarginMonitor = _MM
    get_margin_monitor = _gmm
    MarginEngine = _ME
    get_bot_margin_config = _gbmc
    logger.info("Margin management module loaded")
except ImportError as e:
    logger.warning(f"Margin management module not available: {e}")


# =============================================================================
# REQUEST/RESPONSE MODELS
# =============================================================================

class PreTradeCheckRequest(BaseModel):
    """Request body for pre-trade margin check."""
    symbol: str = Field(..., description="Trading symbol (e.g., BTC-PERP, ES)")
    side: str = Field(..., description="Trade direction: 'long' or 'short'")
    quantity: float = Field(..., gt=0, description="Position size (contracts or coins)")
    entry_price: float = Field(..., gt=0, description="Expected entry price")
    leverage: Optional[float] = Field(None, gt=0, description="Leverage (perps only)")


class PriceScenarioRequest(BaseModel):
    """Request body for price move scenario simulation."""
    price_change_pct: float = Field(..., description="Price change percentage (e.g., -5.0 for 5% drop)")


class AddPositionScenarioRequest(BaseModel):
    """Request body for add-position scenario simulation."""
    quantity: float = Field(..., gt=0, description="Additional quantity")
    price: float = Field(..., gt=0, description="Entry price for new position")
    side: str = Field("long", description="Position side: 'long' or 'short'")


class LeverageScenarioRequest(BaseModel):
    """Request body for leverage change scenario simulation."""
    new_leverage: float = Field(..., gt=0, description="New leverage multiplier")


class UpdateConfigRequest(BaseModel):
    """Request body for updating bot margin configuration."""
    max_margin_usage_pct: Optional[float] = Field(None, ge=10, le=100)
    min_liquidation_distance_pct: Optional[float] = Field(None, ge=0, le=50)
    max_effective_leverage: Optional[float] = Field(None, ge=1, le=200)
    max_single_position_margin_pct: Optional[float] = Field(None, ge=5, le=100)
    warning_threshold_pct: Optional[float] = Field(None, ge=10, le=100)
    danger_threshold_pct: Optional[float] = Field(None, ge=20, le=100)
    critical_threshold_pct: Optional[float] = Field(None, ge=30, le=100)
    auto_reduce_enabled: Optional[bool] = None
    leverage_override: Optional[float] = Field(None, ge=1, le=200)


# =============================================================================
# HEALTH CHECK
# =============================================================================

def _check_module_available():
    """Verify margin module is loaded."""
    if get_margin_monitor is None:
        raise HTTPException(
            status_code=503,
            detail="Margin management module not available"
        )


# =============================================================================
# ENDPOINTS
# =============================================================================

@router.get("/health")
async def get_portfolio_margin_health():
    """Get portfolio-level margin overview across all bots.

    Returns aggregate equity, margin usage, and per-bot health status.
    """
    _check_module_available()
    try:
        monitor = get_margin_monitor()
        summary = monitor.get_portfolio_summary()
        return {"success": True, "data": summary}
    except Exception as e:
        logger.exception(f"Error getting portfolio margin health: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/bot/{bot_name}/status")
async def get_bot_margin_status(bot_name: str):
    """Get detailed margin health for a specific bot.

    Returns account equity, margin used, available margin, health status,
    effective leverage, and all position margin details.
    """
    _check_module_available()
    try:
        monitor = get_margin_monitor()
        metrics = monitor.get_bot_margin_metrics(bot_name)

        if metrics is None:
            # Try to calculate on-demand
            config = get_bot_margin_config(bot_name)
            if config is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"Bot '{bot_name}' not found in margin configuration"
                )

            engine = MarginEngine(config)
            equity, positions = monitor._get_bot_state(bot_name, config)
            if equity is None:
                return {
                    "success": True,
                    "data": {
                        "bot_name": bot_name,
                        "status": "no_data",
                        "message": "No equity/position data available. Bot may not be active.",
                    }
                }
            metrics = engine.calculate_account_metrics(equity, positions)

        return {"success": True, "data": metrics.to_dict()}

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error getting margin status for {bot_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/bot/{bot_name}/positions")
async def get_bot_position_margins(bot_name: str):
    """Get per-position margin details for a bot.

    Returns margin required, liquidation price, distance to liquidation,
    unrealized P&L, and funding costs for each open position.
    """
    _check_module_available()
    try:
        monitor = get_margin_monitor()
        metrics = monitor.get_bot_margin_metrics(bot_name)

        if metrics is None:
            config = get_bot_margin_config(bot_name)
            if config is None:
                raise HTTPException(status_code=404, detail=f"Bot '{bot_name}' not found")

            engine = MarginEngine(config)
            equity, positions = monitor._get_bot_state(bot_name, config)
            if equity is None:
                return {"success": True, "data": {"positions": []}}
            metrics = engine.calculate_account_metrics(equity, positions)

        return {
            "success": True,
            "data": {
                "bot_name": bot_name,
                "position_count": metrics.position_count,
                "positions": [p.to_dict() for p in metrics.positions],
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error getting position margins for {bot_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/bot/{bot_name}/pre-trade-check")
async def pre_trade_margin_check(bot_name: str, request: PreTradeCheckRequest):
    """Check if a proposed trade can be opened within margin limits.

    This is the critical safety endpoint. Call BEFORE placing any order.
    Returns approval status with detailed reason if rejected.
    """
    _check_module_available()
    try:
        monitor = get_margin_monitor()
        proposed = {
            "symbol": request.symbol,
            "side": request.side,
            "quantity": request.quantity,
            "entry_price": request.entry_price,
            "leverage": request.leverage,
        }

        result = monitor.check_margin_for_trade(bot_name, proposed)
        if result is None:
            raise HTTPException(
                status_code=404,
                detail=f"Cannot check margin for '{bot_name}': no config or data available"
            )

        return {"success": True, "data": result}

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error in pre-trade check for {bot_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/bot/{bot_name}/simulate/price")
async def simulate_price_move(bot_name: str, request: PriceScenarioRequest):
    """Simulate what happens if prices move by a given percentage.

    Shows projected margin usage, liquidation risk, and margin call status.
    """
    _check_module_available()
    try:
        config = get_bot_margin_config(bot_name)
        if config is None:
            raise HTTPException(status_code=404, detail=f"Bot '{bot_name}' not found")

        engine = MarginEngine(config)
        monitor = get_margin_monitor()
        equity, positions = monitor._get_bot_state(bot_name, config)

        if equity is None:
            return {"success": True, "data": {"message": "No position data available"}}

        result = engine.simulate_price_move(equity, positions, request.price_change_pct)
        return {"success": True, "data": result.to_dict()}

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error simulating price move for {bot_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/bot/{bot_name}/simulate/add")
async def simulate_add_position(bot_name: str, request: AddPositionScenarioRequest):
    """Simulate adding more contracts/coins to see margin impact."""
    _check_module_available()
    try:
        config = get_bot_margin_config(bot_name)
        if config is None:
            raise HTTPException(status_code=404, detail=f"Bot '{bot_name}' not found")

        engine = MarginEngine(config)
        monitor = get_margin_monitor()
        equity, positions = monitor._get_bot_state(bot_name, config)

        if equity is None:
            return {"success": True, "data": {"message": "No position data available"}}

        result = engine.simulate_add_contracts(
            equity, positions, request.quantity, request.price, request.side
        )
        return {"success": True, "data": result.to_dict()}

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error simulating add position for {bot_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/bot/{bot_name}/simulate/leverage")
async def simulate_leverage_change(bot_name: str, request: LeverageScenarioRequest):
    """Simulate changing leverage to see margin impact."""
    _check_module_available()
    try:
        config = get_bot_margin_config(bot_name)
        if config is None:
            raise HTTPException(status_code=404, detail=f"Bot '{bot_name}' not found")

        engine = MarginEngine(config)
        monitor = get_margin_monitor()
        equity, positions = monitor._get_bot_state(bot_name, config)

        if equity is None:
            return {"success": True, "data": {"message": "No position data available"}}

        result = engine.simulate_leverage_change(equity, positions, request.new_leverage)
        return {"success": True, "data": result.to_dict()}

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error simulating leverage change for {bot_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/alerts")
async def get_margin_alerts(
    bot_name: Optional[str] = Query(None, description="Filter by bot name"),
    limit: int = Query(50, ge=1, le=200, description="Max alerts to return"),
):
    """Get recent margin alerts across all bots or filtered by bot."""
    _check_module_available()
    try:
        monitor = get_margin_monitor()
        alerts = monitor.get_alert_history(bot_name=bot_name, limit=limit)
        return {"success": True, "data": {"alerts": alerts, "count": len(alerts)}}
    except Exception as e:
        logger.exception(f"Error getting margin alerts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history/{bot_name}")
async def get_margin_history(
    bot_name: str,
    hours: int = Query(24, ge=1, le=168, description="Hours of history (max 7 days)"),
):
    """Get historical margin snapshots for a bot.

    Returns time-series data for margin usage, equity, and health status.
    Useful for visualizing margin utilization over time.
    """
    _check_module_available()
    try:
        from database_adapter import get_connection
        conn = get_connection()
        cursor = conn.cursor()

        since = datetime.now(CENTRAL_TZ) - timedelta(hours=hours)

        cursor.execute("""
            SELECT timestamp, account_equity, margin_used, margin_available,
                   margin_usage_pct, margin_ratio, effective_leverage,
                   total_notional, total_unrealized_pnl, position_count,
                   health_status, total_funding_cost_daily
            FROM margin_snapshots
            WHERE bot_name = %s AND timestamp >= %s
            ORDER BY timestamp ASC
        """, (bot_name, since))

        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        snapshots = []
        for row in rows:
            snapshots.append({
                "timestamp": row[0].isoformat() if row[0] else None,
                "account_equity": float(row[1]) if row[1] else 0,
                "margin_used": float(row[2]) if row[2] else 0,
                "margin_available": float(row[3]) if row[3] else 0,
                "margin_usage_pct": float(row[4]) if row[4] else 0,
                "margin_ratio": float(row[5]) if row[5] else 0,
                "effective_leverage": float(row[6]) if row[6] else 0,
                "total_notional": float(row[7]) if row[7] else 0,
                "total_unrealized_pnl": float(row[8]) if row[8] else 0,
                "position_count": int(row[9]) if row[9] else 0,
                "health_status": row[10] if row[10] else "UNKNOWN",
                "total_funding_cost_daily": float(row[11]) if row[11] else None,
            })

        return {
            "success": True,
            "data": {
                "bot_name": bot_name,
                "hours": hours,
                "snapshot_count": len(snapshots),
                "snapshots": snapshots,
            }
        }

    except Exception as e:
        logger.exception(f"Error getting margin history for {bot_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/daily-report")
async def get_daily_margin_report():
    """Generate daily margin report.

    Returns peak margin usage, time in risk zones, closest liquidation distance,
    and funding costs for each bot.
    """
    _check_module_available()
    try:
        monitor = get_margin_monitor()
        report = monitor.get_daily_report()
        return {"success": True, "data": report}
    except Exception as e:
        logger.exception(f"Error generating daily report: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/config/{bot_name}")
async def get_bot_margin_config_endpoint(bot_name: str):
    """Get the margin configuration for a specific bot."""
    _check_module_available()
    try:
        config = get_bot_margin_config(bot_name)
        if config is None:
            raise HTTPException(
                status_code=404,
                detail=f"No margin configuration found for bot '{bot_name}'"
            )
        return {"success": True, "data": config.to_dict()}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error getting margin config for {bot_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/config/{bot_name}")
async def update_bot_margin_config(bot_name: str, request: UpdateConfigRequest):
    """Update margin configuration for a bot.

    Stores updated values in the margin_bot_config table.
    Changes take effect on the next polling cycle.
    """
    _check_module_available()
    try:
        from database_adapter import get_connection
        conn = get_connection()
        cursor = conn.cursor()

        # Ensure table exists
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS margin_bot_config (
                id SERIAL PRIMARY KEY,
                bot_name VARCHAR(50) NOT NULL,
                config_key VARCHAR(100) NOT NULL,
                config_value VARCHAR(500) NOT NULL,
                is_active BOOLEAN DEFAULT true,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                UNIQUE(bot_name, config_key)
            )
        """)

        updates = request.dict(exclude_none=True)
        for key, value in updates.items():
            cursor.execute("""
                INSERT INTO margin_bot_config (bot_name, config_key, config_value, updated_at)
                VALUES (%s, %s, %s, NOW())
                ON CONFLICT (bot_name, config_key) DO UPDATE
                SET config_value = EXCLUDED.config_value,
                    updated_at = NOW()
            """, (bot_name, key, str(value)))

        conn.commit()
        cursor.close()
        conn.close()

        return {
            "success": True,
            "data": {
                "bot_name": bot_name,
                "updated_fields": list(updates.keys()),
                "message": "Configuration updated. Changes take effect on next poll cycle.",
            }
        }

    except Exception as e:
        logger.exception(f"Error updating margin config for {bot_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/bots")
async def list_configured_bots():
    """List all bots with margin configuration."""
    _check_module_available()
    try:
        from trading.margin.margin_config import BOT_INSTRUMENT_MAP, MARKET_DEFAULTS

        bots = []
        for bot_name, instrument in BOT_INSTRUMENT_MAP.items():
            market = MARKET_DEFAULTS.get(instrument)
            bots.append({
                "bot_name": bot_name,
                "instrument": instrument,
                "market_type": market.market_type.value if market else "unknown",
                "exchange": market.exchange if market else "unknown",
                "has_funding_rate": market.has_funding_rate if market else False,
            })

        return {"success": True, "data": {"bots": bots, "count": len(bots)}}

    except Exception as e:
        logger.exception(f"Error listing configured bots: {e}")
        raise HTTPException(status_code=500, detail=str(e))
