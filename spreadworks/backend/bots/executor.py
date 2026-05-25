"""Paper-trade executor — open / close / MTM for one bot.

NO BROKER CALLS. Fills use mid prices passed in by the caller; this module
never imports anything from Tradier. Keeps the paper-only invariant explicit.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import Any, Iterable

from sqlalchemy import text
from sqlalchemy.engine import Engine

from .db import bot_table, load_config
from .strategies import CREDIT_STRATEGIES

logger = logging.getLogger("spreadworks.bots.executor")


def account_equity(engine: Engine, bot: str) -> float:
    """starting_capital + cumulative realized P&L (closed trades)."""
    cfg = load_config(engine, bot)
    t = bot_table(bot, "closed_trades")
    with engine.begin() as conn:
        row = conn.execute(text(
            f"SELECT COALESCE(SUM(realized_pnl), 0) AS s FROM {t}"
        )).mappings().first()
    return float(cfg["starting_capital"]) + float(row["s"] or 0)


def _new_position_id(bot: str, now: datetime) -> str:
    return f"{bot}-{now.date().isoformat()}-{uuid.uuid4().hex[:8]}"


def open_position(
    engine: Engine,
    bot: str,
    strategy: str,
    signal: Any,
    now: datetime,
) -> str:
    """Insert one OPEN row into {bot}_positions, return position_id."""
    pid = _new_position_id(bot, now)
    t = bot_table(bot, "positions")
    # All signals expose .legs(), .pt_target_pnl, .sl_target_pnl, .max_profit,
    # .max_loss, .contracts, .ticker plus EITHER .credit (IBF) OR .debit (DC/DD).
    entry_price = signal.credit if hasattr(signal, "credit") else signal.debit
    legs_json = json.dumps(signal.legs())
    with engine.begin() as conn:
        conn.execute(text(
            f"INSERT INTO {t} ("
            "position_id, ticker, strategy, legs, entry_price, contracts, entry_time, "
            "status, mtm_value, mtm_pnl, mtm_updated_at, pt_target_pnl, sl_target_pnl, "
            "max_profit, max_loss, account_label"
            ") VALUES ("
            ":pid, :tk, :st, :legs, :ep, :ct, :et, 'OPEN', :mv, 0, :et, "
            ":pt, :sl, :mp, :ml, 'paper'"
            ")"
        ), {
            "pid": pid, "tk": signal.ticker, "st": strategy, "legs": legs_json,
            "ep": entry_price, "ct": signal.contracts, "et": now,
            "mv": entry_price,
            "pt": signal.pt_target_pnl, "sl": signal.sl_target_pnl,
            "mp": signal.max_profit * signal.contracts,
            "ml": signal.max_loss * signal.contracts,
        })
    logger.info(f"[{bot}] opened {pid} {strategy} entry={entry_price} contracts={signal.contracts}")
    return pid


def close_position(
    engine: Engine,
    bot: str,
    position_id: str,
    close_value: float,
    close_reason: str,
    now: datetime,
) -> float:
    """Move position OPEN -> CLOSED. Returns realized_pnl ($)."""
    t_pos = bot_table(bot, "positions")
    t_cls = bot_table(bot, "closed_trades")
    with engine.begin() as conn:
        row = conn.execute(text(
            f"SELECT * FROM {t_pos} WHERE position_id=:p AND status='OPEN'"
        ), {"p": position_id}).mappings().first()
        if row is None:
            raise ValueError(f"{position_id} not OPEN (already closed or unknown)")

        strategy = row["strategy"]
        entry_price = float(row["entry_price"])
        contracts = int(row["contracts"])
        if strategy in CREDIT_STRATEGIES:
            realized = (entry_price - float(close_value)) * contracts * 100.0
        else:
            realized = (float(close_value) - entry_price) * contracts * 100.0

        conn.execute(text(
            f"UPDATE {t_pos} SET status='CLOSED', "
            "mtm_value=:cv, mtm_pnl=:rp, mtm_updated_at=:n "
            "WHERE position_id=:p"
        ), {"cv": close_value, "rp": realized, "n": now, "p": position_id})

        conn.execute(text(
            f"INSERT INTO {t_cls} ("
            "position_id, close_price, close_time, close_reason, realized_pnl, "
            "contracts, legs, entry_price, entry_time, ticker, strategy"
            ") VALUES ("
            ":pid, :cp, :ct, :cr, :rp, :con, :legs, :ep, :et, :tk, :st"
            ")"
        ), {
            "pid": position_id, "cp": close_value, "ct": now, "cr": close_reason,
            "rp": realized, "con": contracts, "legs": row["legs"],
            "ep": entry_price, "et": row["entry_time"],
            "tk": row["ticker"], "st": strategy,
        })
    logger.info(f"[{bot}] closed {position_id} reason={close_reason} pnl={realized:.2f}")
    return realized


def list_open_positions(engine: Engine, bot: str) -> list[dict[str, Any]]:
    t = bot_table(bot, "positions")
    with engine.begin() as conn:
        rows = conn.execute(text(
            f"SELECT * FROM {t} WHERE status='OPEN' ORDER BY entry_time"
        )).mappings().all()
    return [dict(r) for r in rows]


def compute_mtm(
    *,
    strategy: str,
    legs: list[dict[str, Any]],
    entry_price: float,
    contracts: int,
    leg_mids: Iterable[float] | None = None,
    cost_to_close_override: float | None = None,
) -> tuple[float, float]:
    """Return (mtm_value, mtm_pnl).

    `leg_mids` must align with `legs` (same order). Each mid is the current
    market mid for that leg.

    For Iron Butterfly: mtm_value = short_call + short_put - long_call - long_put
        i.e. the cost to BUY BACK the structure (positive = it costs to close).
    For Double Calendar / Diagonal: mtm_value = long_back_call + long_back_put -
        short_front_call - short_front_put — i.e. the credit you'd RECEIVE to close.

    `cost_to_close_override` is used in tests to bypass the leg arithmetic.
    """
    if cost_to_close_override is not None:
        mtm_value = float(cost_to_close_override)
    else:
        mids = list(leg_mids or [])
        if len(mids) != len(legs):
            raise ValueError("leg_mids length mismatch")
        signed = 0.0
        for leg, m in zip(legs, mids):
            sign = 1.0 if leg["side"] == "short" else -1.0
            # IBF: closing buys back shorts (+) and sells longs (-)
            # DC/DD: closing buys back front shorts (+) and sells back longs (-)
            # Same sign convention works for both because we always compute
            # "cost to unwind from this side"; we invert for debit strats in
            # the PnL calculation below.
            signed += sign * m
        mtm_value = signed

    if strategy in CREDIT_STRATEGIES:
        # Credit strategies (IBF, IC, credit double diagonal): mtm_value
        # already reads as "cost to buy back the structure"; pnl is (credit
        # received - cost to close) × contracts × $100/share.
        mtm_pnl = (entry_price - mtm_value) * contracts * 100.0
    else:
        # For debit strats, mtm_value above is signed as "cost to buy in",
        # but for DC/DD we want "current credit to unwind" — flip sign:
        mtm_value = -mtm_value
        mtm_pnl = (mtm_value - entry_price) * contracts * 100.0
    return round(mtm_value, 4), round(mtm_pnl, 2)


def update_mtm(engine: Engine, bot: str, position_id: str,
               mtm_value: float, mtm_pnl: float, now: datetime) -> None:
    t = bot_table(bot, "positions")
    with engine.begin() as conn:
        conn.execute(text(
            f"UPDATE {t} SET mtm_value=:v, mtm_pnl=:p, mtm_updated_at=:n "
            "WHERE position_id=:pid"
        ), {"v": mtm_value, "p": mtm_pnl, "n": now, "pid": position_id})
