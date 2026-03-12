# Databricks notebook source

# COMMAND ----------

# MAGIC %md
# MAGIC # Fix Stuck Collateral in IronForge Paper Accounts
# MAGIC
# MAGIC When positions are closed but `collateral_in_use` doesn't get released,
# MAGIC this script detects the mismatch and fixes it for ALL bots.
# MAGIC
# MAGIC **How it works:**
# MAGIC 1. For each bot, sums `collateral_required` from OPEN positions
# MAGIC 2. Compares to `collateral_in_use` in paper_account
# MAGIC 3. If mismatched, resets collateral and recalculates buying_power
# MAGIC
# MAGIC Set `EXECUTE = True` below to apply fixes.

# COMMAND ----------

# ── CONFIGURATION ──────────────────────────────────────────────────────────

EXECUTE = True           # True = apply fixes, False = dry run (show only)
BOT_FILTER = None         # None = all bots, or "flame", "spark", "inferno"

# COMMAND ----------

import os

CATALOG = os.getenv("DATABRICKS_CATALOG", "alpha_prime")
SCHEMA = os.getenv("DATABRICKS_SCHEMA", "ironforge")

# Set timezone to Central
spark.sql("SET TIME ZONE 'America/Chicago'")


def bot_table(bot: str, table: str) -> str:
    return f"{CATALOG}.{SCHEMA}.{bot}_{table}"


def db_query(sql: str) -> list:
    result = spark.sql(sql)
    rows = result.collect()
    if not rows:
        return []
    columns = result.columns
    return [dict(zip(columns, row)) for row in rows]


def db_execute(sql: str):
    spark.sql(sql)


BOTS = [
    {"name": "flame", "dte": "2DTE"},
    {"name": "spark", "dte": "1DTE"},
    {"name": "inferno", "dte": "0DTE"},
]

# COMMAND ----------

def check_and_fix_bot(bot: dict, execute: bool) -> bool:
    """Check a bot for stuck collateral, optionally fix it. Returns True if issue found."""
    name = bot["name"].upper()
    dte = bot["dte"]

    # 1. Get paper account state
    acct_rows = db_query(f"""
        SELECT id, current_balance, cumulative_pnl, collateral_in_use, buying_power,
               total_trades, high_water_mark, max_drawdown, dte_mode
        FROM {bot_table(bot['name'], 'paper_account')}
        WHERE dte_mode = '{dte}'
        ORDER BY id DESC LIMIT 1
    """)
    if not acct_rows:
        print(f"  {name}: No paper account row found for {dte}")
        return False

    acct = acct_rows[0]
    balance = float(acct.get("current_balance") or 0)
    collateral_in_use = float(acct.get("collateral_in_use") or 0)
    buying_power = float(acct.get("buying_power") or 0)
    cumulative_pnl = float(acct.get("cumulative_pnl") or 0)

    # 2. Count actual open positions and their total collateral
    open_rows = db_query(f"""
        SELECT COUNT(*) as cnt,
               COALESCE(SUM(COALESCE(collateral_required, 0)), 0) as total_collateral
        FROM {bot_table(bot['name'], 'positions')}
        WHERE status = 'open' AND dte_mode = '{dte}'
    """)
    open_count = int(open_rows[0].get("cnt") or 0) if open_rows else 0
    actual_collateral = float(open_rows[0].get("total_collateral") or 0) if open_rows else 0

    # 3. Compare
    print(f"\n  {name} ({dte}):")
    print(f"    Balance:          ${balance:,.2f}")
    print(f"    Cumulative P&L:   ${cumulative_pnl:,.2f}")
    print(f"    Collateral in DB: ${collateral_in_use:,.2f}")
    print(f"    Actual collateral (from open positions): ${actual_collateral:,.2f}")
    print(f"    Buying power:     ${buying_power:,.2f}")
    print(f"    Open positions:   {open_count}")

    if abs(collateral_in_use - actual_collateral) < 0.01:
        print(f"    ✓ Collateral is correct")
        return False

    stuck = collateral_in_use - actual_collateral
    correct_bp = balance - actual_collateral
    print(f"    ✗ STUCK COLLATERAL: ${stuck:,.2f}")
    print(f"    → collateral_in_use should be: ${actual_collateral:,.2f}")
    print(f"    → buying_power should be:      ${correct_bp:,.2f}")

    # 4. Check for positions closed with NULL/0 collateral_required
    null_collateral_rows = db_query(f"""
        SELECT COUNT(*) as cnt
        FROM {bot_table(bot['name'], 'positions')}
        WHERE status = 'closed' AND dte_mode = '{dte}'
          AND (collateral_required IS NULL OR collateral_required = 0)
    """)
    null_count = int(null_collateral_rows[0].get("cnt") or 0) if null_collateral_rows else 0
    if null_count > 0:
        print(f"    ⚠ {null_count} closed positions had NULL/0 collateral_required")

    if not execute:
        print(f"    → DRY RUN: Would fix collateral_in_use and buying_power")
        return True

    # 5. Fix it
    db_execute(f"""
        UPDATE {bot_table(bot['name'], 'paper_account')}
        SET collateral_in_use = {actual_collateral},
            buying_power = current_balance - {actual_collateral},
            updated_at = CURRENT_TIMESTAMP()
        WHERE dte_mode = '{dte}'
    """)
    print(f"    ✓ FIXED: collateral_in_use → ${actual_collateral:,.2f}, buying_power → ${correct_bp:,.2f}")

    # 6. Log the fix
    try:
        escaped_msg = f"Fixed stuck collateral: was {stuck:.2f}, now {actual_collateral:.2f}"
        db_execute(f"""
            INSERT INTO {bot_table(bot['name'], 'logs')} (level, message, details, dte_mode)
            VALUES ('RECOVERY',
                    '{escaped_msg}',
                    '{{"stuck_amount": {stuck}, "open_positions": {open_count}, "source": "fix_stuck_collateral"}}',
                    '{dte}')
        """)
    except Exception as e:
        print(f"    ⚠ Could not log fix: {e}")

    return True

# COMMAND ----------

# ── MAIN ──────────────────────────────────────────────────────────────────

print("=" * 60)
print("IronForge Stuck Collateral Fix")
print(f"Mode: {'EXECUTE' if EXECUTE else 'DRY RUN'}")
print("=" * 60)

bots_to_check = BOTS
if BOT_FILTER:
    bots_to_check = [b for b in BOTS if b["name"] == BOT_FILTER]

issues_found = 0
for bot in bots_to_check:
    if check_and_fix_bot(bot, EXECUTE):
        issues_found += 1

print(f"\n{'=' * 60}")
if issues_found == 0:
    print("All bots have correct collateral. No fixes needed.")
elif EXECUTE:
    print(f"Fixed {issues_found} bot(s) with stuck collateral.")
else:
    print(f"Found {issues_found} bot(s) with stuck collateral.")
    print("Set EXECUTE = True and re-run to apply fixes.")
print("=" * 60)
