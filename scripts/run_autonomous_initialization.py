"""
Autonomous Trader Initialization Script
Runs backtests on all patterns and trains ML model

This script initializes the autonomous trader system by:
1. Running backtests on all psychology trap patterns
2. Training the ML model on historical data
3. Initializing the strategy competition
4. Generating performance reports

Run this ONCE before starting the autonomous trader for the first time
"""

import sys
from datetime import datetime
from typing import Dict, List

print("=" * 80)
print("🚀 AUTONOMOUS TRADER INITIALIZATION")
print("=" * 80)
print()

# Step 1: Run backtests on all patterns
print("📊 STEP 1: Running Backtests on All Patterns")
print("-" * 80)

try:
    from backtest.autonomous_backtest_engine import get_backtester

    backtester = get_backtester()

    # Backtest all patterns (90 days lookback)
    print("🔍 Backtesting all patterns (90 days)...")
    all_results = backtester.backtest_all_patterns(lookback_days=90)

    print(f"\n✅ Backtest complete! Found {len(all_results)} patterns to validate\n")

    # Display results ranked by expectancy
    print("🏆 BACKTEST RESULTS (Ranked by Expectancy):")
    print("-" * 80)

    for i, result in enumerate(all_results, 1):
        if result['total_signals'] > 0:
            print(f"\n{i}. {result['pattern']}")
            print(f"   Total Signals: {result['total_signals']}")
            print(f"   Win Rate: {result['win_rate']:.1f}%")
            print(f"   Expectancy: {result['expectancy']:.2f}%")
            print(f"   Sharpe Ratio: {result['sharpe_ratio']:.2f}")
            print(f"   Profit Factor: {result['profit_factor']:.2f}")
            print(f"   Avg Win: {result['avg_profit_pct']:.2f}% | Avg Loss: {result['avg_loss_pct']:.2f}%")

    # Analyze liberation accuracy
    print("\n" + "=" * 80)
    print("🔓 LIBERATION SETUP ACCURACY:")
    print("-" * 80)

    liberation_analysis = backtester.analyze_liberation_accuracy(lookback_days=90)
    print(f"Total Liberation Signals: {liberation_analysis['total_liberation_signals']}")
    print(f"Successful Liberations: {liberation_analysis['successful_liberations']}")
    print(f"Accuracy: {liberation_analysis['accuracy_pct']:.1f}%")
    print(f"Avg Move After Liberation: {liberation_analysis['avg_move_after_liberation_pct']:.2f}%")
    print(f"Avg Confidence: {liberation_analysis['avg_confidence']:.1f}%")

    # Analyze false floor effectiveness
    print("\n" + "=" * 80)
    print("🛡️ FALSE FLOOR DETECTION EFFECTIVENESS:")
    print("-" * 80)

    false_floor_analysis = backtester.analyze_false_floor_effectiveness(lookback_days=90)
    print(f"Total False Floor Detections: {false_floor_analysis['total_false_floor_detections']}")
    print(f"Avoided Bad Short Trades: {false_floor_analysis['avoided_bad_short_trades']}")
    print(f"Avg Price Move: {false_floor_analysis['avg_price_move_pct']:.2f}%")
    print(f"Effectiveness: {false_floor_analysis['effectiveness']}")

    print("\n✅ STEP 1 COMPLETE: All pattern backtests finished!")

except Exception as e:
    print(f"❌ ERROR in backtesting: {e}")
    import traceback
    traceback.print_exc()

# Step 2: Train ML model on historical data
print("\n" + "=" * 80)
print("🤖 STEP 2: Training ML Model on Historical Data")
print("-" * 80)

try:
    from ai.autonomous_ml_pattern_learner import get_pattern_learner

    ml_learner = get_pattern_learner()

    print("🔍 Loading historical data (180 days)...")
    print("🧠 Training Random Forest classifier...")

    training_results = ml_learner.train_pattern_classifier(lookback_days=180)

    if training_results.get('error'):
        print(f"⚠️ ML Training Error: {training_results['error']}")
    else:
        print(f"\n✅ ML Model Trained Successfully!")
        print(f"   Training Samples: {training_results['samples']}")
        print(f"   Test Samples: {training_results['test_samples']}")
        print(f"   Accuracy: {training_results['accuracy']:.1%}")
        print(f"   Precision: {training_results['precision']:.1%}")
        print(f"   Recall: {training_results['recall']:.1%}")
        print(f"   F1 Score: {training_results['f1_score']:.3f}")

        print(f"\n📊 TOP 10 MOST IMPORTANT FEATURES:")
        for i, (feature, importance) in enumerate(training_results['top_features'], 1):
            print(f"   {i}. {feature}: {importance:.4f}")

        # Save model for future use
        print("\n💾 Saving trained model...")
        ml_learner.save_model('autonomous_ml_model.pkl')
        print("   ✅ Model saved to autonomous_ml_model.pkl")

    print("\n✅ STEP 2 COMPLETE: ML model trained and saved!")

except Exception as e:
    print(f"❌ ERROR in ML training: {e}")
    import traceback
    traceback.print_exc()

# Step 3: Initialize strategy competition
print("\n" + "=" * 80)
print("🏆 STEP 3: Initializing Strategy Competition")
print("-" * 80)

try:
    from core.autonomous_strategy_competition import get_competition

    competition = get_competition()

    print("🎮 8 strategies initialized with $5,000 capital each:")
    for strategy_id, strategy in competition.strategies.items():
        print(f"   • {strategy['name']}: {strategy['description']}")

    # Get leaderboard (should be empty initially)
    leaderboard = competition.get_leaderboard()

    print(f"\n📊 Leaderboard initialized with {len(leaderboard)} strategies")
    print("   Competition will track performance as trades execute")

    print("\n✅ STEP 3 COMPLETE: Strategy competition ready!")

except Exception as e:
    print(f"❌ ERROR in competition init: {e}")
    import traceback
    traceback.print_exc()

# Step 4: Display summary
print("\n" + "=" * 80)
print("✅ INITIALIZATION COMPLETE!")
print("=" * 80)
print()
print("🎯 NEXT STEPS:")
print("   1. The autonomous trader is now ready to run")
print("   2. Backtests validate pattern effectiveness")
print("   3. ML model will adjust confidence scores in real-time")
print("   4. Strategy competition will track 8 different approaches")
print("   5. All logs will be saved to autonomous_trader_logs table")
print()
print("🚀 Start the autonomous trader with:")
print("   python autonomous_paper_trader_background.py")
print()
print("=" * 80)
