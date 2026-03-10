"""
IronForge Databricks API — FastAPI layer for the dashboard.

Exposes the SAME endpoints with the SAME response shapes as the
Next.js API routes so the dashboard works without modification.

Env vars required:
  DATABRICKS_HOST          - Databricks workspace hostname
  DATABRICKS_HTTP_PATH     - SQL warehouse HTTP path
  DATABRICKS_TOKEN         - Personal access token
  TRADIER_API_KEY          - Sandbox API key (for market data quotes)
  TRADIER_SANDBOX_KEY_USER - (optional) Sandbox key for User account
  TRADIER_SANDBOX_KEY_MATT - (optional) Sandbox key for Matt account
  TRADIER_SANDBOX_KEY_LOGAN - (optional) Sandbox key for Logan account
  TRADIER_SANDBOX_ACCOUNT_ID_USER  - (optional) Account ID for User
  TRADIER_SANDBOX_ACCOUNT_ID_MATT  - (required) Account ID for Matt
  TRADIER_SANDBOX_ACCOUNT_ID_LOGAN - (required) Account ID for Logan

Run: uvicorn ironforge_api:app --host 0.0.0.0 --port 8000
"""

import os
import json
import math
import random
import logging
import traceback
import requests
from datetime import datetime, timedelta
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Import shared functions from the scanner module
from ironforge_scanner import (
    db_query,
    db_execute,
    bot_table,
    num,
    to_int,
    get_central_time,
    is_tradier_configured,
    get_quote,
    get_ic_mark_to_market,
    get_ic_entry_credit,
    get_option_expirations,
    evaluate_advisor,
    calculate_strikes,
    get_target_expiration,
    open_ic_sandbox_per_account,
    close_ic_sandbox_per_account,
    _get_sandbox_order_fill_price,
    _get_sandbox_accounts_lazy,
    _get_account_id_for_key,
    shared_table,
    CATALOG,
    SCHEMA,
    SANDBOX_URL,
)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("ironforge.api")

# ---------------------------------------------------------------------------
#  FastAPI App
# ---------------------------------------------------------------------------

app = FastAPI(title="IronForge Databricks API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
#  Helpers
# ---------------------------------------------------------------------------

VALID_BOTS = {"flame", "spark"}
DTE_MAP = {"flame": "2DTE", "spark": "1DTE"}
MIN_DTE_MAP = {"flame": 2, "spark": 1}
HEARTBEAT_MAP = {"flame": "FLAME", "spark": "SPARK"}


def validate_bot(bot: str) -> str:
    """Validate and normalize bot name."""
    b = bot.lower()
    if b not in VALID_BOTS:
        raise HTTPException(status_code=400, detail="Invalid bot")
    return b


def dte_mode(bot: str) -> str:
    return DTE_MAP[bot]


def heartbeat_name(bot: str) -> str:
    return HEARTBEAT_MAP[bot]


def fmt_ts(val: Any) -> Optional[str]:
    """Format a timestamp value to ISO string."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.isoformat()
    return str(val)


def fmt_date(val: Any) -> Optional[str]:
    """Format a date value to YYYY-MM-DD string."""
    if val is None:
        return None
    return str(val)[:10]


def parse_json_safe(val: Any) -> Any:
    """Safely parse a JSON string."""
    if val is None:
        return None
    if isinstance(val, dict):
        return val
    try:
        return json.loads(val)
    except (json.JSONDecodeError, TypeError):
        return None


# ---------------------------------------------------------------------------
#  GET /api/health
# ---------------------------------------------------------------------------


@app.get("/api/health")
async def health():
    try:
        rows = db_query("SELECT CURRENT_TIMESTAMP() as ts")
        return {"status": "ok", "time": fmt_ts(rows[0]["ts"]) if rows else None}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ---------------------------------------------------------------------------
#  GET /api/{bot}/status
# ---------------------------------------------------------------------------


@app.get("/api/{bot}/status")
async def bot_status(bot: str):
    bot = validate_bot(bot)
    dte = dte_mode(bot)
    hb_name = heartbeat_name(bot)

    try:
        account_rows = db_query(f"""
            SELECT starting_capital, current_balance, cumulative_pnl,
                   total_trades, collateral_in_use, buying_power,
                   high_water_mark, max_drawdown, is_active
            FROM {bot_table(bot, 'paper_account')}
            WHERE is_active = TRUE AND dte_mode = '{dte}'
            ORDER BY id DESC LIMIT 1
        """)

        position_count = db_query(f"""
            SELECT COUNT(*) as cnt
            FROM {bot_table(bot, 'positions')}
            WHERE status = 'open' AND dte_mode = '{dte}'
        """)

        heartbeat_rows = db_query(f"""
            SELECT scan_count, last_heartbeat, status, details
            FROM {CATALOG}.{SCHEMA}.bot_heartbeats
            WHERE bot_name = '{hb_name}'
        """)

        snapshot_rows = db_query(f"""
            SELECT unrealized_pnl, open_positions, snapshot_time
            FROM {bot_table(bot, 'equity_snapshots')}
            WHERE dte_mode = '{dte}'
            ORDER BY snapshot_time DESC
            LIMIT 1
        """)

        scans_today = db_query(f"""
            SELECT COUNT(*) as cnt
            FROM {bot_table(bot, 'logs')}
            WHERE level = 'SCAN'
              AND CAST(log_time AS DATE) = CURRENT_DATE()
              AND dte_mode = '{dte}'
        """)

        last_error_rows = db_query(f"""
            SELECT log_time, message
            FROM {bot_table(bot, 'logs')}
            WHERE level = 'ERROR' AND dte_mode = '{dte}'
            ORDER BY log_time DESC LIMIT 1
        """)

        acct = account_rows[0] if account_rows else {}
        balance = num(acct.get("current_balance"))
        starting_capital = num(acct.get("starting_capital"))
        realized_pnl = num(acct.get("cumulative_pnl"))
        unrealized_pnl = num(snapshot_rows[0].get("unrealized_pnl")) if snapshot_rows else 0
        total_pnl = realized_pnl + unrealized_pnl
        return_pct = (total_pnl / starting_capital * 100) if starting_capital > 0 else 0

        hb = heartbeat_rows[0] if heartbeat_rows else {}
        last_err = last_error_rows[0] if last_error_rows else None

        hb_details = parse_json_safe(hb.get("details")) or {}
        hb_status = hb.get("status", "unknown")
        hb_action = hb_details.get("action", "")

        if hb_status == "error":
            bot_state = "error"
        elif hb_action == "monitoring":
            bot_state = "monitoring"
        elif hb_action in ("traded", "closed"):
            bot_state = "traded"
        elif hb_action in ("outside_window", "outside_entry_window"):
            bot_state = "market_closed"
        elif hb_status == "idle":
            bot_state = "idle"
        elif hb_status == "active":
            bot_state = "scanning"
        else:
            bot_state = "unknown"

        return {
            "bot_name": bot.upper(),
            "strategy": "2DTE Paper Iron Condor" if bot == "flame" else "1DTE Paper Iron Condor",
            "dte": 2 if bot == "flame" else 1,
            "ticker": "SPY",
            "is_active": acct.get("is_active") is True,
            "account": {
                "starting_capital": starting_capital,
                "balance": balance,
                "cumulative_pnl": realized_pnl,
                "unrealized_pnl": unrealized_pnl,
                "total_pnl": round(total_pnl, 2),
                "return_pct": round(return_pct, 2),
                "total_trades": to_int(acct.get("total_trades")),
                "collateral_in_use": num(acct.get("collateral_in_use")),
                "buying_power": num(acct.get("buying_power")),
                "high_water_mark": num(acct.get("high_water_mark")),
                "max_drawdown": num(acct.get("max_drawdown")),
            },
            "open_positions": to_int(position_count[0].get("cnt")) if position_count else 0,
            "last_scan": fmt_ts(hb.get("last_heartbeat")),
            "last_snapshot": fmt_ts(snapshot_rows[0].get("snapshot_time")) if snapshot_rows else None,
            "scan_count": to_int(hb.get("scan_count")),
            "scans_today": to_int(scans_today[0].get("cnt")) if scans_today else 0,
            "spot_price": hb_details.get("spot") or None,
            "vix": hb_details.get("vix") or None,
            "bot_state": bot_state,
            "last_error": {
                "time": fmt_ts(last_err.get("log_time")),
                "message": last_err.get("message"),
            } if last_err else None,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
#  GET /api/{bot}/positions
# ---------------------------------------------------------------------------


@app.get("/api/{bot}/positions")
async def bot_positions(bot: str):
    bot = validate_bot(bot)
    dte = dte_mode(bot)

    try:
        rows = db_query(f"""
            SELECT position_id, ticker, expiration,
                   put_short_strike, put_long_strike, put_credit,
                   call_short_strike, call_long_strike, call_credit,
                   contracts, spread_width, total_credit, max_loss, max_profit,
                   underlying_at_entry, vix_at_entry, collateral_required,
                   oracle_win_probability, oracle_advice,
                   wings_adjusted, status, open_time
            FROM {bot_table(bot, 'positions')}
            WHERE status = 'open' AND dte_mode = '{dte}'
            ORDER BY open_time DESC
        """)

        positions = [{
            "position_id": r["position_id"],
            "ticker": r["ticker"],
            "expiration": fmt_date(r["expiration"]),
            "put_short_strike": num(r["put_short_strike"]),
            "put_long_strike": num(r["put_long_strike"]),
            "put_credit": num(r["put_credit"]),
            "call_short_strike": num(r["call_short_strike"]),
            "call_long_strike": num(r["call_long_strike"]),
            "call_credit": num(r["call_credit"]),
            "contracts": to_int(r["contracts"]),
            "spread_width": num(r["spread_width"]),
            "total_credit": num(r["total_credit"]),
            "max_loss": num(r["max_loss"]),
            "max_profit": num(r["max_profit"]),
            "underlying_at_entry": num(r["underlying_at_entry"]),
            "vix_at_entry": num(r["vix_at_entry"]),
            "collateral_required": num(r["collateral_required"]),
            "oracle_win_probability": num(r["oracle_win_probability"]),
            "oracle_advice": r.get("oracle_advice"),
            "wings_adjusted": r.get("wings_adjusted") is True,
            "open_time": fmt_ts(r["open_time"]),
        } for r in rows]

        return {"positions": positions}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
#  GET /api/{bot}/position-monitor
# ---------------------------------------------------------------------------


@app.get("/api/{bot}/position-monitor")
async def bot_position_monitor(bot: str):
    bot = validate_bot(bot)
    dte = dte_mode(bot)

    try:
        rows = db_query(f"""
            SELECT position_id, ticker, expiration,
                   put_short_strike, put_long_strike, put_credit,
                   call_short_strike, call_long_strike, call_credit,
                   contracts, spread_width, total_credit, max_loss, max_profit,
                   underlying_at_entry, vix_at_entry, collateral_required,
                   wings_adjusted, open_time, sandbox_order_id
            FROM {bot_table(bot, 'positions')}
            WHERE status = 'open' AND dte_mode = '{dte}'
            ORDER BY open_time DESC
        """)

        if not rows:
            return {
                "positions": [],
                "total_unrealized_pnl": 0,
                "spot_price": None,
                "tradier_connected": is_tradier_configured(),
            }

        positions = []
        for r in rows:
            ps = num(r["put_short_strike"])
            pl = num(r["put_long_strike"])
            cs = num(r["call_short_strike"])
            cl = num(r["call_long_strike"])
            contracts = to_int(r["contracts"])
            entry_credit = num(r["total_credit"])
            ticker = r.get("ticker") or "SPY"
            expiration = fmt_date(r["expiration"]) or ""

            profit_target_price = round(entry_credit * 0.7, 4)
            stop_loss_price = round(entry_credit * 2.0, 4)

            mtm_val = None
            unrealized_pnl = None
            unrealized_pnl_pct = None
            spot_price = None
            distance_to_pt = None
            distance_to_sl = None

            if is_tradier_configured():
                mtm_result = get_ic_mark_to_market(ticker, expiration, ps, pl, cs, cl)
                if mtm_result:
                    mtm_val = mtm_result["cost_to_close"]
                    spot_price = mtm_result["spot_price"]
                    unrealized_pnl = round((entry_credit - mtm_val) * 100 * contracts, 2)
                    unrealized_pnl_pct = (
                        round((entry_credit - mtm_val) / entry_credit * 100, 2)
                        if entry_credit > 0 else 0
                    )
                    distance_to_pt = round(mtm_val - profit_target_price, 4)
                    distance_to_sl = round(stop_loss_price - mtm_val, 4)

            positions.append({
                "position_id": r["position_id"],
                "ticker": ticker,
                "expiration": expiration,
                "put_short_strike": ps,
                "put_long_strike": pl,
                "put_credit": num(r["put_credit"]),
                "call_short_strike": cs,
                "call_long_strike": cl,
                "call_credit": num(r["call_credit"]),
                "contracts": contracts,
                "spread_width": num(r["spread_width"]),
                "total_credit": entry_credit,
                "max_loss": num(r["max_loss"]),
                "max_profit": num(r["max_profit"]),
                "underlying_at_entry": num(r["underlying_at_entry"]),
                "vix_at_entry": num(r["vix_at_entry"]),
                "collateral_required": num(r["collateral_required"]),
                "wings_adjusted": r.get("wings_adjusted") is True,
                "open_time": fmt_ts(r["open_time"]),
                "current_cost_to_close": mtm_val,
                "spot_price": spot_price,
                "unrealized_pnl": unrealized_pnl,
                "unrealized_pnl_pct": unrealized_pnl_pct,
                "profit_target_price": profit_target_price,
                "stop_loss_price": stop_loss_price,
                "distance_to_pt": distance_to_pt,
                "distance_to_sl": distance_to_sl,
                "sandbox_order_ids": parse_json_safe(r.get("sandbox_order_id")),
            })

        total_unrealized = sum(p["unrealized_pnl"] or 0 for p in positions)

        return {
            "positions": positions,
            "total_unrealized_pnl": round(total_unrealized, 2),
            "spot_price": positions[0]["spot_price"] if positions else None,
            "tradier_connected": is_tradier_configured(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
#  GET /api/{bot}/equity-curve
# ---------------------------------------------------------------------------


@app.get("/api/{bot}/equity-curve")
async def bot_equity_curve(bot: str, period: str = "all"):
    bot = validate_bot(bot)
    dte = dte_mode(bot)

    try:
        capital_rows = db_query(f"""
            SELECT starting_capital
            FROM {bot_table(bot, 'paper_account')}
            WHERE is_active = TRUE AND dte_mode = '{dte}'
            LIMIT 1
        """)

        curve_rows = db_query(f"""
            SELECT close_time, realized_pnl,
                   SUM(realized_pnl) OVER (ORDER BY close_time) as cumulative_pnl
            FROM {bot_table(bot, 'positions')}
            WHERE status IN ('closed', 'expired')
              AND realized_pnl IS NOT NULL
              AND close_time IS NOT NULL
              AND dte_mode = '{dte}'
            ORDER BY close_time
        """)

        starting_capital = num(capital_rows[0].get("starting_capital")) if capital_rows else 5000

        curve = [{
            "timestamp": fmt_ts(row["close_time"]),
            "pnl": num(row["realized_pnl"]),
            "cumulative_pnl": num(row["cumulative_pnl"]),
            "equity": round(starting_capital + num(row["cumulative_pnl"]), 2),
        } for row in curve_rows]

        # Filter by period if not 'all'
        if period != "all" and curve:
            now = datetime.now()
            cutoff_map = {
                "1d": now.replace(hour=0, minute=0, second=0, microsecond=0),
                "1w": now - timedelta(days=7),
                "1m": now - timedelta(days=30),
                "3m": now - timedelta(days=90),
            }
            cutoff = cutoff_map.get(period, datetime.min)
            curve = [
                pt for pt in curve
                if pt["timestamp"] and datetime.fromisoformat(pt["timestamp"].replace("Z", "+00:00")) >= cutoff
            ]

        return {"starting_capital": starting_capital, "curve": curve, "period": period}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
#  GET /api/{bot}/equity-curve/intraday
# ---------------------------------------------------------------------------


@app.get("/api/{bot}/equity-curve/intraday")
async def bot_equity_curve_intraday(bot: str):
    bot = validate_bot(bot)
    dte = dte_mode(bot)

    try:
        capital_rows = db_query(f"""
            SELECT starting_capital
            FROM {bot_table(bot, 'paper_account')}
            WHERE is_active = TRUE AND dte_mode = '{dte}'
            LIMIT 1
        """)

        snapshot_rows = db_query(f"""
            SELECT snapshot_time, balance, realized_pnl, unrealized_pnl,
                   open_positions, note
            FROM {bot_table(bot, 'equity_snapshots')}
            WHERE dte_mode = '{dte}'
              AND CAST(snapshot_time AS DATE) = CURRENT_DATE()
            ORDER BY snapshot_time ASC
        """)

        starting_capital = num(capital_rows[0].get("starting_capital")) if capital_rows else 5000

        snapshots = [{
            "timestamp": fmt_ts(r["snapshot_time"]),
            "balance": num(r["balance"]),
            "realized_pnl": num(r["realized_pnl"]),
            "unrealized_pnl": num(r["unrealized_pnl"]),
            "equity": num(r["balance"]) + num(r["unrealized_pnl"]),
            "open_positions": to_int(r["open_positions"]),
            "note": r.get("note"),
        } for r in snapshot_rows]

        return {"starting_capital": starting_capital, "snapshots": snapshots}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
#  GET /api/{bot}/trades
# ---------------------------------------------------------------------------


@app.get("/api/{bot}/trades")
async def bot_trades(bot: str):
    bot = validate_bot(bot)
    dte = dte_mode(bot)

    try:
        rows = db_query(f"""
            SELECT position_id, ticker, expiration,
                   put_short_strike, put_long_strike,
                   call_short_strike, call_long_strike,
                   contracts, spread_width, total_credit,
                   close_price, close_reason, realized_pnl,
                   open_time, close_time,
                   underlying_at_entry, vix_at_entry,
                   wings_adjusted, sandbox_order_id
            FROM {bot_table(bot, 'positions')}
            WHERE status IN ('closed', 'expired') AND dte_mode = '{dte}'
            ORDER BY close_time DESC
            LIMIT 50
        """)

        trades = [{
            "position_id": r["position_id"],
            "ticker": r["ticker"],
            "expiration": fmt_date(r["expiration"]),
            "put_short_strike": num(r["put_short_strike"]),
            "put_long_strike": num(r["put_long_strike"]),
            "call_short_strike": num(r["call_short_strike"]),
            "call_long_strike": num(r["call_long_strike"]),
            "contracts": to_int(r["contracts"]),
            "spread_width": num(r["spread_width"]),
            "total_credit": num(r["total_credit"]),
            "close_price": num(r["close_price"]),
            "close_reason": r.get("close_reason", ""),
            "realized_pnl": num(r["realized_pnl"]),
            "open_time": fmt_ts(r["open_time"]),
            "close_time": fmt_ts(r["close_time"]),
            "underlying_at_entry": num(r["underlying_at_entry"]),
            "vix_at_entry": num(r["vix_at_entry"]),
            "wings_adjusted": r.get("wings_adjusted") is True,
            "sandbox_order_ids": parse_json_safe(r.get("sandbox_order_id")),
        } for r in rows]

        return {"trades": trades}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
#  GET /api/{bot}/performance
# ---------------------------------------------------------------------------


@app.get("/api/{bot}/performance")
async def bot_performance(bot: str):
    bot = validate_bot(bot)
    dte = dte_mode(bot)

    try:
        rows = db_query(f"""
            SELECT
                COUNT(*) as total_trades,
                SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN realized_pnl <= 0 THEN 1 ELSE 0 END) as losses,
                COALESCE(SUM(realized_pnl), 0) as total_pnl,
                COALESCE(AVG(CASE WHEN realized_pnl > 0 THEN realized_pnl END), 0) as avg_win,
                COALESCE(AVG(CASE WHEN realized_pnl <= 0 THEN realized_pnl END), 0) as avg_loss,
                COALESCE(MAX(realized_pnl), 0) as best_trade,
                COALESCE(MIN(realized_pnl), 0) as worst_trade
            FROM {bot_table(bot, 'positions')}
            WHERE status IN ('closed', 'expired')
              AND realized_pnl IS NOT NULL
              AND dte_mode = '{dte}'
        """)

        r = rows[0] if rows else {}
        total = to_int(r.get("total_trades"))
        wins = to_int(r.get("wins"))
        win_rate = (wins / total * 100) if total > 0 else 0

        return {
            "total_trades": total,
            "wins": wins,
            "losses": to_int(r.get("losses")),
            "win_rate": round(win_rate, 1),
            "total_pnl": round(num(r.get("total_pnl")), 2),
            "avg_win": round(num(r.get("avg_win")), 2),
            "avg_loss": round(num(r.get("avg_loss")), 2),
            "best_trade": round(num(r.get("best_trade")), 2),
            "worst_trade": round(num(r.get("worst_trade")), 2),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
#  GET /api/{bot}/logs
# ---------------------------------------------------------------------------


@app.get("/api/{bot}/logs")
async def bot_logs(bot: str):
    bot = validate_bot(bot)
    dte = dte_mode(bot)

    try:
        rows = db_query(f"""
            SELECT log_time, level, message, details
            FROM {bot_table(bot, 'logs')}
            WHERE dte_mode = '{dte}'
            ORDER BY log_time DESC
            LIMIT 50
        """)

        logs = [{
            "timestamp": fmt_ts(r["log_time"]),
            "level": r["level"],
            "message": r["message"],
            "details": r["details"],
        } for r in rows]

        return {"logs": logs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
#  GET /api/{bot}/config
# ---------------------------------------------------------------------------

CONFIG_DEFAULTS = {
    "flame": {
        "sd_multiplier": 1.2, "spread_width": 5.0, "min_credit": 0.05,
        "profit_target_pct": 30.0, "stop_loss_pct": 100.0, "vix_skip": 32.0,
        "max_contracts": 10, "max_trades_per_day": 1, "buying_power_usage_pct": 0.85,
        "risk_per_trade_pct": 0.15, "min_win_probability": 0.42,
        "entry_start": "08:30", "entry_end": "14:00", "eod_cutoff_et": "15:45",
        "pdt_max_day_trades": 3, "starting_capital": 5000.0,
    },
    "spark": {
        "sd_multiplier": 1.2, "spread_width": 5.0, "min_credit": 0.05,
        "profit_target_pct": 30.0, "stop_loss_pct": 100.0, "vix_skip": 32.0,
        "max_contracts": 10, "max_trades_per_day": 1, "buying_power_usage_pct": 0.85,
        "risk_per_trade_pct": 0.15, "min_win_probability": 0.42,
        "entry_start": "08:30", "entry_end": "14:00", "eod_cutoff_et": "15:45",
        "pdt_max_day_trades": 3, "starting_capital": 5000.0,
    },
}

NUMERIC_FIELDS = {
    "sd_multiplier", "spread_width", "min_credit", "profit_target_pct",
    "stop_loss_pct", "vix_skip", "buying_power_usage_pct", "risk_per_trade_pct",
    "min_win_probability", "starting_capital",
}
INT_FIELDS = {"max_contracts", "max_trades_per_day", "pdt_max_day_trades"}
STRING_FIELDS = {"entry_start", "entry_end", "eod_cutoff_et"}
ALL_FIELDS = NUMERIC_FIELDS | INT_FIELDS | STRING_FIELDS


@app.get("/api/{bot}/config")
async def bot_config_get(bot: str):
    bot = validate_bot(bot)
    dte = dte_mode(bot)

    try:
        rows = db_query(f"""
            SELECT sd_multiplier, spread_width, min_credit, profit_target_pct,
                   stop_loss_pct, vix_skip, max_contracts, max_trades_per_day,
                   buying_power_usage_pct, risk_per_trade_pct, min_win_probability,
                   entry_start, entry_end, eod_cutoff_et, pdt_max_day_trades,
                   starting_capital
            FROM {bot_table(bot, 'config')}
            WHERE dte_mode = '{dte}' LIMIT 1
        """)

        defaults = CONFIG_DEFAULTS[bot].copy()
        if not rows:
            defaults["source"] = "defaults"
            return defaults

        row = rows[0]
        merged = defaults.copy()
        for key in ALL_FIELDS:
            if row.get(key) is not None:
                if key in INT_FIELDS:
                    merged[key] = to_int(row[key])
                elif key in NUMERIC_FIELDS:
                    merged[key] = num(row[key])
                else:
                    merged[key] = row[key]
        merged["source"] = "database"
        return merged
    except Exception:
        defaults = CONFIG_DEFAULTS[bot].copy()
        defaults["source"] = "defaults"
        return defaults


# ---------------------------------------------------------------------------
#  PUT /api/{bot}/config
# ---------------------------------------------------------------------------


@app.put("/api/{bot}/config")
async def bot_config_put(bot: str, request: Request):
    bot = validate_bot(bot)
    dte = dte_mode(bot)

    try:
        body = await request.json()

        # Filter to only allowed fields
        filtered = {}
        for key, val in body.items():
            if key not in ALL_FIELDS:
                continue
            if key in INT_FIELDS:
                v = int(val)
                if v < 0:
                    continue
                filtered[key] = v
            elif key in NUMERIC_FIELDS:
                v = float(val)
                if v < 0:
                    continue
                filtered[key] = v
            else:
                filtered[key] = str(val)

        if not filtered:
            raise HTTPException(status_code=400, detail="No valid config fields provided")

        if "profit_target_pct" in filtered and not (0 < filtered["profit_target_pct"] < 100):
            raise HTTPException(status_code=422, detail="profit_target_pct must be 0-100")
        if "spread_width" in filtered and filtered["spread_width"] <= 0:
            raise HTTPException(status_code=422, detail="spread_width must be positive")

        # Build MERGE statement for upsert
        col_names = ", ".join(["dte_mode"] + list(filtered.keys()))
        values_parts = [f"'{dte}'"]
        for key, val in filtered.items():
            if isinstance(val, str):
                values_parts.append(f"'{val}'")
            else:
                values_parts.append(str(val))
        values_str = ", ".join(values_parts)

        update_parts = [f"{k} = s.{k}" for k in filtered.keys()]
        update_parts.append("updated_at = CURRENT_TIMESTAMP()")
        update_str = ", ".join(update_parts)

        source_cols = ", ".join([f"'{dte}' AS dte_mode"] + [
            f"{'chr(39)' if isinstance(v, str) else ''}{v}{'chr(39)' if isinstance(v, str) else ''} AS {k}"
            for k, v in filtered.items()
        ])

        # Simpler approach: try insert, if conflict update
        # Databricks MERGE INTO
        set_parts = ", ".join(
            [f"{k} = {repr(v) if isinstance(v, str) else v}" for k, v in filtered.items()]
            + ["updated_at = CURRENT_TIMESTAMP()"]
        )
        insert_cols = ", ".join(["dte_mode"] + list(filtered.keys()) + ["created_at", "updated_at"])
        insert_vals_parts = [f"'{dte}'"]
        for val in filtered.values():
            insert_vals_parts.append(f"'{val}'" if isinstance(val, str) else str(val))
        insert_vals_parts.extend(["CURRENT_TIMESTAMP()", "CURRENT_TIMESTAMP()"])
        insert_vals = ", ".join(insert_vals_parts)

        db_execute(f"""
            MERGE INTO {bot_table(bot, 'config')} AS t
            USING (SELECT '{dte}' AS dte_mode) AS s
            ON t.dte_mode = s.dte_mode
            WHEN MATCHED THEN UPDATE SET {set_parts}
            WHEN NOT MATCHED THEN INSERT ({insert_cols}) VALUES ({insert_vals})
        """)

        # Log
        details_json = json.dumps({**filtered, "source": "config_api"}).replace("'", "''")
        db_execute(f"""
            INSERT INTO {bot_table(bot, 'logs')}
                (log_time, level, message, details, dte_mode)
            VALUES (
                CURRENT_TIMESTAMP(),
                'CONFIG',
                'Config updated: {", ".join(filtered.keys())}',
                '{details_json}',
                '{dte}'
            )
        """)

        return {
            "success": True,
            "updated_fields": list(filtered.keys()),
            "values": filtered,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
#  GET /api/{bot}/daily-perf
# ---------------------------------------------------------------------------


@app.get("/api/{bot}/daily-perf")
async def bot_daily_perf(bot: str):
    bot = validate_bot(bot)

    try:
        rows = db_query(f"""
            SELECT trade_date, trades_executed, positions_closed, realized_pnl
            FROM {bot_table(bot, 'daily_perf')}
            ORDER BY trade_date DESC
            LIMIT 30
        """)

        data = [{
            "trade_date": fmt_date(r["trade_date"]),
            "trades_executed": to_int(r["trades_executed"]),
            "positions_closed": to_int(r["positions_closed"]),
            "realized_pnl": num(r["realized_pnl"]),
        } for r in rows]

        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
#  POST /api/{bot}/force-trade
# ---------------------------------------------------------------------------


@app.post("/api/{bot}/force-trade")
async def bot_force_trade(bot: str):
    bot = validate_bot(bot)
    dte = dte_mode(bot)
    min_dte = MIN_DTE_MAP[bot]
    bot_upper = bot.upper()

    if not is_tradier_configured():
        raise HTTPException(status_code=500, detail="TRADIER_API_KEY not configured")

    try:
        # 1. Check for existing open position
        open_rows = db_query(f"""
            SELECT position_id FROM {bot_table(bot, 'positions')}
            WHERE status = 'open' AND dte_mode = '{dte}' LIMIT 1
        """)
        if open_rows:
            raise HTTPException(
                status_code=409,
                detail=f"{bot_upper} already has an open position: {open_rows[0]['position_id']}",
            )

        # 2. Get market data
        spy_quote = get_quote("SPY")
        vix_quote = get_quote("VIX")

        if not spy_quote:
            raise HTTPException(status_code=502, detail="Could not get SPY quote from Tradier")

        spot = spy_quote["last"]
        if not vix_quote or not vix_quote.get("last"):
            raise HTTPException(status_code=502, detail="Could not get VIX quote from Tradier")
        vix = vix_quote["last"]
        expected_move = (vix / 100 / math.sqrt(252)) * spot

        # 3. VIX filter
        if vix > 32:
            raise HTTPException(status_code=422, detail=f"VIX {vix:.1f} too high (>32), skipping")

        # 4. Expiration
        target_exp = get_target_expiration(min_dte)
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

        # 5. Strikes
        strikes = calculate_strikes(spot, expected_move)

        # 6. Credits
        credits = get_ic_entry_credit(
            "SPY", expiration,
            strikes["putShort"], strikes["putLong"],
            strikes["callShort"], strikes["callLong"],
        )
        if not credits or credits["totalCredit"] < 0.05:
            raise HTTPException(
                status_code=422,
                detail=f"Credit too low: ${credits['totalCredit']:.4f if credits else 0} (min $0.05)",
            )

        # 7. Account + sizing
        account_rows = db_query(f"""
            SELECT id, current_balance, buying_power
            FROM {bot_table(bot, 'paper_account')}
            WHERE is_active = TRUE AND dte_mode = '{dte}'
            ORDER BY id DESC LIMIT 1
        """)
        if not account_rows:
            raise HTTPException(status_code=500, detail="No paper account found")

        acct = account_rows[0]
        buying_power = num(acct["buying_power"])
        spread_width = strikes["putShort"] - strikes["putLong"]
        collateral_per = max(0, (spread_width - credits["totalCredit"]) * 100)
        usable_bp = buying_power * 0.85
        max_contracts = min(10, max(1, math.floor(usable_bp / collateral_per))) if collateral_per > 0 else 0

        if buying_power < 200 or collateral_per <= 0:
            raise HTTPException(status_code=422, detail=f"Insufficient buying power: ${buying_power:.2f}")

        total_collateral = collateral_per * max_contracts
        max_profit = credits["totalCredit"] * 100 * max_contracts
        max_loss = total_collateral

        # 8. Advisor
        adv = evaluate_advisor(vix, spot, expected_move, dte)

        # 9. Position ID
        now = datetime.now()
        date_str = now.strftime("%Y%m%d")
        hex_str = format(random.randint(0, 0xFFFFFF), "06X")
        position_id = f"{bot_upper}-{date_str}-{hex_str}"

        now_ts = get_central_time().strftime("%Y-%m-%d %H:%M:%S")
        today_date = get_central_time().strftime("%Y-%m-%d")
        factors_json = json.dumps(adv["topFactors"]).replace("'", "''")

        # 10. Insert position
        db_execute(f"""
            INSERT INTO {bot_table(bot, 'positions')} (
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
                created_at, updated_at
            ) VALUES (
                '{position_id}', 'SPY', CAST('{expiration}' AS DATE),
                {strikes['putShort']}, {strikes['putLong']}, {credits['putCredit']},
                {strikes['callShort']}, {strikes['callLong']}, {credits['callCredit']},
                {max_contracts}, {spread_width}, {credits['totalCredit']}, {max_loss}, {max_profit},
                {total_collateral},
                {spot}, {vix}, {expected_move},
                0, 0, 'UNKNOWN', 0, 0,
                {adv['confidence']}, {adv['winProbability']}, '{adv['advice']}',
                '{adv['reasoning'].replace(chr(39), chr(39)+chr(39))}', '{factors_json}', FALSE,
                FALSE, {spread_width}, {spread_width},
                'PAPER', 'PAPER',
                'open', CAST('{now_ts}' AS TIMESTAMP), CAST('{today_date}' AS DATE), '{dte}',
                CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP()
            )
        """)

        # 10b. Sandbox mirror — each account sizes independently
        sandbox_order_ids = {}
        actual_credit = credits["totalCredit"]
        try:
            sandbox_order_ids = open_ic_sandbox_per_account(
                "SPY", expiration,
                strikes["putShort"], strikes["putLong"],
                strikes["callShort"], strikes["callLong"],
                collateral_per, position_id,
            )
            if sandbox_order_ids:
                sandbox_json = json.dumps(sandbox_order_ids).replace("'", "''")
                db_execute(f"""
                    UPDATE {bot_table(bot, 'positions')}
                    SET sandbox_order_id = '{sandbox_json}', updated_at = CURRENT_TIMESTAMP()
                    WHERE position_id = '{position_id}'
                """)

                # Get actual fill price from User's sandbox order
                user_info = sandbox_order_ids.get("User", {})
                if isinstance(user_info, dict) and user_info.get("order_id"):
                    all_accounts = _get_sandbox_accounts_lazy()
                    user_accts = [a for a in all_accounts if a["name"] == "User"]
                    if user_accts:
                        user_acct_id = _get_account_id_for_key(user_accts[0]["api_key"])
                        if user_acct_id:
                            fill = _get_sandbox_order_fill_price(
                                user_accts[0]["api_key"], user_acct_id,
                                user_info["order_id"],
                            )
                            if fill is not None and fill > 0:
                                log.info(
                                    f"Force trade fill from USER sandbox: ${fill:.4f} "
                                    f"(calculated was ${credits['totalCredit']:.4f})"
                                )
                                actual_credit = fill
        except Exception as sb_err:
            log.warning(f"Sandbox mirror failed for {position_id}: {sb_err}")

        # 11. Update paper account
        db_execute(f"""
            UPDATE {bot_table(bot, 'paper_account')}
            SET collateral_in_use = collateral_in_use + {total_collateral},
                buying_power = buying_power - {total_collateral},
                updated_at = CURRENT_TIMESTAMP()
            WHERE id = {acct['id']}
        """)

        # 12. Signal + logs + PDT + snapshot + daily_perf
        db_execute(f"""
            INSERT INTO {bot_table(bot, 'signals')} (
                signal_time, spot_price, vix, expected_move, call_wall, put_wall,
                gex_regime, put_short, put_long, call_short, call_long,
                total_credit, confidence, was_executed, reasoning, wings_adjusted, dte_mode
            ) VALUES (
                CURRENT_TIMESTAMP(), {spot}, {vix}, {expected_move}, 0, 0,
                'UNKNOWN', {strikes['putShort']}, {strikes['putLong']},
                {strikes['callShort']}, {strikes['callLong']},
                {credits['totalCredit']}, {adv['confidence']}, TRUE,
                'Force trade via API | {adv['reasoning'].replace(chr(39), chr(39)+chr(39))}',
                FALSE, '{dte}'
            )
        """)

        trade_details = json.dumps({
            "position_id": position_id, "contracts": max_contracts,
            "credit": credits["totalCredit"], "collateral": total_collateral,
            "source": "force_trade_api", "sandbox_order_ids": sandbox_order_ids,
        }).replace("'", "''")
        db_execute(f"""
            INSERT INTO {bot_table(bot, 'logs')} (log_time, level, message, details, dte_mode)
            VALUES (CURRENT_TIMESTAMP(), 'TRADE_OPEN',
                'FORCE TRADE: {position_id} {strikes['putLong']}/{strikes['putShort']}P-{strikes['callShort']}/{strikes['callLong']}C x{max_contracts} @ ${credits['totalCredit']:.4f}',
                '{trade_details}', '{dte}')
        """)

        db_execute(f"""
            INSERT INTO {bot_table(bot, 'pdt_log')}
                (trade_date, symbol, position_id, opened_at, contracts, entry_credit, dte_mode, created_at)
            VALUES (CURRENT_DATE(), 'SPY', '{position_id}', CURRENT_TIMESTAMP(),
                    {max_contracts}, {credits['totalCredit']}, '{dte}', CURRENT_TIMESTAMP())
        """)

        updated_acct = db_query(f"""
            SELECT current_balance, cumulative_pnl
            FROM {bot_table(bot, 'paper_account')} WHERE id = {acct['id']}
        """)
        bal = num(updated_acct[0]["current_balance"]) if updated_acct else 0
        cum_pnl = num(updated_acct[0]["cumulative_pnl"]) if updated_acct else 0
        db_execute(f"""
            INSERT INTO {bot_table(bot, 'equity_snapshots')}
                (snapshot_time, balance, realized_pnl, unrealized_pnl, open_positions, note, dte_mode, created_at)
            VALUES (CURRENT_TIMESTAMP(), {bal}, {cum_pnl}, 0, 1, 'force_trade:{position_id}', '{dte}', CURRENT_TIMESTAMP())
        """)

        db_execute(f"""
            MERGE INTO {bot_table(bot, 'daily_perf')} AS t
            USING (SELECT CURRENT_DATE() AS trade_date) AS s
            ON t.trade_date = s.trade_date
            WHEN MATCHED THEN UPDATE SET trades_executed = t.trades_executed + 1, updated_at = CURRENT_TIMESTAMP()
            WHEN NOT MATCHED THEN INSERT (trade_date, trades_executed, positions_closed, realized_pnl, updated_at)
                VALUES (CURRENT_DATE(), 1, 0, 0, CURRENT_TIMESTAMP())
        """)

        db_execute(f"""
            MERGE INTO {CATALOG}.{SCHEMA}.bot_heartbeats AS t
            USING (SELECT '{bot_upper}' AS bot_name) AS s
            ON t.bot_name = s.bot_name
            WHEN MATCHED THEN UPDATE SET
                last_heartbeat = CURRENT_TIMESTAMP(), status = 'active',
                scan_count = t.scan_count + 1,
                details = '{json.dumps({"last_action": "force_trade"}).replace(chr(39), chr(39)+chr(39))}'
            WHEN NOT MATCHED THEN INSERT (bot_name, last_heartbeat, status, scan_count, details)
                VALUES ('{bot_upper}', CURRENT_TIMESTAMP(), 'active', 1,
                        '{json.dumps({"last_action": "force_trade"}).replace(chr(39), chr(39)+chr(39))}')
        """)

        return {
            "success": True,
            "position_id": position_id,
            "expiration": expiration,
            "strikes": {
                "put_long": strikes["putLong"],
                "put_short": strikes["putShort"],
                "call_short": strikes["callShort"],
                "call_long": strikes["callLong"],
            },
            "contracts": max_contracts,
            "credit": credits["totalCredit"],
            "collateral": total_collateral,
            "max_profit": round(max_profit, 2),
            "max_loss": round(max_loss, 2),
            "spot_price": spot,
            "vix": vix,
            "source": credits["source"],
            "sandbox_order_ids": sandbox_order_ids,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
#  POST /api/{bot}/force-close
# ---------------------------------------------------------------------------


@app.post("/api/{bot}/force-close")
async def bot_force_close(bot: str, request: Request):
    bot = validate_bot(bot)
    dte = dte_mode(bot)

    try:
        body = await request.json()
        position_id = body.get("position_id")
        override_price = body.get("close_price")

        if not position_id:
            raise HTTPException(status_code=400, detail="position_id is required")

        # 1. Look up position (include sandbox_order_id for per-account close)
        rows = db_query(f"""
            SELECT position_id, ticker, expiration,
                   put_short_strike, put_long_strike, put_credit,
                   call_short_strike, call_long_strike, call_credit,
                   contracts, spread_width, total_credit, max_loss,
                   collateral_required, sandbox_order_id
            FROM {bot_table(bot, 'positions')}
            WHERE position_id = '{position_id}' AND status = 'open' AND dte_mode = '{dte}'
            LIMIT 1
        """)

        if not rows:
            raise HTTPException(status_code=404, detail=f"No open position found: {position_id}")

        pos = rows[0]
        total_credit = num(pos["total_credit"])
        contracts = to_int(pos["contracts"])
        collateral = num(pos["collateral_required"])

        # 2. Determine close price
        if override_price is not None and override_price >= 0:
            close_price = override_price
        elif is_tradier_configured():
            mtm = get_ic_mark_to_market(
                pos["ticker"], fmt_date(pos["expiration"]) or "",
                num(pos["put_short_strike"]), num(pos["put_long_strike"]),
                num(pos["call_short_strike"]), num(pos["call_long_strike"]),
            )
            close_price = mtm["cost_to_close"] if mtm else 0
        else:
            close_price = 0

        # 3. Calculate P&L
        pnl_per_contract = (total_credit - close_price) * 100
        realized_pnl = round(pnl_per_contract * contracts, 2)

        now_ts = get_central_time().strftime("%Y-%m-%d %H:%M:%S")
        today_str = get_central_time().strftime("%Y-%m-%d")

        # 4. Close position
        db_execute(f"""
            UPDATE {bot_table(bot, 'positions')}
            SET status = 'closed', close_time = CAST('{now_ts}' AS TIMESTAMP),
                close_price = {close_price}, realized_pnl = {realized_pnl},
                close_reason = 'manual_close', updated_at = CAST('{now_ts}' AS TIMESTAMP)
            WHERE position_id = '{position_id}' AND status = 'open' AND dte_mode = '{dte}'
        """)

        # 5. Update paper account
        db_execute(f"""
            UPDATE {bot_table(bot, 'paper_account')}
            SET current_balance = current_balance + {realized_pnl},
                cumulative_pnl = cumulative_pnl + {realized_pnl},
                total_trades = total_trades + 1,
                collateral_in_use = GREATEST(0, collateral_in_use - {collateral}),
                buying_power = buying_power + {collateral} + {realized_pnl},
                high_water_mark = GREATEST(high_water_mark, current_balance + {realized_pnl}),
                max_drawdown = GREATEST(max_drawdown,
                    GREATEST(high_water_mark, current_balance + {realized_pnl}) - (current_balance + {realized_pnl})),
                updated_at = CAST('{now_ts}' AS TIMESTAMP)
            WHERE is_active = TRUE AND dte_mode = '{dte}'
        """)

        # 6. PDT log
        db_execute(f"""
            UPDATE {bot_table(bot, 'pdt_log')}
            SET closed_at = CAST('{now_ts}' AS TIMESTAMP), exit_cost = {close_price},
                pnl = {realized_pnl}, close_reason = 'manual_close',
                is_day_trade = (CAST(opened_at AS DATE) = CAST('{today_str}' AS DATE))
            WHERE position_id = '{position_id}' AND dte_mode = '{dte}'
        """)

        # 7. Equity snapshot
        acct_rows = db_query(f"""
            SELECT current_balance, cumulative_pnl FROM {bot_table(bot, 'paper_account')}
            WHERE dte_mode = '{dte}' ORDER BY id DESC LIMIT 1
        """)
        bal = num(acct_rows[0]["current_balance"]) if acct_rows else 0
        cum_pnl = num(acct_rows[0]["cumulative_pnl"]) if acct_rows else 0
        open_count = db_query(f"""
            SELECT COUNT(*) as cnt FROM {bot_table(bot, 'positions')}
            WHERE status = 'open' AND dte_mode = '{dte}'
        """)
        open_cnt = to_int(open_count[0]["cnt"]) if open_count else 0
        db_execute(f"""
            INSERT INTO {bot_table(bot, 'equity_snapshots')}
                (snapshot_time, balance, realized_pnl, unrealized_pnl, open_positions, note, dte_mode, created_at)
            VALUES (CURRENT_TIMESTAMP(), {bal}, {cum_pnl}, 0, {open_cnt},
                    'force_close:{position_id}', '{dte}', CURRENT_TIMESTAMP())
        """)

        # 8. Sandbox mirror — per-account contract counts
        sandbox_close_ids = {}
        try:
            sb_json_str = pos.get("sandbox_order_id", "") or ""
            sb_open_info = {}
            if sb_json_str:
                try:
                    sb_open_info = json.loads(sb_json_str)
                except (json.JSONDecodeError, TypeError):
                    pass

            sandbox_close_ids = close_ic_sandbox_per_account(
                pos["ticker"], fmt_date(pos["expiration"]) or "",
                num(pos["put_short_strike"]), num(pos["put_long_strike"]),
                num(pos["call_short_strike"]), num(pos["call_long_strike"]),
                contracts, sb_open_info, position_id,
            )
        except Exception as sb_err:
            log.warning(f"Sandbox close mirror failed for {position_id}: {sb_err}")

        # 9. Log
        details_json = json.dumps({
            "position_id": position_id, "close_price": close_price,
            "realized_pnl": realized_pnl, "close_reason": "manual_close",
            "entry_credit": total_credit, "source": "force_close_api",
            "sandbox_close_ids": sandbox_close_ids,
        }).replace("'", "''")
        db_execute(f"""
            INSERT INTO {bot_table(bot, 'logs')} (log_time, level, message, details, dte_mode)
            VALUES (CURRENT_TIMESTAMP(), 'TRADE_CLOSE',
                'FORCE CLOSE: {position_id} @ ${close_price:.4f} P&L=${realized_pnl:.2f}',
                '{details_json}', '{dte}')
        """)

        # 10. Daily perf
        db_execute(f"""
            MERGE INTO {bot_table(bot, 'daily_perf')} AS t
            USING (SELECT CURRENT_DATE() AS trade_date) AS s
            ON t.trade_date = s.trade_date
            WHEN MATCHED THEN UPDATE SET
                positions_closed = t.positions_closed + 1,
                realized_pnl = t.realized_pnl + {realized_pnl},
                updated_at = CURRENT_TIMESTAMP()
            WHEN NOT MATCHED THEN INSERT (trade_date, trades_executed, positions_closed, realized_pnl, updated_at)
                VALUES (CURRENT_DATE(), 0, 1, {realized_pnl}, CURRENT_TIMESTAMP())
        """)

        return {
            "success": True,
            "position_id": position_id,
            "close_price": close_price,
            "realized_pnl": realized_pnl,
            "entry_credit": total_credit,
            "contracts": contracts,
            "sandbox_close_ids": sandbox_close_ids,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
#  POST /api/{bot}/toggle
# ---------------------------------------------------------------------------


@app.post("/api/{bot}/toggle")
async def bot_toggle(bot: str, request: Request):
    bot = validate_bot(bot)
    dte = dte_mode(bot)
    bot_upper = heartbeat_name(bot)

    try:
        body = await request.json()
        active = bool(body.get("active", False))

        db_execute(f"""
            UPDATE {bot_table(bot, 'paper_account')}
            SET is_active = {active}, updated_at = CURRENT_TIMESTAMP()
            WHERE dte_mode = '{dte}'
        """)

        status_str = "ENABLED" if active else "DISABLED"
        details_json = json.dumps({"active": active, "source": "toggle_api"}).replace("'", "''")
        db_execute(f"""
            INSERT INTO {bot_table(bot, 'logs')} (log_time, level, message, details, dte_mode)
            VALUES (CURRENT_TIMESTAMP(), 'CONFIG', '{bot_upper} bot {status_str} via API',
                    '{details_json}', '{dte}')
        """)

        return {
            "success": True,
            "is_active": active,
            "message": f"{bot_upper} {status_str.lower()}",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
#  Accounts Management (ironforge_accounts)
# ---------------------------------------------------------------------------

ACCOUNTS_TABLE = f"{CATALOG}.{SCHEMA}.ironforge_accounts"


def _mask_api_key(key: str) -> str:
    """Mask API key: show first 4 + ... + last 4 chars."""
    if not key or len(key) < 9:
        return "****"
    return f"{key[:4]}...{key[-4:]}"


def _escape_sql(val: str) -> str:
    """Escape single quotes for Databricks SQL string literals."""
    return val.replace("'", "''")


def _ensure_accounts_table() -> None:
    """Create ironforge_accounts table if it doesn't exist (idempotent)."""
    try:
        db_execute(f"""
            CREATE TABLE IF NOT EXISTS {ACCOUNTS_TABLE} (
                id         BIGINT GENERATED ALWAYS AS IDENTITY,
                person     STRING NOT NULL,
                account_id STRING NOT NULL,
                api_key    STRING NOT NULL,
                bot        STRING NOT NULL,
                type       STRING NOT NULL,
                is_active  BOOLEAN,
                created_at TIMESTAMP,
                updated_at TIMESTAMP,
                CONSTRAINT ironforge_accounts_pk PRIMARY KEY (id)
            )
        """)
    except Exception as e:
        log.warning(f"[accounts] ensure table failed (may already exist): {e}")


def _seed_accounts_from_env() -> None:
    """One-time bootstrap: seed ironforge_accounts from env vars if empty."""
    try:
        rows = db_query(f"SELECT id FROM {ACCOUNTS_TABLE} LIMIT 1")
        if rows:
            return  # Already seeded

        for acct in _get_sandbox_accounts_lazy():
            name = acct["name"]
            api_key = acct["api_key"]
            if not api_key:
                continue

            # Discover account ID
            acct_id = acct.get("account_id") or ""
            if not acct_id:
                acct_id = _get_account_id_for_key(api_key) or ""
            if not acct_id:
                log.warning(f"[accounts] Could not discover account ID for {name} — skipping seed")
                continue

            esc_person = _escape_sql(name)
            esc_acct_id = _escape_sql(acct_id)
            esc_key = _escape_sql(api_key)

            db_execute(f"""
                MERGE INTO {ACCOUNTS_TABLE} AS t
                USING (SELECT '{esc_acct_id}' AS account_id) AS s
                ON t.account_id = s.account_id
                WHEN NOT MATCHED THEN INSERT (
                    person, account_id, api_key, bot, type, is_active, created_at, updated_at
                ) VALUES (
                    '{esc_person}', '{esc_acct_id}', '{esc_key}', 'BOTH', 'production',
                    TRUE, CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP()
                )
            """)
            log.info(f"[accounts] Seeded {name} → {acct_id} (production)")
    except Exception as e:
        log.error(f"[accounts] Seed failed: {e}")


# Run table creation + seed on module load
_ensure_accounts_table()
_seed_accounts_from_env()


@app.get("/api/accounts")
async def get_accounts():
    """Get all accounts grouped by person, with masked API keys."""
    try:
        rows = db_query(f"""
            SELECT id, person, account_id, api_key, bot, type, is_active,
                   created_at, updated_at
            FROM {ACCOUNTS_TABLE}
            ORDER BY type, person, id
        """)

        # Group production accounts by person
        production_by_person: dict[str, list[dict]] = {}
        sandbox_account = None

        for row in rows:
            acct = {
                "id": int(row["id"]),
                "account_id": row["account_id"],
                "api_key_masked": _mask_api_key(row["api_key"] or ""),
                "bot": row["bot"],
                "type": row["type"],
                "is_active": bool(row["is_active"]) if row["is_active"] is not None else True,
                "created_at": fmt_ts(row.get("created_at")),
                "updated_at": fmt_ts(row.get("updated_at")),
            }

            if row["type"] == "sandbox":
                sandbox_account = {
                    "person": row["person"],
                    **acct,
                }
            else:
                person = row["person"]
                if person not in production_by_person:
                    production_by_person[person] = []
                production_by_person[person].append(acct)

        production = [
            {"person": person, "accounts": accounts}
            for person, accounts in production_by_person.items()
        ]

        return {"production": production, "sandbox": sandbox_account}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class AccountCreate(BaseModel):
    person: str
    account_id: str
    api_key: str
    bot: str
    type: str


@app.post("/api/accounts")
async def create_account(body: AccountCreate):
    """Create a new account. Rejects sandbox if one already exists."""
    if not body.person or not body.account_id or not body.api_key:
        raise HTTPException(status_code=400, detail="person, account_id, and api_key are required")
    if body.bot not in ("FLAME", "SPARK", "INFERNO", "BOTH"):
        raise HTTPException(status_code=400, detail="bot must be FLAME, SPARK, INFERNO, or BOTH")
    if body.type not in ("production", "sandbox"):
        raise HTTPException(status_code=400, detail="type must be production or sandbox")

    try:
        # Sandbox enforcement: only one active sandbox allowed
        if body.type == "sandbox":
            existing = db_query(f"""
                SELECT id FROM {ACCOUNTS_TABLE}
                WHERE type = 'sandbox' AND is_active = TRUE
                LIMIT 1
            """)
            if existing:
                raise HTTPException(status_code=409, detail="A sandbox account already exists")

        # Check duplicate account_id
        esc_acct_id = _escape_sql(body.account_id)
        dupes = db_query(f"""
            SELECT id FROM {ACCOUNTS_TABLE}
            WHERE account_id = '{esc_acct_id}'
            LIMIT 1
        """)
        if dupes:
            raise HTTPException(status_code=409, detail="This account ID already exists")

        esc_person = _escape_sql(body.person)
        esc_key = _escape_sql(body.api_key)
        esc_bot = _escape_sql(body.bot)
        esc_type = _escape_sql(body.type)

        db_execute(f"""
            INSERT INTO {ACCOUNTS_TABLE}
                (person, account_id, api_key, bot, type, is_active, created_at, updated_at)
            VALUES (
                '{esc_person}', '{esc_acct_id}', '{esc_key}', '{esc_bot}', '{esc_type}',
                TRUE, CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP()
            )
        """)

        log.info(f"[accounts] Created account {body.account_id} for {body.person} ({body.type})")
        return {"success": True, "message": f"Account {body.account_id} created"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class AccountUpdate(BaseModel):
    bot: Optional[str] = None
    api_key: Optional[str] = None
    is_active: Optional[bool] = None


@app.put("/api/accounts/{account_db_id}")
async def update_account(account_db_id: int, body: AccountUpdate):
    """Update an existing account (bot assignment, API key, active status)."""
    try:
        existing = db_query(f"""
            SELECT id, person, account_id FROM {ACCOUNTS_TABLE}
            WHERE id = {account_db_id}
            LIMIT 1
        """)
        if not existing:
            raise HTTPException(status_code=404, detail="Account not found")

        updates = []
        if body.bot is not None:
            if body.bot not in ("FLAME", "SPARK", "INFERNO", "BOTH"):
                raise HTTPException(status_code=400, detail="bot must be FLAME, SPARK, INFERNO, or BOTH")
            updates.append(f"bot = '{_escape_sql(body.bot)}'")
        if body.api_key is not None:
            updates.append(f"api_key = '{_escape_sql(body.api_key)}'")
        if body.is_active is not None:
            updates.append(f"is_active = {body.is_active}")

        if not updates:
            return {"success": True, "message": "No changes"}

        updates.append("updated_at = CURRENT_TIMESTAMP()")
        set_clause = ", ".join(updates)

        db_execute(f"""
            UPDATE {ACCOUNTS_TABLE}
            SET {set_clause}
            WHERE id = {account_db_id}
        """)

        log.info(f"[accounts] Updated account id={account_db_id}")
        return {"success": True, "message": "Account updated"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/accounts/{account_db_id}")
async def deactivate_account(account_db_id: int):
    """Soft delete — sets is_active = false. Never hard deletes."""
    try:
        existing = db_query(f"""
            SELECT id, person, account_id FROM {ACCOUNTS_TABLE}
            WHERE id = {account_db_id}
            LIMIT 1
        """)
        if not existing:
            raise HTTPException(status_code=404, detail="Account not found")

        db_execute(f"""
            UPDATE {ACCOUNTS_TABLE}
            SET is_active = FALSE, updated_at = CURRENT_TIMESTAMP()
            WHERE id = {account_db_id}
        """)

        acct = existing[0]
        log.info(f"[accounts] Deactivated {acct['account_id']} ({acct['person']})")
        return {"success": True, "message": f"Account {acct['account_id']} deactivated"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class TestAccountRequest(BaseModel):
    account_id: str
    api_key: str


@app.post("/api/accounts/test")
async def test_account(body: TestAccountRequest):
    """Test a single account's API key against Tradier sandbox."""
    try:
        resp = requests.get(
            f"{SANDBOX_URL}/user/profile",
            headers={
                "Authorization": f"Bearer {body.api_key}",
                "Accept": "application/json",
            },
            timeout=5,
        )
        if resp.ok:
            return {"account_id": body.account_id, "success": True, "message": "Connected"}
        else:
            return {
                "account_id": body.account_id,
                "success": False,
                "message": f"HTTP {resp.status_code}",
            }
    except requests.exceptions.Timeout:
        return {"account_id": body.account_id, "success": False, "message": "Timeout"}
    except Exception as e:
        return {"account_id": body.account_id, "success": False, "message": str(e)}


class TestAllRequest(BaseModel):
    accounts: list[TestAccountRequest]


@app.post("/api/accounts/test-all")
async def test_all_accounts(body: TestAllRequest):
    """Test all provided accounts in parallel (5s timeout each)."""
    import concurrent.futures

    def _test_one(acct: TestAccountRequest) -> dict:
        try:
            resp = requests.get(
                f"{SANDBOX_URL}/user/profile",
                headers={
                    "Authorization": f"Bearer {acct.api_key}",
                    "Accept": "application/json",
                },
                timeout=5,
            )
            if resp.ok:
                return {"account_id": acct.account_id, "success": True, "message": "Connected"}
            return {"account_id": acct.account_id, "success": False, "message": f"HTTP {resp.status_code}"}
        except requests.exceptions.Timeout:
            return {"account_id": acct.account_id, "success": False, "message": "Timeout"}
        except Exception as e:
            return {"account_id": acct.account_id, "success": False, "message": str(e)}

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(_test_one, acct) for acct in body.accounts]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    return results
