#!/usr/bin/env python3
"""
GEX History Snapshot Job
Saves hourly/daily GEX snapshots for historical analysis and backtesting

Run this as a cron job or background task to accumulate GEX history over time.
"""

from datetime import datetime
from config_and_database import DB_PATH
from database_adapter import get_connection
from typing import Dict, Optional

# Try to import GEX data source
try:
    from core_classes_and_engines import TradingVolatilityAPI
    TV_API_AVAILABLE = True
except ImportError:
    TV_API_AVAILABLE = False

try:
    from gex_copilot import calculate_gex_from_options_chain
    GEX_COPILOT_AVAILABLE = True
except ImportError:
    GEX_COPILOT_AVAILABLE = False


def get_current_gex_data(symbol: str = 'SPY') -> Optional[Dict]:
    """
    Get current GEX data from available sources

    Returns:
        {
            'net_gex': float,
            'flip_point': float,
            'call_wall': float,
            'put_wall': float,
            'spot_price': float,
            'mm_state': str,  # 'LONG_GAMMA' or 'SHORT_GAMMA'
            'regime': str,    # 'POSITIVE', 'NEGATIVE', or 'NEUTRAL'
            'data_source': str
        }
    """
    # Try TradingVolatility API first
    if TV_API_AVAILABLE:
        try:
            api = TradingVolatilityAPI()
            gex_data = api.get_gex_data(symbol)

            if gex_data:
                return {
                    'net_gex': gex_data.get('net_gex', 0),
                    'flip_point': gex_data.get('flip_point', 0),
                    'call_wall': gex_data.get('call_wall', 0),
                    'put_wall': gex_data.get('put_wall', 0),
                    'spot_price': gex_data.get('spot_price', 0),
                    'mm_state': gex_data.get('mm_state', 'UNKNOWN'),
                    'regime': gex_data.get('regime', 'UNKNOWN'),
                    'data_source': 'TradingVolatility'
                }
        except Exception as e:
            print(f"⚠️  TradingVolatility API failed: {e}")

    # Fallback to local calculation
    if GEX_COPILOT_AVAILABLE:
        try:
            gex_data = calculate_gex_from_options_chain(symbol)

            if gex_data:
                # Determine regime
                net_gex = gex_data.get('net_gex', 0)
                if net_gex > 1e9:  # > $1B positive
                    regime = 'POSITIVE'
                elif net_gex < -1e9:  # < -$1B negative
                    regime = 'NEGATIVE'
                else:
                    regime = 'NEUTRAL'

                # Determine MM state
                spot = gex_data.get('spot_price', 0)
                flip = gex_data.get('flip_point', 0)
                mm_state = 'LONG_GAMMA' if spot > flip else 'SHORT_GAMMA'

                return {
                    'net_gex': net_gex,
                    'flip_point': gex_data.get('flip_point', 0),
                    'call_wall': gex_data.get('call_wall', 0),
                    'put_wall': gex_data.get('put_wall', 0),
                    'spot_price': spot,
                    'mm_state': mm_state,
                    'regime': regime,
                    'data_source': 'LocalCalculation'
                }
        except Exception as e:
            print(f"⚠️  Local GEX calculation failed: {e}")

    print("❌ No GEX data sources available")
    return None


def save_gex_snapshot(symbol: str = 'SPY') -> bool:
    """
    Take a GEX snapshot and save to database

    Returns:
        True if successful, False otherwise
    """
    try:
        # Get current GEX data
        gex_data = get_current_gex_data(symbol)

        if not gex_data:
            print("❌ Could not get GEX data")
            return False

        # Save to database
        conn = get_connection()
        c = conn.cursor()

        c.execute('''
            INSERT INTO gex_history (
                timestamp, symbol, net_gex, flip_point, call_wall, put_wall,
                spot_price, mm_state, regime, data_source
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            symbol,
            gex_data['net_gex'],
            gex_data['flip_point'],
            gex_data['call_wall'],
            gex_data['put_wall'],
            gex_data['spot_price'],
            gex_data['mm_state'],
            gex_data['regime'],
            gex_data['data_source']
        ))

        result = c.fetchone()
        snapshot_id = result[0] if result else None
        conn.commit()
        conn.close()

        print(f"✅ GEX snapshot saved (ID: {snapshot_id})")
        print(f"   Net GEX: ${gex_data['net_gex']/1e9:.2f}B")
        print(f"   Flip Point: ${gex_data['flip_point']:.2f}")
        print(f"   Spot: ${gex_data['spot_price']:.2f}")
        print(f"   Regime: {gex_data['regime']}")

        return True

    except Exception as e:
        print(f"❌ Failed to save GEX snapshot: {e}")
        import traceback
        traceback.print_exc()
        return False


def get_gex_history(symbol: str = 'SPY', days: int = 30) -> list:
    """
    Retrieve GEX history from database

    Args:
        symbol: Stock symbol
        days: How many days of history to retrieve

    Returns:
        List of GEX snapshots
    """
    try:
        conn = get_connection()
        c = conn.cursor()

        c.execute('''
            SELECT
                timestamp, net_gex, flip_point, call_wall, put_wall,
                spot_price, mm_state, regime, data_source
            FROM gex_history
            WHERE symbol = %s
            AND timestamp >= NOW() - INTERVAL '%s days'
            ORDER BY timestamp DESC
        ''', (symbol, days))

        history = []
        for row in c.fetchall():
            history.append({
                'timestamp': row[0],
                'net_gex': row[1],
                'flip_point': row[2],
                'call_wall': row[3],
                'put_wall': row[4],
                'spot_price': row[5],
                'mm_state': row[6],
                'regime': row[7],
                'data_source': row[8]
            })

        conn.close()
        return history

    except Exception as e:
        print(f"❌ Failed to get GEX history: {e}")
        return []


if __name__ == "__main__":
    print("=" * 60)
    print("GEX HISTORY SNAPSHOT JOB")
    print("=" * 60)

    # Take snapshot
    success = save_gex_snapshot('SPY')

    if success:
        # Show recent history
        history = get_gex_history('SPY', days=7)
        print(f"\n📊 Recent GEX History ({len(history)} snapshots):")

        for i, snap in enumerate(history[:5]):
            print(f"\n{i+1}. {snap['timestamp']}")
            print(f"   Net GEX: ${snap['net_gex']/1e9:.2f}B")
            print(f"   Regime: {snap['regime']}")
            print(f"   Spot: ${snap['spot_price']:.2f}")

    print("\n" + "=" * 60)
    print("✅ Job complete")
    print("=" * 60)
