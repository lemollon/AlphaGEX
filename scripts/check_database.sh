#!/bin/bash
# Check database contents and data freshness
# Shows what data is currently stored

echo "=============================================="
echo "ALPHAGEX DATABASE STATUS"
echo "=============================================="
echo "Time: $(date)"
echo ""

cd /home/user/AlphaGEX

python3 << 'EOF'
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, '/home/user/AlphaGEX')

try:
    from database_adapter import get_connection

    conn = get_connection()
    cursor = conn.cursor()

    print("=== TABLE SUMMARY ===\n")
    print(f"{'Table':<40} {'Rows':>10} {'Latest Data':<20}")
    print("-" * 75)

    # Get all tables with row counts
    cursor.execute("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
        ORDER BY table_name
    """)
    tables = [row[0] for row in cursor.fetchall()]

    for table in tables:
        try:
            # Get row count
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]

            # Try to get latest timestamp
            latest = "N/A"
            for col in ['timestamp', 'created_at', 'updated_at', 'date', 'trade_date']:
                try:
                    cursor.execute(f"SELECT MAX({col}) FROM {table}")
                    result = cursor.fetchone()[0]
                    if result:
                        latest = str(result)[:19]
                        break
                except:
                    continue

            print(f"{table:<40} {count:>10} {latest:<20}")
        except Exception as e:
            print(f"{table:<40} {'ERROR':>10} {str(e)[:20]:<20}")

    print("\n" + "=" * 75)
    print("\n=== KEY DATA FRESHNESS ===\n")

    # Check specific important tables
    important_tables = [
        ('gex_history', 'timestamp', 'GEX Data'),
        ('autonomous_closed_trades', 'timestamp', 'Closed Trades'),
        ('autonomous_open_positions', 'timestamp', 'Open Positions'),
        ('trading_decisions', 'timestamp', 'Decision Audit Log'),
        ('options_chain_snapshots', 'timestamp', 'Option Chain Data'),
        ('backtest_results', 'timestamp', 'Backtest Results')
    ]

    for table, ts_col, label in important_tables:
        if table in tables:
            try:
                cursor.execute(f"SELECT COUNT(*), MIN({ts_col}), MAX({ts_col}) FROM {table}")
                count, earliest, latest = cursor.fetchone()

                if count > 0:
                    print(f"{label}:")
                    print(f"  Records: {count}")
                    print(f"  Range: {str(earliest)[:10]} to {str(latest)[:10]}")

                    # Check freshness
                    if latest:
                        try:
                            if hasattr(latest, 'date'):
                                days_old = (datetime.now().date() - latest.date()).days
                            else:
                                days_old = (datetime.now() - latest).days
                            if days_old > 7:
                                print(f"  STATUS: STALE ({days_old} days old)")
                            else:
                                print(f"  STATUS: Fresh ({days_old} days old)")
                        except:
                            pass
                else:
                    print(f"{label}: EMPTY")
                print()
            except:
                pass

    # Check trading decisions specifically
    if 'trading_decisions' in tables:
        print("\n=== RECENT TRADING DECISIONS ===\n")
        try:
            cursor.execute("""
                SELECT decision_id, timestamp, symbol, action, strategy
                FROM trading_decisions
                ORDER BY timestamp DESC
                LIMIT 10
            """)
            rows = cursor.fetchall()
            if rows:
                for row in rows:
                    print(f"  {row[0]} | {str(row[1])[:16]} | {row[2]} | {row[3]} | {row[4]}")
            else:
                print("  No trading decisions logged yet")
        except Exception as e:
            print(f"  Could not query trading_decisions: {e}")

    conn.close()
    print("\n" + "=" * 75)

except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
EOF
