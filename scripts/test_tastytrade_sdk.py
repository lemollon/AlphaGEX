#!/usr/bin/env python3
"""
Test Tastytrade SDK Installation and DXLinkStreamer
Verifies real-time futures quotes are working for HERACLES
"""

import os
import sys

print("=" * 60)
print("TASTYTRADE SDK VERIFICATION")
print("=" * 60)

# Step 1: Check if tastytrade package is installed
print("\n1. Checking tastytrade package installation...")
try:
    import tastytrade
    print(f"   ✅ tastytrade version: {tastytrade.__version__}")
except ImportError as e:
    print(f"   ❌ tastytrade NOT installed: {e}")
    print("\n   To install: pip install tastytrade>=11.0.0")
    sys.exit(1)

# Step 2: Check required imports
print("\n2. Checking required imports...")
try:
    from tastytrade import Session, DXLinkStreamer
    from tastytrade.dxfeed import Quote
    print("   ✅ Session imported")
    print("   ✅ DXLinkStreamer imported")
    print("   ✅ Quote imported")
except ImportError as e:
    print(f"   ❌ Import failed: {e}")
    sys.exit(1)

# Step 3: Check credentials
print("\n3. Checking Tastytrade credentials...")
username = os.environ.get("TASTYTRADE_USERNAME")
password = os.environ.get("TASTYTRADE_PASSWORD")

if not username:
    print("   ❌ TASTYTRADE_USERNAME not set")
    sys.exit(1)
if not password:
    print("   ❌ TASTYTRADE_PASSWORD not set")
    sys.exit(1)

print(f"   ✅ Username: {username[:3]}***")
print(f"   ✅ Password: {'*' * 8}")

# Step 4: Test authentication
print("\n4. Testing Tastytrade authentication...")
try:
    session = Session(username, password)
    print("   ✅ Authentication successful!")
    print(f"   ✅ Session token obtained")
except Exception as e:
    print(f"   ❌ Authentication failed: {e}")
    sys.exit(1)

# Step 5: Test DXLinkStreamer for MES futures quote
print("\n5. Testing DXLinkStreamer for MES futures quote...")
import asyncio

async def get_mes_quote():
    """Get a single MES futures quote via DXLinkStreamer"""
    try:
        async with DXLinkStreamer(session) as streamer:
            # Try different MES symbol formats
            symbols_to_try = ['/MESH6', '/MESM6', '/MES']

            for symbol in symbols_to_try:
                print(f"   Trying symbol: {symbol}")
                try:
                    await streamer.subscribe(Quote, [symbol])

                    # Wait for quote with timeout
                    quote = await asyncio.wait_for(
                        streamer.get_event(Quote),
                        timeout=10.0
                    )

                    if quote and (quote.bid_price or quote.ask_price):
                        return {
                            'symbol': symbol,
                            'bid': quote.bid_price,
                            'ask': quote.ask_price,
                            'success': True
                        }
                except asyncio.TimeoutError:
                    print(f"      Timeout on {symbol}, trying next...")
                except Exception as e:
                    print(f"      Error on {symbol}: {e}")

            return {'success': False, 'error': 'No quotes received for any symbol'}

    except Exception as e:
        return {'success': False, 'error': str(e)}

try:
    result = asyncio.run(get_mes_quote())

    if result.get('success'):
        print(f"\n   ✅ Got MES quote via DXLinkStreamer!")
        print(f"   Symbol: {result['symbol']}")
        print(f"   Bid: {result['bid']}")
        print(f"   Ask: {result['ask']}")
        print(f"\n   🚀 REAL-TIME FUTURES QUOTES ARE WORKING!")
    else:
        print(f"\n   ⚠️  DXLinkStreamer connected but no quote received")
        print(f"   Error: {result.get('error', 'Unknown')}")
        print("\n   Note: This may be a known issue with Tastytrade's API token")
        print("   See: https://github.com/tastyware/tastytrade/issues/142")
        print("   Fallback to Yahoo Finance will be used")

except Exception as e:
    print(f"\n   ❌ DXLinkStreamer test failed: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
print("VERIFICATION COMPLETE")
print("=" * 60)
