#!/usr/bin/env python3
"""
AGAPE-SPOT POST-FIX MONITORING SCRIPT
=======================================
Compares pre-fix baseline (before Feb 15 2026 19:00 UTC) vs post-fix performance.
Run on Render shell every 48-72h to evaluate whether fixes are working.

Run:
  python scripts/analyze_agape_spot_postfix.py

What was fixed on Feb 15, 2026:
  F1: Silent sell retry (DB-vs-exchange drift, orphaned coins)
  F2: Position pileup fix (93 BTC positions blocking ETH scans)
  F3: EWMA dynamic choppy gate (replaced flat $0.50 threshold)
  F4: BTC tightened (max_hold 4h, max 2 positions, cooldown 5 scans)
  F5: Major/altcoin bias split removed (BTC/ETH no longer disadvantaged)
  F6: Momentum filter relaxed (-0.2% to -0.5%)
  F7: Orphan auto-sell (stranded Coinbase coins get market-sold)
  F8: ETH max positions 5->3 (flash crash exposure cut 40%)
  F9: DOGE funding gate enforced (no more ALTCOIN_BASE_LONG fallback)
  F10: Fallback position cleanup (legacy ghosts closed at entry price)
  F11: Per-ticker max_hold_hours (BTC uses 4h not global 6h)
  F12: Paper mirrors live exactly (paper = shadow of live fills)

Pre-fix baseline (from P1-P17 analysis on Feb 15):
  ETH-USD:  196 trades, +$188.05, 58.2% WR, avg +$0.96
  DOGE-USD: 303 trades, +$45.79, 61.1% WR, avg +$0.15
  BTC-USD:  19 trades,  +$0.24,  52.6% WR, avg +$0.01
  XRP-USD:  117 trades, -$0.55,  50.4% WR, avg -$0.00
  SHIB-USD: 142 trades, -$0.64,  48.6% WR, avg -$0.00

Key pre-fix problems identified:
  - ETH 32-trade max loss streak (likely during position pileup)
  - ETH loses -$475 overnight (5pm-8am CT), makes +$545 during market hours
  - DOGE 42.6 trades/day, estimated $116/week in fees vs $45 P&L
  - BTC 17/19 trades expired MAX_HOLD with $0.03 avg (wrong timeout)
  - XRP/SHIB negative EV: below breakeven WR with unfavorable R:R
  - Fee tracking broken: only 3 of 777 trades have fee data
  - 359 BTC_fallback positions at 3.3% WR dragging all BTC stats
"""

import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CENTRAL_TZ = ZoneInfo("America/Chicago")

# Deploy cutoff: last fix commit was 2026-02-15 19:55 UTC
# Use 20:00 UTC as a clean cutoff (2pm CT)
FIX_CUTOFF = "2026-02-15 20:00:00+00"

TICKERS = ["ETH-USD", "BTC-USD", "XRP-USD", "SHIB-USD", "DOGE-USD"]

# Pre-fix baseline from P1-P17 analysis
PRE_FIX_BASELINE = {
    "ETH-USD":  {"trades": 196, "pnl": 188.05, "wr": 58.2, "avg_pnl": 0.96, "avg_win": 7.99, "avg_loss": -8.82, "max_streak": 32, "trades_per_day": 28.0},
    "DOGE-USD": {"trades": 303, "pnl": 45.79,  "wr": 61.1, "avg_pnl": 0.15, "avg_win": 0.31, "avg_loss": -0.09, "max_streak": 17, "trades_per_day": 42.6},
    "BTC-USD":  {"trades": 19,  "pnl": 0.24,   "wr": 52.6, "avg_pnl": 0.01, "avg_win": 0.06, "avg_loss": -0.03, "max_streak": 5,  "trades_per_day": 2.7},
    "XRP-USD":  {"trades": 117, "pnl": -0.55,  "wr": 50.4, "avg_pnl": 0.00, "avg_win": 0.05, "avg_loss": -0.06, "max_streak": 13, "trades_per_day": 16.7},
    "SHIB-USD": {"trades": 142, "pnl": -0.64,  "wr": 48.6, "avg_pnl": 0.00, "avg_win": 0.07, "avg_loss": -0.08, "max_streak": 21, "trades_per_day": 20.3},
}

# Breakeven WR thresholds (pre-fix)
BREAKEVEN_WR = {
    "ETH-USD": 52.4,   # |avg_loss| / (avg_win + |avg_loss|)
    "DOGE-USD": 22.5,
    "BTC-USD": 33.3,
    "XRP-USD": 54.5,
    "SHIB-USD": 53.3,
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
        print(f"ERROR: Database connection failed: {e}")
        sys.exit(1)


def run_query(conn, sql, params=None):
    cursor = conn.cursor()
    cursor.execute(sql, params)
    rows = cursor.fetchall()
    cursor.close()
    return rows


def fmt_pnl(val):
    if val is None:
        return "N/A"
    v = float(val)
    sign = "+" if v >= 0 else ""
    return f"${sign}{v:,.2f}"


def fmt_delta(post, pre, unit="%", better="higher"):
    """Format a comparison as delta with verdict."""
    if pre is None or post is None:
        return "N/A"
    delta = post - pre
    sign = "+" if delta >= 0 else ""
    if better == "higher":
        verdict = "BETTER" if delta > 0 else "WORSE" if delta < 0 else "SAME"
    else:
        verdict = "BETTER" if delta < 0 else "WORSE" if delta > 0 else "SAME"
    return f"{sign}{delta:.1f}{unit} ({verdict})"


# ===================================================================
# PF1: Post-Fix Summary vs Pre-Fix Baseline
# ===================================================================
def pf1_summary_comparison(conn):
    print("\n" + "=" * 80)
    print("PF1: POST-FIX SUMMARY vs PRE-FIX BASELINE")
    print("=" * 80)
    print(f"  Fix cutoff: {FIX_CUTOFF}")

    rows = run_query(conn, """
        SELECT
            ticker,
            COUNT(*) AS trades,
            COUNT(*) FILTER (WHERE realized_pnl > 0) AS wins,
            COUNT(*) FILTER (WHERE realized_pnl < 0) AS losses,
            COALESCE(SUM(realized_pnl), 0) AS total_pnl,
            COALESCE(AVG(realized_pnl), 0) AS avg_pnl,
            COALESCE(AVG(realized_pnl) FILTER (WHERE realized_pnl > 0), 0) AS avg_win,
            COALESCE(AVG(realized_pnl) FILTER (WHERE realized_pnl < 0), 0) AS avg_loss,
            MIN(open_time) AS first_trade,
            MAX(close_time) AS last_trade
        FROM agape_spot_positions
        WHERE status IN ('closed', 'expired', 'stopped')
          AND realized_pnl IS NOT NULL
          AND account_label NOT LIKE '%%fallback%%'
          AND account_label != 'paper'
          AND open_time > %s
        GROUP BY ticker
        ORDER BY COALESCE(SUM(realized_pnl), 0) DESC
    """, (FIX_CUTOFF,))

    if not rows:
        print("\n  NO POST-FIX TRADES YET. Run again after 24-48h.")
        return

    # Calculate hours since fix
    first_post = min(r[8] for r in rows if r[8])
    last_post = max(r[9] for r in rows if r[9])
    hours_trading = (last_post - first_post).total_seconds() / 3600 if first_post and last_post else 0

    print(f"  Post-fix trading period: {hours_trading:.1f} hours")
    print(f"  First post-fix trade: {first_post}")
    print(f"  Latest trade: {last_post}")

    print(f"\n  {'Ticker':<10} {'Trades':>6} | {'WR%':>6} {'(pre)':>6} {'delta':>14} | {'Avg P&L':>8} {'(pre)':>8} | {'Total P&L':>10} | {'Avg Win':>8} {'Avg Loss':>9}")
    print(f"  {'-'*105}")

    total_post_pnl = 0
    for r in rows:
        ticker = r[0]
        trades, wins, losses = r[1], r[2] or 0, r[3] or 0
        total_pnl, avg_pnl = float(r[4]), float(r[5])
        avg_win, avg_loss = float(r[6]), float(r[7])
        wr = wins / trades * 100 if trades > 0 else 0
        total_post_pnl += total_pnl

        pre = PRE_FIX_BASELINE.get(ticker, {})
        pre_wr = pre.get("wr", 0)
        pre_avg = pre.get("avg_pnl", 0)
        wr_delta = fmt_delta(wr, pre_wr)

        be_wr = BREAKEVEN_WR.get(ticker, 50)
        wr_flag = " OK" if wr > be_wr else " BELOW BE"

        print(f"  {ticker:<10} {trades:>6} | {wr:>5.1f}% {pre_wr:>5.1f}% {wr_delta:>14} | {fmt_pnl(avg_pnl):>8} {fmt_pnl(pre_avg):>8} | {fmt_pnl(total_pnl):>10} | {fmt_pnl(avg_win):>8} {fmt_pnl(avg_loss):>9}{wr_flag}")

    print(f"  {'-'*105}")
    print(f"  TOTAL POST-FIX P&L: {fmt_pnl(total_post_pnl)}")


# ===================================================================
# PF2: Fix Validation - Did each fix work?
# ===================================================================
def pf2_fix_validation(conn):
    print("\n" + "=" * 80)
    print("PF2: FIX VALIDATION — Is each fix working?")
    print("=" * 80)

    # F1: Silent sell retry — check for orphaned coins
    print("\n  F1: SILENT SELL RETRY")
    rows = run_query(conn, """
        SELECT COUNT(*) FROM agape_spot_positions
        WHERE status = 'open'
          AND sell_fail_count > 0
    """)
    fail_count = rows[0][0] if rows else 0
    print(f"     Open positions with sell failures: {fail_count}")
    if fail_count > 0:
        retries = run_query(conn, """
            SELECT ticker, sell_fail_count, position_id
            FROM agape_spot_positions
            WHERE status = 'open' AND sell_fail_count > 0
            ORDER BY sell_fail_count DESC LIMIT 5
        """)
        for r in retries:
            print(f"       {r[0]}: {r[1]} failures — {r[2]}")
    else:
        print(f"     PASS: No stuck sells")

    # F2: Position pileup — max simultaneous positions
    print("\n  F2: POSITION PILEUP (was 93 simultaneous, limit should be ~36)")
    rows = run_query(conn, """
        SELECT ticker, COUNT(*) as open_count
        FROM agape_spot_positions
        WHERE status = 'open'
          AND account_label NOT LIKE '%%fallback%%'
        GROUP BY ticker
        ORDER BY open_count DESC
    """)
    total_open = sum(r[1] for r in rows) if rows else 0
    print(f"     Current open positions: {total_open}")
    for r in rows:
        limit = 3 if r[0] == 'ETH-USD' else 2 if r[0] == 'BTC-USD' else 5
        flag = " OVER LIMIT!" if r[1] > limit else ""
        print(f"       {r[0]}: {r[1]} open (limit: {limit}){flag}")
    if total_open <= 36:
        print(f"     PASS: Under 36 total")
    else:
        print(f"     FAIL: {total_open} > 36 limit")

    # F4: BTC max_hold_hours — check BTC hold durations post-fix
    print("\n  F4: BTC MAX HOLD (was using 6h global, should be 4h)")
    rows = run_query(conn, """
        SELECT
            ROUND(AVG(EXTRACT(EPOCH FROM (close_time - open_time)) / 3600)::numeric, 1) as avg_hold_hours,
            MAX(EXTRACT(EPOCH FROM (close_time - open_time)) / 3600) as max_hold_hours,
            COUNT(*) as trades
        FROM agape_spot_positions
        WHERE ticker = 'BTC-USD'
          AND status IN ('closed', 'expired', 'stopped')
          AND account_label NOT LIKE '%%fallback%%'
          AND account_label != 'paper'
          AND open_time > %s
    """, (FIX_CUTOFF,))
    if rows and rows[0][2] and rows[0][2] > 0:
        avg_h, max_h, cnt = float(rows[0][0] or 0), float(rows[0][1] or 0), rows[0][2]
        print(f"     Post-fix BTC: {cnt} trades, avg hold {avg_h}h, max hold {max_h:.1f}h")
        print(f"     {'PASS' if max_h <= 4.5 else 'FAIL'}: Max hold {'<=' if max_h <= 4.5 else '>'} 4.5h")
    else:
        print(f"     No post-fix BTC trades yet")

    # F8: ETH max positions — check max simultaneous ETH
    print("\n  F8: ETH MAX POSITIONS (was 5, now 3)")
    rows = run_query(conn, """
        SELECT COUNT(*) FROM agape_spot_positions
        WHERE ticker = 'ETH-USD'
          AND status = 'open'
          AND account_label NOT LIKE '%%fallback%%'
          AND account_label != 'paper'
    """)
    eth_open = rows[0][0] if rows else 0
    print(f"     ETH open positions: {eth_open}")
    print(f"     {'PASS' if eth_open <= 3 else 'FAIL'}: {'<= 3' if eth_open <= 3 else '> 3 LIMIT EXCEEDED'}")

    # F9: DOGE funding gate — check if DOGE trades have funding data
    print("\n  F9: DOGE FUNDING GATE (was entering with no signal)")
    rows = run_query(conn, """
        SELECT
            funding_regime_at_entry,
            COUNT(*) as cnt
        FROM agape_spot_positions
        WHERE ticker = 'DOGE-USD'
          AND account_label NOT LIKE '%%fallback%%'
          AND account_label != 'paper'
          AND open_time > %s
        GROUP BY funding_regime_at_entry
        ORDER BY cnt DESC
    """, (FIX_CUTOFF,))
    if rows:
        for r in rows:
            regime = r[0] or 'NULL/UNKNOWN'
            flag = " GATE BYPASSED!" if regime in ('UNKNOWN', None) else ""
            print(f"       {regime}: {r[1]} trades{flag}")
    else:
        print(f"     No post-fix DOGE trades yet")

    # F10: Fallback cleanup — any fallback positions still open?
    print("\n  F10: FALLBACK CLEANUP (was 359 BTC_fallback zombie positions)")
    rows = run_query(conn, """
        SELECT account_label, ticker, COUNT(*), status
        FROM agape_spot_positions
        WHERE account_label LIKE '%%fallback%%'
        GROUP BY account_label, ticker, status
        ORDER BY count DESC
    """)
    if rows:
        open_fallbacks = sum(r[2] for r in rows if r[3] == 'open')
        closed_fallbacks = sum(r[2] for r in rows if r[3] != 'open')
        print(f"     Open fallback positions: {open_fallbacks}")
        print(f"     Closed fallback positions: {closed_fallbacks}")
        for r in rows:
            if r[3] == 'open':
                print(f"       STILL OPEN: {r[0]} {r[1]}: {r[2]} positions")
        if open_fallbacks == 0:
            print(f"     PASS: All fallbacks closed")
        else:
            print(f"     FAIL: {open_fallbacks} fallbacks still open")
    else:
        print(f"     PASS: No fallback positions exist")


# ===================================================================
# PF3: Overtrading Check (was DOGE 42.6/day)
# ===================================================================
def pf3_overtrading(conn):
    print("\n" + "=" * 80)
    print("PF3: OVERTRADING CHECK")
    print("=" * 80)

    rows = run_query(conn, """
        WITH daily AS (
            SELECT
                ticker,
                DATE(open_time AT TIME ZONE 'America/Chicago') as trade_date,
                COUNT(*) as daily_trades
            FROM agape_spot_positions
            WHERE account_label NOT LIKE '%%fallback%%'
              AND account_label != 'paper'
              AND open_time > %s
            GROUP BY ticker, DATE(open_time AT TIME ZONE 'America/Chicago')
        )
        SELECT
            ticker,
            ROUND(AVG(daily_trades)::numeric, 1) as avg_per_day,
            MAX(daily_trades) as max_day,
            MIN(daily_trades) as min_day,
            COUNT(DISTINCT trade_date) as trading_days
        FROM daily
        GROUP BY ticker
        ORDER BY avg_per_day DESC
    """, (FIX_CUTOFF,))

    if rows:
        print(f"\n  {'Ticker':<12} {'Avg/Day':>8} {'Max Day':>8} {'Min Day':>8} {'Days':>6} | {'Pre-Fix':>8} {'Delta':>14}")
        print(f"  {'-'*80}")
        for r in rows:
            ticker = r[0]
            avg_day, max_day, min_day, days = float(r[1]), r[2], r[3], r[4]
            pre = PRE_FIX_BASELINE.get(ticker, {}).get("trades_per_day", 0)
            delta = fmt_delta(avg_day, pre, unit="/day", better="lower")
            print(f"  {ticker:<12} {avg_day:>7.1f} {max_day:>8} {min_day:>8} {days:>6} | {pre:>7.1f} {delta:>14}")
    else:
        print("  No post-fix trades yet")


# ===================================================================
# PF4: Close Reason Distribution (pre vs post fix)
# ===================================================================
def pf4_close_reasons(conn):
    print("\n" + "=" * 80)
    print("PF4: CLOSE REASON DISTRIBUTION (post-fix)")
    print("=" * 80)
    print("  Key: More TRAILING_STOP = good. Less MAX_LOSS = good.")

    rows = run_query(conn, """
        SELECT
            ticker,
            CASE
                WHEN close_reason LIKE 'TRAIL%%' THEN 'TRAILING_STOP'
                WHEN close_reason LIKE 'MAX_LOSS%%' THEN 'MAX_LOSS'
                WHEN close_reason LIKE 'MAX_HOLD%%' OR close_reason LIKE 'STALE%%' THEN 'MAX_HOLD'
                WHEN close_reason LIKE 'PROFIT_TARGET%%' THEN 'PROFIT_TARGET'
                WHEN close_reason LIKE 'EMERGENCY%%' THEN 'EMERGENCY'
                WHEN close_reason LIKE 'FORCE_EXPIRED%%' THEN 'FORCE_EXPIRED'
                ELSE COALESCE(close_reason, 'UNKNOWN')
            END AS reason_group,
            COUNT(*) AS cnt,
            ROUND(AVG(realized_pnl)::numeric, 2) AS avg_pnl,
            ROUND(SUM(realized_pnl)::numeric, 2) AS total_pnl
        FROM agape_spot_positions
        WHERE status IN ('closed', 'expired', 'stopped')
          AND account_label NOT LIKE '%%fallback%%'
          AND account_label != 'paper'
          AND open_time > %s
        GROUP BY ticker, reason_group
        ORDER BY ticker, cnt DESC
    """, (FIX_CUTOFF,))

    if rows:
        print(f"\n  {'Ticker':<12} {'Reason':<18} {'Count':>6} {'Avg P&L':>10} {'Total P&L':>10}")
        print(f"  {'-'*60}")
        current = None
        for r in rows:
            ticker = r[0]
            if ticker != current:
                if current:
                    print(f"  {'-'*60}")
                current = ticker
            reason, cnt = r[1], r[2]
            avg_pnl, total_pnl = float(r[3] or 0), float(r[4] or 0)
            print(f"  {ticker:<12} {reason:<18} {cnt:>6} {fmt_pnl(avg_pnl):>10} {fmt_pnl(total_pnl):>10}")
    else:
        print("  No post-fix trades yet")


# ===================================================================
# PF5: Time of Day — Is ETH still losing overnight?
# ===================================================================
def pf5_time_of_day(conn):
    print("\n" + "=" * 80)
    print("PF5: TIME OF DAY P&L (post-fix)")
    print("=" * 80)
    print("  Pre-fix: ETH made +$545 (9am-2pm CT) and lost -$475 (5pm-8am CT)")

    rows = run_query(conn, """
        SELECT
            ticker,
            CASE
                WHEN EXTRACT(HOUR FROM open_time AT TIME ZONE 'America/Chicago') BETWEEN 9 AND 14
                THEN 'MARKET_HOURS_9to2'
                WHEN EXTRACT(HOUR FROM open_time AT TIME ZONE 'America/Chicago') BETWEEN 15 AND 16
                THEN 'AFTERNOON_3to4'
                ELSE 'OFF_HOURS'
            END AS period,
            COUNT(*) AS trades,
            COALESCE(SUM(realized_pnl), 0) AS total_pnl,
            ROUND(100.0 * COUNT(*) FILTER (WHERE realized_pnl > 0) / NULLIF(COUNT(*), 0)::numeric, 1) AS wr
        FROM agape_spot_positions
        WHERE status IN ('closed', 'expired', 'stopped')
          AND realized_pnl IS NOT NULL
          AND account_label NOT LIKE '%%fallback%%'
          AND account_label != 'paper'
          AND open_time > %s
        GROUP BY ticker, period
        ORDER BY ticker, period
    """, (FIX_CUTOFF,))

    if rows:
        print(f"\n  {'Ticker':<12} {'Period':<22} {'Trades':>7} {'P&L':>10} {'WR%':>7}")
        print(f"  {'-'*65}")
        current = None
        for r in rows:
            ticker = r[0]
            if ticker != current:
                if current:
                    print(f"  {'-'*65}")
                current = ticker
            period, trades, pnl, wr = r[1], r[2], float(r[3]), float(r[4] or 0)
            flag = " STILL LOSING" if period == 'OFF_HOURS' and pnl < 0 else ""
            print(f"  {ticker:<12} {period:<22} {trades:>7} {fmt_pnl(pnl):>10} {wr:>6.1f}%{flag}")
    else:
        print("  No post-fix trades yet")


# ===================================================================
# PF6: Fee Tracking Check (was 3 of 777 with data)
# ===================================================================
def pf6_fee_tracking(conn):
    print("\n" + "=" * 80)
    print("PF6: FEE TRACKING (was 3 of 777 trades with fee data)")
    print("=" * 80)

    rows = run_query(conn, """
        SELECT
            ticker,
            COUNT(*) AS trades,
            COUNT(*) FILTER (WHERE entry_fee_usd IS NOT NULL AND entry_fee_usd > 0) AS has_entry_fee,
            COUNT(*) FILTER (WHERE exit_fee_usd IS NOT NULL AND exit_fee_usd > 0) AS has_exit_fee,
            ROUND(COALESCE(SUM(entry_fee_usd), 0)::numeric, 2) AS total_entry_fees,
            ROUND(COALESCE(SUM(exit_fee_usd), 0)::numeric, 2) AS total_exit_fees,
            ROUND(COALESCE(SUM(realized_pnl), 0)::numeric, 2) AS total_pnl
        FROM agape_spot_positions
        WHERE status IN ('closed', 'expired', 'stopped')
          AND account_label NOT LIKE '%%fallback%%'
          AND account_label != 'paper'
          AND open_time > %s
        GROUP BY ticker
        ORDER BY ticker
    """, (FIX_CUTOFF,))

    if rows:
        total_trades = sum(r[1] for r in rows)
        total_with_fees = sum(r[2] for r in rows)
        pct = total_with_fees / total_trades * 100 if total_trades > 0 else 0

        print(f"\n  Fee data coverage: {total_with_fees}/{total_trades} trades ({pct:.0f}%)")
        if pct < 50:
            print(f"  STILL BROKEN: Fee tracking needs fixing in executor.py")
        elif pct < 95:
            print(f"  PARTIAL: Some trades missing fee data")
        else:
            print(f"  PASS: Fee data being recorded")

        print(f"\n  {'Ticker':<12} {'Trades':>7} {'w/ Entry Fee':>12} {'w/ Exit Fee':>12} {'Total Fees':>10} {'P&L':>10} {'Fee/PnL':>8}")
        print(f"  {'-'*75}")
        for r in rows:
            ticker, trades = r[0], r[1]
            has_entry, has_exit = r[2], r[3]
            total_fees = float(r[4]) + float(r[5])
            total_pnl = float(r[6])
            fee_ratio = abs(total_fees / total_pnl * 100) if total_pnl != 0 else 0
            print(f"  {ticker:<12} {trades:>7} {has_entry:>12} {has_exit:>12} {fmt_pnl(-total_fees):>10} {fmt_pnl(total_pnl):>10} {fee_ratio:>6.1f}%")
    else:
        print("  No post-fix trades yet")


# ===================================================================
# PF7: Consecutive Loss Streak (post-fix)
# ===================================================================
def pf7_loss_streaks(conn):
    print("\n" + "=" * 80)
    print("PF7: CONSECUTIVE LOSS STREAKS (post-fix)")
    print("=" * 80)

    for ticker in TICKERS:
        rows = run_query(conn, """
            SELECT realized_pnl
            FROM agape_spot_positions
            WHERE ticker = %s
              AND status IN ('closed', 'expired', 'stopped')
              AND realized_pnl IS NOT NULL
              AND account_label NOT LIKE '%%fallback%%'
              AND account_label != 'paper'
              AND open_time > %s
            ORDER BY close_time ASC
        """, (ticker, FIX_CUTOFF))

        if not rows:
            continue

        max_streak = 0
        current_streak = 0
        for r in rows:
            if float(r[0]) <= 0:
                current_streak += 1
                max_streak = max(max_streak, current_streak)
            else:
                current_streak = 0

        pre_streak = PRE_FIX_BASELINE.get(ticker, {}).get("max_streak", 0)
        delta = fmt_delta(max_streak, pre_streak, unit="", better="lower")
        print(f"  {ticker:<12} Max streak: {max_streak:>3}  (pre-fix: {pre_streak})  {delta}")


# ===================================================================
# PF8: Win/Loss R:R Ratio (post-fix vs pre-fix)
# ===================================================================
def pf8_risk_reward(conn):
    print("\n" + "=" * 80)
    print("PF8: RISK/REWARD RATIO (post-fix vs pre-fix)")
    print("=" * 80)

    rows = run_query(conn, """
        SELECT
            ticker,
            COALESCE(AVG(realized_pnl) FILTER (WHERE realized_pnl > 0), 0) AS avg_win,
            COALESCE(AVG(realized_pnl) FILTER (WHERE realized_pnl < 0), 0) AS avg_loss,
            COUNT(*) FILTER (WHERE realized_pnl > 0) AS wins,
            COUNT(*) FILTER (WHERE realized_pnl < 0) AS losses,
            COUNT(*) AS total
        FROM agape_spot_positions
        WHERE status IN ('closed', 'expired', 'stopped')
          AND realized_pnl IS NOT NULL
          AND account_label NOT LIKE '%%fallback%%'
          AND account_label != 'paper'
          AND open_time > %s
        GROUP BY ticker
        ORDER BY ticker
    """, (FIX_CUTOFF,))

    if rows:
        print(f"\n  {'Ticker':<12} {'Avg Win':>8} {'(pre)':>8} {'Avg Loss':>9} {'(pre)':>9} {'R:R':>6} {'BE WR':>7} {'Act WR':>7} {'EV/trade':>10}")
        print(f"  {'-'*90}")
        for r in rows:
            ticker = r[0]
            avg_win, avg_loss = float(r[1]), float(r[2])
            wins, losses, total = r[3] or 0, r[4] or 0, r[5]
            wr = wins / total * 100 if total > 0 else 0

            pre = PRE_FIX_BASELINE.get(ticker, {})
            pre_win = pre.get("avg_win", 0)
            pre_loss = pre.get("avg_loss", 0)

            rr = avg_win / abs(avg_loss) if avg_loss != 0 else 999
            be_wr = abs(avg_loss) / (avg_win + abs(avg_loss)) * 100 if (avg_win + abs(avg_loss)) > 0 else 50
            ev = (wr/100 * avg_win) + ((1 - wr/100) * avg_loss)
            ev_flag = " +EV" if ev > 0 else " -EV"

            print(f"  {ticker:<12} {fmt_pnl(avg_win):>8} {fmt_pnl(pre_win):>8} {fmt_pnl(avg_loss):>9} {fmt_pnl(pre_loss):>9} {rr:>5.2f} {be_wr:>6.1f}% {wr:>6.1f}% {fmt_pnl(ev):>10}{ev_flag}")
    else:
        print("  No post-fix trades yet")


# ===================================================================
# PF9: Scan Effectiveness (are scans converting to trades?)
# ===================================================================
def pf9_scan_effectiveness(conn):
    print("\n" + "=" * 80)
    print("PF9: SCAN EFFECTIVENESS (post-fix)")
    print("=" * 80)
    print("  Pre-fix: 1,068/1,400 ETH scans were blocked by position pileup")

    rows = run_query(conn, """
        SELECT
            ticker,
            outcome,
            COUNT(*) as cnt
        FROM agape_spot_scan_activity
        WHERE timestamp > %s
        GROUP BY ticker, outcome
        ORDER BY ticker, cnt DESC
    """, (FIX_CUTOFF,))

    if rows:
        print(f"\n  {'Ticker':<12} {'Outcome':<30} {'Count':>8} {'%':>7}")
        print(f"  {'-'*60}")
        # Calculate totals per ticker
        ticker_totals = {}
        for r in rows:
            ticker_totals[r[0]] = ticker_totals.get(r[0], 0) + r[2]

        current = None
        for r in rows:
            ticker, outcome, cnt = r[0], r[1], r[2]
            if ticker != current:
                if current:
                    print(f"  {'-'*60}")
                current = ticker
            pct = cnt / ticker_totals[ticker] * 100 if ticker_totals[ticker] > 0 else 0
            flag = " FIX NEEDED" if outcome in ('BLOCKED_BY_CAPACITY', 'MAX_POSITIONS') and pct > 30 else ""
            print(f"  {ticker:<12} {outcome:<30} {cnt:>8} {pct:>6.1f}%{flag}")
    else:
        print("  No post-fix scan data yet")


# ===================================================================
# PF10: Quick Health Dashboard
# ===================================================================
def pf10_health_dashboard(conn):
    print("\n" + "=" * 80)
    print("PF10: QUICK HEALTH DASHBOARD")
    print("=" * 80)

    checks = []

    # Check 1: Any trades happening?
    rows = run_query(conn, """
        SELECT COUNT(*) FROM agape_spot_positions
        WHERE open_time > %s AND account_label NOT LIKE '%%fallback%%' AND account_label != 'paper'
    """, (FIX_CUTOFF,))
    trade_count = rows[0][0] if rows else 0
    checks.append(("Trades executing", "PASS" if trade_count > 0 else "FAIL", f"{trade_count} trades"))

    # Check 2: No open fallback positions
    rows = run_query(conn, """
        SELECT COUNT(*) FROM agape_spot_positions
        WHERE account_label LIKE '%%fallback%%' AND status = 'open'
    """)
    fb = rows[0][0] if rows else 0
    checks.append(("No open fallbacks", "PASS" if fb == 0 else "FAIL", f"{fb} open"))

    # Check 3: Position count under limit
    rows = run_query(conn, """
        SELECT COUNT(*) FROM agape_spot_positions
        WHERE status = 'open' AND account_label NOT LIKE '%%fallback%%'
    """)
    open_ct = rows[0][0] if rows else 0
    checks.append(("Positions under limit", "PASS" if open_ct <= 36 else "FAIL", f"{open_ct} open"))

    # Check 4: No sell failures stuck
    rows = run_query(conn, """
        SELECT COUNT(*) FROM agape_spot_positions
        WHERE status = 'open' AND sell_fail_count >= 3
    """)
    stuck = rows[0][0] if rows else 0
    checks.append(("No stuck sells (3+ fails)", "PASS" if stuck == 0 else "FAIL", f"{stuck} stuck"))

    # Check 5: Post-fix P&L positive
    rows = run_query(conn, """
        SELECT COALESCE(SUM(realized_pnl), 0) FROM agape_spot_positions
        WHERE status IN ('closed', 'expired', 'stopped')
          AND account_label NOT LIKE '%%fallback%%' AND account_label != 'paper'
          AND open_time > %s
    """, (FIX_CUTOFF,))
    post_pnl = float(rows[0][0]) if rows else 0
    checks.append(("Post-fix P&L positive", "PASS" if post_pnl > 0 else "WARN" if post_pnl == 0 else "FAIL", fmt_pnl(post_pnl)))

    # Check 6: Paper mirrors live
    rows = run_query(conn, """
        SELECT
            COUNT(*) FILTER (WHERE account_label = 'paper') as paper,
            COUNT(*) FILTER (WHERE account_label != 'paper') as live
        FROM agape_spot_positions
        WHERE open_time > %s
          AND account_label NOT LIKE '%%fallback%%'
    """, (FIX_CUTOFF,))
    paper, live = (rows[0][0], rows[0][1]) if rows else (0, 0)
    mirror_ok = abs(paper - live) < max(live * 0.2, 5) if live > 0 else True
    checks.append(("Paper mirrors live", "PASS" if mirror_ok else "WARN", f"paper={paper} live={live}"))

    print(f"\n  {'Check':<30} {'Status':>8} {'Detail'}")
    print(f"  {'-'*65}")
    for name, status, detail in checks:
        icon = "PASS" if status == "PASS" else "WARN" if status == "WARN" else "FAIL"
        print(f"  {name:<30} {icon:>8}   {detail}")

    passed = sum(1 for _, s, _ in checks if s == "PASS")
    total = len(checks)
    print(f"\n  Score: {passed}/{total} checks passed")


# ===================================================================
# PF11: Go/No-Go Decision Table
# ===================================================================
def pf11_go_nogo(conn):
    print("\n" + "=" * 80)
    print("PF11: GO / NO-GO DECISION TABLE")
    print("=" * 80)
    print("  Based on post-fix data. Minimum 20 trades needed for evaluation.")

    rows = run_query(conn, """
        SELECT
            ticker,
            COUNT(*) AS trades,
            ROUND(100.0 * COUNT(*) FILTER (WHERE realized_pnl > 0) / NULLIF(COUNT(*), 0)::numeric, 1) AS wr,
            COALESCE(SUM(realized_pnl), 0) AS total_pnl,
            COALESCE(AVG(realized_pnl) FILTER (WHERE realized_pnl > 0), 0) AS avg_win,
            COALESCE(AVG(realized_pnl) FILTER (WHERE realized_pnl < 0), 0) AS avg_loss
        FROM agape_spot_positions
        WHERE status IN ('closed', 'expired', 'stopped')
          AND realized_pnl IS NOT NULL
          AND account_label NOT LIKE '%%fallback%%'
          AND account_label != 'paper'
          AND open_time > %s
        GROUP BY ticker
        ORDER BY COALESCE(SUM(realized_pnl), 0) DESC
    """, (FIX_CUTOFF,))

    if rows:
        print(f"\n  {'Ticker':<12} {'Trades':>6} {'WR%':>6} {'P&L':>10} {'EV/trade':>10} {'Decision':>10} {'Reason'}")
        print(f"  {'-'*85}")
        for r in rows:
            ticker = r[0]
            trades, wr = r[1], float(r[2] or 0)
            total_pnl = float(r[3])
            avg_win, avg_loss = float(r[4]), float(r[5])

            be_wr = abs(avg_loss) / (avg_win + abs(avg_loss)) * 100 if (avg_win + abs(avg_loss)) > 0 else 50
            ev = (wr/100 * avg_win) + ((1 - wr/100) * avg_loss)

            if trades < 20:
                decision = "WAIT"
                reason = f"Only {trades} trades, need 20+"
            elif ev > 0 and wr > be_wr:
                decision = "GO"
                reason = f"+EV ({fmt_pnl(ev)}), WR {wr:.0f}% > BE {be_wr:.0f}%"
            elif ev > 0:
                decision = "MONITOR"
                reason = f"+EV but WR near breakeven"
            else:
                decision = "STOP"
                reason = f"-EV ({fmt_pnl(ev)}), WR {wr:.0f}% < BE {be_wr:.0f}%"

            pre_pnl = PRE_FIX_BASELINE.get(ticker, {}).get("pnl", 0)
            trend = "improving" if total_pnl > 0 and (pre_pnl <= 0 or total_pnl / max(trades, 1) > pre_pnl / max(PRE_FIX_BASELINE.get(ticker, {}).get("trades", 1), 1)) else "same" if abs(total_pnl) < 1 else "degrading"

            print(f"  {ticker:<12} {trades:>6} {wr:>5.1f}% {fmt_pnl(total_pnl):>10} {fmt_pnl(ev):>10} {decision:>10}   {reason} [{trend}]")
    else:
        print("  No post-fix trades yet. Run again in 24-48 hours.")


# ===================================================================
# MAIN
# ===================================================================
def main():
    print("=" * 80)
    print("  AGAPE-SPOT POST-FIX MONITORING REPORT")
    print(f"  Generated: {datetime.now(CENTRAL_TZ).strftime('%Y-%m-%d %H:%M:%S CT')}")
    print(f"  Fix cutoff: {FIX_CUTOFF}")
    print(f"  Comparing post-fix trades against pre-fix baseline")
    print("=" * 80)

    conn = get_db_connection()

    # Quick check
    count = run_query(conn, """
        SELECT COUNT(*) FROM agape_spot_positions
        WHERE open_time > %s AND account_label NOT LIKE '%%fallback%%' AND account_label != 'paper'
    """, (FIX_CUTOFF,))
    post_count = count[0][0] if count else 0
    print(f"\n  Post-fix trades found: {post_count}")

    if post_count == 0:
        print("\n  NO POST-FIX TRADES YET.")
        print("  Fixes were deployed ~Feb 15 20:00 UTC.")
        print("  Run again after 24-48 hours of trading.")
        conn.close()
        return

    # Run all monitoring queries
    pf1_summary_comparison(conn)
    pf2_fix_validation(conn)
    pf3_overtrading(conn)
    pf4_close_reasons(conn)
    pf5_time_of_day(conn)
    pf6_fee_tracking(conn)
    pf7_loss_streaks(conn)
    pf8_risk_reward(conn)
    pf9_scan_effectiveness(conn)
    pf10_health_dashboard(conn)
    pf11_go_nogo(conn)

    conn.close()

    print("\n" + "=" * 80)
    print("  MONITORING COMPLETE")
    print("  Schedule: Run every 48-72h")
    print("  Command:  python scripts/analyze_agape_spot_postfix.py")
    print("  Decision: After 7 days post-fix, use PF11 GO/NO-GO to decide each ticker")
    print("=" * 80)


if __name__ == "__main__":
    main()
