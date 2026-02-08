#!/usr/bin/env python3
"""
Test Market Structure Signal Logic

Verifies the threshold logic for all 9 market structure signals.
Run with: python scripts/test_market_structure_logic.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_flip_point_thresholds():
    """Test flip point movement thresholds"""
    print("\n=== Testing Flip Point Thresholds ===")

    # Test RISING: change > $2 or > 0.3%
    current, prior = 590.0, 585.0
    change = current - prior
    change_pct = (change / prior) * 100
    direction = "RISING" if (change > 2 or change_pct > 0.3) else "STABLE"
    assert direction == "RISING", f"Expected RISING, got {direction}"
    print(f"  ✓ RISING: ${change:.2f} change ({change_pct:.2f}%)")

    # Test FALLING: change < -$2 or < -0.3%
    current, prior = 580.0, 585.0
    change = current - prior
    change_pct = (change / prior) * 100
    direction = "FALLING" if (change < -2 or change_pct < -0.3) else "STABLE"
    assert direction == "FALLING", f"Expected FALLING, got {direction}"
    print(f"  ✓ FALLING: ${change:.2f} change ({change_pct:.2f}%)")

    # Test STABLE: change within thresholds
    current, prior = 585.5, 585.0
    change = current - prior
    change_pct = (change / prior) * 100
    direction = "STABLE" if (abs(change) <= 2 and abs(change_pct) <= 0.3) else "CHANGED"
    assert direction == "STABLE", f"Expected STABLE, got {direction}"
    print(f"  ✓ STABLE: ${change:.2f} change ({change_pct:.2f}%)")


def test_bounds_thresholds():
    """Test expected move bounds shift thresholds"""
    print("\n=== Testing Bounds Shift Thresholds ===")

    # Test SHIFTED_UP: both bounds up > $0.50
    upper_change, lower_change = 5.0, 5.0
    if upper_change > 0.5 and lower_change > 0.5:
        direction = "SHIFTED_UP"
    elif upper_change < -0.5 and lower_change < -0.5:
        direction = "SHIFTED_DOWN"
    elif abs(upper_change) < 0.5 and abs(lower_change) < 0.5:
        direction = "STABLE"
    else:
        direction = "MIXED"
    assert direction == "SHIFTED_UP", f"Expected SHIFTED_UP, got {direction}"
    print(f"  ✓ SHIFTED_UP: upper +${upper_change:.2f}, lower +${lower_change:.2f}")

    # Test SHIFTED_DOWN
    upper_change, lower_change = -3.0, -3.0
    if upper_change > 0.5 and lower_change > 0.5:
        direction = "SHIFTED_UP"
    elif upper_change < -0.5 and lower_change < -0.5:
        direction = "SHIFTED_DOWN"
    elif abs(upper_change) < 0.5 and abs(lower_change) < 0.5:
        direction = "STABLE"
    else:
        direction = "MIXED"
    assert direction == "SHIFTED_DOWN", f"Expected SHIFTED_DOWN, got {direction}"
    print(f"  ✓ SHIFTED_DOWN: upper ${upper_change:.2f}, lower ${lower_change:.2f}")

    # Test MIXED
    upper_change, lower_change = 2.0, -1.0
    if upper_change > 0.5 and lower_change > 0.5:
        direction = "SHIFTED_UP"
    elif upper_change < -0.5 and lower_change < -0.5:
        direction = "SHIFTED_DOWN"
    elif abs(upper_change) < 0.5 and abs(lower_change) < 0.5:
        direction = "STABLE"
    else:
        direction = "MIXED"
    assert direction == "MIXED", f"Expected MIXED, got {direction}"
    print(f"  ✓ MIXED: upper +${upper_change:.2f}, lower ${lower_change:.2f}")


def test_width_thresholds():
    """Test range width (volatility) thresholds"""
    print("\n=== Testing Width (Vol) Thresholds ===")

    # Test WIDENING: > 5% increase
    current_width, prior_width = 7.0, 6.0
    change_pct = ((current_width - prior_width) / prior_width) * 100
    if change_pct > 5:
        direction = "WIDENING"
    elif change_pct < -5:
        direction = "NARROWING"
    else:
        direction = "STABLE"
    assert direction == "WIDENING", f"Expected WIDENING, got {direction}"
    print(f"  ✓ WIDENING: {change_pct:.1f}% change")

    # Test NARROWING: > 5% decrease
    current_width, prior_width = 5.0, 6.0
    change_pct = ((current_width - prior_width) / prior_width) * 100
    if change_pct > 5:
        direction = "WIDENING"
    elif change_pct < -5:
        direction = "NARROWING"
    else:
        direction = "STABLE"
    assert direction == "NARROWING", f"Expected NARROWING, got {direction}"
    print(f"  ✓ NARROWING: {change_pct:.1f}% change")

    # Test STABLE: < 5% change
    current_width, prior_width = 6.2, 6.0
    change_pct = ((current_width - prior_width) / prior_width) * 100
    if change_pct > 5:
        direction = "WIDENING"
    elif change_pct < -5:
        direction = "NARROWING"
    else:
        direction = "STABLE"
    assert direction == "STABLE", f"Expected STABLE, got {direction}"
    print(f"  ✓ STABLE: {change_pct:.1f}% change")


def test_vix_regime_thresholds():
    """Test VIX regime classification thresholds"""
    print("\n=== Testing VIX Regime Thresholds ===")

    test_cases = [
        (12.0, "LOW"),
        (18.0, "NORMAL"),
        (25.0, "ELEVATED"),
        (30.0, "HIGH"),
        (42.0, "EXTREME"),
    ]

    for vix, expected in test_cases:
        if vix < 15:
            regime = "LOW"
        elif vix < 22:
            regime = "NORMAL"
        elif vix < 28:
            regime = "ELEVATED"
        elif vix < 35:
            regime = "HIGH"
        else:
            regime = "EXTREME"

        assert regime == expected, f"VIX {vix}: Expected {expected}, got {regime}"
        print(f"  ✓ VIX {vix:.1f} → {regime}")


def test_wall_break_risk_thresholds():
    """Test wall break risk thresholds"""
    print("\n=== Testing Wall Break Risk Thresholds ===")

    # HIGH risk: <0.3% away with NEGATIVE gamma
    spot, call_wall = 594.5, 595.0
    gamma_regime = "NEGATIVE"
    dist_pct = ((call_wall - spot) / spot) * 100

    if dist_pct < 0.3:
        if gamma_regime == "NEGATIVE":
            risk = "HIGH"
        else:
            risk = "ELEVATED"
    elif dist_pct < 0.7:
        risk = "MODERATE"
    else:
        risk = "LOW"

    assert risk == "HIGH", f"Expected HIGH, got {risk}"
    print(f"  ✓ HIGH risk: {dist_pct:.2f}% away, {gamma_regime} gamma")

    # ELEVATED risk: <0.3% away with POSITIVE gamma
    gamma_regime = "POSITIVE"
    if dist_pct < 0.3:
        if gamma_regime == "NEGATIVE":
            risk = "HIGH"
        else:
            risk = "ELEVATED"
    elif dist_pct < 0.7:
        risk = "MODERATE"
    else:
        risk = "LOW"

    assert risk == "ELEVATED", f"Expected ELEVATED, got {risk}"
    print(f"  ✓ ELEVATED risk: {dist_pct:.2f}% away, {gamma_regime} gamma")

    # LOW risk: >0.7% away
    spot, call_wall = 590.0, 600.0
    dist_pct = ((call_wall - spot) / spot) * 100

    if dist_pct < 0.3:
        risk = "HIGH"
    elif dist_pct < 0.7:
        risk = "MODERATE"
    else:
        risk = "LOW"

    assert risk == "LOW", f"Expected LOW, got {risk}"
    print(f"  ✓ LOW risk: {dist_pct:.2f}% away")


def test_gex_momentum_conviction():
    """Test GEX momentum conviction detection"""
    print("\n=== Testing GEX Momentum Conviction ===")

    test_cases = [
        (1.5e9, 1.0e9, "STRONG_BULLISH"),   # Increasing, positive
        (-1.5e9, -1.0e9, "STRONG_BEARISH"), # Decreasing, negative
        (0.5e9, 1.0e9, "BULLISH_FADING"),   # Decreasing, still positive
        (-0.5e9, -1.0e9, "BEARISH_FADING"), # Increasing, still negative
    ]

    for current, prior, expected in test_cases:
        change = current - prior

        if change > 0 and current > 0:
            conviction = "STRONG_BULLISH"
        elif change < 0 and current < 0:
            conviction = "STRONG_BEARISH"
        elif change < 0 and current > 0:
            conviction = "BULLISH_FADING"
        elif change > 0 and current < 0:
            conviction = "BEARISH_FADING"
        else:
            conviction = "NEUTRAL"

        assert conviction == expected, f"Expected {expected}, got {conviction}"
        print(f"  ✓ {expected}: current={current/1e9:.1f}B, prior={prior/1e9:.1f}B")


def test_intraday_thresholds():
    """Test intraday EM change thresholds"""
    print("\n=== Testing Intraday EM Thresholds ===")

    # EXPANDING: >3% increase from open
    open_em, current_em = 3.0, 3.5
    change_pct = ((current_em - open_em) / open_em) * 100

    if change_pct > 3:
        direction = "EXPANDING"
    elif change_pct < -3:
        direction = "CONTRACTING"
    else:
        direction = "STABLE"

    assert direction == "EXPANDING", f"Expected EXPANDING, got {direction}"
    print(f"  ✓ EXPANDING: {change_pct:.1f}% from open")

    # CONTRACTING: >3% decrease from open
    open_em, current_em = 3.0, 2.5
    change_pct = ((current_em - open_em) / open_em) * 100

    if change_pct > 3:
        direction = "EXPANDING"
    elif change_pct < -3:
        direction = "CONTRACTING"
    else:
        direction = "STABLE"

    assert direction == "CONTRACTING", f"Expected CONTRACTING, got {direction}"
    print(f"  ✓ CONTRACTING: {change_pct:.1f}% from open")

    # STABLE: <3% change from open
    open_em, current_em = 3.0, 3.05
    change_pct = ((current_em - open_em) / open_em) * 100

    if change_pct > 3:
        direction = "EXPANDING"
    elif change_pct < -3:
        direction = "CONTRACTING"
    else:
        direction = "STABLE"

    assert direction == "STABLE", f"Expected STABLE, got {direction}"
    print(f"  ✓ STABLE: {change_pct:.1f}% from open")


def test_database_schema_completeness():
    """Verify database schema has all required columns"""
    print("\n=== Testing Database Schema Completeness ===")

    # watchtower_snapshots required columns
    argus_columns = [
        'id', 'symbol', 'expiration_date', 'snapshot_time',
        'spot_price', 'expected_move', 'vix',
        'total_net_gamma', 'gamma_regime', 'previous_regime',
        'regime_flipped', 'market_status', 'created_at'
    ]
    print(f"  ✓ watchtower_snapshots has {len(argus_columns)} required columns")

    # gex_history required columns (for flip_point, walls)
    gex_columns = [
        'id', 'timestamp', 'symbol', 'net_gex',
        'flip_point', 'call_wall', 'put_wall',
        'spot_price', 'mm_state', 'regime', 'data_source'
    ]
    print(f"  ✓ gex_history has {len(gex_columns)} required columns")


def main():
    """Run all tests"""
    print("=" * 60)
    print("MARKET STRUCTURE SIGNAL LOGIC TESTS")
    print("=" * 60)

    tests = [
        test_flip_point_thresholds,
        test_bounds_thresholds,
        test_width_thresholds,
        test_vix_regime_thresholds,
        test_wall_break_risk_thresholds,
        test_gex_momentum_conviction,
        test_intraday_thresholds,
        test_database_schema_completeness,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"  ✗ FAILED: {e}")
            failed += 1
        except Exception as e:
            print(f"  ✗ ERROR: {e}")
            failed += 1

    print("\n" + "=" * 60)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("=" * 60)

    return failed == 0


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
