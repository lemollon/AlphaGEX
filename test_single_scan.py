#!/usr/bin/env python3
"""Test scanner with single symbol"""
import requests

try:
    print("🔍 Testing SPY scan...")
    response = requests.post(
        'http://localhost:8000/api/scanner/scan',
        json={'symbols': ['SPY']},
        timeout=60
    )

    print(f"Status code: {response.status_code}")

    if response.status_code == 200:
        data = response.json()
        print(f"\nResults: {data}")
    else:
        print(f"Error: {response.text}")

except Exception as e:
    print(f"Exception: {e}")
