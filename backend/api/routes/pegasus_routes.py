"""
PEGASUS SPX Iron Condor Bot API Routes
========================================

API endpoints for the PEGASUS SPX Iron Condor trading bot.
Trades SPX options with $10 spread widths using SPXW weekly options.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Request, Query
from zoneinfo import ZoneInfo

from database_adapter import get_connection

# Authentication middleware
try:
    from backend.api.auth_middleware import require_api_key, require_admin, AuthInfo
    AUTH_AVAILABLE = True
except ImportError:
    AUTH_AVAILABLE = False
    require_api_key = None
    require_admin = None

router = APIRouter(prefix="/api/pegasus", tags=["PEGASUS"])
logger = logging.getLogger(__name__)

# Try to import Tradier for account balance (same pattern as ARES)
TradierDataFetcher = None
TRADIER_AVAILABLE = False

try:
    from data.tradier_data_fetcher import TradierDataFetcher
    TRADIER_AVAILABLE = True
    logger.info("TradierDataFetcher loaded for PEGASUS")
except ImportError as e:
    logger.debug(f"TradierDataFetcher import failed: {e}")

if not TRADIER_AVAILABLE:
    try:
        import importlib.util
        from pathlib import Path
        project_root = Path(__file__).parent.parent.parent.parent
        tradier_path = project_root / 'data' / 'tradier_data_fetcher.py'
        if tradier_path.exists():
            spec = importlib.util.spec_from_file_location("tradier_direct", str(tradier_path))
            tradier_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(tradier_module)
            TradierDataFetcher = tradier_module.TradierDataFetcher
            TRADIER_AVAILABLE = True
            logger.info(f"TradierDataFetcher loaded via direct import for PEGASUS")
    except Exception as e:
        logger.warning(f"Direct Tradier import failed for PEGASUS: {e}")


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


# Try to import PEGASUS trader
pegasus_trader = None
try:
    from trading.pegasus import PEGASUSTrader, PEGASUSConfig, TradingMode, StrategyPreset
    PEGASUS_AVAILABLE = True
except ImportError as e:
    PEGASUS_AVAILABLE = False
    PEGASUSConfig = None
    StrategyPreset = None
    logger.warning(f"PEGASUS module not available: {e}")


def get_pegasus_instance():
    """Get the PEGASUS trader instance from scheduler if available"""
    global pegasus_trader
    if pegasus_trader:
        return pegasus_trader

    try:
        from scheduler.trader_scheduler import get_pegasus_trader
        pegasus_trader = get_pegasus_trader()
        return pegasus_trader
    except Exception:
        return None


def _get_tradier_account_balance() -> dict:
    """
    Get account balance from Tradier API for PEGASUS.
    Same pattern as ARES for consistency.
    """
    if not TRADIER_AVAILABLE or not TradierDataFetcher:
        return {'connected': False, 'total_equity': 0, 'sandbox': True, 'error': 'TradierDataFetcher not imported'}

    try:
        from unified_config import APIConfig

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
        use_sandbox = getattr(APIConfig, 'TRADIER_SANDBOX', True)

        if not api_key or not account_id:
            return {'connected': False, 'total_equity': 0, 'sandbox': use_sandbox, 'error': 'No credentials configured'}

        tradier = TradierDataFetcher(api_key=api_key, account_id=account_id, sandbox=use_sandbox)
        balance = tradier.get_account_balance()

        if balance:
            return {
                'connected': True,
                'total_equity': balance.get('total_equity', 0),
                'option_buying_power': balance.get('option_buying_power', 0),
                'sandbox': use_sandbox,
                'account_id': account_id
            }

        return {'connected': False, 'total_equity': 0, 'sandbox': use_sandbox, 'error': 'Empty response from Tradier'}

    except Exception as e:
        logger.error(f"PEGASUS Tradier balance fetch ERROR: {e}")
        return {'connected': False, 'total_equity': 0, 'sandbox': True, 'error': str(e)}


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

            if last_heartbeat:
                if last_heartbeat.tzinfo is None:
                    last_heartbeat = last_heartbeat.replace(tzinfo=ZoneInfo("UTC"))
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
async def get_pegasus_status():
    """
    Get current PEGASUS bot status.

    Returns mode, capital, P&L, positions, configuration, and heartbeat.
    """
    pegasus = get_pegasus_instance()
    heartbeat = _get_heartbeat('PEGASUS')

    if not pegasus:
        # PEGASUS not running - read stats from database
        starting_capital = 200000
        total_pnl = 0
        trade_count = 0
        win_count = 0
        open_count = 0
        closed_count = 0
        traded_today = False
        today = datetime.now(ZoneInfo("America/Chicago")).strftime('%Y-%m-%d')

        try:
            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute('''
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 'open' THEN 1 ELSE 0 END) as open_count,
                    SUM(CASE WHEN status IN ('closed', 'expired') THEN 1 ELSE 0 END) as closed_count,
                    SUM(CASE WHEN status IN ('closed', 'expired') AND realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
                    COALESCE(SUM(CASE WHEN status IN ('closed', 'expired') THEN realized_pnl ELSE 0 END), 0) as total_pnl,
                    SUM(CASE WHEN DATE(open_time AT TIME ZONE 'America/Chicago') = %s THEN 1 ELSE 0 END) as traded_today
                FROM pegasus_positions
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
            logger.debug(f"Could not read PEGASUS stats from database: {db_err}")

        win_rate = round((win_count / closed_count) * 100, 1) if closed_count > 0 else 0

        # Get Tradier account balance - PEGASUS should be connected
        tradier_balance = _get_tradier_account_balance()

        if tradier_balance.get('connected') and tradier_balance.get('total_equity', 0) > 0:
            capital = round(tradier_balance['total_equity'], 2)
            sandbox_connected = True
            tradier_error = None
            capital_message = f"Connected to Tradier {'sandbox' if tradier_balance.get('sandbox') else 'production'}"
        else:
            tradier_error = tradier_balance.get('error', 'Unknown connection error')
            sandbox_connected = False
            capital = 200000  # Paper capital for display
            capital_message = f"ERROR: Not connected to Tradier - {tradier_error}"
            logger.error(f"PEGASUS Tradier connection failed: {tradier_error}")

        return {
            "success": True,
            "data": {
                "mode": "paper" if not sandbox_connected else "sandbox",
                "ticker": "SPX",
                "capital": capital,
                "capital_source": "tradier" if sandbox_connected else "paper_fallback",
                "total_pnl": round(total_pnl, 2),
                "trade_count": trade_count,
                "win_rate": win_rate,
                "open_positions": open_count,
                "closed_positions": closed_count,
                "traded_today": traded_today,
                "in_trading_window": False,
                "high_water_mark": capital,
                "current_time": datetime.now(ZoneInfo("America/Chicago")).strftime('%Y-%m-%d %H:%M:%S CT'),
                "is_active": False,
                "scan_interval_minutes": 5,
                "heartbeat": heartbeat,
                "sandbox_connected": sandbox_connected,
                "tradier_error": tradier_error,
                "tradier_account_id": tradier_balance.get('account_id') if sandbox_connected else None,
                "config": {
                    "risk_per_trade": 10.0,
                    "spread_width": 10.0,
                    "sd_multiplier": 1.0,
                    "ticker": "SPX"
                },
                "source": "tradier" if sandbox_connected else "error",
                "message": capital_message
            }
        }

    try:
        status = pegasus.get_status()
        status['is_active'] = True
        status['scan_interval_minutes'] = 5
        status['heartbeat'] = heartbeat

        return {
            "success": True,
            "data": status
        }
    except Exception as e:
        logger.error(f"Error getting PEGASUS status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/positions")
async def get_pegasus_positions():
    """
    Get PEGASUS open and recently closed positions.

    Returns Iron Condor positions with full details.
    """
    pegasus = get_pegasus_instance()

    if not pegasus:
        # PEGASUS not running - read from database directly
        try:
            conn = get_connection()
            cursor = conn.cursor()

            # Get open positions with FULL audit trail context
            cursor.execute('''
                SELECT
                    position_id, expiration,
                    put_long_strike, put_short_strike, call_short_strike, call_long_strike,
                    put_credit, call_credit, total_credit,
                    contracts, spread_width, max_loss,
                    underlying_at_entry, vix_at_entry, status,
                    -- GEX context
                    gex_regime, call_wall, put_wall, flip_point, net_gex,
                    -- Oracle audit trail
                    oracle_confidence, oracle_win_probability, oracle_advice,
                    oracle_reasoning, oracle_top_factors,
                    -- Timing
                    open_time
                FROM pegasus_positions
                WHERE status = 'open'
                ORDER BY open_time DESC
            ''')
            open_rows = cursor.fetchall()

            # Get closed positions (last 100) with FULL audit trail context
            cursor.execute('''
                SELECT
                    position_id, expiration,
                    put_long_strike, put_short_strike, call_short_strike, call_long_strike,
                    put_credit, call_credit, total_credit,
                    contracts, spread_width, max_loss, close_price, realized_pnl,
                    underlying_at_entry, vix_at_entry, status, close_reason,
                    -- GEX context
                    gex_regime, call_wall, put_wall, flip_point, net_gex,
                    -- Oracle audit trail
                    oracle_confidence, oracle_win_probability, oracle_advice,
                    oracle_reasoning, oracle_top_factors,
                    -- Timing
                    open_time, close_time
                FROM pegasus_positions
                WHERE status IN ('closed', 'expired')
                ORDER BY close_time DESC
                LIMIT 100
            ''')
            closed_rows = cursor.fetchall()
            conn.close()

            # Format open positions with FULL audit trail context
            open_positions = []
            for row in open_rows:
                (pos_id, exp, put_long, put_short, call_short, call_long,
                 put_cr, call_cr, total_cr, contracts, spread_w, max_loss,
                 underlying, vix, status,
                 gex_regime, call_wall, put_wall, flip_point, net_gex,
                 oracle_confidence, oracle_win_prob, oracle_advice,
                 oracle_reasoning, oracle_top_factors,
                 open_time) = row

                dte = 0
                if exp:
                    try:
                        exp_date = datetime.strptime(str(exp), "%Y-%m-%d").date()
                        today = datetime.now(ZoneInfo("America/Chicago")).date()
                        dte = (exp_date - today).days
                    except:
                        pass

                # Format open_time to Central Time
                open_time_ct = None
                if open_time:
                    if open_time.tzinfo is None:
                        open_time = open_time.replace(tzinfo=ZoneInfo("UTC"))
                    open_time_ct = open_time.astimezone(ZoneInfo("America/Chicago"))

                open_positions.append({
                    "position_id": pos_id,
                    "ticker": "SPX",
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
                    "underlying_at_entry": float(underlying) if underlying else 0,
                    "vix_at_entry": float(vix) if vix else 0,
                    "status": status,
                    # GEX context (AUDIT TRAIL)
                    "gex_regime": gex_regime or "NEUTRAL",
                    "call_wall": float(call_wall) if call_wall else 0,
                    "put_wall": float(put_wall) if put_wall else 0,
                    "flip_point": float(flip_point) if flip_point else 0,
                    "net_gex": float(net_gex) if net_gex else 0,
                    # Oracle context (AUDIT TRAIL - why this trade was chosen)
                    "oracle_confidence": float(oracle_confidence) if oracle_confidence else 0,
                    "oracle_win_probability": float(oracle_win_prob) if oracle_win_prob else 0,
                    "oracle_advice": oracle_advice or "",
                    "oracle_reasoning": oracle_reasoning or "",
                    "oracle_top_factors": oracle_top_factors or "",
                    # Timing (Central Time)
                    "open_time": open_time_ct.strftime('%Y-%m-%d %H:%M:%S CT') if open_time_ct else None,
                    "open_time_iso": open_time_ct.isoformat() if open_time_ct else None,
                })

            # Format closed positions with FULL audit trail context
            closed_positions = []
            for row in closed_rows:
                (pos_id, exp, put_long, put_short, call_short, call_long,
                 put_cr, call_cr, total_cr, contracts, spread_w, max_loss, close_price, realized_pnl,
                 underlying, vix, status, close_reason,
                 gex_regime, call_wall, put_wall, flip_point, net_gex,
                 oracle_confidence, oracle_win_prob, oracle_advice,
                 oracle_reasoning, oracle_top_factors,
                 open_time, close_time) = row

                max_profit = float(total_cr or 0) * 100 * (contracts or 0)
                return_pct = round((float(realized_pnl or 0) / max_profit) * 100, 1) if max_profit else 0

                # Format times to Central Time
                open_time_ct = None
                if open_time:
                    if open_time.tzinfo is None:
                        open_time = open_time.replace(tzinfo=ZoneInfo("UTC"))
                    open_time_ct = open_time.astimezone(ZoneInfo("America/Chicago"))

                close_time_ct = None
                if close_time:
                    if close_time.tzinfo is None:
                        close_time = close_time.replace(tzinfo=ZoneInfo("UTC"))
                    close_time_ct = close_time.astimezone(ZoneInfo("America/Chicago"))

                closed_positions.append({
                    "position_id": pos_id,
                    "ticker": "SPX",
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
                    "close_reason": close_reason,
                    "underlying_at_entry": float(underlying) if underlying else 0,
                    "vix_at_entry": float(vix) if vix else 0,
                    "status": status,
                    # GEX context (AUDIT TRAIL)
                    "gex_regime": gex_regime or "NEUTRAL",
                    "call_wall": float(call_wall) if call_wall else 0,
                    "put_wall": float(put_wall) if put_wall else 0,
                    "flip_point": float(flip_point) if flip_point else 0,
                    "net_gex": float(net_gex) if net_gex else 0,
                    # Oracle context (AUDIT TRAIL - why this trade was chosen)
                    "oracle_confidence": float(oracle_confidence) if oracle_confidence else 0,
                    "oracle_win_probability": float(oracle_win_prob) if oracle_win_prob else 0,
                    "oracle_advice": oracle_advice or "",
                    "oracle_reasoning": oracle_reasoning or "",
                    "oracle_top_factors": oracle_top_factors or "",
                    # Timing (Central Time)
                    "open_time": open_time_ct.strftime('%Y-%m-%d %H:%M:%S CT') if open_time_ct else None,
                    "open_time_iso": open_time_ct.isoformat() if open_time_ct else None,
                    "close_time": close_time_ct.strftime('%Y-%m-%d %H:%M:%S CT') if close_time_ct else None,
                    "close_time_iso": close_time_ct.isoformat() if close_time_ct else None,
                })

            return {
                "success": True,
                "data": {
                    "open_positions": open_positions,
                    "closed_positions": closed_positions,
                    "open_count": len(open_positions),
                    "closed_count": len(closed_positions),
                    "source": "database"
                }
            }
        except Exception as db_err:
            logger.warning(f"Could not read positions from database: {db_err}")

        return {
            "success": True,
            "data": {
                "open_positions": [],
                "closed_positions": [],
                "message": "No positions found"
            }
        }

    try:
        positions = pegasus.get_positions()
        open_positions = []
        for pos in positions:
            dte = 0
            if pos.expiration:
                try:
                    exp_date = datetime.strptime(pos.expiration, "%Y-%m-%d").date()
                    today = datetime.now(ZoneInfo("America/Chicago")).date()
                    dte = (exp_date - today).days
                except:
                    pass

            open_positions.append({
                "position_id": pos.position_id,
                "ticker": "SPX",
                "expiration": pos.expiration,
                "dte": dte,
                "is_0dte": dte == 0,
                "put_long_strike": pos.put_long_strike,
                "put_short_strike": pos.put_short_strike,
                "call_short_strike": pos.call_short_strike,
                "call_long_strike": pos.call_long_strike,
                "put_spread": f"{pos.put_long_strike}/{pos.put_short_strike}P",
                "call_spread": f"{pos.call_short_strike}/{pos.call_long_strike}C",
                "put_credit": pos.put_credit,
                "call_credit": pos.call_credit,
                "total_credit": pos.total_credit,
                "contracts": pos.contracts,
                "spread_width": pos.spread_width,
                "max_loss": pos.max_loss,
                "max_profit": pos.max_profit,
                "premium_collected": pos.total_credit * 100 * pos.contracts,
                "underlying_at_entry": pos.underlying_at_entry,
                "vix_at_entry": pos.vix_at_entry,
                "status": pos.status.value
            })

        return {
            "success": True,
            "data": {
                "open_positions": open_positions,
                "closed_positions": [],
                "open_count": len(open_positions),
                "closed_count": 0
            }
        }
    except Exception as e:
        logger.error(f"Error getting PEGASUS positions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/equity-curve")
async def get_pegasus_equity_curve(days: int = 30):
    """
    Get PEGASUS equity curve data.

    Args:
        days: Number of days of history (default 30)

    Returns equity curve built from closed positions.
    """
    starting_capital = 200000
    today = datetime.now(ZoneInfo("America/Chicago")).strftime('%Y-%m-%d')

    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT DATE(close_time AT TIME ZONE 'America/Chicago') as close_date,
                   realized_pnl, position_id
            FROM pegasus_positions
            WHERE status IN ('closed', 'expired')
            AND close_time IS NOT NULL
            ORDER BY close_time ASC
        ''')
        rows = cursor.fetchall()
        conn.close()

        if rows:
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


@router.post("/run-cycle")
async def run_pegasus_cycle(
    request: Request,
    auth: AuthInfo = Depends(require_admin) if AUTH_AVAILABLE and require_admin else None
):
    """
    Manually trigger a PEGASUS trading cycle.

    This will attempt to open a new SPX Iron Condor position if conditions are met.

    PROTECTED: Requires admin authentication.
    """
    pegasus = get_pegasus_instance()

    if not pegasus:
        raise HTTPException(
            status_code=503,
            detail="PEGASUS not initialized. Wait for scheduled startup."
        )

    try:
        result = pegasus.run_cycle()

        return {
            "success": True,
            "data": result,
            "message": "PEGASUS cycle completed"
        }
    except Exception as e:
        logger.error(f"Error running PEGASUS cycle: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/config")
async def get_pegasus_config():
    """
    Get PEGASUS configuration parameters.
    """
    pegasus = get_pegasus_instance()

    default_config = {
        "ticker": "SPX",
        "spread_width": 10.0,
        "risk_per_trade_pct": 10.0,
        "sd_multiplier": 1.0,
        "min_credit": 1.50,
        "profit_target_pct": 50,
        "use_stop_loss": False,
        "entry_window": "08:30 - 15:55 CT",
        "description": "PEGASUS trades SPX Iron Condors with $10 spread widths using SPXW weekly options."
    }

    if pegasus and hasattr(pegasus, 'config'):
        config = pegasus.config
        return {
            "success": True,
            "data": {
                "ticker": "SPX",
                "spread_width": config.spread_width,
                "risk_per_trade_pct": config.risk_per_trade_pct,
                "sd_multiplier": config.sd_multiplier,
                "min_credit": config.min_credit,
                "profit_target_pct": config.profit_target_pct,
                "use_stop_loss": config.use_stop_loss,
                "entry_window": f"{config.entry_start} - {config.entry_end} CT",
                "mode": config.mode.value
            }
        }

    return {
        "success": True,
        "data": default_config
    }


@router.post("/force-close")
async def force_close_pegasus_positions(
    request: Request,
    auth: AuthInfo = Depends(require_admin) if AUTH_AVAILABLE and require_admin else None
):
    """
    Force close all open PEGASUS positions.

    PROTECTED: Requires admin authentication.
    """
    pegasus = get_pegasus_instance()

    if not pegasus:
        raise HTTPException(
            status_code=503,
            detail="PEGASUS not initialized."
        )

    try:
        result = pegasus.force_close_all("MANUAL")

        return {
            "success": True,
            "data": result,
            "message": f"Closed {result.get('closed', 0)} positions"
        }
    except Exception as e:
        logger.error(f"Error force closing PEGASUS positions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/live-pnl")
async def get_pegasus_live_pnl():
    """
    Get real-time unrealized P&L for all open PEGASUS positions.
    """
    pegasus = get_pegasus_instance()
    today = datetime.now(ZoneInfo("America/Chicago")).strftime('%Y-%m-%d')

    if not pegasus:
        try:
            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute('''
                SELECT
                    position_id, expiration,
                    put_long_strike, put_short_strike,
                    call_short_strike, call_long_strike,
                    total_credit, contracts, max_loss, spread_width,
                    underlying_at_entry, vix_at_entry
                FROM pegasus_positions
                WHERE status = 'open'
            ''')
            open_rows = cursor.fetchall()

            cursor.execute('''
                SELECT COALESCE(SUM(realized_pnl), 0)
                FROM pegasus_positions
                WHERE status IN ('closed', 'expired')
                AND DATE(close_time AT TIME ZONE 'America/Chicago') = %s
            ''', (today,))
            realized_row = cursor.fetchone()
            today_realized = float(realized_row[0]) if realized_row else 0
            conn.close()

            positions = []
            for row in open_rows:
                (pos_id, exp, put_long, put_short, call_short, call_long,
                 credit, contracts, max_loss, spread_width, entry_price, vix_entry) = row

                credit_received = float(credit or 0) * 100 * (contracts or 0)

                positions.append({
                    'position_id': pos_id,
                    'expiration': str(exp) if exp else None,
                    'put_long_strike': float(put_long) if put_long else 0,
                    'put_short_strike': float(put_short) if put_short else 0,
                    'call_short_strike': float(call_short) if call_short else 0,
                    'call_long_strike': float(call_long) if call_long else 0,
                    'credit_received': round(credit_received, 2),
                    'contracts': contracts or 0,
                    'max_loss': round(float(max_loss or 0) * 100 * (contracts or 0), 2),
                    'underlying_at_entry': float(entry_price) if entry_price else 0,
                    'vix_at_entry': float(vix_entry) if vix_entry else 0,
                    'unrealized_pnl': None,
                    'note': 'Live valuation requires PEGASUS worker'
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
                    "message": "Open positions loaded from DB - live valuation requires PEGASUS worker"
                }
            }
        except Exception as db_err:
            logger.warning(f"Could not read PEGASUS live P&L from database: {db_err}")

        return {
            "success": True,
            "data": {
                "total_unrealized_pnl": 0,
                "total_realized_pnl": 0,
                "net_pnl": 0,
                "positions": [],
                "position_count": 0,
                "message": "PEGASUS not initialized"
            }
        }

    try:
        status = pegasus.get_status()
        positions = pegasus.get_positions()

        return {
            "success": True,
            "data": {
                "total_unrealized_pnl": status.get('unrealized_pnl', 0),
                "total_realized_pnl": 0,
                "net_pnl": status.get('unrealized_pnl', 0),
                "positions": [
                    {
                        'position_id': p.position_id,
                        'expiration': p.expiration,
                        'credit_received': p.total_credit * 100 * p.contracts,
                        'contracts': p.contracts,
                        'status': p.status.value
                    }
                    for p in positions
                ],
                "position_count": len(positions)
            }
        }
    except Exception as e:
        logger.error(f"Error getting PEGASUS live P&L: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/logs")
async def get_pegasus_logs(
    level: Optional[str] = Query(None, description="Filter by level: DEBUG, INFO, WARNING, ERROR"),
    limit: int = Query(100, description="Max logs to return")
):
    """
    Get PEGASUS logs for debugging and monitoring.
    """
    # Resolve Query objects for direct function calls (E2E tests)
    level = _resolve_query_param(level, None)
    limit = _resolve_query_param(limit, 100)

    try:
        conn = get_connection()
        c = conn.cursor()

        where_clause = "WHERE bot_name = 'PEGASUS'"
        params = []
        if level:
            where_clause += " AND log_level = %s"
            params.append(level)
        params.append(limit)

        c.execute(f"""
            SELECT
                id, created_at, log_level, message, details
            FROM pegasus_logs
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
        # If pegasus_logs table doesn't exist, try bot_logs
        try:
            conn = get_connection()
            c = conn.cursor()

            where_clause = "WHERE bot_name = 'PEGASUS'"
            params = []
            if level:
                where_clause += " AND level = %s"
                params.append(level)
            params.append(limit)

            c.execute(f"""
                SELECT
                    id, created_at, level, message, details
                FROM bot_logs
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
        except Exception:
            pass

        logger.error(f"Error getting PEGASUS logs: {e}")
        return {
            "success": True,
            "data": [],
            "count": 0,
            "message": "Log table not available"
        }


@router.get("/performance")
async def get_pegasus_performance(
    days: int = Query(30, description="Number of days to include")
):
    """
    Get PEGASUS performance metrics over time.
    """
    # Resolve Query objects for direct function calls (E2E tests)
    days = _resolve_query_param(days, 30)

    try:
        conn = get_connection()
        c = conn.cursor()

        # Get closed positions for performance calculation
        c.execute("""
            SELECT
                DATE(close_time AT TIME ZONE 'America/Chicago') as trade_date,
                COUNT(*) as trades_executed,
                SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as trades_won,
                SUM(CASE WHEN realized_pnl <= 0 THEN 1 ELSE 0 END) as trades_lost,
                COALESCE(SUM(realized_pnl), 0) as net_pnl
            FROM pegasus_positions
            WHERE status IN ('closed', 'expired')
            AND close_time >= CURRENT_DATE - INTERVAL '%s days'
            GROUP BY DATE(close_time AT TIME ZONE 'America/Chicago')
            ORDER BY trade_date DESC
        """, (days,))

        rows = c.fetchall()

        # Calculate summary stats
        c.execute("""
            SELECT
                COUNT(*) as total_trades,
                SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as total_wins,
                COALESCE(SUM(realized_pnl), 0) as total_pnl
            FROM pegasus_positions
            WHERE status IN ('closed', 'expired')
            AND close_time >= CURRENT_DATE - INTERVAL '%s days'
        """, (days,))

        summary_row = c.fetchone()
        conn.close()

        daily_data = []
        for row in rows:
            trades = row[1] or 0
            wins = row[2] or 0
            win_rate = (wins / trades * 100) if trades > 0 else 0

            daily_data.append({
                "date": str(row[0]),
                "trades": trades,
                "wins": wins,
                "losses": row[3] or 0,
                "win_rate": round(win_rate, 1),
                "net_pnl": float(row[4]) if row[4] else 0
            })

        total_trades = summary_row[0] if summary_row else 0
        total_wins = summary_row[1] if summary_row else 0
        avg_win_rate = (total_wins / total_trades * 100) if total_trades > 0 else 0

        return {
            "success": True,
            "data": {
                "summary": {
                    "total_trades": total_trades,
                    "total_wins": total_wins,
                    "total_pnl": float(summary_row[2]) if summary_row and summary_row[2] else 0,
                    "avg_win_rate": round(avg_win_rate, 1)
                },
                "daily": daily_data
            }
        }

    except Exception as e:
        logger.error(f"Error getting PEGASUS performance: {e}")
        return {
            "success": True,
            "data": {
                "summary": {
                    "total_trades": 0,
                    "total_wins": 0,
                    "total_pnl": 0,
                    "avg_win_rate": 0
                },
                "daily": []
            },
            "message": "Performance data not available"
        }


@router.post("/reset")
async def reset_pegasus_data(confirm: bool = False):
    """
    Reset PEGASUS trading data - delete all positions and start fresh.

    Args:
        confirm: Must be True to actually delete data (safety check)

    WARNING: This will permanently delete ALL PEGASUS trading history.
    """
    if not confirm:
        # Get current counts for preview
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM pegasus_positions")
            total = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM pegasus_positions WHERE status = 'open'")
            open_count = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM pegasus_positions WHERE status IN ('closed', 'expired')")
            closed_count = cursor.fetchone()[0]
            conn.close()

            return {
                "success": False,
                "message": "Set confirm=true to reset PEGASUS data. This action cannot be undone.",
                "preview": {
                    "total_positions": total,
                    "open_positions": open_count,
                    "closed_positions": closed_count
                }
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Could not preview data: {e}"
            }

    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Delete all PEGASUS positions
        cursor.execute("DELETE FROM pegasus_positions")
        deleted_positions = cursor.rowcount

        # Also delete PEGASUS daily performance
        deleted_performance = 0
        try:
            cursor.execute("DELETE FROM pegasus_daily_perf")
            deleted_performance = cursor.rowcount
        except Exception:
            pass

        # Also delete PEGASUS scan activity logs if table exists
        deleted_scans = 0
        try:
            cursor.execute("DELETE FROM pegasus_scan_activity")
            deleted_scans = cursor.rowcount
        except Exception:
            pass

        # Try to delete from bot_scan_activity table too
        try:
            cursor.execute("DELETE FROM bot_scan_activity WHERE bot_name = 'PEGASUS'")
            deleted_scans += cursor.rowcount
        except Exception:
            pass

        # Reset PEGASUS config to defaults
        deleted_config = 0
        try:
            cursor.execute("DELETE FROM autonomous_config WHERE key LIKE 'pegasus_%'")
            deleted_config = cursor.rowcount
        except Exception:
            pass

        conn.commit()
        conn.close()

        logger.info(f"PEGASUS reset complete: {deleted_positions} positions, {deleted_performance} performance records, {deleted_scans} scan logs, {deleted_config} config entries deleted")

        return {
            "success": True,
            "message": "PEGASUS data has been reset successfully",
            "deleted": {
                "positions": deleted_positions,
                "daily_performance": deleted_performance,
                "scan_activity": deleted_scans,
                "config_entries": deleted_config
            }
        }
    except Exception as e:
        logger.error(f"Error resetting PEGASUS data: {e}")
        raise HTTPException(status_code=500, detail=str(e))
