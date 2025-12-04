"""
Example usage of LangChain integration for AlphaGEX

This script demonstrates key features of the new LangChain-powered intelligence system.
"""

import os
from datetime import datetime
from ai.langchain_intelligence import LangChainIntelligence, get_quick_market_analysis, get_trade_recommendation
from ai.langchain_models import TradeRecommendation, OptionType
from ai.langchain_tools import (
    get_gex_data,
    analyze_gex_regime,
    calculate_position_size,
    get_volatility_regime
)


def example_1_basic_market_analysis():
    """
    Example 1: Basic market analysis using agent workflow
    """
    print("\n" + "="*70)
    print("EXAMPLE 1: Basic Market Analysis")
    print("="*70)

    # Initialize intelligence
    intelligence = LangChainIntelligence()

    # Analyze market (agent will automatically use tools)
    result = intelligence.analyze_market(
        symbol="SPY",
        user_query="What's the current Market Maker state and what should I be trading?"
    )

    if result["success"]:
        print("\n📊 MARKET ANALYSIS:")
        print(result["analysis"])
    else:
        print(f"\n❌ Error: {result['error']}")


def example_2_structured_recommendation():
    """
    Example 2: Get structured trade recommendation with Pydantic validation
    """
    print("\n" + "="*70)
    print("EXAMPLE 2: Structured Trade Recommendation")
    print("="*70)

    intelligence = LangChainIntelligence()

    # Get structured recommendation
    rec = intelligence.get_structured_recommendation(
        symbol="SPY",
        account_size=10000,
        current_price=565.50
    )

    if rec:
        print("\n✅ TRADE RECOMMENDATION (VALIDATED):")
        print(f"   Symbol: {rec.symbol}")
        print(f"   Strategy: {rec.strategy_type.value}")
        print(f"   MM State: {rec.market_maker_state.value}")
        print(f"   Confidence: {rec.confidence:.1%}")
        print(f"   Win Probability: {rec.win_probability:.1%}")
        print(f"\n   POSITION:")
        for i, leg in enumerate(rec.legs, 1):
            print(f"   Leg {i}: {leg.action} {leg.quantity} {leg.option_type.value.upper()} @ ${leg.strike} exp {leg.expiration}")
        print(f"\n   PRICING:")
        print(f"   Max Entry: ${rec.max_entry_price:.2f}")
        print(f"   Target: ${rec.target_price:.2f}")
        print(f"   Stop: ${rec.stop_loss:.2f}")
        print(f"\n   SIZING:")
        print(f"   Contracts: {rec.recommended_contracts}")
        print(f"   Max Risk: ${rec.max_risk_dollars:.2f}")
        print(f"   Account %: {rec.account_allocation_pct:.1f}%")
        print(f"\n   RISK METRICS:")
        print(f"   R:R Ratio: {rec.risk_reward_ratio:.1f}:1")
        print(f"   Max Loss: {rec.max_loss_pct:.0f}%")
        print(f"\n   EDGE:")
        print(f"   {rec.edge_description}")
        print(f"\n   KEY LEVELS:")
        for level, price in rec.key_levels.items():
            print(f"   {level.title()}: ${price}")
        print(f"\n   TIMING:")
        print(f"   Entry: {rec.entry_timing}")
        print(f"   Exit: {rec.exit_timing}")
        print(f"   Hold: {rec.hold_duration_days} days")

        if rec.warnings:
            print(f"\n   ⚠️  WARNINGS:")
            for warning in rec.warnings:
                print(f"   - {warning}")
    else:
        print("\n❌ No valid recommendation at this time")


def example_3_individual_tools():
    """
    Example 3: Using individual tools directly
    """
    print("\n" + "="*70)
    print("EXAMPLE 3: Using Individual Tools")
    print("="*70)

    # Tool 1: Get GEX data
    print("\n📈 GEX DATA:")
    gex = get_gex_data("SPY")
    if "error" not in gex:
        print(f"   Net GEX: ${gex['net_gex']:.2f}B")
        print(f"   Flip Point: ${gex['flip_point']:.2f}")
        print(f"   Call Wall: ${gex['call_wall']:.2f} (${gex['call_wall_strength']:.2f}B)")
        print(f"   Put Wall: ${gex['put_wall']:.2f} (${gex['put_wall_strength']:.2f}B)")
        print(f"   Positioning: {gex['dealer_positioning']}")
    else:
        print(f"   Error: {gex['error']}")

    # Tool 2: Analyze GEX regime
    print("\n🎯 GEX REGIME ANALYSIS:")
    regime = analyze_gex_regime("SPY", 565.50)
    if "error" not in regime:
        print(f"   MM State: {regime['market_maker_state']}")
        print(f"   Confidence: {regime['confidence']:.0%}")
        print(f"   Distance to Flip: {regime['distance_to_flip_pct']:.2f}%")
        print(f"   Volatility Risk: {regime['volatility_risk']}")
        print(f"\n   Implication:")
        print(f"   {regime['trading_implication']}")
        print(f"\n   Expected Behavior:")
        print(f"   {regime['expected_behavior']}")
    else:
        print(f"   Error: {regime['error']}")

    # Tool 3: Volatility regime
    print("\n📊 VOLATILITY REGIME:")
    vol_regime = get_volatility_regime()
    if "error" not in vol_regime:
        print(f"   VIX: {vol_regime['vix_level']:.2f}")
        print(f"   Regime: {vol_regime['volatility_regime']}")
        print(f"   Implication: {vol_regime['trading_implication']}")
        print(f"   Risk: {vol_regime['risk_warning']}")
    else:
        print(f"   Error: {vol_regime['error']}")

    # Tool 4: Position sizing
    print("\n💰 POSITION SIZING (Kelly Criterion):")
    sizing = calculate_position_size(
        account_size=10000,
        win_rate=0.68,
        risk_reward_ratio=3.0,
        max_risk_pct=5.0,
        kelly_fraction="half"
    )
    if "error" not in sizing:
        print(f"   Account Size: ${sizing['account_size']:,.2f}")
        print(f"   Kelly Fraction: {sizing['kelly_fraction'].title()}")
        print(f"   Recommended: ${sizing['recommended_position_dollars']:,.2f} ({sizing['recommended_position_pct']:.1f}%)")
        print(f"   Max Risk: ${sizing['max_risk_dollars']:,.2f} ({sizing['max_risk_pct']:.1f}%)")
        print(f"   Risk of Ruin: {sizing['risk_of_ruin']:.2%}")
        print(f"   Expected Growth: {sizing['expected_growth_rate']:.2%}/trade")
    else:
        print(f"   Error: {sizing['error']}")


def example_4_trade_validation():
    """
    Example 4: Validate trade with risk management agent
    """
    print("\n" + "="*70)
    print("EXAMPLE 4: Trade Validation")
    print("="*70)

    intelligence = LangChainIntelligence()

    # Trade to validate
    trade_details = {
        "symbol": "SPY",
        "strategy": "NEGATIVE_GEX_SQUEEZE",
        "contracts": 3,
        "entry_price": 3.50,
        "stop_loss": 2.45,
        "position_size_dollars": 1050,  # 3 * $3.50 * 100
        "max_loss_dollars": 315,  # 3 * ($3.50 - $2.45) * 100
        "proposed_delta": 0.40
    }

    print("\n📝 TRADE TO VALIDATE:")
    for key, value in trade_details.items():
        print(f"   {key}: {value}")

    # Validate
    validation = intelligence.validate_trade(
        trade_details=trade_details,
        account_size=10000,
        current_portfolio_delta=0.15
    )

    if validation["success"]:
        print("\n✅ VALIDATION RESULT:")
        print(validation["validation"])
    else:
        print(f"\n❌ Validation Error: {validation['error']}")


def example_5_conversation_memory():
    """
    Example 5: Conversation memory management
    """
    print("\n" + "="*70)
    print("EXAMPLE 5: Conversation Memory")
    print("="*70)

    intelligence = LangChainIntelligence()

    # First query
    print("\n🗣️  Query 1: Analyzing SPY...")
    result1 = intelligence.analyze_market("SPY")

    # Second query (with context from first)
    print("\n🗣️  Query 2: Follow-up question...")
    result2 = intelligence.analyze_market(
        "SPY",
        user_query="Based on what you just told me, should I buy calls or puts?"
    )

    # Get conversation history
    history = intelligence.get_conversation_history()
    print(f"\n📚 CONVERSATION HISTORY: {len(history)} messages")

    # Save conversation
    filename = f"conversation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    intelligence.save_conversation(filename)
    print(f"\n💾 Saved conversation to: {filename}")

    # Clear memory
    intelligence.clear_memory()
    print("🧹 Memory cleared")

    # Load conversation
    intelligence.load_conversation(filename)
    print(f"📂 Loaded conversation from: {filename}")

    history_after = intelligence.get_conversation_history()
    print(f"📚 History after reload: {len(history_after)} messages")


def example_6_quick_functions():
    """
    Example 6: Using quick convenience functions
    """
    print("\n" + "="*70)
    print("EXAMPLE 6: Quick Convenience Functions")
    print("="*70)

    # Quick market analysis
    print("\n⚡ Quick Market Analysis:")
    analysis = get_quick_market_analysis("SPY")
    print(analysis)

    # Quick recommendation
    print("\n⚡ Quick Trade Recommendation:")
    rec = get_trade_recommendation(
        symbol="SPY",
        account_size=10000,
        current_price=565.50
    )
    if rec:
        print(f"   Strategy: {rec.strategy_type.value}")
        print(f"   Confidence: {rec.confidence:.1%}")
        print(f"   Contracts: {rec.recommended_contracts}")
    else:
        print("   No recommendation available")


def example_7_error_handling():
    """
    Example 7: Proper error handling
    """
    print("\n" + "="*70)
    print("EXAMPLE 7: Error Handling")
    print("="*70)

    try:
        intelligence = LangChainIntelligence()

        # Attempt to get recommendation
        rec = intelligence.get_structured_recommendation(
            symbol="INVALID",
            account_size=10000,
            current_price=100.0
        )

        if rec:
            print(f"✅ Got recommendation for {rec.symbol}")
        else:
            print("⚠️  No recommendation returned (expected for invalid symbol)")

    except ValueError as e:
        print(f"❌ ValueError: {e}")
    except Exception as e:
        print(f"❌ Unexpected error: {type(e).__name__}: {e}")


def main():
    """
    Run all examples
    """
    print("\n" + "="*70)
    print("🚀 ALPHAGEX LANGCHAIN INTEGRATION EXAMPLES")
    print("="*70)
    print("\nThese examples demonstrate the new LangChain-powered intelligence system.")
    print("Make sure you have set your ANTHROPIC_API_KEY environment variable.")

    # Check API key
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("\n❌ ERROR: ANTHROPIC_API_KEY not set")
        print("Set it with: export ANTHROPIC_API_KEY='your_key_here'")
        return

    # Run examples
    examples = [
        ("Basic Market Analysis", example_1_basic_market_analysis),
        ("Structured Recommendation", example_2_structured_recommendation),
        ("Individual Tools", example_3_individual_tools),
        ("Trade Validation", example_4_trade_validation),
        ("Conversation Memory", example_5_conversation_memory),
        ("Quick Functions", example_6_quick_functions),
        ("Error Handling", example_7_error_handling)
    ]

    print("\n📋 Available examples:")
    for i, (name, _) in enumerate(examples, 1):
        print(f"   {i}. {name}")

    print("\n🎯 Running all examples...")

    for name, example_func in examples:
        try:
            example_func()
        except Exception as e:
            print(f"\n❌ Example '{name}' failed: {e}")
            import traceback
            traceback.print_exc()

    print("\n" + "="*70)
    print("✅ ALL EXAMPLES COMPLETED")
    print("="*70)
    print("\nNext steps:")
    print("1. Review LANGCHAIN_INTEGRATION_GUIDE.md for detailed documentation")
    print("2. Test with real market data")
    print("3. Integrate into your trading workflow")
    print("4. Set up LangSmith monitoring for production use")


if __name__ == "__main__":
    main()
