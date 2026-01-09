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


# ==================== ROC HISTORY PERSISTENCE ====================
# Persist gamma history to database for ROC calculation continuity

_history_loaded: Dict[str, bool] = {}  # Track if we've loaded history from DB per symbol


def ensure_gamma_history_table():
    """Create the gamma history table if it doesn't exist"""
    try:
        conn = get_connection()
        if not conn:
            return False
        cursor = conn.cursor()
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
        # Create index for efficient lookups
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_argus_gamma_history_strike_time
            ON argus_gamma_history(symbol, strike, recorded_at DESC)
        """)
        # Create index for cleanup queries
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_argus_gamma_history_recorded_at
            ON argus_gamma_history(recorded_at)
        """)
        conn.commit()
        cursor.close()
        conn.close()
        logger.info("ARGUS: Gamma history table ensured")
        return True
    except Exception as e:
        logger.error(f"Failed to create gamma history table: {e}")
        return False


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
    if not ARGUS_AVAILABLE:
        return None
    try:
        return get_argus_engine()
    except Exception as e:
        logger.error(f"Failed to get ARGUS engine: {e}")
        return None


def get_tradier():
    """Get the Tradier data fetcher instance"""
    if not TRADIER_AVAILABLE or TradierDataFetcher is None:
        return None
    try:
        return TradierDataFetcher()
    except Exception as e:
        logger.error(f"Failed to get Tradier fetcher: {e}")
        return None


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
        logger.warning("ARGUS: Tradier not available, using mock data")
        # Get real prices for mock data
        spot, vix = await get_real_prices()
        result = get_mock_gamma_data(symbol, spot, vix)
        # Don't cache mock data - allow retry on next request
        return result

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

        # If no options (market closed/weekend), fall back to mock
        if options_count == 0:
            logger.warning("ARGUS: No options data available (market likely closed), using mock data")
            spot, vix_val = await get_real_prices()
            result = get_mock_gamma_data(symbol, spot, vix_val)
            # Don't cache mock data - allow retry on next request for live data
            return result

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
        spot, vix_val = await get_real_prices()
        result = get_mock_gamma_data(symbol, spot, vix_val)
        # Don't cache mock data on error - allow retry on next request
        return result


async def get_real_prices() -> tuple:
    """Fetch real SPY and VIX prices - NO FAKE FALLBACKS"""
    cache_key = "real_prices"
    cached = get_cached(cache_key, PRICE_CACHE_TTL)
    if cached:
        return cached

    # Get VIX directly using reliable vix_fetcher
    from data.vix_fetcher import get_vix_price

    # Get SPY from Tradier
    from data.tradier_data_fetcher import TradierDataFetcher
    tradier = TradierDataFetcher()
    spy_quote = tradier.get_quote('SPY')

    if not spy_quote or not spy_quote.get('last'):
        raise ValueError("Failed to get SPY price from Tradier")

    spot = float(spy_quote['last'])
    vix = get_vix_price()

    result = (spot, vix)
    set_cached(cache_key, result)
    return result


def get_mock_gamma_data(symbol: str = "SPY", spot: float = None, vix: float = None) -> dict:
    """Return mock gamma data for development/testing.
    Uses randomization to simulate live updates - marked as is_mock=True.
    """
    import random

    if spot is None:
        spot = 600.0
    if vix is None:
        vix = 18.0

    strikes = []
    base_strike = round(spot)

    for i in range(-5, 6):  # Fewer strikes, more realistic
        strike = base_strike + i
        distance = abs(i)

        # Simulate gamma distribution (higher near ATM)
        base_gamma = max(0, 0.05 - distance * 0.008)
        call_gamma = base_gamma * (1 + random.uniform(-0.2, 0.2))
        put_gamma = base_gamma * (1 + random.uniform(-0.2, 0.2))

        # Simulate OI - realistic values
        call_oi = int(max(500, 15000 - distance * 2000))
        put_oi = int(max(500, 15000 - distance * 2000))

        strikes.append({
            'strike': strike,
            'call_gamma': call_gamma,
            'put_gamma': put_gamma,
            'call_oi': call_oi,
            'put_oi': put_oi,
            'call_price': max(0.05, (spot - strike) + 2 if i < 0 else max(0.05, 2.0 - i * 0.4)),
            'put_price': max(0.05, (strike - spot) + 2 if i > 0 else max(0.05, 2.0 + i * 0.4)),
            'call_iv': 0.15 + abs(i) * 0.01,
            'put_iv': 0.17 + abs(i) * 0.01,
            'volume': int(max(100, 5000 - distance * 800))
        })

    return {
        'symbol': symbol,
        'spot_price': spot,
        'vix': vix,
        'expiration': date.today().strftime('%Y-%m-%d'),
        'strikes': strikes,
        'is_mock': True,  # Flag to indicate simulated data
        'fetched_at': format_central_timestamp()  # Actual fetch timestamp (Central timezone)
    }


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

    Shows what ARES, ATHENA, PHOENIX are doing relative to gamma structure.
    """
    try:
        positions = []

        # Check ARES positions
        try:
            from backend.api.routes.ares_routes import get_ares_positions
            ares_data = await get_ares_positions()
            if ares_data.get('success') and ares_data.get('data', {}).get('positions'):
                for pos in ares_data['data']['positions']:
                    positions.append({
                        'bot': 'ARES',
                        'strategy': 'Iron Condor',
                        'status': pos.get('status', 'open'),
                        'strikes': f"{pos.get('put_short_strike')}/{pos.get('call_short_strike')}",
                        'safe': True  # Will be calculated based on magnets
                    })
        except Exception:
            pass

        # Check ATHENA positions
        try:
            from backend.api.routes.athena_routes import get_athena_positions
            athena_data = await get_athena_positions()
            if athena_data.get('success') and athena_data.get('data', {}).get('positions'):
                for pos in athena_data['data']['positions']:
                    positions.append({
                        'bot': 'ATHENA',
                        'strategy': pos.get('strategy', 'Directional'),
                        'status': pos.get('status', 'open'),
                        'strikes': str(pos.get('strike', 'N/A')),
                        'safe': True
                    })
        except Exception:
            pass

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


@router.get("/patterns")
async def get_pattern_matches():
    """
    Get pattern match analysis.

    Compares current gamma structure to historical patterns.
    """
    engine = get_engine()
    if not engine or not engine.previous_snapshot:
        return {
            "success": True,
            "data": {
                "patterns": [],
                "message": "No pattern data available yet"
            }
        }

    try:
        # This would use historical data to find similar patterns
        # For now, return placeholder
        return {
            "success": True,
            "data": {
                "patterns": [],
                "current_structure": {
                    "gamma_regime": engine.previous_snapshot.gamma_regime,
                    "top_magnet": engine.previous_snapshot.magnets[0]['strike']
                        if engine.previous_snapshot.magnets else None,
                    "likely_pin": engine.previous_snapshot.likely_pin
                },
                "message": "Pattern matching will be available after collecting more historical data"
            }
        }

    except Exception as e:
        logger.error(f"Error getting pattern matches: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
