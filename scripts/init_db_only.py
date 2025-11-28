#!/usr/bin/env python3
"""
Initialize main database schema only
"""
import sys
from config_and_database import init_database
from database_adapter import get_connection

print("=" * 80)
print("INITIALIZING ALPHAGEX DATABASE")
print("=" * 80)
print("Database: PostgreSQL via DATABASE_URL")
print()

# Initialize main database schema
print("Creating main database schema...")
try:
    init_database()
    print("✅ Main database schema created successfully")
except Exception as e:
    print(f"❌ Error creating main schema: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Now create autonomous trader tables manually
print("\nCreating autonomous trader tables...")
conn = get_connection()
c = conn.cursor()

try:
    # Positions table (PostgreSQL syntax)
    c.execute("""
        CREATE TABLE IF NOT EXISTS autonomous_positions (
            id SERIAL PRIMARY KEY,
            symbol TEXT NOT NULL,
            strategy TEXT NOT NULL,
            action TEXT NOT NULL,
            entry_date TEXT NOT NULL,
            entry_time TEXT NOT NULL,
            strike REAL NOT NULL,
            option_type TEXT NOT NULL,
            expiration_date TEXT NOT NULL,
            contracts INTEGER NOT NULL,
            entry_price REAL NOT NULL,
            entry_bid REAL,
            entry_ask REAL,
            entry_spot_price REAL,
            current_price REAL,
            current_spot_price REAL,
            unrealized_pnl REAL,
            status TEXT DEFAULT 'OPEN',
            closed_date TEXT,
            closed_time TEXT,
            exit_price REAL,
            realized_pnl REAL,
            exit_reason TEXT,
            confidence INTEGER,
            gex_regime TEXT,
            entry_net_gex REAL,
            entry_flip_point REAL,
            trade_reasoning TEXT,
            contract_symbol TEXT
        )
    """)

    # Trade log
    c.execute("""
        CREATE TABLE IF NOT EXISTS autonomous_trade_log (
            id SERIAL PRIMARY KEY,
            date TEXT NOT NULL,
            time TEXT NOT NULL,
            action TEXT NOT NULL,
            details TEXT,
            position_id INTEGER,
            success INTEGER DEFAULT 1
        )
    """)

    # Config table
    c.execute("""
        CREATE TABLE IF NOT EXISTS autonomous_config (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)

    # Live status table
    c.execute("""
        CREATE TABLE IF NOT EXISTS autonomous_live_status (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            timestamp TEXT NOT NULL,
            status TEXT NOT NULL,
            current_action TEXT,
            market_analysis TEXT,
            next_check_time TEXT,
            last_decision TEXT,
            is_working INTEGER DEFAULT 1
        )
    """)

    # Initialize live status
    c.execute("SELECT COUNT(*) FROM autonomous_live_status WHERE id = 1")
    if c.fetchone()[0] == 0:
        from datetime import datetime
        c.execute("""
            INSERT INTO autonomous_live_status (id, timestamp, status, current_action, is_working)
            VALUES (1, %s, 'INITIALIZED', 'System ready', 1)
        """, (datetime.now().isoformat(),))

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

    conn.commit()
    print("✅ Autonomous trader tables created successfully")

except Exception as e:
    print(f"❌ Error creating autonomous tables: {e}")
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
print("The database will now track all trades with full details including:")
print("  - Strike price")
print("  - Expiration date")
print("  - Contract symbol")
print("  - Entry/exit times")
print("  - P&L tracking")
print()
