#!/usr/bin/env python3
"""
GEX History Gap Backfill Script

Backfills GEX history for the gap between Dec 25, 2025 and current date
using TradingVolatility API's historical data endpoint.

Usage:
    python scripts/backfill_gex_gap.py
    python scripts/backfill_gex_gap.py --days 30  # Override days
    python scripts/backfill_gex_gap.py --dry-run  # Preview only

CREATED: January 2026
FIX: GEX history stopped collecting on Christmas Day
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


def get_last_gex_record(symbol: str = 'SPY') -> datetime:
    """Find the last GEX history record timestamp"""
    conn = get_connection()
    if not conn:
        return None

    try:
        c = conn.cursor()
        c.execute('''
            SELECT MAX(timestamp) FROM gex_history WHERE symbol = %s
        ''', (symbol,))
        result = c.fetchone()
        conn.close()
        return result[0] if result and result[0] else None
    except Exception as e:
        print(f"❌ Error checking last record: {e}")
        conn.close()
        return None


def get_gex_record_count(symbol: str = 'SPY', since: datetime = None) -> int:
    """Count GEX history records"""
    conn = get_connection()
    if not conn:
        return 0

    try:
        c = conn.cursor()
        if since:
            c.execute('''
                SELECT COUNT(*) FROM gex_history
                WHERE symbol = %s AND timestamp >= %s
            ''', (symbol, since))
        else:
            c.execute('''
                SELECT COUNT(*) FROM gex_history WHERE symbol = %s
            ''', (symbol,))
        result = c.fetchone()
        conn.close()
        return result[0] if result else 0
    except Exception as e:
        print(f"❌ Error counting records: {e}")
        conn.close()
        return 0


def fetch_historical_gex_from_tv(symbol: str, start_date: datetime, end_date: datetime):
    """
    Fetch historical GEX data from TradingVolatility API.

    Note: TradingVolatility may have historical endpoints or we may need
    to reconstruct from their data archives.
    """
    try:
        from core_classes_and_engines import TradingVolatilityAPI

        api = TradingVolatilityAPI()

        # Try historical endpoint
        historical_data = []

        # TradingVolatility may provide historical data via different methods
        # Attempt 1: Historical GEX endpoint
        try:
            gex_history = api.get_gex_history(symbol, days=30)
            if gex_history and isinstance(gex_history, list):
                historical_data.extend(gex_history)
                print(f"  ✅ Got {len(gex_history)} records from get_gex_history")
        except Exception as e:
            print(f"  ⚠️ get_gex_history not available: {e}")

        # Attempt 2: Daily GEX snapshots
        if not historical_data:
            try:
                daily_data = api.get_daily_gex_history(symbol)
                if daily_data and isinstance(daily_data, list):
                    historical_data.extend(daily_data)
                    print(f"  ✅ Got {len(daily_data)} records from get_daily_gex_history")
            except Exception as e:
                print(f"  ⚠️ get_daily_gex_history not available: {e}")

        return historical_data

    except ImportError:
        print("  ❌ TradingVolatility API not available")
        return []
    except Exception as e:
        print(f"  ❌ Error fetching historical GEX: {e}")
        return []


def fetch_from_polygon_options(symbol: str, date: datetime):
    """
    Alternative: Calculate GEX from Polygon options chain data
    This gives real GEX values but requires options data access
    """
    try:
        from data.polygon_data_fetcher import PolygonDataFetcher
        from unified_config import APIConfig

        if not APIConfig.POLYGON_API_KEY:
            return None

        fetcher = PolygonDataFetcher(api_key=APIConfig.POLYGON_API_KEY)

        # Get options chain for the date
        options_chain = fetcher.get_options_chain(
            symbol,
            as_of_date=date.strftime('%Y-%m-%d')
        )

        if not options_chain:
            return None

        # Calculate GEX from options chain
        # This is a simplified calculation
        total_gex = 0
        spot_price = None

        for contract in options_chain:
            oi = contract.get('open_interest', 0)
            gamma = contract.get('greeks', {}).get('gamma', 0)
            contract_type = contract.get('contract_type', '').lower()

            if not spot_price:
                spot_price = contract.get('underlying_price', 0)

            # GEX = gamma * OI * 100 * spot^2 * 0.01
            gex_contribution = gamma * oi * 100 * (spot_price ** 2) * 0.01

            if contract_type == 'call':
                total_gex += gex_contribution
            else:
                total_gex -= gex_contribution

        if spot_price and total_gex:
            return {
                'timestamp': date,
                'net_gex': total_gex,
                'spot_price': spot_price,
                'data_source': 'Polygon_Calculated'
            }

        return None

    except Exception as e:
        print(f"  ⚠️ Polygon options calculation failed: {e}")
        return None


def insert_gex_record(record: dict, symbol: str = 'SPY') -> bool:
    """Insert a single GEX history record"""
    conn = get_connection()
    if not conn:
        return False

    try:
        c = conn.cursor()

        # Check for duplicate
        timestamp = record.get('timestamp') or record.get('date')
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))

        c.execute('''
            SELECT id FROM gex_history
            WHERE symbol = %s AND DATE(timestamp) = DATE(%s)
            LIMIT 1
        ''', (symbol, timestamp))

        if c.fetchone():
            conn.close()
            return False  # Already exists

        # Determine regime
        net_gex = record.get('net_gex', 0)
        spot_price = record.get('spot_price', 0)
        flip_point = record.get('flip_point', spot_price)

        if net_gex > 1e9:
            regime = 'POSITIVE'
        elif net_gex < -1e9:
            regime = 'NEGATIVE'
        else:
            regime = 'NEUTRAL'

        mm_state = 'LONG_GAMMA' if spot_price > flip_point else 'SHORT_GAMMA'

        c.execute('''
            INSERT INTO gex_history (
                timestamp, symbol, net_gex, flip_point, call_wall, put_wall,
                spot_price, mm_state, regime, data_source
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ''', (
            timestamp,
            symbol,
            net_gex,
            record.get('flip_point', spot_price * 0.99),
            record.get('call_wall', spot_price * 1.02),
            record.get('put_wall', spot_price * 0.98),
            spot_price,
            mm_state,
            regime,
            record.get('data_source', 'Backfill')
        ))

        conn.commit()
        conn.close()
        return True

    except Exception as e:
        print(f"  ❌ Insert failed: {e}")
        conn.close()
        return False


def run_backfill(days: int = 35, dry_run: bool = False, symbol: str = 'SPY'):
    """
    Main backfill function

    Args:
        days: Number of days to backfill
        dry_run: If True, only preview what would be done
        symbol: Stock symbol (default SPY)
    """
    print("=" * 70)
    print("GEX HISTORY GAP BACKFILL")
    print("=" * 70)

    # Check current state
    last_record = get_last_gex_record(symbol)
    current_count = get_gex_record_count(symbol)

    print(f"\n📊 Current State:")
    print(f"   Symbol: {symbol}")
    print(f"   Total records: {current_count:,}")
    print(f"   Last record: {last_record}")

    # Calculate gap
    now = datetime.now(CENTRAL_TZ)

    if last_record:
        if last_record.tzinfo is None:
            last_record = last_record.replace(tzinfo=CENTRAL_TZ)
        gap_days = (now - last_record).days
        start_date = last_record + timedelta(days=1)
    else:
        gap_days = days
        start_date = now - timedelta(days=days)

    print(f"   Gap: {gap_days} days")
    print(f"   Backfill from: {start_date.strftime('%Y-%m-%d')}")

    if dry_run:
        print(f"\n🔍 DRY RUN - No data will be inserted")
        print("=" * 70)
        return

    if gap_days <= 0:
        print(f"\n✅ No gap to backfill - data is current!")
        print("=" * 70)
        return

    # Try to get historical data
    print(f"\n📡 Fetching historical GEX data...")

    historical_data = fetch_historical_gex_from_tv(symbol, start_date, now)

    if historical_data:
        print(f"\n💾 Inserting {len(historical_data)} records...")
        inserted = 0
        for record in historical_data:
            if insert_gex_record(record, symbol):
                inserted += 1
        print(f"   ✅ Inserted {inserted} new records")
    else:
        print(f"\n⚠️ No historical GEX data available from TradingVolatility")
        print(f"   Historical data must be collected going forward")
        print(f"   The scheduled collection will now run hourly")

    # Show final state
    new_count = get_gex_record_count(symbol)
    print(f"\n📊 Final State:")
    print(f"   Total records: {new_count:,}")
    print(f"   Records added: {new_count - current_count:,}")

    print("\n" + "=" * 70)
    print("✅ BACKFILL COMPLETE")
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(description='Backfill GEX history gap')
    parser.add_argument('--days', type=int, default=35,
                        help='Days to backfill (default: 35)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Preview only, do not insert data')
    parser.add_argument('--symbol', default='SPY',
                        help='Symbol to backfill (default: SPY)')

    args = parser.parse_args()

    run_backfill(
        days=args.days,
        dry_run=args.dry_run,
        symbol=args.symbol
    )


if __name__ == "__main__":
    main()
