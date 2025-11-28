"""
Gamma Intelligence API routes.

Handles gamma analytics, probabilities, expiration analysis, and waterfall data.
"""

import math
from datetime import datetime

from fastapi import APIRouter, HTTPException
import psycopg2.extras

router = APIRouter(prefix="/api/gamma", tags=["Gamma Intelligence"])


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


@router.get("/{symbol}/intelligence")
async def get_gamma_intelligence(symbol: str, vix: float = 20):
    """
    Get comprehensive gamma intelligence for a symbol.
    Returns gamma metrics, market regime, and MM state analysis.
    """
    try:
        from core_classes_and_engines import TradingVolatilityAPI
        from core.strategy_stats import calculate_mm_confidence, get_mm_states

        symbol = symbol.upper()
        api_client = TradingVolatilityAPI()

        # Get basic GEX data
        gex_data = api_client.get_net_gamma(symbol)
        if not gex_data or gex_data.get('error'):
            error_msg = gex_data.get('error', 'Unknown error') if gex_data else 'No data returned'
            raise HTTPException(status_code=404, detail=f"GEX data not available for {symbol}: {error_msg}")

        # Try to get detailed profile (rate limited)
        profile = None
        try:
            profile = api_client.get_gex_profile(symbol)
            if profile and profile.get('error'):
                profile = None
        except Exception:
            profile = None

        # Calculate gamma from strike data or estimate
        total_call_gamma = 0
        total_put_gamma = 0

        if profile and profile.get('strikes'):
            for strike in profile['strikes']:
                total_call_gamma += strike.get('call_gamma', 0)
                total_put_gamma += strike.get('put_gamma', 0)

        if total_call_gamma == 0 and total_put_gamma == 0:
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

        return {
            "success": True,
            "symbol": symbol,
            "data": {
                "symbol": symbol,
                "spot_price": spot_price,
                "total_gamma": total_gamma,
                "call_gamma": total_call_gamma,
                "put_gamma": total_put_gamma,
                "gamma_exposure_ratio": gamma_exposure_ratio,
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
                "put_wall": profile.get('put_wall', 0) if profile else 0
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
        from core_classes_and_engines import TradingVolatilityAPI
        from probability_calculator import ProbabilityCalculator

        symbol = symbol.upper()
        api_client = TradingVolatilityAPI()
        prob_calc = ProbabilityCalculator()

        gex_data = api_client.get_net_gamma(symbol)
        if not gex_data:
            raise HTTPException(status_code=404, detail=f"No data for {symbol}")

        net_gex = gex_data.get('net_gex', 0)
        spot_price = gex_data.get('spot_price', 0)

        # Calculate probabilities
        probabilities = prob_calc.calculate_move_probabilities(
            spot_price=spot_price,
            net_gex=net_gex,
            vix=vix
        )

        return {
            "success": True,
            "symbol": symbol,
            "data": probabilities,
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
        from core_classes_and_engines import TradingVolatilityAPI

        symbol = symbol.upper()
        api_client = TradingVolatilityAPI()

        profile = api_client.get_gex_profile(symbol)
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
        from core_classes_and_engines import TradingVolatilityAPI

        symbol = symbol.upper()
        api_client = TradingVolatilityAPI()

        profile = api_client.get_gex_profile(symbol)
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
    """Get historical gamma data."""
    try:
        from database_adapter import get_connection
        from datetime import timedelta

        symbol = symbol.upper()
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

        cursor.execute("""
            SELECT timestamp, net_gex, call_gex, put_gex, spot_price
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
                "spot_price": safe_round(row['spot_price'])
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
