#!/usr/bin/env python3
"""
Auto FORTRESS Trade - No Manual Confirmation Required
=================================================

Automatically triggers FORTRESS to execute a trade without requiring manual input.
This is the script to run for automated/scheduled trading.

Usage:
    python scripts/auto_ares_trade.py           # Paper mode (default)
    python scripts/auto_ares_trade.py --live    # LIVE mode (real money!)
"""

import os
import sys
import argparse
from datetime import datetime
from zoneinfo import ZoneInfo

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    parser = argparse.ArgumentParser(description='Auto FORTRESS Trade (No Manual Confirmation)')
    parser.add_argument('--live', action='store_true', help='Use LIVE mode (REAL MONEY)')
    parser.add_argument('--force', action='store_true', help='Force trade even if already traded today')
    args = parser.parse_args()

    print("=" * 60)
    print("FORTRESS AUTO TRADE - NO CONFIRMATION REQUIRED")
    print("=" * 60)
    print(f"Mode: {'LIVE' if args.live else 'PAPER'}")
    print(f"Time: {datetime.now(ZoneInfo('America/Chicago')).strftime('%Y-%m-%d %H:%M:%S CT')}")
    print("=" * 60)

    try:
        from trading.ares_iron_condor import FortressTrader, TradingMode

        mode = TradingMode.LIVE if args.live else TradingMode.PAPER
        print(f"\n🚀 Initializing FORTRESS in {mode.value} mode...")

        fortress = FortressTrader(mode=mode, initial_capital=200_000)

        # Get status
        status = fortress.get_status()
        print(f"\n📊 FORTRESS Status:")
        print(f"  Mode: {status.get('mode', 'unknown')}")
        print(f"  Capital: ${status.get('capital', 0):,.2f}")
        print(f"  Open Positions: {status.get('open_positions', 0)}")
        print(f"  Traded Today: {status.get('traded_today', False)}")
        print(f"  In Trading Window: {status.get('in_trading_window', False)}")

        # Get Tradier status
        print(f"\n💰 Tradier Connection:")
        tradier_status = fortress.get_tradier_account_status()
        if tradier_status.get('success'):
            account = tradier_status.get('data', {}).get('account', {})
            equity = account.get('equity', 0) or account.get('total_equity', 0) or 0
            cash = account.get('cash', 0) or account.get('total_cash', 0) or 0
            buying_power = account.get('day_trade_buying_power', 0) or account.get('option_buying_power', 0) or 0
            print(f"  Account: {account.get('account_number', 'N/A')}")
            print(f"  Equity: ${equity:,.2f}")
            print(f"  Cash: ${cash:,.2f}")
            print(f"  Buying Power: ${buying_power:,.2f}")

            if buying_power <= 0:
                print(f"\n⚠️  WARNING: Buying power is $0!")
                print(f"   If using sandbox, reset at: https://dash.tradier.com/")
                print(f"   Or set separate TRADIER_SANDBOX_API_KEY and TRADIER_SANDBOX_ACCOUNT_ID")
        else:
            print(f"  Error: {tradier_status.get('error', 'Unknown')}")

        # Check if should skip
        if status.get('traded_today') and not args.force:
            print(f"\n⏭️  Already traded today. Use --force to override.")
            return {'skipped': True, 'reason': 'already_traded_today'}

        if not status.get('in_trading_window'):
            print(f"\n⏰ Outside trading window (8:30 AM - 3:30 PM CT)")
            print(f"   Running anyway for testing...")

        # Run the daily cycle - NO CONFIRMATION
        print(f"\n🎯 Running FORTRESS daily cycle...")
        result = fortress.run_daily_cycle()

        print("\n" + "=" * 60)
        print("RESULT:")
        print("=" * 60)

        if result.get('success'):
            print("✅ Trade executed successfully!")
            trade = result.get('trade', {})
            if trade:
                print(f"  Order ID: {trade.get('order_id', 'N/A')}")
                print(f"  Strikes: {trade.get('put_long')}/{trade.get('put_short')}P - {trade.get('call_short')}/{trade.get('call_long')}C")
                print(f"  Credit: ${trade.get('credit', 0):.2f}")
                print(f"  Contracts: {trade.get('contracts', 0)}")
            else:
                print(f"  Details: {result}")
        else:
            reason = result.get('reason', result.get('message', 'Unknown reason'))
            print(f"❌ Trade not executed: {reason}")
            if result.get('skipped'):
                print(f"  Skipped: {result.get('skipped')}")
            if result.get('error'):
                print(f"  Error: {result.get('error')}")

        return result

    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("\nMake sure you have all dependencies installed:")
        print("  pip install -r requirements.txt")
        return {'error': str(e)}
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return {'error': str(e)}


if __name__ == '__main__':
    main()
