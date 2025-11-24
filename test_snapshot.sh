#!/bin/bash
###############################################################################
# Test Daily OI Snapshot Job
# Runs in TEST MODE (no database writes) to verify Polygon.io connection
###############################################################################

echo "================================================================================"
echo "📸 TEST DAILY OI SNAPSHOT JOB"
echo "================================================================================"
echo ""
echo "This will test fetching REAL open interest data from Polygon.io"
echo "Mode: TEST (no database writes)"
echo ""
echo "Testing with: SPY"
echo ""
echo "================================================================================"
echo ""

python3 historical_oi_snapshot_job.py SPY --test

echo ""
echo "================================================================================"
echo "✅ TEST COMPLETE!"
echo "================================================================================"
echo ""
echo "If you saw REAL open interest data above, your Polygon.io API is working!"
echo ""
echo "To run in production (writes to database):"
echo "  python3 historical_oi_snapshot_job.py SPY"
echo ""
echo "To run for multiple symbols:"
echo "  python3 historical_oi_snapshot_job.py SPY QQQ IWM"
echo ""
echo "To schedule daily at 4:30 PM ET:"
echo "  crontab -e"
echo "  Add: 30 16 * * 1-5 cd $(pwd) && python3 historical_oi_snapshot_job.py >> logs/oi.log 2>&1"
echo ""
echo "================================================================================"
