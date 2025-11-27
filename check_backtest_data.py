#!/usr/bin/env python3
"""Quick script to check backtest data availability"""

from database_adapter import get_connection
from datetime import datetime, timedelta

conn = get_connection()
c = conn.cursor()

print("=" * 60)
print("BACKTEST DATA DIAGNOSTIC")
print("=" * 60)

# Check regime_signals table
print("\n1. REGIME SIGNALS TABLE (used by backtests):")
c.execute("SELECT COUNT(*) FROM regime_signals")
total_signals = c.fetchone()[0]
print(f"   Total signals: {total_signals}")

if total_signals > 0:
    c.execute("""
        SELECT primary_regime_type, COUNT(*) as count,
               MIN(timestamp) as earliest, MAX(timestamp) as latest
        FROM regime_signals
        GROUP BY primary_regime_type
        ORDER BY count DESC
    """)
    print("\n   Breakdown by pattern:")
    for row in c.fetchall():
        print(f"   - {row[0]}: {row[1]} signals ({row[2]} to {row[3]})")
else:
    print("   ⚠️  NO DATA FOUND - This is why backtests return 0 results!")

# Check recent autonomous trader activity
print("\n2. AUTONOMOUS TRADER ACTIVITY:")
c.execute("SELECT COUNT(*) FROM autonomous_trader_logs WHERE timestamp >= NOW() - INTERVAL '7 days'")
recent_actions = c.fetchone()[0]
print(f"   Actions in last 7 days: {recent_actions}")

c.execute("SELECT COUNT(*) FROM positions WHERE opened_at >= NOW() - INTERVAL '7 days'")
recent_trades = c.fetchone()[0]
print(f"   Trades in last 7 days: {recent_trades}")

# Check if trader is logging regime data
print("\n3. CHECKING REGIME LOGGING:")
c.execute("""
    SELECT log_type, COUNT(*)
    FROM autonomous_trader_logs
    WHERE timestamp >= NOW() - INTERVAL '7 days'
    GROUP BY log_type
    ORDER BY COUNT(*) DESC
    LIMIT 5
""")
print("   Recent log types:")
rows = c.fetchall()
if rows:
    for row in rows:
        print(f"   - {row[0]}: {row[1]} times")
else:
    print("   - No recent logs found")

conn.close()

print("\n" + "=" * 60)
print("DIAGNOSIS:")
print("=" * 60)
if total_signals == 0:
    print("❌ The regime_signals table is EMPTY")
    print("   This is why backtests return 0 results.")
    print("\n   SOLUTION: The autonomous trader needs to log regime signals")
    print("   when it detects psychology trap patterns. This should happen")
    print("   in the market analysis phase, not just during trade execution.")
else:
    print("✅ Data exists - backtest should work")
print("=" * 60)
