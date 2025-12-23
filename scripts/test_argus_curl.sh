#!/bin/bash
#
# Quick ARGUS API tests using curl
# Run: bash scripts/test_argus_curl.sh
#

BASE_URL="${API_URL:-http://localhost:8000}"
PASSED=0
FAILED=0

echo "========================================"
echo "ARGUS API Tests (curl)"
echo "Testing: $BASE_URL"
echo "========================================"

test_endpoint() {
    local name="$1"
    local endpoint="$2"

    echo -e "\nTEST: $name"
    echo "  Endpoint: $endpoint"

    response=$(curl -s -w "\n%{http_code}" "$BASE_URL$endpoint" 2>/dev/null)
    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | sed '$d')

    if [ "$http_code" != "200" ]; then
        echo "  ❌ FAIL: HTTP $http_code"
        ((FAILED++))
        return 1
    fi

    # Check for success field
    success=$(echo "$body" | grep -o '"success":[^,]*' | head -1)
    if [[ "$success" != *"true"* ]]; then
        echo "  ❌ FAIL: success != true"
        ((FAILED++))
        return 1
    fi

    echo "  ✅ PASS (HTTP 200, success=true)"
    ((PASSED++))
    return 0
}

# Run tests
test_endpoint "Main Gamma" "/api/argus/gamma"
test_endpoint "Strike Trends" "/api/argus/strike-trends"
test_endpoint "Gamma Flips" "/api/argus/gamma-flips"
test_endpoint "Danger Zone Logs" "/api/argus/danger-zones/log"
test_endpoint "Expirations" "/api/argus/expirations"
test_endpoint "Alerts" "/api/argus/alerts"
test_endpoint "Context" "/api/argus/context"

# Summary
echo -e "\n========================================"
echo "SUMMARY"
echo "========================================"
echo "  Passed: $PASSED"
echo "  Failed: $FAILED"
echo "  Total:  $((PASSED + FAILED))"

if [ $FAILED -eq 0 ]; then
    echo -e "\n*** ALL TESTS PASSED ***"
    exit 0
else
    echo -e "\n*** SOME TESTS FAILED ***"
    exit 1
fi
