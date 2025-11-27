"""
AlphaGEX FastAPI Backend
Main application entry point - Professional Options Intelligence Platform
"""

import os
import sys
import asyncio
import requests
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
from config_and_database import STRATEGIES, init_database, MM_STATES
from database_adapter import get_connection
import psycopg2
import psycopg2.extras

# Import probability calculator (NEW - Phase 2 Self-Learning)
from probability_calculator import ProbabilityCalculator

# UNIFIED Data Provider (Tradier primary, Polygon fallback)
try:
    from unified_data_provider import get_data_provider, get_quote, get_price, get_vix
    UNIFIED_DATA_AVAILABLE = True
    print("✅ Backend: Unified Data Provider (Tradier) integrated")
except ImportError as e:
    UNIFIED_DATA_AVAILABLE = False
    print(f"⚠️ Backend: Unified Data Provider not available: {e}")

# Initialize database schema on startup
print("Initializing database schema...")
init_database()
print("✓ Database initialized")

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

# CORS Configuration - Restrict to specific origins for security
# In production, this limits which domains can access the API
ALLOWED_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:3001,http://127.0.0.1:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,  # Restricted to specific frontend origins
    allow_credentials=True,  # Allow credentials with specific origins
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],  # Explicit methods
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

# RSI Data Cache - Prevent Polygon.io rate limit (5 calls/min on free tier)
# Cache RSI data for 5 minutes to avoid repeated API calls
_rsi_cache = {}
_rsi_cache_ttl = 300  # 5 minutes in seconds
_rsi_cache_max_size = 100  # Maximum number of cached symbols to prevent unbounded growth

def _cleanup_rsi_cache():
    """Remove expired entries and enforce max size limit"""
    now = datetime.now()
    # Remove expired entries
    expired_keys = [
        key for key, entry in _rsi_cache.items()
        if (now - entry['timestamp']).total_seconds() > _rsi_cache_ttl
    ]
    for key in expired_keys:
        del _rsi_cache[key]

    # If still over max size, remove oldest entries
    if len(_rsi_cache) > _rsi_cache_max_size:
        # Sort by timestamp, oldest first
        sorted_entries = sorted(_rsi_cache.items(), key=lambda x: x[1]['timestamp'])
        # Remove oldest entries to get back under limit
        for key, _ in sorted_entries[:len(_rsi_cache) - _rsi_cache_max_size]:
            del _rsi_cache[key]

# ============================================================================
# Helper Functions
# ============================================================================

def validate_symbol(symbol: str) -> tuple[bool, str]:
    """
    Validate stock symbol parameter to prevent injection attacks and API errors.

    Returns:
        (is_valid, cleaned_symbol or error_message)
    """
    if not symbol:
        return False, "Symbol cannot be empty"

    # Clean and normalize
    symbol = symbol.strip().upper()

    # Check length (stock symbols are typically 1-5 characters)
    if len(symbol) > 5:
        return False, f"Symbol too long: {len(symbol)} characters (max 5)"

    # Check for valid characters (alphanumeric only)
    if not symbol.isalnum():
        return False, "Symbol must contain only alphanumeric characters"

    # Block obvious injection attempts
    blocked_patterns = ['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'DROP', 'UNION', '--', ';', '/*']
    for pattern in blocked_patterns:
        if pattern in symbol:
            return False, f"Invalid symbol: contains blocked pattern"

    return True, symbol

def fetch_vix_with_metadata(polygon_key: str = None) -> dict:
    """
    Fetch VIX with metadata - Tradier (live) or Polygon (fallback).

    Returns dict with:
    - value: VIX value (float)
    - source: 'tradier' | 'polygon' | 'default'
    - is_live: True if from real API, False if default
    - timestamp: ISO timestamp of data
    - error: Error message if fetch failed (optional)
    """
    vix_data = {
        'value': 18.0,
        'source': 'default',
        'is_live': False,
        'timestamp': datetime.now().isoformat()
    }

    # Try Tradier first (real-time)
    if UNIFIED_DATA_AVAILABLE:
        try:
            vix_value = get_vix()
            if vix_value and vix_value > 0:
                vix_data['value'] = float(vix_value)
                vix_data['source'] = 'tradier'
                vix_data['is_live'] = True
                return vix_data
        except Exception as e:
            print(f"Tradier VIX fetch failed: {e}")

    # Fallback to Polygon
    if not polygon_key:
        vix_data['error'] = 'No Polygon.io API key configured'
        return vix_data

    try:
        # Get last trading day's VIX close
        to_date = datetime.now().strftime('%Y-%m-%d')
        from_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')

        url = f"https://api.polygon.io/v2/aggs/ticker/VIX/range/1/day/{from_date}/{to_date}"
        params = {"apiKey": polygon_key, "sort": "desc", "limit": 1}

        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data.get('status') == 'OK' and data.get('results'):
                vix_data['value'] = float(data['results'][0]['c'])
                vix_data['source'] = 'polygon'
                vix_data['is_live'] = True
                if 'error' in vix_data:
                    del vix_data['error']
            else:
                vix_data['error'] = f"Polygon.io returned no VIX data: {data.get('status', 'unknown')}"
        else:
            vix_data['error'] = f"Polygon.io HTTP {response.status_code}"
    except Exception as e:
        vix_data['error'] = f"VIX fetch failed: {str(e)}"

    return vix_data

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

@app.post("/api/rate-limit-reset")
async def reset_rate_limit():
    """
    Manually reset the circuit breaker and rate limit counters
    Use this if you believe the rate limit has been lifted but circuit breaker is stuck
    """
    TradingVolatilityAPI._shared_circuit_breaker_active = False
    TradingVolatilityAPI._shared_circuit_breaker_until = 0
    TradingVolatilityAPI._shared_consecutive_rate_limit_errors = 0
    TradingVolatilityAPI._shared_api_call_count_minute = 0

    return {
        "success": True,
        "message": "Circuit breaker reset successfully",
        "new_status": {
            "circuit_breaker_active": TradingVolatilityAPI._shared_circuit_breaker_active,
            "consecutive_errors": TradingVolatilityAPI._shared_consecutive_rate_limit_errors,
            "calls_this_minute": TradingVolatilityAPI._shared_api_call_count_minute
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

    # Check Polygon.io API key
    polygon_key_configured = bool(os.getenv("POLYGON_API_KEY"))
    polygon_key_length = len(os.getenv("POLYGON_API_KEY", "")) if polygon_key_configured else 0

    # DON'T test API connectivity in health check - causes rate limits on deployment
    # Health checks should be fast and not make external API calls
    # API connectivity will be tested when endpoints are actually called

    return {
        "status": "diagnostic",
        "timestamp": datetime.now().isoformat(),
        "configuration": {
            "api_key_configured": api_key_configured,
            "api_key_source": api_key_source,
            "polygon_api_key_configured": polygon_key_configured,
            "polygon_api_key_length": polygon_key_length,
            "api_endpoint": api_client.endpoint if hasattr(api_client, 'endpoint') else "unknown"
        },
        "connectivity": {
            "note": "API connectivity tested on first actual endpoint call (not in health check)"
        },
        "cache_stats": api_client.get_api_usage_stats() if hasattr(api_client, 'get_api_usage_stats') else {}
    }

@app.get("/api/diagnostic/rsi")
async def diagnostic_rsi():
    """Diagnostic endpoint specifically for RSI data fetching"""
    import os
    import requests
    from datetime import datetime, timedelta

    polygon_key = os.getenv('POLYGON_API_KEY')

    diagnostic_result = {
        "timestamp": datetime.now().isoformat(),
        "polygon_key_configured": bool(polygon_key),
        "polygon_key_length": len(polygon_key) if polygon_key else 0,
        "polygon_key_preview": polygon_key[:8] + "..." if polygon_key and len(polygon_key) > 8 else "NOT_SET",
        "test_results": {}
    }

    if not polygon_key:
        diagnostic_result["error"] = "POLYGON_API_KEY environment variable not set"
        diagnostic_result["solution"] = "Add POLYGON_API_KEY to Render environment variables"
        return diagnostic_result

    # Test Polygon.io API with a simple request
    try:
        to_date = datetime.now().strftime('%Y-%m-%d')
        from_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')

        url = f"https://api.polygon.io/v2/aggs/ticker/SPY/range/1/day/{from_date}/{to_date}"
        params = {"apiKey": polygon_key, "sort": "desc", "limit": 5}

        response = requests.get(url, params=params, timeout=10)

        diagnostic_result["test_results"] = {
            "url": url.replace(polygon_key, "***"),
            "status_code": response.status_code,
            "response_size": len(response.text),
        }

        if response.status_code == 200:
            data = response.json()
            diagnostic_result["test_results"]["api_status"] = data.get('status')
            diagnostic_result["test_results"]["results_count"] = data.get('resultsCount', 0)
            diagnostic_result["test_results"]["success"] = True

            if data.get('results'):
                diagnostic_result["test_results"]["sample_data"] = {
                    "latest_date": datetime.fromtimestamp(data['results'][0]['t']/1000).strftime('%Y-%m-%d'),
                    "latest_close": data['results'][0]['c']
                }
        else:
            diagnostic_result["test_results"]["success"] = False
            diagnostic_result["test_results"]["error"] = response.text[:500]

            if response.status_code == 403:
                diagnostic_result["error"] = "Polygon.io API returned 403 Forbidden"
                diagnostic_result["possible_causes"] = [
                    "API key is invalid or expired",
                    "Free tier key trying to access real-time data (needs paid plan)",
                    "Rate limit exceeded"
                ]
            elif response.status_code == 401:
                diagnostic_result["error"] = "Polygon.io API returned 401 Unauthorized"
                diagnostic_result["possible_causes"] = ["API key is invalid"]

    except Exception as e:
        diagnostic_result["test_results"]["success"] = False
        diagnostic_result["test_results"]["exception"] = str(e)

    return diagnostic_result

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
    # Validate symbol parameter
    is_valid, result = validate_symbol(symbol)
    if not is_valid:
        return {"success": False, "error": result}
    symbol = result  # Use cleaned symbol

    try:

        # Use existing TradingVolatilityAPI (UNCHANGED)
        gex_data = api_client.get_net_gamma(symbol)

        # Enhanced error logging with cached data fallback
        if not gex_data or gex_data.get('error'):
            error_msg = gex_data.get('error', 'No data returned') if gex_data else 'API returned None'
            print(f"⚠️ GEX API error for {symbol}: {error_msg}")
            print(f"📊 Attempting to use cached data from database...")

            # Try to get cached data from gex_history
            try:
                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT spot_price, net_gex, flip_point, call_wall, put_wall, timestamp
                    FROM gex_history
                    WHERE symbol = %s AND timestamp > NOW() - INTERVAL '24 hours'
                    ORDER BY timestamp DESC
                    LIMIT 1
                """, (symbol,))
                cached_row = cursor.fetchone()
                conn.close()

                if cached_row:
                    print(f"✅ Using cached GEX data from {cached_row[5]}")
                    return JSONResponse({
                        "success": True,
                        "data": {
                            "symbol": symbol,
                            "spot_price": cached_row[0] or 590.0,
                            "net_gex": cached_row[1] or 0,
                            "flip_point": cached_row[2] or cached_row[0],
                            "call_wall": cached_row[3] or (cached_row[0] * 1.02 if cached_row[0] else 600),
                            "put_wall": cached_row[4] or (cached_row[0] * 0.98 if cached_row[0] else 580),
                            "vix": 15.0,
                            "mm_state": "neutral",
                            "levels": [],
                            "rsi": {},
                            "_cached": True,
                            "_cache_time": str(cached_row[5])
                        }
                    })
            except Exception as cache_err:
                print(f"❌ Failed to retrieve cached GEX data: {cache_err}")

            # No cached data available - return error
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
                    detail=f"Trading Volatility API access denied (403 Forbidden). Your API key may need to be renewed or the service may have changed authentication methods."
                )
            else:
                raise HTTPException(
                    status_code=503,
                    detail=f"GEX data not available for {symbol}: {error_msg}"
                )

        # Log successful fetch
        print(f"✅ Successfully fetched GEX data for {symbol} - spot: ${gex_data.get('spot_price', 0):.2f}, net_gex: {gex_data.get('net_gex', 0)/1e9:.2f}B")

        # CRITICAL FIX: Try to get wall data from profile (contains strike-level analysis)
        # The /gex/latest endpoint doesn't include walls, but /gex/gammaOI does
        try:
            profile = api_client.get_gex_profile(symbol)
            if profile and not profile.get('error'):
                # Merge wall data from profile into gex_data
                if profile.get('call_wall') and profile.get('call_wall') > 0:
                    gex_data['call_wall'] = profile['call_wall']
                if profile.get('put_wall') and profile.get('put_wall') > 0:
                    gex_data['put_wall'] = profile['put_wall']
                print(f"✅ Enhanced with wall data: call_wall=${profile.get('call_wall', 0):.2f}, put_wall=${profile.get('put_wall', 0):.2f}")
        except Exception as profile_err:
            # Don't fail if profile fetch fails - walls just won't be available
            print(f"⚠️ Could not fetch profile for wall data: {profile_err}")

        # Get GEX levels for support/resistance
        levels_data = api_client.get_gex_levels(symbol)

        # Get psychology data and multi-timeframe RSI for probability calculation
        psychology_data = {}
        rsi_data = {}

        # Simplified approach: Use ONLY Polygon.io for all timeframes
        import requests
        import pandas as pd
        from datetime import datetime, timedelta

        # Get Polygon.io API key
        polygon_key = os.getenv('POLYGON_API_KEY')

        # Separate try block for RSI fetching to prevent psychology errors from wiping RSI data
        use_cached_rsi = False
        try:
            # Check RSI cache first to avoid rate limits
            cache_key = f"rsi_{symbol}"
            if cache_key in _rsi_cache:
                cached_entry = _rsi_cache[cache_key]
                cache_age = (datetime.now() - cached_entry['timestamp']).total_seconds()
                if cache_age < _rsi_cache_ttl:
                    print(f"✅ Using cached RSI data for {symbol} (age: {cache_age:.0f}s, TTL: {_rsi_cache_ttl}s)")
                    rsi_data = cached_entry['data']
                    use_cached_rsi = True

            # Only fetch RSI data if not using cache
            if not use_cached_rsi:
                if not polygon_key:
                    print(f"⚠️ No Polygon.io API key - RSI calculation will fail")
                else:
                    print(f"✅ Polygon.io API key configured")

            # Calculate RSI for multiple timeframes
            def calculate_rsi(df, period=14):
                """Calculate RSI from dataframe"""
                if df is None or df.empty or len(df) < period:
                    return None
                delta = df['Close'].diff()
                gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
                # Prevent division by zero - when loss is 0, RSI is 100 (all gains)
                # Use replace to handle the Series, not simple division
                rs = gain / loss.replace(0, float('nan'))
                rsi = 100 - (100 / (1 + rs))
                # Fill NaN values (from division by zero) with 100 (all gains scenario)
                rsi = rsi.fillna(100)
                return rsi.iloc[-1] if not rsi.empty else None

            # Helper function to fetch from Polygon.io
            def fetch_polygon_data(symbol, multiplier, timespan, days_back):
                """Fetch data from Polygon.io aggregates API"""
                if not polygon_key:
                    return None

                try:
                    to_date = datetime.now().strftime('%Y-%m-%d')
                    from_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')

                    url = f"https://api.polygon.io/v2/aggs/ticker/{symbol}/range/{multiplier}/{timespan}/{from_date}/{to_date}"
                    params = {"apiKey": polygon_key, "sort": "asc"}

                    response = requests.get(url, params=params, timeout=10)

                    if response.status_code == 200:
                        data = response.json()
                        # Accept both 'OK' (paid tier) and 'DELAYED' (free tier)
                        status = data.get('status', '')
                        if status in ['OK', 'DELAYED'] and data.get('results'):
                            results = data['results']

                            # Convert to DataFrame
                            df = pd.DataFrame(results)
                            df['date'] = pd.to_datetime(df['t'], unit='ms')
                            df.set_index('date', inplace=True)
                            df = df.rename(columns={
                                'o': 'Open', 'h': 'High', 'l': 'Low',
                                'c': 'Close', 'v': 'Volume'
                            })

                            return df
                        else:
                            print(f"    ⚠️ Polygon.io status: {data.get('status')}, resultsCount: {data.get('resultsCount', 0)}")
                            return None
                    else:
                        print(f"    ⚠️ Polygon.io HTTP {response.status_code}")
                        return None
                except Exception as e:
                    print(f"    ⚠️ Polygon.io error: {e}")
                    return None

            # Fetch data for different timeframes (only if not using cache)
            if not use_cached_rsi:
                print(f"📊 Fetching multi-timeframe RSI for {symbol}...")

            # 1D RSI (already working)
            if not use_cached_rsi:
                try:
                    print(f"  🔄 Fetching 1D data from Polygon.io...")
                    df_1d = fetch_polygon_data(symbol, 1, 'day', 90)

                    if df_1d is not None and not df_1d.empty:
                        print(f"  📥 1d: Fetched {len(df_1d)} bars from Polygon.io")
                        print(f"      Date range: {df_1d.index[0]} to {df_1d.index[-1]}")
                        rsi_1d = calculate_rsi(df_1d)
                        if rsi_1d is not None:
                            rsi_data['1d'] = round(float(rsi_1d), 1)
                            print(f"  ✅ 1d RSI: {rsi_data['1d']}")
                        else:
                            rsi_data['1d'] = None
                            print(f"  ⚠️ 1d RSI: insufficient data (need 14+ bars, got {len(df_1d)})")
                    else:
                        rsi_data['1d'] = None
                        print(f"  ⚠️ 1d RSI: no data available")
                except Exception as e:
                    rsi_data['1d'] = None
                    print(f"  ❌ 1d RSI failed: {e}")

            # 4H RSI
            if not use_cached_rsi:
                try:
                    print(f"  🔄 Fetching 4H data from Polygon.io...")
                    df_4h = fetch_polygon_data(symbol, 4, 'hour', 30)

                    if df_4h is not None and not df_4h.empty:
                        print(f"  📥 4h: Fetched {len(df_4h)} bars from Polygon.io")
                        rsi_4h = calculate_rsi(df_4h)
                        if rsi_4h is not None:
                            rsi_data['4h'] = round(float(rsi_4h), 1)
                            print(f"  ✅ 4h RSI: {rsi_data['4h']}")
                        else:
                            rsi_data['4h'] = None
                            print(f"  ⚠️ 4h RSI: insufficient data")
                    else:
                        rsi_data['4h'] = None
                except Exception as e:
                    rsi_data['4h'] = None
                    print(f"  ❌ 4h RSI failed: {e}")

            # 1H RSI
            if not use_cached_rsi:
                try:
                    print(f"  🔄 Fetching 1H data from Polygon.io...")
                    df_1h = fetch_polygon_data(symbol, 1, 'hour', 14)

                    if df_1h is not None and not df_1h.empty:
                        print(f"  📥 1h: Fetched {len(df_1h)} bars from Polygon.io")
                        rsi_1h = calculate_rsi(df_1h)
                        if rsi_1h is not None:
                            rsi_data['1h'] = round(float(rsi_1h), 1)
                            print(f"  ✅ 1h RSI: {rsi_data['1h']}")
                        else:
                            rsi_data['1h'] = None
                            print(f"  ⚠️ 1h RSI: insufficient data")
                    else:
                        rsi_data['1h'] = None
                except Exception as e:
                    rsi_data['1h'] = None
                    print(f"  ❌ 1h RSI failed: {e}")

            # 15M RSI
            if not use_cached_rsi:
                try:
                    print(f"  🔄 Fetching 15M data from Polygon.io...")
                    df_15m = fetch_polygon_data(symbol, 15, 'minute', 7)

                    if df_15m is not None and not df_15m.empty:
                        print(f"  📥 15m: Fetched {len(df_15m)} bars from Polygon.io")
                        rsi_15m = calculate_rsi(df_15m)
                        if rsi_15m is not None:
                            rsi_data['15m'] = round(float(rsi_15m), 1)
                            print(f"  ✅ 15m RSI: {rsi_data['15m']}")
                        else:
                            rsi_data['15m'] = None
                            print(f"  ⚠️ 15m RSI: insufficient data")
                    else:
                        rsi_data['15m'] = None
                except Exception as e:
                    rsi_data['15m'] = None
                    print(f"  ❌ 15m RSI failed: {e}")

            # 5M RSI
            if not use_cached_rsi:
                try:
                    print(f"  🔄 Fetching 5M data from Polygon.io...")
                    df_5m = fetch_polygon_data(symbol, 5, 'minute', 3)

                    if df_5m is not None and not df_5m.empty:
                        print(f"  📥 5m: Fetched {len(df_5m)} bars from Polygon.io")
                        rsi_5m = calculate_rsi(df_5m)
                        if rsi_5m is not None:
                            rsi_data['5m'] = round(float(rsi_5m), 1)
                            print(f"  ✅ 5m RSI: {rsi_data['5m']}")
                        else:
                            rsi_data['5m'] = None
                            print(f"  ⚠️ 5m RSI: insufficient data")
                    else:
                        rsi_data['5m'] = None
                except Exception as e:
                    rsi_data['5m'] = None
                    print(f"  ❌ 5m RSI failed: {e}")

                print(f"📊 RSI Summary: {sum(1 for v in rsi_data.values() if v is not None)}/5 timeframes successful")

                # Cache the RSI data if we got any valid values
                if rsi_data and any(v is not None for v in rsi_data.values()):
                    # Cleanup old cache entries to prevent unbounded growth
                    _cleanup_rsi_cache()
                    _rsi_cache[cache_key] = {
                        'data': rsi_data.copy(),
                        'timestamp': datetime.now()
                    }
                    print(f"💾 Cached RSI data for {symbol} (TTL: {_rsi_cache_ttl}s, cache size: {len(_rsi_cache)})")

        except Exception as e:
            # Only reset RSI if the RSI fetch itself failed
            error_msg = str(e)
            print(f"⚠️  Could not fetch RSI data for {symbol}: {error_msg}")
            rsi_data = {}
            print(f"📊 RSI Summary: 0/5 timeframes successful")

        # Calculate psychology state (separate try block so errors here don't affect RSI)
        try:
            # Use 1d RSI for psychology state (most reliable)
            # Note: .get() returns None if key exists with None value, so we need explicit check
            current_rsi = rsi_data.get('1d')
            if current_rsi is None:
                current_rsi = 50

            # Determine psychology state based on RSI
            if current_rsi > 70:
                psychology_data = {
                    'fomo_level': min(100, (current_rsi - 50) * 2),
                    'fear_level': max(0, (50 - current_rsi) * 2),
                    'state': 'FOMO' if current_rsi > 80 else 'MODERATE_FOMO',
                    'rsi': current_rsi
                }
            elif current_rsi < 30:
                psychology_data = {
                    'fomo_level': max(0, (current_rsi - 50) * 2),
                    'fear_level': min(100, (50 - current_rsi) * 2),
                    'state': 'FEAR' if current_rsi < 20 else 'MODERATE_FEAR',
                    'rsi': current_rsi
                }
            else:
                psychology_data = {
                    'fomo_level': 50,
                    'fear_level': 50,
                    'state': 'BALANCED',
                    'rsi': current_rsi
                }
        except Exception as e:
            # Psychology calculation error - use defaults but DON'T reset RSI data
            error_msg = str(e)
            print(f"⚠️  Could not calculate psychology state for {symbol}: {error_msg}")
            # Return default psychology values (RSI data remains intact)
            psychology_data = {'fomo_level': 50, 'fear_level': 50, 'state': 'BALANCED', 'rsi': 50}

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

        # Get VIX for volatility context using Polygon.io with metadata
        if symbol == 'VIX':
            vix_metadata = {
                'value': spot_price,
                'source': 'symbol_price',
                'is_live': True,
                'timestamp': datetime.now().isoformat()
            }
        else:
            print(f"  🔄 Fetching VIX from Polygon.io...")
            vix_metadata = fetch_vix_with_metadata(polygon_key)
            if vix_metadata.get('is_live'):
                print(f"  ✅ VIX from Polygon.io: {vix_metadata['value']}")
            else:
                error = vix_metadata.get('error', 'Unknown reason')
                print(f"  ⚠️ Using default VIX ({vix_metadata['value']}): {error}")

        vix_level = vix_metadata['value']

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
            "vix": vix_level,
            # NEW: Add multi-timeframe RSI (return null if no data fetched)
            "rsi": rsi_data if rsi_data and any(v is not None for v in rsi_data.values()) else None
        }

        return {
            "success": True,
            "symbol": symbol,
            "data": enhanced_data,
            "vix_metadata": vix_metadata,  # NEW: Let frontend know if VIX is live or default
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

    Returns strike-level data if available, otherwise returns empty array
    (Frontend can still display aggregate GEX data from /api/gex/{symbol})

    Args:
        symbol: Stock symbol

    Returns:
        Array of GEX levels (may be empty if gammaOI endpoint is rate limited)
    """
    try:
        symbol = symbol.upper()

        # Try to get strike-level data from gammaOI endpoint
        # This endpoint has stricter rate limits than /gex/latest
        profile = api_client.get_gex_profile(symbol)

        # If gammaOI is rate limited or unavailable, return empty array
        # Frontend will still show aggregate data from /api/gex/{symbol}
        if not profile:
            print(f"⚠️ No profile data for {symbol} - likely rate limited or not available in subscription")
            return {
                "success": True,
                "symbol": symbol,
                "levels": [],
                "data": [],
                "message": "Strike-level data unavailable (gammaOI endpoint rate limited or not included in subscription)",
                "timestamp": datetime.now().isoformat()
            }

        # Check for error from API
        if profile.get('error'):
            error_msg = profile.get('error')
            print(f"⚠️ GEX profile error for {symbol}: {error_msg}")

            # Return empty array instead of failing
            # Frontend can still display aggregate GEX metrics
            return {
                "success": True,
                "symbol": symbol,
                "levels": [],
                "data": [],
                "message": f"Strike-level data unavailable: {error_msg}",
                "timestamp": datetime.now().isoformat()
            }

        # Extract strikes data from profile
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

        # Try to get detailed profile for strike-level gamma data
        # This endpoint has strict rate limits (2/min during trading hours)
        # Gracefully degrade if not available
        profile = None
        try:
            profile = api_client.get_gex_profile(symbol)
            # If rate limited, profile will be empty dict or have error key
            if profile and profile.get('error'):
                print(f"⚠️ gammaOI unavailable for gamma intelligence: {profile.get('error')}")
                profile = None
        except Exception as e:
            print(f"⚠️ Could not fetch strike-level data for gamma intelligence: {e}")
            profile = None

        # Calculate total call and put gamma from strike-level data (if available)
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

        # Calculate derived metrics (real values, not estimates)
        risk_reversal = (total_call_gamma - total_put_gamma) / total_gamma if total_gamma > 0 else 0
        skew_index = gamma_exposure_ratio

        # NOTE: Vanna and Charm require strike-level option data and IV surface
        # These would need to be calculated from actual option Greeks if available
        # For now, mark as unavailable rather than showing fake estimates
        vanna_exposure = None  # Requires proper Greeks calculation
        charm_decay = None     # Requires proper Greeks calculation

        # Determine market regime
        if net_gex > 0:
            regime_state = "Positive Gamma" if net_gex > 1e9 else "Neutral"
            volatility = "Low" if net_gex > 1e9 else "Moderate"
        else:
            regime_state = "Negative Gamma"
            volatility = "High"

        trend = "Bullish" if total_call_gamma > total_put_gamma else "Bearish" if total_put_gamma > total_call_gamma else "Neutral"

        # DYNAMIC MM STATE: Calculate confidence based on actual GEX data
        from strategy_stats import calculate_mm_confidence, get_mm_states

        # Get flip point for confidence calculation
        flip_point = profile.get('flip_point', 0) if profile else 0

        # Calculate MM state and confidence dynamically
        mm_result = calculate_mm_confidence(net_gex, spot_price, flip_point)
        mm_state_name = mm_result['state']
        mm_confidence = mm_result['confidence']

        # Get MM state configuration (thresholds are now adaptive)
        mm_states_config = get_mm_states()
        mm_state = mm_states_config.get(mm_state_name, mm_states_config['NEUTRAL'])

        # Override hardcoded confidence with calculated confidence
        mm_state['confidence'] = mm_confidence

        print(f"📊 MM State: {mm_state_name} (confidence: {mm_confidence:.1f}%, calculated dynamically)")

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


@app.get("/api/gamma/{symbol}/probabilities")
async def get_gamma_probabilities(symbol: str, vix: float = 20, account_size: float = 10000):
    """
    Get actionable probability analysis for gamma-based trading - COMPLETE MONEY-MAKING SYSTEM

    Returns ALL actionable metrics:
    - Position sizing (Kelly Criterion)
    - Entry/exit prices
    - Risk/reward in dollars
    - Strike rankings
    - Optimal holding period
    - Historical setups
    - Regime stability
    """
    try:
        symbol = symbol.upper()
        print(f"=== PROBABILITY ANALYSIS REQUEST: {symbol}, VIX: {vix}, Account: ${account_size} ===")

        # Import probability engine
        from probability_engine import ProbabilityEngine

        # Get gamma intelligence data first
        gex_data = api_client.get_net_gamma(symbol)

        if not gex_data or gex_data.get('error'):
            raise HTTPException(
                status_code=404,
                detail=f"GEX data not available for {symbol}"
            )

        # Get profile for strike data
        profile = None
        try:
            profile = api_client.get_gex_profile(symbol)
            if profile and profile.get('error'):
                profile = None
        except (KeyError, TypeError, AttributeError, Exception) as e:
            # Failed to fetch GEX profile, continue without it
            profile = None

        # Extract key metrics with validation
        # Don't use 0 as default - it masks missing data
        if 'net_gex' not in gex_data:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid GEX data: missing 'net_gex' field"
            )
        if 'spot_price' not in gex_data:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid GEX data: missing 'spot_price' field"
            )

        net_gex = gex_data['net_gex']
        spot_price = gex_data['spot_price']

        # Validate values are numeric and reasonable
        if not isinstance(net_gex, (int, float)):
            raise HTTPException(
                status_code=422,
                detail=f"Invalid GEX data: net_gex is not numeric"
            )
        if not isinstance(spot_price, (int, float)) or spot_price <= 0:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid GEX data: spot_price must be positive number"
            )
        flip_point = profile.get('flip_point') if profile else None
        call_wall = profile.get('call_wall') if profile else None
        put_wall = profile.get('put_wall') if profile else None

        # Get strikes for probability calculation
        strikes = []
        if profile and profile.get('strikes'):
            strikes = [s['strike'] for s in profile['strikes']]
        else:
            # Generate estimated strikes around spot
            for i in range(-5, 6):
                strikes.append(spot_price + (i * spot_price * 0.01))

        # Determine MM state
        from strategy_stats import calculate_mm_confidence
        mm_result = calculate_mm_confidence(net_gex, spot_price, flip_point or spot_price)
        mm_state = mm_result['state']

        # Initialize probability engine
        prob_engine = ProbabilityEngine()

        # Use enhanced calculator for realistic option pricing
        from enhanced_probability_calculator import EnhancedProbabilityCalculator
        price_calc = EnhancedProbabilityCalculator()

        # Calculate realistic option price based on MM state and VIX
        if mm_state == 'PANICKING':
            # ATM call for panic buying
            option_data = price_calc.calculate_option_for_setup(
                spot_price=spot_price,
                strike_distance_pct=0.0,  # ATM
                days_to_expiry=3,
                vix=vix,
                option_type='call'
            )
        elif mm_state == 'TRAPPED':
            # Slightly OTM call (0.4 delta)
            option_data = price_calc.calculate_option_for_setup(
                spot_price=spot_price,
                strike_distance_pct=0.01,  # 1% OTM ≈ 0.4 delta
                days_to_expiry=3,
                vix=vix,
                option_type='call'
            )
        else:
            # ATM for other states
            option_data = price_calc.calculate_option_for_setup(
                spot_price=spot_price,
                strike_distance_pct=0.0,
                days_to_expiry=3,
                vix=vix,
                option_type='call'
            )

        option_price = option_data['mid']  # Use mid price for calculations

        # Calculate complete probability analysis with NEW metrics
        analysis = prob_engine.get_complete_analysis(
            mm_state=mm_state,
            spot_price=spot_price,
            net_gex=net_gex,
            flip_point=flip_point,
            call_wall=call_wall,
            put_wall=put_wall,
            strikes=strikes,
            account_size=account_size,
            option_price=option_price
        )

        # Convert to dict for JSON response - INCLUDING ALL NEW DATA
        response_data = {
            "best_setup": {
                "setup_type": analysis.best_setup.setup_type,
                "mm_state": analysis.best_setup.mm_state,
                "strike_distance_pct": analysis.best_setup.strike_distance_pct,
                "win_rate": analysis.best_setup.win_rate,
                "avg_win": analysis.best_setup.avg_win,
                "avg_loss": analysis.best_setup.avg_loss,
                "expected_value": analysis.best_setup.expected_value,
                "sample_size": analysis.best_setup.sample_size,
                "confidence_score": analysis.best_setup.confidence_score,
                "entry_price_low": analysis.best_setup.entry_price_low,
                "entry_price_high": analysis.best_setup.entry_price_high,
                "profit_target": analysis.best_setup.profit_target,
                "stop_loss": analysis.best_setup.stop_loss,
                "optimal_hold_days": analysis.best_setup.optimal_hold_days
            } if analysis.best_setup else None,
            "strike_probabilities": analysis.strike_probabilities,
            "wall_probabilities": {
                "call_wall": {
                    "price": call_wall,
                    "prob_1d": analysis.call_wall_prob_1d,
                    "prob_3d": analysis.call_wall_prob_3d,
                    "prob_5d": analysis.call_wall_prob_5d
                } if call_wall else None,
                "put_wall": {
                    "price": put_wall,
                    "prob_1d": analysis.put_wall_prob_1d,
                    "prob_3d": analysis.put_wall_prob_3d,
                    "prob_5d": analysis.put_wall_prob_5d
                } if put_wall else None
            },
            "regime_edge": {
                "current_win_rate": analysis.current_regime_win_rate,
                "baseline_win_rate": analysis.baseline_win_rate,
                "edge_percentage": analysis.edge_percentage,
                "regime_stats": analysis.regime_stats
            },
            # NEW: Position sizing
            "position_sizing": {
                "kelly_pct": analysis.position_sizing.kelly_pct,
                "conservative_pct": analysis.position_sizing.conservative_pct,
                "aggressive_pct": analysis.position_sizing.aggressive_pct,
                "recommended_contracts": analysis.position_sizing.recommended_contracts,
                "max_contracts": analysis.position_sizing.max_contracts,
                "account_risk_pct": analysis.position_sizing.account_risk_pct
            } if analysis.position_sizing else None,
            # NEW: Risk analysis
            "risk_analysis": {
                "total_cost": analysis.risk_analysis.total_cost,
                "best_case_profit": analysis.risk_analysis.best_case_profit,
                "worst_case_loss": analysis.risk_analysis.worst_case_loss,
                "expected_value_dollars": analysis.risk_analysis.expected_value_dollars,
                "roi_percent": analysis.risk_analysis.roi_percent,
                "max_account_risk_pct": analysis.risk_analysis.max_account_risk_pct
            } if analysis.risk_analysis else None,
            # NEW: Holding period
            "holding_period": {
                "day_1_win_rate": analysis.holding_period.day_1_win_rate,
                "day_2_win_rate": analysis.holding_period.day_2_win_rate,
                "day_3_win_rate": analysis.holding_period.day_3_win_rate,
                "day_4_win_rate": analysis.holding_period.day_4_win_rate,
                "day_5_win_rate": analysis.holding_period.day_5_win_rate,
                "optimal_day": analysis.holding_period.optimal_day
            } if analysis.holding_period else None,
            # NEW: Historical setups
            "historical_setups": [
                {
                    "date": setup.date,
                    "outcome": setup.outcome,
                    "pnl_dollars": setup.pnl_dollars,
                    "pnl_percent": setup.pnl_percent,
                    "hold_days": setup.hold_days
                }
                for setup in analysis.historical_setups
            ] if analysis.historical_setups else [],
            # NEW: Regime stability
            "regime_stability": {
                "current_state": analysis.regime_stability.current_state,
                "stay_probability": analysis.regime_stability.stay_probability,
                "shift_probabilities": analysis.regime_stability.shift_probabilities,
                "alert_threshold": analysis.regime_stability.alert_threshold,
                "recommendation": analysis.regime_stability.recommendation
            } if analysis.regime_stability else None,
            # Additional context
            "spot_price": spot_price,
            "option_price": option_price,
            "account_size": account_size,
            # NEW: Enhanced option pricing data with Greeks
            "enhanced_pricing": {
                "bid": option_data.get('bid'),
                "ask": option_data.get('ask'),
                "mid": option_data.get('mid'),
                "spread": option_data.get('estimated_spread'),
                "spread_pct": option_data.get('estimated_spread_pct'),
                "delta": option_data.get('delta'),
                "gamma": option_data.get('gamma'),
                "theta": option_data.get('theta'),
                "vega": option_data.get('vega'),
                "iv_used": option_data.get('iv_used'),
                "strike": option_data.get('strike'),
                "dte": option_data.get('dte'),
                "pricing_method": "ENHANCED_ESTIMATE",
                "note": "Black-Scholes with VIX-based IV and volatility smile. Verify with real market data before trading."
            }
        }

        print(f"✅ COMPLETE probability analysis for {symbol}")
        print(f"   Setup: {response_data['best_setup']['setup_type'] if response_data['best_setup'] else 'None'}")
        print(f"   Win Rate: {response_data['best_setup']['win_rate']*100:.1f}%" if response_data['best_setup'] else "   No edge")
        print(f"   Position: {response_data['position_sizing']['recommended_contracts']} contracts" if response_data['position_sizing'] else "")
        print(f"   Expected Value: ${response_data['risk_analysis']['expected_value_dollars']:.0f}" if response_data['risk_analysis'] else "")

        return {
            "success": True,
            "symbol": symbol,
            "data": response_data,
            "timestamp": datetime.now().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error in probability analysis: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/gamma/{symbol}/expiration")
async def get_gamma_expiration(symbol: str, vix: float = 0):
    """
    Get gamma expiration intelligence for 0DTE trading

    Returns weekly gamma decay patterns, daily risk levels, trading strategies,
    and SPY directional prediction with probability
    """
    try:
        symbol = symbol.upper()
        print(f"=== GAMMA EXPIRATION REQUEST: {symbol}, VIX: {vix} ===")

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

        # Get VIX if not provided - use flexible price data fetcher with intelligent fallback
        current_vix = vix
        last_known_vix = None  # Could be retrieved from cache/database in future

        if current_vix == 0:
            try:
                # Import flexible price data fetcher (multi-source: yfinance, alpha vantage, polygon, twelve data)
                import sys
                from pathlib import Path
                parent_dir = Path(__file__).parent.parent
                if str(parent_dir) not in sys.path:
                    sys.path.insert(0, str(parent_dir))

                from flexible_price_data import get_current_price
                from config import get_vix_fallback

                vix_price = get_current_price('^VIX')
                if vix_price and vix_price > 0:
                    current_vix = vix_price
                    print(f"✅ VIX fetched from flexible source: {current_vix:.2f}")
                else:
                    # Use intelligent fallback (historical average instead of arbitrary 20.0)
                    current_vix = get_vix_fallback(last_known_vix)
                    print(f"⚠️ VIX fetch failed - using fallback: {current_vix:.2f} (historical average)")
            except Exception as e:
                from config import get_vix_fallback
                current_vix = get_vix_fallback(last_known_vix)
                print(f"⚠️ Could not fetch VIX: {e}")
                print(f"   Using fallback: {current_vix:.2f} (historical average)")

        # Get current gamma from API first (needed for adaptive pattern selection)
        net_gex = gex_data.get('net_gex', 0)
        spot_price = gex_data.get('spot_price', 0)
        flip_point = gex_data.get('flip_point', 0)
        call_wall = gex_data.get('call_wall')
        put_wall = gex_data.get('put_wall')

        # Fallback: If walls not available from get_net_gamma, try get_gex_profile
        if (call_wall is None or put_wall is None or call_wall == 0 or put_wall == 0):
            print(f"⚠️ Walls missing from get_net_gamma, fetching from get_gex_profile...")
            try:
                profile_data = api_client.get_gex_profile(symbol)
                if profile_data and 'call_wall' in profile_data:
                    if call_wall is None or call_wall == 0:
                        call_wall = profile_data.get('call_wall', 0)
                    if put_wall is None or put_wall == 0:
                        put_wall = profile_data.get('put_wall', 0)
                    print(f"✅ Fetched walls from profile: Call ${call_wall}, Put ${put_wall}")
            except Exception as e:
                print(f"⚠️ Could not fetch walls from profile: {e}")
                call_wall = call_wall or 0
                put_wall = put_wall or 0

        # Ensure walls are numbers (not None)
        call_wall = call_wall if call_wall is not None else 0
        put_wall = put_wall if put_wall is not None else 0

        # Get adaptive weekly gamma pattern based on VIX and GEX conditions
        from config import get_gamma_decay_pattern
        weekly_gamma_pattern = get_gamma_decay_pattern(vix=current_vix, net_gex=net_gex)

        # Log which pattern was selected
        if net_gex < -2e9:
            pattern_name = "FRONT_LOADED (high negative GEX)"
        elif current_vix > 30:
            pattern_name = "FRONT_LOADED (high VIX)"
        elif current_vix < 15:
            pattern_name = "BACK_LOADED (low VIX)"
        else:
            pattern_name = "BALANCED (normal conditions)"
        print(f"📊 Selected gamma decay pattern: {pattern_name}")

        # Estimate total weekly gamma (reverse calculate from current day)
        current_day_pct = weekly_gamma_pattern.get(day_num, 0.5)
        estimated_monday_gamma = abs(net_gex) / current_day_pct if current_day_pct > 0 else abs(net_gex)

        # Calculate weekly gamma for each day
        # Calculate total decay percentage dynamically
        total_decay_pct = int((1.0 - weekly_gamma_pattern[4]) * 100)  # % decayed by Friday

        weekly_gamma = {
            'monday': estimated_monday_gamma * weekly_gamma_pattern[0],
            'tuesday': estimated_monday_gamma * weekly_gamma_pattern[1],
            'wednesday': estimated_monday_gamma * weekly_gamma_pattern[2],
            'thursday': estimated_monday_gamma * weekly_gamma_pattern[3],
            'friday': estimated_monday_gamma * weekly_gamma_pattern[4],
            'total_decay_pct': total_decay_pct,
            'decay_pattern': pattern_name.split('(')[0].strip()  # Extract pattern type
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

        # =================================================================
        # DIRECTIONAL PREDICTION - SPY Up/Down/Sideways for the Day
        # =================================================================

        directional_prediction = None

        # Only calculate prediction if we have required data
        # Use 'is not None' to allow for 0 values (flip_point could theoretically be 0)
        if spot_price is not None and spot_price > 0 and flip_point is not None:
            # Import configuration
            from config import (
                DirectionalPredictionConfig as DPC,
                VIXConfig,
                get_gex_thresholds
            )

            # Get adaptive GEX thresholds (could use historical average if available)
            # For now, use fixed thresholds as fallback
            gex_thresholds = get_gex_thresholds(symbol, avg_gex=None)

            # Calculate directional factors
            spot_vs_flip_pct = ((spot_price - flip_point) / flip_point * 100) if flip_point else 0
            distance_to_call_wall = ((call_wall - spot_price) / spot_price * 100) if call_wall and spot_price else 999
            distance_to_put_wall = ((spot_price - put_wall) / spot_price * 100) if put_wall and spot_price else 999

            # Directional scoring (0-100)
            bullish_score = DPC.NEUTRAL_SCORE  # Start neutral (from config)
            confidence_factors = []

            # Factor 1: GEX Regime (configurable weight)
            if net_gex < gex_thresholds['moderate_negative']:  # Short gamma (amplification)
                if spot_price > flip_point:
                    bullish_score += DPC.GEX_REGIME_STRONG_INFLUENCE
                    confidence_factors.append("Short gamma + above flip = upside momentum")
                else:
                    bullish_score -= DPC.GEX_REGIME_STRONG_INFLUENCE
                    confidence_factors.append("Short gamma + below flip = downside risk")
            elif net_gex > gex_thresholds['moderate_positive']:  # Long gamma (dampening)
                # Range-bound expectation
                if spot_vs_flip_pct > 1:
                    bullish_score += DPC.GEX_REGIME_MILD_INFLUENCE
                    confidence_factors.append("Long gamma + above flip = mild upward pull")
                elif spot_vs_flip_pct < -1:
                    bullish_score -= DPC.GEX_REGIME_MILD_INFLUENCE
                    confidence_factors.append("Long gamma + below flip = mild downward pull")
                else:
                    confidence_factors.append("Long gamma near flip = range-bound likely")

            # Factor 2: Proximity to Walls (configurable weight)
            if distance_to_call_wall < DPC.WALL_PROXIMITY_THRESHOLD:  # Configurable threshold
                bullish_score -= DPC.WALL_INFLUENCE
                confidence_factors.append(f"Near call wall ${call_wall:.0f} = resistance")
            elif distance_to_put_wall < DPC.WALL_PROXIMITY_THRESHOLD:
                bullish_score += DPC.WALL_INFLUENCE
                confidence_factors.append(f"Near put wall ${put_wall:.0f} = support")

            # Factor 3: VIX Regime (configurable weight)
            if current_vix > VIXConfig.ELEVATED_VIX_THRESHOLD:  # Elevated volatility
                confidence_factors.append(f"VIX {current_vix:.1f} = elevated volatility")
                bullish_score = DPC.NEUTRAL_SCORE + (bullish_score - DPC.NEUTRAL_SCORE) * DPC.VIX_HIGH_DAMPENING
            elif current_vix < VIXConfig.LOW_VIX_THRESHOLD:  # Low volatility
                confidence_factors.append(f"VIX {current_vix:.1f} = low volatility favors range")
                bullish_score = DPC.NEUTRAL_SCORE + (bullish_score - DPC.NEUTRAL_SCORE) * DPC.VIX_LOW_DAMPENING
            else:
                confidence_factors.append(f"VIX {current_vix:.1f} = moderate volatility")

            # Factor 4: Day of Week (configurable weight)
            if day_name in ['Monday', 'Tuesday']:
                confidence_factors.append(f"{day_name} = high gamma, range-bound bias")
                bullish_score = DPC.NEUTRAL_SCORE + (bullish_score - DPC.NEUTRAL_SCORE) * DPC.DAY_OF_WEEK_DAMPENING
            elif day_name == 'Friday':
                confidence_factors.append(f"Friday = low gamma, more volatile")

            # Determine direction and confidence (using configurable thresholds)
            if bullish_score >= DPC.UPWARD_THRESHOLD:
                direction = "UPWARD"
                direction_emoji = "📈"
                probability = int(bullish_score)
                expected_move = "Expect push toward call wall or breakout higher"
            elif bullish_score <= DPC.DOWNWARD_THRESHOLD:
                direction = "DOWNWARD"
                direction_emoji = "📉"
                probability = int(100 - bullish_score)
                expected_move = "Expect push toward put wall or breakdown lower"
            else:
                direction = "SIDEWAYS"
                direction_emoji = "↔️"
                probability = int(100 - abs(bullish_score - 50) * 2)
                expected_move = f"Expect range between ${put_wall:.0f} - ${call_wall:.0f}" if put_wall and call_wall else "Range-bound expected"

            # Calculate expected range
            if put_wall and call_wall:
                range_width = ((call_wall - put_wall) / spot_price * 100)
                range_str = f"${put_wall:.0f} - ${call_wall:.0f}"
                range_pct = f"{range_width:.1f}%"
            else:
                range_str = "N/A"
                range_pct = "N/A"

            directional_prediction = {
                'direction': direction,
                'direction_emoji': direction_emoji,
                'probability': probability,
                'bullish_score': round(bullish_score, 1),
                'expected_move': expected_move,
                'expected_range': range_str,
                'range_width_pct': range_pct,
                'spot_vs_flip_pct': round(spot_vs_flip_pct, 2),
                'distance_to_call_wall_pct': round(distance_to_call_wall, 2) if distance_to_call_wall < 999 else None,
                'distance_to_put_wall_pct': round(distance_to_put_wall, 2) if distance_to_put_wall < 999 else None,
                'key_factors': confidence_factors[:4],  # Top 4 factors
                'vix': round(current_vix, 2)
            }

            print(f"✅ Directional prediction: {direction} {probability}%")

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
            'net_gex': net_gex,
            'call_wall': call_wall,
            'put_wall': put_wall,
            'directional_prediction': directional_prediction
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


@app.get("/api/gamma/{symbol}/expiration-waterfall")
async def get_gamma_expiration_waterfall(symbol: str):
    """
    Get gamma expiration data formatted for waterfall visualization

    Returns strike-by-strike gamma breakdown by expiration date
    showing how gamma decays day-by-day across the timeline

    Args:
        symbol: Stock symbol (e.g., 'SPY')

    Returns:
        {
            "expirations": List[dict],  # Expiration-level data
            "strikes_by_expiration": dict,  # Strike-level data per expiration
            "current_price": float,
            "net_gex": float,
            "summary": dict
        }
    """
    try:
        symbol = symbol.upper()
        print(f"=== GAMMA EXPIRATION WATERFALL REQUEST: {symbol} ===")

        # Use gamma expiration builder
        import sys
        from pathlib import Path
        parent_dir = Path(__file__).parent.parent
        if str(parent_dir) not in sys.path:
            sys.path.insert(0, str(parent_dir))

        from gamma_expiration_builder import build_gamma_with_expirations

        # Build complete gamma data with expiration breakdown
        gamma_data = build_gamma_with_expirations(symbol, use_tv_api=True)

        if not gamma_data or not gamma_data.get('expirations'):
            return {
                "success": False,
                "error": "No expiration data available",
                "expirations": [],
                "strikes_by_expiration": {},
                "current_price": 0,
                "net_gex": 0,
                "summary": {}
            }

        # Format expirations for waterfall
        expirations = []
        strikes_by_expiration = {}

        for exp in gamma_data['expirations']:
            exp_date_str = exp['expiration_date'].isoformat()

            # Expiration-level data
            expirations.append({
                'expiration_date': exp_date_str,
                'dte': exp['dte'],
                'expiration_type': exp['expiration_type'],
                'total_gamma_expiring': abs(exp['total_call_gamma']) + abs(exp['total_put_gamma']),
                'net_gamma': exp['net_gamma'],
                'strikes_count': len(exp['call_strikes']) + len(exp['put_strikes'])
            })

            # Strike-level data
            strikes = {}

            # Process call strikes
            for strike_data in exp['call_strikes']:
                strike = strike_data['strike']
                if strike not in strikes:
                    strikes[strike] = {
                        'strike': strike,
                        'call_gamma': 0,
                        'put_gamma': 0,
                        'total_gamma': 0,
                        'distance_pct': (strike - gamma_data['spot_price']) / gamma_data['spot_price'] * 100 if gamma_data['spot_price'] > 0 else 0
                    }
                strikes[strike]['call_gamma'] = abs(strike_data['gamma_exposure'])
                strikes[strike]['total_gamma'] += abs(strike_data['gamma_exposure'])

            # Process put strikes
            for strike_data in exp['put_strikes']:
                strike = strike_data['strike']
                if strike not in strikes:
                    strikes[strike] = {
                        'strike': strike,
                        'call_gamma': 0,
                        'put_gamma': 0,
                        'total_gamma': 0,
                        'distance_pct': (strike - gamma_data['spot_price']) / gamma_data['spot_price'] * 100 if gamma_data['spot_price'] > 0 else 0
                    }
                strikes[strike]['put_gamma'] = abs(strike_data['gamma_exposure'])
                strikes[strike]['total_gamma'] += abs(strike_data['gamma_exposure'])

            # Sort strikes by total gamma (top 20 per expiration)
            sorted_strikes = sorted(strikes.values(), key=lambda x: x['total_gamma'], reverse=True)[:20]
            strikes_by_expiration[exp_date_str] = sorted_strikes

        # Calculate summary statistics
        total_gamma_next_7d = sum(
            e['total_gamma_expiring']
            for e in expirations
            if e['dte'] <= 7
        )

        total_gamma_next_30d = sum(
            e['total_gamma_expiring']
            for e in expirations
            if e['dte'] <= 30
        )

        # Find major expiration (largest gamma)
        major_exp = max(expirations, key=lambda x: x['total_gamma_expiring']) if expirations else None

        summary = {
            'total_expirations': len(expirations),
            'total_gamma_next_7d': total_gamma_next_7d,
            'total_gamma_next_30d': total_gamma_next_30d,
            'major_expiration': major_exp['expiration_date'] if major_exp else None,
            'major_expiration_gamma': major_exp['total_gamma_expiring'] if major_exp else 0
        }

        print(f"✅ Waterfall data generated: {len(expirations)} expirations")

        return {
            "success": True,
            "symbol": symbol,
            "expirations": expirations,
            "strikes_by_expiration": strikes_by_expiration,
            "current_price": gamma_data['spot_price'],
            "net_gex": gamma_data['net_gex'],
            "summary": summary,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        print(f"❌ Error generating waterfall data: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/gamma/{symbol}/history")
async def get_gamma_history(symbol: str, days: int = 90):
    """
    Get historical gamma exposure data for trend analysis

    Args:
        symbol: Stock symbol
        days: Number of days of history to fetch (default 90)

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
                "price": float(entry.get('price') or 0),
                "net_gex": float(entry.get('skew_adjusted_gex') or 0),
                "flip_point": float(entry.get('gex_flip_price') or 0),
                "implied_volatility": float(entry.get('implied_volatility') or 0),
                "put_call_ratio": float(entry.get('put_call_ratio_open_interest') or 0)
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
# Strategy Optimizer Endpoints (AI-Powered)
# ============================================================================

@app.get("/api/optimizer/analyze/{strategy_name}")
async def optimize_strategy(strategy_name: str):
    """
    AI-powered strategy optimization with dynamic stats integration
    
    Analyzes strategy performance and provides specific optimization recommendations
    Uses live win rates from auto-updated backtest results
    
    Args:
        strategy_name: Name of strategy to optimize (e.g., "BULLISH_CALL_SPREAD")
        
    Returns:
        AI analysis with specific, actionable recommendations
    """
    try:
        import os
        
        api_key = os.getenv('ANTHROPIC_API_KEY') or os.getenv('CLAUDE_API_KEY')
        if not api_key:
            raise HTTPException(
                status_code=500,
                detail="ANTHROPIC_API_KEY not set. Configure API key to use optimizer."
            )
        
        from ai_strategy_optimizer import StrategyOptimizerAgent
        
        optimizer = StrategyOptimizerAgent(anthropic_api_key=api_key)
        
        # Use dynamic stats integration
        result = optimizer.optimize_with_dynamic_stats(strategy_name=strategy_name)
        
        return {
            "success": True,
            "strategy": strategy_name,
            "optimization": result,
            "timestamp": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except ImportError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Optimizer dependencies not installed: {str(e)}. Run: pip install langchain-anthropic"
        )
    except Exception as e:
        print(f"❌ Error in strategy optimizer: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/optimizer/analyze-all")
async def optimize_all_strategies():
    """
    AI-powered analysis of ALL strategies with dynamic stats
    
    Ranks strategies by profitability, identifies top performers,
    and provides resource allocation recommendations
    
    Returns:
        Comprehensive AI analysis of all trading strategies
    """
    try:
        import os
        
        api_key = os.getenv('ANTHROPIC_API_KEY') or os.getenv('CLAUDE_API_KEY')
        if not api_key:
            raise HTTPException(
                status_code=500,
                detail="ANTHROPIC_API_KEY not set. Configure API key to use optimizer."
            )
        
        from ai_strategy_optimizer import StrategyOptimizerAgent
        
        optimizer = StrategyOptimizerAgent(anthropic_api_key=api_key)
        
        # Use dynamic stats integration (analyzes all)
        result = optimizer.optimize_with_dynamic_stats(strategy_name=None)
        
        return {
            "success": True,
            "optimization": result,
            "timestamp": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except ImportError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Optimizer dependencies not installed: {str(e)}. Run: pip install langchain-anthropic"
        )
    except Exception as e:
        print(f"❌ Error in strategy optimizer: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/optimizer/recommend-trade")
async def get_trade_recommendation(request: dict):
    """
    AI-powered real-time trade recommendation
    
    Analyzes current market conditions and provides specific trade recommendation
    with entry, stop, target, and confidence level
    
    Request body:
    {
        "symbol": "SPY",
        "price": 580.50,
        "net_gex": -2500000000,
        "vix": 18.5,
        "flip_point": 578.0,
        "call_wall": 585.0,
        "put_wall": 575.0
    }
    
    Returns:
        Specific trade recommendation (BUY/SELL/WAIT) with reasoning
    """
    try:
        import os
        
        api_key = os.getenv('ANTHROPIC_API_KEY') or os.getenv('CLAUDE_API_KEY')
        if not api_key:
            raise HTTPException(
                status_code=500,
                detail="ANTHROPIC_API_KEY not set. Configure API key to use optimizer."
            )
        
        from ai_strategy_optimizer import StrategyOptimizerAgent
        
        optimizer = StrategyOptimizerAgent(anthropic_api_key=api_key)
        
        # Get trade recommendation based on current market data
        result = optimizer.get_trade_recommendation(current_market_data=request)
        
        return {
            "success": True,
            "trade_recommendation": result,
            "timestamp": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except ImportError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Optimizer dependencies not installed: {str(e)}. Run: pip install langchain-anthropic"
        )
    except Exception as e:
        print(f"❌ Error getting trade recommendation: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Enhanced Strategy Optimizer Endpoints (Strike-Level Intelligence)
# ============================================================================

@app.get("/api/optimizer/strikes")
async def get_strike_performance(strategy: str = None):
    """
    Get strike-level performance analysis

    Shows which strikes perform best by:
    - Moneyness (ITM/ATM/OTM)
    - Strike distance from spot
    - VIX regime
    - Win rate and P&L per strike type

    Query params:
        strategy: Optional strategy name filter

    Returns:
        Detailed strike performance data with win rates and P&L
    """
    try:
        import os
        api_key = os.getenv('ANTHROPIC_API_KEY') or os.getenv('CLAUDE_API_KEY')
        if not api_key:
            raise HTTPException(
                status_code=500,
                detail="ANTHROPIC_API_KEY not set"
            )

        from ai_strategy_optimizer import StrategyOptimizerAgent
        optimizer = StrategyOptimizerAgent(anthropic_api_key=api_key)

        # Get strike performance data
        strike_data_json = optimizer._analyze_strike_performance(strategy)

        # Parse JSON response
        import json
        try:
            strike_data = json.loads(strike_data_json)
        except (json.JSONDecodeError, TypeError, ValueError) as e:
            # If not valid JSON, return as string
            strike_data = {"raw_data": strike_data_json}

        return {
            "success": True,
            "strategy": strategy or "all",
            "strike_performance": strike_data,
            "timestamp": datetime.now().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error in strike performance: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/optimizer/dte")
async def get_dte_optimization(strategy: str = None):
    """
    Get DTE (Days To Expiration) optimization analysis

    Shows which DTE ranges work best:
    - 0-3 DTE (weekly)
    - 4-7 DTE
    - 8-14 DTE
    - 15-30 DTE
    - 30+ DTE

    Query params:
        strategy: Optional strategy name filter

    Returns:
        DTE performance data with win rates per bucket
    """
    try:
        import os
        api_key = os.getenv('ANTHROPIC_API_KEY') or os.getenv('CLAUDE_API_KEY')
        if not api_key:
            raise HTTPException(
                status_code=500,
                detail="ANTHROPIC_API_KEY not set"
            )

        from ai_strategy_optimizer import StrategyOptimizerAgent
        optimizer = StrategyOptimizerAgent(anthropic_api_key=api_key)

        # Get DTE performance data
        dte_data_json = optimizer._analyze_dte_performance(strategy)

        # Parse JSON response
        import json
        try:
            dte_data = json.loads(dte_data_json)
        except (json.JSONDecodeError, TypeError, ValueError) as e:
            dte_data = {"raw_data": dte_data_json}

        return {
            "success": True,
            "strategy": strategy or "all",
            "dte_optimization": dte_data,
            "timestamp": datetime.now().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error in DTE optimization: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/optimizer/regime-specific")
async def get_regime_optimization(strategy: str = None):
    """
    Get regime-specific optimization analysis

    Different strategies for different regimes:
    - VIX < 15 (Low Vol)
    - VIX 15-25 (Normal Vol)
    - VIX > 25 (High Vol)
    - Positive vs Negative Gamma

    Query params:
        strategy: Optional strategy name filter

    Returns:
        Regime-specific performance data
    """
    try:
        import os
        api_key = os.getenv('ANTHROPIC_API_KEY') or os.getenv('CLAUDE_API_KEY')
        if not api_key:
            raise HTTPException(
                status_code=500,
                detail="ANTHROPIC_API_KEY not set"
            )

        from ai_strategy_optimizer import StrategyOptimizerAgent
        optimizer = StrategyOptimizerAgent(anthropic_api_key=api_key)

        # Get regime-specific data
        regime_data_json = optimizer._optimize_by_regime(strategy)

        # Parse JSON response
        import json
        try:
            regime_data = json.loads(regime_data_json)
        except (json.JSONDecodeError, TypeError, ValueError) as e:
            regime_data = {"raw_data": regime_data_json}

        return {
            "success": True,
            "strategy": strategy or "all",
            "regime_optimization": regime_data,
            "timestamp": datetime.now().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error in regime optimization: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/optimizer/live-recommendations")
async def get_live_strike_recommendations(request: dict):
    """
    Get real-time strike recommendations for current market

    Based on historical performance + current regime,
    recommend EXACT strikes to use

    Request body:
    {
        "spot_price": 580.50,
        "vix_current": 18.5,
        "net_gex": -2500000000,
        "pattern_type": "LIBERATION"
    }

    Returns:
        Exact strike recommendations with expected performance
    """
    try:
        import os
        api_key = os.getenv('ANTHROPIC_API_KEY') or os.getenv('CLAUDE_API_KEY')
        if not api_key:
            raise HTTPException(
                status_code=500,
                detail="ANTHROPIC_API_KEY not set"
            )

        from ai_strategy_optimizer import StrategyOptimizerAgent
        optimizer = StrategyOptimizerAgent(anthropic_api_key=api_key)

        # Validate required fields
        required = ['spot_price', 'vix_current']
        for field in required:
            if field not in request:
                raise HTTPException(
                    status_code=400,
                    detail=f"Missing required field: {field}"
                )

        # Get optimal strikes
        recommendations = optimizer.get_optimal_strikes_for_current_market(request)

        return {
            "success": True,
            "recommendations": recommendations,
            "timestamp": datetime.now().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error getting live recommendations: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/optimizer/greeks")
async def get_greeks_optimization(strategy: str = None):
    """
    Get Greeks optimization analysis

    Shows which Greek ranges perform best:
    - Delta targets (0.20-0.30 vs 0.40-0.50)
    - Theta efficiency
    - Gamma exposure
    - Vega exposure

    Query params:
        strategy: Optional strategy name filter

    Returns:
        Greeks performance data with efficiency ratios
    """
    try:
        import os
        api_key = os.getenv('ANTHROPIC_API_KEY') or os.getenv('CLAUDE_API_KEY')
        if not api_key:
            raise HTTPException(
                status_code=500,
                detail="ANTHROPIC_API_KEY not set"
            )

        from ai_strategy_optimizer import StrategyOptimizerAgent
        optimizer = StrategyOptimizerAgent(anthropic_api_key=api_key)

        # Get Greeks optimization data
        greeks_data_json = optimizer._optimize_greeks(strategy)

        # Parse JSON response
        import json
        try:
            greeks_data = json.loads(greeks_data_json)
        except (json.JSONDecodeError, TypeError, ValueError) as e:
            greeks_data = {"raw_data": greeks_data_json}

        return {
            "success": True,
            "strategy": strategy or "all",
            "greeks_optimization": greeks_data,
            "timestamp": datetime.now().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error in Greeks optimization: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/optimizer/best-combinations")
async def get_best_combinations(strategy: str = None):
    """
    Find winning combinations of conditions

    Examples:
    "VIX low + Liberation + 5 DTE + 2% OTM = 78% win rate"

    Query params:
        strategy: Optional strategy name filter

    Returns:
        High-probability setup combinations
    """
    try:
        import os
        api_key = os.getenv('ANTHROPIC_API_KEY') or os.getenv('CLAUDE_API_KEY')
        if not api_key:
            raise HTTPException(
                status_code=500,
                detail="ANTHROPIC_API_KEY not set"
            )

        from ai_strategy_optimizer import StrategyOptimizerAgent
        optimizer = StrategyOptimizerAgent(anthropic_api_key=api_key)

        # Get best combinations
        combinations_json = optimizer._find_best_combinations(strategy)

        # Parse JSON response
        import json
        try:
            combinations_data = json.loads(combinations_json)
        except (json.JSONDecodeError, TypeError, ValueError) as e:
            combinations_data = {"raw_data": combinations_json}

        return {
            "success": True,
            "strategy": strategy or "all",
            "best_combinations": combinations_data,
            "timestamp": datetime.now().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error finding best combinations: {str(e)}")
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
            except (RuntimeError, ConnectionError, Exception) as e:
                # Connection likely closed, will be cleaned up on next disconnect
                pass

manager = ConnectionManager()

# Track subscriptions per connection
_connection_subscriptions: dict = {}

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


@app.websocket("/ws/trader")
async def websocket_trader(websocket: WebSocket):
    """
    WebSocket endpoint for real-time trader updates

    Streams:
    - Trader status updates
    - Position updates with P&L
    - Trade executions
    - Risk alerts

    Update frequency: Every 10 seconds during market hours
    """
    await manager.connect(websocket)
    connection_id = id(websocket)
    _connection_subscriptions[connection_id] = {'symbols': ['SPY', 'SPX']}

    try:
        import asyncio

        # Send initial connection acknowledgment
        await websocket.send_json({
            "type": "connected",
            "message": "Trader WebSocket connected",
            "timestamp": datetime.now().isoformat()
        })

        while True:
            try:
                # Check for incoming messages (subscriptions, commands)
                # Use wait_for with timeout to allow periodic updates
                try:
                    message = await asyncio.wait_for(
                        websocket.receive_json(),
                        timeout=0.1
                    )
                    # Handle subscription changes
                    if message.get('type') == 'subscribe':
                        symbols = message.get('symbols', ['SPY'])
                        # Validate symbols: only alphanumeric, max 5 chars each
                        validated_symbols = []
                        for s in symbols[:10]:  # Max 10 symbols
                            if isinstance(s, str) and s.isalnum() and len(s) <= 5:
                                validated_symbols.append(s.upper())
                        if validated_symbols:
                            _connection_subscriptions[connection_id]['symbols'] = validated_symbols
                        await websocket.send_json({
                            "type": "subscribed",
                            "symbols": _connection_subscriptions[connection_id]['symbols'],
                            "timestamp": datetime.now().isoformat()
                        })
                except asyncio.TimeoutError:
                    pass  # No message, continue with updates

                # Send comprehensive update
                update_data = await _get_trader_update_data()
                await websocket.send_json(update_data)

                # Wait 10 seconds before next update
                await asyncio.sleep(10)

            except Exception as e:
                # Send error but continue
                try:
                    await websocket.send_json({
                        "type": "error",
                        "message": str(e)[:200],  # Truncate error message
                        "timestamp": datetime.now().isoformat()
                    })
                except:
                    pass  # If sending error fails, just continue
                await asyncio.sleep(10)

    except WebSocketDisconnect:
        pass  # Normal disconnect, cleanup in finally
    except Exception as e:
        print(f"Trader WebSocket error: {e}")
    finally:
        # Guaranteed cleanup - prevents memory leak
        if connection_id in _connection_subscriptions:
            del _connection_subscriptions[connection_id]
        try:
            manager.disconnect(websocket)
        except:
            pass  # Ignore disconnect errors


async def _get_trader_update_data() -> dict:
    """
    Gather all trader data for WebSocket update.

    Returns comprehensive update including:
    - Trader status
    - Open positions with real-time P&L
    - Recent trades
    - Risk metrics
    - Market data
    """
    update = {
        "type": "trader_update",
        "timestamp": datetime.now().isoformat(),
        "market_open": is_market_open()
    }

    try:
        conn = get_connection()
        import pandas as pd

        # Get trader status
        cursor = conn.cursor()
        cursor.execute("""
            SELECT key, value FROM autonomous_config
            WHERE key IN ('capital', 'auto_execute', 'last_trade_date', 'mode', 'signal_only')
        """)
        config = {row[0]: row[1] for row in cursor.fetchall()}
        update['config'] = config

        # Get live status
        cursor.execute("""
            SELECT status, current_action, market_analysis, last_decision, timestamp, next_check_time
            FROM autonomous_live_status
            ORDER BY timestamp DESC
            LIMIT 1
        """)
        status_row = cursor.fetchone()
        if status_row:
            update['status'] = {
                'status': status_row[0],
                'current_action': status_row[1],
                'market_analysis': status_row[2],
                'last_decision': status_row[3],
                'last_updated': status_row[4] if status_row[4] else None,
                'next_check_time': status_row[5] if status_row[5] else None
            }

        # Get open positions with current P&L (including Greeks and GEX context)
        positions_df = pd.read_sql_query("""
            SELECT id, symbol, strategy, action, strike, option_type,
                   expiration_date, contracts, entry_price, entry_spot_price,
                   current_price, current_spot_price, unrealized_pnl,
                   unrealized_pnl_pct, confidence, entry_date, entry_time,
                   entry_iv, entry_delta, current_iv, current_delta,
                   entry_bid, entry_ask, gex_regime, entry_net_gex,
                   entry_flip_point, trade_reasoning, contract_symbol
            FROM autonomous_open_positions
            ORDER BY entry_date DESC, entry_time DESC
        """, conn)

        update['positions'] = positions_df.to_dict(orient='records') if not positions_df.empty else []

        # Get recent closed trades (last 10)
        trades_df = pd.read_sql_query("""
            SELECT id, symbol, strategy, action, strike, option_type,
                   entry_date, exit_date, entry_price, exit_price,
                   realized_pnl, realized_pnl_pct, exit_reason
            FROM autonomous_closed_trades
            ORDER BY exit_date DESC, exit_time DESC
            LIMIT 10
        """, conn)

        update['recent_trades'] = trades_df.to_dict(orient='records') if not trades_df.empty else []

        # Calculate performance metrics
        cursor.execute("SELECT COALESCE(SUM(realized_pnl), 0) FROM autonomous_closed_trades")
        total_realized = float(cursor.fetchone()[0] or 0)

        cursor.execute("SELECT COALESCE(SUM(unrealized_pnl), 0) FROM autonomous_open_positions")
        total_unrealized = float(cursor.fetchone()[0] or 0)

        cursor.execute("SELECT COUNT(*) FROM autonomous_closed_trades WHERE realized_pnl > 0")
        winners = cursor.fetchone()[0] or 0

        cursor.execute("SELECT COUNT(*) FROM autonomous_closed_trades WHERE realized_pnl <= 0")
        losers = cursor.fetchone()[0] or 0

        total_trades = winners + losers
        win_rate = (winners / total_trades * 100) if total_trades > 0 else 0

        starting_capital = float(config.get('capital', 5000))
        current_equity = starting_capital + total_realized + total_unrealized

        update['performance'] = {
            'starting_capital': starting_capital,
            'current_equity': current_equity,
            'total_realized_pnl': total_realized,
            'total_unrealized_pnl': total_unrealized,
            'net_pnl': total_realized + total_unrealized,
            'return_pct': ((total_realized + total_unrealized) / starting_capital * 100) if starting_capital > 0 else 0,
            'total_trades': total_trades,
            'winning_trades': winners,
            'losing_trades': losers,
            'win_rate': win_rate,
            'open_positions': len(positions_df)
        }

        # Risk alerts
        alerts = []
        drawdown_pct = ((starting_capital - current_equity) / starting_capital * 100) if starting_capital > 0 and current_equity < starting_capital else 0
        if drawdown_pct > 10:
            alerts.append({
                'level': 'critical',
                'message': f'Drawdown alert: {drawdown_pct:.1f}% from starting capital'
            })
        elif drawdown_pct > 5:
            alerts.append({
                'level': 'warning',
                'message': f'Drawdown warning: {drawdown_pct:.1f}% from starting capital'
            })

        if len(positions_df) > 5:
            alerts.append({
                'level': 'info',
                'message': f'High position count: {len(positions_df)} open positions'
            })

        update['alerts'] = alerts

        # Market data snapshot
        try:
            gex_data = api_client.get_net_gamma('SPY')
            if gex_data and not gex_data.get('error'):
                update['market'] = {
                    'symbol': 'SPY',
                    'spot_price': gex_data.get('spot_price', 0),
                    'net_gex': gex_data.get('net_gex', 0),
                    'flip_point': gex_data.get('flip_point', 0),
                    'call_wall': gex_data.get('call_wall', 0),
                    'put_wall': gex_data.get('put_wall', 0)
                }
        except (KeyError, TypeError, AttributeError, Exception) as e:
            update['market'] = None

        conn.close()

    except Exception as e:
        update['error'] = str(e)

    return update


@app.websocket("/ws/positions")
async def websocket_positions(websocket: WebSocket):
    """
    WebSocket endpoint for position-only updates (lightweight)

    Streams position P&L updates every 5 seconds
    """
    await manager.connect(websocket)

    try:
        import asyncio

        while True:
            try:
                conn = get_connection()
                import pandas as pd

                positions_df = pd.read_sql_query("""
                    SELECT id, symbol, strategy, strike, option_type,
                           expiration_date, contracts, entry_price,
                           current_price, unrealized_pnl, unrealized_pnl_pct
                    FROM autonomous_open_positions
                    ORDER BY unrealized_pnl DESC
                """, conn)
                conn.close()

                await websocket.send_json({
                    "type": "positions_update",
                    "positions": positions_df.to_dict(orient='records') if not positions_df.empty else [],
                    "count": len(positions_df),
                    "total_unrealized": float(positions_df['unrealized_pnl'].sum()) if not positions_df.empty else 0,
                    "timestamp": datetime.now().isoformat()
                })

                await asyncio.sleep(5)

            except Exception as e:
                await websocket.send_json({
                    "type": "error",
                    "message": str(e),
                    "timestamp": datetime.now().isoformat()
                })
                await asyncio.sleep(5)

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        manager.disconnect(websocket)
        print(f"Positions WebSocket error: {e}")

# ============================================================================
# VIX Hedge Manager Endpoints
# ============================================================================

@app.get("/api/vix/hedge-signal")
async def get_vix_hedge_signal(portfolio_delta: float = 0, portfolio_value: float = 100000):
    """
    Generate a VIX-based hedge signal for portfolio protection.

    This is a SIGNAL GENERATOR only - does not auto-execute trades.

    Args:
        portfolio_delta: Current portfolio delta exposure (default 0)
        portfolio_value: Total portfolio value (default $100K)

    Returns:
        Hedge signal with recommendation, reasoning, and risk warning
    """
    try:
        from vix_hedge_manager import get_vix_hedge_manager

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
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/vix/signal-history")
async def get_vix_signal_history(days: int = 30):
    """Get historical VIX hedge signals"""
    try:
        from vix_hedge_manager import get_vix_hedge_manager

        manager = get_vix_hedge_manager()
        history = manager.get_signal_history(days)

        if history.empty:
            return {"success": True, "data": []}

        # Format data for frontend - combine signal_date and signal_time into timestamp
        formatted_data = []
        for _, row in history.iterrows():
            try:
                # Combine date and time into ISO timestamp
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/vix/current")
async def get_vix_current():
    """Get current VIX data and analysis"""
    try:
        from vix_hedge_manager import get_vix_hedge_manager

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
                "vix_m1": vix_data.get('vix_m1', 0),
                "vix_m2": vix_data.get('vix_m2', 0),
                "term_structure_pct": vix_data.get('term_structure_m1_pct', 0),
                "structure_type": vix_data.get('structure_type', 'unknown'),
                "iv_percentile": iv_percentile,
                "realized_vol_20d": realized_vol,
                "iv_rv_spread": vix_spot - realized_vol,
                "vol_regime": vol_regime.value,
                "timestamp": datetime.now().isoformat()
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# SPX Institutional Trader Endpoints
# ============================================================================

@app.get("/api/spx/status")
async def get_spx_trader_status():
    """Get SPX institutional trader status"""
    try:
        from spx_institutional_trader import get_spx_trader_100m

        trader = get_spx_trader_100m()

        return {
            "success": True,
            "data": {
                "symbol": trader.symbol,
                "starting_capital": trader.starting_capital,
                "available_capital": trader.get_available_capital(),
                "max_position_pct": trader.max_position_pct,
                "max_delta_exposure": trader.max_delta_exposure,
                "max_contracts_per_trade": trader.max_contracts_per_trade,
                "greeks": trader.get_portfolio_greeks()
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/spx/performance")
async def get_spx_performance():
    """Get SPX institutional trader performance summary"""
    try:
        from spx_institutional_trader import get_spx_trader_100m

        trader = get_spx_trader_100m()
        performance = trader.get_performance_summary()

        return {
            "success": True,
            "data": performance
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/spx/check-risk")
async def check_spx_risk_limits(
    contracts: int,
    entry_price: float,
    delta: float = 0.5
):
    """Check if a proposed SPX trade passes risk limits"""
    try:
        from spx_institutional_trader import get_spx_trader_100m

        trader = get_spx_trader_100m()

        proposed_trade = {
            'contracts': contracts,
            'entry_price': entry_price,
            'delta': delta
        }

        can_trade, reason = trader.check_risk_limits(proposed_trade)

        return {
            "success": True,
            "data": {
                "can_trade": can_trade,
                "reason": reason,
                "proposed_trade": proposed_trade
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/spx/trades")
async def get_spx_trades(limit: int = 20):
    """Get SPX institutional positions/trades"""
    try:
        import math
        conn = get_connection()
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        c.execute(f'''
            SELECT
                id,
                entry_date,
                entry_time,
                exit_date,
                exit_time,
                option_type,
                strike,
                expiration_date,
                contracts,
                entry_price,
                exit_price,
                realized_pnl,
                unrealized_pnl,
                status,
                strategy,
                trade_reasoning
            FROM spx_institutional_positions
            ORDER BY entry_date DESC, entry_time DESC
            LIMIT {int(limit)}
        ''')

        trades = []
        for row in c.fetchall():
            # Clean values for JSON serialization
            trade = {}
            for key, value in dict(row).items():
                if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
                    trade[key] = 0
                else:
                    trade[key] = value
            trades.append(trade)

        conn.close()

        return {
            "success": True,
            "count": len(trades),
            "data": trades
        }
    except Exception as e:
        return {
            "success": True,
            "count": 0,
            "data": [],
            "message": f"No SPX trades available: {str(e)}"
        }


@app.get("/api/spx/equity-curve")
async def get_spx_equity_curve(days: int = 30):
    """Get SPX institutional equity curve from position history"""
    try:
        import math
        from datetime import datetime, timedelta
        conn = get_connection()
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        starting_capital = 100_000_000  # $100M

        # Get closed positions to build equity curve
        c.execute('''
            SELECT
                exit_date as date,
                SUM(realized_pnl) as daily_pnl
            FROM spx_institutional_positions
            WHERE status = 'CLOSED'
            AND exit_date >= %s
            GROUP BY exit_date
            ORDER BY exit_date ASC
        ''', (start_date,))

        results = c.fetchall()
        conn.close()

        # Build cumulative equity curve
        equity_data = []
        cumulative_pnl = 0

        if results:
            for row in results:
                pnl = float(row['daily_pnl'] or 0)
                if math.isnan(pnl) or math.isinf(pnl):
                    pnl = 0
                cumulative_pnl += pnl
                equity_data.append({
                    "date": str(row['date']),
                    "timestamp": int(datetime.strptime(str(row['date']), '%Y-%m-%d').timestamp()),
                    "pnl": round(cumulative_pnl, 2),
                    "equity": round(starting_capital + cumulative_pnl, 2),
                    "daily_pnl": round(pnl, 2)
                })
        else:
            # Return starting point if no data
            today = datetime.now().strftime('%Y-%m-%d')
            equity_data.append({
                "date": today,
                "timestamp": int(datetime.now().timestamp()),
                "pnl": 0,
                "equity": starting_capital,
                "daily_pnl": 0
            })

        return {
            "success": True,
            "data": equity_data
        }
    except Exception as e:
        # Return empty data on error
        from datetime import datetime as dt
        return {
            "success": True,
            "data": [{
                "date": dt.now().strftime('%Y-%m-%d'),
                "timestamp": int(dt.now().timestamp()),
                "pnl": 0,
                "equity": 100_000_000,
                "daily_pnl": 0
            }],
            "message": str(e)
        }


@app.get("/api/spx/trade-log")
async def get_spx_trade_log():
    """Get SPX trade activity log"""
    try:
        import math
        from datetime import datetime
        conn = get_connection()
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Get recent trade activity
        c.execute('''
            SELECT
                id,
                entry_date as date,
                entry_time as time,
                CASE
                    WHEN status = 'OPEN' THEN 'OPEN ' || option_type
                    ELSE 'CLOSE ' || option_type
                END as action,
                'SPX ' || strike || ' ' || option_type || ' ' || expiration_date as details,
                COALESCE(realized_pnl, unrealized_pnl, 0) as pnl
            FROM spx_institutional_positions
            ORDER BY entry_date DESC, entry_time DESC
            LIMIT 50
        ''')

        trades = []
        for row in c.fetchall():
            trade = {}
            for key, value in dict(row).items():
                if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
                    trade[key] = 0
                else:
                    trade[key] = value
            trades.append(trade)

        conn.close()

        return {
            "success": True,
            "data": trades
        }
    except Exception as e:
        return {
            "success": True,
            "data": [],
            "message": str(e)
        }


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
    print("✅ SPY Autonomous Trader initialized successfully")
except Exception as e:
    trader = None
    trader_available = False
    print(f"⚠️ SPY Autonomous Trader not available: {e}")
    import traceback
    traceback.print_exc()

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

        # Get actual strategy count and today's trades from database
        strategies_active = 0
        total_trades_today = 0

        try:
            conn = get_connection()
            cursor = conn.cursor()

            # Count active strategies (those with enabled=true or not in config)
            cursor.execute("""
                SELECT COUNT(DISTINCT strategy) FROM (
                    SELECT strategy FROM autonomous_open_positions
                    UNION
                    SELECT strategy FROM autonomous_closed_trades
                ) s
            """)
            strategies_active = cursor.fetchone()[0] or 0

            # Count today's trades
            today = datetime.now().strftime('%Y-%m-%d')
            cursor.execute("""
                SELECT
                    (SELECT COUNT(*) FROM autonomous_open_positions WHERE entry_date = %s) +
                    (SELECT COUNT(*) FROM autonomous_closed_trades WHERE entry_date = %s)
            """, (today, today))
            total_trades_today = cursor.fetchone()[0] or 0

            conn.close()
        except Exception as db_error:
            print(f"Error getting trader metrics: {db_error}")

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
                "strategies_active": strategies_active,
                "total_trades_today": total_trades_today
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/trader/diagnostics")
async def get_trader_diagnostics():
    """
    Run comprehensive diagnostics on the autonomous trader
    Returns detailed status of all components to help debug issues
    """
    from datetime import datetime, timedelta, time as dt_time
    from zoneinfo import ZoneInfo

    diagnostics = {
        "timestamp": datetime.now().isoformat(),
        "checks": {},
        "recommendations": []
    }

    # 1. Check market hours
    try:
        ct_now = datetime.now(ZoneInfo("America/Chicago"))
        market_open = dt_time(8, 30)
        market_close = dt_time(15, 0)
        current_time = ct_now.time()
        is_weekday = ct_now.weekday() < 5
        is_market_hours = is_weekday and market_open <= current_time <= market_close

        diagnostics["checks"]["market_hours"] = {
            "status": "open" if is_market_hours else "closed",
            "current_time_ct": ct_now.strftime('%I:%M:%S %p CT'),
            "day_of_week": ct_now.strftime('%A'),
            "is_trading_day": is_weekday,
            "market_open": "8:30 AM CT",
            "market_close": "3:00 PM CT"
        }

        if not is_market_hours:
            diagnostics["recommendations"].append("Market is closed - trader only runs during 8:30 AM - 3:00 PM CT, Mon-Fri")
    except Exception as e:
        diagnostics["checks"]["market_hours"] = {"error": str(e)}

    # 2. Check trader availability
    diagnostics["checks"]["trader_available"] = trader_available

    if not trader_available:
        diagnostics["recommendations"].append("Trader is not available - check startup logs for errors")

    # 3. Check live status
    if trader_available:
        try:
            live_status = trader.get_live_status()
            diagnostics["checks"]["live_status"] = live_status

            # Check if status is stale
            if live_status.get('timestamp'):
                try:
                    last_update = datetime.fromisoformat(live_status['timestamp'].replace('Z', '+00:00'))
                    now = datetime.now(last_update.tzinfo) if last_update.tzinfo else datetime.now()
                    age_minutes = (now - last_update).total_seconds() / 60
                    diagnostics["checks"]["live_status"]["age_minutes"] = round(age_minutes, 1)

                    if age_minutes > 10:
                        diagnostics["checks"]["live_status"]["stale"] = True
                        diagnostics["recommendations"].append(f"Status is {age_minutes:.0f} minutes old - scheduler thread may have crashed")
                except (ValueError, TypeError, AttributeError) as e:
                    # Failed to parse timestamp, skip age check
                    pass
        except Exception as e:
            diagnostics["checks"]["live_status"] = {"error": str(e)}

    # 4. Check configuration
    if trader_available:
        try:
            config = {
                "capital": trader.get_config('capital'),
                "mode": trader.get_config('mode'),
                "signal_only": trader.get_config('signal_only'),
                "last_trade_date": trader.get_config('last_trade_date'),
                "auto_execute": trader.get_config('auto_execute')
            }
            diagnostics["checks"]["config"] = config

            if config.get('signal_only', '').lower() == 'true':
                diagnostics["recommendations"].append("signal_only mode is ENABLED - trades will NOT auto-execute!")
        except Exception as e:
            diagnostics["checks"]["config"] = {"error": str(e)}

    # 5. Check database tables
    try:
        conn = get_connection()
        c = conn.cursor()

        tables = {}
        for table in ['autonomous_live_status', 'autonomous_trade_log', 'autonomous_open_positions',
                      'autonomous_closed_trades', 'autonomous_config', 'autonomous_trader_logs']:
            try:
                c.execute(f"SELECT COUNT(*) FROM {table}")
                tables[table] = c.fetchone()[0]
            except Exception as e:
                tables[table] = f"Error: {e}"

        diagnostics["checks"]["database_tables"] = tables
        conn.close()
    except Exception as e:
        diagnostics["checks"]["database_tables"] = {"error": str(e)}

    # 6. Check recent activity
    try:
        conn = get_connection()
        c = conn.cursor()

        c.execute("""
            SELECT action, details, date, time, success
            FROM autonomous_trade_log
            ORDER BY id DESC
            LIMIT 5
        """)
        recent_logs = []
        for row in c.fetchall():
            recent_logs.append({
                "action": row[0],
                "details": str(row[1])[:100] if row[1] else None,
                "timestamp": f"{row[2]} {row[3]}",
                "success": row[4]
            })
        diagnostics["checks"]["recent_activity"] = recent_logs

        # Count open positions
        c.execute("SELECT COUNT(*) FROM autonomous_open_positions")
        diagnostics["checks"]["open_positions"] = c.fetchone()[0]

        conn.close()
    except Exception as e:
        diagnostics["checks"]["recent_activity"] = {"error": str(e)}

    # 7. Summary
    has_issues = len(diagnostics["recommendations"]) > 0
    diagnostics["summary"] = {
        "healthy": not has_issues,
        "issues_found": len(diagnostics["recommendations"])
    }

    return {"success": True, "data": diagnostics}

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
        print(f"   Database: PostgreSQL via DATABASE_URL")
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
    """Get autonomous trader performance metrics with real calculations"""
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

        # Get latest equity snapshot for real Sharpe and max drawdown
        conn = get_connection()
        cursor = conn.cursor()

        # Get latest equity snapshot
        cursor.execute("""
            SELECT sharpe_ratio, max_drawdown_pct, daily_pnl
            FROM autonomous_equity_snapshots
            ORDER BY snapshot_date DESC, snapshot_time DESC
            LIMIT 1
        """)
        snapshot = cursor.fetchone()
        sharpe_ratio = float(snapshot[0] or 0) if snapshot else 0
        max_drawdown = float(snapshot[1] or 0) if snapshot else 0

        # Get today's P&L from closed trades and open positions
        from datetime import datetime
        from zoneinfo import ZoneInfo
        today = datetime.now(ZoneInfo("America/Chicago")).strftime('%Y-%m-%d')

        cursor.execute("""
            SELECT COALESCE(SUM(realized_pnl), 0)
            FROM autonomous_closed_trades
            WHERE exit_date = %s
        """, (today,))
        today_realized = cursor.fetchone()[0] or 0

        cursor.execute("""
            SELECT COALESCE(SUM(unrealized_pnl), 0)
            FROM autonomous_open_positions
        """)
        today_unrealized = cursor.fetchone()[0] or 0

        conn.close()

        today_pnl = float(today_realized) + float(today_unrealized)

        return {
            "success": True,
            "data": {
                "total_pnl": perf['total_pnl'],
                "today_pnl": today_pnl,
                "win_rate": perf['win_rate'],
                "total_trades": perf['total_trades'],
                "closed_trades": perf.get('closed_trades', 0),
                "open_positions": perf.get('open_positions', 0),
                "winning_trades": perf.get('winning_trades', 0),
                "losing_trades": perf.get('losing_trades', 0),
                "sharpe_ratio": sharpe_ratio,
                "max_drawdown": max_drawdown,
                "realized_pnl": perf.get('realized_pnl', 0),
                "unrealized_pnl": perf.get('unrealized_pnl', 0),
                "starting_capital": perf.get('starting_capital', 5000),
                "current_value": perf.get('current_value', 5000),
                "return_pct": perf.get('return_pct', 0)
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/trader/trades")
async def get_trader_trades(limit: int = 10):
    """Get recent trades from autonomous trader - combines open and closed positions"""
    if not trader_available:
        return {
            "success": False,
            "message": "Trader not configured",
            "data": []
        }

    # Validate and cap limit to prevent abuse
    limit = max(1, min(limit, 100))

    try:
        import pandas as pd

        conn = get_connection()

        # Get open positions with Greeks
        open_trades = pd.read_sql_query(f"""
            SELECT id, symbol, strategy, action, strike, option_type, expiration_date,
                   contracts, contract_symbol, entry_date, entry_time, entry_price,
                   entry_bid, entry_ask, entry_spot_price, current_price,
                   current_spot_price, unrealized_pnl, unrealized_pnl_pct,
                   confidence, gex_regime, entry_net_gex, entry_flip_point,
                   entry_iv, entry_delta, current_iv, current_delta,
                   trade_reasoning, 'OPEN' as status,
                   NULL as exit_date, NULL as exit_time, NULL as exit_price,
                   NULL as realized_pnl, NULL as exit_reason
            FROM autonomous_open_positions
            ORDER BY entry_date DESC, entry_time DESC
            LIMIT {limit}
        """, conn)

        # Get closed trades with Greeks
        closed_trades = pd.read_sql_query(f"""
            SELECT id, symbol, strategy, action, strike, option_type, expiration_date,
                   contracts, contract_symbol, entry_date, entry_time, entry_price,
                   entry_bid, entry_ask, entry_spot_price, exit_price as current_price,
                   exit_spot_price as current_spot_price, realized_pnl as unrealized_pnl,
                   realized_pnl_pct as unrealized_pnl_pct, confidence, gex_regime,
                   entry_net_gex, entry_flip_point, entry_iv, entry_delta,
                   NULL as current_iv, NULL as current_delta,
                   trade_reasoning, 'CLOSED' as status, exit_date, exit_time,
                   exit_price, realized_pnl, exit_reason
            FROM autonomous_closed_trades
            ORDER BY exit_date DESC, exit_time DESC
            LIMIT {limit}
        """, conn)

        conn.close()

        # Combine and sort by date
        all_trades = pd.concat([open_trades, closed_trades], ignore_index=True)
        if not all_trades.empty:
            all_trades = all_trades.sort_values(
                by=['entry_date', 'entry_time'],
                ascending=[False, False]
            ).head(limit)

        trades_list = all_trades.to_dict('records') if not all_trades.empty else []

        return {
            "success": True,
            "data": trades_list
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/trader/positions")
async def get_open_positions():
    """Get currently open positions from autonomous_open_positions table"""
    if not trader_available:
        return {
            "success": False,
            "message": "Trader not configured",
            "data": []
        }

    try:
        import pandas as pd

        conn = get_connection()
        positions = pd.read_sql_query("""
            SELECT * FROM autonomous_open_positions
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

@app.get("/api/trader/closed-trades")
async def get_closed_trades(limit: int = 50):
    """Get closed trades from autonomous_closed_trades table"""
    if not trader_available:
        return {
            "success": False,
            "message": "Trader not configured",
            "data": []
        }

    try:
        import pandas as pd

        conn = get_connection()
        trades = pd.read_sql_query(f"""
            SELECT * FROM autonomous_closed_trades
            ORDER BY exit_date DESC, exit_time DESC
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

@app.get("/api/trader/trade-log")
async def get_trade_log():
    """Get today's trade activity from autonomous_trade_activity table"""
    if not trader_available:
        return JSONResponse({
            "success": False,
            "message": "Trader not configured",
            "data": []
        })

    try:
        import pandas as pd
        from datetime import datetime
        import json
        import math

        conn = get_connection()

        # Get today's date in Central Time
        from intelligence_and_strategies import get_local_time
        today = get_local_time('US/Central').strftime('%Y-%m-%d')

        # Get trade activity from new table
        # Use raw_connection for pandas compatibility
        log_entries = pd.read_sql_query("""
            SELECT
                id,
                activity_date as date,
                activity_time as time,
                action_type as action,
                details,
                position_id,
                pnl_impact as pnl,
                success,
                error_message
            FROM autonomous_trade_activity
            WHERE activity_date = %s
            ORDER BY activity_time DESC
        """, conn.raw_connection, params=(today,))
        conn.close()

        # Clean data for JSON serialization
        if not log_entries.empty:
            # Replace NaN and infinity with None
            log_entries = log_entries.replace([float('inf'), float('-inf')], None)
            log_list = []
            for record in log_entries.to_dict('records'):
                cleaned_record = {}
                for key, value in record.items():
                    # Handle NaN and infinity values
                    if isinstance(value, float):
                        if math.isnan(value) or math.isinf(value):
                            cleaned_record[key] = None
                        else:
                            cleaned_record[key] = value
                    else:
                        cleaned_record[key] = value
                log_list.append(cleaned_record)
        else:
            log_list = []

        return JSONResponse({
            "success": True,
            "data": log_list
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/trader/equity-curve")
async def get_equity_curve(days: int = 30):
    """Get historical equity curve from equity_snapshots table or calculate from trades"""
    if not trader_available:
        return {
            "success": False,
            "message": "Trader not configured",
            "data": []
        }

    try:
        import pandas as pd
        from datetime import datetime, timedelta

        conn = get_connection()

        # Get trade history for specified days
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        starting_equity = 5000

        # Fetch equity snapshots from new table
        snapshots = pd.read_sql_query(f"""
            SELECT
                snapshot_date,
                snapshot_time,
                starting_capital,
                total_realized_pnl,
                total_unrealized_pnl,
                account_value,
                daily_pnl,
                daily_return_pct,
                total_return_pct,
                max_drawdown_pct,
                sharpe_ratio,
                win_rate,
                total_trades
            FROM autonomous_equity_snapshots
            WHERE snapshot_date >= '{start_date.strftime('%Y-%m-%d')}'
            ORDER BY snapshot_date ASC, snapshot_time ASC
        """, conn)

        if snapshots.empty:
            # Try to build equity curve from closed trades
            trades = pd.read_sql_query(f"""
                SELECT
                    exit_date as trade_date,
                    exit_time as trade_time,
                    realized_pnl,
                    strategy
                FROM autonomous_closed_trades
                WHERE exit_date >= '{start_date.strftime('%Y-%m-%d')}'
                ORDER BY exit_date ASC, exit_time ASC
            """, conn)

            conn.close()

            if trades.empty:
                # Return starting point if no trades either
                return {
                    "success": True,
                    "data": [{
                        "timestamp": int(start_date.timestamp()),
                        "date": start_date.strftime('%Y-%m-%d'),
                        "equity": starting_equity,
                        "pnl": 0,
                        "daily_pnl": 0,
                        "total_return_pct": 0,
                        "max_drawdown_pct": 0,
                        "sharpe_ratio": 0,
                        "win_rate": 0
                    }],
                    "total_pnl": 0,
                    "starting_equity": starting_equity,
                    "sharpe_ratio": 0,
                    "max_drawdown_pct": 0,
                    "win_rate": 0,
                    "message": "No trades yet - data will appear after first trade"
                }

            # Calculate cumulative P&L from trades
            equity_data = []
            cumulative_pnl = 0
            peak_equity = starting_equity
            max_drawdown = 0
            winners = 0
            total_trades = 0

            # Group by date for daily aggregation
            trades['trade_date'] = pd.to_datetime(trades['trade_date'])
            daily_trades = trades.groupby('trade_date').agg({
                'realized_pnl': 'sum',
                'strategy': 'count'
            }).reset_index()
            daily_trades.columns = ['trade_date', 'daily_pnl', 'trades_count']

            for _, row in daily_trades.iterrows():
                cumulative_pnl += float(row['daily_pnl'])
                current_equity = starting_equity + cumulative_pnl
                total_trades += int(row['trades_count'])

                # Track peak and drawdown
                if current_equity > peak_equity:
                    peak_equity = current_equity
                current_drawdown = (peak_equity - current_equity) / peak_equity * 100
                max_drawdown = max(max_drawdown, current_drawdown)

                equity_data.append({
                    "timestamp": int(row['trade_date'].timestamp()),
                    "date": row['trade_date'].strftime('%Y-%m-%d'),
                    "equity": current_equity,
                    "pnl": cumulative_pnl,
                    "daily_pnl": float(row['daily_pnl']),
                    "total_return_pct": (current_equity - starting_equity) / starting_equity * 100,
                    "max_drawdown_pct": max_drawdown
                })

            # Calculate win rate from all trades
            trades_wins = trades[trades['realized_pnl'] > 0].shape[0]
            win_rate = (trades_wins / len(trades) * 100) if len(trades) > 0 else 0

            return {
                "success": True,
                "data": equity_data,
                "total_pnl": cumulative_pnl,
                "starting_equity": starting_equity,
                "sharpe_ratio": 0,  # Would need more data to calculate properly
                "max_drawdown_pct": max_drawdown,
                "win_rate": win_rate,
                "total_trades": total_trades,
                "message": "Equity curve calculated from closed trades"
            }

        conn.close()

        # Convert snapshots to equity curve data
        equity_data = []
        for _, snapshot in snapshots.iterrows():
            try:
                snapshot_datetime = datetime.strptime(
                    f"{snapshot['snapshot_date']} {snapshot['snapshot_time']}",
                    '%Y-%m-%d %H:%M:%S'
                )

                equity_data.append({
                    "timestamp": int(snapshot_datetime.timestamp()),
                    "equity": float(snapshot['account_value']),
                    "daily_pnl": float(snapshot['daily_pnl'] or 0),
                    "total_return_pct": float(snapshot['total_return_pct'] or 0),
                    "max_drawdown_pct": float(snapshot['max_drawdown_pct'] or 0),
                    "sharpe_ratio": float(snapshot['sharpe_ratio'] or 0),
                    "win_rate": float(snapshot['win_rate'] or 0)
                })
            except Exception:
                continue

        # Get latest metrics
        latest = snapshots.iloc[-1] if not snapshots.empty else None
        total_pnl = float(latest['total_realized_pnl'] or 0) + float(latest['total_unrealized_pnl'] or 0) if latest is not None else 0

        return {
            "success": True,
            "data": equity_data,
            "total_pnl": total_pnl,
            "starting_equity": starting_equity,
            "sharpe_ratio": float(latest['sharpe_ratio'] or 0) if latest is not None else 0,
            "max_drawdown_pct": float(latest['max_drawdown_pct'] or 0) if latest is not None else 0,
            "win_rate": float(latest['win_rate'] or 0) if latest is not None else 0,
            "total_trades": int(latest['total_trades'] or 0) if latest is not None else 0
        }
    except Exception as e:
        print(f"Error fetching equity curve: {e}")
        return {
            "success": False,
            "message": str(e),
            "data": []
        }

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
    Get price history for charting using Polygon.io

    Returns daily OHLCV data for the specified period
    """
    try:
        symbol = symbol.upper()

        print(f"📊 Fetching {days}-day price history for {symbol} from Polygon.io")

        polygon_key = os.getenv("POLYGON_API_KEY")
        if not polygon_key:
            raise HTTPException(
                status_code=503,
                detail="Polygon.io API key not configured"
            )

        # Calculate date range
        to_date = datetime.now().strftime('%Y-%m-%d')
        from_date = (datetime.now() - timedelta(days=days + 10)).strftime('%Y-%m-%d')

        # Fetch daily bars from Polygon.io
        url = f"https://api.polygon.io/v2/aggs/ticker/{symbol}/range/1/day/{from_date}/{to_date}"
        params = {"apiKey": polygon_key, "sort": "asc", "limit": 50000}

        response = requests.get(url, params=params, timeout=10)

        if response.status_code == 200:
            data = response.json()
            if data.get('status') in ['OK', 'DELAYED'] and data.get('results'):
                results = data['results']

                # Convert to chart format
                chart_data = []
                for bar in results:
                    chart_data.append({
                        "time": bar['t'] // 1000,  # Convert milliseconds to seconds
                        "value": bar['c']  # Close price
                    })

                print(f"✅ Successfully fetched {len(chart_data)} data points from Polygon.io")

                return {
                    "success": True,
                    "symbol": symbol,
                    "data": chart_data,
                    "points": len(chart_data),
                    "source": "polygon.io"
                }
            else:
                raise HTTPException(
                    status_code=503,
                    detail=f"Polygon.io returned no data for {symbol}"
                )
        else:
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Polygon.io API error: {response.status_code}"
            )

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error fetching price history: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch price history: {str(e)}"
        )

@app.get("/api/trader/strategies")
async def get_strategy_stats():
    """Get real strategy statistics from trade database (open + closed positions)"""
    if not trader_available:
        return {
            "success": False,
            "message": "Trader not configured",
            "data": []
        }

    try:
        import pandas as pd

        conn = get_connection()

        # Get all positions from BOTH open and closed tables using UNION
        query = """
            WITH all_trades AS (
                -- Open positions (unrealized P&L)
                SELECT
                    strategy,
                    unrealized_pnl as pnl,
                    CASE WHEN unrealized_pnl > 0 THEN 1 ELSE 0 END as is_winner,
                    entry_date as trade_date,
                    'OPEN' as status
                FROM autonomous_open_positions

                UNION ALL

                -- Closed trades (realized P&L)
                SELECT
                    strategy,
                    realized_pnl as pnl,
                    CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END as is_winner,
                    exit_date as trade_date,
                    'CLOSED' as status
                FROM autonomous_closed_trades
            )
            SELECT
                strategy,
                COUNT(*) as total_trades,
                SUM(is_winner) as wins,
                SUM(pnl) as total_pnl,
                MAX(trade_date) as last_trade_date,
                SUM(CASE WHEN status = 'OPEN' THEN 1 ELSE 0 END) as open_count
            FROM all_trades
            WHERE strategy IS NOT NULL
            GROUP BY strategy
            ORDER BY total_pnl DESC
        """

        strategies = pd.read_sql_query(query, conn)
        conn.close()

        strategy_list = []
        for _, row in strategies.iterrows():
            win_rate = (row['wins'] / row['total_trades'] * 100) if row['total_trades'] > 0 else 0
            # Determine status based on whether there are open positions
            status = "active" if row['open_count'] > 0 else "inactive"

            strategy_list.append({
                "id": row['strategy'].lower().replace(' ', '_').replace('(', '').replace(')', ''),
                "name": row['strategy'],
                "total_trades": int(row['total_trades']),
                "win_rate": float(win_rate),
                "total_pnl": float(row['total_pnl']) if row['total_pnl'] else 0,
                "last_trade_date": str(row['last_trade_date']) if row['last_trade_date'] else None,
                "status": status,
                "open_positions": int(row['open_count'])
            })

        return {
            "success": True,
            "data": strategy_list
        }
    except Exception as e:
        print(f"Error in get_strategy_stats: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/trader/strategies/{strategy_id}/toggle")
async def toggle_strategy(strategy_id: str, enabled: bool = True):
    """Toggle a strategy on/off"""
    if not trader_available:
        return {"success": False, "message": "Trader not configured"}

    try:
        conn = get_connection()
        c = conn.cursor()

        # Create strategy_config table if it doesn't exist
        c.execute("""
            CREATE TABLE IF NOT EXISTS strategy_config (
                strategy_name VARCHAR(100) PRIMARY KEY,
                enabled BOOLEAN DEFAULT TRUE,
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # Convert strategy_id back to name (reverse of the id generation)
        strategy_name = strategy_id.replace('_', ' ').title()

        # Upsert the strategy config
        c.execute("""
            INSERT INTO strategy_config (strategy_name, enabled, updated_at)
            VALUES (%s, %s, NOW())
            ON CONFLICT (strategy_name) DO UPDATE SET
                enabled = EXCLUDED.enabled,
                updated_at = NOW()
        """, (strategy_name, enabled))

        conn.commit()
        conn.close()

        return {
            "success": True,
            "message": f"Strategy '{strategy_name}' {'enabled' if enabled else 'disabled'}",
            "strategy": strategy_name,
            "enabled": enabled
        }
    except Exception as e:
        print(f"Error toggling strategy: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/trader/strategies/config")
async def get_strategy_configs():
    """Get all strategy configurations (enabled/disabled status)"""
    if not trader_available:
        return {"success": False, "data": {}}

    try:
        conn = get_connection()

        # Check if table exists
        c = conn.cursor()
        c.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'strategy_config'
            )
        """)
        table_exists = c.fetchone()[0]

        if not table_exists:
            conn.close()
            return {"success": True, "data": {}}

        import pandas as pd
        df = pd.read_sql_query("SELECT strategy_name, enabled FROM strategy_config", conn)
        conn.close()

        config = {row['strategy_name']: row['enabled'] for _, row in df.iterrows()}
        return {"success": True, "data": config}
    except Exception as e:
        print(f"Error getting strategy configs: {e}")
        return {"success": False, "data": {}}

# ============== AUTONOMOUS TRADER ADVANCED ENDPOINTS ==============

@app.get("/api/autonomous/logs")
async def get_autonomous_logs(limit: int = 50, log_type: str = None):
    """Get autonomous trader decision logs"""
    if not trader_available:
        return {"success": False, "message": "Trader not configured", "data": []}

    try:
        import pandas as pd
        conn = get_connection()

        query = """
            SELECT id, activity_date, activity_time, action_type, symbol, details,
                   position_id, pnl_impact, success, error_message, created_at
            FROM autonomous_trade_activity
            ORDER BY activity_date DESC, activity_time DESC
            LIMIT %s
        """
        logs = pd.read_sql_query(query, conn, params=(limit,))
        conn.close()

        log_list = []
        for _, log in logs.iterrows():
            log_list.append({
                "id": int(log['id']) if log['id'] else None,
                "log_type": log['action_type'],
                "timestamp": f"{log['activity_date']}T{log['activity_time']}",
                "symbol": log['symbol'],
                "details": log['details'],
                "position_id": log['position_id'],
                "pnl_impact": float(log['pnl_impact']) if log['pnl_impact'] else 0,
                "success": bool(log['success']),
                "error_message": log['error_message']
            })

        return {"success": True, "data": log_list}
    except Exception as e:
        print(f"Error getting autonomous logs: {e}")
        return {"success": False, "data": [], "error": str(e)}

@app.get("/api/autonomous/competition/leaderboard")
async def get_competition_leaderboard():
    """Get strategy competition leaderboard"""
    if not trader_available:
        return {"success": False, "message": "Trader not configured", "data": []}

    try:
        import pandas as pd
        conn = get_connection()

        # Get strategy performance aggregated from trades
        query = """
            WITH strategy_stats AS (
                SELECT
                    strategy as strategy_name,
                    COUNT(*) as total_trades,
                    SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as winning_trades,
                    SUM(realized_pnl) as total_pnl,
                    AVG(realized_pnl) as avg_pnl,
                    MIN(exit_date) as first_trade,
                    MAX(exit_date) as last_trade
                FROM autonomous_closed_trades
                GROUP BY strategy
            )
            SELECT
                strategy_name,
                total_trades,
                winning_trades,
                CASE WHEN total_trades > 0 THEN winning_trades::float / total_trades ELSE 0 END as win_rate,
                COALESCE(total_pnl, 0) as total_pnl,
                COALESCE(avg_pnl, 0) as avg_pnl,
                5000 as starting_capital,
                5000 + COALESCE(total_pnl, 0) as current_capital,
                0 as sharpe_ratio,
                first_trade,
                last_trade
            FROM strategy_stats
            ORDER BY total_pnl DESC
        """
        strategies = pd.read_sql_query(query, conn)
        conn.close()

        leaderboard = []
        for idx, row in strategies.iterrows():
            leaderboard.append({
                "rank": idx + 1,
                "strategy_id": row['strategy_name'].lower().replace(' ', '_'),
                "strategy_name": row['strategy_name'],
                "total_trades": int(row['total_trades']),
                "winning_trades": int(row['winning_trades']),
                "win_rate": float(row['win_rate']),
                "total_pnl": float(row['total_pnl']),
                "avg_pnl": float(row['avg_pnl']),
                "starting_capital": float(row['starting_capital']),
                "current_capital": float(row['current_capital']),
                "sharpe_ratio": float(row['sharpe_ratio'])
            })

        return {"success": True, "data": leaderboard}
    except Exception as e:
        print(f"Error getting competition leaderboard: {e}")
        return {"success": False, "data": [], "error": str(e)}

@app.get("/api/autonomous/backtests/all-patterns")
async def get_all_pattern_backtests(lookback_days: int = 90):
    """Get backtest results for all patterns"""
    if not trader_available:
        return {"success": False, "message": "Trader not configured", "data": []}

    try:
        import pandas as pd
        from datetime import datetime, timedelta
        conn = get_connection()

        start_date = (datetime.now() - timedelta(days=lookback_days)).strftime('%Y-%m-%d')

        # Get pattern performance from closed trades
        query = """
            SELECT
                strategy as pattern,
                COUNT(*) as total_signals,
                SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as winning_signals,
                CASE WHEN COUNT(*) > 0 THEN
                    SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END)::float / COUNT(*) * 100
                ELSE 0 END as win_rate,
                AVG(realized_pnl_pct) as expectancy,
                SUM(realized_pnl) as total_pnl
            FROM autonomous_closed_trades
            WHERE exit_date >= %s
            GROUP BY strategy
            ORDER BY win_rate DESC
        """
        patterns = pd.read_sql_query(query, conn, params=(start_date,))
        conn.close()

        results = []
        for _, row in patterns.iterrows():
            results.append({
                "pattern": row['pattern'],
                "total_signals": int(row['total_signals']),
                "winning_signals": int(row['winning_signals']),
                "win_rate": float(row['win_rate']) if row['win_rate'] else 0,
                "expectancy": float(row['expectancy']) if row['expectancy'] else 0,
                "total_pnl": float(row['total_pnl']) if row['total_pnl'] else 0
            })

        return {"success": True, "data": results}
    except Exception as e:
        print(f"Error getting pattern backtests: {e}")
        return {"success": False, "data": [], "error": str(e)}

@app.get("/api/autonomous/risk/status")
async def get_risk_status():
    """Get current risk management status"""
    if not trader_available:
        return {"success": False, "message": "Trader not configured", "data": None}

    try:
        import pandas as pd
        from datetime import datetime
        conn = get_connection()

        today = datetime.now().strftime('%Y-%m-%d')

        # Get today's P&L
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COALESCE(SUM(realized_pnl), 0) as today_pnl
            FROM autonomous_closed_trades
            WHERE exit_date = %s
        """, (today,))
        today_pnl = cursor.fetchone()[0] or 0

        # Get open position exposure
        cursor.execute("""
            SELECT
                COUNT(*) as open_positions,
                COALESCE(SUM(entry_price * contracts * 100), 0) as total_exposure,
                COALESCE(SUM(unrealized_pnl), 0) as unrealized_pnl
            FROM autonomous_open_positions
        """)
        pos_data = cursor.fetchone()
        open_positions = pos_data[0] or 0
        total_exposure = pos_data[1] or 0
        unrealized_pnl = pos_data[2] or 0

        # Get max drawdown from equity snapshots
        cursor.execute("""
            SELECT COALESCE(MAX(max_drawdown_pct), 0) as max_dd
            FROM autonomous_equity_snapshots
        """)
        max_dd = cursor.fetchone()[0] or 0

        conn.close()

        # Calculate risk metrics
        starting_capital = 5000
        daily_loss_limit = -500  # $500 daily loss limit
        position_limit = 5000  # Max position size

        return {
            "success": True,
            "data": {
                "daily_pnl": float(today_pnl),
                "daily_loss_limit": daily_loss_limit,
                "daily_loss_pct": (today_pnl / starting_capital * 100) if starting_capital > 0 else 0,
                "is_daily_limit_hit": today_pnl <= daily_loss_limit,
                "open_positions": open_positions,
                "total_exposure": float(total_exposure),
                "max_position_size": position_limit,
                "exposure_pct": (total_exposure / starting_capital * 100) if starting_capital > 0 else 0,
                "unrealized_pnl": float(unrealized_pnl),
                "max_drawdown_pct": float(max_dd),
                "risk_score": min(100, max(0, 100 - abs(max_dd) * 2))  # Simple risk score
            }
        }
    except Exception as e:
        print(f"Error getting risk status: {e}")
        return {"success": False, "data": None, "error": str(e)}

@app.get("/api/autonomous/risk/metrics")
async def get_risk_metrics(days: int = 30):
    """Get historical risk metrics"""
    if not trader_available:
        return {"success": False, "message": "Trader not configured", "data": []}

    try:
        import pandas as pd
        from datetime import datetime, timedelta
        conn = get_connection()

        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

        query = """
            SELECT
                snapshot_date as date,
                max_drawdown_pct,
                daily_pnl,
                total_return_pct,
                sharpe_ratio,
                win_rate
            FROM autonomous_equity_snapshots
            WHERE snapshot_date >= %s
            ORDER BY snapshot_date ASC
        """
        metrics = pd.read_sql_query(query, conn, params=(start_date,))
        conn.close()

        result = []
        for _, row in metrics.iterrows():
            result.append({
                "date": str(row['date']),
                "max_drawdown_pct": float(row['max_drawdown_pct']) if row['max_drawdown_pct'] else 0,
                "daily_pnl": float(row['daily_pnl']) if row['daily_pnl'] else 0,
                "total_return_pct": float(row['total_return_pct']) if row['total_return_pct'] else 0,
                "sharpe_ratio": float(row['sharpe_ratio']) if row['sharpe_ratio'] else 0,
                "win_rate": float(row['win_rate']) if row['win_rate'] else 0
            })

        return {"success": True, "data": result}
    except Exception as e:
        print(f"Error getting risk metrics: {e}")
        return {"success": False, "data": [], "error": str(e)}

@app.get("/api/autonomous/ml/model-status")
async def get_ml_model_status():
    """Get ML model training status"""
    # ML model is not yet implemented - return placeholder data
    return {
        "success": True,
        "data": {
            "is_trained": False,
            "accuracy": 0,
            "training_samples": 0,
            "last_trained": None,
            "features_used": [],
            "model_version": "0.0.0",
            "status": "Not implemented - ML features coming soon"
        }
    }

@app.get("/api/autonomous/ml/predictions/recent")
async def get_recent_ml_predictions(limit: int = 10):
    """Get recent ML predictions"""
    # ML predictions not yet implemented - return empty list
    return {
        "success": True,
        "data": [],
        "message": "ML predictions not yet implemented"
    }

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

        # Get VIX data for additional context using Polygon.io
        polygon_key = os.getenv('POLYGON_API_KEY')
        vix = 15.0  # Default fallback

        try:
            print(f"  🔄 Fetching VIX from Polygon.io...")
            if polygon_key:
                try:
                    import requests
                    from datetime import datetime, timedelta

                    # Get last trading day's VIX close
                    to_date = datetime.now().strftime('%Y-%m-%d')
                    from_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')

                    url = f"https://api.polygon.io/v2/aggs/ticker/VIX/range/1/day/{from_date}/{to_date}"
                    params = {"apiKey": polygon_key, "sort": "desc", "limit": 1}

                    response = requests.get(url, params=params, timeout=10)
                    if response.status_code == 200:
                        data = response.json()
                        if data.get('status') == 'OK' and data.get('results'):
                            vix = float(data['results'][0]['c'])  # 'c' is close price
                            print(f"  ✅ VIX from Polygon.io: {vix}")
                        else:
                            print(f"  ⚠️ Polygon.io returned no VIX data")
                    else:
                        print(f"  ⚠️ Polygon.io HTTP {response.status_code}")
                except Exception as polygon_error:
                    print(f"  ⚠️ Polygon.io VIX fetch failed: {polygon_error}")
            else:
                print(f"  ⚠️ No Polygon.io API key - using default VIX")
        except Exception as vix_error:
            print(f"Warning: Could not fetch VIX: {vix_error}, using default {vix}")

        # Prepare market data for optimizer
        # Use the correct keys from get_net_gamma response
        # CRITICAL: Handle None values properly - use 'or 0' to provide defaults
        market_data = {
            'spot_price': float(gex_data.get('spot_price') or 0),
            'net_gex': float(gex_data.get('net_gex') or 0),
            'flip_point': float(gex_data.get('flip_point') or 0),
            'call_wall': float(gex_data.get('call_wall') or 0),
            'put_wall': float(gex_data.get('put_wall') or 0),
            'call_wall_gamma': float(gex_data.get('call_wall') or 0),
            'put_wall_gamma': float(gex_data.get('put_wall') or 0),
            'vix': float(vix or 15.0)
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

    conn = get_connection()
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

                net_gex = gex_data.get('net_gex') or 0
                spot_price = gex_data.get('spot_price') or 0
                flip_point = gex_data.get('flip_point') or 0
                call_wall = gex_data.get('call_wall') or 0
                put_wall = gex_data.get('put_wall') or 0

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

        conn = get_connection()
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
        import pandas as pd

        conn = get_connection()

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
        import pandas as pd

        conn = get_connection()

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

    conn = get_connection()
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

                # Use Polygon.io for price data (reuse existing function with caching)
                current_price = spot_price
                price_data = get_cached_price_data(symbol, current_price)

                # Calculate volume ratio
                if len(price_data.get('1d', [])) >= 20:
                    recent_volume = price_data['1d'][-1]['volume']
                    avg_volume = sum(d['volume'] for d in price_data['1d'][-20:]) / 20
                    volume_ratio = recent_volume / avg_volume if avg_volume > 0 else 1.0
                else:
                    volume_ratio = 1.0

                # Format gamma data for analyzer
                gamma_data_formatted = {
                    'net_gamma': net_gex,
                    'expirations': [{
                        'expiration_date': datetime.now() + timedelta(days=7),
                        'dte': 7,
                        'expiration_type': 'weekly',
                        'call_strikes': [{
                            'strike': call_wall if call_wall > 0 else current_price * 1.02,
                            'gamma_exposure': net_gex / 2,
                            'open_interest': 1000
                        }],
                        'put_strikes': [{
                            'strike': put_wall if put_wall > 0 else current_price * 0.98,
                            'gamma_exposure': net_gex / 2,
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

        conn = get_connection()
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
        import pandas as pd

        conn = get_connection()

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

        conn = get_connection()
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

    conn = get_connection()
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

        conn = get_connection()
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
        import pandas as pd

        conn = get_connection()

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

        conn = get_connection()
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
        import pandas as pd

        conn = get_connection()

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
        import pandas as pd

        conn = get_connection()

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

# Import autonomous trader routes
from backend.autonomous_routes import router as autonomous_router

# Import AI intelligence enhancement routes
from backend.ai_intelligence_routes import router as ai_intelligence_router

# Include autonomous trader routes
app.include_router(autonomous_router)

# Include AI intelligence enhancement routes
app.include_router(ai_intelligence_router)

# ==============================================================================
# POLYGON.IO PRICE DATA CACHING - Psychology page fetches once per day
# ==============================================================================
_polygon_price_cache = {}
_polygon_price_cache_ttl = 86400  # 24 hours cache (psychology updates once per day)

def get_cached_price_data(symbol: str, current_price: float):
    """
    Get price data for symbol with caching using Polygon.io API
    Cache TTL: 24 hours (86400 seconds)

    Psychology page design: Fetch once per day, manual refresh only

    This function makes 5 Polygon.io API calls:
    - 90d daily data
    - 30d 4-hour data
    - 14d hourly data
    - 7d 15-minute data
    - 3d 5-minute data

    With 24h caching: 5 API calls per day (only on first load or manual refresh)
    """
    cache_key = f"price_data_{symbol}"
    now = datetime.now()

    # Check if we have cached data that's still fresh
    if cache_key in _polygon_price_cache:
        cached_data, cache_time = _polygon_price_cache[cache_key]
        age_seconds = (now - cache_time).total_seconds()

        if age_seconds < _polygon_price_cache_ttl:
            print(f"✅ Using cached price data (age: {age_seconds:.0f}s)")
            return cached_data
        else:
            print(f"⏰ Cache expired (age: {age_seconds:.0f}s > {_polygon_price_cache_ttl}s)")

    # Cache miss or expired - fetch fresh data from Polygon.io
    print(f"🔄 Fetching fresh price data from Polygon.io (5 API calls)")

    polygon_key = os.getenv("POLYGON_API_KEY")
    if not polygon_key:
        print(f"❌ No POLYGON_API_KEY configured in environment")
        print(f"❌ Available env vars: {', '.join([k for k in os.environ.keys() if 'POLYGON' in k or 'API' in k])}")
        raise HTTPException(
            status_code=503,
            detail=f"Polygon.io API key not configured. Cannot fetch price data for psychology analysis."
        )

    print(f"✅ POLYGON_API_KEY is set (length: {len(polygon_key)} chars)")
    print(f"✅ API key starts with: {polygon_key[:8]}...")

    try:
        import pandas as pd

        def fetch_polygon_bars(symbol, multiplier, timespan, days_back):
            """Fetch price bars from Polygon.io"""
            try:
                to_date = datetime.now().strftime('%Y-%m-%d')
                from_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')

                url = f"https://api.polygon.io/v2/aggs/ticker/{symbol}/range/{multiplier}/{timespan}/{from_date}/{to_date}"
                params = {"apiKey": polygon_key, "sort": "asc", "limit": 50000}

                print(f"    🌐 Calling Polygon.io: {url}")
                print(f"    📅 Date range: {from_date} to {to_date}")

                response = requests.get(url, params=params, timeout=10)

                print(f"    📡 Response status: {response.status_code}")

                if response.status_code == 200:
                    data = response.json()
                    status = data.get('status', '')
                    results_count = data.get('resultsCount', 0)

                    print(f"    📊 Polygon status: {status}")
                    print(f"    📊 Results count: {results_count}")

                    if status in ['OK', 'DELAYED'] and data.get('results'):
                        results = data['results']
                        print(f"    ✅ Got {len(results)} bars")
                        return [
                            {
                                'close': bar['c'],
                                'high': bar['h'],
                                'low': bar['l'],
                                'volume': bar['v']
                            }
                            for bar in results
                        ]
                    else:
                        print(f"    ⚠️ Polygon.io status: {status}, results: {results_count}")
                        print(f"    ⚠️ Full response: {data}")
                        return []
                elif response.status_code == 401:
                    print(f"    ❌ Polygon.io 401 Unauthorized - API key is invalid")
                    print(f"    ❌ Response: {response.text}")
                    return []
                elif response.status_code == 403:
                    print(f"    ❌ Polygon.io 403 Forbidden - API key may not have access to this data")
                    print(f"    ❌ Response: {response.text}")
                    return []
                elif response.status_code == 429:
                    print(f"    ❌ Polygon.io 429 Rate Limit - too many requests")
                    print(f"    ❌ Response: {response.text}")
                    return []
                else:
                    print(f"    ⚠️ Polygon.io HTTP {response.status_code}")
                    print(f"    ⚠️ Response: {response.text[:500]}")
                    return []
            except Exception as e:
                print(f"    ❌ Polygon.io error: {e}")
                import traceback
                traceback.print_exc()
                return []

        price_data = {}

        # Daily data (90 days for RSI calculation)
        print(f"  🔄 Fetching 1d data...")
        price_data['1d'] = fetch_polygon_bars(symbol, 1, 'day', 90)
        print(f"  📊 1d data: {len(price_data['1d'])} bars")

        # 4-hour data (30 days)
        print(f"  🔄 Fetching 4h data...")
        price_data['4h'] = fetch_polygon_bars(symbol, 4, 'hour', 30)
        print(f"  📊 4h data: {len(price_data['4h'])} bars")

        # 1-hour data (14 days)
        print(f"  🔄 Fetching 1h data...")
        price_data['1h'] = fetch_polygon_bars(symbol, 1, 'hour', 14)
        print(f"  📊 1h data: {len(price_data['1h'])} bars")

        # 15-minute data (7 days)
        print(f"  🔄 Fetching 15m data...")
        price_data['15m'] = fetch_polygon_bars(symbol, 15, 'minute', 7)
        print(f"  📊 15m data: {len(price_data['15m'])} bars")

        # 5-minute data (3 days)
        print(f"  🔄 Fetching 5m data...")
        price_data['5m'] = fetch_polygon_bars(symbol, 5, 'minute', 3)
        print(f"  📊 5m data: {len(price_data['5m'])} bars")

        # CRITICAL: Validate that we got actual data
        if len(price_data['1d']) == 0:
            print(f"❌ Polygon.io returned EMPTY data for {symbol}")
            print(f"   This usually means API key is invalid or rate limit exceeded")
            raise ValueError(f"Polygon.io returned no data for {symbol}. Check API key and rate limits.")

        # Cache the result only if we have valid data
        _polygon_price_cache[cache_key] = (price_data, now)
        print(f"✅ Cached fresh price data for {_polygon_price_cache_ttl}s (24 hours)")

        return price_data

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        # NO FALLBACK - Never use mock data
        print(f"❌ Could not fetch price data from Polygon.io: {e}")
        raise HTTPException(
            status_code=503,
            detail=f"Failed to fetch price data for {symbol}. Polygon.io API error: {str(e)}"
        )

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

        # Try to use cached data from database if live API fails
        if not gex_data or 'error' in gex_data:
            error_type = gex_data.get('error', 'unknown') if gex_data else 'no_data'
            print(f"⚠️ Live GEX API unavailable: {error_type}")
            print("📊 Attempting to use cached data from database...")

            # Try to get the most recent cached regime data
            try:
                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT spy_price, net_gamma, primary_regime_type, secondary_regime_type,
                           confidence_score, trade_direction, risk_level, description,
                           rsi_5m, rsi_15m, rsi_1h, rsi_4h, rsi_1d, timestamp
                    FROM regime_signals
                    WHERE timestamp > NOW() - INTERVAL '24 hours'
                    ORDER BY timestamp DESC
                    LIMIT 1
                """)
                cached_row = cursor.fetchone()
                conn.close()

                if cached_row:
                    print(f"✅ Using cached data from {cached_row[13]}")
                    # Build response from cached data
                    cached_response = {
                        "analysis": {
                            "timestamp": str(cached_row[13]),
                            "spy_price": cached_row[0] or 590.0,
                            "regime": {
                                "primary_type": cached_row[2] or "NEUTRAL",
                                "secondary_type": cached_row[3],
                                "confidence": cached_row[4] or 0.7,
                                "description": cached_row[7] or "Cached analysis from database",
                                "detailed_explanation": f"Data cached at {cached_row[13]}. Live API unavailable.",
                                "trade_direction": cached_row[5] or "NEUTRAL",
                                "risk_level": cached_row[6] or "MEDIUM",
                                "timeline": None,
                                "price_targets": {},
                                "psychology_trap": None,
                                "supporting_factors": ["Using cached data - live API unavailable"]
                            },
                            "rsi_analysis": {
                                "score": 50,
                                "individual_rsi": {
                                    "5m": cached_row[8],
                                    "15m": cached_row[9],
                                    "1h": cached_row[10],
                                    "4h": cached_row[11],
                                    "1d": cached_row[12]
                                },
                                "aligned_count": {"overbought": 0, "oversold": 0, "extreme_overbought": 0, "extreme_oversold": 0},
                                "coiling_detected": False
                            },
                            "current_walls": {"call_wall": None, "put_wall": None},
                            "expiration_analysis": {},
                            "forward_gex": {},
                            "volume_ratio": 1.0,
                            "alert_level": {"level": "info", "reason": "Using cached data"}
                        },
                        "market_status": {
                            "is_open": False,
                            "timestamp": str(datetime.now()),
                            "status_text": "Using cached data - API unavailable",
                            "data_age_minutes": 0
                        },
                        "trading_guide": None,
                        "ai_recommendation": None,
                        "historical_comparison": None,
                        "backtest_stats": None,
                        "_cached": True,
                        "_cache_time": str(cached_row[13])
                    }
                    return JSONResponse(cached_response)
            except Exception as cache_err:
                print(f"❌ Failed to retrieve cached data: {cache_err}")

            # No cached data available - return proper error
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
            print(f"  DEBUG: Calling analyze_current_market_complete with:")
            print(f"    - current_price: {current_price}")
            print(f"    - price_data keys: {list(price_data.keys())}")
            print(f"    - price_data['1d'] length: {len(price_data.get('1d', []))}")
            print(f"    - gamma_data keys: {list(gamma_data_formatted.keys())}")
            print(f"    - volume_ratio: {volume_ratio}")

            analysis = analyze_current_market_complete(
                current_price=current_price,
                price_data=price_data,
                gamma_data=gamma_data_formatted,
                volume_ratio=volume_ratio
            )
            print(f"✅ Analysis complete!")
        except Exception as analysis_error:
            print(f"❌ Error in analyze_current_market_complete:")
            print(f"❌ Error type: {type(analysis_error).__name__}")
            print(f"❌ Error message: {str(analysis_error)}")
            import traceback
            import sys
            traceback.print_exc()
            sys.stdout.flush()  # Force flush to ensure error appears in logs

            # Re-raise with more context
            raise HTTPException(
                status_code=500,
                detail=f"Psychology analysis failed: {type(analysis_error).__name__}: {str(analysis_error)}"
            )

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

        # Generate AI-powered trade recommendation
        try:
            from ai_trade_recommendations import get_ai_recommendation
            ai_recommendation = get_ai_recommendation(symbol, analysis)
            print(f"✅ AI recommendation generated")
        except Exception as ai_error:
            print(f"⚠️  AI recommendation failed: {ai_error}")
            ai_recommendation = None

        # Save daily gamma snapshot and get historical comparison
        historical_comparison = None
        backtest_stats = None
        try:
            from historical_tracking import save_daily_gamma_snapshot, get_historical_comparison, calculate_regime_backtest_statistics

            # Save snapshot for historical tracking (non-blocking)
            try:
                save_daily_gamma_snapshot(symbol, gamma_data_formatted, current_price)
            except Exception as snap_err:
                print(f"⚠️  Snapshot save failed (non-critical): {snap_err}")

            # Get historical comparison (non-blocking)
            try:
                current_net_gamma = gamma_data_formatted.get('net_gamma', 0)
                historical_comparison = get_historical_comparison(symbol, current_net_gamma)
            except Exception as comp_err:
                print(f"⚠️  Historical comparison failed (non-critical): {comp_err}")

            # Get backtest statistics for current regime (non-blocking)
            try:
                regime_type = analysis['regime']['primary_type']
                backtest_stats = calculate_regime_backtest_statistics(regime_type)
            except Exception as stats_err:
                print(f"⚠️  Backtest stats failed (non-critical): {stats_err}")

            if historical_comparison or backtest_stats:
                print(f"✅ Historical tracking updated")
        except ImportError as import_err:
            print(f"⚠️  Historical tracking not available (module not found): {import_err}")
        except Exception as hist_error:
            print(f"⚠️  Historical tracking failed: {hist_error}")
            import traceback
            traceback.print_exc()

        # Add market status and metadata
        import pytz
        eastern = pytz.timezone('US/Eastern')
        now = datetime.now(eastern)
        market_open = now.weekday() < 5 and 9 <= now.hour < 16  # Simple check

        market_status = {
            'is_open': market_open,
            'timestamp': now.isoformat(),
            'market_time': now.strftime('%I:%M %p ET'),
            'status_text': 'OPEN' if market_open else 'CLOSED',
            'data_age_minutes': 0 if market_open else int((now.hour - 16) * 60) if now.hour >= 16 else 0
        }

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
        if ai_recommendation:
            ai_recommendation = convert_numpy_types(ai_recommendation)
        if historical_comparison:
            historical_comparison = convert_numpy_types(historical_comparison)
        if backtest_stats:
            backtest_stats = convert_numpy_types(backtest_stats)

        return {
            "success": True,
            "symbol": symbol,
            "analysis": analysis,
            "trading_guide": trading_guide,
            "ai_recommendation": ai_recommendation,
            "market_status": market_status,
            "historical_comparison": historical_comparison,
            "backtest_stats": backtest_stats
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
        

        conn = get_connection()
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
        

        conn = get_connection()
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
        

        conn = get_connection()
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

    Returns:
        {
            "success": bool,
            "count": int,
            "statistics": List[dict],
            "summary": {
                "total_scenarios": int,
                "avg_failure_rate": float,
                "most_dangerous_trap": str,
                "safest_fade": str
            }
        }
    """
    try:
        

        conn = get_connection()
        c = conn.cursor()

        # Get sucker statistics
        c.execute('SELECT * FROM sucker_statistics ORDER BY failure_rate DESC')

        columns = [desc[0] for desc in c.description]
        rows = c.fetchall()

        stats = []
        for row in rows:
            stat = dict(zip(columns, row))
            stats.append(stat)

        conn.close()

        # Calculate summary statistics
        summary = {
            "total_scenarios": len(stats),
            "avg_failure_rate": 0,
            "most_dangerous_trap": "N/A",
            "safest_fade": "N/A"
        }

        if stats:
            # Average failure rate
            summary["avg_failure_rate"] = sum(s.get('failure_rate', 0) for s in stats) / len(stats)

            # Most dangerous trap (highest failure rate)
            most_dangerous = max(stats, key=lambda x: x.get('failure_rate', 0))
            summary["most_dangerous_trap"] = most_dangerous.get('scenario_type', 'N/A')

            # Safest fade (lowest failure rate)
            safest = min(stats, key=lambda x: x.get('failure_rate', 0))
            summary["safest_fade"] = safest.get('scenario_type', 'N/A')

        return {
            "success": True,
            "count": len(stats),
            "statistics": stats,
            "summary": summary
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
# PUSH NOTIFICATION ENDPOINTS (Browser Push API)
# ==============================================================================

# Import push notification service
try:
    import sys
    from pathlib import Path
    backend_dir = Path(__file__).parent
    sys.path.insert(0, str(backend_dir))
    from push_notification_service import get_push_service
    push_service = get_push_service()
    push_notifications_available = True
except Exception as e:
    print(f"⚠️ Push notifications not available: {e}")
    push_service = None
    push_notifications_available = False


@app.get("/api/notifications/vapid-public-key")
async def get_vapid_public_key():
    """
    Get VAPID public key for push notification subscriptions

    Returns:
        {
            "public_key": "BKq..."  # Base64-encoded public key
        }
    """
    if not push_notifications_available or not push_service:
        raise HTTPException(status_code=503, detail="Push notifications not configured")

    public_key = push_service.get_vapid_public_key()

    if not public_key:
        raise HTTPException(status_code=500, detail="VAPID key not available")

    return {
        "success": True,
        "public_key": public_key
    }


@app.post("/api/notifications/subscribe")
async def subscribe_to_push_notifications(request: dict):
    """
    Subscribe to push notifications

    Request body:
    {
        "subscription": {
            "endpoint": "https://...",
            "keys": {
                "p256dh": "...",
                "auth": "..."
            }
        },
        "preferences": {
            "enabled": true,
            "criticalAlerts": true,
            "highAlerts": true,
            "liberationSetups": true,
            "falseFloors": true,
            "regimeChanges": true,
            "sound": true
        }
    }

    Returns:
        {"success": true}
    """
    if not push_notifications_available or not push_service:
        raise HTTPException(status_code=503, detail="Push notifications not configured")

    try:
        subscription = request.get('subscription')
        preferences = request.get('preferences', {})

        if not subscription:
            raise HTTPException(status_code=400, detail="Subscription object required")

        success = push_service.save_subscription(subscription, preferences)

        if not success:
            raise HTTPException(status_code=500, detail="Failed to save subscription")

        return {
            "success": True,
            "message": "Subscription saved successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error subscribing: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/notifications/unsubscribe")
async def unsubscribe_from_push_notifications(request: dict):
    """
    Unsubscribe from push notifications

    Request body:
    {
        "endpoint": "https://..."
    }

    Returns:
        {"success": true}
    """
    if not push_notifications_available or not push_service:
        raise HTTPException(status_code=503, detail="Push notifications not configured")

    try:
        endpoint = request.get('endpoint')

        if not endpoint:
            raise HTTPException(status_code=400, detail="Endpoint required")

        success = push_service.remove_subscription(endpoint)

        return {
            "success": True,
            "message": "Unsubscribed successfully" if success else "Subscription not found"
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error unsubscribing: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/notifications/preferences")
async def update_notification_preferences(request: dict):
    """
    Update notification preferences

    Request body:
    {
        "endpoint": "https://...",  # Optional, use first subscription if not provided
        "preferences": {
            "enabled": true,
            "criticalAlerts": true,
            ...
        }
    }

    Returns:
        {"success": true}
    """
    if not push_notifications_available or not push_service:
        raise HTTPException(status_code=503, detail="Push notifications not configured")

    try:
        endpoint = request.get('endpoint')
        preferences = request.get('preferences', {})

        if not preferences:
            raise HTTPException(status_code=400, detail="Preferences required")

        # If no endpoint provided, update first subscription (single-user mode)
        if not endpoint:
            subscriptions = push_service.get_all_subscriptions()
            if not subscriptions:
                raise HTTPException(status_code=404, detail="No subscriptions found")
            endpoint = subscriptions[0]['endpoint']

        success = push_service.update_preferences(endpoint, preferences)

        if not success:
            raise HTTPException(status_code=404, detail="Subscription not found")

        return {
            "success": True,
            "message": "Preferences updated successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error updating preferences: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/notifications/test")
async def send_test_notification():
    """
    Send test push notification to all subscribed users

    Returns:
        {"success": true, "stats": {...}}
    """
    if not push_notifications_available or not push_service:
        raise HTTPException(status_code=503, detail="Push notifications not configured")

    try:
        stats = push_service.broadcast_notification(
            title="Test Alert",
            body="This is a test notification from AlphaGEX",
            alert_level="HIGH",
            data={"type": "test"}
        )

        return {
            "success": True,
            "message": "Test notification sent",
            "stats": stats
        }

    except Exception as e:
        print(f"❌ Error sending test notification: {e}")
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
    import math
    from decimal import Decimal

    def safe_round(value, decimals=2, default=0):
        """Round a value, returning default if inf/nan or any non-serializable float"""
        if value is None:
            return default
        try:
            # Convert to float first to handle Decimal and other numeric types
            float_val = float(value)
            if math.isnan(float_val) or math.isinf(float_val):
                return default
            return round(float_val, decimals)
        except (ValueError, TypeError, OverflowError):
            return default

    try:
        conn = get_connection()
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # PostgreSQL doesn't support parameterized LIMIT - use validated int literal
        if strategy_name:
            c.execute(f'''
                SELECT *
                FROM backtest_results
                WHERE strategy_name = %s
                ORDER BY timestamp DESC
                LIMIT {int(limit)}
            ''', (strategy_name,))
        else:
            c.execute(f'''
                SELECT *
                FROM backtest_results
                ORDER BY timestamp DESC
                LIMIT {int(limit)}
            ''')

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
                'win_rate': safe_round(row['win_rate'], 1),
                'avg_win_pct': safe_round(row['avg_win_pct'], 2),
                'avg_loss_pct': safe_round(row['avg_loss_pct'], 2),
                'largest_win_pct': safe_round(row['largest_win_pct'], 2),
                'largest_loss_pct': safe_round(row['largest_loss_pct'], 2),
                'expectancy_pct': safe_round(row['expectancy_pct'], 2),
                'total_return_pct': safe_round(row['total_return_pct'], 2),
                'max_drawdown_pct': safe_round(row['max_drawdown_pct'], 2),
                'sharpe_ratio': safe_round(row['sharpe_ratio'], 2),
                'avg_trade_duration_days': safe_round(row['avg_trade_duration_days'], 1)
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
        conn = get_connection()
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

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
        conn = get_connection()
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        c.execute('''
            SELECT *
            FROM backtest_results
            WHERE expectancy_pct >= %s
            AND win_rate >= %s
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


@app.post("/api/backtests/run")
async def run_backtests(request: dict = None):
    """
    Run all backtests for specified symbol and date range

    Request body (optional):
        {
            "symbol": "SPY",
            "start_date": "2022-01-01",
            "end_date": "2024-12-31"
        }

    Returns:
        Backtest execution status and results
    """
    try:
        import subprocess
        from datetime import datetime, timedelta

        # Parse request parameters with defaults
        if request is None:
            request = {}

        symbol = request.get('symbol', 'SPY')

        # Default to last 2 years if not specified
        if 'end_date' not in request:
            end_date = datetime.now().strftime('%Y-%m-%d')
        else:
            end_date = request.get('end_date')

        if 'start_date' not in request:
            start_date = (datetime.now() - timedelta(days=730)).strftime('%Y-%m-%d')
        else:
            start_date = request.get('start_date')

        print(f"\n🚀 Running backtests for {symbol} from {start_date} to {end_date}")

        # Run the backtest script with environment variables
        result = subprocess.run(
            ['python', 'run_all_backtests.py',
             '--symbol', symbol,
             '--start', start_date,
             '--end', end_date],
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout
            env=os.environ.copy()  # Pass environment variables to subprocess
        )

        if result.returncode == 0:
            print("✅ Backtests completed successfully")

            # Fetch the results
            

            conn = get_connection()
            
            c = conn.cursor()

            # Get latest results
            c.execute('''
                SELECT COUNT(*) as count
                FROM backtest_results
                WHERE symbol = ?
            ''', (symbol,))

            count_row = c.fetchone()
            result_count = count_row['count'] if count_row else 0

            conn.close()

            return {
                "success": True,
                "message": f"Backtests completed successfully for {symbol}",
                "symbol": symbol,
                "start_date": start_date,
                "end_date": end_date,
                "results_count": result_count,
                "output": result.stdout
            }
        else:
            print(f"❌ Backtests failed: {result.stderr}")

            # Check for specific errors
            error_message = result.stderr
            if "ModuleNotFoundError: No module named 'pandas'" in error_message:
                error_detail = "Missing required dependencies: pandas and numpy. Install with: pip install pandas numpy scipy"
            elif "ModuleNotFoundError" in error_message:
                module_name = error_message.split("'")[1] if "'" in error_message else "unknown"
                error_detail = f"Missing required dependency: {module_name}. Install with: pip install {module_name}"
            else:
                error_detail = "Backtest execution failed. Check backend logs for details."

            raise HTTPException(
                status_code=500,
                detail=error_detail + f"\n\nFull error:\n{result.stderr}"
            )

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": "Backtest execution timed out (>5 minutes)"
        }
    except Exception as e:
        print(f"❌ Error running backtests: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@app.get("/api/backtests/smart-recommendations")
async def get_smart_recommendations():
    """
    Smart Strategy Picker - Match current market conditions to best backtested strategies

    Returns:
        - Current market conditions
        - Top 3-5 strategies that match current conditions
        - Confidence scores based on condition matching
        - Actionable setup links
    """
    try:
        

        # 1. Get current market conditions from latest Psychology Analysis
        gex_data = api_client.get_net_gamma('SPY')

        if not gex_data or 'error' in gex_data:
            raise HTTPException(
                status_code=404,
                detail="No current market data available. Run Psychology Analysis first."
            )

        current_price = gex_data.get('price', 0)
        net_gex = gex_data.get('net_gex', 0)

        # Get RSI and regime detection
        conn = get_connection()
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Get latest regime signal
        c.execute('''
            SELECT
                primary_regime_type,
                confidence_score,
                rsi_score,
                vix_current
            FROM regime_signals
            ORDER BY timestamp DESC
            LIMIT 1
        ''')

        regime_row = c.fetchone()

        if not regime_row:
            raise HTTPException(
                status_code=404,
                detail="No regime data available. Run Psychology Analysis first."
            )

        current_pattern = regime_row['primary_regime_type']
        rsi_score = regime_row['rsi_score'] or 50
        vix = regime_row['vix_current'] or 15
        pattern_confidence = regime_row['confidence_score'] or 0

        market_conditions = {
            'current_pattern': current_pattern,
            'spy_price': current_price,
            'vix': vix,
            'net_gex': net_gex,
            'rsi_score': rsi_score,
            'confidence': pattern_confidence
        }

        # 2. Get backtest results for strategies matching this pattern
        c.execute('''
            SELECT
                strategy_name,
                symbol,
                start_date,
                end_date,
                total_trades,
                win_rate,
                expectancy_pct,
                avg_win_pct,
                avg_loss_pct,
                max_drawdown_pct,
                sharpe_ratio
            FROM backtest_results
            WHERE strategy_name LIKE %s
            OR strategy_name LIKE '%%TRAP%%'
            OR strategy_name LIKE '%%GEX%%'
            ORDER BY expectancy_pct DESC
        ''', (f'%{current_pattern}%',))

        strategy_rows = c.fetchall()

        # 3. Calculate confidence scores based on condition matching
        recommendations = []

        for row in strategy_rows:
            conditions_met = 0
            conditions_total = 5

            # Condition 1: Expectancy > 0.5%
            if row['expectancy_pct'] > 0.5:
                conditions_met += 1

            # Condition 2: Win rate > 55%
            if row['win_rate'] > 55:
                conditions_met += 1

            # Condition 3: Sufficient sample size (>20 trades)
            if row['total_trades'] > 20:
                conditions_met += 1

            # Condition 4: Max drawdown manageable (<20%)
            if abs(row['max_drawdown_pct']) < 20:
                conditions_met += 1

            # Condition 5: Positive Sharpe ratio
            if row['sharpe_ratio'] > 0.5:
                conditions_met += 1

            # Calculate confidence score (0-100)
            confidence_score = (conditions_met / conditions_total) * 100

            # Determine market match description
            if current_pattern.upper() in row['strategy_name'].upper():
                market_match = f"Exact match for {current_pattern.replace('_', ' ').title()}"
            elif 'TRAP' in row['strategy_name'].upper():
                market_match = f"Psychology pattern strategy"
            elif 'GEX' in row['strategy_name'].upper():
                market_match = f"GEX-based strategy"
            else:
                market_match = "General strategy"

            recommendations.append({
                'strategy_name': row['strategy_name'],
                'win_rate': row['win_rate'],
                'expectancy_pct': row['expectancy_pct'],
                'total_trades': row['total_trades'],
                'confidence_score': confidence_score,
                'conditions_met': conditions_met,
                'conditions_total': conditions_total,
                'market_match': market_match,
                'avg_win_pct': row['avg_win_pct'],
                'avg_loss_pct': row['avg_loss_pct'],
                'sharpe_ratio': row['sharpe_ratio'],
                'setup_link': f'/psychology?pattern={row["strategy_name"]}'
            })

        # Sort by confidence score, then expectancy
        recommendations.sort(key=lambda x: (x['confidence_score'], x['expectancy_pct']), reverse=True)

        conn.close()

        return {
            'success': True,
            'market_conditions': market_conditions,
            'recommendations': recommendations[:10],  # Top 10
            'total_matches': len(recommendations)
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error getting smart recommendations: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate recommendations: {str(e)}"
        )


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

    except ImportError as e:
        raise HTTPException(
            status_code=503,
            detail="AI Strategy Optimizer requires langchain. Install with: pip install langchain langchain-anthropic"
        )
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e)
        )
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

    except ImportError as e:
        raise HTTPException(
            status_code=503,
            detail="AI Strategy Optimizer requires langchain. Install with: pip install langchain langchain-anthropic"
        )
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e)
        )
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
    Get multi-timeframe RSI analysis only using Polygon.io
    Useful for quick RSI checks without full regime analysis
    """
    try:
        # Get current price from GEX data
        gex_data = api_client.get_net_gamma(symbol)
        current_price = gex_data.get('spot_price', 0)

        # Use Polygon.io for price data (with caching)
        price_data = get_cached_price_data(symbol, current_price)

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
    Quick psychology trap check for scanners using Polygon.io (lightweight version)
    Returns only regime type, confidence, and trade direction
    """
    try:
        # Get current price from GEX data
        gex_data = api_client.get_net_gamma(symbol)
        current_price = gex_data.get('spot_price', 0)

        # Use Polygon.io for price data (with caching)
        price_data = get_cached_price_data(symbol, current_price)

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


@app.get("/api/database/stats")
async def get_database_stats():
    """
    Get statistics about all database tables
    Returns table names, row counts, and sample data
    """
    try:
        

        conn = get_connection()
        cursor = conn.cursor()

        # Get all tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = [row[0] for row in cursor.fetchall()]

        table_stats = []

        for table_name in tables:
            # Get row count
            cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            row_count = cursor.fetchone()[0]

            # Get column info
            cursor.execute(f"PRAGMA table_info({table_name})")
            columns = [{"name": col[1], "type": col[2]} for col in cursor.fetchall()]

            # Get sample data (first 5 rows)
            sample_data = []
            if row_count > 0:
                cursor.execute(f"SELECT * FROM {table_name} LIMIT 5")
                rows = cursor.fetchall()
                column_names = [col["name"] for col in columns]

                for row in rows:
                    sample_data.append(dict(zip(column_names, row)))

            table_stats.append({
                "table_name": table_name,
                "row_count": row_count,
                "columns": columns,
                "sample_data": sample_data
            })

        conn.close()

        return {
            "success": True,
            "database_url": os.getenv('DATABASE_URL', 'Not configured'),
            "total_tables": len(tables),
            "tables": table_stats,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database stats error: {str(e)}")


@app.get("/api/test-connections")
async def test_api_connections():
    """
    Test connections to external APIs (Trading Volatility and Polygon)
    Returns detailed status for each API including response times and data quality
    """
    import time

    results = {
        "timestamp": datetime.now().isoformat(),
        "trading_volatility": {
            "status": "unknown",
            "response_time_ms": 0,
            "error": None,
            "data_quality": None,
            "test_symbol": "SPY",
            "fields_received": []
        },
        "polygon": {
            "status": "unknown",
            "response_time_ms": 0,
            "error": None,
            "data_quality": None,
            "test_symbol": "VIX",
            "vix_value": None
        },
        "overall_status": "unknown"
    }

    # Test Trading Volatility API
    try:
        api_client = TradingVolatilityAPI()
        start_time = time.time()

        gex_data = api_client.get_net_gamma("SPY")

        elapsed_ms = int((time.time() - start_time) * 1000)
        results["trading_volatility"]["response_time_ms"] = elapsed_ms

        if gex_data and not gex_data.get('error'):
            results["trading_volatility"]["status"] = "connected"
            results["trading_volatility"]["fields_received"] = list(gex_data.keys())

            # Check data quality
            required_fields = ['net_gex', 'spot_price', 'collection_date']
            missing_fields = [f for f in required_fields if f not in gex_data]

            if missing_fields:
                results["trading_volatility"]["data_quality"] = f"incomplete (missing: {', '.join(missing_fields)})"
            else:
                results["trading_volatility"]["data_quality"] = "complete"
                results["trading_volatility"]["sample_data"] = {
                    "spot_price": gex_data.get('spot_price'),
                    "net_gex": gex_data.get('net_gex'),
                    "collection_date": gex_data.get('collection_date')
                }
        else:
            results["trading_volatility"]["status"] = "error"
            results["trading_volatility"]["error"] = gex_data.get('error', 'Unknown error')
            results["trading_volatility"]["data_quality"] = "failed"

    except Exception as e:
        results["trading_volatility"]["status"] = "error"
        results["trading_volatility"]["error"] = str(e)
        results["trading_volatility"]["data_quality"] = "failed"

    # Test Polygon API (VIX data)
    try:
        if not POLYGON_API_KEY:
            results["polygon"]["status"] = "not_configured"
            results["polygon"]["error"] = "POLYGON_API_KEY not set in environment"
            results["polygon"]["data_quality"] = "n/a"
        else:
            start_time = time.time()

            # Test with VIX symbol
            url = f"https://api.polygon.io/v2/aggs/ticker/I:VIX/prev"
            response = requests.get(url, params={"apiKey": POLYGON_API_KEY}, timeout=10)

            elapsed_ms = int((time.time() - start_time) * 1000)
            results["polygon"]["response_time_ms"] = elapsed_ms

            if response.status_code == 200:
                data = response.json()

                if data.get('results') and len(data['results']) > 0:
                    vix_close = data['results'][0].get('c')
                    results["polygon"]["status"] = "connected"
                    results["polygon"]["data_quality"] = "complete"
                    results["polygon"]["vix_value"] = vix_close
                    results["polygon"]["sample_data"] = {
                        "close": vix_close,
                        "timestamp": data['results'][0].get('t'),
                        "volume": data['results'][0].get('v')
                    }
                else:
                    results["polygon"]["status"] = "error"
                    results["polygon"]["error"] = "No VIX data in response"
                    results["polygon"]["data_quality"] = "incomplete"
            elif response.status_code == 403:
                results["polygon"]["status"] = "error"
                results["polygon"]["error"] = "403 Forbidden - Check API key validity or subscription"
                results["polygon"]["data_quality"] = "failed"
            elif response.status_code == 429:
                results["polygon"]["status"] = "error"
                results["polygon"]["error"] = "429 Rate Limited - Too many requests"
                results["polygon"]["data_quality"] = "failed"
            else:
                results["polygon"]["status"] = "error"
                results["polygon"]["error"] = f"HTTP {response.status_code}: {response.text[:100]}"
                results["polygon"]["data_quality"] = "failed"

    except Exception as e:
        results["polygon"]["status"] = "error"
        results["polygon"]["error"] = str(e)
        results["polygon"]["data_quality"] = "failed"

    # Determine overall status
    tv_ok = results["trading_volatility"]["status"] == "connected"
    polygon_ok = results["polygon"]["status"] in ["connected", "not_configured"]  # not_configured is acceptable

    if tv_ok and polygon_ok:
        results["overall_status"] = "all_systems_operational"
    elif tv_ok:
        results["overall_status"] = "trading_volatility_only"
    elif polygon_ok:
        results["overall_status"] = "polygon_only"
    else:
        results["overall_status"] = "all_systems_down"

    return {
        "success": True,
        "results": results
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

    # Auto-initialize database with historical data on first startup
    print("\n🔄 Checking database initialization...")
    try:
        import sys
        sys.path.insert(0, str(parent_dir))
        from startup_init import initialize_on_startup
        initialize_on_startup()
    except Exception as e:
        print(f"⚠️  Initialization check failed: {e}")
        print("📊 App will create tables as needed during operation")

    # Auto-run backtests on startup IF database is empty
    print("\n🔄 Checking backtest results...")
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM backtest_results")
        count = cursor.fetchone()[0]
        conn.close()

        if count == 0:
            print("⚠️  No backtest results found. Auto-running backtests in background...")
            import subprocess
            import threading

            def run_backtests_async():
                try:
                    # Calculate date range for last 365 days
                    from datetime import datetime, timedelta
                    end_date = datetime.now().strftime('%Y-%m-%d')
                    start_date = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')

                    result = subprocess.run(
                        ['python3', 'run_all_backtests.py', '--symbol', 'SPY', '--start', start_date, '--end', end_date],
                        cwd=str(parent_dir),
                        capture_output=True,
                        text=True,
                        timeout=600  # 10 minute timeout
                    )
                    if result.returncode == 0:
                        print("✅ Backtests completed successfully on startup")
                    else:
                        print(f"❌ Backtests failed: {result.stderr[:200]}")
                except Exception as e:
                    print(f"❌ Error running backtests: {e}")

            # Run in background thread so startup doesn't block
            thread = threading.Thread(target=run_backtests_async, daemon=True)
            thread.start()
            print("✅ Backtests started in background thread")
        else:
            print(f"✅ Found {count} existing backtest results")
    except Exception as e:
        print(f"⚠️  Could not check backtest results: {e}")

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

# ============================================================================
# Probability System APIs
# ============================================================================

@app.get("/api/probability/outcomes")
async def get_probability_outcomes(days: int = 30):
    """
    Get prediction accuracy outcomes over time

    Shows how accurate our probability predictions have been
    """
    try:
        conn = get_connection()
        c = conn.cursor()

        c.execute('''
            SELECT
                prediction_date,
                pattern_type,
                predicted_probability,
                actual_outcome,
                correct_prediction,
                outcome_timestamp
            FROM probability_outcomes
            WHERE prediction_date >= datetime('now', '-' || ? || ' days')
            ORDER BY prediction_date DESC
        ''', (days,))

        outcomes = []
        for row in c.fetchall():
            outcomes.append({
                'prediction_date': row[0],
                'pattern_type': row[1],
                'predicted_probability': row[2],
                'actual_outcome': row[3],
                'correct_prediction': bool(row[4]),
                'outcome_timestamp': row[5]
            })

        # Calculate accuracy stats
        total = len(outcomes)
        correct = sum(1 for o in outcomes if o['correct_prediction'])
        accuracy = (correct / total * 100) if total > 0 else 0

        conn.close()

        return {
            "success": True,
            "outcomes": outcomes,
            "stats": {
                "total_predictions": total,
                "correct": correct,
                "accuracy_pct": accuracy
            }
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/api/probability/weights")
async def get_probability_weights():
    """Get current probability weighting configuration"""
    try:
        conn = get_connection()
        c = conn.cursor()

        c.execute('''
            SELECT
                weight_name,
                weight_value,
                description,
                last_updated,
                calibration_count
            FROM probability_weights
            ORDER BY weight_name
        ''')

        weights = []
        for row in c.fetchall():
            weights.append({
                'weight_name': row[0],
                'weight_value': row[1],
                'description': row[2],
                'last_updated': row[3],
                'calibration_count': row[4]
            })

        conn.close()

        return {
            "success": True,
            "weights": weights
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/api/probability/calibration-history")
async def get_calibration_history(days: int = 90):
    """Get model calibration adjustment history"""
    try:
        conn = get_connection()
        c = conn.cursor()

        c.execute('''
            SELECT
                calibration_date,
                weight_name,
                old_value,
                new_value,
                reason,
                performance_delta
            FROM calibration_history
            WHERE calibration_date >= datetime('now', '-' || ? || ' days')
            ORDER BY calibration_date DESC
        ''', (days,))

        history = []
        for row in c.fetchall():
            history.append({
                'calibration_date': row[0],
                'weight_name': row[1],
                'old_value': row[2],
                'new_value': row[3],
                'reason': row[4],
                'performance_delta': row[5]
            })

        conn.close()

        return {
            "success": True,
            "calibration_history": history
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

# ============================================================================
# Conversation History APIs
# ============================================================================

@app.get("/api/ai/conversations")
async def get_conversation_history(limit: int = 50):
    """Get AI copilot conversation history"""
    try:
        conn = get_connection()
        c = conn.cursor()

        c.execute('''
            SELECT
                id,
                timestamp,
                user_message,
                ai_response,
                context,
                session_id
            FROM conversations
            ORDER BY timestamp DESC
            LIMIT ?
        ''', (limit,))

        conversations = []
        for row in c.fetchall():
            conversations.append({
                'id': row[0],
                'timestamp': row[1],
                'user_message': row[2],
                'ai_response': row[3],
                'context': row[4],
                'session_id': row[5]
            })

        conn.close()

        return {
            "success": True,
            "conversations": conversations,
            "total": len(conversations)
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/api/ai/conversation/{conversation_id}")
async def get_conversation_detail(conversation_id: int):
    """Get full conversation thread details"""
    try:
        conn = get_connection()
        c = conn.cursor()

        c.execute('''
            SELECT
                id,
                timestamp,
                user_message,
                ai_response,
                context,
                session_id
            FROM conversations
            WHERE id = ?
        ''', (conversation_id,))

        row = c.fetchone()
        conn.close()

        if row:
            return {
                "success": True,
                "conversation": {
                    'id': row[0],
                    'timestamp': row[1],
                    'user_message': row[2],
                    'ai_response': row[3],
                    'context': row[4],
                    'session_id': row[5]
                }
            }
        else:
            return {"success": False, "error": "Conversation not found"}
    except Exception as e:
        return {"success": False, "error": str(e)}

# ============================================================================
# Open Interest Trends APIs
# ============================================================================

@app.get("/api/oi/trends")
async def get_oi_trends(symbol: str = "SPY", days: int = 30):
    """Get historical open interest trends"""
    try:
        conn = get_connection()
        c = conn.cursor()

        c.execute('''
            SELECT
                snapshot_date,
                strike,
                expiration,
                call_oi,
                put_oi,
                total_oi,
                call_volume,
                put_volume,
                put_call_ratio
            FROM historical_open_interest
            WHERE symbol = ?
            AND snapshot_date >= date('now', '-' || ? || ' days')
            ORDER BY snapshot_date DESC, total_oi DESC
        ''', (symbol, days))

        trends = []
        for row in c.fetchall():
            trends.append({
                'snapshot_date': row[0],
                'strike': row[1],
                'expiration': row[2],
                'call_oi': row[3],
                'put_oi': row[4],
                'total_oi': row[5],
                'call_volume': row[6],
                'put_volume': row[7],
                'put_call_ratio': row[8]
            })

        conn.close()

        return {
            "success": True,
            "trends": trends,
            "symbol": symbol
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/api/oi/unusual-activity")
async def get_unusual_oi_activity(symbol: str = "SPY", days: int = 7):
    """Detect unusual open interest changes"""
    try:
        conn = get_connection()
        c = conn.cursor()

        # Get strikes with significant OI changes
        c.execute('''
            SELECT
                h1.snapshot_date,
                h1.strike,
                h1.expiration,
                h1.total_oi,
                h2.total_oi as prev_oi,
                ((h1.total_oi - h2.total_oi) * 100.0 / h2.total_oi) as oi_change_pct
            FROM historical_open_interest h1
            LEFT JOIN historical_open_interest h2
                ON h1.strike = h2.strike
                AND h1.expiration = h2.expiration
                AND h2.snapshot_date = date(h1.snapshot_date, '-1 day')
            WHERE h1.symbol = ?
            AND h1.snapshot_date >= date('now', '-' || ? || ' days')
            AND h2.total_oi IS NOT NULL
            AND abs((h1.total_oi - h2.total_oi) * 100.0 / h2.total_oi) > 20
            ORDER BY abs((h1.total_oi - h2.total_oi) * 100.0 / h2.total_oi) DESC
            LIMIT 50
        ''', (symbol, days))

        unusual = []
        for row in c.fetchall():
            unusual.append({
                'date': row[0],
                'strike': row[1],
                'expiration': row[2],
                'current_oi': row[3],
                'previous_oi': row[4],
                'change_pct': row[5]
            })

        conn.close()

        return {
            "success": True,
            "unusual_activity": unusual
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

# ============================================================================
# Recommendations History APIs
# ============================================================================

@app.get("/api/recommendations/history")
async def get_recommendations_history(days: int = 30):
    """Get past trade recommendations"""
    try:
        conn = get_connection()
        c = conn.cursor()

        c.execute('''
            SELECT
                id,
                timestamp,
                symbol,
                strategy,
                direction,
                confidence,
                reasoning,
                strike,
                expiration,
                entry_price,
                target_price,
                stop_loss,
                status,
                actual_outcome
            FROM recommendations
            WHERE timestamp >= datetime('now', '-' || ? || ' days')
            ORDER BY timestamp DESC
        ''', (days,))

        recommendations = []
        for row in c.fetchall():
            recommendations.append({
                'id': row[0],
                'timestamp': row[1],
                'symbol': row[2],
                'strategy': row[3],
                'direction': row[4],
                'confidence': row[5],
                'reasoning': row[6],
                'strike': row[7],
                'expiration': row[8],
                'entry_price': row[9],
                'target_price': row[10],
                'stop_loss': row[11],
                'status': row[12],
                'actual_outcome': row[13]
            })

        conn.close()

        return {
            "success": True,
            "recommendations": recommendations
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/api/recommendations/performance")
async def get_recommendation_performance():
    """Analyze how well past recommendations performed"""
    try:
        conn = get_connection()
        c = conn.cursor()

        # Get recommendations with outcomes
        c.execute('''
            SELECT
                confidence,
                actual_outcome,
                CASE WHEN actual_outcome = 'WIN' THEN 1 ELSE 0 END as won
            FROM recommendations
            WHERE status = 'CLOSED'
            AND actual_outcome IS NOT NULL
        ''')

        results = c.fetchall()

        # Calculate stats by confidence bucket
        buckets = {
            '90-100': {'total': 0, 'wins': 0},
            '80-89': {'total': 0, 'wins': 0},
            '70-79': {'total': 0, 'wins': 0},
            '60-69': {'total': 0, 'wins': 0},
            'below-60': {'total': 0, 'wins': 0}
        }

        for row in results:
            conf = row[0]
            won = row[2]

            if conf >= 90:
                bucket = '90-100'
            elif conf >= 80:
                bucket = '80-89'
            elif conf >= 70:
                bucket = '70-79'
            elif conf >= 60:
                bucket = '60-69'
            else:
                bucket = 'below-60'

            buckets[bucket]['total'] += 1
            buckets[bucket]['wins'] += won

        # Calculate win rates
        performance = []
        for bucket_name, data in buckets.items():
            win_rate = (data['wins'] / data['total'] * 100) if data['total'] > 0 else 0
            performance.append({
                'confidence_bucket': bucket_name,
                'total': data['total'],
                'wins': data['wins'],
                'win_rate': win_rate
            })

        conn.close()

        return {
            "success": True,
            "performance_by_confidence": performance
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

# ============================================================================
# GEX History APIs
# ============================================================================

@app.get("/api/gex/history")
async def get_gex_history(symbol: str = "SPY", days: int = 90):
    """Get historical GEX snapshots"""
    try:
        conn = get_connection()
        c = conn.cursor()

        c.execute('''
            SELECT
                timestamp,
                net_gex,
                flip_point,
                call_wall,
                put_wall,
                spot_price,
                mm_state,
                regime,
                data_source
            FROM gex_history
            WHERE symbol = ?
            AND timestamp >= datetime('now', '-' || ? || ' days')
            ORDER BY timestamp DESC
        ''', (symbol, days))

        history = []
        for row in c.fetchall():
            history.append({
                'timestamp': row[0],
                'net_gex': row[1],
                'flip_point': row[2],
                'call_wall': row[3],
                'put_wall': row[4],
                'spot_price': row[5],
                'mm_state': row[6],
                'regime': row[7],
                'data_source': row[8]
            })

        conn.close()

        return {
            "success": True,
            "history": history,
            "symbol": symbol
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/api/gex/regime-changes")
async def get_gex_regime_changes(symbol: str = "SPY", days: int = 90):
    """Identify when GEX regime flipped"""
    try:
        conn = get_connection()
        c = conn.cursor()

        # Get regime changes
        c.execute('''
            SELECT
                h1.timestamp,
                h1.regime as new_regime,
                h2.regime as old_regime,
                h1.net_gex,
                h1.spot_price
            FROM gex_history h1
            LEFT JOIN gex_history h2
                ON h2.timestamp = (
                    SELECT MAX(timestamp)
                    FROM gex_history
                    WHERE timestamp < h1.timestamp
                    AND symbol = h1.symbol
                )
            WHERE h1.symbol = ?
            AND h1.timestamp >= datetime('now', '-' || ? || ' days')
            AND h1.regime != h2.regime
            ORDER BY h1.timestamp DESC
        ''', (symbol, days))

        changes = []
        for row in c.fetchall():
            changes.append({
                'timestamp': row[0],
                'new_regime': row[1],
                'old_regime': row[2],
                'net_gex': row[3],
                'spot_price': row[4]
            })

        conn.close()

        return {
            "success": True,
            "regime_changes": changes
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

# ============================================================================
# Push Subscription Management APIs
# ============================================================================

@app.get("/api/notifications/subscriptions")
async def get_push_subscriptions():
    """Get all push notification subscriptions"""
    try:
        conn = get_connection()
        c = conn.cursor()

        c.execute('''
            SELECT
                id,
                endpoint,
                created_at,
                last_notification,
                notification_count,
                active
            FROM push_subscriptions
            WHERE active = 1
            ORDER BY created_at DESC
        ''')

        subscriptions = []
        for row in c.fetchall():
            subscriptions.append({
                'id': row[0],
                'endpoint': row[1][:50] + '...',  # Truncate for security
                'created_at': row[2],
                'last_notification': row[3],
                'notification_count': row[4],
                'active': bool(row[5])
            })

        conn.close()

        return {
            "success": True,
            "subscriptions": subscriptions
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.delete("/api/notifications/subscription/{subscription_id}")
async def delete_push_subscription(subscription_id: int):
    """Unsubscribe from push notifications"""
    try:
        conn = get_connection()
        c = conn.cursor()

        c.execute('''
            UPDATE push_subscriptions
            SET active = 0
            WHERE id = ?
        ''', (subscription_id,))

        conn.commit()
        conn.close()

        return {
            "success": True,
            "message": "Subscription deactivated"
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

# ============================================================================
# System Management APIs - Autonomous Trader Control
# ============================================================================

@app.get("/api/system/trader-status")
async def get_trader_status():
    """Get autonomous trader status and auto-start configuration"""
    import subprocess
    import os

    try:
        # Detect if running on Render
        is_render = bool(os.getenv("RENDER")) or bool(os.getenv("RENDER_SERVICE_NAME"))

        status = {
            "trader_running": False,
            "trader_pid": None,
            "autostart_enabled": False,
            "watchdog_enabled": False,
            "last_log_entry": None,
            "uptime": None,
            "platform": "render" if is_render else "local",
            "autostart_type": None
        }

        # Check if trader is running
        alphagex_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        pid_file = os.path.join(alphagex_dir, "logs", "trader.pid")

        if os.path.exists(pid_file):
            with open(pid_file, 'r') as f:
                pid = f.read().strip()
                status["trader_pid"] = int(pid)

                # Check if process is actually running
                try:
                    result = subprocess.run(['ps', '-p', pid], capture_output=True, text=True)
                    status["trader_running"] = result.returncode == 0
                except (OSError, subprocess.SubprocessError, FileNotFoundError) as e:
                    status["trader_running"] = False

        # Handle auto-start detection based on platform
        if is_render:
            # On Render, auto-start is managed via render.yaml worker service
            status["autostart_enabled"] = True
            status["watchdog_enabled"] = True
            status["autostart_type"] = "render_worker"
        else:
            # On local/VPS, check crontab
            try:
                result = subprocess.run(['crontab', '-l'], capture_output=True, text=True)
                crontab_content = result.stdout
                status["autostart_enabled"] = "auto_start_trader.sh" in crontab_content
                status["watchdog_enabled"] = "trader_watchdog.sh" in crontab_content
                status["autostart_type"] = "crontab" if status["autostart_enabled"] else None
            except (OSError, subprocess.SubprocessError, FileNotFoundError) as e:
                status["autostart_enabled"] = False
                status["watchdog_enabled"] = False

        # Get last log entry
        log_file = os.path.join(alphagex_dir, "logs", "trader.log")
        if os.path.exists(log_file):
            try:
                with open(log_file, 'r') as f:
                    lines = f.readlines()
                    if lines:
                        status["last_log_entry"] = lines[-1].strip()
            except (IOError, OSError, PermissionError) as e:
                # Unable to read log file
                pass

        return {
            "success": True,
            "status": status
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/system/enable-autostart")
async def enable_autostart():
    """Enable autonomous trader auto-start on boot + watchdog"""
    import subprocess
    import os

    try:
        # Detect if running on Render
        is_render = bool(os.getenv("RENDER")) or bool(os.getenv("RENDER_SERVICE_NAME"))

        if is_render:
            # On Render, auto-start is managed via render.yaml
            return {
                "success": True,
                "message": "Auto-start is already configured via Render worker service (render.yaml). The autonomous trader runs automatically as a background worker and restarts if it crashes.",
                "already_enabled": True,
                "platform": "render"
            }

        alphagex_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        # Get current crontab
        try:
            result = subprocess.run(['crontab', '-l'], capture_output=True, text=True)
            current_crontab = result.stdout
        except FileNotFoundError:
            return {
                "success": False,
                "error": "crontab command not found. This system doesn't support cron-based auto-start.",
                "platform": "unsupported"
            }
        except Exception as e:
            current_crontab = ""

        # Check if already enabled
        if "auto_start_trader.sh" in current_crontab and "trader_watchdog.sh" in current_crontab:
            return {
                "success": True,
                "message": "Auto-start already enabled",
                "already_enabled": True
            }

        # Add auto-start and watchdog entries
        new_entries = f"""
# AlphaGEX Autonomous Trader - Auto-start on boot
@reboot {alphagex_dir}/auto_start_trader.sh

# AlphaGEX Autonomous Trader - Watchdog (checks every minute, restarts if crashed)
* * * * * {alphagex_dir}/trader_watchdog.sh
"""

        # Remove old entries if they exist (to avoid duplicates)
        lines = current_crontab.split('\n')
        filtered_lines = [l for l in lines if 'auto_start_trader.sh' not in l and 'trader_watchdog.sh' not in l]
        updated_crontab = '\n'.join(filtered_lines) + new_entries

        # Update crontab
        process = subprocess.Popen(['crontab', '-'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = process.communicate(input=updated_crontab.encode())

        if process.returncode != 0:
            return {
                "success": False,
                "error": f"Failed to update crontab: {stderr.decode()}"
            }

        return {
            "success": True,
            "message": "Auto-start enabled successfully! Trader will start on boot and auto-restart if crashed.",
            "already_enabled": False
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/system/disable-autostart")
async def disable_autostart():
    """Disable autonomous trader auto-start"""
    import subprocess

    try:
        # Get current crontab
        try:
            result = subprocess.run(['crontab', '-l'], capture_output=True, text=True)
            current_crontab = result.stdout
        except (OSError, subprocess.SubprocessError, FileNotFoundError) as e:
            return {
                "success": True,
                "message": "Auto-start already disabled (no crontab found)"
            }

        # Remove auto-start entries
        lines = current_crontab.split('\n')
        filtered_lines = [l for l in lines if 'auto_start_trader.sh' not in l and 'trader_watchdog.sh' not in l and l.strip()]
        updated_crontab = '\n'.join(filtered_lines) + '\n'

        # Update crontab
        process = subprocess.Popen(['crontab', '-'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = process.communicate(input=updated_crontab.encode())

        if process.returncode != 0:
            return {
                "success": False,
                "error": f"Failed to update crontab: {stderr.decode()}"
            }

        return {
            "success": True,
            "message": "Auto-start disabled. Trader will not start automatically on boot."
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/system/start-trader")
async def start_trader_manually():
    """Manually start the autonomous trader"""
    import subprocess
    import os

    try:
        alphagex_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        start_script = os.path.join(alphagex_dir, "auto_start_trader.sh")

        if not os.path.exists(start_script):
            return {
                "success": False,
                "error": f"Start script not found at {start_script}"
            }

        # Run the start script with timeout to prevent hanging
        try:
            result = subprocess.run(
                [start_script],
                capture_output=True,
                text=True,
                cwd=alphagex_dir,
                timeout=30  # 30 second timeout
            )
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": "Start script timed out after 30 seconds"
            }

        if result.returncode != 0:
            return {
                "success": False,
                "error": f"Start script failed: {result.stderr or result.stdout}"
            }

        return {
            "success": True,
            "message": "Trader started successfully",
            "output": result.stdout
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/system/stop-trader")
async def stop_trader_manually():
    """Manually stop the autonomous trader"""
    import subprocess
    import os
    import signal

    try:
        alphagex_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        pid_file = os.path.join(alphagex_dir, "logs", "trader.pid")

        if not os.path.exists(pid_file):
            return {
                "success": False,
                "error": "Trader is not running (no PID file found)"
            }

        # Read and validate PID file
        try:
            with open(pid_file, 'r') as f:
                pid_content = f.read().strip()
                if not pid_content:
                    return {
                        "success": False,
                        "error": "PID file is empty"
                    }
                pid = int(pid_content)
        except ValueError:
            return {
                "success": False,
                "error": f"Invalid PID file contents: '{pid_content[:50]}'"
            }

        # Validate PID is reasonable (not system processes)
        if pid <= 0 or pid > 4194304:  # Max PID on Linux
            return {
                "success": False,
                "error": f"Invalid PID value: {pid}"
            }

        # Verify the process exists and is actually a trader process
        try:
            # Check if process exists first
            os.kill(pid, 0)  # Signal 0 doesn't kill, just checks existence

            # Try to verify it's actually a Python/trader process (optional safety check)
            try:
                cmdline_path = f"/proc/{pid}/cmdline"
                if os.path.exists(cmdline_path):
                    with open(cmdline_path, 'r') as f:
                        cmdline = f.read()
                        # Basic sanity check - should contain python or trader
                        if 'python' not in cmdline.lower() and 'trader' not in cmdline.lower():
                            return {
                                "success": False,
                                "error": f"PID {pid} does not appear to be the trader process"
                            }
            except (IOError, PermissionError):
                # Can't read cmdline, proceed anyway
                pass

            # Kill the process
            os.kill(pid, signal.SIGTERM)

            # Clean up the PID file
            try:
                os.remove(pid_file)
            except:
                pass

            return {
                "success": True,
                "message": f"Trader stopped (PID: {pid})"
            }
        except ProcessLookupError:
            # Process doesn't exist, clean up stale PID file
            try:
                os.remove(pid_file)
            except:
                pass
            return {
                "success": False,
                "error": "Trader process not found (may have already stopped). Cleaned up stale PID file."
            }
        except PermissionError:
            return {
                "success": False,
                "error": f"Permission denied when trying to stop PID {pid}"
            }
    except Exception as e:
        return {"success": False, "error": str(e)}

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
