#!/usr/bin/env python3
"""
Check ORAT Database for ML Training Data
=========================================

Checks what historical options data is available in ORAT for training ML models.

Usage:
    export ORAT_DATABASE_URL="postgresql://..."
    python scripts/check_orat_data.py

Or:
    python scripts/check_orat_data.py --url "postgresql://..."
"""

import os
import sys
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    parser = argparse.ArgumentParser(description='Check ORAT Database')
    parser.add_argument('--url', type=str, help='ORAT database URL')
    args = parser.parse_args()

    db_url = args.url or os.getenv('ORAT_DATABASE_URL')
    if not db_url:
        print("ERROR: Set ORAT_DATABASE_URL or use --url")
        sys.exit(1)

    import psycopg2

    print("=" * 70)
    print("ORAT DATABASE - ML TRAINING DATA CHECK")
    print("=" * 70)

    try:
        conn = psycopg2.connect(db_url, connect_timeout=30)
        c = conn.cursor()
        print("Connected successfully!\n")
    except Exception as e:
        print(f"Connection failed: {e}")
        sys.exit(1)

    # List tables
    c.execute("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
        ORDER BY table_name
    """)
    tables = [row[0] for row in c.fetchall()]
    print(f"Tables found: {len(tables)}")
    for t in tables:
        print(f"  - {t}")

    # Check orat_options_eod
    print("\n" + "-" * 70)
    print("OPTIONS DATA (orat_options_eod)")
    print("-" * 70)

    try:
        c.execute("SELECT COUNT(*) FROM orat_options_eod")
        count = c.fetchone()[0]
        print(f"Total records: {count:,}")

        c.execute("SELECT MIN(trade_date), MAX(trade_date) FROM orat_options_eod")
        min_date, max_date = c.fetchone()
        print(f"Date range: {min_date} to {max_date}")

        c.execute("SELECT DISTINCT ticker FROM orat_options_eod ORDER BY ticker")
        symbols = [row[0] for row in c.fetchall()]
        print(f"Symbols: {symbols}")

        print("\nRecords per symbol:")
        for sym in symbols:
            c.execute("""
                SELECT COUNT(*), COUNT(DISTINCT trade_date)
                FROM orat_options_eod WHERE ticker = %s
            """, (sym,))
            rec_count, day_count = c.fetchone()

            # Check if enough for ML training
            status = "✅ READY" if day_count >= 100 else f"⚠️ Need {100-day_count} more days"
            print(f"  {sym}: {rec_count:,} records, {day_count} days - {status}")

    except Exception as e:
        print(f"Error reading orat_options_eod: {e}")

    # Check columns
    print("\n" + "-" * 70)
    print("TABLE COLUMNS")
    print("-" * 70)

    try:
        c.execute("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'orat_options_eod'
            ORDER BY ordinal_position
        """)
        cols = c.fetchall()
        print(f"orat_options_eod has {len(cols)} columns:")
        for col, dtype in cols[:15]:
            print(f"  {col}: {dtype}")
        if len(cols) > 15:
            print(f"  ... and {len(cols) - 15} more")
    except Exception as e:
        print(f"Error: {e}")

    # Summary
    print("\n" + "=" * 70)
    print("ML TRAINING READINESS")
    print("=" * 70)

    if count and count > 0:
        print(f"""
With {count:,} options records from {min_date} to {max_date}, you can:

1. Populate GEX structure data:
   python scripts/populate_gex_structures.py --symbol SPY SPX --start {min_date}

2. Train GEX models:
   python scripts/train_gex_probability_models.py
   python scripts/train_directional_ml.py

3. Train all ready models:
   python scripts/check_ml_training_readiness.py --train-all
""")
    else:
        print("No options data found in orat_options_eod table.")

    conn.close()


if __name__ == "__main__":
    main()
