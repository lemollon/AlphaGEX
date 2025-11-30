#!/usr/bin/env python3
"""
COMPREHENSIVE DATA FLOW VERIFICATION TEST

This script tests every API endpoint and verifies that:
1. Real data is being returned (not fake/static)
2. Data has actual timestamps (recent)
3. Data contains expected fields
4. Database tables have real data

Run this to prove data is flowing correctly.
"""

import os
import sys
import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Any, Tuple
import requests

# Configuration
API_BASE_URL = os.getenv('API_BASE_URL', 'http://localhost:8000')
FRONTEND_URL = os.getenv('FRONTEND_URL', 'http://localhost:3000')

# Results tracking
results = {
    'passed': [],
    'failed': [],
    'warnings': [],
    'no_data': []
}

def log_pass(test_name: str, details: str = ""):
    """Log a passed test"""
    results['passed'].append({'test': test_name, 'details': details})
    print(f"✅ PASS: {test_name}")
    if details:
        print(f"   └── {details}")

def log_fail(test_name: str, reason: str):
    """Log a failed test"""
    results['failed'].append({'test': test_name, 'reason': reason})
    print(f"❌ FAIL: {test_name}")
    print(f"   └── {reason}")

def log_warning(test_name: str, message: str):
    """Log a warning"""
    results['warnings'].append({'test': test_name, 'message': message})
    print(f"⚠️  WARN: {test_name}")
    print(f"   └── {message}")

def log_no_data(test_name: str, message: str):
    """Log when no data is found"""
    results['no_data'].append({'test': test_name, 'message': message})
    print(f"📭 NO DATA: {test_name}")
    print(f"   └── {message}")

def is_recent_timestamp(timestamp_str: str, max_age_days: int = 30) -> bool:
    """Check if a timestamp is recent (within max_age_days)"""
    try:
        # Try various timestamp formats
        formats = [
            '%Y-%m-%dT%H:%M:%S.%fZ',
            '%Y-%m-%dT%H:%M:%SZ',
            '%Y-%m-%dT%H:%M:%S',
            '%Y-%m-%d %H:%M:%S.%f',
            '%Y-%m-%d %H:%M:%S',
            '%Y-%m-%d',
        ]
        for fmt in formats:
            try:
                ts = datetime.strptime(timestamp_str[:26], fmt)
                age = datetime.now() - ts
                return age.days <= max_age_days
            except ValueError:
                continue
        return False
    except:
        return False

def has_real_values(data: Dict, required_fields: List[str]) -> Tuple[bool, str]:
    """Check if data has real (non-null, non-placeholder) values"""
    for field in required_fields:
        if field not in data:
            return False, f"Missing field: {field}"
        value = data[field]
        if value is None:
            return False, f"Null value for: {field}"
        if isinstance(value, str) and value in ['N/A', 'null', 'undefined', '', 'PLACEHOLDER']:
            return False, f"Placeholder value for: {field}"
    return True, "All required fields present"

def test_api_endpoint(endpoint: str, expected_fields: List[str], test_name: str):
    """Test an API endpoint for real data"""
    url = f"{API_BASE_URL}{endpoint}"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()

            # Check if it's a list
            if isinstance(data, list):
                if len(data) == 0:
                    log_no_data(test_name, f"Empty list returned from {endpoint}")
                    return False
                data = data[0]  # Check first item

            # Check if it's wrapped in a response object
            if isinstance(data, dict) and 'data' in data:
                data = data['data']
                if isinstance(data, list):
                    if len(data) == 0:
                        log_no_data(test_name, f"Empty data array from {endpoint}")
                        return False
                    data = data[0]

            # Verify real values
            valid, msg = has_real_values(data, expected_fields)
            if valid:
                # Check for timestamps
                timestamp_fields = ['timestamp', 'created_at', 'date', 'entry_date']
                has_timestamp = False
                for tf in timestamp_fields:
                    if tf in data and data[tf]:
                        has_timestamp = True
                        if is_recent_timestamp(str(data[tf])):
                            log_pass(test_name, f"Real data with recent timestamp: {data[tf]}")
                        else:
                            log_warning(test_name, f"Data exists but timestamp is old: {data[tf]}")
                        break

                if not has_timestamp:
                    log_pass(test_name, f"Real data returned (no timestamp field)")
                return True
            else:
                log_fail(test_name, msg)
                return False
        elif response.status_code == 404:
            log_no_data(test_name, f"Endpoint {endpoint} not found (404)")
            return False
        else:
            log_fail(test_name, f"HTTP {response.status_code} from {endpoint}")
            return False
    except requests.exceptions.ConnectionError:
        log_fail(test_name, f"Cannot connect to {url} - is the server running?")
        return False
    except Exception as e:
        log_fail(test_name, f"Error: {str(e)}")
        return False

def test_database_tables():
    """Test database tables for data directly"""
    print("\n" + "=" * 80)
    print("DATABASE TABLE VERIFICATION")
    print("=" * 80)

    try:
        from database_adapter import get_connection
        conn = get_connection()
        c = conn.cursor()

        # Tables that MUST have data
        critical_tables = [
            ('gex_history', 'GEX History (core data)'),
            ('regime_signals', 'Psychology Regime Signals'),
            ('backtest_results', 'Backtest Results'),
        ]

        # Tables that SHOULD have data
        important_tables = [
            ('autonomous_closed_trades', 'Closed Trades'),
            ('autonomous_open_positions', 'Open Positions'),
            ('autonomous_equity_snapshots', 'Equity Curve'),
            ('market_data', 'Market Data Snapshots'),
            ('probability_predictions', 'ML Predictions'),
            ('probability_outcomes', 'ML Outcomes'),
        ]

        # Tables for the new ML data
        ml_tables = [
            ('price_history', 'Historical Prices (NEW)'),
            ('greeks_snapshots', 'Greeks Snapshots (NEW)'),
            ('vix_term_structure', 'VIX Term Structure (NEW)'),
            ('options_flow', 'Options Flow (NEW)'),
            ('ai_analysis_history', 'AI Analysis History (NEW)'),
            ('market_snapshots', 'Market Snapshots (NEW)'),
        ]

        print("\n--- CRITICAL TABLES (must have data) ---")
        for table, desc in critical_tables:
            try:
                c.execute(f"SELECT COUNT(*) FROM {table}")
                count = c.fetchone()[0]

                # Get latest timestamp
                latest = None
                try:
                    c.execute(f"SELECT MAX(timestamp) FROM {table}")
                    latest = c.fetchone()[0]
                except:
                    try:
                        c.execute(f"SELECT MAX(created_at) FROM {table}")
                        latest = c.fetchone()[0]
                    except:
                        pass

                if count > 0:
                    log_pass(f"DB: {desc}", f"{count} rows, latest: {latest}")
                else:
                    log_fail(f"DB: {desc}", f"TABLE EMPTY - no data stored!")
            except Exception as e:
                log_fail(f"DB: {desc}", f"Table error: {e}")

        print("\n--- IMPORTANT TABLES (should have data) ---")
        for table, desc in important_tables:
            try:
                c.execute(f"SELECT COUNT(*) FROM {table}")
                count = c.fetchone()[0]
                if count > 0:
                    log_pass(f"DB: {desc}", f"{count} rows")
                else:
                    log_no_data(f"DB: {desc}", "Empty - needs data collection")
            except Exception as e:
                log_warning(f"DB: {desc}", f"Table may not exist: {e}")

        print("\n--- NEW ML TABLES (for comprehensive analysis) ---")
        for table, desc in ml_tables:
            try:
                c.execute(f"SELECT COUNT(*) FROM {table}")
                count = c.fetchone()[0]
                if count > 0:
                    log_pass(f"DB: {desc}", f"{count} rows")
                else:
                    log_no_data(f"DB: {desc}", "Empty - data collection not active yet")
            except Exception as e:
                log_warning(f"DB: {desc}", f"Table doesn't exist yet - run init_database")

        conn.close()
        return True

    except ImportError:
        log_fail("Database Connection", "Cannot import database_adapter")
        return False
    except Exception as e:
        log_fail("Database Connection", f"DATABASE_URL not set or connection failed: {e}")
        return False

def test_all_api_endpoints():
    """Test all API endpoints for real data"""
    print("\n" + "=" * 80)
    print("API ENDPOINT VERIFICATION")
    print("=" * 80)

    # Define all endpoints with their expected fields
    endpoints = [
        # GEX Data
        ('/api/gex/SPY', ['net_gex', 'flip_point'], 'GEX: SPY Live Data'),
        ('/api/gex/SPY/levels', ['call_wall', 'put_wall'], 'GEX: Level Zones'),

        # Gamma Intelligence
        ('/api/gamma/SPY/intelligence', ['primary_view'], 'Gamma: Intelligence'),
        ('/api/gamma/SPY/levels', ['levels'], 'Gamma: Levels'),

        # VIX
        ('/api/vix/current', ['vix', 'change_pct'], 'VIX: Current Level'),
        ('/api/vix/hedge-signal', ['signal'], 'VIX: Hedge Signal'),

        # Psychology
        ('/api/psychology/current-regime', ['regime_type'], 'Psychology: Current Regime'),
        ('/api/psychology/history', [], 'Psychology: History'),

        # Trader
        ('/api/trader/status', ['status'], 'Trader: Status'),
        ('/api/trader/positions', [], 'Trader: Open Positions'),
        ('/api/trader/closed-trades', [], 'Trader: Closed Trades'),
        ('/api/trader/equity-curve', [], 'Trader: Equity Curve'),
        ('/api/trader/performance', [], 'Trader: Performance'),

        # Backtest
        ('/api/backtest/results', [], 'Backtest: Results'),
        ('/api/backtest/summary', [], 'Backtest: Summary'),

        # Database
        ('/api/database/status', ['status'], 'Database: Status'),
        ('/api/database/stats', [], 'Database: Table Stats'),

        # Health
        ('/health', ['status'], 'System: Health Check'),
    ]

    print("\n--- Testing API Endpoints ---\n")

    for endpoint, fields, name in endpoints:
        test_api_endpoint(endpoint, fields, name)

def print_summary():
    """Print final summary"""
    print("\n" + "=" * 80)
    print("VERIFICATION SUMMARY")
    print("=" * 80)

    total = len(results['passed']) + len(results['failed']) + len(results['no_data'])

    print(f"\n✅ PASSED: {len(results['passed'])} tests")
    print(f"❌ FAILED: {len(results['failed'])} tests")
    print(f"📭 NO DATA: {len(results['no_data'])} endpoints/tables")
    print(f"⚠️  WARNINGS: {len(results['warnings'])}")

    if results['failed']:
        print("\n--- FAILURES (must fix) ---")
        for fail in results['failed']:
            print(f"  • {fail['test']}: {fail['reason']}")

    if results['no_data']:
        print("\n--- NO DATA (needs data collection) ---")
        for nd in results['no_data']:
            print(f"  • {nd['test']}: {nd['message']}")

    print("\n" + "=" * 80)

    if results['failed']:
        print("⛔ VERIFICATION FAILED - Some endpoints are broken!")
        return False
    elif results['no_data']:
        print("⚠️  VERIFICATION INCOMPLETE - Data collection needed!")
        return False
    else:
        print("✅ VERIFICATION PASSED - All data is flowing correctly!")
        return True

def main():
    """Main entry point"""
    print("=" * 80)
    print("ALPHAGEX DATA FLOW VERIFICATION")
    print("=" * 80)
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"API URL: {API_BASE_URL}")
    print("=" * 80)

    # Test database first
    test_database_tables()

    # Then test API endpoints
    test_all_api_endpoints()

    # Print summary
    success = print_summary()

    # Save results to file
    with open('/home/user/AlphaGEX/data_verification_results.json', 'w') as f:
        json.dump({
            'timestamp': datetime.now().isoformat(),
            'results': results,
            'success': success
        }, f, indent=2)

    print(f"\nResults saved to: data_verification_results.json")

    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())
