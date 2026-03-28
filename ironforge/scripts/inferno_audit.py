#!/usr/bin/env python3
"""
INFERNO Audit Script — Parts 2 & 3
===================================
Runs all 10 database queries and performs loss analysis.
Outputs raw results, analysis, and recommended DB UPDATE statements.

Usage:
  DATABASE_URL=postgresql://... python3 ironforge/scripts/inferno_audit.py

Requires: psycopg2-binary (pip install psycopg2-binary)
"""

import os
import sys
from decimal import Decimal

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    print("ERROR: psycopg2-binary not installed. Run: pip install psycopg2-binary")
    sys.exit(1)


def get_conn():
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        print("ERROR: DATABASE_URL environment variable not set")
        sys.exit(1)
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return psycopg2.connect(url)


def run_query(cur, label, sql, show_cols=True):
    """Run a query, print results, return rows as dicts."""
    print(f"\n{'=' * 70}")
    print(f"  {label}")
    print(f"{'=' * 70}")
    cur.execute(sql)
    cols = [d[0] for d in cur.description]
    rows = cur.fetchall()
    if show_cols:
        print(f"  Columns: {', '.join(cols)}")
    print(f"  Rows: {len(rows)}")
    print()
    for i, row in enumerate(rows):
        if show_cols:
            for c, v in zip(cols, row):
                print(f"    {c}: {v}")
            if i < len(rows) - 1:
                print("    ---")
        else:
            print("  | ".join(str(v) for v in row))
    # Return as list of dicts
    return [dict(zip(cols, row)) for row in rows]


def main():
    conn = get_conn()
    cur = conn.cursor()

    # ── Pre-flight checks ──
    print("\n" + "=" * 70)
    print("  PRE-FLIGHT: Confirming DB values")
    print("=" * 70)

    cur.execute("SELECT DISTINCT account_type FROM inferno_positions")
    acct_types = [r[0] for r in cur.fetchall()]
    print(f"  account_type values in inferno_positions: {acct_types}")

    cur.execute("SELECT dte_mode FROM inferno_config LIMIT 1")
    row = cur.fetchone()
    dte_mode = row[0] if row else "UNKNOWN"
    print(f"  dte_mode in inferno_config: '{dte_mode}'")

    # ── Q1: CONFIG STATE ──
    q1 = run_query(cur, "Q1: CONFIG STATE",
        f"SELECT * FROM inferno_config WHERE dte_mode = '{dte_mode}'")

    # ── Q2: PAPER ACCOUNT INTEGRITY ──
    q2 = run_query(cur, "Q2: PAPER ACCOUNT INTEGRITY", """
        SELECT
          id,
          current_balance,
          starting_capital,
          cumulative_pnl,
          buying_power,
          collateral_in_use,
          (current_balance - starting_capital - cumulative_pnl) AS balance_drift,
          (buying_power + collateral_in_use) AS bp_sum,
          (current_balance - (buying_power + collateral_in_use)) AS bp_drift,
          is_active,
          dte_mode,
          person,
          account_type,
          total_trades,
          high_water_mark,
          max_drawdown
        FROM inferno_paper_account
        ORDER BY id
    """)

    # Check integrity
    active_rows = [r for r in q2 if r.get("is_active")]
    if len(active_rows) > 1:
        print("\n  ⚠️  MULTIPLE ACTIVE ROWS — ghost row exists!")
    for r in q2:
        drift = r.get("balance_drift")
        bp_drift = r.get("bp_drift")
        if drift and abs(float(drift)) > 0.01:
            print(f"\n  ⚠️  BALANCE DRIFT: {drift} (id={r['id']})")
        if bp_drift and abs(float(bp_drift)) > 0.01:
            print(f"\n  ⚠️  BP DRIFT: {bp_drift} (id={r['id']})")

    # ── Q3: FULL TRADE HISTORY ──
    q3 = run_query(cur, "Q3: FULL TRADE HISTORY", """
        SELECT
          position_id,
          open_time AT TIME ZONE 'America/Chicago' AS open_ct,
          close_time AT TIME ZONE 'America/Chicago' AS close_ct,
          ROUND(EXTRACT(EPOCH FROM (close_time - open_time))/60) AS hold_minutes,
          contracts,
          spread_width,
          total_credit,
          collateral_required AS collateral,
          close_price,
          close_reason,
          realized_pnl,
          oracle_win_probability,
          vix_at_entry AS vix_at_open,
          status
        FROM inferno_positions
        ORDER BY open_time DESC
    """, show_cols=False)

    # Flag issues
    print("\n  --- FLAGS ---")
    for t in q3:
        if t["contracts"] and int(t["contracts"]) > 3:
            print(f"  ⚠️  HIGH CONTRACTS: {t['position_id']} has {t['contracts']} contracts")
        if t["status"] == "open" and t.get("open_ct"):
            open_date = str(t["open_ct"])[:10]
            print(f"  ⚠️  OPEN POSITION: {t['position_id']} opened {open_date}")

    # ── Q4: LOSS BREAKDOWN BY EXIT TYPE ──
    q4 = run_query(cur, "Q4: LOSS BREAKDOWN BY EXIT TYPE", """
        SELECT
          close_reason,
          COUNT(*) AS trades,
          SUM(realized_pnl) AS total_pnl,
          ROUND(AVG(realized_pnl), 2) AS avg_pnl,
          ROUND(MIN(realized_pnl), 2) AS worst,
          ROUND(MAX(realized_pnl), 2) AS best,
          COUNT(CASE WHEN realized_pnl > 0 THEN 1 END) AS winners,
          COUNT(CASE WHEN realized_pnl <= 0 THEN 1 END) AS losers,
          ROUND(COUNT(CASE WHEN realized_pnl > 0 THEN 1 END) * 100.0
            / NULLIF(COUNT(*), 0), 1) AS win_rate_pct
        FROM inferno_positions
        WHERE status = 'closed'
        GROUP BY close_reason
        ORDER BY total_pnl ASC
    """)

    # ── Q5: P&L BY VIX REGIME ──
    q5 = run_query(cur, "Q5: P&L BY VIX REGIME", """
        SELECT
          CASE
            WHEN vix_at_entry < 15 THEN '1. LOW < 15'
            WHEN vix_at_entry < 20 THEN '2. NORMAL 15-20'
            WHEN vix_at_entry < 25 THEN '3. ELEVATED 20-25'
            WHEN vix_at_entry < 35 THEN '4. HIGH 25-35'
            ELSE '5. EXTREME 35+'
          END AS vix_bucket,
          COUNT(*) AS trades,
          ROUND(AVG(vix_at_entry)::numeric, 1) AS avg_vix,
          SUM(realized_pnl) AS total_pnl,
          ROUND(AVG(realized_pnl), 2) AS avg_pnl,
          ROUND(COUNT(CASE WHEN realized_pnl > 0 THEN 1 END) * 100.0
            / NULLIF(COUNT(*), 0), 1) AS win_rate_pct
        FROM inferno_positions
        WHERE status = 'closed'
        GROUP BY vix_bucket
        ORDER BY vix_bucket
    """)

    # ── Q6: P&L BY HOUR OF DAY ──
    q6 = run_query(cur, "Q6: P&L BY HOUR OF DAY", """
        SELECT
          EXTRACT(HOUR FROM open_time AT TIME ZONE 'America/Chicago') AS hour_ct,
          COUNT(*) AS trades,
          SUM(realized_pnl) AS total_pnl,
          ROUND(AVG(realized_pnl), 2) AS avg_pnl,
          ROUND(COUNT(CASE WHEN realized_pnl > 0 THEN 1 END) * 100.0
            / NULLIF(COUNT(*), 0), 1) AS win_rate_pct
        FROM inferno_positions
        WHERE status = 'closed'
        GROUP BY hour_ct
        ORDER BY hour_ct
    """)

    # ── Q7: P&L BY DAY OF WEEK ──
    q7 = run_query(cur, "Q7: P&L BY DAY OF WEEK", """
        SELECT
          TO_CHAR(open_time AT TIME ZONE 'America/Chicago', 'Day') AS day_name,
          EXTRACT(DOW FROM open_time AT TIME ZONE 'America/Chicago') AS dow,
          COUNT(*) AS trades,
          SUM(realized_pnl) AS total_pnl,
          ROUND(AVG(realized_pnl), 2) AS avg_pnl,
          ROUND(COUNT(CASE WHEN realized_pnl > 0 THEN 1 END) * 100.0
            / NULLIF(COUNT(*), 0), 1) AS win_rate_pct
        FROM inferno_positions
        WHERE status = 'closed'
        GROUP BY day_name, dow
        ORDER BY dow
    """)

    # ── Q8: ORACLE SIGNAL QUALITY ──
    q8 = run_query(cur, "Q8: ORACLE SIGNAL QUALITY", """
        SELECT
          ROUND(oracle_win_probability::numeric, 1) AS wp_rounded,
          COUNT(*) AS trades,
          SUM(realized_pnl) AS total_pnl,
          ROUND(AVG(realized_pnl), 2) AS avg_pnl,
          ROUND(COUNT(CASE WHEN realized_pnl > 0 THEN 1 END) * 100.0
            / NULLIF(COUNT(*), 0), 1) AS actual_win_rate_pct
        FROM inferno_positions
        WHERE status = 'closed'
          AND oracle_win_probability IS NOT NULL
        GROUP BY wp_rounded
        ORDER BY wp_rounded
    """)

    # ── Q9: SIZING AUDIT (with Kelly columns) ──
    # Check if Kelly columns exist first
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'inferno_positions' AND column_name IN ('kelly_raw', 'kelly_half', 'kelly_size_pct')
    """)
    kelly_cols_exist = len(cur.fetchall()) == 3
    kelly_select = ", kelly_raw, kelly_half, kelly_size_pct" if kelly_cols_exist else ""

    q9 = run_query(cur, "Q9: SIZING AUDIT", f"""
        SELECT
          position_id,
          contracts,
          collateral_required AS collateral,
          spread_width,
          total_credit,
          oracle_win_probability,
          ROUND((spread_width - total_credit) * 100 * contracts, 2)
            AS expected_collateral,
          collateral_required - ROUND((spread_width - total_credit) * 100 * contracts, 2)
            AS collateral_discrepancy
          {kelly_select}
        FROM inferno_positions
        ORDER BY contracts DESC
        LIMIT 20
    """)

    for r in q9:
        disc = r.get("collateral_discrepancy")
        if disc and abs(float(disc)) > 0.01:
            print(f"  ⚠️  COLLATERAL DISCREPANCY: {r['position_id']} off by ${disc}")

    # ── Q10: OPEN POSITION ORPHAN CHECK ──
    q10 = run_query(cur, "Q10: OPEN POSITION ORPHAN CHECK", """
        SELECT
          position_id,
          status,
          contracts,
          collateral_required AS collateral,
          open_time AT TIME ZONE 'America/Chicago' AS open_ct,
          DATE(open_time AT TIME ZONE 'America/Chicago') AS open_date,
          CURRENT_DATE AS today
        FROM inferno_positions
        WHERE status = 'open'
    """)

    for r in q10:
        open_date = str(r.get("open_date", ""))
        today = str(r.get("today", ""))
        if open_date and today and open_date < today:
            print(f"\n  ⚠️  ORPHAN POSITION: {r['position_id']} opened {open_date}, today is {today}")
            print(f"      → Close manually or run: UPDATE inferno_positions SET status='closed', close_reason='manual_audit_close', close_time=NOW(), realized_pnl=0 WHERE position_id='{r['position_id']}'")

    # ══════════════════════════════════════════════════════════════════
    #  PART 3: LOSS ANALYSIS
    # ══════════════════════════════════════════════════════════════════

    print("\n\n" + "=" * 70)
    print("  PART 3: LOSS ANALYSIS")
    print("=" * 70)

    # Get all closed trades for analysis
    cur.execute("""
        SELECT
          position_id, realized_pnl, close_reason,
          total_credit, contracts, spread_width,
          open_time AT TIME ZONE 'America/Chicago' AS open_ct,
          close_time AT TIME ZONE 'America/Chicago' AS close_ct,
          vix_at_entry, oracle_win_probability,
          EXTRACT(HOUR FROM open_time AT TIME ZONE 'America/Chicago') AS hour_ct,
          EXTRACT(DOW FROM open_time AT TIME ZONE 'America/Chicago') AS dow
        FROM inferno_positions
        WHERE status = 'closed'
        ORDER BY open_time
    """)
    cols = [d[0] for d in cur.description]
    closed_trades = [dict(zip(cols, r)) for r in cur.fetchall()]

    if not closed_trades:
        print("\n  NO CLOSED TRADES — cannot perform analysis.")
        conn.close()
        return

    # 3A: Overall Performance
    total_trades = len(closed_trades)
    winners = [t for t in closed_trades if t["realized_pnl"] and float(t["realized_pnl"]) > 0]
    losers = [t for t in closed_trades if t["realized_pnl"] and float(t["realized_pnl"]) <= 0]
    total_pnl = sum(float(t["realized_pnl"] or 0) for t in closed_trades)
    win_rate = len(winners) / total_trades if total_trades > 0 else 0
    avg_win = sum(float(t["realized_pnl"]) for t in winners) / len(winners) if winners else 0
    avg_loss = sum(float(t["realized_pnl"]) for t in losers) / len(losers) if losers else 0
    ev = (win_rate * avg_win) + ((1 - win_rate) * avg_loss)

    print(f"\n  3A: OVERALL PERFORMANCE")
    print(f"    Total trades: {total_trades}")
    print(f"    Winners: {len(winners)} | Losers: {len(losers)}")
    print(f"    Win rate: {win_rate:.1%}")
    print(f"    Avg winner: ${avg_win:.2f}")
    print(f"    Avg loser: ${avg_loss:.2f}")
    print(f"    Expected value per trade: ${ev:.2f}")
    print(f"    EV is {'POSITIVE ✅' if ev > 0 else 'NEGATIVE ❌'}")
    print(f"    Total cumulative P&L: ${total_pnl:.2f}")
    print(f"    Account is {'GROWING ✅' if total_pnl > 0 else 'SHRINKING ❌'}")

    # 3B: Primary Loss Driver
    print(f"\n  3B: PRIMARY LOSS DRIVER")
    sl_trades = [t for t in closed_trades if t["close_reason"] and "stop_loss" in str(t["close_reason"])]
    eod_trades = [t for t in closed_trades if t["close_reason"] and "eod" in str(t["close_reason"]).lower()]
    sl_total_loss = sum(float(t["realized_pnl"] or 0) for t in sl_trades if float(t["realized_pnl"] or 0) < 0)
    eod_total_loss = sum(float(t["realized_pnl"] or 0) for t in eod_trades if float(t["realized_pnl"] or 0) < 0)
    total_losses = sum(float(t["realized_pnl"] or 0) for t in closed_trades if float(t["realized_pnl"] or 0) < 0)

    if total_losses != 0:
        print(f"    Stop loss trades: {len(sl_trades)} | Loss from SL: ${sl_total_loss:.2f} ({sl_total_loss / total_losses * 100:.1f}% of total losses)")
        print(f"    EOD trades: {len(eod_trades)} | Loss from EOD: ${eod_total_loss:.2f} ({eod_total_loss / total_losses * 100:.1f}% of total losses)")
    else:
        print(f"    No losses recorded.")

    # Cost of 3.0x SL vs 2.0x
    sl_cost_diff = 0
    for t in sl_trades:
        pnl = float(t["realized_pnl"] or 0)
        credit = float(t["total_credit"] or 0)
        contracts = int(t["contracts"] or 0)
        if pnl < 0 and credit > 0 and contracts > 0:
            what_2x = -(credit * 2.0 * 100 * contracts)
            diff = pnl - what_2x  # actual loss minus what 2x would have been
            sl_cost_diff += diff
    print(f"    Cost of 3.0x SL vs 2.0x: ${sl_cost_diff:.2f} (extra loss from wider stop)")

    # 3C: VIX Analysis
    print(f"\n  3C: VIX ANALYSIS")
    for r in q5:
        pnl = r.get("total_pnl", 0) or 0
        bucket = r.get("vix_bucket", "")
        trades = r.get("trades", 0) or 0
        wr = r.get("win_rate_pct", 0) or 0
        print(f"    {bucket}: {trades} trades, P&L=${float(pnl):.2f}, WR={float(wr):.1f}%")
        if float(pnl) < 0 and trades >= 3:
            print(f"      → UNPROFITABLE (consider skipping this VIX range)")

    # 3D: Time of Day
    print(f"\n  3D: TIME OF DAY ANALYSIS")
    for r in q6:
        hr = int(r.get("hour_ct", 0) or 0)
        trades = r.get("trades", 0) or 0
        pnl = r.get("total_pnl", 0) or 0
        wr = r.get("win_rate_pct", 0) or 0
        tag = "✅" if float(pnl) > 0 else "❌"
        print(f"    {hr:02d}:00 CT: {trades} trades, P&L=${float(pnl):.2f}, WR={float(wr):.1f}% {tag}")

    # 3E: Day of Week
    print(f"\n  3E: DAY OF WEEK ANALYSIS")
    for r in q7:
        day = str(r.get("day_name", "")).strip()
        trades = r.get("trades", 0) or 0
        pnl = r.get("total_pnl", 0) or 0
        wr = r.get("win_rate_pct", 0) or 0
        tag = "✅" if float(pnl) > 0 else "❌"
        print(f"    {day}: {trades} trades, P&L=${float(pnl):.2f}, WR={float(wr):.1f}% {tag}")

    # 3F: Oracle Quality
    print(f"\n  3F: ORACLE QUALITY")
    if not q8:
        print("    No oracle data available.")
    else:
        for r in q8:
            wp = r.get("wp_rounded", 0) or 0
            trades = r.get("trades", 0) or 0
            pnl = r.get("total_pnl", 0) or 0
            actual_wr = r.get("actual_win_rate_pct", 0) or 0
            print(f"    WP={float(wp):.1f}: {trades} trades, P&L=${float(pnl):.2f}, actual WR={float(actual_wr):.1f}%")

        # Check if higher WP actually predicts better outcomes
        if len(q8) >= 2:
            wps = sorted(q8, key=lambda r: float(r.get("wp_rounded", 0) or 0))
            low_wr = float(wps[0].get("actual_win_rate_pct", 0) or 0)
            high_wr = float(wps[-1].get("actual_win_rate_pct", 0) or 0)
            if abs(high_wr - low_wr) < 5:
                print("    → Oracle has NO predictive value — high and low WP produce similar actual win rates")
            elif high_wr > low_wr:
                print("    → Oracle HAS predictive value — higher WP produces higher actual win rate")
            else:
                print("    → Oracle is INVERTED — higher WP produces LOWER actual win rate!")

    # 3G: Sliding PT Assessment
    print(f"\n  3G: SLIDING PT ASSESSMENT")
    morning_trades = [t for t in closed_trades if t.get("hour_ct") and int(t["hour_ct"]) < 10]
    afternoon_trades = [t for t in closed_trades if t.get("hour_ct") and int(t["hour_ct"]) >= 13]
    morning_pt = [t for t in morning_trades if t["close_reason"] and "profit_target" in str(t["close_reason"])]
    morning_sl = [t for t in morning_trades if t["close_reason"] and "stop_loss" in str(t["close_reason"])]
    afternoon_pt = [t for t in afternoon_trades if t["close_reason"] and "profit_target" in str(t["close_reason"])]

    print(f"    Morning trades: {len(morning_trades)} (PT={len(morning_pt)}, SL={len(morning_sl)})")
    print(f"    Afternoon trades: {len(afternoon_trades)} (PT={len(afternoon_pt)})")
    if morning_trades:
        print(f"    Morning: {len(morning_pt)}/{len(morning_trades)} hit PT ({len(morning_pt)/len(morning_trades)*100:.0f}%)")
    if afternoon_trades:
        print(f"    Afternoon: {len(afternoon_pt)}/{len(afternoon_trades)} hit PT ({len(afternoon_pt)/len(afternoon_trades)*100:.0f}%)")
    print(f"    → PT has been REVERSED in code: Morning 20% → Midday 30% → Afternoon 50%")
    print(f"    → This lets theta work in afternoon when 0DTE decay accelerates")

    # 3H: Root Cause Summary
    print(f"\n  3H: ROOT CAUSE SUMMARY")
    causes = []
    if sl_total_loss != 0:
        causes.append(("3.0x Stop Loss (too wide)", sl_total_loss, f"{len(sl_trades)} SL trades lost ${sl_total_loss:.2f}; extra cost vs 2.0x: ${sl_cost_diff:.2f}"))
    if eod_total_loss != 0:
        causes.append(("EOD Cutoff Losses", eod_total_loss, f"{len(eod_trades)} EOD trades with net loss ${eod_total_loss:.2f}"))

    # Check for overtrading (many small losses)
    small_losses = [t for t in losers if abs(float(t["realized_pnl"] or 0)) < 50]
    if len(small_losses) > 5:
        small_loss_total = sum(float(t["realized_pnl"]) for t in small_losses)
        causes.append(("Overtrading (many small losses)", small_loss_total, f"{len(small_losses)} trades under $50 loss totaling ${small_loss_total:.2f}"))

    causes.sort(key=lambda x: x[1])
    for i, (cause, impact, detail) in enumerate(causes[:3], 1):
        print(f"    #{i}: {cause}")
        print(f"        Impact: ${impact:.2f}")
        print(f"        Data: {detail}")

    # ══════════════════════════════════════════════════════════════════
    #  RECOMMENDED DB UPDATES
    # ══════════════════════════════════════════════════════════════════

    print("\n\n" + "=" * 70)
    print("  RECOMMENDED DB UPDATES")
    print("  (Copy and run these in your PostgreSQL client)")
    print("=" * 70)

    print(f"""
-- Fix 1: Stop Loss 3.0x → 2.0x
UPDATE inferno_config SET stop_loss_pct = 200.0 WHERE dte_mode = '{dte_mode}';

-- Fix 2: max_contracts → 9999 (Kelly sizes dynamically)
UPDATE inferno_config SET max_contracts = 9999 WHERE dte_mode = '{dte_mode}';

-- Add Kelly columns to positions table
ALTER TABLE inferno_positions ADD COLUMN IF NOT EXISTS kelly_raw NUMERIC(8,4);
ALTER TABLE inferno_positions ADD COLUMN IF NOT EXISTS kelly_half NUMERIC(8,4);
ALTER TABLE inferno_positions ADD COLUMN IF NOT EXISTS kelly_size_pct NUMERIC(6,4);

-- Verify changes:
SELECT stop_loss_pct, max_contracts, dte_mode FROM inferno_config WHERE dte_mode = '{dte_mode}';
""")

    conn.close()
    print("\n  AUDIT COMPLETE.")


if __name__ == "__main__":
    main()
