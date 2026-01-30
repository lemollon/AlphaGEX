#!/bin/bash
#
# PROMETHEUS Full Test Suite for Render Shell
#
# Run all PROMETHEUS tests:
#   chmod +x scripts/test_prometheus_full.sh
#   ./scripts/test_prometheus_full.sh
#
# Or run directly:
#   bash scripts/test_prometheus_full.sh
#

set -e

echo "=================================================="
echo "PROMETHEUS FULL TEST SUITE"
echo "=================================================="
echo "Timestamp: $(date -Iseconds)"
echo ""

# Colors
GREEN='\033[92m'
RED='\033[91m'
YELLOW='\033[93m'
BLUE='\033[94m'
RESET='\033[0m'
BOLD='\033[1m'

# Track results
TESTS_PASSED=0
TESTS_FAILED=0

run_test() {
    local name=$1
    local script=$2

    echo -e "\n${BOLD}${BLUE}Running: $name${RESET}"
    echo "----------------------------------------"

    if python "$script"; then
        echo -e "${GREEN}✓ $name PASSED${RESET}"
        ((TESTS_PASSED++))
    else
        echo -e "${RED}✗ $name FAILED${RESET}"
        ((TESTS_FAILED++))
    fi
}

# Change to project root
cd "$(dirname "$0")/.."

# Set API base URL if not set
if [ -z "$API_BASE_URL" ]; then
    export API_BASE_URL="http://localhost:8000"
    echo "Using default API_BASE_URL: $API_BASE_URL"
fi

# Run database tests
run_test "Database Verification" "scripts/test_prometheus_db.py"

# Run API tests
run_test "API Endpoint Tests" "scripts/test_prometheus_api.py"

# Summary
echo ""
echo "=================================================="
echo "FINAL SUMMARY"
echo "=================================================="
echo -e "Tests Passed: ${GREEN}$TESTS_PASSED${RESET}"
echo -e "Tests Failed: ${RED}$TESTS_FAILED${RESET}"

if [ $TESTS_FAILED -gt 0 ]; then
    echo -e "\n${RED}SOME TESTS FAILED!${RESET}"
    exit 1
else
    echo -e "\n${GREEN}ALL TESTS PASSED!${RESET}"
    exit 0
fi
