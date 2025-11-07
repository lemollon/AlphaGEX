#!/usr/bin/env python3
"""Test Trading Volatility API with TradingVolatilityAPI class"""
import os
os.environ['TRADING_VOLATILITY_API_KEY'] = 'I-RWFNBLR2S1DP'

from core_classes_and_engines import TradingVolatilityAPI

print("Testing TradingVolatilityAPI class...")
print("=" * 60)

api = TradingVolatilityAPI()
print(f"API Key: {api.api_key}")
print(f"Endpoint: {api.endpoint}")
print()

print("Fetching SPY data...")
result = api.get_net_gamma('SPY')

if 'error' in result:
    print(f"❌ Error: {result['error']}")
else:
    print(f"✅ Success!")
    print(f"Symbol: {result.get('symbol')}")
    print(f"Spot Price: ${result.get('spot_price', 0):.2f}")
    print(f"Net GEX: ${result.get('net_gex', 0)/1e9:.2f}B")
    print(f"Flip Point: ${result.get('flip_point', 0):.2f}")
