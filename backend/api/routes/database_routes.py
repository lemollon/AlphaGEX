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

    # 4. Market Status (Central Time)
    try:
        now = datetime.now(ZoneInfo("America/Chicago"))
        market_open = (
            now.weekday() < 5 and
            8 <= now.hour < 15 and
            not (now.hour == 8 and now.minute < 30)
        )
        health["components"]["market"] = {
            "status": "open" if market_open else "closed",
            "current_time_ct": now.strftime("%H:%M:%S CT"),
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
    from zoneinfo import ZoneInfo

    # Use Central Time for display
    central_tz = ZoneInfo("America/Chicago")
    now_central = datetime.now(central_tz)

    freshness = {
        "timestamp": now_central.isoformat(),
        "timezone": "America/Chicago",
        "tables": {}
    }

    # Tables and their timestamp columns - COMPREHENSIVE LIST
    # Each tuple: (table_name, timestamp_column, expected_frequency_minutes)
    # expected_frequency: None = user-activated, 5 = every 5 min, 1440 = daily
    table_configs = [
        # Core Trading Tables
        ("autonomous_config", None, None),  # No timestamp - static config
        ("autonomous_open_positions", "created_at", 5),
        ("autonomous_closed_trades", "created_at", None),  # Per trade
        ("autonomous_trade_log", "date", None),  # Per trade
        ("autonomous_trade_activity", "timestamp", None),  # Per trade
        ("autonomous_live_status", "timestamp", 5),
        ("autonomous_equity_snapshots", "timestamp", 5),
        ("trading_decisions", "timestamp", None),  # Per decision
        ("trades", "timestamp", None),  # Per trade
        ("positions", "timestamp", None),  # Per position

        # Market Data Tables
        ("gex_history", "timestamp", 5),
        ("gamma_history", "timestamp", 5),
        ("gamma_daily_summary", "date", 1440),
        ("gex_levels", "timestamp", 5),
        ("gex_snapshots_detailed", "timestamp", 5),
        ("gamma_strike_history", "timestamp", 5),
        ("market_data", "timestamp", 5),
        ("historical_open_interest", "date", 1440),
        ("regime_signals", "timestamp", 5),
        ("regime_classifications", "timestamp", 5),
        ("spy_correlation", "date", 1440),
        ("gamma_correlation", "timestamp", 1440),
        ("gex_change_log", "timestamp", None),

        # AI/ML Tables
        ("ai_predictions", "timestamp", None),
        ("ai_performance", "date", 1440),
        ("ai_recommendations", "timestamp", None),
        ("pattern_learning", "last_seen", None),
        ("ml_predictions", "timestamp", None),
        ("probability_predictions", "timestamp", None),
        ("ai_analysis_history", "timestamp", None),

        # Backtest Tables
        ("backtest_results", "timestamp", None),  # Weekly + on-demand
        ("backtest_summary", "timestamp", None),
        ("backtest_trades", "timestamp", None),
        ("spx_wheel_backtest_runs", "created_at", None),
        ("spx_wheel_backtest_equity", "backtest_date", None),
        ("spx_wheel_backtest_trades", "backtest_date", None),
        ("sucker_statistics", "created_at", None),
        ("psychology_analysis", "timestamp", 5),

        # User-Activated Feature Tables
        ("alerts", "created_at", None),
        ("alert_history", "triggered_at", None),
        ("trade_setups", "timestamp", None),
        ("conversations", "timestamp", None),
        ("push_subscriptions", "created_at", None),
        ("wheel_cycles", "created_at", None),
        ("wheel_legs", "created_at", None),
        ("wheel_activity_log", "timestamp", None),
        ("vix_hedge_signals", "created_at", None),
        ("vix_hedge_positions", "created_at", None),

        # System Tables
        ("background_jobs", "started_at", None),
        ("scheduler_state", "updated_at", 5),
        ("data_collection_log", "timestamp", 5),
        ("performance", "date", 1440),
        ("recommendations", "timestamp", None),

        # Unified Engine Tables
        ("unified_positions", "created_at", None),
        ("unified_trades", "created_at", None),
        ("strategy_competition", "timestamp", None),

        # Validation Tables
        ("paper_signals", "timestamp", None),
        ("paper_outcomes", "timestamp", None),

        # Data Collection Tables (need wiring)
        ("greeks_snapshots", "timestamp", None),
        ("vix_term_structure", "timestamp", None),
        ("options_flow", "timestamp", None),
        ("market_snapshots", "timestamp", None),
        ("position_sizing_history", "timestamp", None),
        ("price_history", "timestamp", None),
        ("options_chain_snapshots", "timestamp", None),
        ("options_collection_log", "timestamp", None),
    ]

    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        for table_name, ts_column, expected_freq in table_configs:
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
                        "age_minutes": None,
                        "expected_frequency": expected_freq
                    }
                    continue

                # Handle tables without timestamp column
                if ts_column is None:
                    # Just get row count for tables without timestamps
                    count_query = sql.SQL("SELECT COUNT(*) as cnt FROM {}").format(
                        sql.Identifier(table_name)
                    )
                    cursor.execute(count_query)
                    count = cursor.fetchone()['cnt']
                    freshness["tables"][table_name] = {
                        "status": "configured" if count > 0 else "empty",
                        "last_record": "N/A (no timestamp column)",
                        "row_count": count,
                        "age_minutes": None,
                        "expected_frequency": expected_freq
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

                    # Make timezone-aware if not already
                    if latest.tzinfo is None:
                        # Assume UTC for naive datetimes from database
                        latest = latest.replace(tzinfo=ZoneInfo("UTC"))

                    # Convert to Central Time for display
                    latest_central = latest.astimezone(central_tz)

                    # Calculate age from now
                    age = now_central - latest_central
                    age_minutes = int(age.total_seconds() / 60)

                    # Determine status based on age
                    if age_minutes < 60:
                        status = "fresh"
                    elif age_minutes < 1440:  # 24 hours
                        status = "recent"
                    else:
                        status = "stale"

                    # Check if data is stale based on expected frequency
                    is_stale = False
                    if expected_freq and age_minutes > expected_freq * 2:
                        is_stale = True
                        status = "stale"

                    freshness["tables"][table_name] = {
                        "status": status,
                        "last_record": latest_central.strftime("%Y-%m-%d %I:%M:%S %p CT"),
                        "age_minutes": age_minutes,
                        "age_human": f"{age_minutes // 60}h {age_minutes % 60}m" if age_minutes >= 60 else f"{age_minutes}m",
                        "expected_frequency": expected_freq,
                        "is_stale": is_stale
                    }
                else:
                    freshness["tables"][table_name] = {
                        "status": "empty",
                        "last_record": None,
                        "age_minutes": None,
                        "expected_frequency": expected_freq
                    }

            except Exception as e:
                # Rollback to clear aborted transaction state
                conn.rollback()
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


# ============================================================================
# Data Collection Diagnostics & Manual Trigger
# ============================================================================

@router.get("/api/data-collection/status")
async def get_data_collection_status():
    """
    Get status of data collection threads and last collection times.
    Helps diagnose why data might not be collecting.
    """
    import threading
    from zoneinfo import ZoneInfo

    status = {
        "timestamp": datetime.now().isoformat(),
        "threads": {},
        "watchdog": {},
        "last_collections": {},
        "api_status": {},
        "diagnostics": []
    }

    # Check watchdog status first (preferred method)
    try:
        from services.thread_watchdog import get_watchdog_status
        watchdog_status = get_watchdog_status()
        status["watchdog"] = watchdog_status

        if watchdog_status.get("watchdog_running"):
            status["diagnostics"].append("OK: Thread Watchdog is ACTIVE and monitoring threads")
            # Get detailed thread info from watchdog
            for name, thread_info in watchdog_status.get("threads", {}).items():
                status["threads"][name] = {
                    "alive": thread_info.get("alive", False),
                    "restart_count": thread_info.get("restart_count", 0),
                    "restarts_last_hour": thread_info.get("restarts_last_hour", 0),
                    "last_restart": thread_info.get("last_restart"),
                    "can_restart": thread_info.get("can_restart", True),
                    "monitored": True
                }
                if not thread_info.get("alive"):
                    status["diagnostics"].append(f"WARNING: {name} is dead but watchdog will restart it")
        else:
            status["diagnostics"].append("WARNING: Thread Watchdog is NOT running - threads won't auto-restart")
    except ImportError:
        status["diagnostics"].append("WARNING: Thread Watchdog module not available")

    # Also check running threads directly (fallback)
    for thread in threading.enumerate():
        if thread.name in ["AutomatedDataCollector", "AutonomousTrader", "PsychologyNotificationMonitor", "ThreadWatchdog"]:
            if thread.name not in status["threads"]:
                status["threads"][thread.name] = {}
            status["threads"][thread.name]["alive"] = thread.is_alive()
            status["threads"][thread.name]["daemon"] = thread.daemon

    # Check if expected threads exist
    expected_threads = ["AutomatedDataCollector", "AutonomousTrader"]
    for expected in expected_threads:
        if expected not in status["threads"] or not status["threads"].get(expected, {}).get("alive"):
            if not status.get("watchdog", {}).get("watchdog_running"):
                status["diagnostics"].append(f"CRITICAL: {expected} not running and watchdog is inactive")

    # Check last collection times from database
    try:
        conn = get_connection()
        c = conn.cursor()

        # Check gex_history
        c.execute("SELECT MAX(timestamp) FROM gex_history WHERE symbol = 'SPY'")
        result = c.fetchone()
        if result and result[0]:
            last_gex = result[0]
            status["last_collections"]["gex_history"] = str(last_gex)
            age_hours = (datetime.now() - last_gex).total_seconds() / 3600 if isinstance(last_gex, datetime) else None
            if age_hours and age_hours > 1:
                status["diagnostics"].append(f"STALE: gex_history last updated {age_hours:.1f} hours ago")

        # Check scheduler_state
        c.execute("SELECT updated_at, is_running FROM scheduler_state WHERE id = 1")
        result = c.fetchone()
        if result:
            status["last_collections"]["scheduler_state"] = str(result[0])
            status["last_collections"]["scheduler_is_running"] = result[1]

        # Check data_collection_log
        c.execute("SELECT MAX(timestamp), COUNT(*) FROM data_collection_log WHERE timestamp > NOW() - INTERVAL '1 day'")
        result = c.fetchone()
        if result:
            status["last_collections"]["data_collection_log_last"] = str(result[0]) if result[0] else "Never"
            status["last_collections"]["collections_last_24h"] = result[1]

        conn.close()

    except Exception as e:
        status["diagnostics"].append(f"DATABASE ERROR: {str(e)}")

    # Check TradingVolatility API status
    try:
        from core_classes_and_engines import TradingVolatilityAPI
        api = TradingVolatilityAPI()
        status["api_status"]["trading_volatility"] = {
            "api_key_configured": bool(api.api_key),
            "endpoint": api.endpoint,
            "circuit_breaker_active": TradingVolatilityAPI._shared_circuit_breaker_active,
            "calls_this_minute": TradingVolatilityAPI._shared_api_call_count_minute
        }
        if not api.api_key:
            status["diagnostics"].append("CONFIG ERROR: TRADING_VOLATILITY_API_KEY not set")
    except Exception as e:
        status["api_status"]["trading_volatility"] = {"error": str(e)}
        status["diagnostics"].append(f"API IMPORT ERROR: {str(e)}")

    # Check market hours (Central Time)
    try:
        ct_tz = ZoneInfo("America/Chicago")
        now_ct = datetime.now(ct_tz)
        is_market_hours = (
            now_ct.weekday() < 5 and
            ((now_ct.hour == 8 and now_ct.minute >= 30) or (now_ct.hour > 8 and now_ct.hour < 15))
        )
        status["market_status"] = {
            "current_time_ct": now_ct.strftime("%Y-%m-%d %H:%M:%S CT"),
            "is_market_hours": is_market_hours,
            "day_of_week": now_ct.strftime("%A")
        }
        if not is_market_hours:
            status["diagnostics"].append("INFO: Market is closed - data collection only runs during market hours (9:30 AM - 4:00 PM ET)")
    except Exception as e:
        status["diagnostics"].append(f"TIMEZONE ERROR: {str(e)}")

    return {"success": True, "data": status}


@router.post("/api/data-collection/trigger")
async def trigger_data_collection():
    """
    Manually trigger data collection.
    Useful for testing or when automatic collection has stopped.
    """
    results = {
        "timestamp": datetime.now().isoformat(),
        "collections": {}
    }

    # Try to collect GEX data
    try:
        from gamma.gex_history_snapshot_job import save_gex_snapshot
        success = save_gex_snapshot('SPY')
        results["collections"]["gex_snapshot"] = {
            "success": success,
            "message": "GEX snapshot saved" if success else "Failed to save GEX snapshot"
        }
    except Exception as e:
        results["collections"]["gex_snapshot"] = {
            "success": False,
            "error": str(e)
        }

    # Try to update scheduler state
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute("""
            UPDATE scheduler_state
            SET updated_at = CURRENT_TIMESTAMP,
                last_trade_check = CURRENT_TIMESTAMP
            WHERE id = 1
        """)
        conn.commit()
        conn.close()
        results["collections"]["scheduler_state"] = {"success": True}
    except Exception as e:
        results["collections"]["scheduler_state"] = {"success": False, "error": str(e)}

    # Log the manual trigger
    log_activity_event("manual_data_collection", results)

    return {"success": True, "data": results}


# ============================================================================
# Thread Watchdog Management
# ============================================================================

@router.get("/api/watchdog/status")
async def get_watchdog_status_endpoint():
    """
    Get detailed status of the thread watchdog and all monitored threads.
    """
    try:
        from services.thread_watchdog import get_watchdog_status
        status = get_watchdog_status()
        return {"success": True, "data": status}
    except ImportError:
        return {
            "success": False,
            "error": "Thread watchdog module not available",
            "data": {"watchdog_running": False}
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/api/watchdog/restart-thread/{thread_name}")
async def restart_thread(thread_name: str):
    """
    Force restart a specific thread.
    Useful when a thread is stuck but not technically dead.
    """
    try:
        from services.thread_watchdog import get_watchdog

        watchdog = get_watchdog()

        if thread_name not in watchdog.threads:
            return {
                "success": False,
                "error": f"Thread '{thread_name}' not registered with watchdog",
                "available_threads": list(watchdog.threads.keys())
            }

        # Get thread info and restart
        info = watchdog.threads[thread_name]

        # Kill old thread if running (it's a daemon, will die when we lose reference)
        if info.thread and info.thread.is_alive():
            # Can't kill threads in Python, but we can start a new one
            # The old daemon thread will eventually die
            pass

        # Start new thread
        success = watchdog._start_thread(info)

        if success:
            info.restart_count += 1
            watchdog._restart_timestamps[thread_name].append(datetime.now())

        log_activity_event("manual_thread_restart", {
            "thread": thread_name,
            "success": success
        })

        return {
            "success": success,
            "message": f"Thread '{thread_name}' restart {'successful' if success else 'failed'}",
            "restart_count": info.restart_count
        }

    except ImportError:
        return {"success": False, "error": "Thread watchdog not available"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# Export the logging functions for use by other modules
__all__ = ['router', 'log_error_event', 'log_activity_event', 'ERROR_LOG_BUFFER', 'ACTIVITY_LOG_BUFFER']
