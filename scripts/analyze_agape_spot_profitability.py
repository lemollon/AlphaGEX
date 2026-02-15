#!/usr/bin/env python3
"""
AGAPE-SPOT COMPREHENSIVE PROFITABILITY ANALYSIS
================================================
Completes Sections 8-14 of the AGAPE-SPOT audit that couldn't run
without DATABASE_URL.

Run on Render shell or locally with DATABASE_URL set:
  python scripts/analyze_agape_spot_profitability.py

Queries (P1-P17):
  P1:  Overall summary (all tickers aggregate + per-ticker)
  P2:  Win/loss size asymmetry (the #1 known issue)
  P3:  P&L by funding regime (Bayesian tracker validation)
  P4:  P&L by close reason (trailing stop vs max loss vs expired)
  P5:  Hold duration vs outcome (are we holding losers too long?)
  P6:  P&L by time of day (24/7 crypto patterns)
  P7:  P&L by day of week
  P8:  Bayesian win tracker state (per-ticker, per-regime)
  P9:  Capital allocator rankings (current live state)
  P10: Scan activity breakdown (why trades are skipped)
  P11: Alpha vs buy-and-hold (is the bot capturing beta or alpha?)
  P12: Fee & slippage impact (Coinbase execution cost)
  P13: Consecutive loss streaks
  P14: Paper vs live account comparison
  P15: Recent trade trend (last 30 trades per ticker)
  P16: Orphaned positions check (open with no activity)
  P17: EV gate effectiveness (choppy vs non-choppy trades)
"""

import os
import sys
from datetime import datetime, timedelta
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
    """Get database connection."""
    try:
        import psycopg2
        url = os.environ.get("DATABASE_URL")
        if not url:
            # Try loading from .env file
            env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
            if os.path.exists(env_path):
                with open(env_path) as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("DATABASE_URL=") and not line.startswith("#"):
                            url = line.split("=", 1)[1].strip()
                            break
        if not url:
            print("ERROR: DATABASE_URL not set. Export it or create .env file.")
            sys.exit(1)
        return psycopg2.connect(url, connect_timeout=15)
    except Exception as e:
        print(f"ERROR: Database connection failed: {e}")
        sys.exit(1)


def run_query(conn, sql, params=None):
    """Run a query and return all rows."""
    cursor = conn.cursor()
    cursor.execute(sql, params)
    rows = cursor.fetchall()
    cursor.close()
    return rows


def fmt_pnl(val):
    """Format P&L with color indicator."""
    if val is None:
        return "N/A"
    v = float(val)
    sign = "+" if v >= 0 else ""
    return f"${sign}{v:,.2f}"


def fmt_pct(val, total):
    """Format as percentage."""
    if total == 0:
        return "0.0%"
    return f"{val / total * 100:.1f}%"


# ===================================================================
# P1: Overall Summary
# ===================================================================
def p1_overall_summary(conn):
    print("\n" + "=" * 80)
    print("P1: OVERALL SUMMARY")
    print("=" * 80)

    # Aggregate
    rows = run_query(conn, """
        SELECT
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE status IN ('closed', 'expired', 'stopped')) AS closed,
            COUNT(*) FILTER (WHERE status = 'open') AS open,
            COUNT(*) FILTER (WHERE realized_pnl > 0) AS wins,
            COUNT(*) FILTER (WHERE realized_pnl < 0) AS losses,
            COUNT(*) FILTER (WHERE realized_pnl = 0) AS breakeven,
            COUNT(*) FILTER (WHERE realized_pnl IS NULL AND status != 'open') AS null_pnl,
            COALESCE(SUM(realized_pnl), 0) AS total_pnl,
            COALESCE(AVG(realized_pnl) FILTER (WHERE realized_pnl IS NOT NULL), 0) AS avg_pnl,
            COALESCE(MAX(realized_pnl), 0) AS max_win,
            COALESCE(MIN(realized_pnl), 0) AS max_loss,
            MIN(open_time) AS first_trade,
            MAX(open_time) AS last_trade
        FROM agape_spot_positions
        WHERE account_label != 'paper'
    """)
    if rows and rows[0][0] > 0:
        r = rows[0]
        total, closed, open_ct, wins, losses, be, null_pnl = r[0], r[1], r[2], r[3] or 0, r[4] or 0, r[5] or 0, r[6] or 0
        total_pnl, avg_pnl, max_win, max_loss = float(r[7]), float(r[8]), float(r[9]), float(r[10])
        first, last = r[11], r[12]
        wr = wins / closed * 100 if closed > 0 else 0

        print(f"\n  AGGREGATE (LIVE accounts only, all tickers)")
        print(f"  {'='*55}")
        print(f"  Total trades:      {total}")
        print(f"  Closed/Expired:    {closed}")
        print(f"  Currently Open:    {open_ct}")
        print(f"  Wins/Losses/BE:    {wins} / {losses} / {be}")
        print(f"  Win Rate:          {wr:.1f}%")
        print(f"  Total P&L:         {fmt_pnl(total_pnl)}")
        print(f"  Avg P&L/trade:     {fmt_pnl(avg_pnl)}")
        print(f"  Best trade:        {fmt_pnl(max_win)}")
        print(f"  Worst trade:       {fmt_pnl(max_loss)}")
        if null_pnl > 0:
            print(f"  NULL P&L trades:   {null_pnl} (data integrity issue)")
        if first and last:
            days = (last - first).days or 1
            print(f"  Trading since:     {first.strftime('%Y-%m-%d')} ({days} days)")
            print(f"  Last trade:        {last.strftime('%Y-%m-%d %H:%M')}")
    else:
        print("  No trades found!")
        return

    # Per-ticker breakdown
    print(f"\n  PER-TICKER BREAKDOWN (LIVE only)")
    print(f"  {'-'*75}")
    print(f"  {'Ticker':<12} {'Trades':>7} {'Wins':>6} {'Losses':>6} {'WR%':>7} {'Total P&L':>12} {'Avg P&L':>10} {'Capital':>8}")
    print(f"  {'-'*75}")

    rows = run_query(conn, """
        SELECT
            ticker,
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE realized_pnl > 0) AS wins,
            COUNT(*) FILTER (WHERE realized_pnl < 0) AS losses,
            COALESCE(SUM(realized_pnl), 0) AS total_pnl,
            COALESCE(AVG(realized_pnl) FILTER (WHERE realized_pnl IS NOT NULL), 0) AS avg_pnl,
            COUNT(*) FILTER (WHERE status = 'open') AS open_ct
        FROM agape_spot_positions
        WHERE account_label != 'paper'
        GROUP BY ticker
        ORDER BY COALESCE(SUM(realized_pnl), 0) DESC
    """)
    for r in rows:
        ticker, total, wins, losses = r[0], r[1], r[2] or 0, r[3] or 0
        total_pnl, avg_pnl = float(r[4]), float(r[5])
        wr = wins / (wins + losses) * 100 if (wins + losses) > 0 else 0
        cap = STARTING_CAPITAL.get(ticker, 1000)
        roi = total_pnl / cap * 100 if cap > 0 else 0
        pnl_str = fmt_pnl(total_pnl)
        avg_str = fmt_pnl(avg_pnl)
        print(f"  {ticker:<12} {total:>7} {wins:>6} {losses:>6} {wr:>6.1f}% {pnl_str:>12} {avg_str:>10} ${cap:,.0f}")

    # ROI summary
    print(f"\n  RETURN ON CAPITAL")
    print(f"  {'-'*50}")
    total_capital = sum(STARTING_CAPITAL.values())
    agg_pnl = sum(float(r[4]) for r in rows)
    print(f"  Total deployed capital:  ${total_capital:,.0f}")
    print(f"  Total P&L:               {fmt_pnl(agg_pnl)}")
    print(f"  Overall ROI:             {agg_pnl/total_capital*100:+.2f}%")


# ===================================================================
# P2: Win/Loss Size Asymmetry (the #1 known issue)
# ===================================================================
def p2_win_loss_asymmetry(conn):
    print("\n" + "=" * 80)
    print("P2: WIN/LOSS SIZE ASYMMETRY (Known #1 Issue)")
    print("=" * 80)
    print("  Audit noted: 'losses were $30 vs $9 avg win, need 77% WR to break even'")

    rows = run_query(conn, """
        SELECT
            ticker,
            COALESCE(AVG(realized_pnl) FILTER (WHERE realized_pnl > 0), 0) AS avg_win,
            COALESCE(AVG(realized_pnl) FILTER (WHERE realized_pnl < 0), 0) AS avg_loss,
            COALESCE(MAX(realized_pnl), 0) AS max_win,
            COALESCE(MIN(realized_pnl), 0) AS max_loss,
            COALESCE(STDDEV(realized_pnl) FILTER (WHERE realized_pnl > 0), 0) AS win_stddev,
            COALESCE(STDDEV(realized_pnl) FILTER (WHERE realized_pnl < 0), 0) AS loss_stddev,
            COUNT(*) FILTER (WHERE realized_pnl > 0) AS wins,
            COUNT(*) FILTER (WHERE realized_pnl < 0) AS losses
        FROM agape_spot_positions
        WHERE status IN ('closed', 'expired', 'stopped')
          AND realized_pnl IS NOT NULL
          AND account_label != 'paper'
        GROUP BY ticker
        ORDER BY ticker
    """)

    if rows:
        print(f"\n  {'Ticker':<12} {'Avg Win':>10} {'Avg Loss':>10} {'Ratio':>7} {'BrkEvn WR':>10} {'Max Win':>10} {'Max Loss':>10}")
        print(f"  {'-'*75}")
        for r in rows:
            ticker = r[0]
            avg_win, avg_loss = float(r[1]), float(r[2])
            max_win, max_loss = float(r[3]), float(r[4])
            wins, losses = r[7] or 0, r[8] or 0
            ratio = abs(avg_loss / avg_win) if avg_win > 0 else 999
            # Breakeven win rate = |avg_loss| / (avg_win + |avg_loss|)
            be_wr = abs(avg_loss) / (avg_win + abs(avg_loss)) * 100 if (avg_win + abs(avg_loss)) > 0 else 0
            flag = " !!!" if ratio > 2.0 else " !" if ratio > 1.5 else ""
            print(f"  {ticker:<12} {fmt_pnl(avg_win):>10} {fmt_pnl(avg_loss):>10} {ratio:>6.1f}x {be_wr:>8.0f}% {fmt_pnl(max_win):>10} {fmt_pnl(max_loss):>10}{flag}")

        # Overall
        agg = run_query(conn, """
            SELECT
                COALESCE(AVG(realized_pnl) FILTER (WHERE realized_pnl > 0), 0),
                COALESCE(AVG(realized_pnl) FILTER (WHERE realized_pnl < 0), 0)
            FROM agape_spot_positions
            WHERE status IN ('closed', 'expired', 'stopped')
              AND realized_pnl IS NOT NULL AND account_label != 'paper'
        """)
        if agg:
            avg_w, avg_l = float(agg[0][0]), float(agg[0][1])
            ratio = abs(avg_l / avg_w) if avg_w > 0 else 999
            be_wr = abs(avg_l) / (avg_w + abs(avg_l)) * 100 if (avg_w + abs(avg_l)) > 0 else 0
            print(f"  {'-'*75}")
            print(f"  {'OVERALL':<12} {fmt_pnl(avg_w):>10} {fmt_pnl(avg_l):>10} {ratio:>6.1f}x {be_wr:>8.0f}%")
            if ratio > 2.0:
                print(f"\n  CRITICAL: Average loss is {ratio:.1f}x average win.")
                print(f"  Need {be_wr:.0f}% win rate just to break even.")
    else:
        print("  No closed trades with P&L data")


# ===================================================================
# P3: P&L by Funding Regime
# ===================================================================
def p3_funding_regime(conn):
    print("\n" + "=" * 80)
    print("P3: P&L BY FUNDING REGIME")
    print("=" * 80)

    rows = run_query(conn, """
        SELECT
            ticker,
            COALESCE(funding_regime_at_entry, 'UNKNOWN') AS regime,
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE realized_pnl > 0) AS wins,
            COUNT(*) FILTER (WHERE realized_pnl < 0) AS losses,
            COALESCE(SUM(realized_pnl), 0) AS total_pnl,
            COALESCE(AVG(realized_pnl), 0) AS avg_pnl
        FROM agape_spot_positions
        WHERE status IN ('closed', 'expired', 'stopped')
          AND realized_pnl IS NOT NULL AND account_label != 'paper'
        GROUP BY ticker, COALESCE(funding_regime_at_entry, 'UNKNOWN')
        ORDER BY ticker, total DESC
    """)

    if rows:
        print(f"\n  {'Ticker':<12} {'Funding Regime':<25} {'Trades':>6} {'Wins':>5} {'WR%':>6} {'Total P&L':>12} {'Avg P&L':>10}")
        print(f"  {'-'*80}")
        current_ticker = None
        for r in rows:
            ticker, regime, total, wins, losses = r[0], r[1], r[2], r[3] or 0, r[4] or 0
            total_pnl, avg_pnl = float(r[5]), float(r[6])
            wr = wins / total * 100 if total > 0 else 0
            if ticker != current_ticker:
                if current_ticker:
                    print(f"  {'-'*80}")
                current_ticker = ticker
            print(f"  {ticker:<12} {regime:<25} {total:>6} {wins:>5} {wr:>5.1f}% {fmt_pnl(total_pnl):>12} {fmt_pnl(avg_pnl):>10}")
    else:
        print("  No data")


# ===================================================================
# P4: P&L by Close Reason
# ===================================================================
def p4_close_reason(conn):
    print("\n" + "=" * 80)
    print("P4: P&L BY CLOSE REASON")
    print("=" * 80)

    rows = run_query(conn, """
        SELECT
            COALESCE(close_reason, 'UNKNOWN') AS reason,
            ticker,
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE realized_pnl > 0) AS wins,
            COALESCE(SUM(realized_pnl), 0) AS total_pnl,
            COALESCE(AVG(realized_pnl), 0) AS avg_pnl
        FROM agape_spot_positions
        WHERE status IN ('closed', 'expired', 'stopped')
          AND realized_pnl IS NOT NULL AND account_label != 'paper'
        GROUP BY close_reason, ticker
        ORDER BY close_reason, ticker
    """)

    if rows:
        print(f"\n  {'Close Reason':<30} {'Ticker':<12} {'Trades':>6} {'Wins':>5} {'WR%':>6} {'Total P&L':>12} {'Avg P&L':>10}")
        print(f"  {'-'*85}")
        for r in rows:
            reason, ticker, total, wins = r[0], r[1], r[2], r[3] or 0
            total_pnl, avg_pnl = float(r[4]), float(r[5])
            wr = wins / total * 100 if total > 0 else 0
            print(f"  {reason:<30} {ticker:<12} {total:>6} {wins:>5} {wr:>5.1f}% {fmt_pnl(total_pnl):>12} {fmt_pnl(avg_pnl):>10}")

        # Aggregate by reason
        print(f"\n  AGGREGATE BY REASON:")
        print(f"  {'-'*70}")
        agg = run_query(conn, """
            SELECT
                COALESCE(close_reason, 'UNKNOWN'),
                COUNT(*),
                COUNT(*) FILTER (WHERE realized_pnl > 0),
                COALESCE(SUM(realized_pnl), 0),
                COALESCE(AVG(realized_pnl), 0)
            FROM agape_spot_positions
            WHERE status IN ('closed', 'expired', 'stopped')
              AND realized_pnl IS NOT NULL AND account_label != 'paper'
            GROUP BY close_reason ORDER BY COUNT(*) DESC
        """)
        for r in agg:
            reason, total, wins = r[0] or 'UNKNOWN', r[1], r[2] or 0
            total_pnl, avg_pnl = float(r[3]), float(r[4])
            wr = wins / total * 100 if total > 0 else 0
            print(f"  {reason:<30} {total:>6} trades  {wr:>5.1f}% WR  {fmt_pnl(total_pnl):>12} total  {fmt_pnl(avg_pnl):>10} avg")
    else:
        print("  No data")


# ===================================================================
# P5: Hold Duration vs Outcome
# ===================================================================
def p5_hold_duration(conn):
    print("\n" + "=" * 80)
    print("P5: HOLD DURATION VS OUTCOME")
    print("=" * 80)

    rows = run_query(conn, """
        SELECT
            ticker,
            CASE
                WHEN EXTRACT(EPOCH FROM (close_time - open_time)) / 60 < 15 THEN '<15min'
                WHEN EXTRACT(EPOCH FROM (close_time - open_time)) / 60 < 60 THEN '15-60min'
                WHEN EXTRACT(EPOCH FROM (close_time - open_time)) / 3600 < 2 THEN '1-2hr'
                WHEN EXTRACT(EPOCH FROM (close_time - open_time)) / 3600 < 4 THEN '2-4hr'
                WHEN EXTRACT(EPOCH FROM (close_time - open_time)) / 3600 < 8 THEN '4-8hr'
                ELSE '>8hr'
            END AS duration_bucket,
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE realized_pnl > 0) AS wins,
            COALESCE(SUM(realized_pnl), 0) AS total_pnl,
            COALESCE(AVG(realized_pnl), 0) AS avg_pnl,
            AVG(EXTRACT(EPOCH FROM (close_time - open_time)) / 60) AS avg_minutes
        FROM agape_spot_positions
        WHERE status IN ('closed', 'expired', 'stopped')
          AND realized_pnl IS NOT NULL AND account_label != 'paper'
          AND open_time IS NOT NULL AND close_time IS NOT NULL
        GROUP BY ticker, duration_bucket
        ORDER BY ticker, avg_minutes
    """)

    if rows:
        print(f"\n  {'Ticker':<12} {'Duration':<12} {'Trades':>6} {'WR%':>6} {'Total P&L':>12} {'Avg P&L':>10} {'Avg Min':>8}")
        print(f"  {'-'*72}")
        current = None
        for r in rows:
            ticker = r[0]
            if ticker != current:
                if current:
                    print(f"  {'-'*72}")
                current = ticker
            bucket, total, wins = r[1], r[2], r[3] or 0
            total_pnl, avg_pnl, avg_min = float(r[4]), float(r[5]), float(r[6] or 0)
            wr = wins / total * 100 if total > 0 else 0
            print(f"  {ticker:<12} {bucket:<12} {total:>6} {wr:>5.1f}% {fmt_pnl(total_pnl):>12} {fmt_pnl(avg_pnl):>10} {avg_min:>7.0f}m")
    else:
        print("  No data")


# ===================================================================
# P6: P&L by Hour of Day (UTC)
# ===================================================================
def p6_hour_of_day(conn):
    print("\n" + "=" * 80)
    print("P6: P&L BY HOUR OF DAY (CT)")
    print("=" * 80)

    rows = run_query(conn, """
        SELECT
            EXTRACT(HOUR FROM open_time AT TIME ZONE 'America/Chicago') AS hour_ct,
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE realized_pnl > 0) AS wins,
            COALESCE(SUM(realized_pnl), 0) AS total_pnl,
            COALESCE(AVG(realized_pnl), 0) AS avg_pnl
        FROM agape_spot_positions
        WHERE status IN ('closed', 'expired', 'stopped')
          AND realized_pnl IS NOT NULL AND account_label != 'paper'
          AND open_time IS NOT NULL
        GROUP BY hour_ct
        ORDER BY hour_ct
    """)

    if rows:
        print(f"\n  {'Hour (CT)':<12} {'Trades':>7} {'Wins':>6} {'WR%':>7} {'Total P&L':>12} {'Avg P&L':>10}")
        print(f"  {'-'*60}")
        for r in rows:
            hour, total, wins = int(r[0]), r[1], r[2] or 0
            total_pnl, avg_pnl = float(r[3]), float(r[4])
            wr = wins / total * 100 if total > 0 else 0
            bar = "+" * max(0, min(int(total_pnl / 2), 20)) if total_pnl > 0 else "-" * max(0, min(int(abs(total_pnl) / 2), 20))
            print(f"  {hour:>2}:00 CT    {total:>7} {wins:>6} {wr:>6.1f}% {fmt_pnl(total_pnl):>12} {fmt_pnl(avg_pnl):>10}  {bar}")
    else:
        print("  No data")


# ===================================================================
# P7: P&L by Day of Week
# ===================================================================
def p7_day_of_week(conn):
    print("\n" + "=" * 80)
    print("P7: P&L BY DAY OF WEEK")
    print("=" * 80)

    rows = run_query(conn, """
        SELECT
            EXTRACT(DOW FROM open_time AT TIME ZONE 'America/Chicago') AS dow,
            TO_CHAR(open_time AT TIME ZONE 'America/Chicago', 'Day') AS day_name,
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE realized_pnl > 0) AS wins,
            COUNT(*) FILTER (WHERE realized_pnl < 0) AS losses,
            COALESCE(SUM(realized_pnl), 0) AS total_pnl,
            COALESCE(AVG(realized_pnl), 0) AS avg_pnl
        FROM agape_spot_positions
        WHERE status IN ('closed', 'expired', 'stopped')
          AND realized_pnl IS NOT NULL AND account_label != 'paper'
        GROUP BY dow, day_name
        ORDER BY dow
    """)

    if rows:
        print(f"\n  {'Day':<12} {'Trades':>7} {'Wins':>6} {'Losses':>6} {'WR%':>7} {'Total P&L':>12} {'Avg P&L':>10}")
        print(f"  {'-'*65}")
        for r in rows:
            day = (r[1] or '').strip()
            total, wins, losses = r[2], r[3] or 0, r[4] or 0
            total_pnl, avg_pnl = float(r[5]), float(r[6])
            wr = wins / total * 100 if total > 0 else 0
            print(f"  {day:<12} {total:>7} {wins:>6} {losses:>6} {wr:>6.1f}% {fmt_pnl(total_pnl):>12} {fmt_pnl(avg_pnl):>10}")
    else:
        print("  No data")


# ===================================================================
# P8: Bayesian Win Tracker State
# ===================================================================
def p8_bayesian_tracker(conn):
    print("\n" + "=" * 80)
    print("P8: BAYESIAN WIN TRACKER STATE (per-ticker, per-regime)")
    print("=" * 80)

    rows = run_query(conn, """
        SELECT DISTINCT ON (ticker)
            ticker, alpha, beta, total_trades,
            positive_funding_wins, positive_funding_losses,
            negative_funding_wins, negative_funding_losses,
            neutral_funding_wins, neutral_funding_losses,
            COALESCE(ema_win, 0), COALESCE(ema_loss, 0),
            updated_at
        FROM agape_spot_win_tracker
        ORDER BY ticker, id DESC
    """)

    if rows:
        for r in rows:
            ticker = r[0]
            alpha, beta, total = float(r[1]), float(r[2]), int(r[3])
            win_prob = alpha / (alpha + beta) if (alpha + beta) > 0 else 0.5
            pf_w, pf_l = int(r[4]), int(r[5])
            nf_w, nf_l = int(r[6]), int(r[7])
            neut_w, neut_l = int(r[8]), int(r[9])
            ema_win, ema_loss = float(r[10]), float(r[11])
            updated = r[12]

            print(f"\n  {ticker}")
            print(f"  {'-'*50}")
            print(f"  Overall:  alpha={alpha:.1f}  beta={beta:.1f}  P(win)={win_prob:.3f}  trades={total}")
            print(f"  EWMA:     avg_win=${ema_win:.2f}  avg_loss=${ema_loss:.2f}  mag=${(ema_win+ema_loss)/2:.2f}")

            # Regime breakdown
            for regime, w, l in [("POSITIVE", pf_w, pf_l), ("NEGATIVE", nf_w, nf_l), ("NEUTRAL", neut_w, neut_l)]:
                regime_prob = (w + 1) / (w + l + 2)
                total_regime = w + l
                print(f"  {regime:<12} {w}W / {l}L  P(win)={regime_prob:.3f}  ({total_regime} trades)")

            if updated:
                print(f"  Last updated: {updated.strftime('%Y-%m-%d %H:%M')}")

            # Cold start warning
            if total < 10:
                print(f"  COLD START: Only {total} trades, probability floored at 0.52")
    else:
        print("  No win tracker data found")


# ===================================================================
# P9: Capital Allocator State
# ===================================================================
def p9_capital_allocator(conn):
    print("\n" + "=" * 80)
    print("P9: CAPITAL ALLOCATOR RANKINGS")
    print("=" * 80)

    # Compute the same metrics the allocator uses
    rows = run_query(conn, """
        SELECT
            ticker,
            COUNT(*) AS total_trades,
            COUNT(*) FILTER (WHERE realized_pnl > 0) AS wins,
            COALESCE(SUM(realized_pnl), 0) AS total_pnl,
            COALESCE(AVG(realized_pnl) FILTER (WHERE realized_pnl > 0), 0) AS avg_win,
            COALESCE(AVG(ABS(realized_pnl)) FILTER (WHERE realized_pnl < 0), 0) AS avg_loss,
            COALESCE(SUM(realized_pnl) FILTER (WHERE close_time > NOW() - INTERVAL '24 hours'), 0) AS recent_24h_pnl
        FROM agape_spot_positions
        WHERE status IN ('closed', 'expired', 'stopped')
          AND account_label != 'paper'
        GROUP BY ticker
        ORDER BY COALESCE(SUM(realized_pnl), 0) DESC
    """)

    if rows:
        print(f"\n  {'Ticker':<12} {'Trades':>7} {'WR%':>7} {'P&L':>12} {'Avg Win':>10} {'Avg Loss':>10} {'PF':>6} {'24h P&L':>10}")
        print(f"  {'-'*80}")
        for r in rows:
            ticker, total, wins = r[0], r[1], r[2] or 0
            losses = total - wins
            total_pnl = float(r[3])
            avg_win, avg_loss = float(r[4]), float(r[5])
            recent = float(r[6])
            wr = wins / total * 100 if total > 0 else 0
            pf = (avg_win * wins) / (avg_loss * losses) if (losses > 0 and avg_loss > 0) else (2.0 if wins > 0 else 0.0)
            print(f"  {ticker:<12} {total:>7} {wr:>6.1f}% {fmt_pnl(total_pnl):>12} {fmt_pnl(avg_win):>10} {fmt_pnl(-avg_loss):>10} {pf:>5.2f} {fmt_pnl(recent):>10}")
    else:
        print("  No data")


# ===================================================================
# P10: Scan Activity Breakdown
# ===================================================================
def p10_scan_activity(conn):
    print("\n" + "=" * 80)
    print("P10: SCAN ACTIVITY - WHY TRADES ARE SKIPPED (last 7 days)")
    print("=" * 80)

    rows = run_query(conn, """
        SELECT
            ticker,
            outcome,
            COUNT(*) AS count
        FROM agape_spot_scan_activity
        WHERE timestamp > NOW() - INTERVAL '7 days'
        GROUP BY ticker, outcome
        ORDER BY ticker, count DESC
    """)

    if rows:
        print(f"\n  {'Ticker':<12} {'Outcome':<30} {'Count':>8} {'%':>7}")
        print(f"  {'-'*60}")
        current = None
        ticker_total = {}
        for r in rows:
            ticker_total[r[0]] = ticker_total.get(r[0], 0) + r[2]
        for r in rows:
            ticker, outcome, count = r[0], r[1], r[2]
            if ticker != current:
                if current:
                    print(f"  {'-'*60}")
                current = ticker
            pct = count / ticker_total[ticker] * 100 if ticker_total[ticker] > 0 else 0
            print(f"  {ticker:<12} {outcome:<30} {count:>8} {pct:>6.1f}%")

        # Top skip reasons across all tickers
        print(f"\n  TOP SKIP REASONS (all tickers, 7 days):")
        print(f"  {'-'*65}")
        reasons = run_query(conn, """
            SELECT
                LEFT(COALESCE(signal_reasoning, outcome), 70) AS reason,
                COUNT(*) AS count
            FROM agape_spot_scan_activity
            WHERE outcome IN ('NO_TRADE', 'SKIPPED', 'WAIT', 'NO_SIGNAL')
              AND timestamp > NOW() - INTERVAL '7 days'
            GROUP BY LEFT(COALESCE(signal_reasoning, outcome), 70)
            ORDER BY count DESC
            LIMIT 15
        """)
        for r in reasons:
            print(f"  {r[1]:>6}x  {r[0]}")
    else:
        print("  No scan activity data (last 7 days)")


# ===================================================================
# P11: Alpha vs Buy-and-Hold
# ===================================================================
def p11_alpha_vs_buyhold(conn):
    print("\n" + "=" * 80)
    print("P11: ALPHA VS BUY-AND-HOLD")
    print("=" * 80)
    print("  Is the bot generating alpha or just riding crypto's trend?")

    # Get first recorded price and total P&L per ticker
    rows = run_query(conn, """
        WITH first_prices AS (
            SELECT DISTINCT ON (ticker)
                ticker, eth_price AS first_price, timestamp AS first_ts
            FROM agape_spot_equity_snapshots
            WHERE eth_price IS NOT NULL AND eth_price > 0
            ORDER BY ticker, timestamp ASC
        ),
        latest_prices AS (
            SELECT DISTINCT ON (ticker)
                ticker, eth_price AS current_price
            FROM agape_spot_equity_snapshots
            WHERE eth_price IS NOT NULL AND eth_price > 0
            ORDER BY ticker, timestamp DESC
        ),
        trade_pnl AS (
            SELECT
                ticker,
                COALESCE(SUM(realized_pnl), 0) AS total_pnl
            FROM agape_spot_positions
            WHERE status IN ('closed', 'expired', 'stopped')
              AND account_label != 'paper'
            GROUP BY ticker
        )
        SELECT
            fp.ticker,
            fp.first_price,
            lp.current_price,
            fp.first_ts,
            tp.total_pnl
        FROM first_prices fp
        JOIN latest_prices lp ON fp.ticker = lp.ticker
        LEFT JOIN trade_pnl tp ON fp.ticker = tp.ticker
        ORDER BY fp.ticker
    """)

    if rows:
        print(f"\n  {'Ticker':<12} {'1st Price':>10} {'Now':>10} {'B&H Return':>12} {'Trading P&L':>12} {'Alpha':>10} {'Since'}")
        print(f"  {'-'*85}")
        for r in rows:
            ticker = r[0]
            first_price, current_price = float(r[1]), float(r[2])
            first_ts = r[3]
            trading_pnl = float(r[4] or 0)
            capital = STARTING_CAPITAL.get(ticker, 1000)

            # Buy-and-hold: if invested capital at first_price, what would it be worth now?
            bh_units = capital / first_price if first_price > 0 else 0
            bh_value = bh_units * current_price
            bh_return = bh_value - capital
            bh_pct = bh_return / capital * 100 if capital > 0 else 0
            trade_pct = trading_pnl / capital * 100 if capital > 0 else 0
            alpha_pct = trade_pct - bh_pct

            flag = " (ALPHA)" if alpha_pct > 0 else " (BETA ONLY)" if alpha_pct < -5 else ""
            since = first_ts.strftime('%m/%d') if first_ts else "?"
            print(f"  {ticker:<12} ${first_price:>8,.2f} ${current_price:>8,.2f} {fmt_pnl(bh_return):>12} {fmt_pnl(trading_pnl):>12} {alpha_pct:>+8.1f}%{flag}  {since}")
    else:
        print("  No equity snapshot data for buy-and-hold comparison")


# ===================================================================
# P12: Fee & Slippage Impact
# ===================================================================
def p12_fees_slippage(conn):
    print("\n" + "=" * 80)
    print("P12: COINBASE FEE & SLIPPAGE IMPACT")
    print("=" * 80)

    rows = run_query(conn, """
        SELECT
            ticker,
            COUNT(*) AS trades,
            COALESCE(SUM(entry_fee_usd), 0) AS total_entry_fees,
            COALESCE(SUM(exit_fee_usd), 0) AS total_exit_fees,
            COALESCE(AVG(entry_slippage_pct), 0) AS avg_entry_slip,
            COALESCE(AVG(exit_slippage_pct), 0) AS avg_exit_slip,
            COALESCE(SUM(realized_pnl), 0) AS total_pnl,
            COUNT(*) FILTER (WHERE entry_fee_usd IS NOT NULL) AS has_fee_data
        FROM agape_spot_positions
        WHERE status IN ('closed', 'expired', 'stopped')
          AND account_label != 'paper'
        GROUP BY ticker
        ORDER BY ticker
    """)

    if rows:
        print(f"\n  {'Ticker':<12} {'Trades':>7} {'Entry Fees':>12} {'Exit Fees':>12} {'Total Fees':>12} {'Avg Slip%':>10} {'P&L':>12} {'Fee/PnL':>8}")
        print(f"  {'-'*85}")
        for r in rows:
            ticker, trades = r[0], r[1]
            entry_fees, exit_fees = float(r[2]), float(r[3])
            avg_entry_slip, avg_exit_slip = float(r[4]), float(r[5])
            total_pnl = float(r[6])
            has_data = r[7]
            total_fees = entry_fees + exit_fees
            avg_slip = (avg_entry_slip + avg_exit_slip) / 2
            fee_ratio = abs(total_fees / total_pnl * 100) if total_pnl != 0 else 0

            data_flag = "" if has_data > 0 else " (no fee data)"
            print(f"  {ticker:<12} {trades:>7} {fmt_pnl(-entry_fees):>12} {fmt_pnl(-exit_fees):>12} {fmt_pnl(-total_fees):>12} {avg_slip:>9.3f}% {fmt_pnl(total_pnl):>12} {fee_ratio:>6.1f}%{data_flag}")
    else:
        print("  No data")


# ===================================================================
# P13: Consecutive Loss Streaks
# ===================================================================
def p13_loss_streaks(conn):
    print("\n" + "=" * 80)
    print("P13: CONSECUTIVE LOSS STREAKS")
    print("=" * 80)

    for ticker in TICKERS:
        rows = run_query(conn, """
            SELECT realized_pnl, close_time
            FROM agape_spot_positions
            WHERE ticker = %s
              AND status IN ('closed', 'expired', 'stopped')
              AND realized_pnl IS NOT NULL
              AND account_label != 'paper'
            ORDER BY close_time ASC
        """, (ticker,))

        if not rows:
            continue

        # Find max consecutive losses
        max_streak = 0
        current_streak = 0
        streaks = []
        for r in rows:
            pnl = float(r[0])
            if pnl < 0:
                current_streak += 1
                max_streak = max(max_streak, current_streak)
            else:
                if current_streak >= 3:
                    streaks.append(current_streak)
                current_streak = 0

        if current_streak >= 3:
            streaks.append(current_streak)

        total_trades = len(rows)
        print(f"\n  {ticker}: {total_trades} trades | Max loss streak: {max_streak} | Streaks >= 3: {len(streaks)}")
        if streaks:
            print(f"    Streak lengths: {sorted(streaks, reverse=True)[:10]}")


# ===================================================================
# P14: Paper vs Live Comparison
# ===================================================================
def p14_paper_vs_live(conn):
    print("\n" + "=" * 80)
    print("P14: PAPER VS LIVE ACCOUNT COMPARISON")
    print("=" * 80)

    rows = run_query(conn, """
        SELECT
            account_label,
            ticker,
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE realized_pnl > 0) AS wins,
            COALESCE(SUM(realized_pnl), 0) AS total_pnl,
            COALESCE(AVG(realized_pnl), 0) AS avg_pnl
        FROM agape_spot_positions
        WHERE status IN ('closed', 'expired', 'stopped')
          AND realized_pnl IS NOT NULL
        GROUP BY account_label, ticker
        ORDER BY account_label, ticker
    """)

    if rows:
        print(f"\n  {'Account':<15} {'Ticker':<12} {'Trades':>7} {'WR%':>7} {'Total P&L':>12} {'Avg P&L':>10}")
        print(f"  {'-'*68}")
        current = None
        for r in rows:
            acct, ticker, total, wins = r[0], r[1], r[2], r[3] or 0
            total_pnl, avg_pnl = float(r[4]), float(r[5])
            wr = wins / total * 100 if total > 0 else 0
            if acct != current:
                if current:
                    print(f"  {'-'*68}")
                current = acct
            print(f"  {acct:<15} {ticker:<12} {total:>7} {wr:>6.1f}% {fmt_pnl(total_pnl):>12} {fmt_pnl(avg_pnl):>10}")
    else:
        print("  No data (or all trades on same account)")


# ===================================================================
# P15: Recent Trade Trend (last 30 per ticker)
# ===================================================================
def p15_recent_trend(conn):
    print("\n" + "=" * 80)
    print("P15: RECENT TRADE TREND (last 30 per ticker)")
    print("=" * 80)

    for ticker in TICKERS:
        rows = run_query(conn, """
            SELECT
                DATE(close_time AT TIME ZONE 'America/Chicago') AS trade_date,
                realized_pnl,
                close_reason,
                EXTRACT(EPOCH FROM (close_time - open_time)) / 60 AS hold_minutes
            FROM agape_spot_positions
            WHERE ticker = %s
              AND status IN ('closed', 'expired', 'stopped')
              AND realized_pnl IS NOT NULL
              AND account_label != 'paper'
            ORDER BY close_time DESC
            LIMIT 30
        """, (ticker,))

        if not rows:
            continue

        wins = sum(1 for r in rows if r[1] and float(r[1]) > 0)
        losses = sum(1 for r in rows if r[1] and float(r[1]) < 0)
        total_pnl = sum(float(r[1] or 0) for r in rows)
        count = len(rows)

        print(f"\n  {ticker}: Last {count} trades = {wins}W / {losses}L | {fmt_pnl(total_pnl)}")
        print(f"  {'Date':<12} {'P&L':>10} {'Running':>10} {'Reason':<25} {'Hold':>8}")
        print(f"  {'-'*70}")

        running = 0
        for r in reversed(rows):
            trade_date, pnl, reason, hold_min = r[0], float(r[1] or 0), r[2], float(r[3] or 0)
            running += pnl
            marker = "W" if pnl > 0 else "L" if pnl < 0 else "-"
            hold_str = f"{hold_min:.0f}m" if hold_min < 120 else f"{hold_min/60:.1f}h"
            print(f"  {str(trade_date):<12} {fmt_pnl(pnl):>10} {fmt_pnl(running):>10} {(reason or '?'):<25} {hold_str:>8} {marker}")


# ===================================================================
# P16: Orphaned Positions Check
# ===================================================================
def p16_orphaned_positions(conn):
    print("\n" + "=" * 80)
    print("P16: ORPHANED / STUCK POSITIONS CHECK")
    print("=" * 80)

    # Open positions older than 24h (crypto shouldn't hold this long)
    rows = run_query(conn, """
        SELECT
            position_id, ticker, entry_price, quantity,
            open_time,
            EXTRACT(EPOCH FROM (NOW() - open_time)) / 3600 AS hours_open,
            account_label,
            sell_fail_count
        FROM agape_spot_positions
        WHERE status = 'open'
        ORDER BY open_time ASC
    """)

    if rows:
        print(f"\n  Found {len(rows)} open position(s):")
        print(f"  {'Position ID':<30} {'Ticker':<12} {'Hours':>7} {'Account':<12} {'Fail#':>6} {'Entry':>10}")
        print(f"  {'-'*80}")
        for r in rows:
            pos_id, ticker, entry, qty = r[0], r[1], float(r[2]), float(r[3])
            hours = float(r[5])
            acct = r[6]
            fail_count = r[7] or 0
            flag = " STUCK!" if hours > 24 else " LONG" if hours > 8 else ""
            fail_flag = f" (SELL FAILED x{fail_count})" if fail_count > 0 else ""
            print(f"  {pos_id:<30} {ticker:<12} {hours:>6.1f}h {acct:<12} {fail_count:>6} ${entry:>8,.2f}{flag}{fail_flag}")
    else:
        print("  No open positions (all clear)")

    # Closed positions with NULL P&L
    null_rows = run_query(conn, """
        SELECT ticker, COUNT(*), MIN(open_time), MAX(close_time)
        FROM agape_spot_positions
        WHERE status IN ('closed', 'expired', 'stopped')
          AND realized_pnl IS NULL
        GROUP BY ticker
    """)
    if null_rows:
        print(f"\n  POSITIONS WITH NULL P&L (data integrity issue):")
        for r in null_rows:
            print(f"    {r[0]}: {r[1]} trades (from {r[2]} to {r[3]})")


# ===================================================================
# P17: Choppy EV Gate Effectiveness
# ===================================================================
def p17_ev_gate(conn):
    print("\n" + "=" * 80)
    print("P17: EV GATE EFFECTIVENESS (choppy market filter)")
    print("=" * 80)
    print("  Audit noted: 'C beat no gate (A): +$87.66 P&L, -284 trades'")

    # Compare trades that went through choppy conditions vs not
    rows = run_query(conn, """
        SELECT
            ticker,
            funding_regime_at_entry,
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE realized_pnl > 0) AS wins,
            COALESCE(SUM(realized_pnl), 0) AS total_pnl,
            COALESCE(AVG(realized_pnl), 0) AS avg_pnl
        FROM agape_spot_positions
        WHERE status IN ('closed', 'expired', 'stopped')
          AND realized_pnl IS NOT NULL AND account_label != 'paper'
        GROUP BY ticker, funding_regime_at_entry
        ORDER BY ticker, total DESC
    """)

    if rows:
        # Group choppy regimes (BALANCED, MILD_*) vs conviction (EXTREME_*, HEAVILY_*)
        choppy_regimes = {'BALANCED', 'MILD_LONG_BIAS', 'MILD_SHORT_BIAS', 'NEUTRAL', 'UNKNOWN', None}

        print(f"\n  CHOPPY vs CONVICTION REGIME PERFORMANCE:")
        print(f"  {'-'*75}")

        ticker_data = {}
        for r in rows:
            ticker = r[0]
            regime = r[1] or 'UNKNOWN'
            if ticker not in ticker_data:
                ticker_data[ticker] = {'choppy': {'trades': 0, 'wins': 0, 'pnl': 0},
                                       'conviction': {'trades': 0, 'wins': 0, 'pnl': 0}}
            bucket = 'choppy' if regime in choppy_regimes else 'conviction'
            ticker_data[ticker][bucket]['trades'] += r[2]
            ticker_data[ticker][bucket]['wins'] += r[3] or 0
            ticker_data[ticker][bucket]['pnl'] += float(r[4])

        print(f"  {'Ticker':<12} {'Type':<12} {'Trades':>7} {'WR%':>7} {'Total P&L':>12} {'Avg P&L':>10}")
        print(f"  {'-'*65}")
        for ticker in sorted(ticker_data.keys()):
            for bucket_name in ['conviction', 'choppy']:
                d = ticker_data[ticker][bucket_name]
                if d['trades'] == 0:
                    continue
                wr = d['wins'] / d['trades'] * 100 if d['trades'] > 0 else 0
                avg = d['pnl'] / d['trades']
                print(f"  {ticker:<12} {bucket_name:<12} {d['trades']:>7} {wr:>6.1f}% {fmt_pnl(d['pnl']):>12} {fmt_pnl(avg):>10}")
            print(f"  {'-'*65}")
    else:
        print("  No data")


# ===================================================================
# MAIN
# ===================================================================
def main():
    print("=" * 80)
    print("  AGAPE-SPOT COMPREHENSIVE PROFITABILITY ANALYSIS")
    print(f"  Generated: {datetime.now(CENTRAL_TZ).strftime('%Y-%m-%d %H:%M:%S CT')}")
    print("=" * 80)

    conn = get_db_connection()

    # Quick table existence check
    rows = run_query(conn, """
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_name = 'agape_spot_positions'
        )
    """)
    if not rows or not rows[0][0]:
        print("\nERROR: agape_spot_positions table does not exist!")
        conn.close()
        sys.exit(1)

    # Run count check
    count = run_query(conn, "SELECT COUNT(*) FROM agape_spot_positions")[0][0]
    print(f"\n  Total rows in agape_spot_positions: {count}")

    if count == 0:
        print("  No trades found. AGAPE-SPOT has not executed any trades yet.")
        conn.close()
        return

    # Run all profitability queries
    p1_overall_summary(conn)
    p2_win_loss_asymmetry(conn)
    p3_funding_regime(conn)
    p4_close_reason(conn)
    p5_hold_duration(conn)
    p6_hour_of_day(conn)
    p7_day_of_week(conn)
    p8_bayesian_tracker(conn)
    p9_capital_allocator(conn)
    p10_scan_activity(conn)
    p11_alpha_vs_buyhold(conn)
    p12_fees_slippage(conn)
    p13_loss_streaks(conn)
    p14_paper_vs_live(conn)
    p15_recent_trend(conn)
    p16_orphaned_positions(conn)
    p17_ev_gate(conn)

    conn.close()

    print("\n" + "=" * 80)
    print("  ANALYSIS COMPLETE")
    print("  To re-run: python scripts/analyze_agape_spot_profitability.py")
    print("=" * 80)


if __name__ == "__main__":
    main()
