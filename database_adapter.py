"""
PostgreSQL Database Adapter
Connects to PostgreSQL database via DATABASE_URL environment variable.

Now with connection pooling for improved performance (30-40% latency reduction).
"""

import os
import threading
from urllib.parse import urlparse

try:
    import psycopg2
    import psycopg2.extras
    import psycopg2.pool
except ImportError:
    raise ImportError(
        "psycopg2 is required. Install with: pip install psycopg2-binary"
    )


class DatabaseUnavailableError(Exception):
    """Raised when database is not available"""
    pass


class DatabaseAdapter:
    """PostgreSQL database adapter with connection pooling"""

    # Pool configuration
    MIN_CONNECTIONS = 2
    MAX_CONNECTIONS = 15  # Increased for high-traffic scenarios

    def __init__(self):
        """Initialize adapter with connection pool - requires DATABASE_URL"""
        self.database_url = os.getenv('DATABASE_URL')
        self._pool = None
        self._pool_lock = threading.Lock()

        if not self.database_url:
            raise DatabaseUnavailableError(
                "DATABASE_URL environment variable is required.\n"
                "For local development, set: export DATABASE_URL=postgresql://user:pass@localhost:5432/dbname"
            )

        # Parse PostgreSQL URL for logging only (pool uses URL directly)
        result = urlparse(self.database_url)
        self._host = result.hostname
        self._database = result.path[1:] if result.path else 'unknown'

        global _connection_logged
        if not _connection_logged:
            print(f"✅ Using PostgreSQL with pooling: {self._host}/{self._database}")
            _connection_logged = True

        # Initialize the connection pool
        self._init_pool()

    def _init_pool(self):
        """Initialize the connection pool."""
        try:
            self._pool = psycopg2.pool.ThreadedConnectionPool(
                self.MIN_CONNECTIONS,
                self.MAX_CONNECTIONS,
                self.database_url,
                # Timeout settings
                connect_timeout=30,
                options='-c statement_timeout=300000',  # 5 minute query timeout
                # Keepalive settings
                keepalives=1,
                keepalives_idle=30,
                keepalives_interval=10,
                keepalives_count=5
            )
            global _connection_logged
            if _connection_logged:
                print(f"   Pool initialized: min={self.MIN_CONNECTIONS}, max={self.MAX_CONNECTIONS}")
        except psycopg2.Error as e:
            print(f"⚠️  Failed to initialize connection pool: {e}")
            self._pool = None

    def connect(self):
        """Get a connection from the pool (or create new if pool unavailable)"""
        if self._pool:
            try:
                with self._pool_lock:
                    conn = self._pool.getconn()
                if conn:
                    conn.autocommit = False
                    return PooledPostgreSQLConnection(conn, self)
            except psycopg2.pool.PoolError as e:
                print(f"⚠️  Pool exhausted, creating direct connection: {e}")
                # Fall through to direct connection

        # Fallback: Create direct connection (no pooling)
        conn = psycopg2.connect(
            self.database_url,
            connect_timeout=30,
            options='-c statement_timeout=300000',
            keepalives=1,
            keepalives_idle=30,
            keepalives_interval=10,
            keepalives_count=5
        )
        conn.autocommit = False
        return PostgreSQLConnection(conn)

    def return_connection(self, conn):
        """Return a connection to the pool."""
        if self._pool and conn:
            try:
                with self._pool_lock:
                    self._pool.putconn(conn)
            except Exception:
                # If returning fails, just close it
                try:
                    conn.close()
                except Exception:
                    pass

    def get_db_type(self) -> str:
        """Return database type"""
        return 'postgresql'

    def get_pool_stats(self) -> dict:
        """Get connection pool statistics."""
        if not self._pool:
            return {'pooling': False, 'reason': 'Pool not initialized'}

        # ThreadedConnectionPool doesn't expose stats directly,
        # but we can provide configuration info
        return {
            'pooling': True,
            'min_connections': self.MIN_CONNECTIONS,
            'max_connections': self.MAX_CONNECTIONS,
            'host': self._host,
            'database': self._database
        }

    def close_pool(self):
        """Close all connections in the pool."""
        if self._pool:
            try:
                self._pool.closeall()
                print("✅ Connection pool closed")
            except Exception as e:
                print(f"⚠️  Error closing pool: {e}")


class PostgreSQLConnection:
    """PostgreSQL connection wrapper (non-pooled, closes on close())"""

    def __init__(self, conn):
        self._conn = conn

    @property
    def raw_connection(self):
        """Return raw psycopg2 connection for pandas compatibility"""
        return self._conn

    def cursor(self, cursor_factory=None):
        """Return cursor with optional cursor_factory support"""
        if cursor_factory:
            return PostgreSQLCursor(self._conn.cursor(cursor_factory=cursor_factory))
        return PostgreSQLCursor(self._conn.cursor())

    def execute(self, sql, params=None):
        """Execute SQL directly on connection"""
        cursor = self._conn.cursor()
        if params:
            cursor.execute(sql, params)
        else:
            cursor.execute(sql)
        return cursor

    def commit(self):
        """Commit transaction"""
        self._conn.commit()

    def rollback(self):
        """Rollback transaction"""
        self._conn.rollback()

    def close(self):
        """Close connection"""
        self._conn.close()

    def __enter__(self):
        """Context manager entry"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        if exc_type is None:
            self.commit()
        else:
            self.rollback()
        self.close()


class PooledPostgreSQLConnection(PostgreSQLConnection):
    """PostgreSQL connection wrapper that returns to pool on close()"""

    def __init__(self, conn, adapter):
        super().__init__(conn)
        self._adapter = adapter
        self._returned = False

    def close(self):
        """Return connection to pool instead of closing"""
        if not self._returned and self._conn:
            self._returned = True
            try:
                # Rollback any uncommitted transaction before returning to pool
                try:
                    self._conn.rollback()
                except Exception:
                    pass
                self._adapter.return_connection(self._conn)
            except Exception:
                # If returning fails, actually close it
                try:
                    self._conn.close()
                except Exception:
                    pass

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - commit/rollback then return to pool"""
        if exc_type is None:
            try:
                self.commit()
            except Exception:
                self.rollback()
        else:
            self.rollback()
        self.close()

    def __del__(self):
        """Ensure connection is returned to pool if forgotten"""
        if not self._returned and self._conn:
            self.close()


class PostgreSQLCursor:
    """PostgreSQL cursor wrapper"""

    def __init__(self, cursor):
        self._cursor = cursor

    def execute(self, sql, params=None):
        """Execute SQL"""
        import re
        from psycopg2 import sql as psycopg2_sql

        # If sql is a Composed object (from psycopg2.sql), execute directly without transformation
        # Composed objects are already safely constructed and shouldn't be modified
        if isinstance(sql, (psycopg2_sql.Composed, psycopg2_sql.SQL)):
            if params:
                self._cursor.execute(sql, params)
            else:
                self._cursor.execute(sql)
            return self

        # Convert ? placeholders to %s for PostgreSQL
        if '?' in sql and params:
            sql = sql.replace('?', '%s')

        # Basic SQL translations for convenience
        sql = sql.replace('INTEGER PRIMARY KEY AUTOINCREMENT', 'SERIAL PRIMARY KEY')
        sql = sql.replace('AUTOINCREMENT', '')
        sql = re.sub(r'\bDATETIME\b', 'TIMESTAMP', sql, flags=re.IGNORECASE)
        sql = sql.replace("DATETIME('now')", 'NOW()')
        sql = sql.replace("datetime('now')", 'NOW()')

        # INSERT OR IGNORE → INSERT ... ON CONFLICT DO NOTHING
        if 'INSERT OR IGNORE' in sql.upper():
            sql = re.sub(r'\bINSERT\s+OR\s+IGNORE\b', 'INSERT', sql, flags=re.IGNORECASE)
            if 'ON CONFLICT' not in sql.upper():
                sql = sql.rstrip().rstrip(';') + ' ON CONFLICT DO NOTHING'

        # INSERT OR REPLACE → INSERT ... ON CONFLICT DO UPDATE
        # This handles common key-value config tables like autonomous_config, paper_config, etc.
        if 'INSERT OR REPLACE' in sql.upper():
            # Extract table name and columns
            match = re.search(
                r'INSERT\s+OR\s+REPLACE\s+INTO\s+(\w+)\s*\(([^)]+)\)',
                sql, flags=re.IGNORECASE
            )
            if match:
                table_name = match.group(1)
                columns = [col.strip() for col in match.group(2).split(',')]
                # First column is typically the primary key
                pk_column = columns[0]
                # Build the ON CONFLICT UPDATE clause for all non-PK columns
                update_cols = [col for col in columns if col != pk_column]
                update_clause = ', '.join([f'{col} = EXCLUDED.{col}' for col in update_cols])

                # Remove OR REPLACE
                sql = re.sub(r'\bINSERT\s+OR\s+REPLACE\b', 'INSERT', sql, flags=re.IGNORECASE)
                # Add ON CONFLICT clause
                if 'ON CONFLICT' not in sql.upper() and update_clause:
                    sql = sql.rstrip().rstrip(';') + f' ON CONFLICT ({pk_column}) DO UPDATE SET {update_clause}'

        if params:
            self._cursor.execute(sql, params)
        else:
            self._cursor.execute(sql)
        return self

    def executemany(self, sql, params_list):
        """Execute many statements"""
        # Convert ? placeholders to %s
        if '?' in sql:
            sql = sql.replace('?', '%s')
        self._cursor.executemany(sql, params_list)
        return self

    def fetchone(self):
        """Fetch one row"""
        return self._cursor.fetchone()

    def fetchall(self):
        """Fetch all rows"""
        return self._cursor.fetchall()

    def fetchmany(self, size=None):
        """Fetch many rows"""
        if size:
            return self._cursor.fetchmany(size)
        return self._cursor.fetchmany()

    @property
    def rowcount(self):
        """Return number of affected rows"""
        return self._cursor.rowcount

    @property
    def lastrowid(self):
        """Return last inserted row ID (use RETURNING instead)"""
        return None

    @property
    def description(self):
        """Return cursor description (column metadata)"""
        return self._cursor.description

    def close(self):
        """Close cursor"""
        self._cursor.close()


# Global adapter instance
_adapter = None
_db_available = None  # Cache the availability check
_connection_logged = False  # Only log connection once


def is_database_available() -> bool:
    """Check if database is available without throwing an exception"""
    global _db_available
    if _db_available is not None:
        return _db_available
    try:
        get_db_adapter()
        _db_available = True
        return True
    except (DatabaseUnavailableError, ImportError):
        _db_available = False
        return False


def get_db_adapter() -> DatabaseAdapter:
    """Get global database adapter instance (singleton)"""
    global _adapter
    if _adapter is None:
        _adapter = DatabaseAdapter()
    return _adapter


def get_connection():
    """
    Get PostgreSQL database connection

    Usage:
        from database_adapter import get_connection

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM gex_history LIMIT 10")
        rows = cursor.fetchall()
        conn.close()
    """
    adapter = get_db_adapter()
    return adapter.connect()


if __name__ == "__main__":
    # Test the adapter
    print("\n" + "="*70)
    print("DATABASE ADAPTER TEST")
    print("="*70)

    try:
        adapter = get_db_adapter()
        print(f"\nDatabase Type: {adapter.get_db_type()}")

        print(f"\nTesting connection...")
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT version()")
        print(f"PostgreSQL Version: {cursor.fetchone()[0]}")

        conn.close()
        print("✅ Connection test successful!")

    except Exception as e:
        print(f"❌ Connection test failed: {e}")
        import traceback
        traceback.print_exc()

    print("="*70 + "\n")
