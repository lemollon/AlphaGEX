"""
VIX Price Fetcher - Copy of ARES approach (which works)
"""

import os
import logging

logger = logging.getLogger(__name__)


def get_vix_price() -> float:
    """Get VIX spot price - same way ARES does it."""

    # Exactly how ARES does it (ares_routes.py line 393-400)
    try:
        from data.tradier_data_fetcher import TradierDataFetcher
        use_sandbox = os.getenv('TRADIER_SANDBOX', 'true').lower() == 'true'
        tradier = TradierDataFetcher(sandbox=use_sandbox)

        vix_quote = tradier.get_quote("$VIX.X")
        if vix_quote and vix_quote.get('last'):
            return float(vix_quote['last'])
    except Exception as e:
        logger.error(f"Tradier VIX failed: {e}")

    # Yahoo backup
    try:
        import yfinance as yf
        vix = yf.Ticker("^VIX")
        hist = vix.history(period='1d')
        if not hist.empty:
            return float(hist['Close'].iloc[-1])
    except Exception as e:
        logger.error(f"Yahoo VIX failed: {e}")

    raise Exception("Could not get VIX price from Tradier or Yahoo")


def get_vix_with_source() -> tuple:
    """Get VIX with source name."""

    try:
        from data.tradier_data_fetcher import TradierDataFetcher
        use_sandbox = os.getenv('TRADIER_SANDBOX', 'true').lower() == 'true'
        tradier = TradierDataFetcher(sandbox=use_sandbox)

        vix_quote = tradier.get_quote("$VIX.X")
        if vix_quote and vix_quote.get('last'):
            return float(vix_quote['last']), 'tradier'
    except Exception as e:
        logger.error(f"Tradier VIX failed: {e}")

    try:
        import yfinance as yf
        vix = yf.Ticker("^VIX")
        hist = vix.history(period='1d')
        if not hist.empty:
            return float(hist['Close'].iloc[-1]), 'yahoo'
    except Exception as e:
        logger.error(f"Yahoo VIX failed: {e}")

    raise Exception("Could not get VIX price from Tradier or Yahoo")
