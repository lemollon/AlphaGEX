#!/usr/bin/env bash
# Monitor FLAME's first production trade after deploy.
# Polls every 30 seconds until a production position appears or you ctrl-c.
#
# Usage (from Render shell):  bash monitor_first_trade.sh
# Usage (from local):         bash monitor_first_trade.sh https://your-ironforge.onrender.com
#
# Run this at ~8:30 AM CT and leave it running until FLAME opens its first trade.

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
INTERVAL=30

green() { printf "\033[32m%s\033[0m\n" "$*"; }
red()   { printf "\033[31m%s\033[0m\n" "$*"; }
yellow(){ printf "\033[33m%s\033[0m\n" "$*"; }
dim()   { printf "\033[2m%s\033[0m\n" "$*"; }

# Use node for JSON parsing (guaranteed on Render Node.js service)
jq_node() {
  node -e "const d=JSON.parse(require('fs').readFileSync('/dev/stdin','utf8')); $1"
}

echo "================================================"
echo "  FLAME First Production Trade Monitor"
echo "  Target: $BASE"
echo "  Polling every ${INTERVAL}s — Ctrl+C to stop"
echo "================================================"
echo ""

CYCLE=0
while true; do
  ((CYCLE++))
  NOW=$(date '+%H:%M:%S %Z')

  # ── Check for open production positions ──────────────────────────
  PROD_POS=$(curl -sf "$BASE/api/flame/positions?account_type=production" 2>/dev/null || echo '{}')
  POS_COUNT=$(echo "$PROD_POS" | jq_node "
    const p=d.positions||(Array.isArray(d)?d:[]);
    console.log(p.filter(x=>x.status==='open').length)
  " 2>/dev/null || echo 0)

  if [ "$POS_COUNT" -gt 0 ] 2>/dev/null; then
    echo ""
    green "=========================================="
    green "  PRODUCTION TRADE DETECTED!"
    green "=========================================="
    echo ""

    # Print position details
    echo "$PROD_POS" | jq_node "
      const p=d.positions||(Array.isArray(d)?d:[]);
      p.filter(x=>x.status==='open').forEach(x=>{
        console.log('  Position:  '+x.position_id);
        console.log('  Person:    '+(x.person||'?')+' ('+(x.account_type||'?')+')');
        console.log('  Contracts: '+x.contracts);
        console.log('  Credit:    \$'+(x.total_credit||0).toFixed(4));
        console.log('  Strikes:   '+x.put_short_strike+'/'+x.put_long_strike+'P '+x.call_short_strike+'/'+x.call_long_strike+'C');
        console.log('');
      });
    " 2>/dev/null

    echo "Next steps:"
    echo "  1. Check Tradier dashboard (account 6YB71371) for matching order"
    echo "  2. Watch Live Trading tab on FLAME dashboard"
    echo "  3. Monitor P&L updates every scan cycle"
    echo ""
    green "Monitor complete. Position is live."
    exit 0
  fi

  # ── Check scanner status for skip reasons ────────────────────────
  SCANNER=$(curl -sf "$BASE/api/scanner/status" 2>/dev/null || echo '{}')
  LAST_RESULT=$(echo "$SCANNER" | jq_node "
    const f=(d.bots||{}).flame||{};
    console.log((f.last_result||'unknown').slice(0,80))
  " 2>/dev/null || echo unknown)

  LAST_SCAN=$(echo "$SCANNER" | jq_node "
    const f=(d.bots||{}).flame||{};
    console.log((f.last_scan||'never').slice(0,19))
  " 2>/dev/null || echo never)

  # ── Check if production accounts are loaded ──────────────────────
  DIAG=$(curl -sf "$BASE/api/flame/diagnose-production" 2>/dev/null || echo '{}')
  PROD_COUNT=$(echo "$DIAG" | jq_node "
    console.log((d.production_accounts||[]).length)
  " 2>/dev/null || echo 0)

  # ── Display status ───────────────────────────────────────────────
  if echo "$LAST_RESULT" | grep -q "^traded:"; then
    yellow "  [$NOW] #$CYCLE  Sandbox traded: $LAST_RESULT  |  Prod accounts: $PROD_COUNT  |  Prod positions: $POS_COUNT"
  elif echo "$LAST_RESULT" | grep -q "^skip:"; then
    REASON=$(echo "$LAST_RESULT" | sed 's/^skip://')
    dim    "  [$NOW] #$CYCLE  Skipped: $REASON  |  Prod accounts: $PROD_COUNT"
  else
    dim    "  [$NOW] #$CYCLE  Last: $LAST_RESULT  |  Last scan: $LAST_SCAN  |  Prod accts: $PROD_COUNT"
  fi

  # ── Alert on critical issues ─────────────────────────────────────
  if [ "$PROD_COUNT" = "0" ]; then
    red   "         WARNING: 0 production accounts loaded! DB load may have failed."
  fi

  sleep "$INTERVAL"
done
