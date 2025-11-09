"""
AlphaGEX FastAPI Backend
Main application entry point - Professional Options Intelligence Platform
"""

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

# Add parent directory to path to import existing AlphaGEX modules
parent_dir = Path(__file__).parent.parent
sys.path.insert(0, str(parent_dir))

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.middleware.base import BaseHTTPMiddleware
import uvicorn

# Import existing AlphaGEX logic (DO NOT MODIFY THESE)
from core_classes_and_engines import TradingVolatilityAPI, MonteCarloEngine, BlackScholesPricer
from intelligence_and_strategies import ClaudeIntelligence, get_et_time, get_local_time, is_market_open, MultiStrategyOptimizer
from config_and_database import STRATEGIES

# Import probability calculator (NEW - Phase 2 Self-Learning)
from probability_calculator import ProbabilityCalculator

# Create FastAPI app
app = FastAPI(
    title="AlphaGEX API",
    description="Professional Options Intelligence Platform - Backend API",
    version="2.0.0",
    docs_url="/docs",  # Swagger UI
    redoc_url="/redoc"  # ReDoc
)

# Custom CORS Middleware - Ensures headers are added to ALL responses
class CORSHeaderMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Handle preflight OPTIONS requests
        if request.method == "OPTIONS":
            response = JSONResponse(content={"status": "ok"}, status_code=200)
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS, PATCH"
            response.headers["Access-Control-Allow-Headers"] = "*"
            response.headers["Access-Control-Max-Age"] = "3600"
            return response

        # Process the request
        response = await call_next(request)

        # Add CORS headers to all responses
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS, PATCH"
        response.headers["Access-Control-Allow-Headers"] = "*"
        response.headers["Access-Control-Expose-Headers"] = "*"

        return response

# Add custom CORS middleware FIRST
app.add_middleware(CORSHeaderMiddleware)

# CORS Configuration - Allow all origins for development
# IMPORTANT: In production, restrict this to specific domains
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins
    allow_credentials=False,  # Cannot use credentials with wildcard origins
    allow_methods=["*"],  # Allow all methods including OPTIONS
    allow_headers=["*"],  # Allow all headers
    expose_headers=["*"],
)

# Initialize existing AlphaGEX components (singleton pattern)
api_client = TradingVolatilityAPI()
claude_ai = ClaudeIntelligence()
monte_carlo = MonteCarloEngine()
pricer = BlackScholesPricer()
strategy_optimizer = MultiStrategyOptimizer()

# Initialize probability calculator (NEW - Phase 2 Self-Learning)
probability_calc = ProbabilityCalculator()

# ============================================================================
# Health Check & Status Endpoints
# ============================================================================

@app.get("/")
async def root():
    """Root endpoint - API health check"""
    return {
        "name": "AlphaGEX API",
        "version": "2.0.0",
        "status": "operational",
        "timestamp": datetime.now().isoformat(),
        "docs": "/docs",
        "redoc": "/redoc"
    }

@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring"""
    market_open = is_market_open()
    current_time_et = get_et_time()

    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "market": {
            "open": market_open,
            "current_time_et": current_time_et.strftime("%Y-%m-%d %H:%M:%S %Z")
        },
        "services": {
            "api_client": "operational",
            "claude_ai": "operational",
            "database": "operational"  # Will update when PostgreSQL is connected
        }
    }

@app.get("/api/rate-limit-status")
async def get_rate_limit_status():
    """Get current Trading Volatility API rate limit status and health"""
    return {
        "calls_this_minute": TradingVolatilityAPI._shared_api_call_count_minute,
        "limit_per_minute": 20,
        "remaining": max(0, 20 - TradingVolatilityAPI._shared_api_call_count_minute),
        "circuit_breaker_active": TradingVolatilityAPI._shared_circuit_breaker_active,
        "cache_size": len(TradingVolatilityAPI._shared_response_cache),
        "cache_duration_minutes": TradingVolatilityAPI._shared_cache_duration / 60,
        "total_calls_lifetime": TradingVolatilityAPI._shared_api_call_count,
        "status": "healthy" if not TradingVolatilityAPI._shared_circuit_breaker_active else "rate_limited",
        "recommendation": "Rate limit OK" if TradingVolatilityAPI._shared_api_call_count_minute < 15 else "Approaching limit - requests may queue"
    }

@app.get("/api/time")
async def get_time():
    """Get current market time and status"""
    et_time = get_et_time()
    ct_time = get_local_time('US/Central')
    market_open = is_market_open()

    return {
        "eastern_time": et_time.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "central_time": ct_time.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "market_open": market_open,
        "timestamp": datetime.now().isoformat()
    }

@app.get("/api/diagnostic")
async def diagnostic():
    """Diagnostic endpoint to check API configuration and connectivity"""
    import os

    # Check environment variables (without exposing actual values)
    api_key_configured = bool(
        os.getenv("TRADING_VOLATILITY_API_KEY") or
        os.getenv("TV_USERNAME") or
        os.getenv("tv_username")
    )

    api_key_source = "none"
    if os.getenv("TRADING_VOLATILITY_API_KEY"):
        api_key_source = "TRADING_VOLATILITY_API_KEY"
    elif os.getenv("TV_USERNAME"):
        api_key_source = "TV_USERNAME"
    elif os.getenv("tv_username"):
        api_key_source = "tv_username"

    # DON'T test API connectivity in health check - causes rate limits on deployment
    # Health checks should be fast and not make external API calls
    # API connectivity will be tested when endpoints are actually called

    return {
        "status": "diagnostic",
        "timestamp": datetime.now().isoformat(),
        "configuration": {
            "api_key_configured": api_key_configured,
            "api_key_source": api_key_source,
            "api_endpoint": api_client.endpoint if hasattr(api_client, 'endpoint') else "unknown"
        },
        "connectivity": {
            "note": "API connectivity tested on first actual endpoint call (not in health check)"
        },
        "cache_stats": api_client.get_api_usage_stats() if hasattr(api_client, 'get_api_usage_stats') else {}
    }

# ============================================================================
# GEX Data Endpoints
# ============================================================================

@app.get("/api/gex/{symbol}")
async def get_gex_data(symbol: str):
    """
    Get GEX (Gamma Exposure) data for a symbol

    Args:
        symbol: Stock symbol (e.g., SPY, QQQ, AAPL)

    Returns:
        GEX data including net_gex, spot_price, flip_point, levels, etc.
    """
    try:
        symbol = symbol.upper()

        # Use existing TradingVolatilityAPI (UNCHANGED)
        gex_data = api_client.get_net_gamma(symbol)

        # Enhanced error logging
        if not gex_data:
            print(f"❌ GEX API returned None for {symbol}")
            raise HTTPException(
                status_code=503,
                detail=f"Trading Volatility API returned no data for {symbol}. Check API key configuration."
            )

        if gex_data.get('error'):
            error_msg = gex_data['error']
            print(f"❌ GEX API error for {symbol}: {error_msg}")

            # Provide specific error messages
            if 'API key not configured' in error_msg or 'username not found' in error_msg:
                raise HTTPException(
                    status_code=503,
                    detail=f"Trading Volatility API key not configured. Please set TRADING_VOLATILITY_API_KEY or TV_USERNAME environment variable."
                )
            elif 'rate limit' in error_msg.lower():
                raise HTTPException(
                    status_code=429,
                    detail=f"Trading Volatility API rate limit exceeded. Please wait and try again."
                )
            elif 'No ticker data' in error_msg or 'No data found' in error_msg:
                raise HTTPException(
                    status_code=404,
                    detail=f"No GEX data available for {symbol}. The symbol may not be available in the Trading Volatility database today."
                )
            elif '403' in error_msg:
                raise HTTPException(
                    status_code=403,
                    detail=f"Trading Volatility API access denied (403 Forbidden). Your API key (I-RWFNBLR2S1DP) may need to be renewed or the service may have changed authentication methods. Please contact support@tradingvolatility.net to verify your account status and API access."
                )
            else:
                raise HTTPException(
                    status_code=503,
                    detail=f"GEX data not available for {symbol}: {error_msg}"
                )

        # Log successful fetch
        print(f"✅ Successfully fetched GEX data for {symbol} - spot: ${gex_data.get('spot_price', 0):.2f}, net_gex: {gex_data.get('net_gex', 0)/1e9:.2f}B")

        # Get GEX levels for support/resistance
        levels_data = api_client.get_gex_levels(symbol)

        # Get psychology data for probability calculation
        psychology_data = {}
        try:
            # Try to get RSI and psychology state (non-blocking)
            import yfinance as yf
            ticker = yf.Ticker(symbol)
            df_1d = ticker.history(period="30d", interval="1d")

            if not df_1d.empty:
                # Calculate simple RSI
                delta = df_1d['Close'].diff()
                gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                rs = gain / loss
                rsi = 100 - (100 / (1 + rs))
                current_rsi = rsi.iloc[-1] if not rsi.empty else 50

                # Determine psychology state based on RSI
                if current_rsi > 70:
                    psychology_data = {
                        'fomo_level': min(100, (current_rsi - 50) * 2),
                        'fear_level': max(0, (50 - current_rsi) * 2),
                        'state': 'FOMO' if current_rsi > 80 else 'MODERATE_FOMO'
                    }
                elif current_rsi < 30:
                    psychology_data = {
                        'fomo_level': max(0, (current_rsi - 50) * 2),
                        'fear_level': min(100, (50 - current_rsi) * 2),
                        'state': 'FEAR' if current_rsi < 20 else 'MODERATE_FEAR'
                    }
                else:
                    psychology_data = {
                        'fomo_level': 50,
                        'fear_level': 50,
                        'state': 'BALANCED'
                    }
            else:
                # Default values if no data
                psychology_data = {'fomo_level': 50, 'fear_level': 50, 'state': 'BALANCED'}
        except Exception as e:
            print(f"⚠️  Could not fetch psychology data for {symbol}: {e}")
            psychology_data = {'fomo_level': 50, 'fear_level': 50, 'state': 'BALANCED'}

        # Calculate probability (EOD and Next Day)
        spot_price = gex_data.get('spot_price', 0)
        net_gex = gex_data.get('net_gex', 0)
        flip_point = gex_data.get('flip_point', spot_price)

        # Determine MM state
        if net_gex < -2e9:
            mm_state = 'PANICKING'
        elif net_gex < -1e9:
            mm_state = 'SQUEEZING' if spot_price < flip_point else 'BREAKDOWN'
        elif net_gex > 1e9:
            mm_state = 'DEFENDING'
        else:
            mm_state = 'NEUTRAL'

        # Get VIX for volatility context
        vix_level = 18.0  # Default
        try:
            if symbol == 'VIX':
                vix_level = spot_price
            else:
                vix_ticker = yf.Ticker('VIX')
                vix_data = vix_ticker.history(period="1d")
                if not vix_data.empty:
                    vix_level = vix_data['Close'].iloc[-1]
        except:
            pass

        # Prepare GEX data for probability calculator
        prob_gex_data = {
            'net_gex': net_gex,
            'flip_point': flip_point,
            'call_wall': gex_data.get('call_wall', spot_price * 1.02),
            'put_wall': gex_data.get('put_wall', spot_price * 0.98),
            'vix': vix_level,
            'implied_vol': gex_data.get('implied_volatility', 0.25),
            'mm_state': mm_state
        }

        # Calculate EOD and Next Day probabilities
        eod_probability = None
        next_day_probability = None
        try:
            eod_probability = probability_calc.calculate_probability(
                symbol=symbol,
                current_price=spot_price,
                gex_data=prob_gex_data,
                psychology_data=psychology_data,
                prediction_type='EOD'
            )

            next_day_probability = probability_calc.calculate_probability(
                symbol=symbol,
                current_price=spot_price,
                gex_data=prob_gex_data,
                psychology_data=psychology_data,
                prediction_type='NEXT_DAY'
            )
        except Exception as e:
            print(f"⚠️  Could not calculate probability for {symbol}: {e}")

        # Enhance data with missing fields for frontend compatibility
        enhanced_data = {
            **gex_data,
            "total_call_gex": gex_data.get('total_call_gex', 0),
            "total_put_gex": gex_data.get('total_put_gex', 0),
            "key_levels": {
                "resistance": levels_data.get('resistance', []) if levels_data else [],
                "support": levels_data.get('support', []) if levels_data else []
            },
            # NEW: Add probability data
            "probability": {
                "eod": eod_probability,
                "next_day": next_day_probability
            } if eod_probability and next_day_probability else None,
            # Add psychology and MM state
            "psychology": psychology_data,
            "mm_state": mm_state,
            "vix": vix_level
        }

        return {
            "success": True,
            "symbol": symbol,
            "data": enhanced_data,
            "timestamp": datetime.now().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Unexpected error fetching GEX for {symbol}: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/gex/{symbol}/levels")
async def get_gex_levels(symbol: str):
    """
    Get GEX support/resistance levels for a symbol with strike-by-strike breakdown
    Filtered to +/- 7 day standard deviation range

    Args:
        symbol: Stock symbol

    Returns:
        Array of GEX levels with detailed strike data (call_gex, put_gex, OI, etc.)
    """
    try:
        symbol = symbol.upper()

        # Use get_gex_profile() to get detailed strike-level gamma data
        # This calls /gex/gammaOI endpoint which returns gamma_array
        # Already filtered to +/- 7 day STD in get_gex_profile()
        profile = api_client.get_gex_profile(symbol)

        if not profile or profile.get('error'):
            error_msg = profile.get('error', 'Unknown error') if profile else 'No data returned'
            print(f"❌ GEX profile API error for {symbol}: {error_msg}")

            if '403' in str(error_msg):
                raise HTTPException(
                    status_code=403,
                    detail=f"Trading Volatility API access denied (403 Forbidden). Your API key (I-RWFNBLR2S1DP) may need to be renewed or the service may have changed authentication methods. Please contact support@tradingvolatility.net to verify your account status and API access."
                )
            else:
                raise HTTPException(
                    status_code=404,
                    detail=f"GEX profile not available for {symbol}: {error_msg}"
                )

        # Extract strikes data from profile (already filtered to +/- 7 day STD)
        strikes = profile.get('strikes', [])

        if not strikes:
            print(f"⚠️ No strikes data in profile for {symbol}")
            print(f"DEBUG: Profile keys: {list(profile.keys())}")
            return {
                "success": True,
                "symbol": symbol,
                "levels": [],
                "data": [],
                "message": "No strike-level data available",
                "timestamp": datetime.now().isoformat()
            }

        # Debug: Log first strike to see available fields
        if len(strikes) > 0:
            print(f"DEBUG: First strike fields: {list(strikes[0].keys())}")
            print(f"DEBUG: First strike data: {strikes[0]}")
            print(f"DEBUG: Total strikes (filtered to +/- 7 day STD): {len(strikes)}")

        # Transform strikes to match frontend interface
        # Frontend expects: {strike, call_gex, put_gex, total_gex, call_oi, put_oi, pcr}
        levels_array = []
        for strike_data in strikes:
            level = {
                "strike": strike_data.get('strike', 0),
                "call_gex": strike_data.get('call_gamma', 0),
                "put_gex": strike_data.get('put_gamma', 0),
                "total_gex": strike_data.get('total_gamma', 0),
                "call_oi": strike_data.get('call_oi', 0),
                "put_oi": strike_data.get('put_oi', 0),
                "pcr": strike_data.get('put_call_ratio', 0)
            }
            levels_array.append(level)

        # Debug: Log summary of data AND check for missing OI
        print(f"✅ Returning {len(levels_array)} strike levels for {symbol} (filtered to +/- 7 day STD)")
        if len(levels_array) > 0:
            sample = levels_array[0]
            print(f"DEBUG: Sample transformed level: {sample}")
            print(f"DEBUG: Has OI data: call_oi={sample['call_oi']}, put_oi={sample['put_oi']}, pcr={sample['pcr']}")
            print(f"DEBUG: Has total_gex: {sample['total_gex']}")

            # Check if Trading Volatility API is returning OI data
            non_zero_oi_count = sum(1 for level in levels_array if level['call_oi'] > 0 or level['put_oi'] > 0)
            print(f"DEBUG: {non_zero_oi_count}/{len(levels_array)} strikes have non-zero OI data")

            if non_zero_oi_count == 0:
                print(f"⚠️ WARNING: Trading Volatility API not returning OI data for {symbol}")
                print(f"   This is normal for some symbols or during non-market hours")
                print(f"   Raw strike keys from API: {list(strikes[0].keys()) if strikes else 'N/A'}")

        return {
            "success": True,
            "symbol": symbol,
            "levels": levels_array,
            "data": levels_array,  # Also provide as .data for compatibility
            "count": len(levels_array),
            "spot_price": profile.get('spot_price', 0),
            "flip_point": profile.get('flip_point', 0),
            "call_wall": profile.get('call_wall', 0),
            "put_wall": profile.get('put_wall', 0),
            "has_oi_data": non_zero_oi_count > 0,  # Flag for frontend
            "oi_data_warning": "Trading Volatility API not returning OI data - this is normal for some symbols or during non-market hours" if non_zero_oi_count == 0 else None,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        print(f"❌ Error in get_gex_levels for {symbol}: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# Gamma Intelligence Endpoints
# ============================================================================

@app.get("/api/gamma/{symbol}/intelligence")
async def get_gamma_intelligence(symbol: str, vix: float = 20):
    """
    Get comprehensive gamma intelligence - SIMPLIFIED for speed

    Returns basic gamma metrics derived from GEX data without slow external calls
    """
    try:
        symbol = symbol.upper()
        print(f"=== GAMMA INTELLIGENCE REQUEST: {symbol}, VIX: {vix} ===")

        # Get basic GEX data (fast, already working)
        gex_data = api_client.get_net_gamma(symbol)

        # Check for errors (not 'success' field - that doesn't exist!)
        if not gex_data or gex_data.get('error'):
            error_msg = gex_data.get('error', 'Unknown error') if gex_data else 'No data returned'
            raise HTTPException(
                status_code=404,
                detail=f"GEX data not available for {symbol}: {error_msg}"
            )

        # Get detailed profile for strike-level gamma data
        profile = api_client.get_gex_profile(symbol)

        # Calculate total call and put gamma from strike-level data
        total_call_gamma = 0
        total_put_gamma = 0

        if profile and profile.get('strikes'):
            for strike in profile['strikes']:
                total_call_gamma += strike.get('call_gamma', 0)
                total_put_gamma += strike.get('put_gamma', 0)

        # If we don't have strike data, estimate from net_gex
        if total_call_gamma == 0 and total_put_gamma == 0:
            net_gex = gex_data.get('net_gex', 0)
            # Rough estimate: if net is positive, assume 60% calls, 40% puts
            if net_gex > 0:
                total_call_gamma = abs(net_gex) * 0.6
                total_put_gamma = abs(net_gex) * 0.4
            else:
                total_call_gamma = abs(net_gex) * 0.4
                total_put_gamma = abs(net_gex) * 0.6

        # Extract basic metrics
        net_gex = gex_data.get('net_gex', 0)
        spot_price = gex_data.get('spot_price', 0)

        # Calculate derived metrics
        total_gamma = total_call_gamma + total_put_gamma
        gamma_exposure_ratio = total_call_gamma / total_put_gamma if total_put_gamma > 0 else 0

        # Simple estimates (can be enhanced later)
        vanna_exposure = total_gamma * 0.15  # Approximate vanna as % of gamma
        charm_decay = -total_gamma * 0.05    # Approximate daily theta decay
        risk_reversal = (total_call_gamma - total_put_gamma) / total_gamma if total_gamma > 0 else 0
        skew_index = gamma_exposure_ratio

        # Determine market regime
        if net_gex > 0:
            regime_state = "Positive Gamma" if net_gex > 1e9 else "Neutral"
            volatility = "Low" if net_gex > 1e9 else "Moderate"
        else:
            regime_state = "Negative Gamma"
            volatility = "High"

        trend = "Bullish" if total_call_gamma > total_put_gamma else "Bearish" if total_put_gamma > total_call_gamma else "Neutral"

        # Determine Market Maker State and Trading Edge
        mm_state_name = "NEUTRAL"
        mm_state_data = STRATEGIES  # Will be replaced with actual MM_STATES

        # Import MM_STATES from config
        from config_and_database import MM_STATES

        # Determine which MM state we're in based on net_gex
        if net_gex < -3e9:
            mm_state_name = "PANICKING"
        elif net_gex < -2e9:
            mm_state_name = "TRAPPED"
        elif net_gex < -1e9:
            mm_state_name = "HUNTING"
        elif net_gex > 1e9:
            mm_state_name = "DEFENDING"
        else:
            mm_state_name = "NEUTRAL"

        # Get the MM state configuration
        mm_state = MM_STATES.get(mm_state_name, MM_STATES['NEUTRAL'])

        # Generate key observations
        observations = [
            f"Net GEX is {'positive' if net_gex > 0 else 'negative'} at ${abs(net_gex)/1e9:.2f}B",
            f"Call/Put gamma ratio: {gamma_exposure_ratio:.2f}",
            f"Market regime: {regime_state} with {volatility.lower()} volatility"
        ]

        # Trading implications
        implications = [
            f"{'Reduced' if net_gex > 0 else 'Increased'} volatility expected",
            f"Price likely to {'stabilize' if net_gex > 0 else 'trend'} near current levels",
            f"Consider {'selling' if net_gex > 0 else 'buying'} volatility"
        ]

        # Get strike-level data for heatmap visualization
        strikes_data = []
        if profile and profile.get('strikes'):
            strikes_data = profile['strikes']

        # Build response matching frontend expectations
        intelligence = {
            "symbol": symbol,
            "spot_price": spot_price,
            "total_gamma": total_gamma,
            "call_gamma": total_call_gamma,
            "put_gamma": total_put_gamma,
            "gamma_exposure_ratio": gamma_exposure_ratio,
            "vanna_exposure": vanna_exposure,
            "charm_decay": charm_decay,
            "risk_reversal": risk_reversal,
            "skew_index": skew_index,
            "key_observations": observations,
            "trading_implications": implications,
            "market_regime": {
                "state": regime_state,
                "volatility": volatility,
                "trend": trend
            },
            "mm_state": {
                "name": mm_state_name,
                "behavior": mm_state['behavior'],
                "confidence": mm_state['confidence'],
                "action": mm_state['action'],
                "threshold": mm_state['threshold']
            },
            "net_gex": net_gex,  # Add net_gex for MM state context
            "strikes": strikes_data,  # Include strike-level data for visualizations
            "flip_point": profile.get('flip_point', 0) if profile else 0,
            "call_wall": profile.get('call_wall', 0) if profile else 0,
            "put_wall": profile.get('put_wall', 0) if profile else 0
        }

        print(f"✅ Gamma intelligence generated successfully for {symbol}")

        return {
            "success": True,
            "symbol": symbol,
            "data": intelligence,
            "timestamp": datetime.now().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error in gamma intelligence: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/gamma/{symbol}/expiration")
async def get_gamma_expiration(symbol: str):
    """
    Get gamma expiration intelligence for 0DTE trading

    Returns weekly gamma decay patterns, daily risk levels, and trading strategies
    """
    try:
        symbol = symbol.upper()
        print(f"=== GAMMA EXPIRATION REQUEST: {symbol} ===")

        # Get current GEX data
        gex_data = api_client.get_net_gamma(symbol)

        if not gex_data or gex_data.get('error'):
            error_msg = gex_data.get('error', 'Unknown error') if gex_data else 'No data returned'
            raise HTTPException(
                status_code=404,
                detail=f"GEX data not available for {symbol}: {error_msg}"
            )

        # Get current day of week
        from datetime import datetime
        today = datetime.now()
        day_name = today.strftime('%A')
        day_num = today.weekday()  # 0=Monday, 4=Friday

        # Estimate weekly gamma pattern (front-loaded decay typical for 0DTE)
        # Monday starts at 100%, decays heavily through week
        weekly_gamma_pattern = {
            0: 1.00,  # Monday
            1: 0.71,  # Tuesday
            2: 0.42,  # Wednesday
            3: 0.12,  # Thursday
            4: 0.08   # Friday
        }

        # Current gamma from API
        net_gex = gex_data.get('net_gex', 0)
        spot_price = gex_data.get('spot_price', 0)
        flip_point = gex_data.get('flip_point', 0)

        # Estimate total weekly gamma (reverse calculate from current day)
        current_day_pct = weekly_gamma_pattern.get(day_num, 0.5)
        estimated_monday_gamma = abs(net_gex) / current_day_pct if current_day_pct > 0 else abs(net_gex)

        # Calculate weekly gamma for each day
        weekly_gamma = {
            'monday': estimated_monday_gamma * weekly_gamma_pattern[0],
            'tuesday': estimated_monday_gamma * weekly_gamma_pattern[1],
            'wednesday': estimated_monday_gamma * weekly_gamma_pattern[2],
            'thursday': estimated_monday_gamma * weekly_gamma_pattern[3],
            'friday': estimated_monday_gamma * weekly_gamma_pattern[4],
            'total_decay_pct': 92,
            'decay_pattern': 'FRONT_LOADED'
        }

        # Current vs after close
        current_gamma = abs(net_gex)
        next_day_num = (day_num + 1) % 5
        next_day_pct = weekly_gamma_pattern.get(next_day_num, 0.08)
        after_close_gamma = estimated_monday_gamma * next_day_pct
        gamma_loss_today = current_gamma - after_close_gamma
        gamma_loss_pct = int((gamma_loss_today / current_gamma * 100)) if current_gamma > 0 else 0

        # Calculate daily risk levels
        # Risk based on gamma decay rate and volatility
        daily_risks = {
            'monday': 29,    # Low risk, max gamma
            'tuesday': 41,   # Moderate, gamma declining
            'wednesday': 70, # High, major decay point
            'thursday': 38,  # Moderate, post-decay
            'friday': 100    # Extreme, final expiration
        }

        # Determine risk level for today
        today_risk = daily_risks.get(day_name.lower(), 50)
        if today_risk >= 70:
            risk_level = 'EXTREME'
        elif today_risk >= 50:
            risk_level = 'HIGH'
        elif today_risk >= 30:
            risk_level = 'MODERATE'
        else:
            risk_level = 'LOW'

        expiration_data = {
            'symbol': symbol,
            'current_day': day_name,
            'current_gamma': current_gamma,
            'after_close_gamma': after_close_gamma,
            'gamma_loss_today': gamma_loss_today,
            'gamma_loss_pct': gamma_loss_pct,
            'risk_level': risk_level,
            'weekly_gamma': weekly_gamma,
            'daily_risks': daily_risks,
            'spot_price': spot_price,
            'flip_point': flip_point,
            'net_gex': net_gex
        }

        print(f"✅ Gamma expiration data generated for {symbol}")

        return {
            "success": True,
            "symbol": symbol,
            "data": expiration_data,
            "timestamp": datetime.now().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error fetching gamma expiration: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/gamma/{symbol}/history")
async def get_gamma_history(symbol: str, days: int = 30):
    """
    Get historical gamma exposure data for trend analysis

    Args:
        symbol: Stock symbol
        days: Number of days of history to fetch (default 30)

    Returns:
        Historical gamma data including net_gex, spot_price, etc.
    """
    try:
        symbol = symbol.upper()
        print(f"=== GAMMA HISTORY REQUEST: {symbol}, days: {days} ===")

        # Use existing TradingVolatilityAPI to get historical data
        history_data = api_client.get_historical_gamma(symbol, days_back=days)

        if not history_data:
            return {
                "success": True,
                "symbol": symbol,
                "data": [],
                "message": "No historical data available",
                "timestamp": datetime.now().isoformat()
            }

        # Transform data for frontend
        formatted_history = []
        for entry in history_data:
            formatted_history.append({
                "date": entry.get('collection_date', ''),
                "price": float(entry.get('price', 0)),
                "net_gex": float(entry.get('skew_adjusted_gex', 0)),
                "flip_point": float(entry.get('gex_flip_price', 0)),
                "implied_volatility": float(entry.get('implied_volatility', 0)),
                "put_call_ratio": float(entry.get('put_call_ratio_open_interest', 0))
            })

        print(f"✅ Fetched {len(formatted_history)} historical data points for {symbol}")

        return {
            "success": True,
            "symbol": symbol,
            "data": formatted_history,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        print(f"❌ Error fetching gamma history: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# AI Copilot Endpoints
# ============================================================================

@app.post("/api/ai/analyze")
async def ai_analyze_market(request: dict):
    """
    Generate AI market analysis and trade recommendations

    Request body:
    {
        "symbol": "SPY",
        "query": "What's the best trade right now?",
        "market_data": {...},  # Optional GEX data
        "gamma_intel": {...}   # Optional gamma intelligence
    }

    Returns:
        Claude AI analysis and recommendations
    """
    try:
        symbol = request.get('symbol', 'SPY').upper()
        query = request.get('query', '')
        market_data = request.get('market_data', {})
        gamma_intel = request.get('gamma_intel')

        if not query:
            raise HTTPException(status_code=400, detail="Query is required")

        # If no market data provided, fetch it
        if not market_data:
            gex_data = api_client.get_net_gamma(symbol)
            market_data = {
                'net_gex': gex_data.get('net_gex', 0),
                'spot_price': gex_data.get('spot_price', 0),
                'flip_point': gex_data.get('flip_point', 0),
                'symbol': symbol
            }

        # Use existing ClaudeIntelligence (UNCHANGED LOGIC)
        ai_response = claude_ai.analyze_market(
            market_data=market_data,
            user_query=query,
            gamma_intel=gamma_intel
        )

        return {
            "success": True,
            "symbol": symbol,
            "query": query,
            "response": ai_response,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# WebSocket - Real-Time Market Data
# ============================================================================

class ConnectionManager:
    """Manage WebSocket connections"""

    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except:
                pass

manager = ConnectionManager()

@app.websocket("/ws/market-data")
async def websocket_market_data(websocket: WebSocket, symbol: str = "SPY"):
    """
    WebSocket endpoint for real-time market data updates

    Query params:
        symbol: Stock symbol to monitor (default: SPY)

    Sends updates every 30 seconds during market hours
    """
    await manager.connect(websocket)
    symbol = symbol.upper()

    try:
        import asyncio

        while True:
            # Check if market is open
            if is_market_open():
                # Fetch latest GEX data
                gex_data = api_client.get_net_gamma(symbol)

                # Send update to client
                await websocket.send_json({
                    "type": "market_update",
                    "symbol": symbol,
                    "data": gex_data,
                    "timestamp": datetime.now().isoformat()
                })

                # Wait 30 seconds
                await asyncio.sleep(30)
            else:
                # Market closed - send status and wait longer
                await websocket.send_json({
                    "type": "market_closed",
                    "message": "Market is currently closed",
                    "timestamp": datetime.now().isoformat()
                })

                # Wait 5 minutes when market is closed
                await asyncio.sleep(300)

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        manager.disconnect(websocket)
        print(f"WebSocket error: {e}")

# ============================================================================
# Error Handlers
# ============================================================================

@app.exception_handler(404)
async def not_found_handler(request, exc):
    response = JSONResponse(
        status_code=404,
        content={
            "success": False,
            "error": "Not found",
            "detail": str(exc.detail) if hasattr(exc, 'detail') else "Resource not found"
        }
    )
    # Add CORS headers to error responses
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS, PATCH"
    response.headers["Access-Control-Allow-Headers"] = "*"
    return response

@app.exception_handler(500)
async def internal_error_handler(request, exc):
    response = JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": "Internal server error",
            "detail": str(exc)
        }
    )
    # Add CORS headers to error responses
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS, PATCH"
    response.headers["Access-Control-Allow-Headers"] = "*"
    return response

# ============================================================================
# ============================================================================
# Position Sizing Endpoints
# ============================================================================

@app.post("/api/position-sizing/calculate")
async def calculate_position_sizing(
    account_size: float,
    risk_percent: float,
    win_rate: float,
    risk_reward: float,
    option_premium: float,
    max_loss_per_contract: float = None
):
    """
    Calculate optimal position size using Kelly Criterion and Risk of Ruin

    Returns:
    - Kelly Criterion sizing
    - Optimal F sizing
    - Risk of Ruin probability
    - Recommended contracts
    """
    try:
        # Kelly Criterion: f* = (p*b - q) / b
        # where p = win probability, q = loss probability, b = win/loss ratio
        p = win_rate / 100  # Convert percentage to decimal
        q = 1 - p
        b = risk_reward  # win/loss ratio

        kelly_pct = ((p * b) - q) / b if b > 0 else 0
        kelly_pct = max(0, min(kelly_pct, 1))  # Clamp between 0 and 1

        # Half Kelly (more conservative, recommended)
        half_kelly_pct = kelly_pct / 2

        # Quarter Kelly (very conservative)
        quarter_kelly_pct = kelly_pct / 4

        # Calculate actual dollar amounts
        kelly_dollars = account_size * kelly_pct
        half_kelly_dollars = account_size * half_kelly_pct
        quarter_kelly_dollars = account_size * quarter_kelly_pct

        # User's current risk amount
        user_risk_dollars = account_size * (risk_percent / 100)

        # Calculate contracts based on different methods
        max_loss = max_loss_per_contract if max_loss_per_contract else (option_premium * 100)

        kelly_contracts = max(1, int(kelly_dollars / max_loss))
        half_kelly_contracts = max(1, int(half_kelly_dollars / max_loss))
        quarter_kelly_contracts = max(1, int(quarter_kelly_dollars / max_loss))
        user_contracts = max(1, int(user_risk_dollars / max_loss))

        # Risk of Ruin calculation (simplified)
        # Probability of losing entire account with given win rate and risk per trade
        risk_of_ruin_kelly = calculate_risk_of_ruin(p, kelly_pct)
        risk_of_ruin_half_kelly = calculate_risk_of_ruin(p, half_kelly_pct)
        risk_of_ruin_user = calculate_risk_of_ruin(p, risk_percent / 100)

        # Optimal F (Ralph Vince method)
        # Simplified: f = 1 / biggest_loss_percentage
        # For options, assume biggest loss = 100% of premium
        optimal_f_pct = 1 / (max_loss / account_size) if max_loss > 0 else 0
        optimal_f_pct = min(optimal_f_pct, kelly_pct)  # Never exceed Kelly
        optimal_f_contracts = max(1, int((account_size * optimal_f_pct) / max_loss))

        return {
            "success": True,
            "kelly_criterion": {
                "full_kelly_pct": round(kelly_pct * 100, 2),
                "half_kelly_pct": round(half_kelly_pct * 100, 2),
                "quarter_kelly_pct": round(quarter_kelly_pct * 100, 2),
                "full_kelly_dollars": round(kelly_dollars, 2),
                "half_kelly_dollars": round(half_kelly_dollars, 2),
                "quarter_kelly_dollars": round(quarter_kelly_dollars, 2),
                "full_kelly_contracts": kelly_contracts,
                "half_kelly_contracts": half_kelly_contracts,
                "quarter_kelly_contracts": quarter_kelly_contracts,
                "risk_of_ruin": round(risk_of_ruin_kelly * 100, 2)
            },
            "optimal_f": {
                "optimal_f_pct": round(optimal_f_pct * 100, 2),
                "optimal_f_contracts": optimal_f_contracts,
                "optimal_f_dollars": round(account_size * optimal_f_pct, 2)
            },
            "user_sizing": {
                "user_risk_pct": risk_percent,
                "user_risk_dollars": round(user_risk_dollars, 2),
                "user_contracts": user_contracts,
                "risk_of_ruin": round(risk_of_ruin_user * 100, 2)
            },
            "recommendation": {
                "recommended_method": "Half Kelly" if half_kelly_pct < risk_percent / 100 else "Quarter Kelly",
                "recommended_contracts": half_kelly_contracts if half_kelly_pct < risk_percent / 100 else quarter_kelly_contracts,
                "recommended_dollars": round(half_kelly_dollars if half_kelly_pct < risk_percent / 100 else quarter_kelly_dollars, 2),
                "recommended_pct": round((half_kelly_pct if half_kelly_pct < risk_percent / 100 else quarter_kelly_pct) * 100, 2),
                "reasoning": "Half Kelly balances growth with safety" if half_kelly_pct < risk_percent / 100 else "Quarter Kelly recommended for higher risk setups"
            },
            "parameters": {
                "account_size": account_size,
                "risk_percent": risk_percent,
                "win_rate": win_rate,
                "risk_reward": risk_reward,
                "option_premium": option_premium,
                "max_loss_per_contract": max_loss
            }
        }

    except Exception as e:
        print(f"❌ Error in position sizing calculation: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

def calculate_risk_of_ruin(win_rate: float, risk_per_trade: float) -> float:
    """
    Calculate probability of ruin (losing entire account)

    Simplified formula based on gambler's ruin problem
    """
    if win_rate >= 1.0 or risk_per_trade <= 0:
        return 0.0

    if win_rate <= 0.0:
        return 1.0

    # Simplified: higher risk per trade and lower win rate = higher ruin probability
    # This is an approximation
    ruin_prob = (1 - win_rate) / win_rate * risk_per_trade * 10
    return min(1.0, max(0.0, ruin_prob))

# ============================================================================
# Autonomous Trader Endpoints
# ============================================================================
# ============================================================================

# Initialize trader (if exists)
try:
    from autonomous_paper_trader import AutonomousPaperTrader
    trader = AutonomousPaperTrader()
    trader_available = True
except:
    trader = None
    trader_available = False

@app.get("/api/trader/status")
async def get_trader_status():
    """Get autonomous trader status"""
    if not trader_available:
        return {
            "success": False,
            "message": "Trader not configured",
            "data": {
                "is_active": False,
                "mode": "paper",
                "uptime": 0,
                "last_check": datetime.now().isoformat(),
                "strategies_active": 0,
                "total_trades_today": 0
            }
        }

    try:
        # Get live status from trader
        live_status = trader.get_live_status()
        mode = trader.get_config('mode') if trader else 'paper'

        return {
            "success": True,
            "data": {
                "is_active": live_status.get('is_working', False),
                "mode": mode,
                "status": live_status.get('status', 'UNKNOWN'),
                "current_action": live_status.get('current_action', 'System initializing...'),
                "market_analysis": live_status.get('market_analysis'),
                "last_decision": live_status.get('last_decision'),
                "last_check": live_status.get('timestamp', datetime.now().isoformat()),
                "next_check": live_status.get('next_check_time'),
                "strategies_active": 2,  # TODO: Get from trader config
                "total_trades_today": 0  # TODO: Calculate from database
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/trader/live-status")
async def get_trader_live_status():
    """
    Get real-time "thinking out loud" status from autonomous trader
    Shows what the trader is currently doing and its analysis
    """
    if not trader_available:
        return {
            "success": False,
            "message": "Trader not configured",
            "data": {
                "status": "OFFLINE",
                "current_action": "Trader service not available",
                "is_working": False
            }
        }

    try:
        live_status = trader.get_live_status()

        # Add diagnostic info
        print(f"📊 Trader Live Status Query:")
        print(f"   Database: {trader.db_path}")
        print(f"   Status: {live_status.get('status')}")
        print(f"   Action: {live_status.get('current_action')}")
        print(f"   Timestamp: {live_status.get('timestamp')}")

        return {
            "success": True,
            "data": live_status
        }
    except Exception as e:
        print(f"❌ ERROR reading trader status: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/trader/performance")
async def get_trader_performance():
    """Get autonomous trader performance metrics"""
    if not trader_available:
        return {
            "success": False,
            "message": "Trader not configured",
            "data": {
                "total_pnl": 0,
                "today_pnl": 0,
                "win_rate": 0,
                "total_trades": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "sharpe_ratio": 0,
                "max_drawdown": 0
            }
        }

    try:
        perf = trader.get_performance()

        # Calculate additional metrics
        winning_trades = int(perf['total_trades'] * perf['win_rate'] / 100) if perf['total_trades'] > 0 else 0
        losing_trades = perf['total_trades'] - winning_trades

        return {
            "success": True,
            "data": {
                "total_pnl": perf['total_pnl'],
                "today_pnl": perf['unrealized_pnl'],  # Approximate
                "win_rate": perf['win_rate'],
                "total_trades": perf['total_trades'],
                "winning_trades": winning_trades,
                "losing_trades": losing_trades,
                "sharpe_ratio": 0,  # TODO: Calculate sharpe ratio
                "max_drawdown": 0  # TODO: Calculate max drawdown
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/trader/trades")
async def get_trader_trades(limit: int = 10):
    """Get recent trades from autonomous trader"""
    if not trader_available:
        return {
            "success": False,
            "message": "Trader not configured",
            "data": []
        }

    try:
        import sqlite3
        import pandas as pd

        conn = sqlite3.connect(trader.db_path)
        trades = pd.read_sql_query(f"""
            SELECT * FROM autonomous_positions
            ORDER BY entry_date DESC, entry_time DESC
            LIMIT {limit}
        """, conn)
        conn.close()

        trades_list = trades.to_dict('records') if not trades.empty else []

        return {
            "success": True,
            "data": trades_list
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/trader/positions")
async def get_open_positions():
    """Get currently open positions"""
    if not trader_available:
        return {
            "success": False,
            "message": "Trader not configured",
            "data": []
        }

    try:
        import sqlite3
        import pandas as pd

        conn = sqlite3.connect(trader.db_path)
        positions = pd.read_sql_query("""
            SELECT * FROM autonomous_positions
            WHERE status = 'OPEN'
            ORDER BY entry_date DESC, entry_time DESC
        """, conn)
        conn.close()

        positions_list = positions.to_dict('records') if not positions.empty else []

        return {
            "success": True,
            "data": positions_list
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/trader/trade-log")
async def get_trade_log():
    """Get today's trade log"""
    if not trader_available:
        return {
            "success": False,
            "message": "Trader not configured",
            "data": []
        }

    try:
        import sqlite3
        import pandas as pd
        from datetime import datetime

        conn = sqlite3.connect(trader.db_path)

        # Get today's date in Central Time
        from intelligence_and_strategies import get_local_time
        today = get_local_time('US/Central').strftime('%Y-%m-%d')

        log_entries = pd.read_sql_query(f"""
            SELECT * FROM autonomous_trade_log
            WHERE date = '{today}'
            ORDER BY time DESC
        """, conn)
        conn.close()

        log_list = log_entries.to_dict('records') if not log_entries.empty else []

        return {
            "success": True,
            "data": log_list
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/trader/execute")
async def execute_trader_cycle():
    """
    Execute one autonomous trader cycle NOW

    This endpoint:
    1. Finds and executes a daily trade (if not already traded today)
    2. Manages existing open positions
    3. Returns the results
    """
    if not trader_available:
        return {
            "success": False,
            "message": "Trader not configured",
            "error": "Autonomous trader module not available"
        }

    try:
        print("\n" + "="*60)
        print(f"🤖 MANUAL TRADER EXECUTION - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*60 + "\n")

        # Update status
        trader.update_live_status(
            status='MANUAL_EXECUTION',
            action='Manual execution triggered via API',
            analysis='User initiated trader cycle'
        )

        results = {
            "new_trade": None,
            "closed_positions": [],
            "message": ""
        }

        # Step 1: Try to find and execute new trade
        print("🔍 Checking for new trade opportunity...")
        try:
            position_id = trader.find_and_execute_daily_trade(api_client)

            if position_id:
                print(f"✅ SUCCESS: Opened position #{position_id}")
                results["new_trade"] = {
                    "position_id": position_id,
                    "message": f"Successfully opened position #{position_id}"
                }
                results["message"] = f"New position #{position_id} opened"
            else:
                print("ℹ️  INFO: No new trade (already traded today or no setup found)")
                results["message"] = "No new trade (already traded today or no qualifying setup)"

        except Exception as e:
            print(f"❌ ERROR during trade execution: {e}")
            import traceback
            traceback.print_exc()
            results["message"] = f"Trade execution error: {str(e)}"

        # Step 2: Manage existing positions
        print("\n🔄 Checking open positions for exit conditions...")
        try:
            actions = trader.auto_manage_positions(api_client)

            if actions:
                print(f"✅ SUCCESS: Closed {len(actions)} position(s)")
                for action in actions:
                    print(f"   - {action['strategy']}: P&L ${action['pnl']:+,.2f} ({action['pnl_pct']:+.1f}%) - {action['reason']}")

                results["closed_positions"] = actions
                if not results["message"]:
                    results["message"] = f"Closed {len(actions)} position(s)"
                else:
                    results["message"] += f", closed {len(actions)} position(s)"
            else:
                print("ℹ️  INFO: All positions look good - no exits needed")
                if not results["message"]:
                    results["message"] = "No exits needed"

        except Exception as e:
            print(f"❌ ERROR during position management: {e}")
            import traceback
            traceback.print_exc()

        # Step 3: Get performance summary
        perf = trader.get_performance()
        print("\n📊 PERFORMANCE SUMMARY:")
        print(f"   Starting Capital: ${perf['starting_capital']:,.0f}")
        print(f"   Current Value: ${perf['current_value']:,.2f}")
        print(f"   Total P&L: ${perf['total_pnl']:+,.2f} ({perf['return_pct']:+.2f}%)")
        print(f"   Total Trades: {perf['total_trades']}")
        print(f"   Open Positions: {perf['open_positions']}")
        print(f"   Win Rate: {perf['win_rate']:.1f}%")

        print(f"\n{'='*60}")
        print("CYCLE COMPLETE")
        print("="*60 + "\n")

        return {
            "success": True,
            "data": {
                **results,
                "performance": perf
            }
        }

    except Exception as e:
        print(f"❌ CRITICAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/market/price-history/{symbol}")
async def get_price_history(symbol: str, days: int = 90):
    """
    Get price history for charting using yfinance

    YAHOO FINANCE RATE LIMITS (as of 2025):
    - ~2000 requests per hour per IP
    - ~48000 requests per day per IP
    - Rate limit resets every hour
    - 429 error when limit exceeded
    - No official documentation - limits discovered through testing

    RECOMMENDATION: Use TradingView widget instead to avoid rate limits
    """
    try:
        symbol = symbol.upper()

        import yfinance as yf
        from datetime import datetime, timedelta
        import time

        print(f"📊 Fetching {days}-day price history for {symbol}")
        print(f"⚠️  Yahoo Finance rate limits: ~2000 req/hour, resets hourly")

        # Calculate date range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days + 10)  # Add buffer for weekends/holidays

        try:
            # Add small delay to avoid rate limiting
            time.sleep(0.5)

            # Fetch data using yfinance with explicit date range
            ticker = yf.Ticker(symbol)
            hist = ticker.history(start=start_date, end=end_date)

            if hist.empty:
                print(f"❌ yfinance returned no data for {symbol}")
                print(f"   Possible reasons:")
                print(f"   1. Yahoo Finance rate limit (2000 req/hour)")
                print(f"   2. Invalid symbol")
                print(f"   3. Yahoo API downtime")
                raise HTTPException(
                    status_code=503,
                    detail=f"Yahoo Finance returned no data. Possible rate limit (2000 req/hour). Use TradingView widget for reliable charts."
                )

            # Convert to chart format
            chart_data = []
            for date, row in hist.iterrows():
                chart_data.append({
                    "time": int(date.timestamp()),
                    "value": float(row['Close'])
                })

            print(f"✅ Successfully fetched {len(chart_data)} data points for {symbol}")
            print(f"   Date range: {hist.index[0].date()} to {hist.index[-1].date()}")
            print(f"   Price range: ${hist['Close'].min():.2f} - ${hist['Close'].max():.2f}")

            return {
                "success": True,
                "symbol": symbol,
                "data": chart_data,
                "points": len(chart_data),
                "start_date": hist.index[0].isoformat(),
                "end_date": hist.index[-1].isoformat(),
                "source": "yfinance",
                "rate_limit_warning": "Yahoo has ~2000 req/hour limit. Use TradingView widget for production."
            }

        except Exception as yf_error:
            error_str = str(yf_error).lower()
            if '429' in error_str or 'too many' in error_str or 'rate limit' in error_str:
                print(f"🚨 YAHOO FINANCE RATE LIMIT HIT")
                print(f"   Limit: ~2000 requests/hour, ~48000/day")
                print(f"   Resets: Every hour on the hour")
                raise HTTPException(
                    status_code=429,
                    detail=f"Yahoo Finance rate limit exceeded (~2000 req/hour, resets hourly). Use TradingView widget to avoid this."
                )
            else:
                raise

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error fetching price history for {symbol}: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch price history: {str(e)}. Use TradingView widget for reliable charts."
        )

@app.get("/api/trader/strategies")
async def get_strategy_stats():
    """Get real strategy statistics from trade database"""
    if not trader_available:
        return {
            "success": False,
            "message": "Trader not configured",
            "data": []
        }

    try:
        import sqlite3
        import pandas as pd

        conn = sqlite3.connect(trader.db_path)

        # Get all positions grouped by strategy
        query = """
            SELECT
                strategy,
                COUNT(*) as total_trades,
                SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN status = 'CLOSED' THEN realized_pnl ELSE unrealized_pnl END) as total_pnl,
                MAX(entry_date) as last_trade_date
            FROM autonomous_positions
            GROUP BY strategy
        """

        strategies = pd.read_sql_query(query, conn)
        conn.close()

        strategy_list = []
        for _, row in strategies.iterrows():
            win_rate = (row['wins'] / row['total_trades'] * 100) if row['total_trades'] > 0 else 0
            strategy_list.append({
                "name": row['strategy'],
                "total_trades": int(row['total_trades']),
                "win_rate": float(win_rate),
                "total_pnl": float(row['total_pnl']) if row['total_pnl'] else 0,
                "last_trade_date": row['last_trade_date'],
                "status": "active"  # TODO: Determine from config or recent activity
            })

        return {
            "success": True,
            "data": strategy_list
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/strategies/compare")
async def compare_all_strategies(symbol: str = "SPY"):
    """
    Multi-Strategy Optimizer - Compare ALL strategies side-by-side
    Shows which strategy has the best win rate for current conditions
    Includes entry timing optimization
    """
    try:
        # Fetch current market data
        gex_data = api_client.get_net_gamma(symbol)

        # Debug logging - DETAILED
        print(f"\n{'='*60}")
        print(f"DEBUG: Strategy Optimizer - GEX Data Check")
        print(f"{'='*60}")
        print(f"Type of gex_data: {type(gex_data)}")
        print(f"gex_data keys: {gex_data.keys() if isinstance(gex_data, dict) else 'NOT A DICT'}")
        print(f"gex_data value (first 500 chars): {str(gex_data)[:500]}")
        print(f"{'='*60}\n")

        # Check if we got valid data
        if not gex_data:
            raise HTTPException(
                status_code=503,
                detail="No GEX data available. API might be rate-limited or unavailable."
            )

        if not isinstance(gex_data, dict):
            raise HTTPException(
                status_code=500,
                detail=f"Invalid GEX data type: {type(gex_data)}. Expected dict, got: {str(gex_data)[:200]}"
            )

        # Check for API error
        if 'error' in gex_data:
            error_msg = gex_data['error']
            if error_msg == 'rate_limit':
                raise HTTPException(
                    status_code=429,
                    detail="Trading Volatility API rate limit hit. Please wait a few minutes and try again."
                )
            else:
                raise HTTPException(
                    status_code=503,
                    detail=f"Trading Volatility API Error: {error_msg}"
                )

        # Validate required fields
        required_fields = ['spot_price', 'net_gex', 'flip_point', 'call_wall', 'put_wall']
        missing_fields = [field for field in required_fields if field not in gex_data]
        if missing_fields:
            print(f"⚠️  Missing fields in gex_data: {missing_fields}")
            print(f"Available keys: {list(gex_data.keys())}")

        # Get VIX data for additional context
        try:
            import yfinance as yf
            vix_ticker = yf.Ticker("^VIX")
            vix_data = vix_ticker.history(period="1d")
            vix = float(vix_data['Close'].iloc[-1]) if not vix_data.empty else 15.0
        except Exception as vix_error:
            print(f"Warning: Could not fetch VIX: {vix_error}")
            vix = 15.0  # Default fallback

        # Prepare market data for optimizer
        # Use the correct keys from get_net_gamma response
        market_data = {
            'spot_price': float(gex_data.get('spot_price', 0)),
            'net_gex': float(gex_data.get('net_gex', 0)),
            'flip_point': float(gex_data.get('flip_point', 0)),
            'call_wall': float(gex_data.get('call_wall', 0)),
            'put_wall': float(gex_data.get('put_wall', 0)),
            'call_wall_gamma': float(gex_data.get('call_wall', 0)),
            'put_wall_gamma': float(gex_data.get('put_wall', 0)),
            'vix': float(vix)
        }

        print(f"Market data prepared: {market_data}")

        # Get comprehensive strategy comparison
        try:
            comparison = strategy_optimizer.compare_all_strategies(market_data)
            print(f"✅ Strategy comparison completed successfully")
        except Exception as optimizer_error:
            print(f"❌ Error in strategy_optimizer.compare_all_strategies:")
            print(f"Error type: {type(optimizer_error)}")
            print(f"Error message: {str(optimizer_error)}")
            import traceback
            traceback.print_exc()
            raise HTTPException(
                status_code=500,
                detail=f"Strategy optimizer failed: {str(optimizer_error)}"
            )

        return {
            "success": True,
            "symbol": symbol,
            "data": comparison
        }
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"❌ Error in compare_all_strategies endpoint:")
        print(f"Error type: {type(e)}")
        print(f"Error message: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to compare strategies: {str(e)}")

# ============================================================================
# Multi-Symbol Scanner Endpoints (WITH DATABASE PERSISTENCE)
# ============================================================================

def init_scanner_database():
    """Initialize scanner database schema with tracking"""
    import sqlite3

    conn = sqlite3.connect('scanner_results.db')
    c = conn.cursor()

    # Scanner runs table
    c.execute('''
        CREATE TABLE IF NOT EXISTS scanner_runs (
            id TEXT PRIMARY KEY,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            symbols_scanned TEXT,
            total_symbols INTEGER,
            opportunities_found INTEGER,
            scan_duration_seconds REAL,
            user_notes TEXT
        )
    ''')

    # Scanner results table
    c.execute('''
        CREATE TABLE IF NOT EXISTS scanner_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scan_id TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            symbol TEXT NOT NULL,
            strategy TEXT NOT NULL,
            confidence REAL,
            net_gex REAL,
            spot_price REAL,
            flip_point REAL,
            call_wall REAL,
            put_wall REAL,
            entry_price REAL,
            target_price REAL,
            stop_price REAL,
            risk_reward REAL,
            expected_move TEXT,
            reasoning TEXT,
            FOREIGN KEY (scan_id) REFERENCES scanner_runs(id)
        )
    ''')

    conn.commit()
    conn.close()

# Initialize scanner database on startup
try:
    init_scanner_database()
except Exception as e:
    print(f"Scanner DB init warning: {e}")

@app.post("/api/scanner/scan")
async def scan_symbols(request: dict):
    """
    Scan multiple symbols for trading opportunities using ALL strategies

    Returns setups with SPECIFIC money-making instructions
    """
    import sqlite3
    import uuid
    import time

    try:
        symbols = request.get('symbols', ['SPY', 'QQQ', 'IWM', 'AAPL', 'TSLA', 'NVDA'])

        # Generate unique scan ID
        scan_id = str(uuid.uuid4())
        scan_start = time.time()

        results = []

        # Add per-symbol timeout to prevent Scanner from hanging
        TIMEOUT_PER_SYMBOL = 10  # seconds
        MAX_TOTAL_SCAN_TIME = 120  # 2 minutes total

        for symbol in symbols:
            # Check if total scan time exceeded
            if time.time() - scan_start > MAX_TOTAL_SCAN_TIME:
                print(f"⚠️ Scanner timeout: {len(results)} strategies found in {time.time() - scan_start:.1f}s")
                break

            try:
                symbol_start = time.time()

                # Get real GEX data with timeout protection
                gex_data = api_client.get_net_gamma(symbol)

                # Check if this symbol took too long
                symbol_elapsed = time.time() - symbol_start
                if symbol_elapsed > TIMEOUT_PER_SYMBOL:
                    print(f"⚠️ {symbol} took {symbol_elapsed:.1f}s (timeout: {TIMEOUT_PER_SYMBOL}s), skipping...")
                    continue

                if not gex_data or gex_data.get('error'):
                    print(f"⚠️ {symbol} returned error or no data, skipping...")
                    continue

                net_gex = gex_data.get('net_gex', 0)
                spot_price = gex_data.get('spot_price', 0)
                flip_point = gex_data.get('flip_point', 0)
                call_wall = gex_data.get('call_wall', 0)
                put_wall = gex_data.get('put_wall', 0)

                # Helper function to round strikes appropriately
                def round_strike(price, increment=1.0):
                    """Round to nearest strike increment (1, 2.5, 5, etc based on price)"""
                    if price < 20:
                        inc = 0.5
                    elif price < 100:
                        inc = 1.0
                    elif price < 200:
                        inc = 2.5
                    else:
                        inc = 5.0
                    return round(price / inc) * inc

                # Calculate metrics for strategy selection
                distance_to_flip = abs(spot_price - flip_point) / spot_price * 100 if spot_price else 0
                distance_to_call_wall = abs(call_wall - spot_price) / spot_price * 100 if spot_price else 0
                distance_to_put_wall = abs(put_wall - spot_price) / spot_price * 100 if spot_price else 0

                # Calculate spread width (percentage-based for consistency)
                spread_width_pct = 0.015  # 1.5% for most strategies
                if spot_price < 50:
                    spread_width_pct = 0.02  # 2% for cheaper stocks

                spread_width = spot_price * spread_width_pct

                # Storage for all potential setups
                symbol_setups = []

                # ===== CHECK ALL 12 STRATEGIES =====

                # 1. BULLISH CALL SPREAD
                if net_gex < 0 or (net_gex >= 0 and distance_to_flip < 3.0):
                    buy_strike = round_strike(max(spot_price, flip_point - spread_width/2))
                    sell_strike = round_strike(buy_strike + spread_width)
                    target_strike = round_strike(min(call_wall, sell_strike + spread_width))

                    confidence = 0.65
                    if net_gex < -1e9:
                        confidence += 0.10
                    if distance_to_flip < 1.5:
                        confidence += 0.05

                    symbol_setups.append({
                        'symbol': symbol,
                        'strategy': 'BULLISH_CALL_SPREAD',
                        'confidence': min(confidence, 0.85),
                        'net_gex': net_gex,
                        'spot_price': spot_price,
                        'flip_point': flip_point,
                        'call_wall': call_wall,
                        'put_wall': put_wall,
                        'entry_price': buy_strike,
                        'target_price': target_strike,
                        'stop_price': put_wall,
                        'risk_reward': 2.0,
                        'expected_move': '2-4% up',
                        'win_rate': 0.65,
                        'money_making_plan': f"""BUY {buy_strike:.0f} CALL / SELL {sell_strike:.0f} CALL

Target: ${target_strike:.0f} | Stop: ${put_wall:.0f}
Risk ${(sell_strike - buy_strike):.0f} to make ${(target_strike - buy_strike):.0f}
Best with 3-14 DTE""",
                        'reasoning': f"Bullish setup. GEX: ${net_gex/1e9:.1f}B. {distance_to_flip:.1f}% from flip."
                    })

                # 2. BEARISH PUT SPREAD
                if net_gex > 1e9 or spot_price < flip_point:
                    buy_strike = round_strike(min(spot_price, flip_point + spread_width/2))
                    sell_strike = round_strike(buy_strike - spread_width)
                    target_strike = round_strike(max(put_wall, sell_strike - spread_width))

                    confidence = 0.62
                    if net_gex > 2e9:
                        confidence += 0.08

                    symbol_setups.append({
                        'symbol': symbol,
                        'strategy': 'BEARISH_PUT_SPREAD',
                        'confidence': min(confidence, 0.80),
                        'net_gex': net_gex,
                        'spot_price': spot_price,
                        'flip_point': flip_point,
                        'call_wall': call_wall,
                        'put_wall': put_wall,
                        'entry_price': buy_strike,
                        'target_price': target_strike,
                        'stop_price': call_wall,
                        'risk_reward': 2.0,
                        'expected_move': '2-4% down',
                        'win_rate': 0.62,
                        'money_making_plan': f"""BUY {buy_strike:.0f} PUT / SELL {sell_strike:.0f} PUT

Target: ${target_strike:.0f} | Stop: ${call_wall:.0f}
Risk ${(buy_strike - sell_strike):.0f} to make ${(buy_strike - target_strike):.0f}
Best with 3-14 DTE""",
                        'reasoning': f"Bearish setup. GEX: ${net_gex/1e9:.1f}B. Below flip."
                    })

                # 3. BULL PUT SPREAD (Credit)
                if net_gex > 0.5e9 and distance_to_put_wall >= 2.0:
                    sell_strike = round_strike(put_wall)
                    buy_strike = round_strike(sell_strike - spread_width)

                    confidence = 0.70
                    if distance_to_put_wall > 3.0:
                        confidence += 0.05

                    symbol_setups.append({
                        'symbol': symbol,
                        'strategy': 'BULL_PUT_SPREAD',
                        'confidence': min(confidence, 0.80),
                        'net_gex': net_gex,
                        'spot_price': spot_price,
                        'flip_point': flip_point,
                        'call_wall': call_wall,
                        'put_wall': put_wall,
                        'entry_price': spot_price,
                        'target_price': sell_strike,
                        'stop_price': buy_strike,
                        'risk_reward': 0.4,
                        'expected_move': 'Flat to +2%',
                        'win_rate': 0.70,
                        'money_making_plan': f"""SELL {sell_strike:.0f} PUT / BUY {buy_strike:.0f} PUT

Credit spread at support. Collect premium, close at 50%
Best with 5-21 DTE | Target: 50% profit in 3-5 days""",
                        'reasoning': f"Credit spread. Put wall support at ${put_wall:.0f} ({distance_to_put_wall:.1f}% away)."
                    })

                # 4. BEAR CALL SPREAD (Credit)
                if net_gex > 0.5e9 and distance_to_call_wall >= 2.0:
                    sell_strike = round_strike(call_wall)
                    buy_strike = round_strike(sell_strike + spread_width)

                    confidence = 0.68
                    if distance_to_call_wall > 3.0:
                        confidence += 0.05

                    symbol_setups.append({
                        'symbol': symbol,
                        'strategy': 'BEAR_CALL_SPREAD',
                        'confidence': min(confidence, 0.78),
                        'net_gex': net_gex,
                        'spot_price': spot_price,
                        'flip_point': flip_point,
                        'call_wall': call_wall,
                        'put_wall': put_wall,
                        'entry_price': spot_price,
                        'target_price': sell_strike,
                        'stop_price': buy_strike,
                        'risk_reward': 0.4,
                        'expected_move': 'Flat to -2%',
                        'win_rate': 0.68,
                        'money_making_plan': f"""SELL {sell_strike:.0f} CALL / BUY {buy_strike:.0f} CALL

Credit spread at resistance. Collect premium, close at 50%
Best with 5-21 DTE | Target: 50% profit in 3-5 days""",
                        'reasoning': f"Credit spread. Call wall resistance at ${call_wall:.0f} ({distance_to_call_wall:.1f}% away)."
                    })

                # 5. IRON CONDOR
                if net_gex > 1e9 and distance_to_call_wall >= 2.0 and distance_to_put_wall >= 2.0:
                    call_short = round_strike(call_wall)
                    call_long = round_strike(call_short + spread_width)
                    put_short = round_strike(put_wall)
                    put_long = round_strike(put_short - spread_width)

                    confidence = 0.72
                    if distance_to_call_wall > 3.0 and distance_to_put_wall > 3.0:
                        confidence += 0.08

                    symbol_setups.append({
                        'symbol': symbol,
                        'strategy': 'IRON_CONDOR',
                        'confidence': min(confidence, 0.85),
                        'net_gex': net_gex,
                        'spot_price': spot_price,
                        'flip_point': flip_point,
                        'call_wall': call_wall,
                        'put_wall': put_wall,
                        'entry_price': spot_price,
                        'target_price': spot_price,
                        'stop_price': None,
                        'risk_reward': 0.3,
                        'expected_move': 'Range bound',
                        'win_rate': 0.72,
                        'money_making_plan': f"""SELL {call_short:.0f}/{call_long:.0f} CALL SPREAD + {put_short:.0f}/{put_long:.0f} PUT SPREAD

Range: ${put_wall:.0f} - ${call_wall:.0f}
Premium collection. Close at 50% profit or 2 DTE
Best with 5-10 DTE""",
                        'reasoning': f"Strong positive GEX (${net_gex/1e9:.1f}B) with wide walls. Perfect IC setup."
                    })

                # 6. NEGATIVE GEX SQUEEZE
                if net_gex < -1e9 and distance_to_flip < 2.0:
                    entry_strike = round_strike(flip_point + 0.5)

                    confidence = 0.75 if spot_price < flip_point else 0.85

                    symbol_setups.append({
                        'symbol': symbol,
                        'strategy': 'NEGATIVE_GEX_SQUEEZE',
                        'confidence': confidence,
                        'net_gex': net_gex,
                        'spot_price': spot_price,
                        'flip_point': flip_point,
                        'call_wall': call_wall,
                        'put_wall': put_wall,
                        'entry_price': entry_strike,
                        'target_price': call_wall,
                        'stop_price': put_wall,
                        'risk_reward': 3.0,
                        'expected_move': '2-3% up',
                        'win_rate': 0.68,
                        'money_making_plan': f"""BUY {entry_strike:.0f} CALL when price breaks ${flip_point:.0f}

Negative GEX squeeze play. MMs chase price UP.
Target: ${call_wall:.0f} | Stop: ${put_wall:.0f}
Best with 0-5 DTE""",
                        'reasoning': f"Negative GEX (${net_gex/1e9:.1f}B) creates upside squeeze. {distance_to_flip:.1f}% from flip."
                    })

                # 7. LONG STRADDLE (High volatility expected)
                if net_gex < -2e9:
                    atm_strike = round_strike(spot_price)

                    confidence = 0.55
                    if net_gex < -3e9:
                        confidence += 0.10

                    symbol_setups.append({
                        'symbol': symbol,
                        'strategy': 'LONG_STRADDLE',
                        'confidence': min(confidence, 0.70),
                        'net_gex': net_gex,
                        'spot_price': spot_price,
                        'flip_point': flip_point,
                        'call_wall': call_wall,
                        'put_wall': put_wall,
                        'entry_price': spot_price,
                        'target_price': None,
                        'stop_price': None,
                        'risk_reward': 3.0,
                        'expected_move': '5%+ either direction',
                        'win_rate': 0.55,
                        'money_making_plan': f"""BUY {atm_strike:.0f} CALL + BUY {atm_strike:.0f} PUT

Extreme negative GEX = big move coming
Exit at either wall: ${call_wall:.0f} or ${put_wall:.0f}
Best with 0-7 DTE, before major events""",
                        'reasoning': f"Extreme negative GEX (${net_gex/1e9:.1f}B). Expect large move."
                    })

                # ALWAYS INCLUDE: Fallback strategy if nothing else fits
                if len(symbol_setups) == 0:
                    # Default to a simple directional play based on GEX
                    if net_gex < 0:
                        # Bullish fallback
                        buy_strike = round_strike(spot_price)
                        sell_strike = round_strike(buy_strike + spread_width)

                        symbol_setups.append({
                            'symbol': symbol,
                            'strategy': 'BULLISH_CALL_SPREAD',
                            'confidence': 0.55,
                            'net_gex': net_gex,
                            'spot_price': spot_price,
                            'flip_point': flip_point,
                            'call_wall': call_wall,
                            'put_wall': put_wall,
                            'entry_price': buy_strike,
                            'target_price': call_wall,
                            'stop_price': put_wall,
                            'risk_reward': 2.0,
                            'expected_move': '1-3% up',
                            'win_rate': 0.55,
                            'money_making_plan': f"""BUY {buy_strike:.0f} CALL / SELL {sell_strike:.0f} CALL

Fallback bullish play. Target: ${call_wall:.0f}""",
                            'reasoning': f"Negative GEX suggests bullish bias."
                        })
                    else:
                        # Range-bound fallback
                        call_short = round_strike(call_wall)
                        call_long = round_strike(call_short + spread_width)
                        put_short = round_strike(put_wall)
                        put_long = round_strike(put_short - spread_width)

                        symbol_setups.append({
                            'symbol': symbol,
                            'strategy': 'IRON_CONDOR',
                            'confidence': 0.60,
                            'net_gex': net_gex,
                            'spot_price': spot_price,
                            'flip_point': flip_point,
                            'call_wall': call_wall,
                            'put_wall': put_wall,
                            'entry_price': spot_price,
                            'target_price': spot_price,
                            'stop_price': None,
                            'risk_reward': 0.3,
                            'expected_move': 'Range bound',
                            'win_rate': 0.60,
                            'money_making_plan': f"""SELL {call_short:.0f}/{call_long:.0f} CALL SPREAD + {put_short:.0f}/{put_long:.0f} PUT SPREAD

Fallback range play. Positive GEX suggests range-bound action.""",
                            'reasoning': f"Positive GEX (${net_gex/1e9:.1f}B) suggests range trading."
                        })

                # Add ALL strategies above confidence threshold (65%)
                MIN_CONFIDENCE = 0.65

                if symbol_setups:
                    # Filter for strategies meeting minimum confidence
                    viable_setups = [s for s in symbol_setups if s['confidence'] >= MIN_CONFIDENCE]

                    if viable_setups:
                        # Return ALL viable strategies (not just the best one)
                        results.extend(viable_setups)
                    else:
                        # If nothing meets threshold, return the best strategy anyway
                        best_setup = max(symbol_setups, key=lambda x: x['confidence'])
                        results.append(best_setup)

            except Exception as e:
                print(f"❌ Error scanning {symbol}: {e}")
                # Continue with next symbol - don't let one failure stop the whole scan
                continue

        # Save scan to database
        scan_duration = time.time() - scan_start

        # Log scan completion
        print(f"✅ Scanner completed: {len(results)} strategies found across {len(symbols)} symbols in {scan_duration:.1f}s")

        conn = sqlite3.connect('scanner_results.db')
        c = conn.cursor()

        c.execute("""
            INSERT INTO scanner_runs (id, symbols_scanned, total_symbols, opportunities_found, scan_duration_seconds)
            VALUES (?, ?, ?, ?, ?)
        """, (scan_id, ','.join(symbols), len(symbols), len(results), scan_duration))

        # Save each result
        for result in results:
            c.execute("""
                INSERT INTO scanner_results (
                    scan_id, symbol, strategy, confidence, net_gex, spot_price,
                    flip_point, call_wall, put_wall, entry_price, target_price,
                    stop_price, risk_reward, expected_move, reasoning
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                scan_id, result['symbol'], result['strategy'], result['confidence'],
                result['net_gex'], result['spot_price'], result['flip_point'],
                result['call_wall'], result['put_wall'], result['entry_price'],
                result['target_price'], result.get('stop_price'), result['risk_reward'],
                result['expected_move'], result['reasoning']
            ))

        conn.commit()
        conn.close()

        return {
            "success": True,
            "scan_id": scan_id,
            "timestamp": datetime.now().isoformat(),
            "total_symbols": len(symbols),
            "opportunities_found": len(results),
            "scan_duration_seconds": scan_duration,
            "results": results
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/scanner/history")
async def get_scanner_history(limit: int = 10):
    """Get scanner run history"""
    try:
        import sqlite3
        import pandas as pd

        conn = sqlite3.connect('scanner_results.db')

        runs = pd.read_sql_query(f"""
            SELECT * FROM scanner_runs
            ORDER BY timestamp DESC
            LIMIT {limit}
        """, conn)

        conn.close()

        return {
            "success": True,
            "data": runs.to_dict('records') if not runs.empty else []
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/scanner/results/{scan_id}")
async def get_scan_results(scan_id: str):
    """Get results for a specific scan"""
    try:
        import sqlite3
        import pandas as pd

        conn = sqlite3.connect('scanner_results.db')

        results = pd.read_sql_query(f"""
            SELECT * FROM scanner_results
            WHERE scan_id = '{scan_id}'
            ORDER BY confidence DESC
        """, conn)

        conn.close()

        return {
            "success": True,
            "scan_id": scan_id,
            "data": results.to_dict('records') if not results.empty else []
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# Trade Setups - AI-Generated Trade Recommendations
# ============================================================================

def init_trade_setups_database():
    """Initialize trade setups database schema"""
    import sqlite3

    conn = sqlite3.connect('trade_setups.db')
    c = conn.cursor()

    # Trade setups table
    c.execute('''
        CREATE TABLE IF NOT EXISTS trade_setups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            symbol TEXT NOT NULL,
            setup_type TEXT NOT NULL,
            confidence REAL,
            entry_price REAL,
            target_price REAL,
            stop_price REAL,
            risk_reward REAL,
            position_size INTEGER,
            max_risk_dollars REAL,
            time_horizon TEXT,
            catalyst TEXT,
            ai_reasoning TEXT,
            money_making_plan TEXT,
            status TEXT DEFAULT 'active',
            actual_entry REAL,
            actual_exit REAL,
            actual_pnl REAL,
            notes TEXT
        )
    ''')

    conn.commit()
    conn.close()

# Initialize trade setups database on startup
init_trade_setups_database()

@app.post("/api/setups/generate")
async def generate_trade_setups(request: dict):
    """
    Generate AI-powered trade setups based on current market conditions
    Request body:
    {
        "symbols": ["SPY", "QQQ"],  // Optional, defaults to SPY
        "account_size": 50000,       // Optional
        "risk_pct": 2.0             // Optional
    }
    """
    try:
        symbols = request.get('symbols', ['SPY'])
        account_size = request.get('account_size', 50000)
        risk_pct = request.get('risk_pct', 2.0)

        max_risk = account_size * (risk_pct / 100)

        setups = []

        # Import necessary components
        from intelligence_and_strategies import RealOptionsChainFetcher
        options_fetcher = RealOptionsChainFetcher()

        for symbol in symbols:
            # Fetch current GEX data
            gex_data = api_client.get_net_gamma(symbol)
            net_gex = gex_data.get('net_gex', 0)
            spot_price = gex_data.get('spot_price', 0)
            flip_point = gex_data.get('flip_point', 0)
            call_wall = gex_data.get('call_wall', 0)
            put_wall = gex_data.get('put_wall', 0)

            # Get current regime analysis
            regime_info = None
            try:
                from psychology_trap_detector import analyze_current_market_complete
                import yfinance as yf

                # Get price data for regime analysis
                ticker = yf.Ticker(symbol)
                gex_full_data = api_client.get_net_gamma(symbol)

                # Get historical price data for RSI
                price_data = {}
                df_1d = ticker.history(period="90d", interval="1d")
                price_data['1d'] = [{'close': row['Close'], 'high': row['High'], 'low': row['Low'], 'volume': row['Volume']} for _, row in df_1d.iterrows()]

                df_4h = ticker.history(period="30d", interval="1h")
                df_4h_resampled = df_4h.resample('4H').agg({'Close': 'last', 'High': 'max', 'Low': 'min', 'Volume': 'sum'}).dropna()
                price_data['4h'] = [{'close': row['Close'], 'high': row['High'], 'low': row['Low'], 'volume': row['Volume']} for _, row in df_4h_resampled.iterrows()]

                df_1h = ticker.history(period="7d", interval="1h")
                price_data['1h'] = [{'close': row['Close'], 'high': row['High'], 'low': row['Low'], 'volume': row['Volume']} for _, row in df_1h.iterrows()]

                df_15m = ticker.history(period="5d", interval="15m")
                price_data['15m'] = [{'close': row['Close'], 'high': row['High'], 'low': row['Low'], 'volume': row['Volume']} for _, row in df_15m.iterrows()]

                df_5m = ticker.history(period="2d", interval="5m")
                price_data['5m'] = [{'close': row['Close'], 'high': row['High'], 'low': row['Low'], 'volume': row['Volume']} for _, row in df_5m.iterrows()]

                # Calculate volume ratio
                current_price = gex_full_data.get('spot_price', spot_price)
                if len(price_data.get('1d', [])) >= 20:
                    recent_volume = price_data['1d'][-1]['volume']
                    avg_volume = sum(d['volume'] for d in price_data['1d'][-20:]) / 20
                    volume_ratio = recent_volume / avg_volume if avg_volume > 0 else 1.0
                else:
                    volume_ratio = 1.0

                # Format gamma data for analyzer
                gamma_data_formatted = {
                    'net_gamma': gex_full_data.get('net_gex', 0),
                    'expirations': [{
                        'expiration_date': datetime.now() + timedelta(days=7),
                        'dte': 7,
                        'expiration_type': 'weekly',
                        'call_strikes': [{
                            'strike': gex_full_data.get('call_wall', current_price * 1.02),
                            'gamma_exposure': gex_full_data.get('net_gex', 0) / 2,
                            'open_interest': 1000
                        }],
                        'put_strikes': [{
                            'strike': gex_full_data.get('put_wall', current_price * 0.98),
                            'gamma_exposure': gex_full_data.get('net_gex', 0) / 2,
                            'open_interest': 1000
                        }]
                    }]
                }

                # Analyze regime with CORRECT signature
                analysis = analyze_current_market_complete(
                    current_price=current_price,
                    price_data=price_data,
                    gamma_data=gamma_data_formatted,
                    volume_ratio=volume_ratio
                )
                if analysis and 'regime' in analysis:
                    regime_info = analysis['regime']
            except Exception as e:
                print(f"Regime analysis failed: {e}")
                import traceback
                traceback.print_exc()
                regime_info = None

            # Determine market regime and setup type using STRATEGIES config
            from config_and_database import STRATEGIES

            matched_strategy = None
            strategy_config = None

            # NEGATIVE_GEX_SQUEEZE - Highest probability directional setup (68% win rate)
            if net_gex < STRATEGIES['NEGATIVE_GEX_SQUEEZE']['conditions']['net_gex_threshold']:
                if spot_price < flip_point:
                    matched_strategy = 'NEGATIVE_GEX_SQUEEZE'
                    strategy_config = STRATEGIES['NEGATIVE_GEX_SQUEEZE']
                    setup_type = matched_strategy
                    entry_price = spot_price
                    target_price = call_wall if call_wall else spot_price * 1.03
                    stop_price = put_wall if put_wall else spot_price * 0.98
                    catalyst = f"Negative GEX regime (${net_gex/1e9:.1f}B) with price below flip point creates MM buy pressure - {strategy_config['typical_move']} expected"

            # POSITIVE_GEX_BREAKDOWN - When breaking from compression
            if matched_strategy is None and net_gex > STRATEGIES['POSITIVE_GEX_BREAKDOWN']['conditions']['net_gex_threshold']:
                distance_to_flip_pct = abs(spot_price - flip_point) / flip_point * 100 if flip_point else 100
                if distance_to_flip_pct < STRATEGIES['POSITIVE_GEX_BREAKDOWN']['conditions']['proximity_to_flip']:
                    matched_strategy = 'POSITIVE_GEX_BREAKDOWN'
                    strategy_config = STRATEGIES['POSITIVE_GEX_BREAKDOWN']
                    setup_type = matched_strategy
                    entry_price = spot_price
                    target_price = put_wall if put_wall else spot_price * 0.98
                    stop_price = call_wall if call_wall else spot_price * 1.02
                    catalyst = f"Positive GEX breakdown near flip point - {strategy_config['typical_move']} expected as compression releases"

            # IRON_CONDOR - BEST WIN RATE (72%) in stable positive GEX
            if matched_strategy is None and net_gex > STRATEGIES['IRON_CONDOR']['conditions']['net_gex_threshold']:
                matched_strategy = 'IRON_CONDOR'
                strategy_config = STRATEGIES['IRON_CONDOR']
                setup_type = matched_strategy
                entry_price = spot_price
                target_price = spot_price * 1.01  # Small premium collection
                stop_price = call_wall if call_wall else spot_price * 1.03
                catalyst = f"Positive GEX regime (${net_gex/1e9:.1f}B) creates range-bound environment - HIGHEST WIN RATE SETUP (72%)"

            # PREMIUM_SELLING - Fallback strategy
            if matched_strategy is None:
                matched_strategy = 'PREMIUM_SELLING'
                strategy_config = STRATEGIES['PREMIUM_SELLING']
                setup_type = matched_strategy
                entry_price = spot_price
                target_price = spot_price * 1.01
                stop_price = flip_point if flip_point else spot_price * 0.98
                catalyst = f"Neutral GEX allows for premium collection - {strategy_config['typical_move']} expected"

            # Use actual win_rate and risk_reward from STRATEGIES config
            confidence = strategy_config['win_rate']  # ✅ Evidence-based win rate
            expected_risk_reward = strategy_config['risk_reward']  # ✅ From research

            # Calculate actual risk/reward for this specific trade
            if target_price and stop_price and entry_price:
                reward = abs(target_price - entry_price)
                risk = abs(entry_price - stop_price)
                risk_reward = reward / risk if risk > 0 else expected_risk_reward
            else:
                risk_reward = expected_risk_reward

            # Get real option chain and select optimal strike
            option_details = None
            strike_price = None
            option_cost = None
            option_greeks = {}

            try:
                # Determine option type based on strategy
                option_type = 'call' if matched_strategy in ['NEGATIVE_GEX_SQUEEZE'] else 'put' if matched_strategy in ['POSITIVE_GEX_BREAKDOWN'] else 'call'

                # Get options chain
                chain = options_fetcher.get_options_chain(symbol)

                if chain and 'calls' in chain and 'puts' in chain:
                    options = chain['calls'] if option_type == 'call' else chain['puts']

                    # Find ATM or slightly OTM strike
                    best_option = None
                    min_diff = float('inf')

                    for opt in options:
                        strike = opt.get('strike', 0)
                        bid = opt.get('bid', 0)
                        ask = opt.get('ask', 0)

                        # Skip if no liquidity
                        if bid == 0 or ask == 0:
                            continue

                        # Find closest to ATM (or slightly OTM for better delta)
                        if option_type == 'call':
                            ideal_strike = spot_price + (spot_price * 0.005)  # 0.5% OTM
                        else:
                            ideal_strike = spot_price - (spot_price * 0.005)

                        diff = abs(strike - ideal_strike)

                        if diff < min_diff:
                            min_diff = diff
                            best_option = opt
                            strike_price = strike
                            option_cost = (bid + ask) / 2  # Use mid price

                    if best_option:
                        option_details = best_option

                        # Extract Greeks if available
                        option_greeks = {
                            'delta': best_option.get('delta', 0),
                            'gamma': best_option.get('gamma', 0),
                            'theta': best_option.get('theta', 0),
                            'vega': best_option.get('vega', 0),
                            'iv': best_option.get('impliedVolatility', 0)
                        }

            except Exception as e:
                print(f"Failed to fetch option chain: {e}")
                # Fall back to estimate
                option_cost = spot_price * 0.02
                strike_price = entry_price

            # Calculate position size based on actual option cost
            if option_cost and option_cost > 0:
                contracts_per_risk = int(max_risk / (option_cost * 100))
                position_size = max(1, min(contracts_per_risk, 10))  # Cap at 10 contracts
                actual_cost = option_cost * 100 * position_size
                potential_profit = max_risk * risk_reward
            else:
                # Fall back to estimate
                option_cost = spot_price * 0.02
                contracts_per_risk = int(max_risk / (option_cost * 100)) if option_cost > 0 else 1
                position_size = max(1, min(contracts_per_risk, 10))
                actual_cost = option_cost * 100 * position_size
                potential_profit = max_risk * risk_reward

            # Determine hold period based on regime and strategy
            hold_period = "1-3 days"
            if regime_info:
                timeline = regime_info.get('timeline', '')
                if timeline and 'hour' in timeline.lower():
                    hold_period = "0-1 days"
                elif timeline and 'day' in timeline.lower():
                    hold_period = "1-3 days"

            # Get regime description for the plan
            regime_description = ""
            if regime_info:
                regime_type = regime_info.get('primary_type', '')
                regime_confidence = int(regime_info.get('confidence', 0))
                regime_description = f"\n🎯 {regime_type.upper().replace('_', ' ')} ({regime_confidence}% confidence)\n"

            # Generate specific money-making instructions using market context
            strike_display = f"${strike_price:.0f}" if strike_price else f"${entry_price:.2f}"
            option_symbol = f"{symbol} {strike_display} {'C' if option_type == 'call' else 'P'}"

            money_making_plan = f"""
{regime_description}
🎯 AI-GENERATED TRADE SETUP - {setup_type}

1. **THE EXACT TRADE** (Copy This):
   - BUY {option_symbol} (expires in 0-3 DTE)
   - Cost: ${actual_cost:.0f} ({position_size} contracts @ ${option_cost:.2f} each)
   - Target: ${potential_profit:.0f} (+{(potential_profit/actual_cost*100):.0f}%)
   - Win Rate: {confidence*100:.0f}%
   - Hold: {hold_period}

2. **MARKET CONTEXT** (Why Now):
   - {symbol} at ${spot_price:.2f}
   - Net GEX: ${net_gex/1e9:.1f}B ({  'NEGATIVE - MMs forced to hedge' if net_gex < 0 else 'POSITIVE - MMs stabilizing'})
   - Flip Point: ${flip_point:.2f} ({'ABOVE' if spot_price > flip_point else 'BELOW'} current price)
   - Call Wall: ${call_wall:.2f} | Put Wall: ${put_wall:.2f}

3. **WHY THIS WORKS**:
   - {catalyst}
   - {regime_info.get('description', 'Market regime favorable for this setup') if regime_info else 'Market conditions favor this setup'}

4. **ENTRY CRITERIA** (When to Buy):
   - IMMEDIATE: Market is in optimal regime NOW
   - Confirmation: Price action respecting ${flip_point:.2f} flip point
   - Best execution: First 30 min after market open
   - Strike: {option_symbol}

4. **EXIT STRATEGY** (How to Take Profits):
   - Target 1: ${(entry_price + (target_price-entry_price)*0.5):.2f} - Take 50% off here
   - Target 2: ${target_price:.2f} - Take final 50% off
   - STOP LOSS: ${stop_price:.2f} - NO EXCEPTIONS, cut losses fast
   - Time Stop: Exit EOD if no movement (avoid overnight risk)
   - Expected R:R: {risk_reward:.1f}:1

5. **WHY THIS WORKS** (The Edge):
   - {catalyst}
   - Historical Win Rate: {confidence*100:.0f}% in this regime
   - MM Hedging Flow: {'Buying pressure above flip' if net_gex < 0 and spot_price < flip_point else 'Selling pressure' if net_gex < 0 else 'Range compression'}
   - Key Level: {'Break above flip triggers squeeze' if net_gex < 0 and spot_price < flip_point else 'Walls contain movement' if net_gex > 0 else 'Premium decay favorable'}

⏰ TIMING: Execute this setup within the next 2 hours for optimal edge.
💰 PROFIT POTENTIAL: ${max_risk * risk_reward:.2f} on ${max_risk:.2f} risk ({risk_reward:.1f}:1)
"""

            setup = {
                'symbol': symbol,
                'setup_type': setup_type,
                'confidence': confidence,
                'win_rate': confidence,  # ✅ Include win_rate from STRATEGIES (same as confidence)
                'expected_risk_reward': expected_risk_reward,  # ✅ From STRATEGIES config
                'entry_price': entry_price,
                'target_price': target_price,
                'stop_price': stop_price,
                'risk_reward': risk_reward,
                'position_size': position_size,
                'max_risk_dollars': max_risk,
                'time_horizon': '0-3 DTE',
                'best_days': strategy_config['best_days'],  # ✅ From STRATEGIES
                'entry_rule': strategy_config['entry'],  # ✅ From STRATEGIES
                'exit_rule': strategy_config['exit'],  # ✅ From STRATEGIES
                'catalyst': catalyst,
                'money_making_plan': money_making_plan,
                'market_data': {
                    'net_gex': net_gex,
                    'spot_price': spot_price,
                    'flip_point': flip_point,
                    'call_wall': call_wall,
                    'put_wall': put_wall
                },
                # ✅ NEW: Regime information
                'regime': regime_info if regime_info else {
                    'primary_type': 'NEUTRAL',
                    'confidence': 50,
                    'description': 'Standard market conditions',
                    'trade_direction': 'DIRECTIONAL',
                    'risk_level': 'MEDIUM'
                },
                # ✅ NEW: Specific option details
                'option_details': {
                    'option_type': option_type,
                    'strike_price': strike_price if strike_price else entry_price,
                    'option_symbol': option_symbol,
                    'option_cost': option_cost,
                    'bid': option_details.get('bid', 0) if option_details else 0,
                    'ask': option_details.get('ask', 0) if option_details else 0,
                    'volume': option_details.get('volume', 0) if option_details else 0,
                    'open_interest': option_details.get('openInterest', 0) if option_details else 0
                },
                # ✅ NEW: Greeks
                'greeks': option_greeks,
                # ✅ NEW: Cost and profit calculations
                'actual_cost': actual_cost,
                'potential_profit': potential_profit,
                'hold_period': hold_period,
                'generated_at': datetime.now().isoformat()
            }

            setups.append(setup)

        # Filter to only show setups with >50% win rate (evidence-based threshold)
        filtered_setups = [s for s in setups if s['win_rate'] >= 0.50]

        # Sort by win_rate (highest first) - Iron Condor (72%) should be highlighted
        sorted_setups = sorted(filtered_setups, key=lambda x: x['win_rate'], reverse=True)

        return {
            "success": True,
            "setups": sorted_setups,  # ✅ Sorted by win rate, filtered to >50%
            "total_setups_found": len(setups),
            "high_probability_setups": len(sorted_setups),  # Count of >50% setups
            "account_size": account_size,
            "risk_pct": risk_pct,
            "max_risk_per_trade": max_risk,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/setups/save")
async def save_trade_setup(request: dict):
    """
    Save a trade setup to database for tracking
    Request body: trade setup object
    """
    try:
        import sqlite3

        conn = sqlite3.connect('trade_setups.db')
        c = conn.cursor()

        c.execute('''
            INSERT INTO trade_setups (
                symbol, setup_type, confidence, entry_price, target_price,
                stop_price, risk_reward, position_size, max_risk_dollars,
                time_horizon, catalyst, money_making_plan
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            request['symbol'],
            request['setup_type'],
            request['confidence'],
            request['entry_price'],
            request['target_price'],
            request['stop_price'],
            request['risk_reward'],
            request['position_size'],
            request['max_risk_dollars'],
            request['time_horizon'],
            request['catalyst'],
            request['money_making_plan']
        ))

        setup_id = c.lastrowid
        conn.commit()
        conn.close()

        return {
            "success": True,
            "setup_id": setup_id,
            "message": "Trade setup saved successfully"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/setups/list")
async def list_trade_setups(limit: int = 20, status: str = 'active'):
    """Get saved trade setups"""
    try:
        import sqlite3
        import pandas as pd

        conn = sqlite3.connect('trade_setups.db')

        setups = pd.read_sql_query(f"""
            SELECT * FROM trade_setups
            WHERE status = '{status}'
            ORDER BY timestamp DESC
            LIMIT {limit}
        """, conn)

        conn.close()

        return {
            "success": True,
            "data": setups.to_dict('records') if not setups.empty else []
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/setups/{setup_id}")
async def update_trade_setup(setup_id: int, request: dict):
    """
    Update a trade setup (e.g., mark as executed, add actual results)
    Request body can include: status, actual_entry, actual_exit, actual_pnl, notes
    """
    try:
        import sqlite3

        conn = sqlite3.connect('trade_setups.db')
        c = conn.cursor()

        update_fields = []
        values = []

        if 'status' in request:
            update_fields.append('status = ?')
            values.append(request['status'])
        if 'actual_entry' in request:
            update_fields.append('actual_entry = ?')
            values.append(request['actual_entry'])
        if 'actual_exit' in request:
            update_fields.append('actual_exit = ?')
            values.append(request['actual_exit'])
        if 'actual_pnl' in request:
            update_fields.append('actual_pnl = ?')
            values.append(request['actual_pnl'])
        if 'notes' in request:
            update_fields.append('notes = ?')
            values.append(request['notes'])

        if not update_fields:
            raise HTTPException(status_code=400, detail="No fields to update")

        values.append(setup_id)

        c.execute(f"""
            UPDATE trade_setups
            SET {', '.join(update_fields)}
            WHERE id = ?
        """, values)

        conn.commit()
        conn.close()

        return {
            "success": True,
            "message": "Trade setup updated successfully"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# Alerts System - Price & GEX Threshold Notifications
# ============================================================================

def init_alerts_database():
    """Initialize alerts database schema"""
    import sqlite3

    conn = sqlite3.connect('alerts.db')
    c = conn.cursor()

    # Alerts table
    c.execute('''
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            symbol TEXT NOT NULL,
            alert_type TEXT NOT NULL,
            condition TEXT NOT NULL,
            threshold REAL NOT NULL,
            message TEXT,
            status TEXT DEFAULT 'active',
            triggered_at DATETIME,
            triggered_value REAL,
            notes TEXT
        )
    ''')

    # Alert history table (for triggered alerts)
    c.execute('''
        CREATE TABLE IF NOT EXISTS alert_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            alert_id INTEGER NOT NULL,
            triggered_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            symbol TEXT NOT NULL,
            alert_type TEXT NOT NULL,
            condition TEXT NOT NULL,
            threshold REAL NOT NULL,
            actual_value REAL NOT NULL,
            message TEXT,
            FOREIGN KEY (alert_id) REFERENCES alerts(id)
        )
    ''')

    conn.commit()
    conn.close()

# Initialize alerts database on startup
init_alerts_database()

@app.post("/api/alerts/create")
async def create_alert(request: dict):
    """
    Create a new alert
    Request body:
    {
        "symbol": "SPY",
        "alert_type": "price" | "net_gex" | "flip_point",
        "condition": "above" | "below" | "crosses_above" | "crosses_below",
        "threshold": 600.0,
        "message": "Optional custom message"
    }
    """
    try:
        import sqlite3

        symbol = request.get('symbol', 'SPY').upper()
        alert_type = request.get('alert_type')
        condition = request.get('condition')
        threshold = request.get('threshold')
        message = request.get('message', '')

        if not all([alert_type, condition, threshold]):
            raise HTTPException(status_code=400, detail="Missing required fields")

        # Generate default message if not provided
        if not message:
            if alert_type == 'price':
                message = f"{symbol} price {condition} ${threshold}"
            elif alert_type == 'net_gex':
                message = f"{symbol} Net GEX {condition} ${threshold/1e9:.1f}B"
            elif alert_type == 'flip_point':
                message = f"{symbol} {condition} flip point at ${threshold}"

        conn = sqlite3.connect('alerts.db')
        c = conn.cursor()

        c.execute('''
            INSERT INTO alerts (symbol, alert_type, condition, threshold, message)
            VALUES (?, ?, ?, ?, ?)
        ''', (symbol, alert_type, condition, threshold, message))

        alert_id = c.lastrowid
        conn.commit()
        conn.close()

        return {
            "success": True,
            "alert_id": alert_id,
            "message": "Alert created successfully"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/alerts/list")
async def list_alerts(status: str = 'active'):
    """Get all alerts with specified status"""
    try:
        import sqlite3
        import pandas as pd

        conn = sqlite3.connect('alerts.db')

        alerts = pd.read_sql_query(f"""
            SELECT * FROM alerts
            WHERE status = '{status}'
            ORDER BY created_at DESC
        """, conn)

        conn.close()

        return {
            "success": True,
            "data": alerts.to_dict('records') if not alerts.empty else []
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/alerts/{alert_id}")
async def delete_alert(alert_id: int):
    """Delete an alert"""
    try:
        import sqlite3

        conn = sqlite3.connect('alerts.db')
        c = conn.cursor()

        c.execute('DELETE FROM alerts WHERE id = ?', (alert_id,))

        conn.commit()
        conn.close()

        return {
            "success": True,
            "message": "Alert deleted successfully"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/alerts/check")
async def check_alerts():
    """
    Check all active alerts against current market data
    This endpoint should be called periodically (e.g., every minute)
    """
    try:
        import sqlite3
        import pandas as pd

        conn = sqlite3.connect('alerts.db')

        # Get all active alerts
        alerts = pd.read_sql_query("""
            SELECT * FROM alerts
            WHERE status = 'active'
        """, conn)

        triggered_alerts = []

        for _, alert in alerts.iterrows():
            symbol = alert['symbol']
            alert_type = alert['alert_type']
            condition = alert['condition']
            threshold = alert['threshold']

            # Fetch current market data
            gex_data = api_client.get_net_gamma(symbol)
            spot_price = gex_data.get('spot_price', 0)
            net_gex = gex_data.get('net_gex', 0)
            flip_point = gex_data.get('flip_point', 0)

            triggered = False
            actual_value = 0

            # Check conditions
            if alert_type == 'price':
                actual_value = spot_price
                if condition == 'above' and spot_price > threshold:
                    triggered = True
                elif condition == 'below' and spot_price < threshold:
                    triggered = True

            elif alert_type == 'net_gex':
                actual_value = net_gex
                if condition == 'above' and net_gex > threshold:
                    triggered = True
                elif condition == 'below' and net_gex < threshold:
                    triggered = True

            elif alert_type == 'flip_point':
                actual_value = spot_price
                if condition == 'crosses_above' and spot_price > flip_point:
                    triggered = True
                elif condition == 'crosses_below' and spot_price < flip_point:
                    triggered = True

            if triggered:
                # Mark alert as triggered
                c = conn.cursor()
                c.execute('''
                    UPDATE alerts
                    SET status = 'triggered', triggered_at = CURRENT_TIMESTAMP, triggered_value = ?
                    WHERE id = ?
                ''', (actual_value, alert['id']))

                # Add to alert history
                c.execute('''
                    INSERT INTO alert_history (
                        alert_id, symbol, alert_type, condition, threshold,
                        actual_value, message
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    alert['id'], symbol, alert_type, condition,
                    threshold, actual_value, alert['message']
                ))

                conn.commit()

                triggered_alerts.append({
                    'id': alert['id'],
                    'symbol': symbol,
                    'message': alert['message'],
                    'actual_value': actual_value,
                    'threshold': threshold
                })

        conn.close()

        return {
            "success": True,
            "checked": len(alerts),
            "triggered": len(triggered_alerts),
            "alerts": triggered_alerts
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/alerts/history")
async def get_alert_history(limit: int = 50):
    """Get alert trigger history"""
    try:
        import sqlite3
        import pandas as pd

        conn = sqlite3.connect('alerts.db')

        history = pd.read_sql_query(f"""
            SELECT * FROM alert_history
            ORDER BY triggered_at DESC
            LIMIT {limit}
        """, conn)

        conn.close()

        return {
            "success": True,
            "data": history.to_dict('records') if not history.empty else []
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# Position Sizing Calculator - Kelly Criterion
# ============================================================================

@app.post("/api/position-sizing/calculate")
async def calculate_position_size(request: dict):
    """
    Calculate optimal position size using Kelly Criterion
    Request body:
    {
        "account_size": 50000,
        "win_rate": 0.65,         // 65%
        "avg_win": 300,           // Average win in $
        "avg_loss": 150,          // Average loss in $
        "current_price": 580,     // Stock/option price
        "risk_per_trade_pct": 2.0 // Max risk as % of account
    }
    """
    try:
        account_size = request.get('account_size', 50000)
        win_rate = request.get('win_rate', 0.65)
        avg_win = request.get('avg_win', 300)
        avg_loss = request.get('avg_loss', 150)
        current_price = request.get('current_price', 100)
        risk_per_trade_pct = request.get('risk_per_trade_pct', 2.0)

        # Validate inputs
        if not (0 < win_rate < 1):
            raise HTTPException(status_code=400, detail="Win rate must be between 0 and 1")

        # Calculate Kelly Criterion
        # Kelly % = W - [(1 - W) / R]
        # Where: W = win rate, R = avg win / avg loss (reward-to-risk ratio)
        reward_to_risk = avg_win / avg_loss if avg_loss > 0 else 1
        kelly_pct = win_rate - ((1 - win_rate) / reward_to_risk)

        # Kelly can be negative (don't take the bet) or > 100% (very aggressive)
        # We cap it at reasonable levels
        kelly_pct_capped = max(0, min(kelly_pct, 0.25))  # Cap at 25% of account

        # Calculate position sizes
        max_risk_dollars = account_size * (risk_per_trade_pct / 100)
        kelly_position_dollars = account_size * kelly_pct_capped
        kelly_contracts = int(kelly_position_dollars / (current_price * 100)) if current_price > 0 else 0

        # Conservative position (half Kelly)
        half_kelly_pct = kelly_pct_capped / 2
        half_kelly_position_dollars = account_size * half_kelly_pct
        half_kelly_contracts = int(half_kelly_position_dollars / (current_price * 100)) if current_price > 0 else 0

        # Fixed risk position
        fixed_risk_contracts = int(max_risk_dollars / (current_price * 100)) if current_price > 0 else 0

        # Calculate expected value
        expected_value = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)
        expected_value_pct = (expected_value / avg_loss * 100) if avg_loss > 0 else 0

        # Generate money-making guide
        recommendation = "FULL KELLY" if kelly_pct_capped > 0.15 else "HALF KELLY" if kelly_pct_capped > 0.08 else "FIXED RISK"

        money_making_guide = f"""
💰 POSITION SIZING GUIDE - HOW TO SIZE YOUR TRADES

═══════════════════════════════════════════════════════════════

📊 YOUR STATS:
   - Account Size: ${account_size:,.2f}
   - Win Rate: {win_rate*100:.1f}%
   - Average Win: ${avg_win:.2f}
   - Average Loss: ${avg_loss:.2f}
   - Reward:Risk Ratio: {reward_to_risk:.2f}:1
   - Expected Value per Trade: ${expected_value:.2f} ({expected_value_pct:+.1f}%)

═══════════════════════════════════════════════════════════════

🎯 KELLY CRITERION ANALYSIS:

   Raw Kelly %: {kelly_pct*100:.1f}% of account
   {'⚠️ This is AGGRESSIVE - we cap at 25%' if kelly_pct > 0.25 else '✅ Within reasonable limits'}

   RECOMMENDATION: {recommendation}

═══════════════════════════════════════════════════════════════

💡 THREE POSITION SIZING STRATEGIES:

1. 🔥 FULL KELLY (Aggressive - Max Growth)
   ├─ Position Size: ${kelly_position_dollars:,.2f} ({kelly_pct_capped*100:.1f}% of account)
   ├─ Contracts: {kelly_contracts} contracts
   ├─ Risk per Trade: ${kelly_position_dollars:,.2f}
   └─ Use When: High confidence, proven edge, good win rate >65%

2. ✅ HALF KELLY (Recommended - Balanced)
   ├─ Position Size: ${half_kelly_position_dollars:,.2f} ({half_kelly_pct*100:.1f}% of account)
   ├─ Contracts: {half_kelly_contracts} contracts
   ├─ Risk per Trade: ${half_kelly_position_dollars:,.2f}
   └─ Use When: Standard setups, normal market conditions

3. 🛡️ FIXED RISK (Conservative - Capital Preservation)
   ├─ Position Size: ${max_risk_dollars:,.2f} ({risk_per_trade_pct:.1f}% of account)
   ├─ Contracts: {fixed_risk_contracts} contracts
   ├─ Risk per Trade: ${max_risk_dollars:,.2f}
   └─ Use When: Learning, uncertain conditions, or small account

═══════════════════════════════════════════════════════════════

📈 EXPECTED OUTCOMES (per 100 trades):

   Full Kelly Strategy:
   - Wins: {int(win_rate*100)} @ ${avg_win:.2f} = ${win_rate*100*avg_win:,.2f}
   - Losses: {int((1-win_rate)*100)} @ ${avg_loss:.2f} = ${(1-win_rate)*100*avg_loss:,.2f}
   - Net Expected: ${expected_value*100:,.2f}
   - ROI: {expected_value_pct*100:.1f}%

   Account Growth Projection:
   - Starting: ${account_size:,.2f}
   - After 100 trades: ${account_size + (expected_value*100):,.2f}
   - Gain: {((expected_value*100)/account_size)*100:+.1f}%

═══════════════════════════════════════════════════════════════

⚠️ RISK MANAGEMENT RULES:

1. NEVER risk more than {risk_per_trade_pct}% on a single trade
2. STOP trading after 3 consecutive losses (reevaluate edge)
3. Reduce position size by 50% during drawdowns >10%
4. Keep win rate above {win_rate*100-10:.0f}% or adjust strategy
5. Track EVERY trade to validate your win rate & R:R assumptions

═══════════════════════════════════════════════════════════════

🎓 HOW TO USE THIS:

1. Start with HALF KELLY until you prove your edge
2. Track actual win rate and R:R over 30+ trades
3. Adjust inputs monthly based on real performance
4. If actual results differ by >10%, recalculate immediately
5. Scale up position size only after consistent profitability

{'✅ POSITIVE EDGE: Your system has positive expectancy - keep trading!' if expected_value > 0 else '❌ NEGATIVE EDGE: DO NOT TRADE - fix strategy first!'}

═══════════════════════════════════════════════════════════════
"""

        return {
            "success": True,
            "calculations": {
                "kelly_percentage": kelly_pct,
                "kelly_percentage_capped": kelly_pct_capped,
                "reward_to_risk_ratio": reward_to_risk,
                "expected_value": expected_value,
                "expected_value_pct": expected_value_pct,
                "recommendation": recommendation
            },
            "positions": {
                "full_kelly": {
                    "dollars": kelly_position_dollars,
                    "contracts": kelly_contracts,
                    "percentage": kelly_pct_capped * 100
                },
                "half_kelly": {
                    "dollars": half_kelly_position_dollars,
                    "contracts": half_kelly_contracts,
                    "percentage": half_kelly_pct * 100
                },
                "fixed_risk": {
                    "dollars": max_risk_dollars,
                    "contracts": fixed_risk_contracts,
                    "percentage": risk_per_trade_pct
                }
            },
            "money_making_guide": money_making_guide,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# PSYCHOLOGY TRAP DETECTION ENDPOINTS
# ============================================================================

from psychology_trap_detector import (
    analyze_current_market_complete,
    save_regime_signal_to_db,
    calculate_mtf_rsi_score
)
from psychology_trading_guide import get_trading_guide
from psychology_performance import performance_tracker
from psychology_notifications import notification_manager

# ==============================================================================
# YFINANCE CACHING - Psychology page fetches once per day, manual refresh only
# ==============================================================================
_yfinance_cache = {}
_yfinance_cache_ttl = 86400  # 24 hours cache (psychology updates once per day)

def get_cached_price_data(symbol: str, current_price: float):
    """
    Get price data for symbol with caching to prevent excessive API calls
    Cache TTL: 24 hours (86400 seconds)

    Psychology page design: Fetch once per day, manual refresh only

    This function makes 5 yfinance API calls:
    - 90d daily data
    - 30d hourly→4h data
    - 7d hourly data
    - 5d 15-minute data
    - 2d 5-minute data

    With 24h caching: 5 API calls per day (only on first load or manual refresh)
    """
    cache_key = f"price_data_{symbol}"
    now = datetime.now()

    # Check if we have cached data that's still fresh
    if cache_key in _yfinance_cache:
        cached_data, cache_time = _yfinance_cache[cache_key]
        age_seconds = (now - cache_time).total_seconds()

        if age_seconds < _yfinance_cache_ttl:
            print(f"✅ Using cached price data (age: {age_seconds:.0f}s)")
            return cached_data
        else:
            print(f"⏰ Cache expired (age: {age_seconds:.0f}s > {_yfinance_cache_ttl}s)")

    # Cache miss or expired - fetch fresh data
    print(f"🔄 Fetching fresh price data from yfinance (5 API calls)")

    try:
        import yfinance as yf
        ticker = yf.Ticker(symbol)

        price_data = {}

        # Daily data (90 days for RSI calculation)
        df_1d = ticker.history(period="90d", interval="1d")
        price_data['1d'] = [
            {
                'close': row['Close'],
                'high': row['High'],
                'low': row['Low'],
                'volume': row['Volume']
            }
            for _, row in df_1d.iterrows()
        ]

        # 4-hour data (30 days)
        df_4h = ticker.history(period="30d", interval="1h")
        # Resample to 4h
        df_4h_resampled = df_4h.resample('4H').agg({
            'Close': 'last',
            'High': 'max',
            'Low': 'min',
            'Volume': 'sum'
        }).dropna()
        price_data['4h'] = [
            {
                'close': row['Close'],
                'high': row['High'],
                'low': row['Low'],
                'volume': row['Volume']
            }
            for _, row in df_4h_resampled.iterrows()
        ]

        # 1-hour data (7 days)
        df_1h = ticker.history(period="7d", interval="1h")
        price_data['1h'] = [
            {
                'close': row['Close'],
                'high': row['High'],
                'low': row['Low'],
                'volume': row['Volume']
            }
            for _, row in df_1h.iterrows()
        ]

        # 15-minute data (5 days)
        df_15m = ticker.history(period="5d", interval="15m")
        price_data['15m'] = [
            {
                'close': row['Close'],
                'high': row['High'],
                'low': row['Low'],
                'volume': row['Volume']
            }
            for _, row in df_15m.iterrows()
        ]

        # 5-minute data (2 days)
        df_5m = ticker.history(period="2d", interval="5m")
        price_data['5m'] = [
            {
                'close': row['Close'],
                'high': row['High'],
                'low': row['Low'],
                'volume': row['Volume']
            }
            for _, row in df_5m.iterrows()
        ]

        # Cache the result
        _yfinance_cache[cache_key] = (price_data, now)
        print(f"✅ Cached fresh price data for {_yfinance_cache_ttl}s (24 hours)")

        return price_data

    except Exception as e:
        # Fallback if yfinance fails
        print(f"⚠️  Warning: Could not fetch price data: {e}")
        print(f"Using fallback mock data")
        return {
            '5m': [{'close': current_price, 'high': current_price, 'low': current_price, 'volume': 0} for _ in range(100)],
            '15m': [{'close': current_price, 'high': current_price, 'low': current_price, 'volume': 0} for _ in range(100)],
            '1h': [{'close': current_price, 'high': current_price, 'low': current_price, 'volume': 0} for _ in range(100)],
            '4h': [{'close': current_price, 'high': current_price, 'low': current_price, 'volume': 0} for _ in range(50)],
            '1d': [{'close': current_price, 'high': current_price, 'low': current_price, 'volume': 0} for _ in range(50)]
        }

@app.get("/api/psychology/current-regime")
async def get_current_regime(symbol: str = "SPY"):
    """
    Get current psychology trap regime analysis

    Returns complete analysis with:
    - Multi-timeframe RSI
    - Current gamma walls
    - Gamma expiration timeline
    - Forward GEX magnets
    - Regime detection with psychology traps
    """
    try:
        print(f"\n{'='*60}")
        print(f"Psychology Trap Detection - Starting analysis for {symbol}")
        print(f"{'='*60}\n")

        # Get current price and gamma data using get_net_gamma
        gex_data = api_client.get_net_gamma(symbol)

        print(f"1. GEX Data fetched: {type(gex_data)}")

        # NEVER USE MOCK DATA - Always require real API data
        if not gex_data or 'error' in gex_data:
            error_type = gex_data.get('error', 'unknown') if gex_data else 'no_data'
            print(f"❌ GEX data error: {error_type}")

            # Return proper errors - NO MOCK DATA FALLBACK
            if error_type == 'rate_limit':
                raise HTTPException(
                    status_code=429,
                    detail={
                        "error": "Rate Limit Exceeded",
                        "message": "Trading Volatility API rate limit hit. Circuit breaker is active.",
                        "solution": "Wait 30-60 seconds and try again. System manages rate limits automatically."
                    }
                )
            elif error_type == 'api_key':
                raise HTTPException(
                    status_code=503,
                    detail={
                        "error": "Service Unavailable",
                        "message": "Trading Volatility API key not configured.",
                        "solution": "Configure 'tv_username' environment variable with your Trading Volatility API key"
                    }
                )
            else:
                # Generic error
                raise HTTPException(
                    status_code=503,
                    detail={
                        "error": "Service Unavailable",
                        "message": f"Failed to fetch GEX data: {error_type}",
                        "solution": "Check API configuration and network connectivity"
                    }
                )

        current_price = gex_data.get('spot_price', 0)
        print(f"2. Current price: ${current_price}")

        # Get price data with caching (prevents excessive API calls)
        price_data = get_cached_price_data(symbol, current_price)
        print(f"3. Price data prepared with {len(price_data)} timeframes")

        # Calculate volume ratio (using daily data)
        if len(price_data['1d']) >= 20:
            recent_volume = price_data['1d'][-1]['volume']
            avg_volume = sum(d['volume'] for d in price_data['1d'][-20:]) / 20
            volume_ratio = recent_volume / avg_volume if avg_volume > 0 else 1.0
        else:
            volume_ratio = 1.0

        # Format gamma data for psychology trap detector
        # Need to structure with expirations
        gamma_data_formatted = {
            'net_gamma': gex_data.get('net_gex', 0),
            'expirations': []
        }

        # Parse expiration data from gex_data
        # The TradingVolatility API returns strikes by expiration
        if 'expirations' in gex_data:
            for exp_date_str, exp_data in gex_data['expirations'].items():
                try:
                    # Parse expiration date
                    exp_date = datetime.strptime(exp_date_str, '%Y-%m-%d')
                    dte = (exp_date - datetime.now()).days

                    # Determine expiration type
                    if dte == 0:
                        exp_type = '0dte'
                    elif dte <= 7:
                        exp_type = 'weekly'
                    else:
                        # Check if it's monthly (3rd Friday)
                        # For simplicity, treat all > 7 DTE as monthly
                        exp_type = 'monthly'

                    call_strikes = []
                    put_strikes = []

                    if 'strikes' in exp_data:
                        for strike_data in exp_data['strikes']:
                            strike = strike_data.get('strike', 0)

                            if 'call_gamma' in strike_data:
                                call_strikes.append({
                                    'strike': strike,
                                    'gamma_exposure': strike_data['call_gamma'],
                                    'open_interest': strike_data.get('call_oi', 0)
                                })

                            if 'put_gamma' in strike_data:
                                put_strikes.append({
                                    'strike': strike,
                                    'gamma_exposure': strike_data['put_gamma'],
                                    'open_interest': strike_data.get('put_oi', 0)
                                })

                    gamma_data_formatted['expirations'].append({
                        'expiration_date': exp_date,
                        'dte': dte,
                        'expiration_type': exp_type,
                        'call_strikes': call_strikes,
                        'put_strikes': put_strikes
                    })

                except Exception as e:
                    print(f"Error parsing expiration {exp_date_str}: {e}")
                    continue
        else:
            # Fallback: create single expiration from call/put walls
            call_wall = gex_data.get('call_wall', current_price * 1.02)
            put_wall = gex_data.get('put_wall', current_price * 0.98)

            gamma_data_formatted['expirations'] = [{
                'expiration_date': datetime.now() + timedelta(days=7),
                'dte': 7,
                'expiration_type': 'weekly',
                'call_strikes': [{
                    'strike': call_wall,
                    'gamma_exposure': gex_data.get('net_gex', 0) / 2,
                    'open_interest': 1000
                }],
                'put_strikes': [{
                    'strike': put_wall,
                    'gamma_exposure': gex_data.get('net_gex', 0) / 2,
                    'open_interest': 1000
                }]
            }]

        print(f"4. Gamma data formatted with {len(gamma_data_formatted.get('expirations', []))} expirations")
        print(f"5. Volume ratio: {volume_ratio:.2f}")
        print(f"\nCalling analyze_current_market_complete...")

        # Run complete psychology trap analysis
        try:
            analysis = analyze_current_market_complete(
                current_price=current_price,
                price_data=price_data,
                gamma_data=gamma_data_formatted,
                volume_ratio=volume_ratio
            )
            print(f"✅ Analysis complete!")
        except Exception as analysis_error:
            print(f"❌ Error in analyze_current_market_complete:")
            import traceback
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=f"Psychology analysis failed: {str(analysis_error)}")

        # Save to database
        try:
            signal_id = save_regime_signal_to_db(analysis)
            analysis['signal_id'] = signal_id
            print(f"6. Saved to database with ID: {signal_id}")
        except Exception as e:
            print(f"⚠️  Warning: Could not save regime signal: {e}")

        print(f"\n{'='*60}")
        print(f"Psychology Trap Detection - Analysis Complete")
        print(f"{'='*60}\n")

        # Generate trading guide
        trading_guide = get_trading_guide(
            regime_type=analysis['regime']['primary_type'],
            current_price=current_price,
            regime_data=analysis['regime']
        )

        # Convert numpy types to Python native types for JSON serialization
        def convert_numpy_types(obj):
            """Recursively convert numpy types to Python native types"""
            import numpy as np
            if isinstance(obj, dict):
                return {k: convert_numpy_types(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [convert_numpy_types(item) for item in obj]
            elif isinstance(obj, np.bool_):
                return bool(obj)
            elif isinstance(obj, np.integer):
                return int(obj)
            elif isinstance(obj, np.floating):
                return float(obj)
            elif isinstance(obj, np.ndarray):
                return obj.tolist()
            else:
                return obj

        # Convert all data before returning
        analysis = convert_numpy_types(analysis)
        trading_guide = convert_numpy_types(trading_guide)

        return {
            "success": True,
            "symbol": symbol,
            "analysis": analysis,
            "trading_guide": trading_guide
        }

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


@app.get("/api/psychology/history")
async def get_regime_history(limit: int = 50, regime_type: str = None):
    """
    Get historical regime signals

    Args:
        limit: Number of recent signals to return
        regime_type: Filter by specific regime type (optional)
    """
    try:
        import sqlite3
        from config_and_database import DB_PATH

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        if regime_type:
            c.execute('''
                SELECT * FROM regime_signals
                WHERE primary_regime_type = ?
                ORDER BY timestamp DESC
                LIMIT ?
            ''', (regime_type, limit))
        else:
            c.execute('''
                SELECT * FROM regime_signals
                ORDER BY timestamp DESC
                LIMIT ?
            ''', (limit,))

        columns = [desc[0] for desc in c.description]
        rows = c.fetchall()

        signals = []
        for row in rows:
            signal = dict(zip(columns, row))
            signals.append(signal)

        conn.close()

        return {
            "success": True,
            "count": len(signals),
            "signals": signals
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/psychology/liberation-setups")
async def get_liberation_setups():
    """
    Get active liberation trade setups
    Returns walls that are about to expire and release price
    """
    try:
        import sqlite3
        from config_and_database import DB_PATH

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        # Get recent signals with liberation setups
        c.execute('''
            SELECT * FROM regime_signals
            WHERE liberation_setup_detected = 1
            AND liberation_expiry_date >= date('now')
            ORDER BY liberation_expiry_date ASC
            LIMIT 10
        ''')

        columns = [desc[0] for desc in c.description]
        rows = c.fetchall()

        setups = []
        for row in rows:
            setup = dict(zip(columns, row))
            setups.append(setup)

        conn.close()

        return {
            "success": True,
            "count": len(setups),
            "liberation_setups": setups
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/psychology/false-floors")
async def get_false_floors():
    """
    Get active false floor warnings
    Returns support levels that are temporary and will disappear
    """
    try:
        import sqlite3
        from config_and_database import DB_PATH

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        # Get recent signals with false floor warnings
        c.execute('''
            SELECT * FROM regime_signals
            WHERE false_floor_detected = 1
            AND false_floor_expiry_date >= date('now')
            ORDER BY false_floor_expiry_date ASC
            LIMIT 10
        ''')

        columns = [desc[0] for desc in c.description]
        rows = c.fetchall()

        floors = []
        for row in rows:
            floor = dict(zip(columns, row))
            floors.append(floor)

        conn.close()

        return {
            "success": True,
            "count": len(floors),
            "false_floors": floors
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/psychology/statistics")
async def get_sucker_statistics():
    """
    Get statistics on how often newbie logic fails
    Shows historical success/failure rates for different scenarios
    """
    try:
        import sqlite3
        from config_and_database import DB_PATH

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        # Get sucker statistics
        c.execute('SELECT * FROM sucker_statistics ORDER BY failure_rate DESC')

        columns = [desc[0] for desc in c.description]
        rows = c.fetchall()

        stats = []
        for row in rows:
            stat = dict(zip(columns, row))
            stats.append(stat)

        # If no data, return default stats
        if not stats:
            stats = [
                {
                    'scenario_type': 'LIBERATION_TRADE',
                    'total_occurrences': 0,
                    'newbie_fade_failed': 0,
                    'newbie_fade_succeeded': 0,
                    'failure_rate': 0,
                    'avg_price_change_when_failed': 0,
                    'avg_days_to_resolution': 0,
                    'last_updated': None
                }
            ]

        conn.close()

        return {
            "success": True,
            "count": len(stats),
            "statistics": stats
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/psychology/performance/overview")
async def get_performance_overview(days: int = 30):
    """
    Get overall performance metrics for psychology trap detection

    Args:
        days: Number of days to analyze (default 30)

    Returns:
        Overall metrics including total signals, win rate, avg confidence, etc.
    """
    try:
        metrics = performance_tracker.get_overview_metrics(days)
        return {
            "success": True,
            "metrics": metrics
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/psychology/performance/by-pattern")
async def get_pattern_performance(days: int = 90):
    """
    Get performance metrics for each pattern type

    Args:
        days: Number of days to analyze (default 90)

    Returns:
        List of pattern performance data with win rates, expectancy, etc.
    """
    try:
        patterns = performance_tracker.get_pattern_performance(days)
        return {
            "success": True,
            "count": len(patterns),
            "patterns": patterns
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/psychology/performance/signals")
async def get_historical_signals(limit: int = 100, pattern_type: str = None):
    """
    Get historical signals with full details and outcomes

    Args:
        limit: Maximum number of signals to return (default 100)
        pattern_type: Filter by specific pattern type (optional)

    Returns:
        List of historical signals with timestamps, patterns, outcomes, etc.
    """
    try:
        signals = performance_tracker.get_historical_signals(limit, pattern_type)
        return {
            "success": True,
            "count": len(signals),
            "signals": signals
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/psychology/performance/chart-data")
async def get_chart_data(days: int = 90):
    """
    Get time series data for performance charts

    Args:
        days: Number of days of data (default 90)

    Returns:
        Dict with daily_signals, win_rate_timeline, and pattern_timeline
    """
    try:
        chart_data = performance_tracker.get_chart_data(days)
        return {
            "success": True,
            "chart_data": chart_data
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/psychology/performance/vix-correlation")
async def get_vix_correlation(days: int = 90):
    """
    Analyze correlation between VIX levels and pattern performance

    Args:
        days: Number of days to analyze (default 90)

    Returns:
        Performance data by VIX level and spike status
    """
    try:
        correlation = performance_tracker.get_vix_correlation(days)
        return {
            "success": True,
            "correlation": correlation
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/psychology/notifications/stream")
async def notification_stream():
    """
    Server-Sent Events (SSE) endpoint for real-time notifications

    Streams critical psychology trap pattern alerts to connected clients.
    Critical patterns: GAMMA_SQUEEZE_CASCADE, FLIP_POINT_CRITICAL, CAPITULATION_CASCADE
    """
    async def event_generator():
        # Subscribe to notifications
        queue = await notification_manager.subscribe()

        try:
            # Send initial connection message
            yield f"data: {json.dumps({'type': 'connected', 'message': 'Notification stream connected'})}\n\n"

            # Stream notifications
            while True:
                try:
                    # Wait for notification with timeout
                    notification = await asyncio.wait_for(queue.get(), timeout=30.0)

                    # Send notification as SSE
                    yield f"data: {json.dumps(notification)}\n\n"

                except asyncio.TimeoutError:
                    # Send keepalive ping every 30 seconds
                    yield f"data: {json.dumps({'type': 'ping'})}\n\n"

        except asyncio.CancelledError:
            # Client disconnected
            await notification_manager.unsubscribe(queue)
            raise
        except Exception as e:
            print(f"Error in notification stream: {e}")
            await notification_manager.unsubscribe(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Disable buffering for nginx
        }
    )


@app.get("/api/psychology/notifications/history")
async def get_notification_history(limit: int = 50):
    """
    Get recent notification history

    Args:
        limit: Maximum number of notifications to return (default 50)

    Returns:
        List of recent notifications
    """
    try:
        history = notification_manager.get_notification_history(limit)
        return {
            "success": True,
            "count": len(history),
            "notifications": history
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/psychology/notifications/stats")
async def get_notification_stats():
    """
    Get notification statistics

    Returns:
        Stats including total notifications, critical count, active subscribers, etc.
    """
    try:
        stats = notification_manager.get_notification_stats()
        return {
            "success": True,
            "stats": stats
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==============================================================================
# BACKTEST RESULTS ENDPOINTS
# ==============================================================================

@app.get("/api/backtests/results")
async def get_backtest_results(strategy_name: str = None, limit: int = 50):
    """
    Get backtest results for all strategies or specific strategy

    Args:
        strategy_name: Filter by specific strategy (optional)
        limit: Maximum number of results (default 50)

    Returns:
        List of backtest results with full metrics
    """
    try:
        import sqlite3
        from config_and_database import DB_PATH

        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        if strategy_name:
            c.execute('''
                SELECT *
                FROM backtest_results
                WHERE strategy_name = ?
                ORDER BY timestamp DESC
                LIMIT ?
            ''', (strategy_name, limit))
        else:
            c.execute('''
                SELECT *
                FROM backtest_results
                ORDER BY timestamp DESC
                LIMIT ?
            ''', (limit,))

        results = []
        for row in c.fetchall():
            results.append({
                'id': row['id'],
                'timestamp': row['timestamp'],
                'strategy_name': row['strategy_name'],
                'symbol': row['symbol'],
                'start_date': row['start_date'],
                'end_date': row['end_date'],
                'total_trades': row['total_trades'],
                'winning_trades': row['winning_trades'],
                'losing_trades': row['losing_trades'],
                'win_rate': round(row['win_rate'], 1),
                'avg_win_pct': round(row['avg_win_pct'], 2),
                'avg_loss_pct': round(row['avg_loss_pct'], 2),
                'largest_win_pct': round(row['largest_win_pct'], 2),
                'largest_loss_pct': round(row['largest_loss_pct'], 2),
                'expectancy_pct': round(row['expectancy_pct'], 2),
                'total_return_pct': round(row['total_return_pct'], 2),
                'max_drawdown_pct': round(row['max_drawdown_pct'], 2),
                'sharpe_ratio': round(row['sharpe_ratio'], 2),
                'avg_trade_duration_days': round(row['avg_trade_duration_days'], 1)
            })

        conn.close()

        return {
            "success": True,
            "count": len(results),
            "results": results
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/backtests/summary")
async def get_backtest_summary():
    """
    Get latest backtest summary comparing all strategy categories

    Returns:
        Summary with psychology, GEX, and options strategy performance
    """
    try:
        import sqlite3
        from config_and_database import DB_PATH

        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        c.execute('''
            SELECT *
            FROM backtest_summary
            ORDER BY timestamp DESC
            LIMIT 1
        ''')

        row = c.fetchone()
        conn.close()

        if not row:
            return {
                "success": True,
                "summary": None,
                "message": "No backtest summary found. Run backtests first."
            }

        summary = {
            'timestamp': row['timestamp'],
            'symbol': row['symbol'],
            'start_date': row['start_date'],
            'end_date': row['end_date'],
            'psychology': {
                'total_trades': row['psychology_trades'],
                'win_rate': round(row['psychology_win_rate'], 1),
                'expectancy_pct': round(row['psychology_expectancy'], 2)
            },
            'gex': {
                'total_trades': row['gex_trades'],
                'win_rate': round(row['gex_win_rate'], 1),
                'expectancy_pct': round(row['gex_expectancy'], 2)
            },
            'options': {
                'total_trades': row['options_trades'],
                'win_rate': round(row['options_win_rate'], 1),
                'expectancy_pct': round(row['options_expectancy'], 2)
            }
        }

        return {
            "success": True,
            "summary": summary
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/backtests/best-strategies")
async def get_best_strategies(min_expectancy: float = 0.5, min_win_rate: float = 55):
    """
    Get best performing strategies based on backtest results

    Args:
        min_expectancy: Minimum expectancy % (default 0.5)
        min_win_rate: Minimum win rate % (default 55)

    Returns:
        List of strategies that meet criteria, sorted by expectancy
    """
    try:
        import sqlite3
        from config_and_database import DB_PATH

        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        c.execute('''
            SELECT *
            FROM backtest_results
            WHERE expectancy_pct >= ?
            AND win_rate >= ?
            AND total_trades >= 10
            ORDER BY expectancy_pct DESC
            LIMIT 20
        ''', (min_expectancy, min_win_rate))

        strategies = []
        for row in c.fetchall():
            strategies.append({
                'strategy_name': row['strategy_name'],
                'total_trades': row['total_trades'],
                'win_rate': round(row['win_rate'], 1),
                'expectancy_pct': round(row['expectancy_pct'], 2),
                'total_return_pct': round(row['total_return_pct'], 2),
                'sharpe_ratio': round(row['sharpe_ratio'], 2),
                'max_drawdown_pct': round(row['max_drawdown_pct'], 2)
            })

        conn.close()

        return {
            "success": True,
            "count": len(strategies),
            "strategies": strategies,
            "criteria": {
                "min_expectancy_pct": min_expectancy,
                "min_win_rate": min_win_rate
            }
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==============================================================================
# AI-POWERED FEATURES (Claude + LangChain)
# ==============================================================================

@app.post("/api/ai/optimize-strategy")
async def optimize_strategy(request: dict):
    """
    AI-powered strategy optimization using Claude

    Request body:
        {
            "strategy_name": "GAMMA_SQUEEZE_CASCADE",
            "api_key": "optional_anthropic_key"
        }

    Returns:
        Detailed analysis and optimization recommendations
    """
    try:
        from ai_strategy_optimizer import StrategyOptimizerAgent

        strategy_name = request.get('strategy_name')
        api_key = request.get('api_key')

        if not strategy_name:
            raise HTTPException(status_code=400, detail="strategy_name required")

        optimizer = StrategyOptimizerAgent(anthropic_api_key=api_key)
        result = optimizer.optimize_strategy(strategy_name)

        return {
            "success": True,
            "optimization": result
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/ai/analyze-all-strategies")
async def analyze_all_strategies(api_key: str = None):
    """
    AI analysis of all strategies with rankings and recommendations

    Query params:
        api_key: Optional Anthropic API key

    Returns:
        Comprehensive analysis report with strategy rankings
    """
    try:
        from ai_strategy_optimizer import StrategyOptimizerAgent

        optimizer = StrategyOptimizerAgent(anthropic_api_key=api_key)
        result = optimizer.analyze_all_strategies()

        return {
            "success": True,
            "analysis": result
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/ai/trade-advice")
async def get_trade_advice(signal_data: dict):
    """
    Get AI-powered trade recommendation with reasoning

    Request body:
        {
            "pattern": "GAMMA_SQUEEZE_CASCADE",
            "price": 570.25,
            "direction": "Bullish",
            "confidence": 85,
            "vix": 18.5,
            "volatility_regime": "EXPLOSIVE_VOLATILITY",
            "description": "VIX spike detected",
            "api_key": "optional_anthropic_key"
        }

    Returns:
        Recommendation (TAKE_TRADE/SKIP/WAIT) with detailed reasoning
    """
    try:
        from ai_trade_advisor import SmartTradeAdvisor

        api_key = signal_data.pop('api_key', None)
        advisor = SmartTradeAdvisor(anthropic_api_key=api_key)
        result = advisor.analyze_trade(signal_data)

        return {
            "success": True,
            "advice": result
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/ai/feedback")
async def provide_ai_feedback(feedback: dict):
    """
    Provide feedback on AI prediction to enable learning

    Request body:
        {
            "prediction_id": 123,
            "actual_outcome": "WIN" or "LOSS",
            "outcome_pnl": 2.5
        }

    Returns:
        Updated learning stats
    """
    try:
        from ai_trade_advisor import SmartTradeAdvisor

        advisor = SmartTradeAdvisor()
        result = advisor.provide_feedback(
            prediction_id=feedback.get('prediction_id'),
            actual_outcome=feedback.get('actual_outcome'),
            outcome_pnl=feedback.get('outcome_pnl', 0.0)
        )

        return {
            "success": True,
            "feedback": result
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/ai/learning-insights")
async def get_learning_insights():
    """
    Get AI learning insights (accuracy by pattern, confidence calibration, etc)

    Returns:
        Learning statistics and insights
    """
    try:
        from ai_trade_advisor import SmartTradeAdvisor

        advisor = SmartTradeAdvisor()
        insights = advisor.get_learning_insights()

        return {
            "success": True,
            "insights": insights
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/ai/track-record")
async def get_ai_track_record(days: int = 30):
    """
    Get AI's prediction track record over time

    Query params:
        days: Number of days to analyze (default 30)

    Returns:
        Accuracy stats and calibration metrics
    """
    try:
        from ai_trade_advisor import SmartTradeAdvisor

        advisor = SmartTradeAdvisor()
        track_record = advisor.get_ai_track_record(days=days)

        return {
            "success": True,
            "track_record": track_record
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==============================================================================
# PROBABILITY PREDICTION ENDPOINTS (Phase 2 Self-Learning)
# ==============================================================================

@app.post("/api/probability/record-outcome")
async def record_probability_outcome(request: dict):
    """
    Record actual outcome for a prediction (for calibration/learning)

    Request body:
        {
            "prediction_id": 123,
            "actual_close_price": 570.50
        }

    Returns:
        Success status
    """
    try:
        prediction_id = request.get('prediction_id')
        actual_close_price = request.get('actual_close_price')

        if not prediction_id or actual_close_price is None:
            raise HTTPException(
                status_code=400,
                detail="prediction_id and actual_close_price required"
            )

        probability_calc.record_outcome(prediction_id, actual_close_price)

        return {
            "success": True,
            "message": f"Outcome recorded for prediction {prediction_id}"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/probability/accuracy")
async def get_probability_accuracy(days: int = 30):
    """
    Get accuracy metrics for probability predictions

    Query params:
        days: Number of days to analyze (default 30)

    Returns:
        Accuracy statistics by prediction type and confidence level
    """
    try:
        metrics = probability_calc.get_accuracy_metrics(days=days)

        return {
            "success": True,
            "metrics": metrics
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/probability/calibrate")
async def calibrate_probability_model(min_predictions: int = 50):
    """
    Calibrate probability model based on actual outcomes (Phase 2 Self-Learning)

    This adjusts weights to improve accuracy based on historical performance.

    Query params:
        min_predictions: Minimum predictions required for calibration (default 50)

    Returns:
        Calibration results and new weights
    """
    try:
        result = probability_calc.calibrate(min_predictions=min_predictions)

        return {
            "success": True,
            "calibration": result
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/psychology/rsi-analysis/{symbol}")
async def get_rsi_analysis(symbol: str = "SPY"):
    """
    Get multi-timeframe RSI analysis only
    Useful for quick RSI checks without full regime analysis
    """
    try:
        import yfinance as yf

        ticker = yf.Ticker(symbol)

        # Get price data for different timeframes
        price_data = {}

        # Daily
        df_1d = ticker.history(period="90d", interval="1d")
        price_data['1d'] = [{'close': row['Close'], 'high': row['High'], 'low': row['Low'], 'volume': row['Volume']}
                           for _, row in df_1d.iterrows()]

        # 4-hour
        df_4h = ticker.history(period="30d", interval="1h")
        df_4h_resampled = df_4h.resample('4H').agg({
            'Close': 'last', 'High': 'max', 'Low': 'min', 'Volume': 'sum'
        }).dropna()
        price_data['4h'] = [{'close': row['Close'], 'high': row['High'], 'low': row['Low'], 'volume': row['Volume']}
                           for _, row in df_4h_resampled.iterrows()]

        # 1-hour
        df_1h = ticker.history(period="7d", interval="1h")
        price_data['1h'] = [{'close': row['Close'], 'high': row['High'], 'low': row['Low'], 'volume': row['Volume']}
                           for _, row in df_1h.iterrows()]

        # 15-minute
        df_15m = ticker.history(period="5d", interval="15m")
        price_data['15m'] = [{'close': row['Close'], 'high': row['High'], 'low': row['Low'], 'volume': row['Volume']}
                            for _, row in df_15m.iterrows()]

        # 5-minute
        df_5m = ticker.history(period="2d", interval="5m")
        price_data['5m'] = [{'close': row['Close'], 'high': row['High'], 'low': row['Low'], 'volume': row['Volume']}
                           for _, row in df_5m.iterrows()]

        # Calculate RSI
        rsi_analysis = calculate_mtf_rsi_score(price_data)

        return {
            "success": True,
            "symbol": symbol,
            "timestamp": datetime.now().isoformat(),
            "rsi_analysis": rsi_analysis
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/psychology/quick-check/{symbol}")
async def get_quick_psychology_check(symbol: str = "SPY"):
    """
    Quick psychology trap check for scanners (lightweight version)
    Returns only regime type, confidence, and trade direction
    """
    try:
        import yfinance as yf

        # Get basic price data (less history for speed)
        ticker = yf.Ticker(symbol)
        current_price = ticker.history(period="1d")['Close'].iloc[-1]

        # Get minimal price data for RSI
        df_1d = ticker.history(period="30d", interval="1d")
        df_1h = ticker.history(period="3d", interval="1h")

        price_data = {
            '5m': [{'close': current_price, 'high': current_price, 'low': current_price, 'volume': 0} for _ in range(50)],
            '15m': [{'close': current_price, 'high': current_price, 'low': current_price, 'volume': 0} for _ in range(50)],
            '1h': [{'close': row['Close'], 'high': row['High'], 'low': row['Low'], 'volume': row['Volume']}
                   for _, row in df_1h.iterrows()],
            '4h': [{'close': current_price, 'high': current_price, 'low': current_price, 'volume': 0} for _ in range(50)],
            '1d': [{'close': row['Close'], 'high': row['High'], 'low': row['Low'], 'volume': row['Volume']}
                   for _, row in df_1d.iterrows()]
        }

        # Calculate RSI only
        rsi_analysis = calculate_mtf_rsi_score(price_data)

        # Simple regime determination
        regime_type = 'NEUTRAL'
        confidence = 50
        trade_direction = 'wait'

        # Check for obvious extremes
        if rsi_analysis['aligned_count']['overbought'] >= 3:
            regime_type = 'OVERBOUGHT_EXTREME'
            confidence = 60 + rsi_analysis['aligned_count']['overbought'] * 5
            trade_direction = 'fade' if rsi_analysis['score'] > 70 else 'momentum'
        elif rsi_analysis['aligned_count']['oversold'] >= 3:
            regime_type = 'OVERSOLD_EXTREME'
            confidence = 60 + rsi_analysis['aligned_count']['oversold'] * 5
            trade_direction = 'bounce' if rsi_analysis['score'] < -70 else 'breakdown'

        return {
            "success": True,
            "symbol": symbol,
            "regime_type": regime_type,
            "confidence": confidence,
            "trade_direction": trade_direction,
            "rsi_score": rsi_analysis['score'],
            "overbought_tfs": rsi_analysis['aligned_count']['overbought'],
            "oversold_tfs": rsi_analysis['aligned_count']['oversold'],
            "current_price": float(current_price)
        }

    except Exception as e:
        return {
            "success": False,
            "symbol": symbol,
            "regime_type": "ERROR",
            "confidence": 0,
            "trade_direction": "wait",
            "error": str(e)
        }


# ============================================================================
# Startup & Shutdown Events
# ============================================================================

@app.on_event("startup")
async def startup_event():
    """Run on application startup"""
    print("=" * 80)
    print("🚀 AlphaGEX API Starting...")
    print("=" * 80)
    print(f"Environment: {os.getenv('ENVIRONMENT', 'development')}")
    print(f"Market Open: {is_market_open()}")
    print(f"Current Time (ET): {get_et_time().strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print("=" * 80)
    print("📊 Available Endpoints:")
    print("  - GET  /                                  Health check")
    print("  - GET  /docs                              API documentation")
    print("  - GET  /api/gex/{symbol}                  GEX data")
    print("  - GET  /api/gamma/{symbol}/intelligence   Gamma 3 views")
    print("  - POST /api/ai/analyze                    AI Copilot")
    print("  - WS   /ws/market-data                    Real-time updates")
    print("\n🧠 Psychology Trap Detection:")
    print("  - GET  /api/psychology/current-regime     Current regime analysis")
    print("  - GET  /api/psychology/rsi-analysis/{symbol}  Multi-TF RSI")
    print("  - GET  /api/psychology/liberation-setups  Liberation trades")
    print("  - GET  /api/psychology/false-floors       False floor warnings")
    print("  - GET  /api/psychology/history            Historical signals")
    print("  - GET  /api/psychology/statistics         Sucker statistics")
    print("=" * 80)

    # Start Autonomous Trader in background thread
    try:
        import threading
        from autonomous_scheduler import run_continuous_scheduler

        print("\n🤖 Starting Autonomous Trader...")
        print("⏰ Check interval: 5 minutes (optimized for max responsiveness)")
        print("📈 Will trade daily during market hours (9:30am-4pm ET, Mon-Fri)")
        print("🎯 GUARANTEED: Makes at least 1 trade per day (directional or Iron Condor)")

        # Start autonomous trader in daemon thread
        trader_thread = threading.Thread(
            target=run_continuous_scheduler,
            kwargs={'check_interval_minutes': 5},
            daemon=True,
            name="AutonomousTrader"
        )
        trader_thread.start()

        print("✅ Autonomous Trader started successfully!")
        print("=" * 80 + "\n")
    except Exception as e:
        print(f"⚠️ Warning: Could not start Autonomous Trader: {e}")
        print("   (Trader can still be run manually via autonomous_scheduler.py)")
        print("=" * 80 + "\n")

    # Start Psychology Trap Notification Monitor
    try:
        print("🔔 Starting Psychology Trap Notification Monitor...")
        print("⚡ Critical patterns: GAMMA_SQUEEZE_CASCADE, FLIP_POINT_CRITICAL")
        print("⏰ Check interval: 60 seconds")

        # Start notification monitor as background task
        asyncio.create_task(notification_manager.monitor_and_notify(interval_seconds=60))

        print("✅ Notification Monitor started successfully!")
        print("=" * 80 + "\n")
    except Exception as e:
        print(f"⚠️ Warning: Could not start Notification Monitor: {e}")
        print("   (Notifications will not be sent)")
        print("=" * 80 + "\n")

@app.on_event("shutdown")
async def shutdown_event():
    """Run on application shutdown"""
    print("🛑 AlphaGEX API Shutting down...")

# ============================================================================
# Run Server (for local development)
# ============================================================================

if __name__ == "__main__":
    # Run with: python main.py
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,  # Auto-reload on code changes
        log_level="info"
    )
