#!/usr/bin/env bash
# Post-deploy verification for FLAME production trading
# Run immediately after deploying to Render.
#
# Usage (from Render shell):  bash post_deploy_verify.sh
# Usage (from local):         bash post_deploy_verify.sh https://your-ironforge.onrender.com
#
# Auto-detects: IRONFORGE_API_URL env var → arg → Render external URL

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

PASS=0
FAIL=0
WARN=0

green() { printf "\033[32m%s\033[0m\n" "$*"; }
red()   { printf "\033[31m%s\033[0m\n" "$*"; }
yellow(){ printf "\033[33m%s\033[0m\n" "$*"; }
check() {
  local label="$1" ok="$2"
  if [ "$ok" = "true" ]; then
    green "  PASS  $label"; PASS=$((PASS+1))
  else
    red   "  FAIL  $label"; FAIL=$((FAIL+1))
  fi
}
warn_check() {
  local label="$1" ok="$2"
  if [ "$ok" = "true" ]; then
    green "  PASS  $label"; PASS=$((PASS+1))
  else
    yellow "  WARN  $label"; WARN=$((WARN+1))
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
# Response: {"status":"ok","checks":{"database":{"status":"ok","detail":"..."},"tradier":{"status":"ok","detail":"SPY $X"}}}
echo "1. Health Check"
HEALTH=$(curl -sf "$BASE/api/health" 2>/dev/null || echo '{}')
DB_OK=$(echo "$HEALTH" | jq_node "const c=d.checks||{}; console.log((c.database||{}).status==='ok'?'true':'false')" 2>/dev/null || echo false)
TRADIER_OK=$(echo "$HEALTH" | jq_node "const c=d.checks||{}; console.log((c.tradier||{}).status==='ok'?'true':'false')" 2>/dev/null || echo false)
TRADIER_DETAIL=$(echo "$HEALTH" | jq_node "const c=d.checks||{}; console.log((c.tradier||{}).detail||'?')" 2>/dev/null || echo ?)
check "Database connected" "$DB_OK"
check "Tradier connected ($TRADIER_DETAIL)" "$TRADIER_OK"
echo ""

# ── 2. Scanner status ────────────────────────────────────────────────
# Response: {"status":"ok"|"degraded"|"down","bots":[{"bot":"flame","status":"active","is_stale":false,...}],...}
echo "2. Scanner Status"
SCANNER=$(curl -sf "$BASE/api/scanner/status" 2>/dev/null || echo '{}')
SCANNER_OK=$(echo "$SCANNER" | jq_node "console.log(d.status==='ok'?'true':'false')" 2>/dev/null || echo false)
warn_check "Scanner status OK" "$SCANNER_OK"

# Check each bot's staleness
for BOT in flame spark inferno; do
  BOT_STALE=$(echo "$SCANNER" | jq_node "
    const b=(d.bots||[]).find(x=>x.bot==='$BOT');
    console.log(b&&!b.is_stale?'true':'false')
  " 2>/dev/null || echo false)
  BOT_STATUS=$(echo "$SCANNER" | jq_node "
    const b=(d.bots||[]).find(x=>x.bot==='$BOT');
    console.log(b?b.status:'missing')
  " 2>/dev/null || echo missing)
  warn_check "  ${BOT^^} not stale (status: $BOT_STATUS)" "$BOT_STALE"
done
echo ""

# ── 3. FLAME bot status ──────────────────────────────────────────────
# Response: {"is_active":true,"account":{...},"open_positions":0,...}
echo "3. FLAME Bot Status"
STATUS=$(curl -sf "$BASE/api/flame/status" 2>/dev/null || echo '{}')
ENABLED=$(echo "$STATUS" | jq_node "console.log(d.is_active?'true':'false')" 2>/dev/null || echo false)
check "FLAME enabled (is_active)" "$ENABLED"

BALANCE=$(echo "$STATUS" | jq_node "console.log((d.account||{}).balance||'?')" 2>/dev/null || echo ?)
BP=$(echo "$STATUS" | jq_node "console.log((d.account||{}).buying_power||'?')" 2>/dev/null || echo ?)
RETURN_PCT=$(echo "$STATUS" | jq_node "console.log((d.account||{}).return_pct||0)" 2>/dev/null || echo 0)
echo "        Balance: \$$BALANCE  |  BP: \$$BP  |  Return: ${RETURN_PCT}%"

OPEN_POS=$(echo "$STATUS" | jq_node "console.log(d.open_positions||0)" 2>/dev/null || echo 0)
echo "        Open positions: $OPEN_POS"
echo ""

# ── 4. Diagnose production account ───────────────────────────────────
# Response: {"checks":[{"step":"...","pass":true,"detail":"..."},...],"verdict":"..."}
echo "4. Production Account Diagnostics"
DIAG=$(curl -sf "$BASE/api/flame/diagnose-production" 2>/dev/null || echo '{}')

VERDICT=$(echo "$DIAG" | jq_node "console.log(d.verdict||'no response')" 2>/dev/null || echo "no response")
ALL_PASS=$(echo "$DIAG" | jq_node "
  const checks=d.checks||[];
  console.log(checks.length>0 && checks.every(c=>c.pass)?'true':'false')
" 2>/dev/null || echo false)

# Print each diagnostic step
echo "$DIAG" | jq_node "
  (d.checks||[]).forEach(c=>{
    const icon=c.pass?'✓':'✗';
    console.log('    '+icon+' '+c.step+': '+c.detail);
  });
" 2>/dev/null || echo "    (could not parse diagnostics)"

check "All production checks pass" "$ALL_PASS"
echo "        Verdict: $VERDICT"
echo ""

# ── 5. Paper account balance ─────────────────────────────────────────
echo "5. Paper Account"
# Reuse STATUS from step 3
ACCT_BALANCE=$(echo "$STATUS" | jq_node "
  const a=d.account||{};
  console.log(a.starting_capital!=null?'true':'false')
" 2>/dev/null || echo false)
STARTING=$(echo "$STATUS" | jq_node "console.log((d.account||{}).starting_capital||'?')" 2>/dev/null || echo ?)
CUM_PNL=$(echo "$STATUS" | jq_node "console.log((d.account||{}).cumulative_pnl||0)" 2>/dev/null || echo 0)
check "Paper account loaded (starting=\$$STARTING, cumPnl=\$$CUM_PNL)" "$ACCT_BALANCE"
echo ""

# ── 6. Open positions ────────────────────────────────────────────────
echo "6. Open Positions"
POSITIONS=$(curl -sf "$BASE/api/flame/positions" 2>/dev/null || echo '{}')
POS_COUNT=$(echo "$POSITIONS" | jq_node "
  const p=d.positions||[];
  console.log(p.length)
" 2>/dev/null || echo 0)
echo "        Open positions: $POS_COUNT"
if [ "$POS_COUNT" = "0" ]; then
  green "  PASS  No open positions"
  PASS=$((PASS+1))
else
  yellow "  WARN  $POS_COUNT open position(s) — verify they're expected"
  WARN=$((WARN+1))
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
