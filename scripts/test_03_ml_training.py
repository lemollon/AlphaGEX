#!/usr/bin/env python3
"""
TEST 03: ML Training Pipeline
Tests ML feature extraction and model training.

Run: python scripts/test_03_ml_training.py
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta
import json

print("\n" + "="*60)
print(" TEST 03: ML TRAINING PIPELINE")
print("="*60)

# =============================================================================
# 1. Import ML Components
# =============================================================================
print("\n--- Importing ML Components ---")

ml_imports_ok = True

try:
    from data.polygon_data_fetcher import get_ml_features_for_trade
    print("  get_ml_features_for_trade imported")
except ImportError as e:
    print(f"  Could not import get_ml_features_for_trade: {e}")
    ml_imports_ok = False

try:
    from ai.autonomous_ml_pattern_learner import PatternLearner
    SPXPatternLearner = PatternLearner  # Alias for compatibility
    print("  PatternLearner imported from ai.autonomous_ml_pattern_learner")
except ImportError:
    try:
        from autonomous_ml_pattern_learner import PatternLearner
        SPXPatternLearner = PatternLearner
        print("  PatternLearner imported (alternate path)")
    except ImportError as e:
        print(f"  Could not import PatternLearner: {e}")
        SPXPatternLearner = None
        ml_imports_ok = False

if not ml_imports_ok:
    print("\n  Some ML imports failed, continuing with available components...")

# =============================================================================
# 2. Test ML Feature Extraction
# =============================================================================
print("\n--- ML Feature Extraction ---")

try:
    # Test feature extraction for a sample trade
    test_date = (datetime.now() - timedelta(days=14)).strftime('%Y-%m-%d')

    features = get_ml_features_for_trade(
        trade_date=test_date,
        strike=580.0,
        underlying_price=600.0,
        option_iv=0.16
    )

    print(f"  Trade date: {features.get('trade_date')}")
    print(f"\n  Market Features:")
    print(f"    VIX: {features.get('vix')}")
    print(f"    IV Rank: {features.get('iv_rank')}")
    print(f"    VIX Percentile: {features.get('vix_percentile')}")

    print(f"\n  SPX Returns:")
    print(f"    5-day: {features.get('spx_5d_return')}%")
    print(f"    20-day: {features.get('spx_20d_return')}%")
    print(f"    Distance from high: {features.get('distance_from_high')}%")

    print(f"\n  GEX Data:")
    print(f"    Net GEX: {features.get('net_gex')}")
    print(f"    Put Wall: {features.get('put_wall')}")
    print(f"    Call Wall: {features.get('call_wall')}")
    print(f"    Put Wall Distance: {features.get('put_wall_distance_pct')}%")

    print(f"\n  Trade-Specific:")
    print(f"    Moneyness: {features.get('moneyness')}")
    print(f"    Strike distance: {features.get('strike_distance_pct')}%")

    print(f"\n  Data Quality: {features.get('data_quality_pct', 0):.1f}%")

    # Show data sources
    print("\n  Data Sources:")
    for source, status in features.get('data_sources', {}).items():
        icon = "OK" if status in ['POLYGON', 'CALCULATED', 'TRADING_VOLATILITY', 'VIX_PROXY'] else "??"
        print(f"    [{icon}] {source}: {status}")

except Exception as e:
    print(f"  Error: {e}")
    import traceback
    traceback.print_exc()

# =============================================================================
# 3. Generate Training Data from Backtest
# =============================================================================
print("\n--- Generating Training Data from Backtest ---")

try:
    from backtest.spx_premium_backtest import SPXPremiumBacktester

    end_date = datetime.now() - timedelta(days=7)
    start_date = end_date - timedelta(days=60)  # 2 months

    print(f"  Running backtest: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")

    # SPXPremiumBacktester takes dates in constructor, uses run() method
    backtest = SPXPremiumBacktester(
        start_date=start_date.strftime('%Y-%m-%d'),
        end_date=end_date.strftime('%Y-%m-%d'),
        initial_capital=100000000  # $100M
    )

    results = backtest.run(save_to_db=False)

    trades = results.get('all_trades', results.get('trades', []))
    print(f"  Trades from backtest: {len(trades)}")

    if trades:
        # Enrich trades with ML features
        print("\n  Enriching trades with ML features...")
        enriched_count = 0
        sample_enriched = None

        for i, trade in enumerate(trades[:5]):  # Process first 5 for demo
            try:
                entry_date = trade.get('entry_date', '')
                strike = trade.get('strike', 0)
                premium = trade.get('premium', 0)

                # Estimate underlying price from strike (CSP typically 3-5% OTM)
                underlying_price = strike / 0.96

                features = get_ml_features_for_trade(
                    trade_date=entry_date,
                    strike=strike,
                    underlying_price=underlying_price,
                    option_iv=0.16
                )

                # Merge features into trade
                enriched_trade = {**trade, **features}
                enriched_count += 1

                if sample_enriched is None:
                    sample_enriched = enriched_trade

            except Exception as e:
                print(f"    Error enriching trade {i}: {e}")

        print(f"  Enriched {enriched_count} trades")

        if sample_enriched:
            print("\n  Sample enriched trade:")
            for key in ['entry_date', 'strike', 'pnl', 'vix', 'iv_rank', 'net_gex', 'spx_5d_return']:
                if key in sample_enriched:
                    val = sample_enriched[key]
                    if isinstance(val, float):
                        print(f"    {key}: {val:.2f}")
                    else:
                        print(f"    {key}: {val}")

except Exception as e:
    print(f"  Error: {e}")
    import traceback
    traceback.print_exc()

# =============================================================================
# 4. Test Pattern Learner Initialization
# =============================================================================
print("\n--- Pattern Learner Initialization ---")

learner = None
try:
    if SPXPatternLearner is not None:
        learner = SPXPatternLearner()
        print(f"  PatternLearner initialized")

        # Check what methods are available
        methods = [m for m in dir(learner) if not m.startswith('_')]
        print(f"  Available methods: {', '.join(methods[:10])}...")

        # Check if model exists
        if hasattr(learner, 'model'):
            print(f"  Model attribute exists: {type(learner.model)}")
        else:
            print(f"  No model attribute (needs training)")
    else:
        print("  PatternLearner not available (import failed)")

except Exception as e:
    print(f"  Error: {e}")

# =============================================================================
# 5. Test Training Pipeline
# =============================================================================
print("\n--- Training Pipeline Test ---")

try:
    # Check if learner has train method
    if hasattr(learner, 'train') or hasattr(learner, 'fit'):
        print("  Training method available")

        # Create sample training data
        sample_data = []
        for i in range(10):
            sample_data.append({
                'vix': 15 + i,
                'iv_rank': 30 + i * 2,
                'spx_5d_return': -2 + i * 0.5,
                'net_gex': 1000000 + i * 100000,
                'outcome': 'win' if i % 2 == 0 else 'loss',
                'pnl': 500 if i % 2 == 0 else -200
            })

        print(f"  Sample training data: {len(sample_data)} records")

        # Try to train (may need specific format)
        if hasattr(learner, 'add_trade_result'):
            for trade in sample_data:
                learner.add_trade_result(trade)
            print("  Added trade results to learner")

        if hasattr(learner, 'train'):
            try:
                learner.train()
                print("  Training completed")
            except Exception as e:
                print(f"  Training failed (may need more data): {e}")
    else:
        print("  No train/fit method found")

except Exception as e:
    print(f"  Error: {e}")

# =============================================================================
# 6. Test Model Persistence
# =============================================================================
print("\n--- Model Persistence ---")

try:
    import os

    # Check for saved models
    model_paths = [
        'models/',
        'ml/models/',
        'data/models/',
        './'
    ]

    for path in model_paths:
        if os.path.exists(path):
            files = os.listdir(path)
            model_files = [f for f in files if f.endswith(('.pkl', '.joblib', '.h5', '.pt'))]
            if model_files:
                print(f"  Found models in {path}:")
                for f in model_files:
                    print(f"    - {f}")

    # Check if learner can save/load
    if hasattr(learner, 'save_model'):
        print("  save_model method available")
    if hasattr(learner, 'load_model'):
        print("  load_model method available")

except Exception as e:
    print(f"  Error: {e}")

# =============================================================================
# 7. Feature Importance Check
# =============================================================================
print("\n--- Feature Importance ---")

try:
    # List of ML features we track
    ml_features = [
        'vix', 'iv_rank', 'vix_percentile',
        'spx_5d_return', 'spx_20d_return', 'distance_from_high',
        'net_gex', 'put_wall_distance_pct', 'call_wall_distance_pct',
        'moneyness', 'strike_distance_pct'
    ]

    print("  Features used for ML:")
    for i, feature in enumerate(ml_features, 1):
        print(f"    {i}. {feature}")

    # Check if learner has feature importance
    if hasattr(learner, 'feature_importance'):
        importance = learner.feature_importance
        print("\n  Feature Importance (from model):")
        for feat, imp in sorted(importance.items(), key=lambda x: -x[1])[:5]:
            print(f"    {feat}: {imp:.3f}")

except Exception as e:
    print(f"  Error: {e}")

# =============================================================================
# Summary
# =============================================================================
print("\n" + "="*60)
print(" ML TRAINING PIPELINE TEST COMPLETE")
print("="*60 + "\n")
