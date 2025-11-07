"""
AlphaGEX FastAPI Backend
Main application entry point - Professional Options Intelligence Platform
"""

import os
import sys
from datetime import datetime
from pathlib import Path

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

# Add parent directory to path to import existing AlphaGEX modules
parent_dir = Path(__file__).parent.parent
sys.path.insert(0, str(parent_dir))

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
import uvicorn

# Import existing AlphaGEX logic (DO NOT MODIFY THESE)
from core_classes_and_engines import TradingVolatilityAPI, MonteCarloEngine, BlackScholesPricer
from intelligence_and_strategies import ClaudeIntelligence, get_et_time, get_local_time, is_market_open, MultiStrategyOptimizer
from config_and_database import STRATEGIES

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

    # Test API connectivity with SPY
    test_result = api_client.get_net_gamma("SPY")
    api_working = not test_result.get('error') if test_result else False

    return {
        "status": "diagnostic",
        "timestamp": datetime.now().isoformat(),
        "configuration": {
            "api_key_configured": api_key_configured,
            "api_key_source": api_key_source,
            "api_endpoint": api_client.endpoint if hasattr(api_client, 'endpoint') else "unknown"
        },
        "connectivity": {
            "api_working": api_working,
            "test_symbol": "SPY",
            "test_result": "success" if api_working else "failed",
            "error": test_result.get('error') if test_result and test_result.get('error') else None,
            "spot_price": test_result.get('spot_price') if api_working else None
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

        # Enhance data with missing fields for frontend compatibility
        enhanced_data = {
            **gex_data,
            "total_call_gex": gex_data.get('total_call_gex', 0),
            "total_put_gex": gex_data.get('total_put_gex', 0),
            "key_levels": {
                "resistance": levels_data.get('resistance', []) if levels_data else [],
                "support": levels_data.get('support', []) if levels_data else []
            }
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
        return {
            "success": True,
            "data": live_status
        }
    except Exception as e:
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
        if not gex_data:
            raise HTTPException(status_code=404, detail=f"No GEX data available for {symbol}")

        # Get VIX data for additional context
        try:
            import yfinance as yf
            vix_ticker = yf.Ticker("^VIX")
            vix_data = vix_ticker.history(period="1d")
            vix = float(vix_data['Close'].iloc[-1]) if not vix_data.empty else 15.0
        except:
            vix = 15.0  # Default fallback

        # Prepare market data for optimizer
        market_data = {
            'spot_price': gex_data.get('spot_price', 0),
            'net_gex': gex_data.get('net_gex', 0),
            'flip_point': gex_data.get('zero_gamma', 0),
            'call_wall': gex_data.get('largest_call_strike', 0),
            'put_wall': gex_data.get('largest_put_strike', 0),
            'call_wall_gamma': gex_data.get('largest_call_oi', 0),
            'put_wall_gamma': gex_data.get('largest_put_oi', 0),
            'vix': vix
        }

        # Get comprehensive strategy comparison
        comparison = strategy_optimizer.compare_all_strategies(market_data)

        return {
            "success": True,
            "symbol": symbol,
            "data": comparison
        }
    except HTTPException:
        raise
    except Exception as e:
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

                # Check ALL strategies (not just Iron Condor!)
                for strategy_name, strategy_config in STRATEGIES.items():
                    confidence = 0
                    setup = None

                    # NEGATIVE GEX SQUEEZE - Directional Long Play
                    if strategy_name == 'NEGATIVE_GEX_SQUEEZE':
                        if net_gex < strategy_config['conditions']['net_gex_threshold']:
                            distance_to_flip = abs(spot_price - flip_point) / spot_price * 100
                            if distance_to_flip < strategy_config['conditions']['distance_to_flip']:
                                confidence = 0.75 if spot_price < flip_point else 0.85

                                setup = {
                                    'symbol': symbol,
                                    'strategy': strategy_name,
                                    'confidence': confidence,
                                    'net_gex': net_gex,
                                    'spot_price': spot_price,
                                    'flip_point': flip_point,
                                    'call_wall': call_wall,
                                    'put_wall': put_wall,
                                    'entry_price': spot_price,
                                    'target_price': call_wall,
                                    'stop_price': put_wall,
                                    'risk_reward': strategy_config['risk_reward'],
                                    'expected_move': strategy_config['typical_move'],
                                    'win_rate': strategy_config['win_rate'],
                                    'money_making_plan': f"""
🎯 HOW TO MAKE MONEY WITH THIS SETUP:

1. **THE SETUP** (Current State):
   - {symbol} is in NEGATIVE GEX regime (${net_gex/1e9:.1f}B)
   - Price: ${spot_price:.2f} | Flip: ${flip_point:.2f}
   - This means: Market makers are SHORT gamma and must hedge aggressively

2. **THE TRADE** (Specific Actions):
   - BUY {symbol} ${(flip_point + 0.5):.2f} CALL (ATM or slightly OTM)
   - Entry: When price breaks ${flip_point:.2f} (flip point)
   - Quantity: Risk 1-2% of account (use Position Sizing tool)
   - Time: 0-3 DTE for max gamma, OR 7-14 DTE for less risk

3. **THE PROFIT** (Exit Strategy):
   - Target 1: ${(spot_price + (spot_price * 0.02)):.2f} (2% move) - Take 50% off
   - Target 2: ${call_wall:.2f} (Call Wall) - Take remaining 50% off
   - STOP LOSS: ${put_wall:.2f} (Put Wall breach) - Exit immediately
   - Expected Win Rate: {strategy_config['win_rate']*100:.0f}%

4. **WHY IT WORKS**:
   - Negative GEX = MMs chase price UP when it rises
   - Breaking flip point = Feedback loop begins
   - Call wall = Where MM hedging pressure stops
   - This setup wins {strategy_config['win_rate']*100:.0f}% historically

5. **TIMING**:
   - Best days: {', '.join(strategy_config['best_days'])}
   - Best time: First 30 min after flip break
   - Avoid: Last 15 min of day (low liquidity)
                                    """,
                                    'reasoning': f"Negative GEX ({net_gex/1e9:.1f}B) creates upside squeeze. Price ${distance_to_flip:.1f}% from flip point. Win rate: {strategy_config['win_rate']*100:.0f}%"
                                }

                    # POSITIVE GEX BREAKDOWN - Directional Short Play
                    elif strategy_name == 'POSITIVE_GEX_BREAKDOWN':
                        if net_gex > strategy_config['conditions']['net_gex_threshold']:
                            proximity = abs(spot_price - flip_point) / flip_point * 100
                            if proximity < strategy_config['conditions']['proximity_to_flip']:
                                confidence = 0.70

                                setup = {
                                    'symbol': symbol,
                                    'strategy': strategy_name,
                                    'confidence': confidence,
                                    'net_gex': net_gex,
                                    'spot_price': spot_price,
                                    'flip_point': flip_point,
                                    'call_wall': call_wall,
                                    'put_wall': put_wall,
                                    'entry_price': spot_price,
                                    'target_price': put_wall,
                                    'stop_price': call_wall,
                                    'risk_reward': strategy_config['risk_reward'],
                                    'expected_move': strategy_config['typical_move'],
                                    'win_rate': strategy_config['win_rate'],
                                    'money_making_plan': f"""
🎯 HOW TO MAKE MONEY WITH THIS SETUP:

1. **THE SETUP** (Current State):
   - {symbol} is in POSITIVE GEX regime (${net_gex/1e9:.1f}B)
   - Price: ${spot_price:.2f} | Flip: ${flip_point:.2f}
   - This means: Market makers are LONG gamma and will fade moves

2. **THE TRADE** (Specific Actions):
   - BUY {symbol} ${(flip_point - 0.5):.2f} PUT (ATM or slightly OTM)
   - Entry: When price breaks BELOW ${flip_point:.2f} (flip point)
   - Quantity: Risk 1-2% of account
   - Time: 0-3 DTE for max profit potential

3. **THE PROFIT** (Exit Strategy):
   - Target: ${put_wall:.2f} (Put Wall) - Exit 100% here
   - Stop: ${call_wall:.2f} (Call Wall breach) - Cut losses
   - Expected Win Rate: {strategy_config['win_rate']*100:.0f}%
   - Typical Move: {strategy_config['typical_move']}

4. **WHY IT WORKS**:
   - Positive GEX breakdown = MMs fade the move DOWN
   - Flip break triggers cascade
   - Put wall = Support level where MMs defend
   - Wins {strategy_config['win_rate']*100:.0f}% when setup is clean

5. **TIMING**:
   - Best days: {', '.join(strategy_config['best_days'])}
   - Best time: After rejection at call wall
   - Avoid: Before major news/earnings
                                    """,
                                    'reasoning': f"Positive GEX ({net_gex/1e9:.1f}B) near flip creates breakdown risk. Historical win rate: {strategy_config['win_rate']*100:.0f}%"
                                }

                    # IRON CONDOR - Range-Bound Income
                    elif strategy_name == 'IRON_CONDOR':
                        if net_gex > strategy_config['conditions']['net_gex_threshold']:
                            wall_distance_call = abs(call_wall - spot_price) / spot_price * 100
                            wall_distance_put = abs(put_wall - spot_price) / spot_price * 100

                            if wall_distance_call >= 2.0 and wall_distance_put >= 2.0:
                                confidence = 0.75

                                setup = {
                                    'symbol': symbol,
                                    'strategy': strategy_name,
                                    'confidence': confidence,
                                    'net_gex': net_gex,
                                    'spot_price': spot_price,
                                    'flip_point': flip_point,
                                    'call_wall': call_wall,
                                    'put_wall': put_wall,
                                    'entry_price': spot_price,
                                    'target_price': spot_price,  # Range bound
                                    'stop_price': None,  # Defined by strikes
                                    'risk_reward': strategy_config['risk_reward'],
                                    'expected_move': strategy_config['typical_move'],
                                    'win_rate': strategy_config['win_rate'],
                                    'money_making_plan': f"""
🎯 HOW TO MAKE MONEY WITH THIS SETUP:

1. **THE SETUP** (Current State):
   - {symbol} is in POSITIVE GEX (${net_gex/1e9:.1f}B) = RANGE BOUND
   - Price: ${spot_price:.2f}
   - Call Wall: ${call_wall:.2f} ({wall_distance_call:.1f}% away)
   - Put Wall: ${put_wall:.2f} ({wall_distance_put:.1f}% away)
   - This means: Price likely stays in range

2. **THE TRADE** (Specific Actions):
   - SELL Iron Condor with 5-10 DTE:
     * Sell ${call_wall:.2f} Call
     * Buy ${(call_wall + 5):.2f} Call (protection)
     * Sell ${put_wall:.2f} Put
     * Buy ${(put_wall - 5):.2f} Put (protection)
   - Collect: ~$0.30-0.50 per contract
   - Max Risk: $5.00 per contract
   - Position Size: Risk max 5% of account total

3. **THE PROFIT** (Exit Strategy):
   - Target: 50% of credit collected (close early!)
   - If collect $40 → close at $20 remaining value
   - Time-based: Close at 2 DTE if not at 50%
   - STOP: If price breaches wall → close immediately
   - Win Rate: {strategy_config['win_rate']*100:.0f}%!

4. **WHY IT WORKS**:
   - Positive GEX pins price in range
   - Walls are natural support/resistance
   - High win rate, steady income
   - Compound small wins = big gains

5. **RISK MANAGEMENT**:
   - Never risk > 5% per trade
   - Close at 50% profit (greed kills)
   - Don't fight wall breaches
   - Best on: {', '.join(strategy_config['best_days'])}
                                    """,
                                    'reasoning': f"Strong positive GEX ({net_gex/1e9:.1f}B) with wide walls. Perfect IC setup. Win rate: {strategy_config['win_rate']*100:.0f}%"
                                }

                    # PREMIUM SELLING - Wall Rejection Play
                    elif strategy_name == 'PREMIUM_SELLING':
                        wall_strength_call = abs(call_wall - spot_price) / spot_price * 100
                        wall_strength_put = abs(put_wall - spot_price) / spot_price * 100

                        if net_gex > 0 and (wall_strength_call < 1.5 or wall_strength_put < 1.5):
                            confidence = 0.68

                            at_call_wall = wall_strength_call < 1.5

                            setup = {
                                'symbol': symbol,
                                'strategy': strategy_name,
                                'confidence': confidence,
                                'net_gex': net_gex,
                                'spot_price': spot_price,
                                'flip_point': flip_point,
                                'call_wall': call_wall,
                                'put_wall': put_wall,
                                'entry_price': spot_price,
                                'target_price': call_wall if at_call_wall else put_wall,
                                'stop_price': None,
                                'risk_reward': strategy_config['risk_reward'],
                                'expected_move': strategy_config['typical_move'],
                                'win_rate': strategy_config['win_rate'],
                                'money_making_plan': f"""
🎯 HOW TO MAKE MONEY WITH THIS SETUP:

1. **THE SETUP** (Current State):
   - {symbol} at {'CALL' if at_call_wall else 'PUT'} WALL: ${call_wall if at_call_wall else put_wall:.2f}
   - Current Price: ${spot_price:.2f}
   - Wall Distance: {wall_strength_call if at_call_wall else wall_strength_put:.1f}%
   - This means: High probability of rejection at wall

2. **THE TRADE** (Specific Actions):
   - SELL {'CALL' if at_call_wall else 'PUT'} at ${(call_wall if at_call_wall else put_wall):.2f} strike
   - Time: 0-2 DTE (max theta decay)
   - Collect: $0.20-0.40 per contract
   - Quantity: Sell 1-2 contracts per $10K account
   - Delta: -0.30 to -0.40 (OTM but close)

3. **THE PROFIT** (Exit Strategy):
   - Target: 50-70% profit in 1 day
   - If collect $30 → close at $10 remaining
   - Time: Close before 4pm on expiration day
   - STOP: If wall breaks by >0.5% → exit immediately
   - Win Rate: {strategy_config['win_rate']*100:.0f}%

4. **WHY IT WORKS**:
   - Walls reject price {strategy_config['win_rate']*100:.0f}% of the time
   - Theta decay works for you (time = money)
   - Near expiration = max decay
   - Positive GEX = walls hold strong

5. **RISK MANAGEMENT**:
   - Only sell premium at walls
   - Max 2-3 contracts at once
   - Close winners early (don't be greedy!)
   - Best timing: {', '.join(strategy_config['best_days'])}
                                    """,
                                    'reasoning': f"Price near {'call' if at_call_wall else 'put'} wall. Premium selling setup with {strategy_config['win_rate']*100:.0f}% win rate."
                                }

                    # If setup was created, add it to results
                    if setup:
                        results.append(setup)

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

        for symbol in symbols:
            # Fetch current GEX data
            gex_data = api_client.get_net_gamma(symbol)
            net_gex = gex_data.get('net_gex', 0)
            spot_price = gex_data.get('spot_price', 0)
            flip_point = gex_data.get('flip_point', 0)
            call_wall = gex_data.get('call_wall', 0)
            put_wall = gex_data.get('put_wall', 0)

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

            # Calculate position size (conservative options estimate)
            # Assume each option contract costs ~2% of stock price
            option_price_estimate = spot_price * 0.02
            contracts_per_risk = int(max_risk / (option_price_estimate * 100)) if option_price_estimate > 0 else 1
            position_size = max(1, min(contracts_per_risk, 10))  # Cap at 10 contracts

            # Generate specific money-making instructions using market context
            money_making_plan = f"""
🎯 AI-GENERATED TRADE SETUP - {setup_type}

1. **MARKET CONTEXT** (Right Now):
   - {symbol} trading at ${spot_price:.2f}
   - Net GEX: ${net_gex/1e9:.1f}B ({  'NEGATIVE - MMs forced to hedge' if net_gex < 0 else 'POSITIVE - MMs stabilizing'})
   - Flip Point: ${flip_point:.2f} ({'ABOVE' if spot_price > flip_point else 'BELOW'} current price)
   - Call Wall: ${call_wall:.2f} | Put Wall: ${put_wall:.2f}

2. **THE TRADE** (Exact Setup):
   - Setup: {setup_type.replace('_', ' ').title()}
   - Entry: ${entry_price:.2f}
   - Target: ${target_price:.2f} ({abs(target_price-entry_price)/entry_price*100:.1f}% move)
   - Stop: ${stop_price:.2f} ({abs(stop_price-entry_price)/entry_price*100:.1f}% stop)
   - Position Size: {position_size} contracts
   - Max Risk: ${max_risk:.2f} ({risk_pct}% of account)

3. **ENTRY CRITERIA** (When to Enter):
   - IMMEDIATE: Market is in optimal regime NOW
   - Confirmation: Price action respecting {flip_point:.2f} flip point
   - Time: Best execution in first 30 min after confirmation
   - Strike: {'ATM CALL' if 'CALL' in setup_type else 'ATM PUT' if 'PUT' in setup_type else 'Strangle/Condor'} at ${entry_price:.2f}

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
    print("  - GET  /               Health check")
    print("  - GET  /docs           API documentation")
    print("  - GET  /api/gex/{symbol}              GEX data")
    print("  - GET  /api/gamma/{symbol}/intelligence   Gamma 3 views")
    print("  - POST /api/ai/analyze                AI Copilot")
    print("  - WS   /ws/market-data                Real-time updates")
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
