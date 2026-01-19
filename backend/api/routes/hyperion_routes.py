"""
HYPERION (Weekly Gamma) API Routes - Enhanced Version
======================================================

API endpoints for weekly options gamma visualization.
HYPERION focuses on stocks/ETFs with weekly options (not 0DTE).

Named after the Titan of Watchfulness - watching longer-term gamma setups.

Enhanced Features (matching ARGUS):
- ML probability calculation
- Market structure analysis (9 signals)
- Alerts system
- Pattern matching
- Gamma flip detection
- Strike trends
"""

import logging
import random
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any, Tuple
from fastapi import APIRouter, HTTPException, Query
from zoneinfo import ZoneInfo
import time

from database_adapter import get_connection

# Import shared gamma engine
try:
    from core.shared_gamma_engine import (
        get_shared_gamma_engine,
        SharedGammaEngine,
        StrikeData,
        Alert,
        MarketStructureSignals,
        AlertType,
        AlertPriority,
        DangerType,
        FlipDirection
    )
    SHARED_ENGINE_AVAILABLE = True
except ImportError as e:
    SHARED_ENGINE_AVAILABLE = False
    print(f"Warning: Could not import shared_gamma_engine: {e}")

router = APIRouter(prefix="/api/hyperion", tags=["HYPERION"])
logger = logging.getLogger(__name__)

# Timezone
CENTRAL_TZ = ZoneInfo("America/Chicago")

# Cache
_cache: Dict[str, Any] = {}
_cache_times: Dict[str, float] = {}
CACHE_TTL_SECONDS = 60

# History for ROC calculation - maps (symbol, strike) -> [(timestamp, gamma)]
_gamma_history: Dict[str, List[Tuple[datetime, float]]] = {}
HISTORY_MINUTES = 420  # 7 hours

# Previous snapshots for flip detection
_previous_snapshots: Dict[str, Dict] = {}  # symbol -> snapshot
_previous_magnets: Dict[str, List[float]] = {}  # symbol -> [magnet strikes]

# Alerts storage (in-memory, persisted to DB)
_active_alerts: Dict[str, List[Alert]] = {}  # symbol -> alerts

# Prior day data for market structure comparison
_prior_day_data: Dict[str, Dict] = {}

# Track loaded history per symbol
_history_loaded: Dict[str, bool] = {}

# Supported symbols
WEEKLY_SYMBOLS = [
    {'symbol': 'AAPL', 'name': 'Apple Inc.', 'sector': 'Technology'},
    {'symbol': 'MSFT', 'name': 'Microsoft Corp.', 'sector': 'Technology'},
    {'symbol': 'GOOGL', 'name': 'Alphabet Inc.', 'sector': 'Technology'},
    {'symbol': 'AMZN', 'name': 'Amazon.com Inc.', 'sector': 'Consumer'},
    {'symbol': 'NVDA', 'name': 'NVIDIA Corp.', 'sector': 'Technology'},
    {'symbol': 'META', 'name': 'Meta Platforms', 'sector': 'Technology'},
    {'symbol': 'TSLA', 'name': 'Tesla Inc.', 'sector': 'Consumer'},
    {'symbol': 'AMD', 'name': 'AMD Inc.', 'sector': 'Technology'},
    {'symbol': 'NFLX', 'name': 'Netflix Inc.', 'sector': 'Communication'},
    {'symbol': 'XLF', 'name': 'Financial Select ETF', 'sector': 'ETF'},
    {'symbol': 'XLE', 'name': 'Energy Select ETF', 'sector': 'ETF'},
    {'symbol': 'GLD', 'name': 'Gold ETF', 'sector': 'Commodity'},
    {'symbol': 'SLV', 'name': 'Silver ETF', 'sector': 'Commodity'},
    {'symbol': 'TLT', 'name': 'Treasury Bond ETF', 'sector': 'Fixed Income'},
]


def get_shared_engine() -> Optional[SharedGammaEngine]:
    """Get the shared gamma engine instance"""
    if SHARED_ENGINE_AVAILABLE:
        return get_shared_gamma_engine()
    return None


def ensure_tables():
    """Ensure all required tables exist"""
    try:
        conn = get_connection()
        if not conn:
            return False
        cursor = conn.cursor()

        # Unified gamma history table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS unified_gamma_history (
                id SERIAL PRIMARY KEY,
                system VARCHAR(10) NOT NULL,
                symbol VARCHAR(10) NOT NULL,
                expiration_date DATE,
                strike DECIMAL(10, 2) NOT NULL,
                net_gamma DECIMAL(20, 8) NOT NULL,
                call_gamma DECIMAL(20, 8),
                put_gamma DECIMAL(20, 8),
                call_oi INTEGER,
                put_oi INTEGER,
                spot_price DECIMAL(10, 2),
                recorded_at TIMESTAMP WITH TIME ZONE NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        """)

        # Alerts table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS gamma_alerts (
                id SERIAL PRIMARY KEY,
                system VARCHAR(10) NOT NULL,
                symbol VARCHAR(10) NOT NULL,
                alert_type VARCHAR(50) NOT NULL,
                strike DECIMAL(10, 2),
                message TEXT NOT NULL,
                priority VARCHAR(10) NOT NULL,
                spot_price DECIMAL(10, 2),
                old_value TEXT,
                new_value TEXT,
                acknowledged BOOLEAN DEFAULT FALSE,
                acknowledged_at TIMESTAMP WITH TIME ZONE,
                triggered_at TIMESTAMP WITH TIME ZONE NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        """)

        # Patterns table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS gamma_patterns (
                id SERIAL PRIMARY KEY,
                system VARCHAR(10) NOT NULL,
                symbol VARCHAR(10) NOT NULL,
                pattern_date DATE NOT NULL,
                spot_price DECIMAL(10, 2),
                open_price DECIMAL(10, 2),
                close_price DECIMAL(10, 2),
                day_high DECIMAL(10, 2),
                day_low DECIMAL(10, 2),
                gamma_regime VARCHAR(20),
                total_net_gamma DECIMAL(20, 8),
                top_magnet DECIMAL(10, 2),
                likely_pin DECIMAL(10, 2),
                flip_point DECIMAL(10, 2),
                call_wall DECIMAL(10, 2),
                put_wall DECIMAL(10, 2),
                vix DECIMAL(6, 2),
                outcome_direction VARCHAR(10),
                outcome_pct DECIMAL(6, 2),
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                UNIQUE(system, symbol, pattern_date)
            )
        """)

        # Danger zones table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS gamma_danger_zones (
                id SERIAL PRIMARY KEY,
                system VARCHAR(10) NOT NULL,
                symbol VARCHAR(10) NOT NULL,
                strike DECIMAL(10, 2) NOT NULL,
                danger_type VARCHAR(20) NOT NULL,
                roc_1min DECIMAL(10, 2),
                roc_5min DECIMAL(10, 2),
                spot_price DECIMAL(10, 2),
                distance_from_spot_pct DECIMAL(6, 2),
                is_active BOOLEAN DEFAULT TRUE,
                detected_at TIMESTAMP WITH TIME ZONE NOT NULL,
                resolved_at TIMESTAMP WITH TIME ZONE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        """)

        # Strike trends table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS gamma_strike_trends (
                id SERIAL PRIMARY KEY,
                system VARCHAR(10) NOT NULL,
                symbol VARCHAR(10) NOT NULL,
                strike DECIMAL(10, 2) NOT NULL,
                trend_date DATE NOT NULL,
                spike_count INTEGER DEFAULT 0,
                flip_count INTEGER DEFAULT 0,
                building_count INTEGER DEFAULT 0,
                collapsing_count INTEGER DEFAULT 0,
                peak_roc DECIMAL(10, 2),
                time_as_magnet_mins INTEGER DEFAULT 0,
                dominant_status VARCHAR(20),
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                UNIQUE(system, symbol, strike, trend_date)
            )
        """)

        # Create indexes
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_unified_gamma_hyperion
            ON unified_gamma_history(system, symbol, strike, recorded_at DESC)
            WHERE system = 'HYPERION'
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_gamma_alerts_hyperion
            ON gamma_alerts(system, symbol, triggered_at DESC)
            WHERE system = 'HYPERION'
        """)

        conn.commit()
        cursor.close()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Error ensuring tables: {e}")
        return False


def persist_gamma_history(symbol: str, strike: float, gamma: float,
                          timestamp: datetime, expiration: str = None):
    """Persist gamma history to unified table"""
    try:
        conn = get_connection()
        if not conn:
            return

        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO unified_gamma_history
                (system, symbol, strike, net_gamma, expiration_date, recorded_at)
            VALUES ('HYPERION', %s, %s, %s, %s, %s)
        """, (symbol, strike, gamma, expiration, timestamp))
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        logger.debug(f"Error persisting gamma history: {e}")


def load_gamma_history(symbol: str):
    """Load gamma history from database"""
    global _gamma_history, _history_loaded

    if _history_loaded.get(symbol, False):
        return

    try:
        conn = get_connection()
        if not conn:
            _history_loaded[symbol] = True
            return

        cursor = conn.cursor()
        cursor.execute("""
            SELECT strike, net_gamma, recorded_at
            FROM unified_gamma_history
            WHERE system = 'HYPERION'
            AND symbol = %s
            AND recorded_at > NOW() - INTERVAL '420 minutes'
            ORDER BY strike, recorded_at ASC
        """, (symbol,))

        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        for strike, gamma, recorded_at in rows:
            history_key = f"{symbol}_{float(strike)}"
            if history_key not in _gamma_history:
                _gamma_history[history_key] = []
            if recorded_at.tzinfo is None:
                recorded_at = recorded_at.replace(tzinfo=CENTRAL_TZ)
            _gamma_history[history_key].append((recorded_at, float(gamma)))

        _history_loaded[symbol] = True
        logger.info(f"HYPERION: Loaded gamma history for {symbol}")

    except Exception as e:
        logger.warning(f"Error loading gamma history: {e}")
        _history_loaded[symbol] = True


def persist_alert(alert: Alert, symbol: str):
    """Persist alert to database"""
    try:
        conn = get_connection()
        if not conn:
            return

        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO gamma_alerts
                (system, symbol, alert_type, strike, message, priority,
                 spot_price, old_value, new_value, triggered_at)
            VALUES ('HYPERION', %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (symbol, alert.alert_type, alert.strike, alert.message,
              alert.priority, alert.spot_price, alert.old_value,
              alert.new_value, alert.triggered_at))
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        logger.debug(f"Error persisting alert: {e}")


def persist_danger_zone(symbol: str, strike: float, danger_type: str,
                        roc_1min: float, roc_5min: float, spot_price: float):
    """Persist danger zone to database"""
    try:
        conn = get_connection()
        if not conn:
            return

        distance_pct = abs(strike - spot_price) / spot_price * 100 if spot_price > 0 else 0

        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO gamma_danger_zones
                (system, symbol, strike, danger_type, roc_1min, roc_5min,
                 spot_price, distance_from_spot_pct, detected_at)
            VALUES ('HYPERION', %s, %s, %s, %s, %s, %s, %s, NOW())
        """, (symbol, strike, danger_type, roc_1min, roc_5min,
              spot_price, distance_pct))
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        logger.debug(f"Error persisting danger zone: {e}")


def update_strike_trend(symbol: str, strike: float, status: str, is_magnet: bool):
    """Update strike trend statistics"""
    try:
        conn = get_connection()
        if not conn:
            return

        today = date.today()
        cursor = conn.cursor()

        # Upsert trend record
        cursor.execute("""
            INSERT INTO gamma_strike_trends
                (system, symbol, strike, trend_date, spike_count, flip_count,
                 building_count, collapsing_count, time_as_magnet_mins)
            VALUES ('HYPERION', %s, %s, %s, 0, 0, 0, 0, 0)
            ON CONFLICT (system, symbol, strike, trend_date) DO NOTHING
        """, (symbol, strike, today))

        # Update counts based on status
        if status == 'SPIKE':
            cursor.execute("""
                UPDATE gamma_strike_trends
                SET spike_count = spike_count + 1, updated_at = NOW()
                WHERE system = 'HYPERION' AND symbol = %s
                AND strike = %s AND trend_date = %s
            """, (symbol, strike, today))
        elif status == 'BUILDING':
            cursor.execute("""
                UPDATE gamma_strike_trends
                SET building_count = building_count + 1, updated_at = NOW()
                WHERE system = 'HYPERION' AND symbol = %s
                AND strike = %s AND trend_date = %s
            """, (symbol, strike, today))
        elif status == 'COLLAPSING':
            cursor.execute("""
                UPDATE gamma_strike_trends
                SET collapsing_count = collapsing_count + 1, updated_at = NOW()
                WHERE system = 'HYPERION' AND symbol = %s
                AND strike = %s AND trend_date = %s
            """, (symbol, strike, today))

        if is_magnet:
            cursor.execute("""
                UPDATE gamma_strike_trends
                SET time_as_magnet_mins = time_as_magnet_mins + 1, updated_at = NOW()
                WHERE system = 'HYPERION' AND symbol = %s
                AND strike = %s AND trend_date = %s
            """, (symbol, strike, today))

        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        logger.debug(f"Error updating strike trend: {e}")


def cleanup_old_data():
    """Clean up old history data (>8 hours)"""
    try:
        conn = get_connection()
        if not conn:
            return

        cursor = conn.cursor()
        cursor.execute("""
            DELETE FROM unified_gamma_history
            WHERE system = 'HYPERION'
            AND recorded_at < NOW() - INTERVAL '8 hours'
        """)
        deleted = cursor.rowcount
        conn.commit()
        cursor.close()
        conn.close()

        if deleted > 0:
            logger.debug(f"HYPERION: Cleaned up {deleted} old history entries")
    except Exception as e:
        logger.warning(f"Error cleaning up old data: {e}")


def get_cached(key: str, ttl: int = CACHE_TTL_SECONDS) -> Any:
    """Get cached value if not expired"""
    if key in _cache and key in _cache_times:
        if time.time() - _cache_times[key] < ttl:
            return _cache[key]
    return None


def set_cached(key: str, value: Any):
    """Set cache value"""
    _cache[key] = value
    _cache_times[key] = time.time()


def format_central_timestamp() -> str:
    """Get ISO formatted timestamp in Central timezone"""
    return datetime.now(CENTRAL_TZ).isoformat()


def update_gamma_history(symbol: str, strike: float, gamma: float,
                          timestamp: datetime = None):
    """Update in-memory gamma history"""
    if timestamp is None:
        timestamp = datetime.now(CENTRAL_TZ)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=CENTRAL_TZ)

    history_key = f"{symbol}_{strike}"
    if history_key not in _gamma_history:
        _gamma_history[history_key] = []

    _gamma_history[history_key].append((timestamp, gamma))

    # Trim to keep only recent history
    cutoff = timestamp - timedelta(minutes=HISTORY_MINUTES)
    _gamma_history[history_key] = [
        (t, g) for t, g in _gamma_history[history_key]
        if (t.replace(tzinfo=CENTRAL_TZ) if t.tzinfo is None else t) >= cutoff
    ]


def is_market_hours() -> bool:
    """Check if market is open (8:30 AM - 3:00 PM CT, Mon-Fri)"""
    now = datetime.now(CENTRAL_TZ)
    if now.weekday() >= 5:
        return False
    try:
        from trading.market_calendar import MARKET_HOLIDAYS_2024_2025
        if now.strftime('%Y-%m-%d') in MARKET_HOLIDAYS_2024_2025:
            return False
    except ImportError:
        pass
    time_minutes = now.hour * 60 + now.minute
    return 8 * 60 + 30 <= time_minutes < 15 * 60


# Try to import Tradier data fetcher
TRADIER_AVAILABLE = False
TradierDataFetcher = None
try:
    from data.tradier_data_fetcher import TradierDataFetcher
    TRADIER_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Tradier data fetcher not available: {e}")


def get_tradier():
    """Get Tradier data fetcher instance"""
    if not TRADIER_AVAILABLE or TradierDataFetcher is None:
        return None
    try:
        return TradierDataFetcher()
    except Exception as e:
        logger.error(f"Failed to get Tradier fetcher: {e}")
        return None


def get_weekly_expirations(symbol: str, weeks: int = 4) -> List[Dict]:
    """Get weekly expiration dates for a symbol"""
    tradier = get_tradier()
    if not tradier:
        return get_mock_expirations(weeks)

    try:
        expirations = tradier.get_option_expirations(symbol)
        today = date.today()

        weekly_exps = []
        for exp_str in expirations[:weeks * 2]:
            try:
                exp_date = datetime.strptime(exp_str, '%Y-%m-%d').date()
                if exp_date >= today:
                    dte = (exp_date - today).days
                    is_monthly = exp_date.day > 14 and exp_date.day <= 21 and exp_date.weekday() == 4
                    weekly_exps.append({
                        'date': exp_str,
                        'dte': dte,
                        'is_weekly': True,
                        'is_monthly': is_monthly
                    })
            except ValueError:
                continue

            if len(weekly_exps) >= weeks:
                break

        return weekly_exps
    except Exception as e:
        logger.error(f"Error fetching expirations for {symbol}: {e}")
        return get_mock_expirations(weeks)


def get_mock_expirations(weeks: int = 4) -> List[Dict]:
    """Generate mock weekly expirations"""
    today = date.today()
    expirations = []

    for i in range(weeks):
        days_until_friday = (4 - today.weekday() + 7) % 7
        if days_until_friday == 0 and i == 0:
            days_until_friday = 7
        friday = today + timedelta(days=days_until_friday + (i * 7))

        expirations.append({
            'date': friday.strftime('%Y-%m-%d'),
            'dte': (friday - today).days,
            'is_weekly': True,
            'is_monthly': friday.day > 14 and friday.day <= 21
        })

    return expirations


async def fetch_gamma_data(symbol: str, expiration: str) -> dict:
    """Fetch gamma data with all enhanced features"""
    global _previous_snapshots, _previous_magnets, _active_alerts, _prior_day_data

    # Ensure tables exist
    ensure_tables()

    # Cache check
    market_open = is_market_hours()
    cache_ttl = CACHE_TTL_SECONDS if market_open else 300
    cache_key = f"hyperion_gamma_{symbol}_{expiration}"
    cached = get_cached(cache_key, cache_ttl)
    if cached and not cached.get('is_mock', False):
        return cached

    # Load history from DB
    load_gamma_history(symbol)

    tradier = get_tradier()
    engine = get_shared_engine()

    if not tradier:
        logger.warning("HYPERION: Tradier not available, using mock data")
        return get_mock_gamma_data(symbol, expiration)

    try:
        # Get quote
        quote = tradier.get_quote(symbol)
        spot_price = quote.get('last', 0) or quote.get('close', 0)

        # Get VIX
        from data.vix_fetcher import get_vix_price
        vix = get_vix_price()

        # Get options chain
        option_chain = tradier.get_option_chain(symbol, expiration)
        contracts = option_chain.chains.get(expiration, [])

        if len(contracts) == 0:
            return get_mock_gamma_data(symbol, expiration, spot_price, vix)

        # Build strike data
        options_by_key = {}
        for contract in contracts:
            strike = contract.strike
            opt_type = contract.option_type
            if strike and opt_type:
                options_by_key[(strike, opt_type)] = contract

        unique_strikes = set(c.strike for c in contracts if c.strike)
        timestamp = datetime.now(CENTRAL_TZ)

        # Get previous snapshot for flip detection
        prev_snapshot = _previous_snapshots.get(symbol, {})
        prev_strikes = {s['strike']: s for s in prev_snapshot.get('strikes', [])}
        previous_regime = prev_snapshot.get('gamma_regime')

        strikes = []
        total_gamma = 0
        total_net_gamma = 0
        gamma_flips = []

        # Calculate expected move from ATM options
        atm_strike = min(unique_strikes, key=lambda s: abs(s - spot_price))
        atm_call = options_by_key.get((atm_strike, 'call'))
        atm_put = options_by_key.get((atm_strike, 'put'))
        expected_move = 0
        if atm_call and atm_put:
            call_price = atm_call.last or atm_call.mid or 0
            put_price = atm_put.last or atm_put.mid or 0
            if engine:
                expected_move = engine.calculate_expected_move(call_price, put_price)
            else:
                expected_move = call_price + put_price

        for strike in sorted(unique_strikes):
            call = options_by_key.get((strike, 'call'))
            put = options_by_key.get((strike, 'put'))

            call_gamma = call.gamma if call else 0
            put_gamma = put.gamma if put else 0
            call_oi = call.open_interest if call else 0
            put_oi = put.open_interest if put else 0

            # Calculate net gamma
            if engine:
                net_gamma = engine.calculate_net_gamma(
                    call_gamma, put_gamma, call_oi, put_oi, spot_price
                )
            else:
                net_gamma = (call_gamma * call_oi - put_gamma * put_oi) * 100 * spot_price

            total_gamma += abs(net_gamma)
            total_net_gamma += net_gamma

            # Detect gamma flip
            prev_strike_data = prev_strikes.get(strike)
            prev_gamma = prev_strike_data['net_gamma'] if prev_strike_data else 0
            flipped = False
            flip_dir = None

            if engine:
                flipped, flip_dir = engine.detect_gamma_flip(net_gamma, prev_gamma)
            elif prev_gamma != 0:
                if net_gamma > 0 and prev_gamma < 0:
                    flipped, flip_dir = True, "NEG_TO_POS"
                elif net_gamma < 0 and prev_gamma > 0:
                    flipped, flip_dir = True, "POS_TO_NEG"

            if flipped:
                gamma_flips.append({
                    'strike': strike,
                    'direction': flip_dir,
                    'gamma_before': prev_gamma,
                    'gamma_after': net_gamma,
                    'flipped_at': timestamp.isoformat()
                })

            # Update history and calculate ROC
            history_key = f"{symbol}_{strike}"
            update_gamma_history(symbol, strike, net_gamma, timestamp)
            history = _gamma_history.get(history_key, [])

            if engine:
                roc_data = engine.calculate_all_roc(net_gamma, history)
            else:
                roc_data = {
                    'roc_1min': 0, 'roc_5min': 0, 'roc_30min': 0,
                    'roc_1hr': 0, 'roc_4hr': 0, 'roc_trading_day': 0
                }

            strike_data = {
                'strike': strike,
                'net_gamma': net_gamma,
                'call_gamma': call_gamma,
                'put_gamma': put_gamma,
                'call_oi': call_oi,
                'put_oi': put_oi,
                'probability': 0,
                'gamma_change_pct': 0,
                'roc_1min': roc_data['roc_1min'],
                'roc_5min': roc_data['roc_5min'],
                'roc_30min': roc_data['roc_30min'],
                'roc_1hr': roc_data['roc_1hr'],
                'roc_4hr': roc_data['roc_4hr'],
                'roc_trading_day': roc_data['roc_trading_day'],
                'is_magnet': False,
                'magnet_rank': None,
                'is_pin': False,
                'is_danger': False,
                'danger_type': None,
                'gamma_flipped': flipped,
                'flip_direction': flip_dir
            }
            strikes.append(strike_data)

            # Persist to DB periodically
            if random.random() < 0.1:
                persist_gamma_history(symbol, strike, net_gamma, timestamp, expiration)

        # Build gamma_structure for ML predictions before calculating probabilities
        # Find magnets early (top 3 by gamma magnitude)
        sorted_by_gamma = sorted(strikes, key=lambda s: abs(s['net_gamma']), reverse=True)
        top_magnets = [{'strike': s['strike'], 'gamma': s['net_gamma']} for s in sorted_by_gamma[:3]]

        # Calculate flip point (weighted average of positive/negative gamma centers)
        positive_strikes = [s for s in strikes if s['net_gamma'] > 0]
        negative_strikes = [s for s in strikes if s['net_gamma'] < 0]
        if positive_strikes and negative_strikes:
            pos_weight = sum(abs(s['net_gamma']) for s in positive_strikes)
            neg_weight = sum(abs(s['net_gamma']) for s in negative_strikes)
            pos_center = sum(s['strike'] * abs(s['net_gamma']) for s in positive_strikes) / pos_weight if pos_weight else spot_price
            neg_center = sum(s['strike'] * abs(s['net_gamma']) for s in negative_strikes) / neg_weight if neg_weight else spot_price
            flip_point = (pos_center + neg_center) / 2
        else:
            flip_point = spot_price

        # Determine gamma regime
        net_gamma_sum = sum(s['net_gamma'] for s in strikes)
        if net_gamma_sum > total_gamma * 0.1:
            gamma_regime = 'POSITIVE'
        elif net_gamma_sum < -total_gamma * 0.1:
            gamma_regime = 'NEGATIVE'
        else:
            gamma_regime = 'NEUTRAL'

        # Build gamma_structure for ML
        gamma_structure = {
            'net_gamma': net_gamma_sum,
            'total_gamma': total_gamma,
            'flip_point': flip_point,
            'magnets': top_magnets,
            'vix': vix,
            'gamma_regime': gamma_regime,
            'expected_move': expected_move,
            'spot_price': spot_price
        }

        # Calculate probabilities using shared engine with gamma_structure
        if engine:
            for s in strikes:
                s['probability'] = engine.calculate_probability_hybrid(
                    s['strike'], spot_price, s['net_gamma'],
                    total_gamma, expected_move,
                    gamma_structure  # Pass gamma_structure for ML predictions
                )

            # Normalize probabilities
            total_prob = sum(s['probability'] for s in strikes)
            if total_prob > 0:
                for s in strikes:
                    s['probability'] = round((s['probability'] / total_prob) * 100, 1)

        # Identify magnets
        sorted_strikes = sorted(strikes, key=lambda s: abs(s['net_gamma']), reverse=True)
        magnets = []
        for i, s in enumerate(sorted_strikes[:3]):
            s['is_magnet'] = True
            s['magnet_rank'] = i + 1
            magnets.append({
                'rank': i + 1,
                'strike': s['strike'],
                'net_gamma': s['net_gamma'],
                'probability': s.get('probability', 0)
            })
            update_strike_trend(symbol, s['strike'], None, True)

        # Identify pin strike
        likely_pin = None
        pin_probability = 0
        if engine:
            strike_objs = [StrikeData(**s) for s in strikes]
            likely_pin, pin_probability = engine.identify_pin_strike(strike_objs, spot_price)
        else:
            if sorted_strikes:
                likely_pin = sorted_strikes[0]['strike']
                pin_probability = sorted_strikes[0].get('probability', 25)

        # Mark pin strike
        for s in strikes:
            if s['strike'] == likely_pin:
                s['is_pin'] = True

        # Identify danger zones
        danger_zones = []
        ROC_1MIN_SPIKE = 15.0
        ROC_5MIN_BUILDING = 25.0
        ROC_5MIN_COLLAPSING = -25.0

        for s in strikes:
            danger_type = None
            if s['roc_5min'] >= ROC_5MIN_BUILDING:
                danger_type = 'BUILDING'
            elif s['roc_5min'] <= ROC_5MIN_COLLAPSING:
                danger_type = 'COLLAPSING'
            elif s['roc_1min'] >= ROC_1MIN_SPIKE:
                danger_type = 'SPIKE'

            if danger_type:
                s['is_danger'] = True
                s['danger_type'] = danger_type
                danger_zones.append({
                    'strike': s['strike'],
                    'danger_type': danger_type,
                    'roc_1min': s['roc_1min'],
                    'roc_5min': s['roc_5min']
                })
                persist_danger_zone(symbol, s['strike'], danger_type,
                                    s['roc_1min'], s['roc_5min'], spot_price)
                update_strike_trend(symbol, s['strike'], danger_type, False)

        # Determine gamma regime
        if engine:
            gamma_regime = engine.classify_gamma_regime(total_net_gamma)
        else:
            if total_net_gamma > 1e9:
                gamma_regime = 'POSITIVE'
            elif total_net_gamma < -1e9:
                gamma_regime = 'NEGATIVE'
            else:
                gamma_regime = 'NEUTRAL'

        regime_flipped = previous_regime is not None and gamma_regime != previous_regime

        # Detect pinning condition
        pinning_status = {'is_pinning': False}
        if engine:
            strike_objs = [StrikeData(**s) for s in strikes]
            pinning_status = engine.detect_pinning_condition(
                strike_objs, spot_price, likely_pin, danger_zones
            )
        else:
            if len(danger_zones) == 0 and likely_pin:
                distance_pct = abs(spot_price - likely_pin) / spot_price * 100
                if distance_pct < 0.5:
                    pinning_status = {
                        'is_pinning': True,
                        'pin_strike': likely_pin,
                        'distance_to_pin_pct': round(distance_pct, 2),
                        'message': f'PINNING near ${likely_pin}',
                        'trade_idea': 'Iron Condor around pin may be favorable'
                    }

        # Calculate market structure (9 signals)
        market_structure = None
        if engine:
            prior_data = _prior_day_data.get(symbol, {})
            signals = engine.calculate_market_structure(
                spot_price, vix, expected_move, total_net_gamma,
                [StrikeData(**s) for s in strikes], prior_data
            )
            market_structure = signals.to_dict()

        # Generate alerts
        alerts = []
        if engine:
            prev_magnets = _previous_magnets.get(symbol, [])
            alerts = engine.generate_alerts(
                symbol, spot_price, gamma_regime, previous_regime,
                gamma_flips, danger_zones, likely_pin, magnets, prev_magnets
            )
            for alert in alerts:
                persist_alert(alert, symbol)

        # Store active alerts
        _active_alerts[symbol] = alerts

        # Update previous snapshot
        _previous_snapshots[symbol] = {
            'strikes': strikes,
            'gamma_regime': gamma_regime,
            'magnets': magnets,
            'spot_price': spot_price,
            'expected_move': expected_move,
            'total_net_gamma': total_net_gamma
        }
        _previous_magnets[symbol] = [m['strike'] for m in magnets]

        # Store for next day comparison
        _prior_day_data[symbol] = {
            'bounds_upper': spot_price + expected_move,
            'bounds_lower': spot_price - expected_move,
            'width': expected_move * 2,
            'flip_point': market_structure.get('flip_point', {}).get('current') if market_structure else None,
            'open_em': expected_move,
            'total_net_gamma': total_net_gamma
        }

        result = {
            'symbol': symbol,
            'spot_price': spot_price,
            'vix': vix,
            'expiration_date': expiration,
            'expected_move': expected_move,
            'total_net_gamma': total_net_gamma,
            'gamma_regime': gamma_regime,
            'regime_flipped': regime_flipped,
            'market_status': 'open' if market_open else 'closed',
            'strikes': strikes,
            'magnets': magnets,
            'likely_pin': likely_pin,
            'pin_probability': pin_probability,
            'danger_zones': danger_zones,
            'gamma_flips': gamma_flips,
            'pinning_status': pinning_status,
            'market_structure': market_structure,
            'is_mock': False,
            'fetched_at': format_central_timestamp()
        }

        # Cleanup old data periodically
        if random.random() < 0.01:
            cleanup_old_data()

        set_cached(cache_key, result)
        return result

    except Exception as e:
        logger.error(f"Error fetching HYPERION gamma data: {e}")
        import traceback
        traceback.print_exc()
        return get_mock_gamma_data(symbol, expiration)


def get_mock_gamma_data(symbol: str, expiration: str,
                        spot: float = None, vix: float = None) -> dict:
    """Return mock gamma data for development"""
    if spot is None:
        default_prices = {
            'AAPL': 195.0, 'MSFT': 425.0, 'GOOGL': 175.0, 'AMZN': 195.0,
            'NVDA': 140.0, 'META': 580.0, 'TSLA': 250.0, 'AMD': 145.0,
            'NFLX': 900.0, 'XLF': 45.0, 'XLE': 90.0, 'GLD': 240.0,
            'SLV': 28.0, 'TLT': 95.0
        }
        spot = default_prices.get(symbol, 100.0)

    if vix is None:
        vix = 18.0

    strikes = []
    base_strike = round(spot)
    timestamp = datetime.now(CENTRAL_TZ)

    for i in range(-10, 11):
        strike = base_strike + i
        distance = abs(i)

        base_gamma = max(0, 0.05 - distance * 0.004) * 1e6
        net_gamma = base_gamma * (1 + random.uniform(-0.3, 0.3))
        if random.random() > 0.5:
            net_gamma = -net_gamma

        update_gamma_history(symbol, strike, net_gamma, timestamp)

        strikes.append({
            'strike': strike,
            'net_gamma': net_gamma,
            'call_gamma': abs(net_gamma) * 0.6,
            'put_gamma': abs(net_gamma) * 0.4,
            'probability': max(0, 20 - distance * 2),
            'gamma_change_pct': 0,
            'roc_1min': 0,
            'roc_5min': 0,
            'roc_30min': 0,
            'roc_1hr': 0,
            'roc_4hr': 0,
            'roc_trading_day': 0,
            'is_magnet': distance <= 1,
            'magnet_rank': distance + 1 if distance <= 2 else None,
            'is_pin': i == 0,
            'is_danger': False,
            'danger_type': None,
            'gamma_flipped': False,
            'flip_direction': None
        })

    strikes.sort(key=lambda s: s['strike'], reverse=True)

    return {
        'symbol': symbol,
        'spot_price': spot,
        'vix': vix,
        'expiration_date': expiration,
        'expected_move': spot * 0.02,
        'total_net_gamma': sum(s['net_gamma'] for s in strikes),
        'gamma_regime': 'POSITIVE' if sum(s['net_gamma'] for s in strikes) > 0 else 'NEGATIVE',
        'regime_flipped': False,
        'market_status': 'closed',
        'strikes': strikes,
        'magnets': [{'rank': i+1, 'strike': s['strike'], 'net_gamma': s['net_gamma'],
                    'probability': s['probability']} for i, s in enumerate(strikes[:3])],
        'likely_pin': base_strike,
        'pin_probability': 25.0,
        'danger_zones': [],
        'gamma_flips': [],
        'pinning_status': {'is_pinning': False},
        'market_structure': None,
        'is_mock': True,
        'fetched_at': format_central_timestamp()
    }


# ==================== API ENDPOINTS ====================

@router.get("/gamma")
async def get_hyperion_gamma(
    symbol: str = Query("AAPL", description="Stock/ETF symbol"),
    expiration: Optional[str] = Query(None, description="Expiration date YYYY-MM-DD")
):
    """
    Get weekly gamma data for a stock/ETF.

    Returns comprehensive gamma analysis including:
    - Net gamma per strike with ROC
    - ML-powered probability
    - Market structure (9 signals)
    - Danger zones and alerts
    """
    try:
        if not expiration:
            expirations = get_weekly_expirations(symbol, weeks=1)
            if expirations:
                expiration = expirations[0]['date']
            else:
                expiration = (date.today() + timedelta(days=(4 - date.today().weekday() + 7) % 7 or 7)).strftime('%Y-%m-%d')

        data = await fetch_gamma_data(symbol, expiration)

        return {"success": True, "data": data}

    except Exception as e:
        logger.error(f"Error getting HYPERION gamma data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/expirations")
async def get_hyperion_expirations(
    symbol: str = Query("AAPL", description="Stock/ETF symbol"),
    weeks: int = Query(4, description="Number of weeks to return")
):
    """Get available weekly expirations for a symbol."""
    try:
        expirations = get_weekly_expirations(symbol, weeks)
        return {
            "success": True,
            "data": {"symbol": symbol, "expirations": expirations}
        }
    except Exception as e:
        logger.error(f"Error getting HYPERION expirations: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/symbols")
async def get_hyperion_symbols():
    """Get list of supported symbols for HYPERION."""
    return {
        "success": True,
        "data": {"symbols": WEEKLY_SYMBOLS, "count": len(WEEKLY_SYMBOLS)}
    }


@router.get("/alerts")
async def get_hyperion_alerts(
    symbol: str = Query("AAPL", description="Stock/ETF symbol"),
    limit: int = Query(20, description="Max alerts to return"),
    acknowledged: Optional[bool] = Query(None, description="Filter by acknowledged status")
):
    """
    Get active alerts for a symbol.

    Alert types:
    - GAMMA_FLIP: Strike gamma crossed zero
    - REGIME_CHANGE: Overall regime shifted
    - MAGNET_SHIFT: Top magnet changed
    - DANGER_ZONE: Strike entered danger zone
    - PIN_ZONE_ENTRY: Price near pin strike
    """
    try:
        conn = get_connection()
        if not conn:
            # Return in-memory alerts
            alerts = _active_alerts.get(symbol, [])
            return {
                "success": True,
                "data": {
                    "alerts": [a.to_dict() if hasattr(a, 'to_dict') else a for a in alerts[:limit]],
                    "count": len(alerts),
                    "source": "memory"
                }
            }

        cursor = conn.cursor()

        query = """
            SELECT id, alert_type, strike, message, priority, spot_price,
                   old_value, new_value, acknowledged, triggered_at
            FROM gamma_alerts
            WHERE system = 'HYPERION' AND symbol = %s
        """
        params = [symbol]

        if acknowledged is not None:
            query += " AND acknowledged = %s"
            params.append(acknowledged)

        query += " ORDER BY triggered_at DESC LIMIT %s"
        params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        alerts = [{
            'id': row[0],
            'alert_type': row[1],
            'strike': float(row[2]) if row[2] else None,
            'message': row[3],
            'priority': row[4],
            'spot_price': float(row[5]) if row[5] else None,
            'old_value': row[6],
            'new_value': row[7],
            'acknowledged': row[8],
            'triggered_at': row[9].isoformat() if row[9] else None
        } for row in rows]

        return {
            "success": True,
            "data": {"alerts": alerts, "count": len(alerts), "source": "database"}
        }

    except Exception as e:
        logger.error(f"Error getting HYPERION alerts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/alerts/{alert_id}/acknowledge")
async def acknowledge_hyperion_alert(alert_id: int):
    """Acknowledge an alert by ID."""
    try:
        conn = get_connection()
        if not conn:
            raise HTTPException(status_code=503, detail="Database unavailable")

        cursor = conn.cursor()
        cursor.execute("""
            UPDATE gamma_alerts
            SET acknowledged = TRUE, acknowledged_at = NOW()
            WHERE id = %s AND system = 'HYPERION'
            RETURNING id
        """, (alert_id,))

        result = cursor.fetchone()
        conn.commit()
        cursor.close()
        conn.close()

        if result:
            return {"success": True, "data": {"acknowledged_id": alert_id}}
        else:
            raise HTTPException(status_code=404, detail="Alert not found")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error acknowledging alert: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/patterns")
async def get_hyperion_patterns(
    symbol: str = Query("AAPL", description="Stock/ETF symbol"),
    days: int = Query(30, description="Days of history to analyze"),
    min_similarity: float = Query(0.7, description="Minimum similarity score")
):
    """
    Get historical pattern matches for current gamma structure.

    Finds similar historical setups and their outcomes.
    """
    try:
        conn = get_connection()
        patterns = []

        if conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT pattern_date, spot_price, open_price, close_price,
                       day_high, day_low, gamma_regime, total_net_gamma,
                       top_magnet, likely_pin, flip_point, call_wall, put_wall,
                       vix, outcome_direction, outcome_pct
                FROM gamma_patterns
                WHERE system = 'HYPERION' AND symbol = %s
                AND pattern_date > NOW() - INTERVAL '%s days'
                ORDER BY pattern_date DESC
            """, (symbol, days))

            rows = cursor.fetchall()
            cursor.close()
            conn.close()

            for row in rows:
                patterns.append({
                    'date': row[0].strftime('%Y-%m-%d') if row[0] else None,
                    'spot_price': float(row[1]) if row[1] else None,
                    'open_price': float(row[2]) if row[2] else None,
                    'close_price': float(row[3]) if row[3] else None,
                    'day_high': float(row[4]) if row[4] else None,
                    'day_low': float(row[5]) if row[5] else None,
                    'gamma_regime': row[6],
                    'total_net_gamma': float(row[7]) if row[7] else None,
                    'top_magnet': float(row[8]) if row[8] else None,
                    'likely_pin': float(row[9]) if row[9] else None,
                    'flip_point': float(row[10]) if row[10] else None,
                    'call_wall': float(row[11]) if row[11] else None,
                    'put_wall': float(row[12]) if row[12] else None,
                    'vix': float(row[13]) if row[13] else None,
                    'outcome_direction': row[14],
                    'outcome_pct': float(row[15]) if row[15] else None,
                    'similarity_score': 0.75  # Placeholder - would calculate based on current structure
                })

        # Get current structure for comparison
        current = _previous_snapshots.get(symbol, {})

        return {
            "success": True,
            "data": {
                "patterns": patterns,
                "current_structure": {
                    "gamma_regime": current.get('gamma_regime'),
                    "top_magnet": current.get('magnets', [{}])[0].get('strike') if current.get('magnets') else None,
                    "likely_pin": current.get('likely_pin')
                },
                "message": f"Found {len(patterns)} historical patterns" if patterns else "No pattern data yet - patterns build over time"
            }
        }

    except Exception as e:
        logger.error(f"Error getting HYPERION patterns: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/strike-trends")
async def get_hyperion_strike_trends(
    symbol: str = Query("AAPL", description="Stock/ETF symbol"),
    date_str: Optional[str] = Query(None, description="Date YYYY-MM-DD (default: today)")
):
    """
    Get strike behavior trends for the day.

    Shows which strikes have been most active (spikes, flips, magnet time).
    """
    try:
        if date_str:
            trend_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        else:
            trend_date = date.today()

        conn = get_connection()
        trends = {}

        if conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT strike, spike_count, flip_count, building_count,
                       collapsing_count, peak_roc, time_as_magnet_mins,
                       dominant_status
                FROM gamma_strike_trends
                WHERE system = 'HYPERION' AND symbol = %s AND trend_date = %s
                ORDER BY spike_count + flip_count + building_count + collapsing_count DESC
            """, (symbol, trend_date))

            rows = cursor.fetchall()
            cursor.close()
            conn.close()

            for row in rows:
                strike = float(row[0])
                trends[str(strike)] = {
                    'strike': strike,
                    'spike_count': row[1],
                    'flip_count': row[2],
                    'building_count': row[3],
                    'collapsing_count': row[4],
                    'peak_roc': float(row[5]) if row[5] else 0,
                    'time_as_magnet_mins': row[6],
                    'dominant_status': row[7] or 'NEUTRAL',
                    'total_events': row[1] + row[2] + row[3] + row[4]
                }

        return {
            "success": True,
            "data": {
                "trends": trends,
                "date": trend_date.strftime('%Y-%m-%d'),
                "symbol": symbol
            }
        }

    except Exception as e:
        logger.error(f"Error getting HYPERION strike trends: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/gamma-flips")
async def get_hyperion_gamma_flips(
    symbol: str = Query("AAPL", description="Stock/ETF symbol"),
    minutes: int = Query(30, description="Lookback period in minutes")
):
    """
    Get recent gamma flips (sign changes) for a symbol.

    Gamma flips indicate significant repositioning.
    """
    try:
        cutoff = datetime.now(CENTRAL_TZ) - timedelta(minutes=minutes)
        flips = []

        # Check in-memory recent data
        prev = _previous_snapshots.get(symbol, {})
        for s in prev.get('strikes', []):
            if s.get('gamma_flipped'):
                flips.append({
                    'strike': s['strike'],
                    'direction': s.get('flip_direction'),
                    'flipped_at': datetime.now(CENTRAL_TZ).isoformat(),
                    'gamma_before': s.get('previous_net_gamma', 0),
                    'gamma_after': s['net_gamma'],
                    'mins_ago': 0
                })

        return {
            "success": True,
            "data": {
                "flips": flips,
                "lookback_minutes": minutes,
                "symbol": symbol
            }
        }

    except Exception as e:
        logger.error(f"Error getting HYPERION gamma flips: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/danger-zones/log")
async def get_hyperion_danger_zone_logs(
    symbol: str = Query("AAPL", description="Stock/ETF symbol"),
    limit: int = Query(50, description="Max logs to return"),
    active_only: bool = Query(False, description="Only show active danger zones")
):
    """
    Get danger zone history for a symbol.

    Shows when strikes entered/exited danger zones.
    """
    try:
        conn = get_connection()
        logs = []

        if conn:
            cursor = conn.cursor()

            query = """
                SELECT id, strike, danger_type, roc_1min, roc_5min,
                       spot_price, distance_from_spot_pct, is_active,
                       detected_at, resolved_at
                FROM gamma_danger_zones
                WHERE system = 'HYPERION' AND symbol = %s
            """
            params = [symbol]

            if active_only:
                query += " AND is_active = TRUE"

            query += " ORDER BY detected_at DESC LIMIT %s"
            params.append(limit)

            cursor.execute(query, params)
            rows = cursor.fetchall()
            cursor.close()
            conn.close()

            for row in rows:
                logs.append({
                    'id': row[0],
                    'strike': float(row[1]),
                    'danger_type': row[2],
                    'roc_1min': float(row[3]) if row[3] else 0,
                    'roc_5min': float(row[4]) if row[4] else 0,
                    'spot_price': float(row[5]) if row[5] else None,
                    'distance_from_spot_pct': float(row[6]) if row[6] else None,
                    'is_active': row[7],
                    'detected_at': row[8].isoformat() if row[8] else None,
                    'resolved_at': row[9].isoformat() if row[9] else None
                })

        return {
            "success": True,
            "data": {"logs": logs, "count": len(logs), "symbol": symbol}
        }

    except Exception as e:
        logger.error(f"Error getting HYPERION danger zone logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/context")
async def get_hyperion_context(
    symbol: str = Query("AAPL", description="Stock/ETF symbol")
):
    """
    Get market context for a symbol.

    Includes walls, psychology traps, RSI alignment, etc.
    """
    try:
        prev = _previous_snapshots.get(symbol, {})
        strikes = prev.get('strikes', [])

        # Find walls
        call_wall = None
        put_wall = None
        positive_gamma = [s for s in strikes if s['net_gamma'] > 0]
        negative_gamma = [s for s in strikes if s['net_gamma'] < 0]

        if positive_gamma:
            call_wall = max(positive_gamma, key=lambda s: s['net_gamma'])['strike']
        if negative_gamma:
            put_wall = min(negative_gamma, key=lambda s: s['net_gamma'])['strike']

        spot_price = prev.get('spot_price', 0)

        context = {
            'gamma_walls': {
                'call_wall': call_wall,
                'call_wall_distance': abs(spot_price - call_wall) if call_wall and spot_price else None,
                'put_wall': put_wall,
                'put_wall_distance': abs(spot_price - put_wall) if put_wall and spot_price else None,
                'net_gamma_regime': prev.get('gamma_regime')
            },
            'monthly_magnets': {
                'above': call_wall,
                'below': put_wall
            },
            'regime': {
                'type': prev.get('gamma_regime'),
                'direction': 'BULLISH' if prev.get('gamma_regime') == 'POSITIVE' else 'BEARISH' if prev.get('gamma_regime') == 'NEGATIVE' else 'NEUTRAL'
            }
        }

        return {"success": True, "data": context}

    except Exception as e:
        logger.error(f"Error getting HYPERION context: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/accuracy")
async def get_hyperion_accuracy(
    symbol: str = Query("AAPL", description="Stock/ETF symbol")
):
    """
    Get prediction accuracy metrics for a symbol.

    Shows how accurate pin predictions and magnet hits have been.
    """
    try:
        conn = get_connection()

        if not conn:
            return {
                "success": True,
                "data": {
                    "message": "Accuracy metrics build over time",
                    "pin_accuracy_7d": 0,
                    "pin_accuracy_30d": 0,
                    "direction_accuracy_7d": 0,
                    "direction_accuracy_30d": 0,
                    "magnet_hit_rate_7d": 0,
                    "magnet_hit_rate_30d": 0,
                    "total_predictions": 0
                }
            }

        cursor = conn.cursor()

        # Count patterns with outcomes
        cursor.execute("""
            SELECT COUNT(*) FROM gamma_patterns
            WHERE system = 'HYPERION' AND symbol = %s
            AND outcome_direction IS NOT NULL
        """, (symbol,))
        total = cursor.fetchone()[0]

        cursor.close()
        conn.close()

        return {
            "success": True,
            "data": {
                "message": f"Based on {total} historical observations" if total > 0 else "Building accuracy metrics over time",
                "pin_accuracy_7d": 0,
                "pin_accuracy_30d": 0,
                "direction_accuracy_7d": 0,
                "direction_accuracy_30d": 0,
                "magnet_hit_rate_7d": 0,
                "magnet_hit_rate_30d": 0,
                "total_predictions": total
            }
        }

    except Exception as e:
        logger.error(f"Error getting HYPERION accuracy: {e}")
        raise HTTPException(status_code=500, detail=str(e))
