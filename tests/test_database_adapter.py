"""
Comprehensive Tests for Database Adapter

Tests the PostgreSQL database adapter including:
- Connection management
- SQL translation (SQLite to PostgreSQL)
- Cursor wrapper functionality
- Error handling

Run with: pytest tests/test_database_adapter.py -v
"""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestDatabaseAdapter:
    """Tests for DatabaseAdapter class"""

    @patch.dict('os.environ', {'DATABASE_URL': 'postgresql://user:pass@localhost:5432/testdb'})
    @patch('database_adapter.psycopg2')
    def test_adapter_initialization(self, mock_psycopg):
        """Test adapter initializes with DATABASE_URL"""
        from database_adapter import DatabaseAdapter

        adapter = DatabaseAdapter()

        assert adapter.pg_config['host'] == 'localhost'
        assert adapter.pg_config['port'] == 5432
        assert adapter.pg_config['user'] == 'user'
        assert adapter.pg_config['database'] == 'testdb'

    @patch.dict('os.environ', {}, clear=True)
    def test_adapter_raises_without_database_url(self):
        """Test adapter raises error without DATABASE_URL"""
        # Need to reload to pick up cleared env
        import importlib
        import database_adapter

        # Clear cached adapter
        database_adapter._adapter = None
        database_adapter._db_available = None

        with pytest.raises(Exception) as exc_info:
            database_adapter.get_db_adapter()

        assert 'DATABASE_URL' in str(exc_info.value)

    @patch.dict('os.environ', {'DATABASE_URL': 'postgresql://user:pass@localhost:5432/testdb'})
    @patch('database_adapter.psycopg2')
    def test_get_db_type(self, mock_psycopg):
        """Test get_db_type returns postgresql"""
        from database_adapter import DatabaseAdapter

        adapter = DatabaseAdapter()
        assert adapter.get_db_type() == 'postgresql'

    @patch.dict('os.environ', {'DATABASE_URL': 'postgresql://user:pass@localhost:5432/testdb'})
    @patch('database_adapter.psycopg2')
    def test_connect_returns_wrapper(self, mock_psycopg):
        """Test connect returns PostgreSQLConnection wrapper"""
        mock_conn = MagicMock()
        mock_psycopg.connect.return_value = mock_conn

        from database_adapter import DatabaseAdapter, PostgreSQLConnection

        adapter = DatabaseAdapter()
        conn = adapter.connect()

        assert isinstance(conn, PostgreSQLConnection)
        mock_psycopg.connect.assert_called_once()


class TestPostgreSQLConnection:
    """Tests for PostgreSQLConnection wrapper"""

    def test_cursor_returns_wrapper(self):
        """Test cursor returns PostgreSQLCursor wrapper"""
        from database_adapter import PostgreSQLConnection, PostgreSQLCursor

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        wrapper = PostgreSQLConnection(mock_conn)
        cursor = wrapper.cursor()

        assert isinstance(cursor, PostgreSQLCursor)

    def test_commit(self):
        """Test commit calls underlying connection"""
        from database_adapter import PostgreSQLConnection

        mock_conn = MagicMock()
        wrapper = PostgreSQLConnection(mock_conn)

        wrapper.commit()
        mock_conn.commit.assert_called_once()

    def test_rollback(self):
        """Test rollback calls underlying connection"""
        from database_adapter import PostgreSQLConnection

        mock_conn = MagicMock()
        wrapper = PostgreSQLConnection(mock_conn)

        wrapper.rollback()
        mock_conn.rollback.assert_called_once()

    def test_close(self):
        """Test close calls underlying connection"""
        from database_adapter import PostgreSQLConnection

        mock_conn = MagicMock()
        wrapper = PostgreSQLConnection(mock_conn)

        wrapper.close()
        mock_conn.close.assert_called_once()

    def test_context_manager_commit_on_success(self):
        """Test context manager commits on successful exit"""
        from database_adapter import PostgreSQLConnection

        mock_conn = MagicMock()
        wrapper = PostgreSQLConnection(mock_conn)

        with wrapper:
            pass  # Success path

        mock_conn.commit.assert_called_once()
        mock_conn.close.assert_called_once()

    def test_context_manager_rollback_on_exception(self):
        """Test context manager rolls back on exception"""
        from database_adapter import PostgreSQLConnection

        mock_conn = MagicMock()
        wrapper = PostgreSQLConnection(mock_conn)

        with pytest.raises(ValueError):
            with wrapper:
                raise ValueError("Test error")

        mock_conn.rollback.assert_called_once()
        mock_conn.close.assert_called_once()

    def test_raw_connection_property(self):
        """Test raw_connection returns underlying connection"""
        from database_adapter import PostgreSQLConnection

        mock_conn = MagicMock()
        wrapper = PostgreSQLConnection(mock_conn)

        assert wrapper.raw_connection is mock_conn


class TestPostgreSQLCursor:
    """Tests for PostgreSQLCursor wrapper"""

    def test_execute_basic_sql(self):
        """Test basic SQL execution"""
        from database_adapter import PostgreSQLCursor

        mock_cursor = MagicMock()
        wrapper = PostgreSQLCursor(mock_cursor)

        wrapper.execute("SELECT * FROM users WHERE id = %s", (1,))
        mock_cursor.execute.assert_called_once()

    def test_execute_converts_question_mark_placeholders(self):
        """Test that ? placeholders are converted to %s"""
        from database_adapter import PostgreSQLCursor

        mock_cursor = MagicMock()
        wrapper = PostgreSQLCursor(mock_cursor)

        wrapper.execute("SELECT * FROM users WHERE id = ?", (1,))

        # The SQL should have been converted
        called_sql = mock_cursor.execute.call_args[0][0]
        assert '%s' in called_sql
        assert '?' not in called_sql

    def test_execute_converts_datetime_function(self):
        """Test DATETIME is converted to TIMESTAMP"""
        from database_adapter import PostgreSQLCursor

        mock_cursor = MagicMock()
        wrapper = PostgreSQLCursor(mock_cursor)

        wrapper.execute("CREATE TABLE test (created DATETIME)")

        called_sql = mock_cursor.execute.call_args[0][0]
        assert 'TIMESTAMP' in called_sql
        assert 'DATETIME' not in called_sql

    def test_execute_converts_autoincrement(self):
        """Test AUTOINCREMENT is converted to SERIAL"""
        from database_adapter import PostgreSQLCursor

        mock_cursor = MagicMock()
        wrapper = PostgreSQLCursor(mock_cursor)

        wrapper.execute("CREATE TABLE test (id INTEGER PRIMARY KEY AUTOINCREMENT)")

        called_sql = mock_cursor.execute.call_args[0][0]
        assert 'SERIAL PRIMARY KEY' in called_sql

    def test_execute_converts_insert_or_ignore(self):
        """Test INSERT OR IGNORE is converted to ON CONFLICT DO NOTHING"""
        from database_adapter import PostgreSQLCursor

        mock_cursor = MagicMock()
        wrapper = PostgreSQLCursor(mock_cursor)

        wrapper.execute("INSERT OR IGNORE INTO users (id, name) VALUES (?, ?)", (1, 'test'))

        called_sql = mock_cursor.execute.call_args[0][0]
        assert 'ON CONFLICT DO NOTHING' in called_sql
        assert 'OR IGNORE' not in called_sql.upper()

    def test_execute_converts_insert_or_replace(self):
        """Test INSERT OR REPLACE is converted to ON CONFLICT DO UPDATE"""
        from database_adapter import PostgreSQLCursor

        mock_cursor = MagicMock()
        wrapper = PostgreSQLCursor(mock_cursor)

        wrapper.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", ('test', 'value'))

        called_sql = mock_cursor.execute.call_args[0][0]
        assert 'ON CONFLICT' in called_sql
        assert 'DO UPDATE' in called_sql
        assert 'OR REPLACE' not in called_sql.upper()

    def test_execute_converts_datetime_now(self):
        """Test datetime('now') is converted to NOW()"""
        from database_adapter import PostgreSQLCursor

        mock_cursor = MagicMock()
        wrapper = PostgreSQLCursor(mock_cursor)

        wrapper.execute("INSERT INTO logs (created_at) VALUES (datetime('now'))")

        called_sql = mock_cursor.execute.call_args[0][0]
        assert 'NOW()' in called_sql

    def test_fetchone(self):
        """Test fetchone passes through"""
        from database_adapter import PostgreSQLCursor

        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (1, 'test')
        wrapper = PostgreSQLCursor(mock_cursor)

        result = wrapper.fetchone()
        assert result == (1, 'test')

    def test_fetchall(self):
        """Test fetchall passes through"""
        from database_adapter import PostgreSQLCursor

        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [(1, 'a'), (2, 'b')]
        wrapper = PostgreSQLCursor(mock_cursor)

        result = wrapper.fetchall()
        assert result == [(1, 'a'), (2, 'b')]

    def test_fetchmany(self):
        """Test fetchmany passes through"""
        from database_adapter import PostgreSQLCursor

        mock_cursor = MagicMock()
        mock_cursor.fetchmany.return_value = [(1, 'a')]
        wrapper = PostgreSQLCursor(mock_cursor)

        result = wrapper.fetchmany(1)
        assert result == [(1, 'a')]

    def test_rowcount_property(self):
        """Test rowcount property"""
        from database_adapter import PostgreSQLCursor

        mock_cursor = MagicMock()
        mock_cursor.rowcount = 5
        wrapper = PostgreSQLCursor(mock_cursor)

        assert wrapper.rowcount == 5

    def test_description_property(self):
        """Test description property"""
        from database_adapter import PostgreSQLCursor

        mock_cursor = MagicMock()
        mock_cursor.description = [('id',), ('name',)]
        wrapper = PostgreSQLCursor(mock_cursor)

        assert wrapper.description == [('id',), ('name',)]

    def test_executemany(self):
        """Test executemany with placeholder conversion"""
        from database_adapter import PostgreSQLCursor

        mock_cursor = MagicMock()
        wrapper = PostgreSQLCursor(mock_cursor)

        wrapper.executemany("INSERT INTO users (id) VALUES (?)", [(1,), (2,)])

        called_sql = mock_cursor.executemany.call_args[0][0]
        assert '%s' in called_sql
        assert '?' not in called_sql

    def test_close(self):
        """Test close passes through"""
        from database_adapter import PostgreSQLCursor

        mock_cursor = MagicMock()
        wrapper = PostgreSQLCursor(mock_cursor)

        wrapper.close()
        mock_cursor.close.assert_called_once()


class TestHelperFunctions:
    """Tests for module-level helper functions"""

    @patch.dict('os.environ', {'DATABASE_URL': 'postgresql://user:pass@localhost:5432/testdb'})
    @patch('database_adapter.psycopg2')
    def test_is_database_available_returns_true(self, mock_psycopg):
        """Test is_database_available returns True when DB available"""
        import database_adapter
        database_adapter._adapter = None
        database_adapter._db_available = None

        result = database_adapter.is_database_available()
        assert result is True

    @patch.dict('os.environ', {}, clear=True)
    def test_is_database_available_returns_false(self):
        """Test is_database_available returns False when no DATABASE_URL"""
        import importlib
        import database_adapter

        database_adapter._adapter = None
        database_adapter._db_available = None

        result = database_adapter.is_database_available()
        assert result is False

    @patch.dict('os.environ', {'DATABASE_URL': 'postgresql://user:pass@localhost:5432/testdb'})
    @patch('database_adapter.psycopg2')
    def test_get_db_adapter_singleton(self, mock_psycopg):
        """Test get_db_adapter returns singleton"""
        import database_adapter
        database_adapter._adapter = None

        adapter1 = database_adapter.get_db_adapter()
        adapter2 = database_adapter.get_db_adapter()

        assert adapter1 is adapter2

    @patch.dict('os.environ', {'DATABASE_URL': 'postgresql://user:pass@localhost:5432/testdb'})
    @patch('database_adapter.psycopg2')
    def test_get_connection(self, mock_psycopg):
        """Test get_connection returns connection wrapper"""
        mock_conn = MagicMock()
        mock_psycopg.connect.return_value = mock_conn

        import database_adapter
        database_adapter._adapter = None

        from database_adapter import get_connection, PostgreSQLConnection

        conn = get_connection()
        assert isinstance(conn, PostgreSQLConnection)


class TestConnectionPooling:
    """Tests for connection configuration"""

    @patch.dict('os.environ', {'DATABASE_URL': 'postgresql://user:pass@localhost:5432/testdb'})
    @patch('database_adapter.psycopg2')
    def test_connection_timeout_settings(self, mock_psycopg):
        """Test connection has timeout settings"""
        from database_adapter import DatabaseAdapter

        adapter = DatabaseAdapter()

        assert 'connect_timeout' in adapter.pg_config
        assert adapter.pg_config['connect_timeout'] == 30

    @patch.dict('os.environ', {'DATABASE_URL': 'postgresql://user:pass@localhost:5432/testdb'})
    @patch('database_adapter.psycopg2')
    def test_keepalive_settings(self, mock_psycopg):
        """Test connection has keepalive settings"""
        from database_adapter import DatabaseAdapter

        adapter = DatabaseAdapter()

        assert adapter.pg_config.get('keepalives') == 1
        assert adapter.pg_config.get('keepalives_idle') == 30


class TestDatabaseUnavailableError:
    """Tests for DatabaseUnavailableError"""

    def test_error_is_defined(self):
        """Test DatabaseUnavailableError is defined"""
        from database_adapter import DatabaseUnavailableError

        assert issubclass(DatabaseUnavailableError, Exception)

    def test_error_can_be_raised(self):
        """Test DatabaseUnavailableError can be raised"""
        from database_adapter import DatabaseUnavailableError

        with pytest.raises(DatabaseUnavailableError):
            raise DatabaseUnavailableError("Test error")


class TestEdgeCases:
    """Tests for edge cases"""

    def test_cursor_with_cursor_factory(self):
        """Test cursor with custom cursor_factory"""
        from database_adapter import PostgreSQLConnection, PostgreSQLCursor

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        wrapper = PostgreSQLConnection(mock_conn)

        # Pass cursor_factory
        cursor = wrapper.cursor(cursor_factory=MagicMock)

        assert isinstance(cursor, PostgreSQLCursor)
        mock_conn.cursor.assert_called()

    def test_execute_without_params(self):
        """Test execute without parameters"""
        from database_adapter import PostgreSQLCursor

        mock_cursor = MagicMock()
        wrapper = PostgreSQLCursor(mock_cursor)

        wrapper.execute("SELECT * FROM users")
        mock_cursor.execute.assert_called_once()

    def test_lastrowid_returns_none(self):
        """Test lastrowid returns None (PostgreSQL uses RETURNING)"""
        from database_adapter import PostgreSQLCursor

        mock_cursor = MagicMock()
        wrapper = PostgreSQLCursor(mock_cursor)

        assert wrapper.lastrowid is None
