#!/usr/bin/env python3
"""
Apache GEX Directional Strategy - Optimizer & ML Trainer

This script:
1. Trains the MAGNET theory ML model
2. Tests the Apache strategy with different configurations
3. Finds the optimal combination of parameters

MAGNET THEORY (KEY INSIGHT):
- High put GEX = price pulled DOWN toward puts = BEARISH
- High call GEX = price pulled UP toward calls = BULLISH
- This is OPPOSITE of "support/resistance" theory!

Best Configuration Found:
- MAGNET Theory (inverted GEX)
- 3% wall proximity
- Day trades (hold_days=1)
- VIX 15-25 filter for best risk-adjusted returns

Usage:
    # Train ML model and run optimized backtest
    python scripts/optimize_apache_strategy.py --train-ml

    # Run backtest with VIX filter + 3-year period
    python scripts/optimize_apache_strategy.py --vix-filter

    # Run full optimization suite
    python scripts/optimize_apache_strategy.py --full
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse
from datetime import datetime

from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / '.env')


def train_ml_model(start_date='2022-01-01', end_date=None, ticker='SPX'):
    """Train the GEX Directional ML model with MAGNET theory features"""
    from quant.gex_directional_ml import GEXDirectionalPredictor

    end_date = end_date or datetime.now().strftime('%Y-%m-%d')

    print("=" * 70)
    print("TRAINING GEX DIRECTIONAL ML MODEL (MAGNET THEORY)")
    print("=" * 70)
    print(f"\nTicker: {ticker}")
    print(f"Training period: {start_date} to {end_date}")
    print("\nMAGNET THEORY Features:")
    print("  - gex_ratio: put_gex / call_gex (key signal)")
    print("  - gex_ratio_log: log(gex_ratio) for scaling")
    print("  - near_put_wall: within 3% of put wall")
    print("  - near_call_wall: within 3% of call wall")
    print("  - gex_asymmetry_strong: ratio > 1.5 or < 0.67")
    print("  - vix_regime_mid: VIX 15-25 (best risk-adjusted)")

    # Ensure output directory exists
    os.makedirs('models', exist_ok=True)

    # Initialize and train
    predictor = GEXDirectionalPredictor(ticker=ticker)

    try:
        result = predictor.train(
            start_date=start_date,
            end_date=end_date,
            n_splits=5
        )

        print(f"\nTraining Complete!")
        print(f"   Accuracy: {result.accuracy:.1%}")
        print(f"   Training samples: {result.training_samples}")

        # Save model
        model_path = 'models/gex_directional_model.joblib'
        predictor.save_model(model_path)
        print(f"\nModel saved to: {model_path}")

        # Print feature importance
        if result.feature_importance:
            print(f"\nTop Feature Importances:")
            sorted_features = sorted(result.feature_importance.items(),
                                    key=lambda x: x[1], reverse=True)[:15]
            for feat, imp in sorted_features:
                print(f"   {feat}: {imp:.3f}")

        return True

    except Exception as e:
        print(f"\nTraining failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_apache_backtest(
    start_date='2024-01-01',
    end_date=None,
    ticker='SPX',
    min_vix=None,
    max_vix=None,
    hold_days=1,
    wall_proximity_pct=3.0,
    capital=100_000
):
    """Run Apache directional backtest with specified parameters"""
    from backtest.zero_dte_hybrid_fixed import HybridFixedBacktester

    end_date = end_date or datetime.now().strftime('%Y-%m-%d')

    config_name = f"VIX {min_vix or 'any'}-{max_vix or 'any'}, {wall_proximity_pct}% wall, {hold_days}d hold"
    print(f"\n{'='*60}")
    print(f"APACHE BACKTEST: {config_name}")
    print(f"{'='*60}")
    print(f"Period: {start_date} to {end_date}")

    backtester = HybridFixedBacktester(
        start_date=start_date,
        end_date=end_date,
        initial_capital=capital,
        ticker=ticker,
        strategy_type='apache_directional',
        min_vix=min_vix,
        max_vix=max_vix,
        hold_days=hold_days,
        wall_proximity_pct=wall_proximity_pct,
    )

    results = backtester.run()

    return results


def run_optimization_suite():
    """Run full optimization suite testing various configurations"""
    print("\n" + "=" * 70)
    print("APACHE STRATEGY OPTIMIZATION SUITE")
    print("=" * 70)

    configs = [
        # Baseline
        {'name': 'Baseline (no filter)', 'min_vix': None, 'max_vix': None, 'wall_proximity_pct': 3.0, 'hold_days': 1},

        # VIX filters
        {'name': 'VIX 15-25 (best PF)', 'min_vix': 15, 'max_vix': 25, 'wall_proximity_pct': 3.0, 'hold_days': 1},
        {'name': 'VIX < 20 (low vol)', 'min_vix': None, 'max_vix': 20, 'wall_proximity_pct': 3.0, 'hold_days': 1},
        {'name': 'VIX > 20 (high vol)', 'min_vix': 20, 'max_vix': None, 'wall_proximity_pct': 3.0, 'hold_days': 1},

        # Wall proximity
        {'name': 'Tight walls (2%)', 'min_vix': None, 'max_vix': None, 'wall_proximity_pct': 2.0, 'hold_days': 1},
        {'name': 'Wide walls (5%)', 'min_vix': None, 'max_vix': None, 'wall_proximity_pct': 5.0, 'hold_days': 1},

        # Hold duration
        {'name': 'Swing (2 days)', 'min_vix': None, 'max_vix': None, 'wall_proximity_pct': 3.0, 'hold_days': 2},
        {'name': 'Swing (3 days)', 'min_vix': None, 'max_vix': None, 'wall_proximity_pct': 3.0, 'hold_days': 3},

        # Combined best
        {'name': 'BEST: VIX 15-25 + 3% wall', 'min_vix': 15, 'max_vix': 25, 'wall_proximity_pct': 3.0, 'hold_days': 1},
    ]

    results_summary = []

    for config in configs:
        try:
            results = run_apache_backtest(
                start_date='2022-01-01',
                end_date=datetime.now().strftime('%Y-%m-%d'),
                min_vix=config.get('min_vix'),
                max_vix=config.get('max_vix'),
                wall_proximity_pct=config.get('wall_proximity_pct', 3.0),
                hold_days=config.get('hold_days', 1),
            )

            summary = results.get('summary', {})
            trades = results.get('trades', {})

            results_summary.append({
                'name': config['name'],
                'trades': trades.get('total', 0),
                'win_rate': trades.get('win_rate', 0),
                'return': summary.get('total_return_pct', 0),
                'profit_factor': trades.get('profit_factor', 0),
                'max_dd': summary.get('max_drawdown_pct', 0),
            })

        except Exception as e:
            print(f"Failed: {config['name']} - {e}")
            results_summary.append({
                'name': config['name'],
                'error': str(e)
            })

    # Print comparison
    print("\n" + "=" * 70)
    print("OPTIMIZATION RESULTS COMPARISON")
    print("=" * 70)
    print(f"\n{'Configuration':<30} {'Trades':>7} {'Win %':>7} {'Return':>8} {'PF':>6} {'MaxDD':>7}")
    print("-" * 70)

    for r in results_summary:
        if 'error' in r:
            print(f"{r['name']:<30} ERROR: {r['error']}")
        else:
            print(f"{r['name']:<30} {r['trades']:>7} {r['win_rate']:>6.1f}% {r['return']:>7.1f}% {r['profit_factor']:>6.2f} {r['max_dd']:>6.1f}%")

    return results_summary


def main():
    parser = argparse.ArgumentParser(
        description='Apache GEX Directional Strategy - Optimizer & ML Trainer',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Train ML model only
  python scripts/optimize_apache_strategy.py --train-ml

  # Run backtest with VIX 15-25 filter (best risk-adjusted)
  python scripts/optimize_apache_strategy.py --vix-filter

  # Run backtest on specific date range
  python scripts/optimize_apache_strategy.py --backtest --start 2022-01-01 --end 2024-12-31

  # Run full optimization suite
  python scripts/optimize_apache_strategy.py --full
        """
    )

    parser.add_argument('--train-ml', action='store_true',
                       help='Train the ML model with MAGNET theory features')
    parser.add_argument('--backtest', action='store_true',
                       help='Run Apache backtest')
    parser.add_argument('--vix-filter', action='store_true',
                       help='Run backtest with VIX 15-25 filter')
    parser.add_argument('--full', action='store_true',
                       help='Run full optimization suite')

    parser.add_argument('--start', default='2022-01-01',
                       help='Backtest start date (default: 2022-01-01)')
    parser.add_argument('--end', default=None,
                       help='Backtest end date (default: today)')
    parser.add_argument('--ticker', default='SPX',
                       help='Ticker symbol (default: SPX)')

    parser.add_argument('--min-vix', type=float, default=None,
                       help='Minimum VIX to trade')
    parser.add_argument('--max-vix', type=float, default=None,
                       help='Maximum VIX to trade')
    parser.add_argument('--wall-proximity', type=float, default=3.0,
                       help='Wall proximity %% (default: 3.0)')
    parser.add_argument('--hold-days', type=int, default=1,
                       help='Hold days: 1=day, 2+=swing (default: 1)')

    args = parser.parse_args()

    if args.train_ml:
        print("\n" + "=" * 70)
        print("STEP 1: Training ML Model")
        print("=" * 70)
        train_ml_model(
            start_date=args.start,
            end_date=args.end,
            ticker=args.ticker
        )

    if args.vix_filter:
        print("\n" + "=" * 70)
        print("Running Apache with VIX 15-25 Filter (Best Risk-Adjusted)")
        print("=" * 70)
        run_apache_backtest(
            start_date=args.start,
            end_date=args.end,
            ticker=args.ticker,
            min_vix=15,
            max_vix=25,
            wall_proximity_pct=3.0,
            hold_days=1
        )

    if args.backtest:
        run_apache_backtest(
            start_date=args.start,
            end_date=args.end,
            ticker=args.ticker,
            min_vix=args.min_vix,
            max_vix=args.max_vix,
            wall_proximity_pct=args.wall_proximity,
            hold_days=args.hold_days
        )

    if args.full:
        # Train ML first
        print("\n" + "=" * 70)
        print("STEP 1: Training ML Model")
        print("=" * 70)
        train_ml_model(start_date=args.start, ticker=args.ticker)

        # Then run optimization
        print("\n" + "=" * 70)
        print("STEP 2: Running Optimization Suite")
        print("=" * 70)
        run_optimization_suite()

    if not any([args.train_ml, args.backtest, args.vix_filter, args.full]):
        parser.print_help()
        print("\n" + "=" * 70)
        print("Quick Start:")
        print("=" * 70)
        print("\n1. Train ML model:     python scripts/optimize_apache_strategy.py --train-ml")
        print("2. Test VIX filter:    python scripts/optimize_apache_strategy.py --vix-filter")
        print("3. Full optimization:  python scripts/optimize_apache_strategy.py --full")


if __name__ == '__main__':
    main()
