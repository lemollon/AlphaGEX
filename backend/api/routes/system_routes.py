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
