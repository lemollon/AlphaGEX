"""Unit tests for the sliding-window rate limiter tv_scanner.py's concurrent candidate pool
uses to keep every TradingVolatility call inside the vendor's real per-account caps (5
expensive calls/min, 60 calls/min overall) regardless of how many worker threads are calling
tv_get() at once. See spreadworks/backend/ember/legacy/rate_limiter.py.

The window-boundary test injects a fake clock/sleep pair (RateLimiter's clock=/sleep=
constructor args) instead of sleeping in real wall-clock time -- deterministic and instant,
so it can't flake on a slow or loaded CI runner. The thread-safety test uses real threads on
purpose (that's the property under test); its assertion is a hard invariant (never more than
max_calls timestamps in any window), not a timing tolerance, so it isn't speed-sensitive --
only the join() timeout has margin, widened for slower shared runners.
"""
from __future__ import annotations

import threading
import time

from backend.ember.legacy.rate_limiter import RateLimiter


class _FakeClock:
    """A controllable clock: now() reads the current fake time, sleep() advances it by
    exactly the requested amount -- no real waiting, no scheduler jitter."""

    def __init__(self):
        self.t = 0.0

    def now(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.t += seconds


def test_acquire_never_exceeds_max_calls_in_the_window():
    clock = _FakeClock()
    limiter = RateLimiter(max_calls=3, period_s=10.0, clock=clock.now, sleep=clock.sleep)

    for _ in range(3):
        limiter.acquire()
    # 3 calls within the budget never have to wait.
    assert clock.t == 0.0

    # A 4th call inside the same window must be pushed exactly to the window boundary --
    # deterministic given the fake clock, no tolerance needed.
    limiter.acquire()
    assert clock.t == 10.0

    # Two more calls at the (now-advanced) fake time still fit inside the fresh window.
    limiter.acquire()
    limiter.acquire()
    assert clock.t == 10.0

    # The budget is full again (3 calls sitting at t=10.0) -- the next acquire() must wait a
    # full period for them to age out before a new slot opens.
    limiter.acquire()
    assert clock.t == 20.0


def test_acquire_is_thread_safe_under_concurrent_callers():
    """24 threads racing for a 6-per-0.3s budget must never see more than 6 in-flight
    timestamps inside any 0.3s window -- a broken (non-atomic) check-then-append would let
    a race admit more than max_calls. The window/count/timeout are generous on purpose so
    this is a correctness check, not a speed check, on a slow or loaded CI runner."""
    limiter = RateLimiter(max_calls=6, period_s=0.3)
    stamps: list[float] = []
    lock = threading.Lock()

    def worker():
        limiter.acquire()
        with lock:
            stamps.append(time.monotonic())

    threads = [threading.Thread(target=worker) for _ in range(24)]
    for th in threads: th.start()
    for th in threads: th.join(timeout=15)

    assert len(stamps) == 24
    stamps.sort()
    # Slide a 0.3s window across the recorded acquisitions; none should ever contain > 6.
    for i, t in enumerate(stamps):
        in_window = sum(1 for s in stamps if t <= s < t + 0.3)
        assert in_window <= 6, f"window starting at acquisition {i} admitted {in_window} calls"
