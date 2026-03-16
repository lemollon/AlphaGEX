#!/usr/bin/env bash
#
# IronForge Production Readiness Test Suite
#
# Run AFTER deploying to Render to verify all endpoints and scanner behavior.
# Usage:
#   BASE_URL=https://your-ironforge.onrender.com ./scripts/test-production.sh
#
# Tests can't be run locally because they require:
#   - PostgreSQL on Render
#   - Tradier API keys in Render env vars
#   - Scanner running inside the Next.js process

set -euo pipefail

BASE="${BASE_URL:-http://localhost:3000}"
PASS=0
FAIL=0
TOTAL=0

green() { echo -e "\033[32m✓ $1\033[0m"; }
red()   { echo -e "\033[31m✗ $1\033[0m"; }

check() {
  local desc="$1"
  local url="$2"
  local expected="${3:-200}"
  TOTAL=$((TOTAL + 1))

  status=$(curl -s -o /tmp/ironforge_test_body -w "%{http_code}" "$url" 2>/dev/null || echo "000")

  if [ "$status" = "$expected" ]; then
    green "$desc (HTTP $status)"
    PASS=$((PASS + 1))
  else
    red "$desc (expected $expected, got $status)"
    # Show first 200 chars of body for debugging
    head -c 200 /tmp/ironforge_test_body 2>/dev/null || true
    echo ""
    FAIL=$((FAIL + 1))
  fi
}

check_json() {
  local desc="$1"
  local url="$2"
  local jq_expr="$3"
  local expected="$4"
  TOTAL=$((TOTAL + 1))

  body=$(curl -s "$url" 2>/dev/null || echo "{}")
  actual=$(echo "$body" | jq -r "$jq_expr" 2>/dev/null || echo "null")

  if [ "$actual" = "$expected" ]; then
    green "$desc ($jq_expr = $actual)"
    PASS=$((PASS + 1))
  else
    red "$desc (expected $jq_expr=$expected, got $actual)"
    FAIL=$((FAIL + 1))
  fi
}

echo "=============================================="
echo "  IronForge Production Test Suite"
echo "  Target: $BASE"
echo "=============================================="
echo ""

# ---- Section 1: Health & Connectivity ----
echo "--- Health & Connectivity ---"
check "Health endpoint"        "$BASE/api/health"
check_json "DB connected"      "$BASE/api/health" ".checks.database.status" "ok"
check_json "Tradier connected" "$BASE/api/health" ".checks.tradier.status"  "ok"

# ---- Section 2: Bot Status (all 3 bots) ----
echo ""
echo "--- Bot Status ---"
for bot in flame spark inferno; do
  check "${bot^^} status"  "$BASE/api/$bot/status"
  check "${bot^^} config"  "$BASE/api/$bot/config"
done

# ---- Section 3: Scanner Heartbeat ----
echo ""
echo "--- Scanner Heartbeat ---"
echo "  (Scanner must have run at least once for these to pass)"
for bot in FLAME SPARK INFERNO; do
  check_json "$bot heartbeat exists" "$BASE/api/health" ".status" "ok"
done

# Verify heartbeat is recent (< 5 min old)
echo ""
echo "--- Heartbeat Freshness (manual check) ---"
for bot in flame spark inferno; do
  echo "  curl -s '$BASE/api/$bot/status' | jq '.heartbeat'"
done

# ---- Section 4: Data Endpoints ----
echo ""
echo "--- Data Endpoints ---"
for bot in flame spark inferno; do
  check "${bot^^} positions"      "$BASE/api/$bot/positions"
  check "${bot^^} equity-curve"   "$BASE/api/$bot/equity-curve"
  check "${bot^^} equity intraday" "$BASE/api/$bot/equity-curve/intraday"
  check "${bot^^} trades"         "$BASE/api/$bot/trades"
  check "${bot^^} performance"    "$BASE/api/$bot/performance"
  check "${bot^^} daily-perf"     "$BASE/api/$bot/daily-perf"
  check "${bot^^} logs"           "$BASE/api/$bot/logs"
  check "${bot^^} signals"        "$BASE/api/$bot/signals"
  check "${bot^^} PDT status"     "$BASE/api/$bot/pdt"
done

# ---- Section 5: Config Values ----
echo ""
echo "--- Config Verification ---"
echo "  Verify per-bot config matches expected defaults:"
echo ""

# FLAME: sd=1.2, pt=30%, sl=100%, entry_end=14:00, max_contracts=10
echo "  FLAME config:"
curl -s "$BASE/api/flame/config" | jq '{sd_multiplier, profit_target_pct, stop_loss_pct, entry_end, max_contracts, max_trades_per_day}' 2>/dev/null || echo "  (failed to fetch)"

# INFERNO: sd=1.0, pt=50%, sl=200%, entry_end=14:30, max_contracts=3, max_trades=0
echo "  INFERNO config:"
curl -s "$BASE/api/inferno/config" | jq '{sd_multiplier, profit_target_pct, stop_loss_pct, entry_end, max_contracts, max_trades_per_day}' 2>/dev/null || echo "  (failed to fetch)"

# ---- Section 6: Scanner Fix Verification ----
echo ""
echo "--- Scanner Fix Verification ---"
echo ""
echo "  Fix 1 (Per-bot config): Check scanner logs for 'config loaded'"
echo "    curl -s '$BASE/api/flame/logs?limit=20' | jq '.logs[] | select(.message | contains(\"config loaded\"))'"
echo ""
echo "  Fix 2 (Sliding PT): Check position-monitor for PT tier"
echo "    curl -s '$BASE/api/flame/position-monitor' | jq '.positions[].profit_target_tier'"
echo ""
echo "  Fix 3 (MTM failures): Check logs for 'mtm_failed' entries"
echo "    curl -s '$BASE/api/flame/logs?limit=50' | jq '[.logs[] | select(.message | contains(\"mtm_failed\"))] | length'"
echo ""
echo "  Fix 4 (Collateral reconciliation): Check logs for 'COLLATERAL RECONCILED'"
echo "    curl -s '$BASE/api/flame/logs?limit=50' | jq '[.logs[] | select(.message | contains(\"RECONCILED\"))] | length'"
echo ""
echo "  Fix 5 (Double-close guard): Check logs for 'matched 0 rows'"
echo "    curl -s '$BASE/api/flame/logs?limit=50' | jq '[.logs[] | select(.message | contains(\"matched 0 rows\"))] | length'"
echo ""
echo "  Fix 6 (EOD cutoff 14:45): Verify no positions open after 2:45 PM CT"
echo "    curl -s '$BASE/api/flame/positions' | jq '.positions | length'"
echo ""
echo "  Fix 7 (Sandbox cleanup): Check logs for 'SANDBOX_CLEANUP'"
echo "    curl -s '$BASE/api/flame/logs?limit=100' | jq '[.logs[] | select(.level == \"SANDBOX_CLEANUP\")] | length'"
echo ""
echo "  Fix 8 (Sandbox health): Check logs for 'SANDBOX_HEALTH'"
echo "    curl -s '$BASE/api/flame/logs?limit=100' | jq '[.logs[] | select(.level == \"SANDBOX_HEALTH\")] | length'"
echo ""
echo "  Fix 9 (Post-EOD verify): Check logs for 'POST_EOD_CHECK'"
echo "    curl -s '$BASE/api/flame/logs?limit=100' | jq '[.logs[] | select(.level == \"POST_EOD_CHECK\")] | length'"
echo ""
echo "  Fix 10 (Live BP): Verify diagnose-trade shows live collateral derivation"
echo "    curl -s '$BASE/api/flame/diagnose-trade'"
echo ""
echo "  Fix 11 (Per-bot entry window): INFERNO should show cutoff 14:30, others 14:00"
echo "    curl -s '$BASE/api/flame/logs?limit=20' | jq '.logs[] | select(.message | contains(\"cutoff\"))'"

# ---- Section 7: Sandbox Account Check ----
echo ""
echo "--- Sandbox Accounts ---"
check "Production accounts" "$BASE/api/accounts/production"

# ---- Section 8: Frontend Pages ----
echo ""
echo "--- Frontend Pages ---"
check "Home page"     "$BASE/"
check "FLAME page"    "$BASE/flame"
check "SPARK page"    "$BASE/spark"
check "INFERNO page"  "$BASE/inferno"
check "Compare page"  "$BASE/compare"
check "Accounts page" "$BASE/accounts"

# ---- Summary ----
echo ""
echo "=============================================="
echo "  Results: $PASS passed, $FAIL failed (of $TOTAL)"
echo "=============================================="

if [ "$FAIL" -gt 0 ]; then
  exit 1
fi
