#!/usr/bin/env python3
"""
JUBILEE Tradier Verification Script
=======================================

Run this on Render shell to verify JUBILEE is getting LIVE SPX data:
    python scripts/verify_jubilee_tradier.py

This script tests:
1. Environment variables are set
2. Tradier PRODUCTION client initializes correctly
3. SPX quotes are returned (not available in sandbox)
4. Box spread pricing works with real data
"""

import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime

# Colors for output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'
BOLD = '\033[1m'

def print_header(text):
    print(f"\n{BOLD}{BLUE}{'=' * 60}{RESET}")
    print(f"{BOLD}{BLUE}{text}{RESET}")
    print(f"{BOLD}{BLUE}{'=' * 60}{RESET}\n")

def print_result(test_name, passed, details=""):
    icon = f"{GREEN}PASS{RESET}" if passed else f"{RED}FAIL{RESET}"
    print(f"  [{icon}] {test_name}")
    if details:
        print(f"         {details}")

def main():
    print(f"\n{BOLD}JUBILEE TRADIER VERIFICATION{RESET}")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    results = {"passed": 0, "failed": 0}

    # ================================================================
    print_header("1. ENVIRONMENT VARIABLES")
    # ================================================================

    tradier_key = os.environ.get('TRADIER_API_KEY')
    tradier_prod_key = os.environ.get('TRADIER_PROD_API_KEY')
    sandbox_key = os.environ.get('TRADIER_SANDBOX_API_KEY')

    has_prod_key = bool(tradier_key or tradier_prod_key)
    print_result(
        "Production API Key",
        has_prod_key,
        f"TRADIER_API_KEY={'****' + tradier_key[-4:] if tradier_key else 'NOT SET'}, "
        f"TRADIER_PROD_API_KEY={'****' + tradier_prod_key[-4:] if tradier_prod_key else 'NOT SET'}"
    )

    if has_prod_key:
        results["passed"] += 1
    else:
        results["failed"] += 1
        print(f"\n{RED}CRITICAL: No production Tradier API key found!{RESET}")
        print("Set TRADIER_API_KEY in Render environment variables.")
        return 1

    # ================================================================
    print_header("2. TRADIER CLIENT INITIALIZATION")
    # ================================================================

    try:
        from data.tradier_data_fetcher import TradierDataFetcher

        prod_key = tradier_prod_key or tradier_key
        client = TradierDataFetcher(api_key=prod_key, sandbox=False)

        print_result(
            "TradierDataFetcher Created",
            True,
            f"Mode: PRODUCTION, Base URL: {client.base_url}"
        )
        results["passed"] += 1

    except Exception as e:
        print_result("TradierDataFetcher Created", False, str(e))
        results["failed"] += 1
        return 1

    # ================================================================
    print_header("3. SPX QUOTE TEST (Production Only)")
    # ================================================================

    try:
        spx_quote = client.get_quote('SPX')

        if spx_quote and spx_quote.get('last'):
            spx_price = spx_quote['last']
            print_result(
                "SPX Quote Retrieved",
                True,
                f"SPX = ${spx_price:,.2f} (last), bid=${spx_quote.get('bid', 'N/A')}, ask=${spx_quote.get('ask', 'N/A')}"
            )
            results["passed"] += 1
        else:
            print_result(
                "SPX Quote Retrieved",
                False,
                f"Response: {spx_quote}"
            )
            results["failed"] += 1
            print(f"\n{RED}SPX quotes require PRODUCTION Tradier API!{RESET}")
            print("Sandbox API does NOT provide SPX data.")

    except Exception as e:
        print_result("SPX Quote Retrieved", False, str(e))
        results["failed"] += 1

    # ================================================================
    print_header("4. VIX QUOTE TEST")
    # ================================================================

    try:
        vix_quote = client.get_quote('VIX')

        if vix_quote and vix_quote.get('last'):
            vix_price = vix_quote['last']
            print_result(
                "VIX Quote Retrieved",
                True,
                f"VIX = {vix_price:.2f}"
            )
            results["passed"] += 1
        else:
            print_result("VIX Quote Retrieved", False, f"Response: {vix_quote}")
            results["failed"] += 1

    except Exception as e:
        print_result("VIX Quote Retrieved", False, str(e))
        results["failed"] += 1

    # ================================================================
    print_header("5. JUBILEE SIGNAL GENERATOR TEST")
    # ================================================================

    try:
        from trading.jubilee.signals import _get_tradier, BoxSpreadSignalGenerator

        # Test lazy-loaded client
        tradier = _get_tradier()
        print_result(
            "_get_tradier() Returns Client",
            tradier is not None,
            f"Type: {type(tradier).__name__}" if tradier else "None returned"
        )

        if tradier:
            results["passed"] += 1

            # Test market data fetch
            generator = BoxSpreadSignalGenerator()
            market_data = generator._get_market_data()

            if market_data and market_data.get('spot_price'):
                print_result(
                    "BoxSpreadSignalGenerator._get_market_data()",
                    True,
                    f"spot=${market_data['spot_price']:,.2f}, source={market_data.get('source')}"
                )
                results["passed"] += 1
            else:
                print_result(
                    "BoxSpreadSignalGenerator._get_market_data()",
                    False,
                    f"Response: {market_data}"
                )
                results["failed"] += 1
        else:
            results["failed"] += 1

    except Exception as e:
        print_result("JUBILEE Signal Generator", False, str(e))
        results["failed"] += 1

    # ================================================================
    print_header("6. JUBILEE IC SIGNAL GENERATOR TEST")
    # ================================================================

    try:
        from trading.jubilee.signals import PrometheusICSignalGenerator

        ic_generator = PrometheusICSignalGenerator()
        ic_market_data = ic_generator.get_market_data()

        if ic_market_data and ic_market_data.get('spot_price'):
            print_result(
                "PrometheusICSignalGenerator.get_market_data()",
                True,
                f"spot=${ic_market_data['spot_price']:,.2f}, vix={ic_market_data.get('vix')}"
            )
            results["passed"] += 1
        else:
            print_result(
                "PrometheusICSignalGenerator.get_market_data()",
                False,
                f"Response: {ic_market_data}"
            )
            results["failed"] += 1

    except Exception as e:
        print_result("JUBILEE IC Signal Generator", False, str(e))
        results["failed"] += 1

    # ================================================================
    print_header("SUMMARY")
    # ================================================================

    total = results["passed"] + results["failed"]
    print(f"  Passed: {GREEN}{results['passed']}{RESET}/{total}")
    print(f"  Failed: {RED}{results['failed']}{RESET}/{total}")

    if results["failed"] == 0:
        print(f"\n{GREEN}{BOLD}ALL TESTS PASSED! JUBILEE is using LIVE SPX data.{RESET}")
        return 0
    else:
        print(f"\n{RED}{BOLD}SOME TESTS FAILED! Check configuration above.{RESET}")
        return 1


if __name__ == '__main__':
    sys.exit(main())
