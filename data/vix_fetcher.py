"""
VIX Price Fetcher
=================
Yahoo first (free, reliable for VIX), Tradier backup.
Tradier sandbox may not support $VIX.X index quotes.
"""

import os
import logging

logger = logging.getLogger(__name__)


def get_vix_price() -> float:
    """Get VIX spot price."""

    # Yahoo FIRST - free, reliable, works for VIX
    try:
        import yfinance as yf
        vix = yf.Ticker("^VIX")
        hist = vix.history(period='5d')
        if not hist.empty:
            price = float(hist['Close'].iloc[-1])
            if price > 0:
                return price
    except Exception as e:
        logger.warning(f"Yahoo VIX failed: {e}")

    # Tradier backup (may not work in sandbox for index quotes)
    try:
        from data.tradier_data_fetcher import TradierDataFetcher
        use_sandbox = os.getenv('TRADIER_SANDBOX', 'true').lower() == 'true'
        tradier = TradierDataFetcher(sandbox=use_sandbox)

        vix_quote = tradier.get_quote("$VIX.X")
        if vix_quote and vix_quote.get('last'):
            return float(vix_quote['last'])
    except Exception as e:
        logger.warning(f"Tradier VIX failed: {e}")

    raise Exception("Could not get VIX price")


def get_vix_with_source() -> tuple:
    """Get VIX with source name."""

    # Yahoo FIRST
    try:
        import yfinance as yf
        vix = yf.Ticker("^VIX")
        hist = vix.history(period='5d')
        if not hist.empty:
            price = float(hist['Close'].iloc[-1])
            if price > 0:
                return price, 'yahoo'
    except Exception as e:
        logger.warning(f"Yahoo VIX failed: {e}")

    # Tradier backup
    try:
        from data.tradier_data_fetcher import TradierDataFetcher
        use_sandbox = os.getenv('TRADIER_SANDBOX', 'true').lower() == 'true'
        tradier = TradierDataFetcher(sandbox=use_sandbox)

        vix_quote = tradier.get_quote("$VIX.X")
        if vix_quote and vix_quote.get('last'):
            return float(vix_quote['last']), 'tradier'
    except Exception as e:
        logger.warning(f"Tradier VIX failed: {e}")

    raise Exception("Could not get VIX price")
