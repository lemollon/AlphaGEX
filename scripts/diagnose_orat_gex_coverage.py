#!/usr/bin/env python3
"""
ORAT GEX Data Coverage Diagnostic Tool
=======================================
Analyzes ORAT data to determine why GEX calculations might fail.

This helps answer:
1. Is it a MISSING DATA issue (no records for certain dates)?
2. Is it a DATA QUALITY issue (records exist but gamma is NULL/0)?

Usage:
    python scripts/diagnose_orat_gex_coverage.py
    python scripts/diagnose_orat_gex_coverage.py --ticker SPY
    python scripts/diagnose_orat_gex_coverage.py --start 2024-01-01 --end 2024-12-31
"""

import os
import sys
import argparse
from datetime import datetime, timedelta

# Add parent directory for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()


def get_connection():
    """Get database connection using ORAT_DATABASE_URL or DATABASE_URL"""
    import psycopg2

    database_url = os.getenv('ORAT_DATABASE_URL') or os.getenv('DATABASE_URL')
    if not database_url:
        raise ValueError("DATABASE_URL not set")

    return psycopg2.connect(database_url)


def analyze_orat_coverage(ticker: str = 'SPY', start_date: str = None, end_date: str = None):
    """Analyze ORAT data coverage and quality"""

    conn = get_connection()
    cur = conn.cursor()

    print("=" * 70)
    print("ORAT GEX DATA COVERAGE DIAGNOSTIC")
    print("=" * 70)
    print(f"\nTicker: {ticker}")

    # 1. Overall date range
    print("\n[1/7] Querying date range...", end=" ", flush=True)
    cur.execute("""
        SELECT
            MIN(trade_date) as first_date,
            MAX(trade_date) as last_date,
            COUNT(DISTINCT trade_date) as total_days,
            COUNT(*) as total_rows
        FROM orat_options_eod
        WHERE ticker = %s
    """, (ticker,))
    result = cur.fetchone()
    print("✓")

    if not result or not result[0]:
        print(f"\n❌ NO DATA FOUND for ticker {ticker}")
        conn.close()
        return

    first_date, last_date, total_days, total_rows = result
    print(f"\n📅 Date Range: {first_date} to {last_date}")
    print(f"📊 Total Trading Days: {total_days}")
    print(f"📈 Total Option Rows: {total_rows:,}")

    # Apply date filters if provided
    date_filter = ""
    params = [ticker]
    if start_date:
        date_filter += " AND trade_date >= %s"
        params.append(start_date)
    if end_date:
        date_filter += " AND trade_date <= %s"
        params.append(end_date)

    # 2. GEX-eligible data analysis
    print("\n" + "-" * 70)
    print("GEX CALCULATION REQUIREMENTS ANALYSIS")
    print("-" * 70)
    print("\nGEX requires: gamma IS NOT NULL AND gamma > 0 AND (call_oi > 0 OR put_oi > 0)")
    print("             AND dte <= 7 (for 0DTE/weekly options)")

    # Days with ANY data
    print("\n[2/7] Counting days with any data...", end=" ", flush=True)
    cur.execute(f"""
        SELECT COUNT(DISTINCT trade_date)
        FROM orat_options_eod
        WHERE ticker = %s {date_filter}
    """, params)
    days_with_any_data = cur.fetchone()[0]
    print("✓")

    # Days with gamma data (non-NULL)
    print("[3/7] Counting days with gamma NOT NULL...", end=" ", flush=True)
    cur.execute(f"""
        SELECT COUNT(DISTINCT trade_date)
        FROM orat_options_eod
        WHERE ticker = %s
          AND gamma IS NOT NULL
          {date_filter}
    """, params)
    days_with_gamma_not_null = cur.fetchone()[0]
    print("✓")

    # Days with gamma > 0
    print("[4/7] Counting days with gamma > 0...", end=" ", flush=True)
    cur.execute(f"""
        SELECT COUNT(DISTINCT trade_date)
        FROM orat_options_eod
        WHERE ticker = %s
          AND gamma IS NOT NULL
          AND gamma > 0
          {date_filter}
    """, params)
    days_with_gamma_positive = cur.fetchone()[0]
    print("✓")

    # Days with OI data
    print("[5/7] Counting days with OI data...", end=" ", flush=True)
    cur.execute(f"""
        SELECT COUNT(DISTINCT trade_date)
        FROM orat_options_eod
        WHERE ticker = %s
          AND (call_oi > 0 OR put_oi > 0)
          {date_filter}
    """, params)
    days_with_oi = cur.fetchone()[0]
    print("✓")

    # Days with FULL GEX eligibility (all requirements met)
    print("[6/7] Counting GEX-eligible days (all requirements)...", end=" ", flush=True)
    cur.execute(f"""
        SELECT COUNT(DISTINCT trade_date)
        FROM orat_options_eod
        WHERE ticker = %s
          AND gamma IS NOT NULL
          AND gamma > 0
          AND (call_oi > 0 OR put_oi > 0)
          AND dte <= 7
          {date_filter}
    """, params)
    days_gex_eligible = cur.fetchone()[0]
    print("✓")

    print("\n" + "=" * 70)
    print("RESULTS")
    print("=" * 70)
    print(f"\n{'Metric':<45} {'Count':>8} {'%':>8}")
    print("-" * 65)
    print(f"{'Days with ANY ORAT data':<45} {days_with_any_data:>8}")
    print(f"{'Days with gamma IS NOT NULL':<45} {days_with_gamma_not_null:>8} {(days_with_gamma_not_null/days_with_any_data*100) if days_with_any_data else 0:>7.1f}%")
    print(f"{'Days with gamma > 0':<45} {days_with_gamma_positive:>8} {(days_with_gamma_positive/days_with_any_data*100) if days_with_any_data else 0:>7.1f}%")
    print(f"{'Days with OI data':<45} {days_with_oi:>8} {(days_with_oi/days_with_any_data*100) if days_with_any_data else 0:>7.1f}%")
    print(f"{'Days GEX-ELIGIBLE (all requirements + dte<=7)':<45} {days_gex_eligible:>8} {(days_gex_eligible/days_with_any_data*100) if days_with_any_data else 0:>7.1f}%")

    # 3. Identify the ISSUE
    print("\n" + "-" * 70)
    print("DIAGNOSIS")
    print("-" * 70)

    missing_gamma_pct = 100 - (days_with_gamma_positive/days_with_any_data*100) if days_with_any_data else 100

    if days_gex_eligible == days_with_any_data:
        print("\n✅ GOOD: All days have GEX-eligible data!")
    elif days_with_gamma_positive < days_with_any_data * 0.9:
        print(f"\n⚠️  DATA QUALITY ISSUE: {missing_gamma_pct:.1f}% of days have missing/zero gamma")
        print("    This is likely an ORAT data quality issue.")
        print("    ORAT may not calculate gamma for all contracts or all dates.")
    elif days_gex_eligible < days_with_gamma_positive:
        print(f"\n⚠️  DTE FILTER ISSUE: Days have gamma but no 0-7 DTE options")
        print("    GEX calculation only uses dte <= 7 (weekly/0DTE options)")

    # 4. Monthly breakdown
    print("\n" + "-" * 70)
    print("[7/7] Querying monthly breakdown (this may take a moment)...", end=" ", flush=True)

    cur.execute(f"""
        SELECT
            DATE_TRUNC('month', trade_date)::date as month,
            COUNT(DISTINCT trade_date) as total_days,
            COUNT(DISTINCT CASE WHEN gamma IS NOT NULL AND gamma > 0 THEN trade_date END) as gamma_days,
            COUNT(DISTINCT CASE
                WHEN gamma IS NOT NULL AND gamma > 0
                AND (call_oi > 0 OR put_oi > 0)
                AND dte <= 7
                THEN trade_date
            END) as gex_eligible_days
        FROM orat_options_eod
        WHERE ticker = %s {date_filter}
        GROUP BY DATE_TRUNC('month', trade_date)
        ORDER BY month DESC
        LIMIT 12
    """, params)
    print("✓")

    print("\n" + "-" * 70)
    print("MONTHLY BREAKDOWN (Recent 12 months)")
    print("-" * 70)
    print(f"\n{'Month':<12} {'Total':<8} {'w/Gamma':<10} {'GEX OK':<10} {'Coverage':<10}")
    print("-" * 55)

    for row in cur.fetchall():
        month = row[0].strftime('%Y-%m')
        total = row[1]
        gamma = row[2]
        gex_ok = row[3]
        pct = (gex_ok/total*100) if total > 0 else 0
        status = "✅" if pct >= 90 else "⚠️" if pct >= 50 else "❌"
        print(f"{month:<12} {total:<8} {gamma:<10} {gex_ok:<10} {pct:>5.0f}% {status}")

    # 5. Sample of problematic dates
    print("\n" + "-" * 70)
    print("SAMPLE PROBLEM DATES (last 10 dates with no GEX eligibility)")
    print("-" * 70)

    cur.execute(f"""
        WITH all_dates AS (
            SELECT DISTINCT trade_date FROM orat_options_eod
            WHERE ticker = %s {date_filter}
        ),
        gex_dates AS (
            SELECT DISTINCT trade_date FROM orat_options_eod
            WHERE ticker = %s
              AND gamma IS NOT NULL AND gamma > 0
              AND (call_oi > 0 OR put_oi > 0) AND dte <= 7
              {date_filter}
        )
        SELECT ad.trade_date,
            (SELECT COUNT(*) FROM orat_options_eod WHERE ticker = %s AND trade_date = ad.trade_date) as total_rows,
            (SELECT COUNT(*) FROM orat_options_eod WHERE ticker = %s AND trade_date = ad.trade_date AND gamma IS NOT NULL) as gamma_not_null,
            (SELECT COUNT(*) FROM orat_options_eod WHERE ticker = %s AND trade_date = ad.trade_date AND gamma > 0) as gamma_positive,
            (SELECT COUNT(*) FROM orat_options_eod WHERE ticker = %s AND trade_date = ad.trade_date AND dte <= 7) as dte_7_or_less
        FROM all_dates ad
        LEFT JOIN gex_dates gd ON ad.trade_date = gd.trade_date
        WHERE gd.trade_date IS NULL
        ORDER BY ad.trade_date DESC
        LIMIT 10
    """, params + params + [ticker, ticker, ticker, ticker])

    problem_dates = cur.fetchall()

    if problem_dates:
        print(f"\n{'Date':<15} {'Rows':<10} {'γ≠NULL':<10} {'γ>0':<10} {'DTE≤7':<10}")
        print("-" * 55)
        for row in problem_dates:
            print(f"{row[0]!s:<15} {row[1]:<10} {row[2]:<10} {row[3]:<10} {row[4]:<10}")
    else:
        print("\n✅ No problem dates found - all dates have GEX-eligible data!")

    # 6. Check gamma distribution
    print("\n" + "-" * 70)
    print("GAMMA VALUE DISTRIBUTION (for non-NULL gamma)")
    print("-" * 70)

    cur.execute(f"""
        SELECT
            COUNT(*) as total,
            COUNT(CASE WHEN gamma IS NULL THEN 1 END) as null_count,
            COUNT(CASE WHEN gamma = 0 THEN 1 END) as zero_count,
            COUNT(CASE WHEN gamma > 0 AND gamma < 0.0001 THEN 1 END) as tiny_count,
            COUNT(CASE WHEN gamma >= 0.0001 THEN 1 END) as usable_count,
            AVG(CASE WHEN gamma > 0 THEN gamma END) as avg_gamma,
            MAX(gamma) as max_gamma
        FROM orat_options_eod
        WHERE ticker = %s {date_filter}
    """, params)

    result = cur.fetchone()
    total, null_ct, zero_ct, tiny_ct, usable_ct, avg_gamma, max_gamma = result

    print(f"\nTotal rows: {total:,}")
    print(f"  NULL gamma:      {null_ct:>12,} ({null_ct/total*100:.1f}%)")
    print(f"  Zero gamma:      {zero_ct:>12,} ({zero_ct/total*100:.1f}%)")
    print(f"  Tiny gamma (<0.0001): {tiny_ct:>8,} ({tiny_ct/total*100:.1f}%)")
    print(f"  Usable gamma (≥0.0001): {usable_ct:>6,} ({usable_ct/total*100:.1f}%)")
    print(f"\n  Average gamma (when > 0): {avg_gamma:.6f}" if avg_gamma else "")
    print(f"  Max gamma: {max_gamma:.6f}" if max_gamma else "")

    conn.close()

    # Final summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    gex_coverage = (days_gex_eligible/days_with_any_data*100) if days_with_any_data else 0
    print(f"\n📊 GEX Coverage: {gex_coverage:.1f}% of trading days")
    print(f"   (Expected ~100% if ORAT provides complete data)")

    if gex_coverage < 90:
        if null_ct/total > 0.5:
            print("\n🔍 ROOT CAUSE: ORAT gamma field is NULL for >50% of records")
            print("   This is a DATA QUALITY issue from ORAT, not a missing data issue.")
            print("   ORAT may not calculate gamma for all option contracts.")
        elif days_with_gamma_positive < days_with_any_data * 0.9:
            print("\n🔍 ROOT CAUSE: Many dates have records but gamma is 0 or NULL")
            print("   This suggests ORAT data has quality gaps for certain dates.")
        else:
            print("\n🔍 ROOT CAUSE: Data exists but doesn't meet GEX criteria (dte <= 7)")
    else:
        print("\n✅ Data quality looks good!")

    print("\n" + "=" * 70)


def main():
    parser = argparse.ArgumentParser(description='Diagnose ORAT GEX data coverage')
    parser.add_argument('--ticker', type=str, default='SPY', help='Ticker to analyze (default: SPY)')
    parser.add_argument('--start', type=str, help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, help='End date (YYYY-MM-DD)')
    args = parser.parse_args()

    try:
        analyze_orat_coverage(args.ticker, args.start, args.end)
    except ImportError:
        print("❌ psycopg2 not installed. Install with: pip install psycopg2-binary")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
