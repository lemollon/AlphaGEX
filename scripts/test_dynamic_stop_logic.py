#!/usr/bin/env python3
"""
Standalone test for dynamic stop loss logic.
No external dependencies required.
"""

from enum import Enum

class GammaRegime(Enum):
    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"
    NEUTRAL = "NEUTRAL"


def calculate_dynamic_stop(base_stop: float, vix: float, atr: float, gamma_regime: GammaRegime) -> float:
    """
    Calculate dynamic stop distance based on market conditions.
    
    This is the EXACT logic from trading/valor/signals.py
    """
    # 1. VIX Adjustment
    if vix <= 0:
        vix_multiplier = 1.0
    elif vix < 15:
        vix_multiplier = 0.80  # Calm markets - tighten 20%
    elif vix < 20:
        vix_multiplier = 1.0   # Normal - use base
    elif vix < 25:
        vix_multiplier = 1.20  # Elevated - widen 20%
    elif vix < 30:
        vix_multiplier = 1.40  # High - widen 40%
    else:
        vix_multiplier = 1.60  # Very high - widen 60%

    # 2. ATR Adjustment
    if atr <= 0:
        atr_multiplier = 1.0
    elif atr < 3:
        atr_multiplier = 0.85  # Low intraday vol - tighten 15%
    elif atr < 5:
        atr_multiplier = 1.0   # Normal
    elif atr < 8:
        atr_multiplier = 1.15  # Higher vol - widen 15%
    else:
        atr_multiplier = 1.30  # High vol - widen 30%

    # 3. Regime Adjustment
    if gamma_regime == GammaRegime.POSITIVE:
        regime_multiplier = 0.90  # Mean reversion - tighter
    elif gamma_regime == GammaRegime.NEGATIVE:
        regime_multiplier = 1.10  # Momentum - wider
    else:
        regime_multiplier = 1.0

    # Calculate final stop
    dynamic_stop = base_stop * vix_multiplier * atr_multiplier * regime_multiplier

    # Cap between 1.5 and 6 points
    MIN_STOP = 1.5
    MAX_STOP = 6.0
    capped_stop = max(MIN_STOP, min(MAX_STOP, dynamic_stop))

    return round(capped_stop, 2)


def main():
    print("=" * 70)
    print("DYNAMIC STOP LOSS LOGIC TEST")
    print("=" * 70)
    
    base_stop = 2.5  # Config default
    print(f"\nBase stop: {base_stop} pts (${base_stop * 5:.2f})")
    
    # Test cases with expected behavior
    test_cases = [
        # (VIX, ATR, Regime, Description)
        (12, 2.5, GammaRegime.POSITIVE, "Low VIX, Low ATR, Positive"),
        (12, 2.5, GammaRegime.NEGATIVE, "Low VIX, Low ATR, Negative"),
        (18, 4.0, GammaRegime.NEUTRAL, "Normal conditions"),
        (18, 4.0, GammaRegime.POSITIVE, "Normal VIX, Positive gamma"),
        (18, 4.0, GammaRegime.NEGATIVE, "Normal VIX, Negative gamma"),
        (22, 5.5, GammaRegime.NEGATIVE, "Elevated VIX, Higher ATR"),
        (28, 7.0, GammaRegime.NEGATIVE, "High VIX, High ATR"),
        (35, 10.0, GammaRegime.NEGATIVE, "Crisis (should cap at 6)"),
        (10, 1.5, GammaRegime.POSITIVE, "Very calm (should cap at 1.5)"),
    ]
    
    print("\nTest Results:")
    print("-" * 80)
    print(f"{'VIX':<6} {'ATR':<6} {'Regime':<12} {'Stop':<8} {'$Value':<10} {'Description':<25}")
    print("-" * 80)
    
    results = []
    for vix, atr, regime, desc in test_cases:
        stop = calculate_dynamic_stop(base_stop, vix, atr, regime)
        dollar = stop * 5.0
        results.append((vix, atr, regime, stop))
        print(f"{vix:<6} {atr:<6} {regime.value:<12} {stop:<8.2f} ${dollar:<9.2f} {desc}")
    
    print("-" * 80)
    
    # Run validation checks
    print("\n" + "=" * 70)
    print("VALIDATION CHECKS")
    print("=" * 70)
    
    tests_passed = 0
    tests_failed = 0
    
    # Test 1: Low VIX should produce tighter stop than High VIX (same regime)
    low_vix = [r for r in results if r[0] == 12 and r[2] == GammaRegime.NEGATIVE][0][3]
    high_vix = [r for r in results if r[0] == 28][0][3]
    if low_vix < high_vix:
        print(f"✅ TEST 1 PASS: Low VIX ({low_vix:.2f}) < High VIX ({high_vix:.2f})")
        tests_passed += 1
    else:
        print(f"❌ TEST 1 FAIL: Low VIX ({low_vix:.2f}) should be < High VIX ({high_vix:.2f})")
        tests_failed += 1
    
    # Test 2: Positive gamma should be tighter than Negative gamma (same VIX/ATR)
    pos = [r for r in results if r[0] == 18 and r[2] == GammaRegime.POSITIVE][0][3]
    neg = [r for r in results if r[0] == 18 and r[2] == GammaRegime.NEGATIVE][0][3]
    if pos < neg:
        print(f"✅ TEST 2 PASS: Positive gamma ({pos:.2f}) < Negative gamma ({neg:.2f})")
        tests_passed += 1
    else:
        print(f"❌ TEST 2 FAIL: Positive gamma ({pos:.2f}) should be < Negative gamma ({neg:.2f})")
        tests_failed += 1
    
    # Test 3: Crisis conditions should cap at 6.0
    crisis = [r for r in results if r[0] == 35][0][3]
    if crisis == 6.0:
        print(f"✅ TEST 3 PASS: Crisis stop capped at 6.0 pts")
        tests_passed += 1
    else:
        print(f"❌ TEST 3 FAIL: Crisis stop ({crisis:.2f}) should cap at 6.0")
        tests_failed += 1
    
    # Test 4: Very calm conditions should cap at 1.5
    calm = [r for r in results if r[0] == 10][0][3]
    if calm == 1.5:
        print(f"✅ TEST 4 PASS: Calm stop capped at 1.5 pts")
        tests_passed += 1
    else:
        print(f"❌ TEST 4 FAIL: Calm stop ({calm:.2f}) should cap at 1.5")
        tests_failed += 1
    
    # Test 5: All stops in valid range
    all_valid = all(1.5 <= r[3] <= 6.0 for r in results)
    if all_valid:
        print(f"✅ TEST 5 PASS: All stops in range [1.5, 6.0]")
        tests_passed += 1
    else:
        out_of_range = [r for r in results if not (1.5 <= r[3] <= 6.0)]
        print(f"❌ TEST 5 FAIL: Some stops out of range: {out_of_range}")
        tests_failed += 1
    
    # Test 6: Normal conditions should equal base stop
    normal = [r for r in results if r[0] == 18 and r[1] == 4.0 and r[2] == GammaRegime.NEUTRAL][0][3]
    if normal == base_stop:
        print(f"✅ TEST 6 PASS: Normal conditions equal base stop ({base_stop})")
        tests_passed += 1
    else:
        print(f"❌ TEST 6 FAIL: Normal conditions ({normal:.2f}) should equal base ({base_stop})")
        tests_failed += 1
    
    print("-" * 70)
    print(f"\nRESULTS: {tests_passed} passed, {tests_failed} failed")
    
    if tests_failed == 0:
        print("\n✅✅✅ ALL DYNAMIC STOP LOGIC TESTS PASSED ✅✅✅")
    else:
        print(f"\n❌ {tests_failed} test(s) failed - review logic")
    
    # Show impact analysis
    print("\n" + "=" * 70)
    print("IMPACT ANALYSIS: Dynamic vs Fixed Stop")
    print("=" * 70)
    
    scenarios = [
        ("Calm day (VIX=14, ATR=3)", 14, 3.0, GammaRegime.NEUTRAL),
        ("Normal day (VIX=17, ATR=4)", 17, 4.0, GammaRegime.NEUTRAL),
        ("Choppy day (VIX=22, ATR=5.5)", 22, 5.5, GammaRegime.NEGATIVE),
        ("Volatile day (VIX=28, ATR=8)", 28, 8.0, GammaRegime.NEGATIVE),
    ]
    
    print(f"\n{'Scenario':<35} {'Fixed':<10} {'Dynamic':<10} {'Diff':<10} {'$ Impact':<10}")
    print("-" * 75)
    
    for name, vix, atr, regime in scenarios:
        dynamic = calculate_dynamic_stop(base_stop, vix, atr, regime)
        diff = dynamic - base_stop
        dollar_diff = diff * 5
        print(f"{name:<35} {base_stop:<10.2f} {dynamic:<10.2f} {diff:+.2f}     ${dollar_diff:+.2f}")
    
    print("-" * 75)
    print("""
INTERPRETATION:
- On calm days: You SAVE money by not getting stopped out unnecessarily
- On volatile days: You AVOID premature stops that would have been winners
- The trade-off: Wider stops mean bigger losses when wrong

TO VALIDATE IN PRODUCTION:
Compare win rate and avg loss BEFORE vs AFTER dynamic stops
""")


if __name__ == "__main__":
    main()
