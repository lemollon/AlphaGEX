#!/usr/bin/env python3
"""
PROMETHEUS Training Data Generator
====================================

Generates ML training data for Prometheus from:
1. Historical backtest results
2. SPX Wheel trade outcomes from database
3. Synthetic data for bootstrapping

Author: AlphaGEX Quant
"""

import os
import sys
import json
import random
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

# Add project root
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

logger = logging.getLogger(__name__)

# ML imports
try:
    import numpy as np
    import pandas as pd
    ML_AVAILABLE = True
except ImportError:
    ML_AVAILABLE = False
    np = None
    pd = None

# Database
try:
    from database_adapter import get_connection
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False

# Prometheus ML
try:
    from trading.prometheus_ml import (
        PrometheusFeatures,
        PrometheusOutcome,
        get_prometheus_trainer
    )
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False


def generate_synthetic_training_data(
    n_samples: int = 100,
    win_rate: float = 0.68,
    seed: int = 42
) -> List['PrometheusOutcome']:
    """
    Generate synthetic training data for Prometheus.

    This creates realistic-looking SPX wheel outcomes based on
    known patterns in options selling.

    Args:
        n_samples: Number of synthetic trades to generate
        win_rate: Target win rate for the synthetic data
        seed: Random seed for reproducibility

    Returns:
        List of PrometheusOutcome objects
    """
    if not ML_AVAILABLE or not PROMETHEUS_AVAILABLE:
        print("Error: ML libraries or Prometheus not available")
        return []

    np.random.seed(seed)
    outcomes = []

    for i in range(n_samples):
        # Generate realistic feature values

        # VIX cycles between 12-35, with occasional spikes
        vix_base = np.random.uniform(14, 28)
        vix_spike = np.random.random() < 0.1  # 10% chance of spike
        vix = vix_base + (np.random.uniform(5, 15) if vix_spike else 0)

        # IV Rank correlates somewhat with VIX
        iv_rank = min(100, max(0, (vix - 12) * 3 + np.random.uniform(-10, 10)))

        # VIX term structure - usually contango, sometimes backwardation
        backwardation = np.random.random() < 0.15  # 15% chance
        vix_term_structure = np.random.uniform(2, 5) if backwardation else np.random.uniform(-4, -0.5)

        # SPX price around 5800-6200 range
        underlying_price = np.random.uniform(5800, 6200)

        # Strike selection - typically 2-5% OTM
        otm_pct = np.random.uniform(1.5, 4.0)
        strike = underlying_price * (1 - otm_pct / 100)

        # Delta for puts at this OTM level
        delta = -np.random.uniform(0.08, 0.20)

        # DTE - typically 0-3 for 0DTE trades
        dte = np.random.choice([0, 1, 2, 3], p=[0.4, 0.3, 0.2, 0.1])

        # Premium based on VIX and DTE
        base_premium = (vix / 20) * (dte + 0.5) * 2
        premium = max(1.0, base_premium + np.random.uniform(-1, 2))

        # IV
        iv = vix / 100 + np.random.uniform(-0.02, 0.05)

        # VIX percentile
        vix_percentile = min(100, max(0, (vix - 12) / 30 * 100))

        # GEX features
        net_gex = np.random.uniform(-5e9, 10e9)
        positive_gex = net_gex > 0

        # Put wall distance - positive GEX = stronger support
        put_wall_distance = np.random.uniform(1, 6) if positive_gex else np.random.uniform(3, 10)
        call_wall_distance = np.random.uniform(2, 8)

        # Market momentum
        spx_20d_return = np.random.normal(0, 3)  # Mean 0, std 3%
        spx_5d_return = np.random.normal(0, 1.5)  # Mean 0, std 1.5%
        spx_distance_from_high = np.random.uniform(0, 5)

        # Premium quality
        premium_to_strike = premium / strike * 100
        annualized_return = (premium_to_strike / 100) * (365 / max(dte, 0.5)) * 100

        # Determine win/loss based on realistic patterns
        # Higher win probability when:
        # - IV Rank > 50 (selling expensive options)
        # - VIX 18-30 (good premium, not extreme)
        # - Positive GEX (mean reversion)
        # - Close to put wall (support)
        # - After pullback (mean reversion)

        win_factors = 0

        if iv_rank > 50:
            win_factors += 0.05
        if 18 <= vix <= 30:
            win_factors += 0.03
        if positive_gex:
            win_factors += 0.04
        if put_wall_distance < 3:
            win_factors += 0.03
        if spx_5d_return < -1:  # Recent pullback
            win_factors += 0.02
        if vix_term_structure < 0:  # Contango
            win_factors += 0.02

        # Penalty factors
        if vix > 35:
            win_factors -= 0.08  # Extreme volatility is risky
        if vix_term_structure > 2:
            win_factors -= 0.05  # Backwardation = fear
        if spx_5d_return > 3:
            win_factors -= 0.02  # Extended moves

        # Calculate final win probability
        base_win_prob = win_rate
        actual_win_prob = min(0.95, max(0.2, base_win_prob + win_factors))

        is_win = np.random.random() < actual_win_prob

        # Calculate P&L
        contracts = max(1, int(np.random.uniform(1, 10)))
        if is_win:
            pnl = premium * 100 * contracts  # Keep full premium
            max_drawdown = -premium * 100 * contracts * np.random.uniform(0.1, 0.5)
            settlement_price = strike + np.random.uniform(5, 50)  # Expired OTM
        else:
            # Loss - ITM at expiration
            intrinsic = np.random.uniform(5, 50)
            pnl = (premium - intrinsic) * 100 * contracts
            max_drawdown = pnl * np.random.uniform(1.2, 2.0)
            settlement_price = strike - intrinsic

        # Create date
        base_date = datetime(2024, 1, 1) + timedelta(days=i)
        trade_date = base_date.strftime('%Y-%m-%d')

        features = PrometheusFeatures(
            trade_date=trade_date,
            strike=round(strike, 2),
            underlying_price=round(underlying_price, 2),
            dte=dte,
            delta=round(delta, 4),
            premium=round(premium, 2),
            iv=round(iv, 4),
            iv_rank=round(iv_rank, 1),
            vix=round(vix, 2),
            vix_percentile=round(vix_percentile, 1),
            vix_term_structure=round(vix_term_structure, 2),
            put_wall_distance_pct=round(put_wall_distance, 2),
            call_wall_distance_pct=round(call_wall_distance, 2),
            net_gex=round(net_gex, 0),
            spx_20d_return=round(spx_20d_return, 2),
            spx_5d_return=round(spx_5d_return, 2),
            spx_distance_from_high=round(spx_distance_from_high, 2),
            premium_to_strike_pct=round(premium_to_strike, 4),
            annualized_return=round(annualized_return, 1)
        )

        outcomes.append(PrometheusOutcome(
            trade_id=f"SYNTH-{i:04d}",
            features=features,
            outcome="WIN" if is_win else "LOSS",
            pnl=round(pnl, 2),
            max_drawdown=round(max_drawdown, 2),
            settlement_price=round(settlement_price, 2)
        ))

    return outcomes


def save_training_data_to_db(outcomes: List['PrometheusOutcome']) -> int:
    """
    Save training data to the database.

    Args:
        outcomes: List of PrometheusOutcome objects

    Returns:
        Number of records inserted
    """
    if not DB_AVAILABLE:
        print("Error: Database not available")
        return 0

    if not outcomes:
        print("No outcomes to save")
        return 0

    try:
        conn = get_connection()
        cursor = conn.cursor()

        inserted = 0
        for outcome in outcomes:
            f = outcome.features

            try:
                cursor.execute('''
                    INSERT INTO spx_wheel_ml_outcomes (
                        trade_id, trade_date, strike, underlying_price, dte, delta, premium,
                        iv, iv_rank, vix, vix_percentile, vix_term_structure,
                        put_wall_distance_pct, call_wall_distance_pct, net_gex,
                        spx_20d_return, spx_5d_return, spx_distance_from_high,
                        premium_to_strike_pct, annualized_return, outcome, pnl,
                        max_drawdown, settlement_price
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (trade_id) DO NOTHING
                ''', (
                    outcome.trade_id, f.trade_date, f.strike, f.underlying_price,
                    f.dte, f.delta, f.premium, f.iv, f.iv_rank, f.vix, f.vix_percentile,
                    f.vix_term_structure, f.put_wall_distance_pct, f.call_wall_distance_pct,
                    f.net_gex, f.spx_20d_return, f.spx_5d_return, f.spx_distance_from_high,
                    f.premium_to_strike_pct, f.annualized_return, outcome.outcome, outcome.pnl,
                    outcome.max_drawdown, outcome.settlement_price
                ))
                inserted += 1
            except Exception as e:
                logger.warning(f"Failed to insert {outcome.trade_id}: {e}")

        conn.commit()
        conn.close()

        print(f"✓ Inserted {inserted} training records")
        return inserted

    except Exception as e:
        print(f"Error saving to database: {e}")
        return 0


def extract_from_backtest_results(backtest_id: str = None) -> List['PrometheusOutcome']:
    """
    Extract training data from stored backtest results.

    Args:
        backtest_id: Optional specific backtest to extract from

    Returns:
        List of PrometheusOutcome objects
    """
    if not DB_AVAILABLE or not PROMETHEUS_AVAILABLE:
        print("Error: Database or Prometheus not available")
        return []

    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Get trades from backtest tables
        if backtest_id:
            cursor.execute('''
                SELECT t.*, r.vix_avg
                FROM spx_wheel_backtest_trades t
                JOIN spx_wheel_backtest_runs r ON t.run_id = r.id
                WHERE r.id = %s
            ''', (backtest_id,))
        else:
            cursor.execute('''
                SELECT t.*, r.vix_avg
                FROM spx_wheel_backtest_trades t
                JOIN spx_wheel_backtest_runs r ON t.run_id = r.id
                ORDER BY t.trade_date DESC
                LIMIT 500
            ''')

        rows = cursor.fetchall()
        conn.close()

        outcomes = []
        for row in rows:
            # Convert backtest trade to PrometheusOutcome
            # Note: This is a simplified extraction - actual implementation
            # would need to match the exact schema
            pass

        return outcomes

    except Exception as e:
        print(f"Error extracting backtest data: {e}")
        return []


def train_prometheus_with_data(outcomes: List['PrometheusOutcome']) -> Dict:
    """
    Train Prometheus with the provided outcomes.

    Args:
        outcomes: List of training outcomes

    Returns:
        Training result dict
    """
    if not PROMETHEUS_AVAILABLE:
        return {'error': 'Prometheus not available'}

    if len(outcomes) < 30:
        return {'error': f'Need at least 30 outcomes, have {len(outcomes)}'}

    trainer = get_prometheus_trainer()
    result = trainer.train(outcomes, calibrate=True, use_time_series_cv=True)

    return result


def main():
    """Main entry point for training data generation and model training"""
    print("=" * 60)
    print("PROMETHEUS Training Data Generator")
    print("=" * 60)
    print()

    # Check availability
    print(f"ML Available: {ML_AVAILABLE}")
    print(f"DB Available: {DB_AVAILABLE}")
    print(f"Prometheus Available: {PROMETHEUS_AVAILABLE}")
    print()

    if not ML_AVAILABLE or not PROMETHEUS_AVAILABLE:
        print("Error: Required dependencies not available")
        return

    # Generate synthetic data
    print("Generating synthetic training data...")
    outcomes = generate_synthetic_training_data(n_samples=100, win_rate=0.68)
    print(f"Generated {len(outcomes)} synthetic outcomes")

    # Calculate actual win rate
    wins = sum(1 for o in outcomes if o.is_win())
    print(f"Actual win rate: {wins/len(outcomes):.1%}")
    print()

    # Save to database if available
    if DB_AVAILABLE:
        print("Saving to database...")
        inserted = save_training_data_to_db(outcomes)
        print(f"Saved {inserted} records to database")
        print()

    # Train the model
    print("Training Prometheus model...")
    result = train_prometheus_with_data(outcomes)

    if result.get('success'):
        print("✅ Training successful!")
        print(f"   Model version: {result.get('model_version')}")
        metrics = result.get('metrics', {})
        print(f"   Accuracy: {metrics.get('accuracy', 0):.1%}")
        print(f"   CV Score: {metrics.get('cv_accuracy_mean', 0):.1%}")
        print(f"   Calibrated: {metrics.get('is_calibrated', False)}")
        print()
        print("Honest Assessment:")
        print(f"   {result.get('honest_assessment', 'N/A')}")
    else:
        print(f"❌ Training failed: {result.get('error')}")

    print()
    print("=" * 60)


if __name__ == "__main__":
    main()
