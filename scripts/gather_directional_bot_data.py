#!/usr/bin/env python3
"""
=============================================================================
COMPREHENSIVE DIRECTIONAL BOTS DATA GATHERER
=============================================================================

Run this script in Render shell to gather ALL data about SOLOMON and ICARUS.

Usage (in Render shell):
    cd /opt/render/project/src
    python scripts/gather_directional_bot_data.py

Gathers:
- All closed trades with full context
- Win/loss breakdown by every dimension
- Oracle prediction accuracy
- Signal generation patterns
- Configuration settings
- Comparison with IC bots (FORTRESS, SAMSON, PEGASUS)
"""

import os
import sys
import json
from datetime import datetime, timedelta

# Auto-detect Render environment
if os.path.exists('/opt/render/project/src'):
    sys.path.insert(0, '/opt/render/project/src')
else:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database_adapter import DatabaseAdapter


def section_header(title: str):
    print(f"\n{'='*80}")
    print(f" {title}")
    print(f"{'='*80}")


def run_query(cursor, query: str, description: str = ""):
    """Run query and return results"""
    try:
        cursor.execute(query)
        return cursor.fetchall()
    except Exception as e:
        print(f"  Query error: {e}")
        return []


def gather_solomon_data(db):
    """Gather all SOLOMON data"""
    section_header("SOLOMON - COMPLETE DATA DUMP")

    conn = db.connect()
    cursor = conn.cursor()

    # 1. OVERALL STATS
    print("\n--- 1. OVERALL STATISTICS ---")
    rows = run_query(cursor, """
        SELECT
            COUNT(*) as total_trades,
            SUM(CASE WHEN status IN ('closed', 'expired', 'partial_close') THEN 1 ELSE 0 END) as closed,
            SUM(CASE WHEN status = 'open' THEN 1 ELSE 0 END) as open_now,
            SUM(CASE WHEN status IN ('closed', 'expired', 'partial_close') AND realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN status IN ('closed', 'expired', 'partial_close') AND realized_pnl <= 0 THEN 1 ELSE 0 END) as losses,
            COALESCE(SUM(CASE WHEN status IN ('closed', 'expired', 'partial_close') THEN realized_pnl ELSE 0 END), 0) as total_pnl,
            COALESCE(AVG(CASE WHEN status IN ('closed', 'expired', 'partial_close') AND realized_pnl > 0 THEN realized_pnl END), 0) as avg_win,
            COALESCE(AVG(CASE WHEN status IN ('closed', 'expired', 'partial_close') AND realized_pnl <= 0 THEN realized_pnl END), 0) as avg_loss,
            MIN(open_time) as first_trade,
            MAX(close_time) as last_trade
        FROM solomon_positions
    """)
    if rows and rows[0]:
        r = rows[0]
        total, closed, open_now, wins, losses, total_pnl, avg_win, avg_loss, first, last = r
        win_rate = (wins / closed * 100) if closed and closed > 0 else 0
        print(f"  Total Trades: {total}")
        print(f"  Open Now: {open_now}")
        print(f"  Closed: {closed}")
        print(f"  Wins: {wins} ({win_rate:.1f}%)")
        print(f"  Losses: {losses}")
        print(f"  Total P&L: ${total_pnl:,.2f}")
        print(f"  Avg Win: ${avg_win:,.2f}")
        print(f"  Avg Loss: ${avg_loss:,.2f}")
        if avg_loss != 0:
            print(f"  Win/Loss Ratio: {abs(avg_win/avg_loss):.2f}")
        print(f"  First Trade: {first}")
        print(f"  Last Trade: {last}")

    # 2. BY SPREAD TYPE
    print("\n--- 2. BY SPREAD TYPE ---")
    rows = run_query(cursor, """
        SELECT
            spread_type,
            COUNT(*) as trades,
            SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
            COALESCE(SUM(realized_pnl), 0) as pnl,
            COALESCE(AVG(realized_pnl), 0) as avg_pnl
        FROM solomon_positions
        WHERE status IN ('closed', 'expired', 'partial_close')
        GROUP BY spread_type
        ORDER BY trades DESC
    """)
    for row in rows:
        spread, trades, wins, pnl, avg = row
        wr = (wins / trades * 100) if trades > 0 else 0
        print(f"  {spread}: {trades} trades, {wr:.1f}% WR, ${pnl:,.2f} P&L, ${avg:,.2f} avg")

    # 3. BY GEX REGIME
    print("\n--- 3. BY GEX REGIME ---")
    rows = run_query(cursor, """
        SELECT
            COALESCE(gex_regime, 'UNKNOWN') as regime,
            COUNT(*) as trades,
            SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
            COALESCE(SUM(realized_pnl), 0) as pnl
        FROM solomon_positions
        WHERE status IN ('closed', 'expired', 'partial_close')
        GROUP BY gex_regime
        ORDER BY trades DESC
    """)
    for row in rows:
        regime, trades, wins, pnl = row
        wr = (wins / trades * 100) if trades > 0 else 0
        print(f"  {regime}: {trades} trades, {wr:.1f}% WR, ${pnl:,.2f}")

    # 4. BY VIX LEVEL
    print("\n--- 4. BY VIX LEVEL ---")
    rows = run_query(cursor, """
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
        FROM solomon_positions
        WHERE status IN ('closed', 'expired', 'partial_close')
        AND vix_at_entry IS NOT NULL
        GROUP BY 1
        ORDER BY MIN(vix_at_entry)
    """)
    for row in rows:
        vix_range, trades, wins, pnl = row
        wr = (wins / trades * 100) if trades > 0 else 0
        print(f"  {vix_range}: {trades} trades, {wr:.1f}% WR, ${pnl:,.2f}")

    # 5. BY DAY OF WEEK
    print("\n--- 5. BY DAY OF WEEK ---")
    rows = run_query(cursor, """
        SELECT
            TO_CHAR(open_time AT TIME ZONE 'America/Chicago', 'Day') as day_name,
            EXTRACT(DOW FROM open_time AT TIME ZONE 'America/Chicago') as dow,
            COUNT(*) as trades,
            SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
            COALESCE(SUM(realized_pnl), 0) as pnl
        FROM solomon_positions
        WHERE status IN ('closed', 'expired', 'partial_close')
        GROUP BY 1, 2
        ORDER BY dow
    """)
    for row in rows:
        day, dow, trades, wins, pnl = row
        wr = (wins / trades * 100) if trades > 0 else 0
        print(f"  {day.strip()}: {trades} trades, {wr:.1f}% WR, ${pnl:,.2f}")

    # 6. BY ENTRY HOUR
    print("\n--- 6. BY ENTRY HOUR (CT) ---")
    rows = run_query(cursor, """
        SELECT
            EXTRACT(HOUR FROM open_time AT TIME ZONE 'America/Chicago') as hour,
            COUNT(*) as trades,
            SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
            COALESCE(SUM(realized_pnl), 0) as pnl
        FROM solomon_positions
        WHERE status IN ('closed', 'expired', 'partial_close')
        GROUP BY 1
        ORDER BY hour
    """)
    for row in rows:
        hour, trades, wins, pnl = row
        wr = (wins / trades * 100) if trades > 0 else 0
        print(f"  {int(hour):02d}:00: {trades} trades, {wr:.1f}% WR, ${pnl:,.2f}")

    # 7. BY CLOSE REASON
    print("\n--- 7. BY CLOSE REASON ---")
    rows = run_query(cursor, """
        SELECT
            COALESCE(close_reason, 'UNKNOWN') as reason,
            COUNT(*) as trades,
            SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
            COALESCE(SUM(realized_pnl), 0) as pnl,
            COALESCE(AVG(realized_pnl), 0) as avg_pnl
        FROM solomon_positions
        WHERE status IN ('closed', 'expired', 'partial_close')
        GROUP BY close_reason
        ORDER BY trades DESC
    """)
    for row in rows:
        reason, trades, wins, pnl, avg = row
        wr = (wins / trades * 100) if trades > 0 else 0
        print(f"  {reason}: {trades} trades, {wr:.1f}% WR, ${pnl:,.2f} total, ${avg:,.2f} avg")

    # 8. BY ORACLE CONFIDENCE
    print("\n--- 8. BY ORACLE CONFIDENCE ---")
    rows = run_query(cursor, """
        SELECT
            CASE
                WHEN oracle_confidence IS NULL THEN 'NO_ORACLE'
                WHEN oracle_confidence < 0.5 THEN 'LOW (<50%)'
                WHEN oracle_confidence < 0.6 THEN 'MEDIUM (50-60%)'
                WHEN oracle_confidence < 0.7 THEN 'GOOD (60-70%)'
                WHEN oracle_confidence < 0.8 THEN 'HIGH (70-80%)'
                ELSE 'VERY HIGH (>80%)'
            END as conf_range,
            COUNT(*) as trades,
            SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
            COALESCE(SUM(realized_pnl), 0) as pnl
        FROM solomon_positions
        WHERE status IN ('closed', 'expired', 'partial_close')
        GROUP BY 1
        ORDER BY 1
    """)
    for row in rows:
        conf, trades, wins, pnl = row
        wr = (wins / trades * 100) if trades > 0 else 0
        print(f"  {conf}: {trades} trades, {wr:.1f}% WR, ${pnl:,.2f}")

    # 9. BY ORACLE ADVICE
    print("\n--- 9. BY ORACLE ADVICE ---")
    rows = run_query(cursor, """
        SELECT
            COALESCE(oracle_advice, 'UNKNOWN') as advice,
            COUNT(*) as trades,
            SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
            COALESCE(SUM(realized_pnl), 0) as pnl
        FROM solomon_positions
        WHERE status IN ('closed', 'expired', 'partial_close')
        GROUP BY oracle_advice
        ORDER BY trades DESC
    """)
    for row in rows:
        advice, trades, wins, pnl = row
        wr = (wins / trades * 100) if trades > 0 else 0
        print(f"  {advice}: {trades} trades, {wr:.1f}% WR, ${pnl:,.2f}")

    # 10. LAST 7 DAYS DAILY
    print("\n--- 10. LAST 7 DAYS DAILY ---")
    rows = run_query(cursor, """
        SELECT
            DATE(close_time AT TIME ZONE 'America/Chicago') as trade_date,
            COUNT(*) as trades,
            SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
            COALESCE(SUM(realized_pnl), 0) as pnl
        FROM solomon_positions
        WHERE status IN ('closed', 'expired', 'partial_close')
        AND close_time >= NOW() - INTERVAL '7 days'
        GROUP BY 1
        ORDER BY trade_date DESC
    """)
    for row in rows:
        date, trades, wins, pnl = row
        wr = (wins / trades * 100) if trades > 0 else 0
        status = "WIN" if pnl > 0 else "LOSS"
        print(f"  {date}: {trades} trades, {wr:.0f}% WR, ${pnl:,.2f} ({status})")

    # 11. LAST 20 TRADES DETAIL
    print("\n--- 11. LAST 20 TRADES (DETAIL) ---")
    rows = run_query(cursor, """
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
            close_time AT TIME ZONE 'America/Chicago' as close_ct
        FROM solomon_positions
        WHERE status IN ('closed', 'expired', 'partial_close')
        ORDER BY close_time DESC
        LIMIT 20
    """)
    print(f"  {'ID':<20} {'Type':<12} {'Strikes':<12} {'Spot':<8} {'VIX':<6} {'Regime':<10} {'Oracle':<8} {'P&L':<10} {'Reason':<15}")
    print(f"  {'-'*110}")
    for row in rows:
        pos_id, spread, long_s, short_s, spot, vix, regime, conf, advice, pnl, reason, open_t, close_t = row
        strikes = f"{long_s}/{short_s}"
        conf_str = f"{conf:.0%}" if conf else "N/A"
        print(f"  {pos_id[:20]:<20} {spread[:12]:<12} {strikes:<12} ${spot:<7.2f} {vix:<6.1f} {(regime or 'N/A'):<10} {conf_str:<8} ${pnl:<9.2f} {(reason or 'N/A'):<15}")

    # 12. WINNING VS LOSING TRADE CHARACTERISTICS
    print("\n--- 12. WINNING VS LOSING TRADE CHARACTERISTICS ---")
    rows = run_query(cursor, """
        SELECT
            CASE WHEN realized_pnl > 0 THEN 'WINNERS' ELSE 'LOSERS' END as outcome,
            AVG(vix_at_entry) as avg_vix,
            AVG(oracle_confidence) as avg_oracle_conf,
            AVG(EXTRACT(EPOCH FROM (close_time - open_time)) / 60) as avg_minutes_held,
            AVG(ABS(underlying_at_entry - CASE
                WHEN spread_type LIKE 'BULL%' THEN put_wall
                ELSE call_wall
            END) / NULLIF(underlying_at_entry, 0) * 100) as avg_wall_dist_pct
        FROM solomon_positions
        WHERE status IN ('closed', 'expired', 'partial_close')
        AND close_time IS NOT NULL
        GROUP BY 1
    """)
    for row in rows:
        outcome, avg_vix, avg_conf, avg_min, avg_wall = row
        print(f"  {outcome}:")
        print(f"    Avg VIX: {avg_vix:.1f}" if avg_vix else "    Avg VIX: N/A")
        print(f"    Avg Oracle Conf: {avg_conf:.1%}" if avg_conf else "    Avg Oracle Conf: N/A")
        print(f"    Avg Time Held: {avg_min:.0f} min" if avg_min else "    Avg Time Held: N/A")
        print(f"    Avg Wall Distance: {avg_wall:.2f}%" if avg_wall else "    Avg Wall Distance: N/A")

    conn.close()


def gather_icarus_data(db):
    """Gather all ICARUS data"""
    section_header("ICARUS - COMPLETE DATA DUMP")

    conn = db.connect()
    cursor = conn.cursor()

    # Same queries as SOLOMON but for icarus_positions
    # 1. OVERALL STATS
    print("\n--- 1. OVERALL STATISTICS ---")
    rows = run_query(cursor, """
        SELECT
            COUNT(*) as total_trades,
            SUM(CASE WHEN status IN ('closed', 'expired', 'partial_close') THEN 1 ELSE 0 END) as closed,
            SUM(CASE WHEN status = 'open' THEN 1 ELSE 0 END) as open_now,
            SUM(CASE WHEN status IN ('closed', 'expired', 'partial_close') AND realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN status IN ('closed', 'expired', 'partial_close') AND realized_pnl <= 0 THEN 1 ELSE 0 END) as losses,
            COALESCE(SUM(CASE WHEN status IN ('closed', 'expired', 'partial_close') THEN realized_pnl ELSE 0 END), 0) as total_pnl,
            COALESCE(AVG(CASE WHEN status IN ('closed', 'expired', 'partial_close') AND realized_pnl > 0 THEN realized_pnl END), 0) as avg_win,
            COALESCE(AVG(CASE WHEN status IN ('closed', 'expired', 'partial_close') AND realized_pnl <= 0 THEN realized_pnl END), 0) as avg_loss,
            MIN(open_time) as first_trade,
            MAX(close_time) as last_trade
        FROM icarus_positions
    """)
    if rows and rows[0]:
        r = rows[0]
        total, closed, open_now, wins, losses, total_pnl, avg_win, avg_loss, first, last = r
        win_rate = (wins / closed * 100) if closed and closed > 0 else 0
        print(f"  Total Trades: {total}")
        print(f"  Open Now: {open_now}")
        print(f"  Closed: {closed}")
        print(f"  Wins: {wins} ({win_rate:.1f}%)")
        print(f"  Losses: {losses}")
        print(f"  Total P&L: ${total_pnl:,.2f}")
        print(f"  Avg Win: ${avg_win:,.2f}")
        print(f"  Avg Loss: ${avg_loss:,.2f}")
        if avg_loss != 0:
            print(f"  Win/Loss Ratio: {abs(avg_win/avg_loss):.2f}")
        print(f"  First Trade: {first}")
        print(f"  Last Trade: {last}")

    # 2. BY SPREAD TYPE
    print("\n--- 2. BY SPREAD TYPE ---")
    rows = run_query(cursor, """
        SELECT
            spread_type,
            COUNT(*) as trades,
            SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
            COALESCE(SUM(realized_pnl), 0) as pnl,
            COALESCE(AVG(realized_pnl), 0) as avg_pnl
        FROM icarus_positions
        WHERE status IN ('closed', 'expired', 'partial_close')
        GROUP BY spread_type
        ORDER BY trades DESC
    """)
    for row in rows:
        spread, trades, wins, pnl, avg = row
        wr = (wins / trades * 100) if trades > 0 else 0
        print(f"  {spread}: {trades} trades, {wr:.1f}% WR, ${pnl:,.2f} P&L, ${avg:,.2f} avg")

    # 3. BY GEX REGIME
    print("\n--- 3. BY GEX REGIME ---")
    rows = run_query(cursor, """
        SELECT
            COALESCE(gex_regime, 'UNKNOWN') as regime,
            COUNT(*) as trades,
            SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
            COALESCE(SUM(realized_pnl), 0) as pnl
        FROM icarus_positions
        WHERE status IN ('closed', 'expired', 'partial_close')
        GROUP BY gex_regime
        ORDER BY trades DESC
    """)
    for row in rows:
        regime, trades, wins, pnl = row
        wr = (wins / trades * 100) if trades > 0 else 0
        print(f"  {regime}: {trades} trades, {wr:.1f}% WR, ${pnl:,.2f}")

    # 4. BY VIX LEVEL
    print("\n--- 4. BY VIX LEVEL ---")
    rows = run_query(cursor, """
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
        FROM icarus_positions
        WHERE status IN ('closed', 'expired', 'partial_close')
        AND vix_at_entry IS NOT NULL
        GROUP BY 1
        ORDER BY MIN(vix_at_entry)
    """)
    for row in rows:
        vix_range, trades, wins, pnl = row
        wr = (wins / trades * 100) if trades > 0 else 0
        print(f"  {vix_range}: {trades} trades, {wr:.1f}% WR, ${pnl:,.2f}")

    # 5. BY DAY OF WEEK
    print("\n--- 5. BY DAY OF WEEK ---")
    rows = run_query(cursor, """
        SELECT
            TO_CHAR(open_time AT TIME ZONE 'America/Chicago', 'Day') as day_name,
            EXTRACT(DOW FROM open_time AT TIME ZONE 'America/Chicago') as dow,
            COUNT(*) as trades,
            SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
            COALESCE(SUM(realized_pnl), 0) as pnl
        FROM icarus_positions
        WHERE status IN ('closed', 'expired', 'partial_close')
        GROUP BY 1, 2
        ORDER BY dow
    """)
    for row in rows:
        day, dow, trades, wins, pnl = row
        wr = (wins / trades * 100) if trades > 0 else 0
        print(f"  {day.strip()}: {trades} trades, {wr:.1f}% WR, ${pnl:,.2f}")

    # 6. BY ENTRY HOUR
    print("\n--- 6. BY ENTRY HOUR (CT) ---")
    rows = run_query(cursor, """
        SELECT
            EXTRACT(HOUR FROM open_time AT TIME ZONE 'America/Chicago') as hour,
            COUNT(*) as trades,
            SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
            COALESCE(SUM(realized_pnl), 0) as pnl
        FROM icarus_positions
        WHERE status IN ('closed', 'expired', 'partial_close')
        GROUP BY 1
        ORDER BY hour
    """)
    for row in rows:
        hour, trades, wins, pnl = row
        wr = (wins / trades * 100) if trades > 0 else 0
        print(f"  {int(hour):02d}:00: {trades} trades, {wr:.1f}% WR, ${pnl:,.2f}")

    # 7. BY CLOSE REASON
    print("\n--- 7. BY CLOSE REASON ---")
    rows = run_query(cursor, """
        SELECT
            COALESCE(close_reason, 'UNKNOWN') as reason,
            COUNT(*) as trades,
            SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
            COALESCE(SUM(realized_pnl), 0) as pnl,
            COALESCE(AVG(realized_pnl), 0) as avg_pnl
        FROM icarus_positions
        WHERE status IN ('closed', 'expired', 'partial_close')
        GROUP BY close_reason
        ORDER BY trades DESC
    """)
    for row in rows:
        reason, trades, wins, pnl, avg = row
        wr = (wins / trades * 100) if trades > 0 else 0
        print(f"  {reason}: {trades} trades, {wr:.1f}% WR, ${pnl:,.2f} total, ${avg:,.2f} avg")

    # 8. BY ORACLE CONFIDENCE
    print("\n--- 8. BY ORACLE CONFIDENCE ---")
    rows = run_query(cursor, """
        SELECT
            CASE
                WHEN oracle_confidence IS NULL THEN 'NO_ORACLE'
                WHEN oracle_confidence < 0.5 THEN 'LOW (<50%)'
                WHEN oracle_confidence < 0.6 THEN 'MEDIUM (50-60%)'
                WHEN oracle_confidence < 0.7 THEN 'GOOD (60-70%)'
                WHEN oracle_confidence < 0.8 THEN 'HIGH (70-80%)'
                ELSE 'VERY HIGH (>80%)'
            END as conf_range,
            COUNT(*) as trades,
            SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
            COALESCE(SUM(realized_pnl), 0) as pnl
        FROM icarus_positions
        WHERE status IN ('closed', 'expired', 'partial_close')
        GROUP BY 1
        ORDER BY 1
    """)
    for row in rows:
        conf, trades, wins, pnl = row
        wr = (wins / trades * 100) if trades > 0 else 0
        print(f"  {conf}: {trades} trades, {wr:.1f}% WR, ${pnl:,.2f}")

    # 9. BY ORACLE ADVICE
    print("\n--- 9. BY ORACLE ADVICE ---")
    rows = run_query(cursor, """
        SELECT
            COALESCE(oracle_advice, 'UNKNOWN') as advice,
            COUNT(*) as trades,
            SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
            COALESCE(SUM(realized_pnl), 0) as pnl
        FROM icarus_positions
        WHERE status IN ('closed', 'expired', 'partial_close')
        GROUP BY oracle_advice
        ORDER BY trades DESC
    """)
    for row in rows:
        advice, trades, wins, pnl = row
        wr = (wins / trades * 100) if trades > 0 else 0
        print(f"  {advice}: {trades} trades, {wr:.1f}% WR, ${pnl:,.2f}")

    # 10. LAST 7 DAYS DAILY
    print("\n--- 10. LAST 7 DAYS DAILY ---")
    rows = run_query(cursor, """
        SELECT
            DATE(close_time AT TIME ZONE 'America/Chicago') as trade_date,
            COUNT(*) as trades,
            SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
            COALESCE(SUM(realized_pnl), 0) as pnl
        FROM icarus_positions
        WHERE status IN ('closed', 'expired', 'partial_close')
        AND close_time >= NOW() - INTERVAL '7 days'
        GROUP BY 1
        ORDER BY trade_date DESC
    """)
    for row in rows:
        date, trades, wins, pnl = row
        wr = (wins / trades * 100) if trades > 0 else 0
        status = "WIN" if pnl > 0 else "LOSS"
        print(f"  {date}: {trades} trades, {wr:.0f}% WR, ${pnl:,.2f} ({status})")

    # 11. LAST 20 TRADES DETAIL
    print("\n--- 11. LAST 20 TRADES (DETAIL) ---")
    rows = run_query(cursor, """
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
            close_time AT TIME ZONE 'America/Chicago' as close_ct
        FROM icarus_positions
        WHERE status IN ('closed', 'expired', 'partial_close')
        ORDER BY close_time DESC
        LIMIT 20
    """)
    print(f"  {'ID':<20} {'Type':<12} {'Strikes':<12} {'Spot':<8} {'VIX':<6} {'Regime':<10} {'Oracle':<8} {'P&L':<10} {'Reason':<15}")
    print(f"  {'-'*110}")
    for row in rows:
        pos_id, spread, long_s, short_s, spot, vix, regime, conf, advice, pnl, reason, open_t, close_t = row
        strikes = f"{long_s}/{short_s}"
        conf_str = f"{conf:.0%}" if conf else "N/A"
        print(f"  {pos_id[:20]:<20} {spread[:12]:<12} {strikes:<12} ${spot:<7.2f} {vix:<6.1f} {(regime or 'N/A'):<10} {conf_str:<8} ${pnl:<9.2f} {(reason or 'N/A'):<15}")

    # 12. WINNING VS LOSING TRADE CHARACTERISTICS
    print("\n--- 12. WINNING VS LOSING TRADE CHARACTERISTICS ---")
    rows = run_query(cursor, """
        SELECT
            CASE WHEN realized_pnl > 0 THEN 'WINNERS' ELSE 'LOSERS' END as outcome,
            AVG(vix_at_entry) as avg_vix,
            AVG(oracle_confidence) as avg_oracle_conf,
            AVG(EXTRACT(EPOCH FROM (close_time - open_time)) / 60) as avg_minutes_held,
            AVG(ABS(underlying_at_entry - CASE
                WHEN spread_type LIKE 'BULL%' THEN put_wall
                ELSE call_wall
            END) / NULLIF(underlying_at_entry, 0) * 100) as avg_wall_dist_pct
        FROM icarus_positions
        WHERE status IN ('closed', 'expired', 'partial_close')
        AND close_time IS NOT NULL
        GROUP BY 1
    """)
    for row in rows:
        outcome, avg_vix, avg_conf, avg_min, avg_wall = row
        print(f"  {outcome}:")
        print(f"    Avg VIX: {avg_vix:.1f}" if avg_vix else "    Avg VIX: N/A")
        print(f"    Avg Oracle Conf: {avg_conf:.1%}" if avg_conf else "    Avg Oracle Conf: N/A")
        print(f"    Avg Time Held: {avg_min:.0f} min" if avg_min else "    Avg Time Held: N/A")
        print(f"    Avg Wall Distance: {avg_wall:.2f}%" if avg_wall else "    Avg Wall Distance: N/A")

    conn.close()


def gather_ic_bot_comparison(db):
    """Compare directional bots with IC bots"""
    section_header("IC BOTS COMPARISON (FORTRESS, SAMSON, PEGASUS)")

    conn = db.connect()
    cursor = conn.cursor()

    # Check each IC bot
    for bot, table in [("FORTRESS", "fortress_positions"), ("SAMSON", "samson_positions"), ("PEGASUS", "pegasus_positions")]:
        print(f"\n--- {bot} ---")
        rows = run_query(cursor, f"""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN status IN ('closed', 'expired') THEN 1 ELSE 0 END) as closed,
                SUM(CASE WHEN status IN ('closed', 'expired') AND realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
                COALESCE(SUM(CASE WHEN status IN ('closed', 'expired') THEN realized_pnl ELSE 0 END), 0) as pnl,
                COALESCE(AVG(CASE WHEN status IN ('closed', 'expired') AND realized_pnl > 0 THEN realized_pnl END), 0) as avg_win,
                COALESCE(AVG(CASE WHEN status IN ('closed', 'expired') AND realized_pnl <= 0 THEN realized_pnl END), 0) as avg_loss
            FROM {table}
        """)
        if rows and rows[0] and rows[0][0]:
            total, closed, wins, pnl, avg_win, avg_loss = rows[0]
            wr = (wins / closed * 100) if closed and closed > 0 else 0
            print(f"  Trades: {closed}, Win Rate: {wr:.1f}%, P&L: ${pnl:,.2f}")
            print(f"  Avg Win: ${avg_win:,.2f}, Avg Loss: ${avg_loss:,.2f}")
            if avg_loss != 0:
                print(f"  Win/Loss Ratio: {abs(avg_win/avg_loss):.2f}")
        else:
            print(f"  No data found")

    conn.close()


def gather_config_data(db):
    """Get current bot configurations"""
    section_header("CURRENT BOT CONFIGURATIONS")

    conn = db.connect()
    cursor = conn.cursor()

    rows = run_query(cursor, """
        SELECT bot_name, config_data, updated_at
        FROM autonomous_config
        WHERE bot_name IN ('SOLOMON', 'ICARUS')
        ORDER BY bot_name
    """)

    for row in rows:
        bot, config, updated = row
        print(f"\n--- {bot} (updated: {updated}) ---")
        if config:
            if isinstance(config, str):
                config = json.loads(config)
            for key, value in sorted(config.items()):
                print(f"  {key}: {value}")

    conn.close()


def gather_signal_data(db):
    """Get recent signal generation data"""
    section_header("RECENT SIGNALS (Last 50)")

    conn = db.connect()
    cursor = conn.cursor()

    for bot, table in [("SOLOMON", "solomon_signals"), ("ICARUS", "icarus_signals")]:
        print(f"\n--- {bot} SIGNALS ---")
        rows = run_query(cursor, f"""
            SELECT
                signal_time AT TIME ZONE 'America/Chicago' as time_ct,
                direction,
                spread_type,
                confidence,
                spot_price,
                vix,
                gex_regime,
                was_executed,
                skip_reason
            FROM {table}
            ORDER BY signal_time DESC
            LIMIT 25
        """)

        if rows:
            executed = sum(1 for r in rows if r[7])
            skipped = len(rows) - executed
            print(f"  Last 25: {executed} executed, {skipped} skipped")
            print(f"\n  {'Time':<20} {'Dir':<8} {'Type':<12} {'Conf':<6} {'Spot':<8} {'VIX':<6} {'Regime':<10} {'Exec':<5} {'Skip Reason':<30}")
            print(f"  {'-'*115}")
            for row in rows[:15]:
                time, dir, type, conf, spot, vix, regime, executed, skip = row
                time_str = time.strftime("%Y-%m-%d %H:%M") if time else "N/A"
                exec_str = "YES" if executed else "NO"
                print(f"  {time_str:<20} {(dir or 'N/A'):<8} {(type or 'N/A'):<12} {conf or 0:<6.0%} ${spot or 0:<7.2f} {vix or 0:<6.1f} {(regime or 'N/A'):<10} {exec_str:<5} {(skip or '')[:30]:<30}")
        else:
            print("  No signals found")

    conn.close()


def main():
    print("=" * 80)
    print(" COMPREHENSIVE DIRECTIONAL BOTS DATA GATHERER")
    print(f" Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    try:
        db = DatabaseAdapter()
    except Exception as e:
        print(f"\nERROR: Could not connect to database: {e}")
        print("\nMake sure DATABASE_URL is set correctly.")
        sys.exit(1)

    # Gather all data
    gather_solomon_data(db)
    gather_icarus_data(db)
    gather_ic_bot_comparison(db)
    gather_config_data(db)
    gather_signal_data(db)

    print("\n" + "=" * 80)
    print(" DATA GATHERING COMPLETE")
    print("=" * 80)
    print("\nCopy this output and share it to analyze the results.")


if __name__ == "__main__":
    main()
