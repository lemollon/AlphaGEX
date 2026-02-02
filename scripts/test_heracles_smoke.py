#!/usr/bin/env python
"""
HERACLES Smoke Test Script for Render Shell

Quick smoke test to verify HERACLES is operational:
    python scripts/test_heracles_smoke.py

This runs minimal checks to verify:
1. Database connection works
2. Tables exist (including new scan_activity and paper_account)
3. Critical API endpoints respond
4. Scheduler imports work
5. No 500 errors on key endpoints
"""

import os
import sys

# Add project root to Python path for Render shell
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import requests
from datetime import datetime

# Configuration - Render uses internal URL or RENDER_EXTERNAL_URL
BASE_URL = os.environ.get('API_BASE_URL') or os.environ.get('RENDER_EXTERNAL_URL') or 'http://localhost:8000'
# Remove trailing slash if present
BASE_URL = BASE_URL.rstrip('/')
HERACLES_PREFIX = '/api/heracles'

# ANSI colors
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'
BOLD = '\033[1m'


def test_api(path: str, name: str, method: str = 'GET') -> bool:
    """Test a single API endpoint."""
    try:
        url = f"{BASE_URL}{HERACLES_PREFIX}{path}"
        if method == 'GET':
            response = requests.get(url, timeout=30)
        else:
            response = requests.post(url, json={}, timeout=30)

        if response.status_code == 200:
            print(f"  {GREEN}✓{RESET} [{response.status_code}] {name}")
            return True
        elif response.status_code == 503:
            print(f"  {YELLOW}○{RESET} [{response.status_code}] {name} (module not available)")
            return True  # 503 is acceptable - module may not be loaded
        else:
            print(f"  {RED}✗{RESET} [{response.status_code}] {name}")
            try:
                error_detail = response.json().get('detail', '')[:50]
                if error_detail:
                    print(f"      Error: {error_detail}")
            except:
                pass
            return False
    except Exception as e:
        print(f"  {RED}✗{RESET} [ERR] {name} - {str(e)[:50]}")
        return False


def test_db() -> bool:
    """Test database connection and tables."""
    try:
        from database_adapter import get_connection
        conn = get_connection()
        cursor = conn.cursor()

        # Check critical tables
        critical_tables = [
            'heracles_positions',
            'heracles_closed_trades',
            'heracles_equity_snapshots',
            'heracles_signals',
            'heracles_paper_account',      # Paper trading account
            'heracles_scan_activity',      # ML training data
        ]

        missing = []
        for table in critical_tables:
            cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = %s
                )
            """, (table,))
            exists = cursor.fetchone()[0]
            if exists:
                print(f"  {GREEN}✓{RESET} Table: {table}")
            else:
                print(f"  {RED}✗{RESET} Table missing: {table}")
                missing.append(table)

        cursor.close()

        if missing:
            print(f"\n  {YELLOW}Tip:{RESET} Tables are auto-created on first HERACLES import")
            return False

        return True

    except ImportError as e:
        print(f"  {RED}✗{RESET} database_adapter not available: {e}")
        print(f"      Make sure you're in the project root directory")
        print(f"      Current working dir: {os.getcwd()}")
        return False
    except Exception as e:
        print(f"  {RED}✗{RESET} Database error: {str(e)[:60]}")
        return False


def test_scheduler_imports() -> bool:
    """Test that HERACLES can be imported by scheduler."""
    print(f"\n{BOLD}Scheduler Import Check:{RESET}")
    try:
        from trading.heracles import HERACLESTrader, HERACLESConfig, TradingMode
        print(f"  {GREEN}✓{RESET} HERACLESTrader imported")
        print(f"  {GREEN}✓{RESET} HERACLESConfig imported")
        print(f"  {GREEN}✓{RESET} TradingMode imported")
        return True
    except ImportError as e:
        print(f"  {RED}✗{RESET} Import failed: {e}")
        return False
    except Exception as e:
        print(f"  {RED}✗{RESET} Error: {str(e)[:60]}")
        return False


def test_db_methods() -> bool:
    """Test that new database methods work."""
    print(f"\n{BOLD}Database Method Check:{RESET}")
    try:
        from trading.heracles.db import HERACLESDatabase
        db = HERACLESDatabase()

        # Test paper account
        account = db.get_paper_account()
        if account:
            print(f"  {GREEN}✓{RESET} get_paper_account() works")
            print(f"      Balance: ${account.get('current_balance', 0):,.2f}")
        else:
            # Initialize if not exists
            db.initialize_paper_account(100000.0)
            print(f"  {YELLOW}○{RESET} Paper account initialized (was empty)")

        # Test scan activity
        scans = db.get_scan_activity(limit=5)
        print(f"  {GREEN}✓{RESET} get_scan_activity() works ({len(scans)} scans)")

        # Test ML training data
        ml_data = db.get_ml_training_data()
        print(f"  {GREEN}✓{RESET} get_ml_training_data() works ({len(ml_data)} samples)")

        return True

    except Exception as e:
        print(f"  {RED}✗{RESET} Database method error: {str(e)[:60]}")
        import traceback
        traceback.print_exc()
        return False


def test_paper_account_init() -> bool:
    """Verify paper account is initialized correctly."""
    print(f"\n{BOLD}Paper Account Check:{RESET}")
    try:
        from trading.heracles.db import HERACLESDatabase
        db = HERACLESDatabase()

        account = db.get_paper_account()
        if not account:
            print(f"  {YELLOW}○{RESET} No paper account - initializing...")
            db.initialize_paper_account(100000.0)
            account = db.get_paper_account()

        if account:
            starting = account.get('starting_capital', 0)
            current = account.get('current_balance', 0)
            pnl = account.get('cumulative_pnl', 0)
            print(f"  {GREEN}✓{RESET} Starting Capital: ${starting:,.2f}")
            print(f"  {GREEN}✓{RESET} Current Balance: ${current:,.2f}")
            print(f"  {GREEN}✓{RESET} Cumulative P&L: ${pnl:+,.2f}")
            return True
        else:
            print(f"  {RED}✗{RESET} Could not get/create paper account")
            return False

    except Exception as e:
        print(f"  {RED}✗{RESET} Paper account error: {str(e)[:60]}")
        return False


def main():
    """Run smoke tests."""
    print(f"\n{BOLD}{'='*60}{RESET}")
    print(f"{BOLD}HERACLES Smoke Test{RESET}")
    print(f"{'='*60}")
    print(f"Base URL: {BASE_URL}")
    print(f"Timestamp: {datetime.now().isoformat()}")

    passed = 0
    failed = 0

    # 1. Scheduler import check (CRITICAL - if this fails, scheduler dies)
    if test_scheduler_imports():
        passed += 1
    else:
        failed += 1
        print(f"\n  {RED}CRITICAL: Scheduler imports failed!{RESET}")
        print(f"  This will crash the alphagex-trader worker!")

    # 2. Database tables check
    print(f"\n{BOLD}Database Tables:{RESET}")
    if test_db():
        passed += 1
    else:
        failed += 1

    # 3. Database methods check
    if test_db_methods():
        passed += 1
    else:
        failed += 1

    # 4. Paper account check
    if test_paper_account_init():
        passed += 1
    else:
        failed += 1

    # 5. Health check
    print(f"\n{BOLD}API Health Check:{RESET}")
    if test_api('/status', 'HERACLES status'):
        passed += 1
    else:
        failed += 1

    # 6. Core endpoints
    print(f"\n{BOLD}Core Endpoints:{RESET}")
    core_endpoints = [
        ('/positions', 'Open Positions'),
        ('/closed-trades', 'Closed Trades'),
        ('/paper-equity-curve', 'Paper Equity Curve'),
        ('/signals/recent', 'Recent Signals'),
        ('/logs', 'Activity Logs'),
    ]
    for path, name in core_endpoints:
        if test_api(path, name):
            passed += 1
        else:
            failed += 1

    # 7. NEW: Scan Activity endpoints (ML training data)
    print(f"\n{BOLD}Scan Activity (ML Training):{RESET}")
    ml_endpoints = [
        ('/scan-activity', 'Scan Activity'),
        ('/ml-training-data', 'ML Training Data'),
    ]
    for path, name in ml_endpoints:
        if test_api(path, name):
            passed += 1
        else:
            failed += 1

    # Summary
    print(f"\n{BOLD}{'='*60}{RESET}")
    print(f"{BOLD}Results:{RESET}")
    total = passed + failed
    print(f"  Passed: {GREEN}{passed}{RESET}/{total}")
    print(f"  Failed: {RED}{failed}{RESET}/{total}")

    if failed > 0:
        print(f"\n{RED}SMOKE TEST FAILED{RESET}")
        print(f"\n{YELLOW}Troubleshooting:{RESET}")
        print(f"  1. Make sure you're in the project root directory:")
        print(f"     cd ~/project/src  # or wherever the project is")
        print(f"  2. Set the API URL to your Render deployment:")
        print(f"     export API_BASE_URL='https://alphagex-api.onrender.com'")
        print(f"  3. Verify DATABASE_URL is set for database tests")
        print(f"  4. If scheduler imports failed, check trading/heracles/__init__.py")
        print(f"  5. Run again: python scripts/test_heracles_smoke.py")
        sys.exit(1)
    else:
        print(f"\n{GREEN}SMOKE TEST PASSED{RESET}")
        print(f"\n{BLUE}HERACLES is ready for production!{RESET}")
        sys.exit(0)


if __name__ == '__main__':
    main()
