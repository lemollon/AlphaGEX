#!/usr/bin/env python3
"""
ALPHAGEX COMPREHENSIVE SYSTEM VERIFICATION
==========================================
Run this script to verify all components are working properly.
This will check everything the frontend needs to display data.

Usage:
    python scripts/verify_system.py

Run on Render:
    python scripts/verify_system.py
"""

import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Tuple

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Test results tracking
results = {
    'passed': 0,
    'failed': 0,
    'warnings': 0
}
issues = []
warnings_list = []


def log_pass(test: str, details: str = ""):
    results['passed'] += 1
    print(f"✅ PASS: {test}")
    if details:
        print(f"         {details}")


def log_fail(test: str, details: str = ""):
    results['failed'] += 1
    issues.append(f"{test}: {details}")
    print(f"❌ FAIL: {test}")
    if details:
        print(f"         {details}")


def log_warn(test: str, details: str = ""):
    results['warnings'] += 1
    warnings_list.append(f"{test}: {details}")
    print(f"⚠️  WARN: {test}")
    if details:
        print(f"         {details}")


def print_section(title: str):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}\n")


# =============================================================================
# TEST 1: DATABASE CONNECTION
# =============================================================================
def test_database_connection():
    print_section("DATABASE CONNECTION")

    try:
        from database_adapter import get_connection
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT version()")
        version = cursor.fetchone()[0]
        conn.close()
        log_pass("Database Connection", f"PostgreSQL connected: {version[:50]}...")
        return True
    except Exception as e:
        log_fail("Database Connection", str(e))
        return False


# =============================================================================
# TEST 2: CRITICAL TABLES EXIST AND HAVE DATA
# =============================================================================
def test_critical_tables():
    print_section("CRITICAL DATABASE TABLES")

    try:
        from database_adapter import get_connection
        conn = get_connection()
        cursor = conn.cursor()

        tables = [
            ('gex_history', 'Historical GEX data for charts', True),
            ('regime_signals', 'Psychology regime signals', True),
            ('autonomous_open_positions', 'Current open trades', False),
            ('autonomous_closed_trades', 'Historical closed trades', False),
            ('autonomous_config', 'Trader configuration', True),
            ('backtest_results', 'Backtest results', True),
            ('autonomous_trade_log', 'Trade activity log', False),
        ]

        for table, description, required_data in tables:
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                count = cursor.fetchone()[0]

                if count > 0:
                    log_pass(f"{table}", f"{count} records - {description}")
                elif required_data:
                    log_fail(f"{table}", f"EMPTY - {description} - Frontend will show blank!")
                else:
                    log_warn(f"{table}", f"Empty (may be normal) - {description}")
            except Exception as e:
                if "does not exist" in str(e):
                    log_fail(f"{table}", f"Table does not exist!")
                else:
                    log_fail(f"{table}", str(e))
                conn.rollback()

        conn.close()
        return True
    except Exception as e:
        log_fail("Table Check", str(e))
        return False


# =============================================================================
# TEST 3: GEX HISTORY FRESHNESS
# =============================================================================
def test_gex_history_freshness():
    print_section("GEX HISTORY DATA FRESHNESS")

    try:
        from database_adapter import get_connection
        from zoneinfo import ZoneInfo

        conn = get_connection()
        cursor = conn.cursor()

        # Check total records
        cursor.execute("SELECT COUNT(*) FROM gex_history")
        total = cursor.fetchone()[0]

        if total == 0:
            log_fail("GEX History", "NO DATA - Data collector is not running or never ran!")
            conn.close()
            return False

        # Check most recent record
        cursor.execute("SELECT timestamp, spot_price, net_gex FROM gex_history ORDER BY timestamp DESC LIMIT 1")
        latest = cursor.fetchone()

        if latest:
            timestamp, spot_price, net_gex = latest
            now = datetime.now(ZoneInfo("America/New_York"))

            # Handle timezone-aware vs naive datetime
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=ZoneInfo("America/New_York"))

            age_hours = (now - timestamp).total_seconds() / 3600

            print(f"   Latest record: {timestamp}")
            print(f"   SPY Spot: ${spot_price:.2f}")
            print(f"   Net GEX: ${net_gex/1e9:.2f}B")
            print(f"   Age: {age_hours:.1f} hours")

            if age_hours < 1:
                log_pass("GEX Freshness", f"Data is {age_hours*60:.0f} minutes old")
            elif age_hours < 8:
                log_warn("GEX Freshness", f"Data is {age_hours:.1f} hours old (may be from last market close)")
            else:
                log_warn("GEX Freshness", f"Data is {age_hours:.1f} hours old - check if data collector is running")

        # Check today's records
        today = datetime.now(ZoneInfo("America/New_York")).strftime('%Y-%m-%d')
        cursor.execute("SELECT COUNT(*) FROM gex_history WHERE DATE(timestamp) = %s", (today,))
        today_count = cursor.fetchone()[0]

        print(f"   Today's records: {today_count}")

        if today_count > 0:
            log_pass("Today's GEX Data", f"{today_count} snapshots collected today")
        else:
            # Check if market is open
            now = datetime.now(ZoneInfo("America/New_York"))
            is_weekday = now.weekday() < 5
            is_market_hours = 9 <= now.hour < 16 or (now.hour == 16 and now.minute == 0)

            if is_weekday and is_market_hours:
                log_warn("Today's GEX Data", "No data for today but market is open - data collector may not be running")
            else:
                log_warn("Today's GEX Data", f"No data for today ({today}) - market may be closed")

        conn.close()
        return True
    except Exception as e:
        log_fail("GEX History Check", str(e))
        return False


# =============================================================================
# TEST 4: AUTONOMOUS TRADER STATUS
# =============================================================================
def test_autonomous_trader():
    print_section("AUTONOMOUS TRADER STATUS")

    try:
        from database_adapter import get_connection
        conn = get_connection()
        cursor = conn.cursor()

        # Check config
        cursor.execute("SELECT key, value FROM autonomous_config WHERE key IN ('mode', 'capital', 'last_trade_date')")
        config = {row[0]: row[1] for row in cursor.fetchall()}

        print(f"   Mode: {config.get('mode', 'NOT SET')}")
        print(f"   Capital: \${float(config.get('capital', 0)):,.0f}")
        print(f"   Last Trade Date: {config.get('last_trade_date', 'Never')}")

        if config.get('mode'):
            log_pass("Trader Config", f"Mode={config.get('mode')}, Capital=\${float(config.get('capital', 0)):,.0f}")
        else:
            log_warn("Trader Config", "No configuration found")

        # Check open positions
        cursor.execute("SELECT COUNT(*) FROM autonomous_open_positions")
        open_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM autonomous_closed_trades")
        closed_count = cursor.fetchone()[0]

        print(f"   Open Positions: {open_count}")
        print(f"   Closed Trades: {closed_count}")

        if open_count > 0 or closed_count > 0:
            log_pass("Trading Activity", f"{open_count} open, {closed_count} closed trades")
        else:
            log_warn("Trading Activity", "No trades yet - trader may not have found opportunities")

        # Check for \$0 entry prices (data integrity)
        cursor.execute("""
            SELECT COUNT(*) FROM autonomous_closed_trades
            WHERE entry_price IS NULL OR entry_price = 0
        """)
        zero_entry = cursor.fetchone()[0]

        if zero_entry > 0:
            log_warn("Data Integrity", f"{zero_entry} trades have \$0 entry price (legacy data issue)")
        else:
            log_pass("Data Integrity", "All trades have valid entry prices")

        conn.close()
        return True
    except Exception as e:
        log_fail("Trader Status Check", str(e))
        return False


# =============================================================================
# TEST 5: TRADING VOLATILITY API
# =============================================================================
def test_trading_volatility_api():
    print_section("TRADING VOLATILITY API")

    try:
        from core_classes_and_engines import TradingVolatilityAPI
        api = TradingVolatilityAPI()

        print("   Testing get_net_gamma('SPY')...")
        data = api.get_net_gamma('SPY')

        if 'error' in data:
            log_fail("Trading Vol API", f"Error: {data['error']}")
            return False

        spot_price = data.get('spot_price', 0)
        net_gex = data.get('net_gex', 0)
        flip_point = data.get('flip_point', 0)
        call_wall = data.get('call_wall')
        put_wall = data.get('put_wall')
        iv = data.get('implied_volatility', 0)

        print(f"   Spot Price: \${spot_price:.2f}")
        print(f"   Net GEX: \${net_gex/1e9:.2f}B")
        print(f"   Flip Point: \${flip_point:.2f}")
        print(f"   Call Wall: \${call_wall:.2f}" if call_wall else "   Call Wall: Not available")
        print(f"   Put Wall: \${put_wall:.2f}" if put_wall else "   Put Wall: Not available")
        print(f"   Implied Volatility: {iv*100:.1f}%")

        if spot_price > 0:
            log_pass("Trading Vol API - Spot Price", f"\${spot_price:.2f}")
        else:
            log_fail("Trading Vol API - Spot Price", "Returned \$0")

        if call_wall and call_wall > 0:
            log_pass("Trading Vol API - Call Wall", f"\${call_wall:.2f}")
        else:
            log_warn("Trading Vol API - Call Wall", "Not available from /gex/latest (may need gammaOI endpoint)")

        if put_wall and put_wall > 0:
            log_pass("Trading Vol API - Put Wall", f"\${put_wall:.2f}")
        else:
            log_warn("Trading Vol API - Put Wall", "Not available from /gex/latest (may need gammaOI endpoint)")

        return True
    except ImportError as e:
        log_fail("Trading Vol API Import", str(e))
        return False
    except Exception as e:
        log_fail("Trading Vol API", str(e))
        return False


# =============================================================================
# TEST 6: ENVIRONMENT CONFIGURATION
# =============================================================================
def test_environment():
    print_section("ENVIRONMENT CONFIGURATION")

    env_vars = [
        ('DATABASE_URL', 'PostgreSQL connection', True),
        ('TRADING_VOLATILITY_API_KEY', 'Trading Vol API key', False),
        ('TV_USERNAME', 'Trading Vol username (alt)', False),
        ('POLYGON_API_KEY', 'Polygon API key', False),
        ('TRADIER_ACCESS_TOKEN', 'Tradier access token', False),
    ]

    for var, description, required in env_vars:
        value = os.getenv(var)
        if value:
            # Mask sensitive values
            masked = value[:4] + '...' + value[-4:] if len(value) > 10 else '***'
            log_pass(f"ENV: {var}", f"Set ({masked})")
        elif required:
            log_fail(f"ENV: {var}", f"NOT SET - {description}")
        else:
            log_warn(f"ENV: {var}", f"Not set - {description}")

    return True


# =============================================================================
# MAIN
# =============================================================================
if __name__ == "__main__":
    print("\n" + "="*70)
    print("  ALPHAGEX COMPREHENSIVE SYSTEM VERIFICATION")
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)

    # Run all tests
    test_database_connection()
    test_critical_tables()
    test_gex_history_freshness()
    test_autonomous_trader()
    test_trading_volatility_api()
    test_environment()

    # Summary
    print("\n" + "="*70)
    print("  VERIFICATION RESULTS")
    print("="*70)

    total = results['passed'] + results['failed'] + results['warnings']
    print(f"\n   ✅ Passed:   {results['passed']}/{total}")
    print(f"   ❌ Failed:   {results['failed']}/{total}")
    print(f"   ⚠️  Warnings: {results['warnings']}/{total}")

    if issues:
        print("\n   CRITICAL ISSUES:")
        for issue in issues:
            print(f"      • {issue}")

    if warnings_list:
        print("\n   WARNINGS:")
        for warning in warnings_list[:5]:  # Show first 5 warnings
            print(f"      • {warning}")
        if len(warnings_list) > 5:
            print(f"      ... and {len(warnings_list) - 5} more warnings")

    # Recommendations
    print("\n   RECOMMENDATIONS:")
    if results['failed'] > 0:
        if any('gex_history' in i.lower() for i in issues):
            print("      1. Data collector may not be running - deploy latest code with data collector fix")
        if any('database' in i.lower() for i in issues):
            print("      2. Check DATABASE_URL environment variable")
        if any('api' in i.lower() for i in issues):
            print("      3. Check Trading Volatility API credentials")
    else:
        print("      ✅ System appears healthy!")
        if results['warnings'] > 0:
            print("      ⚠️  Review warnings above for potential improvements")

    print("\n" + "="*70)

    # Exit code
    if results['failed'] > 0:
        print("\n🚨 VERIFICATION FAILED - Critical issues detected!")
        sys.exit(1)
    elif results['warnings'] > 3:
        print("\n⚠️  VERIFICATION PASSED WITH WARNINGS")
        sys.exit(0)
    else:
        print("\n✅ VERIFICATION PASSED")
        sys.exit(0)
