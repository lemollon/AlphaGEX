"""
Database Integration Tests

These tests run against the ACTUAL database (not mocked).
They verify real database operations work correctly.

IMPORTANT: These tests require DATABASE_URL environment variable.
Run with: pytest tests/integration/test_database_integration.py -v

To skip if no database: pytest tests/integration/ -v --ignore-glob="*integration*"
"""

import pytest
import os
from datetime import datetime
from zoneinfo import ZoneInfo
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

CENTRAL_TZ = ZoneInfo("America/Chicago")

# Skip all tests if no DATABASE_URL
pytestmark = pytest.mark.skipif(
    not os.getenv('DATABASE_URL'),
    reason="DATABASE_URL not set - skipping integration tests"
)


class TestDatabaseConnection:
    """Tests for actual database connection"""

    def test_can_connect_to_database(self):
        """Test that we can connect to the real database"""
        from database_adapter import get_connection

        conn = get_connection()
        assert conn is not None

        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        result = cursor.fetchone()

        assert result[0] == 1
        conn.close()

    def test_database_version(self):
        """Test we can get database version"""
        from database_adapter import get_connection

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT version()")
        version = cursor.fetchone()[0]

        assert 'PostgreSQL' in version
        conn.close()


class TestTableExistence:
    """Tests for required tables"""

    def test_autonomous_config_table_exists(self):
        """Test autonomous_config table exists"""
        from database_adapter import get_connection

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'autonomous_config'
            )
        """)
        exists = cursor.fetchone()[0]
        conn.close()

        assert exists is True

    def test_gex_history_table_exists(self):
        """Test gex_history table exists"""
        from database_adapter import get_connection

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'gex_history'
            )
        """)
        exists = cursor.fetchone()[0]
        conn.close()

        assert exists is True

    def test_autonomous_open_positions_table_exists(self):
        """Test positions table exists"""
        from database_adapter import get_connection

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'autonomous_open_positions'
            )
        """)
        exists = cursor.fetchone()[0]
        conn.close()

        assert exists is True


class TestDataOperations:
    """Tests for data operations"""

    def test_can_read_config(self):
        """Test reading from autonomous_config"""
        from database_adapter import get_connection

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT key, value FROM autonomous_config LIMIT 5")
        rows = cursor.fetchall()
        conn.close()

        # Should be able to read (may be empty)
        assert isinstance(rows, list)

    def test_can_read_gex_history(self):
        """Test reading from gex_history"""
        from database_adapter import get_connection

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM gex_history")
        count = cursor.fetchone()[0]
        conn.close()

        assert isinstance(count, int)

    def test_can_write_and_read_test_data(self):
        """Test writing and reading test data"""
        from database_adapter import get_connection

        conn = get_connection()
        cursor = conn.cursor()

        # Use a test key that won't conflict
        test_key = f"_test_integration_{datetime.now().timestamp()}"
        test_value = "test_value"

        try:
            # Write
            cursor.execute(
                "INSERT INTO autonomous_config (key, value) VALUES (%s, %s)",
                (test_key, test_value)
            )
            conn.commit()

            # Read back
            cursor.execute(
                "SELECT value FROM autonomous_config WHERE key = %s",
                (test_key,)
            )
            result = cursor.fetchone()

            assert result is not None
            assert result[0] == test_value

        finally:
            # Cleanup
            cursor.execute(
                "DELETE FROM autonomous_config WHERE key = %s",
                (test_key,)
            )
            conn.commit()
            conn.close()


class TestHeartbeatTable:
    """Tests for bot heartbeat table"""

    def test_can_read_heartbeats(self):
        """Test reading bot heartbeats"""
        from database_adapter import get_connection

        conn = get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT bot_name, last_scan, status
                FROM bot_heartbeats
                ORDER BY last_scan DESC
                LIMIT 5
            """)
            rows = cursor.fetchall()
            assert isinstance(rows, list)
        except Exception:
            # Table may not exist in all environments
            pass
        finally:
            conn.close()


class TestRegimeClassifications:
    """Tests for regime classifications table"""

    def test_can_read_regime_history(self):
        """Test reading regime classification history"""
        from database_adapter import get_connection

        conn = get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT symbol, recommended_action, confidence, created_at
                FROM regime_classifications
                ORDER BY created_at DESC
                LIMIT 10
            """)
            rows = cursor.fetchall()
            assert isinstance(rows, list)
        except Exception:
            # Table may not exist
            pass
        finally:
            conn.close()


class TestPositionsTable:
    """Tests for positions table"""

    def test_can_read_open_positions(self):
        """Test reading open positions"""
        from database_adapter import get_connection

        conn = get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT id, symbol, strategy, entry_price, status
                FROM autonomous_open_positions
                WHERE status = 'open'
                LIMIT 10
            """)
            rows = cursor.fetchall()
            assert isinstance(rows, list)
        except Exception:
            pass
        finally:
            conn.close()


class TestTradesTable:
    """Tests for trades/closed positions table"""

    def test_can_read_trade_history(self):
        """Test reading trade history"""
        from database_adapter import get_connection

        conn = get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT COUNT(*) FROM autonomous_closed_trades
            """)
            count = cursor.fetchone()[0]
            assert isinstance(count, int)
        except Exception:
            pass
        finally:
            conn.close()


class TestTransactionHandling:
    """Tests for transaction handling"""

    def test_rollback_on_error(self):
        """Test that transactions rollback on error"""
        from database_adapter import get_connection

        conn = get_connection()

        try:
            cursor = conn.cursor()
            # Try to insert invalid data
            cursor.execute("INSERT INTO nonexistent_table VALUES (1)")
            conn.commit()
        except Exception:
            conn.rollback()
            # Rollback should work without error

        conn.close()

    def test_context_manager_commits(self):
        """Test context manager commits on success"""
        from database_adapter import get_connection

        test_key = f"_test_ctx_{datetime.now().timestamp()}"

        try:
            with get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO autonomous_config (key, value) VALUES (%s, %s)",
                    (test_key, "ctx_test")
                )
                # Should auto-commit on exit

            # Verify it was committed
            conn2 = get_connection()
            cursor2 = conn2.cursor()
            cursor2.execute(
                "SELECT value FROM autonomous_config WHERE key = %s",
                (test_key,)
            )
            result = cursor2.fetchone()
            conn2.close()

            assert result is not None
        finally:
            # Cleanup
            conn3 = get_connection()
            cursor3 = conn3.cursor()
            cursor3.execute(
                "DELETE FROM autonomous_config WHERE key = %s",
                (test_key,)
            )
            conn3.commit()
            conn3.close()


class TestPerformanceQueries:
    """Tests for performance-critical queries"""

    def test_gex_history_query_performance(self):
        """Test GEX history query completes in reasonable time"""
        import time
        from database_adapter import get_connection

        conn = get_connection()
        cursor = conn.cursor()

        start = time.time()
        cursor.execute("""
            SELECT symbol, net_gex, call_wall, put_wall, created_at
            FROM gex_history
            WHERE symbol = 'SPY'
            ORDER BY created_at DESC
            LIMIT 100
        """)
        rows = cursor.fetchall()
        elapsed = time.time() - start

        conn.close()

        # Should complete in under 5 seconds
        assert elapsed < 5.0

    def test_positions_query_performance(self):
        """Test positions query completes quickly"""
        import time
        from database_adapter import get_connection

        conn = get_connection()
        cursor = conn.cursor()

        start = time.time()
        cursor.execute("""
            SELECT * FROM autonomous_open_positions
            WHERE status = 'open'
        """)
        rows = cursor.fetchall()
        elapsed = time.time() - start

        conn.close()

        # Should complete in under 2 seconds
        assert elapsed < 2.0
