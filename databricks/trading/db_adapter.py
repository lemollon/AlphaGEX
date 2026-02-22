"""
Databricks SQL Adapter
======================

Provides database connectivity using the Databricks SQL connector.
Replaces psycopg2-based database_adapter from the parent AlphaGEX project.
"""

import logging
from contextlib import contextmanager

from databricks import sql as databricks_sql

from config import DatabricksConfig

logger = logging.getLogger(__name__)


def get_connection():
    """Get a Databricks SQL connection."""
    return databricks_sql.connect(
        server_hostname=DatabricksConfig.SERVER_HOSTNAME,
        http_path=DatabricksConfig.HTTP_PATH,
        access_token=DatabricksConfig.ACCESS_TOKEN,
        catalog=DatabricksConfig.CATALOG,
        schema=DatabricksConfig.SCHEMA,
    )


@contextmanager
def db_connection():
    """Context manager for Databricks SQL connections."""
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
    """Get fully qualified table name."""
    return DatabricksConfig.get_full_table_name(name)
