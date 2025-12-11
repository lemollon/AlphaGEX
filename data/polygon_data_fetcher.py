"""
Polygon.io Data Fetcher - Comprehensive utility for ALL AlphaGEX data needs

This module provides a single, reliable data fetcher using Polygon.io exclusively.
Replaces Yahoo Finance, Alpha Vantage, and other unreliable sources.

Features:
- Stock price data (all timeframes: 1m, 5m, 15m, 1h, 4h, 1d)
- Options data (chains, Greeks, quotes, trades)
- VIX and market indices
- Aggressive caching to minimize API calls
- Support for all Polygon.io tiers (Stocks Starter, Options Developer, Advanced, etc.)
- Historical data for backtesting
- Real-time data support for paid tiers

Supported Plans:
- Stocks Starter: Real-time stock data, all intraday timeframes
- Options Developer: Real-time options data, Greeks, chains
- Advanced+: Real-time everything with higher rate limits

Usage:
    from polygon_data_fetcher import polygon_fetcher

    # Get stock prices
    df = polygon_fetcher.get_price_history('SPY', days=90, timeframe='day')

    # Get options chain
    chain = polygon_fetcher.get_options_chain('SPY', strike=570, expiration='2024-12-20')

    # Get current price
    price = polygon_fetcher.get_current_price('SPY')

    # Check your subscription tier
    tier = polygon_fetcher.detect_subscription_tier()
"""

import os
import time
import math
import requests
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from functools import lru_cache
from scipy.stats import norm
from pathlib import Path

# Load environment variables from .env file
from dotenv import load_dotenv
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(env_path)

# Data collection hook for ML storage
try:
    from services.data_collector import DataCollector
    DATA_COLLECTOR_AVAILABLE = True
except:
    DATA_COLLECTOR_AVAILABLE = False


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

    Supports all Polygon.io subscription tiers:
    - Free: DELAYED status, daily data only
    - Stocks Starter: OK/DELAYED status, real-time stocks, all intraday timeframes
    - Options Developer: OK status, real-time options data with Greeks
    - Advanced+: OK status, real-time everything with higher rate limits

    Current Configuration: Stocks Starter + Options Developer (Real-time capable)
    """

    def __init__(self):
        # Import from centralized config
        try:
            from unified_config import APIConfig
            self.api_key = APIConfig.POLYGON_API_KEY
            self.base_url = APIConfig.POLYGON_BASE_URL
        except ImportError:
            self.api_key = os.getenv("POLYGON_API_KEY")
            self.base_url = "https://api.polygon.io"

        if not self.api_key:
            print("⚠️  POLYGON_API_KEY not set - data fetching will fail")

        self.cache = PolygonDataCache()
        self._detected_tier = None

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

                    # Handle indices (like I:VIX) that don't have Volume data
                    if 'Volume' in df.columns:
                        result = df[['Open', 'High', 'Low', 'Close', 'Volume']]
                    else:
                        # Index data - no volume, add dummy column
                        df['Volume'] = 0
                        result = df[['Open', 'High', 'Low', 'Close', 'Volume']]

                    # Cache the result
                    self.cache.set('price_history', cache_key, result)

                    # Store in ML database for analysis
                    if DATA_COLLECTOR_AVAILABLE:
                        try:
                            prices = [
                                {'timestamp': idx, 'o': row['Open'], 'h': row['High'],
                                 'l': row['Low'], 'c': row['Close'], 'v': row['Volume']}
                                for idx, row in result.iterrows()
                            ]
                            DataCollector.store_prices(prices, symbol, timeframe)
                        except:
                            pass  # Don't fail if storage fails

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

    def get_latest_price(self, symbol: str) -> Optional[float]:
        """Alias for get_current_price for backward compatibility"""
        return self.get_current_price(symbol)

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
            # Ensure strike is a number (might be passed as string from API/database)
            strike_num = float(strike) if isinstance(strike, str) else strike
            # Round strike to valid increment (SPY uses $1, SPX uses $5)
            if symbol.upper() in ['SPY', 'QQQ', 'IWM']:
                strike_num = round(strike_num)  # $1 increments
            elif symbol.upper() in ['SPX', 'SPXW', 'NDX']:
                strike_num = round(strike_num / 5) * 5  # $5 increments
            else:
                strike_num = round(strike_num)  # Default to $1
            strike_str = f"{int(strike_num * 1000):08d}"  # $570 -> "00570000"

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

                    bid = last_quote.get('bid', 0)
                    ask = last_quote.get('ask', 0)

                    # Debug logging when bid/ask is missing
                    if bid == 0 or ask == 0:
                        print(f"⚠️  Polygon returned missing bid/ask for {option_ticker}:")
                        print(f"    last_quote: {last_quote}")
                        print(f"    last_trade: {last_trade}")
                        print(f"    API status: {data.get('status')}")

                    # Track data freshness - DELAYED means 15-minute delay
                    data_status = data.get('status', 'UNKNOWN')
                    is_delayed = data_status == 'DELAYED'

                    # Extract quote timestamp if available
                    quote_timestamp = last_quote.get('sip_timestamp') or last_quote.get('participant_timestamp')
                    if quote_timestamp:
                        # Convert nanoseconds to datetime
                        from datetime import datetime
                        quote_time = datetime.fromtimestamp(quote_timestamp / 1e9)
                        quote_time_str = quote_time.strftime('%Y-%m-%d %H:%M:%S')
                    else:
                        quote_time_str = None

                    # Calculate mid price - use last trade price as fallback when bid/ask missing
                    last_price = last_trade.get('price', 0)
                    if bid > 0 and ask > 0:
                        mid_price = (bid + ask) / 2
                    elif last_price > 0:
                        # Fallback to last trade price when quotes unavailable (e.g., after hours)
                        mid_price = last_price
                        # Estimate bid/ask spread around last price (typically 2-5% for options)
                        spread_estimate = last_price * 0.03  # 3% spread estimate
                        if bid == 0:
                            bid = last_price - spread_estimate / 2
                        if ask == 0:
                            ask = last_price + spread_estimate / 2
                    else:
                        mid_price = 0

                    return {
                        'bid': bid,
                        'ask': ask,
                        'last': last_price,
                        'mid': mid_price,
                        'volume': details.get('volume', 0),
                        'open_interest': details.get('open_interest', 0),
                        'implied_volatility': greeks.get('implied_volatility', 0),
                        'delta': greeks.get('delta', 0),
                        'gamma': greeks.get('gamma', 0),
                        'theta': greeks.get('theta', 0),
                        'vega': greeks.get('vega', 0),
                        'strike': strike,
                        'expiration': expiration,
                        'contract_symbol': option_ticker,
                        # New fields for delayed data tracking
                        'data_status': data_status,  # 'OK' = real-time, 'DELAYED' = 15-min delay
                        'is_delayed': is_delayed,
                        'quote_timestamp': quote_time_str,
                        'delay_minutes': 15 if is_delayed else 0
                    }
                else:
                    print(f"⚠️  Polygon response missing results for {option_ticker}:")
                    print(f"    status: {data.get('status')}, results: {data.get('results')}")

            print(f"⚠️  Could not fetch option quote for {option_ticker} (HTTP {response.status_code})")
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

    def detect_subscription_tier(self) -> Dict[str, any]:
        """
        Detect the current Polygon.io subscription tier

        Tests various endpoints to determine tier capabilities:
        - Stocks real-time (Stocks Starter+)
        - Options data (Options Developer+)
        - Response status (OK = real-time, DELAYED = free/limited)

        Returns:
            {
                'tier': str,  # 'Free', 'Stocks Starter', 'Options Developer', 'Advanced', or 'Unknown'
                'has_realtime_stocks': bool,
                'has_realtime_options': bool,
                'has_intraday': bool,
                'stocks_status': str,  # 'OK' or 'DELAYED'
                'options_status': str,  # 'OK', 'DELAYED', or 'N/A'
                'detected_at': str
            }
        """
        if self._detected_tier is not None:
            return self._detected_tier

        result = {
            'tier': 'Unknown',
            'has_realtime_stocks': False,
            'has_realtime_options': False,
            'has_intraday': False,
            'stocks_status': 'N/A',
            'options_status': 'N/A',
            'detected_at': datetime.now().isoformat()
        }

        try:
            # Test 1: Check stock data status
            print("🔍 Detecting Polygon.io subscription tier...")

            # Try to get 1-minute bars (requires Starter+)
            df = self.get_price_history('SPY', days=1, timeframe='minute', multiplier=1)
            if df is not None and not df.empty:
                result['has_intraday'] = True
                print("   ✅ Intraday data access confirmed")

            # Test 2: Check stock real-time status
            url = f"{self.base_url}/v2/last/trade/SPY"
            params = {"apiKey": self.api_key}
            response = requests.get(url, params=params, timeout=5)

            if response.status_code == 200:
                data = response.json()
                status = data.get('status', 'N/A')
                result['stocks_status'] = status

                if status == 'OK':
                    result['has_realtime_stocks'] = True
                    print("   ✅ Real-time stock data confirmed (status: OK)")
                elif status == 'DELAYED':
                    print("   ⚠️  Stock data is delayed (status: DELAYED)")

            # Test 3: Check options access
            try:
                exp_date = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')
                exp_str = exp_date.replace('-', '')[2:]
                option_ticker = f"O:SPY{exp_str}C00570000"

                url = f"{self.base_url}/v3/snapshot/options/SPY/{option_ticker}"
                params = {"apiKey": self.api_key}
                response = requests.get(url, params=params, timeout=5)

                if response.status_code == 200:
                    data = response.json()
                    status = data.get('status', 'N/A')
                    result['options_status'] = status

                    if status == 'OK':
                        result['has_realtime_options'] = True
                        print("   ✅ Real-time options data confirmed (status: OK)")
                    elif status == 'DELAYED':
                        print("   ⚠️  Options data is delayed (status: DELAYED)")

                    if data.get('results'):
                        print("   ✅ Options data access confirmed")
                elif response.status_code == 403:
                    result['options_status'] = 'FORBIDDEN'
                    print("   ❌ Options data not available (403 Forbidden)")
            except Exception as e:
                print(f"   ⚠️  Could not test options access: {e}")

            # Determine tier based on capabilities
            if result['has_realtime_options'] and result['has_realtime_stocks']:
                result['tier'] = 'Options Developer + Stocks Starter'
                print("\n🎉 Detected: Options Developer + Stocks Starter")
                print("   • Real-time stocks ✅")
                print("   • Real-time options ✅")
                print("   • All intraday timeframes ✅")
            elif result['has_realtime_stocks'] and result['has_intraday']:
                result['tier'] = 'Stocks Starter'
                print("\n📊 Detected: Stocks Starter")
                print("   • Real-time stocks ✅")
                print("   • All intraday timeframes ✅")
            elif result['has_intraday']:
                result['tier'] = 'Basic (with intraday)'
                print("\n📈 Detected: Basic subscription with intraday access")
            else:
                result['tier'] = 'Free'
                print("\n⚠️  Detected: Free tier (daily data only)")

            self._detected_tier = result
            return result

        except Exception as e:
            print(f"❌ Error detecting subscription tier: {e}")
            result['tier'] = 'Unknown'
            return result

    def clear_cache(self):
        """Clear all cached data"""
        self.cache.clear()
        print("✅ Cache cleared")

    def get_historical_option_prices(
        self,
        symbol: str,
        strike: float,
        expiration: str,
        option_type: str,
        start_date: str,
        end_date: str = None
    ) -> Optional[pd.DataFrame]:
        """
        Get HISTORICAL daily prices for a specific option contract.

        This is CRITICAL for backtesting - gives you the REAL bid/ask/close
        for an option on any historical date.

        Args:
            symbol: Underlying symbol (e.g., 'SPY')
            strike: Strike price
            expiration: Option expiration date YYYY-MM-DD
            option_type: 'call' or 'put'
            start_date: Start date YYYY-MM-DD
            end_date: End date YYYY-MM-DD (default: today)

        Returns:
            DataFrame with columns: date, open, high, low, close, volume, vwap
            Each row = one trading day's option prices
        """
        if not self.api_key:
            raise ValueError("POLYGON_API_KEY not configured")

        try:
            # Build option ticker symbol
            # Format: O:SPY241220C00570000
            exp_str = expiration.replace('-', '')[2:]  # "2024-12-20" -> "241220"
            type_char = 'C' if option_type.lower() == 'call' else 'P'
            # Ensure strike is a number (might be passed as string from API/database)
            strike_num = float(strike) if isinstance(strike, str) else strike
            strike_str = f"{int(strike_num * 1000):08d}"

            option_ticker = f"O:{symbol}{exp_str}{type_char}{strike_str}"

            if end_date is None:
                end_date = datetime.now().strftime('%Y-%m-%d')

            # Use aggregates endpoint for historical data
            url = f"{self.base_url}/v2/aggs/ticker/{option_ticker}/range/1/day/{start_date}/{end_date}"
            params = {
                "apiKey": self.api_key,
                "adjusted": "true",
                "sort": "asc"
            }

            print(f"📊 Fetching historical prices for {option_ticker} ({start_date} to {end_date})...")
            response = requests.get(url, params=params, timeout=10)

            if response.status_code == 200:
                data = response.json()

                if data.get('status') in ['OK', 'DELAYED'] and data.get('results'):
                    results = data['results']

                    df = pd.DataFrame(results)

                    # Rename columns to standard names
                    df = df.rename(columns={
                        't': 'timestamp',
                        'o': 'open',
                        'h': 'high',
                        'l': 'low',
                        'c': 'close',
                        'v': 'volume',
                        'vw': 'vwap',
                        'n': 'num_trades'
                    })

                    # Convert timestamp to date
                    df['date'] = pd.to_datetime(df['timestamp'], unit='ms').dt.date

                    # Add metadata
                    df['option_ticker'] = option_ticker
                    df['underlying'] = symbol
                    df['strike'] = strike
                    df['expiration'] = expiration
                    df['option_type'] = option_type

                    print(f"   ✅ Got {len(df)} days of historical option prices")
                    return df

                else:
                    print(f"   ⚠️  No historical data for {option_ticker}")
                    print(f"   Response: {data.get('status')}, count: {data.get('resultsCount', 0)}")
                    return None

            elif response.status_code == 403:
                print(f"   ❌ 403 Forbidden - Options historical data requires Options tier")
                return None
            else:
                print(f"   ❌ HTTP {response.status_code}: {response.text[:200]}")
                return None

        except Exception as e:
            print(f"❌ Error fetching historical option prices: {e}")
            import traceback
            traceback.print_exc()
            return None

    def find_option_at_delta(
        self,
        symbol: str,
        expiration: str,
        option_type: str,
        target_delta: float,
        date: str = None
    ) -> Optional[Dict]:
        """
        Find the option closest to a target delta.

        For backtesting wheel strategy, we need to find the ~25 delta put.

        Args:
            symbol: Underlying symbol
            expiration: Option expiration YYYY-MM-DD
            option_type: 'call' or 'put'
            target_delta: Target delta (e.g., 0.25 for 25-delta)
            date: Date to check (default: today)

        Returns:
            Dict with strike, delta, price info for closest match
        """
        if not self.api_key:
            raise ValueError("POLYGON_API_KEY not configured")

        try:
            # Get all options for this expiration
            chain = self.get_options_chain(symbol, expiration=expiration)

            if chain is None or len(chain) == 0:
                return None

            # Filter by option type
            type_filter = 'call' if option_type.lower() == 'call' else 'put'
            filtered = chain[chain['contract_type'] == type_filter]

            if len(filtered) == 0:
                return None

            # For puts, delta is negative, so we need abs comparison
            if option_type.lower() == 'put':
                target_delta = -abs(target_delta)  # Make negative for puts

            # Find closest to target delta
            # Note: Polygon chain may not have Greeks - need to get individual quotes
            best_match = None
            best_delta_diff = float('inf')

            for _, row in filtered.iterrows():
                strike = row.get('strike_price', 0)
                if strike <= 0:
                    continue

                # Get quote with Greeks
                quote = self.get_option_quote(symbol, strike, expiration, option_type)
                if quote is None:
                    continue

                delta = quote.get('delta', 0)
                delta_diff = abs(delta - target_delta)

                if delta_diff < best_delta_diff:
                    best_delta_diff = delta_diff
                    best_match = {
                        'strike': strike,
                        'delta': delta,
                        'bid': quote.get('bid', 0),
                        'ask': quote.get('ask', 0),
                        'mid': quote.get('mid', 0),
                        'iv': quote.get('implied_volatility', 0),
                        'contract_symbol': quote.get('contract_symbol', ''),
                        'expiration': expiration
                    }

                # Stop if we found a close enough match
                if delta_diff < 0.02:  # Within 2 delta
                    break

            return best_match

        except Exception as e:
            print(f"❌ Error finding option at delta: {e}")
            return None


# Global singleton instance
polygon_fetcher = PolygonDataFetcher()


# Convenience functions
def get_price_history(symbol: str, days: int = 90, timeframe: str = 'day', multiplier: int = 1) -> Optional[pd.DataFrame]:
    """Get historical price data"""
    return polygon_fetcher.get_price_history(symbol, days, timeframe, multiplier)


def get_current_price(symbol: str) -> Optional[float]:
    """Get current price"""
    return polygon_fetcher.get_current_price(symbol)


def get_latest_price(symbol: str) -> Optional[float]:
    """Get latest price (alias for get_current_price)"""
    return polygon_fetcher.get_current_price(symbol)


def get_options_chain(symbol: str, expiration: str = None, strike: float = None) -> Optional[pd.DataFrame]:
    """Get options chain"""
    return polygon_fetcher.get_options_chain(symbol, expiration, strike)


def get_option_quote(symbol: str, strike: float, expiration: str, option_type: str) -> Optional[Dict]:
    """Get option quote with Greeks"""
    return polygon_fetcher.get_option_quote(symbol, strike, expiration, option_type)


def detect_subscription_tier() -> Dict[str, any]:
    """Detect current Polygon.io subscription tier"""
    return polygon_fetcher.detect_subscription_tier()


def calculate_delayed_price_range(
    quote: Dict,
    underlying_price: float = None,
    vix: float = None
) -> Dict:
    """
    Calculate expected price range for a delayed option quote.

    With 15-minute delayed data, prices can move significantly.
    This function provides a realistic range to expect at entry.

    Args:
        quote: Option quote dict from get_option_quote()
        underlying_price: Current underlying price (for delta calculation)
        vix: Current VIX level (for volatility adjustment)

    Returns:
        {
            'displayed_mid': float,       # The 15-min delayed mid price
            'estimated_current_low': float,   # Likely lower bound now
            'estimated_current_high': float,  # Likely upper bound now
            'spread_buffer_pct': float,   # % buffer to add
            'entry_recommendation': str,  # Recommended limit price strategy
            'is_delayed': bool,
            'delay_warning': str
        }
    """
    if quote is None:
        return {'error': 'No quote data'}

    bid = quote.get('bid', 0) or 0
    ask = quote.get('ask', 0) or 0
    last_price = quote.get('last', 0) or 0
    # Use mid from quote, or calculate from bid/ask, or fallback to last price
    mid = quote.get('mid', 0) or ((bid + ask) / 2 if bid > 0 and ask > 0 else last_price)
    is_delayed = quote.get('is_delayed', False)
    delta = abs(quote.get('delta', 0.5) or 0.5)
    iv = quote.get('implied_volatility', 0.25) or 0.25

    # For non-delayed data, return simple values
    if not is_delayed:
        return {
            'displayed_mid': mid,
            'estimated_current_low': bid,
            'estimated_current_high': ask,
            'spread_buffer_pct': 0,
            'entry_recommendation': f'Use limit order at ${mid:.2f} (real-time data)',
            'is_delayed': False,
            'delay_warning': None
        }

    # For delayed data (15 minutes):
    # SPY typically moves 0.1-0.3% in 15 minutes
    # Option prices can move 2-10% based on delta and IV

    # Base buffer: account for typical 15-min SPY movement
    base_move_pct = 0.15  # SPY moves ~0.15% in 15 min on average

    # Adjust for VIX (higher VIX = more movement)
    vix_multiplier = 1.0
    if vix:
        if vix > 25:
            vix_multiplier = 1.5  # High volatility
        elif vix > 20:
            vix_multiplier = 1.25
        elif vix < 15:
            vix_multiplier = 0.75  # Low volatility

    # Option price change estimate: delta * underlying move + IV factor
    # Higher delta options move more with underlying
    option_move_pct = (delta * base_move_pct * 100 * vix_multiplier) + (iv * 0.02)

    # Minimum 3% buffer, maximum 15% buffer
    spread_buffer_pct = max(3.0, min(15.0, option_move_pct * 100))

    # Calculate range
    buffer = mid * (spread_buffer_pct / 100)
    estimated_low = max(0.01, mid - buffer)
    estimated_high = mid + buffer

    # Entry recommendation
    if spread_buffer_pct > 8:
        entry_rec = f"⚠️ WIDE RANGE: Bid at ${estimated_low:.2f}, may fill up to ${estimated_high:.2f}"
    else:
        entry_rec = f"Use limit at ${mid:.2f}, expect to pay ${estimated_low:.2f}-${estimated_high:.2f}"

    return {
        'displayed_mid': mid,
        'displayed_bid': bid,
        'displayed_ask': ask,
        'estimated_current_low': round(estimated_low, 2),
        'estimated_current_high': round(estimated_high, 2),
        'spread_buffer_pct': round(spread_buffer_pct, 1),
        'entry_recommendation': entry_rec,
        'is_delayed': True,
        'delay_warning': '⏱️ Price is 15 minutes delayed - actual price will differ!',
        'quote_time': quote.get('quote_timestamp')
    }


def calculate_black_scholes_price(
    spot_price: float,
    strike: float,
    time_to_expiry: float,
    volatility: float,
    option_type: str = 'call',
    risk_free_rate: float = 0.05
) -> float:
    """
    Calculate theoretical option price using Black-Scholes model.

    Args:
        spot_price: Current underlying price
        strike: Option strike price
        time_to_expiry: Time to expiration in years (e.g., 7 days = 7/365)
        volatility: Implied volatility as decimal (e.g., 0.25 for 25%)
        option_type: 'call' or 'put'
        risk_free_rate: Risk-free interest rate (default 5%)

    Returns:
        Theoretical option price
    """
    if time_to_expiry <= 0:
        # At expiration, only intrinsic value
        if option_type.lower() == 'call':
            return max(0, spot_price - strike)
        else:
            return max(0, strike - spot_price)

    # Ensure volatility is reasonable
    volatility = max(0.01, min(volatility, 5.0))  # Cap at 500% IV

    # Calculate d1 and d2
    d1 = (math.log(spot_price / strike) + (risk_free_rate + 0.5 * volatility**2) * time_to_expiry) / (volatility * math.sqrt(time_to_expiry))
    d2 = d1 - volatility * math.sqrt(time_to_expiry)

    if option_type.lower() == 'call':
        price = spot_price * norm.cdf(d1) - strike * math.exp(-risk_free_rate * time_to_expiry) * norm.cdf(d2)
    else:
        price = strike * math.exp(-risk_free_rate * time_to_expiry) * norm.cdf(-d2) - spot_price * norm.cdf(-d1)

    return max(0, price)


def calculate_theoretical_option_price(
    quote: Dict,
    current_spot: float = None,
    current_vix: float = None
) -> Dict:
    """
    Calculate theoretical option price using Black-Scholes to compensate for 15-minute delay.

    This function takes a delayed option quote and calculates what the price
    SHOULD be based on the current underlying price and the IV from the quote.

    Args:
        quote: Option quote dict from get_option_quote()
        current_spot: Current SPY price (if None, uses estimate from quote)
        current_vix: Current VIX level (for IV adjustment)

    Returns:
        Enhanced quote dict with theoretical prices:
        {
            ...original quote fields...,
            'theoretical_price': float,      # Black-Scholes calculated price
            'theoretical_bid': float,        # Estimated bid (theoretical - spread/2)
            'theoretical_ask': float,        # Estimated ask (theoretical + spread/2)
            'price_adjustment': float,       # Difference from delayed mid
            'price_adjustment_pct': float,   # Adjustment as percentage
            'recommended_entry': float,      # Recommended entry price
            'confidence': str,               # 'high', 'medium', 'low'
            'calculation_method': str        # Explanation of how price was calculated
        }
    """
    if quote is None:
        return {'error': 'No quote data'}

    # Extract quote data
    bid = quote.get('bid', 0) or 0
    ask = quote.get('ask', 0) or 0
    last_price = quote.get('last', 0) or 0
    # Use mid from quote, or calculate from bid/ask, or fallback to last price
    mid = quote.get('mid', 0) or ((bid + ask) / 2 if bid > 0 and ask > 0 else last_price)
    strike = quote.get('strike', 0)
    expiration = quote.get('expiration', '')
    iv = quote.get('implied_volatility', 0) or 0.25  # Default 25% IV
    delta = quote.get('delta', 0)
    is_delayed = quote.get('is_delayed', False)

    # Determine option type from delta (positive = call, negative = put)
    if delta is None or delta == 0:
        # Try to infer from contract symbol
        contract = quote.get('contract_symbol', '')
        option_type = 'call' if 'C' in contract else 'put'
    else:
        option_type = 'call' if delta > 0 else 'put'

    # Calculate time to expiry
    try:
        exp_date = datetime.strptime(expiration, '%Y-%m-%d')
        days_to_exp = (exp_date - datetime.now()).days
        time_to_expiry = max(1, days_to_exp) / 365.0  # At least 1 day
    except (ValueError, TypeError):
        time_to_expiry = 7 / 365.0  # Default to 7 days

    # Get current spot price
    if current_spot is None or current_spot <= 0:
        # Try to fetch current price
        current_spot = get_current_price('SPY')
        if current_spot is None or current_spot <= 0:
            # Fall back to estimating from quote
            # Use the strike and delta to estimate spot
            if abs(delta) > 0.01:
                # ATM option has ~0.50 delta
                # Rough estimate: spot ≈ strike when delta is near 0.50
                current_spot = strike
            else:
                current_spot = strike

    # Adjust IV based on VIX if available (IV tends to track VIX)
    adjusted_iv = iv
    if current_vix and current_vix > 0:
        # VIX is annualized, so use it to sanity-check IV
        vix_decimal = current_vix / 100.0
        # Blend quote IV with VIX-implied IV (70% quote, 30% VIX)
        adjusted_iv = (iv * 0.7) + (vix_decimal * 0.3)

    # Calculate theoretical price using Black-Scholes
    theoretical_price = calculate_black_scholes_price(
        spot_price=current_spot,
        strike=strike,
        time_to_expiry=time_to_expiry,
        volatility=adjusted_iv,
        option_type=option_type
    )

    # Estimate bid/ask spread from original quote
    original_spread = ask - bid if (ask > 0 and bid > 0) else mid * 0.02  # Default 2% spread
    spread_pct = (original_spread / mid * 100) if mid > 0 else 2.0

    # Apply spread to theoretical price
    half_spread = original_spread / 2
    theoretical_bid = max(0.01, theoretical_price - half_spread)
    theoretical_ask = theoretical_price + half_spread

    # Calculate price adjustment
    price_adjustment = theoretical_price - mid if mid > 0 else 0
    price_adjustment_pct = (price_adjustment / mid * 100) if mid > 0 else 0

    # Determine confidence level
    if abs(price_adjustment_pct) < 3:
        confidence = 'high'  # Theoretical close to quoted
        recommended_entry = theoretical_price
    elif abs(price_adjustment_pct) < 8:
        confidence = 'medium'  # Moderate difference
        # Use weighted average of theoretical and quoted
        recommended_entry = (theoretical_price * 0.6 + mid * 0.4)
    else:
        confidence = 'low'  # Large difference - market may have moved significantly
        # Be more conservative
        if option_type == 'call':
            # For calls, if theoretical > quoted, market moved up
            recommended_entry = max(theoretical_price, mid) if price_adjustment > 0 else min(theoretical_price, mid)
        else:
            # For puts, if theoretical > quoted, market moved down
            recommended_entry = max(theoretical_price, mid) if price_adjustment > 0 else min(theoretical_price, mid)

    # Build calculation explanation
    calculation_method = (
        f"Black-Scholes with SPY=${current_spot:.2f}, "
        f"K=${strike:.0f}, IV={adjusted_iv*100:.1f}%, "
        f"DTE={int(time_to_expiry*365)}, {option_type.upper()}"
    )

    # Return enhanced quote
    result = dict(quote)  # Copy original quote
    result.update({
        'theoretical_price': round(theoretical_price, 2),
        'theoretical_bid': round(theoretical_bid, 2),
        'theoretical_ask': round(theoretical_ask, 2),
        'theoretical_mid': round(theoretical_price, 2),
        'price_adjustment': round(price_adjustment, 2),
        'price_adjustment_pct': round(price_adjustment_pct, 1),
        'recommended_entry': round(recommended_entry, 2),
        'confidence': confidence,
        'calculation_method': calculation_method,
        'current_spot_used': round(current_spot, 2),
        'adjusted_iv_used': round(adjusted_iv, 4),
        'use_theoretical': is_delayed,  # Flag to indicate theoretical should be preferred
    })

    return result


def get_best_entry_price(quote: Dict, current_spot: float = None, use_theoretical: bool = True) -> float:
    """
    Get the best entry price for an option, using theoretical pricing if delayed data.

    Args:
        quote: Option quote from get_option_quote()
        current_spot: Current SPY price (optional)
        use_theoretical: Whether to use theoretical pricing for delayed data

    Returns:
        Best estimated entry price
    """
    if quote is None:
        return 0.0

    is_delayed = quote.get('is_delayed', False)
    mid = quote.get('mid', 0) or 0

    # For real-time data, just use the mid
    if not is_delayed or not use_theoretical:
        return mid

    # For delayed data, calculate theoretical price
    enhanced = calculate_theoretical_option_price(quote, current_spot)

    if 'error' in enhanced:
        return mid

    # Return the recommended entry price
    return enhanced.get('recommended_entry', mid)


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


# =============================================================================
# Backward Compatibility with polygon_helper.py
# =============================================================================
# These functions provide the same interface as the deprecated polygon_helper.py

def get_polygon_data_fetcher() -> PolygonDataFetcher:
    """Get the singleton polygon fetcher (backward compat with polygon_helper)"""
    return polygon_fetcher


def get_historical_data(symbol: str, period: str = "90d", interval: str = "1d") -> List[Dict]:
    """
    Get historical data (backward compat with polygon_helper).

    Args:
        symbol: Stock symbol
        period: Period string like "90d", "1y"
        interval: Interval like "1d", "1h"

    Returns:
        List of dicts with OHLCV data
    """
    # Parse period
    days = 90
    if period.endswith('d'):
        days = int(period[:-1])
    elif period.endswith('y'):
        days = int(period[:-1]) * 365

    # Map interval to timeframe
    timeframe_map = {'1d': 'day', '1h': 'hour', '1m': 'minute', '5m': 'minute'}
    timeframe = timeframe_map.get(interval, 'day')
    multiplier = 5 if interval == '5m' else 1

    df = polygon_fetcher.get_price_history(symbol, days=days, timeframe=timeframe, multiplier=multiplier)
    if df is None:
        return []

    # Convert to list of dicts
    records = []
    for idx, row in df.iterrows():
        records.append({
            'timestamp': idx.isoformat() if hasattr(idx, 'isoformat') else str(idx),
            'open': row.get('Open', row.get('open', 0)),
            'high': row.get('High', row.get('high', 0)),
            'low': row.get('Low', row.get('low', 0)),
            'close': row.get('Close', row.get('close', 0)),
            'volume': row.get('Volume', row.get('volume', 0)),
        })
    return records


def fetch_vix_data() -> Dict:
    """
    Fetch VIX data (backward compat with polygon_helper).

    Returns:
        Dict with current VIX value and metadata
    """
    # Try to get VIX price
    price = polygon_fetcher.get_current_price('VIX')
    if price is None:
        price = polygon_fetcher.get_current_price('VIXY')  # Fallback ETF

    if price is None:
        # Return default
        return {
            'current': 20.0,
            'source': 'default',
            'timestamp': datetime.now().isoformat()
        }

    return {
        'current': price,
        'source': 'polygon',
        'timestamp': datetime.now().isoformat()
    }


# =============================================================================
# REAL DATA HELPERS FOR ML FEATURES
# =============================================================================

# Track VIX data availability globally for transparency
_vix_fetch_stats = {'real': 0, 'fallback': 0, 'errors': []}

# GEX data fetcher (uses TradingVolatilityAPI)
_gex_api = None
_gex_fetch_stats = {'real': 0, 'fallback': 0, 'errors': []}


def get_gex_data(symbol: str = 'SPY') -> Dict:
    """
    Fetch GEX (Gamma Exposure) data from Trading Volatility API.

    This uses the existing TradingVolatilityAPI class that was already built.

    Args:
        symbol: Stock symbol (default SPY)

    Returns:
        Dict with net_gex, put_wall, call_wall, or error
    """
    global _gex_api, _gex_fetch_stats

    try:
        # Lazy init the API
        if _gex_api is None:
            try:
                from core_classes_and_engines import TradingVolatilityAPI
                _gex_api = TradingVolatilityAPI()
            except ImportError as e:
                print(f"⚠️ TradingVolatilityAPI not available: {e}")
                _gex_fetch_stats['errors'].append(str(e))
                return {'error': 'TradingVolatilityAPI not available'}

        if not _gex_api.api_key:
            _gex_fetch_stats['fallback'] += 1
            return {'error': 'No Trading Volatility API key configured'}

        # Fetch GEX data
        result = _gex_api.get_net_gamma(symbol)

        if 'error' in result:
            _gex_fetch_stats['fallback'] += 1
            _gex_fetch_stats['errors'].append(result['error'])
            return result

        # Extract the important values
        net_gex = result.get('net_gex', result.get('netGamma', 0))
        put_wall = result.get('put_wall', 0)
        call_wall = result.get('call_wall', 0)

        _gex_fetch_stats['real'] += 1

        return {
            'net_gex': net_gex,
            'put_wall': put_wall,
            'call_wall': call_wall,
            'source': 'TRADING_VOLATILITY'
        }

    except Exception as e:
        print(f"❌ GEX fetch failed: {e}")
        _gex_fetch_stats['fallback'] += 1
        _gex_fetch_stats['errors'].append(str(e))
        return {'error': str(e)}


def get_gex_data_quality() -> dict:
    """Get statistics on GEX data availability"""
    global _gex_fetch_stats
    total = _gex_fetch_stats['real'] + _gex_fetch_stats['fallback']
    if total == 0:
        return {'available': False, 'message': 'No GEX requests made yet'}

    real_pct = _gex_fetch_stats['real'] / total * 100
    return {
        'available': _gex_fetch_stats['real'] > 0,
        'real_pct': round(real_pct, 1),
        'real_count': _gex_fetch_stats['real'],
        'fallback_count': _gex_fetch_stats['fallback'],
        'recent_errors': _gex_fetch_stats['errors'][-5:] if _gex_fetch_stats['errors'] else []
    }


def get_vix_for_date(date_str: str) -> float:
    """
    Get VIX value for a specific historical date.

    CRITICAL for backtesting - ML needs REAL VIX, not hardcoded 15.

    Args:
        date_str: Date in YYYY-MM-DD format

    Returns:
        VIX close value for that date, or estimated value if not available
    """
    global _vix_fetch_stats

    try:
        # Parse target date
        target_date = datetime.strptime(date_str, '%Y-%m-%d')

        # Get VIX history covering the target date
        days_ago = (datetime.now() - target_date).days + 5  # Buffer for weekends
        days_ago = max(5, min(days_ago, 400))  # Limit to ~1 year of data

        # CRITICAL FIX: VIX is an index - try multiple ticker formats
        # Polygon uses I:VIX for indices
        df = None
        vix_tickers = ['I:VIX', 'VIX', 'VIXY']  # Try index format first, then fallbacks

        for ticker in vix_tickers:
            df = polygon_fetcher.get_price_history(ticker, days=days_ago, timeframe='day')
            if df is not None and not df.empty:
                break

        if df is not None and not df.empty:
            # Find closest date
            df.index = pd.to_datetime(df.index)
            target = pd.Timestamp(target_date)

            # Get exact match or closest prior date
            prior_dates = df.index[df.index <= target]
            if len(prior_dates) > 0:
                closest_date = prior_dates[-1]
                vix_value = float(df.loc[closest_date, 'Close'])
                _vix_fetch_stats['real'] += 1
                return vix_value

        # Fallback: estimate VIX based on market conditions
        print(f"⚠️ WARNING: No VIX data for {date_str}, using estimate 18.0 (ML quality degraded)")
        _vix_fetch_stats['fallback'] += 1
        _vix_fetch_stats['errors'].append(f"No data for {date_str}")
        return 18.0  # Long-term VIX average

    except Exception as e:
        print(f"❌ VIX fetch failed for {date_str}: {e}")
        _vix_fetch_stats['fallback'] += 1
        _vix_fetch_stats['errors'].append(str(e))
        return 18.0


def get_vix_data_quality() -> dict:
    """Get statistics on VIX data availability"""
    global _vix_fetch_stats
    total = _vix_fetch_stats['real'] + _vix_fetch_stats['fallback']
    if total == 0:
        return {'real_pct': 100, 'total': 0, 'warning': None}

    real_pct = _vix_fetch_stats['real'] / total * 100
    warning = None
    if real_pct < 80:
        warning = f"Only {real_pct:.0f}% of VIX data from Polygon. ML features degraded."
    return {
        'real_pct': round(real_pct, 1),
        'real_count': _vix_fetch_stats['real'],
        'fallback_count': _vix_fetch_stats['fallback'],
        'total': total,
        'warning': warning,
        'recent_errors': _vix_fetch_stats['errors'][-5:] if _vix_fetch_stats['errors'] else []
    }


def calculate_iv_rank(symbol: str, current_iv: float, lookback_days: int = 252) -> float:
    """
    Calculate IV Rank: where is current IV relative to past year?

    IV Rank = (Current IV - Min IV) / (Max IV - Min IV) * 100

    CRITICAL for put selling - high IV rank = better premium.

    Args:
        symbol: Underlying symbol (e.g., 'SPY')
        current_iv: Current implied volatility (as decimal, e.g., 0.15 for 15%)
        lookback_days: Days to look back (default 252 = 1 year)

    Returns:
        IV Rank from 0-100 (100 = IV at yearly high)
    """
    try:
        # For options-based IV, we'd need historical IV data
        # As a proxy, we can use VIX for SPX/SPY since VIX is SPX implied vol
        if symbol.upper() in ['SPY', 'SPX', 'ES']:
            df = polygon_fetcher.get_price_history('VIX', days=lookback_days, timeframe='day')

            if df is not None and len(df) > 20:
                # Get min/max VIX over lookback period
                vix_min = df['Close'].min() / 100  # Convert to decimal
                vix_max = df['Close'].max() / 100

                # Calculate IV rank
                if vix_max > vix_min:
                    iv_rank = (current_iv - vix_min) / (vix_max - vix_min) * 100
                    iv_rank = max(0, min(100, iv_rank))  # Clamp to 0-100
                    print(f"✅ IV Rank for {symbol}: {iv_rank:.1f}% (IV={current_iv*100:.1f}%, range={vix_min*100:.1f}%-{vix_max*100:.1f}%)")
                    return iv_rank

        # Fallback: Use historical volatility as proxy
        price_df = polygon_fetcher.get_price_history(symbol, days=lookback_days, timeframe='day')

        if price_df is not None and len(price_df) > 20:
            # Calculate historical volatility (20-day rolling)
            returns = price_df['Close'].pct_change()
            hist_vol = returns.rolling(20).std() * math.sqrt(252)

            # Get min/max over lookback
            hv_min = hist_vol.min()
            hv_max = hist_vol.max()

            if hv_max > hv_min:
                # Use HV as proxy - IV usually trades above HV
                iv_rank = (current_iv - hv_min) / (hv_max - hv_min) * 100
                iv_rank = max(0, min(100, iv_rank))
                return iv_rank

        # Default to middle of range
        return 50.0

    except Exception as e:
        print(f"❌ Error calculating IV rank: {e}")
        return 50.0


def get_vix_term_structure() -> float:
    """
    Get VIX term structure: VIX - VIX3M

    Negative = contango (normal)
    Positive = backwardation (stress/fear)

    Returns:
        VIX - VIX3M spread
    """
    try:
        # Get VIX (30-day) and VIX3M (90-day)
        vix = polygon_fetcher.get_current_price('VIX')
        vix3m = polygon_fetcher.get_current_price('VIX3M')

        if vix and vix3m:
            spread = vix - vix3m
            print(f"✅ VIX term structure: VIX={vix:.2f}, VIX3M={vix3m:.2f}, spread={spread:.2f}")
            return spread

        # If VIX3M not available, estimate based on typical contango
        if vix:
            # Typical contango is ~5-10% VIX3M > VIX
            estimated_vix3m = vix * 1.07
            return vix - estimated_vix3m

        return 0.0  # Can't determine

    except Exception as e:
        print(f"❌ Error fetching VIX term structure: {e}")
        return 0.0


def get_spx_returns(date_str: str = None) -> Dict[str, float]:
    """
    Get SPX/SPY returns over various periods.

    Args:
        date_str: Reference date (default: today)

    Returns:
        Dict with 5d, 20d returns and distance from high
    """
    try:
        df = polygon_fetcher.get_price_history('SPY', days=100, timeframe='day')

        if df is None or len(df) < 20:
            return {'5d_return': 0, '20d_return': 0, 'distance_from_high': 0}

        # If specific date, filter to that date
        if date_str:
            target = pd.Timestamp(date_str)
            df = df[df.index <= target]

        if len(df) < 20:
            return {'5d_return': 0, '20d_return': 0, 'distance_from_high': 0}

        current = df['Close'].iloc[-1]

        # 5-day return
        ret_5d = (current / df['Close'].iloc[-6] - 1) * 100 if len(df) >= 6 else 0

        # 20-day return
        ret_20d = (current / df['Close'].iloc[-21] - 1) * 100 if len(df) >= 21 else 0

        # Distance from 52-week high
        high_52w = df['High'].max()
        distance_from_high = (current / high_52w - 1) * 100

        return {
            '5d_return': round(ret_5d, 2),
            '20d_return': round(ret_20d, 2),
            'distance_from_high': round(distance_from_high, 2)
        }

    except Exception as e:
        print(f"❌ Error calculating SPX returns: {e}")
        return {'5d_return': 0, '20d_return': 0, 'distance_from_high': 0}


def get_ml_features_for_trade(
    trade_date: str,
    strike: float,
    underlying_price: float,
    option_iv: float = None
) -> Dict:
    """
    Get ALL ML features for a trade - USING REAL DATA.

    This is the CRITICAL function that should be called when
    processing backtest trades for ML training.

    Args:
        trade_date: Trade date YYYY-MM-DD
        strike: Option strike price
        underlying_price: Underlying price at trade time
        option_iv: Option's implied volatility (if available)

    Returns:
        Dict with all ML features, including data quality indicators
    """
    features = {
        # Trade basics
        'trade_date': trade_date,
        'strike': strike,
        'underlying_price': underlying_price,

        # Data quality tracking
        'data_sources': {}
    }

    # 1. Get VIX for that date
    try:
        features['vix'] = get_vix_for_date(trade_date)
        features['data_sources']['vix'] = 'POLYGON'
    except:
        features['vix'] = 18.0
        features['data_sources']['vix'] = 'ESTIMATED'

    # 2. Calculate IV rank
    if option_iv:
        features['iv'] = option_iv
        features['iv_rank'] = calculate_iv_rank('SPY', option_iv)
        features['data_sources']['iv_rank'] = 'CALCULATED'
    else:
        # Use VIX as IV proxy
        features['iv'] = features['vix'] / 100  # Convert VIX to decimal IV
        features['iv_rank'] = calculate_iv_rank('SPY', features['iv'])
        features['data_sources']['iv_rank'] = 'VIX_PROXY'

    # 3. VIX term structure
    features['vix_term_structure'] = get_vix_term_structure()
    features['data_sources']['vix_term_structure'] = 'POLYGON' if features['vix_term_structure'] != 0 else 'ESTIMATED'

    # 4. SPX returns
    spx_data = get_spx_returns(trade_date)
    features['spx_5d_return'] = spx_data['5d_return']
    features['spx_20d_return'] = spx_data['20d_return']
    features['distance_from_high'] = spx_data['distance_from_high']
    features['data_sources']['spx_returns'] = 'POLYGON'

    # 5. Get GEX data from Trading Volatility API
    try:
        gex_data = get_gex_data('SPY')
        if 'error' not in gex_data:
            features['net_gex'] = gex_data.get('net_gex', 0) or 0
            features['put_wall'] = gex_data.get('put_wall') or 0
            features['call_wall'] = gex_data.get('call_wall') or 0

            # Calculate distances from walls (handle None values)
            put_wall = features['put_wall']
            call_wall = features['call_wall']

            if put_wall and put_wall > 0:
                features['put_wall_distance_pct'] = (underlying_price - put_wall) / underlying_price * 100
            else:
                features['put_wall_distance_pct'] = (underlying_price - strike) / underlying_price * 100

            if call_wall and call_wall > 0:
                features['call_wall_distance_pct'] = (call_wall - underlying_price) / underlying_price * 100
            else:
                features['call_wall_distance_pct'] = 5  # Default

            features['data_sources']['gex'] = 'TRADING_VOLATILITY'
        else:
            # GEX not available - use basic calculation
            features['net_gex'] = 0
            features['put_wall_distance_pct'] = (underlying_price - strike) / underlying_price * 100
            features['call_wall_distance_pct'] = 5
            features['data_sources']['gex'] = f"UNAVAILABLE: {gex_data.get('error', 'unknown')}"
    except Exception as e:
        features['net_gex'] = 0
        features['put_wall_distance_pct'] = (underlying_price - strike) / underlying_price * 100
        features['call_wall_distance_pct'] = 5
        features['data_sources']['gex'] = f"ERROR: {str(e)}"

    # 6. VIX percentile (where is VIX relative to history?)
    try:
        # Try I:VIX first (index format), then fallback to VIX
        vix_df = None
        for ticker in ['I:VIX', 'VIX']:
            vix_df = polygon_fetcher.get_price_history(ticker, days=252, timeframe='day')
            if vix_df is not None and len(vix_df) > 20:
                break

        if vix_df is not None and len(vix_df) > 20:
            vix_values = vix_df['Close'].values
            current_vix = features['vix']
            # Percentile rank
            percentile = sum(v < current_vix for v in vix_values) / len(vix_values) * 100
            features['vix_percentile'] = round(percentile, 1)
            features['data_sources']['vix_percentile'] = 'CALCULATED'
        else:
            features['vix_percentile'] = 50
            features['data_sources']['vix_percentile'] = 'ESTIMATED'
    except:
        features['vix_percentile'] = 50
        features['data_sources']['vix_percentile'] = 'ESTIMATED'

    # 7. Calculate data quality score
    real_sources = sum(1 for v in features['data_sources'].values()
                       if v in ['POLYGON', 'CALCULATED', 'TRADING_VOLATILITY', 'VIX_PROXY'])
    total_sources = len(features['data_sources'])
    features['data_quality_pct'] = round(real_sources / total_sources * 100, 1) if total_sources > 0 else 0

    return features
