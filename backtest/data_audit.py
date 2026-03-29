#!/usr/bin/env python3
"""
Data Audit for SPARK/FLAME Backtest
====================================
Run this BEFORE the backtest to verify data availability.

Usage:
    python backtest/data_audit.py
    python backtest/data_audit.py --parquet backtest/data/spy_options.parquet
"""

import os
import sys
import argparse


def audit_orat_db():
    """Step 0A: Check ORAT DB for SPY data."""
    print("=" * 60)
    print("STEP 0A: ORAT DB Audit")
    print("=" * 60)

    try:
        import psycopg2
    except ImportError:
        print("  psycopg2 not installed — skipping ORAT DB check")
        return

    orat_url = os.getenv(
        "ORAT_DATABASE_URL",
        "postgresql://alphagex_user:e5DSVWnKceA16V5ysssLZCbqNE9ELRKi"
        "@dpg-d4quq1u3jp1c739oijb0-a.oregon-postgres.render.com/alphagex_backtest",
    )
    try:
        conn = psycopg2.connect(orat_url, connect_timeout=15)
        cur = conn.cursor()

        cur.execute("""
            SELECT underlying_symbol, COUNT(*), MIN(quote_date), MAX(quote_date)
            FROM orat_options_eod GROUP BY underlying_symbol ORDER BY COUNT(*) DESC;
        """)
        print("ORAT DB contents:")
        for r in cur.fetchall():
            print(f"  {r[0]}: {r[1]:,} rows | {r[2]} -> {r[3]}")

        cur.execute("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'orat_options_eod'
            ORDER BY ordinal_position;
        """)
        print("\norat_options_eod schema:")
        for r in cur.fetchall():
            print(f"  {r[0]}: {r[1]}")

        conn.close()
    except Exception as e:
        print(f"  ORAT DB connection failed: {e}")


def audit_parquet(parquet_path: str):
    """Step 0B + 0C: Audit parquet file schema and DTE availability."""
    print(f"\n{'=' * 60}")
    print(f"STEP 0B: Parquet Audit — {parquet_path}")
    print("=" * 60)

    import pandas as pd

    if not os.path.exists(parquet_path):
        # Try yearly files
        data_dir = os.path.dirname(parquet_path)
        yearly = [
            f for f in os.listdir(data_dir)
            if f.startswith("spy_") and f.endswith(".parquet")
        ] if os.path.isdir(data_dir) else []
        if yearly:
            print(f"  Main parquet not found. Found {len(yearly)} yearly files.")
            for yf in sorted(yearly):
                fp = os.path.join(data_dir, yf)
                sz = os.path.getsize(fp)
                status = "OK" if sz > 500 else f"LFS POINTER ({sz}B)"
                print(f"    {yf}: {sz:,} bytes — {status}")
        else:
            print(f"  ERROR: No data found at {parquet_path}")
        return

    size = os.path.getsize(parquet_path)
    print(f"  File size: {size / 1e6:.1f} MB")

    if size < 500:
        print("  ERROR: File too small — likely an LFS pointer")
        return

    df = pd.read_parquet(parquet_path)
    print(f"\n  Total rows: {len(df):,}")
    print(f"  Columns ({len(df.columns)}): {list(df.columns)}")

    # Step 0C: Column normalization check
    print(f"\n{'=' * 60}")
    print("STEP 0C: Column Normalization Check")
    print("=" * 60)

    from spark_flame_backtest import _build_column_rename_map, REQUIRED_COLUMNS

    rename_map = _build_column_rename_map(list(df.columns))
    if rename_map:
        print(f"  Rename map: {rename_map}")
        df = df.rename(columns=rename_map)
    else:
        print("  No renames needed — columns match standard names")

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        print(f"  MISSING REQUIRED: {missing}")
        print("  GATE FAILED — cannot proceed with backtest")
        return
    print("  All required columns present: OK")

    # Date range and DTE check
    df["date"] = pd.to_datetime(df["date"])
    df["expiration"] = pd.to_datetime(df["expiration"])
    df["dte_calc"] = (df["expiration"] - df["date"]).dt.days

    print(f"\n  Date range: {df['date'].min().date()} -> {df['date'].max().date()}")

    for dte in [1, 2]:
        sub = df[df["dte_calc"] == dte]
        by_year = sub.groupby(sub["date"].dt.year).size()
        print(f"\n  {dte}DTE rows by year:")
        print(by_year.to_string(header=False))

    # Required column checks
    for col in ["bid", "ask", "delta", "implied_volatility", "strike", "type", "expiration"]:
        present = col in df.columns
        print(f"  Column '{col}': {'OK' if present else 'MISSING'}")

    # Sample row
    print(f"\n  Sample row:\n{df.iloc[0].to_string()}")


def main():
    parser = argparse.ArgumentParser(description="Data audit for SPARK/FLAME backtest")
    parser.add_argument(
        "--parquet",
        default="backtest/data/spy_options.parquet",
        help="Path to SPY options parquet",
    )
    args = parser.parse_args()

    audit_orat_db()
    audit_parquet(args.parquet)


if __name__ == "__main__":
    main()
