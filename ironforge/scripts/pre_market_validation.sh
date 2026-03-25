#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
# IronForge Pre-Market Validation — API & Sandbox Tests
# ═══════════════════════════════════════════════════════════════════════════
#
# Run from any machine with:
#   - IRONFORGE_API_URL (or pass URL as $1; default: ironforge-899p.onrender.com)
#   - TRADIER_SANDBOX_KEY_USER (for sandbox tests)
#   - DATABRICKS_SERVER_HOSTNAME, DATABRICKS_WAREHOUSE_ID, DATABRICKS_TOKEN (for DB comparison)
#
# Usage: bash ironforge/scripts/pre_market_validation.sh [URL]
#
# ALL TESTS ARE READ-ONLY. No positions opened, no data modified.
# ═══════════════════════════════════════════════════════════════════════════

set -uo pipefail

# Auto-detect base URL
# Render shell is a separate container — no PORT, no localhost access.
RENDER_DEFAULT="https://ironforge-899p.onrender.com"
if [ -n "${IRONFORGE_API_URL:-}" ]; then
  BASE="$IRONFORGE_API_URL"
elif [ -n "${RENDER_EXTERNAL_URL:-}" ]; then
  BASE="$RENDER_EXTERNAL_URL"
elif [ -n "${1:-}" ]; then
  BASE="$1"
else
  BASE="$RENDER_DEFAULT"
fi
BASE="${BASE%/}"
API="$BASE/api"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

pass() { echo -e "${GREEN}  PASS${NC}: $1"; }
fail() { echo -e "${RED}  FAIL${NC}: $1"; }
warn() { echo -e "${YELLOW}  WARN${NC}: $1"; }
info() { echo "  INFO: $1"; }

echo "═══════════════════════════════════════════════════════════"
echo "  IronForge Pre-Market Validation"
echo "  Render: $BASE"
echo "  Time: $(date)"
echo "═══════════════════════════════════════════════════════════"
echo ""

# ── TEST 3: API Response vs Expected Structure ──────────────────────────

echo "━━━ TEST 3: API Status Endpoints ━━━"
echo ""

for BOT in spark flame inferno; do
  echo "  --- ${BOT^^} ---"
  RESP=$(curl -s --max-time 15 "$API/$BOT/status" 2>/dev/null)
  HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 15 "$API/$BOT/status" 2>/dev/null)

  if [ "$HTTP_CODE" != "200" ]; then
    fail "${BOT^^} status returned HTTP $HTTP_CODE"
    continue
  fi

  # Extract fields
  BALANCE=$(echo "$RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('account',{}).get('balance','MISSING'))" 2>/dev/null)
  CUM_PNL=$(echo "$RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('account',{}).get('cumulative_pnl','MISSING'))" 2>/dev/null)
  UNREAL=$(echo "$RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('account',{}).get('unrealized_pnl','MISSING'))" 2>/dev/null)
  COLL=$(echo "$RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('account',{}).get('collateral_in_use','MISSING'))" 2>/dev/null)
  BP=$(echo "$RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('account',{}).get('buying_power','MISSING'))" 2>/dev/null)
  TRADES=$(echo "$RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('account',{}).get('total_trades','MISSING'))" 2>/dev/null)
  OPEN=$(echo "$RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('open_positions','MISSING'))" 2>/dev/null)
  START_CAP=$(echo "$RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('account',{}).get('starting_capital','MISSING'))" 2>/dev/null)

  echo "    balance:          $BALANCE"
  echo "    cumulative_pnl:   $CUM_PNL"
  echo "    unrealized_pnl:   $UNREAL"
  echo "    collateral:       $COLL"
  echo "    buying_power:     $BP"
  echo "    total_trades:     $TRADES"
  echo "    open_positions:   $OPEN"
  echo "    starting_capital: $START_CAP"

  # Validation checks
  if [ "$BALANCE" = "MISSING" ] || [ "$BALANCE" = "None" ]; then
    fail "balance is $BALANCE"
  else
    pass "balance present: $BALANCE"
  fi

  # Balance should = starting_capital + cumulative_pnl
  python3 -c "
bal = float('$BALANCE') if '$BALANCE' not in ('MISSING','None') else None
cap = float('$START_CAP') if '$START_CAP' not in ('MISSING','None') else None
pnl = float('$CUM_PNL') if '$CUM_PNL' not in ('MISSING','None') else None
if bal is not None and cap is not None and pnl is not None:
    expected = cap + pnl
    drift = abs(bal - expected)
    if drift < 0.02:
        print(f'  PASS: balance integrity (bal={bal:.2f} = cap({cap:.0f})+pnl({pnl:.2f})={expected:.2f})')
    else:
        print(f'  FAIL: balance integrity DRIFT \${drift:.2f} (bal={bal:.2f} != cap({cap:.0f})+pnl({pnl:.2f})={expected:.2f})')
else:
    print('  WARN: Could not verify balance integrity (missing values)')
" 2>/dev/null

  # Collateral should be 0 on weekend (no open positions)
  if [ "$OPEN" = "0" ] && [ "$COLL" != "0" ] && [ "$COLL" != "0.0" ]; then
    warn "collateral=$COLL but open_positions=0 (potential drift)"
  fi

  echo ""
done

# ── TEST 5: Sandbox Account Health ──────────────────────────────────────

echo "━━━ TEST 5: Tradier Sandbox Health ━━━"
echo ""

SANDBOX_KEY="${TRADIER_SANDBOX_KEY_USER:-}"
if [ -z "$SANDBOX_KEY" ]; then
  warn "TRADIER_SANDBOX_KEY_USER not set — skipping sandbox tests"
else
  # Get profile
  PROFILE=$(curl -s --max-time 10 \
    -H "Authorization: Bearer $SANDBOX_KEY" \
    "https://sandbox.tradier.com/v1/user/profile" 2>/dev/null)

  if [ -z "$PROFILE" ] || echo "$PROFILE" | grep -q '"fault"'; then
    fail "Sandbox profile fetch failed (bad API key?)"
  else
    ACCT_IDS=$(echo "$PROFILE" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    accts = d.get('profile',{}).get('account',[])
    if isinstance(accts, dict): accts = [accts]
    for a in accts:
        print(a.get('account_number',''))
except: pass
" 2>/dev/null)

    for ACCT_ID in $ACCT_IDS; do
      [ -z "$ACCT_ID" ] && continue
      echo "  --- Account: $ACCT_ID ---"

      # Balance
      BAL_RESP=$(curl -s --max-time 10 \
        -H "Authorization: Bearer $SANDBOX_KEY" \
        "https://sandbox.tradier.com/v1/accounts/$ACCT_ID/balances" 2>/dev/null)
      OPT_BP=$(echo "$BAL_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('balances',{}).get('option_buying_power','N/A'))" 2>/dev/null)
      EQUITY=$(echo "$BAL_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('balances',{}).get('total_equity','N/A'))" 2>/dev/null)
      echo "    option_buying_power: $OPT_BP"
      echo "    total_equity: $EQUITY"

      # Check for negative BP
      python3 -c "
bp = float('$OPT_BP') if '$OPT_BP' not in ('N/A','None','') else None
if bp is not None:
    if bp < 0:
        print(f'  FAIL: NEGATIVE buying power \${bp:.2f} — sandbox needs reset!')
    elif bp < 1000:
        print(f'  WARN: Low buying power \${bp:.2f}')
    else:
        print(f'  PASS: Buying power OK \${bp:.2f}')
else:
    print('  WARN: Could not read buying power')
" 2>/dev/null

      # Open positions
      POS_RESP=$(curl -s --max-time 10 \
        -H "Authorization: Bearer $SANDBOX_KEY" \
        "https://sandbox.tradier.com/v1/accounts/$ACCT_ID/positions" 2>/dev/null)
      POS_COUNT=$(echo "$POS_RESP" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    positions = d.get('positions',{})
    if positions == 'null' or not positions:
        print(0)
    else:
        p = positions.get('position',[])
        if isinstance(p, dict): p = [p]
        print(len(p))
except:
    print('ERROR')
" 2>/dev/null)
      echo "    open_positions: $POS_COUNT"

      if [ "$POS_COUNT" != "0" ] && [ "$POS_COUNT" != "ERROR" ]; then
        warn "$POS_COUNT stale positions in sandbox account $ACCT_ID"
        echo "    ACTION NEEDED: Run Kill Switch or manually close at developer.tradier.com"
      elif [ "$POS_COUNT" = "0" ]; then
        pass "No stale positions"
      fi

      echo ""
    done
  fi
fi

# ── TEST 6: Kill Switch Diagnostic (GET only) ──────────────────────────

echo "━━━ TEST 6: Kill Switch Diagnostic (READ ONLY) ━━━"
echo ""

KS_RESP=$(curl -s --max-time 15 "$API/sandbox/emergency-close" 2>/dev/null)
KS_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 15 "$API/sandbox/emergency-close" 2>/dev/null)

if [ "$KS_CODE" = "200" ]; then
  pass "Kill switch endpoint responding (HTTP 200)"
  echo "$KS_RESP" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print('    Kill switch response:')
    print(json.dumps(d, indent=4)[:2000])
except:
    print('    (could not parse response)')
" 2>/dev/null
else
  fail "Kill switch returned HTTP $KS_CODE"
fi
echo ""

# ── TEST 7: Scanner Health Badge ────────────────────────────────────────

echo "━━━ TEST 7: Scanner Health Check ━━━"
echo ""

for BOT in spark flame inferno; do
  RESP=$(curl -s --max-time 15 "$API/$BOT/status" 2>/dev/null)
  LAST_SCAN=$(echo "$RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('last_scan','None'))" 2>/dev/null)
  BOT_STATE=$(echo "$RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('bot_state','None'))" 2>/dev/null)
  SCAN_COUNT=$(echo "$RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('scan_count','None'))" 2>/dev/null)

  echo "  ${BOT^^}:"
  echo "    last_scan: $LAST_SCAN"
  echo "    bot_state: $BOT_STATE"
  echo "    scan_count: $SCAN_COUNT"

  # Check if last scan is stale (>30 min old)
  python3 -c "
from datetime import datetime, timezone
scan = '$LAST_SCAN'
if scan and scan != 'None':
    try:
        scan_dt = datetime.fromisoformat(scan.replace('Z','+00:00'))
        age_min = (datetime.now(timezone.utc) - scan_dt).total_seconds() / 60
        if age_min > 120:
            print(f'    PASS: Scanner idle (last scan {age_min:.0f}m ago — expected on weekend)')
        elif age_min > 30:
            print(f'    WARN: Scanner may be stale ({age_min:.0f}m since last scan)')
        else:
            print(f'    INFO: Scanner recently active ({age_min:.0f}m ago)')
    except Exception as e:
        print(f'    WARN: Could not parse scan time ({e})')
else:
    print('    WARN: No last_scan timestamp available')
" 2>/dev/null
  echo ""
done

# ── TEST 9: Cache Busting Verification ──────────────────────────────────

echo "━━━ TEST 9: Databricks Cache Bust Verification ━━━"
echo ""

if [ -n "${DATABRICKS_SERVER_HOSTNAME:-}" ] && [ -n "${DATABRICKS_WAREHOUSE_ID:-}" ] && [ -n "${DATABRICKS_TOKEN:-}" ]; then
  # Run same query twice in rapid succession with different timestamps
  # If caching were broken, both would return the same response
  SQL="SELECT CURRENT_TIMESTAMP() as now_ts, 'cache_test' as label"
  TS1=$(date +%s%N)
  TS2=$((TS1 + 1))

  RESP1=$(curl -s --max-time 30 -X POST \
    "https://${DATABRICKS_SERVER_HOSTNAME}/api/2.0/sql/statements/" \
    -H "Authorization: Bearer ${DATABRICKS_TOKEN}" \
    -H "Content-Type: application/json" \
    -d "{\"warehouse_id\":\"${DATABRICKS_WAREHOUSE_ID}\",\"catalog\":\"alpha_prime\",\"schema\":\"ironforge\",\"statement\":\"${SQL} /* ts=${TS1} */\",\"wait_timeout\":\"30s\",\"disposition\":\"INLINE\",\"format\":\"JSON_ARRAY\"}" 2>/dev/null)

  RESP2=$(curl -s --max-time 30 -X POST \
    "https://${DATABRICKS_SERVER_HOSTNAME}/api/2.0/sql/statements/" \
    -H "Authorization: Bearer ${DATABRICKS_TOKEN}" \
    -H "Content-Type: application/json" \
    -d "{\"warehouse_id\":\"${DATABRICKS_WAREHOUSE_ID}\",\"catalog\":\"alpha_prime\",\"schema\":\"ironforge\",\"statement\":\"${SQL} /* ts=${TS2} */\",\"wait_timeout\":\"30s\",\"disposition\":\"INLINE\",\"format\":\"JSON_ARRAY\"}" 2>/dev/null)

  TIME1=$(echo "$RESP1" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('result',{}).get('data_array',[[]])[0][0])" 2>/dev/null)
  TIME2=$(echo "$RESP2" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('result',{}).get('data_array',[[]])[0][0])" 2>/dev/null)

  echo "  Query 1 timestamp: $TIME1"
  echo "  Query 2 timestamp: $TIME2"
  if [ "$TIME1" != "$TIME2" ] && [ -n "$TIME1" ] && [ -n "$TIME2" ]; then
    pass "Cache bust working — different timestamps returned"
  elif [ "$TIME1" = "$TIME2" ]; then
    fail "SAME timestamp returned — cache may not be busted!"
  else
    warn "Could not verify (query failed)"
  fi
else
  warn "Databricks credentials not set — skipping cache test"
  info "Set DATABRICKS_SERVER_HOSTNAME, DATABRICKS_WAREHOUSE_ID, DATABRICKS_TOKEN"
fi
echo ""

# ── TEST 10: API Response Headers (no-cache) ─────────────────────────

echo "━━━ TEST 10: API Cache Headers ━━━"
echo ""

for BOT in spark flame inferno; do
  HEADERS=$(curl -sI --max-time 15 "$API/$BOT/status" 2>/dev/null)
  CACHE=$(echo "$HEADERS" | grep -i "cache-control" | head -1 | tr -d '\r')
  RENDER_CACHE=$(echo "$HEADERS" | grep -i "x-render-cache\|x-vercel-cache" | head -1 | tr -d '\r')
  AGE=$(echo "$HEADERS" | grep -i "^age:" | head -1 | tr -d '\r')

  echo "  ${BOT^^}:"
  echo "    ${CACHE:-cache-control: (not set)}"
  echo "    ${RENDER_CACHE:-x-render-cache: (not set)}"
  echo "    ${AGE:-age: (not set)}"

  if echo "$CACHE" | grep -qi "no-store\|no-cache\|max-age=0"; then
    pass "Cache headers correct"
  elif [ -z "$CACHE" ]; then
    warn "No cache-control header — Render may cache responses"
  else
    warn "Unexpected cache-control: $CACHE"
  fi
  echo ""
done

# ── TEST 11: Null Display Test (B2) ──────────────────────────────────

echo "━━━ TEST 11: Null/Zero Handling (INV-12) ━━━"
echo ""

for BOT in spark flame inferno; do
  RESP=$(curl -s --max-time 15 "$API/$BOT/status" 2>/dev/null)
  echo "  ${BOT^^}:"
  python3 -c "
import sys, json
d = json.load(sys.stdin)
acct = d.get('account', {})
urpnl = acct.get('unrealized_pnl')
open_pos = d.get('open_positions', 0)

if open_pos == 0 and urpnl == 0:
    print('    PASS: unrealized_pnl=0 with 0 open positions (correct)')
elif open_pos == 0 and urpnl is None:
    print('    PASS: unrealized_pnl=null with 0 open positions (acceptable)')
elif open_pos > 0 and urpnl is None:
    print('    INFO: unrealized_pnl=null with open positions (Tradier not configured or market closed — frontend should show \"—\")')
elif open_pos > 0 and urpnl == 0:
    print('    WARN: unrealized_pnl=0 with open positions — is this real zero or masked error?')
else:
    print(f'    INFO: unrealized_pnl={urpnl} open_positions={open_pos}')

# Check no field is unexpectedly missing
for field in ['balance', 'cumulative_pnl', 'collateral_in_use', 'buying_power', 'total_trades']:
    val = acct.get(field)
    if val is None:
        print(f'    FAIL: {field} is null — should always have a value')
    elif val == 'MISSING':
        print(f'    FAIL: {field} is missing from response')
" <<< "$RESP" 2>/dev/null
  echo ""
done

echo "═══════════════════════════════════════════════════════════"
echo "  Validation Complete"
echo "═══════════════════════════════════════════════════════════"
echo ""
echo "NEXT STEPS:"
echo "  1. Run ironforge/databricks/pre_market_validation.py in Databricks"
echo "  2. Open each bot dashboard and compare values with Test 3 output"
echo "  3. If all pass → merge to main: git checkout main && git merge claude/setup-databricks-notebook-Y3OXC && git push origin main"
echo "  4. Fill in the confidence report with actual test results"
echo ""
