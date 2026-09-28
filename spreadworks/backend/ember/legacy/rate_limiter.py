"""Thread-safe sliding-window rate limiter shared by tv_scanner.py's TradingVolatility
calls (2026-09-28 concurrency redesign -- see PR). Extracted to its own module (same
split as ember_lock.py) so the limiter itself is unit-testable without importing
tv_scanner.py, which executes its scan top-level on import with no __main__ guard.

tv_scanner.py runs candidate evaluation on a bounded thread pool instead of one
name at a time; every TradingVolatility call funnels through tv_get(), which now
acquires a slot from GENERAL_LIMITER (TV's documented 60 calls/min) and, for the
screener-preset and GEX-curve calls (marked expensive=True), an additional slot from
EXPENSIVE_LIMITER (TV's documented 5 calls/min) before the request goes out. Both
limiters are shared across every worker thread, so the real cap is enforced
regardless of how many names are being evaluated at once -- concurrency changes WHEN
a name's non-TV work (ThetaData pricing, RSI, row building) happens, never how fast
TradingVolatility itself is hit.
"""
from __future__ import annotations

import threading
import time


class RateLimiter:
    """At most `max_calls` acquisitions in any trailing `period_s` window. acquire()
    blocks the calling thread until a slot is free, then reserves it -- the
    reservation (append under lock) happens before the lock releases, so two threads
    racing for the last slot can never both succeed for the same window. Never raises."""

    def __init__(self, max_calls: int, period_s: float):
        self.max_calls = max_calls
        self.period_s = period_s
        self._times: list[float] = []
        self._lock = threading.Lock()

    def acquire(self) -> None:
        while True:
            with self._lock:
                now = time.monotonic()
                self._times = [t for t in self._times if now - t < self.period_s]
                if len(self._times) < self.max_calls:
                    self._times.append(now)
                    return
                wait = self.period_s - (now - self._times[0])
            time.sleep(max(wait, 0.01))
