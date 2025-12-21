#!/usr/bin/env python3
"""
Test all VIX sources to find which one works.
Run this on Render console or locally.
"""

import sys

print("=" * 50)
print("VIX SOURCE TESTER")
print("=" * 50)

# Test 1: Yahoo Direct API
print("\n[1] Yahoo Finance Direct API...")
try:
    import requests
    url = "https://query1.finance.yahoo.com/v8/finance/chart/%5EVIX"
    resp = requests.get(url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
    print(f"    Status: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        price = data['chart']['result'][0]['meta']['regularMarketPrice']
        print(f"    ✅ VIX = {price}")
    else:
        print(f"    ❌ Bad status: {resp.text[:200]}")
except Exception as e:
    print(f"    ❌ FAILED: {e}")

# Test 2: Google Finance
print("\n[2] Google Finance...")
try:
    import requests
    import re
    url = "https://www.google.com/finance/quote/VIX:INDEXCBOE"
    resp = requests.get(url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
    print(f"    Status: {resp.status_code}")
    if resp.status_code == 200:
        match = re.search(r'data-last-price="([0-9.]+)"', resp.text)
        if match:
            price = float(match.group(1))
            print(f"    ✅ VIX = {price}")
        else:
            print(f"    ❌ Could not parse price from HTML")
    else:
        print(f"    ❌ Bad status")
except Exception as e:
    print(f"    ❌ FAILED: {e}")

# Test 3: yfinance library
print("\n[3] yfinance library...")
try:
    import yfinance as yf
    vix = yf.Ticker("^VIX")
    hist = vix.history(period='5d')
    if not hist.empty:
        price = float(hist['Close'].iloc[-1])
        print(f"    ✅ VIX = {price}")
    else:
        print(f"    ❌ Empty history")
except ImportError:
    print(f"    ❌ yfinance not installed")
except Exception as e:
    print(f"    ❌ FAILED: {e}")

# Test 4: Tradier
print("\n[4] Tradier API...")
try:
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from data.tradier_data_fetcher import TradierDataFetcher

    use_sandbox = os.getenv('TRADIER_SANDBOX', 'true').lower() == 'true'
    print(f"    Sandbox mode: {use_sandbox}")

    tradier = TradierDataFetcher(sandbox=use_sandbox)
    print(f"    Base URL: {tradier.base_url}")

    vix_quote = tradier.get_quote("$VIX.X")
    if vix_quote and vix_quote.get('last'):
        price = float(vix_quote['last'])
        print(f"    ✅ VIX = {price}")
    else:
        print(f"    ❌ No quote returned: {vix_quote}")
except Exception as e:
    print(f"    ❌ FAILED: {e}")

print("\n" + "=" * 50)
print("DONE - At least one source should work!")
print("=" * 50)
