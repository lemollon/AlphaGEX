#!/usr/bin/env python3
"""
Render Quick Setup Script
Run this to initialize database and take initial data snapshots.

Usage: python scripts/render_setup.py
"""

import os
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path - try multiple locations
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / 'backend'))
sys.path.insert(0, str(project_root / 'services'))

# Also handle if running from /opt/render/project/src
render_root = Path('/opt/render/project/src')
if render_root.exists():
    sys.path.insert(0, str(render_root))
    sys.path.insert(0, str(render_root / 'backend'))
    sys.path.insert(0, str(render_root / 'services'))

# Load environment variables
from dotenv import load_dotenv
load_dotenv(project_root / '.env')
if render_root.exists():
    load_dotenv(render_root / '.env')

print("=" * 70)
print("🚀 ALPHAGEX RENDER QUICK SETUP")
print(f"   Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 70)

# =============================================================================
# STEP 1: Verify DATABASE_URL
# =============================================================================
print("\n" + "-" * 70)
print("STEP 1: Checking DATABASE_URL")
print("-" * 70)

if not os.getenv('DATABASE_URL'):
    print("❌ DATABASE_URL not set!")
    print("   Set this in Render's Environment Variables section.")
    sys.exit(1)

print("✅ DATABASE_URL is set")

# =============================================================================
# STEP 2: Test Database Connection
# =============================================================================
print("\n" + "-" * 70)
print("STEP 2: Testing Database Connection")
print("-" * 70)

try:
    from database_adapter import get_connection
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT 1")
    conn.close()
    print("✅ Database connection successful")
except Exception as e:
    print(f"❌ Database connection failed: {e}")
    print("   Check your DATABASE_URL format:")
    print("   postgresql://user:password@host:5432/database")
    sys.exit(1)

# =============================================================================
# STEP 3: Initialize Database Tables
# =============================================================================
print("\n" + "-" * 70)
print("STEP 3: Initializing Database Tables")
print("-" * 70)

try:
    from db.config_and_database import init_database
    init_database()
    print("✅ Database tables initialized")
except Exception as e:
    print(f"❌ Database initialization failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# =============================================================================
# STEP 4: Verify Critical Tables Exist
# =============================================================================
print("\n" + "-" * 70)
print("STEP 4: Verifying Critical Tables")
print("-" * 70)

critical_tables = [
    'gex_history',
    'regime_signals',
    'market_data',
    'probability_outcomes',
    'autonomous_open_positions',
    'autonomous_closed_trades',
    'data_collection_log',
]

try:
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
    """)
    existing = {row[0] for row in cursor.fetchall()}

    all_exist = True
    for table in critical_tables:
        if table in existing:
            print(f"  ✅ {table}")
        else:
            print(f"  ❌ {table} - MISSING!")
            all_exist = False

    conn.close()

    if not all_exist:
        print("\n⚠️  Some tables missing. Re-running init...")
        from db.config_and_database import init_database
        init_database()
except Exception as e:
    print(f"❌ Table verification failed: {e}")

# =============================================================================
# STEP 5: Check for GEX Data Source
# =============================================================================
print("\n" + "-" * 70)
print("STEP 5: Checking GEX Data Sources")
print("-" * 70)

has_tv_api = bool(os.getenv('TRADING_VOLATILITY_API_KEY') or os.getenv('TV_USERNAME'))
has_tradier = bool(os.getenv('TRADIER_API_KEY'))

if has_tv_api:
    print("✅ TradingVolatility API configured")
elif has_tradier:
    print("✅ Tradier API configured (fallback)")
else:
    print("⚠️  No GEX data source configured!")
    print("   Live GEX data will not be available.")
    print("   Add TRADING_VOLATILITY_API_KEY or TRADIER_API_KEY in Render Environment")

# =============================================================================
# STEP 6: Take Initial GEX Snapshot (if source available)
# =============================================================================
print("\n" + "-" * 70)
print("STEP 6: Taking Initial GEX Snapshot")
print("-" * 70)

if has_tv_api or has_tradier:
    try:
        from gamma.gex_history_snapshot_job import save_gex_snapshot
        success = save_gex_snapshot('SPY')
        if success:
            print("✅ Initial GEX snapshot saved")
        else:
            print("⚠️  GEX snapshot returned no data (market may be closed)")
    except Exception as e:
        print(f"⚠️  GEX snapshot failed: {e}")
        print("   This may be normal outside market hours")
else:
    print("⚠️  Skipping - no GEX data source configured")

# =============================================================================
# STEP 7: Verify Data in Tables
# =============================================================================
print("\n" + "-" * 70)
print("STEP 7: Checking Data Status")
print("-" * 70)

try:
    conn = get_connection()
    cursor = conn.cursor()

    tables_to_check = ['gex_history', 'regime_signals', 'market_data']
    for table in tables_to_check:
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        count = cursor.fetchone()[0]
        if count > 0:
            print(f"  ✅ {table}: {count} records")
        else:
            print(f"  ⚠️  {table}: empty (will populate during market hours)")

    conn.close()
except Exception as e:
    print(f"⚠️  Data check failed: {e}")

# =============================================================================
# STEP 8: Test Backend API
# =============================================================================
print("\n" + "-" * 70)
print("STEP 8: Testing Backend API Import")
print("-" * 70)

try:
    from backend.main import app
    print("✅ FastAPI app loads successfully")
except Exception as e:
    print(f"❌ Backend API failed to load: {e}")
    import traceback
    traceback.print_exc()

# =============================================================================
# SUMMARY
# =============================================================================
print("\n" + "=" * 70)
print("🎉 SETUP COMPLETE")
print("=" * 70)

print("""
Next Steps:
-----------
1. ✅ Database is initialized with all tables

2. 📊 To populate data during market hours:
   - The automated_data_collector.py should run automatically
   - Or manually: python data/automated_data_collector.py

3. 🔍 To run full diagnostics:
   python scripts/render_diagnostic.py

4. 🌐 Your API should be accessible at:
   https://your-app.onrender.com/api/health

5. 📱 Frontend should connect to:
   NEXT_PUBLIC_API_URL=https://your-backend.onrender.com
""")

print("=" * 70)
