#!/bin/bash
# =============================================================================
# AlphaGEX Full Production Check - Run in Render Shell
# =============================================================================
#
# Usage:
#   bash scripts/render_full_check.sh
#
# This runs ALL verification scripts in order.
# =============================================================================

set -e  # Exit on error

echo "============================================================"
echo "AlphaGEX Full Production Check"
echo "============================================================"
echo ""

# Track results
PASSED=0
FAILED=0

run_check() {
    local name=$1
    local script=$2

    echo ""
    echo ">>> Running: $name"
    echo "------------------------------------------------------------"

    if python "$script"; then
        PASSED=$((PASSED + 1))
        echo "[PASS] $name"
    else
        FAILED=$((FAILED + 1))
        echo "[FAIL] $name"
    fi
}

# Run all checks
run_check "Python Imports" "scripts/render_check_imports.py"
run_check "Database Connection" "scripts/render_check_database.py"
run_check "AI Features" "scripts/render_check_ai.py"
run_check "API Endpoints" "scripts/render_test_api.py"
run_check "Bot Status Endpoints" "scripts/render_verify_bots.py"
run_check "AI Init Script" "scripts/init_ai_features.py"

# Summary
echo ""
echo "============================================================"
echo "SUMMARY"
echo "============================================================"
echo "Passed: $PASSED"
echo "Failed: $FAILED"
echo ""

if [ $FAILED -eq 0 ]; then
    echo "ALL CHECKS PASSED - System is production ready!"
    exit 0
else
    echo "$FAILED check(s) failed - Review output above"
    exit 1
fi
