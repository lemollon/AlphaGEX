#!/usr/bin/env python3
"""
COMPREHENSIVE PROFITABILITY ANALYSIS: ATHENA, ICARUS, TITAN
============================================================
Analyzes why these bots have not been profitable by examining:
1. Trade win/loss distribution
2. P&L patterns by day of week
3. P&L patterns by VIX regime
4. P&L patterns by GEX regime
5. Entry timing analysis
6. Direction accuracy (for directional bots)
7. Strike selection effectiveness

Run: python scripts/analyze_unprofitable_bots.py
"""

import os
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CENTRAL_TZ = ZoneInfo("America/Chicago")

BOT_CONFIGS = {
    'athena': {
        'table': 'athena_positions',
        'type': 'directional',
        'underlying': 'SPY',
        'pnl_formula': 'debit',  # (close_price - entry_debit) * contracts * 100
        'columns': {
            'entry_price': 'entry_debit',
            'close_price': 'close_price',
            'direction': 'spread_type',
            'underlying_at_entry': 'underlying_at_entry',
        }
    },
    'icarus': {
        'table': 'icarus_positions',
        'type': 'directional',
        'underlying': 'SPY',
        'pnl_formula': 'debit',
        'columns': {
            'entry_price': 'entry_debit',
            'close_price': 'close_price',
            'direction': 'spread_type',
            'underlying_at_entry': 'underlying_at_entry',
        }
    },
    'titan': {
        'table': 'titan_positions',
        'type': 'iron_condor',
        'underlying': 'SPX',
        'pnl_formula': 'credit',  # (total_credit - close_price) * contracts * 100
        'columns': {
            'entry_price': 'total_credit',
            'close_price': 'close_price',
            'underlying_at_entry': 'underlying_at_entry',
        }
    }
}


def get_db_connection():
    """Get database connection"""
    try:
        from database_adapter import get_connection
        return get_connection()
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        sys.exit(1)


def analyze_bot(conn, bot_name, config):
    """Comprehensive analysis for a single bot"""
    cursor = conn.cursor()
    table = config['table']

    print("\n" + "=" * 80)
    print(f"📊 {bot_name.upper()} PROFITABILITY ANALYSIS")
    print("=" * 80)

    # 1. Check if table exists
    cursor.execute(f"""
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_name = '{table}'
        )
    """)
    if not cursor.fetchone()[0]:
        print(f"  ❌ Table {table} does not exist")
        return None

    results = {
        'bot': bot_name,
        'summary': {},
        'by_day': {},
        'by_direction': {},
        'by_vix': {},
        'by_gex_regime': {},
        'by_hour': {},
        'losing_trades': [],
        'winning_trades': []
    }

    # 2. Overall Summary
    print("\n" + "-" * 60)
    print("1. OVERALL SUMMARY")
    print("-" * 60)

    cursor.execute(f"""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN status IN ('closed', 'expired') THEN 1 ELSE 0 END) as closed,
            SUM(CASE WHEN status = 'open' THEN 1 ELSE 0 END) as open,
            SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN realized_pnl < 0 THEN 1 ELSE 0 END) as losses,
            SUM(CASE WHEN realized_pnl = 0 THEN 1 ELSE 0 END) as breakeven,
            SUM(CASE WHEN realized_pnl IS NULL AND status IN ('closed', 'expired') THEN 1 ELSE 0 END) as null_pnl,
            COALESCE(SUM(realized_pnl), 0) as total_pnl,
            COALESCE(AVG(realized_pnl), 0) as avg_pnl,
            COALESCE(MAX(realized_pnl), 0) as max_win,
            COALESCE(MIN(realized_pnl), 0) as max_loss
        FROM {table}
    """)
    row = cursor.fetchone()
    total, closed, open_count, wins, losses, breakeven, null_pnl, total_pnl, avg_pnl, max_win, max_loss = row

    wins = wins or 0
    losses = losses or 0
    closed = closed or 0

    win_rate = (wins / closed * 100) if closed > 0 else 0

    results['summary'] = {
        'total_trades': total,
        'closed': closed,
        'open': open_count,
        'wins': wins,
        'losses': losses,
        'win_rate': win_rate,
        'total_pnl': float(total_pnl or 0),
        'avg_pnl': float(avg_pnl or 0),
        'max_win': float(max_win or 0),
        'max_loss': float(max_loss or 0),
        'null_pnl_count': null_pnl or 0
    }

    print(f"  Total trades: {total}")
    print(f"  Closed/Expired: {closed}")
    print(f"  Currently Open: {open_count}")
    print(f"  Wins: {wins} | Losses: {losses} | Breakeven: {breakeven}")
    print(f"  Win Rate: {win_rate:.1f}%")
    print(f"  Total P&L: ${float(total_pnl or 0):,.2f}")
    print(f"  Avg P&L per trade: ${float(avg_pnl or 0):,.2f}")
    print(f"  Max Win: ${float(max_win or 0):,.2f}")
    print(f"  Max Loss: ${float(max_loss or 0):,.2f}")
    if null_pnl and null_pnl > 0:
        print(f"  ⚠️  Trades with NULL P&L: {null_pnl}")

    # 3. P&L by Day of Week
    print("\n" + "-" * 60)
    print("2. P&L BY DAY OF WEEK")
    print("-" * 60)

    cursor.execute(f"""
        SELECT
            EXTRACT(DOW FROM COALESCE(open_time, close_time)::timestamptz) as dow,
            TO_CHAR(COALESCE(open_time, close_time)::timestamptz, 'Day') as day_name,
            COUNT(*) as count,
            SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN realized_pnl < 0 THEN 1 ELSE 0 END) as losses,
            COALESCE(SUM(realized_pnl), 0) as total_pnl,
            COALESCE(AVG(realized_pnl), 0) as avg_pnl
        FROM {table}
        WHERE status IN ('closed', 'expired')
        AND realized_pnl IS NOT NULL
        GROUP BY EXTRACT(DOW FROM COALESCE(open_time, close_time)::timestamptz),
                 TO_CHAR(COALESCE(open_time, close_time)::timestamptz, 'Day')
        ORDER BY dow
    """)

    day_results = cursor.fetchall()
    if day_results:
        print(f"  {'Day':<12} {'Count':>6} {'Wins':>6} {'Losses':>6} {'Win%':>7} {'Total P&L':>12} {'Avg P&L':>10}")
        print("  " + "-" * 65)
        for row in day_results:
            dow, day_name, count, wins, losses, total_pnl, avg_pnl = row
            wins = wins or 0
            losses = losses or 0
            wr = (wins / count * 100) if count > 0 else 0
            day_name = (day_name or '').strip()
            print(f"  {day_name:<12} {count:>6} {wins:>6} {losses:>6} {wr:>6.1f}% ${float(total_pnl):>10,.2f} ${float(avg_pnl):>8,.2f}")
            results['by_day'][day_name] = {
                'count': count, 'wins': wins, 'losses': losses,
                'win_rate': wr, 'total_pnl': float(total_pnl), 'avg_pnl': float(avg_pnl)
            }
    else:
        print("  No closed trades with P&L data")

    # 4. P&L by Direction (for directional bots)
    if config['type'] == 'directional' and 'direction' in config['columns']:
        print("\n" + "-" * 60)
        print("3. P&L BY DIRECTION")
        print("-" * 60)

        direction_col = config['columns']['direction']
        cursor.execute(f"""
            SELECT
                {direction_col} as direction,
                COUNT(*) as count,
                SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN realized_pnl < 0 THEN 1 ELSE 0 END) as losses,
                COALESCE(SUM(realized_pnl), 0) as total_pnl,
                COALESCE(AVG(realized_pnl), 0) as avg_pnl
            FROM {table}
            WHERE status IN ('closed', 'expired')
            AND realized_pnl IS NOT NULL
            GROUP BY {direction_col}
            ORDER BY count DESC
        """)

        dir_results = cursor.fetchall()
        if dir_results:
            print(f"  {'Direction':<15} {'Count':>6} {'Wins':>6} {'Losses':>6} {'Win%':>7} {'Total P&L':>12} {'Avg P&L':>10}")
            print("  " + "-" * 70)
            for row in dir_results:
                direction, count, wins, losses, total_pnl, avg_pnl = row
                wins = wins or 0
                losses = losses or 0
                wr = (wins / count * 100) if count > 0 else 0
                print(f"  {direction or 'Unknown':<15} {count:>6} {wins:>6} {losses:>6} {wr:>6.1f}% ${float(total_pnl):>10,.2f} ${float(avg_pnl):>8,.2f}")
                results['by_direction'][direction] = {
                    'count': count, 'wins': wins, 'losses': losses,
                    'win_rate': wr, 'total_pnl': float(total_pnl), 'avg_pnl': float(avg_pnl)
                }

    # 5. P&L by VIX Level at Entry
    print("\n" + "-" * 60)
    print("4. P&L BY VIX LEVEL AT ENTRY")
    print("-" * 60)

    cursor.execute(f"""
        SELECT
            CASE
                WHEN vix_at_entry < 15 THEN 'Low (<15)'
                WHEN vix_at_entry BETWEEN 15 AND 20 THEN 'Normal (15-20)'
                WHEN vix_at_entry BETWEEN 20 AND 25 THEN 'Elevated (20-25)'
                WHEN vix_at_entry BETWEEN 25 AND 30 THEN 'High (25-30)'
                WHEN vix_at_entry > 30 THEN 'Extreme (>30)'
                ELSE 'Unknown'
            END as vix_bucket,
            COUNT(*) as count,
            SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN realized_pnl < 0 THEN 1 ELSE 0 END) as losses,
            COALESCE(SUM(realized_pnl), 0) as total_pnl,
            COALESCE(AVG(realized_pnl), 0) as avg_pnl,
            AVG(vix_at_entry) as avg_vix
        FROM {table}
        WHERE status IN ('closed', 'expired')
        AND realized_pnl IS NOT NULL
        GROUP BY CASE
                WHEN vix_at_entry < 15 THEN 'Low (<15)'
                WHEN vix_at_entry BETWEEN 15 AND 20 THEN 'Normal (15-20)'
                WHEN vix_at_entry BETWEEN 20 AND 25 THEN 'Elevated (20-25)'
                WHEN vix_at_entry BETWEEN 25 AND 30 THEN 'High (25-30)'
                WHEN vix_at_entry > 30 THEN 'Extreme (>30)'
                ELSE 'Unknown'
            END
        ORDER BY avg_vix
    """)

    vix_results = cursor.fetchall()
    if vix_results:
        print(f"  {'VIX Level':<18} {'Count':>6} {'Wins':>6} {'Losses':>6} {'Win%':>7} {'Total P&L':>12} {'Avg P&L':>10}")
        print("  " + "-" * 70)
        for row in vix_results:
            vix_bucket, count, wins, losses, total_pnl, avg_pnl, avg_vix = row
            wins = wins or 0
            losses = losses or 0
            wr = (wins / count * 100) if count > 0 else 0
            print(f"  {vix_bucket:<18} {count:>6} {wins:>6} {losses:>6} {wr:>6.1f}% ${float(total_pnl):>10,.2f} ${float(avg_pnl):>8,.2f}")
            results['by_vix'][vix_bucket] = {
                'count': count, 'wins': wins, 'losses': losses,
                'win_rate': wr, 'total_pnl': float(total_pnl), 'avg_pnl': float(avg_pnl)
            }
    else:
        print("  No VIX data available")

    # 6. P&L by GEX Regime
    print("\n" + "-" * 60)
    print("5. P&L BY GEX REGIME")
    print("-" * 60)

    cursor.execute(f"""
        SELECT
            COALESCE(gex_regime, 'Unknown') as regime,
            COUNT(*) as count,
            SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN realized_pnl < 0 THEN 1 ELSE 0 END) as losses,
            COALESCE(SUM(realized_pnl), 0) as total_pnl,
            COALESCE(AVG(realized_pnl), 0) as avg_pnl
        FROM {table}
        WHERE status IN ('closed', 'expired')
        AND realized_pnl IS NOT NULL
        GROUP BY COALESCE(gex_regime, 'Unknown')
        ORDER BY count DESC
    """)

    gex_results = cursor.fetchall()
    if gex_results:
        print(f"  {'GEX Regime':<20} {'Count':>6} {'Wins':>6} {'Losses':>6} {'Win%':>7} {'Total P&L':>12} {'Avg P&L':>10}")
        print("  " + "-" * 72)
        for row in gex_results:
            regime, count, wins, losses, total_pnl, avg_pnl = row
            wins = wins or 0
            losses = losses or 0
            wr = (wins / count * 100) if count > 0 else 0
            print(f"  {regime:<20} {count:>6} {wins:>6} {losses:>6} {wr:>6.1f}% ${float(total_pnl):>10,.2f} ${float(avg_pnl):>8,.2f}")
            results['by_gex_regime'][regime] = {
                'count': count, 'wins': wins, 'losses': losses,
                'win_rate': wr, 'total_pnl': float(total_pnl), 'avg_pnl': float(avg_pnl)
            }
    else:
        print("  No GEX regime data available")

    # 7. P&L by Entry Hour
    print("\n" + "-" * 60)
    print("6. P&L BY ENTRY HOUR (CT)")
    print("-" * 60)

    cursor.execute(f"""
        SELECT
            EXTRACT(HOUR FROM open_time::timestamptz AT TIME ZONE 'America/Chicago') as hour,
            COUNT(*) as count,
            SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN realized_pnl < 0 THEN 1 ELSE 0 END) as losses,
            COALESCE(SUM(realized_pnl), 0) as total_pnl,
            COALESCE(AVG(realized_pnl), 0) as avg_pnl
        FROM {table}
        WHERE status IN ('closed', 'expired')
        AND realized_pnl IS NOT NULL
        AND open_time IS NOT NULL
        GROUP BY EXTRACT(HOUR FROM open_time::timestamptz AT TIME ZONE 'America/Chicago')
        ORDER BY hour
    """)

    hour_results = cursor.fetchall()
    if hour_results:
        print(f"  {'Hour (CT)':<12} {'Count':>6} {'Wins':>6} {'Losses':>6} {'Win%':>7} {'Total P&L':>12} {'Avg P&L':>10}")
        print("  " + "-" * 65)
        for row in hour_results:
            hour, count, wins, losses, total_pnl, avg_pnl = row
            wins = wins or 0
            losses = losses or 0
            wr = (wins / count * 100) if count > 0 else 0
            hour_str = f"{int(hour):02d}:00"
            print(f"  {hour_str:<12} {count:>6} {wins:>6} {losses:>6} {wr:>6.1f}% ${float(total_pnl):>10,.2f} ${float(avg_pnl):>8,.2f}")
            results['by_hour'][hour_str] = {
                'count': count, 'wins': wins, 'losses': losses,
                'win_rate': wr, 'total_pnl': float(total_pnl), 'avg_pnl': float(avg_pnl)
            }
    else:
        print("  No entry time data available")

    # 8. Biggest Losses Analysis
    print("\n" + "-" * 60)
    print("7. TOP 10 BIGGEST LOSSES")
    print("-" * 60)

    cursor.execute(f"""
        SELECT
            position_id,
            DATE(open_time) as trade_date,
            TO_CHAR(open_time::timestamptz AT TIME ZONE 'America/Chicago', 'Dy') as day,
            EXTRACT(HOUR FROM open_time::timestamptz AT TIME ZONE 'America/Chicago') as hour,
            realized_pnl,
            vix_at_entry,
            gex_regime,
            {'spread_type' if config['type'] == 'directional' else "'IC'" } as direction,
            underlying_at_entry
        FROM {table}
        WHERE status IN ('closed', 'expired')
        AND realized_pnl < 0
        ORDER BY realized_pnl ASC
        LIMIT 10
    """)

    loss_results = cursor.fetchall()
    if loss_results:
        print(f"  {'Date':<12} {'Day':<5} {'Hour':>5} {'P&L':>12} {'VIX':>6} {'GEX Regime':<15} {'Direction':<12}")
        print("  " + "-" * 75)
        for row in loss_results:
            pos_id, trade_date, day, hour, pnl, vix, gex_regime, direction, underlying = row
            vix_str = f"{float(vix):.1f}" if vix else "N/A"
            print(f"  {str(trade_date):<12} {day:<5} {int(hour or 0):>5} ${float(pnl):>10,.2f} {vix_str:>6} {gex_regime or 'N/A':<15} {direction or 'N/A':<12}")
            results['losing_trades'].append({
                'date': str(trade_date), 'day': day, 'hour': int(hour or 0),
                'pnl': float(pnl), 'vix': float(vix or 0), 'gex_regime': gex_regime,
                'direction': direction, 'underlying': float(underlying or 0)
            })
    else:
        print("  No losing trades found")

    # 9. Oracle Confidence vs Outcome
    print("\n" + "-" * 60)
    print("8. ORACLE CONFIDENCE VS OUTCOME")
    print("-" * 60)

    cursor.execute(f"""
        SELECT
            CASE
                WHEN oracle_confidence < 0.4 THEN 'Low (<40%)'
                WHEN oracle_confidence BETWEEN 0.4 AND 0.6 THEN 'Medium (40-60%)'
                WHEN oracle_confidence BETWEEN 0.6 AND 0.8 THEN 'High (60-80%)'
                WHEN oracle_confidence > 0.8 THEN 'Very High (>80%)'
                ELSE 'Unknown'
            END as confidence_bucket,
            COUNT(*) as count,
            SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN realized_pnl < 0 THEN 1 ELSE 0 END) as losses,
            COALESCE(SUM(realized_pnl), 0) as total_pnl,
            COALESCE(AVG(realized_pnl), 0) as avg_pnl,
            AVG(oracle_confidence) as avg_conf
        FROM {table}
        WHERE status IN ('closed', 'expired')
        AND realized_pnl IS NOT NULL
        GROUP BY CASE
                WHEN oracle_confidence < 0.4 THEN 'Low (<40%)'
                WHEN oracle_confidence BETWEEN 0.4 AND 0.6 THEN 'Medium (40-60%)'
                WHEN oracle_confidence BETWEEN 0.6 AND 0.8 THEN 'High (60-80%)'
                WHEN oracle_confidence > 0.8 THEN 'Very High (>80%)'
                ELSE 'Unknown'
            END
        ORDER BY avg_conf NULLS LAST
    """)

    conf_results = cursor.fetchall()
    if conf_results:
        print(f"  {'Confidence':<20} {'Count':>6} {'Wins':>6} {'Losses':>6} {'Win%':>7} {'Total P&L':>12} {'Avg P&L':>10}")
        print("  " + "-" * 72)
        for row in conf_results:
            bucket, count, wins, losses, total_pnl, avg_pnl, avg_conf = row
            wins = wins or 0
            losses = losses or 0
            wr = (wins / count * 100) if count > 0 else 0
            print(f"  {bucket:<20} {count:>6} {wins:>6} {losses:>6} {wr:>6.1f}% ${float(total_pnl):>10,.2f} ${float(avg_pnl):>8,.2f}")
    else:
        print("  No oracle confidence data available")

    # 10. Recent Trend (Last 20 trades)
    print("\n" + "-" * 60)
    print("9. RECENT TREND (Last 20 Closed Trades)")
    print("-" * 60)

    cursor.execute(f"""
        SELECT
            DATE(COALESCE(close_time, open_time)) as trade_date,
            realized_pnl,
            vix_at_entry,
            gex_regime,
            {'spread_type' if config['type'] == 'directional' else "'IC'" } as direction
        FROM {table}
        WHERE status IN ('closed', 'expired')
        AND realized_pnl IS NOT NULL
        ORDER BY COALESCE(close_time, open_time) DESC
        LIMIT 20
    """)

    recent = cursor.fetchall()
    if recent:
        running_pnl = 0
        wins = sum(1 for r in recent if r[1] and r[1] > 0)
        losses = sum(1 for r in recent if r[1] and r[1] < 0)
        total = sum(float(r[1] or 0) for r in recent)

        print(f"  Last 20: {wins}W / {losses}L | Total: ${total:,.2f}")
        print(f"\n  {'Date':<12} {'P&L':>10} {'Running':>10} {'VIX':>6} {'GEX Regime':<15}")
        print("  " + "-" * 60)

        # Reverse to show oldest first (for running total)
        for row in reversed(recent):
            trade_date, pnl, vix, gex_regime, direction = row
            pnl = float(pnl or 0)
            running_pnl += pnl
            vix_str = f"{float(vix):.1f}" if vix else "N/A"
            marker = "✅" if pnl > 0 else "❌" if pnl < 0 else "➖"
            print(f"  {str(trade_date):<12} ${pnl:>8,.2f} ${running_pnl:>8,.2f} {vix_str:>6} {gex_regime or 'N/A':<15} {marker}")
    else:
        print("  No recent closed trades")

    # 11. Oracle Win Probability Correlation
    print("\n" + "-" * 60)
    print("10. ORACLE WIN PROBABILITY VS ACTUAL OUTCOME")
    print("-" * 60)

    try:
        # Correlate Oracle win probability predictions with actual outcomes
        cursor.execute(f"""
            SELECT
                CASE
                    WHEN oracle_confidence < 0.45 THEN 'Very Low (<45%)'
                    WHEN oracle_confidence BETWEEN 0.45 AND 0.55 THEN 'Low (45-55%)'
                    WHEN oracle_confidence BETWEEN 0.55 AND 0.65 THEN 'Medium (55-65%)'
                    WHEN oracle_confidence BETWEEN 0.65 AND 0.75 THEN 'High (65-75%)'
                    WHEN oracle_confidence > 0.75 THEN 'Very High (>75%)'
                    ELSE 'Unknown'
                END as wp_bucket,
                COUNT(*) as count,
                SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as actual_wins,
                SUM(CASE WHEN realized_pnl <= 0 THEN 1 ELSE 0 END) as actual_losses,
                AVG(oracle_confidence) as avg_predicted_wp,
                COALESCE(AVG(realized_pnl), 0) as avg_pnl
            FROM {table}
            WHERE status IN ('closed', 'expired')
            AND realized_pnl IS NOT NULL
            AND oracle_confidence IS NOT NULL
            GROUP BY CASE
                    WHEN oracle_confidence < 0.45 THEN 'Very Low (<45%)'
                    WHEN oracle_confidence BETWEEN 0.45 AND 0.55 THEN 'Low (45-55%)'
                    WHEN oracle_confidence BETWEEN 0.55 AND 0.65 THEN 'Medium (55-65%)'
                    WHEN oracle_confidence BETWEEN 0.65 AND 0.75 THEN 'High (65-75%)'
                    WHEN oracle_confidence > 0.75 THEN 'Very High (>75%)'
                    ELSE 'Unknown'
                END
            ORDER BY avg_predicted_wp NULLS LAST
        """)

        wp_results = cursor.fetchall()
        if wp_results:
            print(f"  {'Predicted WP':<18} {'Count':>6} {'Wins':>6} {'Losses':>6} {'Actual WR':>10} {'Pred Avg':>10} {'Avg P&L':>10}")
            print("  " + "-" * 78)
            for row in wp_results:
                bucket, count, wins, losses, avg_wp, avg_pnl = row
                wins = wins or 0
                losses = losses or 0
                actual_wr = (wins / count * 100) if count > 0 else 0
                avg_wp_pct = float(avg_wp or 0) * 100
                calibration = "✅" if abs(actual_wr - avg_wp_pct) < 10 else "⚠️"
                print(f"  {bucket:<18} {count:>6} {wins:>6} {losses:>6} {actual_wr:>8.1f}% {avg_wp_pct:>8.1f}% ${float(avg_pnl):>8,.2f} {calibration}")
        else:
            print("  No Oracle win probability data available")
    except Exception as e:
        print(f"  Error: {e}")

    # 12. Scan Activity Analysis - Why trades are being skipped
    print("\n" + "-" * 60)
    print("11. SCAN ACTIVITY - WHY TRADES ARE SKIPPED")
    print("-" * 60)

    try:
        cursor.execute("""
            SELECT
                outcome,
                COUNT(*) as count
            FROM scan_activity
            WHERE bot_name = %s
            AND timestamp > NOW() - INTERVAL '30 days'
            GROUP BY outcome
            ORDER BY count DESC
        """, (bot_name.upper(),))

        outcomes = cursor.fetchall()
        if outcomes:
            total_scans = sum(o[1] for o in outcomes)
            print(f"  Total scans (30d): {total_scans}")
            print(f"  {'Outcome':<20} {'Count':>8} {'Percentage':>12}")
            print("  " + "-" * 45)
            for outcome, count in outcomes:
                pct = count / total_scans * 100 if total_scans > 0 else 0
                print(f"  {outcome:<20} {count:>8} {pct:>10.1f}%")

        # Most common skip reasons
        print("\n  Most Common Skip Reasons:")
        print("  " + "-" * 45)

        cursor.execute("""
            SELECT
                LEFT(decision_summary, 60) as reason,
                COUNT(*) as count
            FROM scan_activity
            WHERE bot_name = %s
            AND outcome = 'NO_TRADE'
            AND timestamp > NOW() - INTERVAL '30 days'
            GROUP BY LEFT(decision_summary, 60)
            ORDER BY count DESC
            LIMIT 8
        """, (bot_name.upper(),))

        reasons = cursor.fetchall()
        if reasons:
            for reason, count in reasons:
                print(f"  {count:>4}x: {reason or 'Unknown'}")
        else:
            print("  No NO_TRADE scans found")

    except Exception as e:
        print(f"  Scan activity not available: {e}")

    return results


def generate_recommendations(all_results):
    """Generate recommendations based on analysis"""
    print("\n" + "=" * 80)
    print("🎯 RECOMMENDATIONS BASED ON ANALYSIS")
    print("=" * 80)

    for bot_name, results in all_results.items():
        if not results:
            continue

        print(f"\n--- {bot_name.upper()} ---")

        summary = results['summary']

        # Overall profitability
        if summary['total_pnl'] < 0:
            print(f"  ⚠️  Overall loss of ${abs(summary['total_pnl']):,.2f}")

        # Win rate analysis
        if summary['win_rate'] < 45:
            print(f"  ⚠️  Low win rate ({summary['win_rate']:.1f}%) - consider tightening entry criteria")

        # Risk/Reward analysis
        if abs(summary['max_loss']) > 2 * summary['max_win']:
            print(f"  ⚠️  Max loss (${abs(summary['max_loss']):,.2f}) > 2x max win (${summary['max_win']:,.2f})")
            print(f"      → Consider tighter stop losses or better position sizing")

        # Day of week patterns
        by_day = results.get('by_day', {})
        worst_day = None
        worst_pnl = 0
        for day, stats in by_day.items():
            if stats['total_pnl'] < worst_pnl:
                worst_pnl = stats['total_pnl']
                worst_day = day
        if worst_day and worst_pnl < -500:
            print(f"  ⚠️  {worst_day} is worst day: ${worst_pnl:,.2f}")
            print(f"      → Consider avoiding or reducing exposure on {worst_day}")

        # VIX pattern analysis
        by_vix = results.get('by_vix', {})
        for vix_level, stats in by_vix.items():
            if stats['win_rate'] < 40 and stats['count'] >= 3:
                print(f"  ⚠️  Poor performance in VIX {vix_level}: {stats['win_rate']:.0f}% win rate")
                print(f"      → Consider avoiding trades at this VIX level")

        # GEX regime analysis
        by_gex = results.get('by_gex_regime', {})
        for regime, stats in by_gex.items():
            if stats['win_rate'] < 40 and stats['count'] >= 3:
                print(f"  ⚠️  Poor performance in {regime} regime: {stats['win_rate']:.0f}% win rate")

        # Direction analysis (for directional bots)
        by_dir = results.get('by_direction', {})
        for direction, stats in by_dir.items():
            if stats['total_pnl'] < -500:
                print(f"  ⚠️  {direction} trades losing money: ${stats['total_pnl']:,.2f}")
                print(f"      → Review direction selection logic")

        # Hour analysis
        by_hour = results.get('by_hour', {})
        for hour, stats in by_hour.items():
            if stats['win_rate'] < 35 and stats['count'] >= 3:
                print(f"  ⚠️  Avoid trading at {hour} CT: {stats['win_rate']:.0f}% win rate")

        # NULL P&L warning
        if summary.get('null_pnl_count', 0) > 0:
            print(f"  ⚠️  {summary['null_pnl_count']} trades have NULL P&L - data integrity issue")


def main():
    print("=" * 80)
    print("ATHENA, ICARUS, TITAN PROFITABILITY ANALYSIS")
    print(f"Generated: {datetime.now(CENTRAL_TZ).strftime('%Y-%m-%d %H:%M:%S CT')}")
    print("=" * 80)

    conn = get_db_connection()

    all_results = {}

    for bot_name in ['athena', 'icarus', 'titan']:
        config = BOT_CONFIGS[bot_name]
        results = analyze_bot(conn, bot_name, config)
        all_results[bot_name] = results

    # Generate recommendations
    generate_recommendations(all_results)

    conn.close()

    print("\n" + "=" * 80)
    print("ANALYSIS COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()
