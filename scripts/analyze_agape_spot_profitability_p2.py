#!/usr/bin/env python3
"""
AGAPE-SPOT PROFITABILITY ANALYSIS — PART 2 (Deep Dive)
=======================================================
Builds on P1-P17 findings. Focuses on root cause analysis
for BTC catastrophic performance, multi-account impact,
position stacking, and post-fix validation.

Run on Render shell:
  python scripts/analyze_agape_spot_profitability_p2.py

Queries (P18-P30):
  P18: Account-level P&L breakdown (default vs dedicated vs paper vs fallback)
  P19: Position stacking over time (simultaneous open positions)
  P20: BTC deep dive (why 4% win rate? entry conditions, exit timing)
  P21: Signal action effectiveness (which signal types win?)
  P22: Bayesian tracker accuracy vs actual outcomes
  P23: Max drawdown per ticker (peak-to-trough equity)
  P24: Time-to-loss speed (how fast do losers fail?)
  P25: P&L trajectory by week (are tickers improving or degrading?)
  P26: Fallback position audit (count, age, P&L impact)
  P27: Close reason × ticker heatmap (which exits work where?)
  P28: Trade clustering / burst detection
  P29: Unrealized P&L on open positions right now
  P30: Post-fix validation (max_hold_hours, fallback cleanup, trend scaling)
"""

import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CENTRAL_TZ = ZoneInfo("America/Chicago")

TICKERS = ["ETH-USD", "BTC-USD", "XRP-USD", "SHIB-USD", "DOGE-USD", "MSTU-USD"]
STARTING_CAPITAL = {
    "ETH-USD": 5000.0, "BTC-USD": 5000.0,
    "XRP-USD": 1000.0, "SHIB-USD": 1000.0,
    "DOGE-USD": 1000.0, "MSTU-USD": 1000.0,
}


def get_db_connection():
    try:
        import psycopg2
        url = os.environ.get("DATABASE_URL")
        if not url:
            env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
            if os.path.exists(env_path):
                with open(env_path) as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("DATABASE_URL=") and not line.startswith("#"):
                            url = line.split("=", 1)[1].strip()
                            break
        if not url:
            print("ERROR: DATABASE_URL not set.")
            sys.exit(1)
        return psycopg2.connect(url, connect_timeout=15)
    except Exception as e:
        print(f"ERROR: DB connection failed: {e}")
        sys.exit(1)


def q(conn, sql, params=None):
    cur = conn.cursor()
    cur.execute(sql, params)
    rows = cur.fetchall()
    cur.close()
    return rows


def pnl(val):
    if val is None:
        return "N/A"
    v = float(val)
    return f"${'+' if v >= 0 else ''}{v:,.2f}"


# ===================================================================
# P18: Account-Level P&L Breakdown
# ===================================================================
def p18_account_breakdown(conn):
    print("\n" + "=" * 80)
    print("P18: ACCOUNT-LEVEL P&L BREAKDOWN")
    print("=" * 80)
    print("  Shows P&L per account_label to identify fallback/paper pollution.")

    rows = q(conn, """
        SELECT
            account_label,
            ticker,
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE status = 'open') AS open_ct,
            COUNT(*) FILTER (WHERE realized_pnl > 0) AS wins,
            COUNT(*) FILTER (WHERE realized_pnl < 0) AS losses,
            COUNT(*) FILTER (WHERE realized_pnl = 0) AS breakeven,
            COUNT(*) FILTER (WHERE realized_pnl IS NULL AND status != 'open') AS null_pnl,
            COALESCE(SUM(realized_pnl), 0) AS total_pnl,
            COALESCE(AVG(realized_pnl) FILTER (WHERE realized_pnl IS NOT NULL), 0) AS avg_pnl,
            MIN(open_time) AS first_trade,
            MAX(COALESCE(close_time, open_time)) AS last_activity
        FROM agape_spot_positions
        GROUP BY account_label, ticker
        ORDER BY account_label, ticker
    """)

    if rows:
        print(f"\n  {'Account':<20} {'Ticker':<12} {'Total':>6} {'Open':>5} {'W':>5} {'L':>5} {'BE':>4} {'NullP':>5} {'Total P&L':>12} {'Avg P&L':>10}")
        print(f"  {'-'*95}")
        current_acct = None
        acct_totals = {}
        for r in rows:
            acct, ticker = r[0] or 'NULL', r[1] or 'NULL'
            total, open_ct, wins, losses, be, null_p = r[2], r[3], r[4] or 0, r[5] or 0, r[6] or 0, r[7] or 0
            total_pnl, avg_pnl = float(r[8]), float(r[9])

            if acct != current_acct:
                if current_acct and current_acct in acct_totals:
                    t = acct_totals[current_acct]
                    print(f"  {'  SUBTOTAL':<20} {'':12} {t['total']:>6} {t['open']:>5} {t['wins']:>5} {t['losses']:>5} {'':>4} {'':>5} {pnl(t['pnl']):>12}")
                    print(f"  {'-'*95}")
                current_acct = acct
                acct_totals[acct] = {'total': 0, 'open': 0, 'wins': 0, 'losses': 0, 'pnl': 0.0}

            acct_totals[acct]['total'] += total
            acct_totals[acct]['open'] += open_ct
            acct_totals[acct]['wins'] += wins
            acct_totals[acct]['losses'] += losses
            acct_totals[acct]['pnl'] += total_pnl

            flag = " !!FALLBACK" if "_fallback" in acct else ""
            print(f"  {acct:<20} {ticker:<12} {total:>6} {open_ct:>5} {wins:>5} {losses:>5} {be:>4} {null_p:>5} {pnl(total_pnl):>12} {pnl(avg_pnl):>10}{flag}")

        # Print last subtotal
        if current_acct and current_acct in acct_totals:
            t = acct_totals[current_acct]
            print(f"  {'  SUBTOTAL':<20} {'':12} {t['total']:>6} {t['open']:>5} {t['wins']:>5} {t['losses']:>5} {'':>4} {'':>5} {pnl(t['pnl']):>12}")

        # Summary by account type
        print(f"\n  SUMMARY BY ACCOUNT TYPE:")
        print(f"  {'-'*60}")
        agg = q(conn, """
            SELECT
                CASE
                    WHEN account_label LIKE '%_fallback' THEN 'FALLBACK'
                    WHEN account_label = 'paper' THEN 'PAPER'
                    ELSE 'LIVE'
                END AS acct_type,
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE status = 'open') AS open_ct,
                COUNT(*) FILTER (WHERE realized_pnl > 0) AS wins,
                COUNT(*) FILTER (WHERE realized_pnl < 0) AS losses,
                COALESCE(SUM(realized_pnl), 0) AS total_pnl
            FROM agape_spot_positions
            GROUP BY 1
            ORDER BY 1
        """)
        for r in agg:
            atype, total, open_ct, wins, losses = r[0], r[1], r[2], r[3] or 0, r[4] or 0
            total_pnl = float(r[5])
            wr = wins / (wins + losses) * 100 if (wins + losses) > 0 else 0
            print(f"  {atype:<12} {total:>6} trades  {open_ct:>4} open  {wr:>5.1f}% WR  {pnl(total_pnl):>12}")
    else:
        print("  No data")


# ===================================================================
# P19: Position Stacking (Simultaneous Open Positions)
# ===================================================================
def p19_position_stacking(conn):
    print("\n" + "=" * 80)
    print("P19: POSITION STACKING (simultaneous open positions)")
    print("=" * 80)

    # Max simultaneous positions per ticker (using open_time/close_time overlap)
    for ticker in TICKERS:
        rows = q(conn, """
            WITH pos AS (
                SELECT open_time, COALESCE(close_time, NOW()) AS end_time
                FROM agape_spot_positions
                WHERE ticker = %s AND account_label NOT LIKE '%%_fallback'
            )
            SELECT
                p1.open_time,
                COUNT(*) AS concurrent
            FROM pos p1
            JOIN pos p2
                ON p1.open_time >= p2.open_time
               AND p1.open_time < p2.end_time
            GROUP BY p1.open_time
            ORDER BY concurrent DESC
            LIMIT 1
        """, (ticker,))

        if rows and rows[0]:
            max_concurrent = rows[0][1]
            peak_time = rows[0][0]

            # Also get current open count
            current = q(conn, """
                SELECT COUNT(*), COUNT(DISTINCT account_label)
                FROM agape_spot_positions
                WHERE ticker = %s AND status = 'open'
            """, (ticker,))
            cur_ct = current[0][0] if current else 0
            cur_accts = current[0][1] if current else 0

            print(f"\n  {ticker}: Peak concurrent = {max_concurrent} (at {peak_time})")
            print(f"    Currently open: {cur_ct} across {cur_accts} account(s)")
        else:
            print(f"\n  {ticker}: No position data")

    # Global total
    global_ct = q(conn, """
        SELECT
            COUNT(*) FILTER (WHERE status = 'open') AS open_total,
            COUNT(*) FILTER (WHERE status = 'open' AND account_label LIKE '%%_fallback') AS open_fallback,
            COUNT(*) FILTER (WHERE status = 'open' AND account_label = 'paper') AS open_paper,
            COUNT(*) FILTER (WHERE status = 'open' AND account_label NOT IN ('paper') AND account_label NOT LIKE '%%_fallback') AS open_live
        FROM agape_spot_positions
    """)
    if global_ct and global_ct[0]:
        r = global_ct[0]
        print(f"\n  GLOBAL OPEN: {r[0]} total = {r[3]} live + {r[2]} paper + {r[1]} fallback")


# ===================================================================
# P20: BTC Deep Dive
# ===================================================================
def p20_btc_deep_dive(conn):
    print("\n" + "=" * 80)
    print("P20: BTC-USD DEEP DIVE (4% win rate, -$90 P&L)")
    print("=" * 80)

    # Entry timing: when did BTC trades open?
    print("\n  BTC ENTRY HOUR DISTRIBUTION:")
    rows = q(conn, """
        SELECT
            EXTRACT(HOUR FROM open_time AT TIME ZONE 'America/Chicago') AS hour_ct,
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE realized_pnl > 0) AS wins,
            COALESCE(SUM(realized_pnl), 0) AS total_pnl
        FROM agape_spot_positions
        WHERE ticker = 'BTC-USD'
          AND status IN ('closed', 'expired', 'stopped')
          AND realized_pnl IS NOT NULL
          AND account_label NOT IN ('paper') AND account_label NOT LIKE '%%_fallback'
        GROUP BY hour_ct
        ORDER BY hour_ct
    """)
    if rows:
        print(f"  {'Hour CT':>8} {'Trades':>7} {'Wins':>5} {'WR%':>7} {'P&L':>12}")
        print(f"  {'-'*45}")
        for r in rows:
            hour, total, wins = int(r[0]), r[1], r[2] or 0
            wr = wins / total * 100 if total > 0 else 0
            print(f"  {hour:>5}:00 {total:>7} {wins:>5} {wr:>6.1f}% {pnl(r[3]):>12}")

    # Hold duration breakdown for BTC specifically
    print("\n  BTC HOLD DURATION vs OUTCOME (live accounts only):")
    rows = q(conn, """
        SELECT
            CASE
                WHEN EXTRACT(EPOCH FROM (close_time - open_time)) / 60 < 15 THEN '01_<15min'
                WHEN EXTRACT(EPOCH FROM (close_time - open_time)) / 60 < 60 THEN '02_15-60min'
                WHEN EXTRACT(EPOCH FROM (close_time - open_time)) / 3600 < 2 THEN '03_1-2hr'
                WHEN EXTRACT(EPOCH FROM (close_time - open_time)) / 3600 < 4 THEN '04_2-4hr'
                WHEN EXTRACT(EPOCH FROM (close_time - open_time)) / 3600 < 6 THEN '05_4-6hr'
                WHEN EXTRACT(EPOCH FROM (close_time - open_time)) / 3600 < 8 THEN '06_6-8hr'
                WHEN EXTRACT(EPOCH FROM (close_time - open_time)) / 3600 < 12 THEN '07_8-12hr'
                ELSE '08_>12hr'
            END AS bucket,
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE realized_pnl > 0) AS wins,
            COALESCE(SUM(realized_pnl), 0) AS total_pnl,
            COALESCE(AVG(realized_pnl), 0) AS avg_pnl,
            AVG(EXTRACT(EPOCH FROM (close_time - open_time)) / 3600) AS avg_hours
        FROM agape_spot_positions
        WHERE ticker = 'BTC-USD'
          AND status IN ('closed', 'expired', 'stopped')
          AND realized_pnl IS NOT NULL
          AND account_label NOT IN ('paper') AND account_label NOT LIKE '%%_fallback'
          AND close_time IS NOT NULL
        GROUP BY bucket
        ORDER BY bucket
    """)
    if rows:
        print(f"  {'Duration':<15} {'Trades':>6} {'Wins':>5} {'WR%':>7} {'P&L':>12} {'Avg P&L':>10} {'AvgHrs':>7}")
        print(f"  {'-'*68}")
        for r in rows:
            bucket = r[0][3:]  # strip sort prefix
            total, wins = r[1], r[2] or 0
            wr = wins / total * 100 if total > 0 else 0
            avg_hrs = float(r[5] or 0)
            print(f"  {bucket:<15} {total:>6} {wins:>5} {wr:>6.1f}% {pnl(r[3]):>12} {pnl(r[4]):>10} {avg_hrs:>6.1f}h")

    # BTC close reason breakdown
    print("\n  BTC CLOSE REASONS (live only):")
    rows = q(conn, """
        SELECT
            COALESCE(close_reason, 'UNKNOWN') AS reason,
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE realized_pnl > 0) AS wins,
            COALESCE(SUM(realized_pnl), 0) AS total_pnl,
            COALESCE(AVG(realized_pnl), 0) AS avg_pnl
        FROM agape_spot_positions
        WHERE ticker = 'BTC-USD'
          AND status IN ('closed', 'expired', 'stopped')
          AND realized_pnl IS NOT NULL
          AND account_label NOT IN ('paper') AND account_label NOT LIKE '%%_fallback'
        GROUP BY close_reason
        ORDER BY COUNT(*) DESC
    """)
    if rows:
        print(f"  {'Reason':<30} {'Trades':>6} {'Wins':>5} {'WR%':>7} {'P&L':>12} {'Avg':>10}")
        print(f"  {'-'*75}")
        for r in rows:
            total, wins = r[1], r[2] or 0
            wr = wins / total * 100 if total > 0 else 0
            print(f"  {r[0]:<30} {total:>6} {wins:>5} {wr:>6.1f}% {pnl(r[3]):>12} {pnl(r[4]):>10}")

    # BTC funding regime at entry
    print("\n  BTC FUNDING REGIME AT ENTRY (live only):")
    rows = q(conn, """
        SELECT
            COALESCE(funding_regime_at_entry, 'UNKNOWN') AS regime,
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE realized_pnl > 0) AS wins,
            COALESCE(SUM(realized_pnl), 0) AS total_pnl
        FROM agape_spot_positions
        WHERE ticker = 'BTC-USD'
          AND status IN ('closed', 'expired', 'stopped')
          AND realized_pnl IS NOT NULL
          AND account_label NOT IN ('paper') AND account_label NOT LIKE '%%_fallback'
        GROUP BY regime
        ORDER BY COUNT(*) DESC
    """)
    if rows:
        print(f"  {'Regime':<25} {'Trades':>6} {'Wins':>5} {'WR%':>7} {'P&L':>12}")
        print(f"  {'-'*60}")
        for r in rows:
            total, wins = r[1], r[2] or 0
            wr = wins / total * 100 if total > 0 else 0
            print(f"  {r[0]:<25} {total:>6} {wins:>5} {wr:>6.1f}% {pnl(r[3]):>12}")


# ===================================================================
# P21: Signal Action Effectiveness
# ===================================================================
def p21_signal_action(conn):
    print("\n" + "=" * 80)
    print("P21: SIGNAL ACTION EFFECTIVENESS (which signals win?)")
    print("=" * 80)

    rows = q(conn, """
        SELECT
            sa.signal_action,
            p.ticker,
            COUNT(*) AS trades,
            COUNT(*) FILTER (WHERE p.realized_pnl > 0) AS wins,
            COALESCE(SUM(p.realized_pnl), 0) AS total_pnl,
            COALESCE(AVG(p.realized_pnl), 0) AS avg_pnl
        FROM agape_spot_scan_activity sa
        JOIN agape_spot_positions p
            ON sa.ticker = p.ticker
           AND sa.position_id = p.position_id
        WHERE p.status IN ('closed', 'expired', 'stopped')
          AND p.realized_pnl IS NOT NULL
          AND p.account_label NOT IN ('paper')
          AND p.account_label NOT LIKE '%%_fallback'
        GROUP BY sa.signal_action, p.ticker
        ORDER BY sa.signal_action, p.ticker
    """)

    if rows:
        print(f"\n  {'Signal Action':<25} {'Ticker':<12} {'Trades':>6} {'Wins':>5} {'WR%':>7} {'P&L':>12} {'Avg':>10}")
        print(f"  {'-'*80}")
        for r in rows:
            action, ticker, trades, wins = r[0] or 'UNKNOWN', r[1], r[2], r[3] or 0
            wr = wins / trades * 100 if trades > 0 else 0
            print(f"  {action:<25} {ticker:<12} {trades:>6} {wins:>5} {wr:>6.1f}% {pnl(r[4]):>12} {pnl(r[5]):>10}")
    else:
        print("  No data (scan_activity doesn't track position_id, or no matches)")

    # Fallback: just show scan_activity signal actions distribution
    print(f"\n  SIGNAL ACTION DISTRIBUTION (last 7 days, all scans):")
    rows2 = q(conn, """
        SELECT
            ticker,
            signal_action,
            COUNT(*) AS count
        FROM agape_spot_scan_activity
        WHERE signal_action IS NOT NULL
          AND timestamp > NOW() - INTERVAL '7 days'
        GROUP BY ticker, signal_action
        ORDER BY ticker, count DESC
    """)
    if rows2:
        print(f"  {'Ticker':<12} {'Signal Action':<30} {'Count':>7}")
        print(f"  {'-'*55}")
        for r in rows2:
            print(f"  {r[0]:<12} {r[1]:<30} {r[2]:>7}")


# ===================================================================
# P22: Bayesian Tracker Accuracy
# ===================================================================
def p22_bayesian_accuracy(conn):
    print("\n" + "=" * 80)
    print("P22: BAYESIAN TRACKER ACCURACY (predicted vs actual)")
    print("=" * 80)

    # Compare predicted win probability at entry vs actual outcome
    rows = q(conn, """
        SELECT
            ticker,
            CASE
                WHEN bayesian_probability < 0.40 THEN '01_<40%'
                WHEN bayesian_probability < 0.50 THEN '02_40-50%'
                WHEN bayesian_probability < 0.55 THEN '03_50-55%'
                WHEN bayesian_probability < 0.60 THEN '04_55-60%'
                WHEN bayesian_probability >= 0.60 THEN '05_>=60%'
                ELSE '06_NULL'
            END AS prob_bucket,
            COUNT(*) AS predictions,
            COUNT(*) FILTER (WHERE actual_win = true) AS actual_wins,
            AVG(bayesian_probability) AS avg_predicted_prob
        FROM agape_spot_ml_shadow
        WHERE actual_win IS NOT NULL
        GROUP BY ticker, prob_bucket
        ORDER BY ticker, prob_bucket
    """)

    if rows:
        print(f"\n  {'Ticker':<12} {'Predicted':<12} {'Count':>6} {'Actual W':>8} {'Actual WR':>10} {'Avg Pred':>10} {'Calibrated?':<12}")
        print(f"  {'-'*75}")
        current = None
        for r in rows:
            ticker = r[0]
            if ticker != current:
                if current:
                    print(f"  {'-'*75}")
                current = ticker
            bucket = r[1][3:]  # strip sort prefix
            count, actual_wins = r[2], r[3] or 0
            actual_wr = actual_wins / count * 100 if count > 0 else 0
            avg_pred = float(r[4] or 0) * 100
            # Well-calibrated = predicted within 10pp of actual
            diff = abs(actual_wr - avg_pred)
            cal = "YES" if diff < 10 else "CLOSE" if diff < 20 else "NO"
            print(f"  {ticker:<12} {bucket:<12} {count:>6} {actual_wins:>8} {actual_wr:>8.1f}% {avg_pred:>8.1f}%   {cal}")
    else:
        print("  No ML shadow prediction data (table may not exist or be empty)")
        # Try direct query
        try:
            count = q(conn, "SELECT COUNT(*) FROM agape_spot_ml_shadow")
            print(f"  ML shadow table has {count[0][0]} rows total")
        except Exception:
            print("  agape_spot_ml_shadow table does not exist")


# ===================================================================
# P23: Maximum Drawdown Per Ticker
# ===================================================================
def p23_max_drawdown(conn):
    print("\n" + "=" * 80)
    print("P23: MAXIMUM DRAWDOWN PER TICKER")
    print("=" * 80)

    for ticker in TICKERS:
        rows = q(conn, """
            SELECT
                realized_pnl,
                close_time
            FROM agape_spot_positions
            WHERE ticker = %s
              AND status IN ('closed', 'expired', 'stopped')
              AND realized_pnl IS NOT NULL
              AND account_label NOT IN ('paper')
              AND account_label NOT LIKE '%%_fallback'
            ORDER BY close_time ASC
        """, (ticker,))

        if not rows:
            continue

        capital = STARTING_CAPITAL.get(ticker, 1000)
        equity = capital
        peak = capital
        max_dd = 0
        max_dd_pct = 0
        dd_start = None
        dd_end = None
        current_dd_start = None

        for r in rows:
            equity += float(r[0])
            if equity > peak:
                peak = equity
                current_dd_start = r[1]
            dd = peak - equity
            dd_pct = dd / peak * 100 if peak > 0 else 0
            if dd > max_dd:
                max_dd = dd
                max_dd_pct = dd_pct
                dd_start = current_dd_start
                dd_end = r[1]

        final_equity = equity
        total_pnl = final_equity - capital
        roi = total_pnl / capital * 100

        print(f"\n  {ticker}: Capital=${capital:,.0f}  Final=${final_equity:,.2f}  ROI={roi:+.2f}%")
        print(f"    Max Drawdown:  ${max_dd:,.2f} ({max_dd_pct:.1f}%)")
        if dd_start and dd_end:
            print(f"    DD Period:     {dd_start} → {dd_end}")
        print(f"    Peak Equity:   ${peak:,.2f}")


# ===================================================================
# P24: Time-to-Loss Speed
# ===================================================================
def p24_time_to_loss(conn):
    print("\n" + "=" * 80)
    print("P24: TIME-TO-LOSS SPEED (how fast do losers fail?)")
    print("=" * 80)
    print("  Shows if positions are stopped out quickly (good) or bleed slowly (bad)")

    rows = q(conn, """
        SELECT
            ticker,
            CASE WHEN realized_pnl > 0 THEN 'WIN' ELSE 'LOSS' END AS outcome,
            COUNT(*) AS trades,
            AVG(EXTRACT(EPOCH FROM (close_time - open_time)) / 60) AS avg_min,
            PERCENTILE_CONT(0.5) WITHIN GROUP (
                ORDER BY EXTRACT(EPOCH FROM (close_time - open_time)) / 60
            ) AS median_min,
            MIN(EXTRACT(EPOCH FROM (close_time - open_time)) / 60) AS min_min,
            MAX(EXTRACT(EPOCH FROM (close_time - open_time)) / 60) AS max_min
        FROM agape_spot_positions
        WHERE status IN ('closed', 'expired', 'stopped')
          AND realized_pnl IS NOT NULL AND realized_pnl != 0
          AND account_label NOT IN ('paper') AND account_label NOT LIKE '%%_fallback'
          AND close_time IS NOT NULL AND open_time IS NOT NULL
        GROUP BY ticker, outcome
        ORDER BY ticker, outcome
    """)

    if rows:
        print(f"\n  {'Ticker':<12} {'Outcome':<7} {'Trades':>6} {'Avg':>8} {'Median':>8} {'Min':>8} {'Max':>8}  (minutes)")
        print(f"  {'-'*70}")
        current = None
        for r in rows:
            ticker = r[0]
            if ticker != current:
                if current:
                    print(f"  {'-'*70}")
                current = ticker
            outcome, trades = r[1], r[2]
            avg_m, med_m, min_m, max_m = float(r[3] or 0), float(r[4] or 0), float(r[5] or 0), float(r[6] or 0)
            def fmt_time(m):
                if m > 120:
                    return f"{m/60:.1f}h"
                return f"{m:.0f}m"
            print(f"  {ticker:<12} {outcome:<7} {trades:>6} {fmt_time(avg_m):>8} {fmt_time(med_m):>8} {fmt_time(min_m):>8} {fmt_time(max_m):>8}")
    else:
        print("  No data")


# ===================================================================
# P25: P&L Trajectory by Week
# ===================================================================
def p25_weekly_trajectory(conn):
    print("\n" + "=" * 80)
    print("P25: WEEKLY P&L TRAJECTORY (is performance improving?)")
    print("=" * 80)

    rows = q(conn, """
        SELECT
            ticker,
            DATE_TRUNC('week', close_time AT TIME ZONE 'America/Chicago')::date AS week,
            COUNT(*) AS trades,
            COUNT(*) FILTER (WHERE realized_pnl > 0) AS wins,
            COALESCE(SUM(realized_pnl), 0) AS week_pnl,
            COALESCE(AVG(realized_pnl), 0) AS avg_pnl
        FROM agape_spot_positions
        WHERE status IN ('closed', 'expired', 'stopped')
          AND realized_pnl IS NOT NULL
          AND account_label NOT IN ('paper') AND account_label NOT LIKE '%%_fallback'
          AND close_time IS NOT NULL
        GROUP BY ticker, week
        ORDER BY ticker, week
    """)

    if rows:
        current = None
        running = {}
        for r in rows:
            ticker, week, trades, wins = r[0], r[1], r[2], r[3] or 0
            week_pnl, avg_pnl = float(r[4]), float(r[5])
            wr = wins / trades * 100 if trades > 0 else 0

            if ticker != current:
                if current:
                    print()
                current = ticker
                running[ticker] = 0.0
                print(f"\n  {ticker}:")
                print(f"  {'Week':<12} {'Trades':>6} {'WR%':>7} {'Week P&L':>12} {'Running':>12} {'Trend'}")
                print(f"  {'-'*65}")

            running[ticker] += week_pnl
            bar = "+" * min(int(week_pnl * 10), 20) if week_pnl > 0 else "-" * min(int(abs(week_pnl) * 10), 20)
            print(f"  {str(week):<12} {trades:>6} {wr:>6.1f}% {pnl(week_pnl):>12} {pnl(running[ticker]):>12}  {bar}")
    else:
        print("  No data")


# ===================================================================
# P26: Fallback Position Audit
# ===================================================================
def p26_fallback_audit(conn):
    print("\n" + "=" * 80)
    print("P26: FALLBACK POSITION AUDIT")
    print("=" * 80)
    print("  Fallback positions were created by old code when live orders failed.")
    print("  The fix removes fallback creation and cleans up open ones at init.")

    # Count by status
    rows = q(conn, """
        SELECT
            account_label,
            status,
            COUNT(*) AS count,
            COALESCE(SUM(realized_pnl), 0) AS total_pnl,
            MIN(open_time) AS first,
            MAX(COALESCE(close_time, open_time)) AS last
        FROM agape_spot_positions
        WHERE account_label LIKE '%%_fallback'
        GROUP BY account_label, status
        ORDER BY account_label, status
    """)

    if rows:
        print(f"\n  {'Account':<20} {'Status':<10} {'Count':>7} {'P&L':>12} {'First':<20} {'Last':<20}")
        print(f"  {'-'*95}")
        total_fallback = 0
        total_open = 0
        for r in rows:
            acct, status, count = r[0], r[1], r[2]
            total_pnl = float(r[3])
            first = str(r[4])[:16] if r[4] else "?"
            last = str(r[5])[:16] if r[5] else "?"
            total_fallback += count
            if status == 'open':
                total_open += count
            print(f"  {acct:<20} {status:<10} {count:>7} {pnl(total_pnl):>12} {first:<20} {last:<20}")

        print(f"\n  Total fallback positions: {total_fallback}")
        print(f"  Still OPEN: {total_open} {'(cleanup fix will close these at init)' if total_open > 0 else '(all cleaned up)'}")
    else:
        print("  No fallback positions found (all clean!)")

    # Check for LEGACY_FALLBACK_CLEANUP close reason (evidence of fix running)
    cleanup = q(conn, """
        SELECT COUNT(*), MAX(close_time)
        FROM agape_spot_positions
        WHERE close_reason = 'LEGACY_FALLBACK_CLEANUP'
    """)
    if cleanup and cleanup[0][0] > 0:
        print(f"\n  Cleanup fix has run: {cleanup[0][0]} positions closed at {cleanup[0][1]}")


# ===================================================================
# P27: Close Reason x Ticker Heatmap
# ===================================================================
def p27_close_reason_heatmap(conn):
    print("\n" + "=" * 80)
    print("P27: CLOSE REASON × TICKER — WIN RATE HEATMAP")
    print("=" * 80)

    rows = q(conn, """
        SELECT
            COALESCE(
                CASE
                    WHEN close_reason LIKE 'TRAIL_STOP%%' THEN 'TRAIL_STOP'
                    WHEN close_reason LIKE 'MAX_LOSS%%' THEN 'MAX_LOSS'
                    WHEN close_reason LIKE 'STALE%%' THEN 'STALE'
                    ELSE close_reason
                END, 'UNKNOWN'
            ) AS reason_group,
            ticker,
            COUNT(*) AS trades,
            COUNT(*) FILTER (WHERE realized_pnl > 0) AS wins,
            COALESCE(SUM(realized_pnl), 0) AS total_pnl
        FROM agape_spot_positions
        WHERE status IN ('closed', 'expired', 'stopped')
          AND realized_pnl IS NOT NULL
          AND account_label NOT IN ('paper') AND account_label NOT LIKE '%%_fallback'
        GROUP BY reason_group, ticker
        ORDER BY reason_group, ticker
    """)

    if rows:
        # Collect unique reasons and tickers
        reasons = sorted(set(r[0] for r in rows))
        tickers_seen = sorted(set(r[1] for r in rows))

        # Build matrix
        matrix = {}
        for r in rows:
            reason, ticker = r[0], r[1]
            trades, wins = r[2], r[3] or 0
            wr = wins / trades * 100 if trades > 0 else 0
            matrix[(reason, ticker)] = (trades, wr, float(r[4]))

        # Print header
        header = f"  {'Reason':<20}"
        for t in tickers_seen:
            header += f" {t[:6]:>8}"
        print(f"\n{header}")
        print(f"  {'-'*(20 + 9 * len(tickers_seen))}")

        # Win Rate rows
        print(f"  {'--- WIN RATE ---':<20}")
        for reason in reasons:
            row = f"  {reason:<20}"
            for t in tickers_seen:
                if (reason, t) in matrix:
                    trades, wr, _ = matrix[(reason, t)]
                    row += f" {wr:>6.0f}%"
                else:
                    row += f" {'--':>7}"
            print(row)

        # P&L rows
        print(f"\n  {'--- TOTAL P&L ---':<20}")
        for reason in reasons:
            row = f"  {reason:<20}"
            for t in tickers_seen:
                if (reason, t) in matrix:
                    _, _, total_pnl = matrix[(reason, t)]
                    row += f" {pnl(total_pnl):>8}"
                else:
                    row += f" {'--':>8}"
            print(row)
    else:
        print("  No data")


# ===================================================================
# P28: Trade Clustering / Burst Detection
# ===================================================================
def p28_trade_clustering(conn):
    print("\n" + "=" * 80)
    print("P28: TRADE CLUSTERING (burst entries in short windows)")
    print("=" * 80)

    for ticker in TICKERS:
        rows = q(conn, """
            SELECT
                DATE_TRUNC('hour', open_time AT TIME ZONE 'America/Chicago') AS hour_bucket,
                COUNT(*) AS entries,
                COUNT(DISTINCT account_label) AS accounts,
                COALESCE(SUM(realized_pnl), 0) AS total_pnl
            FROM agape_spot_positions
            WHERE ticker = %s
              AND account_label NOT IN ('paper') AND account_label NOT LIKE '%%_fallback'
            GROUP BY hour_bucket
            HAVING COUNT(*) >= 3
            ORDER BY entries DESC
            LIMIT 5
        """, (ticker,))

        if rows:
            print(f"\n  {ticker} — Top burst hours (3+ entries in 1 hour):")
            print(f"  {'Hour (CT)':<20} {'Entries':>8} {'Accounts':>9} {'P&L':>12}")
            print(f"  {'-'*55}")
            for r in rows:
                hour_str = str(r[0])[:16] if r[0] else "?"
                print(f"  {hour_str:<20} {r[1]:>8} {r[2]:>9} {pnl(r[3]):>12}")
        else:
            print(f"\n  {ticker}: No burst entries (good — spacing filters working)")


# ===================================================================
# P29: Unrealized P&L on Open Positions
# ===================================================================
def p29_unrealized_pnl(conn):
    print("\n" + "=" * 80)
    print("P29: UNREALIZED P&L ON CURRENT OPEN POSITIONS")
    print("=" * 80)
    print("  NOTE: Cannot fetch live prices from Render shell.")
    print("  Showing open positions with entry price and age.")

    rows = q(conn, """
        SELECT
            position_id,
            ticker,
            account_label,
            entry_price,
            quantity,
            entry_price * quantity AS notional,
            open_time,
            EXTRACT(EPOCH FROM (NOW() - open_time)) / 3600 AS hours_open,
            high_water_mark,
            trailing_active,
            current_stop,
            sell_fail_count
        FROM agape_spot_positions
        WHERE status = 'open'
        ORDER BY ticker, open_time ASC
    """)

    if rows:
        total_notional = 0
        print(f"\n  {'Ticker':<10} {'Account':<15} {'Entry$':>10} {'Qty':>12} {'Notional':>10} {'Hours':>6} {'Trail?':>6} {'Stop$':>10} {'HWM$':>10} {'Fail#':>5}")
        print(f"  {'-'*110}")
        for r in rows:
            ticker = r[1]
            acct = r[2] or 'default'
            entry = float(r[3])
            qty = float(r[4])
            notional = float(r[5] or 0)
            hours = float(r[7] or 0)
            hwm = float(r[8] or 0)
            trail = "YES" if r[9] else "no"
            stop = float(r[10] or 0)
            fail_ct = r[11] or 0

            total_notional += notional
            flag = " STUCK!" if hours > 24 else " LONG!" if hours > 8 else ""
            fail_flag = f" SELL_FAIL!" if fail_ct > 0 else ""
            print(f"  {ticker:<10} {acct:<15} ${entry:>9,.2f} {qty:>12.5f} ${notional:>8,.2f} {hours:>5.1f}h {trail:>6} ${stop:>9,.2f} ${hwm:>9,.2f} {fail_ct:>5}{flag}{fail_flag}")

        print(f"\n  Total open positions: {len(rows)}")
        print(f"  Total notional value: ${total_notional:,.2f}")
    else:
        print("\n  No open positions!")


# ===================================================================
# P30: Post-Fix Validation
# ===================================================================
def p30_post_fix_validation(conn):
    print("\n" + "=" * 80)
    print("P30: POST-FIX VALIDATION")
    print("=" * 80)
    print("  Validates the 3 bugs fixed in commit 93ed864:")
    print("  1. BTC max_hold_hours (should be 4h, was using global 6h)")
    print("  2. Trend scaling removed from max_hold (was pushing 4h→12h)")
    print("  3. Fallback position cleanup (should close all open fallbacks)")

    # Fix 1: Check if any BTC positions were held >4h after the fix date
    print("\n  FIX 1: BTC MAX_HOLD_HOURS (should close at 4h, not 6h)")
    rows = q(conn, """
        SELECT
            EXTRACT(EPOCH FROM (close_time - open_time)) / 3600 AS hold_hours,
            close_reason,
            close_time,
            account_label
        FROM agape_spot_positions
        WHERE ticker = 'BTC-USD'
          AND status IN ('closed', 'expired', 'stopped')
          AND account_label NOT IN ('paper') AND account_label NOT LIKE '%%_fallback'
          AND close_time IS NOT NULL
        ORDER BY close_time DESC
        LIMIT 20
    """)
    if rows:
        over_4h = [r for r in rows if float(r[0] or 0) > 4.0]
        under_4h = [r for r in rows if float(r[0] or 0) <= 4.0]
        print(f"  Last 20 BTC trades: {len(under_4h)} ≤4h, {len(over_4h)} >4h")
        if over_4h:
            print(f"  Over-4h trades (pre-fix or trend-scaled):")
            for r in over_4h:
                print(f"    {float(r[0]):.1f}h | {r[1]} | {str(r[2])[:16]} | {r[3]}")
    else:
        print("  No recent BTC trades to validate")

    # Fix 2: Check for MAX_HOLD_TIME exits and their durations
    print("\n  FIX 2: MAX_HOLD_TIME EXIT DURATIONS (should respect per-ticker config)")
    rows = q(conn, """
        SELECT
            ticker,
            EXTRACT(EPOCH FROM (close_time - open_time)) / 3600 AS hold_hours,
            close_time
        FROM agape_spot_positions
        WHERE close_reason = 'MAX_HOLD_TIME'
          AND account_label NOT IN ('paper') AND account_label NOT LIKE '%%_fallback'
        ORDER BY close_time DESC
        LIMIT 30
    """)
    if rows:
        # Group by ticker
        by_ticker = {}
        for r in rows:
            t = r[0]
            if t not in by_ticker:
                by_ticker[t] = []
            by_ticker[t].append(float(r[1] or 0))

        for t, hours_list in sorted(by_ticker.items()):
            avg_h = sum(hours_list) / len(hours_list)
            max_h = max(hours_list)
            min_h = min(hours_list)
            config_max = {"BTC-USD": 4, "ETH-USD": 8, "XRP-USD": 4, "SHIB-USD": 4, "DOGE-USD": 4}.get(t, 6)
            status = "OK" if max_h <= config_max * 1.1 else "OVER"
            print(f"  {t:<12} config={config_max}h  avg={avg_h:.1f}h  max={max_h:.1f}h  min={min_h:.1f}h  [{status}]")
    else:
        print("  No MAX_HOLD_TIME exits found")

    # Fix 3: Check for remaining open fallback positions
    print("\n  FIX 3: FALLBACK POSITION CLEANUP")
    rows = q(conn, """
        SELECT account_label, COUNT(*)
        FROM agape_spot_positions
        WHERE account_label LIKE '%%_fallback' AND status = 'open'
        GROUP BY account_label
    """)
    if rows:
        total = sum(r[1] for r in rows)
        print(f"  REMAINING OPEN FALLBACK POSITIONS: {total}")
        for r in rows:
            print(f"    {r[0]}: {r[1]} open")
        print("  Fix has NOT run yet (deploy needed)")
    else:
        print("  No open fallback positions (fix has run or none existed)")

    # Check if cleanup ran
    cleanup = q(conn, """
        SELECT COUNT(*), MAX(close_time)
        FROM agape_spot_positions
        WHERE close_reason = 'LEGACY_FALLBACK_CLEANUP'
    """)
    if cleanup and cleanup[0][0] > 0:
        print(f"  Cleanup executed: {cleanup[0][0]} positions closed at {cleanup[0][1]}")
    else:
        print(f"  Cleanup has not executed yet (awaiting deploy)")


# ===================================================================
# MAIN
# ===================================================================
def main():
    print("=" * 80)
    print("  AGAPE-SPOT PROFITABILITY ANALYSIS — PART 2 (Deep Dive)")
    print(f"  Generated: {datetime.now(CENTRAL_TZ).strftime('%Y-%m-%d %H:%M:%S CT')}")
    print("=" * 80)

    conn = get_db_connection()

    # Verify table exists
    exists = q(conn, """
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_name = 'agape_spot_positions'
        )
    """)
    if not exists or not exists[0][0]:
        print("\nERROR: agape_spot_positions table does not exist!")
        conn.close()
        sys.exit(1)

    count = q(conn, "SELECT COUNT(*) FROM agape_spot_positions")[0][0]
    print(f"\n  Total rows in agape_spot_positions: {count}")
    if count == 0:
        print("  No trades found.")
        conn.close()
        return

    p18_account_breakdown(conn)
    p19_position_stacking(conn)
    p20_btc_deep_dive(conn)
    p21_signal_action(conn)
    p22_bayesian_accuracy(conn)
    p23_max_drawdown(conn)
    p24_time_to_loss(conn)
    p25_weekly_trajectory(conn)
    p26_fallback_audit(conn)
    p27_close_reason_heatmap(conn)
    p28_trade_clustering(conn)
    p29_unrealized_pnl(conn)
    p30_post_fix_validation(conn)

    conn.close()

    print("\n" + "=" * 80)
    print("  PART 2 ANALYSIS COMPLETE")
    print("  Run Part 1: python scripts/analyze_agape_spot_profitability.py")
    print("  Run Part 2: python scripts/analyze_agape_spot_profitability_p2.py")
    print("=" * 80)


if __name__ == "__main__":
    main()
