# Databricks notebook source

# COMMAND ----------

# MAGIC %md
# MAGIC # Position Monitor — Fast PT/SL/EOD Monitor
# MAGIC
# MAGIC Runs on a faster cadence than the scanner to catch profit targets and stop losses quickly.
# MAGIC Monitors all open positions for FLAME, SPARK, and INFERNO.
# MAGIC
# MAGIC **Config must match the scanner exactly** — sl_mult, pt_pct, spread_width cap.

# COMMAND ----------

# ── CREDENTIALS ──────────────────────────────────────────────────────────
import os

def _set_if_missing(key, fallback):
    if not os.environ.get(key):
        os.environ[key] = fallback

_set_if_missing("TRADIER_API_KEY", "HbOM7HNC6Ibs6QAE6hYgr02rpx2K")
_set_if_missing("TRADIER_SANDBOX_KEY_USER", "iPidGGnYrhzjp6vGBBQw8HyqF0xj")
_set_if_missing("TRADIER_SANDBOX_KEY_MATT", "AGoNTv6o6GKMKT8uc7ooVNOct0e0")
_set_if_missing("TRADIER_SANDBOX_KEY_LOGAN", "AcDucIMyjeNgFh60LWOb0F5fhXHh")
_set_if_missing("TRADIER_SANDBOX_ACCOUNT_ID_USER", "VA39284047")
_set_if_missing("TRADIER_SANDBOX_ACCOUNT_ID_MATT", "VA55391129")
_set_if_missing("TRADIER_SANDBOX_ACCOUNT_ID_LOGAN", "VA59240884")
_set_if_missing("DATABRICKS_CATALOG", "alpha_prime")
_set_if_missing("DATABRICKS_SCHEMA", "ironforge")

print(f"Tradier: {'OK' if os.environ.get('TRADIER_API_KEY') else 'MISSING'}")

# COMMAND ----------

import json
import math
import time
import random
import logging
import requests
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Optional, Any

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s %(message)s")
log = logging.getLogger("position_monitor")

CATALOG = os.environ.get("DATABRICKS_CATALOG", "alpha_prime")
SCHEMA = os.environ.get("DATABRICKS_SCHEMA", "ironforge")

# ── BOT CONFIG — MUST MATCH SCANNER BOT_CONFIG EXACTLY ──────────────────
BOT_CONFIG = {
    "flame":   {"pt_pct": 0.30, "sl_mult": 2.0},   # SL at 2x credit = 100% loss
    "spark":   {"pt_pct": 0.30, "sl_mult": 2.0},   # SL at 2x credit = 100% loss
    "inferno": {"pt_pct": 0.50, "sl_mult": 3.0},   # SL at 3x credit = 200% loss
}

# DB field → BOT_CONFIG key mapping (mirrors scanner _DB_TO_CFG)
_DB_TO_CFG = {
    "profit_target_pct": ("pt_pct", lambda v: float(v) / 100.0),  # DB stores 30.0 → we use 0.30
    "stop_loss_pct": ("sl_mult", lambda v: float(v) / 100.0),     # DB stores 200.0 → we use 2.0
}

def load_config_overrides() -> None:
    """Read {bot}_config tables from Databricks and merge into BOT_CONFIG.

    Mirrors the scanner's load_config_overrides() so PT/SL thresholds stay in sync.
    Falls back silently to defaults if table doesn't exist or query fails.
    """
    dte_map = {"flame": "2DTE", "spark": "1DTE", "inferno": "0DTE"}
    for bot_name, defaults in BOT_CONFIG.items():
        dte = dte_map[bot_name]
        try:
            rows = db_query(
                f"SELECT * FROM {bot_table(bot_name, 'config')} "
                f"WHERE dte_mode = '{dte}' LIMIT 1"
            )
            if not rows:
                continue
            row = rows[0]
            for db_col, mapping in _DB_TO_CFG.items():
                val = row.get(db_col)
                if val is None:
                    continue
                if isinstance(mapping, tuple):
                    cfg_key, transform = mapping
                    defaults[cfg_key] = transform(val)
                else:
                    defaults[mapping] = float(val)
            log.info(f"[{bot_name.upper()}] Config overrides loaded: pt_pct={defaults['pt_pct']}, sl_mult={defaults['sl_mult']}")
        except Exception as e:
            log.debug(f"[{bot_name.upper()}] Config table not found (using defaults): {e}")
        # Sanitize: Databricks returns Decimal objects — force all numeric config to float
        for k, v in defaults.items():
            if hasattr(v, '__float__') and not isinstance(v, (int, float)):
                defaults[k] = float(v)


BOTS = [
    {"name": "flame",   "dte": "2DTE"},
    {"name": "spark",   "dte": "1DTE"},
    {"name": "inferno", "dte": "0DTE"},
]

CENTRAL_TZ = ZoneInfo("America/Chicago")

spark.sql("SET TIME ZONE 'America/Chicago'")

# COMMAND ----------

# ── Databricks SQL helpers ───────────────────────────────────────────────

def db_query(sql_str):
    result = spark.sql(sql_str)
    rows = result.collect()
    if not rows:
        return []
    return [dict(zip(result.columns, row)) for row in rows]

def db_execute(sql_str):
    """Execute a SQL statement (INSERT/UPDATE/DELETE).
    Returns num_affected_rows for DML (UPDATE/DELETE/MERGE), 0 for DDL/INSERT.
    """
    result = spark.sql(sql_str)
    try:
        rows = result.collect()
        if rows and len(rows) > 0 and len(rows[0]) > 0:
            val = rows[0][0]
            if isinstance(val, (int, float)):
                return int(val)
    except Exception:
        pass
    return 0

def bot_table(bot_name, suffix):
    return f"{CATALOG}.{SCHEMA}.{bot_name}_{suffix}"

def shared_table(name):
    return f"{CATALOG}.{SCHEMA}.{name}"

def num(val):
    if val is None or val == "":
        return 0.0
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0

def to_int(val):
    if val is None or val == "":
        return 0
    try:
        return int(val)
    except (ValueError, TypeError):
        return 0

def get_central_time():
    return datetime.now(CENTRAL_TZ)

# COMMAND ----------

# ── Tradier API ──────────────────────────────────────────────────────────

TRADIER_BASE_URL = "https://api.tradier.com/v1"
SANDBOX_URL = "https://sandbox.tradier.com/v1"

def tradier_get(endpoint, params=None):
    api_key = os.environ.get("TRADIER_API_KEY", "")
    if not api_key:
        return None
    try:
        resp = requests.get(
            f"{TRADIER_BASE_URL}{endpoint}",
            params=params or {},
            headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        log.warning(f"Tradier API error: {e}")
    return None

def get_option_quote(occ_symbol):
    data = tradier_get("/markets/quotes", {"symbols": occ_symbol, "greeks": "false"})
    if not data:
        return None
    quotes = data.get("quotes", {})
    # Check for unmatched symbols (invalid OCC)
    if quotes.get("unmatched_symbols"):
        return None
    q = quotes.get("quote")
    if not q:
        return None
    if isinstance(q, list):
        q = q[0]
    return {
        "bid": float(q.get("bid") or 0),
        "ask": float(q.get("ask") or 0),
        "last": float(q.get("last") or 0),
    }

def build_occ_symbol(ticker, expiration, strike, opt_type):
    exp_date = datetime.strptime(str(expiration)[:10], "%Y-%m-%d")
    exp_str = exp_date.strftime("%y%m%d")
    strike_str = f"{int(float(strike) * 1000):08d}"
    return f"{ticker}{exp_str}{opt_type}{strike_str}"

def get_ic_mark_to_market(ticker, expiration, put_short, put_long, call_short, call_long):
    """Get IC cost-to-close with spread_width cap (matches scanner fix)."""
    ps_q = get_option_quote(build_occ_symbol(ticker, expiration, put_short, "P"))
    pl_q = get_option_quote(build_occ_symbol(ticker, expiration, put_long, "P"))
    cs_q = get_option_quote(build_occ_symbol(ticker, expiration, call_short, "C"))
    cl_q = get_option_quote(build_occ_symbol(ticker, expiration, call_long, "C"))
    if not all([ps_q, pl_q, cs_q, cl_q]):
        return None

    # Cost to close: buy back shorts at ask, sell longs at bid
    raw_cost = ps_q["ask"] + cs_q["ask"] - pl_q["bid"] - cl_q["bid"]

    # Cap at spread width — theoretical max cost for an IC
    spread_width = round(put_short - put_long, 2)
    cost = min(max(0, raw_cost), spread_width)

    return {
        "cost_to_close": round(cost, 4),
        "put_short_ask": ps_q["ask"],
        "put_long_bid": pl_q["bid"],
        "call_short_ask": cs_q["ask"],
        "call_long_bid": cl_q["bid"],
        "spread_width": spread_width,
        "raw_cost": round(raw_cost, 4),
    }

# COMMAND ----------

# ── Sandbox API helpers ──────────────────────────────────────────────────

def _sandbox_get(endpoint, params, api_key):
    """Authenticated GET to Tradier sandbox API."""
    if not api_key:
        return None
    try:
        resp = requests.get(
            f"{SANDBOX_URL}{endpoint}",
            headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
            params=params or {},
            timeout=15,
        )
        if resp.ok:
            return resp.json()
        log.warning(f"Sandbox GET {endpoint}: {resp.status_code}")
    except Exception as e:
        log.warning(f"Sandbox GET error: {e}")
    return None

# COMMAND ----------

# ── Sandbox close mirroring (FLAME only) ─────────────────────────────────

def _sandbox_post(endpoint, body, api_key):
    try:
        resp = requests.post(
            f"{SANDBOX_URL}{endpoint}",
            data=body,
            headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
            timeout=15,
        )
        if resp.status_code in (200, 201):
            return resp.json()
        log.warning(f"Sandbox POST {endpoint}: {resp.status_code} {resp.text[:200]}")
    except Exception as e:
        log.warning(f"Sandbox POST error: {e}")
    return None

def _get_sandbox_accounts():
    accounts = []
    for name, key_env, acct_env in [
        ("User", "TRADIER_SANDBOX_KEY_USER", "TRADIER_SANDBOX_ACCOUNT_ID_USER"),
        ("Matt", "TRADIER_SANDBOX_KEY_MATT", "TRADIER_SANDBOX_ACCOUNT_ID_MATT"),
        ("Logan", "TRADIER_SANDBOX_KEY_LOGAN", "TRADIER_SANDBOX_ACCOUNT_ID_LOGAN"),
    ]:
        key = os.environ.get(key_env)
        acct_id = os.environ.get(acct_env)
        if key and acct_id:
            accounts.append({"name": name, "api_key": key, "account_id": acct_id})
    return accounts

def _get_sandbox_fill_price(api_key, account_id, order_id, max_wait=45):
    """Poll sandbox order for fill price (FLAME 1:1 sync)."""
    headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
    for attempt in range(max_wait // 3):
        try:
            resp = requests.get(
                f"{SANDBOX_URL}/accounts/{account_id}/orders/{order_id}",
                headers=headers, timeout=10
            )
            resp.raise_for_status()
            order = resp.json().get("order", {})
            status = order.get("status", "")
            if status == "filled":
                price = order.get("avg_fill_price")
                if price is not None and float(price) > 0:
                    return float(price)
                legs = order.get("leg", [])
                if isinstance(legs, dict):
                    legs = [legs]
                prices = [float(l.get("avg_fill_price", 0)) for l in legs if l.get("avg_fill_price")]
                if prices:
                    return round(sum(prices), 4)
            elif status in ("rejected", "canceled", "expired"):
                return None
        except Exception:
            pass
        time.sleep(3)
    return None

def mirror_close_to_sandbox(bot, position_id, ticker, expiration, ps, pl, cs, cl, contracts):
    """Close IC on all sandbox accounts with cascade fallback.

    Cascade close strategy (matches main scanner):
      1. 4-leg multileg close (2 attempts)
      2. 2 × 2-leg spread close (put spread + call spread)
      3. 4 individual leg closes

    Returns User fill price if available.
    """
    if bot["name"] != "flame":
        return None

    accounts = _get_sandbox_accounts()
    if not accounts:
        return None

    # Read sandbox_order_id from position to get per-account contract counts
    sb_rows = db_query(f"""
        SELECT sandbox_order_id
        FROM {bot_table(bot['name'], 'positions')}
        WHERE position_id = '{position_id}' AND dte_mode = '{bot['dte']}'
    """)
    sb_json_str = sb_rows[0].get("sandbox_order_id", "") if sb_rows else ""
    sb_open_info = {}
    if sb_json_str:
        try:
            sb_open_info = json.loads(sb_json_str)
        except (json.JSONDecodeError, TypeError):
            pass

    occ_ps = build_occ_symbol(ticker, expiration, ps, "P")
    occ_pl = build_occ_symbol(ticker, expiration, pl, "P")
    occ_cs = build_occ_symbol(ticker, expiration, cs, "C")
    occ_cl = build_occ_symbol(ticker, expiration, cl, "C")

    user_fill_price = None
    failed_accounts = []

    for acct in accounts:
        acct_id = acct["account_id"]
        acct_name = acct["name"]
        # Use per-account contract count if available, else use paper contracts
        acct_info = sb_open_info.get(acct_name, {})
        acct_contracts = acct_info.get("contracts", contracts) if isinstance(acct_info, dict) else contracts

        close_ok = False

        # --- Stage 1: 4-leg multileg close (2 attempts) ---
        body_4leg = {
            "class": "multileg",
            "symbol": ticker,
            "type": "market",
            "duration": "day",
            "option_symbol[0]": occ_ps, "side[0]": "buy_to_close",  "quantity[0]": str(acct_contracts),
            "option_symbol[1]": occ_pl, "side[1]": "sell_to_close", "quantity[1]": str(acct_contracts),
            "option_symbol[2]": occ_cs, "side[2]": "buy_to_close",  "quantity[2]": str(acct_contracts),
            "option_symbol[3]": occ_cl, "side[3]": "sell_to_close", "quantity[3]": str(acct_contracts),
        }
        result = _sandbox_post(f"/accounts/{acct_id}/orders", body_4leg, acct["api_key"])
        if result and result.get("order", {}).get("id"):
            order_id = result["order"]["id"]
            log.info(f"  Sandbox [{acct_name}] close order #{order_id} (4-leg)")
            close_ok = True
        else:
            # Retry 4-leg after 1s
            log.warning(f"  Sandbox [{acct_name}] 4-leg attempt 1 failed, retrying...")
            time.sleep(1)
            result = _sandbox_post(f"/accounts/{acct_id}/orders", body_4leg, acct["api_key"])
            if result and result.get("order", {}).get("id"):
                order_id = result["order"]["id"]
                log.info(f"  Sandbox [{acct_name}] close order #{order_id} (4-leg retry)")
                close_ok = True

        # --- Stage 2: 2 × 2-leg spread close ---
        put_id = None
        call_id = None
        if not close_ok:
            log.warning(f"  Sandbox [{acct_name}] 4-leg FAILED — falling back to 2x 2-leg spreads")
            put_spread_body = {
                "class": "multileg",
                "symbol": ticker,
                "type": "market",
                "duration": "day",
                "option_symbol[0]": occ_ps, "side[0]": "buy_to_close",  "quantity[0]": str(acct_contracts),
                "option_symbol[1]": occ_pl, "side[1]": "sell_to_close", "quantity[1]": str(acct_contracts),
            }
            call_spread_body = {
                "class": "multileg",
                "symbol": ticker,
                "type": "market",
                "duration": "day",
                "option_symbol[0]": occ_cs, "side[0]": "buy_to_close",  "quantity[0]": str(acct_contracts),
                "option_symbol[1]": occ_cl, "side[1]": "sell_to_close", "quantity[1]": str(acct_contracts),
            }
            put_result = _sandbox_post(f"/accounts/{acct_id}/orders", put_spread_body, acct["api_key"])
            call_result = _sandbox_post(f"/accounts/{acct_id}/orders", call_spread_body, acct["api_key"])
            put_id = put_result.get("order", {}).get("id") if put_result else None
            call_id = call_result.get("order", {}).get("id") if call_result else None

            if put_id and call_id:
                order_id = put_id
                log.info(f"  Sandbox [{acct_name}] close OK (2x2-leg): put={put_id} call={call_id}")
                close_ok = True

        # --- Stage 3: 4 individual leg closes ---
        if not close_ok:
            log.warning(
                f"  Sandbox [{acct_name}] 2-leg FAILED "
                f"(put={'OK' if put_id else 'FAIL'}, call={'OK' if call_id else 'FAIL'}) — "
                f"falling back to individual legs"
            )
            individual_legs = [
                (occ_ps, "buy_to_close",  "put_short"),
                (occ_pl, "sell_to_close", "put_long"),
                (occ_cs, "buy_to_close",  "call_short"),
                (occ_cl, "sell_to_close", "call_long"),
            ]
            any_leg_ok = False
            for occ, side, label in individual_legs:
                # Skip legs already closed by partial 2-leg success
                if label.startswith("put") and put_id:
                    continue
                if label.startswith("call") and call_id:
                    continue

                leg_body = {
                    "class": "option",
                    "symbol": ticker,
                    "option_symbol": occ,
                    "side": side,
                    "quantity": str(acct_contracts),
                    "type": "market",
                    "duration": "day",
                }
                leg_result = _sandbox_post(f"/accounts/{acct_id}/orders", leg_body, acct["api_key"])
                leg_id = leg_result.get("order", {}).get("id") if leg_result else None
                if leg_id:
                    any_leg_ok = True
                    log.info(f"  Sandbox [{acct_name}] leg close OK: {label} order_id={leg_id}")
                else:
                    log.error(f"  Sandbox [{acct_name}] leg close FAILED: {label}")

            if any_leg_ok:
                order_id = -1  # flag cascade used
                close_ok = True
                log.info(f"  Sandbox [{acct_name}] cascade completed (individual legs)")
            else:
                log.error(
                    f"  Sandbox [{acct_name}] ALL close strategies FAILED — "
                    f"sandbox ORPHAN likely for {position_id}"
                )
                failed_accounts.append(acct_name)

        # FLAME 1:1: Wait for User fill to use as paper close price
        if close_ok and acct_name == "User" and order_id and order_id > 0:
            fill = _get_sandbox_fill_price(acct["api_key"], acct_id, order_id)
            if fill is not None and fill >= 0:
                user_fill_price = fill
                log.info(f"  FLAME 1:1: User fill ${fill:.4f}")

    # Log sandbox failures to DB for triage visibility
    if failed_accounts:
        fail_details = json.dumps({
            "position_id": position_id,
            "failed_accounts": failed_accounts,
            "source": "position_monitor",
        }).replace("'", "''")
        try:
            db_execute(f"""
                INSERT INTO {bot_table('flame', 'logs')}
                    (log_time, level, message, details, dte_mode)
                VALUES (
                    CURRENT_TIMESTAMP(),
                    'SANDBOX_CLOSE_FAIL',
                    'MONITOR: Sandbox close cascade FAILED for {position_id} on [{",".join(failed_accounts)}]',
                    '{fail_details}',
                    '{bot['dte']}'
                )
            """)
        except Exception:
            pass

    return user_fill_price

# COMMAND ----------

# ── Orphan sandbox fill recovery (FLAME only) ────────────────────────────
# If the scanner placed a sandbox order but timed out waiting for fill,
# and the order filled AFTER the scanner moved on, we have a live Tradier
# position with no matching paper position.  This function detects that
# and creates the paper position retroactively using the sandbox fill data.
# FLAME only trades once/day — same strikes on paper and sandbox.

def parse_occ_symbol(symbol):
    """Parse OCC symbol → (ticker, expiration, strike, opt_type).

    Example: SPY260316C00684000 → ("SPY", "2026-03-16", 684.0, "C")
    """
    try:
        ticker = symbol[:3]
        yy = symbol[3:5]
        mm = symbol[5:7]
        dd = symbol[7:9]
        opt_type = symbol[9]  # C or P
        strike = int(symbol[10:]) / 1000.0
        expiration = f"20{yy}-{mm}-{dd}"
        return ticker, expiration, strike, opt_type
    except (IndexError, ValueError):
        return None, None, None, None


def recover_orphan_sandbox_fills():
    """Check if User sandbox has filled positions that paper doesn't know about.

    FLAME trades once/day, so the logic is simple:
    1. Query User sandbox for open SPY option positions
    2. Group them by expiration into IC legs (should be 4 legs)
    3. Check if FLAME has a matching paper position (open OR closed today)
    4. Check PDT budget + max_trades_per_day before creating
    5. If unmatched + budget allows → create paper position from sandbox fill

    Invariants enforced:
    - INV-31: Check open AND closed positions for de-dup
    - INV-32: Max 1 orphan recovery per day (hard ceiling)
    - INV-33: Check PDT before creating (same-day position = potential day trade)
    - INV-34: Partial fills (< 4 legs) = alert only, no auto-close
    - INV-35: Only same-day positions (ignore stale/expired)
    - INV-36: Paper account sizing, not sandbox quantities
    - INV-37: Respect max_trades_per_day from scanner config

    Runs every monitor cycle — fast (1 API call + a few DB queries).
    Only acts for FLAME (the only bot using sandbox).
    """
    bot = {"name": "flame", "dte": "2DTE"}
    ct = get_central_time()
    today_str = ct.strftime("%Y-%m-%d")

    # Only during market hours — sandbox positions aren't meaningful after close
    hhmm = ct.hour * 100 + ct.minute
    if hhmm < 830 or hhmm > 1500:
        return

    # INV-32: Hard limit — max 1 orphan recovery per day
    # Check if we already recovered today (via logs table)
    already_recovered = db_query(f"""
        SELECT COUNT(*) as cnt FROM {bot_table('flame', 'logs')}
        WHERE level = 'ORPHAN_RECOVERY'
          AND CAST(log_time AS DATE) = CURRENT_DATE()
          AND dte_mode = '2DTE'
    """)
    if to_int(already_recovered[0].get("cnt") if already_recovered else 0) > 0:
        return  # Already recovered once today — hard ceiling

    # 1. Get User sandbox account
    accounts = _get_sandbox_accounts()
    user_acct = None
    for a in accounts:
        if a["name"] == "User":
            user_acct = a
            break
    if not user_acct:
        return

    # 2. Query User sandbox positions
    data = _sandbox_get(
        f"/accounts/{user_acct['account_id']}/positions",
        None, user_acct["api_key"]
    )
    if not data:
        return

    positions = data.get("positions", {})
    if not positions or positions == "null":
        return

    pos_list = positions.get("position", [])
    if isinstance(pos_list, dict):
        pos_list = [pos_list]

    # 3. Parse SPY option positions, group by expiration
    #    An IC has 4 legs: sell put, buy put, sell call, buy call
    legs_by_exp = {}
    for p in pos_list:
        symbol = p.get("symbol", "")
        qty = p.get("quantity", 0)
        if not symbol or qty == 0:
            continue
        ticker, expiration, strike, opt_type = parse_occ_symbol(symbol)
        if ticker != "SPY" or not expiration:
            continue
        # INV-35: Only same-day or future expirations — ignore stale/expired
        if expiration < today_str:
            continue
        if expiration not in legs_by_exp:
            legs_by_exp[expiration] = []
        legs_by_exp[expiration].append({
            "symbol": symbol,
            "strike": strike,
            "opt_type": opt_type,
            "quantity": qty,
            "cost_basis": float(p.get("cost_basis", 0)),
        })

    if not legs_by_exp:
        return

    # 4. For each expiration group, identify IC or alert on partial fills
    for expiration, legs in legs_by_exp.items():
        if len(legs) != 4:
            # INV-34: Partial fill — alert only, never auto-close
            if 0 < len(legs) < 4:
                leg_details = json.dumps([
                    {"symbol": l["symbol"], "qty": l["quantity"], "strike": l["strike"],
                     "type": l["opt_type"]}
                    for l in legs
                ]).replace("'", "''")
                log.warning(
                    f"PARTIAL FILL DETECTED: Sandbox has {len(legs)} legs for exp={expiration} "
                    f"(need 4 for IC) — operator must decide"
                )
                db_execute(f"""
                    INSERT INTO {bot_table('flame', 'logs')}
                        (log_time, level, message, details, dte_mode)
                    VALUES (
                        CURRENT_TIMESTAMP(),
                        'PARTIAL_FILL_DETECTED',
                        'MONITOR: Sandbox has {len(legs)}/4 IC legs for exp={expiration} — manual review required',
                        '{leg_details}',
                        '2DTE'
                    )
                """)
            continue

        # Identify the IC structure:
        #   Short put  (qty < 0, P), Long put  (qty > 0, P)
        #   Short call (qty < 0, C), Long call (qty > 0, C)
        puts = [l for l in legs if l["opt_type"] == "P"]
        calls = [l for l in legs if l["opt_type"] == "C"]
        if len(puts) != 2 or len(calls) != 2:
            continue

        short_put = next((l for l in puts if l["quantity"] < 0), None)
        long_put = next((l for l in puts if l["quantity"] > 0), None)
        short_call = next((l for l in calls if l["quantity"] < 0), None)
        long_call = next((l for l in calls if l["quantity"] > 0), None)

        if not all([short_put, long_put, short_call, long_call]):
            continue

        ps = short_put["strike"]
        pl = long_put["strike"]
        cs = short_call["strike"]
        cl = long_call["strike"]
        sandbox_contracts = abs(short_put["quantity"])

        # 5. INV-31: Check BOTH open AND closed positions for de-dup
        existing = db_query(f"""
            SELECT position_id, status FROM {bot_table('flame', 'positions')}
            WHERE dte_mode = '2DTE'
              AND put_short_strike = {ps} AND put_long_strike = {pl}
              AND call_short_strike = {cs} AND call_long_strike = {cl}
              AND expiration = CAST('{expiration}' AS DATE)
              AND (status = 'open' OR open_date = CAST('{today_str}' AS DATE))
        """)

        if existing:
            # Paper position already exists (open or closed today) — in sync
            continue

        # Also check: does FLAME already have ANY open position today?
        # FLAME trades once/day — if there's already an open position, don't create another
        any_open_today = db_query(f"""
            SELECT position_id FROM {bot_table('flame', 'positions')}
            WHERE status = 'open' AND dte_mode = '2DTE'
              AND open_date = CAST('{today_str}' AS DATE)
        """)
        if any_open_today:
            log.info(
                f"ORPHAN RECOVERY SKIP: FLAME already has open position {any_open_today[0]['position_id']} "
                f"today — sandbox has unmatched {ps}/{pl}P-{cs}/{cl}C but won't create duplicate"
            )
            continue

        # 6. INV-37 + INV-33: Check PDT budget + max_trades_per_day
        #    Mirrors scanner's try_open_trade() checks (ironforge_scanner.py:1821-1849)
        pdt_cfg_rows = db_query(f"""
            SELECT pdt_enabled, day_trade_count, max_day_trades, max_trades_per_day
            FROM {shared_table('ironforge_pdt_config')}
            WHERE bot_name = 'FLAME'
            LIMIT 1
        """)
        pdt_cfg = pdt_cfg_rows[0] if pdt_cfg_rows else {}
        pdt_enabled = pdt_cfg.get("pdt_enabled", True) not in (False, 0, "false")
        pdt_count = to_int(pdt_cfg.get("day_trade_count", 0))
        max_day_trades = to_int(pdt_cfg.get("max_day_trades", 3))  # rolling window
        max_trades_per_day = to_int(pdt_cfg.get("max_trades_per_day", 1))  # daily limit

        # Check max_trades_per_day (scanner uses pdt_log count)
        if pdt_enabled and max_trades_per_day > 0:
            today_trades = db_query(f"""
                SELECT COUNT(*) as cnt
                FROM {bot_table('flame', 'pdt_log')}
                WHERE trade_date = CURRENT_DATE() AND dte_mode = '2DTE'
            """)
            today_count = to_int(today_trades[0].get("cnt") if today_trades else 0)
            if today_count >= max_trades_per_day:
                log.info(
                    f"ORPHAN RECOVERY SKIP: max_trades_per_day reached "
                    f"({today_count}/{max_trades_per_day}) — sandbox orphan not recovered"
                )
                continue

        # Check PDT rolling window
        if pdt_enabled and max_day_trades > 0 and pdt_count >= max_day_trades:
            log.info(
                f"ORPHAN RECOVERY SKIP: PDT blocked "
                f"({pdt_count}/{max_day_trades} day trades in rolling window)"
            )
            continue

        # 7. ORPHAN DETECTED — all gates passed, create paper position
        log.warning(
            f"ORPHAN FILL DETECTED: Sandbox has {ps}/{pl}P-{cs}/{cl}C exp={expiration} "
            f"x{sandbox_contracts} but no paper position — creating now"
        )

        # Get entry credit from sandbox cost basis
        total_cost_basis = sum(l["cost_basis"] for l in legs)
        # Tradier cost_basis: negative = credit received, positive = debit paid
        entry_credit = abs(total_cost_basis) / (sandbox_contracts * 100)

        # If cost basis is unreliable, get live MTM as fallback
        if entry_credit < 0.01:
            mtm = get_ic_mark_to_market("SPY", expiration, ps, pl, cs, cl)
            if mtm:
                entry_credit = mtm["cost_to_close"]
            else:
                entry_credit = 0.10  # absolute minimum fallback
            log.warning(f"  Cost basis unreliable, using {'MTM' if mtm else 'minimum'}: ${entry_credit:.4f}")

        # INV-36: Paper sizing (matches scanner ironforge_scanner.py:1909-1916)
        spread_width = round(ps - pl, 2)
        collateral_per = max(0, (spread_width - entry_credit) * 100)

        # Get paper account for sizing
        acct_rows = db_query(f"""
            SELECT id, current_balance, buying_power
            FROM {bot_table('flame', 'paper_account')}
            WHERE is_active = TRUE AND dte_mode = '2DTE'
            ORDER BY id DESC LIMIT 1
        """)
        if not acct_rows:
            log.error("ORPHAN RECOVERY FAILED: No paper account found")
            continue

        paper_acct = acct_rows[0]
        paper_acct_id = paper_acct["id"]
        balance = num(paper_acct["current_balance"])

        # Recalculate buying power from live collateral (matches scanner)
        live_coll_rows = db_query(f"""
            SELECT COALESCE(SUM(collateral_required), 0) AS total_collateral
            FROM {bot_table('flame', 'positions')}
            WHERE status = 'open' AND dte_mode = '2DTE'
        """)
        live_collateral = num(live_coll_rows[0]["total_collateral"]) if live_coll_rows else 0.0
        buying_power = balance - live_collateral

        if collateral_per <= 0:
            log.error(f"ORPHAN RECOVERY FAILED: bad collateral_per={collateral_per}")
            continue

        if buying_power < 200:
            log.warning(f"ORPHAN RECOVERY SKIP: low buying power (${buying_power:.0f})")
            continue

        usable_bp = buying_power * 0.85
        bp_contracts = max(1, math.floor(usable_bp / collateral_per))
        max_contracts = min(10, bp_contracts)  # cap at 10 for paper

        total_collateral = collateral_per * max_contracts
        max_profit = entry_credit * 100 * max_contracts
        max_loss = total_collateral

        # Generate position ID
        date_str = ct.strftime("%Y%m%d")
        hex_str = format(random.randint(0, 0xFFFFFF), "06X")
        position_id = f"FLAME-{date_str}-{hex_str}"
        now_ts = ct.strftime("%Y-%m-%d %H:%M:%S")

        # Build sandbox_order_id JSON (we don't have the order_id, mark as recovered)
        sandbox_json = json.dumps({
            "User": {"recovered": True, "contracts": sandbox_contracts}
        }).replace("'", "''")

        # 8. INSERT paper position
        db_execute(f"""
            INSERT INTO {bot_table('flame', 'positions')} (
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
                sandbox_order_id, created_at, updated_at
            ) VALUES (
                '{position_id}', 'SPY', CAST('{expiration}' AS DATE),
                {ps}, {pl}, 0,
                {cs}, {cl}, 0,
                {max_contracts}, {spread_width}, {entry_credit}, {max_loss}, {max_profit},
                {total_collateral},
                0, 0, 0,
                0, 0, 'UNKNOWN',
                0, 0,
                0, 0, 'ORPHAN_RECOVERY',
                'Position recovered from sandbox fill — scanner timed out waiting for fill', '', FALSE,
                FALSE, {spread_width}, {spread_width},
                'PAPER', 'PAPER',
                'open', CAST('{now_ts}' AS TIMESTAMP), CAST('{today_str}' AS DATE), '2DTE',
                '{sandbox_json}', CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP()
            )
        """)

        # 9. Update paper_account collateral
        db_execute(f"""
            UPDATE {bot_table('flame', 'paper_account')}
            SET collateral_in_use = collateral_in_use + {total_collateral},
                buying_power = buying_power - {total_collateral},
                updated_at = CURRENT_TIMESTAMP()
            WHERE id = {paper_acct_id}
        """)

        # 10. PDT log — record this trade so scanner's daily count stays accurate
        db_execute(f"""
            INSERT INTO {bot_table('flame', 'pdt_log')} (
                trade_date, symbol, position_id, opened_at,
                contracts, entry_credit, dte_mode, created_at
            ) VALUES (
                CURRENT_DATE(), 'SPY', '{position_id}', CURRENT_TIMESTAMP(),
                {max_contracts}, {entry_credit}, '2DTE',
                CURRENT_TIMESTAMP()
            )
        """)

        # 11. Log it
        details = json.dumps({
            "position_id": position_id,
            "contracts_paper": max_contracts,
            "contracts_sandbox": sandbox_contracts,
            "entry_credit": entry_credit,
            "collateral": total_collateral,
            "source": "orphan_fill_recovery",
            "strikes": f"{pl}/{ps}P-{cs}/{cl}C",
            "expiration": expiration,
            "pdt_count": pdt_count,
            "max_trades_per_day": max_trades_per_day,
        }).replace("'", "''")
        db_execute(f"""
            INSERT INTO {bot_table('flame', 'logs')}
                (log_time, level, message, details, dte_mode)
            VALUES (
                CURRENT_TIMESTAMP(),
                'ORPHAN_RECOVERY',
                'MONITOR: Created paper position {position_id} from sandbox fill ({pl}/{ps}P-{cs}/{cl}C x{max_contracts})',
                '{details}',
                '2DTE'
            )
        """)

        # 12. Equity snapshot
        updated_acct = db_query(f"""
            SELECT current_balance, cumulative_pnl
            FROM {bot_table('flame', 'paper_account')}
            WHERE id = {paper_acct_id}
        """)
        if updated_acct:
            bal = num(updated_acct[0]["current_balance"])
            cum_pnl = num(updated_acct[0]["cumulative_pnl"])
            db_execute(f"""
                INSERT INTO {bot_table('flame', 'equity_snapshots')}
                    (snapshot_time, balance, realized_pnl, unrealized_pnl,
                     open_positions, note, dte_mode, created_at)
                VALUES (
                    CURRENT_TIMESTAMP(), {bal}, {cum_pnl}, 0,
                    1, 'orphan_recovery:{position_id}', '2DTE',
                    CURRENT_TIMESTAMP()
                )
            """)

        # 13. Daily perf — count as a trade
        db_execute(f"""
            MERGE INTO {bot_table('flame', 'daily_perf')} AS t
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
            f"ORPHAN RECOVERY COMPLETE: {position_id} "
            f"{pl}/{ps}P-{cs}/{cl}C x{max_contracts} (paper) / x{sandbox_contracts} (sandbox) "
            f"@ ${entry_credit:.4f} exp={expiration}"
        )


# COMMAND ----------

# ── Time checks ──────────────────────────────────────────────────────────

def is_after_eod_cutoff(ct):
    """EOD cutoff: 2:45 PM CT (matches scanner)."""
    hhmm = ct.hour * 100 + ct.minute
    return hhmm >= 1445

def get_sliding_profit_target(ct, base_pt=0.30, bot_name=""):
    """Sliding PT tiers — matches scanner exactly."""
    time_minutes = ct.hour * 60 + ct.minute
    is_inferno = bot_name == "inferno"

    # Before 10:30 AM CT (630 min) = MORNING
    if time_minutes < 630:
        return base_pt, "MORNING"
    # Before 1:00 PM CT (780 min) = MIDDAY
    elif time_minutes < 780:
        if is_inferno:
            return 0.30, "MIDDAY"
        return max(0.10, base_pt - 0.10), "MIDDAY"
    # After 1:00 PM CT = AFTERNOON
    else:
        if is_inferno:
            return 0.10, "AFTERNOON"
        return max(0.10, base_pt - 0.15), "AFTERNOON"

def validate_mtm(mtm, entry_credit):
    """Validate MTM data quality — matches scanner."""
    cost = mtm["cost_to_close"]
    if cost < 0:
        return False, "negative_cost"
    # All legs should have some value
    if mtm["put_short_ask"] <= 0 and mtm["call_short_ask"] <= 0:
        return False, "zero_short_asks"
    return True, ""

# COMMAND ----------

# ── Close position ───────────────────────────────────────────────────────

def close_position(bot, position_id, ticker, expiration, ps, pl, cs, cl,
                   contracts, entry_credit, reason, close_price=None):
    """Close position: update DB, mirror sandbox, reconcile collateral."""

    price = close_price
    price_source = "calculated"
    sandbox_fill_price = None

    # Get MTM if no price provided
    if price is None:
        mtm = get_ic_mark_to_market(ticker, expiration, ps, pl, cs, cl)
        price = mtm["cost_to_close"] if mtm else 0.0

    # FLAME: mirror close to sandbox and use User fill price (1:1)
    if bot["name"] == "flame":
        try:
            fill = mirror_close_to_sandbox(
                bot, position_id, ticker, expiration, ps, pl, cs, cl, contracts
            )
            if fill is not None and fill >= 0:
                sandbox_fill_price = fill
                price = fill
                price_source = "sandbox_fill"
                log.info(f"FLAME 1:1 close: using sandbox fill ${fill:.4f}")
        except Exception as e:
            log.warning(f"Sandbox close failed for {position_id}: {e}")
            # Log sandbox failure to DB so triage queries can find it
            sb_fail_details = json.dumps({
                "position_id": position_id,
                "error": str(e)[:500],
                "close_reason": reason,
                "source": "position_monitor",
            }).replace("'", "''")
            try:
                db_execute(f"""
                    INSERT INTO {bot_table('flame', 'logs')}
                        (log_time, level, message, details, dte_mode)
                    VALUES (
                        CURRENT_TIMESTAMP(),
                        'SANDBOX_CLOSE_FAIL',
                        'MONITOR: Sandbox close failed for {position_id}: {str(e)[:200]}',
                        '{sb_fail_details}',
                        '{bot['dte']}'
                    )
                """)
            except Exception:
                pass  # Don't let logging failure block position close

    realized_pnl = round((entry_credit - price) * 100 * contracts, 2)
    now_ts = get_central_time().strftime("%Y-%m-%d %H:%M:%S")
    today_str = get_central_time().strftime("%Y-%m-%d")

    # 1. Close the position (atomically — only if still open)
    rows_affected = db_execute(f"""
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

    if rows_affected == 0:
        log.warning(
            f"{bot['name'].upper()} {position_id}: position UPDATE matched 0 rows "
            f"(already closed by scanner or another monitor run). Skipping paper_account "
            f"update to prevent double-counting. realized_pnl would have been ${realized_pnl:.2f}"
        )
        # Still log to activity log so we know the monitor tried
        skip_details = json.dumps({
            "position_id": position_id,
            "skipped_pnl": realized_pnl,
            "close_reason": reason,
            "source": "position_monitor",
            "skip_reason": "already_closed_by_another_process",
        }).replace("'", "''")
        db_execute(f"""
            INSERT INTO {bot_table(bot['name'], 'logs')}
                (log_time, level, message, details, dte_mode)
            VALUES (
                CURRENT_TIMESTAMP(),
                'SKIP',
                'MONITOR SKIP: {position_id} already closed — would have been ${realized_pnl:.2f} [{reason}]',
                '{skip_details}',
                '{bot['dte']}'
            )
        """)
        return

    # 2. Reconcile collateral from actual remaining open positions
    pos_table = bot_table(bot['name'], 'positions')
    acct_table = bot_table(bot['name'], 'paper_account')
    remaining = db_query(f"""
        SELECT COALESCE(SUM(collateral_required), 0) AS total_collateral
        FROM {pos_table}
        WHERE status = 'open' AND dte_mode = '{bot['dte']}'
    """)
    actual_collateral = num(remaining[0]["total_collateral"]) if remaining else 0.0

    db_execute(f"""
        UPDATE {acct_table}
        SET current_balance = current_balance + {realized_pnl},
            cumulative_pnl = cumulative_pnl + {realized_pnl},
            total_trades = total_trades + 1,
            collateral_in_use = {actual_collateral},
            buying_power = current_balance + {realized_pnl} - {actual_collateral},
            high_water_mark = GREATEST(high_water_mark, current_balance + {realized_pnl}),
            max_drawdown = GREATEST(max_drawdown,
                GREATEST(high_water_mark, current_balance + {realized_pnl}) - (current_balance + {realized_pnl})),
            updated_at = CAST('{now_ts}' AS TIMESTAMP)
        WHERE is_active = TRUE AND dte_mode = '{bot['dte']}'
    """)

    # 3. PDT log
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

    # 4. PDT counter (same-day open+close)
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
            log.info(f"{bot_upper} PDT: day trade recorded, count {old_count} -> {new_count}")
    except Exception as pdt_err:
        log.warning(f"PDT counter update failed: {pdt_err}")

    # 5. Activity log
    details = json.dumps({
        "position_id": position_id,
        "scanner_close_price": price,
        "sandbox_fill_price": sandbox_fill_price,
        "price_source": price_source,
        "realized_pnl": realized_pnl,
        "close_reason": reason,
        "source": "position_monitor",
    }).replace("'", "''")

    db_execute(f"""
        INSERT INTO {bot_table(bot['name'], 'logs')}
            (log_time, level, message, details, dte_mode)
        VALUES (
            CURRENT_TIMESTAMP(),
            'TRADE_CLOSE',
            'MONITOR CLOSE: {position_id} @ ${price:.4f} P&L=${realized_pnl:.2f} [{reason}] ({price_source})',
            '{details}',
            '{bot['dte']}'
        )
    """)

    # 6. Daily perf
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

# COMMAND ----------

# ── Main monitor logic ───────────────────────────────────────────────────

def monitor_all_bots():
    ct = get_central_time()
    print(f"Position monitor at {ct.strftime('%Y-%m-%d %H:%M:%S')} CT")

    # Load config overrides from DB so PT/SL thresholds match the scanner
    load_config_overrides()
    for bot_name, cfg in BOT_CONFIG.items():
        print(f"  {bot_name.upper()} config: pt_pct={cfg['pt_pct']}, sl_mult={cfg['sl_mult']}")

    # FLAME: recover orphan sandbox fills before monitoring positions
    # (if scanner timed out waiting for fill but Tradier filled after)
    try:
        recover_orphan_sandbox_fills()
    except Exception as e:
        log.warning(f"Orphan fill recovery error (non-fatal): {e}")

    total_closed = 0

    for bot in BOTS:
        cfg = BOT_CONFIG[bot["name"]]

        positions = db_query(f"""
            SELECT position_id, ticker, expiration,
                   put_short_strike, put_long_strike,
                   call_short_strike, call_long_strike,
                   contracts, total_credit, max_loss,
                   collateral_required, open_time
            FROM {bot_table(bot['name'], 'positions')}
            WHERE status = 'open' AND dte_mode = '{bot['dte']}'
        """)

        if not positions:
            continue

        print(f"  {bot['name'].upper()}: {len(positions)} open position(s)")

        for pos in positions:
            entry_credit = num(pos["total_credit"])
            contracts = to_int(pos["contracts"])
            ticker = pos.get("ticker") or "SPY"
            exp_raw = pos.get("expiration")
            expiration = str(exp_raw)[:10] if exp_raw else ""

            open_time = pos.get("open_time")
            open_date_str = str(open_time)[:10] if open_time else None
            today_str = ct.strftime("%Y-%m-%d")
            is_stale = open_date_str is not None and open_date_str < today_str

            ps = num(pos["put_short_strike"])
            pl = num(pos["put_long_strike"])
            cs = num(pos["call_short_strike"])
            cl = num(pos["call_long_strike"])

            # 1. Stale/holdover or EOD cutoff — close immediately
            if is_stale or is_after_eod_cutoff(ct):
                reason = "stale_holdover" if is_stale else "eod_cutoff"
                try:
                    close_position(
                        bot, pos["position_id"], ticker, expiration,
                        ps, pl, cs, cl,
                        contracts, entry_credit, reason,
                    )
                except Exception as e:
                    log.warning(f"Force-close failed, retrying at entry credit: {e}")
                    close_position(
                        bot, pos["position_id"], ticker, expiration,
                        ps, pl, cs, cl,
                        contracts, entry_credit, reason,
                        close_price=entry_credit,
                    )
                total_closed += 1
                continue

            # 2. Get MTM quotes
            mtm = get_ic_mark_to_market(ticker, expiration, ps, pl, cs, cl)
            if not mtm:
                print(f"    {pos['position_id']}: MTM failed — skipping")
                continue

            # 3. Validate MTM
            is_valid, invalid_reason = validate_mtm(mtm, entry_credit)
            if not is_valid:
                print(f"    {pos['position_id']}: MTM invalid ({invalid_reason}) — skipping")
                continue

            cost_to_close = mtm["cost_to_close"]
            pt_pct, pt_tier = get_sliding_profit_target(ct, cfg["pt_pct"], bot["name"])
            profit_target_price = round(entry_credit * (1 - pt_pct), 4)
            stop_loss_price = round(entry_credit * cfg["sl_mult"], 4)

            # 4. Profit target
            if cost_to_close <= profit_target_price:
                reason = f"profit_target_{pt_tier.lower()}"
                close_position(
                    bot, pos["position_id"], ticker, expiration,
                    ps, pl, cs, cl,
                    contracts, entry_credit, reason, cost_to_close,
                )
                total_closed += 1
                print(
                    f"    {pos['position_id']}: PROFIT TARGET ({pt_tier} {pt_pct:.0%}): "
                    f"debit=${cost_to_close:.4f} <= threshold=${profit_target_price:.4f}"
                )
                continue

            # 5. Stop loss
            if cost_to_close >= stop_loss_price:
                log.info(
                    f"{bot['name'].upper()} STOP LOSS TRIGGER: "
                    f"cost_to_close=${cost_to_close:.4f} >= threshold=${stop_loss_price:.4f} "
                    f"(entry=${entry_credit:.4f} x sl_mult={cfg['sl_mult']}) "
                    f"legs: PS_ask={mtm['put_short_ask']:.4f} PL_bid={mtm['put_long_bid']:.4f} "
                    f"CS_ask={mtm['call_short_ask']:.4f} CL_bid={mtm['call_long_bid']:.4f}"
                )
                close_position(
                    bot, pos["position_id"], ticker, expiration,
                    ps, pl, cs, cl,
                    contracts, entry_credit, "stop_loss", cost_to_close,
                )
                total_closed += 1
                continue

            # 6. Still monitoring
            unrealized = round((entry_credit - cost_to_close) * 100 * contracts, 2)
            print(
                f"    {pos['position_id']}: mtm=${cost_to_close:.4f} "
                f"uPnL=${unrealized:.2f} "
                f"(PT=${profit_target_price:.4f} SL=${stop_loss_price:.4f})"
            )

    if total_closed > 0:
        print(f"  CLOSED {total_closed} position(s)")
    else:
        print(f"  No exits triggered")

    # Save equity snapshots for every bot (fills gaps when scanner isn't running)
    for bot in BOTS:
        try:
            acct_rows = db_query(f"""
                SELECT current_balance, cumulative_pnl
                FROM {bot_table(bot['name'], 'paper_account')}
                WHERE is_active = TRUE AND dte_mode = '{bot['dte']}'
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
                        0, {open_cnt},
                        'monitor_cycle', '{bot['dte']}',
                        CURRENT_TIMESTAMP()
                    )
                """)
        except Exception as snap_err:
            log.warning(f"{bot['name'].upper()} equity snapshot failed: {snap_err}")

print("Position monitor functions loaded")

# COMMAND ----------

# ── EXECUTE ──────────────────────────────────────────────────────────────
monitor_all_bots()
