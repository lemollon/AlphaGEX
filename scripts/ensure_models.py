#!/usr/bin/env python3
"""
Ensure ML models exist - train them if missing.
Also runs database migrations for new config settings.

This script is designed to run at startup to ensure the GEX ML models
are available. If the models file doesn't exist, it will train them.

Usage:
    python scripts/ensure_models.py

Called automatically from start.sh or Render build command.
"""

import os
import sys

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

MODEL_PATH = "models/gex_signal_generator.joblib"


def ensure_config():
    """Ensure apache_config has all required settings."""
    try:
        from database_adapter import get_connection

        conn = get_connection()
        c = conn.cursor()

        # Add min_rr_ratio if missing
        c.execute("""
            SELECT setting_value FROM apache_config
            WHERE setting_name = 'min_rr_ratio'
        """)
        if not c.fetchone():
            c.execute("""
                INSERT INTO apache_config (setting_name, setting_value, description)
                VALUES ('min_rr_ratio', '0.8', 'Minimum risk:reward ratio for debit spreads (0.8 = realistic for 0DTE)')
            """)
            conn.commit()
            print("[ensure_config] Added min_rr_ratio = 0.8 to apache_config")
        else:
            print("[ensure_config] min_rr_ratio already configured")

        conn.close()
        return True
    except Exception as e:
        print(f"[ensure_config] Warning: {e}")
        return False


def ensure_models():
    """Check if models exist, train if missing."""

    # Create models directory if needed
    os.makedirs("models", exist_ok=True)

    if os.path.exists(MODEL_PATH):
        size_kb = os.path.getsize(MODEL_PATH) // 1024
        print(f"[ensure_models] Models exist: {MODEL_PATH} ({size_kb} KB)")
        return True

    print(f"[ensure_models] Models not found at {MODEL_PATH}")
    print("[ensure_models] Training models... (this may take a minute)")

    try:
        # Import and run the training
        from quant.gex_probability_models import GEXSignalGenerator

        generator = GEXSignalGenerator()

        # Check if we have training data (in ORAT database)
        import psycopg2
        from urllib.parse import urlparse

        db_url = os.environ.get('ORAT_DATABASE_URL') or os.environ.get('DATABASE_URL')
        if not db_url:
            print("[ensure_models] No database URL configured")
            return False

        result = urlparse(db_url)
        conn = psycopg2.connect(
            host=result.hostname,
            port=result.port or 5432,
            user=result.username,
            password=result.password,
            database=result.path[1:],
            connect_timeout=10
        )
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM gex_structure_daily")
        count = c.fetchone()[0]
        conn.close()

        if count < 100:
            print(f"[ensure_models] Not enough training data ({count} records, need 100+)")
            print("[ensure_models] Skipping model training - Prophet will be used instead")
            return False

        print(f"[ensure_models] Found {count} training records")

        # Train the models
        generator.train()
        generator.save(MODEL_PATH)

        size_kb = os.path.getsize(MODEL_PATH) // 1024
        print(f"[ensure_models] Models trained and saved: {MODEL_PATH} ({size_kb} KB)")
        return True

    except Exception as e:
        print(f"[ensure_models] Training failed: {e}")
        print("[ensure_models] Apache will use Prophet fallback (no ML)")
        return False


if __name__ == "__main__":
    # Run config migrations first
    ensure_config()

    # Then ensure models exist
    success = ensure_models()
    sys.exit(0 if success else 1)
