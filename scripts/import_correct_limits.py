#!/usr/bin/env python3
"""
Import Missing Files with CORRECT DECIMAL Limits

The database uses DECIMAL types, not REAL:
- DECIMAL(10,6) max = 9999.999999
- DECIMAL(10,4) max = 999999.9999
- DECIMAL(10,2) max = 99999999.99

This script caps values to fit the actual DECIMAL limits.

Usage:
    python scripts/import_correct_limits.py --workers 8
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

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / '.env')

ORAT_PROCESSED_DIR = Path(__file__).parent.parent / 'data' / 'orat_processed'
DATABASE_URL = os.getenv('DATABASE_URL')

# CORRECT limits based on DECIMAL types in database schema
DECIMAL_10_6_MAX = 9999.999999      # delta, gamma, rho, call_iv, put_iv
DECIMAL_10_4_MAX = 999999.9999      # theta, vega, prices
DECIMAL_10_2_MAX = 99999999.99      # strike, underlying_price


def cap_decimal_10_6(value):
    """Cap value to fit DECIMAL(10,6): max ±9999.999999"""
    if value is None or value == '' or value == 'None':
        return 0.0
    try:
        f = float(value)
        if math.isnan(f) or math.isinf(f):
            return 0.0
        if f > DECIMAL_10_6_MAX:
            return DECIMAL_10_6_MAX
        if f < -DECIMAL_10_6_MAX:
            return -DECIMAL_10_6_MAX
        return round(f, 6)
    except:
        return 0.0


def cap_decimal_10_4(value):
    """Cap value to fit DECIMAL(10,4): max ±999999.9999"""
    if value is None or value == '' or value == 'None':
        return 0.0
    try:
        f = float(value)
        if math.isnan(f) or math.isinf(f):
            return 0.0
        if f > DECIMAL_10_4_MAX:
            return DECIMAL_10_4_MAX
        if f < -DECIMAL_10_4_MAX:
            return -DECIMAL_10_4_MAX
        return round(f, 4)
    except:
        return 0.0


def cap_decimal_10_2(value):
    """Cap value to fit DECIMAL(10,2): max ±99999999.99"""
    if value is None or value == '' or value == 'None':
        return 0.0
    try:
        f = float(value)
        if math.isnan(f) or math.isinf(f):
            return 0.0
        if f > DECIMAL_10_2_MAX:
            return DECIMAL_10_2_MAX
        if f < -DECIMAL_10_2_MAX:
            return -DECIMAL_10_2_MAX
        return round(f, 2)
    except:
        return 0.0


def safe_int(value):
    """Convert to int safely"""
    if value is None or value == '' or value == 'None':
        return 0
    try:
        f = float(value)
        if math.isnan(f) or math.isinf(f):
            return 0
        return int(f)
    except:
        return 0


def get_imported_dates():
    """Get list of dates already imported"""
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT trade_date FROM orat_options_eod")
    dates = set(row[0].strftime('%Y%m%d') for row in cursor.fetchall())
    conn.close()
    return dates


def import_single_file(csv_path_str: str) -> tuple:
    """Import a single CSV file with correct DECIMAL limits"""
    csv_path = Path(csv_path_str)

    try:
        conn = psycopg2.connect(DATABASE_URL)
    except Exception as e:
        return (csv_path.name, 0, f"Connection error: {e}")

    try:
        date_str = csv_path.stem.replace('orat_spx_', '')
        trade_date = datetime.strptime(date_str, '%Y%m%d').date()

        # Build buffer with CORRECTLY capped values
        buffer = StringIO()
        rows_count = 0

        with open(csv_path, 'r') as f:
            reader = csv.DictReader(f)

            for row in reader:
                try:
                    exp_date = row.get('expirDate', '') or '\\N'
                    yte = cap_decimal_10_4(row.get('yte', 0))
                    dte = safe_int(yte * 365)

                    # Prices - DECIMAL(10,4)
                    c_bid = cap_decimal_10_4(row.get('cBidPx', 0))
                    c_ask = cap_decimal_10_4(row.get('cAskPx', 0))
                    p_bid = cap_decimal_10_4(row.get('pBidPx', 0))
                    p_ask = cap_decimal_10_4(row.get('pAskPx', 0))

                    # Greeks - DECIMAL(10,6) for delta/gamma/rho
                    delta = cap_decimal_10_6(row.get('delta', 0))
                    gamma = cap_decimal_10_6(row.get('gamma', 0))
                    rho = cap_decimal_10_6(row.get('rho', 0))

                    # Greeks - DECIMAL(10,4) for theta/vega
                    theta = cap_decimal_10_4(row.get('theta', 0))
                    vega = cap_decimal_10_4(row.get('vega', 0))

                    # IV - DECIMAL(10,6)
                    c_iv = cap_decimal_10_6(row.get('cMidIv', 0))
                    p_iv = cap_decimal_10_6(row.get('pMidIv', 0))

                    # Strike and underlying - DECIMAL(10,2)
                    strike = cap_decimal_10_2(row.get('strike', 0))
                    stk_px = cap_decimal_10_2(row.get('stkPx', 0))

                    # Tab-separated line
                    line = '\t'.join([
                        str(trade_date),
                        row.get('ticker', ''),
                        exp_date,
                        str(strike),
                        'BOTH',
                        str(c_bid),
                        str(c_ask),
                        str(round((c_bid + c_ask) / 2, 4)),
                        str(p_bid),
                        str(p_ask),
                        str(round((p_bid + p_ask) / 2, 4)),
                        str(delta),
                        str(gamma),
                        str(theta),
                        str(vega),
                        str(rho),
                        str(c_iv),
                        str(p_iv),
                        str(stk_px),
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

        buffer.seek(0)
        cursor = conn.cursor()

        # Create temp table matching exact DECIMAL types
        cursor.execute("""
            CREATE TEMP TABLE temp_import (
                trade_date DATE,
                ticker VARCHAR(10),
                expiration_date TEXT,
                strike DECIMAL(10,2),
                option_type VARCHAR(10),
                call_bid DECIMAL(10,4),
                call_ask DECIMAL(10,4),
                call_mid DECIMAL(10,4),
                put_bid DECIMAL(10,4),
                put_ask DECIMAL(10,4),
                put_mid DECIMAL(10,4),
                delta DECIMAL(10,6),
                gamma DECIMAL(10,6),
                theta DECIMAL(10,4),
                vega DECIMAL(10,4),
                rho DECIMAL(10,6),
                call_iv DECIMAL(10,6),
                put_iv DECIMAL(10,6),
                underlying_price DECIMAL(10,2),
                dte INTEGER,
                call_volume INTEGER,
                put_volume INTEGER,
                call_oi INTEGER,
                put_oi INTEGER
            )
        """)

        # COPY data (now with correctly capped values)
        cursor.copy_from(buffer, 'temp_import', sep='\t', null='\\N')

        # Insert into main table
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
                CASE WHEN expiration_date = '' OR expiration_date = '\\N'
                     THEN NULL ELSE expiration_date::DATE END,
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
    parser = argparse.ArgumentParser(description='Import with correct DECIMAL limits')
    parser.add_argument('--workers', type=int, default=8, help='Number of workers')
    args = parser.parse_args()

    print("=" * 70)
    print("IMPORT WITH CORRECT DECIMAL LIMITS")
    print("=" * 70)
    print("Limits:")
    print(f"  DECIMAL(10,6): ±{DECIMAL_10_6_MAX} (delta, gamma, rho, IV)")
    print(f"  DECIMAL(10,4): ±{DECIMAL_10_4_MAX} (theta, vega, prices)")
    print(f"  DECIMAL(10,2): ±{DECIMAL_10_2_MAX} (strike, underlying)")
    print()

    print("Checking database for imported dates...")
    imported_dates = get_imported_dates()
    print(f"Found {len(imported_dates)} dates already imported")

    csv_files = sorted(ORAT_PROCESSED_DIR.glob('orat_spx_*.csv'))
    print(f"Found {len(csv_files)} total CSV files")

    missing_files = []
    for f in csv_files:
        date_str = f.stem.replace('orat_spx_', '')
        if date_str not in imported_dates:
            missing_files.append(str(f))

    print(f"Missing files to import: {len(missing_files)}")
    print()

    if not missing_files:
        print("All files already imported!")
        return

    total_rows = 0
    success_count = 0
    failed_count = 0
    failed_files = []

    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(import_single_file, f): f for f in missing_files}

        completed = 0
        for future in as_completed(futures):
            completed += 1
            filename, rows, error = future.result()

            if error:
                failed_count += 1
                failed_files.append((filename, error))
                print(f"[{completed}/{len(missing_files)}] {filename}: ERROR - {error[:50]}...")
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
        for fname, err in failed_files[:10]:
            print(f"  - {fname}: {err[:60]}")
    print("=" * 70)


if __name__ == '__main__':
    main()
