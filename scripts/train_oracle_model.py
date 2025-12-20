#!/usr/bin/env python3
"""
ORACLE MODEL TRAINING SCRIPT
=============================
Run this in Render Shell to manually train the Oracle ML model.

Usage:
    python scripts/train_oracle_model.py              # Train if needed
    python scripts/train_oracle_model.py --force      # Force retrain

This will:
1. Check training data availability (live outcomes → backtests → KRONOS)
2. Train the GradientBoostingClassifier model
3. Calibrate probabilities with isotonic regression
4. Save model to PostgreSQL database (persists across restarts)
5. Display training metrics
"""

import os
import sys
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def main():
    parser = argparse.ArgumentParser(description='Train Oracle ML Model')
    parser.add_argument('--force', action='store_true',
                       help='Force retrain even if model exists')
    args = parser.parse_args()

    print("=" * 60)
    print(" ORACLE MODEL TRAINING")
    print("=" * 60)

    try:
        from quant.oracle_advisor import (
            get_oracle, auto_train, get_training_status,
            get_pending_outcomes_count
        )

        # Get current status
        print("\n📊 Current Status:")
        status = get_training_status()

        print(f"  Model Trained: {status.get('model_trained')}")
        print(f"  Model Version: {status.get('model_version')}")
        print(f"  Model Source: {status.get('model_source')}")
        print(f"  DB Persistence: {status.get('db_persistence')}")
        print(f"  Pending Outcomes: {status.get('pending_outcomes')}")
        print(f"  Total Outcomes: {status.get('total_outcomes')}")

        if status.get('training_metrics'):
            print(f"  Current Accuracy: {status['training_metrics'].get('accuracy', 'N/A')}")

        # Check if training is needed
        needs_training = args.force or not status.get('model_trained') or not status.get('db_persistence')

        if not needs_training:
            print("\n✅ Model already trained and persisted in database.")
            print("   Use --force to retrain anyway.")
            return True

        # Train the model
        print("\n🎯 Starting Training...")
        print("-" * 40)

        result = auto_train(threshold_outcomes=50, force=args.force)

        if result.get('success'):
            print("\n✅ TRAINING COMPLETE!")
            print("-" * 40)

            print(f"  Method: {result.get('method', 'unknown')}")
            print(f"  Samples Used: {result.get('samples_used', 'N/A')}")

            if result.get('training_metrics'):
                metrics = result['training_metrics']
                print(f"\n  Training Metrics:")
                print(f"    Accuracy: {metrics.get('accuracy', 0):.1%}")
                print(f"    Precision: {metrics.get('precision', 0):.1%}")
                print(f"    Recall: {metrics.get('recall', 0):.1%}")
                print(f"    F1 Score: {metrics.get('f1_score', 0):.3f}")
                print(f"    AUC-ROC: {metrics.get('auc_roc', 0):.3f}")
                print(f"    Brier Score: {metrics.get('brier_score', 0):.3f}")

            # Verify persistence
            new_status = get_training_status()
            if new_status.get('db_persistence'):
                print("\n" + "=" * 60)
                print(" ✅ MODEL SAVED TO DATABASE - WILL SURVIVE RESTARTS")
                print("=" * 60)
            else:
                print("\n⚠️  WARNING: Model NOT saved to database!")
                print("   Check database connection and try again.")

            return True

        else:
            print(f"\n❌ Training failed: {result.get('reason', 'Unknown error')}")

            if result.get('reason') == 'insufficient_data':
                print("\n   Not enough training data. Options:")
                print("   1. Run more backtests")
                print("   2. Wait for live trading outcomes")
                print("   3. Check KRONOS memory table")

            return False

    except ImportError as e:
        print(f"\n❌ Import error: {e}")
        print("   Make sure all dependencies are installed.")
        return False

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
