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

# Try to import ARES trader and strategy presets
ares_trader = None
try:
    from trading.ares_iron_condor import ARESTrader, TradingMode, StrategyPreset, STRATEGY_PRESETS
    # Note: ARES trader is initialized by scheduler, we query its state
    ARES_AVAILABLE = True
except ImportError:
    ARES_AVAILABLE = False
    StrategyPreset = None
    STRATEGY_PRESETS = {}
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


def _get_heartbeat(bot_name: str) -> dict:
    """Get heartbeat info for a bot from the database"""
    CENTRAL_TZ = ZoneInfo("America/Chicago")

    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT last_heartbeat, status, scan_count, details
            FROM bot_heartbeats
            WHERE bot_name = %s
        ''', (bot_name,))

        row = cursor.fetchone()
        conn.close()

        if row:
            last_heartbeat, status, scan_count, details = row

            # Convert timestamp to Central Time
            # PostgreSQL may return UTC or naive datetime - handle both cases
            if last_heartbeat:
                if last_heartbeat.tzinfo is None:
                    # Naive datetime from PostgreSQL - assume it's UTC
                    from zoneinfo import ZoneInfo
                    last_heartbeat = last_heartbeat.replace(tzinfo=ZoneInfo("UTC"))
                # Convert to Central Time
                last_heartbeat_ct = last_heartbeat.astimezone(CENTRAL_TZ)
            else:
                last_heartbeat_ct = None

            return {
                'last_scan': last_heartbeat_ct.strftime('%Y-%m-%d %H:%M:%S CT') if last_heartbeat_ct else None,
                'last_scan_iso': last_heartbeat_ct.isoformat() if last_heartbeat_ct else None,
                'status': status,
                'scan_count_today': scan_count or 0,
                'details': details or {}
            }
        return {
            'last_scan': None,
            'last_scan_iso': None,
            'status': 'NEVER_RUN',
            'scan_count_today': 0,
            'details': {}
        }
    except Exception as e:
        logger.debug(f"Could not get heartbeat for {bot_name}: {e}")
        return {
            'last_scan': None,
            'last_scan_iso': None,
            'status': 'UNKNOWN',
            'scan_count_today': 0,
            'details': {}
        }


@router.get("/status")
async def get_ares_status():
    """
    Get current ARES bot status.

    Returns mode, capital, P&L, positions, configuration, and heartbeat.
    """
    ares = get_ares_instance()

    # Get heartbeat info
    heartbeat = _get_heartbeat('ARES')

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
                "current_time": datetime.now(ZoneInfo("America/Chicago")).strftime('%Y-%m-%d %H:%M:%S CT'),
                "is_active": False,
                "scan_interval_minutes": 5,
                "heartbeat": heartbeat,
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
        status['scan_interval_minutes'] = 5
        status['heartbeat'] = heartbeat

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
        # Helper to infer ticker from spread width
        def get_ticker(pos):
            if hasattr(pos, 'spread_width'):
                return "SPY" if pos.spread_width <= 5 else "SPX"
            # Fallback: infer from underlying price
            if hasattr(pos, 'underlying_price_at_entry') and pos.underlying_price_at_entry:
                return "SPY" if pos.underlying_price_at_entry < 1000 else "SPX"
            return "SPX"

        open_positions = []
        for pos in ares.open_positions:
            # Calculate DTE
            dte = 0
            if pos.expiration:
                try:
                    from datetime import datetime
                    exp_date = datetime.strptime(pos.expiration, "%Y-%m-%d").date()
                    today = datetime.now(ZoneInfo("America/Chicago")).date()
                    dte = (exp_date - today).days
                except:
                    pass

            # Format spread strings
            put_spread = f"{pos.put_long_strike}/{pos.put_short_strike}P"
            call_spread = f"{pos.call_short_strike}/{pos.call_long_strike}C"

            open_positions.append({
                "position_id": pos.position_id,
                "ticker": get_ticker(pos),
                "open_date": pos.open_date,
                "expiration": pos.expiration,
                "dte": dte,
                "is_0dte": dte == 0,
                "put_long_strike": pos.put_long_strike,
                "put_short_strike": pos.put_short_strike,
                "call_short_strike": pos.call_short_strike,
                "call_long_strike": pos.call_long_strike,
                "put_spread": put_spread,
                "call_spread": call_spread,
                "put_credit": pos.put_credit,
                "call_credit": pos.call_credit,
                "total_credit": pos.total_credit,
                "contracts": pos.contracts,
                "spread_width": pos.spread_width,
                "max_loss": pos.max_loss,
                "premium_collected": pos.total_credit * 100 * pos.contracts,
                "max_profit": pos.total_credit * 100 * pos.contracts,
                "rr_ratio": round((pos.total_credit * 100 * pos.contracts) / pos.max_loss, 2) if pos.max_loss else 0,
                "underlying_at_entry": pos.underlying_price_at_entry,
                "vix_at_entry": pos.vix_at_entry,
                "gex_regime": getattr(pos, 'gex_regime', None),
                "oracle_confidence": getattr(pos, 'oracle_confidence', None),
                "status": pos.status
            })

        closed_positions = []
        for pos in ares.closed_positions[-100:]:  # Last 100 closed (increased from 20)
            # Calculate DTE at entry
            dte_at_entry = 0
            if pos.expiration and pos.open_date:
                try:
                    from datetime import datetime
                    exp_date = datetime.strptime(pos.expiration, "%Y-%m-%d").date()
                    open_date = datetime.strptime(pos.open_date, "%Y-%m-%d").date()
                    dte_at_entry = (exp_date - open_date).days
                except:
                    pass

            # Calculate return percentage
            max_profit = pos.total_credit * 100 * pos.contracts if pos.total_credit and pos.contracts else 0
            return_pct = round((pos.realized_pnl / max_profit) * 100, 1) if max_profit and pos.realized_pnl else 0

            closed_positions.append({
                "position_id": pos.position_id,
                "ticker": get_ticker(pos),
                "open_date": pos.open_date,
                "close_date": pos.close_date,
                "expiration": pos.expiration,
                "dte_at_entry": dte_at_entry,
                "was_0dte": dte_at_entry == 0,
                "put_long_strike": pos.put_long_strike,
                "put_short_strike": pos.put_short_strike,
                "call_short_strike": pos.call_short_strike,
                "call_long_strike": pos.call_long_strike,
                "put_spread": f"{pos.put_long_strike}/{pos.put_short_strike}P",
                "call_spread": f"{pos.call_short_strike}/{pos.call_long_strike}C",
                "contracts": pos.contracts,
                "spread_width": pos.spread_width,
                "total_credit": pos.total_credit,
                "max_profit": max_profit,
                "max_loss": pos.max_loss,
                "close_price": pos.close_price,
                "realized_pnl": pos.realized_pnl,
                "return_pct": return_pct,
                "exit_reason": getattr(pos, 'exit_reason', None),
                "underlying_at_entry": pos.underlying_price_at_entry,
                "vix_at_entry": getattr(pos, 'vix_at_entry', None),
                "gex_regime": getattr(pos, 'gex_regime', None),
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
    starting_capital = 200000  # ARES allocated capital
    today = datetime.now(ZoneInfo("America/Chicago")).strftime('%Y-%m-%d')

    if not ares:
        # Return starting equity point
        return {
            "success": True,
            "data": {
                "equity_curve": [{
                    "date": today,
                    "equity": starting_capital,
                    "pnl": 0,
                    "daily_pnl": 0,
                    "return_pct": 0
                }],
                "starting_capital": starting_capital,
                "current_equity": starting_capital,
                "total_pnl": 0,
                "message": "ARES not yet initialized"
            }
        }

    try:
        # Build equity curve from closed positions
        equity_curve = []
        cumulative_pnl = 0

        # Group positions by close date (or expiration if no close_date)
        positions_by_date = {}
        for pos in ares.closed_positions:
            # Use close_date if available, otherwise expiration
            date_key = pos.close_date or pos.expiration
            if date_key:
                if date_key not in positions_by_date:
                    positions_by_date[date_key] = []
                positions_by_date[date_key].append(pos)

        # Sort dates and build curve
        sorted_dates = sorted(positions_by_date.keys())

        # Add starting point
        if sorted_dates:
            first_date = sorted_dates[0]
            # Add day before first trade as starting point
            equity_curve.append({
                "date": first_date,
                "equity": starting_capital,
                "pnl": 0,
                "daily_pnl": 0,
                "return_pct": 0
            })

        for date_str in sorted_dates:
            daily_pnl = sum(pos.realized_pnl for pos in positions_by_date[date_str])
            cumulative_pnl += daily_pnl
            current_equity = starting_capital + cumulative_pnl

            equity_curve.append({
                "date": date_str,
                "equity": round(current_equity, 2),
                "pnl": round(cumulative_pnl, 2),
                "daily_pnl": round(daily_pnl, 2),
                "return_pct": round((cumulative_pnl / starting_capital) * 100, 2),
                "trades_closed": len(positions_by_date[date_str])
            })

        # If no closed positions but we have performance data, build from that
        if not equity_curve and ares.total_pnl != 0:
            equity_curve.append({
                "date": today,
                "equity": starting_capital,
                "pnl": 0,
                "daily_pnl": 0,
                "return_pct": 0
            })
            equity_curve.append({
                "date": today,
                "equity": round(starting_capital + ares.total_pnl, 2),
                "pnl": round(ares.total_pnl, 2),
                "daily_pnl": round(ares.total_pnl, 2),
                "return_pct": round((ares.total_pnl / starting_capital) * 100, 2)
            })

        # Add current point if we have trades
        if equity_curve and equity_curve[-1]["date"] != today:
            current_equity = starting_capital + ares.total_pnl
            equity_curve.append({
                "date": today,
                "equity": round(current_equity, 2),
                "pnl": round(ares.total_pnl, 2),
                "daily_pnl": 0,
                "return_pct": round((ares.total_pnl / starting_capital) * 100, 2)
            })

        # Add starting point if still empty
        if not equity_curve:
            equity_curve.append({
                "date": today,
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
                "total_return_pct": round((ares.total_pnl / starting_capital) * 100, 2),
                "closed_positions_count": len(ares.closed_positions)
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

    IMPORTANT: SPX and VIX index quotes ($SPX.X, $VIX.X) are ONLY available
    on Tradier's PRODUCTION API, not sandbox. If production credentials aren't
    available, we use sandbox and estimate SPX from SPY * 10.
    """
    import math
    import os

    try:
        from data.tradier_data_fetcher import TradierDataFetcher
        from unified_config import APIConfig

        # Determine which API to use:
        # - If production credentials are available, use production (supports SPX/VIX indexes)
        # - Otherwise, fall back to sandbox (only SPY available, estimate SPX)
        prod_key = APIConfig.TRADIER_API_KEY
        prod_account = APIConfig.TRADIER_ACCOUNT_ID
        sandbox_key = APIConfig.TRADIER_SANDBOX_API_KEY
        sandbox_account = APIConfig.TRADIER_SANDBOX_ACCOUNT_ID

        tradier = None
        using_sandbox = False

        if prod_key and prod_account:
            try:
                tradier = TradierDataFetcher(sandbox=False)
                using_sandbox = False
                logger.info("ARES API: Using Tradier PRODUCTION API for market data")
            except Exception as e:
                logger.warning(f"ARES API: Failed to initialize production client: {e}")

        if not tradier and sandbox_key and sandbox_account:
            try:
                tradier = TradierDataFetcher(
                    api_key=sandbox_key,
                    account_id=sandbox_account,
                    sandbox=True
                )
                using_sandbox = True
                logger.info("ARES API: Using Tradier SANDBOX API (SPX/VIX will be estimated)")
            except Exception as e:
                logger.error(f"ARES API: Failed to initialize sandbox client: {e}")

        if not tradier:
            return {
                "success": False,
                "message": "No Tradier credentials available (neither production nor sandbox)",
                "data": None
            }

        # Get SPY first (works on both sandbox and production)
        spy_price = None
        spy_quote = tradier.get_quote("SPY")
        if spy_quote and spy_quote.get('last'):
            spy_price = float(spy_quote['last'])

        # Get SPX and VIX based on API type
        spx_price = None
        vix = 15.0  # Default VIX

        if using_sandbox:
            # Sandbox: Index quotes not available, estimate from SPY
            if spy_price:
                spx_price = spy_price * 10
            logger.info(f"ARES API: Sandbox mode - SPX estimated from SPY*10: ${spx_price}")
        else:
            # Production: Try to get SPX and VIX directly
            spx_quote = tradier.get_quote("$SPX.X")
            if spx_quote and spx_quote.get('last'):
                spx_price = float(spx_quote['last'])
            elif spy_price:
                # Fallback if production SPX fails
                spx_price = spy_price * 10
                logger.warning("ARES API: $SPX.X failed, using SPY*10 fallback")

            vix_quote = tradier.get_quote("$VIX.X")
            if vix_quote and vix_quote.get('last'):
                vix = float(vix_quote['last'])

        # Validate VIX is reasonable (between 8 and 100)
        if vix < 8 or vix > 100:
            logger.warning(f"ARES API: VIX {vix} outside normal range, clamping")
            vix = max(8, min(100, vix))

        # Calculate expected moves (1 SD daily move)
        spx_expected_move = 0
        spy_expected_move = 0
        if spx_price and spx_price > 0:
            spx_expected_move = spx_price * (vix / 100) * math.sqrt(1/252)
            # Validate expected move is reasonable
            if spx_expected_move <= 0:
                logger.error(f"ARES API: SPX expected move calculation failed, using fallback")
                spx_expected_move = spx_price * (vix / 100) * 0.063
        if spy_price and spy_price > 0:
            spy_expected_move = spy_price * (vix / 100) * math.sqrt(1/252)
            # Validate expected move is reasonable
            if spy_expected_move <= 0:
                logger.error(f"ARES API: SPY expected move calculation failed, using fallback")
                spy_expected_move = spy_price * (vix / 100) * 0.063

        api_source = "Tradier Sandbox API (SPX estimated)" if using_sandbox else "Tradier Production API"
        logger.info(f"ARES API: SPX=${spx_price}, SPY=${spy_price}, VIX={vix}, SPX_EM=${spx_expected_move:.2f}, SPY_EM={spy_expected_move:.2f}, Source={api_source}")

        return {
            "success": True,
            "data": {
                "spx": {
                    "ticker": "SPX",
                    "price": round(spx_price, 2) if spx_price else None,
                    "expected_move": round(spx_expected_move, 2),
                    "estimated": using_sandbox  # Indicates if SPX was estimated from SPY
                },
                "spy": {
                    "ticker": "SPY",
                    "price": round(spy_price, 2) if spy_price else None,
                    "expected_move": round(spy_expected_move, 2)
                },
                "vix": round(vix, 2),
                "timestamp": datetime.now(ZoneInfo("America/Chicago")).isoformat(),
                "source": api_source,
                # Legacy fields for backward compatibility
                "ticker": "SPX",
                "underlying_price": round(spx_price, 2) if spx_price else None,
                "expected_move": round(spx_expected_move, 2)
            }
        }
    except Exception as e:
        logger.error(f"Error fetching market data: {e}", exc_info=True)
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

    Returns the current trading configuration for both SPX and SPY.
    """
    ares = get_ares_instance()

    default_config = {
        "ticker": "SPX",
        "spread_width": 10.0,
        "spread_width_spy": 2.0,
        "risk_per_trade_pct": 10.0,
        "sd_multiplier": 0.5,
        "sd_multiplier_spy": 0.5,
        "use_0dte": True,
        "min_credit": 1.50,
        "min_credit_spy": 0.02,
        "profit_target_pct": 50,
        "use_stop_loss": False,
        "entry_window": "09:35 - 15:55 ET",
        "target_return": "10% monthly (~0.5% daily)",
        "description": "ARES (Aggressive Iron Condor) trades daily 0DTE Iron Condors targeting 10% monthly returns through premium collection."
    }

    if ares and ares.config:
        config = ares.config
        return {
            "success": True,
            "data": {
                "ticker": ares.get_trading_ticker(),
                "spread_width": config.spread_width,
                "spread_width_spy": config.spread_width_spy,
                "risk_per_trade_pct": config.risk_per_trade_pct,
                "sd_multiplier": config.sd_multiplier,
                "sd_multiplier_spy": config.sd_multiplier,  # Same for now, can be different
                "use_0dte": config.use_0dte,
                "min_credit": config.min_credit_per_spread,
                "min_credit_spy": config.min_credit_per_spread_spy,
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


@router.get("/live-pnl")
async def get_ares_live_pnl():
    """
    Get real-time unrealized P&L for all open ARES Iron Condor positions.

    Returns:
    - total_unrealized_pnl: Sum of all open position unrealized P&L
    - total_realized_pnl: Today's realized P&L from closed positions
    - net_pnl: Total (unrealized + realized)
    - positions: List of position details with current P&L, strike distances, risk status
    - underlying_price: Current SPY/SPX price
    """
    ares = get_ares_instance()

    if not ares:
        return {
            "success": True,
            "data": {
                "total_unrealized_pnl": 0,
                "total_realized_pnl": 0,
                "net_pnl": 0,
                "positions": [],
                "position_count": 0,
                "message": "ARES not initialized"
            }
        }

    try:
        live_pnl = ares.get_live_pnl()

        return {
            "success": True,
            "data": live_pnl
        }
    except Exception as e:
        logger.error(f"Error getting ARES live P&L: {e}")
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


@router.post("/skip-today")
async def skip_ares_today():
    """
    Skip trading for the rest of today.

    This will prevent ARES from opening any new positions until tomorrow.
    Existing positions will still be managed.
    """
    ares = get_ares_instance()

    if not ares:
        raise HTTPException(
            status_code=503,
            detail="ARES not initialized. Wait for scheduled startup."
        )

    try:
        # Set the skip flag for today
        today = datetime.now(ZoneInfo("America/Chicago")).date()
        ares.skip_date = today

        return {
            "success": True,
            "message": f"ARES will skip trading for {today.isoformat()}",
            "data": {
                "skip_date": today.isoformat()
            }
        }
    except Exception as e:
        logger.error(f"Error setting skip date: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/config")
async def update_ares_config(updates: dict):
    """
    Update ARES configuration parameters.

    Supports updating:
    - risk_per_trade_pct: Risk per trade percentage (1-15)
    - sd_multiplier: Standard deviation multiplier (0.3-1.5)
    """
    ares = get_ares_instance()

    if not ares:
        raise HTTPException(
            status_code=503,
            detail="ARES not initialized. Wait for scheduled startup."
        )

    try:
        updated = {}

        if 'risk_per_trade_pct' in updates:
            new_risk = updates['risk_per_trade_pct']
            if not (1 <= new_risk <= 15):
                raise HTTPException(
                    status_code=400,
                    detail="risk_per_trade_pct must be between 1 and 15"
                )
            ares.config.risk_per_trade_pct = new_risk
            updated['risk_per_trade_pct'] = new_risk

        if 'sd_multiplier' in updates:
            new_sd = updates['sd_multiplier']
            if not (0.3 <= new_sd <= 1.5):
                raise HTTPException(
                    status_code=400,
                    detail="sd_multiplier must be between 0.3 and 1.5"
                )
            ares.config.sd_multiplier = new_sd
            updated['sd_multiplier'] = new_sd

        return {
            "success": True,
            "message": "Configuration updated successfully",
            "data": {
                "updated": updated,
                "current_config": {
                    "risk_per_trade_pct": ares.config.risk_per_trade_pct,
                    "sd_multiplier": ares.config.sd_multiplier
                }
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating ARES config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/strategy/presets")
async def get_strategy_presets():
    """
    Get available strategy presets with their configurations.

    Returns list of presets with:
    - name: Display name
    - description: What the strategy does
    - vix_hard_skip: VIX threshold for skipping (0 = disabled)
    - backtest_sharpe: Sharpe ratio from 2022-2024 backtest
    - backtest_win_rate: Win rate from backtest
    """
    if not ARES_AVAILABLE or not STRATEGY_PRESETS:
        return {
            "success": True,
            "data": {
                "presets": [],
                "active_preset": "moderate"
            }
        }

    ares = get_ares_instance()
    active_preset = ares.config.strategy_preset if ares else "moderate"

    presets = []
    for preset_enum, config in STRATEGY_PRESETS.items():
        presets.append({
            "id": preset_enum.value,
            "name": config["name"],
            "description": config["description"],
            "vix_hard_skip": config.get("vix_hard_skip") or 0,
            "vix_monday_friday_skip": config.get("vix_monday_friday_skip", 0),
            "vix_streak_skip": config.get("vix_streak_skip", 0),
            "risk_per_trade_pct": config["risk_per_trade_pct"],
            "sd_multiplier": config["sd_multiplier"],
            "backtest_sharpe": config.get("backtest_sharpe", 0),
            "backtest_win_rate": config.get("backtest_win_rate", 0),
            "is_active": preset_enum.value == active_preset
        })

    return {
        "success": True,
        "data": {
            "presets": presets,
            "active_preset": active_preset
        }
    }


@router.post("/strategy/preset")
async def set_strategy_preset(request: dict):
    """
    Set the active strategy preset.

    Body:
    - preset: Strategy preset ID (baseline, conservative, moderate, aggressive, wide_strikes)
    """
    ares = get_ares_instance()

    if not ares:
        raise HTTPException(
            status_code=503,
            detail="ARES not initialized. Wait for scheduled startup."
        )

    preset_id = request.get("preset", "").lower()

    # Validate preset
    valid_presets = ["baseline", "conservative", "moderate", "aggressive", "wide_strikes"]
    if preset_id not in valid_presets:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid preset. Must be one of: {', '.join(valid_presets)}"
        )

    try:
        # Apply the strategy preset
        ares.config.apply_strategy_preset(preset_id)

        # Get the preset config for response
        preset_config = STRATEGY_PRESETS.get(StrategyPreset(preset_id), {})

        return {
            "success": True,
            "message": f"Strategy preset changed to: {preset_config.get('name', preset_id)}",
            "data": {
                "preset": preset_id,
                "name": preset_config.get("name", preset_id),
                "description": preset_config.get("description", ""),
                "current_config": {
                    "vix_hard_skip": ares.config.vix_hard_skip,
                    "vix_monday_friday_skip": ares.config.vix_monday_friday_skip,
                    "vix_streak_skip": ares.config.vix_streak_skip,
                    "risk_per_trade_pct": ares.config.risk_per_trade_pct,
                    "sd_multiplier": ares.config.sd_multiplier
                }
            }
        }
    except Exception as e:
        logger.error(f"Error setting strategy preset: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scan-activity")
async def get_ares_scan_activity(
    date: str = None,
    outcome: str = None,
    limit: int = 50
):
    """
    Get ARES scan activity with full decision context.

    Each scan shows:
    - Market conditions at time of scan
    - Oracle advice and reasoning
    - Why trade was/wasn't taken
    - All checks performed
    - GEX regime and signal quality

    This is the key endpoint for understanding ARES behavior.
    """
    try:
        from trading.scan_activity_logger import get_recent_scans

        scans = get_recent_scans(
            bot_name="ARES",
            date=date,
            outcome=outcome.upper() if outcome else None,
            limit=min(limit, 200)
        )

        # Calculate summary stats
        trades = sum(1 for s in scans if s.get('trade_executed'))
        no_trades = sum(1 for s in scans if s.get('outcome') == 'NO_TRADE')
        skips = sum(1 for s in scans if s.get('outcome') == 'SKIP')
        errors = sum(1 for s in scans if s.get('outcome') == 'ERROR')

        return {
            "success": True,
            "data": {
                "count": len(scans),
                "summary": {
                    "trades_executed": trades,
                    "no_trade_scans": no_trades,
                    "skips": skips,
                    "errors": errors
                },
                "scans": scans
            }
        }
    except ImportError:
        return {
            "success": True,
            "data": {
                "count": 0,
                "scans": [],
                "message": "Scan activity logger not available"
            }
        }
    except Exception as e:
        logger.error(f"Error getting ARES scan activity: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scan-activity/today")
async def get_ares_scan_activity_today():
    """Get all ARES scans from today with summary."""
    today = datetime.now(ZoneInfo("America/Chicago")).strftime('%Y-%m-%d')
    return await get_ares_scan_activity(date=today, limit=200)
