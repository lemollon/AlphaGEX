#!/bin/bash
# =============================================================================
# TEST TRANSPARENCY FIXES
# =============================================================================
# Tests all the commits made for trader transparency:
# - 8e13027: Backend transparency flags and error handling
# - 947a2c1: Frontend error tracking
# - 7e23eb2: Dynamic capital values
# =============================================================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

PASSED=0
FAILED=0
WARNINGS=0

API_BASE="${API_BASE:-http://localhost:8000}"

log_pass() {
    echo -e "${GREEN}✅ PASS${NC}: $1"
    ((PASSED++))
}

log_fail() {
    echo -e "${RED}❌ FAIL${NC}: $1"
    ((FAILED++))
}

log_warn() {
    echo -e "${YELLOW}⚠️  WARN${NC}: $1"
    ((WARNINGS++))
}

log_info() {
    echo -e "${BLUE}ℹ️  INFO${NC}: $1"
}

print_section() {
    echo ""
    echo "=============================================================================="
    echo "  $1"
    echo "=============================================================================="
    echo ""
}

# =============================================================================
# TEST 1: Backend API Returns Transparency Flags
# =============================================================================
test_backend_transparency_flags() {
    print_section "TEST 1: Backend Transparency Flags"

    # Test GEX endpoint returns vix_is_estimated flag
    log_info "Testing /api/gex/SPY for vix_is_estimated flag..."

    response=$(curl -s "${API_BASE}/api/gex/SPY" 2>/dev/null || echo '{"error": "curl failed"}')

    if echo "$response" | grep -q '"vix_is_estimated"'; then
        log_pass "GEX endpoint returns vix_is_estimated flag"

        # Check if it's a boolean
        if echo "$response" | grep -qE '"vix_is_estimated":\s*(true|false)'; then
            log_pass "vix_is_estimated is a boolean value"
        else
            log_fail "vix_is_estimated is not a boolean"
        fi
    else
        log_fail "GEX endpoint missing vix_is_estimated flag"
    fi

    # Test data_source field
    if echo "$response" | grep -q '"data_source"'; then
        log_pass "GEX endpoint returns data_source field"

        # Extract data_source value
        data_source=$(echo "$response" | grep -oP '"data_source":\s*"\K[^"]+' || echo "unknown")
        log_info "Data source: $data_source"

        if [[ "$data_source" == "tradier_live" ]]; then
            log_pass "Using Tradier as primary data source"
        elif [[ "$data_source" == "live_api" ]]; then
            log_warn "Using TradingVolatility API (Tradier may have failed)"
        else
            log_warn "Using fallback data source: $data_source"
        fi
    else
        log_warn "GEX endpoint missing data_source field"
    fi
}

# =============================================================================
# TEST 2: Gamma Routes Return Estimation Flag
# =============================================================================
test_gamma_estimation_flag() {
    print_section "TEST 2: Gamma Estimation Flag"

    log_info "Testing /api/gamma/split/SPY for gamma_is_estimated flag..."

    response=$(curl -s "${API_BASE}/api/gamma/split/SPY" 2>/dev/null || echo '{"error": "curl failed"}')

    if echo "$response" | grep -q '"gamma_is_estimated"'; then
        log_pass "Gamma split endpoint returns gamma_is_estimated flag"

        if echo "$response" | grep -qE '"gamma_is_estimated":\s*(true|false)'; then
            log_pass "gamma_is_estimated is a boolean value"
        else
            log_fail "gamma_is_estimated is not a boolean"
        fi
    else
        log_fail "Gamma split endpoint missing gamma_is_estimated flag"
    fi
}

# =============================================================================
# TEST 3: SPX Routes Return Proper Success Status
# =============================================================================
test_spx_success_status() {
    print_section "TEST 3: SPX Routes Success Status"

    log_info "Testing /api/spx/trades for proper success status..."

    response=$(curl -s "${API_BASE}/api/spx/trades" 2>/dev/null || echo '{"error": "curl failed"}')

    # Check that success field exists
    if echo "$response" | grep -q '"success"'; then
        log_pass "SPX trades endpoint returns success field"

        # If there's an error, success should be false
        if echo "$response" | grep -q '"error"'; then
            if echo "$response" | grep -q '"success":\s*false'; then
                log_pass "SPX trades returns success:false on error"
            else
                log_fail "SPX trades returns success:true despite error"
            fi
        else
            log_pass "SPX trades response has no error"
        fi
    else
        log_fail "SPX trades endpoint missing success field"
    fi

    log_info "Testing /api/spx/equity-curve..."

    response=$(curl -s "${API_BASE}/api/spx/equity-curve?days=30" 2>/dev/null || echo '{"error": "curl failed"}')

    if echo "$response" | grep -q '"success"'; then
        log_pass "SPX equity curve endpoint returns success field"
    else
        log_fail "SPX equity curve endpoint missing success field"
    fi
}

# =============================================================================
# TEST 4: Trader Routes Log Errors
# =============================================================================
test_trader_error_logging() {
    print_section "TEST 4: Trader Routes Error Handling"

    log_info "Testing /api/trader/performance..."

    response=$(curl -s "${API_BASE}/api/trader/performance" 2>/dev/null || echo '{"error": "curl failed"}')

    if echo "$response" | grep -q '"success":\s*true'; then
        log_pass "Trader performance endpoint working"

        # Check for required fields
        if echo "$response" | grep -q '"total_pnl"'; then
            log_pass "Response includes total_pnl"
        else
            log_warn "Response missing total_pnl"
        fi

        if echo "$response" | grep -q '"starting_capital"'; then
            log_pass "Response includes starting_capital"
        else
            log_warn "Response missing starting_capital"
        fi
    else
        log_warn "Trader performance endpoint may have issues"
    fi

    log_info "Testing /api/trader/status..."

    response=$(curl -s "${API_BASE}/api/trader/status" 2>/dev/null || echo '{"error": "curl failed"}')

    if echo "$response" | grep -q '"success"'; then
        log_pass "Trader status endpoint returns success field"
    else
        log_fail "Trader status endpoint missing success field"
    fi
}

# =============================================================================
# TEST 5: System Health Endpoint
# =============================================================================
test_system_health() {
    print_section "TEST 5: System Health Endpoint"

    log_info "Testing /api/system-health..."

    response=$(curl -s "${API_BASE}/api/system-health" 2>/dev/null || echo '{"error": "curl failed"}')

    if echo "$response" | grep -q '"overall_status"'; then
        log_pass "System health endpoint returns overall_status"

        status=$(echo "$response" | grep -oP '"overall_status":\s*"\K[^"]+' || echo "unknown")
        log_info "System status: $status"

        if [[ "$status" == "healthy" ]]; then
            log_pass "System is healthy"
        elif [[ "$status" == "degraded" ]]; then
            log_warn "System is degraded - check warnings"
        else
            log_warn "System status: $status"
        fi
    else
        log_warn "System health endpoint may not exist (added in recent commit)"
    fi

    # Check for components breakdown
    if echo "$response" | grep -q '"components"'; then
        log_pass "System health includes components breakdown"
    fi

    # Check for issues array
    if echo "$response" | grep -q '"issues"'; then
        log_pass "System health includes issues array"
    fi
}

# =============================================================================
# TEST 6: Data Source Priority
# =============================================================================
test_data_source_priority() {
    print_section "TEST 6: Data Source Priority"

    log_info "Checking data source priority in GEX response..."

    response=$(curl -s "${API_BASE}/api/gex/SPY" 2>/dev/null || echo '{"error": "curl failed"}')

    # Check for Tradier as primary
    if echo "$response" | grep -q 'tradier'; then
        log_pass "Response indicates Tradier data source"

        if echo "$response" | grep -q '"data_source":\s*"tradier_live"'; then
            log_pass "Using Tradier LIVE as primary (correct priority)"
        elif echo "$response" | grep -q '"data_source":\s*"tradier_calculated"'; then
            log_warn "Using Tradier calculated (direct failed)"
        fi
    elif echo "$response" | grep -q '"data_source":\s*"live_api"'; then
        log_warn "Using TradingVolatility API - Tradier may not be configured"
    elif echo "$response" | grep -q '"data_source":\s*"database_fallback"'; then
        log_warn "Using database fallback - all live sources failed"
    fi
}

# =============================================================================
# TEST 7: Frontend Files Modified
# =============================================================================
test_frontend_modifications() {
    print_section "TEST 7: Frontend Modifications"

    log_info "Checking frontend files for error tracking..."

    # Check trader page has failedEndpoints state
    if grep -q "failedEndpoints" /home/user/AlphaGEX/frontend/src/app/trader/page.tsx 2>/dev/null; then
        log_pass "Trader page has failedEndpoints state"
    else
        log_fail "Trader page missing failedEndpoints state"
    fi

    # Check SPX page has failedEndpoints state
    if grep -q "failedEndpoints" /home/user/AlphaGEX/frontend/src/app/spx/page.tsx 2>/dev/null; then
        log_pass "SPX page has failedEndpoints state"
    else
        log_fail "SPX page missing failedEndpoints state"
    fi

    # Check dashboard has failedEndpoints state
    if grep -q "failedEndpoints" /home/user/AlphaGEX/frontend/src/app/page.tsx 2>/dev/null; then
        log_pass "Dashboard has failedEndpoints state"
    else
        log_fail "Dashboard missing failedEndpoints state"
    fi

    # Check hooks have error logging
    if grep -q "fetchWithLogging" /home/user/AlphaGEX/frontend/src/hooks/useTraderWebSocket.ts 2>/dev/null; then
        log_pass "useTraderWebSocket has fetchWithLogging helper"
    else
        log_fail "useTraderWebSocket missing fetchWithLogging helper"
    fi

    # Check for dynamic capital values (not hardcoded)
    if grep -q 'status?.starting_capital' /home/user/AlphaGEX/frontend/src/app/spx/page.tsx 2>/dev/null; then
        log_pass "SPX page uses dynamic starting_capital"
    else
        log_fail "SPX page may have hardcoded capital values"
    fi

    if grep -q 'performance?.starting_capital' /home/user/AlphaGEX/frontend/src/app/trader/page.tsx 2>/dev/null; then
        log_pass "Trader page uses dynamic starting_capital"
    else
        log_fail "Trader page may have hardcoded capital values"
    fi
}

# =============================================================================
# TEST 8: Backend Files Modified
# =============================================================================
test_backend_modifications() {
    print_section "TEST 8: Backend Modifications"

    log_info "Checking backend files for transparency fixes..."

    # Check gex_routes has vix_is_estimated
    if grep -q "vix_is_estimated" /home/user/AlphaGEX/backend/api/routes/gex_routes.py 2>/dev/null; then
        log_pass "gex_routes.py has vix_is_estimated flag"
    else
        log_fail "gex_routes.py missing vix_is_estimated flag"
    fi

    # Check gamma_routes has gamma_is_estimated
    if grep -q "gamma_is_estimated" /home/user/AlphaGEX/backend/api/routes/gamma_routes.py 2>/dev/null; then
        log_pass "gamma_routes.py has gamma_is_estimated flag"
    else
        log_fail "gamma_routes.py missing gamma_is_estimated flag"
    fi

    # Check spx_routes returns success:false on error
    if grep -q '"success": False' /home/user/AlphaGEX/backend/api/routes/spx_routes.py 2>/dev/null; then
        log_pass "spx_routes.py returns success:False on error"
    else
        log_warn "spx_routes.py may not return success:False on error"
    fi

    # Check trader_routes has proper error logging
    if grep -q "logger.warning" /home/user/AlphaGEX/backend/api/routes/trader_routes.py 2>/dev/null; then
        log_pass "trader_routes.py has warning logging"
    else
        log_fail "trader_routes.py missing warning logging"
    fi
}

# =============================================================================
# TEST 9: Verify System Script
# =============================================================================
test_verify_script() {
    print_section "TEST 9: Verify System Script"

    if [ -f /home/user/AlphaGEX/scripts/verify_system.py ]; then
        log_pass "verify_system.py exists"

        # Check it has the expected tests
        if grep -q "test_database_connection" /home/user/AlphaGEX/scripts/verify_system.py 2>/dev/null; then
            log_pass "verify_system.py has database test"
        fi

        if grep -q "test_autonomous_trader" /home/user/AlphaGEX/scripts/verify_system.py 2>/dev/null; then
            log_pass "verify_system.py has trader test"
        fi

        if grep -q "test_trading_volatility_api" /home/user/AlphaGEX/scripts/verify_system.py 2>/dev/null; then
            log_pass "verify_system.py has Trading Vol API test"
        fi
    else
        log_fail "verify_system.py not found"
    fi
}

# =============================================================================
# MAIN
# =============================================================================
main() {
    echo ""
    echo "=============================================================================="
    echo "  ALPHAGEX TRANSPARENCY FIXES TEST SUITE"
    echo "  Testing commits: 8e13027, 947a2c1, 7e23eb2"
    echo "  Started: $(date)"
    echo "=============================================================================="

    # Check if API is running
    log_info "Checking if API is running at ${API_BASE}..."

    if curl -s "${API_BASE}/api/health" > /dev/null 2>&1; then
        log_pass "API is running"

        # Run API tests
        test_backend_transparency_flags
        test_gamma_estimation_flag
        test_spx_success_status
        test_trader_error_logging
        test_system_health
        test_data_source_priority
    else
        log_warn "API not running - skipping API tests"
        log_info "Start the backend with: cd /home/user/AlphaGEX && python backend/main.py"
    fi

    # Run file-based tests (don't need API)
    test_frontend_modifications
    test_backend_modifications
    test_verify_script

    # Summary
    print_section "TEST RESULTS"

    TOTAL=$((PASSED + FAILED + WARNINGS))

    echo ""
    echo "  ✅ Passed:   $PASSED"
    echo "  ❌ Failed:   $FAILED"
    echo "  ⚠️  Warnings: $WARNINGS"
    echo "  ━━━━━━━━━━━━━━━━"
    echo "  Total:      $TOTAL"
    echo ""

    if [ $FAILED -gt 0 ]; then
        echo -e "${RED}❌ SOME TESTS FAILED${NC}"
        exit 1
    elif [ $WARNINGS -gt 3 ]; then
        echo -e "${YELLOW}⚠️  PASSED WITH WARNINGS${NC}"
        exit 0
    else
        echo -e "${GREEN}✅ ALL TESTS PASSED${NC}"
        exit 0
    fi
}

main "$@"
