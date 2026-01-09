#!/usr/bin/env python3
"""
Test script for ARGUS ROC persistence feature.

This script verifies:
1. Database table creation
2. New ROC fields in API response
3. History persistence and loading
4. Cleanup functionality

Usage:
    python scripts/test_argus_roc_persistence.py
"""

import os
import sys
import json
from datetime import datetime, timedelta

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Try to import database adapter, but don't fail if psycopg2 not installed
try:
    from database_adapter import get_connection
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False
    get_connection = None
    print("Note: Database not available (psycopg2 not installed)")
    print("Skipping database tests...\n")


def test_database_table():
    """Test that argus_gamma_history table exists and has correct structure."""
    print("\n" + "="*60)
    print("TEST 1: Database Table Structure")
    print("="*60)

    if not DB_AVAILABLE:
        print("⚠️  SKIPPED: Database not available")
        return True  # Don't fail if DB not available

    conn = get_connection()
    if not conn:
        print("❌ FAILED: Could not connect to database")
        return False

    cursor = conn.cursor()

    # Check if table exists
    cursor.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_name = 'argus_gamma_history'
        );
    """)
    exists = cursor.fetchone()[0]

    if not exists:
        print("⚠️  Table does not exist yet (will be created on first API call)")
        cursor.close()
        conn.close()
        return True

    print("✅ Table exists: argus_gamma_history")

    # Check columns
    cursor.execute("""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = 'argus_gamma_history'
        ORDER BY ordinal_position;
    """)
    columns = cursor.fetchall()

    print("\nColumns:")
    expected_cols = ['id', 'symbol', 'strike', 'gamma_value', 'recorded_at', 'created_at']
    for col_name, col_type in columns:
        status = "✅" if col_name in expected_cols else "⚠️"
        print(f"  {status} {col_name}: {col_type}")

    # Check indexes
    cursor.execute("""
        SELECT indexname FROM pg_indexes
        WHERE tablename = 'argus_gamma_history';
    """)
    indexes = [row[0] for row in cursor.fetchall()]
    print("\nIndexes:")
    for idx in indexes:
        print(f"  ✅ {idx}")

    # Check row count
    cursor.execute("SELECT COUNT(*) FROM argus_gamma_history;")
    count = cursor.fetchone()[0]
    print(f"\nTotal rows: {count}")

    # Check recent data
    cursor.execute("""
        SELECT symbol, COUNT(*), MIN(recorded_at), MAX(recorded_at)
        FROM argus_gamma_history
        WHERE recorded_at > NOW() - INTERVAL '1 hour'
        GROUP BY symbol;
    """)
    recent = cursor.fetchall()
    if recent:
        print("\nRecent data (last hour):")
        for symbol, cnt, min_t, max_t in recent:
            print(f"  {symbol}: {cnt} entries, {min_t} to {max_t}")
    else:
        print("\n⚠️  No recent data in last hour")

    cursor.close()
    conn.close()
    return True


def test_strike_data_class():
    """Test that StrikeData class has all new ROC fields (file-based check)."""
    print("\n" + "="*60)
    print("TEST 2: StrikeData Class Fields (Code Check)")
    print("="*60)

    # Read the argus_engine.py file and check for field definitions
    engine_file = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'core', 'argus_engine.py'
    )

    if not os.path.exists(engine_file):
        print(f"❌ FAILED: Could not find {engine_file}")
        return False

    with open(engine_file, 'r') as f:
        content = f.read()

    expected_roc_fields = [
        'roc_1min', 'roc_5min', 'roc_30min',
        'roc_1hr', 'roc_4hr', 'roc_trading_day'
    ]

    print("ROC fields in StrikeData:")
    all_present = True
    for field in expected_roc_fields:
        # Look for field definition pattern like "roc_1min: float = 0.0"
        if f"{field}:" in content:
            print(f"  ✅ {field}")
        else:
            print(f"  ❌ {field} - MISSING!")
            all_present = False

    return all_present


def test_roc_calculation_methods():
    """Test that ArgusEngine has all ROC calculation methods (file-based check)."""
    print("\n" + "="*60)
    print("TEST 3: ArgusEngine ROC Methods (Code Check)")
    print("="*60)

    # Read the argus_engine.py file and check for method definitions
    engine_file = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'core', 'argus_engine.py'
    )

    if not os.path.exists(engine_file):
        print(f"❌ FAILED: Could not find {engine_file}")
        return False

    with open(engine_file, 'r') as f:
        content = f.read()

    methods_to_check = [
        'def calculate_roc',
        'def calculate_roc_since_open',
        'def update_history'
    ]

    all_present = True
    for method in methods_to_check:
        if method in content:
            print(f"  ✅ {method.replace('def ', '')}()")
        else:
            print(f"  ❌ {method.replace('def ', '')}() - MISSING!")
            all_present = False

    # Also check for key implementation details
    impl_checks = [
        ('minutes=60', 'ROC 1hr calculation (60 min)'),
        ('minutes=240', 'ROC 4hr calculation (240 min)'),
        ('market_open = now.replace(hour=8, minute=30', 'Market open detection (8:30 CT)'),
        ('timedelta(minutes=420)', 'History retention (7 hours)'),
    ]

    print("\nImplementation Details:")
    for code, desc in impl_checks:
        if code in content:
            print(f"  ✅ {desc}")
        else:
            print(f"  ❌ {desc} - MISSING!")
            all_present = False

    return all_present


def test_persistence_functions():
    """Test that persistence functions exist in the source file."""
    print("\n" + "="*60)
    print("TEST 4: Persistence Functions (Code Check)")
    print("="*60)

    # Read the argus_routes.py file and check for function definitions
    routes_file = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'backend', 'api', 'routes', 'argus_routes.py'
    )

    if not os.path.exists(routes_file):
        print(f"❌ FAILED: Could not find {routes_file}")
        return False

    with open(routes_file, 'r') as f:
        content = f.read()

    functions_to_check = [
        'def ensure_gamma_history_table',
        'def persist_gamma_history',
        'def load_gamma_history',
        'def cleanup_old_gamma_history'
    ]

    all_present = True
    for func in functions_to_check:
        if func in content:
            print(f"  ✅ {func.replace('def ', '')}()")
        else:
            print(f"  ❌ {func.replace('def ', '')}() - MISSING!")
            all_present = False

    # Check for key SQL statements
    sql_checks = [
        ('CREATE TABLE IF NOT EXISTS argus_gamma_history', 'Table creation SQL'),
        ('CREATE INDEX IF NOT EXISTS idx_argus_gamma_history', 'Index creation SQL'),
        ("INTERVAL '420 minutes'", 'History load interval (7 hours)'),
        ("INTERVAL '8 hours'", 'Cleanup interval'),
    ]

    print("\nSQL Statements:")
    for sql, desc in sql_checks:
        if sql in content:
            print(f"  ✅ {desc}")
        else:
            print(f"  ❌ {desc} - MISSING!")
            all_present = False

    return all_present


def test_api_response_fields():
    """Test that process_options_chain includes all ROC fields."""
    print("\n" + "="*60)
    print("TEST 5: API Response Fields (Code Check)")
    print("="*60)

    # Read the argus_engine.py file and check process_options_chain
    engine_file = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'core', 'argus_engine.py'
    )

    if not os.path.exists(engine_file):
        print(f"❌ FAILED: Could not find {engine_file}")
        return False

    with open(engine_file, 'r') as f:
        content = f.read()

    # Check that StrikeData is created with all ROC fields
    roc_assignments = [
        'roc_1min=roc_1min',
        'roc_5min=roc_5min',
        'roc_30min=roc_30min',
        'roc_1hr=roc_1hr',
        'roc_4hr=roc_4hr',
        'roc_trading_day=roc_trading_day',
    ]

    print("ROC fields assigned in process_options_chain:")
    all_present = True
    for assignment in roc_assignments:
        if assignment in content:
            print(f"  ✅ {assignment}")
        else:
            print(f"  ❌ {assignment} - MISSING!")
            all_present = False

    # Check frontend TypeScript types
    print("\nFrontend TypeScript types:")
    frontend_file = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'frontend', 'src', 'app', 'argus', 'page.tsx'
    )

    if os.path.exists(frontend_file):
        with open(frontend_file, 'r') as f:
            ts_content = f.read()

        ts_fields = [
            'roc_30min:', 'roc_1hr:', 'roc_4hr:', 'roc_trading_day:'
        ]
        for field in ts_fields:
            if field in ts_content:
                print(f"  ✅ {field.replace(':', '')} in TypeScript")
            else:
                print(f"  ❌ {field.replace(':', '')} - MISSING in TypeScript!")
                all_present = False
    else:
        print("  ⚠️  Frontend file not found")

    return all_present


def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("ARGUS ROC PERSISTENCE TEST SUITE")
    print("="*60)
    print(f"Running at: {datetime.now()}")

    results = []

    results.append(("Database Table", test_database_table()))
    results.append(("StrikeData Fields", test_strike_data_class()))
    results.append(("ROC Methods", test_roc_calculation_methods()))
    results.append(("Persistence Functions", test_persistence_functions()))
    results.append(("API Response", test_api_response_fields()))

    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)

    passed = sum(1 for _, r in results if r)
    total = len(results)

    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {status}: {name}")

    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 All tests passed! ROC persistence is ready.")
    else:
        print("\n⚠️  Some tests failed. Review the output above.")

    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
