"""
Graceful Shutdown Manager - Zero-Downtime Deployment Support
=============================================================

Ensures AlphaGEX continues working during deployments by:
1. Draining in-flight requests before shutdown
2. Closing database connections gracefully
3. Stopping background threads cleanly
4. Safeguarding open positions
5. Coordinating shutdown across services

Usage:
    from backend.services.graceful_shutdown import shutdown_manager

    # In FastAPI shutdown event:
    await shutdown_manager.shutdown()

Author: AlphaGEX
Date: 2026-01-14
"""

import asyncio
import logging
import signal
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime
from enum import Enum
from typing import Callable, Dict, List, Optional, Set
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

CENTRAL_TZ = ZoneInfo("America/Chicago")


class ShutdownPhase(Enum):
    """Phases of graceful shutdown"""
    RUNNING = "RUNNING"           # Normal operation
    DRAINING = "DRAINING"         # Stop accepting new requests, finish in-flight
    CLOSING = "CLOSING"           # Close connections and resources
    TERMINATED = "TERMINATED"     # Shutdown complete


class GracefulShutdownManager:
    """
    Singleton manager for coordinating graceful shutdown across all components.

    Ensures zero-downtime deployments by:
    - Tracking in-flight requests
    - Coordinating component shutdown order
    - Providing readiness state for load balancers
    """

    _instance = None
    _lock = threading.Lock()

    # Shutdown timing (seconds)
    DRAIN_TIMEOUT = 30      # Max time to wait for in-flight requests
    CLOSE_TIMEOUT = 15      # Max time to close connections
    POSITION_TIMEOUT = 30   # Max time for position safeguarding

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._phase = ShutdownPhase.RUNNING
        self._shutdown_requested = False
        self._ready = False  # Not ready until startup complete

        # Track in-flight requests
        self._in_flight_requests: Set[str] = set()
        self._request_lock = threading.Lock()

        # Shutdown callbacks (called in order)
        self._shutdown_callbacks: List[Callable] = []

        # Components to notify
        self._components: Dict[str, any] = {}

        # Shutdown timestamp
        self._shutdown_started: Optional[datetime] = None

        self._initialized = True
        logger.info("GracefulShutdownManager initialized")

    @property
    def phase(self) -> ShutdownPhase:
        """Current shutdown phase"""
        return self._phase

    @property
    def is_ready(self) -> bool:
        """Whether the service is ready to accept requests"""
        return self._ready and self._phase == ShutdownPhase.RUNNING

    @property
    def is_healthy(self) -> bool:
        """Whether the service is healthy (can be true even during drain)"""
        return self._phase in (ShutdownPhase.RUNNING, ShutdownPhase.DRAINING)

    @property
    def is_shutting_down(self) -> bool:
        """Whether shutdown has been initiated"""
        return self._shutdown_requested

    @property
    def in_flight_count(self) -> int:
        """Number of requests currently being processed"""
        return len(self._in_flight_requests)

    def set_ready(self, ready: bool = True):
        """Mark the service as ready (called after startup complete)"""
        self._ready = ready
        logger.info(f"Service readiness: {'READY' if ready else 'NOT READY'}")

    def register_component(self, name: str, component: any):
        """Register a component that needs shutdown notification"""
        self._components[name] = component
        logger.debug(f"Registered component: {name}")

    def add_shutdown_callback(self, callback: Callable):
        """Add a callback to be called during shutdown"""
        self._shutdown_callbacks.append(callback)

    def track_request(self, request_id: str):
        """Start tracking an in-flight request"""
        if self._phase != ShutdownPhase.RUNNING:
            return False  # Reject new requests during shutdown

        with self._request_lock:
            self._in_flight_requests.add(request_id)
        return True

    def complete_request(self, request_id: str):
        """Mark a request as completed"""
        with self._request_lock:
            self._in_flight_requests.discard(request_id)

    async def shutdown(self):
        """
        Execute graceful shutdown sequence.

        Order:
        1. DRAINING: Stop accepting new requests, wait for in-flight
        2. CLOSING: Close connections and resources
        3. TERMINATED: Shutdown complete
        """
        if self._shutdown_requested:
            logger.warning("Shutdown already in progress")
            return

        self._shutdown_requested = True
        self._shutdown_started = datetime.now(CENTRAL_TZ)

        logger.info("=" * 60)
        logger.info("GRACEFUL SHUTDOWN INITIATED")
        logger.info(f"Time: {self._shutdown_started.strftime('%Y-%m-%d %H:%M:%S CT')}")
        logger.info("=" * 60)

        # Phase 1: DRAINING
        await self._drain_phase()

        # Phase 2: CLOSING
        await self._close_phase()

        # Phase 3: TERMINATED
        self._phase = ShutdownPhase.TERMINATED

        elapsed = (datetime.now(CENTRAL_TZ) - self._shutdown_started).total_seconds()
        logger.info(f"Graceful shutdown complete in {elapsed:.1f}s")

    async def _drain_phase(self):
        """Phase 1: Stop accepting new requests, wait for in-flight"""
        self._phase = ShutdownPhase.DRAINING
        self._ready = False  # Tell load balancer we're draining

        logger.info(f"[DRAIN] Starting drain phase (timeout: {self.DRAIN_TIMEOUT}s)")
        logger.info(f"[DRAIN] In-flight requests: {self.in_flight_count}")

        start = time.time()
        while self.in_flight_count > 0 and (time.time() - start) < self.DRAIN_TIMEOUT:
            logger.info(f"[DRAIN] Waiting for {self.in_flight_count} requests...")
            await asyncio.sleep(1)

        if self.in_flight_count > 0:
            logger.warning(f"[DRAIN] Timeout! {self.in_flight_count} requests still in-flight")
        else:
            logger.info("[DRAIN] All requests completed")

    async def _close_phase(self):
        """Phase 2: Close connections and resources"""
        self._phase = ShutdownPhase.CLOSING

        logger.info(f"[CLOSE] Starting close phase (timeout: {self.CLOSE_TIMEOUT}s)")

        # Execute shutdown callbacks
        for i, callback in enumerate(self._shutdown_callbacks):
            try:
                logger.info(f"[CLOSE] Running callback {i+1}/{len(self._shutdown_callbacks)}")
                if asyncio.iscoroutinefunction(callback):
                    await callback()
                else:
                    callback()
            except Exception as e:
                logger.error(f"[CLOSE] Callback {i+1} failed: {e}")

        # Close database pool
        await self._close_database()

        # Stop thread watchdog
        await self._stop_watchdog()

        # Safeguard positions
        await self._safeguard_positions()

    async def _close_database(self):
        """Close database connection pool"""
        try:
            from database_adapter import close_pool
            logger.info("[CLOSE] Closing database connection pool...")
            close_pool()
            logger.info("[CLOSE] Database pool closed")
        except ImportError:
            logger.debug("[CLOSE] Database adapter not available")
        except Exception as e:
            logger.error(f"[CLOSE] Database close failed: {e}")

    async def _stop_watchdog(self):
        """Stop thread watchdog"""
        try:
            watchdog = self._components.get('watchdog')
            if watchdog and hasattr(watchdog, 'stop'):
                logger.info("[CLOSE] Stopping thread watchdog...")
                watchdog.stop()
                logger.info("[CLOSE] Watchdog stopped")
        except Exception as e:
            logger.error(f"[CLOSE] Watchdog stop failed: {e}")

    async def _safeguard_positions(self):
        """Log open positions state (don't force close - let market decide)"""
        try:
            from database_adapter import get_connection

            logger.info("[CLOSE] Checking open positions...")

            conn = get_connection()
            cursor = conn.cursor()

            # Get count of open positions
            cursor.execute("""
                SELECT bot_name, COUNT(*) as count,
                       SUM(CASE WHEN unrealized_pnl < 0 THEN 1 ELSE 0 END) as losing
                FROM autonomous_open_positions
                WHERE status = 'OPEN'
                GROUP BY bot_name
            """)

            rows = cursor.fetchall()
            if rows:
                logger.warning("[CLOSE] OPEN POSITIONS AT SHUTDOWN:")
                for row in rows:
                    logger.warning(f"  {row[0]}: {row[1]} positions ({row[2]} losing)")

                # Log to database for recovery tracking
                cursor.execute("""
                    INSERT INTO shutdown_log (timestamp, open_positions, details)
                    VALUES (NOW(), %s, %s)
                    ON CONFLICT DO NOTHING
                """, [
                    sum(r[1] for r in rows),
                    str({r[0]: r[1] for r in rows})
                ])
                conn.commit()
            else:
                logger.info("[CLOSE] No open positions")

            cursor.close()
            conn.close()

        except Exception as e:
            logger.error(f"[CLOSE] Position check failed: {e}")


# Global singleton instance
shutdown_manager = GracefulShutdownManager()


def get_shutdown_manager() -> GracefulShutdownManager:
    """Get the global shutdown manager instance"""
    return shutdown_manager


# Signal handlers for worker processes
def setup_signal_handlers():
    """Setup signal handlers for graceful shutdown"""

    def handle_signal(signum, frame):
        sig_name = signal.Signals(signum).name
        logger.info(f"Received signal {sig_name} - initiating graceful shutdown")
        shutdown_manager._shutdown_requested = True

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    logger.info("Signal handlers installed (SIGTERM, SIGINT)")


# FastAPI lifespan context manager (modern approach)
@asynccontextmanager
async def lifespan_manager(app):
    """
    FastAPI lifespan context manager for startup/shutdown.

    Usage in main.py:
        from backend.services.graceful_shutdown import lifespan_manager
        app = FastAPI(lifespan=lifespan_manager)
    """
    # Startup
    logger.info("Starting AlphaGEX with graceful shutdown support...")
    setup_signal_handlers()

    # Allow time for all components to initialize
    await asyncio.sleep(0.5)
    shutdown_manager.set_ready(True)

    yield  # Application runs here

    # Shutdown
    await shutdown_manager.shutdown()
