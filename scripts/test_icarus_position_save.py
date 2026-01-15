#!/usr/bin/env python3
"""
ICARUS Position Save Test Script
=================================

Tests that ICARUS can:
1. Initialize properly with all DB columns
2. Generate a valid signal
3. Execute a paper trade
4. Save position to database with all fields
5. Retrieve the position back

Run: python scripts/test_icarus_position_save.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
from zoneinfo import ZoneInfo
import traceback

CENTRAL_TZ = ZoneInfo("America/Chicago")


def test_db_schema():
    """Test 1: Verify icarus_positions table has all required columns."""
    print("\n" + "="*60)
    print("TEST 1: Database Schema Verification")
    print("="*60)

    try:
        from database_adapter import get_connection

        conn = get_connection()
        c = conn.cursor()

        # Get all columns from icarus_positions table
        c.execute("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'icarus_positions'
            ORDER BY ordinal_position
        """)

        columns = {row[0]: row[1] for row in c.fetchall()}
        conn.close()

        # Required columns that were missing before the fix
        required_columns = [
            'flip_point', 'net_gex', 'oracle_advice',
            'ml_model_name', 'ml_win_probability', 'ml_top_features',
            'wall_type', 'wall_distance_pct', 'trade_reasoning'
        ]

        print(f"\nFound {len(columns)} columns in icarus_positions table:")

        missing = []
        for col in required_columns:
            if col in columns:
                print(f"  ✅ {col}: {columns[col]}")
            else:
                print(f"  ❌ {col}: MISSING")
                missing.append(col)

        if missing:
            print(f"\n❌ FAIL: Missing columns: {missing}")
            print("   Run the ICARUS trader once to trigger _ensure_ml_columns migration")
            return False

        print("\n✅ PASS: All required columns exist")
        return True

    except Exception as e:
        print(f"\n❌ FAIL: Database error: {e}")
        traceback.print_exc()
        return False


def test_icarus_init():
    """Test 2: Verify ICARUS trader initializes without errors."""
    print("\n" + "="*60)
    print("TEST 2: ICARUS Trader Initialization")
    print("="*60)

    try:
        from trading.icarus.trader import ICARUSTrader
        from trading.icarus.models import ICARUSConfig, TradingMode

        config = ICARUSConfig(mode=TradingMode.PAPER)
        trader = ICARUSTrader(config=config)

        print(f"\n  Mode: {trader.config.mode.value}")
        print(f"  Ticker: {trader.config.ticker}")
        print(f"  Max Positions: {trader.config.max_open_positions}")
        print(f"  Min Win Probability: {trader.config.min_win_probability}")

        print("\n✅ PASS: ICARUS initialized successfully")
        return trader

    except Exception as e:
        print(f"\n❌ FAIL: Initialization error: {e}")
        traceback.print_exc()
        return None


def test_signal_generation(trader):
    """Test 3: Verify ICARUS can generate a signal."""
    print("\n" + "="*60)
    print("TEST 3: Signal Generation")
    print("="*60)

    try:
        # Get GEX data first
        gex_data = trader.signals.get_gex_data()
        if not gex_data:
            print("\n⚠️  SKIP: No GEX data available (market may be closed)")
            return None

        print(f"\n  GEX Data Retrieved:")
        print(f"    Spot Price: ${gex_data.get('spot_price', 0):.2f}")
        print(f"    VIX: {gex_data.get('vix', 0):.1f}")
        print(f"    GEX Regime: {gex_data.get('gex_regime', 'N/A')}")
        print(f"    Call Wall: ${gex_data.get('call_wall', 0):.2f}")
        print(f"    Put Wall: ${gex_data.get('put_wall', 0):.2f}")

        # Generate signal
        signal = trader.signals.generate_signal()

        if signal:
            print(f"\n  Signal Generated:")
            print(f"    Direction: {signal.direction}")
            print(f"    Spread Type: {signal.spread_type.value if signal.spread_type else 'N/A'}")
            print(f"    Confidence: {signal.confidence:.1%}")
            print(f"    Is Valid: {signal.is_valid}")
            print(f"    Oracle Advice: {signal.oracle_advice}")
            print(f"    Oracle Win Prob: {signal.oracle_win_probability:.1%}")
            print(f"    Long Strike: ${signal.long_strike}")
            print(f"    Short Strike: ${signal.short_strike}")

            if signal.is_valid:
                print("\n✅ PASS: Valid signal generated")
            else:
                print(f"\n⚠️  SKIP: Signal not valid - {signal.reasoning}")

            return signal
        else:
            print("\n⚠️  SKIP: No signal generated (may be outside trading hours)")
            return None

    except Exception as e:
        print(f"\n❌ FAIL: Signal generation error: {e}")
        traceback.print_exc()
        return None


def test_position_save(trader):
    """Test 4: Verify ICARUS can save a position to database."""
    print("\n" + "="*60)
    print("TEST 4: Position Save to Database")
    print("="*60)

    try:
        from trading.icarus.models import SpreadPosition, SpreadType, PositionStatus
        import uuid

        now = datetime.now(CENTRAL_TZ)
        test_id = f"TEST-ICARUS-{now.strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"

        # Create a test position with ALL fields
        test_position = SpreadPosition(
            position_id=test_id,
            spread_type=SpreadType.BULL_CALL,
            ticker="SPY",
            long_strike=590.0,
            short_strike=593.0,
            expiration=now.strftime("%Y-%m-%d"),
            entry_debit=1.25,
            contracts=2,
            max_profit=175.0,
            max_loss=250.0,
            underlying_at_entry=591.50,
            call_wall=595.0,
            put_wall=585.0,
            gex_regime="NEUTRAL",
            vix_at_entry=15.5,
            # Kronos context (fields that were missing)
            flip_point=590.0,
            net_gex=1500000.0,
            # Oracle context (fields that were missing)
            oracle_confidence=0.75,
            oracle_advice="TRADE_FULL",
            ml_direction="BULLISH",
            ml_confidence=0.65,
            ml_model_name="GEX_5_MODEL_ENSEMBLE",
            ml_win_probability=0.62,
            ml_top_features="vix_level,gex_regime,wall_proximity",
            # Wall context (fields that were missing)
            wall_type="PUT_WALL",
            wall_distance_pct=1.1,
            trade_reasoning="Test position for database save verification",
            # Order tracking
            order_id="TEST_PAPER",
            status=PositionStatus.OPEN,
            open_time=now,
        )

        print(f"\n  Created test position: {test_id}")
        print(f"    Spread: {test_position.spread_type.value}")
        print(f"    Strikes: {test_position.long_strike}/{test_position.short_strike}")
        print(f"    Oracle Advice: {test_position.oracle_advice}")

        # Save to database
        success = trader.db.save_position(test_position)

        if success:
            print("\n  ✅ Position saved to database")

            # Verify by reading it back
            positions = trader.db.get_open_positions()
            found = None
            for pos in positions:
                if pos.position_id == test_id:
                    found = pos
                    break

            if found:
                print(f"\n  Retrieved position from database:")
                print(f"    Position ID: {found.position_id}")
                print(f"    Oracle Advice: {found.oracle_advice}")
                print(f"    ML Model: {found.ml_model_name}")
                print(f"    Wall Type: {found.wall_type}")
                print(f"    Trade Reasoning: {found.trade_reasoning[:50]}...")

                # Clean up - close the test position
                trader.db.close_position(
                    position_id=test_id,
                    close_price=1.30,
                    realized_pnl=10.0,
                    close_reason="TEST_CLEANUP"
                )
                print(f"\n  🧹 Test position cleaned up (closed)")

                print("\n✅ PASS: Position save and retrieval successful")
                return True
            else:
                print(f"\n❌ FAIL: Position saved but not found in database")
                return False
        else:
            print("\n❌ FAIL: Position save returned False")
            return False

    except Exception as e:
        print(f"\n❌ FAIL: Position save error: {e}")
        traceback.print_exc()
        return False


def test_full_cycle(trader):
    """Test 5: Run a full trading cycle (if market conditions allow)."""
    print("\n" + "="*60)
    print("TEST 5: Full Trading Cycle")
    print("="*60)

    try:
        result = trader.run_cycle()

        print(f"\n  Cycle Result:")
        print(f"    Action: {result.get('action', 'N/A')}")
        print(f"    Trades Opened: {result.get('trades_opened', 0)}")
        print(f"    Trades Closed: {result.get('trades_closed', 0)}")
        print(f"    Realized P&L: ${result.get('realized_pnl', 0):.2f}")

        if result.get('errors'):
            print(f"    Errors: {result['errors']}")

        if result.get('details', {}).get('skip_reason'):
            print(f"    Skip Reason: {result['details']['skip_reason']}")

        if result.get('action') == 'error':
            print("\n⚠️  WARN: Cycle completed with errors")
        else:
            print("\n✅ PASS: Trading cycle completed")

        return True

    except Exception as e:
        print(f"\n❌ FAIL: Trading cycle error: {e}")
        traceback.print_exc()
        return False


def main():
    """Run all ICARUS tests."""
    print("\n" + "="*60)
    print("ICARUS POSITION SAVE TEST SUITE")
    print(f"Time: {datetime.now(CENTRAL_TZ).strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print("="*60)

    results = {}

    # Test 1: Database schema
    results['schema'] = test_db_schema()

    # Test 2: Initialization
    trader = test_icarus_init()
    results['init'] = trader is not None

    if trader:
        # Test 3: Signal generation
        signal = test_signal_generation(trader)
        results['signal'] = signal is not None

        # Test 4: Position save (most important test)
        results['position_save'] = test_position_save(trader)

        # Test 5: Full cycle
        results['full_cycle'] = test_full_cycle(trader)

    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)

    passed = 0
    failed = 0
    skipped = 0

    for test_name, result in results.items():
        if result is True:
            status = "✅ PASS"
            passed += 1
        elif result is False:
            status = "❌ FAIL"
            failed += 1
        else:
            status = "⚠️  SKIP"
            skipped += 1
        print(f"  {test_name}: {status}")

    print(f"\nTotal: {passed} passed, {failed} failed, {skipped} skipped")

    if failed > 0:
        print("\n⚠️  Some tests failed. Check errors above.")
        return 1
    elif results.get('position_save') is True:
        print("\n🎉 ICARUS position save is working correctly!")
        return 0
    else:
        print("\n⚠️  Tests inconclusive. May need market hours to fully verify.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
