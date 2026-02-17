#!/usr/bin/env python3
"""
AGAPE-SPOT PRODUCTION HEALTH CHECK
====================================
Run on Render shell to verify bots are trading correctly.

Usage:
  python scripts/agape_spot_health_check.py          # Full check
  python scripts/agape_spot_health_check.py --quick   # Last 1h only

What it checks:
  1. BALANCE  — Live Coinbase USD balance per account (are we reading it?)
  2. SIZING   — Are trades using full balance or still tiny $2-5 orders?
  3. SCANS    — Is the bot scanning? How often? What outcomes?
  4. TRADES   — Recent trades: sizes, P&L, win rate
  5. POSITIONS — Open positions, stuck/orphaned, sell failures
  6. COMPOUND — Is balance growing with profits?
  7. FEES     — Are entry/exit fees being tracked?
  8. STREAKS  — Loss streaks per ticker (risk check)
  9. BAYESIAN — Win tracker state per ticker
  10. OVERALL  — GO / WATCH / STOP verdict per ticker
"""

import os
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CT = ZoneInfo("America/Chicago")
UTC = ZoneInfo("UTC")

# Fix cutoff for post-fix analysis
FIX_CUTOFF = "2026-02-15 20:00:00+00"

TICKERS = ["ETH-USD", "BTC-USD", "XRP-USD", "SHIB-USD", "DOGE-USD", "MSTU-USD"]
LIVE_ACCOUNTS = ["default", "dedicated"]


def get_conn():
    import psycopg2
    url = os.environ.get("DATABASE_URL")
    if not url:
        env_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"
        )
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("DATABASE_URL=") and not line.startswith("#"):
                        url = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break
    if not url:
        print("ERROR: DATABASE_URL not set. Run on Render or set in .env")
        sys.exit(1)
    return psycopg2.connect(url)


def q(conn, sql, params=None):
    """Execute query, return list of dicts."""
    with conn.cursor() as cur:
        cur.execute(sql, params or ())
        if cur.description is None:
            return []
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def pct(num, denom):
    if not denom:
        return 0.0
    return round(num / denom * 100, 1)


def fmt_usd(val):
    if val is None:
        return "N/A"
    return f"${val:,.2f}" if val >= 0 else f"-${abs(val):,.2f}"


def hdr(title):
    w = 70
    print(f"\n{'=' * w}")
    print(f"  {title}")
    print(f"{'=' * w}")


def sub(title):
    print(f"\n  --- {title} ---")


# =========================================================================
# CHECKS
# =========================================================================

def check_1_recent_balance_logs(conn, lookback_hours):
    """Check if the bot is reading Coinbase balances and what values it sees."""
    hdr("1. BALANCE READING")

    rows = q(conn, """
        SELECT
            timestamp AT TIME ZONE 'America/Chicago' AS ts,
            ticker,
            action,
            message,
            details
        FROM agape_spot_activity_log
        WHERE action IN ('FULL_BALANCE_SIZED', 'NO_USD_BALANCE',
                         'BELOW_MIN_NOTIONAL', 'NO_COINBASE_CLIENT')
          AND timestamp > NOW() - INTERVAL '%s hours'
        ORDER BY timestamp DESC
        LIMIT 30
    """, (lookback_hours,))

    if not rows:
        print(f"  WARNING: No balance log entries in the last {lookback_hours}h.")
        print("  The bot may not be running, or the sizing code path isn't reached.")
        print("  Look for AGAPE-SPOT BALANCE: lines in Render logs.")
        return

    # Group by action
    actions = {}
    for r in rows:
        a = r["action"]
        actions.setdefault(a, []).append(r)

    sized = actions.get("FULL_BALANCE_SIZED", [])
    no_bal = actions.get("NO_USD_BALANCE", [])
    below_min = actions.get("BELOW_MIN_NOTIONAL", [])

    print(f"  Last {lookback_hours}h balance events:")
    print(f"    Sized from balance:  {len(sized)}")
    print(f"    $0 balance (skip):   {len(no_bal)}")
    print(f"    Below minimum:       {len(below_min)}")

    if sized:
        print(f"\n  Most recent balance reads:")
        for r in sized[:10]:
            print(f"    {r['ts']:%H:%M} | {r['ticker']:10s} | {r['message']}")

    if no_bal:
        print(f"\n  WARNING: {len(no_bal)} trades skipped due to $0 balance:")
        for r in no_bal[:5]:
            print(f"    {r['ts']:%H:%M} | {r['ticker']:10s} | {r['message']}")


def check_2_trade_sizing(conn, lookback_hours):
    """Are trades using full balance or still tiny?"""
    hdr("2. TRADE SIZING (post-fix)")

    rows = q(conn, """
        SELECT
            ticker,
            account_label,
            entry_price,
            quantity,
            quantity * entry_price AS notional_usd,
            open_time AT TIME ZONE 'America/Chicago' AS ts
        FROM agape_spot_positions
        WHERE open_time > NOW() - INTERVAL '%s hours'
          AND account_label IN ('default', 'dedicated')
        ORDER BY open_time DESC
        LIMIT 30
    """, (lookback_hours,))

    if not rows:
        print(f"  No live trades in the last {lookback_hours}h.")
        return

    print(f"  Recent {len(rows)} live trades:")
    print(f"  {'Time':>8} | {'Ticker':10s} | {'Account':10s} | {'Notional':>10} | {'Qty':>12} | {'Price':>10}")
    print(f"  {'-'*8} | {'-'*10} | {'-'*10} | {'-'*10} | {'-'*12} | {'-'*10}")

    total_notional = 0
    for r in rows:
        notional = r["notional_usd"] or 0
        total_notional += notional
        print(
            f"  {r['ts']:%H:%M:%S} | {r['ticker']:10s} | {r['account_label']:10s} | "
            f"{fmt_usd(notional):>10} | {r['quantity']:>12.4f} | {fmt_usd(r['entry_price']):>10}"
        )

    avg = total_notional / len(rows)
    print(f"\n  Avg trade size: {fmt_usd(avg)}")
    if avg < 10:
        print("  PROBLEM: Trades still tiny (<$10). Balance reading may be broken.")
    elif avg < 50:
        print("  WARNING: Trades small (<$50). Check Coinbase USD balance.")
    else:
        print(f"  OK: Avg ${avg:.0f} per trade — balance is being used.")


def check_3_scan_activity(conn, lookback_hours):
    """Is the bot scanning? What outcomes?"""
    hdr("3. SCAN ACTIVITY")

    rows = q(conn, """
        SELECT
            ticker,
            outcome,
            COUNT(*) AS cnt
        FROM agape_spot_scan_activity
        WHERE timestamp > NOW() - INTERVAL '%s hours'
        GROUP BY ticker, outcome
        ORDER BY ticker, cnt DESC
    """, (lookback_hours,))

    if not rows:
        print(f"  WARNING: No scans in the last {lookback_hours}h. Bot may be down.")
        return

    # Total scans
    total = sum(r["cnt"] for r in rows)
    trades = sum(r["cnt"] for r in rows if r["outcome"] == "TRADE")
    print(f"  Total scans: {total} | Trades: {trades} | Trade rate: {pct(trades, total)}%")

    # Per-ticker breakdown
    by_ticker = {}
    for r in rows:
        by_ticker.setdefault(r["ticker"], []).append(r)

    print(f"\n  {'Ticker':10s} | {'Scans':>6} | {'Trades':>6} | {'Rate':>5} | Top Skip Reason")
    print(f"  {'-'*10} | {'-'*6} | {'-'*6} | {'-'*5} | {'-'*30}")

    for ticker in TICKERS:
        outcomes = by_ticker.get(ticker, [])
        if not outcomes:
            print(f"  {ticker:10s} | {'0':>6} |    --- |   --- | (no scans)")
            continue
        t_total = sum(o["cnt"] for o in outcomes)
        t_trades = sum(o["cnt"] for o in outcomes if o["outcome"] == "TRADE")
        # Top skip reason
        skips = [o for o in outcomes if o["outcome"] != "TRADE"]
        top_skip = max(skips, key=lambda x: x["cnt"])["outcome"] if skips else "-"
        print(
            f"  {ticker:10s} | {t_total:>6} | {t_trades:>6} | {pct(t_trades, t_total):>4.1f}% | {top_skip}"
        )

    # Last scan time (is bot alive?)
    last = q(conn, """
        SELECT MAX(timestamp AT TIME ZONE 'America/Chicago') AS last_scan
        FROM agape_spot_scan_activity
    """)
    if last and last[0]["last_scan"]:
        ago = datetime.now(CT) - last[0]["last_scan"].replace(tzinfo=CT)
        mins = ago.total_seconds() / 60
        print(f"\n  Last scan: {last[0]['last_scan']:%Y-%m-%d %H:%M CT} ({mins:.0f} min ago)")
        if mins > 10:
            print("  WARNING: Last scan >10 min ago. Bot may be stopped or stuck.")


def check_4_recent_pnl(conn, lookback_hours):
    """Recent closed trades with P&L."""
    hdr("4. RECENT TRADES & P&L")

    # Per-ticker summary
    rows = q(conn, """
        SELECT
            ticker,
            account_label,
            COUNT(*) AS trades,
            COUNT(*) FILTER (WHERE realized_pnl > 0) AS wins,
            COUNT(*) FILTER (WHERE realized_pnl < 0) AS losses,
            COUNT(*) FILTER (WHERE realized_pnl = 0) AS breakeven,
            COALESCE(SUM(realized_pnl), 0) AS total_pnl,
            COALESCE(AVG(realized_pnl) FILTER (WHERE realized_pnl > 0), 0) AS avg_win,
            COALESCE(AVG(realized_pnl) FILTER (WHERE realized_pnl < 0), 0) AS avg_loss,
            COALESCE(AVG(quantity * entry_price), 0) AS avg_notional,
            MAX(close_time AT TIME ZONE 'America/Chicago') AS last_close
        FROM agape_spot_positions
        WHERE status IN ('closed', 'expired', 'stopped')
          AND close_time > NOW() - INTERVAL '%s hours'
          AND account_label IN ('default', 'dedicated')
        GROUP BY ticker, account_label
        ORDER BY ticker, account_label
    """, (lookback_hours,))

    if not rows:
        print(f"  No closed trades in the last {lookback_hours}h.")
        return

    print(f"  {'Ticker':10s} | {'Acct':10s} | {'Trades':>6} | {'WR':>5} | {'P&L':>10} | {'AvgWin':>8} | {'AvgLoss':>8} | {'AvgSize':>8}")
    print(f"  {'-'*10} | {'-'*10} | {'-'*6} | {'-'*5} | {'-'*10} | {'-'*8} | {'-'*8} | {'-'*8}")

    for r in rows:
        wr = pct(r["wins"], r["trades"])
        print(
            f"  {r['ticker']:10s} | {r['account_label']:10s} | {r['trades']:>6} | "
            f"{wr:>4.1f}% | {fmt_usd(r['total_pnl']):>10} | "
            f"{fmt_usd(r['avg_win']):>8} | {fmt_usd(r['avg_loss']):>8} | "
            f"{fmt_usd(r['avg_notional']):>8}"
        )

    # Last 10 trades
    sub("Last 10 closed trades")
    recent = q(conn, """
        SELECT
            ticker, account_label, realized_pnl, close_reason,
            quantity * entry_price AS notional,
            close_time AT TIME ZONE 'America/Chicago' AS ts
        FROM agape_spot_positions
        WHERE status IN ('closed', 'expired', 'stopped')
          AND account_label IN ('default', 'dedicated')
          AND realized_pnl IS NOT NULL
        ORDER BY close_time DESC
        LIMIT 10
    """)

    for r in recent:
        icon = "+" if (r["realized_pnl"] or 0) >= 0 else "-"
        print(
            f"  {icon} {r['ts']:%m/%d %H:%M} | {r['ticker']:10s} | {r['account_label']:10s} | "
            f"{fmt_usd(r['realized_pnl']):>10} | {fmt_usd(r['notional']):>8} | {r['close_reason'] or '?'}"
        )


def check_5_open_positions(conn):
    """Open positions — stuck or healthy?"""
    hdr("5. OPEN POSITIONS")

    rows = q(conn, """
        SELECT
            position_id,
            ticker,
            account_label,
            quantity,
            entry_price,
            quantity * entry_price AS notional,
            sell_fail_count,
            open_time AT TIME ZONE 'America/Chicago' AS ts,
            EXTRACT(EPOCH FROM (NOW() - open_time)) / 3600 AS hours_open
        FROM agape_spot_positions
        WHERE status = 'open'
        ORDER BY open_time ASC
    """)

    if not rows:
        print("  No open positions. All capital is in USD (ready for next trade).")
        return

    print(f"  {len(rows)} open positions:")
    print(f"  {'Ticker':10s} | {'Account':10s} | {'Notional':>10} | {'Open':>6} h | {'SellFails':>9} | {'Status'}")
    print(f"  {'-'*10} | {'-'*10} | {'-'*10} | {'-'*8} | {'-'*9} | {'-'*15}")

    for r in rows:
        hours = r["hours_open"] or 0
        fails = r["sell_fail_count"] or 0
        # Status assessment
        if fails > 3:
            status = "STUCK (sell failing)"
        elif hours > 24:
            status = "ORPHANED (>24h)"
        elif hours > 12:
            status = "STALE (>12h)"
        else:
            status = "OK"
        print(
            f"  {r['ticker']:10s} | {r['account_label']:10s} | {fmt_usd(r['notional']):>10} | "
            f"{hours:>6.1f} h | {fails:>9} | {status}"
        )

    # Orphan warning
    orphans = [r for r in rows if (r["hours_open"] or 0) > 24]
    if orphans:
        print(f"\n  WARNING: {len(orphans)} positions open >24h. These may be orphaned.")
        print("  Capital is locked in these positions. Check Coinbase portfolio.")


def check_6_compounding(conn):
    """Is P&L compounding? Compare trade sizes over time."""
    hdr("6. COMPOUNDING CHECK")

    # Compare average trade size: first 3 days vs last 3 days (post-fix)
    rows = q(conn, """
        WITH post_fix AS (
            SELECT
                ticker,
                account_label,
                quantity * entry_price AS notional,
                open_time,
                ROW_NUMBER() OVER (PARTITION BY ticker, account_label ORDER BY open_time ASC) AS rn_asc,
                ROW_NUMBER() OVER (PARTITION BY ticker, account_label ORDER BY open_time DESC) AS rn_desc
            FROM agape_spot_positions
            WHERE open_time > %s::timestamptz
              AND account_label IN ('default', 'dedicated')
        )
        SELECT
            ticker,
            account_label,
            COALESCE(AVG(notional) FILTER (WHERE rn_asc <= 5), 0) AS first_5_avg,
            COALESCE(AVG(notional) FILTER (WHERE rn_desc <= 5), 0) AS last_5_avg,
            COUNT(*) AS total_trades
        FROM post_fix
        GROUP BY ticker, account_label
        HAVING COUNT(*) >= 3
        ORDER BY ticker, account_label
    """, (FIX_CUTOFF,))

    if not rows:
        print("  Not enough post-fix trades to measure compounding yet.")
        return

    print(f"  {'Ticker':10s} | {'Account':10s} | {'First5 Avg':>10} | {'Last5 Avg':>10} | {'Change':>8} | {'Trades':>6}")
    print(f"  {'-'*10} | {'-'*10} | {'-'*10} | {'-'*10} | {'-'*8} | {'-'*6}")

    for r in rows:
        first_avg = r["first_5_avg"]
        last_avg = r["last_5_avg"]
        if first_avg > 0:
            change = ((last_avg - first_avg) / first_avg) * 100
            change_str = f"{change:+.1f}%"
        else:
            change_str = "N/A"
        print(
            f"  {r['ticker']:10s} | {r['account_label']:10s} | "
            f"{fmt_usd(first_avg):>10} | {fmt_usd(last_avg):>10} | "
            f"{change_str:>8} | {r['total_trades']:>6}"
        )

    print("\n  Positive % = trades getting bigger (compounding working).")
    print("  Negative % = trades shrinking (losing money or balance not read).")


def check_7_fee_tracking(conn, lookback_hours):
    """Are Coinbase fees being recorded?"""
    hdr("7. FEE TRACKING")

    rows = q(conn, """
        SELECT
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE entry_fee_usd IS NOT NULL AND entry_fee_usd > 0) AS has_entry_fee,
            COUNT(*) FILTER (WHERE exit_fee_usd IS NOT NULL AND exit_fee_usd > 0) AS has_exit_fee,
            COALESCE(SUM(entry_fee_usd), 0) AS total_entry_fees,
            COALESCE(SUM(exit_fee_usd), 0) AS total_exit_fees,
            COALESCE(SUM(realized_pnl), 0) AS total_pnl
        FROM agape_spot_positions
        WHERE status IN ('closed', 'expired', 'stopped')
          AND account_label IN ('default', 'dedicated')
          AND close_time > NOW() - INTERVAL '%s hours'
    """, (lookback_hours,))

    if not rows or rows[0]["total"] == 0:
        print(f"  No closed trades in the last {lookback_hours}h to check fees.")
        return

    r = rows[0]
    entry_pct = pct(r["has_entry_fee"], r["total"])
    exit_pct = pct(r["has_exit_fee"], r["total"])

    print(f"  Trades with entry fee data: {r['has_entry_fee']}/{r['total']} ({entry_pct}%)")
    print(f"  Trades with exit fee data:  {r['has_exit_fee']}/{r['total']} ({exit_pct}%)")
    print(f"  Total entry fees:  {fmt_usd(r['total_entry_fees'])}")
    print(f"  Total exit fees:   {fmt_usd(r['total_exit_fees'])}")
    print(f"  Total P&L:         {fmt_usd(r['total_pnl'])}")

    total_fees = (r["total_entry_fees"] or 0) + (r["total_exit_fees"] or 0)
    if r["total_pnl"] and r["total_pnl"] > 0:
        fee_ratio = total_fees / r["total_pnl"] * 100 if r["total_pnl"] else 0
        print(f"  Fees as % of P&L:  {fee_ratio:.1f}%")

    if entry_pct < 50:
        print("  WARNING: <50% of trades have fee data. Real P&L is lower than reported.")


def check_8_loss_streaks(conn, lookback_hours):
    """Current loss streak per ticker (risk check)."""
    hdr("8. LOSS STREAKS")

    for ticker in TICKERS:
        trades = q(conn, """
            SELECT realized_pnl
            FROM agape_spot_positions
            WHERE ticker = %s
              AND status IN ('closed', 'expired', 'stopped')
              AND account_label IN ('default', 'dedicated')
              AND realized_pnl IS NOT NULL
            ORDER BY close_time DESC
            LIMIT 50
        """, (ticker,))

        if not trades:
            continue

        # Current streak (from most recent trade backwards)
        current_streak = 0
        for t in trades:
            if t["realized_pnl"] < 0:
                current_streak += 1
            else:
                break

        # Max streak in last 50
        max_streak = 0
        streak = 0
        for t in trades:
            if t["realized_pnl"] < 0:
                streak += 1
                max_streak = max(max_streak, streak)
            else:
                streak = 0

        icon = "!!" if current_streak >= 5 else "!" if current_streak >= 3 else " "
        print(
            f"  {icon} {ticker:10s} | Current streak: {current_streak:>2} losses | "
            f"Max (last 50): {max_streak:>2}"
        )

    print("\n  !! = 5+ consecutive losses (consider pausing)")
    print("  !  = 3+ consecutive losses (watching)")


def check_9_bayesian_state(conn):
    """Bayesian win tracker: are probabilities reasonable?"""
    hdr("9. BAYESIAN WIN TRACKER")

    rows = q(conn, """
        SELECT
            ticker,
            total_trades,
            alpha,
            beta,
            CASE WHEN (alpha + beta) > 0
                 THEN ROUND(alpha::numeric / (alpha + beta)::numeric, 4)
                 ELSE 0 END AS win_prob,
            positive_funding_wins + positive_funding_losses AS pos_trades,
            negative_funding_wins + negative_funding_losses AS neg_trades,
            neutral_funding_wins + neutral_funding_losses AS neut_trades,
            updated_at AT TIME ZONE 'America/Chicago' AS updated
        FROM agape_spot_win_tracker
        ORDER BY ticker
    """)

    if not rows:
        print("  No Bayesian tracker data. Bot hasn't completed trades yet.")
        return

    print(f"  {'Ticker':10s} | {'Trades':>6} | {'WinProb':>7} | {'PosF':>5} | {'NegF':>5} | {'NeuF':>5} | {'Updated'}")
    print(f"  {'-'*10} | {'-'*6} | {'-'*7} | {'-'*5} | {'-'*5} | {'-'*5} | {'-'*20}")

    for r in rows:
        prob = float(r["win_prob"]) * 100
        status = ""
        if r["total_trades"] < 10:
            status = " (cold start)"
        elif prob < 50:
            status = " (negative EV!)"
        print(
            f"  {r['ticker']:10s} | {r['total_trades']:>6} | {prob:>5.1f}%{status:15s} | "
            f"{r['pos_trades'] or 0:>5} | {r['neg_trades'] or 0:>5} | "
            f"{r['neut_trades'] or 0:>5} | {r['updated']}"
        )


def check_10_account_pnl(conn):
    """Per-account cumulative P&L (are both accounts profitable?)."""
    hdr("10. ACCOUNT P&L (all-time live)")

    rows = q(conn, """
        SELECT
            account_label,
            COUNT(*) AS trades,
            COUNT(*) FILTER (WHERE realized_pnl > 0) AS wins,
            COALESCE(SUM(realized_pnl), 0) AS total_pnl,
            COALESCE(AVG(quantity * entry_price), 0) AS avg_notional,
            MIN(open_time AT TIME ZONE 'America/Chicago') AS first_trade,
            MAX(close_time AT TIME ZONE 'America/Chicago') AS last_trade
        FROM agape_spot_positions
        WHERE status IN ('closed', 'expired', 'stopped')
          AND account_label IN ('default', 'dedicated')
          AND realized_pnl IS NOT NULL
        GROUP BY account_label
        ORDER BY account_label
    """)

    if not rows:
        print("  No closed live trades in either account.")
        return

    for r in rows:
        wr = pct(r["wins"], r["trades"])
        print(f"\n  Account: {r['account_label'].upper()}")
        print(f"    Trades:        {r['trades']}")
        print(f"    Win Rate:      {wr}%")
        print(f"    Total P&L:     {fmt_usd(r['total_pnl'])}")
        print(f"    Avg Trade Size:{fmt_usd(r['avg_notional'])}")
        print(f"    First Trade:   {r['first_trade']}")
        print(f"    Last Trade:    {r['last_trade']}")

    # Post-fix comparison
    sub("Post-Fix P&L (after Feb 15 20:00 UTC)")
    post = q(conn, """
        SELECT
            account_label,
            COUNT(*) AS trades,
            COUNT(*) FILTER (WHERE realized_pnl > 0) AS wins,
            COALESCE(SUM(realized_pnl), 0) AS total_pnl,
            COALESCE(AVG(quantity * entry_price), 0) AS avg_notional
        FROM agape_spot_positions
        WHERE status IN ('closed', 'expired', 'stopped')
          AND account_label IN ('default', 'dedicated')
          AND realized_pnl IS NOT NULL
          AND close_time > %s::timestamptz
        GROUP BY account_label
        ORDER BY account_label
    """, (FIX_CUTOFF,))

    if not post:
        print("  No post-fix trades yet.")
    else:
        for r in post:
            wr = pct(r["wins"], r["trades"])
            print(
                f"  {r['account_label']:10s} | {r['trades']:>4} trades | "
                f"WR {wr:>5.1f}% | P&L {fmt_usd(r['total_pnl']):>10} | "
                f"Avg size {fmt_usd(r['avg_notional'])}"
            )


def check_11_verdict(conn, lookback_hours):
    """GO / WATCH / STOP per ticker."""
    hdr("11. VERDICT PER TICKER")

    for ticker in TICKERS:
        r = q(conn, """
            SELECT
                COUNT(*) AS trades,
                COUNT(*) FILTER (WHERE realized_pnl > 0) AS wins,
                COUNT(*) FILTER (WHERE realized_pnl < 0) AS losses,
                COALESCE(SUM(realized_pnl), 0) AS total_pnl,
                COALESCE(AVG(realized_pnl) FILTER (WHERE realized_pnl > 0), 0) AS avg_win,
                COALESCE(AVG(realized_pnl) FILTER (WHERE realized_pnl < 0), 0) AS avg_loss,
                COALESCE(AVG(quantity * entry_price), 0) AS avg_notional
            FROM agape_spot_positions
            WHERE ticker = %s
              AND status IN ('closed', 'expired', 'stopped')
              AND account_label IN ('default', 'dedicated')
              AND realized_pnl IS NOT NULL
              AND close_time > NOW() - INTERVAL '%s hours'
        """, (ticker, lookback_hours))

        if not r or r[0]["trades"] == 0:
            print(f"  {ticker:10s} | --- (no trades in {lookback_hours}h)")
            continue

        r = r[0]
        wr = pct(r["wins"], r["trades"])
        avg_win = r["avg_win"] or 0
        avg_loss = abs(r["avg_loss"] or 0)

        # EV per trade
        if r["trades"] > 0:
            ev = r["total_pnl"] / r["trades"]
        else:
            ev = 0

        # Breakeven WR needed
        if avg_win + avg_loss > 0:
            be_wr = avg_loss / (avg_win + avg_loss) * 100
        else:
            be_wr = 50

        # Verdict
        issues = []
        if ev < 0:
            issues.append("negative EV")
        if wr < be_wr and r["trades"] >= 5:
            issues.append(f"WR {wr:.0f}% < breakeven {be_wr:.0f}%")
        if r["avg_notional"] < 10 and r["trades"] >= 3:
            issues.append(f"tiny trades ({fmt_usd(r['avg_notional'])})")

        if not issues:
            verdict = "GO"
        elif len(issues) == 1 and r["trades"] < 10:
            verdict = "WATCH"
        else:
            verdict = "STOP"

        icon = {"GO": "+", "WATCH": "~", "STOP": "X"}[verdict]
        print(
            f"  {icon} {ticker:10s} | {verdict:5s} | {r['trades']:>3} trades | "
            f"WR {wr:>5.1f}% | EV {fmt_usd(ev):>8} | "
            f"P&L {fmt_usd(r['total_pnl']):>10} | "
            f"Size {fmt_usd(r['avg_notional']):>8}"
        )
        if issues:
            print(f"    Issues: {', '.join(issues)}")

    print(f"\n  + = GO (profitable, keep trading)")
    print(f"  ~ = WATCH (needs more data or minor issue)")
    print(f"  X = STOP (losing money, investigate)")


# =========================================================================
# MAIN
# =========================================================================

def main():
    import argparse
    parser = argparse.ArgumentParser(description="AGAPE-SPOT Production Health Check")
    parser.add_argument("--quick", action="store_true", help="Last 1h only")
    parser.add_argument("--hours", type=int, default=24, help="Lookback hours (default: 24)")
    args = parser.parse_args()

    lookback = 1 if args.quick else args.hours

    print("=" * 70)
    print("  AGAPE-SPOT PRODUCTION HEALTH CHECK")
    print(f"  {datetime.now(CT):%Y-%m-%d %H:%M CT}")
    print(f"  Lookback: {lookback}h" + (" (quick mode)" if args.quick else ""))
    print("=" * 70)

    conn = get_conn()

    try:
        check_1_recent_balance_logs(conn, lookback)
        check_2_trade_sizing(conn, lookback)
        check_3_scan_activity(conn, lookback)
        check_4_recent_pnl(conn, lookback)
        check_5_open_positions(conn)
        check_6_compounding(conn)
        check_7_fee_tracking(conn, lookback)
        check_8_loss_streaks(conn, lookback)
        check_9_bayesian_state(conn)
        check_10_account_pnl(conn)
        check_11_verdict(conn, lookback)
    finally:
        conn.close()

    print(f"\n{'=' * 70}")
    print(f"  DONE. Run with --quick for last 1h, --hours 48 for 2 days.")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    main()
