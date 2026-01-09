"""
VIX Price Fetcher - Multi-source with robust fallbacks

Priority order:
1. Tradier (production data source - most reliable)
2. Yahoo Finance direct API
3. Google Finance scraping
4. Fallback default value

IMPORTANT: Never raises exceptions - always returns a value so signal
generation can continue. Uses 'source' field to indicate data quality.
"""

import os
import re
import requests
import logging

logger = logging.getLogger(__name__)

# Default VIX value when all sources fail
DEFAULT_VIX = 18.0


def get_vix_from_tradier() -> tuple:
    """Get VIX from Tradier - primary production source."""
    try:
        from data.tradier_data_fetcher import TradierDataFetcher

        # Use production API for VIX data (not sandbox)
        use_sandbox = os.getenv('TRADIER_SANDBOX', 'false').lower() == 'true'
        tradier = TradierDataFetcher(sandbox=use_sandbox)

        # VIX index symbol in Tradier
        vix_quote = tradier.get_quote("$VIX.X")
        if vix_quote and vix_quote.get('last'):
            price = float(vix_quote['last'])
            if 5 < price < 100:  # Sanity check
                logger.debug(f"VIX from Tradier: {price}")
                return price, 'tradier'
    except Exception as e:
        logger.warning(f"Tradier VIX failed: {e}")
    return None, None


def get_vix_from_yahoo() -> tuple:
    """Get VIX from Yahoo Finance direct API."""
    try:
        url = "https://query1.finance.yahoo.com/v8/finance/chart/%5EVIX"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        resp = requests.get(url, timeout=10, headers=headers)
        if resp.status_code == 200:
            data = resp.json()
            price = data['chart']['result'][0]['meta']['regularMarketPrice']
            if price and 5 < price < 100:  # Sanity check
                logger.debug(f"VIX from Yahoo: {price}")
                return float(price), 'yahoo'
    except Exception as e:
        logger.warning(f"Yahoo VIX failed: {e}")
    return None, None


def get_vix_from_google() -> tuple:
    """Get VIX from Google Finance (scraping)."""
    try:
        url = "https://www.google.com/finance/quote/VIX:INDEXCBOE"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        resp = requests.get(url, timeout=10, headers=headers)
        if resp.status_code == 200:
            # Try multiple regex patterns for robustness
            patterns = [
                r'data-last-price="([0-9.]+)"',
                r'"price":\s*"?\$?([0-9.]+)"?',
                r'class="YMlKec fxKbKc"[^>]*>([0-9.]+)',
            ]
            for pattern in patterns:
                match = re.search(pattern, resp.text)
                if match:
                    price = float(match.group(1))
                    if 5 < price < 100:  # Sanity check
                        logger.debug(f"VIX from Google: {price}")
                        return price, 'google'
    except Exception as e:
        logger.warning(f"Google VIX failed: {e}")
    return None, None


def get_vix_price() -> float:
    """
    Get VIX spot price from best available source.

    Returns:
        float: VIX price (never raises, uses fallback if needed)
    """
    # Try sources in priority order
    price, source = get_vix_from_tradier()
    if price:
        return price

    price, source = get_vix_from_yahoo()
    if price:
        return price

    price, source = get_vix_from_google()
    if price:
        return price

    # Fallback
    logger.warning(f"All VIX sources failed - using default {DEFAULT_VIX}")
    return DEFAULT_VIX


def get_vix_with_source() -> tuple:
    """
    Get VIX with source name for tracking data quality.

    Returns:
        tuple: (price, source) where source is one of:
            - 'tradier' (production data)
            - 'yahoo' (direct API)
            - 'google' (scraped)
            - 'fallback' (default value)

    NOTE: This function NEVER raises an exception. If all sources fail,
    it returns (DEFAULT_VIX, 'fallback') so signal generation can continue.
    """
    # Try sources in priority order

    # 1. Tradier (most reliable for production)
    price, source = get_vix_from_tradier()
    if price:
        return price, source

    # 2. Yahoo Finance direct API
    price, source = get_vix_from_yahoo()
    if price:
        return price, source

    # 3. Google Finance scraping
    price, source = get_vix_from_google()
    if price:
        return price, source

    # 4. Fallback - NEVER raise an exception
    logger.warning(f"All VIX sources failed - using fallback default {DEFAULT_VIX}")
    return DEFAULT_VIX, 'fallback'
