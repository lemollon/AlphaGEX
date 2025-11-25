#!/bin/bash
#
# Manually Trigger Autonomous Trader Cycle
# This will run the full trading logic and log exactly what happens
#
# Usage: ./trigger_trade.sh [api_url]
#

API_URL="${1:-https://alphagex-api.onrender.com}"

echo "========================================"
echo "  MANUAL TRADE TRIGGER"
echo "  $(date)"
echo "  API: $API_URL"
echo "========================================"

echo -e "\n⏳ Triggering trade cycle..."
echo "   This will analyze market conditions and execute a trade if conditions are met."
echo ""

# Execute trade cycle
response=$(curl -s -X POST "$API_URL/api/trader/execute" 2>/dev/null)

echo "Response:"
echo "$response" | python3 -m json.tool 2>/dev/null || echo "$response"

echo -e "\n========================================"

# Check the result
if echo "$response" | grep -q '"success": true'; then
    echo "✅ Trade cycle completed successfully"
else
    echo "⚠️ Trade cycle did not complete as expected"
fi

echo -e "\nNow checking trade log for details..."
echo ""

# Get latest trade log entries
curl -s "$API_URL/api/trader/trade-log" | python3 -m json.tool 2>/dev/null | head -50

echo -e "\n========================================"
echo "  Check Render logs for detailed output"
echo "========================================"
