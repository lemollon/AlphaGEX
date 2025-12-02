#!/bin/bash
# ==========================================================================
# SPX WHEEL DAILY TRADING CYCLE
# ==========================================================================
#
# Run this EVERY TRADING DAY to execute the calibrated strategy.
#
# USAGE:
#   ./run_spx_daily.sh          # Paper trading (default - NO REAL MONEY)
#   ./run_spx_daily.sh paper    # Paper trading explicitly
#   ./run_spx_daily.sh live     # LIVE TRADING - REAL MONEY AT RISK!
#
# What this script does:
# 1. Loads your calibrated parameters from the database
# 2. Checks if market conditions are favorable (VIX filter)
# 3. Processes any expiring positions (cash settlement)
# 4. Opens new positions if you have capacity
# 5. Logs everything to the database for audit
# 6. Compares actual performance to backtest expectations
#
# The trader uses EXACTLY the parameters found during calibration.
# ==========================================================================

MODE="${1:-paper}"  # Default to paper trading

echo "==========================================================================="
echo "SPX WHEEL - DAILY TRADING CYCLE"
echo "==========================================================================="
echo "Time: $(date)"
echo ""

if [ "$MODE" == "live" ]; then
    echo "🔴 LIVE TRADING MODE - REAL MONEY AT RISK!"
    echo ""
    read -p "Are you sure you want to trade with real money? (yes/no): " CONFIRM
    if [ "$CONFIRM" != "yes" ]; then
        echo "Aborting."
        exit 0
    fi
else
    echo "📝 PAPER TRADING MODE (simulation)"
fi
echo ""

# Check environment
if [ -z "$DATABASE_URL" ]; then
    echo "ERROR: DATABASE_URL not set"
    exit 1
fi

if [ "$MODE" == "live" ] && [ -z "$TRADIER_API_KEY" ]; then
    echo "ERROR: TRADIER_API_KEY required for live trading"
    exit 1
fi

cd /home/user/AlphaGEX

python3 << EOF
import sys
sys.path.insert(0, '/home/user/AlphaGEX')

from trading.spx_wheel_system import SPXWheelTrader, TradingMode
import json

# Get mode from shell variable
mode_str = "$MODE"
trading_mode = TradingMode.LIVE if mode_str == "live" else TradingMode.PAPER

print("="*70)
print(f"LOADING CALIBRATED PARAMETERS - {trading_mode.value.upper()} MODE")
print("="*70)

# Initialize with saved parameters and trading mode
trader = SPXWheelTrader(mode=trading_mode)

print(f"""
Using parameters from calibration on: {trader.params.calibration_date[:10] if trader.params.calibration_date else 'DEFAULT'}

  Put Delta:      {trader.params.put_delta}
  DTE Target:     {trader.params.dte_target}
  Max Positions:  {trader.params.max_open_positions}
  Min VIX:        {trader.params.min_vix}
  Max VIX:        {trader.params.max_vix}

BACKTEST EXPECTATIONS:
  Win Rate:       {trader.params.backtest_win_rate:.1f}%
  Return:         {trader.params.backtest_total_return:+.1f}%
  Max Drawdown:   {trader.params.backtest_max_drawdown:.1f}%
""")

print("="*70)
print("RUNNING DAILY CYCLE")
print("="*70)

# Run the daily cycle
result = trader.run_daily_cycle()

print(f"""
CYCLE COMPLETE

Actions taken:
""")
for action in result['actions']:
    print(f"  - {action}")

if not result['actions']:
    print("  - No actions taken (may be weekend or conditions not favorable)")

print(f"""
Current Status:
  Open Positions: {result['current_positions']}
  Positions Opened: {result['positions_opened']}
  Positions Closed: {result['positions_closed']}
""")

# Show comparison to backtest
print("="*70)
print("PERFORMANCE VS BACKTEST")
print("="*70)

comparison = trader.compare_to_backtest()
print(f"""
  Live Return:     {comparison['live_return']:+.1f}%
  Backtest Return: {comparison['backtest_return']:+.1f}%
  Divergence:      {comparison['divergence']:+.1f}%
  Recommendation:  {comparison['recommendation']}
""")

if abs(comparison['divergence']) > 10:
    print("⚠️  WARNING: Significant divergence from backtest!")
    print("   Consider re-running calibration.")
EOF

echo ""
echo "==========================================================================="
echo "DAILY CYCLE COMPLETE"
echo "==========================================================================="
