#!/usr/bin/env python3
"""
VIX Price Fetch Diagnostic Script
=================================
Run this script to verify VIX data fetching is working correctly.

Usage:
    python scripts/test_vix_fetch.py
"""

import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_tradier():
    """Test Tradier VIX fetch"""
    print("\n" + "="*60)
    print("TEST 1: TRADIER ($VIX.X)")
    print("="*60)

    try:
        from data.tradier_data_fetcher import TradierDataFetcher

        sandbox = os.getenv('TRADIER_SANDBOX', 'true').lower() == 'true'
        print(f"  TRADIER_SANDBOX env: {os.getenv('TRADIER_SANDBOX', 'not set')}")
        print(f"  Using: {'SANDBOX (paper)' if sandbox else 'PRODUCTION (live)'}")

        if sandbox:
            print("  ⚠️  WARNING: Sandbox mode may not have VIX data!")
            print("     Set TRADIER_SANDBOX=false in .env for real market data")

        tradier = TradierDataFetcher(sandbox=sandbox)
        quote = tradier.get_quote("$VIX.X")

        if quote:
            print(f"\n  ✅ SUCCESS!")
            print(f"     VIX Last: {quote.get('last')}")
            print(f"     VIX Bid:  {quote.get('bid')}")
            print(f"     VIX Ask:  {quote.get('ask')}")
            return quote.get('last')
        else:
            print(f"\n  ❌ FAILED: Tradier returned empty quote")
            return None

    except Exception as e:
        print(f"\n  ❌ ERROR: {e}")
        return None


def test_yahoo():
    """Test Yahoo Finance VIX fetch"""
    print("\n" + "="*60)
    print("TEST 2: YAHOO FINANCE (^VIX)")
    print("="*60)

    try:
        import yfinance as yf
        print("  yfinance version:", yf.__version__)

        vix = yf.Ticker("^VIX")

        # Method 1: Info
        try:
            info = vix.info
            price = info.get('regularMarketPrice') or info.get('previousClose')
            if price:
                print(f"\n  ✅ SUCCESS (via info)!")
                print(f"     VIX Price: {price}")
                return price
        except Exception as e:
            print(f"  Info method failed: {e}")

        # Method 2: History
        try:
            hist = vix.history(period='5d')
            if not hist.empty:
                price = float(hist['Close'].iloc[-1])
                print(f"\n  ✅ SUCCESS (via history)!")
                print(f"     VIX Last Close: {price:.2f}")
                return price
        except Exception as e:
            print(f"  History method failed: {e}")

        print(f"\n  ❌ FAILED: Yahoo returned no data")
        return None

    except ImportError:
        print("\n  ❌ yfinance not installed!")
        print("     Run: pip install yfinance")
        return None
    except Exception as e:
        print(f"\n  ❌ ERROR: {e}")
        return None


def test_unified_provider():
    """Test unified data provider"""
    print("\n" + "="*60)
    print("TEST 3: UNIFIED DATA PROVIDER")
    print("="*60)

    try:
        from data.unified_data_provider import UnifiedDataProvider

        provider = UnifiedDataProvider()
        vix = provider.get_vix()

        if vix and vix > 0 and vix != 18.0:
            print(f"\n  ✅ SUCCESS!")
            print(f"     VIX: {vix}")
            return vix
        elif vix == 18.0:
            print(f"\n  ⚠️  WARNING: Got fallback value 18.0")
            print("     This means all sources failed!")
            return None
        else:
            print(f"\n  ❌ FAILED: Got {vix}")
            return None

    except Exception as e:
        print(f"\n  ❌ ERROR: {e}")
        return None


def test_vix_route():
    """Test the actual VIX API endpoint"""
    print("\n" + "="*60)
    print("TEST 4: VIX API ENDPOINT (/api/vix/current)")
    print("="*60)

    try:
        import requests

        api_url = os.getenv('API_URL', 'http://localhost:8000')
        response = requests.get(f"{api_url}/api/vix/current", timeout=10)

        if response.status_code == 200:
            data = response.json()
            vix_data = data.get('data', {})
            vix_spot = vix_data.get('vix_spot')
            vix_source = vix_data.get('vix_source')

            print(f"\n  Response: {response.status_code}")
            print(f"     VIX Spot: {vix_spot}")
            print(f"     Source:   {vix_source}")

            if vix_source == 'default':
                print(f"\n  ⚠️  WARNING: Using DEFAULT value!")
                print("     All data sources failed.")
            elif vix_spot and vix_spot != 18.0:
                print(f"\n  ✅ SUCCESS!")
                return vix_spot

            return vix_spot
        else:
            print(f"\n  ❌ FAILED: HTTP {response.status_code}")
            print(f"     {response.text[:200]}")
            return None

    except requests.exceptions.ConnectionError:
        print("\n  ❌ Cannot connect to API server")
        print("     Is the backend running?")
        return None
    except Exception as e:
        print(f"\n  ❌ ERROR: {e}")
        return None


def main():
    print("\n" + "#"*60)
    print("#  VIX PRICE FETCH DIAGNOSTIC")
    print("#"*60)
    print(f"\nExpected VIX: ~14.91 (as reported by user)")

    results = {}

    # Run all tests
    results['tradier'] = test_tradier()
    results['yahoo'] = test_yahoo()
    results['unified'] = test_unified_provider()
    results['api'] = test_vix_route()

    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)

    working = []
    failed = []

    for source, value in results.items():
        if value and value != 18.0:
            working.append(f"{source}: {value}")
        else:
            failed.append(source)

    if working:
        print(f"\n✅ Working sources:")
        for w in working:
            print(f"   - {w}")

    if failed:
        print(f"\n❌ Failed sources:")
        for f in failed:
            print(f"   - {f}")

    # Recommendations
    print("\n" + "-"*60)
    print("RECOMMENDATIONS:")
    print("-"*60)

    if 'tradier' in failed:
        print("""
1. TRADIER: Set TRADIER_SANDBOX=false in .env
   - Sandbox mode doesn't have VIX data
   - You need production API access for VIX
""")

    if 'yahoo' in failed:
        print("""
2. YAHOO FINANCE: Install yfinance
   - Run: pip install yfinance
   - This is FREE and doesn't need API key
""")

    if not working:
        print("""
⚠️  ALL SOURCES FAILED!

Fix priority:
1. Install yfinance: pip install yfinance
2. Or set TRADIER_SANDBOX=false in .env
""")


if __name__ == "__main__":
    main()
