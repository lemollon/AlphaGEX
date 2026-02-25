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
    # Primary key used for market data quotes (any sandbox key works)
    TRADIER_API_KEY = os.getenv("TRADIER_API_KEY", "")
    TRADIER_BASE_URL = os.getenv(
        "TRADIER_BASE_URL", "https://sandbox.tradier.com/v1"
    )
    # Account ID for sandbox order execution (auto-discovered if blank)
    TRADIER_ACCOUNT_ID = os.getenv("TRADIER_ACCOUNT_ID", "")

    # Three sandbox accounts for FLAME trade mirroring
    TRADIER_SANDBOX_KEY_USER = os.getenv("TRADIER_SANDBOX_KEY_USER", "")
    TRADIER_SANDBOX_KEY_MATT = os.getenv("TRADIER_SANDBOX_KEY_MATT", "")
    TRADIER_SANDBOX_KEY_LOGAN = os.getenv("TRADIER_SANDBOX_KEY_LOGAN", "")

    @classmethod
    def get_sandbox_accounts(cls) -> list:
        """Return list of configured sandbox accounts for FLAME mirroring."""
        accounts = []
        if cls.TRADIER_SANDBOX_KEY_USER:
            accounts.append({"name": "User", "api_key": cls.TRADIER_SANDBOX_KEY_USER})
        if cls.TRADIER_SANDBOX_KEY_MATT:
            accounts.append({"name": "Matt", "api_key": cls.TRADIER_SANDBOX_KEY_MATT})
        if cls.TRADIER_SANDBOX_KEY_LOGAN:
            accounts.append({"name": "Logan", "api_key": cls.TRADIER_SANDBOX_KEY_LOGAN})
        return accounts

    @classmethod
    def validate(cls) -> tuple:
        missing = []
        if not cls.DATABASE_URL:
            missing.append("DATABASE_URL")
        if missing:
            return False, f"Missing env vars: {', '.join(missing)}"
        return True, "OK"
