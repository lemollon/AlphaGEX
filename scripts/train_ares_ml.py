#!/usr/bin/env python3
"""
Train ARES ML Advisor from KRONOS Backtest Data
================================================

This script demonstrates the ML feedback loop:
1. Run KRONOS backtest to generate historical trade data
2. Extract features and train ML model
3. Show pattern insights
4. Demo predictions for ARES

Usage:
    python scripts/train_ares_ml.py

    # With custom date range:
    python scripts/train_ares_ml.py --start 2022-01-01 --end 2024-12-01

Author: AlphaGEX ML
"""

import os
import sys
import argparse
from datetime import datetime

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / '.env')


def main():
    parser = argparse.ArgumentParser(description='Train ARES ML Advisor')
    parser.add_argument('--start', type=str, default='2021-01-01', help='Backtest start date')
    parser.add_argument('--end', type=str, default=datetime.now().strftime('%Y-%m-%d'), help='Backtest end date')
    parser.add_argument('--skip-backtest', action='store_true', help='Skip backtest, use existing model')
    args = parser.parse_args()

    print("=" * 70)
    print("ARES ML Advisor Training Pipeline")
    print("=" * 70)
    print(f"\nDate range: {args.start} to {args.end}")

    # Import ML advisor
    try:
        from quant.ares_ml_advisor import (
            get_advisor, train_from_backtest, get_trading_advice,
            TradingAdvice
        )
        print("[OK] ML Advisor module loaded")
    except ImportError as e:
        print(f"[ERROR] Failed to load ML Advisor: {e}")
        print("Make sure scikit-learn, pandas, numpy are installed:")
        print("  pip install scikit-learn pandas numpy")
        return 1

    # Step 1: Run KRONOS backtest
    if not args.skip_backtest:
        print("\n" + "-" * 70)
        print("STEP 1: Running KRONOS Backtest")
        print("-" * 70)

        try:
            from backtest.zero_dte_hybrid_fixed import HybridFixedBacktester

            # Run backtest with standard ARES parameters
            backtester = HybridFixedBacktester(
                start_date=args.start,
                end_date=args.end,
                initial_capital=1_000_000,
                spread_width=10.0,
                sd_multiplier=1.0,
                risk_per_trade_pct=10.0,
                ticker="SPX",
                strategy_type="iron_condor"
            )

            print(f"\nRunning backtest from {args.start} to {args.end}...")
            print("This may take a few minutes...")

            results = backtester.run()

            if results:
                print(f"\nBacktest Complete!")
                print(f"  Total trades: {results.get('total_trades', 0)}")
                print(f"  Win rate: {results.get('win_rate', 0):.1f}%")
                print(f"  Total P&L: ${results.get('total_pnl', 0):,.2f}")

                # Step 2: Train ML model
                print("\n" + "-" * 70)
                print("STEP 2: Training ML Model")
                print("-" * 70)

                try:
                    metrics = train_from_backtest(results)

                    print(f"\nModel Training Complete!")
                    print(f"  Samples: {metrics.total_samples}")
                    print(f"  Accuracy: {metrics.accuracy:.1%}")
                    print(f"  AUC-ROC: {metrics.auc_roc:.3f}")
                    print(f"  Brier Score: {metrics.brier_score:.4f} (lower is better)")
                    print(f"  Actual Win Rate: {metrics.win_rate_actual:.1%}")

                    print(f"\nFeature Importance:")
                    for feat, imp in sorted(metrics.feature_importances.items(), key=lambda x: -x[1])[:5]:
                        print(f"  {feat}: {imp:.3f}")

                except Exception as e:
                    print(f"\n[ERROR] Training failed: {e}")
                    print("Continuing with existing model if available...")

            else:
                print("[ERROR] Backtest returned no results")
                print("Check ORAT database connection and data availability")

        except Exception as e:
            print(f"[ERROR] Backtest failed: {e}")
            print("Will try to use existing model...")
    else:
        print("\n[SKIP] Backtest skipped, using existing model")

    # Step 3: Get Pattern Insights
    print("\n" + "-" * 70)
    print("STEP 3: Pattern Analysis")
    print("-" * 70)

    advisor = get_advisor()

    if advisor.is_trained:
        insights = advisor.get_pattern_insights()

        print(f"\nModel Version: {insights.get('model_version', 'N/A')}")

        if insights.get('vix_sensitivity'):
            print("\nVIX Sensitivity Analysis:")
            print(f"  {'VIX':>6} | {'Win Prob':>10} | {'Advice':<15}")
            print(f"  {'-'*6} | {'-'*10} | {'-'*15}")
            for v in insights['vix_sensitivity']:
                print(f"  {v['vix']:>6} | {v['win_probability']:>9.1%} | {v['advice']:<15}")

        if insights.get('day_of_week_analysis'):
            print("\nDay of Week Analysis:")
            print(f"  {'Day':>10} | {'Win Prob':>10} | {'Advice':<15}")
            print(f"  {'-'*10} | {'-'*10} | {'-'*15}")
            for d in insights['day_of_week_analysis']:
                print(f"  {d['day']:>10} | {d['win_probability']:>9.1%} | {d['advice']:<15}")

        if insights.get('pattern_recommendations'):
            print("\nRecommendations:")
            for rec in insights['pattern_recommendations']:
                print(f"  - {rec}")
    else:
        print("\n[INFO] Model not trained - showing fallback predictions")

    # Step 4: Demo Predictions
    print("\n" + "-" * 70)
    print("STEP 4: Demo Trading Predictions")
    print("-" * 70)

    # Get today's day of week
    today_dow = datetime.now().weekday()
    dow_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

    print(f"\nToday is {dow_names[today_dow]}")

    scenarios = [
        {"vix": 14, "desc": "Low volatility (VIX 14)"},
        {"vix": 20, "desc": "Normal volatility (VIX 20)"},
        {"vix": 28, "desc": "Elevated volatility (VIX 28)"},
        {"vix": 38, "desc": "High volatility (VIX 38)"},
    ]

    print(f"\nPredictions for today ({dow_names[today_dow]}):")
    print(f"{'Scenario':<30} | {'Advice':<15} | {'Win Prob':>10} | {'Risk %':>8} | {'SD Mult':>8}")
    print(f"{'-'*30} | {'-'*15} | {'-'*10} | {'-'*8} | {'-'*8}")

    for scenario in scenarios:
        pred = get_trading_advice(vix=scenario['vix'], day_of_week=today_dow)
        print(f"{scenario['desc']:<30} | {pred.advice.value:<15} | {pred.win_probability:>9.1%} | {pred.suggested_risk_pct:>7.1f}% | {pred.suggested_sd_multiplier:>8.2f}")

    # Summary
    print("\n" + "=" * 70)
    print("TRAINING COMPLETE")
    print("=" * 70)
    print("""
Next Steps:
1. Review the pattern insights above
2. Integrate ML advisor into ARES (see below)
3. Monitor predictions vs actual outcomes
4. Periodically retrain with new outcomes

Integration Example:
    from quant.ares_ml_advisor import get_trading_advice, TradingAdvice

    # In ARES daily cycle:
    advice = get_trading_advice(vix=current_vix, day_of_week=today.weekday())

    if advice.advice == TradingAdvice.SKIP_TODAY:
        logger.info(f"ML suggests skipping: {advice.win_probability:.1%} win prob")
        return

    # Use suggested risk percentage
    risk_pct = advice.suggested_risk_pct  # Instead of fixed 10%
    sd_mult = advice.suggested_sd_multiplier  # Instead of fixed 1.0
""")

    return 0


if __name__ == "__main__":
    exit(main())
