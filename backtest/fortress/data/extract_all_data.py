"""
FORTRESS Backtest - Comprehensive Data Extraction Script
=========================================================

Run this script with access to the Render database to extract ALL data
needed for the FORTRESS backtest into CSV files.

Usage:
    # Set the DATABASE_URL environment variable first
    export DATABASE_URL="postgresql://alphagex_user:e5DSVWnKceA16V5ysssLZCbqNE9ELRKi@dpg-d4quq1u3jp1c739oijb0-a.oregon-postgres.render.com/alphagex_backtest"

    python extract_all_data.py

Or run directly (uses DATABASE_URL from .env or environment):
    python extract_all_data.py
"""

import os
import sys
import csv
import time
from datetime import datetime

# Add project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Default to the backtest DB URL, fallback to env
DATABASE_URL = os.environ.get(
    'DATABASE_URL',
    'postgresql://alphagex_user:e5DSVWnKceA16V5ysssLZCbqNE9ELRKi@dpg-d4quq1u3jp1c739oijb0-a.oregon-postgres.render.com/alphagex_backtest'
)

DATA_DIR = os.path.dirname(os.path.abspath(__file__))


def get_connection():
    """Get a direct psycopg2 connection."""
    import psycopg2
    return psycopg2.connect(DATABASE_URL)


def extract_table(conn, query, filename, description):
    """Extract query results to CSV file."""
    filepath = os.path.join(DATA_DIR, filename)
    print(f"\n{'='*60}")
    print(f"  Extracting: {description}")
    print(f"  File: {filename}")

    start = time.time()
    cursor = conn.cursor()

    try:
        cursor.execute(query)
        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]

        with open(filepath, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(columns)
            writer.writerows(rows)

        elapsed = time.time() - start
        print(f"  Rows: {len(rows):,}")
        print(f"  Columns: {len(columns)}")
        print(f"  Time: {elapsed:.1f}s")
        print(f"  Size: {os.path.getsize(filepath) / 1024 / 1024:.1f} MB")
        return len(rows)
    except Exception as e:
        print(f"  ERROR: {e}")
        return 0
    finally:
        cursor.close()


def run_count_query(conn):
    """Run the row count / date range diagnostic query first."""
    print("\n" + "="*60)
    print("  PHASE 0: Data Inventory (row counts & date ranges)")
    print("="*60)

    tables_to_check = [
        ("orat_options_eod (SPY 0-7 DTE)",
         "SELECT COUNT(*), MIN(trade_date)::text, MAX(trade_date)::text FROM orat_options_eod WHERE ticker='SPY' AND dte BETWEEN 0 AND 7"),
        ("orat_options_eod (SPX 0-7 DTE)",
         "SELECT COUNT(*), MIN(trade_date)::text, MAX(trade_date)::text FROM orat_options_eod WHERE ticker='SPX' AND dte BETWEEN 0 AND 7"),
        ("price_history (SPY)",
         "SELECT COUNT(*), MIN(timestamp::date)::text, MAX(timestamp::date)::text FROM price_history WHERE symbol='SPY'"),
        ("gex_structure_daily (SPY)",
         "SELECT COUNT(*), MIN(trade_date)::text, MAX(trade_date)::text FROM gex_structure_daily WHERE symbol='SPY'"),
        ("gex_daily (SPY/SPX)",
         "SELECT COUNT(*), MIN(trade_date)::text, MAX(trade_date)::text FROM gex_daily"),
        ("options_chain_snapshots (SPY)",
         "SELECT COUNT(*), MIN(timestamp::date)::text, MAX(timestamp::date)::text FROM options_chain_snapshots WHERE symbol='SPY'"),
        ("regime_signals",
         "SELECT COUNT(*), MIN(timestamp::date)::text, MAX(timestamp::date)::text FROM regime_signals"),
        ("volatility_surface_snapshots",
         "SELECT COUNT(*), MIN(snapshot_time::date)::text, MAX(snapshot_time::date)::text FROM volatility_surface_snapshots"),
        ("gamma_history (SPY)",
         "SELECT COUNT(*), MIN(date)::text, MAX(date)::text FROM gamma_history WHERE symbol='SPY'"),
        ("watchtower_snapshots (SPY)",
         "SELECT COUNT(*), MIN(snapshot_time::date)::text, MAX(snapshot_time::date)::text FROM watchtower_snapshots WHERE symbol='SPY'"),
        ("argus_strikes",
         "SELECT COUNT(*), MIN(created_at::date)::text, MAX(created_at::date)::text FROM argus_strikes"),
        ("scan_activity (FORTRESS)",
         "SELECT COUNT(*), MIN(date)::text, MAX(date)::text FROM scan_activity WHERE bot_name='FORTRESS'"),
        ("scan_activity (ALL bots)",
         "SELECT COUNT(*), MIN(date)::text, MAX(date)::text FROM scan_activity"),
        ("prophet_predictions (FORTRESS)",
         "SELECT COUNT(*), MIN(trade_date)::text, MAX(trade_date)::text FROM prophet_predictions WHERE bot_name='FORTRESS'"),
        ("prophet_training_outcomes (FORTRESS)",
         "SELECT COUNT(*), MIN(trade_date)::text, MAX(trade_date)::text FROM prophet_training_outcomes WHERE bot_name='FORTRESS'"),
        ("vix_term_structure",
         "SELECT COUNT(*), MIN(timestamp::date)::text, MAX(timestamp::date)::text FROM vix_term_structure"),
        ("argus_predictions",
         "SELECT COUNT(*), MIN(prediction_date)::text, MAX(prediction_date)::text FROM argus_predictions"),
        ("argus_gamma_flips",
         "SELECT COUNT(*), MIN(flip_time::date)::text, MAX(flip_time::date)::text FROM argus_gamma_flips"),
        ("fortress_positions",
         "SELECT COUNT(*), MIN(created_at::date)::text, MAX(created_at::date)::text FROM fortress_positions"),
        ("fortress_daily_performance",
         "SELECT COUNT(*), MIN(date)::text, MAX(date)::text FROM fortress_daily_performance"),
    ]

    cursor = conn.cursor()
    results = []

    for name, query in tables_to_check:
        try:
            cursor.execute(query)
            row = cursor.fetchone()
            count, min_dt, max_dt = row
            results.append((name, count, min_dt or 'N/A', max_dt or 'N/A'))
            print(f"  {name:45s} | {count:>10,} rows | {min_dt or 'N/A'} → {max_dt or 'N/A'}")
        except Exception as e:
            results.append((name, 0, 'ERROR', str(e)[:50]))
            print(f"  {name:45s} | ERROR: {str(e)[:60]}")
            conn.rollback()

    cursor.close()

    # Save inventory to file
    with open(os.path.join(DATA_DIR, '_data_inventory.txt'), 'w') as f:
        f.write(f"FORTRESS Backtest Data Inventory\n")
        f.write(f"Generated: {datetime.now().isoformat()}\n")
        f.write(f"{'='*80}\n\n")
        for name, count, min_dt, max_dt in results:
            f.write(f"{name:45s} | {count:>10,} rows | {min_dt} → {max_dt}\n")

    return results


def main():
    print("="*60)
    print("  FORTRESS Backtest - Comprehensive Data Extraction")
    print(f"  Output: {DATA_DIR}")
    print(f"  Time: {datetime.now().isoformat()}")
    print("="*60)

    conn = get_connection()

    # =========================================================================
    # PHASE 0: Inventory
    # =========================================================================
    inventory = run_count_query(conn)

    # =========================================================================
    # PHASE 1: ORAT Options Data (Primary backtest data)
    # =========================================================================
    extract_table(conn,
        """
        SELECT trade_date, ticker, expiration_date, strike, option_type,
               call_bid, call_ask, call_mid, put_bid, put_ask, put_mid,
               delta, gamma, theta, vega, rho,
               call_iv, put_iv, underlying_price, dte,
               call_volume, put_volume, call_oi, put_oi
        FROM orat_options_eod
        WHERE ticker = 'SPY' AND dte BETWEEN 0 AND 7
        ORDER BY trade_date, expiration_date, strike
        """,
        "orat_spy_0_7dte.csv",
        "ORAT SPY Options (0-7 DTE) - Primary backtest data"
    )

    extract_table(conn,
        """
        SELECT trade_date, ticker, expiration_date, strike, option_type,
               call_bid, call_ask, call_mid, put_bid, put_ask, put_mid,
               delta, gamma, theta, vega, rho,
               call_iv, put_iv, underlying_price, dte,
               call_volume, put_volume, call_oi, put_oi
        FROM orat_options_eod
        WHERE ticker = 'SPX' AND dte BETWEEN 0 AND 7
        ORDER BY trade_date, expiration_date, strike
        """,
        "orat_spx_0_7dte.csv",
        "ORAT SPX Options (0-7 DTE)"
    )

    # =========================================================================
    # PHASE 2: Price History (Underlying for settlement)
    # =========================================================================
    extract_table(conn,
        """
        SELECT timestamp, symbol, timeframe, open, high, low, close, volume, vwap, data_source
        FROM price_history
        WHERE symbol = 'SPY'
        ORDER BY timestamp
        """,
        "price_history_spy.csv",
        "SPY Price History (all timeframes)"
    )

    # =========================================================================
    # PHASE 3: GEX Data (GEX-Protected IC feature columns)
    # =========================================================================
    extract_table(conn,
        """
        SELECT *
        FROM gex_structure_daily
        WHERE symbol IN ('SPY', 'SPX')
        ORDER BY trade_date, symbol
        """,
        "gex_structure_daily.csv",
        "GEX Structure Daily (walls, magnets, flip points)"
    )

    extract_table(conn,
        """
        SELECT *
        FROM gex_daily
        ORDER BY trade_date, symbol
        """,
        "gex_daily.csv",
        "GEX Daily (regime, walls, flip point)"
    )

    # =========================================================================
    # PHASE 4: Watchtower Data (Intraday gamma evolution)
    # =========================================================================
    extract_table(conn,
        """
        SELECT id, symbol, expiration_date, snapshot_time,
               spot_price, expected_move, vix,
               total_net_gamma, gamma_regime, previous_regime, regime_flipped,
               market_status
        FROM watchtower_snapshots
        WHERE symbol = 'SPY'
        ORDER BY snapshot_time
        """,
        "watchtower_snapshots_spy.csv",
        "Watchtower Gamma Snapshots (per-minute)"
    )

    # Argus strikes - this can be HUGE, so limit to key columns and sample
    extract_table(conn,
        """
        SELECT s.snapshot_id, s.strike, s.net_gamma, s.call_gamma, s.put_gamma,
               s.probability, s.roc_1min, s.roc_5min,
               s.is_magnet, s.magnet_rank, s.is_pin, s.is_danger, s.danger_type,
               ws.snapshot_time, ws.spot_price, ws.gamma_regime
        FROM argus_strikes s
        JOIN watchtower_snapshots ws ON s.snapshot_id = ws.id
        WHERE ws.symbol = 'SPY'
          AND (s.is_magnet = TRUE OR s.is_pin = TRUE OR s.is_danger = TRUE
               OR ABS(s.strike - ws.spot_price) / ws.spot_price < 0.03)
        ORDER BY ws.snapshot_time, s.strike
        """,
        "argus_strikes_filtered.csv",
        "Argus Strikes (magnets, pins, dangers, near-spot only to limit size)"
    )

    # =========================================================================
    # PHASE 5: Options Chain Snapshots (Intraday option pricing!)
    # =========================================================================
    extract_table(conn,
        """
        SELECT timestamp, symbol, expiration, strike, option_type,
               bid, ask, last, volume, open_interest,
               implied_volatility, delta, gamma, theta, vega,
               underlying_price
        FROM options_chain_snapshots
        WHERE symbol = 'SPY'
          AND (expiration - timestamp::date) BETWEEN 0 AND 5
        ORDER BY timestamp, expiration, strike
        """,
        "options_chain_snapshots_spy_0_5dte.csv",
        "Live Option Chain Snapshots (SPY 0-5 DTE, 15-min intervals)"
    )

    # =========================================================================
    # PHASE 6: Regime & Volatility Context
    # =========================================================================
    extract_table(conn,
        """
        SELECT *
        FROM regime_signals
        ORDER BY timestamp
        """,
        "regime_signals.csv",
        "Regime Signals (80+ columns per day)"
    )

    extract_table(conn,
        """
        SELECT *
        FROM volatility_surface_snapshots
        ORDER BY snapshot_time
        """,
        "volatility_surface_snapshots.csv",
        "Volatility Surface (IV, skew, term structure)"
    )

    extract_table(conn,
        """
        SELECT *
        FROM vix_term_structure
        ORDER BY timestamp
        """,
        "vix_term_structure.csv",
        "VIX Term Structure (futures curve)"
    )

    # =========================================================================
    # PHASE 7: FORTRESS Historical Decisions (Validation Data)
    # =========================================================================
    extract_table(conn,
        """
        SELECT *
        FROM scan_activity
        WHERE bot_name = 'FORTRESS'
        ORDER BY timestamp
        """,
        "scan_activity_fortress.csv",
        "FORTRESS Scan Activity (every decision with full context)"
    )

    extract_table(conn,
        """
        SELECT *
        FROM prophet_predictions
        WHERE bot_name = 'FORTRESS'
        ORDER BY trade_date
        """,
        "prophet_predictions_fortress.csv",
        "Prophet Predictions for FORTRESS (ML advice + outcomes)"
    )

    extract_table(conn,
        """
        SELECT *
        FROM prophet_training_outcomes
        WHERE bot_name = 'FORTRESS'
        ORDER BY trade_date
        """,
        "prophet_training_outcomes_fortress.csv",
        "Prophet Training Outcomes (features + outcomes for ML)"
    )

    # =========================================================================
    # PHASE 8: FORTRESS Positions & Performance
    # =========================================================================
    extract_table(conn,
        """
        SELECT *
        FROM fortress_positions
        ORDER BY created_at
        """,
        "fortress_positions.csv",
        "FORTRESS Historical Positions"
    )

    extract_table(conn,
        """
        SELECT *
        FROM fortress_daily_performance
        ORDER BY date
        """,
        "fortress_daily_performance.csv",
        "FORTRESS Daily Performance"
    )

    # =========================================================================
    # PHASE 9: Gamma Flips & Predictions (Watchtower ML)
    # =========================================================================
    extract_table(conn,
        """
        SELECT *
        FROM argus_gamma_flips
        ORDER BY flip_time
        """,
        "argus_gamma_flips.csv",
        "Gamma Flip Events (with price outcomes)"
    )

    extract_table(conn,
        """
        SELECT p.*, o.actual_close, o.actual_high, o.actual_low,
               o.pin_accuracy, o.pin_error, o.direction_correct, o.magnet_touched
        FROM argus_predictions p
        LEFT JOIN argus_outcomes o ON p.id = o.prediction_id
        ORDER BY p.prediction_date
        """,
        "argus_predictions_with_outcomes.csv",
        "Argus Predictions + Outcomes (pin, direction, magnet accuracy)"
    )

    # =========================================================================
    # PHASE 10: Gamma History (Intraday GEX snapshots)
    # =========================================================================
    extract_table(conn,
        """
        SELECT *
        FROM gamma_history
        WHERE symbol = 'SPY'
        ORDER BY timestamp
        """,
        "gamma_history_spy.csv",
        "Gamma History SPY (intraday GEX snapshots)"
    )

    # =========================================================================
    # SUMMARY
    # =========================================================================
    conn.close()

    print("\n" + "="*60)
    print("  EXTRACTION COMPLETE")
    print("="*60)

    total_size = 0
    for f in os.listdir(DATA_DIR):
        if f.endswith('.csv'):
            size = os.path.getsize(os.path.join(DATA_DIR, f))
            total_size += size
            print(f"  {f:50s} {size / 1024 / 1024:>8.1f} MB")

    print(f"\n  Total: {total_size / 1024 / 1024:.1f} MB")
    print(f"  Files saved to: {DATA_DIR}")
    print("\n  Next: Copy these files to the sandbox and run the backtest!")


if __name__ == '__main__':
    main()
