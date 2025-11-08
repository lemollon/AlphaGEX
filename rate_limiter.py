"""
Centralized Rate Limiter for AlphaGEX
Prevents API overuse across all deployments
"""

import time
import threading
from collections import deque
from datetime import datetime, timedelta

class RateLimiter:
    """
    Thread-safe rate limiter with multiple strategies
    """

    def __init__(self, max_calls_per_minute=15, max_calls_per_hour=800):
        """
        Initialize rate limiter

        Args:
            max_calls_per_minute: Maximum API calls per minute (default: 15 for safety margin)
            max_calls_per_hour: Maximum API calls per hour (default: 800)
        """
        self.max_calls_per_minute = max_calls_per_minute
        self.max_calls_per_hour = max_calls_per_hour

        # Track call timestamps
        self.call_history_minute = deque(maxlen=max_calls_per_minute * 2)
        self.call_history_hour = deque(maxlen=max_calls_per_hour * 2)

        # Thread lock for safety
        self.lock = threading.Lock()

        # Statistics
        self.total_calls = 0
        self.total_blocked = 0
        self.total_delayed = 0

    def can_make_request(self) -> tuple[bool, float]:
        """
        Check if a request can be made now

        Returns:
            (can_proceed, wait_time_seconds)
        """
        with self.lock:
            now = time.time()

            # Clean old entries from minute window
            while self.call_history_minute and now - self.call_history_minute[0] > 60:
                self.call_history_minute.popleft()

            # Clean old entries from hour window
            while self.call_history_hour and now - self.call_history_hour[0] > 3600:
                self.call_history_hour.popleft()

            # Check minute limit
            if len(self.call_history_minute) >= self.max_calls_per_minute:
                # Calculate when next slot becomes available
                oldest_call = self.call_history_minute[0]
                wait_time = 60 - (now - oldest_call)
                return False, max(0, wait_time)

            # Check hour limit
            if len(self.call_history_hour) >= self.max_calls_per_hour:
                # Calculate when next slot becomes available
                oldest_call = self.call_history_hour[0]
                wait_time = 3600 - (now - oldest_call)
                return False, max(0, wait_time)

            return True, 0

    def record_call(self):
        """Record that an API call was made"""
        with self.lock:
            now = time.time()
            self.call_history_minute.append(now)
            self.call_history_hour.append(now)
            self.total_calls += 1

    def wait_if_needed(self, timeout=60) -> bool:
        """
        Wait if rate limit is hit, returns True if can proceed

        Args:
            timeout: Maximum time to wait in seconds

        Returns:
            True if can proceed, False if timeout exceeded
        """
        start_time = time.time()

        while True:
            can_proceed, wait_time = self.can_make_request()

            if can_proceed:
                self.record_call()
                return True

            # Check timeout
            if time.time() - start_time > timeout:
                with self.lock:
                    self.total_blocked += 1
                return False

            # Wait a bit
            sleep_time = min(wait_time, 1.0)
            if sleep_time > 0:
                with self.lock:
                    self.total_delayed += 1
                print(f"⏱️  Rate limit: waiting {sleep_time:.1f}s (quota: {len(self.call_history_minute)}/{self.max_calls_per_minute}/min)")
                time.sleep(sleep_time)

    def get_stats(self) -> dict:
        """Get rate limiter statistics"""
        with self.lock:
            now = time.time()

            # Count recent calls
            calls_last_minute = sum(1 for t in self.call_history_minute if now - t <= 60)
            calls_last_hour = sum(1 for t in self.call_history_hour if now - t <= 3600)

            return {
                'calls_last_minute': calls_last_minute,
                'calls_last_hour': calls_last_hour,
                'max_calls_per_minute': self.max_calls_per_minute,
                'max_calls_per_hour': self.max_calls_per_hour,
                'remaining_minute': max(0, self.max_calls_per_minute - calls_last_minute),
                'remaining_hour': max(0, self.max_calls_per_hour - calls_last_hour),
                'total_calls': self.total_calls,
                'total_blocked': self.total_blocked,
                'total_delayed': self.total_delayed,
                'utilization_minute': calls_last_minute / self.max_calls_per_minute * 100,
                'utilization_hour': calls_last_hour / self.max_calls_per_hour * 100
            }

    def reset(self):
        """Reset rate limiter (for testing)"""
        with self.lock:
            self.call_history_minute.clear()
            self.call_history_hour.clear()
            self.total_calls = 0
            self.total_blocked = 0
            self.total_delayed = 0


# Global rate limiter instance
# Set to 15/min for safety (Trading Volatility is 20/min, but we want margin)
trading_volatility_limiter = RateLimiter(
    max_calls_per_minute=15,  # 75% of 20/min quota
    max_calls_per_hour=800     # Safety limit
)


# Decorator for rate-limited functions
def rate_limited(limiter=trading_volatility_limiter, timeout=60):
    """
    Decorator to rate limit a function

    Usage:
        @rate_limited(limiter=trading_volatility_limiter, timeout=30)
        def fetch_gex_data(symbol):
            # Your API call here
            pass
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            # Wait if needed
            if not limiter.wait_if_needed(timeout=timeout):
                raise Exception(f"Rate limit timeout exceeded ({timeout}s)")

            # Call function
            return func(*args, **kwargs)

        return wrapper
    return decorator


# Example usage
if __name__ == '__main__':
    # Test rate limiter
    limiter = RateLimiter(max_calls_per_minute=5)  # Low limit for testing

    print("Testing rate limiter with 5 calls/minute limit...")
    print("=" * 60)

    for i in range(10):
        print(f"\nRequest #{i+1}:")
        can_proceed, wait_time = limiter.can_make_request()

        if can_proceed:
            limiter.record_call()
            print(f"  ✅ Allowed")
        else:
            print(f"  ⏱️  Rate limited - would wait {wait_time:.1f}s")

        # Show stats
        stats = limiter.get_stats()
        print(f"  Stats: {stats['calls_last_minute']}/{stats['max_calls_per_minute']} calls/min")

        time.sleep(0.5)  # Small delay between tests

    print("\n" + "=" * 60)
    print("Final stats:")
    print(limiter.get_stats())
