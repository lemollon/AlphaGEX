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

# Import mark-to-market utility for real option pricing
MTM_AVAILABLE = False
try:
    from trading.mark_to_market import (
        calculate_ic_mark_to_market,
        build_occ_symbol,
        get_option_quotes_batch,
        clear_quote_cache
    )
    MTM_AVAILABLE = True
    logger.info("Mark-to-market utility loaded for PEGASUS")
except ImportError as e:
    logger.debug(f"Mark-to-market import failed: {e}")

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


def _calculate_pegasus_unrealized_pnl(positions: list) -> dict:
    """
    Calculate unrealized P&L for PEGASUS positions using mark-to-market pricing.

    Fetches real option quotes from Tradier and calculates actual cost to close
    each position. Falls back to estimation if quotes unavailable.

    Args:
        positions: List of position tuples from database query with columns:
                   (position_id, total_credit, contracts, spread_width,
                    put_short_strike, put_long_strike, call_short_strike, call_long_strike,
                    expiration)

    Returns:
        Dict with:
        - total_unrealized_pnl: float
        - positions: list of position details with individual P&L
        - method: 'mark_to_market' or 'estimation'
        - pricing_source: description of data source
    """
    result = {
        'total_unrealized_pnl': 0,
        'positions': [],
        'method': 'estimation',
        'pricing_source': 'estimated',
        'mtm_success_count': 0,
        'mtm_fail_count': 0
    }

    if not positions:
        return result

    total_unrealized = 0

    for pos in positions:
        pos_id, total_credit, contracts, spread_width, put_short, put_long, call_short, call_long, expiration = pos
        total_credit = float(total_credit or 0)
        contracts = int(contracts or 1)
        spread_width = float(spread_width or 10)
        put_short = float(put_short or 0)
        put_long = float(put_long or 0)
        call_short = float(call_short or 0)
        call_long = float(call_long or 0)

        pos_result = {
            'position_id': pos_id,
            'unrealized_pnl': 0,
            'method': 'estimation',
            'current_value': None
        }

        # Try mark-to-market first
        if MTM_AVAILABLE and expiration:
            try:
                exp_str = expiration.strftime('%Y-%m-%d') if hasattr(expiration, 'strftime') else str(expiration)
                mtm = calculate_ic_mark_to_market(
                    underlying='SPX',
                    expiration=exp_str,
                    put_short_strike=put_short,
                    put_long_strike=put_long,
                    call_short_strike=call_short,
                    call_long_strike=call_long,
                    contracts=contracts,
                    entry_credit=total_credit,
                    use_cache=True
                )

                if mtm['success']:
                    pos_result['unrealized_pnl'] = mtm['unrealized_pnl']
                    pos_result['current_value'] = mtm['current_value']
                    pos_result['method'] = 'mark_to_market'
                    pos_result['leg_prices'] = mtm.get('leg_prices')
                    result['mtm_success_count'] += 1
                    total_unrealized += mtm['unrealized_pnl']
                    result['positions'].append(pos_result)
                    continue
                else:
                    result['mtm_fail_count'] += 1
                    logger.debug(f"MTM failed for {pos_id}: {mtm.get('error')}")
            except Exception as e:
                result['mtm_fail_count'] += 1
                logger.debug(f"MTM exception for {pos_id}: {e}")

        # Fallback to estimation based on underlying price
        try:
            from data.unified_data_provider import get_price
            spx_price = get_price("SPX")
            if not spx_price or spx_price <= 0:
                spy_price = get_price("SPY")
                if spy_price and spy_price > 0:
                    spx_price = spy_price * 10
        except Exception:
            spx_price = None

        if not spx_price or spx_price <= 0:
            # Try Tradier direct - SPX requires PRODUCTION API
            try:
                import os
                from data.tradier_data_fetcher import TradierDataFetcher as TDF
                # Check both TRADIER_PROD_API_KEY (priority) and TRADIER_API_KEY
                prod_key = os.environ.get('TRADIER_PROD_API_KEY') or os.environ.get('TRADIER_API_KEY')
                if prod_key:
                    tradier = TDF(api_key=prod_key, sandbox=False)
                    quote = tradier.get_quote('SPX')
                    if quote and quote.get('last'):
                        spx_price = float(quote['last'])
                # Fallback: Try SPY * 10 from sandbox if production not available
                if (not spx_price or spx_price <= 0):
                    sandbox_key = os.environ.get('TRADIER_SANDBOX_API_KEY')
                    if sandbox_key:
                        tradier = TDF(api_key=sandbox_key, sandbox=True)
                        quote = tradier.get_quote('SPY')
                        if quote and quote.get('last'):
                            spx_price = float(quote['last']) * 10
            except Exception:
                pass

        if spx_price and spx_price > 0:
            # Estimate IC value based on underlying price
            if put_short < spx_price < call_short:
                # Safe zone
                put_dist = (spx_price - put_short) / spread_width
                call_dist = (call_short - spx_price) / spread_width
                factor = min(put_dist, call_dist) / 2
                current_value = total_credit * max(0.1, 0.5 - factor * 0.3)
            elif spx_price <= put_short:
                intrinsic = put_short - spx_price
                current_value = min(spread_width, intrinsic + total_credit * 0.2)
            else:
                intrinsic = spx_price - call_short
                current_value = min(spread_width, intrinsic + total_credit * 0.2)

            pos_unrealized = (total_credit - current_value) * 100 * contracts
            pos_result['unrealized_pnl'] = round(pos_unrealized, 2)
            pos_result['current_value'] = round(current_value, 4)
            pos_result['underlying_price'] = spx_price
            total_unrealized += pos_unrealized

        result['positions'].append(pos_result)

    result['total_unrealized_pnl'] = round(total_unrealized, 2)

    # Set method based on success rate
    if result['mtm_success_count'] > 0:
        if result['mtm_fail_count'] == 0:
            result['method'] = 'mark_to_market'
            result['pricing_source'] = 'Tradier real-time option quotes'
        else:
            result['method'] = 'mixed'
            result['pricing_source'] = f"MTM: {result['mtm_success_count']}, estimated: {result['mtm_fail_count']}"
    else:
        result['method'] = 'estimation'
        result['pricing_source'] = 'estimated from underlying price'

    return result


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
    except ImportError as e:
        logger.debug(f"Could not import trader_scheduler: {e}")
        return None
    except Exception as e:
        logger.debug(f"Could not get PEGASUS trader: {e}")
        return None


def _get_tradier_account_balance() -> dict:
    """
    Get account balance from Tradier API for PEGASUS.

    PEGASUS always uses PRODUCTION Tradier because:
    - Sandbox doesn't support SPX quotes
    - PEGASUS needs SPX prices for trading
    """
    if not TRADIER_AVAILABLE or not TradierDataFetcher:
        return {'connected': False, 'total_equity': 0, 'sandbox': False, 'error': 'TradierDataFetcher not imported'}

    try:
        from unified_config import APIConfig

        # PEGASUS always uses PRODUCTION Tradier for SPX quotes (sandbox doesn't have SPX)
        api_key = (
            getattr(APIConfig, 'TRADIER_PROD_API_KEY', None) or
            getattr(APIConfig, 'TRADIER_API_KEY', None)
        )
        account_id = (
            getattr(APIConfig, 'TRADIER_PROD_ACCOUNT_ID', None) or
            getattr(APIConfig, 'TRADIER_ACCOUNT_ID', None)
        )

        logger.info(f"PEGASUS Tradier: mode=PRODUCTION (SPX requires prod), api_key={'SET' if api_key else 'NOT SET'}, account_id={account_id}")

        if not api_key or not account_id:
            return {'connected': False, 'total_equity': 0, 'sandbox': False, 'error': 'No credentials configured'}

        # PEGASUS uses production (sandbox=False) for SPX quotes
        tradier = TradierDataFetcher(api_key=api_key, account_id=account_id, sandbox=False)
        balance = tradier.get_account_balance()

        if balance:
            return {
                'connected': True,
                'total_equity': balance.get('total_equity', 0),
                'option_buying_power': balance.get('option_buying_power', 0),
                'sandbox': False,
                'account_id': account_id
            }

        return {'connected': False, 'total_equity': 0, 'sandbox': False, 'error': 'Empty response from Tradier'}

    except Exception as e:
        logger.error(f"PEGASUS Tradier balance fetch ERROR: {e}")
        return {'connected': False, 'total_equity': 0, 'sandbox': False, 'error': str(e)}


def _get_heartbeat(bot_name: str) -> dict:
    """Get heartbeat info for a bot from the database"""
    CENTRAL_TZ = ZoneInfo("America/Chicago")
    conn = None

    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT last_heartbeat, status, scan_count, details
            FROM bot_heartbeats
            WHERE bot_name = %s
        ''', (bot_name,))

        row = cursor.fetchone()

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
    finally:
        if conn:
            conn.close()


def _is_bot_actually_active(heartbeat: dict, scan_interval_minutes: int = 5) -> tuple[bool, str]:
    """
    Determine if a bot is actually active based on heartbeat status and recency.

    Returns:
        (is_active, reason) tuple
    """
    status = heartbeat.get('status', 'UNKNOWN')

    # These statuses indicate the bot is NOT active/healthy
    inactive_statuses = {
        'UNAVAILABLE': 'Trader not initialized',
        'ERROR': 'Encountered an error',
        'KILLED': 'Stopped by kill switch',
        'NEVER_RUN': 'Has never run',
        'UNKNOWN': 'Status unknown'
    }

    if status in inactive_statuses:
        return False, inactive_statuses[status]

    # Check heartbeat recency
    last_scan_iso = heartbeat.get('last_scan_iso')
    if not last_scan_iso:
        return False, 'No heartbeat recorded'

    try:
        last_scan_time = datetime.fromisoformat(last_scan_iso)
        now = datetime.now(last_scan_time.tzinfo)
        age_seconds = (now - last_scan_time).total_seconds()

        # If heartbeat is older than 2x scan interval, consider it stale/crashed
        max_age_seconds = scan_interval_minutes * 60 * 2
        if age_seconds > max_age_seconds:
            return False, f'Heartbeat stale ({int(age_seconds)}s old, max {max_age_seconds}s)'
    except ValueError as e:
        logger.debug(f"Could not parse heartbeat time format: {e}")
    except Exception as e:
        logger.warning(f"Unexpected error parsing heartbeat time: {e}")

    # Active statuses
    if status in ('SCAN_COMPLETE', 'TRADED', 'MARKET_CLOSED', 'BEFORE_WINDOW', 'AFTER_WINDOW'):
        return True, f'Running ({status})'

    return True, f'Running ({status})'


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
        starting_capital = 200000  # Default for PEGASUS (SPX bot)
        total_pnl = 0
        # IMPORTANT: Don't use stale unrealized_pnl from database when worker isn't running
        # Set to None to indicate live pricing is unavailable
        unrealized_pnl = None
        trade_count = 0
        win_count = 0
        open_count = 0
        closed_count = 0
        traded_today = False
        today = datetime.now(ZoneInfo("America/Chicago")).strftime('%Y-%m-%d')

        try:
            conn = get_connection()
            cursor = conn.cursor()

            # Get starting capital from config table (consistent with intraday endpoint)
            try:
                cursor.execute("SELECT value FROM autonomous_config WHERE key = 'pegasus_starting_capital'")
                config_row = cursor.fetchone()
                if config_row and config_row[0]:
                    starting_capital = float(config_row[0])
            except Exception:
                pass

            # Note: We intentionally do NOT use unrealized_pnl from database here
            # because it may be stale. Unrealized P&L requires live pricing.
            cursor.execute('''
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 'open' THEN 1 ELSE 0 END) as open_count,
                    SUM(CASE WHEN status IN ('closed', 'expired', 'partial_close') THEN 1 ELSE 0 END) as closed_count,
                    SUM(CASE WHEN status IN ('closed', 'expired', 'partial_close') AND realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
                    COALESCE(SUM(CASE WHEN status IN ('closed', 'expired', 'partial_close') THEN realized_pnl ELSE 0 END), 0) as total_pnl,
                    SUM(CASE WHEN DATE(open_time::timestamptz AT TIME ZONE 'America/Chicago') = %s THEN 1 ELSE 0 END) as traded_today
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

        # PEGASUS paper trades with $200k - Tradier is only for SPX prices, not required
        tradier_balance = _get_tradier_account_balance()
        tradier_connected = tradier_balance.get('connected', False)

        # PEGASUS always uses paper capital - Tradier is optional for price data
        capital = starting_capital + total_pnl  # Paper capital + P&L
        capital_message = "Paper trading with $200k capital"
        if tradier_connected:
            capital_message += " (Tradier connected for live prices)"

        # Calculate trading window status
        now = datetime.now(ZoneInfo("America/Chicago"))
        current_time_str = now.strftime('%Y-%m-%d %H:%M:%S CT')

        # PEGASUS trading window: 8:30 AM - 2:45 PM CT (market closes at 3:00 PM CT)
        entry_start = "08:30"
        entry_end = "14:45"

        # Check for early close days (Christmas Eve - Dec 31 is normal)
        if now.month == 12 and now.day == 24:
            entry_end = "11:50"  # Christmas Eve early close (10 min before 12:00 PM)

        start_parts = entry_start.split(':')
        end_parts = entry_end.split(':')
        start_time = now.replace(hour=int(start_parts[0]), minute=int(start_parts[1]), second=0, microsecond=0)
        end_time = now.replace(hour=int(end_parts[0]), minute=int(end_parts[1]), second=0, microsecond=0)

        is_weekday = now.weekday() < 5
        in_window = is_weekday and start_time <= now <= end_time
        trading_window_status = "OPEN" if in_window else "CLOSED"

        # Determine if PEGASUS is actually active based on heartbeat
        scan_interval = 5
        is_active, active_reason = _is_bot_actually_active(heartbeat, scan_interval)

        # current_equity = starting_capital + realized
        # Only add unrealized if we have live pricing (worker running)
        # When unrealized is None, show realized-only equity
        current_equity = starting_capital + total_pnl
        if unrealized_pnl is not None:
            current_equity += unrealized_pnl

        return {
            "success": True,
            "data": {
                "mode": "paper",
                "ticker": "SPX",
                "capital": capital,
                "starting_capital": starting_capital,
                "current_equity": round(current_equity, 2),
                "capital_source": "paper",
                "total_pnl": round(total_pnl, 2),
                # Return None to frontend when live pricing unavailable
                "unrealized_pnl": round(unrealized_pnl, 2) if unrealized_pnl is not None else None,
                "trade_count": trade_count,
                "win_rate": win_rate,
                "open_positions": open_count,
                "closed_positions": closed_count,
                "traded_today": traded_today,
                "in_trading_window": in_window,
                "trading_window_status": trading_window_status,
                "trading_window_end": entry_end,
                "high_water_mark": starting_capital,
                "current_time": current_time_str,
                "is_active": is_active,
                "active_reason": active_reason,
                "scan_interval_minutes": scan_interval,
                "heartbeat": heartbeat,
                "tradier_connected": tradier_connected,
                "tradier_for_prices": tradier_connected,
                "config": {
                    "risk_per_trade": 10.0,
                    "spread_width": 10.0,
                    "sd_multiplier": 1.0,
                    "ticker": "SPX"
                },
                "source": "paper",
                "message": capital_message
            }
        }

    # Calculate trading window for when instance returns status
    now = datetime.now(ZoneInfo("America/Chicago"))
    current_time_str = now.strftime('%Y-%m-%d %H:%M:%S CT')
    entry_start = "08:30"
    entry_end = "14:45"  # Market closes at 3:00 PM CT, stop entries 15 min before
    if now.month == 12 and now.day == 24:
        entry_end = "11:50"  # Christmas Eve early close (10 min before 12:00 PM)
    start_parts = entry_start.split(':')
    end_parts = entry_end.split(':')
    start_time = now.replace(hour=int(start_parts[0]), minute=int(start_parts[1]), second=0, microsecond=0)
    end_time = now.replace(hour=int(end_parts[0]), minute=int(end_parts[1]), second=0, microsecond=0)
    is_weekday = now.weekday() < 5
    in_window = is_weekday and start_time <= now <= end_time
    trading_window_status = "OPEN" if in_window else "CLOSED"

    try:
        status = pegasus.get_status()
        scan_interval = 5
        is_active, active_reason = _is_bot_actually_active(heartbeat, scan_interval)
        status['is_active'] = is_active
        status['active_reason'] = active_reason
        status['scan_interval_minutes'] = scan_interval
        status['heartbeat'] = heartbeat
        # Ensure all required fields are present
        status['in_trading_window'] = in_window
        status['trading_window_status'] = trading_window_status
        status['trading_window_end'] = entry_end
        status['current_time'] = current_time_str

        # CRITICAL FIX: Query database for total realized P&L from closed positions
        # The trader's get_status() doesn't include total_pnl, causing portfolio sync issues
        db_total_pnl = 0
        db_trade_count = 0
        db_win_count = 0
        db_open_count = 0
        db_closed_count = 0
        db_starting_capital = 200000  # Default for PEGASUS (SPX bot)
        today = now.strftime('%Y-%m-%d')
        try:
            conn = get_connection()
            cursor = conn.cursor()

            # Get starting capital from config table (consistent with intraday endpoint)
            try:
                cursor.execute("SELECT value FROM autonomous_config WHERE key = 'pegasus_starting_capital'")
                config_row = cursor.fetchone()
                if config_row and config_row[0]:
                    db_starting_capital = float(config_row[0])
            except Exception:
                pass

            cursor.execute('''
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 'open' THEN 1 ELSE 0 END) as open_count,
                    SUM(CASE WHEN status IN ('closed', 'expired', 'partial_close') THEN 1 ELSE 0 END) as closed_count,
                    SUM(CASE WHEN status IN ('closed', 'expired', 'partial_close') AND realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
                    COALESCE(SUM(CASE WHEN status IN ('closed', 'expired', 'partial_close') THEN realized_pnl ELSE 0 END), 0) as total_pnl
                FROM pegasus_positions
            ''')
            row = cursor.fetchone()
            conn.close()
            if row:
                db_trade_count = row[0] or 0
                db_open_count = row[1] or 0
                db_closed_count = row[2] or 0
                db_win_count = row[3] or 0
                db_total_pnl = float(row[4] or 0)
        except Exception as db_err:
            logger.debug(f"Could not read PEGASUS stats from database: {db_err}")

        # Use database values for accurate P&L tracking
        status['total_pnl'] = db_total_pnl
        status['trade_count'] = db_trade_count
        status['win_rate'] = round((db_win_count / db_closed_count) * 100, 1) if db_closed_count > 0 else 0
        status['open_positions'] = db_open_count
        status['closed_positions'] = db_closed_count

        # Ensure capital fields exist
        if 'capital' not in status:
            status['capital'] = db_starting_capital
        if 'capital_source' not in status:
            status['capital_source'] = 'paper'

        # Calculate current_equity = starting_capital + realized + unrealized (matches equity curve)
        starting_capital = db_starting_capital
        total_pnl = status.get('total_pnl', 0)
        unrealized_pnl = status.get('unrealized_pnl')  # Can be None if no live pricing
        status['starting_capital'] = starting_capital
        # Only include unrealized in equity if we have live pricing
        if unrealized_pnl is not None:
            status['current_equity'] = round(starting_capital + total_pnl + unrealized_pnl, 2)
        else:
            status['current_equity'] = round(starting_capital + total_pnl, 2)

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
                WHERE status IN ('closed', 'expired', 'partial_close')
                ORDER BY COALESCE(close_time, open_time) DESC
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
                    except (ValueError, TypeError):
                        pass  # Keep default dte=0 if date parsing fails

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
                except (ValueError, TypeError, AttributeError):
                    pass  # Keep default dte=0 if date parsing fails

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

        # ALWAYS query database for closed positions (in-memory instance only tracks open)
        closed_positions = []
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                SELECT
                    position_id, expiration,
                    put_long_strike, put_short_strike, call_short_strike, call_long_strike,
                    put_credit, call_credit, total_credit,
                    contracts, spread_width, max_loss, close_price, realized_pnl,
                    underlying_at_entry, vix_at_entry, status, close_reason,
                    gex_regime, call_wall, put_wall, flip_point, net_gex,
                    oracle_confidence, oracle_win_probability, oracle_advice,
                    oracle_reasoning, oracle_top_factors,
                    open_time, close_time
                FROM pegasus_positions
                WHERE status IN ('closed', 'expired', 'partial_close')
                ORDER BY COALESCE(close_time, open_time) DESC
                LIMIT 100
            ''')
            closed_rows = cursor.fetchall()
            conn.close()

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
                    "gex_regime": gex_regime or "NEUTRAL",
                    "call_wall": float(call_wall) if call_wall else 0,
                    "put_wall": float(put_wall) if put_wall else 0,
                    "flip_point": float(flip_point) if flip_point else 0,
                    "net_gex": float(net_gex) if net_gex else 0,
                    "oracle_confidence": float(oracle_confidence) if oracle_confidence else 0,
                    "oracle_win_probability": float(oracle_win_prob) if oracle_win_prob else 0,
                    "oracle_advice": oracle_advice or "",
                    "oracle_reasoning": oracle_reasoning or "",
                    "oracle_top_factors": oracle_top_factors or "",
                    "open_time": open_time_ct.strftime('%Y-%m-%d %H:%M:%S CT') if open_time_ct else None,
                    "open_time_iso": open_time_ct.isoformat() if open_time_ct else None,
                    "close_time": close_time_ct.strftime('%Y-%m-%d %H:%M:%S CT') if close_time_ct else None,
                    "close_time_iso": close_time_ct.isoformat() if close_time_ct else None,
                })
        except Exception as db_err:
            logger.warning(f"Could not read closed positions from database: {db_err}")

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
        logger.error(f"Error getting PEGASUS positions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/equity-curve")
async def get_pegasus_equity_curve(days: int = 30):
    """
    Get PEGASUS equity curve data including unrealized P&L from open positions.

    Args:
        days: Number of days of history (default 30)
    """
    starting_capital = 200000  # Default for PEGASUS (SPX bot)
    now_ct = datetime.now(ZoneInfo("America/Chicago"))
    today = now_ct.strftime('%Y-%m-%d')

    # Calculate cutoff date for filtering based on days parameter
    cutoff_date = (now_ct - timedelta(days=days)).strftime('%Y-%m-%d')

    unrealized_pnl = 0.0
    open_positions_count = 0

    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Check config table for starting capital (consistent with intraday endpoint)
        try:
            cursor.execute("SELECT value FROM autonomous_config WHERE key = 'pegasus_starting_capital'")
            config_row = cursor.fetchone()
            if config_row and config_row[0]:
                starting_capital = float(config_row[0])
        except Exception:
            pass

        # Get closed positions for historical equity curve - use full timestamp for granular chart
        # Use COALESCE to fall back to open_time if close_time is NULL (legacy data)
        cursor.execute('''
            SELECT COALESCE(close_time, open_time)::timestamptz AT TIME ZONE 'America/Chicago' as close_timestamp,
                   realized_pnl, position_id
            FROM pegasus_positions
            WHERE status IN ('closed', 'expired', 'partial_close')
            ORDER BY COALESCE(close_time, open_time) ASC
        ''')
        rows = cursor.fetchall()

        # Get open positions for unrealized P&L calculation
        cursor.execute('''
            SELECT position_id, total_credit, contracts, spread_width,
                   put_short_strike, put_long_strike, call_short_strike, call_long_strike,
                   expiration
            FROM pegasus_positions
            WHERE status = 'open'
        ''')
        open_positions = cursor.fetchall()
        open_positions_count = len(open_positions)
        conn.close()

        # Calculate unrealized P&L from open positions using MTM
        if open_positions:
            mtm_result = _calculate_pegasus_unrealized_pnl(open_positions)
            unrealized_pnl = mtm_result['total_unrealized_pnl']
            logger.debug(f"PEGASUS equity-curve: unrealized=${unrealized_pnl:.2f} via {mtm_result['method']}")

        # Build equity curve - one point per trade for granular visualization
        equity_curve = []
        cumulative_pnl = 0

        if rows:
            # Add starting point before first trade
            first_timestamp = rows[0][0]
            if first_timestamp:
                first_date = first_timestamp.strftime('%Y-%m-%d') if hasattr(first_timestamp, 'strftime') else str(first_timestamp)[:10]
                equity_curve.append({
                    "date": first_date,
                    "timestamp": first_date + "T00:00:00",
                    "equity": starting_capital,
                    "pnl": 0,
                    "daily_pnl": 0,
                    "return_pct": 0,
                    "position_id": None
                })

            # Create one data point per trade
            for row in rows:
                close_timestamp, pnl, pos_id = row
                trade_pnl = float(pnl or 0)
                cumulative_pnl += trade_pnl
                current_equity = starting_capital + cumulative_pnl

                # Format timestamp for frontend
                if close_timestamp:
                    if hasattr(close_timestamp, 'isoformat'):
                        timestamp_str = close_timestamp.isoformat()
                        date_str = close_timestamp.strftime('%Y-%m-%d')
                    else:
                        timestamp_str = str(close_timestamp)
                        date_str = str(close_timestamp)[:10]
                else:
                    timestamp_str = today + "T00:00:00"
                    date_str = today

                equity_curve.append({
                    "date": date_str,
                    "timestamp": timestamp_str,
                    "equity": round(current_equity, 2),
                    "pnl": round(cumulative_pnl, 2),
                    "daily_pnl": round(trade_pnl, 2),
                    "return_pct": round((cumulative_pnl / starting_capital) * 100, 2),
                    "position_id": pos_id
                })

        # Add today's entry with unrealized P&L from open positions
        total_pnl_with_unrealized = cumulative_pnl + unrealized_pnl
        current_equity_with_unrealized = starting_capital + total_pnl_with_unrealized
        now = datetime.now(ZoneInfo("America/Chicago"))

        # Always add today's data point if we have open positions or closed positions
        if open_positions_count > 0 or rows:
            equity_curve.append({
                "date": today,
                "timestamp": now.isoformat(),
                "equity": round(current_equity_with_unrealized, 2),
                "pnl": round(total_pnl_with_unrealized, 2),
                "realized_pnl": round(cumulative_pnl, 2),
                "unrealized_pnl": round(unrealized_pnl, 2),
                "daily_pnl": round(unrealized_pnl, 2),  # Today's change is unrealized
                "return_pct": round((total_pnl_with_unrealized / starting_capital) * 100, 2),
                "open_positions": open_positions_count
            })

            # Filter equity curve to only show data within the requested days range
            filtered_curve = [point for point in equity_curve if point["date"] >= cutoff_date]

            # If we filtered out all points, add a starting point at cutoff
            if not filtered_curve and equity_curve:
                pre_cutoff_points = [p for p in equity_curve if p["date"] < cutoff_date]
                if pre_cutoff_points:
                    last_pre_cutoff = pre_cutoff_points[-1]
                    filtered_curve.append({
                        "date": cutoff_date,
                        "timestamp": cutoff_date + "T00:00:00",
                        "equity": last_pre_cutoff["equity"],
                        "pnl": last_pre_cutoff["pnl"],
                        "daily_pnl": 0,
                        "return_pct": last_pre_cutoff["return_pct"],
                        "position_id": None
                    })
                else:
                    filtered_curve.append({
                        "date": cutoff_date,
                        "timestamp": cutoff_date + "T00:00:00",
                        "equity": starting_capital,
                        "pnl": 0,
                        "daily_pnl": 0,
                        "return_pct": 0,
                        "position_id": None
                    })

            return {
                "success": True,
                "data": {
                    "equity_curve": filtered_curve,
                    "starting_capital": starting_capital,
                    "current_equity": round(current_equity_with_unrealized, 2),
                    "total_pnl": round(total_pnl_with_unrealized, 2),
                    "realized_pnl": round(cumulative_pnl, 2),
                    "unrealized_pnl": round(unrealized_pnl, 2),
                    "total_return_pct": round((total_pnl_with_unrealized / starting_capital) * 100, 2),
                    "closed_positions_count": len(rows),
                    "open_positions_count": open_positions_count,
                    "source": "database",
                    "days_filter": days
                }
            }

    except Exception as db_err:
        logger.warning(f"Could not read equity curve from database: {db_err}")

    now = datetime.now(ZoneInfo("America/Chicago"))
    return {
        "success": True,
        "data": {
            "equity_curve": [{
                "date": today,
                "timestamp": now.isoformat(),
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


@router.get("/equity-curve/intraday")
async def get_pegasus_intraday_equity(date: str = None):
    """
    Get PEGASUS intraday equity curve with 5-minute interval snapshots.

    Returns equity data points throughout the trading day showing:
    - Realized P&L from closed positions
    - Unrealized P&L from open positions (mark-to-market)

    Args:
        date: Date to get intraday data for (default: today)
    """
    CENTRAL_TZ = ZoneInfo("America/Chicago")
    now = datetime.now(CENTRAL_TZ)
    today = date or now.strftime('%Y-%m-%d')
    current_time = now.strftime('%H:%M:%S')

    starting_capital = 200000

    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Get starting capital from config
        cursor.execute("""
            SELECT value FROM autonomous_config WHERE key = 'pegasus_starting_capital'
        """)
        row = cursor.fetchone()
        if row and row[0]:
            try:
                starting_capital = float(row[0])
            except (ValueError, TypeError):
                pass

        # Get intraday snapshots for the requested date
        cursor.execute("""
            SELECT timestamp, balance, unrealized_pnl, realized_pnl, open_positions, note
            FROM pegasus_equity_snapshots
            WHERE DATE(timestamp::timestamptz AT TIME ZONE 'America/Chicago') = %s
            ORDER BY timestamp ASC
        """, (today,))
        snapshots = cursor.fetchall()

        # Get total realized P&L from closed positions up to today
        # Use COALESCE to handle legacy data with NULL close_time
        cursor.execute("""
            SELECT COALESCE(SUM(realized_pnl), 0)
            FROM pegasus_positions
            WHERE status IN ('closed', 'expired', 'partial_close')
            AND DATE(COALESCE(close_time, open_time)::timestamptz AT TIME ZONE 'America/Chicago') <= %s
        """, (today,))
        total_realized_row = cursor.fetchone()
        total_realized = float(total_realized_row[0]) if total_realized_row and total_realized_row[0] else 0

        # Get today's closed positions P&L
        cursor.execute("""
            SELECT COALESCE(SUM(realized_pnl), 0), COUNT(*)
            FROM pegasus_positions
            WHERE status IN ('closed', 'expired', 'partial_close')
            AND DATE(COALESCE(close_time, open_time)::timestamptz AT TIME ZONE 'America/Chicago') = %s
        """, (today,))
        today_row = cursor.fetchone()
        today_realized = float(today_row[0]) if today_row and today_row[0] else 0
        today_closed_count = int(today_row[1]) if today_row and today_row[1] else 0

        # Get today's closed trades with timestamps for accurate intraday cumulative calculation
        # This fixes the "cliff" bug where old snapshots had NULL/incorrect realized_pnl
        # IMPORTANT: Include 'partial_close' to capture all realized P&L
        cursor.execute("""
            SELECT COALESCE(close_time, open_time)::timestamptz, realized_pnl
            FROM pegasus_positions
            WHERE status IN ('closed', 'expired', 'partial_close')
            AND DATE(COALESCE(close_time, open_time)::timestamptz AT TIME ZONE 'America/Chicago') = %s
            ORDER BY COALESCE(close_time, open_time) ASC
        """, (today,))
        today_closes = cursor.fetchall()

        # Calculate unrealized P&L from open positions using mark-to-market pricing
        unrealized_pnl = 0
        open_positions = []
        pricing_method = 'estimation'

        try:
            # Query positions with all fields needed for MTM calculation
            cursor.execute("""
                SELECT position_id, total_credit, contracts, spread_width,
                       put_short_strike, put_long_strike, call_short_strike, call_long_strike,
                       expiration
                FROM pegasus_positions
                WHERE status = 'open'
            """)
            open_rows = cursor.fetchall()

            if open_rows:
                # Use the MTM helper function for real option pricing
                mtm_result = _calculate_pegasus_unrealized_pnl(open_rows)
                unrealized_pnl = mtm_result['total_unrealized_pnl']
                open_positions = mtm_result['positions']
                pricing_method = mtm_result['method']
                logger.debug(f"PEGASUS intraday: unrealized=${unrealized_pnl:.2f} via {pricing_method}")
        except Exception as e:
            logger.warning(f"Error calculating unrealized P&L: {e}")

        conn.close()

        # Build intraday data points (frontend expects data_points with cumulative_pnl)
        data_points = []

        # Add market open point
        prev_day_realized = total_realized - today_realized
        market_open_equity = round(starting_capital + prev_day_realized, 2)
        data_points.append({
            "timestamp": f"{today}T08:30:00",
            "time": "08:30:00",
            "equity": market_open_equity,
            "cumulative_pnl": round(prev_day_realized, 2),
            "open_positions": 0,
            "unrealized_pnl": 0
        })

        # Track high/low for summary
        all_equities = [market_open_equity]

        # Add snapshots - calculate cumulative realized at each snapshot's timestamp
        # This fixes the "cliff" bug where old snapshots had NULL/incorrect realized_pnl
        for snapshot in snapshots:
            ts, balance, snap_unrealized, snap_realized, open_count, note = snapshot
            snap_time = ts.astimezone(CENTRAL_TZ) if ts.tzinfo else ts

            # Calculate cumulative realized at this snapshot's timestamp from actual trades
            # prev_day_realized + sum of today's closes that happened before this snapshot
            snap_realized_val = prev_day_realized
            for close_time, close_pnl in today_closes:
                close_time_ct = close_time.astimezone(CENTRAL_TZ) if close_time and close_time.tzinfo else close_time
                if close_time_ct and close_time_ct <= snap_time:
                    snap_realized_val += float(close_pnl or 0)

            snap_unrealized_val = float(snap_unrealized or 0)
            # Recalculate equity: starting_capital + realized + unrealized
            snap_equity = round(starting_capital + snap_realized_val + snap_unrealized_val, 2)
            all_equities.append(snap_equity)

            data_points.append({
                "timestamp": snap_time.isoformat(),
                "time": snap_time.strftime('%H:%M:%S'),
                "equity": snap_equity,
                "cumulative_pnl": round(snap_realized_val + snap_unrealized_val, 2),
                "open_positions": open_count or 0,
                "unrealized_pnl": round(snap_unrealized_val, 2)
            })

        # Add current live point if viewing today
        # IMPORTANT: Without live pricing from PEGASUS worker, unrealized_pnl = 0
        # So current_equity will be realized-only, which is consistent with /status endpoint
        current_equity = starting_capital + total_realized + unrealized_pnl
        if today == now.strftime('%Y-%m-%d'):
            total_pnl = total_realized + unrealized_pnl
            current_equity = starting_capital + total_pnl
            all_equities.append(round(current_equity, 2))

            data_points.append({
                "timestamp": now.isoformat(),
                "time": current_time,
                "equity": round(current_equity, 2),
                "cumulative_pnl": round(total_pnl, 2),
                "open_positions": len(open_positions),
                "unrealized_pnl": round(unrealized_pnl, 2),
                "note": "Realized P&L only" if unrealized_pnl == 0 and len(open_positions) > 0 else None
            })

        # Calculate high/low of day
        high_of_day = max(all_equities) if all_equities else starting_capital
        low_of_day = min(all_equities) if all_equities else starting_capital
        day_pnl = today_realized + unrealized_pnl

        return {
            "success": True,
            "date": today,
            "bot": "PEGASUS",
            "data_points": data_points,
            "current_equity": round(current_equity, 2),
            "day_pnl": round(day_pnl, 2),
            "day_realized": round(today_realized, 2),
            "day_unrealized": round(unrealized_pnl, 2),
            "starting_equity": market_open_equity,  # Equity at market open (starting_capital + prev realized)
            "high_of_day": round(high_of_day, 2),
            "low_of_day": round(low_of_day, 2),
            "snapshots_count": len(snapshots)
        }

    except Exception as e:
        logger.error(f"Error getting PEGASUS intraday equity: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e),
            "date": today,
            "bot": "PEGASUS",
            "data_points": [{
                "timestamp": now.isoformat(),
                "time": current_time,
                "equity": starting_capital,
                "cumulative_pnl": 0,
                "open_positions": 0,
                "unrealized_pnl": 0
            }],
            "current_equity": starting_capital,
            "day_pnl": 0,
            "day_realized": 0,
            "day_unrealized": 0,
            "starting_equity": starting_capital,
            "high_of_day": starting_capital,
            "low_of_day": starting_capital,
            "snapshots_count": 0
        }


@router.post("/equity-snapshot")
async def save_pegasus_equity_snapshot():
    """
    Save current equity snapshot for intraday tracking.

    Call this periodically (every 5 minutes) during market hours
    to build detailed intraday equity curve.
    """
    CENTRAL_TZ = ZoneInfo("America/Chicago")
    now = datetime.now(CENTRAL_TZ)

    starting_capital = 200000
    unrealized_pnl = 0
    realized_pnl = 0
    open_count = 0

    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Get starting capital
        cursor.execute("""
            SELECT value FROM autonomous_config WHERE key = 'pegasus_starting_capital'
        """)
        row = cursor.fetchone()
        if row and row[0]:
            try:
                starting_capital = float(row[0])
            except (ValueError, TypeError):
                pass

        # Get total realized P&L
        cursor.execute("""
            SELECT COALESCE(SUM(realized_pnl), 0)
            FROM pegasus_positions
            WHERE status IN ('closed', 'expired', 'partial_close')
        """)
        row = cursor.fetchone()
        realized_pnl = float(row[0]) if row and row[0] else 0

        # Get open positions and calculate unrealized P&L using mark-to-market
        cursor.execute("""
            SELECT position_id, total_credit, contracts, spread_width,
                   put_short_strike, put_long_strike, call_short_strike, call_long_strike,
                   expiration
            FROM pegasus_positions WHERE status = 'open'
        """)
        open_positions = cursor.fetchall()
        open_count = len(open_positions)

        # Calculate unrealized P&L using MTM helper
        unrealized_pnl = 0
        pricing_method = 'estimation'

        if open_positions:
            mtm_result = _calculate_pegasus_unrealized_pnl(open_positions)
            unrealized_pnl = mtm_result['total_unrealized_pnl']
            pricing_method = mtm_result['method']
            logger.debug(f"PEGASUS snapshot: unrealized=${unrealized_pnl:.2f} via {pricing_method}")

        current_equity = starting_capital + realized_pnl + unrealized_pnl

        # Create table if not exists
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS pegasus_equity_snapshots (
                id SERIAL PRIMARY KEY,
                timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
                balance DECIMAL(12, 2) NOT NULL,
                unrealized_pnl DECIMAL(12, 2),
                realized_pnl DECIMAL(12, 2),
                open_positions INTEGER,
                note TEXT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        ''')

        # Insert snapshot
        cursor.execute('''
            INSERT INTO pegasus_equity_snapshots
            (timestamp, balance, unrealized_pnl, realized_pnl, open_positions, note)
            VALUES (%s, %s, %s, %s, %s, %s)
        ''', (
            now,
            current_equity,
            unrealized_pnl,
            realized_pnl,
            open_count,
            f"Auto snapshot at {now.strftime('%H:%M:%S')}"
        ))

        conn.commit()
        conn.close()

        return {
            "success": True,
            "data": {
                "timestamp": now.isoformat(),
                "equity": round(current_equity, 2),
                "unrealized_pnl": round(unrealized_pnl, 2),
                "realized_pnl": round(realized_pnl, 2),
                "open_positions": open_count
            }
        }

    except Exception as e:
        logger.error(f"Error saving PEGASUS equity snapshot: {e}")
        return {
            "success": False,
            "error": str(e)
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
        "min_credit": 0.75,
        "profit_target_pct": 50,
        "use_stop_loss": False,
        "entry_window": "08:30 - 14:45 CT",
        "force_exit": "14:50 CT (10 min before market close)",
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

            # Query positions with all fields needed for MTM
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

            # Use COALESCE to handle legacy data with NULL close_time
            cursor.execute('''
                SELECT COALESCE(SUM(realized_pnl), 0)
                FROM pegasus_positions
                WHERE status IN ('closed', 'expired', 'partial_close')
                AND DATE(COALESCE(close_time, open_time)::timestamptz AT TIME ZONE 'America/Chicago') = %s
            ''', (today,))
            realized_row = cursor.fetchone()
            today_realized = float(realized_row[0]) if realized_row else 0

            # Get cumulative realized P&L from ALL closed positions (matches equity curve)
            # Note: Don't filter on close_time - historical data may have NULL close_time
            cursor.execute('''
                SELECT COALESCE(SUM(realized_pnl), 0)
                FROM pegasus_positions
                WHERE status IN ('closed', 'expired', 'partial_close')
            ''')
            cumulative_row = cursor.fetchone()
            cumulative_realized = float(cumulative_row[0]) if cumulative_row else 0
            conn.close()

            # Calculate unrealized P&L using MTM
            positions = []
            total_unrealized = 0.0
            mtm_method = 'estimation'

            for row in open_rows:
                (pos_id, exp, put_long, put_short, call_short, call_long,
                 credit, contracts, max_loss, spread_width, entry_price, vix_entry) = row

                credit_val = float(credit or 0)
                contracts_val = int(contracts or 0)
                credit_received = credit_val * 100 * contracts_val
                pos_unrealized = None
                method = 'estimation'

                # Try MTM for this position
                if MTM_AVAILABLE and exp and put_short and put_long and call_short and call_long:
                    try:
                        mtm_result = calculate_ic_mark_to_market(
                            underlying='SPX',
                            expiration=str(exp),
                            put_short_strike=float(put_short),
                            put_long_strike=float(put_long),
                            call_short_strike=float(call_short),
                            call_long_strike=float(call_long),
                            contracts=contracts_val,
                            entry_credit=credit_val,
                            use_cache=True
                        )
                        if mtm_result.get('success') and mtm_result.get('unrealized_pnl') is not None:
                            pos_unrealized = mtm_result['unrealized_pnl']
                            total_unrealized += pos_unrealized
                            method = 'mark_to_market'
                            mtm_method = 'mark_to_market'
                    except Exception as e:
                        logger.debug(f"PEGASUS live-pnl MTM failed for {pos_id}: {e}")

                positions.append({
                    'position_id': pos_id,
                    'expiration': str(exp) if exp else None,
                    'put_long_strike': float(put_long) if put_long else 0,
                    'put_short_strike': float(put_short) if put_short else 0,
                    'call_short_strike': float(call_short) if call_short else 0,
                    'call_long_strike': float(call_long) if call_long else 0,
                    'credit_received': round(credit_received, 2),
                    'contracts': contracts_val,
                    'max_loss': round(float(max_loss or 0) * 100 * contracts_val, 2),
                    'underlying_at_entry': float(entry_price) if entry_price else 0,
                    'vix_at_entry': float(vix_entry) if vix_entry else 0,
                    'unrealized_pnl': round(pos_unrealized, 2) if pos_unrealized is not None else None,
                    'method': method
                })

            # Use MTM total if we got any successful MTM calculations
            final_unrealized = round(total_unrealized, 2) if mtm_method == 'mark_to_market' else None

            return {
                "success": True,
                "data": {
                    "total_unrealized_pnl": final_unrealized,
                    "total_realized_pnl": round(cumulative_realized, 2),
                    "today_realized_pnl": round(today_realized, 2),
                    "net_pnl": round(cumulative_realized + (final_unrealized or 0), 2) if final_unrealized is not None else round(cumulative_realized, 2),
                    "positions": positions,
                    "position_count": len(positions),
                    "source": "database",
                    "method": mtm_method,
                    "message": "Live valuation via mark-to-market" if mtm_method == 'mark_to_market' else "MTM unavailable - estimation fallback"
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

        # Query cumulative realized P&L from closed positions
        cumulative_realized = 0.0
        conn = get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                SELECT COALESCE(SUM(realized_pnl), 0)
                FROM pegasus_positions
                WHERE status IN ('closed', 'expired', 'partial_close')
            ''')
            realized_row = cursor.fetchone()
            cumulative_realized = float(realized_row[0]) if realized_row else 0.0
        except Exception as db_err:
            logger.warning(f"Could not query realized P&L: {db_err}")

        # Calculate unrealized P&L using SAME MTM method as equity curve (fixes discrepancy)
        # Previously used estimation from trader status, now uses MTM for consistency
        unrealized_pnl = None
        has_live_pricing = False
        position_details = []
        mtm_method = 'estimation'

        try:
            # Query open positions for MTM calculation
            cursor.execute('''
                SELECT position_id, total_credit, contracts, spread_width,
                       put_short_strike, put_long_strike, call_short_strike, call_long_strike,
                       expiration
                FROM pegasus_positions
                WHERE status = 'open'
            ''')
            open_rows = cursor.fetchall()

            if open_rows:
                mtm_result = _calculate_pegasus_unrealized_pnl(open_rows)
                if mtm_result.get('total_unrealized_pnl') is not None:
                    unrealized_pnl = mtm_result['total_unrealized_pnl']
                    has_live_pricing = mtm_result.get('method') == 'mark_to_market'
                    mtm_method = mtm_result.get('method', 'estimation')
                    position_details = mtm_result.get('positions', [])
        except Exception as mtm_err:
            logger.warning(f"MTM calculation failed, using trader estimation: {mtm_err}")
            # Fallback to trader estimation
            unrealized_pnl = status.get('unrealized_pnl')
            has_live_pricing = status.get('has_live_pricing', False)

        conn.close()

        # net_pnl = realized + unrealized
        net_pnl = cumulative_realized + (unrealized_pnl or 0) if unrealized_pnl is not None else cumulative_realized

        return {
            "success": True,
            "data": {
                "total_unrealized_pnl": round(unrealized_pnl, 2) if unrealized_pnl is not None else None,
                "total_realized_pnl": round(cumulative_realized, 2),
                "net_pnl": round(net_pnl, 2),
                "has_live_pricing": has_live_pricing,
                "pricing_method": mtm_method,
                "positions": position_details if position_details else [
                    {
                        'position_id': p.position_id,
                        'expiration': p.expiration,
                        'credit_received': p.total_credit * 100 * p.contracts,
                        'contracts': p.contracts,
                        'status': p.status.value,
                        'unrealized_pnl': None
                    }
                    for p in positions
                ],
                "position_count": len(positions),
                "note": f"Using {mtm_method} pricing" if has_live_pricing else "MTM unavailable - using estimation"
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

        # pegasus_logs table has columns: log_time, level (not created_at, log_level)
        # and does NOT have bot_name column (it's PEGASUS-specific)
        where_clause = "WHERE 1=1"
        params = []
        if level:
            where_clause += " AND level = %s"
            params.append(level)
        params.append(limit)

        c.execute(f"""
            SELECT
                id, log_time, level, message, details
            FROM pegasus_logs
            {where_clause}
            ORDER BY log_time DESC
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
                    id, log_time, level, message, details
                FROM bot_logs
                {where_clause}
                ORDER BY log_time DESC
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
        # Use COALESCE to handle legacy data with NULL close_time
        c.execute("""
            SELECT
                DATE(COALESCE(close_time, open_time)::timestamptz AT TIME ZONE 'America/Chicago') as trade_date,
                COUNT(*) as trades_executed,
                SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as trades_won,
                SUM(CASE WHEN realized_pnl <= 0 THEN 1 ELSE 0 END) as trades_lost,
                COALESCE(SUM(realized_pnl), 0) as net_pnl
            FROM pegasus_positions
            WHERE status IN ('closed', 'expired', 'partial_close')
            AND COALESCE(close_time, open_time) >= CURRENT_DATE - INTERVAL '%s days'
            GROUP BY DATE(COALESCE(close_time, open_time)::timestamptz AT TIME ZONE 'America/Chicago')
            ORDER BY trade_date DESC
        """, (days,))

        rows = c.fetchall()

        # Calculate summary stats
        # Use COALESCE to handle legacy data with NULL close_time
        c.execute("""
            SELECT
                COUNT(*) as total_trades,
                SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as total_wins,
                COALESCE(SUM(realized_pnl), 0) as total_pnl
            FROM pegasus_positions
            WHERE status IN ('closed', 'expired', 'partial_close')
            AND COALESCE(close_time, open_time) >= CURRENT_DATE - INTERVAL '%s days'
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
            cursor.execute("SELECT COUNT(*) FROM pegasus_positions WHERE status IN ('closed', 'expired', 'partial_close')")
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


@router.post("/cleanup-open-positions")
async def cleanup_open_positions(confirm: bool = False):
    """
    Clean up open PEGASUS positions without affecting closed trade history.

    Use this to remove test/demo/orphaned positions that are showing in Live P&L
    without wiping the entire trading history.

    Args:
        confirm: Must be True to actually delete positions (safety check)
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Get current open positions for preview
        cursor.execute("""
            SELECT position_id, expiration, total_credit, contracts,
                   put_short_strike, call_short_strike, open_time
            FROM pegasus_positions
            WHERE status = 'open'
            ORDER BY open_time DESC
        """)
        open_positions = cursor.fetchall()

        if not confirm:
            positions_preview = []
            for pos in open_positions:
                positions_preview.append({
                    "position_id": pos[0],
                    "expiration": str(pos[1]) if pos[1] else None,
                    "credit": float(pos[2]) if pos[2] else 0,
                    "contracts": pos[3],
                    "put_short": float(pos[4]) if pos[4] else 0,
                    "call_short": float(pos[5]) if pos[5] else 0,
                    "open_time": pos[6].isoformat() if pos[6] else None
                })

            conn.close()
            return {
                "success": False,
                "message": "Set confirm=true to delete open positions. This will NOT affect closed trade history.",
                "preview": {
                    "open_positions_count": len(open_positions),
                    "positions": positions_preview
                }
            }

        # Delete only open positions
        cursor.execute("DELETE FROM pegasus_positions WHERE status = 'open'")
        deleted_count = cursor.rowcount

        # Also clear any equity snapshots from today (they include the bad unrealized P&L)
        today = datetime.now(ZoneInfo("America/Chicago")).strftime('%Y-%m-%d')
        cursor.execute("""
            DELETE FROM pegasus_equity_snapshots
            WHERE DATE(timestamp::timestamptz AT TIME ZONE 'America/Chicago') = %s
        """, (today,))
        deleted_snapshots = cursor.rowcount

        conn.commit()
        conn.close()

        logger.info(f"PEGASUS cleanup: Deleted {deleted_count} open positions and {deleted_snapshots} today's snapshots")

        return {
            "success": True,
            "message": f"Cleaned up {deleted_count} open positions",
            "data": {
                "deleted_positions": deleted_count,
                "deleted_snapshots": deleted_snapshots,
                "note": "Closed trade history preserved"
            }
        }

    except Exception as e:
        logger.error(f"Error cleaning up PEGASUS positions: {e}")
        raise HTTPException(status_code=500, detail=str(e))
