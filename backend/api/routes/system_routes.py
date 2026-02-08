"""
System Management API routes - Autonomous Trader Control.
"""

import os
import subprocess
import signal
from datetime import datetime

from fastapi import APIRouter

router = APIRouter(prefix="/api/system", tags=["System"])


@router.get("/trader-status")
async def get_system_trader_status():
    """Get autonomous trader status and auto-start configuration"""
    try:
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

        alphagex_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        pid_file = os.path.join(alphagex_dir, "logs", "trader.pid")

        if os.path.exists(pid_file):
            with open(pid_file, 'r') as f:
                pid = f.read().strip()
                status["trader_pid"] = int(pid)

                try:
                    result = subprocess.run(['ps', '-p', pid], capture_output=True, text=True)
                    status["trader_running"] = result.returncode == 0
                except (OSError, subprocess.SubprocessError, FileNotFoundError):
                    status["trader_running"] = False

        if is_render:
            status["autostart_enabled"] = True
            status["watchdog_enabled"] = True
            status["autostart_type"] = "render_worker"
        else:
            try:
                result = subprocess.run(['crontab', '-l'], capture_output=True, text=True)
                crontab_content = result.stdout
                status["autostart_enabled"] = "auto_start_trader.sh" in crontab_content
                status["watchdog_enabled"] = "trader_watchdog.sh" in crontab_content
                status["autostart_type"] = "crontab" if status["autostart_enabled"] else None
            except (OSError, subprocess.SubprocessError, FileNotFoundError):
                status["autostart_enabled"] = False
                status["watchdog_enabled"] = False

        log_file = os.path.join(alphagex_dir, "logs", "trader.log")
        if os.path.exists(log_file):
            try:
                with open(log_file, 'r') as f:
                    lines = f.readlines()
                    if lines:
                        status["last_log_entry"] = lines[-1].strip()
            except (IOError, OSError, PermissionError):
                pass

        return {"success": True, "status": status}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/enable-autostart")
async def enable_autostart():
    """Enable autonomous trader auto-start on boot + watchdog"""
    try:
        is_render = bool(os.getenv("RENDER")) or bool(os.getenv("RENDER_SERVICE_NAME"))

        if is_render:
            return {
                "success": True,
                "message": "Auto-start is already configured via Render worker service (render.yaml).",
                "already_enabled": True,
                "platform": "render"
            }

        alphagex_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

        try:
            result = subprocess.run(['crontab', '-l'], capture_output=True, text=True)
            current_crontab = result.stdout
        except FileNotFoundError:
            return {
                "success": False,
                "error": "crontab command not found.",
                "platform": "unsupported"
            }
        except Exception:
            current_crontab = ""

        if "auto_start_trader.sh" in current_crontab and "trader_watchdog.sh" in current_crontab:
            return {
                "success": True,
                "message": "Auto-start already enabled",
                "already_enabled": True
            }

        new_entries = f"""
# AlphaGEX Autonomous Trader - Auto-start on boot
@reboot {alphagex_dir}/auto_start_trader.sh

# AlphaGEX Autonomous Trader - Watchdog (checks every minute, restarts if crashed)
* * * * * {alphagex_dir}/trader_watchdog.sh
"""

        lines = current_crontab.split('\n')
        filtered_lines = [l for l in lines if 'auto_start_trader.sh' not in l and 'trader_watchdog.sh' not in l]
        updated_crontab = '\n'.join(filtered_lines) + new_entries

        process = subprocess.Popen(['crontab', '-'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = process.communicate(input=updated_crontab.encode())

        if process.returncode != 0:
            return {"success": False, "error": f"Failed to update crontab: {stderr.decode()}"}

        return {
            "success": True,
            "message": "Auto-start enabled successfully!",
            "already_enabled": False
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/disable-autostart")
async def disable_autostart():
    """Disable autonomous trader auto-start"""
    try:
        try:
            result = subprocess.run(['crontab', '-l'], capture_output=True, text=True)
            current_crontab = result.stdout
        except (OSError, subprocess.SubprocessError, FileNotFoundError):
            return {"success": True, "message": "Auto-start already disabled (no crontab found)"}

        lines = current_crontab.split('\n')
        filtered_lines = [l for l in lines if 'auto_start_trader.sh' not in l and 'trader_watchdog.sh' not in l and l.strip()]
        updated_crontab = '\n'.join(filtered_lines) + '\n'

        process = subprocess.Popen(['crontab', '-'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = process.communicate(input=updated_crontab.encode())

        if process.returncode != 0:
            return {"success": False, "error": f"Failed to update crontab: {stderr.decode()}"}

        return {"success": True, "message": "Auto-start disabled."}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/start-trader")
async def start_trader_manually():
    """Manually start the autonomous trader"""
    try:
        alphagex_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        start_script = os.path.join(alphagex_dir, "auto_start_trader.sh")

        if not os.path.exists(start_script):
            return {"success": False, "error": f"Start script not found at {start_script}"}

        try:
            result = subprocess.run(
                [start_script],
                capture_output=True,
                text=True,
                cwd=alphagex_dir,
                timeout=30
            )
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Start script timed out after 30 seconds"}

        if result.returncode != 0:
            return {"success": False, "error": f"Start script failed: {result.stderr or result.stdout}"}

        return {"success": True, "message": "Trader started successfully", "output": result.stdout}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/stop-trader")
async def stop_trader_manually():
    """Manually stop the autonomous trader"""
    try:
        alphagex_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        pid_file = os.path.join(alphagex_dir, "logs", "trader.pid")

        if not os.path.exists(pid_file):
            return {"success": False, "error": "Trader is not running (no PID file found)"}

        try:
            with open(pid_file, 'r') as f:
                pid_content = f.read().strip()
                if not pid_content:
                    return {"success": False, "error": "PID file is empty"}
                pid = int(pid_content)
        except ValueError:
            return {"success": False, "error": f"Invalid PID file contents: '{pid_content[:50]}'"}

        if pid <= 0 or pid > 4194304:
            return {"success": False, "error": f"Invalid PID value: {pid}"}

        try:
            os.kill(pid, 0)

            try:
                cmdline_path = f"/proc/{pid}/cmdline"
                if os.path.exists(cmdline_path):
                    with open(cmdline_path, 'r') as f:
                        cmdline = f.read()
                        if 'python' not in cmdline.lower() and 'trader' not in cmdline.lower():
                            return {"success": False, "error": f"PID {pid} does not appear to be the trader process"}
            except (IOError, PermissionError):
                pass

            os.kill(pid, signal.SIGTERM)

            try:
                os.remove(pid_file)
            except OSError:
                pass  # PID file cleanup failed, ignore

            return {"success": True, "message": f"Trader stopped (PID: {pid})"}
        except ProcessLookupError:
            try:
                os.remove(pid_file)
            except OSError:
                pass  # PID file cleanup failed, ignore
            return {"success": False, "error": "Trader process not found. Cleaned up stale PID file."}
        except PermissionError:
            return {"success": False, "error": f"Permission denied when trying to stop PID {pid}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/config")
async def get_system_config():
    """
    Get system configuration values (read-only).
    Exposes key configuration parameters for UI display.
    """
    try:
        # Import config classes
        from config import (
            VIXConfig, GEXThresholdConfig, RateLimitConfig,
            TradeSetupConfig, RiskLevelConfig, SystemConfig,
            ImpliedVolatilityConfig
        )

        return {
            "success": True,
            "data": {
                "vix": {
                    "default_vix": VIXConfig.DEFAULT_VIX,
                    "low_threshold": VIXConfig.LOW_VIX_THRESHOLD,
                    "elevated_threshold": VIXConfig.ELEVATED_VIX_THRESHOLD,
                    "high_threshold": VIXConfig.HIGH_VIX_THRESHOLD,
                    "extreme_threshold": VIXConfig.EXTREME_VIX_THRESHOLD,
                },
                "gex": {
                    "use_adaptive_thresholds": GEXThresholdConfig.USE_ADAPTIVE_THRESHOLDS,
                    "adaptive_lookback_days": GEXThresholdConfig.ADAPTIVE_LOOKBACK_DAYS,
                    "fixed_thresholds": {
                        "extreme_negative": GEXThresholdConfig.FIXED_THRESHOLDS['extreme_negative'] / 1e9,
                        "high_negative": GEXThresholdConfig.FIXED_THRESHOLDS['high_negative'] / 1e9,
                        "moderate_negative": GEXThresholdConfig.FIXED_THRESHOLDS['moderate_negative'] / 1e9,
                        "moderate_positive": GEXThresholdConfig.FIXED_THRESHOLDS['moderate_positive'] / 1e9,
                        "high_positive": GEXThresholdConfig.FIXED_THRESHOLDS['high_positive'] / 1e9,
                        "extreme_positive": GEXThresholdConfig.FIXED_THRESHOLDS['extreme_positive'] / 1e9,
                    },
                },
                "rate_limits": {
                    "min_request_interval_seconds": RateLimitConfig.MIN_REQUEST_INTERVAL,
                    "circuit_breaker_duration_seconds": RateLimitConfig.CIRCUIT_BREAKER_DURATION,
                    "max_consecutive_errors": RateLimitConfig.MAX_CONSECUTIVE_ERRORS,
                    "cache_duration_seconds": RateLimitConfig.CACHE_DURATION,
                },
                "trade_setup": {
                    "min_confidence_threshold": TradeSetupConfig.MIN_CONFIDENCE_THRESHOLD,
                    "min_win_rate_threshold": TradeSetupConfig.MIN_WIN_RATE_THRESHOLD,
                    "spread_width_normal_pct": TradeSetupConfig.SPREAD_WIDTH_NORMAL * 100,
                    "spread_width_low_price_pct": TradeSetupConfig.SPREAD_WIDTH_LOW_PRICE * 100,
                },
                "risk": {
                    "extreme_risk_threshold": RiskLevelConfig.EXTREME_RISK_THRESHOLD,
                    "high_risk_threshold": RiskLevelConfig.HIGH_RISK_THRESHOLD,
                    "moderate_risk_threshold": RiskLevelConfig.MODERATE_RISK_THRESHOLD,
                    "daily_risk_levels": RiskLevelConfig.DAILY_RISK_LEVELS,
                },
                "implied_volatility": {
                    "default_iv_pct": ImpliedVolatilityConfig.DEFAULT_IV * 100,
                    "low_iv_threshold_pct": ImpliedVolatilityConfig.LOW_IV_THRESHOLD * 100,
                    "normal_iv_threshold_pct": ImpliedVolatilityConfig.NORMAL_IV_THRESHOLD * 100,
                    "high_iv_threshold_pct": ImpliedVolatilityConfig.HIGH_IV_THRESHOLD * 100,
                    "extreme_iv_threshold_pct": ImpliedVolatilityConfig.EXTREME_IV_THRESHOLD * 100,
                },
                "system": {
                    "environment": SystemConfig.ENVIRONMENT,
                    "log_level": SystemConfig.LOG_LEVEL,
                    "enable_adaptive_gex": SystemConfig.ENABLE_ADAPTIVE_GEX_THRESHOLDS,
                    "enable_adaptive_gamma": SystemConfig.ENABLE_ADAPTIVE_GAMMA_PATTERN,
                    "max_concurrent_api_calls": SystemConfig.MAX_CONCURRENT_API_CALLS,
                    "request_timeout_seconds": SystemConfig.REQUEST_TIMEOUT,
                },
            },
            "timestamp": datetime.now().isoformat()
        }
    except ImportError as e:
        return {"success": False, "error": f"Config import failed: {str(e)}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/cleanup-equity-snapshots")
async def cleanup_equity_snapshots(bot: str = None, confirm: bool = False):
    """
    Clean up corrupt equity snapshots for trading bots.

    This endpoint clears today's equity snapshots which may contain incorrect
    unrealized P&L values. New correct snapshots will be generated by the scheduler.

    Args:
        bot: Optional specific bot to clean (fortress, solomon, gideon, anchor, samson).
             If not specified, cleans all bots.
        confirm: Must be True to actually delete data (safety check)
    """
    from database_adapter import get_connection
    from zoneinfo import ZoneInfo

    CENTRAL_TZ = ZoneInfo("America/Chicago")
    today = datetime.now(CENTRAL_TZ).strftime('%Y-%m-%d')

    # Bot configurations
    all_bots = {
        'fortress': 'fortress_equity_snapshots',
        'solomon': 'solomon_equity_snapshots',
        'gideon': 'gideon_equity_snapshots',
        'anchor': 'anchor_equity_snapshots',
        'samson': 'samson_equity_snapshots',
    }

    # Validate bot parameter
    if bot:
        bot = bot.lower()
        if bot not in all_bots:
            return {
                "success": False,
                "error": f"Unknown bot: {bot}. Valid bots: {', '.join(all_bots.keys())}"
            }
        bots_to_clean = {bot: all_bots[bot]}
    else:
        bots_to_clean = all_bots

    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        if not confirm:
            # Preview mode - show what would be deleted
            preview = {}
            for bot_name, table_name in bots_to_clean.items():
                try:
                    cursor.execute(f"""
                        SELECT COUNT(*), MIN(timestamp), MAX(timestamp)
                        FROM {table_name}
                        WHERE DATE(timestamp::timestamptz AT TIME ZONE 'America/Chicago') = %s
                    """, (today,))
                    row = cursor.fetchone()
                    preview[bot_name] = {
                        "table": table_name,
                        "snapshots_today": row[0] or 0,
                        "earliest": row[1].isoformat() if row[1] else None,
                        "latest": row[2].isoformat() if row[2] else None
                    }
                except Exception as e:
                    preview[bot_name] = {"error": str(e)}

            conn.close()
            return {
                "success": False,
                "message": "Set confirm=true to delete today's snapshots. This allows fresh snapshots with correct P&L.",
                "date": today,
                "preview": preview
            }

        # Actually delete the snapshots
        results = {}
        for bot_name, table_name in bots_to_clean.items():
            try:
                cursor.execute(f"""
                    DELETE FROM {table_name}
                    WHERE DATE(timestamp::timestamptz AT TIME ZONE 'America/Chicago') = %s
                """, (today,))
                deleted = cursor.rowcount
                results[bot_name] = {"deleted": deleted, "table": table_name}
            except Exception as e:
                results[bot_name] = {"error": str(e)}

        conn.commit()
        conn.close()

        return {
            "success": True,
            "message": f"Cleaned up equity snapshots for {today}. Scheduler will create fresh snapshots.",
            "date": today,
            "results": results
        }

    except Exception as e:
        if conn:
            try:
                conn.close()
            except Exception:
                pass
        return {"success": False, "error": str(e)}


@router.get("/collector-health")
async def get_collector_health():
    """
    Get data collector health status from heartbeat table.

    Returns:
        - last_heartbeat: Timestamp of last heartbeat
        - status: Current collector status
        - is_healthy: True if heartbeat within last 10 minutes
        - heartbeat_age_minutes: Minutes since last heartbeat
        - recent_heartbeats: Last 10 heartbeat records
    """
    from database_adapter import get_connection
    from zoneinfo import ZoneInfo

    CENTRAL_TZ = ZoneInfo("America/Chicago")

    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Check if heartbeat table exists
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'collector_heartbeat'
            )
        """)
        table_exists = cursor.fetchone()[0]

        if not table_exists:
            conn.close()
            return {
                "success": True,
                "data": {
                    "is_healthy": False,
                    "status": "unknown",
                    "message": "Heartbeat table not yet created - collector may not have started",
                    "last_heartbeat": None,
                    "heartbeat_age_minutes": None,
                    "recent_heartbeats": []
                }
            }

        # Get latest heartbeat
        cursor.execute("""
            SELECT timestamp, status, error_message, market_open, is_holiday
            FROM collector_heartbeat
            ORDER BY timestamp DESC
            LIMIT 1
        """)
        latest = cursor.fetchone()

        if not latest:
            conn.close()
            return {
                "success": True,
                "data": {
                    "is_healthy": False,
                    "status": "no_heartbeat",
                    "message": "No heartbeat records found",
                    "last_heartbeat": None,
                    "heartbeat_age_minutes": None,
                    "recent_heartbeats": []
                }
            }

        last_timestamp, last_status, last_error, market_open, is_holiday = latest

        # Calculate age
        now = datetime.now(CENTRAL_TZ)
        if last_timestamp.tzinfo is None:
            last_timestamp = last_timestamp.replace(tzinfo=CENTRAL_TZ)
        else:
            last_timestamp = last_timestamp.astimezone(CENTRAL_TZ)

        age_seconds = (now - last_timestamp).total_seconds()
        age_minutes = age_seconds / 60

        # Healthy if heartbeat within 10 minutes
        is_healthy = age_minutes < 10

        # Get recent heartbeats
        cursor.execute("""
            SELECT timestamp, status, error_message, market_open, is_holiday
            FROM collector_heartbeat
            ORDER BY timestamp DESC
            LIMIT 10
        """)
        recent = cursor.fetchall()

        recent_heartbeats = [
            {
                "timestamp": row[0].isoformat() if row[0] else None,
                "status": row[1],
                "error": row[2],
                "market_open": row[3],
                "is_holiday": row[4]
            }
            for row in recent
        ]

        conn.close()

        # Determine health message
        if is_healthy:
            if last_status == "error":
                message = f"Collector running but had recent error: {last_error[:100] if last_error else 'Unknown'}"
            elif last_status == "holiday":
                message = "Collector running - market holiday"
            elif last_status == "idle" or last_status == "waiting":
                message = "Collector running - waiting for market open"
            else:
                message = "Collector healthy and running"
        else:
            message = f"Collector may be down - last heartbeat {age_minutes:.1f} minutes ago"

        return {
            "success": True,
            "data": {
                "is_healthy": is_healthy,
                "status": last_status,
                "message": message,
                "last_heartbeat": last_timestamp.isoformat(),
                "heartbeat_age_minutes": round(age_minutes, 2),
                "market_open": market_open,
                "is_holiday": is_holiday,
                "last_error": last_error,
                "recent_heartbeats": recent_heartbeats
            }
        }

    except Exception as e:
        if conn:
            try:
                conn.close()
            except Exception:
                pass
        return {"success": False, "error": str(e)}
