#!/usr/bin/env python3
"""
FULL SYSTEM AUDIT: Are our bots trading with real money or fake paper data?
Run on Render shell: python3 system_audit/audit_all_bots.py
"""
import os
import sys
from datetime import datetime, timedelta


def get_connection():
    """Get DB connection using the app's pattern."""
    try:
        from database_adapter import get_connection as gc
        return gc()
    except Exception:
        import psycopg2
        return psycopg2.connect(os.environ['DATABASE_URL'])


def audit_bot(conn, bot_name, positions_table):
    """Audit a single bot for real vs fake trading."""
    cur = conn.cursor()
    print(f"\n{'='*60}")
    print(f"  BOT: {bot_name}")
    print(f"  Table: {positions_table}")
    print(f"{'='*60}")

    # CHECK 1: Does the table exist?
    cur.execute("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = %s
        )
    """, (positions_table,))
    if not cur.fetchone()[0]:
        print(f"  Table {positions_table} does NOT exist")
        return

    # CHECK 2: How many trades?
    try:
        cur.execute(f"SELECT COUNT(*) FROM {positions_table}")
        total = cur.fetchone()[0]
        print(f"  Total rows: {total}")
    except Exception as e:
        print(f"  Query failed: {e}")
        conn.rollback()
        return

    if total == 0:
        print(f"  No trades at all")
        return

    # CHECK 3: Are trades identical? (THE SAMSON TEST)
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = %s
        AND column_name IN ('entry_credit', 'entry_price', 'credit', 'premium', 'fill_price')
    """, (positions_table,))
    credit_cols = [r[0] for r in cur.fetchall()]

    if credit_cols:
        credit_col = credit_cols[0]
        cur.execute(f"""
            SELECT {credit_col}, COUNT(*) as cnt
            FROM {positions_table}
            GROUP BY {credit_col}
            ORDER BY cnt DESC
            LIMIT 5
        """)
        distribution = cur.fetchall()
        print(f"  Entry credit distribution ({credit_col}):")
        for val, cnt in distribution:
            pct = cnt / total * 100
            flag = " SUSPICIOUS" if pct > 80 and total > 10 else ""
            print(f"    ${val}: {cnt} trades ({pct:.1f}%){flag}")

        if distribution and distribution[0][1] / total > 0.90 and total > 20:
            print(f"  FAKE ALERT: {distribution[0][1]/total*100:.0f}% of trades have identical entry credit")

    # CHECK 4: P&L distribution
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = %s
        AND column_name IN ('realized_pnl', 'pnl', 'profit', 'profit_loss')
    """, (positions_table,))
    pnl_cols = [r[0] for r in cur.fetchall()]

    if pnl_cols:
        pnl_col = pnl_cols[0]
        cur.execute(f"""
            SELECT {pnl_col}, COUNT(*) as cnt
            FROM {positions_table}
            WHERE {pnl_col} IS NOT NULL AND {pnl_col} != 0
            GROUP BY {pnl_col}
            ORDER BY cnt DESC
            LIMIT 5
        """)
        pnl_dist = cur.fetchall()
        print(f"  P&L distribution ({pnl_col}):")
        for val, cnt in pnl_dist:
            pct = cnt / total * 100
            flag = " ALL IDENTICAL" if pct > 80 and total > 10 else ""
            print(f"    ${val}: {cnt} trades ({pct:.1f}%){flag}")

    # CHECK 5: Win rate (100% = almost certainly fake)
    if pnl_cols:
        pnl_col = pnl_cols[0]
        cur.execute(f"""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN {pnl_col} > 0 THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN {pnl_col} <= 0 THEN 1 ELSE 0 END) as losses,
                ROUND(SUM(CASE WHEN {pnl_col} > 0 THEN 1 ELSE 0 END)::numeric
                    / NULLIF(COUNT(*), 0) * 100, 1) as win_rate
            FROM {positions_table}
            WHERE {pnl_col} IS NOT NULL AND {pnl_col} != 0
        """)
        row = cur.fetchone()
        if row and row[0] > 0:
            total_pnl_rows, wins, losses, win_rate = row
            flag = " IMPOSSIBLE" if win_rate and float(win_rate) >= 99 and int(total_pnl_rows) > 20 else ""
            print(f"  Win rate: {win_rate}% ({wins}W / {losses}L){flag}")

    # CHECK 6: Hold time distribution
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = %s
        AND column_name IN ('opened_at', 'open_time', 'created_at', 'entry_time')
    """, (positions_table,))
    open_cols = [r[0] for r in cur.fetchall()]

    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = %s
        AND column_name IN ('closed_at', 'close_time', 'exit_time')
    """, (positions_table,))
    close_cols = [r[0] for r in cur.fetchall()]

    if open_cols and close_cols:
        open_col, close_col = open_cols[0], close_cols[0]
        try:
            cur.execute(f"""
                SELECT
                    ROUND(AVG(EXTRACT(EPOCH FROM ({close_col} - {open_col})) / 60)::numeric, 1) as avg_hold_min,
                    ROUND(MIN(EXTRACT(EPOCH FROM ({close_col} - {open_col})) / 60)::numeric, 1) as min_hold_min,
                    ROUND(MAX(EXTRACT(EPOCH FROM ({close_col} - {open_col})) / 60)::numeric, 1) as max_hold_min,
                    ROUND(STDDEV(EXTRACT(EPOCH FROM ({close_col} - {open_col})) / 60)::numeric, 2) as stddev_hold_min
                FROM {positions_table}
                WHERE {close_col} IS NOT NULL AND {open_col} IS NOT NULL
            """)
            hold = cur.fetchone()
            if hold and hold[0]:
                stddev = float(hold[3]) if hold[3] else 0
                flag = " ZERO VARIANCE = FAKE" if stddev < 0.5 and total > 20 else ""
                print(f"  Hold time: avg={hold[0]}min, min={hold[1]}min, max={hold[2]}min, stddev={hold[3]}min{flag}")
        except Exception as e:
            print(f"  Hold time query failed: {e}")
            conn.rollback()

    # CHECK 7: Recent activity
    if close_cols:
        close_col = close_cols[0]
        try:
            cur.execute(f"""
                SELECT MAX({close_col}) as last_trade
                FROM {positions_table}
                WHERE {close_col} IS NOT NULL
            """)
            last = cur.fetchone()
            if last and last[0]:
                if hasattr(last[0], 'tzinfo') and last[0].tzinfo:
                    days_ago = (datetime.now(last[0].tzinfo) - last[0]).days
                else:
                    days_ago = (datetime.now() - last[0]).days
                flag = " STALE" if isinstance(days_ago, int) and days_ago > 3 else ""
                print(f"  Last trade: {last[0]} ({days_ago} days ago){flag}")
        except Exception as e:
            print(f"  Last trade query failed: {e}")
            conn.rollback()

    # CHECK 8: Open positions still sitting
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = %s AND column_name = 'status'
    """, (positions_table,))
    if cur.fetchone():
        try:
            cur.execute(f"SELECT COUNT(*) FROM {positions_table} WHERE status IN ('open', 'pending', 'OPEN')")
            open_count = cur.fetchone()[0]
            if open_count > 0:
                print(f"  {open_count} positions still OPEN")
        except Exception as e:
            print(f"  Open count query failed: {e}")
            conn.rollback()


def main():
    print("=" * 60)
    print("  ALPHAGEX FULL SYSTEM AUDIT - REAL vs FAKE DATA")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    conn = get_connection()

    # DISCOVER ALL POSITION/TRADE TABLES
    cur = conn.cursor()
    cur.execute("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public'
        AND (table_name LIKE '%%position%%' OR table_name LIKE '%%trade%%' OR table_name LIKE '%%closed%%')
        ORDER BY table_name
    """)
    all_tables = [r[0] for r in cur.fetchall()]
    cur.close()

    print(f"\nDiscovered {len(all_tables)} position/trade tables:")
    for t in all_tables:
        print(f"  - {t}")

    # MAP KNOWN BOTS TO TABLES
    bot_map = {
        "SAMSON": "samson_positions",
        "SAMSON (closed)": "samson_closed_trades",
        "JUBILEE IC": "jubilee_ic_positions",
        "JUBILEE IC (closed)": "jubilee_ic_closed_trades",
        "JUBILEE Box": "jubilee_positions",
        "ANCHOR": "anchor_positions",
        "ANCHOR (closed)": "anchor_closed_trades",
        "GIDEON": "gideon_positions",
        "GIDEON (closed)": "gideon_closed_trades",
        "FAITH": "faith_positions",
        "FAITH (closed)": "faith_closed_trades",
        "SOLOMON": "solomon_positions",
        "FORTRESS": "fortress_positions",
        "VALOR": "valor_positions",
        "AGAPE-SPOT": "agape_spot_positions",
    }

    # Check for unmapped tables
    mapped_tables = set(bot_map.values())
    unmapped = [t for t in all_tables if t not in mapped_tables and 'archive' not in t]
    if unmapped:
        print(f"\nUnmapped tables (may be additional bots):")
        for t in unmapped:
            print(f"  - {t}")
            bot_map[f"UNKNOWN ({t})"] = t

    # AUDIT EACH BOT
    for bot_name, table in sorted(bot_map.items()):
        try:
            audit_bot(conn, bot_name, table)
        except Exception as e:
            print(f"\n  AUDIT FAILED for {bot_name}: {e}")
            conn.rollback()

    # FINAL SUMMARY
    print(f"\n{'='*60}")
    print(f"  FULL SYSTEM AUDIT COMPLETE")
    print(f"  Review each bot above for SUSPICIOUS/FAKE/IMPOSSIBLE flags")
    print(f"  Any bot with identical trades/P&L/hold times is PAPER")
    print(f"  Any bot with no recent trades is DEAD")
    print(f"{'='*60}")

    conn.close()


if __name__ == "__main__":
    main()
