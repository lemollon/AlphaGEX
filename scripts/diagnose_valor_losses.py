#!/usr/bin/env python3
"""
Diagnose why VALOR losses are bigger than wins.
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database_adapter import DatabaseAdapter

print("=" * 70)
print("VALOR (VALOR) LOSS DIAGNOSIS")
print("=" * 70)

db = DatabaseAdapter()

# 1. Check recent closed trades
print("\n1. RECENT CLOSED TRADES (last 20)")
print("-" * 70)
rows = db.fetchall("""
    SELECT
        position_id,
        direction,
        entry_price,
        close_price,
        initial_stop,
        stop_type,
        stop_points_used,
        realized_pnl,
        close_reason,
        close_time
    FROM valor_closed_trades
    ORDER BY close_time DESC
    LIMIT 20
""")

if rows:
    wins = []
    losses = []
    for r in rows:
        pnl = float(r[7] or 0)
        stop_pts = float(r[6] or 0)
        stop_type = r[5] or 'UNKNOWN'
        reason = r[8] or ''

        print(f"  {r[0][:8]}.. | {r[1]:5} | Entry: {r[2]:.2f} | Close: {r[3]:.2f} | "
              f"Stop: {r[4]:.2f} | Type: {stop_type:8} | Pts: {stop_pts:.1f} | "
              f"P&L: ${pnl:+.2f} | {reason}")

        if pnl >= 0:
            wins.append(pnl)
        else:
            losses.append(pnl)

    print()
    if wins:
        print(f"  WINS: {len(wins)} trades, Avg: ${sum(wins)/len(wins):.2f}, Total: ${sum(wins):.2f}")
    if losses:
        print(f"  LOSSES: {len(losses)} trades, Avg: ${sum(losses)/len(losses):.2f}, Total: ${sum(losses):.2f}")

    if wins and losses:
        avg_win = sum(wins) / len(wins)
        avg_loss = abs(sum(losses) / len(losses))
        print(f"\n  Avg Win: ${avg_win:.2f}")
        print(f"  Avg Loss: ${avg_loss:.2f}")
        if avg_loss > avg_win:
            print(f"  ⚠️  PROBLEM: Avg loss (${avg_loss:.2f}) > Avg win (${avg_win:.2f})")
else:
    print("  No closed trades found")

# 2. Check stop type distribution
print("\n2. STOP TYPE DISTRIBUTION")
print("-" * 70)
rows = db.fetchall("""
    SELECT
        stop_type,
        COUNT(*) as count,
        AVG(stop_points_used) as avg_stop_pts,
        AVG(realized_pnl) as avg_pnl,
        SUM(CASE WHEN realized_pnl >= 0 THEN 1 ELSE 0 END) as wins,
        SUM(CASE WHEN realized_pnl < 0 THEN 1 ELSE 0 END) as losses
    FROM valor_closed_trades
    WHERE close_time > NOW() - INTERVAL '7 days'
    GROUP BY stop_type
""")

if rows:
    for r in rows:
        stop_type = r[0] or 'NULL'
        count = r[1]
        avg_pts = float(r[2] or 0)
        avg_pnl = float(r[3] or 0)
        wins = r[4] or 0
        losses = r[5] or 0
        win_rate = (wins / count * 100) if count > 0 else 0
        print(f"  {stop_type:10} | Trades: {count:3} | Avg Stop: {avg_pts:.1f} pts | "
              f"Avg P&L: ${avg_pnl:+.2f} | Win Rate: {win_rate:.0f}%")
else:
    print("  No data")

# 3. Check current config
print("\n3. CURRENT CONFIG")
print("-" * 70)
rows = db.fetchall("""
    SELECT key, value FROM valor_config
    WHERE key IN ('initial_stop_points', 'profit_target_points', 'ab_test_stops_enabled', 'trade_overnight')
""")
if rows:
    for r in rows:
        print(f"  {r[0]}: {r[1]}")
else:
    print("  Using defaults (config not in DB)")
    print("  initial_stop_points: 2.5 (default)")
    print("  profit_target_points: 6.0 (default)")
    print("  ab_test_stops_enabled: Check API")

# 4. Check if position monitor is working
print("\n4. POSITION MONITOR STATUS")
print("-" * 70)
# Check scan_activity for monitor actions
rows = db.fetchall("""
    SELECT
        action_type,
        COUNT(*) as count,
        MAX(timestamp) as last_seen
    FROM valor_scan_activity
    WHERE timestamp > NOW() - INTERVAL '1 hour'
    GROUP BY action_type
    ORDER BY count DESC
""")
if rows:
    for r in rows:
        print(f"  {r[0]:20} | Count: {r[1]:4} | Last: {r[2]}")
else:
    print("  No scan activity in last hour")

# 5. Check open positions
print("\n5. CURRENT OPEN POSITIONS")
print("-" * 70)
rows = db.fetchall("""
    SELECT
        position_id,
        direction,
        entry_price,
        current_stop,
        stop_type,
        stop_points_used,
        open_time
    FROM valor_positions
    WHERE status = 'OPEN'
""")
if rows:
    for r in rows:
        print(f"  {r[0][:8]}.. | {r[1]:5} | Entry: {r[2]:.2f} | Stop: {r[3]:.2f} | "
              f"Type: {r[4] or 'N/A':8} | Pts: {float(r[5] or 0):.1f}")
else:
    print("  No open positions")

print("\n" + "=" * 70)
print("RECOMMENDATIONS:")
print("=" * 70)
print("""
If DYNAMIC stops are showing in recent trades:
  → The backend may need redeployment to use FIXED stops

If avg loss > $12.50 per contract:
  → Slippage may be occurring - check execution prices

If position monitor shows no activity:
  → The 15-second monitor may not be running

Run: curl https://alphagex-api.onrender.com/api/valor/ab-test/status
  → Verify ab_test_enabled = false
""")
