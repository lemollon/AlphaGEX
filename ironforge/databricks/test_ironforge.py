"""
IronForge Test Notebook
=======================
Run each section in order to verify the full system works.
Tests: DB connection, Tradier keys, sandbox accounts, paper trading,
and sandbox order placement.

Usage:
  - In a Databricks notebook: paste each cell (separated by # CELL N comments)
  - As a script: python test_ironforge.py (requires env vars set)
"""

import os
import sys
import json
import requests
from datetime import datetime, timedelta

# ============================================================
# CELL 1: Environment Setup
# ============================================================

TRADIER_API_KEY = os.environ.get("TRADIER_API_KEY", "")
TRADIER_SANDBOX_KEY_USER = os.environ.get("TRADIER_SANDBOX_KEY_USER", "")
TRADIER_SANDBOX_KEY_MATT = os.environ.get("TRADIER_SANDBOX_KEY_MATT", "")
TRADIER_SANDBOX_KEY_LOGAN = os.environ.get("TRADIER_SANDBOX_KEY_LOGAN", "")

SANDBOX_KEYS = {
    "USER": TRADIER_SANDBOX_KEY_USER,
    "MATT": TRADIER_SANDBOX_KEY_MATT,
    "LOGAN": TRADIER_SANDBOX_KEY_LOGAN,
}

PROD_URL = "https://api.tradier.com/v1"
SANDBOX_URL = "https://sandbox.tradier.com/v1"

# Track results for final summary
_results = {
    "db": False,
    "prod_quotes": False,
    "spy_price": 0.0,
    "sandbox_accounts": {},
    "sandbox_orders": {},
}

print("Environment loaded")
print(f"  TRADIER_API_KEY: {'set' if TRADIER_API_KEY else 'MISSING'}")
for name, key in SANDBOX_KEYS.items():
    print(f"  TRADIER_SANDBOX_KEY_{name}: {'set' if key else 'MISSING'}")


# ============================================================
# CELL 2: Test Database Connection
# ============================================================

def test_database():
    """Test Databricks SQL connection and table access."""
    print("\n--- Testing Database Connection ---")

    # Try spark.sql (Databricks notebook) or databricks-sql-connector
    try:
        # Databricks notebook environment
        result = spark.sql("SELECT COUNT(*) as cnt FROM alpha_prime.ironforge.bot_heartbeats")  # noqa: F821
        cnt = result.collect()[0].cnt
        print(f"  Database connected — heartbeats table has {cnt} rows")

        result2 = spark.sql("SELECT * FROM alpha_prime.ironforge.flame_paper_account")  # noqa: F821
        for row in result2.collect():
            print(f"  FLAME: balance=${row.current_balance}, buying_power=${row.buying_power}")

        result3 = spark.sql("SELECT * FROM alpha_prime.ironforge.spark_paper_account")  # noqa: F821
        for row in result3.collect():
            print(f"  SPARK: balance=${row.current_balance}, buying_power=${row.buying_power}")

        _results["db"] = True
        return True
    except NameError:
        # Not in Databricks notebook — try databricks-sql-connector
        try:
            from databricks import sql as databricks_sql

            host = os.environ.get("DATABRICKS_HOST", os.environ.get("DATABRICKS_SERVER_HOSTNAME", ""))
            warehouse_id = os.environ.get("DATABRICKS_WAREHOUSE_ID", "")
            http_path = os.environ.get("DATABRICKS_HTTP_PATH", "")
            if not http_path and warehouse_id:
                http_path = f"/sql/1.0/warehouses/{warehouse_id}"
            token = os.environ.get("DATABRICKS_TOKEN", "")

            if not host or not http_path or not token:
                print("  SKIP: Missing DATABRICKS_HOST/HTTP_PATH/TOKEN env vars")
                return False

            conn = databricks_sql.connect(
                server_hostname=host,
                http_path=http_path,
                access_token=token,
                catalog="alpha_prime",
                schema="ironforge",
            )
            with conn.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) as cnt FROM alpha_prime.ironforge.bot_heartbeats")
                row = cursor.fetchone()
                print(f"  Database connected — heartbeats table has {row[0]} rows")

                cursor.execute("SELECT current_balance, buying_power FROM alpha_prime.ironforge.flame_paper_account LIMIT 1")
                row = cursor.fetchone()
                if row:
                    print(f"  FLAME: balance=${row[0]}, buying_power=${row[1]}")

                cursor.execute("SELECT current_balance, buying_power FROM alpha_prime.ironforge.spark_paper_account LIMIT 1")
                row = cursor.fetchone()
                if row:
                    print(f"  SPARK: balance=${row[0]}, buying_power=${row[1]}")

            conn.close()
            _results["db"] = True
            return True
        except Exception as e:
            print(f"  FAILED: {e}")
            return False


test_database()


# ============================================================
# CELL 3: Test Production Tradier Key (quotes)
# ============================================================

def prod_get(endpoint, params=None):
    """GET request to Tradier production API."""
    r = requests.get(
        f"{PROD_URL}/{endpoint}",
        params=params,
        headers={
            "Authorization": f"Bearer {TRADIER_API_KEY}",
            "Accept": "application/json",
        },
        timeout=10,
    )
    return r.status_code, r.json() if r.ok else r.text


def test_production_quotes():
    """Test production Tradier API key with SPY/VIX quotes."""
    print("\n--- Testing Production Tradier Key ---")

    if not TRADIER_API_KEY:
        print("  SKIP: TRADIER_API_KEY not set")
        return False

    try:
        status, data = prod_get("markets/quotes", {"symbols": "SPY,VIX"})
        if status == 200:
            quotes = data.get("quotes", {}).get("quote", [])
            if isinstance(quotes, dict):
                quotes = [quotes]
            for q in quotes:
                sym = q.get("symbol", "?")
                last = q.get("last", "N/A")
                print(f"  {sym}: ${last}")
                if sym == "SPY":
                    _results["spy_price"] = float(last)
            _results["prod_quotes"] = True
            return True
        elif status == 401:
            print(f"  FAILED: 401 Unauthorized — this key is NOT a production key")
            print("  Try testing as sandbox key instead")
            return False
        else:
            print(f"  FAILED: HTTP {status}")
            return False
    except Exception as e:
        print(f"  ERROR: {e}")
        return False


test_production_quotes()


# ============================================================
# CELL 4: Test All 3 Sandbox Keys
# ============================================================

def sandbox_get(key, endpoint, params=None):
    """GET request to Tradier sandbox API."""
    r = requests.get(
        f"{SANDBOX_URL}/{endpoint}",
        params=params,
        headers={
            "Authorization": f"Bearer {key}",
            "Accept": "application/json",
        },
        timeout=10,
    )
    return r.status_code, r.json() if r.ok else r.text


def test_sandbox_accounts():
    """Discover sandbox account IDs for each key."""
    print("\n--- Testing Sandbox Account Discovery ---")

    for name, key in SANDBOX_KEYS.items():
        if not key:
            print(f"  {name}: SKIP (key not set)")
            _results["sandbox_accounts"][name] = None
            continue

        try:
            status, data = sandbox_get(key, "user/profile")
            if status == 200:
                profile = data.get("profile", {})
                account = profile.get("account", {})
                if isinstance(account, list):
                    account = account[0] if account else {}
                acct_id = account.get("account_number", "UNKNOWN")
                _results["sandbox_accounts"][name] = acct_id
                print(f"  {name}: Account {acct_id} (key: {key[:8]}...)")
            elif status == 401:
                print(f"  {name}: FAILED (401 Unauthorized — invalid key)")
                _results["sandbox_accounts"][name] = None
            else:
                print(f"  {name}: FAILED (HTTP {status})")
                _results["sandbox_accounts"][name] = None
        except Exception as e:
            print(f"  {name}: ERROR ({e})")
            _results["sandbox_accounts"][name] = None

    discovered = {k: v for k, v in _results["sandbox_accounts"].items() if v}
    print(f"\n  Discovered {len(discovered)}/3 accounts: {discovered}")


test_sandbox_accounts()


# ============================================================
# CELL 5: Test Sandbox Order Placement (FLAME mirror test)
# ============================================================

def test_sandbox_orders():
    """Place a test Iron Condor order on each sandbox account."""
    print("\n--- Testing Sandbox Order Placement ---")

    spy_price = _results["spy_price"]
    if spy_price == 0:
        print("  SKIP: No SPY price available (production quotes failed)")
        return

    # Get next expiration
    if not TRADIER_API_KEY:
        print("  SKIP: No TRADIER_API_KEY for expirations lookup")
        return

    status, data = prod_get("markets/options/expirations",
                            {"symbol": "SPY", "includeAllRoots": "true"})
    if status != 200:
        print(f"  FAILED: Could not get expirations (HTTP {status})")
        return

    expirations = data.get("expirations", {}).get("date", [])
    today = datetime.now().date()
    expiration = None
    for exp in expirations:
        exp_date = datetime.strptime(exp, "%Y-%m-%d").date()
        if (exp_date - today).days >= 2:
            expiration = exp
            break

    if not expiration:
        print("  FAILED: No expiration found >= 2 DTE")
        return

    print(f"  Expiration: {expiration}")

    # Build conservative test strikes ($10 away from spot, rounded to $5)
    put_short = round((spy_price - 10) / 5) * 5
    put_long = put_short - 5
    call_short = round((spy_price + 10) / 5) * 5
    call_long = call_short + 5

    print(f"  SPY @ ${spy_price:.2f}")
    print(f"  Put spread:  {put_long}/{put_short}")
    print(f"  Call spread: {call_short}/{call_long}")

    # Build OCC symbols
    exp_fmt = datetime.strptime(expiration, "%Y-%m-%d").strftime("%y%m%d")

    def occ(strike, opt_type):
        s = int(strike * 1000)
        return f"SPY{exp_fmt}{opt_type}{s:08d}"

    legs = [
        {"side": "sell_to_open", "option_symbol": occ(put_short, "P")},
        {"side": "buy_to_open", "option_symbol": occ(put_long, "P")},
        {"side": "sell_to_open", "option_symbol": occ(call_short, "C")},
        {"side": "buy_to_open", "option_symbol": occ(call_long, "C")},
    ]

    print(f"\n  Placing test orders (limit $0.10 — will NOT fill)...")

    for name, key in SANDBOX_KEYS.items():
        acct_id = _results["sandbox_accounts"].get(name)
        if not acct_id:
            print(f"  {name}: SKIP (no account ID)")
            _results["sandbox_orders"][name] = None
            continue

        order_data = {
            "class": "multileg",
            "symbol": "SPY",
            "type": "credit",
            "duration": "day",
            "price": "0.10",
        }
        for i, leg in enumerate(legs):
            order_data[f"option_symbol[{i}]"] = leg["option_symbol"]
            order_data[f"side[{i}]"] = leg["side"]
            order_data[f"quantity[{i}]"] = "1"

        try:
            r = requests.post(
                f"{SANDBOX_URL}/accounts/{acct_id}/orders",
                data=order_data,
                headers={
                    "Authorization": f"Bearer {key}",
                    "Accept": "application/json",
                },
                timeout=10,
            )
            if r.status_code == 200:
                order = r.json().get("order", {})
                order_id = order.get("id", "UNKNOWN")
                order_status = order.get("status", "UNKNOWN")
                _results["sandbox_orders"][name] = order_id
                print(f"  {name}: Order #{order_id} ({order_status}) on account {acct_id}")
            else:
                print(f"  {name}: FAILED (HTTP {r.status_code}): {r.text[:200]}")
                _results["sandbox_orders"][name] = None
        except Exception as e:
            print(f"  {name}: ERROR ({e})")
            _results["sandbox_orders"][name] = None


test_sandbox_orders()


# ============================================================
# CELL 6: Write test data to verify dashboard reads it
# ============================================================

def write_test_data():
    """Write heartbeat and log data so the Vercel dashboard has something to show."""
    print("\n--- Writing Test Data ---")

    spy_price = _results["spy_price"] or 0
    sandbox_accounts = _results["sandbox_accounts"]
    sandbox_orders = _results["sandbox_orders"]

    details_json = json.dumps({
        "action": "test",
        "spot": spy_price,
        "vix": 18.5,
        "message": "Test notebook run",
    }).replace("'", "''")

    log_details_json = json.dumps({
        "spy": spy_price,
        "sandbox_accounts": {k: v for k, v in sandbox_accounts.items() if v},
        "sandbox_orders": {k: v for k, v in sandbox_orders.items() if v},
    }).replace("'", "''")

    try:
        # Try Databricks notebook spark.sql
        for bot_name in ["FLAME", "SPARK"]:
            spark.sql(f"""  # noqa: F821
                MERGE INTO alpha_prime.ironforge.bot_heartbeats AS t
                USING (SELECT '{bot_name}' AS bot_name) AS s
                ON t.bot_name = s.bot_name
                WHEN MATCHED THEN UPDATE SET
                    last_heartbeat = CURRENT_TIMESTAMP(),
                    status = 'ok',
                    scan_count = COALESCE(t.scan_count, 0) + 1,
                    details = '{details_json}'
                WHEN NOT MATCHED THEN INSERT
                    (bot_name, last_heartbeat, status, scan_count, details)
                VALUES ('{bot_name}', CURRENT_TIMESTAMP(), 'ok', 1, '{details_json}')
            """)
            print(f"  Heartbeat updated for {bot_name}")

        spark.sql(f"""  # noqa: F821
            INSERT INTO alpha_prime.ironforge.flame_logs
            (log_time, level, message, details, dte_mode)
            VALUES (
                CURRENT_TIMESTAMP(), 'INFO',
                'Test notebook: system verified',
                '{log_details_json}',
                '2DTE'
            )
        """)
        print("  Test log written to flame_logs")
    except NameError:
        # Not in notebook — use databricks-sql-connector
        try:
            from ironforge_scanner import db_execute
            for bot_name in ["FLAME", "SPARK"]:
                db_execute(f"""
                    MERGE INTO alpha_prime.ironforge.bot_heartbeats AS t
                    USING (SELECT '{bot_name}' AS bot_name) AS s
                    ON t.bot_name = s.bot_name
                    WHEN MATCHED THEN UPDATE SET
                        last_heartbeat = CURRENT_TIMESTAMP(),
                        status = 'ok',
                        scan_count = COALESCE(t.scan_count, 0) + 1,
                        details = '{details_json}'
                    WHEN NOT MATCHED THEN INSERT
                        (bot_name, last_heartbeat, status, scan_count, details)
                    VALUES ('{bot_name}', CURRENT_TIMESTAMP(), 'ok', 1, '{details_json}')
                """)
                print(f"  Heartbeat updated for {bot_name}")

            db_execute(f"""
                INSERT INTO alpha_prime.ironforge.flame_logs
                (log_time, level, message, details, dte_mode)
                VALUES (
                    CURRENT_TIMESTAMP(), 'INFO',
                    'Test notebook: system verified',
                    '{log_details_json}',
                    '2DTE'
                )
            """)
            print("  Test log written to flame_logs")
        except Exception as e:
            print(f"  SKIP: Could not write test data ({e})")
            return

write_test_data()


# ============================================================
# CELL 7: Final Summary
# ============================================================

def print_summary():
    """Print final test results."""
    print("\n" + "=" * 60)
    print("  IRONFORGE TEST RESULTS")
    print("=" * 60)

    db_ok = _results["db"]
    quotes_ok = _results["prod_quotes"]
    spy = _results["spy_price"]
    accounts = _results["sandbox_accounts"]
    orders = _results["sandbox_orders"]

    print(f"  Database:          {'OK' if db_ok else 'FAILED'} — alpha_prime.ironforge")
    print(f"  Production quotes: {'OK' if quotes_ok else 'FAILED'}{f' SPY=${spy:.2f}' if spy else ''}")
    print(f"  Sandbox accounts:")
    for name in ["USER", "MATT", "LOGAN"]:
        acct_id = accounts.get(name)
        order_id = orders.get(name)
        acct_status = "OK" if acct_id else "FAILED"
        order_status = f"OK (#{order_id})" if order_id else "FAILED"
        print(f"    {name}: Account {acct_status}"
              f"{f' ({acct_id})' if acct_id else ''}"
              f" | Order: {order_status}")

    print("=" * 60)
    print("\nNEXT STEPS:")
    if not db_ok:
        print("  - Fix database connection (check DATABRICKS_* env vars)")
    if not quotes_ok:
        print("  - Fix TRADIER_API_KEY (must be a production key)")
    missing_accounts = [n for n, v in accounts.items() if not v]
    if missing_accounts:
        print(f"  - Fix sandbox keys for: {', '.join(missing_accounts)}")
    if db_ok and quotes_ok:
        print("  1. Check Vercel dashboard — should show test data")
        print("  2. Deploy ironforge_scanner.py as Databricks Job")
        print("  3. Sandbox orders with $0.10 limit price won't fill (test only)")


print_summary()
