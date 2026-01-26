#!/usr/bin/env python3
"""
GEX History Snapshot Job
Saves hourly/daily GEX snapshots for historical analysis and backtesting

Run this as a cron job or background task to accumulate GEX history over time.

FIXES (Jan 2026):
- Added detailed error logging for diagnostics
- Added Polygon API fallback when TradingVolatility fails
- Added collection health tracking to database
"""

from datetime import datetime
from zoneinfo import ZoneInfo
from db.config_and_database import DB_PATH
from database_adapter import get_connection
from typing import Dict, Optional
import logging
import traceback

logger = logging.getLogger(__name__)

# Texas Central Time
CENTRAL_TZ = ZoneInfo("America/Chicago")

# Try to import GEX data source
TV_API_AVAILABLE = False
try:
    from core_classes_and_engines import TradingVolatilityAPI
    TV_API_AVAILABLE = True
except ImportError as e:
    logger.warning(f"TradingVolatilityAPI not available: {e}")

GEX_COPILOT_AVAILABLE = False
try:
    from gex_copilot import calculate_gex_from_options_chain
    GEX_COPILOT_AVAILABLE = True
except ImportError as e:
    logger.warning(f"gex_copilot not available: {e}")

# Polygon fallback
POLYGON_AVAILABLE = False
try:
    from data.polygon_data_fetcher import PolygonDataFetcher
    POLYGON_AVAILABLE = True
except ImportError as e:
    logger.warning(f"PolygonDataFetcher not available: {e}")


def log_collection_attempt(symbol: str, source: str, success: bool, error: str = None):
    """Log collection attempt to database for diagnostics"""
    try:
        conn = get_connection()
        c = conn.cursor()

        # Create tracking table if not exists
        c.execute('''
            CREATE TABLE IF NOT EXISTS gex_collection_health (
                id SERIAL PRIMARY KEY,
                timestamp TIMESTAMPTZ DEFAULT NOW(),
                symbol VARCHAR(10),
                data_source VARCHAR(50),
                success BOOLEAN,
                error_message TEXT
            )
        ''')

        c.execute('''
            INSERT INTO gex_collection_health (symbol, data_source, success, error_message)
            VALUES (%s, %s, %s, %s)
        ''', (symbol, source, success, error[:500] if error else None))

        # Keep only last 7 days of health records
        c.execute('''
            DELETE FROM gex_collection_health
            WHERE timestamp < NOW() - INTERVAL '7 days'
        ''')

        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Failed to log collection health: {e}")


def get_gex_from_polygon(symbol: str) -> Optional[Dict]:
    """
    Fallback: Get GEX-like data from Polygon when TradingVolatility is unavailable.
    This provides basic price data that can be used for trend tracking.
    """
    if not POLYGON_AVAILABLE:
        return None

    try:
        from unified_config import APIConfig
        if not APIConfig.POLYGON_API_KEY:
            logger.warning("Polygon API key not configured")
            return None

        fetcher = PolygonDataFetcher(api_key=APIConfig.POLYGON_API_KEY)
        quote = fetcher.get_quote(symbol)

        if not quote:
            return None

        spot_price = quote.get('last') or quote.get('close') or 0

        # We can't calculate real GEX from Polygon, but we can provide price data
        # This allows the system to at least track price movement
        return {
            'net_gex': 0,  # Unknown without options data
            'flip_point': spot_price,  # Approximate
            'call_wall': spot_price * 1.02,  # Approximate 2% above
            'put_wall': spot_price * 0.98,  # Approximate 2% below
            'spot_price': spot_price,
            'mm_state': 'UNKNOWN',
            'regime': 'UNKNOWN',
            'data_source': 'Polygon_Fallback'
        }
    except Exception as e:
        logger.error(f"Polygon fallback failed: {e}")
        return None


def get_current_gex_data(symbol: str = 'SPY') -> Optional[Dict]:
    """
    Get current GEX data from available sources with detailed error tracking.

    Data source priority:
    1. TradingVolatility API (primary - real GEX data)
    2. Local GEX calculation (fallback)
    3. Polygon API (emergency fallback - price only)

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
    errors = []

    # Try TradingVolatility API first (primary source)
    if TV_API_AVAILABLE:
        try:
            api = TradingVolatilityAPI()
            gex_data = api.get_net_gamma(symbol)

            if gex_data and not gex_data.get('error'):
                # Determine regime from net_gex
                net_gex = gex_data.get('net_gex', 0)
                if net_gex > 1e9:
                    regime = 'POSITIVE'
                elif net_gex < -1e9:
                    regime = 'NEGATIVE'
                else:
                    regime = 'NEUTRAL'

                # Determine MM state from spot vs flip
                spot = gex_data.get('spot_price', 0)
                flip = gex_data.get('flip_point', 0)
                mm_state = 'LONG_GAMMA' if spot > flip else 'SHORT_GAMMA'

                log_collection_attempt(symbol, 'TradingVolatility', True)
                return {
                    'net_gex': net_gex,
                    'flip_point': flip,
                    'call_wall': gex_data.get('call_wall', 0),
                    'put_wall': gex_data.get('put_wall', 0),
                    'spot_price': spot,
                    'mm_state': mm_state,
                    'regime': regime,
                    'data_source': 'TradingVolatility'
                }
            else:
                error_msg = gex_data.get('error', 'No data returned') if gex_data else 'API returned None'
                errors.append(f"TradingVolatility: {error_msg}")
                logger.warning(f"TradingVolatility API returned no valid data: {error_msg}")
                log_collection_attempt(symbol, 'TradingVolatility', False, error_msg)
        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)}"
            errors.append(f"TradingVolatility: {error_msg}")
            logger.error(f"TradingVolatility API exception: {error_msg}")
            logger.debug(traceback.format_exc())
            log_collection_attempt(symbol, 'TradingVolatility', False, error_msg)
    else:
        errors.append("TradingVolatility: Module not available")

    # Fallback to local calculation
    if GEX_COPILOT_AVAILABLE:
        try:
            gex_data = calculate_gex_from_options_chain(symbol)

            if gex_data:
                # Determine regime
                net_gex = gex_data.get('net_gex', 0)
                if net_gex > 1e9:
                    regime = 'POSITIVE'
                elif net_gex < -1e9:
                    regime = 'NEGATIVE'
                else:
                    regime = 'NEUTRAL'

                # Determine MM state
                spot = gex_data.get('spot_price', 0)
                flip = gex_data.get('flip_point', 0)
                mm_state = 'LONG_GAMMA' if spot > flip else 'SHORT_GAMMA'

                log_collection_attempt(symbol, 'LocalCalculation', True)
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
            else:
                errors.append("LocalCalculation: No data returned")
                log_collection_attempt(symbol, 'LocalCalculation', False, "No data returned")
        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)}"
            errors.append(f"LocalCalculation: {error_msg}")
            logger.error(f"Local GEX calculation exception: {error_msg}")
            log_collection_attempt(symbol, 'LocalCalculation', False, error_msg)
    else:
        errors.append("LocalCalculation: Module not available")

    # Emergency fallback: Polygon API (price tracking only)
    polygon_data = get_gex_from_polygon(symbol)
    if polygon_data:
        logger.warning(f"Using Polygon fallback for {symbol} - GEX values will be approximate")
        log_collection_attempt(symbol, 'Polygon_Fallback', True, "Fallback used - no real GEX data")
        return polygon_data
    else:
        errors.append("Polygon_Fallback: Not available or failed")

    # All sources failed
    error_summary = " | ".join(errors)
    logger.error(f"❌ All GEX data sources failed for {symbol}: {error_summary}")
    log_collection_attempt(symbol, 'ALL_SOURCES', False, error_summary)
    print(f"❌ No GEX data sources available: {error_summary}")
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
            logger.error(f"Could not get GEX data for {symbol}")
            print("❌ Could not get GEX data")
            return False

        # Save to database with timezone-aware timestamp
        conn = get_connection()
        c = conn.cursor()

        # Use timezone-aware timestamp
        now_ct = datetime.now(CENTRAL_TZ)

        c.execute('''
            INSERT INTO gex_history (
                timestamp, symbol, net_gex, flip_point, call_wall, put_wall,
                spot_price, mm_state, regime, data_source
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (
            now_ct,  # Use datetime object directly for proper timezone handling
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

        net_gex_display = gex_data['net_gex'] / 1e9 if gex_data['net_gex'] != 0 else 0
        logger.info(f"GEX snapshot saved for {symbol}: ID={snapshot_id}, "
                   f"Net GEX=${net_gex_display:.2f}B, Regime={gex_data['regime']}, "
                   f"Source={gex_data['data_source']}")

        print(f"✅ GEX snapshot saved (ID: {snapshot_id})")
        print(f"   Net GEX: ${net_gex_display:.2f}B")
        print(f"   Flip Point: ${gex_data['flip_point']:.2f}")
        print(f"   Spot: ${gex_data['spot_price']:.2f}")
        print(f"   Regime: {gex_data['regime']}")
        print(f"   Source: {gex_data['data_source']}")

        return True

    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)}"
        logger.error(f"Failed to save GEX snapshot for {symbol}: {error_msg}")
        logger.debug(traceback.format_exc())
        print(f"❌ Failed to save GEX snapshot: {e}")
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
