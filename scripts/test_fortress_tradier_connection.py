#!/usr/bin/env python3
"""
FORTRESS-Tradier Connection Test Script
====================================

Run this in Render shell to verify FORTRESS can communicate with Tradier.

Usage:
    python scripts/test_fortress_tradier_connection.py          # Test connection only
    python scripts/test_fortress_tradier_connection.py --trade  # Test with a real trade

Tests:
1. Credentials loaded correctly
2. Tradier API connection works
3. Account balance fetched
4. Positions can be retrieved
5. (Optional) Place a test Iron Condor trade
"""

import os
import sys
import argparse
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def print_header(title):
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def print_result(test_name, success, details=""):
    status = "✅ PASS" if success else "❌ FAIL"
    print(f"\n{status}: {test_name}")
    if details:
        print(f"       {details}")


def test_credentials():
    """Test 1: Check if credentials are configured"""
    print_header("TEST 1: Credentials Configuration")

    try:
        from unified_config import APIConfig

        sandbox_key = getattr(APIConfig, 'TRADIER_SANDBOX_API_KEY', None)
        sandbox_account = getattr(APIConfig, 'TRADIER_SANDBOX_ACCOUNT_ID', None)
        prod_key = getattr(APIConfig, 'TRADIER_PROD_API_KEY', None)
        prod_account = getattr(APIConfig, 'TRADIER_PROD_ACCOUNT_ID', None)
        use_sandbox = getattr(APIConfig, 'TRADIER_SANDBOX', True)

        print(f"\n  TRADIER_SANDBOX_API_KEY:    {'SET (' + sandbox_key[:8] + '...)' if sandbox_key else 'NOT SET'}")
        print(f"  TRADIER_SANDBOX_ACCOUNT_ID: {sandbox_account or 'NOT SET'}")
        print(f"  TRADIER_PROD_API_KEY:       {'SET (' + prod_key[:8] + '...)' if prod_key else 'NOT SET'}")
        print(f"  TRADIER_PROD_ACCOUNT_ID:    {prod_account or 'NOT SET'}")
        print(f"  TRADIER_SANDBOX:            {use_sandbox}")

        # Determine which credentials will be used
        api_key = sandbox_key or prod_key
        account_id = sandbox_account or prod_account

        if api_key and account_id:
            print_result("Credentials configured", True, f"Using account: {account_id}")
            return True, api_key, account_id, use_sandbox
        else:
            print_result("Credentials configured", False, "Missing API key or account ID")
            return False, None, None, use_sandbox

    except Exception as e:
        print_result("Credentials configured", False, str(e))
        return False, None, None, True


def test_tradier_import():
    """Test 2: Check if TradierDataFetcher can be imported"""
    print_header("TEST 2: TradierDataFetcher Import")

    # Method 1: Standard import
    try:
        from data.tradier_data_fetcher import TradierDataFetcher
        print_result("Standard import (data.tradier_data_fetcher)", True)
        return True, TradierDataFetcher
    except ImportError as e:
        print(f"\n  Standard import failed: {e}")

    # Method 2: Direct import
    try:
        import importlib.util
        from pathlib import Path

        project_root = Path(__file__).parent.parent
        tradier_path = project_root / 'data' / 'tradier_data_fetcher.py'

        if tradier_path.exists():
            spec = importlib.util.spec_from_file_location("tradier_direct", str(tradier_path))
            tradier_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(tradier_module)
            TradierDataFetcher = tradier_module.TradierDataFetcher
            print_result("Direct file import", True, f"Loaded from {tradier_path}")
            return True, TradierDataFetcher
        else:
            print_result("Direct file import", False, f"File not found: {tradier_path}")
            return False, None
    except Exception as e:
        print_result("Direct file import", False, str(e))
        return False, None


def test_connection(TradierDataFetcher, api_key, account_id, sandbox):
    """Test 3: Test actual Tradier API connection"""
    print_header("TEST 3: Tradier API Connection")

    try:
        tradier = TradierDataFetcher(
            api_key=api_key,
            account_id=account_id,
            sandbox=sandbox
        )

        print(f"\n  Base URL: {tradier.base_url}")
        print(f"  Account:  {tradier.account_id}")
        print(f"  Sandbox:  {tradier.sandbox}")

        print_result("Tradier client created", True)
        return True, tradier
    except Exception as e:
        print_result("Tradier client created", False, str(e))
        return False, None


def test_balance(tradier):
    """Test 4: Fetch account balance"""
    print_header("TEST 4: Account Balance")

    try:
        balance = tradier.get_account_balance()

        if balance:
            total_equity = balance.get('total_equity', 0)
            option_bp = balance.get('option_buying_power', 0)

            print(f"\n  Total Equity:       ${total_equity:,.2f}")
            print(f"  Option Buying Power: ${option_bp:,.2f}")
            print(f"  Account Type:        {balance.get('account_type', 'N/A')}")

            if total_equity > 0:
                print_result("Balance fetched", True, f"${total_equity:,.2f}")
                return True, total_equity
            else:
                print_result("Balance fetched", False, "Total equity is $0")
                return False, 0
        else:
            print_result("Balance fetched", False, "Empty response")
            return False, 0
    except Exception as e:
        print_result("Balance fetched", False, str(e))
        return False, 0


def test_positions(tradier):
    """Test 5: Fetch current positions"""
    print_header("TEST 5: Current Positions")

    try:
        positions = tradier.get_positions()

        print(f"\n  Open Positions: {len(positions)}")

        for pos in positions[:5]:  # Show first 5
            print(f"    - {pos.symbol}: {pos.quantity} @ ${pos.cost_basis:.2f}")

        if len(positions) > 5:
            print(f"    ... and {len(positions) - 5} more")

        print_result("Positions fetched", True, f"{len(positions)} positions")
        return True, positions
    except Exception as e:
        print_result("Positions fetched", False, str(e))
        return False, []


def test_spy_quote(tradier):
    """Test 6: Fetch SPY quote"""
    print_header("TEST 6: SPY Quote")

    try:
        quote = tradier.get_quote('SPY')

        if quote:
            print(f"\n  SPY Last:   ${quote.get('last', 0):.2f}")
            print(f"  SPY Bid:    ${quote.get('bid', 0):.2f}")
            print(f"  SPY Ask:    ${quote.get('ask', 0):.2f}")
            print(f"  SPY Volume: {quote.get('volume', 0):,}")

            print_result("SPY quote fetched", True, f"${quote.get('last', 0):.2f}")
            return True, quote
        else:
            print_result("SPY quote fetched", False, "Empty response")
            return False, None
    except Exception as e:
        print_result("SPY quote fetched", False, str(e))
        return False, None


def test_options_chain(tradier):
    """Test 7: Fetch SPY options chain"""
    print_header("TEST 7: SPY Options Chain (0DTE)")

    try:
        from datetime import datetime
        today = datetime.now().strftime('%Y-%m-%d')

        chain = tradier.get_options_chain('SPY', today)

        if chain:
            calls = [o for o in chain if o.get('option_type') == 'call']
            puts = [o for o in chain if o.get('option_type') == 'put']

            print(f"\n  Expiration: {today}")
            print(f"  Calls:      {len(calls)}")
            print(f"  Puts:       {len(puts)}")

            print_result("Options chain fetched", True, f"{len(chain)} options")
            return True, chain
        else:
            print_result("Options chain fetched", False, "Empty response (market may be closed)")
            return False, None
    except Exception as e:
        print_result("Options chain fetched", False, str(e))
        return False, None


def test_place_trade(tradier, spy_price):
    """Test 8: Place a test Iron Condor trade (DANGEROUS - real money!)"""
    print_header("TEST 8: Place Test Iron Condor Trade")

    print("\n  ⚠️  WARNING: This will place a REAL trade!")
    print("  ⚠️  Only run this during market hours with sufficient buying power")

    confirm = input("\n  Type 'YES' to proceed: ")
    if confirm != 'YES':
        print("\n  Trade cancelled.")
        return False, None

    try:
        from trading.fortress_v2 import FortressTrader

        # Initialize FORTRESS
        trader = FortressTrader()

        print(f"\n  FORTRESS initialized in {trader.config.mode.value} mode")
        print(f"  Ticker: {trader.config.ticker}")

        # Run a single cycle
        print("\n  Running FORTRESS cycle...")
        result = trader.run_cycle()

        print(f"\n  Result: {result.get('action', 'none')}")

        if result.get('trade_opened'):
            position = result.get('details', {}).get('position', {})
            print(f"\n  ✅ TRADE OPENED!")
            print(f"     Position ID: {position.get('position_id', 'N/A')}")
            print(f"     Put Spread:  {position.get('put_long_strike')}/{position.get('put_short_strike')}P")
            print(f"     Call Spread: {position.get('call_short_strike')}/{position.get('call_long_strike')}C")
            print(f"     Contracts:   {position.get('contracts', 0)}")
            print(f"     Credit:      ${position.get('total_credit', 0):.2f}")
            print_result("Trade placed", True)
            return True, result
        else:
            reason = result.get('details', {}).get('skip_reason', 'Unknown')
            print(f"\n  Trade not opened: {reason}")
            print_result("Trade placed", False, reason)
            return False, result

    except Exception as e:
        print_result("Trade placed", False, str(e))
        import traceback
        traceback.print_exc()
        return False, None


def main():
    parser = argparse.ArgumentParser(description='Test FORTRESS-Tradier connection')
    parser.add_argument('--trade', action='store_true', help='Also test placing a trade (DANGEROUS)')
    args = parser.parse_args()

    print("\n" + "=" * 60)
    print("  FORTRESS-TRADIER CONNECTION TEST")
    print("  " + datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    print("=" * 60)

    results = {}

    # Test 1: Credentials
    success, api_key, account_id, sandbox = test_credentials()
    results['credentials'] = success
    if not success:
        print("\n❌ Cannot continue without credentials")
        return

    # Test 2: Import
    success, TradierDataFetcher = test_tradier_import()
    results['import'] = success
    if not success:
        print("\n❌ Cannot continue without TradierDataFetcher")
        return

    # Test 3: Connection
    success, tradier = test_connection(TradierDataFetcher, api_key, account_id, sandbox)
    results['connection'] = success
    if not success:
        print("\n❌ Cannot continue without Tradier connection")
        return

    # Test 4: Balance
    success, balance = test_balance(tradier)
    results['balance'] = success

    # Test 5: Positions
    success, positions = test_positions(tradier)
    results['positions'] = success

    # Test 6: SPY Quote
    success, quote = test_spy_quote(tradier)
    results['quote'] = success
    spy_price = quote.get('last', 0) if quote else 0

    # Test 7: Options Chain
    success, chain = test_options_chain(tradier)
    results['options'] = success

    # Test 8: Place Trade (optional)
    if args.trade:
        success, trade_result = test_place_trade(tradier, spy_price)
        results['trade'] = success

    # Summary
    print_header("SUMMARY")

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    print(f"\n  Tests passed: {passed}/{total}")
    print()

    for test, success in results.items():
        status = "✅" if success else "❌"
        print(f"  {status} {test}")

    if passed == total:
        print("\n  🎉 All tests passed! FORTRESS-Tradier connection is working.")
    else:
        print("\n  ⚠️  Some tests failed. Check the output above for details.")


if __name__ == '__main__':
    main()
