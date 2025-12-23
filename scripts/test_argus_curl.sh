#!/bin/bash
#
# Quick ARGUS API tests using curl
# Run: bash scripts/test_argus_curl.sh
# Or with custom URL: API_URL=https://your-api.onrender.com bash scripts/test_argus_curl.sh
#

# Try to find a working URL
find_api_url() {
    local urls=("${API_URL:-}" "http://localhost:8000" "https://alphagex-api.onrender.com" "https://alphagex.onrender.com")

    for url in "${urls[@]}"; do
        if [ -z "$url" ]; then continue; fi
        echo "Trying $url..." >&2
        if curl -s --connect-timeout 3 "$url/health" > /dev/null 2>&1; then
            echo "  Connected!" >&2
            echo "$url"
            return 0
        fi
        echo "  Failed" >&2
    done
    return 1
}

echo "========================================"
echo "ARGUS API Tests (curl)"
echo "========================================"
echo ""
echo "Finding API server..."

BASE_URL=$(find_api_url)
if [ -z "$BASE_URL" ]; then
    echo "ERROR: Cannot connect to any API server!"
    echo "Try: API_URL=https://your-api-url.com bash scripts/test_argus_curl.sh"
    exit 1
fi

echo ""
echo "Using: $BASE_URL"
echo "========================================"

PASSED=0
FAILED=0

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
