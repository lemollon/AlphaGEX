#!/usr/bin/env python
"""
JUBILEE Database Verification Script for Render Shell

Run this script in the Render shell to verify all JUBILEE database tables and data:
    python scripts/test_jubilee_db.py

This verifies:
1. All 14 required tables exist
2. All 7 indexes exist
3. Table schemas are correct
4. Foreign keys are valid
5. Sample data queries work
"""

import os
import sys

# Add project root to Python path for Render shell
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from datetime import datetime
from typing import Dict, List, Tuple, Any

# ANSI colors for output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'
BOLD = '\033[1m'


def print_header(text: str):
    print(f"\n{BOLD}{BLUE}{'=' * 60}{RESET}")
    print(f"{BOLD}{BLUE}{text}{RESET}")
    print(f"{BOLD}{BLUE}{'=' * 60}{RESET}\n")


def print_result(name: str, success: bool, message: str = ""):
    icon = f"{GREEN}✓{RESET}" if success else f"{RED}✗{RESET}"
    msg = f" - {message}" if message else ""
    print(f"  {icon} {name}{msg}")


# Required tables for JUBILEE
REQUIRED_TABLES = [
    # Box Spread tables
    'jubilee_positions',
    'jubilee_signals',
    'prometheus_capital_deployments',
    'prometheus_rate_analysis',
    'jubilee_daily_briefings',
    'prometheus_roll_decisions',
    'jubilee_config',
    'jubilee_logs',
    'jubilee_equity_snapshots',
    # IC Trading tables
    'jubilee_ic_positions',
    'prometheus_ic_closed_trades',
    'jubilee_ic_signals',
    'jubilee_ic_config',
    'jubilee_ic_equity_snapshots',
]

# Required indexes
REQUIRED_INDEXES = [
    'idx_jubilee_ic_positions_status',
    'idx_jubilee_ic_positions_open_time',
    'idx_prometheus_ic_closed_trades_close_time',
    'idx_jubilee_ic_signals_time',
    'idx_jubilee_ic_signals_executed',
    'idx_jubilee_ic_equity_snapshots_time',
    'idx_jubilee_logs_action',
]

# Key columns to verify per table
TABLE_COLUMNS = {
    'jubilee_positions': [
        'position_id', 'ticker', 'lower_strike', 'upper_strike', 'expiration',
        'total_credit_received', 'implied_annual_rate', 'status', 'open_time'
    ],
    'jubilee_ic_positions': [
        'position_id', 'ticker', 'put_short_strike', 'call_short_strike',
        'expiration', 'total_credit_received', 'unrealized_pnl', 'status', 'open_time'
    ],
    'prometheus_ic_closed_trades': [
        'position_id', 'ticker', 'realized_pnl', 'open_time', 'close_time', 'close_reason'
    ],
    'jubilee_ic_equity_snapshots': [
        'snapshot_time', 'total_equity', 'starting_capital', 'total_realized_pnl',
        'total_unrealized_pnl', 'open_position_count'
    ],
    'jubilee_logs': [
        'log_time', 'level', 'action', 'message', 'details'
    ],
}


def get_connection():
    """Get database connection."""
    try:
        from database_adapter import get_connection
        return get_connection()
    except ImportError:
        print(f"{RED}ERROR: database_adapter not available{RESET}")
        print("Make sure you're running this from the AlphaGEX root directory")
        sys.exit(1)


def check_tables_exist(conn) -> Tuple[int, int, List[str]]:
    """Check if all required tables exist."""
    cursor = conn.cursor()
    passed = 0
    failed = 0
    failed_tables = []

    print_header("TABLE EXISTENCE CHECK")

    for table in REQUIRED_TABLES:
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = %s
            )
        """, (table,))
        exists = cursor.fetchone()[0]

        if exists:
            # Get row count
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            print_result(table, True, f"rows={count}")
            passed += 1
        else:
            print_result(table, False, "TABLE MISSING")
            failed += 1
            failed_tables.append(table)

    cursor.close()
    return passed, failed, failed_tables


def check_indexes_exist(conn) -> Tuple[int, int, List[str]]:
    """Check if all required indexes exist."""
    cursor = conn.cursor()
    passed = 0
    failed = 0
    failed_indexes = []

    print_header("INDEX EXISTENCE CHECK")

    for index in REQUIRED_INDEXES:
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM pg_indexes
                WHERE indexname = %s
            )
        """, (index,))
        exists = cursor.fetchone()[0]

        if exists:
            print_result(index, True)
            passed += 1
        else:
            print_result(index, False, "INDEX MISSING")
            failed += 1
            failed_indexes.append(index)

    cursor.close()
    return passed, failed, failed_indexes


def check_table_columns(conn) -> Tuple[int, int, List[str]]:
    """Check if required columns exist in key tables."""
    cursor = conn.cursor()
    passed = 0
    failed = 0
    failed_columns = []

    print_header("COLUMN EXISTENCE CHECK")

    for table, columns in TABLE_COLUMNS.items():
        # First check if table exists
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = %s
            )
        """, (table,))
        if not cursor.fetchone()[0]:
            print_result(f"{table}.*", False, "table doesn't exist")
            failed += len(columns)
            for col in columns:
                failed_columns.append(f"{table}.{col}")
            continue

        # Check each column
        for column in columns:
            cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.columns
                    WHERE table_name = %s AND column_name = %s
                )
            """, (table, column))
            exists = cursor.fetchone()[0]

            if exists:
                print_result(f"{table}.{column}", True)
                passed += 1
            else:
                print_result(f"{table}.{column}", False, "COLUMN MISSING")
                failed += 1
                failed_columns.append(f"{table}.{column}")

    cursor.close()
    return passed, failed, failed_columns


def check_data_queries(conn) -> Tuple[int, int, List[str]]:
    """Test key data queries."""
    cursor = conn.cursor()
    passed = 0
    failed = 0
    failed_queries = []

    print_header("DATA QUERY CHECK")

    queries = [
        ("Get open box positions", """
            SELECT COUNT(*) FROM jubilee_positions WHERE status = 'open'
        """),
        ("Get closed box positions", """
            SELECT COUNT(*) FROM jubilee_positions WHERE status = 'closed'
        """),
        ("Get open IC positions", """
            SELECT COUNT(*) FROM jubilee_ic_positions WHERE status IN ('open', 'pending')
        """),
        ("Get IC closed trades", """
            SELECT COUNT(*) FROM prometheus_ic_closed_trades
        """),
        ("Get IC performance stats", """
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as winners,
                SUM(realized_pnl) as total_pnl
            FROM prometheus_ic_closed_trades
        """),
        ("Get today's IC equity snapshots", """
            SELECT COUNT(*) FROM jubilee_ic_equity_snapshots
            WHERE DATE(snapshot_time AT TIME ZONE 'America/Chicago') =
                  DATE(NOW() AT TIME ZONE 'America/Chicago')
        """),
        ("Get recent IC signals", """
            SELECT COUNT(*) FROM jubilee_ic_signals
            WHERE signal_time > NOW() - INTERVAL '7 days'
        """),
        ("Get IC logs with action filter", """
            SELECT COUNT(*) FROM jubilee_logs
            WHERE action LIKE 'IC_%'
        """),
        ("Get box spread config", """
            SELECT COUNT(*) FROM jubilee_config
        """),
        ("Get IC config", """
            SELECT COUNT(*) FROM jubilee_ic_config
        """),
    ]

    for name, query in queries:
        try:
            cursor.execute(query)
            result = cursor.fetchone()
            value = result[0] if result else 0
            print_result(name, True, f"result={value}")
            passed += 1
        except Exception as e:
            print_result(name, False, str(e)[:50])
            failed += 1
            failed_queries.append(name)

    cursor.close()
    return passed, failed, failed_queries


def check_foreign_keys(conn) -> Tuple[int, int, List[str]]:
    """Check data consistency (foreign key-like relationships)."""
    cursor = conn.cursor()
    passed = 0
    failed = 0
    failed_checks = []

    print_header("DATA CONSISTENCY CHECK")

    checks = [
        ("IC positions reference valid box positions", """
            SELECT COUNT(*) FROM jubilee_ic_positions p
            WHERE p.source_box_position_id IS NOT NULL
            AND NOT EXISTS (
                SELECT 1 FROM jubilee_positions bp
                WHERE bp.position_id = p.source_box_position_id
            )
        """, 0),  # Should be 0 orphaned records
        ("IC closed trades have valid times", """
            SELECT COUNT(*) FROM prometheus_ic_closed_trades
            WHERE close_time < open_time
        """, 0),  # Should be 0 invalid times
        ("IC signals reference valid positions", """
            SELECT COUNT(*) FROM jubilee_ic_signals s
            WHERE s.executed_position_id IS NOT NULL
            AND s.was_executed = TRUE
            AND NOT EXISTS (
                SELECT 1 FROM jubilee_ic_positions p
                WHERE p.position_id = s.executed_position_id
            )
            AND NOT EXISTS (
                SELECT 1 FROM prometheus_ic_closed_trades t
                WHERE t.position_id = s.executed_position_id
            )
        """, 0),  # Should be 0 orphaned references
    ]

    for name, query, expected in checks:
        try:
            cursor.execute(query)
            result = cursor.fetchone()[0]
            success = result == expected
            print_result(name, success, f"orphaned={result}" if not success else "OK")
            if success:
                passed += 1
            else:
                failed += 1
                failed_checks.append(name)
        except Exception as e:
            print_result(name, False, str(e)[:50])
            failed += 1
            failed_checks.append(name)

    cursor.close()
    return passed, failed, failed_checks


def check_jubilee_config(conn) -> Tuple[int, int, List[str]]:
    """Verify JUBILEE configurations are properly stored."""
    cursor = conn.cursor()
    passed = 0
    failed = 0
    failed_configs = []

    print_header("CONFIGURATION CHECK")

    # Check box spread config
    try:
        cursor.execute("""
            SELECT config_data FROM jubilee_config WHERE config_key = 'default'
        """)
        row = cursor.fetchone()
        if row and row[0]:
            config = row[0]
            required_fields = ['mode', 'ticker', 'strike_width', 'starting_capital']
            missing = [f for f in required_fields if f not in config]
            if not missing:
                print_result("Box spread config", True, f"fields={len(config)}")
                passed += 1
            else:
                print_result("Box spread config", False, f"missing: {missing}")
                failed += 1
                failed_configs.append("Box spread config")
        else:
            print_result("Box spread config", True, "not set (will use defaults)")
            passed += 1
    except Exception as e:
        print_result("Box spread config", False, str(e)[:50])
        failed += 1
        failed_configs.append("Box spread config")

    # Check IC config
    try:
        cursor.execute("""
            SELECT config_data FROM jubilee_ic_config WHERE config_key = 'default'
        """)
        row = cursor.fetchone()
        if row and row[0]:
            config = row[0]
            required_fields = ['enabled', 'mode', 'ticker']
            missing = [f for f in required_fields if f not in config]
            if not missing:
                print_result("IC trading config", True, f"fields={len(config)}")
                passed += 1
            else:
                print_result("IC trading config", False, f"missing: {missing}")
                failed += 1
                failed_configs.append("IC trading config")
        else:
            print_result("IC trading config", True, "not set (will use defaults)")
            passed += 1
    except Exception as e:
        print_result("IC trading config", False, str(e)[:50])
        failed += 1
        failed_configs.append("IC trading config")

    cursor.close()
    return passed, failed, failed_configs


def main():
    """Main entry point."""
    print(f"\n{BOLD}JUBILEE Database Verification Script{RESET}")
    print(f"Timestamp: {datetime.now().isoformat()}")

    # Get connection
    print_header("DATABASE CONNECTION")
    try:
        conn = get_connection()
        print_result("Database connection", True)
    except Exception as e:
        print(f"{RED}ERROR: Cannot connect to database{RESET}")
        print(f"Error: {e}")
        sys.exit(1)

    # Run all checks
    total_passed = 0
    total_failed = 0
    all_failures = []

    # Check tables
    passed, failed, failures = check_tables_exist(conn)
    total_passed += passed
    total_failed += failed
    all_failures.extend(failures)

    # Check indexes
    passed, failed, failures = check_indexes_exist(conn)
    total_passed += passed
    total_failed += failed
    all_failures.extend(failures)

    # Check columns
    passed, failed, failures = check_table_columns(conn)
    total_passed += passed
    total_failed += failed
    all_failures.extend(failures)

    # Check data queries
    passed, failed, failures = check_data_queries(conn)
    total_passed += passed
    total_failed += failed
    all_failures.extend(failures)

    # Check consistency
    passed, failed, failures = check_foreign_keys(conn)
    total_passed += passed
    total_failed += failed
    all_failures.extend(failures)

    # Check configs
    passed, failed, failures = check_jubilee_config(conn)
    total_passed += passed
    total_failed += failed
    all_failures.extend(failures)

    # Summary
    print_header("VERIFICATION SUMMARY")
    total = total_passed + total_failed
    print(f"  Total checks: {total}")
    print(f"  {GREEN}Passed: {total_passed}{RESET}")
    print(f"  {RED}Failed: {total_failed}{RESET}")

    if all_failures:
        print(f"\n{YELLOW}Failures:{RESET}")
        for f in all_failures:
            print(f"  - {f}")

    success_rate = (total_passed / total * 100) if total > 0 else 0
    print(f"\n  Success rate: {success_rate:.1f}%")

    # Exit code
    if total_failed > 0:
        print(f"\n{RED}Database verification failed!{RESET}")
        sys.exit(1)
    else:
        print(f"\n{GREEN}Database verification passed!{RESET}")
        sys.exit(0)


if __name__ == '__main__':
    main()
