#!/usr/bin/env python3
"""
Train GEX Probability Models
============================

Trains all 5 GEX probability models for the Apache Directional Strategy:
1. Direction Probability (UP/DOWN/FLAT)
2. Flip Gravity (probability price moves toward flip point)
3. Magnet Attraction (probability price reaches nearest magnet)
4. Volatility Estimate (expected price range)
5. Pin Zone Behavior (probability of staying between magnets)

Usage:
    python scripts/train_gex_probability_models.py
    python scripts/train_gex_probability_models.py --symbols SPX SPY --start 2020-01-01

Prerequisites:
    - GEX structure data populated in database (run populate_gex_structures.py first)
    - VIX data populated (automatic if gex_hypothesis_validation.py was run)

Output:
    - Trained models saved to models/gex_signal_generator.joblib
    - Ready for use in Apache Directional Strategy

Author: AlphaGEX Quant
"""

import os
import sys
import argparse
from pathlib import Path

# Add parent directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / '.env')


def check_prerequisites():
    """Check that required data exists in database"""
    from quant.gex_probability_models import get_connection

    print("Checking prerequisites...")

    conn = get_connection()
    cursor = conn.cursor()

    # Check gex_structure_daily table
    cursor.execute("""
        SELECT COUNT(*), MIN(trade_date), MAX(trade_date)
        FROM gex_structure_daily
    """)
    gex_count, gex_min, gex_max = cursor.fetchone()

    print(f"  gex_structure_daily: {gex_count} records ({gex_min} to {gex_max})")

    if gex_count == 0:
        print("\n  ERROR: No GEX structure data found!")
        print("  Please run: python scripts/populate_gex_structures.py")
        return False

    # Check for non-zero price data
    cursor.execute("""
        SELECT COUNT(*)
        FROM gex_structure_daily
        WHERE price_range_pct > 0
    """)
    valid_price_count = cursor.fetchone()[0]
    print(f"  Records with valid price data: {valid_price_count}")

    if valid_price_count < 100:
        print("\n  WARNING: Limited price data. ML models may have poor accuracy.")
        print("  Consider re-running populate_gex_structures.py with proper OHLC data.")

    # Check VIX data
    cursor.execute("""
        SELECT COUNT(*), MIN(trade_date), MAX(trade_date)
        FROM vix_daily
    """)
    vix_count, vix_min, vix_max = cursor.fetchone()

    print(f"  vix_daily: {vix_count} records ({vix_min} to {vix_max})")

    if vix_count == 0:
        print("\n  WARNING: No VIX data found. VIX features will be imputed.")
        print("  Consider running: python scripts/gex_hypothesis_validation.py")

    conn.close()

    return True


def main():
    parser = argparse.ArgumentParser(description='Train GEX Probability Models')
    parser.add_argument('--symbols', type=str, nargs='+', default=['SPX', 'SPY'],
                        help='Symbols to train on (default: SPX SPY)')
    parser.add_argument('--start', type=str, default='2020-01-01',
                        help='Training start date (default: 2020-01-01)')
    parser.add_argument('--end', type=str, default=None,
                        help='Training end date (default: today)')
    parser.add_argument('--output', type=str, default='models/gex_signal_generator.joblib',
                        help='Output model path')
    parser.add_argument('--skip-checks', action='store_true',
                        help='Skip prerequisite checks')
    args = parser.parse_args()

    print("=" * 70)
    print("GEX PROBABILITY MODELS TRAINER")
    print("=" * 70)
    print(f"\nSymbols: {args.symbols}")
    print(f"Date range: {args.start} to {args.end or 'present'}")
    print(f"Output: {args.output}")

    # Check prerequisites
    if not args.skip_checks:
        if not check_prerequisites():
            print("\nExiting due to missing prerequisites.")
            sys.exit(1)

    # Import and train
    from quant.gex_probability_models import GEXSignalGenerator

    print("\n" + "-" * 70)
    print("Starting model training...")

    generator = GEXSignalGenerator()

    try:
        results = generator.train(
            symbols=args.symbols,
            start_date=args.start,
            end_date=args.end
        )

        # Save models to file
        generator.save(args.output)

        # Also save to database for Render persistence
        print("\nSaving to database for persistence...")
        generator.save_to_db(
            metrics=results if isinstance(results, dict) else None,
            training_records=results.get('total_records') if isinstance(results, dict) else None
        )

        print("\n" + "=" * 70)
        print("TRAINING COMPLETE")
        print("=" * 70)
        print(f"\nModels saved to: {args.output}")
        print("Models also saved to database (persists across Render deploys)")
        print("\nUsage in code:")
        print("  from quant.gex_probability_models import GEXSignalGenerator")
        print("  generator = GEXSignalGenerator()")
        print("  generator.load_from_db()  # Load from database")
        print("  signal = generator.predict(features)")
        print("  print(signal.trade_recommendation)")

    except Exception as e:
        print(f"\nERROR during training: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
