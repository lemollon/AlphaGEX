#!/usr/bin/env python3
"""
TEST 02: Backtest Execution
Tests the SPX wheel backtest engine and trade generation.

Run: python scripts/test_02_backtest_execution.py
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta

print("\n" + "="*60)
print(" TEST 02: BACKTEST EXECUTION")
print("="*60)

# =============================================================================
# 1. Import Backtest Engine
# =============================================================================
print("\n--- Importing Backtest Engine ---")

SPXBacktest = None
try:
    from backtest.spx_premium_backtest import SPXPremiumBacktester
    SPXBacktest = SPXPremiumBacktester
    print("  SPXPremiumBacktester imported from backtest.spx_premium_backtest")
except ImportError as e:
    print(f"  Trying alternate imports...")
    try:
        from backtest.wheel_backtest import WheelBacktester
        SPXBacktest = WheelBacktester
        print("  WheelBacktester imported from backtest.wheel_backtest")
    except ImportError:
        try:
            from backtest.real_wheel_backtest import RealWheelBacktester
            SPXBacktest = RealWheelBacktester
            print("  RealWheelBacktester imported from backtest.real_wheel_backtest")
        except ImportError:
            print(f"  Could not import any backtest engine: {e}")
            sys.exit(1)

# =============================================================================
# 2. Initialize and Run Backtest (1 month)
# =============================================================================
print("\n--- Running 1-Month Backtest ---")

results = None
try:
    end_date = datetime.now() - timedelta(days=7)  # End a week ago
    start_date = end_date - timedelta(days=30)

    start_str = start_date.strftime('%Y-%m-%d')
    end_str = end_date.strftime('%Y-%m-%d')

    print(f"  Date range: {start_str} to {end_str}")
    print(f"  Initial capital: $100,000,000")
    print("  Running backtest...")

    # SPXPremiumBacktester takes dates in constructor, uses run() method
    backtest = SPXBacktest(
        start_date=start_str,
        end_date=end_str,
        initial_capital=100000000  # $100M
    )
    print(f"  Engine: {type(backtest).__name__}")

    results = backtest.run(save_to_db=False)

    if results:
        print(f"  Backtest completed!")

        # Check for trades
        trades = results.get('all_trades', results.get('trades', []))
        print(f"\n  Trades generated: {len(trades)}")

        if trades:
            print("\n  Sample trade:")
            sample = trades[0]
            for key in ['entry_date', 'strike', 'premium', 'exit_date', 'outcome', 'pnl']:
                if key in sample:
                    print(f"    {key}: {sample[key]}")

        # Check summary
        summary = results.get('summary', {})
        print(f"\n  Summary:")
        print(f"    Total return: {summary.get('total_return_pct', 'N/A')}%")
        print(f"    Max drawdown: {summary.get('max_drawdown_pct', 'N/A')}%")
        print(f"    Win rate: {summary.get('win_rate', 'N/A')}%")
        print(f"    Total trades: {summary.get('total_trades', len(trades))}")

        # Check equity curve
        equity = results.get('equity_curve', [])
        print(f"\n  Equity curve points: {len(equity)}")
        if equity:
            print(f"    Start: ${equity[0].get('equity', 'N/A'):,.2f}" if isinstance(equity[0].get('equity'), (int, float)) else f"    Start: {equity[0]}")
            print(f"    End: ${equity[-1].get('equity', 'N/A'):,.2f}" if isinstance(equity[-1].get('equity'), (int, float)) else f"    End: {equity[-1]}")
    else:
        print("  No results returned")

except Exception as e:
    print(f"  Error: {e}")
    import traceback
    traceback.print_exc()

# =============================================================================
# 4. Check Trade Structure
# =============================================================================
print("\n--- Trade Structure Validation ---")

try:
    if 'results' in dir() and results:
        trades = results.get('all_trades', results.get('trades', []))

        if trades:
            required_fields = ['entry_date', 'strike', 'premium', 'exit_date', 'outcome', 'pnl']
            ml_fields = ['vix_at_entry', 'iv_rank', 'delta_at_entry', 'dte_at_entry']

            sample = trades[0]

            print("  Required fields:")
            for field in required_fields:
                status = "present" if field in sample else "MISSING"
                icon = "OK" if field in sample else "XX"
                print(f"    [{icon}] {field}: {status}")

            print("\n  ML feature fields:")
            for field in ml_fields:
                status = "present" if field in sample else "missing (will be added by ML process)"
                icon = "OK" if field in sample else "??"
                print(f"    [{icon}] {field}: {status}")
        else:
            print("  No trades to validate")
    else:
        print("  No backtest results available")

except Exception as e:
    print(f"  Error: {e}")

# =============================================================================
# 5. Test Different Delta Levels
# =============================================================================
print("\n--- Delta Level Tests ---")

try:
    for delta in [0.10, 0.16, 0.20]:
        print(f"\n  Testing delta = {delta}:")

        end_date = datetime.now() - timedelta(days=7)
        start_date = end_date - timedelta(days=14)

        # SPXPremiumBacktester uses put_delta parameter
        bt = SPXBacktest(
            start_date=start_date.strftime('%Y-%m-%d'),
            end_date=end_date.strftime('%Y-%m-%d'),
            initial_capital=100000000,  # $100M
            put_delta=delta
        )

        results = bt.run(save_to_db=False)

        if results:
            trades = results.get('all_trades', results.get('trades', []))
            summary = results.get('summary', {})
            print(f"    Trades: {len(trades)}")
            print(f"    Win rate: {summary.get('win_rate', 'N/A')}%")
        else:
            print(f"    No results")

except Exception as e:
    print(f"  Error: {e}")

# =============================================================================
# 6. Verify Data Sources Used
# =============================================================================
print("\n--- Data Sources in Backtest ---")

try:
    # Check if backtest uses real market data
    from data.polygon_data_fetcher import polygon_fetcher

    # Get SPY price to compare with backtest
    df = polygon_fetcher.get_price_history('SPY', days=30)

    if df is not None and not df.empty:
        print(f"  Market data available: {len(df)} days")
        print(f"  Price range: ${df['Close'].min():.2f} - ${df['Close'].max():.2f}")
        print(f"  Backtest should use this real price data")
    else:
        print("  Warning: No market data from Polygon")
        print("  Backtest may be using simulated data")

except Exception as e:
    print(f"  Error checking data sources: {e}")

# =============================================================================
# Summary
# =============================================================================
print("\n" + "="*60)
print(" BACKTEST EXECUTION TEST COMPLETE")
print("="*60 + "\n")
