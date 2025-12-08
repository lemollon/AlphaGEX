#!/usr/bin/env python3
"""
Fast CSV-to-Database Importer

Imports already-processed CSV files directly to database.
Skips ZIP extraction entirely - use when CSVs are already created.

Usage:
    python scripts/import_csvs_to_db.py
"""

import os
import sys
import csv
import argparse
from datetime import datetime
from pathlib import Path

# Add parent directory for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load environment
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / '.env')

# Paths
ORAT_PROCESSED_DIR = Path(__file__).parent.parent / 'data' / 'orat_processed'


def import_csv_to_db(csv_path: Path) -> int:
    """Import a single CSV file to database with batch inserts"""
    from database_adapter import get_connection

    rows_imported = 0
    BATCH_SIZE = 1000

    conn = get_connection()
    cursor = conn.cursor()

    # Parse trade date from filename
    date_str = csv_path.stem.replace('orat_spx_', '')
    trade_date = datetime.strptime(date_str, '%Y%m%d').date()

    insert_sql = """
        INSERT INTO orat_options_eod (
            trade_date, ticker, expiration_date, strike, option_type,
            call_bid, call_ask, call_mid, put_bid, put_ask, put_mid,
            delta, gamma, theta, vega, rho,
            call_iv, put_iv, underlying_price, dte,
            call_volume, put_volume, call_oi, put_oi
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
        ON CONFLICT (trade_date, ticker, expiration_date, strike) DO NOTHING
    """

    batch = []

    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)

        for row in reader:
            try:
                # Parse expiration date
                exp_date = row.get('expirDate', '')
                if exp_date:
                    try:
                        exp_date = datetime.strptime(exp_date, '%Y-%m-%d').date()
                    except:
                        exp_date = None

                # Calculate DTE
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
                    conn.commit()
                    batch = []

            except Exception:
                continue

    # Insert remaining
    if batch:
        cursor.executemany(insert_sql, batch)
        conn.commit()

    conn.close()
    return rows_imported


def main():
    parser = argparse.ArgumentParser(description='Import CSVs to database')
    parser.add_argument('--start', type=str, help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, help='End date (YYYY-MM-DD)')
    args = parser.parse_args()

    start_date = datetime.strptime(args.start, '%Y-%m-%d').date() if args.start else None
    end_date = datetime.strptime(args.end, '%Y-%m-%d').date() if args.end else None

    print("=" * 70)
    print("📥 CSV TO DATABASE IMPORTER")
    print("=" * 70)

    # Get all CSV files
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
            rows = import_csv_to_db(csv_file)
            total_rows += rows
            print(f"✅ {rows:,} rows")
        except Exception as e:
            print(f"❌ {e}")

    print()
    print("=" * 70)
    print(f"✅ IMPORT COMPLETE: {total_rows:,} total rows")
    print("=" * 70)


if __name__ == '__main__':
    main()
