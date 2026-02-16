#!/usr/bin/env python3
"""
PHASE 2A: DOWNTREND PATTERN ANALYSIS
=====================================
Analyzes crypto downtrend behavior at the microstructure level using
AGAPE-SPOT scan_activity data (1-minute snapshots) to find exploitable
patterns for long entries.

Data source: agape_spot_scan_activity table
  - 1-minute price snapshots (eth_price column = ticker spot price)
  - Funding rate, funding regime, combined signal, oracle win probability
  - Signal action and reasoning

Analyses:
  D1: Downtrend identification — reconstruct price trends from scan data
  D2: Bounce frequency and magnitude during downtrends
  D3: Funding rate dynamics during downtrends (does extreme negative predict bounce?)
  D4: Time-of-day effect on downtrend bounces
  D5: Combined signal distribution during downtrends
  D6: Recovery speed after different drawdown depths
  D7: Mean-reversion opportunity window analysis
  D8: Downtrend duration and magnitude distribution
  D9: Bounce reliability by ticker

Run:
  python scripts/phase2_downtrend_analysis.py
"""

import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CENTRAL_TZ = ZoneInfo("America/Chicago")

TICKERS = ["ETH-USD", "BTC-USD", "XRP-USD", "SHIB-USD", "DOGE-USD"]


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
        return psycopg2.connect(url, connect_timeout=30)
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
# D1: Downtrend Identification from Scan Data
# ===================================================================
def d1_downtrend_identification(conn):
    print("\n" + "=" * 80)
    print("D1: DOWNTREND IDENTIFICATION FROM SCAN DATA")
    print("=" * 80)
    print("  Reconstructs price trends from 1-min scan snapshots.")
    print("  Downtrend = price drops > 0.5% over 30+ minutes.\n")

    for ticker in TICKERS:
        # Get price data in 15-min buckets for trend analysis
        rows = q(conn, """
            WITH price_series AS (
                SELECT
                    date_trunc('hour', timestamp) +
                        INTERVAL '15 min' * FLOOR(EXTRACT(MINUTE FROM timestamp) / 15) AS bucket,
                    AVG(eth_price) AS avg_price,
                    MIN(eth_price) AS low_price,
                    MAX(eth_price) AS high_price,
                    COUNT(*) AS readings
                FROM agape_spot_scan_activity
                WHERE ticker = %s
                  AND eth_price IS NOT NULL AND eth_price > 0
                  AND timestamp > NOW() - INTERVAL '14 days'
                GROUP BY bucket
                ORDER BY bucket
            ),
            with_change AS (
                SELECT
                    bucket,
                    avg_price,
                    low_price,
                    high_price,
                    readings,
                    LAG(avg_price, 1) OVER (ORDER BY bucket) AS prev_price,
                    LAG(avg_price, 4) OVER (ORDER BY bucket) AS price_1h_ago,
                    (avg_price - LAG(avg_price, 4) OVER (ORDER BY bucket))
                        / NULLIF(LAG(avg_price, 4) OVER (ORDER BY bucket), 0) * 100 AS pct_change_1h
                FROM price_series
            )
            SELECT
                CASE
                    WHEN pct_change_1h < -1.0 THEN 'STRONG_DOWN (>-1%/hr)'
                    WHEN pct_change_1h < -0.5 THEN 'MILD_DOWN (-0.5 to -1%/hr)'
                    WHEN pct_change_1h < 0.0 THEN 'SLIGHT_DOWN (0 to -0.5%/hr)'
                    WHEN pct_change_1h < 0.5 THEN 'SLIGHT_UP (0 to +0.5%/hr)'
                    WHEN pct_change_1h < 1.0 THEN 'MILD_UP (+0.5 to +1%/hr)'
                    ELSE 'STRONG_UP (>+1%/hr)'
                END AS trend,
                COUNT(*) AS periods,
                AVG(pct_change_1h) AS avg_change,
                MIN(pct_change_1h) AS worst_drop,
                MAX(pct_change_1h) AS best_rally
            FROM with_change
            WHERE pct_change_1h IS NOT NULL
            GROUP BY trend
            ORDER BY avg_change
        """, (ticker,))

        if not rows:
            continue

        print(f"  {ticker} — 1-Hour Trend Distribution (15-min buckets, last 14 days):")
        print(f"  {'Trend Regime':<28} {'Periods':>8} {'Avg Change':>11} {'Worst':>9} {'Best':>9}")
        print(f"  {'-'*70}")
        total_periods = sum(r[1] for r in rows)
        for r in rows:
            trend, periods, avg_ch, worst, best = r[0], r[1], float(r[2]), float(r[3]), float(r[4])
            pct_of_time = periods / total_periods * 100 if total_periods > 0 else 0
            print(f"  {trend:<28} {periods:>8} ({pct_of_time:>4.1f}%) {avg_ch:>+10.3f}% {worst:>+8.3f}% {best:>+8.3f}%")
        print()


# ===================================================================
# D2: Bounce Frequency and Magnitude During Downtrends
# ===================================================================
def d2_bounce_analysis(conn):
    print("\n" + "=" * 80)
    print("D2: BOUNCE ANALYSIS DURING DOWNTRENDS")
    print("=" * 80)
    print("  After price drops 0.5%+ in 30 min, how often does a 0.3%+ bounce occur?")
    print("  Uses 5-min price buckets from scan data.\n")

    for ticker in TICKERS:
        rows = q(conn, """
            WITH price_5min AS (
                SELECT
                    date_trunc('hour', timestamp) +
                        INTERVAL '5 min' * FLOOR(EXTRACT(MINUTE FROM timestamp) / 5) AS bucket,
                    AVG(eth_price) AS price,
                    MIN(eth_price) AS low,
                    MAX(eth_price) AS high,
                    COUNT(*) AS n
                FROM agape_spot_scan_activity
                WHERE ticker = %s
                  AND eth_price IS NOT NULL AND eth_price > 0
                  AND timestamp > NOW() - INTERVAL '14 days'
                GROUP BY bucket
                HAVING COUNT(*) >= 2
                ORDER BY bucket
            ),
            with_context AS (
                SELECT
                    bucket,
                    price,
                    low,
                    high,
                    -- 30-min lookback (6 x 5-min buckets)
                    LAG(price, 6) OVER (ORDER BY bucket) AS price_30min_ago,
                    -- 15-min lookahead (3 x 5-min buckets)
                    LEAD(high, 1) OVER (ORDER BY bucket) AS next_5min_high,
                    LEAD(high, 2) OVER (ORDER BY bucket) AS next_10min_high,
                    LEAD(high, 3) OVER (ORDER BY bucket) AS next_15min_high
                FROM price_5min
            ),
            drops AS (
                SELECT
                    bucket,
                    price,
                    price_30min_ago,
                    (price - price_30min_ago) / NULLIF(price_30min_ago, 0) * 100 AS drop_pct,
                    -- Max bounce in next 15 min
                    GREATEST(
                        COALESCE(next_5min_high, 0),
                        COALESCE(next_10min_high, 0),
                        COALESCE(next_15min_high, 0)
                    ) AS max_next_15min_high,
                    price AS low_point
                FROM with_context
                WHERE price_30min_ago IS NOT NULL
                  AND (price - price_30min_ago) / NULLIF(price_30min_ago, 0) * 100 < -0.5
            )
            SELECT
                CASE
                    WHEN drop_pct < -2.0 THEN 'CRASH (>-2%)'
                    WHEN drop_pct < -1.0 THEN 'STRONG_DROP (-1 to -2%)'
                    ELSE 'MILD_DROP (-0.5 to -1%)'
                END AS drop_severity,
                COUNT(*) AS drop_events,
                -- Bounce = price rises 0.3%+ from low within 15 min
                COUNT(*) FILTER (
                    WHERE (max_next_15min_high - low_point) / NULLIF(low_point, 0) * 100 > 0.3
                ) AS bounced_03,
                COUNT(*) FILTER (
                    WHERE (max_next_15min_high - low_point) / NULLIF(low_point, 0) * 100 > 0.5
                ) AS bounced_05,
                COUNT(*) FILTER (
                    WHERE (max_next_15min_high - low_point) / NULLIF(low_point, 0) * 100 > 1.0
                ) AS bounced_10,
                AVG((max_next_15min_high - low_point) / NULLIF(low_point, 0) * 100) AS avg_bounce_pct
            FROM drops
            GROUP BY drop_severity
            ORDER BY drop_severity
        """, (ticker,))

        if not rows:
            continue

        print(f"  {ticker}:")
        print(f"  {'Drop Severity':<24} {'Events':>7} {'0.3% Bounce':>12} {'0.5% Bounce':>12} {'1.0% Bounce':>12} {'Avg Bounce':>11}")
        print(f"  {'-'*82}")
        for r in rows:
            severity, events = r[0], r[1]
            b03, b05, b10 = r[2] or 0, r[3] or 0, r[4] or 0
            avg_b = float(r[5] or 0)
            pct03 = b03 / events * 100 if events > 0 else 0
            pct05 = b05 / events * 100 if events > 0 else 0
            pct10 = b10 / events * 100 if events > 0 else 0
            print(f"  {severity:<24} {events:>7} {b03:>5} ({pct03:>4.0f}%) {b05:>5} ({pct05:>4.0f}%) {b10:>5} ({pct10:>4.0f}%) {avg_b:>+10.3f}%")
        print()


# ===================================================================
# D3: Funding Rate Dynamics During Downtrends
# ===================================================================
def d3_funding_dynamics(conn):
    print("\n" + "=" * 80)
    print("D3: FUNDING RATE DYNAMICS DURING DOWNTRENDS")
    print("=" * 80)
    print("  When funding goes extremely negative, does it predict a bounce?")
    print("  Cross-references price movement after extreme funding readings.\n")

    for ticker in TICKERS:
        rows = q(conn, """
            WITH scans AS (
                SELECT
                    timestamp,
                    eth_price,
                    funding_rate,
                    funding_regime,
                    LEAD(eth_price, 5) OVER (ORDER BY timestamp) AS price_5min_later,
                    LEAD(eth_price, 15) OVER (ORDER BY timestamp) AS price_15min_later,
                    LEAD(eth_price, 30) OVER (ORDER BY timestamp) AS price_30min_later,
                    LEAD(eth_price, 60) OVER (ORDER BY timestamp) AS price_60min_later
                FROM agape_spot_scan_activity
                WHERE ticker = %s
                  AND eth_price IS NOT NULL AND eth_price > 0
                  AND funding_rate IS NOT NULL
                  AND timestamp > NOW() - INTERVAL '14 days'
            )
            SELECT
                CASE
                    WHEN funding_rate < -0.01 THEN 'VERY_NEGATIVE (<-1%)'
                    WHEN funding_rate < -0.001 THEN 'NEGATIVE (-1% to -0.1%)'
                    WHEN funding_rate < 0.001 THEN 'NEUTRAL'
                    WHEN funding_rate < 0.01 THEN 'POSITIVE (+0.1% to +1%)'
                    ELSE 'VERY_POSITIVE (>+1%)'
                END AS regime,
                COUNT(*) AS readings,
                AVG((price_5min_later - eth_price) / NULLIF(eth_price, 0) * 100) AS avg_5min_return,
                AVG((price_15min_later - eth_price) / NULLIF(eth_price, 0) * 100) AS avg_15min_return,
                AVG((price_30min_later - eth_price) / NULLIF(eth_price, 0) * 100) AS avg_30min_return,
                AVG((price_60min_later - eth_price) / NULLIF(eth_price, 0) * 100) AS avg_60min_return,
                -- % of times price was higher 15 min later
                COUNT(*) FILTER (WHERE price_15min_later > eth_price)::FLOAT / NULLIF(COUNT(*), 0) * 100 AS pct_up_15min
            FROM scans
            WHERE price_5min_later IS NOT NULL
            GROUP BY regime
            ORDER BY AVG(funding_rate) NULLS FIRST
        """, (ticker,))

        if not rows:
            continue

        print(f"  {ticker} — Forward Returns by Funding Rate:")
        print(f"  {'Funding Regime':<26} {'Readings':>9} {'5min Ret':>9} {'15min Ret':>10} {'30min Ret':>10} {'60min Ret':>10} {'%Up 15m':>8}")
        print(f"  {'-'*88}")
        for r in rows:
            regime, readings = r[0], r[1]
            r5, r15, r30, r60 = [float(x or 0) for x in r[2:6]]
            pct_up = float(r[6] or 0)
            print(f"  {regime:<26} {readings:>9} {r5:>+8.4f}% {r15:>+9.4f}% {r30:>+9.4f}% {r60:>+9.4f}% {pct_up:>7.1f}%")
        print()


# ===================================================================
# D4: Time-of-Day Effect on Downtrend Bounces
# ===================================================================
def d4_time_of_day_bounces(conn):
    print("\n" + "=" * 80)
    print("D4: TIME-OF-DAY EFFECT ON PRICE MOMENTUM (CT)")
    print("=" * 80)
    print("  Average forward 15-min return by hour of day.\n")

    rows = q(conn, """
        WITH scans AS (
            SELECT
                EXTRACT(HOUR FROM timestamp AT TIME ZONE 'America/Chicago') AS hour_ct,
                eth_price,
                LEAD(eth_price, 15) OVER (PARTITION BY ticker ORDER BY timestamp) AS price_15m_later
            FROM agape_spot_scan_activity
            WHERE ticker = 'ETH-USD'
              AND eth_price IS NOT NULL AND eth_price > 0
              AND timestamp > NOW() - INTERVAL '14 days'
        )
        SELECT
            hour_ct,
            COUNT(*) AS readings,
            AVG((price_15m_later - eth_price) / NULLIF(eth_price, 0) * 100) AS avg_15min_return,
            COUNT(*) FILTER (WHERE price_15m_later > eth_price)::FLOAT / NULLIF(COUNT(*), 0) * 100 AS pct_up
        FROM scans
        WHERE price_15m_later IS NOT NULL
        GROUP BY hour_ct
        ORDER BY hour_ct
    """)

    if not rows:
        print("  No data")
        return

    print(f"  ETH-USD — Avg 15-min forward return by hour (CT):")
    print(f"  {'Hour':>6} {'Readings':>9} {'Avg Return':>11} {'% Up':>7}  Visual")
    print(f"  {'-'*55}")
    for r in rows:
        hour, readings = int(r[0]), r[1]
        avg_ret = float(r[2] or 0)
        pct_up = float(r[3] or 0)
        bar_len = min(int(abs(avg_ret) * 500), 25)
        visual = ("+" * bar_len) if avg_ret >= 0 else ("-" * bar_len)
        print(f"  {hour:>2}:00 {readings:>9} {avg_ret:>+10.4f}% {pct_up:>6.1f}%  {visual}")


# ===================================================================
# D5: Combined Signal Distribution During Price Drops
# ===================================================================
def d5_signal_during_drops(conn):
    print("\n" + "=" * 80)
    print("D5: COMBINED SIGNAL DISTRIBUTION DURING PRICE DROPS")
    print("=" * 80)
    print("  What signals does the system generate when price is falling?\n")

    rows = q(conn, """
        WITH scans_with_change AS (
            SELECT
                ticker,
                combined_signal,
                combined_confidence,
                signal_action,
                eth_price,
                LAG(eth_price, 10) OVER (PARTITION BY ticker ORDER BY timestamp) AS price_10min_ago,
                (eth_price - LAG(eth_price, 10) OVER (PARTITION BY ticker ORDER BY timestamp))
                    / NULLIF(LAG(eth_price, 10) OVER (PARTITION BY ticker ORDER BY timestamp), 0) * 100 AS pct_change_10min
            FROM agape_spot_scan_activity
            WHERE eth_price IS NOT NULL AND eth_price > 0
              AND timestamp > NOW() - INTERVAL '14 days'
        )
        SELECT
            ticker,
            combined_signal,
            signal_action,
            COUNT(*) AS readings,
            AVG(pct_change_10min) AS avg_10min_change
        FROM scans_with_change
        WHERE pct_change_10min IS NOT NULL
          AND pct_change_10min < -0.3
        GROUP BY ticker, combined_signal, signal_action
        HAVING COUNT(*) >= 5
        ORDER BY ticker, COUNT(*) DESC
    """)

    if not rows:
        print("  No data")
        return

    print(f"  Signals generated when price was dropping (>-0.3% in 10 min):")
    print(f"  {'Ticker':<12} {'Combined Signal':<20} {'Signal Action':<15} {'Count':>7} {'Avg Drop':>10}")
    print(f"  {'-'*70}")
    for r in rows:
        ticker, signal, action, count, avg_drop = r[0], r[1] or "NULL", r[2] or "NULL", r[3], float(r[4] or 0)
        print(f"  {ticker:<12} {signal:<20} {action:<15} {count:>7} {avg_drop:>+9.3f}%")


# ===================================================================
# D6: Recovery Speed After Drawdowns
# ===================================================================
def d6_recovery_speed(conn):
    print("\n" + "=" * 80)
    print("D6: RECOVERY SPEED AFTER DRAWDOWNS")
    print("=" * 80)
    print("  How long does it take to recover from different drawdown depths?\n")

    for ticker in ["ETH-USD", "BTC-USD"]:
        rows = q(conn, """
            WITH price_5min AS (
                SELECT
                    date_trunc('hour', timestamp) +
                        INTERVAL '5 min' * FLOOR(EXTRACT(MINUTE FROM timestamp) / 5) AS bucket,
                    AVG(eth_price) AS price
                FROM agape_spot_scan_activity
                WHERE ticker = %s
                  AND eth_price IS NOT NULL AND eth_price > 0
                  AND timestamp > NOW() - INTERVAL '14 days'
                GROUP BY bucket
                ORDER BY bucket
            ),
            with_peak AS (
                SELECT
                    bucket,
                    price,
                    MAX(price) OVER (ORDER BY bucket ROWS BETWEEN 12 PRECEDING AND CURRENT ROW) AS local_peak_1h,
                    (price - MAX(price) OVER (ORDER BY bucket ROWS BETWEEN 12 PRECEDING AND CURRENT ROW))
                        / NULLIF(MAX(price) OVER (ORDER BY bucket ROWS BETWEEN 12 PRECEDING AND CURRENT ROW), 0) * 100 AS drawdown_pct,
                    -- Look ahead: does price recover to peak within next hour?
                    MAX(price) OVER (ORDER BY bucket ROWS BETWEEN CURRENT ROW AND 12 FOLLOWING) AS max_next_1h
                FROM price_5min
            )
            SELECT
                CASE
                    WHEN drawdown_pct < -2.0 THEN 'DEEP (>-2%)'
                    WHEN drawdown_pct < -1.0 THEN 'MODERATE (-1 to -2%)'
                    WHEN drawdown_pct < -0.5 THEN 'MILD (-0.5 to -1%)'
                    ELSE 'SHALLOW (<-0.5%)'
                END AS depth,
                COUNT(*) AS events,
                -- % that recovered to at least the local peak within 1h
                COUNT(*) FILTER (WHERE max_next_1h >= local_peak_1h * 0.998)::FLOAT
                    / NULLIF(COUNT(*), 0) * 100 AS full_recovery_pct,
                -- % that bounced at least 0.3% from bottom
                COUNT(*) FILTER (WHERE (max_next_1h - price) / NULLIF(price, 0) * 100 > 0.3)::FLOAT
                    / NULLIF(COUNT(*), 0) * 100 AS bounce_03_pct,
                AVG((max_next_1h - price) / NULLIF(price, 0) * 100) AS avg_recovery_pct
            FROM with_peak
            WHERE drawdown_pct < -0.3
            GROUP BY depth
            ORDER BY AVG(drawdown_pct) ASC
        """, (ticker,))

        if not rows:
            continue

        print(f"  {ticker} — Recovery within 1 hour of hitting drawdown low:")
        print(f"  {'Depth':<22} {'Events':>7} {'Full Recover':>13} {'0.3% Bounce':>12} {'Avg Recovery':>13}")
        print(f"  {'-'*72}")
        for r in rows:
            depth, events = r[0], r[1]
            full_rec = float(r[2] or 0)
            bounce = float(r[3] or 0)
            avg_rec = float(r[4] or 0)
            print(f"  {depth:<22} {events:>7} {full_rec:>11.1f}% {bounce:>10.1f}% {avg_rec:>+12.4f}%")
        print()


# ===================================================================
# D7: Mean-Reversion Window Analysis
# ===================================================================
def d7_mean_reversion_window(conn):
    print("\n" + "=" * 80)
    print("D7: MEAN-REVERSION OPPORTUNITY WINDOWS")
    print("=" * 80)
    print("  For each ticker: if you bought every time price dropped X% from")
    print("  its 1-hour high and sold after Y minutes, what's the edge?\n")

    for ticker in ["ETH-USD", "BTC-USD"]:
        rows = q(conn, """
            WITH price_5min AS (
                SELECT
                    date_trunc('hour', timestamp) +
                        INTERVAL '5 min' * FLOOR(EXTRACT(MINUTE FROM timestamp) / 5) AS bucket,
                    AVG(eth_price) AS price
                FROM agape_spot_scan_activity
                WHERE ticker = %s
                  AND eth_price IS NOT NULL AND eth_price > 0
                  AND timestamp > NOW() - INTERVAL '14 days'
                GROUP BY bucket
                ORDER BY bucket
            ),
            with_context AS (
                SELECT
                    bucket,
                    price,
                    MAX(price) OVER (ORDER BY bucket ROWS BETWEEN 12 PRECEDING AND CURRENT ROW) AS peak_1h,
                    (price - MAX(price) OVER (ORDER BY bucket ROWS BETWEEN 12 PRECEDING AND CURRENT ROW))
                        / NULLIF(MAX(price) OVER (ORDER BY bucket ROWS BETWEEN 12 PRECEDING AND CURRENT ROW), 0) * 100 AS drop_from_peak,
                    LEAD(price, 3) OVER (ORDER BY bucket) AS price_15m_later,
                    LEAD(price, 6) OVER (ORDER BY bucket) AS price_30m_later,
                    LEAD(price, 12) OVER (ORDER BY bucket) AS price_1h_later
                FROM price_5min
            )
            SELECT
                CASE
                    WHEN drop_from_peak < -1.5 THEN 'Drop > -1.5%'
                    WHEN drop_from_peak < -1.0 THEN 'Drop -1.0 to -1.5%'
                    WHEN drop_from_peak < -0.5 THEN 'Drop -0.5 to -1.0%'
                    ELSE 'Drop < -0.5%'
                END AS entry_threshold,
                COUNT(*) AS entries,
                -- 15-min return after entry
                AVG((price_15m_later - price) / NULLIF(price, 0) * 100) AS avg_15m_ret,
                COUNT(*) FILTER (WHERE price_15m_later > price)::FLOAT / NULLIF(COUNT(*), 0) * 100 AS pct_up_15m,
                -- 30-min return
                AVG((price_30m_later - price) / NULLIF(price, 0) * 100) AS avg_30m_ret,
                COUNT(*) FILTER (WHERE price_30m_later > price)::FLOAT / NULLIF(COUNT(*), 0) * 100 AS pct_up_30m,
                -- 1-hour return
                AVG((price_1h_later - price) / NULLIF(price, 0) * 100) AS avg_1h_ret,
                COUNT(*) FILTER (WHERE price_1h_later > price)::FLOAT / NULLIF(COUNT(*), 0) * 100 AS pct_up_1h
            FROM with_context
            WHERE drop_from_peak < -0.3
              AND price_15m_later IS NOT NULL
            GROUP BY entry_threshold
            ORDER BY AVG(drop_from_peak) ASC
        """, (ticker,))

        if not rows:
            continue

        print(f"  {ticker} — Mean-Reversion: Buy on dip from 1h peak, hold for N min:")
        print(f"  {'Entry Trigger':<22} {'Events':>7}  |  {'15m Ret':>8} {'%Up':>6}  |  {'30m Ret':>8} {'%Up':>6}  |  {'1h Ret':>8} {'%Up':>6}")
        print(f"  {'-'*90}")
        for r in rows:
            entry, events = r[0], r[1]
            r15, up15 = float(r[2] or 0), float(r[3] or 0)
            r30, up30 = float(r[4] or 0), float(r[5] or 0)
            r1h, up1h = float(r[6] or 0), float(r[7] or 0)
            # Flag if the edge survives 0.8% round-trip fees
            survives_15 = " EDGE!" if r15 > 0.4 and up15 > 55 else ""
            survives_30 = " EDGE!" if r30 > 0.4 and up30 > 55 else ""
            print(f"  {entry:<22} {events:>7}  |  {r15:>+7.3f}% {up15:>5.1f}%  |  {r30:>+7.3f}% {up30:>5.1f}%  |  {r1h:>+7.3f}% {up1h:>5.1f}%{survives_15}{survives_30}")
        print()


# ===================================================================
# D8: Downtrend Duration and Magnitude Distribution
# ===================================================================
def d8_downtrend_duration(conn):
    print("\n" + "=" * 80)
    print("D8: DOWNTREND DURATION & MAGNITUDE (ETH-USD)")
    print("=" * 80)
    print("  How long do downtrends last and how deep do they go?")
    print("  Uses 15-min price data with SMA-20 crossover for regime detection.\n")

    rows = q(conn, """
        WITH price_15min AS (
            SELECT
                date_trunc('hour', timestamp) +
                    INTERVAL '15 min' * FLOOR(EXTRACT(MINUTE FROM timestamp) / 15) AS bucket,
                AVG(eth_price) AS price
            FROM agape_spot_scan_activity
            WHERE ticker = 'ETH-USD'
              AND eth_price IS NOT NULL AND eth_price > 0
              AND timestamp > NOW() - INTERVAL '14 days'
            GROUP BY bucket
            ORDER BY bucket
        ),
        with_sma AS (
            SELECT
                bucket,
                price,
                AVG(price) OVER (ORDER BY bucket ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS sma_20,
                ROW_NUMBER() OVER (ORDER BY bucket) AS rn
            FROM price_15min
        )
        SELECT
            CASE WHEN price < sma_20 THEN 'BELOW_SMA20' ELSE 'ABOVE_SMA20' END AS regime,
            COUNT(*) AS periods,
            AVG(price) AS avg_price,
            AVG((price - sma_20) / NULLIF(sma_20, 0) * 100) AS avg_distance_pct
        FROM with_sma
        WHERE sma_20 IS NOT NULL
        GROUP BY regime
    """)

    if rows:
        print(f"  ETH-USD Price vs SMA-20 (15-min):")
        for r in rows:
            regime, periods, avg_price, avg_dist = r[0], r[1], float(r[2]), float(r[3] or 0)
            print(f"    {regime}: {periods} periods, avg distance = {avg_dist:+.3f}%")
    print()


# ===================================================================
# D9: Bounce Reliability by Ticker
# ===================================================================
def d9_ticker_bounce_comparison(conn):
    print("\n" + "=" * 80)
    print("D9: BOUNCE RELIABILITY COMPARISON — ALL TICKERS")
    print("=" * 80)
    print("  After a >-0.5% drop in 30 min, which ticker bounces most reliably?\n")

    results = []
    for ticker in TICKERS:
        rows = q(conn, """
            WITH price_5min AS (
                SELECT
                    date_trunc('hour', timestamp) +
                        INTERVAL '5 min' * FLOOR(EXTRACT(MINUTE FROM timestamp) / 5) AS bucket,
                    AVG(eth_price) AS price
                FROM agape_spot_scan_activity
                WHERE ticker = %s
                  AND eth_price IS NOT NULL AND eth_price > 0
                  AND timestamp > NOW() - INTERVAL '14 days'
                GROUP BY bucket
                HAVING COUNT(*) >= 2
                ORDER BY bucket
            ),
            with_context AS (
                SELECT
                    bucket,
                    price,
                    LAG(price, 6) OVER (ORDER BY bucket) AS price_30m_ago,
                    (price - LAG(price, 6) OVER (ORDER BY bucket))
                        / NULLIF(LAG(price, 6) OVER (ORDER BY bucket), 0) * 100 AS drop_30m,
                    MAX(price) OVER (ORDER BY bucket ROWS BETWEEN CURRENT ROW AND 6 FOLLOWING) AS max_next_30m
                FROM price_5min
            )
            SELECT
                COUNT(*) AS drop_events,
                COUNT(*) FILTER (
                    WHERE (max_next_30m - price) / NULLIF(price, 0) * 100 > 0.3
                ) AS bounced,
                AVG((max_next_30m - price) / NULLIF(price, 0) * 100) AS avg_bounce
            FROM with_context
            WHERE drop_30m IS NOT NULL AND drop_30m < -0.5
        """, (ticker,))

        if rows and rows[0][0] > 0:
            events, bounced, avg_b = rows[0][0], rows[0][1] or 0, float(rows[0][2] or 0)
            bounce_rate = bounced / events * 100 if events > 0 else 0
            results.append((ticker, events, bounced, bounce_rate, avg_b))

    if results:
        results.sort(key=lambda x: x[3], reverse=True)
        print(f"  {'Ticker':<12} {'Drop Events':>12} {'Bounced 0.3%':>13} {'Bounce Rate':>12} {'Avg Bounce':>11}")
        print(f"  {'-'*65}")
        for r in results:
            print(f"  {r[0]:<12} {r[1]:>12} {r[2]:>13} {r[3]:>11.1f}% {r[4]:>+10.3f}%")
    else:
        print("  No data")


# ===================================================================
# MAIN
# ===================================================================
def main():
    print("=" * 80)
    print("  PHASE 2A: DOWNTREND PATTERN ANALYSIS — AGAPE-SPOT")
    print(f"  Generated: {datetime.now(CENTRAL_TZ).strftime('%Y-%m-%d %H:%M:%S CT')}")
    print("=" * 80)

    conn = get_db_connection()

    # Check scan data availability
    count = q(conn, """
        SELECT COUNT(*), MIN(timestamp), MAX(timestamp)
        FROM agape_spot_scan_activity
        WHERE eth_price IS NOT NULL AND eth_price > 0
    """)
    if count and count[0][0] > 0:
        print(f"\n  Scan data: {count[0][0]:,} readings from {count[0][1]} to {count[0][2]}")
    else:
        print("\n  No scan data available. Run AGAPE-SPOT first to collect data.")
        conn.close()
        return

    d1_downtrend_identification(conn)
    d2_bounce_analysis(conn)
    d3_funding_dynamics(conn)
    d4_time_of_day_bounces(conn)
    d5_signal_during_drops(conn)
    d6_recovery_speed(conn)
    d7_mean_reversion_window(conn)
    d8_downtrend_duration(conn)
    d9_ticker_bounce_comparison(conn)

    conn.close()

    print("\n" + "=" * 80)
    print("  PHASE 2A COMPLETE")
    print("  Key findings to use for strategy design in Phase 3:")
    print("  1. Which drop severity has the best bounce rate?")
    print("  2. Does extreme negative funding predict bounces?")
    print("  3. Which hours have the best forward returns?")
    print("  4. What is the optimal hold time after a mean-reversion entry?")
    print("  Next: Use findings to design strategies in Phase 3 prompts")
    print("=" * 80)


if __name__ == "__main__":
    main()
