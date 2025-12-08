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


class DatabaseUnavailableError(Exception):
    """Raised when database is not available"""
    pass


class DatabaseAdapter:
    """PostgreSQL database adapter"""

    def __init__(self):
        """Initialize adapter - requires DATABASE_URL"""
        self.database_url = os.getenv('DATABASE_URL')

        if not self.database_url:
            raise DatabaseUnavailableError(
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
            'database': result.path[1:],  # Remove leading /
            # Timeout settings to prevent hanging
            'connect_timeout': 30,  # 30 seconds to connect
            'options': '-c statement_timeout=300000',  # 5 minute query timeout
            # Keepalive settings for long operations
            'keepalives': 1,
            'keepalives_idle': 30,
            'keepalives_interval': 10,
            'keepalives_count': 5
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
