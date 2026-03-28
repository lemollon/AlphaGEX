#!/usr/bin/env python3
"""
IronForge Full System Audit — All 3 Bots
=========================================
Runs all verification queries for Phases 1-4.
Auto-fixes missing columns and missing config rows.
Prints raw results and recommended config updates.

Usage:
  DATABASE_URL=postgresql://... python3 ironforge/scripts/full_system_audit.py

Requires: pip install psycopg2-binary
"""

import os, sys, textwrap
from decimal import Decimal

try:
    import psycopg2
except ImportError:
    print("ERROR: pip install psycopg2-binary"); sys.exit(1)


# ── Helpers ──────────────────────────────────────────────────────────

def get_conn():
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        print("ERROR: DATABASE_URL not set"); sys.exit(1)
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return psycopg2.connect(url)


def q(cur, label, sql, autofix_sql=None):
    """Run query, print results, return rows as dicts."""
    sep = "=" * 60
    print(f"\n{sep}\n  {label}\n{sep}")
    try:
        cur.execute(sql)
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
        print(f"  Rows: {len(rows)}")
        for row in rows:
            print("  ---")
            for c, v in zip(cols, row):
                print(f"    {c}: {v}")
        return [dict(zip(cols, r)) for r in rows]
    except Exception as e:
        print(f"  ERROR: {e}")
        if autofix_sql:
            print(f"  AUTO-FIX: {autofix_sql}")
            try:
                cur.connection.rollback()
                cur.execute(autofix_sql)
                cur.connection.commit()
                print("  AUTO-FIX applied. Retrying query...")
                return q(cur, label + " (retry)", sql)
            except Exception as e2:
                print(f"  AUTO-FIX FAILED: {e2}")
                cur.connection.rollback()
        else:
            cur.connection.rollback()
        return []


def f(v):
    """Format a Decimal/float for display."""
    if v is None: return "NULL"
    return f"{float(v):.2f}"


def pf(label, ok):
    """Print PASS/FAIL."""
    tag = "✅ PASS" if ok else "❌ FAIL"
    print(f"  [{tag}] {label}")
    return ok


# ── Config defaults matching scanner.ts exactly ─────────────────────

CONFIG_DEFAULTS = {
    "flame": {
        "dte_mode": "2DTE", "sd_multiplier": 1.2, "spread_width": 5.0,
        "min_credit": 0.05, "profit_target_pct": 30.0, "stop_loss_pct": 200.0,
        "vix_skip": 32, "max_contracts": 10, "max_trades_per_day": 1,
        "buying_power_usage_pct": 0.85, "min_win_probability": 0.42,
        "entry_start": "08:30", "entry_end": "14:00",
        "eod_cutoff_et": "15:50", "starting_capital": 10000.00,
    },
    "spark": {
        "dte_mode": "1DTE", "sd_multiplier": 1.2, "spread_width": 5.0,
        "min_credit": 0.05, "profit_target_pct": 30.0, "stop_loss_pct": 200.0,
        "vix_skip": 35, "max_contracts": 10, "max_trades_per_day": 1,
        "buying_power_usage_pct": 0.85, "min_win_probability": 0.42,
        "entry_start": "08:30", "entry_end": "14:00",
        "eod_cutoff_et": "15:50", "starting_capital": 10000.00,
    },
    "inferno": {
        "dte_mode": "0DTE", "sd_multiplier": 1.0, "spread_width": 5.0,
        "min_credit": 0.15, "profit_target_pct": 50.0, "stop_loss_pct": 200.0,
        "vix_skip": 32, "max_contracts": 9999, "max_trades_per_day": 0,
        "buying_power_usage_pct": 0.85, "min_win_probability": 0.42,
        "entry_start": "08:30", "entry_end": "13:30",
        "eod_cutoff_et": "15:50", "starting_capital": 10000.00,
    },
}


def insert_config_sql(bot):
    d = CONFIG_DEFAULTS[bot]
    cols = ", ".join(d.keys())
    vals = ", ".join(
        f"'{v}'" if isinstance(v, str) else str(v)
        for v in d.values()
    )
    return f"INSERT INTO {bot}_config ({cols}) VALUES ({vals})"


# ── Main ─────────────────────────────────────────────────────────────

def main():
    conn = get_conn()
    conn.autocommit = True
    cur = conn.cursor()
    recommendations = []

    print("\n" + "#" * 60)
    print("#  IRONFORGE FULL SYSTEM AUDIT")
    print("#" * 60)

    # ================================================================
    # PHASE 1: POST-DEPLOY VERIFICATION
    # ================================================================
    print("\n\n" + "=" * 60)
    print("  PHASE 1: POST-DEPLOY VERIFICATION")
    print("=" * 60)

    # 1A: FLAME Logs — account_type column
    print("\n--- 1A: FLAME Logs Column Check ---")
    rows = q(cur, "Check account_type on flame_logs",
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'flame_logs' AND column_name = 'account_type'")
    if not rows:
        pf("account_type column exists on flame_logs", False)
        print("  Applying ALTER TABLE...")
        try:
            cur.execute("ALTER TABLE flame_logs ADD COLUMN IF NOT EXISTS account_type TEXT")
            print("  Column added.")
        except Exception as e:
            print(f"  ALTER failed: {e}")
    else:
        pf("account_type column exists on flame_logs", True)

    # Quick logs check
    q(cur, "Recent flame_logs", """
        SELECT log_time AT TIME ZONE 'America/Chicago' AS log_ct,
               level, LEFT(message, 80) AS message
        FROM flame_logs ORDER BY log_time DESC LIMIT 5""")

    # 1B: Orphan cleanup
    print("\n--- 1B: Orphan Cleanup Check ---")
    q(cur, "Recent orphan/cleanup log entries", """
        SELECT log_time AT TIME ZONE 'America/Chicago' AS log_ct,
               level, LEFT(message, 120) AS message
        FROM flame_logs
        WHERE message ILIKE '%orphan%' OR message ILIKE '%cleanup%'
           OR message ILIKE '%SANDBOX_CLEANUP%'
        ORDER BY log_time DESC LIMIT 10""")

    # 1C: INFERNO Kelly
    print("\n--- 1C: INFERNO Kelly Sizing ---")
    kelly_rows = q(cur, "Recent INFERNO positions (Kelly columns)", """
        SELECT position_id, contracts, kelly_raw, kelly_half,
               kelly_size_pct, total_credit, oracle_win_probability,
               open_time AT TIME ZONE 'America/Chicago' AS open_ct
        FROM inferno_positions
        ORDER BY open_time DESC LIMIT 5""")

    # Check Kelly columns exist
    kelly_cols = q(cur, "Kelly columns exist?",
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'inferno_positions' AND column_name IN ('kelly_raw','kelly_half','kelly_size_pct')")
    pf(f"Kelly columns exist ({len(kelly_cols)}/3)", len(kelly_cols) == 3)

    if kelly_cols and kelly_rows:
        has_kelly = any(r.get("kelly_raw") is not None for r in kelly_rows)
        pf("Kelly values populated on recent positions", has_kelly)

    # 1D: Paper account drift
    print("\n--- 1D: Paper Account Drift ---")
    for bot in ["flame", "spark", "inferno"]:
        rows = q(cur, f"{bot.upper()} paper account",
            f"SELECT current_balance, starting_capital, cumulative_pnl, "
            f"buying_power, collateral_in_use, "
            f"(current_balance - starting_capital - cumulative_pnl) AS balance_drift, "
            f"(current_balance - (buying_power + collateral_in_use)) AS bp_drift "
            f"FROM {bot}_paper_account WHERE is_active = true")
        if rows:
            bd = float(rows[0].get("balance_drift") or 0)
            bpd = float(rows[0].get("bp_drift") or 0)
            pf(f"{bot.upper()} balance_drift = {bd:.2f}", abs(bd) < 0.02)
            pf(f"{bot.upper()} bp_drift = {bpd:.2f}", abs(bpd) < 0.02)

    # 1E: Config tables
    print("\n--- 1E: Config Tables ---")
    for bot in ["flame", "spark", "inferno"]:
        dte = CONFIG_DEFAULTS[bot]["dte_mode"]
        rows = q(cur, f"{bot.upper()} config",
            f"SELECT * FROM {bot}_config WHERE dte_mode = '{dte}'")
        if not rows:
            pf(f"{bot.upper()} config row exists", False)
            sql = insert_config_sql(bot)
            print(f"  Inserting: {sql[:80]}...")
            try:
                cur.execute(sql)
                print(f"  Inserted {bot.upper()} config row.")
            except Exception as e:
                print(f"  INSERT failed: {e}")
        else:
            pf(f"{bot.upper()} config row exists (dte_mode='{dte}')", True)

    # ================================================================
    # PHASE 2: SPARK DATABASE AUDIT
    # ================================================================
    print("\n\n" + "=" * 60)
    print("  PHASE 2: SPARK DATABASE AUDIT")
    print("=" * 60)

    run_bot_audit(cur, "spark", "1DTE", recommendations)

    # ================================================================
    # PHASE 3: FLAME FULL AUDIT
    # ================================================================
    print("\n\n" + "=" * 60)
    print("  PHASE 3: FLAME FULL AUDIT")
    print("=" * 60)

    run_bot_audit(cur, "flame", "2DTE", recommendations)

    # FLAME-specific: Sandbox close failure rate
    q(cur, "FLAME Q5: Sandbox close failure rate", """
        SELECT
          COUNT(*) AS total_closed,
          COUNT(CASE WHEN sandbox_close_order_id IS NULL THEN 1 END) AS missing_sandbox_close,
          COUNT(CASE WHEN sandbox_close_order_id IS NOT NULL THEN 1 END) AS successful_sandbox_close,
          ROUND(COUNT(CASE WHEN sandbox_close_order_id IS NULL THEN 1 END) * 100.0
            / NULLIF(COUNT(*), 0), 1) AS failure_rate_pct
        FROM flame_positions WHERE status = 'closed'""")

    # FLAME-specific: Sandbox order audit
    q(cur, "FLAME: Recent positions sandbox audit", """
        SELECT position_id,
          CASE WHEN sandbox_order_id IS NULL THEN 'MISSING' ELSE 'OK' END AS open_order,
          CASE WHEN sandbox_close_order_id IS NULL AND status = 'closed'
               THEN 'MISSING' ELSE 'OK' END AS close_order,
          close_reason, status,
          open_time AT TIME ZONE 'America/Chicago' AS open_ct,
          close_time AT TIME ZONE 'America/Chicago' AS close_ct
        FROM flame_positions ORDER BY open_time DESC LIMIT 10""")

    # ================================================================
    # PHASE 4: FINAL SYSTEM HEALTH
    # ================================================================
    print("\n\n" + "=" * 60)
    print("  PHASE 4: FINAL SYSTEM HEALTH CHECK")
    print("=" * 60)

    # 4A: All configs populated
    print("\n--- 4A: Config Summary ---")
    q(cur, "All config rows", """
        SELECT 'FLAME' as bot, dte_mode, min_credit, stop_loss_pct,
          max_contracts, entry_end, vix_skip FROM flame_config
        UNION ALL
        SELECT 'SPARK', dte_mode, min_credit, stop_loss_pct,
          max_contracts, entry_end, vix_skip FROM spark_config
        UNION ALL
        SELECT 'INFERNO', dte_mode, min_credit, stop_loss_pct,
          max_contracts, entry_end, vix_skip FROM inferno_config""")

    # 4B: Paper account drift
    print("\n--- 4B: Paper Account Health ---")
    q(cur, "All paper accounts", """
        SELECT bot, current_balance, buying_power, collateral_in_use,
          (buying_power + collateral_in_use) - current_balance AS drift
        FROM (
          SELECT 'FLAME' as bot, current_balance, buying_power, collateral_in_use
          FROM flame_paper_account WHERE is_active = true
          UNION ALL
          SELECT 'SPARK', current_balance, buying_power, collateral_in_use
          FROM spark_paper_account WHERE is_active = true
          UNION ALL
          SELECT 'INFERNO', current_balance, buying_power, collateral_in_use
          FROM inferno_paper_account WHERE is_active = true
        ) accounts""")

    # 4C: Orphan positions
    print("\n--- 4C: Orphan Positions ---")
    orphans = q(cur, "Open positions from prior days", """
        SELECT 'FLAME' as bot, position_id, status,
          open_time AT TIME ZONE 'America/Chicago' AS open_ct
        FROM flame_positions
        WHERE status = 'open'
          AND DATE(open_time AT TIME ZONE 'America/Chicago') < CURRENT_DATE
        UNION ALL
        SELECT 'SPARK', position_id, status,
          open_time AT TIME ZONE 'America/Chicago' AS open_ct
        FROM spark_positions
        WHERE status = 'open'
          AND DATE(open_time AT TIME ZONE 'America/Chicago') < CURRENT_DATE
        UNION ALL
        SELECT 'INFERNO', position_id, status,
          open_time AT TIME ZONE 'America/Chicago' AS open_ct
        FROM inferno_positions
        WHERE status = 'open'
          AND DATE(open_time AT TIME ZONE 'America/Chicago') < CURRENT_DATE""")
    pf("No orphan positions from prior days", len(orphans) == 0)

    # ================================================================
    # RECOMMENDED CONFIG UPDATES
    # ================================================================
    print("\n\n" + "=" * 60)
    print("  RECOMMENDED CONFIG UPDATES")
    print("  (Review before running — not auto-applied)")
    print("=" * 60)

    if recommendations:
        for r in recommendations:
            print(f"\n  -- {r['reason']}")
            print(f"  {r['sql']};")
    else:
        print("\n  No data-driven config changes recommended at this time.")
        print("  (Insufficient trade data or all metrics within acceptable ranges)")

    print("\n\n  AUDIT COMPLETE.")
    conn.close()


def run_bot_audit(cur, bot, dte, recommendations):
    """Run the standard 7-query audit for a bot."""
    BOT = bot.upper()

    # Q1: Paper account
    q(cur, f"{BOT} Q1: Paper Account Integrity", f"""
        SELECT current_balance, starting_capital, cumulative_pnl,
          buying_power, collateral_in_use,
          (current_balance - starting_capital - cumulative_pnl) AS balance_drift,
          (buying_power + collateral_in_use) AS bp_sum,
          (current_balance - (buying_power + collateral_in_use)) AS bp_drift
        FROM {bot}_paper_account WHERE is_active = true""")

    # Q2: Full trade history
    q(cur, f"{BOT} Q2: Full Trade History", f"""
        SELECT position_id,
          open_time AT TIME ZONE 'America/Chicago' AS open_ct,
          close_time AT TIME ZONE 'America/Chicago' AS close_ct,
          ROUND(EXTRACT(EPOCH FROM (close_time - open_time))/60) AS hold_minutes,
          contracts, total_credit, collateral_required,
          close_price, close_reason, realized_pnl,
          oracle_win_probability, vix_at_entry, status
        FROM {bot}_positions ORDER BY open_time DESC""")

    # Q3: Loss breakdown
    q3 = q(cur, f"{BOT} Q3: Loss Breakdown by Exit Type", f"""
        SELECT close_reason, COUNT(*) AS trades,
          SUM(realized_pnl) AS total_pnl,
          ROUND(AVG(realized_pnl), 2) AS avg_pnl,
          ROUND(MIN(realized_pnl), 2) AS worst,
          ROUND(MAX(realized_pnl), 2) AS best,
          COUNT(CASE WHEN realized_pnl > 0 THEN 1 END) AS winners,
          COUNT(CASE WHEN realized_pnl <= 0 THEN 1 END) AS losers,
          ROUND(COUNT(CASE WHEN realized_pnl > 0 THEN 1 END) * 100.0
            / NULLIF(COUNT(*), 0), 1) AS win_rate_pct
        FROM {bot}_positions WHERE status = 'closed'
        GROUP BY close_reason ORDER BY total_pnl ASC""")

    # Q4: VIX regime
    q(cur, f"{BOT} Q4: P&L by VIX Regime", f"""
        SELECT CASE
            WHEN vix_at_entry < 15 THEN '1.LOW<15'
            WHEN vix_at_entry < 20 THEN '2.NORMAL 15-20'
            WHEN vix_at_entry < 25 THEN '3.ELEVATED 20-25'
            WHEN vix_at_entry < 35 THEN '4.HIGH 25-35'
            ELSE '5.EXTREME 35+' END AS vix_bucket,
          COUNT(*) AS trades, SUM(realized_pnl) AS total_pnl,
          ROUND(AVG(realized_pnl), 2) AS avg_pnl,
          COUNT(CASE WHEN close_reason = 'stop_loss' THEN 1 END) AS stop_losses,
          ROUND(COUNT(CASE WHEN realized_pnl > 0 THEN 1 END) * 100.0
            / NULLIF(COUNT(*), 0), 1) AS win_rate_pct
        FROM {bot}_positions WHERE status = 'closed'
        GROUP BY vix_bucket ORDER BY vix_bucket""")

    # Q5: Day of week
    q5 = q(cur, f"{BOT} Q5: P&L by Day of Week", f"""
        SELECT TO_CHAR(open_time AT TIME ZONE 'America/Chicago', 'Day') AS day_name,
          EXTRACT(DOW FROM open_time AT TIME ZONE 'America/Chicago') AS dow,
          COUNT(*) AS trades, SUM(realized_pnl) AS total_pnl,
          ROUND(AVG(realized_pnl), 2) AS avg_pnl,
          COUNT(CASE WHEN close_reason = 'stop_loss' THEN 1 END) AS stop_losses,
          ROUND(COUNT(CASE WHEN realized_pnl > 0 THEN 1 END) * 100.0
            / NULLIF(COUNT(*), 0), 1) AS win_rate_pct
        FROM {bot}_positions WHERE status = 'closed'
        GROUP BY day_name, dow ORDER BY dow""")

    # Q6: Hour of day
    q(cur, f"{BOT} Q6: P&L by Hour of Day", f"""
        SELECT EXTRACT(HOUR FROM open_time AT TIME ZONE 'America/Chicago') AS hour_ct,
          COUNT(*) AS trades, SUM(realized_pnl) AS total_pnl,
          ROUND(AVG(realized_pnl), 2) AS avg_pnl,
          COUNT(CASE WHEN close_reason = 'stop_loss' THEN 1 END) AS stop_losses,
          ROUND(COUNT(CASE WHEN realized_pnl > 0 THEN 1 END) * 100.0
            / NULLIF(COUNT(*), 0), 1) AS win_rate_pct
        FROM {bot}_positions WHERE status = 'closed'
        GROUP BY hour_ct ORDER BY hour_ct""")

    # Q7: Oracle quality
    q(cur, f"{BOT} Q7: Oracle Signal Quality", f"""
        SELECT ROUND(oracle_win_probability::numeric, 1) AS wp_rounded,
          COUNT(*) AS trades, SUM(realized_pnl) AS total_pnl,
          ROUND(AVG(realized_pnl), 2) AS avg_pnl,
          ROUND(COUNT(CASE WHEN realized_pnl > 0 THEN 1 END) * 100.0
            / NULLIF(COUNT(*), 0), 1) AS actual_win_rate_pct
        FROM {bot}_positions WHERE status = 'closed'
          AND oracle_win_probability IS NOT NULL
        GROUP BY wp_rounded ORDER BY wp_rounded""")

    # ── Analysis ──
    print(f"\n  --- {BOT} ANALYSIS ---")

    # Overall P&L
    try:
        cur.execute(f"""
            SELECT COUNT(*) AS total,
              SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) AS wins,
              SUM(realized_pnl) AS total_pnl,
              ROUND(AVG(CASE WHEN realized_pnl > 0 THEN realized_pnl END), 2) AS avg_win,
              ROUND(AVG(CASE WHEN realized_pnl <= 0 THEN realized_pnl END), 2) AS avg_loss
            FROM {bot}_positions WHERE status = 'closed'""")
        r = cur.fetchone()
        if r and r[0] and r[0] > 0:
            total, wins, pnl, avg_win, avg_loss = r
            wr = wins / total * 100 if total > 0 else 0
            print(f"    Total trades: {total}, Wins: {wins}, WR: {wr:.1f}%")
            print(f"    Total P&L: ${float(pnl or 0):.2f}")
            print(f"    Avg win: ${float(avg_win or 0):.2f}, Avg loss: ${float(avg_loss or 0):.2f}")
            tag = "PROFITABLE" if float(pnl or 0) > 0 else "UNPROFITABLE"
            print(f"    Status: {tag}")
        else:
            print(f"    No closed trades for {BOT}.")
    except Exception as e:
        print(f"    Analysis error: {e}")
        cur.connection.rollback()

    # Friday check — recommend skip if consistently negative
    for row in q5:
        dow = row.get("dow")
        if dow is not None and int(dow) == 5:
            friday_pnl = float(row.get("total_pnl") or 0)
            friday_trades = int(row.get("trades") or 0)
            friday_wr = float(row.get("win_rate_pct") or 0)
            if friday_pnl < -50 and friday_trades >= 3:
                recommendations.append({
                    "reason": f"{BOT} Friday P&L is ${friday_pnl:.0f} over {friday_trades} trades (WR={friday_wr:.0f}%) — consider Friday skip",
                    "sql": f"-- Add Friday skip filter in scanner.ts for {bot} (code change, not config)"
                })


if __name__ == "__main__":
    main()
