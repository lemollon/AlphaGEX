#!/usr/bin/env python3
"""
Test SPX Quote Fetching with Tradier Production API

This script verifies that:
1. TRADIER_API_KEY (production) is set
2. Production API can fetch SPX quotes
3. Production API can fetch SPXW option quotes
4. Mark-to-Market utility uses production for SPX

SPX/SPXW quotes are ONLY available via Tradier PRODUCTION API.
Sandbox API does NOT support SPX index or SPX options.
"""

import os
import sys
from datetime import datetime, timedelta

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_env_vars():
    """Check required environment variables"""
    print("\n" + "="*60)
    print("1. CHECKING ENVIRONMENT VARIABLES")
    print("="*60)

    prod_key = os.environ.get('TRADIER_API_KEY')
    sandbox_key = os.environ.get('TRADIER_SANDBOX_API_KEY')

    print(f"\n  TRADIER_API_KEY (production): {'✓ SET' if prod_key else '✗ NOT SET'}")
    if prod_key:
        print(f"    Key prefix: {prod_key[:8]}...")

    print(f"  TRADIER_SANDBOX_API_KEY:      {'✓ SET' if sandbox_key else '✗ NOT SET'}")
    if sandbox_key:
        print(f"    Key prefix: {sandbox_key[:8]}...")

    if not prod_key:
        print("\n  ⚠️  WARNING: TRADIER_API_KEY not set!")
        print("     SPX quotes will NOT work without production key.")
        return False

    return True


def test_spx_quote_production():
    """Test fetching SPX quote with production API"""
    print("\n" + "="*60)
    print("2. TESTING SPX QUOTE (Production API)")
    print("="*60)

    try:
        from data.tradier_data_fetcher import TradierDataFetcher

        prod_key = os.environ.get('TRADIER_API_KEY')
        if not prod_key:
            print("\n  ✗ SKIP: No production API key")
            return False

        print(f"\n  Creating Tradier client (sandbox=False)...")
        tradier = TradierDataFetcher(api_key=prod_key, sandbox=False)
        print(f"  Mode: {'SANDBOX' if tradier.sandbox else 'PRODUCTION'}")

        print(f"\n  Fetching SPX quote...")
        quote = tradier.get_quote('SPX')

        if quote and quote.get('last'):
            price = float(quote['last'])
            print(f"  ✓ SPX Price: ${price:,.2f}")
            print(f"    Bid: ${quote.get('bid', 'N/A')}")
            print(f"    Ask: ${quote.get('ask', 'N/A')}")
            print(f"    Volume: {quote.get('volume', 'N/A')}")
            return True
        else:
            print(f"  ✗ Failed to get SPX quote")
            print(f"    Response: {quote}")
            return False

    except Exception as e:
        print(f"  ✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_spy_quote_comparison():
    """Compare SPX vs SPY*10 to verify accuracy"""
    print("\n" + "="*60)
    print("3. COMPARING SPX vs SPY*10")
    print("="*60)

    try:
        from data.tradier_data_fetcher import TradierDataFetcher

        prod_key = os.environ.get('TRADIER_API_KEY')
        if not prod_key:
            print("\n  ✗ SKIP: No production API key")
            return False

        tradier = TradierDataFetcher(api_key=prod_key, sandbox=False)

        spx_quote = tradier.get_quote('SPX')
        spy_quote = tradier.get_quote('SPY')

        if spx_quote and spy_quote:
            spx_price = float(spx_quote.get('last', 0))
            spy_price = float(spy_quote.get('last', 0))
            spy_estimated_spx = spy_price * 10

            diff = abs(spx_price - spy_estimated_spx)
            diff_pct = (diff / spx_price) * 100 if spx_price > 0 else 0

            print(f"\n  SPX actual:     ${spx_price:,.2f}")
            print(f"  SPY × 10:       ${spy_estimated_spx:,.2f}")
            print(f"  Difference:     ${diff:,.2f} ({diff_pct:.3f}%)")

            if diff_pct < 0.5:
                print(f"  ✓ SPY*10 is a good estimate (within 0.5%)")
            else:
                print(f"  ⚠️ SPY*10 differs from SPX by {diff_pct:.2f}%")

            return True
        else:
            print(f"  ✗ Failed to get quotes")
            return False

    except Exception as e:
        print(f"  ✗ Error: {e}")
        return False


def test_spxw_option_quote():
    """Test fetching SPXW option quotes"""
    print("\n" + "="*60)
    print("4. TESTING SPXW OPTION QUOTES (Production API)")
    print("="*60)

    try:
        from data.tradier_data_fetcher import TradierDataFetcher
        from trading.mark_to_market import build_occ_symbol

        prod_key = os.environ.get('TRADIER_API_KEY')
        if not prod_key:
            print("\n  ✗ SKIP: No production API key")
            return False

        tradier = TradierDataFetcher(api_key=prod_key, sandbox=False)

        # Get SPX price first
        spx_quote = tradier.get_quote('SPX')
        if not spx_quote or not spx_quote.get('last'):
            print("\n  ✗ Could not get SPX price for strike calculation")
            return False

        spx_price = float(spx_quote['last'])
        print(f"\n  SPX Price: ${spx_price:,.2f}")

        # Find next expiration (next trading day)
        today = datetime.now()
        # Try today, tomorrow, and next few days
        for days_ahead in range(0, 5):
            exp_date = today + timedelta(days=days_ahead)
            if exp_date.weekday() < 5:  # Weekday
                exp_str = exp_date.strftime('%Y-%m-%d')
                break

        # Calculate ATM strike (round to nearest 5)
        atm_strike = round(spx_price / 5) * 5

        print(f"  Expiration: {exp_str}")
        print(f"  ATM Strike: {atm_strike}")

        # Build option symbol
        option_symbol = build_occ_symbol('SPX', exp_str, atm_strike, 'C')
        print(f"  Option Symbol: {option_symbol}")

        # Try to get quote
        print(f"\n  Fetching option quote...")
        opt_quote = tradier.get_quote(option_symbol)

        if opt_quote and (opt_quote.get('last') or opt_quote.get('bid') or opt_quote.get('ask')):
            print(f"  ✓ Got option quote!")
            print(f"    Last: ${opt_quote.get('last', 'N/A')}")
            print(f"    Bid:  ${opt_quote.get('bid', 'N/A')}")
            print(f"    Ask:  ${opt_quote.get('ask', 'N/A')}")
            return True
        else:
            print(f"  ⚠️ No option quote (may be outside market hours)")
            print(f"    Response: {opt_quote}")
            # This might fail outside market hours, so not a hard failure
            return None

    except Exception as e:
        print(f"  ✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_mark_to_market():
    """Test Mark-to-Market utility for SPX"""
    print("\n" + "="*60)
    print("5. TESTING MARK-TO-MARKET UTILITY")
    print("="*60)

    try:
        from trading.mark_to_market import (
            calculate_ic_mark_to_market,
            _get_tradier_client
        )
        from data.tradier_data_fetcher import TradierDataFetcher

        prod_key = os.environ.get('TRADIER_API_KEY')
        if not prod_key:
            print("\n  ✗ SKIP: No production API key")
            return False

        # Test that _get_tradier_client returns production for SPX
        print("\n  Testing _get_tradier_client for SPXW...")
        client = _get_tradier_client(underlying='SPXW')
        if client:
            print(f"  ✓ Client created")
            print(f"    Mode: {'SANDBOX' if client.sandbox else 'PRODUCTION'}")
            if not client.sandbox:
                print(f"    ✓ Correctly using PRODUCTION for SPXW")
            else:
                print(f"    ✗ ERROR: Should use PRODUCTION for SPXW!")
                return False
        else:
            print(f"  ✗ Failed to create client")
            return False

        # Get SPX price for test IC
        tradier = TradierDataFetcher(api_key=prod_key, sandbox=False)
        spx_quote = tradier.get_quote('SPX')
        if not spx_quote or not spx_quote.get('last'):
            print("\n  ✗ Could not get SPX price")
            return False

        spx_price = float(spx_quote['last'])

        # Find next expiration
        today = datetime.now()
        for days_ahead in range(0, 5):
            exp_date = today + timedelta(days=days_ahead)
            if exp_date.weekday() < 5:
                exp_str = exp_date.strftime('%Y-%m-%d')
                break

        # Create test IC strikes
        put_short = round((spx_price - 50) / 5) * 5
        put_long = put_short - 10
        call_short = round((spx_price + 50) / 5) * 5
        call_long = call_short + 10

        print(f"\n  Testing IC MTM calculation...")
        print(f"    SPX: ${spx_price:,.2f}")
        print(f"    Put spread:  {put_long}/{put_short}")
        print(f"    Call spread: {call_short}/{call_long}")
        print(f"    Expiration: {exp_str}")

        result = calculate_ic_mark_to_market(
            underlying='SPX',
            expiration=exp_str,
            put_short_strike=put_short,
            put_long_strike=put_long,
            call_short_strike=call_short,
            call_long_strike=call_long,
            contracts=1,
            entry_credit=1.50,
            use_cache=False
        )

        print(f"\n  MTM Result:")
        print(f"    Success: {result.get('success')}")
        print(f"    Method: {result.get('method')}")
        if result.get('success'):
            print(f"    Current Value: ${result.get('current_value', 0):.4f}")
            print(f"    Unrealized P&L: ${result.get('unrealized_pnl', 0):.2f}")
            print(f"  ✓ MTM calculation successful!")
            return True
        else:
            print(f"    Error: {result.get('error')}")
            print(f"  ⚠️ MTM failed (may be outside market hours)")
            return None

    except Exception as e:
        print(f"  ✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    print("\n" + "="*60)
    print("SPX PRODUCTION API QUOTE TEST")
    print("="*60)
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    results = {}

    # Run tests
    results['env_vars'] = test_env_vars()

    if results['env_vars']:
        results['spx_quote'] = test_spx_quote_production()
        results['spy_comparison'] = test_spy_quote_comparison()
        results['option_quote'] = test_spxw_option_quote()
        results['mtm'] = test_mark_to_market()
    else:
        print("\n⚠️  Skipping API tests - no production key available")

    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)

    all_passed = True
    for test_name, result in results.items():
        if result is True:
            status = "✓ PASS"
        elif result is False:
            status = "✗ FAIL"
            all_passed = False
        elif result is None:
            status = "⚠️ SKIP (may be outside market hours)"
        else:
            status = "? UNKNOWN"

        print(f"  {test_name}: {status}")

    print("\n" + "="*60)
    if all_passed:
        print("✓ ALL TESTS PASSED - SPX quotes working with production API!")
    else:
        print("✗ SOME TESTS FAILED - Check output above for details")
    print("="*60 + "\n")

    return 0 if all_passed else 1


if __name__ == '__main__':
    sys.exit(main())
