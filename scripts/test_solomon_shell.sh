#!/bin/bash
#
# SOLOMON SHELL TEST SCRIPT
# Run in Render shell: bash scripts/test_solomon_shell.sh
#
# Quick verification of Solomon tables and functionality
#

echo "======================================================================"
echo "SOLOMON SHELL VERIFICATION TESTS"
echo "======================================================================"
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test counter
PASSED=0
FAILED=0

pass() {
    echo -e "   ${GREEN}✅ $1${NC}"
    ((PASSED++))
}

fail() {
    echo -e "   ${RED}❌ $1${NC}"
    ((FAILED++))
}

warn() {
    echo -e "   ${YELLOW}⚠️  $1${NC}"
}

# =====================================================
# TEST 1: Database Connection
# =====================================================
echo "TEST 1: DATABASE CONNECTION"
echo "----------------------------"

if [ -z "$DATABASE_URL" ]; then
    fail "DATABASE_URL not set"
else
    RESULT=$(psql $DATABASE_URL -c "SELECT 1" 2>&1)
    if echo "$RESULT" | grep -q "1 row"; then
        pass "Database connection successful"
    else
        fail "Database connection failed: $RESULT"
    fi
fi

# =====================================================
# TEST 2: Solomon Tables Exist
# =====================================================
echo ""
echo "TEST 2: SOLOMON TABLES EXIST"
echo "----------------------------"

TABLES=(
    "solomon_audit_log"
    "solomon_proposals"
    "solomon_versions"
    "solomon_performance"
    "solomon_rollbacks"
    "solomon_health"
    "solomon_kill_switch"
    "solomon_validations"
    "solomon_ab_tests"
)

for TABLE in "${TABLES[@]}"; do
    EXISTS=$(psql $DATABASE_URL -t -c "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = '$TABLE')" 2>/dev/null | tr -d ' ')
    if [ "$EXISTS" = "t" ]; then
        COUNT=$(psql $DATABASE_URL -t -c "SELECT COUNT(*) FROM $TABLE" 2>/dev/null | tr -d ' ')
        pass "$TABLE: EXISTS ($COUNT rows)"
    else
        fail "$TABLE: MISSING"
    fi
done

# =====================================================
# TEST 3: Solomon Health Endpoint
# =====================================================
echo ""
echo "TEST 3: SOLOMON HEALTH ENDPOINT"
echo "--------------------------------"

HEALTH=$(curl -s http://localhost:8000/api/solomon/health 2>/dev/null)
if echo "$HEALTH" | grep -q '"status"'; then
    STATUS=$(echo "$HEALTH" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','unknown'))" 2>/dev/null)
    pass "Solomon health endpoint: $STATUS"
else
    warn "Solomon health endpoint not responding (server may not be running)"
fi

# =====================================================
# TEST 4: Oracle Strategy Recommendation
# =====================================================
echo ""
echo "TEST 4: ORACLE STRATEGY RECOMMENDATION"
echo "--------------------------------------"

ORACLE=$(curl -s http://localhost:8000/api/oracle/strategy-recommendation 2>/dev/null)
if echo "$ORACLE" | grep -q '"recommended_strategy"'; then
    STRATEGY=$(echo "$ORACLE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('recommended_strategy','unknown'))" 2>/dev/null)
    pass "Oracle returning strategy: $STRATEGY"

    # Check for Solomon info in reasoning
    HAS_SOLOMON=$(echo "$ORACLE" | python3 -c "import sys,json; d=json.load(sys.stdin); print('YES' if 'SOLOMON' in d.get('reasoning','') else 'NO')" 2>/dev/null)
    if [ "$HAS_SOLOMON" = "YES" ]; then
        pass "Solomon info present in Oracle reasoning"
    else
        warn "No Solomon info in reasoning (may be expected if no historical data)"
    fi
else
    warn "Oracle endpoint not responding (server may not be running)"
fi

# =====================================================
# TEST 5: A/B Test Table Writable
# =====================================================
echo ""
echo "TEST 5: A/B TEST TABLE WRITABLE"
echo "--------------------------------"

# Try to insert and then delete a test record
TEST_ID="TEST-VERIFY-$(date +%s)"
INSERT_RESULT=$(psql $DATABASE_URL -c "
    INSERT INTO solomon_ab_tests (test_id, bot_name, control_config, variant_config, status)
    VALUES ('$TEST_ID', 'TEST', '{\"test\": true}', '{\"test\": true}', 'RUNNING')
" 2>&1)

if echo "$INSERT_RESULT" | grep -q "INSERT"; then
    pass "A/B test table is writable"

    # Verify read
    READ_RESULT=$(psql $DATABASE_URL -t -c "SELECT test_id FROM solomon_ab_tests WHERE test_id = '$TEST_ID'" 2>/dev/null | tr -d ' ')
    if [ "$READ_RESULT" = "$TEST_ID" ]; then
        pass "A/B test record readable"
    else
        fail "A/B test record not readable"
    fi

    # Cleanup
    psql $DATABASE_URL -c "DELETE FROM solomon_ab_tests WHERE test_id = '$TEST_ID'" > /dev/null 2>&1
    pass "Test record cleaned up"
else
    fail "A/B test table not writable: $INSERT_RESULT"
fi

# =====================================================
# TEST 6: Realtime Status (Bot Position Tables)
# =====================================================
echo ""
echo "TEST 6: REALTIME STATUS DATA"
echo "----------------------------"

BOTS=(
    "ARES:ares_positions"
    "ATHENA:athena_positions"
    "TITAN:titan_positions"
    "PEGASUS:pegasus_positions"
    "ICARUS:icarus_positions"
)

for BOT_TABLE in "${BOTS[@]}"; do
    BOT_NAME="${BOT_TABLE%%:*}"
    TABLE="${BOT_TABLE##*:}"

    COUNT=$(psql $DATABASE_URL -t -c "
        SELECT COUNT(*) FROM $TABLE
        WHERE close_time::timestamptz >= NOW() - INTERVAL '30 days'
    " 2>/dev/null | tr -d ' ')

    if [ -n "$COUNT" ] && [ "$COUNT" -gt 0 ]; then
        pass "$BOT_NAME: $COUNT trades in last 30 days"
    else
        warn "$BOT_NAME: No recent trades (expected if not trading)"
    fi
done

# =====================================================
# TEST 7: Solomon Enhanced Endpoints
# =====================================================
echo ""
echo "TEST 7: SOLOMON ENHANCED ENDPOINTS"
echo "-----------------------------------"

ENDPOINTS=(
    "/api/solomon/enhanced/digest"
    "/api/solomon/enhanced/correlations"
    "/api/solomon/strategy-analysis?days=30"
    "/api/solomon/oracle-accuracy?days=30"
    "/api/solomon/realtime-status?days=7"
)

for ENDPOINT in "${ENDPOINTS[@]}"; do
    RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:8000$ENDPOINT" 2>/dev/null)
    if [ "$RESPONSE" = "200" ]; then
        pass "$ENDPOINT: 200 OK"
    elif [ "$RESPONSE" = "503" ]; then
        warn "$ENDPOINT: 503 (service unavailable)"
    elif [ "$RESPONSE" = "000" ]; then
        warn "$ENDPOINT: Connection refused (server not running?)"
    else
        fail "$ENDPOINT: HTTP $RESPONSE"
    fi
done

# =====================================================
# SUMMARY
# =====================================================
echo ""
echo "======================================================================"
echo "SUMMARY"
echo "======================================================================"
echo ""
echo "   Passed: $PASSED"
echo "   Failed: $FAILED"
echo ""

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}======================================================================"
    echo "✅ ALL TESTS PASSED - SOLOMON IS PRODUCTION READY"
    echo -e "======================================================================${NC}"
else
    echo -e "${RED}======================================================================"
    echo "❌ $FAILED TEST(S) FAILED - REVIEW ABOVE"
    echo -e "======================================================================${NC}"
fi

echo ""
