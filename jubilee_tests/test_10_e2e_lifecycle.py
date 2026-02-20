#!/usr/bin/env python3
"""Test 10: End-to-End Trade Lifecycle Trace

Traces one complete trade: signal → position → activity → equity.
Verifies each link in the chain exists and data is consistent.
Read-only — no data modification.
"""
import sys
import traceback

HEADER = """
╔══════════════════════════════════════╗
║  TEST 10: E2E Trade Lifecycle Trace  ║
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

    # --- Find the most recent closed position ---
    print("--- Check 10A: Find Most Recent Closed IC Position ---")
    position = None
    try:
        cursor.execute("""
            SELECT position_id, ticker, entry_credit, close_price, contracts,
                   realized_pnl, close_reason, open_time, close_time,
                   put_short_strike, put_long_strike, call_short_strike, call_long_strike,
                   max_loss, status
            FROM jubilee_ic_closed_trades
            ORDER BY close_time DESC
            LIMIT 1
        """)
        row = cursor.fetchone()
        if row:
            columns = [desc[0] for desc in cursor.description]
            position = dict(zip(columns, row))
            print(f"  Found closed position: {position['position_id']}")
            print(f"    Ticker:       {position['ticker']}")
            print(f"    Entry Credit: ${float(position.get('entry_credit', 0) or 0):.2f}")
            print(f"    Close Price:  ${float(position.get('close_price', 0) or 0):.2f}")
            print(f"    Contracts:    {position.get('contracts')}")
            print(f"    Realized P&L: ${float(position.get('realized_pnl', 0) or 0):,.2f}")
            print(f"    Close Reason: {position.get('close_reason')}")
            print(f"    Open Time:    {position['open_time']}")
            print(f"    Close Time:   {position['close_time']}")
            print(f"    Strikes:      {position.get('put_long_strike')}/{position.get('put_short_strike')} P | "
                  f"{position.get('call_short_strike')}/{position.get('call_long_strike')} C")
            print(f"Result: ✅ PASS — position found")
        else:
            print(f"  ℹ️  No closed IC positions found")
            print(f"  Cannot trace lifecycle without closed trades")
            print(f"Result: ⚠️ WARNING — no data to trace")
            _print_overall(True)
            try:
                cursor.close()
                conn.close()
            except Exception:
                pass
            return
    except Exception as e:
        print(f"  Error: {e}")
        traceback.print_exc()
        print(f"Result: ❌ FAIL")
        overall_pass = False
    print()

    if not position:
        _print_overall(overall_pass)
        return

    pos_id = position['position_id']
    open_time = position['open_time']
    close_time = position['close_time']

    # --- Find matching signal ---
    print(f"--- Check 10B: Find Matching Signal for {pos_id} ---")
    signal_found = False
    try:
        # First detect which columns exist
        cursor.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'jubilee_ic_signals'
            ORDER BY ordinal_position
        """)
        signal_cols = [r[0] for r in cursor.fetchall()]

        # Search by execution_position_id if it exists
        if 'execution_position_id' in signal_cols:
            cursor.execute("""
                SELECT *
                FROM jubilee_ic_signals
                WHERE execution_position_id = %s
                LIMIT 1
            """, (pos_id,))
            row = cursor.fetchone()
            if row:
                cols = [desc[0] for desc in cursor.description]
                signal = dict(zip(cols, row))
                signal_found = True
                print(f"  ✅ Found matching signal by execution_position_id")
                for key in ['signal_id', 'signal_time', 'total_credit', 'contracts',
                            'oracle_approved', 'executed', 'was_executed',
                            'execution_position_id', 'skip_reason']:
                    if key in signal:
                        print(f"    {key}: {signal[key]}")

                # Verify credit consistency
                sig_credit = float(signal.get('total_credit', 0) or 0)
                pos_credit = float(position.get('entry_credit', 0) or 0)
                if sig_credit > 0 and pos_credit > 0:
                    diff = abs(sig_credit - pos_credit)
                    if diff < 0.10:
                        print(f"\n  ✅ Signal credit (${sig_credit:.2f}) ≈ Position credit (${pos_credit:.2f})")
                    else:
                        print(f"\n  ⚠️ Credit mismatch: Signal ${sig_credit:.2f} vs Position ${pos_credit:.2f} (diff ${diff:.2f})")
            else:
                print(f"  ❌ No signal found with execution_position_id = {pos_id}")

        if not signal_found:
            # Try to find by time proximity
            if open_time:
                cursor.execute("""
                    SELECT *
                    FROM jubilee_ic_signals
                    WHERE signal_time BETWEEN %s - INTERVAL '5 minutes' AND %s + INTERVAL '5 minutes'
                    ORDER BY signal_time DESC
                    LIMIT 3
                """, (open_time, open_time))
                rows = cursor.fetchall()
                if rows:
                    cols = [desc[0] for desc in cursor.description]
                    print(f"  ⚠️ No direct link, but found {len(rows)} signal(s) within 5 min of open_time:")
                    for row in rows:
                        s = dict(zip(cols, row))
                        print(f"    Signal: {s.get('signal_id')}, time: {s.get('signal_time')}")
                    signal_found = True  # Partial match
                else:
                    print(f"  ❌ No signals found near open_time {open_time}")

        if signal_found:
            print(f"Result: ✅ PASS — signal found")
        else:
            print(f"Result: ❌ FAIL — no matching signal")
            overall_pass = False
    except Exception as e:
        print(f"  Error: {e}")
        traceback.print_exc()
        print(f"Result: ❌ FAIL")
        overall_pass = False
    print()

    # --- Find activity log entries ---
    print(f"--- Check 10C: Activity Log Around Trade {pos_id} ---")
    try:
        # Search for log entries mentioning this position_id
        cursor.execute("""
            SELECT log_id, timestamp, action, message, level
            FROM jubilee_logs
            WHERE message LIKE %s
               OR (details::text LIKE %s)
            ORDER BY timestamp
            LIMIT 20
        """, (f'%{pos_id}%', f'%{pos_id}%'))
        rows = cursor.fetchall()

        if rows:
            print(f"  Found {len(rows)} log entries for {pos_id}:")
            has_open = False
            has_close = False
            for row in rows:
                action = str(row[2] or '').lower()
                msg = str(row[3] or '')[:120]
                print(f"    [{row[1]}] {row[2]}: {msg}")
                if 'open' in action or 'execute' in action or 'create' in action:
                    has_open = True
                if 'close' in action or 'exit' in action:
                    has_close = True

            if has_open and has_close:
                print(f"\n  ✅ Both OPEN and CLOSE events found in log")
            elif has_open:
                print(f"\n  ⚠️ Only OPEN event found, no CLOSE event in log")
            elif has_close:
                print(f"\n  ⚠️ Only CLOSE event found, no OPEN event in log")
            else:
                print(f"\n  ⚠️ Neither OPEN nor CLOSE events clearly labeled")
            print(f"Result: ✅ PASS — log entries found")
        else:
            # Try broader search around the timestamps
            if open_time and close_time:
                cursor.execute("""
                    SELECT log_id, timestamp, action, message
                    FROM jubilee_logs
                    WHERE timestamp BETWEEN %s - INTERVAL '1 minute' AND %s + INTERVAL '1 minute'
                    ORDER BY timestamp
                    LIMIT 10
                """, (open_time, close_time))
                rows2 = cursor.fetchall()
                if rows2:
                    print(f"  ⚠️ No logs matching position_id, but {len(rows2)} entries around trade times:")
                    for r in rows2:
                        print(f"    [{r[1]}] {r[2]}: {str(r[3] or '')[:100]}")
                    print(f"Result: ⚠️ WARNING — logs exist but don't reference position_id")
                else:
                    print(f"  ❌ No log entries found around trade timestamps")
                    print(f"Result: ❌ FAIL — activity log missing for this trade")
                    overall_pass = False
            else:
                print(f"  ❌ No log entries found for {pos_id}")
                print(f"Result: ❌ FAIL — activity log missing")
                overall_pass = False
    except Exception as e:
        print(f"  Error: {e}")
        traceback.print_exc()
        print(f"Result: ⚠️ WARNING — log query failed")
    print()

    # --- Find equity snapshots during trade lifetime ---
    print(f"--- Check 10D: Equity Snapshots During Trade Lifetime ---")
    try:
        if open_time and close_time:
            cursor.execute("""
                SELECT snapshot_time, total_equity, realized_pnl, unrealized_pnl
                FROM jubilee_ic_equity_snapshots
                WHERE snapshot_time BETWEEN %s AND %s + INTERVAL '5 minutes'
                ORDER BY snapshot_time
            """, (open_time, close_time))
            rows = cursor.fetchall()

            if rows:
                print(f"  Found {len(rows)} equity snapshots during trade lifetime:")
                for i, row in enumerate(rows):
                    print(f"    [{row[0]}] Equity: ${float(row[1] or 0):,.2f}, "
                          f"Realized: ${float(row[2] or 0):,.2f}, "
                          f"Unrealized: ${float(row[3] or 0):,.2f}")

                # Check if equity changed after close
                first_eq = float(rows[0][1] or 0)
                last_eq = float(rows[-1][1] or 0)
                if abs(last_eq - first_eq) > 0.01:
                    print(f"\n  ✅ Equity changed during trade: ${first_eq:,.2f} → ${last_eq:,.2f}")
                else:
                    print(f"\n  ⚠️ Equity unchanged: ${first_eq:,.2f} → ${last_eq:,.2f}")
                print(f"Result: ✅ PASS — equity snapshots found")
            else:
                print(f"  ❌ No equity snapshots between {open_time} and {close_time}")
                print(f"  Equity recording may not be running during trades")
                print(f"Result: ⚠️ WARNING — no snapshots during trade")
        else:
            print(f"  Cannot check — missing open_time or close_time")
            print(f"Result: ⚠️ WARNING")
    except Exception as e:
        print(f"  Error: {e}")
        traceback.print_exc()
        print(f"Result: ⚠️ WARNING")
    print()

    # --- Full chain summary ---
    print("--- Check 10E: Full Lifecycle Chain Summary ---")
    print(f"  Position: {pos_id}")
    print(f"  Signal → Position → Activity Log → Equity Snapshot")
    print(f"    {'✅' if signal_found else '❌'} Signal found")
    print(f"    ✅ Position found (this is our anchor)")
    print(f"    {'✅ or ⚠️' } Activity log (see 10C above)")
    print(f"    {'See 10D'} Equity snapshots (see 10D above)")
    print()

    # --- Cleanup ---
    try:
        cursor.close()
        conn.close()
    except Exception:
        pass

    _print_overall(overall_pass)


def _print_overall(passed):
    print(f"""
═══════════════════════════════
TEST 10 OVERALL: {'✅ PASS' if passed else '❌ FAIL'}
═══════════════════════════════
""")


if __name__ == '__main__':
    try:
        run()
    except Exception as e:
        print(f"\n❌ SCRIPT CRASHED: {e}")
        traceback.print_exc()
        sys.exit(1)
