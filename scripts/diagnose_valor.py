"""
VALOR Diagnostic Script - Run in Render Shell
Usage: python scripts/diagnose_valor.py
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database_adapter import get_connection

def run():
    conn = get_connection()
    cur = conn.cursor()

    # 1. Are scans happening?
    print("=" * 60)
    print("1. SCAN ACTIVITY SINCE 2/25")
    print("=" * 60)
    cur.execute("""
        SELECT DATE(created_at AT TIME ZONE 'America/Chicago') as day,
               outcome, COUNT(*)
        FROM valor_scan_activity
        WHERE created_at >= '2026-02-25'
        GROUP BY day, outcome
        ORDER BY day
    """)
    rows = cur.fetchall()
    if rows:
        for r in rows:
            print(f"  {r[0]} | {r[1]:>10} | {r[2]}")
    else:
        print("  *** NO SCAN ROWS AT ALL — VALOR process is likely dead ***")

    # 2. Skip reasons
    print()
    print("=" * 60)
    print("2. TOP SKIP REASONS")
    print("=" * 60)
    cur.execute("""
        SELECT COALESCE(skip_reason, '(null)'), COUNT(*)
        FROM valor_scan_activity
        WHERE created_at >= '2026-02-25'
          AND outcome IN ('NO_TRADE', 'SKIP', 'ERROR')
        GROUP BY skip_reason
        ORDER BY COUNT(*) DESC
        LIMIT 20
    """)
    rows = cur.fetchall()
    if rows:
        for r in rows:
            print(f"  {r[1]:>6}x | {(r[0] or '(null)')[:120]}")
    else:
        print("  (none)")

    # 3. Last trade before silence
    print()
    print("=" * 60)
    print("3. LAST 5 CLOSED TRADES (any date)")
    print("=" * 60)
    cur.execute("""
        SELECT position_id, ticker, direction,
               ROUND(entry_price::numeric, 2) as entry,
               ROUND(close_price::numeric, 2) as close_px,
               ROUND(realized_pnl::numeric, 2) as pnl,
               close_time AT TIME ZONE 'America/Chicago' as close_ct
        FROM valor_closed_trades
        ORDER BY close_time DESC
        LIMIT 5
    """)
    rows = cur.fetchall()
    if rows:
        for r in rows:
            print(f"  {r[6]} | {r[1]} {r[2]} | entry={r[3]} close={r[4]} pnl={r[5]}")
    else:
        print("  (no closed trades)")

    # 4. Open positions stuck?
    print()
    print("=" * 60)
    print("4. OPEN POSITIONS (stuck?)")
    print("=" * 60)
    cur.execute("""
        SELECT position_id, ticker, direction,
               ROUND(entry_price::numeric, 2) as entry,
               open_time AT TIME ZONE 'America/Chicago' as open_ct,
               status
        FROM valor_positions
        WHERE status = 'OPEN'
        ORDER BY open_time
    """)
    rows = cur.fetchall()
    if rows:
        for r in rows:
            print(f"  {r[4]} | {r[1]} {r[2]} | entry={r[3]} | status={r[5]}")
        print(f"  *** {len(rows)} OPEN positions — may be stale/stuck ***")
    else:
        print("  (none open)")

    # 5. Config check
    print()
    print("=" * 60)
    print("5. VALOR CONFIG IN DB")
    print("=" * 60)
    try:
        cur.execute("""
            SELECT key, value
            FROM valor_config
            ORDER BY key
        """)
        rows = cur.fetchall()
        if rows:
            for r in rows:
                print(f"  {r[0]} = {str(r[1])[:80]}")
        else:
            print("  (no config rows — using code defaults)")
    except Exception as e:
        print(f"  (valor_config table error: {e})")
        conn.rollback()

    # 6. Most recent scan activity (last 5)
    print()
    print("=" * 60)
    print("6. LAST 5 SCAN ENTRIES")
    print("=" * 60)
    cur.execute("""
        SELECT created_at AT TIME ZONE 'America/Chicago' as ts,
               ticker, outcome,
               COALESCE(LEFT(skip_reason, 80), LEFT(action, 80), '') as reason
        FROM valor_scan_activity
        ORDER BY created_at DESC
        LIMIT 5
    """)
    rows = cur.fetchall()
    if rows:
        for r in rows:
            print(f"  {r[0]} | {r[1]:>4} | {r[2]:>10} | {r[3]}")
    else:
        print("  *** NO SCANS EVER — table is empty ***")

    conn.close()
    print()
    print("Done.")

if __name__ == "__main__":
    run()
