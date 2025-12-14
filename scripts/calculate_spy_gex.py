#!/usr/bin/env python3
"""Calculate and store SPY GEX data in gex_daily table"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2
from dotenv import load_dotenv
load_dotenv()

def main():
    db_url = os.getenv('ORAT_DATABASE_URL') or os.getenv('DATABASE_URL')
    conn = psycopg2.connect(db_url)
    cur = conn.cursor()

    print('Calculating SPY GEX data...')

    # Get all trading dates with SPY options
    cur.execute('''
        SELECT DISTINCT trade_date FROM orat_options_eod
        WHERE ticker = 'SPY' AND trade_date >= '2020-01-01'
        ORDER BY trade_date
    ''')
    dates = [row[0] for row in cur.fetchall()]
    print(f'Found {len(dates)} trading days with SPY options')

    if len(dates) == 0:
        print('No SPY data found!')
        return

    inserted = 0
    for i, trade_date in enumerate(dates):
        if i % 50 == 0:
            print(f'  Processing {i}/{len(dates)}: {trade_date}')

        # Get options data for this date (0-7 DTE)
        cur.execute('''
            SELECT strike, call_put, delta, gamma, open_interest, stock_price
            FROM orat_options_eod
            WHERE ticker = 'SPY'
              AND trade_date = %s
              AND dte <= 7
              AND open_interest > 0
              AND gamma IS NOT NULL
        ''', (trade_date,))

        options = cur.fetchall()
        if not options:
            continue

        spot_price = options[0][5] if options else 0
        if not spot_price:
            continue

        # Calculate GEX per strike
        strike_gex = {}
        total_call_gex = 0
        total_put_gex = 0

        for strike, cp, delta, gamma, oi, spot in options:
            gex = gamma * oi * 100 * (spot ** 2)

            if cp == 'C':
                total_call_gex += gex
            else:
                total_put_gex -= gex

            if strike not in strike_gex:
                strike_gex[strike] = 0
            strike_gex[strike] += gex if cp == 'C' else -gex

        net_gex = total_call_gex + total_put_gex

        # Find walls
        call_wall, max_call_gex = spot_price, 0
        put_wall, min_put_gex = spot_price, 0

        for strike, gex in strike_gex.items():
            if strike > spot_price and gex > max_call_gex:
                max_call_gex, call_wall = gex, strike
            if strike < spot_price and gex < min_put_gex:
                min_put_gex, put_wall = gex, strike

        flip_point = spot_price
        gex_normalized = net_gex / (spot_price ** 2) if spot_price > 0 else 0
        gex_regime = 'POSITIVE' if net_gex > 0 else 'NEGATIVE' if net_gex < 0 else 'NEUTRAL'
        distance_to_flip_pct = 0

        cur.execute('''
            INSERT INTO gex_daily (
                trade_date, symbol, spot_price, net_gex, call_gex, put_gex,
                call_wall, put_wall, flip_point, gex_normalized, gex_regime,
                distance_to_flip_pct, above_call_wall, below_put_wall, between_walls
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (symbol, trade_date) DO UPDATE SET
                spot_price = EXCLUDED.spot_price, net_gex = EXCLUDED.net_gex,
                call_gex = EXCLUDED.call_gex, put_gex = EXCLUDED.put_gex,
                call_wall = EXCLUDED.call_wall, put_wall = EXCLUDED.put_wall,
                gex_normalized = EXCLUDED.gex_normalized, gex_regime = EXCLUDED.gex_regime
        ''', (trade_date, 'SPY', spot_price, net_gex, total_call_gex, total_put_gex,
              call_wall, put_wall, flip_point, gex_normalized, gex_regime,
              distance_to_flip_pct, spot_price > call_wall, spot_price < put_wall,
              put_wall <= spot_price <= call_wall))
        inserted += 1

    conn.commit()
    print(f'\nInserted/updated {inserted} SPY GEX records')

    cur.execute('SELECT symbol, COUNT(*), MIN(trade_date), MAX(trade_date) FROM gex_daily GROUP BY symbol')
    print('\nGEX data available:')
    for row in cur.fetchall():
        print(f'  {row[0]}: {row[1]} days ({row[2]} to {row[3]})')

    conn.close()
    print('Done!')

if __name__ == '__main__':
    main()
