#!/usr/bin/env python3
"""
Set wall_filter_pct to 1.0% for SOLOMON and GIDEON.

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
print("SETTING wall_filter_pct = 1.0% FOR SOLOMON AND GIDEON")
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

    # Check if there are bot-specific config tables
    print("\n[2] Checking for bot-specific config tables...")
    c.execute("""
        SELECT table_name FROM information_schema.tables
        WHERE table_name LIKE '%config%'
        ORDER BY table_name
    """)
    config_tables = [row[0] for row in c.fetchall()]
    print(f"    Config tables: {config_tables}")

    # Simple key-value table (key, value) - no bot_name column
    if columns == ['key', 'value'] or set(columns) == {'key', 'value'}:
        print("\n[3] Simple key-value table detected")
        print("    Will use prefixed keys: SOLOMON_wall_filter_pct, ICARUS_wall_filter_pct")

        # Check current values
        print("\n[4] Current wall_filter values...")
        c.execute("SELECT key, value FROM autonomous_config WHERE key LIKE '%wall_filter%'")
        existing = c.fetchall()
        if existing:
            for row in existing:
                print(f"    {row[0]}: {row[1]}")
        else:
            print("    (none set)")

        # Set SOLOMON
        print("\n[5] Setting SOLOMON_wall_filter_pct = 1.0...")
        c.execute("""
            INSERT INTO autonomous_config (key, value)
            VALUES ('SOLOMON_wall_filter_pct', '1.0')
            ON CONFLICT (key) DO UPDATE SET value = '1.0'
        """)
        print("    ✅ SOLOMON_wall_filter_pct = 1.0")

        # Set GIDEON
        print("\n[6] Setting ICARUS_wall_filter_pct = 1.0...")
        c.execute("""
            INSERT INTO autonomous_config (key, value)
            VALUES ('ICARUS_wall_filter_pct', '1.0')
            ON CONFLICT (key) DO UPDATE SET value = '1.0'
        """)
        print("    ✅ ICARUS_wall_filter_pct = 1.0")

        conn.commit()

        # Verify
        print("\n[7] Verifying...")
        c.execute("SELECT key, value FROM autonomous_config WHERE key LIKE '%wall_filter%'")
        final = c.fetchall()
        for row in final:
            status = "✅" if row[1] == '1.0' else "❌"
            print(f"    {status} {row[0]}: {row[1]}")

    # Bot-specific table with bot_name column
    elif 'bot_name' in columns or 'bot' in columns:
        bot_col = 'bot_name' if 'bot_name' in columns else 'bot'
        key_col = 'config_key' if 'config_key' in columns else 'key'
        val_col = 'config_value' if 'config_value' in columns else 'value'

        print(f"\n[3] Bot-specific table detected")
        print(f"    Using columns: {bot_col}, {key_col}, {val_col}")

        # Check current values
        print("\n[4] Current wall_filter_pct values...")
        c.execute(f"SELECT {bot_col}, {val_col} FROM autonomous_config WHERE {key_col} = 'wall_filter_pct'")
        existing = c.fetchall()
        if existing:
            for row in existing:
                print(f"    {row[0]}: {row[1]}%")
        else:
            print("    (none set)")

        # Set SOLOMON
        print("\n[5] Setting SOLOMON wall_filter_pct = 1.0%...")
        c.execute(f"""
            INSERT INTO autonomous_config ({bot_col}, {key_col}, {val_col})
            VALUES ('SOLOMON', 'wall_filter_pct', '1.0')
            ON CONFLICT ({bot_col}, {key_col}) DO UPDATE SET {val_col} = '1.0'
        """)
        print("    ✅ SOLOMON = 1.0%")

        # Set GIDEON
        print("\n[6] Setting GIDEON wall_filter_pct = 1.0%...")
        c.execute(f"""
            INSERT INTO autonomous_config ({bot_col}, {key_col}, {val_col})
            VALUES ('GIDEON', 'wall_filter_pct', '1.0')
            ON CONFLICT ({bot_col}, {key_col}) DO UPDATE SET {val_col} = '1.0'
        """)
        print("    ✅ GIDEON = 1.0%")

        conn.commit()

        # Verify
        print("\n[7] Verifying...")
        c.execute(f"SELECT {bot_col}, {val_col} FROM autonomous_config WHERE {key_col} = 'wall_filter_pct'")
        final = c.fetchall()
        for row in final:
            status = "✅" if row[1] == '1.0' else "❌"
            print(f"    {status} {row[0]}: {row[1]}%")

    else:
        print(f"\n    ERROR: Unexpected table structure: {columns}")
        conn.close()
        sys.exit(1)

    conn.close()

    print("\n" + "=" * 60)
    print("SUCCESS! Bots will use 1.0% threshold on next scan.")
    print("=" * 60)
    print("\nNOTE: You may need to update the bot code to read these keys.")
    print("Check trading/solomon_v2/db.py and trading/gideon/db.py")

except Exception as e:
    print(f"\nERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
