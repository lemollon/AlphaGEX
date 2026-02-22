# Databricks notebook source
# MAGIC %md
# MAGIC # FLAME - 2DTE Iron Condor Bot
# MAGIC **Self-contained paper trading bot. Schedule this notebook to run every 5 minutes during market hours.**
# MAGIC
# MAGIC | Setting | Value |
# MAGIC |---------|-------|
# MAGIC | Strategy | Iron Condor (SPY) |
# MAGIC | DTE | 2 days to expiration |
# MAGIC | Capital | $5,000 paper |
# MAGIC | Profit Target | 30% of credit |
# MAGIC | Stop Loss | 100% of credit |
# MAGIC | Max Trades | 1 per day |
# MAGIC | Schedule | Every 5 min, Mon-Fri, 8:30 AM - 2:45 PM CT |

# COMMAND ----------

# MAGIC %md
# MAGIC ## Configuration

# COMMAND ----------

# CHANGE THIS: Your Tradier production API key
TRADIER_API_KEY = dbutils.widgets.get("tradier_api_key") if "tradier_api_key" in [w.name for w in dbutils.widgets.getAll()] else ""

# If not set via widget, try secrets
if not TRADIER_API_KEY:
    try:
        TRADIER_API_KEY = dbutils.secrets.get("ironforge", "tradier-api-key")
    except Exception:
        pass

# Bot config
BOT_NAME = "FLAME"
DTE_MODE = "2DTE"
MIN_DTE = 2
CATALOG = "alpha_prime"
SCHEMA = "default"
TICKER = "SPY"
STARTING_CAPITAL = 5000.0
SD_MULTIPLIER = 1.2
SPREAD_WIDTH = 5.0
MIN_CREDIT = 0.05
MAX_TRADES_PER_DAY = 1
PROFIT_TARGET_PCT = 30.0
STOP_LOSS_PCT = 100.0
EOD_CUTOFF_ET = "15:45"
ENTRY_START_CT = "08:30"
ENTRY_END_CT = "14:00"
VIX_SKIP = 32.0
PDT_MAX_DAY_TRADES = 3
MAX_CONTRACTS = 10
BUYING_POWER_USAGE_PCT = 0.85
MAX_CONSECUTIVE_MTM_FAILURES = 10

# COMMAND ----------

# MAGIC %md
# MAGIC ## Install dependencies

# COMMAND ----------

# MAGIC %pip install requests -q

# COMMAND ----------

import json
import math
import uuid
import logging
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass
from enum import Enum

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s %(message)s")
logger = logging.getLogger(BOT_NAME)

CENTRAL_TZ = ZoneInfo("America/Chicago")
EASTERN_TZ = ZoneInfo("America/New_York")

def _t(table_name):
    """Fully qualified table name."""
    return f"{CATALOG}.{SCHEMA}.{table_name}"

def _bot_table(suffix):
    """Bot-specific table name."""
    return _t(f"{BOT_NAME.lower()}_{suffix}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Tradier API Client

# COMMAND ----------

class TradierClient:
    """Minimal Tradier API client for option quotes and chain data."""

    def __init__(self, api_key: str):
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        })
        self.base_url = "https://api.tradier.com/v1"

    def _get(self, endpoint, params=None):
        try:
            resp = self.session.get(f"{self.base_url}{endpoint}", params=params, timeout=10)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning(f"Tradier API error: {e}")
            return None

    def get_quote(self, symbol):
        data = self._get("/markets/quotes", {"symbols": symbol})
        if not data:
            return None
        quotes = data.get("quotes", {}).get("quote", {})
        if isinstance(quotes, list):
            quotes = quotes[0] if quotes else {}
        return quotes

    def get_vix(self):
        quote = self.get_quote("VIX")
        if quote:
            return float(quote.get("last", 0)) or None
        return None

    def get_option_expirations(self, symbol):
        data = self._get("/markets/options/expirations", {"symbol": symbol})
        if not data:
            return None
        expirations = data.get("expirations", {}).get("date", [])
        if isinstance(expirations, str):
            return [expirations]
        return expirations

    def get_option_chain(self, symbol, expiration):
        data = self._get("/markets/options/chains", {
            "symbol": symbol, "expiration": expiration, "greeks": "false",
        })
        if not data:
            return None
        options = data.get("options", {}).get("option", [])
        if isinstance(options, dict):
            return [options]
        return options

    def get_option_quote(self, occ_symbol):
        data = self._get("/markets/quotes", {"symbols": occ_symbol})
        if not data:
            return None
        quotes = data.get("quotes", {}).get("quote", {})
        if isinstance(quotes, list):
            quotes = quotes[0] if quotes else {}
        if quotes and quotes.get("bid") is not None:
            return quotes
        unmatched = data.get("quotes", {}).get("unmatched_symbols", {})
        if unmatched:
            return None
        return quotes

# COMMAND ----------

# MAGIC %md
# MAGIC ## Database Operations

# COMMAND ----------

def db_get_paper_account():
    """Get paper account from Delta Lake."""
    rows = spark.sql(f"""
        SELECT starting_capital, current_balance, cumulative_pnl,
               total_trades, collateral_in_use, buying_power,
               high_water_mark, max_drawdown, is_active
        FROM {_bot_table('paper_account')}
        WHERE is_active = TRUE AND dte_mode = '{DTE_MODE}'
        ORDER BY id DESC LIMIT 1
    """).collect()
    if rows:
        r = rows[0]
        return {
            "starting_balance": float(r.starting_capital),
            "balance": float(r.current_balance),
            "cumulative_pnl": float(r.cumulative_pnl),
            "total_trades": int(r.total_trades),
            "collateral_in_use": float(r.collateral_in_use),
            "buying_power": float(r.buying_power),
            "high_water_mark": float(r.high_water_mark),
            "max_drawdown": float(r.max_drawdown),
            "is_active": bool(r.is_active),
        }
    return {
        "starting_balance": STARTING_CAPITAL, "balance": STARTING_CAPITAL,
        "cumulative_pnl": 0, "total_trades": 0, "collateral_in_use": 0,
        "buying_power": STARTING_CAPITAL, "high_water_mark": STARTING_CAPITAL,
        "max_drawdown": 0, "is_active": True,
    }


def db_update_paper_balance(realized_pnl=0, collateral_change=0):
    """Update paper account balance."""
    rows = spark.sql(f"""
        SELECT id, current_balance, cumulative_pnl, total_trades,
               collateral_in_use, high_water_mark, max_drawdown
        FROM {_bot_table('paper_account')}
        WHERE is_active = TRUE AND dte_mode = '{DTE_MODE}'
        ORDER BY id DESC LIMIT 1
    """).collect()
    if not rows:
        return False

    r = rows[0]
    account_id = r.id
    new_balance = float(r.current_balance) + realized_pnl
    new_cum_pnl = float(r.cumulative_pnl) + realized_pnl
    new_collateral = max(0, float(r.collateral_in_use) + collateral_change)
    new_bp = new_balance - new_collateral
    new_trades = int(r.total_trades) + (1 if realized_pnl != 0 else 0)
    new_hwm = max(float(r.high_water_mark), new_balance)
    new_max_dd = max(float(r.max_drawdown), new_hwm - new_balance)

    spark.sql(f"""
        UPDATE {_bot_table('paper_account')}
        SET current_balance = {new_balance},
            cumulative_pnl = {new_cum_pnl},
            total_trades = {new_trades},
            collateral_in_use = {new_collateral},
            buying_power = {new_bp},
            high_water_mark = {new_hwm},
            max_drawdown = {new_max_dd},
            updated_at = CURRENT_TIMESTAMP()
        WHERE id = {account_id}
    """)
    return True


def db_get_open_positions():
    """Get all open positions."""
    rows = spark.sql(f"""
        SELECT position_id, ticker, expiration,
               put_short_strike, put_long_strike, put_credit,
               call_short_strike, call_long_strike, call_credit,
               contracts, spread_width, total_credit, max_loss, max_profit,
               underlying_at_entry, vix_at_entry, expected_move,
               status, open_time, close_time, close_price, close_reason,
               realized_pnl, collateral_required
        FROM {_bot_table('positions')}
        WHERE status = 'open' AND dte_mode = '{DTE_MODE}'
        ORDER BY open_time DESC
    """).collect()
    return [r.asDict() for r in rows]


def db_save_position(pos):
    """Save a new position to Delta Lake."""
    spark.sql(f"""
        INSERT INTO {_bot_table('positions')} (
            position_id, ticker, expiration,
            put_short_strike, put_long_strike, put_credit,
            call_short_strike, call_long_strike, call_credit,
            contracts, spread_width, total_credit, max_loss, max_profit,
            collateral_required, underlying_at_entry, vix_at_entry, expected_move,
            wings_adjusted, status, open_time, open_date, dte_mode
        ) VALUES (
            '{pos["position_id"]}', '{pos["ticker"]}', '{pos["expiration"]}',
            {pos["put_short"]}, {pos["put_long"]}, {pos["put_credit"]},
            {pos["call_short"]}, {pos["call_long"]}, {pos["call_credit"]},
            {pos["contracts"]}, {pos["spread_width"]}, {pos["total_credit"]},
            {pos["max_loss"]}, {pos["max_profit"]}, {pos["collateral"]},
            {pos["spot_price"]}, {pos["vix"]}, {pos["expected_move"]},
            {pos["wings_adjusted"]}, 'open',
            CURRENT_TIMESTAMP(), CURRENT_DATE(), '{DTE_MODE}'
        )
    """)


def db_close_position(position_id, close_price, realized_pnl, close_reason):
    """Close a position."""
    spark.sql(f"""
        UPDATE {_bot_table('positions')}
        SET status = 'closed',
            close_time = CURRENT_TIMESTAMP(),
            close_price = {close_price},
            realized_pnl = {realized_pnl},
            close_reason = '{close_reason}',
            updated_at = CURRENT_TIMESTAMP()
        WHERE position_id = '{position_id}' AND status = 'open' AND dte_mode = '{DTE_MODE}'
    """)


def db_has_traded_today(date_str):
    """Check if bot already traded today."""
    rows = spark.sql(f"""
        SELECT COUNT(*) as cnt
        FROM {_bot_table('positions')}
        WHERE CAST(open_time AS DATE) = '{date_str}' AND dte_mode = '{DTE_MODE}'
    """).collect()
    return rows[0].cnt > 0 if rows else False


def db_get_day_trade_count_rolling_5():
    """Get PDT day trade count for rolling 5 business days."""
    rows = spark.sql(f"""
        SELECT COUNT(*) as cnt
        FROM {_bot_table('pdt_log')}
        WHERE is_day_trade = TRUE
        AND dte_mode = '{DTE_MODE}'
        AND trade_date >= DATE_SUB(CURRENT_DATE(), 8)
        AND DAYOFWEEK(trade_date) BETWEEN 2 AND 6
    """).collect()
    return rows[0].cnt if rows else 0


def db_log_pdt_entry(position_id, symbol, opened_at, contracts, entry_credit):
    """Log a PDT entry."""
    spark.sql(f"""
        INSERT INTO {_bot_table('pdt_log')}
        (trade_date, symbol, position_id, opened_at, contracts, entry_credit, dte_mode)
        VALUES (CURRENT_DATE(), '{symbol}', '{position_id}',
                CURRENT_TIMESTAMP(), {contracts}, {entry_credit}, '{DTE_MODE}')
    """)


def db_update_pdt_close(position_id, exit_cost, pnl, close_reason):
    """Update PDT log on position close."""
    rows = spark.sql(f"""
        SELECT opened_at FROM {_bot_table('pdt_log')}
        WHERE position_id = '{position_id}' AND dte_mode = '{DTE_MODE}'
        LIMIT 1
    """).collect()
    is_day_trade = False
    if rows and rows[0].opened_at:
        opened_date = str(rows[0].opened_at.date())
        closed_date = str(datetime.now(CENTRAL_TZ).date())
        is_day_trade = opened_date == closed_date

    spark.sql(f"""
        UPDATE {_bot_table('pdt_log')}
        SET closed_at = CURRENT_TIMESTAMP(),
            exit_cost = {exit_cost},
            pnl = {pnl},
            close_reason = '{close_reason}',
            is_day_trade = {str(is_day_trade).lower()}
        WHERE position_id = '{position_id}' AND dte_mode = '{DTE_MODE}'
    """)


def db_log(level, message, details=None):
    """Write a log entry."""
    details_str = json.dumps(details).replace("'", "''") if details else ""
    msg_safe = message.replace("'", "''")
    spark.sql(f"""
        INSERT INTO {_bot_table('logs')} (level, message, details, dte_mode)
        VALUES ('{level}', '{msg_safe}', '{details_str}', '{DTE_MODE}')
    """)


def db_log_signal(spot_price, vix, expected_move, put_short, put_long,
                  call_short, call_long, total_credit, confidence,
                  was_executed, skip_reason=None, reasoning=None, wings_adjusted=False):
    """Log a signal to the signals table."""
    skip_str = f"'{skip_reason}'" if skip_reason else "NULL"
    reason_str = f"'{reasoning.replace(chr(39), chr(39)+chr(39))}'" if reasoning else "NULL"
    spark.sql(f"""
        INSERT INTO {_bot_table('signals')} (
            spot_price, vix, expected_move, put_short, put_long,
            call_short, call_long, total_credit, confidence,
            was_executed, skip_reason, reasoning, wings_adjusted, dte_mode
        ) VALUES (
            {spot_price}, {vix}, {expected_move}, {put_short}, {put_long},
            {call_short}, {call_long}, {total_credit}, {confidence},
            {str(was_executed).lower()}, {skip_str}, {reason_str},
            {str(wings_adjusted).lower()}, '{DTE_MODE}'
        )
    """)


def db_save_equity_snapshot(balance, realized_pnl=0, unrealized_pnl=0, open_positions=0, note=""):
    """Save an equity snapshot."""
    note_safe = note.replace("'", "''")
    spark.sql(f"""
        INSERT INTO {_bot_table('equity_snapshots')}
        (balance, realized_pnl, unrealized_pnl, open_positions, note, dte_mode)
        VALUES ({balance}, {realized_pnl}, {unrealized_pnl}, {open_positions}, '{note_safe}', '{DTE_MODE}')
    """)


def db_update_heartbeat(status, action):
    """Update the heartbeat table."""
    details = json.dumps({"last_action": action}).replace("'", "''")
    spark.sql(f"""
        MERGE INTO {_t('bot_heartbeats')} AS t
        USING (SELECT '{BOT_NAME}' AS bot_name) AS s
        ON t.bot_name = s.bot_name
        WHEN MATCHED THEN UPDATE SET
            last_heartbeat = CURRENT_TIMESTAMP(),
            status = '{status}',
            scan_count = t.scan_count + 1,
            details = '{details}'
        WHEN NOT MATCHED THEN INSERT (bot_name, last_heartbeat, status, scan_count, details)
            VALUES ('{BOT_NAME}', CURRENT_TIMESTAMP(), '{status}', 1, '{details}')
    """)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Signal Generator

# COMMAND ----------

def get_market_data(tradier):
    """Get current market data."""
    quote = tradier.get_quote(TICKER)
    if not quote or not quote.get("last"):
        return None
    spot = float(quote["last"])
    vix = 20.0
    fetched_vix = tradier.get_vix()
    if fetched_vix and fetched_vix >= 10:
        vix = fetched_vix
    expected_move = (vix / 100 / (252 ** 0.5)) * spot
    return {"spot_price": spot, "vix": vix, "expected_move": expected_move}


def get_target_expiration(now):
    """Get target expiration MIN_DTE trading days out."""
    target = now
    trading_days = 0
    while trading_days < MIN_DTE:
        target += timedelta(days=1)
        if target.weekday() < 5:
            trading_days += 1
    return target.strftime("%Y-%m-%d")


def validate_expiration(tradier, target_exp):
    """Validate expiration exists in option chain."""
    expirations = tradier.get_option_expirations(TICKER)
    if not expirations:
        return target_exp
    if target_exp in expirations:
        return target_exp
    target_date = datetime.strptime(target_exp, "%Y-%m-%d")
    nearest = None
    min_diff = float("inf")
    for exp_str in expirations:
        try:
            exp_date = datetime.strptime(exp_str, "%Y-%m-%d")
            diff = abs((exp_date - target_date).days)
            if diff < min_diff and exp_date >= datetime.now():
                min_diff = diff
                nearest = exp_str
        except (ValueError, TypeError):
            continue
    return nearest


def calculate_strikes(spot, expected_move):
    """Calculate IC strikes."""
    sd = max(SD_MULTIPLIER, 1.2)
    min_em = spot * 0.005
    em = max(expected_move, min_em)
    put_short = math.floor(spot - sd * em)
    call_short = math.ceil(spot + sd * em)
    put_long = put_short - SPREAD_WIDTH
    call_long = call_short + SPREAD_WIDTH
    if call_short <= put_short:
        put_short = math.floor(spot - spot * 0.02)
        call_short = math.ceil(spot + spot * 0.02)
        put_long = put_short - SPREAD_WIDTH
        call_long = call_short + SPREAD_WIDTH
    return put_short, put_long, call_short, call_long


def enforce_symmetric_wings(ps, pl, cs, cl):
    """Ensure put and call spread widths match."""
    put_w = ps - pl
    call_w = cl - cs
    if abs(put_w - call_w) < 0.01:
        return ps, pl, cs, cl, False
    target = max(put_w, call_w)
    adjusted = False
    if put_w < target:
        pl = ps - target
        adjusted = True
    elif call_w < target:
        cl = cs + target
        adjusted = True
    return ps, pl, cs, cl, adjusted


def get_real_credits(tradier, expiration, ps, pl, cs, cl):
    """Get real option credits from Tradier."""
    try:
        exp_date = datetime.strptime(expiration, "%Y-%m-%d")
        exp_str = exp_date.strftime("%y%m%d")

        def sym(strike, opt_type):
            return f"SPY{exp_str}{opt_type}{int(strike * 1000):08d}"

        ps_q = tradier.get_option_quote(sym(ps, "P"))
        pl_q = tradier.get_option_quote(sym(pl, "P"))
        cs_q = tradier.get_option_quote(sym(cs, "C"))
        cl_q = tradier.get_option_quote(sym(cl, "C"))

        if not all([ps_q, pl_q, cs_q, cl_q]):
            return None

        put_credit = float(ps_q.get("bid", 0) or 0) - float(pl_q.get("ask", 0) or 0)
        call_credit = float(cs_q.get("bid", 0) or 0) - float(cl_q.get("ask", 0) or 0)

        if put_credit <= 0 or call_credit <= 0:
            ps_mid = (float(ps_q.get("bid", 0) or 0) + float(ps_q.get("ask", 0) or 0)) / 2
            pl_mid = (float(pl_q.get("bid", 0) or 0) + float(pl_q.get("ask", 0) or 0)) / 2
            cs_mid = (float(cs_q.get("bid", 0) or 0) + float(cs_q.get("ask", 0) or 0)) / 2
            cl_mid = (float(cl_q.get("bid", 0) or 0) + float(cl_q.get("ask", 0) or 0)) / 2
            put_credit = max(0, ps_mid - pl_mid)
            call_credit = max(0, cs_mid - cl_mid)

        total = put_credit + call_credit
        width = ps - pl
        return {
            "put_credit": round(put_credit, 4),
            "call_credit": round(call_credit, 4),
            "total_credit": round(total, 4),
            "max_profit": round(total * 100, 2),
            "max_loss": round((width - total) * 100, 2),
        }
    except Exception as e:
        logger.warning(f"Failed to get real credits: {e}")
        return None


def get_ic_mark_to_market(tradier, ps, pl, cs, cl, expiration):
    """Get current cost to close an IC position."""
    try:
        exp_date = datetime.strptime(expiration, "%Y-%m-%d")
        exp_str = exp_date.strftime("%y%m%d")

        def sym(strike, opt_type):
            return f"SPY{exp_str}{opt_type}{int(strike * 1000):08d}"

        ps_q = tradier.get_option_quote(sym(ps, "P"))
        pl_q = tradier.get_option_quote(sym(pl, "P"))
        cs_q = tradier.get_option_quote(sym(cs, "C"))
        cl_q = tradier.get_option_quote(sym(cl, "C"))

        if not all([ps_q, pl_q, cs_q, cl_q]):
            return None

        cost = (
            float(ps_q.get("ask", 0) or 0)
            + float(cs_q.get("ask", 0) or 0)
            - float(pl_q.get("bid", 0) or 0)
            - float(cl_q.get("bid", 0) or 0)
        )
        return max(0, round(cost, 4))
    except Exception as e:
        logger.warning(f"MTM failed: {e}")
        return None

# COMMAND ----------

# MAGIC %md
# MAGIC ## Trading Logic

# COMMAND ----------

def is_in_trading_window(now):
    """Check if within trading hours (CT)."""
    mins = now.hour * 60 + now.minute
    start_h, start_m = map(int, ENTRY_START_CT.split(":"))
    start = start_h * 60 + start_m
    eod = 14 * 60 + 45  # 2:45 PM CT = 3:45 PM ET
    if mins < start:
        return False, f"Before market open ({ENTRY_START_CT} CT)"
    if mins > eod:
        return False, "Past EOD cutoff (2:45 PM CT)"
    return True, "In trading window"


def is_past_eod_cutoff(now):
    """Check if past 3:45 PM ET."""
    now_et = now.astimezone(EASTERN_TZ)
    cutoff_h, cutoff_m = map(int, EOD_CUTOFF_ET.split(":"))
    if now_et.hour > cutoff_h:
        return True
    if now_et.hour == cutoff_h and now_et.minute >= cutoff_m:
        return True
    return False


def manage_positions(tradier, now, mtm_failures):
    """Manage open positions: profit target, stop loss, EOD."""
    positions = db_get_open_positions()
    if not positions:
        return 0, 0.0, mtm_failures

    managed = 0
    total_pnl = 0.0
    today_str = now.strftime("%Y-%m-%d")

    for pos in positions:
        pid = pos["position_id"]
        entry_credit = float(pos["total_credit"])
        expiration = str(pos["expiration"])
        ps = float(pos["put_short_strike"])
        pl = float(pos["put_long_strike"])
        cs = float(pos["call_short_strike"])
        cl = float(pos["call_long_strike"])
        contracts = int(pos["contracts"])
        collateral = float(pos["collateral_required"] or 0)

        # Check stale/expired
        pos_date = str(pos["open_time"])[:10] if pos["open_time"] else None
        is_stale = pos_date and pos_date < today_str
        is_expired = expiration < today_str

        if is_stale or is_expired:
            reason = "expired_previous_day" if is_expired else "stale_overnight_position"
            close_price = get_ic_mark_to_market(tradier, ps, pl, cs, cl, expiration)
            if close_price is None:
                close_price = entry_credit
            pnl = round((entry_credit - close_price) * 100 * contracts, 2)
            db_close_position(pid, close_price, pnl, reason)
            db_update_paper_balance(realized_pnl=pnl, collateral_change=-collateral)
            db_update_pdt_close(pid, close_price, pnl, reason)
            db_save_equity_snapshot(db_get_paper_account()["balance"], realized_pnl=pnl,
                                   open_positions=len(db_get_open_positions()), note=f"Closed {pid}: {reason}")
            db_log("TRADE_CLOSE", f"Closed {pid}: ${pnl:.2f} [{reason}]")
            managed += 1
            total_pnl += pnl
            mtm_failures.pop(pid, None)
            continue

        # Get MTM
        close_price = get_ic_mark_to_market(tradier, ps, pl, cs, cl, expiration)

        if close_price is None:
            mtm_failures[pid] = mtm_failures.get(pid, 0) + 1
            if mtm_failures[pid] >= MAX_CONSECUTIVE_MTM_FAILURES:
                close_price = entry_credit
                pnl = 0.0
                db_close_position(pid, close_price, pnl, "data_feed_failure")
                db_update_paper_balance(realized_pnl=pnl, collateral_change=-collateral)
                db_log("TRADE_CLOSE", f"Closed {pid}: ${pnl:.2f} [data_feed_failure]")
                managed += 1
                mtm_failures.pop(pid, None)
            elif is_past_eod_cutoff(now):
                close_price = entry_credit
                pnl = 0.0
                db_close_position(pid, close_price, pnl, "eod_safety_no_data")
                db_update_paper_balance(realized_pnl=pnl, collateral_change=-collateral)
                db_log("TRADE_CLOSE", f"Closed {pid}: ${pnl:.2f} [eod_safety_no_data]")
                managed += 1
                mtm_failures.pop(pid, None)
            continue

        mtm_failures.pop(pid, None)

        # Profit target (30%)
        pt_price = entry_credit * (1 - PROFIT_TARGET_PCT / 100)
        if close_price <= pt_price:
            pnl = round((entry_credit - close_price) * 100 * contracts, 2)
            db_close_position(pid, close_price, pnl, "profit_target")
            db_update_paper_balance(realized_pnl=pnl, collateral_change=-collateral)
            db_update_pdt_close(pid, close_price, pnl, "profit_target")
            db_save_equity_snapshot(db_get_paper_account()["balance"], realized_pnl=pnl,
                                   open_positions=len(db_get_open_positions()), note=f"Closed {pid}: profit_target")
            db_log("TRADE_CLOSE", f"Closed {pid}: ${pnl:.2f} [profit_target]")
            managed += 1
            total_pnl += pnl
            continue

        # Stop loss (100%)
        sl_price = entry_credit * (1 + STOP_LOSS_PCT / 100)
        if close_price >= sl_price:
            pnl = round((entry_credit - close_price) * 100 * contracts, 2)
            db_close_position(pid, close_price, pnl, "stop_loss")
            db_update_paper_balance(realized_pnl=pnl, collateral_change=-collateral)
            db_update_pdt_close(pid, close_price, pnl, "stop_loss")
            db_save_equity_snapshot(db_get_paper_account()["balance"], realized_pnl=pnl,
                                   open_positions=len(db_get_open_positions()), note=f"Closed {pid}: stop_loss")
            db_log("TRADE_CLOSE", f"Closed {pid}: ${pnl:.2f} [stop_loss]")
            managed += 1
            total_pnl += pnl
            continue

        # EOD safety
        if is_past_eod_cutoff(now):
            pnl = round((entry_credit - close_price) * 100 * contracts, 2)
            db_close_position(pid, close_price, pnl, "eod_safety")
            db_update_paper_balance(realized_pnl=pnl, collateral_change=-collateral)
            db_update_pdt_close(pid, close_price, pnl, "eod_safety")
            db_save_equity_snapshot(db_get_paper_account()["balance"], realized_pnl=pnl,
                                   open_positions=len(db_get_open_positions()), note=f"Closed {pid}: eod_safety")
            db_log("TRADE_CLOSE", f"Closed {pid}: ${pnl:.2f} [eod_safety]")
            managed += 1
            total_pnl += pnl

    return managed, total_pnl, mtm_failures

# COMMAND ----------

# MAGIC %md
# MAGIC ## Main Run Cycle

# COMMAND ----------

def run_cycle():
    """Execute one complete trading cycle."""
    now = datetime.now(CENTRAL_TZ)
    today_str = now.strftime("%Y-%m-%d")
    mtm_failures = {}

    logger.info(f"=== {BOT_NAME} SCAN @ {now.strftime('%H:%M:%S')} CT ===")

    # Initialize Tradier
    if not TRADIER_API_KEY:
        logger.error("TRADIER_API_KEY not set! Set it via widget or secrets.")
        return {"action": "error", "reason": "No Tradier API key"}

    tradier = TradierClient(TRADIER_API_KEY)

    # Step 1: ALWAYS manage positions
    managed, manage_pnl, mtm_failures = manage_positions(tradier, now, mtm_failures)
    if managed > 0:
        logger.info(f"  Managed {managed} position(s), P&L: ${manage_pnl:.2f}")

    # Step 2: Check trading window
    in_window, window_msg = is_in_trading_window(now)
    if not in_window:
        db_update_heartbeat("idle", window_msg)
        logger.info(f"  {window_msg}")
        return {"action": "outside_window", "reason": window_msg}

    # Step 3: Check for open positions
    if db_get_open_positions():
        db_update_heartbeat("active", "monitoring")
        logger.info("  Monitoring open position(s)")
        return {"action": "monitoring"}

    # Step 4: Already traded today?
    if db_has_traded_today(today_str):
        db_update_heartbeat("active", "max_trades_reached")
        logger.info("  Already traded today")
        return {"action": "max_trades"}

    # Step 5: PDT check
    pdt_count = db_get_day_trade_count_rolling_5()
    if pdt_count >= PDT_MAX_DAY_TRADES:
        db_update_heartbeat("active", "pdt_blocked")
        db_log("SKIP", f"PDT blocked: {pdt_count}/{PDT_MAX_DAY_TRADES}")
        logger.info(f"  PDT blocked: {pdt_count}/{PDT_MAX_DAY_TRADES}")
        return {"action": "pdt_blocked"}

    # Step 6: Check buying power
    account = db_get_paper_account()
    if account["buying_power"] < 200:
        db_update_heartbeat("active", "insufficient_bp")
        db_log("SKIP", f"Insufficient BP: ${account['buying_power']:.2f}")
        logger.info(f"  Insufficient buying power: ${account['buying_power']:.2f}")
        return {"action": "insufficient_bp"}

    # Step 7: Get market data
    market = get_market_data(tradier)
    if not market:
        db_log("SKIP", "No market data")
        logger.warning("  No market data available")
        return {"action": "no_data"}

    spot = market["spot_price"]
    vix = market["vix"]
    em = market["expected_move"]

    # Step 8: VIX filter
    if vix > VIX_SKIP:
        db_log("SKIP", f"VIX {vix:.1f} > {VIX_SKIP}")
        logger.info(f"  VIX {vix:.1f} too high (>{VIX_SKIP})")
        return {"action": "vix_skip", "vix": vix}

    # Step 9: Calculate strikes
    ps, pl, cs, cl = calculate_strikes(spot, em)
    ps, pl, cs, cl, wings_adj = enforce_symmetric_wings(ps, pl, cs, cl)

    # Step 10: Get expiration
    expiration = get_target_expiration(now)
    expiration = validate_expiration(tradier, expiration)
    if not expiration:
        db_log("SKIP", "No valid expiration")
        return {"action": "no_expiration"}

    # Step 11: Get credits
    credits = get_real_credits(tradier, expiration, ps, pl, cs, cl)
    if not credits:
        db_log("SKIP", "Could not get option credits")
        logger.info("  No credits available (options may not be listed)")
        return {"action": "no_credits"}

    total_credit = credits["total_credit"]
    if total_credit < MIN_CREDIT:
        db_log_signal(spot, vix, em, ps, pl, cs, cl, total_credit, 0.5,
                      False, f"Credit ${total_credit:.2f} below min ${MIN_CREDIT}",
                      wings_adjusted=wings_adj)
        logger.info(f"  Credit ${total_credit:.2f} below minimum ${MIN_CREDIT}")
        return {"action": "low_credit", "credit": total_credit}

    # Step 12: Size the trade
    spread_width = ps - pl
    collateral_per = max(0, (spread_width * 100) - (total_credit * 100))
    usable_bp = account["buying_power"] * BUYING_POWER_USAGE_PCT
    max_contracts = min(int(usable_bp / collateral_per) if collateral_per > 0 else 0, MAX_CONTRACTS)

    if max_contracts < 1:
        db_log("SKIP", f"Can't afford 1 contract. BP=${account['buying_power']:.2f}")
        return {"action": "insufficient_bp_for_trade"}

    # Step 13: Race condition guard
    if db_get_open_positions():
        db_log("SKIP", "Position appeared (race guard)")
        return {"action": "race_guard"}

    # Step 14: Execute paper trade
    position_id = f"{BOT_NAME}-{now.strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
    total_collateral = collateral_per * max_contracts

    db_save_position({
        "position_id": position_id,
        "ticker": TICKER,
        "expiration": expiration,
        "put_short": ps, "put_long": pl,
        "put_credit": credits["put_credit"],
        "call_short": cs, "call_long": cl,
        "call_credit": credits["call_credit"],
        "contracts": max_contracts,
        "spread_width": spread_width,
        "total_credit": total_credit,
        "max_loss": credits["max_loss"],
        "max_profit": credits["max_profit"],
        "collateral": total_collateral,
        "spot_price": spot,
        "vix": vix,
        "expected_move": em,
        "wings_adjusted": str(wings_adj).lower(),
    })

    db_update_paper_balance(collateral_change=total_collateral)
    db_log_pdt_entry(position_id, TICKER, now, max_contracts, total_credit)
    db_save_equity_snapshot(db_get_paper_account()["balance"],
                           open_positions=1, note=f"Opened {position_id}")

    db_log_signal(spot, vix, em, ps, pl, cs, cl, total_credit, 0.5,
                  True, reasoning=f"{DTE_MODE} IC opened", wings_adjusted=wings_adj)

    db_log("TRADE_OPEN",
           f"Opened {position_id}: {pl}/{ps}P-{cs}/{cl}C x{max_contracts} @ ${total_credit:.2f}",
           {"position_id": position_id, "contracts": max_contracts,
            "credit": total_credit, "collateral": total_collateral})

    db_update_heartbeat("active", "traded")

    logger.info(f"  TRADED: {position_id}")
    logger.info(f"    {pl}/{ps}P - {cs}/{cl}C x{max_contracts}")
    logger.info(f"    Credit: ${total_credit:.2f} | Collateral: ${total_collateral:.2f}")
    logger.info(f"    Expiration: {expiration} | Wings adjusted: {wings_adj}")

    return {
        "action": "traded",
        "position_id": position_id,
        "strikes": f"{pl}/{ps}P-{cs}/{cl}C",
        "contracts": max_contracts,
        "credit": total_credit,
    }

# COMMAND ----------

# MAGIC %md
# MAGIC ## Run It

# COMMAND ----------

result = run_cycle()
print(f"\nResult: {result}")
