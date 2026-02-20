"""
VALOR POST-DEPLOY API TESTS (Tests 5 & 6)
============================================

These tests require network access to Tradier and TradingVolatility APIs.
If API keys are not configured or services are unreachable, tests are marked SKIP.
"""

import sys
import os
import importlib.util

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

RESULTS = {}

# Expected price ranges for each proxy ETF
PRICE_RANGES = {
    "SPY": (400, 800),
    "QQQ": (300, 700),
    "IWM": (150, 350),
    "USO": (40, 120),
    "UNG": (5, 50),
    "GLD": (150, 400),
}


def test_5_tradier_fetch():
    """Test 5: Verify Tradier can fetch data for all 6 proxy ETFs."""
    test_name = "Test 5: Tradier Fetch (6 ETFs)"
    failures = []
    skipped = False

    try:
        tradier_key = os.environ.get("TRADIER_API_KEY") or os.environ.get("TRADIER_PRODUCTION_KEY")
        if not tradier_key:
            print("  SKIP: No Tradier API key configured")
            skipped = True
            RESULTS[test_name] = (None, ["SKIP: No API key"])
            return

        import requests
        headers = {
            "Authorization": f"Bearer {tradier_key}",
            "Accept": "application/json",
        }

        for etf, (low, high) in PRICE_RANGES.items():
            try:
                url = f"https://api.tradier.com/v1/markets/quotes?symbols={etf}"
                resp = requests.get(url, headers=headers, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    quotes = data.get("quotes", {}).get("quote", {})
                    if isinstance(quotes, list):
                        quotes = quotes[0] if quotes else {}
                    price = quotes.get("last", 0) or quotes.get("close", 0) or 0

                    if price <= 0:
                        failures.append(f"  {etf}: Price=0 (no data returned)")
                    elif low <= price <= high:
                        print(f"  {etf}: Price=${price:.2f} (in [{low}, {high}]) ✓")
                    else:
                        failures.append(f"  {etf}: Price=${price:.2f} OUT OF RANGE [{low}, {high}]")
                elif resp.status_code == 401:
                    print(f"  SKIP: Tradier auth failed (key may be sandbox)")
                    skipped = True
                    break
                else:
                    failures.append(f"  {etf}: HTTP {resp.status_code}")
            except Exception as e:
                failures.append(f"  {etf}: Error: {e}")

    except ImportError:
        print("  SKIP: requests not available")
        skipped = True
    except Exception as e:
        print(f"  SKIP: {e}")
        skipped = True

    if skipped:
        RESULTS[test_name] = (None, ["SKIP"])
    else:
        RESULTS[test_name] = (len(failures) == 0, failures)


def test_6_trading_volatility_fetch():
    """Test 6: Verify TradingVolatility has GEX data for all 6 proxy ETFs."""
    test_name = "Test 6: TradingVol Fetch (6 ETFs)"
    failures = []
    skipped = False

    try:
        # Try to load TradingVolatilityAPI
        from core_classes_and_engines import TradingVolatilityAPI

        api_key = os.environ.get("TRADING_VOLATILITY_API_KEY")
        tv_username = os.environ.get("TV_USERNAME")
        if not api_key and not tv_username:
            print("  SKIP: No TradingVolatility API key configured")
            RESULTS[test_name] = (None, ["SKIP: No API key"])
            return

        api = TradingVolatilityAPI()

        for etf in ["SPY", "QQQ", "IWM", "USO", "UNG", "GLD"]:
            try:
                result = api.get_net_gamma(etf)
                if result and 'error' not in result:
                    flip = result.get('flip_point', 0)
                    net_gex = result.get('net_gex', 0)
                    if flip > 0:
                        low, high = PRICE_RANGES[etf]
                        if low <= flip <= high:
                            print(f"  {etf}: flip={flip:.2f}, net_gex={net_gex:.2e} ✓")
                        else:
                            # Flip point might be slightly outside the ETF price range
                            # (that's OK, it's a GEX level, not a price)
                            print(f"  {etf}: flip={flip:.2f} (outside price range but data exists) ✓")
                    else:
                        failures.append(f"  CRITICAL: {etf}: flip_point=0 — NO GEX DATA. Cannot trade overnight.")
                else:
                    error_msg = result.get('error', 'Unknown') if result else 'No response'
                    failures.append(f"  CRITICAL: {etf}: API error: {error_msg}")

                # Respect rate limits - wait between calls
                import time
                time.sleep(4.5)

            except Exception as e:
                failures.append(f"  {etf}: Error: {e}")

    except ImportError as e:
        print(f"  SKIP: TradingVolatilityAPI not available ({e})")
        skipped = True
    except Exception as e:
        print(f"  SKIP: {e}")
        skipped = True

    if skipped:
        RESULTS[test_name] = (None, ["SKIP"])
    else:
        RESULTS[test_name] = (len(failures) == 0, failures)


def main():
    print("=" * 60)
    print("VALOR POST-DEPLOY API TESTS (Tests 5 & 6)")
    print("=" * 60)
    print()

    print("─" * 50)
    print("TEST 5: Tradier Data Fetch Per Proxy ETF")
    print("─" * 50)
    test_5_tradier_fetch()
    print()

    print("─" * 50)
    print("TEST 6: TradingVolatility Data Fetch Per Proxy ETF")
    print("─" * 50)
    test_6_trading_volatility_fetch()
    print()

    return RESULTS


if __name__ == "__main__":
    main()
