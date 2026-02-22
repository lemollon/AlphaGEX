#!/usr/bin/env python3
"""
Post-deploy verification for Tradier-to-Bot Reconciliation System.

Run on Render shell:
    python3 system_audit/verify_reconciliation.py

Tests:
1. All 10 bot position tables exist and have order_id columns
2. Tradier production API connectivity
3. Order-to-bot matching logic
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

# On Render, the worker shell can't reach localhost:8000 (that's the web service).
# Use the external URL to hit the API. Override with RENDER_EXTERNAL_URL if needed.
API_BASE = os.environ.get('RENDER_EXTERNAL_URL', 'https://alphagex-api.onrender.com')

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


def api_get(path):
    """Hit an API endpoint and return (status_code, data_dict)."""
    url = f"{API_BASE}{path}"
    try:
        req = urllib.request.Request(url, headers={'Accept': 'application/json'})
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


def get_db_connection():
    """Get database connection."""
    try:
        from database_adapter import get_connection
        return get_connection()
    except ImportError:
        import psycopg2
        return psycopg2.connect(os.environ['DATABASE_URL'])


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
# TEST 2: API Endpoints
# ============================================================

def test_api_endpoints():
    print("\n" + "=" * 60)
    print("TEST 2: API Endpoint Verification")
    print("=" * 60)

    # 2a: Summary endpoint
    print("\n  --- /api/reconciliation/summary ---")
    status, data = api_get('/api/reconciliation/summary')
    if status == 200:
        ok(f"Summary endpoint returned 200")
        if data.get('status') == 'success':
            summary = data.get('data', {})
            bots = summary.get('bots', {})
            print(f"        Bots found: {len(bots)}")
            for bot_name, info in bots.items():
                mode = info.get('mode', '?')
                open_count = info.get('open', 0)
                print(f"          {bot_name}: {mode} | {open_count} open")

            tradier = summary.get('tradier', {})
            if tradier.get('connected'):
                ok(f"Tradier PRODUCTION connected: {tradier.get('open_positions', 0)} positions")
                if tradier.get('symbols'):
                    print(f"        Tradier symbols: {tradier['symbols']}")
            else:
                warn(f"Tradier PRODUCTION not connected: {tradier.get('error', 'unknown')}")

            sandbox = summary.get('tradier_sandbox', {})
            if sandbox.get('connected'):
                ok(f"Tradier SANDBOX connected: {sandbox.get('open_positions', 0)} positions")
            else:
                print(f"        Tradier SANDBOX: not connected (may be expected)")
        else:
            fail(f"Summary returned non-success: {data}")
    elif status == 404:
        fail(f"Summary endpoint returned 404 — route not registered in main.py")
    elif status == 500:
        fail(f"Summary endpoint returned 500: {data}")
    else:
        fail(f"Summary endpoint returned {status}: {data}")

    # 2b: Tradier balance
    print("\n  --- /api/reconciliation/tradier/balance ---")
    status, data = api_get('/api/reconciliation/tradier/balance')
    if status == 200:
        ok(f"Balance endpoint returned 200")
        balance = data.get('balance', {})
        equity = balance.get('total_equity', balance.get('equity', 'N/A'))
        print(f"        Account equity: {equity}")
    else:
        warn(f"Balance endpoint returned {status}: {data}")

    # 2c: Tradier positions
    print("\n  --- /api/reconciliation/tradier/positions ---")
    status, data = api_get('/api/reconciliation/tradier/positions')
    if status == 200:
        ok(f"Positions endpoint returned 200")
        positions = data.get('positions', [])
        print(f"        Tradier has {len(positions)} open positions")
        for p in positions[:10]:
            print(f"          {p.get('symbol', '?')}: qty={p.get('quantity', '?')} cost=${p.get('cost_basis', '?')}")
    else:
        warn(f"Positions endpoint returned {status}: {data}")

    # 2d: Tradier orders (annotated)
    print("\n  --- /api/reconciliation/tradier/orders ---")
    status, data = api_get('/api/reconciliation/tradier/orders?status=all')
    if status == 200:
        ok(f"Orders endpoint returned 200")
        orders = data.get('orders', [])
        print(f"        Total orders: {len(orders)}")

        claimed = [o for o in orders if o.get('bot_owner')]
        unclaimed = [o for o in orders if not o.get('bot_owner')]
        print(f"        Claimed by a bot: {len(claimed)}")
        print(f"        Unclaimed (orphaned): {len(unclaimed)}")

        if unclaimed:
            warn(f"{len(unclaimed)} Tradier orders NOT claimed by any bot:")
            for o in unclaimed[:10]:
                print(f"          Order {o.get('order_id')}: {o.get('tradier_symbol', '?')} "
                      f"status={o.get('status', '?')} date={o.get('create_date', '?')}")
        else:
            ok("All Tradier orders are claimed by a bot")

        # Show bot→order mapping
        if claimed:
            bot_counts = {}
            for o in claimed:
                bot = o.get('bot_owner', '?')
                bot_counts[bot] = bot_counts.get(bot, 0) + 1
            print(f"        Orders by bot: {bot_counts}")
    else:
        warn(f"Orders endpoint returned {status}: {data}")

    # 2e: Full reconciliation
    print("\n  --- /api/reconciliation/full ---")
    status, data = api_get('/api/reconciliation/full')
    if status == 200:
        ok(f"Full reconciliation returned 200")
        report = data.get('data', {})
        summary = report.get('summary', {})

        print(f"        Tradier connected: {summary.get('tradier_connected')}")
        print(f"        Tradier positions: {summary.get('tradier_positions', 0)}")
        print(f"        Tradier orders: {summary.get('tradier_orders', 0)}")
        print(f"        DB positions (total): {summary.get('db_positions_total', 0)}")
        print(f"        DB positions (paper): {summary.get('db_positions_paper', 0)}")
        print(f"        DB positions (live): {summary.get('db_positions_live', 0)}")
        print(f"        Matched orders: {summary.get('matched_orders', 0)}")
        print(f"        Orphaned on Tradier: {summary.get('orphaned_on_tradier', 0)}")
        print(f"        Orphaned in DB: {summary.get('orphaned_in_db', 0)}")
        print(f"        Health: {summary.get('health', '?')}")

        orphaned_tradier = report.get('orphaned_tradier', [])
        if orphaned_tradier:
            warn(f"{len(orphaned_tradier)} orders on Tradier not claimed by any bot:")
            for o in orphaned_tradier[:10]:
                print(f"          Order {o.get('tradier_order_id')}: {o.get('tradier_symbol', '?')} "
                      f"status={o.get('tradier_status', '?')} date={o.get('tradier_create_date', '?')}")

        orphaned_db = report.get('orphaned_db', [])
        if orphaned_db:
            warn(f"{len(orphaned_db)} bot positions with order IDs NOT found in Tradier:")
            for o in orphaned_db[:10]:
                print(f"          {o.get('bot')}: {o.get('position_id')} "
                      f"order={o.get('order_id')} status={o.get('status')}")

        # Per-bot summary
        bots = report.get('bots', {})
        if bots:
            print(f"\n        Per-bot breakdown:")
            for bot_name, info in bots.items():
                print(f"          {bot_name}: {info.get('open', 0)} open, "
                      f"{info.get('closed', 0)} closed, "
                      f"{info.get('paper', 0)} paper, "
                      f"{info.get('live', 0)} live, "
                      f"{info.get('order_ids_tracked', 0)} order IDs tracked")
    elif status == 500:
        fail(f"Full reconciliation returned 500: {json.dumps(data, indent=2) if isinstance(data, dict) else data}")
    else:
        fail(f"Full reconciliation returned {status}: {data}")

    # 2f: Per-bot endpoint (test a few)
    print("\n  --- /api/reconciliation/bot/{name}/positions ---")
    for bot_name in ['ANCHOR', 'SAMSON', 'JUBILEE_IC', 'FORTRESS']:
        status, data = api_get(f'/api/reconciliation/bot/{bot_name}/positions?status=all')
        if status == 200:
            total = data.get('total', 0)
            positions = data.get('positions', [])
            live = [p for p in positions if not p.get('is_paper')]
            paper = [p for p in positions if p.get('is_paper')]
            ok(f"{bot_name}: {total} positions ({len(live)} live, {len(paper)} paper)")
        elif status == 404:
            warn(f"{bot_name}: 404 (bot not found in registry)")
        else:
            warn(f"{bot_name}: returned {status}")


# ============================================================
# TEST 3: Cross-validation
# ============================================================

def test_cross_validation():
    print("\n" + "=" * 60)
    print("TEST 3: Cross-Validation")
    print("=" * 60)

    # Get Tradier positions
    _, tradier_data = api_get('/api/reconciliation/tradier/positions')
    tradier_positions = tradier_data.get('positions', []) if isinstance(tradier_data, dict) else []

    # Get summary
    _, summary_data = api_get('/api/reconciliation/summary')
    summary = summary_data.get('data', {}) if isinstance(summary_data, dict) else {}
    bots = summary.get('bots', {})

    # Count live open across all bots
    total_live_open = sum(b.get('live_open', 0) for b in bots.values())
    tradier_count = len(tradier_positions)

    print(f"\n  Tradier open positions: {tradier_count}")
    print(f"  DB live open positions: {total_live_open}")

    if tradier_count == total_live_open:
        ok(f"Position counts MATCH: {tradier_count}")
    elif tradier_count == 0 and total_live_open == 0:
        ok("Both empty (all bots are PAPER mode)")
    elif tradier_count > total_live_open:
        warn(f"Tradier has {tradier_count - total_live_open} MORE positions than DB tracks — possible stranded orders")
    elif total_live_open > tradier_count:
        warn(f"DB has {total_live_open - tradier_count} MORE live positions than Tradier — possible ghost positions")


# ============================================================
# MAIN
# ============================================================

if __name__ == '__main__':
    print("=" * 60)
    print("  TRADIER-TO-BOT RECONCILIATION VERIFICATION")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  API: {API_BASE}")
    print("=" * 60)

    test_database_schema()
    test_api_endpoints()
    test_cross_validation()

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
