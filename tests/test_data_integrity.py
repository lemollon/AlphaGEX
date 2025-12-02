#!/usr/bin/env python3
"""
DATA INTEGRITY TESTS
====================
Comprehensive validation of data flow from backend to frontend.
Run these tests on Render to verify:
1. Data is being stored in database
2. Entry prices are valid (not $0.00)
3. Trading Volatility API returns valid data
4. SPX and SPY endpoints all work
5. Data freshness

Usage: python tests/test_data_integrity.py
"""

import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Tuple

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Test results tracking
test_results = {'passed': 0, 'failed': 0, 'warnings': 0}
failures = []
warnings_list = []


def log_pass(test: str, details: str = ""):
    test_results['passed'] += 1
    print(f"✅ {test}: {details}")


def log_fail(test: str, details: str = ""):
    test_results['failed'] += 1
    failures.append(f"{test}: {details}")
    print(f"❌ {test}: {details}")


def log_warn(test: str, details: str = ""):
    test_results['warnings'] += 1
    warnings_list.append(f"{test}: {details}")
    print(f"⚠️  {test}: {details}")


# =============================================================================
# TEST 1: Database Data Storage Verification
# =============================================================================
def test_data_storage():
    """Verify data is being stored in the database today"""
    print("\n" + "="*70)
    print("TEST: DATA STORAGE VERIFICATION")
    print("="*70)

    try:
        from database_adapter import get_connection
        conn = get_connection()
        cursor = conn.cursor()

        today = datetime.now().strftime('%Y-%m-%d')
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')

        tables_to_check = [
            ('gex_history', 'timestamp', 'GEX data'),
            ('regime_signals', 'timestamp', 'Regime signals'),
            ('autonomous_trade_log', 'date', 'Trade log'),
        ]

        print(f"\nChecking data stored today ({today}):")

        for table, date_col, desc in tables_to_check:
            try:
                # Check today
                cursor.execute(f"SELECT COUNT(*) FROM {table} WHERE {date_col}::date = %s", (today,))
                today_count = cursor.fetchone()[0]

                # Check yesterday for comparison
                cursor.execute(f"SELECT COUNT(*) FROM {table} WHERE {date_col}::date = %s", (yesterday,))
                yesterday_count = cursor.fetchone()[0]

                # Check total
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                total = cursor.fetchone()[0]

                print(f"   {desc}: Today={today_count}, Yesterday={yesterday_count}, Total={total}")

                if today_count > 0:
                    log_pass(f"Data Storage - {desc}", f"{today_count} records today")
                elif yesterday_count > 0:
                    log_warn(f"Data Storage - {desc}", f"No data today but {yesterday_count} yesterday")
                else:
                    log_warn(f"Data Storage - {desc}", f"No recent data (total={total})")

            except Exception as e:
                log_warn(f"Data Storage - {desc}", str(e))
                conn.rollback()

        conn.close()

    except Exception as e:
        log_fail("Data Storage Check", str(e))


# =============================================================================
# TEST 2: Entry Price Validation (Critical - No $0.00 entries)
# =============================================================================
def test_entry_prices():
    """Verify entry prices are valid (not $0.00)"""
    print("\n" + "="*70)
    print("TEST: ENTRY PRICE VALIDATION (CRITICAL)")
    print("="*70)

    try:
        from database_adapter import get_connection
        conn = get_connection()
        cursor = conn.cursor()

        # Check open positions
        print("\nChecking open positions for $0 entry prices:")
        cursor.execute("""
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN entry_price IS NULL OR entry_price = 0 THEN 1 ELSE 0 END) as zero_entries
            FROM autonomous_open_positions
        """)
        result = cursor.fetchone()
        total_open = result[0] or 0
        zero_entries_open = result[1] or 0

        if total_open > 0:
            print(f"   Open Positions: {total_open} total, {zero_entries_open} with $0 entry")
            if zero_entries_open > 0:
                log_fail("Open Positions Entry Prices", f"{zero_entries_open}/{total_open} have $0 entry")
            else:
                log_pass("Open Positions Entry Prices", "All entries valid")

        # Check closed trades
        print("\nChecking closed trades for $0 entry prices:")
        cursor.execute("""
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN entry_price IS NULL OR entry_price = 0 THEN 1 ELSE 0 END) as zero_entries
            FROM autonomous_closed_trades
        """)
        result = cursor.fetchone()
        total_closed = result[0] or 0
        zero_entries_closed = result[1] or 0

        if total_closed > 0:
            print(f"   Closed Trades: {total_closed} total, {zero_entries_closed} with $0 entry")
            if zero_entries_closed > 0:
                # Check recent trades specifically
                cursor.execute("""
                    SELECT id, strategy, entry_price, exit_price, entry_date
                    FROM autonomous_closed_trades
                    WHERE entry_price IS NULL OR entry_price = 0
                    ORDER BY exit_date DESC
                    LIMIT 5
                """)
                zero_trades = cursor.fetchall()
                print("   Recent trades with $0 entry:")
                for t in zero_trades:
                    print(f"      ID={t[0]}, Strategy={t[1]}, Entry=${t[2]}, Exit=${t[3]}, Date={t[4]}")

                log_fail("Closed Trades Entry Prices", f"{zero_entries_closed}/{total_closed} have $0 entry (data integrity issue)")
            else:
                log_pass("Closed Trades Entry Prices", "All entries valid")
        else:
            log_warn("Closed Trades Entry Prices", "No closed trades to verify")

        conn.close()

    except Exception as e:
        log_fail("Entry Price Validation", str(e))


# =============================================================================
# TEST 3: Trading Volatility API Data
# =============================================================================
def test_trading_volatility_api():
    """Verify Trading Volatility API returns valid data"""
    print("\n" + "="*70)
    print("TEST: TRADING VOLATILITY API DATA")
    print("="*70)

    try:
        from core_classes_and_engines import TradingVolatilityAPI
        api = TradingVolatilityAPI()

        print("\nTesting TradingVolatilityAPI.get_net_gamma('SPY'):")
        data = api.get_net_gamma('SPY')

        if 'error' in data:
            log_fail("TradingVol API - SPY", f"Error: {data['error']}")
        else:
            print(f"   Spot Price: ${data.get('spot_price', 0):.2f}")
            print(f"   Net GEX: ${data.get('net_gex', 0)/1e9:.2f}B")
            print(f"   Flip Point: ${data.get('flip_point', 0):.2f}")
            print(f"   Call Wall: ${data.get('call_wall') or 0:.2f}")
            print(f"   Put Wall: ${data.get('put_wall') or 0:.2f}")
            print(f"   IV: {data.get('implied_volatility', 0):.1f}%")

            # Validate key fields
            if data.get('spot_price', 0) > 0:
                log_pass("TradingVol API - Spot Price", f"${data['spot_price']:.2f}")
            else:
                log_fail("TradingVol API - Spot Price", "$0 - API may be down")

            if data.get('net_gex', 0) != 0:
                log_pass("TradingVol API - Net GEX", f"${data['net_gex']/1e9:.2f}B")
            else:
                log_warn("TradingVol API - Net GEX", "$0 - may indicate issue")

            if data.get('call_wall') and data.get('call_wall') > 0:
                log_pass("TradingVol API - Call Wall", f"${data['call_wall']:.2f}")
            else:
                log_warn("TradingVol API - Call Wall", "Not available from /gex/latest")

            if data.get('put_wall') and data.get('put_wall') > 0:
                log_pass("TradingVol API - Put Wall", f"${data['put_wall']:.2f}")
            else:
                log_warn("TradingVol API - Put Wall", "Not available from /gex/latest")

    except ImportError as e:
        log_fail("TradingVol API Import", str(e))
    except Exception as e:
        log_fail("TradingVol API", str(e))


# =============================================================================
# TEST 4: REST API Endpoints (SPY and SPX)
# =============================================================================
def test_rest_endpoints():
    """Verify all REST endpoints work"""
    print("\n" + "="*70)
    print("TEST: REST API ENDPOINTS")
    print("="*70)

    try:
        from fastapi.testclient import TestClient
        from backend.main import app
        client = TestClient(app)

        endpoints = [
            # SPY endpoints
            ('GET', '/api/trader/status', 'SPY Trader Status'),
            ('GET', '/api/trader/SPY/positions', 'SPY Positions'),
            ('GET', '/api/trader/performance', 'SPY Performance'),

            # SPX endpoints
            ('GET', '/api/spx/status', 'SPX Trader Status'),
            ('GET', '/api/spx/trades', 'SPX Trades'),
            ('GET', '/api/spx/performance', 'SPX Performance'),
            ('GET', '/api/spx/equity-curve', 'SPX Equity Curve'),

            # GEX endpoints
            ('GET', '/api/gex/SPY', 'GEX Data - SPY'),
            ('GET', '/api/gex/SPY/levels', 'GEX Levels - SPY'),

            # Regime endpoints
            ('GET', '/api/regime/current', 'Current Regime'),
        ]

        print("\nTesting REST API endpoints:")

        for method, endpoint, description in endpoints:
            try:
                if method == 'GET':
                    response = client.get(endpoint)
                else:
                    response = client.post(endpoint)

                if response.status_code == 200:
                    data = response.json()
                    # Check if data has meaningful content
                    if data.get('success') is False:
                        log_warn(f"REST {description}", f"HTTP 200 but success=false: {data.get('error', data.get('message', ''))}")
                    else:
                        log_pass(f"REST {description}", f"HTTP {response.status_code}")
                elif response.status_code == 404:
                    log_warn(f"REST {description}", "Endpoint not found")
                elif response.status_code == 500:
                    log_fail(f"REST {description}", f"HTTP 500 - Server error")
                else:
                    log_warn(f"REST {description}", f"HTTP {response.status_code}")

            except Exception as e:
                log_fail(f"REST {description}", str(e))

    except Exception as e:
        log_fail("REST Endpoints", str(e))


# =============================================================================
# TEST 5: Data Freshness
# =============================================================================
def test_data_freshness():
    """Verify data is fresh (not stale)"""
    print("\n" + "="*70)
    print("TEST: DATA FRESHNESS")
    print("="*70)

    try:
        from database_adapter import get_connection
        conn = get_connection()
        cursor = conn.cursor()

        print("\nChecking data freshness:")

        # Check most recent GEX data
        cursor.execute("""
            SELECT timestamp, spot_price, net_gex
            FROM gex_history
            ORDER BY timestamp DESC
            LIMIT 1
        """)
        gex = cursor.fetchone()
        if gex:
            age_minutes = (datetime.now() - gex[0].replace(tzinfo=None)).total_seconds() / 60
            print(f"   Latest GEX: {gex[0]} (${gex[1]:.2f}, {age_minutes:.0f} min ago)")
            if age_minutes < 60:
                log_pass("GEX Data Freshness", f"{age_minutes:.0f} minutes old")
            elif age_minutes < 360:
                log_warn("GEX Data Freshness", f"{age_minutes:.0f} minutes old (>1 hour)")
            else:
                log_fail("GEX Data Freshness", f"{age_minutes/60:.1f} hours old (very stale)")
        else:
            log_fail("GEX Data Freshness", "No GEX data found")

        # Check most recent regime signal
        cursor.execute("""
            SELECT timestamp, primary_regime_type, risk_level
            FROM regime_signals
            ORDER BY timestamp DESC
            LIMIT 1
        """)
        regime = cursor.fetchone()
        if regime:
            age_minutes = (datetime.now() - regime[0].replace(tzinfo=None)).total_seconds() / 60
            print(f"   Latest Regime: {regime[0]} ({regime[1]}, {age_minutes:.0f} min ago)")
            if age_minutes < 60:
                log_pass("Regime Data Freshness", f"{age_minutes:.0f} minutes old")
            elif age_minutes < 360:
                log_warn("Regime Data Freshness", f"{age_minutes:.0f} minutes old")
            else:
                log_fail("Regime Data Freshness", f"{age_minutes/60:.1f} hours old")
        else:
            log_warn("Regime Data Freshness", "No regime data found")

        # Check position data freshness
        cursor.execute("""
            SELECT updated_at, symbol
            FROM autonomous_open_positions
            ORDER BY updated_at DESC
            LIMIT 1
        """)
        pos = cursor.fetchone()
        if pos:
            age_minutes = (datetime.now() - pos[0].replace(tzinfo=None)).total_seconds() / 60
            print(f"   Latest Position Update: {pos[0]} ({pos[1]}, {age_minutes:.0f} min ago)")
            if age_minutes < 60:
                log_pass("Position Freshness", f"{age_minutes:.0f} minutes old")
            else:
                log_warn("Position Freshness", f"{age_minutes:.0f} minutes old")
        else:
            log_warn("Position Freshness", "No open positions")

        conn.close()

    except Exception as e:
        log_fail("Data Freshness", str(e))


# =============================================================================
# TEST 6: SPX and SPY Feature Parity
# =============================================================================
def test_feature_parity():
    """Verify SPX and SPY have equivalent features"""
    print("\n" + "="*70)
    print("TEST: SPX/SPY FEATURE PARITY")
    print("="*70)

    try:
        from database_adapter import get_connection
        conn = get_connection()
        cursor = conn.cursor()

        print("\nChecking feature parity:")

        # Check config for both symbols
        cursor.execute("""
            SELECT DISTINCT symbol FROM autonomous_open_positions
            UNION
            SELECT DISTINCT symbol FROM autonomous_closed_trades
        """)
        symbols = [r[0] for r in cursor.fetchall()]
        print(f"   Symbols with data: {symbols}")

        # Check position count per symbol
        for symbol in ['SPY', 'SPX']:
            cursor.execute("SELECT COUNT(*) FROM autonomous_open_positions WHERE symbol = %s", (symbol,))
            open_count = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM autonomous_closed_trades WHERE symbol = %s", (symbol,))
            closed_count = cursor.fetchone()[0]
            print(f"   {symbol}: {open_count} open, {closed_count} closed")

            if symbol == 'SPX' and open_count == 0 and closed_count == 0:
                log_warn(f"{symbol} Data", "No SPX trades - SPX trader may not be running")
            elif open_count > 0 or closed_count > 0:
                log_pass(f"{symbol} Data", f"{open_count} open, {closed_count} closed trades")

        conn.close()

    except Exception as e:
        log_fail("Feature Parity", str(e))


# =============================================================================
# MAIN
# =============================================================================
if __name__ == "__main__":
    print("="*70)
    print("DATA INTEGRITY TESTS")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)

    # Run all tests
    test_data_storage()
    test_entry_prices()
    test_trading_volatility_api()
    test_rest_endpoints()
    test_data_freshness()
    test_feature_parity()

    # Summary
    print("\n" + "="*70)
    print("DATA INTEGRITY TEST RESULTS")
    print("="*70)

    print(f"\n✅ Passed:   {test_results['passed']}")
    print(f"❌ Failed:   {test_results['failed']}")
    print(f"⚠️  Warnings: {test_results['warnings']}")

    if failures:
        print("\n❌ FAILURES:")
        for f in failures:
            print(f"   • {f}")

    if warnings_list:
        print("\n⚠️  WARNINGS:")
        for w in warnings_list:
            print(f"   • {w}")

    # Exit with error code if any failures
    if test_results['failed'] > 0:
        print("\n🚨 CRITICAL: Some tests FAILED - data integrity issues detected!")
        sys.exit(1)
    elif test_results['warnings'] > 5:
        print("\n⚠️  WARNING: Multiple warnings - review recommended")
        sys.exit(0)
    else:
        print("\n✅ All critical tests passed")
        sys.exit(0)
