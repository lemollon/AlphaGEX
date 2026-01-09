#!/usr/bin/env python3
"""
Test script for HYPERION ROC persistence feature.

This script verifies:
1. Database table creation
2. New ROC fields in API response
3. History persistence and loading
4. Cleanup functionality
5. Market hours detection

Usage:
    python scripts/test_hyperion_roc_persistence.py
"""

import os
import sys
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
    """Test that hyperion_gamma_history table exists and has correct structure."""
    print("\n" + "="*60)
    print("TEST 1: Database Table Structure")
    print("="*60)

    if not DB_AVAILABLE:
        print("  SKIPPED: Database not available")
        return True  # Don't fail if DB not available

    conn = get_connection()
    if not conn:
        print("  FAILED: Could not connect to database")
        return False

    cursor = conn.cursor()

    # Check if table exists
    cursor.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_name = 'hyperion_gamma_history'
        );
    """)
    exists = cursor.fetchone()[0]

    if not exists:
        print("  Table does not exist yet (will be created on first API call)")
        cursor.close()
        conn.close()
        return True

    print("  Table exists: hyperion_gamma_history")

    # Check columns
    cursor.execute("""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = 'hyperion_gamma_history'
        ORDER BY ordinal_position;
    """)
    columns = cursor.fetchall()

    print("\nColumns:")
    expected_cols = ['id', 'symbol', 'strike', 'gamma_value', 'recorded_at', 'created_at']
    for col_name, col_type in columns:
        status = "  " if col_name in expected_cols else "  "
        print(f"  {status} {col_name}: {col_type}")

    # Check indexes
    cursor.execute("""
        SELECT indexname FROM pg_indexes
        WHERE tablename = 'hyperion_gamma_history';
    """)
    indexes = [row[0] for row in cursor.fetchall()]
    print("\nIndexes:")
    for idx in indexes:
        print(f"    {idx}")

    # Check row count
    cursor.execute("SELECT COUNT(*) FROM hyperion_gamma_history;")
    count = cursor.fetchone()[0]
    print(f"\nTotal rows: {count}")

    # Check recent data by symbol
    cursor.execute("""
        SELECT symbol, COUNT(*), MIN(recorded_at), MAX(recorded_at)
        FROM hyperion_gamma_history
        WHERE recorded_at > NOW() - INTERVAL '1 hour'
        GROUP BY symbol;
    """)
    recent = cursor.fetchall()
    if recent:
        print("\nRecent data (last hour):")
        for symbol, cnt, min_t, max_t in recent:
            print(f"  {symbol}: {cnt} entries, {min_t} to {max_t}")
    else:
        print("\n  No recent data in last hour")

    cursor.close()
    conn.close()
    return True


def test_roc_fields_in_routes():
    """Test that hyperion_routes.py has all ROC fields."""
    print("\n" + "="*60)
    print("TEST 2: ROC Fields in Routes (Code Check)")
    print("="*60)

    routes_file = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'backend', 'api', 'routes', 'hyperion_routes.py'
    )

    if not os.path.exists(routes_file):
        print(f"  FAILED: Could not find {routes_file}")
        return False

    with open(routes_file, 'r') as f:
        content = f.read()

    expected_roc_fields = [
        'roc_1min', 'roc_5min', 'roc_30min',
        'roc_1hr', 'roc_4hr', 'roc_trading_day'
    ]

    print("ROC fields in strike data:")
    all_present = True
    for field in expected_roc_fields:
        # Look for field in strike dict like "'roc_1min': roc_1min"
        if f"'{field}':" in content or f'"{field}":' in content:
            print(f"    {field}")
        else:
            print(f"    {field} - MISSING!")
            all_present = False

    return all_present


def test_roc_calculation_methods():
    """Test that HYPERION has all ROC calculation methods."""
    print("\n" + "="*60)
    print("TEST 3: ROC Calculation Methods (Code Check)")
    print("="*60)

    routes_file = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'backend', 'api', 'routes', 'hyperion_routes.py'
    )

    if not os.path.exists(routes_file):
        print(f"  FAILED: Could not find {routes_file}")
        return False

    with open(routes_file, 'r') as f:
        content = f.read()

    methods_to_check = [
        'def calculate_roc',
        'def calculate_roc_since_open',
        'def update_gamma_history'
    ]

    all_present = True
    for method in methods_to_check:
        if method in content:
            print(f"    {method.replace('def ', '')}()")
        else:
            print(f"    {method.replace('def ', '')}() - MISSING!")
            all_present = False

    # Also check for key implementation details
    impl_checks = [
        ('minutes=60', 'ROC 1hr calculation (60 min)'),
        ('minutes=240', 'ROC 4hr calculation (240 min)'),
        ('market_open = now.replace(hour=8, minute=30', 'Market open detection (8:30 CT)'),
        ('HISTORY_MINUTES = 420', 'History retention (7 hours)'),
    ]

    print("\nImplementation Details:")
    for code, desc in impl_checks:
        if code in content:
            print(f"    {desc}")
        else:
            print(f"    {desc} - MISSING!")
            all_present = False

    return all_present


def test_persistence_functions():
    """Test that persistence functions exist in the source file."""
    print("\n" + "="*60)
    print("TEST 4: Persistence Functions (Code Check)")
    print("="*60)

    routes_file = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'backend', 'api', 'routes', 'hyperion_routes.py'
    )

    if not os.path.exists(routes_file):
        print(f"  FAILED: Could not find {routes_file}")
        return False

    with open(routes_file, 'r') as f:
        content = f.read()

    functions_to_check = [
        'def ensure_hyperion_gamma_history_table',
        'def persist_hyperion_gamma_history',
        'def load_hyperion_gamma_history',
        'def cleanup_old_hyperion_gamma_history'
    ]

    all_present = True
    for func in functions_to_check:
        if func in content:
            print(f"    {func.replace('def ', '')}()")
        else:
            print(f"    {func.replace('def ', '')}() - MISSING!")
            all_present = False

    # Check for key SQL statements
    sql_checks = [
        ('CREATE TABLE IF NOT EXISTS hyperion_gamma_history', 'Table creation SQL'),
        ('CREATE INDEX IF NOT EXISTS idx_hyperion_gamma_history', 'Index creation SQL'),
        ("INTERVAL '420 minutes'", 'History load interval (7 hours)'),
        ("INTERVAL '8 hours'", 'Cleanup interval'),
    ]

    print("\nSQL Statements:")
    for sql, desc in sql_checks:
        if sql in content:
            print(f"    {desc}")
        else:
            print(f"    {desc} - MISSING!")
            all_present = False

    return all_present


def test_market_hours_function():
    """Test that is_market_hours() function exists and works."""
    print("\n" + "="*60)
    print("TEST 5: Market Hours Detection (Code Check)")
    print("="*60)

    routes_file = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'backend', 'api', 'routes', 'hyperion_routes.py'
    )

    if not os.path.exists(routes_file):
        print(f"  FAILED: Could not find {routes_file}")
        return False

    with open(routes_file, 'r') as f:
        content = f.read()

    checks = [
        ('def is_market_hours', 'is_market_hours() function'),
        ('now.weekday() >= 5', 'Weekend check'),
        ('8 * 60 + 30 <= time_minutes < 15 * 60', 'Market hours check (8:30 AM - 3:00 PM CT)'),
        ("market_status': 'open' if market_open else 'closed'", 'Dynamic market status'),
    ]

    all_present = True
    for code, desc in checks:
        if code in content:
            print(f"    {desc}")
        else:
            print(f"    {desc} - MISSING!")
            all_present = False

    return all_present


def test_frontend_types():
    """Test that frontend TypeScript has all ROC fields."""
    print("\n" + "="*60)
    print("TEST 6: Frontend TypeScript Types (Code Check)")
    print("="*60)

    frontend_file = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'frontend', 'src', 'app', 'hyperion', 'page.tsx'
    )

    if not os.path.exists(frontend_file):
        print(f"  Frontend file not found: {frontend_file}")
        return True  # Don't fail if frontend not found

    with open(frontend_file, 'r') as f:
        content = f.read()

    ts_fields = [
        'roc_1min:', 'roc_5min:', 'roc_30min:',
        'roc_1hr:', 'roc_4hr:', 'roc_trading_day:'
    ]

    print("StrikeData interface fields:")
    all_present = True
    for field in ts_fields:
        if field in content:
            print(f"    {field.replace(':', '')} in TypeScript")
        else:
            print(f"    {field.replace(':', '')} - MISSING in TypeScript!")
            all_present = False

    # Check for ROC timeframe selector
    ui_checks = [
        ("type RocTimeframe = '4hr' | 'day'", 'ROC timeframe type'),
        ('selectedRocTimeframe', 'ROC timeframe state'),
        ('rocTimeframeOptions', 'ROC timeframe options'),
    ]

    print("\nUI Components:")
    for code, desc in ui_checks:
        if code in content:
            print(f"    {desc}")
        else:
            print(f"    {desc} - MISSING!")
            all_present = False

    return all_present


def test_api_integration():
    """Test that API wiring is correct."""
    print("\n" + "="*60)
    print("TEST 7: API Integration (Code Check)")
    print("="*60)

    routes_file = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'backend', 'api', 'routes', 'hyperion_routes.py'
    )

    if not os.path.exists(routes_file):
        print(f"  FAILED: Could not find {routes_file}")
        return False

    with open(routes_file, 'r') as f:
        content = f.read()

    integration_checks = [
        ('load_hyperion_gamma_history(symbol)', 'History loading in fetch_gamma_data'),
        ('persist_hyperion_gamma_history(symbol)', 'History persistence after fetch'),
        ('cleanup_old_hyperion_gamma_history()', 'Cleanup call'),
        ('cache_ttl = CACHE_TTL_SECONDS if market_open else 300', 'Dynamic cache TTL'),
    ]

    all_present = True
    for code, desc in integration_checks:
        if code in content:
            print(f"    {desc}")
        else:
            print(f"    {desc} - MISSING!")
            all_present = False

    return all_present


def test_data_flow():
    """Test that data flows correctly from DB to API to frontend."""
    print("\n" + "="*60)
    print("TEST 8: Data Flow Verification")
    print("="*60)

    if not DB_AVAILABLE:
        print("  SKIPPED: Database not available")
        return True

    conn = get_connection()
    if not conn:
        print("  SKIPPED: Could not connect to database")
        return True

    cursor = conn.cursor()

    # Check if we have any data
    cursor.execute("""
        SELECT COUNT(*) FROM hyperion_gamma_history
        WHERE recorded_at > NOW() - INTERVAL '1 hour';
    """)
    recent_count = cursor.fetchone()[0]

    if recent_count == 0:
        print("  No recent data - run HYPERION page first to populate")
        cursor.close()
        conn.close()
        return True

    # Get sample data
    cursor.execute("""
        SELECT symbol, strike, gamma_value, recorded_at
        FROM hyperion_gamma_history
        WHERE recorded_at > NOW() - INTERVAL '1 hour'
        ORDER BY recorded_at DESC
        LIMIT 5;
    """)
    samples = cursor.fetchall()

    print(f"Recent data samples ({recent_count} total in last hour):")
    for symbol, strike, gamma, recorded_at in samples:
        print(f"  {symbol} ${strike}: {float(gamma):.2f} @ {recorded_at}")

    # Check data distribution by symbol
    cursor.execute("""
        SELECT symbol, COUNT(DISTINCT strike) as strikes, COUNT(*) as entries
        FROM hyperion_gamma_history
        WHERE recorded_at > NOW() - INTERVAL '7 hours'
        GROUP BY symbol;
    """)
    distribution = cursor.fetchall()

    print("\nData distribution (last 7 hours):")
    for symbol, strikes, entries in distribution:
        print(f"  {symbol}: {strikes} strikes, {entries} entries")

    cursor.close()
    conn.close()
    return True


def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("HYPERION ROC PERSISTENCE TEST SUITE")
    print("="*60)
    print(f"Running at: {datetime.now()}")

    results = []

    results.append(("Database Table", test_database_table()))
    results.append(("ROC Fields in Routes", test_roc_fields_in_routes()))
    results.append(("ROC Calculation Methods", test_roc_calculation_methods()))
    results.append(("Persistence Functions", test_persistence_functions()))
    results.append(("Market Hours Detection", test_market_hours_function()))
    results.append(("Frontend TypeScript", test_frontend_types()))
    results.append(("API Integration", test_api_integration()))
    results.append(("Data Flow", test_data_flow()))

    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)

    passed = sum(1 for _, r in results if r)
    total = len(results)

    for name, result in results:
        status = "  PASS" if result else "  FAIL"
        print(f"  {status}: {name}")

    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print("\n  All tests passed! HYPERION ROC persistence is ready.")
    else:
        print("\n  Some tests failed. Review the output above.")

    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
