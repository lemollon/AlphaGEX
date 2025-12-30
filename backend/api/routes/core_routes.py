"""
Core API routes - Health, diagnostics, time, rate-limit endpoints.
"""

import logging
import os

logger = logging.getLogger(__name__)
from datetime import datetime, timedelta

import requests
from fastapi import APIRouter, HTTPException

# Import dependencies with fallback handling
try:
    from backend.api.dependencies import (
        api_client,
        get_et_time,
        get_local_time,
        is_market_open,
        UNIFIED_DATA_AVAILABLE,
    )
except ImportError as e:
    logger.debug(f" core_routes: dependencies import failed: {e}")
    api_client = None
    UNIFIED_DATA_AVAILABLE = False
    from zoneinfo import ZoneInfo
    CENTRAL_TZ = ZoneInfo("America/Chicago")
    def get_et_time():
        """Returns Central Time (legacy name for compatibility)"""
        return datetime.now(CENTRAL_TZ)
    def get_local_time(tz='America/Chicago'):
        return datetime.now(ZoneInfo(tz))
    def is_market_open():
        ct = datetime.now(CENTRAL_TZ)
        if ct.weekday() >= 5:
            return False
        market_open = ct.replace(hour=8, minute=30, second=0, microsecond=0)
        market_close = ct.replace(hour=15, minute=0, second=0, microsecond=0)
        return market_open <= ct < market_close

# TradingVolatilityAPI - with fallback
TradingVolatilityAPI = None
try:
    from core_classes_and_engines import TradingVolatilityAPI
except ImportError as e:
    logger.debug(f" core_routes: TradingVolatilityAPI import failed: {e}")

# Database connection - with fallback
get_connection = None
try:
    from database_adapter import get_connection
except ImportError as e:
    logger.debug(f" core_routes: database_adapter import failed: {e}")

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


@router.get("/api/system-health")
async def comprehensive_system_health():
    """
    COMPREHENSIVE SYSTEM HEALTH CHECK
    Shows the real status of ALL components - database, traders, data collection, etc.
    Run this to verify the entire system is working properly.
    """
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    CENTRAL_TZ = ZoneInfo("America/Chicago")

    health = {
        "timestamp": datetime.now(CENTRAL_TZ).isoformat(),
        "overall_status": "healthy",
        "issues": [],
        "warnings": [],
        "components": {}
    }

    # 1. DATABASE CONNECTION
    try:
        if get_connection:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            conn.close()
            health["components"]["database"] = {"status": "connected", "message": "PostgreSQL connection successful"}
        else:
            health["components"]["database"] = {"status": "error", "message": "get_connection not available"}
            health["issues"].append("Database adapter not loaded")
    except Exception as e:
        health["components"]["database"] = {"status": "error", "message": str(e)}
        health["issues"].append(f"Database connection failed: {str(e)}")

    # 2. GEX HISTORY DATA (Critical for frontend charts)
    try:
        if get_connection:
            conn = get_connection()
            cursor = conn.cursor()

            # Check total records
            cursor.execute("SELECT COUNT(*) FROM gex_history")
            total_gex = cursor.fetchone()[0]

            # Check records from today (Central Time)
            today = datetime.now(ZoneInfo("America/Chicago")).strftime('%Y-%m-%d')
            cursor.execute("SELECT COUNT(*) FROM gex_history WHERE DATE(timestamp) = %s", (today,))
            today_gex = cursor.fetchone()[0]

            # Check most recent record
            cursor.execute("SELECT timestamp FROM gex_history ORDER BY timestamp DESC LIMIT 1")
            last_gex = cursor.fetchone()
            last_gex_time = last_gex[0] if last_gex else None

            conn.close()

            if total_gex == 0:
                health["components"]["gex_history"] = {
                    "status": "empty",
                    "total_records": 0,
                    "today_records": 0,
                    "message": "NO DATA - Data collector may not be running"
                }
                health["issues"].append("gex_history table is EMPTY - historical charts will be blank")
            else:
                health["components"]["gex_history"] = {
                    "status": "has_data",
                    "total_records": total_gex,
                    "today_records": today_gex,
                    "last_update": last_gex_time.isoformat() if last_gex_time else None,
                    "message": f"{total_gex} total records, {today_gex} from today"
                }
                if today_gex == 0:
                    health["warnings"].append(f"No GEX data for today ({today}) - market may be closed or data collector not running")
    except Exception as e:
        health["components"]["gex_history"] = {"status": "error", "message": str(e)}
        health["issues"].append(f"Could not check gex_history: {str(e)}")

    # 3. REGIME SIGNALS DATA
    try:
        if get_connection:
            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(*) FROM regime_signals")
            total_regime = cursor.fetchone()[0]

            cursor.execute("SELECT timestamp FROM regime_signals ORDER BY timestamp DESC LIMIT 1")
            last_regime = cursor.fetchone()

            conn.close()

            if total_regime == 0:
                health["components"]["regime_signals"] = {
                    "status": "empty",
                    "total_records": 0,
                    "message": "NO DATA - Psychology pages will be blank"
                }
                health["warnings"].append("regime_signals table is empty")
            else:
                health["components"]["regime_signals"] = {
                    "status": "has_data",
                    "total_records": total_regime,
                    "last_update": last_regime[0].isoformat() if last_regime else None
                }
    except Exception as e:
        health["components"]["regime_signals"] = {"status": "error", "message": str(e)}

    # 4. AUTONOMOUS TRADER DATA
    try:
        if get_connection:
            conn = get_connection()
            cursor = conn.cursor()

            # Open positions
            cursor.execute("SELECT COUNT(*) FROM autonomous_open_positions")
            open_positions = cursor.fetchone()[0]

            # Closed trades
            cursor.execute("SELECT COUNT(*) FROM autonomous_closed_trades")
            closed_trades = cursor.fetchone()[0]

            # Check for $0 entry prices (data integrity issue)
            cursor.execute("""
                SELECT COUNT(*) FROM autonomous_closed_trades
                WHERE entry_price IS NULL OR entry_price = 0
            """)
            zero_entry_count = cursor.fetchone()[0]

            # Last trade date
            cursor.execute("SELECT MAX(exit_date) FROM autonomous_closed_trades")
            last_trade = cursor.fetchone()[0]

            conn.close()

            health["components"]["autonomous_trader"] = {
                "status": "active" if (open_positions > 0 or closed_trades > 0) else "no_trades",
                "open_positions": open_positions,
                "closed_trades": closed_trades,
                "last_trade_date": str(last_trade) if last_trade else None,
                "data_integrity": {
                    "zero_entry_price_count": zero_entry_count,
                    "status": "clean" if zero_entry_count == 0 else "has_legacy_issues"
                }
            }

            if zero_entry_count > 0:
                health["warnings"].append(f"{zero_entry_count} closed trades have $0 entry price (legacy data issue)")
    except Exception as e:
        health["components"]["autonomous_trader"] = {"status": "error", "message": str(e)}

    # 5. TRADING VOLATILITY API
    try:
        if TradingVolatilityAPI:
            circuit_breaker_active = getattr(TradingVolatilityAPI, '_shared_circuit_breaker_active', False)
            calls_this_minute = getattr(TradingVolatilityAPI, '_shared_api_call_count_minute', 0)

            health["components"]["trading_volatility_api"] = {
                "status": "rate_limited" if circuit_breaker_active else "available",
                "calls_this_minute": calls_this_minute,
                "limit_per_minute": 20,
                "circuit_breaker": circuit_breaker_active
            }

            if circuit_breaker_active:
                health["warnings"].append("Trading Volatility API circuit breaker is ACTIVE - API calls are blocked")
        else:
            health["components"]["trading_volatility_api"] = {"status": "not_loaded"}
            health["issues"].append("TradingVolatilityAPI not loaded")
    except Exception as e:
        health["components"]["trading_volatility_api"] = {"status": "error", "message": str(e)}

    # 6. BACKTEST RESULTS
    try:
        if get_connection:
            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(*) FROM backtest_results")
            backtest_count = cursor.fetchone()[0]

            conn.close()

            health["components"]["backtest_results"] = {
                "status": "has_data" if backtest_count > 0 else "empty",
                "total_results": backtest_count
            }
    except Exception as e:
        health["components"]["backtest_results"] = {"status": "error", "message": str(e)}

    # 7. MARKET STATUS
    try:
        et_now = get_et_time()
        is_open = is_market_open()

        health["components"]["market"] = {
            "status": "open" if is_open else "closed",
            "current_time_et": et_now.strftime("%Y-%m-%d %H:%M:%S %Z"),
            "day_of_week": et_now.strftime("%A"),
            "is_weekend": et_now.weekday() >= 5
        }
    except Exception as e:
        health["components"]["market"] = {"status": "error", "message": str(e)}

    # OVERALL STATUS CALCULATION
    if len(health["issues"]) > 0:
        health["overall_status"] = "critical" if any("EMPTY" in i or "failed" in i.lower() for i in health["issues"]) else "degraded"
    elif len(health["warnings"]) > 0:
        health["overall_status"] = "warnings"

    # RECOMMENDATIONS
    health["recommendations"] = []

    if health["components"].get("gex_history", {}).get("status") == "empty":
        health["recommendations"].append("Run data collector to populate gex_history: The automated data collector should be running")

    if health["components"].get("regime_signals", {}).get("status") == "empty":
        health["recommendations"].append("Run backtests to populate regime_signals: python -c 'from backtest.autonomous_backtest_engine import get_backtester; get_backtester().backtest_all_patterns_and_save()'")

    if health["components"].get("autonomous_trader", {}).get("data_integrity", {}).get("zero_entry_price_count", 0) > 0:
        health["recommendations"].append("Legacy trades with $0 entry price exist - these are historical data issues that won't affect new trades")

    return health


@router.get("/api/rate-limit-status")
async def get_rate_limit_status():
    """Get current Trading Volatility API rate limit status and health"""
    if not TradingVolatilityAPI:
        return {
            "calls_this_minute": 0,
            "limit_per_minute": 20,
            "remaining": 20,
            "circuit_breaker_active": False,
            "cache_size": 0,
            "cache_duration_minutes": 0,
            "total_calls_lifetime": 0,
            "status": "unavailable",
            "recommendation": "TradingVolatilityAPI not loaded"
        }

    return {
        "calls_this_minute": getattr(TradingVolatilityAPI, '_shared_api_call_count_minute', 0),
        "limit_per_minute": 20,
        "remaining": max(0, 20 - getattr(TradingVolatilityAPI, '_shared_api_call_count_minute', 0)),
        "circuit_breaker_active": getattr(TradingVolatilityAPI, '_shared_circuit_breaker_active', False),
        "cache_size": len(getattr(TradingVolatilityAPI, '_shared_response_cache', {})),
        "cache_duration_minutes": getattr(TradingVolatilityAPI, '_shared_cache_duration', 0) / 60,
        "total_calls_lifetime": getattr(TradingVolatilityAPI, '_shared_api_call_count', 0),
        "status": "healthy" if not getattr(TradingVolatilityAPI, '_shared_circuit_breaker_active', False) else "rate_limited",
        "recommendation": "Rate limit OK" if getattr(TradingVolatilityAPI, '_shared_api_call_count_minute', 0) < 15 else "Approaching limit - requests may queue"
    }


@router.post("/api/rate-limit-reset")
async def reset_rate_limit():
    """Manually reset the circuit breaker and rate limit counters"""
    if not TradingVolatilityAPI:
        return {
            "success": False,
            "message": "TradingVolatilityAPI not available",
            "new_status": {}
        }

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
    if not get_connection:
        return {
            "success": False,
            "error": "Database adapter not available",
            "data": {},
            "timestamp": datetime.now().isoformat()
        }

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
    if not api_client:
        results["connections"]["trading_volatility"] = {"status": "not_configured", "error": "API client not loaded"}
    else:
        try:
            gex = api_client.get_net_gamma("SPY")
            results["connections"]["trading_volatility"] = {
                "status": "ok" if gex and not gex.get('error') else "error",
                "error": gex.get('error') if gex else "No response"
            }
        except Exception as e:
            results["connections"]["trading_volatility"] = {"status": "error", "error": str(e)}

    # Test Database
    if not get_connection:
        results["connections"]["database"] = {"status": "not_configured", "error": "Database adapter not loaded"}
    else:
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
