# Databricks notebook source

# COMMAND ----------

# MAGIC %md
# MAGIC # Fix Stuck Collateral in IronForge Paper Accounts
# MAGIC
# MAGIC Collateral can get "stuck" in several ways:
# MAGIC 1. **Stale positions**: Positions past expiration or from a prior day still marked `open`
# MAGIC 2. **Orphan positions**: Open positions with wrong/NULL `dte_mode` that hold collateral invisibly
# MAGIC 3. **Collateral mismatch**: `collateral_in_use` in paper_account doesn't match actual open positions
# MAGIC 4. **Balance drift**: `current_balance` doesn't equal `starting_capital + sum(realized_pnl)`
# MAGIC 5. **Multiple paper_account rows**: Duplicate rows cause fix scripts and dashboard to read different data
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


def db_execute(sql: str) -> int:
    """Execute SQL statement. Returns num_affected_rows for UPDATE/DELETE, 0 otherwise."""
    result = spark.sql(sql)
    try:
        rows = result.collect()
        if rows and len(rows) > 0 and len(rows[0]) > 0:
            val = rows[0][0]
            if isinstance(val, (int, float)):
                return int(val)
    except Exception:
        pass
    return 0


def num(val) -> float:
    """Safely convert to float, handling None/Decimal."""
    if val is None:
        return 0.0
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0


BOTS = [
    {"name": "flame", "dte": "2DTE"},
    {"name": "spark", "dte": "1DTE"},
    {"name": "inferno", "dte": "0DTE"},
]

# COMMAND ----------

def diagnose_bot(bot: dict) -> None:
    """Print full diagnostic info for a bot — shows ALL data the dashboard reads."""
    name = bot["name"].upper()
    dte = bot["dte"]

    # 1. ALL paper_account rows (detect duplicates)
    all_accts = db_query(f"""
        SELECT id, is_active, dte_mode, starting_capital, current_balance,
               cumulative_pnl, collateral_in_use, buying_power, total_trades
        FROM {bot_table(bot['name'], 'paper_account')}
        WHERE dte_mode = '{dte}'
        ORDER BY id
    """)
    print(f"\n  📋 Paper account rows (dte_mode='{dte}'): {len(all_accts)}")
    for i, row in enumerate(all_accts):
        active = "✓ ACTIVE" if row.get("is_active") in (True, "true", 1) else "✗ inactive"
        print(f"    Row {i+1} (id={row['id']}): {active} | "
              f"bal=${num(row.get('current_balance')):,.2f} | "
              f"collateral=${num(row.get('collateral_in_use')):,.2f} | "
              f"bp=${num(row.get('buying_power')):,.2f} | "
              f"pnl=${num(row.get('cumulative_pnl')):,.2f}")

    # 2. ALL open positions (regardless of dte_mode — catch orphans)
    all_open = db_query(f"""
        SELECT position_id, dte_mode, status, collateral_required,
               total_credit, contracts, expiration, open_time
        FROM {bot_table(bot['name'], 'positions')}
        WHERE status = 'open'
        ORDER BY open_time
    """)
    print(f"\n  📋 ALL open positions (any dte_mode): {len(all_open)}")
    for pos in all_open:
        dte_label = pos.get("dte_mode") or "NULL"
        orphan = " ⚠ ORPHAN" if dte_label != dte else ""
        print(f"    {pos['position_id']}: dte={dte_label}{orphan} | "
              f"collateral=${num(pos.get('collateral_required')):,.2f} | "
              f"credit=${num(pos.get('total_credit')):.4f} x{pos.get('contracts')} | "
              f"exp={str(pos.get('expiration', ''))[:10]} | "
              f"opened={str(pos.get('open_time', ''))[:19]}")

    # 3. What the status API would calculate
    live_stats = db_query(f"""
        SELECT COALESCE(SUM(realized_pnl), 0) as total_pnl,
               COUNT(*) as total_trades
        FROM {bot_table(bot['name'], 'positions')}
        WHERE status IN ('closed', 'expired')
          AND realized_pnl IS NOT NULL
          AND dte_mode = '{dte}'
    """)
    api_pnl = num(live_stats[0].get("total_pnl")) if live_stats else 0
    api_trades = int(num(live_stats[0].get("total_trades"))) if live_stats else 0

    live_coll = db_query(f"""
        SELECT COALESCE(SUM(collateral_required), 0) as total_collateral
        FROM {bot_table(bot['name'], 'positions')}
        WHERE status = 'open' AND dte_mode = '{dte}'
    """)
    api_collateral = num(live_coll[0].get("total_collateral")) if live_coll else 0

    # Also check open positions WITHOUT dte filter (orphans that might hold collateral)
    all_open_coll = db_query(f"""
        SELECT COALESCE(SUM(collateral_required), 0) as total_collateral,
               COUNT(*) as cnt
        FROM {bot_table(bot['name'], 'positions')}
        WHERE status = 'open'
    """)
    all_open_collateral = num(all_open_coll[0].get("total_collateral")) if all_open_coll else 0
    all_open_count = int(num(all_open_coll[0].get("cnt"))) if all_open_coll else 0

    api_balance = 10000 + api_pnl  # startingCapital defaults to 10000
    api_bp = api_balance - api_collateral

    print(f"\n  📋 What status API would return:")
    print(f"    balance:    ${api_balance:,.2f} (10000 + {api_pnl:,.2f} from {api_trades} closed/expired trades)")
    print(f"    collateral: ${api_collateral:,.2f} (from dte-filtered open positions)")
    print(f"    buying_pwr: ${api_bp:,.2f}")
    if all_open_collateral != api_collateral:
        print(f"    ⚠ UNFILTERED open collateral: ${all_open_collateral:,.2f} from {all_open_count} positions (dte filter hides ${all_open_collateral - api_collateral:,.2f})")

# COMMAND ----------

def close_stale_positions(bot: dict, execute: bool) -> int:
    """Find and force-close open positions that are expired or from a prior day."""
    name = bot["name"].upper()
    dte = bot["dte"]

    # Also find orphan positions (wrong/NULL dte_mode)
    stale_rows = db_query(f"""
        SELECT position_id, dte_mode, ticker, expiration, total_credit, contracts,
               collateral_required, open_time,
               CAST(expiration AS DATE) AS exp_date,
               CAST(open_time AS DATE) AS open_date,
               CURRENT_DATE() AS today
        FROM {bot_table(bot['name'], 'positions')}
        WHERE status = 'open'
          AND (
              CAST(expiration AS DATE) < CURRENT_DATE()
              OR CAST(open_time AS DATE) < CURRENT_DATE()
              OR dte_mode IS NULL
              OR dte_mode != '{dte}'
          )
        ORDER BY open_time
    """)

    if not stale_rows:
        print(f"    No stale/expired/orphan positions")
        return 0

    closed_count = 0
    for pos in stale_rows:
        pid = pos["position_id"]
        pos_dte = pos.get("dte_mode") or "NULL"
        entry_credit = num(pos["total_credit"])
        contracts = int(num(pos["contracts"]))
        collateral = num(pos["collateral_required"])
        exp_date = str(pos.get("exp_date", ""))[:10]
        open_date = str(pos.get("open_date", ""))[:10]
        today = str(pos.get("today", ""))[:10]

        is_expired = exp_date < today
        is_orphan = pos_dte != dte

        if is_orphan:
            reason = "orphan_force_close"
            close_price = entry_credit
            realized_pnl = 0.0
            label = f"ORPHAN (dte_mode={pos_dte}, expected={dte})"
        elif is_expired:
            reason = "expired_force_close"
            close_price = 0.0
            realized_pnl = round(entry_credit * 100 * contracts, 2)
            label = f"EXPIRED (exp={exp_date})"
        else:
            reason = "stale_holdover_force_close"
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

        # Close the position (use the POSITION's dte_mode, not the bot's)
        # Guard: only proceed with paper_account update if we actually changed the row
        rows_affected = db_execute(f"""
            UPDATE {bot_table(bot['name'], 'positions')}
            SET status = 'closed',
                close_time = CURRENT_TIMESTAMP(),
                close_price = {close_price},
                realized_pnl = {realized_pnl},
                close_reason = '{reason}',
                dte_mode = '{dte}',
                updated_at = CURRENT_TIMESTAMP()
            WHERE position_id = '{pid}'
              AND status = 'open'
        """)

        if rows_affected == 0:
            print(f"      ⚠ SKIPPED: position already closed by another process (double-count prevented)")
            closed_count += 1
            continue

        # Update paper account balance (all rows for this dte)
        if realized_pnl != 0:
            db_execute(f"""
                UPDATE {bot_table(bot['name'], 'paper_account')}
                SET current_balance = current_balance + {realized_pnl},
                    cumulative_pnl = cumulative_pnl + {realized_pnl},
                    total_trades = total_trades + 1,
                    updated_at = CURRENT_TIMESTAMP()
                WHERE dte_mode = '{dte}'
            """)

        # Log it
        try:
            db_execute(f"""
                INSERT INTO {bot_table(bot['name'], 'logs')} (log_time, level, message, details, dte_mode)
                VALUES (CURRENT_TIMESTAMP(), 'RECOVERY',
                        'Force-closed {reason}: {pid} P&L=${realized_pnl:.2f}',
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
    """Reconcile paper_account with actual position data.

    Matches the status API logic exactly:
    - P&L from status IN ('closed', 'expired')
    - Collateral from status = 'open' AND dte_mode filter
    - Updates ALL paper_account rows for this dte_mode
    """
    name = bot["name"].upper()
    dte = bot["dte"]

    # Read paper account (same filter as status API: is_active = TRUE)
    acct_rows = db_query(f"""
        SELECT id, starting_capital, current_balance, cumulative_pnl,
               collateral_in_use, buying_power, total_trades, is_active
        FROM {bot_table(bot['name'], 'paper_account')}
        WHERE is_active = TRUE AND dte_mode = '{dte}'
        ORDER BY id DESC LIMIT 1
    """)
    if not acct_rows:
        # Fallback: try without is_active filter
        acct_rows = db_query(f"""
            SELECT id, starting_capital, current_balance, cumulative_pnl,
                   collateral_in_use, buying_power, total_trades, is_active
            FROM {bot_table(bot['name'], 'paper_account')}
            WHERE dte_mode = '{dte}'
            ORDER BY id DESC LIMIT 1
        """)
    if not acct_rows:
        print(f"    No paper account found for {dte}")
        return False

    acct = acct_rows[0]
    acct_id = acct["id"]
    balance = num(acct.get("current_balance"))
    starting_capital = num(acct.get("starting_capital")) or 10000.0
    collateral_in_use = num(acct.get("collateral_in_use"))
    buying_power = num(acct.get("buying_power"))
    cumulative_pnl = num(acct.get("cumulative_pnl"))

    # Match status API: realized P&L from closed + expired positions
    pnl_rows = db_query(f"""
        SELECT COALESCE(SUM(realized_pnl), 0) as total_pnl,
               COUNT(*) as total_trades
        FROM {bot_table(bot['name'], 'positions')}
        WHERE status IN ('closed', 'expired')
          AND realized_pnl IS NOT NULL
          AND dte_mode = '{dte}'
    """)
    actual_total_pnl = num(pnl_rows[0].get("total_pnl")) if pnl_rows else 0.0
    actual_total_trades = int(num(pnl_rows[0].get("total_trades"))) if pnl_rows else 0
    expected_balance = round(starting_capital + actual_total_pnl, 2)

    # Collateral from open positions (same as status API)
    open_rows = db_query(f"""
        SELECT COUNT(*) as cnt,
               COALESCE(SUM(COALESCE(collateral_required, 0)), 0) as total_collateral
        FROM {bot_table(bot['name'], 'positions')}
        WHERE status = 'open' AND dte_mode = '{dte}'
    """)
    open_count = int(num(open_rows[0].get("cnt"))) if open_rows else 0
    actual_collateral = num(open_rows[0].get("total_collateral")) if open_rows else 0.0

    correct_bp = round(expected_balance - actual_collateral, 2)

    print(f"\n  {name} ({dte}) [paper_account id={acct_id}]:")
    print(f"    Starting capital: ${starting_capital:,.2f}")
    print(f"    Balance:          ${balance:,.2f}")
    print(f"    Expected balance: ${expected_balance:,.2f} (starting + P&L from {actual_total_trades} closed/expired trades)")
    print(f"    Cumulative P&L:   ${cumulative_pnl:,.2f} (stored)")
    print(f"    Actual total P&L: ${actual_total_pnl:,.2f} (from closed+expired trades)")
    print(f"    Collateral in DB: ${collateral_in_use:,.2f}")
    print(f"    Actual collateral: ${actual_collateral:,.2f} (from {open_count} open positions)")
    print(f"    Buying power:     ${buying_power:,.2f}")
    print(f"    Correct BP:       ${correct_bp:,.2f}")

    issues = []

    if abs(collateral_in_use - actual_collateral) > 0.01:
        stuck = collateral_in_use - actual_collateral
        issues.append(f"collateral_mismatch(stuck=${stuck:,.2f})")
        print(f"    ✗ COLLATERAL MISMATCH: ${stuck:,.2f} stuck")

    if abs(balance - expected_balance) > 0.01:
        drift = balance - expected_balance
        issues.append(f"balance_drift(${drift:,.2f})")
        print(f"    ✗ BALANCE DRIFT: ${drift:,.2f}")

    if abs(cumulative_pnl - actual_total_pnl) > 0.01:
        issues.append(f"pnl_mismatch")
        print(f"    ✗ P&L MISMATCH: stored=${cumulative_pnl:,.2f} vs actual=${actual_total_pnl:,.2f}")

    if abs(buying_power - correct_bp) > 0.01:
        issues.append(f"bp_wrong")
        print(f"    ✗ BUYING POWER: ${buying_power:,.2f} should be ${correct_bp:,.2f}")

    if not issues:
        print(f"    ✓ All values correct")
        return False

    if not execute:
        print(f"    → DRY RUN: Would fix {len(issues)} issue(s)")
        return True

    # Fix ALL paper_account rows for this dte_mode (not just one)
    db_execute(f"""
        UPDATE {bot_table(bot['name'], 'paper_account')}
        SET current_balance = {expected_balance},
            cumulative_pnl = {actual_total_pnl},
            collateral_in_use = {actual_collateral},
            buying_power = {correct_bp},
            total_trades = {actual_total_trades},
            high_water_mark = GREATEST(high_water_mark, {expected_balance}),
            updated_at = CURRENT_TIMESTAMP()
        WHERE dte_mode = '{dte}'
    """)

    print(f"    ✓ FIXED (all rows where dte_mode='{dte}'):")
    print(f"      balance:        ${balance:,.2f} → ${expected_balance:,.2f}")
    print(f"      cumulative_pnl: ${cumulative_pnl:,.2f} → ${actual_total_pnl:,.2f}")
    print(f"      collateral:     ${collateral_in_use:,.2f} → ${actual_collateral:,.2f}")
    print(f"      buying_power:   ${buying_power:,.2f} → ${correct_bp:,.2f}")
    print(f"      total_trades:   → {actual_total_trades}")

    try:
        issues_str = ", ".join(issues)
        db_execute(f"""
            INSERT INTO {bot_table(bot['name'], 'logs')} (log_time, level, message, details, dte_mode)
            VALUES (CURRENT_TIMESTAMP(), 'RECOVERY',
                    'Reconciled account: {issues_str}',
                    '{{"old_balance": {balance}, "new_balance": {expected_balance}, "old_collateral": {collateral_in_use}, "new_collateral": {actual_collateral}, "source": "fix_stuck_collateral_v3"}}',
                    '{dte}')
        """)
    except Exception as e:
        print(f"    ⚠ Could not log: {e}")

    return True

# COMMAND ----------

# ── MAIN ──────────────────────────────────────────────────────────────────

print("=" * 60)
print("IronForge Stuck Collateral Fix v3")
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
    print(f"\n{'━' * 60}")
    print(f"  {name} ({bot['dte']})")
    print(f"{'━' * 60}")

    # Phase 0: Full diagnostic
    print(f"\n  Phase 0: Diagnostics...")
    diagnose_bot(bot)

    # Phase 1: Close stale/expired/orphan positions
    print(f"\n  Phase 1: Closing stale/expired/orphan positions...")
    stale_closed = close_stale_positions(bot, EXECUTE)
    total_stale_closed += stale_closed

    # Phase 2: Reconcile collateral + balance + P&L
    print(f"\n  Phase 2: Reconciling account state...")
    if reconcile_collateral(bot, EXECUTE):
        total_reconciled += 1

print(f"\n{'=' * 60}")
print(f"SUMMARY:")
print(f"  Stale/orphan positions closed: {total_stale_closed}")
print(f"  Accounts reconciled:           {total_reconciled}")
if not EXECUTE and (total_stale_closed > 0 or total_reconciled > 0):
    print(f"\n  Set EXECUTE = True and re-run to apply fixes.")
elif total_stale_closed == 0 and total_reconciled == 0:
    print(f"\n  All bots healthy. No fixes needed.")
else:
    print(f"\n  All fixes applied. Refresh the dashboard to verify.")
print("=" * 60)
