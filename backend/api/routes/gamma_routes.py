"""
Gamma Intelligence API routes.

Handles gamma analytics, probabilities, expiration analysis, and waterfall data.

Bug #5 Fix: Uses singleton instances for API clients to avoid recreation overhead.
Bug #7 Fix: Improved error logging for fallback chain.
Bug #12 Fix: Added data_source and data_age tracking for stale data indication.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from fastapi import APIRouter, HTTPException
import psycopg2.extras

# Import centralized utilities
from backend.api.utils import safe_round, safe_float, clean_dict_for_json

logger = logging.getLogger(__name__)

# Bug #5 Fix: Singleton instances for API clients
_trading_volatility_api = None
_gex_calculator = None


def get_trading_volatility_api():
    """Get singleton TradingVolatilityAPI instance."""
    global _trading_volatility_api
    if _trading_volatility_api is None:
        try:
            from core_classes_and_engines import TradingVolatilityAPI
            _trading_volatility_api = TradingVolatilityAPI()
            logger.info("TradingVolatilityAPI singleton initialized")
        except Exception as e:
            logger.error(f"Failed to initialize TradingVolatilityAPI: {e}")
            return None
    return _trading_volatility_api


def get_gex_calculator_instance():
    """Get singleton GEX calculator instance."""
    global _gex_calculator
    if _gex_calculator is None:
        try:
            from data.gex_calculator import get_gex_calculator
            _gex_calculator = get_gex_calculator()
            logger.info("GEX Calculator singleton initialized")
        except Exception as e:
            logger.error(f"Failed to initialize GEX Calculator: {e}")
            return None
    return _gex_calculator


def get_gex_with_fallback(symbol: str) -> Dict[str, Any]:
    """
    Get GEX data with intelligent fallback chain:
    1. TradingVolatilityAPI (live data)
    2. Tradier calculation (real-time from options chain)
    3. Database (historical cache)

    Bug #5 Fix: Uses singleton API instance
    Bug #7 Fix: Improved error logging
    Bug #12 Fix: Returns data_source for stale data indication
    """
    # PRIMARY: Try TradingVolatilityAPI (singleton)
    try:
        api = get_trading_volatility_api()
        if api:
            data = api.get_net_gamma(symbol)
            if data and 'error' not in data:
                data['data_source'] = 'live_api'
                data['data_age'] = 'live'
                return data
            elif data and 'error' in data:
                logger.warning(f"TradingVolatilityAPI returned error for {symbol}: {data.get('error')}")
    except Exception as e:
        logger.warning(f"TradingVolatilityAPI failed for {symbol}: {type(e).__name__}: {str(e)}")

    # FALLBACK 1: Calculate from Tradier (singleton)
    try:
        calculator = get_gex_calculator_instance()
        if calculator:
            data = calculator.get_gex(symbol)
            if data and 'error' not in data:
                data['data_source'] = 'tradier_calculated'
                data['data_age'] = 'live'
                logger.info(f"GEX calculated from Tradier for {symbol}")
                return data
            elif data and 'error' in data:
                # Bug #7 Fix: Log the actual error
                logger.warning(f"Tradier GEX calculation returned error for {symbol}: {data.get('error')}")
    except ValueError as e:
        # Bug #7 Fix: Log API key issues clearly
        logger.error(f"Tradier GEX calculation failed for {symbol} - API key issue: {str(e)}")
    except Exception as e:
        logger.warning(f"Tradier GEX calculation failed for {symbol}: {type(e).__name__}: {str(e)}")

    # FALLBACK 2: Try database
    try:
        from database_adapter import get_connection
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute("""
            SELECT net_gex, flip_point, call_wall, put_wall, spot_price,
                   mm_state, regime, timestamp
            FROM gex_history
            WHERE symbol = %s AND timestamp >= NOW() - INTERVAL '7 days'
            ORDER BY timestamp DESC LIMIT 1
        """, (symbol,))
        row = cursor.fetchone()
        conn.close()
        if row:
            # Bug #12 Fix: Calculate data age for stale indicator
            data_timestamp = row.get('timestamp')
            if data_timestamp:
                age_hours = (datetime.now() - data_timestamp).total_seconds() / 3600
                if age_hours < 1:
                    data_age = 'recent'
                elif age_hours < 24:
                    data_age = f'{int(age_hours)}h old'
                else:
                    data_age = f'{int(age_hours / 24)}d old'
            else:
                data_age = 'unknown'

            logger.info(f"Using database GEX for {symbol} (age: {data_age})")
            return {
                'symbol': symbol,
                'spot_price': float(row.get('spot_price') or 0),
                'net_gex': float(row.get('net_gex') or 0),
                'flip_point': float(row.get('flip_point') or 0),
                'call_wall': float(row.get('call_wall') or 0),
                'put_wall': float(row.get('put_wall') or 0),
                'mm_state': row.get('mm_state'),
                'regime': row.get('regime'),
                'collection_date': row.get('timestamp').strftime('%Y-%m-%d') if row.get('timestamp') else None,
                'data_source': 'database_fallback',
                'data_age': data_age
            }
    except Exception as e:
        logger.error(f"Database fallback failed for {symbol}: {type(e).__name__}: {str(e)}")

    return {'error': 'All data sources failed', 'data_source': 'none'}


def get_gex_profile_with_fallback(symbol: str) -> Optional[Dict[str, Any]]:
    """
    Get detailed GEX profile with fallback to Tradier calculation.

    Bug #5 Fix: Uses singleton API instance
    Bug #6 Fix: Returns proper error dict instead of empty dict on rate limit
    Bug #7 Fix: Improved error logging
    """
    # PRIMARY: Try TradingVolatilityAPI (singleton)
    try:
        api = get_trading_volatility_api()
        if api:
            profile = api.get_gex_profile(symbol)
            if profile and 'error' not in profile and profile.get('strikes'):
                profile['profile_source'] = 'live_api'
                return profile
            elif profile and 'error' in profile:
                logger.warning(f"TradingVolatilityAPI profile returned error for {symbol}: {profile.get('error')}")
            elif profile and not profile.get('strikes'):
                logger.warning(f"TradingVolatilityAPI profile returned no strikes for {symbol} (rate limited?)")
    except Exception as e:
        logger.warning(f"TradingVolatilityAPI profile failed for {symbol}: {type(e).__name__}: {str(e)}")

    # FALLBACK: Calculate from Tradier (singleton)
    try:
        calculator = get_gex_calculator_instance()
        if calculator:
            profile = calculator.get_gex_profile(symbol)
            if profile and 'error' not in profile:
                profile['profile_source'] = 'tradier_calculated'
                logger.info(f"GEX profile calculated from Tradier for {symbol}")
                return profile
            elif profile and 'error' in profile:
                logger.warning(f"Tradier GEX profile returned error for {symbol}: {profile.get('error')}")
    except ValueError as e:
        # Bug #7 Fix: Log API key issues clearly
        logger.error(f"Tradier GEX profile failed for {symbol} - API key issue: {str(e)}")
    except Exception as e:
        logger.warning(f"Tradier GEX profile calculation failed for {symbol}: {type(e).__name__}: {str(e)}")

    return None


def get_last_trading_day():
    """Get the last trading day date"""
    now = datetime.now()
    if now.weekday() == 5:  # Saturday
        return (now - timedelta(days=1)).strftime('%Y-%m-%d')
    elif now.weekday() == 6:  # Sunday
        return (now - timedelta(days=2)).strftime('%Y-%m-%d')
    elif now.hour < 9 or (now.hour == 9 and now.minute < 30):
        # Before market open
        if now.weekday() == 0:  # Monday
            return (now - timedelta(days=3)).strftime('%Y-%m-%d')
        else:
            return (now - timedelta(days=1)).strftime('%Y-%m-%d')
    return now.strftime('%Y-%m-%d')

router = APIRouter(prefix="/api/gamma", tags=["Gamma Intelligence"])


# Note: safe_round is imported from backend.api.utils


@router.get("/{symbol}/intelligence")
async def get_gamma_intelligence(symbol: str, vix: float = 20):
    """
    Get comprehensive gamma intelligence for a symbol.
    Returns gamma metrics, market regime, and MM state analysis.
    Uses fallback chain: TradingVolatilityAPI -> Tradier calculation -> Database
    """
    try:
        from core.strategy_stats import calculate_mm_confidence, get_mm_states

        symbol = symbol.upper()

        # Get basic GEX data with fallback chain
        gex_data = get_gex_with_fallback(symbol)
        if not gex_data or gex_data.get('error'):
            error_msg = gex_data.get('error', 'Unknown error') if gex_data else 'No data returned'
            raise HTTPException(status_code=404, detail=f"GEX data not available for {symbol}: {error_msg}")

        # Try to get detailed profile (with fallback)
        profile = get_gex_profile_with_fallback(symbol)

        # Calculate gamma from strike data or estimate
        total_call_gamma = 0
        total_put_gamma = 0

        if profile and profile.get('strikes'):
            for strike in profile['strikes']:
                total_call_gamma += strike.get('call_gamma', 0)
                total_put_gamma += strike.get('put_gamma', 0)

        # Track if gamma values are estimated (no real strike-level data available)
        gamma_is_estimated = False
        if total_call_gamma == 0 and total_put_gamma == 0:
            gamma_is_estimated = True
            logger.info(f"Estimating gamma split for {symbol} - no strike-level data available")
            net_gex = gex_data.get('net_gex', 0)
            if net_gex > 0:
                total_call_gamma = abs(net_gex) * 0.6
                total_put_gamma = abs(net_gex) * 0.4
            else:
                total_call_gamma = abs(net_gex) * 0.4
                total_put_gamma = abs(net_gex) * 0.6

        net_gex = gex_data.get('net_gex', 0)
        spot_price = gex_data.get('spot_price', 0)
        total_gamma = total_call_gamma + total_put_gamma
        gamma_exposure_ratio = total_call_gamma / total_put_gamma if total_put_gamma > 0 else 0
        risk_reversal = (total_call_gamma - total_put_gamma) / total_gamma if total_gamma > 0 else 0

        # Determine market regime
        if net_gex > 0:
            regime_state = "Positive Gamma" if net_gex > 1e9 else "Neutral"
            volatility = "Low" if net_gex > 1e9 else "Moderate"
        else:
            regime_state = "Negative Gamma"
            volatility = "High"

        trend = "Bullish" if total_call_gamma > total_put_gamma else "Bearish" if total_put_gamma > total_call_gamma else "Neutral"

        # Calculate MM state
        flip_point = profile.get('flip_point', 0) if profile else 0
        mm_result = calculate_mm_confidence(net_gex, spot_price, flip_point)
        mm_states_config = get_mm_states()
        mm_state = mm_states_config.get(mm_result['state'], mm_states_config['NEUTRAL'])
        mm_state['confidence'] = mm_result['confidence']

        observations = [
            f"Net GEX is {'positive' if net_gex > 0 else 'negative'} at ${abs(net_gex)/1e9:.2f}B",
            f"Call/Put gamma ratio: {gamma_exposure_ratio:.2f}",
            f"Market regime: {regime_state} with {volatility.lower()} volatility"
        ]

        implications = [
            f"{'Reduced' if net_gex > 0 else 'Increased'} volatility expected",
            f"Price likely to {'stabilize' if net_gex > 0 else 'trend'} near current levels",
            f"Consider {'selling' if net_gex > 0 else 'buying'} volatility"
        ]

        # Get data_date from GEX data or calculate
        data_date = gex_data.get('collection_date') or get_last_trading_day()

        # Bug #8 Fix: Calculate vanna_exposure and charm_decay
        # Vanna = dDelta/dIV - approximated from gamma and IV relationship
        # Charm = dDelta/dTime - approximated from theta/gamma relationship
        implied_vol = gex_data.get('implied_volatility', 0.20)  # Default 20% IV
        vanna_exposure = 0
        charm_decay = 0

        if profile and profile.get('strikes'):
            # Calculate vanna as sensitivity of delta to IV changes
            # Approximation: vanna ≈ gamma * spot_price * sqrt(time) / IV
            # Using 7-day as typical DTE
            import math
            time_to_expiry = 7 / 365  # 7 days in years
            for strike in profile['strikes']:
                strike_gamma = strike.get('call_gamma', 0) + strike.get('put_gamma', 0)
                # Vanna approximation: larger for ATM options
                strike_price = strike.get('strike', spot_price)
                moneyness = abs(strike_price - spot_price) / spot_price
                atm_factor = max(0.1, 1 - moneyness * 5)  # ATM = 1, 20% OTM = 0
                vanna_exposure += strike_gamma * atm_factor * spot_price * math.sqrt(time_to_expiry)

            # Charm is the decay of delta over time
            # Approximation: charm ≈ -gamma * theta_factor
            # Options lose delta as they approach expiration
            theta_factor = 0.05  # Approximate theta as 5% of gamma per day
            charm_decay = -total_gamma * theta_factor

        # Bug #12 Fix: Include data source and age in response
        data_source = gex_data.get('data_source', 'unknown')
        data_age = gex_data.get('data_age', 'unknown')
        profile_source = profile.get('profile_source', 'unknown') if profile else 'none'

        return {
            "success": True,
            "symbol": symbol,
            "data": {
                "symbol": symbol,
                "spot_price": spot_price,
                "total_gamma": total_gamma,
                "call_gamma": total_call_gamma,
                "put_gamma": total_put_gamma,
                "gamma_is_estimated": gamma_is_estimated,  # True if gamma split is estimated (no strike data)
                "gamma_exposure_ratio": gamma_exposure_ratio,
                # Bug #8 Fix: Added vanna_exposure and charm_decay
                "vanna_exposure": vanna_exposure,
                "charm_decay": charm_decay,
                "risk_reversal": risk_reversal,
                "skew_index": gamma_exposure_ratio,
                "key_observations": observations,
                "trading_implications": implications,
                "market_regime": {"state": regime_state, "volatility": volatility, "trend": trend},
                "mm_state": {
                    "name": mm_result['state'],
                    "behavior": mm_state['behavior'],
                    "confidence": mm_state['confidence'],
                    "action": mm_state['action'],
                    "threshold": mm_state['threshold']
                },
                "net_gex": net_gex,
                "strikes": profile.get('strikes', []) if profile else [],
                "flip_point": profile.get('flip_point', 0) if profile else 0,
                "call_wall": profile.get('call_wall', 0) if profile else 0,
                "put_wall": profile.get('put_wall', 0) if profile else 0,
                "data_date": data_date,
                # Bug #12 Fix: Added data source tracking for stale data indication
                "data_source": data_source,
                "data_age": data_age,
                "profile_source": profile_source
            },
            "timestamp": datetime.now().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{symbol}/probabilities")
async def get_gamma_probabilities(symbol: str, vix: float = 20, account_size: float = 10000):
    """Get actionable probability analysis for gamma-based trading."""
    try:
        from core.probability_calculator import ProbabilityCalculator

        symbol = symbol.upper()
        prob_calc = ProbabilityCalculator()

        # Use fallback chain for GEX data
        gex_data = get_gex_with_fallback(symbol)
        if not gex_data or gex_data.get('error'):
            raise HTTPException(status_code=404, detail=f"No data for {symbol}")

        net_gex = gex_data.get('net_gex', 0) or 0
        spot_price = gex_data.get('spot_price', 0) or 590.0  # Default SPY price
        flip_point = gex_data.get('flip_point') or spot_price
        call_wall = gex_data.get('call_wall') or (spot_price * 1.02)
        put_wall = gex_data.get('put_wall') or (spot_price * 0.98)
        mm_state = gex_data.get('mm_state') or 'NEUTRAL'

        # Ensure vix is never None
        vix = float(vix) if vix else 20.0

        # Build gex_data dict for probability calculator
        gex_input = {
            'net_gex': net_gex,
            'flip_point': flip_point,
            'call_wall': call_wall,
            'put_wall': put_wall,
            'vix': vix,
            'implied_vol': vix / 100,
            'mm_state': mm_state
        }

        # Default psychology data
        psychology_data = {
            'fomo_level': 50,
            'fear_level': 50,
            'state': 'NEUTRAL'
        }

        # Calculate probabilities using the correct method
        probabilities = prob_calc.calculate_probability(
            symbol=symbol,
            current_price=spot_price,
            gex_data=gex_input,
            psychology_data=psychology_data,
            prediction_type='EOD'
        )

        data_date = gex_data.get('collection_date') or get_last_trading_day()

        return {
            "success": True,
            "symbol": symbol,
            "data": probabilities,
            "data_date": data_date,
            "timestamp": datetime.now().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{symbol}/expiration")
async def get_gamma_expiration(symbol: str):
    """Get gamma by expiration date analysis."""
    try:
        symbol = symbol.upper()

        # Use fallback chain for profile data
        profile = get_gex_profile_with_fallback(symbol)
        if not profile or profile.get('error'):
            return {
                "success": True,
                "symbol": symbol,
                "data": {"expirations": [], "message": "Expiration data not available"},
                "timestamp": datetime.now().isoformat()
            }

        expirations = profile.get('expirations', [])

        return {
            "success": True,
            "symbol": symbol,
            "data": {"expirations": expirations},
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{symbol}/expiration-waterfall")
async def get_gamma_expiration_waterfall(symbol: str):
    """Get gamma expiration waterfall for visualization."""
    try:
        symbol = symbol.upper()

        # Use fallback chain for profile data
        profile = get_gex_profile_with_fallback(symbol)
        if not profile:
            return {
                "success": True,
                "symbol": symbol,
                "data": {"waterfall": []},
                "timestamp": datetime.now().isoformat()
            }

        # Build waterfall from expiration data
        waterfall = []
        expirations = profile.get('expirations', [])

        for exp in expirations:
            waterfall.append({
                "expiration": exp.get('date'),
                "gamma": safe_round(exp.get('gamma', 0)),
                "call_gamma": safe_round(exp.get('call_gamma', 0)),
                "put_gamma": safe_round(exp.get('put_gamma', 0)),
                "dte": exp.get('dte', 0)
            })

        return {
            "success": True,
            "symbol": symbol,
            "data": {"waterfall": waterfall},
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{symbol}/history")
async def get_gamma_history(symbol: str, days: int = 30):
    """Get historical gamma data with IV and put/call ratio."""
    try:
        from database_adapter import get_connection
        from datetime import timedelta

        symbol = symbol.upper()
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

        # Join gex_history with vix_term_structure to get IV and put/call ratio
        # Use a time-based join (same day) since they're collected at different intervals
        cursor.execute("""
            SELECT
                g.timestamp,
                g.net_gex,
                g.spot_price,
                g.flip_point,
                g.call_wall,
                g.put_wall,
                g.regime,
                COALESCE(v.vix_spot, 0.18) / 100 as implied_volatility,
                COALESCE(v.put_call_ratio, 0.8) as put_call_ratio
            FROM gex_history g
            LEFT JOIN LATERAL (
                SELECT vix_spot, put_call_ratio
                FROM vix_term_structure
                WHERE DATE(timestamp) = DATE(g.timestamp)
                ORDER BY ABS(EXTRACT(EPOCH FROM (timestamp - g.timestamp)))
                LIMIT 1
            ) v ON true
            WHERE g.symbol = %s AND DATE(g.timestamp) >= %s
            ORDER BY g.timestamp ASC
        """, (symbol, start_date))

        history = []
        for row in cursor.fetchall():
            # Format for frontend HistoricalData interface
            ts = row['timestamp']
            history.append({
                "date": ts.strftime('%Y-%m-%d_%H:%M') if ts else None,
                "timestamp": ts.isoformat() if ts else None,
                "net_gex": safe_round(row['net_gex']),
                "price": safe_round(row['spot_price']),
                "spot_price": safe_round(row['spot_price']),
                "flip_point": safe_round(row.get('flip_point') or 0),
                "call_gex": safe_round(row.get('call_wall') or 0),
                "put_gex": safe_round(row.get('put_wall') or 0),
                "regime": row.get('regime'),
                "implied_volatility": float(row.get('implied_volatility') or 0.18),
                "put_call_ratio": float(row.get('put_call_ratio') or 0.8)
            })

        conn.close()

        return {
            "success": True,
            "symbol": symbol,
            "data": history,
            "days": days,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{symbol}/expiration-intel")
async def get_gamma_expiration_intel(symbol: str):
    """
    Get comprehensive gamma expiration intelligence for 0DTE trading.
    Returns weekly gamma structure, directional prediction, and risk levels.
    """
    try:
        symbol = symbol.upper()

        # Get real GEX data with fallback chain
        gex_data = get_gex_with_fallback(symbol)
        if not gex_data or gex_data.get('error'):
            raise HTTPException(status_code=404, detail=f"No GEX data for {symbol}")

        net_gex = gex_data.get('net_gex', 0)
        spot_price = gex_data.get('spot_price', 0)

        # Get profile data with fallback
        profile = get_gex_profile_with_fallback(symbol)

        flip_point = profile.get('flip_point', spot_price) if profile else spot_price
        call_wall = profile.get('call_wall', spot_price * 1.02) if profile else spot_price * 1.02
        put_wall = profile.get('put_wall', spot_price * 0.98) if profile else spot_price * 0.98

        # Get VIX with fallback
        current_vix = 18
        try:
            from data.unified_data_provider import get_vix as udp_get_vix
            vix_value = udp_get_vix()
            if vix_value and isinstance(vix_value, (int, float)) and vix_value > 0:
                current_vix = float(vix_value)
            elif vix_value and isinstance(vix_value, dict):
                current_vix = vix_value.get('current', 18) or vix_value.get('value', 18) or 18
        except Exception:
            pass

        # Determine day of week
        today = datetime.now()
        days_of_week = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        current_day = days_of_week[today.weekday()] if today.weekday() < 5 else 'Friday'

        # Build weekly gamma structure (realistic decay pattern)
        # Gamma decays as options expire throughout the week
        base_gamma = abs(net_gex) if net_gex else 2e9
        weekly_gamma = {
            'monday': base_gamma * 1.0,      # 100% - Full week gamma
            'tuesday': base_gamma * 0.85,    # 85% - Monday expiries gone
            'wednesday': base_gamma * 0.65,  # 65% - Wed/OPEX often big
            'thursday': base_gamma * 0.35,   # 35% - Most daily gone
            'friday': base_gamma * 0.12,     # 12% - Friday is chaos
            'total_decay_pct': 88,
            'decay_pattern': 'Heavy Friday Expiration'
        }

        # Determine current gamma based on day
        day_gamma_map = {
            'Monday': weekly_gamma['monday'],
            'Tuesday': weekly_gamma['tuesday'],
            'Wednesday': weekly_gamma['wednesday'],
            'Thursday': weekly_gamma['thursday'],
            'Friday': weekly_gamma['friday']
        }
        current_gamma = day_gamma_map.get(current_day, weekly_gamma['monday'])

        # Calculate after-close gamma (next day's value)
        day_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
        if current_day in day_order:
            current_idx = day_order.index(current_day)
            next_idx = min(current_idx + 1, 4)
            next_day = day_order[next_idx].lower()
            after_close_gamma = weekly_gamma[next_day]
        else:
            after_close_gamma = weekly_gamma['monday']

        gamma_loss_today = current_gamma - after_close_gamma
        gamma_loss_pct = round((gamma_loss_today / current_gamma * 100) if current_gamma else 0, 1)

        # Calculate risk level
        if gamma_loss_pct >= 50:
            risk_level = 'EXTREME'
        elif gamma_loss_pct >= 30:
            risk_level = 'HIGH'
        elif gamma_loss_pct >= 15:
            risk_level = 'MODERATE'
        else:
            risk_level = 'LOW'

        # Daily risk levels
        daily_risks = {
            'monday': 15,
            'tuesday': 20,
            'wednesday': 35,
            'thursday': 55,
            'friday': 100  # Friday always extreme
        }

        # Calculate directional prediction
        spot_vs_flip_pct = ((spot_price - flip_point) / flip_point * 100) if flip_point else 0
        distance_to_call_wall = ((call_wall - spot_price) / spot_price * 100) if call_wall and spot_price else 999
        distance_to_put_wall = ((spot_price - put_wall) / spot_price * 100) if put_wall and spot_price else 999

        bullish_score = 50  # Start neutral
        key_factors = []

        # Factor 1: GEX Regime (40% weight)
        if net_gex < -1e9:
            if spot_price > flip_point:
                bullish_score += 20
                key_factors.append("Short gamma + above flip = upside momentum")
            else:
                bullish_score -= 20
                key_factors.append("Short gamma + below flip = downside risk")
        elif net_gex > 1e9:
            if spot_vs_flip_pct > 1:
                bullish_score += 5
                key_factors.append("Long gamma + above flip = mild upward pull")
            elif spot_vs_flip_pct < -1:
                bullish_score -= 5
                key_factors.append("Long gamma + below flip = mild downward pull")
            else:
                key_factors.append("Long gamma near flip = range-bound likely")

        # Factor 2: Wall proximity (30% weight)
        if distance_to_call_wall < 1.5:
            bullish_score -= 15
            key_factors.append(f"Near call wall ${call_wall:.0f} = resistance")
        elif distance_to_put_wall < 1.5:
            bullish_score += 15
            key_factors.append(f"Near put wall ${put_wall:.0f} = support")

        # Factor 3: VIX regime (20% weight)
        if current_vix > 20:
            key_factors.append(f"VIX {current_vix:.1f} = elevated volatility")
            bullish_score = 50 + (bullish_score - 50) * 0.7
        elif current_vix < 15:
            key_factors.append(f"VIX {current_vix:.1f} = low volatility favors range")
            bullish_score = 50 + (bullish_score - 50) * 0.8
        else:
            key_factors.append(f"VIX {current_vix:.1f} = moderate volatility")

        # Factor 4: Day of week (10% weight)
        if current_day in ['Monday', 'Tuesday']:
            key_factors.append(f"{current_day} = high gamma, range-bound bias")
            bullish_score = 50 + (bullish_score - 50) * 0.9
        elif current_day == 'Friday':
            key_factors.append("Friday = low gamma, more volatile")

        # Determine direction
        if bullish_score >= 65:
            direction = "UPWARD"
            direction_emoji = "📈"
            probability = int(bullish_score)
            expected_move = "Expect push toward call wall or breakout higher"
        elif bullish_score <= 35:
            direction = "DOWNWARD"
            direction_emoji = "📉"
            probability = int(100 - bullish_score)
            expected_move = "Expect push toward put wall or breakdown lower"
        else:
            direction = "SIDEWAYS"
            direction_emoji = "↔️"
            probability = int(100 - abs(bullish_score - 50) * 2)
            expected_move = f"Expect range between ${put_wall:.0f} - ${call_wall:.0f}"

        # Build expected range
        range_width = ((call_wall - put_wall) / spot_price * 100) if call_wall and put_wall and spot_price else 0
        expected_range = f"${put_wall:.2f} - ${call_wall:.2f}"
        range_width_pct = f"{range_width:.1f}%"

        directional_prediction = {
            'direction': direction,
            'direction_emoji': direction_emoji,
            'probability': probability,
            'bullish_score': round(bullish_score, 1),
            'expected_move': expected_move,
            'expected_range': expected_range,
            'range_width_pct': range_width_pct,
            'spot_vs_flip_pct': round(spot_vs_flip_pct, 2),
            'distance_to_call_wall_pct': round(distance_to_call_wall, 2) if distance_to_call_wall < 999 else None,
            'distance_to_put_wall_pct': round(distance_to_put_wall, 2) if distance_to_put_wall < 999 else None,
            'key_factors': key_factors[:4],
            'vix': round(current_vix, 1)
        }

        data_date = gex_data.get('collection_date') or get_last_trading_day()

        return {
            "success": True,
            "data": {
                "symbol": symbol,
                "current_day": current_day,
                "current_gamma": safe_round(current_gamma),
                "after_close_gamma": safe_round(after_close_gamma),
                "gamma_loss_today": safe_round(gamma_loss_today),
                "gamma_loss_pct": gamma_loss_pct,
                "risk_level": risk_level,
                "weekly_gamma": {k: safe_round(v) if isinstance(v, (int, float)) else v for k, v in weekly_gamma.items()},
                "daily_risks": daily_risks,
                "spot_price": safe_round(spot_price),
                "flip_point": safe_round(flip_point),
                "net_gex": safe_round(net_gex),
                "call_wall": safe_round(call_wall),
                "put_wall": safe_round(put_wall),
                "directional_prediction": directional_prediction,
                "data_date": data_date
            },
            "timestamp": datetime.now().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
