#!/bin/bash
# ==========================================================================
# SPX WHEEL DAILY TRADING CYCLE
# ==========================================================================
#
# Run this EVERY TRADING DAY to execute the calibrated strategy.
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

echo "==========================================================================="
echo "SPX WHEEL - DAILY TRADING CYCLE"
echo "==========================================================================="
echo "Time: $(date)"
echo ""

# Check environment
if [ -z "$DATABASE_URL" ]; then
    echo "ERROR: DATABASE_URL not set"
    exit 1
fi

cd /home/user/AlphaGEX

python3 << 'EOF'
import sys
sys.path.insert(0, '/home/user/AlphaGEX')

from trading.spx_wheel_system import SPXWheelTrader
import json

print("="*70)
print("LOADING CALIBRATED PARAMETERS")
print("="*70)

# Initialize with saved parameters
trader = SPXWheelTrader()

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
