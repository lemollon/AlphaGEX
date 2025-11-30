"""
VIX Hedge Manager API routes.
With fallback data sources when VIX module is unavailable.
"""

import os
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

from fastapi import APIRouter, HTTPException
import requests


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


def get_vix_fallback_data() -> Dict[str, Any]:
    """
    Fallback VIX data when vix_hedge_manager is unavailable.
    Tries Tradier first, then Polygon, then returns estimated data.
    ALWAYS returns valid data - never throws.
    """
    vix_data = {
        'vix_spot': 18.0,
        'vix_source': 'default',
        'is_estimated': True,
        'vix_m1': 0,
        'vix_m2': 0,
        'term_structure_m1_pct': 0,
        'term_structure_m2_pct': 0,
        'structure_type': 'unknown',
        'vvix': None,
        'vvix_source': 'none',
        'vix_stress_level': 'normal',
        'position_size_multiplier': 1.0
    }

    # Try unified data provider (Tradier)
    try:
        from data.unified_data_provider import get_vix
        vix_value = get_vix()
        if vix_value:
            # Handle both float and dict return types
            if isinstance(vix_value, (int, float)) and vix_value > 0:
                vix_data['vix_spot'] = float(vix_value)
                vix_data['vix_source'] = 'tradier'
                vix_data['is_estimated'] = False
                return vix_data
            elif isinstance(vix_value, dict) and vix_value.get('value', 0) > 0:
                vix_data['vix_spot'] = float(vix_value['value'])
                vix_data['vix_source'] = vix_value.get('source', 'tradier')
                vix_data['is_estimated'] = False
                return vix_data
    except ImportError as e:
        print(f"Tradier VIX import failed (expected on some deployments): {e}")
    except Exception as e:
        print(f"Tradier VIX fallback failed: {e}")

    # Try Polygon
    polygon_key = os.getenv('POLYGON_API_KEY')
    if polygon_key:
        try:
            to_date = datetime.now().strftime('%Y-%m-%d')
            from_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')

            url = f"https://api.polygon.io/v2/aggs/ticker/VIX/range/1/day/{from_date}/{to_date}"
            params = {"apiKey": polygon_key, "sort": "desc", "limit": 1}

            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get('status') == 'OK' and data.get('results'):
                    vix_data['vix_spot'] = float(data['results'][0]['c'])
                    vix_data['vix_source'] = 'polygon'
                    vix_data['is_estimated'] = False
                    return vix_data
        except Exception as e:
            print(f"Polygon VIX fallback failed: {e}")

    # Calculate stress level based on VIX value
    vix = vix_data['vix_spot']
    if vix >= 30:
        vix_data['vix_stress_level'] = 'extreme'
        vix_data['position_size_multiplier'] = 0.25
    elif vix >= 25:
        vix_data['vix_stress_level'] = 'high'
        vix_data['position_size_multiplier'] = 0.5
    elif vix >= 20:
        vix_data['vix_stress_level'] = 'elevated'
        vix_data['position_size_multiplier'] = 0.75
    else:
        vix_data['vix_stress_level'] = 'normal'
        vix_data['position_size_multiplier'] = 1.0

    return vix_data


router = APIRouter(prefix="/api/vix", tags=["VIX"])


@router.get("/hedge-signal")
async def get_vix_hedge_signal(portfolio_delta: float = 0, portfolio_value: float = 100000):
    """
    Generate a VIX-based hedge signal for portfolio protection.
    This is a SIGNAL GENERATOR only - does not auto-execute trades.
    Falls back to basic signal when vix_hedge_manager is unavailable.
    """
    # Try vix_hedge_manager first
    try:
        from core.vix_hedge_manager import get_vix_hedge_manager

        manager = get_vix_hedge_manager()
        signal = manager.generate_hedge_signal(
            portfolio_delta=portfolio_delta,
            portfolio_value=portfolio_value
        )

        return {
            "success": True,
            "data": {
                "timestamp": signal.timestamp.isoformat(),
                "signal_type": signal.signal_type.value,
                "confidence": signal.confidence,
                "vol_regime": signal.vol_regime.value,
                "reasoning": signal.reasoning,
                "recommended_action": signal.recommended_action,
                "risk_warning": signal.risk_warning,
                "metrics": signal.metrics
            }
        }
    except ImportError as e:
        print(f"⚠️ VIX hedge manager import failed: {e}, using fallback signal")
    except Exception as e:
        print(f"⚠️ VIX hedge manager error: {e}, using fallback signal")

    # FALLBACK: Generate basic signal from VIX level
    try:
        vix_data = get_vix_fallback_data()
        vix_spot = vix_data['vix_spot']

        # Determine signal based on VIX level
        if vix_spot >= 30:
            signal_type = 'hedge_recommended'
            confidence = 0.8
            vol_regime = 'extreme'
            reasoning = f"VIX at {vix_spot:.1f} indicates extreme volatility. Consider hedging."
            recommended_action = "Add protective puts or reduce position sizes"
            risk_warning = "High volatility environment - expect large price swings"
        elif vix_spot >= 25:
            signal_type = 'monitor_closely'
            confidence = 0.6
            vol_regime = 'high'
            reasoning = f"VIX at {vix_spot:.1f} indicates elevated volatility. Monitor closely."
            recommended_action = "Consider reducing position sizes"
            risk_warning = "Elevated risk - prepare hedge strategy"
        elif vix_spot >= 20:
            signal_type = 'no_action'
            confidence = 0.5
            vol_regime = 'elevated'
            reasoning = f"VIX at {vix_spot:.1f} is slightly elevated. Normal caution."
            recommended_action = "Maintain current positions with stops"
            risk_warning = None
        else:
            signal_type = 'no_action'
            confidence = 0.7
            vol_regime = 'normal'
            reasoning = f"VIX at {vix_spot:.1f} indicates low volatility. No hedging needed."
            recommended_action = "Normal trading conditions"
            risk_warning = None

        return {
            "success": True,
            "data": {
                "timestamp": datetime.now().isoformat(),
                "signal_type": signal_type,
                "confidence": confidence,
                "vol_regime": vol_regime,
                "reasoning": reasoning,
                "recommended_action": recommended_action,
                "risk_warning": risk_warning,
                "metrics": {
                    "vix_spot": vix_spot,
                    "vix_source": vix_data.get('vix_source', 'fallback')
                },
                "fallback_mode": True
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Hedge signal error: {str(e)}")


@router.get("/signal-history")
async def get_vix_signal_history(days: int = 30):
    """Get historical VIX hedge signals.
    Returns empty list if vix_hedge_manager is unavailable."""
    try:
        from core.vix_hedge_manager import get_vix_hedge_manager

        manager = get_vix_hedge_manager()
        history = manager.get_signal_history(days)

        if history.empty:
            return {"success": True, "data": []}

        formatted_data = []
        for _, row in history.iterrows():
            try:
                date_str = str(row.get('signal_date', ''))
                time_str = str(row.get('signal_time', '00:00:00'))
                timestamp = f"{date_str}T{time_str}"
            except Exception:
                timestamp = None

            formatted_data.append({
                "timestamp": timestamp,
                "signal_type": row.get('signal_type', 'no_action'),
                "vix_level": float(row.get('vix_spot', 0)) if row.get('vix_spot') else None,
                "confidence": float(row.get('confidence', 0)) if row.get('confidence') else None,
                "action_taken": row.get('recommended_action', 'Monitored')
            })

        return {
            "success": True,
            "data": formatted_data
        }
    except ImportError as e:
        print(f"⚠️ VIX hedge manager import failed for history: {e}")
        return {"success": True, "data": [], "fallback_mode": True, "message": "Signal history unavailable - module not loaded"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/current")
async def get_vix_current():
    """Get current VIX data and analysis with VVIX and stress indicators.
    Falls back to direct API calls if vix_hedge_manager is unavailable."""

    # Try to use vix_hedge_manager first
    try:
        from core.vix_hedge_manager import get_vix_hedge_manager
        manager = get_vix_hedge_manager()

        vix_data = manager.get_vix_data()
        vix_spot = vix_data.get('vix_spot', 18.0)

        iv_percentile = manager.calculate_iv_percentile(vix_spot)
        realized_vol = manager.calculate_realized_vol('SPY')
        vol_regime = manager.get_vol_regime(vix_spot)

        return {
            "success": True,
            "data": {
                "vix_spot": vix_spot,
                "vix_source": vix_data.get('vix_source', 'unknown'),
                "vix_m1": vix_data.get('vix_m1', 0),
                "vix_m2": vix_data.get('vix_m2', 0),
                "is_estimated": vix_data.get('is_estimated', True),
                "term_structure_pct": vix_data.get('term_structure_m1_pct', 0),
                "term_structure_m2_pct": vix_data.get('term_structure_m2_pct', 0),
                "structure_type": vix_data.get('structure_type', 'unknown'),
                "vvix": vix_data.get('vvix'),
                "vvix_source": vix_data.get('vvix_source', 'none'),
                "iv_percentile": iv_percentile,
                "realized_vol_20d": realized_vol,
                "iv_rv_spread": vix_spot - realized_vol,
                "vol_regime": vol_regime.value,
                "vix_stress_level": vix_data.get('vix_stress_level', 'unknown'),
                "position_size_multiplier": vix_data.get('position_size_multiplier', 1.0),
                "data_date": get_last_trading_day(),
                "timestamp": datetime.now().isoformat()
            }
        }
    except ImportError as e:
        print(f"⚠️ VIX hedge manager import failed: {e}, using fallback")
    except Exception as e:
        print(f"⚠️ VIX hedge manager error: {e}, using fallback")

    # FALLBACK: Use direct API calls when vix_hedge_manager is unavailable
    try:
        vix_data = get_vix_fallback_data()
        vix_spot = vix_data['vix_spot']

        # Estimate vol regime from VIX level
        if vix_spot >= 30:
            vol_regime = 'extreme'
        elif vix_spot >= 25:
            vol_regime = 'high'
        elif vix_spot >= 20:
            vol_regime = 'elevated'
        elif vix_spot >= 15:
            vol_regime = 'normal'
        else:
            vol_regime = 'low'

        return {
            "success": True,
            "data": {
                "vix_spot": vix_spot,
                "vix_source": vix_data.get('vix_source', 'fallback'),
                "vix_m1": vix_data.get('vix_m1', 0),
                "vix_m2": vix_data.get('vix_m2', 0),
                "is_estimated": vix_data.get('is_estimated', True),
                "term_structure_pct": vix_data.get('term_structure_m1_pct', 0),
                "term_structure_m2_pct": vix_data.get('term_structure_m2_pct', 0),
                "structure_type": vix_data.get('structure_type', 'unknown'),
                "vvix": vix_data.get('vvix'),
                "vvix_source": vix_data.get('vvix_source', 'none'),
                "iv_percentile": 50.0,  # Default estimate
                "realized_vol_20d": vix_spot * 0.9,  # Rough estimate
                "iv_rv_spread": vix_spot * 0.1,  # Rough estimate
                "vol_regime": vol_regime,
                "vix_stress_level": vix_data.get('vix_stress_level', 'normal'),
                "position_size_multiplier": vix_data.get('position_size_multiplier', 1.0),
                "data_date": get_last_trading_day(),
                "timestamp": datetime.now().isoformat(),
                "fallback_mode": True
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"VIX data error (fallback also failed): {type(e).__name__}: {str(e)}")


@router.get("/debug")
async def get_vix_debug():
    """VIX debugging endpoint - shows all VIX-related data and sources."""
    try:
        from core.vix_hedge_manager import get_vix_hedge_manager

        manager = get_vix_hedge_manager()
        vix_data = manager.get_vix_data()
        vix_spot = vix_data.get('vix_spot', 18.0)

        iv_percentile = manager.calculate_iv_percentile(vix_spot)
        realized_vol = manager.calculate_realized_vol('SPY')
        vol_regime = manager.get_vol_regime(vix_spot)

        raw_sources = {}

        try:
            from data.unified_data_provider import get_vix as unified_get_vix
            raw_sources['unified_provider'] = unified_get_vix()
        except Exception as e:
            raw_sources['unified_provider'] = f"Error: {e}"

        try:
            from data.polygon_data_fetcher import polygon_fetcher
            raw_sources['polygon'] = polygon_fetcher.get_current_price('^VIX')
        except Exception as e:
            raw_sources['polygon'] = f"Error: {e}"

        return {
            "success": True,
            "data": {
                "vix_data": vix_data,
                "raw_sources": raw_sources,
                "calculated_metrics": {
                    "iv_percentile": iv_percentile,
                    "realized_vol_20d": realized_vol,
                    "iv_rv_spread": vix_spot - realized_vol,
                    "vol_regime": vol_regime.value
                },
                "trading_impact": {
                    "stress_level": vix_data.get('vix_stress_level', 'unknown'),
                    "position_size_multiplier": vix_data.get('position_size_multiplier', 1.0),
                    "should_reduce_risk": vix_data.get('vix_stress_level') in ['high', 'extreme'],
                    "vvix_available": vix_data.get('vvix') is not None
                },
                "timestamp": datetime.now().isoformat()
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
