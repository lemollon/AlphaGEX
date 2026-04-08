"""
Database Query Integration Tests

Tests three key database queries against the REAL database:
1. Table count - confirms MCP/DB connection works
2. Open FORTRESS positions - tests a real trading query
3. AGAPE-SPOT weekly P&L - tests a more complex aggregation query

IMPORTANT: These tests require DATABASE_URL environment variable.
Run with: pytest tests/integration/test_database_queries.py -v -s
"""

import pytest
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Skip all tests if no DATABASE_URL
pytestmark = pytest.mark.skipif(
    not os.getenv('DATABASE_URL'),
    reason="DATABASE_URL not set - skipping integration tests"
)


class TestTableCount:
    """Tests: 'How many tables are in my alphagex database?'"""

    def test_count_all_tables(self):
        """Count all tables in the public schema - confirms DB connection works"""
        from database_adapter import get_connection

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE table_schema = 'public'
        """)
        count = cursor.fetchone()[0]
        conn.close()

        print(f"\n{'='*50}")
        print(f"  TOTAL TABLES IN DATABASE: {count}")
        print(f"{'='*50}")

        assert isinstance(count, int)
        assert count > 200, f"Expected 200+ tables (docs say 285+), got {count}"

    def test_list_table_names(self):
        """List table names to verify schema is populated"""
        from database_adapter import get_connection

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name
        """)
        tables = [row[0] for row in cursor.fetchall()]
        conn.close()

        print(f"\n  First 20 tables (of {len(tables)}):")
        for t in tables[:20]:
            print(f"    - {t}")
        print(f"  ... and {max(0, len(tables) - 20)} more")

        assert len(tables) > 0, "No tables found in database"

        # Verify key tables exist
        key_tables = ['fortress_positions', 'agape_spot_positions', 'autonomous_config']
        for table in key_tables:
            assert table in tables, f"Expected table '{table}' not found"


class TestFortressPositions:
    """Tests: 'Show me all open FORTRESS positions'"""

    def test_fortress_table_exists(self):
        """Verify fortress_positions table exists"""
        from database_adapter import get_connection

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name = 'fortress_positions'
            )
        """)
        exists = cursor.fetchone()[0]
        conn.close()

        assert exists is True, "fortress_positions table does not exist"

    def test_fortress_position_columns(self):
        """Verify fortress_positions has expected columns"""
        from database_adapter import get_connection

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'fortress_positions'
            ORDER BY ordinal_position
        """)
        columns = [row[0] for row in cursor.fetchall()]
        conn.close()

        expected_columns = [
            'position_id', 'status', 'put_short_strike', 'call_short_strike',
            'total_credit', 'contracts', 'spread_width', 'open_time'
        ]
        for col in expected_columns:
            assert col in columns, f"Missing column '{col}' in fortress_positions"

    def test_query_open_fortress_positions(self):
        """Query open FORTRESS positions using the exact production SQL"""
        from database_adapter import get_connection

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                position_id, open_time, expiration,
                put_long_strike, put_short_strike,
                call_short_strike, call_long_strike,
                put_credit, call_credit, total_credit,
                contracts, spread_width, max_loss, status,
                underlying_price_at_entry, vix_at_entry,
                COALESCE(ticker, CASE WHEN spread_width <= 5 THEN 'SPY' ELSE 'SPX' END) as ticker
            FROM fortress_positions
            WHERE status = 'open'
            ORDER BY open_time DESC
        """)
        rows = cursor.fetchall()
        conn.close()

        print(f"\n  OPEN FORTRESS POSITIONS: {len(rows)}")
        if rows:
            print(f"  {'ID':<20} {'Ticker':<6} {'Put Short':<10} {'Call Short':<10} {'Credit':<10} {'Contracts':<10} {'Opened'}")
            print(f"  {'-'*90}")
            for row in rows:
                pos_id = row[0] or ''
                opened = str(row[1] or '')[:19]
                put_short = row[4] or 0
                call_short = row[5] or 0
                credit = row[9] or 0
                contracts = row[10] or 0
                ticker = row[16] or '?'
                print(f"  {pos_id:<20} {ticker:<6} {put_short:<10} {call_short:<10} {credit:<10.2f} {contracts:<10} {opened}")
        else:
            print("  (No open positions - market may be closed)")

        assert isinstance(rows, list)


class TestAgapeSpotWeeklyPnL:
    """Tests: 'What's AGAPE-SPOT's P&L this week?'"""

    def test_agape_spot_table_exists(self):
        """Verify agape_spot_positions table exists"""
        from database_adapter import get_connection

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name = 'agape_spot_positions'
            )
        """)
        exists = cursor.fetchone()[0]
        conn.close()

        assert exists is True, "agape_spot_positions table does not exist"

    def test_agape_spot_weekly_pnl(self):
        """Query AGAPE-SPOT P&L for the last 7 days, grouped by ticker"""
        from database_adapter import get_connection

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                ticker,
                COUNT(*) as trade_count,
                COALESCE(SUM(realized_pnl), 0) as total_pnl,
                COUNT(CASE WHEN realized_pnl > 0 THEN 1 END) as wins,
                COUNT(CASE WHEN realized_pnl <= 0 THEN 1 END) as losses
            FROM agape_spot_positions
            WHERE status IN ('closed', 'expired', 'stopped')
              AND close_time >= NOW() - INTERVAL '7 days'
            GROUP BY ticker
            ORDER BY total_pnl DESC
        """)
        rows = cursor.fetchall()

        # Also get the weekly total
        cursor.execute("""
            SELECT
                COUNT(*) as trade_count,
                COALESCE(SUM(realized_pnl), 0) as total_pnl
            FROM agape_spot_positions
            WHERE status IN ('closed', 'expired', 'stopped')
              AND close_time >= NOW() - INTERVAL '7 days'
        """)
        totals = cursor.fetchone()
        conn.close()

        total_trades = totals[0] or 0
        total_pnl = totals[1] or 0

        print(f"\n  AGAPE-SPOT WEEKLY P&L (last 7 days)")
        print(f"  {'='*60}")
        if rows:
            print(f"  {'Ticker':<12} {'Trades':<8} {'P&L':>10} {'Wins':>6} {'Losses':>8} {'Win Rate':>10}")
            print(f"  {'-'*60}")
            for row in rows:
                ticker = row[0] or '?'
                trades = row[1] or 0
                pnl = row[2] or 0
                wins = row[3] or 0
                losses = row[4] or 0
                wr = (wins / trades * 100) if trades > 0 else 0
                print(f"  {ticker:<12} {trades:<8} ${pnl:>9.2f} {wins:>6} {losses:>8} {wr:>9.1f}%")
            print(f"  {'-'*60}")
            print(f"  {'TOTAL':<12} {total_trades:<8} ${total_pnl:>9.2f}")
        else:
            print("  (No closed trades in the last 7 days)")

        assert isinstance(rows, list)

    def test_agape_spot_all_time_pnl(self):
        """Query all-time AGAPE-SPOT P&L as a sanity check"""
        from database_adapter import get_connection

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                ticker,
                COUNT(*) as trade_count,
                COALESCE(SUM(realized_pnl), 0) as total_pnl
            FROM agape_spot_positions
            WHERE status IN ('closed', 'expired', 'stopped')
            GROUP BY ticker
            ORDER BY total_pnl DESC
        """)
        rows = cursor.fetchall()
        conn.close()

        print(f"\n  AGAPE-SPOT ALL-TIME P&L")
        print(f"  {'='*40}")
        if rows:
            for row in rows:
                ticker = row[0] or '?'
                trades = row[1] or 0
                pnl = row[2] or 0
                print(f"  {ticker:<12} {trades:>6} trades  ${pnl:>10.2f}")
        else:
            print("  (No closed trades found)")

        assert isinstance(rows, list)
