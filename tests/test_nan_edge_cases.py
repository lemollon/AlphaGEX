"""
Test edge cases that could produce NaN in realistic pricing
"""

from utils.realistic_option_pricing import create_bullish_call_spread, SpreadPricer

print("Testing Edge Cases for NaN Prevention")
print("=" * 60)

# Test 1: Very narrow spread (could cause debit > width)
print("\nTest 1: Very narrow spread (1% wide)")
try:
    spread = create_bullish_call_spread(
        spot_price=400.0,
        volatility=0.25,
        dte=30,
        target_delta=0.30,
        spread_width_pct=1.0  # Very narrow - 1% wide
    )
    print(f"  ✓ Spread created: ${spread['long_strike']:.0f}/${spread['short_strike']:.0f}")
    print(f"  ✓ Debit: ${spread['debit']:.2f}, Width: ${spread['spread_width']:.2f}")
    print(f"  ✓ Max Profit: ${spread['max_profit']:.2f}, Max Loss: ${spread['max_loss']:.2f}")

    # Test P&L calculation
    pricer = SpreadPricer()
    pnl = pricer.calculate_spread_pnl(
        spread_details=spread,
        current_price=410.0,
        days_held=10,
        entry_volatility=0.25
    )

    if str(pnl['pnl_percent']) == 'nan':
        print(f"  ❌ NaN detected in P&L: {pnl['pnl_percent']}")
    else:
        print(f"  ✓ P&L: {pnl['pnl_percent']:.2f}% (valid, not NaN)")
except Exception as e:
    print(f"  ⚠️ Exception: {e}")

# Test 2: Very high volatility (extreme pricing)
print("\nTest 2: Very high IV (50%)")
try:
    spread = create_bullish_call_spread(
        spot_price=400.0,
        volatility=0.50,  # 50% IV - very high
        dte=30,
        target_delta=0.30,
        spread_width_pct=5.0
    )
    print(f"  ✓ Spread created with high IV")
    print(f"  ✓ Debit: ${spread['debit']:.2f}")

    pricer = SpreadPricer()
    pnl = pricer.calculate_spread_pnl(
        spread_details=spread,
        current_price=410.0,
        days_held=10,
        entry_volatility=0.50,
        exit_volatility=0.30  # IV crush
    )

    if str(pnl['pnl_percent']) == 'nan':
        print(f"  ❌ NaN detected in P&L: {pnl['pnl_percent']}")
    else:
        print(f"  ✓ P&L: {pnl['pnl_percent']:.2f}% (valid, not NaN)")
except Exception as e:
    print(f"  ⚠️ Exception: {e}")

# Test 3: Short DTE (1 day to expiry)
print("\nTest 3: Very short DTE (1 day)")
try:
    spread = create_bullish_call_spread(
        spot_price=400.0,
        volatility=0.25,
        dte=1,  # 1 day to expiry
        target_delta=0.30,
        spread_width_pct=5.0
    )
    print(f"  ✓ Spread created with 1 DTE")
    print(f"  ✓ Debit: ${spread['debit']:.2f}")

    pricer = SpreadPricer()
    pnl = pricer.calculate_spread_pnl(
        spread_details=spread,
        current_price=410.0,
        days_held=0,  # Same day
        entry_volatility=0.25
    )

    if str(pnl['pnl_percent']) == 'nan':
        print(f"  ❌ NaN detected in P&L: {pnl['pnl_percent']}")
    else:
        print(f"  ✓ P&L: {pnl['pnl_percent']:.2f}% (valid, not NaN)")
except Exception as e:
    print(f"  ⚠️ Exception: {e}")

# Test 4: Zero debit edge case
print("\nTest 4: Simulated near-zero debit")
try:
    spread = create_bullish_call_spread(
        spot_price=400.0,
        volatility=0.10,  # Very low IV
        dte=1,
        target_delta=0.05,  # Very OTM
        spread_width_pct=2.0
    )
    print(f"  ✓ Spread created: Debit ${spread['debit']:.4f}")

    # Manually override debit to test edge case
    test_spread = spread.copy()
    test_spread['debit'] = 0.005  # Half a cent

    pricer = SpreadPricer()
    pnl = pricer.calculate_spread_pnl(
        spread_details=test_spread,
        current_price=410.0,
        days_held=1,
        entry_volatility=0.10
    )

    if str(pnl['pnl_percent']) == 'nan':
        print(f"  ❌ NaN detected in P&L: {pnl['pnl_percent']}")
    else:
        print(f"  ✓ P&L handled edge case: {pnl['pnl_percent']:.2f}% (should be 0 or capped)")
except Exception as e:
    print(f"  ⚠️ Exception: {e}")

# Test 5: Expired option (0 DTE held full period)
print("\nTest 5: Held to expiration (DTE reaches 0)")
try:
    spread = create_bullish_call_spread(
        spot_price=400.0,
        volatility=0.25,
        dte=10,
        target_delta=0.30,
        spread_width_pct=5.0
    )
    print(f"  ✓ Spread created with 10 DTE")

    pricer = SpreadPricer()
    pnl = pricer.calculate_spread_pnl(
        spread_details=spread,
        current_price=425.0,  # ITM at expiration
        days_held=10,  # Full DTE elapsed
        entry_volatility=0.25
    )

    if str(pnl['pnl_percent']) == 'nan':
        print(f"  ❌ NaN detected in P&L: {pnl['pnl_percent']}")
    else:
        print(f"  ✓ P&L at expiration: {pnl['pnl_percent']:.2f}% (valid, not NaN)")
        print(f"  ✓ Intrinsic: ${pnl['intrinsic_value']:.2f}, Time: ${pnl['time_value']:.2f}")
except Exception as e:
    print(f"  ⚠️ Exception: {e}")

print("\n" + "=" * 60)
print("✅ All edge case tests completed")
print("If any NaN values were detected above, the fix needs adjustment")
print("=" * 60)
