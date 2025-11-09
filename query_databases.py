#!/usr/bin/env python3
"""
AlphaGEX Database Query Tool
Quickly inspect both local and production databases
"""

import sqlite3
import os
from datetime import datetime

def query_local_sqlite():
    """Query local SQLite database"""
    db_path = '/home/user/AlphaGEX/gex_copilot.db'

    print("\n" + "="*80)
    print("LOCAL SQLITE DATABASE")
    print("="*80)
    print(f"Location: {db_path}")

    if not os.path.exists(db_path):
        print("❌ Database file not found!")
        return

    size = os.path.getsize(db_path)
    print(f"Size: {size:,} bytes ({size/1024:.2f} KB)")

    if size == 0:
        print("⚠️  Database is empty (no data yet)")
        print("\nTo populate it, run:")
        print("  python run_all_backtests.py")
        return

    # Connect and query
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # List tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    print(f"\nTables ({len(tables)}):")
    for table in tables:
        table_name = table[0]
        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        count = cursor.fetchone()[0]
        print(f"  - {table_name}: {count:,} rows")

    # Show sample data from each table
    for table in tables:
        table_name = table[0]
        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        count = cursor.fetchone()[0]

        if count > 0:
            print(f"\n{table_name} (sample 3 rows):")
            cursor.execute(f"SELECT * FROM {table_name} LIMIT 3")
            rows = cursor.fetchall()

            # Get column names
            cursor.execute(f"PRAGMA table_info({table_name})")
            columns = [col[1] for col in cursor.fetchall()]

            print("  Columns:", ", ".join(columns[:5]), "..." if len(columns) > 5 else "")
            for row in rows:
                print("  ", row[:5], "..." if len(row) > 5 else "")

    conn.close()

def query_render_postgres():
    """Query Render PostgreSQL database"""
    print("\n" + "="*80)
    print("RENDER POSTGRESQL DATABASE (Production)")
    print("="*80)

    database_url = os.getenv('DATABASE_URL')

    if not database_url:
        print("⚠️  DATABASE_URL not set in environment")
        print("\nTo connect:")
        print("1. Get connection string from: https://dashboard.render.com")
        print("2. Navigate to: Databases → alphagex-db → Connect")
        print("3. Copy 'External Connection String'")
        print("4. Run: export DATABASE_URL='postgresql://...'")
        print("5. Run this script again")
        return

    try:
        import psycopg2
    except ImportError:
        print("❌ psycopg2 not installed")
        print("Install: pip install psycopg2-binary")
        return

    try:
        # Connect
        print("Connecting to Render PostgreSQL...")
        conn = psycopg2.connect(database_url)
        cursor = conn.cursor()

        # List tables
        cursor.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema='public'
            ORDER BY table_name
        """)
        tables = cursor.fetchall()

        if not tables:
            print("⚠️  No tables found (database is empty)")
        else:
            print(f"\nTables ({len(tables)}):")
            for table in tables:
                table_name = table[0]
                cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                count = cursor.fetchone()[0]
                print(f"  - {table_name}: {count:,} rows")

        # Database size
        cursor.execute("SELECT pg_size_pretty(pg_database_size('alphagex'))")
        size = cursor.fetchone()[0]
        print(f"\nDatabase size: {size}")

        # Connection info
        cursor.execute("SELECT version()")
        version = cursor.fetchone()[0]
        print(f"PostgreSQL version: {version.split(',')[0]}")

        conn.close()
        print("\n✅ Connected to Render PostgreSQL successfully")

    except Exception as e:
        print(f"❌ Error connecting to Render: {e}")
        print("\nCheck:")
        print("1. DATABASE_URL is correct")
        print("2. Database is running on Render")
        print("3. Network connection is available")

if __name__ == "__main__":
    print("\n🗄️  ALPHAGEX DATABASE QUERY TOOL")
    print("=" * 80)
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    query_local_sqlite()
    query_render_postgres()

    print("\n" + "="*80)
    print("✅ Query complete!")
    print("="*80)
    print("\nNext steps:")
    print("1. Run backtests to populate local database:")
    print("   python run_all_backtests.py")
    print("\n2. Query specific data:")
    print("   sqlite3 gex_copilot.db 'SELECT * FROM backtest_results;'")
    print("\n3. Connect to Render (if needed):")
    print("   export DATABASE_URL='postgresql://...'")
    print("   python query_databases.py")
    print("="*80 + "\n")
