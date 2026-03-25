#!/bin/bash
# IronForge Scanner Health Check — run in Render shell
# Usage: bash check_scanner.sh [URL]
# Example: bash check_scanner.sh https://ironforge-xxxx.onrender.com

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

echo "=== IronForge Scanner Health Check ==="
echo "Target: $BASE"
echo ""

# 1. Scanner status — is it running? Are accounts loaded?
echo "--- 1. Scanner Status ---"
curl -s "$BASE/api/scanner/status" | python3 -m json.tool 2>/dev/null || curl -s "$BASE/api/scanner/status"
echo ""

# 2. Health endpoint
echo "--- 2. Health ---"
curl -s "$BASE/api/health" | python3 -m json.tool 2>/dev/null || curl -s "$BASE/api/health"
echo ""

# 3. Check accounts — are any loaded from DB?
echo "--- 3. Accounts (DB) ---"
curl -s "$BASE/api/accounts" | python3 -m json.tool 2>/dev/null || curl -s "$BASE/api/accounts"
echo ""

# 4. Test Tradier connectivity with first account
echo "--- 4. Tradier Account Test ---"
curl -s "$BASE/api/accounts/test-all" | python3 -m json.tool 2>/dev/null || curl -s "$BASE/api/accounts/test-all"
echo ""

# 5. Check FLAME scan activity — what's the scanner actually doing?
echo "--- 5. FLAME Recent Scan Logs (last 10) ---"
curl -s "$BASE/api/scanner/status" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    bots = d.get('bots', {})
    for name, info in bots.items():
        print(f'  {name}: status={info.get(\"status\",\"?\")}, scans={info.get(\"scan_count\",0)}, last={info.get(\"last_scan\",\"never\")}')
        details = info.get('details', {})
        if details:
            print(f'    action={details.get(\"action\",\"?\")}, reason={details.get(\"reason\",\"?\")}')
            if details.get('spot'): print(f'    SPY={details[\"spot\"]}, VIX={details.get(\"vix\",\"?\")}')
except: print('  (could not parse)')
" 2>/dev/null
echo ""

# 6. Check if quote API key is working (SPY quote)
echo "--- 6. SPY Quote Test ---"
curl -s "$BASE/api/health" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    t = d.get('tradier', {})
    print(f'  configured: {t.get(\"configured\", False)}')
    print(f'  key_source: {t.get(\"key_source\", \"unknown\")}')
    print(f'  base_url: {t.get(\"base_url\", \"unknown\")}')
except: print('  (could not parse)')
" 2>/dev/null
echo ""

echo "=== KEY THINGS TO CHECK ==="
echo "1. Scanner 'started' should be true"
echo "2. Accounts should show at least 1 loaded"
echo "3. Bot action should NOT be 'tradier_not_configured'"
echo "4. Bot action should be 'traded' or 'no_trade' or 'monitoring' (not 'skip')"
echo "5. If action='skip' + reason='tradier_not_configured' → API key not loading from DB"
echo "6. If action='skip' + reason='no_spy_quote' → key loaded but sandbox API rejecting it"
echo ""
echo "=== QUICK DB CHECK (run in Render PostgreSQL shell) ==="
echo "SELECT id, person, type, is_active, LEFT(api_key, 8) || '...' as key_preview FROM ironforge_accounts;"
echo ""
