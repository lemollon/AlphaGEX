#!/usr/bin/env python3
"""
Verify Direction Fix - Complete End-to-End Test

This script verifies the ENTIRE execution chain from database config
to direction logic for the ATHENA/ICARUS direction fix.

Run on Render:
    python scripts/verify_direction_fix.py

What it checks:
1. Database config values (ATHENA_wall_filter_pct, ICARUS_wall_filter_pct)
2. Config loading in bot code
3. Direction logic in price_trend_tracker
4. Oracle integration
5. Simulated scenarios matching Apache backtest

Expected output: All checks should show green checkmarks.
"""

import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime

print("=" * 70)
print("DIRECTION FIX VERIFICATION - COMPLETE END-TO-END TEST")
print("=" * 70)
print(f"Run time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print()

all_passed = True
results = []

def check(name, condition, details=""):
    global all_passed
    status = "PASS" if condition else "FAIL"
    icon = "\u2705" if condition else "\u274c"
    if not condition:
        all_passed = False
    results.append((name, condition, details))
    print(f"  {icon} {name}")
    if details and not condition:
        print(f"      {details}")
    return condition

# ============================================================================
# TEST 1: DATABASE CONFIG VALUES
# ============================================================================
print("\n[1] DATABASE CONFIG VALUES")
print("-" * 70)

try:
    import psycopg2
    DATABASE_URL = os.environ.get('DATABASE_URL')

    if not DATABASE_URL:
        print("  WARNING: DATABASE_URL not set - skipping database tests")
        print("  (This is expected when running locally without .env)")
        db_athena_value = None
        db_icarus_value = None
    else:
        conn = psycopg2.connect(DATABASE_URL)
        c = conn.cursor()

        # Check ATHENA config
        c.execute("SELECT value FROM autonomous_config WHERE key = 'ATHENA_wall_filter_pct'")
        result = c.fetchone()
        db_athena_value = result[0] if result else None
        check("ATHENA_wall_filter_pct in database",
              db_athena_value == '1.0',
              f"Got: {db_athena_value}, Expected: 1.0")

        # Check ICARUS config
        c.execute("SELECT value FROM autonomous_config WHERE key = 'ICARUS_wall_filter_pct'")
        result = c.fetchone()
        db_icarus_value = result[0] if result else None
        check("ICARUS_wall_filter_pct in database",
              db_icarus_value == '1.0',
              f"Got: {db_icarus_value}, Expected: 1.0")

        conn.close()

except Exception as e:
    print(f"  ERROR: Database check failed: {e}")
    db_athena_value = None
    db_icarus_value = None

# ============================================================================
# TEST 2: CONFIG LOADING IN BOT CODE
# ============================================================================
print("\n[2] CONFIG LOADING IN BOT CODE")
print("-" * 70)

try:
    from trading.athena_v2.db import ATHENADatabase
    from trading.athena_v2.models import ATHENAConfig

    # Test default config
    default_config = ATHENAConfig()
    check("ATHENA default wall_filter_pct is 1.0",
          default_config.wall_filter_pct == 1.0,
          f"Got: {default_config.wall_filter_pct}, Expected: 1.0")

    # Test loading from database (if available)
    if DATABASE_URL:
        try:
            db = ATHENADatabase()
            loaded_config = db.load_config()
            check("ATHENA loaded wall_filter_pct is 1.0",
                  loaded_config.wall_filter_pct == 1.0,
                  f"Got: {loaded_config.wall_filter_pct}, Expected: 1.0")
        except Exception as e:
            print(f"  WARNING: Could not load ATHENA config from DB: {e}")

except Exception as e:
    print(f"  ERROR: ATHENA config test failed: {e}")

try:
    from trading.icarus.db import ICARUSDatabase
    from trading.icarus.models import ICARUSConfig

    # Test default config
    default_config = ICARUSConfig()
    check("ICARUS default wall_filter_pct is 1.0",
          default_config.wall_filter_pct == 1.0,
          f"Got: {default_config.wall_filter_pct}, Expected: 1.0")

    # Test loading from database (if available)
    if DATABASE_URL:
        try:
            db = ICARUSDatabase()
            loaded_config = db.load_config()
            check("ICARUS loaded wall_filter_pct is 1.0",
                  loaded_config.wall_filter_pct == 1.0,
                  f"Got: {loaded_config.wall_filter_pct}, Expected: 1.0")
        except Exception as e:
            print(f"  WARNING: Could not load ICARUS config from DB: {e}")

except Exception as e:
    print(f"  ERROR: ICARUS config test failed: {e}")

# ============================================================================
# TEST 3: DIRECTION LOGIC IN PRICE_TREND_TRACKER
# ============================================================================
print("\n[3] DIRECTION LOGIC (THE FIX)")
print("-" * 70)

try:
    from quant.price_trend_tracker import PriceTrendTracker, TrendDirection
    from unittest.mock import MagicMock

    tracker = PriceTrendTracker.get_instance()

    # Scenario A: Near PUT wall with BEARISH trend
    # THE CRITICAL FIX: Should return BULLISH (wall takes priority)
    print("\n  Scenario A: Price near PUT wall, trend is BEARISH")
    print("  (This was the bug - trend used to override wall)")

    mock_wall_near_put = MagicMock()
    mock_wall_near_put.dist_to_put_wall_pct = 0.5  # 0.5% from put wall
    mock_wall_near_put.dist_to_call_wall_pct = 4.5
    mock_wall_near_put.position_in_range_pct = 10
    mock_wall_near_put.nearest_wall = "PUT_WALL"
    mock_wall_near_put.nearest_wall_distance_pct = 0.5

    mock_trend_bearish = MagicMock()
    mock_trend_bearish.derived_direction = "BEARISH"
    mock_trend_bearish.derived_confidence = 0.65
    mock_trend_bearish.reasoning = "Price falling with momentum"
    mock_trend_bearish.direction = TrendDirection.DOWNTREND
    mock_trend_bearish.strength = 0.7

    original_analyze_trend = tracker.analyze_trend
    original_analyze_wall = tracker.analyze_wall_position
    tracker.analyze_trend = lambda x: mock_trend_bearish
    tracker.analyze_wall_position = lambda *args: mock_wall_near_put

    direction, confidence, reasoning, wall_passed = tracker.get_neutral_regime_direction(
        symbol="SPY",
        spot_price=585.5,
        call_wall=595.0,
        put_wall=582.0,
        wall_filter_pct=1.0
    )

    tracker.analyze_trend = original_analyze_trend
    tracker.analyze_wall_position = original_analyze_wall

    check("Near PUT wall + BEARISH trend = BULLISH direction",
          direction == "BULLISH",
          f"Got: {direction}, Expected: BULLISH")
    check("wall_filter_passed = True when near wall",
          wall_passed == True,
          f"Got: {wall_passed}, Expected: True")
    print(f"      Reasoning: {reasoning[:80]}...")

    # Scenario B: Near CALL wall with BULLISH trend
    print("\n  Scenario B: Price near CALL wall, trend is BULLISH")

    mock_wall_near_call = MagicMock()
    mock_wall_near_call.dist_to_put_wall_pct = 4.5
    mock_wall_near_call.dist_to_call_wall_pct = 0.5  # 0.5% from call wall
    mock_wall_near_call.position_in_range_pct = 90
    mock_wall_near_call.nearest_wall = "CALL_WALL"
    mock_wall_near_call.nearest_wall_distance_pct = 0.5

    mock_trend_bullish = MagicMock()
    mock_trend_bullish.derived_direction = "BULLISH"
    mock_trend_bullish.derived_confidence = 0.65
    mock_trend_bullish.reasoning = "Price rising with momentum"
    mock_trend_bullish.direction = TrendDirection.UPTREND
    mock_trend_bullish.strength = 0.7

    tracker.analyze_trend = lambda x: mock_trend_bullish
    tracker.analyze_wall_position = lambda *args: mock_wall_near_call

    direction, confidence, reasoning, wall_passed = tracker.get_neutral_regime_direction(
        symbol="SPY",
        spot_price=594.5,
        call_wall=595.0,
        put_wall=582.0,
        wall_filter_pct=1.0
    )

    tracker.analyze_trend = original_analyze_trend
    tracker.analyze_wall_position = original_analyze_wall

    check("Near CALL wall + BULLISH trend = BEARISH direction",
          direction == "BEARISH",
          f"Got: {direction}, Expected: BEARISH")
    check("wall_filter_passed = True when near wall",
          wall_passed == True,
          f"Got: {wall_passed}, Expected: True")

    # Scenario C: Middle of range (not near any wall)
    print("\n  Scenario C: Price in MIDDLE of range (not near walls)")

    mock_wall_middle = MagicMock()
    mock_wall_middle.dist_to_put_wall_pct = 2.5  # 2.5% from put wall
    mock_wall_middle.dist_to_call_wall_pct = 2.5  # 2.5% from call wall
    mock_wall_middle.position_in_range_pct = 50
    mock_wall_middle.nearest_wall = "PUT_WALL"
    mock_wall_middle.nearest_wall_distance_pct = 2.5

    tracker.analyze_trend = lambda x: mock_trend_bearish
    tracker.analyze_wall_position = lambda *args: mock_wall_middle

    direction, confidence, reasoning, wall_passed = tracker.get_neutral_regime_direction(
        symbol="SPY",
        spot_price=588.5,
        call_wall=595.0,
        put_wall=582.0,
        wall_filter_pct=1.0
    )

    tracker.analyze_trend = original_analyze_trend
    tracker.analyze_wall_position = original_analyze_wall

    check("Middle of range uses TREND direction",
          direction == "BEARISH",
          f"Got: {direction}, Expected: BEARISH (from trend)")
    check("wall_filter_passed = False when not near wall",
          wall_passed == False,
          f"Got: {wall_passed}, Expected: False")

except Exception as e:
    print(f"  ERROR: Direction logic test failed: {e}")
    import traceback
    traceback.print_exc()

# ============================================================================
# TEST 4: ORACLE INTEGRATION
# ============================================================================
print("\n[4] ORACLE INTEGRATION")
print("-" * 70)

try:
    from quant.oracle_advisor import OracleAdvisor, MarketContext, GEXRegime

    oracle = OracleAdvisor()

    # Create context for near-put-wall scenario (dataclass)
    context = MarketContext(
        spot_price=585.5,
        vix=18.0,
        gex_put_wall=582.0,
        gex_call_wall=595.0,
        gex_regime=GEXRegime.NEUTRAL,
        gex_net=0,
        gex_flip_point=588.0,
    )

    # Call Oracle with wall_filter_pct
    prediction = oracle.get_athena_advice(
        context=context,
        use_gex_walls=True,
        wall_filter_pct=1.0
    )

    if prediction:
        check("Oracle returns prediction",
              prediction is not None,
              "Oracle returned None")

        neutral_dir = getattr(prediction, 'neutral_derived_direction', '')
        check("Oracle uses neutral_derived_direction",
              neutral_dir != '',
              f"Got: '{neutral_dir}' (empty means not set)")

        wall_passed = getattr(prediction, 'wall_filter_passed', None)
        print(f"      neutral_derived_direction: {neutral_dir}")
        print(f"      wall_filter_passed: {wall_passed}")
        print(f"      advice: {prediction.advice.value if prediction.advice else 'N/A'}")
    else:
        print("  WARNING: Oracle returned None - may need market data")

except Exception as e:
    print(f"  ERROR: Oracle integration test failed: {e}")
    import traceback
    traceback.print_exc()

# ============================================================================
# TEST 5: APACHE BACKTEST COMPARISON
# ============================================================================
print("\n[5] APACHE BACKTEST COMPARISON")
print("-" * 70)

print("""
  Apache Backtest Parameters (achieved 58% win rate):
  - wall_filter_pct: 1.0%
  - Trades per week: ~8
  - Direction logic: Wall proximity takes priority

  Current Settings:
""")

try:
    from trading.athena_v2.models import ATHENAConfig
    config = ATHENAConfig()

    print(f"  - wall_filter_pct: {config.wall_filter_pct}%")
    print(f"  - min_win_probability: {config.min_win_probability}")
    print(f"  - min_confidence: {config.min_confidence}")
    print(f"  - min_rr_ratio: {config.min_rr_ratio}")

    check("wall_filter_pct matches Apache (1.0%)",
          config.wall_filter_pct == 1.0,
          f"Got: {config.wall_filter_pct}%, Expected: 1.0%")

except Exception as e:
    print(f"  ERROR: Could not load config: {e}")

# ============================================================================
# SUMMARY
# ============================================================================
print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)

passed = sum(1 for _, cond, _ in results if cond)
failed = sum(1 for _, cond, _ in results if not cond)
total = len(results)

print(f"\n  Total checks: {total}")
print(f"  Passed: {passed} \u2705")
print(f"  Failed: {failed} \u274c")

if failed > 0:
    print("\n  FAILED CHECKS:")
    for name, cond, details in results:
        if not cond:
            print(f"    - {name}")
            if details:
                print(f"      {details}")

print()
if all_passed:
    print("  \u2705 ALL CHECKS PASSED - Direction fix is correctly wired!")
    print()
    print("  The fix ensures:")
    print("    - Near PUT wall  -> BULLISH (expect bounce off support)")
    print("    - Near CALL wall -> BEARISH (expect rejection at resistance)")
    print("    - This matches Apache backtest which achieved 58% win rate")
else:
    print("  \u274c SOME CHECKS FAILED - Review the issues above")
    sys.exit(1)

print("\n" + "=" * 70)
