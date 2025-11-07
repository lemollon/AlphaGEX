"""
verify_api_access.py - Verify TradingVolatility API Access

This script tests the API connection and validates that credentials are properly configured.
"""

import os
import sys
from pathlib import Path

# Add the current directory to Python path
current_dir = Path(__file__).parent
if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))

from core_classes_and_engines import TradingVolatilityAPI


def verify_api_access():
    """
    Verify TradingVolatility API access is working correctly.

    Returns:
        bool: True if API is accessible, False otherwise
    """
    print("=" * 60)
    print("TradingVolatility API Access Verification")
    print("=" * 60)

    # Initialize API
    print("\n1. Initializing API client...")
    try:
        api = TradingVolatilityAPI()
        print("   ✓ API client initialized successfully")
    except Exception as e:
        print(f"   ✗ Failed to initialize API client: {e}")
        return False

    # Check API key configuration
    print("\n2. Checking API key configuration...")
    if not api.api_key:
        print("   ✗ No API key found!")
        print("   Please set one of the following:")
        print("   - Environment variable: TRADING_VOLATILITY_API_KEY")
        print("   - Streamlit secrets: tv_username")
        return False
    else:
        # Mask the API key for security
        masked_key = api.api_key[:4] + "*" * (len(api.api_key) - 8) + api.api_key[-4:] if len(api.api_key) > 8 else "****"
        print(f"   ✓ API key found: {masked_key}")

    # Test API connection with SPY
    print("\n3. Testing API connection with SPY...")
    try:
        data = api.get_net_gamma("SPY")

        if data and 'error' not in data:
            print("   ✓ API connection successful!")

            # Display some basic data
            print("\n4. API Response Summary:")
            print(f"   - Symbol: {data.get('symbol', 'N/A')}")
            print(f"   - Current Price: ${data.get('current_price', 'N/A')}")
            print(f"   - Net GEX: {data.get('net_gex', 'N/A'):,.0f}" if data.get('net_gex') else "   - Net GEX: N/A")
            print(f"   - Flip Point: ${data.get('flip_point', 'N/A')}")

            # Check rate limiting status
            stats = api.get_rate_limit_stats()
            print("\n5. API Usage Statistics:")
            print(f"   - Total API calls: {stats['total_calls']}")
            print(f"   - Calls this minute: {stats['calls_this_minute']}")
            print(f"   - Cached responses: {stats['cache_size']}")
            print(f"   - Time until minute reset: {stats['time_until_minute_reset']}s")

            print("\n" + "=" * 60)
            print("✓ API ACCESS VERIFIED SUCCESSFULLY")
            print("=" * 60)
            return True
        else:
            error_msg = data.get('error', 'Unknown error') if data else 'No data returned'
            print(f"   ✗ API request failed: {error_msg}")
            return False

    except Exception as e:
        print(f"   ✗ API connection test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = verify_api_access()
    sys.exit(0 if success else 1)
