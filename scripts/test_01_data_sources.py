#!/usr/bin/env python3
"""
TEST 01: Data Sources
Tests Polygon API and Trading Volatility API connectivity.

Run: python scripts/test_01_data_sources.py
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta

print("\n" + "="*60)
print(" TEST 01: DATA SOURCES")
print("="*60)

# =============================================================================
# 1. Check Environment Variables
# =============================================================================
print("\n--- Environment Variables ---")

polygon_key = os.getenv('POLYGON_API_KEY')
tv_key = os.getenv('TRADING_VOLATILITY_API_KEY') or os.getenv('TV_USERNAME')
db_url = os.getenv('DATABASE_URL')

print(f"POLYGON_API_KEY: {'✅ Set' if polygon_key else '❌ NOT SET'}")
print(f"TRADING_VOLATILITY_API_KEY: {'✅ Set' if tv_key else '❌ NOT SET'}")
print(f"DATABASE_URL: {'✅ Set' if db_url else '⚠️ Not set (will use SQLite)'}")

if not polygon_key:
    print("\n❌ POLYGON_API_KEY is required. Exiting.")
    sys.exit(1)

# =============================================================================
# 2. Test Polygon - VIX Data
# =============================================================================
print("\n--- Polygon: VIX Data (I:VIX) ---")

try:
    from data.polygon_data_fetcher import polygon_fetcher, get_vix_for_date

    # Test current VIX
    for ticker in ['I:VIX', 'VIX']:
        print(f"Trying {ticker}...")
        df = polygon_fetcher.get_price_history(ticker, days=10, timeframe='day')
        if df is not None and not df.empty:
            print(f"  ✅ {ticker} works! Got {len(df)} days")
            print(f"  Latest VIX: {df['Close'].iloc[-1]:.2f}")
            print(f"  Date range: {df.index[0]} to {df.index[-1]}")
            break
    else:
        print("  ❌ Could not fetch VIX from any ticker")

    # Test historical VIX lookup
    test_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    print(f"\nHistorical VIX for {test_date}:")
    vix_val = get_vix_for_date(test_date)
    if vix_val != 18.0:
        print(f"  ✅ VIX = {vix_val:.2f}")
    else:
        print(f"  ⚠️ Got fallback value 18.0")

except Exception as e:
    print(f"  ❌ Error: {e}")

# =============================================================================
# 3. Test Polygon - SPY Data
# =============================================================================
print("\n--- Polygon: SPY Price Data ---")

try:
    from data.polygon_data_fetcher import polygon_fetcher, get_spx_returns

    df = polygon_fetcher.get_price_history('SPY', days=30, timeframe='day')
    if df is not None and not df.empty:
        print(f"  ✅ Got {len(df)} days of SPY data")
        print(f"  Latest close: ${df['Close'].iloc[-1]:.2f}")
        print(f"  Date range: {df.index[0]} to {df.index[-1]}")

        # Test returns calculation
        returns = get_spx_returns()
        print(f"  5-day return: {returns['5d_return']:.2f}%")
        print(f"  20-day return: {returns['20d_return']:.2f}%")
        print(f"  Distance from high: {returns['distance_from_high']:.2f}%")
    else:
        print("  ❌ No SPY data returned")

except Exception as e:
    print(f"  ❌ Error: {e}")

# =============================================================================
# 4. Test Polygon - SPX Options Data
# =============================================================================
print("\n--- Polygon: SPX Options Data ---")

try:
    from data.polygon_data_fetcher import polygon_fetcher

    # Try to get SPX options
    from datetime import date
    today = date.today()
    expiry = today + timedelta(days=45)

    # Format expiry for Polygon
    expiry_str = expiry.strftime('%y%m%d')

    # Try getting option chain
    symbol = 'SPX'
    print(f"  Checking options data availability for {symbol}...")

    # Check if we can get any option data
    test_option = f"O:{symbol}{expiry_str}P00580000"
    print(f"  Testing option ticker format: {test_option}")

    # This is informational - options data requires Polygon options subscription
    print("  ℹ️ Options data requires Polygon Options subscription")

except Exception as e:
    print(f"  ❌ Error: {e}")

# =============================================================================
# 5. Test Trading Volatility - GEX Data
# =============================================================================
print("\n--- Trading Volatility: GEX Data ---")

try:
    from data.polygon_data_fetcher import get_gex_data, get_gex_data_quality

    result = get_gex_data('SPY')

    if 'error' not in result:
        print(f"  ✅ GEX data retrieved!")
        print(f"  Net GEX: {result.get('net_gex', 'N/A')}")
        print(f"  Put Wall: {result.get('put_wall', 'N/A')}")
        print(f"  Call Wall: {result.get('call_wall', 'N/A')}")
        print(f"  Source: {result.get('source', 'N/A')}")
    else:
        print(f"  ⚠️ GEX unavailable: {result.get('error')}")

    quality = get_gex_data_quality()
    print(f"  Stats: {quality}")

except Exception as e:
    print(f"  ❌ Error: {e}")

# =============================================================================
# 6. Test IV Rank Calculation
# =============================================================================
print("\n--- IV Rank Calculation ---")

try:
    from data.polygon_data_fetcher import calculate_iv_rank

    # Test with current VIX level
    current_iv = 0.15  # 15% IV
    iv_rank = calculate_iv_rank('SPY', current_iv)
    print(f"  IV Rank for 15% IV: {iv_rank:.1f}%")

    current_iv = 0.25  # 25% IV
    iv_rank = calculate_iv_rank('SPY', current_iv)
    print(f"  IV Rank for 25% IV: {iv_rank:.1f}%")

except Exception as e:
    print(f"  ❌ Error: {e}")

# =============================================================================
# 7. Test Full ML Features
# =============================================================================
print("\n--- Full ML Feature Extraction ---")

try:
    from data.polygon_data_fetcher import get_ml_features_for_trade

    test_date = (datetime.now() - timedelta(days=14)).strftime('%Y-%m-%d')

    features = get_ml_features_for_trade(
        trade_date=test_date,
        strike=580.0,
        underlying_price=600.0,
        option_iv=0.16
    )

    print(f"  Trade date: {features.get('trade_date')}")
    print(f"  VIX: {features.get('vix'):.2f}")
    print(f"  IV Rank: {features.get('iv_rank'):.1f}%")
    print(f"  VIX Percentile: {features.get('vix_percentile'):.1f}%")
    print(f"  SPX 5d Return: {features.get('spx_5d_return'):.2f}%")
    print(f"  SPX 20d Return: {features.get('spx_20d_return'):.2f}%")
    print(f"  Net GEX: {features.get('net_gex')}")
    print(f"  Put Wall Distance: {features.get('put_wall_distance_pct'):.2f}%")
    print(f"  Data Quality: {features.get('data_quality_pct'):.1f}%")

    print("\n  Data Sources:")
    for source, status in features.get('data_sources', {}).items():
        icon = "✅" if status in ['POLYGON', 'CALCULATED', 'TRADING_VOLATILITY', 'VIX_PROXY'] else "⚠️"
        print(f"    {icon} {source}: {status}")

except Exception as e:
    print(f"  ❌ Error: {e}")
    import traceback
    traceback.print_exc()

# =============================================================================
# Summary
# =============================================================================
print("\n" + "="*60)
print(" DATA SOURCES TEST COMPLETE")
print("="*60 + "\n")
