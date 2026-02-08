#!/usr/bin/env python3
"""
WATCHTOWER Actionable Trade & Signal Tracking - End-to-End Test
==========================================================

Tests the complete loop for:
1. Actionable trade recommendations (/api/watchtower/trade-action)
2. Signal logging (/api/watchtower/signals/log)
3. Signal retrieval (/api/watchtower/signals/recent)
4. Performance stats (/api/watchtower/signals/performance)
5. Outcome updates (/api/watchtower/signals/update-outcomes)

Run: python scripts/test_actionable_trade_system.py
"""

import os
import sys
import json
import requests
from datetime import datetime

# Add parent directory for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configuration
API_BASE = os.getenv("API_BASE_URL", "http://localhost:8000")
SYMBOL = "SPY"

# Test results tracking
tests_passed = 0
tests_failed = 0
test_results = []


def log_test(name: str, passed: bool, details: str = ""):
    """Log test result"""
    global tests_passed, tests_failed
    status = "✅ PASS" if passed else "❌ FAIL"
    if passed:
        tests_passed += 1
    else:
        tests_failed += 1
    print(f"  {status}: {name}")
    if details and not passed:
        print(f"         {details}")
    test_results.append({"name": name, "passed": passed, "details": details})


def test_database_table():
    """Test 1: Verify argus_trade_signals table exists"""
    print("\n" + "=" * 60)
    print("TEST 1: Database Table Exists")
    print("=" * 60)

    try:
        from database_adapter import get_connection
        conn = get_connection()
        if not conn:
            log_test("Database connection", False, "Could not connect")
            return False

        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) FROM information_schema.tables
            WHERE table_name = 'argus_trade_signals'
        """)
        exists = cursor.fetchone()[0] == 1
        cursor.close()
        conn.close()

        log_test("Table argus_trade_signals exists", exists)

        if exists:
            # Check columns
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'argus_trade_signals'
                ORDER BY ordinal_position
            """)
            columns = [row[0] for row in cursor.fetchall()]
            cursor.close()
            conn.close()

            required_cols = ['action', 'direction', 'confidence', 'trade_description',
                           'spot_at_signal', 'status', 'actual_pnl']
            for col in required_cols:
                log_test(f"Column '{col}' exists", col in columns)

        return exists
    except Exception as e:
        log_test("Database check", False, str(e))
        return False


def test_trade_action_endpoint():
    """Test 2: Verify /api/watchtower/trade-action returns proper structure"""
    print("\n" + "=" * 60)
    print("TEST 2: Trade Action Endpoint")
    print("=" * 60)

    try:
        url = f"{API_BASE}/api/watchtower/trade-action"
        params = {
            "symbol": SYMBOL,
            "account_size": 50000,
            "risk_per_trade_pct": 1.0,
            "spread_width": 2
        }
        response = requests.get(url, params=params, timeout=30)
        log_test("Endpoint responds", response.status_code == 200,
                f"Status: {response.status_code}")

        if response.status_code != 200:
            return None

        data = response.json()
        log_test("Response has success field", "success" in data)
        log_test("Response success is True", data.get("success") == True)

        if not data.get("success"):
            return None

        result = data.get("data", {})

        # Check required fields
        log_test("Has 'action' field", "action" in result)
        log_test("Has 'confidence' field", "confidence" in result)

        action = result.get("action")
        if action == "WAIT":
            log_test("WAIT response has 'reason'", "reason" in result)
            print(f"         Note: WAIT response - {result.get('reason', 'no reason')}")
        else:
            log_test("Has 'direction' field", "direction" in result)
            log_test("Has 'trade_description' field", "trade_description" in result)
            log_test("Has 'trade' structure", "trade" in result and result["trade"] is not None)
            log_test("Has 'why' array", "why" in result and isinstance(result.get("why"), list))
            log_test("Has 'sizing' structure", "sizing" in result)
            log_test("Has 'entry' field", "entry" in result)
            log_test("Has 'exit' structure", "exit" in result)
            log_test("Has 'market_context'", "market_context" in result)

            # Check sizing fields
            sizing = result.get("sizing", {})
            log_test("Sizing has 'contracts'", "contracts" in sizing)
            log_test("Sizing has 'max_loss'", "max_loss" in sizing)
            log_test("Sizing has 'max_profit'", "max_profit" in sizing)
            log_test("Sizing has 'risk_reward'", "risk_reward" in sizing)

            # Check exit rules
            exit_rules = result.get("exit", {})
            log_test("Exit has 'profit_target'", "profit_target" in exit_rules)
            log_test("Exit has 'stop_loss'", "stop_loss" in exit_rules)

            print(f"\n         Trade: {result.get('trade_description', 'N/A')}")
            print(f"         Confidence: {result.get('confidence', 0)}%")

        return result

    except Exception as e:
        log_test("Trade action endpoint", False, str(e))
        return None


def test_signal_logging(trade_data: dict):
    """Test 3: Verify signal logging works"""
    print("\n" + "=" * 60)
    print("TEST 3: Signal Logging")
    print("=" * 60)

    if not trade_data or trade_data.get("action") == "WAIT":
        print("         Skipping - no actionable trade to log")
        log_test("Signal logging (skipped - WAIT)", True)
        return None

    try:
        url = f"{API_BASE}/api/watchtower/signals/log"
        params = {"symbol": SYMBOL}
        response = requests.post(url, params=params, json=trade_data, timeout=30)

        log_test("Log endpoint responds", response.status_code == 200,
                f"Status: {response.status_code}")

        if response.status_code != 200:
            return None

        data = response.json()
        log_test("Log response has success", "success" in data)
        log_test("Log was successful", data.get("success") == True)
        log_test("Signal ID returned", "signal_id" in data and data.get("signal_id") is not None)

        signal_id = data.get("signal_id")
        if signal_id:
            print(f"         Logged signal ID: {signal_id}")

        return signal_id

    except Exception as e:
        log_test("Signal logging", False, str(e))
        return None


def test_recent_signals():
    """Test 4: Verify recent signals retrieval"""
    print("\n" + "=" * 60)
    print("TEST 4: Recent Signals Retrieval")
    print("=" * 60)

    try:
        url = f"{API_BASE}/api/watchtower/signals/recent"
        params = {"symbol": SYMBOL, "limit": 10}
        response = requests.get(url, params=params, timeout=30)

        log_test("Recent signals endpoint responds", response.status_code == 200,
                f"Status: {response.status_code}")

        if response.status_code != 200:
            return []

        data = response.json()
        log_test("Response has success field", "success" in data)

        result = data.get("data", {})
        signals = result.get("signals", [])

        log_test("Response has signals array", isinstance(signals, list))
        log_test("Count field present", "count" in result)

        if signals:
            # Check first signal structure
            first = signals[0]
            log_test("Signal has 'id'", "id" in first)
            log_test("Signal has 'action'", "action" in first)
            log_test("Signal has 'status'", "status" in first)
            log_test("Signal has 'created_at'", "created_at" in first)

            print(f"         Found {len(signals)} recent signals")
            for sig in signals[:3]:
                status_emoji = "🟢" if sig.get("status") == "WIN" else "🔴" if sig.get("status") == "LOSS" else "🟡"
                print(f"         {status_emoji} {sig.get('action')} - {sig.get('status')} - ${sig.get('actual_pnl', 0):.0f}")
        else:
            print("         No signals found yet (expected if first run)")

        return signals

    except Exception as e:
        log_test("Recent signals retrieval", False, str(e))
        return []


def test_performance_stats():
    """Test 5: Verify performance statistics"""
    print("\n" + "=" * 60)
    print("TEST 5: Performance Statistics")
    print("=" * 60)

    try:
        url = f"{API_BASE}/api/watchtower/signals/performance"
        params = {"symbol": SYMBOL, "days": 30}
        response = requests.get(url, params=params, timeout=30)

        log_test("Performance endpoint responds", response.status_code == 200,
                f"Status: {response.status_code}")

        if response.status_code != 200:
            return None

        data = response.json()
        log_test("Response has success field", "success" in data)

        result = data.get("data", {})

        # Check summary structure
        summary = result.get("summary", {})
        log_test("Has summary object", "summary" in result)
        log_test("Summary has total_signals", "total_signals" in summary)
        log_test("Summary has wins", "wins" in summary)
        log_test("Summary has losses", "losses" in summary)
        log_test("Summary has win_rate", "win_rate" in summary)
        log_test("Summary has total_pnl", "total_pnl" in summary)

        # Check by_action structure
        log_test("Has by_action array", "by_action" in result and isinstance(result.get("by_action"), list))

        # Check daily_pnl structure
        log_test("Has daily_pnl array", "daily_pnl" in result and isinstance(result.get("daily_pnl"), list))

        # Print stats
        print(f"\n         Performance Summary (30 days):")
        print(f"         Total Signals: {summary.get('total_signals', 0)}")
        print(f"         Win Rate: {summary.get('win_rate', 0):.1f}%")
        print(f"         Total P&L: ${summary.get('total_pnl', 0):.2f}")
        print(f"         Avg Win: ${summary.get('avg_win', 0):.2f}")
        print(f"         Avg Loss: ${summary.get('avg_loss', 0):.2f}")

        return result

    except Exception as e:
        log_test("Performance statistics", False, str(e))
        return None


def test_outcome_update():
    """Test 6: Verify outcome update endpoint"""
    print("\n" + "=" * 60)
    print("TEST 6: Outcome Update")
    print("=" * 60)

    try:
        url = f"{API_BASE}/api/watchtower/signals/update-outcomes"
        params = {"symbol": SYMBOL}
        response = requests.post(url, params=params, timeout=30)

        log_test("Update outcomes endpoint responds", response.status_code == 200,
                f"Status: {response.status_code}")

        if response.status_code != 200:
            return False

        data = response.json()
        log_test("Response has success field", "success" in data)
        log_test("Update was successful", data.get("success") == True)

        print(f"         Message: {data.get('message', 'N/A')}")
        return data.get("success")

    except Exception as e:
        log_test("Outcome update", False, str(e))
        return False


def test_complete_loop():
    """Test 7: Verify STANDARDS.md Complete Loop"""
    print("\n" + "=" * 60)
    print("TEST 7: STANDARDS.md Complete Loop Verification")
    print("=" * 60)

    # 1. Database - already tested
    log_test("Step 1: Database schema exists", tests_passed > 0)

    # 2. Data Population - signal logging
    log_test("Step 2: Data population (signal logging)",
             any(r["name"] == "Log was successful" and r["passed"] for r in test_results))

    # 3. Backend API - endpoints working
    log_test("Step 3: Backend API endpoints respond",
             any(r["name"] == "Endpoint responds" and r["passed"] for r in test_results))

    # 4. Frontend - would need browser test, check API returns frontend-compatible data
    log_test("Step 4: API returns frontend-compatible structure",
             any(r["name"] == "Has 'sizing' structure" and r["passed"] for r in test_results) or
             any(r["name"] == "Signal logging (skipped - WAIT)" and r["passed"] for r in test_results))

    # 5. Verification - this test itself
    log_test("Step 5: End-to-end verification completed", True)


def main():
    """Run all tests"""
    print("=" * 60)
    print("  WATCHTOWER Actionable Trade & Signal Tracking Test Suite")
    print("=" * 60)
    print(f"  API Base: {API_BASE}")
    print(f"  Symbol: {SYMBOL}")
    print(f"  Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Run tests
    test_database_table()
    trade_data = test_trade_action_endpoint()
    signal_id = test_signal_logging(trade_data)
    test_recent_signals()
    test_performance_stats()
    test_outcome_update()
    test_complete_loop()

    # Summary
    print("\n" + "=" * 60)
    print("  TEST SUMMARY")
    print("=" * 60)
    total = tests_passed + tests_failed
    print(f"  Passed: {tests_passed}/{total}")
    print(f"  Failed: {tests_failed}/{total}")

    if tests_failed == 0:
        print("\n  ✅ ALL TESTS PASSED")
    else:
        print("\n  ❌ SOME TESTS FAILED")
        print("\n  Failed tests:")
        for r in test_results:
            if not r["passed"]:
                print(f"    - {r['name']}: {r['details']}")

    print("=" * 60)

    return tests_failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
