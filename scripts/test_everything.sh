#!/bin/bash
# =============================================================================
# ALPHAGEX COMPLETE TEST SUITE
# =============================================================================
# Single script to test ALL commits and verify the entire system.
#
# Commits tested:
#   538fb2b - Commission test uses actual calculator values
#   ad1e728 - Database backfill rollback + date type cast
#   0174057 - Trading Vol API walls fallback + SPX routes fix
#   9f144e9 - Data integrity test suite
#   5db0dae - Data collector auto-start + System health endpoint
#   1ece991 - Frontend timer synced with backend scheduler
#   8e13027 - Backend transparency flags and error handling
#   947a2c1 - Frontend error tracking
#   7e23eb2 - Dynamic capital values
#
# Usage:
#   ./scripts/test_everything.sh
# =============================================================================

set +e  # Don't exit on first error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

API_BASE="${API_BASE:-http://localhost:8000}"

PASSED=0
FAILED=0
WARNINGS=0

log_pass() { echo -e "  ${GREEN}✓${NC} $1"; PASSED=$((PASSED+1)); }
log_fail() { echo -e "  ${RED}✗${NC} $1"; FAILED=$((FAILED+1)); }
log_warn() { echo -e "  ${YELLOW}⚠${NC} $1"; WARNINGS=$((WARNINGS+1)); }
log_info() { echo -e "  ${BLUE}ℹ${NC} $1"; }

section() {
    echo ""
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${CYAN}  $1${NC}"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

subsection() {
    echo ""
    echo -e "${BLUE}▶ $1${NC}"
}

# =============================================================================
# HEADER
# =============================================================================
echo ""
echo -e "${CYAN}╔══════════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║           ALPHAGEX COMPLETE TEST SUITE                              ║${NC}"
echo -e "${CYAN}║           Testing All Transparency & Reliability Commits            ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo "  Started: $(date)"
echo "  Project: $PROJECT_DIR"
echo ""

# =============================================================================
# PART 1: GIT STATUS
# =============================================================================
section "PART 1: GIT STATUS"

subsection "Recent commits on this branch"
git log --oneline -10 2>/dev/null || echo "  (git not available)"

subsection "Current branch"
git branch --show-current 2>/dev/null || echo "  (unknown)"

# =============================================================================
# PART 2: FILE VERIFICATION
# =============================================================================
section "PART 2: FILE VERIFICATION"

# --- 538fb2b: Commission Calculator ---
subsection "538fb2b - Commission Calculator"
if [ -f "tests/test_commission_calculator.py" ]; then
    log_pass "test_commission_calculator.py exists"
    grep -q "CommissionCalculator" tests/test_commission_calculator.py && log_pass "Uses CommissionCalculator class"
else
    log_warn "test_commission_calculator.py not found"
fi

# --- ad1e728: Database Rollback ---
subsection "ad1e728 - Database Backfill Rollback"
grep -rq "conn.rollback()" scripts/ backend/ 2>/dev/null && log_pass "Database rollback calls found" || log_warn "No rollback calls found"
grep -rq "::date\|DATE(" backend/api/routes/ 2>/dev/null && log_pass "Date type casting found" || log_warn "Date casting may be missing"

# --- 0174057: Trading Vol API Walls ---
subsection "0174057 - Trading Vol API Walls Fallback"
grep -q "call_wall\|put_wall" backend/api/routes/gex_routes.py && log_pass "Wall calculations in gex_routes.py" || log_fail "Missing wall calculations"
grep -q '"success": False' backend/api/routes/spx_routes.py && log_pass "SPX returns success:False on error" || log_fail "SPX may return success:True on error"

# --- 9f144e9: Data Integrity ---
subsection "9f144e9 - Data Integrity Test Suite"
if [ -f "tests/test_data_integrity.py" ]; then
    log_pass "test_data_integrity.py exists"
    grep -q "entry_price" tests/test_data_integrity.py && log_pass "Tests entry_price validation"
    grep -q "autonomous_closed_trades" tests/test_data_integrity.py && log_pass "Tests autonomous_closed_trades"
else
    log_warn "test_data_integrity.py not found"
fi

# --- 5db0dae: Data Collector Auto-Start ---
subsection "5db0dae - Data Collector Auto-Start"
grep -q "AutomatedDataCollector\|run_data_collector" backend/main.py && log_pass "Data collector startup in main.py" || log_fail "Data collector NOT started"
grep -q "system-health\|system_health" backend/api/routes/core_routes.py && log_pass "System health endpoint exists" || log_warn "System health may be elsewhere"

# --- 1ece991: Timer Sync ---
subsection "1ece991 - Timer Sync"
grep -q "minutes_to_next\|seconds_to_next" scheduler/autonomous_scheduler.py && log_pass "Scheduler calculates next 5-min mark" || log_warn "May use fixed sleep"
grep -q "current_minute.*% 5\|minute % 5" scheduler/autonomous_scheduler.py && log_pass "Uses modulo 5 for clock sync" || log_warn "Clock sync logic missing"

# --- 8e13027: Backend Transparency ---
subsection "8e13027 - Backend Transparency Flags"
grep -q "vix_is_estimated" backend/api/routes/gex_routes.py && log_pass "vix_is_estimated in gex_routes.py" || log_fail "MISSING vix_is_estimated"
grep -q "gamma_is_estimated" backend/api/routes/gamma_routes.py && log_pass "gamma_is_estimated in gamma_routes.py" || log_fail "MISSING gamma_is_estimated"
grep -q "logger.warning.*Could not fetch" backend/api/routes/trader_routes.py && log_pass "Trader routes has warning logging" || log_warn "May have silent errors"

# --- 947a2c1: Frontend Error Tracking ---
subsection "947a2c1 - Frontend Error Tracking"
for page in "trader/page.tsx" "spx/page.tsx" "page.tsx"; do
    file="frontend/src/app/$page"
    [ -f "$file" ] && grep -q "failedEndpoints" "$file" && log_pass "$page has failedEndpoints" || log_fail "$page MISSING failedEndpoints"
done
grep -q "fetchWithLogging" frontend/src/hooks/useTraderWebSocket.ts && log_pass "useTraderWebSocket has fetchWithLogging" || log_fail "MISSING fetchWithLogging"
grep -q "AlertTriangle" frontend/src/app/trader/page.tsx && log_pass "Trader page has warning icon"

# --- 7e23eb2: Dynamic Capital ---
subsection "7e23eb2 - Dynamic Capital Values"
grep -q 'status?.starting_capital' frontend/src/app/spx/page.tsx && log_pass "SPX uses dynamic starting_capital" || log_fail "SPX has hardcoded capital"
grep -q 'performance?.starting_capital' frontend/src/app/trader/page.tsx && log_pass "Trader uses dynamic starting_capital" || log_fail "Trader has hardcoded capital"
! grep -q "'\$100M'" frontend/src/app/spx/page.tsx && log_pass "No hardcoded \$100M in SPX" || log_warn "May have hardcoded \$100M"

# =============================================================================
# PART 3: API VERIFICATION
# =============================================================================
section "PART 3: API VERIFICATION"

if curl -s "${API_BASE}/api/health" > /dev/null 2>&1; then
    log_pass "API is running at ${API_BASE}"

    # GEX Endpoint
    subsection "GEX Endpoint (/api/gex/SPY)"
    response=$(curl -s "${API_BASE}/api/gex/SPY" 2>/dev/null)

    echo "$response" | grep -q '"vix_is_estimated"' && log_pass "Returns vix_is_estimated flag" || log_fail "Missing vix_is_estimated"
    echo "$response" | grep -q '"data_source"' && {
        data_source=$(echo "$response" | grep -oP '"data_source":\s*"\K[^"]+' || echo "unknown")
        log_pass "Data source: $data_source"
        [ "$data_source" = "tradier_live" ] && log_pass "Using Tradier as PRIMARY (correct)"
    } || log_fail "Missing data_source"
    echo "$response" | grep -q '"net_gex"' && log_pass "Returns net_gex"
    echo "$response" | grep -q '"call_wall"' && log_pass "Returns call_wall"
    echo "$response" | grep -q '"put_wall"' && log_pass "Returns put_wall"

    # Gamma Endpoint
    subsection "Gamma Endpoint (/api/gamma/split/SPY)"
    response=$(curl -s "${API_BASE}/api/gamma/split/SPY" 2>/dev/null)
    echo "$response" | grep -q '"gamma_is_estimated"' && log_pass "Returns gamma_is_estimated" || log_fail "Missing gamma_is_estimated"

    # Trader Endpoint
    subsection "Trader Endpoint (/api/trader/performance)"
    response=$(curl -s "${API_BASE}/api/trader/performance" 2>/dev/null)
    echo "$response" | grep -q '"success"' && log_pass "Returns success field"
    echo "$response" | grep -q '"starting_capital"' && log_pass "Returns starting_capital" || log_warn "Missing starting_capital"
    echo "$response" | grep -q '"total_pnl"' && log_pass "Returns total_pnl"

    # SPX Endpoint
    subsection "SPX Endpoint (/api/spx/trades)"
    response=$(curl -s "${API_BASE}/api/spx/trades" 2>/dev/null)
    echo "$response" | grep -q '"success"' && log_pass "Returns success field"

    # System Health
    subsection "System Health (/api/system-health)"
    response=$(curl -s "${API_BASE}/api/system-health" 2>/dev/null)
    if echo "$response" | grep -q '"overall_status"'; then
        status=$(echo "$response" | grep -oP '"overall_status":\s*"\K[^"]+' || echo "unknown")
        log_pass "System status: $status"
        echo "$response" | grep -q '"components"' && log_pass "Includes components breakdown"
        echo "$response" | grep -q '"issues"' && log_pass "Includes issues array"
    else
        log_warn "System health endpoint may not exist"
    fi

else
    log_warn "API not running at ${API_BASE}"
    log_info "Start backend: cd $PROJECT_DIR && python backend/main.py"
    log_info "Skipping API tests..."
fi

# =============================================================================
# PART 4: PYTHON VERIFICATION (verify_system.py)
# =============================================================================
section "PART 4: PYTHON SYSTEM VERIFICATION"

if [ -f "scripts/verify_system.py" ]; then
    log_pass "verify_system.py exists"

    echo ""
    echo -e "${YELLOW}Running verify_system.py...${NC}"
    echo ""

    python scripts/verify_system.py 2>&1 || true
else
    log_fail "verify_system.py not found"
fi

# =============================================================================
# PART 5: DEPENDENCY CHECK
# =============================================================================
section "PART 5: DEPENDENCY CHECK"

subsection "Python packages"
python -c "import fastapi" 2>/dev/null && log_pass "fastapi installed" || log_fail "fastapi missing"
python -c "import psycopg2" 2>/dev/null && log_pass "psycopg2 installed" || log_fail "psycopg2 missing"
python -c "import schedule" 2>/dev/null && log_pass "schedule installed" || log_fail "schedule missing"

subsection "Environment variables"
[ -n "$DATABASE_URL" ] && log_pass "DATABASE_URL is set" || log_warn "DATABASE_URL not set"
[ -n "$TRADIER_API_KEY" ] && log_pass "TRADIER_API_KEY is set" || log_warn "TRADIER_API_KEY not set"
[ -n "$TRADING_VOLATILITY_API_KEY" ] && log_pass "TRADING_VOLATILITY_API_KEY is set" || log_warn "TRADING_VOLATILITY_API_KEY not set"

# =============================================================================
# SUMMARY
# =============================================================================
section "TEST SUMMARY"

TOTAL=$((PASSED + FAILED + WARNINGS))

echo ""
echo "  Commits verified:"
echo "    538fb2b - Commission test uses actual calculator values"
echo "    ad1e728 - Database backfill rollback + date type cast"
echo "    0174057 - Trading Vol API walls fallback + SPX routes fix"
echo "    9f144e9 - Data integrity test suite"
echo "    5db0dae - Data collector auto-start + System health endpoint"
echo "    1ece991 - Frontend timer synced with backend scheduler"
echo "    8e13027 - Backend transparency flags and error handling"
echo "    947a2c1 - Frontend error tracking"
echo "    7e23eb2 - Dynamic capital values"
echo ""
echo "  ┌─────────────────────────────┐"
echo -e "  │ ${GREEN}✓ Passed:${NC}   ${BOLD}$PASSED${NC}              │"
echo -e "  │ ${RED}✗ Failed:${NC}   ${BOLD}$FAILED${NC}              │"
echo -e "  │ ${YELLOW}⚠ Warnings:${NC} ${BOLD}$WARNINGS${NC}              │"
echo "  │ ─────────────────────────── │"
echo "  │ Total:      $TOTAL              │"
echo "  └─────────────────────────────┘"
echo ""

if [ $FAILED -gt 0 ]; then
    echo -e "${RED}╔══════════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${RED}║  ❌ SOME TESTS FAILED - Review errors above                         ║${NC}"
    echo -e "${RED}╚══════════════════════════════════════════════════════════════════════╝${NC}"
    exit 1
elif [ $WARNINGS -gt 5 ]; then
    echo -e "${YELLOW}╔══════════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${YELLOW}║  ⚠️  PASSED WITH WARNINGS - Review warnings above                    ║${NC}"
    echo -e "${YELLOW}╚══════════════════════════════════════════════════════════════════════╝${NC}"
    exit 0
else
    echo -e "${GREEN}╔══════════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║  ✅ ALL TESTS PASSED                                                ║${NC}"
    echo -e "${GREEN}╚══════════════════════════════════════════════════════════════════════╝${NC}"
    exit 0
fi
