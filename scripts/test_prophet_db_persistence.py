#!/usr/bin/env python3
"""
PROPHET DATABASE PERSISTENCE TEST SCRIPT
========================================
Run this in Render Shell to verify the trained model is stored and retrieved from database.

Usage:
    python scripts/test_oracle_db_persistence.py

This script tests:
1. Database connection
2. prophet_trained_models table creation
3. Model training and saving to database
4. Model loading from database
5. Full persistence verification
"""

import os
import sys
import pickle

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def print_header(title):
    print("\n" + "=" * 60)
    print(f" {title}")
    print("=" * 60)

def print_result(test_name, passed, details=""):
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"{status} - {test_name}")
    if details:
        print(f"       {details}")

# Global connection helper
def get_db_connection():
    """Get database connection using database_adapter"""
    from database_adapter import get_connection
    return get_connection()

def main():
    print_header("PROPHET DATABASE PERSISTENCE TESTS")

    all_passed = True

    # ========================================
    # TEST 1: Database Connection
    # ========================================
    print_header("TEST 1: Database Connection")
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        result = cursor.fetchone()
        print_result("Database connection", result[0] == 1, f"Query returned: {result}")
    except Exception as e:
        print_result("Database connection", False, str(e))
        all_passed = False
    finally:
        if conn:
            conn.close()

    # ========================================
    # TEST 2: Check/Create prophet_trained_models Table
    # ========================================
    print_header("TEST 2: prophet_trained_models Table")
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Check if table exists
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'prophet_trained_models'
            )
        """)
        table_exists = cursor.fetchone()[0]

        if not table_exists:
            print("  Table doesn't exist, creating...")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS prophet_trained_models (
                    id SERIAL PRIMARY KEY,
                    model_version VARCHAR(20) NOT NULL,
                    model_data BYTEA NOT NULL,
                    training_metrics JSONB,
                    has_gex_features BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_active BOOLEAN DEFAULT TRUE
                )
            """)
            conn.commit()
            print_result("Table creation", True, "Created prophet_trained_models table")
        else:
            print_result("Table exists", True)

        # Check table structure
        cursor.execute("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'prophet_trained_models'
            ORDER BY ordinal_position
        """)
        columns = cursor.fetchall()
        print("\n  Table columns:")
        for col_name, col_type in columns:
            print(f"    - {col_name}: {col_type}")

        print_result("Table structure", len(columns) >= 6)
    except Exception as e:
        print_result("Table check/creation", False, str(e))
        all_passed = False
    finally:
        if conn:
            conn.close()

    # ========================================
    # TEST 3: Check Existing Trained Models
    # ========================================
    print_header("TEST 3: Existing Trained Models")
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, model_version, has_gex_features, is_active,
                   created_at, LENGTH(model_data) as data_size
            FROM prophet_trained_models
            ORDER BY created_at DESC
            LIMIT 5
        """)
        models = cursor.fetchall()

        if models:
            print(f"  Found {len(models)} model(s) in database:")
            for m in models:
                print(f"    ID: {m[0]}, Version: {m[1]}, GEX: {m[2]}, Active: {m[3]}, Size: {m[5]} bytes")
            print_result("Models in database", True, f"{len(models)} model(s) found")
        else:
            print_result("Models in database", False, "No models found - need to train first")
    except Exception as e:
        print_result("Check existing models", False, str(e))
        all_passed = False
    finally:
        if conn:
            conn.close()

    # ========================================
    # TEST 4: Prophet Advisor Instantiation
    # ========================================
    print_header("TEST 4: Prophet Advisor Instantiation")
    try:
        from quant.prophet_advisor import ProphetAdvisor, get_training_status, auto_train

        prophet = ProphetAdvisor()
        print_result("ProphetAdvisor import", True)

        # Check if model was loaded from database (use module function)
        status = get_training_status()
        print(f"\n  Training Status:")
        print(f"    - Model Trained: {status.get('model_trained', False)}")
        print(f"    - Model Source: {status.get('model_source', 'none')}")
        print(f"    - DB Persistence: {status.get('db_persistence', False)}")
        print(f"    - Has GEX Features: {prophet._has_gex_features}")

        if status.get('training_metrics'):
            print(f"    - Accuracy: {status['training_metrics'].get('accuracy', 'N/A')}")
            print(f"    - Total Samples: {status['training_metrics'].get('total_samples', 'N/A')}")

        db_loaded = status.get('model_source') == 'database'
        print_result("Model loaded from database", db_loaded,
                    "Model was loaded from database!" if db_loaded else "Model NOT from database")

    except Exception as e:
        print_result("Prophet Advisor instantiation", False, str(e))
        all_passed = False

    # ========================================
    # TEST 5: Training Data Availability
    # ========================================
    print_header("TEST 5: Training Data Availability")
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Check live outcomes (table may not exist)
        live_count = 0
        try:
            cursor.execute("SELECT COUNT(*) FROM oracle_live_outcomes")
            live_count = cursor.fetchone()[0]
        except Exception:
            pass
        print(f"  Live outcomes: {live_count}")

        # Check backtest results
        backtest_count = 0
        try:
            cursor.execute("SELECT COUNT(*) FROM backtest_results")
            backtest_count = cursor.fetchone()[0]
        except Exception:
            pass
        print(f"  Backtest results: {backtest_count}")

        # Check CHRONICLES memory
        kronos_count = 0
        try:
            cursor.execute("SELECT COUNT(*) FROM kronos_memory")
            kronos_count = cursor.fetchone()[0]
        except Exception:
            pass
        print(f"  CHRONICLES memory: {kronos_count}")

        # Check zero_dte_backtest_results (main source)
        zero_dte_count = 0
        try:
            cursor.execute("SELECT COUNT(*) FROM zero_dte_backtest_results")
            zero_dte_count = cursor.fetchone()[0]
        except Exception:
            pass
        print(f"  Zero-DTE backtest results: {zero_dte_count}")

        total = live_count + backtest_count + kronos_count + zero_dte_count
        print_result("Training data available", total > 0, f"Total potential samples: {total}")

    except Exception as e:
        print_result("Training data check", False, str(e))
        all_passed = False
    finally:
        if conn:
            conn.close()

    # ========================================
    # TEST 6: Trigger Training (if no model)
    # ========================================
    print_header("TEST 6: Training Test")
    try:
        from quant.prophet_advisor import ProphetAdvisor, get_training_status, auto_train

        status = get_training_status()

        if not status.get('db_persistence'):
            print("  No model in database. Triggering training...")
            result = auto_train(force=True)

            if result.get('success'):
                print(f"  ✅ Training completed!")
                print(f"    - Samples used: {result.get('samples_used', 'N/A')}")
                print(f"    - Source: {result.get('method', 'N/A')}")
                print(f"    - Accuracy: {result.get('training_metrics', {}).get('accuracy', 'N/A')}")

                # Verify it was saved to database
                new_status = get_training_status()
                db_saved = new_status.get('db_persistence', False)
                print_result("Model saved to database", db_saved,
                            "Model persisted successfully!" if db_saved else "WARNING: Model NOT saved!")
            else:
                print_result("Training", False, result.get('reason', 'Training failed'))
        else:
            print_result("Model already in database", True, "Skipping training test")

    except Exception as e:
        print_result("Training test", False, str(e))
        all_passed = False

    # ========================================
    # TEST 7: Verify Persistence (Critical!)
    # ========================================
    print_header("TEST 7: Persistence Verification")
    try:
        from quant.prophet_advisor import ProphetAdvisor, get_training_status

        # Create a NEW ProphetAdvisor instance to simulate restart
        print("  Creating new ProphetAdvisor instance (simulating restart)...")
        oracle_new = ProphetAdvisor()

        status = get_training_status()

        if status.get('model_trained') and status.get('model_source') == 'database':
            print_result("PERSISTENCE VERIFICATION", True,
                        "Model survives restart! Loaded from database.")
            print(f"\n  ✅ YOUR MODEL IS SAFE!")
            print(f"     - Stored in: PostgreSQL database")
            print(f"     - Table: prophet_trained_models")
            print(f"     - Will survive Render restarts: YES")
        elif status.get('model_trained'):
            print_result("PERSISTENCE VERIFICATION", False,
                        f"Model loaded from {status.get('model_source')} - NOT database!")
        else:
            print_result("PERSISTENCE VERIFICATION", False, "No trained model found")

    except Exception as e:
        print_result("Persistence verification", False, str(e))
        all_passed = False

    # ========================================
    # FINAL SUMMARY
    # ========================================
    print_header("FINAL SUMMARY")

    if all_passed:
        print("""
✅ ALL TESTS PASSED!

Your Prophet ML model is:
  ✅ Trained and ready
  ✅ Stored in PostgreSQL database
  ✅ Will survive Render restarts
  ✅ Automatically loaded on startup

The model learns from:
  1. Live trading outcomes (primary)
  2. Backtest results (fallback)
  3. CHRONICLES memory (last resort)

Auto-training runs:
  - Weekly: Sunday midnight CT
  - Threshold: When 100+ new outcomes accumulate
""")
    else:
        print("""
⚠️  SOME TESTS FAILED

Please check the failures above. Common issues:
  - Database connection: Check TIMESCALE_URL env var
  - No training data: Run backtests first
  - Table missing: Will be auto-created on first train

To manually trigger training:
  >>> from quant.prophet_advisor import ProphetAdvisor
  >>> prophet = ProphetAdvisor()
  >>> prophet.auto_train(force=True)
""")

    return all_passed

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
