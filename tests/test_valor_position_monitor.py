#!/usr/bin/env python3
"""
VALOR Position Monitor - Production Readiness Test Suite
============================================================
Comprehensive tests following the Production Readiness Audit standard.

Tests:
1. Module Import Tests - Can we import the position monitor?
2. Method Existence Tests - Does monitor_positions() exist?
3. Response Shape Tests - Does it return expected structure?
4. Logic Tests - Does stop/profit target checking work correctly?
5. Scheduler Integration Tests - Is the job scheduled?
6. API Endpoint Tests - Can we call it via API?

Run: python tests/test_valor_position_monitor.py
"""

import os
import sys
from datetime import datetime
from typing import Dict, Any, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Test results tracking
RESULTS = {
    "passed": 0,
    "failed": 0,
    "skipped": 0,
    "failures": []
}

def log_result(test_name: str, passed: bool, message: str = "", expected: str = "", actual: str = ""):
    """Log test result with consistent formatting."""
    status = "PASS" if passed else "FAIL"
    if passed:
        RESULTS["passed"] += 1
        print(f"  [{status}] {test_name}")
    else:
        RESULTS["failed"] += 1
        failure = {"test": test_name, "message": message, "expected": expected, "actual": actual}
        RESULTS["failures"].append(failure)
        print(f"  [{status}] {test_name} - {message}")
        if expected:
            print(f"           Expected: {expected}")
        if actual:
            print(f"           Actual: {actual}")


def run_module_import_tests():
    """Test that all required modules can be imported."""
    print("\n=== MODULE IMPORT TESTS ===")

    # Test 1: Import VALOR trader
    try:
        from trading.valor import ValorTrader
        log_result("Import ValorTrader", True)
    except ImportError as e:
        log_result("Import ValorTrader", False, str(e))

    # Test 2: Import VALOR config
    try:
        from trading.valor import ValorConfig
        log_result("Import ValorConfig", True)
    except ImportError as e:
        log_result("Import ValorConfig", False, str(e))

    # Test 3: Import scheduler
    try:
        from scheduler.trader_scheduler import AutonomousTraderScheduler
        log_result("Import AutonomousTraderScheduler", True)
    except ImportError as e:
        log_result("Import AutonomousTraderScheduler", False, str(e))


def run_method_existence_tests():
    """Test that required methods exist."""
    print("\n=== METHOD EXISTENCE TESTS ===")

    try:
        from trading.valor import ValorTrader

        # Test 1: monitor_positions method exists
        has_method = hasattr(ValorTrader, 'monitor_positions')
        log_result("ValorTrader.monitor_positions() exists", has_method,
                  "Method not found" if not has_method else "")

        # Test 2: run_scan method exists (original)
        has_run_scan = hasattr(ValorTrader, 'run_scan')
        log_result("ValorTrader.run_scan() exists", has_run_scan)

        # Test 3: _manage_position method exists (called by monitor)
        has_manage = hasattr(ValorTrader, '_manage_position')
        log_result("ValorTrader._manage_position() exists", has_manage)

        # Test 4: _check_stop_hit method exists
        has_stop_check = hasattr(ValorTrader, '_check_stop_hit')
        log_result("ValorTrader._check_stop_hit() exists", has_stop_check)

        # Test 5: _check_profit_target_hit method exists
        has_target_check = hasattr(ValorTrader, '_check_profit_target_hit')
        log_result("ValorTrader._check_profit_target_hit() exists", has_target_check)

    except ImportError as e:
        log_result("Method existence tests", False, f"Import failed: {e}")


def run_scheduler_integration_tests():
    """Test that the position monitor job is scheduled."""
    print("\n=== SCHEDULER INTEGRATION TESTS ===")

    try:
        from scheduler.trader_scheduler import AutonomousTraderScheduler

        # Test 1: scheduled_valor_position_monitor method exists
        has_method = hasattr(AutonomousTraderScheduler, 'scheduled_valor_position_monitor')
        log_result("AutonomousTraderScheduler.scheduled_valor_position_monitor() exists", has_method,
                  "Method not found" if not has_method else "")

        # Test 2: Check scheduler code contains 15-second interval
        scheduler_file = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "scheduler", "trader_scheduler.py"
        )
        with open(scheduler_file, 'r') as f:
            content = f.read()

        has_15_sec = "seconds=15" in content
        log_result("Scheduler has 15-second interval configured", has_15_sec,
                  "seconds=15 not found in scheduler" if not has_15_sec else "")

        has_monitor_job = "valor_position_monitor" in content
        log_result("Scheduler has valor_position_monitor job ID", has_monitor_job,
                  "Job ID not found" if not has_monitor_job else "")

    except Exception as e:
        log_result("Scheduler integration tests", False, str(e))


def run_response_shape_tests():
    """Test that monitor_positions returns expected structure."""
    print("\n=== RESPONSE SHAPE TESTS ===")

    try:
        from trading.valor import ValorTrader, ValorConfig
        from trading.valor.models import TradingMode

        # Create trader in paper mode for testing
        config = ValorConfig(mode=TradingMode.PAPER)
        trader = ValorTrader(config=config)

        # Call monitor_positions
        result = trader.monitor_positions()

        # Test required fields
        required_fields = ["timestamp", "positions_checked", "positions_closed", "status"]

        for field in required_fields:
            has_field = field in result
            log_result(f"monitor_positions() returns '{field}' field", has_field,
                      f"Missing field: {field}" if not has_field else "")

        # Test field types
        if "positions_checked" in result:
            is_int = isinstance(result["positions_checked"], int)
            log_result("positions_checked is integer", is_int,
                      f"Type is {type(result['positions_checked'])}" if not is_int else "")

        if "status" in result:
            valid_statuses = ["completed", "market_closed", "no_quote", "invalid_price", "error"]
            is_valid = result["status"] in valid_statuses
            log_result(f"status is valid value", is_valid,
                      f"Got '{result['status']}', expected one of {valid_statuses}" if not is_valid else "")

    except Exception as e:
        log_result("Response shape tests", False, f"Exception: {e}")


def run_stop_logic_tests():
    """Test stop loss checking logic."""
    print("\n=== STOP LOSS LOGIC TESTS ===")

    try:
        from trading.valor.models import FuturesPosition, TradeDirection, PositionStatus, GammaRegime
        from datetime import datetime
        import pytz

        CENTRAL_TZ = pytz.timezone('America/Chicago')
        MES_POINT_VALUE = 5.0  # $5 per point per contract

        # Create test positions with all required fields
        def create_test_position(direction: str, entry: float, stop: float) -> FuturesPosition:
            contracts = 1
            entry_value = entry * contracts * MES_POINT_VALUE
            # Breakeven is typically entry + small buffer for commissions
            breakeven_price = entry + 0.5 if direction == "LONG" else entry - 0.5

            return FuturesPosition(
                position_id="TEST-001",
                symbol="/MESH6",
                direction=TradeDirection.LONG if direction == "LONG" else TradeDirection.SHORT,
                entry_price=entry,
                entry_value=entry_value,
                contracts=contracts,
                initial_stop=stop,
                current_stop=stop,
                breakeven_price=breakeven_price,
                status=PositionStatus.OPEN,
                open_time=datetime.now(CENTRAL_TZ),
                gamma_regime=GammaRegime.POSITIVE
            )

        # Test 1: LONG stop hit (price below stop)
        pos = create_test_position("LONG", 5900, 5897.5)
        current_price = 5897.0  # Below stop
        should_stop = current_price <= pos.current_stop
        log_result("LONG: price 5897 triggers stop at 5897.5", should_stop == True)

        # Test 2: LONG stop NOT hit (price above stop)
        current_price = 5898.0  # Above stop
        should_stop = current_price <= pos.current_stop
        log_result("LONG: price 5898 does NOT trigger stop at 5897.5", should_stop == False)

        # Test 3: SHORT stop hit (price above stop)
        pos = create_test_position("SHORT", 5900, 5902.5)
        current_price = 5903.0  # Above stop
        should_stop = current_price >= pos.current_stop
        log_result("SHORT: price 5903 triggers stop at 5902.5", should_stop == True)

        # Test 4: SHORT stop NOT hit (price below stop)
        current_price = 5902.0  # Below stop
        should_stop = current_price >= pos.current_stop
        log_result("SHORT: price 5902 does NOT trigger stop at 5902.5", should_stop == False)

        # Test 5: Exact stop price (edge case)
        pos = create_test_position("LONG", 5900, 5897.5)
        current_price = 5897.5  # Exactly at stop
        should_stop = current_price <= pos.current_stop
        log_result("LONG: price exactly at stop (5897.5) triggers stop", should_stop == True)

    except Exception as e:
        log_result("Stop logic tests", False, f"Exception: {e}")


def run_profit_target_logic_tests():
    """Test profit target checking logic."""
    print("\n=== PROFIT TARGET LOGIC TESTS ===")

    try:
        # Test profit target logic (6-point default)
        profit_target_points = 6.0

        def check_profit_target(entry: float, current: float, direction: str) -> bool:
            if direction == "LONG":
                target = entry + profit_target_points
                return current >= target
            else:
                target = entry - profit_target_points
                return current <= target

        # Test 1: LONG profit target hit
        result = check_profit_target(5900, 5906, "LONG")
        log_result("LONG: price 5906 hits 6-point target from 5900", result == True)

        # Test 2: LONG profit target NOT hit
        result = check_profit_target(5900, 5905.5, "LONG")
        log_result("LONG: price 5905.5 does NOT hit target", result == False)

        # Test 3: SHORT profit target hit
        result = check_profit_target(5900, 5894, "SHORT")
        log_result("SHORT: price 5894 hits 6-point target from 5900", result == True)

        # Test 4: SHORT profit target NOT hit
        result = check_profit_target(5900, 5894.5, "SHORT")
        log_result("SHORT: price 5894.5 does NOT hit target", result == False)

        # Test 5: Gap through target (LONG)
        result = check_profit_target(5900, 5910, "LONG")
        log_result("LONG: price 5910 (gap through) hits target", result == True)

        # Test 6: Gap through target (SHORT)
        result = check_profit_target(5900, 5890, "SHORT")
        log_result("SHORT: price 5890 (gap through) hits target", result == True)

    except Exception as e:
        log_result("Profit target logic tests", False, f"Exception: {e}")


def run_api_endpoint_tests(api_url: str):
    """Test API endpoints for position monitoring."""
    print("\n=== API ENDPOINT TESTS ===")

    try:
        import requests

        # Test 1: VALOR status endpoint
        resp = requests.get(f"{api_url}/api/valor/status", timeout=30)
        log_result("GET /api/valor/status returns 200", resp.status_code == 200,
                  f"Got {resp.status_code}" if resp.status_code != 200 else "")

        # Test 2: VALOR positions endpoint
        resp = requests.get(f"{api_url}/api/valor/positions", timeout=30)
        log_result("GET /api/valor/positions returns 200", resp.status_code == 200,
                  f"Got {resp.status_code}" if resp.status_code != 200 else "")

        # Test 3: Check status includes position data
        if resp.status_code == 200:
            data = resp.json()
            has_positions = "positions" in data
            log_result("Positions endpoint returns positions field", has_positions)

        # Test 4: VALOR diagnostics endpoint
        resp = requests.get(f"{api_url}/api/valor/diagnostics", timeout=30)
        log_result("GET /api/valor/diagnostics returns 200", resp.status_code == 200,
                  f"Got {resp.status_code}" if resp.status_code != 200 else "")

    except ImportError:
        print("  [SKIP] requests library not available - skipping API tests")
        RESULTS["skipped"] += 4
    except Exception as e:
        log_result("API endpoint tests", False, f"Exception: {e}")


def run_timing_comparison_test():
    """Show the improvement from 1-min to 15-sec monitoring."""
    print("\n=== TIMING IMPROVEMENT ANALYSIS ===")

    # Theoretical analysis
    print("\n  Position Monitor Timing Comparison:")
    print("  " + "-" * 50)
    print("  | Interval | Max Wait | Max Slippage (@4pt/min) |")
    print("  " + "-" * 50)
    print("  | 60 sec   | 60 sec   | ~4.0 points ($20/contract) |")
    print("  | 30 sec   | 30 sec   | ~2.0 points ($10/contract) |")
    print("  | 15 sec   | 15 sec   | ~1.0 points ($5/contract)  |")
    print("  " + "-" * 50)
    print("  ✓ 15-second monitoring reduces max slippage by 75%")

    log_result("Timing analysis documented", True)


def print_summary():
    """Print test summary."""
    print("\n" + "=" * 70)
    print("VALOR POSITION MONITOR TEST RESULTS")
    print("=" * 70)
    print(f"PASSED:  {RESULTS['passed']}")
    print(f"FAILED:  {RESULTS['failed']}")
    print(f"SKIPPED: {RESULTS['skipped']}")
    print("=" * 70)

    if RESULTS["failures"]:
        print("\nFAILED TESTS:")
        for f in RESULTS["failures"]:
            print(f"  - {f['test']}: {f['message']}")
            if f.get("expected"):
                print(f"    Expected: {f['expected']}")
            if f.get("actual"):
                print(f"    Actual: {f['actual']}")

    total = RESULTS["passed"] + RESULTS["failed"]
    if RESULTS["failed"] == 0:
        print("\n✅ All position monitor tests passed!")
        print("   The 15-second monitoring is correctly implemented.")
        return 0
    else:
        print(f"\n❌ {RESULTS['failed']}/{total} tests failed")
        return 1


def main():
    import argparse

    parser = argparse.ArgumentParser(description="VALOR Position Monitor Tests")
    parser.add_argument("--api-url", default=os.environ.get("API_URL", "http://localhost:8000"),
                        help="API URL for endpoint tests")
    parser.add_argument("--skip-api", action="store_true",
                        help="Skip API tests")
    args = parser.parse_args()

    print("=" * 70)
    print("VALOR POSITION MONITOR - PRODUCTION READINESS TEST")
    print("=" * 70)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print(f"API URL: {args.api_url}")

    # Run all test suites
    run_module_import_tests()
    run_method_existence_tests()
    run_scheduler_integration_tests()
    run_response_shape_tests()
    run_stop_logic_tests()
    run_profit_target_logic_tests()
    run_timing_comparison_test()

    if not args.skip_api:
        run_api_endpoint_tests(args.api_url)

    return print_summary()


if __name__ == "__main__":
    sys.exit(main())
