#!/usr/bin/env python3
"""
MASTER TEST RUNNER
Runs all pipeline tests in sequence and provides a summary.

Run: python scripts/run_all_tests.py

Test Pipeline:
  01. Data Sources     - Polygon API, Trading Volatility API
  02. Backtest         - SPX Wheel backtest engine
  03. ML Training      - Feature extraction, model training
  04. API Endpoints    - FastAPI routes
  05. End-to-End       - Complete pipeline validation
"""

import os
import sys
import subprocess
from datetime import datetime

print("\n" + "="*70)
print(" ALPHAGEX PIPELINE TEST SUITE")
print(f" {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("="*70)

# Get script directory
script_dir = os.path.dirname(os.path.abspath(__file__))

# Define tests
tests = [
    ("01", "Data Sources", "test_01_data_sources.py"),
    ("02", "Backtest Execution", "test_02_backtest_execution.py"),
    ("03", "ML Training Pipeline", "test_03_ml_training.py"),
    ("04", "API Endpoints", "test_04_api_endpoints.py"),
    ("05", "End-to-End Pipeline", "test_05_end_to_end.py"),
]

results = {}

# Run each test
for test_id, test_name, test_file in tests:
    print(f"\n{'='*70}")
    print(f" RUNNING TEST {test_id}: {test_name.upper()}")
    print(f"{'='*70}")

    test_path = os.path.join(script_dir, test_file)

    if not os.path.exists(test_path):
        print(f"  [SKIP] Test file not found: {test_file}")
        results[test_id] = "SKIP"
        continue

    try:
        # Run the test
        result = subprocess.run(
            [sys.executable, test_path],
            capture_output=False,  # Show output in real-time
            timeout=120  # 2 minute timeout per test
        )

        results[test_id] = "PASS" if result.returncode == 0 else "FAIL"

    except subprocess.TimeoutExpired:
        print(f"  [TIMEOUT] Test exceeded 2 minute limit")
        results[test_id] = "TIMEOUT"

    except Exception as e:
        print(f"  [ERROR] {e}")
        results[test_id] = "ERROR"

# =============================================================================
# FINAL SUMMARY
# =============================================================================
print("\n" + "="*70)
print(" FINAL TEST SUMMARY")
print("="*70)

print("\n  Test Results:")
for test_id, test_name, _ in tests:
    result = results.get(test_id, "N/A")
    icon = {
        "PASS": "[OK]",
        "FAIL": "[XX]",
        "SKIP": "[--]",
        "TIMEOUT": "[TO]",
        "ERROR": "[!!]"
    }.get(result, "[??]")
    print(f"    {icon} Test {test_id}: {test_name} - {result}")

# Count results
passed = sum(1 for r in results.values() if r == "PASS")
failed = sum(1 for r in results.values() if r == "FAIL")
other = len(results) - passed - failed

print(f"\n  Summary: {passed} passed, {failed} failed, {other} other")

if failed == 0 and passed > 0:
    print("\n  All tests passed! Pipeline is working correctly.")
elif failed > 0:
    print(f"\n  {failed} test(s) failed. Review output above for details.")

print("\n" + "="*70 + "\n")

# Exit with appropriate code
sys.exit(0 if failed == 0 else 1)
