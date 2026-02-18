#!/usr/bin/env bash
# Test 4: /api/watchtower/session-data — session date walk-back, bar/tick format
# Run: bash scripts/tests/test_chart_04_session_data.sh [BASE_URL]

set -euo pipefail

BASE="${1:-http://localhost:8000}"
PASS=0
FAIL=0

echo "=== Test 4: Session Data Endpoint ==="
echo "Base URL: $BASE"
echo ""

# 4a) Default call (no date) — should return most recent session
echo "[4a] GET /api/watchtower/session-data?symbol=SPY"
RESP=$(curl -sf "$BASE/api/watchtower/session-data?symbol=SPY" 2>&1) || {
  echo "  FAIL: curl error"
  FAIL=$((FAIL+1))
  RESP=""
}

if [ -n "$RESP" ]; then
  SUCCESS=$(echo "$RESP" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('success', False))" 2>/dev/null || echo "PARSE_ERROR")
  if [ "$SUCCESS" = "True" ]; then
    echo "  PASS: success=True"
    PASS=$((PASS+1))
  else
    echo "  FAIL: success=$SUCCESS"
    FAIL=$((FAIL+1))
  fi

  # Check session_date
  SD=$(echo "$RESP" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('data',{}).get('session_date','MISSING'))" 2>/dev/null || echo "MISSING")
  echo "  INFO: session_date=$SD"

  # Check bars
  BAR_COUNT=$(echo "$RESP" | python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d.get('data',{}).get('bars',[])))" 2>/dev/null || echo "0")
  echo "  INFO: bars=$BAR_COUNT"

  # Check gex_ticks
  TICK_COUNT=$(echo "$RESP" | python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d.get('data',{}).get('gex_ticks',[])))" 2>/dev/null || echo "0")
  echo "  INFO: gex_ticks=$TICK_COUNT"

  # Check gex_levels
  HAS_LEVELS=$(echo "$RESP" | python3 -c "
import json,sys
d=json.load(sys.stdin)
levels = d.get('data',{}).get('gex_levels',{})
keys = ['flip_point','call_wall','put_wall']
present = [k for k in keys if k in levels]
print(f'{len(present)}/{len(keys)}')
" 2>/dev/null || echo "PARSE_ERROR")
  echo "  INFO: gex_levels keys — $HAS_LEVELS"

  # Check market_open field
  MARKET_OPEN=$(echo "$RESP" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('data',{}).get('market_open','MISSING'))" 2>/dev/null || echo "MISSING")
  if [ "$MARKET_OPEN" != "MISSING" ]; then
    echo "  PASS: market_open=$MARKET_OPEN present"
    PASS=$((PASS+1))
  else
    echo "  FAIL: market_open field missing"
    FAIL=$((FAIL+1))
  fi

  # Check available_dates
  DATES_COUNT=$(echo "$RESP" | python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d.get('data',{}).get('available_dates',[])))" 2>/dev/null || echo "0")
  echo "  INFO: available_dates=$DATES_COUNT"
fi

echo ""
echo "=== RESULTS: $PASS passed, $FAIL failed ==="
exit $FAIL
