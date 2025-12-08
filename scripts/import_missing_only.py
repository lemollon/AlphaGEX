#!/usr/bin/env python3
"""
Import ONLY Missing Files - Skips already imported dates

Checks which dates are already in the database and only imports
the files that are missing.

Usage:
    python scripts/import_missing_only.py --workers 8
"""

import os
import sys
import csv
import argparse
import psycopg2
import math
from datetime import datetime
from pathlib import Path
from io import StringIO
from concurrent.futures import ProcessPoolExecutor, as_completed

# Add parent directory for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load environment
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / '.env')

# PostgreSQL REAL limits
REAL_MAX = 3.4e38
REAL_MIN = -3.4e38

# Paths
ORAT_PROCESSED_DIR = Path(__file__).parent.parent / 'data' / 'orat_processed'

# Get DATABASE_URL at module level for workers
DATABASE_URL = os.getenv('DATABASE_URL')


def get_imported_dates():
    """Get list of dates already imported to database"""
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT DISTINCT trade_date
        FROM orat_options_eod
        ORDER BY trade_date
    """)

    dates = set(row[0].strftime('%Y%m%d') for row in cursor.fetchall())
    conn.close()

    return dates


def safe_float(value, default=0.0):
    """Convert value to float with bounds checking."""
    if value is None or value == '' or value == 'None':
        return default
    try:
        f = float(value)
        if math.isnan(f) or math.isinf(f):
            return default
        if f > REAL_MAX:
            return REAL_MAX
        if f < REAL_MIN:
            return REAL_MIN
        return f
    except (ValueError, TypeError):
        return default


def safe_int(value, default=0):
    """Convert value to int safely"""
    if value is None or value == '' or value == 'None':
        return default
    try:
        f = float(value)
        if math.isnan(f) or math.isinf(f):
            return default
        return int(f)
    except (ValueError, TypeError):
        return default


def import_single_file(csv_path_str: str) -> tuple:
    """
    Import a single CSV file. Designed to run in a separate process.
    Returns (filename, rows_count, error_or_none)
    """
    csv_path = Path(csv_path_str)

    # Each worker needs its own connection
    try:
        conn = psycopg2.connect(DATABASE_URL)
    except Exception as e:
        return (csv_path.name, 0, f"Connection error: {e}")

    try:
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
                    yte = safe_float(row.get('yte', 0))
                    dte = safe_int(yte * 365)

                    c_bid = safe_float(row.get('cBidPx', 0))
                    c_ask = safe_float(row.get('cAskPx', 0))
                    p_bid = safe_float(row.get('pBidPx', 0))
                    p_ask = safe_float(row.get('pAskPx', 0))

                    # Tab-separated values for COPY
                    line = '\t'.join([
                        str(trade_date),
                        row.get('ticker', ''),
                        exp_date,
                        str(safe_float(row.get('strike', 0))),
                        'BOTH',
                        str(c_bid),
                        str(c_ask),
                        str((c_bid + c_ask) / 2),
                        str(p_bid),
                        str(p_ask),
                        str((p_bid + p_ask) / 2),
                        str(safe_float(row.get('delta', 0))),
                        str(safe_float(row.get('gamma', 0))),
                        str(safe_float(row.get('theta', 0))),
                        str(safe_float(row.get('vega', 0))),
                        str(safe_float(row.get('rho', 0))),
                        str(safe_float(row.get('cMidIv', 0))),
                        str(safe_float(row.get('pMidIv', 0))),
                        str(safe_float(row.get('stkPx', 0))),
                        str(dte),
                        str(safe_int(row.get('cVolu', 0))),
                        str(safe_int(row.get('pVolu', 0))),
                        str(safe_int(row.get('cOi', 0))),
                        str(safe_int(row.get('pOi', 0)))
                    ])
                    buffer.write(line + '\n')
                    rows_count += 1

                except Exception:
                    continue

        if rows_count == 0:
            conn.close()
            return (csv_path.name, 0, "No valid rows")

        # Use COPY to load data
        buffer.seek(0)
        cursor = conn.cursor()

        # Create temp table
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

        # COPY data into temp table
        cursor.copy_from(buffer, 'temp_import', sep='\t', null='\\N')

        # Insert with conflict handling
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

        return (csv_path.name, rows_count, None)

    except Exception as e:
        conn.close()
        return (csv_path.name, 0, str(e))


def main():
    parser = argparse.ArgumentParser(description='Import only missing files')
    parser.add_argument('--workers', type=int, default=8, help='Number of parallel workers (default: 8)')
    args = parser.parse_args()

    print("=" * 70)
    print("IMPORT MISSING FILES ONLY")
    print("=" * 70)

    # Get dates already in database
    print("Checking database for already imported dates...")
    imported_dates = get_imported_dates()
    print(f"Found {len(imported_dates)} dates already imported")

    # Get all CSV files
    csv_files = sorted(ORAT_PROCESSED_DIR.glob('orat_spx_*.csv'))
    print(f"Found {len(csv_files)} total CSV files")

    # Find missing files
    missing_files = []
    for f in csv_files:
        date_str = f.stem.replace('orat_spx_', '')
        if date_str not in imported_dates:
            missing_files.append(str(f))

    print(f"Missing files to import: {len(missing_files)}")
    print()

    if not missing_files:
        print("All files already imported! Nothing to do.")
        return

    # Show which dates are missing
    print("Missing dates:")
    for f in missing_files[:10]:
        date_str = Path(f).stem.replace('orat_spx_', '')
        print(f"  - {date_str[:4]}-{date_str[4:6]}-{date_str[6:]}")
    if len(missing_files) > 10:
        print(f"  ... and {len(missing_files) - 10} more")
    print()

    total_rows = 0
    success_count = 0
    failed_count = 0
    failed_files = []

    # Use ProcessPoolExecutor for true parallelism
    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(import_single_file, f): f for f in missing_files}

        completed = 0
        for future in as_completed(futures):
            completed += 1
            filename, rows, error = future.result()

            if error:
                failed_count += 1
                failed_files.append((filename, error))
                print(f"[{completed}/{len(missing_files)}] {filename}: ERROR - {error[:40]}...")
            else:
                success_count += 1
                total_rows += rows
                print(f"[{completed}/{len(missing_files)}] {filename}: {rows:,} rows")

    print()
    print("=" * 70)
    print(f"IMPORT COMPLETE")
    print(f"  Successful: {success_count} files, {total_rows:,} rows")
    print(f"  Failed: {failed_count} files")
    if failed_files:
        print(f"\nFailed files:")
        for fname, err in failed_files:
            print(f"  - {fname}: {err[:60]}")
    print("=" * 70)


if __name__ == '__main__':
    main()
