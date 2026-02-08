#!/usr/bin/env python3
"""
Bot Signals Extraction Script
=============================

Extract signal generation logs from FORTRESS and ANCHOR to understand
what was happening at decision time.

Usage:
    python scripts/extract_bot_signals.py [--date YYYY-MM-DD] [--bot FORTRESS|ANCHOR|ALL]

Example:
    python scripts/extract_bot_signals.py --date 2026-02-03 --bot ALL
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CENTRAL_TZ = ZoneInfo("America/Chicago")


def get_connection():
    """Get database connection"""
    try:
        from database_adapter import get_connection
        return get_connection()
    except Exception as e:
        print(f"ERROR: Could not connect to database: {e}")
        sys.exit(1)


def get_fortress_signals(conn, target_date: str) -> list:
    """Get FORTRESS signals for a date"""
    c = conn.cursor()
    c.execute("""
        SELECT
            id,
            signal_time,
            spot_price,
            vix,
            expected_move,
            call_wall,
            put_wall,
            gex_regime,
            put_short,
            put_long,
            call_short,
            call_long,
            total_credit,
            confidence,
            was_executed,
            skip_reason,
            reasoning
        FROM fortress_signals
        WHERE DATE(signal_time::timestamptz AT TIME ZONE 'America/Chicago') = %s
        ORDER BY signal_time
    """, (target_date,))

    columns = [
        'id', 'signal_time', 'spot_price', 'vix', 'expected_move',
        'call_wall', 'put_wall', 'gex_regime', 'put_short', 'put_long',
        'call_short', 'call_long', 'total_credit', 'confidence',
        'was_executed', 'skip_reason', 'reasoning'
    ]

    signals = []
    for row in c.fetchall():
        signal = dict(zip(columns, row))
        if signal['signal_time']:
            signal['signal_time'] = signal['signal_time'].isoformat()
        signals.append(signal)

    return signals


def get_anchor_signals(conn, target_date: str) -> list:
    """Get ANCHOR signals for a date"""
    c = conn.cursor()
    c.execute("""
        SELECT
            id,
            signal_time,
            spot_price,
            vix,
            expected_move,
            put_short,
            put_long,
            call_short,
            call_long,
            total_credit,
            confidence,
            was_executed,
            skip_reason
        FROM anchor_signals
        WHERE DATE(signal_time::timestamptz AT TIME ZONE 'America/Chicago') = %s
        ORDER BY signal_time
    """, (target_date,))

    columns = [
        'id', 'signal_time', 'spot_price', 'vix', 'expected_move',
        'put_short', 'put_long', 'call_short', 'call_long',
        'total_credit', 'confidence', 'was_executed', 'skip_reason'
    ]

    signals = []
    for row in c.fetchall():
        signal = dict(zip(columns, row))
        if signal['signal_time']:
            signal['signal_time'] = signal['signal_time'].isoformat()
        signals.append(signal)

    return signals


def get_scan_activity(conn, target_date: str, bot_name: str) -> list:
    """Get scan activity logs for more detailed context"""
    table_name = f"{bot_name.lower()}_scan_activity"
    c = conn.cursor()

    # Check if table exists
    c.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_name = %s
        )
    """, (table_name,))

    if not c.fetchone()[0]:
        return []

    c.execute(f"""
        SELECT *
        FROM {table_name}
        WHERE DATE(scan_time::timestamptz AT TIME ZONE 'America/Chicago') = %s
        ORDER BY scan_time
    """, (target_date,))

    columns = [desc[0] for desc in c.description]
    results = []
    for row in c.fetchall():
        record = dict(zip(columns, row))
        # Convert datetime fields
        for key, value in record.items():
            if isinstance(value, datetime):
                record[key] = value.isoformat()
        results.append(record)

    return results


def analyze_signal(signal: dict, bot_name: str) -> dict:
    """Analyze a signal for strike width issues"""
    spot = float(signal.get('spot_price') or 0)
    em = float(signal.get('expected_move') or 0)
    put_short = float(signal.get('put_short') or 0)
    call_short = float(signal.get('call_short') or 0)
    put_wall = float(signal.get('put_wall') or 0)
    call_wall = float(signal.get('call_wall') or 0)

    analysis = {
        'signal_id': signal.get('id'),
        'time': signal.get('signal_time'),
        'executed': signal.get('was_executed'),
        'spot': spot,
        'expected_move': em,
    }

    if spot > 0 and em > 0:
        if put_short > 0:
            analysis['put_sd'] = round((spot - put_short) / em, 2)
        else:
            analysis['put_sd'] = None

        if call_short > 0:
            analysis['call_sd'] = round((call_short - spot) / em, 2)
        else:
            analysis['call_sd'] = None

        # Check GEX walls
        if put_wall > 0:
            analysis['put_wall_sd'] = round((spot - put_wall) / em, 2)
        else:
            analysis['put_wall_sd'] = None

        if call_wall > 0:
            analysis['call_wall_sd'] = round((call_wall - spot) / em, 2)
        else:
            analysis['call_wall_sd'] = None

        # Flag issues
        issues = []
        if analysis.get('put_sd') and analysis['put_sd'] < 1.0:
            issues.append(f"PUT_TOO_TIGHT ({analysis['put_sd']} SD)")
        if analysis.get('call_sd') and analysis['call_sd'] < 1.0:
            issues.append(f"CALL_TOO_TIGHT ({analysis['call_sd']} SD)")

        analysis['issues'] = issues
    else:
        analysis['put_sd'] = None
        analysis['call_sd'] = None
        analysis['issues'] = ['NO_DATA']

    return analysis


def print_signals(bot_name: str, signals: list, analyses: list):
    """Print signal analysis"""
    print(f"\n{'='*80}")
    print(f" {bot_name} SIGNALS")
    print(f"{'='*80}")

    if not signals:
        print(f"\n  No signals found")
        return

    print(f"\n  Total signals: {len(signals)}")
    executed = sum(1 for s in signals if s.get('was_executed'))
    print(f"  Executed: {executed}")

    executed_signals = [(s, a) for s, a in zip(signals, analyses) if s.get('was_executed')]

    if executed_signals:
        print(f"\n  EXECUTED SIGNALS:")
        for signal, analysis in executed_signals:
            print(f"\n  Signal #{analysis['signal_id']} at {analysis['time']}")
            print(f"    Spot: ${analysis['spot']:.2f}, EM: ${analysis['expected_move']:.2f}")
            print(f"    Put SD: {analysis.get('put_sd', 'N/A')}, Call SD: {analysis.get('call_sd', 'N/A')}")

            if analysis.get('put_wall_sd'):
                print(f"    Put Wall SD: {analysis['put_wall_sd']}, Call Wall SD: {analysis.get('call_wall_sd', 'N/A')}")

            if analysis['issues']:
                print(f"    ⚠️  ISSUES: {', '.join(analysis['issues'])}")

            if signal.get('reasoning'):
                print(f"    Reasoning: {signal['reasoning'][:200]}...")


def main():
    parser = argparse.ArgumentParser(description='Extract bot signals')
    parser.add_argument('--date', type=str, help='Date to analyze (YYYY-MM-DD)')
    parser.add_argument('--bot', type=str, default='ALL', choices=['FORTRESS', 'ANCHOR', 'ALL'])
    parser.add_argument('--json', action='store_true', help='Output as JSON')
    args = parser.parse_args()

    if args.date:
        target_date = args.date
    else:
        yesterday = datetime.now(CENTRAL_TZ) - timedelta(days=1)
        target_date = yesterday.strftime('%Y-%m-%d')

    print(f"\n{'='*80}")
    print(f" BOT SIGNALS EXTRACTION - {target_date}")
    print(f"{'='*80}")

    conn = get_connection()

    output = {'date': target_date}

    try:
        if args.bot in ['FORTRESS', 'ALL']:
            fortress_signals = get_fortress_signals(conn, target_date)
            ares_analyses = [analyze_signal(s, 'FORTRESS') for s in fortress_signals]
            output['fortress_signals'] = fortress_signals
            output['ares_analyses'] = ares_analyses

            ares_scan = get_scan_activity(conn, target_date, 'FORTRESS')
            output['fortress_scan_activity'] = ares_scan

        if args.bot in ['ANCHOR', 'ALL']:
            anchor_signals = get_anchor_signals(conn, target_date)
            anchor_analyses = [analyze_signal(s, 'ANCHOR') for s in anchor_signals]
            output['anchor_signals'] = anchor_signals
            output['anchor_analyses'] = anchor_analyses

            anchor_scan = get_scan_activity(conn, target_date, 'ANCHOR')
            output['anchor_scan_activity'] = anchor_scan

        if args.json:
            print(json.dumps(output, indent=2, default=str))
        else:
            if args.bot in ['FORTRESS', 'ALL']:
                print_signals('FORTRESS', fortress_signals, ares_analyses)
            if args.bot in ['ANCHOR', 'ALL']:
                print_signals('ANCHOR', anchor_signals, anchor_analyses)

    finally:
        conn.close()

    print(f"\n{'='*80}")
    print(f" END OF EXTRACTION")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    main()
