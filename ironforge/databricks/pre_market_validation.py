# Databricks notebook source

# COMMAND ----------

# MAGIC %md
# MAGIC # IronForge Pre-Market Validation — Step 2
# MAGIC
# MAGIC Run each cell in order. If A1 or A2 FAIL → **STOP. NO-GO for Monday.**
# MAGIC
# MAGIC | Test | What It Proves | Blocking? |
# MAGIC |------|---------------|-----------|
# MAGIC | A1 | db_execute rows_affected basic | YES |
# MAGIC | A2 | rows_affected with exact close_position() pattern | YES |
# MAGIC | E2 | Race condition (sequential simulation) | YES |
# MAGIC | A3 | All money invariants hold right now | YES |
# MAGIC | A4 | P&L integrity (realized_pnl matches trade math) | INFO |
# MAGIC | A5 | Config overrides (max_contracts, PT/SL) | INFO |
# MAGIC | A6 | FLAME position-to-sandbox reconciliation | INFO |

# COMMAND ----------

# ── Setup ──────────────────────────────────────────────────────────────
import json
from datetime import datetime
from zoneinfo import ZoneInfo

CATALOG = "alpha_prime"
SCHEMA = "ironforge"

def t(name):
    """Full table path."""
    return f"{CATALOG}.{SCHEMA}.{name}"

def bot_table(bot, suffix):
    return f"{CATALOG}.{SCHEMA}.{bot}_{suffix}"

CENTRAL_TZ = ZoneInfo("America/Chicago")
spark.sql("SET TIME ZONE 'America/Chicago'")

PASS = "✅ PASS"
FAIL = "❌ FAIL"
WARN = "⚠️ WARNING"

results = {}

print("Setup complete. Running tests...")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Test A1: db_execute rows_affected — Basic

# COMMAND ----------

# A1: Basic rows_affected test
try:
    spark.sql(f"DROP TABLE IF EXISTS {t('test_validation')}")
    spark.sql(f"""
        CREATE TABLE {t('test_validation')} (
            id INT, status STRING, pnl FLOAT
        )
    """)
    spark.sql(f"INSERT INTO {t('test_validation')} VALUES (1, 'open', 0.0)")

    # UPDATE matching row → expect 1
    r1 = spark.sql(f"""
        UPDATE {t('test_validation')}
        SET status = 'closed', pnl = 50.0
        WHERE id = 1 AND status = 'open'
    """)
    val1 = r1.collect()[0][0]

    # UPDATE no-match (already closed) → expect 0
    r2 = spark.sql(f"""
        UPDATE {t('test_validation')}
        SET status = 'closed', pnl = 50.0
        WHERE id = 1 AND status = 'open'
    """)
    val2 = r2.collect()[0][0]

    spark.sql(f"DROP TABLE {t('test_validation')}")

    if val1 == 1 and val2 == 0:
        results["A1"] = PASS
        print(f"A1: {PASS}")
        print(f"  UPDATE match → {val1} (expected 1)")
        print(f"  UPDATE no-match → {val2} (expected 0)")
    else:
        results["A1"] = FAIL
        print(f"A1: {FAIL}")
        print(f"  UPDATE match → {val1} (expected 1)")
        print(f"  UPDATE no-match → {val2} (expected 0)")
        print("  ⛔ STOP — double-count guard is broken. NO-GO for Monday.")

except Exception as e:
    results["A1"] = f"{FAIL}: {e}"
    print(f"A1: {FAIL} — {e}")
    print("  ⛔ STOP — cannot validate foundation. NO-GO for Monday.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Test A2: db_execute rows_affected — Exact close_position() Pattern

# COMMAND ----------

# A2: Test with exact SQL pattern from close_position()
try:
    spark.sql(f"DROP TABLE IF EXISTS {t('test_close_pattern')}")
    spark.sql(f"""
        CREATE TABLE {t('test_close_pattern')} (
            position_id STRING, status STRING, dte_mode STRING,
            close_time TIMESTAMP, close_price FLOAT,
            realized_pnl FLOAT, close_reason STRING, updated_at TIMESTAMP
        )
    """)
    spark.sql(f"""
        INSERT INTO {t('test_close_pattern')}
        VALUES ('TEST-001', 'open', '1DTE', NULL, NULL, 0.0, NULL, NULL)
    """)

    # Simulate close_position() UPDATE
    r1 = spark.sql(f"""
        UPDATE {t('test_close_pattern')}
        SET status = 'closed',
            close_time = CURRENT_TIMESTAMP(),
            close_price = 1.50,
            realized_pnl = 50.0,
            close_reason = 'test_validation',
            updated_at = CURRENT_TIMESTAMP()
        WHERE position_id = 'TEST-001'
          AND status = 'open'
          AND dte_mode = '1DTE'
    """)
    val1 = r1.collect()[0][0]

    # Simulate DUPLICATE close (race condition)
    r2 = spark.sql(f"""
        UPDATE {t('test_close_pattern')}
        SET status = 'closed',
            close_time = CURRENT_TIMESTAMP(),
            close_price = 1.50,
            realized_pnl = 50.0,
            close_reason = 'test_validation_duplicate',
            updated_at = CURRENT_TIMESTAMP()
        WHERE position_id = 'TEST-001'
          AND status = 'open'
          AND dte_mode = '1DTE'
    """)
    val2 = r2.collect()[0][0]

    # Don't drop yet — E2 reuses this table

    if val1 == 1 and val2 == 0:
        results["A2"] = PASS
        print(f"A2: {PASS} — Delta Lake UPDATE returns correct rows_affected")
    else:
        results["A2"] = FAIL
        print(f"A2: {FAIL}")
        print("  ⛔ STOP — close_position() guard pattern doesn't work. NO-GO for Monday.")
    print(f"  Close pattern → {val1} (expected 1)")
    print(f"  Duplicate close → {val2} (expected 0)")

except Exception as e:
    results["A2"] = f"{FAIL}: {e}"
    print(f"A2: {FAIL} — {e}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Test E2: Race Condition Simulation (Sequential)

# COMMAND ----------

# E2: Simulate scanner + monitor both trying to close same position
try:
    # Reset the test table with a fresh open position
    spark.sql(f"""
        INSERT INTO {t('test_close_pattern')}
        VALUES ('RACE-001', 'open', '1DTE', NULL, NULL, 0.0, NULL, NULL)
    """)

    # Process A (scanner) closes first
    r_a = spark.sql(f"""
        UPDATE {t('test_close_pattern')}
        SET status = 'closed',
            realized_pnl = 50.0,
            close_reason = 'scanner_eod',
            close_time = CURRENT_TIMESTAMP(),
            updated_at = CURRENT_TIMESTAMP()
        WHERE position_id = 'RACE-001'
          AND status = 'open'
          AND dte_mode = '1DTE'
    """)
    rows_a = r_a.collect()[0][0]

    # Process B (monitor) tries the same position
    r_b = spark.sql(f"""
        UPDATE {t('test_close_pattern')}
        SET status = 'closed',
            realized_pnl = 50.0,
            close_reason = 'monitor_stop_loss',
            close_time = CURRENT_TIMESTAMP(),
            updated_at = CURRENT_TIMESTAMP()
        WHERE position_id = 'RACE-001'
          AND status = 'open'
          AND dte_mode = '1DTE'
    """)
    rows_b = r_b.collect()[0][0]

    # Cleanup
    spark.sql(f"DROP TABLE IF EXISTS {t('test_close_pattern')}")

    print(f"E2: Process A (scanner) → rows_affected = {rows_a}")
    print(f"E2: Process B (monitor) → rows_affected = {rows_b}")

    if rows_a == 1 and rows_b == 0:
        results["E2"] = PASS
        print(f"E2: {PASS} — Guard works: only first close succeeds")
    elif rows_a == 1 and rows_b == 1:
        results["E2"] = FAIL
        print(f"E2: {FAIL} — BOTH returned 1! Double-counting WILL happen!")
        print("  ⛔ STOP — Need optimistic locking (version column). NO-GO for Monday.")
    else:
        results["E2"] = f"{FAIL}: unexpected A={rows_a}, B={rows_b}"
        print(f"E2: {FAIL} — Unexpected: A={rows_a}, B={rows_b}")

except Exception as e:
    results["E2"] = f"{FAIL}: {e}"
    print(f"E2: {FAIL} — {e}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Test A3: All Money Invariants — Current State
# MAGIC
# MAGIC Checks INV-1 through INV-5 for all 3 bots.

# COMMAND ----------

# A3: Money invariants for all bots
BOTS = [
    {"name": "flame", "dte": "2DTE"},
    {"name": "spark", "dte": "1DTE"},
    {"name": "inferno", "dte": "0DTE"},
]

all_pass = True
a3_details = []

for bot in BOTS:
    bot_name = bot["name"]
    dte = bot["dte"]
    pos_tbl = bot_table(bot_name, "positions")
    acct_tbl = bot_table(bot_name, "paper_account")

    try:
        # Get paper_account values
        acct_rows = spark.sql(f"""
            SELECT starting_capital, current_balance, cumulative_pnl,
                   collateral_in_use, buying_power
            FROM {acct_tbl}
            WHERE is_active = TRUE AND dte_mode = '{dte}'
            ORDER BY id DESC LIMIT 1
        """).collect()

        if not acct_rows:
            print(f"  {bot_name.upper()}: No active paper_account row found")
            a3_details.append(f"{bot_name.upper()}: NO ACCOUNT")
            all_pass = False
            continue

        acct = acct_rows[0]
        starting_capital = float(acct["starting_capital"] or 10000)
        stored_balance = float(acct["current_balance"] or 0)
        stored_cumulative = float(acct["cumulative_pnl"] or 0)
        stored_collateral = float(acct["collateral_in_use"] or 0)
        stored_bp = float(acct["buying_power"] or 0)

        # Calculate from positions
        stats = spark.sql(f"""
            SELECT
                COALESCE(SUM(CASE WHEN status IN ('closed', 'expired') AND realized_pnl IS NOT NULL
                    THEN realized_pnl ELSE 0 END), 0) as sum_realized_pnl,
                COALESCE(SUM(CASE WHEN status = 'open'
                    THEN collateral_required ELSE 0 END), 0) as sum_open_collateral,
                COUNT(CASE WHEN status = 'open' THEN 1 END) as open_count,
                COUNT(CASE WHEN status = 'open'
                    AND CAST(open_time AS DATE) < CURRENT_DATE() THEN 1 END) as stale_count
            FROM {pos_tbl}
            WHERE dte_mode = '{dte}'
        """).collect()[0]

        sum_pnl = float(stats["sum_realized_pnl"])
        sum_collateral = float(stats["sum_open_collateral"])
        open_count = int(stats["open_count"])
        stale_count = int(stats["stale_count"])

        calculated_balance = round(starting_capital + sum_pnl, 2)
        calculated_bp = round(stored_balance - stored_collateral, 2)

        # Check invariants
        inv1_drift = round(stored_balance - calculated_balance, 2)
        inv2_drift = round(stored_collateral - sum_collateral, 2)
        inv3_drift = round(stored_bp - calculated_bp, 2)

        inv1_ok = abs(inv1_drift) < 0.02
        inv2_ok = abs(inv2_drift) < 0.02
        inv3_ok = abs(inv3_drift) < 0.02
        inv5_ok = stale_count == 0

        bot_pass = inv1_ok and inv2_ok and inv3_ok and inv5_ok

        print(f"\n{'='*60}")
        print(f"  {bot_name.upper()} ({dte})")
        print(f"{'='*60}")
        print(f"  INV-1 balance = starting + sum(pnl):")
        print(f"    stored={stored_balance:.2f}  calculated={calculated_balance:.2f}  drift={inv1_drift:.2f}  {'✅' if inv1_ok else '❌'}")
        print(f"  INV-2 collateral = sum(open collateral):")
        print(f"    stored={stored_collateral:.2f}  actual={sum_collateral:.2f}  drift={inv2_drift:.2f}  {'✅' if inv2_ok else '❌'}")
        print(f"  INV-3 buying_power = balance - collateral:")
        print(f"    stored={stored_bp:.2f}  calculated={calculated_bp:.2f}  drift={inv3_drift:.2f}  {'✅' if inv3_ok else '❌'}")
        print(f"  INV-5 no stale open positions:")
        print(f"    open={open_count}  stale={stale_count}  {'✅' if inv5_ok else '❌'}")

        if not bot_pass:
            all_pass = False
            failures = []
            if not inv1_ok: failures.append(f"INV-1 drift ${inv1_drift}")
            if not inv2_ok: failures.append(f"INV-2 drift ${inv2_drift}")
            if not inv3_ok: failures.append(f"INV-3 drift ${inv3_drift}")
            if not inv5_ok: failures.append(f"INV-5 {stale_count} stale positions")
            a3_details.append(f"{bot_name.upper()}: {', '.join(failures)}")
        else:
            a3_details.append(f"{bot_name.upper()}: all invariants hold")

    except Exception as e:
        print(f"  {bot_name.upper()}: ERROR — {e}")
        a3_details.append(f"{bot_name.upper()}: ERROR {e}")
        all_pass = False

if all_pass:
    results["A3"] = PASS
    print(f"\nA3: {PASS} — All money invariants hold for all bots")
else:
    results["A3"] = FAIL
    print(f"\nA3: {FAIL}")
    for d in a3_details:
        print(f"  {d}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Test A4: P&L Integrity Check

# COMMAND ----------

# A4: Verify realized_pnl = (entry_credit - close_price) * contracts * 100
a4_issues = []

for bot in BOTS:
    bot_name = bot["name"]
    dte = bot["dte"]
    pos_tbl = bot_table(bot_name, "positions")

    try:
        rows = spark.sql(f"""
            SELECT position_id, total_credit, close_price, contracts, realized_pnl,
                   ROUND((total_credit - close_price) * contracts * 100, 2) as calculated_pnl,
                   ROUND(realized_pnl - ROUND((total_credit - close_price) * contracts * 100, 2), 2) as discrepancy
            FROM {pos_tbl}
            WHERE status IN ('closed', 'expired')
              AND close_price IS NOT NULL
              AND contracts IS NOT NULL
              AND realized_pnl IS NOT NULL
              AND dte_mode = '{dte}'
              AND ABS(realized_pnl - ROUND((total_credit - close_price) * contracts * 100, 2)) > 1.0
        """).collect()

        if rows:
            a4_issues.append(f"{bot_name.upper()}: {len(rows)} positions with P&L discrepancy > $1.00")
            for r in rows[:3]:  # Show first 3
                print(f"  {bot_name.upper()} {r['position_id']}: stored=${r['realized_pnl']:.2f} calculated=${r['calculated_pnl']:.2f} diff=${r['discrepancy']:.2f}")
        else:
            print(f"  {bot_name.upper()}: All closed positions P&L matches trade math ✅")

    except Exception as e:
        a4_issues.append(f"{bot_name.upper()}: ERROR {e}")

if not a4_issues:
    results["A4"] = PASS
    print(f"\nA4: {PASS} — P&L integrity verified for all bots")
else:
    results["A4"] = WARN
    print(f"\nA4: {WARN}")
    for issue in a4_issues:
        print(f"  {issue}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Test A5: Config Override Check

# COMMAND ----------

# A5: Check effective config for all bots
for bot in BOTS:
    bot_name = bot["name"]
    dte = bot["dte"]

    try:
        rows = spark.sql(f"""
            SELECT *
            FROM {bot_table(bot_name, 'config')}
            WHERE dte_mode = '{dte}'
            LIMIT 1
        """).collect()

        if rows:
            row = rows[0]
            row_dict = row.asDict()
            print(f"\n{bot_name.upper()} config from DB:")
            for k, v in sorted(row_dict.items()):
                if v is not None:
                    print(f"  {k}: {v}")
        else:
            print(f"\n{bot_name.upper()}: No config row found (using code defaults)")

    except Exception as e:
        print(f"\n{bot_name.upper()}: Config table error — {e}")

results["A5"] = "INFO — review output above"
print(f"\nA5: Check max_contracts values match your expectations")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Test A6: FLAME Position-to-Sandbox Reconciliation

# COMMAND ----------

# A6: FLAME positions from last 7 days — health check
try:
    rows = spark.sql(f"""
        SELECT
            position_id,
            status,
            close_reason,
            open_time,
            close_time,
            collateral_required,
            realized_pnl,
            sandbox_order_id,
            CASE
                WHEN status = 'closed' AND close_reason IS NULL THEN 'WARNING: closed without reason'
                WHEN status = 'closed' AND close_time IS NULL THEN 'WARNING: closed without close_time'
                WHEN status = 'open' THEN 'OPEN — should not exist on weekend'
                ELSE 'OK'
            END as health
        FROM {bot_table('flame', 'positions')}
        WHERE dte_mode = '2DTE'
          AND open_time >= DATE_ADD(CURRENT_DATE(), -7)
        ORDER BY open_time DESC
    """).collect()

    warnings = [r for r in rows if r["health"] != "OK"]
    print(f"A6: FLAME positions (last 7 days): {len(rows)} total, {len(warnings)} warnings")

    for r in rows:
        health = r["health"]
        health_marker = "⚠️" if health != "OK" else "  "
        rpnl = r["realized_pnl"]
        pnl_str = f"${rpnl:.2f}" if rpnl is not None else "N/A"
        sb_col = r["sandbox_order_id"] if "sandbox_order_id" in r.asDict() else None
        has_sandbox = "SB:yes" if sb_col else "SB:no"
        close_reason = r["close_reason"] or "N/A"
        print(f"  {health_marker} {r['position_id'][:20]:20s} {r['status']:8s} {str(close_reason):20s} pnl={pnl_str:>10s} {has_sandbox} [{health}]")

    if warnings:
        results["A6"] = WARN
    else:
        results["A6"] = PASS

except Exception as e:
    results["A6"] = f"{FAIL}: {e}"
    print(f"A6: {FAIL} — {e}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Summary

# COMMAND ----------

# Print final summary
print("=" * 60)
print("  IRONFORGE PRE-MARKET VALIDATION SUMMARY")
print(f"  {datetime.now(CENTRAL_TZ).strftime('%Y-%m-%d %H:%M:%S')} CT")
print("=" * 60)

blocking_fail = False
for test_id in ["A1", "A2", "E2", "A3", "A4", "A5", "A6"]:
    status = results.get(test_id, "NOT RUN")
    print(f"  {test_id}: {status}")
    if test_id in ("A1", "A2", "E2", "A3") and FAIL in str(status):
        blocking_fail = True

print("=" * 60)
if blocking_fail:
    print("  ⛔ NO-GO — Critical test(s) failed. Do NOT merge to main.")
    print("  Fix the failing tests before proceeding.")
else:
    print("  ✅ GO — All critical tests passed. Proceed to Step 3 (API tests).")
print("=" * 60)
