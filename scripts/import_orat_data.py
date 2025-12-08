#!/usr/bin/env python3
"""
ORAT SMV Strikes Data Importer

Imports ORAT historical options data for backtesting.
Filters for SPX, SPXW (weekly SPX - includes 0DTE), and SPY only.

Usage:
    # Import all ZIP files in orat_raw folder:
    python scripts/import_orat_data.py

    # Import specific year:
    python scripts/import_orat_data.py --year 2024

    # Import date range:
    python scripts/import_orat_data.py --start 2020-01-01 --end 2024-12-31

Directory Structure:
    data/orat_raw/          <- Put downloaded ZIP files here
    data/orat_processed/    <- Filtered CSVs saved here
"""

import os
import sys
import zipfile
import csv
import argparse
from datetime import datetime, date
from pathlib import Path
from typing import List, Dict, Optional, Generator
import io
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
import multiprocessing

# Add parent directory for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load environment
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / '.env')

# Target tickers for backtesting
TARGET_TICKERS = {'SPX', 'SPXW', 'SPY', 'VIX', '^SPX', '^VIX'}

# We'll also extract underlying prices (stkPx) for these tickers
# This gives us SPX, SPY, and VIX spot prices from ORAT data

# Paths
ORAT_RAW_DIR = Path(__file__).parent.parent / 'data' / 'orat_raw'
ORAT_PROCESSED_DIR = Path(__file__).parent.parent / 'data' / 'orat_processed'


def get_zip_files(directory: Path, year: Optional[int] = None,
                  start_date: Optional[date] = None,
                  end_date: Optional[date] = None) -> List[Path]:
    """Get list of ORAT ZIP files to process"""
    zip_files = []

    for f in sorted(directory.glob('**/*.zip')):
        # Parse date from filename: ORATS_SMV_Strikes_YYYYMMDD.zip
        try:
            filename = f.name
            if 'ORATS_SMV_Strikes_' in filename:
                date_str = filename.replace('ORATS_SMV_Strikes_', '').replace('.zip', '')
                file_date = datetime.strptime(date_str, '%Y%m%d').date()

                # Apply filters
                if year and file_date.year != year:
                    continue
                if start_date and file_date < start_date:
                    continue
                if end_date and file_date > end_date:
                    continue

                zip_files.append(f)
        except (ValueError, IndexError):
            print(f"  ⚠️ Skipping file with unexpected format: {f.name}")
            continue

    return zip_files


def process_zip_file(zip_path: Path, save_filtered: bool = True) -> Dict:
    """
    Process a single ORAT ZIP file.
    Extracts CSV, filters for target tickers, optionally saves filtered version.
    Returns stats about the processing.
    """
    stats = {
        'file': zip_path.name,
        'total_rows': 0,
        'filtered_rows': 0,
        'tickers_found': set(),
        'date': None,
        'success': False,
        'error': None
    }

    try:
        # Parse date from filename
        date_str = zip_path.name.replace('ORATS_SMV_Strikes_', '').replace('.zip', '')
        file_date = datetime.strptime(date_str, '%Y%m%d').date()
        stats['date'] = file_date

        filtered_rows = []
        header = None

        with zipfile.ZipFile(zip_path, 'r') as zf:
            # Find the CSV file inside
            csv_files = [n for n in zf.namelist() if n.endswith('.csv')]
            if not csv_files:
                stats['error'] = 'No CSV file found in ZIP'
                return stats

            csv_filename = csv_files[0]

            with zf.open(csv_filename) as csv_file:
                # Read as text
                text_wrapper = io.TextIOWrapper(csv_file, encoding='utf-8')
                reader = csv.reader(text_wrapper)

                # Get header
                header = next(reader)
                ticker_idx = header.index('ticker') if 'ticker' in header else 0

                for row in reader:
                    stats['total_rows'] += 1

                    if len(row) > ticker_idx:
                        ticker = row[ticker_idx].upper().strip()

                        if ticker in TARGET_TICKERS:
                            filtered_rows.append(row)
                            stats['filtered_rows'] += 1
                            stats['tickers_found'].add(ticker)

        # Save filtered data
        if save_filtered and filtered_rows and header:
            output_path = ORAT_PROCESSED_DIR / f'orat_spx_{date_str}.csv'
            with open(output_path, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(header)
                writer.writerows(filtered_rows)

        stats['success'] = True
        stats['tickers_found'] = list(stats['tickers_found'])

    except Exception as e:
        stats['error'] = str(e)

    return stats


def extract_underlying_prices(csv_path: Path) -> Dict:
    """Extract underlying prices (stkPx) from ORAT data for SPX, SPY, VIX"""
    prices = {}  # {ticker: stkPx}

    try:
        with open(csv_path, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                ticker = row.get('ticker', '').upper().strip()
                stk_px = row.get('stkPx', 0)

                if ticker and stk_px and ticker not in prices:
                    try:
                        prices[ticker] = float(stk_px)
                    except:
                        pass

    except Exception as e:
        print(f"  ⚠️ Error extracting prices: {e}")

    return prices


def save_underlying_prices(trade_date: date, prices: Dict) -> int:
    """Save underlying prices to database"""
    try:
        from database_adapter import get_connection
    except ImportError:
        return 0

    rows_saved = 0

    try:
        conn = get_connection()
        cursor = conn.cursor()

        for ticker, price in prices.items():
            # Map ORAT ticker to standard symbol
            symbol_map = {
                'SPX': 'SPX',
                'SPXW': 'SPX',  # Weekly SPX maps to SPX underlying
                'SPY': 'SPY',
                'VIX': 'VIX',
            }
            symbol = symbol_map.get(ticker, ticker)

            try:
                # Insert into underlying_prices or vix_history
                if symbol == 'VIX':
                    cursor.execute("""
                        INSERT INTO vix_history (trade_date, close, source)
                        VALUES (%s, %s, 'orat')
                        ON CONFLICT (trade_date) DO UPDATE SET close = EXCLUDED.close
                    """, (trade_date, price))
                else:
                    cursor.execute("""
                        INSERT INTO underlying_prices (trade_date, symbol, close, source)
                        VALUES (%s, %s, %s, 'orat')
                        ON CONFLICT (trade_date, symbol) DO UPDATE SET close = EXCLUDED.close
                    """, (trade_date, symbol, price))

                rows_saved += 1

            except Exception as e:
                continue

        conn.commit()
        conn.close()

    except Exception as e:
        print(f"  ⚠️ Error saving prices: {e}")

    return rows_saved


def import_to_database(csv_path: Path) -> int:
    """Import a processed CSV file into the database using batch inserts"""
    try:
        from database_adapter import get_connection
        import psycopg2.extras
    except ImportError:
        print("  ⚠️ Database not available - skipping DB import")
        return 0

    rows_imported = 0
    BATCH_SIZE = 1000  # Insert 1000 rows at a time

    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Parse trade date from filename
        date_str = csv_path.stem.replace('orat_spx_', '')
        trade_date = datetime.strptime(date_str, '%Y%m%d').date()

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

                    # Calculate DTE from yte (years to expiration)
                    yte = float(row.get('yte', 0) or 0)
                    dte = int(yte * 365)

                    # Build row tuple
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

                    # Insert batch when full
                    if len(batch) >= BATCH_SIZE:
                        psycopg2.extras.execute_values(
                            cursor,
                            """INSERT INTO orat_options_eod (
                                trade_date, ticker, expiration_date, strike, option_type,
                                call_bid, call_ask, call_mid, put_bid, put_ask, put_mid,
                                delta, gamma, theta, vega, rho,
                                call_iv, put_iv, underlying_price, dte,
                                call_volume, put_volume, call_oi, put_oi
                            ) VALUES %s
                            ON CONFLICT (trade_date, ticker, expiration_date, strike) DO NOTHING""",
                            batch,
                            page_size=BATCH_SIZE
                        )
                        batch = []

                except Exception as e:
                    continue

        # Insert remaining rows
        if batch:
            psycopg2.extras.execute_values(
                cursor,
                """INSERT INTO orat_options_eod (
                    trade_date, ticker, expiration_date, strike, option_type,
                    call_bid, call_ask, call_mid, put_bid, put_ask, put_mid,
                    delta, gamma, theta, vega, rho,
                    call_iv, put_iv, underlying_price, dte,
                    call_volume, put_volume, call_oi, put_oi
                ) VALUES %s
                ON CONFLICT (trade_date, ticker, expiration_date, strike) DO NOTHING""",
                batch,
                page_size=BATCH_SIZE
            )

        conn.commit()
        conn.close()

    except Exception as e:
        print(f"  ❌ Database error: {e}")

    return rows_imported


def process_single_file(args_tuple):
    """Worker function for parallel processing"""
    zip_file, save_filtered = args_tuple
    return process_zip_file(zip_file, save_filtered)


def main():
    parser = argparse.ArgumentParser(description='Import ORAT SMV Strikes data')
    parser.add_argument('--year', type=int, help='Process only specific year')
    parser.add_argument('--start', type=str, help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, help='End date (YYYY-MM-DD)')
    parser.add_argument('--no-db', action='store_true', help='Skip database import')
    parser.add_argument('--sample', action='store_true', help='Process only first 5 files (for testing)')
    parser.add_argument('--workers', type=int, default=4, help='Number of parallel workers (default: 4)')
    parser.add_argument('--extract-only', action='store_true', help='Only extract/filter CSVs, no DB import')
    args = parser.parse_args()

    # Parse date arguments
    start_date = datetime.strptime(args.start, '%Y-%m-%d').date() if args.start else None
    end_date = datetime.strptime(args.end, '%Y-%m-%d').date() if args.end else None

    print("=" * 70)
    print("📊 ORAT SMV STRIKES DATA IMPORTER (PARALLEL)")
    print("=" * 70)
    print(f"\n📁 Source: {ORAT_RAW_DIR}")
    print(f"📁 Output: {ORAT_PROCESSED_DIR}")
    print(f"🎯 Target tickers: {', '.join(TARGET_TICKERS)}")
    print(f"⚡ Workers: {args.workers}")

    if args.year:
        print(f"📅 Year filter: {args.year}")
    if start_date:
        print(f"📅 Start date: {start_date}")
    if end_date:
        print(f"📅 End date: {end_date}")

    # Ensure directories exist
    ORAT_RAW_DIR.mkdir(parents=True, exist_ok=True)
    ORAT_PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    # Get ZIP files
    zip_files = get_zip_files(ORAT_RAW_DIR, args.year, start_date, end_date)

    if not zip_files:
        print(f"\n⚠️ No ZIP files found in {ORAT_RAW_DIR}")
        print("\n📋 TO GET STARTED:")
        print("   1. Download ORAT ZIP files from FTP")
        print("   2. Place them in: data/orat_raw/")
        print("   3. Run this script again")
        print("\n   Expected filename format: ORATS_SMV_Strikes_YYYYMMDD.zip")
        return

    if args.sample:
        zip_files = zip_files[:5]
        print(f"\n🧪 SAMPLE MODE: Processing first 5 files only")

    print(f"\n📦 Found {len(zip_files)} ZIP files to process")
    print(f"⏱️  Estimated time: ~{len(zip_files) // args.workers // 60 + 1} minutes with {args.workers} workers\n")

    # Process files IN PARALLEL
    total_stats = {
        'files_processed': 0,
        'files_success': 0,
        'files_error': 0,
        'total_rows': 0,
        'filtered_rows': 0,
        'db_rows': 0,
        'price_rows': 0
    }

    # Prepare arguments for workers
    work_items = [(zf, True) for zf in zip_files]

    print("🚀 Starting parallel extraction...")
    results = []

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(process_single_file, item): item[0] for item in work_items}

        for i, future in enumerate(as_completed(futures), 1):
            zip_file = futures[future]
            try:
                stats = future.result()
                results.append(stats)

                total_stats['files_processed'] += 1
                total_stats['total_rows'] += stats['total_rows']
                total_stats['filtered_rows'] += stats['filtered_rows']

                if stats['success']:
                    total_stats['files_success'] += 1
                    tickers = ', '.join(stats['tickers_found']) if stats['tickers_found'] else 'None'
                    print(f"[{i}/{len(zip_files)}] ✅ {zip_file.name} - {stats['filtered_rows']:,} rows ({tickers})")
                else:
                    total_stats['files_error'] += 1
                    print(f"[{i}/{len(zip_files)}] ❌ {zip_file.name} - {stats['error']}")

            except Exception as e:
                total_stats['files_error'] += 1
                print(f"[{i}/{len(zip_files)}] ❌ {zip_file.name} - Worker error: {e}")

    # Database import (sequential for now)
    if not args.no_db and not args.extract_only:
        print("\n📥 Importing to database...")

        # Count files to import
        files_to_import = [s for s in results if s['success'] and s['filtered_rows'] > 0 and s['date']]
        total_files = len(files_to_import)

        for idx, stats in enumerate(files_to_import, 1):
            csv_path = ORAT_PROCESSED_DIR / f"orat_spx_{stats['date'].strftime('%Y%m%d')}.csv"
            if csv_path.exists():
                # Show progress
                date_str = stats['date'].strftime('%Y-%m-%d')
                print(f"  [{idx}/{total_files}] Importing {date_str}...", end=" ", flush=True)

                # Import options data
                db_rows = import_to_database(csv_path)
                total_stats['db_rows'] += db_rows

                # Also extract and save underlying prices
                prices = extract_underlying_prices(csv_path)
                if prices:
                    price_rows = save_underlying_prices(stats['date'], prices)
                    total_stats['price_rows'] += price_rows

                print(f"✅ {db_rows:,} rows")

    # Summary
    print("\n" + "=" * 70)
    print("📊 IMPORT SUMMARY")
    print("=" * 70)
    print(f"  Files processed: {total_stats['files_processed']}")
    print(f"  Files success: {total_stats['files_success']}")
    print(f"  Files with errors: {total_stats['files_error']}")
    print(f"  Total rows scanned: {total_stats['total_rows']:,}")
    print(f"  Filtered rows (SPX/SPXW/SPY/VIX): {total_stats['filtered_rows']:,}")
    if not args.no_db and not args.extract_only:
        print(f"  Options data imported: {total_stats['db_rows']:,}")
        print(f"  Price data imported: {total_stats['price_rows']:,}")
    print("=" * 70)


if __name__ == '__main__':
    main()
