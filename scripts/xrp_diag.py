#!/usr/bin/env python3
"""XRP-PERP scan diagnostic — shows why XRP isn't trading."""
from database_adapter import get_connection
conn = get_connection()
cur = conn.cursor()
cur.execute("""
    SELECT scan_time, outcome, funding_rate, signal_action, signal_reasoning
    FROM agape_xrp_perp_scan_activity
    ORDER BY scan_time DESC LIMIT 15
""")
rows = cur.fetchall()
if not rows:
    print("NO SCANS FOUND — bot may not be running")
else:
    for r in rows:
        t = str(r[0])[-8:] if r[0] else "?"
        print(f"{t} | {r[1] or 'NULL':30s} | fr={r[2] or 0:.4f} | {r[3] or '-':6s} | {r[4] or '-'}")
cur.close()
conn.close()
