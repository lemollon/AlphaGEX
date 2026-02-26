"""
PostgreSQL Database Adapter for IronForge
==========================================

Provides database connectivity using psycopg2 via the shared AlphaGEX
database_adapter. Migrated from Databricks SQL to run on Render.
"""

import logging
from contextlib import contextmanager

from database_adapter import get_connection as _get_pg_connection

logger = logging.getLogger(__name__)


def get_connection():
    """Get a PostgreSQL connection from the shared AlphaGEX pool."""
    return _get_pg_connection()


@contextmanager
def db_connection():
    """Context manager for PostgreSQL connections."""
    conn = None
    try:
        conn = get_connection()
        yield conn
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


def _to_python(val):
    """Convert numpy/pandas types to native Python types for database insertion."""
    if val is None:
        return None
    type_name = type(val).__name__
    if 'float' in type_name or 'Float' in type_name:
        return float(val)
    if 'int' in type_name or 'Int' in type_name:
        return int(val)
    if 'bool' in type_name:
        return bool(val)
    if 'str' in type_name:
        return str(val)
    if hasattr(val, 'item'):
        return val.item()
    return val


def table(name: str) -> str:
    """Get table name (no catalog/schema prefix needed for PostgreSQL)."""
    return name
