"""
Demo: Enhanced Dealer Hedging Feedback Loop Analysis

This script demonstrates the new features:
1. Detailed feedback loop mechanics explaining WHY it happens
2. Volume analysis at high OI strikes
3. Probability calculations for breakout/rejection
4. 2x volume threshold for dealer activity confirmation

Author: AlphaGEX Team
Date: 2025-11-15
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from core_classes_and_engines import GEXAnalyzer
from core.psychology_trap_detector import (
    analyze_dealer_feedback_loop_mechanics,
    calculate_breakout_rejection_probability
)
from db.config_and_database import DB_PATH
from database_adapter import get_connection


def demo_enhanced_feedback_loop():
    """
    Demonstrate the enhanced dealer hedging feedback loop analysis
    """
    print("\n" + "="*80)
    print("ENHANCED DEALER HEDGING FEEDBACK LOOP ANALYSIS - DEMONSTRATION")
    print("="*80 + "\n")

    # Step 1: Load latest options data
    print("📊 Step 1: Loading latest options data...")
    conn = get_connection()

    # Get most recent data date
    query = "SELECT MAX(timestamp) as latest FROM option_chain"
    latest_timestamp = pd.read_sql(query, conn.raw_connection)['latest'].iloc[0]

    # Load options data for latest timestamp
    query = f"""
        SELECT strike, option_type, open_interest, volume, implied_volatility,
               expiration, underlying_price
        FROM option_chain
        WHERE timestamp = '{latest_timestamp}'
    """
    options_df = pd.read_sql(query, conn.raw_connection)
    conn.close()

    if options_df.empty:
        print("❌ No options data found. Please run fetch_and_store_gex_data.py first.")
        return

    current_price = options_df['underlying_price'].iloc[0]
    print(f"✅ Loaded {len(options_df)} options contracts")
    print(f"   Current SPY Price: ${current_price:.2f}")
    print(f"   Data Timestamp: {latest_timestamp}\n")

    # Step 2: Initialize GEX Analyzer
    print("📊 Step 2: Analyzing gamma exposure...")
    gex_analyzer = GEXAnalyzer(ticker='SPY', spot_price=current_price)
    gex_analyzer.load_options_data(options_df)

    # Calculate GEX
    gex_df = gex_analyzer.calculate_gex()
    key_levels = gex_analyzer.identify_key_levels()

    print(f"✅ Net GEX: ${gex_analyzer.net_gex / 1e9:.2f}B")
    print(f"   Gamma Flip: ${gex_analyzer.gamma_flip:.2f}")
    print(f"   Total Levels Identified: {len(key_levels)}\n")

    # Step 3: Analyze strike-level volume activity
    print("📊 Step 3: Analyzing volume activity at high OI strikes...")
    print("-" * 80)

    strike_volume_analysis = gex_analyzer.analyze_strike_volume_activity()

    if not strike_volume_analysis.empty:
        print("\n🎯 HIGH OPEN INTEREST STRIKES WITH UNUSUAL VOLUME:")
        print(f"\n{'Strike':<10} {'OI':<12} {'Volume':<10} {'Vol/OI':<10} {'GEX':<15} {'Hedging':<12}")
        print("-" * 80)

        for idx, row in strike_volume_analysis.head(10).iterrows():
            gex_str = f"${row['gex']/1e6:.1f}M" if abs(row['gex']) > 1e6 else f"${row['gex']/1e3:.1f}K"
            print(f"${row['strike']:<9.2f} {int(row['open_interest']):<12,} "
                  f"{int(row['volume']):<10,} {row['volume_oi_ratio']:<10.2f} "
                  f"{gex_str:<15} {row['hedging_intensity']:<12}")
            if row['volume_oi_ratio'] > 2.0:
                print(f"         → {row['interpretation']}")

        print("\n💡 INTERPRETATION:")
        active_hedging = strike_volume_analysis[strike_volume_analysis['volume_oi_ratio'] > 2.0]
        if len(active_hedging) > 0:
            print(f"   ✅ {len(active_hedging)} strikes show volume/OI > 2.0x = DEALER HEDGING ACTIVE")
            print("   → Dealers are actively rebalancing positions at these strikes")
            print("   → This confirms real price pressure, not just noise")
        else:
            print("   ⚠️ No strikes showing volume/OI > 2.0x")
            print("   → Minimal dealer hedging detected")
            print("   → Low volume suggests weak conviction in current move")
    else:
        print("⚠️ No high OI strikes found")

    # Step 4: Analyze feedback loop mechanics
    print("\n\n" + "="*80)
    print("📊 Step 4: DEALER HEDGING FEEDBACK LOOP MECHANICS ANALYSIS")
    print("="*80)

    # Calculate price momentum (simulate 1% up move for demo)
    price_momentum = 0.8  # Assume 0.8% upward move
    volume_ratio = 2.3  # Assume 2.3x average volume

    # Prepare strike data for analysis
    strike_data = options_df.groupby('strike').agg({
        'open_interest': 'sum',
        'volume': 'sum'
    }).reset_index()

    # Add GEX data
    gex_by_strike = gex_df.groupby('strike')['gex'].sum().reset_index()
    strike_data = strike_data.merge(gex_by_strike, on='strike', how='left')
    strike_data['gex'] = strike_data['gex'].fillna(0)

    # Analyze feedback loop
    feedback_analysis = analyze_dealer_feedback_loop_mechanics(
        strike_data=strike_data,
        current_price=current_price,
        net_gex=gex_analyzer.net_gex,
        price_momentum=price_momentum,
        volume_ratio=volume_ratio
    )

    print(feedback_analysis['mechanics_explanation'])

    if feedback_analysis['feedback_loop_active']:
        print(f"\n🔥 FEEDBACK LOOP DETECTED!")
        print(f"   Strength: {feedback_analysis['loop_strength'].upper()}")
        print(f"   Direction: {feedback_analysis['direction'].upper()}")
        print(f"   Amplification Factor: {feedback_analysis['amplification_factor']:.2f}x")
        print(f"   Dealer Hedging Pressure: ${feedback_analysis['dealer_hedging_pressure']:.1f}M")

        print(f"\n📋 Supporting Evidence:")
        for evidence in feedback_analysis['supporting_evidence']:
            print(f"   • {evidence}")

    # Step 5: Calculate breakout/rejection probability
    print("\n\n" + "="*80)
    print("📊 Step 5: BREAKOUT/REJECTION PROBABILITY ANALYSIS")
    print("="*80)

    # Get resistance and support levels
    call_wall = key_levels.get('call_wall_1')
    put_wall = key_levels.get('put_wall_1')

    if call_wall and put_wall:
        resistance_strike = call_wall.strike
        support_strike = put_wall.strike

        # Calculate probability
        probability_analysis = calculate_breakout_rejection_probability(
            current_price=current_price,
            resistance_strike=resistance_strike,
            support_strike=support_strike,
            net_gex=gex_analyzer.net_gex,
            strike_gex=call_wall.gex_value,  # GEX at resistance
            volume_ratio=volume_ratio,
            rsi_score=45,  # Simulate neutral RSI
            price_momentum=price_momentum,
            dealer_hedging_pressure=feedback_analysis['dealer_hedging_pressure'],
            distance_to_gamma_flip=abs((current_price - gex_analyzer.gamma_flip) / current_price * 100)
        )

        print(f"\n🎯 TESTING LEVEL: ${probability_analysis['level_price']:.2f} ({probability_analysis['level_type'].upper()})")
        print(f"   Distance from current price: {probability_analysis['distance_pct']:+.2f}%")
        print(f"\n📊 PROBABILITY BREAKDOWN:")
        print(f"   Breakout Probability: {probability_analysis['breakout_probability']:.1f}%")
        print(f"   Rejection Probability: {probability_analysis['rejection_probability']:.1f}%")
        print(f"   Confidence Level: {probability_analysis['confidence'].upper()}")

        print(f"\n🔍 LOGIC BREAKDOWN (Transparent Scoring):")
        for factor_name, factor_data in probability_analysis['logic_breakdown'].items():
            print(f"\n   {factor_name.upper().replace('_', ' ')}:")
            print(f"      Score: {factor_data['score']}/{factor_data['weight']} points")
            print(f"      {factor_data['explanation']}")

        print(f"\n💡 RECOMMENDATION:")
        print(f"   {probability_analysis['recommendation']}")

        print(f"\n📋 Key Factors Driving This Probability:")
        for factor in probability_analysis['key_factors']:
            print(f"   • {factor}")

    else:
        print("⚠️ Call wall or put wall not found - cannot calculate probability")

    # Step 6: Summary and Trading Implications
    print("\n\n" + "="*80)
    print("📊 SUMMARY & TRADING IMPLICATIONS")
    print("="*80)

    print("\n🔑 KEY TAKEAWAYS:")

    if feedback_analysis['feedback_loop_active']:
        print(f"\n1. FEEDBACK LOOP ACTIVE ({feedback_analysis['loop_strength'].upper()})")
        print(f"   • Trade WITH the dealer flow, not against it")
        print(f"   • Direction: {feedback_analysis['direction'].upper()}")
        print(f"   • Move amplified by {(feedback_analysis['amplification_factor'] - 1) * 100:.0f}%")

    if volume_ratio >= 2.0:
        print(f"\n2. VOLUME CONFIRMATION ✅")
        print(f"   • {volume_ratio:.2f}x average volume confirms real dealer activity")
        print(f"   • Not just noise - this is a genuine move")
    else:
        print(f"\n2. VOLUME TOO LOW ⚠️")
        print(f"   • {volume_ratio:.2f}x average - need 2.0x minimum")
        print(f"   • Without volume, move likely to fail")

    active_strikes = len(strike_volume_analysis[strike_volume_analysis['volume_oi_ratio'] > 2.0])
    if active_strikes > 0:
        print(f"\n3. ACTIVE DEALER HEDGING DETECTED")
        print(f"   • {active_strikes} strikes showing volume/OI > 2.0x")
        print(f"   • Dealers are rebalancing positions RIGHT NOW")
    else:
        print(f"\n3. NO ACTIVE DEALER HEDGING")
        print(f"   • No strikes showing unusual volume")
        print(f"   • Current move may lack conviction")

    if call_wall and put_wall:
        print(f"\n4. SUPPORT/RESISTANCE LEVELS")
        print(f"   • Resistance (Call Wall): ${call_wall.strike:.2f} ({call_wall.distance_from_spot:+.2f}%)")
        print(f"   • Support (Put Wall): ${put_wall.strike:.2f} ({put_wall.distance_from_spot:+.2f}%)")
        if 'probability_analysis' in locals():
            print(f"   • {probability_analysis['recommendation']}")

    print("\n\n" + "="*80)
    print("✅ DEMO COMPLETE")
    print("="*80 + "\n")


if __name__ == "__main__":
    demo_enhanced_feedback_loop()
