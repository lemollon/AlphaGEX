#!/usr/bin/env python3
"""
FULL DATABASE AUDIT SCRIPT

Run this script to get a complete picture of your database state.

USAGE:
    # On Render (Shell tab):
    python scripts/full_database_audit.py

    # Locally:
    export DATABASE_URL="postgresql://alphagex_user:PASSWORD@host/alphagex"
    python scripts/full_database_audit.py
"""

import os
import sys
from datetime import datetime, timedelta

# Try to use the DATABASE_URL
DATABASE_URL = os.environ.get('DATABASE_URL')

if not DATABASE_URL:
    print("❌ DATABASE_URL not set!")
    print("Set it with: export DATABASE_URL='postgresql://...'")
    sys.exit(1)

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    print("Installing psycopg2-binary...")
    os.system("pip install psycopg2-binary")
    import psycopg2
    import psycopg2.extras

def run_audit():
    print("=" * 100)
    print("ALPHAGEX DATABASE AUDIT - FULL REPORT")
    print("=" * 100)
    print(f"Time: {datetime.now()}")
    print(f"Database: {DATABASE_URL.split('@')[1].split('/')[0] if '@' in DATABASE_URL else 'Unknown'}")
    print("=" * 100)

    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        print("\n✅ DATABASE CONNECTION SUCCESSFUL\n")
    except Exception as e:
        print(f"\n❌ DATABASE CONNECTION FAILED: {e}")
        sys.exit(1)

    # =========================================================================
    # PHASE 1: Get all tables
    # =========================================================================
    cursor.execute("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
        ORDER BY table_name
    """)
    tables = [row[0] for row in cursor.fetchall()]

    print(f"TOTAL TABLES FOUND: {len(tables)}")
    print("=" * 100)

    # =========================================================================
    # PHASE 2: Check each table
    # =========================================================================
    populated = []
    empty = []
    errors = []

    print(f"\n{'TABLE NAME':<45} | {'ROWS':>10} | {'LATEST DATA':>25} | STATUS")
    print("-" * 100)

    for table in tables:
        try:
            # Get row count
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]

            # Try to get latest timestamp
            latest = "N/A"
            for col in ['timestamp', 'created_at', 'updated_at', 'date', 'entry_date']:
                try:
                    cursor.execute(f"SELECT MAX({col}) FROM {table}")
                    result = cursor.fetchone()[0]
                    if result:
                        latest = str(result)[:19]
                        break
                except:
                    continue

            status = "✅ HAS DATA" if count > 0 else "❌ EMPTY"
            print(f"{table:<45} | {count:>10} | {latest:>25} | {status}")

            if count > 0:
                populated.append((table, count, latest))
            else:
                empty.append(table)

        except Exception as e:
            errors.append((table, str(e)))
            print(f"{table:<45} | ERROR: {str(e)[:40]}")

    # =========================================================================
    # PHASE 3: Summary
    # =========================================================================
    print("\n" + "=" * 100)
    print("SUMMARY")
    print("=" * 100)

    print(f"\n✅ TABLES WITH DATA ({len(populated)} tables):")
    print("-" * 60)
    for t, c, l in sorted(populated, key=lambda x: -x[1]):
        days_old = ""
        try:
            if l != "N/A":
                from datetime import datetime
                last_dt = datetime.fromisoformat(l.replace('Z', ''))
                age = (datetime.now() - last_dt).days
                if age == 0:
                    days_old = "(TODAY)"
                elif age == 1:
                    days_old = "(yesterday)"
                elif age < 7:
                    days_old = f"({age} days ago)"
                else:
                    days_old = f"({age} days old - STALE!)"
        except:
            pass
        print(f"   {t:<40} {c:>8} rows  {days_old}")

    print(f"\n❌ EMPTY TABLES ({len(empty)} tables):")
    print("-" * 60)
    for t in sorted(empty):
        print(f"   {t}")

    if errors:
        print(f"\n⚠️ TABLES WITH ERRORS ({len(errors)}):")
        print("-" * 60)
        for t, e in errors:
            print(f"   {t}: {e}")

    # =========================================================================
    # PHASE 4: Check for NEW ML tables
    # =========================================================================
    print("\n" + "=" * 100)
    print("NEW ML/AI TABLES CHECK")
    print("=" * 100)

    new_tables = [
        'price_history',
        'greeks_snapshots',
        'vix_term_structure',
        'options_flow',
        'ai_analysis_history',
        'position_sizing_history',
        'strategy_comparison_history',
        'market_snapshots',
        'backtest_trades',
        'backtest_runs',
        'data_collection_log'
    ]

    print("\nChecking if new ML/AI tables exist:")
    for table in new_tables:
        if table in tables:
            # Get count
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            status = f"EXISTS ({count} rows)" if count > 0 else "EXISTS (empty)"
            print(f"   ✅ {table:<35} {status}")
        else:
            print(f"   ❌ {table:<35} MISSING - needs to be created")

    # =========================================================================
    # PHASE 5: Check critical data
    # =========================================================================
    print("\n" + "=" * 100)
    print("CRITICAL DATA CHECK")
    print("=" * 100)

    # Check GEX history
    print("\n📊 GEX HISTORY:")
    try:
        cursor.execute("SELECT COUNT(*) FROM gex_history")
        count = cursor.fetchone()[0]
        cursor.execute("SELECT symbol, net_gex, flip_point, spot_price, timestamp FROM gex_history ORDER BY timestamp DESC LIMIT 3")
        rows = cursor.fetchall()
        print(f"   Total records: {count}")
        if rows:
            print("   Latest entries:")
            for row in rows:
                print(f"      {row[0]}: GEX={row[1]}, Flip={row[2]}, Spot={row[3]}, Time={row[4]}")
        else:
            print("   ❌ NO GEX DATA!")
    except Exception as e:
        print(f"   ❌ Error: {e}")

    # Check regime signals
    print("\n📊 REGIME SIGNALS:")
    try:
        cursor.execute("SELECT COUNT(*) FROM regime_signals")
        count = cursor.fetchone()[0]
        cursor.execute("SELECT primary_regime_type, confidence_score, spy_price, timestamp FROM regime_signals ORDER BY timestamp DESC LIMIT 3")
        rows = cursor.fetchall()
        print(f"   Total records: {count}")
        if rows:
            print("   Latest entries:")
            for row in rows:
                print(f"      Regime={row[0]}, Confidence={row[1]}, SPY={row[2]}, Time={row[3]}")
        else:
            print("   ❌ NO REGIME DATA!")
    except Exception as e:
        print(f"   ❌ Error: {e}")

    # Check backtest results
    print("\n📊 BACKTEST RESULTS:")
    try:
        cursor.execute("SELECT COUNT(*) FROM backtest_results")
        count = cursor.fetchone()[0]
        cursor.execute("SELECT strategy_name, win_rate, total_trades, timestamp FROM backtest_results ORDER BY timestamp DESC LIMIT 5")
        rows = cursor.fetchall()
        print(f"   Total records: {count}")
        if rows:
            print("   Latest entries:")
            for row in rows:
                print(f"      {row[0]}: Win={row[1]:.1f}%, Trades={row[2]}, Time={row[3]}")
        else:
            print("   ❌ NO BACKTEST DATA!")
    except Exception as e:
        print(f"   ❌ Error: {e}")

    # Check closed trades
    print("\n📊 AUTONOMOUS CLOSED TRADES:")
    try:
        cursor.execute("SELECT COUNT(*) FROM autonomous_closed_trades")
        count = cursor.fetchone()[0]
        cursor.execute("SELECT symbol, strategy, realized_pnl, exit_date FROM autonomous_closed_trades ORDER BY exit_date DESC LIMIT 5")
        rows = cursor.fetchall()
        print(f"   Total records: {count}")
        if rows:
            print("   Latest entries:")
            for row in rows:
                print(f"      {row[0]} {row[1]}: P&L=${row[2]}, Exit={row[3]}")
        else:
            print("   ❌ NO CLOSED TRADES - Has the trader ever traded?")
    except Exception as e:
        print(f"   ❌ Error: {e}")

    # Check backtest_trades (individual trades for verification)
    print("\n📊 BACKTEST TRADES (Individual - for verification):")
    try:
        cursor.execute("SELECT COUNT(*) FROM backtest_trades")
        count = cursor.fetchone()[0]
        print(f"   Total records: {count}")
        if count == 0:
            print("   ❌ NO INDIVIDUAL BACKTEST TRADES - Cannot verify backtest results!")
            print("   💡 This is WHY you can't trust the backtest numbers")
    except Exception as e:
        print(f"   ❌ Table doesn't exist yet - run init_database()")

    # =========================================================================
    # PHASE 6: Action items
    # =========================================================================
    print("\n" + "=" * 100)
    print("ACTION ITEMS")
    print("=" * 100)

    actions = []

    # Check for missing new tables
    missing_tables = [t for t in new_tables if t not in tables]
    if missing_tables:
        actions.append(f"CREATE TABLES: {', '.join(missing_tables)}")

    # Check for empty critical tables
    critical_empty = [t for t in ['gex_history', 'regime_signals', 'backtest_results'] if t in empty]
    if critical_empty:
        actions.append(f"POPULATE TABLES: {', '.join(critical_empty)}")

    if 'backtest_trades' not in tables or 'backtest_trades' in empty:
        actions.append("FIX BACKTESTS: Update backtest framework to save individual trades")

    if actions:
        print("\n⚠️ ACTIONS NEEDED:")
        for i, action in enumerate(actions, 1):
            print(f"   {i}. {action}")
    else:
        print("\n✅ No critical actions needed!")

    print("\n" + "=" * 100)
    print("AUDIT COMPLETE")
    print("=" * 100)

    conn.close()
    return len(populated), len(empty), len(errors)


if __name__ == "__main__":
    run_audit()
