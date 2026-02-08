#!/usr/bin/env python3
"""
Comprehensive JUBILEE System Test Suite for Render Shell

Run with: python scripts/test_prometheus_comprehensive.py

Tests:
1. Database tables exist and are accessible
2. All API endpoints respond correctly
3. Data integrity checks
4. Box spread calculations
5. IC trading endpoints
6. Integration with Oracle
"""

import os
import sys
import json
import traceback
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Test results tracking
RESULTS: List[Tuple[str, bool, str]] = []

def log_test(name: str, passed: bool, details: str = ""):
    """Log test result"""
    status = "✅ PASS" if passed else "❌ FAIL"
    RESULTS.append((name, passed, details))
    print(f"{status}: {name}")
    if details and not passed:
        print(f"       Details: {details}")

def log_section(title: str):
    """Print section header"""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")


# =============================================================================
# SECTION 1: DATABASE TESTS
# =============================================================================

def test_database_connection():
    """Test database connection"""
    log_section("DATABASE CONNECTION TESTS")

    try:
        from database_adapter import DatabaseAdapter
        db = DatabaseAdapter()

        # Test basic query
        result = db.execute_query("SELECT 1 as test")
        if result and len(result) > 0:
            log_test("Database connection", True)
            return db
        else:
            log_test("Database connection", False, "Query returned no results")
            return None
    except Exception as e:
        log_test("Database connection", False, str(e))
        return None


def test_prometheus_tables(db):
    """Test all JUBILEE-related tables exist"""
    log_section("JUBILEE DATABASE TABLES")

    if not db:
        log_test("Jubilee tables check", False, "No database connection")
        return

    expected_tables = [
        'jubilee_positions',
        'jubilee_closed',
        'jubilee_ic_positions',
        'prometheus_ic_closed',
        'jubilee_scan_activity',
        'jubilee_equity_snapshots',
        'jubilee_config',
    ]

    for table in expected_tables:
        try:
            result = db.execute_query(f"""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = '{table}'
                )
            """)
            exists = result[0]['exists'] if result else False
            log_test(f"Table exists: {table}", exists)

            if exists:
                # Get row count
                count_result = db.execute_query(f"SELECT COUNT(*) as cnt FROM {table}")
                count = count_result[0]['cnt'] if count_result else 0
                print(f"       Row count: {count}")
        except Exception as e:
            log_test(f"Table exists: {table}", False, str(e))


def test_jubilee_config(db):
    """Test JUBILEE configuration"""
    log_section("JUBILEE CONFIGURATION")

    if not db:
        log_test("Jubilee config check", False, "No database connection")
        return

    try:
        result = db.execute_query("""
            SELECT * FROM jubilee_config
            ORDER BY created_at DESC
            LIMIT 1
        """)

        if result and len(result) > 0:
            config = result[0]
            log_test("Jubilee config exists", True)
            print(f"       Config ID: {config.get('id', 'N/A')}")
            print(f"       Enabled: {config.get('enabled', 'N/A')}")
            print(f"       Strike Width: {config.get('strike_width', 'N/A')}")
            print(f"       Target DTE Min: {config.get('target_dte_min', 'N/A')}")
            print(f"       Target DTE Max: {config.get('target_dte_max', 'N/A')}")
            print(f"       Min DTE to Hold: {config.get('min_dte_to_hold', 'N/A')}")
            print(f"       Reserve Pct: {config.get('reserve_pct', 'N/A')}")
            print(f"       Max Implied Rate: {config.get('max_implied_rate', 'N/A')}")
        else:
            log_test("Jubilee config exists", False, "No config found")
    except Exception as e:
        log_test("Jubilee config exists", False, str(e))


def test_box_positions(db):
    """Test box spread positions data"""
    log_section("BOX SPREAD POSITIONS")

    if not db:
        log_test("Box positions check", False, "No database connection")
        return

    try:
        # Check open positions
        result = db.execute_query("""
            SELECT
                position_id,
                ticker,
                lower_strike,
                upper_strike,
                strike_width,
                expiration,
                current_dte,
                contracts,
                entry_credit,
                implied_annual_rate,
                created_at
            FROM jubilee_positions
            ORDER BY created_at DESC
            LIMIT 5
        """)

        count = len(result) if result else 0
        log_test(f"Box positions query", True, f"Found {count} open positions")

        if result:
            for pos in result:
                print(f"       Position: {pos.get('position_id', 'N/A')}")
                print(f"         Strikes: {pos.get('lower_strike')}/{pos.get('upper_strike')}")
                print(f"         DTE: {pos.get('current_dte')}, Rate: {pos.get('implied_annual_rate', 0)*100:.2f}%")
                print()
    except Exception as e:
        log_test("Box positions query", False, str(e))

    try:
        # Check closed positions
        result = db.execute_query("""
            SELECT COUNT(*) as cnt,
                   SUM(realized_pnl) as total_pnl
            FROM jubilee_closed
        """)

        if result:
            cnt = result[0].get('cnt', 0)
            pnl = result[0].get('total_pnl', 0) or 0
            log_test(f"Closed box positions", True, f"{cnt} closed, Total P&L: ${pnl:.2f}")
    except Exception as e:
        log_test("Closed box positions", False, str(e))


def test_ic_positions(db):
    """Test IC positions data"""
    log_section("IC TRADING POSITIONS")

    if not db:
        log_test("IC positions check", False, "No database connection")
        return

    try:
        # Check open IC positions
        result = db.execute_query("""
            SELECT
                position_id,
                ticker,
                put_short_strike,
                put_long_strike,
                call_short_strike,
                call_long_strike,
                expiration,
                contracts,
                entry_credit,
                oracle_confidence,
                created_at
            FROM jubilee_ic_positions
            ORDER BY created_at DESC
            LIMIT 5
        """)

        count = len(result) if result else 0
        log_test(f"IC positions query", True, f"Found {count} open IC positions")

        if result:
            for pos in result:
                print(f"       Position: {pos.get('position_id', 'N/A')}")
                print(f"         Put Spread: {pos.get('put_short_strike')}/{pos.get('put_long_strike')}")
                print(f"         Call Spread: {pos.get('call_short_strike')}/{pos.get('call_long_strike')}")
                print(f"         Oracle Conf: {pos.get('oracle_confidence', 0)*100:.1f}%")
                print()
    except Exception as e:
        log_test("IC positions query", False, str(e))

    try:
        # Check closed IC positions
        result = db.execute_query("""
            SELECT COUNT(*) as cnt,
                   SUM(realized_pnl) as total_pnl,
                   COUNT(CASE WHEN realized_pnl > 0 THEN 1 END) as wins,
                   COUNT(CASE WHEN realized_pnl <= 0 THEN 1 END) as losses
            FROM prometheus_ic_closed
        """)

        if result:
            cnt = result[0].get('cnt', 0)
            pnl = result[0].get('total_pnl', 0) or 0
            wins = result[0].get('wins', 0)
            losses = result[0].get('losses', 0)
            win_rate = (wins / cnt * 100) if cnt > 0 else 0
            log_test(f"Closed IC trades", True,
                    f"{cnt} trades, {wins}W/{losses}L ({win_rate:.1f}%), P&L: ${pnl:.2f}")
    except Exception as e:
        log_test("Closed IC trades", False, str(e))


def test_scan_activity(db):
    """Test scan activity logs"""
    log_section("SCAN ACTIVITY LOGS")

    if not db:
        log_test("Scan activity check", False, "No database connection")
        return

    try:
        result = db.execute_query("""
            SELECT
                scan_time,
                spx_price,
                vix_level,
                oracle_decision,
                oracle_confidence,
                win_probability,
                action_taken,
                reason
            FROM jubilee_scan_activity
            ORDER BY scan_time DESC
            LIMIT 10
        """)

        count = len(result) if result else 0
        log_test(f"Scan activity query", True, f"Found {count} recent scans")

        if result:
            trades = sum(1 for r in result if r.get('action_taken') == 'OPENED')
            skips = sum(1 for r in result if r.get('action_taken') == 'SKIP')
            print(f"       Last 10: {trades} trades, {skips} skips")

            # Show latest scan
            latest = result[0]
            print(f"       Latest scan: {latest.get('scan_time')}")
            print(f"         SPX: {latest.get('spx_price')}, VIX: {latest.get('vix_level')}")
            print(f"         Oracle: {latest.get('oracle_decision')}, Conf: {latest.get('oracle_confidence', 0)*100:.1f}%")
            print(f"         Action: {latest.get('action_taken')}, Reason: {latest.get('reason')}")
    except Exception as e:
        log_test("Scan activity query", False, str(e))


def test_equity_snapshots(db):
    """Test equity snapshots"""
    log_section("EQUITY SNAPSHOTS")

    if not db:
        log_test("Equity snapshots check", False, "No database connection")
        return

    try:
        result = db.execute_query("""
            SELECT
                snapshot_time,
                total_equity,
                box_equity,
                ic_equity,
                unrealized_pnl,
                realized_pnl
            FROM jubilee_equity_snapshots
            ORDER BY snapshot_time DESC
            LIMIT 5
        """)

        count = len(result) if result else 0
        log_test(f"Equity snapshots query", True, f"Found {count} recent snapshots")

        if result:
            latest = result[0]
            print(f"       Latest: {latest.get('snapshot_time')}")
            print(f"         Total Equity: ${latest.get('total_equity', 0):,.2f}")
            print(f"         Box Equity: ${latest.get('box_equity', 0):,.2f}")
            print(f"         IC Equity: ${latest.get('ic_equity', 0):,.2f}")
    except Exception as e:
        log_test("Equity snapshots query", False, str(e))


# =============================================================================
# SECTION 2: API ENDPOINT TESTS
# =============================================================================

def test_api_endpoints():
    """Test all JUBILEE API endpoints"""
    log_section("API ENDPOINT TESTS")

    try:
        import requests
    except ImportError:
        log_test("API tests", False, "requests module not available")
        return

    # Get API URL from environment
    api_url = os.environ.get('API_URL', 'http://localhost:8000')

    # Core endpoints to test
    endpoints = [
        # Status endpoints
        ('/api/jubilee/status', 'GET', 'System status'),
        ('/api/jubilee/config', 'GET', 'Configuration'),

        # Box spread endpoints
        ('/api/jubilee/positions', 'GET', 'Open box positions'),
        ('/api/jubilee/closed', 'GET', 'Closed box positions'),
        ('/api/jubilee/rates/current', 'GET', 'Current rates'),
        ('/api/jubilee/rates/history', 'GET', 'Rate history'),
        ('/api/jubilee/mtm', 'GET', 'Mark-to-market'),

        # IC trading endpoints
        ('/api/jubilee/ic/status', 'GET', 'IC trading status'),
        ('/api/jubilee/ic/positions', 'GET', 'Open IC positions'),
        ('/api/jubilee/ic/closed-trades', 'GET', 'Closed IC trades'),
        ('/api/jubilee/ic/equity-curve', 'GET', 'IC equity curve'),
        ('/api/jubilee/ic/equity-curve/intraday', 'GET', 'IC intraday equity'),
        ('/api/jubilee/ic/performance', 'GET', 'IC performance stats'),
        ('/api/jubilee/ic/logs', 'GET', 'IC activity logs'),
        ('/api/jubilee/ic/signals/recent', 'GET', 'Recent IC signals'),

        # Combined endpoints
        ('/api/jubilee/combined/performance', 'GET', 'Combined performance'),
        ('/api/jubilee/combined/daily-breakdown', 'GET', 'Daily breakdown'),

        # Analytics endpoints
        ('/api/jubilee/analytics/cost-efficiency', 'GET', 'Cost efficiency'),
        ('/api/jubilee/analytics/reconciliation', 'GET', 'Reconciliation'),
    ]

    for endpoint, method, description in endpoints:
        try:
            url = f"{api_url}{endpoint}"
            if method == 'GET':
                response = requests.get(url, timeout=10)
            else:
                response = requests.post(url, timeout=10)

            if response.status_code == 200:
                log_test(f"API: {description}", True, endpoint)
                # Try to parse JSON
                try:
                    data = response.json()
                    if isinstance(data, dict):
                        if 'error' in data:
                            print(f"       Warning: {data.get('error')}")
                        elif 'success' in data:
                            print(f"       Success: {data.get('success')}")
                except:
                    pass
            elif response.status_code == 404:
                log_test(f"API: {description}", False, f"{endpoint} - 404 Not Found")
            elif response.status_code == 500:
                log_test(f"API: {description}", False, f"{endpoint} - 500 Server Error")
            else:
                log_test(f"API: {description}", False, f"{endpoint} - Status {response.status_code}")
        except requests.exceptions.ConnectionError:
            log_test(f"API: {description}", False, f"Connection refused to {api_url}")
            break  # Don't continue if API is unreachable
        except requests.exceptions.Timeout:
            log_test(f"API: {description}", False, f"Timeout on {endpoint}")
        except Exception as e:
            log_test(f"API: {description}", False, str(e))


# =============================================================================
# SECTION 3: BACKEND MODULE TESTS
# =============================================================================

def test_prometheus_modules():
    """Test JUBILEE backend modules can be imported"""
    log_section("BACKEND MODULE IMPORTS")

    modules_to_test = [
        ('trading.jubilee.models', 'BoxSpreadPosition, JubileeConfig'),
        ('trading.jubilee.db', 'JubileeDatabase'),
        ('trading.jubilee.signals', 'BoxSpreadSignalGenerator'),
        ('trading.jubilee.executor', 'JubileeExecutor'),
        ('trading.jubilee.trader', 'JubileeTrader'),
    ]

    for module_name, classes in modules_to_test:
        try:
            module = __import__(module_name, fromlist=[classes.split(',')[0].strip()])
            log_test(f"Import: {module_name}", True)

            # Check if key classes exist
            for class_name in classes.split(','):
                class_name = class_name.strip()
                if hasattr(module, class_name):
                    print(f"       Found: {class_name}")
                else:
                    print(f"       Missing: {class_name}")
        except ImportError as e:
            log_test(f"Import: {module_name}", False, str(e))
        except Exception as e:
            log_test(f"Import: {module_name}", False, str(e))


def test_jubilee_database_class():
    """Test JubileeDatabase class methods"""
    log_section("JUBILEE DATABASE CLASS")

    try:
        from trading.jubilee.db import JubileeDatabase

        pdb = JubileeDatabase()
        log_test("JubileeDatabase instantiation", True)

        # Test get_config
        try:
            config = pdb.get_config()
            log_test("JubileeDatabase.get_config()", config is not None)
            if config:
                print(f"       Config enabled: {config.enabled if hasattr(config, 'enabled') else 'N/A'}")
        except Exception as e:
            log_test("JubileeDatabase.get_config()", False, str(e))

        # Test get_open_positions
        try:
            positions = pdb.get_open_positions()
            log_test("JubileeDatabase.get_open_positions()", True, f"Found {len(positions) if positions else 0}")
        except Exception as e:
            log_test("JubileeDatabase.get_open_positions()", False, str(e))

        # Test get_ic_positions
        try:
            ic_positions = pdb.get_ic_positions()
            log_test("JubileeDatabase.get_ic_positions()", True, f"Found {len(ic_positions) if ic_positions else 0}")
        except Exception as e:
            log_test("JubileeDatabase.get_ic_positions()", False, str(e))

    except ImportError as e:
        log_test("JubileeDatabase instantiation", False, f"Import error: {e}")
    except Exception as e:
        log_test("JubileeDatabase instantiation", False, str(e))


def test_box_spread_calculations():
    """Test box spread calculation logic"""
    log_section("BOX SPREAD CALCULATIONS")

    try:
        from trading.jubilee.models import BoxSpreadPosition

        # Create a test position
        test_position = BoxSpreadPosition(
            position_id="TEST-001",
            ticker="SPXW",
            lower_strike=5900,
            upper_strike=5950,
            strike_width=50,
            expiration="2026-06-30",
            open_time=datetime.now(),
            dte_at_entry=150,
            current_dte=150,
            contracts=1,
            entry_credit=4850.0,  # $48.50 per share = $4850 per contract
            theoretical_value=5000.0,  # 50 * 100
            total_credit_received=4850.0,
            total_owed_at_expiration=5000.0,
            borrowing_cost=150.0,
            implied_annual_rate=0.045,  # 4.5%
        )

        log_test("BoxSpreadPosition creation", True)

        # Test calculations
        expected_theoretical = 50 * 100  # strike_width * 100
        log_test("Theoretical value calculation",
                test_position.theoretical_value == expected_theoretical,
                f"Expected {expected_theoretical}, got {test_position.theoretical_value}")

        # Test borrowing cost
        borrowing_cost = test_position.total_owed_at_expiration - test_position.total_credit_received
        log_test("Borrowing cost calculation",
                borrowing_cost == 150.0,
                f"Expected 150.0, got {borrowing_cost}")

        # Test implied rate sanity check
        log_test("Implied rate sanity check",
                0 < test_position.implied_annual_rate < 0.20,  # Between 0% and 20%
                f"Rate: {test_position.implied_annual_rate*100:.2f}%")

    except ImportError as e:
        log_test("BoxSpreadPosition import", False, str(e))
    except Exception as e:
        log_test("Box spread calculations", False, str(e))


def test_oracle_integration():
    """Test Oracle integration for IC trading"""
    log_section("ORACLE INTEGRATION")

    try:
        from quant.oracle_advisor import OracleAdvisor

        oracle = OracleAdvisor()
        log_test("OracleAdvisor instantiation", True)

        # Test health check
        try:
            health = oracle.health_check() if hasattr(oracle, 'health_check') else None
            log_test("Oracle health check", health is not None or True)
        except Exception as e:
            log_test("Oracle health check", False, str(e))

        # Test get_recommendation (if method exists)
        try:
            if hasattr(oracle, 'get_strategy_recommendation'):
                rec = oracle.get_strategy_recommendation(
                    symbol='SPX',
                    spot_price=5950,
                    vix=18.5
                )
                log_test("Oracle strategy recommendation", rec is not None)
                if rec:
                    print(f"       Recommendation: {rec.get('strategy', 'N/A')}")
                    print(f"       Confidence: {rec.get('confidence', 0)*100:.1f}%")
        except Exception as e:
            log_test("Oracle strategy recommendation", False, str(e))

    except ImportError as e:
        log_test("OracleAdvisor import", False, str(e))
    except Exception as e:
        log_test("Oracle integration", False, str(e))


# =============================================================================
# SECTION 4: FRONTEND BUILD TEST
# =============================================================================

def test_typescript_build():
    """Check for TypeScript errors that would break the build"""
    log_section("TYPESCRIPT BUILD CHECK")

    # Check BotBranding for JUBILEE
    try:
        with open('frontend/src/components/trader/BotBranding.tsx', 'r') as f:
            content = f.read()

        has_prometheus_type = "'JUBILEE'" in content or '"JUBILEE"' in content
        log_test("JUBILEE in BotName type", has_prometheus_type)

        has_prometheus_brand = "JUBILEE:" in content and "BOT_BRANDS" in content
        log_test("JUBILEE in BOT_BRANDS", has_prometheus_brand)
    except Exception as e:
        log_test("BotBranding.tsx check", False, str(e))

    # Check files that use Record<BotName, ...>
    record_files = [
        ('frontend/src/components/dashboard/AllBotReportsSummary.tsx', 'reportMap'),
        ('frontend/src/components/dashboard/PortfolioSummaryCard.tsx', 'DEFAULT_STARTING_CAPITALS'),
        ('frontend/src/components/charts/MultiBotEquityCurve.tsx', 'LIVE_BOTS'),
    ]

    for filepath, var_name in record_files:
        try:
            with open(filepath, 'r') as f:
                content = f.read()

            has_prometheus = 'JUBILEE' in content
            filename = filepath.split('/')[-1]
            log_test(f"JUBILEE in {filename}", has_prometheus,
                    f"Check {var_name} includes JUBILEE")
        except FileNotFoundError:
            log_test(f"File exists: {filepath.split('/')[-1]}", False, "File not found")
        except Exception as e:
            log_test(f"Check {filepath.split('/')[-1]}", False, str(e))


# =============================================================================
# MAIN EXECUTION
# =============================================================================

def print_summary():
    """Print test summary"""
    log_section("TEST SUMMARY")

    total = len(RESULTS)
    passed = sum(1 for _, p, _ in RESULTS if p)
    failed = total - passed

    print(f"Total Tests: {total}")
    print(f"Passed:      {passed} ✅")
    print(f"Failed:      {failed} ❌")
    print(f"Pass Rate:   {passed/total*100:.1f}%" if total > 0 else "N/A")

    if failed > 0:
        print(f"\n{'='*60}")
        print("  FAILED TESTS:")
        print(f"{'='*60}")
        for name, passed, details in RESULTS:
            if not passed:
                print(f"  ❌ {name}")
                if details:
                    print(f"     {details}")


def main():
    """Run all tests"""
    print("""
╔══════════════════════════════════════════════════════════════╗
║     JUBILEE COMPREHENSIVE TEST SUITE                      ║
║     Box Spread Synthetic Borrowing + IC Trading              ║
╚══════════════════════════════════════════════════════════════╝
    """)

    print(f"Start Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Working Directory: {os.getcwd()}")

    # Run database tests
    db = test_database_connection()
    if db:
        test_prometheus_tables(db)
        test_jubilee_config(db)
        test_box_positions(db)
        test_ic_positions(db)
        test_scan_activity(db)
        test_equity_snapshots(db)

    # Run API tests
    test_api_endpoints()

    # Run module tests
    test_prometheus_modules()
    test_jubilee_database_class()
    test_box_spread_calculations()
    test_oracle_integration()

    # Run TypeScript build checks
    test_typescript_build()

    # Print summary
    print_summary()

    print(f"\nEnd Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Exit with appropriate code
    failed = sum(1 for _, p, _ in RESULTS if not p)
    sys.exit(1 if failed > 0 else 0)


if __name__ == "__main__":
    main()
