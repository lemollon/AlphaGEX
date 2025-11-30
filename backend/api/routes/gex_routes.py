"""
GEX (Gamma Exposure) API routes.

Handles all GEX data, levels, history, and regime analysis.
With fallback to database-stored data if live API fails.
"""

import math
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from fastapi import APIRouter, HTTPException
import psycopg2.extras

from database_adapter import get_connection

router = APIRouter(prefix="/api/gex", tags=["GEX"])


def safe_round(value, decimals=2, default=0):
    """Round a value, returning default if inf/nan"""
    if value is None:
        return default
    try:
        float_val = float(value)
        if math.isnan(float_val) or math.isinf(float_val):
            return default
        return round(float_val, decimals)
    except (ValueError, TypeError, OverflowError):
        return default


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
                spot_price, mm_state, regime, data_source,
                call_gex, put_gex, gamma_flip, max_pain
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
                'flip_point': float(row.get('flip_point') or row.get('gamma_flip') or 0),
                'call_wall': float(row.get('call_wall') or 0),
                'put_wall': float(row.get('put_wall') or 0),
                'call_gex': float(row.get('call_gex') or 0),
                'put_gex': float(row.get('put_gex') or 0),
                'max_pain': float(row.get('max_pain') or 0),
                'collection_date': row.get('timestamp').strftime('%Y-%m-%d') if row.get('timestamp') else None,
                'data_source': 'database_fallback',
                'is_cached': True
            }
        return None
    except Exception as e:
        print(f"Database fallback failed for {symbol}: {e}")
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
            print(f"✅ GEX calculated from Tradier options for {symbol}")
            return data
        return None
    except ImportError as e:
        print(f"⚠️ GEX calculator import failed: {e}")
        return None
    except Exception as e:
        print(f"⚠️ Tradier GEX calculation failed for {symbol}: {e}")
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
            return data
        else:
            error_msg = data.get('error', 'Unknown error') if data else 'No data returned'
            errors.append(f"TradingVolatilityAPI: {error_msg}")
    except ImportError as e:
        errors.append(f"TradingVolatilityAPI import failed: {e}")
    except Exception as e:
        errors.append(f"TradingVolatilityAPI error: {e}")

    # FALLBACK 1: Calculate from Tradier options chain (real-time)
    print(f"⚠️ TradingVolatilityAPI failed for {symbol}, trying Tradier calculation...")
    tradier_data = get_gex_from_tradier_calculation(symbol)
    if tradier_data:
        return tradier_data
    else:
        errors.append("Tradier calculation: Failed or unavailable")

    # FALLBACK 2: Try database (most recent cached data)
    print(f"⚠️ Tradier calculation failed for {symbol}, trying database fallback...")
    db_data = get_gex_from_database(symbol)
    if db_data:
        print(f"✅ Using database fallback for {symbol}")
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

        return {
            "success": True,
            "data": {
                "symbol": symbol,
                "net_gex": safe_round(net_gex),
                "call_gex": safe_round(data.get('call_gex', 0)),
                "put_gex": safe_round(data.get('put_gex', 0)),
                "gamma_flip": safe_round(data.get('gamma_flip', 0) or data.get('flip_point', 0)),
                "call_wall": safe_round(data.get('call_wall', 0)),
                "put_wall": safe_round(data.get('put_wall', 0)),
                "max_pain": safe_round(data.get('max_pain', 0)),
                "spot_price": safe_round(data.get('spot_price', 0)),
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
                call_gex,
                put_gex,
                gamma_flip,
                call_wall,
                put_wall,
                spot_price
            FROM gex_history
            WHERE symbol = %s AND DATE(timestamp) >= %s
            ORDER BY timestamp ASC
        """, (symbol, start_date))

        history = []
        for row in cursor.fetchall():
            history.append({
                "timestamp": row['timestamp'].isoformat() if row['timestamp'] else None,
                "net_gex": safe_round(row['net_gex']),
                "call_gex": safe_round(row['call_gex']),
                "put_gex": safe_round(row['put_gex']),
                "gamma_flip": safe_round(row['gamma_flip']),
                "call_wall": safe_round(row['call_wall']),
                "put_wall": safe_round(row['put_wall']),
                "spot_price": safe_round(row['spot_price'])
            })

        conn.close()

        # Calculate regime and other fields expected by frontend
        gex_history = []
        for h in history:
            net_gex = h.get('net_gex', 0) or 0
            # Determine regime
            if net_gex <= -3e9:
                regime = 'NEGATIVE'
            elif net_gex < 0:
                regime = 'NEGATIVE'
            elif net_gex >= 3e9:
                regime = 'POSITIVE'
            elif net_gex > 0:
                regime = 'POSITIVE'
            else:
                regime = 'NEUTRAL'

            # Determine MM state
            flip_point = h.get('gamma_flip', 0) or 0
            spot_price = h.get('spot_price', 0) or 0
            mm_state = 'LONG_GAMMA' if spot_price > flip_point else 'SHORT_GAMMA'

            gex_history.append({
                **h,
                'regime': regime,
                'mm_state': mm_state,
                'flip_point': flip_point,
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
