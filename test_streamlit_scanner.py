#!/usr/bin/env python3
"""Test if Streamlit scanner can actually fetch data"""
import os
import sys

# Mock streamlit for testing
class MockStreamlit:
    class secrets:
        @staticmethod
        def get(key, default=None):
            secrets_map = {
                'tv_username': 'I-RWFNBLR2S1DP',
                'endpoint': 'https://stocks.tradingvolatility.net/api'
            }
            return secrets_map.get(key, default)

sys.modules['streamlit'] = MockStreamlit()

# Now import and test
from core_classes_and_engines import TradingVolatilityAPI

print("Testing TradingVolatilityAPI with Streamlit secrets mock...")
print("=" * 80)

api = TradingVolatilityAPI()
print(f"API Key: {api.api_key}")
print(f"Endpoint: {api.endpoint}")
print()

print("Fetching SPY data (respecting 20s rate limit)...")
import time
start = time.time()

result = api.get_net_gamma('SPY')

elapsed = time.time() - start
print(f"Request took: {elapsed:.1f}s")
print()

if 'error' in result:
    print(f"❌ ERROR: {result['error']}")
else:
    print(f"✅ SUCCESS!")
    print(f"  Symbol: {result.get('symbol')}")
    print(f"  Spot Price: ${result.get('spot_price', 0):.2f}")
    print(f"  Net GEX: ${result.get('net_gex', 0)/1e9:.2f}B")
    print(f"  Flip Point: ${result.get('flip_point', 0):.2f}")
