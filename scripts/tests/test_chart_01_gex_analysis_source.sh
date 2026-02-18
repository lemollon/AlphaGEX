#!/usr/bin/env bash
# Test 1: /api/watchtower/gex-analysis returns source + source_label fields
# Run: bash scripts/tests/test_chart_01_gex_analysis_source.sh [BASE_URL]

set -euo pipefail

BASE="${1:-http://localhost:8000}"
PASS=0
FAIL=0

echo "=== Test 1: GEX Analysis Source Fields ==="
echo "Base URL: $BASE"
echo ""

# 1a) Fetch gex-analysis for SPY (default)
echo "[1a] GET /api/watchtower/gex-analysis?symbol=SPY"
RESP=$(curl -sf "$BASE/api/watchtower/gex-analysis?symbol=SPY" 2>&1) || {
  echo "  FAIL: curl returned non-zero. Response: $RESP"
  FAIL=$((FAIL+1))
  RESP=""
}

if [ -n "$RESP" ]; then
  # Check success field
  SUCCESS=$(echo "$RESP" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('success', False))" 2>/dev/null || echo "PARSE_ERROR")
  if [ "$SUCCESS" = "True" ]; then
    echo "  PASS: success=True"
    PASS=$((PASS+1))
  else
    echo "  FAIL: success=$SUCCESS (expected True)"
    FAIL=$((FAIL+1))
  fi

  # Check source field exists and is one of expected values
  SOURCE=$(echo "$RESP" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('source', 'MISSING'))" 2>/dev/null || echo "PARSE_ERROR")
  case "$SOURCE" in
    tradier_live|tradier_cached|trading_volatility)
      echo "  PASS: source=$SOURCE (valid)"
      PASS=$((PASS+1))
      ;;
    MISSING)
      echo "  FAIL: 'source' field missing from response"
      FAIL=$((FAIL+1))
      ;;
    *)
      echo "  FAIL: source=$SOURCE (unexpected value)"
      FAIL=$((FAIL+1))
      ;;
  esac

  # Check source_label field exists
  LABEL=$(echo "$RESP" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('source_label', 'MISSING'))" 2>/dev/null || echo "PARSE_ERROR")
  if [ "$LABEL" != "MISSING" ] && [ "$LABEL" != "None" ] && [ "$LABEL" != "PARSE_ERROR" ]; then
    echo "  PASS: source_label=$LABEL"
    PASS=$((PASS+1))
  else
    echo "  FAIL: 'source_label' missing or null (got: $LABEL)"
    FAIL=$((FAIL+1))
  fi

  # Check data.header.price exists and > 0
  PRICE=$(echo "$RESP" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('data',{}).get('header',{}).get('price',0))" 2>/dev/null || echo "0")
  if python3 -c "exit(0 if float('$PRICE') > 0 else 1)" 2>/dev/null; then
    echo "  PASS: price=$PRICE (>0)"
    PASS=$((PASS+1))
  else
    echo "  FAIL: price=$PRICE (expected >0)"
    FAIL=$((FAIL+1))
  fi

  # Check data.levels exists with key fields
  HAS_LEVELS=$(echo "$RESP" | python3 -c "
import json,sys
d=json.load(sys.stdin)
levels = d.get('data',{}).get('levels',{})
keys = ['gex_flip','call_wall','put_wall','upper_1sd','lower_1sd']
present = [k for k in keys if k in levels]
print(f'{len(present)}/{len(keys)} level keys present: {present}')
" 2>/dev/null || echo "PARSE_ERROR")
  echo "  INFO: levels — $HAS_LEVELS"

  # Check data.gex_chart.strikes has entries
  STRIKES_COUNT=$(echo "$RESP" | python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d.get('data',{}).get('gex_chart',{}).get('strikes',[])))" 2>/dev/null || echo "0")
  if [ "$STRIKES_COUNT" -gt 0 ] 2>/dev/null; then
    echo "  PASS: strikes count=$STRIKES_COUNT"
    PASS=$((PASS+1))
  else
    echo "  WARN: strikes count=$STRIKES_COUNT (may be 0 if no data)"
  fi
fi

echo ""
echo "=== RESULTS: $PASS passed, $FAIL failed ==="
exit $FAIL
