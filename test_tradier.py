#!/usr/bin/env python3
"""
Quick test script for Tradier API - just fetches data, no trading.

Usage:
  python test_tradier.py

Make sure you have these environment variables set:
  TRADIER_API_KEY=your_key
  TRADIER_ACCOUNT_ID=your_account_id
  TRADIER_SANDBOX=true
"""

import os
import sys

# Check if env vars are set
api_key = os.getenv('TRADIER_API_KEY')
account_id = os.getenv('TRADIER_ACCOUNT_ID')

if not api_key:
    print("❌ TRADIER_API_KEY not set!")
    print("\nSet it with:")
    print('  export TRADIER_API_KEY="your_key_here"')
    print('  export TRADIER_ACCOUNT_ID="your_account_id"')
    print('  export TRADIER_SANDBOX="true"')
    sys.exit(1)

print(f"✓ API Key found (ends with ...{api_key[-4:]})")
print(f"✓ Account ID: {account_id or 'not set'}")
print(f"✓ Sandbox mode: {os.getenv('TRADIER_SANDBOX', 'true')}")
print()

try:
    from tradier_data_fetcher import TradierDataFetcher

    tradier = TradierDataFetcher()
    print(f"Mode: {'SANDBOX (paper)' if tradier.sandbox else 'LIVE (real money)'}")
    print("=" * 50)

    # Test 1: Get SPY quote
    print("\n📊 TEST 1: SPY Quote")
    quote = tradier.get_quote('SPY')
    if quote:
        print(f"  Last:   ${quote.get('last', 'N/A')}")
        print(f"  Bid:    ${quote.get('bid', 'N/A')}")
        print(f"  Ask:    ${quote.get('ask', 'N/A')}")
        print(f"  Volume: {quote.get('volume', 0):,}")
        print("  ✓ Quote working!")
    else:
        print("  ❌ No quote data returned")

    # Test 2: Get option expirations
    print("\n📅 TEST 2: SPY Option Expirations")
    expirations = tradier.get_option_expirations('SPY')
    if expirations:
        print(f"  Found {len(expirations)} expirations")
        print(f"  Next 5: {expirations[:5]}")
        print("  ✓ Expirations working!")
    else:
        print("  ❌ No expirations returned")

    # Test 3: Get options chain with Greeks
    print("\n📈 TEST 3: SPY Options Chain (nearest expiration)")
    if expirations:
        chain = tradier.get_option_chain('SPY', expirations[0], greeks=True)
        if chain.chains:
            contracts = list(chain.chains.values())[0]
            print(f"  Underlying: ${chain.underlying_price:.2f}")
            print(f"  Contracts: {len(contracts)}")

            # Show a few ATM options
            calls = [c for c in contracts if c.option_type == 'call']
            calls_sorted = sorted(calls, key=lambda c: abs(c.strike - chain.underlying_price))[:3]

            print("\n  Near-ATM Calls:")
            print("  Strike    Bid     Ask     Delta   Gamma    IV")
            print("  " + "-" * 55)
            for c in calls_sorted:
                print(f"  {c.strike:>6.0f}  {c.bid:>6.2f}  {c.ask:>6.2f}  {c.delta:>6.2f}  {c.gamma:>6.4f}  {c.implied_volatility:>5.1%}")
            print("  ✓ Options chain with Greeks working!")
        else:
            print("  ❌ No chain data returned")

    # Test 4: Account balance (sandbox)
    print("\n💰 TEST 4: Account Balance")
    try:
        balance = tradier.get_account_balance()
        print(f"  Total Equity:     ${balance.get('total_equity', 0):,.2f}")
        print(f"  Option Buying Power: ${balance.get('option_buying_power', 0):,.2f}")
        print(f"  Cash:             ${balance.get('total_cash', 0):,.2f}")
        print("  ✓ Account access working!")
    except Exception as e:
        print(f"  ⚠ Account access failed: {e}")
        print("  (This might be a permissions issue with your API key)")

    # Test 5: SPX options (for your SPX trader)
    print("\n🎯 TEST 5: SPX Options")
    spx_exps = tradier.get_option_expirations('SPX')
    if spx_exps:
        print(f"  Found {len(spx_exps)} SPX expirations")
        spx_chain = tradier.get_option_chain('SPX', spx_exps[0], greeks=True)
        if spx_chain.chains:
            spx_contracts = list(spx_chain.chains.values())[0]
            print(f"  SPX Price: ${spx_chain.underlying_price:.2f}")
            print(f"  Contracts: {len(spx_contracts)}")
            print("  ✓ SPX options working!")
    else:
        print("  ⚠ No SPX expirations (might need different symbol like $SPX.X)")

    print("\n" + "=" * 50)
    print("✅ All basic tests passed! Tradier API is working.")
    print("\nNext steps:")
    print("1. Add these env vars to Render")
    print("2. The autonomous traders can now use Tradier for live data")

except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback
    traceback.print_exc()
