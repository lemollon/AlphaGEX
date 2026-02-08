#!/usr/bin/env python3
"""
WATCHTOWER End-to-End Test Script
============================

Comprehensive testing for WATCHTOWER live data feed, caching, and timezone handling.

Usage:
    python scripts/test_argus_e2e.py [--url BASE_URL]

Example:
    python scripts/test_argus_e2e.py --url https://alphagex-api.onrender.com
"""

import sys
import json
import time
import argparse
from datetime import datetime
from zoneinfo import ZoneInfo

# Color codes for terminal output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'
BOLD = '\033[1m'

CENTRAL_TZ = ZoneInfo("America/Chicago")

# Test results tracking
results = {
    'passed': 0,
    'failed': 0,
    'warnings': 0,
    'tests': []
}


def log_pass(name, detail=""):
    results['passed'] += 1
    results['tests'].append({'name': name, 'status': 'pass', 'detail': detail})
    print(f"  {GREEN}✓{RESET} {name}" + (f" ({detail})" if detail else ""))


def log_fail(name, detail=""):
    results['failed'] += 1
    results['tests'].append({'name': name, 'status': 'fail', 'detail': detail})
    print(f"  {RED}✗{RESET} {name}" + (f" ({detail})" if detail else ""))


def log_warn(name, detail=""):
    results['warnings'] += 1
    results['tests'].append({'name': name, 'status': 'warn', 'detail': detail})
    print(f"  {YELLOW}⚠{RESET} {name}" + (f" ({detail})" if detail else ""))


def log_info(msg):
    print(f"  {BLUE}ℹ{RESET} {msg}")


def is_market_hours():
    """Check if currently within market hours (9:30 AM - 4:00 PM CT, Mon-Fri)"""
    now = datetime.now(CENTRAL_TZ)
    if now.weekday() >= 5:  # Weekend
        return False
    time_minutes = now.hour * 60 + now.minute
    return 570 <= time_minutes <= 960  # 9:30 AM to 4:00 PM


def test_tradier_connectivity():
    """Test 1: Verify Tradier API connectivity"""
    print(f"\n{BOLD}TEST 1: Tradier API Connectivity{RESET}")
    print("=" * 50)

    try:
        from data.tradier_data_fetcher import TradierDataFetcher

        tradier = TradierDataFetcher()
        log_pass("Tradier client initialized", f"Mode: {'SANDBOX' if tradier.sandbox else 'PRODUCTION'}")

        # Test quote
        quote = tradier.get_quote('SPY')
        price = quote.get('last') or quote.get('close')
        if price and price > 0:
            log_pass("SPY quote retrieved", f"${price:.2f}")
        else:
            log_fail("SPY quote retrieved", "No price returned")
            return False

        # Test expirations
        expirations = tradier.get_option_expirations('SPY')
        if expirations and len(expirations) > 0:
            log_pass("Option expirations retrieved", f"{len(expirations)} expirations")
        else:
            log_fail("Option expirations retrieved", "No expirations")
            return False

        # Test option chain
        exp = expirations[0]
        chain = tradier.get_option_chain('SPY', exp)
        contracts = chain.chains.get(exp, [])
        if contracts and len(contracts) > 0:
            log_pass("Option chain retrieved", f"{len(contracts)} contracts for {exp}")

            # Check for gamma data
            with_gamma = [c for c in contracts if c.gamma and c.gamma != 0]
            if with_gamma:
                log_pass("Greeks available", f"{len(with_gamma)} contracts with gamma")
            else:
                log_warn("Greeks available", "No gamma data - market may be closed")
        else:
            log_fail("Option chain retrieved", "No contracts")
            return False

        return True

    except Exception as e:
        log_fail("Tradier connectivity", str(e))
        return False


def test_argus_api(base_url):
    """Test 2: Verify WATCHTOWER API endpoints"""
    print(f"\n{BOLD}TEST 2: WATCHTOWER API Endpoints{RESET}")
    print("=" * 50)

    try:
        import requests

        # Test gamma endpoint
        response = requests.get(f"{base_url}/api/watchtower/gamma", timeout=30)
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                gamma_data = data.get('data', {})
                log_pass("Gamma endpoint", f"Status 200")

                # Check is_mock
                is_mock = gamma_data.get('is_mock', True)
                if is_mock:
                    if is_market_hours():
                        log_warn("Live data status", "Mock data during market hours!")
                    else:
                        log_pass("Live data status", "Mock data (market closed)")
                else:
                    log_pass("Live data status", "LIVE data from Tradier")

                # Check fetched_at
                fetched_at = gamma_data.get('fetched_at')
                if fetched_at:
                    log_pass("Timestamp present", f"{fetched_at}")
                    # Check if timestamp is in Central timezone
                    if '-05:00' in fetched_at or '-06:00' in fetched_at:
                        log_pass("Central timezone", "Timestamp includes CT offset")
                    else:
                        log_warn("Central timezone", "Timezone offset not visible in ISO format")
                else:
                    log_fail("Timestamp present", "No fetched_at in response")

                # Check strikes
                strikes = gamma_data.get('strikes', [])
                if strikes and len(strikes) > 0:
                    log_pass("Strike data", f"{len(strikes)} strikes returned")
                else:
                    log_warn("Strike data", "No strikes in response")

                return True
            else:
                log_fail("Gamma endpoint", "success: false")
        else:
            log_fail("Gamma endpoint", f"Status {response.status_code}")

        return False

    except requests.exceptions.Timeout:
        log_fail("Gamma endpoint", "Request timeout (>30s)")
        return False
    except Exception as e:
        log_fail("WATCHTOWER API", str(e))
        return False


def test_cache_behavior(base_url):
    """Test 3: Verify cache doesn't persist mock data"""
    print(f"\n{BOLD}TEST 3: Cache Behavior{RESET}")
    print("=" * 50)

    try:
        import requests

        # Make two requests
        log_info("Making first request...")
        r1 = requests.get(f"{base_url}/api/watchtower/gamma", timeout=30)
        d1 = r1.json().get('data', {}) if r1.status_code == 200 else {}
        is_mock_1 = d1.get('is_mock', True)
        fetched_1 = d1.get('fetched_at', '')

        log_info(f"First: is_mock={is_mock_1}, fetched_at={fetched_1[:19] if fetched_1 else 'N/A'}")

        # Wait and make second request
        log_info("Waiting 5 seconds...")
        time.sleep(5)

        log_info("Making second request...")
        r2 = requests.get(f"{base_url}/api/watchtower/gamma", timeout=30)
        d2 = r2.json().get('data', {}) if r2.status_code == 200 else {}
        is_mock_2 = d2.get('is_mock', True)
        fetched_2 = d2.get('fetched_at', '')

        log_info(f"Second: is_mock={is_mock_2}, fetched_at={fetched_2[:19] if fetched_2 else 'N/A'}")

        # Check cache behavior
        if not is_mock_1 and not is_mock_2:
            log_pass("Live data consistency", "Both requests returned live data")
        elif is_mock_1 and is_mock_2:
            if is_market_hours():
                log_warn("Mock data persistence", "Mock data persisting during market hours")
            else:
                log_pass("Mock data (market closed)", "Expected behavior outside market hours")
        else:
            log_warn("Data consistency", f"First: mock={is_mock_1}, Second: mock={is_mock_2}")

        # Check if timestamps are from cache (same) or fresh
        if fetched_1 == fetched_2:
            log_info("Timestamps identical - data served from cache (expected within TTL)")
        else:
            log_info("Timestamps differ - fresh fetch occurred")

        return True

    except Exception as e:
        log_fail("Cache test", str(e))
        return False


def test_data_freshness(base_url):
    """Test 4: Verify data freshness during market hours"""
    print(f"\n{BOLD}TEST 4: Data Freshness{RESET}")
    print("=" * 50)

    if not is_market_hours():
        log_info("Skipping freshness test - market is closed")
        log_info(f"Current CT time: {datetime.now(CENTRAL_TZ).strftime('%I:%M %p')}")
        return True

    try:
        import requests

        response = requests.get(f"{base_url}/api/watchtower/gamma", timeout=30)
        if response.status_code != 200:
            log_fail("Data freshness", f"API returned {response.status_code}")
            return False

        data = response.json().get('data', {})
        fetched_at_str = data.get('fetched_at', '')

        if not fetched_at_str:
            log_fail("Data freshness", "No fetched_at timestamp")
            return False

        # Parse timestamp
        try:
            fetched_at = datetime.fromisoformat(fetched_at_str.replace('Z', '+00:00'))
            now = datetime.now(CENTRAL_TZ)

            # Make fetched_at timezone-aware if it isn't
            if fetched_at.tzinfo is None:
                fetched_at = fetched_at.replace(tzinfo=CENTRAL_TZ)

            age_seconds = (now - fetched_at).total_seconds()

            if age_seconds < 0:
                log_warn("Data freshness", f"Timestamp in future by {-age_seconds:.0f}s (clock skew?)")
            elif age_seconds <= 60:
                log_pass("Data freshness", f"Data is {age_seconds:.0f}s old (within 60s TTL)")
            elif age_seconds <= 300:
                log_warn("Data freshness", f"Data is {age_seconds:.0f}s old (>60s)")
            else:
                log_fail("Data freshness", f"Data is {age_seconds:.0f}s old (very stale)")

        except Exception as e:
            log_warn("Timestamp parsing", f"Could not parse: {fetched_at_str} ({e})")

        return True

    except Exception as e:
        log_fail("Data freshness", str(e))
        return False


def test_expected_range(base_url):
    """Test 5: Verify expected range calculation"""
    print(f"\n{BOLD}TEST 5: Expected Range Calculation{RESET}")
    print("=" * 50)

    try:
        import requests

        response = requests.get(f"{base_url}/api/gamma/SPY/expiration-intel", timeout=30)
        if response.status_code != 200:
            log_warn("Expected range", f"API returned {response.status_code}")
            return True  # Non-critical

        data = response.json().get('data', {})
        prediction = data.get('directional_prediction', {})

        expected_range = prediction.get('expected_range', '')
        range_width_pct = prediction.get('range_width_pct', '')
        spot = data.get('spot_price', 0)

        log_info(f"Spot price: ${spot:.2f}")
        log_info(f"Expected range: {expected_range}")
        log_info(f"Range width: {range_width_pct}")

        # Check that range isn't collapsed (e.g., "$680.00 - $680.00")
        if expected_range:
            parts = expected_range.replace('$', '').split(' - ')
            if len(parts) == 2:
                try:
                    lower, upper = float(parts[0]), float(parts[1])
                    if lower == upper:
                        log_fail("Expected range", "Range is collapsed (lower == upper)")
                    elif upper - lower < 1:
                        log_warn("Expected range", f"Range very narrow: ${upper - lower:.2f}")
                    else:
                        log_pass("Expected range", f"Range width: ${upper - lower:.2f}")
                except:
                    log_warn("Expected range parsing", f"Could not parse: {expected_range}")
            else:
                log_warn("Expected range format", f"Unexpected format: {expected_range}")
        else:
            log_warn("Expected range", "Not present in response")

        return True

    except Exception as e:
        log_warn("Expected range test", str(e))
        return True  # Non-critical


def print_summary():
    """Print test summary"""
    print(f"\n{'=' * 60}")
    print(f"{BOLD}TEST SUMMARY{RESET}")
    print(f"{'=' * 60}")

    total = results['passed'] + results['failed'] + results['warnings']

    print(f"\n  {GREEN}Passed:   {results['passed']}/{total}{RESET}")
    print(f"  {RED}Failed:   {results['failed']}/{total}{RESET}")
    print(f"  {YELLOW}Warnings: {results['warnings']}/{total}{RESET}")

    # Current status
    print(f"\n{BOLD}CURRENT STATUS:{RESET}")
    now_ct = datetime.now(CENTRAL_TZ)
    print(f"  Time (CT): {now_ct.strftime('%I:%M:%S %p')}")
    print(f"  Day: {now_ct.strftime('%A')}")
    print(f"  Market: {'OPEN' if is_market_hours() else 'CLOSED'}")

    if results['failed'] > 0:
        print(f"\n{RED}⚠ {results['failed']} test(s) failed - review above{RESET}")
        return 1
    elif results['warnings'] > 0:
        print(f"\n{YELLOW}⚠ {results['warnings']} warning(s) - review above{RESET}")
        return 0
    else:
        print(f"\n{GREEN}✓ All tests passed!{RESET}")
        return 0


def main():
    parser = argparse.ArgumentParser(description='WATCHTOWER End-to-End Tests')
    parser.add_argument('--url', default='https://alphagex-api.onrender.com',
                        help='Base URL for API (default: https://alphagex-api.onrender.com)')
    parser.add_argument('--skip-tradier', action='store_true',
                        help='Skip Tradier connectivity test')
    args = parser.parse_args()

    print(f"\n{'=' * 60}")
    print(f"{BOLD}WATCHTOWER END-TO-END TESTS{RESET}")
    print(f"{'=' * 60}")
    print(f"Base URL: {args.url}")
    print(f"Time: {datetime.now(CENTRAL_TZ).strftime('%Y-%m-%d %I:%M:%S %p')} CT")

    # Run tests
    if not args.skip_tradier:
        test_tradier_connectivity()

    test_argus_api(args.url)
    test_cache_behavior(args.url)
    test_data_freshness(args.url)
    test_expected_range(args.url)

    return print_summary()


if __name__ == '__main__':
    sys.exit(main())
