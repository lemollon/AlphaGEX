#!/usr/bin/env python3
"""
Quick database connection test - diagnoses where the problem is
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from pathlib import Path
load_dotenv(Path(__file__).parent.parent / '.env')

import time

print("=" * 60)
print("DATABASE CONNECTION TEST")
print("=" * 60)

# Step 1: Check DATABASE_URL
db_url = os.getenv('DATABASE_URL')
if not db_url:
    print("❌ DATABASE_URL not set!")
    print("   Run: set DATABASE_URL=postgresql://...")
    sys.exit(1)
print(f"✅ DATABASE_URL is set")
print(f"   Host: {db_url.split('@')[1].split('/')[0] if '@' in db_url else 'unknown'}")

# Step 2: Test basic connection
print("\n📡 Testing connection (30 second timeout)...")
start = time.time()
try:
    import psycopg2
    from urllib.parse import urlparse

    result = urlparse(db_url)
    conn = psycopg2.connect(
        host=result.hostname,
        port=result.port or 5432,
        user=result.username,
        password=result.password,
        database=result.path[1:],
        connect_timeout=30
    )
    elapsed = time.time() - start
    print(f"✅ Connected in {elapsed:.1f}s")
except Exception as e:
    elapsed = time.time() - start
    print(f"❌ Connection failed after {elapsed:.1f}s: {e}")
    sys.exit(1)

# Step 3: Check if table exists
print("\n📋 Checking if orat_options_eod table exists...")
cursor = conn.cursor()
try:
    cursor.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_name = 'orat_options_eod'
        );
    """)
    exists = cursor.fetchone()[0]
    if exists:
        print("✅ Table orat_options_eod EXISTS")
    else:
        print("❌ Table orat_options_eod DOES NOT EXIST")
        print("   Run: python scripts/create_backtest_schema.py")
        conn.close()
        sys.exit(1)
except Exception as e:
    print(f"❌ Error checking table: {e}")
    conn.close()
    sys.exit(1)

# Step 4: Count existing rows
print("\n📊 Counting existing rows...")
try:
    cursor.execute("SELECT COUNT(*) FROM orat_options_eod;")
    count = cursor.fetchone()[0]
    print(f"✅ Table has {count:,} rows")
except Exception as e:
    print(f"❌ Error counting rows: {e}")

# Step 5: Try a test INSERT
print("\n🧪 Testing INSERT (will rollback)...")
start = time.time()
try:
    cursor.execute("""
        INSERT INTO orat_options_eod (trade_date, ticker, strike, option_type)
        VALUES ('1999-01-01', 'TEST', 100.0, 'TEST')
    """)
    elapsed = time.time() - start
    print(f"✅ INSERT succeeded in {elapsed:.1f}s")
    conn.rollback()  # Don't actually insert test data
    print("   (Rolled back test data)")
except Exception as e:
    elapsed = time.time() - start
    print(f"❌ INSERT failed after {elapsed:.1f}s: {e}")
    conn.rollback()

conn.close()
print("\n" + "=" * 60)
print("TEST COMPLETE")
print("=" * 60)
