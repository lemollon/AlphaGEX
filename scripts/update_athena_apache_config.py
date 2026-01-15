#!/usr/bin/env python3
"""
Update ATHENA config in database to match Apache GEX backtest optimal parameters.

This script updates the autonomous_config table with the profitable parameters
from the Apache GEX directional backtest.

Run this after deploying the code changes to ensure the database config matches.

Usage:
    python scripts/update_athena_apache_config.py
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / '.env')
except ImportError:
    pass  # dotenv not required if env vars already set

from database_adapter import db_connection


# Apache GEX backtest optimal parameters
APACHE_CONFIG = {
    # Strategy params
    'wall_filter_pct': 1.0,        # Trade within 1% of GEX wall (was 3.0)
    'min_rr_ratio': 1.5,           # Min risk:reward ratio (was 0.8)

    # Win probability thresholds
    'min_win_probability': 0.55,   # 55% minimum (was 0.42)
    'min_confidence': 0.55,        # 55% minimum (was 0.45)

    # VIX filter
    'min_vix': 15.0,               # Skip if VIX too low
    'max_vix': 25.0,               # Skip if VIX too high

    # GEX ratio asymmetry
    'min_gex_ratio_bearish': 1.5,  # GEX ratio > 1.5 for bearish
    'max_gex_ratio_bullish': 0.67, # GEX ratio < 0.67 for bullish
}


def update_athena_config():
    """Update ATHENA config in database with Apache parameters"""

    print("=" * 60)
    print("UPDATING ATHENA CONFIG TO APACHE BACKTEST PARAMETERS")
    print("=" * 60)

    try:
        with db_connection() as conn:
            c = conn.cursor()

            # First, show current config
            print("\n[CURRENT CONFIG]")
            c.execute("""
                SELECT config_key, config_value
                FROM autonomous_config
                WHERE bot_name = 'ATHENA'
                ORDER BY config_key
            """)
            current = c.fetchall()

            if current:
                for key, value in current:
                    print(f"  {key}: {value}")
            else:
                print("  (no config stored - using code defaults)")

            # Update/insert each config value
            print("\n[UPDATING TO APACHE PARAMETERS]")
            for key, value in APACHE_CONFIG.items():
                # Use upsert pattern
                c.execute("""
                    INSERT INTO autonomous_config (bot_name, config_key, config_value)
                    VALUES ('ATHENA', %s, %s)
                    ON CONFLICT (bot_name, config_key) DO UPDATE SET
                        config_value = EXCLUDED.config_value,
                        updated_at = NOW()
                """, (key, str(value)))
                print(f"  {key}: {value}")

            conn.commit()

            # Verify the update
            print("\n[VERIFIED CONFIG]")
            c.execute("""
                SELECT config_key, config_value
                FROM autonomous_config
                WHERE bot_name = 'ATHENA'
                ORDER BY config_key
            """)

            for key, value in c.fetchall():
                expected = APACHE_CONFIG.get(key)
                status = "✓" if expected is not None else " "
                print(f"  {status} {key}: {value}")

            print("\n" + "=" * 60)
            print("SUCCESS: ATHENA config updated to Apache parameters")
            print("=" * 60)
            print("\nThe bot will use these settings on next restart/scan.")

            return True

    except Exception as e:
        print(f"\nERROR: Failed to update config: {e}")
        import traceback
        traceback.print_exc()
        return False


def show_config_comparison():
    """Show comparison between old defaults and Apache parameters"""

    print("\n[PARAMETER COMPARISON]")
    print("-" * 60)
    print(f"{'Parameter':<25} {'Old Default':<15} {'Apache Optimal':<15}")
    print("-" * 60)

    comparisons = [
        ('wall_filter_pct', '3.0%', '1.0%'),
        ('min_win_probability', '42%', '55%'),
        ('min_confidence', '45%', '55%'),
        ('min_rr_ratio', '0.8:1', '1.5:1'),
        ('min_vix', '(none)', '15'),
        ('max_vix', '(none)', '25'),
        ('min_gex_ratio_bearish', '(none)', '1.5'),
        ('max_gex_ratio_bullish', '(none)', '0.67'),
    ]

    for param, old, new in comparisons:
        print(f"{param:<25} {old:<15} {new:<15}")

    print("-" * 60)


if __name__ == '__main__':
    show_config_comparison()

    print("\nThis will update the ATHENA database config.")
    response = input("Proceed? [y/N]: ").strip().lower()

    if response == 'y':
        success = update_athena_config()
        sys.exit(0 if success else 1)
    else:
        print("Aborted.")
        sys.exit(0)
