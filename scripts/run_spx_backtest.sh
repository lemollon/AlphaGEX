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
echo "Check the Excel file for full audit trail."
echo "=============================================="
