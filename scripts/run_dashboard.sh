#!/bin/bash
# ==========================================================================
# SPX WHEEL TRADING DASHBOARD
# ==========================================================================
#
# Starts the web dashboard where you can SEE everything:
# - Every trade with full details
# - Price source for each trade (REAL vs ESTIMATED)
# - Current open positions
# - Equity curve
# - Data quality percentage
# - Live vs backtest comparison
#
# Usage:
#   ./run_dashboard.sh
#
# Then open: http://localhost:5000
# ==========================================================================

echo "==========================================================================="
echo "SPX WHEEL TRADING DASHBOARD"
echo "==========================================================================="
echo ""

# Check environment
if [ -z "$DATABASE_URL" ]; then
    echo "ERROR: DATABASE_URL not set"
    echo "The dashboard needs database access to show your trades."
    exit 1
fi

cd /home/user/AlphaGEX

# Check if Flask is installed
if ! python3 -c "import flask" 2>/dev/null; then
    echo "Installing Flask..."
    pip install flask
fi

echo "Starting dashboard..."
echo ""
echo "Open in your browser: http://localhost:5000"
echo ""
echo "Dashboard shows:"
echo "  - Every trade with full details"
echo "  - Price source (POLYGON/TRADIER/ESTIMATED)"
echo "  - Data quality percentage"
echo "  - Equity curve"
echo "  - Live vs backtest comparison"
echo ""
echo "Press Ctrl+C to stop"
echo "==========================================================================="
echo ""

python3 dashboard/app.py
