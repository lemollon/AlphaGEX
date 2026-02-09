"""
ML Model Persistence Layer
==========================

Stores trained ML models in PostgreSQL so they persist across Render deploys.
Render uses ephemeral storage, so file-based models (.joblib, .pkl) are lost on redeploy.

Usage:
    from quant.model_persistence import save_model_to_db, load_model_from_db

    # Save after training
    save_model_to_db('gex_probability', model_object, metrics={'accuracy': 0.85})

    # Load at startup
    model = load_model_from_db('gex_probability')

Models stored:
    - gex_probability: GEXSignalGenerator (5 sub-models)
    - gex_directional: GEXDirectionalPredictor
    - fortress_ml: FORTRESS ML Advisor
    - regime_classifier: ML Regime Classifier (per symbol)
"""

import os
import sys
import pickle
import base64
import zlib
import json
from datetime import datetime
from typing import Any, Dict, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def get_connection():
    """Get database connection"""
    import psycopg2
    from urllib.parse import urlparse

    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        raise ValueError("DATABASE_URL not set")

    result = urlparse(database_url)
    return psycopg2.connect(
        host=result.hostname,
        port=result.port or 5432,
        user=result.username,
        password=result.password,
        database=result.path[1:],
        connect_timeout=30
    )


def ensure_table(conn):
    """Create ml_models table if it doesn't exist, and add missing columns"""
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ml_models (
            id SERIAL PRIMARY KEY,
            model_name VARCHAR(100) NOT NULL,
            model_version INTEGER DEFAULT 1,
            model_data BYTEA NOT NULL,
            metrics JSONB,
            training_records INTEGER,
            training_date_start DATE,
            training_date_end DATE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            is_active BOOLEAN DEFAULT TRUE,
            UNIQUE(model_name, model_version)
        )
    """)

    # Add is_active column if it doesn't exist (for existing tables)
    cursor.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'ml_models' AND column_name = 'is_active'
            ) THEN
                ALTER TABLE ml_models ADD COLUMN is_active BOOLEAN DEFAULT TRUE;
            END IF;
        END $$;
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_ml_models_name ON ml_models(model_name)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_ml_models_active ON ml_models(model_name, is_active)
    """)
    conn.commit()


def save_model_to_db(
    model_name: str,
    model: Any,
    metrics: Optional[Dict] = None,
    training_records: Optional[int] = None,
    training_date_start: Optional[str] = None,
    training_date_end: Optional[str] = None
) -> bool:
    """
    Save a trained model to the database.

    Args:
        model_name: Unique identifier (e.g., 'gex_probability', 'gex_directional')
        model: The trained model object (must be picklable)
        metrics: Optional dict of training metrics
        training_records: Number of records used for training
        training_date_start: Start date of training data
        training_date_end: End date of training data

    Returns:
        True if saved successfully
    """
    conn = get_connection()
    ensure_table(conn)
    cursor = conn.cursor()

    try:
        # Serialize and compress the model
        pickled = pickle.dumps(model)
        compressed = zlib.compress(pickled, level=9)

        # Get next version number
        cursor.execute("""
            SELECT COALESCE(MAX(model_version), 0) + 1
            FROM ml_models WHERE model_name = %s
        """, (model_name,))
        next_version = cursor.fetchone()[0]

        # Deactivate old versions
        cursor.execute("""
            UPDATE ml_models SET is_active = FALSE
            WHERE model_name = %s AND is_active = TRUE
        """, (model_name,))

        # Insert new model (use json.dumps for JSONB column)
        cursor.execute("""
            INSERT INTO ml_models (
                model_name, model_version, model_data, metrics,
                training_records, training_date_start, training_date_end,
                is_active
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, TRUE)
        """, (
            model_name,
            next_version,
            compressed,
            json.dumps(metrics if metrics else {}),
            training_records,
            training_date_start,
            training_date_end
        ))

        conn.commit()
        conn.close()

        size_kb = len(compressed) / 1024
        print(f"[model_persistence] Saved {model_name} v{next_version} ({size_kb:.1f} KB)")
        return True

    except Exception as e:
        conn.rollback()
        conn.close()
        print(f"[model_persistence] Error saving {model_name}: {e}")
        return False


def load_model_from_db(model_name: str, version: Optional[int] = None) -> Optional[Any]:
    """
    Load a trained model from the database.

    Args:
        model_name: The model identifier
        version: Specific version to load (default: latest active)

    Returns:
        The model object, or None if not found
    """
    try:
        conn = get_connection()
        ensure_table(conn)
        cursor = conn.cursor()

        if version:
            cursor.execute("""
                SELECT model_data, model_version, metrics, created_at
                FROM ml_models
                WHERE model_name = %s AND model_version = %s
            """, (model_name, version))
        else:
            cursor.execute("""
                SELECT model_data, model_version, metrics, created_at
                FROM ml_models
                WHERE model_name = %s AND is_active = TRUE
                ORDER BY model_version DESC
                LIMIT 1
            """, (model_name,))

        row = cursor.fetchone()
        conn.close()

        if not row:
            print(f"[model_persistence] No model found: {model_name}")
            return None

        model_data, ver, metrics, created_at = row

        # Handle memoryview from psycopg2
        if isinstance(model_data, memoryview):
            model_data = bytes(model_data)

        # Decompress and unpickle
        decompressed = zlib.decompress(model_data)
        model = pickle.loads(decompressed)

        print(f"[model_persistence] Loaded {model_name} v{ver} (trained {created_at})")
        return model

    except Exception as e:
        print(f"[model_persistence] Error loading {model_name}: {e}")
        return None


def delete_model_from_db(model_name: str) -> bool:
    """
    Delete a model from the database.

    Args:
        model_name: The model identifier to delete

    Returns:
        True if deleted successfully, False otherwise
    """
    try:
        conn = get_connection()
        ensure_table(conn)
        cursor = conn.cursor()

        # Delete all versions of this model
        cursor.execute("""
            DELETE FROM ml_models
            WHERE model_name = %s
        """, (model_name,))

        deleted_count = cursor.rowcount
        conn.commit()
        conn.close()

        if deleted_count > 0:
            print(f"[model_persistence] Deleted {deleted_count} version(s) of {model_name}")
            return True
        else:
            print(f"[model_persistence] No model found to delete: {model_name}")
            return True  # Still success - model doesn't exist

    except Exception as e:
        print(f"[model_persistence] Error deleting {model_name}: {e}")
        return False


def get_model_info(model_name: str) -> Optional[Dict]:
    """Get metadata about a stored model without loading it"""
    try:
        conn = get_connection()
        ensure_table(conn)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT model_version, metrics, training_records,
                   training_date_start, training_date_end,
                   created_at, LENGTH(model_data) as size_bytes
            FROM ml_models
            WHERE model_name = %s AND is_active = TRUE
            ORDER BY model_version DESC
            LIMIT 1
        """, (model_name,))

        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return {
            'model_name': model_name,
            'version': row[0],
            'metrics': row[1],
            'training_records': row[2],
            'training_date_start': str(row[3]) if row[3] else None,
            'training_date_end': str(row[4]) if row[4] else None,
            'created_at': str(row[5]),
            'size_kb': row[6] / 1024 if row[6] else 0
        }

    except Exception as e:
        print(f"[model_persistence] Error getting info for {model_name}: {e}")
        return None


def list_models() -> Dict[str, Dict]:
    """List all stored models with their info"""
    try:
        conn = get_connection()
        ensure_table(conn)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT DISTINCT ON (model_name)
                model_name, model_version, metrics, training_records,
                created_at, LENGTH(model_data) as size_bytes
            FROM ml_models
            WHERE is_active = TRUE
            ORDER BY model_name, model_version DESC
        """)

        rows = cursor.fetchall()
        conn.close()

        models = {}
        for row in rows:
            models[row[0]] = {
                'version': row[1],
                'metrics': row[2],
                'training_records': row[3],
                'created_at': str(row[4]),
                'size_kb': row[5] / 1024 if row[5] else 0
            }

        return models

    except Exception as e:
        print(f"[model_persistence] Error listing models: {e}")
        return {}


def model_exists(model_name: str) -> bool:
    """Check if a model exists in the database"""
    info = get_model_info(model_name)
    return info is not None


# Model name constants for consistency
MODEL_GEX_PROBABILITY = 'gex_probability'
MODEL_GEX_DIRECTIONAL = 'gex_directional'
MODEL_FORTRESS_ML = 'fortress_ml'
MODEL_VALOR_ML = 'valor_ml'  # VALOR/VALOR MES futures scalping
MODEL_REGIME_PREFIX = 'regime_'  # + symbol, e.g., 'regime_SPY'


if __name__ == '__main__':
    # Test the module
    print("=" * 60)
    print("ML MODEL PERSISTENCE - DATABASE STATUS")
    print("=" * 60)

    models = list_models()
    if models:
        for name, info in models.items():
            print(f"\n{name}:")
            print(f"  Version: {info['version']}")
            print(f"  Size: {info['size_kb']:.1f} KB")
            print(f"  Training records: {info['training_records']}")
            print(f"  Created: {info['created_at']}")
            if info['metrics']:
                print(f"  Metrics: {info['metrics']}")
    else:
        print("\nNo models stored in database yet.")
        print("\nTo store models after training:")
        print("  from quant.model_persistence import save_model_to_db")
        print("  save_model_to_db('gex_probability', trained_model)")
