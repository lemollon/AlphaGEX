#!/usr/bin/env python3
"""
Reconciliation: Compare what our DB thinks is open vs what Tradier actually has.
Run on Render shell: python3 system_audit/reconcile_positions.py
"""
import os
import json
import urllib.request
from datetime import datetime

print("=" * 60)
print("  DB vs TRADIER POSITION RECONCILIATION")
print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 60)

# Get DB positions
try:
    from database_adapter import get_connection
except ImportError:
    import psycopg2
    def get_connection():
        return psycopg2.connect(os.environ['DATABASE_URL'])

conn = get_connection()
cur = conn.cursor()

print("\n--- DB: Open positions across ALL bots ---")
# Check every positions table for open records
cur.execute("""
    SELECT table_name FROM information_schema.tables
    WHERE table_schema = 'public'
    AND table_name LIKE '%%position%%'
""")
pos_tables = [r[0] for r in cur.fetchall()]

db_open_total = 0
db_open_by_bot = {}

for table in sorted(pos_tables):
    try:
        # Check if table has status column
        cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = %s AND column_name = 'status'
        """, (table,))
        has_status = cur.fetchone() is not None

        if has_status:
            cur.execute(f"SELECT COUNT(*) FROM {table} WHERE status IN ('open', 'OPEN', 'pending')")
            count = cur.fetchone()[0]
            if count > 0:
                print(f"  {table}: {count} open positions")
                db_open_total += count
                db_open_by_bot[table] = count

                # Show details
                # Find key columns
                cur.execute("""
                    SELECT column_name FROM information_schema.columns
                    WHERE table_name = %s
                    AND column_name IN ('position_id', 'ticker', 'symbol', 'expiration', 'open_time', 'entry_credit')
                    ORDER BY column_name
                """, (table,))
                detail_cols = [r[0] for r in cur.fetchall()]
                if detail_cols:
                    cols_str = ', '.join(detail_cols)
                    cur.execute(f"SELECT {cols_str} FROM {table} WHERE status IN ('open', 'OPEN', 'pending') LIMIT 5")
                    rows = cur.fetchall()
                    for row in rows:
                        row_dict = dict(zip(detail_cols, row))
                        parts = []
                        for k, v in row_dict.items():
                            parts.append(f"{k}={v}")
                        print(f"    {' | '.join(parts)}")
        else:
            # No status column - count all rows
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            count = cur.fetchone()[0]
            if count > 0:
                print(f"  {table}: {count} total rows (no status column)")
    except Exception as e:
        print(f"  {table}: Error: {e}")
        conn.rollback()

print(f"\n  TOTAL DB OPEN: {db_open_total}")

# Get Tradier positions
print("\n--- TRADIER: Actual positions on the account ---")
tradier_count = "unknown"
tradier_symbols = []

try:
    API_TOKEN = (
        os.environ.get('TRADIER_PROD_API_KEY')
        or os.environ.get('TRADIER_API_KEY')
        or os.environ.get('TRADIER_API_TOKEN')
    )
    ACCOUNT_ID = os.environ.get('TRADIER_ACCOUNT_ID') or os.environ.get('TRADIER_ACCOUNT')
    BASE_URL = 'https://api.tradier.com/v1'

    if not API_TOKEN or not ACCOUNT_ID:
        print("  Cannot check Tradier: missing API_TOKEN or ACCOUNT_ID")
    else:
        url = f"{BASE_URL}/accounts/{ACCOUNT_ID}/positions"
        req = urllib.request.Request(url, headers={
            'Authorization': f'Bearer {API_TOKEN}',
            'Accept': 'application/json'
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())

        positions = data.get('positions', {})
        if not positions or positions == 'null':
            tradier_count = 0
            print("  No positions on Tradier")
        else:
            pos_list = positions.get('position', [])
            if isinstance(pos_list, dict):
                pos_list = [pos_list]
            tradier_count = len(pos_list)
            print(f"  {tradier_count} positions on Tradier:")
            for p in pos_list:
                symbol = p.get('symbol', '?')
                tradier_symbols.append(symbol)
                print(f"    {symbol}: qty={p.get('quantity', '?')} cost=${p.get('cost_basis', '?')}")

except Exception as e:
    print(f"  Cannot check Tradier: {e}")

# RECONCILIATION
print(f"\n{'='*60}")
print(f"  RECONCILIATION RESULT")
print(f"  DB open positions:      {db_open_total}")
print(f"  Tradier positions:      {tradier_count}")
if isinstance(tradier_count, int):
    if db_open_total == tradier_count == 0:
        print(f"  MATCH (both empty)")
    elif db_open_total == tradier_count:
        print(f"  MATCH")
    elif db_open_total > 0 and tradier_count == 0:
        print(f"  MISMATCH: DB has {db_open_total} open but Tradier has 0")
        print(f"     This means bots are PAPER TRADING - positions only exist in DB")
        if db_open_by_bot:
            print(f"     Paper bots:")
            for table, count in db_open_by_bot.items():
                print(f"       {table}: {count}")
    elif tradier_count > db_open_total:
        print(f"  MISMATCH: Tradier has {tradier_count} but DB only has {db_open_total}")
        print(f"     Orphaned positions on Tradier not tracked in DB!")
    else:
        print(f"  MISMATCH: DB={db_open_total}, Tradier={tradier_count}")
print(f"{'='*60}")

cur.close()
conn.close()
