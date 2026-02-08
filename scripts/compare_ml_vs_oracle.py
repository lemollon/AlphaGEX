#!/usr/bin/env python3
"""
Compare FORTRESS ML Advisor vs Oracle Advisor Performance
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
    except (ValueError, TypeError):
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

    VIX-based skip rules (applied even without GEX data):
    - VIX > 35: SKIP (too volatile)
    - VIX > 30 + Monday/Friday: SKIP (volatile + bad day)
    - VIX > 28 + losing streak: SKIP (compound risk)
    """
    from quant.oracle_advisor import BotName

    allowed_trades = []
    skipped_trades = []
    recent_losses = 0  # Track losing streak

    for trade in trades:
        try:
            # Build context for Oracle
            vix = trade.get('vix', trade.get('vix_open', 20))
            spot_price = trade.get('spot_price', trade.get('underlying_price', 6000))
            expected_move = trade.get('expected_move', trade.get('exp_move', 30))
            day_of_week = get_day_of_week(trade.get('trade_date', trade.get('date', '')))

            # ========== VIX-Based Skip Rules (No GEX Required) ==========
            skip_reason = None

            # Rule 1: Extreme VIX - always skip
            if vix > 35:
                skip_reason = f"VIX_EXTREME ({vix:.1f} > 35)"

            # Rule 2: High VIX + Bad Day (Monday=0, Friday=4)
            elif vix > 30 and day_of_week in [0, 4]:
                skip_reason = f"VIX_HIGH_BAD_DAY (VIX={vix:.1f}, Day={day_of_week})"

            # Rule 3: Elevated VIX + Losing Streak
            elif vix > 28 and recent_losses >= 2:
                skip_reason = f"VIX_ELEVATED_STREAK (VIX={vix:.1f}, Losses={recent_losses})"

            # Rule 4: Very High VIX
            elif vix > 32:
                skip_reason = f"VIX_VERY_HIGH ({vix:.1f} > 32)"

            if skip_reason:
                skipped_trades.append({
                    **trade,
                    'skip_reason': skip_reason,
                    'vix': vix,
                    'day_of_week': day_of_week,
                })
                # Update losing streak from skipped trade's actual outcome
                if trade.get('outcome', '') in ['PUT_BREACHED', 'CALL_BREACHED', 'DOUBLE_BREACH']:
                    recent_losses += 1
                else:
                    recent_losses = 0
                continue

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
                bot_name=BotName.FORTRESS,
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
                # Update losing streak
                if trade.get('outcome', '') in ['PUT_BREACHED', 'CALL_BREACHED', 'DOUBLE_BREACH']:
                    recent_losses += 1
                else:
                    recent_losses = 0
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


def simulate_combined_decisions(trades: List[Dict], ml_advisor, oracle) -> Dict[str, Any]:
    """
    Simulate backtest with ML + Oracle working TOGETHER (how FORTRESS actually operates).

    Decision flow:
    1. VIX-based pre-filter (skip extreme conditions)
    2. ML provides base win probability
    3. Oracle adjusts based on GEX, VIX, market conditions
    4. Final decision combines both signals

    Thresholds:
    - ≥70% combined confidence = TRADE_FULL
    - 55-70% combined confidence = TRADE_REDUCED (smaller position)
    - <55% combined confidence = SKIP
    """
    from quant.oracle_advisor import BotName

    allowed_trades = []
    skipped_trades = []
    reduced_trades = []  # Trades with reduced position size
    recent_losses = 0  # Track losing streak

    for trade in trades:
        try:
            # Get market context
            vix = trade.get('vix', trade.get('vix_open', 20))
            spot_price = trade.get('spot_price', trade.get('underlying_price', 6000))
            expected_move = trade.get('expected_move', trade.get('exp_move', 30))
            dow = get_day_of_week(trade.get('trade_date', trade.get('date', '')))

            # ========== Step 0: VIX-Based Pre-Filter ==========
            skip_reason = None

            # Rule 1: Extreme VIX - always skip
            if vix > 35:
                skip_reason = f"VIX_EXTREME ({vix:.1f} > 35)"

            # Rule 2: High VIX + Bad Day (Monday=0, Friday=4)
            elif vix > 30 and dow in [0, 4]:
                skip_reason = f"VIX_HIGH_BAD_DAY (VIX={vix:.1f}, Day={dow})"

            # Rule 3: Elevated VIX + Losing Streak
            elif vix > 28 and recent_losses >= 2:
                skip_reason = f"VIX_ELEVATED_STREAK (VIX={vix:.1f}, Losses={recent_losses})"

            # Rule 4: Very High VIX
            elif vix > 32:
                skip_reason = f"VIX_VERY_HIGH ({vix:.1f} > 32)"

            if skip_reason:
                skipped_trades.append({
                    **trade,
                    'skip_reason': skip_reason,
                    'decision': 'SKIP',
                    'vix': vix,
                    'day_of_week': dow,
                })
                # Update losing streak
                if trade.get('outcome', '') in ['PUT_BREACHED', 'CALL_BREACHED', 'DOUBLE_BREACH']:
                    recent_losses += 1
                else:
                    recent_losses = 0
                continue

            # ========== Step 1: Get ML Base Probability ==========
            ml_prob = 0.65  # Default if ML fails
            ml_sd_mult = 1.0
            if ml_advisor:
                try:
                    ml_advice = ml_advisor.predict(vix=vix, day_of_week=dow)
                    ml_prob = ml_advice.win_probability
                    ml_sd_mult = ml_advice.suggested_sd_mult
                except Exception:
                    pass

            # ========== Step 2: Get Oracle Adjustments ==========
            oracle_adjustment = 0.0
            oracle_sd_mult = 1.0
            oracle_reasoning = []

            if oracle:
                try:
                    # Build GEX data if available
                    gex_data = None
                    if trade.get('gex_regime') or trade.get('put_wall'):
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

                    oracle_pred = oracle.get_prediction(
                        bot_name=BotName.FORTRESS,
                        vix=vix,
                        spot_price=spot_price,
                        expected_move=expected_move,
                        gex_data=gex_data,
                    )

                    # Oracle provides adjustments based on conditions
                    oracle_sd_mult = oracle_pred.suggested_sd_multiplier

                    # Calculate adjustment from Oracle's confidence vs baseline
                    oracle_confidence = oracle_pred.win_probability
                    oracle_adjustment = oracle_confidence - 0.65  # Deviation from neutral

                    # Track reasoning
                    if gex_data and gex_data.gex_regime == 'POSITIVE':
                        oracle_reasoning.append("+GEX_POSITIVE")
                    elif gex_data and gex_data.gex_regime == 'NEGATIVE':
                        oracle_reasoning.append("-GEX_NEGATIVE")
                    if vix > 25:
                        oracle_reasoning.append("-HIGH_VIX")
                    if vix < 15:
                        oracle_reasoning.append("+LOW_VIX")

                except Exception as e:
                    oracle_reasoning.append(f"ORACLE_ERROR: {str(e)[:30]}")

            # ========== Step 3: Combine Signals ==========
            # Combined probability = ML base + Oracle adjustment (capped 0-1)
            combined_prob = max(0.0, min(1.0, ml_prob + oracle_adjustment))

            # Use Oracle's SD multiplier if it differs significantly from ML's
            final_sd_mult = oracle_sd_mult if abs(oracle_sd_mult - 1.0) > 0.1 else ml_sd_mult

            # ========== Step 4: Make Decision ==========
            trade_data = {
                **trade,
                'ml_prob': ml_prob,
                'oracle_adjustment': oracle_adjustment,
                'combined_prob': combined_prob,
                'final_sd_mult': final_sd_mult,
                'oracle_reasoning': oracle_reasoning,
            }

            if combined_prob >= 0.70:
                # TRADE_FULL - high confidence
                trade_data['decision'] = 'TRADE_FULL'
                trade_data['position_multiplier'] = 1.0
                allowed_trades.append(trade_data)
                # Update losing streak
                if trade.get('outcome', '') in ['PUT_BREACHED', 'CALL_BREACHED', 'DOUBLE_BREACH']:
                    recent_losses += 1
                else:
                    recent_losses = 0
            elif combined_prob >= 0.55:
                # TRADE_REDUCED - moderate confidence, smaller position
                trade_data['decision'] = 'TRADE_REDUCED'
                trade_data['position_multiplier'] = 0.5  # Half position
                # Adjust P&L for reduced position
                orig_pnl = trade.get('net_pnl', trade.get('pnl', 0))
                trade_data['adjusted_pnl'] = orig_pnl * 0.5
                reduced_trades.append(trade_data)
                allowed_trades.append(trade_data)
                # Update losing streak
                if trade.get('outcome', '') in ['PUT_BREACHED', 'CALL_BREACHED', 'DOUBLE_BREACH']:
                    recent_losses += 1
                else:
                    recent_losses = 0
            else:
                # SKIP - low confidence
                trade_data['decision'] = 'SKIP'
                trade_data['skip_reason'] = f"Combined prob {combined_prob:.1%} < 55%"
                skipped_trades.append(trade_data)

        except Exception as e:
            # On error, allow trade with neutral settings
            allowed_trades.append({
                **trade,
                'combined_prob': 0.65,
                'decision': 'TRADE_FULL',
                'error': str(e),
            })

    # Calculate metrics
    # For reduced trades, use adjusted P&L
    pnls = []
    for t in allowed_trades:
        if t.get('decision') == 'TRADE_REDUCED':
            pnls.append(t.get('adjusted_pnl', t.get('net_pnl', t.get('pnl', 0)) * 0.5))
        else:
            pnls.append(t.get('net_pnl', t.get('pnl', 0)))

    outcomes = [t.get('outcome', 'UNKNOWN') for t in allowed_trades]
    wins = sum(1 for o in outcomes if o in ['MAX_PROFIT', 'WIN', 'PROFIT_TARGET'])

    skipped_pnls = [t.get('net_pnl', t.get('pnl', 0)) for t in skipped_trades]
    skipped_losses = sum(1 for p in skipped_pnls if p < 0)

    return {
        'allowed_trades': len(allowed_trades),
        'skipped_trades': len(skipped_trades),
        'reduced_trades': len(reduced_trades),
        'full_trades': len(allowed_trades) - len(reduced_trades),
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
        from quant.fortress_ml_advisor import get_advisor, train_from_backtest

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

    # Combined ML + Oracle (how FORTRESS actually operates)
    combined_results = None
    if ml_advisor or oracle:
        print("  Simulating COMBINED ML + Oracle decisions (FORTRESS mode)...")
        combined_results = simulate_combined_decisions(all_trades, ml_advisor, oracle)
        print(f"    Full trades: {combined_results.get('full_trades', 0)} | Reduced: {combined_results.get('reduced_trades', 0)} | Skipped: {combined_results['skipped_trades']}")

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
    print(f"\n{'Metric':<25} {'Baseline':>12} {'ML Only':>12} {'Oracle Only':>12} {'COMBINED':>12}")
    print("-" * 85)

    def fmt_pnl(v): return f"${v:,.0f}" if v else "$0"
    def fmt_pct(v): return f"{v:.1f}%" if v else "0.0%"
    def fmt_num(v): return f"{v:.2f}" if isinstance(v, float) else str(v)

    metrics = [
        ('Total Trades', baseline_total,
         ml_results['allowed_trades'] if ml_results else 'N/A',
         oracle_results['allowed_trades'] if oracle_results else 'N/A',
         combined_results['allowed_trades'] if combined_results else 'N/A'),
        ('Trades Skipped', 0,
         ml_results['skipped_trades'] if ml_results else 'N/A',
         oracle_results['skipped_trades'] if oracle_results else 'N/A',
         combined_results['skipped_trades'] if combined_results else 'N/A'),
        ('Reduced Position', 0, 'N/A', 'N/A',
         combined_results.get('reduced_trades', 0) if combined_results else 'N/A'),
        ('Total P&L', baseline_pnl,
         ml_results['total_pnl'] if ml_results else 'N/A',
         oracle_results['total_pnl'] if oracle_results else 'N/A',
         combined_results['total_pnl'] if combined_results else 'N/A'),
        ('Win Rate %', baseline_win_rate,
         ml_results['win_rate'] if ml_results else 'N/A',
         oracle_results['win_rate'] if oracle_results else 'N/A',
         combined_results['win_rate'] if combined_results else 'N/A'),
        ('Sharpe Ratio', baseline_sharpe,
         ml_results['sharpe_ratio'] if ml_results else 'N/A',
         oracle_results['sharpe_ratio'] if oracle_results else 'N/A',
         combined_results['sharpe_ratio'] if combined_results else 'N/A'),
        ('Avg Trade P&L', baseline_pnl / baseline_total if baseline_total else 0,
         ml_results['avg_pnl'] if ml_results else 'N/A',
         oracle_results['avg_pnl'] if oracle_results else 'N/A',
         combined_results['avg_pnl'] if combined_results else 'N/A'),
        ('Losses Avoided', 0,
         ml_results['skipped_would_be_losses'] if ml_results else 'N/A',
         oracle_results['skipped_would_be_losses'] if oracle_results else 'N/A',
         combined_results['skipped_would_be_losses'] if combined_results else 'N/A'),
        ('Loss $ Avoided', 0,
         abs(ml_results['skipped_pnl_avoided']) if ml_results else 'N/A',
         abs(oracle_results['skipped_pnl_avoided']) if oracle_results else 'N/A',
         abs(combined_results['skipped_pnl_avoided']) if combined_results else 'N/A'),
    ]

    for name, baseline, ml, oracle_val, combined in metrics:
        if isinstance(baseline, float) and 'P&L' in name or 'Avoided' in name:
            b_str = fmt_pnl(baseline)
            m_str = fmt_pnl(ml) if isinstance(ml, (int, float)) else str(ml)
            o_str = fmt_pnl(oracle_val) if isinstance(oracle_val, (int, float)) else str(oracle_val)
            c_str = fmt_pnl(combined) if isinstance(combined, (int, float)) else str(combined)
        elif isinstance(baseline, float) and '%' in name:
            b_str = fmt_pct(baseline)
            m_str = fmt_pct(ml) if isinstance(ml, (int, float)) else str(ml)
            o_str = fmt_pct(oracle_val) if isinstance(oracle_val, (int, float)) else str(oracle_val)
            c_str = fmt_pct(combined) if isinstance(combined, (int, float)) else str(combined)
        elif isinstance(baseline, float):
            b_str = fmt_num(baseline)
            m_str = fmt_num(ml) if isinstance(ml, (int, float)) else str(ml)
            o_str = fmt_num(oracle_val) if isinstance(oracle_val, (int, float)) else str(oracle_val)
            c_str = fmt_num(combined) if isinstance(combined, (int, float)) else str(combined)
        else:
            b_str = str(baseline)
            m_str = str(ml)
            o_str = str(oracle_val)
            c_str = str(combined)

        print(f"{name:<25} {b_str:>12} {m_str:>12} {o_str:>12} {c_str:>12}")

    # =========================================================================
    # Phase 5: Winner Determination
    # =========================================================================
    print("\n" + "=" * 80)
    print("VERDICT")
    print("=" * 80)

    ml_score = 0
    oracle_score = 0
    combined_score = 0

    # Helper to get value or 0
    def get_val(results, key, default=0):
        return results.get(key, default) if results else default

    # Compare all three approaches
    results_list = [
        ('ML Only', ml_results),
        ('Oracle Only', oracle_results),
        ('COMBINED', combined_results),
    ]

    # Only compare if we have results
    valid_results = [(name, r) for name, r in results_list if r]

    if len(valid_results) >= 2:
        print("\n  Performance Ranking:")

        # Rank by P&L
        by_pnl = sorted(valid_results, key=lambda x: x[1]['total_pnl'], reverse=True)
        print(f"\n  By Total P&L:")
        for i, (name, r) in enumerate(by_pnl, 1):
            marker = " <-- BEST" if i == 1 else ""
            print(f"    {i}. {name}: ${r['total_pnl']:,.0f}{marker}")

        # Rank by Sharpe
        by_sharpe = sorted(valid_results, key=lambda x: x[1]['sharpe_ratio'], reverse=True)
        print(f"\n  By Sharpe Ratio:")
        for i, (name, r) in enumerate(by_sharpe, 1):
            marker = " <-- BEST" if i == 1 else ""
            print(f"    {i}. {name}: {r['sharpe_ratio']:.2f}{marker}")

        # Rank by Win Rate
        by_winrate = sorted(valid_results, key=lambda x: x[1]['win_rate'], reverse=True)
        print(f"\n  By Win Rate:")
        for i, (name, r) in enumerate(by_winrate, 1):
            marker = " <-- BEST" if i == 1 else ""
            print(f"    {i}. {name}: {r['win_rate']:.1f}%{marker}")

        # Rank by Losses Avoided
        by_losses = sorted(valid_results, key=lambda x: x[1]['skipped_would_be_losses'], reverse=True)
        print(f"\n  By Losses Avoided:")
        for i, (name, r) in enumerate(by_losses, 1):
            marker = " <-- BEST" if i == 1 else ""
            losses = r['skipped_would_be_losses']
            avoided = abs(r['skipped_pnl_avoided'])
            print(f"    {i}. {name}: {losses} trades (${avoided:,.0f} saved){marker}")

        # Calculate scores
        for name, r in valid_results:
            score = 0
            if r == by_pnl[0][1]: score += 3
            if r == by_sharpe[0][1]: score += 2
            if r == by_winrate[0][1]: score += 1
            if r == by_losses[0][1]: score += 1

            if name == 'ML Only':
                ml_score = score
            elif name == 'Oracle Only':
                oracle_score = score
            elif name == 'COMBINED':
                combined_score = score

    print(f"\n  SCORES:")
    print(f"    ML Only:      {ml_score}")
    print(f"    Oracle Only:  {oracle_score}")
    print(f"    COMBINED:     {combined_score}")

    # Determine winner
    scores = [('ML Only', ml_score), ('Oracle Only', oracle_score), ('COMBINED', combined_score)]
    scores = [(n, s) for n, s in scores if s > 0]
    if scores:
        scores.sort(key=lambda x: x[1], reverse=True)
        winner = scores[0][0]
        if winner == 'COMBINED':
            reason = "ML + Oracle together outperforms either alone (synergy effect)"
        elif winner == 'ML Only':
            reason = "Pure ML pattern recognition performed best"
        else:
            reason = "Oracle's multi-factor analysis won"
    else:
        winner = "BASELINE"
        reason = "Advisors did not improve on baseline"

    print(f"\n  WINNER: {winner}")
    print(f"  Reason: {reason}")

    # =========================================================================
    # Recommendations
    # =========================================================================
    print("\n" + "-" * 80)
    print("RECOMMENDATIONS")
    print("-" * 80)

    baseline_avg = baseline_pnl / baseline_total if baseline_total else 0

    if combined_results:
        combined_improvement = combined_results['avg_pnl'] - baseline_avg
        skip_rate = combined_results['skipped_trades'] / len(all_trades) * 100
        reduced_rate = combined_results.get('reduced_trades', 0) / len(all_trades) * 100

        print(f"\n  COMBINED (FORTRESS Mode) Analysis:")
        print(f"    - Skips {skip_rate:.1f}% of trades")
        print(f"    - Uses reduced position on {reduced_rate:.1f}% of trades")
        print(f"    - Avoided {combined_results['skipped_would_be_losses']} losing trades")
        print(f"    - Saved ${abs(combined_results['skipped_pnl_avoided']):,.0f} from avoided losses")

        if combined_improvement > 0:
            print(f"    - Improves avg trade by ${combined_improvement:,.0f} vs baseline")
        else:
            print(f"    - Avg trade is ${abs(combined_improvement):,.0f} WORSE than baseline")

        # Final recommendation
        print(f"\n  RECOMMENDATION:")
        if combined_score >= max(ml_score, oracle_score):
            print(f"    USE COMBINED MODE (current FORTRESS setup) - best overall performance")
        elif ml_score > oracle_score:
            print(f"    Consider ML-only mode - better pattern recognition")
        elif oracle_score > ml_score:
            print(f"    Oracle-only mode shows promise - rely more on GEX/VIX signals")
        else:
            print(f"    Current setup is reasonable - continue monitoring")

    print("\n" + "=" * 80)

    return {
        'baseline': baseline_results,
        'ml_results': ml_results,
        'oracle_results': oracle_results,
        'combined_results': combined_results,
        'comparison': {
            'ml_score': ml_score,
            'oracle_score': oracle_score,
            'combined_score': combined_score,
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
