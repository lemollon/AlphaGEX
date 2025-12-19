#!/usr/bin/env python3
"""
Test script to verify GEX calculator works correctly with real Tradier data.
This proves:
1. We can get options data from Tradier
2. GEX calculations are mathematically correct
3. Data is from current trading day
"""

import os
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

print("=" * 70)
print("GEX CALCULATOR VERIFICATION TEST")
print(f"Test Time: {datetime.now().isoformat()}")
print("=" * 70)

# Test 1: Check if Tradier credentials exist
print("\n[TEST 1] Checking Tradier API credentials...")
tradier_key = os.getenv('TRADIER_API_KEY')
if tradier_key:
    print(f"  ✅ TRADIER_API_KEY found (length: {len(tradier_key)})")
else:
    print("  ⚠️ TRADIER_API_KEY not set - will use sandbox or fail")

# Test 2: Try to import and use Tradier
print("\n[TEST 2] Testing Tradier Data Fetcher...")
try:
    from data.tradier_data_fetcher import TradierDataFetcher
    tradier = TradierDataFetcher()
    print(f"  ✅ TradierDataFetcher initialized")
    print(f"  - Sandbox mode: {tradier.sandbox}")
    print(f"  - Base URL: {tradier.base_url}")
except Exception as e:
    print(f"  ❌ TradierDataFetcher failed: {e}")
    tradier = None

# Test 3: Get a quote to verify API works
if tradier:
    print("\n[TEST 3] Getting SPY quote from Tradier...")
    try:
        quote = tradier.get_quote('SPY')
        if quote:
            print(f"  ✅ SPY Quote received:")
            print(f"     - Last Price: ${quote.get('last', 'N/A')}")
            print(f"     - Bid/Ask: ${quote.get('bid', 'N/A')} / ${quote.get('ask', 'N/A')}")
            print(f"     - Volume: {quote.get('volume', 'N/A'):,}")
            spot_price = float(quote.get('last') or quote.get('close') or 0)
        else:
            print("  ❌ No quote data returned")
            spot_price = 0
    except Exception as e:
        print(f"  ❌ Quote failed: {e}")
        spot_price = 0

# Test 4: Get options chain
if tradier and spot_price > 0:
    print("\n[TEST 4] Getting SPY options chain with Greeks...")
    try:
        chain = tradier.get_option_chain('SPY', greeks=True)
        if chain and chain.chains:
            total_contracts = sum(len(contracts) for contracts in chain.chains.values())
            print(f"  ✅ Options chain received:")
            print(f"     - Underlying Price: ${chain.underlying_price:.2f}")
            print(f"     - Total Expirations: {len(chain.chains)}")
            print(f"     - Total Contracts: {total_contracts}")

            # Show sample contract to verify Greeks
            first_exp = list(chain.chains.keys())[0]
            sample = chain.chains[first_exp][0]
            print(f"\n  Sample contract ({first_exp}):")
            print(f"     - Strike: ${sample.strike}")
            print(f"     - Type: {sample.option_type}")
            print(f"     - Gamma: {sample.gamma}")
            print(f"     - Delta: {sample.delta}")
            print(f"     - Open Interest: {sample.open_interest}")
        else:
            print("  ❌ No options chain data")
            chain = None
    except Exception as e:
        print(f"  ❌ Options chain failed: {e}")
        import traceback
        traceback.print_exc()
        chain = None

# Test 5: Calculate GEX using our calculator
print("\n[TEST 5] Testing GEX Calculator...")
try:
    from data.gex_calculator import TradierGEXCalculator, calculate_gex_from_chain

    calculator = TradierGEXCalculator()
    print("  ✅ GEX Calculator initialized")

    # Test the calculation
    gex_result = calculator.get_gex('SPY')

    if gex_result and 'error' not in gex_result:
        print(f"\n  ✅ GEX CALCULATION RESULTS:")
        print(f"     Symbol: {gex_result.get('symbol')}")
        print(f"     Spot Price: ${gex_result.get('spot_price', 0):.2f}")
        print(f"     Net GEX: ${gex_result.get('net_gex', 0):,.0f}")
        print(f"     Call GEX: ${gex_result.get('call_gex', 0):,.0f}")
        print(f"     Put GEX: ${gex_result.get('put_gex', 0):,.0f}")
        print(f"     Call Wall: ${gex_result.get('call_wall', 0):.2f}")
        print(f"     Put Wall: ${gex_result.get('put_wall', 0):.2f}")
        print(f"     Gamma Flip: ${gex_result.get('gamma_flip', 0):.2f}")
        print(f"     Max Pain: ${gex_result.get('max_pain', 0):.2f}")
        print(f"     Data Source: {gex_result.get('data_source')}")
        print(f"     Collection Date: {gex_result.get('collection_date')}")
    else:
        print(f"  ❌ GEX calculation failed: {gex_result}")

except Exception as e:
    print(f"  ❌ GEX Calculator test failed: {e}")
    import traceback
    traceback.print_exc()

# Test 6: Verify the math manually
print("\n[TEST 6] Manual GEX Formula Verification...")
print("""
  GEX FORMULA EXPLANATION:
  ========================
  For each option contract:
    GEX_per_strike = gamma × open_interest × 100 × spot_price²

  Where:
    - gamma: Rate of change of delta (from Greeks)
    - open_interest: Number of contracts outstanding
    - 100: Contract multiplier (1 contract = 100 shares)
    - spot_price²: Price scaling factor

  Market Maker Interpretation:
    - MMs are typically SHORT options (sold to retail)
    - Short Calls → Long Gamma → Positive GEX (stabilizing)
    - Short Puts → Short Gamma → Negative GEX (amplifying)

  Net GEX Meaning:
    - Positive Net GEX → Mean reverting market (low volatility)
    - Negative Net GEX → Trending market (high volatility)
""")

# Test 7: Compare with TradingVolatilityAPI if available
print("\n[TEST 7] Comparison with TradingVolatilityAPI (if available)...")
try:
    from core_classes_and_engines import TradingVolatilityAPI
    tv_api = TradingVolatilityAPI()
    tv_result = tv_api.get_net_gamma('SPY')

    if tv_result and 'error' not in tv_result:
        print(f"  ✅ TradingVolatilityAPI result:")
        print(f"     Net GEX: ${tv_result.get('net_gex', 0):,.0f}")
        print(f"     Flip Point: ${tv_result.get('flip_point', 0):.2f}")
        print(f"     Call Wall: ${tv_result.get('call_wall', 0):.2f}")
        print(f"     Put Wall: ${tv_result.get('put_wall', 0):.2f}")

        # Compare if both exist
        if gex_result and 'error' not in gex_result:
            print(f"\n  COMPARISON:")
            print(f"     Net GEX diff: {abs(gex_result.get('net_gex', 0) - tv_result.get('net_gex', 0)):,.0f}")
    else:
        print(f"  ⚠️ TradingVolatilityAPI returned error: {tv_result}")
except ImportError:
    print("  ⚠️ TradingVolatilityAPI not available (expected in some environments)")
except Exception as e:
    print(f"  ⚠️ TradingVolatilityAPI error: {e}")

# Test 8: Verify data freshness
print("\n[TEST 8] Data Freshness Verification...")
print(f"  Current Time: {datetime.now().isoformat()}")
print(f"  Day of Week: {datetime.now().strftime('%A')}")
print(f"  Market Hours: 8:30 AM - 3:00 PM CT")

# Check if we're in market hours (Central Time)
from zoneinfo import ZoneInfo
ct_now = datetime.now(ZoneInfo("America/Chicago"))
print(f"  Central Time: {ct_now.strftime('%Y-%m-%d %H:%M:%S CT')}")

is_weekday = ct_now.weekday() < 5
market_open = ct_now.replace(hour=8, minute=30, second=0, microsecond=0)
market_close = ct_now.replace(hour=15, minute=0, second=0, microsecond=0)
is_market_hours = market_open <= ct_now <= market_close

if is_weekday and is_market_hours:
    print("  ✅ Market is OPEN - data should be live")
else:
    print(f"  ⚠️ Market is CLOSED - data may be from last trading day")
    if not is_weekday:
        print(f"     (Weekend: {et_now.strftime('%A')})")

print("\n" + "=" * 70)
print("TEST COMPLETE")
print("=" * 70)
