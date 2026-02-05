#!/usr/bin/env python3
"""
HERACLES Data Diagnostic
Run on Render: python scripts/heracles_data_diagnostic.py
"""
import os
import psycopg2

conn = psycopg2.connect(os.environ['DATABASE_URL'])
cursor = conn.cursor()

print("=" * 70)
print("HERACLES DATA DIAGNOSTIC")
print("=" * 70)

# 1. Table structure
print("\n--- TABLE STRUCTURE ---")
cursor.execute("""
    SELECT column_name, data_type
    FROM information_schema.columns
    WHERE table_name = 'heracles_scan_activity'
    ORDER BY ordinal_position
""")
for col, dtype in cursor.fetchall():
    print(f"  {col}: {dtype}")

# 2. Sample trades with outcomes
print("\n--- SAMPLE TRADES WITH OUTCOMES ---")
cursor.execute("""
    SELECT scan_time, underlying_price, atr, gamma_regime, signal_direction, trade_outcome, realized_pnl
    FROM heracles_scan_activity
    WHERE trade_executed = TRUE AND trade_outcome IS NOT NULL
    ORDER BY scan_time DESC
    LIMIT 10
""")
for row in cursor.fetchall():
    print(f"  {row}")

# 3. Scan frequency by day
print("\n--- SCAN FREQUENCY BY DAY ---")
cursor.execute("""
    SELECT
        DATE(scan_time) as day,
        COUNT(*) as total_scans,
        COUNT(CASE WHEN trade_executed THEN 1 END) as trades,
        MIN(scan_time)::time as first_scan,
        MAX(scan_time)::time as last_scan
    FROM heracles_scan_activity
    GROUP BY DATE(scan_time)
    ORDER BY day DESC
    LIMIT 10
""")
for row in cursor.fetchall():
    print(f"  {row}")

# 4. Time gaps between scans
print("\n--- SCAN TIME GAPS ---")
cursor.execute("""
    WITH scan_gaps AS (
        SELECT
            scan_time,
            LAG(scan_time) OVER (ORDER BY scan_time) as prev_scan,
            EXTRACT(EPOCH FROM (scan_time - LAG(scan_time) OVER (ORDER BY scan_time)))/60 as gap_minutes
        FROM heracles_scan_activity
        WHERE underlying_price > 0
    )
    SELECT
        ROUND(AVG(gap_minutes)::numeric, 1) as avg_gap_min,
        ROUND(MIN(gap_minutes)::numeric, 1) as min_gap_min,
        ROUND(MAX(gap_minutes)::numeric, 1) as max_gap_min,
        COUNT(*) as total_scans
    FROM scan_gaps
    WHERE gap_minutes IS NOT NULL AND gap_minutes < 60
""")
row = cursor.fetchone()
print(f"  Avg gap: {row[0]} min, Min: {row[1]} min, Max: {row[2]} min, Scans: {row[3]}")

# 5. Win rate by regime
print("\n--- WIN RATE BY REGIME ---")
cursor.execute("""
    SELECT
        gamma_regime,
        COUNT(*) as trades,
        COUNT(CASE WHEN trade_outcome = 'WIN' THEN 1 END) as wins,
        ROUND(COUNT(CASE WHEN trade_outcome = 'WIN' THEN 1 END) * 100.0 / COUNT(*), 1) as win_rate
    FROM heracles_scan_activity
    WHERE trade_executed = TRUE AND trade_outcome IS NOT NULL
    GROUP BY gamma_regime
""")
for row in cursor.fetchall():
    print(f"  {row[0]}: {row[1]} trades, {row[2]} wins, {row[3]}% win rate")

# 6. Check if we can do momentum lookback
print("\n--- MOMENTUM LOOKBACK FEASIBILITY ---")
cursor.execute("""
    SELECT COUNT(*) as trades_with_5min_history
    FROM heracles_scan_activity t1
    WHERE t1.trade_executed = TRUE
      AND t1.trade_outcome IS NOT NULL
      AND EXISTS (
          SELECT 1 FROM heracles_scan_activity t2
          WHERE t2.scan_time BETWEEN t1.scan_time - INTERVAL '6 minutes'
                                 AND t1.scan_time - INTERVAL '4 minutes'
            AND t2.underlying_price > 0
      )
""")
print(f"  Trades with 5-min price history available: {cursor.fetchone()[0]}")

cursor.close()
conn.close()
print("\n" + "=" * 70)
