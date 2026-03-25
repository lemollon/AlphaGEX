#!/usr/bin/env bash
# Post-deploy verification for FLAME production trading
# Run immediately after deploying to Render.
#
# Usage (from Render shell):  bash post_deploy_verify.sh
# Usage (from local):         bash post_deploy_verify.sh https://your-ironforge.onrender.com
#
# Auto-detects: IRONFORGE_API_URL env var → arg → Render external URL

set -euo pipefail

# Auto-detect base URL
# Render shell is a separate container — no PORT, no localhost access.
# Default to the external Render URL for the ironforge-dashboard service.
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

# Use node for JSON parsing (guaranteed on Render Node.js service)
jq_node() {
  node -e "const d=JSON.parse(require('fs').readFileSync('/dev/stdin','utf8')); $1"
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
DB_OK=$(echo "$HEALTH" | jq_node "console.log(d.database==='connected'?'true':'false')" 2>/dev/null || echo false)
TRADIER_OK=$(echo "$HEALTH" | jq_node "console.log(d.tradier==='connected'?'true':'false')" 2>/dev/null || echo false)
check "Database connected" "$DB_OK"
check "Tradier connected" "$TRADIER_OK"
echo ""

# ── 2. Scanner status ────────────────────────────────────────────────
echo "2. Scanner Status"
SCANNER=$(curl -sf "$BASE/api/scanner/status" 2>/dev/null || echo '{}')
RUNNING=$(echo "$SCANNER" | jq_node "console.log(d.running?'true':'false')" 2>/dev/null || echo false)
warn_check "Scanner running" "$RUNNING"
echo ""

# ── 3. FLAME bot status ──────────────────────────────────────────────
echo "3. FLAME Bot Status"
STATUS=$(curl -sf "$BASE/api/flame/status" 2>/dev/null || echo '{}')
ENABLED=$(echo "$STATUS" | jq_node "console.log(d.enabled?'true':'false')" 2>/dev/null || echo false)
check "FLAME enabled" "$ENABLED"
echo ""

# ── 4. Diagnose production account ───────────────────────────────────
echo "4. Production Account Diagnostics"
DIAG=$(curl -sf "$BASE/api/flame/diagnose-production" 2>/dev/null || echo '{}')

PROD_LOADED=$(echo "$DIAG" | jq_node "
  const a=d.production_accounts||[];
  console.log(a.length>0?'true':'false')
" 2>/dev/null || echo false)
check "Production account loaded from DB" "$PROD_LOADED"

API_VALID=$(echo "$DIAG" | jq_node "
  const a=d.production_accounts||[];
  console.log(a[0]&&a[0].api_key_valid?'true':'false')
" 2>/dev/null || echo false)
check "Production API key valid" "$API_VALID"

BP=$(echo "$DIAG" | jq_node "
  const a=d.production_accounts||[];
  console.log(a[0]?Math.round(a[0].option_buying_power||0):0)
" 2>/dev/null || echo 0)
BP_OK="false"
if [ "$BP" -gt 500 ] 2>/dev/null; then BP_OK="true"; fi
check "Production BP >= \$500 (got \$$BP)" "$BP_OK"

CAP_PCT=$(echo "$DIAG" | jq_node "
  const a=d.production_accounts||[];
  console.log(a[0]?a[0].capital_pct||100:'unknown')
" 2>/dev/null || echo unknown)
echo "        capital_pct = ${CAP_PCT}%"

SIZING=$(echo "$DIAG" | jq_node "
  const a=d.production_accounts||[];
  console.log(a[0]?a[0].estimated_contracts||'?':'?')
" 2>/dev/null || echo ?)
echo "        Estimated contracts = $SIZING"
echo ""

# ── 5. Production paper account exists ───────────────────────────────
echo "5. Production Paper Account"
PROD_STATUS=$(curl -sf "$BASE/api/flame/status?account_type=production" 2>/dev/null || echo '{}')
PROD_BALANCE=$(echo "$PROD_STATUS" | jq_node "
  const a=d.paper_account||{};
  console.log(a.current_balance!=null?a.current_balance:'missing')
" 2>/dev/null || echo missing)
PAPER_OK="false"
if [ "$PROD_BALANCE" != "missing" ]; then PAPER_OK="true"; fi
check "Production paper_account exists (balance=\$$PROD_BALANCE)" "$PAPER_OK"
echo ""

# ── 6. No stale production positions ─────────────────────────────────
echo "6. Open Production Positions"
PROD_POS=$(curl -sf "$BASE/api/flame/positions?account_type=production" 2>/dev/null || echo '{}')
POS_COUNT=$(echo "$PROD_POS" | jq_node "
  const p=d.positions||(Array.isArray(d)?d:[]);
  console.log(p.filter(x=>x.status==='open').length)
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
