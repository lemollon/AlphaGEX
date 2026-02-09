#!/usr/bin/env python3
"""
Force a test trade on FORTRESS second Tradier sandbox account.

This script verifies the second sandbox account can receive and execute orders
after deployment. It places a real Iron Condor on the second account using
far-OTM strikes so it fills at minimal cost.

Usage:
    python scripts/force_fortress_trade_account2.py

Environment Variables (checks both new and legacy names):
    TRADIER_FORTRESS_SANDBOX_API_KEY_2 or TRADIER_ARES_SANDBOX_API_KEY_2
    TRADIER_FORTRESS_SANDBOX_ACCOUNT_ID_2 or TRADIER_ARES_SANDBOX_ACCOUNT_ID_2
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def get_second_account_credentials():
    """Get second account credentials, checking both new and legacy env var names."""
    api_key = os.getenv('TRADIER_FORTRESS_SANDBOX_API_KEY_2') or os.getenv('TRADIER_ARES_SANDBOX_API_KEY_2')
    account_id = os.getenv('TRADIER_FORTRESS_SANDBOX_ACCOUNT_ID_2') or os.getenv('TRADIER_ARES_SANDBOX_ACCOUNT_ID_2')

    # Show which env var name was found
    if os.getenv('TRADIER_FORTRESS_SANDBOX_API_KEY_2'):
        print("  Found key via: TRADIER_FORTRESS_SANDBOX_API_KEY_2")
    elif os.getenv('TRADIER_ARES_SANDBOX_API_KEY_2'):
        print("  Found key via: TRADIER_ARES_SANDBOX_API_KEY_2 (legacy name)")

    if os.getenv('TRADIER_FORTRESS_SANDBOX_ACCOUNT_ID_2'):
        print("  Found account via: TRADIER_FORTRESS_SANDBOX_ACCOUNT_ID_2")
    elif os.getenv('TRADIER_ARES_SANDBOX_ACCOUNT_ID_2'):
        print("  Found account via: TRADIER_ARES_SANDBOX_ACCOUNT_ID_2 (legacy name)")

    return api_key, account_id


def force_trade_on_second_account():
    """Force a real Iron Condor trade on the second sandbox account."""
    print("\n" + "=" * 70)
    print("  FORCE TRADE ON FORTRESS SECOND SANDBOX ACCOUNT")
    print("=" * 70)

    # Step 1: Get credentials
    print("\n[1/5] Checking credentials...")
    api_key_2, account_id_2 = get_second_account_credentials()

    if not api_key_2 or not account_id_2:
        print("\n  [FAIL] Second account credentials not found!")
        print("  Set one of these pairs:")
        print("    TRADIER_FORTRESS_SANDBOX_API_KEY_2 + TRADIER_FORTRESS_SANDBOX_ACCOUNT_ID_2")
        print("    TRADIER_ARES_SANDBOX_API_KEY_2 + TRADIER_ARES_SANDBOX_ACCOUNT_ID_2")
        return False

    print(f"  API Key: {api_key_2[:6]}...{api_key_2[-4:]}")
    print(f"  Account: {account_id_2}")

    # Step 2: Initialize Tradier client
    print("\n[2/5] Initializing Tradier client for second account...")
    try:
        from data.tradier_data_fetcher import TradierDataFetcher

        tradier_2 = TradierDataFetcher(
            api_key=api_key_2,
            account_id=account_id_2,
            sandbox=True
        )
        print(f"  [OK] Client initialized")
        print(f"  Using account: {tradier_2.account_id}")
        print(f"  Sandbox mode: {tradier_2.sandbox}")
    except Exception as e:
        print(f"  [FAIL] Client init failed: {e}")
        return False

    # Step 3: Get account balance
    print("\n[3/5] Checking account balance...")
    try:
        balance = tradier_2.get_account_balance()
        if balance:
            equity = balance.get('total_equity', balance.get('equity', 'N/A'))
            cash = balance.get('total_cash', balance.get('cash', 'N/A'))
            print(f"  Total Equity: ${equity}")
            print(f"  Cash: ${cash}")
        else:
            print("  [WARN] Could not get balance (may still work for orders)")
    except Exception as e:
        print(f"  [WARN] Balance check failed: {e}")

    # Step 4: Get market data for IC strikes
    print("\n[4/5] Getting market data for Iron Condor...")
    try:
        quote = tradier_2.get_quote("SPY")
        if not quote or not quote.get('last'):
            print("  [FAIL] Could not get SPY quote")
            return False

        spy_price = quote['last']
        print(f"  SPY price: ${spy_price:.2f}")

        # Get nearest expiration
        expirations = tradier_2.get_options_expirations("SPY")
        if not expirations:
            print("  [FAIL] Could not get expirations")
            return False

        exp = expirations[0]
        print(f"  Using expiration: {exp}")

        # Far OTM strikes (~$15 away) to minimize risk
        put_long = round(spy_price - 20, 0)
        put_short = round(spy_price - 15, 0)
        call_short = round(spy_price + 15, 0)
        call_long = round(spy_price + 20, 0)

        print(f"  Iron Condor strikes:")
        print(f"    Bull Put:  Buy {put_long} / Sell {put_short}")
        print(f"    Bear Call: Sell {call_short} / Buy {call_long}")

    except Exception as e:
        print(f"  [FAIL] Market data error: {e}")
        return False

    # Step 5: Place the trade
    print("\n[5/5] Placing Iron Condor on second account...")
    print(f"  Account: {account_id_2}")
    print(f"  Symbol: SPY")
    print(f"  Expiration: {exp}")
    print(f"  Contracts: 1")
    print(f"  Limit: Market price (credit)")

    try:
        result = tradier_2.place_iron_condor(
            symbol="SPY",
            expiration=exp,
            put_long=put_long,
            put_short=put_short,
            call_short=call_short,
            call_long=call_long,
            quantity=1,
            limit_price=None  # Market order to ensure fill in sandbox
        )

        if result and result.get('order'):
            order_id = result['order'].get('id')
            status = result['order'].get('status')
            print(f"\n  [SUCCESS] Order placed on second account!")
            print(f"    Order ID: {order_id}")
            print(f"    Status: {status}")
            print(f"    Account: {account_id_2}")

            # Wait briefly and check order status
            time.sleep(2)
            print(f"\n  Checking order fill status...")
            try:
                orders = tradier_2.get_orders()
                if orders:
                    for order in orders[:3]:
                        oid = order.get('id')
                        ostatus = order.get('status')
                        print(f"    Order {oid}: {ostatus}")
            except Exception as e:
                print(f"    Could not check orders: {e}")

            return True
        else:
            print(f"\n  [FAIL] Order placement failed!")
            print(f"    Response: {result}")
            return False

    except Exception as e:
        print(f"\n  [FAIL] Order execution error: {e}")
        import traceback
        traceback.print_exc()
        return False


def also_check_primary_account():
    """Quick check that primary account still works too."""
    print("\n" + "-" * 70)
    print("  QUICK CHECK: Primary sandbox account")
    print("-" * 70)

    try:
        api_key = os.getenv('TRADIER_SANDBOX_API_KEY')
        account_id = os.getenv('TRADIER_SANDBOX_ACCOUNT_ID')

        if not api_key or not account_id:
            print("  [SKIP] Primary credentials not set locally")
            return

        from data.tradier_data_fetcher import TradierDataFetcher
        tradier_1 = TradierDataFetcher(sandbox=True)
        print(f"  Primary account: {tradier_1.account_id}")

        # Verify they're different accounts
        api_key_2, account_id_2 = get_second_account_credentials()
        if account_id_2:
            if tradier_1.account_id == account_id_2:
                print("  [WARN] Primary and secondary use the SAME account!")
            else:
                print(f"  Second account:  {account_id_2}")
                print("  [OK] Accounts are different")

    except Exception as e:
        print(f"  [SKIP] Primary check failed: {e}")


def main():
    print("\n" + "=" * 70)
    print("  FORTRESS SECOND ACCOUNT FORCE TRADE")
    print("  Tests that the second Tradier sandbox account can place orders")
    print("=" * 70)

    # Run the force trade
    success = force_trade_on_second_account()

    # Also verify primary is still working
    also_check_primary_account()

    # Summary
    print("\n" + "=" * 70)
    if success:
        print("  RESULT: Second account trade placed SUCCESSFULLY")
        print("  The second Tradier sandbox account is working correctly.")
    else:
        print("  RESULT: Second account trade FAILED")
        print("  Check the errors above and verify env var configuration.")
    print("=" * 70 + "\n")

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
