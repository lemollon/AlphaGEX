#!/usr/bin/env python3
"""
AlphaGEX Master Production Test Runner
========================================
Runs ALL production test suites and reports combined results.

Run: python tests/run_production_tests.py --api-url https://your-app.onrender.com
"""

import os
import sys
import argparse
import subprocess
from datetime import datetime

def run_test_suite(script_name: str, args: list = None) -> dict:
    """Run a test script and capture results."""
    script_path = os.path.join(os.path.dirname(__file__), script_name)

    if not os.path.exists(script_path):
        return {"name": script_name, "passed": 0, "failed": 1, "error": "Script not found"}

    cmd = [sys.executable, script_path] + (args or [])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        output = result.stdout + result.stderr

        # Parse results from output
        passed = 0
        failed = 0
        for line in output.split('\n'):
            if 'PASSED:' in line:
                try:
                    passed = int(line.split('PASSED:')[1].strip().split()[0])
                except:
                    pass
            if 'FAILED:' in line:
                try:
                    failed = int(line.split('FAILED:')[1].strip().split()[0])
                except:
                    pass

        return {
            "name": script_name,
            "passed": passed,
            "failed": failed,
            "exit_code": result.returncode,
            "output": output
        }

    except subprocess.TimeoutExpired:
        return {"name": script_name, "passed": 0, "failed": 1, "error": "Test timed out (300s)"}
    except Exception as e:
        return {"name": script_name, "passed": 0, "failed": 1, "error": str(e)}


def main():
    parser = argparse.ArgumentParser(description="AlphaGEX Master Production Test Runner")
    parser.add_argument("--api-url", default=os.environ.get("API_URL", "http://localhost:8000"),
                        help="Base API URL for API tests")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Show full test output")
    args = parser.parse_args()

    print("=" * 60)
    print("ALPHAGEX PRODUCTION TEST SUITE")
    print("=" * 60)
    print(f"API URL: {args.api_url}")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print("=" * 60)

    # Test suites to run
    test_suites = [
        ("production_api_test.py", ["--api-url", args.api_url]),
        ("production_trading_logic_test.py", []),
    ]

    total_passed = 0
    total_failed = 0
    results = []

    for script_name, script_args in test_suites:
        print(f"\nRunning: {script_name}")
        result = run_test_suite(script_name, script_args)
        results.append(result)

        total_passed += result.get("passed", 0)
        total_failed += result.get("failed", 0)

        if result.get("error"):
            print(f"  ERROR: {result['error']}")
        else:
            print(f"  {result['passed']} passed, {result['failed']} failed")

        if args.verbose and result.get("output"):
            print("\n--- OUTPUT ---")
            print(result["output"])
            print("--- END OUTPUT ---")

    # Summary
    print("\n" + "=" * 60)
    print("MASTER RESULTS")
    print("=" * 60)

    for result in results:
        status = "OK" if result.get("failed", 0) == 0 and not result.get("error") else "FAIL"
        print(f"  [{status}] {result['name']}: {result.get('passed', 0)} passed, {result.get('failed', 0)} failed")

    print("=" * 60)
    print(f"TOTAL: {total_passed} PASSED, {total_failed} FAILED")
    print("=" * 60)

    if total_failed == 0:
        print("\n✅ DEPLOYMENT STATUS: READY")
        return 0
    else:
        print(f"\n❌ DEPLOYMENT STATUS: NOT READY - Fix {total_failed} failures")
        return 1


if __name__ == "__main__":
    sys.exit(main())
