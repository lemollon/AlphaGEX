#!/usr/bin/env python3
"""
Fast SQLite Importer for ORAT Data

Imports CSV files to a local SQLite database for fast backtesting.
Much faster than remote PostgreSQL - no network latency.

Usage:
    python scripts/import_to_sqlite.py --start 2020-01-01 --end 2025-12-31
"""

import os
import sys
import csv
import sqlite3
import argparse
from datetime import datetime
from pathlib import Path

# Paths
SCRIPT_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent
ORAT_PROCESSED_DIR = PROJECT_DIR / 'data' / 'orat_processed'
SQLITE_DB_PATH = PROJECT_DIR / 'data' / 'backtest.db'


def create_tables(conn):
    """Create SQLite tables"""
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orat_options_eod (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_date TEXT NOT NULL,
            ticker TEXT NOT NULL,
            expiration_date TEXT,
            strike REAL,
            option_type TEXT,
            call_bid REAL,
            call_ask REAL,
            call_mid REAL,
            put_bid REAL,
            put_ask REAL,
            put_mid REAL,
            delta REAL,
            gamma REAL,
            theta REAL,
            vega REAL,
            rho REAL,
            call_iv REAL,
            put_iv REAL,
            underlying_price REAL,
            dte INTEGER,
            call_volume INTEGER,
            put_volume INTEGER,
            call_oi INTEGER,
            put_oi INTEGER
        )
    """)

    # Create indexes for fast queries
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_trade_date ON orat_options_eod(trade_date)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ticker ON orat_options_eod(ticker)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_expiration ON orat_options_eod(expiration_date)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_dte ON orat_options_eod(dte)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_strike ON orat_options_eod(strike)")

    # Unique constraint to prevent duplicates
    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_option
        ON orat_options_eod(trade_date, ticker, expiration_date, strike)
    """)

    conn.commit()


def import_csv_to_sqlite(conn, csv_path: Path) -> int:
    """Import a single CSV file to SQLite"""
    cursor = conn.cursor()

    # Parse trade date from filename
    date_str = csv_path.stem.replace('orat_spx_', '')
    trade_date = date_str[:4] + '-' + date_str[4:6] + '-' + date_str[6:8]

    rows_imported = 0
    batch = []
    BATCH_SIZE = 5000  # Larger batches for SQLite

    insert_sql = """
        INSERT OR IGNORE INTO orat_options_eod (
            trade_date, ticker, expiration_date, strike, option_type,
            call_bid, call_ask, call_mid, put_bid, put_ask, put_mid,
            delta, gamma, theta, vega, rho,
            call_iv, put_iv, underlying_price, dte,
            call_volume, put_volume, call_oi, put_oi
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)

        for row in reader:
            try:
                exp_date = row.get('expirDate', '')
                yte = float(row.get('yte', 0) or 0)
                dte = int(yte * 365)

                row_data = (
                    trade_date,
                    row.get('ticker', ''),
                    exp_date,
                    float(row.get('strike', 0) or 0),
                    'BOTH',
                    float(row.get('cBidPx', 0) or 0),
                    float(row.get('cAskPx', 0) or 0),
                    (float(row.get('cBidPx', 0) or 0) + float(row.get('cAskPx', 0) or 0)) / 2,
                    float(row.get('pBidPx', 0) or 0),
                    float(row.get('pAskPx', 0) or 0),
                    (float(row.get('pBidPx', 0) or 0) + float(row.get('pAskPx', 0) or 0)) / 2,
                    float(row.get('delta', 0) or 0),
                    float(row.get('gamma', 0) or 0),
                    float(row.get('theta', 0) or 0),
                    float(row.get('vega', 0) or 0),
                    float(row.get('rho', 0) or 0),
                    float(row.get('cMidIv', 0) or 0),
                    float(row.get('pMidIv', 0) or 0),
                    float(row.get('stkPx', 0) or 0),
                    dte,
                    int(float(row.get('cVolu', 0) or 0)),
                    int(float(row.get('pVolu', 0) or 0)),
                    int(float(row.get('cOi', 0) or 0)),
                    int(float(row.get('pOi', 0) or 0))
                )
                batch.append(row_data)
                rows_imported += 1

                if len(batch) >= BATCH_SIZE:
                    cursor.executemany(insert_sql, batch)
                    batch = []

            except Exception:
                continue

    if batch:
        cursor.executemany(insert_sql, batch)

    conn.commit()
    return rows_imported


def main():
    parser = argparse.ArgumentParser(description='Import CSVs to SQLite')
    parser.add_argument('--start', type=str, help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, help='End date (YYYY-MM-DD)')
    args = parser.parse_args()

    start_date = datetime.strptime(args.start, '%Y-%m-%d').date() if args.start else None
    end_date = datetime.strptime(args.end, '%Y-%m-%d').date() if args.end else None

    print("=" * 70)
    print("📥 SQLITE IMPORTER (LOCAL - FAST)")
    print("=" * 70)

    # Create data directory if needed
    SQLITE_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Connect to SQLite
    conn = sqlite3.connect(SQLITE_DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")  # Faster writes
    conn.execute("PRAGMA synchronous=NORMAL")

    # Create tables
    create_tables(conn)

    # Get CSV files
    csv_files = sorted(ORAT_PROCESSED_DIR.glob('orat_spx_*.csv'))

    # Filter by date
    filtered_files = []
    for f in csv_files:
        date_str = f.stem.replace('orat_spx_', '')
        try:
            file_date = datetime.strptime(date_str, '%Y%m%d').date()
            if start_date and file_date < start_date:
                continue
            if end_date and file_date > end_date:
                continue
            filtered_files.append((f, file_date))
        except:
            continue

    print(f"📁 Source: {ORAT_PROCESSED_DIR}")
    print(f"📁 Database: {SQLITE_DB_PATH}")
    print(f"📄 Files to import: {len(filtered_files)}")
    print()

    if not filtered_files:
        print("⚠️ No CSV files found!")
        return

    total_rows = 0

    for idx, (csv_file, file_date) in enumerate(filtered_files, 1):
        date_str = file_date.strftime('%Y-%m-%d')
        print(f"[{idx}/{len(filtered_files)}] {date_str}...", end=" ", flush=True)

        try:
            rows = import_csv_to_sqlite(conn, csv_file)
            total_rows += rows
            print(f"✅ {rows:,} rows")
        except Exception as e:
            print(f"❌ {e}")

    conn.close()

    print()
    print("=" * 70)
    print(f"✅ IMPORT COMPLETE: {total_rows:,} total rows")
    print(f"📁 Database saved to: {SQLITE_DB_PATH}")
    print("=" * 70)


if __name__ == '__main__':
    main()
