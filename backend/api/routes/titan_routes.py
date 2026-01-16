"""
TITAN Aggressive SPX Iron Condor Bot API Routes
=================================================

API endpoints for the TITAN aggressive SPX Iron Condor trading bot.
Trades SPX options with $12 spread widths, multiple times per day.

TITAN is more aggressive than PEGASUS:
- Multiple trades per day (30min cooldown)
- Higher risk per trade (15% vs 10%)
- Lower win probability threshold (40% vs 50%)
- Closer strikes (0.8 SD vs 1.0 SD)
- Faster profit taking (30% vs 50%)
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

router = APIRouter(prefix="/api/titan", tags=["TITAN"])
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
    logger.info("Mark-to-market utility loaded for TITAN")
except ImportError as e:
    logger.debug(f"Mark-to-market import failed: {e}")

# Try to import Tradier for account balance
TradierDataFetcher = None
TRADIER_AVAILABLE = False

try:
    from data.tradier_data_fetcher import TradierDataFetcher
    TRADIER_AVAILABLE = True
    logger.info("TradierDataFetcher loaded for TITAN")
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
            logger.info(f"TradierDataFetcher loaded via direct import for TITAN")
    except Exception as e:
        logger.warning(f"Direct Tradier import failed for TITAN: {e}")


def _resolve_query_param(param, default=None):
    """Resolve a FastAPI Query parameter to its actual value."""
    if param is None:
        return default
    if hasattr(param, 'default'):
        return param.default if param.default is not None else default
    return param


def _calculate_titan_unrealized_pnl(positions: list) -> dict:
    """
    Calculate unrealized P&L for TITAN positions using mark-to-market pricing.

    Fetches real option quotes from Tradier and calculates actual cost to close
    each position. Falls back to estimation if quotes unavailable.

    Args:
        positions: List of position tuples from database query with columns:
                   (position_id, entry_credit, contracts, spread_width,
                    put_short_strike, put_long_strike, call_short_strike, call_long_strike,
                    expiration)

    Returns:
        Dict with total_unrealized_pnl, positions, method, pricing_source
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
        pos_id, entry_credit, contracts, spread_width, put_short, put_long, call_short, call_long, expiration = pos
        entry_credit = float(entry_credit or 0)
        contracts = int(contracts or 1)
        spread_width = float(spread_width or 12)
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
                    entry_credit=entry_credit,
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
            # SPX quotes require Tradier PRODUCTION API - sandbox doesn't have SPX
            try:
                import os
                from data.tradier_data_fetcher import TradierDataFetcher as TDF
                prod_key = os.environ.get('TRADIER_API_KEY')
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
            if put_short < spx_price < call_short:
                put_dist = (spx_price - put_short) / spread_width
                call_dist = (call_short - spx_price) / spread_width
                factor = min(put_dist, call_dist) / 2
                current_value = entry_credit * max(0.1, 0.5 - factor * 0.3)
            elif spx_price <= put_short:
                intrinsic = put_short - spx_price
                current_value = min(spread_width, intrinsic + entry_credit * 0.2)
            else:
                intrinsic = spx_price - call_short
                current_value = min(spread_width, intrinsic + entry_credit * 0.2)

            pos_unrealized = (entry_credit - current_value) * 100 * contracts
            pos_result['unrealized_pnl'] = round(pos_unrealized, 2)
            pos_result['current_value'] = round(current_value, 4)
            pos_result['underlying_price'] = spx_price
            total_unrealized += pos_unrealized

        result['positions'].append(pos_result)

    result['total_unrealized_pnl'] = round(total_unrealized, 2)

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


# Try to import TITAN trader
titan_trader = None
try:
    from trading.titan import TITANTrader, TITANConfig, TradingMode, StrategyPreset
    TITAN_AVAILABLE = True
except ImportError as e:
    TITAN_AVAILABLE = False
    TITANConfig = None
    StrategyPreset = None
    logger.warning(f"TITAN module not available: {e}")


def get_titan_instance():
    """Get the TITAN trader instance from scheduler if available"""
    global titan_trader
    if titan_trader:
        return titan_trader

    try:
        from scheduler.trader_scheduler import get_titan_trader
        titan_trader = get_titan_trader()
        return titan_trader
    except ImportError as e:
        logger.debug(f"Could not import trader_scheduler: {e}")
        return None
    except Exception as e:
        logger.debug(f"Could not get TITAN trader: {e}")
        return None


def _get_tradier_account_balance() -> dict:
    """Get account balance from Tradier API for TITAN."""
    if not TRADIER_AVAILABLE or not TradierDataFetcher:
        return {'connected': False, 'total_equity': 0, 'sandbox': False, 'error': 'TradierDataFetcher not imported'}

    try:
        from unified_config import APIConfig

        api_key = (
            getattr(APIConfig, 'TRADIER_PROD_API_KEY', None) or
            getattr(APIConfig, 'TRADIER_API_KEY', None)
        )
        account_id = (
            getattr(APIConfig, 'TRADIER_PROD_ACCOUNT_ID', None) or
            getattr(APIConfig, 'TRADIER_ACCOUNT_ID', None)
        )

        logger.info(f"TITAN Tradier: mode=PRODUCTION (SPX requires prod)")

        if not api_key or not account_id:
            return {'connected': False, 'total_equity': 0, 'sandbox': False, 'error': 'No credentials configured'}

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
        logger.error(f"TITAN Tradier balance fetch ERROR: {e}")
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
    """Determine if a bot is actually active based on heartbeat status and recency."""
    status = heartbeat.get('status', 'UNKNOWN')

    inactive_statuses = {
        'UNAVAILABLE': 'Trader not initialized',
        'ERROR': 'Encountered an error',
        'KILLED': 'Stopped by kill switch',
        'NEVER_RUN': 'Has never run',
        'UNKNOWN': 'Status unknown'
    }

    if status in inactive_statuses:
        return False, inactive_statuses[status]

    last_scan_iso = heartbeat.get('last_scan_iso')
    if not last_scan_iso:
        return False, 'No heartbeat recorded'

    try:
        last_scan_time = datetime.fromisoformat(last_scan_iso)
        now = datetime.now(last_scan_time.tzinfo)
        age_seconds = (now - last_scan_time).total_seconds()

        max_age_seconds = scan_interval_minutes * 60 * 2
        if age_seconds > max_age_seconds:
            return False, f'Heartbeat stale ({int(age_seconds)}s old, max {max_age_seconds}s)'
    except ValueError as e:
        logger.debug(f"Could not parse heartbeat time format: {e}")
    except Exception as e:
        logger.warning(f"Unexpected error parsing heartbeat time: {e}")

    if status in ('SCAN_COMPLETE', 'TRADED', 'MARKET_CLOSED', 'BEFORE_WINDOW', 'AFTER_WINDOW'):
        return True, f'Running ({status})'

    return True, f'Running ({status})'


@router.get("/status")
async def get_titan_status():
    """
    Get current TITAN bot status.

    Returns mode, capital, P&L, positions, configuration, and heartbeat.
    """
    titan = get_titan_instance()
    heartbeat = _get_heartbeat('TITAN')

    if not titan:
        # TITAN not running - read stats from database
        starting_capital = 200000
        total_pnl = 0
        # IMPORTANT: Don't use stale unrealized_pnl from database when worker isn't running
        # Set to None to indicate live pricing is unavailable
        unrealized_pnl = None
        trade_count = 0
        win_count = 0
        open_count = 0
        closed_count = 0
        trades_today = 0
        today = datetime.now(ZoneInfo("America/Chicago")).strftime('%Y-%m-%d')

        try:
            conn = get_connection()
            cursor = conn.cursor()

            # Note: We intentionally do NOT use unrealized_pnl from database here
            # because it may be stale. Unrealized P&L requires live pricing.
            cursor.execute('''
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 'open' THEN 1 ELSE 0 END) as open_count,
                    SUM(CASE WHEN status IN ('closed', 'expired') THEN 1 ELSE 0 END) as closed_count,
                    SUM(CASE WHEN status IN ('closed', 'expired') AND realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
                    COALESCE(SUM(CASE WHEN status IN ('closed', 'expired') THEN realized_pnl ELSE 0 END), 0) as total_pnl,
                    SUM(CASE WHEN DATE(open_time AT TIME ZONE 'America/Chicago') = %s THEN 1 ELSE 0 END) as trades_today
                FROM titan_positions
            ''', (today,))
            row = cursor.fetchone()
            conn.close()

            if row:
                trade_count = row[0] or 0
                open_count = row[1] or 0
                closed_count = row[2] or 0
                win_count = row[3] or 0
                total_pnl = float(row[4] or 0)
                trades_today = row[5] or 0
        except Exception as db_err:
            logger.debug(f"Could not read TITAN stats from database: {db_err}")

        win_rate = round((win_count / closed_count) * 100, 1) if closed_count > 0 else 0

        tradier_balance = _get_tradier_account_balance()
        tradier_connected = tradier_balance.get('connected', False)

        capital = 200000 + total_pnl
        capital_message = "Paper trading with $200k capital (AGGRESSIVE MODE)"
        if tradier_connected:
            capital_message += " (Tradier connected for live prices)"

        now = datetime.now(ZoneInfo("America/Chicago"))
        current_time_str = now.strftime('%Y-%m-%d %H:%M:%S CT')

        # TITAN trading window: 8:30 AM - 2:45 PM CT (market closes at 3:00 PM CT)
        entry_start = "08:30"
        entry_end = "14:45"  # Stop new entries 15 min before close

        if now.month == 12 and now.day == 24:
            entry_end = "11:50"  # Christmas Eve early close (10 min before 12:00 PM)

        start_parts = entry_start.split(':')
        end_parts = entry_end.split(':')
        start_time = now.replace(hour=int(start_parts[0]), minute=int(start_parts[1]), second=0, microsecond=0)
        end_time = now.replace(hour=int(end_parts[0]), minute=int(end_parts[1]), second=0, microsecond=0)

        is_weekday = now.weekday() < 5
        in_window = is_weekday and start_time <= now <= end_time
        trading_window_status = "OPEN" if in_window else "CLOSED"

        scan_interval = 5
        is_active, active_reason = _is_bot_actually_active(heartbeat, scan_interval)

        # current_equity = starting_capital + realized
        # Only add unrealized if we have live pricing (worker running)
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
                "trades_today": trades_today,
                "win_rate": win_rate,
                "open_positions": open_count,
                "closed_positions": closed_count,
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
                "oracle_available": False,
                "gex_ml_available": False,
                "config": {
                    "risk_per_trade": 15.0,  # TITAN: higher risk
                    "spread_width": 12.0,     # TITAN: wider spreads
                    "sd_multiplier": 0.8,     # TITAN: closer strikes
                    "ticker": "SPX",
                    "profit_target_pct": 30,  # TITAN: faster exit
                    "trade_cooldown_minutes": 30
                },
                "source": "paper",
                "message": capital_message
            }
        }

    now = datetime.now(ZoneInfo("America/Chicago"))
    current_time_str = now.strftime('%Y-%m-%d %H:%M:%S CT')
    entry_start = "08:30"
    entry_end = "14:45"  # Market closes at 3:00 PM CT
    if now.month == 12 and now.day == 24:
        entry_end = "11:50"  # Christmas Eve early close
    start_parts = entry_start.split(':')
    end_parts = entry_end.split(':')
    start_time = now.replace(hour=int(start_parts[0]), minute=int(start_parts[1]), second=0, microsecond=0)
    end_time = now.replace(hour=int(end_parts[0]), minute=int(end_parts[1]), second=0, microsecond=0)
    is_weekday = now.weekday() < 5
    in_window = is_weekday and start_time <= now <= end_time
    trading_window_status = "OPEN" if in_window else "CLOSED"

    try:
        status = titan.get_status()
        scan_interval = 5
        is_active, active_reason = _is_bot_actually_active(heartbeat, scan_interval)
        status['is_active'] = is_active
        status['active_reason'] = active_reason
        status['scan_interval_minutes'] = scan_interval
        status['heartbeat'] = heartbeat
        status['in_trading_window'] = in_window
        status['trading_window_status'] = trading_window_status
        status['trading_window_end'] = entry_end
        status['current_time'] = current_time_str
        if 'capital' not in status:
            status['capital'] = 200000
        if 'capital_source' not in status:
            status['capital_source'] = 'paper'
        if 'total_pnl' not in status:
            status['total_pnl'] = 0
        if 'trade_count' not in status:
            status['trade_count'] = 0
        if 'win_rate' not in status:
            status['win_rate'] = 0

        # Calculate current_equity = starting_capital + realized + unrealized (matches equity curve)
        starting_capital = 200000  # TITAN starting capital
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
        logger.error(f"Error getting TITAN status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/positions")
async def get_titan_positions():
    """
    Get TITAN open and recently closed positions.

    Returns Iron Condor positions with full details.
    """
    titan = get_titan_instance()

    if not titan:
        # TITAN not running - read from database directly
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
                    gex_regime, call_wall, put_wall, flip_point, net_gex,
                    oracle_confidence, oracle_win_probability, oracle_advice,
                    oracle_reasoning, oracle_top_factors,
                    open_time
                FROM titan_positions
                WHERE status = 'open'
                ORDER BY open_time DESC
            ''')
            open_rows = cursor.fetchall()

            # Get closed positions (last 100)
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
                FROM titan_positions
                WHERE status IN ('closed', 'expired')
                ORDER BY close_time DESC
                LIMIT 100
            ''')
            closed_rows = cursor.fetchall()
            conn.close()

            # Format open positions
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
                        pass

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
                })

            # Format closed positions
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
        positions = titan.get_positions()
        open_positions = []
        for pos in positions:
            dte = 0
            if pos.expiration:
                try:
                    exp_date = datetime.strptime(pos.expiration, "%Y-%m-%d").date()
                    today = datetime.now(ZoneInfo("America/Chicago")).date()
                    dte = (exp_date - today).days
                except (ValueError, TypeError, AttributeError):
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
        logger.error(f"Error getting TITAN positions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/equity-curve")
async def get_titan_equity_curve(days: int = 30):
    """
    Get TITAN equity curve data.

    Args:
        days: Number of days of history (default 30)
    """
    starting_capital = 200000
    today = datetime.now(ZoneInfo("America/Chicago")).strftime('%Y-%m-%d')

    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT DATE(close_time AT TIME ZONE 'America/Chicago') as close_date,
                   realized_pnl, position_id
            FROM titan_positions
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


@router.get("/equity-curve/intraday")
async def get_titan_intraday_equity(date: str = None):
    """
    Get TITAN intraday equity curve with 5-minute interval snapshots.

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
            SELECT value FROM autonomous_config WHERE key = 'titan_starting_capital'
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
            FROM titan_equity_snapshots
            WHERE DATE(timestamp AT TIME ZONE 'America/Chicago') = %s
            ORDER BY timestamp ASC
        """, (today,))
        snapshots = cursor.fetchall()

        # Get total realized P&L from closed positions up to today
        cursor.execute("""
            SELECT COALESCE(SUM(realized_pnl), 0)
            FROM titan_positions
            WHERE status IN ('closed', 'expired')
            AND DATE(close_time AT TIME ZONE 'America/Chicago') <= %s
        """, (today,))
        total_realized_row = cursor.fetchone()
        total_realized = float(total_realized_row[0]) if total_realized_row and total_realized_row[0] else 0

        # Get today's closed positions P&L
        cursor.execute("""
            SELECT COALESCE(SUM(realized_pnl), 0), COUNT(*)
            FROM titan_positions
            WHERE status IN ('closed', 'expired')
            AND DATE(close_time AT TIME ZONE 'America/Chicago') = %s
        """, (today,))
        today_row = cursor.fetchone()
        today_realized = float(today_row[0]) if today_row and today_row[0] else 0
        today_closed_count = int(today_row[1]) if today_row and today_row[1] else 0

        # Calculate unrealized P&L from open positions using mark-to-market pricing
        unrealized_pnl = 0
        open_positions = []
        pricing_method = 'estimation'

        try:
            # Query positions with all fields needed for MTM calculation
            cursor.execute("""
                SELECT position_id, entry_credit, contracts, spread_width,
                       put_short_strike, put_long_strike, call_short_strike, call_long_strike,
                       expiration
                FROM titan_positions
                WHERE status = 'open'
            """)
            open_rows = cursor.fetchall()

            if open_rows:
                mtm_result = _calculate_titan_unrealized_pnl(open_rows)
                unrealized_pnl = mtm_result['total_unrealized_pnl']
                open_positions = mtm_result['positions']
                pricing_method = mtm_result['method']
                logger.debug(f"TITAN intraday: unrealized=${unrealized_pnl:.2f} via {pricing_method}")
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

        # Add snapshots
        for snapshot in snapshots:
            ts, balance, snap_unrealized, snap_realized, open_count, note = snapshot
            snap_time = ts.astimezone(CENTRAL_TZ) if ts.tzinfo else ts
            snap_unrealized_val = float(snap_unrealized or 0)
            snap_realized_val = float(snap_realized or 0)
            snap_equity = round(float(balance) if balance else starting_capital, 2)
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
            "bot": "TITAN",
            "data_points": data_points,
            "current_equity": round(current_equity, 2),
            "day_pnl": round(day_pnl, 2),
            "starting_equity": round(starting_capital, 2),
            "high_of_day": round(high_of_day, 2),
            "low_of_day": round(low_of_day, 2),
            "snapshots_count": len(snapshots)
        }

    except Exception as e:
        logger.error(f"Error getting TITAN intraday equity: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e),
            "date": today,
            "bot": "TITAN",
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


@router.post("/equity-snapshot")
async def save_titan_equity_snapshot():
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
            SELECT value FROM autonomous_config WHERE key = 'titan_starting_capital'
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
            FROM titan_positions
            WHERE status IN ('closed', 'expired')
        """)
        row = cursor.fetchone()
        realized_pnl = float(row[0]) if row and row[0] else 0

        # Get open positions and calculate unrealized P&L using mark-to-market
        cursor.execute("""
            SELECT position_id, entry_credit, contracts, spread_width,
                   put_short_strike, put_long_strike, call_short_strike, call_long_strike,
                   expiration
            FROM titan_positions
            WHERE status = 'open'
        """)
        open_positions = cursor.fetchall()
        open_count = len(open_positions)

        # Calculate unrealized P&L using MTM helper
        unrealized_pnl = 0
        pricing_method = 'estimation'

        if open_positions:
            mtm_result = _calculate_titan_unrealized_pnl(open_positions)
            unrealized_pnl = mtm_result['total_unrealized_pnl']
            pricing_method = mtm_result['method']
            logger.debug(f"TITAN snapshot: unrealized=${unrealized_pnl:.2f} via {pricing_method}")

        current_equity = starting_capital + realized_pnl + unrealized_pnl

        # Create table if not exists
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS titan_equity_snapshots (
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
            INSERT INTO titan_equity_snapshots
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
        logger.error(f"Error saving TITAN equity snapshot: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@router.post("/run-cycle")
async def run_titan_cycle(
    request: Request,
    auth: AuthInfo = Depends(require_admin) if AUTH_AVAILABLE and require_admin else None
):
    """
    Manually trigger a TITAN trading cycle.

    PROTECTED: Requires admin authentication.
    """
    titan = get_titan_instance()

    if not titan:
        raise HTTPException(
            status_code=503,
            detail="TITAN not initialized. Wait for scheduled startup."
        )

    try:
        result = titan.run_cycle()

        return {
            "success": True,
            "data": result,
            "message": "TITAN cycle completed"
        }
    except Exception as e:
        logger.error(f"Error running TITAN cycle: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/config")
async def get_titan_config():
    """Get TITAN configuration parameters."""
    titan = get_titan_instance()

    default_config = {
        "ticker": "SPX",
        "spread_width": 12.0,
        "risk_per_trade_pct": 15.0,
        "sd_multiplier": 0.8,
        "min_credit": 0.50,
        "profit_target_pct": 30,
        "use_stop_loss": True,
        "entry_window": "08:30 - 14:45 CT",
        "trade_cooldown_minutes": 30,
        "max_open_positions": 10,
        "min_win_probability": 0.40,
        "description": "TITAN is an aggressive SPX Iron Condor bot with $12 spreads, multiple trades per day."
    }

    if titan and hasattr(titan, 'config'):
        config = titan.config
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
                "trade_cooldown_minutes": config.trade_cooldown_minutes,
                "max_open_positions": config.max_open_positions,
                "min_win_probability": config.min_win_probability,
                "mode": config.mode.value
            }
        }

    return {
        "success": True,
        "data": default_config
    }


@router.post("/force-close")
async def force_close_titan_positions(
    request: Request,
    auth: AuthInfo = Depends(require_admin) if AUTH_AVAILABLE and require_admin else None
):
    """
    Force close all open TITAN positions.

    PROTECTED: Requires admin authentication.
    """
    titan = get_titan_instance()

    if not titan:
        raise HTTPException(
            status_code=503,
            detail="TITAN not initialized."
        )

    try:
        result = titan.force_close_all("MANUAL")

        return {
            "success": True,
            "data": result,
            "message": f"Closed {result.get('closed', 0)} positions"
        }
    except Exception as e:
        logger.error(f"Error force closing TITAN positions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/live-pnl")
async def get_titan_live_pnl():
    """Get real-time unrealized P&L for all open TITAN positions."""
    titan = get_titan_instance()
    today = datetime.now(ZoneInfo("America/Chicago")).strftime('%Y-%m-%d')

    if not titan:
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
                FROM titan_positions
                WHERE status = 'open'
            ''')
            open_rows = cursor.fetchall()

            cursor.execute('''
                SELECT COALESCE(SUM(realized_pnl), 0)
                FROM titan_positions
                WHERE status IN ('closed', 'expired')
                AND DATE(close_time AT TIME ZONE 'America/Chicago') = %s
            ''', (today,))
            realized_row = cursor.fetchone()
            today_realized = float(realized_row[0]) if realized_row else 0
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
                        logger.debug(f"TITAN live-pnl MTM failed for {pos_id}: {e}")

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
            logger.warning(f"Could not read TITAN live P&L from database: {db_err}")

        return {
            "success": True,
            "data": {
                "total_unrealized_pnl": None,
                "total_realized_pnl": 0,
                "net_pnl": None,
                "positions": [],
                "position_count": 0,
                "message": "TITAN not initialized"
            }
        }

    try:
        status = titan.get_status()
        positions = titan.get_positions()

        # unrealized_pnl is None when live pricing unavailable
        unrealized_pnl = status.get('unrealized_pnl')
        has_live_pricing = status.get('has_live_pricing', False)

        # net_pnl = realized + unrealized (but only if unrealized is available)
        net_pnl = unrealized_pnl if unrealized_pnl is not None else None

        return {
            "success": True,
            "data": {
                "total_unrealized_pnl": unrealized_pnl,
                "total_realized_pnl": 0,
                "net_pnl": net_pnl,
                "has_live_pricing": has_live_pricing,
                "positions": [
                    {
                        'position_id': p.position_id,
                        'expiration': p.expiration,
                        'credit_received': p.total_credit * 100 * p.contracts,
                        'contracts': p.contracts,
                        'status': p.status.value,
                        'unrealized_pnl': None  # Individual position P&L requires live pricing
                    }
                    for p in positions
                ],
                "position_count": len(positions),
                "note": "Live pricing available" if has_live_pricing else "Live pricing unavailable - unrealized P&L cannot be calculated"
            }
        }
    except Exception as e:
        logger.error(f"Error getting TITAN live P&L: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/logs")
async def get_titan_logs(
    level: Optional[str] = Query(None, description="Filter by level: DEBUG, INFO, WARNING, ERROR"),
    limit: int = Query(100, description="Max logs to return")
):
    """Get TITAN logs for debugging and monitoring."""
    level = _resolve_query_param(level, None)
    limit = _resolve_query_param(limit, 100)

    try:
        conn = get_connection()
        c = conn.cursor()

        where_clause = "WHERE 1=1"
        params = []
        if level:
            where_clause += " AND level = %s"
            params.append(level)
        params.append(limit)

        c.execute(f"""
            SELECT
                id, log_time, level, message, details
            FROM titan_logs
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
        logger.error(f"Error getting TITAN logs: {e}")
        return {
            "success": True,
            "data": [],
            "count": 0,
            "message": "Log table not available"
        }


@router.get("/performance")
async def get_titan_performance(
    days: int = Query(30, description="Number of days to include")
):
    """Get TITAN performance metrics over time."""
    days = _resolve_query_param(days, 30)

    try:
        conn = get_connection()
        c = conn.cursor()

        c.execute("""
            SELECT
                DATE(close_time AT TIME ZONE 'America/Chicago') as trade_date,
                COUNT(*) as trades_executed,
                SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as trades_won,
                SUM(CASE WHEN realized_pnl <= 0 THEN 1 ELSE 0 END) as trades_lost,
                COALESCE(SUM(realized_pnl), 0) as net_pnl
            FROM titan_positions
            WHERE status IN ('closed', 'expired')
            AND close_time >= CURRENT_DATE - INTERVAL '%s days'
            GROUP BY DATE(close_time AT TIME ZONE 'America/Chicago')
            ORDER BY trade_date DESC
        """, (days,))

        rows = c.fetchall()

        c.execute("""
            SELECT
                COUNT(*) as total_trades,
                SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as total_wins,
                COALESCE(SUM(realized_pnl), 0) as total_pnl
            FROM titan_positions
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
        logger.error(f"Error getting TITAN performance: {e}")
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
async def reset_titan_data(
    request: Request,
    auth: AuthInfo = Depends(require_admin) if AUTH_AVAILABLE and require_admin else None
):
    """Reset all TITAN data (positions, signals, logs)."""
    try:
        conn = get_connection()
        c = conn.cursor()

        # Delete all TITAN data
        c.execute("DELETE FROM titan_positions")
        c.execute("DELETE FROM titan_signals")
        c.execute("DELETE FROM titan_logs")
        c.execute("DELETE FROM titan_daily_perf")

        conn.commit()
        conn.close()

        return {
            "success": True,
            "message": "All TITAN data has been reset"
        }

    except Exception as e:
        logger.error(f"Error resetting TITAN data: {e}")
        raise HTTPException(status_code=500, detail=str(e))
