#!/usr/bin/env python3
"""
Diagnostic script to test CHRONICLES backtest execution and identify failure points.
This script runs a short backtest with debug mode enabled to trace where trades fail.
"""

import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / '.env')

def get_orat_connection():
    """Get connection to ORAT database (uses ORAT_DATABASE_URL or falls back to DATABASE_URL)"""
    import psycopg2
    from urllib.parse import urlparse

    database_url = os.getenv('ORAT_DATABASE_URL') or os.getenv('DATABASE_URL')
    if not database_url:
        raise ValueError("Neither ORAT_DATABASE_URL nor DATABASE_URL is set")

    result = urlparse(database_url)
    return psycopg2.connect(
        host=result.hostname,
        port=result.port or 5432,
        user=result.username,
        password=result.password,
        database=result.path[1:],
        connect_timeout=30
    )


def main():
    print("=" * 70)
    print("CHRONICLES BACKTEST DIAGNOSTIC TEST")
    print("=" * 70)

    # Check environment variables
    print("\n[0] Checking environment variables...")
    orat_url = os.getenv('ORAT_DATABASE_URL')
    db_url = os.getenv('DATABASE_URL')
    print(f"    ORAT_DATABASE_URL: {'✅ Set' if orat_url else '❌ Not set'}")
    print(f"    DATABASE_URL: {'✅ Set' if db_url else '❌ Not set'}")
    if orat_url:
        print(f"    Using: ORAT_DATABASE_URL")
    elif db_url:
        print(f"    Using: DATABASE_URL (fallback)")
    else:
        print(f"    ❌ No database URL configured!")
        print(f"       Set ORAT_DATABASE_URL to your backtester database connection string.")
        return

    # Test 1: Database connection
    print("\n[1] Testing database connection...")
    try:
        conn = get_orat_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM orat_options_eod")
        count = cursor.fetchone()[0]
        print(f"    ✅ Database connected. ORAT rows: {count:,}")

        # Check SPX data specifically
        cursor.execute("""
            SELECT COUNT(*), MIN(trade_date), MAX(trade_date)
            FROM orat_options_eod
            WHERE ticker = 'SPX'
        """)
        row = cursor.fetchone()
        print(f"    ✅ SPX options: {row[0]:,} rows, dates: {row[1]} to {row[2]}")

        # Check if we have 0DTE options
        cursor.execute("""
            SELECT COUNT(*)
            FROM orat_options_eod
            WHERE ticker = 'SPX' AND dte = 0
        """)
        dte0_count = cursor.fetchone()[0]
        print(f"    ✅ SPX 0DTE options: {dte0_count:,} rows")

        # Check if we have put_bid/call_bid data
        cursor.execute("""
            SELECT
                COUNT(*) as total,
                COUNT(put_bid) as has_put_bid,
                COUNT(call_bid) as has_call_bid,
                AVG(put_bid) as avg_put_bid,
                AVG(call_bid) as avg_call_bid
            FROM orat_options_eod
            WHERE ticker = 'SPX' AND dte <= 7
            LIMIT 1000
        """)
        row = cursor.fetchone()
        print(f"    📊 Bid data sample (DTE<=7): {row[1]} put_bids, {row[2]} call_bids")
        print(f"       Avg put_bid: ${row[3]:.2f if row[3] else 0:.2f}, Avg call_bid: ${row[4]:.2f if row[4] else 0:.2f}")

        conn.close()
    except Exception as e:
        print(f"    ❌ Database error: {e}")
        return

    # Test 2: Run a short backtest
    print("\n[2] Running diagnostic backtest (2024-01-01 to 2024-01-31)...")
    try:
        from backtest.zero_dte_hybrid_fixed import HybridFixedBacktester

        backtester = HybridFixedBacktester(
            start_date="2024-01-01",
            end_date="2024-01-31",
            initial_capital=100_000,
            spread_width=10.0,
            sd_multiplier=1.0,
            risk_per_trade_pct=5.0,
            ticker="SPX",
            strategy_type="iron_condor",
        )

        # Run the backtest
        results = backtester.run()

        # Print results
        print("\n" + "-" * 70)
        if results and results.get('trades', {}).get('total', 0) > 0:
            print(f"✅ SUCCESS: {results['trades']['total']} trades executed")
            print(f"   Final equity: ${results['summary']['final_equity']:,.0f}")
            print(f"   Total return: {results['summary']['total_return_pct']:.2f}%")
        else:
            print("❌ FAILED: No trades executed")

        # Print debug stats
        print("\n" + "-" * 70)
        print("Debug Stats Summary:")
        ds = backtester.debug_stats
        sf = ds.get('strategy_failures', {})
        print(f"  Skipped (wrong weekday): {ds.get('skipped_by_trade_day', 0)}")
        print(f"  Skipped (VIX filter): {ds.get('skipped_by_vix_filter', 0)}")
        print(f"  Skipped (tier limit): {ds.get('skipped_by_tier_limit', 0)}")
        print(f"  Skipped (no OHLC): {ds.get('skipped_no_ohlc', 0)}")
        print(f"  Skipped (no options): {ds.get('skipped_no_options', 0)}")
        print(f"  Skipped (strategy failed): {ds.get('skipped_no_strategy', 0)}")
        print(f"  Skipped (bad credit): {ds.get('skipped_bad_credit', 0)}")
        print(f"\nStrategy failure breakdown:")
        for key, val in sf.items():
            if val > 0:
                print(f"  - {key}: {val}")

    except Exception as e:
        import traceback
        print(f"    ❌ Backtest error: {e}")
        traceback.print_exc()

    print("\n" + "=" * 70)
    print("DIAGNOSTIC COMPLETE")
    print("=" * 70)

if __name__ == "__main__":
    main()
