#!/usr/bin/env bash
# Test 2: /api/watchtower/intraday-bars — fallback param, session_date, bar format
# Run: bash scripts/tests/test_chart_02_intraday_bars.sh [BASE_URL]

set -euo pipefail

BASE="${1:-http://localhost:8000}"
PASS=0
FAIL=0

echo "=== Test 2: Intraday Bars Endpoint ==="
echo "Base URL: $BASE"
echo ""

# 2a) Default call (no fallback) — should return today's bars (may be empty after hours)
echo "[2a] GET /api/watchtower/intraday-bars?symbol=SPY&interval=5min"
RESP=$(curl -sf "$BASE/api/watchtower/intraday-bars?symbol=SPY&interval=5min" 2>&1) || {
  echo "  FAIL: curl error"
  FAIL=$((FAIL+1))
  RESP=""
}

if [ -n "$RESP" ]; then
  SUCCESS=$(echo "$RESP" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('success', False))" 2>/dev/null || echo "PARSE_ERROR")
  BAR_COUNT=$(echo "$RESP" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('data',{}).get('count',0))" 2>/dev/null || echo "0")
  SESSION_DATE=$(echo "$RESP" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('data',{}).get('session_date','MISSING'))" 2>/dev/null || echo "MISSING")

  if [ "$SUCCESS" = "True" ]; then
    echo "  PASS: success=True"
    PASS=$((PASS+1))
  else
    echo "  FAIL: success=$SUCCESS"
    FAIL=$((FAIL+1))
  fi

  echo "  INFO: bar_count=$BAR_COUNT (no fallback — may be 0 after hours)"

  if [ "$SESSION_DATE" != "MISSING" ] && [ "$SESSION_DATE" != "None" ]; then
    echo "  PASS: session_date=$SESSION_DATE present"
    PASS=$((PASS+1))
  else
    echo "  FAIL: session_date missing from response"
    FAIL=$((FAIL+1))
  fi
fi

# 2b) With fallback=true — should always return bars (walks back to last session)
echo ""
echo "[2b] GET /api/watchtower/intraday-bars?symbol=SPY&interval=5min&fallback=true"
RESP=$(curl -sf "$BASE/api/watchtower/intraday-bars?symbol=SPY&interval=5min&fallback=true" 2>&1) || {
  echo "  FAIL: curl error"
  FAIL=$((FAIL+1))
  RESP=""
}

if [ -n "$RESP" ]; then
  BAR_COUNT=$(echo "$RESP" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('data',{}).get('count',0))" 2>/dev/null || echo "0")
  SESSION_DATE=$(echo "$RESP" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('data',{}).get('session_date','MISSING'))" 2>/dev/null || echo "MISSING")

  if [ "$BAR_COUNT" -gt 0 ] 2>/dev/null; then
    echo "  PASS: bar_count=$BAR_COUNT (>0 with fallback)"
    PASS=$((PASS+1))
  else
    echo "  FAIL: bar_count=$BAR_COUNT (expected >0 with fallback=true)"
    FAIL=$((FAIL+1))
  fi

  if [ "$SESSION_DATE" != "MISSING" ] && [ "$SESSION_DATE" != "None" ]; then
    echo "  PASS: session_date=$SESSION_DATE"
    PASS=$((PASS+1))
  else
    echo "  FAIL: session_date missing"
    FAIL=$((FAIL+1))
  fi

  # Validate bar OHLCV shape
  BAR_SHAPE=$(echo "$RESP" | python3 -c "
import json,sys
d=json.load(sys.stdin)
bars = d.get('data',{}).get('bars',[])
if bars:
    b = bars[0]
    keys = ['time','open','high','low','close','volume']
    present = [k for k in keys if k in b]
    print(f'{len(present)}/{len(keys)} keys: {present}')
else:
    print('NO_BARS')
" 2>/dev/null || echo "PARSE_ERROR")
  echo "  INFO: bar shape — $BAR_SHAPE"

  if echo "$BAR_SHAPE" | grep -q "6/6"; then
    echo "  PASS: all OHLCV+time keys present"
    PASS=$((PASS+1))
  elif [ "$BAR_SHAPE" != "NO_BARS" ]; then
    echo "  FAIL: missing keys in bar — $BAR_SHAPE"
    FAIL=$((FAIL+1))
  fi
fi

echo ""
echo "=== RESULTS: $PASS passed, $FAIL failed ==="
exit $FAIL
