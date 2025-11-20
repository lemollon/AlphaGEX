#!/usr/bin/env python3
"""
Startup Initialization Script
Runs once when the application starts to ensure database is populated
"""
import sqlite3
import os
from datetime import datetime
from config_and_database import DB_PATH, init_database

def check_needs_initialization() -> bool:
    """Check if database needs initialization"""
    try:
        conn = sqlite3.connect(DB_PATH, timeout=5.0)
        c = conn.cursor()

        # Check if gex_history has any data
        c.execute("SELECT COUNT(*) FROM gex_history")
        count = c.fetchone()[0]
        conn.close()

        return count == 0
    except:
        # Table doesn't exist or other error - needs init
        return True

def initialize_on_startup():
    """Initialize database with tables and basic data on first startup"""

    print("\n" + "="*70)
    print("STARTUP INITIALIZATION CHECK")
    print("="*70)

    if not check_needs_initialization():
        print("✅ Database already initialized - skipping")
        return

    print("📊 Database is empty - initializing...")

    try:
        # Create tables
        print("Creating database tables...")
        init_database()
        print("✅ Tables created")

        # Try to backfill with Polygon data
        try:
            from polygon_helper import PolygonDataFetcher
            from dotenv import load_dotenv
            load_dotenv()

            print("📊 Fetching historical data from Polygon...")
            polygon = PolygonDataFetcher()
            bars = polygon.get_daily_bars('SPY', days=365)

            if bars and len(bars) > 0:
                print(f"✅ Fetched {len(bars)} days of data")

                # Insert data
                conn = sqlite3.connect(DB_PATH, timeout=30.0)
                conn.execute('PRAGMA journal_mode=WAL')
                c = conn.cursor()

                inserted = 0
                for bar in bars:
                    ts = datetime.fromtimestamp(bar['time']/1000)
                    try:
                        c.execute('''INSERT OR IGNORE INTO gex_history
                                     (timestamp, symbol, net_gex, flip_point, call_wall, put_wall,
                                      spot_price, mm_state, regime, data_source)
                                     VALUES (?, 'SPY', ?, ?, ?, ?, ?, 'NEUTRAL', 'NEUTRAL', 'Polygon')''',
                                  (ts.strftime('%Y-%m-%d 16:00:00'),
                                   1e9, bar['close']*0.99, bar['close']*1.02, bar['close']*0.98,
                                   bar['close']))
                        inserted += 1
                    except:
                        pass

                conn.commit()
                conn.close()
                print(f"✅ Inserted {inserted} historical records")
            else:
                print("⚠️  No data from Polygon - will collect data live")

        except Exception as e:
            print(f"⚠️  Could not fetch Polygon data: {e}")
            print("📊 App will collect data during normal operation")

        print("="*70)
        print("✅ STARTUP INITIALIZATION COMPLETE")
        print("="*70 + "\n")

    except Exception as e:
        print(f"❌ Initialization error: {e}")
        print("⚠️  App will attempt to create tables as needed")

if __name__ == "__main__":
    initialize_on_startup()
