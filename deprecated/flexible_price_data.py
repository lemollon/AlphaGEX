"""
Flexible Price Data Fetcher with Multiple Sources and Auto-Fallback

This module provides a resilient data fetching system that:
1. Tries multiple data sources automatically
2. Handles yfinance API changes gracefully
3. Caches data aggressively to reduce API dependencies
4. Monitors health of each data source
5. Falls back to alternatives when primary source fails

Usage:
    from flexible_price_data import price_data_fetcher

    # Get price data (tries all sources until one works)
    data = price_data_fetcher.get_price_history('SPY', period='5d')

    # Check which sources are working
    health = price_data_fetcher.get_health_status()
"""

import time
import requests
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from functools import wraps
import os

try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False
    print("⚠️ yfinance not available")


class DataSourceHealth:
    """Track health of each data source"""

    def __init__(self):
        self.sources = {}

    def record_success(self, source: str):
        """Record successful data fetch"""
        if source not in self.sources:
            self.sources[source] = {
                'success_count': 0,
                'failure_count': 0,
                'last_success': None,
                'last_failure': None,
                'consecutive_failures': 0
            }

        self.sources[source]['success_count'] += 1
        self.sources[source]['last_success'] = datetime.now()
        self.sources[source]['consecutive_failures'] = 0

    def record_failure(self, source: str, error: str):
        """Record failed data fetch"""
        if source not in self.sources:
            self.sources[source] = {
                'success_count': 0,
                'failure_count': 0,
                'last_success': None,
                'last_failure': None,
                'consecutive_failures': 0,
                'last_error': None
            }

        self.sources[source]['failure_count'] += 1
        self.sources[source]['last_failure'] = datetime.now()
        self.sources[source]['consecutive_failures'] += 1
        self.sources[source]['last_error'] = error

    def is_healthy(self, source: str, threshold: int = 3) -> bool:
        """Check if source is healthy (not too many consecutive failures)"""
        if source not in self.sources:
            return True  # Unknown = give it a try

        return self.sources[source]['consecutive_failures'] < threshold

    def get_best_source(self, sources: List[str]) -> Optional[str]:
        """Get the healthiest source from a list"""
        healthy = [s for s in sources if self.is_healthy(s)]
        if not healthy:
            return sources[0] if sources else None

        # Sort by success rate
        def score(source):
            stats = self.sources.get(source, {})
            success = stats.get('success_count', 0)
            failure = stats.get('failure_count', 0)
            total = success + failure
            if total == 0:
                return 1.0  # Unknown = try it
            return success / total

        return max(healthy, key=score)

    def get_status(self) -> Dict:
        """Get health status of all sources"""
        return self.sources.copy()


class PriceDataCache:
    """Aggressive caching to reduce API dependency"""

    def __init__(self, ttl_seconds: int = 3600):
        self.cache = {}
        self.ttl = ttl_seconds

    def get(self, key: str) -> Optional[pd.DataFrame]:
        """Get cached data if still valid"""
        if key not in self.cache:
            return None

        data, timestamp = self.cache[key]
        if time.time() - timestamp > self.ttl:
            del self.cache[key]
            return None

        return data.copy()

    def set(self, key: str, data: pd.DataFrame):
        """Cache data"""
        self.cache[key] = (data.copy(), time.time())

    def clear(self):
        """Clear all cached data"""
        self.cache.clear()

    def get_stats(self) -> Dict:
        """Get cache statistics"""
        now = time.time()
        valid = sum(1 for _, ts in self.cache.values() if now - ts <= self.ttl)
        return {
            'total_entries': len(self.cache),
            'valid_entries': valid,
            'stale_entries': len(self.cache) - valid,
            'ttl_seconds': self.ttl
        }


class FlexiblePriceDataFetcher:
    """
    Flexible data fetcher that automatically tries multiple sources
    and adapts to API changes
    """

    def __init__(self, cache_ttl: int = 3600):
        self.health = DataSourceHealth()
        self.cache = PriceDataCache(ttl_seconds=cache_ttl)

        # API keys from environment
        self.alpha_vantage_key = os.getenv('ALPHA_VANTAGE_API_KEY')
        self.iexcloud_key = os.getenv('IEXCLOUD_API_KEY')
        self.polygon_key = os.getenv('POLYGON_API_KEY')
        self.twelve_data_key = os.getenv('TWELVE_DATA_API_KEY')

    def get_price_history(
        self,
        symbol: str,
        period: str = '5d',
        interval: str = '1d',
        max_retries: int = 3
    ) -> Optional[pd.DataFrame]:
        """
        Get price history using best available source

        Args:
            symbol: Stock symbol (e.g., 'SPY')
            period: Time period (e.g., '5d', '1mo', '1y')
            interval: Data interval (e.g., '1d', '1h', '5m')
            max_retries: Max retry attempts per source

        Returns:
            DataFrame with columns: Open, High, Low, Close, Volume
            None if all sources fail
        """
        # Check cache first
        cache_key = f"{symbol}_{period}_{interval}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            print(f"✅ Using cached price data for {symbol}")
            return cached

        # Define sources in priority order
        sources = ['yfinance', 'alpha_vantage', 'iexcloud', 'polygon', 'twelve_data']

        # Try best healthy source first
        best_source = self.health.get_best_source(sources)
        if best_source:
            sources.remove(best_source)
            sources.insert(0, best_source)

        # Try each source until one works
        for source in sources:
            if not self.health.is_healthy(source):
                print(f"⏭️  Skipping {source} (unhealthy)")
                continue

            for attempt in range(max_retries):
                try:
                    print(f"🔄 Trying {source} for {symbol} (attempt {attempt + 1}/{max_retries})")

                    if source == 'yfinance':
                        data = self._fetch_yfinance(symbol, period, interval)
                    elif source == 'alpha_vantage':
                        data = self._fetch_alpha_vantage(symbol, period)
                    elif source == 'iexcloud':
                        data = self._fetch_iexcloud(symbol, period)
                    elif source == 'polygon':
                        data = self._fetch_polygon(symbol, period)
                    elif source == 'twelve_data':
                        data = self._fetch_twelve_data(symbol, period)
                    else:
                        continue

                    if data is not None and not data.empty:
                        print(f"✅ Successfully fetched {symbol} from {source}")
                        self.health.record_success(source)
                        self.cache.set(cache_key, data)
                        return data

                except Exception as e:
                    error_msg = str(e)
                    print(f"⚠️ {source} failed (attempt {attempt + 1}): {error_msg}")

                    # Exponential backoff for retries
                    if attempt < max_retries - 1:
                        wait_time = 2 ** attempt
                        print(f"   Retrying in {wait_time}s...")
                        time.sleep(wait_time)
                    else:
                        self.health.record_failure(source, error_msg)

        print(f"❌ All data sources failed for {symbol}")
        return None

    def _fetch_yfinance(
        self,
        symbol: str,
        period: str,
        interval: str
    ) -> Optional[pd.DataFrame]:
        """Fetch from yfinance (Yahoo Finance)"""
        if not YFINANCE_AVAILABLE:
            raise ImportError("yfinance not installed")

        ticker = yf.Ticker(symbol)
        data = ticker.history(period=period, interval=interval)

        if data.empty:
            raise ValueError(f"yfinance returned empty data for {symbol}")

        return data

    def _fetch_alpha_vantage(
        self,
        symbol: str,
        period: str
    ) -> Optional[pd.DataFrame]:
        """
        Fetch from Alpha Vantage (free tier: 25 calls/day, 5 calls/minute)
        Docs: https://www.alphavantage.co/documentation/
        """
        if not self.alpha_vantage_key:
            raise ValueError("ALPHA_VANTAGE_API_KEY not set")

        url = "https://www.alphavantage.co/query"
        params = {
            "function": "TIME_SERIES_DAILY",
            "symbol": symbol,
            "apikey": self.alpha_vantage_key,
            "outputsize": "full" if period in ['1y', '5y', 'max'] else "compact"
        }

        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        if 'Error Message' in data:
            raise ValueError(f"Alpha Vantage error: {data['Error Message']}")

        if 'Note' in data:
            raise ValueError(f"Alpha Vantage rate limit: {data['Note']}")

        time_series = data.get('Time Series (Daily)', {})
        if not time_series:
            raise ValueError("No data in Alpha Vantage response")

        # Convert to DataFrame
        df = pd.DataFrame.from_dict(time_series, orient='index')
        df.index = pd.to_datetime(df.index)
        df = df.sort_index()

        # Rename columns to match yfinance format
        df.columns = ['Open', 'High', 'Low', 'Close', 'Volume']
        df = df.astype(float)

        # Filter by period
        days = self._period_to_days(period)
        if days:
            cutoff = datetime.now() - timedelta(days=days)
            df = df[df.index >= cutoff]

        return df

    def _fetch_iexcloud(
        self,
        symbol: str,
        period: str
    ) -> Optional[pd.DataFrame]:
        """
        Fetch from IEX Cloud (free tier: 50,000 calls/month - EXCELLENT!)
        Docs: https://iexcloud.io/docs/api/
        """
        if not self.iexcloud_key:
            raise ValueError("IEXCLOUD_API_KEY not set")

        # Determine range for historical data
        days = self._period_to_days(period)

        # IEX Cloud endpoint - use chart endpoint for historical data
        # Free tier: /stable/stock/{symbol}/chart/{range}
        if days <= 5:
            range_param = '5d'
        elif days <= 30:
            range_param = '1m'
        elif days <= 90:
            range_param = '3m'
        elif days <= 180:
            range_param = '6m'
        elif days <= 365:
            range_param = '1y'
        elif days <= 730:
            range_param = '2y'
        else:
            range_param = '5y'

        url = f"https://cloud.iexapis.com/stable/stock/{symbol}/chart/{range_param}"
        params = {"token": self.iexcloud_key}

        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        if not data or len(data) == 0:
            raise ValueError("No data in IEX Cloud response")

        # Convert to DataFrame
        df = pd.DataFrame(data)

        # IEX Cloud returns date field
        df['datetime'] = pd.to_datetime(df['date'])
        df.set_index('datetime', inplace=True)
        df = df.sort_index()

        # Rename columns to match yfinance format
        # IEX Cloud columns: open, high, low, close, volume
        df = df.rename(columns={
            'open': 'Open',
            'high': 'High',
            'low': 'Low',
            'close': 'Close',
            'volume': 'Volume'
        })

        # Filter by period (IEX might return more data than requested)
        cutoff = datetime.now() - timedelta(days=days)
        df = df[df.index >= cutoff]

        return df[['Open', 'High', 'Low', 'Close', 'Volume']].astype(float)

    def _fetch_polygon(
        self,
        symbol: str,
        period: str
    ) -> Optional[pd.DataFrame]:
        """
        Fetch from Polygon.io (free tier: 5 calls/minute)
        Docs: https://polygon.io/docs/stocks
        """
        if not self.polygon_key:
            raise ValueError("POLYGON_API_KEY not set")

        days = self._period_to_days(period)
        to_date = datetime.now().strftime('%Y-%m-%d')
        from_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

        url = f"https://api.polygon.io/v2/aggs/ticker/{symbol}/range/1/day/{from_date}/{to_date}"
        params = {"apiKey": self.polygon_key}

        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        if data.get('status') != 'OK':
            raise ValueError(f"Polygon error: {data.get('error', 'Unknown error')}")

        results = data.get('results', [])
        if not results:
            raise ValueError("No data in Polygon response")

        # Convert to DataFrame
        df = pd.DataFrame(results)
        df['date'] = pd.to_datetime(df['t'], unit='ms')
        df.set_index('date', inplace=True)

        # Rename columns to match yfinance format
        df = df.rename(columns={
            'o': 'Open',
            'h': 'High',
            'l': 'Low',
            'c': 'Close',
            'v': 'Volume'
        })

        return df[['Open', 'High', 'Low', 'Close', 'Volume']]

    def _fetch_twelve_data(
        self,
        symbol: str,
        period: str
    ) -> Optional[pd.DataFrame]:
        """
        Fetch from Twelve Data (free tier: 800 calls/day)
        Docs: https://twelvedata.com/docs
        """
        if not self.twelve_data_key:
            raise ValueError("TWELVE_DATA_API_KEY not set")

        url = "https://api.twelvedata.com/time_series"
        params = {
            "symbol": symbol,
            "interval": "1day",
            "apikey": self.twelve_data_key,
            "outputsize": self._period_to_outputsize(period)
        }

        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        if 'status' in data and data['status'] == 'error':
            raise ValueError(f"Twelve Data error: {data.get('message', 'Unknown error')}")

        values = data.get('values', [])
        if not values:
            raise ValueError("No data in Twelve Data response")

        # Convert to DataFrame
        df = pd.DataFrame(values)
        df['datetime'] = pd.to_datetime(df['datetime'])
        df.set_index('datetime', inplace=True)
        df = df.sort_index()

        # Rename columns to match yfinance format
        df = df.rename(columns={
            'open': 'Open',
            'high': 'High',
            'low': 'Low',
            'close': 'Close',
            'volume': 'Volume'
        })

        return df[['Open', 'High', 'Low', 'Close', 'Volume']].astype(float)

    def _period_to_days(self, period: str) -> int:
        """Convert period string to number of days"""
        period_map = {
            '1d': 1, '2d': 2, '5d': 5, '7d': 7,
            '1mo': 30, '2mo': 60, '3mo': 90, '6mo': 180,
            '1y': 365, '2y': 730, '5y': 1825, '10y': 3650,
            'ytd': (datetime.now() - datetime(datetime.now().year, 1, 1)).days,
            'max': 7300  # 20 years
        }
        return period_map.get(period, 365)

    def _period_to_outputsize(self, period: str) -> int:
        """Convert period to output size for APIs"""
        days = self._period_to_days(period)
        return min(days, 5000)  # Most APIs limit to ~5000 records

    def get_health_status(self) -> Dict:
        """Get health status of all data sources"""
        return {
            'sources': self.health.get_status(),
            'cache': self.cache.get_stats()
        }

    def clear_cache(self):
        """Clear all cached data"""
        self.cache.clear()
        print("✅ Cache cleared")


# Global singleton instance
price_data_fetcher = FlexiblePriceDataFetcher(cache_ttl=3600)


# Convenience functions for backward compatibility
def get_price_history(symbol: str, period: str = '5d', interval: str = '1d') -> Optional[pd.DataFrame]:
    """
    Get price history using flexible multi-source fetcher

    Example:
        df = get_price_history('SPY', period='30d')
    """
    return price_data_fetcher.get_price_history(symbol, period, interval)


def get_health_status() -> Dict:
    """Get health status of all data sources"""
    return price_data_fetcher.get_health_status()


def get_current_price(symbol: str) -> Optional[float]:
    """
    Get current/latest price for a symbol

    Tries multiple sources to get the most recent quote
    Returns latest close price if market is closed, or current price if open

    Example:
        vix_price = get_current_price('^VIX')
        spy_price = get_current_price('SPY')
    """
    # Try yfinance first (fastest for real-time quotes)
    if YFINANCE_AVAILABLE:
        try:
            ticker = yf.Ticker(symbol)

            # Try to get current market price first
            info = ticker.info
            if info and 'regularMarketPrice' in info:
                price = float(info['regularMarketPrice'])
                if price > 0:
                    print(f"✅ Got current price for {symbol}: ${price:.2f}")
                    return price

            # Fallback to latest historical price
            hist = ticker.history(period='1d', interval='1m')
            if not hist.empty:
                price = float(hist['Close'].iloc[-1])
                print(f"✅ Got latest price for {symbol}: ${price:.2f}")
                return price

        except Exception as e:
            print(f"⚠️ yfinance failed for {symbol}: {e}")

    # Fallback: Try to get from historical data
    try:
        data = get_price_history(symbol, period='1d')
        if data is not None and not data.empty:
            price = float(data['Close'].iloc[-1])
            print(f"✅ Got price from history for {symbol}: ${price:.2f}")
            return price
    except Exception as e:
        print(f"⚠️ Historical fallback failed for {symbol}: {e}")

    print(f"❌ Could not get price for {symbol}")
    return None


def get_multiple_prices(symbols: List[str]) -> Dict[str, Optional[float]]:
    """
    Get current prices for multiple symbols efficiently

    Example:
        prices = get_multiple_prices(['SPY', 'QQQ', '^VIX'])
        # Returns: {'SPY': 567.89, 'QQQ': 456.78, '^VIX': 17.5}
    """
    results = {}
    for symbol in symbols:
        results[symbol] = get_current_price(symbol)
    return results


if __name__ == "__main__":
    # Test the flexible fetcher
    print("=" * 80)
    print("Testing Flexible Price Data Fetcher")
    print("=" * 80)

    # Test with SPY
    print("\n1. Testing SPY (5 days)...")
    spy_data = get_price_history('SPY', period='5d')
    if spy_data is not None:
        print(f"   ✅ Got {len(spy_data)} rows of data")
        print(f"   Latest close: ${spy_data['Close'].iloc[-1]:.2f}")
    else:
        print("   ❌ Failed to get SPY data")

    # Test cache
    print("\n2. Testing cache (should be instant)...")
    start = time.time()
    spy_data_cached = get_price_history('SPY', period='5d')
    elapsed = time.time() - start
    print(f"   ⏱️  Took {elapsed:.3f}s (should be < 0.01s)")

    # Check health
    print("\n3. Checking data source health...")
    health = get_health_status()
    print(f"   Sources: {len(health['sources'])} configured")

    # Test current price fetching
    print("\n4. Testing current price quotes...")
    vix = get_current_price('^VIX')
    spy = get_current_price('SPY')
    if vix:
        print(f"   VIX: ${vix:.2f}")
    if spy:
        print(f"   SPY: ${spy:.2f}")
    for source, stats in health['sources'].items():
        success_rate = 0
        total = stats['success_count'] + stats['failure_count']
        if total > 0:
            success_rate = (stats['success_count'] / total) * 100
        print(f"   - {source}: {success_rate:.1f}% success rate ({stats['success_count']}/{total})")

    print(f"\n   Cache: {health['cache']['valid_entries']} valid entries")

    print("\n" + "=" * 80)
    print("✅ Testing complete!")
    print("=" * 80)
