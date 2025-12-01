"""
Database connection management for AlphaGEX.

This module provides:
- Connection pooling for efficient database access
- Async-ready connection management
- Safe error handling without exposing credentials
- Transaction context managers
"""

import os
import logging
from typing import Any, Dict, Generator, Optional
from contextlib import contextmanager
from functools import lru_cache

import psycopg2
import psycopg2.pool
import psycopg2.extras

from backend.api.exceptions import DatabaseConnectionError, DatabaseQueryError
from backend.api.logging_config import api_logger

# =============================================================================
# CONNECTION POOL
# =============================================================================

class DatabasePool:
    """
    Thread-safe database connection pool.

    Usage:
        pool = get_database_pool()
        with pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM table")
    """

    _instance: Optional['DatabasePool'] = None
    _pool: Optional[psycopg2.pool.ThreadedConnectionPool] = None

    def __init__(
        self,
        min_connections: int = 2,
        max_connections: int = 10
    ):
        self.min_connections = min_connections
        self.max_connections = max_connections
        self._initialize_pool()

    def _initialize_pool(self):
        """Initialize the connection pool."""
        database_url = os.getenv('DATABASE_URL', '')

        if not database_url:
            api_logger.warning("DATABASE_URL not configured - database features will be unavailable")
            return

        try:
            self._pool = psycopg2.pool.ThreadedConnectionPool(
                self.min_connections,
                self.max_connections,
                database_url,
                cursor_factory=psycopg2.extras.RealDictCursor
            )
            api_logger.info(
                f"Database pool initialized: min={self.min_connections}, max={self.max_connections}"
            )
        except psycopg2.Error as e:
            # Never log the actual connection string - it contains credentials
            api_logger.error(
                "Failed to initialize database pool - check DATABASE_URL configuration",
                extra={'context': {'error_type': type(e).__name__}}
            )
            self._pool = None

    @property
    def is_available(self) -> bool:
        """Check if the pool is available."""
        return self._pool is not None

    @contextmanager
    def get_connection(self) -> Generator[psycopg2.extensions.connection, None, None]:
        """
        Get a connection from the pool.

        Usage:
            with pool.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1")

        Yields:
            Database connection

        Raises:
            DatabaseConnectionError: If connection cannot be obtained
        """
        if not self._pool:
            raise DatabaseConnectionError("Database pool not initialized")

        conn = None
        try:
            conn = self._pool.getconn()
            if conn is None:
                raise DatabaseConnectionError("No connections available in pool")

            yield conn

            # Commit if no errors
            conn.commit()

        except psycopg2.Error as e:
            if conn:
                conn.rollback()
            # Don't expose internal database error details
            api_logger.error(
                "Database error occurred",
                extra={'context': {'error_type': type(e).__name__}}
            )
            raise DatabaseConnectionError(f"Database operation failed: {type(e).__name__}")

        finally:
            if conn:
                self._pool.putconn(conn)

    @contextmanager
    def get_cursor(
        self,
        cursor_factory=None
    ) -> Generator[psycopg2.extensions.cursor, None, None]:
        """
        Get a cursor directly from the pool.

        Usage:
            with pool.get_cursor() as cursor:
                cursor.execute("SELECT * FROM table")
                rows = cursor.fetchall()

        Yields:
            Database cursor

        Raises:
            DatabaseConnectionError: If cursor cannot be obtained
        """
        factory = cursor_factory or psycopg2.extras.RealDictCursor

        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=factory)
            try:
                yield cursor
            finally:
                cursor.close()

    def execute(
        self,
        query: str,
        params: tuple = None,
        fetch: str = 'all'
    ) -> Any:
        """
        Execute a query and return results.

        Args:
            query: SQL query to execute
            params: Query parameters
            fetch: 'all', 'one', 'none', or 'count'

        Returns:
            Query results based on fetch parameter
        """
        with self.get_cursor() as cursor:
            cursor.execute(query, params)

            if fetch == 'all':
                return cursor.fetchall()
            elif fetch == 'one':
                return cursor.fetchone()
            elif fetch == 'count':
                return cursor.rowcount
            else:
                return None

    def execute_many(
        self,
        query: str,
        params_list: list
    ) -> int:
        """
        Execute a query with multiple parameter sets.

        Args:
            query: SQL query to execute
            params_list: List of parameter tuples

        Returns:
            Number of rows affected
        """
        with self.get_cursor() as cursor:
            cursor.executemany(query, params_list)
            return cursor.rowcount

    def health_check(self) -> Dict[str, Any]:
        """
        Perform a health check on the database connection.

        Returns:
            Dictionary with health check results
        """
        if not self._pool:
            return {
                'healthy': False,
                'error': 'Pool not initialized'
            }

        try:
            with self.get_cursor() as cursor:
                cursor.execute("SELECT 1 as test")
                result = cursor.fetchone()
                return {
                    'healthy': True,
                    'test_query': result['test'] == 1 if result else False
                }
        except Exception as e:
            return {
                'healthy': False,
                'error': type(e).__name__
            }

    def close(self):
        """Close all connections in the pool."""
        if self._pool:
            self._pool.closeall()
            api_logger.info("Database pool closed")


# =============================================================================
# SINGLETON ACCESS
# =============================================================================

_pool_instance: Optional[DatabasePool] = None


def get_database_pool() -> DatabasePool:
    """
    Get the database pool singleton.

    Returns:
        DatabasePool instance
    """
    global _pool_instance
    if _pool_instance is None:
        _pool_instance = DatabasePool()
    return _pool_instance


def get_db_connection():
    """
    Get a database connection from the pool.

    This is a convenience function for compatibility with existing code.

    Returns:
        Connection context manager
    """
    return get_database_pool().get_connection()


# =============================================================================
# TRANSACTION HELPERS
# =============================================================================

@contextmanager
def transaction():
    """
    Context manager for database transactions.

    Usage:
        with transaction() as (conn, cursor):
            cursor.execute("INSERT INTO table VALUES (%s)", (value,))
            cursor.execute("UPDATE other_table SET x = %s", (value,))
        # Commits automatically on success, rolls back on exception
    """
    pool = get_database_pool()

    if not pool.is_available:
        raise DatabaseConnectionError("Database not available")

    conn = pool._pool.getconn()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        yield conn, cursor
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        pool._pool.putconn(conn)


# =============================================================================
# QUERY HELPERS
# =============================================================================

def fetch_all(query: str, params: tuple = None) -> list:
    """Execute query and fetch all results."""
    return get_database_pool().execute(query, params, fetch='all')


def fetch_one(query: str, params: tuple = None) -> Optional[Dict]:
    """Execute query and fetch one result."""
    return get_database_pool().execute(query, params, fetch='one')


def execute_query(query: str, params: tuple = None) -> int:
    """Execute query and return affected row count."""
    return get_database_pool().execute(query, params, fetch='count')


# =============================================================================
# LEGACY COMPATIBILITY
# =============================================================================

def get_connection():
    """
    Legacy compatibility function.

    DEPRECATED: Use get_database_pool().get_connection() instead.

    This maintains backward compatibility with code that uses:
        conn = get_connection()
        cursor = conn.cursor()
        ...
        conn.close()
    """
    # For legacy code, return a direct connection
    # Note: The caller is responsible for closing this connection
    database_url = os.getenv('DATABASE_URL', '')

    if not database_url:
        raise DatabaseConnectionError("DATABASE_URL not configured")

    try:
        conn = psycopg2.connect(
            database_url,
            cursor_factory=psycopg2.extras.RealDictCursor
        )
        return conn
    except psycopg2.Error as e:
        api_logger.error(
            "Failed to create database connection",
            extra={'context': {'error_type': type(e).__name__}}
        )
        raise DatabaseConnectionError("Database connection failed")
