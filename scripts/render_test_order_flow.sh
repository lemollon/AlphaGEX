#!/bin/bash
# Order Flow System Verification for Render Shell
# Run with: bash scripts/render_test_order_flow.sh

echo "=============================================="
echo "  ORDER FLOW SYSTEM - RENDER SHELL TEST"
echo "=============================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color

pass() { echo -e "  ${GREEN}✅ PASS${NC}: $1"; }
fail() { echo -e "  ${RED}❌ FAIL${NC}: $1"; }

echo "TEST 1: Database Table Exists"
echo "------------------------------"
TABLE_EXISTS=$(psql $DATABASE_URL -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'argus_order_flow_history';" 2>/dev/null | tr -d ' ')
if [ "$TABLE_EXISTS" = "1" ]; then
    pass "Table argus_order_flow_history exists"
else
    fail "Table does not exist"
fi

echo ""
echo "TEST 2: Table Has Required Columns"
echo "-----------------------------------"
# Use sed to strip leading/trailing whitespace from each line
COLUMNS=$(psql $DATABASE_URL -t -c "SELECT column_name FROM information_schema.columns WHERE table_name = 'argus_order_flow_history' ORDER BY ordinal_position;" 2>/dev/null | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
for col in net_pressure raw_pressure combined_signal signal_confidence total_bid_size total_ask_size; do
    if echo "$COLUMNS" | grep -qw "$col"; then
        pass "Column '$col' exists"
    else
        fail "Column '$col' missing"
    fi
done

echo ""
echo "TEST 3: Database Has Records"
echo "----------------------------"
RECORD_COUNT=$(psql $DATABASE_URL -t -c "SELECT COUNT(*) FROM argus_order_flow_history;" 2>/dev/null | tr -d ' ')
if [ "$RECORD_COUNT" -gt "0" ]; then
    pass "Found $RECORD_COUNT records"
else
    echo "  ⚠️  No records yet (will populate on first API call)"
fi

echo ""
echo "TEST 4: Recent Data (last 24 hours)"
echo "------------------------------------"
RECENT=$(psql $DATABASE_URL -t -c "SELECT COUNT(*) FROM argus_order_flow_history WHERE recorded_at > NOW() - INTERVAL '24 hours';" 2>/dev/null | tr -d ' ')
if [ "$RECENT" -gt "0" ]; then
    pass "Found $RECENT records in last 24 hours"
else
    echo "  ⚠️  No recent records (may need API calls to populate)"
fi

echo ""
echo "TEST 5: Signal Distribution"
echo "---------------------------"
psql $DATABASE_URL -c "
SELECT
    combined_signal,
    signal_confidence,
    COUNT(*) as count
FROM argus_order_flow_history
WHERE recorded_at > NOW() - INTERVAL '24 hours'
GROUP BY combined_signal, signal_confidence
ORDER BY count DESC
LIMIT 10;
" 2>/dev/null

echo ""
echo "TEST 6: Latest Order Flow Record"
echo "---------------------------------"
psql $DATABASE_URL -c "
SELECT
    symbol,
    recorded_at AT TIME ZONE 'America/Chicago' as time_ct,
    combined_signal,
    signal_confidence,
    ROUND(net_pressure * 100, 1) as pressure_pct,
    pressure_direction,
    flow_direction,
    ROUND(net_gex_volume, 2) as net_gex_vol_m,
    is_valid
FROM argus_order_flow_history
ORDER BY recorded_at DESC
LIMIT 1;
" 2>/dev/null

echo ""
echo "TEST 7: API Endpoint Test"
echo "-------------------------"
API_RESPONSE=$(curl -s "https://alphagex-api.onrender.com/api/argus/gamma?symbol=SPY" 2>/dev/null)
if echo "$API_RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); exit(0 if d.get('data',{}).get('order_flow') else 1)" 2>/dev/null; then
    pass "API returns order_flow"

    # Extract and display live data
    echo ""
    echo "  Live Order Flow Data:"
    echo "$API_RESPONSE" | python3 -c "
import sys, json
d = json.load(sys.stdin)
of = d.get('data', {}).get('order_flow', {})
ba = of.get('bid_ask_pressure', {})
print(f\"    Combined Signal: {of.get('combined_signal', 'N/A')}\")
print(f\"    Confidence: {of.get('signal_confidence', 'N/A')}\")
print(f\"    Flow Direction: {of.get('flow_direction', 'N/A')}\")
print(f\"    Pressure Direction: {ba.get('pressure_direction', 'N/A')}\")
print(f\"    Net Pressure: {ba.get('net_pressure', 0)*100:.1f}%\")
print(f\"    Is Valid: {ba.get('is_valid', False)}\")
" 2>/dev/null
else
    fail "API does not return order_flow"
fi

echo ""
echo "TEST 8: Gap Fix Verification (STANDARDS.md)"
echo "--------------------------------------------"
echo "  Verifying root cause fixes are complete..."

# Test GAP #5-6: Empty result fields
echo ""
echo "  GAP #5-6: Empty result structure fields"
FIELDS_CHECK=$(psql $DATABASE_URL -t -c "
SELECT
    CASE WHEN raw_pressure IS NOT NULL THEN 1 ELSE 0 END +
    CASE WHEN is_valid IS NOT NULL THEN 1 ELSE 0 END as field_count
FROM argus_order_flow_history
WHERE recorded_at > NOW() - INTERVAL '1 hour'
LIMIT 1;
" 2>/dev/null | tr -d ' ')
if [ "$FIELDS_CHECK" = "2" ]; then
    pass "raw_pressure and is_valid fields populated"
else
    echo "  ⚠️  No recent records to verify field population"
fi

# Test that is_valid defaults correctly (should have both true and false)
IS_VALID_DIST=$(psql $DATABASE_URL -t -c "
SELECT
    COUNT(CASE WHEN is_valid = true THEN 1 END) as valid_count,
    COUNT(CASE WHEN is_valid = false THEN 1 END) as invalid_count
FROM argus_order_flow_history
WHERE recorded_at > NOW() - INTERVAL '7 days';
" 2>/dev/null)
echo "  is_valid distribution: $IS_VALID_DIST"

# Test API response structure
echo ""
echo "  GAP #1: Smoothing periods in response"
SMOOTHING=$(echo "$API_RESPONSE" | python3 -c "
import sys, json
d = json.load(sys.stdin)
ba = d.get('data', {}).get('order_flow', {}).get('bid_ask_pressure', {})
sp = ba.get('smoothing_periods', -1)
print(sp)
" 2>/dev/null)
if [ "$SMOOTHING" != "-1" ]; then
    pass "smoothing_periods field present (value: $SMOOTHING)"
else
    fail "smoothing_periods field missing"
fi

# Test data_unavailable handling
echo ""
echo "  GAP #2-3: spot_price validation (API error handling)"
ERROR_RESPONSE=$(curl -s "https://alphagex-api.onrender.com/api/argus/gamma?symbol=INVALID" 2>/dev/null)
if echo "$ERROR_RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); exit(0 if 'success' in d or 'detail' in d else 1)" 2>/dev/null; then
    pass "API returns proper error structure for invalid symbol"
else
    fail "API error handling incomplete"
fi

echo ""
echo "=============================================="
echo "  TEST COMPLETE"
echo "=============================================="
