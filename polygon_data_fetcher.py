"""
Polygon.io Data Fetcher - Comprehensive utility for ALL AlphaGEX data needs

This module provides a single, reliable data fetcher using Polygon.io exclusively.
Replaces Yahoo Finance, Alpha Vantage, and other unreliable sources.

Features:
- Stock price data (all timeframes: 1m, 5m, 15m, 1h, 4h, 1d)
- Options data (chains, Greeks, quotes, trades)
- VIX and market indices
- Aggressive caching to minimize API calls
- Support for both free tier (DELAYED) and paid tier (OK)
- Historical data for backtesting

Usage:
    from polygon_data_fetcher import polygon_fetcher

    # Get stock prices
    df = polygon_fetcher.get_price_history('SPY', days=90, timeframe='day')

    # Get options chain
    chain = polygon_fetcher.get_options_chain('SPY', strike=570, expiration='2024-12-20')

    # Get current price
    price = polygon_fetcher.get_current_price('SPY')
"""

import os
import time
import requests
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from functools import lru_cache


class PolygonDataCache:
    """Aggressive caching to minimize API calls"""

    def __init__(self):
        self.cache = {}
        self.ttls = {
            'price_history': 3600,  # 1 hour for historical prices
            'current_price': 60,     # 1 minute for current prices
            'options_chain': 300,    # 5 minutes for options chains
            'options_quote': 60,     # 1 minute for options quotes
        }

    def get(self, cache_type: str, key: str) -> Optional[any]:
        """Get cached data if still valid"""
        cache_key = f"{cache_type}:{key}"
        if cache_key not in self.cache:
            return None

        data, timestamp = self.cache[cache_key]
        ttl = self.ttls.get(cache_type, 3600)

        if time.time() - timestamp > ttl:
            del self.cache[cache_key]
            return None

        return data

    def set(self, cache_type: str, key: str, data: any):
        """Cache data"""
        cache_key = f"{cache_type}:{key}"
        self.cache[cache_key] = (data, time.time())

    def clear(self):
        """Clear all cached data"""
        self.cache.clear()


class PolygonDataFetcher:
    """
    Comprehensive Polygon.io data fetcher for all AlphaGEX needs

    Supports:
    - Free tier: DELAYED status, daily data only
    - Starter tier: DELAYED status, all intraday timeframes
    - Advanced tier: OK status, real-time data
    """

    def __init__(self):
        self.api_key = os.getenv("POLYGON_API_KEY")
        if not self.api_key:
            print("⚠️  POLYGON_API_KEY not set - data fetching will fail")

        self.cache = PolygonDataCache()
        self.base_url = "https://api.polygon.io"

    def get_price_history(
        self,
        symbol: str,
        days: int = 90,
        timeframe: str = 'day',
        multiplier: int = 1
    ) -> Optional[pd.DataFrame]:
        """
        Get historical price data

        Args:
            symbol: Stock symbol (e.g., 'SPY')
            days: Number of days of history
            timeframe: 'minute', 'hour', 'day', 'week', 'month'
            multiplier: Multiplier for timeframe (e.g., 5 for 5-minute bars)

        Returns:
            DataFrame with columns: Open, High, Low, Close, Volume
        """
        if not self.api_key:
            raise ValueError("POLYGON_API_KEY not configured")

        # Check cache
        cache_key = f"{symbol}_{days}_{timeframe}_{multiplier}"
        cached = self.cache.get('price_history', cache_key)
        if cached is not None:
            print(f"✅ Using cached price data for {symbol}")
            return cached

        try:
            to_date = datetime.now().strftime('%Y-%m-%d')
            from_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

            url = f"{self.base_url}/v2/aggs/ticker/{symbol}/range/{multiplier}/{timeframe}/{from_date}/{to_date}"
            params = {"apiKey": self.api_key, "sort": "asc", "limit": 50000}

            response = requests.get(url, params=params, timeout=10)

            if response.status_code == 200:
                data = response.json()
                status = data.get('status', '')

                # Accept both OK (paid) and DELAYED (free/starter)
                if status in ['OK', 'DELAYED'] and data.get('results'):
                    results = data['results']

                    # Convert to DataFrame
                    df = pd.DataFrame(results)
                    df['date'] = pd.to_datetime(df['t'], unit='ms')
                    df.set_index('date', inplace=True)

                    # Rename columns to standard format
                    df = df.rename(columns={
                        'o': 'Open',
                        'h': 'High',
                        'l': 'Low',
                        'c': 'Close',
                        'v': 'Volume'
                    })

                    result = df[['Open', 'High', 'Low', 'Close', 'Volume']]

                    # Cache the result
                    self.cache.set('price_history', cache_key, result)

                    print(f"✅ Fetched {len(result)} bars for {symbol} ({status})")
                    return result
                else:
                    print(f"⚠️  Polygon.io status: {status}, results: {data.get('resultsCount', 0)}")
                    return None
            else:
                print(f"❌ Polygon.io HTTP {response.status_code}: {response.text}")
                return None

        except Exception as e:
            print(f"❌ Error fetching price data: {e}")
            return None

    def get_current_price(self, symbol: str) -> Optional[float]:
        """
        Get current/latest price for a symbol

        Args:
            symbol: Stock symbol (e.g., 'SPY')

        Returns:
            Latest close price or None
        """
        # Check cache
        cached = self.cache.get('current_price', symbol)
        if cached is not None:
            return cached

        try:
            # Get last trade
            url = f"{self.base_url}/v2/last/trade/{symbol}"
            params = {"apiKey": self.api_key}

            response = requests.get(url, params=params, timeout=5)

            if response.status_code == 200:
                data = response.json()
                if data.get('status') in ['OK', 'DELAYED'] and data.get('results'):
                    price = float(data['results']['p'])
                    self.cache.set('current_price', symbol, price)
                    print(f"✅ Current price for {symbol}: ${price:.2f}")
                    return price

            # Fallback: Get latest from daily data
            df = self.get_price_history(symbol, days=1, timeframe='day')
            if df is not None and not df.empty:
                price = float(df['Close'].iloc[-1])
                self.cache.set('current_price', symbol, price)
                return price

        except Exception as e:
            print(f"❌ Error fetching current price: {e}")

        return None

    def get_options_chain(
        self,
        symbol: str,
        expiration: Optional[str] = None,
        strike: Optional[float] = None,
        option_type: Optional[str] = None
    ) -> Optional[pd.DataFrame]:
        """
        Get options chain data

        Args:
            symbol: Underlying symbol (e.g., 'SPY')
            expiration: Expiration date YYYY-MM-DD (optional)
            strike: Strike price (optional)
            option_type: 'call' or 'put' (optional)

        Returns:
            DataFrame with options data including Greeks
        """
        if not self.api_key:
            raise ValueError("POLYGON_API_KEY not configured")

        # Check cache
        cache_key = f"{symbol}_{expiration}_{strike}_{option_type}"
        cached = self.cache.get('options_chain', cache_key)
        if cached is not None:
            return cached

        try:
            url = f"{self.base_url}/v3/reference/options/contracts"
            params = {
                "apiKey": self.api_key,
                "underlying_ticker": symbol,
                "limit": 1000
            }

            if expiration:
                params['expiration_date'] = expiration
            if strike:
                params['strike_price'] = strike
            if option_type:
                params['contract_type'] = option_type.lower()

            response = requests.get(url, params=params, timeout=10)

            if response.status_code == 200:
                data = response.json()
                if data.get('status') in ['OK', 'DELAYED'] and data.get('results'):
                    df = pd.DataFrame(data['results'])
                    self.cache.set('options_chain', cache_key, df)
                    print(f"✅ Fetched {len(df)} options contracts for {symbol}")
                    return df
                else:
                    print(f"⚠️  No options data for {symbol}")
                    return None
            else:
                print(f"❌ Polygon.io HTTP {response.status_code}")
                return None

        except Exception as e:
            print(f"❌ Error fetching options chain: {e}")
            return None

    def get_option_quote(
        self,
        symbol: str,
        strike: float,
        expiration: str,
        option_type: str
    ) -> Optional[Dict]:
        """
        Get real-time quote for a specific option

        Args:
            symbol: Underlying symbol (e.g., 'SPY')
            strike: Strike price
            expiration: Expiration date YYYY-MM-DD
            option_type: 'call' or 'put'

        Returns:
            Dict with bid, ask, last, mid, volume, open_interest, Greeks
        """
        if not self.api_key:
            raise ValueError("POLYGON_API_KEY not configured")

        try:
            # First, get the option ticker symbol
            # Format: O:SPY241220C00570000 (for SPY $570 Call expiring 2024-12-20)
            exp_str = expiration.replace('-', '')[2:]  # "2024-12-20" -> "241220"
            type_char = 'C' if option_type.lower() == 'call' else 'P'
            strike_str = f"{int(strike * 1000):08d}"  # $570 -> "00570000"

            option_ticker = f"O:{symbol}{exp_str}{type_char}{strike_str}"

            # Get snapshot
            url = f"{self.base_url}/v3/snapshot/options/{symbol}/{option_ticker}"
            params = {"apiKey": self.api_key}

            response = requests.get(url, params=params, timeout=5)

            if response.status_code == 200:
                data = response.json()
                if data.get('status') in ['OK', 'DELAYED'] and data.get('results'):
                    result = data['results']

                    # Extract quote data
                    last_quote = result.get('last_quote', {})
                    last_trade = result.get('last_trade', {})
                    details = result.get('details', {})
                    greeks = result.get('greeks', {})

                    return {
                        'bid': last_quote.get('bid', 0),
                        'ask': last_quote.get('ask', 0),
                        'last': last_trade.get('price', 0),
                        'mid': (last_quote.get('bid', 0) + last_quote.get('ask', 0)) / 2,
                        'volume': details.get('volume', 0),
                        'open_interest': details.get('open_interest', 0),
                        'implied_volatility': greeks.get('implied_volatility', 0),
                        'delta': greeks.get('delta', 0),
                        'gamma': greeks.get('gamma', 0),
                        'theta': greeks.get('theta', 0),
                        'vega': greeks.get('vega', 0),
                        'strike': strike,
                        'expiration': expiration,
                        'contract_symbol': option_ticker
                    }

            print(f"⚠️  Could not fetch option quote for {option_ticker}")
            return None

        except Exception as e:
            print(f"❌ Error fetching option quote: {e}")
            return None

    def get_multiple_timeframes(
        self,
        symbol: str,
        timeframes: Dict[str, Tuple[int, str, int]] = None
    ) -> Dict[str, List[Dict]]:
        """
        Get price data for multiple timeframes efficiently

        Args:
            symbol: Stock symbol
            timeframes: Dict mapping name to (days, timeframe, multiplier)
                       Default: {'5m': (3, 'minute', 5), '15m': (7, 'minute', 15), ...}

        Returns:
            Dict mapping timeframe name to list of price bars
        """
        if timeframes is None:
            timeframes = {
                '5m': (3, 'minute', 5),
                '15m': (7, 'minute', 15),
                '1h': (14, 'hour', 1),
                '4h': (30, 'hour', 4),
                '1d': (90, 'day', 1)
            }

        result = {}

        for tf_name, (days, timeframe, multiplier) in timeframes.items():
            df = self.get_price_history(symbol, days=days, timeframe=timeframe, multiplier=multiplier)

            if df is not None and not df.empty:
                result[tf_name] = [
                    {
                        'close': row['Close'],
                        'high': row['High'],
                        'low': row['Low'],
                        'volume': row['Volume']
                    }
                    for _, row in df.iterrows()
                ]
                print(f"  ✅ {tf_name}: {len(result[tf_name])} bars")
            else:
                result[tf_name] = []
                print(f"  ⚠️  {tf_name}: No data")

        return result

    def clear_cache(self):
        """Clear all cached data"""
        self.cache.clear()
        print("✅ Cache cleared")


# Global singleton instance
polygon_fetcher = PolygonDataFetcher()


# Convenience functions
def get_price_history(symbol: str, days: int = 90, timeframe: str = 'day', multiplier: int = 1) -> Optional[pd.DataFrame]:
    """Get historical price data"""
    return polygon_fetcher.get_price_history(symbol, days, timeframe, multiplier)


def get_current_price(symbol: str) -> Optional[float]:
    """Get current price"""
    return polygon_fetcher.get_current_price(symbol)


def get_options_chain(symbol: str, expiration: str = None, strike: float = None) -> Optional[pd.DataFrame]:
    """Get options chain"""
    return polygon_fetcher.get_options_chain(symbol, expiration, strike)


def get_option_quote(symbol: str, strike: float, expiration: str, option_type: str) -> Optional[Dict]:
    """Get option quote with Greeks"""
    return polygon_fetcher.get_option_quote(symbol, strike, expiration, option_type)


if __name__ == "__main__":
    # Test the fetcher
    print("=" * 80)
    print("Testing Polygon.io Data Fetcher")
    print("=" * 80)

    # Test stock prices
    print("\n1. Testing SPY price history (90 days)...")
    df = get_price_history('SPY', days=90, timeframe='day')
    if df is not None:
        print(f"   ✅ Got {len(df)} days of data")
        print(f"   Latest close: ${df['Close'].iloc[-1]:.2f}")

    # Test current price
    print("\n2. Testing current price...")
    price = get_current_price('SPY')
    if price:
        print(f"   ✅ SPY: ${price:.2f}")

    # Test options
    print("\n3. Testing options chain...")
    exp_date = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')
    chain = get_options_chain('SPY', expiration=exp_date)
    if chain is not None:
        print(f"   ✅ Got {len(chain)} options contracts")

    print("\n" + "=" * 80)
    print("✅ Testing complete!")
    print("=" * 80)
