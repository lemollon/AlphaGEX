#!/usr/bin/env python3
"""
Test script to manually push a trade to Tradier via FORTRESS.

Usage:
    python scripts/test_fortress_trade.py --mode paper
    python scripts/test_fortress_trade.py --mode live  # CAUTION: Real money!
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
        from trading.fortress_v2 import FortressTrader, FortressConfig, TradingMode

        mode = TradingMode.LIVE if args.mode == 'live' else TradingMode.PAPER
        print(f"\nInitializing FORTRESS in {mode.value} mode...")

        config = FortressConfig(mode=mode, capital=200_000)
        fortress = FortressTrader(config=config)

        # Get status
        status = fortress.get_status()
        print(f"\nFORTRESS Status:")
        print(f"  Mode: {status.get('mode', 'unknown')}")
        print(f"  Capital: ${status.get('capital', 0):,.2f}")
        print(f"  Open Positions: {status.get('open_positions', 0)}")
        print(f"  Traded Today: {status.get('traded_today', False)}")
        print(f"  In Trading Window: {status.get('in_trading_window', False)}")

        # Get Tradier status via executor
        print(f"\nTradier Connection:")
        exec_status = fortress.executor.get_execution_status()
        print(f"  Can Execute: {exec_status.get('can_execute', False)}")
        print(f"  Primary Tradier: {'Initialized' if exec_status.get('tradier_initialized') else 'Not initialized'}")
        print(f"  Second Tradier: {'Initialized' if exec_status.get('tradier_2_initialized') else 'Not configured'}")

        if args.dry_run:
            print("\n[DRY RUN] Would run trading cycle here...")
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

        # Run the trading cycle
        print("\nRunning FORTRESS cycle...")
        result = fortress.run_cycle()

        print("\n" + "=" * 60)
        print("RESULT:")
        print("=" * 60)

        if result.get('trade_opened'):
            print("✅ Trade executed successfully!")
            details = result.get('details', {})
            print(f"  Action: {result.get('action', 'N/A')}")
            print(f"  Realized P&L: ${result.get('realized_pnl', 0):.2f}")
        else:
            print(f"Action: {result.get('action', 'none')}")
            errors = result.get('errors', [])
            if errors:
                for err in errors:
                    print(f"  Error: {err}")
            else:
                print("  No trade opened this cycle (conditions may not be met)")

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
