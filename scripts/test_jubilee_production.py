#!/usr/bin/env python3
"""
JUBILEE Production Readiness Test Script
============================================
Run this in Render shell to verify JUBILEE is fully operational.

Usage:
    python scripts/test_jubilee_production.py

Tests:
1. Database tables exist with correct schema
2. IC Trader initializes properly
3. Paper box spread creates successfully
4. Capital flows correctly
5. All API endpoints return real data
6. Scheduler jobs are registered

Per STANDARDS.md - NO SCAFFOLDING - all tests verify REAL data flow.
"""

import os
import sys
import json
from datetime import datetime, timedelta

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Color output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
RESET = '\033[0m'
BOLD = '\033[1m'

def print_header(title: str):
    print(f"\n{BOLD}{'='*60}{RESET}")
    print(f"{BOLD}{title}{RESET}")
    print(f"{BOLD}{'='*60}{RESET}\n")

def print_pass(msg: str):
    print(f"  {GREEN}✅ PASS:{RESET} {msg}")

def print_fail(msg: str):
    print(f"  {RED}❌ FAIL:{RESET} {msg}")

def print_warn(msg: str):
    print(f"  {YELLOW}⚠️ WARN:{RESET} {msg}")

def print_info(msg: str):
    print(f"  ℹ️  {msg}")

# Track results
results = {"passed": 0, "failed": 0, "warnings": 0}

def test_pass(msg: str):
    results["passed"] += 1
    print_pass(msg)

def test_fail(msg: str):
    results["failed"] += 1
    print_fail(msg)

def test_warn(msg: str):
    results["warnings"] += 1
    print_warn(msg)

# =============================================================================
# TEST 1: Database Tables Exist
# =============================================================================
def test_database_tables():
    print_header("TEST 1: Database Tables")

    try:
        from trading.jubilee.db import JubileeDatabase
        db = JubileeDatabase(bot_name="TEST")

        # Tables should be created by _ensure_tables()
        test_pass("JubileeDatabase initialized successfully")

        # Check box spread tables
        box_tables = [
            'jubilee_positions',
            'jubilee_signals',
            'jubilee_logs',
            'jubilee_config',
            'jubilee_equity_snapshots',
        ]

        for table in box_tables:
            try:
                conn = db._get_connection()
                cursor = conn.cursor()
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                count = cursor.fetchone()[0]
                cursor.close()
                test_pass(f"Table '{table}' exists (rows: {count})")
            except Exception as e:
                test_fail(f"Table '{table}' error: {e}")

        # Check IC tables
        ic_tables = [
            'jubilee_ic_positions',
            'jubilee_ic_closed_trades',
            'jubilee_ic_signals',
            'jubilee_ic_config',
            'jubilee_ic_equity_snapshots',
        ]

        for table in ic_tables:
            try:
                conn = db._get_connection()
                cursor = conn.cursor()
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                count = cursor.fetchone()[0]
                cursor.close()
                test_pass(f"Table '{table}' exists (rows: {count})")
            except Exception as e:
                test_fail(f"Table '{table}' error: {e}")

    except Exception as e:
        test_fail(f"Database initialization failed: {e}")

# =============================================================================
# TEST 2: IC Trader Initialization
# =============================================================================
def test_ic_trader_init():
    print_header("TEST 2: IC Trader Initialization")

    try:
        from trading.jubilee.trader import JubileeICTrader
        from trading.jubilee.models import PrometheusICConfig, TradingMode

        # Create config
        config = PrometheusICConfig()
        config.mode = TradingMode.PAPER
        config.enabled = True

        test_pass(f"PrometheusICConfig created (mode={config.mode.value}, enabled={config.enabled})")

        # Initialize trader
        trader = JubileeICTrader(config=config)
        test_pass("JubileeICTrader initialized successfully")

        # Check components
        if trader.db:
            test_pass("IC trader has database connection")
        else:
            test_fail("IC trader missing database connection")

        if trader.signal_gen:
            test_pass("IC trader has signal generator")
        else:
            test_fail("IC trader missing signal generator")

        if trader.executor:
            test_pass("IC trader has executor")
        else:
            test_fail("IC trader missing executor")

        # Check config validation
        if trader.config.starting_capital > 0:
            test_pass(f"IC starting_capital = ${trader.config.starting_capital:,.0f}")
        else:
            test_fail(f"IC starting_capital invalid: {trader.config.starting_capital}")

    except Exception as e:
        test_fail(f"IC Trader initialization failed: {e}")
        import traceback
        print(traceback.format_exc())

# =============================================================================
# TEST 3: Paper Box Spread Creation
# =============================================================================
def test_paper_box_spread():
    print_header("TEST 3: Paper Box Spread Creation")

    try:
        from trading.jubilee.trader import JubileeICTrader
        from trading.jubilee.models import PrometheusICConfig, TradingMode

        # Create IC trader in PAPER mode
        config = PrometheusICConfig()
        config.mode = TradingMode.PAPER
        trader = JubileeICTrader(config=config)

        # Check current box positions
        box_positions_before = trader.db.get_open_positions()
        print_info(f"Box positions before: {len(box_positions_before)}")

        # Call _ensure_paper_box_spread
        trader._ensure_paper_box_spread()

        # Check again
        box_positions_after = trader.db.get_open_positions()
        print_info(f"Box positions after: {len(box_positions_after)}")

        if len(box_positions_after) > 0:
            test_pass(f"Paper box spread exists ({len(box_positions_after)} positions)")

            # Verify the position has correct fields
            box = box_positions_after[0]

            if hasattr(box, 'total_cash_deployed') and box.total_cash_deployed > 0:
                test_pass(f"Box has cash deployed: ${box.total_cash_deployed:,.0f}")
            else:
                test_fail("Box missing total_cash_deployed")

            if hasattr(box, 'position_id') and box.position_id:
                test_pass(f"Box has position_id: {box.position_id}")
            else:
                test_fail("Box missing position_id")

            if hasattr(box, 'implied_annual_rate'):
                test_pass(f"Box has implied_annual_rate: {box.implied_annual_rate:.2f}%")
            else:
                test_warn("Box missing implied_annual_rate")
        else:
            test_fail("Paper box spread was NOT created")

    except Exception as e:
        test_fail(f"Paper box spread test failed: {e}")
        import traceback
        print(traceback.format_exc())

# =============================================================================
# TEST 4: Capital Flow
# =============================================================================
def test_capital_flow():
    print_header("TEST 4: Capital Flow (Box → IC)")

    try:
        from trading.jubilee.trader import JubileeICTrader
        from trading.jubilee.models import PrometheusICConfig, TradingMode

        # Create IC trader in PAPER mode
        config = PrometheusICConfig()
        config.mode = TradingMode.PAPER
        trader = JubileeICTrader(config=config)

        # Get available capital (should trigger paper box creation)
        available = trader._get_available_capital()

        if available > 0:
            test_pass(f"Available capital: ${available:,.0f}")
        else:
            test_fail(f"Available capital is $0 - capital flow broken")

        # Get source box position
        source_box = trader._get_source_box_position()

        if source_box:
            test_pass(f"Source box position: {source_box}")
        else:
            test_fail("No source box position - IC cannot link trades")

        # Check can_trade
        can_trade = trader._can_open_new_position()
        in_window = trader._in_trading_window()

        print_info(f"In trading window: {in_window}")
        print_info(f"Can open new position: {can_trade}")

        if not in_window:
            test_warn("Outside trading window - expected if market closed")

    except Exception as e:
        test_fail(f"Capital flow test failed: {e}")
        import traceback
        print(traceback.format_exc())

# =============================================================================
# TEST 5: IC Status Endpoint Data
# =============================================================================
def test_ic_status():
    print_header("TEST 5: IC Status Data")

    try:
        from trading.jubilee.trader import JubileeICTrader
        from trading.jubilee.models import PrometheusICConfig, TradingMode

        config = PrometheusICConfig()
        config.mode = TradingMode.PAPER
        trader = JubileeICTrader(config=config)

        # Get status
        status = trader.get_status()

        # Verify required fields
        required_fields = [
            'enabled',
            'trading_active',
            'inactive_reason',
            'mode',
            'ticker',
            'open_positions',
            'available_capital',
            'can_trade',
            'in_trading_window',
        ]

        for field in required_fields:
            if field in status:
                test_pass(f"Status has '{field}': {status[field]}")
            else:
                test_fail(f"Status missing '{field}'")

        # Check trading_active logic
        if status.get('enabled') and status.get('in_trading_window'):
            if status.get('trading_active'):
                test_pass("trading_active=True (enabled AND in window)")
            else:
                test_fail("trading_active should be True but isn't")
        else:
            if not status.get('trading_active'):
                test_pass(f"trading_active=False (reason: {status.get('inactive_reason')})")
            else:
                test_warn("trading_active=True but should be False")

    except Exception as e:
        test_fail(f"IC status test failed: {e}")
        import traceback
        print(traceback.format_exc())

# =============================================================================
# TEST 6: Scheduler Jobs
# =============================================================================
def test_scheduler_jobs():
    print_header("TEST 6: Scheduler Jobs")

    try:
        # Check scheduler imports
        from scheduler.trader_scheduler import (
            PROMETHEUS_BOX_AVAILABLE,
            JUBILEE_IC_AVAILABLE,
        )

        if PROMETHEUS_BOX_AVAILABLE:
            test_pass("PROMETHEUS_BOX_AVAILABLE = True")
        else:
            test_fail("PROMETHEUS_BOX_AVAILABLE = False - box spread jobs won't run")

        if JUBILEE_IC_AVAILABLE:
            test_pass("JUBILEE_IC_AVAILABLE = True")
        else:
            test_fail("JUBILEE_IC_AVAILABLE = False - IC jobs won't run")

        # Check scheduler has the methods
        from scheduler.trader_scheduler import AutonomousTraderScheduler

        methods_to_check = [
            'scheduled_jubilee_daily_logic',
            'scheduled_jubilee_equity_snapshot',
            'scheduled_jubilee_rate_analysis',
            'scheduled_jubilee_ic_cycle',
            'scheduled_jubilee_ic_mtm_update',
        ]

        for method in methods_to_check:
            if hasattr(AutonomousTraderScheduler, method):
                test_pass(f"AutonomousTraderScheduler.{method}() exists")
            else:
                test_fail(f"AutonomousTraderScheduler.{method}() MISSING")

    except ImportError as e:
        test_fail(f"Scheduler import failed: {e}")
    except Exception as e:
        test_fail(f"Scheduler test failed: {e}")

# =============================================================================
# TEST 7: Database Methods Return Data
# =============================================================================
def test_database_methods():
    print_header("TEST 7: Database Methods Return Data")

    try:
        from trading.jubilee.db import JubileeDatabase
        db = JubileeDatabase(bot_name="TEST")

        # Test each critical method
        methods = [
            ('get_open_positions', [], "Box positions"),
            ('get_ic_performance', [], "IC performance"),
            ('get_equity_curve', [10], "Equity curve"),
            ('get_recent_logs', [10], "Recent logs"),
        ]

        for method_name, args, description in methods:
            try:
                method = getattr(db, method_name)
                result = method(*args)

                if result is not None:
                    if isinstance(result, list):
                        test_pass(f"{description}: returns list ({len(result)} items)")
                    elif isinstance(result, dict):
                        test_pass(f"{description}: returns dict ({len(result)} keys)")
                    else:
                        test_pass(f"{description}: returns {type(result).__name__}")
                else:
                    test_warn(f"{description}: returns None (may be OK if no data yet)")
            except Exception as e:
                test_fail(f"{description} ({method_name}): {e}")

    except Exception as e:
        test_fail(f"Database methods test failed: {e}")

# =============================================================================
# MAIN
# =============================================================================
def main():
    print(f"\n{BOLD}{'='*60}{RESET}")
    print(f"{BOLD}   JUBILEE PRODUCTION READINESS TEST{RESET}")
    print(f"{BOLD}   {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{RESET}")
    print(f"{BOLD}{'='*60}{RESET}")

    # Run all tests
    test_database_tables()
    test_ic_trader_init()
    test_paper_box_spread()
    test_capital_flow()
    test_ic_status()
    test_scheduler_jobs()
    test_database_methods()

    # Summary
    print_header("TEST SUMMARY")
    print(f"  {GREEN}Passed:   {results['passed']}{RESET}")
    print(f"  {RED}Failed:   {results['failed']}{RESET}")
    print(f"  {YELLOW}Warnings: {results['warnings']}{RESET}")

    total = results['passed'] + results['failed']
    if total > 0:
        score = (results['passed'] / total) * 100
        print(f"\n  Score: {score:.0f}%")

        if results['failed'] == 0:
            print(f"\n  {GREEN}{BOLD}🎉 JUBILEE IS PRODUCTION READY!{RESET}")
        else:
            print(f"\n  {RED}{BOLD}⚠️ JUBILEE HAS {results['failed']} FAILURE(S) - NOT READY{RESET}")

    return results['failed'] == 0

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
