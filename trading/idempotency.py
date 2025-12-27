"""
Idempotency Keys for Trade Order Submissions

Prevents duplicate order submissions by tracking unique request identifiers.
Essential for production safety when network issues could cause retries.

Features:
- Unique key generation per trade request
- Database-backed persistence for multi-instance deployments
- In-memory cache for fast lookups
- Automatic cleanup of expired keys
- Integration with ARES and ATHENA order flows

Usage:
    from trading.idempotency import (
        IdempotencyManager,
        get_idempotency_manager,
        generate_idempotency_key
    )

    # Before placing order
    key = generate_idempotency_key("ARES", position_id, expiration)

    # Check if already processed
    existing = manager.get_result(key)
    if existing:
        return existing  # Return cached result

    # Place order
    result = execute_order(...)

    # Store result
    manager.store_result(key, result)
"""

import hashlib
import logging
import secrets
import threading
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

CENTRAL_TZ = ZoneInfo("America/Chicago")


class IdempotencyStatus(Enum):
    """Status of an idempotency key"""
    PENDING = "pending"        # Request in progress
    COMPLETED = "completed"    # Request completed successfully
    FAILED = "failed"          # Request failed
    EXPIRED = "expired"        # Key expired (can be reused)


@dataclass
class IdempotencyRecord:
    """Record for an idempotency key"""
    key: str
    status: IdempotencyStatus
    created_at: datetime
    expires_at: datetime
    bot_name: str
    request_hash: str
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class IdempotencyManager:
    """
    Manages idempotency keys for preventing duplicate order submissions.

    Uses both in-memory cache and database persistence for reliability.
    """

    # Default TTL for keys (24 hours)
    DEFAULT_TTL_HOURS = 24

    # Maximum in-memory cache size
    MAX_CACHE_SIZE = 1000

    def __init__(self, use_database: bool = True):
        """
        Initialize the idempotency manager.

        Args:
            use_database: Whether to persist keys to database
        """
        self._cache: Dict[str, IdempotencyRecord] = {}
        self._cache_lock = threading.Lock()
        self._use_database = use_database
        self._db_available = False

        if use_database:
            self._init_database()

        logger.info(f"IdempotencyManager initialized (db: {self._db_available})")

    def _init_database(self) -> None:
        """Initialize database table for idempotency keys."""
        try:
            from database_adapter import get_connection

            conn = get_connection()
            cursor = conn.cursor()

            # Create table if not exists
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS idempotency_keys (
                    key VARCHAR(128) PRIMARY KEY,
                    status VARCHAR(20) NOT NULL,
                    created_at TIMESTAMP NOT NULL,
                    expires_at TIMESTAMP NOT NULL,
                    bot_name VARCHAR(50),
                    request_hash VARCHAR(64),
                    result JSONB,
                    error TEXT,
                    updated_at TIMESTAMP DEFAULT NOW()
                );

                CREATE INDEX IF NOT EXISTS idx_idempotency_expires
                ON idempotency_keys(expires_at);

                CREATE INDEX IF NOT EXISTS idx_idempotency_bot
                ON idempotency_keys(bot_name, created_at DESC);
            """)

            conn.commit()
            conn.close()
            self._db_available = True

        except Exception as e:
            logger.warning(f"Could not initialize idempotency database: {e}")
            self._db_available = False

    def generate_key(
        self,
        bot_name: str,
        *components: Any
    ) -> str:
        """
        Generate a unique idempotency key.

        Args:
            bot_name: Name of the bot (ARES, ATHENA)
            *components: Additional components to include in key
                        (e.g., position_id, expiration, strikes)

        Returns:
            Unique idempotency key string
        """
        # Build key components
        parts = [
            bot_name,
            datetime.now(CENTRAL_TZ).strftime('%Y%m%d'),
            *[str(c) for c in components if c is not None]
        ]

        # Create hash from components
        content = "|".join(parts)
        hash_value = hashlib.sha256(content.encode()).hexdigest()[:16]

        # Add random suffix for uniqueness
        random_suffix = secrets.token_hex(4)

        key = f"{bot_name}_{hash_value}_{random_suffix}"
        return key

    def create_request_hash(self, request_data: Dict[str, Any]) -> str:
        """
        Create a hash of the request data for detecting duplicate requests.

        Args:
            request_data: Dictionary of request parameters

        Returns:
            SHA256 hash of the request data
        """
        # Sort keys for consistent hashing
        sorted_data = sorted(request_data.items())
        content = str(sorted_data)
        return hashlib.sha256(content.encode()).hexdigest()

    def check_key(self, key: str) -> Tuple[bool, Optional[IdempotencyRecord]]:
        """
        Check if an idempotency key has been used.

        Args:
            key: The idempotency key to check

        Returns:
            Tuple of (key_exists, record_if_exists)
        """
        # Check cache first
        with self._cache_lock:
            if key in self._cache:
                record = self._cache[key]
                if datetime.now(CENTRAL_TZ) < record.expires_at:
                    return True, record
                else:
                    # Key expired, remove from cache
                    del self._cache[key]

        # Check database
        if self._db_available:
            record = self._load_from_db(key)
            if record:
                # Add to cache
                with self._cache_lock:
                    self._cache[key] = record
                return True, record

        return False, None

    def mark_pending(
        self,
        key: str,
        bot_name: str,
        request_hash: str,
        ttl_hours: int = DEFAULT_TTL_HOURS
    ) -> bool:
        """
        Mark a key as pending (request in progress).

        Args:
            key: The idempotency key
            bot_name: Name of the bot
            request_hash: Hash of the request data
            ttl_hours: Time-to-live in hours

        Returns:
            True if key was marked pending, False if already exists
        """
        exists, _ = self.check_key(key)
        if exists:
            return False

        now = datetime.now(CENTRAL_TZ)
        record = IdempotencyRecord(
            key=key,
            status=IdempotencyStatus.PENDING,
            created_at=now,
            expires_at=now + timedelta(hours=ttl_hours),
            bot_name=bot_name,
            request_hash=request_hash
        )

        # Store in cache
        with self._cache_lock:
            self._cleanup_cache()
            self._cache[key] = record

        # Store in database
        if self._db_available:
            self._save_to_db(record)

        return True

    def mark_completed(
        self,
        key: str,
        result: Dict[str, Any]
    ) -> bool:
        """
        Mark a key as completed with result.

        Args:
            key: The idempotency key
            result: The result of the operation

        Returns:
            True if successfully marked
        """
        with self._cache_lock:
            if key in self._cache:
                record = self._cache[key]
                record.status = IdempotencyStatus.COMPLETED
                record.result = result

        if self._db_available:
            self._update_status_in_db(key, IdempotencyStatus.COMPLETED, result=result)

        logger.debug(f"Idempotency key {key} marked COMPLETED")
        return True

    def mark_failed(
        self,
        key: str,
        error: str
    ) -> bool:
        """
        Mark a key as failed with error.

        Args:
            key: The idempotency key
            error: Error message

        Returns:
            True if successfully marked
        """
        with self._cache_lock:
            if key in self._cache:
                record = self._cache[key]
                record.status = IdempotencyStatus.FAILED
                record.error = error

        if self._db_available:
            self._update_status_in_db(key, IdempotencyStatus.FAILED, error=error)

        logger.debug(f"Idempotency key {key} marked FAILED: {error}")
        return True

    def get_result(self, key: str) -> Optional[Dict[str, Any]]:
        """
        Get the result for a completed key.

        Args:
            key: The idempotency key

        Returns:
            Result dictionary if completed, None otherwise
        """
        exists, record = self.check_key(key)

        if exists and record.status == IdempotencyStatus.COMPLETED:
            return record.result

        return None

    def _cleanup_cache(self) -> None:
        """Remove expired entries from cache. Must be called with lock held."""
        now = datetime.now(CENTRAL_TZ)

        # Remove expired
        expired = [k for k, v in self._cache.items() if v.expires_at < now]
        for k in expired:
            del self._cache[k]

        # Enforce max size
        if len(self._cache) > self.MAX_CACHE_SIZE:
            # Remove oldest entries
            sorted_items = sorted(
                self._cache.items(),
                key=lambda x: x[1].created_at
            )
            for k, _ in sorted_items[:len(self._cache) - self.MAX_CACHE_SIZE]:
                del self._cache[k]

    def _load_from_db(self, key: str) -> Optional[IdempotencyRecord]:
        """Load a record from database."""
        try:
            from database_adapter import get_connection
            import json

            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute("""
                SELECT key, status, created_at, expires_at, bot_name,
                       request_hash, result, error
                FROM idempotency_keys
                WHERE key = %s AND expires_at > NOW()
            """, (key,))

            row = cursor.fetchone()
            conn.close()

            if row:
                return IdempotencyRecord(
                    key=row[0],
                    status=IdempotencyStatus(row[1]),
                    created_at=row[2].replace(tzinfo=CENTRAL_TZ) if row[2] else datetime.now(CENTRAL_TZ),
                    expires_at=row[3].replace(tzinfo=CENTRAL_TZ) if row[3] else datetime.now(CENTRAL_TZ),
                    bot_name=row[4],
                    request_hash=row[5],
                    result=row[6] if row[6] else None,
                    error=row[7]
                )

        except Exception as e:
            logger.debug(f"Error loading idempotency key from DB: {e}")

        return None

    def _save_to_db(self, record: IdempotencyRecord) -> None:
        """Save a record to database."""
        try:
            from database_adapter import get_connection
            import json

            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO idempotency_keys
                    (key, status, created_at, expires_at, bot_name, request_hash, result, error)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (key) DO UPDATE SET
                    status = EXCLUDED.status,
                    result = EXCLUDED.result,
                    error = EXCLUDED.error,
                    updated_at = NOW()
            """, (
                record.key,
                record.status.value,
                record.created_at,
                record.expires_at,
                record.bot_name,
                record.request_hash,
                json.dumps(record.result) if record.result else None,
                record.error
            ))

            conn.commit()
            conn.close()

        except Exception as e:
            logger.warning(f"Error saving idempotency key to DB: {e}")

    def _update_status_in_db(
        self,
        key: str,
        status: IdempotencyStatus,
        result: Optional[Dict] = None,
        error: Optional[str] = None
    ) -> None:
        """Update status in database."""
        try:
            from database_adapter import get_connection
            import json

            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute("""
                UPDATE idempotency_keys
                SET status = %s,
                    result = %s,
                    error = %s,
                    updated_at = NOW()
                WHERE key = %s
            """, (
                status.value,
                json.dumps(result) if result else None,
                error,
                key
            ))

            conn.commit()
            conn.close()

        except Exception as e:
            logger.debug(f"Error updating idempotency key in DB: {e}")

    def cleanup_expired(self) -> int:
        """
        Clean up expired keys from database.

        Returns:
            Number of keys removed
        """
        if not self._db_available:
            return 0

        try:
            from database_adapter import get_connection

            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute("""
                DELETE FROM idempotency_keys
                WHERE expires_at < NOW()
            """)

            deleted = cursor.rowcount
            conn.commit()
            conn.close()

            logger.info(f"Cleaned up {deleted} expired idempotency keys")
            return deleted

        except Exception as e:
            logger.warning(f"Error cleaning up idempotency keys: {e}")
            return 0


# =============================================================================
# Singleton Instance
# =============================================================================

_idempotency_manager: Optional[IdempotencyManager] = None
_manager_lock = threading.Lock()


def get_idempotency_manager() -> IdempotencyManager:
    """Get the singleton idempotency manager instance."""
    global _idempotency_manager

    with _manager_lock:
        if _idempotency_manager is None:
            _idempotency_manager = IdempotencyManager()

    return _idempotency_manager


# =============================================================================
# Convenience Functions
# =============================================================================

def generate_idempotency_key(
    bot_name: str,
    position_id: Optional[str] = None,
    expiration: Optional[str] = None,
    **kwargs
) -> str:
    """
    Generate a unique idempotency key for a trade.

    Args:
        bot_name: Name of the bot (ARES, ATHENA)
        position_id: Position identifier
        expiration: Option expiration date
        **kwargs: Additional components

    Returns:
        Unique idempotency key
    """
    manager = get_idempotency_manager()
    return manager.generate_key(
        bot_name,
        position_id,
        expiration,
        *kwargs.values()
    )


def check_idempotency(key: str) -> Tuple[bool, Optional[Dict]]:
    """
    Check if a request with this key has already been processed.

    Args:
        key: The idempotency key

    Returns:
        Tuple of (already_processed, result_if_completed)
    """
    manager = get_idempotency_manager()
    exists, record = manager.check_key(key)

    if exists:
        if record.status == IdempotencyStatus.COMPLETED:
            return True, record.result
        elif record.status == IdempotencyStatus.PENDING:
            # Request in progress
            return True, {"status": "pending", "message": "Request in progress"}
        elif record.status == IdempotencyStatus.FAILED:
            # Failed, allow retry
            return False, None

    return False, None


def with_idempotency(
    key: str,
    bot_name: str,
    request_data: Dict[str, Any]
):
    """
    Decorator/context for idempotent operations.

    Usage:
        key = generate_idempotency_key("ARES", position_id)
        if with_idempotency(key, "ARES", request_data):
            # Proceed with operation
            result = execute_order()
            mark_idempotency_completed(key, result)
    """
    manager = get_idempotency_manager()
    request_hash = manager.create_request_hash(request_data)
    return manager.mark_pending(key, bot_name, request_hash)


def mark_idempotency_completed(key: str, result: Dict[str, Any]) -> None:
    """Mark an idempotency key as completed with result."""
    manager = get_idempotency_manager()
    manager.mark_completed(key, result)


def mark_idempotency_failed(key: str, error: str) -> None:
    """Mark an idempotency key as failed with error."""
    manager = get_idempotency_manager()
    manager.mark_failed(key, error)
