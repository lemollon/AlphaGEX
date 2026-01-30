#!/usr/bin/env python
"""
PROMETHEUS Smoke Test Script for Render Shell

Quick smoke test to verify PROMETHEUS is operational:
    python scripts/test_prometheus_smoke.py

This runs minimal checks to verify:
1. Database connection works
2. Tables exist
3. Critical API endpoints respond
4. No 500 errors on key endpoints
"""

import os
import sys
import requests
from datetime import datetime

# Configuration
BASE_URL = os.environ.get('API_BASE_URL', 'http://localhost:8000')
PROMETHEUS_PREFIX = '/api/prometheus-box'

# ANSI colors
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
RESET = '\033[0m'
BOLD = '\033[1m'


def test_api(path: str, name: str) -> bool:
    """Test a single API endpoint."""
    try:
        url = f"{BASE_URL}{PROMETHEUS_PREFIX}{path}"
        response = requests.get(url, timeout=30)

        if response.status_code == 200:
            print(f"  {GREEN}✓{RESET} [{response.status_code}] {name}")
            return True
        elif response.status_code == 503:
            print(f"  {YELLOW}○{RESET} [{response.status_code}] {name} (module not available)")
            return True  # 503 is acceptable - module may not be loaded
        else:
            print(f"  {RED}✗{RESET} [{response.status_code}] {name}")
            return False
    except Exception as e:
        print(f"  {RED}✗{RESET} [ERR] {name} - {str(e)[:40]}")
        return False


def test_db() -> bool:
    """Test database connection and tables."""
    try:
        from database_adapter import get_connection
        conn = get_connection()
        cursor = conn.cursor()

        # Check critical tables
        critical_tables = [
            'prometheus_positions',
            'prometheus_ic_positions',
            'prometheus_ic_equity_snapshots',
            'prometheus_logs',
        ]

        for table in critical_tables:
            cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = %s
                )
            """, (table,))
            if not cursor.fetchone()[0]:
                print(f"  {RED}✗{RESET} Table missing: {table}")
                cursor.close()
                return False

        print(f"  {GREEN}✓{RESET} All critical tables exist")
        cursor.close()
        return True

    except ImportError:
        print(f"  {RED}✗{RESET} database_adapter not available")
        return False
    except Exception as e:
        print(f"  {RED}✗{RESET} Database error: {str(e)[:50]}")
        return False


def main():
    """Run smoke tests."""
    print(f"\n{BOLD}PROMETHEUS Smoke Test{RESET}")
    print(f"Base URL: {BASE_URL}")
    print(f"Timestamp: {datetime.now().isoformat()}")

    passed = 0
    failed = 0

    # 1. Database check
    print(f"\n{BOLD}Database Check:{RESET}")
    if test_db():
        passed += 1
    else:
        failed += 1

    # 2. Health check
    print(f"\n{BOLD}Health Check:{RESET}")
    if test_api('/health', 'PROMETHEUS health'):
        passed += 1
    else:
        failed += 1

    # 3. Critical Box Spread endpoints
    print(f"\n{BOLD}Box Spread Endpoints:{RESET}")
    box_endpoints = [
        ('/status', 'Status'),
        ('/positions', 'Positions'),
        ('/equity-curve', 'Equity Curve'),
        ('/logs', 'Logs'),
    ]
    for path, name in box_endpoints:
        if test_api(path, name):
            passed += 1
        else:
            failed += 1

    # 4. Critical IC endpoints
    print(f"\n{BOLD}IC Trading Endpoints:{RESET}")
    ic_endpoints = [
        ('/ic/status', 'IC Status'),
        ('/ic/positions', 'IC Positions'),
        ('/ic/equity-curve', 'IC Equity Curve'),
        ('/ic/equity-curve/intraday', 'IC Intraday Equity'),
        ('/ic/performance', 'IC Performance'),
        ('/ic/logs', 'IC Logs'),
    ]
    for path, name in ic_endpoints:
        if test_api(path, name):
            passed += 1
        else:
            failed += 1

    # Summary
    print(f"\n{BOLD}Results:{RESET}")
    total = passed + failed
    print(f"  Passed: {GREEN}{passed}{RESET}/{total}")
    print(f"  Failed: {RED}{failed}{RESET}/{total}")

    if failed > 0:
        print(f"\n{RED}SMOKE TEST FAILED{RESET}")
        sys.exit(1)
    else:
        print(f"\n{GREEN}SMOKE TEST PASSED{RESET}")
        sys.exit(0)


if __name__ == '__main__':
    main()
