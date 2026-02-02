#!/usr/bin/env python3
"""
Test Tastytrade API Connection
Verifies credentials and account access for HERACLES futures bot
"""

import os
import requests
from datetime import datetime

# Tastytrade API endpoints
BASE_URL = "https://api.tastytrade.com"
SANDBOX_URL = "https://api.cert.tastytrade.com"  # Sandbox/cert environment

def test_connection():
    """Test Tastytrade API connection and account access"""

    print("=" * 60)
    print("TASTYTRADE CONNECTION TEST")
    print("=" * 60)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print()

    # Get credentials from environment
    username = os.environ.get("TASTYTRADE_USERNAME")
    password = os.environ.get("TASTYTRADE_PASSWORD")
    account_id = os.environ.get("TASTYTRADE_ACCOUNT_ID")

    # Check credentials exist
    print("1. Checking environment variables...")
    missing = []
    if not username:
        missing.append("TASTYTRADE_USERNAME")
    if not password:
        missing.append("TASTYTRADE_PASSWORD")
    if not account_id:
        missing.append("TASTYTRADE_ACCOUNT_ID")

    if missing:
        print(f"   ❌ Missing: {', '.join(missing)}")
        return False

    print(f"   ✓ Username: {username[:3]}***")
    print(f"   ✓ Password: {'*' * 8}")
    print(f"   ✓ Account ID: {account_id}")
    print()

    # Authenticate
    print("2. Authenticating with Tastytrade API...")
    try:
        auth_response = requests.post(
            f"{BASE_URL}/sessions",
            json={
                "login": username,
                "password": password,
                "remember-me": True
            },
            headers={"Content-Type": "application/json"}
        )

        if auth_response.status_code == 201:
            auth_data = auth_response.json()
            session_token = auth_data.get("data", {}).get("session-token")
            print(f"   ✓ Authentication successful!")
            print(f"   ✓ Session token: {session_token[:20]}...")
        else:
            print(f"   ❌ Authentication failed: {auth_response.status_code}")
            print(f"   Response: {auth_response.text[:500]}")
            return False
    except Exception as e:
        print(f"   ❌ Connection error: {e}")
        return False
    print()

    # Set up authenticated headers
    headers = {
        "Authorization": session_token,
        "Content-Type": "application/json"
    }

    # Get account info
    print("3. Fetching account information...")
    try:
        account_response = requests.get(
            f"{BASE_URL}/customers/me/accounts",
            headers=headers
        )

        if account_response.status_code == 200:
            accounts = account_response.json().get("data", {}).get("items", [])
            print(f"   ✓ Found {len(accounts)} account(s)")

            for acc in accounts:
                acc_num = acc.get("account", {}).get("account-number")
                acc_type = acc.get("account", {}).get("account-type-name")
                margin_type = acc.get("account", {}).get("margin-or-cash")
                is_futures = acc.get("account", {}).get("is-futures-enabled", False)
                print(f"   → {acc_num}: {acc_type} ({margin_type}) | Futures: {'✓' if is_futures else '✗'}")

                if acc_num == account_id:
                    print(f"   ✓ Target account {account_id} found!")
                    if not is_futures:
                        print(f"   ⚠️  WARNING: Futures not enabled on this account!")
        else:
            print(f"   ❌ Failed to fetch accounts: {account_response.status_code}")
            print(f"   Response: {account_response.text[:500]}")
    except Exception as e:
        print(f"   ❌ Error fetching accounts: {e}")
    print()

    # Get account balances
    print("4. Fetching account balances...")
    try:
        balance_response = requests.get(
            f"{BASE_URL}/accounts/{account_id}/balances",
            headers=headers
        )

        if balance_response.status_code == 200:
            balances = balance_response.json().get("data", {})
            net_liq = balances.get("net-liquidating-value", "N/A")
            cash = balances.get("cash-balance", "N/A")
            buying_power = balances.get("derivative-buying-power", "N/A")
            futures_buying_power = balances.get("futures-overnight-margin-requirement", "N/A")
            print(f"   ✓ Net Liquidating Value: ${net_liq}")
            print(f"   ✓ Cash Balance: ${cash}")
            print(f"   ✓ Derivative Buying Power: ${buying_power}")
            print(f"   ✓ Futures Overnight Margin: ${futures_buying_power}")
        else:
            print(f"   ❌ Failed to fetch balances: {balance_response.status_code}")
    except Exception as e:
        print(f"   ❌ Error fetching balances: {e}")
    print()

    # Test MES quote (futures symbol)
    print("5. Testing MES futures quote...")
    try:
        # MES symbol format: /MESH5 (March 2025), /MESM5 (June 2025), etc.
        # Try to get the front month contract
        # Format: /MES + Month Code + Year digit
        # Month codes: H=Mar, M=Jun, U=Sep, Z=Dec

        # Get current front month
        from datetime import datetime
        now = datetime.now()
        month = now.month
        year = now.year % 10  # Last digit of year

        # Determine front month code
        if month <= 3:
            month_code = "H"  # March
        elif month <= 6:
            month_code = "M"  # June
        elif month <= 9:
            month_code = "U"  # September
        else:
            month_code = "Z"  # December

        mes_symbol = f"/MESH{year + 1}" if month > 3 else f"/MES{month_code}{year}"

        # Try common symbols
        test_symbols = ["/MESH6", "/MESM6", "/MES"]

        for symbol in test_symbols:
            quote_response = requests.get(
                f"{BASE_URL}/market-data/quotes/{symbol}",
                headers=headers
            )

            if quote_response.status_code == 200:
                quote_data = quote_response.json().get("data", {})
                bid = quote_data.get("bid-price", "N/A")
                ask = quote_data.get("ask-price", "N/A")
                last = quote_data.get("last-price", "N/A")
                print(f"   ✓ {symbol} Quote: Bid={bid} Ask={ask} Last={last}")
                break
            else:
                print(f"   → {symbol}: {quote_response.status_code} (trying next...)")
        else:
            print("   ⚠️  Could not fetch MES quote (may need DXFeed streaming)")
            print("   Note: Real-time futures quotes may require websocket connection")
    except Exception as e:
        print(f"   ❌ Error fetching MES quote: {e}")
    print()

    # Test futures instruments lookup
    print("6. Looking up MES futures instrument...")
    try:
        instrument_response = requests.get(
            f"{BASE_URL}/instruments/futures",
            headers=headers,
            params={"symbol[]": "/MES"}
        )

        if instrument_response.status_code == 200:
            instruments = instrument_response.json().get("data", {}).get("items", [])
            if instruments:
                for inst in instruments[:3]:  # Show first 3
                    symbol = inst.get("symbol")
                    desc = inst.get("description", "")
                    tick_size = inst.get("tick-size")
                    tick_value = inst.get("tick-value")
                    print(f"   ✓ {symbol}: {desc}")
                    print(f"     Tick: ${tick_value} per {tick_size} point")
            else:
                print("   ⚠️  No MES instruments found in response")
        else:
            print(f"   Response: {instrument_response.status_code}")
    except Exception as e:
        print(f"   ❌ Error looking up instruments: {e}")
    print()

    print("=" * 60)
    print("CONNECTION TEST COMPLETE")
    print("=" * 60)

    return True


if __name__ == "__main__":
    test_connection()
