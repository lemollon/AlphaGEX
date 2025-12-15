#!/usr/bin/env python3
"""
Diagnose GEX Strategy Issues

This script checks the database to understand why apache_directional strategy
might be failing for all trading days.

Usage:
    python scripts/diagnose_gex_strategy.py
"""

import os
import sys
from pathlib import Path

# Add parent directory for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load environment
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / '.env')


def get_connection():
    """Get database connection"""
    try:
        from database_adapter import get_connection as db_get_connection
        return db_get_connection()
    except ImportError:
        import psycopg2
        return psycopg2.connect(os.environ.get('DATABASE_URL'))


def main():
    print("=" * 70)
    print("GEX STRATEGY DIAGNOSTIC TOOL")
    print("=" * 70)

    conn = get_connection()
    cursor = conn.cursor()

    # Check 1: Does options data exist?
    print("\n1. OPTIONS DATA AVAILABILITY")
    print("-" * 50)

    cursor.execute("""
        SELECT
            ticker,
            COUNT(*) as total_rows,
            COUNT(DISTINCT trade_date) as trading_days,
            MIN(trade_date) as first_date,
            MAX(trade_date) as last_date
        FROM orat_options_eod
        WHERE ticker IN ('SPY', 'SPX')
        GROUP BY ticker
        ORDER BY ticker
    """)

    rows = cursor.fetchall()
    if rows:
        for row in rows:
            print(f"  {row[0]}: {row[1]:,} rows, {row[2]} days ({row[3]} to {row[4]})")
    else:
        print("  ❌ No options data found!")
        return

    # Check 2: Do we have gamma data?
    print("\n2. GAMMA DATA AVAILABILITY")
    print("-" * 50)

    cursor.execute("""
        SELECT
            ticker,
            COUNT(*) as total_rows,
            COUNT(gamma) as gamma_non_null,
            COUNT(CASE WHEN gamma > 0 THEN 1 END) as gamma_positive,
            AVG(CASE WHEN gamma > 0 THEN gamma END) as avg_positive_gamma
        FROM orat_options_eod
        WHERE ticker = 'SPY'
        GROUP BY ticker
    """)

    rows = cursor.fetchall()
    if rows:
        for row in rows:
            pct_non_null = (row[2] / row[1] * 100) if row[1] > 0 else 0
            pct_positive = (row[3] / row[1] * 100) if row[1] > 0 else 0
            print(f"  {row[0]}:")
            print(f"    Total rows: {row[1]:,}")
            print(f"    Gamma non-null: {row[2]:,} ({pct_non_null:.1f}%)")
            print(f"    Gamma > 0: {row[3]:,} ({pct_positive:.1f}%)")
            print(f"    Avg positive gamma: {row[4]:.6f}" if row[4] else "    Avg positive gamma: N/A")

    # Check 3: Do we have OI data?
    print("\n3. OPEN INTEREST DATA AVAILABILITY")
    print("-" * 50)

    cursor.execute("""
        SELECT
            ticker,
            COUNT(*) as total_rows,
            COUNT(call_oi) as call_oi_non_null,
            COUNT(CASE WHEN call_oi > 0 THEN 1 END) as call_oi_positive,
            COUNT(put_oi) as put_oi_non_null,
            COUNT(CASE WHEN put_oi > 0 THEN 1 END) as put_oi_positive
        FROM orat_options_eod
        WHERE ticker = 'SPY'
        GROUP BY ticker
    """)

    rows = cursor.fetchall()
    if rows:
        for row in rows:
            print(f"  {row[0]}:")
            print(f"    Call OI non-null: {row[2]:,} ({row[2]/row[1]*100:.1f}%)")
            print(f"    Call OI > 0: {row[3]:,} ({row[3]/row[1]*100:.1f}%)")
            print(f"    Put OI non-null: {row[4]:,} ({row[4]/row[1]*100:.1f}%)")
            print(f"    Put OI > 0: {row[5]:,} ({row[5]/row[1]*100:.1f}%)")

    # Check 4: Sample data for one day
    print("\n4. SAMPLE DATA FOR ONE DAY")
    print("-" * 50)

    cursor.execute("""
        SELECT trade_date FROM orat_options_eod
        WHERE ticker = 'SPY' AND dte = 0
        ORDER BY trade_date DESC LIMIT 1
    """)
    sample_date = cursor.fetchone()

    if sample_date:
        sample_date = sample_date[0]
        print(f"  Checking data for {sample_date} (0DTE):")

        cursor.execute("""
            SELECT
                strike, underlying_price, dte,
                gamma, call_oi, put_oi,
                put_bid, call_bid
            FROM orat_options_eod
            WHERE ticker = 'SPY' AND trade_date = %s AND dte = 0
            ORDER BY strike
            LIMIT 20
        """, (sample_date,))

        rows = cursor.fetchall()
        print(f"\n  Strike | Underlying | DTE | Gamma | Call OI | Put OI | Put Bid | Call Bid")
        print(f"  {'-'*75}")
        for row in rows:
            gamma_str = f"{row[3]:.6f}" if row[3] else "NULL"
            call_oi_str = f"{row[4]:,}" if row[4] else "NULL"
            put_oi_str = f"{row[5]:,}" if row[5] else "NULL"
            print(f"  {row[0]:>6} | {row[1]:>10} | {row[2]:>3} | {gamma_str:>8} | {call_oi_str:>7} | {put_oi_str:>6} | {row[6] or 0:>7.2f} | {row[7] or 0:>8.2f}")

    # Check 5: Calculate GEX walls for sample days
    print("\n5. GEX WALL CALCULATION TEST")
    print("-" * 50)

    # Get 5 random recent trading days
    cursor.execute("""
        SELECT DISTINCT trade_date FROM orat_options_eod
        WHERE ticker = 'SPY' AND dte = 0
        ORDER BY trade_date DESC LIMIT 5
    """)
    test_dates = cursor.fetchall()

    for (test_date,) in test_dates:
        cursor.execute("""
            SELECT
                strike, underlying_price, gamma, call_oi, put_oi
            FROM orat_options_eod
            WHERE ticker = 'SPY' AND trade_date = %s AND dte = 0
        """, (test_date,))

        options = cursor.fetchall()

        if not options:
            print(f"  {test_date}: No 0DTE options found")
            continue

        # Calculate GEX walls
        spot_price = options[0][1] if options[0][1] else 0
        strike_gex = {}
        has_gamma = False

        for strike, underlying, gamma, call_oi, put_oi in options:
            gamma = gamma or 0
            call_oi = call_oi or 0
            put_oi = put_oi or 0

            if strike not in strike_gex:
                strike_gex[strike] = {'call_gex': 0, 'put_gex': 0}

            if gamma > 0:
                has_gamma = True
                call_gex = gamma * call_oi * 100 * (spot_price ** 2) / 1e9
                put_gex = gamma * put_oi * 100 * (spot_price ** 2) / 1e9
                strike_gex[strike]['call_gex'] += call_gex
                strike_gex[strike]['put_gex'] += put_gex

        if not has_gamma:
            print(f"  {test_date}: ❌ No gamma data (gamma=0 or NULL for all options)")
            continue

        # Find walls
        call_wall = 0
        max_call_gex = 0
        put_wall = 0
        max_put_gex = 0

        for strike, gex in strike_gex.items():
            if strike > spot_price and gex['call_gex'] > max_call_gex:
                max_call_gex = gex['call_gex']
                call_wall = strike
            if strike < spot_price and gex['put_gex'] > max_put_gex:
                max_put_gex = gex['put_gex']
                put_wall = strike

        total_call_gex = sum(g['call_gex'] for g in strike_gex.values())
        total_put_gex = sum(g['put_gex'] for g in strike_gex.values())

        if total_call_gex > 0:
            gex_ratio = abs(total_put_gex) / abs(total_call_gex)
        else:
            gex_ratio = 10.0 if total_put_gex > 0 else 1.0

        # Wall proximity
        put_dist = abs(spot_price - put_wall) / spot_price * 100 if put_wall else 100
        call_dist = abs(spot_price - call_wall) / spot_price * 100 if call_wall else 100

        wall_proximity_pct = 1.0  # Default
        near_put = put_dist <= wall_proximity_pct
        near_call = call_dist <= wall_proximity_pct

        # Check conditions
        MIN_RATIO_BEARISH = 1.5
        MIN_RATIO_BULLISH = 0.67

        trade_signal = None
        if gex_ratio >= MIN_RATIO_BEARISH and near_put:
            trade_signal = "BEARISH (bear put spread)"
        elif gex_ratio <= MIN_RATIO_BULLISH and near_call:
            trade_signal = "BULLISH (bull call spread)"

        status = "✅" if trade_signal else "❌"
        print(f"  {test_date}:")
        print(f"    Spot: ${spot_price:.2f}, Put Wall: ${put_wall:.0f} ({put_dist:.2f}% away), Call Wall: ${call_wall:.0f} ({call_dist:.2f}% away)")
        print(f"    GEX Ratio: {gex_ratio:.2f} (needs <0.67 or >1.5 for signal)")
        print(f"    Near Put Wall: {near_put}, Near Call Wall: {near_call} (threshold: {wall_proximity_pct}%)")
        print(f"    {status} Signal: {trade_signal or 'NONE - conditions not met'}")

    # Check 6: Wall proximity analysis over many days
    print("\n6. WALL PROXIMITY DISTRIBUTION")
    print("-" * 50)

    # Check how often price is near walls across all trading days
    cursor.execute("""
        WITH daily_data AS (
            SELECT
                trade_date,
                strike,
                underlying_price,
                gamma,
                call_oi,
                put_oi
            FROM orat_options_eod
            WHERE ticker = 'SPY' AND dte = 0
        )
        SELECT
            COUNT(DISTINCT trade_date) as total_days
        FROM daily_data
        WHERE gamma > 0
    """)

    result = cursor.fetchone()
    if result:
        print(f"  Days with gamma data: {result[0]}")

        # Recommendation
        print("\n" + "=" * 70)
        print("RECOMMENDATIONS")
        print("=" * 70)

        if result[0] == 0:
            print("""
  ❌ CRITICAL: No gamma data in database!

  The apache_directional strategy requires gamma values to calculate GEX walls.
  Without gamma, no trades can be generated.

  SOLUTION: Your ORAT data import needs to include gamma values.
  Check if your data source provides gamma, or use a different data source.
""")
        else:
            print("""
  The strategy filters are very restrictive:
  1. Must be within 1% of a GEX wall
  2. GEX ratio must be < 0.67 (bullish) or > 1.5 (bearish)

  Consider adjusting these parameters:
  - --wall-proximity 2.0  (increase from 1% to 2%)
  - Or modify MIN_RATIO thresholds in the code

  Example:
    python backtest/zero_dte_hybrid_fixed.py --strategy apache_directional \\
        --start 2022-01-01 --capital 1000 --risk 10 --ticker SPY \\
        --wall-proximity 2.0
""")

    conn.close()
    print("\nDone!")


if __name__ == "__main__":
    main()
