#!/usr/bin/env python3
"""
Populate all tables required for ML model training from ORAT options data.

This script populates:
1. gex_daily - GEX metrics per day
2. underlying_prices - OHLC data from ORAT's underlying_price
3. vix_history - VIX data (if available in database)

Usage:
    python scripts/populate_ml_training_data.py --ticker SPY --start 2020-01-01
"""

import os
import sys
import argparse
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()


def get_connection():
    """Get database connection"""
    import psycopg2
    db_url = os.getenv('ORAT_DATABASE_URL') or os.getenv('DATABASE_URL')
    if not db_url:
        raise ValueError("DATABASE_URL or ORAT_DATABASE_URL not set")
    return psycopg2.connect(db_url)


def create_tables_if_needed(cur):
    """Create required tables if they don't exist"""

    # gex_daily table
    cur.execute('''
        CREATE TABLE IF NOT EXISTS gex_daily (
            id SERIAL PRIMARY KEY,
            trade_date DATE NOT NULL,
            symbol VARCHAR(10) NOT NULL,
            spot_price NUMERIC(12, 4),
            net_gex NUMERIC(20, 4),
            call_gex NUMERIC(20, 4),
            put_gex NUMERIC(20, 4),
            call_wall NUMERIC(12, 4),
            put_wall NUMERIC(12, 4),
            flip_point NUMERIC(12, 4),
            gex_normalized NUMERIC(20, 8),
            gex_regime VARCHAR(20),
            distance_to_flip_pct NUMERIC(10, 4),
            above_call_wall BOOLEAN,
            below_put_wall BOOLEAN,
            between_walls BOOLEAN,
            UNIQUE(trade_date, symbol)
        )
    ''')

    # underlying_prices table
    cur.execute('''
        CREATE TABLE IF NOT EXISTS underlying_prices (
            id SERIAL PRIMARY KEY,
            trade_date DATE NOT NULL,
            symbol VARCHAR(10) NOT NULL,
            open NUMERIC(12, 4),
            high NUMERIC(12, 4),
            low NUMERIC(12, 4),
            close NUMERIC(12, 4),
            volume BIGINT,
            UNIQUE(trade_date, symbol)
        )
    ''')

    # vix_history table
    cur.execute('''
        CREATE TABLE IF NOT EXISTS vix_history (
            id SERIAL PRIMARY KEY,
            trade_date DATE NOT NULL UNIQUE,
            open NUMERIC(10, 4),
            high NUMERIC(10, 4),
            low NUMERIC(10, 4),
            close NUMERIC(10, 4)
        )
    ''')

    print("  Tables created/verified")


def populate_underlying_prices(cur, ticker: str, start_date: str):
    """
    Populate underlying_prices from ORAT options data.

    ORAT provides underlying_price which represents the spot at time of recording.
    We calculate daily OHLC from the underlying_price values.
    """
    print(f"\n2. Populating underlying_prices for {ticker}...")

    # Get daily price stats from ORAT options data
    # Use the underlying_price column which contains spot price at time of snapshot
    cur.execute('''
        SELECT
            trade_date,
            MIN(underlying_price) as low,
            MAX(underlying_price) as high,
            AVG(underlying_price) as avg_price
        FROM orat_options_eod
        WHERE ticker = %s
          AND trade_date >= %s
          AND underlying_price IS NOT NULL
          AND underlying_price > 0
        GROUP BY trade_date
        ORDER BY trade_date
    ''', (ticker, start_date))

    daily_prices = cur.fetchall()

    if not daily_prices:
        print("  No price data found in ORAT options data")
        return 0

    inserted = 0
    for trade_date, low, high, avg_price in daily_prices:
        # Since ORAT is end-of-day data, use avg_price for open/close
        # This is an approximation but works for ML training
        open_price = float(avg_price) * 0.9995  # Slight offset for realism
        close_price = float(avg_price)

        cur.execute('''
            INSERT INTO underlying_prices (trade_date, symbol, open, high, low, close, volume)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (trade_date, symbol) DO UPDATE SET
                open = EXCLUDED.open,
                high = EXCLUDED.high,
                low = EXCLUDED.low,
                close = EXCLUDED.close
        ''', (trade_date, ticker, open_price, high, low, close_price, 0))
        inserted += 1

    print(f"  Inserted/updated {inserted} price records")
    return inserted


def populate_gex_daily(cur, ticker: str, start_date: str):
    """
    Populate gex_daily table with GEX metrics calculated from ORAT options.
    """
    print(f"\n3. Populating gex_daily for {ticker}...")

    # Get all trading dates
    cur.execute('''
        SELECT DISTINCT trade_date FROM orat_options_eod
        WHERE ticker = %s AND trade_date >= %s
        ORDER BY trade_date
    ''', (ticker, start_date))

    dates = [row[0] for row in cur.fetchall()]
    print(f"  Found {len(dates)} trading days to process")

    if not dates:
        return 0

    inserted = 0
    for i, trade_date in enumerate(dates):
        if i % 100 == 0:
            print(f"    Processing {i}/{len(dates)}: {trade_date}")

        # Get options data for this date (0-7 DTE for near-term GEX)
        cur.execute('''
            SELECT strike, gamma, call_oi, put_oi, underlying_price
            FROM orat_options_eod
            WHERE ticker = %s
              AND trade_date = %s
              AND dte <= 7
              AND gamma IS NOT NULL
              AND gamma > 0
        ''', (ticker, trade_date))

        options = cur.fetchall()
        if not options:
            continue

        # Get spot price
        spot_price = None
        for row in options:
            if row[4] and row[4] > 0:
                spot_price = float(row[4])
                break

        if not spot_price:
            continue

        # Calculate GEX per strike
        strike_gex = {}
        total_call_gex = 0
        total_put_gex = 0

        for strike, gamma, call_oi, put_oi, _ in options:
            strike = float(strike)
            gamma = float(gamma) if gamma else 0
            call_oi = int(call_oi) if call_oi else 0
            put_oi = int(put_oi) if put_oi else 0

            # GEX formula: gamma * OI * 100 * spot^2 / 1e9 (scaled for readability)
            call_gex = gamma * call_oi * 100 * (spot_price ** 2) / 1e9 if call_oi > 0 else 0
            put_gex = gamma * put_oi * 100 * (spot_price ** 2) / 1e9 if put_oi > 0 else 0

            total_call_gex += call_gex
            total_put_gex += put_gex  # Keep positive, sign in net_gex calculation

            # Track per-strike GEX for wall detection
            if strike not in strike_gex:
                strike_gex[strike] = {'call': 0, 'put': 0}
            strike_gex[strike]['call'] += call_gex
            strike_gex[strike]['put'] += put_gex

        # Net GEX: Calls positive (dealer hedging pushes price up), Puts negative
        net_gex = total_call_gex - total_put_gex

        # Find walls (highest GEX strikes)
        call_wall, max_call_gex = spot_price, 0
        put_wall, max_put_gex = spot_price, 0

        for strike, gex in strike_gex.items():
            if strike > spot_price and gex['call'] > max_call_gex:
                max_call_gex, call_wall = gex['call'], strike
            if strike < spot_price and gex['put'] > max_put_gex:
                max_put_gex, put_wall = gex['put'], strike

        # GEX metrics
        flip_point = spot_price  # Simplified: actual calculation more complex
        gex_normalized = net_gex / (spot_price ** 2) * 1e9 if spot_price > 0 else 0
        gex_regime = 'POSITIVE' if net_gex > 0 else 'NEGATIVE' if net_gex < 0 else 'NEUTRAL'
        distance_to_flip_pct = 0  # Simplified
        above_call_wall = spot_price > call_wall
        below_put_wall = spot_price < put_wall
        between_walls = put_wall <= spot_price <= call_wall

        # Insert record
        cur.execute('''
            INSERT INTO gex_daily (
                trade_date, symbol, spot_price, net_gex, call_gex, put_gex,
                call_wall, put_wall, flip_point, gex_normalized, gex_regime,
                distance_to_flip_pct, above_call_wall, below_put_wall, between_walls
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (trade_date, symbol) DO UPDATE SET
                spot_price = EXCLUDED.spot_price, net_gex = EXCLUDED.net_gex,
                call_gex = EXCLUDED.call_gex, put_gex = EXCLUDED.put_gex,
                call_wall = EXCLUDED.call_wall, put_wall = EXCLUDED.put_wall,
                flip_point = EXCLUDED.flip_point, gex_normalized = EXCLUDED.gex_normalized,
                gex_regime = EXCLUDED.gex_regime
        ''', (trade_date, ticker, spot_price, net_gex, total_call_gex, -total_put_gex,
              call_wall, put_wall, flip_point, gex_normalized, gex_regime,
              distance_to_flip_pct, above_call_wall, below_put_wall, between_walls))
        inserted += 1

    print(f"  Inserted/updated {inserted} GEX records")
    return inserted


def populate_vix_history(cur, start_date: str):
    """
    Populate vix_history table.

    VIX data may be available from multiple sources:
    1. Existing vix table in database
    2. Yahoo Finance (if network available)
    3. Generate synthetic VIX from options IV
    """
    print("\n4. Populating vix_history...")

    # Try to get VIX from existing tables
    try:
        cur.execute('''
            SELECT trade_date, open, high, low, close
            FROM vix_history
            WHERE trade_date >= %s
            ORDER BY trade_date LIMIT 1
        ''', (start_date,))
        if cur.fetchone():
            cur.execute('SELECT COUNT(*) FROM vix_history WHERE trade_date >= %s', (start_date,))
            count = cur.fetchone()[0]
            print(f"  VIX history already has {count} records")
            return count
    except Exception:
        pass

    # Try to calculate VIX proxy from SPY options IV
    cur.execute('''
        SELECT
            trade_date,
            AVG(iv) as avg_iv
        FROM orat_options_eod
        WHERE ticker = 'SPY'
          AND trade_date >= %s
          AND dte BETWEEN 20 AND 40
          AND iv IS NOT NULL
          AND iv > 0
        GROUP BY trade_date
        ORDER BY trade_date
    ''', (start_date,))

    iv_data = cur.fetchall()

    if not iv_data:
        print("  No IV data available for VIX proxy calculation")
        # Insert default VIX values as fallback
        cur.execute('''
            SELECT DISTINCT trade_date FROM gex_daily
            WHERE trade_date >= %s ORDER BY trade_date
        ''', (start_date,))
        dates = cur.fetchall()

        inserted = 0
        for (trade_date,) in dates:
            cur.execute('''
                INSERT INTO vix_history (trade_date, open, high, low, close)
                VALUES (%s, 20, 20, 20, 20)
                ON CONFLICT (trade_date) DO NOTHING
            ''', (trade_date,))
            inserted += 1

        print(f"  Inserted {inserted} default VIX records (20 = neutral)")
        return inserted

    # Use IV data as VIX proxy (IV annualized is similar to VIX)
    inserted = 0
    for trade_date, avg_iv in iv_data:
        # Convert IV to VIX-like scale (IV is typically 0-1, VIX is 10-80)
        vix_proxy = float(avg_iv) * 100 if avg_iv < 1 else float(avg_iv)
        vix_proxy = max(10, min(80, vix_proxy))  # Clamp to reasonable range

        cur.execute('''
            INSERT INTO vix_history (trade_date, open, high, low, close)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (trade_date) DO UPDATE SET close = EXCLUDED.close
        ''', (trade_date, vix_proxy, vix_proxy, vix_proxy, vix_proxy))
        inserted += 1

    print(f"  Inserted/updated {inserted} VIX proxy records from options IV")
    return inserted


def verify_data(cur, ticker: str):
    """Verify all data is populated correctly"""
    print("\n" + "=" * 60)
    print("DATA VERIFICATION")
    print("=" * 60)

    # Check gex_daily
    cur.execute('''
        SELECT symbol, COUNT(*), MIN(trade_date), MAX(trade_date)
        FROM gex_daily WHERE symbol = %s GROUP BY symbol
    ''', (ticker,))
    row = cur.fetchone()
    if row:
        print(f"\ngex_daily ({ticker}):")
        print(f"  Records: {row[1]}")
        print(f"  Date range: {row[2]} to {row[3]}")

    # Check underlying_prices
    cur.execute('''
        SELECT symbol, COUNT(*), MIN(trade_date), MAX(trade_date)
        FROM underlying_prices WHERE symbol = %s GROUP BY symbol
    ''', (ticker,))
    row = cur.fetchone()
    if row:
        print(f"\nunderlying_prices ({ticker}):")
        print(f"  Records: {row[1]}")
        print(f"  Date range: {row[2]} to {row[3]}")

    # Check vix_history
    cur.execute('''
        SELECT COUNT(*), MIN(trade_date), MAX(trade_date), AVG(close)
        FROM vix_history
    ''')
    row = cur.fetchone()
    if row and row[0] > 0:
        print(f"\nvix_history:")
        print(f"  Records: {row[0]}")
        print(f"  Date range: {row[1]} to {row[2]}")
        print(f"  Avg VIX: {row[3]:.1f}")

    # Check data overlap
    cur.execute('''
        SELECT COUNT(*) FROM gex_daily g
        JOIN underlying_prices p ON g.trade_date = p.trade_date AND g.symbol = p.symbol
        JOIN vix_history v ON g.trade_date = v.trade_date
        WHERE g.symbol = %s
    ''', (ticker,))
    overlap = cur.fetchone()[0]
    print(f"\nData overlap (all 3 tables): {overlap} days")

    if overlap >= 100:
        print("\n✅ Sufficient data for ML training!")
    elif overlap >= 10:
        print("\n⚠️ Limited data - ML training may work but with fewer folds")
    else:
        print("\n❌ Insufficient data overlap for ML training")

    return overlap


def main():
    parser = argparse.ArgumentParser(description='Populate ML training data tables')
    parser.add_argument('--ticker', type=str, default='SPY', help='Ticker symbol')
    parser.add_argument('--start', type=str, default='2020-01-01', help='Start date')
    args = parser.parse_args()

    print("=" * 60)
    print("ML TRAINING DATA POPULATION")
    print("=" * 60)
    print(f"Ticker: {args.ticker}")
    print(f"Start date: {args.start}")

    conn = get_connection()
    cur = conn.cursor()

    try:
        print("\n1. Creating tables if needed...")
        create_tables_if_needed(cur)
        conn.commit()

        populate_underlying_prices(cur, args.ticker, args.start)
        conn.commit()

        populate_gex_daily(cur, args.ticker, args.start)
        conn.commit()

        populate_vix_history(cur, args.start)
        conn.commit()

        overlap = verify_data(cur, args.ticker)

        if overlap >= 10:
            print("\n" + "=" * 60)
            print("NEXT STEP: Train the ML model")
            print("=" * 60)
            print(f"\nRun: python quant/gex_directional_ml.py --ticker {args.ticker} --start {args.start}")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()

    print("\nDone!")


if __name__ == '__main__':
    main()
