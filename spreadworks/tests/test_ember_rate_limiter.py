"""Unit tests for the sliding-window rate limiter tv_scanner.py's concurrent candidate pool
uses to keep every TradingVolatility call inside the vendor's real per-account caps (5
expensive calls/min, 60 calls/min overall) regardless of how many worker threads are calling
tv_get() at once. See spreadworks/backend/ember/legacy/rate_limiter.py.
"""
from __future__ import annotations

import threading
import time

from backend.ember.legacy.rate_limiter import RateLimiter


def test_acquire_never_exceeds_max_calls_in_the_window():
    limiter = RateLimiter(max_calls=3, period_s=0.3)
    start = time.monotonic()
    times = [_acquire_and_stamp(limiter) for _ in range(3)]
    # 3 calls within the window shouldn't have to wait at all.
    assert times[-1] - start < 0.1

    # A 4th call inside the same window must be pushed past the window boundary.
    fourth = _acquire_and_stamp(limiter)
    assert fourth - times[0] >= 0.3 - 0.02  # small tolerance for scheduler jitter


def test_acquire_is_thread_safe_under_concurrent_callers():
    """20 threads racing for a 5-per-0.2s budget must never see more than 5 in-flight
    timestamps inside any 0.2s window -- a broken (non-atomic) check-then-append would let
    a race admit more than max_calls."""
    limiter = RateLimiter(max_calls=5, period_s=0.2)
    stamps: list[float] = []
    lock = threading.Lock()

    def worker():
        limiter.acquire()
        with lock:
            stamps.append(time.monotonic())

    threads = [threading.Thread(target=worker) for _ in range(20)]
    for th in threads: th.start()
    for th in threads: th.join(timeout=5)

    assert len(stamps) == 20
    stamps.sort()
    # Slide a 0.2s window across the recorded acquisitions; none should ever contain > 5.
    for i, t in enumerate(stamps):
        in_window = sum(1 for s in stamps if t <= s < t + 0.2)
        assert in_window <= 5, f"window starting at acquisition {i} admitted {in_window} calls"


def _acquire_and_stamp(limiter: RateLimiter) -> float:
    limiter.acquire()
    return time.monotonic()
