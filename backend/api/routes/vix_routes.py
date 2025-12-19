"""
import logging
logger = logging.getLogger(__name__)
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
    Priority: Tradier -> Yahoo Finance (FREE) -> Polygon -> default.
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

    # Try direct Tradier $VIX.X (same as ARES - this works!)
    try:
        from data.tradier_data_fetcher import TradierDataFetcher
        use_sandbox = os.getenv('TRADIER_SANDBOX', 'true').lower() == 'true'
        tradier = TradierDataFetcher(sandbox=use_sandbox)
        vix_quote = tradier.get_quote("$VIX.X")
        if vix_quote and vix_quote.get('last'):
            vix_data['vix_spot'] = float(vix_quote['last'])
            vix_data['vix_source'] = 'tradier'
            vix_data['is_estimated'] = False
            logger.info(f"VIX from Tradier $VIX.X: {vix_data['vix_spot']}")
            return vix_data
    except Exception as e:
        logger.debug(f"Tradier $VIX.X failed: {e}")

    # Try unified data provider (Tradier) - backup
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
        logger.debug(f"Tradier VIX import failed (expected on some deployments): {e}")
    except Exception as e:
        logger.debug(f"Tradier VIX fallback failed: {e}")

    # Try Yahoo Finance (FREE - no API key needed!)
    try:
        import yfinance as yf
        vix_ticker = yf.Ticker("^VIX")

        # Method 1: Try info dict (most reliable)
        try:
            info = vix_ticker.info
            price = info.get('regularMarketPrice') or info.get('previousClose') or info.get('open', 0)
            if price and price > 0:
                vix_data['vix_spot'] = float(price)
                vix_data['vix_source'] = 'yahoo'
                vix_data['is_estimated'] = False
                logger.info(f"VIX from Yahoo Finance (info): {price}")
                return vix_data
        except Exception as e:
            logger.debug(f"Yahoo info failed: {e}")

        # Method 2: Try fast_info with bracket notation
        try:
            fast = vix_ticker.fast_info
            price = fast.get('lastPrice') if hasattr(fast, 'get') else getattr(fast, 'last_price', None)
            if not price:
                price = fast.get('previousClose') if hasattr(fast, 'get') else getattr(fast, 'previous_close', None)
            if price and price > 0:
                vix_data['vix_spot'] = float(price)
                vix_data['vix_source'] = 'yahoo'
                vix_data['is_estimated'] = False
                logger.info(f"VIX from Yahoo Finance (fast_info): {price}")
                return vix_data
        except Exception as e:
            logger.debug(f"Yahoo fast_info failed: {e}")

        # Method 3: Get from history (always works)
        hist = vix_ticker.history(period='5d')
        if not hist.empty:
            price = float(hist['Close'].iloc[-1])
            if price > 0:
                vix_data['vix_spot'] = price
                vix_data['vix_source'] = 'yahoo'
                vix_data['is_estimated'] = False
                logger.info(f"VIX from Yahoo Finance (history): {price}")
                return vix_data
    except ImportError:
        logger.debug("yfinance not installed")
    except Exception as e:
        logger.debug(f"Yahoo Finance VIX fallback failed: {e}")

    # Try Polygon (requires API key)
    polygon_key = os.getenv('POLYGON_API_KEY')
    if polygon_key:
        try:
            to_date = datetime.now().strftime('%Y-%m-%d')
            from_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')

            url = f"https://api.polygon.io/v2/aggs/ticker/I:VIX/range/1/day/{from_date}/{to_date}"
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
            logger.debug(f"Polygon VIX fallback failed: {e}")

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
        logger.debug(f" VIX hedge manager import failed: {e}, using fallback signal")
    except Exception as e:
        logger.debug(f" VIX hedge manager error: {e}, using fallback signal")

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
        logger.debug(f" VIX hedge manager import failed for history: {e}")
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
        logger.debug(f" VIX hedge manager import failed: {e}, using fallback")
    except Exception as e:
        logger.debug(f" VIX hedge manager error: {e}, using fallback")

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
            raw_sources['polygon'] = polygon_fetcher.get_current_price('I:VIX')
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


@router.get("/test-sources")
async def test_vix_sources():
    """
    Detailed VIX source testing - shows exactly what each source returns.
    Use this to debug VIX data issues.
    """
    results = {
        "polygon_api_key_set": bool(os.getenv('POLYGON_API_KEY')),
        "polygon_key_prefix": os.getenv('POLYGON_API_KEY', '')[:8] + '...' if os.getenv('POLYGON_API_KEY') else None,
        "tradier_api_key_set": bool(os.getenv('TRADIER_API_KEY')),
        "sources": {},
        "timestamp": datetime.now().isoformat()
    }

    # Test 1: Direct Polygon API call for I:VIX
    polygon_key = os.getenv('POLYGON_API_KEY')
    if polygon_key:
        try:
            to_date = datetime.now().strftime('%Y-%m-%d')
            from_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')

            # Test the prev endpoint (what we use for indices)
            url = f"https://api.polygon.io/v2/aggs/ticker/I:VIX/prev"
            params = {"apiKey": polygon_key}

            response = requests.get(url, params=params, timeout=10)
            results['sources']['polygon_prev_endpoint'] = {
                'url': url.replace(polygon_key, 'API_KEY'),
                'status_code': response.status_code,
                'response': response.json() if response.status_code == 200 else response.text[:500]
            }

            if response.status_code == 200:
                data = response.json()
                if data.get('status') == 'OK' and data.get('results'):
                    results['sources']['polygon_prev_endpoint']['extracted_vix'] = float(data['results'][0]['c'])
        except Exception as e:
            results['sources']['polygon_prev_endpoint'] = {'error': str(e)}

        # Also test the range endpoint (alternative)
        try:
            url = f"https://api.polygon.io/v2/aggs/ticker/I:VIX/range/1/day/{from_date}/{to_date}"
            params = {"apiKey": polygon_key, "sort": "desc", "limit": 1}

            response = requests.get(url, params=params, timeout=10)
            results['sources']['polygon_range_endpoint'] = {
                'url': url.replace(polygon_key, 'API_KEY'),
                'status_code': response.status_code,
                'response': response.json() if response.status_code == 200 else response.text[:500]
            }

            if response.status_code == 200:
                data = response.json()
                if data.get('status') == 'OK' and data.get('results'):
                    results['sources']['polygon_range_endpoint']['extracted_vix'] = float(data['results'][0]['c'])
        except Exception as e:
            results['sources']['polygon_range_endpoint'] = {'error': str(e)}
    else:
        results['sources']['polygon_prev_endpoint'] = {'error': 'POLYGON_API_KEY not set'}
        results['sources']['polygon_range_endpoint'] = {'error': 'POLYGON_API_KEY not set'}

    # Test 2: polygon_fetcher.get_current_price
    try:
        from data.polygon_data_fetcher import polygon_fetcher
        vix_via_fetcher = polygon_fetcher.get_current_price('I:VIX')
        results['sources']['polygon_fetcher_get_current_price'] = {
            'value': vix_via_fetcher,
            'success': vix_via_fetcher is not None and vix_via_fetcher > 0
        }
    except Exception as e:
        results['sources']['polygon_fetcher_get_current_price'] = {'error': str(e)}

    # Test 3: unified_data_provider.get_vix
    try:
        from data.unified_data_provider import get_vix as unified_get_vix
        vix_unified = unified_get_vix()
        results['sources']['unified_provider_get_vix'] = {
            'value': vix_unified,
            'success': vix_unified is not None and vix_unified > 0
        }
    except Exception as e:
        results['sources']['unified_provider_get_vix'] = {'error': str(e)}

    # Test 4: vix_hedge_manager.get_vix_data
    try:
        from core.vix_hedge_manager import get_vix_hedge_manager
        manager = get_vix_hedge_manager()
        vix_data = manager.get_vix_data()
        results['sources']['vix_hedge_manager'] = {
            'vix_spot': vix_data.get('vix_spot'),
            'vix_source': vix_data.get('vix_source'),
            'is_estimated': vix_data.get('is_estimated', True),
            'success': vix_data.get('vix_spot', 0) > 0 and vix_data.get('vix_source') != 'default'
        }
    except Exception as e:
        results['sources']['vix_hedge_manager'] = {'error': str(e)}

    # Test 5: Tradier VIX - EXACT same code as ARES (which works!)
    try:
        from data.tradier_data_fetcher import TradierDataFetcher
        import os as test_os
        use_sandbox = test_os.getenv('TRADIER_SANDBOX', 'true').lower() == 'true'
        tradier = TradierDataFetcher(sandbox=use_sandbox)
        results['sources']['tradier_sandbox_mode'] = use_sandbox

        # This is EXACTLY what ARES does and it returns VIX=15
        vix_quote = tradier.get_quote("$VIX.X")
        if vix_quote and vix_quote.get('last'):
            vix = float(vix_quote['last'])
            results['sources']['tradier_$VIX.X_ARES_style'] = {
                'value': vix,
                'success': True,
                'raw_response': vix_quote
            }
        else:
            results['sources']['tradier_$VIX.X_ARES_style'] = {
                'value': None,
                'success': False,
                'raw_response': vix_quote,
                'note': 'vix_quote is None or has no last price'
            }
    except Exception as e:
        results['sources']['tradier_$VIX.X_ARES_style'] = {'error': str(e)}

    # Also test other symbols
    tradier_api_key = os.getenv('TRADIER_API_KEY')
    if tradier_api_key:
        try:
            from data.tradier_data_fetcher import TradierDataFetcher
            use_sandbox = os.getenv('TRADIER_SANDBOX', 'true').lower() == 'true'
            tradier = TradierDataFetcher(sandbox=use_sandbox)
            results['sources']['tradier_api_key_set'] = True

            # Test other VIX symbols
            for symbol in ['VIX', 'VIXW']:
                try:
                    data = tradier.get_quote(symbol)
                    if data:
                        price = float(data.get('last', 0) or data.get('close', 0) or 0)
                        results['sources'][f'tradier_{symbol}'] = {
                            'value': price,
                            'raw_response': data,
                            'success': price > 0
                        }
                    else:
                        results['sources'][f'tradier_{symbol}'] = {
                            'value': None,
                            'raw_response': None,
                            'success': False,
                            'note': 'get_quote returned None'
                        }
                except Exception as e:
                    results['sources'][f'tradier_{symbol}'] = {'error': str(e)}
        except Exception as e:
            results['sources']['tradier'] = {'error': str(e)}
    else:
        results['sources']['tradier'] = {'error': 'TRADIER_API_KEY not set'}

    # Test 6: Yahoo Finance (FREE - no API key needed!)
    try:
        import yfinance as yf
        vix_ticker = yf.Ticker("^VIX")

        # Test info dict (most reliable)
        try:
            info = vix_ticker.info
            info_price = info.get('regularMarketPrice') or info.get('previousClose') or info.get('open', 0)
            results['sources']['yahoo_info'] = {
                'value': float(info_price) if info_price else None,
                'regularMarketPrice': info.get('regularMarketPrice'),
                'previousClose': info.get('previousClose'),
                'success': info_price is not None and info_price > 0
            }
        except Exception as e:
            results['sources']['yahoo_info'] = {'error': str(e)}

        # Test history (always works)
        try:
            hist = vix_ticker.history(period='5d')
            if not hist.empty:
                hist_price = float(hist['Close'].iloc[-1])
                results['sources']['yahoo_history'] = {
                    'value': hist_price,
                    'data_points': len(hist),
                    'success': hist_price > 0
                }
            else:
                results['sources']['yahoo_history'] = {'error': 'Empty history'}
        except Exception as e:
            results['sources']['yahoo_history'] = {'error': str(e)}

    except ImportError:
        results['sources']['yahoo'] = {'error': 'yfinance not installed'}
    except Exception as e:
        results['sources']['yahoo'] = {'error': str(e)}

    # Summary
    successful_sources = [k for k, v in results['sources'].items() if isinstance(v, dict) and v.get('success')]
    results['summary'] = {
        'working_sources': successful_sources,
        'total_sources_tested': len(results['sources']),
        'any_source_working': len(successful_sources) > 0
    }

    return results
