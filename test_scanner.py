#!/usr/bin/env python3
"""
Test the fixed scanner endpoint
"""
import requests
import json

# Test symbols (same as user's Streamlit test)
test_symbols = ['SPY', 'QQQ', 'IWM', 'TSLA', 'DIA']

print(f"🔍 Testing scanner with {len(test_symbols)} symbols...")
print("=" * 60)

try:
    response = requests.post(
        'http://localhost:8000/api/scanner/scan',
        json={'symbols': test_symbols},
        timeout=300  # 5 minute timeout
    )

    if response.status_code == 200:
        data = response.json()

        print(f"\n✅ Scan completed!")
        print(f"Total symbols: {data['total_symbols']}")
        print(f"Opportunities found: {data['opportunities_found']}")
        print(f"Duration: {data['scan_duration_seconds']:.1f}s")

        print(f"\n📊 RESULTS:\n")

        if data['results']:
            for i, result in enumerate(data['results'], 1):
                print(f"{i}. {result['symbol']} - {result['strategy']}")
                print(f"   Confidence: {result['confidence']}%")
                print(f"   Action: {result.get('action', 'N/A')}")
                print(f"   Reasoning: {result['reasoning'][:100]}...")
                print()
        else:
            print("❌ NO RESULTS - Something is still wrong!")

    else:
        print(f"❌ Error: {response.status_code}")
        print(response.text)

except Exception as e:
    print(f"❌ Error: {e}")

print("=" * 60)
