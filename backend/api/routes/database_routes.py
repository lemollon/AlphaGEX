"""
Database and System Diagnostics API routes.

Handles database stats, API connectivity tests, and system health checks.
"""

import os
import re
import time
from datetime import datetime, timedelta
from collections import deque
from typing import Dict, List, Any, Optional

from fastapi import APIRouter, HTTPException
import psycopg2.extras
import psycopg2.sql as sql
import requests

from database_adapter import get_connection


# In-memory error log buffer (circular buffer, max 500 entries)
ERROR_LOG_BUFFER: deque = deque(maxlen=500)
ACTIVITY_LOG_BUFFER: deque = deque(maxlen=200)


def log_error_event(source: str, error_type: str, message: str, details: Optional[Dict] = None):
    """Log an error event to the in-memory buffer"""
    ERROR_LOG_BUFFER.append({
        "timestamp": datetime.now().isoformat(),
        "source": source,
        "error_type": error_type,
        "message": message,
        "details": details or {}
    })


def log_activity_event(action: str, details: Optional[Dict] = None):
    """Log an activity event to the in-memory buffer"""
    ACTIVITY_LOG_BUFFER.append({
        "timestamp": datetime.now().isoformat(),
        "action": action,
        "details": details or {}
    })


def mask_database_url(url: str) -> str:
    """Mask sensitive credentials in database URL"""
    if not url:
        return "Not configured"
    # Mask password in postgresql://user:password@host/db format
    masked = re.sub(
        r'(postgresql://[^:]+:)[^@]+(@.+)',
        r'\1****\2',
        url
    )
    # Also mask any remaining sensitive parts
    masked = re.sub(r'password=[^&\s]+', 'password=****', masked)
    return masked

# Use standard logging with fallback for deployment compatibility
# This ensures the module loads even if utils.logging_config is unavailable
import logging
try:
    from utils.logging_config import get_logger, log_error_with_context
    logger = get_logger(__name__)
except ImportError:
    # Fallback to standard logging if utils.logging_config is not available
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    def log_error_with_context(logger, message, error):
        """Fallback error logging function"""
        logger.error(f"{message}: {type(error).__name__}: {error}")

router = APIRouter(tags=["Database & System"])

# Allowlist of valid table names for security
VALID_TABLE_NAMES = {
    'gex_history', 'trade_setups', 'trades', 'positions', 'backtest_results',
    'regime_classifications', 'market_snapshots', 'alerts', 'notifications',
    'psychology_patterns', 'price_history', 'options_chains', 'gamma_data',
    'vix_history', 'iv_rank_history', 'portfolio_snapshots', 'trade_journal',
    'performance_metrics', 'risk_metrics', 'strategy_performance',
    'intraday_levels', 'key_levels', 'earnings_calendar', 'economic_events'
}


def validate_table_name(table_name: str) -> bool:
    """
    Validate table name against allowlist and format.

    Args:
        table_name: The table name to validate

    Returns:
        True if valid, False otherwise
    """
    # Check allowlist first (known tables)
    if table_name in VALID_TABLE_NAMES:
        return True

    # For unknown tables, validate format (alphanumeric + underscore only)
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', table_name):
        logger.warning(
            f"Invalid table name format rejected: {table_name}",
            extra={"table_name": table_name, "security": "sql_injection_prevented"}
        )
        return False

    return True


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

            # SECURITY: Validate table name before using in queries
            if not validate_table_name(table_name):
                logger.warning(
                    f"Skipping invalid table name: {table_name}",
                    extra={"table_name": table_name}
                )
                continue

            # Use psycopg2.sql for safe SQL composition
            # Get row count
            count_query = sql.SQL("SELECT COUNT(*) as cnt FROM {}").format(
                sql.Identifier(table_name)
            )
            cursor.execute(count_query)
            row_count = cursor.fetchone()['cnt']

            # Get column info (parameterized query - already safe)
            cursor.execute("""
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_name = %s
                ORDER BY ordinal_position
            """, (table_name,))
            columns = [{"name": c['column_name'], "type": c['data_type']} for c in cursor.fetchall()]

            # Get sample data (first 3 rows)
            sample_query = sql.SQL("SELECT * FROM {} LIMIT 3").format(
                sql.Identifier(table_name)
            )
            cursor.execute(sample_query)
            sample = cursor.fetchall()

            tables.append({
                "table_name": table_name,
                "row_count": row_count,
                "columns": columns,
                "sample_data": [dict(s) for s in sample]
            })

        conn.close()

        logger.info(
            f"Database stats retrieved for {len(tables)} tables",
            extra={"table_count": len(tables)}
        )

        # Log activity
        log_activity_event("database_stats_fetched", {"table_count": len(tables)})

        return {
            "success": True,
            "database_path": mask_database_url(os.getenv('DATABASE_URL', '')),
            "database_type": "PostgreSQL",
            "connection_status": "connected",
            "total_tables": len(tables),
            "tables": tables,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        log_error_event("database", "connection_error", str(e))
        # Return minimal stats on error
        return {
            "success": False,
            "error": str(e),
            "database_path": mask_database_url(os.getenv('DATABASE_URL', '')),
            "database_type": "PostgreSQL",
            "connection_status": "disconnected",
            "total_tables": 0,
            "tables": [],
            "timestamp": datetime.now().isoformat()
        }


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
        data = api.get_net_gamma('SPY')
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


@router.get("/api/system/logs")
async def get_system_logs(limit: int = 50, log_type: str = "all"):
    """
    Get system error and activity logs.

    Args:
        limit: Maximum number of log entries to return (default 50)
        log_type: 'errors', 'activity', or 'all' (default 'all')
    """
    log_activity_event("system_logs_viewed", {"log_type": log_type})

    result = {
        "success": True,
        "timestamp": datetime.now().isoformat()
    }

    if log_type in ["errors", "all"]:
        result["errors"] = list(ERROR_LOG_BUFFER)[-limit:]
        result["error_count"] = len(ERROR_LOG_BUFFER)

    if log_type in ["activity", "all"]:
        result["activity"] = list(ACTIVITY_LOG_BUFFER)[-limit:]
        result["activity_count"] = len(ACTIVITY_LOG_BUFFER)

    return result


@router.delete("/api/system/logs/clear")
async def clear_system_logs(log_type: str = "all"):
    """Clear system logs"""
    if log_type in ["errors", "all"]:
        ERROR_LOG_BUFFER.clear()
    if log_type in ["activity", "all"]:
        ACTIVITY_LOG_BUFFER.clear()

    log_activity_event("logs_cleared", {"log_type": log_type})

    return {"success": True, "message": f"Cleared {log_type} logs"}


@router.get("/api/system/health")
async def get_system_health():
    """
    Comprehensive system health check.
    Returns status of all system components.
    """
    from zoneinfo import ZoneInfo

    health = {
        "timestamp": datetime.now().isoformat(),
        "overall_status": "healthy",
        "components": {}
    }

    issues = []

    # 1. Database Health
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.close()
        conn.close()
        health["components"]["database"] = {
            "status": "healthy",
            "message": "Connected"
        }
    except Exception as e:
        health["components"]["database"] = {
            "status": "error",
            "message": str(e)
        }
        issues.append("database")
        log_error_event("health_check", "database_error", str(e))

    # 2. Trading Volatility API Health
    try:
        from core_classes_and_engines import TradingVolatilityAPI
        circuit_breaker = getattr(TradingVolatilityAPI, '_shared_circuit_breaker_active', False)
        calls_this_min = getattr(TradingVolatilityAPI, '_shared_api_call_count_minute', 0)

        if circuit_breaker:
            health["components"]["trading_volatility_api"] = {
                "status": "degraded",
                "message": "Circuit breaker active",
                "calls_this_minute": calls_this_min
            }
            issues.append("trading_volatility_api")
        elif calls_this_min > 15:
            health["components"]["trading_volatility_api"] = {
                "status": "warning",
                "message": f"High usage: {calls_this_min}/20 calls",
                "calls_this_minute": calls_this_min
            }
        else:
            health["components"]["trading_volatility_api"] = {
                "status": "healthy",
                "message": "Operational",
                "calls_this_minute": calls_this_min
            }
    except Exception as e:
        health["components"]["trading_volatility_api"] = {
            "status": "unknown",
            "message": str(e)
        }

    # 3. Polygon API Health
    polygon_key = os.getenv('POLYGON_API_KEY')
    if polygon_key:
        health["components"]["polygon_api"] = {
            "status": "configured",
            "message": "API key present"
        }
    else:
        health["components"]["polygon_api"] = {
            "status": "not_configured",
            "message": "No API key"
        }

    # 4. Market Status
    try:
        now = datetime.now(ZoneInfo("America/New_York"))
        market_open = (
            now.weekday() < 5 and
            9 <= now.hour < 16 and
            not (now.hour == 9 and now.minute < 30)
        )
        health["components"]["market"] = {
            "status": "open" if market_open else "closed",
            "current_time_et": now.strftime("%H:%M:%S ET"),
            "day": now.strftime("%A")
        }
    except Exception as e:
        health["components"]["market"] = {
            "status": "unknown",
            "message": str(e)
        }

    # 5. Error Rate (last hour)
    one_hour_ago = datetime.now() - timedelta(hours=1)
    recent_errors = [
        e for e in ERROR_LOG_BUFFER
        if datetime.fromisoformat(e["timestamp"]) > one_hour_ago
    ]
    error_rate = len(recent_errors)

    health["components"]["error_rate"] = {
        "status": "healthy" if error_rate < 10 else "warning" if error_rate < 50 else "critical",
        "errors_last_hour": error_rate,
        "total_errors": len(ERROR_LOG_BUFFER)
    }

    if error_rate >= 50:
        issues.append("high_error_rate")

    # Determine overall status
    if len(issues) == 0:
        health["overall_status"] = "healthy"
    elif "database" in issues:
        health["overall_status"] = "critical"
    else:
        health["overall_status"] = "degraded"

    health["issues"] = issues

    return health


@router.get("/api/database/table-freshness")
async def get_table_freshness():
    """
    Get data freshness for each table (last record timestamps).
    Helps identify stale data.
    """
    freshness = {
        "timestamp": datetime.now().isoformat(),
        "tables": {}
    }

    # Tables and their timestamp columns
    table_configs = [
        ("gex_history", "timestamp"),
        ("autonomous_open_positions", "entry_date"),
        ("autonomous_closed_trades", "exit_date"),
        ("autonomous_trade_log", "timestamp"),
        ("backtest_results", "created_at"),
        ("regime_signals", "timestamp"),
        ("recommendations", "created_at"),
    ]

    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        for table_name, ts_column in table_configs:
            try:
                # Check if table exists
                cursor.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables
                        WHERE table_schema = 'public' AND table_name = %s
                    )
                """, (table_name,))

                if not cursor.fetchone()['exists']:
                    freshness["tables"][table_name] = {
                        "status": "not_found",
                        "last_record": None,
                        "age_minutes": None
                    }
                    continue

                # Get latest record timestamp
                query = sql.SQL("SELECT MAX({}) as latest FROM {}").format(
                    sql.Identifier(ts_column),
                    sql.Identifier(table_name)
                )
                cursor.execute(query)
                result = cursor.fetchone()

                if result and result['latest']:
                    latest = result['latest']
                    if isinstance(latest, str):
                        latest = datetime.fromisoformat(latest.replace('Z', '+00:00'))
                    elif not isinstance(latest, datetime):
                        latest = datetime.combine(latest, datetime.min.time())

                    age = datetime.now() - latest.replace(tzinfo=None)
                    age_minutes = int(age.total_seconds() / 60)

                    # Determine status based on age
                    if age_minutes < 60:
                        status = "fresh"
                    elif age_minutes < 1440:  # 24 hours
                        status = "recent"
                    else:
                        status = "stale"

                    freshness["tables"][table_name] = {
                        "status": status,
                        "last_record": latest.isoformat(),
                        "age_minutes": age_minutes,
                        "age_human": f"{age_minutes // 60}h {age_minutes % 60}m" if age_minutes >= 60 else f"{age_minutes}m"
                    }
                else:
                    freshness["tables"][table_name] = {
                        "status": "empty",
                        "last_record": None,
                        "age_minutes": None
                    }

            except Exception as e:
                freshness["tables"][table_name] = {
                    "status": "error",
                    "error": str(e)
                }

        conn.close()

    except Exception as e:
        freshness["error"] = str(e)
        log_error_event("database", "freshness_check_error", str(e))

    return freshness


@router.post("/api/system/cache/clear")
async def clear_system_cache():
    """Clear server-side caches"""
    try:
        # Try to clear TradingVolatilityAPI cache
        from core_classes_and_engines import TradingVolatilityAPI
        if hasattr(TradingVolatilityAPI, '_shared_response_cache'):
            TradingVolatilityAPI._shared_response_cache.clear()

        log_activity_event("cache_cleared", {"source": "admin_action"})

        return {
            "success": True,
            "message": "Server caches cleared successfully"
        }
    except Exception as e:
        log_error_event("cache", "clear_error", str(e))
        return {
            "success": False,
            "error": str(e)
        }


# Export the logging functions for use by other modules
__all__ = ['router', 'log_error_event', 'log_activity_event', 'ERROR_LOG_BUFFER', 'ACTIVITY_LOG_BUFFER']
