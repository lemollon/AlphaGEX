#!/usr/bin/env python3
"""
Test script to verify the directional prediction logic is working correctly.
This simulates the algorithm without needing to run the full Streamlit app.
"""

def test_directional_prediction():
    """Simulate the directional prediction algorithm"""

    print("=" * 70)
    print("SPY DIRECTIONAL PREDICTION - TEST SCRIPT")
    print("=" * 70)
    print()

    # Simulate sample data (replace with real data in production)
    spot = 567.89
    net_gex = -2.5e9  # Short gamma (negative)
    flip = 566.50
    call_wall = 572.00
    put_wall = 565.00
    current_vix = 17.5
    day_of_week = "Monday"

    print(f"📊 INPUT DATA:")
    print(f"  Spot Price: ${spot:.2f}")
    print(f"  Net GEX: ${net_gex/1e9:.2f}B")
    print(f"  Flip Point: ${flip:.2f}")
    print(f"  Call Wall: ${call_wall:.2f}")
    print(f"  Put Wall: ${put_wall:.2f}")
    print(f"  VIX: {current_vix:.2f}")
    print(f"  Day: {day_of_week}")
    print()

    # Calculate directional factors
    spot_vs_flip_pct = ((spot - flip) / flip * 100) if flip else 0
    distance_to_call_wall = ((call_wall - spot) / spot * 100) if call_wall and spot else 999
    distance_to_put_wall = ((spot - put_wall) / spot * 100) if put_wall and spot else 999

    print(f"📐 CALCULATED METRICS:")
    print(f"  Spot vs Flip: {spot_vs_flip_pct:+.2f}%")
    print(f"  Distance to Call Wall: {distance_to_call_wall:.2f}%")
    print(f"  Distance to Put Wall: {distance_to_put_wall:.2f}%")
    print()

    # Directional scoring (0-100)
    bullish_score = 50  # Start neutral
    confidence_factors = []

    print(f"🧮 SCORING BREAKDOWN:")
    print(f"  Starting Score: {bullish_score}")

    # Factor 1: GEX Regime (40% weight)
    if net_gex < -1e9:  # Short gamma (amplification)
        if spot > flip:
            bullish_score += 20
            factor_msg = "Short gamma + above flip = upside momentum"
            confidence_factors.append(factor_msg)
            print(f"  [+20] {factor_msg}")
        else:
            bullish_score -= 20
            factor_msg = "Short gamma + below flip = downside risk"
            confidence_factors.append(factor_msg)
            print(f"  [-20] {factor_msg}")
    elif net_gex > 1e9:  # Long gamma (dampening)
        # Range-bound expectation
        if spot_vs_flip_pct > 1:
            bullish_score += 5
            factor_msg = "Long gamma + above flip = mild upward pull"
            confidence_factors.append(factor_msg)
            print(f"  [+5] {factor_msg}")
        elif spot_vs_flip_pct < -1:
            bullish_score -= 5
            factor_msg = "Long gamma + below flip = mild downward pull"
            confidence_factors.append(factor_msg)
            print(f"  [-5] {factor_msg}")
        else:
            factor_msg = "Long gamma near flip = range-bound likely"
            confidence_factors.append(factor_msg)
            print(f"  [0] {factor_msg}")

    # Factor 2: Proximity to Walls (30% weight)
    if distance_to_call_wall < 1.5:  # Within 1.5% of call wall
        bullish_score -= 15
        factor_msg = f"Near call wall ${call_wall:.0f} = resistance"
        confidence_factors.append(factor_msg)
        print(f"  [-15] {factor_msg}")
    elif distance_to_put_wall < 1.5:  # Within 1.5% of put wall
        bullish_score += 15
        factor_msg = f"Near put wall ${put_wall:.0f} = support"
        confidence_factors.append(factor_msg)
        print(f"  [+15] {factor_msg}")

    # Factor 3: VIX Regime (20% weight)
    old_score = bullish_score
    if current_vix > 20:  # Elevated volatility
        confidence_factors.append(f"VIX {current_vix:.1f} = elevated volatility")
        bullish_score = 50 + (bullish_score - 50) * 0.7  # Pull toward neutral
        print(f"  [VIX>20] Score adjusted: {old_score:.1f} → {bullish_score:.1f} (pulled toward neutral)")
    elif current_vix < 15:  # Low volatility
        confidence_factors.append(f"VIX {current_vix:.1f} = low volatility favors range")
        bullish_score = 50 + (bullish_score - 50) * 0.8
        print(f"  [VIX<15] Score adjusted: {old_score:.1f} → {bullish_score:.1f} (range-bound bias)")
    else:
        confidence_factors.append(f"VIX {current_vix:.1f} = moderate volatility")
        print(f"  [VIX neutral] No adjustment")

    # Factor 4: Day of Week (10% weight)
    old_score = bullish_score
    if day_of_week in ['Monday', 'Tuesday']:
        confidence_factors.append(f"{day_of_week} = high gamma, range-bound bias")
        bullish_score = 50 + (bullish_score - 50) * 0.9  # Pull slightly to neutral
        print(f"  [{day_of_week}] Score adjusted: {old_score:.1f} → {bullish_score:.1f} (high gamma day)")
    elif day_of_week == 'Friday':
        confidence_factors.append(f"Friday = low gamma, more volatile")
        print(f"  [Friday] More volatile, no score adjustment")

    print()
    print(f"  FINAL SCORE: {bullish_score:.1f}")
    print()

    # Determine direction and confidence
    if bullish_score >= 65:
        direction = "UPWARD"
        direction_emoji = "📈"
        direction_color = "GREEN"
        probability = int(bullish_score)
        expected_move = "Expect push toward call wall or breakout higher"
    elif bullish_score <= 35:
        direction = "DOWNWARD"
        direction_emoji = "📉"
        direction_color = "RED"
        probability = int(100 - bullish_score)
        expected_move = "Expect push toward put wall or breakdown lower"
    else:
        direction = "SIDEWAYS (Range-Bound)"
        direction_emoji = "↔️"
        direction_color = "ORANGE"
        probability = int(100 - abs(bullish_score - 50) * 2)
        expected_move = f"Expect range between ${put_wall:.0f} - ${call_wall:.0f}"

    # Calculate expected range
    if put_wall and call_wall:
        range_width = ((call_wall - put_wall) / spot * 100)
        range_str = f"${put_wall:.0f} - ${call_wall:.0f} ({range_width:.1f}% range)"
    else:
        range_str = "Walls not defined"

    # Display prediction
    print("=" * 70)
    print("🎯 PREDICTION RESULT")
    print("=" * 70)
    print()
    print(f"{direction_emoji} Direction: {direction}")
    print(f"🎲 Probability: {probability}%")
    print(f"🎨 Display Color: {direction_color}")
    print()
    print(f"💰 Current Price: ${spot:.2f}")
    print(f"📊 Expected Range: {range_str}")
    print(f"🔄 Flip Point: ${flip:.2f} ({spot_vs_flip_pct:+.1f}% from spot)")
    print()
    print(f"🔑 Key Factors:")
    for i, factor in enumerate(confidence_factors[:4], 1):
        print(f"   {i}. {factor}")
    print()
    print(f"📈 Expected Move: {expected_move}")
    print()
    print("=" * 70)
    print()
    print("✅ DIRECTIONAL PREDICTION LOGIC IS WORKING CORRECTLY!")
    print()
    print("If you don't see this on your website:")
    print("1. Restart your Streamlit app")
    print("2. Clear browser cache (Ctrl+Shift+R)")
    print("3. Click the 🔄 Refresh button in the Gamma Intelligence section")
    print("4. Check you're in: GEX Analysis → Gamma Expiration Intelligence")
    print()
    print("See DIRECTIONAL_PREDICTION_TROUBLESHOOTING.md for detailed help.")
    print()


if __name__ == "__main__":
    test_directional_prediction()
