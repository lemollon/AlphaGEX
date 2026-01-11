#!/usr/bin/env python3
"""
Train the GEX Directional ML Model
Run this on the production server where database is available.

Usage:
    python scripts/train_directional_ml.py --ticker SPX --start 2022-01-01
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from quant.gex_directional_ml import GEXDirectionalPredictor
from datetime import datetime
import argparse


def main():
    parser = argparse.ArgumentParser(description='Train GEX Directional ML Model')
    parser.add_argument('--ticker', type=str, default='SPX', help='Ticker to train on')
    parser.add_argument('--start', type=str, default='2022-01-01', help='Start date')
    parser.add_argument('--end', type=str, default=None, help='End date (default: today)')
    parser.add_argument('--output', type=str, default='models/gex_directional_model.joblib',
                        help='Output path for model')
    args = parser.parse_args()

    end_date = args.end or datetime.now().strftime('%Y-%m-%d')

    print("=" * 70)
    print("🧠 GEX DIRECTIONAL ML MODEL TRAINER")
    print("=" * 70)
    print(f"\nTicker: {args.ticker}")
    print(f"Training period: {args.start} to {end_date}")
    print(f"Output: {args.output}")

    # Ensure output directory exists
    os.makedirs(os.path.dirname(args.output), exist_ok=True)

    # Initialize and train
    predictor = GEXDirectionalPredictor(ticker=args.ticker)

    try:
        result = predictor.train(
            start_date=args.start,
            end_date=end_date,
            n_splits=5
        )

        print(f"\n✅ Training Complete!")
        print(f"   Accuracy: {result.accuracy:.1%}")
        print(f"   Training samples: {result.training_samples}")

        # Save model to file
        predictor.save_model(args.output)
        print(f"\n💾 Model saved to: {args.output}")

        # Also save to database for Render persistence
        print("💾 Saving to database for persistence...")
        predictor.save_to_db(
            metrics={'accuracy': result.accuracy},
            training_records=result.training_samples
        )
        print("   Model saved to database (persists across Render deploys)")

        # Print feature importance
        if result.feature_importance:
            print(f"\n📊 Top Feature Importances:")
            sorted_features = sorted(result.feature_importance.items(),
                                    key=lambda x: x[1], reverse=True)[:10]
            for feat, imp in sorted_features:
                print(f"   {feat}: {imp:.3f}")

        return True

    except Exception as e:
        print(f"\n❌ Training failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
