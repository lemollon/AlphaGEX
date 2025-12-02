#!/bin/bash
#
# BACKTEST ACCURACY TEST
#
# Runs a backtest and reports what percentage of trades used REAL data
# vs ESTIMATED data.
#
# USAGE:
#   ./scripts/test_backtest_accuracy.sh
#

set -e

PROJECT_ROOT="$(dirname "$(dirname "$(realpath "$0")")")"
cd "$PROJECT_ROOT"

echo ""
echo "╔══════════════════════════════════════════════════════════════════════╗"
echo "║               BACKTEST ACCURACY TEST                                 ║"
echo "╠══════════════════════════════════════════════════════════════════════╣"
echo "║  Running a 3-month backtest to verify data quality                  ║"
echo "╚══════════════════════════════════════════════════════════════════════╝"
echo ""

python3 << 'PYTHON_EOF'
import os
import sys
sys.path.insert(0, os.getcwd())

print("Running backtest (2024-01-01 to 2024-04-01)...")
print("This may take a minute...\n")

try:
    from backtest.spx_premium_backtest import SPXPremiumBacktester

    backtester = SPXPremiumBacktester(
        start_date="2024-01-01",
        end_date="2024-04-01",
        initial_capital=100000,
        put_delta=0.20,
        dte_target=45,
        stop_loss_pct=200
    )

    results = backtester.run(save_to_db=False)

    if not results:
        print("✗ Backtest failed to return results")
        sys.exit(1)

    summary = results.get('summary', {})
    data_quality = results.get('data_quality', {})
    trades = results.get('trades', [])

    print("=" * 70)
    print("BACKTEST RESULTS")
    print("=" * 70)
    print(f"\nPerformance:")
    print(f"  Total Trades:    {summary.get('total_trades', 0)}")
    print(f"  Win Rate:        {summary.get('win_rate', 0):.1f}%")
    print(f"  Total P&L:       ${summary.get('total_pnl', 0):,.2f}")
    print(f"  Total Return:    {summary.get('total_return_pct', 0):.2f}%")
    print(f"  Max Drawdown:    {summary.get('max_drawdown', 0):.2f}%")

    # Data quality analysis
    real_count = data_quality.get('real_data_points', 0)
    est_count = data_quality.get('estimated_data_points', 0)
    total = real_count + est_count
    real_pct = data_quality.get('real_data_pct', 0)

    print(f"\n" + "=" * 70)
    print("DATA QUALITY BREAKDOWN")
    print("=" * 70)
    print(f"\n  Real Data Trades:      {real_count}")
    print(f"  Estimated Data Trades: {est_count}")
    print(f"  Total Trades:          {total}")
    print(f"")
    print(f"  REAL DATA PERCENTAGE:  {real_pct:.1f}%")

    # Per-trade breakdown
    if trades:
        print(f"\n" + "-" * 50)
        print("Sample trades with data source:")
        print(f"{'Trade':<5} {'Type':<15} {'Strike':<8} {'P&L':<10} {'Source'}")
        print("-" * 50)
        for i, t in enumerate(trades[:10]):
            source = t.get('price_source', 'UNKNOWN')
            source_short = 'REAL' if 'POLYGON' in source else 'EST'
            print(f"{i+1:<5} {t.get('trade_type', 'N/A'):<15} ${t.get('strike', 0):,.0f}   ${t.get('pnl', 0):>8,.2f}   {source_short}")

    # Verdict
    print(f"\n" + "=" * 70)
    print("VERDICT")
    print("=" * 70)

    if real_pct >= 80:
        print("""
    ╔══════════════════════════════════════════════════════════════╗
    ║  ✓ HIGH ACCURACY BACKTEST                                    ║
    ║                                                              ║
    ║  {real_pct:.0f}% of trades used REAL historical option prices.       ║
    ║  These results are trustworthy for strategy evaluation.      ║
    ╚══════════════════════════════════════════════════════════════╝
        """.format(real_pct=real_pct))
    elif real_pct >= 50:
        print("""
    ╔══════════════════════════════════════════════════════════════╗
    ║  ⚠ MEDIUM ACCURACY BACKTEST                                  ║
    ║                                                              ║
    ║  {real_pct:.0f}% of trades used real data, rest are estimates.       ║
    ║  Results are useful but may not perfectly reflect reality.   ║
    ╚══════════════════════════════════════════════════════════════╝
        """.format(real_pct=real_pct))
    else:
        print("""
    ╔══════════════════════════════════════════════════════════════╗
    ║  ✗ LOW ACCURACY BACKTEST                                     ║
    ║                                                              ║
    ║  Only {real_pct:.0f}% of trades used real data.                      ║
    ║  Most prices are estimates - DO NOT TRUST these results!     ║
    ║                                                              ║
    ║  FIX: Get Polygon Options subscription for historical data.  ║
    ╚══════════════════════════════════════════════════════════════╝
        """.format(real_pct=real_pct))

except Exception as e:
    print(f"\n✗ Backtest failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
PYTHON_EOF
