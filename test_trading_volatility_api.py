#!/usr/bin/env python3
"""
Test script to directly call Trading Volatility API and inspect the raw response.
This helps diagnose why call_gamma/put_gamma might be 0 in the processed data.

Usage:
    python test_trading_volatility_api.py [SYMBOL]

Example:
    python test_trading_volatility_api.py SPY
"""

import os
import sys
import json
import requests

def get_api_credentials():
    """Load API credentials using the same logic as TradingVolatilityAPI class"""

    # Try environment variables first
    api_key = (
        os.getenv("TRADING_VOLATILITY_API_KEY") or
        os.getenv("TV_USERNAME") or
        os.getenv("TRADINGVOLATILITY_USERNAME")
    )

    # Try secrets.toml if no env var
    if not api_key:
        try:
            import toml
            secrets_path = os.path.join(os.path.dirname(__file__), '.streamlit', 'secrets.toml')
            if os.path.exists(secrets_path):
                secrets = toml.load(secrets_path)
                api_key = (
                    secrets.get("tradingvolatility_username") or
                    secrets.get("tv_username") or
                    secrets.get("TRADING_VOLATILITY_API_KEY")
                )
        except Exception as e:
            print(f"Could not load secrets.toml: {e}")

    # Get endpoint
    endpoint = (
        os.getenv("TRADING_VOLATILITY_ENDPOINT") or
        os.getenv("ENDPOINT") or
        "https://stocks.tradingvolatility.net/api"
    )

    return api_key, endpoint


def test_gammaoi_endpoint(symbol: str = "SPY"):
    """Call /gex/gammaOI endpoint and inspect the response"""

    api_key, endpoint = get_api_credentials()

    print("=" * 70)
    print("TRADING VOLATILITY API TEST - /gex/gammaOI")
    print("=" * 70)
    print(f"Symbol: {symbol}")
    print(f"Endpoint: {endpoint}")
    print(f"API Key: {'*' * (len(api_key) - 4) + api_key[-4:] if api_key else 'NOT FOUND'}")
    print("=" * 70)

    if not api_key:
        print("\n[ERROR] No API key found!")
        print("Set TRADING_VOLATILITY_API_KEY environment variable or add to secrets.toml")
        return None

    # Build request
    url = f"{endpoint}/gex/gammaOI"
    params = {
        'ticker': symbol,
        'username': api_key,
        'format': 'json'
    }

    print(f"\n[REQUEST] GET {url}")
    print(f"[PARAMS] ticker={symbol}, username=***, format=json")

    try:
        response = requests.get(url, params=params, headers={'Accept': 'application/json'}, timeout=30)

        print(f"\n[RESPONSE] Status: {response.status_code}")
        print(f"[RESPONSE] Content-Type: {response.headers.get('Content-Type', 'unknown')}")
        print(f"[RESPONSE] Content Length: {len(response.text)} bytes")

        if response.status_code != 200:
            print(f"\n[ERROR] Non-200 status code")
            print(f"Response text: {response.text[:500]}")
            return None

        if "API limit exceeded" in response.text:
            print(f"\n[ERROR] Rate limited")
            print(f"Response text: {response.text}")
            return None

        # Parse JSON
        data = response.json()

        print("\n" + "=" * 70)
        print("RAW JSON RESPONSE STRUCTURE")
        print("=" * 70)

        # Show top-level keys
        print(f"\nTop-level keys: {list(data.keys())}")

        # Get ticker data
        ticker_data = data.get(symbol, {})
        if not ticker_data:
            print(f"\n[ERROR] No data found for symbol '{symbol}'")
            print(f"Available keys: {list(data.keys())}")
            return data

        print(f"\n{symbol} data keys: {list(ticker_data.keys())}")

        # Show aggregate fields
        print("\n" + "-" * 50)
        print("AGGREGATE FIELDS")
        print("-" * 50)
        for key in ['price', 'implied_volatility', 'gex_flip_price', 'skew_adjusted_gex',
                    'put_call_ratio_open_interest', 'collection_date']:
            val = ticker_data.get(key, 'NOT FOUND')
            print(f"  {key}: {val} (type: {type(val).__name__})")

        # Get gamma_array
        gamma_array = ticker_data.get('gamma_array', [])
        print(f"\n" + "-" * 50)
        print(f"GAMMA ARRAY ({len(gamma_array)} strikes)")
        print("-" * 50)

        if not gamma_array:
            print("[WARNING] gamma_array is empty!")
            return data

        # Show first strike structure
        first_strike = gamma_array[0]
        print(f"\nFirst strike - ALL fields:")
        for key, value in first_strike.items():
            print(f"  {key}: {value!r} (type: {type(value).__name__})")

        # Analyze call_gamma and put_gamma specifically
        print("\n" + "-" * 50)
        print("CALL_GAMMA / PUT_GAMMA ANALYSIS (first 10 strikes)")
        print("-" * 50)
        print(f"{'Strike':<10} {'call_gamma':<25} {'put_gamma':<25} {'net_gamma':<25}")
        print("-" * 85)

        for i, strike in enumerate(gamma_array[:10]):
            strike_price = strike.get('strike', 'N/A')
            call_gamma = strike.get('call_gamma', 'MISSING')
            put_gamma = strike.get('put_gamma', 'MISSING')
            net_gamma = strike.get('net_gamma_$_at_strike', 'MISSING')

            # Show raw values
            print(f"{strike_price:<10} {str(call_gamma):<25} {str(put_gamma):<25} {str(net_gamma):<25}")

        # Try to convert to floats to see if it works
        print("\n" + "-" * 50)
        print("FLOAT CONVERSION TEST (first 5 strikes)")
        print("-" * 50)

        for i, strike in enumerate(gamma_array[:5]):
            strike_price = strike.get('strike', 0)
            call_gamma_raw = strike.get('call_gamma', 0)
            put_gamma_raw = strike.get('put_gamma', 0)

            print(f"\nStrike {strike_price}:")
            print(f"  call_gamma raw: {call_gamma_raw!r} (type: {type(call_gamma_raw).__name__})")
            print(f"  put_gamma raw: {put_gamma_raw!r} (type: {type(put_gamma_raw).__name__})")

            # Try conversion
            try:
                call_float = float(call_gamma_raw) if call_gamma_raw else 0.0
                print(f"  call_gamma as float: {call_float}")
            except Exception as e:
                print(f"  call_gamma CONVERSION FAILED: {e}")

            try:
                put_float = float(put_gamma_raw) if put_gamma_raw else 0.0
                print(f"  put_gamma as float: {put_float}")
            except Exception as e:
                print(f"  put_gamma CONVERSION FAILED: {e}")

        # Check for any strikes with non-zero gamma
        print("\n" + "-" * 50)
        print("NON-ZERO GAMMA CHECK")
        print("-" * 50)

        non_zero_call = 0
        non_zero_put = 0
        zero_call = 0
        zero_put = 0

        for strike in gamma_array:
            call_gamma = strike.get('call_gamma', 0)
            put_gamma = strike.get('put_gamma', 0)

            try:
                call_val = float(call_gamma) if call_gamma else 0.0
                put_val = float(put_gamma) if put_gamma else 0.0

                if call_val != 0:
                    non_zero_call += 1
                else:
                    zero_call += 1

                if put_val != 0:
                    non_zero_put += 1
                else:
                    zero_put += 1
            except:
                pass

        print(f"call_gamma: {non_zero_call} non-zero, {zero_call} zero")
        print(f"put_gamma: {non_zero_put} non-zero, {zero_put} zero")

        print("\n" + "=" * 70)
        print("TEST COMPLETE")
        print("=" * 70)

        return data

    except requests.exceptions.RequestException as e:
        print(f"\n[ERROR] Request failed: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"\n[ERROR] JSON decode failed: {e}")
        print(f"Response text: {response.text[:500]}")
        return None


if __name__ == "__main__":
    symbol = sys.argv[1] if len(sys.argv) > 1 else "SPY"
    test_gammaoi_endpoint(symbol)
