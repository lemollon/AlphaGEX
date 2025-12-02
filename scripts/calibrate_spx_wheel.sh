#!/bin/bash
# ==========================================================================
# SPX WHEEL CALIBRATION SCRIPT
# ==========================================================================
#
# THIS IS THE ENTRY POINT FOR THE BILLIONAIRE TRADER
#
# What this script does:
# 1. Tests multiple parameter combinations (delta, DTE) on REAL historical data
# 2. Finds the OPTIMAL parameters based on your chosen metric (Sharpe, return, etc)
# 3. Saves those parameters to the database
# 4. Initializes the live trader with those exact parameters
#
# The output shows you:
# - Every combination tested with exact numbers
# - Win rate, return, drawdown for each
# - Which combination is BEST and WHY
# - What parameters will be used for live trading
#
# Run monthly to recalibrate based on recent market conditions.
# ==========================================================================

echo "==========================================================================="
echo "SPX WHEEL PARAMETER CALIBRATION"
echo "==========================================================================="
echo "Time: $(date)"
echo ""
echo "PURPOSE: Find optimal parameters from historical data, then use them to trade."
echo ""
echo "This is how the backtest drives live trading decisions:"
echo "  Backtest --> Optimal Parameters --> Live Trader --> Performance Comparison"
echo ""
echo "==========================================================================="

# Configuration
START_DATE="${1:-2022-01-01}"
END_DATE="${2:-$(date +%Y-%m-%d)}"
CAPITAL="${3:-1000000}"
OPTIMIZE_FOR="${4:-sharpe}"  # sharpe, return, win_rate, drawdown

echo ""
echo "CALIBRATION SETTINGS:"
echo "  Historical Period: $START_DATE to $END_DATE"
echo "  Capital:           \$$CAPITAL"
echo "  Optimize For:      $OPTIMIZE_FOR"
echo ""

# Check environment
if [ -z "$DATABASE_URL" ]; then
    echo "ERROR: DATABASE_URL not set - parameters cannot be saved"
    exit 1
fi

if [ -z "$POLYGON_API_KEY" ]; then
    echo "WARNING: POLYGON_API_KEY not set - will use estimated prices"
fi

cd /home/user/AlphaGEX

echo "==========================================================================="
echo "STEP 1: RUNNING PARAMETER GRID SEARCH"
echo "==========================================================================="
echo ""
echo "Testing these parameter combinations on REAL POLYGON HISTORICAL DATA:"
echo ""
echo "  DELTA VALUES:  0.15, 0.20, 0.25, 0.30"
echo "                 (0.15 = more OTM, less risk, less premium)"
echo "                 (0.30 = less OTM, more risk, more premium)"
echo ""
echo "  DTE VALUES:    30, 45, 60 days"
echo "                 (30 = faster decay, more trades per year)"
echo "                 (60 = slower decay, fewer assignment events)"
echo ""
echo "  TOTAL COMBINATIONS: 12"
echo ""
echo "Each combination will show:"
echo "  - Win Rate: % of trades that expired worthless (you kept premium)"
echo "  - Total Return: % gain/loss over the period"
echo "  - Max Drawdown: Worst peak-to-trough decline"
echo "  - Sharpe Ratio: Risk-adjusted return (higher is better)"
echo ""
echo "==========================================================================="
echo ""

python3 << EOF
import sys
sys.path.insert(0, '/home/user/AlphaGEX')

from trading.spx_wheel_system import SPXWheelOptimizer

# Run optimization
optimizer = SPXWheelOptimizer(
    start_date="$START_DATE",
    end_date="$END_DATE",
    initial_capital=$CAPITAL
)

best_params = optimizer.find_optimal_parameters(
    delta_range=[0.15, 0.20, 0.25, 0.30],
    dte_range=[30, 45, 60],
    optimize_for='$OPTIMIZE_FOR'
)

print("\n" + "="*70)
print("CALIBRATION COMPLETE - PARAMETERS SAVED")
print("="*70)
print(f"""
THE SYSTEM WILL NOW USE THESE PARAMETERS FOR LIVE TRADING:

  Put Delta Target:   {best_params.put_delta}
  DTE Target:         {best_params.dte_target} days
  Max Margin Usage:   {best_params.max_margin_pct*100:.0f}%
  Contracts per Trade: {best_params.contracts_per_trade}

BACKTEST PERFORMANCE (what to expect):
  Win Rate:           {best_params.backtest_win_rate:.1f}%
  Total Return:       {best_params.backtest_total_return:+.1f}%
  Max Drawdown:       {best_params.backtest_max_drawdown:.1f}%
  Expectancy:         {best_params.backtest_expectancy:.2f}% per trade

CALIBRATION INFO:
  Period Tested:      {best_params.backtest_period}
  Calibration Date:   {best_params.calibration_date[:10]}

These parameters are now saved to the database.
The live trader will automatically load and use them.
""")
EOF

echo ""
echo "==========================================================================="
echo "STEP 2: VERIFYING TRADER INITIALIZATION"
echo "==========================================================================="
echo ""

python3 << 'EOF'
import sys
sys.path.insert(0, '/home/user/AlphaGEX')

from trading.spx_wheel_system import SPXWheelTrader
import json

# Initialize trader (loads saved parameters)
trader = SPXWheelTrader()

status = trader.get_status()

print("\nTRADER STATUS:")
print(f"  Parameters loaded from calibration: {status['parameters'].get('calibration_date', 'N/A')[:10]}")
print(f"  Put Delta: {status['parameters']['put_delta']}")
print(f"  DTE Target: {status['parameters']['dte_target']}")
print(f"  Open Positions: {status['open_positions']}")
print(f"  Expected Win Rate: {status['backtest_win_rate']:.1f}%")
print(f"  Expected Return: {status['backtest_return']:+.1f}%")
EOF

echo ""
echo "==========================================================================="
echo "HOW TO USE THESE CALIBRATED PARAMETERS"
echo "==========================================================================="
echo ""
echo "NOW THAT CALIBRATION IS COMPLETE, here's your workflow:"
echo ""
echo "1. DAILY TRADING (run each trading day):"
echo "   ./scripts/run_spx_daily.sh"
echo ""
echo "   This will:"
echo "   - Check market conditions (VIX within range?)"
echo "   - Process any expiring positions"
echo "   - Open new positions using calibrated parameters"
echo "   - Log all decisions to the database"
echo ""
echo "2. MONITOR PERFORMANCE:"
echo "   ./scripts/check_spx_performance.sh"
echo ""
echo "   This shows:"
echo "   - Your actual live performance"
echo "   - Comparison to backtest expectations"
echo "   - Alert if divergence > 10%"
echo ""
echo "3. RECALIBRATE (monthly recommended):"
echo "   ./scripts/calibrate_spx_wheel.sh 2023-01-01"
echo ""
echo "   Re-run calibration to adapt to new market conditions."
echo ""
echo "==========================================================================="
echo "CALIBRATION COMPLETE - System Ready for Trading"
echo "==========================================================================="
