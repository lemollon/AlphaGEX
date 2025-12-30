"""
HYPERION (Weekly Gamma) API Routes
====================================

API endpoints for weekly options gamma visualization.
HYPERION focuses on stocks/ETFs with weekly options (not 0DTE).

Named after the Titan of Watchfulness - watching longer-term gamma setups.
"""

import logging
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any, Tuple
from fastapi import APIRouter, HTTPException, Query
from zoneinfo import ZoneInfo
import time

from database_adapter import get_connection

router = APIRouter(prefix="/api/hyperion", tags=["HYPERION"])
logger = logging.getLogger(__name__)

# Timezone
CENTRAL_TZ = ZoneInfo("America/Chicago")

# Cache
_cache: Dict[str, Any] = {}
_cache_times: Dict[str, float] = {}
CACHE_TTL_SECONDS = 60  # 60 second cache for weekly data (less volatile than 0DTE)

# History for ROC calculation - maps (symbol, strike) -> [(timestamp, gamma)]
_gamma_history: Dict[str, List[Tuple[datetime, float]]] = {}
HISTORY_MINUTES = 30  # Keep 30 minutes of history


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


def format_central_timestamp() -> str:
    """Get ISO formatted timestamp in Central timezone"""
    return datetime.now(CENTRAL_TZ).isoformat()


def update_gamma_history(symbol: str, strike: float, gamma: float, timestamp: datetime = None):
    """Update gamma history for a strike"""
    if timestamp is None:
        timestamp = datetime.now(CENTRAL_TZ)

    history_key = f"{symbol}_{strike}"
    if history_key not in _gamma_history:
        _gamma_history[history_key] = []

    _gamma_history[history_key].append((timestamp, gamma))

    # Keep only last 30 minutes of history
    cutoff = timestamp - timedelta(minutes=HISTORY_MINUTES)
    _gamma_history[history_key] = [
        (t, g) for t, g in _gamma_history[history_key] if t >= cutoff
    ]


def calculate_roc(symbol: str, strike: float, current_gamma: float, minutes: int = 1) -> float:
    """
    Calculate rate of change for a strike over specified minutes.

    Args:
        symbol: Stock symbol
        strike: Strike price
        current_gamma: Current gamma value
        minutes: Number of minutes to look back (1 or 5)

    Returns:
        Rate of change as percentage
    """
    history_key = f"{symbol}_{strike}"
    history = _gamma_history.get(history_key, [])

    if not history or len(history) < 2:
        return 0.0

    # Find value from X minutes ago
    now = datetime.now(CENTRAL_TZ)
    target_time = now - timedelta(minutes=minutes)
    old_gamma = None

    for timestamp, gamma in reversed(history):
        # Handle timezone-aware comparison
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=CENTRAL_TZ)
        if timestamp <= target_time:
            old_gamma = gamma
            break

    if old_gamma is None or old_gamma == 0:
        return 0.0

    roc = ((current_gamma - old_gamma) / abs(old_gamma)) * 100
    return round(roc, 2)


# ROC thresholds for danger zone detection
ROC_1MIN_SPIKE_THRESHOLD = 15.0  # % for SPIKE danger type
ROC_5MIN_BUILDING_THRESHOLD = 25.0  # % for BUILDING danger type
ROC_5MIN_COLLAPSING_THRESHOLD = -25.0  # % for COLLAPSING danger type


def identify_danger_zones(symbol: str, strikes: List[Dict]) -> List[Dict]:
    """
    Identify danger zones - strikes with rapid gamma changes.

    Thresholds:
    - BUILDING: 5-min ROC > +25%
    - COLLAPSING: 5-min ROC < -25%
    - SPIKE: 1-min ROC > +15%
    """
    danger_zones = []

    for strike_data in strikes:
        roc_1min = strike_data.get('roc_1min', 0)
        roc_5min = strike_data.get('roc_5min', 0)
        danger_type = None

        if roc_5min >= ROC_5MIN_BUILDING_THRESHOLD:
            danger_type = 'BUILDING'
        elif roc_5min <= ROC_5MIN_COLLAPSING_THRESHOLD:
            danger_type = 'COLLAPSING'
        elif roc_1min >= ROC_1MIN_SPIKE_THRESHOLD:
            danger_type = 'SPIKE'

        if danger_type:
            strike_data['is_danger'] = True
            strike_data['danger_type'] = danger_type
            danger_zones.append({
                'strike': strike_data['strike'],
                'danger_type': danger_type,
                'roc_1min': roc_1min,
                'roc_5min': roc_5min
            })

    return danger_zones


def detect_pinning_condition(
    strikes: List[Dict],
    spot_price: float,
    likely_pin: float,
    danger_zones: List[Dict]
) -> Dict:
    """
    Detect if the market is in a "pinning" condition.

    Pinning is detected when:
    1. No danger zones (gamma is stable, no significant ROC)
    2. Spot price is within 0.5% of likely pin strike
    3. Average absolute ROC is low (< 5%)

    Returns:
        Dict with pinning status and details
    """
    if not strikes or not likely_pin:
        return {'is_pinning': False}

    # Check 1: No danger zones
    has_no_danger = len(danger_zones) == 0

    # Check 2: Spot is close to pin (within 0.5%)
    distance_to_pin_pct = abs(spot_price - likely_pin) / spot_price * 100 if spot_price > 0 else 100
    is_near_pin = distance_to_pin_pct < 0.5

    # Check 3: Average ROC is low (stable gamma)
    roc_values = []
    for s in strikes:
        roc_1 = abs(s.get('roc_1min', 0))
        roc_5 = abs(s.get('roc_5min', 0))
        roc_values.extend([roc_1, roc_5])

    avg_roc = sum(roc_values) / len(roc_values) if roc_values else 0
    is_stable = avg_roc < 5.0  # Less than 5% average movement

    # Determine pinning status
    is_pinning = has_no_danger and (is_near_pin or is_stable)

    if is_pinning:
        if is_near_pin:
            message = f"PINNING: Price is pinning near ${likely_pin} strike (within {distance_to_pin_pct:.2f}%). Gamma stable, expect tight range."
        else:
            message = f"STABLE: No gamma movement detected (avg ROC: {avg_roc:.1f}%). Price likely to gravitate toward ${likely_pin} pin."

        return {
            'is_pinning': True,
            'pin_strike': likely_pin,
            'distance_to_pin_pct': round(distance_to_pin_pct, 2),
            'avg_roc': round(avg_roc, 2),
            'message': message,
            'trade_idea': 'Iron Condor or Credit Spread around pin strike may be favorable.'
        }

    return {'is_pinning': False}


# Try to import Tradier data fetcher
TRADIER_AVAILABLE = False
TradierDataFetcher = None
try:
    from data.tradier_data_fetcher import TradierDataFetcher
    TRADIER_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Tradier data fetcher not available: {e}")


def get_tradier():
    """Get the Tradier data fetcher instance"""
    if not TRADIER_AVAILABLE or TradierDataFetcher is None:
        return None
    try:
        return TradierDataFetcher()
    except Exception as e:
        logger.error(f"Failed to get Tradier fetcher: {e}")
        return None


def get_weekly_expirations(symbol: str, weeks: int = 4) -> List[Dict]:
    """
    Get weekly expiration dates for a symbol.

    Weekly options typically expire on Fridays.
    """
    tradier = get_tradier()
    if not tradier:
        # Return mock expirations
        return get_mock_expirations(weeks)

    try:
        # Get real expirations from Tradier
        expirations = tradier.get_option_expirations(symbol)
        today = date.today()

        weekly_exps = []
        for exp_str in expirations[:weeks * 2]:  # Get more than needed, filter later
            try:
                exp_date = datetime.strptime(exp_str, '%Y-%m-%d').date()
                if exp_date >= today:
                    dte = (exp_date - today).days
                    # Weekly options are typically Fridays (weekday 4)
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
        # Find next Friday
        days_until_friday = (4 - today.weekday() + 7) % 7
        if days_until_friday == 0 and i == 0:
            days_until_friday = 7  # If today is Friday, use next Friday
        friday = today + timedelta(days=days_until_friday + (i * 7))

        dte = (friday - today).days
        is_monthly = friday.day > 14 and friday.day <= 21

        expirations.append({
            'date': friday.strftime('%Y-%m-%d'),
            'dte': dte,
            'is_weekly': True,
            'is_monthly': is_monthly
        })

    return expirations


async def fetch_gamma_data(symbol: str, expiration: str) -> dict:
    """
    Fetch gamma data for a weekly options symbol.
    """
    cache_key = f"hyperion_gamma_{symbol}_{expiration}"
    cached = get_cached(cache_key)
    if cached:
        return cached

    tradier = get_tradier()
    if not tradier:
        logger.warning("HYPERION: Tradier not available, using mock data")
        return get_mock_gamma_data(symbol, expiration)

    try:
        # Get quote
        quote = tradier.get_quote(symbol)
        spot_price = quote.get('last', 0) or quote.get('close', 0)
        logger.info(f"HYPERION: {symbol} quote fetched, price=${spot_price}")

        # Get VIX
        from data.vix_fetcher import get_vix_price
        vix = get_vix_price()

        # Get options chain
        option_chain = tradier.get_option_chain(symbol, expiration)
        contracts = option_chain.chains.get(expiration, [])

        if len(contracts) == 0:
            logger.warning(f"HYPERION: No options data for {symbol} {expiration}")
            return get_mock_gamma_data(symbol, expiration, spot_price, vix)

        # Build strike data using O(1) lookup
        options_by_key = {}
        for contract in contracts:
            strike = contract.strike
            opt_type = contract.option_type
            if strike and opt_type:
                options_by_key[(strike, opt_type)] = contract

        unique_strikes = set(c.strike for c in contracts if c.strike)
        strikes = []

        timestamp = datetime.now(CENTRAL_TZ)
        for strike in sorted(unique_strikes):
            call = options_by_key.get((strike, 'call'))
            put = options_by_key.get((strike, 'put'))

            call_gamma = call.gamma if call else 0
            put_gamma = put.gamma if put else 0
            call_oi = call.open_interest if call else 0
            put_oi = put.open_interest if put else 0

            # Calculate net gamma (simplified)
            net_gamma = (call_gamma * call_oi - put_gamma * put_oi) * 100 * spot_price

            # Update history and calculate ROC
            update_gamma_history(symbol, strike, net_gamma, timestamp)
            roc_1min = calculate_roc(symbol, strike, net_gamma, minutes=1)
            roc_5min = calculate_roc(symbol, strike, net_gamma, minutes=5)

            strikes.append({
                'strike': strike,
                'net_gamma': net_gamma,
                'call_gamma': call_gamma,
                'put_gamma': put_gamma,
                'call_oi': call_oi,
                'put_oi': put_oi,
                'probability': 0,  # Would need ML model
                'gamma_change_pct': 0,
                'roc_1min': roc_1min,
                'roc_5min': roc_5min,
                'is_magnet': False,
                'magnet_rank': None,
                'is_pin': False,
                'is_danger': False,
                'danger_type': None,
                'gamma_flipped': False,
                'flip_direction': None
            })

        # Identify magnets (top 3 by absolute gamma)
        sorted_strikes = sorted(strikes, key=lambda s: abs(s['net_gamma']), reverse=True)
        for i, s in enumerate(sorted_strikes[:3]):
            s['is_magnet'] = True
            s['magnet_rank'] = i + 1

        # Calculate expected move (ATM straddle price)
        atm_strike = min(unique_strikes, key=lambda s: abs(s - spot_price))
        atm_call = options_by_key.get((atm_strike, 'call'))
        atm_put = options_by_key.get((atm_strike, 'put'))
        expected_move = 0
        if atm_call and atm_put:
            call_price = atm_call.last or atm_call.mid or 0
            put_price = atm_put.last or atm_put.mid or 0
            expected_move = call_price + put_price

        # Determine gamma regime
        total_net_gamma = sum(s['net_gamma'] for s in strikes)
        gamma_regime = 'POSITIVE' if total_net_gamma > 0 else 'NEGATIVE' if total_net_gamma < 0 else 'NEUTRAL'

        # Identify danger zones based on ROC thresholds
        danger_zones = identify_danger_zones(symbol, strikes)

        # Determine likely pin
        likely_pin = sorted_strikes[0]['strike'] if sorted_strikes else None

        # Detect pinning condition (stable gamma = likely to pin)
        pinning_status = detect_pinning_condition(strikes, spot_price, likely_pin, danger_zones)

        result = {
            'symbol': symbol,
            'spot_price': spot_price,
            'vix': vix,
            'expiration_date': expiration,
            'expected_move': expected_move,
            'total_net_gamma': total_net_gamma,
            'gamma_regime': gamma_regime,
            'regime_flipped': False,
            'market_status': 'open',
            'strikes': strikes,
            'magnets': [{'rank': i+1, 'strike': s['strike'], 'net_gamma': s['net_gamma'], 'probability': 0}
                       for i, s in enumerate(sorted_strikes[:3])],
            'likely_pin': likely_pin,
            'pin_probability': 0,
            'danger_zones': danger_zones,
            'pinning_status': pinning_status,
            'gamma_flips': [],
            'is_mock': False,
            'fetched_at': format_central_timestamp()
        }

        set_cached(cache_key, result)
        return result

    except Exception as e:
        logger.error(f"Error fetching HYPERION gamma data: {e}")
        return get_mock_gamma_data(symbol, expiration)


def get_mock_gamma_data(symbol: str, expiration: str, spot: float = None, vix: float = None) -> dict:
    """Return mock gamma data for development"""
    import random

    if spot is None:
        # Default prices by symbol
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

        # Simulate gamma distribution
        base_gamma = max(0, 0.05 - distance * 0.004) * 1e6
        net_gamma = base_gamma * (1 + random.uniform(-0.3, 0.3))
        if random.random() > 0.5:
            net_gamma = -net_gamma

        # Update history and calculate ROC for mock data too
        update_gamma_history(symbol, strike, net_gamma, timestamp)
        roc_1min = calculate_roc(symbol, strike, net_gamma, minutes=1)
        roc_5min = calculate_roc(symbol, strike, net_gamma, minutes=5)

        strikes.append({
            'strike': strike,
            'net_gamma': net_gamma,
            'probability': max(0, 20 - distance * 2),
            'gamma_change_pct': 0,
            'roc_1min': roc_1min,
            'roc_5min': roc_5min,
            'is_magnet': distance <= 1,
            'magnet_rank': distance + 1 if distance <= 2 else None,
            'is_pin': i == 0,
            'is_danger': False,
            'danger_type': None,
            'gamma_flipped': False,
            'flip_direction': None
        })

    # Sort by strike
    strikes.sort(key=lambda s: s['strike'], reverse=True)

    # Identify danger zones based on ROC thresholds
    danger_zones = identify_danger_zones(symbol, strikes)

    # Detect pinning condition
    pinning_status = detect_pinning_condition(strikes, spot, base_strike, danger_zones)

    return {
        'symbol': symbol,
        'spot_price': spot,
        'vix': vix,
        'expiration_date': expiration,
        'expected_move': spot * 0.02,  # ~2% move
        'total_net_gamma': sum(s['net_gamma'] for s in strikes),
        'gamma_regime': 'POSITIVE' if sum(s['net_gamma'] for s in strikes) > 0 else 'NEGATIVE',
        'regime_flipped': False,
        'market_status': 'closed',
        'strikes': strikes,
        'magnets': [{'rank': i+1, 'strike': s['strike'], 'net_gamma': s['net_gamma'], 'probability': s['probability']}
                   for i, s in enumerate(strikes[:3])],
        'likely_pin': base_strike,
        'pin_probability': 25.0,
        'danger_zones': danger_zones,
        'pinning_status': pinning_status,
        'gamma_flips': [],
        'is_mock': True,
        'fetched_at': format_central_timestamp()
    }


@router.get("/gamma")
async def get_hyperion_gamma(
    symbol: str = Query("AAPL", description="Stock/ETF symbol"),
    expiration: Optional[str] = Query(None, description="Expiration date YYYY-MM-DD")
):
    """
    Get weekly gamma data for a stock/ETF.

    Returns:
    - Net gamma per strike
    - Gamma magnets
    - Expected move
    """
    try:
        # Get default expiration if not provided
        if not expiration:
            expirations = get_weekly_expirations(symbol, weeks=1)
            if expirations:
                expiration = expirations[0]['date']
            else:
                expiration = (date.today() + timedelta(days=(4 - date.today().weekday() + 7) % 7 or 7)).strftime('%Y-%m-%d')

        data = await fetch_gamma_data(symbol, expiration)

        return {
            "success": True,
            "data": data
        }

    except Exception as e:
        logger.error(f"Error getting HYPERION gamma data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/expirations")
async def get_hyperion_expirations(
    symbol: str = Query("AAPL", description="Stock/ETF symbol"),
    weeks: int = Query(4, description="Number of weeks to return")
):
    """
    Get available weekly expirations for a symbol.
    """
    try:
        expirations = get_weekly_expirations(symbol, weeks)

        return {
            "success": True,
            "data": {
                "symbol": symbol,
                "expirations": expirations
            }
        }

    except Exception as e:
        logger.error(f"Error getting HYPERION expirations: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/symbols")
async def get_hyperion_symbols():
    """
    Get list of supported symbols for HYPERION.
    """
    symbols = [
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

    return {
        "success": True,
        "data": {
            "symbols": symbols,
            "count": len(symbols)
        }
    }
