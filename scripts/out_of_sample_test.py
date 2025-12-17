#!/usr/bin/env python3
"""
Out-of-Sample Test for GEX Probability Models
==============================================

Validates the model edge on data it hasn't seen:
- Train: 2020-01-01 to 2023-12-31
- Test:  2024-01-01 to present

This is the true test of whether the model generalizes.

Usage:
    python scripts/out_of_sample_test.py
"""

import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / '.env')


def run_out_of_sample_test():
    print("=" * 70)
    print("OUT-OF-SAMPLE TEST")
    print("=" * 70)
    print("\nThis test validates model performance on unseen data:")
    print("  Training Period: 2020-01-01 to 2023-12-31")
    print("  Testing Period:  2024-01-01 to present")

    # Import modules
    from quant.gex_probability_models import GEXSignalGenerator
    from scripts.backtest_gex_signals import run_backtest, load_backtest_data, print_results

    # Step 1: Train on 2020-2023 only
    print("\n" + "=" * 70)
    print("STEP 1: TRAINING ON 2020-2023 DATA")
    print("=" * 70)

    generator = GEXSignalGenerator()
    results = generator.train(
        symbols=['SPX', 'SPY'],
        start_date='2020-01-01',
        end_date='2023-12-31'
    )

    # Save to separate file for OOS testing
    oos_model_path = 'models/gex_signal_generator_oos.joblib'
    generator.save(oos_model_path)
    print(f"\nOOS model saved to: {oos_model_path}")

    # Step 2: Test on 2024-2025 (unseen data)
    print("\n" + "=" * 70)
    print("STEP 2: TESTING ON 2024-2025 DATA (OUT-OF-SAMPLE)")
    print("=" * 70)

    # Load the OOS model
    generator_oos = GEXSignalGenerator()
    generator_oos.load(oos_model_path)

    # Run backtest on unseen data
    from scripts.backtest_gex_signals import (
        load_backtest_data, build_features_from_row,
        simulate_spread_trade, Trade, calculate_results, print_results
    )

    # Load test data
    print("\nLoading 2024-2025 test data...")
    test_df = load_backtest_data(
        symbols=['SPY'],
        start_date='2024-01-01',
        end_date=None  # Present
    )
    print(f"  Loaded {len(test_df)} trading days for testing")

    # Run simulation on test data
    print("\nRunning out-of-sample simulation...")
    trades = []

    test_df = test_df.sort_values('trade_date').reset_index(drop=True)

    for i, row in test_df.iterrows():
        prev_row = test_df.iloc[i-1] if i > 0 else None
        features = build_features_from_row(row, prev_row)

        try:
            signal = generator_oos.predict(features)
        except Exception as e:
            continue

        if signal.trade_recommendation not in ['LONG', 'SHORT']:
            continue

        entry_price = float(row['spot_open'])
        close_price = float(row['spot_close'])

        won, pnl_pct = simulate_spread_trade(
            signal.trade_recommendation,
            entry_price,
            close_price,
            spread_width=2.0
        )

        trade = Trade(
            date=str(row['trade_date']),
            symbol=row['symbol'],
            direction=signal.trade_recommendation,
            entry_price=entry_price,
            exit_price=close_price,
            spread_type='BULL_CALL_SPREAD' if signal.trade_recommendation == 'LONG' else 'BEAR_CALL_SPREAD',
            spread_width=2.0,
            price_change_pct=float(row['price_change_pct']),
            won=won,
            pnl_pct=pnl_pct,
            direction_confidence=signal.direction_confidence,
            overall_conviction=signal.overall_conviction,
            expected_volatility=signal.expected_volatility_pct,
            gamma_regime='POSITIVE' if features['gamma_regime_positive'] else 'NEGATIVE'
        )
        trades.append(trade)

    print(f"  Generated {len(trades)} trades on unseen data")

    # Calculate and print results
    oos_results = calculate_results(trades)

    print("\n" + "=" * 70)
    print("OUT-OF-SAMPLE RESULTS (2024-2025)")
    print("=" * 70)

    print_results(oos_results, trades)

    # Compare to in-sample
    print("\n" + "=" * 70)
    print("COMPARISON: IN-SAMPLE vs OUT-OF-SAMPLE")
    print("=" * 70)

    print("\n  Run the full backtest to compare:")
    print("    In-sample:  python scripts/backtest_gex_signals.py --start 2020-01-01 --end 2023-12-31")
    print("    Out-sample: Results shown above")

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    if oos_results.total_trades > 0:
        print(f"\n  Out-of-Sample Performance:")
        print(f"    Trades:        {oos_results.total_trades}")
        print(f"    Win Rate:      {oos_results.win_rate:.1%}")
        print(f"    Profit Factor: {oos_results.profit_factor:.2f}")
        print(f"    Total Return:  {oos_results.total_return_pct:.1f}%")

        if oos_results.win_rate >= 0.6 and oos_results.profit_factor >= 1.5:
            print("\n  ✓ MODEL VALIDATED: Out-of-sample performance is strong")
            print("    Ready for live deployment")
        elif oos_results.win_rate >= 0.5 and oos_results.profit_factor >= 1.0:
            print("\n  ~ MODEL MARGINAL: Out-of-sample shows some edge")
            print("    Consider paper trading before live deployment")
        else:
            print("\n  ✗ MODEL DEGRADED: Out-of-sample performance is weak")
            print("    Possible overfitting - review model features")
    else:
        print("\n  No trades generated in test period")

    return oos_results, trades


if __name__ == '__main__':
    run_out_of_sample_test()
