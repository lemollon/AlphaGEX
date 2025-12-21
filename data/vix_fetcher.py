"""
VIX Price Fetcher
=================

Get VIX spot price. Tradier first, Yahoo backup. That's it.
"""

import logging

logger = logging.getLogger(__name__)


def get_vix_price() -> float:
    """Get VIX spot price from Tradier or Yahoo."""

    # Try Tradier
    try:
        from data.tradier_data_fetcher import TradierDataFetcher
        tradier = TradierDataFetcher()
        quote = tradier.get_quote('$VIX.X')
        if quote and quote.get('last'):
            return float(quote['last'])
    except:
        pass

    # Try Yahoo
    try:
        import yfinance as yf
        vix = yf.Ticker("^VIX")
        hist = vix.history(period='1d')
        if not hist.empty:
            return float(hist['Close'].iloc[-1])
    except:
        pass

    raise Exception("Could not get VIX price")


def get_vix_with_source() -> tuple:
    """Get VIX with source name."""

    # Try Tradier
    try:
        from data.tradier_data_fetcher import TradierDataFetcher
        tradier = TradierDataFetcher()
        quote = tradier.get_quote('$VIX.X')
        if quote and quote.get('last'):
            return float(quote['last']), 'tradier'
    except:
        pass

    # Try Yahoo
    try:
        import yfinance as yf
        vix = yf.Ticker("^VIX")
        hist = vix.history(period='1d')
        if not hist.empty:
            return float(hist['Close'].iloc[-1]), 'yahoo'
    except:
        pass

    raise Exception("Could not get VIX price")
