#!/usr/bin/env python3
"""
Test All Data Sources for AlphaGEX
Shows which data sources are working and ready to use
"""
import os
import sys
from dotenv import load_dotenv

# Load environment
load_dotenv()

print("=" * 80)
print("AlphaGEX Data Source Health Check")
print("=" * 80)

# Test 1: Yahoo Finance (yfinance) - FREE, no API key needed
print("\n1. Testing Yahoo Finance (yfinance)...")
print("   Status: Checking...")

try:
    import yfinance as yf

    # Test simple fetch
    ticker = yf.Ticker("SPY")
    hist = ticker.history(period="5d")

    if not hist.empty:
        latest_price = hist['Close'].iloc[-1]
        print(f"   ✅ SUCCESS! Yahoo Finance is working")
        print(f"   📊 SPY Latest Close: ${latest_price:.2f}")
        print(f"   📈 Got {len(hist)} days of data")
        print(f"   💰 Cost: FREE (unlimited)")
        print(f"   🔑 API Key: Not required")
        yfinance_working = True
    else:
        print(f"   ⚠️ WARNING: Got empty data from yfinance")
        yfinance_working = False

except ImportError:
    print(f"   ❌ FAILED: yfinance not installed")
    print(f"   Fix: pip install yfinance")
    yfinance_working = False
except Exception as e:
    print(f"   ❌ FAILED: {e}")
    yfinance_working = False

# Test 2: Alpha Vantage
print("\n2. Testing Alpha Vantage...")
alpha_key = os.getenv('ALPHA_VANTAGE_API_KEY')

if not alpha_key:
    print(f"   ⚠️ SKIPPED: ALPHA_VANTAGE_API_KEY not set in .env")
    print(f"   Set it in .env file to enable this source")
    alpha_working = False
else:
    print(f"   🔑 API Key: {alpha_key[:10]}...")

    try:
        import requests
        url = "https://www.alphavantage.co/query"
        params = {
            "function": "GLOBAL_QUOTE",
            "symbol": "SPY",
            "apikey": alpha_key
        }

        response = requests.get(url, params=params, timeout=10)

        if response.status_code == 200:
            data = response.json()
            if 'Global Quote' in data and data['Global Quote']:
                price = data['Global Quote'].get('05. price', 'N/A')
                print(f"   ✅ SUCCESS! Alpha Vantage is working")
                print(f"   📊 SPY Price: ${price}")
                print(f"   💰 Cost: FREE (500 calls/day)")
                alpha_working = True
            elif 'Note' in data:
                print(f"   ⚠️ WARNING: Rate limited - {data['Note']}")
                alpha_working = False
            else:
                print(f"   ⚠️ WARNING: Unexpected response - {list(data.keys())}")
                alpha_working = False
        elif response.status_code == 403:
            print(f"   ❌ FAILED: 403 Forbidden")
            print(f"   Reason: API key may need activation (24-48 hours)")
            print(f"   Check your email for activation link from Alpha Vantage")
            print(f"   Or get a new key at: https://www.alphavantage.co/support/#api-key")
            alpha_working = False
        else:
            print(f"   ❌ FAILED: HTTP {response.status_code}")
            alpha_working = False

    except Exception as e:
        print(f"   ❌ FAILED: {e}")
        alpha_working = False

# Test 3: Polygon.io
print("\n3. Testing Polygon.io...")
polygon_key = os.getenv('POLYGON_API_KEY')

if not polygon_key:
    print(f"   ⚠️ SKIPPED: POLYGON_API_KEY not set")
    print(f"   Get free key at: https://polygon.io/")
    print(f"   Free tier: 5 calls/minute")
    polygon_working = False
else:
    print(f"   🔑 API Key: {polygon_key[:10]}...")
    print(f"   ℹ️ Not tested (optional backup source)")
    polygon_working = None

# Test 4: Twelve Data
print("\n4. Testing Twelve Data...")
twelve_key = os.getenv('TWELVE_DATA_API_KEY')

if not twelve_key:
    print(f"   ⚠️ SKIPPED: TWELVE_DATA_API_KEY not set")
    print(f"   Get free key at: https://twelvedata.com/")
    print(f"   Free tier: 800 calls/day")
    twelve_working = False
else:
    print(f"   🔑 API Key: {twelve_key[:10]}...")
    print(f"   ℹ️ Not tested (optional backup source)")
    twelve_working = None

# Summary
print("\n" + "=" * 80)
print("SUMMARY")
print("=" * 80)

working_sources = []
if yfinance_working:
    working_sources.append("Yahoo Finance (yfinance)")
if alpha_working:
    working_sources.append("Alpha Vantage")

if working_sources:
    print(f"\n✅ {len(working_sources)} data source(s) WORKING:")
    for source in working_sources:
        print(f"   • {source}")
else:
    print(f"\n⚠️ No data sources currently working")

print(f"\n📋 Recommendation:")
if yfinance_working:
    print(f"   ✅ USE: Yahoo Finance (yfinance)")
    print(f"   • It's free, unlimited, and working perfectly")
    print(f"   • No API key needed")
    print(f"   • Real-time data during market hours")
    print(f"\n   Your AlphaGEX system is READY TO USE with Yahoo Finance!")
else:
    print(f"   ⚠️ Install yfinance: pip install yfinance")

if not alpha_working and alpha_key:
    print(f"\n📧 Alpha Vantage Action Items:")
    print(f"   1. Check your email for activation link")
    print(f"   2. Wait 24-48 hours for key activation")
    print(f"   3. Or get new key: https://www.alphavantage.co/support/#api-key")
    print(f"   4. Contact support: [email protected]")

print("\n" + "=" * 80)
print("✅ Test Complete!")
print("=" * 80)
