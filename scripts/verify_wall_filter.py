#!/usr/bin/env python3
"""
Verify wall_filter_pct configuration and direction logic.

This script traces the full chain to ensure:
1. Config value is set correctly in database
2. Config is loaded correctly by bots
3. Direction logic uses the correct threshold

Run with: python scripts/verify_wall_filter.py
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / '.env')
except ImportError:
    pass

print("=" * 70)
print("WALL FILTER VERIFICATION")
print("=" * 70)

# ============================================================================
# 1. CHECK MODEL DEFAULTS
# ============================================================================
print("\n[1] MODEL DEFAULTS (in code)")
print("-" * 70)

try:
    from trading.solomon_v2.models import SolomonConfig
    solomon_default = SolomonConfig()
    print(f"  SOLOMON default wall_filter_pct: {solomon_default.wall_filter_pct}%")
except Exception as e:
    print(f"  SOLOMON: Error loading - {e}")

try:
    from trading.gideon.models import GideonConfig
    icarus_default = GideonConfig()
    print(f"  GIDEON default wall_filter_pct: {icarus_default.wall_filter_pct}%")
except Exception as e:
    print(f"  GIDEON: Error loading - {e}")

# ============================================================================
# 2. CHECK DATABASE CONFIG
# ============================================================================
print("\n[2] DATABASE CONFIG (actual values used in production)")
print("-" * 70)

try:
    from database_adapter import db_connection

    with db_connection() as conn:
        c = conn.cursor()

        # SOLOMON config
        c.execute("""
            SELECT config_key, config_value
            FROM autonomous_config
            WHERE bot_name = 'SOLOMON' AND config_key = 'wall_filter_pct'
        """)
        result = c.fetchone()
        if result:
            print(f"  SOLOMON database wall_filter_pct: {result[1]}%")
        else:
            print(f"  SOLOMON database wall_filter_pct: NOT SET (will use default {solomon_default.wall_filter_pct}%)")

        # GIDEON config
        c.execute("""
            SELECT config_key, config_value
            FROM autonomous_config
            WHERE bot_name = 'GIDEON' AND config_key = 'wall_filter_pct'
        """)
        result = c.fetchone()
        if result:
            print(f"  GIDEON database wall_filter_pct: {result[1]}%")
        else:
            print(f"  GIDEON database wall_filter_pct: NOT SET (will use default)")

except Exception as e:
    print(f"  Database error: {e}")
    print("  (Run this on production to see actual values)")

# ============================================================================
# 3. CHECK PROPHET DEFAULT
# ============================================================================
print("\n[3] PROPHET ADVISOR DEFAULT")
print("-" * 70)

try:
    from quant.prophet_advisor import ProphetAdvisor
    import inspect

    # Get the default from the function signature
    sig = inspect.signature(ProphetAdvisor.get_solomon_advice)
    for param_name, param in sig.parameters.items():
        if param_name == 'wall_filter_pct':
            print(f"  Prophet get_solomon_advice default: {param.default}%")
            break
except Exception as e:
    print(f"  Prophet error: {e}")

# ============================================================================
# 4. TEST DIRECTION LOGIC
# ============================================================================
print("\n[4] DIRECTION LOGIC TEST")
print("-" * 70)

try:
    from quant.price_trend_tracker import PriceTrendTracker
    from unittest.mock import MagicMock

    tracker = PriceTrendTracker.get_instance()

    # Create mock wall position for "near put wall" scenario
    mock_wall = MagicMock()
    mock_wall.dist_to_put_wall_pct = 0.8  # 0.8% from put wall
    mock_wall.dist_to_call_wall_pct = 4.2  # 4.2% from call wall
    mock_wall.position_in_range_pct = 16
    mock_wall.nearest_wall = "PUT_WALL"
    mock_wall.nearest_wall_distance_pct = 0.8

    # Create mock bearish trend (the bug scenario)
    mock_trend = MagicMock()
    mock_trend.derived_direction = "BEARISH"
    mock_trend.derived_confidence = 0.65
    mock_trend.reasoning = "Price falling with momentum"
    from quant.price_trend_tracker import TrendDirection
    mock_trend.direction = TrendDirection.DOWNTREND

    # Patch the methods
    original_analyze_trend = tracker.analyze_trend
    original_analyze_wall_position = tracker.analyze_wall_position
    tracker.analyze_trend = lambda x: mock_trend
    tracker.analyze_wall_position = lambda *args: mock_wall

    print("  Scenario: Price 0.8% from PUT wall, trend is BEARISH")
    print()

    # Test with different wall_filter_pct values
    for threshold in [1.0, 3.0, 5.0]:
        direction, confidence, reasoning, wall_passed = tracker.get_neutral_regime_direction(
            symbol="SPY",
            spot_price=588.0,
            call_wall=598.0,
            put_wall=583.0,
            wall_filter_pct=threshold
        )

        status = "✅" if direction == "BULLISH" else "❌"
        print(f"  wall_filter_pct={threshold}%: direction={direction} {status}, wall_passed={wall_passed}")

    # Restore original methods
    tracker.analyze_trend = original_analyze_trend
    tracker.analyze_wall_position = original_analyze_wall_position

except Exception as e:
    print(f"  Error: {e}")
    import traceback
    traceback.print_exc()

# ============================================================================
# 5. APACHE COMPARISON
# ============================================================================
print("\n[5] APACHE BACKTEST PARAMETERS (for reference)")
print("-" * 70)
print("  wall_filter_pct: 1.0%  (traded ~8x/week, 58% win rate)")
print()
print("  RECOMMENDATION:")
print("  - If wall_filter_pct > 3%, consider tightening to 1-2%")
print("  - Wider threshold = more trades but less reliable direction")

print("\n" + "=" * 70)
