#!/usr/bin/env python3
"""
Compare ARES ML Advisor vs Oracle Advisor Performance
======================================================

This script runs backtests and compares decision quality between:
1. ML Advisor (XGBoost model trained on historical patterns)
2. Oracle Advisor (Multi-factor model with GEX, VIX, Claude AI integration)

The comparison shows which advisor makes better trading decisions by
analyzing which trades each would have skipped or allowed.

Usage:
    python scripts/compare_ml_vs_oracle.py
    python scripts/compare_ml_vs_oracle.py --start 2022-01-01 --end 2024-12-01
    python scripts/compare_ml_vs_oracle.py --quick  # 1-year quick test

Author: AlphaGEX Quant
"""

import os
import sys
import argparse
from datetime import datetime, timedelta
import json
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / '.env')


@dataclass
class AdvisorDecision:
    """Represents an advisor's decision for a trade"""
    should_trade: bool
    confidence: float
    risk_pct: float
    sd_multiplier: float
    reasoning: str


def get_day_of_week(date_str: str) -> int:
    """Get day of week (0=Monday, 4=Friday)"""
    try:
        return datetime.strptime(date_str, '%Y-%m-%d').weekday()
    except:
        return 2  # Default to Wednesday


def calculate_sharpe(pnls: List[float], risk_free_rate: float = 0.05) -> float:
    """Calculate Sharpe ratio from P&L list"""
    if not pnls or len(pnls) < 2:
        return 0.0
    import numpy as np
    returns = np.array(pnls)
    if np.std(returns) == 0:
        return 0.0
    excess_return = np.mean(returns) - (risk_free_rate / 252)
    return (excess_return / np.std(returns)) * np.sqrt(252)


def simulate_ml_decisions(trades: List[Dict], ml_advisor) -> Dict[str, Any]:
    """
    Simulate backtest with ML advisor filtering.
    Returns metrics for trades ML would have allowed.
    """
    allowed_trades = []
    skipped_trades = []

    for trade in trades:
        try:
            # Get ML prediction for this trade's context
            vix = trade.get('vix', trade.get('vix_open', 20))
            dow = get_day_of_week(trade.get('trade_date', trade.get('date', '')))

            advice = ml_advisor.predict(vix=vix, day_of_week=dow)

            # Check if ML would allow this trade
            should_trade = advice.advice.value not in ['SKIP_TODAY', 'skip']

            if should_trade:
                allowed_trades.append({
                    **trade,
                    'ml_confidence': advice.win_probability,
                    'ml_risk_pct': advice.suggested_risk_pct,
                    'ml_sd_mult': advice.suggested_sd_mult,
                })
            else:
                skipped_trades.append({
                    **trade,
                    'skip_reason': 'ML_SKIP',
                    'ml_confidence': advice.win_probability,
                })
        except Exception as e:
            # If ML fails, allow the trade (fail-safe)
            allowed_trades.append(trade)

    # Calculate metrics for allowed trades
    pnls = [t.get('net_pnl', t.get('pnl', 0)) for t in allowed_trades]
    outcomes = [t.get('outcome', 'UNKNOWN') for t in allowed_trades]
    wins = sum(1 for o in outcomes if o in ['MAX_PROFIT', 'WIN', 'PROFIT_TARGET'])

    # Calculate metrics for skipped trades (what we avoided)
    skipped_pnls = [t.get('net_pnl', t.get('pnl', 0)) for t in skipped_trades]
    skipped_losses = sum(1 for p in skipped_pnls if p < 0)

    return {
        'allowed_trades': len(allowed_trades),
        'skipped_trades': len(skipped_trades),
        'total_pnl': sum(pnls),
        'win_rate': (wins / len(allowed_trades) * 100) if allowed_trades else 0,
        'sharpe_ratio': calculate_sharpe(pnls),
        'avg_pnl': sum(pnls) / len(pnls) if pnls else 0,
        'skipped_would_be_losses': skipped_losses,
        'skipped_pnl_avoided': sum(p for p in skipped_pnls if p < 0),
        'trades': allowed_trades,
        'skipped': skipped_trades,
    }


def simulate_oracle_decisions(trades: List[Dict], oracle) -> Dict[str, Any]:
    """
    Simulate backtest with Oracle advisor filtering.
    Returns metrics for trades Oracle would have allowed.
    """
    from quant.oracle_advisor import BotName

    allowed_trades = []
    skipped_trades = []

    for trade in trades:
        try:
            # Build context for Oracle
            vix = trade.get('vix', trade.get('vix_open', 20))
            spot_price = trade.get('spot_price', trade.get('underlying_price', 6000))
            expected_move = trade.get('expected_move', trade.get('exp_move', 30))

            # Get GEX data if available
            gex_data = None
            if trade.get('gex_regime') or trade.get('put_wall') or trade.get('call_wall'):
                from quant.kronos_gex_calculator import GEXData
                gex_data = GEXData(
                    net_gex=trade.get('net_gex', 0),
                    call_gex=trade.get('call_gex', 0),
                    put_gex=trade.get('put_gex', 0),
                    call_wall=trade.get('call_wall', spot_price + 50),
                    put_wall=trade.get('put_wall', spot_price - 50),
                    flip_point=trade.get('flip_point', spot_price),
                    gex_normalized=trade.get('gex_normalized', 0),
                    gex_regime=trade.get('gex_regime', 'NEUTRAL'),
                    distance_to_flip_pct=trade.get('distance_to_flip_pct', 0),
                    between_walls=trade.get('between_walls', True),
                )

            # Get Oracle prediction
            prediction = oracle.get_prediction(
                bot_name=BotName.ARES,
                vix=vix,
                spot_price=spot_price,
                expected_move=expected_move,
                gex_data=gex_data,
            )

            # Check if Oracle would allow this trade
            should_trade = prediction.advice.value not in ['SKIP_TODAY', 'skip']

            if should_trade:
                allowed_trades.append({
                    **trade,
                    'oracle_confidence': prediction.confidence,
                    'oracle_win_prob': prediction.win_probability,
                    'oracle_risk_pct': prediction.suggested_risk_pct,
                    'oracle_sd_mult': prediction.suggested_sd_multiplier,
                })
            else:
                skipped_trades.append({
                    **trade,
                    'skip_reason': 'ORACLE_SKIP',
                    'oracle_confidence': prediction.confidence,
                    'oracle_reasoning': prediction.reasoning,
                })
        except Exception as e:
            # If Oracle fails, allow the trade (fail-safe)
            allowed_trades.append(trade)

    # Calculate metrics for allowed trades
    pnls = [t.get('net_pnl', t.get('pnl', 0)) for t in allowed_trades]
    outcomes = [t.get('outcome', 'UNKNOWN') for t in allowed_trades]
    wins = sum(1 for o in outcomes if o in ['MAX_PROFIT', 'WIN', 'PROFIT_TARGET'])

    # Calculate metrics for skipped trades
    skipped_pnls = [t.get('net_pnl', t.get('pnl', 0)) for t in skipped_trades]
    skipped_losses = sum(1 for p in skipped_pnls if p < 0)

    return {
        'allowed_trades': len(allowed_trades),
        'skipped_trades': len(skipped_trades),
        'total_pnl': sum(pnls),
        'win_rate': (wins / len(allowed_trades) * 100) if allowed_trades else 0,
        'sharpe_ratio': calculate_sharpe(pnls),
        'avg_pnl': sum(pnls) / len(pnls) if pnls else 0,
        'skipped_would_be_losses': skipped_losses,
        'skipped_pnl_avoided': sum(p for p in skipped_pnls if p < 0),
        'trades': allowed_trades,
        'skipped': skipped_trades,
    }


def run_comparison(start_date: str, end_date: str, initial_capital: float = 1_000_000):
    """
    Run comparison backtest between ML Advisor and Oracle Advisor.

    Process:
    1. Run baseline backtest to get all trades
    2. Train ML advisor on historical data
    3. Simulate which trades each advisor would have filtered
    4. Compare resulting performance
    """
    from backtest.zero_dte_hybrid_fixed import HybridFixedBacktester

    print("=" * 80)
    print("ADVISOR COMPARISON: ML Model vs Oracle")
    print("=" * 80)
    print(f"Date Range: {start_date} to {end_date}")
    print(f"Initial Capital: ${initial_capital:,.0f}")
    print("=" * 80)

    # =========================================================================
    # Phase 1: Run Baseline Backtest
    # =========================================================================
    print("\n" + "-" * 80)
    print("PHASE 1: Running Baseline Backtest (KRONOS)")
    print("-" * 80)

    baseline_bt = HybridFixedBacktester(
        start_date=start_date,
        end_date=end_date,
        initial_capital=initial_capital,
        spread_width=10.0,
        sd_multiplier=1.0,
        risk_per_trade_pct=5.0,
        ticker='SPX',
        strategy_type='iron_condor'
    )
    baseline_bt.debug_mode = False
    baseline_results = baseline_bt.run()

    # Extract all trades
    all_trades = baseline_results.get('all_trades', [])
    if not all_trades:
        # Try alternative keys
        all_trades = baseline_results.get('trades_list', [])

    print(f"  Baseline trades: {len(all_trades)}")
    print(f"  Baseline P&L: ${baseline_results.get('summary', {}).get('total_pnl', 0):,.0f}")

    if not all_trades:
        print("ERROR: No trades found in backtest results!")
        print("Available keys:", baseline_results.keys())
        return None

    # =========================================================================
    # Phase 2: Initialize Advisors
    # =========================================================================
    print("\n" + "-" * 80)
    print("PHASE 2: Initializing Advisors")
    print("-" * 80)

    # Initialize ML Advisor
    ml_advisor = None
    try:
        from quant.ares_ml_advisor import get_advisor, train_from_backtest

        # Train ML model on baseline results
        print("  Training ML Advisor on baseline data...")
        train_metrics = train_from_backtest(baseline_results)
        ml_advisor = get_advisor()
        print(f"  ML Advisor trained - Accuracy: {train_metrics.get('accuracy', 0):.1%}")
    except Exception as e:
        print(f"  WARNING: ML Advisor initialization failed: {e}")

    # Initialize Oracle
    oracle = None
    try:
        from quant.oracle_advisor import OracleAdvisor
        oracle = OracleAdvisor()
        print("  Oracle Advisor initialized")
    except Exception as e:
        print(f"  WARNING: Oracle Advisor initialization failed: {e}")

    if not ml_advisor and not oracle:
        print("ERROR: Neither advisor could be initialized!")
        return None

    # =========================================================================
    # Phase 3: Simulate Advisor Decisions
    # =========================================================================
    print("\n" + "-" * 80)
    print("PHASE 3: Simulating Advisor Decisions")
    print("-" * 80)

    ml_results = None
    oracle_results = None

    if ml_advisor:
        print("  Simulating ML Advisor decisions...")
        ml_results = simulate_ml_decisions(all_trades, ml_advisor)
        print(f"    Allowed: {ml_results['allowed_trades']} | Skipped: {ml_results['skipped_trades']}")

    if oracle:
        print("  Simulating Oracle Advisor decisions...")
        oracle_results = simulate_oracle_decisions(all_trades, oracle)
        print(f"    Allowed: {oracle_results['allowed_trades']} | Skipped: {oracle_results['skipped_trades']}")

    # =========================================================================
    # Phase 4: Comparison Summary
    # =========================================================================
    print("\n" + "=" * 80)
    print("COMPARISON RESULTS")
    print("=" * 80)

    baseline_summary = baseline_results.get('summary', {})
    baseline_trades = baseline_results.get('trades', {})
    baseline_risk = baseline_results.get('risk_metrics', {})

    baseline_pnl = baseline_summary.get('total_pnl', 0)
    baseline_win_rate = baseline_trades.get('win_rate', 0)
    baseline_sharpe = baseline_risk.get('sharpe_ratio', 0)
    baseline_total = baseline_trades.get('total', len(all_trades))

    # Print comparison table
    print(f"\n{'Metric':<30} {'Baseline':>15} {'ML Advisor':>15} {'Oracle':>15}")
    print("-" * 80)

    def fmt_pnl(v): return f"${v:,.0f}" if v else "$0"
    def fmt_pct(v): return f"{v:.1f}%" if v else "0.0%"
    def fmt_num(v): return f"{v:.2f}" if isinstance(v, float) else str(v)

    metrics = [
        ('Total Trades', baseline_total,
         ml_results['allowed_trades'] if ml_results else 'N/A',
         oracle_results['allowed_trades'] if oracle_results else 'N/A'),
        ('Trades Skipped', 0,
         ml_results['skipped_trades'] if ml_results else 'N/A',
         oracle_results['skipped_trades'] if oracle_results else 'N/A'),
        ('Total P&L', baseline_pnl,
         ml_results['total_pnl'] if ml_results else 'N/A',
         oracle_results['total_pnl'] if oracle_results else 'N/A'),
        ('Win Rate %', baseline_win_rate,
         ml_results['win_rate'] if ml_results else 'N/A',
         oracle_results['win_rate'] if oracle_results else 'N/A'),
        ('Sharpe Ratio', baseline_sharpe,
         ml_results['sharpe_ratio'] if ml_results else 'N/A',
         oracle_results['sharpe_ratio'] if oracle_results else 'N/A'),
        ('Avg Trade P&L', baseline_pnl / baseline_total if baseline_total else 0,
         ml_results['avg_pnl'] if ml_results else 'N/A',
         oracle_results['avg_pnl'] if oracle_results else 'N/A'),
        ('Losses Avoided', 0,
         ml_results['skipped_would_be_losses'] if ml_results else 'N/A',
         oracle_results['skipped_would_be_losses'] if oracle_results else 'N/A'),
        ('Loss $ Avoided', 0,
         abs(ml_results['skipped_pnl_avoided']) if ml_results else 'N/A',
         abs(oracle_results['skipped_pnl_avoided']) if oracle_results else 'N/A'),
    ]

    for name, baseline, ml, oracle in metrics:
        if isinstance(baseline, float) and 'P&L' in name or 'Avoided' in name:
            b_str = fmt_pnl(baseline)
            m_str = fmt_pnl(ml) if isinstance(ml, (int, float)) else str(ml)
            o_str = fmt_pnl(oracle) if isinstance(oracle, (int, float)) else str(oracle)
        elif isinstance(baseline, float) and '%' in name:
            b_str = fmt_pct(baseline)
            m_str = fmt_pct(ml) if isinstance(ml, (int, float)) else str(ml)
            o_str = fmt_pct(oracle) if isinstance(oracle, (int, float)) else str(oracle)
        elif isinstance(baseline, float):
            b_str = fmt_num(baseline)
            m_str = fmt_num(ml) if isinstance(ml, (int, float)) else str(ml)
            o_str = fmt_num(oracle) if isinstance(oracle, (int, float)) else str(oracle)
        else:
            b_str = str(baseline)
            m_str = str(ml)
            o_str = str(oracle)

        print(f"{name:<30} {b_str:>15} {m_str:>15} {o_str:>15}")

    # =========================================================================
    # Phase 5: Winner Determination
    # =========================================================================
    print("\n" + "=" * 80)
    print("VERDICT")
    print("=" * 80)

    ml_score = 0
    oracle_score = 0

    if ml_results and oracle_results:
        # Win rate comparison
        if ml_results['win_rate'] > oracle_results['win_rate']:
            ml_score += 1
            print(f"  Win Rate: ML wins ({ml_results['win_rate']:.1f}% vs {oracle_results['win_rate']:.1f}%)")
        elif oracle_results['win_rate'] > ml_results['win_rate']:
            oracle_score += 1
            print(f"  Win Rate: Oracle wins ({oracle_results['win_rate']:.1f}% vs {ml_results['win_rate']:.1f}%)")

        # Total P&L comparison
        if ml_results['total_pnl'] > oracle_results['total_pnl']:
            ml_score += 2
            print(f"  Total P&L: ML wins (${ml_results['total_pnl']:,.0f} vs ${oracle_results['total_pnl']:,.0f})")
        elif oracle_results['total_pnl'] > ml_results['total_pnl']:
            oracle_score += 2
            print(f"  Total P&L: Oracle wins (${oracle_results['total_pnl']:,.0f} vs ${ml_results['total_pnl']:,.0f})")

        # Sharpe ratio comparison
        if ml_results['sharpe_ratio'] > oracle_results['sharpe_ratio']:
            ml_score += 1
            print(f"  Sharpe: ML wins ({ml_results['sharpe_ratio']:.2f} vs {oracle_results['sharpe_ratio']:.2f})")
        elif oracle_results['sharpe_ratio'] > ml_results['sharpe_ratio']:
            oracle_score += 1
            print(f"  Sharpe: Oracle wins ({oracle_results['sharpe_ratio']:.2f} vs {ml_results['sharpe_ratio']:.2f})")

        # Loss avoidance (skipped losing trades)
        if ml_results['skipped_would_be_losses'] > oracle_results['skipped_would_be_losses']:
            ml_score += 1
            print(f"  Loss Avoidance: ML wins ({ml_results['skipped_would_be_losses']} vs {oracle_results['skipped_would_be_losses']} losses avoided)")
        elif oracle_results['skipped_would_be_losses'] > ml_results['skipped_would_be_losses']:
            oracle_score += 1
            print(f"  Loss Avoidance: Oracle wins ({oracle_results['skipped_would_be_losses']} vs {ml_results['skipped_would_be_losses']} losses avoided)")

    print(f"\n  ML Advisor Score:     {ml_score}")
    print(f"  Oracle Advisor Score: {oracle_score}")

    if ml_score > oracle_score:
        winner = "ML Advisor"
        reason = "Better pattern recognition and trade filtering"
    elif oracle_score > ml_score:
        winner = "Oracle Advisor"
        reason = "Better multi-factor analysis with GEX and AI integration"
    else:
        winner = "TIE"
        reason = "Both advisors performed similarly"

    print(f"\n  WINNER: {winner}")
    print(f"  Reason: {reason}")

    # =========================================================================
    # Recommendations
    # =========================================================================
    print("\n" + "-" * 80)
    print("RECOMMENDATIONS")
    print("-" * 80)

    if ml_results and oracle_results:
        ml_skip_rate = ml_results['skipped_trades'] / len(all_trades) * 100
        oracle_skip_rate = oracle_results['skipped_trades'] / len(all_trades) * 100

        print(f"  - ML skips {ml_skip_rate:.1f}% of trades, Oracle skips {oracle_skip_rate:.1f}%")

        if ml_skip_rate > 30:
            print(f"  - ML may be too conservative (>30% skip rate)")
        if oracle_skip_rate > 30:
            print(f"  - Oracle may be too conservative (>30% skip rate)")

        # Check if skipping improved returns
        baseline_avg = baseline_pnl / baseline_total if baseline_total else 0
        ml_improvement = ml_results['avg_pnl'] - baseline_avg
        oracle_improvement = oracle_results['avg_pnl'] - baseline_avg

        if ml_improvement > 0:
            print(f"  - ML filtering improves avg trade by ${ml_improvement:.0f}")
        if oracle_improvement > 0:
            print(f"  - Oracle filtering improves avg trade by ${oracle_improvement:.0f}")

        # Hybrid recommendation
        if ml_score >= 2 and oracle_score >= 2:
            print(f"  - Consider HYBRID: Trade only when BOTH advisors agree")

    print("\n" + "=" * 80)

    return {
        'baseline': baseline_results,
        'ml_results': ml_results,
        'oracle_results': oracle_results,
        'comparison': {
            'ml_score': ml_score,
            'oracle_score': oracle_score,
            'winner': winner,
            'reason': reason,
        }
    }


def main():
    parser = argparse.ArgumentParser(description='Compare ML Advisor vs Oracle Advisor')

    parser.add_argument('--start', type=str, default='2023-01-01',
                       help='Backtest start date (default: 2023-01-01)')
    parser.add_argument('--end', type=str, default=datetime.now().strftime('%Y-%m-%d'),
                       help='Backtest end date (default: today)')
    parser.add_argument('--capital', type=float, default=1_000_000,
                       help='Initial capital (default: 1,000,000)')
    parser.add_argument('--quick', action='store_true',
                       help='Quick test with 6-month period')
    parser.add_argument('--output', type=str,
                       help='Save comparison results to JSON file')

    args = parser.parse_args()

    # Quick test uses last 6 months
    if args.quick:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=180)
        args.start = start_date.strftime('%Y-%m-%d')
        args.end = end_date.strftime('%Y-%m-%d')
        print("Quick mode: Running 6-month comparison")

    # Run comparison
    results = run_comparison(
        start_date=args.start,
        end_date=args.end,
        initial_capital=args.capital
    )

    # Save results if output specified
    if args.output and results:
        output = {
            'comparison': results['comparison'],
            'baseline_summary': results['baseline'].get('summary', {}),
            'ml_summary': {
                'allowed': results['ml_results']['allowed_trades'] if results['ml_results'] else 0,
                'skipped': results['ml_results']['skipped_trades'] if results['ml_results'] else 0,
                'pnl': results['ml_results']['total_pnl'] if results['ml_results'] else 0,
                'win_rate': results['ml_results']['win_rate'] if results['ml_results'] else 0,
            },
            'oracle_summary': {
                'allowed': results['oracle_results']['allowed_trades'] if results['oracle_results'] else 0,
                'skipped': results['oracle_results']['skipped_trades'] if results['oracle_results'] else 0,
                'pnl': results['oracle_results']['total_pnl'] if results['oracle_results'] else 0,
                'win_rate': results['oracle_results']['win_rate'] if results['oracle_results'] else 0,
            },
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
