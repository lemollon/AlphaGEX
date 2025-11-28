#!/usr/bin/env python3
"""
Simple Alpha Vantage API Test - Try different endpoints
"""
import os
import requests
from dotenv import load_dotenv
import json

load_dotenv()

api_key = os.getenv('ALPHA_VANTAGE_API_KEY', 'IW5CSY60VSCU8TUJ')

print(f"Testing API Key: {api_key}")
print("=" * 70)

# Test 1: Global Quote (simplest endpoint)
print("\n1. Testing GLOBAL_QUOTE endpoint...")
url1 = f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol=IBM&apikey={api_key}"
try:
    r1 = requests.get(url1, timeout=10)
    print(f"   Status Code: {r1.status_code}")
    data1 = r1.json()
    print(f"   Response: {json.dumps(data1, indent=2)[:300]}...")
except Exception as e:
    print(f"   Error: {e}")

# Test 2: Time Series Intraday
print("\n2. Testing TIME_SERIES_INTRADAY endpoint...")
url2 = f"https://www.alphavantage.co/query?function=TIME_SERIES_INTRADAY&symbol=IBM&interval=5min&apikey={api_key}"
try:
    r2 = requests.get(url2, timeout=10)
    print(f"   Status Code: {r2.status_code}")
    data2 = r2.json()
    print(f"   Response keys: {list(data2.keys())}")
    if 'Note' in data2:
        print(f"   Note: {data2['Note']}")
    if 'Error Message' in data2:
        print(f"   Error: {data2['Error Message']}")
except Exception as e:
    print(f"   Error: {e}")

# Test 3: Check if API key is valid
print("\n3. Testing API Key validity...")
url3 = f"https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol=MSFT&apikey={api_key}"
try:
    r3 = requests.get(url3, timeout=10)
    print(f"   Status Code: {r3.status_code}")
    if r3.status_code == 200:
        data3 = r3.json()
        if 'Error Message' in data3:
            print(f"   ❌ Invalid API key or symbol: {data3['Error Message']}")
        elif 'Note' in data3:
            print(f"   ⚠️ Rate limit: {data3['Note']}")
        elif 'Information' in data3:
            print(f"   ℹ️ Info: {data3['Information']}")
        elif 'Time Series (Daily)' in data3:
            print(f"   ✅ API key is VALID! Got data successfully")
        else:
            print(f"   Response: {json.dumps(data3, indent=2)[:500]}")
    else:
        print(f"   ❌ HTTP {r3.status_code}: {r3.text[:200]}")
except Exception as e:
    print(f"   Error: {e}")

print("\n" + "=" * 70)
