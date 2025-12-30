#!/usr/bin/env python3
"""
E2E Production Test Script for ARES, ATHENA, PEGASUS
=====================================================

Run this in Render shell after deployment to verify all bots are wired up correctly.

Usage:
    python scripts/test_all_bots_e2e.py
"""

import os
import sys
import json
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Test results tracking
results = {
    'passed': 0,
    'failed': 0,
    'tests': []
}


def log_test(name, passed, details=""):
    """Log a test result"""
    status = "PASS" if passed else "FAIL"
    icon = "✅" if passed else "❌"
    results['tests'].append({'name': name, 'passed': passed, 'details': details})
    if passed:
        results['passed'] += 1
    else:
        results['failed'] += 1
    print(f"  {icon} {name}")
    if details and not passed:
        print(f"      {details}")


def test_imports():
    """Test that all required modules can be imported"""
    print("\n" + "=" * 60)
    print("  TEST 1: Module Imports")
    print("=" * 60)

    # Database
    try:
        from database_adapter import get_connection
        log_test("database_adapter", True)
    except Exception as e:
        log_test("database_adapter", False, str(e))

    # Config
    try:
        from unified_config import APIConfig
        log_test("unified_config", True)
    except Exception as e:
        log_test("unified_config", False, str(e))

    # ARES
    try:
        from trading.ares_v2 import ARESTrader
        log_test("ARES trader", True)
    except Exception as e:
        log_test("ARES trader", False, str(e))

    # ATHENA
    try:
        from trading.athena_v2 import ATHENATrader
        log_test("ATHENA trader", True)
    except Exception as e:
        log_test("ATHENA trader", False, str(e))

    # PEGASUS
    try:
        from trading.pegasus import PEGASUSTrader
        log_test("PEGASUS trader", True)
    except Exception as e:
        log_test("PEGASUS trader", False, str(e))

    # Tradier
    try:
        from data.tradier_data_fetcher import TradierDataFetcher
        log_test("TradierDataFetcher (standard)", True)
    except Exception as e:
        # Try direct import
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "tradier",
                os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'tradier_data_fetcher.py')
            )
            m = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(m)
            log_test("TradierDataFetcher (direct)", True)
        except Exception as e2:
            log_test("TradierDataFetcher", False, f"Standard: {e}, Direct: {e2}")


def test_database():
    """Test database connectivity and tables"""
    print("\n" + "=" * 60)
    print("  TEST 2: Database Connectivity")
    print("=" * 60)

    try:
        from database_adapter import get_connection
        conn = get_connection()
        cursor = conn.cursor()

        # Test connection
        cursor.execute("SELECT 1")
        log_test("Database connection", True)

        # Check ARES tables
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'ares_positions'
            )
        """)
        exists = cursor.fetchone()[0]
        log_test("ares_positions table", exists, "Table missing" if not exists else "")

        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'ares_logs'
            )
        """)
        exists = cursor.fetchone()[0]
        log_test("ares_logs table", exists, "Table missing" if not exists else "")

        # Check ATHENA tables
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'athena_positions'
            )
        """)
        exists = cursor.fetchone()[0]
        log_test("athena_positions table", exists, "Table missing" if not exists else "")

        # Check PEGASUS tables
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'pegasus_positions'
            )
        """)
        exists = cursor.fetchone()[0]
        log_test("pegasus_positions table", exists, "Table missing" if not exists else "")

        # Check bot_heartbeats
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'bot_heartbeats'
            )
        """)
        exists = cursor.fetchone()[0]
        log_test("bot_heartbeats table", exists, "Table missing" if not exists else "")

        conn.close()

    except Exception as e:
        log_test("Database connection", False, str(e))


def test_api_endpoints():
    """Test API endpoints by importing and calling route handlers"""
    print("\n" + "=" * 60)
    print("  TEST 3: API Endpoints")
    print("=" * 60)

    import asyncio

    # ARES endpoints
    try:
        from backend.api.routes.ares_routes import get_ares_status
        result = asyncio.get_event_loop().run_until_complete(get_ares_status())
        has_data = result.get('success') or 'data' in result
        log_test("ARES /status", has_data, str(result)[:100] if not has_data else "")
    except Exception as e:
        log_test("ARES /status", False, str(e)[:100])

    try:
        from backend.api.routes.ares_routes import get_ares_positions
        result = asyncio.get_event_loop().run_until_complete(get_ares_positions())
        has_data = result.get('success') or 'data' in result
        log_test("ARES /positions", has_data)
    except Exception as e:
        log_test("ARES /positions", False, str(e)[:100])

    try:
        from backend.api.routes.ares_routes import get_ares_logs
        result = asyncio.get_event_loop().run_until_complete(get_ares_logs())
        has_data = result.get('success') or 'data' in result
        log_test("ARES /logs", has_data)
    except Exception as e:
        log_test("ARES /logs", False, str(e)[:100])

    try:
        from backend.api.routes.ares_routes import get_ares_live_pnl
        result = asyncio.get_event_loop().run_until_complete(get_ares_live_pnl())
        has_data = result.get('success') or 'data' in result
        log_test("ARES /live-pnl", has_data)
    except Exception as e:
        log_test("ARES /live-pnl", False, str(e)[:100])

    # ATHENA endpoints
    try:
        from backend.api.routes.athena_routes import get_athena_status
        result = asyncio.get_event_loop().run_until_complete(get_athena_status())
        has_data = result.get('success') or 'data' in result
        log_test("ATHENA /status", has_data)
    except Exception as e:
        log_test("ATHENA /status", False, str(e)[:100])

    try:
        from backend.api.routes.athena_routes import get_athena_positions
        result = asyncio.get_event_loop().run_until_complete(get_athena_positions())
        has_data = result.get('success') or 'data' in result
        log_test("ATHENA /positions", has_data)
    except Exception as e:
        log_test("ATHENA /positions", False, str(e)[:100])

    try:
        from backend.api.routes.athena_routes import get_athena_logs
        result = asyncio.get_event_loop().run_until_complete(get_athena_logs())
        has_data = result.get('success') or 'data' in result
        log_test("ATHENA /logs", has_data)
    except Exception as e:
        log_test("ATHENA /logs", False, str(e)[:100])

    try:
        from backend.api.routes.athena_routes import get_athena_live_pnl
        result = asyncio.get_event_loop().run_until_complete(get_athena_live_pnl())
        has_data = result.get('success') or 'data' in result
        log_test("ATHENA /live-pnl", has_data)
    except Exception as e:
        log_test("ATHENA /live-pnl", False, str(e)[:100])

    # PEGASUS endpoints
    try:
        from backend.api.routes.pegasus_routes import get_pegasus_status
        result = asyncio.get_event_loop().run_until_complete(get_pegasus_status())
        has_data = result.get('success') or 'data' in result
        log_test("PEGASUS /status", has_data)
    except Exception as e:
        log_test("PEGASUS /status", False, str(e)[:100])

    try:
        from backend.api.routes.pegasus_routes import get_pegasus_positions
        result = asyncio.get_event_loop().run_until_complete(get_pegasus_positions())
        has_data = result.get('success') or 'data' in result
        log_test("PEGASUS /positions", has_data)
    except Exception as e:
        log_test("PEGASUS /positions", False, str(e)[:100])

    try:
        from backend.api.routes.pegasus_routes import get_pegasus_logs
        result = asyncio.get_event_loop().run_until_complete(get_pegasus_logs())
        has_data = result.get('success') or 'data' in result
        log_test("PEGASUS /logs", has_data)
    except Exception as e:
        log_test("PEGASUS /logs", False, str(e)[:100])

    try:
        from backend.api.routes.pegasus_routes import get_pegasus_performance
        result = asyncio.get_event_loop().run_until_complete(get_pegasus_performance())
        has_data = result.get('success') or 'data' in result
        log_test("PEGASUS /performance", has_data)
    except Exception as e:
        log_test("PEGASUS /performance", False, str(e)[:100])

    try:
        from backend.api.routes.pegasus_routes import get_pegasus_live_pnl
        result = asyncio.get_event_loop().run_until_complete(get_pegasus_live_pnl())
        has_data = result.get('success') or 'data' in result
        log_test("PEGASUS /live-pnl", has_data)
    except Exception as e:
        log_test("PEGASUS /live-pnl", False, str(e)[:100])


def test_tradier_connection():
    """Test Tradier API connection for ARES"""
    print("\n" + "=" * 60)
    print("  TEST 4: Tradier Connection (ARES)")
    print("=" * 60)

    try:
        from unified_config import APIConfig

        api_key = (
            getattr(APIConfig, 'TRADIER_SANDBOX_API_KEY', None) or
            getattr(APIConfig, 'TRADIER_PROD_API_KEY', None) or
            getattr(APIConfig, 'TRADIER_API_KEY', None)
        )
        account_id = (
            getattr(APIConfig, 'TRADIER_SANDBOX_ACCOUNT_ID', None) or
            getattr(APIConfig, 'TRADIER_PROD_ACCOUNT_ID', None) or
            getattr(APIConfig, 'TRADIER_ACCOUNT_ID', None)
        )
        sandbox = getattr(APIConfig, 'TRADIER_SANDBOX', True)

        if not api_key or not account_id:
            log_test("Tradier credentials", False, "Missing API key or account ID")
            return

        log_test("Tradier credentials", True, f"Account: {account_id}")

        # Try to import and connect
        TradierDataFetcher = None
        try:
            from data.tradier_data_fetcher import TradierDataFetcher
        except ImportError:
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "tradier",
                os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'tradier_data_fetcher.py')
            )
            m = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(m)
            TradierDataFetcher = m.TradierDataFetcher

        tradier = TradierDataFetcher(api_key=api_key, account_id=account_id, sandbox=sandbox)

        # Test balance
        balance = tradier.get_account_balance()
        if balance and balance.get('total_equity', 0) > 0:
            equity = balance.get('total_equity', 0)
            log_test("Tradier balance", True, f"${equity:,.2f}")
        else:
            log_test("Tradier balance", False, "Empty or zero balance")

        # Test SPY quote
        quote = tradier.get_quote('SPY')
        if quote and quote.get('last', 0) > 0:
            log_test("Tradier SPY quote", True, f"${quote.get('last', 0):.2f}")
        else:
            log_test("Tradier SPY quote", False, "Empty quote")

    except Exception as e:
        log_test("Tradier connection", False, str(e)[:100])


def test_timezone():
    """Test that timestamps are in Central Time"""
    print("\n" + "=" * 60)
    print("  TEST 5: Timezone Configuration")
    print("=" * 60)

    try:
        from zoneinfo import ZoneInfo
        from datetime import datetime

        central = ZoneInfo("America/Chicago")
        now_ct = datetime.now(central)

        log_test("Central timezone available", True, now_ct.strftime('%Y-%m-%d %H:%M:%S %Z'))

        # Check heartbeat timezone handling
        from backend.api.routes.ares_routes import _get_heartbeat
        heartbeat = _get_heartbeat('ARES')

        if heartbeat.get('last_scan'):
            has_ct = 'CT' in heartbeat.get('last_scan', '')
            log_test("Heartbeat in Central Time", has_ct, heartbeat.get('last_scan', ''))
        else:
            log_test("Heartbeat timestamp", True, "No heartbeat yet (bot hasn't run)")

    except Exception as e:
        log_test("Timezone check", False, str(e)[:100])


def print_summary():
    """Print test summary"""
    print("\n" + "=" * 60)
    print("  SUMMARY")
    print("=" * 60)

    total = results['passed'] + results['failed']
    print(f"\n  Tests Run:    {total}")
    print(f"  Passed:       {results['passed']} ✅")
    print(f"  Failed:       {results['failed']} ❌")

    if results['failed'] > 0:
        print(f"\n  Failed Tests:")
        for test in results['tests']:
            if not test['passed']:
                print(f"    - {test['name']}: {test['details']}")

    print("\n" + "=" * 60)

    if results['failed'] == 0:
        print("  🎉 ALL TESTS PASSED!")
    else:
        print(f"  ⚠️  {results['failed']} TEST(S) FAILED - Review above")

    print("=" * 60 + "\n")


def main():
    print("\n" + "=" * 60)
    print("  ALPHAGEX E2E PRODUCTION TEST")
    print("  " + datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    print("=" * 60)

    test_imports()
    test_database()
    test_api_endpoints()
    test_tradier_connection()
    test_timezone()

    print_summary()

    # Exit with error code if tests failed
    sys.exit(1 if results['failed'] > 0 else 0)


if __name__ == '__main__':
    main()
