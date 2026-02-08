#!/usr/bin/env python3
"""
Test script to place a test order on the second FORTRESS sandbox account.

This verifies the second account can actually receive orders.

Usage:
    python scripts/test_ares_mirror_order.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def test_second_account_order():
    """Test placing an order directly on the second account."""
    print("\n" + "=" * 60)
    print("  TESTING ORDER PLACEMENT ON SECOND ACCOUNT")
    print("=" * 60)

    # Get second account credentials
    api_key_2 = os.getenv('TRADIER_FORTRESS_SANDBOX_API_KEY_2')
    account_id_2 = os.getenv('TRADIER_FORTRESS_SANDBOX_ACCOUNT_ID_2')

    if not api_key_2 or not account_id_2:
        print("\n[FAIL] Second account credentials not set")
        return False

    print(f"\n  API Key: {api_key_2[:4]}...{api_key_2[-4:]}")
    print(f"  Account: {account_id_2}")

    try:
        from data.tradier_data_fetcher import TradierDataFetcher

        # Initialize with explicit credentials
        print("\n  Initializing TradierDataFetcher with second account...")
        tradier_2 = TradierDataFetcher(
            api_key=api_key_2,
            account_id=account_id_2,
            sandbox=True
        )

        # Verify which account is being used
        print(f"  tradier_2.api_key: {tradier_2.api_key[:4]}...{tradier_2.api_key[-4:]}")
        print(f"  tradier_2.account_id: {tradier_2.account_id}")

        # Check if account_id matches what we passed
        if tradier_2.account_id != account_id_2:
            print(f"\n  [FAIL] Account ID mismatch!")
            print(f"    Expected: {account_id_2}")
            print(f"    Got: {tradier_2.account_id}")
            return False
        else:
            print(f"\n  [OK] Account ID matches: {account_id_2}")

        # Get SPY quote
        print("\n  Getting SPY quote...")
        quote = tradier_2.get_quote("SPY")
        if not quote or not quote.get('last'):
            print("  [FAIL] Could not get SPY quote")
            return False

        spy_price = quote['last']
        print(f"  SPY price: ${spy_price:.2f}")

        # Get today's expiration
        from datetime import datetime, timedelta
        today = datetime.now().strftime('%Y-%m-%d')

        # Get expirations
        expirations = tradier_2.get_options_expirations("SPY")
        if not expirations:
            print("  [FAIL] Could not get expirations")
            return False

        # Use closest expiration
        exp = expirations[0]
        print(f"  Using expiration: {exp}")

        # Calculate strikes for a safe test IC (far OTM)
        put_long = round(spy_price - 20, 0)
        put_short = round(spy_price - 15, 0)
        call_short = round(spy_price + 15, 0)
        call_long = round(spy_price + 20, 0)

        print(f"\n  Test Iron Condor strikes:")
        print(f"    Put spread: {put_long}/{put_short}")
        print(f"    Call spread: {call_short}/{call_long}")

        # Place a test IC order with very low limit (won't fill)
        print(f"\n  Placing test IC order on account {account_id_2}...")
        print("  (Using $0.01 limit - will NOT fill, just tests order placement)")

        result = tradier_2.place_iron_condor(
            symbol="SPY",
            expiration=exp,
            put_long=put_long,
            put_short=put_short,
            call_short=call_short,
            call_long=call_long,
            quantity=1,
            limit_price=0.01  # Won't fill - just testing
        )

        if result and result.get('order'):
            order_id = result['order'].get('id')
            status = result['order'].get('status')
            print(f"\n  [OK] Order placed successfully!")
            print(f"    Order ID: {order_id}")
            print(f"    Status: {status}")

            # Cancel the test order
            print(f"\n  Cancelling test order {order_id}...")
            try:
                cancel_result = tradier_2.cancel_order(order_id)
                print(f"  [OK] Order cancelled")
            except Exception as e:
                print(f"  [WARN] Could not cancel order: {e}")

            return True
        else:
            print(f"\n  [FAIL] Order placement failed: {result}")
            return False

    except Exception as e:
        print(f"\n  [FAIL] Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def check_fortress_executor_accounts():
    """Check what accounts the FORTRESS executor is using."""
    print("\n" + "=" * 60)
    print("  CHECKING FORTRESS EXECUTOR ACCOUNT CONFIGURATION")
    print("=" * 60)

    try:
        from trading.fortress_v2.models import FortressConfig, TradingMode
        from trading.fortress_v2.executor import OrderExecutor

        config = FortressConfig(mode=TradingMode.LIVE)
        executor = OrderExecutor(config)

        print("\n  Primary Tradier:")
        if executor.tradier:
            print(f"    API Key: {executor.tradier.api_key[:4]}...{executor.tradier.api_key[-4:]}")
            print(f"    Account: {executor.tradier.account_id}")
        else:
            print("    [NOT INITIALIZED]")

        print("\n  Second Tradier (Mirror):")
        if executor.tradier_2:
            print(f"    API Key: {executor.tradier_2.api_key[:4]}...{executor.tradier_2.api_key[-4:]}")
            print(f"    Account: {executor.tradier_2.account_id}")
        else:
            print("    [NOT INITIALIZED]")

        # Check if they're different
        if executor.tradier and executor.tradier_2:
            if executor.tradier.account_id == executor.tradier_2.account_id:
                print("\n  [WARN] Both accounts have the SAME account_id!")
                print("         This means trades will go to the same account twice.")
            else:
                print(f"\n  [OK] Accounts are different:")
                print(f"       Primary: {executor.tradier.account_id}")
                print(f"       Mirror:  {executor.tradier_2.account_id}")

        return True

    except Exception as e:
        print(f"\n  [FAIL] Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    print("\n" + "=" * 60)
    print("  FORTRESS MIRROR ORDER TEST")
    print("=" * 60)

    # Test 1: Check FORTRESS executor account configuration
    check_fortress_executor_accounts()

    # Test 2: Place actual test order on second account
    success = test_second_account_order()

    print("\n" + "=" * 60)
    if success:
        print("  RESULT: Second account CAN receive orders")
    else:
        print("  RESULT: Second account order placement FAILED")
    print("=" * 60 + "\n")

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
