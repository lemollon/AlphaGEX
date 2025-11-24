#!/bin/bash
###############################################################################
# AlphaGEX Feature Test Suite
# Tests all new features safely (no production database writes)
###############################################################################

set -e  # Exit on error

echo "================================================================================"
echo "🧪 ALPHAGEX FEATURE TEST SUITE"
echo "================================================================================"
echo "This script tests all new features in SAFE MODE (no database writes)"
echo ""
echo "Tests:"
echo "  1. Data Quality Dashboard"
echo "  2. Historical OI Snapshot (test mode)"
echo "  3. Polygon OI Backfill (test mode, 1 day sample)"
echo "  4. Enhanced Backtest Optimizer (test mode)"
echo ""
echo "================================================================================"
echo ""

# Check if we're in the right directory
if [ ! -f "config_and_database.py" ]; then
    echo "❌ Error: Must run from AlphaGEX root directory"
    exit 1
fi

# Test 1: Data Quality Dashboard (Quick Check)
echo ""
echo "================================================================================"
echo "TEST 1: Data Quality Dashboard - Quick Status"
echo "================================================================================"
echo ""
python3 data_quality_dashboard.py --quick
echo ""
read -p "✅ Press Enter to continue to next test..."

# Test 2: Data Quality Dashboard (Full Report)
echo ""
echo "================================================================================"
echo "TEST 2: Data Quality Dashboard - Full Report"
echo "================================================================================"
echo ""
python3 data_quality_dashboard.py
echo ""
read -p "✅ Press Enter to continue to next test..."

# Test 3: Historical OI Snapshot (TEST MODE - No DB Writes)
echo ""
echo "================================================================================"
echo "TEST 3: Historical OI Snapshot Job (Test Mode - SPY Only)"
echo "================================================================================"
echo ""
echo "⚠️  Running in TEST MODE - No database writes will occur"
echo ""
python3 historical_oi_snapshot_job.py SPY --test
echo ""
read -p "✅ Press Enter to continue to next test..."

# Test 4: Polygon OI Backfill (TEST MODE - 1 Day Sample)
echo ""
echo "================================================================================"
echo "TEST 4: Polygon OI Backfill (Test Mode - 1 Day Sample)"
echo "================================================================================"
echo ""
echo "⚠️  Running in TEST MODE - No database writes will occur"
echo "This will test fetching options data for 1 day only (fast test)"
echo ""
python3 polygon_oi_backfill.py --symbol SPY --days 1 --test
echo ""
read -p "✅ Press Enter to continue to next test..."

# Test 5: Enhanced Backtest Optimizer (TEST MODE)
echo ""
echo "================================================================================"
echo "TEST 5: Enhanced Backtest Optimizer (Test Mode - 30 Days Sample)"
echo "================================================================================"
echo ""
echo "⚠️  Running in TEST MODE - No database writes will occur"
echo ""
python3 enhanced_backtest_optimizer.py --symbol SPY --days 30 --test
echo ""

# Summary
echo ""
echo "================================================================================"
echo "🎉 ALL TESTS COMPLETED!"
echo "================================================================================"
echo ""
echo "Results:"
echo "  ✅ Data Quality Dashboard - Working"
echo "  ✅ Historical OI Snapshot - Working (test mode)"
echo "  ✅ Polygon OI Backfill - Working (test mode)"
echo "  ✅ Enhanced Optimizer - Working (test mode)"
echo ""
echo "Next Steps:"
echo "  1. Review the output above to ensure everything looks correct"
echo "  2. If satisfied, run the PRODUCTION scripts:"
echo "     - ./run_backfill.sh (to populate real data)"
echo "     - ./run_optimizer.sh (to populate optimization tables)"
echo ""
echo "================================================================================"
