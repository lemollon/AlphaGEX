#!/usr/bin/env bash
# Monitor FLAME's first production trade after deploy.
# Polls every 30 seconds until a production position appears or you ctrl-c.
#
# Usage: bash ironforge/scripts/monitor_first_trade.sh [BASE_URL]
# Default: https://ironforge-pi.vercel.app
#
# Run this at ~8:30 AM CT and leave it running until FLAME opens its first trade.

set -uo pipefail

BASE="${1:-https://ironforge-pi.vercel.app}"
INTERVAL=30

green() { printf "\033[32m%s\033[0m\n" "$*"; }
red()   { printf "\033[31m%s\033[0m\n" "$*"; }
yellow(){ printf "\033[33m%s\033[0m\n" "$*"; }
dim()   { printf "\033[2m%s\033[0m\n" "$*"; }

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
  POS_COUNT=$(echo "$PROD_POS" | python3 -c "
import sys,json
d=json.load(sys.stdin)
positions = d.get('positions', d if isinstance(d, list) else [])
open_pos = [p for p in positions if p.get('status') == 'open']
print(len(open_pos))
" 2>/dev/null || echo 0)

  if [ "$POS_COUNT" -gt 0 ]; then
    echo ""
    green "=========================================="
    green "  PRODUCTION TRADE DETECTED!"
    green "=========================================="
    echo ""

    # Print position details
    echo "$PROD_POS" | python3 -c "
import sys,json
d=json.load(sys.stdin)
positions = d.get('positions', d if isinstance(d, list) else [])
for p in positions:
    if p.get('status') != 'open': continue
    pid = p.get('position_id', '?')
    contracts = p.get('contracts', '?')
    credit = p.get('total_credit', 0) or 0
    ps = p.get('put_short_strike', '?')
    pl = p.get('put_long_strike', '?')
    cs = p.get('call_short_strike', '?')
    cl = p.get('call_long_strike', '?')
    person = p.get('person', '?')
    acct_type = p.get('account_type', '?')
    print(f'  Position:  {pid}')
    print(f'  Person:    {person} ({acct_type})')
    print(f'  Contracts: {contracts}')
    print(f'  Credit:    \${credit:.4f}' if isinstance(credit, (int, float)) else f'  Credit:    {credit}')
    print(f'  Strikes:   {ps}/{pl}P {cs}/{cl}C')
    print()
" 2>/dev/null

    # Verify on Tradier
    echo "Next steps:"
    echo "  1. Check Tradier dashboard (account 6YB71371) for matching order"
    echo "  2. Watch Live Trading tab at $BASE/flame (switch to Live)"
    echo "  3. Monitor P&L updates every scan cycle"
    echo ""
    green "Monitor complete. Position is live."
    exit 0
  fi

  # ── Check scanner status for skip reasons ────────────────────────
  SCANNER=$(curl -sf "$BASE/api/scanner/status" 2>/dev/null || echo '{}')
  LAST_RESULT=$(echo "$SCANNER" | python3 -c "
import sys,json
d=json.load(sys.stdin)
bots = d.get('bots', {})
flame = bots.get('flame', {})
result = flame.get('last_result', 'unknown')
print(result[:80] if isinstance(result, str) else 'unknown')
" 2>/dev/null || echo unknown)

  LAST_SCAN=$(echo "$SCANNER" | python3 -c "
import sys,json
d=json.load(sys.stdin)
bots = d.get('bots', {})
flame = bots.get('flame', {})
print(flame.get('last_scan', 'never')[:19])
" 2>/dev/null || echo never)

  # ── Check if production accounts are loaded ──────────────────────
  DIAG=$(curl -sf "$BASE/api/flame/diagnose-production" 2>/dev/null || echo '{}')
  PROD_COUNT=$(echo "$DIAG" | python3 -c "
import sys,json
d=json.load(sys.stdin)
print(len(d.get('production_accounts', [])))
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
