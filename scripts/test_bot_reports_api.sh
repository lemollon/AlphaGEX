#!/bin/bash
#
# API Test Script for Bot Reports
#
# Run from Render shell or locally to test API endpoints
#
# Usage:
#   ./scripts/test_bot_reports_api.sh [BASE_URL]
#
# Examples:
#   ./scripts/test_bot_reports_api.sh                          # Uses localhost:8000
#   ./scripts/test_bot_reports_api.sh https://api.alphagex.com # Uses production
#

BASE_URL="${1:-http://localhost:8000}"
BOT="ares"  # Test with ARES

echo "=============================================="
echo "  Bot Reports API Test"
echo "  Base URL: $BASE_URL"
echo "=============================================="

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

pass() { echo -e "${GREEN}✅ PASS${NC}: $1"; }
fail() { echo -e "${RED}❌ FAIL${NC}: $1"; }

# Test 1: Get today's report
echo ""
echo "--- Test 1: GET /{bot}/reports/today ---"
RESPONSE=$(curl -s -w "\n%{http_code}" "$BASE_URL/api/trader/$BOT/reports/today")
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [ "$HTTP_CODE" = "200" ]; then
    pass "GET /api/trader/$BOT/reports/today (HTTP $HTTP_CODE)"
    echo "     Response: $(echo $BODY | head -c 200)..."
else
    fail "GET /api/trader/$BOT/reports/today (HTTP $HTTP_CODE)"
    echo "     Response: $BODY"
fi

# Test 2: Get archive stats
echo ""
echo "--- Test 2: GET /{bot}/reports/archive/stats ---"
RESPONSE=$(curl -s -w "\n%{http_code}" "$BASE_URL/api/trader/$BOT/reports/archive/stats")
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [ "$HTTP_CODE" = "200" ]; then
    pass "GET /api/trader/$BOT/reports/archive/stats (HTTP $HTTP_CODE)"
    echo "     Response: $BODY"
else
    fail "GET /api/trader/$BOT/reports/archive/stats (HTTP $HTTP_CODE)"
    echo "     Response: $BODY"
fi

# Test 3: Get archive list
echo ""
echo "--- Test 3: GET /{bot}/reports/archive ---"
RESPONSE=$(curl -s -w "\n%{http_code}" "$BASE_URL/api/trader/$BOT/reports/archive?limit=5")
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [ "$HTTP_CODE" = "200" ]; then
    pass "GET /api/trader/$BOT/reports/archive (HTTP $HTTP_CODE)"
    echo "     Response: $(echo $BODY | head -c 300)..."
else
    fail "GET /api/trader/$BOT/reports/archive (HTTP $HTTP_CODE)"
    echo "     Response: $BODY"
fi

# Test 4: Get specific date (should 404 for non-existent)
echo ""
echo "--- Test 4: GET /{bot}/reports/archive/{date} ---"
TEST_DATE="2025-01-01"
RESPONSE=$(curl -s -w "\n%{http_code}" "$BASE_URL/api/trader/$BOT/reports/archive/$TEST_DATE")
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "404" ]; then
    pass "GET /api/trader/$BOT/reports/archive/$TEST_DATE (HTTP $HTTP_CODE - expected 200 or 404)"
else
    fail "GET /api/trader/$BOT/reports/archive/$TEST_DATE (HTTP $HTTP_CODE)"
    echo "     Response: $BODY"
fi

# Test 5: Invalid bot should 400
echo ""
echo "--- Test 5: Invalid bot returns 400 ---"
RESPONSE=$(curl -s -w "\n%{http_code}" "$BASE_URL/api/trader/invalidbot/reports/today")
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)

if [ "$HTTP_CODE" = "400" ]; then
    pass "Invalid bot returns 400 (HTTP $HTTP_CODE)"
else
    fail "Invalid bot should return 400, got HTTP $HTTP_CODE"
fi

# Test 6: Future date should 400
echo ""
echo "--- Test 6: Future date returns 400 ---"
FUTURE_DATE="2030-01-01"
RESPONSE=$(curl -s -w "\n%{http_code}" "$BASE_URL/api/trader/$BOT/reports/archive/$FUTURE_DATE")
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)

if [ "$HTTP_CODE" = "400" ]; then
    pass "Future date returns 400 (HTTP $HTTP_CODE)"
else
    fail "Future date should return 400, got HTTP $HTTP_CODE"
fi

# Test 7: Generate report (POST)
echo ""
echo "--- Test 7: POST /{bot}/reports/generate ---"
echo "     (This may take 10-30 seconds if there are trades...)"
RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/api/trader/$BOT/reports/generate")
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [ "$HTTP_CODE" = "200" ]; then
    pass "POST /api/trader/$BOT/reports/generate (HTTP $HTTP_CODE)"
    # Check if report has expected fields
    if echo "$BODY" | grep -q "total_pnl"; then
        echo "     ✓ Response contains total_pnl"
    fi
    if echo "$BODY" | grep -q "trade_count"; then
        echo "     ✓ Response contains trade_count"
    fi
    if echo "$BODY" | grep -q "trade_analyses"; then
        echo "     ✓ Response contains trade_analyses"
    fi
else
    fail "POST /api/trader/$BOT/reports/generate (HTTP $HTTP_CODE)"
    echo "     Response: $(echo $BODY | head -c 500)"
fi

echo ""
echo "=============================================="
echo "  API Tests Complete"
echo "=============================================="
