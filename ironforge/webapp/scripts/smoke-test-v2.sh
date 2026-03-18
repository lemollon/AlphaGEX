#!/usr/bin/env bash
#
# IronForge Smoke Test v2 — March 2026
#
# Safe, read-only smoke test for the IronForge Render deployment.
# No force-trades, no writes, no toggles. Just GETs.
#
# Usage:
#   bash ironforge/webapp/scripts/smoke-test-v2.sh https://your-app.onrender.com
#   bash ironforge/webapp/scripts/smoke-test-v2.sh http://localhost:3000
#
set -euo pipefail

BASE_URL="${1:?Usage: $0 <base-url>}"
BASE_URL="${BASE_URL%/}"

PASS=0
FAIL=0
WARN=0
SKIP=0
TOTAL=0
FAILURES=""

# ── Colours ──────────────────────────────────────────────────────
green()  { printf "\033[32m%s\033[0m\n" "$*"; }
red()    { printf "\033[31m%s\033[0m\n" "$*"; }
yellow() { printf "\033[33m%s\033[0m\n" "$*"; }
cyan()   { printf "\033[36m%s\033[0m\n" "$*"; }
bold()   { printf "\033[1m%s\033[0m\n" "$*"; }

# ── Check helper ─────────────────────────────────────────────────
#  check "Label" "URL" [expected_status] [jq_expr] [jq_desc]
#
#  jq_expr  — if provided, extract this from the body and test truthiness
#  jq_desc  — optional human label for what jq_expr checks
check() {
  local label="$1"
  local url="$2"
  local expected="${3:-200}"
  local jq_expr="${4:-}"
  local jq_desc="${5:-}"

  ((TOTAL++))
  printf "  %-55s " "$label"

  local response http_code body
  response=$(curl -s -w "\n%{http_code}" --max-time 20 "$url" 2>/dev/null) || {
    red "FAIL (connection error)"
    ((FAIL++))
    FAILURES+="  ✗ $label — connection error\n"
    return
  }

  http_code=$(echo "$response" | tail -1)
  body=$(echo "$response" | sed '$d')

  if [ "$http_code" != "$expected" ]; then
    red "FAIL (HTTP $http_code, expected $expected)"
    ((FAIL++))
    FAILURES+="  ✗ $label — HTTP $http_code\n"
    return
  fi

  # If no jq check, just verify status code
  if [ -z "$jq_expr" ]; then
    green "PASS (HTTP $http_code)"
    ((PASS++))
    return
  fi

  # jq validation
  if ! command -v jq &>/dev/null; then
    yellow "WARN (HTTP OK, jq not installed — skipping validation)"
    ((WARN++))
    return
  fi

  local jq_result
  jq_result=$(echo "$body" | jq -r "$jq_expr" 2>/dev/null) || jq_result=""

  if [ -z "$jq_result" ] || [ "$jq_result" = "null" ] || [ "$jq_result" = "false" ]; then
    yellow "WARN (HTTP $http_code OK, but ${jq_desc:-jq check} failed)"
    ((WARN++))
    FAILURES+="  ⚠ $label — ${jq_desc:-jq check}: got '$jq_result'\n"
    return
  fi

  green "PASS ($jq_result)"
  ((PASS++))
}

# ── Header ───────────────────────────────────────────────────────
echo ""
bold "╔══════════════════════════════════════════════════════════╗"
bold "║         IronForge Smoke Test v2 — March 2026            ║"
bold "║         READ-ONLY • NO TRADES • NO MUTATIONS            ║"
bold "╚══════════════════════════════════════════════════════════╝"
echo ""
cyan "  Target:  $BASE_URL"
cyan "  Time:    $(date '+%Y-%m-%d %H:%M:%S %Z')"
echo ""

# ══════════════════════════════════════════════════════════════════
#  1. INFRASTRUCTURE
# ══════════════════════════════════════════════════════════════════
bold "1. Infrastructure"
check "Health endpoint"              "$BASE_URL/api/health"   200 '.status'                         "status field"
check "  Database connected"         "$BASE_URL/api/health"   200 '.checks.database.status == "ok"' "db status=ok"
check "  Tradier connected"          "$BASE_URL/api/health"   200 '.checks.tradier.status'          "tradier status"
echo ""

# ══════════════════════════════════════════════════════════════════
#  2. SCANNER
# ══════════════════════════════════════════════════════════════════
bold "2. Scanner"
check "Scanner consolidated status"  "$BASE_URL/api/scanner/status"  200 '.status'  "scanner status"
echo ""

# ══════════════════════════════════════════════════════════════════
#  3–5. PER-BOT CHECKS (FLAME, SPARK, INFERNO)
# ══════════════════════════════════════════════════════════════════
for bot in flame spark inferno; do
  BOT_UPPER=$(echo "$bot" | tr '[:lower:]' '[:upper:]')
  bold "── $BOT_UPPER ──"

  # Status
  check "$BOT_UPPER status"                "$BASE_URL/api/$bot/status"                200 '.account.balance'     "balance"
  check "$BOT_UPPER strategy field"        "$BASE_URL/api/$bot/status"                200 '.strategy'            "strategy"
  check "$BOT_UPPER bot_state field"       "$BASE_URL/api/$bot/status"                200 '.bot_state'           "bot_state"

  # Positions (may be empty array — that's fine)
  check "$BOT_UPPER positions endpoint"    "$BASE_URL/api/$bot/positions"             200 '.positions | type == "array"' "is array"

  # Equity curve (historical)
  check "$BOT_UPPER equity curve"          "$BASE_URL/api/$bot/equity-curve"          200 '.starting_capital'    "starting_capital"
  check "$BOT_UPPER equity curve (1w)"     "$BASE_URL/api/$bot/equity-curve?period=1w" 200 '.period == "1w"'     "period=1w"

  # Intraday equity
  check "$BOT_UPPER intraday equity"       "$BASE_URL/api/$bot/equity-curve/intraday" 200 '.snapshots | type == "array"' "snapshots array"

  # Performance
  check "$BOT_UPPER performance"           "$BASE_URL/api/$bot/performance"           200 '.total_trades'        "total_trades"

  # Config
  check "$BOT_UPPER config"               "$BASE_URL/api/$bot/config"                200 '.config'              "config obj"

  # Trades (closed history)
  check "$BOT_UPPER trades"               "$BASE_URL/api/$bot/trades"                200 '.trades | type == "array"' "trades array"

  # Logs
  check "$BOT_UPPER logs"                 "$BASE_URL/api/$bot/logs"                  200 '.logs | type == "array"'   "logs array"

  # Signals
  check "$BOT_UPPER signals"              "$BASE_URL/api/$bot/signals"               200 '.signals | type == "array"' "signals array"

  # PDT
  check "$BOT_UPPER PDT status"           "$BASE_URL/api/$bot/pdt"                   200 '.pdt_status'          "pdt_status"

  # Daily perf
  check "$BOT_UPPER daily perf"           "$BASE_URL/api/$bot/daily-perf"            200 '.days | type == "array"'  "days array"

  # Diagnostics (read-only GETs)
  check "$BOT_UPPER diagnose-trade"       "$BASE_URL/api/$bot/diagnose-trade"        200 '.gates'               "gates obj"
  check "$BOT_UPPER position-monitor"     "$BASE_URL/api/$bot/position-monitor"      200 '.positions | type == "array"' "positions array"

  echo ""
done

# ══════════════════════════════════════════════════════════════════
#  6. ACCOUNT MANAGEMENT
# ══════════════════════════════════════════════════════════════════
bold "6. Account Management"
check "List accounts"                "$BASE_URL/api/accounts/manage"         200 '.production'      "production key"
check "Production balances"          "$BASE_URL/api/accounts/production"     200 '.accounts | type == "array"' "accounts array"
echo ""

# ══════════════════════════════════════════════════════════════════
#  7. FRONTEND PAGES (just check they return 200)
# ══════════════════════════════════════════════════════════════════
bold "7. Frontend Pages"
for page in "" flame spark inferno accounts compare; do
  label="${page:-home}"
  check "/$label page renders"       "$BASE_URL/$page"                       200
done
echo ""

# ══════════════════════════════════════════════════════════════════
#  8. CROSS-BOT CONSISTENCY CHECKS
# ══════════════════════════════════════════════════════════════════
if command -v jq &>/dev/null; then
  bold "8. Cross-Bot Consistency"

  # Verify each bot reports the correct DTE
  for pair in "flame:2" "spark:1" "inferno:0"; do
    bot="${pair%%:*}"
    expected_dte="${pair##*:}"
    BOT_UPPER=$(echo "$bot" | tr '[:lower:]' '[:upper:]')

    ((TOTAL++))
    printf "  %-55s " "$BOT_UPPER reports DTE=$expected_dte"

    actual_dte=$(curl -s --max-time 10 "$BASE_URL/api/$bot/status" 2>/dev/null | jq -r '.dte // empty' 2>/dev/null) || actual_dte=""

    if [ "$actual_dte" = "$expected_dte" ]; then
      green "PASS (dte=$actual_dte)"
      ((PASS++))
    elif [ -z "$actual_dte" ]; then
      yellow "WARN (dte field missing)"
      ((WARN++))
    else
      red "FAIL (dte=$actual_dte, expected $expected_dte)"
      ((FAIL++))
      FAILURES+="  ✗ $BOT_UPPER DTE — got $actual_dte, expected $expected_dte\n"
    fi
  done

  # Verify collateral sanity: if 0 positions, collateral should be 0
  for bot in flame spark inferno; do
    BOT_UPPER=$(echo "$bot" | tr '[:lower:]' '[:upper:]')

    ((TOTAL++))
    printf "  %-55s " "$BOT_UPPER collateral sanity"

    status_json=$(curl -s --max-time 10 "$BASE_URL/api/$bot/status" 2>/dev/null) || status_json=""
    open_pos=$(echo "$status_json" | jq -r '.open_positions // 0' 2>/dev/null) || open_pos=""
    collateral=$(echo "$status_json" | jq -r '.account.collateral_in_use // 0' 2>/dev/null) || collateral=""

    if [ -z "$open_pos" ] || [ -z "$collateral" ]; then
      yellow "WARN (couldn't parse status)"
      ((WARN++))
    elif [ "$open_pos" = "0" ] && [ "$collateral" != "0" ]; then
      red "FAIL (0 positions but \$$collateral collateral — stuck!)"
      ((FAIL++))
      FAILURES+="  ✗ $BOT_UPPER stuck collateral: 0 positions, \$$collateral collateral\n"
    else
      green "PASS (positions=$open_pos, collateral=\$$collateral)"
      ((PASS++))
    fi
  done

  echo ""
fi

# ══════════════════════════════════════════════════════════════════
#  SUMMARY
# ══════════════════════════════════════════════════════════════════
bold "╔══════════════════════════════════════════════════════════╗"
printf "\033[1m║  Results: %d passed, %d failed, %d warnings (%d total)    \033[0m\n" "$PASS" "$FAIL" "$WARN" "$TOTAL"

if [ -n "$FAILURES" ]; then
  bold "╠══════════════════════════════════════════════════════════╣"
  bold "║  Issues:"
  printf "$FAILURES"
fi

if [ "$FAIL" -gt 0 ]; then
  bold "╠══════════════════════════════════════════════════════════╣"
  red   "║  STATUS: FAILED — $FAIL checks need attention"
  bold "╚══════════════════════════════════════════════════════════╝"
  exit 1
elif [ "$WARN" -gt 0 ]; then
  bold "╠══════════════════════════════════════════════════════════╣"
  yellow "║  STATUS: PASSED WITH WARNINGS"
  bold "╚══════════════════════════════════════════════════════════╝"
  exit 0
else
  bold "╠══════════════════════════════════════════════════════════╣"
  green  "║  STATUS: ALL PASSED ✓"
  bold "╚══════════════════════════════════════════════════════════╝"
  exit 0
fi
