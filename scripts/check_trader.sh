#!/bin/bash
#
# Autonomous Trader Health Check Script
# Usage: ./check_trader.sh [api_url]
#
# Examples:
#   ./check_trader.sh                                    # Uses default URL
#   ./check_trader.sh https://alphagex-api.onrender.com  # Custom URL
#

API_URL="${1:-https://alphagex-api.onrender.com}"

echo "========================================"
echo "  AUTONOMOUS TRADER HEALTH CHECK"
echo "  $(date)"
echo "  API: $API_URL"
echo "========================================"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to make API call and check response
check_endpoint() {
    local name="$1"
    local endpoint="$2"
    local response
    local http_code

    echo -e "\n${YELLOW}Checking: $name${NC}"

    response=$(curl -s -w "\n%{http_code}" "$API_URL$endpoint" 2>/dev/null)
    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | sed '$d')

    if [ "$http_code" = "200" ]; then
        echo -e "${GREEN}✅ $http_code OK${NC}"
        echo "$body" | python3 -m json.tool 2>/dev/null | head -20
    else
        echo -e "${RED}❌ $http_code ERROR${NC}"
        echo "$body" | head -5
    fi
}

# Check main status endpoints
echo -e "\n========== TRADER STATUS =========="
check_endpoint "Trader Status" "/api/trader/status"
check_endpoint "Live Status" "/api/trader/live-status"

echo -e "\n========== PERFORMANCE =========="
check_endpoint "Performance" "/api/trader/performance"

echo -e "\n========== RECENT TRADES =========="
check_endpoint "Recent Trades" "/api/trader/trades?limit=5"

echo -e "\n========== TRADE LOG =========="
check_endpoint "Trade Log" "/api/trader/trade-log"

echo -e "\n========== OPEN POSITIONS =========="
check_endpoint "Open Positions" "/api/trader/positions"

echo -e "\n========== AUTONOMOUS LOGS =========="
check_endpoint "Autonomous Logs" "/api/autonomous/logs?limit=5"

echo -e "\n========== RISK STATUS =========="
check_endpoint "Risk Status" "/api/autonomous/risk/status"

echo -e "\n========== MARKET DATA =========="
check_endpoint "Time/Market Status" "/api/time"
check_endpoint "SPY GEX" "/api/gex/SPY"
check_endpoint "VIX" "/api/vix/current"

echo -e "\n========================================"
echo "  HEALTH CHECK COMPLETE"
echo "========================================"

echo -e "\n${YELLOW}To manually trigger a trade:${NC}"
echo "  curl -X POST $API_URL/api/trader/execute"

echo -e "\n${YELLOW}To check scheduler thread:${NC}"
echo "  Look in Render logs for 'MARKET OPEN - Running cycle'"
