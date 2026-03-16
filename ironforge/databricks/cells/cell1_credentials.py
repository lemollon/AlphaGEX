# Cell 1: Credentials
# These are set as notebook-level fallbacks. If env vars are already set
# (e.g., via Databricks Job config or cluster env vars), those take priority.
import os

def _set_if_missing(key: str, fallback: str) -> None:
    """Set env var only if not already set (Job/cluster env vars take priority)."""
    if not os.environ.get(key):
        os.environ[key] = fallback

# Tradier production key (for live SPY/VIX quotes)
_set_if_missing("TRADIER_API_KEY", "HbOM7HNC6Ibs6QAE6hYgr02rpx2K")

# Tradier sandbox keys (for FLAME order mirroring)
_set_if_missing("TRADIER_SANDBOX_KEY_USER", "iPidGGnYrhzjp6vGBBQw8HyqF0xj")
_set_if_missing("TRADIER_SANDBOX_KEY_MATT", "AGoNTv6o6GKMKT8uc7ooVNOct0e0")
_set_if_missing("TRADIER_SANDBOX_KEY_LOGAN", "AcDucIMyjeNgFh60LWOb0F5fhXHh")

# Tradier sandbox account IDs (hardcoded — no auto-discover dependency)
_set_if_missing("TRADIER_SANDBOX_ACCOUNT_ID_USER", "VA39284047")
_set_if_missing("TRADIER_SANDBOX_ACCOUNT_ID_MATT", "VA55391129")
_set_if_missing("TRADIER_SANDBOX_ACCOUNT_ID_LOGAN", "VA59240884")

# Databricks catalog/schema
_set_if_missing("DATABRICKS_CATALOG", "alpha_prime")
_set_if_missing("DATABRICKS_SCHEMA", "ironforge")

# Scanner mode (single = Job, loop = notebook testing)
_set_if_missing("SCANNER_MODE", "single")

print(f"Credentials: TRADIER_API_KEY={'set' if os.environ.get('TRADIER_API_KEY') else 'MISSING'}")
print(f"  Sandbox keys: USER={'set' if os.environ.get('TRADIER_SANDBOX_KEY_USER') else 'MISSING'}, "
      f"MATT={'set' if os.environ.get('TRADIER_SANDBOX_KEY_MATT') else 'MISSING'}, "
      f"LOGAN={'set' if os.environ.get('TRADIER_SANDBOX_KEY_LOGAN') else 'MISSING'}")
print(f"  Mode: {os.environ.get('SCANNER_MODE', 'single')}")

