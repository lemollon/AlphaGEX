# Databricks notebook source

# COMMAND ----------

# MAGIC %md
# MAGIC # IronForge Scanner
# MAGIC Scans every 1 minute for FLAME (2DTE), SPARK (1DTE), and INFERNO (0DTE) Iron Condor opportunities on SPY.
# MAGIC
# MAGIC **Just click Run All** — credentials are in Cell 1 below, everything else is automatic.

# COMMAND ----------

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

# COMMAND ----------

# Cell 2: Scanner code (all functions)
import sys
import json
import math
import time
import random
import logging
import traceback
from datetime import datetime, date, timedelta, timezone
from typing import Any, Optional
from decimal import Decimal

import requests

# ---------------------------------------------------------------------------
#  Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("ironforge")

# ---------------------------------------------------------------------------
#  Constants
# ---------------------------------------------------------------------------

SCAN_INTERVAL = 60  # 1 minute
CATALOG = os.environ.get("DATABRICKS_CATALOG", "alpha_prime")
SCHEMA = os.environ.get("DATABRICKS_SCHEMA", "ironforge")

# Per-bot config: sd_multiplier, profit_target_pct, stop_loss_pct, entry_end (HHMM)
BOT_CONFIG = {
    "flame":   {"sd": 1.2, "pt_pct": 0.30, "sl_mult": 1.0, "entry_end": 1400, "max_trades": 1},
    "spark":   {"sd": 1.2, "pt_pct": 0.30, "sl_mult": 1.0, "entry_end": 1400, "max_trades": 1},
    "inferno": {"sd": 1.0, "pt_pct": 0.50, "sl_mult": 2.0, "entry_end": 1430, "max_trades": 0},  # 0 = unlimited
}

BOTS = [
    {"name": "flame",   "dte": "2DTE", "min_dte": 2},
    {"name": "spark",   "dte": "1DTE", "min_dte": 1},
    {"name": "inferno", "dte": "0DTE", "min_dte": 0},
]

# ---------------------------------------------------------------------------
#  Databricks SQL — uses spark.sql() in notebook/job context
#  IMPORTANT: Job task type must be "Notebook" (not "Python script")
#  so that the Databricks runtime injects the spark session.
# ---------------------------------------------------------------------------

# Verify spark is available (injected by Databricks runtime)
try:
    spark  # noqa: F821
    _HAS_SPARK = True
except NameError:
    _HAS_SPARK = False
    log.error(
        "spark is not available. The Job task type must be 'Notebook' "
        "(not 'Python script') so Databricks injects the spark session."
    )


def db_query(sql_str: str, params: Optional[dict] = None) -> list[dict]:
    """Execute a SQL query and return rows as list of dicts."""
    if not _HAS_SPARK:
        raise RuntimeError("spark not available — use Notebook task type")
    try:
        result = spark.sql(sql_str)  # noqa: F821
        rows = result.collect()
        if not rows:
            return []
        columns = result.columns
        return [dict(zip(columns, row)) for row in rows]
    except Exception as e:
        log.error(f"DB query error: {e}\nSQL: {sql_str[:200]}")
        raise


def db_execute(sql_str: str, params: Optional[dict] = None) -> None:
    """Execute a SQL statement (INSERT/UPDATE/DELETE) without returning rows."""
    if not _HAS_SPARK:
        raise RuntimeError("spark not available — use Notebook task type")
    try:
        spark.sql(sql_str)  # noqa: F821
    except Exception as e:
        log.error(f"DB execute error: {e}\nSQL: {sql_str[:200]}")
        raise


def bot_table(bot_name: str, suffix: str) -> str:
    """Build fully-qualified table name: alpha_prime.ironforge.{bot}_{suffix}."""
    return f"{CATALOG}.{SCHEMA}.{bot_name}_{suffix}"


def shared_table(name: str) -> str:
    """Build fully-qualified shared table name: alpha_prime.ironforge.{name}."""
    return f"{CATALOG}.{SCHEMA}.{name}"


def num(val: Any) -> float:
    """Parse a value as float, defaulting to 0."""
    if val is None or val == "":
        return 0.0
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0


def to_int(val: Any) -> int:
    """Parse a value as int, defaulting to 0."""
    if val is None or val == "":
        return 0
    try:
        return int(val)
    except (ValueError, TypeError):
        return 0


# ---------------------------------------------------------------------------
#  Tradier API Client
# ---------------------------------------------------------------------------

SANDBOX_URL = "https://sandbox.tradier.com/v1"


def _get_tradier_api_key() -> str:
    return os.environ.get("TRADIER_API_KEY", "")


def _get_tradier_base_url() -> str:
    # Production URL for quotes — NEVER use sandbox for quotes (stale data)
    return os.environ.get("TRADIER_BASE_URL", "https://api.tradier.com/v1")


def is_tradier_configured() -> bool:
    return bool(_get_tradier_api_key())


def tradier_get(endpoint: str, params: Optional[dict] = None) -> Optional[dict]:
    """Authenticated GET to Tradier API."""
    api_key = _get_tradier_api_key()
    if not api_key:
        return None
    try:
        url = f"{_get_tradier_base_url()}{endpoint}"
        resp = requests.get(
            url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
            },
            params=params or {},
            timeout=15,
        )
        if not resp.ok:
            log.warning(f"Tradier GET {endpoint} returned {resp.status_code}")
            return None
        return resp.json()
    except Exception as e:
        log.error(f"Tradier GET {endpoint} error: {e}")
        return None


def build_occ_symbol(ticker: str, expiration: str, strike: float, option_type: str) -> str:
    """Build OCC option symbol: SPY260228P00585000."""
    d = datetime.strptime(expiration[:10], "%Y-%m-%d")
    yy = d.strftime("%y")
    mm = d.strftime("%m")
    dd = d.strftime("%d")
    strike_part = str(round(strike * 1000)).zfill(8)
    return f"{ticker}{yy}{mm}{dd}{option_type}{strike_part}"


def get_quote(symbol: str) -> Optional[dict]:
    """Get a stock/index quote from Tradier."""
    data = tradier_get("/markets/quotes", {"symbols": symbol})
    if not data:
        return None
    quote = data.get("quotes", {}).get("quote")
    if isinstance(quote, list):
        quote = quote[0] if quote else None
    if not quote or quote.get("last") is None:
        return None
    return {
        "last": float(quote["last"]),
        "bid": float(quote["bid"]) if quote.get("bid") is not None else 0.0,
        "ask": float(quote["ask"]) if quote.get("ask") is not None else 0.0,
        "symbol": quote.get("symbol", symbol),
    }


def get_option_quote(occ_symbol: str) -> Optional[dict]:
    """Get an option quote by OCC symbol."""
    data = tradier_get("/markets/quotes", {"symbols": occ_symbol})
    if not data:
        return None
    quote = data.get("quotes", {}).get("quote")
    if isinstance(quote, list):
        quote = quote[0] if quote else None
    if not quote or quote.get("bid") is None:
        return None
    if data.get("quotes", {}).get("unmatched_symbols"):
        return None
    return {
        "bid": float(quote["bid"]),
        "ask": float(quote["ask"]) if quote.get("ask") is not None else 0.0,
        "last": float(quote["last"]) if quote.get("last") is not None else 0.0,
        "symbol": occ_symbol,
    }


def get_option_expirations(symbol: str) -> list[str]:
    """Get available option expirations for a symbol."""
    data = tradier_get(
        "/markets/options/expirations",
        {"symbol": symbol, "includeAllRoots": "true"},
    )
    if not data:
        return []
    dates = data.get("expirations", {}).get("date")
    if not dates:
        return []
    if isinstance(dates, str):
        return [dates]
    return list(dates)


def get_ic_entry_credit(
    ticker: str,
    expiration: str,
    put_short: float,
    put_long: float,
    call_short: float,
    call_long: float,
) -> Optional[dict]:
    """Get the entry credit for an Iron Condor (sell at bid, buy at ask)."""
    ps_q = get_option_quote(build_occ_symbol(ticker, expiration, put_short, "P"))
    pl_q = get_option_quote(build_occ_symbol(ticker, expiration, put_long, "P"))
    cs_q = get_option_quote(build_occ_symbol(ticker, expiration, call_short, "C"))
    cl_q = get_option_quote(build_occ_symbol(ticker, expiration, call_long, "C"))

    if not all([ps_q, pl_q, cs_q, cl_q]):
        return None

    # Conservative paper fills: sell at bid, buy at ask
    put_credit = ps_q["bid"] - pl_q["ask"]
    call_credit = cs_q["bid"] - cl_q["ask"]

    # Mid-price fallback if negative
    if put_credit <= 0 or call_credit <= 0:
        ps_mid = (ps_q["bid"] + ps_q["ask"]) / 2
        pl_mid = (pl_q["bid"] + pl_q["ask"]) / 2
        cs_mid = (cs_q["bid"] + cs_q["ask"]) / 2
        cl_mid = (cl_q["bid"] + cl_q["ask"]) / 2
        put_credit = max(0, ps_mid - pl_mid)
        call_credit = max(0, cs_mid - cl_mid)

    return {
        "putCredit": round(put_credit, 4),
        "callCredit": round(call_credit, 4),
        "totalCredit": round(put_credit + call_credit, 4),
        "source": "TRADIER_LIVE",
    }


def get_ic_mark_to_market(
    ticker: str,
    expiration: str,
    put_short: float,
    put_long: float,
    call_short: float,
    call_long: float,
) -> Optional[dict]:
    """Get current cost-to-close for an Iron Condor by fetching all 4 leg quotes."""
    ps_q = get_option_quote(build_occ_symbol(ticker, expiration, put_short, "P"))
    pl_q = get_option_quote(build_occ_symbol(ticker, expiration, put_long, "P"))
    cs_q = get_option_quote(build_occ_symbol(ticker, expiration, call_short, "C"))
    cl_q = get_option_quote(build_occ_symbol(ticker, expiration, call_long, "C"))
    spot_q = get_quote(ticker)

    if not all([ps_q, pl_q, cs_q, cl_q]):
        return None

    cost = ps_q["ask"] + cs_q["ask"] - pl_q["bid"] - cl_q["bid"]
    return {
        "cost_to_close": max(0, round(cost, 4)),
        "put_short_bid": ps_q["bid"],
        "put_short_ask": ps_q["ask"],
        "put_long_bid": pl_q["bid"],
        "put_long_ask": pl_q["ask"],
        "call_short_bid": cs_q["bid"],
        "call_short_ask": cs_q["ask"],
        "call_long_bid": cl_q["bid"],
        "call_long_ask": cl_q["ask"],
        "spot_price": spot_q["last"] if spot_q else None,
    }


def validate_mtm(mtm: dict, entry_credit: float) -> tuple:
    """Validate MTM quotes are sane. Returns (is_valid, reason)."""
    # Check for zero/negative values on all legs
    for key in ["put_short_ask", "call_short_ask", "put_long_bid", "call_long_bid"]:
        val = mtm.get(key, 0)
        if val is None or val <= 0:
            return False, f"{key} is zero/negative/None: {val}"

    # Check cost_to_close bounds (should be between 0 and 3x entry)
    ctc = mtm.get("cost_to_close", 0)
    if ctc is None or ctc < 0:
        return False, f"cost_to_close is negative/None: {ctc}"
    if entry_credit > 0 and ctc > entry_credit * 3:
        return False, f"cost_to_close ${ctc:.4f} > 3x entry ${entry_credit:.4f}"

    # Check for inverted markets (ask < bid on any leg)
    for leg in ["put_short", "call_short", "put_long", "call_long"]:
        bid = mtm.get(f"{leg}_bid", 0) or 0
        ask = mtm.get(f"{leg}_ask", 0) or 0
        if ask > 0 and bid > 0 and ask < bid:
            return False, f"{leg} inverted: bid=${bid} > ask=${ask}"

    # Check for wide spreads (ask-bid > 50% of mid)
    for leg in ["put_short", "call_short", "put_long", "call_long"]:
        bid = mtm.get(f"{leg}_bid", 0) or 0
        ask = mtm.get(f"{leg}_ask", 0) or 0
        mid = (bid + ask) / 2 if (bid + ask) > 0 else 0
        if mid > 0.05 and (ask - bid) > mid * 0.5:
            return False, f"{leg} wide spread: bid=${bid} ask=${ask} mid=${mid:.4f}"

    return True, "ok"


# ---------------------------------------------------------------------------
#  Sandbox Order Execution (3 accounts: User, Matt, Logan)
# ---------------------------------------------------------------------------


_SANDBOX_KEY_FALLBACKS: dict[str, str] = {
    "TRADIER_SANDBOX_KEY_USER": "iPidGGnYrhzjp6vGBBQw8HyqF0xj",
    "TRADIER_SANDBOX_KEY_MATT": "AGoNTv6o6GKMKT8uc7ooVNOct0e0",
    "TRADIER_SANDBOX_KEY_LOGAN": "AcDucIMyjeNgFh60LWOb0F5fhXHh",
}


def _get_sandbox_accounts() -> list[dict]:
    """Load sandbox accounts from env vars, with hardcoded fallback keys."""
    accounts = []
    for name, key_env, acct_env in [
        ("User", "TRADIER_SANDBOX_KEY_USER", "TRADIER_SANDBOX_ACCOUNT_ID_USER"),
        ("Matt", "TRADIER_SANDBOX_KEY_MATT", "TRADIER_SANDBOX_ACCOUNT_ID_MATT"),
        ("Logan", "TRADIER_SANDBOX_KEY_LOGAN", "TRADIER_SANDBOX_ACCOUNT_ID_LOGAN"),
    ]:
        key = os.environ.get(key_env, "").strip()
        if not key:
            key = _SANDBOX_KEY_FALLBACKS.get(key_env, "")
        acct_id = os.environ.get(acct_env, "").strip()
        if key:
            accounts.append({"name": name, "api_key": key, "account_id": acct_id})
            log.info(f"Sandbox account loaded: {name} (key={key[:6]}...)")
        else:
            log.warning(f"Sandbox account MISSING: {name} ({key_env} not set)")
    return accounts


_sandbox_accounts: Optional[list[dict]] = None
_account_id_cache: dict[str, str] = {}


def _get_sandbox_accounts_lazy() -> list[dict]:
    global _sandbox_accounts
    if _sandbox_accounts is None:
        _sandbox_accounts = _get_sandbox_accounts()
    return _sandbox_accounts


def _sandbox_get(endpoint: str, params: Optional[dict], api_key: str, retries: int = 2) -> Optional[dict]:
    if not api_key:
        return None
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(
                f"{SANDBOX_URL}{endpoint}",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Accept": "application/json",
                },
                params=params or {},
                timeout=30,
            )
            if resp.ok:
                return resp.json()
            if resp.status_code in (502, 503, 504) and attempt < retries:
                log.warning(f"Sandbox GET {endpoint} HTTP {resp.status_code}, retry {attempt}/{retries}...")
                time.sleep(2 * attempt)
                continue
            log.warning(
                f"Sandbox GET {endpoint} failed: HTTP {resp.status_code} — "
                f"{resp.text[:300]}"
            )
            return None
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            if attempt < retries:
                log.warning(f"Sandbox GET {endpoint} {type(e).__name__}, retry {attempt}/{retries}...")
                time.sleep(2 * attempt)
                continue
            log.warning(f"Sandbox GET {endpoint} {type(e).__name__} after {retries} attempts: {e}")
            return None
        except Exception as e:
            log.warning(f"Sandbox GET {endpoint} exception: {e}")
            return None
    return None


def _sandbox_post(endpoint: str, body: dict, api_key: str) -> Optional[dict]:
    if not api_key:
        return None
    try:
        resp = requests.post(
            f"{SANDBOX_URL}{endpoint}",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data=body,
            timeout=15,
        )
        if resp.ok:
            return resp.json()
        log.warning(
            f"Sandbox POST {endpoint} failed: HTTP {resp.status_code} — "
            f"{resp.text[:300]}"
        )
        return None
    except Exception as e:
        log.warning(f"Sandbox POST {endpoint} exception: {e}")
        return None


def _get_account_id_for_key(api_key: str) -> Optional[str]:
    """Get sandbox account ID — prefer pre-configured, fall back to auto-discover."""
    if api_key in _account_id_cache:
        return _account_id_cache[api_key]

    for acct in _get_sandbox_accounts_lazy():
        if acct["api_key"] == api_key and acct.get("account_id"):
            _account_id_cache[api_key] = acct["account_id"]
            return acct["account_id"]

    data = _sandbox_get("/user/profile", None, api_key)
    if not data:
        log.warning("Auto-discover failed for key — set TRADIER_SANDBOX_ACCOUNT_ID_* env var")
        return None
    account = data.get("profile", {}).get("account")
    if isinstance(account, list):
        account = account[0] if account else None
    if not account:
        return None
    account_id = str(account.get("account_number", ""))
    if account_id:
        _account_id_cache[api_key] = account_id
    return account_id or None


# DEPRECATED: Use open_ic_sandbox_per_account() instead.
# Kept for backwards compatibility with ironforge_api.py legacy paths.
def place_ic_order_all_accounts(
    ticker: str,
    expiration: str,
    put_short: float,
    put_long: float,
    call_short: float,
    call_long: float,
    contracts: int,
    total_credit: float,
    tag: Optional[str] = None,
) -> dict[str, int]:
    """Place an Iron Condor in ALL configured sandbox accounts."""
    results: dict[str, int] = {}
    order_body = {
        "class": "multileg",
        "symbol": ticker,
        "type": "market",
        "duration": "day",
        "option_symbol[0]": build_occ_symbol(ticker, expiration, put_short, "P"),
        "side[0]": "sell_to_open",
        "quantity[0]": str(contracts),
        "option_symbol[1]": build_occ_symbol(ticker, expiration, put_long, "P"),
        "side[1]": "buy_to_open",
        "quantity[1]": str(contracts),
        "option_symbol[2]": build_occ_symbol(ticker, expiration, call_short, "C"),
        "side[2]": "sell_to_open",
        "quantity[2]": str(contracts),
        "option_symbol[3]": build_occ_symbol(ticker, expiration, call_long, "C"),
        "side[3]": "buy_to_open",
        "quantity[3]": str(contracts),
    }
    if tag:
        order_body["tag"] = tag[:255]

    for acct in _get_sandbox_accounts_lazy():
        try:
            account_id = _get_account_id_for_key(acct["api_key"])
            if not account_id:
                continue
            result = _sandbox_post(
                f"/accounts/{account_id}/orders",
                order_body,
                acct["api_key"],
            )
            if result and result.get("order", {}).get("id"):
                results[acct["name"]] = result["order"]["id"]
        except Exception as e:
            log.warning(f"Sandbox IC order failed [{acct['name']}]: {e}")

    return results


# DEPRECATED: Use close_ic_sandbox_per_account() instead.
# Kept for backwards compatibility with ironforge_api.py legacy paths.
def close_ic_order_all_accounts(
    ticker: str,
    expiration: str,
    put_short: float,
    put_long: float,
    call_short: float,
    call_long: float,
    contracts: int,
    close_price: float,
    tag: Optional[str] = None,
) -> dict[str, int]:
    """Close an Iron Condor in ALL configured sandbox accounts."""
    results: dict[str, int] = {}
    order_body = {
        "class": "multileg",
        "symbol": ticker,
        "type": "market",
        "duration": "day",
        "option_symbol[0]": build_occ_symbol(ticker, expiration, put_short, "P"),
        "side[0]": "buy_to_close",
        "quantity[0]": str(contracts),
        "option_symbol[1]": build_occ_symbol(ticker, expiration, put_long, "P"),
        "side[1]": "sell_to_close",
        "quantity[1]": str(contracts),
        "option_symbol[2]": build_occ_symbol(ticker, expiration, call_short, "C"),
        "side[2]": "buy_to_close",
        "quantity[2]": str(contracts),
        "option_symbol[3]": build_occ_symbol(ticker, expiration, call_long, "C"),
        "side[3]": "sell_to_close",
        "quantity[3]": str(contracts),
    }
    if tag:
        order_body["tag"] = tag[:255]

    for acct in _get_sandbox_accounts_lazy():
        try:
            account_id = _get_account_id_for_key(acct["api_key"])
            if not account_id:
                continue
            endpoint = f"/accounts/{account_id}/orders"
            # Attempt 1: 4-leg multileg market order
            result = _sandbox_post(endpoint, order_body, acct["api_key"])
            if result and result.get("order", {}).get("id"):
                results[acct["name"]] = result["order"]["id"]
                continue
            # Attempt 2: retry same 4-leg multileg market order after 1s
            log.warning(f"Sandbox IC close attempt 1 failed [{acct['name']}], retrying...")
            time.sleep(1)
            result = _sandbox_post(endpoint, order_body, acct["api_key"])
            if result and result.get("order", {}).get("id"):
                results[acct["name"]] = result["order"]["id"]
            else:
                # Do NOT decompose to individual legs — log error and move on
                log.error(
                    f"Sandbox IC close FAILED after 2 attempts [{acct['name']}] — "
                    f"paper position closed but sandbox may have orphan. "
                    f"DO NOT close individual legs."
                )
        except Exception as e:
            log.warning(f"Sandbox IC close failed [{acct['name']}]: {e}")

    return results


def open_ic_sandbox_per_account(
    ticker: str,
    expiration: str,
    put_short: float,
    put_long: float,
    call_short: float,
    call_long: float,
    collateral_per_contract: float,
    tag: Optional[str] = None,
) -> dict[str, dict]:
    """Open an IC in each sandbox account, sized independently by buying power.

    Returns: {"User": {"order_id": 123, "contracts": 215}, ...}
    """
    results: dict[str, dict] = {}
    occ_ps = build_occ_symbol(ticker, expiration, put_short, "P")
    occ_pl = build_occ_symbol(ticker, expiration, put_long, "P")
    occ_cs = build_occ_symbol(ticker, expiration, call_short, "C")
    occ_cl = build_occ_symbol(ticker, expiration, call_long, "C")

    for acct in _get_sandbox_accounts_lazy():
        try:
            acct_id = _get_account_id_for_key(acct["api_key"])
            if not acct_id:
                continue

            # Query this account's own buying power
            acct_bp = _get_sandbox_buying_power(acct["api_key"], acct_id)
            if acct_bp is None or acct_bp <= 0:
                log.warning(f"Sandbox [{acct['name']}]: no buying power (BP={acct_bp})")
                continue
            if collateral_per_contract <= 0:
                log.warning(f"Sandbox [{acct['name']}]: bad collateral_per={collateral_per_contract}")
                continue
            if acct_bp < collateral_per_contract:
                log.warning(
                    f"Sandbox [{acct['name']}]: BP=${acct_bp:.2f} insufficient "
                    f"(need ${collateral_per_contract:.2f}/contract)"
                )
                continue

            acct_usable = acct_bp * 0.85
            acct_contracts = max(1, math.floor(acct_usable / collateral_per_contract))

            log.info(
                f"Sandbox [{acct['name']}]: BP=${acct_bp:,.0f} → "
                f"usable=${acct_usable:,.0f} → {acct_contracts} contracts "
                f"(collateral/contract=${collateral_per_contract:.2f})"
            )

            order_body = {
                "class": "multileg",
                "symbol": ticker,
                "type": "market",
                "duration": "day",
                "option_symbol[0]": occ_ps, "side[0]": "sell_to_open", "quantity[0]": str(acct_contracts),
                "option_symbol[1]": occ_pl, "side[1]": "buy_to_open",  "quantity[1]": str(acct_contracts),
                "option_symbol[2]": occ_cs, "side[2]": "sell_to_open", "quantity[2]": str(acct_contracts),
                "option_symbol[3]": occ_cl, "side[3]": "buy_to_open",  "quantity[3]": str(acct_contracts),
            }
            if tag:
                order_body["tag"] = tag[:255]

            result = _sandbox_post(
                f"/accounts/{acct_id}/orders",
                order_body,
                acct["api_key"],
            )
            if result and result.get("order", {}).get("id"):
                order_id = result["order"]["id"]
                results[acct["name"]] = {
                    "order_id": order_id,
                    "contracts": acct_contracts,
                }
                log.info(
                    f"Sandbox IC OPEN OK [{acct['name']}]: "
                    f"order_id={order_id} x{acct_contracts}"
                )
            else:
                log.warning(f"Sandbox IC OPEN FAILED [{acct['name']}]: no order ID returned")
        except Exception as e:
            log.warning(f"Sandbox IC order failed [{acct['name']}]: {e}")

    return results


def close_ic_sandbox_per_account(
    ticker: str,
    expiration: str,
    put_short: float,
    put_long: float,
    call_short: float,
    call_long: float,
    paper_contracts: int,
    sb_open_info: dict,
    tag: Optional[str] = None,
) -> dict[str, int]:
    """Close an IC in each sandbox account using per-account contract counts.

    sb_open_info: the parsed sandbox_order_id JSON from the position.
    Handles both new format {"User": {"order_id": X, "contracts": Y}} and
    legacy format {"User": 12345}.  Falls back to paper_contracts if missing.

    Cascade close strategy:
      1. 4-leg multileg close (2 attempts)
      2. 2 × 2-leg spread close (put spread + call spread)
      3. 4 individual leg closes

    Returns: {"User": order_id, "Matt": order_id, ...}
    """
    results: dict[str, int] = {}
    occ_ps = build_occ_symbol(ticker, expiration, put_short, "P")
    occ_pl = build_occ_symbol(ticker, expiration, put_long, "P")
    occ_cs = build_occ_symbol(ticker, expiration, call_short, "C")
    occ_cl = build_occ_symbol(ticker, expiration, call_long, "C")

    for acct in _get_sandbox_accounts_lazy():
        try:
            acct_id = _get_account_id_for_key(acct["api_key"])
            if not acct_id:
                log.warning(f"Sandbox close SKIP [{acct['name']}]: no account_id resolved")
                continue

            # Determine how many contracts this account opened
            acct_info = sb_open_info.get(acct["name"], {})
            if isinstance(acct_info, dict):
                close_qty = acct_info.get("contracts", paper_contracts)
            else:
                # Legacy format: {"User": 12345} (just order_id)
                close_qty = paper_contracts

            log.info(
                f"Sandbox close attempting [{acct['name']}]: "
                f"acct_id={acct_id}, qty={close_qty}"
            )

            tag_str = tag[:255] if tag else ""

            # --- Stage 1: 4-leg multileg close (2 attempts) ---
            order_body_4leg = {
                "class": "multileg",
                "symbol": ticker,
                "type": "market",
                "duration": "day",
                "option_symbol[0]": occ_ps, "side[0]": "buy_to_close",  "quantity[0]": str(close_qty),
                "option_symbol[1]": occ_pl, "side[1]": "sell_to_close", "quantity[1]": str(close_qty),
                "option_symbol[2]": occ_cs, "side[2]": "buy_to_close",  "quantity[2]": str(close_qty),
                "option_symbol[3]": occ_cl, "side[3]": "sell_to_close", "quantity[3]": str(close_qty),
            }
            if tag_str:
                order_body_4leg["tag"] = tag_str

            result = _sandbox_post(
                f"/accounts/{acct_id}/orders", order_body_4leg, acct["api_key"],
            )
            if result and result.get("order", {}).get("id"):
                results[acct["name"]] = result["order"]["id"]
                log.info(
                    f"Sandbox IC CLOSE OK [{acct['name']}]: "
                    f"order_id={result['order']['id']} x{close_qty}"
                )
                continue

            # Retry 4-leg after 1s
            log.warning(f"Sandbox IC close 4-leg attempt 1 failed [{acct['name']}], retrying...")
            time.sleep(1)
            result = _sandbox_post(
                f"/accounts/{acct_id}/orders", order_body_4leg, acct["api_key"],
            )
            if result and result.get("order", {}).get("id"):
                results[acct["name"]] = result["order"]["id"]
                log.info(
                    f"Sandbox IC CLOSE OK [{acct['name']}] (4-leg retry): "
                    f"order_id={result['order']['id']} x{close_qty}"
                )
                continue

            # --- Stage 2: 2 × 2-leg spread close ---
            log.warning(
                f"Sandbox IC close 4-leg FAILED [{acct['name']}] — "
                f"falling back to 2x 2-leg spreads"
            )
            put_spread_body = {
                "class": "multileg",
                "symbol": ticker,
                "type": "market",
                "duration": "day",
                "option_symbol[0]": occ_ps, "side[0]": "buy_to_close",  "quantity[0]": str(close_qty),
                "option_symbol[1]": occ_pl, "side[1]": "sell_to_close", "quantity[1]": str(close_qty),
            }
            if tag_str:
                put_spread_body["tag"] = tag_str

            call_spread_body = {
                "class": "multileg",
                "symbol": ticker,
                "type": "market",
                "duration": "day",
                "option_symbol[0]": occ_cs, "side[0]": "buy_to_close",  "quantity[0]": str(close_qty),
                "option_symbol[1]": occ_cl, "side[1]": "sell_to_close", "quantity[1]": str(close_qty),
            }
            if tag_str:
                call_spread_body["tag"] = tag_str

            put_ok = _sandbox_post(
                f"/accounts/{acct_id}/orders", put_spread_body, acct["api_key"],
            )
            call_ok = _sandbox_post(
                f"/accounts/{acct_id}/orders", call_spread_body, acct["api_key"],
            )

            put_id = put_ok.get("order", {}).get("id") if put_ok else None
            call_id = call_ok.get("order", {}).get("id") if call_ok else None

            if put_id and call_id:
                results[acct["name"]] = put_id  # store first order ID
                log.info(
                    f"Sandbox IC CLOSE OK [{acct['name']}] (2x2-leg): "
                    f"put_order={put_id} call_order={call_id} x{close_qty}"
                )
                continue

            # --- Stage 3: 4 individual leg closes ---
            log.warning(
                f"Sandbox IC close 2-leg FAILED [{acct['name']}] "
                f"(put={'OK' if put_id else 'FAIL'}, call={'OK' if call_id else 'FAIL'}) — "
                f"falling back to 4 individual legs"
            )
            individual_legs = [
                (occ_ps, "buy_to_close",  "put_short"),
                (occ_pl, "sell_to_close", "put_long"),
                (occ_cs, "buy_to_close",  "call_short"),
                (occ_cl, "sell_to_close", "call_long"),
            ]
            any_ok = False
            for occ, side, label in individual_legs:
                # Skip legs already closed by a partial 2-leg success
                if label.startswith("put") and put_id:
                    continue
                if label.startswith("call") and call_id:
                    continue

                leg_body = {
                    "class": "option",
                    "symbol": ticker,
                    "option_symbol": occ,
                    "side": side,
                    "quantity": str(close_qty),
                    "type": "market",
                    "duration": "day",
                }
                if tag_str:
                    leg_body["tag"] = tag_str

                leg_result = _sandbox_post(
                    f"/accounts/{acct_id}/orders", leg_body, acct["api_key"],
                )
                leg_id = leg_result.get("order", {}).get("id") if leg_result else None
                if leg_id:
                    any_ok = True
                    log.info(f"Sandbox leg CLOSE OK [{acct['name']}]: {label} order_id={leg_id}")
                else:
                    log.error(f"Sandbox leg CLOSE FAILED [{acct['name']}]: {label}")

            if any_ok:
                results[acct["name"]] = -1  # flag that cascade was used
                log.info(f"Sandbox IC CLOSE [{acct['name']}]: cascade completed (individual legs)")
            else:
                log.error(
                    f"Sandbox IC close FAILED ALL strategies [{acct['name']}] — "
                    f"sandbox ORPHAN likely. Manual cleanup required."
                )
        except Exception as e:
            log.warning(f"Sandbox IC close failed [{acct['name']}]: {e}")

    return results


def _get_sandbox_order_fill_price(api_key: str, account_id: str, order_id: int) -> Optional[float]:
    """Query a sandbox order and return the average fill price.

    Tries up to 3 times with 1-second delay between attempts,
    because sandbox orders may take a moment to fill.
    """
    for attempt in range(3):
        data = _sandbox_get(
            f"/accounts/{account_id}/orders/{order_id}",
            None,
            api_key,
        )
        if not data:
            time.sleep(1)
            continue

        order = data.get("order", {})
        status = order.get("status", "")

        if status == "filled":
            # For multileg orders, avg_fill_price is on the order level
            avg_fill = order.get("avg_fill_price")
            if avg_fill is not None:
                return abs(float(avg_fill))

            # Fallback: calculate from leg fills
            legs = order.get("leg", [])
            if isinstance(legs, dict):
                legs = [legs]
            if legs:
                total = 0.0
                for leg in legs:
                    side = leg.get("side", "")
                    fill = float(leg.get("avg_fill_price") or 0)
                    if "sell" in side:
                        total += fill  # credit
                    else:
                        total -= fill  # debit
                return abs(total) if total != 0 else None

        if status in ("pending", "open", "partially_filled"):
            time.sleep(1)
            continue

        # rejected, canceled, expired — no fill
        log.warning(f"Sandbox order {order_id} status={status}, no fill price")
        return None

    log.warning(f"Sandbox order {order_id} not filled after 3 attempts")
    return None


def _get_sandbox_buying_power(api_key: str, account_id: str) -> Optional[float]:
    """Get the available buying power from a Tradier sandbox account."""
    data = _sandbox_get(
        f"/accounts/{account_id}/balances",
        None,
        api_key,
    )
    if not data:
        return None
    balances = data.get("balances", {})
    # PDT accounts nest buying power under "pdt" sub-object
    pdt = balances.get("pdt", {})
    bp = (
        pdt.get("option_buying_power")
        or balances.get("option_buying_power")
        or balances.get("buying_power")
    )
    if bp is not None:
        return float(bp)
    return None


# ---------------------------------------------------------------------------
#  Market Hours (Central Time)
# ---------------------------------------------------------------------------


def get_central_time() -> datetime:
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo("America/Chicago"))


def is_market_open(ct: datetime) -> bool:
    """Check if within monitoring window: weekday, 8:30 AM - 3:00 PM CT."""
    dow = ct.weekday()
    if dow >= 5:
        return False
    hhmm = ct.hour * 100 + ct.minute
    return 830 <= hhmm <= 1500


# Pre-market warm-up window: 8:20-8:29 CT weekdays.
# When the cron fires in this window, the scanner waits for market open
# instead of exiting immediately.  This keeps the cluster warm so the
# 8:30 run has zero cold-start delay.
WARMUP_START = 820   # 8:20 AM CT
WARMUP_END   = 829   # 8:29 AM CT (inclusive)


def is_in_warmup_window(ct: datetime) -> bool:
    """Check if within pre-market warm-up window: weekday, 8:20-8:29 CT."""
    if ct.weekday() >= 5:
        return False
    hhmm = ct.hour * 100 + ct.minute
    return WARMUP_START <= hhmm <= WARMUP_END


def is_in_entry_window(ct: datetime, entry_end: int = 1400) -> bool:
    """Check if within entry window: weekday, 8:30 AM - entry_end CT."""
    dow = ct.weekday()
    if dow >= 5:
        return False
    hhmm = ct.hour * 100 + ct.minute
    return 830 <= hhmm <= entry_end


def is_after_eod_cutoff(ct: datetime) -> bool:
    """Check if past EOD cutoff: 2:45 PM CT."""
    hhmm = ct.hour * 100 + ct.minute
    return hhmm >= 1445


def get_sliding_profit_target(ct: datetime, base_pt: float = 0.30, bot_name: str = "") -> tuple:
    """
    Return (profit_target_fraction, tier_label) based on current CT time.

    The profit target slides DOWN as the day progresses — based on CURRENT
    time, not when the trade was opened.

    For FLAME/SPARK (base_pt=0.30):
        8:30 AM – 10:29 AM  → 30%  (MORNING)
        10:30 AM – 12:59 PM → 20%  (MIDDAY)
        1:00 PM – 2:44 PM   → 15%  (AFTERNOON)

    For INFERNO (base_pt=0.50):
        8:30 AM – 10:29 AM  → 50%  (MORNING)
        10:30 AM – 12:59 PM → 30%  (MIDDAY)
        1:00 PM – 2:44 PM   → 10%  (AFTERNOON)

    2:45 PM+ → handled by EOD cutoff (close at any P&L)
    """
    time_minutes = ct.hour * 60 + ct.minute
    is_inferno = bot_name == "inferno"

    if time_minutes < 630:       # before 10:30 AM CT
        return base_pt, "MORNING"
    elif time_minutes < 780:     # before 1:00 PM CT
        if is_inferno:
            return 0.30, "MIDDAY"
        return max(0.10, base_pt - 0.10), "MIDDAY"
    else:
        if is_inferno:
            return 0.10, "AFTERNOON"
        return max(0.10, base_pt - 0.15), "AFTERNOON"


# ---------------------------------------------------------------------------
#  Advisor — evaluates trading conditions
# ---------------------------------------------------------------------------


def evaluate_advisor(vix: float, spot: float, expected_move: float, dte_mode: str) -> dict:
    """Lightweight advisor that scores trading conditions."""
    BASE_WP = 0.65
    win_prob = BASE_WP
    factors: list[tuple[str, float]] = []

    # VIX scoring
    if 15 <= vix <= 22:
        a = 0.10
        win_prob += a
        factors.append(("VIX_IDEAL", a))
    elif vix < 15:
        a = -0.05
        win_prob += a
        factors.append(("VIX_LOW_PREMIUMS", a))
    elif vix <= 28:
        a = -0.05
        win_prob += a
        factors.append(("VIX_ELEVATED", a))
    else:
        a = -0.15
        win_prob += a
        factors.append(("VIX_HIGH_RISK", a))

    # Day of week
    ct = get_central_time()
    py_dow = ct.weekday()
    js_dow = (py_dow + 1) % 7

    if 2 <= js_dow <= 4:  # Tue-Thu
        a = 0.08
        win_prob += a
        factors.append(("DAY_OPTIMAL", a))
    elif js_dow == 1:  # Mon
        a = 0.03
        win_prob += a
        factors.append(("DAY_MONDAY", a))
    elif js_dow == 5:  # Fri
        a = -0.10
        win_prob += a
        factors.append(("DAY_FRIDAY_RISK", a))
    else:
        a = -0.20
        win_prob += a
        factors.append(("DAY_WEEKEND", a))

    # Expected move ratio
    em_ratio = (expected_move / spot * 100) if spot > 0 else 1.0
    if em_ratio < 1.0:
        a = 0.08
        win_prob += a
        factors.append(("EM_TIGHT", a))
    elif em_ratio <= 2.0:
        factors.append(("EM_NORMAL", 0))
    else:
        a = -0.08
        win_prob += a
        factors.append(("EM_WIDE", a))

    # DTE factor
    if dte_mode == "2DTE":
        a = 0.03
        win_prob += a
        factors.append(("DTE_2DAY_DECAY", a))
    elif dte_mode == "0DTE":
        a = -0.05
        win_prob += a
        factors.append(("DTE_0DAY_AGGRESSIVE", a))
    else:
        a = -0.02
        win_prob += a
        factors.append(("DTE_1DAY_TIGHT", a))

    win_prob = max(0.10, min(0.95, win_prob))

    pos_count = sum(1 for _, a in factors if a > 0)
    neg_count = sum(1 for _, a in factors if a < 0)
    total = len(factors)

    if pos_count == total:
        confidence = 0.85
    elif neg_count == total:
        confidence = 0.25
    elif pos_count > neg_count:
        confidence = 0.60 + (pos_count / total) * 0.20
    else:
        confidence = 0.40

    confidence = max(0.10, min(0.95, confidence))

    if win_prob >= 0.60 and confidence >= 0.50:
        advice = "TRADE_FULL"
    elif win_prob >= 0.42 and confidence >= 0.35:
        advice = "TRADE_REDUCED"
    else:
        advice = "SKIP"

    return {
        "advice": advice,
        "winProbability": round(win_prob, 4),
        "confidence": round(confidence, 4),
        "topFactors": factors,
        "reasoning": f"Advisor: {advice} WP={win_prob:.2f} conf={confidence:.2f}",
    }


# ---------------------------------------------------------------------------
#  Strike Calculation
# ---------------------------------------------------------------------------


def calculate_strikes(spot: float, expected_move: float, sd_mult: float = 1.2) -> dict:
    """Calculate IC strikes using SD multiplier, $5 width."""
    SD = sd_mult
    WIDTH = 5

    min_em = spot * 0.005
    em = max(expected_move, min_em)

    put_short = math.floor(spot - SD * em)
    call_short = math.ceil(spot + SD * em)
    put_long = put_short - WIDTH
    call_long = call_short + WIDTH

    if call_short <= put_short:
        put_short = math.floor(spot - spot * 0.02)
        call_short = math.ceil(spot + spot * 0.02)
        put_long = put_short - WIDTH
        call_long = call_short + WIDTH

    return {
        "putShort": put_short,
        "putLong": put_long,
        "callShort": call_short,
        "callLong": call_long,
    }


def get_target_expiration(min_dte: int) -> str:
    """Find target expiration N trading days out."""
    target = datetime.now()
    counted = 0
    while counted < min_dte:
        target += timedelta(days=1)
        if target.weekday() < 5:
            counted += 1
    return target.strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
#  Close Position
# ---------------------------------------------------------------------------


def close_position(
    bot: dict,
    position_id: str,
    ticker: str,
    expiration: str,
    put_short: float,
    put_long: float,
    call_short: float,
    call_long: float,
    contracts: int,
    entry_credit: float,
    collateral: float,
    reason: str,
    close_price: Optional[float] = None,
) -> None:
    """Close a position: update DB, paper account, PDT, sandbox mirror, logs."""
    # Start with the provided or calculated close price as fallback
    price = close_price if close_price is not None else 0.0
    if close_price is None and is_tradier_configured():
        mtm = get_ic_mark_to_market(
            ticker, expiration, put_short, put_long, call_short, call_long
        )
        price = mtm["cost_to_close"] if mtm else 0.0

    price_source = "calculated"
    sandbox_fill_price = None  # track sandbox fill separately (never overwrites paper price)

    # -------------------------------------------------------------------
    # For FLAME: close each sandbox account with its OWN contract count
    # (read from sandbox_order_id stored at open).  Uses cascade close:
    # 4-leg → 2×2-leg → 4 individual legs.
    # For SPARK: no sandbox.
    # -------------------------------------------------------------------
    if bot["name"] == "flame":
        try:
            # Read per-account open info from the position's sandbox_order_id column
            sb_rows = db_query(f"""
                SELECT sandbox_order_id
                FROM {bot_table(bot['name'], 'positions')}
                WHERE position_id = '{position_id}' AND dte_mode = '{bot['dte']}'
            """)
            sb_json_str = sb_rows[0].get("sandbox_order_id", "") if sb_rows else ""
            sb_open_info: dict = {}
            if sb_json_str:
                try:
                    sb_open_info = json.loads(sb_json_str)
                except (json.JSONDecodeError, TypeError):
                    log.warning(f"Failed to parse sandbox_order_id JSON: {sb_json_str[:200]}")

            log.info(
                f"Sandbox close: position={position_id[:20]} "
                f"sb_open_info keys={list(sb_open_info.keys())} "
                f"paper_contracts={contracts}"
            )

            # Delegate to shared function (cascade: 4-leg → 2×2-leg → individual)
            close_results = close_ic_sandbox_per_account(
                ticker, expiration,
                put_short, put_long, call_short, call_long,
                contracts, sb_open_info,
                tag=position_id,
            )

            # Get actual fill price from User's close order (do NOT overwrite paper price)
            user_order_id = close_results.get("User")
            if user_order_id and user_order_id > 0:
                try:
                    user_accts = [a for a in _get_sandbox_accounts_lazy() if a["name"] == "User"]
                    if user_accts:
                        user_acct = user_accts[0]
                        user_acct_id = _get_account_id_for_key(user_acct["api_key"])
                        if user_acct_id:
                            fill_price = _get_sandbox_order_fill_price(
                                user_acct["api_key"], user_acct_id, user_order_id
                            )
                            if fill_price is not None and fill_price >= 0:
                                sandbox_fill_price = fill_price
                                delta_pct = (
                                    round(abs(fill_price - price) / price * 100, 1)
                                    if price > 0 else 0
                                )
                                log.info(
                                    f"Sandbox fill: ${fill_price:.4f} vs "
                                    f"scanner MTM: ${price:.4f} "
                                    f"(delta: {delta_pct}%)"
                                )
                except Exception as e:
                    log.warning(f"Could not get User sandbox fill price: {e}")
        except Exception as e:
            log.warning(f"Sandbox close failed for {position_id}: {e}")

    pnl_per_contract = (entry_credit - price) * 100
    realized_pnl = round(pnl_per_contract * contracts, 2)

    now_ts = get_central_time().strftime("%Y-%m-%d %H:%M:%S")
    today_str = get_central_time().strftime("%Y-%m-%d")

    db_execute(f"""
        UPDATE {bot_table(bot['name'], 'positions')}
        SET status = 'closed',
            close_time = CAST('{now_ts}' AS TIMESTAMP),
            close_price = {price},
            realized_pnl = {realized_pnl},
            close_reason = '{reason}',
            updated_at = CAST('{now_ts}' AS TIMESTAMP)
        WHERE position_id = '{position_id}'
          AND status = 'open'
          AND dte_mode = '{bot['dte']}'
    """)

    db_execute(f"""
        UPDATE {bot_table(bot['name'], 'paper_account')}
        SET current_balance = current_balance + {realized_pnl},
            cumulative_pnl = cumulative_pnl + {realized_pnl},
            total_trades = total_trades + 1,
            collateral_in_use = GREATEST(0, collateral_in_use - {collateral}),
            buying_power = buying_power + {collateral} + {realized_pnl},
            high_water_mark = GREATEST(high_water_mark, current_balance + {realized_pnl}),
            max_drawdown = GREATEST(max_drawdown,
                GREATEST(high_water_mark, current_balance + {realized_pnl}) - (current_balance + {realized_pnl})),
            updated_at = CAST('{now_ts}' AS TIMESTAMP)
        WHERE is_active = TRUE AND dte_mode = '{bot['dte']}'
    """)

    db_execute(f"""
        UPDATE {bot_table(bot['name'], 'pdt_log')}
        SET closed_at = CAST('{now_ts}' AS TIMESTAMP),
            exit_cost = {price},
            pnl = {realized_pnl},
            close_reason = '{reason}',
            is_day_trade = (CAST(opened_at AS DATE) = CAST('{today_str}' AS DATE))
        WHERE position_id = '{position_id}'
          AND dte_mode = '{bot['dte']}'
    """)

    # Post-close: if same-day open+close = day trade, increment PDT counter
    try:
        pos_row = db_query(f"""
            SELECT open_time
            FROM {bot_table(bot['name'], 'positions')}
            WHERE position_id = '{position_id}' AND dte_mode = '{bot['dte']}'
            LIMIT 1
        """)
        open_date_str = str(pos_row[0]["open_time"])[:10] if pos_row else None
        if open_date_str == today_str:
            bot_upper = bot["name"].upper()
            pdt_row = db_query(f"""
                SELECT day_trade_count
                FROM {shared_table('ironforge_pdt_config')}
                WHERE bot_name = '{bot_upper}'
                LIMIT 1
            """)
            old_count = to_int(pdt_row[0]["day_trade_count"]) if pdt_row else 0
            new_count = old_count + 1
            db_execute(f"""
                UPDATE {shared_table('ironforge_pdt_config')}
                SET day_trade_count = {new_count},
                    updated_at = CURRENT_TIMESTAMP()
                WHERE bot_name = '{bot_upper}'
            """)
            old_json = json.dumps({"day_trade_count": old_count}).replace("'", "''")
            new_json = json.dumps({"day_trade_count": new_count}).replace("'", "''")
            reason_txt = f"Day trade: {position_id} opened+closed on {today_str}".replace("'", "''")
            db_execute(f"""
                INSERT INTO {shared_table('ironforge_pdt_log')}
                    (log_id, bot_name, action, old_value, new_value, reason, performed_by, created_at)
                VALUES (
                    UUID(), '{bot_upper}', 'day_trade_recorded',
                    '{old_json}', '{new_json}',
                    '{reason_txt}', 'scanner',
                    CURRENT_TIMESTAMP()
                )
            """)
            log.info(f"{bot_upper} PDT: day trade recorded, count {old_count}→{new_count}")
    except Exception as pdt_err:
        log.warning(f"PDT counter update failed: {pdt_err}")

    fill_delta_pct = (
        round(abs(sandbox_fill_price - price) / price * 100, 1)
        if sandbox_fill_price is not None and price > 0 else None
    )
    details = json.dumps({
        "position_id": position_id,
        "scanner_close_price": price,
        "sandbox_fill_price": sandbox_fill_price,
        "fill_delta_pct": fill_delta_pct,
        "price_source": price_source,
        "realized_pnl": realized_pnl,
        "close_reason": reason,
        "source": "scanner",
    })
    db_execute(f"""
        INSERT INTO {bot_table(bot['name'], 'logs')}
            (log_time, level, message, details, dte_mode)
        VALUES (
            CURRENT_TIMESTAMP(),
            'TRADE_CLOSE',
            'AUTO CLOSE: {position_id} @ ${price:.4f} P&L=${realized_pnl:.2f} [{reason}] ({price_source})',
            '{details.replace(chr(39), chr(39)+chr(39))}',
            '{bot['dte']}'
        )
    """)

    db_execute(f"""
        MERGE INTO {bot_table(bot['name'], 'daily_perf')} AS t
        USING (SELECT CURRENT_DATE() AS trade_date) AS s
        ON t.trade_date = s.trade_date
        WHEN MATCHED THEN UPDATE SET
            positions_closed = t.positions_closed + 1,
            realized_pnl = t.realized_pnl + {realized_pnl},
            updated_at = CURRENT_TIMESTAMP()
        WHEN NOT MATCHED THEN INSERT
            (trade_date, trades_executed, positions_closed, realized_pnl, updated_at)
        VALUES (CURRENT_DATE(), 0, 1, {realized_pnl}, CURRENT_TIMESTAMP())
    """)

    log.info(
        f"{bot['name'].upper()} CLOSED {position_id}: "
        f"${realized_pnl:.2f} [{reason}] ({price_source})"
    )


# ---------------------------------------------------------------------------
#  Monitor Position
# ---------------------------------------------------------------------------


def _monitor_single_position(bot: dict, pos: dict, ct: datetime) -> dict:
    """Monitor a single open position for PT/SL/EOD/stale holdover close."""
    cfg = BOT_CONFIG.get(bot["name"], BOT_CONFIG["flame"])
    entry_credit = num(pos["total_credit"])
    contracts = to_int(pos["contracts"])
    collateral = num(pos["collateral_required"])
    pt_pct, pt_tier = get_sliding_profit_target(ct, cfg["pt_pct"], bot["name"])
    profit_target_price = round(entry_credit * (1 - pt_pct), 4)
    stop_loss_price = round(entry_credit * cfg["sl_mult"], 4)
    ticker = pos.get("ticker") or "SPY"
    exp_raw = pos.get("expiration")
    expiration = str(exp_raw)[:10] if exp_raw else ""

    open_time = pos.get("open_time")
    open_date_str = str(open_time)[:10] if open_time else None
    today_str = ct.strftime("%Y-%m-%d")
    is_stale_holdover = open_date_str is not None and open_date_str < today_str

    if is_after_eod_cutoff(ct) or is_stale_holdover:
        close_reason = "stale_holdover" if is_stale_holdover else "eod_cutoff"
        close_position(
            bot, pos["position_id"], ticker, expiration,
            num(pos["put_short_strike"]), num(pos["put_long_strike"]),
            num(pos["call_short_strike"]), num(pos["call_long_strike"]),
            contracts, entry_credit, collateral, close_reason,
        )
        return {"status": f"closed:{close_reason}", "unrealizedPnl": 0}

    if not is_tradier_configured():
        return {"status": "monitoring:no_tradier", "unrealizedPnl": 0}

    mtm = get_ic_mark_to_market(
        ticker, expiration,
        num(pos["put_short_strike"]), num(pos["put_long_strike"]),
        num(pos["call_short_strike"]), num(pos["call_long_strike"]),
    )

    if not mtm:
        return {"status": "monitoring:mtm_failed", "unrealizedPnl": 0}

    is_valid, invalid_reason = validate_mtm(mtm, entry_credit)
    if not is_valid:
        log.warning(
            f"{bot['name'].upper()} MTM validation failed: {invalid_reason} "
            f"— skipping PT/SL check this cycle"
        )
        return {"status": f"monitoring:mtm_invalid({invalid_reason})", "unrealizedPnl": 0}

    cost_to_close = mtm["cost_to_close"]

    if cost_to_close <= profit_target_price:
        close_reason = f"profit_target_{pt_tier.lower()}"
        close_position(
            bot, pos["position_id"], ticker, expiration,
            num(pos["put_short_strike"]), num(pos["put_long_strike"]),
            num(pos["call_short_strike"]), num(pos["call_long_strike"]),
            contracts, entry_credit, collateral, close_reason, cost_to_close,
        )
        return {
            "status": (
                f"closed:profit_target ({pt_tier} {pt_pct:.0%}): "
                f"debit=${cost_to_close:.4f} <= threshold=${profit_target_price:.4f}"
            ),
            "unrealizedPnl": 0,
        }

    if cost_to_close >= stop_loss_price:
        close_position(
            bot, pos["position_id"], ticker, expiration,
            num(pos["put_short_strike"]), num(pos["put_long_strike"]),
            num(pos["call_short_strike"]), num(pos["call_long_strike"]),
            contracts, entry_credit, collateral, "stop_loss", cost_to_close,
        )
        return {
            "status": f"closed:stop_loss@{cost_to_close:.4f}",
            "unrealizedPnl": 0,
        }

    unrealized_pnl = round((entry_credit - cost_to_close) * 100 * contracts, 2)
    return {
        "status": f"monitoring:mtm={cost_to_close:.4f} uPnL=${unrealized_pnl:.2f}",
        "unrealizedPnl": unrealized_pnl,
    }


def monitor_position(bot: dict, ct: datetime) -> dict:
    """Monitor ALL open positions for PT/SL/EOD/stale holdover close.

    For multi-trade bots (INFERNO), iterates through every open position.
    For single-trade bots (FLAME/SPARK), behaves the same as before.
    """
    positions = db_query(f"""
        SELECT position_id, ticker, expiration,
               put_short_strike, put_long_strike,
               call_short_strike, call_long_strike,
               contracts, total_credit, max_loss,
               collateral_required, open_time
        FROM {bot_table(bot['name'], 'positions')}
        WHERE status = 'open' AND dte_mode = '{bot['dte']}'
        ORDER BY open_time DESC
    """)

    if not positions:
        return {"status": "no_position", "unrealizedPnl": 0}

    total_unrealized = 0.0
    statuses: list[str] = []

    for pos in positions:
        result = _monitor_single_position(bot, pos, ct)
        statuses.append(result["status"])
        total_unrealized += result["unrealizedPnl"]

    # Summarize: if any closed, report it; otherwise report monitoring
    closed = [s for s in statuses if s.startswith("closed:")]
    if closed:
        return {"status": closed[0], "unrealizedPnl": total_unrealized}
    return {"status": statuses[0], "unrealizedPnl": total_unrealized}


# ---------------------------------------------------------------------------
#  Try Open Trade
# ---------------------------------------------------------------------------


def try_open_trade(bot: dict, spot: float, vix: float) -> str:
    """Attempt to open a new IC position."""
    if vix > 32:
        return f"skip:vix_too_high({vix:.1f})"

    # PDT config check — read enforcement state from pdt_config table
    bot_upper = bot["name"].upper()
    pdt_cfg_rows = db_query(f"""
        SELECT pdt_enabled, day_trade_count, max_day_trades, max_trades_per_day
        FROM {shared_table('ironforge_pdt_config')}
        WHERE bot_name = '{bot_upper}'
        LIMIT 1
    """)
    pdt_cfg = pdt_cfg_rows[0] if pdt_cfg_rows else {}
    pdt_enabled = pdt_cfg.get("pdt_enabled", True) not in (False, 0, "false")
    pdt_count = to_int(pdt_cfg.get("day_trade_count", 0))
    max_day_trades = to_int(pdt_cfg.get("max_day_trades", 3))  # 0 = disabled/unlimited
    max_trades_per_day = to_int(pdt_cfg.get("max_trades_per_day", 1))  # 0 = unlimited

    # Check 1: Already traded today? (max per-day limit from config, 0 = unlimited)
    if max_trades_per_day > 0:
        today_trades = db_query(f"""
            SELECT COUNT(*) as cnt
            FROM {bot_table(bot['name'], 'pdt_log')}
            WHERE trade_date = CURRENT_DATE() AND dte_mode = '{bot['dte']}'
        """)
        if to_int(today_trades[0].get("cnt") if today_trades else 0) >= max_trades_per_day:
            return "skip:already_traded_today"

    # Check 2: PDT rolling window (only if enforcement is ON and limit > 0)
    if pdt_enabled and max_day_trades > 0 and pdt_count >= max_day_trades:
        log.info(f"{bot_upper} PDT BLOCKED: {pdt_count}/{max_day_trades} day trades in rolling window")
        return f"skip:pdt_blocked({pdt_count}/{max_day_trades})"

    account_rows = db_query(f"""
        SELECT id, current_balance, buying_power
        FROM {bot_table(bot['name'], 'paper_account')}
        WHERE is_active = TRUE AND dte_mode = '{bot['dte']}'
        ORDER BY id DESC
        LIMIT 1
    """)
    if not account_rows:
        return "skip:no_paper_account"

    acct = account_rows[0]
    paper_acct_id = acct["id"]  # save BEFORE sandbox loop overwrites 'acct'
    buying_power = num(acct["buying_power"])
    if buying_power < 200:
        return f"skip:low_bp(${buying_power:.0f})"

    expected_move = (vix / 100 / math.sqrt(252)) * spot

    adv = evaluate_advisor(vix, spot, expected_move, bot["dte"])
    if adv["advice"] == "SKIP":
        return f"skip:advisor({adv['reasoning']})"

    target_exp = get_target_expiration(bot["min_dte"])
    expirations = get_option_expirations("SPY")
    expiration = target_exp
    if expirations and target_exp not in expirations:
        target_date = datetime.strptime(target_exp, "%Y-%m-%d")
        nearest = expirations[0]
        min_diff = float("inf")
        for exp in expirations:
            diff = abs((datetime.strptime(exp, "%Y-%m-%d") - target_date).total_seconds())
            if diff < min_diff:
                min_diff = diff
                nearest = exp
        expiration = nearest

    cfg = BOT_CONFIG.get(bot["name"], BOT_CONFIG["flame"])
    strikes = calculate_strikes(spot, expected_move, sd_mult=cfg["sd"])
    credits = get_ic_entry_credit(
        "SPY", expiration,
        strikes["putShort"], strikes["putLong"],
        strikes["callShort"], strikes["callLong"],
    )
    if not credits or credits["totalCredit"] < 0.05:
        credit_val = credits["totalCredit"] if credits else 0
        return f"skip:credit_too_low(${credit_val:.4f})"

    spread_width = strikes["putShort"] - strikes["putLong"]
    collateral_per = max(0, (spread_width - credits["totalCredit"]) * 100)
    if collateral_per <= 0:
        return "skip:bad_collateral"
    usable_bp = buying_power * 0.85
    max_contracts = min(10, max(1, math.floor(usable_bp / collateral_per)))

    now = datetime.now()
    date_str = now.strftime("%Y%m%d")
    hex_str = format(random.randint(0, 0xFFFFFF), "06X")
    bot_name = bot["name"].upper()
    position_id = f"{bot_name}-{date_str}-{hex_str}"

    now_ts = get_central_time().strftime("%Y-%m-%d %H:%M:%S")
    today_date = get_central_time().strftime("%Y-%m-%d")

    # -------------------------------------------------------------------
    # For FLAME: each sandbox account sizes independently based on its
    # OWN buying power.  USER goes first to get the actual fill price.
    # For SPARK (paper-only): use calculated credit from bid/ask.
    # -------------------------------------------------------------------
    actual_credit = credits["totalCredit"]  # fallback for SPARK or if sandbox fails
    sandbox_order_ids: dict[str, dict] = {}  # {"User": {"order_id": 123, "contracts": 85}, ...}

    # Build OCC symbols once (shared by all accounts — same strikes)
    _occ_ps = build_occ_symbol("SPY", expiration, strikes["putShort"], "P")
    _occ_pl = build_occ_symbol("SPY", expiration, strikes["putLong"], "P")
    _occ_cs = build_occ_symbol("SPY", expiration, strikes["callShort"], "C")
    _occ_cl = build_occ_symbol("SPY", expiration, strikes["callLong"], "C")

    def _build_ic_open_body(qty: int) -> dict:
        return {
            "class": "multileg",
            "symbol": "SPY",
            "type": "market",
            "duration": "day",
            "option_symbol[0]": _occ_ps, "side[0]": "sell_to_open", "quantity[0]": str(qty),
            "option_symbol[1]": _occ_pl, "side[1]": "buy_to_open",  "quantity[1]": str(qty),
            "option_symbol[2]": _occ_cs, "side[2]": "sell_to_open", "quantity[2]": str(qty),
            "option_symbol[3]": _occ_cl, "side[3]": "buy_to_open",  "quantity[3]": str(qty),
            "tag": position_id[:255],
        }

    if bot["name"] == "flame":
        try:
            # Process accounts in order: User first (for fill price), then others
            all_accounts = _get_sandbox_accounts_lazy()
            user_accounts = [a for a in all_accounts if a["name"] == "User"]
            other_accounts = [a for a in all_accounts if a["name"] != "User"]
            ordered_accounts = user_accounts + other_accounts

            for acct in ordered_accounts:
                try:
                    acct_id = _get_account_id_for_key(acct["api_key"])
                    if not acct_id:
                        continue

                    # Query this account's own buying power
                    acct_bp = _get_sandbox_buying_power(acct["api_key"], acct_id)
                    if acct_bp is None or acct_bp < collateral_per:
                        log.warning(
                            f"Sandbox [{acct['name']}]: BP=${acct_bp} insufficient "
                            f"(need ${collateral_per:.2f}/contract)"
                        )
                        continue

                    # Size based on THIS account's buying power — NO max cap
                    acct_usable = acct_bp * 0.85
                    acct_contracts = max(1, math.floor(acct_usable / collateral_per))

                    log.info(
                        f"Sandbox [{acct['name']}]: BP=${acct_bp:,.0f} → "
                        f"usable=${acct_usable:,.0f} → {acct_contracts} contracts "
                        f"(collateral/contract=${collateral_per:.2f})"
                    )

                    order_body = _build_ic_open_body(acct_contracts)
                    result = _sandbox_post(
                        f"/accounts/{acct_id}/orders",
                        order_body,
                        acct["api_key"],
                    )

                    if result and result.get("order", {}).get("id"):
                        order_id = result["order"]["id"]
                        sandbox_order_ids[acct["name"]] = {
                            "order_id": order_id,
                            "contracts": acct_contracts,
                        }
                        log.info(
                            f"Sandbox IC OPEN OK [{acct['name']}]: "
                            f"order_id={order_id} x{acct_contracts}"
                        )

                        # Get actual fill price from USER (first account)
                        if acct["name"] == "User":
                            fill_price = _get_sandbox_order_fill_price(
                                acct["api_key"], acct_id, order_id
                            )
                            if fill_price is not None and fill_price > 0:
                                log.info(
                                    f"Actual fill price from USER sandbox: ${fill_price:.4f} "
                                    f"(calculated was ${credits['totalCredit']:.4f})"
                                )
                                actual_credit = fill_price
                            else:
                                log.warning(
                                    f"Could not get fill price for order {order_id}, "
                                    f"using calculated: ${credits['totalCredit']:.4f}"
                                )
                    else:
                        log.warning(
                            f"Sandbox IC OPEN FAILED [{acct['name']}]: "
                            f"no order ID returned"
                        )
                except Exception as e:
                    log.warning(f"Sandbox order failed [{acct['name']}]: {e}")
        except Exception as e:
            log.warning(f"Sandbox open failed for {position_id}: {e}")

    # Recalculate financials with actual credit (matches what Tradier filled)
    # Paper position uses paper max_contracts, not sandbox contract counts
    total_collateral = max(0, (spread_width - actual_credit) * 100) * max_contracts
    max_profit = actual_credit * 100 * max_contracts
    max_loss = total_collateral

    factors_json = json.dumps(adv["topFactors"]).replace("'", "''")
    sandbox_json = json.dumps(sandbox_order_ids).replace("'", "''") if sandbox_order_ids else ""

    db_execute(f"""
        INSERT INTO {bot_table(bot['name'], 'positions')} (
            position_id, ticker, expiration,
            put_short_strike, put_long_strike, put_credit,
            call_short_strike, call_long_strike, call_credit,
            contracts, spread_width, total_credit, max_loss, max_profit,
            collateral_required,
            underlying_at_entry, vix_at_entry, expected_move,
            call_wall, put_wall, gex_regime,
            flip_point, net_gex,
            oracle_confidence, oracle_win_probability, oracle_advice,
            oracle_reasoning, oracle_top_factors, oracle_use_gex_walls,
            wings_adjusted, original_put_width, original_call_width,
            put_order_id, call_order_id,
            status, open_time, open_date, dte_mode,
            {('sandbox_order_id, ' if sandbox_json else '')}created_at, updated_at
        ) VALUES (
            '{position_id}', 'SPY', CAST('{expiration}' AS DATE),
            {strikes['putShort']}, {strikes['putLong']}, {credits['putCredit']},
            {strikes['callShort']}, {strikes['callLong']}, {credits['callCredit']},
            {max_contracts}, {spread_width}, {actual_credit}, {max_loss}, {max_profit},
            {total_collateral},
            {spot}, {vix}, {expected_move},
            0, 0, 'UNKNOWN',
            0, 0,
            {adv['confidence']}, {adv['winProbability']}, '{adv['advice']}',
            '{adv['reasoning'].replace(chr(39), chr(39)+chr(39))}', '{factors_json}', FALSE,
            FALSE, {spread_width}, {spread_width},
            'PAPER', 'PAPER',
            'open', CAST('{now_ts}' AS TIMESTAMP), CAST('{today_date}' AS DATE), '{bot['dte']}',
            {(f"'{sandbox_json}', " if sandbox_json else '')}CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP()
        )
    """)

    db_execute(f"""
        UPDATE {bot_table(bot['name'], 'paper_account')}
        SET collateral_in_use = collateral_in_use + {total_collateral},
            buying_power = buying_power - {total_collateral},
            updated_at = CURRENT_TIMESTAMP()
        WHERE id = {paper_acct_id}
    """)

    db_execute(f"""
        INSERT INTO {bot_table(bot['name'], 'signals')} (
            signal_time, spot_price, vix, expected_move, call_wall, put_wall,
            gex_regime, put_short, put_long, call_short, call_long,
            total_credit, confidence, was_executed, reasoning,
            wings_adjusted, dte_mode
        ) VALUES (
            CURRENT_TIMESTAMP(), {spot}, {vix}, {expected_move}, 0, 0,
            'UNKNOWN', {strikes['putShort']}, {strikes['putLong']},
            {strikes['callShort']}, {strikes['callLong']},
            {actual_credit}, {adv['confidence']}, TRUE,
            'Auto scan | {adv['reasoning'].replace(chr(39), chr(39)+chr(39))}',
            FALSE, '{bot['dte']}'
        )
    """)

    trade_details = json.dumps({
        "position_id": position_id,
        "contracts": max_contracts,
        "credit": actual_credit,
        "calculated_credit": credits["totalCredit"],
        "credit_source": "sandbox_fill" if actual_credit != credits["totalCredit"] else "calculated",
        "collateral": total_collateral,
        "source": "scanner",
        "sandbox_order_ids": sandbox_order_ids,
    }).replace("'", "''")
    db_execute(f"""
        INSERT INTO {bot_table(bot['name'], 'logs')}
            (log_time, level, message, details, dte_mode)
        VALUES (
            CURRENT_TIMESTAMP(),
            'TRADE_OPEN',
            'AUTO TRADE: {position_id} {strikes['putLong']}/{strikes['putShort']}P-{strikes['callShort']}/{strikes['callLong']}C x{max_contracts} @ ${actual_credit:.4f}',
            '{trade_details}',
            '{bot['dte']}'
        )
    """)

    db_execute(f"""
        INSERT INTO {bot_table(bot['name'], 'pdt_log')} (
            trade_date, symbol, position_id, opened_at,
            contracts, entry_credit, dte_mode, created_at
        ) VALUES (
            CURRENT_DATE(), 'SPY', '{position_id}', CURRENT_TIMESTAMP(),
            {max_contracts}, {actual_credit}, '{bot['dte']}',
            CURRENT_TIMESTAMP()
        )
    """)

    updated_acct = db_query(f"""
        SELECT current_balance, cumulative_pnl
        FROM {bot_table(bot['name'], 'paper_account')}
        WHERE id = {paper_acct_id}
    """)
    bal = num(updated_acct[0]["current_balance"]) if updated_acct else 0
    cum_pnl = num(updated_acct[0]["cumulative_pnl"]) if updated_acct else 0
    db_execute(f"""
        INSERT INTO {bot_table(bot['name'], 'equity_snapshots')}
            (snapshot_time, balance, realized_pnl, unrealized_pnl,
             open_positions, note, dte_mode, created_at)
        VALUES (
            CURRENT_TIMESTAMP(), {bal}, {cum_pnl}, 0,
            1, 'auto:{position_id}', '{bot['dte']}',
            CURRENT_TIMESTAMP()
        )
    """)

    db_execute(f"""
        MERGE INTO {bot_table(bot['name'], 'daily_perf')} AS t
        USING (SELECT CURRENT_DATE() AS trade_date) AS s
        ON t.trade_date = s.trade_date
        WHEN MATCHED THEN UPDATE SET
            trades_executed = t.trades_executed + 1,
            updated_at = CURRENT_TIMESTAMP()
        WHEN NOT MATCHED THEN INSERT
            (trade_date, trades_executed, positions_closed, realized_pnl, updated_at)
        VALUES (CURRENT_DATE(), 1, 0, 0, CURRENT_TIMESTAMP())
    """)

    log.info(
        f"{bot_name} OPENED {position_id} "
        f"{strikes['putLong']}/{strikes['putShort']}P-"
        f"{strikes['callShort']}/{strikes['callLong']}C "
        f"x{max_contracts} @ ${actual_credit:.4f} "
        f"({'sandbox_fill' if actual_credit != credits['totalCredit'] else 'calculated'}) "
        f"[sandbox:{json.dumps(sandbox_order_ids)}]"
    )
    return f"traded:{position_id}"


# ---------------------------------------------------------------------------
#  Scan Bot
# ---------------------------------------------------------------------------


def scan_bot(bot: dict) -> None:
    """One scan cycle for one bot."""
    ct = get_central_time()
    bot_name = bot["name"].upper()
    action = "scan"
    reason = ""
    spot = 0.0
    vix = 0.0
    unrealized_pnl = 0.0

    try:
        # Auto-decrement PDT counter: recount actual day trades in rolling window
        try:
            pdt_actual = db_query(f"""
                SELECT COUNT(*) as cnt FROM {bot_table(bot['name'], 'pdt_log')}
                WHERE is_day_trade = TRUE AND dte_mode = '{bot['dte']}'
                  AND trade_date >= DATE_ADD(CURRENT_DATE(), -8)
                  AND DAYOFWEEK(trade_date) BETWEEN 2 AND 6
            """)
            actual_count = to_int(pdt_actual[0]["cnt"]) if pdt_actual else 0
            pdt_cfg_row = db_query(f"""
                SELECT day_trade_count FROM {shared_table('ironforge_pdt_config')}
                WHERE bot_name = '{bot_name}'
                LIMIT 1
            """)
            stored_count = to_int(pdt_cfg_row[0]["day_trade_count"]) if pdt_cfg_row else 0
            if stored_count != actual_count:
                db_execute(f"""
                    UPDATE {shared_table('ironforge_pdt_config')}
                    SET day_trade_count = {actual_count}, updated_at = CURRENT_TIMESTAMP()
                    WHERE bot_name = '{bot_name}'
                """)
                if actual_count < stored_count:
                    old_val = json.dumps({"day_trade_count": stored_count}).replace("'", "''")
                    new_val = json.dumps({"day_trade_count": actual_count}).replace("'", "''")
                    reason_str = f"Rolling window update: old trades dropped off ({stored_count}->{actual_count})"
                    db_execute(f"""
                        INSERT INTO {shared_table('ironforge_pdt_log')}
                            (log_id, bot_name, action, old_value, new_value, reason, performed_by, created_at)
                        VALUES (UUID(), '{bot_name}', 'auto_decrement', '{old_val}', '{new_val}',
                                '{reason_str}', 'scanner', CURRENT_TIMESTAMP())
                    """)
        except Exception as pdt_sync_err:
            log.warning(f"{bot_name} PDT sync error: {pdt_sync_err}")

        cfg = BOT_CONFIG.get(bot["name"], BOT_CONFIG["flame"])
        max_trades = cfg["max_trades"]
        entry_end = cfg["entry_end"]

        open_rows = db_query(f"""
            SELECT position_id
            FROM {bot_table(bot['name'], 'positions')}
            WHERE status = 'open' AND dte_mode = '{bot['dte']}'
        """)
        open_count = len(open_rows)
        has_open_position = open_count > 0

        # Always monitor ALL open positions first
        if has_open_position:
            monitor_result = monitor_position(bot, ct)
            if monitor_result["status"].startswith("closed:"):
                action = "closed"
            else:
                action = "monitoring"
            reason = monitor_result["status"]
            unrealized_pnl = monitor_result["unrealizedPnl"]

        # For multi-trade bots, check if we can open more positions
        # For single-trade bots, only open if no position is open
        # max_trades: 0 = unlimited, 1 = single trade, >1 = multi-trade with cap
        can_open_more = (max_trades == 0) or (max_trades > 1 and open_count < max_trades) or (max_trades == 1 and not has_open_position)

        if not is_market_open(ct):
            if not has_open_position:
                action = "outside_window"
                reason = f"Market closed ({ct.hour}:{ct.minute:02d} CT)"
        elif can_open_more and is_in_entry_window(ct, entry_end):
            if not is_tradier_configured():
                action = "skip"
                reason = "tradier_not_configured"
            else:
                spy_quote = get_quote("SPY")
                vix_quote = get_quote("VIX")
                spot = spy_quote["last"] if spy_quote else 0.0
                vix = vix_quote["last"] if vix_quote else 0.0

                if spot == 0:
                    action = "skip"
                    reason = "no_spy_quote"
                elif vix == 0:
                    action = "skip"
                    reason = "no_vix_quote"
                else:
                    trade_result = try_open_trade(bot, spot, vix)
                    if trade_result.startswith("traded:"):
                        action = "traded"
                    else:
                        action = "no_trade"
                    reason = trade_result
        elif not has_open_position:
            action = "outside_entry_window"
            reason = f"Past entry cutoff ({ct.hour}:{ct.minute:02d} CT, cutoff {entry_end})"

        # Equity snapshot every cycle
        try:
            acct_rows = db_query(f"""
                SELECT current_balance, cumulative_pnl
                FROM {bot_table(bot['name'], 'paper_account')}
                WHERE dte_mode = '{bot['dte']}'
                ORDER BY id DESC LIMIT 1
            """)
            open_count = db_query(f"""
                SELECT COUNT(*) as cnt
                FROM {bot_table(bot['name'], 'positions')}
                WHERE status = 'open' AND dte_mode = '{bot['dte']}'
            """)
            if acct_rows:
                bal = num(acct_rows[0]["current_balance"])
                cum_pnl = num(acct_rows[0]["cumulative_pnl"])
                open_cnt = to_int(open_count[0]["cnt"]) if open_count else 0
                db_execute(f"""
                    INSERT INTO {bot_table(bot['name'], 'equity_snapshots')}
                        (snapshot_time, balance, realized_pnl, unrealized_pnl,
                         open_positions, note, dte_mode, created_at)
                    VALUES (
                        CURRENT_TIMESTAMP(), {bal}, {cum_pnl},
                        {unrealized_pnl}, {open_cnt},
                        'scan:{action}', '{bot['dte']}',
                        CURRENT_TIMESTAMP()
                    )
                """)
        except Exception as snap_err:
            log.warning(f"{bot_name} snapshot error: {snap_err}")

    except Exception as err:
        action = "error"
        reason = str(err)
        log.error(f"{bot_name} scan error: {traceback.format_exc()}")

    status = "error" if action == "error" else ("active" if is_market_open(ct) else "idle")
    hb_details = json.dumps({"action": action, "reason": reason, "spot": spot, "vix": vix}).replace("'", "''")

    try:
        db_execute(f"""
            MERGE INTO {CATALOG}.{SCHEMA}.bot_heartbeats AS t
            USING (SELECT '{bot_name}' AS bot_name) AS s
            ON t.bot_name = s.bot_name
            WHEN MATCHED THEN UPDATE SET
                last_heartbeat = CURRENT_TIMESTAMP(),
                status = '{status}',
                scan_count = t.scan_count + 1,
                details = '{hb_details}'
            WHEN NOT MATCHED THEN INSERT
                (bot_name, last_heartbeat, status, scan_count, details)
            VALUES ('{bot_name}', CURRENT_TIMESTAMP(), '{status}', 1, '{hb_details}')
        """)
    except Exception as hb_err:
        log.warning(f"{bot_name} heartbeat error: {hb_err}")

    try:
        spot_str = f" SPY=${spot:.2f}" if spot > 0 else ""
        vix_str = f" VIX={vix:.1f}" if vix > 0 else ""
        scan_details = json.dumps({
            "action": action, "reason": reason, "spot": spot, "vix": vix, "source": "scanner",
        }).replace("'", "''")
        db_execute(f"""
            INSERT INTO {bot_table(bot['name'], 'logs')}
                (log_time, level, message, details, dte_mode)
            VALUES (
                CURRENT_TIMESTAMP(),
                'SCAN',
                'SCAN: {action}{spot_str}{vix_str} | {reason.replace(chr(39), chr(39)+chr(39))}',
                '{scan_details}',
                '{bot['dte']}'
            )
        """)
    except Exception as log_err:
        log.warning(f"{bot_name} log error: {log_err}")

    log.info(f"{bot_name}: {action} | {reason}")


def run_scan_cycle() -> None:
    """Run one scan cycle for all bots."""
    for bot in BOTS:
        try:
            scan_bot(bot)
        except Exception as e:
            log.error(f"{bot['name'].upper()} scan_bot crashed: {e}")
            log.error(traceback.format_exc())


print("Scanner code loaded")

# COMMAND ----------

# Cell 3: Run the scanner

# Reset sandbox cache so new keys/account IDs are picked up
_sandbox_accounts = None
_account_id_cache.clear()


# ---------------------------------------------------------------------------
#  Sandbox Orphan Cleanup
# ---------------------------------------------------------------------------


def _run_sandbox_orphan_cleanup() -> None:
    """Close stranded sandbox positions that weren't closed with the paper position.

    Run via: SCANNER_MODE=cleanup python ironforge_scanner.py
    Or call directly from a Databricks notebook cell.

    Queries each sandbox account for open option positions, then closes them
    with market orders.
    """
    print("=" * 60)
    print("  SANDBOX ORPHAN CLEANUP")
    print("=" * 60)

    accounts = _get_sandbox_accounts()
    if not accounts:
        print("  No sandbox accounts configured")
        return

    for acct in accounts:
        acct_id = _get_account_id_for_key(acct["api_key"])
        if not acct_id:
            print(f"  [{acct['name']}] SKIP — no account_id resolved")
            continue

        print(f"\n  [{acct['name']}] Account: {acct_id}")

        # Query open positions from Tradier sandbox
        data = _sandbox_get(f"/accounts/{acct_id}/positions", None, acct["api_key"])
        if not data:
            print(f"  [{acct['name']}] No position data returned")
            continue

        positions = data.get("positions", {})
        if positions == "null" or not positions:
            print(f"  [{acct['name']}] No open positions — clean")
            continue

        pos_list = positions.get("position", [])
        if isinstance(pos_list, dict):
            pos_list = [pos_list]

        if not pos_list:
            print(f"  [{acct['name']}] No open positions — clean")
            continue

        print(f"  [{acct['name']}] Found {len(pos_list)} open position(s):")
        for p in pos_list:
            symbol = p.get("symbol", "?")
            qty = p.get("quantity", 0)
            cost_basis = p.get("cost_basis", 0)
            print(f"    {symbol} qty={qty} cost_basis={cost_basis}")

        # Close each position with a market order
        for p in pos_list:
            symbol = p.get("symbol", "")
            qty = p.get("quantity", 0)
            if not symbol or qty == 0:
                continue

            # Determine close side: positive qty = long (sell_to_close),
            # negative qty = short (buy_to_close)
            if qty > 0:
                side = "sell_to_close"
                close_qty = qty
            else:
                side = "buy_to_close"
                close_qty = abs(qty)

            close_body = {
                "class": "option",
                "symbol": symbol.split(" ")[0] if " " in symbol else "SPY",
                "option_symbol": symbol,
                "side": side,
                "quantity": str(close_qty),
                "type": "market",
                "duration": "day",
            }

            result = _sandbox_post(
                f"/accounts/{acct_id}/orders", close_body, acct["api_key"],
            )
            order_id = result.get("order", {}).get("id") if result else None
            if order_id:
                print(f"    CLOSED: {symbol} {side} x{close_qty} → order_id={order_id}")
            else:
                print(f"    FAILED: {symbol} {side} x{close_qty} — check logs for HTTP error")

    print(f"\n{'=' * 60}")
    print("  Cleanup complete")
    print("=" * 60)


_pdt_tables_ready = False


def _ensure_pdt_tables() -> None:
    """Create shared ironforge_pdt_config and ironforge_pdt_log tables if they don't exist.

    Runs once per scanner process. Safe to call repeatedly.
    """
    global _pdt_tables_ready
    if _pdt_tables_ready:
        return
    try:
        pdt_config_tbl = shared_table('ironforge_pdt_config')
        pdt_log_tbl = shared_table('ironforge_pdt_log')

        db_execute(f"""
            CREATE TABLE IF NOT EXISTS {pdt_config_tbl} (
                bot_name STRING NOT NULL,
                pdt_enabled BOOLEAN,
                day_trade_count INT,
                max_day_trades INT,
                window_days INT,
                max_trades_per_day INT,
                last_reset_at TIMESTAMP,
                last_reset_by STRING,
                updated_at TIMESTAMP,
                created_at TIMESTAMP
            ) USING DELTA
        """)
        db_execute(f"""
            CREATE TABLE IF NOT EXISTS {pdt_log_tbl} (
                log_id STRING NOT NULL,
                bot_name STRING NOT NULL,
                action STRING NOT NULL,
                old_value STRING,
                new_value STRING,
                reason STRING,
                performed_by STRING,
                created_at TIMESTAMP
            ) USING DELTA
        """)

        # Seed PDT config for each bot if missing
        for bot in BOTS:
            bot_upper = bot["name"].upper()
            cfg = BOT_CONFIG.get(bot["name"], BOT_CONFIG["flame"])
            max_tpd = cfg["max_trades"]
            # INFERNO: no PDT enforcement, unlimited trades per day
            pdt_on = "FALSE" if bot["name"] == "inferno" else "TRUE"
            pdt_max = 0 if bot["name"] == "inferno" else 4  # 0 = disabled, 4 = FINRA limit
            existing = db_query(f"""
                SELECT bot_name FROM {pdt_config_tbl}
                WHERE bot_name = '{bot_upper}' LIMIT 1
            """)
            if not existing:
                db_execute(f"""
                    INSERT INTO {pdt_config_tbl}
                        (bot_name, pdt_enabled, day_trade_count, max_day_trades,
                         window_days, max_trades_per_day, created_at, updated_at)
                    VALUES ('{bot_upper}', {pdt_on}, 0, {pdt_max}, 5, {max_tpd},
                            CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP())
                """)
                log.info(f"Seeded ironforge_pdt_config for {bot_upper} (pdt_enabled={pdt_on}, max_trades_per_day={max_tpd})")
        _pdt_tables_ready = True
        log.info("PDT tables verified/created (ironforge_pdt_config, ironforge_pdt_log)")
    except Exception as e:
        log.warning(f"PDT table auto-creation failed (non-fatal): {e}")


def main() -> None:
    """Single scan — called by Databricks Job every 1 minute.

    In Job context (SCANNER_MODE=single), runs one scan cycle and exits.
    The Databricks Job scheduler handles the 1-minute repeat.

    In notebook context (SCANNER_MODE=loop), runs in an infinite loop
    with a 1-minute sleep between cycles.
    """
    try:
        # Ensure PDT tables exist (auto-create if 01_setup_tables.sql hasn't been re-run)
        _ensure_pdt_tables()

        ct = get_central_time()
        print(f"IronForge scan starting at {ct.strftime('%Y-%m-%d %H:%M:%S')} CT")
        print(f"  Catalog: {CATALOG} | Schema: {SCHEMA} | Tradier: {'OK' if is_tradier_configured() else 'MISSING'}")
        accounts = _get_sandbox_accounts_lazy()
        print(f"  Sandbox accounts: {len(accounts)}")
        for acct in accounts:
            acct_id = acct.get("account_id") or "auto-discover"
            print(f"    {acct['name']}: key={acct['api_key'][:6]}... account={acct_id}")
        log.info(
            f"IronForge scan starting at {ct.strftime('%Y-%m-%d %H:%M:%S')} CT "
            f"| Catalog: {CATALOG} | Schema: {SCHEMA} "
            f"| Tradier: {'OK' if is_tradier_configured() else 'MISSING'}"
        )

        if not is_market_open(ct):
            if is_in_warmup_window(ct):
                # Pre-market warm-up: wait for 8:30 so the cluster stays alive
                from zoneinfo import ZoneInfo
                market_open = ct.replace(hour=8, minute=30, second=0, microsecond=0)
                wait_secs = max(0, (market_open - ct).total_seconds())
                print(f"  Pre-market warm-up — waiting {int(wait_secs)}s for market open")
                log.info(
                    f"Pre-market warm-up window ({ct.strftime('%H:%M')} CT) — "
                    f"cluster warm, waiting {int(wait_secs)}s for market open"
                )
                if wait_secs > 0:
                    time.sleep(wait_secs)
                # Re-check time after sleeping (should now be ~8:30)
                ct = get_central_time()
                print(f"  Warm-up complete — now {ct.strftime('%H:%M:%S')} CT")
                log.info(f"Warm-up complete — now {ct.strftime('%H:%M:%S')} CT, proceeding to scan")
            else:
                print(f"  Market closed ({ct.strftime('%H:%M')} CT) — exiting")
                log.info(
                    f"Market closed ({ct.strftime('%H:%M')} CT, "
                    f"{'weekend' if ct.weekday() >= 5 else 'outside 8:30-15:00'}) — exiting"
                )
                return

        print("  Running scan cycle...")
        run_scan_cycle()
        print("  Scan complete — exiting")
        log.info("Scan complete — exiting")

    except Exception as e:
        print(f"  MAIN ERROR: {e}")
        import traceback as tb
        tb.print_exc()


# Entry point: single-scan (Job) vs loop (notebook testing)
_scanner_mode = os.environ.get("SCANNER_MODE", "single")

if _scanner_mode == "loop":
    # Notebook testing mode — infinite loop with 5-min sleep
    print("Starting in LOOP mode (notebook testing)")
    while True:
        main()
        time.sleep(SCAN_INTERVAL)
elif _scanner_mode == "cleanup":
    # Orphan cleanup mode — close stranded sandbox positions
    _run_sandbox_orphan_cleanup()
else:
    # Job mode — single scan and exit
    main()
