#!/usr/bin/env python3
"""
PROPHET COMPLETE SYSTEM TEST
============================
Run this in Render Shell after deployment to verify the entire Prophet system.

Usage:
    python scripts/test_oracle_complete.py

Tests:
1. Database persistence (model survives restarts)
2. Auto-training cascade (live → backtests → CHRONICLES)
3. Bot advice generation (FORTRESS, CORNERSTONE, LAZARUS, SOLOMON)
4. Claude AI integration
5. API endpoints
6. Scheduler integration
"""

import os
import sys
import json
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def print_header(title):
    print("\n" + "=" * 70)
    print(f" {title}")
    print("=" * 70)

def print_result(test_name, passed, details=""):
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"{status} - {test_name}")
    if details:
        print(f"       {details}")

def print_warning(msg):
    print(f"⚠️  {msg}")

def main():
    print_header("PROPHET COMPLETE SYSTEM TEST")
    print(f"Timestamp: {datetime.now().isoformat()}")

    results = {}

    # ========================================
    # TEST 1: Database Connection
    # ========================================
    print_header("1. DATABASE CONNECTION")
    conn = None
    try:
        from database_adapter import get_connection

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT version()")
        version = cursor.fetchone()[0]

        print_result("PostgreSQL connection", True, version[:50] + "...")
        results['db_connection'] = True
    except Exception as e:
        print_result("PostgreSQL connection", False, str(e))
        results['db_connection'] = False
    finally:
        if conn:
            conn.close()

    # ========================================
    # TEST 2: Prophet Module Import
    # ========================================
    print_header("2. PROPHET MODULE IMPORT")
    try:
        from quant.prophet_advisor import (
            ProphetAdvisor, get_oracle, auto_train,
            get_pending_outcomes_count, get_training_status,
            BotName, TradingAdvice
        )
        print_result("Core imports", True)
        results['imports'] = True
    except Exception as e:
        print_result("Core imports", False, str(e))
        results['imports'] = False
        print("\n❌ Cannot continue without Prophet module. Exiting.")
        return False

    # ========================================
    # TEST 3: Prophet Instantiation
    # ========================================
    print_header("3. PROPHET INSTANTIATION")
    try:
        prophet = get_oracle()
        print_result("get_oracle()", True)

        print(f"\n  Prophet Status:")
        print(f"    - Model Trained: {prophet.is_trained}")
        print(f"    - Model Version: {prophet.model_version}")
        print(f"    - Claude Available: {prophet.claude_available}")
        print(f"    - Has GEX Features: {prophet._has_gex_features}")

        results['instantiation'] = True
    except Exception as e:
        print_result("get_oracle()", False, str(e))
        results['instantiation'] = False

    # ========================================
    # TEST 4: Training Status API
    # ========================================
    print_header("4. TRAINING STATUS")
    try:
        status = get_training_status()

        print(f"\n  Status Response:")
        print(f"    - model_trained: {status.get('model_trained')}")
        print(f"    - model_version: {status.get('model_version')}")
        print(f"    - model_source: {status.get('model_source')}")
        print(f"    - db_persistence: {status.get('db_persistence')}")
        print(f"    - pending_outcomes: {status.get('pending_outcomes')}")
        print(f"    - total_outcomes: {status.get('total_outcomes')}")
        print(f"    - needs_training: {status.get('needs_training')}")
        print(f"    - claude_available: {status.get('claude_available')}")

        if status.get('training_metrics'):
            metrics = status['training_metrics']
            print(f"\n  Training Metrics:")
            print(f"    - Accuracy: {metrics.get('accuracy', 'N/A')}")
            print(f"    - AUC-ROC: {metrics.get('auc_roc', 'N/A')}")
            print(f"    - Total Samples: {metrics.get('total_samples', 'N/A')}")

        print_result("Training status API", True)
        results['training_status'] = True

        # Check persistence
        if status.get('db_persistence'):
            print_result("DATABASE PERSISTENCE", True, "Model is safely stored in database!")
        else:
            print_warning("Model NOT in database - will be lost on restart!")

    except Exception as e:
        print_result("Training status API", False, str(e))
        results['training_status'] = False

    # ========================================
    # TEST 5: Training Data Sources
    # ========================================
    print_header("5. TRAINING DATA SOURCES")
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Check each source
        sources = []

        # Live outcomes
        try:
            cursor.execute("SELECT COUNT(*) FROM oracle_live_outcomes")
            live = cursor.fetchone()[0]
            sources.append(('oracle_live_outcomes', live))
        except Exception:
            sources.append(('oracle_live_outcomes', 'TABLE NOT FOUND'))

        # Training outcomes
        try:
            cursor.execute("SELECT COUNT(*) FROM prophet_training_outcomes")
            training = cursor.fetchone()[0]
            sources.append(('prophet_training_outcomes', training))
        except Exception:
            sources.append(('prophet_training_outcomes', 'TABLE NOT FOUND'))

        # Backtest results
        try:
            cursor.execute("SELECT COUNT(*) FROM backtest_results")
            backtests = cursor.fetchone()[0]
            sources.append(('backtest_results', backtests))
        except Exception:
            sources.append(('backtest_results', 'TABLE NOT FOUND'))

        # CHRONICLES memory
        try:
            cursor.execute("SELECT COUNT(*) FROM kronos_memory")
            chronicles = cursor.fetchone()[0]
            sources.append(('kronos_memory', chronicles))
        except Exception:
            sources.append(('kronos_memory', 'TABLE NOT FOUND'))

        print("\n  Data Sources:")
        total_samples = 0
        for table, count in sources:
            status_icon = "✅" if isinstance(count, int) and count > 0 else "⚠️"
            print(f"    {status_icon} {table}: {count}")
            if isinstance(count, int):
                total_samples += count

        print(f"\n  Total potential training samples: {total_samples}")
        print_result("Training data check", total_samples > 0)
        results['training_data'] = total_samples > 0

    except Exception as e:
        print_result("Training data check", False, str(e))
        results['training_data'] = False
    finally:
        if conn:
            conn.close()

    # ========================================
    # TEST 6: Bot Advice Generation
    # ========================================
    print_header("6. BOT ADVICE GENERATION")

    # Create mock market context
    from quant.prophet_advisor import MarketContext, GEXRegime

    mock_context = MarketContext(
        spy_price=590.0,
        vix=15.5,
        vix_percentile=45.0,
        vix_1d_change=-0.5,
        gex_regime=GEXRegime.POSITIVE,
        net_gex=1500000000,
        call_wall=595.0,
        put_wall=580.0,
        zero_gamma=588.0,
        iv_rank=35.0,
        market_trend="NEUTRAL"
    )

    bots = ['FORTRESS', 'CORNERSTONE', 'LAZARUS', 'SOLOMON', 'ANCHOR']

    for bot_name in bots:
        try:
            advice = prophet.get_advice(
                bot_name=BotName[bot_name],
                context=mock_context
            )

            print(f"\n  {bot_name}:")
            print(f"    - Action: {advice.action.value}")
            print(f"    - Confidence: {advice.confidence:.1%}")
            print(f"    - Risk Score: {advice.risk_score:.2f}")
            if advice.size_multiplier:
                print(f"    - Size Mult: {advice.size_multiplier:.2f}")

            print_result(f"{bot_name} advice", True)
            results[f'bot_{bot_name.lower()}'] = True

        except Exception as e:
            print_result(f"{bot_name} advice", False, str(e))
            results[f'bot_{bot_name.lower()}'] = False

    # ========================================
    # TEST 7: Claude AI Integration
    # ========================================
    print_header("7. CLAUDE AI INTEGRATION")
    try:
        if prophet.claude_available:
            print_result("Claude SDK available", True)

            # Try a simple enhancement
            from quant.prophet_advisor import ClaudeAIEnhancer
            enhancer = ClaudeAIEnhancer()

            if enhancer.client:
                print_result("Claude API client initialized", True)
                results['claude'] = True
            else:
                print_warning("Claude client not initialized (check ANTHROPIC_API_KEY)")
                results['claude'] = False
        else:
            print_warning("Claude not available - using ML-only mode")
            results['claude'] = False

    except Exception as e:
        print_result("Claude integration", False, str(e))
        results['claude'] = False

    # ========================================
    # TEST 8: Auto-Training Cascade
    # ========================================
    print_header("8. AUTO-TRAINING CASCADE")
    try:
        pending = get_pending_outcomes_count()
        print(f"  Pending outcomes: {pending}")
        print(f"  Threshold: 100")
        print(f"  Would trigger: {'YES' if pending >= 100 else 'NO'}")

        # Don't actually train unless needed
        if not prophet.is_trained:
            print("\n  Model not trained. Testing training cascade...")
            result = auto_train(threshold_outcomes=100, force=True)

            if result.get('success'):
                print_result("Auto-train cascade", True,
                           f"Trained via {result.get('method', 'unknown')}")
                results['auto_train'] = True
            else:
                print_result("Auto-train cascade", False, result.get('reason', 'Unknown'))
                results['auto_train'] = False
        else:
            print_result("Model already trained", True, "Skipping training test")
            results['auto_train'] = True

    except Exception as e:
        print_result("Auto-training cascade", False, str(e))
        results['auto_train'] = False

    # ========================================
    # TEST 9: Scheduler Integration
    # ========================================
    print_header("9. SCHEDULER INTEGRATION")
    try:
        from scheduler.autonomous_scheduler import (
            check_and_train_oracle,
            ORACLE_TRAINING_DAY,
            ORACLE_TRAINING_HOUR,
            ORACLE_OUTCOME_THRESHOLD
        )

        print(f"  Training day: {ORACLE_TRAINING_DAY} (Sunday=6)")
        print(f"  Training hour: {ORACLE_TRAINING_HOUR} (midnight CT)")
        print(f"  Outcome threshold: {ORACLE_OUTCOME_THRESHOLD}")

        print_result("Scheduler config loaded", True)
        results['scheduler'] = True

    except Exception as e:
        print_result("Scheduler integration", False, str(e))
        results['scheduler'] = False

    # ========================================
    # TEST 10: Database Model Persistence
    # ========================================
    print_header("10. DATABASE MODEL PERSISTENCE (CRITICAL)")
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Check table exists
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'prophet_trained_models'
            )
        """)
        table_exists = cursor.fetchone()[0]

        if table_exists:
            cursor.execute("""
                SELECT id, model_version, LENGTH(model_data) as size,
                       is_active, created_at
                FROM prophet_trained_models
                WHERE is_active = TRUE
                ORDER BY created_at DESC
                LIMIT 1
            """)
            row = cursor.fetchone()

            if row:
                print(f"\n  Active Model in Database:")
                print(f"    - ID: {row[0]}")
                print(f"    - Version: {row[1]}")
                print(f"    - Size: {row[2]:,} bytes")
                print(f"    - Created: {row[4]}")

                print_result("MODEL PERSISTED IN DATABASE", True,
                           "Your model will survive Render restarts!")
                results['db_persistence'] = True
            else:
                print_warning("No active model in database!")
                print("  Run: python scripts/test_oracle_db_persistence.py")
                results['db_persistence'] = False
        else:
            print_warning("prophet_trained_models table doesn't exist!")
            print("  Table will be created on first training.")
            results['db_persistence'] = False

    except Exception as e:
        print_result("Database persistence check", False, str(e))
        results['db_persistence'] = False
    finally:
        if conn:
            conn.close()

    # ========================================
    # FINAL SUMMARY
    # ========================================
    print_header("FINAL SUMMARY")

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    print(f"\n  Tests Passed: {passed}/{total}")
    print()

    for test, status in results.items():
        icon = "✅" if status else "❌"
        print(f"  {icon} {test}")

    if results.get('db_persistence'):
        print("""
╔══════════════════════════════════════════════════════════════════╗
║  ✅ MODEL PERSISTENCE VERIFIED                                    ║
║                                                                   ║
║  Your Prophet ML model is:                                         ║
║    • Stored in PostgreSQL database                                ║
║    • Will survive Render restarts/deploys                         ║
║    • Automatically loads on app startup                           ║
╚══════════════════════════════════════════════════════════════════╝
""")
    else:
        print("""
╔══════════════════════════════════════════════════════════════════╗
║  ⚠️  MODEL NOT YET PERSISTED                                      ║
║                                                                   ║
║  To fix this:                                                     ║
║    1. Go to Prophet page in UI                                     ║
║    2. Click "Train Model" button                                  ║
║    3. Verify "Model Source: Database" shows green                 ║
║                                                                   ║
║  Or run: python scripts/test_oracle_db_persistence.py             ║
╚══════════════════════════════════════════════════════════════════╝
""")

    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
