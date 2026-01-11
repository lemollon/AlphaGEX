#!/usr/bin/env python3
"""
Populate GEX Structure from Options Chain Snapshots
====================================================

Uses the options_chain_snapshots table (populated by live Tradier/Polygon data)
to create gex_structure_daily records for ML training.

This enables ML model training from YOUR OWN collected data rather than
requiring the ORAT historical database.

Usage:
    python scripts/populate_gex_from_snapshots.py
    python scripts/populate_gex_from_snapshots.py --symbol SPY
    python scripts/populate_gex_from_snapshots.py --days 30  # Last 30 days

Requirements:
    - options_chain_snapshots table populated with data
    - Data should have gamma values per strike

Author: AlphaGEX Quant
"""

import os
import sys
import argparse
from datetime import datetime, timedelta, date
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / '.env')


def get_connection():
    """Get PostgreSQL connection"""
    import psycopg2
    from urllib.parse import urlparse

    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        raise ValueError("DATABASE_URL not set")

    result = urlparse(database_url)
    return psycopg2.connect(
        host=result.hostname,
        port=result.port or 5432,
        user=result.username,
        password=result.password,
        database=result.path[1:],
        connect_timeout=30
    )


def ensure_tables(conn):
    """Create GEX structure tables if they don't exist"""
    cursor = conn.cursor()

    # Table 1: Per-strike gamma data
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS gex_strikes (
            id SERIAL PRIMARY KEY,
            trade_date DATE NOT NULL,
            symbol VARCHAR(10) NOT NULL,
            strike NUMERIC(12,2) NOT NULL,
            call_gamma NUMERIC(20,2),
            put_gamma NUMERIC(20,2),
            net_gamma NUMERIC(20,2),
            call_oi INTEGER,
            put_oi INTEGER,
            distance_from_spot_pct NUMERIC(10,4),
            is_above_spot BOOLEAN,
            UNIQUE(trade_date, symbol, strike)
        )
    """)

    # Table 2: Daily summary with magnets, flips, and price
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS gex_structure_daily (
            id SERIAL PRIMARY KEY,
            trade_date DATE NOT NULL,
            symbol VARCHAR(10) NOT NULL,
            spot_open NUMERIC(12,4),
            spot_high NUMERIC(12,4),
            spot_low NUMERIC(12,4),
            spot_close NUMERIC(12,4),
            total_call_gamma NUMERIC(20,2),
            total_put_gamma NUMERIC(20,2),
            net_gamma NUMERIC(20,2),
            flip_point NUMERIC(12,4),
            flip_point_2 NUMERIC(12,4),
            magnet_1_strike NUMERIC(12,2),
            magnet_1_gamma NUMERIC(20,2),
            magnet_2_strike NUMERIC(12,2),
            magnet_2_gamma NUMERIC(20,2),
            magnet_3_strike NUMERIC(12,2),
            magnet_3_gamma NUMERIC(20,2),
            call_wall NUMERIC(12,4),
            put_wall NUMERIC(12,4),
            gamma_above_spot NUMERIC(20,2),
            gamma_below_spot NUMERIC(20,2),
            gamma_imbalance_pct NUMERIC(10,4),
            num_magnets_above INTEGER,
            num_magnets_below INTEGER,
            nearest_magnet_strike NUMERIC(12,2),
            nearest_magnet_distance_pct NUMERIC(10,4),
            open_to_flip_distance_pct NUMERIC(10,4),
            open_in_pin_zone BOOLEAN,
            price_open NUMERIC(12,4),
            price_close NUMERIC(12,4),
            price_high NUMERIC(12,4),
            price_low NUMERIC(12,4),
            price_change_pct NUMERIC(10,4),
            price_range_pct NUMERIC(10,4),
            close_distance_to_flip_pct NUMERIC(10,4),
            close_distance_to_magnet1_pct NUMERIC(10,4),
            close_distance_to_magnet2_pct NUMERIC(10,4),
            close_distance_to_call_wall_pct NUMERIC(10,4),
            close_distance_to_put_wall_pct NUMERIC(10,4),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(trade_date, symbol)
        )
    """)

    # Indexes
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_gex_strikes_date ON gex_strikes(trade_date)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_gex_strikes_symbol ON gex_strikes(symbol)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_gex_structure_date ON gex_structure_daily(trade_date)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_gex_structure_symbol ON gex_structure_daily(symbol)")

    conn.commit()
    print("  Tables ready")


def get_available_dates(conn, symbol: str, start_date: str = None, end_date: str = None) -> List[date]:
    """Get dates that have options chain snapshot data"""
    cursor = conn.cursor()

    query = """
        SELECT DISTINCT DATE(timestamp) as trade_date
        FROM options_chain_snapshots
        WHERE symbol = %s
    """
    params = [symbol]

    if start_date:
        query += " AND DATE(timestamp) >= %s"
        params.append(start_date)
    if end_date:
        query += " AND DATE(timestamp) <= %s"
        params.append(end_date)

    query += " ORDER BY trade_date"

    cursor.execute(query, params)
    return [row[0] for row in cursor.fetchall()]


def get_ohlc_for_date(conn, symbol: str, trade_date: date) -> Optional[Dict]:
    """Get OHLC price data for a date from collected snapshots"""
    cursor = conn.cursor()

    # Get min/max spot prices from the day's snapshots
    cursor.execute("""
        SELECT
            MIN(spot_price) as low,
            MAX(spot_price) as high,
            (SELECT spot_price FROM options_chain_snapshots
             WHERE symbol = %s AND DATE(timestamp) = %s
             ORDER BY timestamp LIMIT 1) as open_price,
            (SELECT spot_price FROM options_chain_snapshots
             WHERE symbol = %s AND DATE(timestamp) = %s
             ORDER BY timestamp DESC LIMIT 1) as close_price
        FROM options_chain_snapshots
        WHERE symbol = %s AND DATE(timestamp) = %s
    """, (symbol, trade_date, symbol, trade_date, symbol, trade_date))

    row = cursor.fetchone()
    if row and row[0]:
        return {
            'open': float(row[2]) if row[2] else float(row[0]),
            'high': float(row[1]) if row[1] else float(row[0]),
            'low': float(row[0]),
            'close': float(row[3]) if row[3] else float(row[0])
        }

    # Fallback: try Yahoo Finance
    try:
        import yfinance as yf
        ticker_map = {'SPX': '^GSPC', 'SPY': 'SPY', 'QQQ': 'QQQ'}
        ticker = ticker_map.get(symbol, symbol)

        end_dt = trade_date + timedelta(days=1)
        data = yf.download(ticker, start=trade_date, end=end_dt, progress=False)

        if len(data) > 0:
            return {
                'open': float(data['Open'].iloc[0]),
                'high': float(data['High'].iloc[0]),
                'low': float(data['Low'].iloc[0]),
                'close': float(data['Close'].iloc[0])
            }
    except Exception as e:
        pass

    return None


def calculate_gex_from_snapshots(conn, symbol: str, trade_date: date, dte_max: int = 7) -> Optional[Dict]:
    """
    Calculate GEX structure from options_chain_snapshots for a specific date.
    Uses the earliest snapshot of the day (near market open).
    """
    cursor = conn.cursor()

    # Get per-strike data from the earliest snapshot of the day
    cursor.execute("""
        WITH first_snapshot AS (
            SELECT MIN(timestamp) as snap_time
            FROM options_chain_snapshots
            WHERE symbol = %s AND DATE(timestamp) = %s
        )
        SELECT
            o.strike,
            o.option_type,
            o.gamma,
            o.open_interest,
            o.spot_price,
            o.dte
        FROM options_chain_snapshots o
        CROSS JOIN first_snapshot fs
        WHERE o.symbol = %s
          AND o.timestamp = fs.snap_time
          AND o.dte <= %s
          AND o.dte >= 0
          AND o.gamma IS NOT NULL
          AND o.gamma > 0
        ORDER BY o.strike
    """, (symbol, trade_date, symbol, dte_max))

    rows = cursor.fetchall()

    if not rows:
        return None

    # Get spot price and OHLC
    spot_price = float(rows[0][4])
    ohlc = get_ohlc_for_date(conn, symbol, trade_date)
    if not ohlc:
        ohlc = {'open': spot_price, 'high': spot_price * 1.005,
                'low': spot_price * 0.995, 'close': spot_price}

    spot_open = ohlc['open']

    # Build per-strike gamma - aggregate by strike
    strike_data = {}

    for row in rows:
        strike = float(row[0])
        option_type = row[1]
        gamma = float(row[2])
        oi = int(row[3]) if row[3] else 0

        # GEX = gamma * OI * 100 * spot^2
        gex = gamma * oi * 100 * (spot_open ** 2)

        if strike not in strike_data:
            strike_data[strike] = {
                'call_gamma': 0, 'put_gamma': 0, 'net_gamma': 0,
                'call_oi': 0, 'put_oi': 0
            }

        if option_type == 'call':
            strike_data[strike]['call_gamma'] += gex
            strike_data[strike]['net_gamma'] += gex
            strike_data[strike]['call_oi'] += oi
        else:  # put
            strike_data[strike]['put_gamma'] -= gex  # Negative for puts
            strike_data[strike]['net_gamma'] -= gex
            strike_data[strike]['put_oi'] += oi

    if not strike_data:
        return None

    # Find magnets (top 3 by absolute net gamma)
    sorted_by_gamma = sorted(
        strike_data.items(),
        key=lambda x: abs(x[1]['net_gamma']),
        reverse=True
    )

    magnets = []
    for strike, data in sorted_by_gamma[:5]:
        magnets.append({
            'strike': strike,
            'gamma': data['net_gamma'],
            'abs_gamma': abs(data['net_gamma'])
        })

    # Find flip points
    flip_points = []
    sorted_strikes = sorted(strike_data.keys())

    for i in range(len(sorted_strikes) - 1):
        s1, s2 = sorted_strikes[i], sorted_strikes[i+1]
        net1 = strike_data[s1]['net_gamma']
        net2 = strike_data[s2]['net_gamma']

        if (net1 > 0 and net2 < 0) or (net1 < 0 and net2 > 0):
            if net2 != net1:
                flip = s1 + (s2 - s1) * abs(net1) / (abs(net1) + abs(net2))
                flip_points.append(flip)

    # Calculate aggregates
    total_call_gamma = sum(d['call_gamma'] for d in strike_data.values())
    total_put_gamma = sum(d['put_gamma'] for d in strike_data.values())
    net_gamma = total_call_gamma + total_put_gamma

    # Gamma above/below spot
    gamma_above = sum(d['net_gamma'] for s, d in strike_data.items() if s > spot_open)
    gamma_below = sum(d['net_gamma'] for s, d in strike_data.items() if s < spot_open)

    total_abs = abs(gamma_above) + abs(gamma_below)
    gamma_imbalance = (gamma_above - gamma_below) / total_abs * 100 if total_abs > 0 else 0

    # Magnets above/below
    num_magnets_above = sum(1 for m in magnets[:3] if m['strike'] > spot_open)
    num_magnets_below = sum(1 for m in magnets[:3] if m['strike'] < spot_open)

    # Nearest magnet
    nearest_magnet = min(magnets[:3], key=lambda m: abs(m['strike'] - spot_open)) if magnets else None
    nearest_magnet_distance = abs(nearest_magnet['strike'] - spot_open) / spot_open * 100 if nearest_magnet else None

    # Traditional walls
    call_wall = None
    put_wall = None
    max_call_above = 0
    max_put_below = 0

    for strike, data in strike_data.items():
        if strike > spot_open and data['call_gamma'] > max_call_above:
            max_call_above = data['call_gamma']
            call_wall = strike
        if strike < spot_open and abs(data['put_gamma']) > max_put_below:
            max_put_below = abs(data['put_gamma'])
            put_wall = strike

    # Flip distance
    flip_point = flip_points[0] if flip_points else None
    open_to_flip = ((spot_open - flip_point) / spot_open * 100) if flip_point else None

    # Pin zone detection
    in_pin_zone = False
    if len(magnets) >= 2:
        m1, m2 = magnets[0]['strike'], magnets[1]['strike']
        low_magnet, high_magnet = min(m1, m2), max(m1, m2)
        if low_magnet < spot_open < high_magnet:
            in_pin_zone = True

    # Price outcomes
    price_change_pct = (ohlc['close'] - ohlc['open']) / ohlc['open'] * 100
    price_range_pct = (ohlc['high'] - ohlc['low']) / ohlc['open'] * 100

    # Distances at close
    close_distance_to_flip = ((ohlc['close'] - flip_point) / ohlc['close'] * 100) if flip_point else None
    close_distance_to_magnet1 = (ohlc['close'] - magnets[0]['strike']) / ohlc['close'] * 100 if magnets else None
    close_distance_to_magnet2 = (ohlc['close'] - magnets[1]['strike']) / ohlc['close'] * 100 if len(magnets) > 1 else None
    close_distance_to_call_wall = ((ohlc['close'] - call_wall) / ohlc['close'] * 100) if call_wall else None
    close_distance_to_put_wall = ((ohlc['close'] - put_wall) / ohlc['close'] * 100) if put_wall else None

    return {
        'strike_data': strike_data,
        'summary': {
            'trade_date': trade_date.strftime('%Y-%m-%d'),
            'symbol': symbol,
            'spot_open': ohlc['open'],
            'spot_high': ohlc['high'],
            'spot_low': ohlc['low'],
            'spot_close': ohlc['close'],
            'total_call_gamma': total_call_gamma,
            'total_put_gamma': total_put_gamma,
            'net_gamma': net_gamma,
            'flip_point': flip_point,
            'flip_point_2': flip_points[1] if len(flip_points) > 1 else None,
            'magnet_1_strike': magnets[0]['strike'] if len(magnets) > 0 else None,
            'magnet_1_gamma': magnets[0]['gamma'] if len(magnets) > 0 else None,
            'magnet_2_strike': magnets[1]['strike'] if len(magnets) > 1 else None,
            'magnet_2_gamma': magnets[1]['gamma'] if len(magnets) > 1 else None,
            'magnet_3_strike': magnets[2]['strike'] if len(magnets) > 2 else None,
            'magnet_3_gamma': magnets[2]['gamma'] if len(magnets) > 2 else None,
            'call_wall': call_wall,
            'put_wall': put_wall,
            'gamma_above_spot': gamma_above,
            'gamma_below_spot': gamma_below,
            'gamma_imbalance_pct': gamma_imbalance,
            'num_magnets_above': num_magnets_above,
            'num_magnets_below': num_magnets_below,
            'nearest_magnet_strike': nearest_magnet['strike'] if nearest_magnet else None,
            'nearest_magnet_distance_pct': nearest_magnet_distance,
            'open_to_flip_distance_pct': open_to_flip,
            'open_in_pin_zone': in_pin_zone,
            'price_open': ohlc['open'],
            'price_close': ohlc['close'],
            'price_high': ohlc['high'],
            'price_low': ohlc['low'],
            'price_change_pct': price_change_pct,
            'price_range_pct': price_range_pct,
            'close_distance_to_flip_pct': close_distance_to_flip,
            'close_distance_to_magnet1_pct': close_distance_to_magnet1,
            'close_distance_to_magnet2_pct': close_distance_to_magnet2,
            'close_distance_to_call_wall_pct': close_distance_to_call_wall,
            'close_distance_to_put_wall_pct': close_distance_to_put_wall,
        }
    }


def insert_gex_structure(conn, structure: Dict):
    """Insert GEX structure data into both tables"""
    cursor = conn.cursor()

    trade_date = structure['summary']['trade_date']
    symbol = structure['summary']['symbol']
    spot_open = structure['summary']['spot_open']

    # Insert per-strike data
    for strike, data in structure['strike_data'].items():
        distance_pct = (strike - spot_open) / spot_open * 100
        is_above = strike > spot_open

        cursor.execute("""
            INSERT INTO gex_strikes (
                trade_date, symbol, strike,
                call_gamma, put_gamma, net_gamma,
                call_oi, put_oi,
                distance_from_spot_pct, is_above_spot
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (trade_date, symbol, strike) DO UPDATE SET
                call_gamma = EXCLUDED.call_gamma,
                put_gamma = EXCLUDED.put_gamma,
                net_gamma = EXCLUDED.net_gamma,
                call_oi = EXCLUDED.call_oi,
                put_oi = EXCLUDED.put_oi,
                distance_from_spot_pct = EXCLUDED.distance_from_spot_pct,
                is_above_spot = EXCLUDED.is_above_spot
        """, (
            trade_date, symbol, strike,
            data['call_gamma'], data['put_gamma'], data['net_gamma'],
            data['call_oi'], data['put_oi'],
            distance_pct, is_above
        ))

    # Insert summary
    s = structure['summary']
    cursor.execute("""
        INSERT INTO gex_structure_daily (
            trade_date, symbol,
            spot_open, spot_high, spot_low, spot_close,
            total_call_gamma, total_put_gamma, net_gamma,
            flip_point, flip_point_2,
            magnet_1_strike, magnet_1_gamma,
            magnet_2_strike, magnet_2_gamma,
            magnet_3_strike, magnet_3_gamma,
            call_wall, put_wall,
            gamma_above_spot, gamma_below_spot, gamma_imbalance_pct,
            num_magnets_above, num_magnets_below,
            nearest_magnet_strike, nearest_magnet_distance_pct,
            open_to_flip_distance_pct, open_in_pin_zone,
            price_open, price_close, price_high, price_low,
            price_change_pct, price_range_pct,
            close_distance_to_flip_pct, close_distance_to_magnet1_pct,
            close_distance_to_magnet2_pct, close_distance_to_call_wall_pct,
            close_distance_to_put_wall_pct
        ) VALUES (
            %(trade_date)s, %(symbol)s,
            %(spot_open)s, %(spot_high)s, %(spot_low)s, %(spot_close)s,
            %(total_call_gamma)s, %(total_put_gamma)s, %(net_gamma)s,
            %(flip_point)s, %(flip_point_2)s,
            %(magnet_1_strike)s, %(magnet_1_gamma)s,
            %(magnet_2_strike)s, %(magnet_2_gamma)s,
            %(magnet_3_strike)s, %(magnet_3_gamma)s,
            %(call_wall)s, %(put_wall)s,
            %(gamma_above_spot)s, %(gamma_below_spot)s, %(gamma_imbalance_pct)s,
            %(num_magnets_above)s, %(num_magnets_below)s,
            %(nearest_magnet_strike)s, %(nearest_magnet_distance_pct)s,
            %(open_to_flip_distance_pct)s, %(open_in_pin_zone)s,
            %(price_open)s, %(price_close)s, %(price_high)s, %(price_low)s,
            %(price_change_pct)s, %(price_range_pct)s,
            %(close_distance_to_flip_pct)s, %(close_distance_to_magnet1_pct)s,
            %(close_distance_to_magnet2_pct)s, %(close_distance_to_call_wall_pct)s,
            %(close_distance_to_put_wall_pct)s
        )
        ON CONFLICT (trade_date, symbol) DO UPDATE SET
            spot_open = EXCLUDED.spot_open,
            spot_high = EXCLUDED.spot_high,
            spot_low = EXCLUDED.spot_low,
            spot_close = EXCLUDED.spot_close,
            total_call_gamma = EXCLUDED.total_call_gamma,
            total_put_gamma = EXCLUDED.total_put_gamma,
            net_gamma = EXCLUDED.net_gamma,
            flip_point = EXCLUDED.flip_point,
            flip_point_2 = EXCLUDED.flip_point_2,
            magnet_1_strike = EXCLUDED.magnet_1_strike,
            magnet_1_gamma = EXCLUDED.magnet_1_gamma,
            magnet_2_strike = EXCLUDED.magnet_2_strike,
            magnet_2_gamma = EXCLUDED.magnet_2_gamma,
            magnet_3_strike = EXCLUDED.magnet_3_strike,
            magnet_3_gamma = EXCLUDED.magnet_3_gamma,
            call_wall = EXCLUDED.call_wall,
            put_wall = EXCLUDED.put_wall,
            gamma_above_spot = EXCLUDED.gamma_above_spot,
            gamma_below_spot = EXCLUDED.gamma_below_spot,
            gamma_imbalance_pct = EXCLUDED.gamma_imbalance_pct,
            num_magnets_above = EXCLUDED.num_magnets_above,
            num_magnets_below = EXCLUDED.num_magnets_below,
            nearest_magnet_strike = EXCLUDED.nearest_magnet_strike,
            nearest_magnet_distance_pct = EXCLUDED.nearest_magnet_distance_pct,
            open_to_flip_distance_pct = EXCLUDED.open_to_flip_distance_pct,
            open_in_pin_zone = EXCLUDED.open_in_pin_zone,
            price_open = EXCLUDED.price_open,
            price_close = EXCLUDED.price_close,
            price_high = EXCLUDED.price_high,
            price_low = EXCLUDED.price_low,
            price_change_pct = EXCLUDED.price_change_pct,
            price_range_pct = EXCLUDED.price_range_pct,
            close_distance_to_flip_pct = EXCLUDED.close_distance_to_flip_pct,
            close_distance_to_magnet1_pct = EXCLUDED.close_distance_to_magnet1_pct,
            close_distance_to_magnet2_pct = EXCLUDED.close_distance_to_magnet2_pct,
            close_distance_to_call_wall_pct = EXCLUDED.close_distance_to_call_wall_pct,
            close_distance_to_put_wall_pct = EXCLUDED.close_distance_to_put_wall_pct,
            created_at = CURRENT_TIMESTAMP
    """, s)

    conn.commit()


def main():
    parser = argparse.ArgumentParser(description='Populate GEX Structure from Snapshots')
    parser.add_argument('--symbol', type=str, default='SPY', help='Symbol (default: SPY)')
    parser.add_argument('--days', type=int, default=None, help='Last N days to process')
    parser.add_argument('--start', type=str, help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, help='End date (YYYY-MM-DD)')
    args = parser.parse_args()

    print("=" * 70)
    print("POPULATE GEX STRUCTURE FROM OPTIONS CHAIN SNAPSHOTS")
    print("=" * 70)

    conn = get_connection()

    # Ensure tables exist
    print("\nPreparing tables...")
    ensure_tables(conn)

    # Check what snapshot data is available
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            COUNT(*) as total,
            COUNT(DISTINCT DATE(timestamp)) as days,
            MIN(DATE(timestamp)) as first_date,
            MAX(DATE(timestamp)) as last_date
        FROM options_chain_snapshots
        WHERE symbol = %s
    """, (args.symbol,))

    row = cursor.fetchone()
    total_records, unique_days, first_date, last_date = row

    print(f"\nOptions Chain Snapshots for {args.symbol}:")
    print(f"  Total records: {total_records:,}")
    print(f"  Unique days: {unique_days}")
    if first_date:
        print(f"  Date range: {first_date} to {last_date}")

    if unique_days == 0:
        print("\nNo options chain snapshot data found!")
        print("Run the option chain collector first:")
        print("  python data/option_chain_collector.py --symbol SPY")
        conn.close()
        return

    # Determine date range
    if args.days:
        start_date = (datetime.now() - timedelta(days=args.days)).strftime('%Y-%m-%d')
        end_date = None
    else:
        start_date = args.start
        end_date = args.end

    # Get available dates
    available_dates = get_available_dates(conn, args.symbol, start_date, end_date)
    print(f"\nProcessing {len(available_dates)} days with data...")

    if not available_dates:
        print("No dates to process in specified range.")
        conn.close()
        return

    # Process each date
    success = 0
    failed = 0

    for i, trade_date in enumerate(available_dates):
        pct = (i + 1) / len(available_dates) * 100
        print(f"\r  Progress: {pct:.1f}% ({i+1}/{len(available_dates)}) - {trade_date}", end='', flush=True)

        try:
            structure = calculate_gex_from_snapshots(conn, args.symbol, trade_date)
            if structure:
                insert_gex_structure(conn, structure)
                success += 1
            else:
                failed += 1
        except Exception as e:
            conn.rollback()
            failed += 1
            if failed <= 3:
                print(f"\n  Error on {trade_date}: {e}")

    print(f"\r  Progress: 100% ({len(available_dates)}/{len(available_dates)})")

    # Check results
    cursor.execute("SELECT COUNT(*) FROM gex_structure_daily WHERE symbol = %s", (args.symbol,))
    final_count = cursor.fetchone()[0]

    print("\n" + "-" * 70)
    print("RESULTS")
    print("-" * 70)
    print(f"  Processed: {len(available_dates)} days")
    print(f"  Success: {success}")
    print(f"  Failed: {failed}")
    print(f"  Total in gex_structure_daily: {final_count}")

    if final_count >= 100:
        print("\n  ** You now have enough data to train GEX ML models! **")
        print("  Run: python scripts/train_gex_probability_models.py")
    elif final_count > 0:
        print(f"\n  Need {100 - final_count} more days for ML training (minimum 100)")

    conn.close()
    print("\nDone!")


if __name__ == "__main__":
    main()
