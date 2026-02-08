"""
COUNSELOR Caching Layer - High-performance caching for COUNSELOR operations.

Provides TTL-based caching for:
- Market data (60 second TTL)
- Positions (30 second TTL)
- Bot status (60 second TTL)
- System status (30 second TTL)

Features:
- Thread-safe operations
- Automatic TTL expiration
- Cache statistics and monitoring
- Manual invalidation support
"""

import time
import threading
import logging
from typing import Any, Dict, Optional, Callable, TypeVar
from functools import wraps
from dataclasses import dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

T = TypeVar('T')

# Sentinel value to distinguish "not in cache" from "cached None"
_CACHE_MISS = object()


@dataclass
class CacheEntry:
    """A single cache entry with value and metadata."""
    value: Any
    created_at: float
    ttl_seconds: float
    hit_count: int = 0

    @property
    def is_expired(self) -> bool:
        """Check if this entry has expired."""
        return time.time() - self.created_at > self.ttl_seconds

    @property
    def age_seconds(self) -> float:
        """Get the age of this entry in seconds."""
        return time.time() - self.created_at

    @property
    def remaining_ttl(self) -> float:
        """Get remaining TTL in seconds (negative if expired)."""
        return self.ttl_seconds - self.age_seconds


class GEXISCache:
    """
    Thread-safe TTL cache for COUNSELOR operations.

    Usage:
        cache = GEXISCache()

        # Store with TTL
        cache.set("market_data_SPY", data, ttl=60)

        # Retrieve
        data = cache.get("market_data_SPY")

        # Use decorator
        @cache.cached(ttl=60, key_prefix="market")
        def get_market_data(symbol: str):
            return fetch_from_api(symbol)
    """

    # Default TTLs for different data types
    TTL_MARKET_DATA = 60      # Market data: 60 seconds
    TTL_POSITIONS = 30        # Positions: 30 seconds
    TTL_BOT_STATUS = 60       # Bot status: 60 seconds
    TTL_SYSTEM_STATUS = 30    # System status: 30 seconds
    TTL_GEX_DATA = 45         # GEX data: 45 seconds
    TTL_BRIEFING = 300        # Briefing: 5 minutes

    def __init__(self, max_entries: int = 1000):
        """
        Initialize the cache.

        Args:
            max_entries: Maximum number of cache entries before cleanup
        """
        self._cache: Dict[str, CacheEntry] = {}
        self._lock = threading.RLock()
        self._max_entries = max_entries
        self._stats = {
            'hits': 0,
            'misses': 0,
            'sets': 0,
            'evictions': 0,
            'expirations': 0
        }
        self._created_at = datetime.now(timezone.utc)

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a value from the cache.

        Args:
            key: Cache key
            default: Value to return if key not found/expired

        Returns:
            Cached value or default if not found/expired
        """
        with self._lock:
            entry = self._cache.get(key)

            if entry is None:
                self._stats['misses'] += 1
                return default

            if entry.is_expired:
                del self._cache[key]
                self._stats['misses'] += 1
                self._stats['expirations'] += 1
                logger.debug(f"Cache expired: {key}")
                return default

            entry.hit_count += 1
            self._stats['hits'] += 1
            logger.debug(f"Cache hit: {key} (age: {entry.age_seconds:.1f}s)")
            return entry.value

    def set(self, key: str, value: Any, ttl: float = 60) -> None:
        """
        Set a value in the cache.

        Args:
            key: Cache key
            value: Value to cache
            ttl: Time-to-live in seconds
        """
        with self._lock:
            # Cleanup if we're at capacity
            if len(self._cache) >= self._max_entries:
                self._cleanup_expired()

            self._cache[key] = CacheEntry(
                value=value,
                created_at=time.time(),
                ttl_seconds=ttl
            )
            self._stats['sets'] += 1
            logger.debug(f"Cache set: {key} (ttl: {ttl}s)")

    def delete(self, key: str) -> bool:
        """
        Delete a key from the cache.

        Args:
            key: Cache key to delete

        Returns:
            True if key was deleted, False if not found
        """
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    def invalidate_prefix(self, prefix: str) -> int:
        """
        Invalidate all keys with a given prefix.

        Args:
            prefix: Key prefix to invalidate

        Returns:
            Number of keys invalidated
        """
        with self._lock:
            keys_to_delete = [k for k in self._cache.keys() if k.startswith(prefix)]
            for key in keys_to_delete:
                del self._cache[key]
            logger.info(f"Invalidated {len(keys_to_delete)} keys with prefix: {prefix}")
            return len(keys_to_delete)

    def clear(self) -> int:
        """
        Clear all cache entries.

        Returns:
            Number of entries cleared
        """
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            logger.info(f"Cache cleared: {count} entries")
            return count

    def get_or_set(
        self,
        key: str,
        factory: Callable[[], T],
        ttl: float = 60
    ) -> T:
        """
        Get a value from cache, or compute and cache it if not present.

        Args:
            key: Cache key
            factory: Function to call if key is not in cache
            ttl: Time-to-live in seconds

        Returns:
            Cached or computed value (may be None if factory returns None)
        """
        # Use sentinel to distinguish cache miss from cached None
        value = self.get(key, default=_CACHE_MISS)
        if value is not _CACHE_MISS:
            return value

        result = factory()
        self.set(key, result, ttl)
        return result

    def cached(
        self,
        ttl: float = 60,
        key_prefix: str = "",
        key_func: Optional[Callable[..., str]] = None
    ):
        """
        Decorator to cache function results.

        Args:
            ttl: Time-to-live in seconds
            key_prefix: Prefix for cache keys
            key_func: Custom function to generate cache key from args

        Usage:
            @cache.cached(ttl=60, key_prefix="market")
            def get_market_data(symbol: str):
                return fetch_from_api(symbol)
        """
        def decorator(func: Callable[..., T]) -> Callable[..., T]:
            @wraps(func)
            def wrapper(*args, **kwargs) -> T:
                # Generate cache key
                if key_func:
                    cache_key = key_func(*args, **kwargs)
                else:
                    # Default key: prefix:func_name:args:kwargs
                    arg_str = ':'.join(str(a) for a in args)
                    kwarg_str = ':'.join(f"{k}={v}" for k, v in sorted(kwargs.items()))
                    parts = [key_prefix, func.__name__, arg_str, kwarg_str]
                    cache_key = ':'.join(p for p in parts if p)

                # Try to get from cache (use sentinel to handle cached None)
                cached_value = self.get(cache_key, default=_CACHE_MISS)
                if cached_value is not _CACHE_MISS:
                    return cached_value

                # Compute and cache
                result = func(*args, **kwargs)
                self.set(cache_key, result, ttl)
                return result

            # Add cache control methods to the wrapper
            wrapper.cache_clear = lambda: self.invalidate_prefix(f"{key_prefix}:{func.__name__}")
            wrapper.cache_info = lambda: self.get_stats()

            return wrapper
        return decorator

    def _cleanup_expired(self) -> int:
        """
        Remove expired entries from the cache.

        Returns:
            Number of entries removed
        """
        with self._lock:
            expired_keys = [
                key for key, entry in self._cache.items()
                if entry.is_expired
            ]
            for key in expired_keys:
                del self._cache[key]
                self._stats['evictions'] += 1

            if expired_keys:
                logger.debug(f"Cleaned up {len(expired_keys)} expired entries")

            return len(expired_keys)

    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache stats
        """
        with self._lock:
            total_requests = self._stats['hits'] + self._stats['misses']
            hit_rate = (self._stats['hits'] / total_requests * 100) if total_requests > 0 else 0

            return {
                'entries': len(self._cache),
                'max_entries': self._max_entries,
                'hits': self._stats['hits'],
                'misses': self._stats['misses'],
                'hit_rate_pct': round(hit_rate, 2),
                'sets': self._stats['sets'],
                'evictions': self._stats['evictions'],
                'expirations': self._stats['expirations'],
                'uptime_seconds': (datetime.now(timezone.utc) - self._created_at).total_seconds()
            }

    def get_entry_info(self, key: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed info about a cache entry.

        Args:
            key: Cache key

        Returns:
            Entry info or None if not found
        """
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None

            return {
                'key': key,
                'age_seconds': round(entry.age_seconds, 2),
                'ttl_seconds': entry.ttl_seconds,
                'remaining_ttl': round(entry.remaining_ttl, 2),
                'hit_count': entry.hit_count,
                'is_expired': entry.is_expired,
                'value_type': type(entry.value).__name__
            }


# Global cache instance
counselor_cache = GEXISCache()


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def cache_market_data(symbol: str, data: Dict) -> None:
    """Cache market data for a symbol."""
    counselor_cache.set(f"market:{symbol}", data, ttl=GEXISCache.TTL_MARKET_DATA)


def get_cached_market_data(symbol: str) -> Optional[Dict]:
    """Get cached market data for a symbol."""
    return counselor_cache.get(f"market:{symbol}")


def cache_gex_data(symbol: str, data: Dict) -> None:
    """Cache GEX data for a symbol."""
    counselor_cache.set(f"gex:{symbol}", data, ttl=GEXISCache.TTL_GEX_DATA)


def get_cached_gex_data(symbol: str) -> Optional[Dict]:
    """Get cached GEX data for a symbol."""
    return counselor_cache.get(f"gex:{symbol}")


def cache_bot_status(bot_name: str, status: Dict) -> None:
    """Cache bot status."""
    counselor_cache.set(f"bot:{bot_name}", status, ttl=GEXISCache.TTL_BOT_STATUS)


def get_cached_bot_status(bot_name: str) -> Optional[Dict]:
    """Get cached bot status."""
    return counselor_cache.get(f"bot:{bot_name}")


def cache_positions(positions: list) -> None:
    """Cache positions list."""
    counselor_cache.set("positions:all", positions, ttl=GEXISCache.TTL_POSITIONS)


def get_cached_positions() -> Optional[list]:
    """Get cached positions."""
    return counselor_cache.get("positions:all")


def invalidate_positions_cache() -> None:
    """Invalidate positions cache (call after trade execution)."""
    counselor_cache.invalidate_prefix("positions:")


def invalidate_bot_cache(bot_name: Optional[str] = None) -> None:
    """Invalidate bot cache (call after bot control action)."""
    if bot_name:
        counselor_cache.delete(f"bot:{bot_name}")
    else:
        counselor_cache.invalidate_prefix("bot:")
