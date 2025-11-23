#!/usr/bin/env python3
"""Test single insert to see exact error"""
from datetime import datetime
from database_adapter import get_connection

conn = get_connection()
c = conn.cursor()

# Test gex_history insert
timestamp = datetime.now()
date = timestamp.strftime('%Y-%m-%d')

try:
    c.execute('''
        INSERT INTO gex_history (
            symbol, timestamp, date, spot_price, net_gex,
            flip_point, call_wall, put_wall
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', ('SPY', timestamp, date, 580.0, 1000000.0, 570.0, 609.0, 551.0))
    conn.commit()
    print("✅ Insert successful!")
except Exception as e:
    print(f"❌ Insert failed: {e}")
    print(f"Error type: {type(e).__name__}")
    import traceback
    traceback.print_exc()

conn.close()
