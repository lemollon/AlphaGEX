#!/usr/bin/env python3
"""
Compare Standard Iron Condor vs GEX-Protected Iron Condor
==========================================================

This script runs backtests for both strategies and compares their performance
to determine if GEX wall-based strike selection improves outcomes.

Usage:
    python scripts/compare_gex_protected_ic.py
    python scripts/compare_gex_protected_ic.py --start 2022-01-01 --end 2024-12-01
    python scripts/compare_gex_protected_ic.py --quick  # 1-year quick test

Author: AlphaGEX Quant
"""

import os
import sys
import argparse
from datetime import datetime, timedelta
import json

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / '.env')


def run_comparison(start_date: str, end_date: str, initial_capital: float = 1_000_000):
    """
    Run comparison backtest between Standard IC and GEX-Protected IC.

    Returns:
        Dict with comparison results
    """
    from backtest.zero_dte_hybrid_fixed import HybridFixedBacktester

    print("=" * 80)
    print("STRATEGY COMPARISON: Standard IC vs GEX-Protected IC")
    print("=" * 80)
    print(f"Date Range: {start_date} to {end_date}")
    print(f"Initial Capital: ${initial_capital:,.0f}")
    print("=" * 80)

    # Common parameters
    common_params = {
        'start_date': start_date,
        'end_date': end_date,
        'initial_capital': initial_capital,
        'spread_width': 10.0,
        'sd_multiplier': 1.0,
        'risk_per_trade_pct': 5.0,
        'ticker': 'SPX',
    }

    # =========================================================================
    # Run Standard Iron Condor
    # =========================================================================
    print("\n" + "-" * 80)
    print("RUNNING: Standard Iron Condor (SD-based strikes)")
    print("-" * 80)

    standard_bt = HybridFixedBacktester(
        **common_params,
        strategy_type='iron_condor'
    )
    standard_bt.debug_mode = False  # Suppress debug output
    standard_results = standard_bt.run()

    # =========================================================================
    # Run GEX-Protected Iron Condor
    # =========================================================================
    print("\n" + "-" * 80)
    print("RUNNING: GEX-Protected Iron Condor (GEX walls with SD fallback)")
    print("-" * 80)

    gex_bt = HybridFixedBacktester(
        **common_params,
        strategy_type='gex_protected_iron_condor'
    )
    gex_bt.debug_mode = False
    gex_results = gex_bt.run()

    # =========================================================================
    # Comparison Summary
    # =========================================================================
    print("\n" + "=" * 80)
    print("COMPARISON RESULTS")
    print("=" * 80)

    def get_metric(results, *keys):
        """Safely get nested metric"""
        val = results
        for key in keys:
            if isinstance(val, dict) and key in val:
                val = val[key]
            else:
                return 0
        return val if val is not None else 0

    # Extract key metrics
    std_summary = standard_results.get('summary', {})
    std_trades = standard_results.get('trades', {})
    std_risk = standard_results.get('risk_metrics', {})

    gex_summary = gex_results.get('summary', {})
    gex_trades = gex_results.get('trades', {})
    gex_risk = gex_results.get('risk_metrics', {})
    gex_stats = gex_results.get('gex_stats', {})

    # Print comparison table
    print(f"\n{'Metric':<30} {'Standard IC':>15} {'GEX-Protected':>15} {'Diff':>12}")
    print("-" * 75)

    metrics = [
        ('Total Trades', std_trades.get('total', 0), gex_trades.get('total', 0), ''),
        ('Win Rate %', std_trades.get('win_rate', 0), gex_trades.get('win_rate', 0), '%'),
        ('Total Return %', std_summary.get('total_return_pct', 0), gex_summary.get('total_return_pct', 0), '%'),
        ('Final Equity', std_summary.get('final_equity', 0), gex_summary.get('final_equity', 0), '$'),
        ('Total P&L', std_summary.get('total_pnl', 0), gex_summary.get('total_pnl', 0), '$'),
        ('Max Drawdown %', std_summary.get('max_drawdown_pct', 0), gex_summary.get('max_drawdown_pct', 0), '%'),
        ('Avg Monthly Return %', std_summary.get('avg_monthly_return_pct', 0), gex_summary.get('avg_monthly_return_pct', 0), '%'),
        ('Profit Factor', std_trades.get('profit_factor', 0), gex_trades.get('profit_factor', 0), ''),
        ('Sharpe Ratio', std_risk.get('sharpe_ratio', 0), gex_risk.get('sharpe_ratio', 0), ''),
        ('Sortino Ratio', std_risk.get('sortino_ratio', 0), gex_risk.get('sortino_ratio', 0), ''),
        ('Max Consec. Losses', std_risk.get('max_consecutive_losses', 0), gex_risk.get('max_consecutive_losses', 0), ''),
    ]

    for name, std_val, gex_val, unit in metrics:
        if unit == '$':
            diff = gex_val - std_val
            diff_str = f"{'+' if diff >= 0 else ''}{diff:,.0f}"
            print(f"{name:<30} ${std_val:>14,.0f} ${gex_val:>14,.0f} {diff_str:>12}")
        elif unit == '%':
            diff = gex_val - std_val
            diff_str = f"{'+' if diff >= 0 else ''}{diff:.1f}%"
            print(f"{name:<30} {std_val:>14.1f}% {gex_val:>14.1f}% {diff_str:>12}")
        else:
            if isinstance(std_val, int):
                diff = gex_val - std_val
                diff_str = f"{'+' if diff >= 0 else ''}{diff}"
                print(f"{name:<30} {std_val:>15} {gex_val:>15} {diff_str:>12}")
            else:
                diff = gex_val - std_val
                diff_str = f"{'+' if diff >= 0 else ''}{diff:.2f}"
                print(f"{name:<30} {std_val:>15.2f} {gex_val:>15.2f} {diff_str:>12}")

    # GEX-specific stats
    if gex_stats:
        print("\n" + "-" * 75)
        print("GEX-PROTECTED STRATEGY DETAILS")
        print("-" * 75)
        gex_wall_trades = gex_stats.get('trades_with_gex_walls', 0)
        sd_fallback = gex_stats.get('trades_with_sd_fallback', 0)
        total_gex_trades = gex_wall_trades + sd_fallback
        if total_gex_trades > 0:
            gex_pct = (gex_wall_trades / total_gex_trades) * 100
            print(f"  Trades using GEX walls:    {gex_wall_trades:>10} ({gex_pct:.1f}%)")
            print(f"  Trades using SD fallback:  {sd_fallback:>10} ({100 - gex_pct:.1f}%)")
            print(f"  GEX data unavailable days: {gex_stats.get('gex_unavailable_days', 0):>10}")

    # Outcome comparison
    print("\n" + "-" * 75)
    print("OUTCOME BREAKDOWN COMPARISON")
    print("-" * 75)
    std_outcomes = standard_results.get('outcomes', {})
    gex_outcomes = gex_results.get('outcomes', {})
    all_outcomes = set(std_outcomes.keys()) | set(gex_outcomes.keys())

    print(f"{'Outcome':<20} {'Standard IC':>15} {'GEX-Protected':>15}")
    print("-" * 55)
    for outcome in sorted(all_outcomes):
        std_count = std_outcomes.get(outcome, 0)
        gex_count = gex_outcomes.get(outcome, 0)
        print(f"{outcome:<20} {std_count:>15} {gex_count:>15}")

    # Winner determination
    print("\n" + "=" * 80)
    print("VERDICT")
    print("=" * 80)

    # Score each strategy
    std_score = 0
    gex_score = 0

    # Win rate (higher is better)
    if std_trades.get('win_rate', 0) > gex_trades.get('win_rate', 0):
        std_score += 1
    elif gex_trades.get('win_rate', 0) > std_trades.get('win_rate', 0):
        gex_score += 1

    # Total return (higher is better)
    if std_summary.get('total_return_pct', 0) > gex_summary.get('total_return_pct', 0):
        std_score += 2
    elif gex_summary.get('total_return_pct', 0) > std_summary.get('total_return_pct', 0):
        gex_score += 2

    # Max drawdown (lower is better)
    if std_summary.get('max_drawdown_pct', 100) < gex_summary.get('max_drawdown_pct', 100):
        std_score += 1
    elif gex_summary.get('max_drawdown_pct', 100) > std_summary.get('max_drawdown_pct', 100):
        gex_score += 1

    # Sharpe ratio (higher is better)
    if std_risk.get('sharpe_ratio', 0) > gex_risk.get('sharpe_ratio', 0):
        std_score += 1
    elif gex_risk.get('sharpe_ratio', 0) > std_risk.get('sharpe_ratio', 0):
        gex_score += 1

    print(f"  Standard IC Score:     {std_score}")
    print(f"  GEX-Protected Score:   {gex_score}")

    if gex_score > std_score:
        winner = "GEX-Protected Iron Condor"
        reason = "Better risk-adjusted returns using GEX wall protection"
    elif std_score > gex_score:
        winner = "Standard Iron Condor"
        reason = "SD-based strikes performed better in this period"
    else:
        winner = "TIE"
        reason = "Both strategies performed similarly"

    print(f"\n  WINNER: {winner}")
    print(f"  Reason: {reason}")

    # Recommendations
    print("\n" + "-" * 80)
    print("RECOMMENDATIONS")
    print("-" * 80)

    if gex_stats and gex_stats.get('trades_with_gex_walls', 0) > 0:
        gex_wall_pct = (gex_stats['trades_with_gex_walls'] /
                       (gex_stats['trades_with_gex_walls'] + gex_stats['trades_with_sd_fallback'])) * 100
        print(f"  - GEX data was available for {gex_wall_pct:.1f}% of trades")

        if gex_wall_pct < 50:
            print(f"  - Consider: GEX data availability was low, results may not be representative")

    win_rate_diff = gex_trades.get('win_rate', 0) - std_trades.get('win_rate', 0)
    if win_rate_diff > 2:
        print(f"  - GEX-Protected shows +{win_rate_diff:.1f}% higher win rate")
        print(f"  - This suggests GEX walls provide meaningful strike protection")
    elif win_rate_diff < -2:
        print(f"  - Standard IC shows +{abs(win_rate_diff):.1f}% higher win rate")
        print(f"  - GEX walls may be too conservative for current market conditions")

    print("\n" + "=" * 80)

    return {
        'standard': standard_results,
        'gex_protected': gex_results,
        'comparison': {
            'std_score': std_score,
            'gex_score': gex_score,
            'winner': winner,
            'reason': reason,
        }
    }


def main():
    parser = argparse.ArgumentParser(description='Compare Standard IC vs GEX-Protected IC')

    parser.add_argument('--start', type=str, default='2022-01-01',
                       help='Backtest start date (default: 2022-01-01)')
    parser.add_argument('--end', type=str, default=datetime.now().strftime('%Y-%m-%d'),
                       help='Backtest end date (default: today)')
    parser.add_argument('--capital', type=float, default=1_000_000,
                       help='Initial capital (default: 1,000,000)')
    parser.add_argument('--quick', action='store_true',
                       help='Quick test with 1-year period')
    parser.add_argument('--output', type=str,
                       help='Save comparison results to JSON file')

    args = parser.parse_args()

    # Quick test uses last 1 year
    if args.quick:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=365)
        args.start = start_date.strftime('%Y-%m-%d')
        args.end = end_date.strftime('%Y-%m-%d')
        print("Quick mode: Running 1-year comparison")

    # Run comparison
    results = run_comparison(
        start_date=args.start,
        end_date=args.end,
        initial_capital=args.capital
    )

    # Save results if output specified
    if args.output:
        # Convert to JSON-serializable format
        output = {
            'comparison': results['comparison'],
            'standard_summary': results['standard'].get('summary', {}),
            'gex_protected_summary': results['gex_protected'].get('summary', {}),
            'date_range': {
                'start': args.start,
                'end': args.end,
            }
        }

        with open(args.output, 'w') as f:
            json.dump(output, f, indent=2)
        print(f"\nResults saved to {args.output}")

    return results


if __name__ == "__main__":
    main()
