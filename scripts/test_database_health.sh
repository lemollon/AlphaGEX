#!/bin/bash
#
# ============================================================================
# ALPHAGEX COMPREHENSIVE DATABASE HEALTH TEST
# ============================================================================
# Tests ALL tables, ALL pipelines, and ALL preventive measures
#
# Run: chmod +x scripts/test_database_health.sh && ./scripts/test_database_health.sh
# ============================================================================

set +e  # Don't exit on first error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Counters
PASSED=0
FAILED=0
WARNINGS=0

# Project root
PROJECT_ROOT="${PROJECT_ROOT:-$(pwd)}"
API_BASE="${API_BASE:-http://localhost:8000}"

# Helper functions
pass() {
    echo -e "  ${GREEN}✓${NC} $1"
    PASSED=$((PASSED+1))
}

fail() {
    echo -e "  ${RED}✗${NC} $1"
    FAILED=$((FAILED+1))
}

warn() {
    echo -e "  ${YELLOW}⚠${NC} $1"
    WARNINGS=$((WARNINGS+1))
}

info() {
    echo -e "  ${CYAN}ℹ${NC} $1"
}

header() {
    echo ""
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}  $1${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

# ============================================================================
# START
# ============================================================================

echo ""
echo -e "${CYAN}╔══════════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║           ALPHAGEX DATABASE HEALTH TEST SUITE                        ║${NC}"
echo -e "${CYAN}║           Testing All Tables, Pipelines & Preventive Measures        ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo "  Started: $(date)"
echo "  Project: $PROJECT_ROOT"
echo ""

# ============================================================================
# PART 1: SCHEMA VALIDATION
# ============================================================================

header "PART 1: SCHEMA VALIDATION"

# Test 1.1: Main schema file exists
if [ -f "$PROJECT_ROOT/db/config_and_database.py" ]; then
    pass "Main schema file exists: db/config_and_database.py"
else
    fail "Main schema file NOT FOUND: db/config_and_database.py"
fi

# Test 1.2: Schema validation script exists
if [ -f "$PROJECT_ROOT/scripts/validate_schema.py" ]; then
    pass "Schema validation script exists"
else
    fail "Schema validation script NOT FOUND"
fi

# Test 1.3: SCHEMA_REGISTRY.md exists
if [ -f "$PROJECT_ROOT/docs/SCHEMA_REGISTRY.md" ]; then
    pass "SCHEMA_REGISTRY.md documentation exists"
else
    fail "SCHEMA_REGISTRY.md NOT FOUND"
fi

# Test 1.4: Run schema validation
if [ -f "$PROJECT_ROOT/scripts/validate_schema.py" ]; then
    echo ""
    info "Running schema validation script..."
    python3 "$PROJECT_ROOT/scripts/validate_schema.py" > /tmp/schema_validation.log 2>&1
    VALIDATION_EXIT=$?

    if [ $VALIDATION_EXIT -eq 0 ]; then
        pass "Schema validation PASSED (no errors)"
    elif [ $VALIDATION_EXIT -eq 2 ]; then
        warn "Schema validation passed with WARNINGS"
        grep "WARN\|WARNING" /tmp/schema_validation.log | head -5
    else
        fail "Schema validation FAILED"
        grep "ERROR\|FAIL" /tmp/schema_validation.log | head -5
    fi
fi

# Test 1.5: Count tables in main schema
MAIN_TABLES=$(grep -c "CREATE TABLE IF NOT EXISTS" "$PROJECT_ROOT/db/config_and_database.py" 2>/dev/null || echo "0")
if [ "$MAIN_TABLES" -gt 50 ]; then
    pass "Main schema has $MAIN_TABLES tables (consolidated)"
else
    warn "Main schema only has $MAIN_TABLES tables (expected 50+)"
fi

# Test 1.6: Check for external CREATE TABLE statements
EXTERNAL_CREATES=$(grep -r "CREATE TABLE IF NOT EXISTS" --include="*.py" "$PROJECT_ROOT" 2>/dev/null | grep -v "config_and_database.py" | grep -v "validate_schema.py" | grep -v "__pycache__" | wc -l)
if [ "$EXTERNAL_CREATES" -eq 0 ]; then
    pass "No external CREATE TABLE statements found"
else
    warn "$EXTERNAL_CREATES external CREATE TABLE statements found (should be removed)"
    grep -r "CREATE TABLE IF NOT EXISTS" --include="*.py" "$PROJECT_ROOT" 2>/dev/null | grep -v "config_and_database.py" | grep -v "validate_schema.py" | grep -v "__pycache__" | head -3
fi

# ============================================================================
# PART 2: DATABASE CONNECTIVITY
# ============================================================================

header "PART 2: DATABASE CONNECTIVITY"

# Test 2.1: DATABASE_URL is set
if [ -n "$DATABASE_URL" ]; then
    pass "DATABASE_URL environment variable is set"
else
    warn "DATABASE_URL not set (using default)"
fi

# Test 2.2: Python database connection test
python3 -c "
from database_adapter import get_connection
conn = get_connection()
cursor = conn.cursor()
cursor.execute('SELECT 1')
conn.close()
print('OK')
" > /tmp/db_test.log 2>&1

if grep -q "OK" /tmp/db_test.log; then
    pass "Database connection successful"
else
    fail "Database connection FAILED"
    cat /tmp/db_test.log
fi

# ============================================================================
# PART 3: TABLE EXISTENCE VERIFICATION
# ============================================================================

header "PART 3: TABLE EXISTENCE VERIFICATION (All 77 Tables)"

# Core Trading Tables
CORE_TABLES="autonomous_config autonomous_open_positions autonomous_closed_trades autonomous_trade_log autonomous_trade_activity autonomous_live_status autonomous_equity_snapshots trading_decisions trades positions"

# Market Data Tables
MARKET_TABLES="gex_history gamma_history gamma_daily_summary gex_levels gex_snapshots_detailed gamma_strike_history market_data historical_open_interest regime_signals regime_classifications spy_correlation gamma_correlation gex_change_log"

# AI/ML Tables
AI_TABLES="ai_predictions ai_performance ai_recommendations pattern_learning ml_predictions probability_predictions ai_analysis_history"

# Backtest Tables
BACKTEST_TABLES="backtest_results backtest_summary backtest_trades spx_wheel_backtest_runs spx_wheel_backtest_equity spx_wheel_backtest_trades sucker_statistics psychology_analysis"

# User Feature Tables
USER_TABLES="alerts alert_history trade_setups conversations push_subscriptions wheel_cycles wheel_legs wheel_activity_log vix_hedge_signals vix_hedge_positions"

# System Tables
SYSTEM_TABLES="background_jobs scheduler_state data_collection_log performance recommendations"

# Unified Engine Tables
UNIFIED_TABLES="unified_positions unified_trades strategy_competition"

# Validation Tables
VALIDATION_TABLES="paper_signals paper_outcomes"

# Data Collection Tables
DATA_TABLES="greeks_snapshots vix_term_structure options_flow market_snapshots position_sizing_history price_history options_chain_snapshots options_collection_log"

ALL_TABLES="$CORE_TABLES $MARKET_TABLES $AI_TABLES $BACKTEST_TABLES $USER_TABLES $SYSTEM_TABLES $UNIFIED_TABLES $VALIDATION_TABLES $DATA_TABLES"

TABLE_COUNT=0
TABLE_EXISTS=0
TABLE_MISSING=0

for table in $ALL_TABLES; do
    TABLE_COUNT=$((TABLE_COUNT+1))

    EXISTS=$(python3 -c "
from database_adapter import get_connection
conn = get_connection()
cursor = conn.cursor()
cursor.execute(\"\"\"
    SELECT EXISTS (
        SELECT FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = '$table'
    )
\"\"\")
result = cursor.fetchone()[0]
conn.close()
print('yes' if result else 'no')
" 2>/dev/null)

    if [ "$EXISTS" = "yes" ]; then
        TABLE_EXISTS=$((TABLE_EXISTS+1))
    else
        TABLE_MISSING=$((TABLE_MISSING+1))
        warn "Table missing: $table"
    fi
done

if [ $TABLE_MISSING -eq 0 ]; then
    pass "All $TABLE_COUNT tables exist"
else
    fail "$TABLE_MISSING tables missing out of $TABLE_COUNT"
fi

info "Tables found: $TABLE_EXISTS / $TABLE_COUNT"

# ============================================================================
# PART 4: TABLE DATA VERIFICATION
# ============================================================================

header "PART 4: TABLE DATA VERIFICATION"

# Check populated tables have data
POPULATED_TABLES="gex_history regime_signals autonomous_open_positions autonomous_closed_trades autonomous_trade_log backtest_results"

for table in $POPULATED_TABLES; do
    COUNT=$(python3 -c "
from database_adapter import get_connection
conn = get_connection()
cursor = conn.cursor()
cursor.execute('SELECT COUNT(*) FROM $table')
result = cursor.fetchone()[0]
conn.close()
print(result)
" 2>/dev/null)

    if [ -n "$COUNT" ] && [ "$COUNT" -gt 0 ]; then
        pass "$table has $COUNT records"
    else
        warn "$table is empty (expected data)"
    fi
done

# ============================================================================
# PART 5: TIMESTAMP COLUMN VERIFICATION
# ============================================================================

header "PART 5: TIMESTAMP COLUMN VERIFICATION"

# Tables that must have timestamp columns
TIMESTAMP_REQUIRED="gex_history gamma_history regime_signals autonomous_live_status autonomous_equity_snapshots data_collection_log"

for table in $TIMESTAMP_REQUIRED; do
    HAS_TS=$(python3 -c "
from database_adapter import get_connection
conn = get_connection()
cursor = conn.cursor()
cursor.execute(\"\"\"
    SELECT column_name FROM information_schema.columns
    WHERE table_name = '$table'
    AND column_name IN ('timestamp', 'created_at', 'date')
\"\"\")
result = cursor.fetchone()
conn.close()
print('yes' if result else 'no')
" 2>/dev/null)

    if [ "$HAS_TS" = "yes" ]; then
        pass "$table has timestamp column"
    else
        fail "$table MISSING timestamp column"
    fi
done

# ============================================================================
# PART 6: API ENDPOINT VERIFICATION
# ============================================================================

header "PART 6: API ENDPOINT VERIFICATION"

# Check if API is running
API_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$API_BASE/health" 2>/dev/null || echo "000")

if [ "$API_STATUS" = "200" ]; then
    pass "API is running at $API_BASE"

    # Test table-freshness endpoint
    FRESHNESS=$(curl -s "$API_BASE/api/database/table-freshness" 2>/dev/null)
    if echo "$FRESHNESS" | grep -q "tables"; then
        TABLE_COUNT=$(echo "$FRESHNESS" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('tables',{})))" 2>/dev/null || echo "0")
        pass "/api/database/table-freshness returns $TABLE_COUNT tables"
    else
        fail "/api/database/table-freshness endpoint error"
    fi

    # Test database stats endpoint
    STATS=$(curl -s "$API_BASE/api/database/stats" 2>/dev/null)
    if echo "$STATS" | grep -q "success"; then
        pass "/api/database/stats endpoint working"
    else
        fail "/api/database/stats endpoint error"
    fi

    # Test system health endpoint
    HEALTH=$(curl -s "$API_BASE/api/system/health" 2>/dev/null)
    if echo "$HEALTH" | grep -q "overall_status"; then
        pass "/api/system/health endpoint working"
    else
        fail "/api/system/health endpoint error"
    fi
else
    warn "API not running at $API_BASE (skipping API tests)"
    info "Start API with: python backend/main.py"
fi

# ============================================================================
# PART 7: DATA COLLECTOR VERIFICATION
# ============================================================================

header "PART 7: DATA COLLECTOR VERIFICATION"

# Check DataCollector methods exist
DATACOLLECTOR_FILE="$PROJECT_ROOT/services/data_collector.py"

if [ -f "$DATACOLLECTOR_FILE" ]; then
    METHODS="store_gex store_prices store_greeks store_vix_term_structure store_options_flow store_ai_analysis store_market_snapshot store_position_sizing"

    for method in $METHODS; do
        if grep -q "def $method" "$DATACOLLECTOR_FILE"; then
            pass "DataCollector.$method() exists"
        else
            fail "DataCollector.$method() NOT FOUND"
        fi
    done
else
    fail "DataCollector file not found"
fi

# ============================================================================
# PART 8: PREVENTIVE MEASURES VERIFICATION
# ============================================================================

header "PART 8: PREVENTIVE MEASURES VERIFICATION"

# 8.1: Schema validation script
if [ -f "$PROJECT_ROOT/scripts/validate_schema.py" ]; then
    pass "Preventive: Schema validation script exists"
else
    fail "Preventive: Schema validation script MISSING"
fi

# 8.2: Schema registry documentation
if [ -f "$PROJECT_ROOT/docs/SCHEMA_REGISTRY.md" ]; then
    REGISTRY_TABLES=$(grep -c "^\| \`" "$PROJECT_ROOT/docs/SCHEMA_REGISTRY.md" 2>/dev/null || echo "0")
    pass "Preventive: SCHEMA_REGISTRY.md has $REGISTRY_TABLES table entries"
else
    fail "Preventive: SCHEMA_REGISTRY.md MISSING"
fi

# 8.3: Main schema file is authoritative
CONSOLIDATED=$(grep -c "CONSOLIDATED TABLES" "$PROJECT_ROOT/db/config_and_database.py" 2>/dev/null || echo "0")
if [ "$CONSOLIDATED" -gt 0 ]; then
    pass "Preventive: Main schema has CONSOLIDATED TABLES section"
else
    warn "Preventive: Main schema missing CONSOLIDATED TABLES section"
fi

# 8.4: Table freshness endpoint is comprehensive
if [ -f "$PROJECT_ROOT/backend/api/routes/database_routes.py" ]; then
    FRESHNESS_TABLES=$(grep -c '(".*", ".*", ' "$PROJECT_ROOT/backend/api/routes/database_routes.py" 2>/dev/null || echo "0")
    if [ "$FRESHNESS_TABLES" -gt 50 ]; then
        pass "Preventive: Table freshness endpoint checks $FRESHNESS_TABLES tables"
    else
        warn "Preventive: Table freshness only checks $FRESHNESS_TABLES tables (expected 50+)"
    fi
fi

# 8.5: No orphaned tables (scanner_runs, scanner_results)
ORPHANED_SCANNER=$(grep -r "scanner_runs\|scanner_results" --include="*.py" "$PROJECT_ROOT" 2>/dev/null | grep -v "__pycache__" | grep -v "validate_schema" | grep -v "test_" | wc -l)
if [ "$ORPHANED_SCANNER" -lt 5 ]; then
    pass "Preventive: scanner_runs/scanner_results references minimal"
else
    warn "Preventive: $ORPHANED_SCANNER references to orphaned scanner tables"
fi

# 8.6: No SQLite references in main code
SQLITE_REFS=$(grep -r "sqlite3\|\.db\|gex_copilot.db\|autonomous_trader.db" --include="*.py" "$PROJECT_ROOT" 2>/dev/null | grep -v "__pycache__" | grep -v "test_" | grep -v "migration" | grep -v "#" | wc -l)
if [ "$SQLITE_REFS" -lt 5 ]; then
    pass "Preventive: Minimal SQLite references ($SQLITE_REFS)"
else
    warn "Preventive: $SQLITE_REFS SQLite references found (should be removed)"
fi

# ============================================================================
# PART 9: INDEX VERIFICATION
# ============================================================================

header "PART 9: INDEX VERIFICATION"

# Count indexes in main schema
INDEX_COUNT=$(grep -c "CREATE INDEX IF NOT EXISTS" "$PROJECT_ROOT/db/config_and_database.py" 2>/dev/null || echo "0")
if [ "$INDEX_COUNT" -gt 100 ]; then
    pass "Main schema has $INDEX_COUNT index definitions"
else
    warn "Main schema only has $INDEX_COUNT indexes (expected 100+)"
fi

# ============================================================================
# SUMMARY
# ============================================================================

echo ""
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}  TEST SUMMARY${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

TOTAL=$((PASSED + FAILED + WARNINGS))

echo -e "  ┌─────────────────────────────┐"
echo -e "  │ ${GREEN}✓ Passed:   $PASSED${NC}$(printf '%*s' $((14 - ${#PASSED})) '')│"
echo -e "  │ ${RED}✗ Failed:   $FAILED${NC}$(printf '%*s' $((14 - ${#FAILED})) '')│"
echo -e "  │ ${YELLOW}⚠ Warnings: $WARNINGS${NC}$(printf '%*s' $((14 - ${#WARNINGS})) '')│"
echo -e "  │ ─────────────────────────── │"
echo -e "  │ Total:      $TOTAL$(printf '%*s' $((14 - ${#TOTAL})) '')│"
echo -e "  └─────────────────────────────┘"
echo ""

if [ $FAILED -eq 0 ]; then
    if [ $WARNINGS -eq 0 ]; then
        echo -e "${GREEN}╔══════════════════════════════════════════════════════════════════════╗${NC}"
        echo -e "${GREEN}║  ✅ ALL TESTS PASSED                                                 ║${NC}"
        echo -e "${GREEN}╚══════════════════════════════════════════════════════════════════════╝${NC}"
        exit 0
    else
        echo -e "${YELLOW}╔══════════════════════════════════════════════════════════════════════╗${NC}"
        echo -e "${YELLOW}║  ⚠️  TESTS PASSED WITH WARNINGS - Review above                       ║${NC}"
        echo -e "${YELLOW}╚══════════════════════════════════════════════════════════════════════╝${NC}"
        exit 0
    fi
else
    echo -e "${RED}╔══════════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${RED}║  ❌ SOME TESTS FAILED - Review errors above                          ║${NC}"
    echo -e "${RED}╚══════════════════════════════════════════════════════════════════════╝${NC}"
    exit 1
fi
