"""
ARES Iron Condor Bot API Routes
================================

API endpoints for the ARES aggressive Iron Condor trading bot.
Provides status, positions, equity curve, and trade management.

ARES targets 10% monthly returns through daily 0DTE Iron Condors.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, HTTPException
from zoneinfo import ZoneInfo

from database_adapter import get_connection

router = APIRouter(prefix="/api/ares", tags=["ARES"])
logger = logging.getLogger(__name__)

# Try to import ARES trader
ares_trader = None
try:
    from trading.ares_iron_condor import ARESTrader, TradingMode
    # Note: ARES trader is initialized by scheduler, we query its state
    ARES_AVAILABLE = True
except ImportError:
    ARES_AVAILABLE = False
    logger.warning("ARES module not available")


def get_ares_instance():
    """Get the ARES trader instance from scheduler if available"""
    global ares_trader
    if ares_trader:
        return ares_trader

    try:
        from scheduler.trader_scheduler import get_ares_trader
        ares_trader = get_ares_trader()
        return ares_trader
    except Exception:
        return None


@router.get("/status")
async def get_ares_status():
    """
    Get current ARES bot status.

    Returns mode, capital, P&L, positions, and configuration.
    """
    ares = get_ares_instance()

    if not ares:
        # Return default status when ARES not initialized
        return {
            "success": True,
            "data": {
                "mode": "paper",
                "capital": 200000,
                "total_pnl": 0,
                "trade_count": 0,
                "win_rate": 0,
                "open_positions": 0,
                "closed_positions": 0,
                "traded_today": False,
                "in_trading_window": False,
                "high_water_mark": 200000,
                "current_time": datetime.now(ZoneInfo("America/New_York")).strftime('%Y-%m-%d %H:%M:%S %Z'),
                "is_active": False,
                "config": {
                    "risk_per_trade": 10.0,
                    "spread_width": 10.0,
                    "sd_multiplier": 1.0,
                    "ticker": "SPX",
                    "target_return": "10% monthly"
                },
                "message": "ARES not yet initialized - will start on next scheduled run"
            }
        }

    try:
        status = ares.get_status()
        status['is_active'] = True

        return {
            "success": True,
            "data": status
        }
    except Exception as e:
        logger.error(f"Error getting ARES status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/positions")
async def get_ares_positions():
    """
    Get ARES open and recently closed positions.

    Returns Iron Condor positions with full details.
    """
    ares = get_ares_instance()

    if not ares:
        return {
            "success": True,
            "data": {
                "open_positions": [],
                "closed_positions": [],
                "message": "ARES not yet initialized"
            }
        }

    try:
        open_positions = []
        for pos in ares.open_positions:
            open_positions.append({
                "position_id": pos.position_id,
                "open_date": pos.open_date,
                "expiration": pos.expiration,
                "put_long_strike": pos.put_long_strike,
                "put_short_strike": pos.put_short_strike,
                "call_short_strike": pos.call_short_strike,
                "call_long_strike": pos.call_long_strike,
                "put_credit": pos.put_credit,
                "call_credit": pos.call_credit,
                "total_credit": pos.total_credit,
                "contracts": pos.contracts,
                "max_loss": pos.max_loss,
                "premium_collected": pos.total_credit * 100 * pos.contracts,
                "underlying_at_entry": pos.underlying_price_at_entry,
                "vix_at_entry": pos.vix_at_entry,
                "status": pos.status
            })

        closed_positions = []
        for pos in ares.closed_positions[-20:]:  # Last 20 closed
            closed_positions.append({
                "position_id": pos.position_id,
                "open_date": pos.open_date,
                "close_date": pos.close_date,
                "expiration": pos.expiration,
                "put_spread": f"{pos.put_long_strike}/{pos.put_short_strike}P",
                "call_spread": f"{pos.call_short_strike}/{pos.call_long_strike}C",
                "contracts": pos.contracts,
                "total_credit": pos.total_credit,
                "close_price": pos.close_price,
                "realized_pnl": pos.realized_pnl,
                "status": pos.status
            })

        return {
            "success": True,
            "data": {
                "open_positions": open_positions,
                "closed_positions": closed_positions,
                "open_count": len(open_positions),
                "closed_count": len(ares.closed_positions)
            }
        }
    except Exception as e:
        logger.error(f"Error getting ARES positions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/equity-curve")
async def get_ares_equity_curve(days: int = 30):
    """
    Get ARES equity curve data.

    Args:
        days: Number of days of history (default 30)

    Returns equity curve built from closed positions.
    """
    ares = get_ares_instance()

    if not ares:
        # Return starting equity point
        return {
            "success": True,
            "data": {
                "equity_curve": [{
                    "date": datetime.now(ZoneInfo("America/New_York")).strftime('%Y-%m-%d'),
                    "equity": 200000,
                    "pnl": 0,
                    "daily_pnl": 0,
                    "return_pct": 0
                }],
                "starting_capital": 200000,
                "current_equity": 200000,
                "total_pnl": 0,
                "message": "ARES not yet initialized"
            }
        }

    try:
        starting_capital = 200000  # ARES allocated capital

        # Build equity curve from closed positions
        equity_curve = []
        cumulative_pnl = 0

        # Group positions by close date
        positions_by_date = {}
        for pos in ares.closed_positions:
            if pos.close_date:
                if pos.close_date not in positions_by_date:
                    positions_by_date[pos.close_date] = []
                positions_by_date[pos.close_date].append(pos)

        # Sort dates and build curve
        sorted_dates = sorted(positions_by_date.keys())
        for date_str in sorted_dates:
            daily_pnl = sum(pos.realized_pnl for pos in positions_by_date[date_str])
            cumulative_pnl += daily_pnl
            current_equity = starting_capital + cumulative_pnl

            equity_curve.append({
                "date": date_str,
                "equity": round(current_equity, 2),
                "pnl": round(cumulative_pnl, 2),
                "daily_pnl": round(daily_pnl, 2),
                "return_pct": round((cumulative_pnl / starting_capital) * 100, 2)
            })

        # Add current date if no trades yet
        if not equity_curve:
            equity_curve.append({
                "date": datetime.now(ZoneInfo("America/New_York")).strftime('%Y-%m-%d'),
                "equity": starting_capital,
                "pnl": 0,
                "daily_pnl": 0,
                "return_pct": 0
            })

        current_equity = starting_capital + ares.total_pnl

        return {
            "success": True,
            "data": {
                "equity_curve": equity_curve,
                "starting_capital": starting_capital,
                "current_equity": round(current_equity, 2),
                "total_pnl": round(ares.total_pnl, 2),
                "total_return_pct": round((ares.total_pnl / starting_capital) * 100, 2)
            }
        }
    except Exception as e:
        logger.error(f"Error getting ARES equity curve: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/performance")
async def get_ares_performance():
    """
    Get ARES performance metrics.

    Returns detailed performance statistics.
    """
    ares = get_ares_instance()

    if not ares:
        return {
            "success": True,
            "data": {
                "total_trades": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "win_rate": 0,
                "total_pnl": 0,
                "avg_pnl_per_trade": 0,
                "best_trade": 0,
                "worst_trade": 0,
                "current_capital": 200000,
                "return_pct": 0,
                "high_water_mark": 200000,
                "max_drawdown": 0,
                "monthly_target": "10%",
                "message": "ARES not yet initialized"
            }
        }

    try:
        # Calculate performance metrics
        winning_trades = sum(1 for pos in ares.closed_positions if pos.realized_pnl > 0)
        losing_trades = sum(1 for pos in ares.closed_positions if pos.realized_pnl <= 0)
        total_closed = len(ares.closed_positions)

        total_pnl = sum(pos.realized_pnl for pos in ares.closed_positions)
        avg_pnl = total_pnl / total_closed if total_closed > 0 else 0

        best_trade = max((pos.realized_pnl for pos in ares.closed_positions), default=0)
        worst_trade = min((pos.realized_pnl for pos in ares.closed_positions), default=0)

        starting_capital = 200000
        current_capital = starting_capital + total_pnl
        return_pct = (total_pnl / starting_capital) * 100 if starting_capital > 0 else 0

        # Calculate max drawdown
        peak = starting_capital
        max_dd = 0
        running_equity = starting_capital

        for pos in ares.closed_positions:
            running_equity += pos.realized_pnl
            peak = max(peak, running_equity)
            dd = (peak - running_equity) / peak * 100 if peak > 0 else 0
            max_dd = max(max_dd, dd)

        return {
            "success": True,
            "data": {
                "total_trades": ares.trade_count,
                "closed_trades": total_closed,
                "open_positions": len(ares.open_positions),
                "winning_trades": winning_trades,
                "losing_trades": losing_trades,
                "win_rate": round((winning_trades / total_closed * 100) if total_closed > 0 else 0, 1),
                "total_pnl": round(total_pnl, 2),
                "avg_pnl_per_trade": round(avg_pnl, 2),
                "best_trade": round(best_trade, 2),
                "worst_trade": round(worst_trade, 2),
                "current_capital": round(current_capital, 2),
                "return_pct": round(return_pct, 2),
                "high_water_mark": round(ares.high_water_mark, 2),
                "max_drawdown_pct": round(max_dd, 2),
                "monthly_target": "10%",
                "strategy": "0DTE Iron Condor @ 1 SD"
            }
        }
    except Exception as e:
        logger.error(f"Error getting ARES performance: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/decisions")
async def get_ares_decisions(limit: int = 50):
    """
    Get ARES decision log entries.

    Args:
        limit: Maximum number of decisions to return (default 50)

    Returns decision logs filtered for ARES bot.
    """
    try:
        from trading.decision_logger import export_decisions_json

        decisions = export_decisions_json(
            bot_name="ARES",
            limit=min(limit, 200)
        )

        return {
            "success": True,
            "data": {
                "count": len(decisions),
                "decisions": decisions
            }
        }
    except ImportError:
        return {
            "success": True,
            "data": {
                "count": 0,
                "decisions": [],
                "message": "Decision logger not available"
            }
        }
    except Exception as e:
        logger.error(f"Error getting ARES decisions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/market-data")
async def get_ares_market_data():
    """
    Get current market data for ARES (SPX, SPY, VIX, expected moves).

    Returns both SPX and SPY data with their respective expected moves.
    This data comes from Tradier Production API.
    """
    import math

    try:
        from data.tradier_data_fetcher import TradierDataFetcher

        tradier = TradierDataFetcher(sandbox=False)

        # Get VIX first (used for both)
        vix = 15.0
        vix_quote = tradier.get_quote("$VIX.X")
        if vix_quote and vix_quote.get('last'):
            vix = float(vix_quote['last'])

        # Get SPX
        spx_price = None
        spx_quote = tradier.get_quote("$SPX.X")
        if spx_quote and spx_quote.get('last'):
            spx_price = float(spx_quote['last'])

        # Get SPY
        spy_price = None
        spy_quote = tradier.get_quote("SPY")
        if spy_quote and spy_quote.get('last'):
            spy_price = float(spy_quote['last'])

        # Fallback: estimate SPX from SPY if needed
        if not spx_price and spy_price:
            spx_price = spy_price * 10

        # Calculate expected moves (1 SD daily move)
        spx_expected_move = 0
        spy_expected_move = 0
        if spx_price:
            spx_expected_move = spx_price * (vix / 100) * math.sqrt(1/252)
        if spy_price:
            spy_expected_move = spy_price * (vix / 100) * math.sqrt(1/252)

        return {
            "success": True,
            "data": {
                "spx": {
                    "ticker": "SPX",
                    "price": round(spx_price, 2) if spx_price else None,
                    "expected_move": round(spx_expected_move, 2)
                },
                "spy": {
                    "ticker": "SPY",
                    "price": round(spy_price, 2) if spy_price else None,
                    "expected_move": round(spy_expected_move, 2)
                },
                "vix": round(vix, 2),
                "timestamp": datetime.now(ZoneInfo("America/New_York")).isoformat(),
                "source": "Tradier Production API",
                # Legacy fields for backward compatibility
                "ticker": "SPX",
                "underlying_price": round(spx_price, 2) if spx_price else None,
                "expected_move": round(spx_expected_move, 2)
            }
        }
    except Exception as e:
        logger.error(f"Error fetching market data: {e}")
        return {
            "success": False,
            "message": f"Could not fetch market data: {str(e)}",
            "data": None
        }


@router.post("/run-cycle")
async def run_ares_cycle():
    """
    Manually trigger an ARES trading cycle.

    This will attempt to open a new Iron Condor position if conditions are met.

    PROTECTED: Only runs in paper mode for safety.
    """
    ares = get_ares_instance()

    if not ares:
        raise HTTPException(
            status_code=503,
            detail="ARES not initialized. Wait for scheduled startup."
        )

    try:
        result = ares.run_daily_cycle()

        return {
            "success": True,
            "data": result,
            "message": "ARES cycle completed"
        }
    except Exception as e:
        logger.error(f"Error running ARES cycle: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/config")
async def get_ares_config():
    """
    Get ARES configuration parameters.

    Returns the current trading configuration.
    """
    ares = get_ares_instance()

    default_config = {
        "ticker": "SPX",
        "spread_width": 10.0,
        "risk_per_trade_pct": 10.0,
        "sd_multiplier": 1.0,
        "use_0dte": True,
        "min_credit": 3.00,
        "profit_target_pct": 50,
        "use_stop_loss": False,
        "entry_window": "09:45 - 10:30 ET",
        "target_return": "10% monthly (~0.5% daily)",
        "description": "ARES (Aggressive Iron Condor) trades daily 0DTE Iron Condors at 1 SD strikes targeting 10% monthly returns through premium collection."
    }

    if ares and ares.config:
        config = ares.config
        return {
            "success": True,
            "data": {
                "ticker": ares.get_trading_ticker(),
                "spread_width": ares.get_spread_width(),
                "risk_per_trade_pct": config.risk_per_trade_pct,
                "sd_multiplier": config.sd_multiplier,
                "use_0dte": config.use_0dte,
                "min_credit": ares.get_min_credit(),
                "profit_target_pct": config.profit_target_pct,
                "use_stop_loss": config.use_stop_loss,
                "entry_window": f"{config.entry_time_start} - {config.entry_time_end} ET",
                "target_return": "10% monthly (~0.5% daily)",
                "mode": ares.mode.value
            }
        }

    return {
        "success": True,
        "data": default_config
    }


@router.post("/sync-tradier")
async def sync_tradier_positions():
    """
    Sync positions from Tradier to AlphaGEX.

    Pulls current positions from Tradier account and identifies any
    that aren't already tracked in AlphaGEX. Useful for reconciliation
    after manual trades.
    """
    ares = get_ares_instance()

    if not ares:
        return {
            "success": False,
            "error": "ARES not initialized",
            "data": None
        }

    try:
        result = ares.sync_positions_from_tradier()

        return {
            "success": True,
            "data": result
        }
    except Exception as e:
        logger.error(f"Error syncing Tradier positions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tradier-status")
async def get_tradier_account_status():
    """
    Get current Tradier account status.

    Returns account balances, positions, and recent orders
    from the connected Tradier account.
    """
    ares = get_ares_instance()

    if not ares:
        return {
            "success": False,
            "error": "ARES not initialized",
            "data": {
                "mode": "unknown",
                "account": {},
                "positions": [],
                "orders": [],
                "errors": ["ARES not initialized"]
            }
        }

    try:
        result = ares.get_tradier_account_status()

        return {
            "success": result.get('success', False),
            "data": result
        }
    except Exception as e:
        logger.error(f"Error getting Tradier account status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/process-expired")
async def process_expired_positions():
    """
    Manually trigger processing of all expired positions.

    This will process any positions that have expired but weren't processed
    due to service downtime or errors. Useful for catching up after outages.

    Processes positions where expiration <= today and status = 'open'.
    """
    ares = get_ares_instance()

    if not ares:
        raise HTTPException(
            status_code=503,
            detail="ARES not initialized. Wait for scheduled startup."
        )

    try:
        result = ares.process_expired_positions()

        return {
            "success": True,
            "data": result,
            "message": f"Processed {result.get('processed_count', 0)} expired positions"
        }
    except Exception as e:
        logger.error(f"Error processing expired positions: {e}")
        raise HTTPException(status_code=500, detail=str(e))
