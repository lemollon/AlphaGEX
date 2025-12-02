"""
Volatility Surface API Routes

Exposes the volatility surface analysis that was previously orphaned.
Provides:
- IV surface visualization data
- Skew analysis (put/call skew)
- Term structure analysis
- Trading recommendations based on vol surface
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List, Dict
import logging
from datetime import datetime

router = APIRouter(prefix="/api/volatility-surface", tags=["Volatility Surface"])
logger = logging.getLogger(__name__)

# Try to import the volatility surface modules
VolatilitySurface = None
VolatilitySurfaceAnalyzer = None
VOLATILITY_SURFACE_AVAILABLE = False

try:
    from utils.volatility_surface import VolatilitySurface, SkewMetrics, TermStructure
    from core.volatility_surface_integration import (
        VolatilitySurfaceAnalyzer,
        EnhancedVolatilityData,
        SkewRegime,
        TermStructureRegime
    )
    VOLATILITY_SURFACE_AVAILABLE = True
    logger.info("✅ Volatility surface modules loaded")
except ImportError as e:
    logger.warning(f"⚠️ Volatility surface not available: {e}")


@router.get("/status")
async def get_volatility_surface_status():
    """Check if volatility surface analysis is available"""
    return {
        "success": True,
        "available": VOLATILITY_SURFACE_AVAILABLE,
        "message": "Volatility surface analysis ready" if VOLATILITY_SURFACE_AVAILABLE else "Volatility surface modules not available"
    }


@router.get("/analyze/{symbol}")
async def analyze_volatility_surface(
    symbol: str = "SPY",
    dte: int = Query(30, ge=1, le=365, description="Days to expiration to analyze")
):
    """
    Get comprehensive volatility surface analysis for a symbol.

    Returns:
    - Skew regime (put skew, call skew, normal)
    - Term structure regime (contango, backwardation)
    - IV percentile
    - Trading recommendations
    """
    if not VOLATILITY_SURFACE_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="Volatility surface analysis not available. Module not loaded."
        )

    try:
        # Get current spot price from unified data provider
        from data.unified_data_provider import get_data_provider
        provider = get_data_provider()

        quote = provider.get_quote(symbol)
        if not quote or quote.get('error'):
            raise HTTPException(status_code=404, detail=f"Could not get quote for {symbol}")

        spot_price = quote.get('last', quote.get('mid', 0))

        # Create volatility surface analyzer
        analyzer = VolatilitySurfaceAnalyzer(spot_price=spot_price)

        # Get options chain with Greeks
        chain = provider.get_options_chain(symbol, greeks=True)

        if not chain or not chain.chains:
            raise HTTPException(status_code=404, detail=f"No options chain available for {symbol}")

        # Add IV data from options chain
        for exp_date, contracts in chain.chains.items():
            # Calculate DTE
            exp_dt = datetime.strptime(exp_date, '%Y-%m-%d')
            dte_days = (exp_dt - datetime.now()).days

            if dte_days < 1 or dte_days > 90:
                continue

            chain_data = []
            for contract in contracts:
                if contract.implied_volatility and contract.implied_volatility > 0:
                    chain_data.append({
                        'strike': contract.strike,
                        'iv': contract.implied_volatility,
                        'delta': contract.delta,
                        'volume': contract.volume or 0,
                        'open_interest': contract.open_interest or 0
                    })

            if chain_data:
                analyzer.add_chain_data(chain_data, dte_days)

        # Get analysis
        analysis = analyzer.get_enhanced_analysis()

        if analysis is None:
            return {
                "success": False,
                "message": "Insufficient data to build volatility surface",
                "data": None
            }

        return {
            "success": True,
            "data": {
                "symbol": symbol,
                "spot_price": spot_price,
                "skew_regime": analysis.skew_regime.value if hasattr(analysis.skew_regime, 'value') else str(analysis.skew_regime),
                "term_structure_regime": analysis.term_structure_regime.value if hasattr(analysis.term_structure_regime, 'value') else str(analysis.term_structure_regime),
                "atm_iv": analysis.atm_iv,
                "iv_rank": analysis.iv_rank,
                "iv_percentile": analysis.iv_percentile,
                "skew_25d": analysis.skew_25d,
                "risk_reversal": analysis.risk_reversal,
                "butterfly": analysis.butterfly,
                "term_slope": analysis.term_slope,
                "directional_bias": analysis.get_directional_bias(),
                "should_sell_premium": analysis.should_sell_premium(),
                "optimal_strategy": analysis.get_optimal_strategy(),
                "timestamp": datetime.now().isoformat()
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error analyzing volatility surface: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/skew/{symbol}")
async def get_skew_analysis(symbol: str = "SPY"):
    """
    Get put/call skew analysis.

    Skew indicates market's fear gauge:
    - High put skew = fear of downside
    - High call skew = fear of missing rally
    - Normal skew = balanced market
    """
    if not VOLATILITY_SURFACE_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="Volatility surface analysis not available"
        )

    try:
        from data.unified_data_provider import get_data_provider
        provider = get_data_provider()

        quote = provider.get_quote(symbol)
        spot_price = quote.get('last', quote.get('mid', 450))

        analyzer = VolatilitySurfaceAnalyzer(spot_price=spot_price)

        # Get chain and analyze
        chain = provider.get_options_chain(symbol, greeks=True)

        if chain and chain.chains:
            # Use nearest expiration for skew analysis
            for exp_date, contracts in sorted(chain.chains.items())[:2]:
                exp_dt = datetime.strptime(exp_date, '%Y-%m-%d')
                dte_days = max(1, (exp_dt - datetime.now()).days)

                chain_data = [{
                    'strike': c.strike,
                    'iv': c.implied_volatility,
                    'delta': c.delta,
                    'volume': c.volume or 0,
                    'open_interest': c.open_interest or 0
                } for c in contracts if c.implied_volatility and c.implied_volatility > 0]

                if chain_data:
                    analyzer.add_chain_data(chain_data, dte_days)

        analysis = analyzer.get_enhanced_analysis()

        if not analysis:
            return {
                "success": False,
                "message": "Insufficient data for skew analysis",
                "data": None
            }

        return {
            "success": True,
            "data": {
                "symbol": symbol,
                "skew_regime": str(analysis.skew_regime),
                "skew_25d": analysis.skew_25d,
                "risk_reversal": analysis.risk_reversal,
                "butterfly": analysis.butterfly,
                "put_skew_slope": analysis.put_skew_slope if hasattr(analysis, 'put_skew_slope') else None,
                "call_skew_slope": analysis.call_skew_slope if hasattr(analysis, 'call_skew_slope') else None,
                "interpretation": _interpret_skew(analysis.skew_regime, analysis.skew_25d)
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting skew analysis: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/term-structure/{symbol}")
async def get_term_structure(symbol: str = "SPY"):
    """
    Get volatility term structure analysis.

    Term structure indicates:
    - Contango (upward sloping) = calm market expectations
    - Backwardation (downward sloping) = near-term fear
    """
    if not VOLATILITY_SURFACE_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="Volatility surface analysis not available"
        )

    try:
        from data.unified_data_provider import get_data_provider
        provider = get_data_provider()

        quote = provider.get_quote(symbol)
        spot_price = quote.get('last', quote.get('mid', 450))

        analyzer = VolatilitySurfaceAnalyzer(spot_price=spot_price)

        chain = provider.get_options_chain(symbol, greeks=True)

        term_points = []

        if chain and chain.chains:
            for exp_date, contracts in sorted(chain.chains.items()):
                exp_dt = datetime.strptime(exp_date, '%Y-%m-%d')
                dte_days = (exp_dt - datetime.now()).days

                if dte_days < 1 or dte_days > 180:
                    continue

                # Get ATM IV for this expiration
                atm_contracts = [
                    c for c in contracts
                    if c.implied_volatility and abs(c.strike - spot_price) < spot_price * 0.02
                ]

                if atm_contracts:
                    avg_iv = sum(c.implied_volatility for c in atm_contracts) / len(atm_contracts)
                    term_points.append({
                        'dte': dte_days,
                        'expiration': exp_date,
                        'atm_iv': round(avg_iv * 100, 2)  # Convert to percentage
                    })

        if not term_points:
            return {
                "success": False,
                "message": "Insufficient data for term structure",
                "data": None
            }

        # Determine term structure regime
        if len(term_points) >= 2:
            front_iv = term_points[0]['atm_iv']
            back_iv = term_points[-1]['atm_iv']
            slope = (back_iv - front_iv) / (term_points[-1]['dte'] - term_points[0]['dte'])

            if slope > 0.05:
                regime = "STEEP_CONTANGO"
            elif slope > 0:
                regime = "NORMAL_CONTANGO"
            elif slope > -0.05:
                regime = "FLAT"
            elif slope > -0.1:
                regime = "BACKWARDATION"
            else:
                regime = "STEEP_BACKWARDATION"
        else:
            regime = "INSUFFICIENT_DATA"
            slope = 0

        return {
            "success": True,
            "data": {
                "symbol": symbol,
                "term_structure_regime": regime,
                "slope": round(slope, 4),
                "term_points": term_points,
                "interpretation": _interpret_term_structure(regime)
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting term structure: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/trading-signal/{symbol}")
async def get_volatility_trading_signal(symbol: str = "SPY"):
    """
    Get trading signal based on volatility surface analysis.

    Recommends:
    - Strategy type (sell premium, buy premium, directional)
    - Optimal DTE
    - Optimal delta/strike selection
    """
    if not VOLATILITY_SURFACE_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="Volatility surface analysis not available"
        )

    try:
        # Get full analysis
        analysis_response = await analyze_volatility_surface(symbol)

        if not analysis_response.get('success') or not analysis_response.get('data'):
            return {
                "success": False,
                "message": "Could not generate trading signal",
                "signal": None
            }

        data = analysis_response['data']

        # Generate signal
        signal = {
            "symbol": symbol,
            "timestamp": datetime.now().isoformat(),
            "directional_bias": data.get('directional_bias', 'neutral'),
            "recommended_strategy": data.get('optimal_strategy', 'NONE'),
            "should_sell_premium": data.get('should_sell_premium', False),
            "iv_environment": _categorize_iv_environment(data.get('iv_percentile', 50)),
            "skew_regime": data.get('skew_regime'),
            "term_structure": data.get('term_structure_regime'),
            "confidence": _calculate_vol_signal_confidence(data)
        }

        # Add specific recommendations
        if signal['should_sell_premium']:
            signal['recommendations'] = [
                "IV is elevated - good for premium selling",
                f"Consider {signal['recommended_strategy']}",
                "Use shorter DTE (7-30 days) for theta decay"
            ]
        else:
            signal['recommendations'] = [
                "IV is low - premium selling less attractive",
                "Consider directional plays with defined risk",
                "Use longer DTE for more time value"
            ]

        return {
            "success": True,
            "signal": signal
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting trading signal: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _interpret_skew(skew_regime, skew_25d) -> str:
    """Generate human-readable skew interpretation"""
    if 'PUT' in str(skew_regime).upper():
        return "Market showing fear of downside - puts are expensive relative to calls"
    elif 'CALL' in str(skew_regime).upper():
        return "Market showing fear of missing upside - calls are expensive relative to puts"
    else:
        return "Balanced market expectations - normal skew pattern"


def _interpret_term_structure(regime: str) -> str:
    """Generate human-readable term structure interpretation"""
    interpretations = {
        "STEEP_CONTANGO": "Strong contango - market expects calm near-term, volatility to increase later",
        "NORMAL_CONTANGO": "Normal contango - typical term structure, no unusual fear",
        "FLAT": "Flat term structure - uncertainty about volatility direction",
        "BACKWARDATION": "Backwardation - near-term fear elevated, expecting volatility to decrease",
        "STEEP_BACKWARDATION": "Steep backwardation - significant near-term fear, possible event risk"
    }
    return interpretations.get(regime, "Insufficient data for interpretation")


def _categorize_iv_environment(iv_percentile: float) -> str:
    """Categorize IV environment"""
    if iv_percentile < 20:
        return "VERY_LOW"
    elif iv_percentile < 40:
        return "LOW"
    elif iv_percentile < 60:
        return "NORMAL"
    elif iv_percentile < 80:
        return "ELEVATED"
    else:
        return "HIGH"


def _calculate_vol_signal_confidence(data: Dict) -> float:
    """Calculate confidence in volatility-based signal"""
    confidence = 50.0  # Base confidence

    # Higher IV percentile = more confidence in premium selling
    iv_percentile = data.get('iv_percentile', 50)
    if iv_percentile > 70:
        confidence += 15
    elif iv_percentile > 50:
        confidence += 5

    # Clear skew regime adds confidence
    skew = data.get('skew_regime', '')
    if 'EXTREME' in str(skew).upper():
        confidence += 10
    elif 'HIGH' in str(skew).upper():
        confidence += 5

    # Term structure regime
    term = data.get('term_structure_regime', '')
    if 'STEEP' in str(term).upper():
        confidence += 10

    return min(95.0, confidence)
