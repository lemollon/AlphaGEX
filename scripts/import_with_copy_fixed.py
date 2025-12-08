#!/usr/bin/env python3
"""
Fixed PostgreSQL Import using COPY command

Handles numeric overflow errors by:
1. Capping extreme values (e.g., gamma=1.0e+183) to PostgreSQL REAL limits
2. Logging problematic rows for debugging
3. Retry logic for failed files

PostgreSQL REAL type: approximately +-3.4e38

Usage:
    python scripts/import_with_copy_fixed.py --start 2020-01-01 --end 2025-12-31
    python scripts/import_with_copy_fixed.py --retry-failed
"""

import os
import sys
import csv
import argparse
import psycopg2
import json
from datetime import datetime
from pathlib import Path
from io import StringIO
import math

# Add parent directory for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load environment
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / '.env')


# PostgreSQL REAL limits (approximately)
REAL_MAX = 3.4e38
REAL_MIN = -3.4e38

# Paths
ORAT_PROCESSED_DIR = Path(__file__).parent.parent / 'data' / 'orat_processed'
FAILED_FILES_LOG = Path(__file__).parent.parent / 'data' / 'failed_imports.json'


def get_raw_connection():
    """Get raw psycopg2 connection (not wrapped)"""
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        raise Exception("DATABASE_URL not set")
    conn = psycopg2.connect(database_url)
    return conn


def safe_float(value, default=0.0, max_val=REAL_MAX, min_val=REAL_MIN):
    """
    Convert value to float with bounds checking.
    Caps extreme values to PostgreSQL REAL limits.
    """
    if value is None or value == '' or value == 'None':
        return default

    try:
        f = float(value)

        # Handle NaN and Inf
        if math.isnan(f) or math.isinf(f):
            return default

        # Cap to PostgreSQL REAL limits
        if f > max_val:
            return max_val
        if f < min_val:
            return min_val

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


def import_csv_with_copy_fixed(csv_path: Path) -> tuple:
    """
    Import a single CSV file using PostgreSQL COPY (fastest method).
    Returns (rows_count, error_message or None)
    """
    # Parse trade date from filename
    date_str = csv_path.stem.replace('orat_spx_', '')
    trade_date = datetime.strptime(date_str, '%Y%m%d').date()

    # Build data buffer for COPY
    buffer = StringIO()
    rows_count = 0
    skipped_rows = 0
    extreme_values_found = []

    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)

        for row_num, row in enumerate(reader, 1):
            try:
                exp_date = row.get('expirDate', '') or '\\N'
                yte = safe_float(row.get('yte', 0))
                dte = safe_int(yte * 365)

                c_bid = safe_float(row.get('cBidPx', 0))
                c_ask = safe_float(row.get('cAskPx', 0))
                p_bid = safe_float(row.get('pBidPx', 0))
                p_ask = safe_float(row.get('pAskPx', 0))

                # Handle Greeks with extra care (these often have extreme values)
                delta = safe_float(row.get('delta', 0))
                gamma = safe_float(row.get('gamma', 0))
                theta = safe_float(row.get('theta', 0))
                vega = safe_float(row.get('vega', 0))
                rho = safe_float(row.get('rho', 0))

                # Log if we capped extreme values
                raw_gamma = row.get('gamma', '')
                raw_delta = row.get('delta', '')
                if raw_gamma and abs(safe_float(raw_gamma, check_extreme=False)) > REAL_MAX:
                    extreme_values_found.append(f"row {row_num}: gamma={raw_gamma}")
                if raw_delta and abs(safe_float(raw_delta, check_extreme=False)) > REAL_MAX:
                    extreme_values_found.append(f"row {row_num}: delta={raw_delta}")

                # IV values
                c_iv = safe_float(row.get('cMidIv', 0))
                p_iv = safe_float(row.get('pMidIv', 0))

                # Underlying price
                stk_px = safe_float(row.get('stkPx', 0))

                # Volume and OI
                c_volu = safe_int(row.get('cVolu', 0))
                p_volu = safe_int(row.get('pVolu', 0))
                c_oi = safe_int(row.get('cOi', 0))
                p_oi = safe_int(row.get('pOi', 0))

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
                    str(delta),
                    str(gamma),
                    str(theta),
                    str(vega),
                    str(rho),
                    str(c_iv),
                    str(p_iv),
                    str(stk_px),
                    str(dte),
                    str(c_volu),
                    str(p_volu),
                    str(c_oi),
                    str(p_oi)
                ])
                buffer.write(line + '\n')
                rows_count += 1

            except Exception as e:
                skipped_rows += 1
                continue

    if rows_count == 0:
        return 0, f"No valid rows found (skipped {skipped_rows})"

    # Use COPY to load data
    buffer.seek(0)

    try:
        conn = get_raw_connection()
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

        return rows_count, None

    except Exception as e:
        return 0, str(e)


def safe_float_check_extreme(value, default=0.0):
    """Check if value is extreme without capping (for logging)"""
    if value is None or value == '' or value == 'None':
        return default
    try:
        return float(value)
    except:
        return default


# Alias for backward compatibility
def safe_float(value, default=0.0, max_val=REAL_MAX, min_val=REAL_MIN, check_extreme=True):
    """
    Convert value to float with bounds checking.
    Caps extreme values to PostgreSQL REAL limits.
    """
    if value is None or value == '' or value == 'None':
        return default

    try:
        f = float(value)

        # Handle NaN and Inf
        if math.isnan(f) or math.isinf(f):
            return default

        if not check_extreme:
            return f

        # Cap to PostgreSQL REAL limits
        if f > max_val:
            return max_val
        if f < min_val:
            return min_val

        return f
    except (ValueError, TypeError):
        return default


def load_failed_files():
    """Load list of previously failed files"""
    if FAILED_FILES_LOG.exists():
        with open(FAILED_FILES_LOG, 'r') as f:
            return json.load(f)
    return {}


def save_failed_files(failed: dict):
    """Save list of failed files"""
    FAILED_FILES_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(FAILED_FILES_LOG, 'w') as f:
        json.dump(failed, f, indent=2)


def main():
    parser = argparse.ArgumentParser(description='Import CSVs using PostgreSQL COPY (fixed)')
    parser.add_argument('--start', type=str, help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, help='End date (YYYY-MM-DD)')
    parser.add_argument('--retry-failed', action='store_true', help='Retry previously failed files')
    args = parser.parse_args()

    print("=" * 70)
    print("POSTGRESQL COPY IMPORTER (FIXED - HANDLES EXTREME VALUES)")
    print("=" * 70)

    # Load previous failures
    failed_files = load_failed_files()

    if args.retry_failed:
        print(f"Retrying {len(failed_files)} previously failed files...")
        files_to_import = []
        for filename, error in failed_files.items():
            filepath = ORAT_PROCESSED_DIR / filename
            if filepath.exists():
                date_str = filename.replace('orat_spx_', '').replace('.csv', '')
                try:
                    file_date = datetime.strptime(date_str, '%Y%m%d').date()
                    files_to_import.append((filepath, file_date))
                except:
                    continue
        filtered_files = files_to_import
    else:
        start_date = datetime.strptime(args.start, '%Y-%m-%d').date() if args.start else None
        end_date = datetime.strptime(args.end, '%Y-%m-%d').date() if args.end else None

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

    print(f"Source: {ORAT_PROCESSED_DIR}")
    print(f"Files to import: {len(filtered_files)}")
    print()

    if not filtered_files:
        print("No CSV files found!")
        return

    total_rows = 0
    success_count = 0
    failed_count = 0
    new_failures = {}

    for idx, (csv_file, file_date) in enumerate(filtered_files, 1):
        date_str = file_date.strftime('%Y-%m-%d')
        print(f"[{idx}/{len(filtered_files)}] {date_str}...", end=" ", flush=True)

        try:
            rows, error = import_csv_with_copy_fixed(csv_file)

            if error:
                print(f"ERROR: {error[:50]}...")
                failed_count += 1
                new_failures[csv_file.name] = error
            else:
                total_rows += rows
                success_count += 1
                print(f"{rows:,} rows")

                # Remove from failed list if it was there
                if csv_file.name in failed_files:
                    del failed_files[csv_file.name]

        except Exception as e:
            print(f"EXCEPTION: {str(e)[:50]}...")
            failed_count += 1
            new_failures[csv_file.name] = str(e)

    # Update failed files log
    failed_files.update(new_failures)
    save_failed_files(failed_files)

    print()
    print("=" * 70)
    print(f"IMPORT COMPLETE")
    print(f"  Successful: {success_count} files, {total_rows:,} rows")
    print(f"  Failed: {failed_count} files")
    if failed_count > 0:
        print(f"  Failed files logged to: {FAILED_FILES_LOG}")
    print("=" * 70)


if __name__ == '__main__':
    main()
