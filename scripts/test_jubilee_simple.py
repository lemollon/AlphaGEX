#!/usr/bin/env python3
"""
JUBILEE Simple Verification Script
======================================
Minimal dependencies - uses only stdlib + psycopg2

Run: python scripts/test_prometheus_simple.py
"""

import os
import sys

# Colors
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
RESET = '\033[0m'
BOLD = '\033[1m'

results = {"passed": 0, "failed": 0}

def ok(msg):
    results["passed"] += 1
    print(f"  {GREEN}✅{RESET} {msg}")

def fail(msg):
    results["failed"] += 1
    print(f"  {RED}❌{RESET} {msg}")

def info(msg):
    print(f"  ℹ️  {msg}")

def header(title):
    print(f"\n{BOLD}{'='*50}{RESET}")
    print(f"{BOLD}{title}{RESET}")
    print(f"{'='*50}")

# =============================================================================
# TEST 1: Database Connection & Tables
# =============================================================================
def test_database():
    header("TEST 1: Database Tables")

    try:
        import psycopg2

        DATABASE_URL = os.getenv("DATABASE_URL")
        if not DATABASE_URL:
            fail("DATABASE_URL not set")
            return None

        conn = psycopg2.connect(DATABASE_URL)
        ok("Database connected")

        cursor = conn.cursor()

        # Check all JUBILEE tables
        tables = [
            ("jubilee_positions", "Box spread positions"),
            ("jubilee_logs", "Activity logs"),
            ("jubilee_config", "Configuration"),
            ("jubilee_equity_snapshots", "Equity snapshots"),
            ("jubilee_ic_positions", "IC positions"),
            ("jubilee_ic_closed_trades", "IC closed trades"),
            ("jubilee_ic_signals", "IC signals"),
            ("jubilee_ic_config", "IC config"),
            ("jubilee_ic_equity_snapshots", "IC equity snapshots"),
        ]

        for table, desc in tables:
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                count = cursor.fetchone()[0]
                ok(f"{table}: {count} rows")
            except Exception as e:
                fail(f"{table}: {e}")

        cursor.close()
        return conn

    except ImportError:
        fail("psycopg2 not installed")
        return None
    except Exception as e:
        fail(f"Database error: {e}")
        return None

# =============================================================================
# TEST 2: Check for Paper Box Spread
# =============================================================================
def test_paper_box(conn):
    header("TEST 2: Paper Box Spread")

    if not conn:
        fail("No database connection")
        return

    try:
        cursor = conn.cursor()

        # Check for any open box positions
        cursor.execute("""
            SELECT position_id, total_cash_deployed, status,
                   implied_annual_rate, position_explanation
            FROM jubilee_positions
            WHERE status = 'open'
            LIMIT 5
        """)
        rows = cursor.fetchall()

        if rows:
            ok(f"Found {len(rows)} open box position(s)")
            for row in rows:
                info(f"  ID: {row[0]}, Cash: ${row[1]:,.0f}, Rate: {row[3]:.2f}%")
                if 'PAPER' in str(row[4] or ''):
                    ok("Paper box spread detected")
        else:
            info("No open box positions yet (will be created on first IC cycle)")

        cursor.close()

    except Exception as e:
        fail(f"Query error: {e}")

# =============================================================================
# TEST 3: Check IC Config
# =============================================================================
def test_ic_config(conn):
    header("TEST 3: IC Configuration")

    if not conn:
        fail("No database connection")
        return

    try:
        cursor = conn.cursor()

        cursor.execute("""
            SELECT config_data FROM jubilee_ic_config
            WHERE config_key = 'default'
        """)
        row = cursor.fetchone()

        if row and row[0]:
            config = row[0]
            ok("IC config exists in database")

            if isinstance(config, dict):
                enabled = config.get('enabled', True)
                mode = config.get('mode', 'unknown')
                info(f"  enabled: {enabled}")
                info(f"  mode: {mode}")

                if enabled:
                    ok("IC trading is ENABLED")
                else:
                    fail("IC trading is DISABLED in config")
        else:
            info("No IC config in DB (will use defaults: enabled=True)")
            ok("Default config will enable IC trading")

        cursor.close()

    except Exception as e:
        fail(f"Query error: {e}")

# =============================================================================
# TEST 4: Check Recent Activity
# =============================================================================
def test_activity(conn):
    header("TEST 4: Recent Activity")

    if not conn:
        fail("No database connection")
        return

    try:
        cursor = conn.cursor()

        # Check logs
        cursor.execute("""
            SELECT action, message, created_at
            FROM jubilee_logs
            ORDER BY created_at DESC
            LIMIT 5
        """)
        logs = cursor.fetchall()

        if logs:
            ok(f"Found {len(logs)} recent log entries")
            for log in logs[:3]:
                msg = (log[1] or "")[:50]
                info(f"  [{log[2]}] {log[0]}: {msg}...")
        else:
            info("No logs yet (system hasn't run trading cycles)")

        # Check IC signals
        cursor.execute("""
            SELECT COUNT(*) FROM jubilee_ic_signals
            WHERE created_at > NOW() - INTERVAL '24 hours'
        """)
        signal_count = cursor.fetchone()[0]
        info(f"IC signals in last 24h: {signal_count}")

        # Check equity snapshots
        cursor.execute("""
            SELECT COUNT(*) FROM jubilee_ic_equity_snapshots
            WHERE snapshot_time > NOW() - INTERVAL '24 hours'
        """)
        snapshot_count = cursor.fetchone()[0]
        info(f"IC equity snapshots in last 24h: {snapshot_count}")

        cursor.close()

    except Exception as e:
        fail(f"Query error: {e}")

# =============================================================================
# TEST 5: Import Check (without heavy deps)
# =============================================================================
def test_imports():
    header("TEST 5: Core Imports")

    # Test jubilee models (no pandas needed)
    try:
        from trading.jubilee.models import (
            PrometheusICConfig,
            TradingMode,
            BoxSpreadPosition,
            PositionStatus,
        )
        ok("PrometheusICConfig imported")
        ok("TradingMode imported")
        ok("BoxSpreadPosition imported")

        # Create a config
        config = PrometheusICConfig()
        ok(f"Default config: enabled={config.enabled}, capital=${config.starting_capital:,.0f}")

    except ImportError as e:
        fail(f"Import error: {e}")
    except Exception as e:
        fail(f"Error: {e}")

# =============================================================================
# MAIN
# =============================================================================
def main():
    print(f"\n{BOLD}JUBILEE SIMPLE VERIFICATION{RESET}")
    print(f"{'='*50}\n")

    # Run tests
    test_imports()
    conn = test_database()
    test_paper_box(conn)
    test_ic_config(conn)
    test_activity(conn)

    if conn:
        conn.close()

    # Summary
    header("SUMMARY")
    total = results["passed"] + results["failed"]
    print(f"  Passed: {GREEN}{results['passed']}{RESET}")
    print(f"  Failed: {RED}{results['failed']}{RESET}")

    if results["failed"] == 0:
        print(f"\n  {GREEN}{BOLD}✅ All checks passed!{RESET}")
        return True
    else:
        print(f"\n  {RED}{BOLD}❌ {results['failed']} check(s) failed{RESET}")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
