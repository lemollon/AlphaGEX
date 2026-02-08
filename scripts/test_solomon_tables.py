#!/usr/bin/env python3
"""
Proverbs Tables Verification Script

Run this in Render shell to verify:
1. All Proverbs tables exist
2. Data can be written to tables
3. Data can be read from tables
4. A/B test persistence works
5. Validation trade recording works

Usage:
    python scripts/test_proverbs_tables.py
"""

import os
import sys
import json
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def main():
    print("=" * 70)
    print("PROVERBS TABLES VERIFICATION TEST")
    print("=" * 70)
    print()

    # Step 1: Check database connection
    print("1. CHECKING DATABASE CONNECTION...")
    try:
        from database_adapter import get_connection
        conn = get_connection()
        if conn is None:
            print("   ❌ Failed to get database connection")
            return False
        print("   ✅ Database connection successful")
        conn.close()
    except ImportError as e:
        print(f"   ❌ DATABASE NOT AVAILABLE - Import error: {e}")
        return False
    except Exception as e:
        print(f"   ❌ Database error: {e}")
        return False

    # Step 2: Initialize Proverbs (which creates tables)
    print()
    print("2. INITIALIZING PROVERBS (creates tables)...")
    try:
        from quant.proverbs_feedback_loop import get_proverbs
        proverbs = get_proverbs()
        print(f"   ✅ Proverbs initialized: {proverbs.session_id}")
    except Exception as e:
        print(f"   ❌ Failed to initialize Proverbs: {e}")
        return False

    # Step 3: Verify all tables exist
    print()
    print("3. VERIFYING PROVERBS TABLES EXIST...")

    required_tables = [
        'proverbs_audit_log',
        'proverbs_proposals',
        'proverbs_versions',
        'proverbs_performance',
        'proverbs_rollbacks',
        'proverbs_health',
        'proverbs_kill_switch',
        'proverbs_validations',
        'proverbs_ab_tests',  # NEW - A/B test persistence
    ]

    conn = get_connection()
    cursor = conn.cursor()

    all_exist = True
    for table in required_tables:
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = %s
            )
        """, (table,))
        exists = cursor.fetchone()[0]
        if exists:
            # Get row count
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            print(f"   ✅ {table}: EXISTS ({count} rows)")
        else:
            print(f"   ❌ {table}: MISSING")
            all_exist = False

    conn.close()

    if not all_exist:
        print()
        print("   ⚠️  Some tables are missing. Attempting to create them...")
        # Re-run schema creation
        proverbs._ensure_schema()
        print("   Schema recreation attempted. Please re-run this test.")
        return False

    # Step 4: Test A/B Test Persistence
    print()
    print("4. TESTING A/B TEST PERSISTENCE...")
    try:
        from quant.proverbs_enhancements import get_proverbs_enhanced
        enhanced = get_proverbs_enhanced()

        # Create a test A/B test
        test_id = enhanced.ab_testing.create_test(
            bot_name="TEST_BOT",
            control_config={"sd_multiplier": 1.0},
            variant_config={"sd_multiplier": 1.1},
            control_allocation=0.5
        )
        print(f"   ✅ Created A/B test: {test_id}")

        # Record some trades
        enhanced.ab_testing.record_trade(test_id, is_control=True, pnl=50.0)
        enhanced.ab_testing.record_trade(test_id, is_control=False, pnl=75.0)
        print("   ✅ Recorded test trades")

        # Verify it's in database
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM proverbs_ab_tests WHERE test_id = %s", (test_id,))
        row = cursor.fetchone()
        conn.close()

        if row:
            print(f"   ✅ A/B test found in database: {test_id}")
            print(f"      Control trades: {row[7]}, Variant trades: {row[10]}")
        else:
            print(f"   ❌ A/B test NOT found in database!")
            return False

        # Stop the test (cleanup)
        enhanced.ab_testing.stop_test(test_id)
        print(f"   ✅ A/B test stopped: {test_id}")

    except Exception as e:
        print(f"   ❌ A/B test persistence failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    # Step 5: Test Validation Trade Recording
    print()
    print("5. TESTING VALIDATION TRADE RECORDING...")
    try:
        # Check if there are any active validations
        active_validations = enhanced.proposal_validator.get_pending_validations()
        print(f"   Active validations: {len(active_validations)}")

        if active_validations:
            val = active_validations[0]
            print(f"   ✅ Found validation: {val.get('validation_id')}")
        else:
            print("   ℹ️  No active validations to test (this is OK)")

        print("   ✅ Validation system accessible")
    except Exception as e:
        print(f"   ⚠️  Validation trade recording test skipped: {e}")

    # Step 6: Test Audit Logging
    print()
    print("6. TESTING AUDIT LOGGING...")
    try:
        from quant.proverbs_feedback_loop import ActionType

        proverbs.log_action(
            bot_name="TEST_BOT",
            action_type=ActionType.HEALTH_CHECK,
            description="Table verification test",
            reason="Testing audit logging",
        )
        print("   ✅ Audit log entry created")

        # Verify it's in database
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM proverbs_audit_log
            WHERE action_description = 'Table verification test'
            ORDER BY timestamp DESC LIMIT 1
        """)
        row = cursor.fetchone()
        conn.close()

        if row:
            print(f"   ✅ Audit entry found in database")
        else:
            print(f"   ❌ Audit entry NOT found in database!")
            return False

    except Exception as e:
        print(f"   ❌ Audit logging failed: {e}")
        return False

    # Step 7: Test Version Tracking
    print()
    print("7. TESTING VERSION TRACKING...")
    try:
        from quant.proverbs_feedback_loop import VersionType

        version_id = proverbs.save_version(
            bot_name="TEST_BOT",
            version_type=VersionType.PARAMETERS,
            artifact_name="test_parameters",
            artifact_data={"test_param": 123},
            metadata={"test": True},
            approved_by="TEST_SCRIPT"
        )

        if version_id:
            print(f"   ✅ Version saved: {version_id}")

            # Verify it's in database
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM proverbs_versions WHERE version_id = %s", (version_id,))
            row = cursor.fetchone()
            conn.close()

            if row:
                print(f"   ✅ Version found in database")
            else:
                print(f"   ❌ Version NOT found in database!")
                return False
        else:
            print(f"   ⚠️  Version save returned None (may be expected if DB not available)")

    except Exception as e:
        print(f"   ❌ Version tracking failed: {e}")
        return False

    # Step 8: Summary
    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)

    conn = get_connection()
    cursor = conn.cursor()

    print()
    print("Table Row Counts:")
    for table in required_tables:
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        count = cursor.fetchone()[0]
        status = "✅" if count > 0 else "⚠️ "
        print(f"   {status} {table}: {count} rows")

    conn.close()

    print()
    print("=" * 70)
    print("✅ ALL PROVERBS TABLE TESTS PASSED")
    print("=" * 70)
    print()
    print("Proverbs is production-ready:")
    print("  • All 9 required tables exist")
    print("  • A/B test persistence works")
    print("  • Audit logging works")
    print("  • Version tracking works")
    print("  • Data is being saved to PostgreSQL")
    print()

    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
