#!/usr/bin/env python3
"""XRP-PERP diagnostic — shows why XRP isn't trading."""
from database_adapter import get_connection
conn = get_connection()
cur = conn.cursor()

print("=== SCAN OUTCOMES (last 10) ===")
cur.execute("""
    SELECT scan_time, outcome, funding_rate, signal_action, signal_reasoning
    FROM agape_xrp_perp_scan_activity
    ORDER BY scan_time DESC LIMIT 10
""")
for r in cur.fetchall():
    t = str(r[0])[-8:] if r[0] else "?"
    print(f"  {t} | {r[1] or 'NULL':30s} | fr={r[2] or 0:.4f} | {r[3] or '-':6s} | {r[4] or '-'}")

print("\n=== ERROR LOGS (last 10) ===")
cur.execute("""
    SELECT log_time, action, message
    FROM agape_xrp_perp_activity_log
    WHERE level IN ('ERROR', 'WARNING', 'CRITICAL')
    ORDER BY log_time DESC LIMIT 10
""")
for r in cur.fetchall():
    t = str(r[0])[-8:] if r[0] else "?"
    print(f"  {t} | {r[1] or '-':20s} | {r[2] or '-'}")

print("\n=== MARGIN CONFIG ===")
cur.execute("""
    SELECT key, value FROM autonomous_config
    WHERE key LIKE 'agape_xrp_perp%'
""")
rows = cur.fetchall()
if rows:
    for r in rows:
        print(f"  {r[0]} = {r[1]}")
else:
    print("  No agape_xrp_perp config in autonomous_config (uses code defaults)")

print("\n=== BOT STATUS ===")
cur.execute("""
    SELECT COUNT(*) FROM agape_xrp_perp_positions WHERE status = 'open'
""")
print(f"  Open positions: {cur.fetchone()[0]}")
cur.execute("""
    SELECT COUNT(*), COALESCE(SUM(realized_pnl), 0)
    FROM agape_xrp_perp_positions WHERE status = 'closed'
""")
r = cur.fetchone()
print(f"  Closed trades: {r[0]}, Total P&L: ${r[1]:.2f}")

cur.close()
conn.close()
