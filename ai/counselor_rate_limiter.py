"""
COUNSELOR Rate Limiter - Protect API from abuse and control costs.

Provides:
- Per-user rate limiting
- Per-endpoint rate limiting
- Token bucket algorithm
- Request throttling
"""

import time
import threading
import logging
from typing import Dict, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


@dataclass
class RateLimitConfig:
    """Configuration for a rate limit."""
    requests_per_minute: int
    requests_per_hour: int
    burst_size: int = 10  # Allow short bursts


class TokenBucket:
    """
    Token bucket rate limiter implementation.

    Allows for burst traffic while enforcing long-term rate limits.
    """

    def __init__(
        self,
        rate: float,  # tokens per second
        capacity: int  # maximum tokens (burst size)
    ):
        """
        Initialize token bucket.

        Args:
            rate: Token refill rate (tokens per second)
            capacity: Maximum tokens in bucket
        """
        self.rate = rate
        self.capacity = capacity
        self.tokens = capacity
        self.last_update = time.time()
        self._lock = threading.Lock()

    def _refill(self) -> None:
        """Refill tokens based on elapsed time."""
        now = time.time()
        elapsed = now - self.last_update
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
        self.last_update = now

    def consume(self, tokens: int = 1) -> Tuple[bool, float]:
        """
        Try to consume tokens from the bucket.

        Args:
            tokens: Number of tokens to consume

        Returns:
            Tuple of (allowed, wait_time_seconds)
        """
        with self._lock:
            self._refill()

            if self.tokens >= tokens:
                self.tokens -= tokens
                return True, 0.0
            else:
                # Calculate wait time
                needed = tokens - self.tokens
                wait_time = needed / self.rate
                return False, wait_time

    @property
    def available_tokens(self) -> float:
        """Get current available tokens."""
        with self._lock:
            self._refill()
            return self.tokens


class GEXISRateLimiter:
    """
    Rate limiter for COUNSELOR API requests.

    Supports:
    - Per-user limits
    - Per-endpoint limits
    - Global limits
    - Burst allowance
    """

    # Default limits
    DEFAULT_CONFIG = RateLimitConfig(
        requests_per_minute=30,
        requests_per_hour=500,
        burst_size=10
    )

    # Endpoint-specific limits
    ENDPOINT_LIMITS = {
        "/analyze": RateLimitConfig(requests_per_minute=20, requests_per_hour=200, burst_size=5),
        "/briefing": RateLimitConfig(requests_per_minute=10, requests_per_hour=60, burst_size=3),
        "/command": RateLimitConfig(requests_per_minute=60, requests_per_hour=600, burst_size=15),
        "/suggestion": RateLimitConfig(requests_per_minute=15, requests_per_hour=100, burst_size=5),
    }

    def __init__(self):
        """Initialize the rate limiter."""
        self._user_buckets: Dict[str, Dict[str, TokenBucket]] = {}
        self._global_bucket = TokenBucket(
            rate=100 / 60,  # 100 requests per minute globally
            capacity=50
        )
        self._lock = threading.RLock()
        self._stats = {
            'total_requests': 0,
            'allowed_requests': 0,
            'denied_requests': 0,
            'by_endpoint': {}
        }

    def _get_user_bucket(self, user_id: str, endpoint: str) -> TokenBucket:
        """Get or create a token bucket for a user/endpoint combination."""
        with self._lock:
            if user_id not in self._user_buckets:
                self._user_buckets[user_id] = {}

            if endpoint not in self._user_buckets[user_id]:
                config = self.ENDPOINT_LIMITS.get(endpoint, self.DEFAULT_CONFIG)
                self._user_buckets[user_id][endpoint] = TokenBucket(
                    rate=config.requests_per_minute / 60,  # Convert to per-second
                    capacity=config.burst_size
                )

            return self._user_buckets[user_id][endpoint]

    def check_rate_limit(
        self,
        user_id: str,
        endpoint: str,
        tokens: int = 1
    ) -> Tuple[bool, Optional[float], str]:
        """
        Check if a request is allowed under rate limits.

        Args:
            user_id: User identifier (IP, session ID, etc.)
            endpoint: API endpoint being accessed
            tokens: Number of tokens to consume

        Returns:
            Tuple of (allowed, retry_after_seconds, reason)
        """
        with self._lock:
            self._stats['total_requests'] += 1

            if endpoint not in self._stats['by_endpoint']:
                self._stats['by_endpoint'][endpoint] = {'allowed': 0, 'denied': 0}

            # Check global limit first
            global_allowed, global_wait = self._global_bucket.consume(tokens)
            if not global_allowed:
                self._stats['denied_requests'] += 1
                self._stats['by_endpoint'][endpoint]['denied'] += 1
                logger.warning(
                    f"Rate limit hit: global limit for {endpoint}",
                    extra={'context': {'user_id': user_id, 'endpoint': endpoint}}
                )
                return False, global_wait, "Global rate limit exceeded"

            # Check user-specific limit
            user_bucket = self._get_user_bucket(user_id, endpoint)
            user_allowed, user_wait = user_bucket.consume(tokens)

            if not user_allowed:
                self._stats['denied_requests'] += 1
                self._stats['by_endpoint'][endpoint]['denied'] += 1
                logger.warning(
                    f"Rate limit hit: user limit for {user_id} on {endpoint}",
                    extra={'context': {'user_id': user_id, 'endpoint': endpoint}}
                )
                return False, user_wait, "User rate limit exceeded"

            # Request allowed
            self._stats['allowed_requests'] += 1
            self._stats['by_endpoint'][endpoint]['allowed'] += 1
            return True, None, "OK"

    def get_user_limits(self, user_id: str, endpoint: str) -> Dict:
        """
        Get current limit status for a user/endpoint.

        Args:
            user_id: User identifier
            endpoint: API endpoint

        Returns:
            Dictionary with limit information
        """
        config = self.ENDPOINT_LIMITS.get(endpoint, self.DEFAULT_CONFIG)
        bucket = self._get_user_bucket(user_id, endpoint)

        return {
            'endpoint': endpoint,
            'limit_per_minute': config.requests_per_minute,
            'limit_per_hour': config.requests_per_hour,
            'burst_size': config.burst_size,
            'available_tokens': round(bucket.available_tokens, 2),
            'refill_rate_per_second': round(bucket.rate, 4)
        }

    def get_stats(self) -> Dict:
        """Get rate limiter statistics."""
        with self._lock:
            return {
                'total_requests': self._stats['total_requests'],
                'allowed_requests': self._stats['allowed_requests'],
                'denied_requests': self._stats['denied_requests'],
                'denial_rate_pct': round(
                    self._stats['denied_requests'] / self._stats['total_requests'] * 100, 2
                ) if self._stats['total_requests'] > 0 else 0,
                'by_endpoint': dict(self._stats['by_endpoint']),
                'active_users': len(self._user_buckets),
                'global_tokens_available': round(self._global_bucket.available_tokens, 2)
            }

    def reset_user(self, user_id: str) -> bool:
        """
        Reset rate limits for a specific user.

        Args:
            user_id: User identifier

        Returns:
            True if user was found and reset
        """
        with self._lock:
            if user_id in self._user_buckets:
                del self._user_buckets[user_id]
                return True
            return False

    def cleanup_inactive(self, max_age_seconds: int = 3600) -> int:
        """
        Clean up inactive user buckets.

        Args:
            max_age_seconds: Maximum age before cleanup

        Returns:
            Number of users cleaned up
        """
        with self._lock:
            now = time.time()
            to_remove = []

            for user_id, buckets in self._user_buckets.items():
                # Check if all buckets are old
                all_old = all(
                    now - bucket.last_update > max_age_seconds
                    for bucket in buckets.values()
                )
                if all_old:
                    to_remove.append(user_id)

            for user_id in to_remove:
                del self._user_buckets[user_id]

            if to_remove:
                logger.info(f"Cleaned up {len(to_remove)} inactive rate limit users")

            return len(to_remove)


# Global rate limiter instance
counselor_rate_limiter = GEXISRateLimiter()


# =============================================================================
# DECORATOR FOR EASY RATE LIMITING
# =============================================================================

def rate_limited(endpoint: str):
    """
    Decorator for rate limiting API endpoints.

    Args:
        endpoint: Endpoint name for rate limiting

    Usage:
        @rate_limited("/analyze")
        async def analyze_market(request):
            ...
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            # Extract user_id from request (simplified)
            request = kwargs.get('request') or (args[0] if args else None)
            user_id = "default"

            if request:
                # Try to get user ID from request
                if hasattr(request, 'client') and request.client:
                    user_id = request.client.host
                elif hasattr(request, 'get'):
                    user_id = request.get('session_id', 'default')

            # Check rate limit
            allowed, retry_after, reason = counselor_rate_limiter.check_rate_limit(
                user_id, endpoint
            )

            if not allowed:
                from fastapi import HTTPException
                raise HTTPException(
                    status_code=429,
                    detail={
                        "error": "Rate limit exceeded",
                        "reason": reason,
                        "retry_after_seconds": retry_after
                    },
                    headers={"Retry-After": str(int(retry_after or 60))}
                )

            return await func(*args, **kwargs)

        wrapper.__name__ = func.__name__
        wrapper.__doc__ = func.__doc__
        return wrapper
    return decorator
