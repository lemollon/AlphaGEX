#!/bin/bash
###############################################################################
# Run Enhanced Backtest Optimizer - PRODUCTION MODE
# Populates strategy optimization tables
###############################################################################

set -e  # Exit on error

echo "================================================================================"
echo "🧪 ENHANCED BACKTEST OPTIMIZER - PRODUCTION MODE"
echo "================================================================================"
echo ""
echo "⚠️  WARNING: This will write to your PRODUCTION database!"
echo ""
echo "Configuration:"
echo "  Symbol: SPY"
echo "  Days: 365"
echo "  Estimated time: 5 minutes"
echo ""
echo "This will populate:"
echo "  • strike_performance (best strikes for each pattern)"
echo "  • dte_performance (optimal days to expiration)"
echo "  • greeks_performance (Greeks correlation with P&L)"
echo "  • spread_width_performance (optimal spread widths)"
echo ""
echo "Result: AUTO-OPTIMIZATION of trading strategies"
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
echo "🚀 Starting optimizer..."
echo ""

# Run optimizer
python3 enhanced_backtest_optimizer.py --symbol SPY --days 365

echo ""
echo "================================================================================"
echo "✅ OPTIMIZATION COMPLETE!"
echo "================================================================================"
echo ""
echo "Next Steps:"
echo "  1. Run data quality dashboard: python3 data_quality_dashboard.py"
echo "  2. Check populated tables in your database"
echo "  3. Re-run monthly to update strategies: ./run_optimizer.sh"
echo ""
echo "Your strategies will now AUTO-OPTIMIZE based on historical performance!"
echo ""
echo "================================================================================"
