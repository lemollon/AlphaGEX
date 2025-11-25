#!/bin/bash

echo "============================================================"
echo "Options Backtest Comparison: Realistic vs Simplified Pricing"
echo "============================================================"
echo ""
echo "This script will run the options backtest using:"
echo "  1. Realistic pricing (Black-Scholes with Greeks)"
echo "  2. Results will be saved to PostgreSQL database"
echo ""
echo "Symbol: SPY"
echo "Period: 2022-01-01 to 2024-12-31"
echo ""
echo "Press Ctrl+C to cancel, or Enter to continue..."
read

echo ""
echo "============================================================"
echo "Running Backtest with REALISTIC Pricing"
echo "============================================================"
echo ""

python backtest_options_strategies.py \
  --symbol SPY \
  --start 2022-01-01 \
  --end 2024-12-31

echo ""
echo "============================================================"
echo "Backtest Complete!"
echo "============================================================"
echo ""
echo "Results have been saved to the database."
echo "Check the backtest_results table for detailed metrics."
echo ""
echo "Key metrics to compare:"
echo "  - Total trades generated"
echo "  - Win rate (%)"
echo "  - Average P&L per trade"
echo "  - Expectancy (%)"
echo "  - Max drawdown"
echo ""
echo "Realistic pricing includes:"
echo "  ✓ Black-Scholes option valuation"
echo "  ✓ Greeks (delta, gamma, theta, vega)"
echo "  ✓ Bid/ask spreads (4%)"
echo "  ✓ Multi-leg slippage (1.5%)"
echo "  ✓ Time decay modeling"
echo "  ✓ IV impact on P&L"
echo ""
