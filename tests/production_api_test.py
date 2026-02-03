#!/usr/bin/env python3
"""
AlphaGEX Production API Test Suite
===================================
Tests ALL backend endpoints against LIVE API for production readiness.

Run: python tests/production_api_test.py --api-url https://your-app.onrender.com
"""

import os
import sys
import json
import argparse
import time
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple

try:
    import requests
except ImportError:
    print("ERROR: requests library required. Install with: pip install requests")
    sys.exit(1)

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

def test_endpoint_exists(base_url: str, endpoint: str, method: str = "GET",
                         expected_status: int = 200, data: dict = None) -> Tuple[bool, Any]:
    """Test that an endpoint exists and returns expected status code."""
    url = f"{base_url}{endpoint}"
    try:
        if method == "GET":
            resp = requests.get(url, timeout=30)
        elif method == "POST":
            resp = requests.post(url, json=data or {}, timeout=30)
        else:
            return False, f"Unsupported method: {method}"

        return resp.status_code == expected_status, resp
    except requests.exceptions.RequestException as e:
        return False, str(e)

def test_response_shape(response: requests.Response, required_fields: List[str]) -> Tuple[bool, str]:
    """Verify response JSON contains required fields."""
    try:
        data = response.json()
        missing = [f for f in required_fields if f not in data]
        if missing:
            return False, f"Missing fields: {missing}"
        return True, ""
    except json.JSONDecodeError:
        return False, "Response is not valid JSON"

def run_endpoint_existence_tests(base_url: str):
    """Test that all expected endpoints exist."""
    print("\n=== ENDPOINT EXISTENCE TESTS ===")

    # Core health endpoints
    core_endpoints = [
        ("/health", "GET", 200),
        ("/api/time", "GET", 200),
        ("/api/system-health", "GET", 200),
    ]

    # HERACLES endpoints (MES Futures)
    heracles_endpoints = [
        ("/api/heracles/status", "GET", 200),
        ("/api/heracles/positions", "GET", 200),
        ("/api/heracles/closed-trades", "GET", 200),
        ("/api/heracles/paper-equity-curve", "GET", 200),
        ("/api/heracles/equity-curve/intraday", "GET", 200),
        ("/api/heracles/scan-activity", "GET", 200),
        ("/api/heracles/ml-training-data", "GET", 200),
        ("/api/heracles/ml/status", "GET", 200),
        ("/api/heracles/ml/feature-importance", "GET", 200),
        ("/api/heracles/ml/approval-status", "GET", 200),
        ("/api/heracles/ab-test/status", "GET", 200),
        ("/api/heracles/ab-test/results", "GET", 200),
        ("/api/heracles/diagnostics", "GET", 200),
        ("/api/heracles/config", "GET", 200),
        ("/api/heracles/win-tracker", "GET", 200),
    ]

    # PROMETHEUS endpoints (Box Spread + IC)
    prometheus_endpoints = [
        ("/api/prometheus-box/status", "GET", 200),
        ("/api/prometheus-box/positions", "GET", 200),
        ("/api/prometheus-box/equity-curve", "GET", 200),
        ("/api/prometheus-box/equity-curve/intraday", "GET", 200),
        ("/api/prometheus-box/analytics/rates", "GET", 200),
        ("/api/prometheus-box/analytics/capital-flow", "GET", 200),
        ("/api/prometheus-box/ic/status", "GET", 200),
        ("/api/prometheus-box/ic/positions", "GET", 200),
        ("/api/prometheus-box/ic/equity-curve", "GET", 200),
        ("/api/prometheus-box/ic/equity-curve/intraday", "GET", 200),
        ("/api/prometheus-box/ic/performance", "GET", 200),
        ("/api/prometheus-box/combined/performance", "GET", 200),
        ("/api/prometheus-box/reconciliation", "GET", 200),
    ]

    # ARES endpoints (SPY Iron Condor)
    ares_endpoints = [
        ("/api/ares/status", "GET", 200),
        ("/api/ares/positions", "GET", 200),
        ("/api/ares/performance", "GET", 200),
        ("/api/ares/equity-curve", "GET", 200),
        ("/api/ares/equity-curve/intraday", "GET", 200),
        ("/api/ares/config", "GET", 200),
    ]

    # TITAN endpoints (SPX Aggressive IC)
    titan_endpoints = [
        ("/api/titan/status", "GET", 200),
        ("/api/titan/positions", "GET", 200),
        ("/api/titan/equity-curve", "GET", 200),
        ("/api/titan/equity-curve/intraday", "GET", 200),
    ]

    # PEGASUS endpoints (SPX Weekly IC)
    pegasus_endpoints = [
        ("/api/pegasus/status", "GET", 200),
        ("/api/pegasus/positions", "GET", 200),
        ("/api/pegasus/equity-curve", "GET", 200),
        ("/api/pegasus/equity-curve/intraday", "GET", 200),
    ]

    # ATHENA endpoints (Directional Spreads)
    athena_endpoints = [
        ("/api/athena/status", "GET", 200),
        ("/api/athena/positions", "GET", 200),
        ("/api/athena/equity-curve", "GET", 200),
        ("/api/athena/equity-curve/intraday", "GET", 200),
    ]

    # ICARUS endpoints (Aggressive Directional)
    icarus_endpoints = [
        ("/api/icarus/status", "GET", 200),
        ("/api/icarus/positions", "GET", 200),
        ("/api/icarus/equity-curve", "GET", 200),
        ("/api/icarus/equity-curve/intraday", "GET", 200),
    ]

    # Oracle & ML endpoints
    oracle_endpoints = [
        ("/api/zero-dte/oracle/status", "GET", 200),
        ("/api/ml/sage/status", "GET", 200),
        ("/api/ml/gex-models/status", "GET", 200),
    ]

    # Unified metrics endpoints
    metrics_endpoints = [
        ("/api/metrics/ARES/summary", "GET", 200),
        ("/api/metrics/ATHENA/summary", "GET", 200),
        ("/api/metrics/TITAN/summary", "GET", 200),
        ("/api/metrics/PEGASUS/summary", "GET", 200),
        ("/api/metrics/ICARUS/summary", "GET", 200),
        ("/api/metrics/HERACLES/summary", "GET", 200),
    ]

    all_endpoints = (
        core_endpoints + heracles_endpoints + prometheus_endpoints +
        ares_endpoints + titan_endpoints + pegasus_endpoints +
        athena_endpoints + icarus_endpoints + oracle_endpoints + metrics_endpoints
    )

    for endpoint, method, expected_status in all_endpoints:
        passed, resp = test_endpoint_exists(base_url, endpoint, method, expected_status)
        if passed:
            log_result(f"{method} {endpoint}", True)
        else:
            actual_status = resp.status_code if hasattr(resp, 'status_code') else str(resp)
            log_result(f"{method} {endpoint}", False,
                      f"Expected {expected_status}, got {actual_status}",
                      str(expected_status), str(actual_status))

def run_response_shape_tests(base_url: str):
    """Test that endpoints return expected response shapes."""
    print("\n=== RESPONSE SHAPE TESTS ===")

    # Define expected response fields for key endpoints
    shape_tests = [
        # HERACLES
        ("/api/heracles/status", ["status", "mode", "positions"]),
        ("/api/heracles/diagnostics", ["bot_name", "execution", "database", "market_data", "gex_data"]),
        ("/api/heracles/ml/status", ["model_trained"]),
        ("/api/heracles/ml/approval-status", ["ml_approved", "probability_source"]),
        ("/api/heracles/ab-test/status", ["ab_test_enabled"]),

        # PROMETHEUS
        ("/api/prometheus-box/status", ["status"]),
        ("/api/prometheus-box/combined/performance", ["available"]),

        # ARES
        ("/api/ares/status", ["status"]),

        # Oracle
        ("/api/zero-dte/oracle/status", ["status"]),

        # Metrics (unified)
        ("/api/metrics/HERACLES/summary", ["bot_name"]),
    ]

    for endpoint, required_fields in shape_tests:
        passed, resp = test_endpoint_exists(base_url, endpoint)
        if not passed:
            log_result(f"Shape: {endpoint}", False, "Endpoint not reachable")
            continue

        shape_ok, msg = test_response_shape(resp, required_fields)
        log_result(f"Shape: {endpoint} has {required_fields}", shape_ok, msg)

def run_error_handling_tests(base_url: str):
    """Test that endpoints handle errors gracefully."""
    print("\n=== ERROR HANDLING TESTS ===")

    # Test 404 for non-existent endpoints
    passed, resp = test_endpoint_exists(base_url, "/api/heracles/nonexistent", "GET", 404)
    if passed or (hasattr(resp, 'status_code') and resp.status_code in [404, 422]):
        log_result("404 for nonexistent endpoint", True)
    else:
        log_result("404 for nonexistent endpoint", False, "Should return 404")

    # Test invalid bot name in metrics
    passed, resp = test_endpoint_exists(base_url, "/api/metrics/INVALID_BOT/summary", "GET", 400)
    if passed or (hasattr(resp, 'status_code') and resp.status_code in [400, 422, 404]):
        log_result("400/404 for invalid bot name", True)
    else:
        actual = resp.status_code if hasattr(resp, 'status_code') else str(resp)
        log_result("400/404 for invalid bot name", False, f"Got {actual}")

def run_cross_bot_consistency_tests(base_url: str):
    """Test that all bots have consistent endpoint patterns."""
    print("\n=== CROSS-BOT CONSISTENCY TESTS ===")

    bots = ["ares", "athena", "titan", "pegasus", "icarus"]

    # All bots should have /status
    for bot in bots:
        passed, resp = test_endpoint_exists(base_url, f"/api/{bot}/status")
        log_result(f"{bot.upper()} has /status endpoint", passed)

    # All bots should have /positions
    for bot in bots:
        passed, resp = test_endpoint_exists(base_url, f"/api/{bot}/positions")
        log_result(f"{bot.upper()} has /positions endpoint", passed)

    # All bots should have /equity-curve
    for bot in bots:
        passed, resp = test_endpoint_exists(base_url, f"/api/{bot}/equity-curve")
        log_result(f"{bot.upper()} has /equity-curve endpoint", passed)

def run_data_integrity_tests(base_url: str):
    """Test that endpoints return valid data structures."""
    print("\n=== DATA INTEGRITY TESTS ===")

    # Test equity curve returns array structure
    for endpoint in ["/api/heracles/paper-equity-curve", "/api/ares/equity-curve"]:
        passed, resp = test_endpoint_exists(base_url, endpoint)
        if passed:
            try:
                data = resp.json()
                has_curve = "equity_curve" in data or "data" in data
                log_result(f"{endpoint} returns equity_curve data", has_curve)
            except:
                log_result(f"{endpoint} returns equity_curve data", False, "Invalid JSON")
        else:
            log_result(f"{endpoint} returns equity_curve data", False, "Not reachable")

    # Test HERACLES scan activity has outcome field for ML training
    passed, resp = test_endpoint_exists(base_url, "/api/heracles/scan-activity")
    if passed:
        try:
            data = resp.json()
            has_scans = "scans" in data
            log_result("HERACLES scan-activity returns scans array", has_scans)
        except:
            log_result("HERACLES scan-activity returns scans array", False, "Invalid JSON")

def print_summary():
    """Print test summary."""
    print("\n" + "=" * 60)
    print("ALPHAGEX PRODUCTION API TEST RESULTS")
    print("=" * 60)
    print(f"PASSED: {RESULTS['passed']}")
    print(f"FAILED: {RESULTS['failed']}")
    print(f"SKIPPED: {RESULTS['skipped']}")
    print("=" * 60)

    if RESULTS["failures"]:
        print("\nFAILED TESTS:")
        for f in RESULTS["failures"]:
            print(f"  - {f['test']}: {f['message']}")
            if f.get("expected"):
                print(f"    Expected: {f['expected']}, Actual: {f['actual']}")

    total = RESULTS["passed"] + RESULTS["failed"]
    if RESULTS["failed"] == 0:
        print("\n[OK] All tests passed!")
        return 0
    else:
        print(f"\n[FAIL] {RESULTS['failed']}/{total} tests failed")
        return 1

def main():
    parser = argparse.ArgumentParser(description="AlphaGEX Production API Tests")
    parser.add_argument("--api-url", default=os.environ.get("API_URL", "http://localhost:8000"),
                        help="Base API URL (default: http://localhost:8000)")
    args = parser.parse_args()

    base_url = args.api_url.rstrip("/")
    print(f"Testing API at: {base_url}")
    print(f"Timestamp: {datetime.now().isoformat()}")

    # Run all test suites
    run_endpoint_existence_tests(base_url)
    run_response_shape_tests(base_url)
    run_error_handling_tests(base_url)
    run_cross_bot_consistency_tests(base_url)
    run_data_integrity_tests(base_url)

    return print_summary()

if __name__ == "__main__":
    sys.exit(main())
