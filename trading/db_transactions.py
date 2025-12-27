"""
Database Transaction Control with Rollback

Provides safe transaction handling for trading operations.
Ensures atomicity of multi-step database operations.

Features:
- Automatic rollback on errors
- Context manager for clean transaction handling
- Savepoint support for nested transactions
- Retry logic for transient failures
- Integration with trading operations
"""

import logging
import functools
from contextlib import contextmanager
from typing import Optional, Callable, Any, Generator
import time

logger = logging.getLogger(__name__)

# Try to import database adapter
try:
    from database_adapter import get_connection
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False
    get_connection = None


class TransactionError(Exception):
    """Raised when a transaction fails"""
    pass


class TransactionRollbackError(Exception):
    """Raised when a rollback is explicitly requested"""
    pass


@contextmanager
def transaction(
    auto_commit: bool = True,
    savepoint: Optional[str] = None,
    max_retries: int = 3,
    retry_delay: float = 0.5
) -> Generator:
    """
    Context manager for database transactions with automatic rollback.

    Usage:
        with transaction() as (conn, cursor):
            cursor.execute("INSERT INTO ...")
            cursor.execute("UPDATE ...")
            # Auto-commits on success, rolls back on exception

        with transaction(savepoint="trade_insert") as (conn, cursor):
            # Creates a savepoint for nested transaction

    Args:
        auto_commit: Whether to auto-commit on success
        savepoint: Optional savepoint name for nested transactions
        max_retries: Number of retries for transient failures
        retry_delay: Delay between retries in seconds

    Yields:
        Tuple of (connection, cursor)
    """
    if not DB_AVAILABLE:
        raise TransactionError("Database not available")

    conn = None
    cursor = None
    attempt = 0

    while attempt < max_retries:
        try:
            conn = get_connection()
            cursor = conn.cursor()

            # Create savepoint if specified
            if savepoint:
                cursor.execute(f"SAVEPOINT {savepoint}")
                logger.debug(f"Created savepoint: {savepoint}")

            yield conn, cursor

            # Commit if auto_commit is enabled
            if auto_commit:
                if savepoint:
                    cursor.execute(f"RELEASE SAVEPOINT {savepoint}")
                conn.commit()
                logger.debug("Transaction committed successfully")

            break  # Success, exit retry loop

        except TransactionRollbackError as e:
            # Explicit rollback requested
            if conn:
                if savepoint:
                    try:
                        cursor.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
                        logger.debug(f"Rolled back to savepoint: {savepoint}")
                    except Exception:
                        conn.rollback()
                else:
                    conn.rollback()
            logger.warning(f"Transaction rolled back: {e}")
            raise

        except Exception as e:
            # Rollback on any error
            if conn:
                try:
                    if savepoint:
                        cursor.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
                        logger.debug(f"Rolled back to savepoint: {savepoint}")
                    else:
                        conn.rollback()
                        logger.debug("Transaction rolled back due to error")
                except Exception as rollback_error:
                    logger.error(f"Error during rollback: {rollback_error}")

            # Check if error is transient and should retry
            error_str = str(e).lower()
            is_transient = any(term in error_str for term in [
                'connection', 'timeout', 'deadlock', 'serialization'
            ])

            if is_transient and attempt < max_retries - 1:
                attempt += 1
                logger.warning(f"Transient error, retrying ({attempt}/{max_retries}): {e}")
                time.sleep(retry_delay * attempt)  # Exponential backoff
                continue

            logger.error(f"Transaction failed: {e}")
            raise TransactionError(f"Transaction failed: {e}") from e

        finally:
            if cursor:
                try:
                    cursor.close()
                except Exception:
                    pass
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass


def transactional(
    savepoint: Optional[str] = None,
    max_retries: int = 3
):
    """
    Decorator for making a function transactional.

    Usage:
        @transactional()
        def save_trade(conn, cursor, trade_data):
            cursor.execute("INSERT INTO trades ...")
            cursor.execute("UPDATE positions ...")
            return trade_id

    The decorated function receives (conn, cursor) as first two arguments.
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            with transaction(savepoint=savepoint, max_retries=max_retries) as (conn, cursor):
                return func(conn, cursor, *args, **kwargs)
        return wrapper
    return decorator


class TransactionManager:
    """
    Manager for complex multi-step transactions.

    Provides finer control over transaction lifecycle.
    """

    def __init__(self):
        self.conn = None
        self.cursor = None
        self.savepoints: list = []
        self.in_transaction = False

    def begin(self) -> None:
        """Start a new transaction"""
        if self.in_transaction:
            raise TransactionError("Transaction already in progress")

        if not DB_AVAILABLE:
            raise TransactionError("Database not available")

        self.conn = get_connection()
        self.cursor = self.conn.cursor()
        self.in_transaction = True
        logger.debug("Transaction started")

    def savepoint(self, name: str) -> None:
        """Create a savepoint"""
        if not self.in_transaction:
            raise TransactionError("No transaction in progress")

        self.cursor.execute(f"SAVEPOINT {name}")
        self.savepoints.append(name)
        logger.debug(f"Savepoint created: {name}")

    def rollback_to_savepoint(self, name: str) -> None:
        """Rollback to a specific savepoint"""
        if not self.in_transaction:
            raise TransactionError("No transaction in progress")

        if name not in self.savepoints:
            raise TransactionError(f"Savepoint not found: {name}")

        self.cursor.execute(f"ROLLBACK TO SAVEPOINT {name}")

        # Remove savepoints created after this one
        idx = self.savepoints.index(name)
        self.savepoints = self.savepoints[:idx + 1]
        logger.debug(f"Rolled back to savepoint: {name}")

    def commit(self) -> None:
        """Commit the transaction"""
        if not self.in_transaction:
            raise TransactionError("No transaction in progress")

        try:
            self.conn.commit()
            logger.debug("Transaction committed")
        finally:
            self._cleanup()

    def rollback(self) -> None:
        """Rollback the entire transaction"""
        if not self.in_transaction:
            return

        try:
            self.conn.rollback()
            logger.debug("Transaction rolled back")
        finally:
            self._cleanup()

    def _cleanup(self) -> None:
        """Clean up resources"""
        if self.cursor:
            try:
                self.cursor.close()
            except Exception:
                pass
        if self.conn:
            try:
                self.conn.close()
            except Exception:
                pass

        self.conn = None
        self.cursor = None
        self.savepoints = []
        self.in_transaction = False

    def execute(self, query: str, params: tuple = None) -> Any:
        """Execute a query within the transaction"""
        if not self.in_transaction:
            raise TransactionError("No transaction in progress")

        return self.cursor.execute(query, params)

    def fetchone(self) -> Any:
        """Fetch one result"""
        if not self.cursor:
            return None
        return self.cursor.fetchone()

    def fetchall(self) -> list:
        """Fetch all results"""
        if not self.cursor:
            return []
        return self.cursor.fetchall()


# =============================================================================
# Trading-Specific Transaction Helpers
# =============================================================================

def save_position_atomically(
    table: str,
    position_data: dict,
    on_conflict: Optional[str] = None
) -> bool:
    """
    Save a position to database with atomic transaction.

    Args:
        table: Table name (e.g., 'autonomous_open_positions')
        position_data: Dictionary of column -> value
        on_conflict: Optional ON CONFLICT clause

    Returns:
        True if successful
    """
    columns = list(position_data.keys())
    values = list(position_data.values())
    placeholders = ', '.join(['%s'] * len(values))
    column_list = ', '.join(columns)

    query = f"INSERT INTO {table} ({column_list}) VALUES ({placeholders})"

    if on_conflict:
        query += f" ON CONFLICT {on_conflict}"

    try:
        with transaction() as (conn, cursor):
            cursor.execute(query, tuple(values))
            return True
    except TransactionError as e:
        logger.error(f"Failed to save position: {e}")
        return False


def update_position_atomically(
    table: str,
    position_id: str,
    updates: dict
) -> bool:
    """
    Update a position with atomic transaction.

    Args:
        table: Table name
        position_id: Position identifier
        updates: Dictionary of column -> new_value

    Returns:
        True if successful
    """
    set_clauses = ', '.join([f"{col} = %s" for col in updates.keys()])
    values = list(updates.values()) + [position_id]

    query = f"UPDATE {table} SET {set_clauses} WHERE position_id = %s"

    try:
        with transaction() as (conn, cursor):
            cursor.execute(query, tuple(values))
            return cursor.rowcount > 0
    except TransactionError as e:
        logger.error(f"Failed to update position: {e}")
        return False


def close_position_atomically(
    position_id: str,
    close_data: dict,
    trade_log_data: Optional[dict] = None
) -> bool:
    """
    Close a position and log the trade atomically.

    Both operations succeed or both fail.

    Args:
        position_id: Position to close
        close_data: Data for updating position (status, close_price, etc.)
        trade_log_data: Optional data for trade log entry

    Returns:
        True if successful
    """
    try:
        with transaction(savepoint="close_position") as (conn, cursor):
            # Update position status
            set_clauses = ', '.join([f"{col} = %s" for col in close_data.keys()])
            values = list(close_data.values()) + [position_id]

            cursor.execute(
                f"UPDATE autonomous_open_positions SET {set_clauses} WHERE position_id = %s",
                tuple(values)
            )

            if cursor.rowcount == 0:
                raise TransactionRollbackError(f"Position not found: {position_id}")

            # Insert trade log if provided
            if trade_log_data:
                columns = list(trade_log_data.keys())
                placeholders = ', '.join(['%s'] * len(trade_log_data))
                column_list = ', '.join(columns)

                cursor.execute(
                    f"INSERT INTO autonomous_trade_log ({column_list}) VALUES ({placeholders})",
                    tuple(trade_log_data.values())
                )

            logger.info(f"Position {position_id} closed atomically")
            return True

    except TransactionError as e:
        logger.error(f"Failed to close position atomically: {e}")
        return False


def bulk_update_positions(
    updates: list,
    table: str = "autonomous_open_positions"
) -> int:
    """
    Bulk update multiple positions atomically.

    Args:
        updates: List of (position_id, update_dict) tuples
        table: Table name

    Returns:
        Number of positions updated
    """
    if not updates:
        return 0

    updated_count = 0

    try:
        with transaction() as (conn, cursor):
            for position_id, update_data in updates:
                set_clauses = ', '.join([f"{col} = %s" for col in update_data.keys()])
                values = list(update_data.values()) + [position_id]

                cursor.execute(
                    f"UPDATE {table} SET {set_clauses} WHERE position_id = %s",
                    tuple(values)
                )
                updated_count += cursor.rowcount

        logger.info(f"Bulk updated {updated_count} positions")
        return updated_count

    except TransactionError as e:
        logger.error(f"Bulk update failed: {e}")
        return 0
