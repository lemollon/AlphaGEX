#!/bin/bash
# Run SPX Premium Selling Backtest with REAL data
# This traces the path from $1M starting capital using Polygon historical data

echo "=============================================="
echo "SPX PREMIUM SELLING BACKTEST"
echo "=============================================="
echo "Starting capital: \$1,000,000"
echo "Strategy: Cash-Secured Puts (cash-settled)"
echo "Symbol: SPX"
echo ""

# Default dates
START_DATE="${1:-2022-01-01}"
END_DATE="${2:-$(date +%Y-%m-%d)}"
CAPITAL="${3:-1000000}"

echo "Period: $START_DATE to $END_DATE"
echo "Capital: \$$CAPITAL"
echo ""

# Check if we have the required environment
if [ -z "$POLYGON_API_KEY" ]; then
    echo "WARNING: POLYGON_API_KEY not set - will use estimated prices"
fi

if [ -z "$DATABASE_URL" ]; then
    echo "WARNING: DATABASE_URL not set - results won't be saved to database"
fi

echo ""
echo "Running backtest..."
echo ""

cd /home/user/AlphaGEX

python3 backtest/spx_premium_backtest.py \
    --start "$START_DATE" \
    --end "$END_DATE" \
    --capital "$CAPITAL"

echo ""
echo "=============================================="
echo "Backtest complete!"
echo "=============================================="
echo ""
echo "Generated files:"
echo "  - strategy_report_*.html  (MT4-style report with equity curve)"
echo "  - *.xlsx                  (Full audit trail)"
echo ""

# Find and display the HTML report path
REPORT_FILE=$(ls -t strategy_report_*.html 2>/dev/null | head -1)
if [ -n "$REPORT_FILE" ]; then
    echo "Opening Strategy Tester Report: $REPORT_FILE"
    echo ""
    # Try to open in browser
    if command -v xdg-open &> /dev/null; then
        xdg-open "$REPORT_FILE" 2>/dev/null &
    elif command -v open &> /dev/null; then
        open "$REPORT_FILE" 2>/dev/null &
    else
        echo "Open this file in your browser: $(pwd)/$REPORT_FILE"
    fi
fi

echo "=============================================="
