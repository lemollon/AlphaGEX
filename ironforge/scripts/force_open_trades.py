# Databricks notebook source

# COMMAND ----------

# MAGIC %md
# MAGIC # Force Open Trades for All IronForge Bots
# MAGIC
# MAGIC Bypasses all gates (PDT, daily limit, entry window) and opens one IC position
# MAGIC per bot using live Tradier quotes for strike selection and credit pricing.
# MAGIC
# MAGIC - FLAME (2DTE): opens + mirrors to Tradier sandbox (User, Matt, Logan)
# MAGIC - SPARK (1DTE): paper only
# MAGIC - INFERNO (0DTE): paper only
# MAGIC
# MAGIC **IMPORTANT**: Make sure the scanner has the MTM spread_width cap fix
# MAGIC before running this, otherwise the new positions will get false-SL'd.

# COMMAND ----------

# ── CONFIGURATION ──────────────────────────────────────────────────────────

EXECUTE = False           # True = open trades, False = dry run (show what would open)
BOT_FILTER = None         # None = all bots, or "flame", "spark", "inferno"

# ── Credentials ──
import os

def _set_if_missing(key: str, fallback: str) -> None:
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

# COMMAND ----------

import math
import json
import random
import time
import logging
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Optional

CT = ZoneInfo("America/Chicago")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("force_trade")

CATALOG = os.environ.get("DATABRICKS_CATALOG", "alpha_prime")
SCHEMA = os.environ.get("DATABRICKS_SCHEMA", "ironforge")
TRADIER_API_KEY = os.environ.get("TRADIER_API_KEY", "")
TRADIER_URL = "https://api.tradier.com/v1"
SANDBOX_URL = "https://sandbox.tradier.com/v1"

spark.sql("SET TIME ZONE 'America/Chicago'")

BOT_CONFIG = {
    "flame":   {"sd": 1.2, "min_dte": 2, "dte": "2DTE", "max_contracts": 10},
    "spark":   {"sd": 1.2, "min_dte": 1, "dte": "1DTE", "max_contracts": 10},
    "inferno": {"sd": 1.0, "min_dte": 0, "dte": "0DTE", "max_contracts": 10},
}

SANDBOX_ACCOUNTS = [
    {"name": "User",  "api_key": os.environ.get("TRADIER_SANDBOX_KEY_USER", ""),
     "account_id": os.environ.get("TRADIER_SANDBOX_ACCOUNT_ID_USER", "")},
    {"name": "Matt",  "api_key": os.environ.get("TRADIER_SANDBOX_KEY_MATT", ""),
     "account_id": os.environ.get("TRADIER_SANDBOX_ACCOUNT_ID_MATT", "")},
    {"name": "Logan", "api_key": os.environ.get("TRADIER_SANDBOX_KEY_LOGAN", ""),
     "account_id": os.environ.get("TRADIER_SANDBOX_ACCOUNT_ID_LOGAN", "")},
]

# COMMAND ----------

# ── Helpers ────────────────────────────────────────────────────────────────

def bot_table(bot: str, table: str) -> str:
    return f"{CATALOG}.{SCHEMA}.{bot}_{table}"

def shared_table(table: str) -> str:
    return f"{CATALOG}.{SCHEMA}.{table}"

def db_query(sql: str) -> list:
    result = spark.sql(sql)
    rows = result.collect()
    if not rows:
        return []
    return [dict(zip(result.columns, row)) for row in rows]

def db_execute(sql: str):
    spark.sql(sql)

def num(val) -> float:
    if val is None or val == "":
        return 0.0
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0

def tradier_get(endpoint: str, params: dict = None) -> Optional[dict]:
    headers = {"Authorization": f"Bearer {TRADIER_API_KEY}", "Accept": "application/json"}
    try:
        resp = requests.get(f"{TRADIER_URL}{endpoint}", headers=headers, params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        log.error(f"Tradier GET {endpoint}: {e}")
        return None

def sandbox_post(api_key: str, endpoint: str, data: dict) -> Optional[dict]:
    headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
    try:
        resp = requests.post(f"{SANDBOX_URL}{endpoint}", headers=headers, data=data, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.HTTPError as e:
        body = e.response.text if e.response else ""
        log.error(f"Sandbox POST {endpoint}: {e} — {body}")
        return None
    except Exception as e:
        log.error(f"Sandbox POST {endpoint}: {e}")
        return None

def get_sandbox_buying_power(api_key: str, account_id: str) -> float:
    headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
    try:
        resp = requests.get(f"{SANDBOX_URL}/accounts/{account_id}/balances", headers=headers, timeout=10)
        resp.raise_for_status()
        bal = resp.json().get("balances", {})
        return float(bal.get("option_buying_power", bal.get("buying_power", 0)))
    except Exception:
        return 0.0

def get_sandbox_fill_price(api_key: str, account_id: str, order_id: int, max_wait: int = 45) -> Optional[float]:
    """Poll sandbox order for fill price."""
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
                # Try leg fills
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

def build_occ(ticker: str, expiration: str, strike: float, opt_type: str) -> str:
    d = datetime.strptime(expiration, "%Y-%m-%d")
    yy = d.strftime("%y")
    mm = d.strftime("%m")
    dd = d.strftime("%d")
    strike_part = str(round(strike * 1000)).zfill(8)
    return f"{ticker}{yy}{mm}{dd}{opt_type}{strike_part}"

# COMMAND ----------

# ── Signal generation ─────────────────────────────────────────────────────

def get_quote(symbol: str) -> Optional[dict]:
    data = tradier_get("/markets/quotes", {"symbols": symbol})
    if not data:
        return None
    quote = data.get("quotes", {}).get("quote")
    if isinstance(quote, list):
        quote = quote[0]
    if not quote or quote.get("last") is None:
        return None
    return {"last": float(quote["last"]), "bid": float(quote.get("bid", 0)), "ask": float(quote.get("ask", 0))}

def get_option_quote(occ: str) -> Optional[dict]:
    data = tradier_get("/markets/quotes", {"symbols": occ})
    if not data:
        return None
    quote = data.get("quotes", {}).get("quote")
    if isinstance(quote, list):
        quote = quote[0]
    if not quote or quote.get("bid") is None:
        return None
    if data.get("quotes", {}).get("unmatched_symbols"):
        return None
    return {"bid": float(quote["bid"]), "ask": float(quote.get("ask", 0)), "last": float(quote.get("last", 0))}

def get_expirations(symbol: str) -> list:
    data = tradier_get("/markets/options/expirations", {"symbol": symbol, "includeAllRoots": "true"})
    if not data:
        return []
    dates = data.get("expirations", {}).get("date")
    if not dates:
        return []
    if isinstance(dates, str):
        return [dates]
    return list(dates)

def get_target_expiration(min_dte: int) -> str:
    ct = datetime.now(CT)
    target = ct + timedelta(days=min_dte)
    # Skip weekends
    while target.weekday() >= 5:
        target += timedelta(days=1)
    return target.strftime("%Y-%m-%d")

def calculate_strikes(spot: float, expected_move: float, sd_mult: float) -> dict:
    offset = expected_move * sd_mult
    spread_width = 5.0
    put_short = round((spot - offset) / spread_width) * spread_width
    put_long = put_short - spread_width
    call_short = round((spot + offset) / spread_width) * spread_width
    call_long = call_short + spread_width
    return {
        "putShort": put_short, "putLong": put_long,
        "callShort": call_short, "callLong": call_long,
    }

# COMMAND ----------

# ── Force trade logic ─────────────────────────────────────────────────────

def force_trade_for_bot(bot_name: str, execute: bool) -> str:
    cfg = BOT_CONFIG[bot_name]
    dte = cfg["dte"]

    print(f"\n{'─' * 60}")
    print(f"  {bot_name.upper()} ({dte})")
    print(f"{'─' * 60}")

    # Check for existing open position
    open_rows = db_query(f"""
        SELECT position_id FROM {bot_table(bot_name, 'positions')}
        WHERE status = 'open' AND dte_mode = '{dte}'
    """)
    if open_rows:
        print(f"  Already has {len(open_rows)} open position(s) — skipping")
        return "skip:has_open_position"

    # Get paper account
    acct_rows = db_query(f"""
        SELECT id, current_balance, buying_power
        FROM {bot_table(bot_name, 'paper_account')}
        WHERE is_active = TRUE AND dte_mode = '{dte}'
        ORDER BY id DESC LIMIT 1
    """)
    if not acct_rows:
        print(f"  No paper account found — skipping")
        return "skip:no_account"

    acct = acct_rows[0]
    paper_acct_id = acct["id"]
    buying_power = num(acct["buying_power"])
    print(f"  Balance: ${num(acct['current_balance']):,.2f}  BP: ${buying_power:,.2f}")

    if buying_power < 200:
        print(f"  Buying power too low (${buying_power:.0f}) — skipping")
        return f"skip:low_bp(${buying_power:.0f})"

    # Get market data
    spy = get_quote("SPY")
    vix_q = get_quote("VIX")
    if not spy or not vix_q:
        print(f"  Cannot get SPY/VIX quotes — skipping")
        return "skip:no_quotes"

    spot = spy["last"]
    vix = vix_q["last"]
    print(f"  SPY: ${spot:.2f}  VIX: {vix:.1f}")

    if vix > 32:
        print(f"  VIX too high ({vix:.1f}) — skipping")
        return f"skip:vix({vix:.1f})"

    # Calculate strikes
    expected_move = (vix / 100 / math.sqrt(252)) * spot
    strikes = calculate_strikes(spot, expected_move, sd_mult=cfg["sd"])
    spread_width = strikes["putShort"] - strikes["putLong"]

    # Find expiration
    target_exp = get_target_expiration(cfg["min_dte"])
    expirations = get_expirations("SPY")
    expiration = target_exp
    if expirations and target_exp not in expirations:
        from datetime import datetime as dt
        target_date = dt.strptime(target_exp, "%Y-%m-%d")
        nearest = expirations[0]
        min_diff = float("inf")
        for exp in expirations:
            diff = abs((dt.strptime(exp, "%Y-%m-%d") - target_date).total_seconds())
            if diff < min_diff:
                min_diff = diff
                nearest = exp
        expiration = nearest

    print(f"  Strikes: {strikes['putLong']}/{strikes['putShort']}P — {strikes['callShort']}/{strikes['callLong']}C")
    print(f"  Expiration: {expiration}  Spread: ${spread_width}")

    # Get entry credit (conservative: sell at bid, buy at ask)
    occ_ps = build_occ("SPY", expiration, strikes["putShort"], "P")
    occ_pl = build_occ("SPY", expiration, strikes["putLong"], "P")
    occ_cs = build_occ("SPY", expiration, strikes["callShort"], "C")
    occ_cl = build_occ("SPY", expiration, strikes["callLong"], "C")

    ps_q = get_option_quote(occ_ps)
    pl_q = get_option_quote(occ_pl)
    cs_q = get_option_quote(occ_cs)
    cl_q = get_option_quote(occ_cl)

    if not all([ps_q, pl_q, cs_q, cl_q]):
        print(f"  Cannot get option quotes — skipping")
        return "skip:no_option_quotes"

    put_credit = ps_q["bid"] - pl_q["ask"]
    call_credit = cs_q["bid"] - cl_q["ask"]

    if put_credit <= 0 or call_credit <= 0:
        ps_mid = (ps_q["bid"] + ps_q["ask"]) / 2
        pl_mid = (pl_q["bid"] + pl_q["ask"]) / 2
        cs_mid = (cs_q["bid"] + cs_q["ask"]) / 2
        cl_mid = (cl_q["bid"] + cl_q["ask"]) / 2
        put_credit = max(0, ps_mid - pl_mid)
        call_credit = max(0, cs_mid - cl_mid)

    total_credit = round(put_credit + call_credit, 4)
    print(f"  Credit: ${total_credit:.4f} (put=${put_credit:.4f} call=${call_credit:.4f})")

    if total_credit < 0.05:
        print(f"  Credit too low — skipping")
        return f"skip:credit_too_low(${total_credit:.4f})"

    # Size the trade
    collateral_per = max(0, (spread_width - total_credit) * 100)
    usable_bp = buying_power * 0.85
    max_contracts = min(cfg["max_contracts"], max(1, math.floor(usable_bp / collateral_per))) if collateral_per > 0 else 1
    total_collateral = collateral_per * max_contracts
    max_profit = total_credit * 100 * max_contracts
    max_loss = total_collateral

    print(f"  Contracts: {max_contracts}  Collateral: ${total_collateral:,.2f}")

    if not execute:
        print(f"  [DRY RUN] Would open {bot_name.upper()} IC position")
        return "dry_run"

    # Generate position ID
    now = datetime.now(CT)
    date_str = now.strftime("%Y%m%d")
    hex_str = format(random.randint(0, 0xFFFFFF), "06X")
    position_id = f"{bot_name.upper()}-{date_str}-{hex_str}"
    now_ts = now.strftime("%Y-%m-%d %H:%M:%S")
    today_date = now.strftime("%Y-%m-%d")

    actual_credit = total_credit
    sandbox_order_ids = {}

    # ── FLAME: Mirror to Tradier sandbox ──
    if bot_name == "flame":
        print(f"\n  Sandbox mirroring (FLAME 1:1):")
        for i, acct in enumerate(SANDBOX_ACCOUNTS):
            if not acct["api_key"] or not acct["account_id"]:
                continue
            try:
                sb_bp = get_sandbox_buying_power(acct["api_key"], acct["account_id"])
                if sb_bp < collateral_per:
                    print(f"    [{acct['name']}] BP=${sb_bp:,.0f} too low, skipping")
                    continue

                sb_usable = sb_bp * 0.85
                sb_contracts = min(500, max(1, math.floor(sb_usable / collateral_per)))
                print(f"    [{acct['name']}] BP=${sb_bp:,.0f} → {sb_contracts} contracts")

                order_body = {
                    "class": "multileg",
                    "symbol": "SPY",
                    "type": "market",
                    "duration": "day",
                    "option_symbol[0]": occ_ps, "side[0]": "sell_to_open", "quantity[0]": str(sb_contracts),
                    "option_symbol[1]": occ_pl, "side[1]": "buy_to_open",  "quantity[1]": str(sb_contracts),
                    "option_symbol[2]": occ_cs, "side[2]": "sell_to_open", "quantity[2]": str(sb_contracts),
                    "option_symbol[3]": occ_cl, "side[3]": "buy_to_open",  "quantity[3]": str(sb_contracts),
                    "tag": position_id[:255],
                }
                result = sandbox_post(acct["api_key"], f"/accounts/{acct['account_id']}/orders", order_body)

                if result and result.get("order", {}).get("id"):
                    oid = result["order"]["id"]
                    sandbox_order_ids[acct["name"]] = {"order_id": oid, "contracts": sb_contracts}
                    print(f"    [{acct['name']}] Order #{oid} submitted")

                    # For User account, wait for fill to get 1:1 price
                    if acct["name"] == "User":
                        fill = get_sandbox_fill_price(acct["api_key"], acct["account_id"], oid)
                        if fill and fill > 0:
                            actual_credit = fill
                            print(f"    [{acct['name']}] FILLED @ ${fill:.4f} (using as paper credit)")
                        else:
                            print(f"    [{acct['name']}] Fill not available, using calculated credit")
                else:
                    print(f"    [{acct['name']}] Order FAILED")
            except Exception as e:
                print(f"    [{acct['name']}] Error: {e}")

        if not sandbox_order_ids.get("User"):
            print(f"  WARNING: User sandbox didn't fill, but proceeding with paper position anyway (force trade)")

    # ── Recalculate with actual credit ──
    total_collateral = max(0, (spread_width - actual_credit) * 100) * max_contracts
    max_profit = actual_credit * 100 * max_contracts
    max_loss = total_collateral

    # ── Insert position ──
    sandbox_json = json.dumps(sandbox_order_ids).replace("'", "''") if sandbox_order_ids else ""

    db_execute(f"""
        INSERT INTO {bot_table(bot_name, 'positions')} (
            position_id, ticker, expiration,
            put_short_strike, put_long_strike, put_credit,
            call_short_strike, call_long_strike, call_credit,
            contracts, spread_width, total_credit, max_loss, max_profit,
            collateral_required,
            underlying_at_entry, vix_at_entry, expected_move,
            call_wall, put_wall, gex_regime, flip_point, net_gex,
            oracle_confidence, oracle_win_probability, oracle_advice,
            oracle_reasoning, oracle_top_factors, oracle_use_gex_walls,
            wings_adjusted, original_put_width, original_call_width,
            put_order_id, call_order_id,
            status, open_time, open_date, dte_mode,
            {('sandbox_order_id, ' if sandbox_json else '')}created_at, updated_at
        ) VALUES (
            '{position_id}', 'SPY', CAST('{expiration}' AS DATE),
            {strikes['putShort']}, {strikes['putLong']}, {round(put_credit, 4)},
            {strikes['callShort']}, {strikes['callLong']}, {round(call_credit, 4)},
            {max_contracts}, {spread_width}, {actual_credit}, {max_loss}, {max_profit},
            {total_collateral},
            {spot}, {vix}, {expected_move},
            0, 0, 'UNKNOWN', 0, 0,
            0.5, 0.5, 'FORCE_TRADE',
            'Forced trade via force_open_trades script', '[]', FALSE,
            FALSE, {spread_width}, {spread_width},
            'PAPER', 'PAPER',
            'open', CAST('{now_ts}' AS TIMESTAMP), CAST('{today_date}' AS DATE), '{dte}',
            {(f"'{sandbox_json}', " if sandbox_json else '')}CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP()
        )
    """)

    # ── Update paper account ──
    db_execute(f"""
        UPDATE {bot_table(bot_name, 'paper_account')}
        SET collateral_in_use = collateral_in_use + {total_collateral},
            buying_power = buying_power - {total_collateral},
            updated_at = CURRENT_TIMESTAMP()
        WHERE id = {paper_acct_id}
    """)

    # ── PDT log ──
    db_execute(f"""
        INSERT INTO {bot_table(bot_name, 'pdt_log')}
            (position_id, trade_date, entry_credit, contracts, dte_mode, opened_at)
        VALUES ('{position_id}', CURRENT_DATE(), {actual_credit}, {max_contracts},
                '{dte}', CURRENT_TIMESTAMP())
    """)

    # ── Signal log ──
    db_execute(f"""
        INSERT INTO {bot_table(bot_name, 'signals')}
            (signal_time, spot_price, vix, expected_move, call_wall, put_wall,
             gex_regime, put_short, put_long, call_short, call_long,
             total_credit, confidence, was_executed, reasoning, wings_adjusted, dte_mode)
        VALUES (CURRENT_TIMESTAMP(), {spot}, {vix}, {expected_move}, 0, 0,
                'UNKNOWN', {strikes['putShort']}, {strikes['putLong']},
                {strikes['callShort']}, {strikes['callLong']},
                {actual_credit}, 0.5, TRUE, 'force_trade_script', FALSE, '{dte}')
    """)

    # ── Activity log ──
    details = json.dumps({
        "position_id": position_id,
        "strikes": strikes,
        "credit": actual_credit,
        "contracts": max_contracts,
        "collateral": total_collateral,
        "expiration": expiration,
        "source": "force_open_trades",
        "sandbox": sandbox_order_ids,
    }).replace("'", "''")
    db_execute(f"""
        INSERT INTO {bot_table(bot_name, 'logs')} (level, message, details, dte_mode)
        VALUES ('TRADE_OPEN',
                'FORCE TRADE: {position_id} {strikes["putLong"]}/{strikes["putShort"]}P-{strikes["callShort"]}/{strikes["callLong"]}C x{max_contracts} @ ${actual_credit:.4f}',
                '{details}', '{dte}')
    """)

    # ── Daily perf ──
    db_execute(f"""
        MERGE INTO {bot_table(bot_name, 'daily_perf')} AS t
        USING (SELECT CURRENT_DATE() AS trade_date) AS s
        ON t.trade_date = s.trade_date
        WHEN MATCHED THEN UPDATE SET t.trades_executed = t.trades_executed + 1
        WHEN NOT MATCHED THEN INSERT (trade_date, trades_executed, positions_closed, realized_pnl)
            VALUES (CURRENT_DATE(), 1, 0, 0)
    """)

    print(f"\n  ✓ OPENED: {position_id}")
    print(f"    {strikes['putLong']}/{strikes['putShort']}P — {strikes['callShort']}/{strikes['callLong']}C")
    print(f"    x{max_contracts} @ ${actual_credit:.4f}  Exp: {expiration}")
    print(f"    Collateral: ${total_collateral:,.2f}")
    if sandbox_order_ids:
        for name, info in sandbox_order_ids.items():
            print(f"    Sandbox [{name}]: order #{info['order_id']} x{info['contracts']}")

    return f"traded:{position_id}"

# COMMAND ----------

# ── MAIN ──────────────────────────────────────────────────────────────────

print("=" * 60)
print(f"  Force Open Trades — {'EXECUTE' if EXECUTE else 'DRY RUN'}")
print(f"  Time: {datetime.now(CT).strftime('%Y-%m-%d %H:%M:%S CT')}")
print("=" * 60)

bots = ["flame", "spark", "inferno"]
if BOT_FILTER:
    bots = [BOT_FILTER]

results = {}
for bot_name in bots:
    try:
        result = force_trade_for_bot(bot_name, EXECUTE)
        results[bot_name] = result
    except Exception as e:
        print(f"\n  ERROR for {bot_name.upper()}: {e}")
        results[bot_name] = f"error:{e}"

print(f"\n{'=' * 60}")
print("  SUMMARY")
for bot_name, result in results.items():
    status = "✓" if result.startswith("traded:") else "○" if result == "dry_run" else "✗"
    print(f"  {status} {bot_name.upper()}: {result}")
print("=" * 60)
