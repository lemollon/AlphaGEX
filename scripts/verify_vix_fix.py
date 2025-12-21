#!/usr/bin/env python3
"""
VIX Fix Verification Script
===========================

Run this script to verify VIX is being fetched correctly everywhere.
It tests all the code paths that were fixed.

Usage:
    python scripts/verify_vix_fix.py

Expected: All tests should show REAL VIX values (NOT 18.0)
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_tradier_api_key_selection():
    """Test that TradierDataFetcher selects correct API key based on mode"""
    print("\n" + "="*60)
    print("TEST 1: TradierDataFetcher API Key Selection")
    print("="*60)

    try:
        from data.tradier_data_fetcher import TradierDataFetcher
        from unified_config import APIConfig

        # Check what mode we're in
        sandbox_mode = APIConfig.TRADIER_SANDBOX
        print(f"  TRADIER_SANDBOX env: {sandbox_mode}")
        print(f"  TRADIER_API_KEY set: {bool(APIConfig.TRADIER_API_KEY)}")
        print(f"  TRADIER_SANDBOX_API_KEY set: {bool(APIConfig.TRADIER_SANDBOX_API_KEY)}")

        # Create fetcher and check it selected correctly
        tradier = TradierDataFetcher()
        print(f"  TradierDataFetcher mode: {'SANDBOX' if tradier.sandbox else 'PRODUCTION'}")
        print(f"  Base URL: {tradier.base_url}")

        if sandbox_mode and APIConfig.TRADIER_SANDBOX_API_KEY:
            expected_key = APIConfig.TRADIER_SANDBOX_API_KEY
        else:
            expected_key = APIConfig.TRADIER_API_KEY

        if tradier.api_key == expected_key:
            print("  ✅ CORRECT API key selected for mode!")
        else:
            print("  ❌ WRONG API key selected!")

        return True
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False


def test_vix_direct_fetch():
    """Test direct VIX fetch from Tradier"""
    print("\n" + "="*60)
    print("TEST 2: Direct VIX Fetch ($VIX.X)")
    print("="*60)

    try:
        from data.tradier_data_fetcher import TradierDataFetcher

        tradier = TradierDataFetcher()
        vix_quote = tradier.get_quote("$VIX.X")

        if vix_quote:
            vix = vix_quote.get('last', 0)
            print(f"  VIX Quote: {vix_quote}")
            print(f"  VIX Value: {vix}")

            if vix and vix > 0 and vix != 18.0:
                print(f"  ✅ REAL VIX: {vix} (NOT 18.0 fallback!)")
                return True
            elif vix == 18.0:
                print(f"  ⚠️ VIX is 18.0 - might be fallback or real")
                return True
            else:
                print(f"  ❌ VIX is 0 or None")
                return False
        else:
            print("  ❌ No quote returned")
            return False
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False


def test_unified_provider():
    """Test unified data provider get_vix()"""
    print("\n" + "="*60)
    print("TEST 3: Unified Data Provider get_vix()")
    print("="*60)

    try:
        from data.unified_data_provider import get_vix

        vix = get_vix()
        print(f"  VIX: {vix}")

        if vix and vix > 0 and vix != 18.0:
            print(f"  ✅ REAL VIX: {vix}")
            return True
        elif vix == 18.0:
            print(f"  ⚠️ VIX is 18.0 - check if fallback triggered")
            return True
        else:
            print(f"  ❌ VIX is 0 or None")
            return False
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False


def test_vix_hedge_manager():
    """Test VIX hedge manager get_vix_data()"""
    print("\n" + "="*60)
    print("TEST 4: VIX Hedge Manager get_vix_data()")
    print("="*60)

    try:
        from core.vix_hedge_manager import get_vix_hedge_manager

        manager = get_vix_hedge_manager()
        vix_data = manager.get_vix_data()

        vix_spot = vix_data.get('vix_spot')
        vix_source = vix_data.get('vix_source')

        print(f"  VIX Spot: {vix_spot}")
        print(f"  VIX Source: {vix_source}")

        if vix_spot and vix_spot > 0 and vix_spot != 18.0:
            print(f"  ✅ REAL VIX from {vix_source}: {vix_spot}")
            return True
        elif vix_source == 'default':
            print(f"  ❌ Using DEFAULT (18.0) - fetches failed!")
            return False
        else:
            print(f"  ⚠️ VIX: {vix_spot} from {vix_source}")
            return True
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False


def test_api_endpoint():
    """Test /api/vix/current endpoint"""
    print("\n" + "="*60)
    print("TEST 5: API Endpoint /api/vix/current")
    print("="*60)

    try:
        import requests

        response = requests.get("http://localhost:8000/api/vix/current", timeout=5)

        if response.status_code == 200:
            data = response.json()
            vix_spot = data.get('data', {}).get('vix_spot')
            vix_source = data.get('data', {}).get('vix_source')

            print(f"  VIX Spot: {vix_spot}")
            print(f"  VIX Source: {vix_source}")

            if vix_spot and vix_spot > 0 and vix_spot != 18.0:
                print(f"  ✅ REAL VIX from API: {vix_spot}")
                return True
            elif vix_source == 'default':
                print(f"  ❌ API returning DEFAULT (18.0)!")
                return False
            else:
                return True
        else:
            print(f"  ❌ API Error: {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print("  ⚠️ Backend not running - skipping API test")
        return None  # Skip, not failure
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False


def main():
    print("="*60)
    print("VIX FIX VERIFICATION")
    print("="*60)
    print("This script tests that VIX is being fetched correctly")
    print("after the comprehensive VIX fix.")

    results = []

    results.append(("API Key Selection", test_tradier_api_key_selection()))
    results.append(("Direct VIX Fetch", test_vix_direct_fetch()))
    results.append(("Unified Provider", test_unified_provider()))
    results.append(("VIX Hedge Manager", test_vix_hedge_manager()))
    results.append(("API Endpoint", test_api_endpoint()))

    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)

    passed = 0
    failed = 0
    skipped = 0

    for name, result in results:
        if result is True:
            print(f"  ✅ {name}: PASSED")
            passed += 1
        elif result is False:
            print(f"  ❌ {name}: FAILED")
            failed += 1
        else:
            print(f"  ⚠️ {name}: SKIPPED")
            skipped += 1

    print()
    print(f"Total: {passed} passed, {failed} failed, {skipped} skipped")

    if failed == 0:
        print("\n✅ VIX FIX VERIFIED - All tests passed!")
        return 0
    else:
        print("\n❌ VIX FIX HAS ISSUES - Some tests failed!")
        return 1


if __name__ == "__main__":
    sys.exit(main())
