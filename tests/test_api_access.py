#!/usr/bin/env python3
"""
Test API access to prove whether 403 errors are environment-specific
Run this on YOUR Render deployment to verify APIs work there
"""

import os
import requests
from dotenv import load_dotenv

load_dotenv()

def test_trading_volatility_api():
    """Test Trading Volatility API access"""
    api_key = os.getenv('TRADING_VOLATILITY_API_KEY') or os.getenv('TV_USERNAME')

    print("=" * 60)
    print("TRADING VOLATILITY API TEST")
    print("=" * 60)
    print(f"API Key: {api_key[:5]}...{api_key[-5:] if api_key else 'NOT FOUND'}")

    if not api_key:
        print("❌ NO API KEY FOUND")
        return False

    # Test GEX endpoint
    url = "https://api.tradingvolatility.net/gex/SPY"
    headers = {"Authorization": api_key}

    print(f"\nTesting: {url}")
    print(f"Headers: Authorization: {api_key[:10]}...")

    try:
        response = requests.get(url, headers=headers, timeout=10)

        print(f"\nStatus Code: {response.status_code}")
        print(f"Response (first 200 chars):")
        print(response.text[:200])

        if response.status_code == 200:
            print("\n✅ SUCCESS - API IS WORKING!")
            print("Sophisticated strategies WILL work on this environment")
            return True
        elif response.status_code == 403:
            print("\n❌ 403 FORBIDDEN - API ACCESS DENIED")
            print("This is why only fallback straddle is executing")
            return False
        else:
            print(f"\n⚠️  UNEXPECTED STATUS: {response.status_code}")
            return False

    except Exception as e:
        print(f"\n❌ REQUEST FAILED: {str(e)}")
        return False

def test_polygon_api():
    """Test Polygon.io API access"""
    api_key = os.getenv('POLYGON_API_KEY')

    print("\n" + "=" * 60)
    print("POLYGON.IO API TEST")
    print("=" * 60)
    print(f"API Key: {api_key[:5]}...{api_key[-5:] if api_key else 'NOT FOUND'}")

    if not api_key:
        print("❌ NO API KEY FOUND")
        return False

    # Test quote endpoint
    url = f"https://api.polygon.io/v2/last/trade/SPY?apiKey={api_key}"

    print(f"\nTesting: {url[:50]}...")

    try:
        response = requests.get(url, timeout=10)

        print(f"\nStatus Code: {response.status_code}")
        print(f"Response (first 200 chars):")
        print(response.text[:200])

        if response.status_code == 200:
            print("\n✅ SUCCESS - POLYGON API IS WORKING!")
            return True
        else:
            print(f"\n❌ FAILED WITH STATUS: {response.status_code}")
            return False

    except Exception as e:
        print(f"\n❌ REQUEST FAILED: {str(e)}")
        return False

if __name__ == "__main__":
    print("\n" + "🧪 API ACCESS TEST".center(60, "="))
    print("This test proves whether API 403 errors are environment-specific\n")

    tv_works = test_trading_volatility_api()
    polygon_works = test_polygon_api()

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Trading Volatility API: {'✅ WORKING' if tv_works else '❌ BLOCKED (403)'}")
    print(f"Polygon.io API: {'✅ WORKING' if polygon_works else '❌ BLOCKED'}")

    if tv_works:
        print("\n🎉 APIs WORK! Sophisticated strategies SHOULD execute")
        print("   If only seeing fallback straddle, there's a CODE BUG")
    else:
        print("\n⚠️  APIs BLOCKED! This environment cannot access market data")
        print("   Only fallback straddle will execute (by design)")

    print("=" * 60)
