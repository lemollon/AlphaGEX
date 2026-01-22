"""
ARGUS (0DTE Gamma Live) API Routes
====================================

API endpoints for the ARGUS real-time 0DTE gamma visualization system.
Provides gamma data, probabilities, alerts, commentary, and historical replay.

ARGUS - Named after the "all-seeing" giant with 100 eyes from Greek mythology.
"""

import logging
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from zoneinfo import ZoneInfo
import json
import time
import httpx

from database_adapter import get_connection

router = APIRouter(prefix="/api/argus", tags=["ARGUS"])
logger = logging.getLogger(__name__)

# ==================== TIMEZONE ====================
# All AlphaGEX timestamps use Texas/Central timezone
CENTRAL_TZ = ZoneInfo("America/Chicago")

def get_central_time() -> datetime:
    """Get current time in Central timezone (Texas)"""
    return datetime.now(CENTRAL_TZ)

def format_central_timestamp() -> str:
    """Get ISO formatted timestamp in Central timezone"""
    return get_central_time().isoformat()

# ==================== CACHING ====================
# Simple in-memory cache with TTL
_cache: Dict[str, Any] = {}
_cache_times: Dict[str, float] = {}
CACHE_TTL_SECONDS = 30  # 30 second cache for gamma data (reduced for more responsive updates)
PRICE_CACHE_TTL = 10    # 10 second cache for prices


def get_cached(key: str, ttl: int = CACHE_TTL_SECONDS) -> Any:
    """Get cached value if not expired"""
    if key in _cache and key in _cache_times:
        if time.time() - _cache_times[key] < ttl:
            return _cache[key]
    return None


def set_cached(key: str, value: Any):
    """Set cache value with current time"""
    _cache[key] = value
    _cache_times[key] = time.time()

# Try to import ARGUS engine
ARGUS_AVAILABLE = False
try:
    from core.argus_engine import get_argus_engine, ArgusEngine
    ARGUS_AVAILABLE = True
except ImportError as e:
    logger.warning(f"ARGUS engine not available: {e}")

# Try to import Tradier data fetcher
TRADIER_AVAILABLE = False
TradierDataFetcher = None  # Define as None first
try:
    from data.tradier_data_fetcher import TradierDataFetcher
    TRADIER_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Tradier data fetcher not available: {e}")


class CommentaryRequest(BaseModel):
    """Request body for generating commentary"""
    force: bool = False


# Initialize ARGUS database tables on module load
# This runs once when the routes module is imported
_tables_initialized = False


# ==================== ROC HISTORY PERSISTENCE ====================
# Persist gamma history to database for ROC calculation continuity

_history_loaded: Dict[str, bool] = {}  # Track if we've loaded history from DB per symbol


def ensure_all_argus_tables():
    """Create all Argus tables if they don't exist"""
    try:
        conn = get_connection()
        if not conn:
            return False
        cursor = conn.cursor()

        # 1. argus_gamma_history - per-strike gamma tracking
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS argus_gamma_history (
                id SERIAL PRIMARY KEY,
                symbol VARCHAR(10) NOT NULL DEFAULT 'SPY',
                strike DECIMAL(10, 2) NOT NULL,
                gamma_value DECIMAL(20, 8) NOT NULL,
                recorded_at TIMESTAMP WITH TIME ZONE NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_argus_gamma_history_strike_time
            ON argus_gamma_history(symbol, strike, recorded_at DESC)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_argus_gamma_history_recorded_at
            ON argus_gamma_history(recorded_at)
        """)

        # 2. argus_snapshots - market structure snapshots
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS argus_snapshots (
                id SERIAL PRIMARY KEY,
                symbol VARCHAR(10) NOT NULL DEFAULT 'SPY',
                expiration_date DATE,
                snapshot_time TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                spot_price DECIMAL(10, 2),
                expected_move DECIMAL(10, 4),
                vix DECIMAL(6, 2),
                total_net_gamma DECIMAL(20, 2),
                gamma_regime VARCHAR(20),
                previous_regime VARCHAR(20),
                regime_flipped BOOLEAN DEFAULT FALSE,
                market_status VARCHAR(20),
                flip_point DECIMAL(10, 2),
                call_wall DECIMAL(10, 2),
                put_wall DECIMAL(10, 2),
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_argus_snapshots_symbol_time
            ON argus_snapshots(symbol, snapshot_time DESC)
        """)

        # 3. argus_alerts - triggered alerts
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS argus_alerts (
                id SERIAL PRIMARY KEY,
                alert_type VARCHAR(50) NOT NULL,
                strike DECIMAL(10, 2),
                message TEXT,
                priority VARCHAR(10) DEFAULT 'MEDIUM',
                spot_price DECIMAL(10, 2),
                old_value DECIMAL(20, 4),
                new_value DECIMAL(20, 4),
                triggered_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                acknowledged BOOLEAN DEFAULT FALSE,
                acknowledged_at TIMESTAMP WITH TIME ZONE
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_argus_alerts_triggered_at
            ON argus_alerts(triggered_at DESC)
        """)

        # 4. argus_danger_zone_logs - danger zone tracking
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS argus_danger_zone_logs (
                id SERIAL PRIMARY KEY,
                detected_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                expiration_date DATE,
                strike DECIMAL(10, 2) NOT NULL,
                danger_type VARCHAR(20) NOT NULL,
                roc_1min DECIMAL(10, 4),
                roc_5min DECIMAL(10, 4),
                spot_price DECIMAL(10, 2),
                distance_from_spot_pct DECIMAL(6, 2),
                is_active BOOLEAN DEFAULT TRUE,
                resolved_at TIMESTAMP WITH TIME ZONE
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_argus_danger_zone_detected_at
            ON argus_danger_zone_logs(detected_at DESC)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_argus_danger_zone_active
            ON argus_danger_zone_logs(is_active, strike)
        """)

        # 5. argus_pin_predictions - pin strike predictions for accuracy tracking
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS argus_pin_predictions (
                id SERIAL PRIMARY KEY,
                symbol VARCHAR(10) NOT NULL DEFAULT 'SPY',
                prediction_date DATE NOT NULL,
                predicted_pin DECIMAL(10, 2) NOT NULL,
                actual_close DECIMAL(10, 2),
                gamma_regime VARCHAR(20),
                vix_at_prediction DECIMAL(6, 2),
                confidence DECIMAL(5, 2),
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_argus_pin_predictions_date
            ON argus_pin_predictions(symbol, prediction_date DESC)
        """)

        # 6. argus_accuracy - ML model accuracy metrics
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS argus_accuracy (
                id SERIAL PRIMARY KEY,
                metric_date DATE NOT NULL,
                direction_accuracy_7d DECIMAL(5, 2),
                direction_accuracy_30d DECIMAL(5, 2),
                magnet_hit_rate_7d DECIMAL(5, 2),
                magnet_hit_rate_30d DECIMAL(5, 2),
                total_predictions INTEGER DEFAULT 0,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_argus_accuracy_date
            ON argus_accuracy(metric_date DESC)
        """)

        conn.commit()
        cursor.close()
        conn.close()
        logger.info("ARGUS: All tables ensured (6 tables)")
        return True
    except Exception as e:
        logger.error(f"Failed to create ARGUS tables: {e}")
        return False


def ensure_gamma_history_table():
    """Create the gamma history table if it doesn't exist (backward compatible wrapper)"""
    return ensure_all_argus_tables()


def persist_gamma_history(engine, symbol: str = "SPY"):
    """
    Persist current gamma history from engine to database.
    Called periodically to ensure ROC data survives restarts.
    """
    if not engine or not engine.history:
        return

    try:
        conn = get_connection()
        if not conn:
            return

        cursor = conn.cursor()
        ensure_gamma_history_table()

        # Get the most recent timestamp we have in DB for this symbol
        cursor.execute("""
            SELECT MAX(recorded_at) FROM argus_gamma_history WHERE symbol = %s
        """, (symbol,))
        row = cursor.fetchone()
        last_db_time = row[0] if row and row[0] else None

        # Insert only new history entries (avoid duplicates)
        inserted = 0
        for strike, history_list in engine.history.items():
            for recorded_time, gamma_value in history_list:
                # Skip if we already have this or older
                if last_db_time:
                    # Handle timezone-aware comparison
                    check_time = recorded_time
                    if check_time.tzinfo is None:
                        check_time = check_time.replace(tzinfo=CENTRAL_TZ)
                    if last_db_time.tzinfo is None:
                        last_db_time = last_db_time.replace(tzinfo=CENTRAL_TZ)
                    if check_time <= last_db_time:
                        continue

                cursor.execute("""
                    INSERT INTO argus_gamma_history (symbol, strike, gamma_value, recorded_at)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT DO NOTHING
                """, (symbol, strike, gamma_value, recorded_time))
                inserted += 1

        conn.commit()
        cursor.close()
        conn.close()

        if inserted > 0:
            logger.debug(f"ARGUS: Persisted {inserted} gamma history entries for {symbol}")
    except Exception as e:
        logger.warning(f"Failed to persist gamma history: {e}")


def load_gamma_history(engine, symbol: str = "SPY"):
    """
    Load gamma history from database into engine.
    Called on engine startup to restore ROC calculation capability.
    """
    global _history_loaded

    if not engine:
        return

    if _history_loaded.get(symbol, False):
        logger.debug(f"ARGUS: Gamma history already loaded for {symbol}, skipping")
        return

    try:
        conn = get_connection()
        if not conn:
            return

        cursor = conn.cursor()
        ensure_gamma_history_table()

        # Load full trading day of history (7 hours = 420 minutes to support all ROC timeframes)
        cursor.execute("""
            SELECT strike, gamma_value, recorded_at
            FROM argus_gamma_history
            WHERE symbol = %s
            AND recorded_at > NOW() - INTERVAL '420 minutes'
            ORDER BY strike, recorded_at ASC
        """, (symbol,))

        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        if not rows:
            logger.debug(f"ARGUS: No recent gamma history found for {symbol}")
            _history_loaded[symbol] = True
            return

        # Populate engine history
        for strike, gamma_value, recorded_at in rows:
            strike_float = float(strike)
            if strike_float not in engine.history:
                engine.history[strike_float] = []

            # Ensure timezone awareness
            if recorded_at.tzinfo is None:
                recorded_at = recorded_at.replace(tzinfo=CENTRAL_TZ)

            engine.history[strike_float].append((recorded_at, float(gamma_value)))

        _history_loaded[symbol] = True
        unique_strikes = len(engine.history)
        total_entries = sum(len(h) for h in engine.history.values())
        logger.info(f"ARGUS: Loaded gamma history for {symbol}: {unique_strikes} strikes, {total_entries} entries")

    except Exception as e:
        logger.warning(f"Failed to load gamma history: {e}")
        _history_loaded[symbol] = True  # Prevent repeated failures


def cleanup_old_gamma_history():
    """
    Clean up gamma history older than 8 hours.
    Called periodically to prevent table bloat.
    Keeps full trading day data for ROC calculations.
    """
    try:
        conn = get_connection()
        if not conn:
            return

        cursor = conn.cursor()
        cursor.execute("""
            DELETE FROM argus_gamma_history
            WHERE recorded_at < NOW() - INTERVAL '8 hours'
        """)
        deleted = cursor.rowcount
        conn.commit()
        cursor.close()
        conn.close()

        if deleted > 0:
            logger.debug(f"ARGUS: Cleaned up {deleted} old gamma history entries")
    except Exception as e:
        logger.warning(f"Failed to cleanup gamma history: {e}")


def get_engine() -> Optional[ArgusEngine]:
    """Get the ARGUS engine instance"""
    global _tables_initialized
    if not ARGUS_AVAILABLE:
        return None
    try:
        # Ensure database tables exist on first call
        if not _tables_initialized:
            ensure_all_argus_tables()
            _tables_initialized = True
        return get_argus_engine()
    except Exception as e:
        logger.error(f"Failed to get ARGUS engine: {e}")
        return None


# Store the last Tradier initialization error for diagnostic purposes
_tradier_init_error: Optional[str] = None
# Cache the Tradier instance to avoid repeated initialization
_tradier_instance: Optional[Any] = None


def get_tradier():
    """
    Get the Tradier data fetcher instance.

    Uses the same pattern as ARES: explicitly gets credentials from APIConfig
    and tries sandbox mode first (for market data), then production.

    This fixes the bug where ARGUS defaulted to production mode but credentials
    might only be configured for sandbox.
    """
    global _tradier_init_error, _tradier_instance

    # Return cached instance if available
    if _tradier_instance is not None:
        return _tradier_instance

    if not TRADIER_AVAILABLE or TradierDataFetcher is None:
        _tradier_init_error = "TradierDataFetcher module not imported - check logs for import errors"
        return None

    try:
        from unified_config import APIConfig

        # Try sandbox credentials first (like ARES does for market data)
        # Sandbox API still provides real market data for quotes/options
        sandbox_key = APIConfig.TRADIER_SANDBOX_API_KEY or APIConfig.TRADIER_API_KEY
        sandbox_account = APIConfig.TRADIER_SANDBOX_ACCOUNT_ID or APIConfig.TRADIER_ACCOUNT_ID

        if sandbox_key and sandbox_account:
            try:
                fetcher = TradierDataFetcher(
                    api_key=sandbox_key,
                    account_id=sandbox_account,
                    sandbox=True
                )
                _tradier_init_error = None
                _tradier_instance = fetcher
                logger.info("ARGUS: Tradier initialized with SANDBOX credentials")
                return fetcher
            except Exception as e:
                logger.warning(f"ARGUS: Sandbox credentials failed: {e}")

        # Try production credentials
        prod_key = APIConfig.TRADIER_PROD_API_KEY or APIConfig.TRADIER_API_KEY
        prod_account = APIConfig.TRADIER_PROD_ACCOUNT_ID or APIConfig.TRADIER_ACCOUNT_ID

        if prod_key and prod_account:
            try:
                fetcher = TradierDataFetcher(
                    api_key=prod_key,
                    account_id=prod_account,
                    sandbox=False
                )
                _tradier_init_error = None
                _tradier_instance = fetcher
                logger.info("ARGUS: Tradier initialized with PRODUCTION credentials")
                return fetcher
            except Exception as e:
                logger.warning(f"ARGUS: Production credentials failed: {e}")

        # No valid credentials found
        _tradier_init_error = "No valid Tradier credentials found in APIConfig (checked TRADIER_SANDBOX_*, TRADIER_PROD_*, and TRADIER_*)"
        logger.error(f"ARGUS: {_tradier_init_error}")
        return None

    except ImportError as e:
        _tradier_init_error = f"Failed to import unified_config: {e}"
        logger.error(f"ARGUS: {_tradier_init_error}")
        return None
    except Exception as e:
        _tradier_init_error = f"Unexpected error: {type(e).__name__}: {e}"
        logger.error(f"ARGUS: Failed to get Tradier fetcher: {e}")
        return None


def get_tradier_status() -> dict:
    """Get the status of Tradier data fetcher for diagnostics"""
    # Check credentials via APIConfig (same source get_tradier uses)
    try:
        from unified_config import APIConfig
        credentials = {
            'TRADIER_API_KEY': bool(APIConfig.TRADIER_API_KEY),
            'TRADIER_ACCOUNT_ID': bool(APIConfig.TRADIER_ACCOUNT_ID),
            'TRADIER_SANDBOX_API_KEY': bool(APIConfig.TRADIER_SANDBOX_API_KEY),
            'TRADIER_SANDBOX_ACCOUNT_ID': bool(APIConfig.TRADIER_SANDBOX_ACCOUNT_ID),
            'TRADIER_PROD_API_KEY': bool(APIConfig.TRADIER_PROD_API_KEY),
            'TRADIER_PROD_ACCOUNT_ID': bool(APIConfig.TRADIER_PROD_ACCOUNT_ID),
        }
        default_sandbox_mode = APIConfig.TRADIER_SANDBOX
    except ImportError:
        import os
        credentials = {
            'TRADIER_API_KEY': bool(os.getenv('TRADIER_API_KEY')),
            'TRADIER_ACCOUNT_ID': bool(os.getenv('TRADIER_ACCOUNT_ID')),
            'TRADIER_SANDBOX_API_KEY': bool(os.getenv('TRADIER_SANDBOX_API_KEY')),
            'TRADIER_SANDBOX_ACCOUNT_ID': bool(os.getenv('TRADIER_SANDBOX_ACCOUNT_ID')),
            'TRADIER_PROD_API_KEY': bool(os.getenv('TRADIER_PROD_API_KEY')),
            'TRADIER_PROD_ACCOUNT_ID': bool(os.getenv('TRADIER_PROD_ACCOUNT_ID')),
        }
        default_sandbox_mode = os.getenv('TRADIER_SANDBOX', 'false').lower() == 'true'

    # Check if any valid credential pair exists
    has_sandbox_creds = credentials['TRADIER_SANDBOX_API_KEY'] and credentials['TRADIER_SANDBOX_ACCOUNT_ID']
    has_prod_creds = credentials['TRADIER_PROD_API_KEY'] and credentials['TRADIER_PROD_ACCOUNT_ID']
    has_generic_creds = credentials['TRADIER_API_KEY'] and credentials['TRADIER_ACCOUNT_ID']
    has_any_creds = has_sandbox_creds or has_prod_creds or has_generic_creds

    # Try to get a tradier instance
    tradier = get_tradier()
    is_connected = tradier is not None
    active_mode = 'SANDBOX' if (tradier and tradier.sandbox) else ('PRODUCTION' if tradier else None)

    return {
        'module_available': TRADIER_AVAILABLE,
        'credentials_configured': credentials,
        'has_valid_credentials': has_any_creds,
        'default_sandbox_mode': default_sandbox_mode,
        'active_mode': active_mode,
        'is_connected': is_connected,
        'last_error': _tradier_init_error if not is_connected else None,
        'status': 'connected' if is_connected else 'disconnected',
        'recommendation': None if is_connected else (
            'Set TRADIER_API_KEY and TRADIER_ACCOUNT_ID environment variables. '
            'For sandbox testing, also set TRADIER_SANDBOX_API_KEY and TRADIER_SANDBOX_ACCOUNT_ID.'
        )
    }


def is_market_hours() -> bool:
    """Check if market is currently open (9:30 AM - 4:00 PM ET / 8:30 AM - 3:00 PM CT)"""
    now = datetime.now(CENTRAL_TZ)
    # Weekend
    if now.weekday() >= 5:
        return False
    # Holiday check
    from trading.market_calendar import MARKET_HOLIDAYS_2024_2025
    date_str = now.strftime('%Y-%m-%d')
    if date_str in MARKET_HOLIDAYS_2024_2025:
        return False
    # Time check (8:30 AM - 3:00 PM CT)
    time_minutes = now.hour * 60 + now.minute
    return 8 * 60 + 30 <= time_minutes < 15 * 60


async def fetch_gamma_data(symbol: str = "SPY", expiration: str = None) -> dict:
    """
    Fetch gamma data from Tradier API with caching.

    Returns processed options chain with gamma data.
    When market is closed, uses longer cache (5 min) to prevent constant refetching.
    """
    # Determine cache TTL based on market hours
    # When market is closed, use longer cache (5 min) - data won't change
    market_open = is_market_hours()
    cache_ttl = CACHE_TTL_SECONDS if market_open else 300  # 30s when open, 5min when closed

    # Check cache first - but skip if cached data is mock (allow retry for live)
    cache_key = f"gamma_data_{symbol}_{expiration or 'today'}"
    cached = get_cached(cache_key, cache_ttl)
    if cached and not cached.get('is_mock', False):
        logger.debug(f"ARGUS: Returning cached data for {expiration or 'today'} (market_open={market_open}, ttl={cache_ttl}s)")
        return cached
    elif cached and cached.get('is_mock', False):
        logger.debug(f"ARGUS: Skipping cached mock data, attempting fresh fetch")

    tradier = get_tradier()
    if not tradier:
        # Get specific error for better diagnostics
        error_detail = _tradier_init_error or 'Unknown initialization error'
        logger.warning(f"ARGUS: Tradier API not available - {error_detail}")
        return {
            'symbol': symbol,
            'spot_price': 0,
            'vix': 0,
            'expiration': expiration or '',
            'strikes': [],
            'data_unavailable': True,
            'reason': 'Data provider unavailable',
            'message': f'Tradier API error: {error_detail}',
            'error_detail': error_detail,
            'fetched_at': format_central_timestamp()
        }

    try:
        # Get quote for symbol (synchronous method)
        quote = tradier.get_quote(symbol)
        spot_price = quote.get('last', 0) or quote.get('close', 0)
        logger.info(f"ARGUS: {symbol} quote fetched, price=${spot_price}")

        # Get VIX - use reliable vix_fetcher (NO FAKE FALLBACKS)
        from data.vix_fetcher import get_vix_price
        vix = get_vix_price()
        logger.info(f"ARGUS: VIX fetched, value={vix}")

        # Get expiration (default to 0DTE)
        engine = get_engine()
        if not expiration and engine:
            expiration = engine.get_0dte_expiration()
        logger.info(f"ARGUS: Using expiration={expiration}")

        # Get options chain (synchronous method, returns OptionChain dataclass)
        option_chain = tradier.get_option_chain(symbol, expiration)

        # OptionChain.chains is Dict[expiration, List[OptionContract]]
        # Get contracts for the requested expiration
        contracts = option_chain.chains.get(expiration, [])
        options_count = len(contracts)
        logger.info(f"ARGUS: Options chain fetched, {options_count} contracts for {expiration}")

        # If no options (market closed/weekend), return unavailable status
        if options_count == 0:
            logger.warning("ARGUS: No options data available (market likely closed)")
            return {
                'symbol': symbol,
                'spot_price': spot_price,
                'vix': vix,
                'expiration': expiration,
                'strikes': [],
                'data_unavailable': True,
                'reason': 'No options data',
                'message': 'Options chain is empty. Market may be closed or no 0DTE expiration available.',
                'fetched_at': format_central_timestamp()
            }

        # Process chain into strike data using O(1) dictionary lookup instead of O(n²) nested loop
        # Build dictionaries keyed by (strike, option_type) for fast lookup
        options_by_key = {}
        for contract in contracts:
            strike = contract.strike
            opt_type = contract.option_type
            if strike and opt_type:
                options_by_key[(strike, opt_type)] = contract

        # Get unique strikes
        unique_strike_values = set(contract.strike for contract in contracts if contract.strike)

        # Build strike data using O(1) lookups
        unique_strikes = {}
        for strike in unique_strike_values:
            call_contract = options_by_key.get((strike, 'call'))
            put_contract = options_by_key.get((strike, 'put'))

            unique_strikes[strike] = {
                'strike': strike,
                'call_gamma': call_contract.gamma if call_contract else 0,
                'put_gamma': put_contract.gamma if put_contract else 0,
                'call_oi': call_contract.open_interest if call_contract else 0,
                'put_oi': put_contract.open_interest if put_contract else 0,
                'call_price': (call_contract.last or call_contract.mid) if call_contract else 0,
                'put_price': (put_contract.last or put_contract.mid) if put_contract else 0,
                'call_iv': call_contract.implied_volatility if call_contract else 0,
                'put_iv': put_contract.implied_volatility if put_contract else 0,
                'volume': (call_contract.volume if call_contract else 0) + (put_contract.volume if put_contract else 0)
            }

        # Record the actual data fetch time
        data_fetch_time = format_central_timestamp()

        result = {
            'symbol': symbol,
            'spot_price': spot_price,
            'vix': vix,
            'expiration': expiration,
            'strikes': list(unique_strikes.values()),
            'is_mock': False,  # Real market data from Tradier
            'fetched_at': data_fetch_time,  # Actual fetch timestamp (Central timezone)
            'data_timestamp': data_fetch_time,  # When Tradier data was actually fetched
            'cache_time': time.time()  # Unix timestamp for cache age calculation
        }

        # Cache the result
        set_cached(cache_key, result)
        return result

    except Exception as e:
        logger.error(f"Error fetching gamma data: {e}")
        return {
            'symbol': symbol,
            'spot_price': 0,
            'vix': 0,
            'expiration': expiration or '',
            'strikes': [],
            'data_unavailable': True,
            'reason': 'Fetch error',
            'message': f'Error fetching gamma data: {str(e)}',
            'fetched_at': format_central_timestamp()
        }


async def get_real_prices() -> tuple:
    """Fetch real SPY and VIX prices - NO FAKE FALLBACKS"""
    cache_key = "real_prices"
    cached = get_cached(cache_key, PRICE_CACHE_TTL)
    if cached:
        return cached

    # Get VIX directly using reliable vix_fetcher
    from data.vix_fetcher import get_vix_price

    # Get SPY from Tradier - use get_tradier() which handles credentials properly
    tradier = get_tradier()
    if not tradier:
        raise ValueError("Tradier not available - check credentials")

    spy_quote = tradier.get_quote('SPY')

    if not spy_quote or not spy_quote.get('last'):
        raise ValueError("Failed to get SPY price from Tradier")

    spot = float(spy_quote['last'])
    vix = get_vix_price()

    result = (spot, vix)
    set_cached(cache_key, result)
    return result


@router.get("/gamma")
async def get_gamma_data(
    symbol: str = Query("SPY", description="Symbol (SPY, SPX, QQQ, IWM, DIA)"),
    expiration: Optional[str] = Query(None, description="Expiration date YYYY-MM-DD"),
    day: Optional[str] = Query(None, description="Day of week: mon, tue, wed, thu, fri")
):
    """
    Get current net gamma data by strike for SPY 0DTE.

    Returns:
    - Net gamma per strike
    - Probabilities
    - Rate of change
    - Magnets, pin, danger zones
    """
    engine = get_engine()
    if not engine:
        raise HTTPException(status_code=503, detail="ARGUS engine not available")

    # Load persisted gamma history from database for ROC continuity
    # This ensures ROC values persist across page navigation and server restarts
    load_gamma_history(engine, symbol)

    try:
        # Determine expiration
        if day:
            expiration = engine.get_0dte_expiration(day)
        elif not expiration:
            expiration = engine.get_0dte_expiration('today')

        # Fetch raw data
        raw_data = await fetch_gamma_data(symbol, expiration)

        # Check if data is unavailable (API error, market closed, etc.)
        if raw_data.get('data_unavailable'):
            logger.warning(f"ARGUS: Data unavailable - {raw_data.get('reason', 'unknown')}")
            return {
                "success": False,
                "data_unavailable": True,
                "reason": raw_data.get('reason', 'Data unavailable'),
                "message": raw_data.get('message', 'Unable to fetch gamma data'),
                "symbol": symbol,
                "expiration_date": expiration,
                "fetched_at": raw_data.get('fetched_at', format_central_timestamp())
            }

        # CRITICAL: Only process through engine if data is FRESH (not cached)
        # Re-processing cached data causes ROC to become 0 because the same gamma values
        # get added to history with new timestamps, making rate of change appear as 0
        cache_time = raw_data.get('cache_time')
        cache_age_seconds = int(time.time() - cache_time) if cache_time else 0
        is_cached = cache_age_seconds > 2  # Data older than 2 seconds is from cache

        # When market is closed, ALWAYS use previous snapshot if available
        # This prevents ROC from constantly recalculating on stale after-hours data
        market_open = is_market_hours()

        if not market_open and engine.previous_snapshot:
            # Market closed - use existing snapshot, don't reprocess
            logger.debug(f"ARGUS: Market closed - using existing snapshot to prevent ROC recalculation")
            snapshot = engine.previous_snapshot
        elif is_cached and engine.previous_snapshot:
            # Use existing snapshot - don't reprocess cached data
            logger.debug(f"ARGUS: Using existing snapshot (cached data, age={cache_age_seconds}s)")
            snapshot = engine.previous_snapshot
        else:
            # Process fresh data through engine
            logger.debug(f"ARGUS: Processing fresh data through engine (market_open={market_open})")
            snapshot = engine.process_options_chain(
                raw_data,
                raw_data['spot_price'],
                raw_data['vix'],
                expiration
            )

        # Filter strikes to expected move ± 5
        filtered_strikes = engine.filter_strikes_by_expected_move(
            snapshot.strikes,
            snapshot.spot_price,
            snapshot.expected_move,
            extra_strikes=5
        )

        # Get expected move change data (pass spot_price to normalize for overnight gaps)
        em_change = await get_expected_move_change(snapshot.expected_move, raw_data['vix'], snapshot.spot_price)

        # Extract flip_point, call_wall, put_wall from snapshot strikes for structure analysis
        current_flip_point = None
        current_call_wall = None
        current_put_wall = None

        if snapshot.strikes:
            # Find flip point (where gamma crosses zero)
            for i, strike in enumerate(snapshot.strikes[:-1]):
                if hasattr(strike, 'net_gamma'):
                    curr_gamma = strike.net_gamma
                    next_strike = snapshot.strikes[i + 1]
                    next_gamma = next_strike.net_gamma if hasattr(next_strike, 'net_gamma') else 0
                    if curr_gamma * next_gamma < 0:  # Sign change
                        # Linear interpolation for more precise flip point
                        if curr_gamma != next_gamma:
                            ratio = abs(curr_gamma) / (abs(curr_gamma) + abs(next_gamma))
                            current_flip_point = strike.strike + ratio * (next_strike.strike - strike.strike)
                        else:
                            current_flip_point = strike.strike
                        break

            # Find call wall (highest gamma above spot) and put wall (highest gamma below spot)
            above_spot = [s for s in snapshot.strikes if hasattr(s, 'strike') and s.strike > snapshot.spot_price]
            below_spot = [s for s in snapshot.strikes if hasattr(s, 'strike') and s.strike < snapshot.spot_price]

            if above_spot:
                call_wall_strike = max(above_spot, key=lambda s: abs(getattr(s, 'net_gamma', 0)))
                current_call_wall = call_wall_strike.strike
            if below_spot:
                put_wall_strike = max(below_spot, key=lambda s: abs(getattr(s, 'net_gamma', 0)))
                current_put_wall = put_wall_strike.strike

        # Get call/put wall gamma for wall strength analysis
        call_wall_gamma = None
        put_wall_gamma = None
        if snapshot.strikes:
            for strike in snapshot.strikes:
                if hasattr(strike, 'strike') and hasattr(strike, 'net_gamma'):
                    if current_call_wall and abs(strike.strike - current_call_wall) < 0.5:
                        call_wall_gamma = strike.net_gamma
                    if current_put_wall and abs(strike.strike - current_put_wall) < 0.5:
                        put_wall_gamma = strike.net_gamma

        # Get open EM from the expected_move_change data
        open_em_value = em_change.get('at_open') if em_change else None

        # Get comprehensive market structure changes (flip point, bounds, width, walls, + new signals)
        market_structure = await get_market_structure_changes(
            current_spot=snapshot.spot_price,
            current_em=snapshot.expected_move,
            current_vix=raw_data['vix'],
            current_flip_point=current_flip_point,
            current_call_wall=current_call_wall,
            current_put_wall=current_put_wall,
            current_net_gex=snapshot.total_net_gamma,
            gamma_regime=snapshot.gamma_regime,
            open_em=open_em_value,
            danger_zones=snapshot.danger_zones,
            call_wall_gamma=call_wall_gamma,
            put_wall_gamma=put_wall_gamma
        )

        # Only persist danger zones and alerts when we process FRESH data
        # This prevents clearing danger zones due to cached data with stale ROC values
        if not is_cached:
            await persist_danger_zones_to_db(snapshot.danger_zones, snapshot.spot_price, expiration)
            if engine:
                await persist_alerts_to_db(engine.get_active_alerts())
                # Persist gamma history for ROC continuity across page navigation/server restarts
                persist_gamma_history(engine, symbol)
                # Periodically clean up old history entries
                cleanup_old_gamma_history()

            # Persist ARGUS snapshot for prior day market structure comparisons
            await persist_argus_snapshot_to_db(
                symbol=symbol,
                expiration_date=expiration,
                spot_price=snapshot.spot_price,
                expected_move=snapshot.expected_move,
                vix=raw_data.get('vix', 0),
                total_net_gamma=snapshot.total_net_gamma,
                gamma_regime=snapshot.gamma_regime,
                previous_regime=getattr(snapshot, 'previous_regime', None),
                regime_flipped=snapshot.regime_flipped,
                market_status=snapshot.market_status
            )

            # Persist pin prediction for accuracy tracking (once per day)
            # Only store if we have a valid pin prediction with meaningful confidence
            if snapshot.likely_pin and snapshot.pin_probability and snapshot.pin_probability > 0.3:
                await persist_pin_prediction_to_db(
                    symbol=symbol,
                    predicted_pin=snapshot.likely_pin,
                    gamma_regime=snapshot.gamma_regime,
                    vix=raw_data.get('vix', 0),
                    confidence=snapshot.pin_probability * 100  # Convert to percentage
                )

        # Build response
        return {
            "success": True,
            "data": {
                "symbol": snapshot.symbol,
                "expiration_date": snapshot.expiration_date,
                "snapshot_time": snapshot.snapshot_time.isoformat(),
                "spot_price": snapshot.spot_price,
                "expected_move": snapshot.expected_move,
                "expected_move_change": em_change,
                "market_structure": market_structure,
                "vix": snapshot.vix,
                "total_net_gamma": snapshot.total_net_gamma,
                "gamma_regime": snapshot.gamma_regime,
                "regime_flipped": snapshot.regime_flipped,
                "market_status": snapshot.market_status,
                "is_mock": raw_data.get('is_mock', False),  # True = simulated, False = real market data
                "is_cached": is_cached,  # True if showing cached data
                "cache_age_seconds": cache_age_seconds,  # How old the cached data is
                "fetched_at": raw_data.get('fetched_at', format_central_timestamp()),  # When data was fetched from Tradier (Central TZ)
                "data_timestamp": raw_data.get('data_timestamp', raw_data.get('fetched_at', format_central_timestamp())),  # Original data fetch time
                "strikes": [s.to_dict() for s in filtered_strikes],
                "magnets": snapshot.magnets,
                "likely_pin": snapshot.likely_pin,
                "pin_probability": snapshot.pin_probability,
                "danger_zones": snapshot.danger_zones,
                "gamma_flips": snapshot.gamma_flips,
                "pinning_status": snapshot.pinning_status
            }
        }

    except Exception as e:
        logger.error(f"Error getting gamma data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Cache for prior day expected move
_em_cache: Dict[str, float] = {}
_em_result_cache: Dict[str, Any] = {}
_em_result_cache_time: Dict[str, float] = {}
EM_CACHE_TTL = 300  # 5 minute cache for expected move change calculations


async def get_expected_move_change(current_em: float, current_vix: float, spot_price: float = None) -> dict:
    """
    Calculate expected move change from prior day.

    IMPORTANT: We compare EM as % of spot (not absolute $) to account for overnight gaps.
    This is essentially comparing implied volatility levels.

    Returns interpretation:
    - DOWN: Bearish (IV contracting)
    - UP: Bullish (IV expanding)
    - FLAT: Range-bound day expected
    - WIDEN: Big move coming (volatility expansion)
    """
    today = date.today().strftime('%Y-%m-%d')
    prior_key = f"em_prior_{today}"

    # Check cache first - DB queries are expensive
    cache_key = f"em_result_{today}_{round(current_em, 2)}_{round(spot_price or 0, 2)}"
    if cache_key in _em_result_cache and cache_key in _em_result_cache_time:
        if time.time() - _em_result_cache_time[cache_key] < EM_CACHE_TTL:
            logger.debug("ARGUS: Returning cached expected move change")
            return _em_result_cache[cache_key]

    # Try to get prior day's close expected move AND spot from database
    prior_em = None
    prior_spot = None
    open_em = None
    open_spot = None

    try:
        conn = get_connection()
        if conn:
            cursor = conn.cursor()

            # Get yesterday's final expected move AND spot price
            cursor.execute("""
                SELECT expected_move, spot_price
                FROM argus_snapshots
                WHERE DATE(snapshot_time) < CURRENT_DATE
                ORDER BY snapshot_time DESC
                LIMIT 1
            """)
            row = cursor.fetchone()
            if row:
                prior_em = float(row[0])
                prior_spot = float(row[1]) if row[1] else None

            # Get today's opening expected move (first reading of the day)
            cursor.execute("""
                SELECT expected_move, spot_price
                FROM argus_snapshots
                WHERE DATE(snapshot_time) = CURRENT_DATE
                ORDER BY snapshot_time ASC
                LIMIT 1
            """)
            row = cursor.fetchone()
            if row:
                open_em = float(row[0])
                open_spot = float(row[1]) if row[1] else None

            cursor.close()
            conn.close()
    except Exception as e:
        logger.warning(f"Could not fetch prior expected move: {e}")

    # Use cached/current values if DB not available
    if prior_em is None:
        prior_em = _em_cache.get(prior_key, current_em)
    if open_em is None:
        open_em = current_em

    # Store current as potential prior for next calculation
    if prior_key not in _em_cache:
        _em_cache[prior_key] = current_em

    # Calculate EM as % of spot (this normalizes for overnight gaps)
    # EM% = (Expected Move / Spot) * 100
    current_em_pct = (current_em / spot_price * 100) if spot_price and spot_price > 0 else 0
    prior_em_pct = (prior_em / prior_spot * 100) if prior_em and prior_spot and prior_spot > 0 else current_em_pct
    open_em_pct = (open_em / open_spot * 100) if open_em and open_spot and open_spot > 0 else current_em_pct

    # Calculate change in EM% (not absolute $ change)
    # This compares IV levels, not affected by spot price gaps
    pct_change_prior = ((current_em_pct - prior_em_pct) / prior_em_pct * 100) if prior_em_pct and prior_em_pct != 0 else 0

    # Also calculate absolute $ change for display
    change_from_prior = current_em - prior_em if prior_em else 0

    # Thresholds for classification
    FLAT_THRESHOLD = 3.0  # Less than 3% IV change = flat
    WIDEN_THRESHOLD = 12.0  # More than 12% IV expansion = widening

    # Use IV-normalized comparison for signal
    pct_change = pct_change_prior

    if abs(pct_change) < FLAT_THRESHOLD:
        signal = "FLAT"
        interpretation = "Expected move unchanged from prior day - anticipate range-bound price action"
        sentiment = "NEUTRAL"
    elif pct_change > WIDEN_THRESHOLD:
        signal = "WIDEN"
        interpretation = f"Expected move widened +{pct_change:.1f}% from prior day - big move likely coming, prepare for breakout"
        sentiment = "VOLATILE"
    elif pct_change > 0:
        signal = "UP"
        interpretation = f"Expected move UP +{pct_change:.1f}% from prior day - bullish signal"
        sentiment = "BULLISH"
    else:
        signal = "DOWN"
        interpretation = f"Expected move DOWN {pct_change:.1f}% from prior day - bearish signal"
        sentiment = "BEARISH"

    result = {
        "current": round(current_em, 2),
        "current_pct": round(current_em_pct, 3),  # EM as % of spot
        "prior_day": round(prior_em, 2) if prior_em else None,
        "prior_day_pct": round(prior_em_pct, 3) if prior_em_pct else None,
        "at_open": round(open_em, 2) if open_em else None,
        "change_dollars": round(change_from_prior, 2),
        "pct_change_prior": round(pct_change_prior, 1),  # % change in IV
        "signal": signal,
        "sentiment": sentiment,
        "interpretation": interpretation
    }

    # Cache the result
    _em_result_cache[cache_key] = result
    _em_result_cache_time[cache_key] = time.time()

    return result


# =============================================================================
# MARKET STRUCTURE CHANGES - Multi-Signal Analysis
# =============================================================================
# Cache for market structure
_structure_cache: Dict[str, Any] = {}
_structure_cache_time: Dict[str, float] = {}
STRUCTURE_CACHE_TTL = 300  # 5 minute cache


async def get_market_structure_changes(
    current_spot: float,
    current_em: float,
    current_vix: float,
    current_flip_point: float = None,
    current_call_wall: float = None,
    current_put_wall: float = None,
    current_net_gex: float = None,
    gamma_regime: str = None,
    open_em: float = None,
    danger_zones: list = None,
    call_wall_gamma: float = None,
    put_wall_gamma: float = None
) -> dict:
    """
    Comprehensive market structure analysis comparing today vs prior day.

    Returns actionable signals for:
    1. Flip Point Movement - Dealer positioning shift
    2. Expected Move Bounds - Market's price expectations
    3. Range Width - Volatility expansion/contraction
    4. Combined Signal - Trading recommendation

    Args:
        current_spot: Current spot price
        current_em: Current expected move (straddle price)
        current_vix: Current VIX level
        current_flip_point: Current gamma flip point (optional, from strikes)
        current_call_wall: Current call wall strike (optional)
        current_put_wall: Current put wall strike (optional)

    Returns:
        Dictionary with multi-signal analysis and trading implications
    """
    today = date.today().strftime('%Y-%m-%d')
    cache_key = f"structure_{today}_{round(current_spot, 2)}_{round(current_em, 2)}"

    # Check cache
    if cache_key in _structure_cache and cache_key in _structure_cache_time:
        if time.time() - _structure_cache_time[cache_key] < STRUCTURE_CACHE_TTL:
            return _structure_cache[cache_key]

    # Calculate current expected move bounds (+/- 1 std)
    current_upper = current_spot + current_em
    current_lower = current_spot - current_em
    current_width = current_em * 2

    # Initialize prior day values
    prior_spot = None
    prior_em = None
    prior_upper = None
    prior_lower = None
    prior_width = None
    prior_flip_point = None
    prior_call_wall = None
    prior_put_wall = None

    try:
        conn = get_connection()
        if conn:
            cursor = conn.cursor()

            # Get yesterday's closing data from argus_snapshots
            cursor.execute("""
                SELECT spot_price, expected_move
                FROM argus_snapshots
                WHERE DATE(snapshot_time) < CURRENT_DATE
                ORDER BY snapshot_time DESC
                LIMIT 1
            """)
            row = cursor.fetchone()
            if row:
                prior_spot = float(row[0])
                prior_em = float(row[1])
                prior_upper = prior_spot + prior_em
                prior_lower = prior_spot - prior_em
                prior_width = prior_em * 2

            # Get yesterday's flip point, call/put walls from gex_history
            cursor.execute("""
                SELECT flip_point, call_wall, put_wall, spot_price
                FROM gex_history
                WHERE symbol = 'SPY'
                AND DATE(timestamp) < CURRENT_DATE
                ORDER BY timestamp DESC
                LIMIT 1
            """)
            row = cursor.fetchone()
            if row:
                prior_flip_point = float(row[0]) if row[0] else None
                prior_call_wall = float(row[1]) if row[1] else None
                prior_put_wall = float(row[2]) if row[2] else None
                # If we didn't get prior_spot from argus_snapshots, use gex_history
                if prior_spot is None and row[3]:
                    prior_spot = float(row[3])

            cursor.close()
            conn.close()
    except Exception as e:
        logger.warning(f"Could not fetch prior day structure: {e}")

    # =========================================================================
    # SIGNAL 1: FLIP POINT MOVEMENT
    # =========================================================================
    flip_signal = {
        "current": round(current_flip_point, 2) if current_flip_point else None,
        "prior": round(prior_flip_point, 2) if prior_flip_point else None,
        "change": None,
        "change_pct": None,
        "direction": "UNKNOWN",
        "implication": "Flip point data not available"
    }

    if current_flip_point and prior_flip_point and prior_flip_point > 0:
        flip_change = current_flip_point - prior_flip_point
        flip_change_pct = (flip_change / prior_flip_point) * 100
        flip_signal["change"] = round(flip_change, 2)
        flip_signal["change_pct"] = round(flip_change_pct, 2)

        # Threshold: $2 or 0.3% move is significant
        if flip_change > 2 or flip_change_pct > 0.3:
            flip_signal["direction"] = "RISING"
            flip_signal["implication"] = "Dealers added call gamma or reduced put gamma. Support level moved UP - bullish repositioning. MMs expect higher prices."
        elif flip_change < -2 or flip_change_pct < -0.3:
            flip_signal["direction"] = "FALLING"
            flip_signal["implication"] = "Dealers added put gamma or reduced call gamma. Resistance moved DOWN - bearish repositioning. MMs expect lower prices."
        else:
            flip_signal["direction"] = "STABLE"
            flip_signal["implication"] = "Dealers haven't significantly repositioned. Yesterday's support/resistance levels remain valid."

    # =========================================================================
    # SIGNAL 2: EXPECTED MOVE BOUNDS SHIFT
    # =========================================================================
    bounds_signal = {
        "current_upper": round(current_upper, 2),
        "current_lower": round(current_lower, 2),
        "prior_upper": round(prior_upper, 2) if prior_upper else None,
        "prior_lower": round(prior_lower, 2) if prior_lower else None,
        "upper_change": None,
        "lower_change": None,
        "direction": "UNKNOWN",
        "implication": "Prior day bounds not available"
    }

    if prior_upper and prior_lower:
        upper_change = current_upper - prior_upper
        lower_change = current_lower - prior_lower
        bounds_signal["upper_change"] = round(upper_change, 2)
        bounds_signal["lower_change"] = round(lower_change, 2)

        # Check if both bounds shifted in same direction (directional bias)
        # Threshold: $0.50 shift is significant
        if upper_change > 0.5 and lower_change > 0.5:
            bounds_signal["direction"] = "SHIFTED_UP"
            bounds_signal["implication"] = f"Both bounds moved UP (upper +${upper_change:.2f}, lower +${lower_change:.2f}). Options market pricing HIGHER prices today. Bullish bias."
        elif upper_change < -0.5 and lower_change < -0.5:
            bounds_signal["direction"] = "SHIFTED_DOWN"
            bounds_signal["implication"] = f"Both bounds moved DOWN (upper ${upper_change:.2f}, lower ${lower_change:.2f}). Options market pricing LOWER prices today. Bearish bias."
        elif abs(upper_change) < 0.5 and abs(lower_change) < 0.5:
            bounds_signal["direction"] = "STABLE"
            bounds_signal["implication"] = "Expected range unchanged from prior day. Market has no new directional conviction."
        else:
            bounds_signal["direction"] = "MIXED"
            bounds_signal["implication"] = f"Bounds moved asymmetrically (upper {upper_change:+.2f}, lower {lower_change:+.2f}). Possible skew shift in options."

    # =========================================================================
    # SIGNAL 3: RANGE WIDTH (VOLATILITY)
    # =========================================================================
    width_signal = {
        "current_width": round(current_width, 2),
        "prior_width": round(prior_width, 2) if prior_width else None,
        "change": None,
        "change_pct": None,
        "direction": "UNKNOWN",
        "implication": "Prior width not available"
    }

    if prior_width and prior_width > 0:
        width_change = current_width - prior_width
        width_change_pct = (width_change / prior_width) * 100
        width_signal["change"] = round(width_change, 2)
        width_signal["change_pct"] = round(width_change_pct, 1)

        # Threshold: 5% width change is significant
        if width_change_pct > 5:
            width_signal["direction"] = "WIDENING"
            width_signal["implication"] = f"Expected range EXPANDED {width_change_pct:.1f}% (+${width_change:.2f}). Bigger move priced in today. Iron Condors riskier - wider strikes needed. Straddles more expensive."
        elif width_change_pct < -5:
            width_signal["direction"] = "NARROWING"
            width_signal["implication"] = f"Expected range CONTRACTED {abs(width_change_pct):.1f}% (${width_change:.2f}). Smaller move expected. Premium selling opportunity - Iron Condors favored. Straddles cheaper."
        else:
            width_signal["direction"] = "STABLE"
            width_signal["implication"] = "Volatility expectations unchanged. Yesterday's position sizing still appropriate."

    # =========================================================================
    # SIGNAL 4: WALLS MOVEMENT
    # =========================================================================
    walls_signal = {
        "current_call_wall": round(current_call_wall, 2) if current_call_wall else None,
        "current_put_wall": round(current_put_wall, 2) if current_put_wall else None,
        "prior_call_wall": round(prior_call_wall, 2) if prior_call_wall else None,
        "prior_put_wall": round(prior_put_wall, 2) if prior_put_wall else None,
        "call_wall_change": None,
        "put_wall_change": None,
        "asymmetry": None,
        "implication": "Wall data not available"
    }

    if current_call_wall and current_put_wall and prior_call_wall and prior_put_wall:
        call_change = current_call_wall - prior_call_wall
        put_change = current_put_wall - prior_put_wall
        walls_signal["call_wall_change"] = round(call_change, 2)
        walls_signal["put_wall_change"] = round(put_change, 2)

        # Calculate asymmetry: which wall is closer to spot?
        call_dist = current_call_wall - current_spot
        put_dist = current_spot - current_put_wall

        if call_dist > 0 and put_dist > 0:
            asymmetry = (call_dist - put_dist) / current_spot * 100
            walls_signal["asymmetry"] = round(asymmetry, 2)

            if asymmetry > 0.3:
                walls_signal["implication"] = f"Put wall closer than call wall (asymmetry {asymmetry:.2f}%). More downside protection in place. Downside moves may find support faster."
            elif asymmetry < -0.3:
                walls_signal["implication"] = f"Call wall closer than put wall (asymmetry {asymmetry:.2f}%). Upside capped more tightly. Upside moves may face resistance."
            else:
                walls_signal["implication"] = "Walls roughly symmetric. Balanced risk profile for Iron Condors."

    # =========================================================================
    # SIGNAL 5: INTRADAY EM CHANGE (Open → Now)
    # =========================================================================
    intraday_signal = {
        "open_em": round(open_em, 2) if open_em else None,
        "current_em": round(current_em, 2),
        "change": None,
        "change_pct": None,
        "direction": "UNKNOWN",
        "implication": "Today's open EM not available"
    }

    if open_em and open_em > 0:
        intraday_change = current_em - open_em
        intraday_change_pct = (intraday_change / open_em) * 100
        intraday_signal["change"] = round(intraday_change, 2)
        intraday_signal["change_pct"] = round(intraday_change_pct, 1)

        # Threshold: 3% intraday change is significant
        if intraday_change_pct > 3:
            intraday_signal["direction"] = "EXPANDING"
            intraday_signal["implication"] = f"Intraday vol EXPANDING +{intraday_change_pct:.1f}%. Breakout developing NOW. Existing ICs at risk, directional plays gaining edge."
        elif intraday_change_pct < -3:
            intraday_signal["direction"] = "CONTRACTING"
            intraday_signal["implication"] = f"Intraday vol CONTRACTING {intraday_change_pct:.1f}%. Morning spike fading. Premium selling window opening, consider new ICs."
        else:
            intraday_signal["direction"] = "STABLE"
            intraday_signal["implication"] = "Intraday vol stable. No significant change from open. Current positions sizing still appropriate."

    # =========================================================================
    # SIGNAL 6: VIX REGIME CONTEXT
    # =========================================================================
    vix_regime_signal = {
        "vix": round(current_vix, 2),
        "regime": "UNKNOWN",
        "implication": "VIX data not available"
    }

    if current_vix:
        if current_vix < 15:
            vix_regime_signal["regime"] = "LOW"
            vix_regime_signal["implication"] = "LOW VIX (<15): Cheap options, small premiums. Directional plays affordable. IC profits will be modest."
            vix_regime_signal["strategy_modifier"] = "Size up on directional, reduce IC allocation"
        elif current_vix < 22:
            vix_regime_signal["regime"] = "NORMAL"
            vix_regime_signal["implication"] = "NORMAL VIX (15-22): Ideal for Iron Condors. Good premium, manageable risk. Standard position sizing."
            vix_regime_signal["strategy_modifier"] = "Standard allocation to both ICs and directional"
        elif current_vix < 28:
            vix_regime_signal["regime"] = "ELEVATED"
            vix_regime_signal["implication"] = "ELEVATED VIX (22-28): Fat premiums but bigger swings. Wider strikes on ICs, directional has edge."
            vix_regime_signal["strategy_modifier"] = "Wider IC strikes, favor directional plays"
        elif current_vix < 35:
            vix_regime_signal["regime"] = "HIGH"
            vix_regime_signal["implication"] = "HIGH VIX (28-35): Crisis conditions. Huge premiums but extreme risk. Reduce size, go directional with trend."
            vix_regime_signal["strategy_modifier"] = "Reduce size 50%, favor directional with trend"
        else:
            vix_regime_signal["regime"] = "EXTREME"
            vix_regime_signal["implication"] = "EXTREME VIX (>35): Panic mode. Skip ICs entirely. Small directional with strict stops only."
            vix_regime_signal["strategy_modifier"] = "Skip ICs, small directional only"

    # =========================================================================
    # SIGNAL 7: GAMMA REGIME ALIGNMENT
    # =========================================================================
    regime_signal = {
        "current_regime": gamma_regime or "UNKNOWN",
        "alignment": "UNKNOWN",
        "implication": "Gamma regime data not available"
    }

    if gamma_regime:
        regime_signal["current_regime"] = gamma_regime

        # Determine alignment with other signals
        if gamma_regime == "POSITIVE":
            regime_signal["alignment"] = "MEAN_REVERSION"
            regime_signal["implication"] = "POSITIVE GAMMA: MMs absorb moves (mean reversion). Breakouts will face resistance. ICs safer, directional breakouts may fail."
            regime_signal["ic_safety"] = "HIGH"
            regime_signal["breakout_reliability"] = "LOW"
        elif gamma_regime == "NEGATIVE":
            regime_signal["alignment"] = "MOMENTUM"
            regime_signal["implication"] = "NEGATIVE GAMMA: MMs amplify moves (momentum). Breakouts accelerate. ICs riskier, directional has strong edge."
            regime_signal["ic_safety"] = "LOW"
            regime_signal["breakout_reliability"] = "HIGH"
        else:
            regime_signal["alignment"] = "NEUTRAL"
            regime_signal["implication"] = "NEUTRAL GAMMA: Balanced market. Standard trading rules apply."
            regime_signal["ic_safety"] = "MEDIUM"
            regime_signal["breakout_reliability"] = "MEDIUM"

    # =========================================================================
    # SIGNAL 8: NET GEX MOMENTUM
    # =========================================================================
    gex_momentum_signal = {
        "current_gex": round(current_net_gex, 2) if current_net_gex else None,
        "prior_gex": None,
        "change": None,
        "change_pct": None,
        "direction": "UNKNOWN",
        "conviction": "UNKNOWN",
        "implication": "Net GEX data not available"
    }

    # Get prior day's net GEX from database
    prior_net_gex = None
    try:
        conn = get_connection()
        if conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT net_gex
                FROM gex_history
                WHERE symbol = 'SPY'
                AND DATE(timestamp) < CURRENT_DATE
                ORDER BY timestamp DESC
                LIMIT 1
            """)
            row = cursor.fetchone()
            if row and row[0]:
                prior_net_gex = float(row[0])
            cursor.close()
            conn.close()
    except Exception as e:
        logger.warning(f"Could not fetch prior net GEX: {e}")

    if current_net_gex is not None and prior_net_gex is not None:
        gex_momentum_signal["prior_gex"] = round(prior_net_gex, 2)
        gex_change = current_net_gex - prior_net_gex

        # Calculate percentage change relative to magnitude
        if abs(prior_net_gex) > 0:
            gex_change_pct = (gex_change / abs(prior_net_gex)) * 100
        else:
            gex_change_pct = 0

        gex_momentum_signal["change"] = round(gex_change, 2)
        gex_momentum_signal["change_pct"] = round(gex_change_pct, 1)

        # Determine direction and conviction
        if gex_change > 0 and current_net_gex > 0:
            gex_momentum_signal["direction"] = "STRENGTHENING_POSITIVE"
            gex_momentum_signal["conviction"] = "STRONG_BULLISH"
            gex_momentum_signal["implication"] = f"Net GEX increasing (+{gex_change_pct:.1f}%) and POSITIVE. Strong bullish conviction. Dealers adding upside hedges."
        elif gex_change < 0 and current_net_gex < 0:
            gex_momentum_signal["direction"] = "STRENGTHENING_NEGATIVE"
            gex_momentum_signal["conviction"] = "STRONG_BEARISH"
            gex_momentum_signal["implication"] = f"Net GEX decreasing ({gex_change_pct:.1f}%) and NEGATIVE. Strong bearish conviction. Dealers adding downside hedges."
        elif gex_change > 0 and current_net_gex < 0:
            gex_momentum_signal["direction"] = "WEAKENING_NEGATIVE"
            gex_momentum_signal["conviction"] = "BEARISH_FADING"
            gex_momentum_signal["implication"] = f"Net GEX rising (+{gex_change_pct:.1f}%) but still NEGATIVE. Bearish conviction weakening. Possible reversal brewing."
        elif gex_change < 0 and current_net_gex > 0:
            gex_momentum_signal["direction"] = "WEAKENING_POSITIVE"
            gex_momentum_signal["conviction"] = "BULLISH_FADING"
            gex_momentum_signal["implication"] = f"Net GEX falling ({gex_change_pct:.1f}%) but still POSITIVE. Bullish conviction weakening. Watch for breakdown."
        else:
            gex_momentum_signal["direction"] = "STABLE"
            gex_momentum_signal["conviction"] = "NEUTRAL"
            gex_momentum_signal["implication"] = "Net GEX stable. No significant change in dealer positioning conviction."

    # =========================================================================
    # SIGNAL 9: WALL BREAK RISK
    # =========================================================================
    wall_break_signal = {
        "call_wall_risk": "UNKNOWN",
        "put_wall_risk": "UNKNOWN",
        "primary_risk": "NONE",
        "implication": "Wall break risk data not available"
    }

    if current_call_wall and current_put_wall and current_spot:
        call_dist_pct = ((current_call_wall - current_spot) / current_spot) * 100
        put_dist_pct = ((current_spot - current_put_wall) / current_spot) * 100

        wall_break_signal["call_distance_pct"] = round(call_dist_pct, 2)
        wall_break_signal["put_distance_pct"] = round(put_dist_pct, 2)

        # Check for danger zones at walls
        call_wall_danger = None
        put_wall_danger = None
        if danger_zones:
            for dz in danger_zones:
                dz_strike = dz.get('strike', 0)
                # Check if danger zone is at or near a wall
                if abs(dz_strike - current_call_wall) < 1:  # Within $1
                    call_wall_danger = dz.get('danger_type')
                if abs(dz_strike - current_put_wall) < 1:
                    put_wall_danger = dz.get('danger_type')

        # Assess call wall break risk
        if call_dist_pct < 0.3:  # Within 0.3%
            if call_wall_danger == "COLLAPSING" or gamma_regime == "NEGATIVE":
                wall_break_signal["call_wall_risk"] = "HIGH"
            else:
                wall_break_signal["call_wall_risk"] = "ELEVATED"
        elif call_dist_pct < 0.7:  # Within 0.7%
            if call_wall_danger == "COLLAPSING":
                wall_break_signal["call_wall_risk"] = "ELEVATED"
            else:
                wall_break_signal["call_wall_risk"] = "MODERATE"
        else:
            wall_break_signal["call_wall_risk"] = "LOW"

        # Assess put wall break risk
        if put_dist_pct < 0.3:  # Within 0.3%
            if put_wall_danger == "COLLAPSING" or gamma_regime == "NEGATIVE":
                wall_break_signal["put_wall_risk"] = "HIGH"
            else:
                wall_break_signal["put_wall_risk"] = "ELEVATED"
        elif put_dist_pct < 0.7:  # Within 0.7%
            if put_wall_danger == "COLLAPSING":
                wall_break_signal["put_wall_risk"] = "ELEVATED"
            else:
                wall_break_signal["put_wall_risk"] = "MODERATE"
        else:
            wall_break_signal["put_wall_risk"] = "LOW"

        # Determine primary risk
        if wall_break_signal["call_wall_risk"] == "HIGH":
            wall_break_signal["primary_risk"] = "CALL_BREAK"
            wall_break_signal["implication"] = f"HIGH call wall break risk! Price {call_dist_pct:.2f}% from call wall. {'Gamma COLLAPSING at wall - weakening resistance.' if call_wall_danger == 'COLLAPSING' else 'Negative gamma regime amplifies breakouts.'}"
        elif wall_break_signal["put_wall_risk"] == "HIGH":
            wall_break_signal["primary_risk"] = "PUT_BREAK"
            wall_break_signal["implication"] = f"HIGH put wall break risk! Price {put_dist_pct:.2f}% from put wall. {'Gamma COLLAPSING at wall - weakening support.' if put_wall_danger == 'COLLAPSING' else 'Negative gamma regime amplifies breakdowns.'}"
        elif wall_break_signal["call_wall_risk"] == "ELEVATED":
            wall_break_signal["primary_risk"] = "CALL_APPROACHING"
            wall_break_signal["implication"] = f"Call wall under pressure. Price {call_dist_pct:.2f}% away. Watch for breakout."
        elif wall_break_signal["put_wall_risk"] == "ELEVATED":
            wall_break_signal["primary_risk"] = "PUT_APPROACHING"
            wall_break_signal["implication"] = f"Put wall under pressure. Price {put_dist_pct:.2f}% away. Watch for breakdown."
        else:
            wall_break_signal["primary_risk"] = "NONE"
            wall_break_signal["implication"] = f"Walls intact. Call {call_dist_pct:.1f}% away, Put {put_dist_pct:.1f}% away. Safe for premium selling within range."

    # =========================================================================
    # COMBINED SIGNAL & TRADING RECOMMENDATION
    # =========================================================================
    combined = _generate_combined_signal(
        flip_signal["direction"],
        bounds_signal["direction"],
        width_signal["direction"],
        current_spot,
        current_flip_point,
        current_call_wall,
        current_put_wall,
        gamma_regime=gamma_regime,
        vix_regime=vix_regime_signal.get("regime"),
        intraday_direction=intraday_signal.get("direction"),
        wall_break_risk=wall_break_signal.get("primary_risk"),
        gex_conviction=gex_momentum_signal.get("conviction")
    )

    result = {
        "flip_point": flip_signal,
        "bounds": bounds_signal,
        "width": width_signal,
        "walls": walls_signal,
        "intraday": intraday_signal,
        "vix_regime": vix_regime_signal,
        "gamma_regime": regime_signal,
        "gex_momentum": gex_momentum_signal,
        "wall_break": wall_break_signal,
        "combined": combined,
        "spot_price": round(current_spot, 2),
        "vix": round(current_vix, 2),
        "timestamp": format_central_timestamp()
    }

    # Cache the result
    _structure_cache[cache_key] = result
    _structure_cache_time[cache_key] = time.time()

    return result


def _generate_combined_signal(
    flip_direction: str,
    bounds_direction: str,
    width_direction: str,
    spot: float,
    flip_point: float = None,
    call_wall: float = None,
    put_wall: float = None,
    gamma_regime: str = None,
    vix_regime: str = None,
    intraday_direction: str = None,
    wall_break_risk: str = None,
    gex_conviction: str = None
) -> dict:
    """
    Generate combined trading signal from individual signals.

    Now considers:
    - Gamma regime (POSITIVE/NEGATIVE) for IC safety
    - VIX regime for sizing
    - Intraday vol direction for timing
    - Wall break risk for warnings
    - GEX conviction for confidence

    Returns actionable recommendation with profit zone and breakout risks.
    """
    signal = "NEUTRAL"
    bias = "NONE"
    confidence = "LOW"
    strategy = ""
    profit_zone = ""
    breakout_risk = ""
    warnings = []

    # Build profit zone description
    if call_wall and put_wall:
        profit_zone = f"Profit zone: ${put_wall:.0f} - ${call_wall:.0f}"
        call_dist = ((call_wall - spot) / spot * 100) if spot > 0 else 0
        put_dist = ((spot - put_wall) / spot * 100) if spot > 0 else 0
        breakout_risk = f"Call wall {call_dist:.1f}% away, Put wall {put_dist:.1f}% away"

    # Determine spot position relative to flip point
    spot_vs_flip = ""
    if flip_point and spot:
        if spot > flip_point:
            spot_vs_flip = "ABOVE_FLIP"
        else:
            spot_vs_flip = "BELOW_FLIP"

    # =========================================================================
    # CONTEXT MODIFIERS - Add warnings based on new signals
    # =========================================================================

    # Gamma regime warnings
    ic_warning = ""
    breakout_warning = ""
    if gamma_regime == "NEGATIVE":
        ic_warning = " WARNING: Negative gamma - ICs riskier, breakouts will accelerate!"
        breakout_warning = " Negative gamma amplifies moves."
    elif gamma_regime == "POSITIVE":
        breakout_warning = " Positive gamma may resist breakout."

    # VIX regime modifiers
    vix_modifier = ""
    if vix_regime == "HIGH" or vix_regime == "EXTREME":
        vix_modifier = f" VIX {vix_regime}: Reduce size 50%!"
        warnings.append(f"VIX {vix_regime} - reduce position size")
    elif vix_regime == "ELEVATED":
        vix_modifier = " VIX ELEVATED: Use wider strikes."
        warnings.append("VIX elevated - widen IC strikes")
    elif vix_regime == "LOW":
        vix_modifier = " VIX LOW: Premiums are thin."

    # Intraday vol modifier
    intraday_modifier = ""
    if intraday_direction == "EXPANDING":
        intraday_modifier = " Vol expanding intraday - breakout in progress!"
        warnings.append("Intraday vol expanding")
    elif intraday_direction == "CONTRACTING":
        intraday_modifier = " Vol contracting intraday - premium selling window."

    # Wall break risk warnings
    if wall_break_risk in ["CALL_BREAK", "PUT_BREAK"]:
        warnings.append(f"HIGH {wall_break_risk.replace('_', ' ')} RISK!")

    # GEX conviction boost
    conviction_boost = False
    if gex_conviction in ["STRONG_BULLISH", "STRONG_BEARISH"]:
        conviction_boost = True

    # =========================================================================
    # SIGNAL LOGIC MATRIX (Enhanced with context)
    # =========================================================================

    # BULLISH SCENARIOS
    if flip_direction == "RISING" and bounds_direction == "SHIFTED_UP":
        if width_direction == "WIDENING":
            signal = "BULLISH_BREAKOUT"
            bias = "BULLISH"
            confidence = "HIGH" if (gamma_regime == "NEGATIVE" or conviction_boost) else "MEDIUM"
            strategy = f"BUY CALL SPREADS or GO LONG. Dealers and options market both bullish.{breakout_warning}{vix_modifier}"
        else:
            signal = "BULLISH_GRIND"
            bias = "BULLISH"
            confidence = "HIGH" if conviction_boost else "MEDIUM"
            strategy = f"SELL PUT SPREADS. Bullish bias with contained volatility.{vix_modifier}"

    # BEARISH SCENARIOS
    elif flip_direction == "FALLING" and bounds_direction == "SHIFTED_DOWN":
        if width_direction == "WIDENING":
            signal = "BEARISH_BREAKOUT"
            bias = "BEARISH"
            confidence = "HIGH" if (gamma_regime == "NEGATIVE" or conviction_boost) else "MEDIUM"
            strategy = f"BUY PUT SPREADS or GO SHORT. Dealers and options market both bearish.{breakout_warning}{vix_modifier}"
        else:
            signal = "BEARISH_GRIND"
            bias = "BEARISH"
            confidence = "HIGH" if conviction_boost else "MEDIUM"
            strategy = f"SELL CALL SPREADS. Bearish bias with contained volatility.{vix_modifier}"

    # PREMIUM SELLING SCENARIOS
    elif width_direction == "NARROWING":
        if gamma_regime == "NEGATIVE":
            # Downgrade IC recommendations in negative gamma
            signal = "SELL_PREMIUM_CAUTION"
            bias = "NEUTRAL"
            confidence = "LOW"
            strategy = f"CAUTION: Vol narrowing but NEGATIVE gamma makes ICs risky. {profit_zone}. Consider smaller size or skip.{ic_warning}"
        elif flip_direction == "STABLE" and bounds_direction in ["STABLE", "MIXED"]:
            signal = "SELL_PREMIUM"
            bias = "NEUTRAL"
            confidence = "HIGH" if gamma_regime == "POSITIVE" else "MEDIUM"
            strategy = f"IRON CONDORS favored. Volatility contracting, no directional conviction. {profit_zone}.{' Positive gamma = safer ICs.' if gamma_regime == 'POSITIVE' else ''}{vix_modifier}"
        elif flip_direction == "RISING":
            signal = "SELL_PREMIUM_BULLISH_TILT"
            bias = "SLIGHT_BULLISH"
            confidence = "MEDIUM"
            strategy = f"IRON CONDORS with PUT SPREAD wider. Dealers slightly bullish. {profit_zone}.{vix_modifier}"
        elif flip_direction == "FALLING":
            signal = "SELL_PREMIUM_BEARISH_TILT"
            bias = "SLIGHT_BEARISH"
            confidence = "MEDIUM"
            strategy = f"IRON CONDORS with CALL SPREAD wider. Dealers slightly bearish. {profit_zone}.{vix_modifier}"

    # VOL EXPANSION WITHOUT DIRECTION
    elif width_direction == "WIDENING" and flip_direction == "STABLE":
        signal = "VOL_EXPANSION_NO_DIRECTION"
        bias = "NONE"
        confidence = "LOW"
        strategy = f"CAUTION - vol expanding but no direction. Wait for clearer signal.{intraday_modifier}{vix_modifier}"

    # DIVERGENCE SCENARIOS (conflicting signals)
    elif flip_direction == "RISING" and bounds_direction == "SHIFTED_DOWN":
        signal = "DIVERGENCE_BULLISH_DEALERS"
        bias = "UNCERTAIN"
        confidence = "LOW"
        strategy = f"MIXED SIGNALS - Dealers bullish but options pricing lower. Possible reversal. Watch for confirmation."

    elif flip_direction == "FALLING" and bounds_direction == "SHIFTED_UP":
        signal = "DIVERGENCE_BEARISH_DEALERS"
        bias = "UNCERTAIN"
        confidence = "LOW"
        strategy = f"MIXED SIGNALS - Dealers bearish but options pricing higher. Possible exhaustion. Watch for confirmation."

    # WALL BREAK IMMINENT - Override other signals
    elif wall_break_risk in ["CALL_BREAK", "PUT_BREAK"]:
        if wall_break_risk == "CALL_BREAK":
            signal = "CALL_WALL_BREAK_IMMINENT"
            bias = "BULLISH"
            confidence = "HIGH" if gamma_regime == "NEGATIVE" else "MEDIUM"
            strategy = f"UPSIDE BREAKOUT IMMINENT! Consider buying calls or closing short call spreads.{breakout_warning}"
        else:
            signal = "PUT_WALL_BREAK_IMMINENT"
            bias = "BEARISH"
            confidence = "HIGH" if gamma_regime == "NEGATIVE" else "MEDIUM"
            strategy = f"DOWNSIDE BREAKDOWN IMMINENT! Consider buying puts or closing short put spreads.{breakout_warning}"

    # DEFAULT: NEUTRAL
    else:
        signal = "NEUTRAL"
        bias = "NONE"
        confidence = "LOW"
        strategy = f"No clear edge. Consider ICs within {profit_zone}.{ic_warning if gamma_regime == 'NEGATIVE' else ''}{vix_modifier}"

    return {
        "signal": signal,
        "bias": bias,
        "confidence": confidence,
        "strategy": strategy,
        "profit_zone": profit_zone,
        "breakout_risk": breakout_risk,
        "spot_position": spot_vs_flip,
        "warnings": warnings,
        "gamma_regime_context": gamma_regime,
        "vix_regime_context": vix_regime
    }


@router.get("/history")
async def get_gamma_history(
    strike: Optional[float] = Query(None, description="Specific strike to get history for"),
    minutes: int = Query(30, description="Minutes of history to return")
):
    """
    Get historical gamma data for the last N minutes.

    Returns gamma values over time for sparkline display.
    """
    engine = get_engine()
    if not engine:
        raise HTTPException(status_code=503, detail="ARGUS engine not available")

    try:
        history_data = {}

        if strike:
            # Get history for specific strike
            strike_history = engine.history.get(strike, [])
            history_data[strike] = [
                {"time": t.isoformat(), "gamma": g}
                for t, g in strike_history
            ]
        else:
            # Get history for all strikes
            for s, hist in engine.history.items():
                history_data[s] = [
                    {"time": t.isoformat(), "gamma": g}
                    for t, g in hist
                ]

        return {
            "success": True,
            "data": {
                "history": history_data,
                "minutes": minutes
            }
        }

    except Exception as e:
        logger.error(f"Error getting gamma history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/probability")
async def get_probability_data():
    """
    Get ML-powered probability per strike.

    Returns hybrid probability (60% ML + 40% gamma-weighted distance).
    """
    engine = get_engine()
    if not engine:
        raise HTTPException(status_code=503, detail="ARGUS engine not available")

    try:
        if not engine.previous_snapshot:
            # No data yet, fetch fresh
            raw_data = await fetch_gamma_data()

            # Check if data is unavailable
            if raw_data.get('data_unavailable'):
                return {
                    "success": False,
                    "data_unavailable": True,
                    "reason": raw_data.get('reason', 'Data unavailable'),
                    "message": raw_data.get('message', 'Unable to fetch gamma data for probability calculation')
                }

            snapshot = engine.process_options_chain(
                raw_data,
                raw_data['spot_price'],
                raw_data['vix'],
                raw_data['expiration']
            )
        else:
            snapshot = engine.previous_snapshot

        probabilities = [
            {
                "strike": s.strike,
                "probability": s.probability,
                "is_magnet": s.is_magnet,
                "is_pin": s.is_pin
            }
            for s in snapshot.strikes
        ]

        # Sort by probability descending
        probabilities.sort(key=lambda x: x['probability'], reverse=True)

        return {
            "success": True,
            "data": {
                "probabilities": probabilities,
                "likely_pin": snapshot.likely_pin,
                "pin_probability": snapshot.pin_probability,
                "model_type": "hybrid_60ml_40distance"
            }
        }

    except Exception as e:
        logger.error(f"Error getting probability data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def persist_alerts_to_db(alerts: list):
    """Persist alerts to database for history tracking"""
    if not alerts:
        return

    try:
        conn = get_connection()
        if not conn:
            return

        cursor = conn.cursor()
        for alert in alerts:
            # Check if this exact alert already exists (avoid duplicates)
            cursor.execute("""
                SELECT id FROM argus_alerts
                WHERE alert_type = %s
                AND COALESCE(strike, 0) = COALESCE(%s, 0)
                AND triggered_at > NOW() - INTERVAL '2 minutes'
                LIMIT 1
            """, (alert.get('alert_type'), alert.get('strike')))

            if cursor.fetchone():
                continue  # Skip duplicate

            cursor.execute("""
                INSERT INTO argus_alerts
                (alert_type, strike, message, priority, spot_price, old_value, new_value, triggered_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                alert.get('alert_type'),
                alert.get('strike'),
                alert.get('message'),
                alert.get('priority'),
                alert.get('spot_price'),
                alert.get('old_value'),
                alert.get('new_value'),
                alert.get('triggered_at')
            ))

        conn.commit()
        cursor.close()
        conn.close()
        logger.debug(f"Persisted {len(alerts)} alerts to database")
    except Exception as e:
        logger.warning(f"Failed to persist alerts: {e}")


async def persist_danger_zones_to_db(danger_zones: list, spot_price: float, expiration: str):
    """Persist danger zones to database for history tracking"""
    try:
        conn = get_connection()
        if not conn:
            return

        cursor = conn.cursor()

        # Get list of currently active strikes (empty list if no danger zones)
        active_strikes = [dz['strike'] for dz in danger_zones] if danger_zones else []

        # Mark old danger zones as resolved if they're no longer in the active list
        # BUT: Keep danger zones active for at least 5 minutes to prevent flapping
        # This ensures users see spikes even after they calm down
        if active_strikes:
            placeholders = ','.join(['%s'] * len(active_strikes))
            cursor.execute(f"""
                UPDATE argus_danger_zone_logs
                SET is_active = FALSE, resolved_at = NOW()
                WHERE is_active = TRUE
                AND strike NOT IN ({placeholders})
                AND detected_at > NOW() - INTERVAL '1 day'
                AND detected_at < NOW() - INTERVAL '5 minutes'
            """, active_strikes)
        else:
            # No active danger zones - mark as resolved (only if older than 5 minutes)
            cursor.execute("""
                UPDATE argus_danger_zone_logs
                SET is_active = FALSE, resolved_at = NOW()
                WHERE is_active = TRUE
                AND detected_at > NOW() - INTERVAL '1 day'
                AND detected_at < NOW() - INTERVAL '5 minutes'
            """)

        # Insert new danger zones
        for dz in (danger_zones or []):
            # Check if this danger zone is already logged and active
            cursor.execute("""
                SELECT id FROM argus_danger_zone_logs
                WHERE strike = %s
                AND danger_type = %s
                AND is_active = TRUE
                AND detected_at > NOW() - INTERVAL '5 minutes'
                LIMIT 1
            """, (dz['strike'], dz['danger_type']))

            if cursor.fetchone():
                continue  # Skip - already logged

            distance_pct = ((dz['strike'] - spot_price) / spot_price * 100) if spot_price else 0

            cursor.execute("""
                INSERT INTO argus_danger_zone_logs
                (detected_at, expiration_date, strike, danger_type, roc_1min, roc_5min, spot_price, distance_from_spot_pct, is_active)
                VALUES (NOW(), %s, %s, %s, %s, %s, %s, %s, TRUE)
            """, (
                expiration,
                dz['strike'],
                dz['danger_type'],
                dz.get('roc_1min', 0),
                dz.get('roc_5min', 0),
                spot_price,
                distance_pct
            ))

        conn.commit()
        cursor.close()
        conn.close()
        count = len(danger_zones) if danger_zones else 0
        logger.debug(f"Danger zone sync: {count} active, resolved inactive ones")
    except Exception as e:
        logger.warning(f"Failed to persist danger zones: {e}")


async def persist_argus_snapshot_to_db(
    symbol: str,
    expiration_date: str,
    spot_price: float,
    expected_move: float,
    vix: float,
    total_net_gamma: float,
    gamma_regime: str,
    previous_regime: str = None,
    regime_flipped: bool = False,
    market_status: str = "open"
):
    """
    Persist ARGUS snapshot to database for prior day comparisons.

    This enables the market structure signals to compare today vs prior day:
    - Flip point movement
    - Expected move bounds shift
    - Range width changes
    - GEX momentum
    """
    try:
        conn = get_connection()
        if not conn:
            logger.warning("No database connection for ARGUS snapshot persistence")
            return

        cursor = conn.cursor()

        # Check if we already have a snapshot for this minute (prevent duplicates)
        cursor.execute("""
            SELECT id FROM argus_snapshots
            WHERE symbol = %s
            AND snapshot_time > NOW() - INTERVAL '1 minute'
            LIMIT 1
        """, (symbol,))

        if cursor.fetchone():
            cursor.close()
            conn.close()
            return  # Already have a recent snapshot

        # Insert new snapshot
        cursor.execute("""
            INSERT INTO argus_snapshots (
                symbol, expiration_date, snapshot_time,
                spot_price, expected_move, vix,
                total_net_gamma, gamma_regime, previous_regime,
                regime_flipped, market_status
            ) VALUES (
                %s, %s, NOW(),
                %s, %s, %s,
                %s, %s, %s,
                %s, %s
            )
        """, (
            symbol,
            expiration_date,
            spot_price,
            expected_move,
            vix,
            total_net_gamma,
            gamma_regime,
            previous_regime,
            regime_flipped,
            market_status
        ))

        conn.commit()
        cursor.close()
        conn.close()

        logger.debug(f"ARGUS snapshot persisted: {symbol} spot=${spot_price:.2f} EM=${expected_move:.2f}")

    except Exception as e:
        logger.warning(f"Failed to persist ARGUS snapshot: {e}")


# ==================== PIN PREDICTION PERSISTENCE ====================
# Store daily pin predictions for accuracy tracking

async def persist_pin_prediction_to_db(
    symbol: str,
    predicted_pin: float,
    gamma_regime: str,
    vix: float,
    confidence: float
):
    """
    Persist ARGUS pin prediction to database for accuracy tracking.

    Only stores ONE prediction per day (the first one made after market open).
    This ensures we track the "morning prediction" accuracy, not constantly
    updating predictions throughout the day.
    """
    try:
        conn = get_connection()
        if not conn:
            logger.warning("No database connection for pin prediction persistence")
            return False

        cursor = conn.cursor()

        # Check if we already have a prediction for today
        cursor.execute("""
            SELECT id FROM argus_pin_predictions
            WHERE symbol = %s
            AND prediction_date = CURRENT_DATE
            LIMIT 1
        """, (symbol,))

        if cursor.fetchone():
            cursor.close()
            conn.close()
            logger.debug(f"Pin prediction already exists for {symbol} today, skipping")
            return False  # Already have today's prediction

        # Insert new prediction
        cursor.execute("""
            INSERT INTO argus_pin_predictions (
                symbol, prediction_date, predicted_pin, gamma_regime, vix_at_prediction, confidence
            ) VALUES (%s, CURRENT_DATE, %s, %s, %s, %s)
        """, (symbol, predicted_pin, gamma_regime, vix, confidence))

        conn.commit()
        cursor.close()
        conn.close()

        logger.info(f"ARGUS pin prediction stored: {symbol} pin=${predicted_pin:.2f} ({confidence:.0f}% confidence)")
        return True

    except Exception as e:
        logger.warning(f"Failed to persist pin prediction: {e}")
        return False


async def update_pin_prediction_with_actual_close(symbol: str = "SPY"):
    """
    Update today's pin prediction with actual closing price.

    Called at end of day (after 3:00 PM CT) to record the actual close
    so we can calculate prediction accuracy.
    """
    try:
        conn = get_connection()
        if not conn:
            logger.warning("No database connection for pin prediction update")
            return False

        # Get today's actual closing price from the last snapshot
        cursor = conn.cursor()
        cursor.execute("""
            SELECT spot_price FROM argus_snapshots
            WHERE symbol = %s
            AND DATE(snapshot_time) = CURRENT_DATE
            ORDER BY snapshot_time DESC
            LIMIT 1
        """, (symbol,))

        row = cursor.fetchone()
        if not row:
            cursor.close()
            conn.close()
            logger.warning(f"No snapshot found for {symbol} today, cannot update actual close")
            return False

        actual_close = float(row[0])

        # Update today's prediction with actual close
        cursor.execute("""
            UPDATE argus_pin_predictions
            SET actual_close = %s
            WHERE symbol = %s
            AND prediction_date = CURRENT_DATE
            AND actual_close IS NULL
        """, (actual_close, symbol))

        updated = cursor.rowcount
        conn.commit()
        cursor.close()
        conn.close()

        if updated > 0:
            logger.info(f"ARGUS pin prediction updated with actual close: {symbol} close=${actual_close:.2f}")
            return True
        else:
            logger.debug(f"No pin prediction to update for {symbol} today (already updated or none exists)")
            return False

    except Exception as e:
        logger.warning(f"Failed to update pin prediction with actual close: {e}")
        return False


async def calculate_and_store_argus_accuracy():
    """
    Calculate and store ARGUS prediction accuracy metrics.

    Calculates:
    - Direction accuracy (7d and 30d): Did we predict the right direction?
    - Magnet hit rate (7d and 30d): Did price reach predicted magnets?
    - Total predictions count

    Called daily after market close to update accuracy metrics.
    """
    try:
        conn = get_connection()
        if not conn:
            logger.warning("No database connection for accuracy calculation")
            return False

        cursor = conn.cursor()

        # Calculate 7-day accuracy
        cursor.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN ABS(predicted_pin - actual_close) / NULLIF(actual_close, 0) * 100 < 1.0 THEN 1 ELSE 0 END) as accurate_1pct
            FROM argus_pin_predictions
            WHERE prediction_date >= CURRENT_DATE - INTERVAL '7 days'
            AND actual_close IS NOT NULL
        """)
        row_7d = cursor.fetchone()
        total_7d = row_7d[0] or 0
        accurate_7d = row_7d[1] or 0
        accuracy_7d = round(accurate_7d / total_7d * 100, 2) if total_7d > 0 else None

        # Calculate 30-day accuracy
        cursor.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN ABS(predicted_pin - actual_close) / NULLIF(actual_close, 0) * 100 < 1.0 THEN 1 ELSE 0 END) as accurate_1pct
            FROM argus_pin_predictions
            WHERE prediction_date >= CURRENT_DATE - INTERVAL '30 days'
            AND actual_close IS NOT NULL
        """)
        row_30d = cursor.fetchone()
        total_30d = row_30d[0] or 0
        accurate_30d = row_30d[1] or 0
        accuracy_30d = round(accurate_30d / total_30d * 100, 2) if total_30d > 0 else None

        # Calculate magnet hit rate (using snapshots - did price reach within 0.5% of a magnet?)
        # For now, use pin accuracy as proxy for magnet hit rate
        magnet_7d = accuracy_7d
        magnet_30d = accuracy_30d

        # Delete existing accuracy record for today (if any)
        cursor.execute("""
            DELETE FROM argus_accuracy WHERE metric_date = CURRENT_DATE
        """)

        # Insert new accuracy record
        cursor.execute("""
            INSERT INTO argus_accuracy (
                metric_date, direction_accuracy_7d, direction_accuracy_30d,
                magnet_hit_rate_7d, magnet_hit_rate_30d, total_predictions
            ) VALUES (CURRENT_DATE, %s, %s, %s, %s, %s)
        """, (accuracy_7d, accuracy_30d, magnet_7d, magnet_30d, total_30d))

        conn.commit()
        cursor.close()
        conn.close()

        logger.info(f"ARGUS accuracy metrics stored: 7d={accuracy_7d}%, 30d={accuracy_30d}%, total={total_30d}")
        return True

    except Exception as e:
        logger.warning(f"Failed to calculate/store ARGUS accuracy: {e}")
        return False


@router.post("/eod-processing")
async def run_argus_eod_processing(symbol: str = Query(default="SPY")):
    """
    Run ARGUS end-of-day processing.

    Called by scheduler after market close (3:01 PM CT) to:
    1. Update today's pin prediction with actual closing price
    2. Calculate and store accuracy metrics

    This endpoint enables the prediction accuracy tracking to work end-to-end.
    """
    try:
        results = {
            "symbol": symbol,
            "timestamp": format_central_timestamp(),
            "actions": []
        }

        # 1. Update pin prediction with actual close
        updated = await update_pin_prediction_with_actual_close(symbol)
        results["actions"].append({
            "action": "update_pin_prediction",
            "success": updated,
            "description": "Updated today's pin prediction with actual closing price"
        })

        # 2. Calculate and store accuracy metrics
        accuracy_stored = await calculate_and_store_argus_accuracy()
        results["actions"].append({
            "action": "calculate_accuracy",
            "success": accuracy_stored,
            "description": "Calculated and stored ARGUS prediction accuracy metrics"
        })

        success = updated or accuracy_stored
        return {
            "success": success,
            "data": results
        }

    except Exception as e:
        logger.error(f"Error in ARGUS EOD processing: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/alerts")
async def get_alerts():
    """
    Get alerts with history from database.

    Returns alerts from database (persisted) sorted by priority and time.
    """
    try:
        # First get any new alerts from engine
        engine = get_engine()
        if engine:
            new_alerts = engine.get_active_alerts()
            # Persist new alerts to database
            await persist_alerts_to_db(new_alerts)

        # Now fetch from database (includes history)
        conn = get_connection()
        if not conn:
            # Fallback to in-memory alerts
            if engine:
                alerts = engine.get_active_alerts()
                priority_order = {'HIGH': 0, 'MEDIUM': 1, 'LOW': 2}
                alerts.sort(key=lambda a: (priority_order.get(a['priority'], 3), a['triggered_at']), reverse=False)
                return {"success": True, "data": {"alerts": alerts, "count": len(alerts)}}
            return {"success": True, "data": {"alerts": [], "count": 0}}

        cursor = conn.cursor()

        # Get alerts from the last 24 hours
        cursor.execute("""
            SELECT
                alert_type, strike, message, priority, spot_price,
                old_value, new_value, triggered_at, acknowledged
            FROM argus_alerts
            WHERE triggered_at > NOW() - INTERVAL '24 hours'
            ORDER BY
                CASE priority WHEN 'HIGH' THEN 1 WHEN 'MEDIUM' THEN 2 ELSE 3 END,
                triggered_at DESC
            LIMIT 50
        """)

        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        alerts = []
        for row in rows:
            alerts.append({
                'alert_type': row[0],
                'strike': float(row[1]) if row[1] else None,
                'message': row[2],
                'priority': row[3],
                'spot_price': float(row[4]) if row[4] else None,
                'old_value': row[5],
                'new_value': row[6],
                'triggered_at': row[7].isoformat() if row[7] else None,
                'acknowledged': row[8]
            })

        return {
            "success": True,
            "data": {
                "alerts": alerts,
                "count": len(alerts)
            }
        }

    except Exception as e:
        logger.error(f"Error getting alerts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/danger-zones/log")
async def get_danger_zone_logs():
    """
    Get danger zone history logs.

    Returns recent danger zone events with timestamps.
    """
    try:
        conn = get_connection()
        if not conn:
            return {
                "success": True,
                "data": {
                    "logs": [],
                    "message": "Database not connected"
                }
            }

        cursor = conn.cursor()

        # Get danger zone logs from the last 24 hours
        cursor.execute("""
            SELECT
                id, detected_at, strike, danger_type, roc_1min, roc_5min,
                spot_price, distance_from_spot_pct, is_active, resolved_at
            FROM argus_danger_zone_logs
            WHERE detected_at > NOW() - INTERVAL '24 hours'
            ORDER BY detected_at DESC
            LIMIT 100
        """)

        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        logs = []
        for row in rows:
            logs.append({
                'id': row[0],
                'detected_at': row[1].isoformat() if row[1] else None,
                'strike': float(row[2]) if row[2] else None,
                'danger_type': row[3],
                'roc_1min': float(row[4]) if row[4] else 0,
                'roc_5min': float(row[5]) if row[5] else 0,
                'spot_price': float(row[6]) if row[6] else None,
                'distance_from_spot_pct': float(row[7]) if row[7] else 0,
                'is_active': row[8],
                'resolved_at': row[9].isoformat() if row[9] else None
            })

        return {
            "success": True,
            "data": {
                "logs": logs,
                "count": len(logs)
            }
        }

    except Exception as e:
        logger.error(f"Error getting danger zone logs: {e}")
        return {
            "success": True,
            "data": {
                "logs": [],
                "message": f"Error: {str(e)}"
            }
        }


@router.get("/commentary")
async def get_commentary():
    """
    Get latest Claude AI commentary.

    Returns the most recent AI-generated market commentary.
    """
    try:
        conn = get_connection()
        if not conn:
            return {
                "success": True,
                "data": {
                    "commentary": [],
                    "message": "Database not connected"
                }
            }

        cursor = conn.cursor()

        # Get latest commentary entries
        cursor.execute("""
            SELECT
                id,
                commentary_text,
                spot_price,
                top_magnet,
                likely_pin,
                pin_probability,
                danger_zones,
                vix,
                created_at
            FROM argus_commentary
            ORDER BY created_at DESC
            LIMIT 10
        """)

        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        commentary = []
        for row in rows:
            commentary.append({
                "id": row[0],
                "text": row[1],
                "spot_price": float(row[2]) if row[2] else None,
                "top_magnet": float(row[3]) if row[3] else None,
                "likely_pin": float(row[4]) if row[4] else None,
                "pin_probability": float(row[5]) if row[5] else None,
                "danger_zones": row[6] if row[6] else [],
                "vix": float(row[7]) if row[7] else None,
                "timestamp": row[8].isoformat() if row[8] else None
            })

        return {
            "success": True,
            "data": {
                "commentary": commentary
            }
        }

    except Exception as e:
        logger.error(f"Error getting commentary: {e}")
        # Return empty commentary if table doesn't exist yet
        return {
            "success": True,
            "data": {
                "commentary": [],
                "message": "No commentary available yet"
            }
        }


@router.post("/commentary/generate")
async def generate_commentary(request: CommentaryRequest = None):
    """
    Trigger generation of new Claude AI commentary.

    This is called every 5 minutes by the scheduler or manually.
    """
    engine = get_engine()
    if not engine:
        raise HTTPException(status_code=503, detail="ARGUS engine not available")

    try:
        # Get current snapshot
        if not engine.previous_snapshot:
            raw_data = await fetch_gamma_data()

            # Check if data is unavailable
            if raw_data.get('data_unavailable'):
                return {
                    "success": False,
                    "data_unavailable": True,
                    "reason": raw_data.get('reason', 'Data unavailable'),
                    "message": raw_data.get('message', 'Unable to fetch gamma data for commentary generation')
                }

            snapshot = engine.process_options_chain(
                raw_data,
                raw_data['spot_price'],
                raw_data['vix'],
                raw_data['expiration']
            )
        else:
            snapshot = engine.previous_snapshot

        # Generate commentary using Claude
        try:
            from core.argus_commentary import generate_argus_commentary
            commentary = await generate_argus_commentary(snapshot)
        except ImportError:
            # Fallback if commentary module not ready
            commentary = generate_fallback_commentary(snapshot)

        # Store in database
        try:
            conn = get_connection()
            if conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO argus_commentary
                    (commentary_text, spot_price, top_magnet, likely_pin,
                     pin_probability, danger_zones, vix)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (
                    commentary,
                    snapshot.spot_price,
                    snapshot.magnets[0]['strike'] if snapshot.magnets else None,
                    snapshot.likely_pin,
                    snapshot.pin_probability,
                    json.dumps(snapshot.danger_zones),
                    snapshot.vix
                ))
                conn.commit()
                cursor.close()
                conn.close()
        except Exception as db_error:
            logger.warning(f"Could not store commentary in DB: {db_error}")

        return {
            "success": True,
            "data": {
                "commentary": commentary,
                "generated_at": format_central_timestamp()
            }
        }

    except Exception as e:
        logger.error(f"Error generating commentary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def generate_fallback_commentary(snapshot) -> str:
    """Generate basic commentary without Claude API"""
    now = datetime.now(ZoneInfo("America/New_York"))
    time_str = now.strftime("%I:%M %p ET")

    # Build commentary
    lines = [f"🕐 {time_str} - 5-Minute Update", ""]

    # Gamma structure
    if snapshot.magnets:
        top_magnets = ", ".join([f"{m['strike']} ({m['probability']:.0f}%)"
                                 for m in snapshot.magnets[:3]])
        lines.append(f"📊 GAMMA STRUCTURE: Top magnets at {top_magnets}")
    else:
        lines.append(f"📊 GAMMA STRUCTURE: Net gamma is {snapshot.gamma_regime.lower()}")

    # Regime change
    if snapshot.regime_flipped:
        lines.append(f"⚡ REGIME CHANGE: Flipped from {snapshot.previous_regime} to {snapshot.gamma_regime}")

    # Gamma flips
    if snapshot.gamma_flips:
        flip_strikes = ", ".join([str(f['strike']) for f in snapshot.gamma_flips[:3]])
        lines.append(f"🔄 GAMMA FLIPS: Strikes {flip_strikes} changed sign")

    # Pin prediction
    if snapshot.likely_pin:
        lines.append(f"🎯 PIN PREDICTION: {snapshot.likely_pin} strike "
                    f"({snapshot.pin_probability:.0f}% probability)")

    # Danger zones
    if snapshot.danger_zones:
        dz_list = ", ".join([f"{d['strike']} ({d['danger_type']})"
                            for d in snapshot.danger_zones[:3]])
        lines.append(f"⚠️ DANGER ZONES: {dz_list}")

    # Market context
    lines.append(f"📈 CONTEXT: SPY ${snapshot.spot_price:.2f}, "
                f"VIX {snapshot.vix:.1f}, Expected move ±${snapshot.expected_move:.2f}")

    return "\n".join(lines)


@router.get("/bots")
async def get_bot_positions():
    """
    Get active bot positions for ARGUS context.

    Shows what ARES, ATHENA, TITAN, ICARUS, PEGASUS are doing relative to gamma structure.

    Returns BotPosition interface matching frontend:
    - bot: string (ARES, ATHENA, TITAN, etc.)
    - strategy: string (Iron Condor, Directional Spread, etc.)
    - status: string (open, watching, closed)
    - strikes: string (format: "590/610" for IC, "595" for directional)
    - direction: string (BULLISH, BEARISH, NEUTRAL)
    - pnl: number (unrealized P&L for open, realized for closed)
    - safe: boolean (position within gamma walls)
    """
    try:
        positions = []

        # Check ARES positions (Iron Condors - always NEUTRAL direction)
        try:
            from backend.api.routes.ares_routes import get_ares_positions
            ares_data = await get_ares_positions()
            if ares_data.get('success') and ares_data.get('data', {}).get('positions'):
                for pos in ares_data['data']['positions']:
                    # Calculate P&L: For open ICs, estimate based on credit received
                    # Real P&L would require current option prices
                    pnl = pos.get('realized_pnl') or pos.get('max_profit', 0) * 0.3  # Estimate 30% of max for open
                    positions.append({
                        'bot': 'ARES',
                        'strategy': 'Iron Condor',
                        'status': pos.get('status', 'open'),
                        'strikes': f"{pos.get('put_short_strike', 0):.0f}/{pos.get('call_short_strike', 0):.0f}",
                        'direction': 'NEUTRAL',  # Iron Condors are non-directional
                        'pnl': round(float(pnl), 2) if pnl else 0,
                        'safe': True  # Will be calculated based on magnets
                    })
        except Exception as e:
            logger.debug(f"Could not fetch ARES positions: {e}")

        # Check ATHENA positions (Directional spreads)
        try:
            from backend.api.routes.athena_routes import get_athena_positions
            athena_data = await get_athena_positions()
            if athena_data.get('success') and athena_data.get('data', {}).get('positions'):
                for pos in athena_data['data']['positions']:
                    # Determine direction from spread type or explicit field
                    direction = pos.get('direction', 'NEUTRAL')
                    if not direction or direction == 'NEUTRAL':
                        # Infer from strategy name
                        strategy = pos.get('strategy', '').upper()
                        if 'CALL' in strategy or 'BULL' in strategy:
                            direction = 'BULLISH'
                        elif 'PUT' in strategy or 'BEAR' in strategy:
                            direction = 'BEARISH'
                        else:
                            direction = 'NEUTRAL'

                    pnl = pos.get('realized_pnl') or pos.get('unrealized_pnl', 0)
                    positions.append({
                        'bot': 'ATHENA',
                        'strategy': pos.get('strategy', 'Directional Spread'),
                        'status': pos.get('status', 'open'),
                        'strikes': str(pos.get('strike', pos.get('short_strike', 'N/A'))),
                        'direction': direction,
                        'pnl': round(float(pnl), 2) if pnl else 0,
                        'safe': True
                    })
        except Exception as e:
            logger.debug(f"Could not fetch ATHENA positions: {e}")

        # Check TITAN positions (Aggressive Iron Condors on SPX)
        try:
            from backend.api.routes.titan_routes import get_titan_positions
            titan_data = await get_titan_positions()
            if titan_data.get('success') and titan_data.get('data', {}).get('positions'):
                for pos in titan_data['data']['positions']:
                    pnl = pos.get('realized_pnl') or pos.get('unrealized_pnl', 0)
                    positions.append({
                        'bot': 'TITAN',
                        'strategy': 'Aggressive IC (SPX)',
                        'status': pos.get('status', 'open'),
                        'strikes': f"{pos.get('put_short_strike', 0):.0f}/{pos.get('call_short_strike', 0):.0f}",
                        'direction': 'NEUTRAL',
                        'pnl': round(float(pnl), 2) if pnl else 0,
                        'safe': True
                    })
        except Exception as e:
            logger.debug(f"Could not fetch TITAN positions: {e}")

        # Check ICARUS positions (Aggressive Directional)
        try:
            from backend.api.routes.icarus_routes import get_icarus_positions
            icarus_data = await get_icarus_positions()
            if icarus_data.get('success') and icarus_data.get('data', {}).get('positions'):
                for pos in icarus_data['data']['positions']:
                    direction = pos.get('direction', 'NEUTRAL')
                    pnl = pos.get('realized_pnl') or pos.get('unrealized_pnl', 0)
                    positions.append({
                        'bot': 'ICARUS',
                        'strategy': 'Aggressive Directional',
                        'status': pos.get('status', 'open'),
                        'strikes': str(pos.get('strike', 'N/A')),
                        'direction': direction.upper() if direction else 'NEUTRAL',
                        'pnl': round(float(pnl), 2) if pnl else 0,
                        'safe': True
                    })
        except Exception as e:
            logger.debug(f"Could not fetch ICARUS positions: {e}")

        # Check PEGASUS positions (Weekly Iron Condors)
        try:
            from backend.api.routes.pegasus_routes import get_pegasus_positions
            pegasus_data = await get_pegasus_positions()
            if pegasus_data.get('success') and pegasus_data.get('data', {}).get('positions'):
                for pos in pegasus_data['data']['positions']:
                    pnl = pos.get('realized_pnl') or pos.get('unrealized_pnl', 0)
                    positions.append({
                        'bot': 'PEGASUS',
                        'strategy': 'Weekly IC (SPX)',
                        'status': pos.get('status', 'open'),
                        'strikes': f"{pos.get('put_short_strike', 0):.0f}/{pos.get('call_short_strike', 0):.0f}",
                        'direction': 'NEUTRAL',
                        'pnl': round(float(pnl), 2) if pnl else 0,
                        'safe': True
                    })
        except Exception as e:
            logger.debug(f"Could not fetch PEGASUS positions: {e}")

        return {
            "success": True,
            "data": {
                "positions": positions,
                "count": len(positions)
            }
        }

    except Exception as e:
        logger.error(f"Error getting bot positions: {e}")
        return {
            "success": True,
            "data": {
                "positions": [],
                "count": 0
            }
        }


@router.get("/accuracy")
async def get_accuracy_metrics():
    """
    Get prediction accuracy metrics.

    Shows rolling accuracy for pin predictions, direction, magnet hit rate.
    """
    try:
        conn = get_connection()
        if not conn:
            return {
                "success": True,
                "data": get_default_accuracy()
            }

        cursor = conn.cursor()

        # Get latest accuracy metrics
        cursor.execute("""
            SELECT
                metric_date,
                pin_accuracy_7d,
                pin_accuracy_30d,
                direction_accuracy_7d,
                direction_accuracy_30d,
                magnet_hit_rate_7d,
                magnet_hit_rate_30d,
                total_predictions
            FROM argus_accuracy
            ORDER BY metric_date DESC
            LIMIT 1
        """)

        row = cursor.fetchone()
        cursor.close()
        conn.close()

        if row:
            return {
                "success": True,
                "data": {
                    "date": row[0].isoformat() if row[0] else None,
                    "pin_accuracy_7d": float(row[1]) if row[1] else 0,
                    "pin_accuracy_30d": float(row[2]) if row[2] else 0,
                    "direction_accuracy_7d": float(row[3]) if row[3] else 0,
                    "direction_accuracy_30d": float(row[4]) if row[4] else 0,
                    "magnet_hit_rate_7d": float(row[5]) if row[5] else 0,
                    "magnet_hit_rate_30d": float(row[6]) if row[6] else 0,
                    "total_predictions": row[7] or 0
                }
            }
        else:
            return {
                "success": True,
                "data": get_default_accuracy()
            }

    except Exception as e:
        logger.error(f"Error getting accuracy metrics: {e}")
        return {
            "success": True,
            "data": get_default_accuracy()
        }


def get_default_accuracy() -> dict:
    """Return default accuracy metrics"""
    return {
        "date": None,
        "pin_accuracy_7d": 0,
        "pin_accuracy_30d": 0,
        "direction_accuracy_7d": 0,
        "direction_accuracy_30d": 0,
        "magnet_hit_rate_7d": 0,
        "magnet_hit_rate_30d": 0,
        "total_predictions": 0,
        "message": "No accuracy data available yet - predictions will be tracked over time"
    }


def calculate_pattern_similarity(current: dict, historical: dict) -> float:
    """
    Calculate similarity score between current gamma structure and a historical day.
    Returns a score from 0-100.
    """
    score = 0.0
    weights = {
        'regime': 30,      # Same regime is most important
        'net_gex': 25,     # Similar net GEX level
        'flip_dist': 20,   # Similar flip point distance from spot
        'wall_ratio': 15,  # Similar call/put wall balance
        'mm_state': 10,    # Same market maker state
    }

    # 1. Regime match (30 points)
    if current.get('regime') and historical.get('regime'):
        if current['regime'] == historical['regime']:
            score += weights['regime']
        elif (current['regime'] in ['POSITIVE', 'STRONG_POSITIVE'] and
              historical['regime'] in ['POSITIVE', 'STRONG_POSITIVE']):
            score += weights['regime'] * 0.7
        elif (current['regime'] in ['NEGATIVE', 'STRONG_NEGATIVE'] and
              historical['regime'] in ['NEGATIVE', 'STRONG_NEGATIVE']):
            score += weights['regime'] * 0.7

    # 2. Net GEX similarity (25 points) - compare magnitude
    if current.get('net_gex') and historical.get('net_gex'):
        curr_gex = abs(current['net_gex'])
        hist_gex = abs(historical['net_gex'])
        if curr_gex > 0 and hist_gex > 0:
            ratio = min(curr_gex, hist_gex) / max(curr_gex, hist_gex)
            # Same sign bonus
            if (current['net_gex'] > 0) == (historical['net_gex'] > 0):
                score += weights['net_gex'] * ratio
            else:
                score += weights['net_gex'] * ratio * 0.3

    # 3. Flip point distance from spot (20 points)
    if (current.get('flip_point') and current.get('spot_price') and
        historical.get('flip_point') and historical.get('spot_price')):
        curr_flip_dist = (current['flip_point'] - current['spot_price']) / current['spot_price'] * 100
        hist_flip_dist = (historical['flip_point'] - historical['spot_price']) / historical['spot_price'] * 100
        # Similar distance = higher score
        dist_diff = abs(curr_flip_dist - hist_flip_dist)
        if dist_diff < 0.5:
            score += weights['flip_dist']
        elif dist_diff < 1.0:
            score += weights['flip_dist'] * 0.7
        elif dist_diff < 2.0:
            score += weights['flip_dist'] * 0.4

    # 4. Call/Put wall ratio (15 points)
    if (current.get('call_wall') and current.get('put_wall') and current.get('spot_price') and
        historical.get('call_wall') and historical.get('put_wall') and historical.get('spot_price')):
        curr_call_dist = (current['call_wall'] - current['spot_price']) / current['spot_price'] * 100
        curr_put_dist = (current['spot_price'] - current['put_wall']) / current['spot_price'] * 100
        hist_call_dist = (historical['call_wall'] - historical['spot_price']) / historical['spot_price'] * 100
        hist_put_dist = (historical['spot_price'] - historical['put_wall']) / historical['spot_price'] * 100

        call_diff = abs(curr_call_dist - hist_call_dist)
        put_diff = abs(curr_put_dist - hist_put_dist)
        avg_diff = (call_diff + put_diff) / 2

        if avg_diff < 0.5:
            score += weights['wall_ratio']
        elif avg_diff < 1.0:
            score += weights['wall_ratio'] * 0.7
        elif avg_diff < 2.0:
            score += weights['wall_ratio'] * 0.4

    # 5. Market maker state (10 points)
    if current.get('mm_state') and historical.get('mm_state'):
        if current['mm_state'] == historical['mm_state']:
            score += weights['mm_state']

    return round(score, 1)


@router.get("/patterns")
async def get_pattern_matches():
    """
    Get pattern match analysis.

    Compares current gamma structure to historical patterns from gex_history table.
    Returns similar historical days and their price outcomes.
    """
    engine = get_engine()
    if not engine or not engine.previous_snapshot:
        return {
            "success": True,
            "data": {
                "patterns": [],
                "message": "No current gamma data available"
            }
        }

    try:
        snapshot = engine.previous_snapshot

        # Build current structure for comparison
        current_structure = {
            'regime': snapshot.gamma_regime,
            'net_gex': snapshot.total_net_gamma,
            'spot_price': snapshot.spot_price,
            'flip_point': None,  # Will be calculated below
            'call_wall': None,
            'put_wall': None,
            'mm_state': None,
        }

        # Get flip point, walls from strikes
        if snapshot.strikes:
            # Find flip point (where gamma crosses zero)
            for i, strike in enumerate(snapshot.strikes[:-1]):
                if hasattr(strike, 'net_gamma'):
                    curr_gamma = strike.net_gamma
                    next_gamma = snapshot.strikes[i + 1].net_gamma if hasattr(snapshot.strikes[i + 1], 'net_gamma') else 0
                    if curr_gamma * next_gamma < 0:  # Sign change
                        current_structure['flip_point'] = strike.strike
                        break

            # Find call and put walls (highest gamma strikes above/below spot)
            above_spot = [s for s in snapshot.strikes if hasattr(s, 'strike') and s.strike > snapshot.spot_price]
            below_spot = [s for s in snapshot.strikes if hasattr(s, 'strike') and s.strike < snapshot.spot_price]

            if above_spot:
                call_wall = max(above_spot, key=lambda s: abs(getattr(s, 'net_gamma', 0)))
                current_structure['call_wall'] = call_wall.strike
            if below_spot:
                put_wall = max(below_spot, key=lambda s: abs(getattr(s, 'net_gamma', 0)))
                current_structure['put_wall'] = put_wall.strike

        # Query historical data from gex_history table
        conn = get_connection()
        if not conn:
            return {
                "success": True,
                "data": {
                    "patterns": [],
                    "current_structure": {
                        "gamma_regime": snapshot.gamma_regime,
                        "top_magnet": snapshot.magnets[0]['strike'] if snapshot.magnets else None,
                        "likely_pin": snapshot.likely_pin
                    },
                    "message": "Database not available for pattern matching"
                }
            }

        cursor = conn.cursor()

        # Get daily snapshots from gex_history for gamma structure
        # Join with price_history AND market_data_daily for ACTUAL daily OHLC data
        # Look back 90 days for pattern matching
        #
        # BUG FIX: Previously used gex_history spot_price as open/close which was
        # just the price at snapshot time (e.g., 10 AM), NOT actual market open/close.
        # Now uses price_history OR market_data_daily (Yahoo Finance) for real OHLC.
        cursor.execute("""
            WITH daily_snapshots AS (
                -- Get one GEX snapshot per day (morning snapshot for gamma structure)
                SELECT DISTINCT ON (DATE(timestamp))
                    DATE(timestamp) as trade_date,
                    net_gex,
                    flip_point,
                    call_wall,
                    put_wall,
                    spot_price as snapshot_price,
                    mm_state,
                    regime
                FROM gex_history
                WHERE symbol = 'SPY'
                AND timestamp > NOW() - INTERVAL '90 days'
                AND timestamp < NOW() - INTERVAL '1 day'
                AND EXTRACT(HOUR FROM timestamp) BETWEEN 9 AND 11
                ORDER BY DATE(timestamp), timestamp
            ),
            price_history_ohlc AS (
                -- Get daily OHLC from price_history table (Tradier/Polygon)
                SELECT
                    DATE(timestamp) as trade_date,
                    open as day_open,
                    high as day_high,
                    low as day_low,
                    close as day_close,
                    volume as day_volume
                FROM price_history
                WHERE symbol = 'SPY'
                AND timeframe = '1d'
                AND timestamp > NOW() - INTERVAL '90 days'
            ),
            yahoo_ohlc AS (
                -- Fallback: Get daily OHLC from market_data_daily (Yahoo Finance)
                SELECT
                    date as trade_date,
                    open as day_open,
                    high as day_high,
                    low as day_low,
                    close as day_close,
                    volume as day_volume
                FROM market_data_daily
                WHERE symbol = 'SPY'
                AND date > NOW() - INTERVAL '90 days'
            ),
            combined_ohlc AS (
                -- Combine both sources, preferring price_history over yahoo
                SELECT DISTINCT ON (trade_date)
                    COALESCE(ph.trade_date, yh.trade_date) as trade_date,
                    COALESCE(ph.day_open, yh.day_open) as day_open,
                    COALESCE(ph.day_high, yh.day_high) as day_high,
                    COALESCE(ph.day_low, yh.day_low) as day_low,
                    COALESCE(ph.day_close, yh.day_close) as day_close,
                    COALESCE(ph.day_volume, yh.day_volume) as day_volume,
                    CASE WHEN ph.trade_date IS NOT NULL THEN 'price_history' ELSE 'yahoo' END as data_source
                FROM price_history_ohlc ph
                FULL OUTER JOIN yahoo_ohlc yh ON ph.trade_date = yh.trade_date
                ORDER BY trade_date, data_source
            ),
            daily_outcomes AS (
                SELECT
                    ds.trade_date,
                    ds.net_gex,
                    ds.flip_point,
                    ds.call_wall,
                    ds.put_wall,
                    ds.mm_state,
                    ds.regime,
                    ds.snapshot_price,
                    -- Use ACTUAL OHLC from combined sources, fallback to gex snapshot prices
                    COALESCE(ohlc.day_open, ds.snapshot_price) as open_price,
                    COALESCE(ohlc.day_close, ds.snapshot_price) as close_price,
                    COALESCE(ohlc.day_high, ds.snapshot_price) as day_high,
                    COALESCE(ohlc.day_low, ds.snapshot_price) as day_low,
                    COALESCE(ohlc.day_high - ohlc.day_low, 0) as day_range,
                    -- Flag to indicate if we have real OHLC data
                    CASE WHEN ohlc.day_open IS NOT NULL THEN TRUE ELSE FALSE END as has_real_ohlc
                FROM daily_snapshots ds
                LEFT JOIN combined_ohlc ohlc ON ds.trade_date = ohlc.trade_date
            )
            SELECT
                trade_date,
                net_gex,
                flip_point,
                call_wall,
                put_wall,
                open_price,
                mm_state,
                regime,
                close_price,
                day_high,
                day_low,
                day_range,
                CASE
                    WHEN close_price > open_price THEN 'UP'
                    WHEN close_price < open_price THEN 'DOWN'
                    ELSE 'FLAT'
                END as outcome_direction,
                CASE
                    WHEN open_price > 0 THEN ROUND(((close_price - open_price) / open_price * 100)::numeric, 2)
                    ELSE 0
                END as outcome_pct,
                ROUND((close_price - open_price)::numeric, 2) as price_change,
                has_real_ohlc
            FROM daily_outcomes
            WHERE net_gex IS NOT NULL
            ORDER BY trade_date DESC
        """)

        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        if not rows:
            return {
                "success": True,
                "data": {
                    "patterns": [],
                    "current_structure": {
                        "gamma_regime": snapshot.gamma_regime,
                        "top_magnet": snapshot.magnets[0]['strike'] if snapshot.magnets else None,
                        "likely_pin": snapshot.likely_pin
                    },
                    "message": "No historical gamma data available for pattern matching"
                }
            }

        # Calculate similarity for each historical day
        pattern_matches = []
        days_with_real_ohlc = 0
        for row in rows:
            (trade_date, net_gex, flip_point, call_wall, put_wall, open_price,
             mm_state, regime, close_price, day_high, day_low, day_range,
             outcome_dir, outcome_pct, price_change, has_real_ohlc) = row

            # Track how many days have real OHLC data
            if has_real_ohlc:
                days_with_real_ohlc += 1

            historical = {
                'net_gex': float(net_gex) if net_gex else None,
                'flip_point': float(flip_point) if flip_point else None,
                'call_wall': float(call_wall) if call_wall else None,
                'put_wall': float(put_wall) if put_wall else None,
                'spot_price': float(open_price) if open_price else None,
                'mm_state': mm_state,
                'regime': regime,
            }

            similarity = calculate_pattern_similarity(current_structure, historical)

            if similarity >= 30:  # Only include matches with at least 30% similarity
                # Generate a summary of what happened that day
                summary_parts = []
                if regime:
                    summary_parts.append(f"{regime} gamma regime")
                if outcome_dir == 'UP':
                    summary_parts.append(f"SPY rallied +${abs(float(price_change or 0)):.2f} ({abs(float(outcome_pct or 0)):.1f}%)")
                elif outcome_dir == 'DOWN':
                    summary_parts.append(f"SPY fell -${abs(float(price_change or 0)):.2f} ({abs(float(outcome_pct or 0)):.1f}%)")
                else:
                    # Only show "flat" if we have real OHLC and it truly was flat
                    if has_real_ohlc:
                        summary_parts.append("SPY closed flat")
                    else:
                        summary_parts.append("SPY outcome unknown (no price data)")

                if day_range and float(day_range) > 0:
                    range_pct = (float(day_range) / float(open_price) * 100) if open_price else 0
                    summary_parts.append(f"Range: ${float(day_range):.2f} ({range_pct:.1f}%)")

                if mm_state:
                    summary_parts.append(f"MMs were {mm_state}")

                summary = ". ".join(summary_parts) + "." if summary_parts else "No summary available."

                pattern_matches.append({
                    'date': trade_date.strftime('%Y-%m-%d') if trade_date else None,
                    'similarity_score': similarity,
                    'outcome_direction': outcome_dir if has_real_ohlc else 'UNKNOWN',
                    'outcome_pct': float(outcome_pct) if outcome_pct else 0.0,
                    'price_change': float(price_change) if price_change else 0.0,
                    'gamma_regime_then': regime or 'UNKNOWN',
                    'mm_state': mm_state or 'UNKNOWN',
                    # Price details
                    'open_price': float(open_price) if open_price else None,
                    'close_price': float(close_price) if close_price else None,
                    'day_high': float(day_high) if day_high else None,
                    'day_low': float(day_low) if day_low else None,
                    'day_range': float(day_range) if day_range else None,
                    # Key levels that day
                    'flip_point': float(flip_point) if flip_point else None,
                    'call_wall': float(call_wall) if call_wall else None,
                    'put_wall': float(put_wall) if put_wall else None,
                    # Data quality indicator
                    'has_real_ohlc': bool(has_real_ohlc),
                    # Summary
                    'summary': summary,
                })

        # Sort by similarity score and take top 5
        pattern_matches.sort(key=lambda x: x['similarity_score'], reverse=True)
        top_matches = pattern_matches[:5]

        return {
            "success": True,
            "data": {
                "patterns": top_matches,
                "current_structure": {
                    "gamma_regime": snapshot.gamma_regime,
                    "top_magnet": snapshot.magnets[0]['strike'] if snapshot.magnets else None,
                    "likely_pin": snapshot.likely_pin
                },
                "total_days_analyzed": len(rows),
                "matches_found": len(pattern_matches),
                "days_with_real_ohlc": days_with_real_ohlc,
                "data_quality_note": f"{days_with_real_ohlc}/{len(rows)} days have verified daily OHLC data" if rows else None
            }
        }

    except Exception as e:
        logger.error(f"Error getting pattern matches: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": True,
            "data": {
                "patterns": [],
                "message": f"Error analyzing patterns: {str(e)}"
            }
        }


@router.get("/export")
async def export_data(
    format: str = Query("excel", description="Export format: excel, csv"),
    date: Optional[str] = Query(None, description="Date to export YYYY-MM-DD")
):
    """
    Export ARGUS data to Excel or CSV.

    Returns downloadable file with gamma data, commentary, and alerts.
    """
    # This would generate and return an Excel file
    # For now, return the data as JSON
    try:
        engine = get_engine()
        if not engine or not engine.previous_snapshot:
            raise HTTPException(status_code=404, detail="No data to export")

        snapshot = engine.previous_snapshot

        export_data = {
            "snapshot": snapshot.to_dict(),
            "alerts": engine.get_active_alerts(),
            "export_time": format_central_timestamp(),
            "format_requested": format
        }

        return {
            "success": True,
            "data": export_data,
            "message": "Excel export will be implemented - returning JSON for now"
        }

    except Exception as e:
        logger.error(f"Error exporting data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/replay")
async def get_replay_data(
    date: str = Query(..., description="Date to replay YYYY-MM-DD"),
    time: Optional[str] = Query(None, description="Time to get HH:MM")
):
    """
    Get historical replay data for a specific date/time.

    Returns gamma structure as it was at that point in time.
    """
    try:
        conn = get_connection()
        if not conn:
            raise HTTPException(status_code=503, detail="Database not connected")

        cursor = conn.cursor()

        # Build query based on whether time is specified
        if time:
            cursor.execute("""
                SELECT
                    s.id,
                    s.snapshot_time,
                    s.spot_price,
                    s.expected_move,
                    s.vix,
                    s.total_net_gamma,
                    s.gamma_regime
                FROM argus_snapshots s
                WHERE DATE(s.snapshot_time) = %s
                AND s.snapshot_time::time <= %s::time
                ORDER BY s.snapshot_time DESC
                LIMIT 1
            """, (date, time))
        else:
            cursor.execute("""
                SELECT
                    s.id,
                    s.snapshot_time,
                    s.spot_price,
                    s.expected_move,
                    s.vix,
                    s.total_net_gamma,
                    s.gamma_regime
                FROM argus_snapshots s
                WHERE DATE(s.snapshot_time) = %s
                ORDER BY s.snapshot_time DESC
                LIMIT 1
            """, (date,))

        snapshot = cursor.fetchone()

        if not snapshot:
            cursor.close()
            conn.close()
            return {
                "success": True,
                "data": None,
                "message": f"No data available for {date}"
            }

        snapshot_id = snapshot[0]

        # Get strikes for this snapshot
        cursor.execute("""
            SELECT
                strike,
                net_gamma,
                probability,
                is_magnet,
                magnet_rank,
                is_pin
            FROM argus_strikes
            WHERE snapshot_id = %s
            ORDER BY strike
        """, (snapshot_id,))

        strikes = cursor.fetchall()
        cursor.close()
        conn.close()

        return {
            "success": True,
            "data": {
                "snapshot_time": snapshot[1].isoformat() if snapshot[1] else None,
                "spot_price": float(snapshot[2]) if snapshot[2] else None,
                "expected_move": float(snapshot[3]) if snapshot[3] else None,
                "vix": float(snapshot[4]) if snapshot[4] else None,
                "total_net_gamma": float(snapshot[5]) if snapshot[5] else None,
                "gamma_regime": snapshot[6],
                "strikes": [
                    {
                        "strike": float(s[0]),
                        "net_gamma": float(s[1]) if s[1] else 0,
                        "probability": float(s[2]) if s[2] else 0,
                        "is_magnet": s[3],
                        "magnet_rank": s[4],
                        "is_pin": s[5]
                    }
                    for s in strikes
                ]
            }
        }

    except Exception as e:
        logger.error(f"Error getting replay data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/replay/dates")
async def get_available_replay_dates():
    """
    Get list of dates available for historical replay.
    """
    try:
        conn = get_connection()
        if not conn:
            return {
                "success": True,
                "data": {
                    "dates": [],
                    "message": "Database not connected"
                }
            }

        cursor = conn.cursor()
        cursor.execute("""
            SELECT DISTINCT DATE(snapshot_time) as date
            FROM argus_snapshots
            ORDER BY date DESC
            LIMIT 90
        """)

        dates = [row[0].isoformat() for row in cursor.fetchall()]
        cursor.close()
        conn.close()

        return {
            "success": True,
            "data": {
                "dates": dates,
                "count": len(dates)
            }
        }

    except Exception as e:
        logger.error(f"Error getting replay dates: {e}")
        return {
            "success": True,
            "data": {
                "dates": [],
                "message": "No historical data available yet"
            }
        }


@router.get("/context")
async def get_market_context():
    """
    Get additional market context from regime analysis.

    Returns:
    - IV Rank & Percentile
    - Gamma wall proximity
    - Psychology trap alerts
    - VIX context with spike detection
    - Multi-timeframe RSI alignment
    - Monthly magnets
    """
    try:
        conn = get_connection()
        if not conn:
            return {
                "success": True,
                "data": get_default_context(),
                "message": "Database not connected"
            }

        cursor = conn.cursor()

        # Get latest regime signal with full context
        cursor.execute("""
            SELECT
                timestamp,
                spy_price,
                -- Gamma Walls
                nearest_call_wall,
                call_wall_distance_pct,
                call_wall_strength,
                nearest_put_wall,
                put_wall_distance_pct,
                put_wall_strength,
                net_gamma_regime,
                -- Psychology Traps
                psychology_trap,
                liberation_setup_detected,
                liberation_target_strike,
                false_floor_detected,
                false_floor_strike,
                path_of_least_resistance,
                polr_confidence,
                -- VIX
                vix_current,
                vix_spike_detected,
                volatility_regime,
                -- RSI
                rsi_5m,
                rsi_15m,
                rsi_1h,
                rsi_4h,
                rsi_1d,
                rsi_aligned_overbought,
                rsi_aligned_oversold,
                -- Monthly Magnets
                monthly_magnet_above,
                monthly_magnet_below,
                -- Regime
                primary_regime_type,
                confidence_score,
                trade_direction,
                risk_level
            FROM regime_signals
            ORDER BY timestamp DESC
            LIMIT 1
        """)

        row = cursor.fetchone()
        cursor.close()
        conn.close()

        if not row:
            return {
                "success": True,
                "data": get_default_context(),
                "message": "No regime data available"
            }

        return {
            "success": True,
            "data": {
                "timestamp": row[0].isoformat() if row[0] else None,
                "spy_price": float(row[1]) if row[1] else None,
                "gamma_walls": {
                    "call_wall": float(row[2]) if row[2] else None,
                    "call_wall_distance": float(row[3]) if row[3] else None,
                    "call_wall_strength": row[4],
                    "put_wall": float(row[5]) if row[5] else None,
                    "put_wall_distance": float(row[6]) if row[6] else None,
                    "put_wall_strength": row[7],
                    "net_gamma_regime": row[8]
                },
                "psychology_traps": {
                    "active_trap": row[9],
                    "liberation_setup": row[10] or False,
                    "liberation_target": float(row[11]) if row[11] else None,
                    "false_floor": row[12] or False,
                    "false_floor_strike": float(row[13]) if row[13] else None,
                    "polr": row[14],
                    "polr_confidence": float(row[15]) if row[15] else None
                },
                "vix_context": {
                    "current": float(row[16]) if row[16] else None,
                    "spike_detected": row[17] or False,
                    "volatility_regime": row[18]
                },
                "rsi_alignment": {
                    "rsi_5m": float(row[19]) if row[19] else None,
                    "rsi_15m": float(row[20]) if row[20] else None,
                    "rsi_1h": float(row[21]) if row[21] else None,
                    "rsi_4h": float(row[22]) if row[22] else None,
                    "rsi_1d": float(row[23]) if row[23] else None,
                    "aligned_overbought": row[24] or False,
                    "aligned_oversold": row[25] or False
                },
                "monthly_magnets": {
                    "above": float(row[26]) if row[26] else None,
                    "below": float(row[27]) if row[27] else None
                },
                "regime": {
                    "type": row[28],
                    "confidence": float(row[29]) if row[29] else None,
                    "direction": row[30],
                    "risk_level": row[31]
                }
            }
        }

    except Exception as e:
        logger.error(f"Error getting market context: {e}")
        return {
            "success": True,
            "data": get_default_context(),
            "message": f"Error: {str(e)}"
        }


def get_default_context() -> dict:
    """Return default context when data unavailable"""
    return {
        "gamma_walls": {
            "call_wall": None,
            "call_wall_distance": None,
            "put_wall": None,
            "put_wall_distance": None
        },
        "psychology_traps": {
            "active_trap": None,
            "liberation_setup": False,
            "false_floor": False
        },
        "vix_context": {
            "current": None,
            "spike_detected": False
        },
        "rsi_alignment": {},
        "monthly_magnets": {},
        "regime": {}
    }


@router.get("/strike-trends")
async def get_strike_trends():
    """
    Get 30-minute trend data for each strike.

    Returns:
    - Dominant status (BUILDING, COLLAPSING, SPIKE, or NEUTRAL)
    - Duration of current/dominant status
    - Count of each status type
    - Gamma flip history
    """
    try:
        conn = get_connection()
        if not conn:
            return {
                "success": True,
                "data": {"trends": {}, "message": "Database not connected"}
            }

        cursor = conn.cursor()

        # Get danger zone events from the last 30 minutes, grouped by strike
        cursor.execute("""
            SELECT
                strike,
                danger_type,
                detected_at,
                resolved_at,
                is_active,
                roc_1min,
                roc_5min
            FROM argus_danger_zone_logs
            WHERE detected_at > NOW() - INTERVAL '30 minutes'
            ORDER BY strike, detected_at DESC
        """)

        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        # Process into per-strike trends
        strike_events = {}
        for row in rows:
            strike = float(row[0])
            if strike not in strike_events:
                strike_events[strike] = []
            strike_events[strike].append({
                'danger_type': row[1],
                'detected_at': row[2],
                'resolved_at': row[3],
                'is_active': row[4],
                'roc_1min': float(row[5]) if row[5] else 0,
                'roc_5min': float(row[6]) if row[6] else 0
            })

        # Calculate trends for each strike
        trends = {}
        now = datetime.now(CENTRAL_TZ)

        for strike, events in strike_events.items():
            # Count status occurrences
            status_counts = {'BUILDING': 0, 'COLLAPSING': 0, 'SPIKE': 0}
            status_durations = {'BUILDING': 0, 'COLLAPSING': 0, 'SPIKE': 0}

            for event in events:
                status = event['danger_type']
                if status in status_counts:
                    status_counts[status] += 1

                    # Calculate duration (in minutes)
                    start = event['detected_at']
                    end = event['resolved_at'] or now
                    if start.tzinfo is None:
                        start = start.replace(tzinfo=CENTRAL_TZ)
                    if hasattr(end, 'tzinfo') and end.tzinfo is None:
                        end = end.replace(tzinfo=CENTRAL_TZ)
                    duration = (end - start).total_seconds() / 60
                    status_durations[status] += duration

            # Determine dominant status (by total duration)
            dominant = max(status_durations, key=status_durations.get)
            dominant_duration = status_durations[dominant]

            # Get current active status
            current_status = None
            current_duration = 0
            for event in events:
                if event['is_active']:
                    current_status = event['danger_type']
                    start = event['detected_at']
                    if start.tzinfo is None:
                        start = start.replace(tzinfo=CENTRAL_TZ)
                    current_duration = (now - start).total_seconds() / 60
                    break

            trends[str(strike)] = {
                'dominant_status': dominant if dominant_duration > 0 else 'NEUTRAL',
                'dominant_duration_mins': round(dominant_duration, 1),
                'current_status': current_status,
                'current_duration_mins': round(current_duration, 1),
                'status_counts': status_counts,
                'status_durations': {k: round(v, 1) for k, v in status_durations.items()},
                'total_events': len(events)
            }

        return {
            "success": True,
            "data": {
                "trends": trends,
                "window_minutes": 30,
                "generated_at": format_central_timestamp()
            }
        }

    except Exception as e:
        logger.error(f"Error getting strike trends: {e}")
        return {
            "success": True,
            "data": {"trends": {}, "message": f"Error: {str(e)}"}
        }


@router.get("/gamma-flips")
async def get_gamma_flip_history():
    """
    Get gamma flip history for the last 30 minutes.

    Returns strikes that changed from positive to negative gamma or vice versa.
    """
    engine = get_engine()
    if not engine:
        return {
            "success": True,
            "data": {"flips": [], "message": "Engine not available"}
        }

    try:
        # Get flips from engine history
        flips = []
        now = datetime.now()
        cutoff = now - timedelta(minutes=30)

        for strike, history in engine.history.items():
            if len(history) < 2:
                continue

            # Look for sign changes in history
            for i in range(1, len(history)):
                prev_time, prev_gamma = history[i-1]
                curr_time, curr_gamma = history[i]

                if curr_time < cutoff:
                    continue

                # Check for sign flip
                if (prev_gamma > 0 and curr_gamma < 0):
                    flips.append({
                        'strike': strike,
                        'direction': 'POS_TO_NEG',
                        'flipped_at': curr_time.isoformat(),
                        'gamma_before': round(prev_gamma, 2),
                        'gamma_after': round(curr_gamma, 2),
                        'mins_ago': round((now - curr_time).total_seconds() / 60, 1)
                    })
                elif (prev_gamma < 0 and curr_gamma > 0):
                    flips.append({
                        'strike': strike,
                        'direction': 'NEG_TO_POS',
                        'flipped_at': curr_time.isoformat(),
                        'gamma_before': round(prev_gamma, 2),
                        'gamma_after': round(curr_gamma, 2),
                        'mins_ago': round((now - curr_time).total_seconds() / 60, 1)
                    })

        # Sort by most recent first
        flips.sort(key=lambda x: x['mins_ago'])

        return {
            "success": True,
            "data": {
                "flips": flips,
                "count": len(flips),
                "window_minutes": 30
            }
        }

    except Exception as e:
        logger.error(f"Error getting gamma flip history: {e}")
        return {
            "success": True,
            "data": {"flips": [], "message": f"Error: {str(e)}"}
        }


@router.get("/expirations")
async def get_expirations():
    """
    Get available 0DTE expirations for the week.

    SPY has 0DTE every day (Mon-Fri).
    """
    engine = get_engine()
    if not engine:
        raise HTTPException(status_code=503, detail="ARGUS engine not available")

    try:
        today = date.today()
        expirations = []

        for day in ['mon', 'tue', 'wed', 'thu', 'fri']:
            exp_date = engine.get_0dte_expiration(day)
            exp_date_obj = datetime.strptime(exp_date, '%Y-%m-%d').date()

            expirations.append({
                'day': day.upper(),
                'date': exp_date,
                'is_today': exp_date_obj == today,
                'is_past': exp_date_obj < today,
                'is_future': exp_date_obj > today
            })

        return {
            "success": True,
            "data": {
                "expirations": expirations,
                "today": today.strftime('%Y-%m-%d')
            }
        }

    except Exception as e:
        logger.error(f"Error getting expirations: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== TRADE SETUP DETECTOR ====================

@router.get("/trade-setups")
async def get_trade_setups(symbol: str = Query(default="SPY")):
    """
    Detect high-probability trade setups based on current gamma structure.

    Identifies:
    - IC_SAFE_ZONE: Price pinned between strong magnets (ideal for Iron Condors)
    - BREAKOUT_WARNING: Gamma collapsing at walls (avoid new positions)
    - FADE_THE_MOVE: Price overextended from flip in positive gamma (mean reversion)
    - MOMENTUM_PLAY: Strong directional gamma with wall break imminent
    - PIN_SETUP: High probability of pinning to specific strike

    Returns actionable trade setups with confidence scores.
    """
    engine = get_engine()
    if not engine:
        raise HTTPException(status_code=503, detail="ARGUS engine not available")

    try:
        # Get current gamma snapshot
        snapshot = engine.get_gamma_snapshot(symbol)
        if not snapshot or 'strikes' not in snapshot:
            return {"success": True, "data": {"setups": [], "message": "No gamma data available"}}

        spot_price = snapshot.get('spot_price', 0)
        flip_point = snapshot.get('flip_point', spot_price)
        gamma_regime = snapshot.get('gamma_regime', 'NEUTRAL')
        expected_move = snapshot.get('expected_move', 0)
        vix = snapshot.get('vix', 20)

        # Find key levels
        strikes = snapshot.get('strikes', [])
        call_wall = None
        put_wall = None
        max_call_gamma = 0
        max_put_gamma = 0

        for s in strikes:
            strike = s.get('strike', 0)
            net_gamma = s.get('net_gamma', 0)
            if strike > spot_price and net_gamma > max_call_gamma:
                max_call_gamma = net_gamma
                call_wall = strike
            elif strike < spot_price and abs(net_gamma) > max_put_gamma:
                max_put_gamma = abs(net_gamma)
                put_wall = strike

        setups = []

        # Calculate distances
        dist_to_flip_pct = abs(spot_price - flip_point) / spot_price * 100 if spot_price > 0 else 0
        dist_to_call_wall_pct = abs(call_wall - spot_price) / spot_price * 100 if call_wall and spot_price > 0 else 999
        dist_to_put_wall_pct = abs(spot_price - put_wall) / spot_price * 100 if put_wall and spot_price > 0 else 999

        # Helper to build common metrics for all setups
        def build_setup(setup_type: str, description: str, confidence_pct: float,
                        risk_level: str, trade_ideas: list, call_strikes: list = None, put_strikes: list = None):
            """Build a setup dict matching the frontend TradeSetup interface."""
            # Find pin probability from top magnet
            top_magnets = sorted(strikes, key=lambda x: abs(x.get('net_gamma', 0)), reverse=True)[:1]
            pin_prob = top_magnets[0].get('probability', 0.5) if top_magnets else 0.5

            return {
                'setup_type': setup_type,
                'description': description,
                'confidence': confidence_pct / 100.0,  # Frontend expects 0-1, not 0-100
                'risk_level': risk_level,
                'entry_zones': {
                    'call_strikes': call_strikes or ([call_wall] if call_wall else []),
                    'put_strikes': put_strikes or ([put_wall] if put_wall else [])
                },
                'current_metrics': {
                    'gamma_regime': gamma_regime,
                    'pin_probability': pin_prob * 100,  # As percentage
                    'distance_to_flip_pct': round(dist_to_flip_pct, 2),
                    'distance_to_wall_pct': round(min(dist_to_call_wall_pct, dist_to_put_wall_pct), 2)
                },
                'trade_ideas': trade_ideas
            }

        # IC_SAFE_ZONE: Price between walls with positive gamma
        if gamma_regime == 'POSITIVE' and dist_to_call_wall_pct > 0.5 and dist_to_put_wall_pct > 0.5:
            confidence = min(95, 70 + (min(dist_to_call_wall_pct, dist_to_put_wall_pct) * 10))
            setups.append(build_setup(
                setup_type='IC_SAFE_ZONE',
                description=f'Price pinned between walls at ${spot_price:.2f}. Positive gamma dampens moves. Safe for Iron Condors.',
                confidence_pct=confidence,
                risk_level='LOW' if vix < 20 else 'MEDIUM',
                trade_ideas=[
                    f'Sell Iron Condor with short strikes at ${put_wall} / ${call_wall}',
                    f'Target 30-50% of max profit, exit if tested',
                    f'VIX at {vix:.1f} - {"tight spreads OK" if vix < 18 else "widen strikes slightly"}'
                ]
            ))

        # BREAKOUT_WARNING: Near wall with negative gamma
        if gamma_regime == 'NEGATIVE' and (dist_to_call_wall_pct < 0.3 or dist_to_put_wall_pct < 0.3):
            wall_type = 'CALL' if dist_to_call_wall_pct < dist_to_put_wall_pct else 'PUT'
            confidence = min(90, 60 + ((0.5 - min(dist_to_call_wall_pct, dist_to_put_wall_pct)) * 100))
            setups.append(build_setup(
                setup_type='BREAKOUT_WARNING',
                description=f'Price near {wall_type.lower()} wall with negative gamma. Breakout likely. Avoid new Iron Condors.',
                confidence_pct=confidence,
                risk_level='HIGH',
                trade_ideas=[
                    f'AVOID opening new Iron Condors - wall break imminent',
                    f'Consider {"call" if wall_type == "CALL" else "put"} debit spread if directional',
                    f'If holding IC, consider closing {"call" if wall_type == "CALL" else "put"} side'
                ]
            ))

        # FADE_THE_MOVE: Overextended from flip in positive gamma
        if gamma_regime == 'POSITIVE' and dist_to_flip_pct > 0.5:
            direction = 'DOWN' if spot_price > flip_point else 'UP'
            confidence = min(85, 50 + (dist_to_flip_pct * 20))
            setups.append(build_setup(
                setup_type='FADE_THE_MOVE',
                description=f'Price {dist_to_flip_pct:.1f}% from flip point at ${flip_point:.2f}. Positive gamma pulls price back.',
                confidence_pct=confidence,
                risk_level='MEDIUM',
                trade_ideas=[
                    f'Fade move {"down" if direction == "DOWN" else "up"} toward flip at ${flip_point:.2f}',
                    f'{"Put" if direction == "DOWN" else "Call"} credit spread or directional play',
                    f'Target move of ${abs(flip_point - spot_price):.2f} back to flip'
                ]
            ))

        # PIN_SETUP: High magnet attraction
        pin_magnets = sorted(strikes, key=lambda x: abs(x.get('net_gamma', 0)), reverse=True)[:3]
        for magnet in pin_magnets:
            strike = magnet.get('strike', 0)
            probability = magnet.get('probability', 0)
            # Guard against division by zero when spot_price is 0 or missing
            if spot_price > 0 and probability > 0.6 and abs(strike - spot_price) / spot_price * 100 < 1.0:
                setups.append(build_setup(
                    setup_type='PIN_SETUP',
                    description=f'{probability*100:.0f}% probability of pinning to ${strike}. High gamma magnet attraction.',
                    confidence_pct=probability * 100,
                    risk_level='MEDIUM' if probability > 0.7 else 'HIGH',
                    trade_ideas=[
                        f'{"Sell straddle" if probability > 0.75 else "Sell strangle"} centered at ${strike}',
                        f'Pin probability: {probability*100:.0f}% - {"strong" if probability > 0.75 else "moderate"} conviction',
                        f'Distance to pin: {abs(strike - spot_price) / spot_price * 100:.2f}% from current price'
                    ],
                    call_strikes=[strike],
                    put_strikes=[strike]
                ))

        # Sort by confidence (descending)
        setups.sort(key=lambda x: x['confidence'], reverse=True)

        # Return the BEST setup directly in data (not wrapped in array)
        # Frontend expects a single TradeSetup object
        if setups:
            best_setup = setups[0]
        else:
            # Default setup when no conditions match
            best_setup = build_setup(
                setup_type='NEUTRAL',
                description=f'No clear setup detected. Market at ${spot_price:.2f} in {gamma_regime} gamma regime.',
                confidence_pct=50,
                risk_level='MEDIUM',
                trade_ideas=[
                    'Wait for clearer signal before entering',
                    f'Current gamma regime: {gamma_regime}',
                    f'VIX at {vix:.1f} - monitor for regime change'
                ]
            )

        return {
            "success": True,
            "data": best_setup  # Single setup object, not wrapped in array
        }

    except Exception as e:
        logger.error(f"Error detecting trade setups: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== OPTIMAL STRIKE RECOMMENDATIONS ====================

@router.get("/optimal-strikes")
async def get_optimal_strikes(
    symbol: str = Query(default="SPY"),
    strategy: str = Query(default="iron_condor", description="Strategy: iron_condor, put_spread, call_spread")
):
    """
    Recommend optimal strikes based on current gamma structure.

    For Iron Condors:
    - Short put at strongest put wall (support)
    - Short call at strongest call wall (resistance)
    - Wings based on expected move

    Returns strike recommendations with probability of profit.
    """
    engine = get_engine()
    if not engine:
        raise HTTPException(status_code=503, detail="ARGUS engine not available")

    try:
        snapshot = engine.get_gamma_snapshot(symbol)
        if not snapshot or 'strikes' not in snapshot:
            return {"success": True, "data": {"recommendations": [], "message": "No gamma data available"}}

        spot_price = snapshot.get('spot_price', 0)
        expected_move = snapshot.get('expected_move', 0)
        vix = snapshot.get('vix', 20)
        gamma_regime = snapshot.get('gamma_regime', 'NEUTRAL')
        strikes = snapshot.get('strikes', [])

        # Find call and put strikes
        raw_call_strikes = [s for s in strikes if s.get('strike', 0) > spot_price]
        raw_put_strikes = [s for s in strikes if s.get('strike', 0) < spot_price]

        # Sort by gamma strength (best strikes first)
        raw_call_strikes.sort(key=lambda x: x.get('net_gamma', 0), reverse=True)
        raw_put_strikes.sort(key=lambda x: abs(x.get('net_gamma', 0)), reverse=True)

        def build_optimal_strike(s: dict, side: str) -> dict:
            """Build OptimalStrike object matching frontend interface."""
            strike_price = s.get('strike', 0)
            probability = s.get('probability', 0.5)
            gamma = abs(s.get('net_gamma', 0))
            distance_pct = abs(strike_price - spot_price) / spot_price * 100 if spot_price > 0 else 0

            # Calculate expected value and risk/reward
            # For credit spreads: EV = (prob_win * credit) - (prob_loss * max_loss)
            # Simplified: Higher probability and closer distance = better EV
            ev_estimate = (1 - probability) * 100 - (probability * 50)  # Rough estimate
            risk_reward = (1 - probability) / max(probability, 0.01)  # Win/loss ratio

            return {
                'strike': strike_price,
                'side': side,
                'probability': round((1 - probability) * 100, 1),  # Prob of staying OTM (profit)
                'expected_value': round(ev_estimate, 2),
                'risk_reward': round(risk_reward, 2),
                'gamma_exposure': round(gamma, 0),
                'distance_from_spot_pct': round(distance_pct, 2)
            }

        # Build calls and puts arrays matching frontend OptimalStrike interface
        calls = [build_optimal_strike(s, 'CALL') for s in raw_call_strikes[:5]]
        puts = [build_optimal_strike(s, 'PUT') for s in raw_put_strikes[:5]]

        # Frontend expects: { calls: OptimalStrike[], puts: OptimalStrike[] }
        return {
            "success": True,
            "data": {
                "calls": calls,
                "puts": puts
            }
        }

    except Exception as e:
        logger.error(f"Error getting optimal strikes: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== HISTORICAL PATTERN OUTCOMES ====================

@router.get("/pattern-outcomes")
async def get_pattern_outcomes(symbol: str = Query(default="SPY")):
    """
    Match current gamma pattern to historical patterns and show outcomes.

    Returns:
    - Number of similar historical days
    - Win rate (stayed in expected range)
    - Average move
    - Best/worst outcomes
    """
    engine = get_engine()
    if not engine:
        raise HTTPException(status_code=503, detail="ARGUS engine not available")

    try:
        # Get current pattern
        snapshot = engine.get_gamma_snapshot(symbol)
        if not snapshot:
            return {"success": True, "data": {"matches": [], "message": "No gamma data available"}}

        current_regime = snapshot.get('gamma_regime', 'NEUTRAL')
        current_vix = snapshot.get('vix', 20)
        spot_price = snapshot.get('spot_price', 0)
        flip_point = snapshot.get('flip_point', spot_price)
        dist_to_flip = abs(spot_price - flip_point) / spot_price * 100 if spot_price > 0 else 0

        # Query historical data from database
        conn = get_connection()
        if not conn:
            return {"success": True, "data": {"matches": [], "message": "Database not available"}}

        cursor = conn.cursor()

        # Find similar historical patterns
        cursor.execute("""
            SELECT
                trade_date,
                spot_open,
                spot_close,
                spot_high,
                spot_low,
                net_gamma,
                flip_point,
                ABS(spot_close - spot_open) / spot_open * 100 as move_pct,
                (spot_high - spot_low) / spot_open * 100 as range_pct,
                CASE WHEN net_gamma > 0 THEN 'POSITIVE' ELSE 'NEGATIVE' END as regime
            FROM gex_structure_daily
            WHERE symbol = %s
            AND ABS(
                CASE WHEN net_gamma > 0 THEN 1 ELSE -1 END -
                CASE WHEN %s = 'POSITIVE' THEN 1 ELSE -1 END
            ) = 0
            ORDER BY trade_date DESC
            LIMIT 100
        """, (symbol, current_regime))

        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return {
                "success": True,
                "data": {
                    "patterns": [],
                    "message": "Insufficient historical data for pattern matching"
                }
            }

        # Build patterns array matching frontend PatternOutcome interface
        # Group by pattern type and calculate statistics for each
        moves = [abs(r[7]) for r in rows if r[7] is not None]
        ranges = [r[8] for r in rows if r[8] is not None]

        # Determine "win" = stayed within expected move (1.5% for 0DTE)
        expected_range = 1.5  # Typical 0DTE expected move %
        wins = sum(1 for m in moves if m <= expected_range)
        win_rate = wins / len(moves) * 100 if moves else 0

        # Calculate best and worst cases
        best_case = -min(moves) if moves else 0  # Best = smallest move (positive for IC)
        worst_case = -max(moves) if moves else 0  # Worst = biggest move (negative loss)

        # Calculate current similarity based on regime match and VIX
        base_similarity = 0.7 if current_regime in ['POSITIVE', 'NEGATIVE'] else 0.5
        vix_factor = 1.0 if 15 <= current_vix <= 25 else 0.8
        current_similarity = base_similarity * vix_factor

        # Build patterns matching frontend interface
        patterns = [
            {
                'pattern_type': f'{current_regime}_GAMMA',
                'sample_size': len(rows),
                'win_rate': round(win_rate, 1),
                'avg_return': round(-sum(moves) / len(moves) / 10, 1) if moves else 0,  # Approx IC return
                'best_case': round(best_case / 10, 1),  # Scale to reasonable %
                'worst_case': round(worst_case / 10, 1),
                'current_similarity': round(current_similarity, 2)
            }
        ]

        # Add regime-specific patterns if we have enough data
        if win_rate >= 60:
            patterns.append({
                'pattern_type': 'PIN_ZONE_HOLD',
                'sample_size': wins,
                'win_rate': round(win_rate, 1),
                'avg_return': round(abs(sum(m for m in moves if m <= expected_range)) / max(wins, 1) * 5, 1),
                'best_case': round(expected_range * 3, 1),
                'worst_case': -round(expected_range, 1),
                'current_similarity': round(current_similarity * 0.9, 2)
            })

        if len([m for m in moves if m > expected_range]) >= 5:
            breakout_moves = [m for m in moves if m > expected_range]
            patterns.append({
                'pattern_type': 'BREAKOUT_RISK',
                'sample_size': len(breakout_moves),
                'win_rate': round((1 - win_rate / 100) * 100, 1),  # Inverse for breakout traders
                'avg_return': round(sum(breakout_moves) / len(breakout_moves) * 2, 1),
                'best_case': round(max(breakout_moves) * 2, 1),
                'worst_case': round(-min(breakout_moves), 1),
                'current_similarity': round(current_similarity * 0.7, 2)
            })

        # Frontend expects response.data.data.patterns
        return {
            "success": True,
            "data": {
                "patterns": patterns
            }
        }

    except Exception as e:
        logger.error(f"Error getting pattern outcomes: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== PIN ACCURACY TRACKER ====================

@router.get("/pin-accuracy")
async def get_pin_accuracy(symbol: str = Query(default="SPY"), days: int = Query(default=30)):
    """
    Track accuracy of pin strike predictions over time.

    Measures:
    - How often the predicted pin strike was hit
    - Average distance from predicted pin to actual close
    - Accuracy by gamma regime
    """
    try:
        conn = get_connection()
        if not conn:
            return {"success": True, "data": {"accuracy": None, "message": "Database not available"}}

        cursor = conn.cursor()

        # Query prediction accuracy from stored predictions
        cursor.execute("""
            SELECT
                COUNT(*) as total_predictions,
                SUM(CASE WHEN ABS(predicted_pin - actual_close) / actual_close * 100 < 0.5 THEN 1 ELSE 0 END) as hits_05pct,
                SUM(CASE WHEN ABS(predicted_pin - actual_close) / actual_close * 100 < 1.0 THEN 1 ELSE 0 END) as hits_1pct,
                AVG(ABS(predicted_pin - actual_close) / actual_close * 100) as avg_distance_pct,
                gamma_regime
            FROM argus_pin_predictions
            WHERE symbol = %s
            AND prediction_date >= CURRENT_DATE - INTERVAL '%s days'
            GROUP BY gamma_regime
        """, (symbol, days))

        rows = cursor.fetchall()

        if not rows:
            # If no prediction table, return placeholder
            cursor.execute("""
                SELECT COUNT(*) FROM information_schema.tables
                WHERE table_name = 'argus_pin_predictions'
            """)
            table_exists = cursor.fetchone()[0] > 0

            conn.close()

            if not table_exists:
                return {
                    "success": True,
                    "data": {
                        "accuracy": None,
                        "message": "Pin prediction tracking not yet initialized. Predictions will be tracked going forward.",
                        "setup_required": True
                    }
                }

            return {
                "success": True,
                "data": {
                    "accuracy": None,
                    "message": f"No predictions in last {days} days",
                    "days_analyzed": days
                }
            }

        # Aggregate results
        total = sum(r[0] for r in rows)
        hits_05 = sum(r[1] or 0 for r in rows)
        hits_1 = sum(r[2] or 0 for r in rows)

        # Build accuracy_by_period array for frontend compatibility
        # Frontend expects: { period, predictions, accurate_within_1_pct, accurate_within_0_5_pct, accuracy_rate, avg_distance }
        accuracy_by_period = []
        for r in rows:
            regime = r[4] or 'UNKNOWN'
            preds = r[0] or 0
            hits_05_regime = r[1] or 0
            hits_1_regime = r[2] or 0
            avg_dist = float(r[3] or 0)

            accuracy_by_period.append({
                "period": regime,
                "predictions": preds,
                "accurate_within_0_5_pct": hits_05_regime,
                "accurate_within_1_pct": hits_1_regime,
                "accuracy_rate": round(hits_1_regime / preds * 100, 1) if preds > 0 else 0,
                "avg_distance": round(avg_dist, 2)
            })

        conn.close()

        return {
            "success": True,
            "data": {
                "accuracy_by_period": accuracy_by_period,
                "accuracy": {
                    "total_predictions": total,
                    "accuracy_within_05pct": round(hits_05 / total * 100, 1) if total > 0 else 0,
                    "accuracy_within_1pct": round(hits_1 / total * 100, 1) if total > 0 else 0
                },
                "days_analyzed": days,
                "symbol": symbol,
                "timestamp": format_central_timestamp()
            }
        }

    except Exception as e:
        logger.error(f"Error getting pin accuracy: {e}")
        # Return graceful fallback
        return {
            "success": True,
            "data": {
                "accuracy": None,
                "message": "Pin accuracy tracking initializing",
                "error": str(e)
            }
        }


# ==================== INTRADAY GAMMA DECAY ====================

@router.get("/gamma-decay")
async def get_gamma_decay(symbol: str = Query(default="SPY")):
    """
    Show how gamma changes throughout the trading day.

    Critical for 0DTE trading:
    - Gamma increases exponentially as expiration approaches
    - Morning: Lower gamma, wider ranges
    - Afternoon: Higher gamma, tighter pinning
    - Last hour: Gamma explosion, maximum pinning effect
    """
    engine = get_engine()
    if not engine:
        raise HTTPException(status_code=503, detail="ARGUS engine not available")

    try:
        # Get intraday gamma history
        conn = get_connection()
        if not conn:
            return {"success": True, "data": {"periods": [], "current_period": "", "decay_curve": [], "message": "Database not available"}}

        cursor = conn.cursor()

        # Query today's gamma snapshots by hour
        cursor.execute("""
            SELECT
                EXTRACT(HOUR FROM timestamp) as hour,
                AVG(ABS(net_gex)) as avg_gamma,
                MAX(ABS(net_gex)) as max_gamma,
                AVG(ABS(flip_point - spot_price) / spot_price * 100) as avg_dist_to_flip
            FROM gex_history
            WHERE symbol = %s
            AND DATE(timestamp) = CURRENT_DATE
            GROUP BY EXTRACT(HOUR FROM timestamp)
            ORDER BY hour
        """, (symbol,))

        today_data = cursor.fetchall()

        # Also get historical average by hour (for comparison)
        cursor.execute("""
            SELECT
                EXTRACT(HOUR FROM timestamp) as hour,
                AVG(ABS(net_gex)) as avg_gamma
            FROM gex_history
            WHERE symbol = %s
            AND timestamp >= CURRENT_DATE - INTERVAL '30 days'
            GROUP BY EXTRACT(HOUR FROM timestamp)
            ORDER BY hour
        """, (symbol,))

        historical_avg = {int(r[0]): float(r[1] or 0) for r in cursor.fetchall()}
        conn.close()

        # Build periods array (frontend expects 'periods' not 'decay_curve')
        # Frontend expects: { time_label, gamma_magnitude, regime, trading_implication }
        periods = []
        for r in today_data:
            hour = int(r[0])
            if 8 <= hour <= 16:  # Market hours CT
                gamma_val = round(float(r[1] or 0), 0)
                dist_to_flip = round(float(r[3] or 0), 2)

                # Determine regime based on gamma magnitude and distance to flip
                if gamma_val > historical_avg.get(hour, 0) * 1.2:
                    regime = "POSITIVE"  # High gamma = strong pinning
                elif gamma_val < historical_avg.get(hour, 0) * 0.8 or dist_to_flip > 1.0:
                    regime = "NEGATIVE"  # Low gamma or far from flip = momentum
                else:
                    regime = "NEUTRAL"

                # Determine trading implication for this specific hour
                if hour < 10:
                    implication = "Morning: Lower gamma, wider expected range. Good for directional plays."
                elif hour < 14:
                    implication = "Midday: Moderate gamma. Balanced risk/reward for spreads."
                elif hour < 15:
                    implication = "Afternoon: Rising gamma. Tighter ranges, stronger pinning."
                else:
                    implication = "Final hour: Maximum gamma. Extreme pinning. Exit or pin plays only."

                periods.append({
                    "hour": hour,
                    "time_label": f"{hour}:00",
                    "gamma_magnitude": gamma_val,
                    "max_gamma": round(float(r[2] or 0), 0),
                    "dist_to_flip_pct": dist_to_flip,
                    "historical_avg": round(historical_avg.get(hour, 0), 0),
                    "vs_historical": "HIGHER" if gamma_val > historical_avg.get(hour, 0) * 1.1 else "LOWER" if gamma_val < historical_avg.get(hour, 0) * 0.9 else "NORMAL",
                    "regime": regime,
                    "trading_implication": implication
                })

        # Add trading implications
        current_hour = get_central_time().hour
        implications = []

        if current_hour < 10:
            implications.append("MORNING: Lower gamma = wider expected range. Good for directional plays.")
        elif current_hour < 14:
            implications.append("MIDDAY: Moderate gamma. Balanced risk/reward for spreads.")
        elif current_hour < 15:
            implications.append("AFTERNOON: Rising gamma. Tighter ranges, stronger pinning.")
        else:
            implications.append("FINAL HOUR: Maximum gamma. Extreme pinning. Avoid new positions unless confident in pin.")

        # Format current_period for frontend (expects "HH:00" format)
        current_period = f"{current_hour}:00"

        return {
            "success": True,
            "data": {
                "periods": periods,
                "current_period": current_period,
                "current_hour": current_hour,  # Keep for backward compatibility
                "decay_curve": periods,  # Keep for backward compatibility
                "trading_implications": implications,
                "gamma_phases": {
                    "morning": {"hours": "8:30-10:00", "gamma_level": "LOW", "strategy": "Directional or wide IC"},
                    "midday": {"hours": "10:00-14:00", "gamma_level": "MODERATE", "strategy": "Standard IC"},
                    "afternoon": {"hours": "14:00-15:00", "gamma_level": "HIGH", "strategy": "Tight IC or avoid"},
                    "final_hour": {"hours": "15:00-16:00", "gamma_level": "EXTREME", "strategy": "Exit or pin plays only"}
                },
                "timestamp": format_central_timestamp()
            }
        }

    except Exception as e:
        logger.error(f"Error getting gamma decay: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== DATA SOURCE HEALTH CHECK ====================

@router.get("/data-source-status")
async def get_data_source_status():
    """
    Get the status of all data sources used by ARGUS.

    Returns detailed status including:
    - Tradier API connection status and any errors
    - ARGUS engine availability
    - VIX data source status
    - Database connection status

    This endpoint helps diagnose why data may be unavailable.
    """
    import os
    from data.vix_fetcher import get_vix_price

    result = {
        "success": True,
        "timestamp": format_central_timestamp(),
        "data_sources": {}
    }

    # Check Tradier status
    tradier_status = get_tradier_status()
    result["data_sources"]["tradier"] = tradier_status

    # Check ARGUS engine
    engine = get_engine()
    result["data_sources"]["argus_engine"] = {
        "module_available": ARGUS_AVAILABLE,
        "instance_available": engine is not None,
        "status": "available" if engine else "unavailable"
    }

    # Check VIX data source
    try:
        vix = get_vix_price()
        result["data_sources"]["vix"] = {
            "status": "available" if vix and vix > 0 else "unavailable",
            "last_value": vix if vix else None
        }
    except Exception as e:
        result["data_sources"]["vix"] = {
            "status": "error",
            "error": str(e)
        }

    # Check database connection
    try:
        conn = get_connection()
        if conn:
            conn.close()
            result["data_sources"]["database"] = {"status": "connected"}
        else:
            result["data_sources"]["database"] = {"status": "disconnected"}
    except Exception as e:
        result["data_sources"]["database"] = {
            "status": "error",
            "error": str(e)
        }

    # Overall status
    all_ok = (
        tradier_status.get("is_connected", False) and
        engine is not None
    )
    result["overall_status"] = "healthy" if all_ok else "degraded"

    if not all_ok:
        issues = []
        if not tradier_status.get("is_connected"):
            issues.append(f"Tradier: {tradier_status.get('last_error', 'Not configured')}")
        if not engine:
            issues.append("ARGUS engine not available")
        result["issues"] = issues

    return result


@router.get("/test-tradier-connection")
async def test_tradier_connection():
    """
    Test the Tradier API connection by fetching a SPY quote.

    This is a diagnostic endpoint to verify Tradier credentials are working.
    """
    tradier = get_tradier()

    if not tradier:
        return {
            "success": False,
            "connected": False,
            "error": _tradier_init_error or "Tradier client not initialized",
            "recommendation": "Check TRADIER_API_KEY and TRADIER_ACCOUNT_ID environment variables",
            "timestamp": format_central_timestamp()
        }

    try:
        # Try to fetch a quote
        quote = tradier.get_quote("SPY")

        if not quote:
            return {
                "success": False,
                "connected": True,
                "error": "Empty response from Tradier API",
                "timestamp": format_central_timestamp()
            }

        price = quote.get("last") or quote.get("close", 0)

        return {
            "success": True,
            "connected": True,
            "mode": "SANDBOX" if tradier.sandbox else "PRODUCTION",
            "test_quote": {
                "symbol": "SPY",
                "price": price,
                "bid": quote.get("bid"),
                "ask": quote.get("ask"),
                "volume": quote.get("volume")
            },
            "timestamp": format_central_timestamp()
        }

    except Exception as e:
        return {
            "success": False,
            "connected": True,
            "error": f"API call failed: {str(e)}",
            "timestamp": format_central_timestamp()
        }
