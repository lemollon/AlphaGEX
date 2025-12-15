#!/usr/bin/env python3
"""Quick check of options data structure"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from pathlib import Path
load_dotenv(Path(__file__).parent.parent / '.env')

from database_adapter import get_connection

conn = get_connection()
cursor = conn.cursor()

# List all tables
print("=== TABLES IN DATABASE ===")
cursor.execute("""
    SELECT table_name FROM information_schema.tables
    WHERE table_schema = 'public'
    ORDER BY table_name
""")
for row in cursor.fetchall():
    print(f"  {row[0]}")

# Check columns in options tables
print("\n=== COLUMNS IN OPTIONS-RELATED TABLES ===")
for table in ['spy_options', 'options_data', 'orat_options_eod', 'options']:
    cursor.execute("""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = %s
        ORDER BY ordinal_position
    """, (table,))
    rows = cursor.fetchall()
    if rows:
        print(f"\n{table}:")
        for col, dtype in rows:
            print(f"  {col}: {dtype}")

# Check sample data from the table that has SPY options
print("\n=== SAMPLE SPY OPTIONS DATA ===")
# Try to find which table has the data
for table in ['spy_options', 'options_data', 'orat_options_eod', 'options']:
    try:
        cursor.execute(f"""
            SELECT * FROM {table}
            WHERE ticker = 'SPY' OR symbol = 'SPY'
            LIMIT 1
        """)
        row = cursor.fetchone()
        if row:
            print(f"\nFound SPY data in {table}")
            cursor.execute(f"SELECT column_name FROM information_schema.columns WHERE table_name = '{table}' ORDER BY ordinal_position")
            cols = [r[0] for r in cursor.fetchall()]
            for i, col in enumerate(cols):
                print(f"  {col}: {row[i]}")
            break
    except Exception as e:
        pass

# Check gamma and OI specifically
print("\n=== GAMMA AND OI DATA CHECK ===")
cursor.execute("""
    SELECT
        COUNT(*) as total,
        COUNT(gamma) as gamma_count,
        COUNT(CASE WHEN gamma > 0 THEN 1 END) as gamma_positive,
        COUNT(call_oi) as call_oi_count,
        COUNT(CASE WHEN call_oi > 0 THEN 1 END) as call_oi_positive,
        COUNT(put_oi) as put_oi_count,
        COUNT(CASE WHEN put_oi > 0 THEN 1 END) as put_oi_positive
    FROM spy_options
    WHERE ticker = 'SPY'
    LIMIT 1
""")
row = cursor.fetchone()
if row:
    print(f"  Total rows: {row[0]}")
    print(f"  Gamma non-null: {row[1]}, positive: {row[2]}")
    print(f"  Call OI non-null: {row[3]}, positive: {row[4]}")
    print(f"  Put OI non-null: {row[5]}, positive: {row[6]}")

conn.close()
