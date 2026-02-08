#!/bin/bash
#
# Quick API tests for COUNSELOR - run after deploy
# Usage: ./scripts/tests/test_gexis_api.sh [API_BASE_URL]
#

API_BASE="${1:-https://alphagex-api.onrender.com}"

echo "========================================"
echo "COUNSELOR API Tests"
echo "API: $API_BASE"
echo "========================================"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

pass() { echo -e "${GREEN}✓ PASS${NC}: $1"; }
fail() { echo -e "${RED}✗ FAIL${NC}: $1"; }

# Test 1: COUNSELOR Info
echo ""
echo "Test 1: COUNSELOR Info"
RESP=$(curl -s "$API_BASE/api/ai/counselor/info" 2>/dev/null)
if echo "$RESP" | grep -q '"success":true'; then
    pass "GET /api/ai/counselor/info"
else
    fail "GET /api/ai/counselor/info - Response: $RESP"
fi

# Test 2: COUNSELOR Welcome (Proactive Briefing)
echo ""
echo "Test 2: COUNSELOR Welcome (Proactive Briefing)"
RESP=$(curl -s "$API_BASE/api/ai/counselor/welcome" 2>/dev/null)
if echo "$RESP" | grep -q '"success":true'; then
    if echo "$RESP" | grep -q 'Optionist Prime'; then
        pass "GET /api/ai/counselor/welcome - Contains 'Optionist Prime'"
    else
        fail "GET /api/ai/counselor/welcome - Missing 'Optionist Prime'"
    fi
else
    fail "GET /api/ai/counselor/welcome - Response: $RESP"
fi

# Test 3: Slash Command /help
echo ""
echo "Test 3: Slash Command /help"
RESP=$(curl -s -X POST "$API_BASE/api/ai/analyze" \
    -H "Content-Type: application/json" \
    -d '{"query": "/help"}' 2>/dev/null)
if echo "$RESP" | grep -q '"success":true'; then
    if echo "$RESP" | grep -q '"is_command":true'; then
        pass "POST /api/ai/analyze with /help - Detected as command"
    else
        fail "POST /api/ai/analyze with /help - Not detected as command"
    fi
else
    fail "POST /api/ai/analyze with /help - Response: $RESP"
fi

# Test 4: Slash Command /status
echo ""
echo "Test 4: Slash Command /status"
RESP=$(curl -s -X POST "$API_BASE/api/ai/analyze" \
    -H "Content-Type: application/json" \
    -d '{"query": "/status"}' 2>/dev/null)
if echo "$RESP" | grep -q '"success":true'; then
    pass "POST /api/ai/analyze with /status"
else
    fail "POST /api/ai/analyze with /status - Response: $RESP"
fi

# Test 5: Slash Command /calendar
echo ""
echo "Test 5: Slash Command /calendar"
RESP=$(curl -s -X POST "$API_BASE/api/ai/analyze" \
    -H "Content-Type: application/json" \
    -d '{"query": "/calendar"}' 2>/dev/null)
if echo "$RESP" | grep -q '"success":true'; then
    pass "POST /api/ai/analyze with /calendar"
else
    fail "POST /api/ai/analyze with /calendar - Response: $RESP"
fi

# Test 6: Bot Control /start fortress (should require confirmation)
echo ""
echo "Test 6: Bot Control /start fortress"
RESP=$(curl -s -X POST "$API_BASE/api/ai/analyze" \
    -H "Content-Type: application/json" \
    -d '{"query": "/start fortress"}' 2>/dev/null)
if echo "$RESP" | grep -q '"success":true'; then
    if echo "$RESP" | grep -q 'confirm\|Confirm'; then
        pass "POST /api/ai/analyze with /start fortress - Asks for confirmation"
    else
        fail "POST /api/ai/analyze with /start fortress - No confirmation prompt"
    fi
else
    fail "POST /api/ai/analyze with /start fortress - Response: $RESP"
fi

# Test 7: Natural Language Query
echo ""
echo "Test 7: Natural Language Query"
RESP=$(curl -s -X POST "$API_BASE/api/ai/analyze" \
    -H "Content-Type: application/json" \
    -d '{"query": "What is GEX?"}' 2>/dev/null)
if echo "$RESP" | grep -q '"success":true'; then
    if echo "$RESP" | grep -qi 'gamma\|exposure\|gex'; then
        pass "Natural language query answered correctly"
    else
        fail "Natural language query - no relevant content"
    fi
else
    fail "Natural language query - Response: $RESP"
fi

echo ""
echo "========================================"
echo "Tests Complete"
echo "========================================"
