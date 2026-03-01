"""
IronForge Configuration (Render/PostgreSQL)
=============================================

Connection settings for PostgreSQL on Render.
"""

import os


class Config:
    """PostgreSQL connection configuration for Render."""

    DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://localhost:5432/ironforge")

    # Tradier API key (sandbox key — IronForge is a paper trading system)
    TRADIER_API_KEY = os.getenv("TRADIER_API_KEY", "")
    TRADIER_ACCOUNT_ID = os.getenv("TRADIER_ACCOUNT_ID", "")

    # Sandbox URL — IronForge uses sandbox for ALL API calls (quotes + orders)
    TRADIER_SANDBOX_URL = "https://sandbox.tradier.com/v1"
    TRADIER_BASE_URL = os.getenv("TRADIER_BASE_URL", TRADIER_SANDBOX_URL)

    # Three sandbox accounts for FLAME trade mirroring
    # Each needs a key + account ID (matching how FORTRESS does it)
    TRADIER_SANDBOX_KEY_USER = os.getenv("TRADIER_SANDBOX_KEY_USER", "")
    TRADIER_SANDBOX_KEY_MATT = os.getenv("TRADIER_SANDBOX_KEY_MATT", "")
    TRADIER_SANDBOX_KEY_LOGAN = os.getenv("TRADIER_SANDBOX_KEY_LOGAN", "")
    TRADIER_SANDBOX_ACCOUNT_ID_USER = os.getenv("TRADIER_SANDBOX_ACCOUNT_ID_USER", "")
    TRADIER_SANDBOX_ACCOUNT_ID_MATT = os.getenv("TRADIER_SANDBOX_ACCOUNT_ID_MATT", "")
    TRADIER_SANDBOX_ACCOUNT_ID_LOGAN = os.getenv("TRADIER_SANDBOX_ACCOUNT_ID_LOGAN", "")

    @classmethod
    def get_sandbox_accounts(cls) -> list:
        """Return list of configured sandbox accounts for FLAME mirroring."""
        accounts = []
        if cls.TRADIER_SANDBOX_KEY_USER:
            accounts.append({"name": "User", "api_key": cls.TRADIER_SANDBOX_KEY_USER,
                           "account_id": cls.TRADIER_SANDBOX_ACCOUNT_ID_USER})
        if cls.TRADIER_SANDBOX_KEY_MATT:
            accounts.append({"name": "Matt", "api_key": cls.TRADIER_SANDBOX_KEY_MATT,
                           "account_id": cls.TRADIER_SANDBOX_ACCOUNT_ID_MATT})
        if cls.TRADIER_SANDBOX_KEY_LOGAN:
            accounts.append({"name": "Logan", "api_key": cls.TRADIER_SANDBOX_KEY_LOGAN,
                           "account_id": cls.TRADIER_SANDBOX_ACCOUNT_ID_LOGAN})
        return accounts

    @classmethod
    def validate(cls) -> tuple:
        missing = []
        if not cls.DATABASE_URL:
            missing.append("DATABASE_URL")
        if missing:
            return False, f"Missing env vars: {', '.join(missing)}"

        warnings = []
        if not cls.TRADIER_API_KEY:
            warnings.append("TRADIER_API_KEY not set — market data quotes disabled")
        if not cls.TRADIER_ACCOUNT_ID:
            warnings.append("TRADIER_ACCOUNT_ID not set — sandbox orders disabled")
        if not any(cls.get_sandbox_accounts()):
            warnings.append("No sandbox account keys set — FLAME mirroring disabled")

        msg = "OK"
        if warnings:
            msg = f"OK (warnings: {'; '.join(warnings)})"
        return True, msg
