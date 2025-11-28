#!/usr/bin/env python3
"""
AlphaGEX Database Query Tool
Query the PostgreSQL database
"""

import os
from datetime import datetime
from database_adapter import get_connection

def query_postgres():
    """Query PostgreSQL database"""
    print("\n" + "="*80)
    print("POSTGRESQL DATABASE")
    print("="*80)

    database_url = os.getenv('DATABASE_URL')

    if not database_url:
        print("⚠️  DATABASE_URL not set in environment")
        print("\nTo connect:")
        print("1. Get connection string from: https://dashboard.render.com")
        print("2. Navigate to: Databases -> alphagex-db -> Connect")
        print("3. Copy 'External Connection String'")
        print("4. Run: export DATABASE_URL='postgresql://...'")
        print("5. Run this script again")
        return

    try:
        # Connect
        print("Connecting to PostgreSQL...")
        conn = get_connection()
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
        try:
            cursor.execute("SELECT pg_size_pretty(pg_database_size(current_database()))")
            size = cursor.fetchone()[0]
            print(f"\nDatabase size: {size}")
        except:
            pass

        # Connection info
        cursor.execute("SELECT version()")
        version = cursor.fetchone()[0]
        print(f"PostgreSQL version: {version.split(',')[0]}")

        # Show sample data from key tables
        key_tables = ['regime_signals', 'gex_history', 'autonomous_positions']
        for table_name in key_tables:
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                count = cursor.fetchone()[0]

                if count > 0:
                    print(f"\n{table_name} (sample 3 rows):")
                    cursor.execute(f"SELECT * FROM {table_name} LIMIT 3")
                    rows = cursor.fetchall()

                    # Get column names
                    cursor.execute("""
                        SELECT column_name
                        FROM information_schema.columns
                        WHERE table_name = %s
                        ORDER BY ordinal_position
                    """, (table_name,))
                    columns = [col[0] for col in cursor.fetchall()]

                    print("  Columns:", ", ".join(columns[:5]), "..." if len(columns) > 5 else "")
                    for row in rows:
                        print("  ", row[:5], "..." if len(row) > 5 else "")
            except Exception as e:
                print(f"  Error reading {table_name}: {e}")

        conn.close()
        print("\n✅ Connected to PostgreSQL successfully")

    except Exception as e:
        print(f"❌ Error connecting to PostgreSQL: {e}")
        print("\nCheck:")
        print("1. DATABASE_URL is correct")
        print("2. Database is running")
        print("3. Network connection is available")

if __name__ == "__main__":
    print("\n ALPHAGEX DATABASE QUERY TOOL")
    print("=" * 80)
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    query_postgres()

    print("\n" + "="*80)
    print("✅ Query complete!")
    print("="*80)
    print("\nNext steps:")
    print("1. Run backtests to populate database:")
    print("   python run_all_backtests.py")
    print("\n2. Query specific data:")
    print("   python query_database.py --table regime_signals")
    print("\n3. Check table schema:")
    print("   python query_database.py --schema autonomous_positions")
    print("="*80 + "\n")
