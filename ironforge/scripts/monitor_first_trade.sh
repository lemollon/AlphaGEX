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
  CYCLE=$((CYCLE+1))
  NOW=$(date '+%H:%M:%S %Z')

  # ── Check for open production positions ──────────────────────────
  # Response: {"positions":[{...}]} — all returned positions are open (route filters status='open')
  PROD_POS=$(curl -sf "$BASE/api/flame/positions?account_type=production" 2>/dev/null || echo '{"positions":[]}')
  POS_COUNT=$(echo "$PROD_POS" | jq_node "
    const p=d.positions||[];
    console.log(p.length)
  " 2>/dev/null || echo 0)

  if [ "$POS_COUNT" -gt 0 ] 2>/dev/null; then
    echo ""
    green "=========================================="
    green "  PRODUCTION TRADE DETECTED!"
    green "=========================================="
    echo ""

    # Print position details
    echo "$PROD_POS" | jq_node "
      const p=d.positions||[];
      p.forEach(x=>{
        console.log('  Position:  '+x.position_id);
        console.log('  Contracts: '+x.contracts);
        console.log('  Credit:    \$'+(x.total_credit||0).toFixed(4));
        console.log('  Strikes:   '+x.put_short_strike+'/'+x.put_long_strike+'P '+x.call_short_strike+'/'+x.call_long_strike+'C');
        console.log('  Expiry:    '+x.expiration);
        console.log('');
      });
    " 2>/dev/null

    echo "Next steps:"
    echo "  1. Check Tradier dashboard for matching order"
    echo "  2. Watch Live Trading tab on FLAME dashboard"
    echo "  3. Monitor P&L updates every scan cycle"
    echo ""
    green "Monitor complete. Position is live."
    exit 0
  fi

  # ── Check scanner status for skip reasons ────────────────────────
  # Response: {"status":"ok","bots":[{"bot":"flame","status":"active","last_action":"...","last_reason":"..."},...]}
  SCANNER=$(curl -s "$BASE/api/scanner/status" 2>/dev/null || echo '{}')
  FLAME_STATUS=$(echo "$SCANNER" | jq_node "
    const b=(d.bots||[]).find(x=>x.bot==='flame');
    if(!b){console.log('no_data');return}
    const action=b.last_action||'?';
    const reason=b.last_reason||'';
    const age=b.age_minutes!=null?b.age_minutes+'m ago':'never';
    console.log(action+(reason?' ('+reason+')':'')+' | heartbeat: '+age)
  " 2>/dev/null || echo "no data")

  # ── Check production diagnostics ────────────────────────────────
  DIAG=$(curl -sf "$BASE/api/flame/diagnose-production" 2>/dev/null || echo '{}')
  DIAG_OK=$(echo "$DIAG" | jq_node "
    const checks=d.checks||[];
    const passed=checks.filter(c=>c.pass).length;
    const total=checks.length;
    console.log(passed+'/'+total+' checks pass')
  " 2>/dev/null || echo "?")

  # ── Display status ───────────────────────────────────────────────
  dim    "  [$NOW] #$CYCLE  FLAME: $FLAME_STATUS  |  Diag: $DIAG_OK  |  Prod positions: $POS_COUNT"

  # ── Alert on diagnostic failures ────────────────────────────────
  BLOCKED=$(echo "$DIAG" | jq_node "
    const v=d.verdict||'';
    console.log(v.includes('BLOCKED')?v:'')
  " 2>/dev/null || echo "")
  if [ -n "$BLOCKED" ]; then
    red   "         $BLOCKED"
  fi

  sleep "$INTERVAL"
done
