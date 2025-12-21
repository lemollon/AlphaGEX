"""
VIX Price Fetcher - RELIABLE, NO FAKE FALLBACKS
================================================

This module fetches VIX spot price from multiple sources.
It NEVER returns a hardcoded fallback value.
If all sources fail, it raises an exception.

Sources (in order):
1. Tradier API ($VIX.X) - Primary, real-time
2. Yahoo Finance (^VIX) - Free, reliable backup
3. Cache - Recent valid value (max 5 min old)

Usage:
    from data.vix_fetcher import get_vix_price

    vix = get_vix_price()  # Returns float or raises VIXFetchError
"""

import os
import time
import logging
from typing import Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)

# Cache for VIX value - avoid hammering APIs
_vix_cache: dict = {
    'value': None,
    'timestamp': 0,
    'source': None
}
_CACHE_TTL = 60  # 1 minute cache


class VIXFetchError(Exception):
    """Raised when VIX cannot be fetched from any source"""
    pass


def _fetch_from_tradier() -> Tuple[Optional[float], str]:
    """Fetch VIX from Tradier API"""
    try:
        from data.tradier_data_fetcher import TradierDataFetcher
        tradier = TradierDataFetcher()

        quote = tradier.get_quote('$VIX.X')
        if quote:
            price = quote.get('last') or quote.get('close')
            if price and float(price) > 0:
                return float(price), 'tradier'
    except Exception as e:
        logger.debug(f"Tradier VIX fetch failed: {e}")

    return None, 'tradier'


def _fetch_from_yahoo() -> Tuple[Optional[float], str]:
    """Fetch VIX from Yahoo Finance (FREE)"""
    try:
        import yfinance as yf

        vix = yf.Ticker("^VIX")

        # Try fast_info first (faster)
        try:
            price = vix.fast_info.get('lastPrice') or vix.fast_info.get('regularMarketPrice')
            if price and float(price) > 0:
                return float(price), 'yahoo'
        except:
            pass

        # Try info dict
        try:
            info = vix.info
            price = info.get('regularMarketPrice') or info.get('previousClose')
            if price and float(price) > 0:
                return float(price), 'yahoo'
        except:
            pass

        # Try history (always works)
        hist = vix.history(period='1d')
        if not hist.empty:
            price = float(hist['Close'].iloc[-1])
            if price > 0:
                return price, 'yahoo'

    except ImportError:
        logger.warning("yfinance not installed - run: pip install yfinance")
    except Exception as e:
        logger.debug(f"Yahoo VIX fetch failed: {e}")

    return None, 'yahoo'


def _get_cached() -> Optional[float]:
    """Get cached VIX value if still valid"""
    if _vix_cache['value'] and _vix_cache['timestamp']:
        age = time.time() - _vix_cache['timestamp']
        if age < _CACHE_TTL:
            return _vix_cache['value']
    return None


def _set_cache(value: float, source: str):
    """Cache VIX value"""
    _vix_cache['value'] = value
    _vix_cache['timestamp'] = time.time()
    _vix_cache['source'] = source


def get_vix_price(use_cache: bool = True) -> float:
    """
    Get current VIX spot price.

    Tries multiple sources in order. NEVER returns a fake/hardcoded value.
    Raises VIXFetchError if all sources fail.

    Args:
        use_cache: If True, return cached value if available (default: True)

    Returns:
        float: Current VIX spot price

    Raises:
        VIXFetchError: If VIX cannot be fetched from any source
    """
    # Check cache first
    if use_cache:
        cached = _get_cached()
        if cached:
            logger.debug(f"VIX from cache: {cached}")
            return cached

    errors = []

    # Try Tradier first
    vix, source = _fetch_from_tradier()
    if vix:
        logger.info(f"VIX from Tradier: {vix}")
        _set_cache(vix, source)
        return vix
    errors.append("Tradier: No quote returned")

    # Try Yahoo Finance
    vix, source = _fetch_from_yahoo()
    if vix:
        logger.info(f"VIX from Yahoo: {vix}")
        _set_cache(vix, source)
        return vix
    errors.append("Yahoo: No quote returned")

    # All sources failed - check if we have a recent cache (up to 5 min old)
    if _vix_cache['value'] and _vix_cache['timestamp']:
        age = time.time() - _vix_cache['timestamp']
        if age < 300:  # 5 minutes
            logger.warning(f"All VIX sources failed, using {age:.0f}s old cache: {_vix_cache['value']}")
            return _vix_cache['value']

    # Complete failure - raise exception, do NOT return fake data
    error_msg = f"VIX fetch failed from all sources: {'; '.join(errors)}"
    logger.error(error_msg)
    raise VIXFetchError(error_msg)


def get_vix_with_source() -> Tuple[float, str]:
    """
    Get VIX price with source information.

    Returns:
        Tuple of (vix_price, source_name)

    Raises:
        VIXFetchError: If VIX cannot be fetched
    """
    # Check cache
    cached = _get_cached()
    if cached:
        return cached, f"{_vix_cache['source']}_cached"

    # Try sources
    vix, source = _fetch_from_tradier()
    if vix:
        _set_cache(vix, source)
        return vix, source

    vix, source = _fetch_from_yahoo()
    if vix:
        _set_cache(vix, source)
        return vix, source

    raise VIXFetchError("All VIX sources failed")


# Convenience function for backwards compatibility
def get_vix() -> float:
    """Get VIX price. Raises VIXFetchError on failure."""
    return get_vix_price()
