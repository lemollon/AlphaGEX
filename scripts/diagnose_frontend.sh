#!/bin/bash
#
# Frontend API Diagnostics Script
# Tests all API endpoints used by SPX Trader and Backtester pages
#
# Usage: ./diagnose_frontend.sh [api_url]
#

API_URL="${1:-https://alphagex-api.onrender.com}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo "========================================"
echo "  FRONTEND API DIAGNOSTICS"
echo "  $(date)"
echo "  API: $API_URL"
echo "========================================"

# Function to test an endpoint
test_endpoint() {
    local name="$1"
    local endpoint="$2"
    local response
    local http_code
    local body

    echo -e "\n${BLUE}Testing: $name${NC}"
    echo "  Endpoint: $endpoint"

    response=$(curl -s -w "\n%{http_code}" "$API_URL$endpoint" 2>/dev/null)
    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | sed '$d')

    if [ "$http_code" = "200" ]; then
        echo -e "  ${GREEN}✅ $http_code OK${NC}"
        # Check if response has success: true
        if echo "$body" | grep -q '"success": true\|"success":true'; then
            echo -e "  ${GREEN}✅ Response success: true${NC}"
        elif echo "$body" | grep -q '"success": false\|"success":false'; then
            echo -e "  ${YELLOW}⚠️  Response success: false${NC}"
            echo "$body" | python3 -m json.tool 2>/dev/null | head -10
        fi
        # Show first 200 chars of data
        echo "  Data preview: $(echo "$body" | head -c 200)..."
    else
        echo -e "  ${RED}❌ $http_code ERROR${NC}"
        echo "  Response: $(echo "$body" | head -c 500)"
    fi

    return $http_code
}

echo -e "\n${YELLOW}========== SPX TRADER ENDPOINTS ==========${NC}"

test_endpoint "SPX Status" "/api/spx/status"
test_endpoint "SPX Performance" "/api/spx/performance"

echo -e "\n${YELLOW}========== BACKTESTER ENDPOINTS ==========${NC}"

test_endpoint "Backtest Results" "/api/backtests/results"
test_endpoint "Backtest Summary" "/api/backtests/summary"
test_endpoint "Best Strategies" "/api/backtests/best-strategies"
test_endpoint "Smart Recommendations" "/api/backtests/smart-recommendations"

echo -e "\n${YELLOW}========== TRADER DIAGNOSTICS ==========${NC}"

test_endpoint "Trader Diagnostics" "/api/trader/diagnostics"
test_endpoint "Trader Status" "/api/trader/status"
test_endpoint "Trader Live Status" "/api/trader/live-status"

echo -e "\n${YELLOW}========== AUTONOMOUS ENDPOINTS ==========${NC}"

test_endpoint "Autonomous Logs" "/api/autonomous/logs?limit=5"
test_endpoint "Risk Status" "/api/autonomous/risk/status"
test_endpoint "Competition Leaderboard" "/api/autonomous/competition/leaderboard"
test_endpoint "ML Predictions" "/api/autonomous/ml/predictions/recent"

echo -e "\n${YELLOW}========== CORE DATA ENDPOINTS ==========${NC}"

test_endpoint "Time/Market Status" "/api/time"
test_endpoint "SPY GEX" "/api/gex/SPY"
test_endpoint "VIX Current" "/api/vix/current"

echo -e "\n========================================"
echo "  DIAGNOSTICS COMPLETE"
echo "========================================"

echo -e "\n${YELLOW}Quick Summary:${NC}"
echo "If you see 500 errors above, check the Render logs for Python tracebacks."
echo "Common issues:"
echo "  - PostgreSQL column name mismatches"
echo "  - Missing raw_connection for pandas queries"
echo "  - LIMIT placeholder issues"
echo ""
echo "To check Render logs:"
echo "  Look for lines containing 'ERROR' or 'Traceback'"
