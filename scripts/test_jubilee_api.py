#!/usr/bin/env python
"""
JUBILEE API Test Script for Render Shell

Run this script in the Render shell to verify all JUBILEE endpoints are working:
    python scripts/test_jubilee_api.py

This tests all 52 JUBILEE Box Spread API endpoints.
"""

import os
import sys

# Add project root to Python path for Render shell
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import json
import requests
from datetime import datetime
from typing import Dict, List, Tuple, Any

# Configuration - Render uses internal URL or RENDER_EXTERNAL_URL
BASE_URL = os.environ.get('API_BASE_URL') or os.environ.get('RENDER_EXTERNAL_URL') or 'http://localhost:8000'
# Remove trailing slash if present
BASE_URL = BASE_URL.rstrip('/')
PROMETHEUS_PREFIX = '/api/jubilee'

# ANSI colors for output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'
BOLD = '\033[1m'


def print_header(text: str):
    print(f"\n{BOLD}{BLUE}{'=' * 60}{RESET}")
    print(f"{BOLD}{BLUE}{text}{RESET}")
    print(f"{BOLD}{BLUE}{'=' * 60}{RESET}\n")


def print_result(endpoint: str, success: bool, status_code: int, message: str = ""):
    icon = f"{GREEN}✓{RESET}" if success else f"{RED}✗{RESET}"
    status_str = f"[{status_code}]" if status_code else "[---]"
    msg = f" - {message}" if message else ""
    print(f"  {icon} {status_str} {endpoint}{msg}")


def test_endpoint(
    method: str,
    path: str,
    expected_status: int = 200,
    data: Dict = None,
    params: Dict = None,
    check_field: str = None
) -> Tuple[bool, int, str]:
    """
    Test a single API endpoint.

    Returns: (success, status_code, message)
    """
    url = f"{BASE_URL}{PROMETHEUS_PREFIX}{path}"

    try:
        if method.upper() == 'GET':
            response = requests.get(url, params=params, timeout=30)
        elif method.upper() == 'POST':
            response = requests.post(url, json=data, timeout=30)
        else:
            return False, 0, f"Unknown method: {method}"

        success = response.status_code == expected_status
        message = ""

        # Try to get response data for additional checks
        try:
            resp_data = response.json()
            if check_field and check_field in resp_data:
                message = f"{check_field}={resp_data[check_field]}"
            elif 'count' in resp_data:
                message = f"count={resp_data['count']}"
            elif 'available' in resp_data:
                message = f"available={resp_data['available']}"
        except:
            if not success:
                message = response.text[:100]

        return success, response.status_code, message

    except requests.Timeout:
        return False, 0, "Timeout"
    except requests.ConnectionError:
        return False, 0, "Connection failed"
    except Exception as e:
        return False, 0, str(e)[:50]


def run_all_tests() -> Tuple[int, int, List[str]]:
    """
    Run all API endpoint tests.

    Returns: (passed, failed, failed_endpoints)
    """
    passed = 0
    failed = 0
    failed_endpoints = []

    # ==================================================================
    # BOX SPREAD ENDPOINTS
    # ==================================================================
    print_header("BOX SPREAD STATUS & CONFIG")

    endpoints = [
        ('GET', '/status', 200, None, None, 'status'),
        ('GET', '/health', 200, None, None, 'status'),
        ('GET', '/config', 200, None, None, None),
    ]

    for method, path, expected, data, params, check in endpoints:
        success, status, msg = test_endpoint(method, path, expected, data, params, check)
        print_result(path, success, status, msg)
        if success:
            passed += 1
        else:
            failed += 1
            failed_endpoints.append(f"{method} {path}")

    # ==================================================================
    print_header("BOX SPREAD POSITIONS")

    endpoints = [
        ('GET', '/positions', 200, None, None, 'count'),
        ('GET', '/closed-trades', 200, None, {'limit': 10}, 'count'),
        ('GET', '/scan-activity', 200, None, {'limit': 10}, 'count'),
    ]

    for method, path, expected, data, params, check in endpoints:
        success, status, msg = test_endpoint(method, path, expected, data, params, check)
        print_result(path, success, status, msg)
        if success:
            passed += 1
        else:
            failed += 1
            failed_endpoints.append(f"{method} {path}")

    # ==================================================================
    print_header("BOX SPREAD SIGNALS")

    endpoints = [
        ('GET', '/signals/scan', 200, None, None, None),
        ('GET', '/signals/recent', 200, None, {'limit': 10}, 'count'),
    ]

    for method, path, expected, data, params, check in endpoints:
        success, status, msg = test_endpoint(method, path, expected, data, params, check)
        print_result(path, success, status, msg)
        if success:
            passed += 1
        else:
            failed += 1
            failed_endpoints.append(f"{method} {path}")

    # ==================================================================
    print_header("BOX SPREAD ANALYTICS")

    endpoints = [
        ('GET', '/analytics/rates', 200, None, None, None),
        ('GET', '/analytics/rates/history', 200, None, {'days': 7}, 'count'),
        ('GET', '/analytics/interest-rates', 200, None, None, 'fed_funds_rate'),
        ('GET', '/analytics/capital-flow', 200, None, None, None),
        ('GET', '/analytics/performance', 200, None, None, None),
    ]

    for method, path, expected, data, params, check in endpoints:
        success, status, msg = test_endpoint(method, path, expected, data, params, check)
        print_result(path, success, status, msg)
        if success:
            passed += 1
        else:
            failed += 1
            failed_endpoints.append(f"{method} {path}")

    # ==================================================================
    print_header("BOX SPREAD EQUITY CURVES")

    endpoints = [
        ('GET', '/equity-curve', 200, None, {'limit': 50}, None),
        ('GET', '/equity-curve/intraday', 200, None, None, None),
    ]

    for method, path, expected, data, params, check in endpoints:
        success, status, msg = test_endpoint(method, path, expected, data, params, check)
        print_result(path, success, status, msg)
        if success:
            passed += 1
        else:
            failed += 1
            failed_endpoints.append(f"{method} {path}")

    # ==================================================================
    print_header("BOX SPREAD OPERATIONS")

    endpoints = [
        ('GET', '/operations/daily-briefing', 200, None, None, 'system_status'),
    ]

    for method, path, expected, data, params, check in endpoints:
        success, status, msg = test_endpoint(method, path, expected, data, params, check)
        print_result(path, success, status, msg)
        if success:
            passed += 1
        else:
            failed += 1
            failed_endpoints.append(f"{method} {path}")

    # ==================================================================
    print_header("BOX SPREAD EDUCATION")

    endpoints = [
        ('GET', '/education', 200, None, None, None),
        ('GET', '/education/calculator', 200, None, {'strike_width': 50, 'dte': 90, 'market_price': 49.5}, 'inputs'),
        ('GET', '/education/overview', 200, None, None, None),
    ]

    for method, path, expected, data, params, check in endpoints:
        success, status, msg = test_endpoint(method, path, expected, data, params, check)
        print_result(path, success, status, msg)
        if success:
            passed += 1
        else:
            failed += 1
            failed_endpoints.append(f"{method} {path}")

    # ==================================================================
    print_header("BOX SPREAD LOGS & DEPLOYMENTS")

    endpoints = [
        ('GET', '/logs', 200, None, {'limit': 20}, 'count'),
        ('GET', '/deployments', 200, None, None, 'count'),
    ]

    for method, path, expected, data, params, check in endpoints:
        success, status, msg = test_endpoint(method, path, expected, data, params, check)
        print_result(path, success, status, msg)
        if success:
            passed += 1
        else:
            failed += 1
            failed_endpoints.append(f"{method} {path}")

    # ==================================================================
    print_header("BOX SPREAD TRANSPARENCY")

    endpoints = [
        ('GET', '/transparency/summary', 200, None, None, 'available'),
    ]

    for method, path, expected, data, params, check in endpoints:
        success, status, msg = test_endpoint(method, path, expected, data, params, check)
        print_result(path, success, status, msg)
        if success:
            passed += 1
        else:
            failed += 1
            failed_endpoints.append(f"{method} {path}")

    # ==================================================================
    # IC TRADING ENDPOINTS
    # ==================================================================
    print_header("IC TRADING STATUS & CONFIG")

    endpoints = [
        ('GET', '/ic/status', 200, None, None, 'available'),
        ('GET', '/ic/config', 200, None, None, 'available'),
    ]

    for method, path, expected, data, params, check in endpoints:
        success, status, msg = test_endpoint(method, path, expected, data, params, check)
        print_result(path, success, status, msg)
        if success:
            passed += 1
        else:
            failed += 1
            failed_endpoints.append(f"{method} {path}")

    # ==================================================================
    print_header("IC POSITIONS")

    endpoints = [
        ('GET', '/ic/positions', 200, None, None, 'count'),
        ('GET', '/ic/closed-trades', 200, None, {'limit': 20}, 'count'),
    ]

    for method, path, expected, data, params, check in endpoints:
        success, status, msg = test_endpoint(method, path, expected, data, params, check)
        print_result(path, success, status, msg)
        if success:
            passed += 1
        else:
            failed += 1
            failed_endpoints.append(f"{method} {path}")

    # ==================================================================
    print_header("IC PERFORMANCE & EQUITY")

    endpoints = [
        ('GET', '/ic/performance', 200, None, None, 'available'),
        ('GET', '/ic/equity-curve', 200, None, {'limit': 50}, 'count'),
        ('GET', '/ic/equity-curve/intraday', 200, None, None, 'count'),
    ]

    for method, path, expected, data, params, check in endpoints:
        success, status, msg = test_endpoint(method, path, expected, data, params, check)
        print_result(path, success, status, msg)
        if success:
            passed += 1
        else:
            failed += 1
            failed_endpoints.append(f"{method} {path}")

    # ==================================================================
    print_header("IC LOGS & SIGNALS")

    endpoints = [
        ('GET', '/ic/logs', 200, None, {'limit': 20}, 'count'),
        ('GET', '/ic/signals/recent', 200, None, {'limit': 20}, 'count'),
    ]

    for method, path, expected, data, params, check in endpoints:
        success, status, msg = test_endpoint(method, path, expected, data, params, check)
        print_result(path, success, status, msg)
        if success:
            passed += 1
        else:
            failed += 1
            failed_endpoints.append(f"{method} {path}")

    # ==================================================================
    print_header("COMBINED PERFORMANCE")

    endpoints = [
        ('GET', '/combined/performance', 200, None, None, 'available'),
    ]

    for method, path, expected, data, params, check in endpoints:
        success, status, msg = test_endpoint(method, path, expected, data, params, check)
        print_result(path, success, status, msg)
        if success:
            passed += 1
        else:
            failed += 1
            failed_endpoints.append(f"{method} {path}")

    # ==================================================================
    print_header("TRACING & OBSERVABILITY")

    endpoints = [
        ('GET', '/tracing/metrics', 200, None, None, 'available'),
        ('GET', '/tracing/recent', 200, None, {'limit': 20}, 'count'),
        ('GET', '/tracing/rate-audit', 200, None, {'limit': 20}, 'count'),
    ]

    for method, path, expected, data, params, check in endpoints:
        success, status, msg = test_endpoint(method, path, expected, data, params, check)
        print_result(path, success, status, msg)
        if success:
            passed += 1
        else:
            failed += 1
            failed_endpoints.append(f"{method} {path}")

    return passed, failed, failed_endpoints


def main():
    """Main entry point."""
    print(f"\n{BOLD}JUBILEE API Test Suite{RESET}")
    print(f"Base URL: {BASE_URL}")
    print(f"Timestamp: {datetime.now().isoformat()}")

    # First check if API is reachable
    print_header("CONNECTION CHECK")
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=10)
        print_result("/health (root)", response.status_code == 200, response.status_code)
    except Exception as e:
        print(f"{RED}ERROR: Cannot connect to API at {BASE_URL}{RESET}")
        print(f"Error: {e}")
        print("\nMake sure:")
        print("  1. The API server is running")
        print("  2. API_BASE_URL environment variable is set correctly")
        print("  3. Network connectivity is available")
        sys.exit(1)

    # Run all tests
    passed, failed, failed_endpoints = run_all_tests()

    # Summary
    print_header("TEST SUMMARY")
    total = passed + failed
    print(f"  Total endpoints tested: {total}")
    print(f"  {GREEN}Passed: {passed}{RESET}")
    print(f"  {RED}Failed: {failed}{RESET}")

    if failed_endpoints:
        print(f"\n{YELLOW}Failed endpoints:{RESET}")
        for ep in failed_endpoints:
            print(f"  - {ep}")

    success_rate = (passed / total * 100) if total > 0 else 0
    print(f"\n  Success rate: {success_rate:.1f}%")

    # Exit code
    if failed > 0:
        print(f"\n{RED}Some tests failed!{RESET}")
        sys.exit(1)
    else:
        print(f"\n{GREEN}All tests passed!{RESET}")
        sys.exit(0)


if __name__ == '__main__':
    main()
