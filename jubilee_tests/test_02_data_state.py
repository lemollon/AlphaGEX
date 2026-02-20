#!/usr/bin/env python3
"""Test 2: Data State Validation

Queries current open positions, recent closed trades, exit reason distribution,
and compares JUBILEE IC vs SAMSON side-by-side.
Read-only — no data modification.
"""
import sys
import traceback
from datetime import datetime, timedelta

HEADER = """
╔══════════════════════════════════════╗
║  TEST 2: Data State Validation       ║
╚══════════════════════════════════════╝
"""


def run():
    print(HEADER)

    try:
        from database_adapter import get_connection
        conn = get_connection()
        cursor = conn.cursor()
    except Exception as e:
        print(f"❌ Cannot connect to database: {e}")
        return

    overall_pass = True

    # --- Check 2A: Open IC Positions ---
    print("--- Check 2A: Open IC Positions ---")
    try:
        cursor.execute("""
            SELECT position_id, ticker, status, entry_credit, contracts,
                   open_time,
                   put_short_strike, put_long_strike, call_short_strike, call_long_strike,
                   EXTRACT(EPOCH FROM (NOW() - open_time)) / 3600.0 AS age_hours
            FROM jubilee_ic_positions
            WHERE status = 'OPEN' OR status = 'open'
            ORDER BY open_time DESC
        """)
        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
        print(f"  Open IC positions: {len(rows)}")

        stale_count = 0
        bad_credit = 0
        for row in rows:
            r = dict(zip(columns, row))
            age_h = float(r.get('age_hours', 0) or 0)
            credit = float(r.get('entry_credit', 0) or 0)
            print(f"    ID: {r['position_id']}")
            print(f"      Ticker: {r['ticker']}, Status: {r['status']}")
            print(f"      Entry Credit: ${credit:.2f}, Contracts: {r['contracts']}")
            print(f"      Strikes: {r.get('put_long_strike')}/{r.get('put_short_strike')} P | "
                  f"{r.get('call_short_strike')}/{r.get('call_long_strike')} C")
            print(f"      Open: {r['open_time']}, Age: {age_h:.1f} hours")

            if age_h > 8:
                stale_count += 1
                print(f"      ❌ FLAG: Position > 8 hours old — MONITORING LOOP MAY BE BROKEN")
            if 0 < credit < 0.50:
                bad_credit += 1
                print(f"      ❌ FLAG: Entry credit < $0.50 — ENTRY RECORDING BUG")

        if not rows:
            print("  ℹ️  No open positions (may be outside market hours)")

        if stale_count > 0:
            overall_pass = False
            print(f"\nResult: ❌ FAIL — {stale_count} positions > 8 hours old")
        elif bad_credit > 0:
            overall_pass = False
            print(f"\nResult: ❌ FAIL — {bad_credit} positions with suspicious entry credit")
        else:
            print(f"\nResult: ✅ PASS — {len(rows)} open positions, all valid")
    except Exception as e:
        print(f"  Error: {e}")
        traceback.print_exc()
        overall_pass = False
        print(f"Result: ❌ FAIL — query error")
    print()

    # --- Check 2B: Closed Trades (last 7 days) ---
    print("--- Check 2B: Closed IC Trades (last 7 days) ---")
    try:
        cursor.execute("""
            SELECT COUNT(*) AS cnt,
                   MIN(entry_credit) AS min_credit,
                   MAX(entry_credit) AS max_credit,
                   AVG(entry_credit) AS avg_credit,
                   MIN(EXTRACT(EPOCH FROM (close_time - open_time)) / 3600.0) AS min_hold_h,
                   MAX(EXTRACT(EPOCH FROM (close_time - open_time)) / 3600.0) AS max_hold_h,
                   AVG(EXTRACT(EPOCH FROM (close_time - open_time)) / 3600.0) AS avg_hold_h,
                   SUM(realized_pnl) AS total_pnl
            FROM jubilee_ic_closed_trades
            WHERE close_time > NOW() - INTERVAL '7 days'
        """)
        row = cursor.fetchone()
        cnt = int(row[0] or 0)
        print(f"  Closed trades (7d): {cnt}")
        if cnt > 0:
            print(f"  Entry credit: min=${float(row[1] or 0):.2f}, max=${float(row[2] or 0):.2f}, avg=${float(row[3] or 0):.2f}")
            print(f"  Hold time: min={float(row[4] or 0):.1f}h, max={float(row[5] or 0):.1f}h, avg={float(row[6] or 0):.1f}h")
            print(f"  Total P&L (7d): ${float(row[7] or 0):,.2f}")
        else:
            print("  ℹ️  No closed trades in last 7 days")
        print(f"Result: ✅ PASS — data queried successfully")
    except Exception as e:
        print(f"  Error: {e}")
        traceback.print_exc()
        print(f"Result: ❌ FAIL — query error")
    print()

    # --- Check 2C: Exit Reason Distribution ---
    print("--- Check 2C: Exit Reason Distribution ---")
    try:
        cursor.execute("""
            SELECT close_reason, COUNT(*) AS cnt
            FROM jubilee_ic_closed_trades
            GROUP BY close_reason
            ORDER BY cnt DESC
        """)
        rows = cursor.fetchall()
        total = sum(int(r[1]) for r in rows)
        print(f"  Total closed trades (all time): {total}")

        time_stop_pct = 0
        for row in rows:
            reason = row[0] or 'NULL'
            cnt = int(row[1])
            pct = cnt / total * 100 if total > 0 else 0
            print(f"    {reason}: {cnt} ({pct:.1f}%)")
            if 'time_stop' in str(reason).lower() or 'TIME_STOP' in str(reason):
                time_stop_pct = pct

        if total > 0 and time_stop_pct >= 99.0:
            print(f"\n  ❌ FLAG: {time_stop_pct:.1f}% time_stop exits — EXIT LOGIC BROKEN")
            overall_pass = False
            print(f"Result: ❌ FAIL — 100% time_stop exits")
        elif total == 0:
            print(f"Result: ⚠️ WARNING — no closed trades to analyze")
        else:
            # Check for FORCE_EXIT presence
            force_exits = [r for r in rows if 'force_exit' in str(r[0] or '').lower() or 'FORCE_EXIT' in str(r[0] or '')]
            if force_exits:
                print(f"\n  ✅ FORCE_EXIT has been triggered {sum(int(r[1]) for r in force_exits)} time(s)")
            else:
                print(f"\n  ℹ️  FORCE_EXIT has never been triggered (may be normal if no expiration-day holds)")
            print(f"Result: ✅ PASS — exit distribution looks reasonable")
    except Exception as e:
        print(f"  Error: {e}")
        traceback.print_exc()
        print(f"Result: ❌ FAIL — query error")
    print()

    # --- Check 2D: SAMSON vs JUBILEE Side-by-Side ---
    print("--- Check 2D: SAMSON vs JUBILEE IC Comparison ---")
    try:
        # JUBILEE IC stats
        cursor.execute("""
            SELECT
                COUNT(*) AS total_trades,
                AVG(entry_credit) AS avg_credit,
                AVG(contracts) AS avg_contracts,
                AVG(EXTRACT(EPOCH FROM (close_time - open_time)) / 3600.0) AS avg_hold_h,
                SUM(realized_pnl) AS total_pnl,
                COUNT(CASE WHEN realized_pnl > 0 THEN 1 END) AS wins,
                COUNT(CASE WHEN realized_pnl <= 0 THEN 1 END) AS losses
            FROM jubilee_ic_closed_trades
        """)
        jub = cursor.fetchone()

        # SAMSON stats (closed positions from samson_positions)
        cursor.execute("""
            SELECT
                COUNT(*) AS total_trades,
                AVG(entry_credit) AS avg_credit,
                AVG(contracts) AS avg_contracts,
                AVG(EXTRACT(EPOCH FROM (close_time - open_time)) / 3600.0) AS avg_hold_h,
                SUM(realized_pnl) AS total_pnl,
                COUNT(CASE WHEN realized_pnl > 0 THEN 1 END) AS wins,
                COUNT(CASE WHEN realized_pnl <= 0 THEN 1 END) AS losses
            FROM samson_positions
            WHERE status = 'CLOSED'
        """)
        sam = cursor.fetchone()

        def safe_float(val, default=0):
            try:
                return float(val) if val is not None else default
            except (ValueError, TypeError):
                return default

        def safe_int(val, default=0):
            try:
                return int(val) if val is not None else default
            except (ValueError, TypeError):
                return default

        jub_trades = safe_int(jub[0])
        sam_trades = safe_int(sam[0])

        print(f"  {'Metric':<25} {'JUBILEE IC':>15} {'SAMSON':>15}")
        print(f"  {'-'*25} {'-'*15} {'-'*15}")
        print(f"  {'Total Trades':<25} {jub_trades:>15} {sam_trades:>15}")
        jub_credit = f"${safe_float(jub[1]):.2f}"
        sam_credit = f"${safe_float(sam[1]):.2f}"
        print(f"  {'Avg Entry Credit':<25} {jub_credit:>15} {sam_credit:>15}")
        jub_contr = f"{safe_float(jub[2]):.1f}"
        sam_contr = f"{safe_float(sam[2]):.1f}"
        print(f"  {'Avg Contracts':<25} {jub_contr:>15} {sam_contr:>15}")
        jub_hold = f"{safe_float(jub[3]):.1f}"
        sam_hold = f"{safe_float(sam[3]):.1f}"
        print(f"  {'Avg Hold (hours)':<25} {jub_hold:>15} {sam_hold:>15}")
        jub_pnl = f"${safe_float(jub[4]):,.2f}"
        sam_pnl = f"${safe_float(sam[4]):,.2f}"
        print(f"  {'Total P&L':<25} {jub_pnl:>15} {sam_pnl:>15}")

        jub_wr = safe_int(jub[5]) / jub_trades * 100 if jub_trades > 0 else 0
        sam_wr = safe_int(sam[5]) / sam_trades * 100 if sam_trades > 0 else 0
        print(f"  {'Win Rate':<25} {f'{jub_wr:.1f}%':>15} {f'{sam_wr:.1f}%':>15}")

        print(f"\nResult: ✅ PASS — comparison data retrieved")
    except Exception as e:
        print(f"  Error: {e}")
        traceback.print_exc()
        print(f"  ℹ️  SAMSON table may not exist or have different schema")
        print(f"Result: ⚠️ WARNING — comparison partially failed")
    print()

    # --- Cleanup ---
    try:
        cursor.close()
        conn.close()
    except Exception:
        pass

    print(f"""
═══════════════════════════════
TEST 2 OVERALL: {'✅ PASS' if overall_pass else '❌ FAIL'}
═══════════════════════════════
""")


if __name__ == '__main__':
    try:
        run()
    except Exception as e:
        print(f"\n❌ SCRIPT CRASHED: {e}")
        traceback.print_exc()
        sys.exit(1)
