"""
Database and System Diagnostics API routes.

Handles database stats, API connectivity tests, and system health checks.
"""

import os
import time
from datetime import datetime

from fastapi import APIRouter, HTTPException
import psycopg2.extras
import requests

from database_adapter import get_connection

router = APIRouter(tags=["Database & System"])


@router.get("/api/database/stats")
async def get_database_stats():
    """Get database statistics and table info"""
    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Get all tables
        cursor.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name
        """)
        tables_result = cursor.fetchall()

        tables = []
        for t in tables_result:
            table_name = t['table_name']

            # Get row count
            cursor.execute(f"SELECT COUNT(*) as cnt FROM {table_name}")
            row_count = cursor.fetchone()['cnt']

            # Get column info
            cursor.execute(f"""
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_name = %s
                ORDER BY ordinal_position
            """, (table_name,))
            columns = [{"name": c['column_name'], "type": c['data_type']} for c in cursor.fetchall()]

            # Get sample data (first 3 rows)
            cursor.execute(f"SELECT * FROM {table_name} LIMIT 3")
            sample = cursor.fetchall()

            tables.append({
                "table_name": table_name,
                "row_count": row_count,
                "columns": columns,
                "sample_data": [dict(s) for s in sample]
            })

        conn.close()

        return {
            "success": True,
            "database_path": os.getenv('DATABASE_URL', 'PostgreSQL'),
            "total_tables": len(tables),
            "tables": tables,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/test-connections")
async def test_api_connections():
    """Test connectivity to external APIs"""
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
        from core_classes_and_engines import TradingVolatilityAPI
        api = TradingVolatilityAPI()

        start = time.time()
        data = api.get_option_data('SPY')
        elapsed = (time.time() - start) * 1000

        results["trading_volatility"]["response_time_ms"] = round(elapsed)

        if data and 'net_gex' in data:
            results["trading_volatility"]["status"] = "connected"
            results["trading_volatility"]["data_quality"] = "good"
            results["trading_volatility"]["fields_received"] = list(data.keys())[:10]
            results["trading_volatility"]["sample_data"] = {
                "net_gex": data.get('net_gex'),
                "call_wall": data.get('call_wall'),
                "put_wall": data.get('put_wall')
            }
        else:
            results["trading_volatility"]["status"] = "error"
            results["trading_volatility"]["error"] = "No data returned"
    except Exception as e:
        results["trading_volatility"]["status"] = "error"
        results["trading_volatility"]["error"] = str(e)

    # Test Polygon API (VIX)
    try:
        polygon_key = os.getenv('POLYGON_API_KEY')
        if polygon_key:
            from datetime import timedelta
            to_date = datetime.now().strftime('%Y-%m-%d')
            from_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')

            url = f"https://api.polygon.io/v2/aggs/ticker/VIX/range/1/day/{from_date}/{to_date}"
            params = {"apiKey": polygon_key, "sort": "desc", "limit": 1}

            start = time.time()
            response = requests.get(url, params=params, timeout=10)
            elapsed = (time.time() - start) * 1000

            results["polygon"]["response_time_ms"] = round(elapsed)

            if response.status_code == 200:
                data = response.json()
                if data.get('status') == 'OK' and data.get('results'):
                    vix = data['results'][0]['c']
                    results["polygon"]["status"] = "connected"
                    results["polygon"]["data_quality"] = "good"
                    results["polygon"]["vix_value"] = vix
                    results["polygon"]["sample_data"] = data['results'][0]
                else:
                    results["polygon"]["status"] = "error"
                    results["polygon"]["error"] = "No VIX data returned"
            else:
                results["polygon"]["status"] = "error"
                results["polygon"]["error"] = f"HTTP {response.status_code}"
        else:
            results["polygon"]["status"] = "not_configured"
            results["polygon"]["error"] = "No API key configured"
    except Exception as e:
        results["polygon"]["status"] = "error"
        results["polygon"]["error"] = str(e)

    # Determine overall status
    tv_ok = results["trading_volatility"]["status"] == "connected"
    poly_ok = results["polygon"]["status"] in ["connected", "not_configured"]

    if tv_ok and poly_ok:
        results["overall_status"] = "healthy"
    elif tv_ok or poly_ok:
        results["overall_status"] = "degraded"
    else:
        results["overall_status"] = "error"

    return {"success": True, "results": results}


@router.get("/health")
async def health_check():
    """Basic health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "2.0.0"
    }


@router.get("/api/rate-limit-status")
async def get_rate_limit_status():
    """Get current rate limit status"""
    try:
        from core_classes_and_engines import TradingVolatilityAPI
        api = TradingVolatilityAPI()

        return {
            "success": True,
            "data": {
                "circuit_breaker_active": getattr(api, '_circuit_breaker_active', False),
                "circuit_breaker_until": getattr(api, '_circuit_breaker_until', None),
                "last_request_time": getattr(api, '_last_request_time', None),
                "min_interval_seconds": 4.0
            }
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


@router.get("/api/time")
async def get_server_time():
    """Get current server time and market status"""
    from zoneinfo import ZoneInfo

    now = datetime.now(ZoneInfo("America/New_York"))
    chicago = datetime.now(ZoneInfo("America/Chicago"))

    # Check if market is open
    market_open = (
        now.weekday() < 5 and  # Monday-Friday
        9 <= now.hour < 16 and  # 9:30 AM - 4 PM ET (simplified)
        not (now.hour == 9 and now.minute < 30)
    )

    return {
        "success": True,
        "data": {
            "utc": datetime.utcnow().isoformat(),
            "eastern": now.isoformat(),
            "chicago": chicago.isoformat(),
            "market_open": market_open,
            "day_of_week": now.strftime("%A")
        }
    }
