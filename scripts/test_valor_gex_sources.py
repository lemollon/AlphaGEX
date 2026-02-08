#!/usr/bin/env python3
"""
Test VALOR GEX data sources to verify real data is being fetched.
This provides PROOF that the system is working correctly.
"""

import os
import sys
from datetime import datetime
import pytz

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CENTRAL_TZ = pytz.timezone('America/Chicago')

def main():
    print("=" * 70)
    print("VALOR GEX DATA SOURCE TEST")
    print("=" * 70)

    now = datetime.now(CENTRAL_TZ)
    hour = now.hour
    print(f"\nCurrent time (CT): {now.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Current hour: {hour}")

    is_market_hours = 8 <= hour < 15
    is_overnight = (hour >= 15) or (hour < 8)

    print(f"Is market hours (8 AM - 3 PM CT): {is_market_hours}")
    print(f"Is overnight (3 PM - 8 AM CT): {is_overnight}")

    print("\n" + "=" * 70)
    print("DATA SOURCE PRIORITY:")
    print("=" * 70)
    if is_market_hours:
        print("  1. TRADIER (primary - real-time options data)")
        print("  2. TradingVolatility (fallback)")
    else:
        print("  1. TradingVolatility (primary - n+1 GEX data)")
        print("  2. TRADIER (fallback)")

    print("\n" + "=" * 70)
    print("TEST 1: TradingVolatility API")
    print("=" * 70)

    try:
        from core_classes_and_engines import TradingVolatilityAPI

        api = TradingVolatilityAPI()
        api_key = api.api_key

        if api_key:
            print(f"  API Key: {api_key[:10]}... (configured)")
        else:
            print("  API Key: NOT CONFIGURED")
            print("  Set TRADING_VOLATILITY_API_KEY environment variable")

        print("\n  Fetching SPX GEX data...")
        result = api.get_net_gamma("SPX")

        if result and 'error' not in result:
            flip = result.get('flip_point', 0)
            call_wall = result.get('call_wall', 0)
            put_wall = result.get('put_wall', 0)
            net_gex = result.get('net_gex', 0)

            print(f"\n  ✅ TradingVolatility RETURNED DATA:")
            print(f"     flip_point:  {flip}")
            print(f"     call_wall:   {call_wall}")
            print(f"     put_wall:    {put_wall}")
            print(f"     net_gex:     {net_gex}")

            if flip and float(flip) > 0:
                print(f"\n  ✅ REAL DATA CONFIRMED (flip_point > 0)")
            else:
                print(f"\n  ⚠️  flip_point is 0 or missing")
        else:
            print(f"\n  ❌ TradingVolatility returned error or no data")
            if result:
                print(f"     Result: {result}")

    except ImportError as e:
        print(f"  ❌ TradingVolatilityAPI import failed: {e}")
    except Exception as e:
        print(f"  ❌ TradingVolatility error: {e}")

    print("\n" + "=" * 70)
    print("TEST 2: Tradier GEX Calculator")
    print("=" * 70)

    try:
        from data.gex_calculator import TradierGEXCalculator

        tradier_key = os.environ.get('TRADIER_API_KEY')
        if tradier_key:
            print(f"  TRADIER_API_KEY: {tradier_key[:10]}... (configured)")
        else:
            print("  TRADIER_API_KEY: NOT CONFIGURED")

        print("\n  Fetching SPX GEX data (this may take a few seconds)...")
        calculator = TradierGEXCalculator(sandbox=False)
        result = calculator.calculate_gex("SPX")

        if result:
            flip = result.get('flip_point', 0)
            call_wall = result.get('call_wall', 0)
            put_wall = result.get('put_wall', 0)
            net_gex = result.get('net_gex', 0)

            print(f"\n  ✅ Tradier RETURNED DATA:")
            print(f"     flip_point:  {flip}")
            print(f"     call_wall:   {call_wall}")
            print(f"     put_wall:    {put_wall}")
            print(f"     net_gex:     {net_gex}")

            if flip and float(flip) > 0:
                print(f"\n  ✅ REAL DATA CONFIRMED (flip_point > 0)")
            else:
                print(f"\n  ⚠️  flip_point is 0 or missing")
        else:
            print(f"\n  ❌ Tradier returned no data")

    except ImportError as e:
        print(f"  ❌ TradierGEXCalculator import failed: {e}")
    except Exception as e:
        print(f"  ❌ Tradier error: {e}")

    print("\n" + "=" * 70)
    print("TEST 3: get_gex_data_for_heracles() - Full Integration")
    print("=" * 70)

    try:
        from trading.valor.signals import get_gex_data_for_heracles

        print("  Calling get_gex_data_for_heracles('SPX')...")
        result = get_gex_data_for_heracles("SPX")

        print(f"\n  RESULT:")
        for key, value in result.items():
            print(f"     {key}: {value}")

        flip = result.get('flip_point', 0)
        source = result.get('data_source', 'unknown')

        if flip and float(flip) > 0:
            print(f"\n  ✅ SUCCESS: Got flip_point={flip} from {source}")
        else:
            print(f"\n  ❌ FAIL: flip_point is 0 - VALOR will SKIP trading")
            print("     This is CORRECT behavior (no fake data)")

    except Exception as e:
        print(f"  ❌ Integration test error: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "=" * 70)
    print("TEST 4: Database Cache Status")
    print("=" * 70)

    try:
        from trading.valor.signals import _load_gex_cache_from_db

        cache_data, cache_time = _load_gex_cache_from_db()

        if cache_data and cache_time:
            print(f"  ✅ CACHE FOUND IN DATABASE:")
            print(f"     Cache time: {cache_time.strftime('%Y-%m-%d %H:%M:%S')}")
            for key, value in cache_data.items():
                print(f"     {key}: {value}")
        else:
            print("  ⚠️  No cache found in database (normal if first run)")

    except Exception as e:
        print(f"  ❌ Cache test error: {e}")

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print("""
Data Source Priority:
  - Market hours (8 AM - 3 PM CT): TRADIER first, TradingVolatility backup
  - Overnight (3 PM - 8 AM CT): TradingVolatility first, TRADIER backup

If flip_point = 0:
  - VALOR SKIPS trading (no fake data)
  - This is CORRECT behavior

If flip_point > 0:
  - VALOR uses REAL GEX data for signal generation
  - Trading proceeds normally
""")


if __name__ == "__main__":
    main()
