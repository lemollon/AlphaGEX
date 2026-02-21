#!/usr/bin/env python3
"""
Check actual Tradier account state - what does Tradier think we have?
Run on Render shell: python3 system_audit/check_tradier_account.py
"""
import os
import json
import urllib.request

print("=" * 60)
print("  TRADIER ACCOUNT REALITY CHECK")
print("=" * 60)

# Find API credentials
API_TOKEN = (
    os.environ.get('TRADIER_PROD_API_KEY')
    or os.environ.get('TRADIER_API_KEY')
    or os.environ.get('TRADIER_API_TOKEN')
    or os.environ.get('TRADIER_ACCESS_TOKEN')
)
ACCOUNT_ID = (
    os.environ.get('TRADIER_ACCOUNT_ID')
    or os.environ.get('TRADIER_ACCOUNT')
)

if not API_TOKEN:
    print("\nNo Tradier API token found in environment")
    print("Checked: TRADIER_PROD_API_KEY, TRADIER_API_KEY, TRADIER_API_TOKEN, TRADIER_ACCESS_TOKEN")
    exit(1)

if not ACCOUNT_ID:
    print("\nNo Tradier account ID found in environment")
    print("Checked: TRADIER_ACCOUNT_ID, TRADIER_ACCOUNT")
    exit(1)

# Determine production vs sandbox
BASE_URL = 'https://api.tradier.com/v1'
SANDBOX_TOKEN = os.environ.get('TRADIER_SANDBOX_API_KEY') or os.environ.get('TRADIER_SANDBOX_TOKEN')
is_sandbox = 'sandbox' in API_TOKEN.lower() if API_TOKEN else False

print(f"\nAccount ID: {ACCOUNT_ID}")
print(f"Base URL: {BASE_URL}")
print(f"Token prefix: {API_TOKEN[:8]}...")
print(f"{'SANDBOX MODE' if is_sandbox else 'PRODUCTION MODE'}\n")


def tradier_get(endpoint):
    """Make a GET request to Tradier API."""
    url = f"{BASE_URL}{endpoint}"
    req = urllib.request.Request(url, headers={
        'Authorization': f'Bearer {API_TOKEN}',
        'Accept': 'application/json'
    })
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return {'error': f"HTTP {e.code}: {e.read().decode()[:200]}"}
    except Exception as e:
        return {'error': str(e)}


# 1. Account balance
print("--- ACCOUNT BALANCE ---")
data = tradier_get(f'/accounts/{ACCOUNT_ID}/balances')
if 'error' in data:
    print(f"  Failed: {data['error']}")
else:
    bal = data.get('balances', data)
    for key in ['total_equity', 'option_buying_power', 'total_cash', 'cash',
                'market_value', 'pending_cash', 'option_short_value', 'option_long_value']:
        val = bal.get(key)
        if val is not None:
            if isinstance(val, (int, float)):
                print(f"  {key}: ${val:,.2f}")
            else:
                print(f"  {key}: {val}")

# 2. Current positions on Tradier
print("\n--- TRADIER POSITIONS (What Tradier actually holds) ---")
data = tradier_get(f'/accounts/{ACCOUNT_ID}/positions')
if 'error' in data:
    print(f"  Failed: {data['error']}")
else:
    positions = data.get('positions', {})
    if not positions or positions == 'null':
        print("  No positions on Tradier")
    else:
        pos_list = positions.get('position', [])
        if isinstance(pos_list, dict):
            pos_list = [pos_list]
        print(f"  {len(pos_list)} positions on Tradier:")
        for p in pos_list:
            print(f"    {p.get('symbol', '?')}: qty={p.get('quantity', '?')} "
                  f"cost=${p.get('cost_basis', '?')}")

# 3. Recent orders
print("\n--- RECENT ORDERS ---")
data = tradier_get(f'/accounts/{ACCOUNT_ID}/orders')
if 'error' in data:
    print(f"  Failed: {data['error']}")
else:
    orders = data.get('orders', {})
    if not orders or orders == 'null':
        print("  No recent orders - NOTHING IS TRADING FOR REAL")
    else:
        order_list = orders.get('order', [])
        if isinstance(order_list, dict):
            order_list = [order_list]
        print(f"  {len(order_list)} recent orders:")
        for o in order_list[:20]:
            print(f"    {o.get('create_date', '?')[:19]} | "
                  f"{o.get('side', '?')} {o.get('class', '?')} | "
                  f"Status: {o.get('status', '?')} | "
                  f"{o.get('symbol', o.get('option_symbol', '?'))}")

# 4. Order count by day
print("\n--- ORDER COUNT BY DAY ---")
if not orders or orders == 'null':
    print("  No orders found")
else:
    from collections import Counter
    order_list = orders.get('order', [])
    if isinstance(order_list, dict):
        order_list = [order_list]
    by_date = Counter()
    by_status = Counter()
    for o in order_list:
        date_str = str(o.get('create_date', 'unknown'))[:10]
        by_date[date_str] += 1
        by_status[o.get('status', 'unknown')] += 1
    for date_str in sorted(by_date.keys(), reverse=True)[:14]:
        print(f"    {date_str}: {by_date[date_str]} orders")

    print(f"\n  By status:")
    for status, count in by_status.most_common():
        print(f"    {status}: {count}")

print(f"\n{'='*60}")
print("  TRADIER ACCOUNT CHECK COMPLETE")
print(f"{'='*60}")
