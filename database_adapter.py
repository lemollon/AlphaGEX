"""
PostgreSQL Database Adapter
Connects to PostgreSQL database via DATABASE_URL environment variable.
"""

import os
from urllib.parse import urlparse

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    raise ImportError(
        "psycopg2 is required. Install with: pip install psycopg2-binary"
    )


class DatabaseAdapter:
    """PostgreSQL database adapter"""

    def __init__(self):
        """Initialize adapter - requires DATABASE_URL"""
        self.database_url = os.getenv('DATABASE_URL')

        if not self.database_url:
            raise ValueError(
                "DATABASE_URL environment variable is required.\n"
                "For local development, set: export DATABASE_URL=postgresql://user:pass@localhost:5432/dbname"
            )

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

    def connect(self):
        """Create PostgreSQL database connection"""
        conn = psycopg2.connect(**self.pg_config)
        conn.autocommit = False
        return PostgreSQLConnection(conn)

    def get_db_type(self) -> str:
        """Return database type"""
        return 'postgresql'


class PostgreSQLConnection:
    """PostgreSQL connection wrapper"""

    def __init__(self, conn):
        self._conn = conn

    def cursor(self):
        """Return cursor"""
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


class PostgreSQLCursor:
    """PostgreSQL cursor wrapper"""

    def __init__(self, cursor):
        self._cursor = cursor

    def execute(self, sql, params=None):
        """Execute SQL"""
        import re

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
