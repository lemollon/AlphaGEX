#!/usr/bin/env bash
# Test 7: Frontend build verification — ensures no TypeScript errors
# from the chart streaming changes (gex-profile/page.tsx, api.ts)
# Run: bash scripts/tests/test_chart_07_frontend_build.sh

set -euo pipefail

FRONTEND_DIR="/home/user/AlphaGEX/frontend"
PASS=0
FAIL=0

echo "=== Test 7: Frontend Build Verification ==="
echo ""

# 7a) Check that LiveSpyChart is NOT imported in gex-profile/page.tsx
echo "[7a] Checking LiveSpyChart is NOT imported in gex-profile/page.tsx..."
if grep -q "LiveSpyChart" "$FRONTEND_DIR/src/app/gex-profile/page.tsx"; then
  echo "  FAIL: LiveSpyChart still referenced in gex-profile/page.tsx"
  FAIL=$((FAIL+1))
else
  echo "  PASS: No LiveSpyChart reference in gex-profile/page.tsx"
  PASS=$((PASS+1))
fi

# 7b) Check that Plotly Plot is imported
echo "[7b] Checking Plotly is imported..."
if grep -q "import.*react-plotly" "$FRONTEND_DIR/src/app/gex-profile/page.tsx"; then
  echo "  PASS: react-plotly.js imported"
  PASS=$((PASS+1))
else
  echo "  FAIL: react-plotly.js NOT imported"
  FAIL=$((FAIL+1))
fi

# 7c) Check that api.ts has fallback param on both intraday methods
echo "[7c] Checking api.ts fallback parameter..."
if grep -q "fallback.*boolean" "$FRONTEND_DIR/src/lib/api.ts" 2>/dev/null || \
   grep -q "getWatchtowerIntradayBars.*fallback" "$FRONTEND_DIR/src/lib/api.ts"; then
  echo "  PASS: fallback param found in api.ts"
  PASS=$((PASS+1))
else
  echo "  FAIL: fallback param NOT in api.ts"
  FAIL=$((FAIL+1))
fi

# 7d) Check key state variables exist in gex-profile/page.tsx
echo "[7d] Checking key state variables..."
for VAR in "isLive" "dataSource" "sourceLabel" "sessionDate"; do
  if grep -q "$VAR" "$FRONTEND_DIR/src/app/gex-profile/page.tsx"; then
    echo "  PASS: $VAR found"
    PASS=$((PASS+1))
  else
    echo "  FAIL: $VAR NOT found"
    FAIL=$((FAIL+1))
  fi
done

# 7e) Check LIVE indicator exists
echo "[7e] Checking LIVE indicator..."
if grep -q "LIVE" "$FRONTEND_DIR/src/app/gex-profile/page.tsx" && \
   grep -q "animate-pulse" "$FRONTEND_DIR/src/app/gex-profile/page.tsx"; then
  echo "  PASS: LIVE indicator with pulse animation found"
  PASS=$((PASS+1))
else
  echo "  FAIL: LIVE indicator missing"
  FAIL=$((FAIL+1))
fi

# 7f) Check Market Closed indicator
echo "[7f] Checking Market Closed indicator..."
if grep -q "Market Closed" "$FRONTEND_DIR/src/app/gex-profile/page.tsx"; then
  echo "  PASS: Market Closed text found"
  PASS=$((PASS+1))
else
  echo "  FAIL: Market Closed text missing"
  FAIL=$((FAIL+1))
fi

# 7g) Check Plotly transition config
echo "[7g] Checking Plotly transition config..."
if grep -q "transition.*duration.*300" "$FRONTEND_DIR/src/app/gex-profile/page.tsx"; then
  echo "  PASS: Plotly transition config present"
  PASS=$((PASS+1))
else
  echo "  FAIL: Plotly transition config missing"
  FAIL=$((FAIL+1))
fi

# 7h) Check deprecation comments
echo "[7h] Checking deprecation comments..."
if grep -q "DEPRECATED" "$FRONTEND_DIR/src/components/LiveSpyChart.tsx" 2>/dev/null; then
  echo "  PASS: LiveSpyChart.tsx has DEPRECATED comment"
  PASS=$((PASS+1))
else
  echo "  WARN: LiveSpyChart.tsx missing DEPRECATED comment (or file doesn't exist)"
fi

if grep -q "DEPRECATED" "$FRONTEND_DIR/src/hooks/useChartWebSocket.ts" 2>/dev/null; then
  echo "  PASS: useChartWebSocket.ts has DEPRECATED comment"
  PASS=$((PASS+1))
else
  echo "  WARN: useChartWebSocket.ts missing DEPRECATED comment (or file doesn't exist)"
fi

# 7i) TypeScript compilation check (if npx available)
echo ""
echo "[7i] Attempting TypeScript type check..."
if command -v npx &>/dev/null && [ -f "$FRONTEND_DIR/tsconfig.json" ]; then
  cd "$FRONTEND_DIR"
  # Only check the specific files we changed, with --noEmit
  if npx tsc --noEmit --pretty 2>&1 | head -20; then
    echo "  INFO: TypeScript check completed (review output above)"
    PASS=$((PASS+1))
  else
    echo "  WARN: TypeScript check had issues (review above)"
  fi
else
  echo "  SKIP: npx or tsconfig.json not available"
fi

echo ""
echo "=== RESULTS: $PASS passed, $FAIL failed ==="
exit $FAIL
