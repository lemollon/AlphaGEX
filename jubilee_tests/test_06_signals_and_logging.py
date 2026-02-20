#!/usr/bin/env python3
"""Test 6: Signals and Execution Logging

Verifies IC signals are being generated, execution status is updated,
and no orphaned signals exist.
Read-only — no data modification.
"""
import sys
import traceback
from datetime import datetime

HEADER = """
╔══════════════════════════════════════╗
║  TEST 6: Signals & Execution Logging ║
╚══════════════════════════════════════╝
"""


def run():
    print(HEADER)

    overall_pass = True

    try:
        from database_adapter import get_connection
        conn = get_connection()
        cursor = conn.cursor()
    except Exception as e:
        print(f"❌ Cannot connect to database: {e}")
        return

    # --- Check 6A: Recent IC Signals ---
    print("--- Check 6A: Recent IC Signals (last 10) ---")
    try:
        cursor.execute("""
            SELECT *
            FROM jubilee_ic_signals
            ORDER BY signal_time DESC
            LIMIT 10
        """)
        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]

        print(f"  Total recent signals: {len(rows)}")
        if rows:
            for i, row in enumerate(rows):
                r = dict(zip(columns, row))
                print(f"\n  Signal {i+1}:")
                for key in ['signal_id', 'signal_time', 'ticker',
                            'put_short_strike', 'put_long_strike',
                            'call_short_strike', 'call_long_strike',
                            'total_credit', 'contracts', 'max_loss',
                            'oracle_approved', 'is_valid',
                            'executed', 'was_executed',
                            'execution_position_id', 'skip_reason']:
                    if key in r:
                        val = r[key]
                        print(f"    {key}: {val}")
        else:
            # Check if there are ANY signals
            cursor.execute("SELECT COUNT(*) FROM jubilee_ic_signals")
            total = int(cursor.fetchone()[0] or 0)
            print(f"  Total signals all time: {total}")
            if total == 0:
                print(f"  ℹ️  No IC signals have ever been generated")
                print(f"  This could mean: bot hasn't started, or signal generation is broken")

        print(f"\nResult: ✅ PASS — signal data queried")
    except Exception as e:
        print(f"  Error: {e}")
        traceback.print_exc()
        print(f"Result: ❌ FAIL — cannot query signals")
        overall_pass = False
    print()

    # --- Check 6B: Execution Tracking —- signals that were executed ---
    print("--- Check 6B: Executed Signals with Position References ---")
    try:
        # Try both column names (executed vs was_executed)
        exec_col = None
        pos_ref_col = None

        # Detect column names
        cursor.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'jubilee_ic_signals'
            ORDER BY ordinal_position
        """)
        col_names = [r[0] for r in cursor.fetchall()]
        print(f"  Signal table columns: {col_names}")

        # Find execution flag column
        for candidate in ['was_executed', 'executed']:
            if candidate in col_names:
                exec_col = candidate
                break

        # Find position reference column
        for candidate in ['execution_position_id', 'position_id']:
            if candidate in col_names:
                pos_ref_col = candidate
                break

        if exec_col:
            # Count executed signals
            cursor.execute(f"""
                SELECT COUNT(*) FROM jubilee_ic_signals
                WHERE {exec_col} = TRUE
            """)
            executed_count = int(cursor.fetchone()[0] or 0)
            print(f"\n  Executed signals (total): {executed_count}")

            if pos_ref_col and executed_count > 0:
                # Count with valid position reference
                cursor.execute(f"""
                    SELECT COUNT(*) FROM jubilee_ic_signals
                    WHERE {exec_col} = TRUE
                      AND {pos_ref_col} IS NOT NULL
                      AND {pos_ref_col} != ''
                """)
                with_ref = int(cursor.fetchone()[0] or 0)

                # Count orphaned (executed but no position)
                orphaned = executed_count - with_ref
                print(f"  With valid position reference: {with_ref}")
                print(f"  Orphaned (executed but no ref): {orphaned}")

                if orphaned > 0:
                    print(f"\n  ⚠️ {orphaned} signals marked as executed but have no position reference")
                    cursor.execute(f"""
                        SELECT signal_id, signal_time, {pos_ref_col}
                        FROM jubilee_ic_signals
                        WHERE {exec_col} = TRUE
                          AND ({pos_ref_col} IS NULL OR {pos_ref_col} = '')
                        ORDER BY signal_time DESC
                        LIMIT 5
                    """)
                    orphan_rows = cursor.fetchall()
                    for r in orphan_rows:
                        print(f"    Orphan: signal_id={r[0]}, time={r[1]}, ref={r[2]}")
                    print(f"\nResult: ⚠️ WARNING — {orphaned} orphaned signals")
                else:
                    print(f"\nResult: ✅ PASS — all executed signals have position references")
            elif not pos_ref_col:
                print(f"  ⚠️ No position reference column found in signals table")
                print(f"Result: ⚠️ WARNING — cannot verify signal-position linking")
            else:
                print(f"  ℹ️  No executed signals to verify")
                print(f"Result: ✅ PASS")
        else:
            print(f"  ⚠️ No execution flag column found (expected 'was_executed' or 'executed')")
            print(f"Result: ⚠️ WARNING — cannot verify execution tracking")
    except Exception as e:
        print(f"  Error: {e}")
        traceback.print_exc()
        print(f"Result: ❌ FAIL")
        overall_pass = False
    print()

    # --- Check 6C: Signals from today ---
    print("--- Check 6C: Today's Signals ---")
    try:
        cursor.execute("""
            SELECT COUNT(*),
                   MIN(signal_time) AS first_signal,
                   MAX(signal_time) AS last_signal
            FROM jubilee_ic_signals
            WHERE signal_time::date = (NOW() AT TIME ZONE 'America/Chicago')::date
        """)
        row = cursor.fetchone()
        today_count = int(row[0] or 0)

        if today_count > 0:
            print(f"  Signals today: {today_count}")
            print(f"  First: {row[1]}")
            print(f"  Last:  {row[2]}")
            print(f"Result: ✅ PASS — signals being generated today")
        else:
            # Check if market is open
            try:
                from zoneinfo import ZoneInfo
                ct = ZoneInfo("America/Chicago")
            except ImportError:
                import pytz
                ct = pytz.timezone("America/Chicago")
            now_ct = datetime.now(ct)
            is_weekday = now_ct.weekday() < 5
            is_market_hours = 8 <= now_ct.hour < 15

            if not is_weekday:
                print(f"  ℹ️  No signals today — it's a weekend ({now_ct.strftime('%A')})")
                print(f"Result: ✅ PASS — expected on weekends")
            elif not is_market_hours:
                print(f"  ℹ️  No signals today — outside market hours ({now_ct.strftime('%H:%M')} CT)")
                print(f"Result: ✅ PASS — expected outside market hours")
            else:
                print(f"  ⚠️ No signals today but market IS open ({now_ct.strftime('%H:%M')} CT)")
                print(f"  Signal generation may be broken or bot may be paused")
                print(f"Result: ⚠️ WARNING — no signals during market hours")
    except Exception as e:
        print(f"  Error: {e}")
        traceback.print_exc()
        print(f"Result: ⚠️ WARNING")
    print()

    # --- Check 6D: Skip reasons distribution ---
    print("--- Check 6D: Signal Skip Reasons ---")
    try:
        skip_col = 'skip_reason' if 'skip_reason' in col_names else None
        if not skip_col:
            # Try to find it
            for candidate in ['skip_reason', 'rejection_reason', 'reason']:
                if candidate in col_names:
                    skip_col = candidate
                    break

        if skip_col:
            cursor.execute(f"""
                SELECT {skip_col}, COUNT(*) AS cnt
                FROM jubilee_ic_signals
                WHERE {skip_col} IS NOT NULL AND {skip_col} != ''
                GROUP BY {skip_col}
                ORDER BY cnt DESC
                LIMIT 20
            """)
            rows = cursor.fetchall()
            if rows:
                print(f"  Skip reasons (top 20):")
                for row in rows:
                    print(f"    {row[0]}: {row[1]}")
            else:
                print(f"  No skip reasons recorded")
            print(f"Result: ✅ PASS")
        else:
            print(f"  ℹ️  No skip_reason column in signals table")
            print(f"Result: ✅ PASS")
    except Exception as e:
        print(f"  Error: {e}")
        print(f"Result: ⚠️ WARNING")
    print()

    # --- Cleanup ---
    try:
        cursor.close()
        conn.close()
    except Exception:
        pass

    print(f"""
═══════════════════════════════
TEST 6 OVERALL: {'✅ PASS' if overall_pass else '❌ FAIL'}
═══════════════════════════════
""")


if __name__ == '__main__':
    try:
        run()
    except Exception as e:
        print(f"\n❌ SCRIPT CRASHED: {e}")
        traceback.print_exc()
        sys.exit(1)
