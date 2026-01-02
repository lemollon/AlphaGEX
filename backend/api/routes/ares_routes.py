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
    except Exception as e:
        logger.debug(f"Could not parse heartbeat time: {e}")
        # If we can't parse, assume it's okay

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

    # ARES trading window: 8:30 AM - 3:30 PM CT (configurable)
    entry_start = "08:30"
    entry_end = "15:30"

    # Check for early close days (typically day before Thanksgiving, Christmas Eve)
    # Dec 24 is typically 1 PM ET = 12 PM CT early close
    # Dec 31 is a NORMAL trading day (closes at 3 PM CT)
    if now.month == 12 and now.day == 24:
        entry_end = "12:00"  # Christmas Eve early close

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

        return {
            "success": True,
            "data": {
                "mode": stored_mode,
                "ticker": stored_ticker,
                "is_spy_sandbox": stored_ticker == "SPY",
                "capital": capital,
                "capital_source": "tradier" if sandbox_connected else "paper_fallback",
                "total_pnl": round(total_pnl, 2),
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
        # Ensure capital fields exist
        if 'capital' not in status:
            status['capital'] = 100000
        if 'total_pnl' not in status:
            status['total_pnl'] = 0
        if 'trade_count' not in status:
            status['trade_count'] = 0
        if 'win_rate' not in status:
            status['win_rate'] = 0
        if 'open_positions' not in status:
            status['open_positions'] = 0

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
            except:
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
                except:
                    pass

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
                except:
                    pass

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
    Get ARES equity curve data.

    Args:
        days: Number of days of history (default 30)

    Returns equity curve built from closed positions.
    """
    ares = get_ares_instance()

    # Get starting capital from Tradier balance when available
    tradier_balance = _get_tradier_account_balance()
    if tradier_balance.get('connected') and tradier_balance.get('total_equity', 0) > 0:
        starting_capital = round(tradier_balance['total_equity'], 2)
    else:
        starting_capital = 100000  # Default fallback

    today = datetime.now(ZoneInfo("America/Chicago")).strftime('%Y-%m-%d')

    if not ares:
        # ARES not running in this process - read from database directly
        try:
            from database_adapter import get_connection
            conn = get_connection()
            cursor = conn.cursor()

            # Get closed positions from database
            # NOTE: Use DATE(close_time) since close_date column doesn't exist
            cursor.execute('''
                SELECT DATE(close_time AT TIME ZONE 'America/Chicago') as close_date,
                       realized_pnl, position_id
                FROM ares_positions
                WHERE status IN ('closed', 'expired')
                AND close_time IS NOT NULL
                ORDER BY close_time ASC
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
    Get ARES equity curve with LIVE intraday tracking from Tradier SANDBOX.

    This endpoint provides real-time equity tracking:
    - Historical data: From closed positions in database
    - Live data: DIRECTLY from Tradier SANDBOX account balance

    The Tradier balance IS the current equity - it reflects all:
    - Realized P&L from closed positions
    - Unrealized P&L from open positions
    - Cash balance

    Returns equity curve with live intraday points.
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

    # Get LIVE data from Tradier SANDBOX - this is the source of truth
    tradier_balance = _get_tradier_account_balance()
    tradier_positions = _get_tradier_positions()

    tradier_connected = tradier_balance.get('connected', False)
    current_equity = tradier_balance.get('total_equity', 0) if tradier_connected else 0
    option_buying_power = tradier_balance.get('option_buying_power', 0) if tradier_connected else 0

    # Get open positions from Tradier for unrealized P&L context
    tradier_open_positions = tradier_positions.get('positions', []) if tradier_positions.get('connected') else []
    tradier_orders = tradier_positions.get('orders', []) if tradier_positions.get('connected') else []

    try:
        from database_adapter import get_connection
        conn = get_connection()
        cursor = conn.cursor()

        # Get or create starting capital record
        # This stores the initial balance when ARES started trading
        cursor.execute('''
            SELECT value FROM autonomous_config
            WHERE key = 'ares_starting_capital'
        ''')
        row = cursor.fetchone()

        if row and float(row[0]) > 0:
            starting_capital = float(row[0])
        else:
            # First time - use current Tradier balance as starting capital
            # Or fallback to 100k if not connected
            starting_capital = current_equity if current_equity > 0 else 100000
            # Store it for future reference
            cursor.execute('''
                INSERT INTO autonomous_config (key, value)
                VALUES ('ares_starting_capital', %s)
                ON CONFLICT (key) DO UPDATE SET value = %s
            ''', (str(starting_capital), str(starting_capital)))
            conn.commit()

        # Get historical closed positions for the equity curve
        cursor.execute('''
            SELECT DATE(close_time AT TIME ZONE 'America/Chicago') as close_date,
                   realized_pnl, position_id, close_time
            FROM ares_positions
            WHERE status IN ('closed', 'expired')
            AND close_time IS NOT NULL
            ORDER BY close_time ASC
        ''')
        historical_rows = cursor.fetchall()

        # Get today's activity
        cursor.execute('''
            SELECT
                COALESCE(SUM(CASE WHEN status IN ('closed', 'expired') THEN realized_pnl ELSE 0 END), 0) as today_realized,
                SUM(CASE WHEN status IN ('closed', 'expired') THEN 1 ELSE 0 END) as today_closed,
                SUM(CASE WHEN status = 'open' THEN 1 ELSE 0 END) as today_open
            FROM ares_positions
            WHERE DATE(open_time AT TIME ZONE 'America/Chicago') = %s
               OR DATE(close_time AT TIME ZONE 'America/Chicago') = %s
        ''', (today, today))
        today_row = cursor.fetchone()
        today_realized = float(today_row[0]) if today_row and today_row[0] else 0
        today_closed_count = int(today_row[1]) if today_row and today_row[1] else 0
        today_open_count = int(today_row[2]) if today_row and today_row[2] else 0

        # Get intraday snapshots if they exist
        cursor.execute('''
            SELECT timestamp, balance, note
            FROM ares_equity_snapshots
            WHERE DATE(timestamp AT TIME ZONE 'America/Chicago') = %s
            ORDER BY timestamp ASC
        ''')
        # This table may not exist yet - handle gracefully
        intraday_snapshots = []
        try:
            intraday_snapshots = cursor.fetchall()
        except Exception:
            pass

        conn.close()

        # Build equity curve
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
        cumulative_pnl = 0

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
                "source": "historical"
            })

        # Add historical points
        for date_str in sorted_dates:
            daily_data = positions_by_date[date_str]
            daily_pnl = daily_data['pnl']
            cumulative_pnl += daily_pnl

            equity_curve.append({
                "date": date_str,
                "time": "15:00:00",
                "equity": round(starting_capital + cumulative_pnl, 2),
                "pnl": round(cumulative_pnl, 2),
                "daily_pnl": round(daily_pnl, 2),
                "trades_closed": daily_data['count'],
                "return_pct": round((cumulative_pnl / starting_capital) * 100, 2) if starting_capital > 0 else 0,
                "is_live": False,
                "source": "historical"
            })

        # Calculate total P&L from Tradier balance
        total_pnl = current_equity - starting_capital if current_equity > 0 else cumulative_pnl
        today_unrealized = total_pnl - cumulative_pnl - today_realized if current_equity > 0 else 0

        # Add TODAY's live points
        if tradier_connected and current_equity > 0:
            # Market open point (start of day = yesterday's close)
            equity_curve.append({
                "date": today,
                "time": "08:30:00",
                "equity": round(starting_capital + cumulative_pnl, 2),
                "pnl": round(cumulative_pnl, 2),
                "daily_pnl": 0,
                "return_pct": round((cumulative_pnl / starting_capital) * 100, 2) if starting_capital > 0 else 0,
                "is_live": False,
                "source": "market_open",
                "label": "Market Open"
            })

            # Add intraday snapshots if available
            for snapshot in intraday_snapshots:
                snap_time, snap_balance, snap_note = snapshot
                snap_pnl = float(snap_balance) - starting_capital
                equity_curve.append({
                    "date": today,
                    "time": snap_time.strftime('%H:%M:%S') if hasattr(snap_time, 'strftime') else str(snap_time),
                    "equity": round(float(snap_balance), 2),
                    "pnl": round(snap_pnl, 2),
                    "daily_pnl": round(snap_pnl - cumulative_pnl, 2),
                    "return_pct": round((snap_pnl / starting_capital) * 100, 2) if starting_capital > 0 else 0,
                    "is_live": False,
                    "source": "snapshot",
                    "note": snap_note
                })

            # LIVE current point from Tradier
            equity_curve.append({
                "date": today,
                "time": current_time,
                "equity": round(current_equity, 2),
                "pnl": round(total_pnl, 2),
                "daily_pnl": round(total_pnl - cumulative_pnl, 2),
                "daily_realized": round(today_realized, 2),
                "daily_unrealized": round(today_unrealized, 2),
                "return_pct": round((total_pnl / starting_capital) * 100, 2) if starting_capital > 0 else 0,
                "is_live": True,
                "source": "tradier_live",
                "label": "LIVE"
            })

        return {
            "success": True,
            "data": {
                "equity_curve": equity_curve,
                "starting_capital": round(starting_capital, 2),
                "current_equity": round(current_equity, 2) if tradier_connected else round(starting_capital + cumulative_pnl, 2),
                "total_pnl": round(total_pnl, 2) if tradier_connected else round(cumulative_pnl, 2),
                "total_return_pct": round((total_pnl / starting_capital) * 100, 2) if starting_capital > 0 and tradier_connected else round((cumulative_pnl / starting_capital) * 100, 2) if starting_capital > 0 else 0,
                "today": {
                    "date": today,
                    "time": current_time,
                    "realized_pnl": round(today_realized, 2),
                    "unrealized_pnl": round(today_unrealized, 2) if tradier_connected else None,
                    "total_pnl": round(total_pnl - cumulative_pnl, 2) if tradier_connected else round(today_realized, 2),
                    "positions_closed": today_closed_count,
                    "positions_open": len(tradier_open_positions),
                    "db_positions_open": today_open_count
                },
                "tradier": {
                    "connected": tradier_connected,
                    "account_id": tradier_balance.get('account_id'),
                    "total_equity": round(current_equity, 2) if tradier_connected else None,
                    "option_buying_power": round(option_buying_power, 2) if tradier_connected else None,
                    "open_positions": len(tradier_open_positions),
                    "recent_orders": len(tradier_orders),
                    "error": tradier_balance.get('error') if not tradier_connected else None
                },
                "is_market_open": is_market_hours,
                "last_updated": now.isoformat()
            }
        }

    except Exception as e:
        logger.error(f"Error getting live equity curve: {e}")
        import traceback
        traceback.print_exc()

        # Fallback with Tradier data if available
        return {
            "success": True,
            "data": {
                "equity_curve": [{
                    "date": today,
                    "time": current_time,
                    "equity": round(current_equity, 2) if tradier_connected else 100000,
                    "pnl": 0,
                    "daily_pnl": 0,
                    "return_pct": 0,
                    "is_live": True,
                    "source": "tradier_live" if tradier_connected else "fallback"
                }],
                "starting_capital": round(current_equity, 2) if tradier_connected else 100000,
                "current_equity": round(current_equity, 2) if tradier_connected else 100000,
                "total_pnl": 0,
                "tradier": {
                    "connected": tradier_connected,
                    "total_equity": round(current_equity, 2) if tradier_connected else None,
                    "error": tradier_balance.get('error') if not tradier_connected else None
                },
                "error": str(e)
            }
        }


@router.post("/equity-snapshot")
async def save_equity_snapshot():
    """
    Save current equity snapshot for intraday tracking.

    Call this periodically (e.g., every 5-15 minutes) during market hours
    to build detailed intraday equity curve.
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

        # Create table if not exists
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ares_equity_snapshots (
                id SERIAL PRIMARY KEY,
                timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
                balance DECIMAL(12, 2) NOT NULL,
                option_buying_power DECIMAL(12, 2),
                open_positions INTEGER,
                note TEXT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        ''')

        # Get open position count from Tradier
        tradier_positions = _get_tradier_positions()
        open_count = len(tradier_positions.get('positions', []))

        # Insert snapshot
        cursor.execute('''
            INSERT INTO ares_equity_snapshots
            (timestamp, balance, option_buying_power, open_positions, note)
            VALUES (%s, %s, %s, %s, %s)
        ''', (
            now,
            current_equity,
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

    # Get starting capital from Tradier balance when available
    tradier_balance = _get_tradier_account_balance()
    if tradier_balance.get('connected') and tradier_balance.get('total_equity', 0) > 0:
        starting_capital = round(tradier_balance['total_equity'], 2)
    else:
        starting_capital = 100000  # Default fallback

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
            cursor.execute("DELETE FROM ares_daily_performance")
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
