#!/usr/bin/env python3
"""
Debug GEX Wall Calculation
==========================
Check why GEX walls might be too close to spot price, causing SD fallback.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from quant.kronos_gex_calculator import KronosGEXCalculator


def debug_gex_walls(ticker: str = 'SPY', num_days: int = 10):
    """Check GEX walls for recent trading days"""

    import psycopg2

    database_url = os.getenv('ORAT_DATABASE_URL') or os.getenv('DATABASE_URL')
    conn = psycopg2.connect(database_url)
    cur = conn.cursor()

    # Get recent trading dates
    cur.execute("""
        SELECT DISTINCT trade_date
        FROM orat_options_eod
        WHERE ticker = %s
        ORDER BY trade_date DESC
        LIMIT %s
    """, (ticker, num_days))
    dates = [row[0] for row in cur.fetchall()]
    conn.close()

    print("=" * 80)
    print(f"GEX WALL DEBUG FOR {ticker}")
    print("=" * 80)
    print(f"\nChecking {len(dates)} recent trading days...")
    print(f"Fallback happens when walls are < 0.5% from spot price\n")

    calc = KronosGEXCalculator(ticker)

    walls_too_close = 0
    walls_ok = 0
    no_gex = 0

    print(f"{'Date':<12} {'Spot':>10} {'Put Wall':>10} {'Call Wall':>10} {'Put Dist%':>10} {'Call Dist%':>10} {'Status':<15}")
    print("-" * 85)

    for trade_date in sorted(dates):
        gex = calc.calculate_gex_for_date(str(trade_date), dte_max=7)

        if not gex:
            print(f"{trade_date}  {'N/A':>10} {'N/A':>10} {'N/A':>10} {'N/A':>10} {'N/A':>10} NO GEX DATA")
            no_gex += 1
            continue

        spot = gex.spot_price
        put_wall = gex.put_wall
        call_wall = gex.call_wall

        # Calculate distances (same as backtest logic)
        put_dist_pct = (spot - put_wall) / spot * 100 if spot > 0 else 0
        call_dist_pct = (call_wall - spot) / spot * 100 if spot > 0 else 0

        # Check if walls would trigger fallback (< 0.5% from spot)
        min_pct = 0.5
        put_ok = put_dist_pct >= min_pct
        call_ok = call_dist_pct >= min_pct

        if put_ok and call_ok:
            status = "✅ GEX OK"
            walls_ok += 1
        else:
            status = "⚠️ SD FALLBACK"
            walls_too_close += 1
            if not put_ok:
                status += " (put)"
            if not call_ok:
                status += " (call)"

        print(f"{trade_date}  ${spot:>9.2f} ${put_wall:>9.2f} ${call_wall:>9.2f} {put_dist_pct:>9.2f}% {call_dist_pct:>9.2f}% {status}")

    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"  Days with GEX walls OK:      {walls_ok}")
    print(f"  Days with walls too close:   {walls_too_close}")
    print(f"  Days with no GEX data:       {no_gex}")

    if walls_too_close > 0:
        print(f"\n⚠️  {walls_too_close}/{len(dates)} days ({walls_too_close/len(dates)*100:.0f}%) trigger SD fallback")
        print("   because GEX walls are within 0.5% of spot price.")
        print("\n   POSSIBLE CAUSES:")
        print("   1. Put/Call wall defaulting to spot_price (no clear wall found)")
        print("   2. Market trading very close to major GEX levels")
        print("   3. GEX distribution too flat (no dominant strikes)")
    else:
        print(f"\n✅ All {walls_ok} days have valid GEX walls!")


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--ticker', default='SPY')
    parser.add_argument('--days', type=int, default=20)
    args = parser.parse_args()

    debug_gex_walls(args.ticker, args.days)
