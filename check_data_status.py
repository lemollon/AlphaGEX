#!/usr/bin/env python3
"""
Quick script to check real data collection status
"""

import sqlite3
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent))

# Database path - always in backend directory
DB_PATH = Path(__file__).parent / 'backend' / 'gex_copilot.db'

def check_status():
    """Check if real data is being collected"""

    print("="*70)
    print("AlphaGEX Real Data Collection Status")
    print("="*70)
    print()

    # Check if .env exists and has API key
    env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
    has_env = os.path.exists(env_path)

    has_api_key = False
    if has_env:
        with open(env_path, 'r') as f:
            content = f.read()
            has_api_key = 'TRADING_VOLATILITY_API_KEY' in content and 'your_' not in content

    print("Configuration Status:")
    print(f"  .env file exists: {'✅ Yes' if has_env else '❌ No'}")
    print(f"  API key configured: {'✅ Yes' if has_api_key else '❌ No (see REAL_DATA_SETUP.md)'}")
    print()

    # Check database
    if not os.path.exists(DB_PATH):
        print(f"❌ Database not found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Tables to check
    tables = {
        'regime_signals': 'Psychology Performance',
        'gex_history': 'GEX History',
        'recommendations': 'Recommendations History',
        'conversations': 'AI Conversation History',
        'liberation_outcomes': 'Liberation Outcomes',
        'forward_magnets': 'Forward Magnets'
    }

    print("Database Status:")
    print("="*70)

    has_any_data = False
    total_rows = 0

    for table, description in tables.items():
        try:
            c.execute(f'SELECT COUNT(*) FROM {table}')
            count = c.fetchone()[0]
            total_rows += count

            # Get most recent entry
            c.execute(f'SELECT MAX(timestamp) FROM {table} WHERE timestamp IS NOT NULL LIMIT 1')
            latest = c.fetchone()[0]

            if count > 0:
                has_any_data = True
                age = ""
                if latest:
                    try:
                        latest_dt = datetime.fromisoformat(latest.replace('Z', '+00:00'))
                        diff = datetime.now() - latest_dt

                        if diff.total_seconds() < 3600:
                            age = f"(latest: {int(diff.total_seconds()/60)} min ago)"
                        elif diff.total_seconds() < 86400:
                            age = f"(latest: {int(diff.total_seconds()/3600)} hours ago)"
                        else:
                            age = f"(latest: {int(diff.days)} days ago)"
                    except:
                        age = ""

                status = f"✅ {count:>6} rows {age}"
            else:
                status = f"⚪ {count:>6} rows (empty)"

            print(f"  {description:30} {status}")

        except Exception as e:
            print(f"  {description:30} ❌ Error: {str(e)[:30]}")

    conn.close()

    print()
    print("="*70)

    if not has_api_key:
        print("\n⚠️  API KEY REQUIRED FOR REAL DATA")
        print("\nTo start collecting real data:")
        print("  1. Get API key from https://tradingvolatility.net")
        print("  2. Create .env file: cp .env.template .env")
        print("  3. Add your API key to .env")
        print("  4. Start collector: ./manage_collector.sh start")
        print("\nSee REAL_DATA_SETUP.md for detailed instructions")
    elif total_rows == 0:
        print("\n⏳ WAITING FOR FIRST DATA COLLECTION")
        print("\nData collectors are configured but no data yet.")
        print("\nStart collecting:")
        print("  ./manage_collector.sh start")
        print("\nOr manually trigger:")
        print("  python3 gex_history_snapshot_job.py")
    else:
        print(f"\n✅ COLLECTING REAL DATA ({total_rows} total rows)")
        print("\nMonitor collection:")
        print("  ./manage_collector.sh status")
        print("  ./manage_collector.sh logs")
        print("\nRefresh your browser to see updated charts!")

    print()


if __name__ == '__main__':
    check_status()
