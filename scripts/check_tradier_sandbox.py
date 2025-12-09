#!/usr/bin/env python3
"""
Check Tradier Sandbox Status
=============================

Shows current positions, orders, and balance in Tradier sandbox.
This is what ARES trades actually look like on the broker side.

Run: python scripts/check_tradier_sandbox.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    from data.tradier_data_fetcher import TradierDataFetcher

    print("\n" + "="*60)
    print("TRADIER SANDBOX STATUS")
    print("="*60)

    try:
        tradier = TradierDataFetcher(sandbox=True)
        print(f"\n✓ Connected to: {tradier.base_url}")
        print(f"✓ Account: {tradier.account_id}")
        print(f"✓ Mode: {'SANDBOX' if tradier.sandbox else 'PRODUCTION'}")
    except Exception as e:
        print(f"\n❌ Connection failed: {e}")
        return

    # Get account balance
    print("\n" + "-"*40)
    print("ACCOUNT BALANCE")
    print("-"*40)

    try:
        balance = tradier.get_account_balance()
        if balance:
            cash = balance.get('cash', {})
            print(f"  Total Equity:     ${balance.get('total_equity', 0):,.2f}")
            print(f"  Cash Available:   ${cash.get('cash_available', 0):,.2f}")
            print(f"  Option BP:        ${balance.get('option_buying_power', 0):,.2f}")
            print(f"  Day Trade BP:     ${balance.get('day_trade_buying_power', 0):,.2f}")
            print(f"  Market Value:     ${balance.get('market_value', 0):,.2f}")
        else:
            print("  ⚠️  Could not get balance")
    except Exception as e:
        print(f"  Error: {e}")

    # Get positions
    print("\n" + "-"*40)
    print("OPEN POSITIONS")
    print("-"*40)

    try:
        positions = tradier.get_positions()
        if positions:
            for pos in positions:
                symbol = pos.get('symbol', 'Unknown')
                qty = pos.get('quantity', 0)
                cost = pos.get('cost_basis', 0)
                pnl = pos.get('unrealized_pnl', 0) or 0
                print(f"  {symbol}")
                print(f"    Qty: {qty}, Cost: ${cost:,.2f}, P&L: ${pnl:+,.2f}")
        else:
            print("  No open positions")
    except Exception as e:
        print(f"  Error: {e}")

    # Get orders (today's)
    print("\n" + "-"*40)
    print("RECENT ORDERS")
    print("-"*40)

    try:
        orders = tradier.get_orders()
        if orders:
            for order in orders[:10]:  # Show last 10
                order_id = order.get('id', 'Unknown')
                status = order.get('status', 'unknown')
                side = order.get('side', '')
                symbol = order.get('symbol', '')
                order_class = order.get('class', 'equity')
                qty = order.get('quantity', 0)
                created = order.get('create_date', '')

                print(f"  Order #{order_id} [{status.upper()}]")
                print(f"    {side.upper()} {qty}x {symbol} ({order_class})")
                print(f"    Created: {created}")
                print()
        else:
            print("  No recent orders")
    except Exception as e:
        print(f"  Error: {e}")

    # Get order history
    print("-"*40)
    print("ORDER HISTORY (Last 7 Days)")
    print("-"*40)

    try:
        history = tradier.get_order_history()
        if history:
            filled = [o for o in history if o.get('status') == 'filled']
            cancelled = [o for o in history if o.get('status') == 'canceled']
            print(f"  Filled orders: {len(filled)}")
            print(f"  Cancelled orders: {len(cancelled)}")

            if filled:
                print("\n  Recent fills:")
                for order in filled[:5]:
                    print(f"    - {order.get('side', '')} {order.get('symbol', '')} @ ${order.get('avg_fill_price', 0):.2f}")
        else:
            print("  No order history")
    except Exception as e:
        print(f"  Error: {e}")

    print("\n" + "="*60)
    print("HOW TO VIEW ON TRADIER:")
    print("="*60)
    print("""
1. Go to: https://dash.tradier.com/
2. Login with your Tradier credentials
3. Click "Switch to Sandbox" at the top right
4. View:
   - Positions: Dashboard > Positions
   - Orders: Dashboard > Orders
   - History: Dashboard > History

ARES trades will appear here as Iron Condor multileg orders.
Each trade shows:
  - 4 legs (long put, short put, short call, long call)
  - Net credit received
  - Fill status
""")


if __name__ == "__main__":
    main()
