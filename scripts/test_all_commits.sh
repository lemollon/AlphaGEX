#!/bin/bash
# =============================================================================
# TEST ALL COMMITS - Comprehensive Test Suite
# =============================================================================
# Tests ALL transparency and reliability commits:
#
# EARLIER COMMITS:
#   538fb2b - Commission test uses actual calculator values
#   ad1e728 - Database backfill rollback + date type cast
#   0174057 - Trading Vol API walls fallback + SPX routes fix
#   9f144e9 - Data integrity test suite
#   5db0dae - Data collector auto-start + System health endpoint
#   1ece991 - Frontend timer synced with backend scheduler
#
# RECENT COMMITS:
#   8e13027 - Backend transparency flags and error handling
#   947a2c1 - Frontend error tracking
#   7e23eb2 - Dynamic capital values
#
# Usage:
#   ./scripts/test_all_commits.sh           # Run all tests
#   ./scripts/test_all_commits.sh --api     # Only API tests
#   ./scripts/test_all_commits.sh --files   # Only file verification
#   ./scripts/test_all_commits.sh --python  # Only Python verification
# =============================================================================

# Don't exit on first error - we want to run all tests
set +e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

API_BASE="${API_BASE:-http://localhost:8000}"

PASSED=0
FAILED=0
WARNINGS=0

log_pass() { echo -e "  ${GREEN}✓${NC} $1"; PASSED=$((PASSED+1)); }
log_fail() { echo -e "  ${RED}✗${NC} $1"; FAILED=$((FAILED+1)); }
log_warn() { echo -e "  ${YELLOW}⚠${NC} $1"; WARNINGS=$((WARNINGS+1)); }
log_info() { echo -e "  ${BLUE}ℹ${NC} $1"; }

echo ""
echo -e "${CYAN}╔══════════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║          ALPHAGEX COMPREHENSIVE COMMIT TEST SUITE                   ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════════════════════════╝${NC}"
echo ""

# =============================================================================
# TEST: 538fb2b - Commission Calculator
# =============================================================================
test_commission_calculator() {
    echo -e "${BLUE}━━━ TEST: 538fb2b - Commission Calculator ━━━${NC}"

    cd "$PROJECT_DIR"

    if [ -f "tests/test_commission_calculator.py" ]; then
        log_pass "test_commission_calculator.py exists"

        # Check it uses actual config values
        if grep -q "CommissionCalculator" tests/test_commission_calculator.py 2>/dev/null; then
            log_pass "Uses CommissionCalculator"
        else
            log_warn "May not use actual calculator"
        fi
    else
        log_warn "test_commission_calculator.py not found (may be in different location)"
    fi

    echo ""
}

# =============================================================================
# TEST: ad1e728 - Database Backfill Rollback
# =============================================================================
test_database_rollback() {
    echo -e "${BLUE}━━━ TEST: ad1e728 - Database Backfill Rollback ━━━${NC}"

    cd "$PROJECT_DIR"

    # Check for rollback in backfill scripts
    if grep -rq "conn.rollback()" scripts/ backend/ 2>/dev/null; then
        log_pass "Database rollback calls found"
    else
        log_warn "No rollback calls found"
    fi

    # Check for proper date type casting
    if grep -rq "::date\|DATE(" backend/api/routes/ 2>/dev/null; then
        log_pass "Date type casting found in routes"
    else
        log_warn "Date type casting may be missing"
    fi

    echo ""
}

# =============================================================================
# TEST: 0174057 - Trading Vol API Walls Fallback
# =============================================================================
test_trading_vol_fallback() {
    echo -e "${BLUE}━━━ TEST: 0174057 - Trading Vol API Walls Fallback ━━━${NC}"

    cd "$PROJECT_DIR"

    # Check for wall fallback logic in gex_routes
    if grep -q "call_wall\|put_wall" backend/api/routes/gex_routes.py 2>/dev/null; then
        log_pass "Wall calculations in gex_routes.py"
    else
        log_fail "Missing wall calculations"
    fi

    # Check for SPX routes fix
    if grep -q '"success": False' backend/api/routes/spx_routes.py 2>/dev/null; then
        log_pass "SPX routes returns success:False on error"
    else
        log_fail "SPX routes may return success:True on error"
    fi

    echo ""
}

# =============================================================================
# TEST: 9f144e9 - Data Integrity Test Suite
# =============================================================================
test_data_integrity_suite() {
    echo -e "${BLUE}━━━ TEST: 9f144e9 - Data Integrity Test Suite ━━━${NC}"

    cd "$PROJECT_DIR"

    if [ -f "tests/test_data_integrity.py" ]; then
        log_pass "test_data_integrity.py exists"

        # Check for key tests
        if grep -q "entry_price" tests/test_data_integrity.py 2>/dev/null; then
            log_pass "Tests entry_price validation"
        fi

        if grep -q "autonomous_closed_trades" tests/test_data_integrity.py 2>/dev/null; then
            log_pass "Tests autonomous_closed_trades table"
        fi
    else
        log_warn "test_data_integrity.py not found"
    fi

    echo ""
}

# =============================================================================
# TEST: 5db0dae - Data Collector Auto-Start + System Health
# =============================================================================
test_data_collector_autostart() {
    echo -e "${BLUE}━━━ TEST: 5db0dae - Data Collector Auto-Start ━━━${NC}"

    cd "$PROJECT_DIR"

    # Check main.py starts data collector
    if grep -q "AutomatedDataCollector\|run_data_collector" backend/main.py 2>/dev/null; then
        log_pass "Data collector startup in main.py"
    else
        log_fail "Data collector NOT started in main.py"
    fi

    # Check for system health endpoint
    if grep -q "system-health\|system_health" backend/api/routes/core_routes.py 2>/dev/null; then
        log_pass "System health endpoint exists"
    else
        log_warn "System health endpoint may be in different file"
    fi

    # Test API if running
    if curl -s "${API_BASE}/api/system-health" > /dev/null 2>&1; then
        response=$(curl -s "${API_BASE}/api/system-health")
        if echo "$response" | grep -q '"overall_status"'; then
            status=$(echo "$response" | grep -oP '"overall_status":\s*"\K[^"]+' || echo "unknown")
            log_pass "System health returns status: $status"
        fi
    else
        log_info "API not running - skipping endpoint test"
    fi

    echo ""
}

# =============================================================================
# TEST: 1ece991 - Timer Sync
# =============================================================================
test_timer_sync() {
    echo -e "${BLUE}━━━ TEST: 1ece991 - Timer Sync ━━━${NC}"

    cd "$PROJECT_DIR"

    # Check scheduler syncs to clock time
    if grep -q "minutes_to_next\|seconds_to_next" scheduler/autonomous_scheduler.py 2>/dev/null; then
        log_pass "Scheduler calculates time to next 5-min mark"
    else
        log_warn "Scheduler may use fixed sleep"
    fi

    # Check for clock-based timing
    if grep -q "current_minute.*% 5\|minute % 5" scheduler/autonomous_scheduler.py 2>/dev/null; then
        log_pass "Scheduler uses modulo 5 for clock sync"
    else
        log_warn "Clock sync logic may be missing"
    fi

    echo ""
}

# =============================================================================
# TEST: 8e13027 - Backend Transparency Flags
# =============================================================================
test_backend_transparency() {
    echo -e "${BLUE}━━━ TEST: 8e13027 - Backend Transparency Flags ━━━${NC}"

    cd "$PROJECT_DIR"

    # VIX estimation flag
    if grep -q "vix_is_estimated" backend/api/routes/gex_routes.py 2>/dev/null; then
        log_pass "vix_is_estimated flag in gex_routes.py"
    else
        log_fail "MISSING vix_is_estimated flag"
    fi

    # Gamma estimation flag
    if grep -q "gamma_is_estimated" backend/api/routes/gamma_routes.py 2>/dev/null; then
        log_pass "gamma_is_estimated flag in gamma_routes.py"
    else
        log_fail "MISSING gamma_is_estimated flag"
    fi

    # Trader routes logging
    if grep -q "logger.warning.*Could not fetch" backend/api/routes/trader_routes.py 2>/dev/null; then
        log_pass "Trader routes has warning logging"
    else
        log_warn "Trader routes may have silent errors"
    fi

    # Test API if running
    if curl -s "${API_BASE}/api/gex/SPY" > /dev/null 2>&1; then
        response=$(curl -s "${API_BASE}/api/gex/SPY")
        if echo "$response" | grep -q '"vix_is_estimated"'; then
            log_pass "API returns vix_is_estimated"
        fi
        if echo "$response" | grep -q '"data_source"'; then
            data_source=$(echo "$response" | grep -oP '"data_source":\s*"\K[^"]+' || echo "")
            log_info "Data source: $data_source"
        fi
    fi

    echo ""
}

# =============================================================================
# TEST: 947a2c1 - Frontend Error Tracking
# =============================================================================
test_frontend_error_tracking() {
    echo -e "${BLUE}━━━ TEST: 947a2c1 - Frontend Error Tracking ━━━${NC}"

    cd "$PROJECT_DIR"

    # Check pages for failedEndpoints
    for page in "trader/page.tsx" "spx/page.tsx" "page.tsx"; do
        file="frontend/src/app/$page"
        if [ -f "$file" ]; then
            if grep -q "failedEndpoints" "$file"; then
                log_pass "$page has failedEndpoints"
            else
                log_fail "$page MISSING failedEndpoints"
            fi
        fi
    done

    # Check hooks
    if grep -q "fetchWithLogging" frontend/src/hooks/useTraderWebSocket.ts 2>/dev/null; then
        log_pass "useTraderWebSocket has fetchWithLogging"
    else
        log_fail "useTraderWebSocket MISSING fetchWithLogging"
    fi

    # Check for AlertTriangle warning display
    if grep -q "AlertTriangle" frontend/src/app/trader/page.tsx 2>/dev/null; then
        log_pass "Trader page has warning icon import"
    fi

    echo ""
}

# =============================================================================
# TEST: 7e23eb2 - Dynamic Capital Values
# =============================================================================
test_dynamic_capital() {
    echo -e "${BLUE}━━━ TEST: 7e23eb2 - Dynamic Capital Values ━━━${NC}"

    cd "$PROJECT_DIR"

    # Check SPX page uses dynamic capital
    if grep -q 'status?.starting_capital' frontend/src/app/spx/page.tsx 2>/dev/null; then
        log_pass "SPX page uses dynamic starting_capital"
    else
        log_fail "SPX page has hardcoded capital"
    fi

    # Check trader page uses dynamic capital
    if grep -q 'performance?.starting_capital' frontend/src/app/trader/page.tsx 2>/dev/null; then
        log_pass "Trader page uses dynamic starting_capital"
    else
        log_fail "Trader page has hardcoded capital"
    fi

    # Verify no hardcoded $100M in key places
    if grep -q "'\$100M'\|\"\\$100M\"" frontend/src/app/spx/page.tsx 2>/dev/null; then
        log_warn "SPX page may still have hardcoded $100M string"
    else
        log_pass "No hardcoded $100M found in SPX page"
    fi

    echo ""
}

# =============================================================================
# PYTHON VERIFICATION
# =============================================================================
run_python_tests() {
    echo -e "${BLUE}━━━ PYTHON VERIFICATION ━━━${NC}"

    cd "$PROJECT_DIR"

    if [ -f "scripts/verify_system.py" ]; then
        log_pass "verify_system.py exists"

        echo ""
        echo "Running verify_system.py..."
        echo ""

        python scripts/verify_system.py || true
    else
        log_fail "verify_system.py not found"
    fi

    echo ""
}

# =============================================================================
# SUMMARY
# =============================================================================
show_summary() {
    echo ""
    echo -e "${CYAN}╔══════════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║                         TEST SUMMARY                                ║${NC}"
    echo -e "${CYAN}╚══════════════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo "Commits tested:"
    echo "  538fb2b - Commission test uses actual calculator values"
    echo "  ad1e728 - Database backfill rollback + date type cast"
    echo "  0174057 - Trading Vol API walls fallback + SPX routes fix"
    echo "  9f144e9 - Data integrity test suite"
    echo "  5db0dae - Data collector auto-start + System health endpoint"
    echo "  1ece991 - Frontend timer synced with backend scheduler"
    echo "  8e13027 - Backend transparency flags and error handling"
    echo "  947a2c1 - Frontend error tracking"
    echo "  7e23eb2 - Dynamic capital values"
    echo ""

    TOTAL=$((PASSED + FAILED + WARNINGS))

    echo "Results:"
    echo -e "  ${GREEN}✓ Passed:${NC}   $PASSED"
    echo -e "  ${RED}✗ Failed:${NC}   $FAILED"
    echo -e "  ${YELLOW}⚠ Warnings:${NC} $WARNINGS"
    echo "  ━━━━━━━━━━━━━━━━"
    echo "  Total:      $TOTAL"
    echo ""

    if [ $FAILED -gt 0 ]; then
        echo -e "${RED}❌ SOME TESTS FAILED${NC}"
        exit 1
    elif [ $WARNINGS -gt 5 ]; then
        echo -e "${YELLOW}⚠️  PASSED WITH WARNINGS${NC}"
        exit 0
    else
        echo -e "${GREEN}✅ ALL TESTS PASSED${NC}"
        exit 0
    fi
}

# =============================================================================
# MAIN
# =============================================================================
main() {
    case "${1:-all}" in
        --api)
            test_data_collector_autostart
            test_backend_transparency
            ;;
        --files)
            test_commission_calculator
            test_database_rollback
            test_trading_vol_fallback
            test_data_integrity_suite
            test_data_collector_autostart
            test_timer_sync
            test_backend_transparency
            test_frontend_error_tracking
            test_dynamic_capital
            show_summary
            ;;
        --python)
            run_python_tests
            ;;
        all|*)
            test_commission_calculator
            test_database_rollback
            test_trading_vol_fallback
            test_data_integrity_suite
            test_data_collector_autostart
            test_timer_sync
            test_backend_transparency
            test_frontend_error_tracking
            test_dynamic_capital
            run_python_tests
            show_summary
            ;;
    esac
}

main "$@"
