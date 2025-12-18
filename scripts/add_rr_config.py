#!/usr/bin/env python3
"""
Add min_rr_ratio setting to apache_config table.
Run this on deploy or manually to enable the R:R filter config.
"""
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def add_rr_config():
    """Add min_rr_ratio to apache_config if not exists."""
    try:
        from database_adapter import get_connection

        conn = get_connection()
        c = conn.cursor()

        # Check if setting already exists
        c.execute("""
            SELECT setting_value FROM apache_config
            WHERE setting_name = 'min_rr_ratio'
        """)
        existing = c.fetchone()

        if existing:
            print(f"[add_rr_config] min_rr_ratio already exists: {existing[0]}")
            conn.close()
            return True

        # Insert the new setting
        c.execute("""
            INSERT INTO apache_config (setting_name, setting_value, description)
            VALUES ('min_rr_ratio', '1.5', 'Minimum risk:reward ratio using GEX walls (1.5 = need $1.50 reward per $1 risk)')
        """)
        conn.commit()
        print("[add_rr_config] ✅ Added min_rr_ratio = 1.5 to apache_config")

        conn.close()
        return True

    except Exception as e:
        print(f"[add_rr_config] Warning: Could not add config: {e}")
        return False

if __name__ == "__main__":
    add_rr_config()
