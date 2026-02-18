#!/usr/bin/env bash
# Test 3: /api/watchtower/intraday-ticks — fallback param, session_date, tick format
# Run: bash scripts/tests/test_chart_03_intraday_ticks.sh [BASE_URL]

set -euo pipefail

BASE="${1:-http://localhost:8000}"
PASS=0
FAIL=0

echo "=== Test 3: Intraday Ticks Endpoint ==="
echo "Base URL: $BASE"
echo ""

# 3a) Default call (no fallback)
echo "[3a] GET /api/watchtower/intraday-ticks?symbol=SPY&interval=5"
RESP=$(curl -sf "$BASE/api/watchtower/intraday-ticks?symbol=SPY&interval=5" 2>&1) || {
  echo "  FAIL: curl error"
  FAIL=$((FAIL+1))
  RESP=""
}

if [ -n "$RESP" ]; then
  SUCCESS=$(echo "$RESP" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('success', False))" 2>/dev/null || echo "PARSE_ERROR")
  TICK_COUNT=$(echo "$RESP" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('data',{}).get('count',0))" 2>/dev/null || echo "0")
  SESSION_DATE=$(echo "$RESP" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('data',{}).get('session_date','MISSING'))" 2>/dev/null || echo "MISSING")

  if [ "$SUCCESS" = "True" ]; then
    echo "  PASS: success=True"
    PASS=$((PASS+1))
  else
    echo "  FAIL: success=$SUCCESS"
    FAIL=$((FAIL+1))
  fi

  echo "  INFO: tick_count=$TICK_COUNT (no fallback — may be 0 after hours)"

  if [ "$SESSION_DATE" != "MISSING" ] && [ "$SESSION_DATE" != "PARSE_ERROR" ]; then
    echo "  PASS: session_date=$SESSION_DATE present"
    PASS=$((PASS+1))
  else
    echo "  FAIL: session_date missing from response"
    FAIL=$((FAIL+1))
  fi
fi

# 3b) With fallback=true — should return ticks from most recent session
echo ""
echo "[3b] GET /api/watchtower/intraday-ticks?symbol=SPY&interval=5&fallback=true"
RESP=$(curl -sf "$BASE/api/watchtower/intraday-ticks?symbol=SPY&interval=5&fallback=true" 2>&1) || {
  echo "  FAIL: curl error"
  FAIL=$((FAIL+1))
  RESP=""
}

if [ -n "$RESP" ]; then
  TICK_COUNT=$(echo "$RESP" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('data',{}).get('count',0))" 2>/dev/null || echo "0")
  SESSION_DATE=$(echo "$RESP" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('data',{}).get('session_date','MISSING'))" 2>/dev/null || echo "MISSING")

  if [ "$TICK_COUNT" -gt 0 ] 2>/dev/null; then
    echo "  PASS: tick_count=$TICK_COUNT (>0 with fallback)"
    PASS=$((PASS+1))
  else
    echo "  WARN: tick_count=$TICK_COUNT (may be 0 if watchtower_snapshots empty)"
  fi

  if [ "$SESSION_DATE" != "MISSING" ] && [ "$SESSION_DATE" != "PARSE_ERROR" ]; then
    echo "  PASS: session_date=$SESSION_DATE"
    PASS=$((PASS+1))
  else
    echo "  FAIL: session_date missing"
    FAIL=$((FAIL+1))
  fi

  # Validate tick shape
  TICK_SHAPE=$(echo "$RESP" | python3 -c "
import json,sys
d=json.load(sys.stdin)
ticks = d.get('data',{}).get('ticks',[])
if ticks:
    t = ticks[0]
    keys = ['time','spot_price','net_gamma','vix','flip_point','call_wall','put_wall']
    present = [k for k in keys if k in t]
    print(f'{len(present)}/{len(keys)} keys: {present}')
else:
    print('NO_TICKS')
" 2>/dev/null || echo "PARSE_ERROR")
  echo "  INFO: tick shape — $TICK_SHAPE"
fi

echo ""
echo "=== RESULTS: $PASS passed, $FAIL failed ==="
exit $FAIL
