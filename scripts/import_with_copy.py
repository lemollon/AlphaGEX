#!/usr/bin/env python3
"""
Fast PostgreSQL Import using COPY command

Uses PostgreSQL's COPY protocol which is 10-100x faster than INSERT.
Streams data directly to the database.

Usage:
    python scripts/import_with_copy.py --start 2020-01-01 --end 2025-12-31
"""

import os
import sys
import csv
import argparse
from datetime import datetime
from pathlib import Path
from io import StringIO

# Add parent directory for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load environment
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / '.env')

# Paths
ORAT_PROCESSED_DIR = Path(__file__).parent.parent / 'data' / 'orat_processed'


def import_csv_with_copy(csv_path: Path) -> int:
    """Import a single CSV file using PostgreSQL COPY (fastest method)"""
    from database_adapter import get_connection

    # Parse trade date from filename
    date_str = csv_path.stem.replace('orat_spx_', '')
    trade_date = datetime.strptime(date_str, '%Y%m%d').date()

    # Build data buffer for COPY
    buffer = StringIO()
    rows_count = 0

    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)

        for row in reader:
            try:
                exp_date = row.get('expirDate', '') or '\\N'
                yte = float(row.get('yte', 0) or 0)
                dte = int(yte * 365)

                c_bid = float(row.get('cBidPx', 0) or 0)
                c_ask = float(row.get('cAskPx', 0) or 0)
                p_bid = float(row.get('pBidPx', 0) or 0)
                p_ask = float(row.get('pAskPx', 0) or 0)

                # Tab-separated values for COPY
                line = '\t'.join([
                    str(trade_date),
                    row.get('ticker', ''),
                    exp_date,
                    str(float(row.get('strike', 0) or 0)),
                    'BOTH',
                    str(c_bid),
                    str(c_ask),
                    str((c_bid + c_ask) / 2),
                    str(p_bid),
                    str(p_ask),
                    str((p_bid + p_ask) / 2),
                    str(float(row.get('delta', 0) or 0)),
                    str(float(row.get('gamma', 0) or 0)),
                    str(float(row.get('theta', 0) or 0)),
                    str(float(row.get('vega', 0) or 0)),
                    str(float(row.get('rho', 0) or 0)),
                    str(float(row.get('cMidIv', 0) or 0)),
                    str(float(row.get('pMidIv', 0) or 0)),
                    str(float(row.get('stkPx', 0) or 0)),
                    str(dte),
                    str(int(float(row.get('cVolu', 0) or 0))),
                    str(int(float(row.get('pVolu', 0) or 0))),
                    str(int(float(row.get('cOi', 0) or 0))),
                    str(int(float(row.get('pOi', 0) or 0)))
                ])
                buffer.write(line + '\n')
                rows_count += 1

            except Exception:
                continue

    # Use COPY to load data
    buffer.seek(0)

    conn = get_connection()
    cursor = conn.cursor()

    # Create temp table, COPY into it, then INSERT with conflict handling
    cursor.execute("""
        CREATE TEMP TABLE temp_import (
            trade_date DATE,
            ticker TEXT,
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

    # COPY data into temp table (very fast)
    cursor.copy_from(buffer, 'temp_import', sep='\t', null='\\N')

    # Insert from temp to real table with conflict handling
    cursor.execute("""
        INSERT INTO orat_options_eod (
            trade_date, ticker, expiration_date, strike, option_type,
            call_bid, call_ask, call_mid, put_bid, put_ask, put_mid,
            delta, gamma, theta, vega, rho,
            call_iv, put_iv, underlying_price, dte,
            call_volume, put_volume, call_oi, put_oi
        )
        SELECT
            trade_date, ticker,
            CASE WHEN expiration_date = '' THEN NULL ELSE expiration_date::DATE END,
            strike, option_type,
            call_bid, call_ask, call_mid, put_bid, put_ask, put_mid,
            delta, gamma, theta, vega, rho,
            call_iv, put_iv, underlying_price, dte,
            call_volume, put_volume, call_oi, put_oi
        FROM temp_import
        ON CONFLICT (trade_date, ticker, expiration_date, strike) DO NOTHING
    """)

    cursor.execute("DROP TABLE temp_import")
    conn.commit()
    conn.close()

    return rows_count


def main():
    parser = argparse.ArgumentParser(description='Import CSVs using PostgreSQL COPY')
    parser.add_argument('--start', type=str, help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, help='End date (YYYY-MM-DD)')
    args = parser.parse_args()

    start_date = datetime.strptime(args.start, '%Y-%m-%d').date() if args.start else None
    end_date = datetime.strptime(args.end, '%Y-%m-%d').date() if args.end else None

    print("=" * 70)
    print("📥 POSTGRESQL COPY IMPORTER (FASTEST)")
    print("=" * 70)

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
            rows = import_csv_with_copy(csv_file)
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
