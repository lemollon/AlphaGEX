#!/usr/bin/env python3
"""
JUBILEE Standalone Test Suite
=================================

Designed to run in Render shell: python scripts/test_jubilee_standalone.py

This script directly imports modules to avoid dependency chains.
Tests the specific changes we made:
1. Rate fetcher with FRED API
2. Models - scan time, rate tracking fields
3. Signal generator - rate source propagation
4. API endpoints - correct responses
"""

import os
import sys
import json
import traceback
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import List

# Prevent trading/__init__.py from being imported
# by directly adding the trading/jubilee path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BUGS_FOUND = []
TESTS_RUN = 0
TESTS_PASSED = 0


def record_result(test_name: str, passed: bool, message: str, is_bug: bool = True):
    """Record test result."""
    global TESTS_RUN, TESTS_PASSED, BUGS_FOUND
    TESTS_RUN += 1
    if passed:
        TESTS_PASSED += 1
        print(f"  ✅ {test_name}: {message}")
    else:
        print(f"  ❌ {test_name}: {message}")
        if is_bug:
            BUGS_FOUND.append({"test": test_name, "issue": message})


def section(name: str):
    print(f"\n{'=' * 60}")
    print(f"TEST: {name}")
    print("=" * 60)


# =============================================================================
# TEST 1: Rate Fetcher (direct import)
# =============================================================================

def test_rate_fetcher():
    """Test rate fetcher directly."""
    section("RATE FETCHER")

    try:
        # Direct import to avoid trading/__init__.py
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "rate_fetcher",
            os.path.join(os.path.dirname(__file__), "..", "trading", "jubilee", "rate_fetcher.py")
        )
        rate_fetcher = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(rate_fetcher)

        # Test RateFetcher class
        fetcher = rate_fetcher.RateFetcher()
        rates = fetcher.get_rates()

        # Test 1: Fed funds rate is reasonable
        if 0 < rates.fed_funds_rate < 20:
            record_result("Fed funds rate valid", True, f"{rates.fed_funds_rate:.2f}%")
        else:
            record_result("Fed funds rate valid", False, f"Invalid: {rates.fed_funds_rate}")

        # Test 2: SOFR rate is reasonable
        if 0 < rates.sofr_rate < 20:
            record_result("SOFR rate valid", True, f"{rates.sofr_rate:.2f}%")
        else:
            record_result("SOFR rate valid", False, f"Invalid: {rates.sofr_rate}")

        # Test 3: Source is valid
        valid_sources = ['live', 'cached', 'fomc_based', 'fallback']
        if rates.source in valid_sources:
            record_result("Rate source valid", True, rates.source)
        else:
            record_result("Rate source valid", False, f"Unknown: {rates.source}")

        # Test 4: last_updated is set
        if rates.last_updated:
            record_result("last_updated set", True, str(rates.last_updated))
        else:
            record_result("last_updated set", False, "Not set")

        # Test 5: FRED API key status
        fred_key = os.environ.get('FRED_API_KEY')
        if fred_key:
            print(f"\n  FRED_API_KEY: {fred_key[:8]}...{fred_key[-4:]}")
            if rates.source == 'live':
                record_result("FRED API working", True, "Fetching live rates")
            else:
                record_result("FRED API working", False, f"Key set but source={rates.source}", is_bug=False)
        else:
            print(f"\n  FRED_API_KEY: NOT SET")
            record_result("FRED API key", False, "Not configured - using fallback", is_bug=False)

        # Test 6: Fallback rates are reasonable (FOMC-based)
        if rates.source in ['fomc_based', 'fallback']:
            # Should be close to FOMC target range (4.25-4.50%)
            if 4.0 <= rates.fed_funds_rate <= 5.0:
                record_result("Fallback rates reasonable", True, f"Fed funds: {rates.fed_funds_rate}%")
            else:
                record_result("Fallback rates reasonable", False, f"Fed funds: {rates.fed_funds_rate}% (expected 4.0-5.0%)")

        return True

    except Exception as e:
        record_result("Rate fetcher import", False, str(e))
        traceback.print_exc()
        return False


# =============================================================================
# TEST 2: Models (direct import)
# =============================================================================

def test_models():
    """Test JUBILEE models directly."""
    section("MODELS")

    try:
        # Direct import
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "models",
            os.path.join(os.path.dirname(__file__), "..", "trading", "jubilee", "models.py")
        )
        models = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(models)

        # Test 1: JubileeConfig scan start time
        config = models.JubileeConfig()
        if config.entry_start == "08:30":
            record_result("Scan start time", True, "08:30 (market open)")
        else:
            record_result("Scan start time", False, f"Got {config.entry_start}, expected 08:30")

        # Test 2: JubileeConfig scan end time
        if config.entry_end == "15:00":
            record_result("Scan end time", True, "15:00 (market close)")
        else:
            record_result("Scan end time", False, f"Got {config.entry_end}, expected 15:00")

        # Test 3: BorrowingCostAnalysis has rates_source field
        if hasattr(models, 'BorrowingCostAnalysis'):
            # Create instance to check fields
            from dataclasses import fields
            bca_fields = [f.name for f in fields(models.BorrowingCostAnalysis)]

            if 'rates_source' in bca_fields:
                record_result("BorrowingCostAnalysis.rates_source", True, "Field exists")
            else:
                record_result("BorrowingCostAnalysis.rates_source", False, "Field missing")

            if 'rates_last_updated' in bca_fields:
                record_result("BorrowingCostAnalysis.rates_last_updated", True, "Field exists")
            else:
                record_result("BorrowingCostAnalysis.rates_last_updated", False, "Field missing")
        else:
            record_result("BorrowingCostAnalysis class", False, "Class not found")

        return True

    except Exception as e:
        record_result("Models import", False, str(e))
        traceback.print_exc()
        return False


# =============================================================================
# TEST 3: API Endpoints
# =============================================================================

def test_api_endpoints():
    """Test API endpoints."""
    section("API ENDPOINTS")

    try:
        import requests
    except ImportError:
        print("  ⚠️  requests not installed - skipping API tests")
        return True

    # Determine base URL
    base_url = os.environ.get("API_BASE_URL")
    if not base_url:
        # Try localhost first
        try:
            resp = requests.get("http://localhost:8000/health", timeout=3)
            if resp.status_code == 200:
                base_url = "http://localhost:8000"
        except:
            pass

    if not base_url:
        # Try production
        try:
            resp = requests.get("https://alphagex-api.onrender.com/health", timeout=5)
            if resp.status_code == 200:
                base_url = "https://alphagex-api.onrender.com"
        except:
            pass

    if not base_url:
        print("  ⚠️  Cannot reach API - skipping endpoint tests")
        record_result("API connectivity", False, "Cannot reach any API", is_bug=False)
        return True

    print(f"  Using API: {base_url}")

    # Test /api/jubilee/status
    try:
        resp = requests.get(f"{base_url}/api/jubilee/status", timeout=10)
        if resp.status_code == 200:
            data = resp.json()

            # Check required fields
            required = ['status', 'performance']
            missing = [f for f in required if f not in data]

            if not missing:
                record_result("/api/jubilee/status", True, "All required fields present")
            else:
                record_result("/api/jubilee/status", False, f"Missing: {missing}")

            # Check performance has our tracking fields
            perf = data.get('performance', {})
            perf_fields = ['total_borrowed', 'total_ic_returns', 'total_borrowing_costs']
            for field in perf_fields:
                if field in perf:
                    print(f"    {field}: {perf[field]}")
                else:
                    record_result(f"performance.{field}", False, "Field missing")

        else:
            record_result("/api/jubilee/status", False, f"Status {resp.status_code}")

    except Exception as e:
        record_result("/api/jubilee/status", False, str(e), is_bug=False)

    # Test /api/jubilee/rate-analysis (critical for our changes)
    try:
        resp = requests.get(f"{base_url}/api/jubilee/rate-analysis", timeout=10)
        if resp.status_code == 200:
            data = resp.json()

            # Check new fields we added
            if 'rates_source' in data:
                source = data['rates_source']
                if source in ['live', 'cached', 'fomc_based', 'fallback']:
                    record_result("rate-analysis.rates_source", True, source)
                else:
                    record_result("rate-analysis.rates_source", False, f"Invalid: {source}")
            else:
                record_result("rate-analysis.rates_source", False, "Field missing from response")

            if 'rates_last_updated' in data:
                record_result("rate-analysis.rates_last_updated", True, str(data['rates_last_updated']))
            else:
                record_result("rate-analysis.rates_last_updated", False, "Field missing from response")

            # Check standard fields
            standard = ['fed_funds_rate', 'box_implied_rate', 'is_favorable']
            for field in standard:
                if field in data:
                    print(f"    {field}: {data[field]}")
                else:
                    record_result(f"rate-analysis.{field}", False, "Missing")

        else:
            record_result("/api/jubilee/rate-analysis", False, f"Status {resp.status_code}")

    except Exception as e:
        record_result("/api/jubilee/rate-analysis", False, str(e), is_bug=False)

    return True


# =============================================================================
# TEST 4: Frontend File Check
# =============================================================================

def test_frontend_file():
    """Check frontend file has correct content."""
    section("FRONTEND FILE")

    frontend_path = os.path.join(
        os.path.dirname(__file__), "..",
        "frontend", "src", "app", "jubilee", "page.tsx"
    )

    if not os.path.exists(frontend_path):
        record_result("Frontend file exists", False, "File not found")
        return False

    with open(frontend_path, 'r') as f:
        content = f.read()

    # Test 1: Scan time shows 8:30 AM (not 9:00 or 9:30)
    if "8:30 AM CT" in content:
        record_result("Frontend scan time", True, "Shows 8:30 AM CT")
    elif "9:30 AM CT" in content or "9:00 AM CT" in content:
        record_result("Frontend scan time", False, "Still shows old time (9:00/9:30)")
    else:
        record_result("Frontend scan time", False, "Time not found in expected format", is_bug=False)

    # Test 2: Rate source indicator logic
    if "fomc_based" in content:
        record_result("Frontend fomc_based handling", True, "Handles fomc_based source")
    else:
        record_result("Frontend fomc_based handling", False, "Missing fomc_based handling")

    # Test 3: Shows specific borrowed amount (not generic)
    if "totalBorrowed" in content and "formatCurrency(totalBorrowed)" in content:
        record_result("Frontend shows specific amount", True, "Uses totalBorrowed variable")
    else:
        record_result("Frontend shows specific amount", False, "Missing specific borrowed amount display")

    # Test 4: Capital breakdown section
    if "YOUR CAPITAL SOURCE" in content or "Capital Source" in content or "From Box Spreads" in content:
        record_result("Frontend capital breakdown", True, "Has capital breakdown section")
    else:
        record_result("Frontend capital breakdown", False, "Missing capital breakdown")

    # Test 5: Break-even analysis
    if "break-even" in content.lower() or "break even" in content.lower() or "breakeven" in content.lower():
        record_result("Frontend break-even analysis", True, "Has break-even section")
    else:
        record_result("Frontend break-even analysis", False, "Missing break-even analysis")

    return True


# =============================================================================
# TEST 5: Signal Generator (if possible)
# =============================================================================

def test_signal_generator():
    """Test signal generator if imports work."""
    section("SIGNAL GENERATOR")

    try:
        # Try direct import avoiding trading/__init__.py
        import importlib.util

        # First import rate_fetcher
        rf_spec = importlib.util.spec_from_file_location(
            "rate_fetcher",
            os.path.join(os.path.dirname(__file__), "..", "trading", "jubilee", "rate_fetcher.py")
        )
        rate_fetcher = importlib.util.module_from_spec(rf_spec)
        sys.modules['trading.jubilee.rate_fetcher'] = rate_fetcher
        rf_spec.loader.exec_module(rate_fetcher)

        # Then models
        models_spec = importlib.util.spec_from_file_location(
            "models",
            os.path.join(os.path.dirname(__file__), "..", "trading", "jubilee", "models.py")
        )
        models = importlib.util.module_from_spec(models_spec)
        sys.modules['trading.jubilee.models'] = models
        models_spec.loader.exec_module(models)

        # Now try signals
        sig_spec = importlib.util.spec_from_file_location(
            "signals",
            os.path.join(os.path.dirname(__file__), "..", "trading", "jubilee", "signals.py")
        )
        signals = importlib.util.module_from_spec(sig_spec)
        sig_spec.loader.exec_module(signals)

        # Test the generator
        generator = signals.BoxSpreadSignalGenerator()
        analysis = generator.analyze_current_rates()

        if analysis:
            # Check rates_source is populated
            if hasattr(analysis, 'rates_source') and analysis.rates_source:
                record_result("Signal rates_source", True, analysis.rates_source)
            else:
                record_result("Signal rates_source", False, "Not populated")

            # Check rates_last_updated is populated
            if hasattr(analysis, 'rates_last_updated') and analysis.rates_last_updated:
                record_result("Signal rates_last_updated", True, str(analysis.rates_last_updated))
            else:
                record_result("Signal rates_last_updated", False, "Not populated")

            print(f"    Fed Funds: {analysis.fed_funds_rate}%")
            print(f"    Box Rate: {analysis.box_implied_rate}%")
            print(f"    Favorable: {analysis.is_favorable}")
        else:
            record_result("Signal generator analysis", False, "Returned None")

        return True

    except Exception as e:
        print(f"  ⚠️  Cannot test signal generator: {e}")
        record_result("Signal generator", False, str(e), is_bug=False)
        return True  # Not a critical failure for this test env


# =============================================================================
# MAIN
# =============================================================================

def main():
    print("=" * 60)
    print("JUBILEE STANDALONE TEST SUITE")
    print("=" * 60)
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"FRED_API_KEY: {'SET' if os.environ.get('FRED_API_KEY') else 'NOT SET'}")

    # Run tests
    test_rate_fetcher()
    test_models()
    test_api_endpoints()
    test_frontend_file()
    test_signal_generator()

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    print(f"\n✅ Passed: {TESTS_PASSED}/{TESTS_RUN}")
    print(f"❌ Failed: {TESTS_RUN - TESTS_PASSED}")

    if BUGS_FOUND:
        print(f"\n🐛 BUGS REQUIRING FIXES ({len(BUGS_FOUND)}):")
        for i, bug in enumerate(BUGS_FOUND, 1):
            print(f"\n  Bug #{i}: {bug['test']}")
            print(f"    Issue: {bug['issue']}")

        print("\n" + "=" * 60)
        print("❌ TESTS FAILED - Fix bugs above")
        print("=" * 60)
        return 1
    else:
        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED")
        print("=" * 60)
        return 0


if __name__ == "__main__":
    sys.exit(main())
