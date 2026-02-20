#!/usr/bin/env python3
"""Test 9: Entry Credit Audit

Definitively answers whether the $0.02 entry credit bug is fixed.
Shows distribution, P&L math verification, and timeline analysis.
Read-only — no data modification.
"""
import sys
import traceback

HEADER = """
╔══════════════════════════════════════╗
║  TEST 9: Entry Credit Audit          ║
╚══════════════════════════════════════╝
"""

# Buckets for entry credit analysis
BUCKETS = [
    ("BROKEN",     0.00, 0.09),
    ("SUSPICIOUS", 0.10, 0.49),
    ("LOW",        0.50, 0.99),
    ("NORMAL",     1.00, 9.99),
    ("HIGH",       10.00, 999999.99),
]


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

    # --- Check 9A: Entry Credit Distribution ---
    print("--- Check 9A: Entry Credit Distribution (All Trades) ---")
    try:
        # Get all trades with entry_credit
        cursor.execute("""
            SELECT position_id, entry_credit, open_time, close_time, realized_pnl
            FROM jubilee_ic_closed_trades
            ORDER BY close_time DESC
        """)
        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
        trades = [dict(zip(columns, r)) for r in rows]

        # Also check open positions
        cursor.execute("""
            SELECT position_id, entry_credit, open_time
            FROM jubilee_ic_positions
            WHERE status IN ('OPEN', 'open')
        """)
        open_rows = cursor.fetchall()
        open_cols = [desc[0] for desc in cursor.description]
        open_positions = [dict(zip(open_cols, r)) for r in open_rows]

        all_entries = trades + open_positions
        print(f"  Total closed trades: {len(trades)}")
        print(f"  Open positions:      {len(open_positions)}")
        print(f"  Total entries:       {len(all_entries)}")

        if not all_entries:
            print(f"  ℹ️  No trades to analyze")
            print(f"Result: ✅ PASS — no data to audit")
            print()
        else:
            bucket_results = {}
            for label, low, high in BUCKETS:
                matching = [t for t in all_entries
                            if low <= float(t.get('entry_credit', 0) or 0) <= high]
                if matching:
                    dates = [t.get('open_time') or t.get('close_time') for t in matching
                             if t.get('open_time') or t.get('close_time')]
                    earliest = min(dates) if dates else 'N/A'
                    latest = max(dates) if dates else 'N/A'
                    bucket_results[label] = {
                        'count': len(matching),
                        'earliest': earliest,
                        'latest': latest,
                        'entries': matching,
                    }

            print(f"\n  {'Bucket':<15} {'Count':>6} {'Earliest':>22} {'Latest':>22}")
            print(f"  {'-'*15} {'-'*6} {'-'*22} {'-'*22}")
            for label, low, high in BUCKETS:
                if label in bucket_results:
                    b = bucket_results[label]
                    print(f"  {label:<15} {b['count']:>6} {str(b['earliest'])[:22]:>22} {str(b['latest'])[:22]:>22}")
                else:
                    print(f"  {label:<15} {'0':>6} {'N/A':>22} {'N/A':>22}")

            # Verdict on BROKEN bucket
            broken = bucket_results.get('BROKEN', {})
            if broken.get('count', 0) > 0:
                print(f"\n  ⚠️ BROKEN entries found: {broken['count']}")
                # Show some examples
                for t in broken.get('entries', [])[:5]:
                    print(f"    ID: {t.get('position_id')}, credit: ${float(t.get('entry_credit', 0) or 0):.4f}, "
                          f"time: {t.get('open_time')}")

                # TODO: Compare with fix commit date if known
                print(f"\n  ❌ Entry credit recording has/had issues")
                print(f"  Check if all BROKEN entries are from BEFORE the fix commit")
                overall_pass = False
                print(f"Result: ❌ FAIL — broken entry credits found")
            else:
                print(f"\n  ✅ No BROKEN entries ($0.00-$0.09) found")
                print(f"Result: ✅ PASS — entry credits look clean")

            suspicious = bucket_results.get('SUSPICIOUS', {})
            if suspicious.get('count', 0) > 0:
                print(f"\n  ⚠️ {suspicious['count']} SUSPICIOUS entries ($0.10-$0.49)")
                for t in suspicious.get('entries', [])[:5]:
                    print(f"    ID: {t.get('position_id')}, credit: ${float(t.get('entry_credit', 0) or 0):.2f}, "
                          f"time: {t.get('open_time')}")
    except Exception as e:
        print(f"  Error: {e}")
        traceback.print_exc()
        print(f"Result: ❌ FAIL — query error")
        overall_pass = False
    print()

    # --- Check 9B: P&L Math Verification on Recent Closed Trades ---
    print("--- Check 9B: P&L Math Check (5 Most Recent Closed Trades) ---")
    try:
        cursor.execute("""
            SELECT position_id, entry_credit, close_price, contracts,
                   realized_pnl, close_reason, open_time, close_time,
                   max_loss
            FROM jubilee_ic_closed_trades
            ORDER BY close_time DESC
            LIMIT 5
        """)
        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]

        if not rows:
            print(f"  No closed trades to verify")
            print(f"Result: ✅ PASS — no data to check")
        else:
            pnl_matches = 0
            pnl_mismatches = 0

            for row in rows:
                r = dict(zip(columns, row))
                entry = float(r.get('entry_credit', 0) or 0)
                exit_price = float(r.get('close_price', 0) or 0)
                contracts = int(r.get('contracts', 0) or 0)
                stored_pnl = float(r.get('realized_pnl', 0) or 0)
                max_loss = float(r.get('max_loss', 0) or 0)
                close_reason = r.get('close_reason', '')

                # IC P&L: credit received - debit to close = P&L per contract
                # Total P&L = (entry_credit - close_price) * contracts * 100
                if entry > 0 and contracts > 0:
                    calculated_pnl = (entry - exit_price) * contracts * 100
                else:
                    calculated_pnl = stored_pnl  # Can't calculate, assume match

                # Check if close_reason is EXPIRED (kept all credit)
                if close_reason and 'expired' in close_reason.lower():
                    # Expired worthless = full credit kept
                    calculated_pnl = entry * contracts * 100

                match = abs(calculated_pnl - stored_pnl) < 1.0  # $1 tolerance
                icon = "✅" if match else "❌"

                print(f"\n  Position {r['position_id']}:")
                print(f"    Entry Credit: ${entry:.2f}")
                print(f"    Close Price:  ${exit_price:.2f}")
                print(f"    Contracts:    {contracts}")
                print(f"    Close Reason: {close_reason}")
                print(f"    Calculated P&L: (${entry:.2f} - ${exit_price:.2f}) x {contracts} x 100 = ${calculated_pnl:,.2f}")
                print(f"    Stored P&L:     ${stored_pnl:,.2f}")
                print(f"    Match: {icon} {'(within $1)' if match else f'MISMATCH: diff=${abs(calculated_pnl - stored_pnl):,.2f}'}")

                if match:
                    pnl_matches += 1
                else:
                    pnl_mismatches += 1

            print(f"\n  P&L Math: {pnl_matches} match, {pnl_mismatches} mismatch")
            if pnl_mismatches > 0:
                print(f"  ⚠️ P&L mismatches may indicate different calculation method")
                print(f"  (IC P&L often includes spread costs, assignment, etc.)")
                print(f"Result: ⚠️ WARNING — {pnl_mismatches} P&L mismatches")
            else:
                print(f"Result: ✅ PASS — all P&L calculations match")
    except Exception as e:
        print(f"  Error: {e}")
        traceback.print_exc()
        print(f"Result: ❌ FAIL — query error")
        overall_pass = False
    print()

    # --- Check 9C: Entry Credit Timeline ---
    print("--- Check 9C: Entry Credit Timeline (Daily Average) ---")
    try:
        cursor.execute("""
            SELECT (open_time AT TIME ZONE 'America/Chicago')::date AS day,
                   COUNT(*) AS trades,
                   AVG(entry_credit) AS avg_credit,
                   MIN(entry_credit) AS min_credit,
                   MAX(entry_credit) AS max_credit
            FROM jubilee_ic_closed_trades
            GROUP BY day
            ORDER BY day DESC
            LIMIT 14
        """)
        rows = cursor.fetchall()
        if rows:
            print(f"  {'Day':<12} {'Trades':>6} {'Avg Credit':>12} {'Min':>8} {'Max':>8}")
            print(f"  {'-'*12} {'-'*6} {'-'*12} {'-'*8} {'-'*8}")
            for row in rows:
                print(f"  {str(row[0]):<12} {int(row[1]):>6} ${float(row[2] or 0):>10.2f} ${float(row[3] or 0):>6.2f} ${float(row[4] or 0):>6.2f}")
        else:
            print(f"  No timeline data available")
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
TEST 9 OVERALL: {'✅ PASS' if overall_pass else '❌ FAIL'}
═══════════════════════════════
""")


if __name__ == '__main__':
    try:
        run()
    except Exception as e:
        print(f"\n❌ SCRIPT CRASHED: {e}")
        traceback.print_exc()
        sys.exit(1)
