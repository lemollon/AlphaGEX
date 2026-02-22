"""
Databricks Configuration
========================

Connection settings for Databricks SQL warehouse and catalog.
Set these via environment variables or Databricks secrets.
"""

import os


class DatabricksConfig:
    """Databricks connection configuration."""

    # Databricks SQL Warehouse connection
    SERVER_HOSTNAME = os.getenv("DATABRICKS_SERVER_HOSTNAME", "")
    HTTP_PATH = os.getenv("DATABRICKS_HTTP_PATH", "")
    ACCESS_TOKEN = os.getenv("DATABRICKS_TOKEN", "")

    # Unity Catalog settings
    CATALOG = os.getenv("DATABRICKS_CATALOG", "alpha_prime")
    SCHEMA = os.getenv("DATABRICKS_SCHEMA", "default")

    # Tradier API (for live market data)
    TRADIER_API_KEY = os.getenv("TRADIER_API_KEY", "")
    TRADIER_BASE_URL = "https://api.tradier.com/v1"

    @classmethod
    def get_full_table_name(cls, table: str) -> str:
        """Get fully qualified table name: catalog.schema.table"""
        return f"{cls.CATALOG}.{cls.SCHEMA}.{table}"

    @classmethod
    def validate(cls) -> tuple:
        """Validate required configuration."""
        missing = []
        if not cls.SERVER_HOSTNAME:
            missing.append("DATABRICKS_SERVER_HOSTNAME")
        if not cls.HTTP_PATH:
            missing.append("DATABRICKS_HTTP_PATH")
        if not cls.ACCESS_TOKEN:
            missing.append("DATABRICKS_TOKEN")
        if missing:
            return False, f"Missing env vars: {', '.join(missing)}"
        return True, "OK"
