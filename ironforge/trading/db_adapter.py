"""
PostgreSQL Database Adapter
============================

Provides database connectivity using psycopg2 for Render PostgreSQL.
"""

import logging
from contextlib import contextmanager

import psycopg2
import psycopg2.extras

from config import Config

logger = logging.getLogger(__name__)


def get_connection():
    """Get a PostgreSQL connection."""
    conn = psycopg2.connect(Config.DATABASE_URL)
    conn.autocommit = True
    return conn


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
    """Get table name (no catalog prefix needed for PostgreSQL)."""
    return name
