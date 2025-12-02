#!/bin/bash
#
# DATA QUALITY TEST
#
# This script answers ONE question:
# "Is my system using REAL data or ESTIMATED data?"
#
# USAGE:
#   ./scripts/test_data_quality.sh
#

set -e

PROJECT_ROOT="$(dirname "$(dirname "$(realpath "$0")")")"
cd "$PROJECT_ROOT"

echo ""
echo "╔══════════════════════════════════════════════════════════════════════╗"
echo "║               DATA QUALITY VERIFICATION                              ║"
echo "╠══════════════════════════════════════════════════════════════════════╣"
echo "║  This test tells you if backtests use REAL or ESTIMATED data        ║"
echo "╚══════════════════════════════════════════════════════════════════════╝"
echo ""

python3 << 'PYTHON_EOF'
import os
import sys
sys.path.insert(0, os.getcwd())

from datetime import datetime, timedelta

# Tracking
real_data_sources = 0
total_sources = 0

print("Testing each data source...\n")

# =============================================================================
# 1. POLYGON API KEY
# =============================================================================
print("1. POLYGON API KEY")
api_key = os.getenv('POLYGON_API_KEY')
if api_key:
    print(f"   ✓ Set: {api_key[:8]}...")
    real_data_sources += 1
else:
    print(f"   ✗ NOT SET - export POLYGON_API_KEY=your_key")
total_sources += 1

# =============================================================================
# 2. SPX PRICE DATA
# =============================================================================
print("\n2. SPX PRICE DATA (Historical)")
try:
    from data.polygon_data_fetcher import polygon_fetcher
    df = polygon_fetcher.get_price_history('SPX', days=30)
    if df is not None and len(df) > 15:
        print(f"   ✓ REAL DATA: {len(df)} days from Polygon")
        real_data_sources += 1
    else:
        print(f"   ✗ FAILED: Only got {len(df) if df is not None else 0} days")
except Exception as e:
    print(f"   ✗ ERROR: {e}")
total_sources += 1

# =============================================================================
# 3. OPTION PRICES (Historical - FOR BACKTEST)
# =============================================================================
print("\n3. HISTORICAL OPTION PRICES (Critical for backtest accuracy)")
try:
    from data.polygon_data_fetcher import polygon_fetcher
    exp = (datetime.now() + timedelta(days=45)).strftime('%Y-%m-%d')
    start = (datetime.now() - timedelta(days=60)).strftime('%Y-%m-%d')
    end = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')

    hist = polygon_fetcher.get_historical_option_prices(
        'SPX', 5700, exp, 'put', start_date=start, end_date=end
    )

    if hist is not None and len(hist) > 0:
        print(f"   ✓ REAL DATA: {len(hist)} days of option prices")
        print(f"   This means backtests will use ACTUAL historical premiums!")
        real_data_sources += 1
    else:
        print(f"   ⚠ NO DATA: Backtests will use ESTIMATED prices")
        print(f"   Consider: Polygon Options tier subscription")
except Exception as e:
    print(f"   ✗ ERROR: {e}")
    print(f"   Backtests will use ESTIMATED prices")
total_sources += 1

# =============================================================================
# 4. LIVE OPTION QUOTES
# =============================================================================
print("\n4. LIVE OPTION QUOTES")
try:
    from data.polygon_data_fetcher import polygon_fetcher
    exp = (datetime.now() + timedelta(days=45)).strftime('%Y-%m-%d')
    quote = polygon_fetcher.get_option_quote('SPX', 5800, exp, 'put')

    if quote and (quote.get('bid', 0) > 0 or quote.get('last', 0) > 0):
        is_delayed = quote.get('is_delayed', False)
        source = "DELAYED (15-min)" if is_delayed else "REAL-TIME"
        print(f"   ✓ {source}: Bid=${quote.get('bid', 0):.2f}")
        real_data_sources += 1
    else:
        print(f"   ⚠ NO QUOTE (may be outside market hours)")
except Exception as e:
    print(f"   ✗ ERROR: {e}")
total_sources += 1

# =============================================================================
# VERDICT
# =============================================================================
print("\n" + "=" * 70)
print("VERDICT")
print("=" * 70)

pct = (real_data_sources / total_sources * 100) if total_sources > 0 else 0

if pct >= 75:
    print(f"""
    ╔══════════════════════════════════════════════════════════════╗
    ║  ✓ USING REAL DATA ({real_data_sources}/{total_sources} sources working)           ║
    ║                                                              ║
    ║  Your backtests and trading use actual market data.         ║
    ║  Confidence in results: HIGH                                 ║
    ╚══════════════════════════════════════════════════════════════╝
    """)
elif pct >= 50:
    print(f"""
    ╔══════════════════════════════════════════════════════════════╗
    ║  ⚠ PARTIAL REAL DATA ({real_data_sources}/{total_sources} sources working)          ║
    ║                                                              ║
    ║  Some data is real, some is estimated.                      ║
    ║  Check the failures above and fix them.                     ║
    ║  Confidence in results: MEDIUM                              ║
    ╚══════════════════════════════════════════════════════════════╝
    """)
else:
    print(f"""
    ╔══════════════════════════════════════════════════════════════╗
    ║  ✗ USING ESTIMATED DATA ({real_data_sources}/{total_sources} sources working)       ║
    ║                                                              ║
    ║  Most prices are estimates, not real market data.           ║
    ║  Fix the issues above before trusting results.              ║
    ║  Confidence in results: LOW                                 ║
    ╚══════════════════════════════════════════════════════════════╝
    """)

print("To fix issues:")
print("  1. Set POLYGON_API_KEY: export POLYGON_API_KEY=your_key")
print("  2. Check subscription: Polygon Options tier for historical options")
print("  3. Re-run this test: ./scripts/test_data_quality.sh")
print("")
PYTHON_EOF
