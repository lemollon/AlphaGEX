#!/usr/bin/env python3
"""
Check autonomous trader database for trades
"""
import pandas as pd
from datetime import datetime
from database_adapter import get_connection

print("=" * 80)
print("AUTONOMOUS TRADER DATABASE CHECK")
print("=" * 80)
print("Database: PostgreSQL via DATABASE_URL")
print()

conn = get_connection()

# Check positions
print("\n1. AUTONOMOUS POSITIONS (Last 10 trades)")
print("-" * 80)
positions = pd.read_sql_query("""
    SELECT id, entry_date, entry_time, strategy, action, strike, option_type,
           expiration_date, contracts, entry_price, status, realized_pnl, exit_reason
    FROM autonomous_positions
    ORDER BY entry_date DESC, entry_time DESC
    LIMIT 10
""", conn)

if positions.empty:
    print("❌ NO TRADES FOUND IN DATABASE!")
else:
    print(f"✅ Found {len(positions)} trades")
    print(positions.to_string())

# Check trade log
print("\n\n2. TRADE LOG (Last 10 entries)")
print("-" * 80)
log = pd.read_sql_query("""
    SELECT date, time, action, details, success
    FROM autonomous_trade_log
    ORDER BY date DESC, time DESC
    LIMIT 10
""", conn)

if log.empty:
    print("❌ NO LOG ENTRIES FOUND!")
else:
    print(f"✅ Found {len(log)} log entries")
    print(log.to_string())

# Check config
print("\n\n3. CONFIGURATION")
print("-" * 80)
try:
    config = pd.read_sql_query("SELECT * FROM autonomous_config", conn)
    print(config.to_string())
except Exception as e:
    print(f"❌ Error reading config: {e}")

# Check live status
print("\n\n4. LIVE STATUS")
print("-" * 80)
try:
    status = pd.read_sql_query("SELECT * FROM autonomous_live_status", conn)
    print(status.to_string())
except:
    print("❌ No live status table found")

conn.close()

print("\n" + "=" * 80)
print("SUMMARY")
print("=" * 80)
print(f"Total positions in DB: {len(positions) if not positions.empty else 0}")
print(f"Open positions: {len(positions[positions['status'] == 'OPEN']) if not positions.empty else 0}")
print(f"Closed positions: {len(positions[positions['status'] == 'CLOSED']) if not positions.empty else 0}")
print()
