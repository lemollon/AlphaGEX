#!/usr/bin/env python3
"""
Initialize main database schema only
NOTE: Tables are now defined in db/config_and_database.py (single source of truth).
This script just calls init_database() and initializes default config values.
"""
import sys
from db.config_and_database import init_database
from database_adapter import get_connection

print("=" * 80)
print("INITIALIZING ALPHAGEX DATABASE")
print("=" * 80)
print("Database: PostgreSQL via DATABASE_URL")
print("Schema: db/config_and_database.py (single source of truth)")
print()

# Initialize main database schema (creates ALL tables)
print("Creating database schema from db/config_and_database.py...")
try:
    init_database()
    print("✅ Database schema created successfully")
except Exception as e:
    print(f"❌ Error creating schema: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Initialize autonomous trader config and live status
print("\nInitializing autonomous trader configuration...")
conn = get_connection()
c = conn.cursor()

try:
    # Initialize live status if not exists
    c.execute("SELECT COUNT(*) FROM autonomous_live_status WHERE id = 1")
    if c.fetchone()[0] == 0:
        from datetime import datetime
        c.execute("""
            INSERT INTO autonomous_live_status (id, timestamp, status, current_action, is_working)
            VALUES (1, %s, 'INITIALIZED', 'System ready', 1)
        """, (datetime.now().isoformat(),))
        print("   ✅ Live status initialized")

    # Initialize config if first run
    c.execute("SELECT value FROM autonomous_config WHERE key = 'initialized'")
    result = c.fetchone()

    if not result:
        starting_capital = 1000000
        c.execute("INSERT INTO autonomous_config (key, value) VALUES ('capital', %s)", (str(starting_capital),))
        c.execute("INSERT INTO autonomous_config (key, value) VALUES ('initialized', 'true')")
        c.execute("INSERT INTO autonomous_config (key, value) VALUES ('auto_execute', 'true')")
        c.execute("INSERT INTO autonomous_config (key, value) VALUES ('last_trade_date', '')")
        c.execute("INSERT INTO autonomous_config (key, value) VALUES ('mode', 'paper')")
        print(f"   ✅ Initialized with $1,000,000 starting capital")
    else:
        print("   ✅ Config already initialized")

    # Initialize bot-specific starting capitals (for equity curves)
    bot_capitals = {
        'fortress_starting_capital': '100000',
        'solomon_starting_capital': '100000',
        'samson_starting_capital': '200000',
        'anchor_starting_capital': '200000',
        'gideon_starting_capital': '100000',
    }
    for key, value in bot_capitals.items():
        c.execute("""
            INSERT INTO autonomous_config (key, value)
            VALUES (%s, %s)
            ON CONFLICT (key) DO NOTHING
        """, (key, value))
    print("   ✅ Bot starting capitals initialized")

    conn.commit()
    print("✅ Autonomous trader configuration complete")

except Exception as e:
    print(f"❌ Error initializing config: {e}")
    import traceback
    traceback.print_exc()
    conn.rollback()
    sys.exit(1)

# Verify tables
cursor = conn.cursor()
cursor.execute("""
    SELECT table_name
    FROM information_schema.tables
    WHERE table_schema = 'public'
    ORDER BY table_name
""")
tables = cursor.fetchall()
conn.close()

print(f"\n✅ Database has {len(tables)} tables:")
for table in tables:
    print(f"   - {table[0]}")

print("\n" + "=" * 80)
print("✅ DATABASE INITIALIZATION COMPLETE!")
print("=" * 80)
print("\nYour AlphaGEX autonomous trader is now ready to use!")
print("All tables are defined in db/config_and_database.py (single source of truth)")
print()
