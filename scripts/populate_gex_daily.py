#!/usr/bin/env python3
"""
Populate GEX Daily Table

Pre-computes and stores daily Gamma Exposure (GEX) data for SPX and SPY.
This enables:
- Fast backtesting (no on-the-fly GEX calculation)
- Historical GEX analysis and visualization
- Filtering trades by net gamma magnitude

Usage:
    # Populate all available dates
    python scripts/populate_gex_daily.py

    # Populate specific date range
    python scripts/populate_gex_daily.py --start 2022-01-01 --end 2024-12-31

    # Populate single symbol
    python scripts/populate_gex_daily.py --symbol SPY

    # Show top 5 net gamma days after populating
    python scripts/populate_gex_daily.py --top 5
"""

import os
import sys
import argparse
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import math

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / '.env')


def get_connection():
    """Get PostgreSQL connection"""
    import psycopg2
    from urllib.parse import urlparse

    database_url = os.getenv('ORAT_DATABASE_URL') or os.getenv('DATABASE_URL')
    if not database_url:
        raise ValueError("DATABASE_URL or ORAT_DATABASE_URL not set")

    result = urlparse(database_url)
    return psycopg2.connect(
        host=result.hostname,
        port=result.port or 5432,
        user=result.username,
        password=result.password,
        database=result.path[1:],
        connect_timeout=30
    )


def create_gex_daily_table(conn):
    """Create gex_daily table if it doesn't exist"""
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS gex_daily (
            id SERIAL PRIMARY KEY,
            trade_date DATE NOT NULL,
            symbol VARCHAR(10) NOT NULL,

            -- Price context
            spot_price NUMERIC(12,4),

            -- Core GEX metrics
            net_gex NUMERIC(20,2),           -- Net gamma exposure (call - put)
            total_call_gex NUMERIC(20,2),    -- Total call gamma
            total_put_gex NUMERIC(20,2),     -- Total put gamma (negative)

            -- Key levels
            call_wall NUMERIC(12,4),         -- Strike with highest call GEX (resistance)
            put_wall NUMERIC(12,4),          -- Strike with highest put GEX (support)
            flip_point NUMERIC(12,4),        -- Where net GEX crosses zero

            -- Normalized metrics
            gex_normalized NUMERIC(20,10),   -- net_gex / spot^2 (scale-independent)
            gex_regime VARCHAR(20),          -- POSITIVE, NEGATIVE, NEUTRAL

            -- Position relative to levels
            distance_to_flip_pct NUMERIC(10,4),
            distance_to_call_wall_pct NUMERIC(10,4),
            distance_to_put_wall_pct NUMERIC(10,4),
            above_call_wall BOOLEAN,
            below_put_wall BOOLEAN,
            between_walls BOOLEAN,

            -- Data quality
            options_count INTEGER,           -- Number of options used
            dte_max_used INTEGER DEFAULT 7,  -- Max DTE for GEX calculation

            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

            UNIQUE(trade_date, symbol)
        )
    """)

    # Create indexes for common queries
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_gex_daily_date ON gex_daily(trade_date)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_gex_daily_symbol ON gex_daily(symbol)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_gex_daily_net_gex ON gex_daily(net_gex DESC)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_gex_daily_regime ON gex_daily(gex_regime)
    """)

    conn.commit()
    print("Created gex_daily table")


def get_available_dates(conn, symbol: str, start_date: str = None, end_date: str = None) -> List[str]:
    """Get list of dates with options data"""
    cursor = conn.cursor()

    # Map symbol to underlying
    underlying = 'SPX' if symbol == 'SPX' else 'SPY'

    query = """
        SELECT DISTINCT trade_date
        FROM orat_options_eod
        WHERE ticker = %s
    """
    params = [underlying]

    if start_date:
        query += " AND trade_date >= %s"
        params.append(start_date)
    if end_date:
        query += " AND trade_date <= %s"
        params.append(end_date)

    query += " ORDER BY trade_date"

    cursor.execute(query, params)
    dates = [row[0].strftime('%Y-%m-%d') for row in cursor.fetchall()]

    return dates


def get_existing_dates(conn, symbol: str) -> set:
    """Get dates already populated in gex_daily"""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT trade_date FROM gex_daily WHERE symbol = %s
    """, (symbol,))
    return {row[0].strftime('%Y-%m-%d') for row in cursor.fetchall()}


def calculate_gex_for_date(conn, symbol: str, trade_date: str, dte_max: int = 7) -> Optional[Dict]:
    """
    Calculate GEX metrics for a single date.

    GEX Formula: GEX = gamma × open_interest × 100 × spot_price

    Returns dict with all GEX metrics or None if insufficient data.
    """
    cursor = conn.cursor()

    # Map symbol to ticker in ORAT data
    ticker = 'SPX' if symbol == 'SPX' else 'SPY'

    # Get options data for this date (0-7 DTE for near-term gamma)
    cursor.execute("""
        SELECT
            strike,
            call_put,
            gamma,
            open_interest,
            delta,
            underlying_price
        FROM orat_options_eod
        WHERE ticker = %s
        AND trade_date = %s
        AND dte <= %s
        AND dte >= 0
        AND gamma IS NOT NULL
        AND gamma > 0
        AND open_interest > 0
    """, (ticker, trade_date, dte_max))

    rows = cursor.fetchall()

    if not rows:
        return None

    # Get spot price (use first row's underlying price)
    spot_price = float(rows[0][5])

    # Calculate GEX by strike
    strike_gex = {}  # strike -> {'call_gex': x, 'put_gex': y}

    for row in rows:
        strike = float(row[0])
        call_put = row[1]  # 'C' or 'P'
        gamma = float(row[2])
        oi = int(row[3])

        # GEX = gamma × OI × 100 × spot
        # For puts, dealers are SHORT, so put GEX is negative
        gex = gamma * oi * 100 * spot_price

        if strike not in strike_gex:
            strike_gex[strike] = {'call_gex': 0, 'put_gex': 0}

        if call_put == 'C':
            strike_gex[strike]['call_gex'] += gex
        else:
            strike_gex[strike]['put_gex'] -= gex  # Negative for puts

    # Calculate totals
    total_call_gex = sum(s['call_gex'] for s in strike_gex.values())
    total_put_gex = sum(s['put_gex'] for s in strike_gex.values())
    net_gex = total_call_gex + total_put_gex  # put_gex is already negative

    # Find call wall (highest call GEX above spot)
    call_wall = None
    max_call_gex = 0
    for strike, gex_data in strike_gex.items():
        if strike > spot_price and gex_data['call_gex'] > max_call_gex:
            max_call_gex = gex_data['call_gex']
            call_wall = strike

    # Find put wall (highest absolute put GEX below spot)
    put_wall = None
    max_put_gex = 0
    for strike, gex_data in strike_gex.items():
        if strike < spot_price and abs(gex_data['put_gex']) > max_put_gex:
            max_put_gex = abs(gex_data['put_gex'])
            put_wall = strike

    # Find flip point (where net GEX crosses zero)
    flip_point = None
    sorted_strikes = sorted(strike_gex.keys())
    for i in range(len(sorted_strikes) - 1):
        s1, s2 = sorted_strikes[i], sorted_strikes[i+1]
        net1 = strike_gex[s1]['call_gex'] + strike_gex[s1]['put_gex']
        net2 = strike_gex[s2]['call_gex'] + strike_gex[s2]['put_gex']

        # Check for sign change
        if (net1 > 0 and net2 < 0) or (net1 < 0 and net2 > 0):
            # Linear interpolation
            if net2 != net1:
                flip_point = s1 + (s2 - s1) * abs(net1) / (abs(net1) + abs(net2))
            break

    # Normalized GEX (scale-independent)
    gex_normalized = net_gex / (spot_price ** 2) if spot_price > 0 else 0

    # Determine regime
    # Thresholds based on typical SPX GEX values
    if gex_normalized > 0.5:
        gex_regime = 'POSITIVE'
    elif gex_normalized < -0.5:
        gex_regime = 'NEGATIVE'
    else:
        gex_regime = 'NEUTRAL'

    # Distance calculations
    distance_to_flip = ((spot_price - flip_point) / spot_price * 100) if flip_point else None
    distance_to_call_wall = ((call_wall - spot_price) / spot_price * 100) if call_wall else None
    distance_to_put_wall = ((spot_price - put_wall) / spot_price * 100) if put_wall else None

    # Position flags
    above_call_wall = spot_price > call_wall if call_wall else False
    below_put_wall = spot_price < put_wall if put_wall else False
    between_walls = (put_wall and call_wall and put_wall < spot_price < call_wall) if (put_wall and call_wall) else False

    return {
        'trade_date': trade_date,
        'symbol': symbol,
        'spot_price': spot_price,
        'net_gex': net_gex,
        'total_call_gex': total_call_gex,
        'total_put_gex': total_put_gex,
        'call_wall': call_wall,
        'put_wall': put_wall,
        'flip_point': flip_point,
        'gex_normalized': gex_normalized,
        'gex_regime': gex_regime,
        'distance_to_flip_pct': distance_to_flip,
        'distance_to_call_wall_pct': distance_to_call_wall,
        'distance_to_put_wall_pct': distance_to_put_wall,
        'above_call_wall': above_call_wall,
        'below_put_wall': below_put_wall,
        'between_walls': between_walls,
        'options_count': len(rows),
        'dte_max_used': dte_max,
    }


def insert_gex_record(conn, gex_data: Dict):
    """Insert or update GEX record"""
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO gex_daily (
            trade_date, symbol, spot_price,
            net_gex, total_call_gex, total_put_gex,
            call_wall, put_wall, flip_point,
            gex_normalized, gex_regime,
            distance_to_flip_pct, distance_to_call_wall_pct, distance_to_put_wall_pct,
            above_call_wall, below_put_wall, between_walls,
            options_count, dte_max_used
        ) VALUES (
            %(trade_date)s, %(symbol)s, %(spot_price)s,
            %(net_gex)s, %(total_call_gex)s, %(total_put_gex)s,
            %(call_wall)s, %(put_wall)s, %(flip_point)s,
            %(gex_normalized)s, %(gex_regime)s,
            %(distance_to_flip_pct)s, %(distance_to_call_wall_pct)s, %(distance_to_put_wall_pct)s,
            %(above_call_wall)s, %(below_put_wall)s, %(between_walls)s,
            %(options_count)s, %(dte_max_used)s
        )
        ON CONFLICT (trade_date, symbol) DO UPDATE SET
            spot_price = EXCLUDED.spot_price,
            net_gex = EXCLUDED.net_gex,
            total_call_gex = EXCLUDED.total_call_gex,
            total_put_gex = EXCLUDED.total_put_gex,
            call_wall = EXCLUDED.call_wall,
            put_wall = EXCLUDED.put_wall,
            flip_point = EXCLUDED.flip_point,
            gex_normalized = EXCLUDED.gex_normalized,
            gex_regime = EXCLUDED.gex_regime,
            distance_to_flip_pct = EXCLUDED.distance_to_flip_pct,
            distance_to_call_wall_pct = EXCLUDED.distance_to_call_wall_pct,
            distance_to_put_wall_pct = EXCLUDED.distance_to_put_wall_pct,
            above_call_wall = EXCLUDED.above_call_wall,
            below_put_wall = EXCLUDED.below_put_wall,
            between_walls = EXCLUDED.between_walls,
            options_count = EXCLUDED.options_count,
            dte_max_used = EXCLUDED.dte_max_used,
            created_at = CURRENT_TIMESTAMP
    """, gex_data)

    conn.commit()


def show_top_gex_days(conn, symbol: str = None, limit: int = 5):
    """Display top net gamma days"""
    cursor = conn.cursor()

    print("\n" + "=" * 80)
    print(f"TOP {limit} HIGHEST NET GAMMA DAYS")
    print("=" * 80)

    query = """
        SELECT
            trade_date,
            symbol,
            net_gex,
            spot_price,
            call_wall,
            put_wall,
            gex_regime,
            options_count
        FROM gex_daily
    """
    params = []

    if symbol:
        query += " WHERE symbol = %s"
        params.append(symbol)

    query += " ORDER BY net_gex DESC LIMIT %s"
    params.append(limit)

    cursor.execute(query, params)
    rows = cursor.fetchall()

    print(f"\n{'Date':<12} {'Symbol':<6} {'Net GEX':>15} {'Spot':>10} {'Put Wall':>10} {'Call Wall':>10} {'Regime':<10}")
    print("-" * 80)

    for row in rows:
        date, sym, net_gex, spot, call_wall, put_wall, regime, opts = row
        net_gex_b = net_gex / 1e9 if net_gex else 0
        print(f"{date} {sym:<6} {net_gex_b:>14.2f}B ${spot:>9.2f} ${put_wall or 0:>9.2f} ${call_wall or 0:>9.2f} {regime:<10}")

    print("\n" + "=" * 80)
    print(f"TOP {limit} LOWEST NET GAMMA DAYS (Most Negative)")
    print("=" * 80)

    query = """
        SELECT
            trade_date,
            symbol,
            net_gex,
            spot_price,
            call_wall,
            put_wall,
            gex_regime,
            options_count
        FROM gex_daily
    """
    params = []

    if symbol:
        query += " WHERE symbol = %s"
        params.append(symbol)

    query += " ORDER BY net_gex ASC LIMIT %s"
    params.append(limit)

    cursor.execute(query, params)
    rows = cursor.fetchall()

    print(f"\n{'Date':<12} {'Symbol':<6} {'Net GEX':>15} {'Spot':>10} {'Put Wall':>10} {'Call Wall':>10} {'Regime':<10}")
    print("-" * 80)

    for row in rows:
        date, sym, net_gex, spot, call_wall, put_wall, regime, opts = row
        net_gex_b = net_gex / 1e9 if net_gex else 0
        print(f"{date} {sym:<6} {net_gex_b:>14.2f}B ${spot:>9.2f} ${put_wall or 0:>9.2f} ${call_wall or 0:>9.2f} {regime:<10}")

    # Show summary stats
    cursor.execute("""
        SELECT
            symbol,
            COUNT(*) as days,
            AVG(net_gex) as avg_gex,
            MIN(net_gex) as min_gex,
            MAX(net_gex) as max_gex,
            SUM(CASE WHEN gex_regime = 'POSITIVE' THEN 1 ELSE 0 END) as positive_days,
            SUM(CASE WHEN gex_regime = 'NEGATIVE' THEN 1 ELSE 0 END) as negative_days
        FROM gex_daily
        GROUP BY symbol
    """)

    print("\n" + "=" * 80)
    print("GEX SUMMARY BY SYMBOL")
    print("=" * 80)

    for row in cursor.fetchall():
        sym, days, avg, min_gex, max_gex, pos, neg = row
        print(f"\n{sym}:")
        print(f"  Total days:     {days:,}")
        print(f"  Avg Net GEX:    ${avg/1e9:,.2f}B")
        print(f"  Min Net GEX:    ${min_gex/1e9:,.2f}B")
        print(f"  Max Net GEX:    ${max_gex/1e9:,.2f}B")
        print(f"  Positive days:  {pos:,} ({pos/days*100:.1f}%)")
        print(f"  Negative days:  {neg:,} ({neg/days*100:.1f}%)")


def main():
    parser = argparse.ArgumentParser(description='Populate GEX Daily Table')
    parser.add_argument('--start', type=str, help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, help='End date (YYYY-MM-DD)')
    parser.add_argument('--symbol', type=str, choices=['SPX', 'SPY'],
                        help='Single symbol to process (default: both)')
    parser.add_argument('--dte-max', type=int, default=7,
                        help='Max DTE for GEX calculation (default: 7)')
    parser.add_argument('--top', type=int, default=0,
                        help='Show top N net gamma days after populating')
    parser.add_argument('--force', action='store_true',
                        help='Recalculate existing dates')
    parser.add_argument('--show-only', action='store_true',
                        help='Only show top GEX days, do not populate')

    args = parser.parse_args()

    print("Connecting to database...")
    conn = get_connection()

    # Create table
    create_gex_daily_table(conn)

    if args.show_only:
        show_top_gex_days(conn, args.symbol, args.top or 5)
        conn.close()
        return

    # Symbols to process
    symbols = [args.symbol] if args.symbol else ['SPX', 'SPY']

    for symbol in symbols:
        print(f"\n{'='*60}")
        print(f"Processing {symbol}")
        print('='*60)

        # Get available dates
        available_dates = get_available_dates(conn, symbol, args.start, args.end)
        print(f"Found {len(available_dates)} dates with options data")

        if not args.force:
            existing_dates = get_existing_dates(conn, symbol)
            dates_to_process = [d for d in available_dates if d not in existing_dates]
            print(f"Already processed: {len(existing_dates)} dates")
            print(f"New dates to process: {len(dates_to_process)}")
        else:
            dates_to_process = available_dates
            print(f"Force mode: reprocessing all {len(dates_to_process)} dates")

        if not dates_to_process:
            print("No new dates to process")
            continue

        # Process each date
        success = 0
        failed = 0

        for i, trade_date in enumerate(dates_to_process):
            if i % 50 == 0:
                pct = (i / len(dates_to_process)) * 100
                print(f"\r  Processing {symbol}: {pct:.1f}% ({i}/{len(dates_to_process)})", end='', flush=True)

            try:
                gex_data = calculate_gex_for_date(conn, symbol, trade_date, args.dte_max)
                if gex_data:
                    insert_gex_record(conn, gex_data)
                    success += 1
                else:
                    failed += 1
            except Exception as e:
                print(f"\n  Error on {trade_date}: {e}")
                failed += 1

        print(f"\r  Processing {symbol}: 100% ({len(dates_to_process)}/{len(dates_to_process)})")
        print(f"  Success: {success}, Failed/No Data: {failed}")

    # Show top GEX days
    if args.top > 0:
        show_top_gex_days(conn, args.symbol, args.top)

    conn.close()
    print("\nDone!")


if __name__ == "__main__":
    main()
