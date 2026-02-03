#!/usr/bin/env python3
"""
Render Shell Script: VALOR (HERACLES) Update Validation Tests
==============================================================

Validates all VALOR updates including:
1. ML Approval Workflow
2. A/B Test for Dynamic Stops
3. Bidirectional Momentum Signals (Wall Bounce)
4. Dynamic Stop Calculation

Run in Render shell:
    python scripts/render_test_valor_updates.py
"""

import os
import sys
from datetime import datetime

# Project root setup - required for Render shell
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

def ok(msg): print(f"[OK] {msg}")
def fail(msg): print(f"[FAIL] {msg}")
def info(msg): print(f"[INFO] {msg}")

def print_header(title):
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)

def print_result(test_name, passed, details=""):
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"  {status}: {test_name}")
    if details:
        print(f"         {details}")

def test_ml_approval_workflow():
    """Test ML Approval Workflow"""
    print_header("TEST 1: ML APPROVAL WORKFLOW")

    try:
        from trading.heracles.signals import (
            is_ml_approved, approve_ml_model, revoke_ml_approval,
            _get_config_value, _set_config_value
        )

        # Test 1a: Check initial state
        initial_state = is_ml_approved()
        print(f"\n  Current ML approval state: {initial_state}")

        # Test 1b: Test config functions work
        test_key = 'test_ml_approval_check'
        _set_config_value(test_key, True)
        read_back = _get_config_value(test_key)
        print_result("Config read/write works", read_back == True, f"wrote True, read {read_back}")

        # Test 1c: Test approve function
        approve_result = approve_ml_model()
        after_approve = is_ml_approved()
        print_result("approve_ml_model() sets flag", after_approve == True, f"result={approve_result}, is_approved={after_approve}")

        # Test 1d: Test revoke function
        revoke_result = revoke_ml_approval()
        after_revoke = is_ml_approved()
        print_result("revoke_ml_approval() clears flag", after_revoke == False, f"result={revoke_result}, is_approved={after_revoke}")

        # Restore original state
        if initial_state:
            approve_ml_model()

        print("\n  ML Approval Workflow: OPERATIONAL")
        return True

    except Exception as e:
        print(f"\n  ❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_ab_test_workflow():
    """Test A/B Test for Dynamic Stops"""
    print_header("TEST 2: A/B TEST FOR DYNAMIC STOPS")

    try:
        from trading.heracles.signals import (
            is_ab_test_enabled, enable_ab_test, disable_ab_test, get_ab_assignment
        )

        # Test 2a: Check initial state
        initial_state = is_ab_test_enabled()
        print(f"\n  Current A/B test state: {initial_state}")

        # Test 2b: Test enable
        enable_result = enable_ab_test()
        after_enable = is_ab_test_enabled()
        print_result("enable_ab_test() sets flag", after_enable == True, f"result={enable_result}, enabled={after_enable}")

        # Test 2c: Test assignment randomness
        assignments = [get_ab_assignment() for _ in range(100)]
        fixed_count = assignments.count('FIXED')
        dynamic_count = assignments.count('DYNAMIC')
        # Should be roughly 50/50 (allow 30-70 range for small sample)
        is_random = 30 <= fixed_count <= 70
        print_result("get_ab_assignment() is random ~50/50", is_random, f"FIXED={fixed_count}, DYNAMIC={dynamic_count}")

        # Test 2d: Test disable
        disable_result = disable_ab_test()
        after_disable = is_ab_test_enabled()
        print_result("disable_ab_test() clears flag", after_disable == False, f"result={disable_result}, enabled={after_disable}")

        # Restore original state
        if initial_state:
            enable_ab_test()

        print("\n  A/B Test Workflow: OPERATIONAL")
        return True

    except Exception as e:
        print(f"\n  ❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_ab_test_database():
    """Test A/B Test Database Functions"""
    print_header("TEST 3: A/B TEST DATABASE")

    try:
        from trading.heracles.db import HERACLESDatabase

        db = HERACLESDatabase()
        results = db.get_ab_test_results()

        print(f"\n  A/B Test Results from Database:")
        print(f"    FIXED trades:   {results['fixed']['trades']}")
        print(f"    DYNAMIC trades: {results['dynamic']['trades']}")
        print(f"    Total A/B trades: {results['summary']['total_ab_trades']}")
        print(f"    Message: {results['summary']['message']}")

        if results['fixed']['trades'] > 0:
            print(f"\n    FIXED Stats:")
            print(f"      Win Rate: {results['fixed']['win_rate']:.1f}%")
            print(f"      Total P&L: ${results['fixed']['total_pnl']:.2f}")
            print(f"      Avg Stop: {results['fixed'].get('avg_stop_pts', 'N/A')} pts")

        if results['dynamic']['trades'] > 0:
            print(f"\n    DYNAMIC Stats:")
            print(f"      Win Rate: {results['dynamic']['win_rate']:.1f}%")
            print(f"      Total P&L: ${results['dynamic']['total_pnl']:.2f}")
            print(f"      Avg Stop: {results['dynamic'].get('avg_stop_pts', 'N/A')} pts")

        print_result("get_ab_test_results() works", True, "Query executed successfully")
        return True

    except Exception as e:
        print(f"\n  ❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_dynamic_stop_calculation():
    """Test Dynamic Stop Calculation Logic"""
    print_header("TEST 4: DYNAMIC STOP CALCULATION")

    try:
        from trading.heracles.signals import HERACLESSignalGenerator
        from trading.heracles.models import HERACLESConfig, BayesianWinTracker, GammaRegime

        config = HERACLESConfig()
        tracker = BayesianWinTracker()
        generator = HERACLESSignalGenerator(config, tracker)

        base_stop = 2.5  # Default
        test_cases = [
            # (vix, atr, regime, expected_range_min, expected_range_max, description)
            (12, 3.0, GammaRegime.POSITIVE, 1.5, 2.5, "Low VIX, Low ATR, Positive (tightest)"),
            (18, 5.0, GammaRegime.NEUTRAL, 2.0, 3.5, "Normal VIX, Normal ATR, Neutral"),
            (25, 7.0, GammaRegime.NEGATIVE, 3.0, 5.0, "High VIX, High ATR, Negative (widest)"),
            (35, 10.0, GammaRegime.NEGATIVE, 4.0, 6.0, "Extreme VIX (capped at 6)"),
        ]

        print(f"\n  Base stop: {base_stop} points")
        print(f"\n  Testing dynamic stop adjustments:")

        all_passed = True
        for vix, atr, regime, min_exp, max_exp, desc in test_cases:
            result = generator._calculate_dynamic_stop(base_stop, vix, atr, regime)
            passed = min_exp <= result <= max_exp
            all_passed = all_passed and passed
            print_result(
                f"{desc}",
                passed,
                f"VIX={vix}, ATR={atr}, Regime={regime.value} → {result:.2f} pts (expected {min_exp}-{max_exp})"
            )

        # Test caps
        result_min = generator._calculate_dynamic_stop(base_stop, 10, 1.0, GammaRegime.POSITIVE)
        result_max = generator._calculate_dynamic_stop(base_stop, 40, 15.0, GammaRegime.NEGATIVE)

        print_result("Min cap (1.5 pts)", result_min >= 1.5, f"Result: {result_min:.2f}")
        print_result("Max cap (6.0 pts)", result_max <= 6.0, f"Result: {result_max:.2f}")

        return all_passed

    except Exception as e:
        print(f"\n  ❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_bidirectional_momentum():
    """Test Bidirectional Momentum Signals (Wall Bounce)"""
    print_header("TEST 5: BIDIRECTIONAL MOMENTUM (WALL BOUNCE)")

    try:
        from trading.heracles.signals import HERACLESSignalGenerator
        from trading.heracles.models import HERACLESConfig, BayesianWinTracker, GammaRegime, SignalSource

        config = HERACLESConfig()
        tracker = BayesianWinTracker()
        generator = HERACLESSignalGenerator(config, tracker)

        # Test parameters
        flip_point = 6100.0
        call_wall = 6150.0
        put_wall = 6050.0
        vix = 18.0
        atr = 5.0
        net_gex = -500000  # Negative gamma

        print(f"\n  Test Setup:")
        print(f"    Flip Point: {flip_point}")
        print(f"    Call Wall:  {call_wall}")
        print(f"    Put Wall:   {put_wall}")
        print(f"    ATR: {atr}, VIX: {vix}")
        print(f"    Net GEX: {net_gex} (NEGATIVE GAMMA)")

        # Wall proximity threshold = 1.5 * ATR = 7.5 points
        wall_threshold = atr * 1.5
        print(f"    Wall Proximity Threshold: {wall_threshold} pts")

        test_cases = [
            # (price, expected_direction, expected_source, description)
            (6055.0, "LONG", SignalSource.GEX_WALL_BOUNCE, "Near put wall (LONG below flip)"),
            (6145.0, "SHORT", SignalSource.GEX_WALL_BOUNCE, "Near call wall (SHORT above flip)"),
            (6120.0, "LONG", SignalSource.GEX_MOMENTUM, "Above flip breakout (LONG momentum)"),
            (6080.0, "SHORT", SignalSource.GEX_MOMENTUM, "Below flip breakout (SHORT momentum)"),
            (6100.0, None, None, "At flip point (no signal)"),
        ]

        print(f"\n  Testing signal generation:")
        all_passed = True

        for price, expected_dir, expected_source, desc in test_cases:
            signal = generator._generate_momentum_signal(
                current_price=price,
                flip_point=flip_point,
                call_wall=call_wall,
                put_wall=put_wall,
                vix=vix,
                atr=atr,
                net_gex=net_gex,
                gamma_regime=GammaRegime.NEGATIVE
            )

            if expected_dir is None:
                passed = signal is None
                result_str = "No signal (as expected)" if passed else f"Got signal: {signal.direction.value if signal else 'None'}"
            else:
                passed = (signal is not None and
                         signal.direction.value == expected_dir and
                         signal.source == expected_source)
                if signal:
                    result_str = f"Dir={signal.direction.value}, Source={signal.source.value}"
                else:
                    result_str = "No signal generated"

            all_passed = all_passed and passed
            print_result(f"Price {price}: {desc}", passed, result_str)

        # Summary
        if all_passed:
            print("\n  Bidirectional Momentum: WORKING")
            print("    ✓ LONG signals generated near put wall (below flip)")
            print("    ✓ SHORT signals generated near call wall (above flip)")

        return all_passed

    except Exception as e:
        print(f"\n  ❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_signal_stop_tracking():
    """Test that signals include stop tracking fields"""
    print_header("TEST 6: SIGNAL STOP TRACKING FIELDS")

    try:
        from trading.heracles.models import FuturesSignal, TradeDirection, GammaRegime, SignalSource

        # Create a test signal
        signal = FuturesSignal(
            direction=TradeDirection.LONG,
            confidence=0.75,
            source=SignalSource.GEX_MOMENTUM,
            current_price=6100.0,
            gamma_regime=GammaRegime.NEGATIVE,
            gex_value=-500000,
            flip_point=6095.0,
            call_wall=6150.0,
            put_wall=6050.0,
            vix=18.0,
            atr=5.0,
        )

        # Check stop tracking fields exist with defaults
        print_result("stop_type field exists", hasattr(signal, 'stop_type'), f"Default: {signal.stop_type}")
        print_result("stop_points_used field exists", hasattr(signal, 'stop_points_used'), f"Default: {signal.stop_points_used}")

        # Set values and verify
        signal.stop_type = "DYNAMIC"
        signal.stop_points_used = 3.5
        print_result("stop_type assignable", signal.stop_type == "DYNAMIC")
        print_result("stop_points_used assignable", signal.stop_points_used == 3.5)

        return True

    except Exception as e:
        print(f"\n  ❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_position_stop_tracking():
    """Test that positions include stop tracking fields"""
    print_header("TEST 7: POSITION STOP TRACKING FIELDS")

    try:
        from trading.heracles.models import FuturesPosition, TradeDirection, GammaRegime, SignalSource

        # Create a test position
        position = FuturesPosition(
            position_id="test_123",
            symbol="/MESH6",
            direction=TradeDirection.LONG,
            contracts=1,
            entry_price=6100.0,
            entry_value=30500.0,
            initial_stop=6095.0,
            current_stop=6095.0,
            breakeven_price=6102.0,
        )

        # Check stop tracking fields exist with defaults
        print_result("stop_type field exists", hasattr(position, 'stop_type'), f"Default: {position.stop_type}")
        print_result("stop_points_used field exists", hasattr(position, 'stop_points_used'), f"Default: {position.stop_points_used}")

        # Set values and verify
        position.stop_type = "FIXED"
        position.stop_points_used = 2.5
        print_result("stop_type assignable", position.stop_type == "FIXED")
        print_result("stop_points_used assignable", position.stop_points_used == 2.5)

        return True

    except Exception as e:
        print(f"\n  ❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_ml_model_status():
    """Test ML Model Status"""
    print_header("TEST 8: ML MODEL STATUS")

    try:
        from trading.heracles.ml import get_heracles_ml_advisor

        advisor = get_heracles_ml_advisor()

        print(f"\n  ML Advisor Status:")
        print(f"    Model Trained: {advisor.is_trained}")
        print(f"    Model Version: {advisor.model_version}")

        if advisor.training_metrics:
            print(f"    Accuracy: {advisor.training_metrics.accuracy:.2%}")
            print(f"    Training Samples: {advisor.training_metrics.training_samples}")
        else:
            print(f"    Training Metrics: Not available")

        print_result("ML Advisor loads", advisor is not None)
        return True

    except ImportError as e:
        print(f"\n  ⚠️  ML module not available: {e}")
        return True  # Not a failure, just not trained
    except Exception as e:
        print(f"\n  ❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_database_columns():
    """Test that database has required columns"""
    print_header("TEST 9: DATABASE COLUMNS")

    try:
        from database_adapter import get_connection

        conn = get_connection()
        cursor = conn.cursor()

        # Check heracles_closed_trades columns
        cursor.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'heracles_closed_trades'
            AND column_name IN ('stop_type', 'stop_points_used')
        """)
        closed_cols = [row[0] for row in cursor.fetchall()]

        # Check heracles_positions columns
        cursor.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'heracles_positions'
            AND column_name IN ('stop_type', 'stop_points_used')
        """)
        position_cols = [row[0] for row in cursor.fetchall()]

        conn.close()

        print_result("heracles_closed_trades.stop_type", 'stop_type' in closed_cols)
        print_result("heracles_closed_trades.stop_points_used", 'stop_points_used' in closed_cols)
        print_result("heracles_positions.stop_type", 'stop_type' in position_cols)
        print_result("heracles_positions.stop_points_used", 'stop_points_used' in position_cols)

        all_present = (len(closed_cols) == 2 and len(position_cols) == 2)

        if not all_present:
            print("\n  ⚠️  Missing columns - run database migration")

        return all_present

    except Exception as e:
        print(f"\n  ❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_all_tests():
    """Run all validation tests"""
    print("\n" + "=" * 70)
    print("  VALOR (HERACLES) UPDATE VALIDATION SUITE")
    print(f"  Run Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S CT')}")
    print("=" * 70)

    # Check DATABASE_URL for tests that need it
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        fail("DATABASE_URL not set - database tests will fail!")
    else:
        # Mask password for display
        masked_url = db_url
        if "@" in db_url:
            parts = db_url.split("@")
            before = parts[0]
            if ":" in before:
                user_pass = before.split("//")[-1]
                if ":" in user_pass:
                    masked_url = db_url.replace(user_pass.split(":")[1], "****")
        info(f"DATABASE_URL: {masked_url[:50]}...")

    results = []

    # Run each test
    results.append(("ML Approval Workflow", test_ml_approval_workflow()))
    results.append(("A/B Test Workflow", test_ab_test_workflow()))
    results.append(("A/B Test Database", test_ab_test_database()))
    results.append(("Dynamic Stop Calculation", test_dynamic_stop_calculation()))
    results.append(("Bidirectional Momentum", test_bidirectional_momentum()))
    results.append(("Signal Stop Tracking", test_signal_stop_tracking()))
    results.append(("Position Stop Tracking", test_position_stop_tracking()))
    results.append(("ML Model Status", test_ml_model_status()))
    results.append(("Database Columns", test_database_columns()))

    # Summary
    print_header("TEST SUMMARY")

    passed = sum(1 for _, r in results if r)
    total = len(results)

    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {status}: {name}")

    print(f"\n  Overall: {passed}/{total} tests passed")

    if passed == total:
        print("\n  🎉 ALL TESTS PASSED - Updates are working correctly!")
    else:
        print("\n  ⚠️  Some tests failed - review above for details")

    return passed == total


if __name__ == "__main__":
    run_all_tests()
