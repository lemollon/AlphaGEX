"""
IronForge Configuration
========================

Connection settings for IronForge trading bots (FLAME/SPARK).
Database handled by shared AlphaGEX DATABASE_URL.
"""

import os


class DatabricksConfig:
    """IronForge configuration (kept as DatabricksConfig for compatibility)."""

    # Tradier API (for live market data)
    TRADIER_API_KEY = os.getenv("TRADIER_API_KEY", "")
    TRADIER_BASE_URL = "https://api.tradier.com/v1"

    @classmethod
    def get_full_table_name(cls, table: str) -> str:
        """Get table name (no catalog prefix needed for PostgreSQL)."""
        return table

    @classmethod
    def validate(cls) -> tuple:
        """Validate required configuration."""
        if not os.getenv("DATABASE_URL"):
            return False, "Missing env var: DATABASE_URL"
        return True, "OK"
