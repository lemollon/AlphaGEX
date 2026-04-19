"""
IronForge Configuration (Render/PostgreSQL)
=============================================

Connection settings for PostgreSQL on Render.

SPARK is the sole real-money production bot. FLAME and INFERNO are paper-only
(sandbox or pure paper). `get_tradier_base_url(bot)` and `get_tradier_api_key(bot)`
route SPARK to the production Tradier endpoint and everyone else to sandbox,
failing loud at resolver-time if SPARK's production credentials are missing.
"""

import os


# Bot that owns real-money production trading. Must stay in sync with
# PRODUCTION_BOT in ironforge/webapp/src/lib/tradier.ts.
PRODUCTION_BOT = "spark"


class MissingProductionCredentials(RuntimeError):
    """Raised when SPARK tries to resolve credentials but the production env
    vars aren't configured. Fail loud at resolver-time rather than silently
    falling back to sandbox on a live-money bot."""


class Config:
    """PostgreSQL + Tradier connection configuration for Render."""

    DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://localhost:5432/ironforge")

    # Tradier market data key (used for quotes regardless of per-bot routing)
    TRADIER_API_KEY = os.getenv("TRADIER_API_KEY", "")
    TRADIER_ACCOUNT_ID = os.getenv("TRADIER_ACCOUNT_ID", "")

    # Base URLs
    TRADIER_SANDBOX_URL = "https://sandbox.tradier.com/v1"
    TRADIER_PROD_URL = "https://api.tradier.com/v1"
    # Back-compat: modules that haven't been migrated to get_tradier_base_url()
    # still read this. Defaults to sandbox so paper bots stay safe.
    TRADIER_BASE_URL = os.getenv("TRADIER_BASE_URL", TRADIER_SANDBOX_URL)

    # Three sandbox accounts for paper-bot mirroring (User/Matt/Logan)
    TRADIER_SANDBOX_KEY_USER = os.getenv("TRADIER_SANDBOX_KEY_USER", "")
    TRADIER_SANDBOX_KEY_MATT = os.getenv("TRADIER_SANDBOX_KEY_MATT", "")
    TRADIER_SANDBOX_KEY_LOGAN = os.getenv("TRADIER_SANDBOX_KEY_LOGAN", "")
    TRADIER_SANDBOX_ACCOUNT_ID_USER = os.getenv("TRADIER_SANDBOX_ACCOUNT_ID_USER", "")
    TRADIER_SANDBOX_ACCOUNT_ID_MATT = os.getenv("TRADIER_SANDBOX_ACCOUNT_ID_MATT", "")
    TRADIER_SANDBOX_ACCOUNT_ID_LOGAN = os.getenv("TRADIER_SANDBOX_ACCOUNT_ID_LOGAN", "")

    # Production credentials (SPARK real-money trading)
    TRADIER_PROD_API_KEY = os.getenv("TRADIER_PROD_API_KEY", "")
    TRADIER_PROD_ACCOUNT_ID = os.getenv("TRADIER_PROD_ACCOUNT_ID", "")

    @classmethod
    def get_sandbox_accounts(cls) -> list:
        """Return list of configured sandbox accounts for paper mirroring."""
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
            warnings.append("No sandbox account keys set — paper mirroring disabled")
        if not cls.TRADIER_PROD_API_KEY:
            warnings.append(
                f"TRADIER_PROD_API_KEY not set — {PRODUCTION_BOT.upper()} production trading disabled"
            )

        msg = "OK"
        if warnings:
            msg = f"OK (warnings: {'; '.join(warnings)})"
        return True, msg


def _normalize_bot(bot_name: str | None) -> str:
    return (bot_name or "").strip().lower()


def get_tradier_base_url(bot_name: str | None) -> str:
    """Resolve the Tradier base URL for the given bot.

    SPARK → production endpoint (api.tradier.com).
    Everyone else → sandbox endpoint (sandbox.tradier.com).

    SPARK callers MUST have TRADIER_PROD_API_KEY configured; we refuse to
    hand out the production URL without a production key so we never place
    real-money orders with a sandbox key.
    """
    bot = _normalize_bot(bot_name)
    if bot == PRODUCTION_BOT:
        if not Config.TRADIER_PROD_API_KEY:
            raise MissingProductionCredentials(
                f"{PRODUCTION_BOT.upper()} requires TRADIER_PROD_API_KEY to place "
                "real-money orders; refusing to return production base URL."
            )
        return Config.TRADIER_PROD_URL
    return Config.TRADIER_SANDBOX_URL


def get_tradier_api_key(bot_name: str | None, person: str | None = None) -> str:
    """Resolve the Tradier API key for the given bot (and optional person).

    SPARK → TRADIER_PROD_API_KEY. Raises if unset.
    Paper bots → per-person sandbox key (falls back to generic TRADIER_API_KEY
    when `person` is not specified).
    """
    bot = _normalize_bot(bot_name)
    if bot == PRODUCTION_BOT:
        key = Config.TRADIER_PROD_API_KEY
        if not key:
            raise MissingProductionCredentials(
                f"{PRODUCTION_BOT.upper()} requires TRADIER_PROD_API_KEY."
            )
        return key

    if person:
        per_person = {
            "User": Config.TRADIER_SANDBOX_KEY_USER,
            "Matt": Config.TRADIER_SANDBOX_KEY_MATT,
            "Logan": Config.TRADIER_SANDBOX_KEY_LOGAN,
        }.get(person, "")
        if per_person:
            return per_person
    return Config.TRADIER_API_KEY


def get_tradier_account_id(bot_name: str | None, person: str | None = None) -> str:
    """Resolve the Tradier account ID for the given bot (and optional person)."""
    bot = _normalize_bot(bot_name)
    if bot == PRODUCTION_BOT:
        acct = Config.TRADIER_PROD_ACCOUNT_ID
        if not acct:
            raise MissingProductionCredentials(
                f"{PRODUCTION_BOT.upper()} requires TRADIER_PROD_ACCOUNT_ID."
            )
        return acct

    if person:
        per_person = {
            "User": Config.TRADIER_SANDBOX_ACCOUNT_ID_USER,
            "Matt": Config.TRADIER_SANDBOX_ACCOUNT_ID_MATT,
            "Logan": Config.TRADIER_SANDBOX_ACCOUNT_ID_LOGAN,
        }.get(person, "")
        if per_person:
            return per_person
    return Config.TRADIER_ACCOUNT_ID


def ensure_production_ready() -> None:
    """Fail-loud guard called at SPARK startup so we never silently run
    SPARK in sandbox after config drift."""
    if not Config.TRADIER_PROD_API_KEY or not Config.TRADIER_PROD_ACCOUNT_ID:
        raise MissingProductionCredentials(
            f"{PRODUCTION_BOT.upper()} startup aborted: TRADIER_PROD_API_KEY and "
            "TRADIER_PROD_ACCOUNT_ID must be set."
        )
