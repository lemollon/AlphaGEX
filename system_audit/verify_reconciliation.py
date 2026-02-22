#!/usr/bin/env python3
"""
Post-deploy verification for Tradier-to-Bot Reconciliation System.

Fully self-contained: uses direct DB + direct Tradier API calls.
Does NOT require the FastAPI web service (no localhost or external API needed).

Run on Render shell:
    python3 system_audit/verify_reconciliation.py

Tests:
1. All 10 bot position tables exist and have order_id columns
2. Direct Tradier API connectivity (production account)
3. Cross-validation: Tradier positions vs DB live positions
4. Orphan detection (both directions)
"""

import os
import sys
import json
import urllib.request
from datetime import datetime

# ============================================================
# CONFIG
# ============================================================

TRADIER_BASE_URL = 'https://api.tradier.com/v1'

BOT_REGISTRY = [
    ("ANCHOR",      "anchor_positions",     ["put_order_id", "call_order_id"]),
    ("SAMSON",      "samson_positions",      ["put_order_id", "call_order_id"]),
    ("JUBILEE_BOX", "jubilee_positions",     ["put_spread_order_id", "call_spread_order_id"]),
    ("JUBILEE_IC",  "jubilee_ic_positions",  ["put_spread_order_id", "call_spread_order_id"]),
    ("FORTRESS",    "fortress_positions",    ["put_order_id", "call_order_id"]),
    ("FAITH",       "faith_positions",       ["put_order_id", "call_order_id"]),
    ("GRACE",       "grace_positions",       ["put_order_id", "call_order_id"]),
    ("GIDEON",      "gideon_positions",      ["order_id"]),
    ("SOLOMON",     "solomon_positions",     ["order_id"]),
    ("VALOR",       "valor_positions",       ["order_id"]),
]

# ============================================================
# HELPERS
# ============================================================

passed = 0
warned = 0
failed = 0


def ok(msg):
    global passed
    passed += 1
    print(f"  ✅ {msg}")


def warn(msg):
    global warned
    warned += 1
    print(f"  ⚠️  {msg}")


def fail(msg):
    global failed
    failed += 1
    print(f"  ❌ {msg}")


def get_db_connection():
    """Get database connection using psycopg2 directly."""
    import psycopg2
    db_url = os.environ.get('DATABASE_URL')
    if not db_url:
        raise RuntimeError("DATABASE_URL not set")
    return psycopg2.connect(db_url)


def tradier_get(path, account_id=None):
    """Call Tradier API directly. Returns (status_code, data_dict)."""
    api_key = os.environ.get('TRADIER_API_KEY') or os.environ.get('TRADIER_PRODUCTION_TOKEN')
    if not api_key:
        return 0, "TRADIER_API_KEY not set"

    if account_id:
        url = f"{TRADIER_BASE_URL}/accounts/{account_id}{path}"
    else:
        url = f"{TRADIER_BASE_URL}{path}"

    try:
        req = urllib.request.Request(url, headers={
            'Authorization': f'Bearer {api_key}',
            'Accept': 'application/json',
        })
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
            return resp.status, data
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ''
        try:
            body = json.loads(body)
        except Exception:
            pass
        return e.code, body
    except Exception as e:
        return 0, str(e)


# ============================================================
# TEST 1: Database tables and columns
# ============================================================

def test_database_schema():
    print("\n" + "=" * 60)
    print("TEST 1: Database Schema Verification")
    print("=" * 60)

    try:
        conn = get_db_connection()
        cur = conn.cursor()
    except Exception as e:
        fail(f"Cannot connect to database: {e}")
        return

    for bot_name, table, order_cols in BOT_REGISTRY:
        # Check table exists
        cur.execute("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = %s
            )
        """, (table,))
        exists = cur.fetchone()[0]

        if not exists:
            fail(f"{bot_name}: table '{table}' does NOT exist")
            continue

        # Check order ID columns exist
        for col in order_cols:
            cur.execute("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema = 'public'
                    AND table_name = %s AND column_name = %s
                )
            """, (table, col))
            col_exists = cur.fetchone()[0]

            if col_exists:
                ok(f"{bot_name}: {table}.{col} exists")
            else:
                fail(f"{bot_name}: {table}.{col} MISSING")

        # Count positions
        cur.execute(f"""
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE status IN ('open', 'OPEN', 'pending')) AS open_count,
                COUNT(*) FILTER (WHERE status IN ('closed', 'CLOSED', 'expired')) AS closed_count
            FROM {table}
        """)
        total, open_count, closed_count = cur.fetchone()
        print(f"        {bot_name}: {total} total ({open_count} open, {closed_count} closed)")

        # Check for live (non-PAPER) order IDs
        for col in order_cols:
            cur.execute(f"""
                SELECT COUNT(*) FROM {table}
                WHERE {col} IS NOT NULL
                AND {col} != ''
                AND {col} NOT LIKE 'PAPER%%'
            """)
            live_count = cur.fetchone()[0]
            if live_count > 0:
                ok(f"{bot_name}: {live_count} positions with REAL Tradier order IDs in {col}")
            else:
                print(f"        {bot_name}: 0 live order IDs in {col} (all PAPER)")

    cur.close()
    conn.close()


# ============================================================
# TEST 2: Direct Tradier API Verification
# ============================================================

def test_tradier_direct():
    print("\n" + "=" * 60)
    print("TEST 2: Direct Tradier API Verification")
    print("=" * 60)

    api_key = os.environ.get('TRADIER_API_KEY') or os.environ.get('TRADIER_PRODUCTION_TOKEN')
    account_id = os.environ.get('TRADIER_ACCOUNT_ID')

    if not api_key:
        fail("TRADIER_API_KEY not set in environment — cannot test Tradier connectivity")
        return [], []
    if not account_id:
        fail("TRADIER_ACCOUNT_ID not set in environment — cannot test Tradier connectivity")
        return [], []

    print(f"  Account ID: {account_id}")
    print(f"  API Key: {api_key[:8]}...{api_key[-4:]}")

    # 2a: Account balance
    print("\n  --- Account Balance ---")
    status, data = tradier_get('/balances', account_id=account_id)
    if status == 200:
        balances = data.get('balances', {})
        equity = balances.get('total_equity', balances.get('equity', 'N/A'))
        cash = balances.get('total_cash', balances.get('cash', {}).get('cash_available', 'N/A'))
        ok(f"Tradier PRODUCTION connected — equity: ${equity}, cash: ${cash}")
    elif status == 401:
        fail(f"Tradier API key UNAUTHORIZED (401) — check TRADIER_API_KEY")
        return [], []
    else:
        fail(f"Tradier balance returned {status}: {data}")
        return [], []

    # 2b: Open positions
    print("\n  --- Tradier Open Positions ---")
    status, data = tradier_get('/positions', account_id=account_id)
    tradier_positions = []
    if status == 200:
        positions_raw = data.get('positions', {})
        if positions_raw == 'null' or positions_raw is None:
            tradier_positions = []
        elif isinstance(positions_raw, dict):
            pos = positions_raw.get('position', [])
            if isinstance(pos, dict):
                tradier_positions = [pos]
            elif isinstance(pos, list):
                tradier_positions = pos
            else:
                tradier_positions = []
        ok(f"Tradier has {len(tradier_positions)} open positions")
        for p in tradier_positions[:10]:
            print(f"        {p.get('symbol', '?')}: qty={p.get('quantity', '?')} cost=${p.get('cost_basis', '?')}")
    else:
        warn(f"Tradier positions returned {status}: {data}")

    # 2c: Recent orders
    print("\n  --- Tradier Recent Orders ---")
    status, data = tradier_get('/orders', account_id=account_id)
    tradier_orders = []
    if status == 200:
        orders_raw = data.get('orders', {})
        if orders_raw == 'null' or orders_raw is None:
            tradier_orders = []
        elif isinstance(orders_raw, dict):
            ords = orders_raw.get('order', [])
            if isinstance(ords, dict):
                tradier_orders = [ords]
            elif isinstance(ords, list):
                tradier_orders = ords
            else:
                tradier_orders = []
        ok(f"Tradier has {len(tradier_orders)} orders")

        # Show status breakdown
        status_counts = {}
        for o in tradier_orders:
            s = o.get('status', 'unknown')
            status_counts[s] = status_counts.get(s, 0) + 1
        print(f"        Order statuses: {status_counts}")

        # Show recent 5
        for o in tradier_orders[:5]:
            print(f"        Order {o.get('id')}: {o.get('class', '?')} "
                  f"status={o.get('status', '?')} date={o.get('create_date', '?')}")
    else:
        warn(f"Tradier orders returned {status}: {data}")

    return tradier_positions, tradier_orders


# ============================================================
# TEST 3: Cross-validation (DB order IDs vs Tradier orders)
# ============================================================

def test_cross_validation(tradier_positions, tradier_orders):
    print("\n" + "=" * 60)
    print("TEST 3: Cross-Validation (DB vs Tradier)")
    print("=" * 60)

    # Collect all Tradier order IDs
    tradier_order_ids = set()
    for o in tradier_orders:
        oid = o.get('id')
        if oid:
            tradier_order_ids.add(str(oid))

    print(f"\n  Tradier order IDs in account: {len(tradier_order_ids)}")
    print(f"  Tradier open positions: {len(tradier_positions)}")

    # Collect all live order IDs from bot DB tables
    try:
        conn = get_db_connection()
        cur = conn.cursor()
    except Exception as e:
        fail(f"Cannot connect to database: {e}")
        return

    all_db_order_ids = {}  # order_id -> (bot_name, table, status)
    live_open_count = 0

    for bot_name, table, order_cols in BOT_REGISTRY:
        for col in order_cols:
            try:
                cur.execute(f"""
                    SELECT {col}, status FROM {table}
                    WHERE {col} IS NOT NULL
                    AND {col} != ''
                    AND {col} NOT LIKE 'PAPER%%'
                """)
                rows = cur.fetchall()
                for order_id, status in rows:
                    all_db_order_ids[str(order_id)] = (bot_name, table, status)
                    if status in ('open', 'OPEN', 'pending'):
                        live_open_count += 1
            except Exception as e:
                warn(f"Error querying {table}.{col}: {e}")
                conn.rollback()

    print(f"  DB live (non-PAPER) order IDs: {len(all_db_order_ids)}")
    print(f"  DB live open positions: {live_open_count}")

    # 3a: Check DB order IDs exist in Tradier
    if all_db_order_ids:
        orphaned_in_db = []
        matched = []
        for oid, (bot, table, status) in all_db_order_ids.items():
            if oid in tradier_order_ids:
                matched.append((oid, bot, status))
            else:
                orphaned_in_db.append((oid, bot, table, status))

        ok(f"{len(matched)} DB order IDs found in Tradier")
        if orphaned_in_db:
            warn(f"{len(orphaned_in_db)} DB order IDs NOT found in Tradier (orphaned/expired):")
            for oid, bot, table, status in orphaned_in_db[:10]:
                print(f"          {bot}: order_id={oid} status={status} (table={table})")
        else:
            ok("All DB order IDs exist in Tradier — no orphaned DB records")
    else:
        print("  No live order IDs in DB (all bots are PAPER mode)")
        ok("Cross-validation N/A — all bots are PAPER")

    # 3b: Check Tradier orders claimed by a bot
    if tradier_order_ids and all_db_order_ids:
        unclaimed = tradier_order_ids - set(all_db_order_ids.keys())
        claimed = tradier_order_ids & set(all_db_order_ids.keys())

        if unclaimed:
            # Show details of unclaimed orders
            unclaimed_details = [o for o in tradier_orders if str(o.get('id')) in unclaimed]
            # Only warn about filled/open orders (expired/canceled are expected)
            active_unclaimed = [o for o in unclaimed_details
                                if o.get('status') in ('filled', 'open', 'partially_filled', 'pending')]
            if active_unclaimed:
                warn(f"{len(active_unclaimed)} ACTIVE Tradier orders not claimed by any bot:")
                for o in active_unclaimed[:10]:
                    print(f"          Order {o.get('id')}: {o.get('class', '?')} "
                          f"status={o.get('status')} date={o.get('create_date', '?')}")
            else:
                ok(f"All active Tradier orders are claimed by bots "
                   f"({len(unclaimed)} expired/canceled orders excluded)")
        else:
            ok("All Tradier orders are claimed by a bot")

        # Show bot-to-order mapping
        bot_counts = {}
        for oid in claimed:
            bot = all_db_order_ids[oid][0]
            bot_counts[bot] = bot_counts.get(bot, 0) + 1
        if bot_counts:
            print(f"        Orders matched by bot: {bot_counts}")
    elif not tradier_order_ids:
        ok("No Tradier orders to reconcile")

    # 3c: Position count check
    tradier_open = len(tradier_positions)
    print(f"\n  Position count check:")
    print(f"    Tradier open positions: {tradier_open}")
    print(f"    DB live open positions: {live_open_count}")

    if tradier_open == live_open_count:
        ok(f"Position counts MATCH: {tradier_open}")
    elif tradier_open == 0 and live_open_count == 0:
        ok("Both empty (no open positions)")
    elif tradier_open > live_open_count:
        warn(f"Tradier has {tradier_open - live_open_count} MORE positions than DB — possible stranded orders")
    else:
        warn(f"DB has {live_open_count - tradier_open} MORE live positions than Tradier — possible ghost positions")

    cur.close()
    conn.close()


# ============================================================
# MAIN
# ============================================================

if __name__ == '__main__':
    print("=" * 60)
    print("  TRADIER-TO-BOT RECONCILIATION VERIFICATION")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Mode: Direct DB + Direct Tradier API (no FastAPI needed)")
    print("=" * 60)

    test_database_schema()
    tradier_positions, tradier_orders = test_tradier_direct()
    test_cross_validation(tradier_positions, tradier_orders)

    print("\n" + "=" * 60)
    print(f"  RESULTS: {passed} passed, {warned} warnings, {failed} failed")
    if failed > 0:
        print("  STATUS: ❌ ISSUES FOUND — see failures above")
    elif warned > 0:
        print("  STATUS: ⚠️  MOSTLY OK — review warnings above")
    else:
        print("  STATUS: ✅ ALL CHECKS PASSED")
    print("=" * 60)

    sys.exit(1 if failed > 0 else 0)
