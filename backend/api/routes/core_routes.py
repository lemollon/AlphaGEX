"""
Core API routes - Health, diagnostics, time, rate-limit endpoints.
"""

import os
from datetime import datetime, timedelta

import requests
from fastapi import APIRouter, HTTPException

from api.dependencies import (
    api_client,
    get_et_time,
    get_local_time,
    is_market_open,
    UNIFIED_DATA_AVAILABLE,
)
from core_classes_and_engines import TradingVolatilityAPI
from database_adapter import get_connection

router = APIRouter(tags=["Core"])


@router.get("/")
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


@router.get("/health")
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
            "database": "operational"
        }
    }


@router.get("/api/rate-limit-status")
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


@router.post("/api/rate-limit-reset")
async def reset_rate_limit():
    """Manually reset the circuit breaker and rate limit counters"""
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


@router.get("/api/time")
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


@router.get("/api/diagnostic")
async def diagnostic():
    """Diagnostic endpoint to check API configuration and connectivity"""
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

    polygon_key_configured = bool(os.getenv("POLYGON_API_KEY"))
    polygon_key_length = len(os.getenv("POLYGON_API_KEY", "")) if polygon_key_configured else 0

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


@router.get("/api/diagnostic/rsi")
async def diagnostic_rsi():
    """Diagnostic endpoint specifically for RSI data fetching"""
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


@router.get("/api/database/stats")
async def get_database_stats():
    """Get database statistics"""
    try:
        conn = get_connection()
        cursor = conn.cursor()

        stats = {}

        # Get table counts
        tables = [
            'gex_history', 'autonomous_open_positions', 'autonomous_closed_trades',
            'autonomous_trade_log', 'backtest_results', 'regime_signals'
        ]

        for table in tables:
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                stats[table] = cursor.fetchone()[0]
            except Exception:
                stats[table] = "N/A"

        conn.close()

        return {
            "success": True,
            "data": stats,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/test-connections")
async def test_connections():
    """Test all external API connections"""
    results = {
        "timestamp": datetime.now().isoformat(),
        "connections": {}
    }

    # Test Trading Volatility API
    try:
        gex = api_client.get_net_gamma("SPY")
        results["connections"]["trading_volatility"] = {
            "status": "ok" if gex and not gex.get('error') else "error",
            "error": gex.get('error') if gex else "No response"
        }
    except Exception as e:
        results["connections"]["trading_volatility"] = {"status": "error", "error": str(e)}

    # Test Database
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        conn.close()
        results["connections"]["database"] = {"status": "ok"}
    except Exception as e:
        results["connections"]["database"] = {"status": "error", "error": str(e)}

    # Test Polygon
    polygon_key = os.getenv('POLYGON_API_KEY')
    if polygon_key:
        try:
            url = "https://api.polygon.io/v2/aggs/ticker/SPY/prev"
            response = requests.get(url, params={"apiKey": polygon_key}, timeout=5)
            results["connections"]["polygon"] = {
                "status": "ok" if response.status_code == 200 else "error",
                "status_code": response.status_code
            }
        except Exception as e:
            results["connections"]["polygon"] = {"status": "error", "error": str(e)}
    else:
        results["connections"]["polygon"] = {"status": "not_configured"}

    return results
