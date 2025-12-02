#!/bin/bash
# MASTER VERIFICATION SCRIPT
# Runs ALL checks and tests in sequence

echo "=============================================="
echo "ALPHAGEX FULL SYSTEM VERIFICATION"
echo "=============================================="
echo "This script will:"
echo "  1. Verify all systems and credentials"
echo "  2. Check database status"
echo "  3. Run SPX backtest (short period for testing)"
echo "  4. Show results"
echo ""
echo "Press Ctrl+C to cancel, or wait 5 seconds to continue..."
sleep 5

cd /home/user/AlphaGEX/scripts

echo ""
echo "=============================================="
echo "STEP 1: SYSTEM VERIFICATION"
echo "=============================================="
./verify_all_systems.sh

echo ""
echo "=============================================="
echo "STEP 2: DATABASE STATUS"
echo "=============================================="
./check_database.sh

echo ""
echo "=============================================="
echo "STEP 3: SHORT SPX BACKTEST (3 months)"
echo "=============================================="
# Run a 3-month backtest as a test
END_DATE=$(date +%Y-%m-%d)
START_DATE=$(date -d "3 months ago" +%Y-%m-%d 2>/dev/null || date -v-3m +%Y-%m-%d)

./run_spx_backtest.sh "$START_DATE" "$END_DATE" 100000

echo ""
echo "=============================================="
echo "VERIFICATION COMPLETE"
echo "=============================================="
echo ""
echo "Next steps:"
echo "  1. Review the backtest Excel file for verification"
echo "  2. Run full backtest: ./run_spx_backtest.sh 2022-01-01"
echo "  3. Start data collection: python data/option_chain_collector.py --all"
echo ""
