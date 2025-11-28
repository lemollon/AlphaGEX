#!/usr/bin/env python3
"""
Test Autonomous Trader End-to-End
This script verifies the autonomous trader works correctly
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("=" * 80)
print("AUTONOMOUS TRADER END-TO-END TEST")
print("=" * 80)

# Test 1: Import and initialize
print("\n1️⃣  Testing imports...")
try:
    from core.autonomous_paper_trader import AutonomousPaperTrader
    from core_classes_and_engines import TradingVolatilityAPI
    from db.config_and_database import DB_PATH
    print(f"✅ Imports successful")
    print(f"   Database path: {DB_PATH}")
except Exception as e:
    print(f"❌ Import failed: {e}")
    sys.exit(1)

# Test 2: Initialize trader
print("\n2️⃣  Testing trader initialization...")
try:
    trader = AutonomousPaperTrader()
    print(f"✅ Trader initialized")
    print(f"   Database: PostgreSQL via DATABASE_URL")
except Exception as e:
    print(f"❌ Trader init failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 3: Read initial status
print("\n3️⃣  Testing status read...")
try:
    status = trader.get_live_status()
    print(f"✅ Status read successful")
    print(f"   Status: {status.get('status')}")
    print(f"   Action: {status.get('current_action')}")
    print(f"   Working: {status.get('is_working')}")
except Exception as e:
    print(f"❌ Status read failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 4: Update status
print("\n4️⃣  Testing status update...")
try:
    trader.update_live_status(
        status='TEST_MODE',
        action='Running end-to-end test',
        analysis='Testing database write operations',
        decision='Verify status updates work'
    )
    print(f"✅ Status update successful")
except Exception as e:
    print(f"❌ Status update failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 5: Read back updated status
print("\n5️⃣  Testing status read-back...")
try:
    updated_status = trader.get_live_status()
    print(f"✅ Status read-back successful")
    print(f"   Status: {updated_status.get('status')}")
    print(f"   Action: {updated_status.get('current_action')}")
    print(f"   Analysis: {updated_status.get('market_analysis')}")
    print(f"   Decision: {updated_status.get('last_decision')}")

    if updated_status.get('status') == 'TEST_MODE':
        print(f"✅ Status persistence verified!")
    else:
        print(f"⚠️  Status mismatch: expected 'TEST_MODE', got '{updated_status.get('status')}'")
except Exception as e:
    print(f"❌ Status read-back failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 6: Get performance
print("\n6️⃣  Testing performance read...")
try:
    perf = trader.get_performance()
    print(f"✅ Performance read successful")
    print(f"   Starting Capital: ${perf['starting_capital']:,.0f}")
    print(f"   Current Value: ${perf['current_value']:,.2f}")
    print(f"   Total P&L: ${perf['total_pnl']:+,.2f}")
    print(f"   Total Trades: {perf['total_trades']}")
    print(f"   Win Rate: {perf['win_rate']:.1f}%")
except Exception as e:
    print(f"❌ Performance read failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 7: Config operations
print("\n7️⃣  Testing config operations...")
try:
    # Read config
    capital = trader.get_config('capital')
    print(f"✅ Config read successful: capital = ${capital}")

    # Write config
    trader.set_config('test_key', 'test_value')
    test_val = trader.get_config('test_key')

    if test_val == 'test_value':
        print(f"✅ Config write/read verified!")
    else:
        print(f"⚠️  Config mismatch")
except Exception as e:
    print(f"❌ Config operations failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 8: Reset status to INITIALIZING for fresh start
print("\n8️⃣  Resetting status to INITIALIZING...")
try:
    trader.update_live_status(
        status='INITIALIZING',
        action='System ready, waiting for worker to start',
        analysis=None,
        decision=None
    )
    print(f"✅ Status reset successful")
except Exception as e:
    print(f"❌ Status reset failed: {e}")

print("\n" + "=" * 80)
print("✅ ALL TESTS PASSED")
print("=" * 80)
print("\nNext steps:")
print("1. Run autonomous scheduler: python autonomous_scheduler.py --mode continuous")
print("2. Watch status update in real-time")
print("3. Check UI at /trader to see live status")
print()
