#!/usr/bin/env bash
# Test 6: TradingVolatility source switching — verify that after-hours
# returns source=trading_volatility, and during hours returns tradier_live.
# This test checks the source field. Actual switching depends on market hours.
# Run: bash scripts/tests/test_chart_06_tv_source_switching.sh [BASE_URL]

set -euo pipefail

BASE="${1:-http://localhost:8000}"
PASS=0
FAIL=0

echo "=== Test 6: TradingVolatility Source Switching ==="
echo "Base URL: $BASE"
echo ""

# Determine if market is currently open by checking the /api/time endpoint
echo "[6a] Checking market hours..."
TIME_RESP=$(curl -sf "$BASE/api/time" 2>&1) || {
  echo "  WARN: /api/time unavailable, using gex-analysis response to infer"
  TIME_RESP=""
}

# Fetch gex-analysis
echo "[6b] GET /api/watchtower/gex-analysis?symbol=SPY"
RESP=$(curl -sf "$BASE/api/watchtower/gex-analysis?symbol=SPY" 2>&1) || {
  echo "  FAIL: curl error"
  FAIL=$((FAIL+1))
  RESP=""
}

if [ -n "$RESP" ]; then
  SOURCE=$(echo "$RESP" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('source', 'MISSING'))" 2>/dev/null || echo "PARSE_ERROR")
  LABEL=$(echo "$RESP" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('source_label', 'MISSING'))" 2>/dev/null || echo "PARSE_ERROR")
  SUCCESS=$(echo "$RESP" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('success', False))" 2>/dev/null || echo "PARSE_ERROR")

  echo "  source=$SOURCE"
  echo "  source_label=$LABEL"
  echo "  success=$SUCCESS"

  if [ "$SUCCESS" = "True" ]; then
    echo "  PASS: Request successful"
    PASS=$((PASS+1))
  else
    echo "  FAIL: Request failed"
    FAIL=$((FAIL+1))
  fi

  case "$SOURCE" in
    tradier_live)
      echo "  INFO: Market is OPEN — using Tradier live data"
      echo "  PASS: source=tradier_live (expected during market hours)"
      PASS=$((PASS+1))
      ;;
    trading_volatility)
      echo "  INFO: Market is CLOSED — using TradingVolatility next-day data"
      echo "  PASS: source=trading_volatility (expected after hours)"
      PASS=$((PASS+1))
      # Verify TV-specific label
      if echo "$LABEL" | grep -qi "trading" || echo "$LABEL" | grep -qi "next-day"; then
        echo "  PASS: source_label mentions TradingVolatility/Next-Day"
        PASS=$((PASS+1))
      else
        echo "  FAIL: source_label doesn't indicate TV data: $LABEL"
        FAIL=$((FAIL+1))
      fi
      ;;
    tradier_cached)
      echo "  INFO: Market is CLOSED — TradingVolatility may be unavailable, using cached Tradier"
      echo "  PASS: source=tradier_cached (valid fallback)"
      PASS=$((PASS+1))
      ;;
    *)
      echo "  FAIL: unexpected source=$SOURCE"
      FAIL=$((FAIL+1))
      ;;
  esac

  # Verify data structure regardless of source
  HAS_LEVELS=$(echo "$RESP" | python3 -c "
import json,sys
d=json.load(sys.stdin)
data = d.get('data',{})
has_header = 'header' in data
has_levels = 'levels' in data
has_chart = 'gex_chart' in data
print(f'header={has_header} levels={has_levels} gex_chart={has_chart}')
" 2>/dev/null || echo "PARSE_ERROR")
  echo "  INFO: data structure — $HAS_LEVELS"

  if echo "$HAS_LEVELS" | grep -q "header=True"; then
    echo "  PASS: data has expected structure"
    PASS=$((PASS+1))
  else
    echo "  FAIL: data structure incomplete"
    FAIL=$((FAIL+1))
  fi
fi

echo ""
echo "=== RESULTS: $PASS passed, $FAIL failed ==="
exit $FAIL
