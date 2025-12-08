#!/usr/bin/env python3
"""
Import Missing Files - SKIP rows with extreme values

Instead of trying to cap extreme values, this script simply
SKIPS any row that has values outside safe PostgreSQL limits.

Usage:
    python scripts/import_skip_extreme.py --workers 8
"""

import os
import sys
import csv
import argparse
import psycopg2
from datetime import datetime
from pathlib import Path
from io import StringIO
from concurrent.futures import ProcessPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / '.env')

ORAT_PROCESSED_DIR = Path(__file__).parent.parent / 'data' / 'orat_processed'
DATABASE_URL = os.getenv('DATABASE_URL')

# Safe limits for PostgreSQL REAL
MAX_SAFE = 1e30


def is_safe_number(value):
    """Check if value is safe for PostgreSQL REAL"""
    if value is None or value == '' or value == 'None':
        return True, 0.0
    try:
        f = float(value)
        # Check for inf, nan, or extreme values
        if f != f:  # NaN check
            return True, 0.0
        if f == float('inf') or f == float('-inf'):
            return True, 0.0
        if abs(f) > MAX_SAFE:
            return False, f  # SKIP this row
        return True, f
    except:
        return True, 0.0


def get_imported_dates():
    """Get list of dates already imported"""
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT trade_date FROM orat_options_eod")
    dates = set(row[0].strftime('%Y%m%d') for row in cursor.fetchall())
    conn.close()
    return dates


def import_single_file(csv_path_str: str) -> tuple:
    """Import a single CSV file, skipping rows with extreme values"""
    csv_path = Path(csv_path_str)

    try:
        conn = psycopg2.connect(DATABASE_URL)
    except Exception as e:
        return (csv_path.name, 0, 0, f"Connection error: {e}")

    try:
        date_str = csv_path.stem.replace('orat_spx_', '')
        trade_date = datetime.strptime(date_str, '%Y%m%d').date()

        rows_imported = 0
        rows_skipped = 0
        cursor = conn.cursor()

        with open(csv_path, 'r') as f:
            reader = csv.DictReader(f)

            for row in reader:
                # Check ALL numeric fields for extreme values
                fields_to_check = [
                    'strike', 'cBidPx', 'cAskPx', 'pBidPx', 'pAskPx',
                    'delta', 'gamma', 'theta', 'vega', 'rho',
                    'cMidIv', 'pMidIv', 'stkPx'
                ]

                skip_row = False
                for field in fields_to_check:
                    is_safe, _ = is_safe_number(row.get(field, 0))
                    if not is_safe:
                        skip_row = True
                        break

                if skip_row:
                    rows_skipped += 1
                    continue

                # All values are safe - insert the row
                try:
                    exp_date = row.get('expirDate', None) or None
                    yte = float(row.get('yte', 0) or 0)
                    dte = int(yte * 365)

                    _, c_bid = is_safe_number(row.get('cBidPx', 0))
                    _, c_ask = is_safe_number(row.get('cAskPx', 0))
                    _, p_bid = is_safe_number(row.get('pBidPx', 0))
                    _, p_ask = is_safe_number(row.get('pAskPx', 0))
                    _, delta = is_safe_number(row.get('delta', 0))
                    _, gamma = is_safe_number(row.get('gamma', 0))
                    _, theta = is_safe_number(row.get('theta', 0))
                    _, vega = is_safe_number(row.get('vega', 0))
                    _, rho = is_safe_number(row.get('rho', 0))
                    _, c_iv = is_safe_number(row.get('cMidIv', 0))
                    _, p_iv = is_safe_number(row.get('pMidIv', 0))
                    _, stk_px = is_safe_number(row.get('stkPx', 0))
                    _, strike = is_safe_number(row.get('strike', 0))

                    cursor.execute("""
                        INSERT INTO orat_options_eod (
                            trade_date, ticker, expiration_date, strike, option_type,
                            call_bid, call_ask, call_mid, put_bid, put_ask, put_mid,
                            delta, gamma, theta, vega, rho,
                            call_iv, put_iv, underlying_price, dte,
                            call_volume, put_volume, call_oi, put_oi
                        ) VALUES (
                            %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s,
                            %s, %s, %s, %s,
                            %s, %s, %s, %s
                        )
                        ON CONFLICT (trade_date, ticker, expiration_date, strike) DO NOTHING
                    """, (
                        trade_date,
                        row.get('ticker', ''),
                        exp_date,
                        strike,
                        'BOTH',
                        c_bid, c_ask, (c_bid + c_ask) / 2,
                        p_bid, p_ask, (p_bid + p_ask) / 2,
                        delta, gamma, theta, vega, rho,
                        c_iv, p_iv, stk_px, dte,
                        int(float(row.get('cVolu', 0) or 0)),
                        int(float(row.get('pVolu', 0) or 0)),
                        int(float(row.get('cOi', 0) or 0)),
                        int(float(row.get('pOi', 0) or 0))
                    ))
                    rows_imported += 1

                except Exception as e:
                    rows_skipped += 1
                    continue

        conn.commit()
        conn.close()
        return (csv_path.name, rows_imported, rows_skipped, None)

    except Exception as e:
        conn.close()
        return (csv_path.name, 0, 0, str(e))


def main():
    parser = argparse.ArgumentParser(description='Import missing files, skip extreme values')
    parser.add_argument('--workers', type=int, default=8, help='Number of workers')
    args = parser.parse_args()

    print("=" * 70)
    print("IMPORT MISSING FILES - SKIP EXTREME VALUES")
    print("=" * 70)

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

    total_imported = 0
    total_skipped = 0
    success_count = 0
    failed_count = 0

    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(import_single_file, f): f for f in missing_files}

        completed = 0
        for future in as_completed(futures):
            completed += 1
            filename, imported, skipped, error = future.result()

            if error:
                failed_count += 1
                print(f"[{completed}/{len(missing_files)}] {filename}: ERROR - {error[:50]}...")
            else:
                success_count += 1
                total_imported += imported
                total_skipped += skipped
                print(f"[{completed}/{len(missing_files)}] {filename}: {imported:,} rows (skipped {skipped} extreme)")

    print()
    print("=" * 70)
    print(f"IMPORT COMPLETE")
    print(f"  Successful files: {success_count}")
    print(f"  Failed files: {failed_count}")
    print(f"  Rows imported: {total_imported:,}")
    print(f"  Rows skipped (extreme values): {total_skipped:,}")
    print("=" * 70)


if __name__ == '__main__':
    main()
