"""
Centralized Rate Limiter for AlphaGEX
Prevents API overuse across all deployments

AUTO-DETECTS WEEKEND VS WEEKDAY:
- Weekend (Sat/Sun): 2 calls/minute (market closed, strict limits)
- Weekday trading hours (9:30am-4pm ET): 2 calls/minute (realtime data)
- Weekday non-trading hours: 18 calls/minute (safety margin from 20/min limit)
"""

import time
import threading
from collections import deque
from datetime import datetime, timedelta
import pytz

class RateLimiter:
    """
    Thread-safe rate limiter with automatic weekend/weekday detection
    Dynamically adjusts limits based on current time and market hours
    """

    def __init__(self, max_calls_per_minute=None, max_calls_per_hour=800, dynamic_limits=True):
        """
        Initialize rate limiter with dynamic weekend/weekday detection

        Args:
            max_calls_per_minute: Maximum API calls per minute (if None, auto-detected)
            max_calls_per_hour: Maximum API calls per hour (default: 800)
            dynamic_limits: If True, automatically adjust limits based on weekend/weekday
        """
        self.dynamic_limits = dynamic_limits
        self.max_calls_per_hour = max_calls_per_hour

        # Static limit if provided
        self.static_max_calls_per_minute = max_calls_per_minute

        # Track call timestamps (use larger maxlen for dynamic limits)
        self.call_history_minute = deque(maxlen=100)
        self.call_history_hour = deque(maxlen=max_calls_per_hour * 2)

        # Thread lock for safety
        self.lock = threading.Lock()

        # Statistics
        self.total_calls = 0
        self.total_blocked = 0
        self.total_delayed = 0

        # Trading hours timezone
        self.et_tz = pytz.timezone('America/New_York')

    def _get_current_limit(self) -> int:
        """
        Get current rate limit based on day of week and trading hours

        Trading Volatility API Limits (Stocks+ Subscriber):
        - Weekend (Sat/Sun): 2 calls/minute
        - Weekday trading hours (9:30am-4pm ET): 2 calls/minute (realtime data)
        - Weekday non-trading hours: 20 calls/minute (non-realtime data)

        Returns:
            Current maximum calls per minute
        """
        # If dynamic limits disabled, use static value
        if not self.dynamic_limits:
            return self.static_max_calls_per_minute or 15

        # Get current time in Eastern Time
        now_et = datetime.now(self.et_tz)
        day_of_week = now_et.weekday()  # 0 = Monday, 6 = Sunday
        current_hour = now_et.hour
        current_minute = now_et.minute

        # Weekend (Saturday=5, Sunday=6): Strict 2 calls/minute limit
        if day_of_week >= 5:
            return 2

        # Weekday: Check if within trading hours (9:30 AM - 4:00 PM ET)
        # Trading hours use realtime data endpoint (2 calls/minute limit)
        market_open_minutes = 9 * 60 + 30  # 9:30 AM
        market_close_minutes = 16 * 60     # 4:00 PM
        current_minutes = current_hour * 60 + current_minute

        if market_open_minutes <= current_minutes < market_close_minutes:
            # During trading hours: 2 calls/minute (realtime data)
            return 2
        else:
            # Outside trading hours: 18 calls/minute (safety margin from 20/min)
            return 18

    @property
    def max_calls_per_minute(self) -> int:
        """Current maximum calls per minute (dynamic based on time)"""
        return self._get_current_limit()

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

                # Get current limit and show day context
                current_limit = self.max_calls_per_minute
                now_et = datetime.now(self.et_tz)
                day_name = now_et.strftime("%A")
                is_weekend = now_et.weekday() >= 5

                if is_weekend:
                    context = f"{day_name} (WEEKEND - 2/min limit)"
                else:
                    context = f"{day_name} ({current_limit}/min limit)"

                print(f"⏱️  Rate limit: waiting {sleep_time:.1f}s | {len(self.call_history_minute)}/{current_limit} calls/min | {context}")
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
                'utilization_minute': (calls_last_minute / self.max_calls_per_minute * 100) if self.max_calls_per_minute > 0 else 0,
                'utilization_hour': (calls_last_hour / self.max_calls_per_hour * 100) if self.max_calls_per_hour > 0 else 0
            }

    def reset(self):
        """Reset rate limiter (for testing)"""
        with self.lock:
            self.call_history_minute.clear()
            self.call_history_hour.clear()
            self.total_calls = 0
            self.total_blocked = 0
            self.total_delayed = 0


# Global rate limiter instance with DYNAMIC limits
# Automatically detects weekend vs weekday and trading hours:
# - Weekend: 2 calls/minute
# - Weekday trading hours (9:30am-4pm ET): 2 calls/minute
# - Weekday non-trading hours: 18 calls/minute
trading_volatility_limiter = RateLimiter(
    dynamic_limits=True,       # Enable auto-detection
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
