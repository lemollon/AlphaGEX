#!/usr/bin/env python3
"""
Populate GEX Structure Data for ML Training

Stores per-strike gamma profiles to enable pattern recognition:
- Full gamma bar chart structure (per-strike data)
- Magnet identification (largest gamma strikes)
- Flip points (where net gamma crosses zero)
- OHLC price data for training labels

The model learns: Given gamma structure at open → where does price close?

Usage:
    python scripts/populate_gex_structures.py --symbol SPY
    python scripts/populate_gex_structures.py --start 2022-01-01 --end 2024-12-31
    python scripts/populate_gex_structures.py --show-structure 2024-01-15
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


def drop_tables(conn):
    """Drop existing GEX tables (for schema migration)"""
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS gex_strikes CASCADE")
    cursor.execute("DROP TABLE IF EXISTS gex_structure_daily CASCADE")
    conn.commit()
    print("✓ Dropped existing gex_strikes and gex_structure_daily tables")


def create_tables(conn):
    """Create tables for GEX structure data"""
    cursor = conn.cursor()

    # Table 1: Per-strike gamma data (the bar chart)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS gex_strikes (
            id SERIAL PRIMARY KEY,
            trade_date DATE NOT NULL,
            symbol VARCHAR(10) NOT NULL,
            strike NUMERIC(12,2) NOT NULL,

            -- Gamma by type
            call_gamma NUMERIC(20,2),      -- Call gamma exposure at this strike
            put_gamma NUMERIC(20,2),       -- Put gamma exposure (negative)
            net_gamma NUMERIC(20,2),       -- call + put (net at strike)

            -- Open interest context
            call_oi INTEGER,
            put_oi INTEGER,

            -- Relative to spot
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

            -- Price data (for training labels)
            spot_open NUMERIC(12,4),
            spot_high NUMERIC(12,4),
            spot_low NUMERIC(12,4),
            spot_close NUMERIC(12,4),

            -- Aggregates
            total_call_gamma NUMERIC(20,2),
            total_put_gamma NUMERIC(20,2),
            net_gamma NUMERIC(20,2),

            -- Key levels
            flip_point NUMERIC(12,4),          -- Where net gamma = 0
            flip_point_2 NUMERIC(12,4),        -- Second flip if exists

            -- Magnets (top 3 largest absolute gamma strikes)
            magnet_1_strike NUMERIC(12,2),
            magnet_1_gamma NUMERIC(20,2),
            magnet_2_strike NUMERIC(12,2),
            magnet_2_gamma NUMERIC(20,2),
            magnet_3_strike NUMERIC(12,2),
            magnet_3_gamma NUMERIC(20,2),

            -- Traditional walls
            call_wall NUMERIC(12,4),           -- Highest call gamma above spot
            put_wall NUMERIC(12,4),            -- Highest put gamma below spot

            -- Structure features (for ML)
            gamma_above_spot NUMERIC(20,2),    -- Total gamma above open
            gamma_below_spot NUMERIC(20,2),    -- Total gamma below open
            gamma_imbalance_pct NUMERIC(10,4), -- (above-below)/(above+below)

            num_magnets_above INTEGER,         -- Magnets above spot
            num_magnets_below INTEGER,         -- Magnets below spot

            nearest_magnet_strike NUMERIC(12,2),
            nearest_magnet_distance_pct NUMERIC(10,4),

            open_to_flip_distance_pct NUMERIC(10,4),
            open_in_pin_zone BOOLEAN,          -- Between two large magnets?

            -- Raw outcomes (NO BIAS - let the data speak)
            price_open NUMERIC(12,4),          -- Open price
            price_close NUMERIC(12,4),         -- Close price
            price_high NUMERIC(12,4),          -- High price
            price_low NUMERIC(12,4),           -- Low price
            price_change_pct NUMERIC(10,4),    -- (close-open)/open * 100
            price_range_pct NUMERIC(10,4),     -- (high-low)/open * 100

            -- Raw distances at close (for model to learn from)
            close_distance_to_flip_pct NUMERIC(10,4),      -- How far close was from flip
            close_distance_to_magnet1_pct NUMERIC(10,4),   -- How far close was from magnet 1
            close_distance_to_magnet2_pct NUMERIC(10,4),   -- How far close was from magnet 2
            close_distance_to_call_wall_pct NUMERIC(10,4), -- How far close was from call wall
            close_distance_to_put_wall_pct NUMERIC(10,4),  -- How far close was from put wall

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
    print("✓ Created gex_strikes and gex_structure_daily tables")


def get_ohlc_for_date(conn, symbol: str, trade_date: str) -> Optional[Dict]:
    """Get OHLC price data for a date"""
    cursor = conn.cursor()

    # Try to get from orat_options_eod (underlying_price)
    ticker = 'SPX' if symbol == 'SPX' else 'SPY'

    cursor.execute("""
        SELECT DISTINCT underlying_price
        FROM orat_options_eod
        WHERE ticker = %s AND trade_date = %s
        LIMIT 1
    """, (ticker, trade_date))

    row = cursor.fetchone()
    if row:
        # We only have one price from options data, use as proxy
        price = float(row[0])
        return {
            'open': price,
            'high': price * 1.005,  # Estimate
            'low': price * 0.995,   # Estimate
            'close': price
        }

    return None


def get_ohlc_from_yahoo(symbol: str, trade_date: str) -> Optional[Dict]:
    """Get OHLC from Yahoo Finance"""
    try:
        import yfinance as yf
        from datetime import datetime, timedelta

        ticker_map = {'SPX': '^GSPC', 'SPY': 'SPY'}
        ticker = ticker_map.get(symbol, symbol)

        dt = datetime.strptime(trade_date, '%Y-%m-%d')
        start = dt
        end = dt + timedelta(days=1)

        data = yf.download(ticker, start=start, end=end, progress=False)

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


# Global cache for OHLC data
_ohlc_cache = {}


def prefetch_ohlc_data(symbol: str, start_date: str, end_date: str) -> int:
    """
    Pre-fetch all OHLC data for a symbol in bulk.
    Much faster than fetching one day at a time.
    Returns number of days fetched.
    """
    global _ohlc_cache
    import yfinance as yf

    ticker_map = {'SPX': '^GSPC', 'SPY': 'SPY'}
    ticker = ticker_map.get(symbol, symbol)

    print(f"  Fetching OHLC data for {symbol} ({start_date} to {end_date})...")

    try:
        data = yf.download(ticker, start=start_date, end=end_date, progress=False)

        if len(data) == 0:
            print(f"  WARNING: No OHLC data returned for {symbol}")
            return 0

        count = 0
        # Handle multi-level columns from newer yfinance versions
        if hasattr(data.columns, 'levels'):
            data.columns = data.columns.droplevel(1)

        for date, row in data.iterrows():
            date_str = date.strftime('%Y-%m-%d')
            cache_key = f"{symbol}_{date_str}"
            # Handle both scalar and Series values
            def safe_float(val):
                if hasattr(val, 'iloc'):
                    return float(val.iloc[0])
                return float(val)
            _ohlc_cache[cache_key] = {
                'open': safe_float(row['Open']),
                'high': safe_float(row['High']),
                'low': safe_float(row['Low']),
                'close': safe_float(row['Close'])
            }
            count += 1

        print(f"  ✓ Cached {count} days of OHLC data for {symbol}")
        return count
    except Exception as e:
        print(f"  ERROR fetching OHLC for {symbol}: {e}")
        return 0


def get_cached_ohlc(symbol: str, trade_date: str) -> Optional[Dict]:
    """Get OHLC from cache, falling back to Yahoo Finance if not cached"""
    global _ohlc_cache
    cache_key = f"{symbol}_{trade_date}"

    if cache_key in _ohlc_cache:
        return _ohlc_cache[cache_key]

    # Fallback to single fetch if not cached
    return get_ohlc_from_yahoo(symbol, trade_date)


def calculate_gex_structure(conn, symbol: str, trade_date: str, dte_max: int = 7) -> Optional[Dict]:
    """
    Calculate complete GEX structure for a date.

    Returns per-strike data and summary with magnets/flips.
    """
    cursor = conn.cursor()

    ticker = 'SPX' if symbol == 'SPX' else 'SPY'

    # Get all options data for this date
    # Schema: each row has strike with both call_oi and put_oi
    cursor.execute("""
        SELECT
            strike,
            gamma,
            call_oi,
            put_oi,
            underlying_price
        FROM orat_options_eod
        WHERE ticker = %s
        AND trade_date = %s
        AND dte <= %s
        AND dte >= 0
        AND gamma IS NOT NULL
        AND gamma > 0
        AND (call_oi > 0 OR put_oi > 0)
        ORDER BY strike
    """, (ticker, trade_date, dte_max))

    rows = cursor.fetchall()

    if not rows:
        return None

    # Get spot price and OHLC (use cached data for bulk operations)
    spot_price = float(rows[0][4])
    ohlc = get_cached_ohlc(symbol, trade_date)
    if not ohlc:
        # Fallback: use spot_price with estimated range (not ideal but better than 0)
        ohlc = {'open': spot_price, 'high': spot_price * 1.005, 'low': spot_price * 0.995, 'close': spot_price}

    spot_open = ohlc['open']

    # Build per-strike gamma
    # Each row has both call and put OI, so we calculate both GEX values per strike
    strike_data = {}  # strike -> {call_gamma, put_gamma, net_gamma, call_oi, put_oi}

    for row in rows:
        strike = float(row[0])
        gamma = float(row[1])
        call_oi = int(row[2]) if row[2] else 0
        put_oi = int(row[3]) if row[3] else 0

        # GEX = gamma × OI × 100 × spot²  (using spot² like kronos_gex_calculator)
        call_gex = gamma * call_oi * 100 * (spot_open ** 2) if call_oi > 0 else 0
        put_gex = gamma * put_oi * 100 * (spot_open ** 2) if put_oi > 0 else 0

        # Net GEX = call - put (puts have negative effect on price)
        net_gex = call_gex - put_gex

        if strike not in strike_data:
            strike_data[strike] = {
                'call_gamma': 0, 'put_gamma': 0, 'net_gamma': 0,
                'call_oi': 0, 'put_oi': 0
            }

        # Aggregate (in case multiple expirations have same strike)
        strike_data[strike]['call_gamma'] += call_gex
        strike_data[strike]['put_gamma'] += -put_gex  # Store as negative for puts
        strike_data[strike]['net_gamma'] += net_gex
        strike_data[strike]['call_oi'] += call_oi
        strike_data[strike]['put_oi'] += put_oi

    # Find magnets (top 3 by absolute net gamma)
    sorted_by_gamma = sorted(
        strike_data.items(),
        key=lambda x: abs(x[1]['net_gamma']),
        reverse=True
    )

    magnets = []
    for strike, data in sorted_by_gamma[:5]:  # Top 5 candidates
        magnets.append({
            'strike': strike,
            'gamma': data['net_gamma'],
            'abs_gamma': abs(data['net_gamma'])
        })

    # Find flip points (where net gamma crosses zero)
    flip_points = []
    sorted_strikes = sorted(strike_data.keys())

    for i in range(len(sorted_strikes) - 1):
        s1, s2 = sorted_strikes[i], sorted_strikes[i+1]
        net1 = strike_data[s1]['net_gamma']
        net2 = strike_data[s2]['net_gamma']

        # Sign change = flip point
        if (net1 > 0 and net2 < 0) or (net1 < 0 and net2 > 0):
            # Linear interpolation
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

    # Pin zone detection (between two large magnets)
    in_pin_zone = False
    if len(magnets) >= 2:
        m1, m2 = magnets[0]['strike'], magnets[1]['strike']
        low_magnet, high_magnet = min(m1, m2), max(m1, m2)
        if low_magnet < spot_open < high_magnet:
            in_pin_zone = True

    # Raw outcomes - NO BIAS, just measurements
    price_change_pct = (ohlc['close'] - ohlc['open']) / ohlc['open'] * 100
    price_range_pct = (ohlc['high'] - ohlc['low']) / ohlc['open'] * 100

    # Raw distances at close (let model learn what these mean)
    close_distance_to_flip = ((ohlc['close'] - flip_point) / ohlc['close'] * 100) if flip_point else None

    close_distance_to_magnet1 = None
    close_distance_to_magnet2 = None
    if len(magnets) > 0:
        close_distance_to_magnet1 = (ohlc['close'] - magnets[0]['strike']) / ohlc['close'] * 100
    if len(magnets) > 1:
        close_distance_to_magnet2 = (ohlc['close'] - magnets[1]['strike']) / ohlc['close'] * 100

    close_distance_to_call_wall = ((ohlc['close'] - call_wall) / ohlc['close'] * 100) if call_wall else None
    close_distance_to_put_wall = ((ohlc['close'] - put_wall) / ohlc['close'] * 100) if put_wall else None

    return {
        'strike_data': strike_data,
        'summary': {
            'trade_date': trade_date,
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
            # Raw outcomes - NO BIAS
            'price_open': ohlc['open'],
            'price_close': ohlc['close'],
            'price_high': ohlc['high'],
            'price_low': ohlc['low'],
            'price_change_pct': price_change_pct,
            'price_range_pct': price_range_pct,
            # Raw distances at close
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


def show_structure(conn, symbol: str, trade_date: str):
    """Display gamma structure for a specific date"""
    cursor = conn.cursor()

    # Get summary
    cursor.execute("""
        SELECT * FROM gex_structure_daily
        WHERE symbol = %s AND trade_date = %s
    """, (symbol, trade_date))

    columns = [desc[0] for desc in cursor.description]
    row = cursor.fetchone()

    if not row:
        print(f"No data for {symbol} on {trade_date}")
        return

    summary = dict(zip(columns, row))

    # Get strike data
    cursor.execute("""
        SELECT strike, call_gamma, put_gamma, net_gamma
        FROM gex_strikes
        WHERE symbol = %s AND trade_date = %s
        ORDER BY strike
    """, (symbol, trade_date))

    strikes = cursor.fetchall()

    print("\n" + "=" * 80)
    print(f"GEX STRUCTURE: {symbol} on {trade_date}")
    print("=" * 80)

    print(f"\n📊 PRICE")
    print(f"   Open:  ${summary['spot_open']:,.2f}")
    print(f"   High:  ${summary['spot_high']:,.2f}")
    print(f"   Low:   ${summary['spot_low']:,.2f}")
    print(f"   Close: ${summary['spot_close']:,.2f}")
    print(f"   Change: {summary['price_change_pct']:+.2f}%")
    print(f"   Range:  {summary['price_range_pct']:.2f}%")

    print(f"\n🧲 KEY LEVELS")
    print(f"   Flip Point:  ${summary['flip_point']:,.2f}" if summary['flip_point'] else "   Flip Point:  N/A")
    print(f"   Call Wall:   ${summary['call_wall']:,.2f}" if summary['call_wall'] else "   Call Wall:   N/A")
    print(f"   Put Wall:    ${summary['put_wall']:,.2f}" if summary['put_wall'] else "   Put Wall:    N/A")

    print(f"\n🎯 MAGNETS (Top 3)")
    if summary['magnet_1_strike']:
        print(f"   1. ${summary['magnet_1_strike']:,.0f} → {summary['magnet_1_gamma']/1e9:+.2f}B gamma")
    if summary['magnet_2_strike']:
        print(f"   2. ${summary['magnet_2_strike']:,.0f} → {summary['magnet_2_gamma']/1e9:+.2f}B gamma")
    if summary['magnet_3_strike']:
        print(f"   3. ${summary['magnet_3_strike']:,.0f} → {summary['magnet_3_gamma']/1e9:+.2f}B gamma")

    print(f"\n📈 STRUCTURE FEATURES")
    print(f"   Gamma Above Spot: ${summary['gamma_above_spot']/1e9:+.2f}B")
    print(f"   Gamma Below Spot: ${summary['gamma_below_spot']/1e9:+.2f}B")
    print(f"   Imbalance: {summary['gamma_imbalance_pct']:+.1f}%")
    print(f"   In Pin Zone: {'YES' if summary['open_in_pin_zone'] else 'NO'}")
    print(f"   Nearest Magnet: ${summary['nearest_magnet_strike']:,.0f} ({summary['nearest_magnet_distance_pct']:.2f}% away)" if summary['nearest_magnet_strike'] else "")

    print(f"\n📍 DISTANCES AT CLOSE (raw)")
    if summary['close_distance_to_flip_pct'] is not None:
        print(f"   To Flip Point: {summary['close_distance_to_flip_pct']:+.2f}%")
    if summary['close_distance_to_magnet1_pct'] is not None:
        print(f"   To Magnet #1:  {summary['close_distance_to_magnet1_pct']:+.2f}%")
    if summary['close_distance_to_magnet2_pct'] is not None:
        print(f"   To Magnet #2:  {summary['close_distance_to_magnet2_pct']:+.2f}%")
    if summary['close_distance_to_call_wall_pct'] is not None:
        print(f"   To Call Wall:  {summary['close_distance_to_call_wall_pct']:+.2f}%")
    if summary['close_distance_to_put_wall_pct'] is not None:
        print(f"   To Put Wall:   {summary['close_distance_to_put_wall_pct']:+.2f}%")

    # ASCII bar chart
    print(f"\n📊 GAMMA BAR CHART (strikes near spot)")
    print("-" * 60)

    spot = summary['spot_open']
    nearby_strikes = [(s, cg, pg, ng) for s, cg, pg, ng in strikes
                      if abs(s - spot) / spot < 0.03]  # Within 3%

    if nearby_strikes:
        max_gamma = max(abs(ng) for _, _, _, ng in nearby_strikes)
        scale = 30 / max_gamma if max_gamma > 0 else 1

        for strike, call_g, put_g, net_g in nearby_strikes:
            bar_len = int(abs(net_g) * scale)
            marker = ""

            if summary['flip_point'] and abs(strike - summary['flip_point']) < 5:
                marker = " ← FLIP"
            elif strike == summary['magnet_1_strike']:
                marker = " ← MAGNET #1"
            elif strike == summary['magnet_2_strike']:
                marker = " ← MAGNET #2"

            if abs(strike - spot) < 2:
                marker += " [SPOT]"

            if net_g >= 0:
                bar = "+" * bar_len
                print(f"   {strike:>7.0f} |{bar:<30} {net_g/1e9:+.2f}B{marker}")
            else:
                bar = "-" * bar_len
                print(f"   {strike:>7.0f} |{bar:<30} {net_g/1e9:+.2f}B{marker}")

    print("=" * 80)


def get_available_dates(conn, symbol: str, start_date: str = None, end_date: str = None) -> List[str]:
    """Get list of dates with options data"""
    cursor = conn.cursor()
    ticker = 'SPX' if symbol == 'SPX' else 'SPY'

    query = "SELECT DISTINCT trade_date FROM orat_options_eod WHERE ticker = %s"
    params = [ticker]

    if start_date:
        query += " AND trade_date >= %s"
        params.append(start_date)
    if end_date:
        query += " AND trade_date <= %s"
        params.append(end_date)

    query += " ORDER BY trade_date"
    cursor.execute(query, params)

    return [row[0].strftime('%Y-%m-%d') for row in cursor.fetchall()]


def main():
    parser = argparse.ArgumentParser(description='Populate GEX Structure Data')
    parser.add_argument('--start', type=str, help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, help='End date (YYYY-MM-DD)')
    parser.add_argument('--symbol', type=str, choices=['SPX', 'SPY'], help='Symbol (default: both)')
    parser.add_argument('--show-structure', type=str, metavar='DATE', help='Show structure for a specific date')
    parser.add_argument('--force', action='store_true', help='Recalculate existing dates')
    parser.add_argument('--recreate-tables', action='store_true', help='Drop and recreate tables (required for schema changes)')

    args = parser.parse_args()

    print("Connecting to database...")
    conn = get_connection()

    # Recreate tables if requested (for schema migration)
    if args.recreate_tables:
        print("Recreating tables with new schema...")
        drop_tables(conn)

    # Create tables
    create_tables(conn)

    # Show structure for specific date
    if args.show_structure:
        symbol = args.symbol or 'SPY'
        show_structure(conn, symbol, args.show_structure)
        conn.close()
        return

    # Populate data
    symbols = [args.symbol] if args.symbol else ['SPX', 'SPY']

    for symbol in symbols:
        print(f"\n{'='*60}")
        print(f"Processing {symbol}")
        print('='*60)

        available_dates = get_available_dates(conn, symbol, args.start, args.end)
        print(f"Found {len(available_dates)} dates with options data")

        if not available_dates:
            continue

        # Pre-fetch OHLC data in bulk (much faster than per-date fetching)
        start_dt = available_dates[0]
        end_dt = available_dates[-1]
        prefetch_ohlc_data(symbol, start_dt, end_dt)

        success = 0
        failed = 0
        first_error_shown = False

        for i, trade_date in enumerate(available_dates):
            if i % 25 == 0:
                pct = (i / len(available_dates)) * 100
                print(f"\r  Processing: {pct:.1f}% ({i}/{len(available_dates)})", end='', flush=True)

            try:
                structure = calculate_gex_structure(conn, symbol, trade_date)
                if structure:
                    insert_gex_structure(conn, structure)
                    success += 1
                else:
                    failed += 1
            except Exception as e:
                # Rollback transaction to recover from error state
                conn.rollback()
                failed += 1
                # Show first error with full details for debugging
                if not first_error_shown:
                    import traceback
                    print(f"\n  FIRST ERROR on {trade_date}: {e}")
                    traceback.print_exc()
                    first_error_shown = True

        print(f"\r  Processing: 100% ({len(available_dates)}/{len(available_dates)})")
        print(f"  ✓ Success: {success}, ✗ Failed: {failed}")

    conn.close()
    print("\n✓ Done!")


if __name__ == "__main__":
    main()
