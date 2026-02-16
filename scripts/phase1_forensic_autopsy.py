#!/usr/bin/env python3
"""
PHASE 1: FORENSIC AUTOPSY — Where Exactly Is the Money Going?
==============================================================
Combines Phase 1A (Loss Decomposition) + Phase 1B (Signal Quality Audit).

Maps directly to the AGAPE-SPOT database schema:
  - agape_spot_positions: All trade records
  - agape_spot_scan_activity: Every scan cycle with market data
  - agape_spot_win_tracker: Bayesian tracker state
  - agape_spot_equity_snapshots: Equity curve data

Run:
  python scripts/phase1_forensic_autopsy.py

Requires: DATABASE_URL environment variable or .env file.

Sections:
  F1:  P&L by 2-hour window per ticker (CT timezone)
  F2:  P&L by volatility regime (chop_index at entry)
  F3:  P&L by exit reason — which exit type destroys the most value?
  F4:  Consecutive loss streaks with market context
  F5:  Losing trades by funding regime (downtrend proxy)
  F6:  Fee impact: gross vs estimated net P&L per ticker
  F7:  Signal confidence vs actual win rate
  F8:  Oracle win probability calibration (predicted vs actual)
  F9:  Funding rate at entry vs outcome
  F10: Chop index at entry vs outcome
  F11: Multi-factor interaction (best/worst 2-factor combos)
  F12: Optimal stop-loss analysis (was the stop too tight?)
  F13: Overtrading analysis (trade frequency vs P&L)
  F14: Price movement AFTER exit (did we exit too early?)
  F15: Top 3 money-losing conditions (summary)
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
# Coinbase taker fee estimate (0.4% per side, 0.8% round-trip)
FEE_RATE_PER_SIDE = 0.004


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
            print("ERROR: DATABASE_URL not set. Export it or create .env file.")
            sys.exit(1)
        return psycopg2.connect(url, connect_timeout=15)
    except Exception as e:
        print(f"ERROR: Database connection failed: {e}")
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


def bar(val, scale=2, max_len=25):
    """ASCII bar chart."""
    if val is None:
        return ""
    v = float(val)
    n = min(int(abs(v) / scale), max_len)
    return ("+" * n) if v >= 0 else ("-" * n)


# ===================================================================
# F1: P&L by 2-Hour Time Window per Ticker
# ===================================================================
def f1_pnl_by_time_window(conn):
    print("\n" + "=" * 80)
    print("F1: P&L BY 2-HOUR TIME WINDOW (CT) — Per Ticker")
    print("=" * 80)
    print("  Goal: Find which hours are profitable vs destructive per ticker.")
    print("  Uses open_time (entry) for window classification.\n")

    rows = q(conn, """
        WITH time_buckets AS (
            SELECT
                ticker,
                FLOOR(EXTRACT(HOUR FROM open_time AT TIME ZONE 'America/Chicago') / 2) * 2 AS bucket_start,
                realized_pnl,
                CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END AS is_win
            FROM agape_spot_positions
            WHERE status IN ('closed', 'expired', 'stopped')
              AND realized_pnl IS NOT NULL
              AND account_label != 'paper'
        )
        SELECT
            ticker,
            bucket_start,
            COUNT(*) AS trades,
            SUM(is_win) AS wins,
            COALESCE(SUM(realized_pnl), 0) AS total_pnl,
            COALESCE(AVG(realized_pnl), 0) AS avg_pnl
        FROM time_buckets
        GROUP BY ticker, bucket_start
        ORDER BY ticker, bucket_start
    """)

    if not rows:
        print("  No data")
        return

    current_ticker = None
    ticker_totals = {}

    for r in rows:
        ticker, bucket, trades, wins, total_pnl, avg_pnl = r[0], int(r[1]), r[2], r[3] or 0, float(r[4]), float(r[5])
        if ticker != current_ticker:
            if current_ticker:
                # Print summary for previous ticker
                t = ticker_totals.get(current_ticker, {"profit_hours_pnl": 0, "loss_hours_pnl": 0})
                print(f"  {'SUBTOTAL':<12} profit hours: {pnl(t['profit_hours_pnl'])}  |  loss hours: {pnl(t['loss_hours_pnl'])}  |  if_no_loss_hours: {pnl(t['profit_hours_pnl'])}")
                print()
            current_ticker = ticker
            ticker_totals[ticker] = {"profit_hours_pnl": 0, "loss_hours_pnl": 0}
            print(f"  {ticker}")
            print(f"  {'Window':<14} {'Trades':>7} {'Wins':>6} {'WR%':>7} {'Total P&L':>12} {'Avg P&L':>10}  Visual")
            print(f"  {'-'*75}")

        wr = wins / trades * 100 if trades > 0 else 0
        window = f"{bucket:02.0f}:00-{bucket+2:02.0f}:00"
        print(f"  {window:<14} {trades:>7} {wins:>6} {wr:>6.1f}% {pnl(total_pnl):>12} {pnl(avg_pnl):>10}  {bar(total_pnl)}")

        if total_pnl >= 0:
            ticker_totals[ticker]["profit_hours_pnl"] += total_pnl
        else:
            ticker_totals[ticker]["loss_hours_pnl"] += total_pnl

    # Final ticker summary
    if current_ticker:
        t = ticker_totals.get(current_ticker, {"profit_hours_pnl": 0, "loss_hours_pnl": 0})
        print(f"  {'SUBTOTAL':<12} profit hours: {pnl(t['profit_hours_pnl'])}  |  loss hours: {pnl(t['loss_hours_pnl'])}  |  if_no_loss_hours: {pnl(t['profit_hours_pnl'])}")

    # Cross-ticker summary
    print(f"\n  CROSS-TICKER SUMMARY:")
    print(f"  {'-'*60}")
    total_saved = 0
    for ticker in ticker_totals:
        saved = abs(ticker_totals[ticker]["loss_hours_pnl"])
        total_saved += saved
        print(f"  {ticker}: Could save {pnl(saved)} by not trading during losing hours")
    print(f"  TOTAL potential savings: {pnl(total_saved)}")


# ===================================================================
# F2: P&L by Volatility Regime (Chop Index)
# ===================================================================
def f2_volatility_regime(conn):
    print("\n" + "=" * 80)
    print("F2: P&L BY VOLATILITY REGIME (chop_index_at_entry)")
    print("=" * 80)
    print("  chop_index: 0.0 = perfectly trending, 1.0 = perfectly choppy")
    print("  CHOPPY = chop > 0.65, TRENDING = chop <= 0.65\n")

    rows = q(conn, """
        SELECT
            ticker,
            CASE
                WHEN chop_index_at_entry IS NULL THEN 'NO_DATA'
                WHEN chop_index_at_entry > 0.80 THEN 'VERY_CHOPPY (>0.80)'
                WHEN chop_index_at_entry > 0.65 THEN 'CHOPPY (0.65-0.80)'
                WHEN chop_index_at_entry > 0.50 THEN 'MODERATE (0.50-0.65)'
                WHEN chop_index_at_entry > 0.35 THEN 'TRENDING (0.35-0.50)'
                ELSE 'STRONG_TREND (<0.35)'
            END AS regime,
            COUNT(*) AS trades,
            COUNT(*) FILTER (WHERE realized_pnl > 0) AS wins,
            COALESCE(SUM(realized_pnl), 0) AS total_pnl,
            COALESCE(AVG(realized_pnl), 0) AS avg_pnl,
            COALESCE(AVG(chop_index_at_entry), 0) AS avg_chop
        FROM agape_spot_positions
        WHERE status IN ('closed', 'expired', 'stopped')
          AND realized_pnl IS NOT NULL
          AND account_label != 'paper'
        GROUP BY ticker, regime
        ORDER BY ticker, avg_chop
    """)

    if not rows:
        print("  No data")
        return

    print(f"  {'Ticker':<12} {'Regime':<24} {'Trades':>7} {'WR%':>7} {'Total P&L':>12} {'Avg P&L':>10} {'Avg Chop':>9}")
    print(f"  {'-'*85}")
    current = None
    for r in rows:
        ticker = r[0]
        if ticker != current:
            if current:
                print(f"  {'-'*85}")
            current = ticker
        regime, trades, wins, total_pnl, avg_pnl, avg_chop = r[1], r[2], r[3] or 0, float(r[4]), float(r[5]), float(r[6])
        wr = wins / trades * 100 if trades > 0 else 0
        print(f"  {ticker:<12} {regime:<24} {trades:>7} {wr:>6.1f}% {pnl(total_pnl):>12} {pnl(avg_pnl):>10} {avg_chop:>8.3f}")


# ===================================================================
# F3: P&L by Exit Reason — Value Destruction Analysis
# ===================================================================
def f3_exit_reason_value_destruction(conn):
    print("\n" + "=" * 80)
    print("F3: P&L BY EXIT REASON — Which Exit Destroys Most Value?")
    print("=" * 80)

    rows = q(conn, """
        SELECT
            COALESCE(close_reason, 'UNKNOWN') AS reason,
            COUNT(*) AS trades,
            COUNT(*) FILTER (WHERE realized_pnl > 0) AS wins,
            COUNT(*) FILTER (WHERE realized_pnl < 0) AS losses,
            COALESCE(SUM(realized_pnl), 0) AS total_pnl,
            COALESCE(AVG(realized_pnl), 0) AS avg_pnl,
            COALESCE(AVG(realized_pnl) FILTER (WHERE realized_pnl > 0), 0) AS avg_win,
            COALESCE(AVG(realized_pnl) FILTER (WHERE realized_pnl < 0), 0) AS avg_loss,
            AVG(EXTRACT(EPOCH FROM (close_time - open_time)) / 60) AS avg_hold_min
        FROM agape_spot_positions
        WHERE status IN ('closed', 'expired', 'stopped')
          AND realized_pnl IS NOT NULL
          AND account_label != 'paper'
        GROUP BY close_reason
        ORDER BY COALESCE(SUM(realized_pnl), 0) ASC
    """)

    if not rows:
        print("  No data")
        return

    print(f"\n  Sorted by total P&L impact (worst first):")
    print(f"  {'Exit Reason':<28} {'Trades':>7} {'Wins':>5} {'WR%':>6} {'Total P&L':>12} {'Avg Win':>10} {'Avg Loss':>10} {'Avg Hold':>9}")
    print(f"  {'-'*95}")
    for r in rows:
        reason, trades, wins, losses = r[0], r[1], r[2] or 0, r[3] or 0
        total_pnl, avg_pnl = float(r[4]), float(r[5])
        avg_win, avg_loss = float(r[6]), float(r[7])
        avg_hold = float(r[8] or 0)
        wr = wins / trades * 100 if trades > 0 else 0
        hold_str = f"{avg_hold:.0f}m" if avg_hold < 120 else f"{avg_hold/60:.1f}h"
        flag = " <<<" if total_pnl < -10 else ""
        print(f"  {reason:<28} {trades:>7} {wins:>5} {wr:>5.1f}% {pnl(total_pnl):>12} {pnl(avg_win):>10} {pnl(avg_loss):>10} {hold_str:>9}{flag}")

    # Per-ticker breakdown of the worst exit reason
    worst_reason = rows[0][0] if rows else None
    if worst_reason:
        print(f"\n  WORST EXIT REASON '{worst_reason}' — Per Ticker:")
        print(f"  {'-'*60}")
        detail = q(conn, """
            SELECT
                ticker,
                COUNT(*) AS trades,
                COALESCE(SUM(realized_pnl), 0) AS total_pnl,
                COALESCE(AVG(realized_pnl), 0) AS avg_pnl
            FROM agape_spot_positions
            WHERE close_reason = %s
              AND status IN ('closed', 'expired', 'stopped')
              AND realized_pnl IS NOT NULL AND account_label != 'paper'
            GROUP BY ticker ORDER BY total_pnl ASC
        """, (worst_reason,))
        for r in detail:
            print(f"    {r[0]:<12} {r[1]:>5} trades  {pnl(r[2]):>12} total  {pnl(r[3]):>10} avg")


# ===================================================================
# F4: Consecutive Loss Streaks with Market Context
# ===================================================================
def f4_loss_streaks_context(conn):
    print("\n" + "=" * 80)
    print("F4: CONSECUTIVE LOSS STREAKS WITH CONTEXT")
    print("=" * 80)

    for ticker in TICKERS:
        rows = q(conn, """
            SELECT
                position_id, realized_pnl, close_time, close_reason,
                funding_regime_at_entry, chop_index_at_entry,
                oracle_win_probability,
                EXTRACT(HOUR FROM open_time AT TIME ZONE 'America/Chicago') AS entry_hour
            FROM agape_spot_positions
            WHERE ticker = %s
              AND status IN ('closed', 'expired', 'stopped')
              AND realized_pnl IS NOT NULL
              AND account_label != 'paper'
            ORDER BY close_time ASC
        """, (ticker,))

        if not rows:
            continue

        # Find all loss streaks of 5+ trades
        streaks = []
        current_streak = []

        for r in rows:
            pnl_val = float(r[1])
            if pnl_val < 0:
                current_streak.append(r)
            else:
                if len(current_streak) >= 5:
                    streaks.append(current_streak)
                current_streak = []
        if len(current_streak) >= 5:
            streaks.append(current_streak)

        if not streaks:
            continue

        # Sort by total loss (worst first)
        streaks.sort(key=lambda s: sum(float(t[1]) for t in s))

        print(f"\n  {ticker}: {len(streaks)} streaks of 5+ consecutive losses")
        for i, streak in enumerate(streaks[:3]):  # Top 3 worst
            total_loss = sum(float(t[1]) for t in streak)
            start = streak[0][2]
            end = streak[-1][2]
            reasons = {}
            regimes = {}
            hours = {}
            for t in streak:
                r = t[3] or "UNKNOWN"
                reasons[r] = reasons.get(r, 0) + 1
                reg = t[4] or "UNKNOWN"
                regimes[reg] = regimes.get(reg, 0) + 1
                h = int(t[7]) if t[7] else -1
                hours[h] = hours.get(h, 0) + 1

            top_reason = max(reasons, key=reasons.get)
            top_regime = max(regimes, key=regimes.get)
            top_hour = max(hours, key=hours.get)
            avg_oracle = sum(float(t[6] or 0) for t in streak) / len(streak)
            avg_chop = sum(float(t[5] or 0) for t in streak) / max(1, sum(1 for t in streak if t[5]))

            print(f"    Streak #{i+1}: {len(streak)} trades | {pnl(total_loss)} total loss")
            print(f"      Period: {start} → {end}")
            print(f"      Dominant exit: {top_reason} ({reasons[top_reason]}x)")
            print(f"      Dominant regime: {top_regime} ({regimes[top_regime]}x)")
            print(f"      Peak entry hour: {top_hour}:00 CT ({hours[top_hour]}x)")
            print(f"      Avg oracle prob: {avg_oracle:.3f}")
            print(f"      Avg chop index: {avg_chop:.3f}")


# ===================================================================
# F5: Losing Trades by Funding Regime (Negative = Bearish Proxy)
# ===================================================================
def f5_losses_by_funding(conn):
    print("\n" + "=" * 80)
    print("F5: LOSING TRADES BY FUNDING REGIME")
    print("=" * 80)
    print("  Negative funding = shorts paying longs = bearish bias (downtrend proxy)")

    rows = q(conn, """
        WITH regime_buckets AS (
            SELECT
                ticker,
                CASE
                    WHEN funding_regime_at_entry IN ('EXTREME_NEGATIVE', 'HEAVILY_NEGATIVE', 'NEGATIVE') THEN 'NEGATIVE'
                    WHEN funding_regime_at_entry IN ('EXTREME_POSITIVE', 'HEAVILY_POSITIVE', 'POSITIVE') THEN 'POSITIVE'
                    WHEN funding_regime_at_entry IN ('BALANCED', 'MILD_LONG_BIAS', 'MILD_SHORT_BIAS') THEN 'NEUTRAL'
                    ELSE 'UNKNOWN'
                END AS regime_bucket,
                realized_pnl,
                CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END AS is_win
            FROM agape_spot_positions
            WHERE status IN ('closed', 'expired', 'stopped')
              AND realized_pnl IS NOT NULL
              AND account_label != 'paper'
        )
        SELECT
            regime_bucket,
            ticker,
            COUNT(*) AS trades,
            SUM(is_win) AS wins,
            COALESCE(SUM(realized_pnl), 0) AS total_pnl,
            COALESCE(AVG(realized_pnl), 0) AS avg_pnl,
            COALESCE(AVG(realized_pnl) FILTER (WHERE realized_pnl > 0), 0) AS avg_win,
            COALESCE(AVG(realized_pnl) FILTER (WHERE realized_pnl < 0), 0) AS avg_loss
        FROM regime_buckets
        GROUP BY regime_bucket, ticker
        ORDER BY regime_bucket, ticker
    """)

    if not rows:
        print("  No data")
        return

    print(f"\n  {'Regime':<12} {'Ticker':<12} {'Trades':>7} {'WR%':>7} {'Total P&L':>12} {'Avg Win':>10} {'Avg Loss':>10} {'EV/trade':>10}")
    print(f"  {'-'*85}")
    for r in rows:
        regime, ticker, trades, wins = r[0], r[1], r[2], r[3] or 0
        total_pnl, avg_pnl, avg_win, avg_loss = float(r[4]), float(r[5]), float(r[6]), float(r[7])
        wr = wins / trades * 100 if trades > 0 else 0
        # EV = (wr * avg_win) - ((1-wr) * |avg_loss|)
        ev = (wr/100 * avg_win) + ((1-wr/100) * avg_loss) if trades > 0 else 0
        print(f"  {regime:<12} {ticker:<12} {trades:>7} {wr:>6.1f}% {pnl(total_pnl):>12} {pnl(avg_win):>10} {pnl(avg_loss):>10} {pnl(ev):>10}")


# ===================================================================
# F6: Fee Impact — Gross vs Estimated Net P&L
# ===================================================================
def f6_fee_impact(conn):
    print("\n" + "=" * 80)
    print("F6: FEE IMPACT — Gross P&L vs Estimated Net P&L (0.8% round-trip)")
    print("=" * 80)

    rows = q(conn, """
        SELECT
            ticker,
            COUNT(*) AS trades,
            COALESCE(SUM(realized_pnl), 0) AS gross_pnl,
            -- Estimate fees: notional = entry_price * quantity
            -- Round-trip fee = notional * 0.008 (0.4% each side)
            COALESCE(SUM(entry_price * quantity * 0.008), 0) AS estimated_fees,
            COALESCE(SUM(COALESCE(entry_fee_usd, 0) + COALESCE(exit_fee_usd, 0)), 0) AS recorded_fees,
            COUNT(*) FILTER (WHERE entry_fee_usd IS NOT NULL OR exit_fee_usd IS NOT NULL) AS has_fee_data
        FROM agape_spot_positions
        WHERE status IN ('closed', 'expired', 'stopped')
          AND realized_pnl IS NOT NULL
          AND account_label != 'paper'
        GROUP BY ticker
        ORDER BY gross_pnl DESC
    """)

    if not rows:
        print("  No data")
        return

    print(f"\n  {'Ticker':<12} {'Trades':>7} {'Gross P&L':>12} {'Est Fees':>12} {'Net P&L':>12} {'Fee/Gross':>10} {'Fee Data':>9}")
    print(f"  {'-'*80}")
    total_gross = total_fees = 0
    for r in rows:
        ticker, trades = r[0], r[1]
        gross = float(r[2])
        est_fees = float(r[3])
        recorded = float(r[4])
        has_data = r[5]
        net = gross - est_fees
        fee_pct = est_fees / abs(gross) * 100 if gross != 0 else 0
        total_gross += gross
        total_fees += est_fees
        verdict = "PROFITABLE" if net > 0 else "NEGATIVE NET"
        print(f"  {ticker:<12} {trades:>7} {pnl(gross):>12} {pnl(-est_fees):>12} {pnl(net):>12} {fee_pct:>8.1f}% {has_data:>5}/{trades}  {verdict}")

    print(f"  {'-'*80}")
    total_net = total_gross - total_fees
    print(f"  {'TOTAL':<12} {'':>7} {pnl(total_gross):>12} {pnl(-total_fees):>12} {pnl(total_net):>12}")
    print(f"\n  VERDICT: Gross {pnl(total_gross)} → Net {pnl(total_net)} after estimated fees")


# ===================================================================
# F7: Signal Confidence vs Actual Win Rate
# ===================================================================
def f7_signal_confidence(conn):
    print("\n" + "=" * 80)
    print("F7: SIGNAL CONFIDENCE vs ACTUAL WIN RATE")
    print("=" * 80)

    rows = q(conn, """
        SELECT
            COALESCE(signal_confidence, 'UNKNOWN') AS conf,
            ticker,
            COUNT(*) AS trades,
            COUNT(*) FILTER (WHERE realized_pnl > 0) AS wins,
            COALESCE(SUM(realized_pnl), 0) AS total_pnl,
            COALESCE(AVG(realized_pnl), 0) AS avg_pnl
        FROM agape_spot_positions
        WHERE status IN ('closed', 'expired', 'stopped')
          AND realized_pnl IS NOT NULL
          AND account_label != 'paper'
        GROUP BY signal_confidence, ticker
        ORDER BY signal_confidence, ticker
    """)

    if not rows:
        print("  No data")
        return

    print(f"\n  {'Confidence':<12} {'Ticker':<12} {'Trades':>7} {'WR%':>7} {'Total P&L':>12} {'Avg P&L':>10}")
    print(f"  {'-'*65}")
    for r in rows:
        conf, ticker, trades, wins = r[0], r[1], r[2], r[3] or 0
        total_pnl, avg_pnl = float(r[4]), float(r[5])
        wr = wins / trades * 100 if trades > 0 else 0
        print(f"  {conf:<12} {ticker:<12} {trades:>7} {wr:>6.1f}% {pnl(total_pnl):>12} {pnl(avg_pnl):>10}")

    # Aggregate
    print(f"\n  AGGREGATE BY CONFIDENCE:")
    agg = q(conn, """
        SELECT
            COALESCE(signal_confidence, 'UNKNOWN'),
            COUNT(*),
            COUNT(*) FILTER (WHERE realized_pnl > 0),
            COALESCE(SUM(realized_pnl), 0),
            COALESCE(AVG(realized_pnl), 0)
        FROM agape_spot_positions
        WHERE status IN ('closed', 'expired', 'stopped')
          AND realized_pnl IS NOT NULL AND account_label != 'paper'
        GROUP BY signal_confidence ORDER BY signal_confidence
    """)
    print(f"  {'Confidence':<12} {'Trades':>7} {'WR%':>7} {'Total P&L':>12} {'Avg P&L':>10}")
    print(f"  {'-'*55}")
    for r in agg:
        wr = (r[2] or 0) / r[1] * 100 if r[1] > 0 else 0
        print(f"  {r[0]:<12} {r[1]:>7} {wr:>6.1f}% {pnl(r[3]):>12} {pnl(r[4]):>10}")


# ===================================================================
# F8: Oracle Win Probability Calibration
# ===================================================================
def f8_oracle_calibration(conn):
    print("\n" + "=" * 80)
    print("F8: ORACLE WIN PROBABILITY CALIBRATION")
    print("=" * 80)
    print("  Predicted probability vs actual win rate per bucket.")
    print("  Perfectly calibrated = predicted ≈ actual.\n")

    rows = q(conn, """
        SELECT
            CASE
                WHEN oracle_win_probability IS NULL THEN 'NO_DATA'
                WHEN oracle_win_probability < 0.45 THEN '0.00-0.45'
                WHEN oracle_win_probability < 0.50 THEN '0.45-0.50'
                WHEN oracle_win_probability < 0.55 THEN '0.50-0.55'
                WHEN oracle_win_probability < 0.60 THEN '0.55-0.60'
                WHEN oracle_win_probability < 0.65 THEN '0.60-0.65'
                WHEN oracle_win_probability < 0.70 THEN '0.65-0.70'
                ELSE '0.70+'
            END AS prob_bucket,
            COUNT(*) AS trades,
            COUNT(*) FILTER (WHERE realized_pnl > 0) AS wins,
            AVG(oracle_win_probability) AS avg_predicted,
            COALESCE(SUM(realized_pnl), 0) AS total_pnl,
            COALESCE(AVG(realized_pnl), 0) AS avg_pnl
        FROM agape_spot_positions
        WHERE status IN ('closed', 'expired', 'stopped')
          AND realized_pnl IS NOT NULL
          AND account_label != 'paper'
        GROUP BY prob_bucket
        ORDER BY avg_predicted NULLS FIRST
    """)

    if not rows:
        print("  No data")
        return

    print(f"  {'Prob Bucket':<14} {'Trades':>7} {'Actual WR':>10} {'Predicted':>10} {'Gap':>8} {'Total P&L':>12} {'Calibrated?'}")
    print(f"  {'-'*80}")
    for r in rows:
        bucket, trades, wins = r[0], r[1], r[2] or 0
        avg_pred = float(r[3]) if r[3] else 0
        total_pnl, avg_pnl = float(r[4]), float(r[5])
        actual_wr = wins / trades if trades > 0 else 0
        gap = actual_wr - avg_pred if avg_pred > 0 else 0
        calibrated = "YES" if abs(gap) < 0.05 else "OVER" if gap < -0.05 else "UNDER"
        print(f"  {bucket:<14} {trades:>7} {actual_wr:>9.1%} {avg_pred:>9.1%} {gap:>+7.1%} {pnl(total_pnl):>12} {calibrated}")


# ===================================================================
# F9: Funding Rate at Entry vs Outcome
# ===================================================================
def f9_funding_rate_outcome(conn):
    print("\n" + "=" * 80)
    print("F9: FUNDING RATE AT ENTRY vs OUTCOME")
    print("=" * 80)
    print("  Negative funding = shorts paying longs (bearish sentiment)")
    print("  Does going long when funding is negative work?\n")

    rows = q(conn, """
        SELECT
            CASE
                WHEN funding_rate_at_entry IS NULL THEN 'NO_DATA'
                WHEN funding_rate_at_entry < -0.01 THEN 'VERY_NEG (<-1%)'
                WHEN funding_rate_at_entry < -0.001 THEN 'NEG (-1% to -0.1%)'
                WHEN funding_rate_at_entry < 0.001 THEN 'NEUTRAL (-0.1% to +0.1%)'
                WHEN funding_rate_at_entry < 0.01 THEN 'POS (+0.1% to +1%)'
                ELSE 'VERY_POS (>+1%)'
            END AS bucket,
            COUNT(*) AS trades,
            COUNT(*) FILTER (WHERE realized_pnl > 0) AS wins,
            COALESCE(SUM(realized_pnl), 0) AS total_pnl,
            COALESCE(AVG(realized_pnl), 0) AS avg_pnl,
            AVG(funding_rate_at_entry) AS avg_rate
        FROM agape_spot_positions
        WHERE status IN ('closed', 'expired', 'stopped')
          AND realized_pnl IS NOT NULL
          AND account_label != 'paper'
        GROUP BY bucket
        ORDER BY avg_rate NULLS FIRST
    """)

    if not rows:
        print("  No data")
        return

    print(f"  {'Funding Bucket':<24} {'Trades':>7} {'WR%':>7} {'Total P&L':>12} {'Avg P&L':>10} {'Avg Rate':>10}")
    print(f"  {'-'*75}")
    for r in rows:
        bucket, trades, wins = r[0], r[1], r[2] or 0
        total_pnl, avg_pnl = float(r[3]), float(r[4])
        avg_rate = float(r[5]) if r[5] else 0
        wr = wins / trades * 100 if trades > 0 else 0
        print(f"  {bucket:<24} {trades:>7} {wr:>6.1f}% {pnl(total_pnl):>12} {pnl(avg_pnl):>10} {avg_rate:>9.4f}")


# ===================================================================
# F10: Chop Index at Entry vs Outcome
# ===================================================================
def f10_chop_outcome(conn):
    print("\n" + "=" * 80)
    print("F10: CHOP INDEX AT ENTRY vs OUTCOME (0.1 increments)")
    print("=" * 80)

    rows = q(conn, """
        SELECT
            CASE
                WHEN chop_index_at_entry IS NULL THEN 'NO_DATA'
                ELSE CONCAT(
                    ROUND((FLOOR(chop_index_at_entry * 10) / 10.0)::numeric, 1)::text,
                    '-',
                    ROUND(((FLOOR(chop_index_at_entry * 10) + 1) / 10.0)::numeric, 1)::text
                )
            END AS bucket,
            COUNT(*) AS trades,
            COUNT(*) FILTER (WHERE realized_pnl > 0) AS wins,
            COALESCE(SUM(realized_pnl), 0) AS total_pnl,
            COALESCE(AVG(realized_pnl), 0) AS avg_pnl,
            AVG(chop_index_at_entry) AS avg_chop
        FROM agape_spot_positions
        WHERE status IN ('closed', 'expired', 'stopped')
          AND realized_pnl IS NOT NULL
          AND account_label != 'paper'
        GROUP BY bucket
        ORDER BY avg_chop NULLS FIRST
    """)

    if not rows:
        print("  No data")
        return

    print(f"  {'Chop Range':<14} {'Trades':>7} {'WR%':>7} {'Total P&L':>12} {'Avg P&L':>10}")
    print(f"  {'-'*55}")
    for r in rows:
        bucket, trades, wins = r[0], r[1], r[2] or 0
        total_pnl, avg_pnl = float(r[3]), float(r[4])
        wr = wins / trades * 100 if trades > 0 else 0
        visual = bar(total_pnl, scale=5)
        print(f"  {bucket:<14} {trades:>7} {wr:>6.1f}% {pnl(total_pnl):>12} {pnl(avg_pnl):>10}  {visual}")


# ===================================================================
# F11: Multi-Factor Interaction Analysis
# ===================================================================
def f11_multi_factor(conn):
    print("\n" + "=" * 80)
    print("F11: MULTI-FACTOR INTERACTION — Best & Worst 2-Factor Combos")
    print("=" * 80)
    print("  Cross-tabulating funding regime × volatility regime × ticker\n")

    rows = q(conn, """
        WITH categorized AS (
            SELECT
                ticker,
                CASE
                    WHEN funding_regime_at_entry IN ('EXTREME_NEGATIVE', 'HEAVILY_NEGATIVE', 'NEGATIVE') THEN 'NEG_FUND'
                    WHEN funding_regime_at_entry IN ('EXTREME_POSITIVE', 'HEAVILY_POSITIVE', 'POSITIVE') THEN 'POS_FUND'
                    ELSE 'NEUT_FUND'
                END AS funding_cat,
                CASE
                    WHEN chop_index_at_entry IS NULL THEN 'NO_CHOP'
                    WHEN chop_index_at_entry > 0.65 THEN 'CHOPPY'
                    ELSE 'TRENDING'
                END AS vol_cat,
                realized_pnl,
                CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END AS is_win
            FROM agape_spot_positions
            WHERE status IN ('closed', 'expired', 'stopped')
              AND realized_pnl IS NOT NULL
              AND account_label != 'paper'
        )
        SELECT
            ticker,
            funding_cat,
            vol_cat,
            COUNT(*) AS trades,
            SUM(is_win) AS wins,
            COALESCE(SUM(realized_pnl), 0) AS total_pnl,
            COALESCE(AVG(realized_pnl), 0) AS avg_pnl
        FROM categorized
        GROUP BY ticker, funding_cat, vol_cat
        HAVING COUNT(*) >= 5
        ORDER BY avg_pnl DESC
    """)

    if not rows:
        print("  No data (or all combos have < 5 trades)")
        return

    print(f"  BEST COMBOS (highest avg P&L, min 5 trades):")
    print(f"  {'Ticker':<12} {'Funding':<12} {'Volatility':<12} {'Trades':>7} {'WR%':>7} {'Total P&L':>12} {'Avg P&L':>10}")
    print(f"  {'-'*75}")
    for r in rows[:10]:
        ticker, fund, vol, trades, wins = r[0], r[1], r[2], r[3], r[4] or 0
        total_pnl, avg_pnl = float(r[5]), float(r[6])
        wr = wins / trades * 100 if trades > 0 else 0
        print(f"  {ticker:<12} {fund:<12} {vol:<12} {trades:>7} {wr:>6.1f}% {pnl(total_pnl):>12} {pnl(avg_pnl):>10}")

    print(f"\n  WORST COMBOS (lowest avg P&L, min 5 trades):")
    print(f"  {'Ticker':<12} {'Funding':<12} {'Volatility':<12} {'Trades':>7} {'WR%':>7} {'Total P&L':>12} {'Avg P&L':>10}")
    print(f"  {'-'*75}")
    for r in rows[-10:]:
        ticker, fund, vol, trades, wins = r[0], r[1], r[2], r[3], r[4] or 0
        total_pnl, avg_pnl = float(r[5]), float(r[6])
        wr = wins / trades * 100 if trades > 0 else 0
        print(f"  {ticker:<12} {fund:<12} {vol:<12} {trades:>7} {wr:>6.1f}% {pnl(total_pnl):>12} {pnl(avg_pnl):>10}")


# ===================================================================
# F12: Optimal Stop-Loss Analysis
# ===================================================================
def f12_stop_loss_analysis(conn):
    print("\n" + "=" * 80)
    print("F12: STOP-LOSS ANALYSIS — Are stops too tight?")
    print("=" * 80)
    print("  For MAX_LOSS / EMERGENCY_STOP exits: what did price do AFTER the stop?")
    print("  Uses high_water_mark to assess if the trade was going to recover.\n")

    # Check how much higher the HWM was vs entry for losing trades
    rows = q(conn, """
        SELECT
            ticker,
            close_reason,
            COUNT(*) AS trades,
            AVG((close_price - entry_price) / entry_price * 100) AS avg_exit_pct,
            AVG((high_water_mark - entry_price) / NULLIF(entry_price, 0) * 100) AS avg_hwm_pct,
            AVG(EXTRACT(EPOCH FROM (close_time - open_time)) / 60) AS avg_hold_min
        FROM agape_spot_positions
        WHERE status IN ('closed', 'expired', 'stopped')
          AND realized_pnl < 0
          AND account_label != 'paper'
          AND close_reason IN ('MAX_LOSS', 'EMERGENCY_STOP', 'MAX_HOLD_TIME', 'TRAIL_STOP')
          AND entry_price > 0
          AND high_water_mark > 0
        GROUP BY ticker, close_reason
        ORDER BY ticker, close_reason
    """)

    if not rows:
        print("  No losing trades with HWM data")
        return

    print(f"  {'Ticker':<12} {'Exit Reason':<20} {'Trades':>7} {'Avg Exit%':>10} {'Avg HWM%':>10} {'Avg Hold':>9}")
    print(f"  {'-'*72}")
    for r in rows:
        ticker, reason, trades = r[0], r[1], r[2]
        avg_exit_pct = float(r[3] or 0)
        avg_hwm_pct = float(r[4] or 0)
        avg_hold = float(r[5] or 0)
        hold_str = f"{avg_hold:.0f}m" if avg_hold < 120 else f"{avg_hold/60:.1f}h"
        # If HWM% was positive, the trade WAS in profit before losing
        was_profitable = " (was profitable!)" if avg_hwm_pct > 0.2 else ""
        print(f"  {ticker:<12} {reason:<20} {trades:>7} {avg_exit_pct:>+9.2f}% {avg_hwm_pct:>+9.2f}% {hold_str:>9}{was_profitable}")


# ===================================================================
# F13: Overtrading Analysis
# ===================================================================
def f13_overtrading(conn):
    print("\n" + "=" * 80)
    print("F13: OVERTRADING ANALYSIS — Trade Frequency vs P&L")
    print("=" * 80)

    rows = q(conn, """
        WITH daily AS (
            SELECT
                ticker,
                DATE(open_time AT TIME ZONE 'America/Chicago') AS trade_date,
                COUNT(*) AS trades_per_day,
                COALESCE(SUM(realized_pnl), 0) AS daily_pnl
            FROM agape_spot_positions
            WHERE status IN ('closed', 'expired', 'stopped')
              AND realized_pnl IS NOT NULL
              AND account_label != 'paper'
            GROUP BY ticker, trade_date
        )
        SELECT
            ticker,
            AVG(trades_per_day) AS avg_trades_day,
            MAX(trades_per_day) AS max_trades_day,
            CORR(trades_per_day, daily_pnl) AS correlation,
            COUNT(*) AS trading_days,
            -- Simulate minimum gaps
            SUM(CASE WHEN trades_per_day > 24 THEN (trades_per_day - 24) * (daily_pnl / NULLIF(trades_per_day, 0)) ELSE 0 END) AS excess_pnl_if_24_max,
            SUM(CASE WHEN trades_per_day > 12 THEN (trades_per_day - 12) * (daily_pnl / NULLIF(trades_per_day, 0)) ELSE 0 END) AS excess_pnl_if_12_max
        FROM daily
        GROUP BY ticker
        ORDER BY avg_trades_day DESC
    """)

    if not rows:
        print("  No data")
        return

    print(f"\n  {'Ticker':<12} {'Avg/Day':>8} {'Max/Day':>8} {'Corr(freq,pnl)':>15} {'Days':>6}")
    print(f"  {'-'*55}")
    for r in rows:
        ticker = r[0]
        avg_day = float(r[1] or 0)
        max_day = int(r[2] or 0)
        corr = float(r[3]) if r[3] else 0
        days = r[4]
        flag = " !!!" if corr < -0.2 else " !" if corr < -0.1 else ""
        interp = "(more trades = less profit)" if corr < -0.1 else "(no clear relationship)" if abs(corr) < 0.1 else "(more trades = more profit)"
        print(f"  {ticker:<12} {avg_day:>7.1f} {max_day:>8} {corr:>+14.3f}{flag} {days:>6}  {interp}")


# ===================================================================
# F14: Price Movement After Exit
# ===================================================================
def f14_post_exit_movement(conn):
    print("\n" + "=" * 80)
    print("F14: DID WE EXIT TOO EARLY? (HWM analysis on winning trades)")
    print("=" * 80)
    print("  For TRAIL_STOP winners: how much higher did price go vs our exit?")
    print("  high_water_mark / close_price = how much we captured vs peak\n")

    rows = q(conn, """
        SELECT
            ticker,
            close_reason,
            COUNT(*) AS trades,
            AVG((close_price - entry_price) / NULLIF(entry_price, 0) * 100) AS avg_capture_pct,
            AVG((high_water_mark - entry_price) / NULLIF(entry_price, 0) * 100) AS avg_peak_pct,
            AVG((high_water_mark - close_price) / NULLIF(close_price, 0) * 100) AS avg_left_on_table_pct
        FROM agape_spot_positions
        WHERE status IN ('closed', 'expired', 'stopped')
          AND realized_pnl > 0
          AND account_label != 'paper'
          AND entry_price > 0 AND close_price > 0 AND high_water_mark > 0
        GROUP BY ticker, close_reason
        HAVING COUNT(*) >= 3
        ORDER BY ticker, avg_left_on_table_pct DESC
    """)

    if not rows:
        print("  No winning trades with HWM data")
        return

    print(f"  {'Ticker':<12} {'Exit Reason':<22} {'Trades':>7} {'Captured%':>10} {'Peak%':>8} {'Left on Table':>14}")
    print(f"  {'-'*78}")
    for r in rows:
        ticker, reason, trades = r[0], r[1], r[2]
        capture = float(r[3] or 0)
        peak = float(r[4] or 0)
        left = float(r[5] or 0)
        efficiency = (capture / peak * 100) if peak > 0 else 0
        print(f"  {ticker:<12} {reason:<22} {trades:>7} {capture:>+9.3f}% {peak:>+7.3f}% {left:>+13.3f}%  ({efficiency:.0f}% efficient)")


# ===================================================================
# F15: TOP 3 MONEY-LOSING CONDITIONS (Summary)
# ===================================================================
def f15_summary(conn):
    print("\n" + "=" * 80)
    print("F15: TOP 3 MONEY-LOSING CONDITIONS (Summary)")
    print("=" * 80)

    # Query the worst conditions across all dimensions
    rows = q(conn, """
        WITH loss_analysis AS (
            SELECT
                ticker,
                COALESCE(close_reason, 'UNKNOWN') AS exit_reason,
                CASE
                    WHEN chop_index_at_entry > 0.65 THEN 'CHOPPY'
                    WHEN chop_index_at_entry IS NOT NULL THEN 'TRENDING'
                    ELSE 'UNKNOWN_VOL'
                END AS vol_regime,
                CASE
                    WHEN funding_regime_at_entry IN ('EXTREME_NEGATIVE', 'HEAVILY_NEGATIVE', 'NEGATIVE') THEN 'NEG_FUND'
                    WHEN funding_regime_at_entry IN ('EXTREME_POSITIVE', 'HEAVILY_POSITIVE', 'POSITIVE') THEN 'POS_FUND'
                    ELSE 'NEUT_FUND'
                END AS fund_cat,
                EXTRACT(HOUR FROM open_time AT TIME ZONE 'America/Chicago') AS entry_hour,
                realized_pnl
            FROM agape_spot_positions
            WHERE status IN ('closed', 'expired', 'stopped')
              AND realized_pnl IS NOT NULL AND realized_pnl < 0
              AND account_label != 'paper'
        )
        SELECT
            'TICKER+EXIT' AS dimension,
            ticker || ' / ' || exit_reason AS condition,
            COUNT(*) AS trades,
            SUM(realized_pnl) AS total_loss
        FROM loss_analysis
        GROUP BY ticker, exit_reason
        HAVING COUNT(*) >= 3

        UNION ALL

        SELECT
            'TICKER+VOL' AS dimension,
            ticker || ' / ' || vol_regime AS condition,
            COUNT(*) AS trades,
            SUM(realized_pnl) AS total_loss
        FROM loss_analysis
        GROUP BY ticker, vol_regime
        HAVING COUNT(*) >= 3

        UNION ALL

        SELECT
            'TICKER+HOUR' AS dimension,
            ticker || ' / ' || entry_hour::text || ':00 CT' AS condition,
            COUNT(*) AS trades,
            SUM(realized_pnl) AS total_loss
        FROM loss_analysis
        GROUP BY ticker, entry_hour
        HAVING COUNT(*) >= 3

        ORDER BY total_loss ASC
        LIMIT 15
    """)

    if not rows:
        print("  No data")
        return

    print(f"\n  TOP 15 WORST CONDITIONS (by total loss, min 3 losing trades):")
    print(f"  {'Rank':>4} {'Dimension':<16} {'Condition':<35} {'Losses':>7} {'Total Loss':>12}")
    print(f"  {'-'*80}")
    for i, r in enumerate(rows):
        dim, cond, trades, loss = r[0], r[1], r[2], float(r[3])
        print(f"  {i+1:>4} {dim:<16} {cond:<35} {trades:>7} {pnl(loss):>12}")

    print(f"\n  ACTION ITEMS:")
    print(f"  1. Eliminate the top 3 conditions and recalculate net P&L impact")
    print(f"  2. For each condition, check if it's fixable (time filter, regime filter, exit change)")
    print(f"  3. Simulate: with these conditions blocked, what is the new P&L and win rate?")


# ===================================================================
# MAIN
# ===================================================================
def main():
    print("=" * 80)
    print("  PHASE 1: FORENSIC AUTOPSY — AGAPE-SPOT")
    print(f"  Generated: {datetime.now(CENTRAL_TZ).strftime('%Y-%m-%d %H:%M:%S CT')}")
    print("=" * 80)

    conn = get_db_connection()

    count = q(conn, "SELECT COUNT(*) FROM agape_spot_positions WHERE account_label != 'paper'")[0][0]
    print(f"\n  Total LIVE trades in DB: {count}")

    if count == 0:
        print("  No trades found.")
        conn.close()
        return

    # Phase 1A: Loss Decomposition
    f1_pnl_by_time_window(conn)
    f2_volatility_regime(conn)
    f3_exit_reason_value_destruction(conn)
    f4_loss_streaks_context(conn)
    f5_losses_by_funding(conn)
    f6_fee_impact(conn)

    # Phase 1B: Signal Quality Audit
    f7_signal_confidence(conn)
    f8_oracle_calibration(conn)
    f9_funding_rate_outcome(conn)
    f10_chop_outcome(conn)
    f11_multi_factor(conn)
    f12_stop_loss_analysis(conn)
    f13_overtrading(conn)
    f14_post_exit_movement(conn)

    # Summary
    f15_summary(conn)

    conn.close()

    print("\n" + "=" * 80)
    print("  PHASE 1 COMPLETE")
    print("  Next: Run phase2_downtrend_analysis.py to analyze downtrend patterns")
    print("=" * 80)


if __name__ == "__main__":
    main()
