#!/usr/bin/env python3
"""
Test script to manually push a trade to Tradier via FORTRESS.

Usage:
    python scripts/test_ares_trade.py --mode paper
    python scripts/test_ares_trade.py --mode live  # CAUTION: Real money!
"""

import os
import sys
import argparse
from datetime import datetime
from zoneinfo import ZoneInfo

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def main():
    parser = argparse.ArgumentParser(description='Test FORTRESS trade to Tradier')
    parser.add_argument('--mode', choices=['paper', 'live'], default='paper',
                        help='Trading mode (default: paper)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be traded without executing')
    args = parser.parse_args()

    print("=" * 60)
    print("FORTRESS MANUAL TRADE TEST")
    print("=" * 60)
    print(f"Mode: {args.mode.upper()}")
    print(f"Dry Run: {args.dry_run}")
    print(f"Time: {datetime.now(ZoneInfo('America/Chicago')).strftime('%Y-%m-%d %H:%M:%S CT')}")
    print("=" * 60)

    try:
        from trading.ares_iron_condor import FortressTrader, TradingMode

        mode = TradingMode.LIVE if args.mode == 'live' else TradingMode.PAPER
        print(f"\nInitializing FORTRESS in {mode.value} mode...")

        fortress = FortressTrader(mode=mode, initial_capital=200_000)

        # Get status
        status = fortress.get_status()
        print(f"\nARES Status:")
        print(f"  Mode: {status.get('mode', 'unknown')}")
        print(f"  Capital: ${status.get('capital', 0):,.2f}")
        print(f"  Open Positions: {status.get('open_positions', 0)}")
        print(f"  Traded Today: {status.get('traded_today', False)}")
        print(f"  In Trading Window: {status.get('in_trading_window', False)}")

        # Get Tradier status
        print(f"\nTradier Connection:")
        tradier_status = fortress.get_tradier_account_status()
        if tradier_status.get('success'):
            account = tradier_status.get('data', {}).get('account', {})
            print(f"  Account: {account.get('account_number', 'N/A')}")
            print(f"  Equity: ${account.get('equity', 0):,.2f}")
            print(f"  Cash: ${account.get('cash', 0):,.2f}")
            print(f"  Day Trading Buying Power: ${account.get('day_trade_buying_power', 0):,.2f}")
        else:
            print(f"  Error: {tradier_status.get('error', 'Unknown')}")

        if args.dry_run:
            print("\n[DRY RUN] Would run daily cycle here...")
            print("\nTo execute for real, run without --dry-run flag")
            return

        # Confirm before executing
        print("\n" + "!" * 60)
        if args.mode == 'live':
            print("WARNING: This will place a REAL trade with REAL MONEY!")
        else:
            print("This will place a trade in Tradier SANDBOX")
        print("!" * 60)

        confirm = input("\nType 'YES' to proceed: ")
        if confirm != 'YES':
            print("Aborted.")
            return

        # Run the daily cycle
        print("\nRunning FORTRESS daily cycle...")
        result = fortress.run_daily_cycle()

        print("\n" + "=" * 60)
        print("RESULT:")
        print("=" * 60)

        if result.get('success'):
            print("✅ Trade executed successfully!")
            trade = result.get('trade', {})
            print(f"  Order ID: {trade.get('order_id', 'N/A')}")
            print(f"  Strikes: {trade.get('put_long')}/{trade.get('put_short')}P - {trade.get('call_short')}/{trade.get('call_long')}C")
            print(f"  Credit: ${trade.get('credit', 0):.2f}")
            print(f"  Contracts: {trade.get('contracts', 0)}")
        else:
            print(f"❌ Trade not executed: {result.get('reason', 'Unknown reason')}")
            if result.get('skipped'):
                print(f"  Skipped: {result.get('skipped')}")
            if result.get('error'):
                print(f"  Error: {result.get('error')}")

    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("\nMake sure you have all dependencies installed:")
        print("  pip install -r requirements.txt")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()
