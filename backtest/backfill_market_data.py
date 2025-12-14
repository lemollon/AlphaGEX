#!/usr/bin/env python3
"""
Backfill market data from Yahoo Finance directly (no yfinance library needed).
Stores SPX and VIX daily OHLC data in the database.
"""

import os
import sys
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import time

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database_adapter import get_connection, is_database_available


def fetch_yahoo_finance_data(symbol: str, start_date: str, end_date: str) -> List[Dict]:
    """
    Fetch historical data directly from Yahoo Finance API.

    Args:
        symbol: Yahoo Finance symbol (e.g., ^GSPC for S&P 500, ^VIX for VIX)
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format

    Returns:
        List of daily OHLC records
    """
    # Convert dates to Unix timestamps
    start_ts = int(datetime.strptime(start_date, "%Y-%m-%d").timestamp())
    end_ts = int(datetime.strptime(end_date, "%Y-%m-%d").timestamp())

    # Yahoo Finance API URL
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"

    params = {
        "period1": start_ts,
        "period2": end_ts,
        "interval": "1d",
        "events": "history",
        "includeAdjustedClose": "true"
    }

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    print(f"Fetching {symbol} from {start_date} to {end_date}...")

    response = requests.get(url, params=params, headers=headers)

    if response.status_code != 200:
        print(f"Error fetching {symbol}: HTTP {response.status_code}")
        print(response.text[:500])
        return []

    data = response.json()

    # Parse the response
    result = data.get("chart", {}).get("result", [])
    if not result:
        print(f"No data returned for {symbol}")
        return []

    chart_data = result[0]
    timestamps = chart_data.get("timestamp", [])
    quote = chart_data.get("indicators", {}).get("quote", [{}])[0]
    adjclose = chart_data.get("indicators", {}).get("adjclose", [{}])[0].get("adjclose", [])

    records = []
    for i, ts in enumerate(timestamps):
        try:
            date = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")

            open_price = quote.get("open", [])[i]
            high_price = quote.get("high", [])[i]
            low_price = quote.get("low", [])[i]
            close_price = quote.get("close", [])[i]
            volume = quote.get("volume", [])[i]
            adj_close = adjclose[i] if i < len(adjclose) else close_price

            # Skip if any price is None
            if any(p is None for p in [open_price, high_price, low_price, close_price]):
                continue

            records.append({
                "date": date,
                "open": round(float(open_price), 2),
                "high": round(float(high_price), 2),
                "low": round(float(low_price), 2),
                "close": round(float(close_price), 2),
                "adj_close": round(float(adj_close), 2) if adj_close else round(float(close_price), 2),
                "volume": int(volume) if volume else 0
            })
        except (IndexError, TypeError) as e:
            continue

    print(f"  Retrieved {len(records)} records for {symbol}")
    return records


def ensure_table_exists():
    """Create the market_data_daily table if it doesn't exist."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS market_data_daily (
            id SERIAL PRIMARY KEY,
            symbol VARCHAR(20) NOT NULL,
            date DATE NOT NULL,
            open DECIMAL(12,4),
            high DECIMAL(12,4),
            low DECIMAL(12,4),
            close DECIMAL(12,4),
            adj_close DECIMAL(12,4),
            volume BIGINT,
            source VARCHAR(50) DEFAULT 'yahoo',
            created_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(symbol, date)
        )
    """)

    # Create index for faster queries
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_market_data_daily_symbol_date
        ON market_data_daily(symbol, date)
    """)

    conn.commit()
    conn.close()
    print("✅ Table market_data_daily ready")


def store_market_data(symbol: str, data: List[Dict], source: str = "yahoo") -> int:
    """
    Store market data in the database.

    Args:
        symbol: Normalized symbol (e.g., SPX, VIX)
        data: List of OHLC records
        source: Data source identifier

    Returns:
        Number of records inserted/updated
    """
    if not data:
        print(f"No data to store for {symbol}")
        return 0

    conn = get_connection()
    cursor = conn.cursor()

    total_inserted = 0

    for record in data:
        try:
            # Use INSERT ... ON CONFLICT DO UPDATE for upsert
            cursor.execute("""
                INSERT INTO market_data_daily (symbol, date, open, high, low, close, adj_close, volume, source)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (symbol, date) DO UPDATE SET
                    open = EXCLUDED.open,
                    high = EXCLUDED.high,
                    low = EXCLUDED.low,
                    close = EXCLUDED.close,
                    adj_close = EXCLUDED.adj_close,
                    volume = EXCLUDED.volume,
                    source = EXCLUDED.source
            """, (
                symbol,
                record["date"],
                record["open"],
                record["high"],
                record["low"],
                record["close"],
                record.get("adj_close", record["close"]),
                record.get("volume", 0),
                source
            ))
            total_inserted += 1
        except Exception as e:
            print(f"  Error inserting record for {record['date']}: {e}")

    conn.commit()
    conn.close()

    print(f"  Stored {total_inserted} records for {symbol}")
    return total_inserted


def backfill_all(start_date: str = "2020-01-01", end_date: Optional[str] = None):
    """
    Backfill all required market data.

    Args:
        start_date: Start date for backfill
        end_date: End date for backfill (defaults to today)
    """
    if not is_database_available():
        print("❌ Database not available. Set DATABASE_URL environment variable.")
        return 0

    if end_date is None:
        end_date = datetime.now().strftime("%Y-%m-%d")

    # Ensure table exists
    ensure_table_exists()

    # Symbols to backfill: (yahoo_symbol, normalized_symbol)
    symbols = [
        ("^GSPC", "SPX"),   # S&P 500 index
        ("^VIX", "VIX"),    # VIX volatility index
        ("SPY", "SPY"),     # SPY ETF
    ]

    print("=" * 60)
    print("Market Data Backfill")
    print("=" * 60)
    print(f"Date Range: {start_date} to {end_date}")
    print()

    total_records = 0

    for yahoo_symbol, normalized_symbol in symbols:
        print(f"\n--- {normalized_symbol} ({yahoo_symbol}) ---")

        # Fetch data
        data = fetch_yahoo_finance_data(yahoo_symbol, start_date, end_date)

        if data:
            # Store data
            count = store_market_data(normalized_symbol, data)
            total_records += count

        # Small delay between requests
        time.sleep(1)

    print("\n" + "=" * 60)
    print(f"Backfill Complete: {total_records} total records")
    print("=" * 60)

    return total_records


def check_data_status():
    """Check the current status of stored data."""
    if not is_database_available():
        print("❌ Database not available")
        return

    conn = get_connection()
    cursor = conn.cursor()

    print("\n--- Stored Data Status ---")

    for symbol in ["SPX", "VIX", "SPY"]:
        try:
            # Get count
            cursor.execute("""
                SELECT COUNT(*) FROM market_data_daily WHERE symbol = %s
            """, (symbol,))
            count = cursor.fetchone()[0]

            # Get date range
            cursor.execute("""
                SELECT MIN(date), MAX(date) FROM market_data_daily WHERE symbol = %s
            """, (symbol,))
            row = cursor.fetchone()
            first_date = row[0] if row[0] else "N/A"
            last_date = row[1] if row[1] else "N/A"

            print(f"{symbol}: {count} records ({first_date} to {last_date})")

        except Exception as e:
            print(f"{symbol}: Error checking status - {e}")

    conn.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Backfill market data from Yahoo Finance")
    parser.add_argument("--start", default="2020-01-01", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", default=None, help="End date (YYYY-MM-DD), defaults to today")
    parser.add_argument("--status", action="store_true", help="Check data status only")

    args = parser.parse_args()

    if args.status:
        check_data_status()
    else:
        backfill_all(args.start, args.end)
        check_data_status()
