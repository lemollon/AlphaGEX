"""
Singleton Data Fetchers for Performance Optimization

PERFORMANCE FIX: This module provides singleton instances of expensive-to-create
API client objects. Creating these objects per-request caused:
- Unnecessary connection overhead
- Repeated credential loading
- Connection pool churn

Usage:
    from backend.api.singletons import get_tradier_client, get_tradier_data_fetcher

Instead of:
    client = TradierDataFetcher()  # Creates new instance every call

Use:
    client = get_tradier_data_fetcher()  # Returns cached singleton
"""

import threading
from typing import Optional

# Module-level singletons (lazy-initialized)
_tradier_data_fetcher: Optional['TradierDataFetcher'] = None
_tradier_client: Optional['TradierClient'] = None
_trading_volatility_api: Optional['TradingVolatilityAPI'] = None
_lock = threading.Lock()


def get_tradier_data_fetcher() -> Optional['TradierDataFetcher']:
    """
    Get singleton TradierDataFetcher instance.

    PERFORMANCE FIX: Reuses single instance instead of creating new per request.
    Thread-safe via lock.
    """
    global _tradier_data_fetcher

    if _tradier_data_fetcher is None:
        with _lock:
            # Double-check locking pattern
            if _tradier_data_fetcher is None:
                try:
                    from data.tradier_data_fetcher import TradierDataFetcher
                    _tradier_data_fetcher = TradierDataFetcher()
                except ImportError as e:
                    print(f"Warning: TradierDataFetcher not available: {e}")
                    return None

    return _tradier_data_fetcher


def get_tradier_client() -> Optional['TradierClient']:
    """
    Get singleton TradierClient instance.

    PERFORMANCE FIX: Reuses single instance instead of creating new per request.
    Thread-safe via lock.
    """
    global _tradier_client

    if _tradier_client is None:
        with _lock:
            if _tradier_client is None:
                try:
                    from data.tradier_data_fetcher import TradierClient
                    _tradier_client = TradierClient()
                except ImportError as e:
                    print(f"Warning: TradierClient not available: {e}")
                    return None

    return _tradier_client


def get_trading_volatility_api() -> Optional['TradingVolatilityAPI']:
    """
    Get singleton TradingVolatilityAPI instance.

    PERFORMANCE FIX: Reuses single instance instead of creating new per request.
    Thread-safe via lock.
    """
    global _trading_volatility_api

    if _trading_volatility_api is None:
        with _lock:
            if _trading_volatility_api is None:
                try:
                    from core_classes_and_engines import TradingVolatilityAPI
                    _trading_volatility_api = TradingVolatilityAPI()
                except ImportError as e:
                    print(f"Warning: TradingVolatilityAPI not available: {e}")
                    return None

    return _trading_volatility_api


def reset_singletons():
    """
    Reset all singletons (useful for testing or reconnection).
    """
    global _tradier_data_fetcher, _tradier_client, _trading_volatility_api

    with _lock:
        _tradier_data_fetcher = None
        _tradier_client = None
        _trading_volatility_api = None
