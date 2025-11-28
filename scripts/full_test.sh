#!/bin/bash
#
# AlphaGEX Full System Test
# Run this on Render after deploy to verify everything works
#
# Usage:
#   ./scripts/full_test.sh https://your-app.onrender.com
#
#   Or without URL for local-only tests:
#   ./scripts/full_test.sh
#

set -e

BASE_URL="${1:-}"
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "========================================"
echo " ALPHAGEX FULL SYSTEM TEST"
echo " $(date)"
echo "========================================"

if [ -n "$BASE_URL" ]; then
    echo "Target: $BASE_URL"
else
    echo "Mode: Local only (no API tests)"
fi
echo ""

# Run Python test script
echo "Running comprehensive Python tests..."
echo ""
python scripts/test_all.py $BASE_URL

# If URL provided, run additional curl tests
if [ -n "$BASE_URL" ]; then
    echo ""
    echo "========================================"
    echo " ADDITIONAL API TESTS"
    echo "========================================"

    # Health check
    echo -n "Health check: "
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/api/health" 2>/dev/null || echo "000")
    if [ "$HTTP_CODE" = "200" ]; then
        echo -e "${GREEN}OK${NC}"
    else
        echo -e "${RED}FAILED (HTTP $HTTP_CODE)${NC}"
    fi

    # Trader status
    echo -n "Trader status: "
    RESP=$(curl -s "$BASE_URL/api/trader/status" 2>/dev/null || echo '{"success":false}')
    if echo "$RESP" | grep -q '"success":true'; then
        echo -e "${GREEN}OK${NC}"
    else
        echo -e "${YELLOW}WARN${NC} - $RESP"
    fi

    # SPX status
    echo -n "SPX status: "
    RESP=$(curl -s "$BASE_URL/api/spx/status" 2>/dev/null || echo '{"success":false}')
    if echo "$RESP" | grep -q '"success":true'; then
        echo -e "${GREEN}OK${NC}"
    else
        echo -e "${YELLOW}WARN${NC}"
    fi

    # GEX data
    echo -n "GEX data: "
    RESP=$(curl -s "$BASE_URL/api/gex/SPY" 2>/dev/null || echo '{"success":false}')
    if echo "$RESP" | grep -q '"success":true'; then
        echo -e "${GREEN}OK${NC}"
    else
        echo -e "${YELLOW}WARN${NC}"
    fi

    # Regime
    echo -n "Market regime: "
    RESP=$(curl -s "$BASE_URL/api/regime/current" 2>/dev/null || echo '{"success":false}')
    if echo "$RESP" | grep -q '"success":true'; then
        echo -e "${GREEN}OK${NC}"
    else
        echo -e "${YELLOW}WARN${NC}"
    fi

    # Strategy stats
    echo -n "Strategy stats: "
    RESP=$(curl -s "$BASE_URL/api/strategies/stats" 2>/dev/null || echo '{"success":false}')
    if echo "$RESP" | grep -q '"success":true'; then
        echo -e "${GREEN}OK${NC}"
        # Check if any are from backtest
        if echo "$RESP" | grep -q '"source":"backtest"'; then
            echo "  └─ Stats updated from backtests ✓"
        else
            echo -e "  └─ ${YELLOW}All stats are initial estimates - run backtests${NC}"
        fi
    else
        echo -e "${YELLOW}WARN${NC}"
    fi

    # Backtest results
    echo -n "Backtest results: "
    RESP=$(curl -s "$BASE_URL/api/backtests/results" 2>/dev/null || echo '{"success":false}')
    if echo "$RESP" | grep -q '"success":true'; then
        echo -e "${GREEN}OK${NC}"
    else
        echo -e "${YELLOW}WARN${NC}"
    fi

    # AI Intelligence endpoints (the ones that were failing)
    echo -n "AI market-commentary: "
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/api/ai-intelligence/market-commentary" 2>/dev/null || echo "000")
    if [ "$HTTP_CODE" = "200" ]; then
        echo -e "${GREEN}OK${NC}"
    else
        echo -e "${YELLOW}HTTP $HTTP_CODE${NC}"
    fi

    echo -n "AI daily-trading-plan: "
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/api/ai-intelligence/daily-trading-plan" 2>/dev/null || echo "000")
    if [ "$HTTP_CODE" = "200" ]; then
        echo -e "${GREEN}OK${NC}"
    else
        echo -e "${YELLOW}HTTP $HTTP_CODE${NC}"
    fi

    echo ""
    echo "========================================"
    echo " TRIGGER BACKTEST (Optional)"
    echo "========================================"
    echo "To trigger a backtest and update strategy stats:"
    echo "  curl -X POST $BASE_URL/api/backtests/run"
    echo ""
fi

echo "========================================"
echo " TEST COMPLETE"
echo "========================================"
