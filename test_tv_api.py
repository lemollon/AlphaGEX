#!/usr/bin/env python3
"""Test Trading Volatility API directly"""
import requests

api_key = "I-RWFNBLR2S1DP"
endpoint = "https://stocks.tradingvolatility.net/api"

url = f"{endpoint}/gex/latest"
params = {
    'ticker': 'SPY',
    'username': api_key,
    'format': 'json'
}

print(f"Testing API call...")
print(f"URL: {url}")
print(f"Params: {params}")
print()

response = requests.get(url, params=params, headers={'Accept': 'application/json'})

print(f"Status: {response.status_code}")
print(f"Response text (first 500 chars):")
print(response.text[:500])
