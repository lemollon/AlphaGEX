"""
GEX (Gamma Exposure) API routes.

Handles all GEX data, levels, history, and regime analysis.
"""

import math
from datetime import datetime, timedelta

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


@router.get("/{symbol}")
async def get_gex_data(symbol: str):
    """Get comprehensive GEX data for a symbol"""
    symbol = symbol.upper().strip()
    if len(symbol) > 5 or not symbol.isalnum():
        raise HTTPException(status_code=400, detail="Invalid symbol")

    try:
        from core_classes_and_engines import TradingVolatilityAPI
        api = TradingVolatilityAPI()
        data = api.get_option_data(symbol)

        if not data:
            raise HTTPException(status_code=404, detail=f"No GEX data for {symbol}")

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

        return {
            "success": True,
            "data": {
                "symbol": symbol,
                "net_gex": safe_round(net_gex),
                "call_gex": safe_round(data.get('call_gex', 0)),
                "put_gex": safe_round(data.get('put_gex', 0)),
                "gamma_flip": safe_round(data.get('gamma_flip', 0)),
                "call_wall": safe_round(data.get('call_wall', 0)),
                "put_wall": safe_round(data.get('put_wall', 0)),
                "max_pain": safe_round(data.get('max_pain', 0)),
                "spot_price": safe_round(data.get('spot_price', 0)),
                "regime": regime,
                "timestamp": datetime.now().isoformat()
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{symbol}/levels")
async def get_gex_levels(symbol: str):
    """Get key GEX support/resistance levels"""
    symbol = symbol.upper().strip()
    if len(symbol) > 5 or not symbol.isalnum():
        raise HTTPException(status_code=400, detail="Invalid symbol")

    try:
        from core_classes_and_engines import TradingVolatilityAPI
        api = TradingVolatilityAPI()
        data = api.get_option_data(symbol)

        if not data:
            raise HTTPException(status_code=404, detail=f"No GEX data for {symbol}")

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

        return {
            "success": True,
            "data": history,
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
        prev_regime = None
        for row in rows:
            current_regime = row['regime']
            if prev_regime and current_regime != prev_regime:
                changes.append({
                    "timestamp": row['timestamp'].isoformat() if row['timestamp'] else None,
                    "from_regime": prev_regime,
                    "to_regime": current_regime,
                    "net_gex": safe_round(row['net_gex']),
                    "spot_price": safe_round(row['spot_price'])
                })
            prev_regime = current_regime

        return {
            "success": True,
            "data": changes,
            "total_changes": len(changes),
            "symbol": symbol,
            "days": days
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
