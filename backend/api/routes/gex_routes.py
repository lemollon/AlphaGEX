"""
GEX (Gamma Exposure) API routes.

Handles all GEX data, levels, history, and regime analysis.
With fallback to database-stored data if live API fails.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from fastapi import APIRouter, HTTPException
import psycopg2.extras

from database_adapter import get_connection

# Import centralized utilities
from backend.api.utils import safe_round, safe_float, clean_dict_for_json

logger = logging.getLogger(__name__)

# Import data collector for storage
try:
    from services.data_collector import DataCollector
    DATA_COLLECTOR_AVAILABLE = True
except ImportError:
    DATA_COLLECTOR_AVAILABLE = False

router = APIRouter(prefix="/api/gex", tags=["GEX"])


# Note: safe_round is imported from backend.api.utils


def get_gex_from_database(symbol: str) -> Optional[Dict[str, Any]]:
    """
    Fallback: Get most recent GEX data from gex_history database.
    Returns None if no data found.
    """
    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Get most recent GEX snapshot for this symbol (within last 7 days)
        cursor.execute("""
            SELECT
                timestamp, net_gex, flip_point, call_wall, put_wall,
                spot_price, mm_state, regime, data_source
            FROM gex_history
            WHERE symbol = %s
            AND timestamp >= NOW() - INTERVAL '7 days'
            ORDER BY timestamp DESC
            LIMIT 1
        """, (symbol,))

        row = cursor.fetchone()
        conn.close()

        if row:
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
                'is_cached': True
            }
        return None
    except Exception as e:
        logger.debug(f"Database fallback failed for {symbol}: {e}")
        return None


def get_gex_from_tradier_calculation(symbol: str) -> Optional[Dict[str, Any]]:
    """
    FALLBACK: Calculate GEX from Tradier options chain data.
    This computes GEX in real-time when TradingVolatilityAPI is unavailable.
    """
    try:
        from data.gex_calculator import get_calculated_gex
        data = get_calculated_gex(symbol)
        if data and 'error' not in data:
            logger.debug(f" GEX calculated from Tradier options for {symbol}")
            return data
        return None
    except ImportError as e:
        logger.debug(f" GEX calculator import failed: {e}")
        return None
    except Exception as e:
        logger.debug(f" Tradier GEX calculation failed for {symbol}: {e}")
        return None


def get_gex_data_with_fallback(symbol: str) -> Dict[str, Any]:
    """
    Get GEX data with intelligent fallback chain:
    1. Try TradingVolatilityAPI first (live data from dedicated service)
    2. Calculate from Tradier options chain (real-time calculation)
    3. Fallback to gex_history database (cached historical data)
    4. Return error if nothing available
    """
    errors = []

    # PRIMARY: Try TradingVolatilityAPI (fastest, pre-calculated)
    try:
        from core_classes_and_engines import TradingVolatilityAPI
        api = TradingVolatilityAPI()
        data = api.get_net_gamma(symbol)

        if data and 'error' not in data:
            data['data_source'] = 'live_api'
            data['is_cached'] = False
            # Store data for ML/AI analysis
            if DATA_COLLECTOR_AVAILABLE:
                try:
                    DataCollector.store_gex(data, source='tradingvolatility')
                except Exception as e:
                    logger.warning(f": Failed to store GEX data: {e}")
            return data
        else:
            error_msg = data.get('error', 'Unknown error') if data else 'No data returned'
            errors.append(f"TradingVolatilityAPI: {error_msg}")
    except ImportError as e:
        errors.append(f"TradingVolatilityAPI import failed: {e}")
    except Exception as e:
        errors.append(f"TradingVolatilityAPI error: {e}")

    # FALLBACK 1: Calculate from Tradier options chain (real-time)
    logger.debug(f" TradingVolatilityAPI failed for {symbol}, trying Tradier calculation...")
    tradier_data = get_gex_from_tradier_calculation(symbol)
    if tradier_data:
        # Store calculated data for ML/AI analysis
        if DATA_COLLECTOR_AVAILABLE:
            try:
                DataCollector.store_gex(tradier_data, source='tradier_calculated')
            except Exception as e:
                logger.warning(f": Failed to store Tradier GEX data: {e}")
        return tradier_data
    else:
        errors.append("Tradier calculation: Failed or unavailable")

    # FALLBACK 2: Try database (most recent cached data)
    logger.debug(f" Tradier calculation failed for {symbol}, trying database fallback...")
    db_data = get_gex_from_database(symbol)
    if db_data:
        logger.debug(f" Using database fallback for {symbol}")
        return db_data
    else:
        errors.append("Database fallback: No recent data found")

    # All sources failed
    return {
        'error': f"All data sources failed: {'; '.join(errors)}",
        'tried_sources': ['TradingVolatilityAPI', 'Tradier_calculation', 'gex_history_database']
    }


@router.get("/{symbol}")
async def get_gex_data(symbol: str):
    """Get comprehensive GEX data for a symbol with automatic fallback"""
    # Skip reserved paths - redirect to proper endpoints
    # These routes are defined later but /{symbol} matches first due to FastAPI order
    if symbol.lower() == 'history':
        # Forward to history endpoint logic
        return await get_gex_history()
    if symbol.lower() == 'regime-changes':
        # Forward to regime-changes endpoint logic
        return await get_regime_changes()

    symbol = symbol.upper().strip()
    if len(symbol) > 5 or not symbol.isalnum():
        raise HTTPException(status_code=400, detail="Invalid symbol")

    try:
        data = get_gex_data_with_fallback(symbol)

        if 'error' in data:
            raise HTTPException(status_code=404, detail=f"No GEX data for {symbol}: {data['error']}")

        # Calculate regime
        net_gex = data.get('net_gex', 0) or 0
        if net_gex <= -3e9:
            regime = 'EXTREME_NEGATIVE'
        elif net_gex <= -2e9:
            regime = 'HIGH_NEGATIVE'
        elif net_gex <= -1e9:
            regime = 'MODERATE_NEGATIVE'
        elif net_gex >= 3e9:
            regime = 'EXTREME_POSITIVE'
        elif net_gex >= 2e9:
            regime = 'HIGH_POSITIVE'
        elif net_gex >= 1e9:
            regime = 'MODERATE_POSITIVE'
        else:
            regime = 'NEUTRAL'

        # Get data timestamp - when the market data was collected
        data_date = data.get('collection_date') or data.get('data_date')
        if not data_date:
            # Fallback: use last trading day
            now = datetime.now()
            if now.weekday() == 5:  # Saturday
                data_date = (now - timedelta(days=1)).strftime('%Y-%m-%d')
            elif now.weekday() == 6:  # Sunday
                data_date = (now - timedelta(days=2)).strftime('%Y-%m-%d')
            elif now.hour < 9 or (now.hour == 9 and now.minute < 30):
                # Before market open - use previous trading day
                if now.weekday() == 0:  # Monday
                    data_date = (now - timedelta(days=3)).strftime('%Y-%m-%d')
                else:
                    data_date = (now - timedelta(days=1)).strftime('%Y-%m-%d')
            else:
                data_date = now.strftime('%Y-%m-%d')

        # Get VIX for response
        vix_value = 18.0  # Default
        try:
            from data.unified_data_provider import get_vix
            vix_result = get_vix()
            if vix_result:
                if isinstance(vix_result, (int, float)):
                    vix_value = float(vix_result)
                elif isinstance(vix_result, dict):
                    vix_value = float(vix_result.get('value', vix_result.get('current', 18.0)))
        except Exception:
            pass

        # Calculate MM state
        flip_point = data.get('flip_point', 0) or data.get('gamma_flip', 0) or 0
        spot_price = data.get('spot_price', 0) or 0
        if spot_price > 0 and flip_point > 0:
            if spot_price > flip_point:
                mm_state = 'LONG_GAMMA' if net_gex > 0 else 'DEFENDING'
            else:
                mm_state = 'SHORT_GAMMA' if net_gex < 0 else 'SQUEEZING'
        else:
            mm_state = data.get('mm_state', 'NEUTRAL')

        return {
            "success": True,
            "data": {
                "symbol": symbol,
                "net_gex": safe_round(net_gex),
                "call_gex": safe_round(data.get('call_gex', 0)),
                "put_gex": safe_round(data.get('put_gex', 0)),
                "flip_point": safe_round(flip_point),
                "gamma_flip": safe_round(flip_point),  # Alias for backwards compat
                "call_wall": safe_round(data.get('call_wall', 0)),
                "put_wall": safe_round(data.get('put_wall', 0)),
                "max_pain": safe_round(data.get('max_pain', 0)),
                "spot_price": safe_round(spot_price),
                "vix": safe_round(vix_value, 1),
                "mm_state": mm_state,
                "regime": regime,
                "data_date": data_date,
                "timestamp": datetime.now().isoformat()
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"GEX data processing error: {type(e).__name__}: {str(e)}")


@router.get("/{symbol}/levels")
async def get_gex_levels(symbol: str):
    """Get key GEX support/resistance levels with automatic fallback"""
    symbol = symbol.upper().strip()
    if len(symbol) > 5 or not symbol.isalnum():
        raise HTTPException(status_code=400, detail="Invalid symbol")

    try:
        data = get_gex_data_with_fallback(symbol)

        if 'error' in data:
            raise HTTPException(status_code=404, detail=f"No GEX data for {symbol}: {data['error']}")

        spot = data.get('spot_price', 0) or 0
        call_wall = data.get('call_wall', 0) or 0
        put_wall = data.get('put_wall', 0) or 0
        gamma_flip = data.get('gamma_flip', 0) or 0

        # Calculate distances
        call_dist = ((call_wall - spot) / spot * 100) if spot > 0 and call_wall > 0 else 0
        put_dist = ((spot - put_wall) / spot * 100) if spot > 0 and put_wall > 0 else 0
        flip_dist = ((gamma_flip - spot) / spot * 100) if spot > 0 and gamma_flip > 0 else 0

        return {
            "success": True,
            "data": {
                "symbol": symbol,
                "spot_price": safe_round(spot),
                "levels": {
                    "call_wall": {
                        "price": safe_round(call_wall),
                        "distance_pct": safe_round(call_dist),
                        "type": "resistance"
                    },
                    "put_wall": {
                        "price": safe_round(put_wall),
                        "distance_pct": safe_round(put_dist),
                        "type": "support"
                    },
                    "gamma_flip": {
                        "price": safe_round(gamma_flip),
                        "distance_pct": safe_round(flip_dist),
                        "type": "regime_change"
                    },
                    "max_pain": {
                        "price": safe_round(data.get('max_pain', 0)),
                        "type": "magnet"
                    }
                }
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history")
async def get_gex_history(symbol: str = "SPY", days: int = 30):
    """Get historical GEX data"""
    symbol = symbol.upper().strip()

    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

        cursor.execute("""
            SELECT
                timestamp,
                net_gex,
                flip_point,
                call_wall,
                put_wall,
                spot_price,
                mm_state,
                regime
            FROM gex_history
            WHERE symbol = %s AND DATE(timestamp) >= %s
            ORDER BY timestamp ASC
        """, (symbol, start_date))

        history = []
        for row in cursor.fetchall():
            history.append({
                "timestamp": row['timestamp'].isoformat() if row['timestamp'] else None,
                "net_gex": safe_round(row['net_gex']),
                "flip_point": safe_round(row['flip_point']),
                "gamma_flip": safe_round(row['flip_point']),  # Alias for backwards compat
                "call_wall": safe_round(row['call_wall']),
                "put_wall": safe_round(row['put_wall']),
                "spot_price": safe_round(row['spot_price']),
                "mm_state": row['mm_state'],
                "regime": row['regime']
            })

        conn.close()

        # Add data_source and ensure all fields are present for frontend
        gex_history = []
        for h in history:
            # Use stored regime/mm_state if available, otherwise calculate
            regime = h.get('regime')
            mm_state = h.get('mm_state')

            if not regime:
                net_gex = h.get('net_gex', 0) or 0
                if net_gex < 0:
                    regime = 'NEGATIVE'
                elif net_gex > 0:
                    regime = 'POSITIVE'
                else:
                    regime = 'NEUTRAL'

            if not mm_state:
                flip_point = h.get('flip_point', 0) or 0
                spot_price = h.get('spot_price', 0) or 0
                mm_state = 'LONG_GAMMA' if spot_price > flip_point else 'SHORT_GAMMA'

            gex_history.append({
                **h,
                'regime': regime,
                'mm_state': mm_state,
                'data_source': 'gex_history'
            })

        return {
            "success": True,
            "data": history,  # Keep original for backward compat
            "gex_history": gex_history,  # Add formatted data for frontend
            "symbol": symbol,
            "days": days
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/regime-changes")
async def get_regime_changes(symbol: str = "SPY", days: int = 30):
    """Get historical regime change events"""
    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

        cursor.execute("""
            SELECT
                timestamp,
                net_gex,
                spot_price,
                CASE
                    WHEN net_gex <= -3000000000 THEN 'EXTREME_NEGATIVE'
                    WHEN net_gex <= -2000000000 THEN 'HIGH_NEGATIVE'
                    WHEN net_gex <= -1000000000 THEN 'MODERATE_NEGATIVE'
                    WHEN net_gex >= 3000000000 THEN 'EXTREME_POSITIVE'
                    WHEN net_gex >= 2000000000 THEN 'HIGH_POSITIVE'
                    WHEN net_gex >= 1000000000 THEN 'MODERATE_POSITIVE'
                    ELSE 'NEUTRAL'
                END as regime
            FROM gex_history
            WHERE symbol = %s AND DATE(timestamp) >= %s
            ORDER BY timestamp ASC
        """, (symbol, start_date))

        rows = cursor.fetchall()
        conn.close()

        # Find regime changes
        changes = []
        regime_changes = []  # Frontend-compatible format
        prev_regime = None
        prev_timestamp = None

        for row in rows:
            current_regime = row['regime']
            if prev_regime and current_regime != prev_regime:
                # Calculate duration in days
                duration_days = 0
                if prev_timestamp and row['timestamp']:
                    duration_days = (row['timestamp'] - prev_timestamp).days

                change_data = {
                    "timestamp": row['timestamp'].isoformat() if row['timestamp'] else None,
                    "from_regime": prev_regime,
                    "to_regime": current_regime,
                    "net_gex": safe_round(row['net_gex']),
                    "spot_price": safe_round(row['spot_price'])
                }
                changes.append(change_data)

                # Frontend-compatible format
                regime_changes.append({
                    "change_date": row['timestamp'].isoformat() if row['timestamp'] else None,
                    "previous_regime": prev_regime.replace('_', ' ').title() if prev_regime else None,
                    "new_regime": current_regime.replace('_', ' ').title() if current_regime else None,
                    "net_gex_at_change": safe_round(row['net_gex']),
                    "spot_price_at_change": safe_round(row['spot_price']),
                    "duration_days": duration_days
                })

            prev_regime = current_regime
            prev_timestamp = row['timestamp']

        return {
            "success": True,
            "data": changes,
            "regime_changes": regime_changes,  # Frontend-compatible
            "total_changes": len(changes),
            "symbol": symbol,
            "days": days
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/compare/0dte/{symbol}")
async def get_0dte_gamma_comparison(symbol: str):
    """
    Get 0DTE gamma arrays from BOTH data sources for side-by-side comparison.

    Returns gamma arrays from:
    1. TradingVolatility API (primary/external source)
    2. Tradier calculated (fallback/internal calculation)

    Both arrays should be nearly identical if the calculations are correct.
    This endpoint is used by the Volatility Comparison page to validate
    that the Tradier fallback produces accurate results.
    """
    symbol = symbol.upper().strip()
    if len(symbol) > 5 or not symbol.isalnum():
        raise HTTPException(status_code=400, detail="Invalid symbol")

    result = {
        "success": True,
        "symbol": symbol,
        "timestamp": datetime.now().isoformat(),
        "trading_volatility": None,        # All expirations from Trading Volatility API
        "tradier_all_expirations": None,   # All expirations from Tradier (apples-to-apples)
        "tradier_0dte": None,              # 0DTE only from Tradier
        "errors": []
    }

    # Source 1: TradingVolatility API (primary)
    # NOTE: /gex/gamma endpoint returns gamma=0.0 for all strikes (no per-strike data)
    # So we use /gex/gammaOI which HAS real call_gamma/put_gamma values
    # Trade-off: gammaOI is all expirations, not just 0DTE
    try:
        from core_classes_and_engines import TradingVolatilityAPI
        api = TradingVolatilityAPI()

        # Use get_gex_profile which calls /gex/gammaOI (has actual per-strike gamma)
        tv_profile = api.get_gex_profile(symbol)

        if tv_profile and 'strikes' in tv_profile and tv_profile['strikes']:
            raw_strikes = tv_profile.get('strikes', [])

            # Debug: Log first strike to see available fields
            debug_info = {}
            if raw_strikes and len(raw_strikes) > 0:
                sample = raw_strikes[0]
                print(f"DEBUG /gex/gammaOI response - First strike fields: {list(sample.keys())}")
                print(f"DEBUG /gex/gammaOI response - First strike data: {sample}")
                debug_info = {
                    "raw_fields": list(sample.keys()),
                    "sample_strike": {k: str(v)[:50] for k, v in sample.items()}
                }

                # Check for alternative field names
                print(f"DEBUG - call_gamma value: {sample.get('call_gamma', 'NOT FOUND')}")
                print(f"DEBUG - put_gamma value: {sample.get('put_gamma', 'NOT FOUND')}")
                print(f"DEBUG - total_gamma value: {sample.get('total_gamma', 'NOT FOUND')}")
                print(f"DEBUG - net_gamma value: {sample.get('net_gamma', 'NOT FOUND')}")
                print(f"DEBUG - call_gex value: {sample.get('call_gex', 'NOT FOUND')}")
                print(f"DEBUG - put_gex value: {sample.get('put_gex', 'NOT FOUND')}")

            # Format to match expected gamma_array structure
            gamma_array = []
            total_net_gex = 0
            max_call_gamma = 0
            max_put_gamma = 0
            call_wall = 0
            put_wall = 0
            spot_price = float(tv_profile.get('spot_price', 0))

            for strike_data in raw_strikes:
                if not strike_data or 'strike' not in strike_data:
                    continue

                strike = float(strike_data.get('strike', 0))

                # Get gamma values - they're already processed by get_gex_profile()
                # Values are stored as absolute values in the profile
                call_gamma = float(strike_data.get('call_gamma', 0) or 0)
                put_gamma = float(strike_data.get('put_gamma', 0) or 0)
                total_gamma = float(strike_data.get('total_gamma', 0) or 0)

                # If total_gamma is 0 but call/put aren't, calculate it
                if total_gamma == 0 and (call_gamma != 0 or put_gamma != 0):
                    total_gamma = call_gamma - put_gamma  # Call positive, put negative for net

                # If call/put are 0 but total isn't, derive from total
                if call_gamma == 0 and put_gamma == 0 and total_gamma != 0:
                    # Attribute to call if positive, put if negative
                    if total_gamma > 0:
                        call_gamma = total_gamma
                    else:
                        put_gamma = abs(total_gamma)

                total_net_gex += total_gamma

                # Track walls - use the higher gamma values
                if call_gamma > max_call_gamma:
                    max_call_gamma = call_gamma
                    call_wall = strike
                if put_gamma > max_put_gamma:
                    max_put_gamma = put_gamma
                    put_wall = strike

                gamma_array.append({
                    'strike': strike,
                    'call_gamma': call_gamma,
                    'put_gamma': put_gamma,
                    'total_gamma': total_gamma,
                    'net_gex': total_gamma
                })

            result["trading_volatility"] = {
                "data_source": "trading_volatility_api",
                "spot_price": spot_price,
                "flip_point": tv_profile.get('flip_point', spot_price),
                "call_wall": tv_profile.get('call_wall', call_wall),
                "put_wall": tv_profile.get('put_wall', put_wall),
                "net_gex": total_net_gex,
                "gamma_array": gamma_array,
                "strikes_count": len(gamma_array),
                "expiration": "All expirations (gammaOI)",  # Note: not filtered to 0DTE
                "_debug": debug_info
            }
        else:
            result["errors"].append("TradingVolatility API: No gamma profile data available")
    except ImportError as e:
        result["errors"].append(f"TradingVolatility API: Import failed - {e}")
    except Exception as e:
        result["errors"].append(f"TradingVolatility API: {str(e)}")

    # Source 2: Tradier ALL EXPIRATIONS Calculation (apples-to-apples with Trading Volatility)
    try:
        from data.gex_calculator import get_all_expirations_gex_profile
        tradier_all_profile = get_all_expirations_gex_profile(symbol)

        if tradier_all_profile and 'error' not in tradier_all_profile:
            result["tradier_all_expirations"] = {
                "data_source": "tradier_all_expirations_calculated",
                "spot_price": tradier_all_profile.get('spot_price', 0),
                "flip_point": tradier_all_profile.get('flip_point', 0),
                "call_wall": tradier_all_profile.get('call_wall', 0),
                "put_wall": tradier_all_profile.get('put_wall', 0),
                "max_pain": tradier_all_profile.get('max_pain', 0),
                "net_gex": tradier_all_profile.get('net_gex', 0),
                "put_call_ratio": tradier_all_profile.get('put_call_ratio', 0),
                "expiration": tradier_all_profile.get('expiration', 'All expirations'),
                "expirations_included": tradier_all_profile.get('expirations_included', []),
                "gamma_array": tradier_all_profile.get('gamma_array', []),
                "strikes_count": len(tradier_all_profile.get('gamma_array', [])),
                "timestamp": tradier_all_profile.get('timestamp', '')
            }
        else:
            error_msg = tradier_all_profile.get('error', 'Unknown error') if tradier_all_profile else 'No data returned'
            result["errors"].append(f"Tradier all-expirations: {error_msg}")
    except ImportError as e:
        result["errors"].append(f"Tradier all-expirations: Import failed - {e}")
    except Exception as e:
        result["errors"].append(f"Tradier all-expirations: {str(e)}")

    # Source 3: Tradier 0DTE Calculation (for reference)
    try:
        from data.gex_calculator import get_0dte_gex_profile
        tradier_profile = get_0dte_gex_profile(symbol)

        if tradier_profile and 'error' not in tradier_profile:
            result["tradier_0dte"] = {
                "data_source": "tradier_0dte_calculated",
                "spot_price": tradier_profile.get('spot_price', 0),
                "flip_point": tradier_profile.get('flip_point', 0),
                "call_wall": tradier_profile.get('call_wall', 0),
                "put_wall": tradier_profile.get('put_wall', 0),
                "max_pain": tradier_profile.get('max_pain', 0),
                "net_gex": tradier_profile.get('net_gex', 0),
                "put_call_ratio": tradier_profile.get('put_call_ratio', 0),
                "expiration": tradier_profile.get('expiration', ''),
                "gamma_array": tradier_profile.get('gamma_array', []),
                "strikes_count": len(tradier_profile.get('gamma_array', [])),
                "timestamp": tradier_profile.get('timestamp', '')
            }
        else:
            error_msg = tradier_profile.get('error', 'Unknown error') if tradier_profile else 'No data returned'
            result["errors"].append(f"Tradier 0DTE: {error_msg}")
    except ImportError as e:
        result["errors"].append(f"Tradier 0DTE: Import failed - {e}")
    except Exception as e:
        result["errors"].append(f"Tradier 0DTE: {str(e)}")

    # If all sources failed, return error
    if result["trading_volatility"] is None and result["tradier_all_expirations"] is None and result["tradier_0dte"] is None:
        raise HTTPException(
            status_code=503,
            detail=f"Both data sources failed: {'; '.join(result['errors'])}"
        )

    return result
