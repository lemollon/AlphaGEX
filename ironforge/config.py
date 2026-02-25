"""
IronForge Configuration (Render/PostgreSQL)
=============================================

Connection settings for PostgreSQL on Render.
"""

import os


class Config:
    """PostgreSQL connection configuration for Render."""

    DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://localhost:5432/ironforge")

    # Tradier API (sandbox for paper trading)
    TRADIER_API_KEY = os.getenv("TRADIER_API_KEY", "")
    TRADIER_BASE_URL = os.getenv(
        "TRADIER_BASE_URL", "https://sandbox.tradier.com/v1"
    )
    # Account ID for sandbox order execution (auto-discovered if blank)
    TRADIER_ACCOUNT_ID = os.getenv("TRADIER_ACCOUNT_ID", "")

    @classmethod
    def validate(cls) -> tuple:
        missing = []
        if not cls.DATABASE_URL:
            missing.append("DATABASE_URL")
        if missing:
            return False, f"Missing env vars: {', '.join(missing)}"
        return True, "OK"
