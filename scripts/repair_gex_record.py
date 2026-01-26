#!/usr/bin/env python3
"""
GEX Record Repair Script

Fixes incomplete GEX history records (net_gex=0, regime=None).
These records occur when collection fails mid-process.

Usage:
    python scripts/repair_gex_record.py
    python scripts/repair_gex_record.py --dry-run
    python scripts/repair_gex_record.py --date 2026-01-25

CREATED: January 2026
"""

import os
import sys
import argparse
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database_adapter import get_connection

CENTRAL_TZ = ZoneInfo("America/Chicago")


def find_incomplete_records(limit: int = 10):
    """Find GEX records with incomplete data"""
    conn = get_connection()
    if not conn:
        print("❌ Cannot connect to database")
        return []

    try:
        c = conn.cursor()
        c.execute('''
            SELECT id, timestamp, symbol, net_gex, regime, flip_point, data_source
            FROM gex_history
            WHERE (net_gex = 0 OR net_gex IS NULL OR regime IS NULL)
            ORDER BY timestamp DESC
            LIMIT %s
        ''', (limit,))

        records = []
        for row in c.fetchall():
            records.append({
                'id': row[0],
                'timestamp': row[1],
                'symbol': row[2],
                'net_gex': row[3],
                'regime': row[4],
                'flip_point': row[5],
                'data_source': row[6]
            })

        conn.close()
        return records
    except Exception as e:
        print(f"❌ Error finding incomplete records: {e}")
        conn.close()
        return []


def fetch_fresh_gex(symbol: str = 'SPY'):
    """Fetch fresh GEX data from TradingVolatility API"""
    try:
        from gamma.gex_history_snapshot_job import get_gex_data_from_api
        return get_gex_data_from_api(symbol)
    except ImportError:
        print("  ⚠️ Cannot import GEX data fetcher")
        return None
    except Exception as e:
        print(f"  ❌ Error fetching GEX data: {e}")
        return None


def repair_record(record_id: int, gex_data: dict, dry_run: bool = False):
    """Repair an incomplete GEX record with fresh data"""
    if dry_run:
        print(f"  [DRY RUN] Would update record {record_id}")
        return True

    conn = get_connection()
    if not conn:
        return False

    try:
        c = conn.cursor()

        net_gex = gex_data.get('net_gex', 0)
        flip_point = gex_data.get('flip_point', gex_data.get('spot_price', 0))
        spot_price = gex_data.get('spot_price', 0)
        call_wall = gex_data.get('call_wall')
        put_wall = gex_data.get('put_wall')

        # Determine regime
        if net_gex > 1e9:
            regime = 'POSITIVE'
        elif net_gex < -1e9:
            regime = 'NEGATIVE'
        else:
            regime = 'NEUTRAL'

        # Determine MM state
        mm_state = 'LONG_GAMMA' if spot_price > flip_point else 'SHORT_GAMMA'

        c.execute('''
            UPDATE gex_history SET
                net_gex = %s,
                flip_point = %s,
                spot_price = %s,
                call_wall = %s,
                put_wall = %s,
                regime = %s,
                mm_state = %s,
                data_source = %s
            WHERE id = %s
        ''', (net_gex, flip_point, spot_price, call_wall, put_wall,
              regime, mm_state, 'Repaired', record_id))

        conn.commit()
        conn.close()
        return True

    except Exception as e:
        print(f"  ❌ Error repairing record: {e}")
        conn.close()
        return False


def delete_record(record_id: int, dry_run: bool = False):
    """Delete an incomplete GEX record that can't be repaired"""
    if dry_run:
        print(f"  [DRY RUN] Would delete record {record_id}")
        return True

    conn = get_connection()
    if not conn:
        return False

    try:
        c = conn.cursor()
        c.execute('DELETE FROM gex_history WHERE id = %s', (record_id,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"  ❌ Error deleting record: {e}")
        conn.close()
        return False


def repair_by_date(date_str: str, dry_run: bool = False):
    """Repair all incomplete records for a specific date"""
    conn = get_connection()
    if not conn:
        print("❌ Cannot connect to database")
        return

    try:
        c = conn.cursor()
        c.execute('''
            SELECT id, timestamp, symbol, net_gex, regime
            FROM gex_history
            WHERE DATE(timestamp) = %s
            AND (net_gex = 0 OR net_gex IS NULL OR regime IS NULL)
        ''', (date_str,))

        records = c.fetchall()
        conn.close()

        if not records:
            print(f"✅ No incomplete records found for {date_str}")
            return

        print(f"Found {len(records)} incomplete records for {date_str}")

        # Try to get fresh data
        gex_data = fetch_fresh_gex('SPY')

        if gex_data and gex_data.get('net_gex'):
            print(f"  Got fresh GEX data: net_gex={gex_data.get('net_gex'):.2e}")
            for record in records:
                record_id = record[0]
                if repair_record(record_id, gex_data, dry_run):
                    print(f"  ✅ Repaired record {record_id}")
                else:
                    print(f"  ❌ Failed to repair record {record_id}")
        else:
            print("  ⚠️ Cannot fetch fresh GEX data - deleting incomplete records")
            for record in records:
                record_id = record[0]
                if delete_record(record_id, dry_run):
                    print(f"  🗑️ Deleted incomplete record {record_id}")
                else:
                    print(f"  ❌ Failed to delete record {record_id}")

    except Exception as e:
        print(f"❌ Error: {e}")


def run_repair(dry_run: bool = False, specific_date: str = None):
    """Main repair function"""
    print("=" * 70)
    print("GEX RECORD REPAIR")
    print("=" * 70)

    if specific_date:
        repair_by_date(specific_date, dry_run)
    else:
        # Find and show all incomplete records
        incomplete = find_incomplete_records(20)

        if not incomplete:
            print("✅ No incomplete GEX records found!")
            print("=" * 70)
            return

        print(f"\n📋 Found {len(incomplete)} incomplete records:\n")

        for rec in incomplete:
            ts = rec['timestamp'].strftime('%Y-%m-%d %H:%M') if rec['timestamp'] else 'Unknown'
            print(f"  ID {rec['id']}: {ts} - {rec['symbol']}")
            print(f"      net_gex={rec['net_gex']}, regime={rec['regime']}")

        # Try to repair with fresh data
        print(f"\n🔧 Attempting repair...")

        gex_data = fetch_fresh_gex('SPY')

        if gex_data and gex_data.get('net_gex'):
            print(f"  Got fresh GEX data: net_gex={gex_data.get('net_gex'):.2e}")

            repaired = 0
            for rec in incomplete:
                if repair_record(rec['id'], gex_data, dry_run):
                    repaired += 1
                    status = "[DRY RUN] Would repair" if dry_run else "Repaired"
                    print(f"  ✅ {status} record {rec['id']}")

            print(f"\n✅ Repaired {repaired}/{len(incomplete)} records")
        else:
            print("  ⚠️ Cannot fetch fresh GEX data")
            print("  Option: Delete incomplete records with --delete flag")

    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(description='Repair incomplete GEX history records')
    parser.add_argument('--dry-run', action='store_true',
                        help='Preview changes without making them')
    parser.add_argument('--date', type=str,
                        help='Repair records for specific date (YYYY-MM-DD)')
    parser.add_argument('--delete', action='store_true',
                        help='Delete records that cannot be repaired')

    args = parser.parse_args()

    run_repair(dry_run=args.dry_run, specific_date=args.date)


if __name__ == "__main__":
    main()
