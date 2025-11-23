"""
Unified Database Adapter - Automatic PostgreSQL/SQLite Detection
Automatically uses PostgreSQL on Render (when DATABASE_URL exists) or SQLite locally
"""

import os
import sqlite3
from typing import Any, Optional
from urllib.parse import urlparse
from pathlib import Path

# Try to import psycopg2 (only needed on Render)
try:
    import psycopg2
    import psycopg2.extras
    POSTGRESQL_AVAILABLE = True
except ImportError:
    POSTGRESQL_AVAILABLE = False


class DatabaseAdapter:
    """
    Unified database adapter that automatically detects environment:
    - Render (production): Uses PostgreSQL via DATABASE_URL
    - Local (development): Uses SQLite via gex_copilot.db

    This makes all existing code work transparently with both databases.
    """

    def __init__(self):
        """Initialize adapter - auto-detect database type"""
        self.database_url = os.getenv('DATABASE_URL')
        self.is_postgresql = bool(self.database_url and POSTGRESQL_AVAILABLE)

        if self.is_postgresql:
            # Parse PostgreSQL URL
            result = urlparse(self.database_url)
            self.pg_config = {
                'host': result.hostname,
                'port': result.port or 5432,
                'user': result.username,
                'password': result.password,
                'database': result.path[1:]  # Remove leading /
            }
            print(f"✅ Using PostgreSQL: {self.pg_config['host']}/{self.pg_config['database']}")
        else:
            # Use SQLite
            self.sqlite_path = Path(os.environ.get('DATABASE_PATH',
                                                   os.path.join(os.getcwd(), 'gex_copilot.db')))
            print(f"✅ Using SQLite: {self.sqlite_path}")

    def connect(self):
        """
        Create database connection (PostgreSQL or SQLite based on environment)
        Returns a connection object compatible with both database types
        """
        if self.is_postgresql:
            # PostgreSQL connection
            conn = psycopg2.connect(**self.pg_config)
            # Enable autocommit for PostgreSQL (similar to SQLite default behavior)
            conn.autocommit = False
            return PostgreSQLConnectionWrapper(conn)
        else:
            # SQLite connection
            conn = sqlite3.connect(str(self.sqlite_path), timeout=30.0)
            conn.execute('PRAGMA journal_mode=WAL')
            return SQLiteConnectionWrapper(conn)

    def get_db_type(self) -> str:
        """Return 'postgresql' or 'sqlite'"""
        return 'postgresql' if self.is_postgresql else 'sqlite'


class PostgreSQLConnectionWrapper:
    """
    Wrapper for PostgreSQL connections to make them compatible with SQLite-style code
    Translates SQLite-specific syntax to PostgreSQL
    """

    def __init__(self, conn):
        self._conn = conn
        self._in_transaction = False

    def cursor(self):
        """Return cursor"""
        return PostgreSQLCursorWrapper(self._conn.cursor())

    def execute(self, sql, params=None):
        """Execute SQL directly on connection (SQLite style)"""
        cursor = self._conn.cursor()

        # Translate SQLite PRAGMA to PostgreSQL (ignore them)
        if sql.strip().upper().startswith('PRAGMA'):
            return cursor

        # Translate SQLite syntax to PostgreSQL
        sql = self._translate_sql(sql)

        if params:
            cursor.execute(sql, params)
        else:
            cursor.execute(sql)
        return cursor

    def commit(self):
        """Commit transaction"""
        self._conn.commit()
        self._in_transaction = False

    def rollback(self):
        """Rollback transaction"""
        self._conn.rollback()
        self._in_transaction = False

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

    def _translate_sql(self, sql: str) -> str:
        """
        Translate SQLite-specific SQL to PostgreSQL
        Most SQL is identical, but some keywords differ
        """
        import re

        # SQLite uses AUTOINCREMENT, PostgreSQL uses SERIAL
        sql = sql.replace('INTEGER PRIMARY KEY AUTOINCREMENT', 'SERIAL PRIMARY KEY')
        sql = sql.replace('AUTOINCREMENT', '')

        # SQLite uses DATETIME('now'), PostgreSQL uses NOW()
        sql = sql.replace("DATETIME('now')", 'NOW()')
        sql = sql.replace("datetime('now')", 'NOW()')

        # SQLite uses DATETIME as column type, PostgreSQL uses TIMESTAMP
        # Use regex with word boundaries to catch all cases
        sql = re.sub(r'\bDATETIME\b', 'TIMESTAMP', sql, flags=re.IGNORECASE)

        # SQLite uses INSERT OR IGNORE, PostgreSQL uses INSERT ... ON CONFLICT DO NOTHING
        # Pattern: INSERT OR IGNORE INTO table_name (columns...) VALUES (...)
        # Replace with: INSERT INTO table_name (columns...) VALUES (...) ON CONFLICT DO NOTHING
        if 'INSERT OR IGNORE' in sql.upper():
            sql = re.sub(
                r'\bINSERT\s+OR\s+IGNORE\b',
                'INSERT',
                sql,
                flags=re.IGNORECASE
            )
            # Add ON CONFLICT DO NOTHING at the end if not already present
            if 'ON CONFLICT' not in sql.upper():
                sql = sql.rstrip().rstrip(';') + ' ON CONFLICT DO NOTHING'

        # SQLite uses strftime, PostgreSQL uses TO_CHAR
        # (Only translate if needed - most date functions work similarly)

        return sql


class PostgreSQLCursorWrapper:
    """Wrapper for PostgreSQL cursor to add SQLite-compatible methods"""

    def __init__(self, cursor):
        self._cursor = cursor

    def execute(self, sql, params=None):
        """Execute SQL with parameter translation"""
        # Translate SQLite ? placeholders to PostgreSQL %s
        if '?' in sql and params:
            sql = sql.replace('?', '%s')

        # Translate SQL syntax
        sql = self._translate_sql(sql)

        if params:
            self._cursor.execute(sql, params)
        else:
            self._cursor.execute(sql)
        return self

    def executemany(self, sql, params_list):
        """Execute many statements"""
        # Translate placeholders
        if '?' in sql:
            sql = sql.replace('?', '%s')

        sql = self._translate_sql(sql)
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
        """Return last inserted row ID (PostgreSQL compatibility)"""
        # PostgreSQL doesn't have lastrowid, need to use RETURNING
        return None

    @property
    def description(self):
        """Return cursor description (column metadata)"""
        return self._cursor.description

    def close(self):
        """Close cursor"""
        self._cursor.close()

    def _translate_sql(self, sql: str) -> str:
        """Translate SQLite SQL to PostgreSQL"""
        import re

        sql = sql.replace('INTEGER PRIMARY KEY AUTOINCREMENT', 'SERIAL PRIMARY KEY')
        sql = sql.replace('AUTOINCREMENT', '')
        sql = sql.replace("DATETIME('now')", 'NOW()')
        sql = sql.replace("datetime('now')", 'NOW()')

        # SQLite uses DATETIME as column type, PostgreSQL uses TIMESTAMP
        # Use regex with word boundaries to catch all cases
        sql = re.sub(r'\bDATETIME\b', 'TIMESTAMP', sql, flags=re.IGNORECASE)

        # SQLite uses INSERT OR IGNORE, PostgreSQL uses INSERT ... ON CONFLICT DO NOTHING
        if 'INSERT OR IGNORE' in sql.upper():
            sql = re.sub(
                r'\bINSERT\s+OR\s+IGNORE\b',
                'INSERT',
                sql,
                flags=re.IGNORECASE
            )
            # Add ON CONFLICT DO NOTHING at the end if not already present
            if 'ON CONFLICT' not in sql.upper():
                sql = sql.rstrip().rstrip(';') + ' ON CONFLICT DO NOTHING'

        return sql


class SQLiteConnectionWrapper:
    """
    Wrapper for SQLite connections (passthrough - no translation needed)
    Provides consistent interface with PostgreSQL wrapper
    """

    def __init__(self, conn):
        self._conn = conn

    def cursor(self):
        """Return cursor"""
        return self._conn.cursor()

    def execute(self, sql, params=None):
        """Execute SQL"""
        if params:
            return self._conn.execute(sql, params)
        return self._conn.execute(sql)

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
        return self._conn.__enter__()

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        return self._conn.__exit__(exc_type, exc_val, exc_tb)


# Global adapter instance
_adapter = None

def get_db_adapter() -> DatabaseAdapter:
    """Get global database adapter instance (singleton)"""
    global _adapter
    if _adapter is None:
        _adapter = DatabaseAdapter()
    return _adapter


def get_connection():
    """
    Get database connection (PostgreSQL or SQLite based on environment)

    Usage (replaces all sqlite3.connect(DB_PATH) calls):
        from database_adapter import get_connection

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM gex_history LIMIT 10")
        rows = cursor.fetchall()
        conn.close()
    """
    adapter = get_db_adapter()
    return adapter.connect()


# Backwards compatibility: Expose DB_PATH for legacy code
DB_PATH = Path(os.environ.get('DATABASE_PATH', os.path.join(os.getcwd(), 'gex_copilot.db')))


if __name__ == "__main__":
    # Test the adapter
    print("\n" + "="*70)
    print("DATABASE ADAPTER TEST")
    print("="*70)

    adapter = get_db_adapter()
    print(f"\nDatabase Type: {adapter.get_db_type()}")

    print(f"\nTesting connection...")
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Test query
        if adapter.is_postgresql:
            cursor.execute("SELECT version()")
            print(f"PostgreSQL Version: {cursor.fetchone()[0]}")
        else:
            cursor.execute("SELECT sqlite_version()")
            print(f"SQLite Version: {cursor.fetchone()[0]}")

        conn.close()
        print("✅ Connection test successful!")

    except Exception as e:
        print(f"❌ Connection test failed: {e}")
        import traceback
        traceback.print_exc()

    print("="*70 + "\n")
