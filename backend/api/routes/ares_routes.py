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
from fastapi import APIRouter, HTTPException, Depends, Request, Query
from zoneinfo import ZoneInfo

from database_adapter import get_connection

# Authentication middleware
try:
    from backend.api.auth_middleware import require_api_key, require_admin, optional_auth, AuthInfo
    AUTH_AVAILABLE = True
except ImportError:
    AUTH_AVAILABLE = False
    require_api_key = None
    require_admin = None

# Pydantic request/response models
try:
    from backend.api.models import (
        ARESConfigUpdate,
        StrategyPresetRequest,
        APIResponse,
        StrategyPresetEnum
    )
    MODELS_AVAILABLE = True
except ImportError:
    MODELS_AVAILABLE = False
    ARESConfigUpdate = dict
    StrategyPresetRequest = dict

router = APIRouter(prefix="/api/ares", tags=["ARES"])
logger = logging.getLogger(__name__)


def _resolve_query_param(param, default=None):
    """
    Resolve a FastAPI Query parameter to its actual value.

    When endpoints are called directly (bypassing FastAPI routing),
    Query objects aren't resolved. This helper extracts the actual value.
    """
    if param is None:
        return default
    # If it's a Query object (has .default attribute), get the default
    if hasattr(param, 'default'):
        return param.default if param.default is not None else default
    # Otherwise return the value as-is
    return param


# Try to import Tradier for account balance
# NOTE: data/__init__.py imports polygon_data_fetcher which requires pandas
# If pandas is missing, the whole data package fails. We try multiple import methods.
TradierDataFetcher = None
TRADIER_AVAILABLE = False

# Method 1: Try standard import (works if pandas is installed)
try:
    from data.tradier_data_fetcher import TradierDataFetcher
    TRADIER_AVAILABLE = True
    logger.info("TradierDataFetcher loaded via standard import")
except ImportError as e:
    logger.debug(f"Standard import failed: {e}")

# Method 2: Try direct file import (bypasses data/__init__.py)
if not TRADIER_AVAILABLE:
    try:
        import importlib.util
        import sys
        from pathlib import Path

        # Find the tradier_data_fetcher.py file
        # backend/api/routes/ares_routes.py -> go up 3 levels to project root
        project_root = Path(__file__).parent.parent.parent.parent
        tradier_path = project_root / 'data' / 'tradier_data_fetcher.py'

        if tradier_path.exists():
            spec = importlib.util.spec_from_file_location("tradier_direct", str(tradier_path))
            tradier_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(tradier_module)
            TradierDataFetcher = tradier_module.TradierDataFetcher
            TRADIER_AVAILABLE = True
            logger.info(f"TradierDataFetcher loaded via direct import from {tradier_path}")
        else:
            logger.warning(f"tradier_data_fetcher.py not found at {tradier_path}")
    except Exception as e:
        logger.warning(f"Direct import also failed: {e}")

if not TRADIER_AVAILABLE:
    logger.warning("TradierDataFetcher not available - ARES will use default capital")

# Try to import ARES V2 trader and strategy presets
ares_trader = None
try:
    from trading.ares_v2 import ARESTrader, TradingMode, StrategyPreset, STRATEGY_PRESETS
    # Note: ARES trader is initialized by scheduler, we query its state
    ARES_AVAILABLE = True
except ImportError:
    ARES_AVAILABLE = False
    StrategyPreset = None
    STRATEGY_PRESETS = {}
    logger.warning("ARES V2 module not available")


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


def _get_tradier_account_balance() -> dict:
    """
    Get account balance from Tradier API.

    Returns dict with:
    - total_equity: Account total value
    - option_buying_power: Available for options trading
    - sandbox: Whether using sandbox API
    - connected: Whether API call succeeded
    - error: Error message if connection failed
    """
    if not TRADIER_AVAILABLE or not TradierDataFetcher:
        logger.warning("TradierDataFetcher not available - using default capital")
        return {'connected': False, 'total_equity': 0, 'sandbox': True, 'error': 'TradierDataFetcher not imported'}

    try:
        # Try to get API config
        from unified_config import APIConfig

        # Check for credentials - try multiple sources
        # Priority: SANDBOX_* > PROD_* > generic TRADIER_*
        api_key = (
            getattr(APIConfig, 'TRADIER_SANDBOX_API_KEY', None) or
            getattr(APIConfig, 'TRADIER_PROD_API_KEY', None) or
            getattr(APIConfig, 'TRADIER_API_KEY', None)
        )
        account_id = (
            getattr(APIConfig, 'TRADIER_SANDBOX_ACCOUNT_ID', None) or
            getattr(APIConfig, 'TRADIER_PROD_ACCOUNT_ID', None) or
            getattr(APIConfig, 'TRADIER_ACCOUNT_ID', None)
        )

        # Check if sandbox mode is enabled (defaults to True for safety)
        use_sandbox = getattr(APIConfig, 'TRADIER_SANDBOX', True)

        logger.info(f"Tradier balance fetch: api_key={'SET' if api_key else 'NOT SET'}, account_id={account_id}, sandbox={use_sandbox}")

        if not api_key or not account_id:
            logger.warning("No Tradier credentials available for balance fetch")
            return {'connected': False, 'total_equity': 0, 'sandbox': use_sandbox, 'error': 'No credentials configured'}

        tradier = TradierDataFetcher(
            api_key=api_key,
            account_id=account_id,
            sandbox=use_sandbox
        )

        balance = tradier.get_account_balance()
        logger.info(f"Tradier balance response: {balance}")

        if balance:
            total_equity = balance.get('total_equity', 0)
            logger.info(f"Tradier balance fetch SUCCESS: total_equity=${total_equity:,.2f}")
            return {
                'connected': True,
                'total_equity': total_equity,
                'option_buying_power': balance.get('option_buying_power', 0),
                'sandbox': use_sandbox,
                'account_id': account_id
            }

        logger.warning("Tradier balance fetch returned empty response")
        return {'connected': False, 'total_equity': 0, 'sandbox': use_sandbox, 'error': 'Empty response from Tradier'}

    except Exception as e:
        logger.error(f"Tradier balance fetch ERROR: {e}")
        import traceback
        traceback.print_exc()
        return {'connected': False, 'total_equity': 0, 'sandbox': True, 'error': str(e)}


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
        # ARES not running in this process - read stats from database
        total_pnl = 0
        trade_count = 0
        win_count = 0
        open_count = 0
        closed_count = 0
        traded_today = False
        today = datetime.now(ZoneInfo("America/Chicago")).strftime('%Y-%m-%d')

        try:
            from database_adapter import get_connection
            conn = get_connection()
            cursor = conn.cursor()

            # Get summary stats
            cursor.execute('''
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 'open' THEN 1 ELSE 0 END) as open_count,
                    SUM(CASE WHEN status IN ('closed', 'expired') THEN 1 ELSE 0 END) as closed_count,
                    SUM(CASE WHEN status IN ('closed', 'expired') AND realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
                    COALESCE(SUM(CASE WHEN status IN ('closed', 'expired') THEN realized_pnl ELSE 0 END), 0) as total_pnl,
                    SUM(CASE WHEN open_date = %s THEN 1 ELSE 0 END) as traded_today
                FROM ares_positions
            ''', (today,))
            row = cursor.fetchone()
            conn.close()

            if row:
                trade_count = row[0] or 0
                open_count = row[1] or 0
                closed_count = row[2] or 0
                win_count = row[3] or 0
                total_pnl = float(row[4] or 0)
                traded_today = (row[5] or 0) > 0
        except Exception as db_err:
            logger.debug(f"Could not read ARES stats from database: {db_err}")

        win_rate = round((win_count / closed_count) * 100, 1) if closed_count > 0 else 0

        # Try to get stored mode and ticker from config table
        stored_mode = "paper"
        stored_ticker = "SPY"  # Default to SPY for sandbox
        try:
            from database_adapter import get_connection
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM autonomous_config WHERE key = 'ares_mode'")
            row = cursor.fetchone()
            if row:
                stored_mode = row[0]
            cursor.execute("SELECT value FROM autonomous_config WHERE key = 'ares_ticker'")
            row = cursor.fetchone()
            if row:
                stored_ticker = row[0]
            conn.close()
        except:
            pass

        # Get actual Tradier account balance instead of hardcoded value
        tradier_balance = _get_tradier_account_balance()
        if tradier_balance.get('connected') and tradier_balance.get('total_equity', 0) > 0:
            # Use actual Tradier balance
            capital = round(tradier_balance['total_equity'], 2)
            sandbox_connected = True
        else:
            # Fallback to default if Tradier unavailable
            capital = 100000  # Consistent default with frontend
            sandbox_connected = False

        return {
            "success": True,
            "data": {
                "mode": stored_mode,
                "ticker": stored_ticker,
                "is_spy_sandbox": stored_ticker == "SPY",
                "capital": capital,  # Now uses actual Tradier balance when available
                "total_pnl": round(total_pnl, 2),
                "trade_count": trade_count,
                "win_rate": win_rate,
                "open_positions": open_count,
                "closed_positions": closed_count,
                "traded_today": traded_today,
                "in_trading_window": False,
                "high_water_mark": capital,  # High water mark = current capital
                "current_time": datetime.now(ZoneInfo("America/Chicago")).strftime('%Y-%m-%d %H:%M:%S CT'),
                "is_active": False,
                "scan_interval_minutes": 5,
                "heartbeat": heartbeat,
                "sandbox_connected": sandbox_connected,
                "config": {
                    "risk_per_trade": 10.0,
                    "spread_width": 10.0,
                    "sd_multiplier": 1.0,
                    "ticker": stored_ticker,
                    "target_return": "10% monthly"
                },
                "source": "tradier" if sandbox_connected else "database",
                "message": "Capital synced with Tradier sandbox" if sandbox_connected else "Stats loaded from database - ARES worker running separately"
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
    # Always read from database for reliability
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Get open positions
        cursor.execute('''
            SELECT
                position_id, open_time, expiration,
                put_long_strike, put_short_strike, call_short_strike, call_long_strike,
                put_credit, call_credit, total_credit,
                contracts, spread_width, max_loss, status
            FROM ares_positions
            WHERE status = 'open'
            ORDER BY open_time DESC
        ''')
        open_rows = cursor.fetchall()

        # Get closed positions (last 100)
        cursor.execute('''
            SELECT
                position_id, open_time, close_time, expiration,
                put_long_strike, put_short_strike, call_short_strike, call_long_strike,
                put_credit, call_credit, total_credit,
                contracts, spread_width, max_loss, close_price, realized_pnl, status
            FROM ares_positions
            WHERE status IN ('closed', 'expired')
            ORDER BY close_time DESC
            LIMIT 100
        ''')
        closed_rows = cursor.fetchall()
        conn.close()

        # Format open positions
        open_positions = []
        for row in open_rows:
            pos_id, open_date, exp, put_long, put_short, call_short, call_long, \
                put_cr, call_cr, total_cr, contracts, spread_w, max_loss, status = row

            # Calculate DTE
            dte = 0
            if exp:
                try:
                    exp_date = datetime.strptime(str(exp), "%Y-%m-%d").date()
                    today = datetime.now(ZoneInfo("America/Chicago")).date()
                    dte = (exp_date - today).days
                except:
                    pass

            ticker = "SPY" if spread_w and spread_w <= 5 else "SPX"
            open_positions.append({
                "position_id": pos_id,
                "ticker": ticker,
                "open_date": str(open_date) if open_date else None,
                "expiration": str(exp) if exp else None,
                "dte": dte,
                "is_0dte": dte == 0,
                "put_long_strike": float(put_long) if put_long else 0,
                "put_short_strike": float(put_short) if put_short else 0,
                "call_short_strike": float(call_short) if call_short else 0,
                "call_long_strike": float(call_long) if call_long else 0,
                "put_spread": f"{put_long}/{put_short}P",
                "call_spread": f"{call_short}/{call_long}C",
                "put_credit": float(put_cr) if put_cr else 0,
                "call_credit": float(call_cr) if call_cr else 0,
                "total_credit": float(total_cr) if total_cr else 0,
                "contracts": contracts or 0,
                "spread_width": float(spread_w) if spread_w else 0,
                "max_loss": float(max_loss) if max_loss else 0,
                "premium_collected": float(total_cr or 0) * 100 * (contracts or 0),
                "status": status
            })

        # Format closed positions
        closed_positions = []
        for row in closed_rows:
            pos_id, open_date, close_date, exp, put_long, put_short, call_short, call_long, \
                put_cr, call_cr, total_cr, contracts, spread_w, max_loss, close_price, realized_pnl, \
                status = row

            max_profit = float(total_cr or 0) * 100 * (contracts or 0)
            return_pct = round((float(realized_pnl or 0) / max_profit) * 100, 1) if max_profit else 0
            ticker = "SPY" if spread_w and spread_w <= 5 else "SPX"

            closed_positions.append({
                "position_id": pos_id,
                "ticker": ticker,
                "open_date": str(open_date) if open_date else None,
                "close_date": str(close_date) if close_date else None,
                "expiration": str(exp) if exp else None,
                "put_long_strike": float(put_long) if put_long else 0,
                "put_short_strike": float(put_short) if put_short else 0,
                "call_short_strike": float(call_short) if call_short else 0,
                "call_long_strike": float(call_long) if call_long else 0,
                "put_spread": f"{put_long}/{put_short}P",
                "call_spread": f"{call_short}/{call_long}C",
                "contracts": contracts or 0,
                "spread_width": float(spread_w) if spread_w else 0,
                "total_credit": float(total_cr) if total_cr else 0,
                "max_profit": max_profit,
                "max_loss": float(max_loss) if max_loss else 0,
                "close_price": float(close_price) if close_price else 0,
                "realized_pnl": float(realized_pnl) if realized_pnl else 0,
                "return_pct": return_pct,
                "status": status
            })

        return {
            "success": True,
            "data": {
                "open_positions": open_positions,
                "closed_positions": closed_positions,
                "open_count": len(open_positions),
                "closed_count": len(closed_positions)
            }
        }
    except Exception as e:
        logger.error(f"Error getting ARES positions: {e}")
        return {
            "success": True,
            "data": {
                "open_positions": [],
                "closed_positions": [],
                "message": f"Could not load positions: {str(e)}"
            }
        }


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
        # ARES not running in this process - read from database directly
        try:
            from database_adapter import get_connection
            conn = get_connection()
            cursor = conn.cursor()

            # Get closed positions from database
            cursor.execute('''
                SELECT close_date, realized_pnl, position_id
                FROM ares_positions
                WHERE status IN ('closed', 'expired')
                AND close_date IS NOT NULL
                ORDER BY close_date ASC
            ''')
            rows = cursor.fetchall()
            conn.close()

            if rows:
                # Build equity curve from database positions
                equity_curve = []
                positions_by_date = {}
                for row in rows:
                    close_date, pnl, pos_id = row
                    date_key = str(close_date) if close_date else None
                    if date_key:
                        if date_key not in positions_by_date:
                            positions_by_date[date_key] = []
                        positions_by_date[date_key].append({'pnl': float(pnl or 0), 'id': pos_id})

                sorted_dates = sorted(positions_by_date.keys())
                cumulative_pnl = 0

                # Add starting point
                if sorted_dates:
                    equity_curve.append({
                        "date": sorted_dates[0],
                        "equity": starting_capital,
                        "pnl": 0,
                        "daily_pnl": 0,
                        "return_pct": 0
                    })

                for date_str in sorted_dates:
                    daily_pnl = sum(p['pnl'] for p in positions_by_date[date_str])
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

                # Add today's point if needed
                if equity_curve and equity_curve[-1]["date"] != today:
                    equity_curve.append({
                        "date": today,
                        "equity": round(starting_capital + cumulative_pnl, 2),
                        "pnl": round(cumulative_pnl, 2),
                        "daily_pnl": 0,
                        "return_pct": round((cumulative_pnl / starting_capital) * 100, 2)
                    })

                return {
                    "success": True,
                    "data": {
                        "equity_curve": equity_curve,
                        "starting_capital": starting_capital,
                        "current_equity": round(starting_capital + cumulative_pnl, 2),
                        "total_pnl": round(cumulative_pnl, 2),
                        "total_return_pct": round((cumulative_pnl / starting_capital) * 100, 2),
                        "closed_positions_count": len(rows),
                        "source": "database"
                    }
                }
        except Exception as db_err:
            logger.warning(f"Could not read equity curve from database: {db_err}")

        # Fallback: return starting equity point
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
                "message": "No closed positions found"
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


@router.get("/equity-curve/live")
async def get_ares_live_equity_curve():
    """
    Get ARES equity curve with live intraday progress.

    Returns historical equity curve plus today's current P&L including:
    - Historical realized P&L from closed positions
    - Today's realized P&L from positions closed today
    - Today's unrealized P&L from open positions (if ARES worker running)

    This gives a complete picture of intraday performance.
    """
    ares = get_ares_instance()
    starting_capital = 200000
    now = datetime.now(ZoneInfo("America/Chicago"))
    today = now.strftime('%Y-%m-%d')
    current_time = now.strftime('%H:%M:%S')

    # Check if market is open (8:30 AM - 3:00 PM CT on weekdays)
    is_market_hours = (
        now.weekday() < 5 and
        now.hour >= 8 and now.hour < 15 and
        (now.hour > 8 or now.minute >= 30)
    )

    try:
        from database_adapter import get_connection
        conn = get_connection()
        cursor = conn.cursor()

        # Get historical closed positions (excluding today for separate handling)
        cursor.execute('''
            SELECT close_date, realized_pnl, position_id
            FROM ares_positions
            WHERE status IN ('closed', 'expired')
            AND close_date IS NOT NULL
            AND close_date < %s
            ORDER BY close_date ASC
        ''', (today,))
        historical_rows = cursor.fetchall()

        # Get today's realized P&L
        cursor.execute('''
            SELECT COALESCE(SUM(realized_pnl), 0), COUNT(*)
            FROM ares_positions
            WHERE status IN ('closed', 'expired')
            AND close_date = %s
        ''', (today,))
        today_row = cursor.fetchone()
        today_realized = float(today_row[0]) if today_row else 0
        today_closed_count = today_row[1] if today_row else 0

        # Get open positions count
        cursor.execute('''
            SELECT COUNT(*), COALESCE(SUM(total_credit * 100 * contracts), 0)
            FROM ares_positions
            WHERE status = 'open'
        ''')
        open_row = cursor.fetchone()
        open_count = open_row[0] if open_row else 0
        open_credit = float(open_row[1]) if open_row else 0
        conn.close()

        # Build historical equity curve
        equity_curve = []
        positions_by_date = {}
        for row in historical_rows:
            close_date, pnl, pos_id = row
            date_key = str(close_date) if close_date else None
            if date_key:
                if date_key not in positions_by_date:
                    positions_by_date[date_key] = []
                positions_by_date[date_key].append(float(pnl or 0))

        sorted_dates = sorted(positions_by_date.keys())
        cumulative_pnl = 0

        # Add starting point
        if sorted_dates:
            equity_curve.append({
                "date": sorted_dates[0],
                "time": "09:30:00",
                "equity": starting_capital,
                "pnl": 0,
                "daily_pnl": 0,
                "return_pct": 0,
                "is_live": False
            })

        for date_str in sorted_dates:
            daily_pnl = sum(positions_by_date[date_str])
            cumulative_pnl += daily_pnl

            equity_curve.append({
                "date": date_str,
                "time": "15:00:00",
                "equity": round(starting_capital + cumulative_pnl, 2),
                "pnl": round(cumulative_pnl, 2),
                "daily_pnl": round(daily_pnl, 2),
                "return_pct": round((cumulative_pnl / starting_capital) * 100, 2),
                "is_live": False
            })

        # Get live unrealized P&L if ARES is running
        unrealized_pnl = 0
        has_live_data = False
        if ares:
            try:
                live_pnl = ares.get_live_pnl()
                unrealized_pnl = live_pnl.get('total_unrealized_pnl', 0) or 0
                has_live_data = True
            except Exception:
                pass

        # Add today's live point
        today_total_pnl = today_realized + unrealized_pnl
        current_cumulative = cumulative_pnl + today_total_pnl
        current_equity = starting_capital + current_cumulative

        # Add market open point for today if we have any activity
        if is_market_hours or today_realized != 0 or unrealized_pnl != 0:
            # Opening point
            equity_curve.append({
                "date": today,
                "time": "08:30:00",
                "equity": round(starting_capital + cumulative_pnl, 2),
                "pnl": round(cumulative_pnl, 2),
                "daily_pnl": 0,
                "return_pct": round((cumulative_pnl / starting_capital) * 100, 2),
                "is_live": False,
                "label": "Market Open"
            })

            # Current live point
            equity_curve.append({
                "date": today,
                "time": current_time,
                "equity": round(current_equity, 2),
                "pnl": round(current_cumulative, 2),
                "daily_pnl": round(today_total_pnl, 2),
                "daily_realized": round(today_realized, 2),
                "daily_unrealized": round(unrealized_pnl, 2) if has_live_data else None,
                "return_pct": round((current_cumulative / starting_capital) * 100, 2),
                "is_live": True,
                "label": "Current"
            })

        return {
            "success": True,
            "data": {
                "equity_curve": equity_curve,
                "starting_capital": starting_capital,
                "current_equity": round(current_equity, 2),
                "total_pnl": round(current_cumulative, 2),
                "total_return_pct": round((current_cumulative / starting_capital) * 100, 2),
                "today": {
                    "date": today,
                    "time": current_time,
                    "realized_pnl": round(today_realized, 2),
                    "unrealized_pnl": round(unrealized_pnl, 2) if has_live_data else None,
                    "total_pnl": round(today_total_pnl, 2),
                    "positions_closed": today_closed_count,
                    "positions_open": open_count,
                    "open_credit": round(open_credit, 2)
                },
                "is_market_open": is_market_hours,
                "has_live_data": has_live_data,
                "last_updated": now.isoformat()
            }
        }

    except Exception as e:
        logger.error(f"Error getting live equity curve: {e}")
        # Fallback
        return {
            "success": True,
            "data": {
                "equity_curve": [{
                    "date": today,
                    "time": current_time,
                    "equity": starting_capital,
                    "pnl": 0,
                    "daily_pnl": 0,
                    "return_pct": 0,
                    "is_live": True
                }],
                "starting_capital": starting_capital,
                "current_equity": starting_capital,
                "total_pnl": 0,
                "error": str(e)
            }
        }


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


@router.get("/logs")
async def get_ares_logs(
    level: Optional[str] = Query(None, description="Filter by level: DEBUG, INFO, WARNING, ERROR"),
    limit: int = Query(100, description="Max logs to return")
):
    """
    Get ARES logs for debugging and monitoring.
    """
    # Resolve Query objects for direct function calls (E2E tests)
    level = _resolve_query_param(level, None)
    limit = _resolve_query_param(limit, 100)

    try:
        conn = get_connection()
        c = conn.cursor()

        where_clause = ""
        params = []
        if level:
            where_clause = "WHERE level = %s"
            params.append(level)
        params.append(limit)

        c.execute(f"""
            SELECT
                id, created_at, level, message, details
            FROM ares_logs
            {where_clause}
            ORDER BY created_at DESC
            LIMIT %s
        """, tuple(params))

        rows = c.fetchall()
        conn.close()

        logs = []
        for row in rows:
            logs.append({
                "id": row[0],
                "created_at": row[1].isoformat() if row[1] else None,
                "level": row[2],
                "message": row[3],
                "details": row[4]
            })

        return {
            "success": True,
            "data": logs,
            "count": len(logs)
        }

    except Exception as e:
        logger.error(f"Error getting ARES logs: {e}")
        return {
            "success": True,
            "data": [],
            "count": 0,
            "message": "Log table not available"
        }


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
        # - TRADIER_PROD_* credentials take priority for production (supports SPX/VIX indexes)
        # - Otherwise, fall back to sandbox (only SPY available, estimate SPX)
        # This allows keeping sandbox creds in TRADIER_API_KEY while adding prod separately
        has_explicit_prod = APIConfig.TRADIER_PROD_API_KEY and APIConfig.TRADIER_PROD_ACCOUNT_ID
        sandbox_key = APIConfig.TRADIER_SANDBOX_API_KEY or APIConfig.TRADIER_API_KEY
        sandbox_account = APIConfig.TRADIER_SANDBOX_ACCOUNT_ID or APIConfig.TRADIER_ACCOUNT_ID

        tradier = None
        using_sandbox = False

        if has_explicit_prod:
            # Use explicit production credentials for market data
            try:
                tradier = TradierDataFetcher(
                    api_key=APIConfig.TRADIER_PROD_API_KEY,
                    account_id=APIConfig.TRADIER_PROD_ACCOUNT_ID,
                    sandbox=False
                )
                using_sandbox = False
                logger.info("ARES API: Using Tradier PRODUCTION API (TRADIER_PROD_* credentials)")
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
async def run_ares_cycle(
    request: Request,
    auth: AuthInfo = Depends(require_admin) if AUTH_AVAILABLE and require_admin else None
):
    """
    Manually trigger an ARES V2 trading cycle.

    This will attempt to open a new Iron Condor position if conditions are met.

    PROTECTED: Requires admin authentication. Only runs in paper mode for safety.
    """
    ares = get_ares_instance()

    if not ares:
        raise HTTPException(
            status_code=503,
            detail="ARES not initialized. Wait for scheduled startup."
        )

    try:
        # V2 uses run_cycle() instead of run_daily_cycle()
        result = ares.run_cycle()

        return {
            "success": True,
            "data": result,
            "message": "ARES V2 cycle completed"
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
        "entry_window": "08:30 - 15:55 CT",
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
                "entry_window": f"{config.entry_time_start} - {config.entry_time_end} CT",
                "target_return": "10% monthly (~0.5% daily)",
                "mode": ares.mode.value
            }
        }

    return {
        "success": True,
        "data": default_config
    }


@router.post("/sync-tradier")
async def sync_tradier_positions(
    request: Request,
    auth: AuthInfo = Depends(require_api_key) if AUTH_AVAILABLE and require_api_key else None
):
    """
    Sync positions from Tradier to AlphaGEX.

    Pulls current positions from Tradier account and identifies any
    that aren't already tracked in AlphaGEX. Useful for reconciliation
    after manual trades.

    PROTECTED: Requires API key authentication.
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

    today = datetime.now(ZoneInfo("America/Chicago")).strftime('%Y-%m-%d')

    if not ares:
        # ARES not running - read from database
        try:
            conn = get_connection()
            cursor = conn.cursor()

            # Get open positions with all entry context
            cursor.execute('''
                SELECT
                    position_id, open_date, expiration,
                    put_long_strike, put_short_strike,
                    call_short_strike, call_long_strike,
                    total_credit, contracts, max_loss, spread_width,
                    status
                FROM ares_positions
                WHERE status = 'open'
            ''')
            open_rows = cursor.fetchall()

            # Get today's realized P&L from closed positions
            cursor.execute('''
                SELECT COALESCE(SUM(realized_pnl), 0)
                FROM ares_positions
                WHERE status IN ('closed', 'expired')
                AND close_date = %s
            ''', (today,))
            realized_row = cursor.fetchone()
            today_realized = float(realized_row[0]) if realized_row else 0
            conn.close()

            # Format open positions with entry context
            positions = []
            today_date = datetime.now(ZoneInfo("America/Chicago")).date()

            for row in open_rows:
                (pos_id, open_date, exp, put_long, put_short, call_short, call_long,
                 credit, contracts, max_loss, spread_width, status) = row

                credit_received = float(credit or 0) * 100 * (contracts or 0)

                # Calculate DTE
                dte = None
                is_0dte = False
                try:
                    if exp:
                        exp_date = datetime.strptime(str(exp), '%Y-%m-%d').date()
                        dte = (exp_date - today_date).days
                        is_0dte = dte == 0
                except:
                    pass

                positions.append({
                    'position_id': pos_id,
                    'open_date': str(open_date) if open_date else None,
                    'expiration': str(exp) if exp else None,
                    'put_long_strike': float(put_long) if put_long else 0,
                    'put_short_strike': float(put_short) if put_short else 0,
                    'call_short_strike': float(call_short) if call_short else 0,
                    'call_long_strike': float(call_long) if call_long else 0,
                    'credit_received': round(credit_received, 2),
                    'contracts': contracts or 0,
                    'max_loss': round(float(max_loss or 0) * 100 * (contracts or 0), 2),
                    'spread_width': float(spread_width) if spread_width else 0,
                    'dte': dte,
                    'is_0dte': is_0dte,
                    'max_profit': round(credit_received, 2),
                    'strategy': 'IRON_CONDOR',
                    'direction': 'NEUTRAL',
                    # Live data not available from DB
                    'unrealized_pnl': None,
                    'profit_progress_pct': None,
                    'note': 'Live valuation requires ARES worker'
                })

            return {
                "success": True,
                "data": {
                    "total_unrealized_pnl": None,
                    "total_realized_pnl": round(today_realized, 2),
                    "net_pnl": round(today_realized, 2),
                    "positions": positions,
                    "position_count": len(positions),
                    "source": "database",
                    "message": "Open positions loaded from DB - live valuation requires ARES worker"
                }
            }
        except Exception as db_err:
            logger.warning(f"Could not read live P&L from database: {db_err}")

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

    # Check if ares has get_live_pnl method
    if not hasattr(ares, 'get_live_pnl'):
        # Method not available on this trader version - fall back to database
        logger.debug("ARES trader doesn't have get_live_pnl method, using database fallback")
        try:
            conn = get_connection()
            cursor = conn.cursor()

            # Get open positions
            cursor.execute('''
                SELECT
                    position_id, open_date, expiration,
                    put_long_strike, put_short_strike,
                    call_short_strike, call_long_strike,
                    total_credit, contracts, max_loss, spread_width, status
                FROM ares_positions
                WHERE status = 'open'
            ''')
            open_rows = cursor.fetchall()

            # Get today's realized P&L
            cursor.execute('''
                SELECT COALESCE(SUM(realized_pnl), 0)
                FROM ares_positions
                WHERE status IN ('closed', 'expired')
                AND close_date = %s
            ''', (today,))
            realized_row = cursor.fetchone()
            today_realized = float(realized_row[0]) if realized_row else 0
            conn.close()

            # Format positions
            positions = []
            today_date = datetime.now(ZoneInfo("America/Chicago")).date()

            for row in open_rows:
                (pos_id, open_date, exp, put_long, put_short, call_short, call_long,
                 credit, contracts, max_loss, spread_width, status) = row

                credit_received = float(credit or 0) * 100 * (contracts or 0)
                positions.append({
                    'position_id': pos_id,
                    'open_date': str(open_date) if open_date else None,
                    'expiration': str(exp) if exp else None,
                    'credit_received': round(credit_received, 2),
                    'contracts': contracts or 0,
                    'max_profit': round(credit_received, 2),
                    'unrealized_pnl': None,
                    'note': 'Live valuation not available'
                })

            return {
                "success": True,
                "data": {
                    "total_unrealized_pnl": None,
                    "total_realized_pnl": round(today_realized, 2),
                    "net_pnl": round(today_realized, 2),
                    "positions": positions,
                    "position_count": len(positions),
                    "source": "database",
                    "message": "Trader active but get_live_pnl not available"
                }
            }
        except Exception as db_err:
            logger.warning(f"Database fallback failed: {db_err}")
            return {
                "success": True,
                "data": {
                    "total_unrealized_pnl": 0,
                    "total_realized_pnl": 0,
                    "net_pnl": 0,
                    "positions": [],
                    "position_count": 0,
                    "message": "Could not retrieve live P&L"
                }
            }

    try:
        live_pnl = ares.get_live_pnl()

        return {
            "success": True,
            "data": live_pnl
        }
    except AttributeError as e:
        # Method exists but failed - shouldn't happen but handle gracefully
        logger.warning(f"ARES get_live_pnl attribute error: {e}")
        return {
            "success": True,
            "data": {
                "total_unrealized_pnl": 0,
                "total_realized_pnl": 0,
                "net_pnl": 0,
                "positions": [],
                "position_count": 0,
                "message": f"Live P&L method error: {str(e)}"
            }
        }
    except Exception as e:
        logger.error(f"Error getting ARES live P&L: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/process-expired")
async def process_expired_positions(
    request: Request,
    auth: AuthInfo = Depends(require_api_key) if AUTH_AVAILABLE and require_api_key else None
):
    """
    Manually trigger processing of all expired positions.

    This will process any positions that have expired but weren't processed
    due to service downtime or errors. Useful for catching up after outages.

    PROTECTED: Requires API key authentication.
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
async def skip_ares_today(
    request: Request,
    auth: AuthInfo = Depends(require_api_key) if AUTH_AVAILABLE and require_api_key else None
):
    """
    Skip trading for the rest of today.

    This will prevent ARES from opening any new positions until tomorrow.
    Existing positions will still be managed.

    PROTECTED: Requires API key authentication.
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
async def update_ares_config(
    updates: ARESConfigUpdate,
    request: Request,
    auth: AuthInfo = Depends(require_admin) if AUTH_AVAILABLE and require_admin else None
):
    """
    Update ARES configuration parameters.

    Supports updating (all validated by Pydantic):
    - risk_per_trade_pct: Risk per trade percentage (1-15)
    - sd_multiplier: Standard deviation multiplier (0.3-1.5)
    - spread_width: Spread width in dollars (5-50)
    - min_credit_per_spread: Minimum credit ($0.10-$10)
    - max_contracts: Maximum contracts per trade (1-1000)
    - use_stop_loss: Enable per-position stop loss
    - stop_loss_premium_multiple: Stop loss multiplier (1-5x)
    - profit_target_pct: Profit target percentage (10-90%)

    PROTECTED: Requires admin authentication.
    """
    ares = get_ares_instance()

    if not ares:
        raise HTTPException(
            status_code=503,
            detail="ARES not initialized. Wait for scheduled startup."
        )

    try:
        # Get only the fields that were provided (Pydantic already validated ranges)
        update_data = updates.model_dump(exclude_none=True) if MODELS_AVAILABLE else updates
        updated = {}

        # Apply each provided setting
        for field, value in update_data.items():
            if hasattr(ares.config, field):
                setattr(ares.config, field, value)
                updated[field] = value

        return {
            "success": True,
            "message": "Configuration updated successfully",
            "data": {
                "updated": updated,
                "current_config": {
                    "risk_per_trade_pct": ares.config.risk_per_trade_pct,
                    "sd_multiplier": ares.config.sd_multiplier,
                    "spread_width": ares.config.spread_width,
                    "min_credit_per_spread": ares.config.min_credit_per_spread,
                    "max_contracts": ares.config.max_contracts,
                    "use_stop_loss": ares.config.use_stop_loss,
                    "profit_target_pct": ares.config.profit_target_pct
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
async def set_strategy_preset(
    preset_request: StrategyPresetRequest,
    request: Request,
    auth: AuthInfo = Depends(require_admin) if AUTH_AVAILABLE and require_admin else None
):
    """
    Set the active strategy preset.

    Body (validated by Pydantic):
    - preset: Strategy preset ID (baseline, conservative, moderate, aggressive, wide_strikes)

    PROTECTED: Requires admin authentication.
    """
    ares = get_ares_instance()

    if not ares:
        raise HTTPException(
            status_code=503,
            detail="ARES not initialized. Wait for scheduled startup."
        )

    # Pydantic already validated the preset value
    preset_id = preset_request.preset.value if MODELS_AVAILABLE else preset_request.get("preset", "").lower()

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


def _enrich_scan_for_frontend(scan: dict) -> dict:
    """
    Enrich scan activity data with computed fields for frontend display.

    Adds:
    - top_factors: Decision factors with positive/negative impact
    - unlock_conditions: What would need to change for a trade (for NO_TRADE scans)
    - Structured ml_signal and oracle_signal objects
    """
    enriched = dict(scan)

    # Build top_factors from checks and reasoning
    top_factors = []

    # From checks performed
    checks = scan.get('checks_performed') or []
    for check in checks[:5]:  # Top 5 checks
        if isinstance(check, dict):
            check_name = check.get('check_name') or check.get('check', '')
            passed = check.get('passed', False)
            value = check.get('value', '')

            top_factors.append({
                'factor': check_name,
                'impact': 'positive' if passed else 'negative',
                'value': str(value) if value else None
            })

    # From signal confidence
    signal_conf = scan.get('signal_confidence')
    if signal_conf is not None:
        top_factors.append({
            'factor': 'Signal Confidence',
            'impact': 'positive' if signal_conf > 0.6 else 'negative' if signal_conf < 0.4 else 'neutral',
            'value': f"{float(signal_conf) * 100:.0f}%"
        })

    # From VIX
    vix = scan.get('vix')
    if vix is not None:
        top_factors.append({
            'factor': 'VIX Level',
            'impact': 'positive' if 15 <= float(vix) <= 25 else 'negative',
            'value': f"{float(vix):.1f}"
        })

    # From GEX regime
    gex_regime = scan.get('gex_regime')
    if gex_regime:
        top_factors.append({
            'factor': 'GEX Regime',
            'impact': 'positive' if gex_regime in ['POSITIVE', 'BULLISH'] else 'neutral',
            'value': gex_regime
        })

    enriched['top_factors'] = top_factors[:4]  # Limit to 4

    # Build unlock_conditions for NO_TRADE scans
    unlock_conditions = []
    if scan.get('outcome') in ['NO_TRADE', 'SKIP']:
        for check in checks:
            if isinstance(check, dict) and not check.get('passed', True):
                check_name = check.get('check_name') or check.get('check', '')
                value = check.get('value', 'N/A')
                threshold = check.get('threshold', 'N/A')

                unlock_conditions.append({
                    'condition': check_name,
                    'current_value': str(value),
                    'required_value': str(threshold),
                    'met': False,
                    'probability': 0.3  # Default estimate
                })

        # Add common unlock conditions if none from checks
        if not unlock_conditions:
            oracle_advice = scan.get('oracle_advice', '')
            if oracle_advice in ['HOLD', 'SKIP_TODAY', 'REDUCE_SIZE']:
                unlock_conditions.append({
                    'condition': 'Oracle Advice',
                    'current_value': oracle_advice,
                    'required_value': 'TRADE',
                    'met': False,
                    'probability': 0.2
                })

    enriched['unlock_conditions'] = unlock_conditions

    # Structure ML signal
    if scan.get('signal_direction') or scan.get('signal_confidence'):
        enriched['ml_signal'] = {
            'direction': scan.get('signal_direction', 'NEUTRAL'),
            'confidence': float(scan.get('signal_confidence', 0)),
            'advice': scan.get('signal_source', 'ML'),
            'top_factors': []  # Could add ML-specific factors
        }

    # Structure Oracle signal
    if scan.get('oracle_advice') or scan.get('signal_win_probability'):
        enriched['oracle_signal'] = {
            'advice': scan.get('oracle_advice', 'HOLD'),
            'confidence': float(scan.get('signal_confidence', 0)),
            'win_probability': float(scan.get('signal_win_probability', 0)),
            'reasoning': scan.get('oracle_reasoning'),
            'top_factors': []
        }

    # Structure market context
    enriched['market_context'] = {
        'spot_price': float(scan.get('underlying_price', 0)) if scan.get('underlying_price') else 0,
        'vix': float(scan.get('vix', 0)) if scan.get('vix') else 0,
        'gex_regime': scan.get('gex_regime', 'Unknown'),
        'put_wall': float(scan.get('put_wall', 0)) if scan.get('put_wall') else None,
        'call_wall': float(scan.get('call_wall', 0)) if scan.get('call_wall') else None,
        'flip_point': None,  # Could compute from walls
        'flip_distance_pct': None
    }

    # Determine if override occurred
    signal_source = scan.get('signal_source', '')
    if 'Override' in str(signal_source) or 'override' in str(signal_source):
        enriched['override_occurred'] = True
        enriched['override_details'] = {
            'winner': 'Oracle' if 'Oracle' in signal_source else 'ML',
            'overridden_signal': scan.get('signal_direction', 'Unknown'),
            'override_reason': scan.get('decision_summary', 'Override applied')
        }
    else:
        enriched['override_occurred'] = False

    return enriched


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

        # Enrich scans with frontend-friendly fields
        enriched_scans = [_enrich_scan_for_frontend(scan) for scan in scans]

        return {
            "success": True,
            "data": {
                "count": len(enriched_scans),
                "summary": {
                    "trades_executed": trades,
                    "no_trade_scans": no_trades,
                    "skips": skips,
                    "errors": errors
                },
                "scans": enriched_scans
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
