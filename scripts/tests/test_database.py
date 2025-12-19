#!/usr/bin/env python3
"""
Database Connectivity and Schema Test Script
Run in Render shell: python scripts/tests/test_database.py
"""

import os
import sys
from datetime import datetime, timedelta

# Add parent directories to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

def print_header(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

def print_result(test_name, passed, details=""):
    status = "PASS" if passed else "FAIL"
    symbol = "✓" if passed else "✗"
    print(f"  {symbol} [{status}] {test_name}")
    if details:
        print(f"           {details}")

def test_database_connection():
    """Test basic database connectivity"""
    print_header("DATABASE CONNECTION TEST")

    try:
        from database_adapter import get_connection, is_database_available

        # Test 1: Check if DATABASE_URL is set
        db_url = os.environ.get('DATABASE_URL')
        print_result("DATABASE_URL environment variable", bool(db_url),
                    f"{'Set' if db_url else 'NOT SET - Required!'}")

        # Test 2: Check database availability
        available = is_database_available()
        print_result("Database availability check", available)

        if not available:
            print("\n  ⚠️  Database not available. Skipping remaining tests.")
            return False

        # Test 3: Get connection
        conn = get_connection()
        print_result("Database connection", conn is not None)

        # Test 4: Execute simple query
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        result = cursor.fetchone()
        print_result("Simple query execution", result == (1,))

        # Test 5: Check PostgreSQL version
        cursor.execute("SELECT version()")
        version = cursor.fetchone()[0]
        print_result("PostgreSQL version", True, version[:50] + "...")

        conn.close()
        return True

    except Exception as e:
        print_result("Database connection", False, str(e))
        return False


def test_schema_tables():
    """Test that all required tables exist"""
    print_header("SCHEMA TABLES TEST")

    required_tables = [
        # Core tables
        'gex_snapshots',
        'vix_data',
        'market_psychology',
        'spx_levels',

        # Trading tables
        'trade_history',
        'positions',
        'bot_trades',
        'wheel_cycles',
        'wheel_legs',

        # AI/ML tables
        'oracle_predictions',
        'oracle_training_outcomes',
        'probability_predictions',
        'probability_outcomes',
        'probability_weights',
        'calibration_history',

        # Analysis tables
        'backtest_results',
        'backtest_trades',
        'conversation_history',
        'recommendations',

        # System tables
        'decision_logs',
        'gamma_levels',
    ]

    try:
        from database_adapter import get_connection
        conn = get_connection()
        cursor = conn.cursor()

        existing_tables = []
        missing_tables = []

        for table in required_tables:
            cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = %s
                )
            """, (table,))
            exists = cursor.fetchone()[0]

            if exists:
                existing_tables.append(table)
            else:
                missing_tables.append(table)

            print_result(f"Table: {table}", exists)

        conn.close()

        print(f"\n  Summary: {len(existing_tables)}/{len(required_tables)} tables exist")
        if missing_tables:
            print(f"  Missing: {', '.join(missing_tables)}")

        return len(missing_tables) == 0

    except Exception as e:
        print_result("Schema tables check", False, str(e))
        return False


def test_probability_system_schema():
    """Test PYTHIA (probability system) schema"""
    print_header("PYTHIA SCHEMA TEST")

    try:
        from database_adapter import get_connection
        conn = get_connection()
        cursor = conn.cursor()

        # Check probability_weights columns
        cursor.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'probability_weights'
        """)
        weight_cols = [row[0] for row in cursor.fetchall()]

        required_weight_cols = ['gex_wall_strength', 'volatility_impact',
                                'psychology_signal', 'mm_positioning',
                                'historical_pattern', 'active', 'calibration_count']

        for col in required_weight_cols:
            exists = col in weight_cols
            print_result(f"probability_weights.{col}", exists)

        # Check for active weights
        cursor.execute("SELECT COUNT(*) FROM probability_weights WHERE active = TRUE")
        active_count = cursor.fetchone()[0]
        print_result("Active weight configuration exists", active_count > 0,
                    f"{active_count} active configuration(s)")

        conn.close()
        return True

    except Exception as e:
        print_result("PYTHIA schema check", False, str(e))
        return False


def test_oracle_schema():
    """Test ORACLE prediction schema"""
    print_header("ORACLE SCHEMA TEST")

    try:
        from database_adapter import get_connection
        conn = get_connection()
        cursor = conn.cursor()

        # Check oracle_predictions columns
        cursor.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'oracle_predictions'
        """)
        pred_cols = [row[0] for row in cursor.fetchall()]

        required_cols = ['bot_name', 'advice', 'win_probability', 'confidence',
                        'reasoning', 'top_factors', 'claude_analysis']

        for col in required_cols:
            exists = col in pred_cols
            print_result(f"oracle_predictions.{col}", exists)

        # Check oracle_training_outcomes
        cursor.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'oracle_training_outcomes'
        """)
        outcome_cols = [row[0] for row in cursor.fetchall()]

        print_result("oracle_training_outcomes table", len(outcome_cols) > 0,
                    f"{len(outcome_cols)} columns")

        # Check prediction count
        cursor.execute("SELECT COUNT(*) FROM oracle_predictions")
        pred_count = cursor.fetchone()[0]
        print_result("Oracle predictions stored", True, f"{pred_count} predictions")

        conn.close()
        return True

    except Exception as e:
        print_result("ORACLE schema check", False, str(e))
        return False


def test_wheel_schema():
    """Test Wheel Strategy schema"""
    print_header("WHEEL STRATEGY SCHEMA TEST")

    try:
        from database_adapter import get_connection
        conn = get_connection()
        cursor = conn.cursor()

        # Check wheel_cycles
        cursor.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'wheel_cycles'
        """)
        cycle_cols = [row[0] for row in cursor.fetchall()]

        required_cycle_cols = ['symbol', 'status', 'start_date', 'total_premium_collected',
                               'realized_pnl', 'total_csp_premium', 'total_cc_premium']

        for col in required_cycle_cols:
            exists = col in cycle_cols
            print_result(f"wheel_cycles.{col}", exists)

        # Check wheel_legs
        cursor.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'wheel_legs'
        """)
        leg_cols = [row[0] for row in cursor.fetchall()]
        print_result("wheel_legs table", len(leg_cols) > 0, f"{len(leg_cols)} columns")

        # Check cycle counts
        cursor.execute("SELECT status, COUNT(*) FROM wheel_cycles GROUP BY status")
        status_counts = cursor.fetchall()
        for status, count in status_counts:
            print_result(f"Wheel cycles ({status})", True, f"{count} cycles")

        conn.close()
        return True

    except Exception as e:
        print_result("Wheel schema check", False, str(e))
        return False


def test_data_integrity():
    """Test data integrity and relationships"""
    print_header("DATA INTEGRITY TEST")

    try:
        from database_adapter import get_connection
        conn = get_connection()
        cursor = conn.cursor()

        # Check GEX data freshness
        cursor.execute("""
            SELECT MAX(timestamp) FROM gex_snapshots
        """)
        latest_gex = cursor.fetchone()[0]
        if latest_gex:
            age = datetime.now(latest_gex.tzinfo) - latest_gex if latest_gex.tzinfo else datetime.now() - latest_gex
            is_fresh = age < timedelta(days=7)
            print_result("GEX data freshness", is_fresh,
                        f"Latest: {latest_gex.strftime('%Y-%m-%d %H:%M') if latest_gex else 'None'}")
        else:
            print_result("GEX data freshness", False, "No GEX data")

        # Check VIX data
        cursor.execute("SELECT COUNT(*) FROM vix_data")
        vix_count = cursor.fetchone()[0]
        print_result("VIX data available", vix_count > 0, f"{vix_count} records")

        # Check decision logs
        cursor.execute("SELECT COUNT(*) FROM decision_logs")
        log_count = cursor.fetchone()[0]
        print_result("Decision logs", True, f"{log_count} logs")

        # Check trade history
        cursor.execute("SELECT COUNT(*) FROM trade_history")
        trade_count = cursor.fetchone()[0]
        print_result("Trade history", True, f"{trade_count} trades")

        # Check conversation history
        cursor.execute("SELECT COUNT(*) FROM conversation_history")
        conv_count = cursor.fetchone()[0]
        print_result("Conversation history", True, f"{conv_count} conversations")

        conn.close()
        return True

    except Exception as e:
        print_result("Data integrity check", False, str(e))
        return False


def main():
    """Run all database tests"""
    print("\n" + "="*60)
    print("  ALPHAGEX DATABASE TEST SUITE")
    print("  " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("="*60)

    results = {
        "connection": test_database_connection(),
        "schema": test_schema_tables(),
        "pythia": test_probability_system_schema(),
        "oracle": test_oracle_schema(),
        "wheel": test_wheel_schema(),
        "integrity": test_data_integrity(),
    }

    # Summary
    print_header("TEST SUMMARY")
    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for test_name, result in results.items():
        print_result(test_name.upper(), result)

    print(f"\n  Overall: {passed}/{total} test groups passed")

    if passed == total:
        print("\n  ✅ All database tests passed!")
        return 0
    else:
        print("\n  ⚠️  Some tests failed. Check above for details.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
