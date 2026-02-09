#!/usr/bin/env python3
"""
GIDEON Direction Chain Test
===========================
Tests that ML → Prophet → GIDEON direction chain works correctly.

This script simulates the signal generation flow and verifies
that directions are consistent throughout the chain.
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from datetime import datetime

def test_direction_chain():
    print("=" * 70)
    print("GIDEON DIRECTION CHAIN TEST")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S CT')}")
    print("=" * 70)

    # Test 1: Check GEX Signal Generator
    print("\n1. Testing GEX Signal Generator (STARS)...")
    try:
        from quant.gex_signal_integration import GEXSignalGenerator
        generator = GEXSignalGenerator()
        print("   ✅ GEXSignalGenerator loaded")

        # Test with sample data
        test_signal = generator.get_combined_signal(
            ticker="SPY",
            spot_price=590.0,
            call_wall=595.0,
            put_wall=585.0,
            vix=18.0,
        )

        if test_signal:
            print(f"   ✅ ML Signal: {test_signal.get('direction')} @ {test_signal.get('confidence', 0):.0%}")
        else:
            print("   ⚠️  ML Signal returned None (models may not be trained)")
    except Exception as e:
        print(f"   ❌ Error: {e}")

    # Test 2: Check Prophet imports GEX ML
    print("\n2. Testing Prophet GEX ML Integration...")
    try:
        from quant.prophet_advisor import GEX_ML_AVAILABLE, GEXSignalGenerator as OracleGEX
        print(f"   GEX_ML_AVAILABLE: {GEX_ML_AVAILABLE}")
        if GEX_ML_AVAILABLE:
            print("   ✅ Prophet can use ML direction")
        else:
            print("   ❌ Prophet cannot use ML direction - fix may not work!")
    except Exception as e:
        print(f"   ❌ Error importing Prophet: {e}")

    # Test 3: Check Prophet get_solomon_advice
    print("\n3. Testing Prophet.get_solomon_advice()...")
    try:
        from quant.prophet_advisor import ProphetAdvisor, MarketContext, GEXRegime

        prophet = ProphetAdvisor()

        # Create test context
        context = MarketContext(
            spot_price=590.0,
            vix=18.0,
            vix_percentile_30d=50.0,
            vix_change_1d=0.5,
            gex_net=1000000,
            gex_normalized=0.5,
            gex_regime=GEXRegime.NEUTRAL,
            gex_flip_point=589.0,
            gex_call_wall=595.0,
            gex_put_wall=585.0,
            gex_distance_to_flip_pct=0.17,
            gex_between_walls=True,
            day_of_week=0,  # Monday
            days_to_opex=5,
            expected_move_pct=1.2,
            price_change_1d=0.3,
            win_rate_30d=0.55,
        )

        prediction = prophet.get_solomon_advice(
            context=context,
            use_gex_walls=True,
            use_claude_validation=False,
            wall_filter_pct=6.0,  # GIDEON uses 6%
            bot_name="GIDEON_TEST"
        )

        if prediction:
            # Check if neutral_derived_direction is set (means ML was used)
            direction = getattr(prediction, 'neutral_derived_direction', '') or "FLAT"
            if not direction or direction == "FLAT":
                direction = prediction.reasoning.split("ML DIRECTION:")[1].split()[0] if "ML DIRECTION:" in prediction.reasoning else "UNKNOWN"

            print(f"   Prophet Prediction:")
            print(f"   - Direction: {direction}")
            print(f"   - Confidence: {prediction.confidence:.0%}")
            print(f"   - Win Probability: {prediction.win_probability:.0%}")
            print(f"   - Advice: {prediction.advice}")

            if "ML DIRECTION" in prediction.reasoning:
                print("   ✅ Prophet is using ML direction!")
            else:
                print("   ⚠️  Prophet may not be using ML direction")
                print(f"   Reasoning: {prediction.reasoning[:200]}...")
        else:
            print("   ❌ Prophet returned no prediction")

    except Exception as e:
        import traceback
        print(f"   ❌ Error: {e}")
        traceback.print_exc()

    # Test 4: Check GIDEON signals.py direction logic
    print("\n4. Testing GIDEON SignalGenerator direction logic...")
    try:
        # Just check the code structure
        import inspect
        from trading.gideon.signals import SignalGenerator

        source = inspect.getsource(SignalGenerator.generate_signal)

        if "Prophet is the SOLE AUTHORITY" in source:
            print("   ✅ GIDEON uses Prophet as sole authority")
        else:
            print("   ⚠️  GIDEON direction logic may not be updated")

        if "effective_direction = oracle_direction" in source:
            print("   ✅ GIDEON uses oracle_direction when available")
        else:
            print("   ⚠️  Check GIDEON direction assignment")

    except Exception as e:
        print(f"   ❌ Error: {e}")

    # Summary
    print("\n" + "=" * 70)
    print("CHAIN TEST SUMMARY")
    print("=" * 70)
    print("""
  Expected Flow:
  1. ML (STARS) → get_combined_signal() → BULLISH/BEARISH
  2. Prophet → get_solomon_advice() → Uses ML direction
  3. GIDEON → generate_signal() → Follows Prophet direction
  4. Trade → BULL_CALL (if BULLISH) or BEAR_PUT (if BEARISH)

  If all tests pass (✅), the direction chain is working correctly.
  Any ❌ or ⚠️ indicates a potential issue.
    """)

if __name__ == "__main__":
    test_direction_chain()
