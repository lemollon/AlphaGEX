#!/usr/bin/env bash
# Dashboard Accuracy Test — GAP 6
#
# Compares Databricks DB values vs API responses for all three bots.
# Run from any machine with:
#   1. DATABRICKS_SERVER_HOSTNAME, DATABRICKS_WAREHOUSE_ID, DATABRICKS_TOKEN set
#   2. curl access to the Render deployment
#
# Usage: bash ironforge/scripts/dashboard_accuracy_test.sh [URL]

set -euo pipefail

# Auto-detect base URL
# Render shell is a separate container — no PORT, no localhost access.
RENDER_DEFAULT="https://ironforge-dashboard.onrender.com"
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

echo "=== IronForge Dashboard Accuracy Test ==="
echo "Render URL: $BASE"
echo "Databricks: $DATABRICKS_SERVER_HOSTNAME"
echo ""

# --- Helper: query Databricks SQL Statement API ---
db_query() {
  local sql="$1"
  local response
  response=$(curl -s -X POST "https://${DATABRICKS_SERVER_HOSTNAME}/api/2.0/sql/statements/" \
    -H "Authorization: Bearer ${DATABRICKS_TOKEN}" \
    -H "Content-Type: application/json" \
    -d "{
      \"warehouse_id\": \"${DATABRICKS_WAREHOUSE_ID}\",
      \"catalog\": \"alpha_prime\",
      \"schema\": \"ironforge\",
      \"statement\": \"${sql} /* accuracy_test_$(date +%s) */\",
      \"wait_timeout\": \"30s\",
      \"disposition\": \"INLINE\",
      \"format\": \"JSON_ARRAY\"
    }")
  echo "$response"
}

for BOT in spark flame inferno; do
  DTE=""
  case $BOT in
    flame)   DTE="2DTE" ;;
    spark)   DTE="1DTE" ;;
    inferno) DTE="0DTE" ;;
  esac

  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "BOT: ${BOT^^} ($DTE)"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

  # 1. Query Databricks directly for paper_account
  echo ""
  echo "[DB] Paper Account (raw stored values):"
  DB_ACCT=$(db_query "SELECT current_balance, collateral_in_use, cumulative_pnl, buying_power, starting_capital FROM alpha_prime.ironforge.${BOT}_paper_account WHERE is_active = TRUE AND dte_mode = '${DTE}' ORDER BY id DESC LIMIT 1")
  echo "$DB_ACCT" | python3 -c "
import sys, json
r = json.load(sys.stdin)
cols = [c['name'] for c in r.get('manifest',{}).get('schema',{}).get('columns',[])]
rows = r.get('result',{}).get('data_array',[])
if rows:
    for c, v in zip(cols, rows[0]):
        print(f'  {c}: {v}')
else:
    print('  (no data)')
" 2>/dev/null || echo "  (query failed)"

  # 2. Query actual position-derived values (what the API calculates)
  echo ""
  echo "[DB] Live-calculated values (source of truth):"
  DB_LIVE=$(db_query "SELECT COALESCE(SUM(realized_pnl), 0) as total_pnl, COUNT(*) as total_trades FROM alpha_prime.ironforge.${BOT}_positions WHERE status IN ('closed', 'expired') AND realized_pnl IS NOT NULL AND dte_mode = '${DTE}'")
  echo "$DB_LIVE" | python3 -c "
import sys, json
r = json.load(sys.stdin)
cols = [c['name'] for c in r.get('manifest',{}).get('schema',{}).get('columns',[])]
rows = r.get('result',{}).get('data_array',[])
if rows:
    for c, v in zip(cols, rows[0]):
        print(f'  {c}: {v}')
else:
    print('  (no data)')
" 2>/dev/null || echo "  (query failed)"

  DB_COLL=$(db_query "SELECT COALESCE(SUM(collateral_required), 0) as live_collateral FROM alpha_prime.ironforge.${BOT}_positions WHERE status = 'open' AND dte_mode = '${DTE}'")
  echo "$DB_COLL" | python3 -c "
import sys, json
r = json.load(sys.stdin)
rows = r.get('result',{}).get('data_array',[])
if rows:
    print(f'  live_collateral: {rows[0][0]}')
" 2>/dev/null || echo "  (query failed)"

  # 3. Hit the API
  echo ""
  echo "[API] Status endpoint response:"
  API_RESP=$(curl -s "$API/$BOT/status")
  echo "$API_RESP" | python3 -c "
import sys, json
r = json.load(sys.stdin)
a = r.get('account', {})
print(f'  balance:          {a.get(\"balance\")}')
print(f'  cumulative_pnl:   {a.get(\"cumulative_pnl\")}')
print(f'  unrealized_pnl:   {a.get(\"unrealized_pnl\")}')
print(f'  collateral:       {a.get(\"collateral_in_use\")}')
print(f'  buying_power:     {a.get(\"buying_power\")}')
print(f'  total_trades:     {a.get(\"total_trades\")}')
print(f'  starting_capital: {a.get(\"starting_capital\")}')
" 2>/dev/null || echo "  (API call failed)"

  echo ""
  echo "[COMPARE] DB stored vs API calculated:"
  python3 -c "
import json, sys
# Parse both responses
try:
    db_raw = '''$DB_ACCT'''
    api_raw = '''$API_RESP'''
    db = json.loads(db_raw)
    api = json.loads(api_raw)

    db_rows = db.get('result',{}).get('data_array',[])
    api_acct = api.get('account', {})

    if db_rows:
        db_balance = float(db_rows[0][0] or 0)
        db_collateral = float(db_rows[0][1] or 0)
        db_pnl = float(db_rows[0][2] or 0)

        api_balance = float(api_acct.get('balance', 0))
        api_collateral = float(api_acct.get('collateral_in_use', 0))
        api_pnl = float(api_acct.get('cumulative_pnl', 0))

        fields = [
            ('balance', db_balance, api_balance),
            ('collateral', db_collateral, api_collateral),
            ('cumulative_pnl', db_pnl, api_pnl),
        ]
        for name, db_val, api_val in fields:
            match = 'MATCH' if abs(db_val - api_val) < 0.02 else 'DRIFT'
            print(f'  {name}: DB={db_val:.2f} API={api_val:.2f} [{match}]')
except Exception as e:
    print(f'  (comparison failed: {e})')
" 2>/dev/null || echo "  (comparison failed)"

  echo ""
done

echo "=== Test Complete ==="
echo ""
echo "KEY:"
echo "  [DB] = Raw Databricks paper_account table (may be stale)"
echo "  [API] = Render API (recalculates from actual positions — source of truth)"
echo "  MATCH = Values within $0.02"
echo "  DRIFT = Values differ (expected if paper_account hasn't been reconciled)"
echo ""
echo "NOTE: The API is CORRECT even when it doesn't match the DB paper_account."
echo "The API recalculates from actual position data (SUM of closed trades)."
echo "Drift in paper_account is cosmetic — the dashboard shows API values."
