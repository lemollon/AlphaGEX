"""
VIX Price Fetcher - Direct HTTP, no fancy libraries
"""

import requests
import logging

logger = logging.getLogger(__name__)


def get_vix_price() -> float:
    """Get VIX spot price via direct HTTP."""

    # Method 1: Yahoo Finance direct API (no library needed)
    try:
        url = "https://query1.finance.yahoo.com/v8/finance/chart/%5EVIX"
        resp = requests.get(url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
        if resp.status_code == 200:
            data = resp.json()
            price = data['chart']['result'][0]['meta']['regularMarketPrice']
            if price and price > 0:
                return float(price)
    except Exception as e:
        logger.warning(f"Yahoo direct API failed: {e}")

    # Method 2: Google Finance
    try:
        url = "https://www.google.com/finance/quote/VIX:INDEXCBOE"
        resp = requests.get(url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
        if resp.status_code == 200:
            import re
            match = re.search(r'data-last-price="([0-9.]+)"', resp.text)
            if match:
                price = float(match.group(1))
                if price > 0:
                    return price
    except Exception as e:
        logger.warning(f"Google Finance failed: {e}")

    # Method 3: Tradier (if configured)
    try:
        import os
        from data.tradier_data_fetcher import TradierDataFetcher
        use_sandbox = os.getenv('TRADIER_SANDBOX', 'true').lower() == 'true'
        tradier = TradierDataFetcher(sandbox=use_sandbox)
        vix_quote = tradier.get_quote("$VIX.X")
        if vix_quote and vix_quote.get('last'):
            return float(vix_quote['last'])
    except Exception as e:
        logger.warning(f"Tradier failed: {e}")

    raise Exception("Could not get VIX price")


def get_vix_with_source() -> tuple:
    """Get VIX with source name."""

    # Yahoo direct
    try:
        url = "https://query1.finance.yahoo.com/v8/finance/chart/%5EVIX"
        resp = requests.get(url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
        if resp.status_code == 200:
            data = resp.json()
            price = data['chart']['result'][0]['meta']['regularMarketPrice']
            if price and price > 0:
                return float(price), 'yahoo'
    except Exception as e:
        logger.warning(f"Yahoo direct API failed: {e}")

    # Google Finance
    try:
        url = "https://www.google.com/finance/quote/VIX:INDEXCBOE"
        resp = requests.get(url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
        if resp.status_code == 200:
            import re
            match = re.search(r'data-last-price="([0-9.]+)"', resp.text)
            if match:
                price = float(match.group(1))
                if price > 0:
                    return price, 'google'
    except Exception as e:
        logger.warning(f"Google Finance failed: {e}")

    # Tradier
    try:
        import os
        from data.tradier_data_fetcher import TradierDataFetcher
        use_sandbox = os.getenv('TRADIER_SANDBOX', 'true').lower() == 'true'
        tradier = TradierDataFetcher(sandbox=use_sandbox)
        vix_quote = tradier.get_quote("$VIX.X")
        if vix_quote and vix_quote.get('last'):
            return float(vix_quote['last']), 'tradier'
    except Exception as e:
        logger.warning(f"Tradier failed: {e}")

    raise Exception("Could not get VIX price")
