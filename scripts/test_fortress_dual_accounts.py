#!/usr/bin/env python3
"""
Test script to verify FORTRESS dual sandbox account configuration.

Run this after setting environment variables to confirm both accounts work.

Usage:
    python scripts/test_fortress_dual_accounts.py
"""

import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv not required if env vars set externally


def test_environment_variables():
    """Check if required environment variables are set."""
    print("\n" + "=" * 60)
    print("1. CHECKING ENVIRONMENT VARIABLES")
    print("=" * 60)

    vars_to_check = [
        ("TRADIER_SANDBOX_API_KEY", "Primary sandbox API key"),
        ("TRADIER_SANDBOX_ACCOUNT_ID", "Primary sandbox account ID"),
        ("TRADIER_FORTRESS_SANDBOX_API_KEY_2", "Second sandbox API key"),
        ("TRADIER_FORTRESS_SANDBOX_ACCOUNT_ID_2", "Second sandbox account ID"),
    ]

    all_set = True
    for var_name, description in vars_to_check:
        value = os.getenv(var_name)
        if value:
            # Mask the value for security
            masked = f"{value[:4]}...{value[-4:]}" if len(value) > 8 else "***"
            print(f"  [OK] {var_name}: {masked}")
        else:
            print(f"  [MISSING] {var_name}: NOT SET ({description})")
            if "KEY_2" in var_name or "ACCOUNT_ID_2" in var_name:
                all_set = False

    return all_set


def test_account_connectivity(api_key: str, account_id: str, account_name: str):
    """Test connectivity to a Tradier sandbox account."""
    print(f"\n  Testing {account_name}...")

    try:
        from data.tradier_data_fetcher import TradierDataFetcher

        tradier = TradierDataFetcher(
            api_key=api_key,
            account_id=account_id,
            sandbox=True
        )

        # Test 1: Get account profile
        profile = tradier.get_account_profile()
        if profile:
            print(f"    [OK] Account profile retrieved")
            acct_num = profile.get('account', {}).get('account_number', 'N/A')
            print(f"         Account Number: {acct_num}")
        else:
            print(f"    [WARN] Could not get account profile")

        # Test 2: Get account balances
        balances = tradier.get_account_balances()
        if balances:
            print(f"    [OK] Account balances retrieved")
            equity = balances.get('balances', {}).get('total_equity', 'N/A')
            cash = balances.get('balances', {}).get('total_cash', 'N/A')
            print(f"         Total Equity: ${equity:,.2f}" if isinstance(equity, (int, float)) else f"         Total Equity: {equity}")
            print(f"         Total Cash: ${cash:,.2f}" if isinstance(cash, (int, float)) else f"         Total Cash: {cash}")
        else:
            print(f"    [WARN] Could not get account balances")

        # Test 3: Get a simple quote (validates API key works)
        quote = tradier.get_quote("SPY")
        if quote and quote.get('last'):
            print(f"    [OK] Market data working (SPY: ${quote['last']:.2f})")
        else:
            print(f"    [WARN] Could not get SPY quote")

        # Test 4: Get options chain (validates options access)
        chain = tradier.get_options_expirations("SPY")
        if chain:
            print(f"    [OK] Options data working ({len(chain)} expirations available)")
        else:
            print(f"    [WARN] Could not get options expirations")

        return True

    except Exception as e:
        print(f"    [FAIL] Error: {e}")
        return False


def test_both_accounts():
    """Test connectivity to both sandbox accounts."""
    print("\n" + "=" * 60)
    print("2. TESTING ACCOUNT CONNECTIVITY")
    print("=" * 60)

    results = {}

    # Primary account
    key1 = os.getenv('TRADIER_SANDBOX_API_KEY')
    acct1 = os.getenv('TRADIER_SANDBOX_ACCOUNT_ID')

    if key1 and acct1:
        results['primary'] = test_account_connectivity(key1, acct1, "Primary Sandbox Account")
    else:
        print("\n  [SKIP] Primary account - credentials not set")
        results['primary'] = False

    # Second account
    key2 = os.getenv('TRADIER_FORTRESS_SANDBOX_API_KEY_2')
    acct2 = os.getenv('TRADIER_FORTRESS_SANDBOX_ACCOUNT_ID_2')

    if key2 and acct2:
        results['secondary'] = test_account_connectivity(key2, acct2, "Second Sandbox Account (FORTRESS Mirror)")
    else:
        print("\n  [SKIP] Second account - credentials not set")
        results['secondary'] = False

    return results


def test_fortress_executor_init():
    """Test that FORTRESS OrderExecutor initializes both connections."""
    print("\n" + "=" * 60)
    print("3. TESTING FORTRESS EXECUTOR INITIALIZATION")
    print("=" * 60)

    try:
        from trading.fortress_v2.models import FortressConfig, TradingMode
        from trading.fortress_v2.executor import OrderExecutor

        # Create config in LIVE mode (which uses sandbox)
        config = FortressConfig(mode=TradingMode.LIVE)
        executor = OrderExecutor(config)

        status = executor.get_execution_status()

        print(f"\n  Executor Status:")
        print(f"    Mode: {status.get('mode', 'N/A')}")
        print(f"    Can Execute Trades: {status.get('can_execute', False)}")
        print(f"    Primary Tradier: {'[OK] Initialized' if status.get('tradier_initialized') else '[FAIL] Not initialized'}")
        print(f"    Second Tradier:  {'[OK] Initialized' if status.get('tradier_2_initialized') else '[NOT SET] Not configured'}")

        if status.get('init_error'):
            print(f"    Init Error: {status.get('init_error')}")

        return status.get('tradier_initialized', False), status.get('tradier_2_initialized', False)

    except Exception as e:
        print(f"\n  [FAIL] Could not initialize FORTRESS executor: {e}")
        import traceback
        traceback.print_exc()
        return False, False


def main():
    print("\n" + "=" * 60)
    print("  FORTRESS DUAL SANDBOX ACCOUNT TEST")
    print("=" * 60)

    # Test 1: Environment variables
    env_ok = test_environment_variables()

    # Test 2: Account connectivity
    connectivity = test_both_accounts()

    # Test 3: FORTRESS executor
    primary_ok, secondary_ok = test_fortress_executor_init()

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    print(f"\n  Environment Variables:")
    print(f"    Second account vars set: {'YES' if env_ok else 'NO'}")

    print(f"\n  Account Connectivity:")
    print(f"    Primary account:  {'CONNECTED' if connectivity.get('primary') else 'FAILED'}")
    print(f"    Second account:   {'CONNECTED' if connectivity.get('secondary') else 'NOT CONFIGURED' if not env_ok else 'FAILED'}")

    print(f"\n  FORTRESS Executor:")
    print(f"    Primary Tradier:  {'READY' if primary_ok else 'NOT READY'}")
    print(f"    Second Tradier:   {'READY' if secondary_ok else 'NOT CONFIGURED'}")

    # Final verdict
    print("\n" + "-" * 60)
    if primary_ok and secondary_ok:
        print("  RESULT: FORTRESS will mirror trades to BOTH accounts")
    elif primary_ok and not secondary_ok:
        if env_ok:
            print("  RESULT: Second account FAILED - check credentials")
        else:
            print("  RESULT: Second account NOT CONFIGURED - add env vars to Render")
    else:
        print("  RESULT: Primary account not working - FORTRESS cannot trade")
    print("-" * 60 + "\n")

    return 0 if (primary_ok and secondary_ok) else 1


if __name__ == "__main__":
    sys.exit(main())
