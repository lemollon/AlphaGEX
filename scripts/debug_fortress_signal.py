#!/usr/bin/env python3
"""
FORTRESS Signal Debug Script
=========================

Traces through the EXACT signal generation flow to find why FORTRESS isn't trading.

Run on Render shell:
    python scripts/debug_fortress_signal.py
"""

import os
import sys
import json
from datetime import datetime
from zoneinfo import ZoneInfo

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CENTRAL_TZ = ZoneInfo('America/Chicago')

def print_section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

def print_ok(msg):
    print(f"  ✓ {msg}")

def print_fail(msg):
    print(f"  ✗ {msg}")

def print_info(msg):
    print(f"    {msg}")

def main():
    print_section("FORTRESS SIGNAL DEBUG")
    print(f"  Time: {datetime.now(CENTRAL_TZ).strftime('%Y-%m-%d %H:%M:%S CT')}")

    # Step 1: Import and initialize
    print_section("STEP 1: Initialize SignalGenerator")
    try:
        from trading.fortress_v2.signals import SignalGenerator
        from trading.fortress_v2.models import FortressConfig

        config = FortressConfig()
        signals = SignalGenerator(config)
        print_ok(f"SignalGenerator initialized")
        print_info(f"Ticker: {config.ticker}")
        print_info(f"Min Win Prob: {config.min_win_probability}")
        print_info(f"Min Credit: ${config.min_credit}")
    except Exception as e:
        print_fail(f"Failed to initialize: {e}")
        import traceback
        traceback.print_exc()
        return

    # Step 2: Get market data
    print_section("STEP 2: Get Market Data (get_market_data)")
    try:
        market_data = signals.get_market_data()
        if market_data:
            print_ok("Market data fetched")
            print_info(f"spot_price: ${market_data.get('spot_price', 0):.2f}")
            print_info(f"vix: {market_data.get('vix', 0):.2f}")
            print_info(f"expected_move: ${market_data.get('expected_move', 0):.2f}")
            print_info(f"call_wall: ${market_data.get('call_wall', 0):.2f}")
            print_info(f"put_wall: ${market_data.get('put_wall', 0):.2f}")
            print_info(f"gex_regime: {market_data.get('gex_regime', 'UNKNOWN')}")
            print_info(f"flip_point: ${market_data.get('flip_point', 0):.2f}")
            print_info(f"net_gex: {market_data.get('net_gex', 0)}")
        else:
            print_fail("Market data returned None!")
            return
    except Exception as e:
        print_fail(f"Market data error: {e}")
        import traceback
        traceback.print_exc()
        return

    # Step 3: Get Oracle advice
    print_section("STEP 3: Get Oracle Advice")
    try:
        oracle_data = signals.get_oracle_advice(market_data)
        if oracle_data:
            print_ok("Oracle advice fetched")
            print_info(f"advice: {oracle_data.get('advice', 'UNKNOWN')}")
            print_info(f"win_probability: {oracle_data.get('win_probability', 0):.1%}")
            print_info(f"confidence: {oracle_data.get('confidence', 0):.1%}")
            print_info(f"reasoning: {oracle_data.get('reasoning', 'N/A')[:100]}...")

            top_factors = oracle_data.get('top_factors', [])
            if top_factors:
                print_info("Top factors:")
                for f in top_factors[:3]:
                    print_info(f"  - {f.get('factor')}: {f.get('impact', 0):.3f}")

            # Check if Oracle says trade
            advice = oracle_data.get('advice', '')
            oracle_says_trade = advice in ('TRADE_FULL', 'TRADE_REDUCED', 'ENTER')
            if oracle_says_trade:
                print_ok(f"Oracle says TRADE! ({advice})")
            else:
                print_fail(f"Oracle says NO TRADE ({advice})")
        else:
            print_fail("Oracle returned None!")
    except Exception as e:
        print_fail(f"Oracle error: {e}")
        import traceback
        traceback.print_exc()

    # Step 4: Generate signal
    print_section("STEP 4: Generate Signal")
    try:
        # Pass oracle_data to avoid double call
        signal = signals.generate_signal(oracle_data=oracle_data)

        if signal:
            print_ok("Signal generated")
            print_info(f"source: {signal.source}")
            print_info(f"confidence: {signal.confidence:.1%}")
            print_info(f"reasoning: {signal.reasoning[:100]}...")
            print_info(f"oracle_advice: {signal.oracle_advice}")
            print_info(f"oracle_win_probability: {getattr(signal, 'oracle_win_probability', 0):.1%}")

            # Strikes
            print_info(f"Strikes:")
            print_info(f"  Put spread: ${signal.put_long} / ${signal.put_short}")
            print_info(f"  Call spread: ${signal.call_short} / ${signal.call_long}")
            print_info(f"  Total credit: ${signal.total_credit:.2f}")
            print_info(f"  Max loss: ${signal.max_loss:.2f}")

            # Check is_valid
            print_section("STEP 5: Check is_valid")
            print_info(f"signal.is_valid = {signal.is_valid}")

            # Manual validation check
            oracle_approved = signal.oracle_advice in ('TRADE_FULL', 'TRADE_REDUCED', 'ENTER')
            print_info(f"  oracle_approved: {oracle_approved} (advice={signal.oracle_advice})")
            print_info(f"  confidence >= 0.5: {signal.confidence >= 0.5} ({signal.confidence:.2f})")
            print_info(f"  total_credit > 0: {signal.total_credit > 0} (${signal.total_credit:.2f})")
            print_info(f"  put_short > put_long > 0: {signal.put_short > signal.put_long > 0} ({signal.put_short} > {signal.put_long})")
            print_info(f"  call_short < call_long: {signal.call_short < signal.call_long} ({signal.call_short} < {signal.call_long})")
            print_info(f"  call_short > put_short: {signal.call_short > signal.put_short} ({signal.call_short} > {signal.put_short})")

            if signal.is_valid:
                print_ok("Signal IS VALID - should trade!")
            else:
                print_fail("Signal is INVALID - will NOT trade")

                # Diagnose why
                if not oracle_approved and signal.confidence < 0.5:
                    print_fail("  REASON: Oracle not approved AND confidence < 50%")
                if signal.total_credit <= 0:
                    print_fail("  REASON: Total credit is $0 or negative")
                if not (signal.put_short > signal.put_long > 0):
                    print_fail("  REASON: Put strikes invalid")
                if not (signal.call_short < signal.call_long):
                    print_fail("  REASON: Call strikes invalid")
                if not (signal.call_short > signal.put_short):
                    print_fail("  REASON: Strikes overlap")
        else:
            print_fail("Signal returned None!")
            print_info("This means generate_signal() returned early before building signal")
    except Exception as e:
        print_fail(f"Signal generation error: {e}")
        import traceback
        traceback.print_exc()

    # Step 6: Check trading conditions
    print_section("STEP 6: Trading Conditions")
    try:
        from trading.fortress_v2.trader import FortressTrader
        from trading.fortress_v2.models import TradingMode

        trader = FortressTrader(mode=TradingMode.PAPER)
        now = datetime.now(CENTRAL_TZ)

        can_trade, reason = trader._check_basic_conditions(now)
        print_info(f"_check_basic_conditions: {can_trade}")
        if not can_trade:
            print_fail(f"  BLOCKED: {reason}")
        else:
            print_ok(f"  Basic conditions OK")

        # Check position count
        open_positions = trader.db.get_position_count()
        print_info(f"Open positions: {open_positions}")
        if open_positions > 0:
            print_fail(f"  BLOCKED: Already have {open_positions} open position(s)")

    except Exception as e:
        print_fail(f"Trading conditions error: {e}")
        import traceback
        traceback.print_exc()

    print_section("DEBUG COMPLETE")
    print("  Review the output above to find what's blocking trades.")

if __name__ == '__main__':
    main()
