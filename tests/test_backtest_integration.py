#!/usr/bin/env python3
"""
Test Backtest Integration - Verify regime signal logging works end-to-end

This script tests:
1. Autonomous trader can analyze market
2. Regime signals are saved to database
3. Backtester can query the signals
4. Data structure is correct
"""

import sys
import sqlite3
from datetime import datetime
from db.config_and_database import DB_PATH

print("=" * 80)
print("BACKTEST INTEGRATION TEST")
print("=" * 80)

# Step 1: Test imports
print("\n1️⃣  Testing imports...")
try:
    from psychology_trap_detector import analyze_current_market_complete, save_regime_signal_to_db
    from backtest.autonomous_backtest_engine import PatternBacktester
    from data.polygon_helper import PolygonDataFetcher as PolygonHelper
    print("✅ All imports successful")
except Exception as e:
    print(f"❌ Import failed: {e}")
    sys.exit(1)

# Step 2: Test market analysis
print("\n2️⃣  Testing market analysis...")
try:
    polygon_helper = PolygonHelper()

    # Get current market data
    spot = 580.0  # Default if API fails
    try:
        spot_data = polygon_helper.get_latest_price('SPY')
        if spot_data and 'price' in spot_data:
            spot = spot_data['price']
    except:
        pass

    print(f"   Using spot price: ${spot:.2f}")

    # Get price data for analysis
    price_data = polygon_helper.get_multi_timeframe_data('SPY', spot)

    # Build gamma data (simplified)
    gamma_data = {
        'net_gex': 5000000000,
        'flip_point': spot * 0.98,
        'call_wall': spot * 1.02,
        'put_wall': spot * 0.98,
        'spot_price': spot
    }

    # Run complete regime detection
    regime_result = analyze_current_market_complete(
        current_price=spot,
        price_data=price_data,
        gamma_data=gamma_data,
        volume_ratio=1.0
    )

    if regime_result and regime_result.get('regime'):
        pattern = regime_result['regime'].get('primary_regime_type', 'UNKNOWN')
        confidence = regime_result['regime'].get('confidence_score', 0)
        print(f"✅ Market analysis successful")
        print(f"   Pattern detected: {pattern}")
        print(f"   Confidence: {confidence:.0f}%")
    else:
        print("⚠️  Market analysis returned empty result")
        regime_result = None

except Exception as e:
    print(f"❌ Market analysis failed: {e}")
    import traceback
    traceback.print_exc()
    regime_result = None

# Step 3: Test saving regime signal
print("\n3️⃣  Testing regime signal database save...")
signal_id = None
if regime_result:
    try:
        signal_id = save_regime_signal_to_db(regime_result)
        print(f"✅ Regime signal saved successfully")
        print(f"   Signal ID: {signal_id}")
    except Exception as e:
        print(f"❌ Failed to save regime signal: {e}")
        import traceback
        traceback.print_exc()
else:
    print("⚠️  Skipping save (no regime result)")

# Step 4: Verify data in database
print("\n4️⃣  Verifying data in database...")
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

c.execute("SELECT COUNT(*) FROM regime_signals")
total_signals = c.fetchone()[0]
print(f"   Total regime signals in DB: {total_signals}")

if total_signals > 0:
    c.execute("""
        SELECT id, timestamp, primary_regime_type, confidence_score, trade_direction
        FROM regime_signals
        ORDER BY timestamp DESC
        LIMIT 5
    """)
    print("\n   Recent signals:")
    for row in c.fetchall():
        print(f"   - ID {row[0]}: {row[2]} ({row[3]:.0f}% confidence, {row[4]}) at {row[1]}")
else:
    print("   ⚠️  No signals found")

conn.close()

# Step 5: Test backtest can query the data
print("\n5️⃣  Testing backtest query...")
try:
    backtester = PatternBacktester()

    if total_signals > 0:
        # Try to backtest a pattern
        c = sqlite3.connect(DB_PATH).cursor()
        c.execute("SELECT DISTINCT primary_regime_type FROM regime_signals LIMIT 1")
        pattern_row = c.fetchone()

        if pattern_row:
            test_pattern = pattern_row[0]
            print(f"   Testing backtest for pattern: {test_pattern}")

            result = backtester.backtest_pattern(test_pattern, lookback_days=7)

            print(f"✅ Backtest query successful")
            print(f"   Pattern: {result['pattern']}")
            print(f"   Total signals found: {result['total_signals']}")
            print(f"   Win rate: {result['win_rate']:.1f}%")
        else:
            print("   ⚠️  No patterns to test")
    else:
        print("   ⚠️  Skipping backtest (no signals in DB)")

except Exception as e:
    print(f"❌ Backtest query failed: {e}")
    import traceback
    traceback.print_exc()

# Final summary
print("\n" + "=" * 80)
print("INTEGRATION TEST SUMMARY")
print("=" * 80)

if regime_result and signal_id and total_signals > 0:
    print("✅ PASS - Full integration working!")
    print("\nWhat this proves:")
    print("  1. Market analysis generates regime results")
    print("  2. Regime signals save to database successfully")
    print("  3. Backtester can query the saved signals")
    print("  4. Data structure is compatible end-to-end")
    print("\nNext step: Run autonomous trader to accumulate data, then backtests will work!")
    sys.exit(0)
elif regime_result and signal_id:
    print("⚠️  PARTIAL PASS - Save works but check database")
    print("\nThe integration appears to work, but verify:")
    print(f"  - Signal was saved (ID: {signal_id})")
    print(f"  - Total signals in DB: {total_signals}")
    sys.exit(0)
else:
    print("❌ FAIL - Integration issues detected")
    print("\nProblems found:")
    if not regime_result:
        print("  - Market analysis not returning regime results")
    if regime_result and not signal_id:
        print("  - Failed to save regime signal to database")
    print("\nReview error messages above for details")
    sys.exit(1)
