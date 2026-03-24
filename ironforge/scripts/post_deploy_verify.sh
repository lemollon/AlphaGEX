#!/usr/bin/env bash
# Post-deploy verification for FLAME production trading
# Run immediately after deploying to Render/Vercel.
#
# Usage: bash ironforge/scripts/post_deploy_verify.sh [BASE_URL]
# Default: https://ironforge-pi.vercel.app

set -euo pipefail

BASE="${1:-https://ironforge-pi.vercel.app}"
PASS=0
FAIL=0
WARN=0

green() { printf "\033[32m%s\033[0m\n" "$*"; }
red()   { printf "\033[31m%s\033[0m\n" "$*"; }
yellow(){ printf "\033[33m%s\033[0m\n" "$*"; }
check() {
  local label="$1" ok="$2"
  if [ "$ok" = "true" ]; then
    green "  PASS  $label"; ((PASS++))
  else
    red   "  FAIL  $label"; ((FAIL++))
  fi
}
warn_check() {
  local label="$1" ok="$2"
  if [ "$ok" = "true" ]; then
    green "  PASS  $label"; ((PASS++))
  else
    yellow "  WARN  $label"; ((WARN++))
  fi
}

echo "================================================"
echo "  FLAME Post-Deploy Verification"
echo "  Target: $BASE"
echo "  Time:   $(date '+%Y-%m-%d %H:%M:%S %Z')"
echo "================================================"
echo ""

# ── 1. Health check ──────────────────────────────────────────────────
echo "1. Health Check"
HEALTH=$(curl -sf "$BASE/api/health" 2>/dev/null || echo '{}')
DB_OK=$(echo "$HEALTH" | python3 -c "import sys,json; d=json.load(sys.stdin); print('true' if d.get('database') == 'connected' else 'false')" 2>/dev/null || echo false)
TRADIER_OK=$(echo "$HEALTH" | python3 -c "import sys,json; d=json.load(sys.stdin); print('true' if d.get('tradier') == 'connected' else 'false')" 2>/dev/null || echo false)
check "Database connected" "$DB_OK"
check "Tradier connected" "$TRADIER_OK"
echo ""

# ── 2. Scanner status ────────────────────────────────────────────────
echo "2. Scanner Status"
SCANNER=$(curl -sf "$BASE/api/scanner/status" 2>/dev/null || echo '{}')
RUNNING=$(echo "$SCANNER" | python3 -c "import sys,json; d=json.load(sys.stdin); print('true' if d.get('running') else 'false')" 2>/dev/null || echo false)
warn_check "Scanner running" "$RUNNING"
echo ""

# ── 3. FLAME bot status ──────────────────────────────────────────────
echo "3. FLAME Bot Status"
STATUS=$(curl -sf "$BASE/api/flame/status" 2>/dev/null || echo '{}')
ENABLED=$(echo "$STATUS" | python3 -c "import sys,json; d=json.load(sys.stdin); print('true' if d.get('enabled') else 'false')" 2>/dev/null || echo false)
check "FLAME enabled" "$ENABLED"
echo ""

# ── 4. Diagnose production account ───────────────────────────────────
echo "4. Production Account Diagnostics"
DIAG=$(curl -sf "$BASE/api/flame/diagnose-production" 2>/dev/null || echo '{}')

PROD_LOADED=$(echo "$DIAG" | python3 -c "
import sys,json
d=json.load(sys.stdin)
accts = d.get('production_accounts', [])
print('true' if len(accts) > 0 else 'false')
" 2>/dev/null || echo false)
check "Production account loaded from DB" "$PROD_LOADED"

API_VALID=$(echo "$DIAG" | python3 -c "
import sys,json
d=json.load(sys.stdin)
accts = d.get('production_accounts', [])
if accts:
    print('true' if accts[0].get('api_key_valid') else 'false')
else:
    print('false')
" 2>/dev/null || echo false)
check "Production API key valid" "$API_VALID"

BP=$(echo "$DIAG" | python3 -c "
import sys,json
d=json.load(sys.stdin)
accts = d.get('production_accounts', [])
if accts:
    bp = accts[0].get('option_buying_power', 0) or 0
    print(f'{bp:.0f}')
else:
    print('0')
" 2>/dev/null || echo 0)
BP_OK="false"
if [ "$BP" -gt 500 ] 2>/dev/null; then BP_OK="true"; fi
check "Production BP >= \$500 (got \$$BP)" "$BP_OK"

CAP_PCT=$(echo "$DIAG" | python3 -c "
import sys,json
d=json.load(sys.stdin)
accts = d.get('production_accounts', [])
if accts:
    print(accts[0].get('capital_pct', 100))
else:
    print('unknown')
" 2>/dev/null || echo unknown)
echo "        capital_pct = ${CAP_PCT}%"

SIZING=$(echo "$DIAG" | python3 -c "
import sys,json
d=json.load(sys.stdin)
accts = d.get('production_accounts', [])
if accts:
    print(accts[0].get('estimated_contracts', '?'))
else:
    print('?')
" 2>/dev/null || echo ?)
echo "        Estimated contracts = $SIZING"
echo ""

# ── 5. Production paper account exists ───────────────────────────────
echo "5. Production Paper Account"
PROD_STATUS=$(curl -sf "$BASE/api/flame/status?account_type=production" 2>/dev/null || echo '{}')
PROD_BALANCE=$(echo "$PROD_STATUS" | python3 -c "
import sys,json
d=json.load(sys.stdin)
acct = d.get('paper_account', {})
print(acct.get('current_balance', 'missing'))
" 2>/dev/null || echo missing)
PAPER_OK="false"
if [ "$PROD_BALANCE" != "missing" ]; then PAPER_OK="true"; fi
check "Production paper_account exists (balance=\$$PROD_BALANCE)" "$PAPER_OK"
echo ""

# ── 6. No stale production positions ─────────────────────────────────
echo "6. Open Production Positions"
PROD_POS=$(curl -sf "$BASE/api/flame/positions?account_type=production" 2>/dev/null || echo '{}')
POS_COUNT=$(echo "$PROD_POS" | python3 -c "
import sys,json
d=json.load(sys.stdin)
positions = d.get('positions', d if isinstance(d, list) else [])
print(len([p for p in positions if p.get('status') == 'open']))
" 2>/dev/null || echo 0)
echo "        Open production positions: $POS_COUNT"
if [ "$POS_COUNT" = "0" ]; then
  green "  PASS  No stale production positions"
  ((PASS++))
else
  yellow "  WARN  $POS_COUNT open production position(s) — check if stale"
  ((WARN++))
fi
echo ""

# ── Summary ──────────────────────────────────────────────────────────
echo "================================================"
echo "  Results: $PASS passed, $FAIL failed, $WARN warnings"
echo "================================================"
if [ "$FAIL" -gt 0 ]; then
  red "  DEPLOY NOT READY — fix failures before market open"
  exit 1
elif [ "$WARN" -gt 0 ]; then
  yellow "  DEPLOY OK with warnings — review before market open"
  exit 0
else
  green "  ALL CLEAR — ready for production trading"
  exit 0
fi
