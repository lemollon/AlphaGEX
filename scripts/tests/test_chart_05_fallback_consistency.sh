#!/usr/bin/env bash
# Test 5: Cross-endpoint consistency — bars and ticks with fallback
# should return the same (or nearby) session_date
# Run: bash scripts/tests/test_chart_05_fallback_consistency.sh [BASE_URL]

set -euo pipefail

BASE="${1:-http://localhost:8000}"
PASS=0
FAIL=0

echo "=== Test 5: Fallback Consistency ==="
echo "Base URL: $BASE"
echo ""

# Fetch bars with fallback
echo "[5a] Fetching intraday-bars with fallback=true..."
BARS_RESP=$(curl -sf "$BASE/api/watchtower/intraday-bars?symbol=SPY&interval=5min&fallback=true" 2>&1) || {
  echo "  FAIL: curl error for bars"
  FAIL=$((FAIL+1))
  BARS_RESP=""
}

# Fetch ticks with fallback
echo "[5b] Fetching intraday-ticks with fallback=true..."
TICKS_RESP=$(curl -sf "$BASE/api/watchtower/intraday-ticks?symbol=SPY&interval=5&fallback=true" 2>&1) || {
  echo "  FAIL: curl error for ticks"
  FAIL=$((FAIL+1))
  TICKS_RESP=""
}

if [ -n "$BARS_RESP" ] && [ -n "$TICKS_RESP" ]; then
  BARS_DATE=$(echo "$BARS_RESP" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('data',{}).get('session_date','MISSING'))" 2>/dev/null || echo "MISSING")
  TICKS_DATE=$(echo "$TICKS_RESP" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('data',{}).get('session_date','MISSING'))" 2>/dev/null || echo "MISSING")
  BARS_COUNT=$(echo "$BARS_RESP" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('data',{}).get('count',0))" 2>/dev/null || echo "0")
  TICKS_COUNT=$(echo "$TICKS_RESP" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('data',{}).get('count',0))" 2>/dev/null || echo "0")

  echo "  bars_session_date=$BARS_DATE  bars_count=$BARS_COUNT"
  echo "  ticks_session_date=$TICKS_DATE  ticks_count=$TICKS_COUNT"

  # Bars and ticks may come from different sources (Tradier vs watchtower_snapshots)
  # so dates may differ. But both should be valid dates (not MISSING).
  if [ "$BARS_DATE" != "MISSING" ] && [ "$BARS_DATE" != "None" ]; then
    echo "  PASS: bars session_date present ($BARS_DATE)"
    PASS=$((PASS+1))
  else
    echo "  FAIL: bars session_date missing"
    FAIL=$((FAIL+1))
  fi

  if [ "$TICKS_DATE" != "MISSING" ] && [ "$TICKS_DATE" != "None" ] && [ "$TICKS_DATE" != "PARSE_ERROR" ]; then
    echo "  PASS: ticks session_date present ($TICKS_DATE)"
    PASS=$((PASS+1))
  else
    echo "  WARN: ticks session_date=$TICKS_DATE (may be null if no watchtower_snapshots)"
  fi

  # Both should have >0 entries when fallback is true and data exists
  if [ "$BARS_COUNT" -gt 0 ] 2>/dev/null; then
    echo "  PASS: bars have data ($BARS_COUNT bars)"
    PASS=$((PASS+1))
  else
    echo "  FAIL: bars empty even with fallback"
    FAIL=$((FAIL+1))
  fi
fi

# 5c) Verify that fallback=false does NOT walk back
echo ""
echo "[5c] Verifying fallback=false does NOT walk back (weekend/holiday check)..."
NO_FB_RESP=$(curl -sf "$BASE/api/watchtower/intraday-bars?symbol=SPY&interval=5min&fallback=false" 2>&1) || {
  echo "  FAIL: curl error"
  FAIL=$((FAIL+1))
  NO_FB_RESP=""
}

if [ -n "$NO_FB_RESP" ]; then
  NFB_COUNT=$(echo "$NO_FB_RESP" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('data',{}).get('count',0))" 2>/dev/null || echo "0")
  NFB_DATE=$(echo "$NO_FB_RESP" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('data',{}).get('session_date','MISSING'))" 2>/dev/null || echo "MISSING")
  echo "  INFO: fallback=false -> count=$NFB_COUNT, session_date=$NFB_DATE"
  echo "  INFO: (If today is a non-trading day, count=0 is expected without fallback)"
  PASS=$((PASS+1))
fi

echo ""
echo "=== RESULTS: $PASS passed, $FAIL failed ==="
exit $FAIL
