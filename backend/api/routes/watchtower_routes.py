"""
WATCHTOWER (0DTE Gamma Live) API Routes
====================================

API endpoints for the WATCHTOWER real-time 0DTE gamma visualization system.
Provides gamma data, probabilities, alerts, commentary, and historical replay.

WATCHTOWER - Named after the "all-seeing" giant with 100 eyes from Greek mythology.
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

router = APIRouter(prefix="/api/watchtower", tags=["WATCHTOWER"])
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

# ==================== DAILY RESET ====================
# Track last reset date to ensure smoothing state is fresh each day
_last_reset_date: Optional[date] = None


def check_daily_reset():
    """
    Check if we need to reset gamma smoothing state for a new trading day.

    This ensures the smoothing windows and baselines are fresh at market open,
    preventing stale data from previous day affecting today's calculations.
    """
    global _last_reset_date

    if not ARGUS_AVAILABLE:
        return

    today = get_central_time().date()
    now = get_central_time()

    # Reset at or after market open (8:30 AM CT) if not already reset today
    market_open = now.replace(hour=8, minute=30, second=0, microsecond=0)

    if now >= market_open and _last_reset_date != today:
        try:
            engine = get_watchtower_engine()
            engine.reset_gamma_smoothing()
            engine.reset_expected_move_smoothing()
            _last_reset_date = today
            logger.info(f"WATCHTOWER: Daily reset completed for {today}")
        except Exception as e:
            logger.error(f"WATCHTOWER: Failed daily reset: {e}")


# Try to import WATCHTOWER engine
ARGUS_AVAILABLE = False
try:
    from core.watchtower_engine import get_watchtower_engine, WatchtowerEngine
    ARGUS_AVAILABLE = True
except ImportError as e:
    logger.warning(f"WATCHTOWER engine not available: {e}")

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


# Initialize WATCHTOWER database tables on module load
# This runs once when the routes module is imported
_tables_initialized = False


# ==================== ROC HISTORY PERSISTENCE ====================
# Persist gamma history to database for ROC calculation continuity

_history_loaded: Dict[str, bool] = {}  # Track if we've loaded history from DB per symbol


def ensure_all_argus_tables():
    """Create all Watchtower tables if they don't exist"""
    conn = None
    cursor = None
    try:
        conn = get_connection()
        if not conn:
            return False
        cursor = conn.cursor()

        # 1. watchtower_gamma_history - per-strike gamma tracking
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS watchtower_gamma_history (
                id SERIAL PRIMARY KEY,
                symbol VARCHAR(10) NOT NULL DEFAULT 'SPY',
                strike DECIMAL(10, 2) NOT NULL,
                gamma_value DECIMAL(20, 8) NOT NULL,
                recorded_at TIMESTAMP WITH TIME ZONE NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_watchtower_gamma_history_strike_time
            ON watchtower_gamma_history(symbol, strike, recorded_at DESC)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_watchtower_gamma_history_recorded_at
            ON watchtower_gamma_history(recorded_at)
        """)

        # 2. watchtower_snapshots - market structure snapshots
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS watchtower_snapshots (
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
            CREATE INDEX IF NOT EXISTS idx_watchtower_snapshots_symbol_time
            ON watchtower_snapshots(symbol, snapshot_time DESC)
        """)

        # 3. watchtower_alerts - triggered alerts
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS watchtower_alerts (
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
            CREATE INDEX IF NOT EXISTS idx_watchtower_alerts_triggered_at
            ON watchtower_alerts(triggered_at DESC)
        """)

        # 4. watchtower_danger_zone_logs - danger zone tracking
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS watchtower_danger_zone_logs (
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
            CREATE INDEX IF NOT EXISTS idx_watchtower_danger_zone_detected_at
            ON watchtower_danger_zone_logs(detected_at DESC)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_watchtower_danger_zone_active
            ON watchtower_danger_zone_logs(is_active, strike)
        """)

        # 5. watchtower_pin_predictions - pin strike predictions for accuracy tracking
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS watchtower_pin_predictions (
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
            CREATE INDEX IF NOT EXISTS idx_watchtower_pin_predictions_date
            ON watchtower_pin_predictions(symbol, prediction_date DESC)
        """)

        # 6. watchtower_accuracy - ML model accuracy metrics
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS watchtower_accuracy (
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
            CREATE INDEX IF NOT EXISTS idx_watchtower_accuracy_date
            ON watchtower_accuracy(metric_date DESC)
        """)

        # 7. watchtower_order_flow_history - bid/ask pressure tracking
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS watchtower_order_flow_history (
                id SERIAL PRIMARY KEY,
                symbol VARCHAR(10) NOT NULL DEFAULT 'SPY',
                recorded_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                spot_price DECIMAL(10, 2),
                -- Volume flow metrics
                net_gex_volume DECIMAL(12, 2),
                call_gex_flow DECIMAL(12, 2),
                put_gex_flow DECIMAL(12, 2),
                flow_direction VARCHAR(10),
                flow_strength VARCHAR(10),
                -- Bid/Ask pressure metrics (smoothed)
                net_pressure DECIMAL(6, 4),
                raw_pressure DECIMAL(6, 4),
                pressure_direction VARCHAR(10),
                pressure_strength VARCHAR(10),
                call_pressure DECIMAL(6, 4),
                put_pressure DECIMAL(6, 4),
                -- Depth metrics
                total_bid_size INTEGER,
                total_ask_size INTEGER,
                liquidity_score DECIMAL(5, 1),
                strikes_used INTEGER,
                -- Combined signal
                combined_signal VARCHAR(30),
                signal_confidence VARCHAR(10),
                is_valid BOOLEAN DEFAULT TRUE,
                -- Context
                gamma_regime VARCHAR(20),
                vix DECIMAL(6, 2)
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_argus_order_flow_recorded_at
            ON watchtower_order_flow_history(symbol, recorded_at DESC)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_argus_order_flow_signal
            ON watchtower_order_flow_history(combined_signal, signal_confidence)
        """)

        # 8. watchtower_trade_signals - Track generated trade recommendations and outcomes
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS watchtower_trade_signals (
                id SERIAL PRIMARY KEY,
                symbol VARCHAR(10) NOT NULL DEFAULT 'SPY',
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

                -- Signal details
                action VARCHAR(30) NOT NULL,
                direction VARCHAR(30),
                confidence INTEGER,
                trade_description TEXT,

                -- Trade structure (JSON for flexibility)
                trade_structure JSONB,

                -- Pricing at signal time
                spot_at_signal DECIMAL(10, 2),
                credit_target DECIMAL(6, 2),

                -- Strikes
                short_strike DECIMAL(10, 2),
                long_strike DECIMAL(10, 2),
                put_short DECIMAL(10, 2),
                put_long DECIMAL(10, 2),
                call_short DECIMAL(10, 2),
                call_long DECIMAL(10, 2),

                -- Market context at signal time
                vix_at_signal DECIMAL(6, 2),
                gamma_regime VARCHAR(20),
                order_flow VARCHAR(30),
                flow_confidence VARCHAR(10),

                -- Sizing
                contracts INTEGER,
                max_profit DECIMAL(10, 2),
                max_loss DECIMAL(10, 2),

                -- Exit rules
                profit_target_price DECIMAL(6, 2),
                stop_loss_price DECIMAL(6, 2),

                -- Outcome tracking
                status VARCHAR(20) DEFAULT 'OPEN',  -- OPEN, WIN, LOSS, EXPIRED, CANCELLED
                outcome_reason VARCHAR(50),  -- profit_target, stop_loss, time_expired, manual
                closed_at TIMESTAMP WITH TIME ZONE,
                spot_at_close DECIMAL(10, 2),
                actual_pnl DECIMAL(10, 2),
                pnl_percent DECIMAL(6, 2),

                -- Analytics
                time_to_resolution INTEGER,  -- minutes from open to close
                hit_profit_target BOOLEAN,
                hit_stop_loss BOOLEAN,
                expired_in_profit BOOLEAN
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_watchtower_trade_signals_created
            ON watchtower_trade_signals(symbol, created_at DESC)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_watchtower_trade_signals_status
            ON watchtower_trade_signals(status, created_at DESC)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_watchtower_trade_signals_action
            ON watchtower_trade_signals(action, status)
        """)

        conn.commit()
        logger.info("WATCHTOWER: All tables ensured (8 tables)")
        return True
    except Exception as e:
        logger.error(f"Failed to create WATCHTOWER tables: {e}")
        return False
    finally:
        if cursor:
            try:
                cursor.close()
            except:
                pass
        if conn:
            try:
                conn.close()
            except:
                pass


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

    conn = None
    cursor = None
    try:
        conn = get_connection()
        if not conn:
            return

        cursor = conn.cursor()
        ensure_gamma_history_table()

        # Get the most recent timestamp we have in DB for this symbol
        cursor.execute("""
            SELECT MAX(recorded_at) FROM watchtower_gamma_history WHERE symbol = %s
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
                    INSERT INTO watchtower_gamma_history (symbol, strike, gamma_value, recorded_at)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT DO NOTHING
                """, (symbol, strike, gamma_value, recorded_time))
                inserted += 1

        conn.commit()

        if inserted > 0:
            logger.debug(f"WATCHTOWER: Persisted {inserted} gamma history entries for {symbol}")
    except Exception as e:
        logger.warning(f"Failed to persist gamma history: {e}")
    finally:
        if cursor:
            try:
                cursor.close()
            except:
                pass
        if conn:
            try:
                conn.close()
            except:
                pass


def load_gamma_history(engine, symbol: str = "SPY"):
    """
    Load gamma history from database into engine.
    Called on engine startup to restore ROC calculation capability.
    """
    global _history_loaded

    if not engine:
        return

    if _history_loaded.get(symbol, False):
        logger.debug(f"WATCHTOWER: Gamma history already loaded for {symbol}, skipping")
        return

    conn = None
    cursor = None
    rows = []
    try:
        conn = get_connection()
        if not conn:
            return

        cursor = conn.cursor()
        ensure_gamma_history_table()

        # Load full trading day of history (7 hours = 420 minutes to support all ROC timeframes)
        cursor.execute("""
            SELECT strike, gamma_value, recorded_at
            FROM watchtower_gamma_history
            WHERE symbol = %s
            AND recorded_at > NOW() - INTERVAL '420 minutes'
            ORDER BY strike, recorded_at ASC
        """, (symbol,))

        rows = cursor.fetchall()
    except Exception as e:
        logger.warning(f"Failed to load gamma history: {e}")
        _history_loaded[symbol] = True  # Prevent repeated failures
        return
    finally:
        if cursor:
            try:
                cursor.close()
            except:
                pass
        if conn:
            try:
                conn.close()
            except:
                pass

    if not rows:
        logger.debug(f"WATCHTOWER: No recent gamma history found for {symbol}")
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
    logger.info(f"WATCHTOWER: Loaded gamma history for {symbol}: {unique_strikes} strikes, {total_entries} entries")


def cleanup_old_gamma_history():
    """
    Clean up gamma history older than 8 hours.
    Called periodically to prevent table bloat.
    Keeps full trading day data for ROC calculations.
    """
    conn = None
    cursor = None
    try:
        conn = get_connection()
        if not conn:
            return

        cursor = conn.cursor()
        cursor.execute("""
            DELETE FROM watchtower_gamma_history
            WHERE recorded_at < NOW() - INTERVAL '8 hours'
        """)
        deleted = cursor.rowcount
        conn.commit()

        if deleted > 0:
            logger.debug(f"WATCHTOWER: Cleaned up {deleted} old gamma history entries")
    except Exception as e:
        logger.warning(f"Failed to cleanup gamma history: {e}")
    finally:
        if cursor:
            try:
                cursor.close()
            except:
                pass
        if conn:
            try:
                conn.close()
            except:
                pass


def get_engine() -> Optional[WatchtowerEngine]:
    """Get the WATCHTOWER engine instance"""
    global _tables_initialized
    if not ARGUS_AVAILABLE:
        return None
    try:
        # Ensure database tables exist on first call
        if not _tables_initialized:
            ensure_all_argus_tables()
            _tables_initialized = True
        return get_watchtower_engine()
    except Exception as e:
        logger.error(f"Failed to get WATCHTOWER engine: {e}")
        return None


# Store the last Tradier initialization error for diagnostic purposes
_tradier_init_error: Optional[str] = None
# Cache the Tradier instance to avoid repeated initialization
_tradier_instance: Optional[Any] = None


def get_tradier():
    """
    Get the Tradier data fetcher instance.

    Uses the same pattern as FORTRESS: explicitly gets credentials from APIConfig
    and tries sandbox mode first (for market data), then production.

    This fixes the bug where WATCHTOWER defaulted to production mode but credentials
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

        # Try sandbox credentials first (like FORTRESS does for market data)
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
                logger.info("WATCHTOWER: Tradier initialized with SANDBOX credentials")
                return fetcher
            except Exception as e:
                logger.warning(f"WATCHTOWER: Sandbox credentials failed: {e}")

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
                logger.info("WATCHTOWER: Tradier initialized with PRODUCTION credentials")
                return fetcher
            except Exception as e:
                logger.warning(f"WATCHTOWER: Production credentials failed: {e}")

        # No valid credentials found
        _tradier_init_error = "No valid Tradier credentials found in APIConfig (checked TRADIER_SANDBOX_*, TRADIER_PROD_*, and TRADIER_*)"
        logger.error(f"WATCHTOWER: {_tradier_init_error}")
        return None

    except ImportError as e:
        _tradier_init_error = f"Failed to import unified_config: {e}"
        logger.error(f"WATCHTOWER: {_tradier_init_error}")
        return None
    except Exception as e:
        _tradier_init_error = f"Unexpected error: {type(e).__name__}: {e}"
        logger.error(f"WATCHTOWER: Failed to get Tradier fetcher: {e}")
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
    # When market is closed, use INFINITE cache - data MUST NOT change after hours
    market_open = is_market_hours()
    cache_key = f"gamma_data_{symbol}_{expiration or 'today'}"

    if not market_open:
        # AFTER-HOURS: Serve frozen data, never re-fetch from Tradier
        cached = get_cached(cache_key, 999999)  # Effectively infinite TTL
        if cached and not cached.get('is_mock', False):
            logger.debug(f"WATCHTOWER: After-hours - returning frozen cached data for {expiration or 'today'}")
            return cached
        # No cache exists - fall through to fetch ONCE, then cache indefinitely
        logger.info(f"WATCHTOWER: After-hours but no cache exists - fetching once to populate cache")
    else:
        # Market open: 30s cache
        cached = get_cached(cache_key, CACHE_TTL_SECONDS)
        if cached and not cached.get('is_mock', False):
            logger.debug(f"WATCHTOWER: Returning cached data for {expiration or 'today'} (market_open={market_open})")
            return cached
        elif cached and cached.get('is_mock', False):
            logger.debug(f"WATCHTOWER: Skipping cached mock data, attempting fresh fetch")

    tradier = get_tradier()
    if not tradier:
        # Get specific error for better diagnostics
        error_detail = _tradier_init_error or 'Unknown initialization error'
        logger.warning(f"WATCHTOWER: Tradier API not available - {error_detail}")
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
        logger.info(f"WATCHTOWER: {symbol} quote fetched, price=${spot_price}")

        # Get VIX - use reliable vix_fetcher (NO FAKE FALLBACKS)
        from data.vix_fetcher import get_vix_price
        vix = get_vix_price()
        logger.info(f"WATCHTOWER: VIX fetched, value={vix}")

        # Get expiration (default to 0DTE)
        engine = get_engine()
        if not expiration and engine:
            expiration = engine.get_0dte_expiration()
        logger.info(f"WATCHTOWER: Using expiration={expiration}")

        # Get options chain (synchronous method, returns OptionChain dataclass)
        option_chain = tradier.get_option_chain(symbol, expiration)

        # OptionChain.chains is Dict[expiration, List[OptionContract]]
        # Get contracts for the requested expiration
        contracts = option_chain.chains.get(expiration, [])
        options_count = len(contracts)
        logger.info(f"WATCHTOWER: Options chain fetched, {options_count} contracts for {expiration}")

        # If no options (market closed/weekend), return unavailable status
        if options_count == 0:
            logger.warning("WATCHTOWER: No options data available (market likely closed)")
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

        # Get unique strikes - SORTED for deterministic output
        # Using sorted() instead of set() ensures consistent strike ordering across requests
        unique_strike_values = sorted(set(contract.strike for contract in contracts if contract.strike))

        # Build strike data using O(1) lookups (ordered by strike price)
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
                'volume': (call_contract.volume if call_contract else 0) + (put_contract.volume if put_contract else 0),
                'call_volume': call_contract.volume if call_contract else 0,  # Separate for GEX flow
                'put_volume': put_contract.volume if put_contract else 0,     # Separate for GEX flow
                # Bid/ask size for order flow pressure analysis
                'call_bid_size': call_contract.bid_size if call_contract else 0,
                'call_ask_size': call_contract.ask_size if call_contract else 0,
                'put_bid_size': put_contract.bid_size if put_contract else 0,
                'put_ask_size': put_contract.ask_size if put_contract else 0
            }

        # Record the actual data fetch time
        data_fetch_time = format_central_timestamp()

        result = {
            'symbol': symbol,
            'spot_price': spot_price,
            'vix': vix,
            'expiration': expiration,
            'strikes': sorted(unique_strikes.values(), key=lambda s: s['strike']),  # Deterministic sort by strike
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
    # Check if we need to reset smoothing state for new trading day
    check_daily_reset()

    engine = get_engine()
    if not engine:
        raise HTTPException(status_code=503, detail="WATCHTOWER engine not available")

    # Load persisted gamma history from database for ROC continuity
    # This ensures ROC values persist across page navigation and server restarts
    load_gamma_history(engine, symbol)

    try:
        # Determine expiration
        # Day names that need to be converted to dates
        day_names = {'mon', 'tue', 'wed', 'thu', 'fri', 'today'}

        if day:
            expiration = engine.get_0dte_expiration(day)
        elif expiration and expiration.lower() in day_names:
            # Frontend sent day name as expiration - convert it to a date
            expiration = engine.get_0dte_expiration(expiration.lower())
        elif not expiration:
            expiration = engine.get_0dte_expiration('today')

        # Fetch raw data
        raw_data = await fetch_gamma_data(symbol, expiration)

        # Check if data is unavailable (API error, market closed, etc.)
        if raw_data.get('data_unavailable'):
            logger.warning(f"WATCHTOWER: Data unavailable - {raw_data.get('reason', 'unknown')}")
            return {
                "success": False,
                "data_unavailable": True,
                "reason": raw_data.get('reason', 'Data unavailable'),
                "message": raw_data.get('message', 'Unable to fetch gamma data'),
                "symbol": symbol,
                "expiration_date": expiration,
                "fetched_at": raw_data.get('fetched_at', format_central_timestamp())
            }

        # GAP FIX: Validate spot_price before proceeding
        # If spot_price is 0 or invalid, ATM calculations will fail (any strike would be "ATM")
        spot_price = raw_data.get('spot_price', 0)
        use_previous_due_to_invalid_price = False
        if not spot_price or spot_price <= 0:
            logger.warning(f"WATCHTOWER: Invalid spot price ({spot_price}) - cannot calculate ATM range")
            # Try to use previous snapshot if available
            if engine.previous_snapshot and engine.previous_snapshot.spot_price > 0:
                logger.info("WATCHTOWER: Using previous snapshot due to invalid spot price")
                snapshot = engine.previous_snapshot
                use_previous_due_to_invalid_price = True
                # Update raw_data for downstream functions that use it
                raw_data['spot_price'] = snapshot.spot_price
                raw_data['vix'] = snapshot.vix
            else:
                return {
                    "success": False,
                    "data_unavailable": True,
                    "reason": "Invalid spot price",
                    "message": f"Spot price is invalid ({spot_price}). Market data may be unavailable.",
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

        # Skip re-processing if we already used previous snapshot due to invalid spot price
        if use_previous_due_to_invalid_price:
            # Already set snapshot above, skip processing
            # Treat as cached to prevent smoothing updates and database persistence
            is_cached = True
            logger.debug("WATCHTOWER: Skipping re-processing, using previous snapshot due to invalid spot price")
        elif not market_open and engine.previous_snapshot:
            # Market closed - use existing snapshot, don't reprocess
            # Also freeze VIX from the snapshot for complete consistency
            is_cached = True
            logger.debug(f"WATCHTOWER: Market closed - using frozen snapshot to prevent data changes")
            snapshot = engine.previous_snapshot
            raw_data['vix'] = snapshot.vix  # Use snapshot VIX, not fresh Tradier VIX
        elif not market_open and not engine.previous_snapshot:
            # Market closed, no previous snapshot (server just restarted)
            # Process once to populate engine state, then treat as cached
            logger.info(f"WATCHTOWER: Market closed, no snapshot - processing once to initialize")
            snapshot = engine.process_options_chain(
                raw_data,
                raw_data['spot_price'],
                raw_data['vix'],
                expiration
            )
            is_cached = True  # Prevent DB persistence of after-hours data
        elif is_cached and engine.previous_snapshot:
            # Use existing snapshot - don't reprocess cached data
            logger.debug(f"WATCHTOWER: Using existing snapshot (cached data, age={cache_age_seconds}s)")
            snapshot = engine.previous_snapshot
        else:
            # Process fresh data through engine
            logger.debug(f"WATCHTOWER: Processing fresh data through engine (market_open={market_open})")
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

        # Use snapshot VIX for EM change calculation to ensure consistency
        # This prevents VIX fluctuations from affecting the response when using cached snapshots
        effective_vix = snapshot.vix if is_cached else raw_data['vix']

        # Get expected move change data (pass spot_price to normalize for overnight gaps)
        em_change = await get_expected_move_change(snapshot.expected_move, effective_vix, snapshot.spot_price)

        # Extract flip_point, call_wall, put_wall from snapshot strikes for structure analysis
        current_flip_point = None
        current_call_wall = None
        current_put_wall = None

        if snapshot.strikes:
            # Find flip point (where gamma crosses zero) - find ALL sign changes and pick closest to spot
            all_flip_points = []
            for i, strike in enumerate(snapshot.strikes[:-1]):
                if hasattr(strike, 'net_gamma'):
                    curr_gamma = strike.net_gamma
                    next_strike = snapshot.strikes[i + 1]
                    next_gamma = next_strike.net_gamma if hasattr(next_strike, 'net_gamma') else 0
                    if curr_gamma * next_gamma < 0:  # Sign change
                        # Linear interpolation for more precise flip point
                        if curr_gamma != next_gamma:
                            ratio = abs(curr_gamma) / (abs(curr_gamma) + abs(next_gamma))
                            flip_pt = strike.strike + ratio * (next_strike.strike - strike.strike)
                        else:
                            flip_pt = strike.strike
                        all_flip_points.append(flip_pt)

            # Select flip point closest to current spot price
            if all_flip_points:
                current_flip_point = min(all_flip_points, key=lambda fp: abs(fp - snapshot.spot_price))

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
            current_vix=effective_vix,
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

            # Persist WATCHTOWER snapshot for prior day market structure comparisons
            await persist_watchtower_snapshot_to_db(
                symbol=symbol,
                expiration_date=expiration,
                spot_price=snapshot.spot_price,
                expected_move=snapshot.expected_move,
                vix=effective_vix,
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
                    vix=effective_vix,
                    confidence=snapshot.pin_probability * 100  # Convert to percentage
                )

        # Generate actionable trading signal based on gamma evolution
        trading_signal = engine.generate_trading_signal(
            filtered_strikes,
            snapshot.spot_price,
            snapshot.likely_pin,
            snapshot.gamma_regime
        )

        # Order flow is now calculated in process_options_chain() and stored in snapshot
        # This provides signal confirmation based on volume-weighted gamma flow + bid/ask pressure
        order_flow = snapshot.order_flow

        # Persist order flow data for historical analysis (only for fresh data)
        if not is_cached and order_flow:
            await persist_order_flow_to_db(
                symbol=symbol,
                spot_price=snapshot.spot_price,
                order_flow=order_flow,
                gamma_regime=snapshot.gamma_regime,
                vix=effective_vix
            )

        # Determine if data is frozen (after-hours, using cached snapshot)
        is_frozen = not market_open and is_cached

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
                "is_frozen": is_frozen,  # True when after-hours data is frozen (will not change)
                "cache_age_seconds": cache_age_seconds,  # How old the cached data is
                "fetched_at": raw_data.get('fetched_at', format_central_timestamp()),  # When data was fetched from Tradier (Central TZ)
                "data_timestamp": raw_data.get('data_timestamp', raw_data.get('fetched_at', format_central_timestamp())),  # Original data fetch time
                "strikes": [s.to_dict() for s in filtered_strikes],
                "magnets": snapshot.magnets,
                "likely_pin": snapshot.likely_pin,
                "pin_probability": snapshot.pin_probability,
                "danger_zones": snapshot.danger_zones,
                "gamma_flips": snapshot.gamma_flips,
                "pinning_status": snapshot.pinning_status,
                "trading_signal": trading_signal,  # Actionable trading guidance based on gamma evolution
                "order_flow": order_flow  # Bid/ask pressure analysis for signal confirmation
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
            logger.debug("WATCHTOWER: Returning cached expected move change")
            return _em_result_cache[cache_key]

    # Try to get prior day's close expected move AND spot from database
    prior_em = None
    prior_spot = None
    open_em = None
    open_spot = None

    conn = None
    cursor = None
    try:
        conn = get_connection()
        if conn:
            cursor = conn.cursor()

            # Get yesterday's final expected move AND spot price
            cursor.execute("""
                SELECT expected_move, spot_price
                FROM watchtower_snapshots
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
                FROM watchtower_snapshots
                WHERE DATE(snapshot_time) = CURRENT_DATE
                ORDER BY snapshot_time ASC
                LIMIT 1
            """)
            row = cursor.fetchone()
            if row:
                open_em = float(row[0])
                open_spot = float(row[1]) if row[1] else None
    except Exception as e:
        logger.warning(f"Could not fetch prior expected move: {e}")
    finally:
        if cursor:
            try:
                cursor.close()
            except:
                pass
        if conn:
            try:
                conn.close()
            except:
                pass

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

    conn = None
    cursor = None
    try:
        conn = get_connection()
        if conn:
            cursor = conn.cursor()

            # Get yesterday's closing data from watchtower_snapshots
            cursor.execute("""
                SELECT spot_price, expected_move
                FROM watchtower_snapshots
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
                # If we didn't get prior_spot from watchtower_snapshots, use gex_history
                if prior_spot is None and row[3]:
                    prior_spot = float(row[3])
    except Exception as e:
        logger.warning(f"Could not fetch prior day structure: {e}")
    finally:
        if cursor:
            try:
                cursor.close()
            except:
                pass
        if conn:
            try:
                conn.close()
            except:
                pass

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


# =============================================================================
# OPTIONS FLOW DIAGNOSTICS - Trading Volatility Style
# =============================================================================

@router.get("/flow-diagnostics")
async def get_flow_diagnostics(
    symbol: str = Query("SPY", description="Symbol (SPY, SPX, QQQ, IWM, DIA, GLD, etc.)"),
    expiration: Optional[str] = Query(None, description="Expiration date YYYY-MM-DD")
):
    """
    Get Trading Volatility-style Options Flow Diagnostics.

    Returns 6 diagnostic cards analyzing options flow:
    1. Call vs Put Volume Pressure
    2. Short-DTE Call Share
    3. Call Share of Options Flow
    4. Lotto Turnover vs Open Interest
    5. Far-OTM Call Share
    6. Lotto Share of Call Tape

    Plus:
    - Call Structure Classification (Hedging/Overwrite/Speculation)
    - Skew Measures (Skew Ratio, Call Skew)
    - Overall Rating (BULLISH/BEARISH/NEUTRAL)
    - Net GEX estimate
    """
    engine = get_engine()
    if not engine:
        raise HTTPException(status_code=503, detail="WATCHTOWER engine not available")

    try:
        # Determine expiration
        if not expiration:
            expiration = engine.get_0dte_expiration('today')

        # Fetch raw data
        raw_data = await fetch_gamma_data(symbol, expiration)

        if raw_data.get('data_unavailable'):
            return {
                "success": False,
                "data_unavailable": True,
                "reason": raw_data.get('reason', 'Data unavailable'),
                "message": raw_data.get('message', 'Unable to fetch options data')
            }

        spot_price = raw_data.get('spot_price', 0)
        vix = raw_data.get('vix', 0)

        if spot_price <= 0:
            return {
                "success": False,
                "data_unavailable": True,
                "reason": "Invalid spot price",
                "message": "Cannot calculate diagnostics without valid spot price"
            }

        # Process the options chain to get strike data
        # After hours: reuse existing snapshot to prevent engine state mutation
        market_open = is_market_hours()
        if not market_open and engine.previous_snapshot:
            snapshot = engine.previous_snapshot
        else:
            snapshot = engine.process_options_chain(
                raw_data,
                spot_price,
                vix,
                expiration
            )

        # Calculate flow diagnostics
        diagnostics = engine.calculate_options_flow_diagnostics(
            strikes=snapshot.strikes,
            spot_price=spot_price,
            expected_move=snapshot.expected_move
        )

        # Add header metrics like Trading Volatility
        header_metrics = {
            'price': round(spot_price, 2),
            'gex_flip': None,  # Will be calculated from strikes
            '30_day_vol': round(vix, 1) if vix else None,
            'call_structure': diagnostics['call_structure']['structure'],
            'gex_at_expiration': diagnostics['summary']['net_gex'],
            'net_gex': diagnostics['summary']['net_gex'],
            'rating': diagnostics['rating']['rating'],
            'gamma_form': snapshot.gamma_regime,
            'is_frozen': not market_open  # Signal to frontend that data is frozen
        }

        # Find GEX flip point from strikes
        if snapshot.strikes:
            for i, strike in enumerate(snapshot.strikes[:-1]):
                curr_gamma = strike.net_gamma
                next_gamma = snapshot.strikes[i + 1].net_gamma if i + 1 < len(snapshot.strikes) else 0
                if curr_gamma * next_gamma < 0:
                    # Interpolate flip point
                    if curr_gamma != next_gamma:
                        ratio = abs(curr_gamma) / (abs(curr_gamma) + abs(next_gamma))
                        header_metrics['gex_flip'] = round(strike.strike + ratio * (snapshot.strikes[i + 1].strike - strike.strike), 2)
                    else:
                        header_metrics['gex_flip'] = strike.strike
                    break

        # Build strike data for GEX chart (similar to Trading Volatility)
        gex_chart_data = []
        for s in snapshot.strikes:
            gex_chart_data.append({
                'strike': s.strike,
                'net_gamma': s.net_gamma,
                'call_gamma': s.call_gamma,
                'put_gamma': s.put_gamma,
                'call_volume': s.call_volume,
                'put_volume': s.put_volume,
                'call_iv': round(s.call_iv * 100, 1) if s.call_iv else None,
                'put_iv': round(s.put_iv * 100, 1) if s.put_iv else None
            })

        # Calculate ±1 standard deviation bounds
        em = snapshot.expected_move
        upper_1sd = round(spot_price + em, 2) if em else None
        lower_1sd = round(spot_price - em, 2) if em else None

        return {
            "success": True,
            "data": {
                "symbol": symbol,
                "expiration": expiration,
                "timestamp": format_central_timestamp(),
                "header_metrics": header_metrics,
                "diagnostics": diagnostics['diagnostics'],
                "call_structure": diagnostics['call_structure'],
                "skew_measures": diagnostics['skew_measures'],
                "rating": diagnostics['rating'],
                "summary": diagnostics['summary'],
                "chart_data": {
                    "strikes": gex_chart_data,
                    "price": spot_price,
                    "upper_1sd": upper_1sd,
                    "lower_1sd": lower_1sd,
                    "gex_flip": header_metrics['gex_flip'],
                    "expected_move": em
                }
            }
        }

    except Exception as e:
        logger.error(f"Error getting flow diagnostics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/gex-analysis")
async def get_gex_analysis(
    symbol: str = Query("SPY", description="Symbol (SPY, SPX, QQQ, IWM, DIA, GLD, etc.)"),
    expiration: Optional[str] = Query(None, description="Specific expiration YYYY-MM-DD (optional)")
):
    """
    Comprehensive GEX analysis similar to Trading Volatility.

    Returns:
    - Header metrics (price, GEX flip, 30-day vol, structure, rating)
    - Options Flow Diagnostics (6 cards)
    - Skew Measures
    - GEX by strike for both specific expiration and all expirations
    - Key levels (±1σ, flip point, call/put walls)
    """
    engine = get_engine()
    if not engine:
        raise HTTPException(status_code=503, detail="WATCHTOWER engine not available")

    try:
        # Determine expiration
        target_expiration = expiration
        if not target_expiration:
            target_expiration = engine.get_0dte_expiration('today')

        # Fetch data for specific expiration
        raw_data = await fetch_gamma_data(symbol, target_expiration)

        if raw_data.get('data_unavailable'):
            return {
                "success": False,
                "data_unavailable": True,
                "reason": raw_data.get('reason', 'Data unavailable'),
                "message": raw_data.get('message', 'Unable to fetch options data'),
                "symbol": symbol
            }

        spot_price = raw_data.get('spot_price', 0)
        vix = raw_data.get('vix', 0)

        if spot_price <= 0:
            return {
                "success": False,
                "data_unavailable": True,
                "reason": "Invalid spot price",
                "message": "Cannot calculate GEX without valid spot price"
            }

        # Process the options chain
        # After hours: reuse existing snapshot to prevent engine state mutation
        market_open = is_market_hours()
        if not market_open and engine.previous_snapshot:
            snapshot = engine.previous_snapshot
        else:
            snapshot = engine.process_options_chain(
                raw_data,
                spot_price,
                vix,
                target_expiration
            )

        # Calculate flow diagnostics
        diagnostics = engine.calculate_options_flow_diagnostics(
            strikes=snapshot.strikes,
            spot_price=spot_price,
            expected_move=snapshot.expected_move
        )

        # Find key levels
        flip_point = None
        call_wall = None
        put_wall = None
        max_call_gamma_strike = None
        max_put_gamma_strike = None
        max_call_gamma = 0
        max_put_gamma = 0

        if snapshot.strikes:
            # Find flip point
            for i, strike in enumerate(snapshot.strikes[:-1]):
                curr_gamma = strike.net_gamma
                next_gamma = snapshot.strikes[i + 1].net_gamma
                if curr_gamma * next_gamma < 0:
                    ratio = abs(curr_gamma) / (abs(curr_gamma) + abs(next_gamma)) if curr_gamma != next_gamma else 0.5
                    flip_point = round(strike.strike + ratio * (snapshot.strikes[i + 1].strike - strike.strike), 2)
                    break

            # Find call and put walls
            for s in snapshot.strikes:
                if s.strike > spot_price and abs(s.net_gamma) > max_call_gamma:
                    max_call_gamma = abs(s.net_gamma)
                    call_wall = s.strike
                    max_call_gamma_strike = s
                if s.strike < spot_price and abs(s.net_gamma) > max_put_gamma:
                    max_put_gamma = abs(s.net_gamma)
                    put_wall = s.strike
                    max_put_gamma_strike = s

        # Expected move bounds
        em = snapshot.expected_move
        upper_1sd = round(spot_price + em, 2) if em else None
        lower_1sd = round(spot_price - em, 2) if em else None

        # Build GEX chart data
        gex_by_strike = []
        for s in snapshot.strikes:
            gex_by_strike.append({
                'strike': s.strike,
                'net_gamma': round(s.net_gamma, 4),
                'call_gamma': round(s.call_gamma, 6),
                'put_gamma': round(s.put_gamma, 6),
                'call_volume': s.call_volume,
                'put_volume': s.put_volume,
                'total_volume': s.volume,
                'call_iv': round(s.call_iv * 100, 1) if s.call_iv else None,
                'put_iv': round(s.put_iv * 100, 1) if s.put_iv else None
            })

        return {
            "success": True,
            "data": {
                "symbol": symbol,
                "timestamp": format_central_timestamp(),
                "expiration": target_expiration,

                # Header metrics (like Trading Volatility top bar)
                "header": {
                    "price": round(spot_price, 2),
                    "gex_flip": flip_point,
                    "30_day_vol": round(vix, 1) if vix else None,
                    "call_structure": diagnostics['call_structure']['structure'],
                    "gex_at_expiration": diagnostics['summary']['net_gex'],
                    "net_gex": diagnostics['summary']['net_gex'],
                    "rating": diagnostics['rating']['rating'],
                    "gamma_form": snapshot.gamma_regime
                },

                # Options Flow Diagnostics (6 cards)
                "flow_diagnostics": {
                    "cards": diagnostics['diagnostics'],
                    "note": "Volume-based metrics stabilize later in the session as trading activity accumulates"
                },

                # Skew Measures panel
                "skew_measures": diagnostics['skew_measures'],

                # Overall rating
                "rating": diagnostics['rating'],

                # Key levels
                "levels": {
                    "price": round(spot_price, 2),
                    "upper_1sd": upper_1sd,
                    "lower_1sd": lower_1sd,
                    "gex_flip": flip_point,
                    "call_wall": call_wall,
                    "put_wall": put_wall,
                    "expected_move": round(em, 2) if em else None
                },

                # GEX chart data
                "gex_chart": {
                    "expiration": target_expiration,
                    "strikes": gex_by_strike,
                    "total_net_gamma": snapshot.total_net_gamma,
                    "gamma_regime": snapshot.gamma_regime
                },

                # Summary stats
                "summary": diagnostics['summary']
            }
        }

    except Exception as e:
        logger.error(f"Error getting GEX analysis: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
        raise HTTPException(status_code=503, detail="WATCHTOWER engine not available")

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
        raise HTTPException(status_code=503, detail="WATCHTOWER engine not available")

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

    conn = None
    cursor = None
    try:
        conn = get_connection()
        if not conn:
            return

        cursor = conn.cursor()
        for alert in alerts:
            # Check if this exact alert already exists (avoid duplicates)
            cursor.execute("""
                SELECT id FROM watchtower_alerts
                WHERE alert_type = %s
                AND COALESCE(strike, 0) = COALESCE(%s, 0)
                AND triggered_at > NOW() - INTERVAL '2 minutes'
                LIMIT 1
            """, (alert.get('alert_type'), alert.get('strike')))

            if cursor.fetchone():
                continue  # Skip duplicate

            cursor.execute("""
                INSERT INTO watchtower_alerts
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
        logger.debug(f"Persisted {len(alerts)} alerts to database")
    except Exception as e:
        logger.warning(f"Failed to persist alerts: {e}")
    finally:
        if cursor:
            try:
                cursor.close()
            except:
                pass
        if conn:
            try:
                conn.close()
            except:
                pass


async def persist_danger_zones_to_db(danger_zones: list, spot_price: float, expiration: str):
    """Persist danger zones to database for history tracking"""
    conn = None
    cursor = None
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
                UPDATE watchtower_danger_zone_logs
                SET is_active = FALSE, resolved_at = NOW()
                WHERE is_active = TRUE
                AND strike NOT IN ({placeholders})
                AND detected_at > NOW() - INTERVAL '1 day'
                AND detected_at < NOW() - INTERVAL '5 minutes'
            """, active_strikes)
        else:
            # No active danger zones - mark as resolved (only if older than 5 minutes)
            cursor.execute("""
                UPDATE watchtower_danger_zone_logs
                SET is_active = FALSE, resolved_at = NOW()
                WHERE is_active = TRUE
                AND detected_at > NOW() - INTERVAL '1 day'
                AND detected_at < NOW() - INTERVAL '5 minutes'
            """)

        # Insert new danger zones
        for dz in (danger_zones or []):
            # Check if this danger zone is already logged and active
            cursor.execute("""
                SELECT id FROM watchtower_danger_zone_logs
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
                INSERT INTO watchtower_danger_zone_logs
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
        count = len(danger_zones) if danger_zones else 0
        logger.debug(f"Danger zone sync: {count} active, resolved inactive ones")
    except Exception as e:
        logger.warning(f"Failed to persist danger zones: {e}")
    finally:
        if cursor:
            try:
                cursor.close()
            except:
                pass
        if conn:
            try:
                conn.close()
            except:
                pass


async def persist_order_flow_to_db(
    symbol: str,
    spot_price: float,
    order_flow: dict,
    gamma_regime: str = None,
    vix: float = None
):
    """
    Persist order flow pressure data to database for historical analysis.

    Stores both volume flow and bid/ask pressure metrics for:
    - Historical pattern analysis
    - Signal accuracy tracking
    - Backtest validation
    - Divergence pattern research
    """
    conn = None
    cursor = None
    try:
        if not order_flow:
            return

        conn = get_connection()
        if not conn:
            return

        cursor = conn.cursor()

        # Only persist valid signals (or invalid ones for analysis)
        bid_ask = order_flow.get('bid_ask_pressure', {})

        # Check if we already have a reading in the last 30 seconds (prevent duplicates)
        cursor.execute("""
            SELECT id FROM watchtower_order_flow_history
            WHERE symbol = %s
            AND recorded_at > NOW() - INTERVAL '30 seconds'
            LIMIT 1
        """, (symbol,))

        if cursor.fetchone():
            return  # Already have a recent reading

        cursor.execute("""
            INSERT INTO watchtower_order_flow_history (
                symbol, recorded_at, spot_price,
                net_gex_volume, call_gex_flow, put_gex_flow,
                flow_direction, flow_strength,
                net_pressure, raw_pressure, pressure_direction, pressure_strength,
                call_pressure, put_pressure,
                total_bid_size, total_ask_size, liquidity_score, strikes_used,
                combined_signal, signal_confidence, is_valid,
                gamma_regime, vix
            ) VALUES (
                %s, NOW(), %s,
                %s, %s, %s,
                %s, %s,
                %s, %s, %s, %s,
                %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s
            )
        """, (
            symbol, spot_price,
            order_flow.get('net_gex_volume'),
            order_flow.get('call_gex_flow'),
            order_flow.get('put_gex_flow'),
            order_flow.get('flow_direction'),
            order_flow.get('flow_strength'),
            bid_ask.get('net_pressure'),
            bid_ask.get('raw_pressure'),
            bid_ask.get('pressure_direction'),
            bid_ask.get('pressure_strength'),
            bid_ask.get('call_pressure'),
            bid_ask.get('put_pressure'),
            bid_ask.get('total_bid_size'),
            bid_ask.get('total_ask_size'),
            bid_ask.get('liquidity_score'),
            bid_ask.get('strikes_used'),
            order_flow.get('combined_signal'),
            order_flow.get('signal_confidence'),
            bid_ask.get('is_valid', False),  # Default to False for safety
            gamma_regime,
            vix
        ))

        conn.commit()
        logger.debug(f"Order flow persisted: {order_flow.get('combined_signal')} ({order_flow.get('signal_confidence')})")
    except Exception as e:
        logger.warning(f"Failed to persist order flow: {e}")
    finally:
        # Always close cursor and connection to prevent leaks
        if cursor:
            try:
                cursor.close()
            except:
                pass
        if conn:
            try:
                conn.close()
            except:
                pass


async def persist_watchtower_snapshot_to_db(
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
    Persist WATCHTOWER snapshot to database for prior day comparisons.

    This enables the market structure signals to compare today vs prior day:
    - Flip point movement
    - Expected move bounds shift
    - Range width changes
    - GEX momentum
    """
    conn = None
    cursor = None
    try:
        conn = get_connection()
        if not conn:
            logger.warning("No database connection for WATCHTOWER snapshot persistence")
            return

        cursor = conn.cursor()

        # Check if we already have a snapshot for this minute (prevent duplicates)
        cursor.execute("""
            SELECT id FROM watchtower_snapshots
            WHERE symbol = %s
            AND snapshot_time > NOW() - INTERVAL '1 minute'
            LIMIT 1
        """, (symbol,))

        if cursor.fetchone():
            return  # Already have a recent snapshot

        # Insert new snapshot
        cursor.execute("""
            INSERT INTO watchtower_snapshots (
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
        logger.debug(f"WATCHTOWER snapshot persisted: {symbol} spot=${spot_price:.2f} EM=${expected_move:.2f}")

    except Exception as e:
        logger.warning(f"Failed to persist WATCHTOWER snapshot: {e}")
    finally:
        if cursor:
            try:
                cursor.close()
            except:
                pass
        if conn:
            try:
                conn.close()
            except:
                pass


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
    Persist WATCHTOWER pin prediction to database for accuracy tracking.

    Only stores ONE prediction per day (the first one made after market open).
    This ensures we track the "morning prediction" accuracy, not constantly
    updating predictions throughout the day.
    """
    conn = None
    cursor = None
    try:
        conn = get_connection()
        if not conn:
            logger.warning("No database connection for pin prediction persistence")
            return False

        cursor = conn.cursor()

        # Check if we already have a prediction for today
        cursor.execute("""
            SELECT id FROM watchtower_pin_predictions
            WHERE symbol = %s
            AND prediction_date = CURRENT_DATE
            LIMIT 1
        """, (symbol,))

        if cursor.fetchone():
            logger.debug(f"Pin prediction already exists for {symbol} today, skipping")
            return False  # Already have today's prediction

        # Insert new prediction
        cursor.execute("""
            INSERT INTO watchtower_pin_predictions (
                symbol, prediction_date, predicted_pin, gamma_regime, vix_at_prediction, confidence
            ) VALUES (%s, CURRENT_DATE, %s, %s, %s, %s)
        """, (symbol, predicted_pin, gamma_regime, vix, confidence))

        conn.commit()
        logger.info(f"WATCHTOWER pin prediction stored: {symbol} pin=${predicted_pin:.2f} ({confidence:.0f}% confidence)")
        return True

    except Exception as e:
        logger.warning(f"Failed to persist pin prediction: {e}")
        return False
    finally:
        if cursor:
            try:
                cursor.close()
            except:
                pass
        if conn:
            try:
                conn.close()
            except:
                pass


async def update_pin_prediction_with_actual_close(symbol: str = "SPY"):
    """
    Update today's pin prediction with actual closing price.

    Called at end of day (after 3:00 PM CT) to record the actual close
    so we can calculate prediction accuracy.
    """
    conn = None
    cursor = None
    try:
        conn = get_connection()
        if not conn:
            logger.warning("No database connection for pin prediction update")
            return False

        # Get today's actual closing price from the last snapshot
        cursor = conn.cursor()
        cursor.execute("""
            SELECT spot_price FROM watchtower_snapshots
            WHERE symbol = %s
            AND DATE(snapshot_time) = CURRENT_DATE
            ORDER BY snapshot_time DESC
            LIMIT 1
        """, (symbol,))

        row = cursor.fetchone()
        if not row:
            logger.warning(f"No snapshot found for {symbol} today, cannot update actual close")
            return False

        actual_close = float(row[0])

        # Update today's prediction with actual close
        cursor.execute("""
            UPDATE watchtower_pin_predictions
            SET actual_close = %s
            WHERE symbol = %s
            AND prediction_date = CURRENT_DATE
            AND actual_close IS NULL
        """, (actual_close, symbol))

        updated = cursor.rowcount
        conn.commit()

        if updated > 0:
            logger.info(f"WATCHTOWER pin prediction updated with actual close: {symbol} close=${actual_close:.2f}")
            return True
        else:
            logger.debug(f"No pin prediction to update for {symbol} today (already updated or none exists)")
            return False

    except Exception as e:
        logger.warning(f"Failed to update pin prediction with actual close: {e}")
        return False
    finally:
        if cursor:
            try:
                cursor.close()
            except:
                pass
        if conn:
            try:
                conn.close()
            except:
                pass


async def calculate_and_store_watchtower_accuracy():
    """
    Calculate and store WATCHTOWER prediction accuracy metrics.

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
            FROM watchtower_pin_predictions
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
            FROM watchtower_pin_predictions
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
            DELETE FROM watchtower_accuracy WHERE metric_date = CURRENT_DATE
        """)

        # Insert new accuracy record
        cursor.execute("""
            INSERT INTO watchtower_accuracy (
                metric_date, direction_accuracy_7d, direction_accuracy_30d,
                magnet_hit_rate_7d, magnet_hit_rate_30d, total_predictions
            ) VALUES (CURRENT_DATE, %s, %s, %s, %s, %s)
        """, (accuracy_7d, accuracy_30d, magnet_7d, magnet_30d, total_30d))

        conn.commit()
        cursor.close()
        conn.close()

        logger.info(f"WATCHTOWER accuracy metrics stored: 7d={accuracy_7d}%, 30d={accuracy_30d}%, total={total_30d}")
        return True

    except Exception as e:
        logger.warning(f"Failed to calculate/store WATCHTOWER accuracy: {e}")
        return False


@router.post("/eod-processing")
async def run_argus_eod_processing(symbol: str = Query(default="SPY")):
    """
    Run WATCHTOWER end-of-day processing.

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
        accuracy_stored = await calculate_and_store_watchtower_accuracy()
        results["actions"].append({
            "action": "calculate_accuracy",
            "success": accuracy_stored,
            "description": "Calculated and stored WATCHTOWER prediction accuracy metrics"
        })

        success = updated or accuracy_stored
        return {
            "success": success,
            "data": results
        }

    except Exception as e:
        logger.error(f"Error in WATCHTOWER EOD processing: {e}")
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
            FROM watchtower_alerts
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
            FROM watchtower_danger_zone_logs
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
            FROM watchtower_commentary
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
        raise HTTPException(status_code=503, detail="WATCHTOWER engine not available")

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
            from core.watchtower_commentary import generate_watchtower_commentary
            commentary = await generate_watchtower_commentary(snapshot)
        except ImportError:
            # Fallback if commentary module not ready
            commentary = generate_fallback_commentary(snapshot)

        # Store in database
        try:
            conn = get_connection()
            if conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO watchtower_commentary
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
    now = datetime.now(ZoneInfo("America/Chicago"))
    time_str = now.strftime("%I:%M %p CT")

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
    Get active bot positions for WATCHTOWER context.

    Shows what FORTRESS, SOLOMON, SAMSON, GIDEON, ANCHOR are doing relative to gamma structure.

    Returns BotPosition interface matching frontend:
    - bot: string (FORTRESS, SOLOMON, SAMSON, etc.)
    - strategy: string (Iron Condor, Directional Spread, etc.)
    - status: string (open, watching, closed)
    - strikes: string (format: "590/610" for IC, "595" for directional)
    - direction: string (BULLISH, BEARISH, NEUTRAL)
    - pnl: number (unrealized P&L for open, realized for closed)
    - safe: boolean (position within gamma walls)
    """
    try:
        positions = []

        # Check FORTRESS positions (Iron Condors - always NEUTRAL direction)
        try:
            from backend.api.routes.fortress_routes import get_fortress_positions
            fortress_data = await get_fortress_positions()
            if fortress_data.get('success') and fortress_data.get('data', {}).get('positions'):
                for pos in fortress_data['data']['positions']:
                    # Calculate P&L: For open ICs, estimate based on credit received
                    # Real P&L would require current option prices
                    pnl = pos.get('realized_pnl') or pos.get('max_profit', 0) * 0.3  # Estimate 30% of max for open
                    positions.append({
                        'bot': 'FORTRESS',
                        'strategy': 'Iron Condor',
                        'status': pos.get('status', 'open'),
                        'strikes': f"{pos.get('put_short_strike', 0):.0f}/{pos.get('call_short_strike', 0):.0f}",
                        'direction': 'NEUTRAL',  # Iron Condors are non-directional
                        'pnl': round(float(pnl), 2) if pnl else 0,
                        'safe': True  # Will be calculated based on magnets
                    })
        except Exception as e:
            logger.debug(f"Could not fetch FORTRESS positions: {e}")

        # Check SOLOMON positions (Directional spreads)
        try:
            from backend.api.routes.solomon_routes import get_solomon_positions
            solomon_data = await get_solomon_positions()
            if solomon_data.get('success') and solomon_data.get('data', {}).get('positions'):
                for pos in solomon_data['data']['positions']:
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
                        'bot': 'SOLOMON',
                        'strategy': pos.get('strategy', 'Directional Spread'),
                        'status': pos.get('status', 'open'),
                        'strikes': str(pos.get('strike', pos.get('short_strike', 'N/A'))),
                        'direction': direction,
                        'pnl': round(float(pnl), 2) if pnl else 0,
                        'safe': True
                    })
        except Exception as e:
            logger.debug(f"Could not fetch SOLOMON positions: {e}")

        # Check SAMSON positions (Aggressive Iron Condors on SPX)
        try:
            from backend.api.routes.samson_routes import get_samson_positions
            samson_data = await get_samson_positions()
            if samson_data.get('success') and samson_data.get('data', {}).get('positions'):
                for pos in samson_data['data']['positions']:
                    pnl = pos.get('realized_pnl') or pos.get('unrealized_pnl', 0)
                    positions.append({
                        'bot': 'SAMSON',
                        'strategy': 'Aggressive IC (SPX)',
                        'status': pos.get('status', 'open'),
                        'strikes': f"{pos.get('put_short_strike', 0):.0f}/{pos.get('call_short_strike', 0):.0f}",
                        'direction': 'NEUTRAL',
                        'pnl': round(float(pnl), 2) if pnl else 0,
                        'safe': True
                    })
        except Exception as e:
            logger.debug(f"Could not fetch SAMSON positions: {e}")

        # Check GIDEON positions (Aggressive Directional)
        try:
            from backend.api.routes.gideon_routes import get_gideon_positions
            gideon_data = await get_gideon_positions()
            if gideon_data.get('success') and gideon_data.get('data', {}).get('positions'):
                for pos in gideon_data['data']['positions']:
                    direction = pos.get('direction', 'NEUTRAL')
                    pnl = pos.get('realized_pnl') or pos.get('unrealized_pnl', 0)
                    positions.append({
                        'bot': 'GIDEON',
                        'strategy': 'Aggressive Directional',
                        'status': pos.get('status', 'open'),
                        'strikes': str(pos.get('strike', 'N/A')),
                        'direction': direction.upper() if direction else 'NEUTRAL',
                        'pnl': round(float(pnl), 2) if pnl else 0,
                        'safe': True
                    })
        except Exception as e:
            logger.debug(f"Could not fetch GIDEON positions: {e}")

        # Check ANCHOR positions (Weekly Iron Condors)
        try:
            from backend.api.routes.anchor_routes import get_anchor_positions
            anchor_data = await get_anchor_positions()
            if anchor_data.get('success') and anchor_data.get('data', {}).get('positions'):
                for pos in anchor_data['data']['positions']:
                    pnl = pos.get('realized_pnl') or pos.get('unrealized_pnl', 0)
                    positions.append({
                        'bot': 'ANCHOR',
                        'strategy': 'Weekly IC (SPX)',
                        'status': pos.get('status', 'open'),
                        'strikes': f"{pos.get('put_short_strike', 0):.0f}/{pos.get('call_short_strike', 0):.0f}",
                        'direction': 'NEUTRAL',
                        'pnl': round(float(pnl), 2) if pnl else 0,
                        'safe': True
                    })
        except Exception as e:
            logger.debug(f"Could not fetch ANCHOR positions: {e}")

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
            FROM watchtower_accuracy
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
            # Find flip point (where gamma crosses zero) - find ALL and pick closest to spot
            all_flip_points = []
            for i, strike in enumerate(snapshot.strikes[:-1]):
                if hasattr(strike, 'net_gamma'):
                    curr_gamma = strike.net_gamma
                    next_gamma = snapshot.strikes[i + 1].net_gamma if hasattr(snapshot.strikes[i + 1], 'net_gamma') else 0
                    if curr_gamma * next_gamma < 0:  # Sign change
                        all_flip_points.append(strike.strike)
            # Select flip point closest to spot price
            if all_flip_points:
                current_structure['flip_point'] = min(all_flip_points, key=lambda fp: abs(fp - snapshot.spot_price))

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
    Export WATCHTOWER data to Excel or CSV.

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
                FROM watchtower_snapshots s
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
                FROM watchtower_snapshots s
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
            FROM watchtower_strikes
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
            FROM watchtower_snapshots
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
            FROM watchtower_danger_zone_logs
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
        raise HTTPException(status_code=503, detail="WATCHTOWER engine not available")

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


def get_third_friday(year: int, month: int) -> date:
    """Get the third Friday of a given month (OPEX day)."""
    first_day = date(year, month, 1)
    # Find first Friday
    days_until_friday = (4 - first_day.weekday()) % 7
    first_friday = first_day + timedelta(days=days_until_friday)
    # Add 2 weeks for third Friday
    return first_friday + timedelta(weeks=2)


def detect_expiration_pattern(expirations: list, today: date) -> str:
    """
    Dynamically detect the expiration pattern based on actual expirations.

    Returns: 'daily', 'triple_weekly', 'weekly', or 'monthly_only'
    """
    if not expirations:
        return 'weekly'

    # Look at expirations in the next 14 days to detect pattern
    near_term_days = set()
    for exp_str in expirations:
        try:
            exp_date = datetime.strptime(exp_str, '%Y-%m-%d').date()
            dte = (exp_date - today).days
            if 0 <= dte <= 14:  # Next 2 weeks
                near_term_days.add(exp_date.weekday())  # 0=Mon, 4=Fri
        except ValueError:
            continue

    # Check patterns
    weekdays = {0, 1, 2, 3, 4}  # Mon-Fri
    triple_weekly = {0, 2, 4}    # Mon, Wed, Fri

    if near_term_days >= weekdays or len(near_term_days) >= 5:
        return 'daily'  # Has expirations on all/most weekdays
    elif near_term_days >= triple_weekly or len(near_term_days) >= 3:
        return 'triple_weekly'  # Mon/Wed/Fri pattern
    elif 4 in near_term_days:  # Has Fridays
        return 'weekly'
    else:
        return 'monthly_only'


@router.get("/symbol-expirations")
async def get_symbol_expirations(
    symbol: str = Query("SPY", description="Symbol to get expirations for")
):
    """
    Get available option expirations for any symbol with DYNAMIC pattern detection.

    Automatically detects the expiration pattern based on actual expirations:
    - daily: Expirations on all/most weekdays (SPY, SPX, QQQ, IWM)
    - triple_weekly: Mon/Wed/Fri expirations (GLD, SLV, USO, TLT, etc.)
    - weekly: Friday expirations only
    - monthly_only: Only monthly OPEX dates

    Returns:
    - nearest: The closest expiration (0DTE if available)
    - next_opex: Next monthly options expiration (3rd Friday)
    - weekly: List of near-term expirations
    - all_expirations: All categorized expirations
    """
    try:
        # Get Tradier fetcher
        if not TRADIER_AVAILABLE or TradierDataFetcher is None:
            raise HTTPException(status_code=503, detail="Tradier data not available")

        import os
        api_key = os.environ.get('TRADIER_API_KEY')
        if not api_key:
            raise HTTPException(status_code=503, detail="Tradier API key not configured")

        fetcher = TradierDataFetcher(api_key=api_key, sandbox=False)

        # Get all expirations from Tradier
        all_expirations = fetcher.get_option_expirations(symbol.upper())

        if not all_expirations:
            return {
                "success": False,
                "message": f"No expirations found for {symbol}"
            }

        today = date.today()
        symbol_upper = symbol.upper()

        # DYNAMICALLY detect expiration pattern from actual data
        expiration_type = detect_expiration_pattern(all_expirations, today)

        # Categorize expirations
        nearest = None
        weekly = []
        monthly_opex = []
        categorized = []

        for exp_str in all_expirations:
            try:
                exp_date = datetime.strptime(exp_str, '%Y-%m-%d').date()
                if exp_date < today:
                    continue  # Skip past expirations

                dte = (exp_date - today).days
                day_of_week = exp_date.weekday()  # 0=Mon, 4=Fri

                # Check if it's OPEX (3rd Friday)
                is_opex = exp_date == get_third_friday(exp_date.year, exp_date.month)

                # Determine category based on dynamically detected pattern
                category = 'other'
                if is_opex:
                    category = 'monthly'
                    monthly_opex.append(exp_str)
                elif expiration_type == 'daily' and day_of_week < 5:
                    # Daily expirations - any weekday
                    category = 'daily'
                    weekly.append(exp_str)
                elif expiration_type == 'triple_weekly' and day_of_week in [0, 2, 4]:
                    # Triple weekly - Mon/Wed/Fri
                    category = 'weekly'
                    weekly.append(exp_str)
                elif day_of_week == 4:  # Friday
                    category = 'weekly'
                    weekly.append(exp_str)
                else:
                    category = 'other'

                exp_info = {
                    'date': exp_str,
                    'dte': dte,
                    'day': ['MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT', 'SUN'][day_of_week],
                    'category': category,
                    'is_opex': is_opex,
                    'is_today': dte == 0
                }

                categorized.append(exp_info)

                # Track nearest
                if nearest is None or dte < nearest['dte']:
                    nearest = exp_info

            except ValueError:
                continue

        # Sort by date
        categorized.sort(key=lambda x: x['date'])
        weekly.sort()
        monthly_opex.sort()

        # Get next OPEX date
        next_opex = monthly_opex[0] if monthly_opex else None

        return {
            "success": True,
            "data": {
                "symbol": symbol_upper,
                "expiration_type": expiration_type,  # Dynamically detected
                "nearest": nearest,
                "next_opex": next_opex,
                "weekly": weekly[:8],  # Limit to next 8 weekly
                "monthly_opex": monthly_opex[:4],  # Next 4 OPEX dates
                "all_expirations": categorized[:20],  # All categorized, limited to 20
                "total_available": len(all_expirations),
                "pattern_detection": {
                    "method": "dynamic",
                    "description": {
                        "daily": "Expirations on all/most weekdays (0DTE)",
                        "triple_weekly": "Mon/Wed/Fri expirations",
                        "weekly": "Friday expirations",
                        "monthly_only": "Monthly OPEX only"
                    }.get(expiration_type, "Unknown pattern")
                }
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting expirations for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

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
        raise HTTPException(status_code=503, detail="WATCHTOWER engine not available")

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


# ==================== ACTIONABLE TRADE RECOMMENDATIONS ====================

@router.get("/trade-action")
async def get_trade_action(
    symbol: str = Query(default="SPY"),
    account_size: float = Query(default=50000, description="Account size in dollars"),
    risk_per_trade_pct: float = Query(default=1.0, description="Max risk per trade as % of account (1-5%)"),
    spread_width: int = Query(default=2, description="Width of spreads in dollars (1-5)"),
    auto_log: bool = Query(default=True, description="Automatically log signal for tracking (default: True)")
):
    """
    Generate ACTIONABLE trade recommendation with specific strikes, sizing, and reasoning.

    Unlike generic signals ("BULLISH"), this returns executable trades:
    - Exact strikes to trade
    - Credit/debit target
    - Position size based on your risk tolerance
    - Entry trigger and exit rules
    - THE WHY: Reasoning behind each decision

    When auto_log=True (default), the signal is automatically logged to the database
    for performance tracking. WATCHTOWER will track entry/exit and determine win/loss
    automatically at market close.

    Example output:
    "SELL SPY 588/586 PUT SPREAD for $0.45 credit"
    "WHY: Positive gamma at 590 creates support, order flow 72% bullish, VIX 16 = thin premium"
    "SIZE: 3 contracts at 1% risk ($500 max loss)"
    "EXIT: Take profit at $0.22 (50%), Stop at $1.35 (3x credit)"
    """
    engine = get_engine()
    if not engine:
        raise HTTPException(status_code=503, detail="WATCHTOWER engine not available")

    try:
        # Validate inputs
        risk_per_trade_pct = max(0.5, min(5.0, risk_per_trade_pct))
        spread_width = max(1, min(5, spread_width))
        max_risk_dollars = account_size * (risk_per_trade_pct / 100)

        # Get current gamma snapshot with all data
        snapshot = engine.get_gamma_snapshot(symbol)
        if not snapshot or 'strikes' not in snapshot:
            return {
                "success": True,
                "data": {
                    "action": "WAIT",
                    "reason": "No gamma data available - market may be closed",
                    "trade": None
                }
            }

        # Extract key data
        spot = snapshot.get('spot_price', 0)
        vix = snapshot.get('vix', 20)
        expected_move = snapshot.get('expected_move', 0)
        expected_move_pct = (expected_move / spot * 100) if spot > 0 else 1.0
        gamma_regime = snapshot.get('gamma_regime', 'NEUTRAL')
        flip_point = snapshot.get('flip_point', spot)
        strikes_data = snapshot.get('strikes', [])

        # Get order flow data (now included in GammaSnapshot from process_options_chain)
        order_flow = snapshot.get('order_flow', {})
        flow_signal = order_flow.get('combined_signal', 'NEUTRAL')
        flow_confidence = order_flow.get('signal_confidence', 'LOW')
        net_pressure = order_flow.get('bid_ask_pressure', {}).get('net_pressure', 0)

        # Find gamma walls (key levels)
        call_wall = None
        put_wall = None
        max_call_gamma = 0
        max_put_gamma = 0

        for s in strikes_data:
            strike = s.get('strike', 0)
            net_gamma = s.get('net_gamma', 0)
            if strike > spot and net_gamma > max_call_gamma:
                max_call_gamma = net_gamma
                call_wall = strike
            elif strike < spot and abs(net_gamma) > max_put_gamma:
                max_put_gamma = abs(net_gamma)
                put_wall = strike

        # Calculate distances
        dist_to_call_pct = ((call_wall - spot) / spot * 100) if call_wall and spot > 0 else 999
        dist_to_put_pct = ((spot - put_wall) / spot * 100) if put_wall and spot > 0 else 999
        dist_to_flip_pct = abs(spot - flip_point) / spot * 100 if spot > 0 else 0
        spot_vs_flip = "ABOVE" if spot > flip_point else "BELOW"

        # =====================================================================
        # DECISION ENGINE - Generate specific trade recommendation
        # =====================================================================

        trade_type = None
        direction = None
        short_strike = None
        long_strike = None
        estimated_credit = 0
        confidence = 0
        why_parts = []
        entry_trigger = ""
        exit_rules = {}

        # VIX-based credit estimation (rough approximation for 0DTE)
        # Higher VIX = higher premiums, closer strikes = higher credit
        def estimate_credit(distance_pct: float, is_call: bool) -> float:
            """Estimate credit for a spread based on distance and VIX"""
            # Base credit scales with VIX (higher vol = more premium)
            base = 0.20 + (vix - 15) * 0.03
            # Closer to ATM = more credit
            distance_factor = max(0.3, 1.0 - (distance_pct / 2))
            credit = base * distance_factor * (spread_width / 2)
            return round(max(0.15, min(1.50, credit)), 2)

        # =====================================================================
        # SCENARIO 1: IRON CONDOR - Neutral/Range-bound conditions
        # =====================================================================
        if gamma_regime == "POSITIVE" and dist_to_call_pct > 0.5 and dist_to_put_pct > 0.5:
            # Positive gamma + price between walls = premium selling opportunity

            trade_type = "IRON_CONDOR"
            direction = "NEUTRAL"

            # Use gamma walls as short strikes (natural support/resistance)
            short_put = put_wall if put_wall else round(spot - expected_move, 0)
            short_call = call_wall if call_wall else round(spot + expected_move, 0)

            # Credit estimation
            put_credit = estimate_credit(dist_to_put_pct, False)
            call_credit = estimate_credit(dist_to_call_pct, True)
            estimated_credit = round(put_credit + call_credit, 2)

            # Confidence based on multiple factors
            base_conf = 60
            if gamma_regime == "POSITIVE":
                base_conf += 15
            if flow_signal in ['NEUTRAL', 'DIVERGENCE_BULLISH', 'DIVERGENCE_BEARISH']:
                base_conf += 10  # Balanced flow good for IC
            if vix < 20:
                base_conf += 5
            if dist_to_call_pct > 0.7 and dist_to_put_pct > 0.7:
                base_conf += 10
            confidence = min(95, base_conf)

            # THE WHY
            why_parts = [
                f"GAMMA REGIME: {gamma_regime} = dealers will dampen moves (mean reversion)",
                f"SUPPORT: Put wall at ${put_wall:.0f} ({dist_to_put_pct:.1f}% below spot) provides floor",
                f"RESISTANCE: Call wall at ${call_wall:.0f} ({dist_to_call_pct:.1f}% above spot) provides ceiling",
                f"ORDER FLOW: {flow_signal} ({flow_confidence}) - {'confirms range-bound' if flow_signal == 'NEUTRAL' else 'watch for direction'}",
                f"VIX: {vix:.1f} - {'premium thin, need tighter strikes' if vix < 16 else 'good premium available' if vix < 25 else 'elevated, widen strikes'}"
            ]

            entry_trigger = f"Enter when SPY trades between ${put_wall:.0f}-${call_wall:.0f} range"
            exit_rules = {
                "profit_target": f"Close at 50% profit (${estimated_credit * 0.5:.2f} debit)",
                "stop_loss": f"Close if spread value hits ${estimated_credit * 2.5:.2f} (2.5x credit)",
                "time_stop": "Close by 3:00 PM CT if still open (0DTE time decay accelerates)"
            }

        # =====================================================================
        # SCENARIO 2: PUT CREDIT SPREAD - Bullish bias
        # =====================================================================
        elif (flow_signal in ['STRONG_BULLISH', 'BULLISH'] and flow_confidence in ['HIGH', 'MEDIUM']) or \
             (gamma_regime == "POSITIVE" and spot_vs_flip == "ABOVE" and dist_to_flip_pct > 0.3):

            trade_type = "PUT_CREDIT_SPREAD"
            direction = "BULLISH"

            # Short strike at put wall (support), long below
            short_strike = put_wall if put_wall else round(spot - expected_move * 0.5, 0)
            long_strike = short_strike - spread_width
            estimated_credit = estimate_credit(dist_to_put_pct, False)

            # Confidence
            base_conf = 55
            if flow_signal == 'STRONG_BULLISH':
                base_conf += 20
            elif flow_signal == 'BULLISH':
                base_conf += 12
            if gamma_regime == "POSITIVE":
                base_conf += 10
            if spot_vs_flip == "ABOVE":
                base_conf += 8
            if dist_to_put_pct > 0.5:
                base_conf += 5
            confidence = min(90, base_conf)

            # THE WHY
            why_parts = [
                f"ORDER FLOW: {flow_signal} ({flow_confidence}) - buyers dominating, {abs(net_pressure):.1f} net pressure",
                f"GAMMA REGIME: {gamma_regime} - {'supports stability' if gamma_regime == 'POSITIVE' else 'momentum possible'}",
                f"POSITION: Spot ${spot:.2f} is {spot_vs_flip} flip point ${flip_point:.2f} ({dist_to_flip_pct:.1f}% away)",
                f"SUPPORT: Put wall at ${short_strike:.0f} acts as dealer-defended floor",
                f"VIX: {vix:.1f} implies ${expected_move:.2f} expected move ({expected_move_pct:.1f}%)"
            ]

            entry_trigger = f"Enter on pullback to ${short_strike + spread_width:.0f} or better"
            exit_rules = {
                "profit_target": f"Close at 50% profit (${estimated_credit * 0.5:.2f} debit)",
                "stop_loss": f"Close if spread hits ${min(spread_width * 0.8, estimated_credit * 3):.2f}",
                "adjustment": f"Roll down if SPY breaks ${short_strike:.0f} with momentum"
            }

        # =====================================================================
        # SCENARIO 3: CALL CREDIT SPREAD - Bearish bias
        # =====================================================================
        elif (flow_signal in ['STRONG_BEARISH', 'BEARISH'] and flow_confidence in ['HIGH', 'MEDIUM']) or \
             (gamma_regime == "POSITIVE" and spot_vs_flip == "BELOW" and dist_to_flip_pct > 0.3):

            trade_type = "CALL_CREDIT_SPREAD"
            direction = "BEARISH"

            # Short strike at call wall (resistance), long above
            short_strike = call_wall if call_wall else round(spot + expected_move * 0.5, 0)
            long_strike = short_strike + spread_width
            estimated_credit = estimate_credit(dist_to_call_pct, True)

            # Confidence
            base_conf = 55
            if flow_signal == 'STRONG_BEARISH':
                base_conf += 20
            elif flow_signal == 'BEARISH':
                base_conf += 12
            if gamma_regime == "POSITIVE":
                base_conf += 10
            if spot_vs_flip == "BELOW":
                base_conf += 8
            if dist_to_call_pct > 0.5:
                base_conf += 5
            confidence = min(90, base_conf)

            # THE WHY
            why_parts = [
                f"ORDER FLOW: {flow_signal} ({flow_confidence}) - sellers dominating, {abs(net_pressure):.1f} net pressure",
                f"GAMMA REGIME: {gamma_regime} - {'supports stability' if gamma_regime == 'POSITIVE' else 'momentum possible'}",
                f"POSITION: Spot ${spot:.2f} is {spot_vs_flip} flip point ${flip_point:.2f} ({dist_to_flip_pct:.1f}% away)",
                f"RESISTANCE: Call wall at ${short_strike:.0f} acts as dealer-defended ceiling",
                f"VIX: {vix:.1f} implies ${expected_move:.2f} expected move ({expected_move_pct:.1f}%)"
            ]

            entry_trigger = f"Enter on rally to ${short_strike - spread_width:.0f} or better"
            exit_rules = {
                "profit_target": f"Close at 50% profit (${estimated_credit * 0.5:.2f} debit)",
                "stop_loss": f"Close if spread hits ${min(spread_width * 0.8, estimated_credit * 3):.2f}",
                "adjustment": f"Roll up if SPY breaks ${short_strike:.0f} with momentum"
            }

        # =====================================================================
        # SCENARIO 4: DEBIT SPREAD - Breakout conditions
        # =====================================================================
        elif gamma_regime == "NEGATIVE" and (dist_to_call_pct < 0.3 or dist_to_put_pct < 0.3):

            is_call_break = dist_to_call_pct < dist_to_put_pct

            if is_call_break:
                trade_type = "CALL_DEBIT_SPREAD"
                direction = "BULLISH_BREAKOUT"
                long_strike = round(spot, 0)
                short_strike = long_strike + spread_width
                estimated_debit = spread_width * 0.45  # Rough ATM debit estimate
            else:
                trade_type = "PUT_DEBIT_SPREAD"
                direction = "BEARISH_BREAKDOWN"
                long_strike = round(spot, 0)
                short_strike = long_strike - spread_width
                estimated_debit = spread_width * 0.45

            # Confidence for breakout
            base_conf = 50
            if gamma_regime == "NEGATIVE":
                base_conf += 15  # Negative gamma amplifies moves
            if (is_call_break and flow_signal in ['BULLISH', 'STRONG_BULLISH']) or \
               (not is_call_break and flow_signal in ['BEARISH', 'STRONG_BEARISH']):
                base_conf += 15
            confidence = min(85, base_conf)

            estimated_credit = -estimated_debit  # Negative = debit

            wall_type = "call" if is_call_break else "put"
            wall_strike = call_wall if is_call_break else put_wall
            why_parts = [
                f"GAMMA REGIME: NEGATIVE = breakouts accelerate (dealers chase, not stabilize)",
                f"WALL PROXIMITY: Price {dist_to_call_pct if is_call_break else dist_to_put_pct:.1f}% from {wall_type} wall at ${wall_strike:.0f}",
                f"ORDER FLOW: {flow_signal} - {'confirms breakout direction' if ((is_call_break and 'BULLISH' in flow_signal) or (not is_call_break and 'BEARISH' in flow_signal)) else 'watch for confirmation'}",
                f"EXPECTED MOVE: ${expected_move:.2f} ({expected_move_pct:.1f}%) - breakout could exceed this"
            ]

            target_move = expected_move * 1.5
            entry_trigger = f"Enter on {wall_type} wall break at ${wall_strike:.0f}"
            exit_rules = {
                "profit_target": f"Target ${target_move:.2f} move, close at 100% gain",
                "stop_loss": f"Close if move fails and price returns inside ${wall_strike:.0f}",
                "time_stop": "Close by 2:30 PM if not profitable (breakouts need momentum)"
            }

        # =====================================================================
        # DEFAULT: WAIT - No clear edge
        # =====================================================================
        else:
            return {
                "success": True,
                "data": {
                    "action": "WAIT",
                    "reason": "No clear edge - conditions do not favor a high-probability trade",
                    "context": {
                        "gamma_regime": gamma_regime,
                        "order_flow": flow_signal,
                        "flow_confidence": flow_confidence,
                        "vix": vix,
                        "spot": spot,
                        "dist_to_call_wall": f"{dist_to_call_pct:.1f}%",
                        "dist_to_put_wall": f"{dist_to_put_pct:.1f}%"
                    },
                    "suggestions": [
                        "Wait for order flow to align with gamma structure",
                        "Look for price to approach a gamma wall for clearer setup",
                        f"Current range: ${put_wall:.0f} - ${call_wall:.0f}" if put_wall and call_wall else "Walls not defined"
                    ],
                    "trade": None
                }
            }

        # =====================================================================
        # POSITION SIZING
        # =====================================================================
        max_loss_per_contract = (spread_width - abs(estimated_credit)) * 100 if estimated_credit > 0 else abs(estimated_credit) * 100
        contracts = max(1, int(max_risk_dollars / max_loss_per_contract)) if max_loss_per_contract > 0 else 1
        actual_max_loss = max_loss_per_contract * contracts
        actual_max_profit = abs(estimated_credit) * 100 * contracts if estimated_credit > 0 else (spread_width - abs(estimated_credit)) * 100 * contracts

        # Build trade structure
        if trade_type == "IRON_CONDOR":
            trade_structure = {
                "type": "IRON_CONDOR",
                "symbol": symbol,
                "put_spread": {
                    "short": short_put,
                    "long": short_put - spread_width
                },
                "call_spread": {
                    "short": short_call,
                    "long": short_call + spread_width
                },
                "credit": estimated_credit,
                "expiration": "0DTE"
            }
            trade_description = f"SELL {symbol} {short_put - spread_width}/{short_put}p - {short_call}/{short_call + spread_width}c IC @ ${estimated_credit:.2f} credit"
        elif trade_type in ["PUT_CREDIT_SPREAD", "CALL_CREDIT_SPREAD"]:
            trade_structure = {
                "type": trade_type,
                "symbol": symbol,
                "short_strike": short_strike,
                "long_strike": long_strike,
                "credit": estimated_credit,
                "expiration": "0DTE"
            }
            spread_notation = f"{long_strike}/{short_strike}p" if "PUT" in trade_type else f"{short_strike}/{long_strike}c"
            trade_description = f"SELL {symbol} {spread_notation} @ ${estimated_credit:.2f} credit"
        else:
            trade_structure = {
                "type": trade_type,
                "symbol": symbol,
                "long_strike": long_strike,
                "short_strike": short_strike,
                "debit": abs(estimated_credit),
                "expiration": "0DTE"
            }
            spread_notation = f"{long_strike}/{short_strike}c" if "CALL" in trade_type else f"{long_strike}/{short_strike}p"
            trade_description = f"BUY {symbol} {spread_notation} @ ${abs(estimated_credit):.2f} debit"

        # Build the response data
        response_data = {
            "action": trade_type,
            "direction": direction,
            "confidence": confidence,
            "trade_description": trade_description,
            "trade": trade_structure,
            "why": why_parts,
            "sizing": {
                "contracts": contracts,
                "max_loss": f"${actual_max_loss:.0f}",
                "max_profit": f"${actual_max_profit:.0f}",
                "risk_reward": f"1:{actual_max_profit/actual_max_loss:.1f}" if actual_max_loss > 0 else "N/A",
                "account_risk_pct": f"{(actual_max_loss / account_size * 100):.1f}%"
            },
            "entry": entry_trigger,
            "exit": exit_rules,
            "market_context": {
                "spot": spot,
                "vix": vix,
                "expected_move": expected_move,
                "gamma_regime": gamma_regime,
                "order_flow": flow_signal,
                "flow_confidence": flow_confidence,
                "flip_point": flip_point,
                "call_wall": call_wall,
                "put_wall": put_wall
            },
            "timestamp": format_central_timestamp()
        }

        # Auto-log signal if enabled and it's an actionable trade (not WAIT)
        signal_id = None
        if auto_log and trade_type and trade_type != "WAIT":
            signal_id = _log_signal_to_db(response_data, symbol)
            if signal_id:
                logger.info(f"WATCHTOWER: Auto-logged signal #{signal_id}: {trade_type} {direction}")

        return {
            "success": True,
            "data": response_data,
            "signal_id": signal_id,  # None if auto_log=False or WAIT action
            "auto_logged": signal_id is not None
        }

    except Exception as e:
        logger.error(f"Error generating trade action: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== SIGNAL TRACKING & PERFORMANCE ====================

def _log_signal_to_db(signal_data: dict, symbol: str = "SPY") -> Optional[int]:
    """
    Log a trade signal to the database for tracking.
    Returns the signal ID if successful.
    """
    conn = None
    cursor = None
    try:
        conn = get_connection()
        if not conn:
            return None
        cursor = conn.cursor()

        # Extract data from signal
        action = signal_data.get('action', 'UNKNOWN')
        direction = signal_data.get('direction')
        confidence = signal_data.get('confidence', 0)
        trade_desc = signal_data.get('trade_description', '')
        trade = signal_data.get('trade', {}) or {}
        sizing = signal_data.get('sizing', {}) or {}
        context = signal_data.get('market_context', {}) or {}
        exit_rules = signal_data.get('exit', {}) or {}

        # Parse sizing values (remove $ and convert)
        max_profit = float(sizing.get('max_profit', '$0').replace('$', '').replace(',', '')) if sizing.get('max_profit') else 0
        max_loss = float(sizing.get('max_loss', '$0').replace('$', '').replace(',', '')) if sizing.get('max_loss') else 0

        # Extract strikes based on trade type
        short_strike = trade.get('short_strike')
        long_strike = trade.get('long_strike')
        put_short = trade.get('put_spread', {}).get('short') if trade.get('put_spread') else None
        put_long = trade.get('put_spread', {}).get('long') if trade.get('put_spread') else None
        call_short = trade.get('call_spread', {}).get('short') if trade.get('call_spread') else None
        call_long = trade.get('call_spread', {}).get('long') if trade.get('call_spread') else None

        # Credit/debit
        credit = trade.get('credit') or trade.get('debit', 0)
        if trade.get('debit'):
            credit = -trade.get('debit')  # Negative for debits

        # Parse profit target and stop from exit rules
        # e.g., "Close at 50% profit ($0.22 debit)" -> 0.22
        profit_target_price = None
        stop_loss_price = None
        if exit_rules.get('profit_target'):
            import re
            match = re.search(r'\$([0-9.]+)', exit_rules['profit_target'])
            if match:
                profit_target_price = float(match.group(1))
        if exit_rules.get('stop_loss'):
            import re
            match = re.search(r'\$([0-9.]+)', exit_rules['stop_loss'])
            if match:
                stop_loss_price = float(match.group(1))

        cursor.execute("""
            INSERT INTO watchtower_trade_signals (
                symbol, action, direction, confidence, trade_description,
                trade_structure, spot_at_signal, credit_target,
                short_strike, long_strike, put_short, put_long, call_short, call_long,
                vix_at_signal, gamma_regime, order_flow, flow_confidence,
                contracts, max_profit, max_loss,
                profit_target_price, stop_loss_price,
                status
            ) VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s,
                'OPEN'
            ) RETURNING id
        """, (
            symbol, action, direction, confidence, trade_desc,
            json.dumps(trade), context.get('spot'), credit,
            short_strike, long_strike, put_short, put_long, call_short, call_long,
            context.get('vix'), context.get('gamma_regime'), context.get('order_flow'), context.get('flow_confidence'),
            sizing.get('contracts', 1), max_profit, max_loss,
            profit_target_price, stop_loss_price
        ))

        signal_id = cursor.fetchone()[0]
        conn.commit()
        logger.info(f"WATCHTOWER: Logged signal #{signal_id}: {action} {direction}")
        return signal_id

    except Exception as e:
        logger.error(f"Failed to log signal: {e}")
        if conn:
            conn.rollback()
        return None
    finally:
        if cursor:
            try:
                cursor.close()
            except:
                pass
        if conn:
            try:
                conn.close()
            except:
                pass


def _update_signal_outcomes(symbol: str = "SPY", current_spot: float = None, force_close: bool = False):
    """
    Check open signals and update their outcomes based on current price.

    Called periodically (every 5 minutes during market hours) to track performance.
    Checks for:
    1. Profit target hit (intraday)
    2. Stop loss hit (intraday)
    3. Expiration at market close (0DTE)

    Args:
        symbol: Trading symbol
        current_spot: Current price (fetched if not provided)
        force_close: If True, close all open signals (for end of day)

    Returns:
        Dict with update counts
    """
    conn = None
    cursor = None
    updates = {'closed': 0, 'wins': 0, 'losses': 0}

    try:
        conn = get_connection()
        if not conn:
            return updates

        cursor = conn.cursor()

        # Get open signals (0DTE signals from today)
        cursor.execute("""
            SELECT id, action, credit_target, profit_target_price, stop_loss_price,
                   spot_at_signal, max_profit, max_loss, created_at,
                   put_short, call_short, short_strike, long_strike,
                   put_long, call_long
            FROM watchtower_trade_signals
            WHERE symbol = %s AND status = 'OPEN'
            AND created_at > NOW() - INTERVAL '1 day'
            ORDER BY created_at DESC
        """, (symbol,))
        open_signals = cursor.fetchall()

        if not open_signals:
            return updates

        # Get current spot if not provided
        if not current_spot:
            engine = get_engine()
            if engine:
                snapshot = engine.get_gamma_snapshot(symbol)
                current_spot = snapshot.get('spot_price', 0) if snapshot else 0

        if not current_spot or current_spot <= 0:
            return updates

        now = get_central_time()
        market_close = now.replace(hour=15, minute=0, second=0, microsecond=0)
        is_after_close = now >= market_close

        for signal in open_signals:
            (signal_id, action, credit, profit_target, stop_loss, spot_at_signal,
             max_profit, max_loss, created_at, put_short, call_short, short_strike,
             long_strike, put_long, call_long) = signal

            status = None
            outcome_reason = None
            actual_pnl = 0
            hit_profit = False
            hit_stop = False
            expired_profit = False

            # Determine reference strikes for P&L calculation
            # For credit spreads: short strike is the key level
            # For debit spreads: we need price to move toward long strike

            # ================================================================
            # INTRADAY CHECKS - Profit Target & Stop Loss
            # ================================================================

            if action in ['IRON_CONDOR', 'PUT_CREDIT_SPREAD', 'CALL_CREDIT_SPREAD']:
                # Credit spreads - estimate current spread value based on price movement
                # Simplified: if price moved significantly toward short strike, assume loss

                if action == 'IRON_CONDOR' and put_short and call_short:
                    # Distance to nearest short strike
                    dist_to_put = current_spot - put_short
                    dist_to_call = call_short - current_spot

                    # If price breached a short strike, it's a loss
                    if current_spot <= put_short or current_spot >= call_short:
                        status = 'LOSS'
                        outcome_reason = 'strike_breached_intraday'
                        actual_pnl = -max_loss if max_loss else -(credit * 100 * 3)  # ~3x credit
                        hit_stop = True

                elif action == 'PUT_CREDIT_SPREAD':
                    ref_strike = put_short or short_strike
                    if ref_strike and current_spot < ref_strike:
                        # Price below short put = ITM = loss
                        status = 'LOSS'
                        outcome_reason = 'strike_breached_intraday'
                        actual_pnl = -max_loss if max_loss else -(credit * 100 * 3)
                        hit_stop = True

                elif action == 'CALL_CREDIT_SPREAD':
                    ref_strike = call_short or short_strike
                    if ref_strike and current_spot > ref_strike:
                        # Price above short call = ITM = loss
                        status = 'LOSS'
                        outcome_reason = 'strike_breached_intraday'
                        actual_pnl = -max_loss if max_loss else -(credit * 100 * 3)
                        hit_stop = True

            elif action in ['CALL_DEBIT_SPREAD', 'PUT_DEBIT_SPREAD']:
                # Debit spreads - check if hit profit target or stop
                debit_paid = abs(credit) if credit else 0

                if action == 'CALL_DEBIT_SPREAD':
                    # Need price to go UP
                    move_pct = (current_spot - spot_at_signal) / spot_at_signal * 100 if spot_at_signal else 0

                    # Profit target: typically 50-100% of debit
                    if move_pct > 1.0:  # 1% move = ~100% gain on near-ATM debit spread
                        status = 'WIN'
                        outcome_reason = 'profit_target_hit'
                        actual_pnl = max_profit if max_profit else debit_paid * 100
                        hit_profit = True
                    # Stop loss: typically -50% of debit
                    elif move_pct < -0.5:  # 0.5% adverse move
                        status = 'LOSS'
                        outcome_reason = 'stop_loss_hit'
                        actual_pnl = -max_loss if max_loss else -debit_paid * 100
                        hit_stop = True

                else:  # PUT_DEBIT_SPREAD
                    # Need price to go DOWN
                    move_pct = (spot_at_signal - current_spot) / spot_at_signal * 100 if spot_at_signal else 0

                    if move_pct > 1.0:
                        status = 'WIN'
                        outcome_reason = 'profit_target_hit'
                        actual_pnl = max_profit if max_profit else debit_paid * 100
                        hit_profit = True
                    elif move_pct < -0.5:
                        status = 'LOSS'
                        outcome_reason = 'stop_loss_hit'
                        actual_pnl = -max_loss if max_loss else -debit_paid * 100
                        hit_stop = True

            # ================================================================
            # EXPIRATION CHECK - At Market Close
            # ================================================================

            if not status and (is_after_close or force_close):
                if action in ['IRON_CONDOR', 'PUT_CREDIT_SPREAD', 'CALL_CREDIT_SPREAD']:
                    # Credit spreads at expiration
                    if action == 'IRON_CONDOR' and put_short and call_short:
                        if put_short <= current_spot <= call_short:
                            status = 'WIN'
                            outcome_reason = 'expired_otm'
                            actual_pnl = max_profit if max_profit else credit * 100
                            expired_profit = True
                        else:
                            status = 'LOSS'
                            outcome_reason = 'expired_itm'
                            actual_pnl = -max_loss if max_loss else -(credit * 100 * 3)

                    elif action == 'PUT_CREDIT_SPREAD':
                        ref_strike = put_short or short_strike
                        if ref_strike and current_spot >= ref_strike:
                            status = 'WIN'
                            outcome_reason = 'expired_otm'
                            actual_pnl = max_profit if max_profit else credit * 100
                            expired_profit = True
                        else:
                            status = 'LOSS'
                            outcome_reason = 'expired_itm'
                            actual_pnl = -max_loss if max_loss else -(credit * 100 * 3)

                    elif action == 'CALL_CREDIT_SPREAD':
                        ref_strike = call_short or short_strike
                        if ref_strike and current_spot <= ref_strike:
                            status = 'WIN'
                            outcome_reason = 'expired_otm'
                            actual_pnl = max_profit if max_profit else credit * 100
                            expired_profit = True
                        else:
                            status = 'LOSS'
                            outcome_reason = 'expired_itm'
                            actual_pnl = -max_loss if max_loss else -(credit * 100 * 3)

                elif action in ['CALL_DEBIT_SPREAD', 'PUT_DEBIT_SPREAD']:
                    # Debit spreads at expiration
                    if action == 'CALL_DEBIT_SPREAD':
                        if current_spot > spot_at_signal:
                            status = 'WIN'
                            outcome_reason = 'expired_itm_favorable'
                            move_pct = (current_spot - spot_at_signal) / spot_at_signal
                            actual_pnl = (max_profit if max_profit else 100) * min(1.0, move_pct * 50)
                        else:
                            status = 'LOSS'
                            outcome_reason = 'expired_otm'
                            actual_pnl = -max_loss if max_loss else -100

                    else:  # PUT_DEBIT_SPREAD
                        if current_spot < spot_at_signal:
                            status = 'WIN'
                            outcome_reason = 'expired_itm_favorable'
                            move_pct = (spot_at_signal - current_spot) / spot_at_signal
                            actual_pnl = (max_profit if max_profit else 100) * min(1.0, move_pct * 50)
                        else:
                            status = 'LOSS'
                            outcome_reason = 'expired_otm'
                            actual_pnl = -max_loss if max_loss else -100

            # ================================================================
            # UPDATE DATABASE
            # ================================================================

            if status:
                time_to_resolution = int((now - created_at).total_seconds() / 60) if created_at else None
                pnl_pct = (actual_pnl / max_loss * 100) if max_loss and max_loss > 0 else 0

                cursor.execute("""
                    UPDATE watchtower_trade_signals
                    SET status = %s, outcome_reason = %s, closed_at = %s,
                        spot_at_close = %s, actual_pnl = %s, pnl_percent = %s,
                        time_to_resolution = %s, hit_profit_target = %s,
                        hit_stop_loss = %s, expired_in_profit = %s
                    WHERE id = %s
                """, (
                    status, outcome_reason, now, current_spot, actual_pnl, pnl_pct,
                    time_to_resolution, hit_profit, hit_stop, expired_profit, signal_id
                ))

                updates['closed'] += 1
                if status == 'WIN':
                    updates['wins'] += 1
                else:
                    updates['losses'] += 1

                logger.info(f"WATCHTOWER Signal #{signal_id}: {status} ({outcome_reason}) - P&L: ${actual_pnl:.2f}")

        conn.commit()
        return updates

    except Exception as e:
        logger.error(f"Failed to update signal outcomes: {e}")
        if conn:
            conn.rollback()
        return updates
    finally:
        if cursor:
            try:
                cursor.close()
            except:
                pass
        if conn:
            try:
                conn.close()
            except:
                pass


@router.post("/signals/log")
async def log_trade_signal(
    symbol: str = Query(default="SPY"),
    signal_data: dict = None
):
    """
    Log a trade signal for performance tracking.
    Called when user clicks "Execute" or signal is generated.
    """
    if not signal_data:
        raise HTTPException(status_code=400, detail="signal_data required")

    signal_id = _log_signal_to_db(signal_data, symbol)

    return {
        "success": signal_id is not None,
        "signal_id": signal_id,
        "message": f"Signal logged as #{signal_id}" if signal_id else "Failed to log signal"
    }


@router.get("/signals/recent")
async def get_recent_signals(
    symbol: str = Query(default="SPY"),
    limit: int = Query(default=20, le=100),
    status: str = Query(default=None, description="Filter by status: OPEN, WIN, LOSS, EXPIRED")
):
    """
    Get recent trade signals with their outcomes.
    """
    conn = None
    cursor = None
    try:
        conn = get_connection()
        if not conn:
            return {"success": True, "data": {"signals": [], "message": "Database not available"}}

        cursor = conn.cursor()

        query = """
            SELECT id, created_at, action, direction, confidence, trade_description,
                   spot_at_signal, credit_target, vix_at_signal, gamma_regime,
                   contracts, max_profit, max_loss,
                   status, outcome_reason, closed_at, spot_at_close, actual_pnl, pnl_percent,
                   time_to_resolution
            FROM watchtower_trade_signals
            WHERE symbol = %s
        """
        params = [symbol]

        if status:
            query += " AND status = %s"
            params.append(status)

        query += " ORDER BY created_at DESC LIMIT %s"
        params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()

        signals = []
        for row in rows:
            signals.append({
                "id": row[0],
                "created_at": row[1].isoformat() if row[1] else None,
                "action": row[2],
                "direction": row[3],
                "confidence": row[4],
                "trade_description": row[5],
                "spot_at_signal": float(row[6]) if row[6] else None,
                "credit": float(row[7]) if row[7] else None,
                "vix": float(row[8]) if row[8] else None,
                "gamma_regime": row[9],
                "contracts": row[10],
                "max_profit": float(row[11]) if row[11] else None,
                "max_loss": float(row[12]) if row[12] else None,
                "status": row[13],
                "outcome_reason": row[14],
                "closed_at": row[15].isoformat() if row[15] else None,
                "spot_at_close": float(row[16]) if row[16] else None,
                "actual_pnl": float(row[17]) if row[17] else None,
                "pnl_percent": float(row[18]) if row[18] else None,
                "time_to_resolution": row[19]
            })

        return {
            "success": True,
            "data": {
                "signals": signals,
                "count": len(signals)
            }
        }

    except Exception as e:
        logger.error(f"Failed to get recent signals: {e}")
        return {"success": False, "error": str(e)}
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@router.get("/signals/performance")
async def get_signal_performance(
    symbol: str = Query(default="SPY"),
    days: int = Query(default=30, le=365)
):
    """
    Get performance statistics for WATCHTOWER trade signals.

    Returns:
    - Total signals, wins, losses
    - Win rate
    - Total P&L (simulated)
    - Average win/loss
    - Best/worst trade
    - Performance by action type
    """
    conn = None
    cursor = None
    try:
        conn = get_connection()
        if not conn:
            return {"success": True, "data": {"message": "Database not available"}}

        cursor = conn.cursor()

        # Overall stats
        cursor.execute("""
            SELECT
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE status = 'WIN') as wins,
                COUNT(*) FILTER (WHERE status = 'LOSS') as losses,
                COUNT(*) FILTER (WHERE status = 'OPEN') as open_signals,
                COALESCE(SUM(actual_pnl), 0) as total_pnl,
                COALESCE(AVG(actual_pnl) FILTER (WHERE status = 'WIN'), 0) as avg_win,
                COALESCE(AVG(actual_pnl) FILTER (WHERE status = 'LOSS'), 0) as avg_loss,
                COALESCE(MAX(actual_pnl), 0) as best_trade,
                COALESCE(MIN(actual_pnl), 0) as worst_trade,
                COALESCE(AVG(time_to_resolution) FILTER (WHERE status IN ('WIN', 'LOSS')), 0) as avg_resolution_time
            FROM watchtower_trade_signals
            WHERE symbol = %s
            AND created_at > NOW() - INTERVAL '%s days'
        """, (symbol, days))

        row = cursor.fetchone()
        total, wins, losses, open_count, total_pnl, avg_win, avg_loss, best, worst, avg_time = row

        win_rate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0

        # Stats by action type
        cursor.execute("""
            SELECT
                action,
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE status = 'WIN') as wins,
                COUNT(*) FILTER (WHERE status = 'LOSS') as losses,
                COALESCE(SUM(actual_pnl), 0) as total_pnl
            FROM watchtower_trade_signals
            WHERE symbol = %s
            AND created_at > NOW() - INTERVAL '%s days'
            AND status IN ('WIN', 'LOSS')
            GROUP BY action
            ORDER BY total DESC
        """, (symbol, days))

        by_action = []
        for r in cursor.fetchall():
            action_wins = r[2] or 0
            action_losses = r[3] or 0
            action_wr = (action_wins / (action_wins + action_losses) * 100) if (action_wins + action_losses) > 0 else 0
            by_action.append({
                "action": r[0],
                "total": r[1],
                "wins": action_wins,
                "losses": action_losses,
                "win_rate": round(action_wr, 1),
                "total_pnl": float(r[4]) if r[4] else 0
            })

        # Recent performance (daily P&L for last 7 days)
        cursor.execute("""
            SELECT
                DATE(closed_at) as trade_date,
                COUNT(*) as trades,
                COALESCE(SUM(actual_pnl), 0) as daily_pnl,
                COUNT(*) FILTER (WHERE status = 'WIN') as wins
            FROM watchtower_trade_signals
            WHERE symbol = %s
            AND closed_at > NOW() - INTERVAL '7 days'
            AND status IN ('WIN', 'LOSS')
            GROUP BY DATE(closed_at)
            ORDER BY trade_date DESC
        """, (symbol,))

        daily_pnl = []
        for r in cursor.fetchall():
            daily_pnl.append({
                "date": r[0].isoformat() if r[0] else None,
                "trades": r[1],
                "pnl": float(r[2]) if r[2] else 0,
                "wins": r[3]
            })

        return {
            "success": True,
            "data": {
                "summary": {
                    "total_signals": total,
                    "wins": wins,
                    "losses": losses,
                    "open": open_count,
                    "win_rate": round(win_rate, 1),
                    "total_pnl": round(float(total_pnl), 2),
                    "avg_win": round(float(avg_win), 2),
                    "avg_loss": round(float(avg_loss), 2),
                    "best_trade": round(float(best), 2),
                    "worst_trade": round(float(worst), 2),
                    "avg_resolution_minutes": round(float(avg_time), 0)
                },
                "by_action": by_action,
                "daily_pnl": daily_pnl,
                "period_days": days
            }
        }

    except Exception as e:
        logger.error(f"Failed to get signal performance: {e}")
        return {"success": False, "error": str(e)}
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@router.post("/signals/update-outcomes")
async def update_signal_outcomes(
    symbol: str = Query(default="SPY"),
    force_close: bool = Query(default=False, description="Force close all open signals (for EOD)")
):
    """
    Update outcomes for open WATCHTOWER signals.

    Called automatically:
    - Every 5 minutes during market hours (intraday profit/stop checks)
    - At 3:01 PM CT (market close / 0DTE expiration)

    Args:
        symbol: Trading symbol (default SPY)
        force_close: If True, close all open signals regardless of price (for EOD)

    Returns success status and counts of closed/won/lost signals.
    """
    try:
        updates = _update_signal_outcomes(symbol, force_close=force_close)
        return {
            "success": True,
            "message": f"Updated {updates.get('closed', 0)} signals",
            "data": {
                "updates": updates
            }
        }
    except Exception as e:
        logger.error(f"Failed to update outcomes: {e}")
        return {"success": False, "error": str(e)}


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
        raise HTTPException(status_code=503, detail="WATCHTOWER engine not available")

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
    logger.info(f"WATCHTOWER pattern-outcomes: Starting for symbol={symbol}")

    engine = get_engine()
    if not engine:
        logger.error("WATCHTOWER pattern-outcomes: Engine not available")
        raise HTTPException(status_code=503, detail="WATCHTOWER engine not available")

    try:
        # Get current pattern
        logger.debug(f"WATCHTOWER pattern-outcomes: Getting gamma snapshot for {symbol}")
        snapshot = engine.get_gamma_snapshot(symbol)
        if not snapshot:
            logger.info(f"WATCHTOWER pattern-outcomes: No snapshot available for {symbol}")
            return {"success": True, "data": {"patterns": [], "message": "No gamma data available"}}

        current_regime = snapshot.get('gamma_regime', 'NEUTRAL')
        current_vix = snapshot.get('vix', 20)
        spot_price = snapshot.get('spot_price', 0)
        flip_point = snapshot.get('flip_point', spot_price)
        dist_to_flip = abs(spot_price - flip_point) / spot_price * 100 if spot_price > 0 else 0
        logger.debug(f"WATCHTOWER pattern-outcomes: regime={current_regime}, vix={current_vix}, spot={spot_price}")

        # Query historical data from database
        conn = get_connection()
        if not conn:
            logger.warning("WATCHTOWER pattern-outcomes: Database connection not available")
            return {"success": True, "data": {"patterns": [], "message": "Database not available"}}

        cursor = conn.cursor()

        # Find similar historical patterns using gex_history table (aggregated to daily)
        # Uses daily snapshots to find similar gamma regime days and their price outcomes
        try:
            cursor.execute("""
                WITH daily_gex AS (
                    -- Get one GEX snapshot per day (morning snapshot)
                    SELECT DISTINCT ON (DATE(timestamp))
                        DATE(timestamp) as trade_date,
                        spot_price,
                        net_gex as net_gamma,
                        flip_point,
                        CASE WHEN net_gex > 0 THEN 'POSITIVE' ELSE 'NEGATIVE' END as regime
                    FROM gex_history
                    WHERE symbol = %s
                    AND timestamp > NOW() - INTERVAL '90 days'
                    AND timestamp < NOW() - INTERVAL '1 day'
                    ORDER BY DATE(timestamp), timestamp
                ),
                daily_prices AS (
                    -- Get OHLC from price_history or market_data_daily
                    SELECT
                        date as trade_date,
                        open as spot_open,
                        high as spot_high,
                        low as spot_low,
                        close as spot_close
                    FROM market_data_daily
                    WHERE symbol = %s
                    AND date > NOW() - INTERVAL '90 days'
                )
                SELECT
                    dg.trade_date,
                    dp.spot_open,
                    dp.spot_close,
                    dp.spot_high,
                    dp.spot_low,
                    dg.net_gamma,
                    dg.flip_point,
                    CASE WHEN dp.spot_open > 0
                        THEN ABS(dp.spot_close - dp.spot_open) / dp.spot_open * 100
                        ELSE 0 END as move_pct,
                    CASE WHEN dp.spot_open > 0
                        THEN (dp.spot_high - dp.spot_low) / dp.spot_open * 100
                        ELSE 0 END as range_pct,
                    dg.regime
                FROM daily_gex dg
                LEFT JOIN daily_prices dp ON dg.trade_date = dp.trade_date
                WHERE dg.regime = %s
                AND dp.spot_open IS NOT NULL
                ORDER BY dg.trade_date DESC
                LIMIT 100
            """, (symbol, symbol, current_regime))
            rows = cursor.fetchall()
        except Exception as db_err:
            # Tables might not exist - log and return empty
            logger.warning(f"WATCHTOWER pattern-outcomes: Database query failed: {db_err}")
            conn.close()
            return {
                "success": True,
                "data": {
                    "patterns": [],
                    "message": "Insufficient historical data for pattern matching"
                }
            }

        conn.close()
        logger.info(f"WATCHTOWER pattern-outcomes: Query returned {len(rows)} rows")

        if not rows:
            logger.info(f"WATCHTOWER pattern-outcomes: No historical data for {symbol} with regime {current_regime}")
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
        logger.info(f"WATCHTOWER pattern-outcomes: Returning {len(patterns)} patterns for {symbol}")
        return {
            "success": True,
            "data": {
                "patterns": patterns
            }
        }

    except Exception as e:
        logger.error(f"WATCHTOWER pattern-outcomes: Error for {symbol}: {e}", exc_info=True)
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
            FROM watchtower_pin_predictions
            WHERE symbol = %s
            AND prediction_date >= CURRENT_DATE - INTERVAL '%s days'
            GROUP BY gamma_regime
        """, (symbol, days))

        rows = cursor.fetchall()

        if not rows:
            # If no prediction table, return placeholder
            cursor.execute("""
                SELECT COUNT(*) FROM information_schema.tables
                WHERE table_name = 'watchtower_pin_predictions'
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
        raise HTTPException(status_code=503, detail="WATCHTOWER engine not available")

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
    Get the status of all data sources used by WATCHTOWER.

    Returns detailed status including:
    - Tradier API connection status and any errors
    - WATCHTOWER engine availability
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

    # Check WATCHTOWER engine
    engine = get_engine()
    result["data_sources"]["watchtower_engine"] = {
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
            issues.append("WATCHTOWER engine not available")
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
