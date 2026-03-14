"""
IronForge Pre-Market Validation — Run in Databricks Notebook BEFORE Monday
===========================================================================

SAFE: All queries are READ-ONLY except Test 1 which creates/drops a temp table.
Run each test cell independently. Copy results into the confidence report.

Created: 2026-03-14
"""

# ═══════════════════════════════════════════════════════════════════════════
# TEST 1: Verify db_execute() returns correct num_affected_rows
# ═══════════════════════════════════════════════════════════════════════════
# This is the foundation of the double-counting guard.
# If UPDATE on an already-closed row returns 1 instead of 0, the guard is BROKEN.

# --- Cell 1A: Setup ---
spark.sql("""
    CREATE TABLE IF NOT EXISTS alpha_prime.ironforge._test_rows_affected (
        id INT, status STRING
    )
""")
spark.sql("""
    INSERT INTO alpha_prime.ironforge._test_rows_affected VALUES (1, 'open')
""")
print("Setup complete: test row inserted with status='open'")

# --- Cell 1B: UPDATE matching row (should return 1) ---
result1 = spark.sql("""
    UPDATE alpha_prime.ironforge._test_rows_affected
    SET status = 'closed'
    WHERE id = 1 AND status = 'open'
""")
rows1 = result1.collect()
affected1 = rows1[0][0] if rows1 else "EMPTY"
print(f"TEST 1B — UPDATE matching row:")
print(f"  Result: {rows1}")
print(f"  num_affected_rows: {affected1}")
print(f"  EXPECTED: 1")
print(f"  STATUS: {'PASS' if affected1 == 1 else 'FAIL ← CRITICAL'}")

# --- Cell 1C: UPDATE non-matching row (should return 0) ---
# Same WHERE clause but status is now 'closed', not 'open'
result2 = spark.sql("""
    UPDATE alpha_prime.ironforge._test_rows_affected
    SET status = 'closed'
    WHERE id = 1 AND status = 'open'
""")
rows2 = result2.collect()
affected2 = rows2[0][0] if rows2 else "EMPTY"
print(f"TEST 1C — UPDATE non-matching row (already closed):")
print(f"  Result: {rows2}")
print(f"  num_affected_rows: {affected2}")
print(f"  EXPECTED: 0")
print(f"  STATUS: {'PASS' if affected2 == 0 else 'FAIL ← DOUBLE-COUNTING GUARD IS BROKEN'}")

# --- Cell 1D: Cleanup ---
spark.sql("DROP TABLE IF EXISTS alpha_prime.ironforge._test_rows_affected")
print("Cleanup complete: test table dropped")


# ═══════════════════════════════════════════════════════════════════════════
# TEST 1E: Verify REST API also returns num_affected_rows correctly
# ═══════════════════════════════════════════════════════════════════════════
# The webapp uses the REST API (not spark.sql). The dbExecute() function
# in databricks-sql.ts parses the response differently:
#   body.result.data_array[0][0] → parseInt → return n
#
# Test this by running the same sequence through the REST API.
# (Requires: DATABRICKS_SERVER_HOSTNAME, DATABRICKS_WAREHOUSE_ID, DATABRICKS_TOKEN)

import requests, os, json, time

def rest_execute(sql):
    """Execute via REST API and return raw response for inspection."""
    host = os.environ.get("DATABRICKS_SERVER_HOSTNAME", "")
    wh_id = os.environ.get("DATABRICKS_WAREHOUSE_ID", "")
    token = os.environ.get("DATABRICKS_TOKEN", "")
    if not all([host, wh_id, token]):
        # Try dbutils.secrets if env vars not set
        try:
            host = dbutils.secrets.get("ironforge", "databricks_host")
            wh_id = dbutils.secrets.get("ironforge", "warehouse_id")
            token = dbutils.secrets.get("ironforge", "token")
        except Exception:
            print("ERROR: No REST API credentials available. Skip this test.")
            return None

    url = f"https://{host}/api/2.0/sql/statements/"
    ts = int(time.time() * 1000)
    resp = requests.post(url, headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }, json={
        "warehouse_id": wh_id,
        "catalog": "alpha_prime",
        "schema": "ironforge",
        "statement": f"{sql} /* test_{ts} */",
        "wait_timeout": "30s",
        "disposition": "INLINE",
        "format": "JSON_ARRAY",
    }, timeout=30)
    return resp.json()

# Only run this if REST credentials are available
# rest_execute("CREATE TABLE IF NOT EXISTS alpha_prime.ironforge._test_rest (id INT, status STRING)")
# rest_execute("INSERT INTO alpha_prime.ironforge._test_rest VALUES (1, 'open')")
# r1 = rest_execute("UPDATE alpha_prime.ironforge._test_rest SET status='closed' WHERE id=1 AND status='open'")
# print(f"REST UPDATE matching: data_array = {r1.get('result',{}).get('data_array',[])} — expect [[1]]")
# r2 = rest_execute("UPDATE alpha_prime.ironforge._test_rest SET status='closed' WHERE id=1 AND status='open'")
# print(f"REST UPDATE non-matching: data_array = {r2.get('result',{}).get('data_array',[])} — expect [[0]]")
# rest_execute("DROP TABLE IF EXISTS alpha_prime.ironforge._test_rest")


# ═══════════════════════════════════════════════════════════════════════════
# TEST 2: Verify Collateral Drift is Zero Right Now
# ═══════════════════════════════════════════════════════════════════════════

# --- Cell 2A: Paper account current state ---
print("TEST 2A — Paper Account State:")
display(spark.sql("""
    SELECT
        dte_mode,
        current_balance,
        collateral_in_use,
        cumulative_pnl,
        buying_power,
        starting_capital,
        total_trades,
        high_water_mark
    FROM alpha_prime.ironforge.flame_paper_account
    WHERE is_active = TRUE
    ORDER BY dte_mode
"""))

display(spark.sql("""
    SELECT
        dte_mode,
        current_balance,
        collateral_in_use,
        cumulative_pnl,
        buying_power,
        starting_capital,
        total_trades
    FROM alpha_prime.ironforge.spark_paper_account
    WHERE is_active = TRUE
    ORDER BY dte_mode
"""))

display(spark.sql("""
    SELECT
        dte_mode,
        current_balance,
        collateral_in_use,
        cumulative_pnl,
        buying_power,
        starting_capital,
        total_trades
    FROM alpha_prime.ironforge.inferno_paper_account
    WHERE is_active = TRUE
    ORDER BY dte_mode
"""))

# --- Cell 2B: Actual open positions (should be 0 on weekend) ---
print("\nTEST 2B — Open Positions (should be 0 rows on weekend):")
for bot in ["flame", "spark", "inferno"]:
    result = spark.sql(f"""
        SELECT
            position_id, dte_mode, status, collateral_required,
            open_time, ticker, expiration
        FROM alpha_prime.ironforge.{bot}_positions
        WHERE status = 'open'
    """)
    count = result.count()
    if count > 0:
        print(f"\n  WARNING: {bot.upper()} has {count} OPEN positions on weekend!")
        display(result)
    else:
        print(f"  {bot.upper()}: 0 open positions ✓")

# --- Cell 2C: Drift check ---
print("\nTEST 2C — Collateral Drift Check:")
for bot in ["flame", "spark", "inferno"]:
    for dte in ["2DTE", "1DTE", "0DTE"]:
        acct = spark.sql(f"""
            SELECT collateral_in_use
            FROM alpha_prime.ironforge.{bot}_paper_account
            WHERE is_active = TRUE AND dte_mode = '{dte}'
            LIMIT 1
        """).collect()
        if not acct:
            continue
        stored_coll = float(acct[0][0] or 0)

        actual = spark.sql(f"""
            SELECT COALESCE(SUM(collateral_required), 0) as actual
            FROM alpha_prime.ironforge.{bot}_positions
            WHERE status = 'open' AND dte_mode = '{dte}'
        """).collect()
        actual_coll = float(actual[0][0] or 0)

        drift = abs(stored_coll - actual_coll)
        status = "✓ NO DRIFT" if drift < 0.01 else f"⚠ DRIFT ${drift:.2f}"
        print(f"  {bot.upper()} {dte}: stored=${stored_coll:.2f} actual=${actual_coll:.2f} [{status}]")

# --- Cell 2D: Balance integrity check ---
print("\nTEST 2D — Balance Integrity (balance should = starting_capital + cumulative_pnl):")
for bot in ["flame", "spark", "inferno"]:
    for dte in ["2DTE", "1DTE", "0DTE"]:
        acct = spark.sql(f"""
            SELECT current_balance, starting_capital, cumulative_pnl
            FROM alpha_prime.ironforge.{bot}_paper_account
            WHERE is_active = TRUE AND dte_mode = '{dte}'
            LIMIT 1
        """).collect()
        if not acct:
            continue
        bal = float(acct[0][0] or 0)
        start = float(acct[0][1] or 0)
        cum_pnl = float(acct[0][2] or 0)
        expected_bal = start + cum_pnl
        drift = abs(bal - expected_bal)
        status = "✓ MATCH" if drift < 0.01 else f"⚠ DRIFT ${drift:.2f}"
        print(f"  {bot.upper()} {dte}: balance=${bal:.2f} expected=${expected_bal:.2f} (start={start}+pnl={cum_pnl:.2f}) [{status}]")

# --- Cell 2E: Cross-check cumulative_pnl against SUM(realized_pnl) ---
print("\nTEST 2E — PnL Cross-Check (cumulative_pnl should = SUM of closed position realized_pnl):")
for bot in ["flame", "spark", "inferno"]:
    for dte in ["2DTE", "1DTE", "0DTE"]:
        acct = spark.sql(f"""
            SELECT cumulative_pnl
            FROM alpha_prime.ironforge.{bot}_paper_account
            WHERE is_active = TRUE AND dte_mode = '{dte}'
            LIMIT 1
        """).collect()
        if not acct:
            continue
        stored_pnl = float(acct[0][0] or 0)

        actual = spark.sql(f"""
            SELECT COALESCE(SUM(realized_pnl), 0) as total_pnl
            FROM alpha_prime.ironforge.{bot}_positions
            WHERE status IN ('closed', 'expired')
              AND realized_pnl IS NOT NULL
              AND dte_mode = '{dte}'
        """).collect()
        actual_pnl = float(actual[0][0] or 0)

        drift = abs(stored_pnl - actual_pnl)
        status = "✓ MATCH" if drift < 0.02 else f"⚠ DRIFT ${drift:.2f}"
        print(f"  {bot.upper()} {dte}: stored_pnl=${stored_pnl:.2f} actual_sum=${actual_pnl:.2f} [{status}]")


# ═══════════════════════════════════════════════════════════════════════════
# TEST 4: Verify EOD Close Timing Logic
# ═══════════════════════════════════════════════════════════════════════════

import pytz
from datetime import datetime

ct = datetime.now(pytz.timezone('US/Central'))
print(f"TEST 4 — EOD Close Timing:")
print(f"  Current CT: {ct.strftime('%Y-%m-%d %H:%M:%S %Z')}")
print(f"  CT offset: {ct.strftime('%z')}")

# The scanner uses is_after_eod_cutoff() which checks ct.hour*100 + ct.minute >= 1445
# EOD cutoff is 14:45 CT (2:45 PM)
hhmm = ct.hour * 100 + ct.minute
print(f"  HHMM now: {hhmm}")
print(f"  EOD cutoff: 1445 (2:45 PM CT)")
print(f"  Is after EOD: {hhmm >= 1445}")
print(f"  Is weekend: {ct.weekday() >= 5}")

# Verify market hours window
print(f"\n  Market window: 830-1500 (8:30 AM - 3:00 PM CT)")
print(f"  Entry window: FLAME/SPARK=830-1400, INFERNO=830-1430")
print(f"  EOD close window: 1445-1510 (2:45 PM - 3:10 PM CT)")
print(f"  Post-EOD sandbox verify: 1445-1510 (FLAME only)")


# ═══════════════════════════════════════════════════════════════════════════
# TEST 10: Verify INFERNO max_contracts Config
# ═══════════════════════════════════════════════════════════════════════════

print("\nTEST 10 — INFERNO Config Check:")

# Check if there's a DB config override
try:
    config_rows = spark.sql("""
        SELECT config_key, config_value
        FROM alpha_prime.ironforge.inferno_config
        WHERE config_key IN ('max_contracts', 'max_trades', 'sd_multiplier')
    """).collect()
    if config_rows:
        print("  DB config overrides (inferno_config table):")
        for row in config_rows:
            print(f"    {row[0]}: {row[1]}")
    else:
        print("  No DB config overrides — using BOT_CONFIG defaults")
        print("  Default max_contracts = 3 (from ironforge_scanner.py line 92)")
        print("  Default max_trades = 0 (unlimited positions)")
except Exception as e:
    print(f"  Config table query failed: {e}")
    print("  This may mean the config table doesn't exist yet (using defaults)")

print("\n  BOT_CONFIG defaults for INFERNO:")
print("    sd=1.0, pt_pct=0.50, sl_mult=3.0, entry_end=1430")
print("    max_trades=0 (unlimited), max_contracts=3, bp_pct=0.85")
print("    starting_capital=10000.0")
print("\n  NOTE: max_trades=0 means INFERNO can have UNLIMITED open positions")
print("  But max_contracts=3 caps each individual position to 3 contracts")
