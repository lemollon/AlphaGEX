#!/usr/bin/env python3
"""
Backfill all SPY data: prices, GEX calculations
Run on production server where database is accessible.
"""

import os
import sys
import requests
from datetime import datetime
from typing import Dict, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import psycopg2
except ImportError:
    print("Installing psycopg2...")
    os.system("pip install psycopg2-binary")
    import psycopg2

def get_db_connection():
    db_url = os.getenv('ORAT_DATABASE_URL') or os.getenv('DATABASE_URL')
    if not db_url:
        raise ValueError("Set ORAT_DATABASE_URL or DATABASE_URL")
    return psycopg2.connect(db_url)

def fetch_yahoo_data(symbol: str, start: str, end: str) -> List[Dict]:
    """Fetch from Yahoo Finance API"""
    start_ts = int(datetime.strptime(start, "%Y-%m-%d").timestamp())
    end_ts = int(datetime.strptime(end, "%Y-%m-%d").timestamp())

    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    params = {"period1": start_ts, "period2": end_ts, "interval": "1d"}
    headers = {"User-Agent": "Mozilla/5.0"}

    resp = requests.get(url, params=params, headers=headers)
    if resp.status_code != 200:
        print(f"Yahoo error: {resp.status_code}")
        return []

    data = resp.json()
    result = data.get("chart", {}).get("result", [])
    if not result:
        return []

    chart = result[0]
    timestamps = chart.get("timestamp", [])
    quote = chart.get("indicators", {}).get("quote", [{}])[0]

    records = []
    for i, ts in enumerate(timestamps):
        try:
            records.append({
                "date": datetime.fromtimestamp(ts).strftime("%Y-%m-%d"),
                "open": quote["open"][i],
                "high": quote["high"][i],
                "low": quote["low"][i],
                "close": quote["close"][i],
                "volume": quote["volume"][i] or 0
            })
        except:
            continue
    return records

def backfill_spy_prices(conn):
    """Backfill SPY prices to underlying_prices table"""
    print("\n=== Backfilling SPY Prices ===")

    cur = conn.cursor()

    # Check existing data range
    cur.execute("SELECT MIN(trade_date), MAX(trade_date) FROM underlying_prices WHERE symbol = 'SPY'")
    row = cur.fetchone()
    existing_start, existing_end = row[0], row[1]
    print(f"Existing SPY prices: {existing_start} to {existing_end}")

    # Get GEX date range to match
    cur.execute("SELECT MIN(trade_date), MAX(trade_date) FROM gex_daily WHERE symbol = 'SPX'")
    gex_start, gex_end = cur.fetchone()
    print(f"SPX GEX range: {gex_start} to {gex_end}")

    # Fetch SPY data from Yahoo
    start = str(gex_start) if gex_start else "2020-01-01"
    end = datetime.now().strftime("%Y-%m-%d")

    print(f"Fetching SPY from Yahoo ({start} to {end})...")
    data = fetch_yahoo_data("SPY", start, end)
    print(f"Got {len(data)} records")

    if not data:
        return 0

    # Insert into underlying_prices
    inserted = 0
    for rec in data:
        try:
            cur.execute("""
                INSERT INTO underlying_prices (trade_date, symbol, open, high, low, close, volume, source)
                VALUES (%s, 'SPY', %s, %s, %s, %s, %s, 'yahoo')
                ON CONFLICT (trade_date, symbol) DO UPDATE SET
                    open = EXCLUDED.open, high = EXCLUDED.high, low = EXCLUDED.low,
                    close = EXCLUDED.close, volume = EXCLUDED.volume
            """, (rec["date"], rec["open"], rec["high"], rec["low"], rec["close"], rec["volume"]))
            inserted += 1
        except Exception as e:
            pass

    conn.commit()
    print(f"Inserted/updated {inserted} SPY price records")
    return inserted

def calculate_spy_gex(conn):
    """Calculate SPY GEX from ORAT options data"""
    print("\n=== Calculating SPY GEX ===")

    cur = conn.cursor()

    # Get dates with SPY options but no GEX
    cur.execute("""
        SELECT DISTINCT trade_date FROM orat_options
        WHERE ticker = 'SPY'
        AND trade_date NOT IN (SELECT trade_date FROM gex_daily WHERE symbol = 'SPY')
        ORDER BY trade_date
    """)
    dates = [r[0] for r in cur.fetchall()]
    print(f"Found {len(dates)} dates needing SPY GEX calculation")

    if not dates:
        # Check if orat_options table exists and has SPY data
        cur.execute("SELECT COUNT(*) FROM orat_options WHERE ticker = 'SPY'")
        count = cur.fetchone()[0]
        print(f"SPY records in orat_options: {count}")
        if count == 0:
            print("No SPY options data in orat_options table")
            return 0

    inserted = 0
    for trade_date in dates:
        # Get spot price
        cur.execute("""
            SELECT stkPx FROM orat_options WHERE ticker = 'SPY' AND trade_date = %s LIMIT 1
        """, (trade_date,))
        row = cur.fetchone()
        if not row:
            continue
        spot_price = float(row[0])

        # Get options with gamma
        cur.execute("""
            SELECT strike, callPutFlag, gamma,
                   CASE WHEN callPutFlag = 'C' THEN callOpenInterest ELSE putOpenInterest END as oi
            FROM orat_options
            WHERE ticker = 'SPY' AND trade_date = %s AND gamma IS NOT NULL AND gamma > 0
        """, (trade_date,))
        options = cur.fetchall()

        if not options:
            continue

        total_call_gex, total_put_gex = 0, 0
        strike_gex = {}

        for strike, cp, gamma, oi in options:
            if not oi or oi <= 0:
                continue
            gex = float(gamma) * float(oi) * 100 * (spot_price ** 2)

            if cp == 'C':
                total_call_gex += gex
            else:
                total_put_gex -= gex  # Put GEX stored negative

            strike = float(strike)
            if strike not in strike_gex:
                strike_gex[strike] = 0
            strike_gex[strike] += gex if cp == 'C' else -gex

        net_gex = total_call_gex + total_put_gex

        # Find walls
        call_wall, max_call = spot_price, 0
        put_wall, max_put = spot_price, 0
        for s, g in strike_gex.items():
            if g > max_call:
                max_call, call_wall = g, s
            if g < max_put:
                max_put, put_wall = g, s

        flip_point = spot_price
        gex_normalized = net_gex / (spot_price ** 2) if spot_price else 0
        gex_regime = 'POSITIVE' if net_gex > 0 else 'NEGATIVE' if net_gex < 0 else 'NEUTRAL'

        cur.execute("""
            INSERT INTO gex_daily (
                trade_date, symbol, spot_price, net_gex, call_gex, put_gex,
                call_wall, put_wall, flip_point, gex_normalized, gex_regime,
                distance_to_flip_pct, above_call_wall, below_put_wall, between_walls
            ) VALUES (%s, 'SPY', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (trade_date, symbol) DO UPDATE SET
                spot_price = EXCLUDED.spot_price, net_gex = EXCLUDED.net_gex,
                call_gex = EXCLUDED.call_gex, put_gex = EXCLUDED.put_gex,
                call_wall = EXCLUDED.call_wall, put_wall = EXCLUDED.put_wall
        """, (trade_date, spot_price, net_gex, total_call_gex, total_put_gex,
              call_wall, put_wall, flip_point, gex_normalized, gex_regime,
              0, spot_price > call_wall, spot_price < put_wall, put_wall <= spot_price <= call_wall))
        inserted += 1

        if inserted % 100 == 0:
            print(f"  Processed {inserted} dates...")
            conn.commit()

    conn.commit()
    print(f"Inserted/updated {inserted} SPY GEX records")
    return inserted

def show_status(conn):
    """Show data status"""
    print("\n=== Data Status ===")
    cur = conn.cursor()

    # underlying_prices
    print("\nunderlying_prices:")
    cur.execute("SELECT symbol, COUNT(*), MIN(trade_date), MAX(trade_date) FROM underlying_prices GROUP BY symbol ORDER BY symbol")
    for row in cur.fetchall():
        print(f"  {row[0]}: {row[1]} records ({row[2]} to {row[3]})")

    # gex_daily
    print("\ngex_daily:")
    cur.execute("SELECT symbol, COUNT(*), MIN(trade_date), MAX(trade_date) FROM gex_daily GROUP BY symbol ORDER BY symbol")
    for row in cur.fetchall():
        print(f"  {row[0]}: {row[1]} records ({row[2]} to {row[3]})")

    # vix_history
    print("\nvix_history:")
    cur.execute("SELECT COUNT(*), MIN(trade_date), MAX(trade_date) FROM vix_history")
    row = cur.fetchone()
    print(f"  VIX: {row[0]} records ({row[1]} to {row[2]})")

def main():
    print("=" * 60)
    print("SPY Data Backfill - Prices + GEX")
    print("=" * 60)

    conn = get_db_connection()

    # Show initial status
    show_status(conn)

    # Backfill SPY prices
    backfill_spy_prices(conn)

    # Calculate SPY GEX
    calculate_spy_gex(conn)

    # Show final status
    show_status(conn)

    conn.close()
    print("\nDone!")

if __name__ == "__main__":
    main()
