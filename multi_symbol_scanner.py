"""
Multi-Symbol Scanner with Smart Caching
Scans multiple symbols for trading opportunities while respecting API limits

This module provides logic-only scanning functionality.
UI rendering has been removed - use the backend API for scanner views.
"""

from typing import List, Dict, Optional
import pandas as pd
from datetime import datetime, timedelta
import time
import logging

logger = logging.getLogger(__name__)


class SmartCache:
    """Intelligent caching system to minimize API calls"""

    def __init__(self, cache_duration_minutes: int = 5):
        """
        Initialize cache with configurable duration

        Args:
            cache_duration_minutes: How long to cache data before refresh
        """
        self._cache: Dict[str, Dict] = {}
        self._timestamps: Dict[str, datetime] = {}
        self.cache_duration = timedelta(minutes=cache_duration_minutes)

    def get(self, symbol: str) -> Optional[Dict]:
        """Get cached data for symbol if still valid"""
        if symbol not in self._cache:
            return None

        timestamp = self._timestamps.get(symbol)
        if not timestamp:
            return None

        # Check if cache is still valid
        if datetime.now() - timestamp < self.cache_duration:
            return self._cache[symbol]

        return None

    def set(self, symbol: str, data: Dict):
        """Cache data for symbol"""
        self._cache[symbol] = data
        self._timestamps[symbol] = datetime.now()

    def get_cache_age(self, symbol: str) -> str:
        """Get human-readable cache age"""
        timestamp = self._timestamps.get(symbol)
        if not timestamp:
            return "Never"

        age = datetime.now() - timestamp
        if age.seconds < 60:
            return f"{age.seconds}s ago"
        elif age.seconds < 3600:
            return f"{age.seconds // 60}m ago"
        else:
            return f"{age.seconds // 3600}h ago"

    def clear(self, symbol: str = None):
        """Clear cache for specific symbol or all symbols"""
        if symbol:
            self._cache.pop(symbol, None)
            self._timestamps.pop(symbol, None)
        else:
            self._cache = {}
            self._timestamps = {}


# Module-level cache instance
_cache: Optional[SmartCache] = None


def get_cache(cache_duration_minutes: int = 5) -> SmartCache:
    """Get or create the smart cache instance"""
    global _cache
    if _cache is None:
        _cache = SmartCache(cache_duration_minutes)
    return _cache


def scan_symbols(symbols: List[str], api_client, force_refresh: bool = False,
                 progress_callback=None) -> pd.DataFrame:
    """
    Scan multiple symbols for trading opportunities

    Args:
        symbols: List of ticker symbols to scan
        api_client: Trading Volatility API client
        force_refresh: Bypass cache and fetch fresh data
        progress_callback: Optional callback(symbol, idx, total) for progress updates

    Returns:
        DataFrame with scan results
    """

    cache = get_cache()
    results = []

    for idx, symbol in enumerate(symbols):
        if progress_callback:
            progress_callback(symbol, idx, len(symbols))

        # Try to get from cache first
        cached_data = None if force_refresh else cache.get(symbol)

        if cached_data:
            # Use cached data
            scan_result = cached_data
            scan_result['cache_status'] = f"Cached ({cache.get_cache_age(symbol)})"
        else:
            # Fetch fresh data with retry logic for timeouts
            try:
                max_retries = 2
                retry_count = 0
                gex_data = None

                while retry_count <= max_retries:
                    try:
                        # ONLY fetch GEX data - skip skew_data to reduce API calls
                        gex_data = api_client.get_net_gamma(symbol)

                        # Check if we got valid data
                        if gex_data and 'error' not in gex_data:
                            break  # Success, exit retry loop

                        # If error in response, retry
                        retry_count += 1
                        if retry_count <= max_retries:
                            time.sleep(2)  # Brief pause before retry
                            continue
                        else:
                            break  # Exhausted retries

                    except Exception as e:
                        error_msg = str(e).lower()
                        # If timeout error, retry
                        if 'timeout' in error_msg or 'timed out' in error_msg:
                            retry_count += 1
                            if retry_count <= max_retries:
                                logger.warning(f"{symbol}: Timeout, retrying... ({retry_count}/{max_retries})")
                                time.sleep(3)  # Wait before retry
                                continue
                        # Non-timeout error, break out
                        raise

                # Process data if we got it
                if gex_data and 'error' not in gex_data:
                    # Import here to avoid circular dependency
                    from visualization_and_plans import StrategyEngine

                    strategy_engine = StrategyEngine()
                    setups = strategy_engine.detect_setups(gex_data)

                    # Get best setup (highest confidence)
                    best_setup = max(setups, key=lambda x: x.get('confidence', 0)) if setups else None

                    # Calculate expiration date from DTE
                    dte_value = best_setup.get('dte', 0) if best_setup else 0
                    if isinstance(dte_value, (int, float)) and dte_value > 0:
                        exp_date = (datetime.now() + timedelta(days=int(dte_value))).strftime('%Y-%m-%d')
                        dte_display = f"{int(dte_value)}d ({exp_date})"
                    else:
                        dte_display = 'N/A'

                    scan_result = {
                        'symbol': symbol,
                        'spot_price': gex_data.get('spot_price') or 0,
                        'net_gex': (gex_data.get('net_gex') or 0) / 1e9,  # In billions
                        'flip_point': gex_data.get('flip_point') or 0,
                        'distance_to_flip': ((gex_data.get('flip_point', 0) - gex_data.get('spot_price', 0)) /
                                             gex_data.get('spot_price', 1) * 100) if gex_data.get('spot_price') else 0,
                        'setup_type': best_setup.get('strategy', 'N/A') if best_setup else 'N/A',
                        'confidence': best_setup.get('confidence', 0) if best_setup else 0,
                        'dte': dte_display,
                        'action': best_setup.get('action', 'N/A') if best_setup else 'N/A',
                        'cache_status': 'Fresh',
                        'timestamp': datetime.now()
                    }

                    # Cache the result
                    cache.set(symbol, scan_result)

                else:
                    # Failed to get data after retries
                    raise Exception(gex_data.get('error', 'Unknown error') if gex_data else 'Failed to fetch data')

            except Exception as e:
                error_msg = str(e)
                logger.warning(f"{symbol}: {error_msg[:100]}")

                scan_result = {
                    'symbol': symbol,
                    'spot_price': 0,
                    'net_gex': 0,
                    'flip_point': 0,
                    'distance_to_flip': 0,
                    'setup_type': 'Timeout' if "timeout" in error_msg.lower() else 'Error',
                    'confidence': 0,
                    'dte': 'N/A',
                    'action': 'Retry later',
                    'cache_status': 'Error',
                    'timestamp': datetime.now()
                }

        results.append(scan_result)

    # Convert to DataFrame
    df = pd.DataFrame(results)

    return df


def get_top_opportunities(df: pd.DataFrame, top_n: int = 3) -> List[Dict]:
    """
    Get top trading opportunities from scan results

    Args:
        df: DataFrame from scan_symbols
        top_n: Number of top opportunities to return

    Returns:
        List of top opportunity dictionaries
    """
    if df.empty:
        return []

    # Sort by confidence (best opportunities first)
    df_sorted = df.sort_values('confidence', ascending=False)
    top_df = df_sorted.head(top_n)

    opportunities = []
    for idx, row in top_df.iterrows():
        conf = row['confidence']
        if conf >= 80:
            grade = "A"
        elif conf >= 70:
            grade = "B"
        else:
            grade = "C"

        opportunities.append({
            'rank': len(opportunities) + 1,
            'symbol': row['symbol'],
            'setup_type': row['setup_type'],
            'confidence': conf,
            'grade': grade,
            'dte': row['dte'],
            'action': row['action'],
            'spot_price': row['spot_price'],
            'net_gex': row['net_gex'],
            'distance_to_flip': row['distance_to_flip']
        })

    return opportunities


# Default watchlist
DEFAULT_WATCHLIST = ['SPY', 'QQQ', 'IWM', 'DIA', 'TSLA']
POPULAR_SYMBOLS = ['AAPL', 'MSFT', 'NVDA', 'AMD', 'AMZN', 'META', 'GOOGL', 'NFLX']
MAX_WATCHLIST_SIZE = 20
