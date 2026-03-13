# Databricks notebook source

# COMMAND ----------

# MAGIC %md
# MAGIC # Fix Stuck Collateral in IronForge Paper Accounts
# MAGIC
# MAGIC Collateral can get "stuck" in two ways:
# MAGIC 1. **Stale positions**: Positions past expiration or from a prior day still marked `open`
# MAGIC 2. **Collateral mismatch**: `collateral_in_use` in paper_account doesn't match actual open positions
# MAGIC 3. **Balance drift**: `current_balance` doesn't equal `starting_capital + sum(realized_pnl)`
# MAGIC
# MAGIC **This script fixes ALL three.**
# MAGIC
# MAGIC **How it works:**
# MAGIC 1. For each bot, finds open positions that are expired or stale (opened before today)
# MAGIC 2. Force-closes them at entry credit (break-even) — same as scanner's `stale_holdover` logic
# MAGIC 3. Reconciles `collateral_in_use` with remaining open positions
# MAGIC 4. Validates `current_balance` = `starting_capital + sum(all realized_pnl)`
# MAGIC
# MAGIC Set `EXECUTE = True` below to apply fixes.

# COMMAND ----------

# ── CONFIGURATION ──────────────────────────────────────────────────────────

EXECUTE = True           # True = apply fixes, False = dry run (show only)
BOT_FILTER = None         # None = all bots, or "flame", "spark", "inferno"

# COMMAND ----------

import os
from datetime import datetime

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


def num(val) -> float:
    """Safely convert to float, handling None/Decimal."""
    if val is None:
        return 0.0
    return float(val)


BOTS = [
    {"name": "flame", "dte": "2DTE"},
    {"name": "spark", "dte": "1DTE"},
    {"name": "inferno", "dte": "0DTE"},
]

# COMMAND ----------

def close_stale_positions(bot: dict, execute: bool) -> int:
    """Find and force-close open positions that are expired or from a prior day.

    Returns count of positions closed.
    """
    name = bot["name"].upper()
    dte = bot["dte"]

    # Find open positions that are stale:
    #   - expiration < today (expired)
    #   - open_time date < today (holdover from prior day — scanner should have closed at EOD)
    stale_rows = db_query(f"""
        SELECT position_id, ticker, expiration, total_credit, contracts,
               collateral_required, open_time,
               CAST(expiration AS DATE) AS exp_date,
               CAST(open_time AS DATE) AS open_date,
               CURRENT_DATE() AS today
        FROM {bot_table(bot['name'], 'positions')}
        WHERE status = 'open' AND dte_mode = '{dte}'
          AND (
              CAST(expiration AS DATE) < CURRENT_DATE()
              OR CAST(open_time AS DATE) < CURRENT_DATE()
          )
        ORDER BY open_time
    """)

    if not stale_rows:
        print(f"    No stale/expired open positions")
        return 0

    closed_count = 0
    for pos in stale_rows:
        pid = pos["position_id"]
        entry_credit = num(pos["total_credit"])
        contracts = int(num(pos["contracts"]))
        collateral = num(pos["collateral_required"])
        exp_date = str(pos.get("exp_date", ""))[:10]
        open_date = str(pos.get("open_date", ""))[:10]
        today = str(pos.get("today", ""))[:10]

        is_expired = exp_date < today
        is_holdover = open_date < today

        if is_expired:
            reason = "expired_force_close"
            # Expired worthless = full credit kept = profit
            close_price = 0.0
            realized_pnl = round(entry_credit * 100 * contracts, 2)
            label = f"EXPIRED (exp={exp_date})"
        else:
            reason = "stale_holdover_force_close"
            # Stale holdover: close at entry credit (break-even, conservative)
            close_price = entry_credit
            realized_pnl = 0.0
            label = f"STALE HOLDOVER (opened={open_date})"

        print(f"    ✗ {pid}: {label}")
        print(f"      entry=${entry_credit:.4f} x{contracts}, collateral=${collateral:.2f}")
        print(f"      → close @ ${close_price:.4f}, P&L=${realized_pnl:.2f}")

        if not execute:
            print(f"      → DRY RUN: Would force-close")
            closed_count += 1
            continue

        # Close the position
        db_execute(f"""
            UPDATE {bot_table(bot['name'], 'positions')}
            SET status = 'closed',
                close_time = CURRENT_TIMESTAMP(),
                close_price = {close_price},
                realized_pnl = {realized_pnl},
                close_reason = '{reason}',
                updated_at = CURRENT_TIMESTAMP()
            WHERE position_id = '{pid}'
              AND status = 'open'
              AND dte_mode = '{dte}'
        """)

        # Update paper account balance
        db_execute(f"""
            UPDATE {bot_table(bot['name'], 'paper_account')}
            SET current_balance = current_balance + {realized_pnl},
                cumulative_pnl = cumulative_pnl + {realized_pnl},
                total_trades = total_trades + 1,
                high_water_mark = GREATEST(high_water_mark, current_balance + {realized_pnl}),
                max_drawdown = GREATEST(max_drawdown,
                    GREATEST(high_water_mark, current_balance + {realized_pnl}) - (current_balance + {realized_pnl})),
                updated_at = CURRENT_TIMESTAMP()
            WHERE dte_mode = '{dte}'
        """)

        # Log it
        try:
            db_execute(f"""
                INSERT INTO {bot_table(bot['name'], 'logs')} (log_time, level, message, details, dte_mode)
                VALUES (CURRENT_TIMESTAMP(), 'RECOVERY',
                        'Force-closed stale position {pid}: ${realized_pnl:.2f} [{reason}]',
                        '{{"position_id": "{pid}", "reason": "{reason}", "realized_pnl": {realized_pnl}, "close_price": {close_price}, "source": "fix_stuck_collateral"}}',
                        '{dte}')
            """)
        except Exception as e:
            print(f"      ⚠ Could not log: {e}")

        print(f"      ✓ CLOSED")
        closed_count += 1

    return closed_count

# COMMAND ----------

def reconcile_collateral(bot: dict, execute: bool) -> bool:
    """Reconcile collateral_in_use and buying_power with actual open positions.

    Returns True if a fix was needed.
    """
    name = bot["name"].upper()
    dte = bot["dte"]

    acct_rows = db_query(f"""
        SELECT id, starting_capital, current_balance, cumulative_pnl,
               collateral_in_use, buying_power, total_trades, dte_mode
        FROM {bot_table(bot['name'], 'paper_account')}
        WHERE dte_mode = '{dte}'
        ORDER BY id DESC LIMIT 1
    """)
    if not acct_rows:
        print(f"    No paper account found for {dte}")
        return False

    acct = acct_rows[0]
    balance = num(acct.get("current_balance"))
    starting_capital = num(acct.get("starting_capital"))
    collateral_in_use = num(acct.get("collateral_in_use"))
    buying_power = num(acct.get("buying_power"))
    cumulative_pnl = num(acct.get("cumulative_pnl"))

    # Sum collateral from actual open positions
    open_rows = db_query(f"""
        SELECT COUNT(*) as cnt,
               COALESCE(SUM(COALESCE(collateral_required, 0)), 0) as total_collateral
        FROM {bot_table(bot['name'], 'positions')}
        WHERE status = 'open' AND dte_mode = '{dte}'
    """)
    open_count = int(num(open_rows[0].get("cnt"))) if open_rows else 0
    actual_collateral = num(open_rows[0].get("total_collateral")) if open_rows else 0.0

    # Validate balance: starting_capital + sum(all realized_pnl) should = current_balance
    pnl_rows = db_query(f"""
        SELECT COALESCE(SUM(realized_pnl), 0) as total_pnl
        FROM {bot_table(bot['name'], 'positions')}
        WHERE status = 'closed' AND dte_mode = '{dte}'
          AND realized_pnl IS NOT NULL
    """)
    actual_total_pnl = num(pnl_rows[0].get("total_pnl")) if pnl_rows else 0.0
    expected_balance = starting_capital + actual_total_pnl

    correct_bp = balance - actual_collateral

    print(f"\n  {name} ({dte}):")
    print(f"    Starting capital: ${starting_capital:,.2f}")
    print(f"    Balance:          ${balance:,.2f}")
    print(f"    Expected balance: ${expected_balance:,.2f} (starting + sum of realized P&L)")
    print(f"    Cumulative P&L:   ${cumulative_pnl:,.2f} (stored)")
    print(f"    Actual total P&L: ${actual_total_pnl:,.2f} (from closed trades)")
    print(f"    Collateral in DB: ${collateral_in_use:,.2f}")
    print(f"    Actual collateral: ${actual_collateral:,.2f} (from {open_count} open positions)")
    print(f"    Buying power:     ${buying_power:,.2f}")

    issues = []

    # Check 1: Collateral mismatch
    if abs(collateral_in_use - actual_collateral) > 0.01:
        stuck = collateral_in_use - actual_collateral
        issues.append(f"collateral_mismatch(stuck=${stuck:,.2f})")
        print(f"    ✗ COLLATERAL MISMATCH: ${stuck:,.2f} stuck")

    # Check 2: Balance drift
    if abs(balance - expected_balance) > 0.01:
        drift = balance - expected_balance
        issues.append(f"balance_drift(${drift:,.2f})")
        print(f"    ✗ BALANCE DRIFT: ${drift:,.2f} (balance ${balance:,.2f} != expected ${expected_balance:,.2f})")

    # Check 3: Cumulative P&L mismatch
    if abs(cumulative_pnl - actual_total_pnl) > 0.01:
        pnl_diff = cumulative_pnl - actual_total_pnl
        issues.append(f"pnl_mismatch(${pnl_diff:,.2f})")
        print(f"    ✗ CUMULATIVE P&L MISMATCH: stored=${cumulative_pnl:,.2f} vs actual=${actual_total_pnl:,.2f}")

    # Check 4: Buying power wrong
    if abs(buying_power - correct_bp) > 0.01:
        bp_diff = buying_power - correct_bp
        issues.append(f"bp_wrong(${bp_diff:,.2f})")
        print(f"    ✗ BUYING POWER WRONG: ${buying_power:,.2f} should be ${correct_bp:,.2f}")

    if not issues:
        print(f"    ✓ All values correct")
        return False

    if not execute:
        print(f"    → DRY RUN: Would fix {len(issues)} issue(s): {', '.join(issues)}")
        return True

    # Fix everything: reset balance, cumulative_pnl, collateral, buying_power
    new_balance = expected_balance
    new_cumulative_pnl = actual_total_pnl
    new_collateral = actual_collateral
    new_bp = new_balance - new_collateral

    db_execute(f"""
        UPDATE {bot_table(bot['name'], 'paper_account')}
        SET current_balance = {new_balance},
            cumulative_pnl = {new_cumulative_pnl},
            collateral_in_use = {new_collateral},
            buying_power = {new_bp},
            high_water_mark = GREATEST(high_water_mark, {new_balance}),
            updated_at = CURRENT_TIMESTAMP()
        WHERE dte_mode = '{dte}'
    """)

    print(f"    ✓ FIXED:")
    print(f"      balance:        ${balance:,.2f} → ${new_balance:,.2f}")
    print(f"      cumulative_pnl: ${cumulative_pnl:,.2f} → ${new_cumulative_pnl:,.2f}")
    print(f"      collateral:     ${collateral_in_use:,.2f} → ${new_collateral:,.2f}")
    print(f"      buying_power:   ${buying_power:,.2f} → ${new_bp:,.2f}")

    # Log
    try:
        db_execute(f"""
            INSERT INTO {bot_table(bot['name'], 'logs')} (log_time, level, message, details, dte_mode)
            VALUES (CURRENT_TIMESTAMP(), 'RECOVERY',
                    'Reconciled account: {", ".join(issues)}',
                    '{{"old_balance": {balance}, "new_balance": {new_balance}, "old_collateral": {collateral_in_use}, "new_collateral": {new_collateral}, "old_pnl": {cumulative_pnl}, "new_pnl": {new_cumulative_pnl}, "source": "fix_stuck_collateral"}}',
                    '{dte}')
        """)
    except Exception as e:
        print(f"    ⚠ Could not log: {e}")

    return True

# COMMAND ----------

# ── MAIN ──────────────────────────────────────────────────────────────────

print("=" * 60)
print("IronForge Stuck Collateral Fix")
print(f"Mode: {'EXECUTE' if EXECUTE else 'DRY RUN'}")
print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S CT')}")
print("=" * 60)

bots_to_check = BOTS
if BOT_FILTER:
    bots_to_check = [b for b in BOTS if b["name"] == BOT_FILTER]

total_stale_closed = 0
total_reconciled = 0

for bot in bots_to_check:
    name = bot["name"].upper()
    print(f"\n{'─' * 40}")
    print(f"  {name} ({bot['dte']})")
    print(f"{'─' * 40}")

    # Phase 1: Close stale/expired positions
    print(f"\n  Phase 1: Checking for stale/expired positions...")
    stale_closed = close_stale_positions(bot, EXECUTE)
    total_stale_closed += stale_closed

    # Phase 2: Reconcile collateral + balance
    print(f"\n  Phase 2: Reconciling account state...")
    if reconcile_collateral(bot, EXECUTE):
        total_reconciled += 1

print(f"\n{'=' * 60}")
print(f"SUMMARY:")
print(f"  Stale positions closed: {total_stale_closed}")
print(f"  Accounts reconciled:    {total_reconciled}")
if not EXECUTE and (total_stale_closed > 0 or total_reconciled > 0):
    print(f"\n  Set EXECUTE = True and re-run to apply fixes.")
elif total_stale_closed == 0 and total_reconciled == 0:
    print(f"\n  All bots healthy. No fixes needed.")
else:
    print(f"\n  All fixes applied successfully.")
print("=" * 60)
