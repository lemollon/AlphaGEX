#!/usr/bin/env python3
"""
Master Test Runner - Run All AlphaGEX Tests
Run in Render shell: python scripts/tests/run_all_tests.py

This script runs all test suites in sequence and provides a comprehensive report.
"""

import os
import sys
import subprocess
from datetime import datetime

# Add parent directories to path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))


def print_banner():
    print("""
╔═══════════════════════════════════════════════════════════════╗
║                                                               ║
║     █████╗ ██╗     ██████╗ ██╗  ██╗ █████╗  ██████╗ ███████╗██╗  ██╗  ║
║    ██╔══██╗██║     ██╔══██╗██║  ██║██╔══██╗██╔════╝ ██╔════╝╚██╗██╔╝  ║
║    ███████║██║     ██████╔╝███████║███████║██║  ███╗█████╗   ╚███╔╝   ║
║    ██╔══██║██║     ██╔═══╝ ██╔══██║██╔══██║██║   ██║██╔══╝   ██╔██╗   ║
║    ██║  ██║███████╗██║     ██║  ██║██║  ██║╚██████╔╝███████╗██╔╝ ██╗  ║
║    ╚═╝  ╚═╝╚══════╝╚═╝     ╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═╝  ║
║                                                               ║
║              COMPREHENSIVE TEST SUITE RUNNER                  ║
║                                                               ║
╚═══════════════════════════════════════════════════════════════╝
""")


def run_test_suite(script_name, description):
    """Run a test script and return its exit code"""
    print(f"\n{'='*60}")
    print(f"  Running: {description}")
    print(f"  Script: {script_name}")
    print(f"{'='*60}")

    script_path = os.path.join(SCRIPT_DIR, script_name)

    if not os.path.exists(script_path):
        print(f"  ❌ Script not found: {script_path}")
        return 1

    try:
        # Change to project root for imports
        result = subprocess.run(
            [sys.executable, script_path],
            cwd=PROJECT_ROOT,
            env={**os.environ, 'PYTHONPATH': PROJECT_ROOT}
        )
        return result.returncode
    except Exception as e:
        print(f"  ❌ Error running script: {e}")
        return 1


def main():
    """Run all test suites"""
    print_banner()
    print(f"  Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Project Root: {PROJECT_ROOT}")

    # Define test suites
    test_suites = [
        ('test_database.py', 'Database Connectivity & Schema Tests'),
        ('test_api_endpoints.py', 'API Endpoint Tests'),
        ('test_integration.py', 'Integration Tests'),
    ]

    results = {}

    for script, description in test_suites:
        exit_code = run_test_suite(script, description)
        results[description] = exit_code == 0

    # Final Summary
    print("\n" + "="*60)
    print("  FINAL TEST RESULTS")
    print("="*60)

    passed = 0
    failed = 0

    for suite, result in results.items():
        status = "PASS ✓" if result else "FAIL ✗"
        print(f"  [{status}] {suite}")
        if result:
            passed += 1
        else:
            failed += 1

    print(f"\n  Total: {passed} passed, {failed} failed")
    print("="*60)

    if failed == 0:
        print("""
  ╔═══════════════════════════════════════════════════════════╗
  ║                                                           ║
  ║   ✅ ALL TESTS PASSED - System is healthy!               ║
  ║                                                           ║
  ╚═══════════════════════════════════════════════════════════╝
""")
        return 0
    else:
        print("""
  ╔═══════════════════════════════════════════════════════════╗
  ║                                                           ║
  ║   ⚠️  SOME TESTS FAILED - Review output above            ║
  ║                                                           ║
  ╚═══════════════════════════════════════════════════════════╝
""")
        return 1


if __name__ == "__main__":
    sys.exit(main())
