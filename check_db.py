#!/usr/bin/env python3
"""Check scanner database"""
import sqlite3
import os

if os.path.exists('scanner_results.db'):
    conn = sqlite3.connect('scanner_results.db')
    c = conn.cursor()

    print("Recent scanner runs:")
    print("=" * 80)

    try:
        c.execute("SELECT timestamp, symbols_scanned, opportunities_found FROM scanner_runs ORDER BY timestamp DESC LIMIT 5")
        rows = c.fetchall()

        if rows:
            for row in rows:
                print(f"{row[0]} | Symbols: {row[1]} | Found: {row[2]}")
        else:
            print("No runs found")
    except Exception as e:
        print(f"Error: {e}")

    conn.close()
else:
    print("scanner_results.db not found")
