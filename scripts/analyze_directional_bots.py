#!/usr/bin/env python3
"""
=============================================================================
DIRECTIONAL BOTS PERFORMANCE ANALYZER
=============================================================================

Run this script in Render shell to analyze SOLOMON and GIDEON performance.

Usage (in Render shell):
    cd /opt/render/project/src
    python scripts/analyze_directional_bots.py

This script analyzes:
1. Overall win rate and P&L
2. Performance by spread type (BULL_CALL vs BEAR_PUT)
3. Performance by GEX regime (POSITIVE/NEGATIVE/NEUTRAL)
4. Performance by VIX level
5. Performance by day of week
6. Performance by entry hour
7. Performance by close reason
8. Wall distance analysis on losing trades
9. Prophet confidence vs outcome
10. Consecutive loss patterns
"""

import os
import sys
from datetime import datetime, timedelta
from collections import defaultdict

# Auto-detect Render environment
if os.path.exists('/opt/render/project/src'):
    sys.path.insert(0, '/opt/render/project/src')
else:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from database_adapter import DatabaseAdapter
except ImportError:
    print("=" * 60)
    print("ERROR: Could not import DatabaseAdapter")
    print("=" * 60)
    print("\nMake sure you're running from project root:")
    print("  cd /opt/render/project/src")
    print("  python scripts/analyze_directional_bots.py")
    sys.exit(1)


def analyze_bot(db, bot_name: str, table_name: str):
    """Analyze a single bot's performance"""
    print(f"\n{'='*80}")
    print(f" {bot_name} PERFORMANCE ANALYSIS")
    print(f"{'='*80}")

    conn = db.connect()
    cursor = conn.cursor()

    # 1. Overall Statistics
    print(f"\n--- Overall Statistics ---")
    cursor.execute(f"""
        SELECT
            COUNT(*) as total_trades,
            SUM(CASE WHEN status IN ('closed', 'expired', 'partial_close') THEN 1 ELSE 0 END) as closed_trades,
            SUM(CASE WHEN status = 'open' THEN 1 ELSE 0 END) as open_positions,
            SUM(CASE WHEN status IN ('closed', 'expired', 'partial_close') AND realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN status IN ('closed', 'expired', 'partial_close') AND realized_pnl <= 0 THEN 1 ELSE 0 END) as losses,
            COALESCE(SUM(CASE WHEN status IN ('closed', 'expired', 'partial_close') THEN realized_pnl ELSE 0 END), 0) as total_pnl,
            COALESCE(AVG(CASE WHEN status IN ('closed', 'expired', 'partial_close') AND realized_pnl > 0 THEN realized_pnl END), 0) as avg_win,
            COALESCE(AVG(CASE WHEN status IN ('closed', 'expired', 'partial_close') AND realized_pnl <= 0 THEN realized_pnl END), 0) as avg_loss
        FROM {table_name}
    """)
    row = cursor.fetchone()
    if row:
        total, closed, open_pos, wins, losses, total_pnl, avg_win, avg_loss = row
        win_rate = (wins / closed * 100) if closed > 0 else 0
        print(f"  Total Trades: {total}")
        print(f"  Open Positions: {open_pos}")
        print(f"  Closed Trades: {closed}")
        print(f"  Wins: {wins} ({win_rate:.1f}%)")
        print(f"  Losses: {losses}")
        print(f"  Total P&L: ${total_pnl:,.2f}")
        print(f"  Avg Win: ${avg_win:,.2f}")
        print(f"  Avg Loss: ${avg_loss:,.2f}")
        if avg_loss != 0:
            print(f"  Win/Loss Ratio: {abs(avg_win/avg_loss):.2f}")

    # 2. Last 30 Days Performance
    print(f"\n--- Last 30 Days Performance ---")
    cursor.execute(f"""
        SELECT
            COUNT(*) as trades,
            SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN realized_pnl <= 0 THEN 1 ELSE 0 END) as losses,
            COALESCE(SUM(realized_pnl), 0) as pnl
        FROM {table_name}
        WHERE status IN ('closed', 'expired', 'partial_close')
        AND close_time >= NOW() - INTERVAL '30 days'
    """)
    row = cursor.fetchone()
    if row:
        trades, wins, losses, pnl = row
        win_rate = (wins / trades * 100) if trades > 0 else 0
        print(f"  Trades: {trades}")
        print(f"  Win Rate: {win_rate:.1f}%")
        print(f"  P&L: ${pnl:,.2f}")

    # 3. Last 7 Days - Daily Breakdown
    print(f"\n--- Last 7 Days Daily Breakdown ---")
    cursor.execute(f"""
        SELECT
            DATE(close_time AT TIME ZONE 'America/Chicago') as trade_date,
            COUNT(*) as trades,
            SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
            COALESCE(SUM(realized_pnl), 0) as pnl
        FROM {table_name}
        WHERE status IN ('closed', 'expired', 'partial_close')
        AND close_time >= NOW() - INTERVAL '7 days'
        GROUP BY DATE(close_time AT TIME ZONE 'America/Chicago')
        ORDER BY trade_date DESC
    """)
    rows = cursor.fetchall()
    if rows:
        for trade_date, trades, wins, pnl in rows:
            win_rate = (wins / trades * 100) if trades > 0 else 0
            status = "WIN" if pnl > 0 else "LOSS"
            print(f"  {trade_date}: {trades} trades, {win_rate:.0f}% win rate, ${pnl:,.2f} ({status})")
    else:
        print("  No trades in last 7 days")

    # 4. Performance by Spread Type
    print(f"\n--- Performance by Spread Type ---")
    cursor.execute(f"""
        SELECT
            spread_type,
            COUNT(*) as trades,
            SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
            COALESCE(SUM(realized_pnl), 0) as pnl
        FROM {table_name}
        WHERE status IN ('closed', 'expired', 'partial_close')
        GROUP BY spread_type
        ORDER BY trades DESC
    """)
    rows = cursor.fetchall()
    for spread_type, trades, wins, pnl in rows:
        win_rate = (wins / trades * 100) if trades > 0 else 0
        print(f"  {spread_type}: {trades} trades, {win_rate:.1f}% win rate, ${pnl:,.2f}")

    # 5. Performance by GEX Regime
    print(f"\n--- Performance by GEX Regime ---")
    cursor.execute(f"""
        SELECT
            COALESCE(gex_regime, 'UNKNOWN') as regime,
            COUNT(*) as trades,
            SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
            COALESCE(SUM(realized_pnl), 0) as pnl
        FROM {table_name}
        WHERE status IN ('closed', 'expired', 'partial_close')
        GROUP BY gex_regime
        ORDER BY trades DESC
    """)
    rows = cursor.fetchall()
    for regime, trades, wins, pnl in rows:
        win_rate = (wins / trades * 100) if trades > 0 else 0
        print(f"  {regime}: {trades} trades, {win_rate:.1f}% win rate, ${pnl:,.2f}")

    # 6. Performance by VIX Level
    print(f"\n--- Performance by VIX Level ---")
    cursor.execute(f"""
        SELECT
            CASE
                WHEN vix_at_entry < 15 THEN 'LOW (<15)'
                WHEN vix_at_entry < 20 THEN 'NORMAL (15-20)'
                WHEN vix_at_entry < 25 THEN 'ELEVATED (20-25)'
                WHEN vix_at_entry < 30 THEN 'HIGH (25-30)'
                ELSE 'EXTREME (>30)'
            END as vix_range,
            COUNT(*) as trades,
            SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
            COALESCE(SUM(realized_pnl), 0) as pnl
        FROM {table_name}
        WHERE status IN ('closed', 'expired', 'partial_close')
        AND vix_at_entry IS NOT NULL
        GROUP BY 1
        ORDER BY
            CASE
                WHEN vix_at_entry < 15 THEN 1
                WHEN vix_at_entry < 20 THEN 2
                WHEN vix_at_entry < 25 THEN 3
                WHEN vix_at_entry < 30 THEN 4
                ELSE 5
            END
    """)
    rows = cursor.fetchall()
    for vix_range, trades, wins, pnl in rows:
        win_rate = (wins / trades * 100) if trades > 0 else 0
        print(f"  {vix_range}: {trades} trades, {win_rate:.1f}% win rate, ${pnl:,.2f}")

    # 7. Performance by Day of Week
    print(f"\n--- Performance by Day of Week ---")
    cursor.execute(f"""
        SELECT
            TO_CHAR(open_time AT TIME ZONE 'America/Chicago', 'Day') as day_name,
            EXTRACT(DOW FROM open_time AT TIME ZONE 'America/Chicago') as dow,
            COUNT(*) as trades,
            SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
            COALESCE(SUM(realized_pnl), 0) as pnl
        FROM {table_name}
        WHERE status IN ('closed', 'expired', 'partial_close')
        GROUP BY 1, 2
        ORDER BY dow
    """)
    rows = cursor.fetchall()
    for day_name, dow, trades, wins, pnl in rows:
        win_rate = (wins / trades * 100) if trades > 0 else 0
        print(f"  {day_name.strip()}: {trades} trades, {win_rate:.1f}% win rate, ${pnl:,.2f}")

    # 8. Performance by Entry Hour
    print(f"\n--- Performance by Entry Hour (CT) ---")
    cursor.execute(f"""
        SELECT
            EXTRACT(HOUR FROM open_time AT TIME ZONE 'America/Chicago') as hour,
            COUNT(*) as trades,
            SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
            COALESCE(SUM(realized_pnl), 0) as pnl
        FROM {table_name}
        WHERE status IN ('closed', 'expired', 'partial_close')
        GROUP BY 1
        ORDER BY hour
    """)
    rows = cursor.fetchall()
    for hour, trades, wins, pnl in rows:
        win_rate = (wins / trades * 100) if trades > 0 else 0
        print(f"  {int(hour):02d}:00 CT: {trades} trades, {win_rate:.1f}% win rate, ${pnl:,.2f}")

    # 9. Performance by Close Reason
    print(f"\n--- Performance by Close Reason ---")
    cursor.execute(f"""
        SELECT
            COALESCE(close_reason, 'UNKNOWN') as reason,
            COUNT(*) as trades,
            SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
            COALESCE(SUM(realized_pnl), 0) as pnl
        FROM {table_name}
        WHERE status IN ('closed', 'expired', 'partial_close')
        GROUP BY close_reason
        ORDER BY trades DESC
    """)
    rows = cursor.fetchall()
    for reason, trades, wins, pnl in rows:
        win_rate = (wins / trades * 100) if trades > 0 else 0
        print(f"  {reason}: {trades} trades, {win_rate:.1f}% win rate, ${pnl:,.2f}")

    # 10. Recent Losing Trades Analysis
    print(f"\n--- Last 10 Losing Trades (Most Recent First) ---")
    cursor.execute(f"""
        SELECT
            position_id,
            spread_type,
            long_strike,
            short_strike,
            underlying_at_entry,
            vix_at_entry,
            gex_regime,
            oracle_confidence,
            oracle_advice,
            realized_pnl,
            close_reason,
            open_time AT TIME ZONE 'America/Chicago' as open_ct,
            close_time AT TIME ZONE 'America/Chicago' as close_ct,
            trade_reasoning
        FROM {table_name}
        WHERE status IN ('closed', 'expired', 'partial_close')
        AND realized_pnl <= 0
        ORDER BY close_time DESC
        LIMIT 10
    """)
    rows = cursor.fetchall()
    if rows:
        for row in rows:
            pos_id, spread, long_s, short_s, spot, vix, regime, conf, advice, pnl, reason, open_t, close_t, reasoning = row
            print(f"\n  Position: {pos_id}")
            print(f"    {spread}: {long_s}/{short_s} (spot: ${spot:.2f})")
            print(f"    VIX: {vix:.1f}, Regime: {regime}")
            print(f"    Prophet: {advice} ({conf:.0%} conf)" if conf else f"    Prophet: {advice}")
            print(f"    P&L: ${pnl:,.2f} ({reason})")
            print(f"    Entry: {open_t}, Exit: {close_t}")
            if reasoning:
                print(f"    Reasoning: {reasoning[:100]}...")
    else:
        print("  No losing trades found")

    # 11. Wall Distance Analysis on Losses
    print(f"\n--- Wall Distance on Losing Trades ---")
    cursor.execute(f"""
        SELECT
            spread_type,
            AVG(ABS(underlying_at_entry - CASE
                WHEN spread_type LIKE 'BULL%' THEN put_wall
                ELSE call_wall
            END)) as avg_wall_distance,
            AVG(CASE
                WHEN spread_type LIKE 'BULL%' THEN (underlying_at_entry - put_wall) / underlying_at_entry * 100
                ELSE (call_wall - underlying_at_entry) / underlying_at_entry * 100
            END) as avg_wall_dist_pct,
            COUNT(*) as trades
        FROM {table_name}
        WHERE status IN ('closed', 'expired', 'partial_close')
        AND realized_pnl <= 0
        AND call_wall IS NOT NULL
        AND put_wall IS NOT NULL
        GROUP BY spread_type
    """)
    rows = cursor.fetchall()
    for spread, avg_dist, avg_pct, trades in rows:
        print(f"  {spread}: avg ${avg_dist:.2f} ({avg_pct:.2f}%) from wall on {trades} losing trades")

    # 12. Prophet Confidence vs Outcome
    print(f"\n--- Prophet Confidence vs Outcome ---")
    cursor.execute(f"""
        SELECT
            CASE
                WHEN oracle_confidence < 0.5 THEN 'LOW (<50%)'
                WHEN oracle_confidence < 0.7 THEN 'MEDIUM (50-70%)'
                WHEN oracle_confidence < 0.85 THEN 'HIGH (70-85%)'
                ELSE 'VERY HIGH (>85%)'
            END as conf_range,
            COUNT(*) as trades,
            SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
            COALESCE(SUM(realized_pnl), 0) as pnl
        FROM {table_name}
        WHERE status IN ('closed', 'expired', 'partial_close')
        AND oracle_confidence IS NOT NULL
        GROUP BY 1
        ORDER BY 1
    """)
    rows = cursor.fetchall()
    for conf_range, trades, wins, pnl in rows:
        win_rate = (wins / trades * 100) if trades > 0 else 0
        print(f"  {conf_range}: {trades} trades, {win_rate:.1f}% win rate, ${pnl:,.2f}")

    conn.close()


def compare_bots(db):
    """Compare SOLOMON and GIDEON head-to-head"""
    print(f"\n{'='*80}")
    print(f" SOLOMON vs GIDEON COMPARISON")
    print(f"{'='*80}")

    conn = db.connect()
    cursor = conn.cursor()

    # Get same-day performance comparison
    print(f"\n--- Same Day Performance (Last 30 Days) ---")
    cursor.execute("""
        WITH solomon_daily AS (
            SELECT
                DATE(close_time AT TIME ZONE 'America/Chicago') as trade_date,
                COUNT(*) as trades,
                SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END)::float / COUNT(*) * 100 as win_rate,
                SUM(realized_pnl) as pnl
            FROM solomon_positions
            WHERE status IN ('closed', 'expired', 'partial_close')
            AND close_time >= NOW() - INTERVAL '30 days'
            GROUP BY 1
        ),
        icarus_daily AS (
            SELECT
                DATE(close_time AT TIME ZONE 'America/Chicago') as trade_date,
                COUNT(*) as trades,
                SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END)::float / COUNT(*) * 100 as win_rate,
                SUM(realized_pnl) as pnl
            FROM gideon_positions
            WHERE status IN ('closed', 'expired', 'partial_close')
            AND close_time >= NOW() - INTERVAL '30 days'
            GROUP BY 1
        )
        SELECT
            COALESCE(a.trade_date, i.trade_date) as trade_date,
            a.trades as solomon_trades,
            a.win_rate as solomon_wr,
            a.pnl as solomon_pnl,
            i.trades as icarus_trades,
            i.win_rate as icarus_wr,
            i.pnl as icarus_pnl
        FROM solomon_daily a
        FULL OUTER JOIN icarus_daily i ON a.trade_date = i.trade_date
        ORDER BY trade_date DESC
        LIMIT 15
    """)
    rows = cursor.fetchall()

    print(f"  {'Date':<12} {'SOLOMON':<25} {'GIDEON':<25}")
    print(f"  {'':<12} {'Trades WR%   P&L':<25} {'Trades WR%   P&L':<25}")
    print(f"  {'-'*60}")

    for row in rows:
        date, a_tr, a_wr, a_pnl, i_tr, i_wr, i_pnl = row
        a_str = f"{a_tr or 0:>3} {a_wr or 0:>5.0f}% ${a_pnl or 0:>7,.0f}" if a_tr else "  -     -       -"
        i_str = f"{i_tr or 0:>3} {i_wr or 0:>5.0f}% ${i_pnl or 0:>7,.0f}" if i_tr else "  -     -       -"
        print(f"  {date} {a_str:<25} {i_str:<25}")

    conn.close()


def analyze_losing_patterns(db):
    """Deep dive into losing trade patterns"""
    print(f"\n{'='*80}")
    print(f" LOSING TRADE PATTERN ANALYSIS")
    print(f"{'='*80}")

    conn = db.connect()
    cursor = conn.cursor()

    for bot, table in [("SOLOMON", "solomon_positions"), ("GIDEON", "gideon_positions")]:
        print(f"\n--- {bot} Losing Trade Patterns ---")

        # Check for consecutive losses
        cursor.execute(f"""
            WITH ordered AS (
                SELECT
                    position_id,
                    close_time,
                    realized_pnl,
                    CASE WHEN realized_pnl <= 0 THEN 1 ELSE 0 END as is_loss,
                    LAG(CASE WHEN realized_pnl <= 0 THEN 1 ELSE 0 END) OVER (ORDER BY close_time) as prev_loss
                FROM {table}
                WHERE status IN ('closed', 'expired', 'partial_close')
                ORDER BY close_time
            )
            SELECT
                SUM(CASE WHEN is_loss = 1 AND prev_loss = 1 THEN 1 ELSE 0 END) as consecutive_losses,
                COUNT(*) as total_trades
            FROM ordered
        """)
        row = cursor.fetchone()
        if row:
            consec, total = row
            print(f"  Consecutive Loss Events: {consec} out of {total} trades ({consec/total*100:.1f}%)")

        # Check stop loss vs expire vs profit target
        cursor.execute(f"""
            SELECT
                close_reason,
                COUNT(*) as count,
                SUM(realized_pnl) as total_pnl,
                AVG(realized_pnl) as avg_pnl
            FROM {table}
            WHERE status IN ('closed', 'expired', 'partial_close')
            GROUP BY close_reason
            ORDER BY count DESC
        """)
        rows = cursor.fetchall()
        print(f"\n  Exit Reason Breakdown:")
        for reason, count, total_pnl, avg_pnl in rows:
            print(f"    {reason or 'UNKNOWN'}: {count} trades, total ${total_pnl:,.2f}, avg ${avg_pnl:,.2f}")

        # Time in trade for winners vs losers
        cursor.execute(f"""
            SELECT
                CASE WHEN realized_pnl > 0 THEN 'WINNER' ELSE 'LOSER' END as outcome,
                AVG(EXTRACT(EPOCH FROM (close_time - open_time)) / 60) as avg_minutes_in_trade,
                MIN(EXTRACT(EPOCH FROM (close_time - open_time)) / 60) as min_minutes,
                MAX(EXTRACT(EPOCH FROM (close_time - open_time)) / 60) as max_minutes
            FROM {table}
            WHERE status IN ('closed', 'expired', 'partial_close')
            AND close_time IS NOT NULL
            AND open_time IS NOT NULL
            GROUP BY 1
        """)
        rows = cursor.fetchall()
        print(f"\n  Time in Trade:")
        for outcome, avg_min, min_min, max_min in rows:
            print(f"    {outcome}: avg {avg_min:.0f} min (range: {min_min:.0f} - {max_min:.0f} min)")

    conn.close()


def main():
    print("=" * 80)
    print(" DIRECTIONAL BOTS PERFORMANCE ANALYSIS")
    print(f" Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S CT')}")
    print("=" * 80)

    try:
        db = DatabaseAdapter()
    except Exception as e:
        print(f"Error connecting to database: {e}")
        print("Make sure DATABASE_URL environment variable is set")
        sys.exit(1)

    # Analyze each bot
    analyze_bot(db, "SOLOMON", "solomon_positions")
    analyze_bot(db, "GIDEON", "gideon_positions")

    # Compare bots
    compare_bots(db)

    # Analyze losing patterns
    analyze_losing_patterns(db)

    print("\n" + "=" * 80)
    print(" ANALYSIS COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()
