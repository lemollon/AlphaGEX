#!/bin/bash
#
# Diagnose unrealized P&L discrepancy across all three data sources.
# Usage: ./diagnose-unrealized-pnl.sh [BASE_URL] [BOT]
#
# Example: ./diagnose-unrealized-pnl.sh https://ironforge-xxx.vercel.app spark
#          ./diagnose-unrealized-pnl.sh http://localhost:3000 spark

BASE="${1:-http://localhost:3000}"
BOT="${2:-spark}"

echo "=== Unrealized P&L Diagnostic ==="
echo "Base URL: $BASE"
echo "Bot: $BOT"
echo ""

echo "--- 1. /api/$BOT/status (header source) ---"
STATUS=$(curl -s "$BASE/api/$BOT/status")
echo "$STATUS" | python3 -c "
import json, sys
d = json.load(sys.stdin)
a = d.get('account', {})
print(f\"  Balance:        \${a.get('balance', 0):,.2f}\")
print(f\"  Realized P&L:   \${a.get('cumulative_pnl', 0):,.2f}\")
print(f\"  Unrealized P&L: \${a.get('unrealized_pnl', 0):,.2f}\")
print(f\"  Total P&L:      \${a.get('total_pnl', 0):,.2f}\")
print(f\"  Return %:       {a.get('return_pct', 0):.2f}%\")
print(f\"  Open positions: {d.get('open_positions', 0)}\")
print(f\"  Last scan:      {d.get('last_scan', 'N/A')}\")
print(f\"  Last reason:    {d.get('last_scan_reason', 'N/A')}\")
" 2>/dev/null || echo "  ERROR: Could not parse status response"

echo ""
echo "--- 2. /api/$BOT/position-monitor (position card source) ---"
MONITOR=$(curl -s "$BASE/api/$BOT/position-monitor")
echo "$MONITOR" | python3 -c "
import json, sys
d = json.load(sys.stdin)
print(f\"  Total Unrealized P&L: \${d.get('total_unrealized_pnl', 0):,.2f}\")
print(f\"  Spot Price:           {d.get('spot_price', 'N/A')}\")
print(f\"  Tradier Connected:    {d.get('tradier_connected', 'N/A')}\")
print(f\"  Position count:       {len(d.get('positions', []))}\")
for i, p in enumerate(d.get('positions', [])):
    print(f\"\")
    print(f\"  Position {i+1}: {p.get('position_id', 'N/A')}\")
    print(f\"    Ticker:         {p.get('ticker', 'N/A')} exp {p.get('expiration', 'N/A')}\")
    print(f\"    Put spread:     {p.get('put_long_strike', 0)}/{p.get('put_short_strike', 0)}\")
    print(f\"    Call spread:    {p.get('call_short_strike', 0)}/{p.get('call_long_strike', 0)}\")
    print(f\"    Contracts:      {p.get('contracts', 0)}\")
    print(f\"    Entry credit:   \${p.get('total_credit', 0):.4f}\")
    print(f\"    Spread width:   \${p.get('spread_width', 0):.2f}\")
    print(f\"    Cost to close:  \${p.get('current_cost_to_close', 'N/A')}\")
    print(f\"    Unrealized P&L: \${p.get('unrealized_pnl', 'N/A')}\")
    print(f\"    Unrealized %:   {p.get('unrealized_pnl_pct', 'N/A')}%\")
    print(f\"    Spot price:     {p.get('spot_price', 'N/A')}\")
    # Manual verification
    ec = p.get('total_credit', 0)
    ctc = p.get('current_cost_to_close')
    c = p.get('contracts', 0)
    sw = p.get('spread_width', 0)
    if ctc is not None:
        capped = min(max(0, ctc), sw)
        manual_pnl = round((ec - capped) * 100 * c * 100) / 100
        raw_pnl = round((ec - ctc) * 100 * c * 100) / 100
        print(f\"    --- MANUAL CHECK ---\")
        print(f\"    Raw formula:    ({ec:.4f} - {ctc:.4f}) * 100 * {c} = \${raw_pnl:,.2f}\")
        print(f\"    Capped formula: ({ec:.4f} - {capped:.4f}) * 100 * {c} = \${manual_pnl:,.2f}\")
" 2>/dev/null || echo "  ERROR: Could not parse position-monitor response"

echo ""
echo "--- 3. /api/$BOT/equity-curve/intraday (chart source) ---"
INTRADAY=$(curl -s "$BASE/api/$BOT/equity-curve/intraday")
echo "$INTRADAY" | python3 -c "
import json, sys
d = json.load(sys.stdin)
print(f\"  Live Unrealized P&L: \${d.get('live_unrealized_pnl', 0):,.2f}\")
print(f\"  Open positions:      {d.get('open_position_count', 0)}\")
snaps = d.get('snapshots', [])
print(f\"  Snapshot count:      {len(snaps)}\")
if snaps:
    last = snaps[-1]
    print(f\"  Last snapshot:\")
    print(f\"    Time:          {last.get('timestamp', 'N/A')}\")
    print(f\"    Balance:       \${last.get('balance', 0):,.2f}\")
    print(f\"    Unrealized:    \${last.get('unrealized_pnl', 0):,.2f}\")
    print(f\"    Equity:        \${last.get('equity', 0):,.2f}\")
    print(f\"    Note:          {last.get('note', 'N/A')}\")
" 2>/dev/null || echo "  ERROR: Could not parse intraday response"

echo ""
echo "--- 4. COMPARISON ---"
python3 -c "
import json, sys

status = json.loads('''$STATUS''')
monitor = json.loads('''$MONITOR''')
intraday = json.loads('''$INTRADAY''')

s_upnl = status.get('account', {}).get('unrealized_pnl', 0)
m_upnl = monitor.get('total_unrealized_pnl', 0)
i_upnl = intraday.get('live_unrealized_pnl', 0)

print(f'  Status endpoint:      \${s_upnl:>10,.2f}')
print(f'  Position-monitor:     \${m_upnl:>10,.2f}')
print(f'  Intraday equity:      \${i_upnl:>10,.2f}')
print()

if s_upnl == m_upnl == i_upnl:
    print('  ✅ All three agree!')
else:
    print('  ❌ DISCREPANCY DETECTED')
    vals = [s_upnl, m_upnl, i_upnl]
    spread = max(vals) - min(vals)
    print(f'  Max spread: \${spread:,.2f}')
    print()
    # The position-monitor is the source of truth (matches position cards)
    print(f'  Position-monitor is the source of truth.')
    print(f'  Status endpoint off by:  \${s_upnl - m_upnl:+,.2f}')
    print(f'  Intraday endpoint off by: \${i_upnl - m_upnl:+,.2f}')
" 2>/dev/null || echo "  ERROR: Could not compare"

echo ""
echo "=== Done ==="
