#!/usr/bin/env python3
"""
Prometheus Health Check Script
==============================

Verifies that all Prometheus components are functioning correctly:
1. ML libraries available
2. Database connectivity
3. Core classes can be instantiated
4. Training data can be loaded
5. Predictions can be made (if model exists)

Run: python scripts/prometheus_health_check.py
"""

import os
import sys
import traceback

# Add project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def print_status(name: str, passed: bool, message: str = ""):
    status = "✅ PASS" if passed else "❌ FAIL"
    msg = f" - {message}" if message else ""
    print(f"  {status}: {name}{msg}")
    return passed


def check_ml_libraries():
    """Check if ML libraries are available"""
    print("\n1. ML Libraries")
    print("-" * 40)

    passed = True

    try:
        import numpy as np
        print_status("NumPy", True, f"v{np.__version__}")
    except ImportError as e:
        passed = print_status("NumPy", False, str(e)) and passed

    try:
        import sklearn
        print_status("scikit-learn", True, f"v{sklearn.__version__}")
    except ImportError as e:
        passed = print_status("scikit-learn", False, str(e)) and passed

    return passed


def check_database():
    """Check database connectivity"""
    print("\n2. Database Connection")
    print("-" * 40)

    try:
        from database_adapter import get_connection
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        conn.close()
        return print_status("Connection", True)
    except Exception as e:
        return print_status("Connection", False, str(e))


def check_database_tables():
    """Check required database tables exist"""
    print("\n3. Database Tables")
    print("-" * 40)

    required_tables = [
        'spx_wheel_ml_outcomes',
        'prometheus_predictions',
        'prometheus_training_history',
        'prometheus_logs',
        'prometheus_models'
    ]

    all_exist = True

    try:
        from database_adapter import get_connection
        conn = get_connection()
        cursor = conn.cursor()

        for table in required_tables:
            cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = %s
                )
            """, (table,))
            exists = cursor.fetchone()[0]
            all_exist = print_status(table, exists, "exists" if exists else "MISSING") and all_exist

        conn.close()
    except Exception as e:
        print_status("Table check", False, str(e))
        return False

    return all_exist


def check_prometheus_imports():
    """Check Prometheus modules can be imported"""
    print("\n4. Prometheus Modules")
    print("-" * 40)

    passed = True

    try:
        from trading.prometheus_ml import (
            PrometheusFeatures,
            PrometheusOutcome,
            PrometheusPrediction,
            PrometheusTrainer,
            ML_AVAILABLE,
            DB_AVAILABLE
        )
        print_status("prometheus_ml", True)
        print_status("ML_AVAILABLE", ML_AVAILABLE)
        print_status("DB_AVAILABLE", DB_AVAILABLE)
    except Exception as e:
        passed = print_status("prometheus_ml", False, str(e)) and passed

    try:
        from trading.prometheus_outcome_tracker import PrometheusOutcomeTracker
        print_status("prometheus_outcome_tracker", True)
    except Exception as e:
        passed = print_status("prometheus_outcome_tracker", False, str(e)) and passed

    return passed


def check_trainer_instantiation():
    """Check that PrometheusTrainer can be instantiated"""
    print("\n5. Trainer Instantiation")
    print("-" * 40)

    try:
        from trading.prometheus_ml import get_prometheus_trainer
        trainer = get_prometheus_trainer()

        print_status("Trainer created", True)
        print_status("Model loaded", trainer.model is not None,
                    f"v{trainer.model_version}" if trainer.model else "No model")
        print_status("Scaler loaded", trainer.scaler is not None)
        print_status("Is calibrated", trainer.is_calibrated)

        return True
    except Exception as e:
        print_status("Trainer", False, str(e))
        traceback.print_exc()
        return False


def check_training_data():
    """Check training data availability"""
    print("\n6. Training Data")
    print("-" * 40)

    try:
        from database_adapter import get_connection
        conn = get_connection()
        cursor = conn.cursor()

        # Count total outcomes
        cursor.execute("SELECT COUNT(*) FROM spx_wheel_ml_outcomes")
        total = cursor.fetchone()[0]
        print_status("Total entries", True, str(total))

        # Count completed outcomes
        cursor.execute("SELECT COUNT(*) FROM spx_wheel_ml_outcomes WHERE outcome IS NOT NULL")
        completed = cursor.fetchone()[0]
        print_status("With outcomes", True, str(completed))

        # Count wins/losses
        cursor.execute("SELECT outcome, COUNT(*) FROM spx_wheel_ml_outcomes WHERE outcome IS NOT NULL GROUP BY outcome")
        outcomes = dict(cursor.fetchall())
        wins = outcomes.get('WIN', 0)
        losses = outcomes.get('LOSS', 0)
        print_status("Wins/Losses", True, f"{wins}W / {losses}L")

        # Can train?
        can_train = completed >= 30
        print_status("Can train (30+ needed)", can_train, f"{completed} available")

        conn.close()
        return True
    except Exception as e:
        print_status("Training data check", False, str(e))
        return False


def check_prediction():
    """Check that predictions work (if model exists)"""
    print("\n7. Prediction Test")
    print("-" * 40)

    try:
        from trading.prometheus_ml import get_prometheus_trainer, PrometheusFeatures

        trainer = get_prometheus_trainer()

        if trainer.model is None:
            print_status("Prediction", True, "Skipped - no model trained")
            return True

        # Create test features
        test_features = PrometheusFeatures(
            trade_date="2025-01-06",
            strike=5800.0,
            underlying_price=5950.0,
            dte=0,
            delta=-0.15,
            premium=5.50,
            iv=0.18,
            iv_rank=45.0,
            vix=16.5,
            vix_percentile=40.0,
            vix_term_structure=-1.2,
            put_wall_distance_pct=2.5,
            call_wall_distance_pct=3.0,
            net_gex=5e9,
            spx_20d_return=1.5,
            spx_5d_return=0.8,
            spx_distance_from_high=0.5,
            premium_to_strike_pct=0.095,
            annualized_return=35.0
        )

        prediction = trainer.predict(test_features, trade_id="HEALTH-CHECK")

        print_status("Prediction made", True)
        print_status("Win probability", True, f"{prediction.win_probability:.1%}")
        print_status("Recommendation", True, prediction.recommendation.value)

        return True
    except Exception as e:
        print_status("Prediction", False, str(e))
        traceback.print_exc()
        return False


def check_outcome_tracker():
    """Check outcome tracker functionality"""
    print("\n8. Outcome Tracker")
    print("-" * 40)

    try:
        from trading.prometheus_outcome_tracker import get_prometheus_outcome_tracker

        tracker = get_prometheus_outcome_tracker()
        print_status("Tracker created", True)

        # Get market features
        features = tracker.get_current_market_features()
        print_status("Market data fetched", True, f"VIX={features.get('vix', 'N/A')}")

        return True
    except Exception as e:
        print_status("Outcome tracker", False, str(e))
        return False


def check_api_routes():
    """Verify API route file is valid Python"""
    print("\n9. API Routes")
    print("-" * 40)

    try:
        # Just check syntax by compiling the file
        with open('backend/api/routes/prometheus_routes.py', 'r') as f:
            code = f.read()
        compile(code, 'prometheus_routes.py', 'exec')
        print_status("Routes syntax valid", True)

        # Count endpoints
        import re
        endpoints = re.findall(r'@router\.(get|post|put|delete)\("([^"]+)"', code)
        print_status("Endpoints defined", True, str(len(endpoints)))

        return True
    except SyntaxError as e:
        print_status("Routes syntax", False, str(e))
        return False
    except Exception as e:
        print_status("Routes check", False, str(e))
        return False


def main():
    print("=" * 50)
    print("PROMETHEUS HEALTH CHECK")
    print("=" * 50)

    results = []

    # Run all checks
    results.append(("ML Libraries", check_ml_libraries()))
    results.append(("Database", check_database()))
    results.append(("Tables", check_database_tables()))
    results.append(("Imports", check_prometheus_imports()))
    results.append(("Trainer", check_trainer_instantiation()))
    results.append(("Training Data", check_training_data()))
    results.append(("Prediction", check_prediction()))
    results.append(("Outcome Tracker", check_outcome_tracker()))
    results.append(("API Routes", check_api_routes()))

    # Summary
    print("\n" + "=" * 50)
    print("SUMMARY")
    print("=" * 50)

    passed = sum(1 for _, r in results if r)
    total = len(results)

    for name, result in results:
        status = "✅" if result else "❌"
        print(f"  {status} {name}")

    print()
    print(f"Result: {passed}/{total} checks passed")

    if passed == total:
        print("\n🎉 Prometheus is fully operational!")
        return 0
    else:
        print("\n⚠️  Some checks failed. Review the output above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
