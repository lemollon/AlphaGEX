#!/usr/bin/env python3
"""
test_logging_system.py - Validation Script for AlphaGEX Logging System

This script validates that all logging infrastructure is working correctly:
1. Database tables exist and can accept data
2. Logging functions capture and store data
3. API routes return logged data
4. Export functionality generates valid files

Run with: python tests/test_logging_system.py
"""

import sys
import os
import json
from datetime import datetime, timedelta
from typing import Dict, List, Tuple

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Track test results
RESULTS: List[Tuple[str, bool, str]] = []


def log_result(test_name: str, passed: bool, message: str = ""):
    """Log a test result."""
    status = "PASS" if passed else "FAIL"
    RESULTS.append((test_name, passed, message))
    emoji = "\u2705" if passed else "\u274c"
    print(f"  {emoji} {test_name}: {message}" if message else f"  {emoji} {test_name}")


def test_database_connection():
    """Test 1: Database connection works."""
    print("\n--- Test 1: Database Connection ---")
    try:
        from database_adapter import get_connection
        conn = get_connection()
        conn.close()
        log_result("Database connection", True, "Successfully connected to PostgreSQL")
        return True
    except Exception as e:
        log_result("Database connection", False, str(e))
        return False


def test_trading_decisions_table():
    """Test 2: trading_decisions table exists and has correct schema."""
    print("\n--- Test 2: trading_decisions Table ---")
    try:
        from database_adapter import get_connection
        conn = get_connection()
        c = conn.cursor()

        # Check table exists
        c.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'trading_decisions'
            )
        """)
        exists = c.fetchone()[0]
        log_result("Table exists", exists, "trading_decisions table found" if exists else "Table not found")

        if not exists:
            conn.close()
            return False

        # Check key columns exist
        c.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'trading_decisions'
        """)
        columns = [row[0] for row in c.fetchall()]

        required_columns = ['id', 'timestamp', 'bot_name', 'decision_type', 'action', 'symbol', 'reason']
        missing = [col for col in required_columns if col not in columns]

        if missing:
            log_result("Required columns", False, f"Missing: {missing}")
        else:
            log_result("Required columns", True, f"All {len(required_columns)} required columns present")

        # Get row count
        c.execute("SELECT COUNT(*) FROM trading_decisions")
        count = c.fetchone()[0]
        log_result("Row count", True, f"{count} decision records in database")

        conn.close()
        return len(missing) == 0
    except Exception as e:
        log_result("Table check", False, str(e))
        return False


def test_decision_logger_import():
    """Test 3: DecisionLogger can be imported and initialized."""
    print("\n--- Test 3: DecisionLogger Import ---")
    try:
        from trading.decision_logger import DecisionLogger, get_lazarus_logger, get_cornerstone_logger, get_fortress_logger
        log_result("Import DecisionLogger", True)

        # Test bot-specific getters
        lazarus = get_lazarus_logger()
        log_result("Get LAZARUS logger", True, f"Bot: {lazarus.bot_name}")

        cornerstone = get_cornerstone_logger()
        log_result("Get CORNERSTONE logger", True, f"Bot: {cornerstone.bot_name}")

        fortress = get_fortress_logger()
        log_result("Get FORTRESS logger", True, f"Bot: {fortress.bot_name}")

        return True
    except Exception as e:
        log_result("DecisionLogger import", False, str(e))
        return False


def test_log_decision():
    """Test 4: Can log a test decision to database."""
    print("\n--- Test 4: Log Test Decision ---")
    try:
        from trading.decision_logger import (
            DecisionLogger, TradeDecision, MarketContext, get_lazarus_logger
        )

        logger = get_lazarus_logger()

        # Create test decision
        test_decision = TradeDecision(
            decision_type="TEST_VALIDATION",
            action="STAY_FLAT",
            symbol="TEST",
            strategy="test_logging_system.py",
            reason="Automated validation test - verifying logging system works",
            confidence=100,
            market_context=MarketContext(
                spot_price=5900.0,
                vix=15.0,
                net_gex=1000000000,
                regime="POSITIVE_GEX_ABOVE_FLIP"
            )
        )

        # Log it
        decision_id = logger.log_decision(test_decision)

        if decision_id:
            log_result("Log decision", True, f"Logged test decision ID: {decision_id}")

            # Verify it's in database
            from database_adapter import get_connection
            conn = get_connection()
            c = conn.cursor()
            c.execute("SELECT id, bot_name, decision_type FROM trading_decisions WHERE id = %s", (decision_id,))
            row = c.fetchone()
            conn.close()

            if row:
                log_result("Verify in database", True, f"Found: bot={row[1]}, type={row[2]}")
                return True
            else:
                log_result("Verify in database", False, "Decision not found in database")
                return False
        else:
            log_result("Log decision", False, "No decision ID returned")
            return False
    except Exception as e:
        log_result("Log decision", False, str(e))
        return False


def test_export_functions():
    """Test 5: Export functions work correctly."""
    print("\n--- Test 5: Export Functions ---")
    try:
        from trading.decision_logger import export_decisions_json, export_decisions_csv

        # Test JSON export
        json_data = export_decisions_json(limit=5)
        log_result("JSON export", True, f"Exported {len(json_data)} records")

        # Test CSV export
        csv_content = export_decisions_csv(limit=5)
        lines = csv_content.strip().split('\n') if csv_content else []
        log_result("CSV export", True, f"Generated {len(lines)} lines (including header)")

        return True
    except Exception as e:
        log_result("Export functions", False, str(e))
        return False


def test_api_routes():
    """Test 6: API routes respond correctly."""
    print("\n--- Test 6: API Routes ---")

    # Try to import and test API routes directly
    try:
        import requests
        api_base = os.getenv('API_URL', 'http://localhost:8000')

        # Test /api/trader/logs/recent
        try:
            response = requests.get(f"{api_base}/api/trader/logs/recent?limit=5", timeout=5)
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    log_result("GET /api/trader/logs/recent", True, f"Returned {data.get('data', {}).get('count', 0)} records")
                else:
                    log_result("GET /api/trader/logs/recent", False, "API returned success=false")
            else:
                log_result("GET /api/trader/logs/recent", False, f"Status {response.status_code}")
        except requests.exceptions.ConnectionError:
            log_result("GET /api/trader/logs/recent", False, "API server not running (connection refused)")
        except Exception as e:
            log_result("GET /api/trader/logs/recent", False, str(e))

        # Test /api/trader/logs/summary
        try:
            response = requests.get(f"{api_base}/api/trader/logs/summary?days=7", timeout=5)
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    summary = data.get('data', {}).get('summary', {})
                    log_result("GET /api/trader/logs/summary", True,
                              f"Total decisions: {summary.get('total_decisions', 0)}")
                else:
                    log_result("GET /api/trader/logs/summary", False, "API returned success=false")
            else:
                log_result("GET /api/trader/logs/summary", False, f"Status {response.status_code}")
        except requests.exceptions.ConnectionError:
            log_result("GET /api/trader/logs/summary", False, "API server not running")
        except Exception as e:
            log_result("GET /api/trader/logs/summary", False, str(e))

        return True
    except ImportError:
        log_result("API routes", False, "requests library not installed (pip install requests)")
        return False


def test_bot_specific_logging():
    """Test 7: Each bot can log independently."""
    print("\n--- Test 7: Bot-Specific Logging ---")
    try:
        from trading.decision_logger import (
            get_lazarus_logger, get_cornerstone_logger, get_fortress_logger,
            get_shepherd_logger, get_prophet_logger, TradeDecision, MarketContext
        )

        bots = {
            'LAZARUS': get_lazarus_logger(),
            'CORNERSTONE': get_cornerstone_logger(),
            'FORTRESS': get_fortress_logger(),
            'SHEPHERD': get_shepherd_logger(),
            'PROPHET': get_prophet_logger(),
        }

        for bot_name, logger in bots.items():
            if logger.bot_name == bot_name:
                log_result(f"{bot_name} logger", True, f"Correctly configured")
            else:
                log_result(f"{bot_name} logger", False, f"Wrong bot_name: {logger.bot_name}")

        return True
    except Exception as e:
        log_result("Bot-specific logging", False, str(e))
        return False


def test_filter_by_bot():
    """Test 8: Can filter decisions by bot."""
    print("\n--- Test 8: Filter by Bot ---")
    try:
        from trading.decision_logger import export_decisions_json

        # Get all decisions
        all_decisions = export_decisions_json(limit=100)

        # Get LAZARUS decisions
        lazarus_decisions = export_decisions_json(bot_name='LAZARUS', limit=100)

        log_result("All bots query", True, f"Found {len(all_decisions)} total decisions")
        log_result("LAZARUS filter", True, f"Found {len(lazarus_decisions)} LAZARUS decisions")

        # Verify LAZARUS decisions are actually from LAZARUS
        if lazarus_decisions:
            all_lazarus = all(d.get('bot_name') == 'LAZARUS' for d in lazarus_decisions)
            log_result("Filter accuracy", all_lazarus,
                      "All filtered records are LAZARUS" if all_lazarus else "Filter returned wrong bot")

        return True
    except Exception as e:
        log_result("Filter by bot", False, str(e))
        return False


def cleanup_test_data():
    """Cleanup test decisions from database."""
    print("\n--- Cleanup ---")
    try:
        from database_adapter import get_connection
        conn = get_connection()
        c = conn.cursor()

        # Delete test decisions
        c.execute("DELETE FROM trading_decisions WHERE decision_type = 'TEST_VALIDATION'")
        deleted = c.rowcount
        conn.commit()
        conn.close()

        log_result("Cleanup test data", True, f"Removed {deleted} test records")
    except Exception as e:
        log_result("Cleanup", False, str(e))


def print_summary():
    """Print summary of all test results."""
    print("\n" + "=" * 60)
    print("LOGGING SYSTEM VALIDATION SUMMARY")
    print("=" * 60)

    passed = sum(1 for _, p, _ in RESULTS if p)
    failed = sum(1 for _, p, _ in RESULTS if not p)
    total = len(RESULTS)

    print(f"\nTotal Tests: {total}")
    print(f"Passed: {passed} (\u2705)")
    print(f"Failed: {failed} (\u274c)")
    print(f"Success Rate: {passed/total*100:.1f}%")

    if failed > 0:
        print("\nFailed Tests:")
        for name, passed, msg in RESULTS:
            if not passed:
                print(f"  - {name}: {msg}")

    print("\n" + "=" * 60)

    if failed == 0:
        print("\u2705 ALL TESTS PASSED - Logging system is working correctly!")
        print("\nYou can now:")
        print("  1. Start the backend: cd backend && python -m uvicorn api.main:app --reload")
        print("  2. Start the frontend: cd frontend && npm run dev")
        print("  3. Navigate to /logs to view the master logs page")
        print("  4. View bot-specific logs on each bot's page")
    else:
        print("\u274c SOME TESTS FAILED - Please review the errors above")
        print("\nCommon fixes:")
        print("  - Ensure PostgreSQL is running and DATABASE_URL is set")
        print("  - Run migrations: python db/config_and_database.py")
        print("  - Check that API server is running for API tests")

    return failed == 0


def main():
    """Run all validation tests."""
    print("=" * 60)
    print("AlphaGEX Logging System Validation")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # Run tests in order
    db_ok = test_database_connection()

    if db_ok:
        test_trading_decisions_table()
        test_decision_logger_import()
        test_log_decision()
        test_export_functions()
        test_bot_specific_logging()
        test_filter_by_bot()
        test_api_routes()
        cleanup_test_data()

    # Print summary
    success = print_summary()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
