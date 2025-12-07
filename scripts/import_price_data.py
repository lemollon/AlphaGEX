#!/usr/bin/env python3
"""
Price Data Importer for Backtesting

Fetches historical price data for SPX, SPY, and VIX from Polygon.io
with Yahoo Finance as fallback.

Usage:
    # Import all prices (2020-present):
    python scripts/import_price_data.py

    # Import specific date range:
    python scripts/import_price_data.py --start 2020-01-01 --end 2024-12-31

    # Import specific symbol:
    python scripts/import_price_data.py --symbol SPY
"""

import os
import sys
import csv
import argparse
import time
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Dict, List, Optional
import requests

# Add parent directory for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load environment
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / '.env')

# API Keys
POLYGON_API_KEY = os.getenv('POLYGON_API_KEY', '')

# Paths
PRICES_DIR = Path(__file__).parent.parent / 'data' / 'prices'

# Symbols to fetch
SYMBOLS = {
    'SPY': 'SPY',           # SPY ETF
    'SPX': 'I:SPX',         # S&P 500 Index (Polygon format)
    'VIX': 'I:VIX',         # VIX Index (Polygon format)
}

# Yahoo Finance fallback symbols
YAHOO_SYMBOLS = {
    'SPY': 'SPY',
    'SPX': '^GSPC',         # S&P 500 on Yahoo
    'VIX': '^VIX',          # VIX on Yahoo
}


def fetch_polygon_prices(symbol: str, polygon_symbol: str,
                         start_date: date, end_date: date) -> List[Dict]:
    """Fetch daily OHLCV data from Polygon.io"""
    if not POLYGON_API_KEY:
        print(f"  ⚠️ POLYGON_API_KEY not set - skipping Polygon")
        return []

    all_data = []
    current_start = start_date

    while current_start < end_date:
        # Polygon has a limit, so we fetch in chunks
        chunk_end = min(current_start + timedelta(days=365), end_date)

        url = f"https://api.polygon.io/v2/aggs/ticker/{polygon_symbol}/range/1/day/{current_start}/{chunk_end}"
        params = {
            'apiKey': POLYGON_API_KEY,
            'adjusted': 'true',
            'sort': 'asc',
            'limit': 50000
        }

        try:
            response = requests.get(url, params=params, timeout=30)

            if response.status_code == 200:
                data = response.json()
                results = data.get('results', [])

                for bar in results:
                    all_data.append({
                        'date': datetime.fromtimestamp(bar['t'] / 1000).date(),
                        'symbol': symbol,
                        'open': bar.get('o', 0),
                        'high': bar.get('h', 0),
                        'low': bar.get('l', 0),
                        'close': bar.get('c', 0),
                        'volume': bar.get('v', 0),
                        'vwap': bar.get('vw', 0),
                        'source': 'polygon'
                    })

                print(f"    Polygon: {len(results)} bars for {current_start} to {chunk_end}")

            elif response.status_code == 429:
                print(f"    ⚠️ Rate limited - waiting 60s")
                time.sleep(60)
                continue
            else:
                print(f"    ⚠️ Polygon error {response.status_code}: {response.text[:100]}")

        except Exception as e:
            print(f"    ⚠️ Polygon request failed: {e}")

        current_start = chunk_end + timedelta(days=1)
        time.sleep(0.5)  # Rate limiting

    return all_data


def fetch_yahoo_prices(symbol: str, yahoo_symbol: str,
                       start_date: date, end_date: date) -> List[Dict]:
    """Fetch daily OHLCV data from Yahoo Finance (fallback)"""
    try:
        import yfinance as yf
    except ImportError:
        print(f"  ⚠️ yfinance not installed - run: pip install yfinance")
        return []

    all_data = []

    try:
        ticker = yf.Ticker(yahoo_symbol)
        df = ticker.history(start=start_date, end=end_date + timedelta(days=1))

        if df.empty:
            print(f"    ⚠️ Yahoo returned no data for {yahoo_symbol}")
            return []

        for idx, row in df.iterrows():
            all_data.append({
                'date': idx.date() if hasattr(idx, 'date') else idx,
                'symbol': symbol,
                'open': row.get('Open', 0),
                'high': row.get('High', 0),
                'low': row.get('Low', 0),
                'close': row.get('Close', 0),
                'volume': row.get('Volume', 0),
                'vwap': 0,  # Yahoo doesn't provide VWAP
                'source': 'yahoo'
            })

        print(f"    Yahoo: {len(all_data)} bars")

    except Exception as e:
        print(f"    ⚠️ Yahoo request failed: {e}")

    return all_data


def save_to_csv(data: List[Dict], symbol: str) -> Path:
    """Save price data to CSV file"""
    if not data:
        return None

    output_path = PRICES_DIR / f'{symbol.lower()}_prices.csv'

    with open(output_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['date', 'symbol', 'open', 'high', 'low', 'close', 'volume', 'vwap', 'source'])
        writer.writeheader()
        writer.writerows(data)

    return output_path


def import_to_database(data: List[Dict], table_name: str = 'underlying_prices') -> int:
    """Import price data into the database"""
    try:
        from database_adapter import get_connection
    except ImportError:
        print("  ⚠️ Database not available - skipping DB import")
        return 0

    rows_imported = 0

    try:
        conn = get_connection()
        cursor = conn.cursor()

        for row in data:
            try:
                cursor.execute(f"""
                    INSERT INTO {table_name} (
                        trade_date, symbol, open, high, low, close, volume, vwap, source
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    ON CONFLICT (trade_date, symbol) DO UPDATE SET
                        open = EXCLUDED.open,
                        high = EXCLUDED.high,
                        low = EXCLUDED.low,
                        close = EXCLUDED.close,
                        volume = EXCLUDED.volume,
                        vwap = EXCLUDED.vwap,
                        source = EXCLUDED.source
                """, (
                    row['date'],
                    row['symbol'],
                    row['open'],
                    row['high'],
                    row['low'],
                    row['close'],
                    row['volume'],
                    row['vwap'],
                    row['source']
                ))
                rows_imported += 1

            except Exception as e:
                continue

        conn.commit()
        conn.close()

    except Exception as e:
        print(f"  ❌ Database error: {e}")

    return rows_imported


def main():
    parser = argparse.ArgumentParser(description='Import price data for backtesting')
    parser.add_argument('--start', type=str, default='2020-01-01', help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, default=None, help='End date (YYYY-MM-DD), defaults to today')
    parser.add_argument('--symbol', type=str, choices=['SPY', 'SPX', 'VIX', 'ALL'], default='ALL',
                        help='Symbol to fetch (default: ALL)')
    parser.add_argument('--no-db', action='store_true', help='Skip database import')
    parser.add_argument('--yahoo-only', action='store_true', help='Use Yahoo Finance only (skip Polygon)')
    args = parser.parse_args()

    # Parse dates
    start_date = datetime.strptime(args.start, '%Y-%m-%d').date()
    end_date = datetime.strptime(args.end, '%Y-%m-%d').date() if args.end else date.today()

    print("=" * 70)
    print("📈 PRICE DATA IMPORTER (Polygon + Yahoo Finance)")
    print("=" * 70)
    print(f"\n📅 Date range: {start_date} to {end_date}")
    print(f"📁 Output: {PRICES_DIR}")

    if POLYGON_API_KEY and not args.yahoo_only:
        print(f"🔑 Polygon API: Configured ({POLYGON_API_KEY[:8]}...)")
    else:
        print("🔑 Polygon API: Not configured - using Yahoo Finance only")

    # Ensure directory exists
    PRICES_DIR.mkdir(parents=True, exist_ok=True)

    # Determine which symbols to fetch
    symbols_to_fetch = [args.symbol] if args.symbol != 'ALL' else list(SYMBOLS.keys())

    total_stats = {
        'symbols': 0,
        'bars': 0,
        'db_rows': 0
    }

    for symbol in symbols_to_fetch:
        print(f"\n{'='*50}")
        print(f"📊 Fetching {symbol}...")

        polygon_symbol = SYMBOLS.get(symbol, symbol)
        yahoo_symbol = YAHOO_SYMBOLS.get(symbol, symbol)

        all_data = []

        # Try Polygon first (unless yahoo-only)
        if POLYGON_API_KEY and not args.yahoo_only:
            polygon_data = fetch_polygon_prices(symbol, polygon_symbol, start_date, end_date)
            all_data.extend(polygon_data)

        # Fallback to Yahoo if no Polygon data
        if not all_data:
            print(f"  Trying Yahoo Finance fallback...")
            yahoo_data = fetch_yahoo_prices(symbol, yahoo_symbol, start_date, end_date)
            all_data.extend(yahoo_data)

        if all_data:
            # Remove duplicates (prefer Polygon over Yahoo)
            seen_dates = set()
            unique_data = []
            for row in sorted(all_data, key=lambda x: (x['date'], x['source'])):
                if row['date'] not in seen_dates:
                    seen_dates.add(row['date'])
                    unique_data.append(row)

            all_data = unique_data

            # Save to CSV
            csv_path = save_to_csv(all_data, symbol)
            print(f"  💾 Saved {len(all_data)} bars to {csv_path.name}")

            # Import to database
            if not args.no_db:
                table = 'vix_history' if symbol == 'VIX' else 'underlying_prices'
                db_rows = import_to_database(all_data, table)
                print(f"  📥 Imported {db_rows} rows to database")
                total_stats['db_rows'] += db_rows

            total_stats['symbols'] += 1
            total_stats['bars'] += len(all_data)
        else:
            print(f"  ❌ No data retrieved for {symbol}")

    # Summary
    print("\n" + "=" * 70)
    print("📊 IMPORT SUMMARY")
    print("=" * 70)
    print(f"  Symbols processed: {total_stats['symbols']}")
    print(f"  Total price bars: {total_stats['bars']:,}")
    if not args.no_db:
        print(f"  Database rows imported: {total_stats['db_rows']:,}")
    print("=" * 70)


if __name__ == '__main__':
    main()
