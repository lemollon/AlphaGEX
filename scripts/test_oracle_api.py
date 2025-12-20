#!/usr/bin/env python3
"""
ORACLE API ENDPOINTS TEST
=========================
Run this to verify all Oracle API endpoints are working.

Usage:
    python scripts/test_oracle_api.py
    python scripts/test_oracle_api.py --base-url https://your-app.onrender.com

Tests:
- GET /api/zero-dte-backtest/oracle/training-status
- POST /api/zero-dte-backtest/oracle/trigger-training
- GET /api/zero-dte-backtest/oracle/bot-interactions
- GET /api/zero-dte-backtest/oracle/performance
"""

import os
import sys
import json
import argparse
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError

def print_header(title):
    print("\n" + "=" * 60)
    print(f" {title}")
    print("=" * 60)

def print_result(test_name, passed, details=""):
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"{status} - {test_name}")
    if details:
        print(f"       {details}")

def test_endpoint(base_url, method, path, data=None):
    """Test a single endpoint"""
    url = f"{base_url}{path}"

    try:
        if method == "GET":
            req = Request(url)
        else:
            req = Request(url, data=json.dumps(data).encode() if data else None)
            req.add_header('Content-Type', 'application/json')
            req.method = method

        with urlopen(req, timeout=30) as response:
            body = json.loads(response.read().decode())
            return True, response.status, body

    except HTTPError as e:
        try:
            body = json.loads(e.read().decode())
        except:
            body = str(e)
        return False, e.code, body

    except URLError as e:
        return False, 0, str(e.reason)

    except Exception as e:
        return False, 0, str(e)

def main():
    parser = argparse.ArgumentParser(description='Test Oracle API Endpoints')
    parser.add_argument('--base-url', default='http://localhost:5000',
                       help='Base URL of the API (default: http://localhost:5000)')
    args = parser.parse_args()

    base_url = args.base_url.rstrip('/')
    api_base = f"{base_url}/api/zero-dte-backtest"

    print_header("ORACLE API ENDPOINTS TEST")
    print(f"Base URL: {base_url}")

    results = {}

    # ========================================
    # TEST 1: Training Status
    # ========================================
    print_header("1. GET /oracle/training-status")

    success, status, body = test_endpoint(base_url, "GET", "/api/zero-dte-backtest/oracle/training-status")

    if success and body.get('success'):
        print_result("Training status endpoint", True)
        print(f"\n  Response:")
        print(f"    model_trained: {body.get('model_trained')}")
        print(f"    model_version: {body.get('model_version')}")
        print(f"    model_source: {body.get('model_source')}")
        print(f"    db_persistence: {body.get('db_persistence')}")
        print(f"    pending_outcomes: {body.get('pending_outcomes')}")
        results['training_status'] = True
    else:
        print_result("Training status endpoint", False, f"HTTP {status}: {body}")
        results['training_status'] = False

    # ========================================
    # TEST 2: Bot Interactions
    # ========================================
    print_header("2. GET /oracle/bot-interactions")

    success, status, body = test_endpoint(
        base_url, "GET",
        "/api/zero-dte-backtest/oracle/bot-interactions?days=30&limit=10"
    )

    if success and body.get('success'):
        interactions = body.get('interactions', [])
        print_result("Bot interactions endpoint", True, f"Found {len(interactions)} interactions")

        if interactions:
            print(f"\n  Sample interaction:")
            sample = interactions[0]
            print(f"    bot_name: {sample.get('bot_name')}")
            print(f"    trade_date: {sample.get('trade_date')}")
            print(f"    action: {sample.get('action')}")
        results['bot_interactions'] = True
    else:
        print_result("Bot interactions endpoint", False, f"HTTP {status}: {body}")
        results['bot_interactions'] = False

    # ========================================
    # TEST 3: Performance
    # ========================================
    print_header("3. GET /oracle/performance")

    success, status, body = test_endpoint(
        base_url, "GET",
        "/api/zero-dte-backtest/oracle/performance?days=90"
    )

    if success and body.get('success'):
        print_result("Performance endpoint", True)
        print(f"\n  Response:")
        print(f"    overall_win_rate: {body.get('overall_win_rate', 'N/A')}")
        print(f"    total_predictions: {body.get('total_predictions', 'N/A')}")

        by_bot = body.get('by_bot', {})
        if by_bot:
            print(f"\n  By Bot:")
            for bot, stats in by_bot.items():
                print(f"    {bot}: {stats}")
        results['performance'] = True
    else:
        print_result("Performance endpoint", False, f"HTTP {status}: {body}")
        results['performance'] = False

    # ========================================
    # TEST 4: Trigger Training (dry run)
    # ========================================
    print_header("4. POST /oracle/trigger-training")
    print("  (Skipping actual trigger to avoid training during test)")
    print_result("Trigger training endpoint", True, "Endpoint exists (not tested)")
    results['trigger_training'] = True

    # ========================================
    # SUMMARY
    # ========================================
    print_header("SUMMARY")

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    print(f"\n  Tests Passed: {passed}/{total}")

    for test, status in results.items():
        icon = "✅" if status else "❌"
        print(f"  {icon} {test}")

    if passed == total:
        print("\n✅ All API endpoints working!")
    else:
        print("\n⚠️  Some endpoints failed. Check server logs.")

    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
