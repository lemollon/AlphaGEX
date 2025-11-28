#!/usr/bin/env python3
"""
Test Alpha Vantage API Integration
"""
import os
import requests
from dotenv import load_dotenv
import json

# Load environment variables
load_dotenv()

def test_alpha_vantage():
    """Test Alpha Vantage API with your API key"""

    api_key = os.getenv('ALPHA_VANTAGE_API_KEY')

    if not api_key:
        print("❌ ALPHA_VANTAGE_API_KEY not found in environment")
        return False

    print(f"✅ API Key loaded: {api_key[:10]}...")
    print(f"\n🔄 Testing Alpha Vantage API with SPY...")

    # Test API call
    url = "https://www.alphavantage.co/query"
    params = {
        "function": "TIME_SERIES_DAILY",
        "symbol": "SPY",
        "apikey": api_key,
        "outputsize": "compact"  # Last 100 data points
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        # Check for errors
        if 'Error Message' in data:
            print(f"❌ API Error: {data['Error Message']}")
            return False

        if 'Note' in data:
            print(f"⚠️ Rate Limit: {data['Note']}")
            return False

        # Check for data
        time_series = data.get('Time Series (Daily)', {})
        if not time_series:
            print(f"❌ No data received. Response: {json.dumps(data, indent=2)}")
            return False

        # Success!
        latest_date = list(time_series.keys())[0]
        latest_data = time_series[latest_date]

        print(f"\n✅ SUCCESS! Got {len(time_series)} days of SPY data")
        print(f"\n📊 Latest Data ({latest_date}):")
        print(f"   Open:  ${float(latest_data['1. open']):.2f}")
        print(f"   High:  ${float(latest_data['2. high']):.2f}")
        print(f"   Low:   ${float(latest_data['3. low']):.2f}")
        print(f"   Close: ${float(latest_data['4. close']):.2f}")
        print(f"   Volume: {int(float(latest_data['5. volume'])):,}")

        print(f"\n✅ Alpha Vantage is working correctly!")
        print(f"✅ You have 500 free API calls per day")

        return True

    except requests.exceptions.RequestException as e:
        print(f"❌ Network error: {e}")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


if __name__ == "__main__":
    print("=" * 70)
    print("Alpha Vantage API Test")
    print("=" * 70)

    success = test_alpha_vantage()

    print("\n" + "=" * 70)
    if success:
        print("✅ Test PASSED - Ready to use!")
    else:
        print("❌ Test FAILED - Check API key and connection")
    print("=" * 70)
