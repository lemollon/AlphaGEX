#!/usr/bin/env bash
#
# IronForge Production Smoke Test
#
# Run against your Render deployment to verify everything works end-to-end.
#
# Usage:
#   ./scripts/smoke-test.sh https://your-render-app.onrender.com
#   ./scripts/smoke-test.sh http://localhost:3000
#
set -euo pipefail

BASE_URL="${1:?Usage: $0 <base-url>}"
BASE_URL="${BASE_URL%/}" # strip trailing slash

PASS=0
FAIL=0
WARN=0

green()  { printf "\033[32m%s\033[0m\n" "$*"; }
red()    { printf "\033[31m%s\033[0m\n" "$*"; }
yellow() { printf "\033[33m%s\033[0m\n" "$*"; }
bold()   { printf "\033[1m%s\033[0m\n" "$*"; }

check() {
  local label="$1"
  local url="$2"
  local expected_status="${3:-200}"
  local jq_check="${4:-}"

  printf "  %-50s " "$label"

  local http_code body
  body=$(curl -s -w "\n%{http_code}" --max-time 15 "$url" 2>/dev/null) || {
    red "FAIL (connection error)"
    ((FAIL++))
    return
  }

  http_code=$(echo "$body" | tail -1)
  body=$(echo "$body" | sed '$d')

  if [ "$http_code" != "$expected_status" ]; then
    red "FAIL (HTTP $http_code, expected $expected_status)"
    ((FAIL++))
    return
  fi

  if [ -n "$jq_check" ]; then
    local jq_result
    jq_result=$(echo "$body" | jq -r "$jq_check" 2>/dev/null) || jq_result=""
    if [ -z "$jq_result" ] || [ "$jq_result" = "null" ] || [ "$jq_result" = "false" ]; then
      yellow "WARN (HTTP $http_code OK, but jq check failed: $jq_check)"
      ((WARN++))
      return
    fi
    green "PASS ($jq_result)"
  else
    green "PASS (HTTP $http_code)"
  fi
  ((PASS++))
}

check_post() {
  local label="$1"
  local url="$2"
  local expected_status="${3:-200}"

  printf "  %-50s " "$label"

  local http_code body
  body=$(curl -s -w "\n%{http_code}" --max-time 15 -X POST "$url" 2>/dev/null) || {
    red "FAIL (connection error)"
    ((FAIL++))
    return
  }

  http_code=$(echo "$body" | tail -1)

  if [ "$http_code" != "$expected_status" ]; then
    red "FAIL (HTTP $http_code, expected $expected_status)"
    ((FAIL++))
    return
  fi

  green "PASS (HTTP $http_code)"
  ((PASS++))
}

bold ""
bold "========================================================"
bold "  IronForge Production Smoke Test"
bold "  Target: $BASE_URL"
bold "  Time:   $(date '+%Y-%m-%d %H:%M:%S %Z')"
bold "========================================================"
echo ""

# ------------------------------------------------------------------
#  1. Infrastructure Health
# ------------------------------------------------------------------
bold "1. Infrastructure Health"
check "Health endpoint"                   "$BASE_URL/api/health"      200 '.status'
check "  Database connected"              "$BASE_URL/api/health"      200 '.checks.database.status == "ok"'
check "  Tradier connected"               "$BASE_URL/api/health"      200 '.checks.tradier.status'

echo ""

# ------------------------------------------------------------------
#  2. Scanner Status (all 3 bots)
# ------------------------------------------------------------------
bold "2. Scanner Status"
check "Scanner consolidated status"       "$BASE_URL/api/scanner/status"  "" '.status'

for bot in flame spark inferno; do
  BOT_UPPER=$(echo "$bot" | tr '[:lower:]' '[:upper:]')
  echo ""
  bold "3-$bot. $BOT_UPPER Dashboard APIs"

  check "  $BOT_UPPER status"               "$BASE_URL/api/$bot/status"           200 '.account.balance'
  check "  $BOT_UPPER positions"             "$BASE_URL/api/$bot/positions"        200 '.positions'
  check "  $BOT_UPPER equity curve"          "$BASE_URL/api/$bot/equity-curve"     200 '.starting_capital'
  check "  $BOT_UPPER intraday equity"       "$BASE_URL/api/$bot/equity-curve/intraday" 200 '.snapshots'
  check "  $BOT_UPPER performance"           "$BASE_URL/api/$bot/performance"      200 '.total_trades'
  check "  $BOT_UPPER config"                "$BASE_URL/api/$bot/config"           200 '.config'
  check "  $BOT_UPPER trades history"        "$BASE_URL/api/$bot/trades"           200 '.trades'
  check "  $BOT_UPPER logs"                  "$BASE_URL/api/$bot/logs"             200 '.logs'
  check "  $BOT_UPPER PDT status"            "$BASE_URL/api/$bot/pdt"             200 '.pdt_status'
  check "  $BOT_UPPER signals"               "$BASE_URL/api/$bot/signals"          200 '.signals'
  check "  $BOT_UPPER daily perf"            "$BASE_URL/api/$bot/daily-perf"       200 '.days'
  check "  $BOT_UPPER position monitor"      "$BASE_URL/api/$bot/position-monitor" 200 '.positions'
  check "  $BOT_UPPER diagnose trade"        "$BASE_URL/api/$bot/diagnose-trade"   200 '.gates'
done

echo ""

# ------------------------------------------------------------------
#  4. Account Management
# ------------------------------------------------------------------
bold "4. Account Management"
check "  List accounts"                   "$BASE_URL/api/accounts/manage"       200 '.production'
check "  Production balances"             "$BASE_URL/api/accounts/production"   200 '.accounts'

echo ""

# ------------------------------------------------------------------
#  5. Frontend Pages (verify they render)
# ------------------------------------------------------------------
bold "5. Frontend Pages"
for page in "" flame spark inferno accounts compare; do
  label="${page:-home}"
  check "  /$label page loads"            "$BASE_URL/$page"                     200
done

echo ""

# ------------------------------------------------------------------
#  Summary
# ------------------------------------------------------------------
bold "========================================================"
TOTAL=$((PASS + FAIL + WARN))
bold "  Results: $PASS passed, $FAIL failed, $WARN warnings (of $TOTAL checks)"

if [ "$FAIL" -gt 0 ]; then
  red "  STATUS: FAILED — $FAIL checks need attention"
  bold "========================================================"
  exit 1
elif [ "$WARN" -gt 0 ]; then
  yellow "  STATUS: PASSED WITH WARNINGS — $WARN checks need review"
  bold "========================================================"
  exit 0
else
  green "  STATUS: ALL PASSED"
  bold "========================================================"
  exit 0
fi
