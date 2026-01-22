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
    logger.info("Mark-to-market utility loaded for ARES")
except ImportError as e:
    logger.debug(f"Mark-to-market import failed: {e}")


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
    except ImportError as e:
        logger.debug(f"Could not import trader_scheduler: {e}")
        return None
    except Exception as e:
        logger.debug(f"Could not get ARES trader: {e}")
        return None


def _calculate_ares_unrealized_pnl(positions: list) -> dict:
    """
    Calculate unrealized P&L for ARES Iron Condor positions using mark-to-market pricing.

    Args:
        positions: List of position tuples from database query with columns:
                   (position_id, total_credit, contracts, spread_width,
                    put_short_strike, put_long_strike, call_short_strike, call_long_strike,
                    expiration)

    Returns:
        Dict with total_unrealized_pnl, method, and position details
    """
    result = {
        'total_unrealized_pnl': 0,
        'positions': [],
        'method': 'estimation',
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
            'method': 'estimation'
        }

        # Try mark-to-market first
        if MTM_AVAILABLE and expiration:
            try:
                exp_str = expiration.strftime('%Y-%m-%d') if hasattr(expiration, 'strftime') else str(expiration)
                mtm = calculate_ic_mark_to_market(
                    underlying='SPY',  # ARES trades SPY
                    expiration=exp_str,
                    put_short_strike=put_short,
                    put_long_strike=put_long,
                    call_short_strike=call_short,
                    call_long_strike=call_long,
                    contracts=contracts,
                    entry_credit=total_credit,
                    use_cache=True
                )

                if mtm.get('success') and mtm.get('unrealized_pnl') is not None:
                    pos_result['unrealized_pnl'] = mtm['unrealized_pnl']
                    pos_result['method'] = 'mark_to_market'
                    result['mtm_success_count'] += 1
                    total_unrealized += mtm['unrealized_pnl']
                    result['positions'].append(pos_result)
                    continue
                else:
                    result['mtm_fail_count'] += 1
            except Exception as e:
                result['mtm_fail_count'] += 1
                logger.debug(f"MTM failed for {pos_id}: {e}")

        # Fallback to estimation based on underlying price
        try:
            from data.unified_data_provider import get_price
            spy_price = get_price("SPY")
        except Exception:
            spy_price = None

        if spy_price and spy_price > 0:
            if put_short < spy_price < call_short:
                # Safe zone - estimate based on distance from strikes
                put_dist = (spy_price - put_short) / spread_width
                call_dist = (call_short - spy_price) / spread_width
                factor = min(put_dist, call_dist) / 2
                current_value = total_credit * max(0.1, 0.5 - factor * 0.3)
            elif spy_price <= put_short:
                intrinsic = put_short - spy_price
                current_value = min(spread_width, intrinsic + total_credit * 0.2)
            else:
                intrinsic = spy_price - call_short
                current_value = min(spread_width, intrinsic + total_credit * 0.2)

            pos_unrealized = (total_credit - current_value) * 100 * contracts
            pos_result['unrealized_pnl'] = round(pos_unrealized, 2)
            total_unrealized += pos_unrealized

        result['positions'].append(pos_result)

    result['total_unrealized_pnl'] = round(total_unrealized, 2)

    if result['mtm_success_count'] > 0:
        if result['mtm_fail_count'] == 0:
            result['method'] = 'mark_to_market'
        else:
            result['method'] = 'mixed'
    else:
        result['method'] = 'estimation'

    return result


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
    finally:
        if conn:
            conn.close()


def _is_ares_actually_active(heartbeat: dict, scan_interval_minutes: int = 5) -> tuple[bool, str]:
    """
    Determine if ARES is actually active based on heartbeat status and recency.

    Returns:
        (is_active, reason) tuple
    """
    # Check heartbeat status first
    status = heartbeat.get('status', 'UNKNOWN')

    # These statuses indicate ARES is NOT active/healthy
    inactive_statuses = {
        'UNAVAILABLE': 'ARES trader not initialized',
        'ERROR': 'ARES encountered an error',
        'KILLED': 'ARES stopped by kill switch',
        'NEVER_RUN': 'ARES has never run',
        'UNKNOWN': 'ARES status unknown'
    }

    if status in inactive_statuses:
        return False, inactive_statuses[status]

    # Check heartbeat recency
    last_scan_iso = heartbeat.get('last_scan_iso')
    if not last_scan_iso:
        return False, 'No heartbeat recorded'

    try:
        from datetime import datetime
        last_scan_time = datetime.fromisoformat(last_scan_iso)
        now = datetime.now(last_scan_time.tzinfo)
        age_seconds = (now - last_scan_time).total_seconds()

        # If heartbeat is older than 2x scan interval, consider it stale/crashed
        max_age_seconds = scan_interval_minutes * 60 * 2
        if age_seconds > max_age_seconds:
            return False, f'Heartbeat stale ({int(age_seconds)}s old, max {max_age_seconds}s)'
    except ValueError as e:
        logger.debug(f"Could not parse heartbeat time format: {e}")
        # If we can't parse, assume it's okay
    except Exception as e:
        logger.warning(f"Unexpected error parsing heartbeat time: {e}")

    # Active statuses
    if status in ('SCAN_COMPLETE', 'TRADED', 'MARKET_CLOSED', 'BEFORE_WINDOW', 'AFTER_WINDOW'):
        return True, f'Running ({status})'

    # Unknown but recent - assume active
    return True, f'Running ({status})'


def _get_tradier_account_balance() -> dict:
    """
    Get account balance from Tradier API.

    ARES uses SANDBOX Tradier account for trading.

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

        # ARES uses SANDBOX Tradier account
        use_sandbox = True  # ARES uses sandbox account

        # Use SANDBOX credentials (TRADIER_SANDBOX_*)
        api_key = APIConfig.TRADIER_SANDBOX_API_KEY
        account_id = APIConfig.TRADIER_SANDBOX_ACCOUNT_ID

        logger.info(f"Tradier balance fetch: mode=SANDBOX (ARES), api_key={'SET' if api_key else 'NOT SET'}, account_id={account_id}")

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


def _calculate_live_unrealized_pnl() -> dict:
    """
    Calculate live unrealized P&L from open positions in AlphaGEX database.

    Uses mark-to-market pricing by fetching real option quotes from Tradier.
    Falls back to estimation based on underlying price if quotes unavailable.

    For Iron Condors:
    - Entry credit = what we received when opening
    - Current value = what it would cost to close now (from real quotes or estimated)
    - Unrealized P&L = Entry credit - Current value (for credit spreads)

    Returns dict with position details and total unrealized P&L.
    """
    result = {
        'success': False,
        'current_price': None,
        'positions': [],
        'total_unrealized_pnl': 0,
        'total_open_credit': 0,
        'error': None,
        'pricing_method': 'estimation',
        'mtm_success_count': 0,
        'mtm_fail_count': 0
    }

    try:
        # Get current underlying price from multiple sources
        current_price = None

        # Try unified data provider first
        try:
            from data.unified_data_provider import get_price
            current_price = get_price('SPY')
            if not current_price or current_price <= 0:
                current_price = None
        except Exception:
            pass

        # Fallback to Tradier direct
        if not current_price or current_price <= 0:
            if TRADIER_AVAILABLE and TradierDataFetcher:
                try:
                    from unified_config import APIConfig
                    api_key = APIConfig.TRADIER_SANDBOX_API_KEY
                    account_id = APIConfig.TRADIER_SANDBOX_ACCOUNT_ID
                    if api_key and account_id:
                        tradier = TradierDataFetcher(api_key=api_key, account_id=account_id, sandbox=True)
                        quote = tradier.get_quote('SPY')
                        if quote:
                            price = quote.get('last') or quote.get('close')
                            if price and float(price) > 0:
                                current_price = float(price)
                except Exception as e:
                    logger.warning(f"Could not get SPY quote from Tradier: {e}")

            # Try Tradier with env vars as final fallback
            if not current_price or current_price <= 0:
                try:
                    import os
                    api_key = os.environ.get('TRADIER_API_KEY') or os.environ.get('TRADIER_SANDBOX_API_KEY')
                    if api_key:
                        tradier = TradierDataFetcher(api_key=api_key, sandbox='SANDBOX' in str(os.environ.get('TRADIER_SANDBOX_API_KEY', '')))
                        quote = tradier.get_quote('SPY')
                        if quote and quote.get('last'):
                            price = float(quote['last'])
                            if price > 0:
                                current_price = price
                except Exception:
                    pass

        if not current_price or current_price <= 0:
            result['error'] = 'Could not fetch current SPY price'
            return result

        result['current_price'] = current_price

        # Get open positions from database
        from database_adapter import get_connection
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT position_id, ticker, expiration,
                   put_short_strike, put_long_strike,
                   call_short_strike, call_long_strike,
                   total_credit, contracts, spread_width,
                   underlying_at_entry, open_time
            FROM ares_positions
            WHERE status = 'open'
            ORDER BY open_time DESC
        ''')
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            result['success'] = True
            result['message'] = 'No open positions'
            return result

        total_unrealized = 0
        total_credit = 0

        for row in rows:
            (pos_id, ticker, expiration, put_short, put_long,
             call_short, call_long, entry_credit, contracts,
             spread_width, entry_price, open_time) = row

            entry_credit = float(entry_credit)
            contracts = int(contracts)
            spread_width = float(spread_width)
            put_short = float(put_short)
            put_long = float(put_long)
            call_short = float(call_short)
            call_long = float(call_long)

            # Try mark-to-market pricing first
            mtm_success = False
            pricing_method = 'estimation'
            leg_prices = None

            if MTM_AVAILABLE and expiration:
                try:
                    exp_str = expiration.strftime('%Y-%m-%d') if hasattr(expiration, 'strftime') else str(expiration)
                    mtm = calculate_ic_mark_to_market(
                        underlying='SPY',
                        expiration=exp_str,
                        put_short_strike=put_short,
                        put_long_strike=put_long,
                        call_short_strike=call_short,
                        call_long_strike=call_long,
                        contracts=contracts,
                        entry_credit=entry_credit,
                        use_cache=True
                    )

                    if mtm['success']:
                        unrealized_pnl = mtm['unrealized_pnl']
                        mtm_success = True
                        pricing_method = 'mark_to_market'
                        leg_prices = mtm.get('leg_prices')
                        result['mtm_success_count'] += 1
                    else:
                        result['mtm_fail_count'] += 1
                        logger.debug(f"MTM failed for {pos_id}: {mtm.get('error')}")
                except Exception as e:
                    result['mtm_fail_count'] += 1
                    logger.debug(f"MTM exception for {pos_id}: {e}")

            # Fallback to estimation if MTM failed
            if not mtm_success:
                # Check if price is in the "safe zone" (between short strikes)
                in_safe_zone = put_short < current_price < call_short

                if in_safe_zone:
                    put_distance = current_price - put_short
                    call_distance = call_short - current_price
                    min_distance = min(put_distance, call_distance)
                    half_width = spread_width / 2
                    safety_ratio = min(min_distance / half_width, 1.0)
                    estimated_close_cost = entry_credit * (1 - safety_ratio * 0.8)
                    unrealized_pnl = (entry_credit - estimated_close_cost) * 100 * contracts
                else:
                    if current_price <= put_short:
                        intrusion = put_short - current_price
                        max_intrusion = spread_width
                        loss_ratio = min(intrusion / max_intrusion, 1.0)
                        max_loss_per_contract = (spread_width - entry_credit) * 100
                        unrealized_pnl = -max_loss_per_contract * loss_ratio * contracts
                    else:
                        intrusion = current_price - call_short
                        max_intrusion = spread_width
                        loss_ratio = min(intrusion / max_intrusion, 1.0)
                        max_loss_per_contract = (spread_width - entry_credit) * 100
                        unrealized_pnl = -max_loss_per_contract * loss_ratio * contracts

            in_safe_zone = put_short < current_price < call_short

            position_data = {
                'position_id': pos_id,
                'ticker': ticker,
                'expiration': str(expiration),
                'strikes': {
                    'put_long': put_long,
                    'put_short': put_short,
                    'call_short': call_short,
                    'call_long': call_long
                },
                'entry_credit': entry_credit,
                'contracts': contracts,
                'entry_price': float(entry_price) if entry_price else None,
                'current_price': current_price,
                'in_safe_zone': in_safe_zone,
                'unrealized_pnl': round(unrealized_pnl, 2),
                'max_profit': round(entry_credit * 100 * contracts, 2),
                'max_loss': round((spread_width - entry_credit) * 100 * contracts, 2),
                'pricing_method': pricing_method,
                'leg_prices': leg_prices
            }

            result['positions'].append(position_data)
            total_unrealized += unrealized_pnl
            total_credit += entry_credit * 100 * contracts

        result['success'] = True
        result['total_unrealized_pnl'] = round(total_unrealized, 2)
        result['total_open_credit'] = round(total_credit, 2)
        result['position_count'] = len(rows)

        # Set overall pricing method
        if result['mtm_success_count'] > 0:
            if result['mtm_fail_count'] == 0:
                result['pricing_method'] = 'mark_to_market'
            else:
                result['pricing_method'] = 'mixed'
        else:
            result['pricing_method'] = 'estimation'

        return result

    except Exception as e:
        logger.error(f"Error calculating unrealized P&L: {e}")
        import traceback
        traceback.print_exc()
        result['error'] = str(e)
        return result


@router.get("/live-pnl")
async def get_live_pnl():
    """
    Get live unrealized P&L calculated from AlphaGEX open positions.

    Calculates current value of open Iron Condors based on:
    - Current SPY price
    - Distance from short strikes
    - Entry credit received

    This is the TRUE live P&L, not dependent on Tradier balance updates.
    """
    result = _calculate_live_unrealized_pnl()

    if not result.get('success'):
        return {
            "success": False,
            "error": result.get('error', 'Failed to calculate live P&L'),
            "data": None
        }

    return {
        "success": True,
        "data": {
            "current_price": result['current_price'],
            "position_count": result.get('position_count', 0),
            "total_unrealized_pnl": result['total_unrealized_pnl'],
            "total_open_credit": result['total_open_credit'],
            "positions": result['positions'],
            "message": result.get('message')
        }
    }


def _get_tradier_positions() -> dict:
    """
    Get positions directly from Tradier SANDBOX account.

    ARES uses SANDBOX Tradier - this shows actual positions in the broker.

    Returns dict with:
    - connected: Whether API call succeeded
    - positions: List of position dicts from Tradier
    - orders: List of recent orders from Tradier
    - error: Error message if connection failed
    """
    if not TRADIER_AVAILABLE or not TradierDataFetcher:
        return {'connected': False, 'positions': [], 'orders': [], 'error': 'TradierDataFetcher not imported'}

    try:
        from unified_config import APIConfig

        # ARES uses SANDBOX Tradier account
        api_key = APIConfig.TRADIER_SANDBOX_API_KEY
        account_id = APIConfig.TRADIER_SANDBOX_ACCOUNT_ID

        if not api_key or not account_id:
            return {'connected': False, 'positions': [], 'orders': [], 'error': 'No SANDBOX credentials configured'}

        tradier = TradierDataFetcher(
            api_key=api_key,
            account_id=account_id,
            sandbox=True  # ARES uses SANDBOX
        )

        # Get positions from Tradier
        positions = tradier.get_positions()
        position_list = []
        for pos in positions:
            position_list.append({
                'symbol': pos.symbol,
                'quantity': pos.quantity,
                'cost_basis': pos.cost_basis,
                'date_acquired': str(pos.date_acquired) if pos.date_acquired else None,
            })

        # Get recent orders from Tradier
        orders = tradier.get_orders(status='all')
        order_list = []
        for order in orders[:20]:  # Last 20 orders
            order_list.append({
                'id': order.id,
                'symbol': order.symbol,
                'side': order.side,
                'quantity': order.quantity,
                'status': order.status,
                'type': order.type,
                'price': order.price,
                'avg_fill_price': order.avg_fill_price,
                'create_date': str(order.create_date) if order.create_date else None,
            })

        logger.info(f"Tradier positions: {len(position_list)} positions, {len(order_list)} orders")

        return {
            'connected': True,
            'positions': position_list,
            'orders': order_list,
            'account_id': account_id,
            'sandbox': True
        }

    except Exception as e:
        logger.error(f"Tradier positions fetch ERROR: {e}")
        import traceback
        traceback.print_exc()
        return {'connected': False, 'positions': [], 'orders': [], 'error': str(e)}


@router.get("/tradier-positions")
async def get_tradier_positions():
    """
    Get positions directly from Tradier SANDBOX account.

    Shows actual positions in the broker - the source of truth.
    ARES database should match these positions.
    """
    result = _get_tradier_positions()

    if not result.get('connected'):
        return {
            "success": False,
            "error": result.get('error', 'Failed to connect to Tradier'),
            "data": {
                "positions": [],
                "orders": [],
                "sandbox": True
            }
        }

    return {
        "success": True,
        "data": {
            "positions": result['positions'],
            "orders": result['orders'],
            "account_id": result.get('account_id'),
            "sandbox": result.get('sandbox', True),
            "message": f"Connected to Tradier SANDBOX - {len(result['positions'])} positions, {len(result['orders'])} orders"
        }
    }


@router.post("/sync-tradier")
async def sync_with_tradier():
    """
    Sync ARES database with Tradier SANDBOX account.

    Compares positions in Tradier with ARES database and reconciles:
    - Positions in Tradier but not in DB → logs warning (manual trade?)
    - Positions in DB but not in Tradier → may have been closed

    Returns sync status and any discrepancies.
    """
    result = {
        "success": False,
        "tradier_connected": False,
        "tradier_positions": 0,
        "db_positions": 0,
        "synced": False,
        "discrepancies": [],
        "balance": None
    }

    # Get Tradier data
    tradier_data = _get_tradier_positions()
    tradier_balance = _get_tradier_account_balance()

    if not tradier_data.get('connected'):
        result['error'] = tradier_data.get('error', 'Failed to connect to Tradier')
        return result

    result['tradier_connected'] = True
    result['tradier_positions'] = len(tradier_data.get('positions', []))

    if tradier_balance.get('connected'):
        result['balance'] = {
            'total_equity': tradier_balance.get('total_equity', 0),
            'option_buying_power': tradier_balance.get('option_buying_power', 0),
            'account_id': tradier_balance.get('account_id')
        }

    # Get ARES database positions
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT position_id, status, ticker, expiration,
                   put_short_strike, put_long_strike, call_short_strike, call_long_strike,
                   contracts, put_order_id, call_order_id
            FROM ares_positions
            WHERE status = 'open'
        ''')
        db_rows = cursor.fetchall()
        conn.close()

        result['db_positions'] = len(db_rows)

        # Compare positions
        tradier_symbols = set()
        for pos in tradier_data.get('positions', []):
            tradier_symbols.add(pos['symbol'])

        db_order_ids = set()
        for row in db_rows:
            if row[9]:  # put_order_id
                db_order_ids.add(str(row[9]))
            if row[10]:  # call_order_id
                db_order_ids.add(str(row[10]))

        # Check for discrepancies
        if result['tradier_positions'] == 0 and result['db_positions'] > 0:
            result['discrepancies'].append({
                'type': 'db_has_positions_tradier_empty',
                'message': f"ARES DB has {result['db_positions']} open positions but Tradier has none",
                'suggestion': 'Positions may have expired or been closed in Tradier'
            })

        if result['tradier_positions'] > 0 and result['db_positions'] == 0:
            result['discrepancies'].append({
                'type': 'tradier_has_positions_db_empty',
                'message': f"Tradier has {result['tradier_positions']} positions but ARES DB has none",
                'suggestion': 'Positions may have been opened manually or DB not synced'
            })

        result['success'] = True
        result['synced'] = len(result['discrepancies']) == 0
        result['tradier_positions_detail'] = tradier_data.get('positions', [])
        result['tradier_orders'] = tradier_data.get('orders', [])

    except Exception as e:
        logger.error(f"Sync error: {e}")
        result['error'] = str(e)

    return result


@router.get("/tradier-diagnose")
async def diagnose_tradier_connection():
    """
    Diagnostic endpoint to debug Tradier connection issues.
    Tests each step of the balance fetch process.
    """
    results = {
        "steps": [],
        "success": False,
        "final_balance": None
    }

    # Step 1: Check TradierDataFetcher availability
    results["steps"].append({
        "step": 1,
        "name": "TradierDataFetcher available",
        "success": TRADIER_AVAILABLE,
        "value": str(TradierDataFetcher) if TradierDataFetcher else "None"
    })
    if not TRADIER_AVAILABLE:
        results["final_error"] = "TradierDataFetcher not available"
        return results

    # Step 2: Check unified_config import
    try:
        from unified_config import APIConfig
        results["steps"].append({
            "step": 2,
            "name": "Import unified_config.APIConfig",
            "success": True
        })
    except Exception as e:
        results["steps"].append({
            "step": 2,
            "name": "Import unified_config.APIConfig",
            "success": False,
            "error": str(e)
        })
        results["final_error"] = f"Step 2 failed: {e}"
        return results

    # Step 3: Check SANDBOX credentials (ARES uses sandbox account)
    sandbox_api_key = getattr(APIConfig, 'TRADIER_SANDBOX_API_KEY', None)
    sandbox_account_id = getattr(APIConfig, 'TRADIER_SANDBOX_ACCOUNT_ID', None)

    results["steps"].append({
        "step": 3,
        "name": "Check SANDBOX credentials (ARES uses sandbox)",
        "success": bool(sandbox_api_key and sandbox_account_id),
        "TRADIER_SANDBOX_API_KEY": "SET" if sandbox_api_key else "NOT SET",
        "TRADIER_SANDBOX_ACCOUNT_ID": sandbox_account_id[:4] + "..." if sandbox_account_id else "NOT SET"
    })

    # ARES uses SANDBOX credentials
    final_api_key = sandbox_api_key
    final_account_id = sandbox_account_id

    if not final_api_key or not final_account_id:
        results["final_error"] = "No SANDBOX Tradier credentials configured"
        return results

    # Step 4: Create TradierDataFetcher with SANDBOX mode
    try:
        tradier = TradierDataFetcher(
            api_key=final_api_key,
            account_id=final_account_id,
            sandbox=True  # ARES uses SANDBOX
        )
        results["steps"].append({
            "step": 4,
            "name": "Create TradierDataFetcher (SANDBOX)",
            "success": True,
            "sandbox_mode": tradier.sandbox if hasattr(tradier, 'sandbox') else "unknown"
        })
    except Exception as e:
        results["steps"].append({
            "step": 4,
            "name": "Create TradierDataFetcher (SANDBOX)",
            "success": False,
            "error": str(e)
        })
        results["final_error"] = f"Step 4 failed: {e}"
        return results

    # Step 5: Fetch account balance
    try:
        balance = tradier.get_account_balance()
        results["steps"].append({
            "step": 5,
            "name": "Fetch account balance",
            "success": bool(balance),
            "balance": balance
        })
        if balance:
            results["success"] = True
            results["final_balance"] = balance.get('total_equity', 0)
        else:
            results["final_error"] = "Empty balance response"
    except Exception as e:
        import traceback
        results["steps"].append({
            "step": 5,
            "name": "Fetch account balance",
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        })
        results["final_error"] = f"Step 5 failed: {e}"

    return results


@router.get("/db-diagnose")
async def diagnose_database_state():
    """
    Diagnostic endpoint to check ares_positions database state.
    Shows why equity curve might be empty.
    """
    results = {
        "total_positions": 0,
        "by_status": {},
        "positions": [],
        "equity_curve_eligible": 0,
        "issues": []
    }

    try:
        from database_adapter import get_connection
        conn = get_connection()
        cursor = conn.cursor()

        # Get all positions with their key fields
        cursor.execute('''
            SELECT position_id, status, open_time, close_time, realized_pnl,
                   put_short_strike, call_short_strike, contracts, total_credit
            FROM ares_positions
            ORDER BY open_time DESC
            LIMIT 20
        ''')
        rows = cursor.fetchall()

        for row in rows:
            pos = {
                "position_id": row[0],
                "status": row[1],
                "open_time": str(row[2]) if row[2] else None,
                "close_time": str(row[3]) if row[3] else None,
                "realized_pnl": float(row[4]) if row[4] else 0,
                "put_short": float(row[5]) if row[5] else None,
                "call_short": float(row[6]) if row[6] else None,
                "contracts": row[7],
                "total_credit": float(row[8]) if row[8] else None
            }
            results["positions"].append(pos)

            # Track by status
            status = row[1] or "unknown"
            results["by_status"][status] = results["by_status"].get(status, 0) + 1

            # Check if eligible for equity curve
            if status in ('closed', 'expired') and row[3] is not None:
                results["equity_curve_eligible"] += 1

            # Identify issues
            if status in ('closed', 'expired') and row[3] is None:
                results["issues"].append(f"{row[0]}: closed but no close_time")
            if row[4] is None and status in ('closed', 'expired'):
                results["issues"].append(f"{row[0]}: closed but no realized_pnl")

        results["total_positions"] = len(rows)

        # Count total in table
        cursor.execute("SELECT COUNT(*) FROM ares_positions")
        total = cursor.fetchone()[0]
        results["total_in_table"] = total

        conn.close()

        # Summary
        if results["equity_curve_eligible"] == 0:
            results["diagnosis"] = "No positions eligible for equity curve - all are open or missing close_time"
        else:
            results["diagnosis"] = f"{results['equity_curve_eligible']} positions should appear in equity curve"

    except Exception as e:
        import traceback
        results["error"] = str(e)
        results["traceback"] = traceback.format_exc()

    return results


@router.get("/status")
async def get_ares_status():
    """
    Get current ARES bot status.

    Returns mode, capital, P&L, positions, configuration, and heartbeat.
    """
    ares = get_ares_instance()

    # Get heartbeat info
    heartbeat = _get_heartbeat('ARES')

    # Calculate trading window status based on actual time (needed for both code paths)
    now = datetime.now(ZoneInfo("America/Chicago"))
    current_time_str = now.strftime('%Y-%m-%d %H:%M:%S CT')

    # ARES trading window: 8:30 AM - 2:45 PM CT (market closes at 3:00 PM CT)
    entry_start = "08:30"
    entry_end = "14:45"  # Stop new entries 15 min before close

    # Check for early close days (typically day before Thanksgiving, Christmas Eve)
    # Dec 24 is typically 1 PM ET = 12 PM CT early close
    # Dec 31 is a NORMAL trading day (closes at 3 PM CT)
    if now.month == 12 and now.day == 24:
        entry_end = "11:50"  # Christmas Eve early close (10 min before 12:00 PM)

    start_parts = entry_start.split(':')
    end_parts = entry_end.split(':')
    start_time = now.replace(hour=int(start_parts[0]), minute=int(start_parts[1]), second=0, microsecond=0)
    end_time = now.replace(hour=int(end_parts[0]), minute=int(end_parts[1]), second=0, microsecond=0)

    is_weekday = now.weekday() < 5
    in_window = is_weekday and start_time <= now <= end_time
    trading_window_status = "OPEN" if in_window else "CLOSED"

    if not ares:
        # ARES not running in this process - read stats from database
        total_pnl = 0
        unrealized_pnl = 0  # Will calculate using MTM if open positions exist
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

            # Get trade stats
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

            if row:
                trade_count = row[0] or 0
                open_count = row[1] or 0
                closed_count = row[2] or 0
                win_count = row[3] or 0
                total_pnl = float(row[4] or 0)
                traded_today = (row[5] or 0) > 0

            # Calculate unrealized P&L using MTM if there are open positions
            if open_count > 0:
                cursor.execute('''
                    SELECT position_id, total_credit, contracts, spread_width,
                           put_short_strike, put_long_strike, call_short_strike, call_long_strike,
                           expiration
                    FROM ares_positions
                    WHERE status = 'open'
                ''')
                open_positions = cursor.fetchall()
                if open_positions:
                    mtm_result = _calculate_ares_unrealized_pnl(open_positions)
                    unrealized_pnl = mtm_result['total_unrealized_pnl']
                    logger.debug(f"ARES status: MTM unrealized=${unrealized_pnl:.2f} via {mtm_result['method']}")

            conn.close()
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
        except Exception as e:
            logger.debug(f"Could not read ARES config from database: {e}")

        # Get actual Tradier account balance and positions - ARES MUST be connected to Tradier
        tradier_balance = _get_tradier_account_balance()
        tradier_positions_data = _get_tradier_positions()

        if tradier_balance.get('connected') and tradier_balance.get('total_equity', 0) > 0:
            # Use actual Tradier balance
            capital = round(tradier_balance['total_equity'], 2)
            sandbox_connected = True
            tradier_error = None
            capital_message = f"Connected to Tradier {'sandbox' if tradier_balance.get('sandbox') else 'production'}"
        else:
            # NOT connected to Tradier - this is an error state, not fallback
            tradier_error = tradier_balance.get('error', 'Unknown connection error')
            sandbox_connected = False
            # Still show paper capital for display, but clearly indicate error
            capital = 100000  # Paper capital for display only
            capital_message = f"ERROR: Not connected to Tradier - {tradier_error}"
            logger.error(f"ARES Tradier connection failed: {tradier_error}")

        # Get Tradier position counts for sync check
        tradier_open_positions = len(tradier_positions_data.get('positions', []))
        tradier_recent_orders = len(tradier_positions_data.get('orders', []))

        # Determine if ARES is actually active based on heartbeat
        scan_interval = 5
        is_active, active_reason = _is_ares_actually_active(heartbeat, scan_interval)

        # current_equity = starting_capital + realized + unrealized
        # Unrealized P&L is now always calculated using MTM when open positions exist
        # Get starting capital from config table (NOT hardcoded)
        starting_capital = 100000  # Default for ARES (SPY bot)
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM autonomous_config WHERE key = 'ares_starting_capital'")
            config_row = cursor.fetchone()
            if config_row and config_row[0]:
                starting_capital = float(config_row[0])
            conn.close()
        except Exception:
            pass  # Use default if config lookup fails
        current_equity = starting_capital + total_pnl + unrealized_pnl

        return {
            "success": True,
            "data": {
                "mode": stored_mode,
                "ticker": stored_ticker,
                "is_spy_sandbox": stored_ticker == "SPY",
                "capital": capital,
                "starting_capital": starting_capital,
                "current_equity": round(current_equity, 2),
                "capital_source": "tradier" if sandbox_connected else "paper_fallback",
                "total_pnl": round(total_pnl, 2),
                # Return None to frontend when live pricing unavailable
                "unrealized_pnl": round(unrealized_pnl, 2) if unrealized_pnl is not None else None,
                "trade_count": trade_count,
                "win_rate": win_rate,
                "open_positions": open_count,
                "closed_positions": closed_count,
                "tradier_open_positions": tradier_open_positions,
                "tradier_recent_orders": tradier_recent_orders,
                "positions_synced": open_count == tradier_open_positions,
                "traded_today": traded_today,
                "in_trading_window": in_window,
                "trading_window_status": trading_window_status,
                "trading_window_end": entry_end,
                "high_water_mark": capital,
                "current_time": current_time_str,
                "is_active": is_active,
                "active_reason": active_reason,
                "scan_interval_minutes": scan_interval,
                "heartbeat": heartbeat,
                "sandbox_connected": sandbox_connected,
                "tradier_error": tradier_error,
                "tradier_account_id": tradier_balance.get('account_id') if sandbox_connected else None,
                "option_buying_power": tradier_balance.get('option_buying_power', 0) if sandbox_connected else 0,
                "config": {
                    "risk_per_trade": 10.0,
                    "spread_width": 10.0,
                    "sd_multiplier": 1.0,
                    "ticker": stored_ticker,
                    "target_return": "10% monthly"
                },
                "source": "tradier" if sandbox_connected else "error",
                "message": capital_message
            }
        }

    try:
        status = ares.get_status()
        scan_interval = 5
        is_active, active_reason = _is_ares_actually_active(heartbeat, scan_interval)
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
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 'open' THEN 1 ELSE 0 END) as open_count,
                    SUM(CASE WHEN status IN ('closed', 'expired') THEN 1 ELSE 0 END) as closed_count,
                    SUM(CASE WHEN status IN ('closed', 'expired') AND realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
                    COALESCE(SUM(CASE WHEN status IN ('closed', 'expired') THEN realized_pnl ELSE 0 END), 0) as total_pnl
                FROM ares_positions
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
            logger.debug(f"Could not read ARES stats from database: {db_err}")

        # Use database values for accurate P&L tracking
        status['total_pnl'] = db_total_pnl
        status['trade_count'] = db_trade_count
        status['win_rate'] = round((db_win_count / db_closed_count) * 100, 1) if db_closed_count > 0 else 0
        status['open_positions'] = db_open_count
        status['closed_positions'] = db_closed_count

        # Ensure capital fields exist
        if 'capital' not in status:
            status['capital'] = 100000

        # Add Tradier connection status (required by frontend)
        # ALWAYS fetch Tradier balance and positions to ensure we have real data
        tradier_balance = _get_tradier_account_balance()
        tradier_positions_data = _get_tradier_positions()

        # Add Tradier position counts for sync check
        tradier_open_positions = len(tradier_positions_data.get('positions', []))
        tradier_recent_orders = len(tradier_positions_data.get('orders', []))
        status['tradier_open_positions'] = tradier_open_positions
        status['tradier_recent_orders'] = tradier_recent_orders
        status['positions_synced'] = status.get('open_positions', 0) == tradier_open_positions

        if tradier_balance.get('connected') and tradier_balance.get('total_equity', 0) > 0:
            status['sandbox_connected'] = True
            status['tradier_error'] = None
            status['tradier_account_id'] = tradier_balance.get('account_id')
            status['option_buying_power'] = tradier_balance.get('option_buying_power', 0)
            # ALWAYS update capital from Tradier when connected - this is the real balance
            status['capital'] = round(tradier_balance['total_equity'], 2)
            status['capital_source'] = 'tradier'
            status['message'] = f"Connected to Tradier {'sandbox' if tradier_balance.get('sandbox') else 'production'}"
        else:
            status['sandbox_connected'] = False
            status['tradier_error'] = tradier_balance.get('error', 'Unknown connection error')
            status['tradier_account_id'] = None
            status['option_buying_power'] = 0
            status['capital_source'] = 'paper_fallback'
            status['message'] = f"ERROR: Not connected to Tradier - {status['tradier_error']}"
            logger.warning(f"ARES Tradier connection failed: {status['tradier_error']}")

        # Calculate current_equity = starting_capital + realized + unrealized (matches equity curve)
        # Get starting capital from config table (NOT hardcoded)
        starting_capital = 100000  # Default for ARES (SPY bot)
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM autonomous_config WHERE key = 'ares_starting_capital'")
            config_row = cursor.fetchone()
            if config_row and config_row[0]:
                starting_capital = float(config_row[0])
            conn.close()
        except Exception:
            pass  # Use default if config lookup fails
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
        logger.error(f"Error getting ARES status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/positions")
async def get_ares_positions():
    """
    Get ARES open and recently closed positions.

    Returns Iron Condor positions with full details including GEX and Oracle context.
    Field names match frontend IronCondorPosition interface.
    """
    # Always read from database for reliability
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Try to get positions with extended columns first
        # Falls back to basic columns if migration hasn't run yet
        use_extended_columns = True
        try:
            cursor.execute('''
                SELECT
                    position_id, open_time, expiration,
                    put_long_strike, put_short_strike, call_short_strike, call_long_strike,
                    put_credit, call_credit, total_credit,
                    contracts, spread_width, max_loss, status,
                    underlying_price_at_entry, vix_at_entry,
                    COALESCE(ticker, CASE WHEN spread_width <= 5 THEN 'SPY' ELSE 'SPX' END) as ticker,
                    gex_regime, call_wall, put_wall, flip_point, net_gex,
                    oracle_confidence, oracle_win_probability, oracle_advice, oracle_reasoning, oracle_top_factors
                FROM ares_positions
                WHERE status = 'open'
                ORDER BY open_time DESC
            ''')
            open_rows = cursor.fetchall()

            # Get closed positions (last 100) with all columns
            cursor.execute('''
                SELECT
                    position_id, open_time, close_time, expiration,
                    put_long_strike, put_short_strike, call_short_strike, call_long_strike,
                    put_credit, call_credit, total_credit,
                    contracts, spread_width, max_loss, close_price, realized_pnl, status,
                    underlying_price_at_entry, vix_at_entry,
                    COALESCE(ticker, CASE WHEN spread_width <= 5 THEN 'SPY' ELSE 'SPX' END) as ticker,
                    gex_regime, call_wall, put_wall, flip_point, net_gex,
                    oracle_confidence, oracle_win_probability, oracle_advice, oracle_reasoning, oracle_top_factors,
                    close_reason
                FROM ares_positions
                WHERE status IN ('closed', 'expired')
                ORDER BY close_time DESC
                LIMIT 100
            ''')
            closed_rows = cursor.fetchall()
        except Exception as col_err:
            # Fallback: Extended columns don't exist yet - use basic query
            logger.info(f"Using basic columns (extended columns not yet migrated): {col_err}")
            use_extended_columns = False

            cursor.execute('''
                SELECT
                    position_id, open_time, expiration,
                    put_long_strike, put_short_strike, call_short_strike, call_long_strike,
                    put_credit, call_credit, total_credit,
                    contracts, spread_width, max_loss, status,
                    underlying_price_at_entry, vix_at_entry
                FROM ares_positions
                WHERE status = 'open'
                ORDER BY open_time DESC
            ''')
            open_rows = cursor.fetchall()

            cursor.execute('''
                SELECT
                    position_id, open_time, close_time, expiration,
                    put_long_strike, put_short_strike, call_short_strike, call_long_strike,
                    put_credit, call_credit, total_credit,
                    contracts, spread_width, max_loss, close_price, realized_pnl, status,
                    underlying_price_at_entry, vix_at_entry
                FROM ares_positions
                WHERE status IN ('closed', 'expired')
                ORDER BY close_time DESC
                LIMIT 100
            ''')
            closed_rows = cursor.fetchall()

        conn.close()

        def _format_time_iso(time_str):
            """Convert time string to ISO format."""
            if not time_str:
                return None
            try:
                # Try parsing various formats
                for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%dT%H:%M:%S']:
                    try:
                        dt = datetime.strptime(str(time_str), fmt)
                        return dt.replace(tzinfo=ZoneInfo("America/Chicago")).isoformat()
                    except ValueError:
                        continue
                return str(time_str)
            except (TypeError, AttributeError) as e:
                logger.debug(f"Could not format time {time_str}: {e}")
                return str(time_str) if time_str else None

        # Format open positions - field names match frontend IronCondorPosition interface
        open_positions = []
        for row in open_rows:
            if use_extended_columns:
                (pos_id, open_time, exp, put_long, put_short, call_short, call_long,
                 put_cr, call_cr, total_cr, contracts, spread_w, max_loss, status,
                 underlying_price, vix, ticker, gex_regime, call_wall, put_wall, flip_point, net_gex,
                 oracle_conf, oracle_win_prob, oracle_advice, oracle_reasoning, oracle_factors) = row
            else:
                # Basic columns only
                (pos_id, open_time, exp, put_long, put_short, call_short, call_long,
                 put_cr, call_cr, total_cr, contracts, spread_w, max_loss, status,
                 underlying_price, vix) = row
                ticker = "SPY" if spread_w and spread_w <= 5 else "SPX"
                gex_regime = call_wall = put_wall = flip_point = net_gex = None
                oracle_conf = oracle_win_prob = oracle_advice = oracle_reasoning = oracle_factors = None

            # Calculate DTE
            dte = 0
            if exp:
                try:
                    exp_date = datetime.strptime(str(exp), "%Y-%m-%d").date()
                    today = datetime.now(ZoneInfo("America/Chicago")).date()
                    dte = (exp_date - today).days
                except (ValueError, TypeError):
                    pass  # Keep default dte=0 if date parsing fails

            open_positions.append({
                "position_id": pos_id,
                "ticker": ticker or "SPY",
                # Time fields - use open_time (frontend expects this name)
                "open_time": str(open_time) if open_time else None,
                "open_time_iso": _format_time_iso(open_time),
                "expiration": str(exp) if exp else None,
                "dte": dte,
                "is_0dte": dte == 0,
                # Strike prices
                "put_long_strike": float(put_long) if put_long else 0,
                "put_short_strike": float(put_short) if put_short else 0,
                "call_short_strike": float(call_short) if call_short else 0,
                "call_long_strike": float(call_long) if call_long else 0,
                # Spread descriptions
                "put_spread": f"{put_long}/{put_short}P",
                "call_spread": f"{call_short}/{call_long}C",
                # Credits
                "put_credit": float(put_cr) if put_cr else 0,
                "call_credit": float(call_cr) if call_cr else 0,
                "total_credit": float(total_cr) if total_cr else 0,
                "contracts": contracts or 0,
                "spread_width": float(spread_w) if spread_w else 0,
                "max_loss": float(max_loss) if max_loss else 0,
                "max_profit": float(total_cr or 0) * 100 * (contracts or 0),
                "premium_collected": float(total_cr or 0) * 100 * (contracts or 0),
                # Market data at entry
                "underlying_at_entry": float(underlying_price) if underlying_price else None,
                "vix_at_entry": float(vix) if vix else None,
                # GEX Context (audit trail)
                "gex_regime": gex_regime or "NEUTRAL",
                "call_wall": float(call_wall) if call_wall else None,
                "put_wall": float(put_wall) if put_wall else None,
                "flip_point": float(flip_point) if flip_point else None,
                "net_gex": float(net_gex) if net_gex else None,
                # Oracle Context (audit trail)
                "oracle_confidence": float(oracle_conf) if oracle_conf else None,
                "oracle_win_probability": float(oracle_win_prob) if oracle_win_prob else None,
                "oracle_advice": oracle_advice,
                "oracle_reasoning": oracle_reasoning,
                "oracle_top_factors": oracle_factors,
                "status": status
            })

        # Format closed positions
        closed_positions = []
        for row in closed_rows:
            if use_extended_columns:
                (pos_id, open_time, close_time, exp, put_long, put_short, call_short, call_long,
                 put_cr, call_cr, total_cr, contracts, spread_w, max_loss, close_price, realized_pnl, status,
                 underlying_price, vix, ticker, gex_regime, call_wall, put_wall, flip_point, net_gex,
                 oracle_conf, oracle_win_prob, oracle_advice, oracle_reasoning, oracle_factors,
                 close_reason) = row
            else:
                # Basic columns only
                (pos_id, open_time, close_time, exp, put_long, put_short, call_short, call_long,
                 put_cr, call_cr, total_cr, contracts, spread_w, max_loss, close_price, realized_pnl, status,
                 underlying_price, vix) = row
                ticker = "SPY" if spread_w and spread_w <= 5 else "SPX"
                gex_regime = call_wall = put_wall = flip_point = net_gex = None
                oracle_conf = oracle_win_prob = oracle_advice = oracle_reasoning = oracle_factors = None
                close_reason = None

            max_profit = float(total_cr or 0) * 100 * (contracts or 0)
            return_pct = round((float(realized_pnl or 0) / max_profit) * 100, 1) if max_profit else 0

            # Calculate DTE at close (for historical context)
            dte = 0
            if exp:
                try:
                    exp_date = datetime.strptime(str(exp), "%Y-%m-%d").date()
                    close_date = datetime.strptime(str(close_time)[:10], "%Y-%m-%d").date() if close_time else datetime.now(ZoneInfo("America/Chicago")).date()
                    dte = (exp_date - close_date).days
                except (ValueError, TypeError):
                    pass  # Keep default dte=0 if date parsing fails

            closed_positions.append({
                "position_id": pos_id,
                "ticker": ticker or "SPY",
                # Time fields - match frontend interface
                "open_time": str(open_time) if open_time else None,
                "open_time_iso": _format_time_iso(open_time),
                "close_time": str(close_time) if close_time else None,
                "close_time_iso": _format_time_iso(close_time),
                "expiration": str(exp) if exp else None,
                "dte": dte,
                "is_0dte": dte == 0,
                # Strike prices
                "put_long_strike": float(put_long) if put_long else 0,
                "put_short_strike": float(put_short) if put_short else 0,
                "call_short_strike": float(call_short) if call_short else 0,
                "call_long_strike": float(call_long) if call_long else 0,
                # Spread descriptions
                "put_spread": f"{put_long}/{put_short}P",
                "call_spread": f"{call_short}/{call_long}C",
                "contracts": contracts or 0,
                "spread_width": float(spread_w) if spread_w else 0,
                "total_credit": float(total_cr) if total_cr else 0,
                "max_profit": max_profit,
                "premium_collected": max_profit,
                "max_loss": float(max_loss) if max_loss else 0,
                "close_price": float(close_price) if close_price else 0,
                "realized_pnl": float(realized_pnl) if realized_pnl else 0,
                "return_pct": return_pct,
                "close_reason": close_reason or "unknown",
                # Market data at entry
                "underlying_at_entry": float(underlying_price) if underlying_price else None,
                "vix_at_entry": float(vix) if vix else None,
                # GEX Context (audit trail)
                "gex_regime": gex_regime or "NEUTRAL",
                "call_wall": float(call_wall) if call_wall else None,
                "put_wall": float(put_wall) if put_wall else None,
                "flip_point": float(flip_point) if flip_point else None,
                "net_gex": float(net_gex) if net_gex else None,
                # Oracle Context (audit trail)
                "oracle_confidence": float(oracle_conf) if oracle_conf else None,
                "oracle_win_probability": float(oracle_win_prob) if oracle_win_prob else None,
                "oracle_advice": oracle_advice,
                "oracle_reasoning": oracle_reasoning,
                "oracle_top_factors": oracle_factors,
                "status": status
            })

        return {
            "success": True,
            "data": {
                "positions": open_positions,  # Also use 'positions' key for compatibility
                "open_positions": open_positions,
                "closed_positions": closed_positions,
                "open_count": len(open_positions),
                "closed_count": len(closed_positions)
            }
        }
    except Exception as e:
        logger.error(f"Error getting ARES positions: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": True,
            "data": {
                "positions": [],
                "open_positions": [],
                "closed_positions": [],
                "message": f"Could not load positions: {str(e)}"
            }
        }


@router.get("/equity-curve")
async def get_ares_equity_curve(days: int = 30):
    """
    Get ARES equity curve data including unrealized P&L from open positions.

    Args:
        days: Number of days of history (default 30)
    """
    ares = get_ares_instance()

    # CRITICAL FIX: Use fixed starting capital for equity curve calculations
    # Previously used Tradier balance which already includes realized P&L, causing double-counting
    # The equity curve should show: starting_capital + cumulative_realized_pnl + unrealized_pnl
    starting_capital = 100000  # Default for ARES (SPY bot)

    # Check config table for override (consistent with intraday endpoint)
    try:
        from database_adapter import get_connection
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM autonomous_config WHERE key = 'ares_starting_capital'")
        config_row = cursor.fetchone()
        if config_row and config_row[0]:
            starting_capital = float(config_row[0])
        conn.close()
    except Exception:
        pass

    today = datetime.now(ZoneInfo("America/Chicago")).strftime('%Y-%m-%d')
    unrealized_pnl = 0.0
    open_positions_count = 0

    if not ares:
        # ARES not running in this process - read from database directly
        try:
            from database_adapter import get_connection
            conn = get_connection()
            cursor = conn.cursor()

            # Get closed positions from database
            cursor.execute('''
                SELECT DATE(close_time AT TIME ZONE 'America/Chicago') as close_date,
                       realized_pnl, position_id
                FROM ares_positions
                WHERE status IN ('closed', 'expired')
                AND close_time IS NOT NULL
                ORDER BY close_time ASC
            ''')
            rows = cursor.fetchall()

            # Get open positions for unrealized P&L calculation
            cursor.execute('''
                SELECT position_id, total_credit, contracts,
                       put_long_strike, put_short_strike, call_short_strike, call_long_strike,
                       expiration
                FROM ares_positions
                WHERE status = 'open'
            ''')
            open_positions = cursor.fetchall()
            open_positions_count = len(open_positions)
            conn.close()

            # Calculate unrealized P&L from open positions using MTM
            if open_positions and MTM_AVAILABLE:
                for pos in open_positions:
                    pos_id, total_credit, contracts, pl, ps, cs, cl, exp = pos
                    try:
                        exp_str = exp.strftime('%Y-%m-%d') if hasattr(exp, 'strftime') else str(exp)
                        mtm_result = calculate_ic_mark_to_market(
                            underlying='SPY',
                            expiration=exp_str,
                            put_short_strike=float(ps) if ps else 0,
                            put_long_strike=float(pl) if pl else 0,
                            call_short_strike=float(cs) if cs else 0,
                            call_long_strike=float(cl) if cl else 0,
                            contracts=int(contracts) if contracts else 1,
                            entry_credit=float(total_credit) if total_credit else 0
                        )
                        if mtm_result and mtm_result.get('success'):
                            pos_pnl = mtm_result.get('unrealized_pnl', 0) or 0
                            unrealized_pnl += pos_pnl
                    except Exception as e:
                        logger.debug(f"ARES MTM calculation failed for {pos_id}: {e}")

            # Build equity curve from database positions
            equity_curve = []
            positions_by_date = {}
            cumulative_pnl = 0

            if rows:
                for row in rows:
                    close_date, pnl, pos_id = row
                    date_key = str(close_date) if close_date else None
                    if date_key:
                        if date_key not in positions_by_date:
                            positions_by_date[date_key] = []
                        positions_by_date[date_key].append({'pnl': float(pnl or 0), 'id': pos_id})

                sorted_dates = sorted(positions_by_date.keys())

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

            # Add today's entry with unrealized P&L from open positions
            total_pnl_with_unrealized = cumulative_pnl + unrealized_pnl
            current_equity_with_unrealized = starting_capital + total_pnl_with_unrealized

            # Always add today's data point if we have open positions or closed positions
            if open_positions_count > 0 or rows:
                # Remove duplicate today entry if exists
                if equity_curve and equity_curve[-1]["date"] == today:
                    equity_curve.pop()

                equity_curve.append({
                    "date": today,
                    "equity": round(current_equity_with_unrealized, 2),
                    "pnl": round(total_pnl_with_unrealized, 2),
                    "realized_pnl": round(cumulative_pnl, 2),
                    "unrealized_pnl": round(unrealized_pnl, 2),
                    "daily_pnl": round(unrealized_pnl, 2),
                    "return_pct": round((total_pnl_with_unrealized / starting_capital) * 100, 2),
                    "open_positions": open_positions_count
                })

                return {
                    "success": True,
                    "data": {
                        "equity_curve": equity_curve,
                        "starting_capital": starting_capital,
                        "current_equity": round(current_equity_with_unrealized, 2),
                        "total_pnl": round(total_pnl_with_unrealized, 2),
                        "realized_pnl": round(cumulative_pnl, 2),
                        "unrealized_pnl": round(unrealized_pnl, 2),
                        "total_return_pct": round((total_pnl_with_unrealized / starting_capital) * 100, 2),
                        "closed_positions_count": len(rows) if rows else 0,
                        "open_positions_count": open_positions_count,
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

        # Calculate unrealized P&L from open positions
        unrealized_pnl = 0.0
        open_positions_count = len(ares.open_positions) if hasattr(ares, 'open_positions') else 0

        if hasattr(ares, 'open_positions') and ares.open_positions and MTM_AVAILABLE:
            for pos in ares.open_positions:
                try:
                    exp_str = pos.expiration if isinstance(pos.expiration, str) else str(pos.expiration)
                    mtm_result = calculate_ic_mark_to_market(
                        underlying='SPY',
                        expiration=exp_str,
                        put_short_strike=float(pos.put_short_strike) if hasattr(pos, 'put_short_strike') else 0,
                        put_long_strike=float(pos.put_long_strike) if hasattr(pos, 'put_long_strike') else 0,
                        call_short_strike=float(pos.call_short_strike) if hasattr(pos, 'call_short_strike') else 0,
                        call_long_strike=float(pos.call_long_strike) if hasattr(pos, 'call_long_strike') else 0,
                        contracts=int(pos.contracts) if hasattr(pos, 'contracts') else 1,
                        entry_credit=float(pos.total_credit) if hasattr(pos, 'total_credit') else 0
                    )
                    if mtm_result and mtm_result.get('success'):
                        pos_pnl = mtm_result.get('unrealized_pnl', 0) or 0
                        unrealized_pnl += pos_pnl
                except Exception as e:
                    logger.debug(f"ARES MTM calculation failed for position: {e}")

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

        # Add today's entry with unrealized P&L
        total_pnl_with_unrealized = cumulative_pnl + unrealized_pnl
        current_equity_with_unrealized = starting_capital + total_pnl_with_unrealized

        # Remove duplicate today entry if exists
        if equity_curve and equity_curve[-1]["date"] == today:
            equity_curve.pop()

        # Add today's data point
        equity_curve.append({
            "date": today,
            "equity": round(current_equity_with_unrealized, 2),
            "pnl": round(total_pnl_with_unrealized, 2),
            "realized_pnl": round(cumulative_pnl, 2),
            "unrealized_pnl": round(unrealized_pnl, 2),
            "daily_pnl": round(unrealized_pnl, 2),
            "return_pct": round((total_pnl_with_unrealized / starting_capital) * 100, 2),
            "open_positions": open_positions_count
        })

        # Add starting point if still empty
        if len(equity_curve) == 1:
            equity_curve.insert(0, {
                "date": today,
                "equity": starting_capital,
                "pnl": 0,
                "daily_pnl": 0,
                "return_pct": 0
            })

        return {
            "success": True,
            "data": {
                "equity_curve": equity_curve,
                "starting_capital": starting_capital,
                "current_equity": round(current_equity_with_unrealized, 2),
                "total_pnl": round(total_pnl_with_unrealized, 2),
                "realized_pnl": round(cumulative_pnl, 2),
                "unrealized_pnl": round(unrealized_pnl, 2),
                "total_return_pct": round((total_pnl_with_unrealized / starting_capital) * 100, 2),
                "closed_positions_count": len(ares.closed_positions),
                "open_positions_count": open_positions_count
            }
        }
    except Exception as e:
        logger.error(f"Error getting ARES equity curve: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/equity-curve/intraday")
async def get_ares_intraday_equity(date: str = None):
    """
    Get ARES intraday equity curve with 5-minute interval snapshots.

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

    # IMPORTANT: starting_capital is the FIXED amount the bot started with, NOT current account balance
    # Tradier total_equity is current balance (starting + all P&L), using it here would double-count P&L
    starting_capital = 100000  # Default starting capital for ARES

    try:
        from database_adapter import get_connection
        conn = get_connection()
        cursor = conn.cursor()

        # Get starting capital from config (if stored)
        cursor.execute("""
            SELECT value FROM autonomous_config WHERE key = 'ares_starting_capital'
        """)
        row = cursor.fetchone()
        if row and row[0]:
            try:
                starting_capital = float(row[0])
            except (ValueError, TypeError):
                pass

        # Get intraday snapshots for the requested date
        # All snapshot tables now have unrealized_pnl and realized_pnl columns
        cursor.execute("""
            SELECT timestamp, balance, unrealized_pnl, realized_pnl, open_positions, note
            FROM ares_equity_snapshots
            WHERE DATE(timestamp AT TIME ZONE 'America/Chicago') = %s
            ORDER BY timestamp ASC
        """, (today,))
        snapshots = cursor.fetchall()

        # Get total realized P&L from closed positions up to today
        cursor.execute("""
            SELECT COALESCE(SUM(realized_pnl), 0)
            FROM ares_positions
            WHERE status IN ('closed', 'expired')
            AND DATE(close_time AT TIME ZONE 'America/Chicago') <= %s
        """, (today,))
        total_realized_row = cursor.fetchone()
        total_realized = float(total_realized_row[0]) if total_realized_row and total_realized_row[0] else 0

        # Get today's closed positions P&L
        cursor.execute("""
            SELECT COALESCE(SUM(realized_pnl), 0), COUNT(*)
            FROM ares_positions
            WHERE status IN ('closed', 'expired')
            AND DATE(close_time AT TIME ZONE 'America/Chicago') = %s
        """, (today,))
        today_row = cursor.fetchone()
        today_realized = float(today_row[0]) if today_row and today_row[0] else 0
        today_closed_count = int(today_row[1]) if today_row and today_row[1] else 0

        # Calculate unrealized P&L from open positions
        unrealized_pnl = 0
        open_positions = []
        try:
            live_pnl_data = _calculate_live_unrealized_pnl()
            if live_pnl_data.get('success'):
                unrealized_pnl = live_pnl_data.get('total_unrealized_pnl', 0)
                open_positions = live_pnl_data.get('positions', [])
        except Exception as e:
            logger.debug(f"Error calculating unrealized P&L: {e}")

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

        # Add snapshots - recalculate equity from P&L to ensure consistency
        for snapshot in snapshots:
            ts, balance, snap_unrealized, snap_realized, open_count, note = snapshot
            snap_time = ts.astimezone(CENTRAL_TZ) if ts.tzinfo else ts

            # Use snapshot values - convert NULL to 0 (matches other bots)
            # CRITICAL: Do NOT use total_realized as fallback - it's cumulative all-time!
            snap_unrealized_val = float(snap_unrealized or 0)
            snap_realized_val = float(snap_realized or 0)
            # Recalculate equity: starting_capital + realized + unrealized (don't trust stored balance)
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
                "unrealized_pnl": round(unrealized_pnl, 2)
            })

        # Calculate high/low of day
        high_of_day = max(all_equities) if all_equities else starting_capital
        low_of_day = min(all_equities) if all_equities else starting_capital
        day_pnl = today_realized + unrealized_pnl

        return {
            "success": True,
            "date": today,
            "bot": "ARES",
            "data_points": data_points,
            "current_equity": round(current_equity, 2),
            "day_pnl": round(day_pnl, 2),
            "starting_equity": market_open_equity,  # Equity at market open (starting_capital + prev realized)
            "high_of_day": round(high_of_day, 2),
            "low_of_day": round(low_of_day, 2),
            "snapshots_count": len(snapshots)
        }

    except Exception as e:
        logger.error(f"Error getting ARES intraday equity: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e),
            "date": today,
            "bot": "ARES",
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
            "starting_equity": starting_capital,
            "high_of_day": starting_capital,
            "low_of_day": starting_capital,
            "snapshots_count": 0
        }


@router.get("/equity-curve/live")
async def get_ares_live_equity_curve():
    """
    Get ARES equity curve with LIVE intraday tracking.

    ALL DATA COMES FROM ALPHAGEX - not Tradier balance.

    Live Equity = Starting Capital + Realized P&L + Unrealized P&L

    Where:
    - Starting Capital: Stored in database (ares_starting_capital)
    - Realized P&L: Sum of realized_pnl from closed positions in ares_positions
    - Unrealized P&L: Calculated from open positions + current SPY price

    Returns equity curve with real-time live point.
    """
    now = datetime.now(ZoneInfo("America/Chicago"))
    today = now.strftime('%Y-%m-%d')
    current_time = now.strftime('%H:%M:%S')

    # Check if market is open (8:30 AM - 3:00 PM CT on weekdays)
    is_market_hours = (
        now.weekday() < 5 and
        now.hour >= 8 and now.hour < 15 and
        (now.hour > 8 or now.minute >= 30)
    )

    # Calculate LIVE unrealized P&L from AlphaGEX positions
    live_pnl_data = _calculate_live_unrealized_pnl()
    unrealized_pnl = live_pnl_data.get('total_unrealized_pnl', 0) if live_pnl_data.get('success') else 0
    current_price = live_pnl_data.get('current_price')
    open_positions = live_pnl_data.get('positions', [])
    open_position_count = live_pnl_data.get('position_count', 0)

    try:
        from database_adapter import get_connection
        conn = get_connection()
        cursor = conn.cursor()

        # Get or create starting capital record
        cursor.execute('''
            SELECT value FROM autonomous_config
            WHERE key = 'ares_starting_capital'
        ''')
        row = cursor.fetchone()

        if row and float(row[0]) > 0:
            starting_capital = float(row[0])
        else:
            # IMPORTANT: starting_capital is the FIXED initial amount, NOT current Tradier balance
            # Tradier total_equity = starting_capital + all P&L, using it would cause double-counting
            starting_capital = 100000  # Default starting capital for ARES
            # Store it for future reference
            cursor.execute('''
                INSERT INTO autonomous_config (key, value)
                VALUES ('ares_starting_capital', %s)
                ON CONFLICT (key) DO UPDATE SET value = %s
            ''', (str(starting_capital), str(starting_capital)))
            conn.commit()

        # Get ALL realized P&L from closed positions (total historical)
        cursor.execute('''
            SELECT COALESCE(SUM(realized_pnl), 0)
            FROM ares_positions
            WHERE status IN ('closed', 'expired')
        ''')
        total_realized_row = cursor.fetchone()
        total_realized_pnl = float(total_realized_row[0]) if total_realized_row and total_realized_row[0] else 0

        # Get historical closed positions for the equity curve (grouped by date)
        cursor.execute('''
            SELECT DATE(close_time AT TIME ZONE 'America/Chicago') as close_date,
                   realized_pnl, position_id, close_time
            FROM ares_positions
            WHERE status IN ('closed', 'expired')
            AND close_time IS NOT NULL
            ORDER BY close_time ASC
        ''')
        historical_rows = cursor.fetchall()

        # Get today's realized P&L specifically
        cursor.execute('''
            SELECT COALESCE(SUM(realized_pnl), 0), COUNT(*)
            FROM ares_positions
            WHERE status IN ('closed', 'expired')
            AND DATE(close_time AT TIME ZONE 'America/Chicago') = %s
        ''', (today,))
        today_row = cursor.fetchone()
        today_realized = float(today_row[0]) if today_row and today_row[0] else 0
        today_closed_count = int(today_row[1]) if today_row and today_row[1] else 0

        conn.close()

        # Build equity curve from historical data
        equity_curve = []
        positions_by_date = {}

        for row in historical_rows:
            close_date, pnl, pos_id, close_time = row
            date_key = str(close_date) if close_date else None
            if date_key:
                if date_key not in positions_by_date:
                    positions_by_date[date_key] = {'pnl': 0, 'count': 0, 'positions': []}
                positions_by_date[date_key]['pnl'] += float(pnl or 0)
                positions_by_date[date_key]['count'] += 1
                positions_by_date[date_key]['positions'].append(pos_id)

        sorted_dates = sorted(positions_by_date.keys())
        cumulative_realized = 0

        # Add starting point
        if sorted_dates:
            equity_curve.append({
                "date": sorted_dates[0],
                "time": "08:30:00",
                "equity": round(starting_capital, 2),
                "pnl": 0,
                "daily_pnl": 0,
                "return_pct": 0,
                "is_live": False,
                "source": "starting_point"
            })

        # Add historical end-of-day points
        for date_str in sorted_dates:
            daily_data = positions_by_date[date_str]
            daily_pnl = daily_data['pnl']
            cumulative_realized += daily_pnl

            equity_curve.append({
                "date": date_str,
                "time": "15:00:00",
                "equity": round(starting_capital + cumulative_realized, 2),
                "pnl": round(cumulative_realized, 2),
                "daily_pnl": round(daily_pnl, 2),
                "trades_closed": daily_data['count'],
                "return_pct": round((cumulative_realized / starting_capital) * 100, 2) if starting_capital > 0 else 0,
                "is_live": False,
                "source": "historical"
            })

        # Calculate LIVE equity from AlphaGEX data
        # Live Equity = Starting Capital + Total Realized P&L + Unrealized P&L
        total_pnl = total_realized_pnl + unrealized_pnl
        current_equity = starting_capital + total_pnl
        today_total_pnl = today_realized + unrealized_pnl

        # Add TODAY's market open point (yesterday's close value)
        equity_curve.append({
            "date": today,
            "time": "08:30:00",
            "equity": round(starting_capital + total_realized_pnl - today_realized, 2),
            "pnl": round(total_realized_pnl - today_realized, 2),
            "daily_pnl": 0,
            "return_pct": round(((total_realized_pnl - today_realized) / starting_capital) * 100, 2) if starting_capital > 0 else 0,
            "is_live": False,
            "source": "market_open",
            "label": "Market Open"
        })

        # Add LIVE current point - calculated from AlphaGEX
        equity_curve.append({
            "date": today,
            "time": current_time,
            "equity": round(current_equity, 2),
            "pnl": round(total_pnl, 2),
            "daily_pnl": round(today_total_pnl, 2),
            "daily_realized": round(today_realized, 2),
            "daily_unrealized": round(unrealized_pnl, 2),
            "return_pct": round((total_pnl / starting_capital) * 100, 2) if starting_capital > 0 else 0,
            "is_live": True,
            "source": "alphagex_calculated",
            "label": "LIVE",
            "current_spy_price": current_price
        })

        return {
            "success": True,
            "data": {
                "equity_curve": equity_curve,
                "starting_capital": round(starting_capital, 2),
                "current_equity": round(current_equity, 2),
                "total_pnl": round(total_pnl, 2),
                "total_realized_pnl": round(total_realized_pnl, 2),
                "total_unrealized_pnl": round(unrealized_pnl, 2),
                "total_return_pct": round((total_pnl / starting_capital) * 100, 2) if starting_capital > 0 else 0,
                "today": {
                    "date": today,
                    "time": current_time,
                    "realized_pnl": round(today_realized, 2),
                    "unrealized_pnl": round(unrealized_pnl, 2),
                    "total_pnl": round(today_total_pnl, 2),
                    "positions_closed": today_closed_count,
                    "positions_open": open_position_count
                },
                "open_positions": open_positions,
                "current_spy_price": current_price,
                "is_market_open": is_market_hours,
                "last_updated": now.isoformat(),
                "calculation_source": "alphagex"
            }
        }

    except Exception as e:
        logger.error(f"Error getting live equity curve: {e}")
        import traceback
        traceback.print_exc()

        # Fallback - return what we have from live P&L calculation
        fallback_equity = 100000 + unrealized_pnl
        return {
            "success": False,
            "data": {
                "equity_curve": [{
                    "date": today,
                    "time": current_time,
                    "equity": round(fallback_equity, 2),
                    "pnl": round(unrealized_pnl, 2),
                    "daily_pnl": round(unrealized_pnl, 2),
                    "return_pct": round((unrealized_pnl / 100000) * 100, 2),
                    "is_live": True,
                    "source": "alphagex_fallback"
                }],
                "starting_capital": 100000,
                "current_equity": round(fallback_equity, 2),
                "total_pnl": round(unrealized_pnl, 2),
                "total_unrealized_pnl": round(unrealized_pnl, 2),
                "current_spy_price": current_price,
                "calculation_source": "alphagex",
                "error": str(e)
            }
        }


@router.post("/equity-snapshot")
async def save_equity_snapshot():
    """
    Save current equity snapshot for intraday tracking.

    Call this periodically (e.g., every 5-15 minutes) during market hours
    to build detailed intraday equity curve.

    Saves: balance, unrealized_pnl, realized_pnl, open_positions
    """
    now = datetime.now(ZoneInfo("America/Chicago"))

    # Get current Tradier balance
    tradier_balance = _get_tradier_account_balance()

    if not tradier_balance.get('connected'):
        return {
            "success": False,
            "error": "Tradier not connected",
            "details": tradier_balance.get('error')
        }

    current_equity = tradier_balance.get('total_equity', 0)

    try:
        from database_adapter import get_connection
        conn = get_connection()
        cursor = conn.cursor()

        # Create table if not exists with all required columns
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ares_equity_snapshots (
                id SERIAL PRIMARY KEY,
                timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
                balance DECIMAL(12, 2) NOT NULL,
                unrealized_pnl DECIMAL(12, 2),
                realized_pnl DECIMAL(12, 2),
                option_buying_power DECIMAL(12, 2),
                open_positions INTEGER,
                note TEXT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        ''')

        # Add missing columns if they don't exist (for older tables)
        for col in ['unrealized_pnl', 'realized_pnl']:
            try:
                cursor.execute(f"ALTER TABLE ares_equity_snapshots ADD COLUMN IF NOT EXISTS {col} DECIMAL(12, 2)")
            except Exception:
                pass

        # Get open position count from Tradier
        tradier_positions = _get_tradier_positions()
        open_count = len(tradier_positions.get('positions', []))

        # Calculate realized P&L from closed positions
        cursor.execute('''
            SELECT COALESCE(SUM(realized_pnl), 0)
            FROM ares_positions
            WHERE status IN ('closed', 'expired')
        ''')
        realized_row = cursor.fetchone()
        realized_pnl = float(realized_row[0]) if realized_row and realized_row[0] else 0

        # Calculate unrealized P&L from open positions
        unrealized_pnl = 0
        try:
            live_pnl_data = _calculate_live_unrealized_pnl()
            if live_pnl_data.get('success'):
                unrealized_pnl = live_pnl_data.get('total_unrealized_pnl', 0)
        except Exception:
            pass

        # Insert snapshot with all fields
        cursor.execute('''
            INSERT INTO ares_equity_snapshots
            (timestamp, balance, unrealized_pnl, realized_pnl, option_buying_power, open_positions, note)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        ''', (
            now,
            current_equity,
            round(unrealized_pnl, 2),
            round(realized_pnl, 2),
            tradier_balance.get('option_buying_power', 0),
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
                "option_buying_power": round(tradier_balance.get('option_buying_power', 0), 2),
                "open_positions": open_count
            }
        }

    except Exception as e:
        logger.error(f"Error saving equity snapshot: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@router.get("/performance")
async def get_ares_performance():
    """
    Get ARES performance metrics.

    Returns detailed performance statistics.
    """
    ares = get_ares_instance()

    # IMPORTANT: starting_capital is the FIXED amount the bot started with, NOT current account balance
    # Tradier total_equity is current balance (starting + all P&L), using it here would double-count P&L
    starting_capital = 100000  # Default starting capital for ARES

    # Try to get from config table
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM autonomous_config WHERE key = 'ares_starting_capital'")
        row = cursor.fetchone()
        if row and row[0]:
            starting_capital = float(row[0])
        conn.close()
    except Exception:
        pass

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
                "current_capital": starting_capital,
                "return_pct": 0,
                "high_water_mark": starting_capital,
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
                id, log_time, level, message, details
            FROM ares_logs
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
        "entry_window": "08:30 - 14:45 CT",
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


@router.get("/tradier-connection")
async def check_tradier_connection():
    """
    Direct Tradier connection check - diagnose connection issues.

    This endpoint checks if ARES can connect to Tradier API directly,
    without needing the ARES trading bot to be running.

    Returns detailed diagnostic info about:
    - Credentials configuration
    - API connection status
    - Account balance
    - Any errors encountered
    """
    diagnostics = {
        "timestamp": datetime.now(ZoneInfo("America/Chicago")).isoformat(),
        "tradier_fetcher_available": TRADIER_AVAILABLE,
        "credentials": {},
        "connection": {},
        "balance": {}
    }

    # Check credentials
    try:
        from unified_config import APIConfig

        sandbox_key = getattr(APIConfig, 'TRADIER_SANDBOX_API_KEY', None)
        sandbox_account = getattr(APIConfig, 'TRADIER_SANDBOX_ACCOUNT_ID', None)
        prod_key = getattr(APIConfig, 'TRADIER_PROD_API_KEY', None)
        prod_account = getattr(APIConfig, 'TRADIER_PROD_ACCOUNT_ID', None)
        use_sandbox = getattr(APIConfig, 'TRADIER_SANDBOX', True)

        diagnostics["credentials"] = {
            "sandbox_api_key_set": bool(sandbox_key),
            "sandbox_account_id": sandbox_account or "NOT SET",
            "prod_api_key_set": bool(prod_key),
            "prod_account_id": prod_account or "NOT SET",
            "use_sandbox": use_sandbox,
            "effective_account": sandbox_account or prod_account or "NONE"
        }

        # Try to connect and get balance
        if TRADIER_AVAILABLE and TradierDataFetcher:
            # Select credentials based on mode
            if use_sandbox:
                api_key = sandbox_key or prod_key
                account_id = sandbox_account or prod_account
            else:
                api_key = prod_key or sandbox_key
                account_id = prod_account or sandbox_account

            if api_key and account_id:
                try:
                    tradier = TradierDataFetcher(
                        api_key=api_key,
                        account_id=account_id,
                        sandbox=use_sandbox
                    )
                    balance = tradier.get_account_balance()

                    if balance:
                        diagnostics["connection"] = {
                            "status": "CONNECTED",
                            "api_reachable": True,
                            "account_valid": True
                        }
                        diagnostics["balance"] = {
                            "total_equity": balance.get('total_equity', 0),
                            "option_buying_power": balance.get('option_buying_power', 0),
                            "total_cash": balance.get('total_cash', 0)
                        }
                    else:
                        diagnostics["connection"] = {
                            "status": "ERROR",
                            "error": "Empty response from Tradier API"
                        }
                except Exception as conn_err:
                    diagnostics["connection"] = {
                        "status": "ERROR",
                        "error": str(conn_err)
                    }
            else:
                diagnostics["connection"] = {
                    "status": "NO_CREDENTIALS",
                    "error": "API key or account ID not configured"
                }
        else:
            diagnostics["connection"] = {
                "status": "IMPORT_ERROR",
                "error": "TradierDataFetcher module not available"
            }

    except Exception as e:
        diagnostics["credentials"]["error"] = str(e)
        diagnostics["connection"] = {"status": "CONFIG_ERROR", "error": str(e)}

    # Determine overall status
    is_connected = diagnostics["connection"].get("status") == "CONNECTED"

    return {
        "success": is_connected,
        "connected": is_connected,
        "message": "Tradier connected successfully" if is_connected else f"Connection failed: {diagnostics['connection'].get('error', 'Unknown error')}",
        "diagnostics": diagnostics
    }


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
                AND DATE(close_time AT TIME ZONE 'America/Chicago') = %s
            ''', (today,))
            realized_row = cursor.fetchone()
            today_realized = float(realized_row[0]) if realized_row else 0
            conn.close()

            # Format open positions with entry context and calculate MTM
            positions = []
            today_date = datetime.now(ZoneInfo("America/Chicago")).date()
            total_unrealized = 0.0
            mtm_method = 'estimation'

            for row in open_rows:
                (pos_id, open_date, exp, put_long, put_short, call_short, call_long,
                 credit, contracts, max_loss, spread_width, status) = row

                credit_val = float(credit or 0)
                contracts_val = int(contracts or 0)
                credit_received = credit_val * 100 * contracts_val

                # Calculate DTE
                dte = None
                is_0dte = False
                try:
                    if exp:
                        exp_date = datetime.strptime(str(exp), '%Y-%m-%d').date()
                        dte = (exp_date - today_date).days
                        is_0dte = dte == 0
                except (ValueError, TypeError):
                    pass  # Keep default dte=None if date parsing fails

                # Calculate unrealized P&L using MTM
                pos_unrealized = None
                method = 'estimation'

                if MTM_AVAILABLE and exp and put_short and put_long and call_short and call_long:
                    try:
                        mtm_result = calculate_ic_mark_to_market(
                            underlying='SPY',
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
                        logger.debug(f"ARES live-pnl MTM failed for {pos_id}: {e}")

                positions.append({
                    'position_id': pos_id,
                    'open_date': str(open_date) if open_date else None,
                    'expiration': str(exp) if exp else None,
                    'put_long_strike': float(put_long) if put_long else 0,
                    'put_short_strike': float(put_short) if put_short else 0,
                    'call_short_strike': float(call_short) if call_short else 0,
                    'call_long_strike': float(call_long) if call_long else 0,
                    'credit_received': round(credit_received, 2),
                    'contracts': contracts_val,
                    'max_loss': round(float(max_loss or 0) * 100 * contracts_val, 2),
                    'spread_width': float(spread_width) if spread_width else 0,
                    'dte': dte,
                    'is_0dte': is_0dte,
                    'max_profit': round(credit_received, 2),
                    'strategy': 'IRON_CONDOR',
                    'direction': 'NEUTRAL',
                    'unrealized_pnl': round(pos_unrealized, 2) if pos_unrealized is not None else None,
                    'method': method
                })

            final_unrealized = round(total_unrealized, 2) if mtm_method == 'mark_to_market' else None

            return {
                "success": True,
                "data": {
                    "total_unrealized_pnl": final_unrealized,
                    "total_realized_pnl": round(today_realized, 2),
                    "net_pnl": round(today_realized + (final_unrealized or 0), 2) if final_unrealized is not None else round(today_realized, 2),
                    "positions": positions,
                    "position_count": len(positions),
                    "source": "database",
                    "method": mtm_method,
                    "message": "Live valuation via mark-to-market" if mtm_method == 'mark_to_market' else "MTM unavailable - estimation fallback"
                }
            }
        except Exception as db_err:
            logger.warning(f"Could not read live P&L from database: {db_err}")

        return {
            "success": True,
            "data": {
                "total_unrealized_pnl": None,
                "total_realized_pnl": 0,
                "net_pnl": None,
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
                AND DATE(close_time AT TIME ZONE 'America/Chicago') = %s
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
                    "total_unrealized_pnl": None,
                    "total_realized_pnl": 0,
                    "net_pnl": None,
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
                "total_unrealized_pnl": None,
                "total_realized_pnl": 0,
                "net_pnl": None,
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


@router.post("/reset")
async def reset_ares_data(confirm: bool = False):
    """
    Reset ARES trading data - delete all positions and start fresh.

    Args:
        confirm: Must be True to actually delete data (safety check)

    WARNING: This will permanently delete ALL ARES trading history.
    """
    if not confirm:
        # Get current counts for preview
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM ares_positions")
            total = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM ares_positions WHERE status = 'open'")
            open_count = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM ares_positions WHERE status IN ('closed', 'expired')")
            closed_count = cursor.fetchone()[0]
            conn.close()

            return {
                "success": False,
                "message": "Set confirm=true to reset ARES data. This action cannot be undone.",
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

        # Delete all ARES positions
        cursor.execute("DELETE FROM ares_positions")
        deleted_positions = cursor.rowcount

        # Also delete ARES daily performance
        deleted_performance = 0
        try:
            cursor.execute("DELETE FROM ares_daily_perf")
            deleted_performance = cursor.rowcount
        except Exception:
            pass

        # Also delete ARES scan activity logs
        deleted_scans = 0
        try:
            cursor.execute("DELETE FROM ares_scan_activity")
            deleted_scans = cursor.rowcount
        except Exception:
            pass

        # Reset ARES config to defaults
        deleted_config = 0
        try:
            cursor.execute("DELETE FROM autonomous_config WHERE key LIKE 'ares_%'")
            deleted_config = cursor.rowcount
        except Exception:
            pass

        conn.commit()
        conn.close()

        logger.info(f"ARES reset complete: {deleted_positions} positions, {deleted_performance} performance records, {deleted_scans} scan logs, {deleted_config} config entries deleted")

        return {
            "success": True,
            "message": "ARES data has been reset successfully",
            "deleted": {
                "positions": deleted_positions,
                "daily_performance": deleted_performance,
                "scan_activity": deleted_scans,
                "config_entries": deleted_config
            }
        }
    except Exception as e:
        logger.error(f"Error resetting ARES data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/diagnostics")
async def get_ares_diagnostics():
    """
    Get ARES diagnostic information including execution capability.

    This endpoint checks if ARES can actually execute trades in Tradier sandbox.
    Critical for verifying the bot is properly configured.
    """
    from unified_config import APIConfig

    ares = get_ares_instance()

    # Check environment variables
    sandbox_key_set = bool(APIConfig.TRADIER_SANDBOX_API_KEY)
    sandbox_account_set = bool(APIConfig.TRADIER_SANDBOX_ACCOUNT_ID)
    credentials_configured = sandbox_key_set and sandbox_account_set

    # Check Tradier connectivity
    tradier_balance = _get_tradier_account_balance()
    tradier_connected = tradier_balance.get('connected', False)

    # Get execution status from ARES instance if running
    execution_status = None
    if ares and hasattr(ares, 'executor') and hasattr(ares.executor, 'get_execution_status'):
        execution_status = ares.executor.get_execution_status()

    # Build diagnostic result
    can_execute = False
    issues = []

    if not credentials_configured:
        if not sandbox_key_set:
            issues.append("TRADIER_SANDBOX_API_KEY environment variable not set")
        if not sandbox_account_set:
            issues.append("TRADIER_SANDBOX_ACCOUNT_ID environment variable not set")

    if not tradier_connected:
        issues.append(f"Tradier API not connected: {tradier_balance.get('error', 'Unknown error')}")

    if execution_status:
        if not execution_status.get('can_execute'):
            if execution_status.get('init_error'):
                issues.append(f"Executor init error: {execution_status['init_error']}")
            else:
                issues.append("Executor cannot execute trades (tradier not initialized)")
        else:
            can_execute = True
    elif ares is None:
        issues.append("ARES trader not running in this process - cannot verify execution capability")
        # If credentials are configured and Tradier is connected, likely can execute when running
        if credentials_configured and tradier_connected:
            can_execute = True  # Optimistic - will work when worker starts

    return {
        "success": True,
        "data": {
            "can_execute_trades": can_execute,
            "credentials_configured": credentials_configured,
            "tradier_connected": tradier_connected,
            "tradier_sandbox": tradier_balance.get('sandbox', False),
            "tradier_account_id": tradier_balance.get('account_id'),
            "tradier_balance": tradier_balance.get('total_equity', 0) if tradier_connected else None,
            "ares_running": ares is not None,
            "execution_status": execution_status,
            "issues": issues if issues else None,
            "status": "READY" if can_execute and not issues else "NOT_READY",
            "message": "ARES is ready to execute trades in Tradier sandbox" if can_execute and not issues else f"ARES cannot execute trades: {'; '.join(issues)}"
        }
    }
