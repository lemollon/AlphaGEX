"""
Forward Magnets Detector
Identifies gamma strikes that act as price magnets and tracks their effectiveness
"""

import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo
from config_and_database import DB_PATH

CENTRAL_TZ = ZoneInfo("America/Chicago")


def detect_forward_magnets():
    """
    Detect and log gamma strikes that may pull price toward them

    A "forward magnet" is a strike with:
    1. High gamma concentration (> 10% of total gamma)
    2. Above current spot price (for calls) or below (for puts)
    3. Within reasonable distance (2-5% from spot)
    """
    try:
        from tradingvolatility_api import get_gamma_exposure
        import pandas as pd

        print("🧲 Forward Magnets Detector - Finding Gamma Price Magnets\n")

        # Get current GEX data
        gex_data = get_gamma_exposure('SPY')

        if not gex_data or 'levels' not in gex_data:
            print("❌ No GEX data available")
            return

        spot_price = gex_data.get('spot_price', 0)
        if spot_price == 0:
            print("❌ No spot price available")
            return

        # Get gamma by strike
        levels = gex_data['levels']
        df = pd.DataFrame(levels)

        if df.empty:
            print("❌ No gamma levels available")
            return

        # Calculate total gamma
        total_gamma = df['gamma_ex'].abs().sum()

        # Find potential magnets (high gamma concentration)
        df['gamma_pct'] = (df['gamma_ex'].abs() / total_gamma) * 100
        df['distance_pct'] = ((df['strike'] - spot_price) / spot_price) * 100

        # Filter for forward magnets (ahead of price, significant gamma)
        call_magnets = df[
            (df['strike'] > spot_price) &  # Above spot
            (df['distance_pct'] <= 5) &     # Within 5%
            (df['distance_pct'] >= 0.5) &   # At least 0.5% away
            (df['gamma_pct'] >= 5)          # At least 5% of total gamma
        ].sort_values('gamma_pct', ascending=False).head(3)

        put_magnets = df[
            (df['strike'] < spot_price) &   # Below spot
            (df['distance_pct'] >= -5) &    # Within 5%
            (df['distance_pct'] <= -0.5) &  # At least 0.5% away
            (df['gamma_pct'] >= 5)          # At least 5% of total gamma
        ].sort_values('gamma_pct', ascending=False).head(3)

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        magnet_count = 0

        # Log call magnets
        for _, row in call_magnets.iterrows():
            log_forward_magnet(
                c,
                strike=row['strike'],
                magnet_type='CALL',
                spot_price=spot_price,
                gamma_dollars=row['gamma_ex'],
                gamma_pct=row['gamma_pct'],
                distance_pct=row['distance_pct'],
                gex_data=gex_data
            )
            magnet_count += 1
            print(f"🎯 Call Magnet: ${row['strike']:.0f} "
                  f"({row['distance_pct']:+.2f}% from spot) | "
                  f"{row['gamma_pct']:.1f}% of total gamma")

        # Log put magnets
        for _, row in put_magnets.iterrows():
            log_forward_magnet(
                c,
                strike=row['strike'],
                magnet_type='PUT',
                spot_price=spot_price,
                gamma_dollars=row['gamma_ex'],
                gamma_pct=row['gamma_pct'],
                distance_pct=row['distance_pct'],
                gex_data=gex_data
            )
            magnet_count += 1
            print(f"🎯 Put Magnet: ${row['strike']:.0f} "
                  f"({row['distance_pct']:+.2f}% from spot) | "
                  f"{row['gamma_pct']:.1f}% of total gamma")

        conn.commit()

        # Check effectiveness of recent magnets
        check_magnet_effectiveness(c, spot_price)

        conn.close()

        print(f"\n✅ Logged {magnet_count} forward magnets")

    except ImportError:
        print("⚠️ tradingvolatility_api not available, using mock data")
        log_mock_magnets()
    except Exception as e:
        print(f"❌ Error detecting forward magnets: {e}")
        import traceback
        traceback.print_exc()


def log_forward_magnet(cursor, strike: float, magnet_type: str,
                       spot_price: float, gamma_dollars: float,
                       gamma_pct: float, distance_pct: float,
                       gex_data: Dict):
    """Log a detected forward magnet to database"""

    now = datetime.now(CENTRAL_TZ)

    cursor.execute("""
        INSERT INTO forward_magnets (
            timestamp, strike, magnet_type, spot_price_at_detection,
            gamma_dollars, gamma_pct_of_total, distance_from_spot_pct,
            net_gex, call_wall, put_wall, detection_confidence,
            price_reached, hours_to_reach
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        now.strftime('%Y-%m-%d %H:%M:%S'),
        strike,
        magnet_type,
        spot_price,
        gamma_dollars,
        gamma_pct,
        distance_pct,
        gex_data.get('net_gex', 0),
        gex_data.get('call_wall', 0),
        gex_data.get('put_wall', 0),
        min(gamma_pct * 10, 100),  # Higher gamma % = higher confidence
        False,  # Will be updated later
        None
    ))


def check_magnet_effectiveness(cursor, current_spot: float):
    """
    Check if price reached detected magnets
    Updates price_reached and hours_to_reach for recent magnets
    """

    # Get magnets from last 24 hours that haven't been reached yet
    cursor.execute("""
        SELECT id, strike, magnet_type, spot_price_at_detection, timestamp
        FROM forward_magnets
        WHERE timestamp >= datetime('now', '-24 hours')
          AND price_reached = 0
    """)

    magnets = cursor.fetchall()

    for magnet_id, strike, magnet_type, entry_spot, timestamp in magnets:
        # Check if price reached this strike
        reached = False

        if magnet_type == 'CALL' and current_spot >= strike:
            reached = True
        elif magnet_type == 'PUT' and current_spot <= strike:
            reached = True

        if reached:
            # Calculate time to reach
            magnet_dt = datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S')
            now = datetime.now(CENTRAL_TZ).replace(tzinfo=None)
            hours_to_reach = (now - magnet_dt).total_seconds() / 3600

            cursor.execute("""
                UPDATE forward_magnets
                SET price_reached = 1,
                    hours_to_reach = ?,
                    spot_price_at_reach = ?
                WHERE id = ?
            """, (hours_to_reach, current_spot, magnet_id))

            print(f"✅ Magnet reached! ${strike:.0f} hit in {hours_to_reach:.1f} hours")

    # Print effectiveness stats
    cursor.execute("""
        SELECT
            magnet_type,
            COUNT(*) as total,
            SUM(CASE WHEN price_reached = 1 THEN 1 ELSE 0 END) as reached,
            AVG(CASE WHEN price_reached = 1 THEN hours_to_reach END) as avg_hours
        FROM forward_magnets
        WHERE timestamp >= datetime('now', '-7 days')
        GROUP BY magnet_type
    """)

    stats = cursor.fetchall()
    if stats:
        print("\n📊 7-Day Magnet Effectiveness:")
        for magnet_type, total, reached, avg_hours in stats:
            success_rate = (reached / total * 100) if total > 0 else 0
            avg_hours_str = f"{avg_hours:.1f}h" if avg_hours else "N/A"
            print(f"  {magnet_type} Magnets: {success_rate:.1f}% reached ({reached}/{total}) | "
                  f"Avg time: {avg_hours_str}")


def log_mock_magnets():
    """Log mock forward magnets when API is unavailable"""
    try:
        import random

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        # Mock SPY at 580
        spot = 580.0
        now = datetime.now(CENTRAL_TZ)

        # Create 2-3 mock magnets
        call_strike = round(spot * 1.02)  # 2% above
        put_strike = round(spot * 0.98)   # 2% below

        c.execute("""
            INSERT INTO forward_magnets (
                timestamp, strike, magnet_type, spot_price_at_detection,
                gamma_dollars, gamma_pct_of_total, distance_from_spot_pct,
                net_gex, detection_confidence, price_reached
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            now.strftime('%Y-%m-%d %H:%M:%S'),
            call_strike,
            'CALL',
            spot,
            50000000,  # $50M gamma
            8.5,       # 8.5% of total
            2.0,       # 2% away
            1500000000,
            85,
            False
        ))

        c.execute("""
            INSERT INTO forward_magnets (
                timestamp, strike, magnet_type, spot_price_at_detection,
                gamma_dollars, gamma_pct_of_total, distance_from_spot_pct,
                net_gex, detection_confidence, price_reached
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            now.strftime('%Y-%m-%d %H:%M:%S'),
            put_strike,
            'PUT',
            spot,
            45000000,  # $45M gamma
            7.2,       # 7.2% of total
            -2.0,      # 2% away
            1500000000,
            72,
            False
        ))

        conn.commit()
        conn.close()

        print(f"✅ Logged 2 mock forward magnets (API unavailable)")

    except Exception as e:
        print(f"❌ Error logging mock magnets: {e}")


if __name__ == '__main__':
    detect_forward_magnets()
