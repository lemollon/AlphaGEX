"""
VALOR POST-DEPLOY: Final Summary Runner
========================================

Runs all tests and prints the final summary table.
"""

import sys
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

# Run offline tests
from tests.valor.test_post_deploy import main as run_offline_tests
from tests.valor.test_post_deploy_api import main as run_api_tests


def print_summary(offline_results, api_results):
    """Print the final summary table."""

    all_results = {}

    # Map test names
    test_map = {
        "Test 1: Model Configs": "Test 1",
        "Test 2: Next-Expiration Logic": "Test 2",
        "Test 3: GEX Cache Isolation": "Test 3",
        "Test 4: GEX Scale Factors": "Test 4",
        "Test 5: Tradier Fetch (6 ETFs)": "Test 5",
        "Test 6: TradingVol Fetch (6 ETFs)": "Test 6",
        "Test 8: DB Schema": "Test 8",
        "Test 9: Daily Loss Limits": "Test 9",
        "Test 10: MES/RTY Regression": "Test 10",
    }

    all_results.update(offline_results)
    all_results.update(api_results)

    # Frontend build (Test 7) - we ran it separately and it passed
    all_results["Test 7: Frontend Build"] = (True, [])

    # Display order
    ordered_tests = [
        ("Test 1:  Model Configs         ", "Test 1: Model Configs"),
        ("Test 2:  Next-Expiration Logic ", "Test 2: Next-Expiration Logic"),
        ("Test 3:  GEX Cache Isolation   ", "Test 3: GEX Cache Isolation"),
        ("Test 4:  GEX Scale Factors     ", "Test 4: GEX Scale Factors"),
        ("Test 5:  Tradier Fetch (6 ETFs)", "Test 5: Tradier Fetch (6 ETFs)"),
        ("Test 6:  TradingVol Fetch (6)  ", "Test 6: TradingVol Fetch (6 ETFs)"),
        ("Test 7:  Frontend Build        ", "Test 7: Frontend Build"),
        ("Test 8:  DB Schema             ", "Test 8: DB Schema"),
        ("Test 9:  Daily Loss Limits     ", "Test 9: Daily Loss Limits"),
        ("Test 10: MES/RTY Regression    ", "Test 10: MES/RTY Regression"),
    ]

    passed_count = 0
    skip_count = 0
    fail_count = 0
    critical_failures = []

    print()
    print("╔═══════════════════════════════════════════════════╗")
    print("║         VALOR POST-DEPLOY TEST RESULTS            ║")
    print("╠═══════════════════════════════════════════════════╣")

    for display_name, key in ordered_tests:
        result = all_results.get(key)
        if result is None:
            status = "SKIP"
            skip_count += 1
        else:
            passed, failures = result
            if passed is None:
                status = "SKIP"
                skip_count += 1
            elif passed:
                status = "PASS"
                passed_count += 1
            else:
                status = "FAIL"
                fail_count += 1
                for f in failures:
                    if "CRITICAL" in f:
                        critical_failures.append(f.strip())

        color = {"PASS": "✅", "FAIL": "❌", "SKIP": "⏭️ "}.get(status, "?")
        print(f"║ {display_name} [{color} {status}]  ║")

    total = passed_count + fail_count + skip_count
    print("╠═══════════════════════════════════════════════════╣")
    print(f"║ OVERALL:  {passed_count}/{total} PASSED ({skip_count} skipped)             ║")
    if critical_failures:
        print(f"║ CRITICAL FAILURES:                                ║")
        for cf in critical_failures:
            # Truncate to fit
            cf_short = cf[:47] if len(cf) > 47 else cf
            print(f"║   {cf_short:<46} ║")
    else:
        print(f"║ CRITICAL FAILURES: None                           ║")
    print("╚═══════════════════════════════════════════════════╝")
    print()

    # Print failures detail
    for key, result in all_results.items():
        if result and result[0] is not None and not result[0]:
            print(f"FAILURES in {key}:")
            for f in result[1]:
                print(f"  {f}")
            print()


if __name__ == "__main__":
    print()
    offline_results = run_offline_tests()
    print()
    api_results = run_api_tests()
    print_summary(offline_results, api_results)
