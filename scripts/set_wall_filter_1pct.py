#!/usr/bin/env python3
"""
Set wall_filter_pct to 1.0% for ATHENA and ICARUS.

This is the Apache backtest optimal value that achieved 58% win rate.

Usage on Render:
    python scripts/set_wall_filter_1pct.py
"""

import os
import sys

try:
    import psycopg2
except ImportError:
    print("ERROR: psycopg2 not installed")
    sys.exit(1)

DATABASE_URL = os.environ.get('DATABASE_URL')
if not DATABASE_URL:
    print("ERROR: DATABASE_URL environment variable not set")
    sys.exit(1)

print("=" * 60)
print("SETTING wall_filter_pct = 1.0% FOR ATHENA AND ICARUS")
print("=" * 60)

try:
    conn = psycopg2.connect(DATABASE_URL)
    c = conn.cursor()

    # First, check the table structure
    print("\n[1] Checking table structure...")
    c.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'autonomous_config'
        ORDER BY ordinal_position
    """)
    columns = [row[0] for row in c.fetchall()]
    print(f"    Columns: {columns}")

    # Check current values
    print("\n[2] Current config values...")
    c.execute("SELECT * FROM autonomous_config LIMIT 10")
    rows = c.fetchall()
    if rows:
        for row in rows:
            print(f"    {row}")
    else:
        print("    (no rows found)")

    # Determine the correct column names
    # Common patterns: (bot_name, config_key, config_value) or (name, key, value)
    if 'bot_name' in columns:
        bot_col = 'bot_name'
    elif 'bot' in columns:
        bot_col = 'bot'
    elif 'name' in columns:
        bot_col = 'name'
    else:
        print(f"\n    ERROR: Cannot find bot name column. Available: {columns}")
        conn.close()
        sys.exit(1)

    if 'config_key' in columns:
        key_col = 'config_key'
    elif 'key' in columns:
        key_col = 'key'
    else:
        print(f"\n    ERROR: Cannot find key column. Available: {columns}")
        conn.close()
        sys.exit(1)

    if 'config_value' in columns:
        val_col = 'config_value'
    elif 'value' in columns:
        val_col = 'value'
    else:
        print(f"\n    ERROR: Cannot find value column. Available: {columns}")
        conn.close()
        sys.exit(1)

    print(f"\n    Using columns: {bot_col}, {key_col}, {val_col}")

    # Check for existing wall_filter_pct
    print("\n[3] Checking existing wall_filter_pct values...")
    c.execute(f"""
        SELECT {bot_col}, {key_col}, {val_col}
        FROM autonomous_config
        WHERE {key_col} = 'wall_filter_pct'
    """)
    existing = c.fetchall()
    if existing:
        for row in existing:
            print(f"    {row[0]}: {row[2]}%")
    else:
        print("    (none set - using code defaults)")

    # Update/Insert for ATHENA
    print("\n[4] Setting ATHENA wall_filter_pct = 1.0%...")
    try:
        c.execute(f"""
            INSERT INTO autonomous_config ({bot_col}, {key_col}, {val_col})
            VALUES ('ATHENA', 'wall_filter_pct', '1.0')
            ON CONFLICT ({bot_col}, {key_col}) DO UPDATE SET
                {val_col} = '1.0'
        """)
        print("    ATHENA: SET TO 1.0%")
    except psycopg2.Error as e:
        print(f"    ATHENA error: {e}")
        # Try without ON CONFLICT
        conn.rollback()
        c.execute(f"""
            DELETE FROM autonomous_config
            WHERE {bot_col} = 'ATHENA' AND {key_col} = 'wall_filter_pct'
        """)
        c.execute(f"""
            INSERT INTO autonomous_config ({bot_col}, {key_col}, {val_col})
            VALUES ('ATHENA', 'wall_filter_pct', '1.0')
        """)
        print("    ATHENA: SET TO 1.0% (via delete+insert)")

    # Update/Insert for ICARUS
    print("\n[5] Setting ICARUS wall_filter_pct = 1.0%...")
    try:
        c.execute(f"""
            INSERT INTO autonomous_config ({bot_col}, {key_col}, {val_col})
            VALUES ('ICARUS', 'wall_filter_pct', '1.0')
            ON CONFLICT ({bot_col}, {key_col}) DO UPDATE SET
                {val_col} = '1.0'
        """)
        print("    ICARUS: SET TO 1.0%")
    except psycopg2.Error as e:
        print(f"    ICARUS error: {e}")
        conn.rollback()
        c.execute(f"""
            DELETE FROM autonomous_config
            WHERE {bot_col} = 'ICARUS' AND {key_col} = 'wall_filter_pct'
        """)
        c.execute(f"""
            INSERT INTO autonomous_config ({bot_col}, {key_col}, {val_col})
            VALUES ('ICARUS', 'wall_filter_pct', '1.0')
        """)
        print("    ICARUS: SET TO 1.0% (via delete+insert)")

    conn.commit()

    # Verify
    print("\n[6] Verifying...")
    c.execute(f"""
        SELECT {bot_col}, {key_col}, {val_col}
        FROM autonomous_config
        WHERE {key_col} = 'wall_filter_pct'
    """)
    final = c.fetchall()
    for row in final:
        status = "✅" if row[2] == '1.0' else "❌"
        print(f"    {status} {row[0]}: {row[2]}%")

    conn.close()

    print("\n" + "=" * 60)
    print("SUCCESS! Bots will use 1.0% threshold on next scan.")
    print("=" * 60)

except Exception as e:
    print(f"\nERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
