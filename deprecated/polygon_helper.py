"""
Polygon.io Helper Module
Reusable functions for fetching market data from Polygon.io
Replaces Yahoo Finance (yfinance) across AlphaGEX platform
"""

import os
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import time


class PolygonDataFetcher:
    """
    Centralized Polygon.io data fetcher
    Provides reusable functions for fetching price data, replacing yfinance
    """

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Polygon.io fetcher

        Args:
            api_key: Optional API key, otherwise reads from environment
        """
        self.api_key = api_key or os.getenv("POLYGON_API_KEY")
        if not self.api_key:
            raise ValueError("POLYGON_API_KEY not configured in environment")

        self.base_url = "https://api.polygon.io/v2"
        self._cache = {}
        self._cache_ttl = 300  # 5 minutes default cache

    def get_current_price(self, symbol: str) -> float:
        """
        Get current price for symbol (equivalent to yf.Ticker().info['currentPrice'])

        Args:
            symbol: Stock symbol (e.g., 'SPY')

        Returns:
            Current price as float
        """
        try:
            # Get last trade
            url = f"{self.base_url}/last/trade/{symbol}"
            params = {"apiKey": self.api_key}

            response = requests.get(url, params=params, timeout=10)

            if response.status_code == 200:
                data = response.json()
                if data.get('status') == 'OK' and data.get('results'):
                    return float(data['results']['p'])  # price

            # Fallback: Get latest daily close
            return self.get_daily_bars(symbol, days=1)[0]['close']

        except Exception as e:
            print(f"Error getting current price: {e}")
            raise

    def get_daily_bars(self, symbol: str, days: int = 90) -> List[Dict]:
        """
        Get daily OHLCV bars (equivalent to yf.Ticker().history(period='90d'))

        Args:
            symbol: Stock symbol
            days: Number of days of history

        Returns:
            List of dicts with keys: close, high, low, open, volume, time
        """
        to_date = datetime.now().strftime('%Y-%m-%d')
        from_date = (datetime.now() - timedelta(days=days + 10)).strftime('%Y-%m-%d')

        url = f"{self.base_url}/aggs/ticker/{symbol}/range/1/day/{from_date}/{to_date}"
        params = {"apiKey": self.api_key, "sort": "asc", "limit": 50000}

        response = requests.get(url, params=params, timeout=10)

        if response.status_code == 200:
            data = response.json()
            if data.get('status') in ['OK', 'DELAYED'] and data.get('results'):
                return [
                    {
                        'close': bar['c'],
                        'high': bar['h'],
                        'low': bar['l'],
                        'open': bar['o'],
                        'volume': bar.get('v', 0),  # VIX and other indices don't have volume
                        'time': bar['t']
                    }
                    for bar in data['results']
                ]

        raise Exception(f"Failed to fetch daily bars: {response.status_code}")

    def get_intraday_bars(self, symbol: str, multiplier: int, timespan: str, days: int) -> List[Dict]:
        """
        Get intraday bars at any timeframe

        Args:
            symbol: Stock symbol
            multiplier: Time multiplier (e.g., 5 for 5-minute bars)
            timespan: 'minute', 'hour', 'day'
            days: Number of days back to fetch

        Returns:
            List of dicts with OHLCV data
        """
        to_date = datetime.now().strftime('%Y-%m-%d')
        from_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

        url = f"{self.base_url}/aggs/ticker/{symbol}/range/{multiplier}/{timespan}/{from_date}/{to_date}"
        params = {"apiKey": self.api_key, "sort": "asc", "limit": 50000}

        response = requests.get(url, params=params, timeout=10)

        if response.status_code == 200:
            data = response.json()
            if data.get('status') in ['OK', 'DELAYED'] and data.get('results'):
                return [
                    {
                        'close': bar['c'],
                        'high': bar['h'],
                        'low': bar['l'],
                        'open': bar['o'],
                        'volume': bar.get('v', 0),  # VIX and other indices don't have volume
                        'time': bar['t']
                    }
                    for bar in data['results']
                ]

        return []  # Return empty list on failure

    def get_vix_data(self) -> Dict:
        """
        Fetch VIX (Volatility Index) data from Polygon.io
        Replaces: yf.Ticker("^VIX").history()

        Returns:
            {
                'current': float,  # Current VIX level
                'previous_close': float,  # Yesterday's close
                'change_pct': float,  # % change from previous close
                'intraday_high': float,  # Today's high
                'intraday_low': float,  # Today's low
                'ma_20': float,  # 20-day moving average
                'spike_detected': bool  # True if VIX spiked >20%
            }
        """
        try:
            # Polygon uses I:VIX for VIX index
            vix_symbol = "I:VIX"

            # Get 60 days of VIX data for MA calculation
            vix_bars = self.get_daily_bars(vix_symbol, days=60)

            if not vix_bars or len(vix_bars) < 2:
                return self._get_default_vix_data()

            current = vix_bars[-1]['close']
            previous_close = vix_bars[-2]['close']
            intraday_high = vix_bars[-1]['high']
            intraday_low = vix_bars[-1]['low']

            # Calculate 20-day MA
            if len(vix_bars) >= 20:
                recent_closes = [bar['close'] for bar in vix_bars[-20:]]
                ma_20 = sum(recent_closes) / len(recent_closes)
            else:
                ma_20 = current

            # Calculate change
            change_pct = ((current - previous_close) / previous_close * 100) if previous_close > 0 else 0

            # Detect spike (>20% increase OR crossed above MA by >15%)
            spike_detected = (change_pct > 20) or (current > ma_20 * 1.15 and previous_close < ma_20)

            return {
                'current': current,
                'previous_close': previous_close,
                'change_pct': change_pct,
                'intraday_high': intraday_high,
                'intraday_low': intraday_low,
                'ma_20': ma_20,
                'spike_detected': spike_detected
            }

        except Exception as e:
            print(f"Error fetching VIX data from Polygon.io: {e}")
            return self._get_default_vix_data()

    def _get_default_vix_data(self) -> Dict:
        """Return default VIX data when fetch fails"""
        return {
            'current': 20.0,
            'previous_close': 20.0,
            'change_pct': 0.0,
            'intraday_high': 21.0,
            'intraday_low': 19.0,
            'ma_20': 20.0,
            'spike_detected': False
        }

    def get_multi_timeframe_data(self, symbol: str, current_price: float) -> Dict[str, List[Dict]]:
        """
        Get price data across multiple timeframes
        Equivalent to calling yf.Ticker().history() multiple times with different intervals

        This is the main function used to replace yfinance in psychology_trap_detector

        Args:
            symbol: Stock symbol
            current_price: Current price (from GEX data)

        Returns:
            Dict with keys '5m', '15m', '1h', '4h', '1d' containing price data
        """
        print(f"📊 Fetching multi-timeframe data for {symbol} from Polygon.io")

        price_data = {}

        try:
            # 1-day data (90 days back)
            print(f"  🔄 Fetching 1d data...")
            bars_1d = self.get_daily_bars(symbol, days=90)
            price_data['1d'] = bars_1d
            print(f"  ✅ 1d data: {len(bars_1d)} bars")

            # 4-hour data (30 days back)
            print(f"  🔄 Fetching 4h data...")
            bars_4h = self.get_intraday_bars(symbol, 4, 'hour', 30)
            price_data['4h'] = bars_4h
            print(f"  ✅ 4h data: {len(bars_4h)} bars")

            # 1-hour data (14 days back)
            print(f"  🔄 Fetching 1h data...")
            bars_1h = self.get_intraday_bars(symbol, 1, 'hour', 14)
            price_data['1h'] = bars_1h
            print(f"  ✅ 1h data: {len(bars_1h)} bars")

            # 15-minute data (7 days back)
            print(f"  🔄 Fetching 15m data...")
            bars_15m = self.get_intraday_bars(symbol, 15, 'minute', 7)
            price_data['15m'] = bars_15m
            print(f"  ✅ 15m data: {len(bars_15m)} bars")

            # 5-minute data (3 days back)
            print(f"  🔄 Fetching 5m data...")
            bars_5m = self.get_intraday_bars(symbol, 5, 'minute', 3)
            price_data['5m'] = bars_5m
            print(f"  ✅ 5m data: {len(bars_5m)} bars")

            return price_data

        except Exception as e:
            print(f"❌ Error fetching multi-timeframe data: {e}")
            raise


# Convenience function for backwards compatibility
def get_polygon_data_fetcher() -> PolygonDataFetcher:
    """
    Get a configured Polygon.io data fetcher instance

    Returns:
        PolygonDataFetcher instance
    """
    return PolygonDataFetcher()


# Simple replacement functions for common yfinance patterns
def get_current_price(symbol: str) -> float:
    """
    Replace: yf.Ticker(symbol).history(period='1d')['Close'].iloc[-1]
    With: get_current_price(symbol)
    """
    fetcher = get_polygon_data_fetcher()
    return fetcher.get_current_price(symbol)


def get_historical_data(symbol: str, period: str = "90d", interval: str = "1d") -> List[Dict]:
    """
    Replace: yf.Ticker(symbol).history(period=period, interval=interval)
    With: get_historical_data(symbol, period, interval)

    Args:
        symbol: Stock symbol
        period: Time period (e.g., '90d', '30d', '7d')
        interval: Time interval (e.g., '1d', '1h', '15m', '5m')

    Returns:
        List of OHLCV dicts
    """
    fetcher = get_polygon_data_fetcher()

    # Parse period to days
    days = int(period.replace('d', ''))

    # Parse interval
    if interval == '1d':
        return fetcher.get_daily_bars(symbol, days)
    elif interval == '1h':
        return fetcher.get_intraday_bars(symbol, 1, 'hour', days)
    elif interval == '15m':
        return fetcher.get_intraday_bars(symbol, 15, 'minute', days)
    elif interval == '5m':
        return fetcher.get_intraday_bars(symbol, 5, 'minute', days)
    elif interval == '4h':
        return fetcher.get_intraday_bars(symbol, 4, 'hour', days)
    else:
        raise ValueError(f"Unsupported interval: {interval}")


def fetch_vix_data() -> Dict:
    """
    Fetch VIX data from Polygon.io
    Replace: yf.Ticker("^VIX").history()
    With: fetch_vix_data()

    Returns:
        Dict with VIX data (current, previous_close, change_pct, etc.)
    """
    fetcher = get_polygon_data_fetcher()
    return fetcher.get_vix_data()


if __name__ == "__main__":
    # Test the module
    print("Testing Polygon.io Data Fetcher...")

    try:
        fetcher = get_polygon_data_fetcher()

        # Test current price
        print(f"\n1. Testing current price for SPY...")
        price = fetcher.get_current_price("SPY")
        print(f"   ✅ Current SPY price: ${price:.2f}")

        # Test daily bars
        print(f"\n2. Testing daily bars...")
        daily = fetcher.get_daily_bars("SPY", days=5)
        print(f"   ✅ Got {len(daily)} daily bars")
        print(f"   Latest close: ${daily[-1]['close']:.2f}")

        # Test multi-timeframe
        print(f"\n3. Testing multi-timeframe data...")
        mtf_data = fetcher.get_multi_timeframe_data("SPY", price)
        print(f"   ✅ Got data for {len(mtf_data)} timeframes")
        for tf, data in mtf_data.items():
            print(f"      {tf}: {len(data)} bars")

        print("\n✅ All tests passed!")

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
