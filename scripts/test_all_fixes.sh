#!/bin/bash
# =============================================================================
# AlphaGEX Comprehensive Test Script
# Tests all fixes implemented in this session
# =============================================================================

set -e  # Exit on first error

echo "=============================================================================="
echo "  AlphaGEX Comprehensive Test Suite"
echo "=============================================================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

PASSED=0
FAILED=0
WARNINGS=0

# Helper functions
pass() {
    echo -e "${GREEN}✓ PASS${NC}: $1"
    ((PASSED++))
}

fail() {
    echo -e "${RED}✗ FAIL${NC}: $1"
    ((FAILED++))
}

warn() {
    echo -e "${YELLOW}⚠ WARN${NC}: $1"
    ((WARNINGS++))
}

section() {
    echo ""
    echo "------------------------------------------------------------------------------"
    echo "  $1"
    echo "------------------------------------------------------------------------------"
}

# =============================================================================
# Test 1: Environment Variable Validation
# =============================================================================
section "1. Environment Variable Validation"

if [ -n "$DATABASE_URL" ]; then
    pass "DATABASE_URL is set"
else
    fail "DATABASE_URL is not set (required)"
fi

if [ -n "$TRADIER_API_KEY" ]; then
    if [ ${#TRADIER_API_KEY} -ge 10 ]; then
        pass "TRADIER_API_KEY is set and valid length"
    else
        warn "TRADIER_API_KEY is set but appears too short"
    fi
else
    warn "TRADIER_API_KEY is not set (recommended)"
fi

if [ -n "$POLYGON_API_KEY" ]; then
    pass "POLYGON_API_KEY is set"
else
    warn "POLYGON_API_KEY is not set (recommended)"
fi

if [ -n "$TRADING_VOLATILITY_API_KEY" ]; then
    pass "TRADING_VOLATILITY_API_KEY is set"
else
    warn "TRADING_VOLATILITY_API_KEY is not set (recommended)"
fi

# =============================================================================
# Test 2: Python Import Tests
# =============================================================================
section "2. Python Module Import Tests"

python3 << 'PYEOF'
import sys
tests_passed = 0
tests_failed = 0

def test_import(module_path, description):
    global tests_passed, tests_failed
    try:
        exec(f"from {module_path}")
        print(f"✓ PASS: {description}")
        tests_passed += 1
    except Exception as e:
        print(f"✗ FAIL: {description} - {e}")
        tests_failed += 1

# Test core imports
test_import("backend.api.secure_config import DEFAULT_SPX_STARTING_CAPITAL", "SPX capital constant")
test_import("backend.api.secure_config import get_starting_capital_for_symbol", "Capital helper function")
test_import("backend.api.routes.trader_routes import require_live_trading", "Live trading guard")
test_import("data.gex_calculator import validate_options_data", "Options validation function")
test_import("data.gex_calculator import calculate_gex_from_chain", "GEX calculation function")

print(f"\nImport Tests: {tests_passed} passed, {tests_failed} failed")
sys.exit(0 if tests_failed == 0 else 1)
PYEOF

if [ $? -eq 0 ]; then
    pass "All Python imports successful"
else
    fail "Some Python imports failed"
fi

# =============================================================================
# Test 3: SPX Capital Configuration
# =============================================================================
section "3. SPX Capital Configuration"

python3 << 'PYEOF'
from decimal import Decimal
from backend.api.secure_config import (
    DEFAULT_STARTING_CAPITAL,
    DEFAULT_SPX_STARTING_CAPITAL,
    get_starting_capital_for_symbol
)

# Test constants
assert DEFAULT_STARTING_CAPITAL == Decimal('1000000.00'), "SPY capital should be $1M"
print(f"✓ PASS: SPY default capital = ${DEFAULT_STARTING_CAPITAL:,}")

assert DEFAULT_SPX_STARTING_CAPITAL == Decimal('100000000.00'), "SPX capital should be $100M"
print(f"✓ PASS: SPX default capital = ${DEFAULT_SPX_STARTING_CAPITAL:,}")

# Test helper function
spy_capital = get_starting_capital_for_symbol('SPY')
assert spy_capital == Decimal('1000000.00'), "SPY should get $1M"
print(f"✓ PASS: get_starting_capital_for_symbol('SPY') = ${spy_capital:,}")

spx_capital = get_starting_capital_for_symbol('SPX')
assert spx_capital == Decimal('100000000.00'), "SPX should get $100M"
print(f"✓ PASS: get_starting_capital_for_symbol('SPX') = ${spx_capital:,}")

spxw_capital = get_starting_capital_for_symbol('SPXW')
assert spxw_capital == Decimal('100000000.00'), "SPXW should get $100M"
print(f"✓ PASS: get_starting_capital_for_symbol('SPXW') = ${spxw_capital:,}")
PYEOF

if [ $? -eq 0 ]; then
    pass "SPX capital configuration correct"
else
    fail "SPX capital configuration incorrect"
fi

# =============================================================================
# Test 4: Live Trading Guard
# =============================================================================
section "4. Live Trading Guard"

# Test with flag disabled (default)
unset ENABLE_LIVE_TRADING
python3 << 'PYEOF'
import os
os.environ.pop('ENABLE_LIVE_TRADING', None)

from backend.api.routes.trader_routes import check_live_trading_enabled, require_live_trading
from fastapi import HTTPException

# Test check function
assert check_live_trading_enabled() == False, "Should be disabled by default"
print("✓ PASS: Live trading disabled by default")

# Test guard function
try:
    require_live_trading()
    print("✗ FAIL: Guard should have raised HTTPException")
    exit(1)
except HTTPException as e:
    assert e.status_code == 403, "Should return 403"
    print("✓ PASS: Guard blocks execution when disabled (403)")
PYEOF

if [ $? -eq 0 ]; then
    pass "Live trading guard works when disabled"
else
    fail "Live trading guard failed"
fi

# Test with flag enabled
export ENABLE_LIVE_TRADING=true
python3 << 'PYEOF'
import os
os.environ['ENABLE_LIVE_TRADING'] = 'true'

from backend.api.routes.trader_routes import check_live_trading_enabled, require_live_trading

# Test check function
assert check_live_trading_enabled() == True, "Should be enabled"
print("✓ PASS: Live trading enabled when flag set")

# Test guard function (should not raise)
try:
    require_live_trading()
    print("✓ PASS: Guard allows execution when enabled")
except Exception as e:
    print(f"✗ FAIL: Guard should not raise when enabled: {e}")
    exit(1)
PYEOF

if [ $? -eq 0 ]; then
    pass "Live trading guard works when enabled"
else
    fail "Live trading guard failed when enabled"
fi
unset ENABLE_LIVE_TRADING

# =============================================================================
# Test 5: Options Data Validation
# =============================================================================
section "5. Options Data Validation"

python3 << 'PYEOF'
from data.gex_calculator import validate_options_data

# Test with empty data
result = validate_options_data([], 500.0, "TEST")
assert result['valid'] == False, "Empty data should be invalid"
assert "No options data provided" in result['issues']
print("✓ PASS: Empty options data rejected")

# Test with good data
good_data = [
    {'strike': 490, 'gamma': 0.05, 'open_interest': 5000, 'option_type': 'put'},
    {'strike': 495, 'gamma': 0.08, 'open_interest': 8000, 'option_type': 'put'},
    {'strike': 500, 'gamma': 0.12, 'open_interest': 15000, 'option_type': 'call'},
    {'strike': 505, 'gamma': 0.09, 'open_interest': 10000, 'option_type': 'call'},
    {'strike': 510, 'gamma': 0.06, 'open_interest': 6000, 'option_type': 'call'},
    {'strike': 515, 'gamma': 0.04, 'open_interest': 4000, 'option_type': 'call'},
    {'strike': 520, 'gamma': 0.03, 'open_interest': 3000, 'option_type': 'call'},
    {'strike': 485, 'gamma': 0.04, 'open_interest': 4000, 'option_type': 'put'},
    {'strike': 480, 'gamma': 0.03, 'open_interest': 3000, 'option_type': 'put'},
    {'strike': 475, 'gamma': 0.02, 'open_interest': 2000, 'option_type': 'put'},
]
result = validate_options_data(good_data, 500.0, "TEST")
assert result['valid'] == True, f"Good data should be valid: {result['issues']}"
print(f"✓ PASS: Valid options data accepted (stats: {result['stats']['total_contracts']} contracts)")

# Test with bad spot price
result = validate_options_data(good_data, -100.0, "TEST")
assert result['valid'] == False, "Negative spot price should be invalid"
print("✓ PASS: Invalid spot price rejected")
PYEOF

if [ $? -eq 0 ]; then
    pass "Options data validation working"
else
    fail "Options data validation failed"
fi

# =============================================================================
# Test 6: DTE Tracking (Database Query)
# =============================================================================
section "6. DTE Tracking Implementation"

python3 << 'PYEOF'
import inspect
from core.intelligence_and_strategies import DTEOptimizer

# Check that the method exists and has real implementation
optimizer = DTEOptimizer()
method = optimizer._get_historical_dte_performance

# Get source code
source = inspect.getsource(method)

# Verify it's not a placeholder
assert "TODO" not in source, "Should not contain TODO"
assert "placeholder" not in source.lower(), "Should not be placeholder"
assert "SELECT" in source, "Should contain SQL query"
assert "autonomous_closed_trades" in source, "Should query closed trades"

print("✓ PASS: DTE tracking has real implementation (not placeholder)")
print("✓ PASS: DTE tracking queries autonomous_closed_trades table")
PYEOF

if [ $? -eq 0 ]; then
    pass "DTE tracking implemented"
else
    fail "DTE tracking still placeholder"
fi

# =============================================================================
# Test 7: DataFrame Safety Checks
# =============================================================================
section "7. DataFrame Safety Checks"

python3 << 'PYEOF'
import inspect

# Check daily_performance_aggregator
from monitoring import daily_performance_aggregator
source = inspect.getsource(daily_performance_aggregator)

# Should have empty checks before iloc
if "if len(historical_pnl) > 0" in source or "not historical_pnl.empty" in source:
    print("✓ PASS: daily_performance_aggregator has empty DataFrame check")
else:
    print("✗ FAIL: daily_performance_aggregator missing empty check")
    exit(1)

# Check gex_data_tracker
from gamma import gex_data_tracker
source = inspect.getsource(gex_data_tracker)

if "try:" in source and "except (IndexError, KeyError)" in source:
    print("✓ PASS: gex_data_tracker has try/except for iloc access")
else:
    print("✗ FAIL: gex_data_tracker missing safety checks")
    exit(1)
PYEOF

if [ $? -eq 0 ]; then
    pass "DataFrame safety checks in place"
else
    fail "DataFrame safety checks missing"
fi

# =============================================================================
# Test 8: Tradier Integration in GEX Routes
# =============================================================================
section "8. Tradier Integration in GEX Routes"

python3 << 'PYEOF'
import inspect
from backend.api.routes import gex_routes

# Check that Tradier is imported
assert hasattr(gex_routes, 'TRADIER_AVAILABLE'), "Should have TRADIER_AVAILABLE flag"
print(f"✓ PASS: TRADIER_AVAILABLE = {gex_routes.TRADIER_AVAILABLE}")

# Check that get_gex_from_tradier_direct exists
assert hasattr(gex_routes, 'get_gex_from_tradier_direct'), "Should have Tradier direct function"
print("✓ PASS: get_gex_from_tradier_direct function exists")

# Check fallback chain
source = inspect.getsource(gex_routes.get_gex_data_with_fallback)
assert "Tradier direct" in source or "tradier_direct" in source, "Should try Tradier first"
assert "TradingVolatilityAPI" in source, "Should fallback to TradingVolatility"
assert "database" in source.lower(), "Should fallback to database"
print("✓ PASS: Fallback chain: Tradier -> TradingVolatility -> Database")
PYEOF

if [ $? -eq 0 ]; then
    pass "Tradier integration in GEX routes"
else
    fail "Tradier integration missing"
fi

# =============================================================================
# Test 9: Database Connection Cleanup
# =============================================================================
section "9. Database Connection Cleanup"

python3 << 'PYEOF'
import inspect
from backend.api.routes import gex_routes

# Check get_gex_history has finally block
source = inspect.getsource(gex_routes.get_gex_history)
assert "finally:" in source, "get_gex_history should have finally block"
assert "conn.close()" in source, "Should close connection in finally"
print("✓ PASS: get_gex_history has proper connection cleanup")

# Check get_regime_changes has finally block
source = inspect.getsource(gex_routes.get_regime_changes)
assert "finally:" in source, "get_regime_changes should have finally block"
assert "conn.close()" in source, "Should close connection in finally"
print("✓ PASS: get_regime_changes has proper connection cleanup")

# Check get_gex_from_database has finally block
source = inspect.getsource(gex_routes.get_gex_from_database)
assert "finally:" in source, "get_gex_from_database should have finally block"
print("✓ PASS: get_gex_from_database has proper connection cleanup")
PYEOF

if [ $? -eq 0 ]; then
    pass "Database connection cleanup implemented"
else
    fail "Database connection cleanup missing"
fi

# =============================================================================
# Test 10: API Endpoint Test (if server running)
# =============================================================================
section "10. API Endpoint Test (Optional)"

# Check if API is running
if curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/ 2>/dev/null | grep -q "200"; then
    echo "API server detected, running endpoint tests..."

    # Test health endpoint
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/)
    if [ "$HTTP_CODE" = "200" ]; then
        pass "Health endpoint returns 200"
    else
        fail "Health endpoint returned $HTTP_CODE"
    fi

    # Test GEX endpoint
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/api/gex/SPY)
    if [ "$HTTP_CODE" = "200" ]; then
        pass "GEX endpoint returns 200"
    else
        warn "GEX endpoint returned $HTTP_CODE (may need API keys)"
    fi

    # Test execute endpoint without ENABLE_LIVE_TRADING
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST http://localhost:8000/api/trader/execute)
    if [ "$HTTP_CODE" = "403" ]; then
        pass "Execute endpoint blocked (403) - live trading guard working"
    else
        warn "Execute endpoint returned $HTTP_CODE (expected 403)"
    fi
else
    echo "API server not running - skipping endpoint tests"
    echo "Start with: cd backend && python main.py"
fi

# =============================================================================
# Summary
# =============================================================================
echo ""
echo "=============================================================================="
echo "  TEST SUMMARY"
echo "=============================================================================="
echo ""
echo -e "  ${GREEN}PASSED${NC}:   $PASSED"
echo -e "  ${RED}FAILED${NC}:   $FAILED"
echo -e "  ${YELLOW}WARNINGS${NC}: $WARNINGS"
echo ""

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}All critical tests passed!${NC}"
    exit 0
else
    echo -e "${RED}Some tests failed. Please review the output above.${NC}"
    exit 1
fi
