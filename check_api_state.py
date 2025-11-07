#!/usr/bin/env python3
"""Check TradingVolatilityAPI state and circuit breaker"""
import os
import sys

# Set env var before importing
os.environ['TRADING_VOLATILITY_API_KEY'] = 'I-RWFNBLR2S1DP'

from core_classes_and_engines import TradingVolatilityAPI

print("🔍 Checking TradingVolatilityAPI State")
print("=" * 80)

# Check class-level rate limiter state
print("\n📊 SHARED CLASS STATE:")
print(f"  Circuit Breaker Active: {TradingVolatilityAPI._shared_circuit_breaker_active}")
print(f"  Circuit Breaker Until: {TradingVolatilityAPI._shared_circuit_breaker_until}")
print(f"  Consecutive Rate Limit Errors: {TradingVolatilityAPI._shared_consecutive_rate_limit_errors}")
print(f"  Total API Calls: {TradingVolatilityAPI._shared_api_call_count}")
print(f"  API Calls This Minute: {TradingVolatilityAPI._shared_api_call_count_minute}")
print(f"  Cache Size: {len(TradingVolatilityAPI._shared_response_cache)}")
print(f"  Last Request Time: {TradingVolatilityAPI._shared_last_request_time}")

# Create instance
print("\n📡 Creating TradingVolatilityAPI instance:")
api = TradingVolatilityAPI()
print(f"  API Key: {api.api_key}")
print(f"  Endpoint: {api.endpoint}")

# Check if circuit breaker is blocking
import time
current_time = time.time()
if TradingVolatilityAPI._shared_circuit_breaker_active:
    wait_time = TradingVolatilityAPI._shared_circuit_breaker_until - current_time
    print(f"\n⚠️ CIRCUIT BREAKER IS ACTIVE!")
    print(f"  Wait time remaining: {wait_time:.1f} seconds")
else:
    print(f"\n✅ Circuit breaker is NOT active")

# Check cache
if TradingVolatilityAPI._shared_response_cache:
    print(f"\n💾 CACHED RESPONSES:")
    for key in list(TradingVolatilityAPI._shared_response_cache.keys())[:5]:
        print(f"  - {key}")
