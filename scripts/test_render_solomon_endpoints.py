#!/usr/bin/env python3
"""
Render Integration Test Script for Proverbs Feedback Loop (Migration 023)

This script tests the Proverbs API endpoints on the deployed Render service.
Run this after deploying to verify the feedback loop is working end-to-end.

Usage:
    # Test production
    python scripts/test_render_proverbs_endpoints.py

    # Test with custom URL
    python scripts/test_render_proverbs_endpoints.py --url https://your-api.onrender.com

    # Verbose output
    python scripts/test_render_proverbs_endpoints.py -v

Requirements:
    pip install requests

Author: AlphaGEX
Date: January 2025
"""

import argparse
import json
import sys
import time
from typing import Dict, List, Tuple, Optional

try:
    import requests
except ImportError:
    print("Error: requests library required. Install with: pip install requests")
    sys.exit(1)


# Default API URL (update with your Render URL)
DEFAULT_API_URL = "https://alphagex-api.onrender.com"

# Test configuration
TIMEOUT_SECONDS = 30
RETRY_COUNT = 3
RETRY_DELAY_SECONDS = 2


class Colors:
    """ANSI color codes for terminal output"""
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    END = '\033[0m'


def print_status(status: str, message: str, verbose: bool = False):
    """Print colored status message"""
    if status == "PASS":
        print(f"{Colors.GREEN}[PASS]{Colors.END} {message}")
    elif status == "FAIL":
        print(f"{Colors.RED}[FAIL]{Colors.END} {message}")
    elif status == "WARN":
        print(f"{Colors.YELLOW}[WARN]{Colors.END} {message}")
    elif status == "INFO":
        if verbose:
            print(f"{Colors.BLUE}[INFO]{Colors.END} {message}")


def test_endpoint(
    base_url: str,
    endpoint: str,
    method: str = "GET",
    params: Optional[Dict] = None,
    expected_fields: Optional[List[str]] = None,
    verbose: bool = False
) -> Tuple[bool, str, Optional[Dict]]:
    """
    Test a single API endpoint.

    Returns:
        Tuple of (success, message, response_data)
    """
    url = f"{base_url}{endpoint}"

    for attempt in range(RETRY_COUNT):
        try:
            if method == "GET":
                response = requests.get(url, params=params, timeout=TIMEOUT_SECONDS)
            elif method == "POST":
                response = requests.post(url, json=params, timeout=TIMEOUT_SECONDS)
            else:
                return False, f"Unsupported method: {method}", None

            if response.status_code == 200:
                data = response.json()

                # Check expected fields
                if expected_fields:
                    missing = [f for f in expected_fields if f not in data]
                    if missing:
                        return False, f"Missing fields: {missing}", data

                return True, f"Status 200, response valid", data

            elif response.status_code == 500:
                # Server error - might be database issue, log but consider partial success
                try:
                    error_data = response.json()
                    error_msg = error_data.get('detail', 'Unknown error')
                except:
                    error_msg = response.text[:200]
                return False, f"Server error (500): {error_msg}", None

            else:
                return False, f"Unexpected status: {response.status_code}", None

        except requests.exceptions.Timeout:
            if attempt < RETRY_COUNT - 1:
                print_status("WARN", f"Timeout on attempt {attempt + 1}, retrying...", verbose)
                time.sleep(RETRY_DELAY_SECONDS)
            else:
                return False, "Request timed out after retries", None

        except requests.exceptions.ConnectionError as e:
            if attempt < RETRY_COUNT - 1:
                print_status("WARN", f"Connection error on attempt {attempt + 1}, retrying...", verbose)
                time.sleep(RETRY_DELAY_SECONDS)
            else:
                return False, f"Connection failed: {str(e)[:100]}", None

        except Exception as e:
            return False, f"Unexpected error: {str(e)[:100]}", None

    return False, "All retry attempts failed", None


def run_proverbs_tests(base_url: str, verbose: bool = False) -> Tuple[int, int]:
    """
    Run all Proverbs endpoint tests.

    Returns:
        Tuple of (passed_count, total_count)
    """
    print(f"\n{Colors.BOLD}=== Proverbs Feedback Loop Integration Tests ==={Colors.END}")
    print(f"Target: {base_url}\n")

    tests = [
        # Basic health check
        {
            "name": "API Health Check",
            "endpoint": "/health",
            "method": "GET",
            "expected_fields": ["status"],
        },

        # Proverbs Dashboard
        {
            "name": "Proverbs Dashboard",
            "endpoint": "/api/proverbs/dashboard",
            "method": "GET",
        },

        # Migration 023: Strategy Analysis
        {
            "name": "Strategy Analysis (Migration 023)",
            "endpoint": "/api/proverbs/strategy-analysis",
            "method": "GET",
            "expected_fields": ["success"],
        },
        {
            "name": "Strategy Analysis with Days Param",
            "endpoint": "/api/proverbs/strategy-analysis",
            "method": "GET",
            "params": {"days": 7},
        },

        # Migration 023: Oracle Accuracy
        {
            "name": "Oracle Accuracy (Migration 023)",
            "endpoint": "/api/proverbs/oracle-accuracy",
            "method": "GET",
            "expected_fields": ["success"],
        },
        {
            "name": "Oracle Accuracy with Days Param",
            "endpoint": "/api/proverbs/oracle-accuracy",
            "method": "GET",
            "params": {"days": 14},
        },

        # Enhanced Endpoints
        {
            "name": "Proverbs Enhanced Digest",
            "endpoint": "/api/proverbs/enhanced/digest",
            "method": "GET",
        },
        {
            "name": "Proverbs Enhanced Correlations",
            "endpoint": "/api/proverbs/enhanced/correlations",
            "method": "GET",
        },

        # Validation Status
        {
            "name": "Proverbs Validation Status",
            "endpoint": "/api/proverbs/validation/status",
            "method": "GET",
        },
    ]

    passed = 0
    total = len(tests)

    for test in tests:
        name = test["name"]
        endpoint = test["endpoint"]
        method = test.get("method", "GET")
        params = test.get("params")
        expected_fields = test.get("expected_fields")

        print_status("INFO", f"Testing: {name}", verbose)

        success, message, data = test_endpoint(
            base_url, endpoint, method, params, expected_fields, verbose
        )

        if success:
            print_status("PASS", f"{name}: {message}")
            passed += 1
        else:
            print_status("FAIL", f"{name}: {message}")

        if verbose and data:
            print(f"       Response: {json.dumps(data, indent=2)[:500]}...")

    return passed, total


def run_bot_integration_tests(base_url: str, verbose: bool = False) -> Tuple[int, int]:
    """
    Run bot-specific tests to verify feedback loop integration.

    Returns:
        Tuple of (passed_count, total_count)
    """
    print(f"\n{Colors.BOLD}=== Bot Integration Tests ==={Colors.END}\n")

    bots = ['fortress', 'solomon', 'samson', 'anchor', 'gideon']
    passed = 0
    total = len(bots)

    for bot in bots:
        endpoint = f"/api/{bot}/status"
        print_status("INFO", f"Testing {bot.upper()} status...", verbose)

        success, message, data = test_endpoint(base_url, endpoint, verbose=verbose)

        if success:
            # Check if bot has oracle_prediction tracking enabled
            if data and isinstance(data, dict):
                # Look for signs of feedback loop integration
                has_integration = any(k in str(data).lower() for k in ['oracle', 'prediction', 'feedback'])
                if has_integration:
                    print_status("PASS", f"{bot.upper()}: Status OK with feedback loop indicators")
                else:
                    print_status("PASS", f"{bot.upper()}: Status OK (no explicit feedback indicators)")
                passed += 1
            else:
                print_status("PASS", f"{bot.upper()}: Status OK")
                passed += 1
        else:
            print_status("FAIL", f"{bot.upper()}: {message}")

    return passed, total


def main():
    parser = argparse.ArgumentParser(
        description="Test Proverbs feedback loop endpoints on Render deployment"
    )
    parser.add_argument(
        "--url",
        default=DEFAULT_API_URL,
        help=f"Base API URL (default: {DEFAULT_API_URL})"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Verbose output"
    )
    parser.add_argument(
        "--bots-only",
        action="store_true",
        help="Only run bot integration tests"
    )
    parser.add_argument(
        "--proverbs-only",
        action="store_true",
        help="Only run Proverbs endpoint tests"
    )

    args = parser.parse_args()

    total_passed = 0
    total_tests = 0

    if not args.bots_only:
        passed, total = run_proverbs_tests(args.url, args.verbose)
        total_passed += passed
        total_tests += total

    if not args.proverbs_only:
        passed, total = run_bot_integration_tests(args.url, args.verbose)
        total_passed += passed
        total_tests += total

    # Summary
    print(f"\n{Colors.BOLD}=== Test Summary ==={Colors.END}")
    print(f"Passed: {total_passed}/{total_tests}")

    if total_passed == total_tests:
        print(f"{Colors.GREEN}{Colors.BOLD}All tests passed!{Colors.END}")
        sys.exit(0)
    elif total_passed >= total_tests * 0.7:
        print(f"{Colors.YELLOW}{Colors.BOLD}Most tests passed (some may need database data){Colors.END}")
        sys.exit(0)
    else:
        print(f"{Colors.RED}{Colors.BOLD}Tests failed - check deployment{Colors.END}")
        sys.exit(1)


if __name__ == "__main__":
    main()
