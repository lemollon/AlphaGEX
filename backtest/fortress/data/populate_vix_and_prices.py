"""
Populate vix_history and underlying_prices tables from yfinance.

These tables are required by the FORTRESS backtest but are empty in the
ORAT backtest database. The ORAT options data has underlying_price per row,
but VIX needs its own table since the backtest hard-skips days without it.

Usage (on Render):
    pip install yfinance
    python backtest/fortress/data/populate_vix_and_prices.py 2>&1 | tee /tmp/populate_vix.txt
"""

import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

DB_URL = os.environ.get(
    'ORAT_DATABASE_URL',
    'postgresql://alphagex_user:e5DSVWnKceA16V5ysssLZCbqNE9ELRKi@dpg-d4quq1u3jp1c739oijb0-a.oregon-postgres.render.com/alphagex_backtest'
)


def main():
    import psycopg2
    import yfinance as yf

    conn = psycopg2.connect(DB_URL)
    cursor = conn.cursor()

    # ── Get the date range from ORAT data ──
    cursor.execute("""
        SELECT MIN(trade_date), MAX(trade_date)
        FROM orat_options_eod WHERE ticker = 'SPY'
    """)
    min_date, max_date = cursor.fetchone()
    print(f"ORAT date range: {min_date} → {max_date}")

    start_str = str(min_date)
    # Fetch a bit beyond max_date to be safe
    end_str = str(max_date + __import__('datetime').timedelta(days=5))

    # ══════════════════════════════════════════════════════════════════
    # 1. VIX HISTORY
    # ══════════════════════════════════════════════════════════════════
    print("\n=== Downloading VIX history from Yahoo Finance ===")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vix_history (
            trade_date DATE PRIMARY KEY,
            open NUMERIC(10,4),
            high NUMERIC(10,4),
            low NUMERIC(10,4),
            close NUMERIC(10,4)
        )
    """)
    conn.commit()

    vix = yf.download("^VIX", start=start_str, end=end_str, progress=False)
    if vix.empty:
        print("ERROR: yfinance returned no VIX data")
        return

    # Handle multi-level columns from yfinance
    if hasattr(vix.columns, 'levels') and len(vix.columns.levels) > 1:
        vix.columns = vix.columns.get_level_values(0)

    print(f"  Downloaded {len(vix)} VIX rows: {vix.index[0].date()} → {vix.index[-1].date()}")

    inserted = 0
    for idx, row in vix.iterrows():
        trade_date = idx.date() if hasattr(idx, 'date') else idx
        try:
            cursor.execute("""
                INSERT INTO vix_history (trade_date, open, high, low, close)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (trade_date) DO NOTHING
            """, (trade_date, float(row['Open']), float(row['High']),
                  float(row['Low']), float(row['Close'])))
            inserted += 1
        except Exception as e:
            print(f"  Skip {trade_date}: {e}")
            conn.rollback()
            continue

    conn.commit()
    print(f"  Inserted {inserted} VIX rows")

    # Verify
    cursor.execute("SELECT COUNT(*), MIN(trade_date), MAX(trade_date) FROM vix_history")
    count, vmin, vmax = cursor.fetchone()
    print(f"  vix_history: {count} rows, {vmin} → {vmax}")

    # ══════════════════════════════════════════════════════════════════
    # 2. UNDERLYING PRICES (SPY daily OHLC)
    # ══════════════════════════════════════════════════════════════════
    print("\n=== Downloading SPY price history from Yahoo Finance ===")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS underlying_prices (
            trade_date DATE NOT NULL,
            symbol VARCHAR(10) NOT NULL,
            open NUMERIC(12,4),
            high NUMERIC(12,4),
            low NUMERIC(12,4),
            close NUMERIC(12,4),
            PRIMARY KEY (trade_date, symbol)
        )
    """)
    conn.commit()

    spy = yf.download("SPY", start=start_str, end=end_str, progress=False)
    if spy.empty:
        print("ERROR: yfinance returned no SPY data")
        return

    if hasattr(spy.columns, 'levels') and len(spy.columns.levels) > 1:
        spy.columns = spy.columns.get_level_values(0)

    print(f"  Downloaded {len(spy)} SPY rows: {spy.index[0].date()} → {spy.index[-1].date()}")

    inserted = 0
    for idx, row in spy.iterrows():
        trade_date = idx.date() if hasattr(idx, 'date') else idx
        try:
            cursor.execute("""
                INSERT INTO underlying_prices (trade_date, symbol, open, high, low, close)
                VALUES (%s, 'SPY', %s, %s, %s, %s)
                ON CONFLICT (trade_date, symbol) DO NOTHING
            """, (trade_date, float(row['Open']), float(row['High']),
                  float(row['Low']), float(row['Close'])))
            inserted += 1
        except Exception as e:
            print(f"  Skip {trade_date}: {e}")
            conn.rollback()
            continue

    conn.commit()
    print(f"  Inserted {inserted} SPY rows")

    # Also do SPX (^GSPC)
    print("\n=== Downloading SPX price history from Yahoo Finance ===")

    spx = yf.download("^GSPC", start=start_str, end=end_str, progress=False)
    if not spx.empty:
        if hasattr(spx.columns, 'levels') and len(spx.columns.levels) > 1:
            spx.columns = spx.columns.get_level_values(0)

        print(f"  Downloaded {len(spx)} SPX rows: {spx.index[0].date()} → {spx.index[-1].date()}")

        inserted = 0
        for idx, row in spx.iterrows():
            trade_date = idx.date() if hasattr(idx, 'date') else idx
            try:
                cursor.execute("""
                    INSERT INTO underlying_prices (trade_date, symbol, open, high, low, close)
                    VALUES (%s, 'SPX', %s, %s, %s, %s)
                    ON CONFLICT (trade_date, symbol) DO NOTHING
                """, (trade_date, float(row['Open']), float(row['High']),
                      float(row['Low']), float(row['Close'])))
                inserted += 1
            except Exception as e:
                print(f"  Skip {trade_date}: {e}")
                conn.rollback()
                continue

        conn.commit()
        print(f"  Inserted {inserted} SPX rows")

    # ── Final verification ──
    print("\n=== VERIFICATION ===")
    for table in ['vix_history', 'underlying_prices']:
        cursor.execute(f"SELECT COUNT(*), MIN(trade_date), MAX(trade_date) FROM {table}")
        count, tmin, tmax = cursor.fetchone()
        print(f"  {table}: {count} rows, {tmin} → {tmax}")

    cursor.close()
    conn.close()
    print("\nDone. Backtest is now unblocked.")


if __name__ == '__main__':
    main()
