#!/usr/bin/env python3
"""
Run Full Historical Data Backfill - 5 Years Maximum

This script runs the maximum backfill for all your Polygon subscriptions:
- Stocks (SPY): 5 years (1825 days) - Stocks Starter plan
- Options: 2 years (730 days) - Options Starter plan
- Indices: 1+ year (365 days) - Indices Starter plan

Run this on Render after deployment to populate PostgreSQL with historical data.
On local, it will use SQLite.

Usage:
    python run_full_backfill.py
"""

import sys
import subprocess
from datetime import datetime


def run_backfill(symbol: str, days: int, description: str):
    """Run backfill for a specific symbol"""
    print("\n" + "="*70)
    print(f"Backfilling {description}")
    print(f"Symbol: {symbol}, Days: {days}")
    print("="*70 + "\n")

    try:
        result = subprocess.run(
            ['python3', 'backfill_historical_data.py',
             '--symbol', symbol,
             '--days', str(days)],
            check=True,
            capture_output=False,
            text=True
        )
        print(f"\n✅ {description} backfill completed successfully!")
        return True
    except subprocess.CalledProcessError as e:
        print(f"\n❌ {description} backfill failed: {e}")
        return False


def main():
    """Run complete backfill for all subscriptions"""
    start_time = datetime.now()

    print("\n" + "="*70)
    print("🚀 FULL HISTORICAL DATA BACKFILL")
    print("="*70)
    print("Maximizing your Polygon subscriptions:")
    print("  • SPY (Stocks Starter): 5 years = 1825 days")
    print("  • Options: Available but not currently tracked")
    print("  • Indices: Available but not currently tracked")
    print("="*70)
    print(f"Start time: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70 + "\n")

    success = True

    # Backfill SPY with maximum 5 years of data
    if not run_backfill('SPY', 1825, 'SPY - 5 Years of Stock Data'):
        success = False

    # TODO: Add QQQ, IWM, and other major symbols if needed
    # if not run_backfill('QQQ', 1825, 'QQQ - 5 Years of Stock Data'):
    #     success = False

    end_time = datetime.now()
    duration = end_time - start_time

    print("\n" + "="*70)
    if success:
        print("✅ FULL BACKFILL COMPLETE!")
    else:
        print("⚠️  BACKFILL COMPLETED WITH ERRORS")
    print("="*70)
    print(f"End time: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Duration: {duration}")
    print("="*70 + "\n")

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
