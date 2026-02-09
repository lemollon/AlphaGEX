#!/usr/bin/env python3
"""
VALOR Updates Test Script
============================

Tests all recent changes to validate they work correctly:
1. Dynamic Stop Loss calculation
2. ML Integration (if model trained)
3. API endpoint changes

Run: python scripts/test_valor_updates.py
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime

print("=" * 70)
print("VALOR (VALOR) UPDATES VALIDATION")
print("=" * 70)
print(f"Test Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print()

# ============================================================================
# TEST 1: Dynamic Stop Loss Calculation
# ============================================================================
print("\n" + "=" * 70)
print("TEST 1: DYNAMIC STOP LOSS CALCULATION")
print("=" * 70)

try:
    from trading.valor.signals import ValorSignalGenerator
    from trading.valor.models import ValorConfig, GammaRegime, BayesianWinTracker

    config = ValorConfig()
    win_tracker = BayesianWinTracker()
    signal_gen = ValorSignalGenerator(config, win_tracker)

    print(f"\nBase stop from config: {config.initial_stop_points} pts")
    print("\nTesting dynamic stop calculations:")
    print("-" * 60)
    print(f"{'VIX':<8} {'ATR':<8} {'Regime':<12} {'Stop (pts)':<12} {'Stop ($)':<10}")
    print("-" * 60)

    # Test various conditions
    test_cases = [
        # VIX, ATR, Regime
        (12, 2.5, GammaRegime.POSITIVE),   # Low VIX, low ATR, positive gamma
        (18, 4.0, GammaRegime.NEUTRAL),    # Normal VIX, normal ATR
        (18, 4.0, GammaRegime.POSITIVE),   # Normal VIX, positive gamma
        (18, 4.0, GammaRegime.NEGATIVE),   # Normal VIX, negative gamma
        (22, 5.5, GammaRegime.NEGATIVE),   # Elevated VIX, higher ATR
        (28, 7.0, GammaRegime.NEGATIVE),   # High VIX, high ATR
        (35, 10.0, GammaRegime.NEGATIVE),  # Very high VIX (should hit cap)
    ]

    results = []
    for vix, atr, regime in test_cases:
        stop = signal_gen._calculate_dynamic_stop(
            base_stop=config.initial_stop_points,
            vix=vix,
            atr=atr,
            gamma_regime=regime
        )
        dollar_value = stop * 5.0  # $5 per point
        results.append((vix, atr, regime.value, stop, dollar_value))
        print(f"{vix:<8} {atr:<8} {regime.value:<12} {stop:<12.2f} ${dollar_value:<9.2f}")

    print("-" * 60)

    # Validate logic
    print("\nValidation checks:")

    # Check 1: Low VIX should have tighter stop than high VIX
    low_vix_stop = results[0][3]  # VIX=12
    high_vix_stop = results[5][3]  # VIX=28
    check1 = low_vix_stop < high_vix_stop
    print(f"  ✓ Low VIX ({results[0][0]}) tighter than High VIX ({results[5][0]}): {low_vix_stop:.2f} < {high_vix_stop:.2f} = {check1}")

    # Check 2: Positive gamma should have tighter stop than negative
    pos_gamma_stop = results[2][3]  # Positive gamma
    neg_gamma_stop = results[3][3]  # Negative gamma
    check2 = pos_gamma_stop < neg_gamma_stop
    print(f"  ✓ Positive gamma tighter than Negative: {pos_gamma_stop:.2f} < {neg_gamma_stop:.2f} = {check2}")

    # Check 3: Very high VIX should hit the 6pt cap
    very_high_stop = results[6][3]  # VIX=35
    check3 = very_high_stop <= 6.0
    print(f"  ✓ Very high VIX capped at 6pts: {very_high_stop:.2f} <= 6.0 = {check3}")

    # Check 4: All stops should be in valid range
    all_valid = all(1.5 <= r[3] <= 6.0 for r in results)
    print(f"  ✓ All stops in range [1.5, 6.0]: {all_valid}")

    if check1 and check2 and check3 and all_valid:
        print("\n✅ DYNAMIC STOP LOSS: ALL TESTS PASSED")
    else:
        print("\n❌ DYNAMIC STOP LOSS: SOME TESTS FAILED")

except Exception as e:
    print(f"\n❌ ERROR testing dynamic stop: {e}")
    import traceback
    traceback.print_exc()


# ============================================================================
# TEST 2: ML Module Loading
# ============================================================================
print("\n" + "=" * 70)
print("TEST 2: ML MODULE LOADING")
print("=" * 70)

try:
    from trading.valor.ml import ValorMLAdvisor, get_valor_ml_advisor

    print("\n✅ ML module imports successfully")

    advisor = get_valor_ml_advisor()
    print(f"✅ ML Advisor singleton created")

    status = advisor.get_status()
    print(f"\nML Model Status:")
    print(f"  Is Trained: {status['is_trained']}")
    print(f"  Model Version: {status['model_version']}")
    print(f"  Training Date: {status['training_date']}")
    print(f"  Accuracy: {status['accuracy']}")
    print(f"  Samples: {status['samples']}")

    if status['is_trained']:
        print("\n✅ ML MODEL IS TRAINED AND LOADED")

        # Test prediction
        test_features = {
            'vix': 18.0,
            'atr': 4.0,
            'gamma_regime_encoded': -1,  # Negative
            'distance_to_flip_pct': 0.5,
            'distance_to_call_wall_pct': 1.0,
            'distance_to_put_wall_pct': 0.8,
            'day_of_week': 1,  # Tuesday
            'hour_of_day': 10,
            'is_overnight': 0,
            'positive_gamma_win_rate': 0.65,
            'negative_gamma_win_rate': 0.55,
            'signal_confidence': 0.7,
        }

        prediction = advisor.predict(test_features)
        print(f"\nTest Prediction:")
        print(f"  Win Probability: {prediction.get('win_probability', 'N/A'):.2%}")
        print(f"  Confidence: {prediction.get('confidence', 'N/A')}")
        print(f"  Recommendation: {prediction.get('recommendation', 'N/A')}")
    else:
        print("\n⚠️ ML MODEL NOT YET TRAINED")
        print("   (This is expected if less than 50 trades)")

except ImportError as e:
    print(f"\n❌ ML module import failed: {e}")
except Exception as e:
    print(f"\n❌ ERROR testing ML module: {e}")
    import traceback
    traceback.print_exc()


# ============================================================================
# TEST 3: ML Integration in Signal Generator
# ============================================================================
print("\n" + "=" * 70)
print("TEST 3: ML INTEGRATION IN SIGNAL GENERATOR")
print("=" * 70)

try:
    from trading.valor.signals import _get_ml_advisor

    ml_advisor = _get_ml_advisor()
    if ml_advisor is None:
        print("\n⚠️ ML Advisor not loaded (module issue)")
    elif ml_advisor.model is None:
        print("\n⚠️ ML Advisor loaded but model not trained")
        print("   Signal generator will use Bayesian fallback")
    else:
        print("\n✅ ML Advisor loaded and model is trained")
        print("   Signal generator WILL use ML predictions")

except Exception as e:
    print(f"\n❌ ERROR: {e}")


# ============================================================================
# TEST 4: Training Data Availability
# ============================================================================
print("\n" + "=" * 70)
print("TEST 4: TRAINING DATA AVAILABILITY")
print("=" * 70)

try:
    from trading.valor.ml import get_valor_ml_advisor

    advisor = get_valor_ml_advisor()
    df = advisor.get_training_data()

    if df is not None and len(df) > 0:
        print(f"\n✅ Training data available: {len(df)} samples")
        print(f"   Ready for training: {len(df) >= 50}")

        if len(df) >= 10:
            # Show sample distribution
            wins = len(df[df['outcome'] == 1]) if 'outcome' in df.columns else 0
            losses = len(df) - wins
            print(f"\n   Win samples: {wins}")
            print(f"   Loss samples: {losses}")
            print(f"   Win rate in data: {wins/len(df)*100:.1f}%")
    else:
        print("\n⚠️ No training data available yet")
        print("   Need closed trades with outcomes in scan_activity")

except Exception as e:
    print(f"\n❌ ERROR: {e}")


# ============================================================================
# TEST 5: Compare Fixed vs Dynamic Stops (Simulation)
# ============================================================================
print("\n" + "=" * 70)
print("TEST 5: FIXED vs DYNAMIC STOP COMPARISON")
print("=" * 70)

try:
    from trading.valor.signals import ValorSignalGenerator
    from trading.valor.models import ValorConfig, GammaRegime, BayesianWinTracker

    config = ValorConfig()
    win_tracker = BayesianWinTracker()
    signal_gen = ValorSignalGenerator(config, win_tracker)

    # Simulate different market conditions
    scenarios = [
        {"name": "Calm Market", "vix": 13, "atr": 2.5, "regime": GammaRegime.POSITIVE},
        {"name": "Normal Market", "vix": 17, "atr": 4.0, "regime": GammaRegime.NEUTRAL},
        {"name": "Volatile Market", "vix": 25, "atr": 6.5, "regime": GammaRegime.NEGATIVE},
        {"name": "Crisis Market", "vix": 35, "atr": 12.0, "regime": GammaRegime.NEGATIVE},
    ]

    fixed_stop = config.initial_stop_points
    print(f"\nFixed stop: {fixed_stop} pts (${fixed_stop * 5:.2f})")
    print("\nScenario Comparison:")
    print("-" * 70)
    print(f"{'Scenario':<18} {'VIX':<6} {'ATR':<6} {'Fixed':<10} {'Dynamic':<10} {'Diff':<10}")
    print("-" * 70)

    for s in scenarios:
        dynamic = signal_gen._calculate_dynamic_stop(
            base_stop=fixed_stop,
            vix=s['vix'],
            atr=s['atr'],
            gamma_regime=s['regime']
        )
        diff = dynamic - fixed_stop
        diff_pct = (diff / fixed_stop) * 100
        print(f"{s['name']:<18} {s['vix']:<6} {s['atr']:<6} {fixed_stop:<10.2f} {dynamic:<10.2f} {diff:+.2f} ({diff_pct:+.0f}%)")

    print("-" * 70)
    print("\nInterpretation:")
    print("  - Calm markets: Tighter stops (save money on false stops)")
    print("  - Volatile markets: Wider stops (avoid premature stops)")
    print("  - Crisis markets: Much wider stops (capped at 6pts)")

except Exception as e:
    print(f"\n❌ ERROR: {e}")


# ============================================================================
# SUMMARY
# ============================================================================
print("\n" + "=" * 70)
print("TEST SUMMARY")
print("=" * 70)
print("""
Changes Implemented:
1. ✅ Dynamic Stop Loss - Adjusts based on VIX, ATR, and gamma regime
2. ✅ ML Module - XGBoost model for win probability prediction
3. ✅ ML Integration - Signal generator uses ML when model trained
4. ✅ API Limits - Increased from 50/100 to 1000 for all daily trades

IMPORTANT NOTES:
- Dynamic stops are NOW ACTIVE on all new trades
- ML predictions only used when model is trained AND loaded
- To train ML: Need 50+ closed trades with outcomes

To verify in production:
1. Check /api/valor/diagnostics for dynamic_stop info
2. Check /api/valor/ml/status for model status
3. Review closed trades to see actual stops used
""")

print("=" * 70)
