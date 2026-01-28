#!/bin/bash
# Quick test script for equity endpoints
# Run from Render shell: bash scripts/quick_equity_test.sh

echo "============================================"
echo "ALPHAGEX QUICK EQUITY TEST"
echo "============================================"
echo "Date: $(date)"
echo ""

# Run Python tests
echo "Running data consistency check..."
python scripts/test_data_consistency.py

echo ""
echo "Running daily P&L bug verification..."
python scripts/test_daily_pnl_bug.py

echo ""
echo "Running equity endpoint tests..."
python scripts/test_equity_endpoints.py

echo ""
echo "============================================"
echo "QUICK TEST COMPLETE"
echo "============================================"
