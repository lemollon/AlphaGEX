#!/bin/bash
# =============================================================================
# COMPREHENSIVE ROUTE FILE CHECKER FOR ALPHAGEX
# Tests ALL 20 route files + dependencies for import errors
# =============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo "============================================================================="
echo "  ALPHAGEX COMPREHENSIVE ROUTE & MODULE CHECKER"
echo "  Testing ALL 20 route files for import errors"
echo "============================================================================="
echo ""

cd /home/user/AlphaGEX

# Set PYTHONPATH to project root (simulates Render environment)
export PYTHONPATH="/home/user/AlphaGEX:$PYTHONPATH"

ERRORS_FOUND=0
WARNINGS_FOUND=0
FILES_CHECKED=0

# Create temporary results file
RESULTS_FILE="/tmp/alphagex_check_results.txt"
> "$RESULTS_FILE"

# =============================================================================
# PART 1: Check all route files exist
# =============================================================================
echo -e "${BLUE}PART 1: Checking route files exist...${NC}"
echo ""

ROUTE_DIR="backend/api/routes"
EXPECTED_ROUTES=(
    "__init__.py"
    "ai_intelligence_routes.py"
    "ai_routes.py"
    "alerts_routes.py"
    "autonomous_routes.py"
    "backtest_routes.py"
    "core_routes.py"
    "database_routes.py"
    "gamma_routes.py"
    "gex_routes.py"
    "misc_routes.py"
    "notification_routes.py"
    "optimizer_routes.py"
    "probability_routes.py"
    "psychology_routes.py"
    "scanner_routes.py"
    "setups_routes.py"
    "spx_routes.py"
    "system_routes.py"
    "trader_routes.py"
    "vix_routes.py"
)

for route in "${EXPECTED_ROUTES[@]}"; do
    if [ -f "$ROUTE_DIR/$route" ]; then
        echo -e "  ${GREEN}✓${NC} $route exists"
    else
        echo -e "  ${RED}✗${NC} $route MISSING!"
        ERRORS_FOUND=$((ERRORS_FOUND + 1))
        echo "MISSING FILE: $ROUTE_DIR/$route" >> "$RESULTS_FILE"
    fi
done

echo ""

# =============================================================================
# PART 2: Check all required dependency modules exist
# =============================================================================
echo -e "${BLUE}PART 2: Checking dependency modules exist...${NC}"
echo ""

REQUIRED_MODULES=(
    "database_adapter.py"
    "core_classes_and_engines.py"
    "utils/__init__.py"
    "utils/logging_config.py"
    "utils/rate_limiter.py"
    "utils/expiration_utils.py"
    "core/__init__.py"
    "core/intelligence_and_strategies.py"
    "core/probability_calculator.py"
    "data/unified_data_provider.py"
    "db/config_and_database.py"
    "backend/api/__init__.py"
    "backend/api/dependencies.py"
)

for module in "${REQUIRED_MODULES[@]}"; do
    if [ -f "$module" ]; then
        echo -e "  ${GREEN}✓${NC} $module exists"
    else
        echo -e "  ${RED}✗${NC} $module MISSING!"
        ERRORS_FOUND=$((ERRORS_FOUND + 1))
        echo "MISSING MODULE: $module" >> "$RESULTS_FILE"
    fi
done

echo ""

# =============================================================================
# PART 3: Test each route file imports individually
# =============================================================================
echo -e "${BLUE}PART 3: Testing each route file imports (simulating Render)...${NC}"
echo ""

# First, test the utils package itself
echo "  Testing utils package..."
python3 -c "
import sys
sys.path.insert(0, '/home/user/AlphaGEX')
try:
    import utils
    print('    utils package: OK')
except Exception as e:
    print(f'    utils package: FAILED - {e}')
    sys.exit(1)
" 2>&1 || {
    echo -e "  ${RED}✗${NC} utils package failed to import"
    ERRORS_FOUND=$((ERRORS_FOUND + 1))
    echo "IMPORT ERROR: utils package" >> "$RESULTS_FILE"
}

echo "  Testing utils.logging_config..."
python3 -c "
import sys
sys.path.insert(0, '/home/user/AlphaGEX')
try:
    from utils.logging_config import get_logger, log_error_with_context
    print('    utils.logging_config: OK')
except Exception as e:
    print(f'    utils.logging_config: FAILED - {e}')
    sys.exit(1)
" 2>&1 || {
    echo -e "  ${RED}✗${NC} utils.logging_config failed to import"
    ERRORS_FOUND=$((ERRORS_FOUND + 1))
    echo "IMPORT ERROR: utils.logging_config" >> "$RESULTS_FILE"
}

echo ""

# Test each route file
for route in "${EXPECTED_ROUTES[@]}"; do
    if [ "$route" == "__init__.py" ]; then
        continue
    fi

    FILES_CHECKED=$((FILES_CHECKED + 1))
    route_name="${route%.py}"

    echo "  [$FILES_CHECKED/20] Testing $route..."

    # Create a test script that simulates how Render loads the module
    TEST_OUTPUT=$(python3 -c "
import sys
import os

# Simulate Render environment - set PYTHONPATH to project root
sys.path.insert(0, '/home/user/AlphaGEX')
os.chdir('/home/user/AlphaGEX')

# Try to import the route module
try:
    # First, try importing dependencies the route might need
    import importlib.util

    # Load the route file and check for syntax/import errors
    route_path = 'backend/api/routes/$route'
    spec = importlib.util.spec_from_file_location('$route_name', route_path)
    module = importlib.util.module_from_spec(spec)

    # This will execute the module and catch any import errors
    spec.loader.exec_module(module)

    # Check if router exists
    if hasattr(module, 'router'):
        print('OK - router found')
    else:
        print('WARNING - no router attribute')

except SyntaxError as e:
    print(f'SYNTAX ERROR: {e}')
    sys.exit(1)
except ImportError as e:
    print(f'IMPORT ERROR: {e}')
    sys.exit(1)
except Exception as e:
    print(f'ERROR: {type(e).__name__}: {e}')
    sys.exit(1)
" 2>&1)

    if echo "$TEST_OUTPUT" | grep -q "^OK"; then
        echo -e "    ${GREEN}✓${NC} $TEST_OUTPUT"
    elif echo "$TEST_OUTPUT" | grep -q "^WARNING"; then
        echo -e "    ${YELLOW}⚠${NC} $TEST_OUTPUT"
        WARNINGS_FOUND=$((WARNINGS_FOUND + 1))
        echo "WARNING: $route - $TEST_OUTPUT" >> "$RESULTS_FILE"
    else
        echo -e "    ${RED}✗${NC} $TEST_OUTPUT"
        ERRORS_FOUND=$((ERRORS_FOUND + 1))
        echo "ERROR: $route - $TEST_OUTPUT" >> "$RESULTS_FILE"
    fi
done

echo ""

# =============================================================================
# PART 4: Test full import chain (how main.py loads routes)
# =============================================================================
echo -e "${BLUE}PART 4: Testing full import chain (simulating main.py)...${NC}"
echo ""

CHAIN_OUTPUT=$(python3 -c "
import sys
import os

# Set up paths exactly like main.py does
from pathlib import Path
parent_dir = Path('/home/user/AlphaGEX')
sys.path.insert(0, str(parent_dir))
os.chdir(str(parent_dir))

print('Testing import chain...')

# Test 1: Import routes package (this is what fails on Render)
try:
    from backend.api.routes import (
        vix_routes,
        spx_routes,
        system_routes,
        trader_routes,
        backtest_routes,
        database_routes,
        gex_routes,
        gamma_routes,
        core_routes,
        optimizer_routes,
        ai_routes,
        probability_routes,
        notification_routes,
        misc_routes,
        alerts_routes,
        setups_routes,
        scanner_routes,
        autonomous_routes,
        psychology_routes,
        ai_intelligence_routes,
    )
    print('  Routes package: OK')
except Exception as e:
    print(f'  Routes package: FAILED - {type(e).__name__}: {e}')
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 2: Check each router exists
routes_to_check = [
    ('vix_routes', vix_routes),
    ('spx_routes', spx_routes),
    ('system_routes', system_routes),
    ('trader_routes', trader_routes),
    ('backtest_routes', backtest_routes),
    ('database_routes', database_routes),
    ('gex_routes', gex_routes),
    ('gamma_routes', gamma_routes),
    ('core_routes', core_routes),
    ('optimizer_routes', optimizer_routes),
    ('ai_routes', ai_routes),
    ('probability_routes', probability_routes),
    ('notification_routes', notification_routes),
    ('misc_routes', misc_routes),
    ('alerts_routes', alerts_routes),
    ('setups_routes', setups_routes),
    ('scanner_routes', scanner_routes),
    ('autonomous_routes', autonomous_routes),
    ('psychology_routes', psychology_routes),
    ('ai_intelligence_routes', ai_intelligence_routes),
]

all_ok = True
for name, module in routes_to_check:
    if hasattr(module, 'router'):
        print(f'  {name}.router: OK')
    else:
        print(f'  {name}.router: MISSING')
        all_ok = False

if all_ok:
    print('\\nALL ROUTES LOADED SUCCESSFULLY!')
else:
    print('\\nSOME ROUTES HAVE ISSUES')
    sys.exit(1)
" 2>&1)

echo "$CHAIN_OUTPUT"

if echo "$CHAIN_OUTPUT" | grep -q "FAILED\|MISSING"; then
    ERRORS_FOUND=$((ERRORS_FOUND + 1))
    echo "CHAIN ERROR: Full import chain failed" >> "$RESULTS_FILE"
fi

echo ""

# =============================================================================
# PART 5: Line-by-line import analysis for each route file
# =============================================================================
echo -e "${BLUE}PART 5: Detailed import analysis (line-by-line)...${NC}"
echo ""

for route in "${EXPECTED_ROUTES[@]}"; do
    if [ "$route" == "__init__.py" ]; then
        continue
    fi

    echo "  Analyzing imports in $route..."

    # Extract all import statements
    IMPORTS=$(grep -n "^import \|^from " "$ROUTE_DIR/$route" 2>/dev/null || echo "")

    if [ -z "$IMPORTS" ]; then
        echo "    No imports found"
        continue
    fi

    # Check each import
    while IFS= read -r line; do
        LINE_NUM=$(echo "$line" | cut -d: -f1)
        IMPORT_STMT=$(echo "$line" | cut -d: -f2-)

        # Extract module name
        if echo "$IMPORT_STMT" | grep -q "^from "; then
            MODULE=$(echo "$IMPORT_STMT" | sed 's/^from \([^ ]*\).*/\1/')
        else
            MODULE=$(echo "$IMPORT_STMT" | sed 's/^import \([^ ,]*\).*/\1/')
        fi

        # Test if it's a standard library or installed package
        IS_CUSTOM=false
        case "$MODULE" in
            os|sys|re|time|math|json|datetime|typing|pathlib|asyncio|threading|collections)
                STATUS="stdlib"
                ;;
            fastapi|fastapi.*|pydantic|uvicorn|psycopg2|psycopg2.*|requests|zoneinfo)
                STATUS="package"
                ;;
            database_adapter|core_classes_and_engines|utils|utils.*|core|core.*|backend.*|data.*|db.*)
                IS_CUSTOM=true
                # Test the actual import
                TEST_RESULT=$(python3 -c "
import sys
sys.path.insert(0, '/home/user/AlphaGEX')
try:
    $IMPORT_STMT
    print('OK')
except Exception as e:
    print(f'FAILED: {e}')
" 2>&1)
                if echo "$TEST_RESULT" | grep -q "^OK"; then
                    STATUS="custom-ok"
                else
                    STATUS="custom-FAILED"
                    echo -e "    ${RED}Line $LINE_NUM: $IMPORT_STMT${NC}"
                    echo -e "    ${RED}  -> $TEST_RESULT${NC}"
                    echo "IMPORT FAILED: $route:$LINE_NUM - $IMPORT_STMT - $TEST_RESULT" >> "$RESULTS_FILE"
                    ERRORS_FOUND=$((ERRORS_FOUND + 1))
                fi
                ;;
            *)
                STATUS="unknown"
                ;;
        esac

        if [ "$IS_CUSTOM" = false ]; then
            echo -e "    ${GREEN}Line $LINE_NUM: $MODULE ($STATUS)${NC}"
        elif [ "$STATUS" = "custom-ok" ]; then
            echo -e "    ${GREEN}Line $LINE_NUM: $MODULE (custom-ok)${NC}"
        fi

    done <<< "$IMPORTS"

    echo ""
done

# =============================================================================
# PART 6: Check for any syntax errors in all Python files
# =============================================================================
echo -e "${BLUE}PART 6: Checking for syntax errors in all route files...${NC}"
echo ""

for route in "${EXPECTED_ROUTES[@]}"; do
    SYNTAX_CHECK=$(python3 -m py_compile "$ROUTE_DIR/$route" 2>&1)
    if [ $? -eq 0 ]; then
        echo -e "  ${GREEN}✓${NC} $route - syntax OK"
    else
        echo -e "  ${RED}✗${NC} $route - SYNTAX ERROR:"
        echo "    $SYNTAX_CHECK"
        ERRORS_FOUND=$((ERRORS_FOUND + 1))
        echo "SYNTAX ERROR: $route - $SYNTAX_CHECK" >> "$RESULTS_FILE"
    fi
done

echo ""

# =============================================================================
# SUMMARY
# =============================================================================
echo "============================================================================="
echo "  SUMMARY"
echo "============================================================================="
echo ""
echo "  Files checked: $FILES_CHECKED"
echo -e "  Errors found: ${RED}$ERRORS_FOUND${NC}"
echo -e "  Warnings found: ${YELLOW}$WARNINGS_FOUND${NC}"
echo ""

if [ $ERRORS_FOUND -gt 0 ]; then
    echo -e "${RED}ERRORS FOUND! Details:${NC}"
    echo ""
    cat "$RESULTS_FILE"
    echo ""
    exit 1
else
    echo -e "${GREEN}ALL CHECKS PASSED!${NC}"
    exit 0
fi
