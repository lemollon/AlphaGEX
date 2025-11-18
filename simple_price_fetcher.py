"""
Simple Price Data Fetcher - Minimal dependencies fallback for backtesting

Uses free public APIs with no complex dependencies
"""

import requests
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional

def fetch_yahoo_csv(symbol: str, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
    """
    Fetch data using Yahoo Finance CSV download API (no dependencies needed)

    This is a direct CSV download that doesn't require yfinance library
    """
    try:
        # Convert dates to Unix timestamps
        start_dt = datetime.strptime(start_date, '%Y-%m-%d')
        end_dt = datetime.strptime(end_date, '%Y-%m-%d')

        start_ts = int(start_dt.timestamp())
        end_ts = int(end_dt.timestamp())

        # Yahoo Finance CSV download URL
        url = f"https://query1.finance.yahoo.com/v7/finance/download/{symbol}"
        params = {
            'period1': start_ts,
            'period2': end_ts,
            'interval': '1d',
            'events': 'history',
            'includeAdjustedClose': 'true'
        }

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }

        response = requests.get(url, params=params, headers=headers, timeout=30)
        response.raise_for_status()

        # Parse CSV response
        from io import StringIO
        df = pd.read_csv(StringIO(response.text), parse_dates=['Date'])
        df.set_index('Date', inplace=True)

        # Standardize column names
        df = df.rename(columns={
            'Adj Close': 'Close'  # Use adjusted close as Close
        })

        return df

    except Exception as e:
        print(f"⚠️  Yahoo CSV fetch failed: {e}")
        return None


def generate_test_data(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    """
    Generate synthetic price data for backtesting when real data unavailable

    Creates realistic-looking OHLCV data with:
    - Trend + noise
    - Realistic daily ranges
    - Volume variation
    """
    import numpy as np

    start_dt = datetime.strptime(start_date, '%Y-%m-%d')
    end_dt = datetime.strptime(end_date, '%Y-%m-%d')

    # Generate date range (trading days only - rough approximation)
    dates = pd.date_range(start=start_dt, end=end_dt, freq='D')
    dates = [d for d in dates if d.weekday() < 5]  # Remove weekends

    n_days = len(dates)

    # Generate price series with trend and volatility
    np.random.seed(42)  # Reproducible data

    # Starting price (SPY-like ~$450-500)
    base_price = 470.0

    # Generate returns with drift and volatility
    drift = 0.0003  # ~0.03% daily drift (positive trend)
    volatility = 0.012  # ~1.2% daily volatility

    returns = np.random.normal(drift, volatility, n_days)
    prices = base_price * np.cumprod(1 + returns)

    # Generate OHLC
    df = pd.DataFrame(index=dates)
    df['Close'] = prices

    # Generate Open (previous close + small gap)
    df['Open'] = df['Close'].shift(1).fillna(base_price) * (1 + np.random.normal(0, 0.001, n_days))

    # Generate High/Low (Close + realistic range)
    daily_range = np.random.uniform(0.005, 0.015, n_days)  # 0.5-1.5% daily range
    df['High'] = df[['Open', 'Close']].max(axis=1) * (1 + daily_range * 0.7)
    df['Low'] = df[['Open', 'Close']].min(axis=1) * (1 - daily_range * 0.7)

    # Generate Volume (millions of shares)
    df['Volume'] = np.random.lognormal(17, 0.3, n_days)  # Realistic volume distribution

    return df


def get_price_history(symbol: str, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
    """
    Get historical price data using simple CSV download, with test data fallback

    Args:
        symbol: Stock symbol (e.g., 'SPY')
        start_date: Start date 'YYYY-MM-DD'
        end_date: End date 'YYYY-MM-DD'

    Returns:
        DataFrame with OHLCV data or None if failed
    """
    print(f"Fetching {symbol} from {start_date} to {end_date} via Yahoo CSV...")

    df = fetch_yahoo_csv(symbol, start_date, end_date)

    if df is not None and not df.empty:
        print(f"✓ Fetched {len(df)} days of data")
        return df

    print("⚠️  Real data unavailable - generating synthetic test data for backtesting")
    print("   NOTE: This is for testing the backtest framework only")
    print("   Results will NOT reflect real market conditions")
    df = generate_test_data(symbol, start_date, end_date)
    print(f"✓ Generated {len(df)} days of synthetic data")
    return df


# Test function
if __name__ == "__main__":
    df = get_price_history('SPY', '2024-01-01', '2024-01-31')
    if df is not None:
        print("\nSample data:")
        print(df.head())
        print(f"\nColumns: {list(df.columns)}")
