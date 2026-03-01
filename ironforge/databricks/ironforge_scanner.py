"""
IronForge Databricks Scanner — complete port of scanner.ts + tradier.ts

Runs every 5 minutes for both FLAME (2DTE) and SPARK (1DTE) bots.
Uses Tradier API for market data and Databricks for persistence.

Works in two contexts:
  1. Databricks notebook — uses spark.sql() directly (no extra deps needed)
  2. Standalone Python   — uses databricks-sql-connector (pip install databricks-sql-connector)

Env vars (standalone only — notebook context auto-detects):
  DATABRICKS_HOST          - Databricks workspace hostname
  DATABRICKS_HTTP_PATH     - SQL warehouse HTTP path
  DATABRICKS_TOKEN         - Personal access token

Env vars (always required):
  TRADIER_API_KEY          - Production API key (for live quotes)
  TRADIER_SANDBOX_KEY_USER  - Sandbox key for User account (optional)
  TRADIER_SANDBOX_KEY_MATT  - Sandbox key for Matt account (optional)
  TRADIER_SANDBOX_KEY_LOGAN - Sandbox key for Logan account (optional)
  TRADIER_SANDBOX_ACCOUNT_ID_USER  - Account ID for User (optional, auto-discovers if omitted)
  TRADIER_SANDBOX_ACCOUNT_ID_MATT  - Account ID for Matt (required if auto-discover fails)
  TRADIER_SANDBOX_ACCOUNT_ID_LOGAN - Account ID for Logan (required if auto-discover fails)
"""

import os
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

# Detect notebook vs standalone context
_IN_NOTEBOOK = False
try:
    spark  # noqa: F821 — injected by Databricks notebook runtime
    _IN_NOTEBOOK = True
except NameError:
    pass

databricks_sql = None
if not _IN_NOTEBOOK:
    try:
        from databricks import sql as databricks_sql
    except ImportError:
        pass

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

SCAN_INTERVAL = 300  # 5 minutes
CATALOG = os.environ.get("DATABRICKS_CATALOG", "alpha_prime")
SCHEMA = os.environ.get("DATABRICKS_SCHEMA", "ironforge")

BOTS = [
    {"name": "flame", "dte": "2DTE", "min_dte": 2},
    {"name": "spark", "dte": "1DTE", "min_dte": 1},
]

# ---------------------------------------------------------------------------
#  Databricks SQL Connection (Step 3)
#  Supports both notebook context (spark.sql) and standalone (databricks-sql-connector)
# ---------------------------------------------------------------------------

_connection = None


def get_connection():
    """Get or create a Databricks SQL connection (standalone mode only)."""
    if _IN_NOTEBOOK:
        return None  # not used in notebook context
    global _connection
    if databricks_sql is None:
        raise RuntimeError(
            "databricks-sql-connector not installed. "
            "Run: pip install databricks-sql-connector"
        )
    if _connection is None or not _connection.open:
        host = (
            os.environ.get("DATABRICKS_HOST")
            or os.environ.get("DATABRICKS_SERVER_HOSTNAME")
            or ""
        )
        warehouse_id = os.environ.get("DATABRICKS_WAREHOUSE_ID", "")
        http_path = (
            os.environ.get("DATABRICKS_HTTP_PATH")
            or (f"/sql/1.0/warehouses/{warehouse_id}" if warehouse_id else "")
        )
        token = os.environ.get("DATABRICKS_TOKEN", "")
        if not host or not http_path or not token:
            raise RuntimeError(
                "Missing Databricks credentials. Set DATABRICKS_HOST (or "
                "DATABRICKS_SERVER_HOSTNAME), DATABRICKS_HTTP_PATH (or "
                "DATABRICKS_WAREHOUSE_ID), and DATABRICKS_TOKEN."
            )
        _connection = databricks_sql.connect(
            server_hostname=host,
            http_path=http_path,
            access_token=token,
            catalog=CATALOG,
            schema=SCHEMA,
        )
    return _connection


def db_query(sql_str: str, params: Optional[dict] = None) -> list[dict]:
    """Execute a SQL query and return rows as list of dicts.

    Works in both Databricks notebook (spark.sql) and standalone
    (databricks-sql-connector) contexts.
    """
    if _IN_NOTEBOOK:
        try:
            result = spark.sql(sql_str)  # noqa: F821
            rows = result.collect()
            if not rows:
                return []
            columns = result.columns
            return [dict(zip(columns, row)) for row in rows]
        except Exception as e:
            log.error(f"DB query error (notebook): {e}\nSQL: {sql_str[:200]}")
            raise
    else:
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(sql_str, params)
                if cursor.description:
                    columns = [desc[0] for desc in cursor.description]
                    rows = cursor.fetchall()
                    return [dict(zip(columns, row)) for row in rows]
                return []
        except Exception as e:
            log.error(f"DB query error: {e}\nSQL: {sql_str[:200]}")
            raise


def db_execute(sql_str: str, params: Optional[dict] = None) -> None:
    """Execute a SQL statement (INSERT/UPDATE/DELETE) without returning rows.

    Works in both Databricks notebook (spark.sql) and standalone
    (databricks-sql-connector) contexts.
    """
    if _IN_NOTEBOOK:
        try:
            spark.sql(sql_str)  # noqa: F821
        except Exception as e:
            log.error(f"DB execute error (notebook): {e}\nSQL: {sql_str[:200]}")
            raise
    else:
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(sql_str, params)
        except Exception as e:
            log.error(f"DB execute error: {e}\nSQL: {sql_str[:200]}")
            raise


def bot_table(bot_name: str, suffix: str) -> str:
    """Build fully-qualified table name: alpha_prime.ironforge.{bot}_{suffix}."""
    return f"{CATALOG}.{SCHEMA}.{bot_name}_{suffix}"


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
#  Tradier API Client (port of tradier.ts)
# ---------------------------------------------------------------------------

SANDBOX_URL = "https://sandbox.tradier.com/v1"


def _get_tradier_api_key() -> str:
    """Read Tradier API key lazily so notebook env vars set after import are picked up."""
    return os.environ.get("TRADIER_API_KEY", "")


def _get_tradier_base_url() -> str:
    """Read Tradier base URL lazily."""
    return os.environ.get("TRADIER_BASE_URL", SANDBOX_URL)


def is_tradier_configured() -> bool:
    """Whether the Tradier API key is configured."""
    return bool(_get_tradier_api_key())


def tradier_get(endpoint: str, params: Optional[dict] = None) -> Optional[dict]:
    """Authenticated GET to Tradier API. Returns JSON or None on failure."""
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
        "bid": float(quote.get("bid", 0)),
        "ask": float(quote.get("ask", 0)),
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
        "bid": float(quote.get("bid", 0)),
        "ask": float(quote.get("ask", 0)),
        "last": float(quote.get("last", 0)),
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

    # Cost to close = buy back shorts (at ask) - sell longs (at bid)
    cost = ps_q["ask"] + cs_q["ask"] - pl_q["bid"] - cl_q["bid"]
    return {
        "cost_to_close": max(0, round(cost, 4)),
        "put_short_ask": ps_q["ask"],
        "put_long_bid": pl_q["bid"],
        "call_short_ask": cs_q["ask"],
        "call_long_bid": cl_q["bid"],
        "spot_price": spot_q["last"] if spot_q else None,
    }


# ---------------------------------------------------------------------------
#  Sandbox Order Execution (3 accounts: User, Matt, Logan)
# ---------------------------------------------------------------------------


def _get_sandbox_accounts() -> list[dict]:
    """Load sandbox accounts from env vars.

    Each account needs a key and account ID. Account IDs can be provided
    explicitly (like FORTRESS does) or auto-discovered via /user/profile.
    Explicit IDs are preferred — auto-discovery doesn't work with all token types.
    """
    accounts = []
    for name, key_env, acct_env in [
        ("User", "TRADIER_SANDBOX_KEY_USER", "TRADIER_SANDBOX_ACCOUNT_ID_USER"),
        ("Matt", "TRADIER_SANDBOX_KEY_MATT", "TRADIER_SANDBOX_ACCOUNT_ID_MATT"),
        ("Logan", "TRADIER_SANDBOX_KEY_LOGAN", "TRADIER_SANDBOX_ACCOUNT_ID_LOGAN"),
    ]:
        key = os.environ.get(key_env, "")
        acct_id = os.environ.get(acct_env, "")
        if key:
            accounts.append({"name": name, "api_key": key, "account_id": acct_id})
    return accounts


_sandbox_accounts: Optional[list[dict]] = None
_account_id_cache: dict[str, str] = {}


def _get_sandbox_accounts_lazy() -> list[dict]:
    """Lazy-load sandbox accounts so notebook env vars set after import are picked up."""
    global _sandbox_accounts
    if _sandbox_accounts is None:
        _sandbox_accounts = _get_sandbox_accounts()
    return _sandbox_accounts


def _sandbox_get(endpoint: str, params: Optional[dict], api_key: str) -> Optional[dict]:
    """GET request to Tradier sandbox."""
    if not api_key:
        return None
    try:
        resp = requests.get(
            f"{SANDBOX_URL}{endpoint}",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
            },
            params=params or {},
            timeout=15,
        )
        return resp.json() if resp.ok else None
    except Exception:
        return None


def _sandbox_post(endpoint: str, body: dict, api_key: str) -> Optional[dict]:
    """POST request to Tradier sandbox."""
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
        return resp.json() if resp.ok else None
    except Exception:
        return None


def _get_account_id_for_key(api_key: str) -> Optional[str]:
    """Get sandbox account ID — prefer pre-configured, fall back to auto-discover."""
    if api_key in _account_id_cache:
        return _account_id_cache[api_key]

    # Check pre-configured account IDs first (like FORTRESS does)
    for acct in _get_sandbox_accounts_lazy():
        if acct["api_key"] == api_key and acct.get("account_id"):
            _account_id_cache[api_key] = acct["account_id"]
            return acct["account_id"]

    # Fall back to auto-discovery via /user/profile
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
            result = _sandbox_post(
                f"/accounts/{account_id}/orders",
                order_body,
                acct["api_key"],
            )
            if result and result.get("order", {}).get("id"):
                results[acct["name"]] = result["order"]["id"]
        except Exception as e:
            log.warning(f"Sandbox IC close failed [{acct['name']}]: {e}")

    return results


# ---------------------------------------------------------------------------
#  Market Hours (Central Time) — mirrors scanner.ts exactly
# ---------------------------------------------------------------------------


def get_central_time() -> datetime:
    """Get current time in Central Time."""
    from zoneinfo import ZoneInfo

    return datetime.now(ZoneInfo("America/Chicago"))


def is_market_open(ct: datetime) -> bool:
    """Check if market is open: weekday, 8:30 AM - 3:30 PM CT."""
    dow = ct.weekday()  # 0=Monday, 6=Sunday
    if dow >= 5:  # Saturday=5, Sunday=6
        return False
    hhmm = ct.hour * 100 + ct.minute
    return 830 <= hhmm <= 1530


def is_in_entry_window(ct: datetime) -> bool:
    """Check if within entry window: weekday, 8:30 AM - 2:00 PM CT."""
    dow = ct.weekday()
    if dow >= 5:
        return False
    hhmm = ct.hour * 100 + ct.minute
    return 830 <= hhmm <= 1400


def is_after_eod_cutoff(ct: datetime) -> bool:
    """Check if past EOD cutoff: 3:45 PM CT."""
    hhmm = ct.hour * 100 + ct.minute
    return hhmm >= 1545


# ---------------------------------------------------------------------------
#  Advisor — port of evaluateAdvisor() from scanner.ts
# ---------------------------------------------------------------------------


def evaluate_advisor(vix: float, spot: float, expected_move: float, dte_mode: str) -> dict:
    """Lightweight advisor that scores trading conditions. Identical to scanner.ts."""
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

    # Day of week (JS: 0=Sun, 6=Sat. Python weekday(): 0=Mon, 6=Sun)
    # We convert to JS convention for identical behavior
    ct = get_central_time()
    py_dow = ct.weekday()  # 0=Mon ... 6=Sun
    # Convert to JS: Sun=0, Mon=1, ..., Sat=6
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
    else:  # Sat/Sun
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
#  Strike Calculation — port of calculateStrikes() from scanner.ts
# ---------------------------------------------------------------------------


def calculate_strikes(spot: float, expected_move: float) -> dict:
    """Calculate IC strikes using 1.2x SD, $5 width. Identical to scanner.ts."""
    SD = 1.2
    WIDTH = 5

    min_em = spot * 0.005
    em = max(expected_move, min_em)

    put_short = math.floor(spot - SD * em)
    call_short = math.ceil(spot + SD * em)
    put_long = put_short - WIDTH
    call_long = call_short + WIDTH

    # Sanity guard
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
    """Find target expiration N trading days out. Identical to scanner.ts."""
    target = datetime.now()
    counted = 0
    while counted < min_dte:
        target += timedelta(days=1)
        # weekday(): 0=Mon ... 4=Fri, 5=Sat, 6=Sun
        if target.weekday() < 5:
            counted += 1
    return target.strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
#  Close Position — port of closePosition() from scanner.ts
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
    # Determine close price if not provided
    price = close_price if close_price is not None else 0.0
    if close_price is None and is_tradier_configured():
        mtm = get_ic_mark_to_market(
            ticker, expiration, put_short, put_long, call_short, call_long
        )
        price = mtm["cost_to_close"] if mtm else 0.0

    pnl_per_contract = (entry_credit - price) * 100
    realized_pnl = round(pnl_per_contract * contracts, 2)

    now_ts = get_central_time().strftime("%Y-%m-%d %H:%M:%S")
    today_str = get_central_time().strftime("%Y-%m-%d")

    # Close position
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

    # Update paper account
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

    # PDT log
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

    # Mirror close to sandbox (FLAME only — SPARK is paper-only)
    if bot["name"] == "flame":
        try:
            close_ic_order_all_accounts(
                ticker, expiration, put_short, put_long, call_short, call_long,
                contracts, price, position_id,
            )
        except Exception as e:
            log.warning(f"Sandbox close failed for {position_id}: {e}")

    # Log
    details = json.dumps({
        "position_id": position_id,
        "close_price": price,
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
            'AUTO CLOSE: {position_id} @ ${price:.4f} P&L=${realized_pnl:.2f} [{reason}]',
            '{details.replace(chr(39), chr(39)+chr(39))}',
            '{bot['dte']}'
        )
    """)

    # Daily perf — use MERGE for upsert
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
        f"${realized_pnl:.2f} [{reason}]"
    )


# ---------------------------------------------------------------------------
#  Monitor Position — port of monitorPosition() from scanner.ts
# ---------------------------------------------------------------------------


def monitor_position(bot: dict, ct: datetime) -> dict:
    """Monitor open position for PT/SL/EOD/stale holdover close."""
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

    pos = positions[0]
    entry_credit = num(pos["total_credit"])
    contracts = to_int(pos["contracts"])
    collateral = num(pos["collateral_required"])
    profit_target_price = round(entry_credit * 0.7, 4)
    stop_loss_price = round(entry_credit * 2.0, 4)
    ticker = pos.get("ticker") or "SPY"
    exp_raw = pos.get("expiration")
    expiration = str(exp_raw)[:10] if exp_raw else ""

    # Check for stale holdover (position from prior day)
    open_time = pos.get("open_time")
    open_date_str = str(open_time)[:10] if open_time else None
    today_str = ct.strftime("%Y-%m-%d")
    is_stale_holdover = open_date_str is not None and open_date_str < today_str

    # EOD cutoff or stale holdover → force close
    if is_after_eod_cutoff(ct) or is_stale_holdover:
        close_reason = "stale_holdover" if is_stale_holdover else "eod_cutoff"
        close_position(
            bot, pos["position_id"], ticker, expiration,
            num(pos["put_short_strike"]), num(pos["put_long_strike"]),
            num(pos["call_short_strike"]), num(pos["call_long_strike"]),
            contracts, entry_credit, collateral, close_reason,
        )
        return {"status": f"closed:{close_reason}", "unrealizedPnl": 0}

    # Get MTM
    if not is_tradier_configured():
        return {"status": "monitoring:no_tradier", "unrealizedPnl": 0}

    mtm = get_ic_mark_to_market(
        ticker, expiration,
        num(pos["put_short_strike"]), num(pos["put_long_strike"]),
        num(pos["call_short_strike"]), num(pos["call_long_strike"]),
    )

    if not mtm:
        return {"status": "monitoring:mtm_failed", "unrealizedPnl": 0}

    cost_to_close = mtm["cost_to_close"]

    # Profit target: cost_to_close <= 70% of entry credit
    if cost_to_close <= profit_target_price:
        close_position(
            bot, pos["position_id"], ticker, expiration,
            num(pos["put_short_strike"]), num(pos["put_long_strike"]),
            num(pos["call_short_strike"]), num(pos["call_long_strike"]),
            contracts, entry_credit, collateral, "profit_target", cost_to_close,
        )
        return {
            "status": f"closed:profit_target@{cost_to_close:.4f}",
            "unrealizedPnl": 0,
        }

    # Stop loss: cost_to_close >= 200% of entry credit
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


# ---------------------------------------------------------------------------
#  Try Open Trade — port of tryOpenTrade() from scanner.ts
# ---------------------------------------------------------------------------


def try_open_trade(bot: dict, spot: float, vix: float) -> str:
    """Attempt to open a new IC position. Returns status string."""
    # VIX filter
    if vix > 32:
        return f"skip:vix_too_high({vix:.1f})"

    # Already traded today?
    today_trades = db_query(f"""
        SELECT COUNT(*) as cnt
        FROM {bot_table(bot['name'], 'pdt_log')}
        WHERE trade_date = CURRENT_DATE() AND dte_mode = '{bot['dte']}'
    """)
    if to_int(today_trades[0].get("cnt") if today_trades else 0) >= 1:
        return "skip:already_traded_today"

    # Get account
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
    buying_power = num(acct["buying_power"])
    if buying_power < 200:
        return f"skip:low_bp(${buying_power:.0f})"

    expected_move = (vix / 100 / math.sqrt(252)) * spot

    # Advisor
    adv = evaluate_advisor(vix, spot, expected_move, bot["dte"])
    if adv["advice"] == "SKIP":
        return f"skip:advisor({adv['reasoning']})"

    # Expiration
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

    # Strikes + credits
    strikes = calculate_strikes(spot, expected_move)
    credits = get_ic_entry_credit(
        "SPY", expiration,
        strikes["putShort"], strikes["putLong"],
        strikes["callShort"], strikes["callLong"],
    )
    if not credits or credits["totalCredit"] < 0.05:
        credit_val = credits["totalCredit"] if credits else 0
        return f"skip:credit_too_low(${credit_val:.4f})"

    # Sizing
    spread_width = strikes["putShort"] - strikes["putLong"]
    collateral_per = max(0, (spread_width - credits["totalCredit"]) * 100)
    if collateral_per <= 0:
        return "skip:bad_collateral"
    usable_bp = buying_power * 0.85
    max_contracts = min(10, max(1, math.floor(usable_bp / collateral_per)))
    total_collateral = collateral_per * max_contracts
    max_profit = credits["totalCredit"] * 100 * max_contracts
    max_loss = total_collateral

    # Position ID
    now = datetime.now()
    date_str = now.strftime("%Y%m%d")
    hex_str = format(random.randint(0, 0xFFFFFF), "06X")
    bot_name = bot["name"].upper()
    position_id = f"{bot_name}-{date_str}-{hex_str}"

    now_ts = get_central_time().strftime("%Y-%m-%d %H:%M:%S")
    today_date = get_central_time().strftime("%Y-%m-%d")

    # Build oracle factors as JSON string
    factors_json = json.dumps(adv["topFactors"]).replace("'", "''")

    # Insert position
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
            created_at, updated_at
        ) VALUES (
            '{position_id}', 'SPY', CAST('{expiration}' AS DATE),
            {strikes['putShort']}, {strikes['putLong']}, {credits['putCredit']},
            {strikes['callShort']}, {strikes['callLong']}, {credits['callCredit']},
            {max_contracts}, {spread_width}, {credits['totalCredit']}, {max_loss}, {max_profit},
            {total_collateral},
            {spot}, {vix}, {expected_move},
            0, 0, 'UNKNOWN',
            0, 0,
            {adv['confidence']}, {adv['winProbability']}, '{adv['advice']}',
            '{adv['reasoning'].replace(chr(39), chr(39)+chr(39))}', '{factors_json}', FALSE,
            FALSE, {spread_width}, {spread_width},
            'PAPER', 'PAPER',
            'open', CAST('{now_ts}' AS TIMESTAMP), CAST('{today_date}' AS DATE), '{bot['dte']}',
            CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP()
        )
    """)

    # Mirror to sandbox (FLAME only — SPARK is paper-only)
    sandbox_order_ids: dict[str, int] = {}
    if bot["name"] == "flame":
        try:
            sandbox_order_ids = place_ic_order_all_accounts(
                "SPY", expiration,
                strikes["putShort"], strikes["putLong"],
                strikes["callShort"], strikes["callLong"],
                max_contracts, credits["totalCredit"], position_id,
            )
            if sandbox_order_ids:
                sandbox_json = json.dumps(sandbox_order_ids).replace("'", "''")
                db_execute(f"""
                    UPDATE {bot_table(bot['name'], 'positions')}
                    SET sandbox_order_id = '{sandbox_json}',
                        updated_at = CURRENT_TIMESTAMP()
                    WHERE position_id = '{position_id}'
                """)
        except Exception as e:
            log.warning(f"Sandbox open failed for {position_id}: {e}")

    # Deduct collateral
    acct_id = acct["id"]
    db_execute(f"""
        UPDATE {bot_table(bot['name'], 'paper_account')}
        SET collateral_in_use = collateral_in_use + {total_collateral},
            buying_power = buying_power - {total_collateral},
            updated_at = CURRENT_TIMESTAMP()
        WHERE id = {acct_id}
    """)

    # Signal log
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
            {credits['totalCredit']}, {adv['confidence']}, TRUE,
            'Auto scan | {adv['reasoning'].replace(chr(39), chr(39)+chr(39))}',
            FALSE, '{bot['dte']}'
        )
    """)

    # Trade log
    trade_details = json.dumps({
        "position_id": position_id,
        "contracts": max_contracts,
        "credit": credits["totalCredit"],
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
            'AUTO TRADE: {position_id} {strikes['putLong']}/{strikes['putShort']}P-{strikes['callShort']}/{strikes['callLong']}C x{max_contracts} @ ${credits['totalCredit']:.4f}',
            '{trade_details}',
            '{bot['dte']}'
        )
    """)

    # PDT log
    db_execute(f"""
        INSERT INTO {bot_table(bot['name'], 'pdt_log')} (
            trade_date, symbol, position_id, opened_at,
            contracts, entry_credit, dte_mode, created_at
        ) VALUES (
            CURRENT_DATE(), 'SPY', '{position_id}', CURRENT_TIMESTAMP(),
            {max_contracts}, {credits['totalCredit']}, '{bot['dte']}',
            CURRENT_TIMESTAMP()
        )
    """)

    # Equity snapshot
    updated_acct = db_query(f"""
        SELECT current_balance, cumulative_pnl
        FROM {bot_table(bot['name'], 'paper_account')}
        WHERE id = {acct_id}
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

    # Daily perf — MERGE for upsert
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
        f"x{max_contracts} @ ${credits['totalCredit']:.4f} "
        f"[sandbox:{json.dumps(sandbox_order_ids)}]"
    )
    return f"traded:{position_id}"


# ---------------------------------------------------------------------------
#  Scan Bot — port of scanBot() from scanner.ts
# ---------------------------------------------------------------------------


def scan_bot(bot: dict) -> None:
    """One scan cycle for one bot — mirrors scanner.ts scanBot() exactly."""
    ct = get_central_time()
    bot_name = bot["name"].upper()
    action = "scan"
    reason = ""
    spot = 0.0
    vix = 0.0
    unrealized_pnl = 0.0

    try:
        # Step 1: Always monitor open positions first
        open_rows = db_query(f"""
            SELECT position_id
            FROM {bot_table(bot['name'], 'positions')}
            WHERE status = 'open' AND dte_mode = '{bot['dte']}'
            LIMIT 1
        """)
        has_open_position = len(open_rows) > 0

        if has_open_position:
            monitor_result = monitor_position(bot, ct)
            if monitor_result["status"].startswith("closed:"):
                action = "closed"
            else:
                action = "monitoring"
            reason = monitor_result["status"]
            unrealized_pnl = monitor_result["unrealizedPnl"]

        # Step 2: If market closed, log and return
        if not is_market_open(ct):
            if not has_open_position:
                action = "outside_window"
                reason = f"Market closed ({ct.hour}:{ct.minute:02d} CT)"
        # Step 3: If in entry window and no position → try to trade
        elif not has_open_position and is_in_entry_window(ct):
            if not is_tradier_configured():
                action = "skip"
                reason = "tradier_not_configured"
            else:
                spy_quote = get_quote("SPY")
                vix_quote = get_quote("VIX")
                spot = spy_quote["last"] if spy_quote else 0.0
                vix = vix_quote["last"] if vix_quote else 20.0

                if spot == 0:
                    action = "skip"
                    reason = "no_spy_quote"
                else:
                    trade_result = try_open_trade(bot, spot, vix)
                    if trade_result.startswith("traded:"):
                        action = "traded"
                    else:
                        action = "no_trade"
                    reason = trade_result
        elif not has_open_position:
            action = "outside_entry_window"
            reason = f"Past entry cutoff ({ct.hour}:{ct.minute:02d} CT, cutoff 14:00)"

        # Take equity snapshot every cycle
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

    # Update heartbeat + log
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

    # Log every scan
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


# ---------------------------------------------------------------------------
#  Main Loop
# ---------------------------------------------------------------------------

_scan_count = 0


def run_scan_cycle() -> None:
    """Run one full cycle for all bots."""
    global _scan_count
    _scan_count += 1
    log.info(f"=== scan cycle #{_scan_count} starting ===")
    for bot in BOTS:
        try:
            scan_bot(bot)
        except Exception as e:
            log.error(f"{bot['name'].upper()} fatal error: {traceback.format_exc()}")
    log.info(f"=== scan cycle #{_scan_count} complete ===")


def main() -> None:
    """Main entry point — runs scan loop every 5 minutes."""
    log.info("IronForge Databricks scanner starting")
    log.info(f"  Catalog: {CATALOG}")
    log.info(f"  Schema: {SCHEMA}")
    log.info(f"  Tradier configured: {is_tradier_configured()}")
    log.info(f"  Sandbox accounts: {len(_get_sandbox_accounts_lazy())}")
    log.info(f"  Scan interval: {SCAN_INTERVAL}s")

    while True:
        ct = get_central_time()
        if is_market_open(ct):
            run_scan_cycle()
        else:
            log.info(f"Market closed ({ct.hour}:{ct.minute:02d} CT), waiting...")
        time.sleep(SCAN_INTERVAL)


if __name__ == "__main__":
    main()
