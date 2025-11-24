#!/bin/bash
###############################################################################
# Run Polygon.io OI Backfill - PRODUCTION MODE
# This WILL write to your production database!
###############################################################################

set -e  # Exit on error

echo "================================================================================"
echo "📊 POLYGON.IO OPEN INTEREST BACKFILL - PRODUCTION MODE"
echo "================================================================================"
echo ""
echo "⚠️  WARNING: This will write to your PRODUCTION database!"
echo ""
echo "Configuration:"
echo "  Symbol: SPY"
echo "  Days: 90"
echo "  Rate limit: 0.6s (Options Developer tier - 100+ req/min)"
echo "  Estimated time: 5-10 minutes"
echo ""
echo "This will replace synthetic data with REAL open interest from Polygon.io"
echo ""
echo "================================================================================"
echo ""

# Confirm before proceeding
read -p "Continue? (yes/no): " confirm
if [ "$confirm" != "yes" ]; then
    echo "❌ Cancelled"
    exit 0
fi

echo ""
echo "🚀 Starting backfill..."
echo ""

# Run backfill
python3 polygon_oi_backfill.py --symbol SPY --days 90

echo ""
echo "================================================================================"
echo "✅ BACKFILL COMPLETE!"
echo "================================================================================"
echo ""
echo "Next Steps:"
echo "  1. Run data quality dashboard to verify: python3 data_quality_dashboard.py"
echo "  2. Run optimizer to populate strategy tables: ./run_optimizer.sh"
echo "  3. Schedule daily snapshots: crontab -e"
echo "     Add: 30 16 * * 1-5 cd $(pwd) && python3 historical_oi_snapshot_job.py >> logs/oi.log 2>&1"
echo ""
echo "================================================================================"
