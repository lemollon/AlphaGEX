#!/usr/bin/env python3
"""
Quick diagnostic to verify scan activity logging is working.
Run this on Render to check if scans are being logged during market hours.
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta
import pytz

CT = pytz.timezone('America/Chicago')
now_ct = datetime.now(CT)

print("=" * 60)
print("SCAN ACTIVITY LOGGING VERIFICATION")
print(f"Current Time: {now_ct.strftime('%Y-%m-%d %I:%M:%S %p')} CT")
print("=" * 60)

# Check database connection
try:
    from database_adapter import get_connection
    conn = get_connection()
    c = conn.cursor()
    print("\n[OK] Database connection successful")
except Exception as e:
    print(f"\n[FAIL] Database connection failed: {e}")
    sys.exit(1)

# Check recent scans (last 30 minutes)
print("\n--- RECENT SCAN ACTIVITY (last 30 min) ---")
try:
    c.execute("""
        SELECT bot_name, outcome, timestamp, decision_summary
        FROM scan_activity
        WHERE timestamp > NOW() - INTERVAL '30 minutes'
        ORDER BY timestamp DESC
        LIMIT 10
    """)
    rows = c.fetchall()
    if rows:
        for row in rows:
            bot, outcome, ts, summary = row
            ts_ct = ts.astimezone(CT) if ts.tzinfo else CT.localize(ts)
            print(f"  {ts_ct.strftime('%H:%M:%S')} | {bot:8} | {outcome:15} | {summary[:50]}...")
    else:
        print("  [WARNING] No scans in last 30 minutes!")
except Exception as e:
    print(f"  [ERROR] {e}")

# Check heartbeats
print("\n--- BOT HEARTBEATS ---")
try:
    c.execute("""
        SELECT bot_name, status, last_heartbeat,
               EXTRACT(EPOCH FROM (NOW() - last_heartbeat)) as seconds_ago
        FROM bot_heartbeats
        ORDER BY bot_name
    """)
    rows = c.fetchall()
    for row in rows:
        bot, status, hb, secs = row
        secs = int(secs) if secs else 0
        status_icon = "[OK]" if secs < 600 else "[STALE]"
        print(f"  {status_icon} {bot:8} | {status:15} | {secs:4}s ago")
except Exception as e:
    print(f"  [ERROR] {e}")

# Check ML data gatherer
print("\n--- ML DATA GATHERER CHECK ---")
try:
    from trading.ml_data_gatherer import gather_ml_data, GEX_ML_AVAILABLE, ML_REGIME_AVAILABLE, ENSEMBLE_AVAILABLE
    print(f"  GEX_ML_AVAILABLE: {GEX_ML_AVAILABLE}")
    print(f"  ML_REGIME_AVAILABLE: {ML_REGIME_AVAILABLE}")
    print(f"  ENSEMBLE_AVAILABLE: {ENSEMBLE_AVAILABLE}")

    # Try gathering ML data
    ml_data = gather_ml_data(
        symbol="SPY",
        spot_price=590.0,
        vix=15.0,
        gex_data={'net_gex': 1e9, 'call_wall': 600, 'put_wall': 580, 'flip_point': 585},
        bot_name="TEST"
    )
    non_empty = sum(1 for v in ml_data.values() if v)
    print(f"  ML data fields populated: {non_empty}/{len(ml_data)}")

    if ml_data.get('gex_ml_direction'):
        print(f"  GEX ML Direction: {ml_data['gex_ml_direction']} (conf: {ml_data.get('gex_ml_confidence', 0):.2f})")
    else:
        print("  [WARNING] GEX ML Direction not populated - model may not be trained")
except Exception as e:
    print(f"  [ERROR] {e}")
    import traceback
    traceback.print_exc()

# Check scan logger
print("\n--- SCAN LOGGER CHECK ---")
try:
    from trading.scan_activity_logger import log_ares_scan, ScanOutcome, SCAN_ACTIVITY_LOGGER_AVAILABLE
    print(f"  SCAN_ACTIVITY_LOGGER_AVAILABLE: True")
    print(f"  ScanOutcome values: {[e.value for e in ScanOutcome][:5]}...")
except ImportError as e:
    print(f"  [ERROR] Scan logger import failed: {e}")

# Check if scans are being logged during market hours
print("\n--- MARKET HOURS SCAN CHECK ---")
try:
    c.execute("""
        SELECT
            COUNT(*) as total,
            COUNT(CASE WHEN outcome NOT IN ('BEFORE_WINDOW', 'AFTER_WINDOW', 'MARKET_CLOSED') THEN 1 END) as market_hours_scans
        FROM scan_activity
        WHERE DATE(timestamp) = CURRENT_DATE
    """)
    row = c.fetchone()
    total, market_scans = row
    print(f"  Total scans today: {total}")
    print(f"  Market hours scans: {market_scans}")

    if market_scans == 0 and now_ct.hour >= 8 and now_ct.hour < 15:
        print("  [WARNING] No market hours scans yet today!")
    elif market_scans > 0:
        print("  [OK] Market hours scans are being logged!")
except Exception as e:
    print(f"  [ERROR] {e}")

conn.close()
print("\n" + "=" * 60)
print("Verification complete. Check warnings above.")
print("=" * 60)
