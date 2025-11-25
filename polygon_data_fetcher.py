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
        self.api_key = os.getenv("POLYGON_API_KEY")
        if not self.api_key:
            print("⚠️  POLYGON_API_KEY not set - data fetching will fail")

        self.cache = PolygonDataCache()
        self.base_url = "https://api.polygon.io"
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

                    return {
                        'bid': bid,
                        'ask': ask,
                        'last': last_trade.get('price', 0),
                        'mid': (bid + ask) / 2,
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
    mid = quote.get('mid', 0) or (bid + ask) / 2
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
    mid = quote.get('mid', 0) or (bid + ask) / 2
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
    except:
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
