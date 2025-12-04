"""
Thread Watchdog Service

Monitors background threads and automatically restarts them if they crash.
This ensures data collection and trading continue even after thread failures.

Usage:
    from services.thread_watchdog import ThreadWatchdog

    watchdog = ThreadWatchdog()
    watchdog.register("DataCollector", target_func, kwargs={'arg': value})
    watchdog.start()
"""

import threading
import time
import traceback
from datetime import datetime
from typing import Dict, Callable, Any, Optional
from dataclasses import dataclass, field


@dataclass
class ThreadInfo:
    """Information about a monitored thread"""
    name: str
    target: Callable
    kwargs: Dict[str, Any] = field(default_factory=dict)
    thread: Optional[threading.Thread] = None
    restart_count: int = 0
    last_restart: Optional[datetime] = None
    last_alive_check: Optional[datetime] = None
    max_restarts: int = 10  # Max restarts per hour
    enabled: bool = True


class ThreadWatchdog:
    """
    Monitors and auto-restarts background threads.

    Features:
    - Automatic restart of crashed threads
    - Restart rate limiting (max 10 restarts/hour per thread)
    - Status reporting for diagnostics
    - Graceful shutdown
    """

    def __init__(self, check_interval: int = 30):
        """
        Initialize the watchdog.

        Args:
            check_interval: Seconds between health checks (default 30)
        """
        self.threads: Dict[str, ThreadInfo] = {}
        self.check_interval = check_interval
        self._running = False
        self._watchdog_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._restart_timestamps: Dict[str, list] = {}  # Track restart times for rate limiting

    def register(self, name: str, target: Callable, kwargs: Dict[str, Any] = None,
                 max_restarts: int = 10) -> None:
        """
        Register a thread to be monitored.

        Args:
            name: Unique name for the thread
            target: Function to run in the thread
            kwargs: Keyword arguments to pass to the function
            max_restarts: Maximum restarts allowed per hour
        """
        with self._lock:
            self.threads[name] = ThreadInfo(
                name=name,
                target=target,
                kwargs=kwargs or {},
                max_restarts=max_restarts
            )
            self._restart_timestamps[name] = []
            print(f"🔧 Watchdog: Registered thread '{name}'")

    def _start_thread(self, info: ThreadInfo) -> bool:
        """Start or restart a thread"""
        try:
            thread = threading.Thread(
                target=self._wrapped_target,
                args=(info,),
                daemon=True,
                name=info.name
            )
            thread.start()
            info.thread = thread
            info.last_restart = datetime.now()
            print(f"✅ Watchdog: Started thread '{info.name}'")
            return True
        except Exception as e:
            print(f"❌ Watchdog: Failed to start thread '{info.name}': {e}")
            return False

    def _wrapped_target(self, info: ThreadInfo) -> None:
        """Wrapper that catches exceptions and logs them"""
        try:
            info.target(**info.kwargs)
        except Exception as e:
            print(f"\n❌ Thread '{info.name}' crashed with exception:")
            print(f"   {type(e).__name__}: {e}")
            traceback.print_exc()
            # Thread will be detected as dead and restarted by watchdog

    def _can_restart(self, name: str) -> bool:
        """Check if we can restart (rate limiting)"""
        now = datetime.now()
        one_hour_ago = datetime.now().replace(microsecond=0)

        # Clean old timestamps
        self._restart_timestamps[name] = [
            ts for ts in self._restart_timestamps.get(name, [])
            if (now - ts).total_seconds() < 3600
        ]

        max_restarts = self.threads[name].max_restarts
        return len(self._restart_timestamps[name]) < max_restarts

    def _check_threads(self) -> None:
        """Check all threads and restart dead ones"""
        with self._lock:
            for name, info in self.threads.items():
                if not info.enabled:
                    continue

                info.last_alive_check = datetime.now()

                # Check if thread is alive
                if info.thread is None or not info.thread.is_alive():
                    if info.thread is not None:
                        print(f"\n⚠️  Watchdog: Thread '{name}' is dead!")

                    # Check rate limiting
                    if not self._can_restart(name):
                        print(f"🚫 Watchdog: Thread '{name}' hit restart limit (max {info.max_restarts}/hour)")
                        continue

                    # Restart the thread
                    print(f"🔄 Watchdog: Restarting thread '{name}'...")
                    if self._start_thread(info):
                        info.restart_count += 1
                        self._restart_timestamps[name].append(datetime.now())
                        print(f"   Total restarts: {info.restart_count}")

    def start(self) -> None:
        """Start the watchdog monitoring"""
        if self._running:
            print("⚠️  Watchdog already running")
            return

        self._running = True

        # Start all registered threads
        with self._lock:
            for name, info in self.threads.items():
                if info.enabled and (info.thread is None or not info.thread.is_alive()):
                    self._start_thread(info)

        # Start watchdog monitoring thread
        self._watchdog_thread = threading.Thread(
            target=self._monitor_loop,
            daemon=True,
            name="ThreadWatchdog"
        )
        self._watchdog_thread.start()
        print(f"🐕 Watchdog: Started monitoring (check interval: {self.check_interval}s)")

    def _monitor_loop(self) -> None:
        """Main monitoring loop"""
        while self._running:
            try:
                time.sleep(self.check_interval)
                self._check_threads()
            except Exception as e:
                print(f"❌ Watchdog monitor error: {e}")
                traceback.print_exc()

    def stop(self) -> None:
        """Stop the watchdog"""
        self._running = False
        print("🛑 Watchdog: Stopped monitoring")

    def get_status(self) -> Dict[str, Any]:
        """Get status of all monitored threads"""
        status = {
            "watchdog_running": self._running,
            "check_interval": self.check_interval,
            "threads": {}
        }

        with self._lock:
            for name, info in self.threads.items():
                is_alive = info.thread is not None and info.thread.is_alive()
                restarts_last_hour = len([
                    ts for ts in self._restart_timestamps.get(name, [])
                    if (datetime.now() - ts).total_seconds() < 3600
                ])

                status["threads"][name] = {
                    "alive": is_alive,
                    "enabled": info.enabled,
                    "restart_count": info.restart_count,
                    "restarts_last_hour": restarts_last_hour,
                    "last_restart": info.last_restart.isoformat() if info.last_restart else None,
                    "last_alive_check": info.last_alive_check.isoformat() if info.last_alive_check else None,
                    "can_restart": self._can_restart(name)
                }

        return status

    def enable_thread(self, name: str) -> bool:
        """Enable a thread for monitoring"""
        with self._lock:
            if name in self.threads:
                self.threads[name].enabled = True
                return True
        return False

    def disable_thread(self, name: str) -> bool:
        """Disable a thread from monitoring (won't restart)"""
        with self._lock:
            if name in self.threads:
                self.threads[name].enabled = False
                return True
        return False


# Global watchdog instance
_watchdog: Optional[ThreadWatchdog] = None


def get_watchdog() -> ThreadWatchdog:
    """Get or create the global watchdog instance"""
    global _watchdog
    if _watchdog is None:
        _watchdog = ThreadWatchdog(check_interval=30)
    return _watchdog


def get_watchdog_status() -> Dict[str, Any]:
    """Get watchdog status (safe to call even if not initialized)"""
    if _watchdog is None:
        return {"watchdog_running": False, "message": "Watchdog not initialized"}
    return _watchdog.get_status()
